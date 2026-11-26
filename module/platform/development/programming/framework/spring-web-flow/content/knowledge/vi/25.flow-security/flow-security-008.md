# Kiểm tra quyền sở hữu đối tượng từ flow input

Spring Web Flow thường nhận dữ liệu đầu vào để xác định đối tượng mà người dùng muốn thao tác. Ví dụ, một URL có thể mở flow chỉnh sửa đơn hàng theo **orderId**, hoặc flow có thể nhận **documentId** từ flow cha khi gọi subflow. Những giá trị này giúp flow biết cần tải đối tượng nào, nhưng chúng không chứng minh người gửi request có quyền truy cập đối tượng đó.

Nếu ứng dụng chỉ tải bản ghi theo ID rồi hiển thị hoặc cập nhật, người dùng có thể thay ID trong URL, form hoặc request để truy cập dữ liệu của người khác. Đây là lỗi kiểm soát truy cập ở cấp đối tượng, thường được gọi là IDOR (Insecure Direct Object Reference). Cách bảo vệ đúng là xác định danh tính từ ngữ cảnh xác thực phía server, sau đó kiểm tra quyền đối với chính đối tượng được yêu cầu ở tầng nghiệp vụ.

Bài học thuộc chương **Bảo vệ flow** của module **Spring Web Flow**. Module này hướng dẫn mô hình hóa hành trình web nhiều bước bằng state, event, transition và subflow; thực hành form binding, validation, quản lý scope và phiên, tích hợp Spring MVC, kiểm thử và phục hồi luồng khi gặp lỗi.

## 1. Flow input là dữ liệu không đáng tin cậy

Flow input là dữ liệu được truyền vào khi khởi chạy flow hoặc được ánh xạ từ flow cha sang subflow. Một flow có thể nhận ID đơn hàng, ID hồ sơ, mã dự án hoặc một tham số xác định tài nguyên cần xử lý.

Ví dụ:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      id="editOrder">

    <input name="orderId" type="java.lang.Long" />

    <on-start>
        <evaluate expression="orderAccessService.loadOwnedOrder(flowScope.orderId)"
                  result="flowScope.order" />
    </on-start>

    <view-state id="review" view="order/review">
        <transition on="confirm" to="complete" />
        <transition on="cancel" to="cancelled" />
    </view-state>
</flow>
~~~

Ví dụ khai báo một flow input có tên orderId, chuyển đổi thành kiểu Long, rồi dùng service tải đơn hàng được phép truy cập. Cú pháp và cách ánh xạ input cần được đối chiếu với phiên bản Spring Web Flow của ứng dụng; điểm bảo mật không phụ thuộc vào nguồn truyền input: ID vẫn là dữ liệu do request hoặc flow khác cung cấp.

Flow input có thể đến từ:

- Tham số trên URL hoặc request khởi chạy flow.
- Dữ liệu được truyền vào khi flow cha gọi subflow.
- Một biểu mẫu hoặc event trong hành trình.
- Một liên kết được tạo từ giao diện.
- Một hệ thống tích hợp gọi endpoint khởi chạy flow.

Dù đến từ đâu, giá trị đó có thể bị sửa đổi. Người dùng có thể thay orderId=1001 thành orderId=1002, gửi request thủ công hoặc thay dữ liệu ẩn trong form. Việc giá trị đã được chuyển đổi thành Long, đã qua validation định dạng hoặc nằm trong flowScope không làm nó trở nên đáng tin cậy.

Cần phân biệt:

| Khái niệm | Câu hỏi được trả lời |
|---|---|
| Authentication | Người gửi request là ai? |
| Flow input | Flow được yêu cầu làm việc với dữ liệu hoặc đối tượng nào? |
| Authorization | Danh tính hiện tại có quyền thực hiện hành động trên đối tượng đó không? |
| Validation | Dữ liệu có đúng định dạng và quy tắc nghiệp vụ không? |

Một ID hợp lệ chỉ cho biết định danh có thể được phân tích. Nó không cho biết người dùng có quyền đọc, sửa, duyệt hoặc xóa đối tượng.

## 2. Rủi ro IDOR khi chỉ tải đối tượng theo ID

Giả sử ứng dụng có hai người dùng, An và Bình. An sở hữu đơn hàng 1001, Bình sở hữu đơn hàng 1002. Flow chỉnh sửa đơn hàng nhận orderId rồi gọi repository:

~~~java
Order order = orderRepository.findById(orderId)
        .orElseThrow(() -> new OrderNotFoundException(orderId));
