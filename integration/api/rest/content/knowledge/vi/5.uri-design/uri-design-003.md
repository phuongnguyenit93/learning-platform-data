# Tài nguyên lồng nhau và giới hạn độ sâu

## Mục tiêu bài học

Trong chương **Thiết kế URI** của module **INTEGRATION_API_REST**, bài học này giúp bạn thiết kế đường dẫn thể hiện đúng quan hệ giữa các resource mà vẫn giữ hợp đồng API dễ hiểu và ổn định. Sau bài học, bạn có thể:

- Phân biệt quan hệ sở hữu với một liên kết thông thường giữa hai resource.
- Quyết định khi nào dùng URI lồng nhau, URI độc lập hoặc query parameter.
- Đặt giới hạn độ sâu phù hợp thay vì sao chép toàn bộ cấu trúc cơ sở dữ liệu vào đường dẫn.
- Kiểm tra quan hệ cha–con và quyền truy cập khi triển khai bằng Java/Spring hoặc công nghệ tương đương.

## 1. URI lồng nhau diễn đạt điều gì?

Giả sử hệ thống bán hàng có khách hàng và đơn hàng. Ta có thể cung cấp các URI:

```http
GET /customers/cus-17
GET /customers/cus-17/orders
GET /orders/ord-900
```

`/customers/cus-17/orders` biểu diễn một collection đơn hàng trong phạm vi khách hàng `cus-17`. Đường dẫn giúp người gọi hiểu ngữ cảnh của collection trước khi đọc tài liệu chi tiết.

Một URI lồng nhau cho phần tử cụ thể có thể là:

```http
GET /customers/cus-17/orders/ord-900
```

Khi hỗ trợ đường dẫn này, hợp đồng phải yêu cầu đồng thời hai điều kiện: đơn hàng có định danh `ord-900` và đơn hàng thuộc khách hàng `cus-17`. Máy chủ không được bỏ qua `cus-17` rồi trả bất kỳ đơn hàng nào có mã `ord-900`.

Đường dẫn có dấu `/` chỉ cung cấp cấu trúc cú pháp. Ý nghĩa nghiệp vụ như sở hữu, vòng đời, quyền truy cập hay xóa dây chuyền phải được API định nghĩa rõ; chúng không tự xuất hiện vì URI được lồng nhau.

### Quan hệ sở hữu và quan hệ liên kết

| Quan hệ | Đặc điểm cần xem xét | Thiết kế thường phù hợp |
| --- | --- | --- |
| Đơn hàng – dòng hàng | Dòng hàng chỉ có ý nghĩa trong một đơn hàng, mã dòng có thể chỉ duy nhất trong đơn đó | `/orders/{orderId}/items/{itemNo}` |
| Khách hàng – đơn hàng | Đơn hàng thường có định danh riêng; cần tra cứu, thanh toán và theo dõi độc lập | `/orders/{orderId}` và `/customers/{customerId}/orders` |
| Nhóm – người dùng | Một người có thể tham gia nhiều nhóm, người dùng vẫn tồn tại độc lập | `/groups/{groupId}/members` hoặc resource membership |
| Sản phẩm – nhà cung cấp | Có thể là quan hệ nhiều–nhiều, mỗi bên có vòng đời riêng | URI độc lập và truy vấn theo liên kết |

Các lựa chọn trên là ví dụ theo giả định nghiệp vụ, không phải quy tắc áp dụng cho mọi hệ thống. Nếu một “dòng hàng” thực tế có vòng đời độc lập để xử lý giao nhận, bạn cần đánh giá lại mô hình resource đó.

## 2. Khi nào nên lồng resource?

### 2.1. Định danh của resource con chỉ có ý nghĩa trong cha

Một dòng hàng có số thứ tự `3` có thể xuất hiện trong nhiều đơn hàng. Khi đó, cặp `(orderId, itemNo)` mới xác định duy nhất dòng hàng:

```http
GET /orders/ord-900/items/3
GET /orders/ord-901/items/3
```

Hai URI trên chỉ hai resource khác nhau. Nếu không có định danh toàn cục cho dòng hàng, `/items/3` là thiếu ngữ cảnh.

Với loại định danh này, URI lồng nhau là một cách biểu đạt tự nhiên. Máy chủ cần truy vấn bằng đủ hai giá trị, chẳng hạn:

