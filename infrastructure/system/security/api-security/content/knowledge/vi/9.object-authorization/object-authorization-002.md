# Kiểm tra quyền trên từng object ID từ request

Một API có thể xác thực người dùng hoàn toàn chính xác nhưng vẫn để lộ dữ liệu nếu người dùng thay một object ID trong request. Ví dụ, khách hàng A đăng nhập hợp lệ và gọi `GET /api/orders/1001`. Khi đổi ID thành `1002`, API lại trả về đơn hàng của khách hàng B vì chỉ kiểm tra token hợp lệ mà không kiểm tra quyền trên đơn hàng được yêu cầu. Đây là lỗi **Broken Object Level Authorization (BOLA)**, thường được gọi là **IDOR** khi biểu hiện qua việc tham chiếu trực tiếp đến đối tượng.

Trong API Security, mỗi object ID do client gửi lên phải được xem là một yêu cầu truy cập tới một đối tượng cụ thể. Máy chủ cần xác minh người gọi có quyền thực hiện đúng hành động trên đúng đối tượng đó trong ngữ cảnh hiện tại. Việc ID là UUID khó đoán, người dùng đã đăng nhập, endpoint có annotation phân quyền hoặc API chạy qua HTTPS đều không thay thế được bước kiểm tra này.

Sau bài học, người đọc có thể:

- Nhận diện BOLA/IDOR khi API nhận object ID từ path, query, body, nested resource hoặc batch request.
- Phân biệt quyền mức chức năng với quyền trên từng đối tượng.
- Xây dựng quyết định phân quyền dựa trên người gọi, hành động, đối tượng và ngữ cảnh.
- Giới hạn truy vấn dữ liệu theo tenant, owner hoặc quan hệ được phép truy cập.
- Kiểm tra quyền nhất quán cho đọc, cập nhật, xóa, tìm kiếm, tải tệp và xử lý bất đồng bộ.
- Thiết kế test để phát hiện truy cập chéo người dùng, chéo tenant và các trường hợp ID bị thay đổi.

## 1. Object authorization giải quyết vấn đề gì?

Một object là một đối tượng dữ liệu mà API quản lý hoặc tham chiếu, chẳng hạn đơn hàng, hồ sơ, hóa đơn, tài liệu, địa chỉ giao hàng, tệp đính kèm hoặc giao dịch. Object ID là định danh để máy chủ tìm đối tượng đó. ID có thể là số tăng dần, UUID, mã nghiệp vụ hoặc chuỗi do hệ thống bên ngoài cấp.

Khi request chứa ID, API thường thực hiện hai việc khác nhau:

1. Xác định đối tượng mà client muốn thao tác.
2. Quyết định caller có được phép thực hiện hành động trên đối tượng đó hay không.

Lỗi xảy ra khi ứng dụng làm tốt bước thứ nhất nhưng bỏ qua hoặc thực hiện sai bước thứ hai. Ví dụ, controller gọi `orderRepository.findById(id)` rồi trả dữ liệu ngay cho bất kỳ người dùng đã đăng nhập nào. Người gọi có thể thay ID để truy cập dữ liệu của người khác.

### 1.1. BOLA và IDOR

**BOLA** là lỗi kiểm soát quyền mức đối tượng: người gọi có thể truy cập một đối tượng mà chính sách không cho phép. Lỗi có thể xảy ra khi đọc, cập nhật, xóa, tải xuống hoặc kích hoạt hành động trên đối tượng.

**IDOR (Insecure Direct Object Reference)** mô tả một dạng triển khai dễ mắc lỗi: ứng dụng dùng một tham chiếu trực tiếp như ID trong URL hoặc request để tải đối tượng nhưng không kiểm tra quyền tương ứng. IDOR thường là biểu hiện của BOLA; thay đổi ID không phải điều kiện duy nhất để có BOLA, vì lỗi cũng có thể xuất hiện qua mã tham chiếu, khóa tự nhiên, tên tệp hoặc quan hệ lồng nhau.

Ví dụ:

```http
GET /api/invoices/INV-2026-0018
Authorization: Bearer <token-cua-khach-hang-A>
```

Nếu invoice `INV-2026-0018` thuộc khách hàng B mà API vẫn trả dữ liệu cho khách hàng A, việc xác thực token đã thành công nhưng object authorization thất bại.

### 1.2. Phân biệt với phân quyền mức chức năng