~~~

Nếu flow chỉ kiểm tra bản ghi có tồn tại, Bình có thể gửi URL của đơn hàng 1001 và xem hoặc sửa dữ liệu của An. Màn hình có thể không hiển thị liên kết đến đơn hàng đó, nhưng người dùng vẫn có thể tự tạo request.

Đây là lỗi IDOR vì ứng dụng dùng một tham chiếu đối tượng do client kiểm soát mà không xác minh quyền trên đối tượng đích.

Các nguồn ID thường bị bỏ sót:

- ID trên URL khởi chạy flow.
- ID nằm trong hidden input.
- ID được gửi trong JSON hoặc form POST.
- ID nằm trong tham số của event.
- ID được flow cha truyền vào subflow.
- ID được lưu trong flowScope từ một request trước.
- ID được lấy từ một đường dẫn hoặc tên file do client cung cấp.

Không nên dựa vào việc ID khó đoán. ID tuần tự, UUID hoặc mã phức tạp đều không thay thế kiểm tra quyền. Một người dùng có thể nhận ID từ email, log, liên kết được chia sẻ hoặc một lỗi rò rỉ khác.

## 3. Kiểm tra quyền ngay tại service nghiệp vụ

Cách an toàn là kết hợp định danh đối tượng với danh tính đã xác thực khi truy vấn. Thay vì tải mọi bản ghi rồi mới quyết định có được truy cập hay không, hãy ưu tiên truy vấn có điều kiện quyền sở hữu.

Ví dụ repository:

~~~java
public interface OrderRepository extends JpaRepository<Order, Long> {

    Optional<Order> findByIdAndOwnerId(Long id, String ownerId);
}
~~~

Service lấy danh tính từ ngữ cảnh bảo mật phía server:

~~~java
@Service
public class OrderAccessService {

    private final OrderRepository orderRepository;

    public OrderAccessService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    public Order loadOwnedOrder(Long orderId) {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            throw new AccessDeniedException("Authentication is required");
        }

        String currentUserId = authentication.getName();

        return orderRepository.findByIdAndOwnerId(orderId, currentUserId)
                .orElseThrow(() -> new OrderNotFoundException());
    }
}
~~~

Trong ví dụ, currentUserId được lấy từ SecurityContextHolder, không lấy từ tham số ownerId do client gửi. Truy vấn chỉ trả về đơn hàng có ID phù hợp và thuộc người dùng hiện tại. Khi không tìm thấy bản ghi thỏa cả hai điều kiện, service trả về lỗi không tìm thấy.

Trong hệ thống thực tế, authentication.getName() có thể là username hoặc subject. Hãy ánh xạ nó sang ID người dùng nội bộ qua một thành phần như CurrentUserProvider. Không giả định username luôn trùng với khóa chính của bảng người dùng.

Nếu quyền truy cập phụ thuộc tenant hoặc tổ chức, điều kiện truy vấn cần bao gồm cả tenant:

~~~java
Optional<Order> findByIdAndTenantIdAndOwnerId(
        Long id,
        Long tenantId,
        String ownerId
);
~~~

Đối với ACL hoặc thành viên dự án, service cần kiểm tra quan hệ cấp quyền tương ứng. Quyền sở hữu chỉ là một dạng authorization; người dùng có thể được cấp quyền qua vai trò, nhóm, tổ chức hoặc chia sẻ cụ thể.

Ưu tiên kiểm tra quyền ở service vì cùng một nghiệp vụ có thể được gọi từ nhiều flow, controller, API hoặc tác vụ nền. Nếu chỉ kiểm tra ở view-state, một đường gọi khác có thể bỏ qua quy tắc đó.

## 4. Tải đối tượng an toàn trong flow

Flow nên gọi service có kiểm tra quyền ngay khi nhận input và trước khi đưa dữ liệu đối tượng vào scope hoặc render view.

Ví dụ:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      id="editOrder">

    <input name="orderId" type="java.lang.Long" />

    <on-start>
        <evaluate expression="orderAccessService.loadOwnedOrder(flowScope.orderId)"
                  result="flowScope.order" />
    </on-start>

    <view-state id="review" view="order/review">
        <transition on="confirm" to="confirmOrder" />
        <transition on="cancel" to="cancelled" />
    </view-state>

    <action-state id="confirmOrder">
        <evaluate expression="orderCommandService.confirmOwnedOrder(flowScope.orderId)" />
        <transition to="complete" />
    </action-state>

    <end-state id="complete" view="order/complete" />
    <end-state id="cancelled" view="order/cancelled" />
