# Tool definition gồm tên, mô tả và schema tham số

Khi tích hợp tool calling, ứng dụng cần cho mô hình biết có những công cụ nào, mỗi công cụ làm việc gì và phải cung cấp dữ liệu đầu vào theo cấu trúc nào. Trong Spring AI, phần hợp đồng mô tả này được biểu diễn bằng **ToolDefinition**. Một definition có ba thành phần cốt lõi:

- **name**: tên định danh của tool.
- **description**: mô tả mục đích và tình huống nên sử dụng tool.
- **inputSchema**: JSON Schema mô tả các tham số đầu vào.

**ToolDefinition** trả lời câu hỏi “mô hình có thể yêu cầu gọi công cụ nào và cần gửi dữ liệu gì?”. **ToolCallback** kết nối definition đó với phần mã thực thi trong ứng dụng. Phân biệt hai khái niệm này giúp thiết kế giao diện cho mô hình rõ ràng mà vẫn giữ quyền kiểm soát nghiệp vụ ở phía ứng dụng.

## 1. Tool definition nằm ở đâu trong luồng gọi công cụ?

Khi ứng dụng gửi một yêu cầu chat có kèm tool, Spring AI đưa các definition tương ứng vào yêu cầu gửi đến mô hình. Mô hình đọc tên, mô tả và schema để quyết định có cần gọi tool hay không. Nếu cần, mô hình trả về một yêu cầu gọi gồm tên tool cùng các đối số dạng JSON.

Luồng xử lý thường diễn ra như sau:

1. Ứng dụng chọn những tool được phép dùng trong yêu cầu hiện tại.
2. Spring AI đưa definition của các tool đó vào yêu cầu gửi đến mô hình.
3. Mô hình chọn tool và tạo các đối số theo input schema.
4. Spring AI phân giải tên tool đến **ToolCallback** tương ứng; callback chuyển dữ liệu đầu vào cho phần thực thi của ứng dụng.
5. Ứng dụng kiểm tra dữ liệu, xác thực quyền và gọi dịch vụ nghiệp vụ.
6. Kết quả thực thi được gửi lại cho mô hình để mô hình tiếp tục trả lời hoặc yêu cầu gọi tool khác.

Mô hình chỉ gửi yêu cầu gọi tool (một lượt có thể chứa một hoặc nhiều yêu cầu gọi). Nó không tự truy cập cơ sở dữ liệu, không tự chạy phương thức Java và cũng không cấp quyền cho người dùng. Ứng dụng chịu trách nhiệm phân giải, thực thi và xử lý kết quả. Tùy cách tích hợp và phiên bản Spring AI, framework có thể điều phối vòng lặp gọi tool; nếu ứng dụng tự làm việc ở API mức thấp, ứng dụng phải nhận diện tool call, thực thi callback và gửi kết quả trở lại mô hình.

## 2. Tên tool (name)

Tên tool là định danh mà mô hình dùng khi tạo yêu cầu gọi. Spring AI sử dụng tên này để tìm callback tương ứng, vì vậy tên phải duy nhất trong tập tool được cung cấp cho cùng một yêu cầu của mô hình.

Một tên tốt nên:

- Thể hiện hành động và đối tượng nghiệp vụ, chẳng hạn **find_order_status** hoặc **create_support_ticket**.
- Ổn định qua các lần phát hành nếu ý nghĩa của tool không đổi.
- Phân biệt rõ các hành động có tác động khác nhau. **find_order_status** nên khác **cancel_order**.
- Tránh tên chung chung như **process**, **get_data** hoặc **handle_request**.

Với annotation **@Tool**, nếu không khai báo **name**, Spring AI mặc định dùng tên phương thức. Có thể đặt tên tường minh để tránh việc đổi tên phương thức nội bộ vô tình làm thay đổi giao diện mà mô hình nhìn thấy:

~~~java
@Tool(
    name = "find_order_status",
    description = "Tra cứu trạng thái của một đơn hàng theo mã đơn hàng."
)
public OrderStatus findOrderStatus(String orderId) {
    return orderQueryService.findStatus(orderId);
}
~~~

Không nên tái sử dụng cùng một tên cho hai tool có ý nghĩa khác nhau. Nếu hai tool cùng thao tác trên đơn hàng nhưng một tool chỉ đọc trạng thái còn tool kia hủy đơn, hãy đặt tên và mô tả tách biệt để mô hình không nhầm lẫn.