Broken Function Level Authorization (BFLA) xảy ra khi caller gọi được một chức năng mà vai trò hoặc quyền của họ không cho phép, ví dụ khách hàng gọi endpoint quản trị `GET /api/admin/users`.

BOLA xảy ra khi caller được phép dùng chức năng nhưng không được phép thao tác trên object cụ thể, ví dụ khách hàng có quyền `order:read` nhưng chỉ được đọc đơn hàng của mình. Một endpoint có thể đồng thời mắc cả hai loại lỗi.

| Lớp kiểm tra | Câu hỏi | Ví dụ |
|---|---|---|
| Xác thực | Ai đang gọi? | Token có hợp lệ và thuộc user A không? |
| Quyền chức năng | Caller có được dùng hành động này? | User A có `order:read` không? |
| Quyền đối tượng | Caller có quyền trên object này? | Đơn hàng 1002 có thuộc phạm vi của A không? |
| Quyền thuộc tính | Caller được đọc hoặc sửa trường nào? | A có được xem địa chỉ giao hàng hoặc sửa ghi chú không? |
| Quy tắc nghiệp vụ | Hành động có hợp lệ ở trạng thái hiện tại? | Đơn đã giao có còn được hủy không? |

Các lớp kiểm tra bổ sung cho nhau. Có `order:read` không đồng nghĩa được đọc mọi đơn hàng; có quyền trên một đơn hàng cũng không có nghĩa được thay đổi mọi trường hoặc thực hiện mọi hành động trên đơn đó.

## 2. Xác định object ID có thể đến từ đâu

Không chỉ ID ở path parameter mới cần kiểm tra. Bất kỳ giá trị nào được dùng để tìm, chọn hoặc tác động đến một object đều có thể trở thành điểm khai thác.

| Vị trí trong request | Ví dụ | Điều cần xác minh |
|---|---|---|
| Path parameter | `/orders/1002` | Caller có quyền trên đơn hàng 1002 không? |
| Query parameter | `/documents?folderId=F-8` | Caller có quyền xem folder F-8 không? |
| Request body | `{"invoiceId":"I-9"}` | Caller có quyền thao tác invoice I-9 không? |
| Nested resource | `/users/17/orders/1002` | Đơn 1002 có thực sự thuộc user 17 và caller có quyền trên cả quan hệ đó không? |
| Header hoặc custom claim do client gửi | `X-Account-Id: A-7` | Giá trị có phải nguồn định danh đáng tin cậy hay chỉ là lựa chọn do client khai báo? |
| Batch/list | `{"ids":["1001","1002"]}` | Mỗi object trong danh sách có được phép xử lý không? |
| GraphQL variable | `{"orderId":"1002"}` | Resolver có kiểm tra quyền trên object được truy xuất không? |
| File key hoặc attachment ID | `/files/FILE-92/download` | Caller có quyền trên tệp và tài nguyên cha không? |

ID trong body có thể nằm sâu trong cấu trúc, ví dụ `shippingAddressId`, `ownerId`, `projectId`, `paymentMethodId` hoặc danh sách `memberIds`. Không được giả định rằng một request chỉ có một object cần kiểm tra.

ID tuần tự dễ bị đoán, nhưng chuyển sang UUID hoặc ID ngẫu nhiên chỉ làm giảm khả năng dò tìm. Nếu một người lấy được ID từ log, email, URL chia sẻ, response khác hoặc nguồn rò rỉ, họ vẫn có thể khai thác API nếu thiếu authorization. **Định danh khó đoán không phải là cơ chế phân quyền.**

## 3. Mô hình quyết định quyền trên object

Một quyết định object authorization nên xét ít nhất bốn thành phần:

- **Subject (chủ thể):** người dùng hoặc service principal đã được xác thực, cùng các thuộc tính đáng tin cậy như user ID, tenant, role, nhóm và phạm vi được giao.
- **Action (hành động):** thao tác đang yêu cầu, ví dụ `read`, `update`, `delete`, `download`, `approve` hoặc `refund`.
- **Resource (đối tượng):** object đích, loại object, owner, tenant, trạng thái và các quan hệ liên quan.
- **Context (ngữ cảnh):** thời điểm, trạng thái phiên, nguồn gọi, quan hệ phân công, trạng thái nghiệp vụ hoặc điều kiện rủi ro cần áp dụng.

Có thể diễn đạt quyết định dưới dạng:

```text
ALLOW nếu:
  subject đã được xác thực
  AND subject có quyền chức năng cho action
  AND subject có quan hệ được phép với resource
  AND resource thuộc phạm vi tenant/owner phù hợp
  AND context và trạng thái nghiệp vụ đáp ứng chính sách
Ngược lại: DENY
```