</flow>
~~~

Ở đây, on-start chỉ tải đối tượng sau khi service kiểm tra quyền. Nếu người dùng không sở hữu đơn hàng hoặc không được cấp quyền, service từ chối trước khi view nhận dữ liệu.

Tuy nhiên, kiểm tra lúc khởi chạy chưa đủ cho toàn bộ vòng đời flow. Quyền có thể thay đổi trong lúc người dùng đi qua các bước: đơn hàng được chuyển chủ sở hữu, thành viên bị xóa khỏi dự án, vai trò bị thu hồi hoặc tài khoản bị khóa. Vì vậy, thao tác đọc nhạy cảm và mọi thao tác thay đổi dữ liệu đều cần được bảo vệ tại service tương ứng.

## 5. Kiểm tra lại quyền trước thao tác ghi

Một flow nhiều bước có thể giữ đối tượng trong flowScope qua nhiều request. Nếu service chỉ kiểm tra quyền khi tải ban đầu, người dùng có thể tiếp tục một execution cũ sau khi quyền đã bị thu hồi.

Không nên dùng trực tiếp đối tượng đã lưu trong scope làm bằng chứng rằng người dùng vẫn được phép cập nhật. Khi xác nhận, hãy tải lại đối tượng theo danh tính hiện tại và kiểm tra quyền một lần nữa:

~~~java
@Service
public class OrderCommandService {

    private final OrderRepository orderRepository;
    private final CurrentUserProvider currentUserProvider;

    public OrderCommandService(
            OrderRepository orderRepository,
            CurrentUserProvider currentUserProvider) {
        this.orderRepository = orderRepository;
        this.currentUserProvider = currentUserProvider;
    }

    @Transactional
    public void confirmOwnedOrder(Long orderId) {
        String currentUserId = currentUserProvider.requireUserId();

        Order order = orderRepository.findByIdAndOwnerId(orderId, currentUserId)
                .orElseThrow(() -> new OrderNotFoundException());

        if (order.getStatus() != OrderStatus.PENDING) {
            throw new InvalidOrderStateException();
        }

        order.confirm();
    }
}
~~~

Service xác minh lại chủ sở hữu trong cùng luồng nghiệp vụ cập nhật. Nó cũng kiểm tra trạng thái hiện tại để tránh xác nhận một đơn hàng đã hoàn tất hoặc bị hủy.

Với hệ thống có thay đổi quyền đồng thời, cần cân nhắc transaction isolation, optimistic locking hoặc cơ chế khóa phù hợp. Kiểm tra quyền rồi cập nhật ở hai thời điểm tách biệt có thể tạo ra race condition nếu quan hệ quyền thay đổi giữa hai thao tác. Đưa điều kiện quyền vào truy vấn cập nhật hoặc dùng transaction và version check giúp thu hẹp khoảng thời gian này.

Không nên coi flowScope.order là bản ghi mới nhất trong database. Nó là dữ liệu execution đang giữ, có thể đã cũ so với trạng thái nghiệp vụ hiện tại.

## 6. Không nhận ownerId hoặc tenantId từ client làm căn cứ quyền

Một lỗi phổ biến là gửi cả ID đối tượng và ID người sở hữu:

~~~text
orderId=1001
ownerId=user-42
~~~

Sau đó truy vấn:

~~~java
orderRepository.findByIdAndOwnerId(orderId, ownerId);
~~~

Cách này không an toàn nếu ownerId đến từ request. Người dùng có thể thay cả hai giá trị để khớp với một bản ghi khác.

Danh tính và phạm vi quyền phải lấy từ ngữ cảnh server đã xác thực:

- User ID lấy từ principal hoặc dịch vụ ánh xạ danh tính.
- Tenant ID lấy từ security context hoặc tenant context đã được xác minh.
- Vai trò và quyền lấy từ authority/ACL được quản lý phía server.
- ID đối tượng có thể đến từ flow input, nhưng chỉ dùng để chỉ định tài nguyên cần kiểm tra.

Nếu ứng dụng có chức năng quản trị viên truy cập đối tượng của người khác, hãy mô hình hóa đó thành một quyền riêng có kiểm soát. Không dùng một ownerId do client gửi để ngầm mở rộng quyền.

## 7. Kiểm soát dữ liệu form và mass assignment

Kiểm tra quyền sở hữu đối tượng không giải quyết hết rủi ro khi binding form. Một form có thể gửi thêm thuộc tính mà giao diện không hiển thị, chẳng hạn ownerId, tenantId, approved, role hoặc status.

