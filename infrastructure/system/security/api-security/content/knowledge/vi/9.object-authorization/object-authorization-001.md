# Broken Object Level Authorization (BOLA)

Broken Object Level Authorization (BOLA) là lỗi xảy ra khi API cho phép một người gọi truy cập hoặc thao tác trên đối tượng dữ liệu mà người đó không có quyền. Lỗi thường xuất hiện khi endpoint nhận một object ID từ path, query hoặc request body, sau đó tìm bản ghi theo ID nhưng không kiểm tra quan hệ giữa người gọi và bản ghi đó.

Ví dụ, Alice có thể xem đơn hàng `order-100` của mình. Nếu Alice thay ID trong request thành `order-200` thuộc về Bob và API vẫn trả dữ liệu, endpoint đã mắc lỗi BOLA. Alice đã đăng nhập và có quyền gọi chức năng xem đơn hàng, nhưng điều đó không cấp quyền xem mọi đơn hàng trong hệ thống.

Trong thiết kế API Security, cần phân quyền theo từng endpoint, đối tượng dữ liệu và luồng nghiệp vụ. BOLA là một trong những lỗi quan trọng nhất ở ranh giới đối tượng: mỗi request phải kiểm tra người gọi có được phép thực hiện đúng hành động trên đúng bản ghi trong ngữ cảnh hiện tại hay không.

## 1. BOLA là gì và vì sao xảy ra?

API thường dùng định danh để tham chiếu tài nguyên. Định danh có thể là số tăng dần, UUID, mã đơn hàng, slug, tên file, khóa object storage hoặc một ID toàn cục trong GraphQL. Client có thể gửi định danh qua:

- Path parameter, ví dụ `GET /api/orders/{orderId}`.
- Query parameter, ví dụ `GET /api/invoices?customerId=...`.
- Request body, ví dụ `POST /api/orders/{orderId}/cancel` hoặc `PATCH /api/profile`.
- Header, cookie, trường lồng nhau hoặc danh sách ID trong request hàng loạt.
- Tham chiếu gián tiếp như `attachmentId`, `accountId`, `projectId`, `documentKey` hoặc `parentId`.

BOLA xảy ra khi API dựa vào định danh do client cung cấp mà thiếu kiểm tra quyền trên đối tượng tương ứng. Kẻ tấn công không cần phá mật khẩu hay chiếm tài khoản quản trị; một tài khoản hợp lệ với quyền thấp cũng có thể truy cập dữ liệu của người dùng khác nếu endpoint kiểm tra không đầy đủ.

Các nguyên nhân thường gặp:

1. Controller chỉ kiểm tra người dùng đã đăng nhập, sau đó gọi `findById(id)` và trả bản ghi.
2. Hệ thống kiểm tra quyền ở giao diện hoặc gateway nhưng backend không kiểm tra lại trên object.
3. API tin `ownerId`, `tenantId`, `customerId` hoặc role do client gửi lên.
4. Endpoint đọc đã được bảo vệ nhưng endpoint cập nhật, xóa, tải file, export hoặc thao tác hàng loạt bị bỏ sót.
5. Quan hệ giữa các object không được kiểm tra, ví dụ một `invoiceId` có tồn tại nhưng không thuộc `accountId` trong URL.
6. Một đường gọi nội bộ hoặc tác vụ nền bỏ qua chính sách mà endpoint công khai đang áp dụng.

## 2. Phân biệt BOLA với xác thực và các lỗi phân quyền khác

Authentication và authorization giải quyết những câu hỏi khác nhau:

| Kiểm soát | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Authentication | Ai đang gọi API? | Access token hợp lệ đại diện cho Alice. |
| Function-level authorization | Alice có được phép gọi chức năng này không? | Alice có scope `orders:read`. |
| Object-level authorization | Alice có được phép đọc đơn hàng cụ thể này không? | Đơn hàng thuộc Alice hoặc Alice có quyền hỗ trợ phù hợp. |
| Property-level authorization | Alice có được phép xem hoặc sửa từng trường không? | Alice được sửa địa chỉ giao hàng nhưng không được thay `totalPrice` hoặc `ownerId`. |

BOLA tập trung vào quyền trên đối tượng. Nó thường được gọi cùng với IDOR (Insecure Direct Object Reference), vì cả hai thường biểu hiện qua việc thay một tham chiếu đối tượng để truy cập dữ liệu ngoài quyền. Trong thực tế, IDOR mô tả kiểu tham chiếu trực tiếp không an toàn; BOLA nhấn mạnh thiếu kiểm tra authorization ở cấp object trong API.

