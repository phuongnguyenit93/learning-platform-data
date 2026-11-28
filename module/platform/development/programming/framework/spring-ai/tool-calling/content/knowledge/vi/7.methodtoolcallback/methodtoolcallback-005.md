# Truyền ToolContext vào phương thức khi cần

`MethodToolCallback` cho phép biến một phương thức Java đã chọn thành một `ToolCallback`. Cách này hữu ích khi ứng dụng muốn chủ động tạo callback từ một `Method`, cung cấp `ToolDefinition` riêng hoặc tái sử dụng một phương thức nghiệp vụ hiện có mà không phải xây dựng một callback hoàn toàn mới.

Một phương thức công cụ đôi khi cần dữ liệu theo từng yêu cầu như người dùng đã xác thực, tenant, mã tương quan hoặc ngôn ngữ hiển thị. Những dữ liệu này thuộc ngữ cảnh thực thi của ứng dụng. Không nên yêu cầu mô hình tự tạo chúng như đối số JSON. Spring AI cung cấp `ToolContext` để chuyển ngữ cảnh do ứng dụng chuẩn bị vào phương thức công cụ khi callback được thực thi.

Bài này giải thích cách chọn phương thức và đối tượng đích cho `MethodToolCallback`, cách khai báo hợp đồng công cụ, cách nhận `ToolContext`, cách giữ dữ liệu tin cậy ngoài schema gửi mô hình, cùng các lưu ý về reflection, Spring proxy, lỗi và AOT.

## MethodToolCallback làm nhiệm vụ gì?

Một `MethodToolCallback` đóng vai trò cầu nối giữa yêu cầu gọi công cụ và một phương thức Java. Ở mức khái quát, nó thực hiện các việc sau:

1. Công bố định nghĩa công cụ cho Spring AI, gồm tên, mô tả và schema đầu vào.
2. Nhận chuỗi JSON arguments do mô hình tạo ra.
3. Chuyển JSON thành các giá trị phù hợp với tham số Java của phương thức.
4. Chèn `ToolContext` do ứng dụng cung cấp nếu chữ ký phương thức có tham số ngữ cảnh.
5. Gọi phương thức trên đối tượng đích đã cấu hình.
6. Chuyển kết quả trả về thành nội dung kết quả công cụ theo cơ chế converter.

Mô hình chỉ nhìn thấy hợp đồng công cụ và gửi tên cùng đối số. Nó không gọi reflection và không tự thực thi phương thức Java. Callback và ứng dụng chịu trách nhiệm cho việc chuyển đổi, thực thi và xử lý kết quả.

## Phân biệt ba thành phần khi tạo callback

Khi tạo `MethodToolCallback`, cần phân biệt rõ:

| Thành phần | Vai trò |
|---|---|
| `Method` | Chỉ chính xác phương thức Java cần gọi, bao gồm lớp khai báo và danh sách kiểu tham số. |
| Tool object | Đối tượng đích mà phương thức instance sẽ được gọi trên đó, thường là Spring bean đã được inject dependency. |
| `ToolDefinition` | Hợp đồng được gửi tới mô hình: tên, mô tả và JSON Schema của đối số mà mô hình được phép tạo. |

Ba thành phần này phải khớp nhau. Nếu `ToolDefinition` mô tả hai đối số nhưng phương thức cần ba đối số JSON, callback không thể tự suy ra ý nghĩa còn thiếu. Nếu chọn sai overload hoặc truyền nhầm đối tượng đích, lời gọi reflection có thể thất bại hoặc chạy nhầm logic.

## Chọn Method và đối tượng đích

`Method` có thể được lấy bằng reflection. Nên chỉ rõ kiểu của tất cả tham số để tránh chọn nhầm overload:

```java
Method method = OrderTools.class.getMethod(
        "getOrderStatus",
        String.class,
        ToolContext.class
);
```