Ví dụ, khách hàng được đọc đơn hàng nếu đơn thuộc tài khoản của họ; nhân viên hỗ trợ được đọc đơn nếu đơn nằm trong nhóm phụ trách; quản lý được duyệt đơn nếu thuộc khu vực quản lý và đơn đang ở trạng thái cho phép. Cùng một object có thể có chính sách khác nhau cho từng action và từng chủ thể.

### 3.1. Quyền sở hữu (ownership)

Chính sách đơn giản nhất là chỉ owner được thao tác trên object. Ví dụ, một tài liệu có `ownerId` bằng user ID của caller. Điều kiện này phù hợp với hồ sơ cá nhân hoặc tài liệu riêng, nhưng không đủ cho hệ thống có chia sẻ, nhóm, nhân viên hỗ trợ hoặc quản lý.

Không lấy `ownerId` từ body của request để quyết định người gọi là ai. Owner hiện tại phải được đọc từ dữ liệu có thẩm quyền ở máy chủ. Nếu người dùng được phép chuyển quyền sở hữu, đó phải là một hành động riêng có quyền và quy tắc kiểm tra cụ thể.

### 3.2. Quyền theo tenant

Trong hệ thống multi-tenant, object thường thuộc một tenant. Mọi truy vấn truy cập dữ liệu cần được giới hạn theo tenant đáng tin cậy của principal hoặc ngữ cảnh service đã xác minh. Không sử dụng `tenantId` do client tự gửi làm bằng chứng quyền.

Ví dụ, người dùng thuộc tenant A gửi `GET /api/invoices/500`. Dù invoice 500 tồn tại trong tenant B, truy vấn trong phạm vi tenant A phải không trả object đó. Cách này giúp giảm nguy cơ truy cập chéo tenant ngay từ tầng truy vấn.

### 3.3. Quyền theo quan hệ (relationship)

Một object có thể được truy cập qua quan hệ được cấp: thành viên của project, nhân viên được phân công cho ticket, người nhận được chia sẻ tài liệu hoặc người quản lý phụ trách khu vực. Chính sách cần kiểm tra quan hệ hiện tại trong dữ liệu có thẩm quyền, thay vì chỉ so sánh một ID do client cung cấp.

Với hệ thống có nhiều quan hệ, có thể dùng RBAC kết hợp ABAC hoặc mô hình quan hệ như ReBAC. Dù dùng mô hình nào, API vẫn phải có một điểm thực thi chính sách nhất quán và mặc định từ chối khi không xác định được quyền.

## 4. Kiểm tra quyền ngay tại nơi truy xuất object

Một cách triển khai an toàn là giới hạn truy vấn theo phạm vi người gọi ngay trong repository hoặc query. Thay vì tải object chỉ bằng ID rồi quên kiểm tra quyền, hãy truy vấn object mà caller được phép nhìn thấy.

Ví dụ minh họa với Spring Boot và Spring Data:

```java
@GetMapping("/orders/{id}")
@PreAuthorize("hasAuthority('order:read')")
public OrderResponse getOrder(
        @PathVariable UUID id,
        @AuthenticationPrincipal ApiPrincipal principal) {

    Order order = orderRepository
            .findByIdAndTenantIdAndOwnerId(
                    id,
                    principal.tenantId(),
                    principal.userId())
            .orElseThrow(OrderNotFoundException::new);

    return orderMapper.toResponse(order);
}
```

Trong ví dụ:

- `@PreAuthorize` kiểm tra quyền chức năng `order:read`.
- `ApiPrincipal` được tạo từ thông tin xác thực đã xác minh; `tenantId` và `userId` không lấy từ request body hoặc query parameter.
- Truy vấn yêu cầu đồng thời khớp object ID, tenant và owner.
- Khi object không nằm trong phạm vi caller, repository không trả object cho controller.

Phương thức repository có thể được khai báo như sau:

```java
Optional<Order> findByIdAndTenantIdAndOwnerId(
        UUID id,
        UUID tenantId,
        UUID ownerId);
```

Đây là ví dụ cho chính sách owner-only. Nếu nhân viên hỗ trợ hoặc quản lý cũng được truy cập, hãy mở rộng điều kiện theo quan hệ được phép, ví dụ `exists` trong bảng assignment hoặc một query policy rõ ràng. Không nên bỏ điều kiện owner rồi cho mọi user cùng tenant xem mọi object nếu nghiệp vụ không cho phép.