## 3. Mô tả tool (description)

Mô tả giúp mô hình hiểu tool dùng để làm gì và khi nào nên chọn nó. Đây là thông tin hướng dẫn lựa chọn công cụ, không phải phần trang trí cho mã nguồn. Tên tool thường chỉ truyền tải được một phần ý nghĩa; mô tả cần làm rõ phần còn lại.

Một mô tả hữu ích nên trả lời được các câu hỏi:

- Tool thực hiện hành động gì và trên đối tượng nào?
- Những câu hỏi hoặc điều kiện nào của người dùng phù hợp để gọi tool?
- Tool chỉ đọc dữ liệu hay có thể thay đổi trạng thái?
- Có giới hạn nghiệp vụ nào mô hình cần biết trước khi đề xuất gọi không?

Ví dụ, mô tả “Tra cứu đơn hàng” quá ngắn vì chưa cho biết cần mã nào và kết quả dùng để làm gì. Mô tả cụ thể hơn có thể là:

> Tra cứu trạng thái hiện tại của một đơn hàng theo mã đơn hàng. Dùng khi người dùng hỏi đơn hàng đang được xử lý, vận chuyển hay đã giao. Tool chỉ đọc thông tin và không thay đổi đơn hàng.

Mô tả cần chính xác với hành vi thực tế. Nếu tool chỉ tra cứu theo mã đơn hàng, không nên viết rằng nó có thể tìm theo tên khách hàng. Nếu tool có tác dụng phụ, cần nói rõ hành động đó để mô hình có cơ sở phân biệt với tool chỉ đọc.

Không dùng **description** để thay thế xác thực hoặc phân quyền. Viết “chỉ quản trị viên được dùng” trong mô tả không ngăn được một yêu cầu gọi trái phép. Ứng dụng vẫn phải kiểm tra quyền tại thời điểm thực thi.

## 4. Schema tham số (inputSchema)

**inputSchema** mô tả cấu trúc dữ liệu mà mô hình phải gửi khi gọi tool. Spring AI sử dụng JSON Schema để biểu diễn các trường đầu vào, kiểu dữ liệu, trường bắt buộc và các thông tin mô tả liên quan.

Schema cần đủ rõ để mô hình tạo được đối số hợp lệ. Với mỗi trường, hãy xác định:

- Tên trường có ý nghĩa và nhất quán với khái niệm nghiệp vụ.
- Kiểu dữ liệu: chuỗi, số, boolean, mảng hoặc object.
- Mô tả trường, định dạng, đơn vị đo hoặc múi giờ nếu có.
- Trường bắt buộc và trường tùy chọn.
- Tập giá trị hợp lệ nếu trường chỉ nhận một số lựa chọn cố định.

Ví dụ dưới đây minh họa schema cho tool tra cứu đơn hàng:

~~~json
{
  "type": "object",
  "properties": {
    "orderId": {
      "type": "string",
      "description": "Mã đơn hàng, ví dụ ORD-2026-001"
    },
    "includeHistory": {
      "type": "boolean",
      "description": "Có lấy thêm lịch sử thay đổi trạng thái hay không"
    }
  },
  "required": ["orderId"]
}
~~~

Trong ví dụ này, **orderId** là trường bắt buộc. **includeHistory** là trường tùy chọn; khi mô hình không gửi trường này, ứng dụng cần có quy tắc mặc định phù hợp. Nếu một trường nhận giá trị từ tập lựa chọn cố định, có thể biểu diễn bằng **enum**, chẳng hạn:

~~~json
{
  "type": "string",
  "enum": ["PENDING", "PAID", "SHIPPED", "DELIVERED"]
}
~~~

Schema nên mô tả dữ liệu mà mô hình thực sự có thể xác định. Ví dụ, nếu người dùng không cung cấp mã khách hàng và mô hình không có nguồn đáng tin cậy để biết mã đó, không nên thiết kế tham số bắt buộc buộc mô hình phải tự đoán. Hãy cân nhắc hỏi người dùng, dùng ngữ cảnh xác thực của ứng dụng hoặc thiết kế tham số tùy chọn với hành vi mặc định an toàn.

### Tham số bắt buộc và tùy chọn