Ví dụ này chọn phương thức `getOrderStatus(String, ToolContext)` trên `OrderTools`. Nếu có một overload nhận `UUID` hoặc chỉ nhận `String`, danh sách kiểu tham số giúp lựa chọn rõ ràng.

Với phương thức instance, đối tượng đích phải là instance tương thích với lớp khai báo phương thức. Trong ứng dụng Spring, hãy inject bean đã được container quản lý:

```java
@Component
class OrderTools {

    private final OrderQueryService orderQueryService;

    OrderTools(OrderQueryService orderQueryService) {
        this.orderQueryService = orderQueryService;
    }

    public OrderStatusView getOrderStatus(
            String orderId,
            ToolContext toolContext) {
        // Xử lý truy vấn đơn hàng
        return orderQueryService.findStatus(orderId);
    }
}
```

Không tự gọi `new OrderTools(...)` để tạo một bản sao nếu ứng dụng đã có bean. Bean do Spring quản lý giữ đúng dependency, cấu hình, transaction, security advice và các interceptor khác mà ứng dụng đã thiết lập.

### Phương thức overload và phạm vi truy cập

Khi lớp có nhiều phương thức cùng tên, dùng `getMethod(name, parameterTypes...)` hoặc cách lấy `Method` tương đương với chữ ký đầy đủ. Không chọn phương thức chỉ dựa trên tên.

Ưu tiên phương thức `public` với chữ ký ổn định. Phương thức private/protected hoặc phụ thuộc vào quyền truy cập reflection có thể gây khó khăn khi callback được tạo, khi module Java giới hạn truy cập hoặc khi đóng gói ứng dụng. Nếu thật sự cần phương thức không public, hãy xác minh khả năng truy cập của phiên bản và môi trường chạy mục tiêu.

Với phương thức static, không cần trạng thái instance theo cùng cách với phương thức instance; tuy nhiên, phần lớn công cụ nghiệp vụ cần dependency injection nên phương thức instance trên Spring bean thường dễ quản lý hơn.

## Xây dựng MethodToolCallback

Ví dụ sau minh họa việc chọn `Method`, cung cấp bean đích và định nghĩa schema riêng. Các import và chi tiết builder cần được đối chiếu với release line Spring AI đang dùng vì API có thể thay đổi giữa các phiên bản:

```java
Method method = OrderTools.class.getMethod(
        "getOrderStatus",
        String.class,
        ToolContext.class
);

ToolDefinition definition = ToolDefinition.builder()
        .name("getOrderStatus")
        .description("Tra cứu trạng thái hiện tại của đơn hàng theo mã đơn.")
        .inputSchema("""
                {
                  "type": "object",
                  "properties": {
                    "orderId": {
                      "type": "string",
                      "description": "Mã đơn hàng do hệ thống cấp"
                    }
                  },
                  "required": ["orderId"]
                }
                """)
        .build();

ToolCallback callback = MethodToolCallback.builder()
        .toolDefinition(definition)
        .toolMethod(method)
        .toolObject(orderTools)
        .build();
```

Trong ví dụ, `orderTools` là bean `OrderTools` đã được inject. Schema chỉ có `orderId`. `ToolContext` không xuất hiện trong JSON Schema vì nó được ứng dụng truyền riêng trong ngữ cảnh thực thi.

Khi tự cung cấp `ToolDefinition`, hãy giữ schema đồng bộ với chữ ký phương thức. Tên và mô tả trong định nghĩa là hợp đồng công khai mà mô hình sử dụng; thay đổi schema mà không thay đổi hoặc kiểm tra lại phương thức có thể gây lỗi chuyển đổi arguments lúc chạy.

Một số phiên bản hoặc cách tạo callback có thể hỗ trợ sinh định nghĩa từ metadata/annotation của phương thức. Nếu dùng cơ chế đó, vẫn cần kiểm tra kết quả sinh ra và xác nhận `ToolContext` không bị đưa thành một trường đầu vào mà mô hình phải tự cung cấp.

## Nhận ToolContext trong chữ ký phương thức

