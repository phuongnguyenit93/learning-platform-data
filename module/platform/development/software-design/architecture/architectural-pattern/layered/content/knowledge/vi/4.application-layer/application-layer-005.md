# Quản lý ngữ cảnh người dùng, quyền thao tác và tham số ca sử dụng

Tầng ứng dụng điều phối một ca sử dụng: xác định ai đang yêu cầu thực hiện, kiểm tra người đó có được phép thực hiện hành động trong phạm vi dữ liệu liên quan hay không, nhận các tham số cần thiết, gọi quy tắc nghiệp vụ và lưu kết quả. Nếu các thông tin này bị trộn lẫn hoặc lấy từ nguồn không đáng tin cậy, hệ thống có thể cho phép người dùng thao tác trên dữ liệu của người khác, áp dụng sai quyền hoặc khiến ca sử dụng phụ thuộc chặt vào HTTP và framework bảo mật.

Bài học này thuộc module `SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED`, tập trung vào tổ chức phần mềm theo kiến trúc phân tầng. Trong chương **Tầng ứng dụng**, ta tìm hiểu cách tầng ứng dụng quản lý ngữ cảnh người dùng, quyền thao tác và tham số của ca sử dụng qua ví dụ thay đổi địa chỉ giao hàng của một đơn hàng trong Java/Spring.

## Phân biệt danh tính, quyền và dữ liệu đầu vào

Ba nhóm thông tin có liên quan nhưng không nên bị xem là một:

| Nhóm thông tin | Ý nghĩa | Ví dụ |
|---|---|---|
| Ngữ cảnh người dùng (actor context) | Ai đang thực hiện yêu cầu và họ đang hoạt động trong phạm vi nào | `userId`, `tenantId`, các quyền đã được xác thực |
| Quyền thao tác (authorization) | Người đó có được thực hiện hành động cụ thể trên chức năng hoặc tài nguyên này không | Được phép đổi địa chỉ đơn hàng; được quản lý mọi đơn hàng trong cửa hàng |
| Tham số ca sử dụng (use-case input) | Dữ liệu mà người dùng muốn dùng để thực hiện hành động | `orderId`, địa chỉ mới, phiên bản đơn hàng mong đợi |

Ví dụ, người dùng gửi yêu cầu đổi địa chỉ đơn hàng `A123`. `orderId` là tham số để xác định tài nguyên mục tiêu. Danh tính người gửi phải đến từ phiên đăng nhập hoặc thông tin xác thực đã được máy chủ kiểm chứng. Quyền đổi địa chỉ được đánh giá dựa trên danh tính, quyền hạn và chính đơn hàng đó. Không được coi `userId`, `tenantId` hay `role` do client tự gửi trong JSON là bằng chứng về danh tính hoặc quyền.

### Xác thực và phân quyền

**Xác thực (authentication)** trả lời câu hỏi “người gọi là ai?”. Ví dụ, Spring Security xác minh token hoặc phiên đăng nhập và tạo ra đối tượng `Authentication` đã được xác thực.

**Phân quyền (authorization)** trả lời câu hỏi “người gọi được làm gì?”. Việc này có thể dựa trên authority, vai trò, quan hệ sở hữu, trạng thái tài nguyên, phạm vi tenant hoặc chính sách của tổ chức. Đăng nhập thành công không đồng nghĩa người dùng được phép thực hiện mọi thao tác.

Vai trò (role) thường là cách gom nhóm quyền. Chẳng hạn vai trò `ORDER_MANAGER` có thể được ánh xạ thành các quyền `ORDER_READ`, `ORDER_CANCEL` và `ORDER_ADDRESS_CHANGE`. Trong mã ca sử dụng, kiểm tra một quyền cụ thể thường diễn đạt ý định rõ hơn việc kiểm tra tên vai trò chung.

## Ngữ cảnh người dùng trong tầng ứng dụng

Ngữ cảnh người dùng là tập thông tin tối thiểu để ca sử dụng biết ai đang hành động và giới hạn dữ liệu cần truy cập. Một kiểu dữ liệu bất biến có thể được định nghĩa như sau:

```java
public record ActorContext(
        UUID userId,
        UUID tenantId,
        Set<String> authorities) {

    public ActorContext {
        Objects.requireNonNull(userId, "userId");
        Objects.requireNonNull(tenantId, "tenantId");
        authorities = Set.copyOf(authorities);
    }

    public boolean hasAuthority(String authority) {
        return authorities.contains(authority);
    }
}
```

`userId` xác định người đang thao tác; `tenantId` xác định tổ chức hoặc không gian dữ liệu mà người dùng đang hoạt động; `authorities` chứa các quyền đã được xác thực và chuẩn hóa. `Set.copyOf` tạo bản sao không thể sửa đổi để mã xử lý không vô tình thay đổi tập quyền trong lúc thực thi.