```sql
SELECT order_id, item_no, product_id, quantity
FROM order_items
WHERE order_id = :orderId
  AND item_no = :itemNo;
```

Câu truy vấn minh họa cách xác định quan hệ cha–con. Việc kiểm tra quyền đọc đơn hàng vẫn là một bước riêng mà ứng dụng phải thực hiện.

### 2.2. Tập con theo cha là nhu cầu truy cập phổ biến

Một giao diện có màn hình chi tiết khách hàng và danh sách đơn hàng của họ có thể dùng:

```http
GET /customers/cus-17/orders?status=PAID&limit=20
```

Ở đây, `customerId` xác định phạm vi collection; `status` lọc tiếp trong phạm vi đó; `limit` điều khiển kích thước trang. Mọi bộ lọc phải kết hợp với phạm vi khách hàng, không được thay thế hoặc làm rộng phạm vi này.

Lồng collection không bắt buộc lồng URI của từng phần tử. Phản hồi có thể cung cấp liên kết đến URI độc lập của đơn hàng:

```json
{
  "items": [
    {
      "id": "ord-900",
      "status": "PAID",
      "links": {
        "self": "/orders/ord-900",
        "customer": "/customers/cus-17"
      }
    }
  ],
  "nextCursor": null
}
```

Trường `links` và `nextCursor` ở đây là quy ước của API minh họa. Cần mô tả chúng trong hợp đồng dữ liệu để client biết cách sử dụng.

### 2.3. Việc tạo resource cần ngữ cảnh cha

Ví dụ:

```http
POST /orders/ord-900/items
Content-Type: application/json

{
  "productId": "prd-42",
  "quantity": 2
}
```

`orderId` đã có trong path nên body không cần lặp lại thông tin này. Nếu vẫn nhận `orderId` trong body vì một yêu cầu tương thích, hợp đồng phải quy định cách xử lý khi hai giá trị khác nhau; không âm thầm chọn một giá trị tùy ý.

Khi tạo thành công một dòng hàng có số `3`, API có thể trả:

```http
HTTP/1.1 201 Created
Location: /orders/ord-900/items/3
Content-Type: application/json

{
  "orderId": "ord-900",
  "itemNo": 3,
  "productId": "prd-42",
  "quantity": 2
}
```

Lựa chọn lồng URI không tự quyết định tính idempotent của thao tác tạo. Nếu client gửi lại cùng yêu cầu `POST`, API phải có hợp đồng chống tạo trùng riêng khi nghiệp vụ yêu cầu.

## 3. Khi nào nên dùng URI độc lập?

Một resource có định danh toàn cục và nhiều điểm truy cập thường phù hợp với URI độc lập:

```http
GET /orders/ord-900
GET /orders?customerId=cus-17
GET /orders?status=PAID
```

Đơn hàng có thể được truy cập từ màn hình khách hàng, màn hình vận hành hoặc luồng thanh toán. Bắt mọi client mang theo `customerId` chỉ để đọc một `orderId` toàn cục có thể làm tăng sự phụ thuộc không cần thiết.

URI độc lập đặc biệt hữu ích khi:

- Resource được liên kết từ nhiều loại resource khác nhau.
- Quan hệ với cha có thể thay đổi trong vòng đời resource.
- Hệ thống cần tìm kiếm xuyên nhiều cha trong phạm vi người gọi được phép xem.
- Client thường biết trực tiếp định danh của resource con.

Ví dụ, một task có thể chuyển giữa các project. URI `/tasks/tsk-900` vẫn dùng được sau khi chuyển, trong khi URI `/projects/prj-42/tasks/tsk-900` gắn với project cũ cần có chính sách xử lý riêng.

Sự ổn định này phụ thuộc vào mô hình định danh. Nếu mã task chỉ duy nhất trong từng project, không thể đơn giản bỏ `projectId` khỏi URI mà không bổ sung một định danh đủ duy nhất.

## 4. Giới hạn độ sâu: đếm quan hệ, không chỉ đếm dấu `/`

Xem đường dẫn sau:

```text
/organizations/org-17/projects/prj-42/tasks/tsk-900/comments/cmt-8/attachments/att-6
```