Với tool khai báo bằng phương thức, Spring AI mặc định xem các tham số là bắt buộc. Có thể dùng **@ToolParam(required = false)** để đánh dấu tham số tùy chọn. **@Nullable** cũng có thể biểu thị một tham số tùy chọn theo quy tắc của Spring AI.

~~~java
@Tool(description = "Tra cứu đơn hàng theo mã và tùy chọn lấy lịch sử trạng thái.")
public OrderDetails findOrder(
        @ToolParam(description = "Mã đơn hàng cần tra cứu") String orderId,
        @ToolParam(
            description = "Có lấy lịch sử trạng thái hay không",
            required = false
        ) Boolean includeHistory) {

    return orderQueryService.findOrder(
        orderId,
        Boolean.TRUE.equals(includeHistory)
    );
}
~~~

Đánh dấu sai trạng thái bắt buộc có thể khiến mô hình tạo ra dữ liệu không có thật. Chẳng hạn, nếu **customerId** được khai báo bắt buộc nhưng người dùng chỉ cung cấp tên, mô hình có thể tự suy đoán một mã khách hàng. Hãy chọn trạng thái required dựa trên khả năng xác định giá trị và quy tắc nghiệp vụ, không dựa trên việc phương thức Java có khai báo tham số hay không.

### Mô tả từng tham số

Mô tả cấp tool cho biết khi nào nên gọi công cụ; mô tả cấp tham số giải thích cách tạo giá trị cho từng trường. Các thông tin như định dạng ngày, đơn vị tiền tệ, múi giờ, mã định danh hoặc ý nghĩa của một giá trị enum nên được ghi ngay tại tham số tương ứng.

Ví dụ, **date** chưa đủ rõ nếu hệ thống yêu cầu ngày theo múi giờ cụ thể. Mô tả “Ngày cần tra cứu, định dạng YYYY-MM-DD theo múi giờ Asia/Ho_Chi_Minh” giúp giảm khả năng mô hình gửi dữ liệu sai định dạng hoặc hiểu nhầm thời điểm.

Không gom nhiều giá trị không liên quan vào một chuỗi tự do nếu chúng có thể được biểu diễn bằng các trường riêng. Schema càng rõ ràng, ứng dụng càng dễ kiểm tra và chuyển đổi dữ liệu.

## 5. Khai báo definition bằng @Tool và @ToolParam

Đây là cách khai báo thuận tiện khi ứng dụng sở hữu phương thức cần đưa ra làm tool. Spring AI đọc annotation để tạo **ToolDefinition** và liên kết definition với logic gọi phương thức.

~~~java
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;

public class OrderTools {

    private final OrderQueryService orderQueryService;

    public OrderTools(OrderQueryService orderQueryService) {
        this.orderQueryService = orderQueryService;
    }

    @Tool(
        name = "find_order_status",
        description = """
            Tra cứu trạng thái hiện tại của một đơn hàng theo mã đơn hàng.
            Dùng khi người dùng hỏi đơn hàng đang được xử lý, vận chuyển
            hay đã giao. Tool chỉ đọc thông tin và không thay đổi đơn hàng.
            """
    )
    public OrderStatus findOrderStatus(
            @ToolParam(
                description = "Mã đơn hàng, ví dụ ORD-2026-001"
            ) String orderId) {

        return orderQueryService.findStatus(orderId);
    }
}
~~~

Đưa đối tượng chứa phương thức đã đánh dấu **@Tool** vào yêu cầu **ChatClient**:

~~~java
String answer = ChatClient.create(chatModel)
    .prompt()
    .user("Đơn hàng ORD-2026-001 đang ở trạng thái nào?")
    .tools(new OrderTools(orderQueryService))
    .call()
    .content();
~~~

Trong ví dụ:

- **@Tool** định nghĩa tên và mô tả ở cấp công cụ.
- **@ToolParam** bổ sung mô tả cho **orderId**.
- Kiểu Java của tham số được dùng để sinh kiểu dữ liệu trong schema.
- Phương thức gọi dịch vụ nghiệp vụ để lấy kết quả thực tế.

Spring AI cũng hỗ trợ các cách khai báo bằng **MethodToolCallback** hoặc **FunctionToolCallback**. Những cách này hữu ích khi cần tạo tool động, dùng function hoặc method reference, hay khi không thể gắn annotation lên phương thức hiện có. Dù khai báo theo cách nào, mô hình vẫn cần nhận được một definition có tên, mô tả và schema đầu vào rõ ràng.