BOLA cũng khác Broken Function Level Authorization (BFLA). Nếu Alice gọi được endpoint quản trị `DELETE /api/users/{id}` dù không có quyền dùng chức năng quản trị, đó là vấn đề phân quyền chức năng. Nếu Alice được phép xóa một số tài liệu nhưng có thể thay `documentId` để xóa tài liệu của Bob, đó là BOLA. Một request có thể mắc cả hai lỗi nếu hệ thống không kiểm tra cả chức năng lẫn đối tượng.

## 3. Mô hình quyền trên đối tượng

Một quyết định object authorization nên xem xét tối thiểu bốn yếu tố:

- **Subject (chủ thể):** user hoặc client đã được xác thực, tenant, role, permission và quan hệ sở hữu đáng tin cậy.
- **Action (hành động):** đọc, tạo, cập nhật, xóa, chia sẻ, tải xuống, hoàn tiền hoặc chuyển trạng thái.
- **Resource (đối tượng):** bản ghi cụ thể, tenant sở hữu nó, chủ sở hữu, trạng thái và mức độ nhạy cảm.
- **Context (ngữ cảnh):** thời điểm, trạng thái quy trình, quan hệ thành viên, mục đích truy cập hoặc điều kiện nghiệp vụ.

Ví dụ với một đơn hàng:

| Chủ thể | Hành động | Đối tượng | Kết quả minh họa |
| --- | --- | --- | --- |
| Alice | Đọc | Đơn hàng của Alice trong tenant A | Cho phép nếu có quyền `orders:read`. |
| Alice | Đọc | Đơn hàng của Bob trong tenant A | Từ chối nếu Alice không có quyền đọc thay mặt người khác. |
| Alice | Đọc | Đơn hàng trong tenant B | Từ chối do khác tenant. |
| Nhân viên hỗ trợ | Đọc | Đơn hàng trong tenant được phụ trách | Cho phép nếu có permission hỗ trợ và quan hệ phạm vi phù hợp. |
| Alice | Đổi địa chỉ | Đơn hàng đã giao | Từ chối nếu trạng thái nghiệp vụ không cho phép thay đổi. |
| Alice | Đổi chủ sở hữu | Đơn hàng của Alice | Từ chối nếu chức năng chuyển quyền sở hữu không được cấp. |

Không nên dùng một quy tắc đơn giản như “đã đăng nhập thì được đọc” hoặc “có role CUSTOMER thì được truy cập mọi đơn hàng”. Quyết định phải xét object cụ thể và action cụ thể.

### 3.1. Ownership, tenant và quan hệ chia sẻ

Quyền trên object có thể dựa vào quyền sở hữu trực tiếp, membership trong tổ chức, vai trò trên project, quyền được chia sẻ hoặc quan hệ nghiệp vụ. Không phải mọi tài nguyên đều có một `ownerId` duy nhất.

Ví dụ, một tài liệu có thể được chia sẻ với nhóm dự án; thành viên nhóm được đọc nhưng chỉ người tạo hoặc project administrator được xóa. Một hóa đơn có thể thuộc tài khoản doanh nghiệp và chỉ kế toán trong đúng tenant được xem. Chính sách nên mô tả các quan hệ này rõ ràng và kiểm tra chúng từ nguồn dữ liệu tin cậy.

Với hệ thống multi-tenant, tenant isolation là ranh giới cơ bản. Truy vấn object nên được giới hạn theo tenant của principal đã xác thực. Nếu một vai trò được phép truy cập nhiều tenant, phạm vi tenant phải đến từ quyền đã cấp và được xác minh, không phải từ `tenantId` tùy ý trong request.

### 3.2. Quyền phụ thuộc action và trạng thái

Một người có thể được đọc object nhưng không được cập nhật; được cập nhật một số trường nhưng không được xóa; hoặc chỉ được thay đổi khi object đang ở trạng thái nhất định. Vì vậy, kiểm tra object-level cần gắn với hành động và state transition.

Ví dụ, người mua có thể thay địa chỉ khi đơn ở trạng thái `CREATED` hoặc `PROCESSING`, nhưng không được thay sau khi đã `SHIPPED`. Người hỗ trợ có thể xem đơn hàng trong phạm vi phụ trách nhưng không được tự hoàn tiền nếu thiếu quyền `payments:refund`.

## 4. Ví dụ BOLA trong API

Giả sử API có endpoint:

```http
GET /api/orders/7b6d8f6e-ff2b-4c13-8b8c-61c8f3f1d002
Authorization: Bearer <alice-access-token>
```

Alice được phép đọc đơn hàng có ID kết thúc bằng `...0001`. Nếu API triển khai như sau, request thay ID có thể đọc được đơn hàng của Bob:

```java
@GetMapping("/orders/{id}")
public Order getOrder(@PathVariable UUID id) {
    return orderRepository.findById(id)
        .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
}
```

Đoạn code trên chỉ kiểm tra bản ghi có tồn tại hay không. Nó không biết ai đang gọi, tenant nào sở hữu đơn hàng và người gọi có quyền đọc hay không.

Một cách triển khai an toàn hơn là lấy principal đã xác thực, giới hạn truy vấn theo tenant và kiểm tra quyền trên object:

```java
@GetMapping("/orders/{id}")
@PreAuthorize("hasAuthority('SCOPE_orders:read')")
public OrderView getOrder(
        @PathVariable UUID id,
        @AuthenticationPrincipal Jwt jwt) {
    ApiPrincipal principal = principalMapper.from(jwt);
    return orderService.getVisibleOrder(id, principal);
}

@Transactional(readOnly = true)
public OrderView getVisibleOrder(UUID orderId, ApiPrincipal actor) {
    Order order = orderRepository.findByIdAndTenantId(
            orderId, actor.tenantId())
        .orElseThrow(OrderNotFoundException::new);

    if (!orderPolicy.canRead(actor, order)) {
        throw new OrderNotFoundException();
    }

    return orderMapper.toView(order);
}
```

Ví dụ giả định `ApiPrincipal` được tạo từ identity đã xác thực và `tenantId` không lấy từ request body. `findByIdAndTenantId` giới hạn dữ liệu trong tenant; `orderPolicy.canRead` kiểm tra thêm ownership, membership hoặc permission phù hợp. Ở controller, `@PreAuthorize` kiểm tra quyền chức năng; kiểm tra trong service bảo vệ object khi cùng nghiệp vụ được gọi từ endpoint khác hoặc từ một thành phần nội bộ.

Repository có thể dùng truy vấn có điều kiện:

```java
public interface OrderRepository extends JpaRepository<Order, UUID> {
    Optional<Order> findByIdAndTenantId(UUID id, UUID tenantId);
}
```

Nếu chính sách cho phép nhân viên hỗ trợ đọc mọi đơn hàng trong tenant được phụ trách, `orderPolicy` cần kiểm tra permission và phạm vi tenant cụ thể. Không nên bỏ qua tenant constraint chỉ vì caller có role tổng quát như `SUPPORT`.

### 4.1. Tạo object: tự gán owner từ identity

BOLA có thể bắt đầu ngay khi tạo tài nguyên nếu client được tự chọn chủ sở hữu hoặc tenant. Ví dụ, API nhận:

```json
{
  "tenantId": "tenant-b",
  "ownerId": "user-bob",
  "description": "New order"
}
```

Nếu endpoint cho Alice tạo đơn trong tenant A nhưng tin hai trường trên, Alice có thể tạo object dưới danh nghĩa Bob hoặc tenant khác. Server nên lấy owner và tenant từ principal hoặc từ quy trình chuyển quyền đã được kiểm tra:

```java
public Order createOrder(CreateOrderRequest request, ApiPrincipal actor) {
    Order order = Order.create(
        actor.tenantId(),
        actor.userId(),
        request.description()
    );
    return orderRepository.save(order);
}
```

DTO tạo đơn chỉ chứa các trường mà người gọi được phép cung cấp. Nếu nghiệp vụ có chức năng tạo đơn thay mặt người khác, đây phải là một hành động riêng với quyền rõ ràng, audit và validation quan hệ đối tượng.

## 5. Bảo vệ các thao tác khác nhau trên cùng object

Kiểm tra quyền đọc không tự động bảo vệ cập nhật, xóa hoặc các hành động đặc biệt. Mỗi action cần một quyết định riêng.

| Thao tác | Kiểm tra cần có |
| --- | --- |
| Read | Caller có thể xem object này không? Có cần che giấu một số thuộc tính không? |
| Update | Caller có quyền sửa object và các field được gửi không? Trạng thái hiện tại có cho phép sửa không? |
| Delete | Caller có quyền xóa object không? Có phụ thuộc quan hệ hoặc trạng thái khác không? |
| Download | Caller có quyền truy cập file gắn với object không? URL tải có thời hạn và phạm vi phù hợp không? |
| Share | Caller có quyền chia sẻ object, cấp cho ai và ở mức quyền nào không? |
| Export/Search | Mỗi object trong kết quả có nằm trong phạm vi truy cập của caller không? |
| Bulk action | Từng ID trong danh sách có được kiểm tra và xử lý theo chính sách không? |