Nó đi qua chuỗi organization → project → task → comment → attachment. Nếu đã chọn organization làm resource gốc, đường dẫn này có bốn tầng quan hệ con.

Trong bài này, **một tầng lồng nhau** là một quan hệ cha–con được thêm vào đường dẫn resource. Các tiền tố như `/api` hoặc `/v1` không tính vào số tầng quan hệ nghiệp vụ:

| URI | Số tầng quan hệ tính theo cách trên |
| --- | --- |
| `/api/v1/orders/ord-900` | 0 |
| `/api/v1/orders/ord-900/items/3` | 1 |
| `/api/v1/projects/prj-42/tasks/tsk-900/comments` | 2 |

HTTP không quy định rằng REST API chỉ được có tối đa hai tầng lồng nhau. Đó là hướng dẫn thiết kế của nhóm phát triển, không phải giới hạn giao thức. Giới hạn chiều dài URI mà máy chủ hoặc proxy hỗ trợ cũng là một vấn đề khác với số quan hệ nghiệp vụ trong path.

Một quy ước thực dụng cho API mới là:

- Ưu tiên URI độc lập hoặc một tầng cha–con.
- Chấp nhận hai tầng khi từng định danh cha thực sự cần thiết và có thể giải thích rõ.
- Khi muốn thêm tầng thứ ba, xem lại mô hình định danh, nhu cầu điều hướng và khả năng dùng filter hoặc link.

### Vì sao lồng quá sâu gây khó khăn?

**Client phải biết quá nhiều định danh.** Muốn tải attachment, client phải thu thập cả organization, project, task và comment ngay cả khi `att-6` đã đủ duy nhất.

**Quan hệ tổ tiên có thể thay đổi.** Di chuyển task sang project khác làm thay đổi cả chuỗi đường dẫn liên quan nếu API coi toàn bộ chuỗi là định danh chính.

**Kiểm tra tính nhất quán phức tạp hơn.** Máy chủ phải xác nhận project thuộc organization, task thuộc project, comment thuộc task và attachment thuộc comment. Chỉ kiểm tra resource cuối là chưa đủ để đáp ứng hợp đồng của path.

**Hợp đồng và kiểm thử phình ra.** Nhiều cha tạo thêm các trường hợp không tồn tại, sai quan hệ, không đủ quyền và thay đổi quan hệ giữa lúc xử lý yêu cầu.

**Dễ nhầm mô hình API với sơ đồ bảng.** Chuỗi khóa ngoại trong cơ sở dữ liệu không buộc phải trở thành chuỗi segment trong URI.

Đường dẫn sâu không mặc nhiên làm truy vấn cơ sở dữ liệu chậm hơn. Hiệu năng còn phụ thuộc vào truy vấn, chỉ mục, số lần gọi dịch vụ và cách kiểm tra quyền. Vấn đề thiết kế trước hết là sự phụ thuộc và độ phức tạp của hợp đồng.

## 5. Ba cách rút gọn URI mà vẫn giữ ngữ nghĩa

### 5.1. Giữ URI chính ổn định và dùng link để điều hướng

Nếu task, comment và attachment đều có định danh toàn cục, ta có thể chọn:

```http
GET /tasks/tsk-900
GET /comments/cmt-8
GET /attachments/att-6
```

Mỗi biểu diễn trả thêm liên kết đến resource liên quan:

```json
{
  "id": "cmt-8",
  "taskId": "tsk-900",
  "text": "Bổ sung tài liệu triển khai",
  "links": {
    "self": "/comments/cmt-8",
    "task": "/tasks/tsk-900",
    "attachments": "/comments/cmt-8/attachments"
  }
}
```

Client có thể điều hướng qua các liên kết mà không cần tự ghép đầy đủ cây tổ tiên. Resource vẫn có quan hệ nghiệp vụ dù URI chính không mang tất cả quan hệ đó.

### 5.2. Dùng query parameter để truy vấn collection

Các truy vấn sau có thể phục vụ các nhu cầu khác nhau:

```http
GET /tasks?projectId=prj-42&status=OPEN
GET /comments?taskId=tsk-900
GET /attachments?commentId=cmt-8
```

Query parameter phù hợp với điều kiện tìm kiếm và lọc. API cần mô tả kiểu dữ liệu, điều kiện kết hợp, phân trang và tập dữ liệu mà người gọi có quyền xem.