Một phương thức công cụ có thể khai báo `ToolContext` để đọc dữ liệu mà ứng dụng gắn vào lần gọi. Ví dụ:

```java
public OrderStatusView getOrderStatus(
        @ToolParam(description = "Mã đơn hàng do hệ thống cấp") String orderId,
        ToolContext toolContext) {

    Object userIdValue = toolContext.getContext().get("userId");
    if (!(userIdValue instanceof String userId) || userId.isBlank()) {
        throw new IllegalStateException("Thiếu danh tính người dùng trong tool context");
    }

    return orderQueryService.findStatusForUser(orderId, userId);
}
```

Ở đây:

- `orderId` là đối số nghiệp vụ do mô hình đề xuất theo schema.
- `userId` là dữ liệu do ứng dụng cung cấp qua `ToolContext`.
- `findStatusForUser` kiểm tra quyền trên chính đơn hàng trước khi trả dữ liệu.

Nên đặt `ToolContext` ở cuối chữ ký để người đọc dễ nhận biết nó là tham số ngữ cảnh đặc biệt, và để phù hợp với quy ước của các API Spring AI đang dùng. Hãy xác minh chữ ký mà phiên bản dự án hỗ trợ.

Không thêm `ToolContext` vào schema như một object thông thường. Nếu mô hình được yêu cầu tạo `userId`, `tenantId` hoặc quyền truy cập, nó có thể gửi một giá trị giả hoặc giá trị của người khác. Context là kênh truyền dữ liệu từ ứng dụng đến callback, không phải một trường người dùng có thể điều khiển.

## Đưa context vào yêu cầu ChatClient

Ứng dụng tạo context từ thông tin đã xác thực và truyền nó theo yêu cầu chat có cung cấp callback. Ví dụ minh họa theo fluent API của các phiên bản Spring AI hỗ trợ `toolCallbacks(...)` và `toolContext(...)`:

```java
Map<String, Object> context = Map.of(
        "userId", authenticatedUser.id(),
        "tenantId", authenticatedUser.tenantId(),
        "requestId", requestId
);

String answer = chatClient.prompt()
        .user("Tra cứu trạng thái đơn hàng DH-100")
        .toolCallbacks(callback)
        .toolContext(context)
        .call()
        .content();
```

Tên phương thức hoặc vị trí cấu hình context có thể khác theo API của release line. Hãy kiểm tra tài liệu và chữ ký thực tế của phiên bản dự án. Nguyên tắc không đổi: ứng dụng tạo map context cho từng yêu cầu, framework chuyển nó tới callback khi thực thi tool.

Không dùng map tĩnh dùng chung cho nhiều người dùng. Hãy tạo context riêng theo request, chỉ đưa các trường cần thiết và tránh sửa map sau khi đã gửi đi. Nếu xử lý bất đồng bộ hoặc đồng thời, không giữ context trong biến mutable dùng chung giữa các hội thoại.

## ToolContext có gì và không nên chứa gì?

`ToolContext` mang dữ liệu phụ trợ cho việc thực thi. Các giá trị thường hữu ích gồm:

| Dữ liệu | Mục đích |
|---|---|
| `userId` đã xác thực | Xác định chủ thể thực hiện yêu cầu. |
| `tenantId` | Giới hạn truy vấn trong tenant hiện tại. |
| `requestId` hoặc correlation ID | Nối log và trace của model request với tool execution. |
| Locale hoặc múi giờ đã chọn | Định dạng thông tin trả về phù hợp với yêu cầu. |
| Chính sách hoặc phạm vi đã được ứng dụng xác định | Chuyển một quyết định đã được kiểm tra để service áp dụng tiếp. |

Tránh đưa vào context:

- API key, mật khẩu, access token hoặc thông tin xác thực thô nếu phương thức không thực sự cần chúng.
- Toàn bộ đối tượng session, request hoặc principal chứa nhiều dữ liệu riêng tư.
- Các quyền do mô hình tự đề xuất hoặc giá trị lấy trực tiếp từ nội dung người dùng mà chưa được xác minh.
- Dữ liệu lớn không cần thiết cho một lần gọi công cụ.