Đây là ví dụ về ngữ cảnh phù hợp với một ứng dụng nhiều tenant. Ứng dụng đơn tenant có thể không cần `tenantId`. Một hệ thống khác có thể cần thêm mã chi nhánh hoặc phạm vi dự án. Chỉ đưa vào ngữ cảnh những giá trị có ý nghĩa xuyên suốt ca sử dụng; không biến nó thành một túi chứa mọi header, cookie, thông tin HTTP, locale, địa chỉ IP và dữ liệu tùy ý.

Ngữ cảnh nên được tạo từ danh tính đã xác thực ở biên ứng dụng. Ví dụ controller nhận một principal do Spring Security cung cấp rồi ánh xạ sang kiểu dữ liệu của ứng dụng:

```java
@RestController
class OrderController {
    private final ChangeDeliveryAddressService changeAddress;

    OrderController(ChangeDeliveryAddressService changeAddress) {
        this.changeAddress = changeAddress;
    }

    @PutMapping("/orders/{orderId}/delivery-address")
    ResponseEntity<Void> changeAddress(
            @PathVariable UUID orderId,
            @Valid @RequestBody ChangeAddressRequest request,
            @AuthenticationPrincipal UserPrincipal principal) {

        ActorContext actor = new ActorContext(
            principal.userId(),
            principal.tenantId(),
            principal.authorities()
        );

        ChangeDeliveryAddressCommand command =
            new ChangeDeliveryAddressCommand(
                orderId,
                request.street(),
                request.city(),
                request.expectedVersion()
            );

        changeAddress.handle(actor, command);
        return ResponseEntity.noContent().build();
    }
}
```

`UserPrincipal` ở đây là kiểu principal do ứng dụng định nghĩa và chỉ được tạo sau khi cơ chế xác thực kiểm chứng thông tin đăng nhập. Tên lớp và cách ánh xạ có thể khác theo cấu hình Spring Security. Controller làm nhiệm vụ chuyển đổi từ giao thức và principal sang ngữ cảnh cùng lệnh của ứng dụng. Application service không cần nhận `HttpServletRequest`, cookie hay token thô.

Trong một thiết kế khác, application service có thể gọi một cổng như `CurrentActorProvider` để lấy ngữ cảnh hiện tại. Cách đó hữu ích khi không muốn truyền `ActorContext` qua nhiều lời gọi, nhưng cần tránh biến provider thành global state khó kiểm thử. Dù chọn cách nào, phụ thuộc vào Spring Security nên được giữ ở adapter hoặc biên phù hợp, còn ca sử dụng cần một hợp đồng rõ ràng để biết actor là ai.

## Tham số ca sử dụng phải diễn đạt hành động

Tham số ca sử dụng mô tả dữ liệu cần thiết để thực hiện một hành động cụ thể. Có thể gom chúng vào một command thay vì truyền một danh sách dài các tham số rời rạc:

```java
public record ChangeDeliveryAddressCommand(
        UUID orderId,
        String street,
        String city,
        long expectedVersion) {
}
```

Command chứa mã đơn hàng, địa chỉ mới và phiên bản mà client đã đọc trước đó. `expectedVersion` có thể được dùng để phát hiện cập nhật đồng thời, tránh ghi đè thay đổi mới hơn mà người dùng chưa nhìn thấy. Các trường bắt buộc, độ dài chuỗi và định dạng cơ bản nên được kiểm tra ở biên bằng Bean Validation hoặc bộ kiểm tra tương đương.

Ngữ cảnh và command có mục đích khác nhau. `ActorContext` mô tả người đang hành động; command mô tả hành động và dữ liệu được yêu cầu. Không nên thêm `userId` vào command chỉ vì client có thể gửi nó. Cũng không nên để client tự chọn `tenantId` hoặc danh sách quyền. Nếu ca sử dụng cần một đối tượng đích khác với actor, ví dụ quản trị viên cập nhật hồ sơ nhân viên, command có thể chứa `employeeId`; quyền truy cập đối tượng đó vẫn phải được kiểm tra dựa trên actor đã xác thực.

## Kiểm tra quyền ở đúng phạm vi

Phân quyền thường cần nhiều lớp kiểm tra bổ sung cho nhau:

1. **Quyền chức năng:** người dùng có quyền thực hiện hành động này không, ví dụ `ORDER_ADDRESS_CHANGE`.
2. **Phạm vi dữ liệu:** tài nguyên có thuộc tenant hoặc phạm vi mà người dùng được phép truy cập không.
3. **Quyền trên tài nguyên cụ thể:** người dùng có phải chủ đơn hàng, người phụ trách, hoặc người có quyền quản lý đơn hàng đó không.
4. **Quy tắc nghiệp vụ:** trạng thái hiện tại có cho phép thay đổi địa chỉ không, ví dụ đơn hàng đã giao không còn được sửa địa chỉ.