### 4.1. Khi cần tải object trước rồi kiểm tra policy

Một số chính sách phức tạp cần dữ liệu object để quyết định, ví dụ kiểm tra nhân viên có thuộc nhóm phụ trách ticket hay quản lý có phụ trách vùng của đơn hàng. Có thể tải object trong phạm vi tenant, sau đó gọi policy service:

```java
@Transactional(readOnly = true)
public OrderResponse getOrder(UUID orderId, ApiPrincipal actor) {
    Order order = orderRepository
            .findByIdAndTenantId(orderId, actor.tenantId())
            .orElseThrow(OrderNotFoundException::new);

    authorizationService.requireCanReadOrder(actor, order);
    return orderMapper.toResponse(order);
}
```

`requireCanReadOrder` cần kiểm tra quan hệ owner, assignment, vai trò và điều kiện ngữ cảnh theo chính sách. Không trả object hoặc một phần dữ liệu ra ngoài trước khi quyết định quyền hoàn tất. Với dữ liệu rất nhạy cảm hoặc tenant isolation nghiêm ngặt, ưu tiên query có scope ngay từ đầu và chỉ tải các cột cần thiết.

### 4.2. Vì sao kiểm tra ở repository có ích?

Query có scope giúp tránh một số lỗi phổ biến:

- Controller quên gọi authorization service sau `findById`.
- Một nhánh xử lý lỗi hoặc response phụ trả object trước khi kiểm tra quyền.
- Dữ liệu tenant khác được tải và vô tình đưa vào cache hoặc log.
- Phân trang, tổng số bản ghi hoặc bộ lọc bị tính trên toàn bộ dữ liệu trước khi giới hạn quyền.

Query scope không tự giải quyết mọi chính sách. Với quyền dựa trên quan hệ hoặc trạng thái nghiệp vụ, cần thể hiện đầy đủ điều kiện hoặc bổ sung policy check. Điều quan trọng là mọi đường đi tới dữ liệu phải dùng cùng quy tắc.

## 5. Kiểm tra object authorization cho từng loại thao tác

Không chỉ GET mới có nguy cơ BOLA. Kẻ tấn công có thể thay ID trong PUT, PATCH, DELETE hoặc các command như approve, cancel, refund, download và share.

### 5.1. Đọc object

Với `GET /orders/{id}`, truy vấn phải giới hạn theo owner, tenant hoặc quan hệ được phép. Response DTO chỉ chứa các trường caller được đọc. Không serialize trực tiếp entity vì entity có thể chứa thông tin nội bộ hoặc quan hệ nhạy cảm.

### 5.2. Cập nhật object

Với `PATCH /orders/{id}`, kiểm tra caller có quyền cập nhật chính đơn hàng đó và chỉ cho thay đổi thuộc tính được phép. Request DTO nên chỉ chứa các trường như ghi chú giao hàng; các trường `ownerId`, `tenantId`, `total`, `approvedBy` hoặc `status` không được cập nhật qua binding tùy ý.

Ví dụ:

```java
@Transactional
public OrderResponse updateNote(
        UUID orderId,
        UpdateOrderNoteRequest request,
        ApiPrincipal actor) {

    Order order = orderRepository
            .findByIdAndTenantId(orderId, actor.tenantId())
            .orElseThrow(OrderNotFoundException::new);

    authorizationService.requireCanUpdateOrder(actor, order);
    order.changeDeliveryNote(request.deliveryNote());

    return orderMapper.toResponse(order);
}
```

Trong ví dụ, quyền chức năng có thể được kiểm tra ở controller hoặc service; quyền trên object được kiểm tra bằng policy service. Entity chỉ thay đổi qua phương thức nghiệp vụ được phép. Nếu cập nhật trạng thái, giá hoặc quyền sở hữu, hãy thiết kế action riêng và policy chặt chẽ hơn.

### 5.3. Xóa object

Với `DELETE /documents/{id}`, cần kiểm tra quyền xóa trên đúng document, tenant, trạng thái retention và quan hệ phụ thuộc. Quyền đọc hoặc cập nhật không mặc nhiên bao gồm quyền xóa. Nếu xóa là soft delete, các truy vấn đọc và tải tệp cũng phải tôn trọng trạng thái đã xóa.

### 5.4. Hành động nghiệp vụ trên object