Lưu ý: bỏ `projectId` khỏi query không được khiến người gọi nhìn thấy mọi task ngoài quyền hạn. Phạm vi bảo mật phải do máy chủ xác lập, không phụ thuộc vào việc client có gửi filter hay không.

Đường dẫn `/projects/{projectId}/tasks` và `/tasks?projectId={projectId}` đều có thể hợp lý. Chúng không bắt buộc có cùng hành vi khi project không tồn tại:

| Trường hợp | Hợp đồng có thể chọn |
| --- | --- |
| `/projects/prj-42/tasks`, project tồn tại nhưng không có task phù hợp | `200 OK` với collection rỗng |
| `/projects/prj-missing/tasks`, project không tồn tại | `404 Not Found` nếu API yêu cầu cha phải tồn tại |
| `/tasks?projectId=prj-missing`, filter hợp lệ nhưng không khớp dữ liệu | `200 OK` với collection rỗng nếu filter được hiểu như điều kiện tìm kiếm |
| Query có giá trị sai định dạng | `400 Bad Request` theo hợp đồng validation |

API có thể chọn kiểm tra tồn tại cho filter và trả lỗi khác; điều quan trọng là công bố quy ước nhất quán. Với tài nguyên không được phép xem, tiếp tục áp dụng chính sách che giấu hoặc báo thiếu quyền đã chọn.

### 5.3. Biến quan hệ nhiều–nhiều thành resource khi cần

Giả sử người dùng tham gia nhiều nhóm, và việc tham gia có `role`, `joinedAt`, trạng thái hoặc quy trình phê duyệt. Quan hệ đó có thể trở thành resource membership:

```http
POST /groups/grp-7/memberships
GET /groups/grp-7/memberships
GET /memberships/mem-81
```

Biểu diễn membership:

```json
{
  "id": "mem-81",
  "groupId": "grp-7",
  "userId": "usr-23",
  "role": "EDITOR",
  "joinedAt": "2026-01-15T08:00:00Z"
}
```

`DELETE /memberships/mem-81` có thể được định nghĩa là chấm dứt quan hệ thành viên; nó không đồng nghĩa xóa user `usr-23`. Hợp đồng phải phân biệt rõ việc xóa quan hệ với việc xóa một đầu của quan hệ.

Nếu membership không có định danh riêng và cặp `(groupId, userId)` đã đủ duy nhất, `/groups/{groupId}/members/{userId}` cũng có thể là lựa chọn phù hợp. Không cần tạo thêm resource chỉ để giảm một segment trong URI.

## 6. Chọn URI chính và xử lý các đường dẫn phụ

Một API có thể cần cả:

```http
GET /customers/cus-17/orders/ord-900
GET /orders/ord-900
```

Nếu hai URI trả biểu diễn của cùng một đơn hàng, nên chọn URI chính để dùng nhất quán trong `self`, `Location` khi tạo resource và tài liệu API. Ví dụ, chọn `/orders/{orderId}` làm URI chính, còn URI dưới customer là đường truy cập theo ngữ cảnh.

Các lựa chọn triển khai gồm:

1. Chỉ hỗ trợ URI phần tử độc lập, dùng URI lồng nhau cho collection.
2. Hỗ trợ cả hai nhưng dùng chung logic nghiệp vụ và công bố URI chính.
3. Dùng redirect cho URI phụ nếu hệ sinh thái client hỗ trợ và ngữ nghĩa của phương thức được xử lý đúng.

Không nên tự động chuyển mọi phương thức qua redirect mà chưa xác định hành vi client. Một redirect cho `GET` và việc chuyển tiếp một yêu cầu ghi cần được đánh giá theo hợp đồng HTTP tương ứng.

Cache cũng cần được xem xét: nhiều đường dẫn cho cùng nội dung có thể tạo nhiều mục cache. Chọn URI chính giúp giảm các đường truy cập trùng lặp; nó không tự làm mọi cache hiểu hai URI là cùng resource. Với dữ liệu cá nhân, chính sách cache còn phải xét thông tin xác thực và phạm vi chia sẻ.