Các kiểm tra này giải quyết những câu hỏi khác nhau. Người dùng có quyền đổi địa chỉ nói chung vẫn không được sửa đơn hàng của tenant khác. Chủ đơn hàng vẫn không thể sửa địa chỉ sau khi đơn đã giao nếu quy tắc nghiệp vụ cấm thao tác đó.

Ví dụ application service điều phối các bước:

```java
@Service
class ChangeDeliveryAddressService {
    private final OrderRepository orders;

    ChangeDeliveryAddressService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public void handle(
            ActorContext actor,
            ChangeDeliveryAddressCommand command) {

        if (actor == null) {
            throw new UnauthenticatedException();
        }

        if (!actor.hasAuthority("ORDER_ADDRESS_CHANGE")) {
            throw new ForbiddenOperationException();
        }

        Order order = orders
            .findByIdAndTenantId(command.orderId(), actor.tenantId())
            .orElseThrow(OrderNotFoundException::new);

        boolean isOwner = order.isOwnedBy(actor.userId());
        boolean canManageAll = actor.hasAuthority("ORDER_MANAGE_ALL");
        if (!isOwner && !canManageAll) {
            throw new ForbiddenOperationException();
        }

        order.changeDeliveryAddress(
            new Address(command.street(), command.city()),
            command.expectedVersion()
        );
        orders.save(order);
    }
}
```

Ví dụ giả định repository có phương thức truy vấn theo cả mã đơn và tenant. Điều kiện tenant được đưa vào truy vấn để giới hạn dữ liệu ngay tại nơi tải tài nguyên. Khi không tìm thấy đơn hàng trong tenant hiện tại, ứng dụng có thể trả về lỗi không tìm thấy. Với một số hệ thống, cách phản hồi này còn giúp tránh tiết lộ rằng tài nguyên của tenant khác có tồn tại.

`isOwnedBy` kiểm tra quan hệ giữa actor và đơn hàng; `ORDER_MANAGE_ALL` là quyền quản lý vượt qua điều kiện sở hữu trong phạm vi tenant. Sau khi quyền truy cập được xác nhận, `order.changeDeliveryAddress` vẫn phải tự bảo vệ bất biến của đơn hàng, chẳng hạn từ chối khi đơn đã giao. Application service điều phối quyền và luồng công việc; domain object bảo vệ trạng thái hợp lệ của chính nó.

Không phải dự án nào cũng cần tách riêng một policy class. Khi quy tắc truy cập đơn giản, kiểm tra có thể nằm trong application service. Khi chính sách phức tạp hoặc được dùng ở nhiều ca sử dụng, có thể tách thành `OrderAccessPolicy` hoặc một abstraction phù hợp. Điều quan trọng là mọi đường gọi tới ca sử dụng đều đi qua kiểm tra cần thiết, kể cả lời gọi từ tác vụ nền hoặc một giao diện khác.

## Vị trí của các kiểm tra trong Spring

Spring Security cung cấp nhiều cách áp dụng quyền. Ví dụ, `@PreAuthorize("hasAuthority('ORDER_ADDRESS_CHANGE')")` có thể chặn một ca sử dụng khi actor thiếu quyền chức năng. Đây là lớp bảo vệ hữu ích và giúp biểu đạt chính sách ở điểm gọi. Tuy nhiên, kiểm tra này không tự xác minh người dùng có sở hữu đơn hàng cụ thể hay đơn hàng có thuộc tenant hiện tại hay không. Những điều kiện phụ thuộc tài nguyên cần được kiểm tra sau khi tải tài nguyên trong phạm vi thích hợp.

Một số dự án dùng `@PreAuthorize` ở controller, một số đặt ở application service, và một số kết hợp với kiểm tra tường minh trong ca sử dụng. Chọn vị trí sao cho mọi điểm gọi được bảo vệ nhất quán. Không nên chỉ dựa vào việc nút giao diện bị ẩn hoặc nút bấm bị vô hiệu hóa; client có thể tự tạo HTTP request.

Các lỗi thường gặp nên có ý nghĩa nhất quán:

- Chưa xác thực: thường ánh xạ thành HTTP `401 Unauthorized`.
- Đã xác thực nhưng thiếu quyền: thường ánh xạ thành `403 Forbidden`.
- Không tìm thấy tài nguyên trong phạm vi truy cập: thường ánh xạ thành `404 Not Found`.
- Dữ liệu đầu vào không hợp lệ: thường ánh xạ thành `400 Bad Request`.
- Xung đột phiên bản hoặc trạng thái: có thể ánh xạ thành `409 Conflict` tùy hợp đồng API.