### 5.1. Update và mass assignment

Endpoint cập nhật thường mắc đồng thời BOLA và Broken Object Property Level Authorization (BOPLA) nếu chỉ nhận entity trực tiếp từ client. Ví dụ, Alice được đổi địa chỉ nhưng không được thay `ownerId`, `tenantId`, `totalPrice` hoặc `status`.

Hãy dùng request DTO giới hạn field, tải object trong phạm vi tenant, kiểm tra quyền cập nhật và áp dụng state transition trong domain:

```java
public record ChangeAddressRequest(
    @NotBlank @Size(max = 200) String address
) {}

@Transactional
public OrderView changeAddress(
        UUID orderId,
        ChangeAddressRequest request,
        ApiPrincipal actor) {

    Order order = orderRepository.findByIdAndTenantId(
            orderId, actor.tenantId())
        .orElseThrow(OrderNotFoundException::new);

    if (!orderPolicy.canChangeAddress(actor, order)) {
        throw new OrderNotFoundException();
    }

    order.changeShippingAddress(request.address());
    return orderMapper.toView(order);
}
```

Domain method `changeShippingAddress` nên kiểm tra trạng thái hợp lệ hoặc gọi policy nghiệp vụ tương ứng. Không bind toàn bộ request vào entity và không cho phép client tự gán các trường quản trị.

### 5.2. Bulk operation

Một endpoint như `POST /api/orders/archive` có thể nhận danh sách hàng trăm ID. Chỉ kiểm tra người gọi có quyền dùng chức năng archive là chưa đủ. Server phải xác minh quyền trên từng order, giới hạn số lượng phần tử và xác định hành vi khi danh sách chứa cả object được phép lẫn object không được phép.

Có thể chọn xử lý nguyên tử (toàn bộ thành công hoặc toàn bộ thất bại) hoặc kết quả từng phần, nhưng contract phải nói rõ hành vi. Không trả thông tin giúp kẻ tấn công dò object ID ngoài quyền. Tránh truy vấn theo ID mà không kèm tenant hoặc policy scope.

### 5.3. File, export và object storage

Tên file hoặc storage key cũng là object reference. Không nên cho phép người dùng tải `https://storage/.../tenant-b/private.pdf` chỉ vì họ biết đường dẫn. Backend cần kiểm tra quyền trên record gắn với file trước khi tạo signed URL hoặc stream dữ liệu.

Signed URL nên có thời hạn ngắn, chỉ cho đúng object và đúng thao tác (đọc hoặc ghi), có thể thu hồi qua cơ chế phù hợp và không bị ghi vào log công khai. Nếu quyền của user bị thu hồi, hệ thống cần cân nhắc thời gian sống còn lại của URL đã phát hành.

## 6. Những biện pháp phòng chống BOLA

### 6.1. Kiểm tra quyền tại server cho mỗi request

Mọi endpoint nhận hoặc suy ra object reference phải có bước authorization phía server. Kiểm tra cần chạy ở mọi đường truy cập: REST controller, GraphQL resolver, gRPC handler, message consumer, scheduled job và internal service method. Ẩn nút trên frontend hoặc kiểm tra ở API gateway không thay thế được kiểm tra tại service sở hữu dữ liệu.

### 6.2. Dùng principal và dữ liệu resource đáng tin cậy

Identity phải đến từ credential đã được xác thực. Tenant, owner, membership và trạng thái object phải lấy từ nguồn dữ liệu tin cậy phía server. Không dùng `userId`, `tenantId`, `ownerId`, role hoặc permission do client tự gửi làm căn cứ cấp quyền.

### 6.3. Giới hạn truy vấn ngay từ repository

Với hệ thống multi-tenant, ưu tiên truy vấn có điều kiện theo tenant hoặc phạm vi quyền ngay ở repository/database. Ví dụ `findByIdAndTenantId` giảm nguy cơ vô tình tải object ngoài tenant. Với quyền phức tạp, kết hợp truy vấn giới hạn phạm vi và policy check rõ ràng.