Nếu binder cập nhật trực tiếp entity, người dùng có thể thử sửa các trường nhạy cảm bằng request thủ công. Hãy dùng command object/DTO chỉ chứa những trường được phép chỉnh sửa và cấu hình binder theo allowlist khi phù hợp.

Ví dụ command:

~~~java
public class UpdateOrderCommand {

    private String deliveryNote;
    private String contactPhone;

    // getters and setters
}
~~~

Service tải đơn hàng theo quyền sở hữu rồi chỉ áp dụng các trường được phép:

~~~java
@Transactional
public void updateOwnedOrder(Long orderId, UpdateOrderCommand command) {
    String userId = currentUserProvider.requireUserId();

    Order order = orderRepository.findByIdAndOwnerId(orderId, userId)
            .orElseThrow(() -> new OrderNotFoundException());

    order.updateDeliveryDetails(
            command.getDeliveryNote(),
            command.getContactPhone()
    );
}
~~~

Các thuộc tính như ownerId, tenantId, createdBy, approved hoặc trạng thái thanh toán không nên được binding trực tiếp từ form thông thường. Những thay đổi đặc quyền phải đi qua use case riêng với kiểm tra vai trò và quy tắc nghiệp vụ.

## 8. Quyền sở hữu khi gọi subflow

Subflow có thể nhận ID đối tượng từ flow cha. Việc flow cha đã tải hoặc kiểm tra một đối tượng không có nghĩa subflow được miễn kiểm tra quyền.

Ví dụ flow cha truyền ID đơn hàng:

~~~xml
<subflow-state id="editDelivery"
               subflow="delivery/edit">
    <input name="orderId" value="flowScope.orderId" />
    <transition on="updated" to="review" />
    <transition on="cancelled" to="review" />
</subflow-state>
~~~

Subflow khai báo input và tự tải đối tượng qua service:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      id="delivery/edit">

    <input name="orderId" type="java.lang.Long" />

    <on-start>
        <evaluate expression="orderAccessService.loadOwnedOrder(flowScope.orderId)"
                  result="flowScope.order" />
    </on-start>

    <view-state id="deliveryDetails" view="delivery/edit">
        <transition on="save" to="saveDelivery" />
    </view-state>
</flow>
~~~

Đây là ví dụ minh họa việc truyền input và kiểm tra tại ranh giới subflow. Tên flow, cách ánh xạ input/output và biểu thức scope cần khớp với flow definition của ứng dụng.

Subflow cần coi input như dữ liệu không đáng tin cậy, kể cả khi input đến từ flow cha. Cách này bảo vệ subflow khi sau này được gọi từ một flow khác hoặc được tái sử dụng trong một hành trình có chính sách quyền khác.

Nếu subflow chỉ thực hiện một phần nghiệp vụ, service của subflow vẫn phải kiểm tra quyền trên đối tượng và hành động cụ thể. Không truyền cả entity đã tải từ flow cha nếu chỉ cần ID và một số giá trị đầu vào tối thiểu.

## 9. Phản hồi khi người dùng không có quyền

Khi ID không tồn tại, không thuộc người dùng hoặc người dùng không có quyền, ứng dụng cần phản hồi an toàn và nhất quán.

Một số nguyên tắc:

- Không render dữ liệu đối tượng trước khi kiểm tra quyền.
- Không tiết lộ tên chủ sở hữu, tenant hoặc thông tin cho biết bản ghi có tồn tại nhưng thuộc người khác.
- Có thể dùng phản hồi 404 thống nhất cho cả trường hợp không tồn tại và không được phép xem, tùy chính sách sản phẩm.
- Với người dùng chưa xác thực, yêu cầu đăng nhập hoặc trả về 401 theo cơ chế ứng dụng.
- Với người dùng đã xác thực nhưng không có quyền, xử lý 403 hoặc 404 theo chính sách chống dò tìm tài nguyên.
- Không để stack trace, SQL, ID nội bộ hoặc chi tiết principal xuất hiện trong thông báo lỗi.
- Ghi log bảo mật ở phía server với thông tin đủ điều tra nhưng không ghi payload nhạy cảm.

Có thể định nghĩa một đường lỗi trong flow hoặc xử lý exception tập trung ở tầng web. Dù chọn cách nào, cần tránh việc flow tiếp tục tới state xem lại hoặc xác nhận sau khi service đã từ chối truy cập.