Mã HTTP là quyết định của adapter giao diện. Application layer có thể ném các lỗi có ý nghĩa như `OrderNotFoundException` hoặc `ForbiddenOperationException`; controller advice hoặc bộ xử lý ngoại lệ chuyển chúng thành phản hồi phù hợp.

## Không để ngữ cảnh trở thành global state

Trong ứng dụng web đồng bộ, Spring Security thường lưu `SecurityContext` theo luồng thực thi. Cách lưu này thuận tiện cho adapter web, nhưng không có nghĩa mọi lớp nên tự gọi `SecurityContextHolder` ở bất cứ đâu. Việc đọc ngữ cảnh ẩn làm cho chữ ký ca sử dụng không thể hiện đầy đủ đầu vào, gây khó khăn khi unit test và dễ phát sinh lỗi khi chuyển công việc sang luồng khác.

Với xử lý bất đồng bộ hoặc tác vụ nền, không nên giả định ngữ cảnh của request ban đầu tự động có mặt. Nếu cần tiếp tục một hành động dưới danh nghĩa người khởi tạo, hãy truyền một bản ghi công việc có actor và tenant đã được xác minh, ghi audit phù hợp và đánh giá lại quyền tại thời điểm thực thi theo chính sách hệ thống. Với công việc chạy bằng tài khoản dịch vụ, hãy biểu đạt rõ danh tính dịch vụ và quyền hạn riêng; không giả làm người dùng cuối.

Thông tin kỹ thuật như correlation ID có thể được truyền qua logging/tracing context. Locale hoặc múi giờ chỉ nên trở thành tham số ca sử dụng khi chúng thực sự ảnh hưởng đến kết quả nghiệp vụ. Việc phân biệt các loại ngữ cảnh giúp `ActorContext` không biến thành một đối tượng chứa mọi thứ.

## Kiểm thử ngữ cảnh và quyền thao tác

Nên kiểm tra cả trường hợp được phép và bị từ chối, đặc biệt ở ranh giới tenant và quyền trên tài nguyên:

| Tình huống | Kết quả cần xác nhận |
|---|---|
| Không có actor đã xác thực | Ca sử dụng từ chối yêu cầu |
| Actor thiếu `ORDER_ADDRESS_CHANGE` | Không tải hoặc thay đổi đơn hàng; trả lỗi phân quyền phù hợp |
| Actor có quyền chức năng nhưng đơn thuộc tenant khác | Repository không trả đơn hàng ngoài tenant; không tiết lộ dữ liệu đó |
| Actor cùng tenant nhưng không phải chủ đơn và không có quyền quản lý | Từ chối thao tác trên tài nguyên cụ thể |
| Actor là chủ đơn hoặc có quyền quản lý phù hợp | Ca sử dụng tiếp tục và lưu thay đổi hợp lệ |
| Đơn hàng đã giao | Domain từ chối thay đổi theo bất biến nghiệp vụ |
| Phiên bản đơn hàng đã cũ | Phát hiện xung đột thay vì âm thầm ghi đè |
| Client gửi `userId`, `tenantId` hoặc role giả trong body | Giá trị giả không ảnh hưởng đến actor context hoặc quyết định quyền |

Unit test application service có thể dùng repository giả để xác nhận các nhánh phân quyền và thứ tự điều phối. Test tích hợp cần xác nhận truy vấn tenant thực sự giới hạn dữ liệu. Test web với Spring Security có thể xác minh token hoặc principal được ánh xạ đúng và lỗi được chuyển thành mã HTTP đúng. Chỉ kiểm thử trường hợp thành công sẽ bỏ sót nhiều lỗi phân quyền nghiêm trọng.

## Cân bằng giữa bảo mật và độ phức tạp

Đưa actor và command thành các kiểu dữ liệu rõ ràng giúp ca sử dụng dễ đọc, dễ kiểm thử và có thể được gọi từ REST API, giao diện quản trị hoặc tác vụ nền. Đổi lại, cần định nghĩa và ánh xạ thêm một số kiểu dữ liệu. Với ứng dụng rất nhỏ, có thể bắt đầu bằng một context gọn và command đơn giản; chỉ mở rộng khi xuất hiện tenant, nhiều nhóm quyền hoặc quy tắc truy cập tài nguyên thực sự cần thiết.

Không nên gom mọi quyết định vào controller, cũng không nên biến application service thành một hệ thống phân quyền khổng lồ. Controller chuyển đổi thông tin xác thực thành ngữ cảnh ứng dụng; application service điều phối ca sử dụng và kiểm tra quyền phù hợp; domain bảo vệ bất biến nghiệp vụ; repository giới hạn việc đọc ghi theo phạm vi dữ liệu. Vai trò chính xác của từng thành phần có thể thay đổi theo mô hình, nhưng nguồn danh tính phải đáng tin cậy và mọi thao tác trên tài nguyên đều cần được kiểm tra ở phía máy chủ.