Không dựa vào UUID khó đoán để thay authorization. ID ngẫu nhiên chỉ làm giảm khả năng đoán mò; ID có thể xuất hiện trong log, email, URL, lịch sử trình duyệt, response hoặc dữ liệu chia sẻ. Người có ID vẫn phải qua kiểm tra quyền.

### 6.4. Kiểm tra nhất quán trên mọi endpoint và quan hệ lồng nhau

Nếu API có `/projects/{projectId}/documents/{documentId}`, phải xác minh document thực sự thuộc project được nêu và caller có quyền trên cả quan hệ đó. Không kiểm tra `projectId` rồi tải `documentId` độc lập. Tương tự, `accountId` và `invoiceId` trong cùng request phải có quan hệ hợp lệ.

Hãy rà soát cả endpoint ít được dùng như export, download, bulk update, history, attachment, search, report và GraphQL node lookup. Các endpoint này thường dùng repository hoặc service khác với đường đi chính.

### 6.5. Bảo vệ cache và tác vụ bất đồng bộ

Cache response theo URL đơn thuần có thể trả dữ liệu của Alice cho Bob nếu nội dung phụ thuộc identity hoặc tenant. Cache key cần bao gồm phạm vi bảo mật phù hợp hoặc không cache dữ liệu nhạy cảm dùng chung. Luôn kiểm tra quyền trước khi trả dữ liệu từ cache; ETag và conditional request cũng không bỏ qua authorization.

Khi tạo background job, lưu context tin cậy cần thiết và xác định rõ job chạy dưới danh nghĩa ai. Tại thời điểm job thực thi, có thể cần kiểm tra lại quyền và trạng thái object vì membership hoặc quyền có thể đã bị thu hồi sau lúc enqueue. Không coi ID được truyền trong message là bằng chứng quyền.

### 6.6. Fail closed và xử lý lỗi nhất quán

Nếu không thể xác định principal, không tải được policy, thiếu thuộc tính cần thiết hoặc không thể kiểm tra quan hệ sở hữu, thao tác nhạy cảm phải bị từ chối. Không cho phép truy cập chỉ vì authorization service timeout hoặc dữ liệu quyền bị thiếu.

Có thể trả `403 Forbidden` khi muốn thể hiện object tồn tại nhưng caller không có quyền. Có thể trả `404 Not Found` để che giấu sự tồn tại của object, đặc biệt với tài nguyên riêng tư hoặc cross-tenant. Chọn chính sách phù hợp và áp dụng nhất quán để tránh tạo kênh dò tìm ID.

## 7. Kiểm thử BOLA

Kiểm thử cần dùng ít nhất hai người dùng và, với hệ thống multi-tenant, ít nhất hai tenant. Tạo các object có quan hệ sở hữu rõ ràng để kiểm tra việc thay ID ở mọi vị trí có thể.

Giả sử có ba principal:

- Alice thuộc tenant A và sở hữu `order-A1`.
- Bob thuộc tenant A và sở hữu `order-A2`.
- Carol thuộc tenant B và sở hữu `order-B1`.

Ma trận kiểm thử ví dụ:

| Caller | Request | Kết quả mong đợi |
| --- | --- | --- |
| Alice | Đọc `order-A1` | Cho phép. |
| Alice | Đọc `order-A2` | Từ chối nếu Alice không có quyền đọc đơn của Bob. |
| Alice | Đọc `order-B1` | Từ chối do khác tenant. |
| Alice | Cập nhật địa chỉ `order-A2` | Từ chối; dữ liệu không thay đổi. |
| Alice | Xóa `order-A2` | Từ chối; object vẫn tồn tại. |
| Alice | Tải file gắn với `order-B1` | Từ chối; không phát hành signed URL. |
| Support A | Đọc `order-A2` | Cho phép nếu có permission đọc mọi order trong tenant A. |
| Support A | Đọc `order-B1` | Từ chối nếu không có phạm vi tenant B. |
| Alice | Gửi `ownerId=Bob` khi tạo order | Server vẫn gán owner theo Alice hoặc từ chối field không được phép. |

### 7.1. Kiểm thử tự động ở mức API

Một test tích hợp có thể thể hiện ý tưởng kiểm tra object ownership:

```java
@Test
void userCannotReadAnotherUsersOrder() throws Exception {
    UUID bobsOrderId = orderFixture.createOrder(
        tenantA, bobUserId);

    mockMvc.perform(get("/api/orders/{id}", bobsOrderId)
            .with(jwt().jwt(jwt -> jwt
                .subject(aliceUserId.toString())
                .claim("tenant_id", tenantA.toString()))
                .authorities(new SimpleGrantedAuthority("SCOPE_orders:read"))))
        .andExpect(status().isNotFound());
}
```