Không nên trả về một đối tượng rỗng giả để tránh lỗi. Cách đó có thể khiến view hoặc action sau đó hoạt động trên trạng thái không hợp lệ và làm lỗi khó phát hiện.

## 10. Kiểm thử quyền sở hữu từ flow input

Kiểm thử cần bao gồm cả đường truy cập hợp lệ và các tình huống người dùng cố thay đổi ID.

| Kịch bản | Kết quả mong đợi |
|---|---|
| Chủ sở hữu mở flow với ID của mình | Được tải đối tượng và đi tới view được phép |
| Người dùng khác gửi ID đó | Bị từ chối; không nhận dữ liệu đối tượng |
| ID không tồn tại | Trả phản hồi không tìm thấy theo chính sách |
| Không có authentication | Không tải đối tượng |
| Client gửi thêm ownerId giả | Giá trị này không ảnh hưởng danh tính dùng để kiểm tra quyền |
| Client thay ID trong URL hoặc form | Service kiểm tra quyền với ID mới và từ chối nếu không thuộc phạm vi |
| Quyền bị thu hồi khi flow đang mở | Action tiếp theo kiểm tra lại và từ chối |
| Subflow nhận ID từ flow cha | Subflow thực hiện kiểm tra quyền của chính nó |
| Form gửi thêm trường ownerId hoặc approved | Các trường ngoài allowlist không thể thay đổi dữ liệu |
| Hai request cập nhật đồng thời | Version/transaction và quy tắc nghiệp vụ ngăn cập nhật sai hoặc trùng |

Một unit test cho service có thể kiểm tra truy vấn chỉ trả về đối tượng thuộc người dùng hiện tại:

~~~java
@Test
void rejectsOrderOwnedByAnotherUser() {
    when(currentUserProvider.requireUserId()).thenReturn("user-10");
    when(orderRepository.findByIdAndOwnerId(1001L, "user-10"))
            .thenReturn(Optional.empty());

    assertThrows(
        OrderNotFoundException.class,
        () -> orderAccessService.loadOwnedOrder(1001L)
    );
}
~~~

Ngoài unit test, cần có flow integration test gửi request thực tế tới URL khởi chạy flow, thay đổi input ID và xác nhận flow không render dữ liệu trái quyền. Kiểm thử subflow riêng cũng quan trọng vì flow cha có thể đã được bảo vệ nhưng subflow vẫn có đường gọi khác.

Đừng chỉ kiểm thử bằng cách ẩn liên kết trên giao diện. Hãy gửi request trực tiếp với ID của người dùng khác, sửa hidden field, thử gọi event ở state sâu và tiếp tục execution cũ sau khi quyền đã bị thu hồi.

## 11. Checklist bảo vệ đối tượng từ flow input

Trước khi đưa flow vào sử dụng, hãy rà soát:

- [ ] Xác định mọi flow input có thể chỉ tới đối tượng hoặc tài nguyên nghiệp vụ.
- [ ] Coi ID từ URL, form, event và subflow là dữ liệu không đáng tin cậy.
- [ ] Lấy danh tính người dùng từ security context phía server.
- [ ] Không dùng ownerId hoặc tenantId do client gửi làm căn cứ quyền.
- [ ] Truy vấn đối tượng với điều kiện chủ sở hữu, tenant hoặc ACL.
- [ ] Kiểm tra quyền trước khi render dữ liệu nhạy cảm.
- [ ] Kiểm tra lại quyền trong mọi service thực hiện thao tác ghi.
- [ ] Dùng DTO/command và allowlist cho form binding.
- [ ] Bảo vệ từng subflow tại ranh giới nghiệp vụ của nó.
- [ ] Xử lý 401/403/404 và exception mà không làm lộ thông tin.
- [ ] Kiểm thử IDOR, quyền bị thu hồi, nhiều tab và request đồng thời.
- [ ] Ghi audit log phù hợp cho các thao tác nhạy cảm.

Kiểm tra quyền sở hữu đối tượng từ flow input là một phần của authorization ở cấp tài nguyên. Flow input giúp xác định đối tượng cần xử lý, còn service bảo mật phải xác minh người dùng hiện tại có quyền thực hiện hành động cụ thể trên đối tượng đó. Khi kiểm tra quyền ngay lúc tải, kiểm tra lại trước khi ghi và bảo vệ cả ranh giới subflow, Spring Web Flow có thể chống truy cập chéo dữ liệu ngay cả khi client sửa ID hoặc gửi request ngoài giao diện.