Các endpoint như `POST /orders/{id}/approve`, `POST /orders/{id}/refunds` hoặc `POST /tickets/{id}/assign` cần kiểm tra cả quyền trên object lẫn quyền thực hiện action. Ví dụ, người dùng có thể xem đơn hàng nhưng không được duyệt; quản lý có quyền duyệt nhưng chỉ với đơn thuộc khu vực mình phụ trách.

Không nên dùng một quyền chung `order:write` cho tất cả cập nhật, duyệt và hoàn tiền nếu tác động và người được phép khác nhau. Hãy mô hình hóa action đủ cụ thể để policy có thể quyết định rõ ràng.

## 6. Kiểm tra quan hệ giữa các object trong nested resource

Một endpoint lồng nhau có thể tạo cảm giác rằng kiểm tra quyền trên object cha là đủ:

```http
GET /api/users/17/orders/1002
```

Nhưng máy chủ phải xác minh tất cả điều kiện cần thiết:

1. Caller có quyền truy cập user hoặc account 17 theo chính sách không?
2. Order 1002 có thực sự thuộc user 17 không?
3. Caller có quyền đọc order 1002 trong quan hệ đó không?

Nếu API chỉ kiểm tra caller được truy cập user 17 rồi truy vấn order bằng ID 1002 độc lập, kẻ tấn công có thể ghép ID của hai object không liên quan để vượt qua kiểm soát.

Một query phù hợp nên kiểm tra quan hệ trong cùng truy vấn, ví dụ:

```sql
SELECT o.*
FROM orders o
JOIN users u ON u.id = o.user_id
WHERE o.id = :orderId
  AND u.id = :userId
  AND u.tenant_id = :trustedTenantId;
```

Đây chỉ là ví dụ về điều kiện liên kết; quyền caller trên user và order vẫn phải được áp dụng theo policy. Nếu object có quan hệ nhiều-nhiều, cần xác minh quan hệ hiện hành thay vì dựa vào ID cha do client tự chọn.

Nguyên tắc tương tự áp dụng cho:

- `GET /projects/{projectId}/files/{fileId}`: file phải thuộc project được chỉ định và caller được phép đọc cả file.
- `PATCH /teams/{teamId}/members/{memberId}`: member phải thuộc team đó; caller phải có quyền quản lý thành viên.
- `GET /accounts/{accountId}/transactions/{transactionId}`: transaction phải thuộc account và caller được phép xem giao dịch.

## 7. Danh sách, tìm kiếm, batch và các đường truy cập gián tiếp

### 7.1. List và search

Với `GET /orders`, API phải giới hạn tập dữ liệu ngay trong query theo phạm vi caller trước khi phân trang và tính tổng. Nếu lấy toàn bộ dữ liệu rồi lọc trong bộ nhớ, hệ thống có thể trả sai tổng số, làm lộ metadata hoặc tiêu tốn tài nguyên quá mức.

Các điều kiện tenant, owner hoặc assignment cần được áp dụng nhất quán cho cả:

- Danh sách và trang kết quả.
- `totalElements`, count, aggregation và facet.
- Export CSV/Excel/PDF.
- Bộ lọc, autocomplete và endpoint tìm kiếm.
- Thống kê hoặc dashboard tổng hợp theo object.

Không để API trả một danh sách ID hoặc số lượng object mà caller không có quyền nhìn thấy. Metadata như tên khách hàng, trạng thái, tổng tiền hoặc số lượng bản ghi cũng có thể tiết lộ thông tin.

### 7.2. Batch request

Một request có thể chứa nhiều ID:

```json
{
  "orderIds": ["1001", "1002", "1003"]
}
```

Phải kiểm tra quyền trên từng object. Không kiểm tra quyền trên ID đầu tiên rồi xử lý toàn bộ danh sách. API cần quy định rõ:

- **All-or-nothing:** nếu một object không hợp lệ hoặc không được phép, từ chối toàn bộ batch và không để lại thay đổi một phần.
- **Partial result:** xử lý từng object và trả kết quả riêng cho từng phần tử, nhưng không tiết lộ quá mức sự tồn tại hoặc thông tin của object bị từ chối.

Giới hạn số lượng ID, loại bỏ ID trùng theo hợp đồng, kiểm tra kích thước request và bảo đảm mỗi thao tác được thực hiện trong transaction hoặc cơ chế nhất quán phù hợp. Batch là nơi dễ bỏ sót object authorization vì code thường dùng vòng lặp xử lý nhiều bản ghi.

### 7.3. GraphQL, tệp và tác vụ nền