Đây là ví dụ minh họa với Spring Security MockMvc; fixture phải tạo object thuộc Bob và JWT test đại diện cho Alice đã được xác thực. Controller chuyển JWT đã xác minh thành principal nội bộ qua `principalMapper`. Test cần xác minh thêm rằng không có side effect và response không chứa dữ liệu của Bob. Trong dự án thực tế, cấu hình test JWT, claim mapping và fixture phải khớp với ứng dụng.

### 7.2. Kiểm tra cả side effect và các đường vòng

Đối với update/delete, chỉ kiểm tra status code chưa đủ. Hãy đọc lại database để chắc chắn object không bị thay đổi hoặc xóa. Với bulk action, xác minh từng object. Với signed URL, kiểm tra không có URL nào được phát hành cho object ngoài quyền.

Kiểm thử cần bao gồm cả gọi qua gateway và gọi trực tiếp service trong môi trường test nếu kiến trúc cho phép. Điều này giúp phát hiện trường hợp gateway có kiểm tra nhưng backend lại tin request nội bộ không an toàn. Không cần dùng ID ngẫu nhiên trong test; ID dễ nhận biết giúp kiểm chứng rõ ràng rằng API không dựa vào tính khó đoán của định danh.

## 8. Giám sát và phản ứng khi phát hiện BOLA

Log bảo mật nên ghi nhận route template, action, subject ID ở dạng phù hợp, tenant, resource ID, quyết định allow/deny, policy version và correlation ID. Không ghi access token, mật khẩu hoặc payload nhạy cảm nguyên vẹn.

Các tín hiệu đáng theo dõi:

- Một principal thử nhiều ID liên tiếp hoặc truy cập nhiều object không thuộc cùng phạm vi.
- Tỷ lệ `403` hoặc `404` tăng bất thường trên một endpoint có object ID.
- Một tài khoản đọc hoặc tải file từ nhiều tenant trong thời gian ngắn.
- Các request bulk chứa nhiều ID không liên quan đến principal.
- Lưu lượng truy cập object tăng đột biến sau khi một ID xuất hiện trong response, email hoặc log.

Khi nghi ngờ BOLA, cần xác định object và tenant bị ảnh hưởng, thời gian, principal, action và dữ liệu đã bị đọc hoặc thay đổi. Thu hồi session/token hoặc quyền liên quan khi cần; kiểm tra signed URL, cache và background job; đánh giá dữ liệu đã bị truy cập; sửa policy và thêm regression test. Việc xử lý phải giữ lại bằng chứng audit theo quy trình của tổ chức.

## 9. Checklist thiết kế endpoint chống BOLA

- [ ] Endpoint có nhận hoặc suy ra object ID, file key, parent ID hay danh sách ID không?
- [ ] Principal được lấy từ credential đã xác thực và tenant/owner không lấy từ input không đáng tin cậy?
- [ ] Quyền được kiểm tra theo từng action trên từng object và trạng thái nghiệp vụ chưa?
- [ ] Các quan hệ lồng nhau như project-document hoặc account-invoice đã được xác minh chưa?
- [ ] Repository/query có giới hạn theo tenant hoặc phạm vi quyền phù hợp không?
- [ ] Read, update, delete, download, share, export, search và bulk action đều được bảo vệ chưa?
- [ ] DTO chỉ cho phép thay đổi các field mà caller được quyền cập nhật chưa?
- [ ] Cache, signed URL và background job có giữ đúng phạm vi quyền không?
- [ ] Khi policy hoặc dữ liệu quyền không sẵn sàng, thao tác có bị từ chối an toàn không?
- [ ] Có kiểm thử chéo user/tenant cho cả response và side effect không?
- [ ] Log và cảnh báo có thể phát hiện hành vi dò object mà không làm lộ dữ liệu nhạy cảm không?

BOLA không được khắc phục bằng cách làm ID khó đoán hoặc chỉ yêu cầu đăng nhập. API phải kiểm tra quyền của chủ thể đã xác thực trên đúng đối tượng, đúng hành động và đúng ngữ cảnh ở phía server. Khi quy tắc này được áp dụng nhất quán cho mọi endpoint và đường xử lý dữ liệu, việc thay đổi object ID sẽ không giúp người gọi vượt qua phạm vi quyền được cấp.