Nếu resource đổi cha, cần xác định hành vi của URI cũ. Ví dụ, sau khi task chuyển project, `/tasks/tsk-900` có thể giữ nguyên; `/projects/prj-old/tasks/tsk-900` không còn khớp quan hệ và phải được xử lý theo chính sách đã công bố, thay vì tiếp tục trả dữ liệu chỉ vì `taskId` còn tồn tại.

## 7. Kiểm tra cha–con và quyền truy cập

Xét yêu cầu:

```http
GET /customers/cus-17/orders/ord-901
```

Nếu `ord-901` thuộc `cus-99`, máy chủ không được trả nó dưới đường dẫn của `cus-17`.

Một thứ tự xử lý dễ hiểu là:

1. Xác thực người gọi theo cơ chế của API.
2. Kiểm tra định dạng các path parameter.
3. Kiểm tra quyền truy cập ngữ cảnh cha, gồm chính sách xử lý cha không tồn tại.
4. Truy vấn resource con trong đúng phạm vi cha.
5. Áp dụng thêm quyền trên resource con nếu nghiệp vụ yêu cầu.
6. Trả biểu diễn hoặc lỗi theo hợp đồng.

Đây là luồng logic, không bắt buộc mỗi bước phải là một truy vấn riêng. Có thể kết hợp điều kiện tồn tại, tenant, quan hệ và quyền trong truy vấn hoặc policy phù hợp.

### Lồng URI không ngăn được truy cập trái phép

Người gọi có thể thay `customerId`, `orderId` hoặc đồng thời thay cả hai. UUID khó đoán cũng không thay thế kiểm tra quyền. Máy chủ phải ràng buộc người gọi với phạm vi được phép và ràng buộc resource con với cha đã yêu cầu.

Đặc biệt trong hệ thống nhiều tenant, `tenantId` trong path là dữ liệu do client cung cấp. Nó cần được đối chiếu với quyền của người gọi; không được coi nó là bằng chứng xác thực.

Với collection, phân trang, tổng số phần tử và cursor đều phải nằm trong phạm vi đã cho phép. Nếu trang sau dùng cursor làm mất điều kiện `customerId`, một URI nhìn đúng vẫn có thể làm lộ dữ liệu.

### Mã trạng thái phải có ý nghĩa nhất quán

| Tình huống | Cách phản hồi có thể áp dụng |
| --- | --- |
| Parent hợp lệ, child tồn tại và đúng quan hệ, người gọi có quyền | `200 OK` cho yêu cầu đọc thành công |
| Parent hợp lệ, collection không có phần tử phù hợp | `200 OK` với collection rỗng |
| Child không tồn tại trong parent được yêu cầu | `404 Not Found` |
| Người gọi đã xác thực nhưng không có quyền | `403 Forbidden`, hoặc `404 Not Found` theo chính sách che giấu sự tồn tại |
| Path parameter sai định dạng | `400 Bad Request` theo hợp đồng validation |

Nếu API có cơ chế xác thực, yêu cầu thiếu hoặc có thông tin xác thực không hợp lệ thường được xử lý bằng `401 Unauthorized` cùng challenge phù hợp với cơ chế đó. Cách tổ chức URI không thay đổi các nghĩa cơ bản của mã trạng thái.

Khi chọn che giấu sự tồn tại bằng `404`, cần áp dụng chính sách nhất quán cho các đường truy cập liên quan và tránh đưa chi tiết nhạy cảm vào body lỗi.

## 8. Ví dụ Java/Spring: định danh con theo phạm vi cha

Ví dụ sau minh họa đọc một dòng hàng. Giả định số dòng chỉ duy nhất trong từng đơn hàng, nên URI phần tử là `/orders/{orderId}/items/{itemNo}`.

Các thành phần được tách để thấy rõ trách nhiệm:

```java
import java.util.Optional;

record OrderItemView(
        String orderId,
        int itemNo,
        String productId,
        int quantity
) {}

interface OrderAccess {
    // Kiểm tra đơn hàng tồn tại và người gọi hiện tại được đọc đơn này.
    // Nếu ứng dụng dùng tenant, kiểm tra cả phạm vi tenant tại đây.
    void requireReadableOrder(String orderId);
}

interface OrderItemQuery {
    Optional<OrderItemView> findByOrderIdAndItemNo(
            String orderId,
            int itemNo
    );
}
```

Service giữ nguyên cả hai điều kiện định danh:

```java
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
class OrderItemService {
    private final OrderAccess orderAccess;
    private final OrderItemQuery itemQuery;

    OrderItemService(OrderAccess orderAccess, OrderItemQuery itemQuery) {
        this.orderAccess = orderAccess;
        this.itemQuery = itemQuery;
    }

    OrderItemView getItem(String orderId, int itemNo) {
        if (orderId.isBlank() || itemNo < 1) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Invalid order item identifier"
            );
        }

        orderAccess.requireReadableOrder(orderId);

        return itemQuery.findByOrderIdAndItemNo(orderId, itemNo)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND,
                        "Order item not found"
                ));
    }
}
```

Controller ánh xạ trực tiếp hợp đồng URI:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders/{orderId}/items")
class OrderItemController {
    private final OrderItemService service;

    OrderItemController(OrderItemService service) {
        this.service = service;
    }

    @GetMapping("/{itemNo}")
    OrderItemView getItem(
            @PathVariable("orderId") String orderId,
            @PathVariable("itemNo") int itemNo
    ) {
        return service.getItem(orderId, itemNo);
    }
}
```

Các đoạn mã dùng cú pháp Java có hỗ trợ `record` và là các thành phần minh họa, chưa phải một ứng dụng chạy độc lập. Cần triển khai hai interface, cấu hình xác thực và chuẩn hóa body lỗi của API. Nếu mỗi dòng hàng có chính sách truy cập riêng, phải bổ sung kiểm tra quyền đó trước khi trả dữ liệu.

Không thay lời gọi truy vấn bằng `findByItemNo(itemNo)`: số dòng `3` không duy nhất trên toàn hệ thống. Cũng không dùng `findById(childId)` rồi bỏ qua quan hệ trong path khi thiết kế một loại child có định danh toàn cục.

Nếu có thể thay đổi chủ sở hữu hoặc quyền đồng thời với yêu cầu đọc, việc kiểm tra quyền và lấy dữ liệu cần có chiến lược nhất quán phù hợp, chẳng hạn truy vấn có kèm phạm vi quyền hoặc ranh giới giao dịch cần thiết. Độ sâu URI không giải quyết được vấn đề đồng thời này.

## 9. Hợp đồng OpenAPI và kiểm thử cần thể hiện điều gì?

OpenAPI không chỉ liệt kê tên biến trong path. Phần mô tả cần nói rõ phạm vi định danh và quan hệ bắt buộc giữa các biến:

```yaml
paths:
  /orders/{orderId}/items/{itemNo}:
    get:
      operationId: getOrderItem
      summary: Đọc một dòng hàng trong đơn hàng
      description: >-
        itemNo chỉ duy nhất trong phạm vi orderId.
        Người gọi phải được phép đọc đơn hàng.
        Trả 404 nếu không tìm thấy dòng trong đơn hàng đã yêu cầu.
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
        - name: itemNo
          in: path
          required: true
          schema:
            type: integer
            minimum: 1
      responses:
        '200':
          description: Dòng hàng thuộc đơn hàng được yêu cầu
        '400':
          description: Định danh không hợp lệ
        '404':
          description: Không tìm thấy tài nguyên theo chính sách của API