## 6. Tạo ToolDefinition tường minh

Khi cần tự kiểm soát schema hoặc tạo tool tại thời điểm chạy, có thể xây dựng **ToolDefinition** trực tiếp:

~~~java
ToolDefinition definition = ToolDefinition.builder()
    .name("find_order_status")
    .description(
        "Tra cứu trạng thái hiện tại của đơn hàng theo mã đơn hàng."
    )
    .inputSchema("""
        {
          "type": "object",
          "properties": {
            "orderId": {
              "type": "string",
              "description": "Mã đơn hàng cần tra cứu"
            }
          },
          "required": ["orderId"]
        }
        """)
    .build();
~~~

**ToolDefinition** chỉ mô tả hợp đồng mà mô hình nhìn thấy. Để thực thi, ứng dụng còn cần một **ToolCallback** liên kết definition với logic xử lý. **ToolCallback** cung cấp definition và phương thức nhận dữ liệu JSON để thực thi tool; Spring AI có các implementation dựng sẵn như **MethodToolCallback** và **FunctionToolCallback**.

Có thể hiểu quan hệ giữa các thành phần như sau:

| Thành phần | Trách nhiệm |
| --- | --- |
| **ToolDefinition** | Công bố tên, mô tả và schema đầu vào cho mô hình |
| **ToolCallback** | Kết nối definition với hành vi thực thi |
| **@Tool** | Khai báo một phương thức Java như tool |
| **@ToolParam** | Mô tả và xác định trạng thái bắt buộc của tham số |
| **ToolContext** | Chuyển dữ liệu ngữ cảnh từ ứng dụng đến lúc thực thi |

## 7. Phân biệt input schema với ToolContext

Không phải dữ liệu nào phương thức cần cũng nên yêu cầu mô hình gửi. **ToolContext** cho phép ứng dụng chuyển thông tin nội bộ đến tool khi thực thi, chẳng hạn mã tenant, mã người dùng đã xác thực hoặc thông tin request scope. Dữ liệu này không được đưa vào schema cho mô hình và không cần để mô hình tự tạo.

Ví dụ, nếu người dùng đã đăng nhập trong tenant **acme**, ứng dụng có thể truyền tenant hiện tại qua tool context. Tool lấy tenant từ ngữ cảnh này để giới hạn truy vấn:

~~~java
@Tool(description = "Tra cứu thông tin đơn hàng theo mã đơn hàng.")
public OrderStatus findOrderStatus(
        @ToolParam(description = "Mã đơn hàng cần tra cứu") String orderId,
        ToolContext toolContext) {

    String tenantId =
        (String) toolContext.getContext().get("tenantId");

    return orderQueryService.findStatusForTenant(tenantId, orderId);
}
~~~

Khi gọi **ChatClient**, ứng dụng có thể truyền context:

~~~java
String answer = ChatClient.create(chatModel)
    .prompt()
    .user("Kiểm tra trạng thái đơn hàng ORD-2026-001")
    .tools(orderTools)
    .toolContext(Map.of("tenantId", authenticatedTenantId))
    .call()
    .content();
~~~

**tenantId** ở ví dụ trên đến từ phiên đăng nhập do ứng dụng xác minh. Không đưa **tenantId** thành tham số do mô hình tự chọn nếu mục đích của nó là giới hạn dữ liệu theo tenant hiện tại. Cùng nguyên tắc đó áp dụng cho user ID, role, quyền truy cập và thông tin bảo mật khác.

## 8. Các nguyên tắc thiết kế và kiểm tra

Một definition tốt cần giúp mô hình chọn đúng tool và tạo được dữ liệu đầu vào có ý nghĩa. Tuy nhiên, schema không thay thế kiểm tra ở phía server. Đầu vào do mô hình tạo vẫn phải được parse, kiểm tra hợp lệ và áp dụng quy tắc nghiệp vụ trước khi thực thi.

Khi thiết kế tool cho hệ thống nghiệp vụ, nên lưu ý:

1. **Chọn đúng phạm vi tool cho từng yêu cầu.** Chỉ cung cấp những tool mà người dùng và luồng nghiệp vụ hiện tại được phép sử dụng. Một tool không được đưa vào request thì mô hình không thể đề xuất gọi nó trong request đó.
2. **Kiểm tra quyền trong tầng ứng dụng.** Không xem tên, mô tả hoặc schema là cơ chế phân quyền. Dịch vụ nghiệp vụ cần xác minh người dùng, tenant và quyền trên tài nguyên trước khi đọc hoặc thay đổi dữ liệu.
3. **Tách thao tác đọc và thao tác ghi.** Dùng tên riêng cho tra cứu, cập nhật, thanh toán hoặc hủy. Với hành động nhạy cảm, cần có bước xác nhận hoặc cơ chế phê duyệt phù hợp với chính sách ứng dụng.
4. **Xử lý đầu vào không hợp lệ.** Kiểm tra mã định danh có tồn tại không, ngày có đúng định dạng không, số lượng có nằm trong giới hạn không và giá trị enum có được hỗ trợ không.
5. **Trả lỗi có thể xử lý.** Phân biệt dữ liệu không hợp lệ, không tìm thấy tài nguyên, không đủ quyền và lỗi dịch vụ phụ thuộc. Chỉ gửi lại mô hình thông tin lỗi cần thiết; không để lộ stack trace, bí mật hoặc dữ liệu nội bộ.
6. **Giới hạn dữ liệu trả về.** Kết quả tool có thể được đưa trở lại ngữ cảnh của mô hình. Chỉ trả các trường cần cho câu hỏi; tránh gửi toàn bộ entity, thông tin cá nhân hoặc dữ liệu không liên quan.
7. **Thiết kế an toàn khi gọi lặp.** Mô hình có thể yêu cầu gọi tool nhiều lần trong một cuộc hội thoại. Với thao tác ghi, cần cân nhắc idempotency, kiểm tra trạng thái trước khi thực hiện và lưu dấu vết giao dịch.

Nên kiểm tra definition và callback ở cả hai mức:

- **Kiểm tra hợp đồng:** tên có duy nhất không; mô tả có nói đúng hành vi không; schema có đúng kiểu, trường bắt buộc, trường tùy chọn và định dạng không.
- **Kiểm tra thực thi:** dữ liệu hợp lệ, dữ liệu thiếu hoặc sai kiểu, tài nguyên không tồn tại, người dùng không đủ quyền, lỗi từ dịch vụ phụ thuộc và trường hợp tool được gọi lặp.
- **Kiểm tra tích hợp:** xác nhận mô hình có thể chọn đúng tool với câu hỏi đại diện, tạo đúng đối số và sử dụng kết quả tool trong câu trả lời tiếp theo.

Một số dấu hiệu cho thấy definition cần được cải thiện:

| Dấu hiệu | Hướng điều chỉnh |
| --- | --- |
| Mô hình thường chọn nhầm tool | Làm rõ khác biệt trong **name** và **description**; thu hẹp phạm vi từng tool |
| Mô hình tự đoán mã hoặc ID | Xem lại trường bắt buộc; yêu cầu người dùng cung cấp hoặc lấy giá trị từ context đáng tin cậy |
| Ngày, giờ hoặc số đo thường sai | Ghi rõ định dạng, múi giờ và đơn vị trong mô tả tham số |
| Tool nhận quá nhiều dữ liệu không liên quan | Chia tham số thành trường có cấu trúc và chỉ công bố dữ liệu cần thiết |
| Tool thực hiện hành động ngoài ý muốn | Tách tool đọc/ghi, giới hạn tool được cung cấp và bổ sung xác nhận cùng kiểm tra quyền |

## 9. Ghi nhớ

**ToolDefinition** là hợp đồng giao tiếp giữa mô hình và ứng dụng:

- **name** giúp định danh chính xác tool cần gọi.
- **description** giúp mô hình hiểu mục đích và thời điểm nên gọi.
- **inputSchema** giúp mô hình tạo đối số theo cấu trúc mà ứng dụng mong đợi.

Spring AI có thể sinh definition từ phương thức thông qua **@Tool** và **@ToolParam**, hoặc cho phép xây dựng tường minh khi cần kiểm soát cao hơn. Sau khi mô hình đề xuất một tool call, **ToolCallback** và ứng dụng đảm nhận việc phân giải, xác thực, thực thi và trả kết quả. Thiết kế definition rõ ràng giúp mô hình sử dụng công cụ chính xác hơn; kiểm tra quyền và dữ liệu ở phía ứng dụng mới bảo đảm thao tác nghiệp vụ được thực hiện an toàn.

## Tài liệu tham khảo

- [Spring AI Reference — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