Trong GraphQL, resolver phải kiểm tra quyền trên object mà nó truy xuất, kể cả object được lấy qua nested field hoặc DataLoader. Việc đã xác thực ở tầng GraphQL context không đồng nghĩa mọi resolver đều được phép trả dữ liệu.

Với tệp, cần kiểm tra quyền trên file ID và tài nguyên cha (nếu có) trước khi tạo URL tải xuống hoặc stream nội dung. URL ký có thời hạn chỉ nên được cấp sau khi xác minh quyền; thời hạn, phạm vi và khả năng thu hồi phải phù hợp với độ nhạy cảm của tệp.

Với tác vụ bất đồng bộ, lưu lại actor, tenant và phạm vi quyền đã được xác minh khi khởi tạo. Khi worker thực thi, cần xác minh lại các điều kiện có thể thay đổi như assignment, trạng thái object hoặc quyền đã bị thu hồi. Service account dùng để chạy worker không nên vô tình trở thành quyền truy cập vô hạn cho mọi object. Audit log cần liên kết tác vụ với người khởi tạo và danh tính service thực thi.

## 8. Tránh các cách kiểm tra quyền dễ sai

### 8.1. Chỉ kiểm tra đã đăng nhập

```java
@PreAuthorize("isAuthenticated()")
public OrderResponse getOrder(UUID id) {
    return orderRepository.findById(id)
            .map(orderMapper::toResponse)
            .orElseThrow(OrderNotFoundException::new);
}
```

Đoạn code chỉ chứng minh caller có danh tính đã xác thực. Nó không kiểm tra quyền trên order được yêu cầu.

### 8.2. Tin ID hoặc tenant do client gửi

```json
{
  "tenantId": "tenant-B",
  "ownerId": "user-B",
  "deliveryNote": "Để tại cửa"
}
```

Không dùng các trường này để xác định caller thuộc tenant hoặc owner nào. Lấy thông tin chủ thể từ principal được tạo sau xác thực; dữ liệu quan hệ lấy từ cơ sở dữ liệu có thẩm quyền.

### 8.3. Cho rằng UUID đã đủ an toàn

UUID làm ID khó đoán hơn số tăng dần nhưng không ngăn người dùng truy cập ID bị lộ. Vẫn phải kiểm tra quyền trên object ở mọi request.

### 8.4. Chỉ kiểm tra ở giao diện hoặc API Gateway

Ẩn nút, khóa route ở frontend hoặc kiểm tra role tại gateway không đủ để bảo vệ từng object. Client có thể gọi API trực tiếp, gateway có thể không hiểu quan hệ dữ liệu, và nhiều endpoint khác có thể truy cập cùng object. Quyết định quyền cần được thực thi tại lớp ứng dụng/dịch vụ sở hữu dữ liệu; gateway là lớp bổ sung.

### 8.5. Chỉ kiểm tra một lần ở luồng trước

Không giả định rằng caller đã qua một endpoint kiểm tra quyền thì mọi request tiếp theo đều hợp lệ. Quyền có thể bị thu hồi, object có thể đổi owner, assignment hoặc tenant; request mới cũng có thể chứa một ID khác. Mỗi lần truy cập cần kiểm tra lại theo trạng thái hiện tại và chính sách áp dụng.

## 9. Xử lý từ chối truy cập và tránh rò rỉ thông tin

Khi caller không được phép truy cập object, API cần trả lỗi nhất quán và không tiết lộ dữ liệu nhạy cảm.

- `401 Unauthorized`: chưa có thông tin xác thực hợp lệ hoặc token không hợp lệ.
- `403 Forbidden`: caller đã xác thực nhưng không được phép thực hiện hành động theo chính sách.
- `404 Not Found`: có thể dùng khi chính sách yêu cầu che giấu sự tồn tại của object đối với caller không có quyền.

Chọn `403` hay `404` cần dựa trên chính sách bảo mật và trải nghiệm API. Nếu dùng `404` để che giấu object, cần áp dụng nhất quán cho các endpoint liên quan; không để một endpoint trả `404` nhưng endpoint khác tiết lộ object tồn tại qua `403`, thông báo lỗi, count hoặc thời gian xử lý khác biệt rõ rệt.

Response không nên chứa owner, tenant, tên khách hàng, trạng thái, hoặc bất kỳ thuộc tính nào của object bị từ chối. Thông báo chung như `Resource not found` hoặc `Resource is unavailable` thường an toàn hơn việc giải thích object thuộc user khác. Không trả stack trace hoặc câu truy vấn nội bộ.