Ưu tiên truyền các giá trị nhỏ, có kiểu và có nguồn gốc rõ ràng. Nếu context chứa một đối tượng domain, hãy cân nhắc truyền ID hoặc một projection tối thiểu để tránh phụ thuộc quá chặt vào cấu trúc nội bộ.

## Giữ ranh giới tin cậy và kiểm tra quyền

Không được coi `ToolContext` là một cơ chế tự động phân quyền. Context chỉ vận chuyển dữ liệu; service vẫn phải áp dụng quy tắc bảo mật.

Ví dụ, người dùng có thể hỏi về mã đơn hàng thuộc tài khoản khác. Mô hình có thể tạo một tool call hoàn toàn đúng schema, nhưng điều đó không chứng minh người dùng có quyền xem đơn. Service nên truy vấn theo cả `orderId` và `userId`/`tenantId`, hoặc gọi một authorization service trước khi trả dữ liệu.

```java
public OrderStatusView getOrderStatus(
        String orderId,
        ToolContext toolContext) {

    String userId = requireString(toolContext, "userId");
    String tenantId = requireString(toolContext, "tenantId");

    return orderQueryService.findStatusForUserAndTenant(
            orderId,
            userId,
            tenantId
    );
}
```

Các hàm `requireString` và `findStatusForUserAndTenant` là minh họa cho helper/service của ứng dụng. Điểm quan trọng là quyền được kiểm tra trên tài nguyên thực tế. Không chỉ kiểm tra một lần rằng người dùng có quyền gọi tên công cụ `getOrderStatus`.

Với thao tác ghi, context có thể xác định chủ thể và tenant, nhưng ứng dụng vẫn cần kiểm tra trạng thái nghiệp vụ, xác nhận người dùng nếu cần, tính lặp an toàn và điều kiện chống thực thi trùng. Không biến việc mô hình chọn một tool call thành sự chấp thuận cho hành động có tác động.

## Ánh xạ JSON arguments và ToolContext

Callback phải phân biệt hai nguồn dữ liệu:

| Nguồn | Cách đi vào phương thức | Ai kiểm soát? |
|---|---|---|
| JSON arguments | Được converter chuyển thành các tham số nghiệp vụ như `String orderId` hoặc DTO. | Mô hình đề xuất; ứng dụng phải validation. |
| ToolContext | Được framework truyền riêng vào tham số `ToolContext`. | Ứng dụng tạo từ nguồn tin cậy cho từng request. |

Ví dụ, JSON arguments của lời gọi có thể là:

```json
{
  "orderId": "DH-100"
}
```

Trong khi context do ứng dụng cung cấp có thể chứa:

```json
{
  "userId": "user-42",
  "tenantId": "tenant-7",
  "requestId": "req-a91"
}
```

Hai phần được kết hợp ở thời điểm thực thi. `userId` và `tenantId` không cần xuất hiện trong JSON arguments hoặc schema mà mô hình nhìn thấy. Không gộp context vào chuỗi JSON arguments để tiện chuyển đổi; làm vậy sẽ làm lẫn dữ liệu do mô hình điều khiển với dữ liệu do ứng dụng tin cậy.

Khi tự định nghĩa schema, hãy bảo đảm các trường trong schema khớp chính xác với tham số JSON của phương thức. Tham số đặc biệt `ToolContext` không phải một trường trong object đầu vào. Với DTO phức tạp, hãy kiểm tra thứ tự/ánh xạ tham số theo converter của phiên bản đang dùng thay vì tự giả định.

## Xử lý lỗi khi gọi phương thức qua reflection

Một lời gọi `MethodToolCallback` có thể thất bại ở nhiều giai đoạn:

1. **Tạo callback:** không tìm thấy phương thức, chọn sai overload hoặc `Method` không tương thích với đối tượng đích.
2. **Phân tích JSON:** JSON sai cú pháp hoặc không chuyển được sang kiểu tham số Java.
3. **Thiếu context:** context không có trường bắt buộc hoặc giá trị có kiểu không đúng.
4. **Thực thi:** phương thức hoặc service phía sau ném exception, timeout hoặc từ chối quyền.
5. **Chuyển kết quả:** kết quả không thể serialize hoặc vượt giới hạn mà ứng dụng/provider cho phép.

Hãy phân loại lỗi ở nơi phù hợp. Lỗi cấu hình callback thường nên được phát hiện khi khởi tạo ứng dụng hoặc trong kiểm thử. Lỗi đầu vào và quyền truy cập cần được xử lý tại ranh giới thực thi. Lỗi dịch vụ ngoài cần có timeout và retry theo tính chất của thao tác.

Không gửi stack trace, SQL, token hoặc chi tiết nội bộ cho mô hình. Nếu cấu hình xử lý lỗi để trả thông báo về tool result, hãy dùng thông báo ngắn, an toàn và đủ để mô hình phản hồi hoặc hỏi lại. Log kỹ thuật có thể giữ correlation ID và nguyên nhân chi tiết sau khi che dữ liệu nhạy cảm.

## Reflection, Spring proxy và AOP

`MethodToolCallback` dựa vào `Method` và cơ chế gọi reflection. Vì vậy, cách lấy method và đối tượng đích có ảnh hưởng trực tiếp đến việc callback có chạy đúng bean hay không.

- Chọn method từ đúng class hoặc interface tương thích với đối tượng đích.
- Dùng bean Spring đã được inject để giữ dependency injection và các interceptor.
- Nếu bean được bọc bằng JDK dynamic proxy, phương thức cần gọi phải có thể được truy cập qua interface mà proxy công bố. Phương thức chỉ tồn tại trên implementation có thể không gọi được qua proxy đó.
- Với CGLIB proxy hoặc proxy lồng nhau, hãy kiểm tra method và object thực tế được truyền vào builder.
- Không tự unwrap proxy hoặc gọi target object trực tiếp nếu việc đó làm bỏ qua transaction, security, caching hay các advice đang được ứng dụng dựa vào.
- Tránh overload có chữ ký gần giống nhau; chọn method với kiểu tham số cụ thể và kiểm tra callback ngay khi khởi tạo.

Nếu phương thức có `@Transactional`, `@PreAuthorize` hoặc interceptor riêng, hãy kiểm thử rằng lời gọi qua callback đi qua đúng proxy. Đừng chỉ kiểm thử bằng cách gọi trực tiếp phương thức trên một instance được tạo bằng `new`.

## AOT và native image

Reflection có thể cần metadata bổ sung khi ứng dụng được biên dịch AOT hoặc đóng gói thành native image. Build JVM thành công không chứng minh mọi method reflection sẽ hoạt động trong native executable.

Khi triển khai theo hướng AOT/native:

1. Kiểm tra tài liệu Spring AI và Spring Boot đúng phiên bản để biết những runtime hint nào đã được cung cấp.
2. Đăng ký reflection hint cho class, constructor và method cần thiết nếu build yêu cầu.
3. Chạy native build và kiểm thử chính callback trong executable thực tế.
4. Kiểm tra các method được chọn động hoặc tên method lấy từ cấu hình vì công cụ phân tích tĩnh có thể không suy ra được chúng.

Không thêm hint một cách mù quáng. Hãy dùng thông báo lỗi của AOT/native build để xác định metadata thực sự còn thiếu.

## Kiểm thử MethodToolCallback và ToolContext

Hãy kiểm thử cả việc chọn method, mapping JSON, context và service nghiệp vụ:

| Tình huống | Điều cần xác minh |
|---|---|
| Chọn đúng method | Builder dùng đúng `Method` và đúng bean đích. |
| Có overload | Callback không chọn nhầm chữ ký khác cùng tên. |
| JSON hợp lệ | `orderId` được chuyển thành đúng tham số Java. |
| JSON thiếu hoặc sai kiểu | Callback từ chối trước khi thực thi hoặc trả lỗi có kiểm soát. |
| Context hợp lệ | `userId`, `tenantId` và `requestId` đến đúng phương thức. |
| Context thiếu hoặc sai kiểu | Phương thức từ chối an toàn, không tự suy đoán danh tính. |
| Hai request đồng thời | Context của người dùng A không xuất hiện trong lời gọi của người dùng B. |
| Truy cập trái quyền | Service từ chối tài nguyên không thuộc người dùng/tenant. |
| Bean có AOP proxy | Transaction/security advice vẫn được áp dụng khi callback gọi method. |
| Lỗi service hoặc serialize | Lỗi được phân loại, không rò rỉ thông tin nội bộ. |
| Native/AOT | Callback hoạt động trong executable sau khi metadata reflection được cấu hình. |

Nên có unit test cho phương thức và helper đọc context, integration test tạo callback thật với bean Spring, cùng kiểm thử hội thoại để xác minh schema và việc truyền context. Nếu kiểm tra lựa chọn công cụ bằng model thật, ghi nhận tool call và đối số thay vì chỉ so sánh câu trả lời cuối.

## Bài tập thực hành

Tạo callback cho chức năng tra cứu đơn hàng:

1. Viết bean `OrderTools` có phương thức `getOrderStatus(String orderId, ToolContext toolContext)`.
2. Chọn `Method` bằng tên và kiểu tham số cụ thể.
3. Tạo `ToolDefinition` có tên, mô tả và schema chỉ chứa `orderId`.
4. Dùng `MethodToolCallback.builder()` để ghép định nghĩa, method và bean đích.
5. Tạo context từ người dùng đã xác thực và truyền context theo API `ChatClient` của phiên bản dự án.
6. Trong service, kiểm tra quyền trên `orderId` theo `userId` và `tenantId` từ context.
7. Thử context thiếu, sai kiểu, truy cập chéo tenant và hai request đồng thời.
8. Nếu ứng dụng dùng proxy hoặc native image, kiểm tra callback trong đúng môi trường triển khai đó.

Bạn hoàn thành khi mô hình chỉ có thể tạo `orderId`, ứng dụng tự cung cấp danh tính/tenant, callback gọi đúng Spring bean và service từ chối mọi truy cập không hợp lệ.

## Danh sách kiểm tra

- [ ] `Method` được chọn bằng chữ ký cụ thể, không nhập nhằng giữa các overload.
- [ ] Đối tượng đích là bean Spring tương thích với method.
- [ ] `ToolDefinition` có tên, mô tả và schema khớp tham số JSON của phương thức.
- [ ] `ToolContext` được nhận riêng, không xuất hiện như trường JSON mà mô hình phải tạo.
- [ ] Context được tạo theo request từ nguồn đáng tin cậy và không dùng chung mutable state.
- [ ] Phương thức kiểm tra dữ liệu context thiếu hoặc sai kiểu.
- [ ] Service kiểm tra quyền trên tài nguyên theo người dùng và tenant.
- [ ] Lỗi reflection, mapping, context, thực thi và serialize được xử lý có kiểm soát.
- [ ] Proxy/AOP được kiểm tra để bảo đảm interceptor vẫn chạy.
- [ ] AOT/native image có đủ reflection metadata và đã được kiểm thử nếu dự án sử dụng.

`MethodToolCallback` giúp tái sử dụng phương thức Java như một công cụ có hợp đồng rõ ràng. `ToolContext` bổ sung dữ liệu theo từng yêu cầu mà không trao quyền tạo dữ liệu đó cho mô hình. Khi chọn đúng method, bean đích và schema, đồng thời xác thực context trong service, ứng dụng có thể kết nối mô hình với nghiệp vụ mà vẫn giữ quyền kiểm soát thực thi.