```

Đây là đoạn trích mô tả một operation, chưa phải tài liệu OpenAPI đầy đủ. Khi hoàn thiện hợp đồng, cần thêm schema phản hồi, schema lỗi, cơ chế bảo mật và các mã lỗi phù hợp với policy đã chọn.

Các tình huống kiểm thử quan trọng:

| Dữ liệu và hành động | Kết quả cần xác minh |
| --- | --- |
| Đơn `ord-900` có dòng `3`, người gọi có quyền | Trả đúng dòng thuộc `ord-900` |
| Đơn `ord-901` cũng có dòng `3` | Hai yêu cầu trả hai dòng tương ứng, không lẫn dữ liệu |
| Dòng chỉ tồn tại ở đơn khác | Không trả nhầm dòng qua đơn được yêu cầu |
| Người gọi không được đọc đơn | Không trả nội dung dòng hàng |
| `itemNo=0` hoặc `itemNo=abc` | Xử lý lỗi định dạng hoặc miền giá trị theo hợp đồng |
| Collection của một đơn tồn tại nhưng chưa có dòng | Trả collection rỗng theo quy ước |
| Lấy trang tiếp theo của collection | Giữ nguyên phạm vi đơn hàng và quyền truy cập |
| Có cả URI chính và URI phụ cho cùng resource | Policy truy cập và dữ liệu nghiệp vụ nhất quán |

Kiểm thử cha–con sai quan hệ đặc biệt quan trọng khi child có định danh toàn cục: một triển khai chỉ tra theo child ID rất dễ trả dữ liệu thành công dù parent trong path không khớp.

## 10. Quy trình chọn đường dẫn cho một quan hệ mới

Khi thêm resource, hãy đi theo thứ tự sau:

1. **Xác định resource và định danh.** Child có mã toàn cục hay chỉ duy nhất trong parent?
2. **Xác định ý nghĩa của quan hệ.** Đây là sở hữu bắt buộc, ngữ cảnh điều hướng hay liên kết nhiều–nhiều?
3. **Xem xét vòng đời.** Child có thể đổi parent, xuất hiện ở nhiều parent hoặc tồn tại khi parent bị xóa không?
4. **Liệt kê nhu cầu truy cập.** Client thường đọc qua parent, qua child ID hay tìm kiếm xuyên nhiều parent?
5. **Chọn URI chính.** Dùng đủ ngữ cảnh để định danh, ưu tiên đường dẫn ổn định.
6. **Thêm collection và filter cần thiết.** Không thêm mọi tổ tiên chỉ để phản ánh cấu trúc dữ liệu nội bộ.
7. **Kiểm tra độ sâu và quyền.** Mỗi parent trong path phải có lý do và được kiểm tra đúng ý nghĩa.
8. **Ghi hợp đồng.** Mô tả quan hệ, mã lỗi, phân trang, link và hành vi khi đổi parent.

Áp dụng cho hệ thống quản lý công việc với ID toàn cục:

| Nhu cầu | URI đề xuất | Lý do |
| --- | --- | --- |
| Đọc task cụ thể | `/tasks/{taskId}` | Giữ định danh ổn định khi task chuyển project |
| Liệt kê task của project | `/projects/{projectId}/tasks` | Collection có ngữ cảnh project rõ ràng |
| Tìm task theo nhiều điều kiện | `/tasks?projectId={projectId}&status=OPEN` | Hỗ trợ bộ lọc kết hợp trên collection được phép xem |
| Liệt kê comment của task | `/tasks/{taskId}/comments` | Một tầng quan hệ đủ cho nhu cầu điều hướng |
| Đọc attachment có ID toàn cục | `/attachments/{attachmentId}` | Không cần mọi tổ tiên để xác định attachment |

## 11. Bài thực hành

Bạn có mô hình `organization → project → task → comment`, với các giả định:

- Project chỉ thuộc một organization.
- Task có ID toàn cục và có thể chuyển giữa các project trong cùng organization.
- Comment có ID toàn cục và thuộc một task.
- Người gọi chỉ được xem dữ liệu trong organization được cấp quyền.

Hãy thiết kế URI cho việc đọc task, liệt kê task trong project, đọc comment và liệt kê comment của task. Sau đó mô tả cách máy chủ xử lý yêu cầu dùng đúng `taskId` nhưng sai `projectId`.

Một hướng giải quyết là chọn `/tasks/{taskId}` và `/comments/{commentId}` làm URI chính, đồng thời cung cấp `/projects/{projectId}/tasks` và `/tasks/{taskId}/comments` để điều hướng collection. Nếu vẫn hỗ trợ `/projects/{projectId}/tasks/{taskId}`, máy chủ phải xác nhận task thuộc project đó và người gọi có quyền trong organization liên quan.

Sau khi task chuyển project, URI chính của task giữ nguyên. Collection của project cũ không còn chứa task; collection của project mới có thể chứa task theo bộ lọc và quyền hiện hành. Cơ chế cache hoặc dữ liệu đã tải ở client cần có chính sách cập nhật tương ứng.

Điểm cần bảo vệ trong thiết kế là: **URI mang đủ ngữ cảnh cần thiết để định danh và điều hướng, còn máy chủ chịu trách nhiệm xác minh quan hệ, quyền truy cập và tính nhất quán của dữ liệu.**