## 10. Cập nhật đồng thời và kiểm tra quyền tại thời điểm thực thi

Object authorization có thể bị sai nếu ứng dụng kiểm tra quyền, sau đó một tiến trình khác thay đổi owner hoặc trạng thái trước khi request ghi dữ liệu. Đây là vấn đề race condition hoặc time-of-check-to-time-of-use (TOCTOU).

Ví dụ: service kiểm tra nhân viên A đang được phân công ticket 88. Trước khi A cập nhật, quản lý chuyển ticket sang nhân viên B. Nếu request của A vẫn ghi mà không kiểm tra lại hoặc kiểm soát phiên bản, A có thể cập nhật object sau khi quyền đã bị thu hồi.

Các cách giảm rủi ro:

- Đặt kiểm tra quan hệ và cập nhật trong cùng transaction với mức cô lập phù hợp.
- Dùng optimistic locking (`@Version`) hoặc ETag/`If-Match` để phát hiện object đã thay đổi.
- Với thao tác đơn giản, dùng câu lệnh cập nhật có điều kiện theo ID, tenant, owner/assignment và trạng thái; kiểm tra số dòng bị tác động.
- Thực hiện kiểm tra chuyển trạng thái và cập nhật một cách nguyên tử trong lớp nghiệp vụ.
- Với tác vụ bất đồng bộ, kiểm tra lại những điều kiện quyền cần còn hiệu lực tại thời điểm worker thực hiện.

Ví dụ SQL minh họa cho một chính sách owner-only và trạng thái cho phép cập nhật:

```sql
UPDATE orders
SET delivery_note = :deliveryNote,
    version = version + 1
WHERE id = :orderId
  AND tenant_id = :trustedTenantId
  AND owner_id = :trustedUserId
  AND status = 'CREATED';
```

Nếu số dòng cập nhật bằng 0, có thể object không tồn tại, không thuộc phạm vi caller hoặc không còn ở trạng thái cho phép. API xử lý kết quả theo chính sách `404`, `403` hoặc `409` đã công bố. Không trả về chi tiết điều kiện nào thất bại nếu điều đó làm lộ thông tin.

## 11. Cache, log và giám sát object authorization

### 11.1. Cache không được bỏ qua phạm vi quyền

Nếu response phụ thuộc người dùng hoặc tenant, cache key phải phản ánh phạm vi truy cập hoặc cache phải được cấu hình không chia sẻ giữa các caller. Không cache response riêng tư dưới một key chỉ gồm URL nếu URL có thể được gọi bởi nhiều user với quyền khác nhau.

Kiểm tra authorization trước khi trả dữ liệu từ cache. Với dữ liệu có quyền thay đổi thường xuyên, cần cân nhắc vô hiệu hóa cache khi owner, tenant, assignment hoặc trạng thái chia sẻ thay đổi. Response nhạy cảm có thể dùng `Cache-Control: private, no-store`.

### 11.2. Audit và log

Với truy cập object quan trọng, ghi nhận tối thiểu:

- Request ID và thời điểm.
- Actor đã được xác thực (định danh nội bộ phù hợp, không ghi token).
- Action được yêu cầu và loại object/object ID.
- Tenant hoặc phạm vi áp dụng khi phù hợp.
- Quyết định allow/deny và mã lý do nội bộ có kiểm soát.
- Kết quả xử lý và nguồn gọi cần thiết cho điều tra.

Không ghi toàn bộ request body nếu chứa dữ liệu cá nhân, thông tin thanh toán hoặc secret. Audit log cần được bảo vệ khỏi sửa/xóa trái phép và chỉ cấp quyền đọc cho người có nhiệm vụ.

### 11.3. Tín hiệu cần theo dõi

Theo dõi các mẫu như một actor thử nhiều object ID liên tiếp, một user truy cập nhiều tenant, tỷ lệ `403`/`404` tăng đột biến, batch request có nhiều object bị từ chối hoặc tải tệp ngoài phạm vi thường lệ. Có thể đặt cảnh báo theo actor, tenant, endpoint và khoảng thời gian. Một lần truy cập bị từ chối có thể là lỗi người dùng bình thường; chuỗi hành vi lặp lại mới giúp nhận diện dò quét.

## 12. Kiểm thử object authorization

Kiểm thử cần chứng minh caller hợp lệ truy cập được object trong phạm vi của mình và caller khác bị từ chối. Hãy tạo tối thiểu hai người dùng thuộc hai tenant hoặc hai owner khác nhau, cùng một số object có quan hệ rõ ràng.

| Tình huống | Request/thao tác | Kết quả mong đợi |
|---|---|---|
| Owner đọc object của mình | A đọc order A | Cho phép |
| User khác đọc object của A | B thay ID sang order A | Từ chối theo chính sách |
| User cùng tenant nhưng không có quan hệ | C đọc ticket không được phân công | Từ chối nếu policy yêu cầu assignment |
| Truy cập chéo tenant | Tenant B gửi ID của tenant A | Từ chối; không lộ dữ liệu |
| Thay ID trong body | A gửi `invoiceId` của B | Từ chối |
| Ghép sai nested ID | `/users/A/orders/order-of-B` | Từ chối |
| Sửa object của người khác | B PATCH order A | Từ chối, dữ liệu không đổi |
| Xóa object ngoài phạm vi | B DELETE document A | Từ chối, dữ liệu không bị xóa |
| Gọi action nhạy cảm | User chỉ có read gọi approve/refund | Từ chối |
| Batch chứa ID hợp lệ và không hợp lệ | A gửi `[orderA, orderB]` | Đúng hợp đồng all-or-nothing hoặc partial; không xử lý vượt quyền |
| Search/export | A tìm kiếm hoặc export dữ liệu B | Không trả object hoặc metadata ngoài phạm vi |
| Quyền bị thu hồi trong lúc xử lý | Assignment đổi trước khi ghi | Request cũ không được ghi trái phép |

Nên có các lớp test:

- **Unit test:** kiểm tra policy cho từng action và loại quan hệ.
- **Integration test:** xác minh query scope, repository, transaction và mapping lỗi.
- **API test:** gửi request với nhiều danh tính và thay đổi ID ở path, query, body, nested resource và batch.
- **Regression test:** giữ lại test cho từng lỗi BOLA/IDOR từng được phát hiện để tránh tái diễn.

Test phải xác minh cả response lẫn trạng thái dữ liệu sau request bị từ chối. Ví dụ, PATCH bị từ chối không được âm thầm thay đổi một trường; DELETE bị từ chối không được xóa object; batch bị từ chối không được để lại một phần tác động ngoài hợp đồng.

## 13. Checklist review trước khi phát hành

- [ ] Đã liệt kê mọi object ID được đọc từ path, query, body, header, nested resource, batch hoặc GraphQL variables.
- [ ] Principal được tạo từ xác thực đáng tin cậy; không tin `userId`, `ownerId` hoặc `tenantId` do client khai báo.
- [ ] Mỗi action có kiểm tra quyền chức năng phù hợp.
- [ ] Mỗi object được kiểm tra quyền theo owner, tenant, assignment hoặc quan hệ được phép.
- [ ] Query list/search/count/export đã giới hạn theo phạm vi caller trước khi phân trang và tổng hợp.
- [ ] Nested resource xác minh quan hệ giữa object cha và object con.
- [ ] Batch kiểm tra từng object và có hợp đồng all-or-nothing/partial rõ ràng.
- [ ] GET, PUT, PATCH, DELETE và action nghiệp vụ đều có object authorization phù hợp.
- [ ] Request/response DTO giới hạn thuộc tính được phép ghi/đọc.
- [ ] Cập nhật đồng thời và tác vụ nền kiểm tra quyền tại thời điểm phù hợp.
- [ ] Cache không chia sẻ dữ liệu giữa caller có phạm vi quyền khác nhau.
- [ ] Lỗi từ chối không tiết lộ sự tồn tại hoặc dữ liệu nhạy cảm ngoài chính sách.
- [ ] Có audit/log và cảnh báo hành vi truy cập object bất thường.
- [ ] Có test chéo user, chéo tenant, nested ID, batch, read/write/delete và quyền bị thu hồi.

## Kết luận

Mỗi object ID từ request là một lựa chọn tài nguyên do client đề xuất, không phải bằng chứng rằng client có quyền truy cập tài nguyên đó. API phải xác minh quyền trên từng object cho từng action, dựa trên principal đáng tin cậy, tenant, owner, quan hệ và trạng thái nghiệp vụ. Đưa phạm vi quyền vào truy vấn, kiểm tra nested/batch/async path, kiểm soát cập nhật đồng thời và kiểm thử chéo danh tính giúp ngăn BOLA/IDOR một cách nhất quán trên toàn bộ API.
