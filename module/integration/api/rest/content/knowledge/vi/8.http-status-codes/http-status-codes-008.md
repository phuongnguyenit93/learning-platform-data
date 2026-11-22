# 404, 410 và chính sách tiết lộ sự tồn tại của tài nguyên

## 1. Vì sao cùng một URI lại có thể trả về 404 hoặc 410?

Trong REST API, URI định danh một **resource** (tài nguyên), còn mã trạng thái HTTP cho biết máy chủ đã xử lý yêu cầu như thế nào. Với resource không thể truy cập, hai câu hỏi khác nhau thường bị trộn lẫn:

1. **Tài nguyên có còn được cung cấp tại URI này không?** Chẳng hạn một bài viết đã xóa, một đường dẫn sai hoặc tài nguyên vừa được chuyển trạng thái.
2. **Máy chủ có nên tiết lộ rằng tài nguyên từng tồn tại hoặc đang tồn tại không?** Chẳng hạn đơn hàng của khách khác, tài liệu nội bộ, tệp riêng tư hoặc tài khoản thuộc tenant khác.

Mã **404 Not Found** và **410 Gone** trả lời những câu hỏi này theo các mức thông tin khác nhau. Lựa chọn đúng ảnh hưởng đến hợp đồng API, cache, bảo mật, trải nghiệm client và cách ứng dụng kiểm thử lỗi.

Đây là một bài trong chương **Mã trạng thái** của module **INTEGRATION_API_REST**. Nội dung bám vào thiết kế REST theo resource/URI, phương thức và trạng thái HTTP; diễn giải cách lập hợp đồng dữ liệu, phân quyền, cache, tài liệu OpenAPI và kiểm thử với **Java/Spring** hoặc nền tảng tương đương.

**Kết quả học tập:** sau bài này, bạn có thể phân biệt chính xác 404/410 với 401/403; thiết kế chính sách không làm lộ sự tồn tại tài nguyên; xử lý tài nguyên đã xóa; cấu hình cache phù hợp; và kiểm thử nhất quán status, header, body ở các tình huống bảo mật.

## 2. Ý nghĩa HTTP chính xác của 404 và 410

### 2.1. 404 Not Found

Theo ngữ nghĩa HTTP được mô tả trong **RFC 9110, mục 15.5.5**, 404 nghĩa là máy chủ gốc **không tìm thấy biểu diễn hiện tại của tài nguyên đích, hoặc không sẵn sàng tiết lộ rằng biểu diễn đó tồn tại**. Trạng thái này **không cho biết** tình trạng thiếu biểu diễn là tạm thời hay vĩnh viễn.

Ví dụ:

- Client gọi một URI chưa từng tồn tại, như GET /v1/articles/unknown-slug.
- Một tài nguyên đang ở trạng thái nháp, chưa được phép công khai.
- Một tài nguyên chỉ tồn tại cho tenant A nhưng tenant B cố truy cập.
- Một tệp riêng tư đã bị xóa; API không muốn xác nhận rằng tệp từng tồn tại.
- Server không biết liệu resource đã bị loại bỏ vĩnh viễn hay chỉ tạm thời không truy cập được.

Điểm quan trọng: **404 không có nghĩa chắc chắn rằng bản ghi không có trong database**. Nó có thể là kết quả của chính sách hiển thị tài nguyên sau khi đã kiểm tra quyền.

### 2.2. 410 Gone

Theo **RFC 9110, mục 15.5.11**, 410 cho biết việc truy cập tài nguyên đích **không còn khả dụng tại máy chủ gốc và tình trạng đó có khả năng là vĩnh viễn**. 410 dành cho trường hợp máy chủ **biết** tài nguyên đã bị loại bỏ lâu dài. Nếu không biết hoặc không có cơ chế xác định việc loại bỏ là lâu dài, nên ưu tiên 404.

Ví dụ phù hợp khi resource được công khai:

- Một API công bố rằng tài liệu công khai theo URI cũ đã bị thu hồi vĩnh viễn.
- Trang sự kiện công khai bị loại bỏ và sẽ không được phục vụ lại tại URI đó.
- Hợp đồng API dành cho resource công khai định nghĩa một tombstone xác nhận tài nguyên đã ngừng tồn tại tại URI cũ.

410 truyền thêm một dữ kiện so với 404: **URI đó từng có một tài nguyên mà máy chủ biết đã bị gỡ bỏ lâu dài**. Do đó, 410 không thích hợp cho mọi resource đã xóa, nhất là resource riêng tư.

### 2.3. Bảng đối chiếu

| Tiêu chí | 404 Not Found | 410 Gone |
|---|---|---|
| Nghĩa chính | Không có biểu diễn hiện tại **hoặc không tiết lộ** sự tồn tại | Tài nguyên không còn khả dụng và **có khả năng bị loại bỏ lâu dài** |
| Cần biết lịch sử resource? | Không | Có, để xác định tình trạng gỡ bỏ lâu dài |
| Tiết lộ việc từng tồn tại? | Không nhất thiết | Có thể tiết lộ mạnh hơn |
| Tài nguyên thuộc tenant khác | Thường phù hợp nếu dùng chính sách ẩn sự tồn tại | **Không nên** trả 410 theo lịch sử riêng tư |
| Trang/tài liệu công khai đã gỡ lâu dài | Có thể dùng, nếu chưa xác minh tính vĩnh viễn | Thích hợp nếu chính sách đã xác định |
| Cache | Có thể cache theo heuristic nếu không có chỉ thị khác | Cũng có thể cache theo heuristic nếu không có chỉ thị khác |
| Client nên làm gì? | Kiểm tra URI, quyền, điều kiện hiển thị; không tự suy ra vĩnh viễn | Ngừng tham chiếu URI cũ hoặc tìm đường thay thế theo hợp đồng |

**Không nên diễn giải 410 là một lời bảo đảm kỹ thuật rằng tài nguyên không bao giờ quay lại**, hoặc 404 là bằng chứng tài nguyên chưa từng tồn tại. API chỉ công bố trạng thái theo **kiến thức và chính sách ở thời điểm trả lời**.

## 3. Liên hệ với 401, 403 và các mã dễ nhầm

| Mã | Ý nghĩa trong thiết kế API | Ví dụ |
|---|---|---|
| **400 Bad Request** | Request sai cú pháp hoặc dữ liệu đầu vào không hợp lệ | orderId phải là UUID nhưng client gửi chuỗi sai định dạng |
| **401 Unauthorized** | Thiếu thông tin xác thực hợp lệ cho tài nguyên được bảo vệ; response phải có thử thách xác thực phù hợp | Không gửi access token, token hết hạn hoặc không hợp lệ |
| **403 Forbidden** | Server hiểu yêu cầu nhưng từ chối thực hiện; có thể dùng 404 để che giấu resource bị cấm | Người dùng đã xác thực không có quyền xuất báo cáo của dự án |
| **404 Not Found** | Không có biểu diễn hiện tại hoặc chính sách không tiết lộ resource | Đơn hàng không tồn tại **hoặc không thuộc tenant đang gọi** |
| **410 Gone** | Resource không còn khả dụng và có khả năng đã bị gỡ lâu dài | Một bài viết công khai được đánh dấu gỡ bỏ vĩnh viễn |
| **409 Conflict** | Yêu cầu xung đột với trạng thái hiện tại của resource | Thao tác cập nhật không thể thực hiện ở trạng thái nghiệp vụ hiện tại |
| **301/308 redirect** | Resource đã có URI thay thế và hệ thống chủ động điều hướng theo hợp đồng | Tài liệu công khai chuyển sang URI chuẩn mới |

**401 khác 403 về xác thực.** 401 yêu cầu một **WWW-Authenticate** challenge thích hợp; 403 thường dùng khi máy chủ đã có đủ thông tin để đánh giá rằng thao tác bị từ chối. Nếu một endpoint yêu cầu Bearer token, thiếu token thường được xử lý bằng 401 từ tầng bảo mật trước khi API đi tra cứu resource.

**403 và 404 có vùng giao nhau về bảo mật:** RFC 9110 cho phép máy chủ muốn che giấu sự tồn tại của tài nguyên bị cấm trả 404 thay 403. Tuy nhiên, **không nên mặc định đổi mọi 403 thành 404**: nhiều lỗi quyền trên chức năng mà người dùng đã biết, như thiếu scope xuất báo cáo của chính mình, sẽ dễ xử lý hơn với 403.

**410 không phải lựa chọn để báo sai quyền.** Nếu tài khoản khác thử truy cập một tài liệu đã bị xóa của tenant A, trả 410 có thể tiết lộ tài liệu ấy từng tồn tại; chính sách ẩn nên tiếp tục trả 404.

## 4. Xác định chính sách tiết lộ sự tồn tại

Tính hiện hữu của một resource cũng là **thông tin**. Ví dụ, chỉ cần biết URI /v1/patients/123 hoặc /v1/orders/991 có tồn tại có thể làm lộ chuyện riêng tư, khách hàng, lịch sử đơn hàng hoặc cấu trúc dữ liệu nội bộ, dù response không chứa dữ liệu.

### 4.1. Phân loại resource

| Nhóm resource | Ví dụ | Chính sách gợi ý |
|---|---|---|
| **Công khai** | Bài viết phát hành, tài liệu API công khai | 200 khi đang có; 404 khi không rõ; 410 khi biết đã gỡ lâu dài |
| **Riêng tư theo owner/tenant** | Đơn hàng, hóa đơn, file của người dùng | 404 chung cho ID không có và ID không được phép nhìn thấy; không phát 410 dựa trên lịch sử tài nguyên của tenant khác |
| **Chức năng có quyền rõ ràng** | Export đơn của chính mình, quản lý thành viên nhóm | 403 nếu người dùng đã xác thực, biết resource đó nhưng thiếu quyền thao tác; 404 nếu ngay cả sự tồn tại phải ẩn |
| **Resource nội bộ không công khai** | Bản nháp, khóa chia sẻ bí mật, token nội bộ | Không lộ trạng thái riêng qua 403/410; kiểm tra quyền và trả phản hồi tối thiểu |
| **Resource chuyển URI** | Trang hướng dẫn công khai đổi slug | 301/308 nếu muốn điều hướng lâu dài; 410 nếu URI cũ đã ngừng và không công bố hướng thay thế |

### 4.2. Ma trận quyết định cho API đơn hàng

Giả sử GET /v1/orders/{orderId} yêu cầu Bearer token; resource chỉ hiển thị cho người dùng thuộc đúng tenant và có quyền xem.

| Tình huống | Trạng thái | Có tiết lộ tồn tại đơn? |
|---|---|---|
| Không có token ở endpoint bắt buộc xác thực | **401** | Chưa tra cứu ID |
| Token sai hoặc hết hạn | **401** | Chưa tra cứu ID |
| Token hợp lệ, ID không tồn tại | **404** | Không |
| Token hợp lệ, ID thuộc tenant khác | **404** | Không |
| Token hợp lệ, ID thuộc tenant hiện tại nhưng resource bị ẩn theo hợp đồng | **404** | Không |
| Token hợp lệ, resource thuộc tenant và được phép xem | **200** | Có, cho đúng người |
| Token hợp lệ, resource thuộc tenant nhưng thiếu scope cho hành động phụ và việc hiện hữu được phép tiết lộ | **403** | Có, trong phạm vi được cho phép |
| Resource của tenant khác từng bị xóa lâu dài | **404** | Không; tránh tiết lộ lịch sử qua 410 |

Một chính sách tốt cần được **viết thành hợp đồng và áp dụng nhất quán** trên GET, HEAD, route của resource con, endpoint tìm kiếm, truy vấn hàng loạt và các thao tác liên quan. Không thể chỉ “ẩn” ở endpoint GET trong khi DELETE hoặc endpoint kiểm tra tồn tại lại trả thông tin khác.

### 4.3. Luồng quyết định

~~~mermaid
flowchart TD
  A["Request tới resource"] --> B{"Endpoint cần xác thực?"}
  B -->|Có| C{"Xác thực hợp lệ?"}
  C -->|Không| U["401 + WWW-Authenticate"]
  C -->|Có| D["Tra cứu trong phạm vi được phép xem"]
  B -->|Không| P["Tra cứu resource công khai"]
  D --> E{"Tìm thấy resource được phép thấy?"}
  E -->|Không| N["404 chung"]
  E -->|Có| F{"Có quyền thực hiện thao tác?"}
  F -->|Không, được phép tiết lộ| X["403"]
  F -->|Không, cần che giấu| N
  F -->|Có| OK["200 hoặc mã thành công phù hợp"]
  P --> Q{"Có biểu diễn công khai hiện tại?"}
  Q -->|Có| OK
  Q -->|Không| R{"Biết đã gỡ lâu dài và được phép công bố?"}
  R -->|Có| G["410"]
  R -->|Không| N
~~~

Sơ đồ dành cho **đường đọc một resource**. Với POST/PUT/DELETE hoặc thao tác đặc biệt, trạng thái thành công và xung đột phải dựa trên semantics phương thức và hợp đồng resource; không luôn là 200.

## 5. Phân biệt ba trường hợp dễ gây nhầm

### 5.1. Resource không tồn tại hoặc không xác định

~~~http
GET /v1/articles/slug-khong-co HTTP/1.1
Host: api.example.com
Accept: application/json

HTTP/1.1 404 Not Found
Content-Type: application/problem+json
Cache-Control: public, max-age=60

{
  "type": "https://api.example.com/problems/not-found",
  "title": "Not Found",
  "status": 404,
  "detail": "Không tìm thấy tài nguyên."
}
~~~

Đây là endpoint **công khai**, nên có thể chọn cache 404 trong thời gian ngắn nếu việc xuất hiện bài viết mới không đòi hỏi cập nhật ngay. Giá trị 60 giây chỉ là ví dụ. Không được dùng cache công khai như trên cho response phụ thuộc danh tính người gọi.

### 5.2. Resource công khai được xác nhận đã gỡ bỏ lâu dài

~~~http
GET /v1/articles/chuong-trinh-cu HTTP/1.1
Host: api.example.com

HTTP/1.1 410 Gone
Content-Type: application/problem+json
Cache-Control: public, max-age=300

{
  "type": "https://api.example.com/problems/gone",
  "title": "Gone",
  "status": 410,
  "detail": "Tài liệu này không còn được cung cấp."
}
~~~

410 phù hợp nếu máy chủ có **hồ sơ gỡ bỏ đáng tin cậy**, URI từng công khai và việc thông báo đó không xâm phạm quyền riêng tư. Nếu tài liệu đã đổi địa chỉ và hệ thống muốn giữ đường dẫn cũ hoạt động, cân nhắc redirect phù hợp hơn.

### 5.3. Resource riêng tư thuộc người khác

~~~http
GET /v1/orders/0db852ab-87ab-4097-b58a-632fb0b9c229 HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>

HTTP/1.1 404 Not Found
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/not-found",
  "title": "Not Found",
  "status": 404,
  "detail": "Không tìm thấy tài nguyên."
}
~~~

Response phải giống về **mã, loại body và chính sách header** đối với cùng API khi ID thực sự không tồn tại hoặc ID thuộc tenant khác. Không cho client suy ra tình trạng qua message kiểu “Đơn hàng tồn tại nhưng không thuộc tài khoản của bạn”.

## 6. Khi tài nguyên đã xóa: có nhất thiết trả 410?

**Không.** “Đã xóa” là trạng thái của **dữ liệu nội bộ**, còn 404/410 là thông tin mà **API chủ động công bố** tại URI. Xóa mềm, ẩn khỏi danh sách, hết hạn, lưu trữ dài hạn hoặc gỡ tệp có thể có chính sách khác nhau.

| Vòng đời dữ liệu | Ví dụ | Mã GET gợi ý |
|---|---|---|
| Bản ghi chưa từng tồn tại | UUID tự tạo | 404 |
| Bản nháp chưa phát hành công khai | Bài viết đang duyệt | 404 với người ngoài |
| Tài liệu công khai đã gỡ lâu dài, giữ tombstone công khai | Bài hướng dẫn hết hiệu lực | 410 |
| Tài liệu công khai tạm ẩn có thể khôi phục | Bài viết tạm đình chỉ | 404; 410 dễ gây hiểu nhầm về tính lâu dài |
| Đơn hàng riêng tư vừa xóa | Lịch sử đặt hàng đã ẩn khỏi người dùng | 404 theo chính sách tenant, ngay cả khi DB giữ tombstone |
| Resource được di chuyển tới URI mới | Bài viết đổi slug | Cân nhắc 301/308 hoặc liên kết thay thế theo hợp đồng |
| Cơ sở dữ liệu không có cách phân biệt “chưa từng có” và “đã xóa” | Chỉ tìm thấy bản ghi hiện tại | 404; không tự bịa lịch sử để trả 410 |

### 6.1. Tombstone là gì?

**Tombstone** là một dấu vết dữ liệu tối thiểu, chẳng hạn object key, thời điểm thu hồi và trạng thái gỡ bỏ lâu dài, giúp hệ thống biết URI từng được xuất bản và giờ đã gỡ. Nó hữu ích cho 410 của resource công khai, phát hiện đồng bộ và chống tái sử dụng nhầm ID.

Nhưng tombstone cũng là **dữ liệu có thể nhạy cảm**. Không cần giữ mã định danh cá nhân hoặc nội dung đã xóa chỉ để có khả năng trả 410. Các chính sách xóa, retention, legal hold và quyền riêng tư có thể buộc hệ thống giữ dữ liệu nội bộ trong một thời gian; điều đó **không đồng nghĩa** với việc phải thông báo lịch sử của dữ liệu ấy qua API.

### 6.2. “Vĩnh viễn” là quyết định hợp đồng

Nếu URI đã thông báo 410 nhưng một tuần sau được tạo lại, client hay cache có thể vẫn tin resource đã mất. Bởi vậy, chỉ dùng 410 khi có chính sách phát hành rõ, quản trị vòng đời URL và kế hoạch cache phù hợp. Nếu có khả năng khôi phục thường xuyên, 404 có thể diễn tả chính xác hơn việc biểu diễn **hiện tại** không khả dụng.

## 7. Chính sách chống dò tìm tài nguyên (resource enumeration)

**Enumeration** xảy ra khi một người gọi thử nhiều ID/URI để suy ra những tài nguyên nào có tồn tại, ai sở hữu hoặc tài nguyên đã thay đổi trạng thái. Người gọi không cần lấy được nội dung resource; chỉ một bit “có/không” cũng có giá trị.

Ví dụ trong một hệ thống đa tenant:

~~~text
GET /v1/orders/1001  -> 404
GET /v1/orders/1002  -> 403
GET /v1/orders/1003  -> 410
~~~

Nếu ID của đơn không thuộc người gọi nhưng ứng dụng trả khác nhau theo trạng thái thực trong database, client có thể suy ra:

- **404**: có thể chưa tồn tại.
- **403**: có thể tồn tại, nhưng bị chặn quyền.
- **410**: rất có thể từng tồn tại và đã xóa.

Đây là một **rò rỉ siêu dữ liệu**. Đổi ID từ số tuần tự thành UUID ngẫu nhiên giúp giảm khả năng đoán, nhưng **không thay thế kiểm tra phân quyền**: ID có thể bị lộ trong log, email, tài liệu chia sẻ, đường dẫn hoặc browser history.

### 7.1. Kiểm tra quyền cùng với truy vấn

Mẫu an toàn cho API nhiều tenant là chỉ **tìm trong tập resource người gọi có quyền nhìn thấy**, ví dụ:

~~~sql
SELECT id, tenant_id, total_amount, status
FROM orders
WHERE id = :orderId
  AND tenant_id = :authenticatedTenantId
  AND deleted_at IS NULL;
~~~

Nếu không có hàng nào, trả 404. Cách truy vấn này không cho phép controller **findById trước rồi kiểm tra tenant sau** và vô tình tiết lộ tồn tại bằng mã lỗi khác. Dữ liệu tenantId phải lấy từ **ngữ cảnh xác thực đáng tin cậy**, không lấy trực tiếp từ query parameter, body hoặc header do client có thể tự sửa.

Trong hệ thống phức tạp, có thể cần thêm kiểm tra quyền theo owner, quan hệ chia sẻ, nhóm hoặc row-level security của database. Điều cốt lõi là **kiểm tra phạm vi nhìn thấy và quyền thao tác trước khi công bố bất kỳ trạng thái nào về resource**.

### 7.2. Ẩn mã trạng thái chưa đủ

Trả 404 chung vẫn có thể làm lộ tồn tại qua các kênh phụ:

| Kênh rò rỉ | Ví dụ | Biện pháp |
|---|---|---|
| **Body** | ID không tồn tại ghi “Not found”, ID người khác ghi “Permission denied” | Dùng cùng cấu trúc lỗi, detail trung tính và mã lỗi chung khi cần che giấu |
| **Header** | Chỉ resource tồn tại mới có ETag, Last-Modified, Location hoặc resource owner | Không trả metadata của tài nguyên chưa được phép nhìn thấy |
| **Thời gian phản hồi** | ID có bản ghi phải thêm bước kiểm tra quyền, chậm hơn rõ rệt | Truy vấn trong phạm vi quyền, đo và hạn chế khác biệt thời gian có thể khai thác |
| **Độ dài response** | 404 thật có 30 byte, 404 ẩn có 400 byte | Dùng template phản hồi tương đương; không thêm dữ liệu nội bộ |
| **Cache/CDN** | Response 404 riêng tư bị lưu trong cache chung | Cache-Control phù hợp, tránh dùng cache chung cho trạng thái phụ thuộc danh tính |
| **Danh sách, tìm kiếm, đếm** | GET riêng tư trả 404, nhưng search tổng hợp vẫn tính tài nguyên đó | Áp dụng cùng chính sách quyền cho list, filter, count, pagination |
| **Batch và resource con** | GET /orders/{id} trả 404 nhưng /orders/{id}/items trả 403 | Thống nhất trạng thái của resource cha và các đường dẫn con |
| **Retry/error diagnostics** | Mã lỗi nội bộ “ORDER_BELONGS_TO_OTHER_USER” lọt ra client | Log nguyên nhân nội bộ có kiểm soát; response công khai trung tính |
| **Theo dõi và báo cáo** | Endpoint kiểm tra tồn tại, analytics, event stream trả trạng thái khác | Thiết kế quyền xuyên mọi kênh lộ resource |

Không phải mọi khác biệt thời gian đều có thể loại bỏ, nhưng phải tránh **đường xử lý cố tình tiết lộ** khác nhau. Không nên tự thêm delay cố định cho mọi 404 để “bảo mật”; cần đo rủi ro thực tế, tối ưu truy vấn và dùng kiểm soát truy cập, rate limit, monitoring.

### 7.3. 401 vẫn cần nhất quán

Nếu đường dẫn cần đăng nhập, request **chưa xác thực** nên đi qua bộ lọc bảo mật và trả 401 kèm challenge; ứng dụng không được tự đi tìm đơn hàng rồi chọn 404/410 dựa trên bản ghi. Khác biệt giữa 401 cho người **chưa xác thực** và 404 cho người **đã xác thực nhưng không được thấy** là một chính sách hợp lý.

Nếu có chính sách ẩn ngay cả sự tồn tại của API route, phải đánh giá kỹ sự tương thích với challenge xác thực, client và quy ước HTTP. Không dùng “security by obscurity” như cơ chế bảo vệ duy nhất.

### 7.4. Giám sát hành vi dò tìm

Theo dõi số lần 404, 403, 401, tỷ lệ truy vấn ID không thấy và số URL khác nhau theo token/IP/tenant trong cửa sổ thời gian. Gắn rate limit và alert theo rủi ro, tránh công khai thông tin khách hàng qua log. Một lượng 404 cao cũng có thể do bot tìm kiếm, liên kết hỏng hoặc triển khai API mới; phải kết hợp ngữ cảnh để tránh nhầm người dùng hợp lệ với tấn công.

## 8. Ảnh hưởng của phương thức HTTP

404 và 410 mô tả trạng thái của **resource tại URI**; nhưng ý nghĩa phương thức HTTP vẫn quyết định cách client diễn giải toàn bộ thao tác.

| Phương thức | Tình huống | Chính sách cần xác định |
|---|---|---|
| **GET** | Đọc resource không có biểu diễn hiện tại | 404; nếu resource công khai được biết đã gỡ lâu dài, có thể 410 |
| **HEAD** | Kiểm tra metadata và tính khả dụng của resource | Quyết định trạng thái và header tương đương GET phù hợp, **không gửi body** |
| **DELETE** | Xóa resource đã không còn hoặc đã xóa | 204, 404 hoặc 410 có thể phù hợp tùy hợp đồng; tính idempotent không bắt buộc response phải giống nhau mỗi lần |
| **PUT** | Tạo/ghi đè resource tại URI đã gỡ | Phụ thuộc việc client có quyền tạo resource, quy tắc tombstone và xung đột trạng thái; không tự suy ra 410 |
| **PATCH** | Cập nhật resource không được nhìn thấy | 404 theo chính sách ẩn, hoặc 403 nếu được phép tiết lộ và thiếu quyền |
| **POST** | Thao tác vào collection hoặc resource con | Áp dụng quy tắc của endpoint; 404 có thể chỉ rằng resource cha không tồn tại/không hiển thị |

### 8.1. DELETE idempotent không có nghĩa luôn trả 204

Một DELETE được gọi là **idempotent theo semantics** khi gọi lại cùng một yêu cầu không tạo thêm hiệu ứng dự kiến lên trạng thái server so với gọi một lần. Ví dụ:

~~~http
DELETE /v1/bookmarks/abc HTTP/1.1
Authorization: Bearer <access-token>

HTTP/1.1 204 No Content
~~~

Client gọi lần hai, API có thể tiếp tục trả **204** để đơn giản hóa đồng bộ trạng thái, hoặc **404** nếu hợp đồng muốn chỉ ra bookmark không còn. Hai response khác nhau không làm phương thức DELETE mất tính idempotent, miễn hiệu ứng mục tiêu vẫn như nhau. Riêng resource cần giấu quyền sở hữu, phải bảo đảm lần DELETE đầu hay lần sau **không để lộ** bookmark của người khác.

Không nên trả 410 cho **mọi** DELETE lần hai chỉ vì trước đó đã có thao tác xóa: 410 đưa ra thông tin lịch sử và tính lâu dài mà API có thể không muốn hoặc không biết.

### 8.2. HEAD và các điều kiện cache

Với GET và HEAD, không tính ETag/Last-Modified của resource **trước khi kiểm tra quyền**. Không để các phản hồi điều kiện như 304 Not Modified trở thành đường vòng xác nhận sự tồn tại của resource riêng tư. HEAD phải tôn trọng chính sách 404/410/ẩn resource giống GET ở mức thông tin có thể công bố, dù bản thân HEAD không có response body.

## 9. Cache 404 và 410: một điểm dễ sai

**404 và 410 đều có thể được cache bằng heuristic theo ngữ nghĩa HTTP nếu không có quy định ngược lại.** Vì vậy, việc “trả lỗi thôi” không có nghĩa response sẽ luôn được gửi về server ở request kế tiếp.

### 9.1. Negative caching

**Negative caching** là lưu response chỉ rằng resource hiện không có/không khả dụng. Nó giảm tải khi client hoặc bot liên tục yêu cầu một URL sai, nhưng cũng khiến resource vừa được tạo hoặc khôi phục **tiếp tục bị xem như không tồn tại** cho đến khi cache hết hạn hoặc được invalidation.

Ví dụ:

~~~http
HTTP/1.1 404 Not Found
Cache-Control: public, max-age=60
Content-Type: application/problem+json
~~~

Response 404 công khai có thể được CDN/cache dùng trong 60 giây, nếu cấu hình cache key và nhà cung cấp cho phép. Nếu resource có thể được tạo ngay lập tức và client cần đọc tức thì, phải giảm TTL, vô hiệu hóa cache theo sự kiện hoặc dùng chính sách phù hợp hơn.

### 9.2. Khuyến nghị cache theo loại API

| Response | Cache-Control gợi ý | Lý do |
|---|---|---|
| 404 của bài viết/tài liệu công khai không có | public, max-age=60 (ví dụ) | Giảm tải, nhưng không giữ âm tính quá lâu |
| 410 của URI công khai đã rút lâu dài | public, max-age=300 (ví dụ) | Trạng thái thay đổi ít; cân nhắc invalidation nếu có ngoại lệ |
| 404 của đơn hàng/tệp riêng tư hoặc theo tenant | **no-store** | Tránh cache lưu hoặc phân phối trạng thái phụ thuộc danh tính |
| 401/403 chứa thông tin xác thực/quyền | **no-store** là lựa chọn thận trọng | Tránh lưu thông tin nhạy cảm hoặc tái dùng trạng thái cho người khác |
| Response biến đổi theo người dùng nhưng được phép cache | private hoặc thiết kế cache key rất cẩn thận | Không để shared cache trộn dữ liệu giữa các danh tính |

**Cache-Control: no-store** yêu cầu cache không lưu response theo chỉ thị. **private** ngăn shared cache lưu nhưng vẫn cho phép cache riêng của client; nếu response chứa thông tin nhạy cảm hoặc trạng thái quyền cần cập nhật ngay, **no-store** thường dễ kiểm soát hơn.

### 9.3. Cache key, xác thực và CDN

Không nên đặt **Cache-Control: public** cho kết quả 404/410 phụ thuộc access token, tenant, vai trò hoặc cookie. Một CDN có cache key chỉ dựa vào URL có thể nhận 404 do tenant A không có quyền rồi trả 404 đã cache cho tenant B vốn **có quyền**; hoặc tệ hơn, phục vụ metadata nhạy cảm của tài khoản khác.

Với nội dung công khai, phải xác minh CDN cache theo đúng host, path, query cần thiết và thời hạn hợp đồng. Với nội dung riêng tư, nên tránh shared caching hoặc chỉ sử dụng khi đã có thiết kế phân tách danh tính và header đủ chặt chẽ. Header **Vary: Authorization** không phải giải pháp “thần kỳ”: cơ chế hỗ trợ và chính sách cache có thể khác nhau; không thay thế kiểm tra cache key và cách CDN xử lý credential.

## 10. Thiết kế body lỗi với Problem Details

Sử dụng **Problem Details for HTTP APIs** theo **RFC 9457** giúp client xử lý lỗi bằng cấu trúc nhất quán. Media type là **application/problem+json** với các thành phần phổ biến: type, title, status, detail và instance.

Ví dụ lỗi 404 dành cho resource riêng tư:

~~~json
{
  "type": "https://api.example.com/problems/not-found",
  "title": "Not Found",
  "status": 404,
  "detail": "Không tìm thấy tài nguyên.",
  "requestId": "req-7fc2"
}
~~~

**requestId** là trường mở rộng minh họa, giúp support tra log. Không nên thêm tenant của chủ resource, lịch sử xóa, ownerId, tên đầy đủ, đường dẫn ổ đĩa, stack trace hoặc câu kiểu “Bạn không có quyền xem đơn của người X”.

### 10.1. Quy tắc xây dựng lỗi

- **Cùng tình huống phải cho cùng loại phản hồi:** ID không tồn tại và ID bị ẩn đều trả 404 trung tính, cùng type và title; requestId khác nhau là bình thường.
- **Không dựa vào detail để quyết định luồng chương trình:** client dựa trên status và mã/type đã công bố.
- **Phân tách log nội bộ:** backend có thể ghi nguyên nhân chính xác dưới quyền truy cập được kiểm soát để vận hành, nhưng body công khai chỉ chứa thông tin an toàn.
- **Không đưa URL chứa token hoặc dữ liệu nhạy cảm vào trường instance:** có thể dùng một request ID/đường dẫn tổng quát nếu hợp đồng yêu cầu.
- **Đảm bảo status trong body khớp HTTP status:** tránh HTTP 200 kèm body có status 404 hay 410.

### 10.2. Tránh dùng 410 như thông báo quy trình nghiệp vụ

Một đơn hàng “đã hủy” vẫn là **đơn hàng tồn tại** và có thể đọc trạng thái CANCELED; không nên trả 410 chỉ vì không thể tiếp tục thanh toán. Tương tự, một sản phẩm “hết hàng” có thể vẫn có trang chi tiết và trạng thái OUT_OF_STOCK. **Trạng thái nghiệp vụ của resource** không tương đương **biểu diễn resource không còn tại URI**.

## 11. Mẫu chính sách theo vòng đời resource

Để thiết kế nhất quán, hãy đặt ra quyết định theo **loại resource** trước khi viết controller. Ví dụ hợp đồng của ứng dụng bán hàng:

~~~text
RESOURCE: /v1/orders/{orderId}
PUBLIC: false
AUTHENTICATION: required
VISIBILITY: chỉ tenant/owner được cấp quyền
GET khi không có hoặc không nhìn thấy: 404 chung
GET khi order đã bị xóa khỏi giao diện: 404 chung
GET khi order bị hủy nghiệp vụ: 200 với status=CANCELED nếu vẫn được phép xem
GET khi thiếu token: 401 + WWW-Authenticate
CACHE: no-store cho response theo danh tính

RESOURCE: /v1/help/articles/{slug}
PUBLIC: true
GET khi đang phát hành: 200
GET khi slug chưa biết hoặc chỉ tạm ẩn: 404
GET khi tombstone công khai ghi gỡ lâu dài: 410
GET khi có canonical URI thay thế: cân nhắc redirect
CACHE: cho phép public cache 404/410 TTL ngắn theo chính sách xuất bản
~~~

Quy tắc này giúp thống nhất backend, tài liệu API, lớp cache, frontend và bộ kiểm thử. **Không nên quyết định 404 hay 410 chỉ dựa vào tên cột isDeleted** nếu chưa phân loại rõ quyền riêng tư và ý nghĩa công khai của URI.

## 12. Ví dụ triển khai Java và Spring Boot

Ví dụ dưới đây dùng phong cách **Spring Boot 3 / Spring Framework 6, Java 17+**, với OAuth2 Resource Server, để minh họa **ranh giới trách nhiệm**. Đây là các đoạn mã thiết kế; cần cung cấp dependency, entity, repository, mapper, cấu hình issuer/JWK và dữ liệu kiểm thử tương ứng trong ứng dụng thực.

### 12.1. Security filter xác thực trước controller

~~~java
@Configuration
@EnableWebSecurity
class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/v1/help/articles/**").permitAll()
                .requestMatchers("/v1/orders/**").authenticated()
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

Trong mẫu trên, JWT phải được xác thực đúng chữ ký, issuer, audience, thời hạn và các claim quan trọng theo chính sách ứng dụng. **Không sử dụng tenantId do client tự truyền** thay cho claim danh tính đã được xác minh. Endpoint bắt buộc xác thực sẽ được filter trả **401** khi token thiếu/không hợp lệ, trước khi controller kiểm tra ID đơn hàng.

Nếu API có thêm quyền theo scope, role hoặc thao tác, phải thiết kế phân biệt rõ **quyền truy cập route** và **quyền xem một resource cụ thể**. Route-level 403 có thể hữu ích, còn resource-level 404 giúp tránh xác nhận ID của tenant khác.

### 12.2. Controller riêng tư: tìm theo tenant ngay ở repository

~~~java
@RestController
@RequestMapping("/v1/orders")
class OrderReadController {
    private final OrderReadRepository orders;
    private final OrderMapper mapper;

    OrderReadController(OrderReadRepository orders, OrderMapper mapper) {
        this.orders = orders;
        this.mapper = mapper;
    }

    @GetMapping("/{id}")
    ResponseEntity<OrderDto> get(
        @PathVariable UUID id,
        @AuthenticationPrincipal Jwt jwt
    ) {
        String tenantId = jwt.getClaimAsString("tenant_id");

        // Repository chỉ tìm đơn còn hiển thị của tenant đã xác thực.
        OrderDto dto = orders.findVisibleByIdAndTenantId(id, tenantId)
            .map(mapper::toDto)
            .orElseThrow(ResourceNotVisibleException::new);

        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(dto);
    }
}
~~~

Để ví dụ hoạt động an toàn, **tenant_id phải là claim bắt buộc được kiểm tra trong quá trình xác thực**; nếu thiếu hoặc không hợp lệ, từ chối token theo chính sách, không rơi về “tenant mặc định”. Phương thức repository phải đưa điều kiện tenant và trạng thái hiển thị vào **truy vấn DB**, hoặc dùng cơ chế phân quyền tương đương được kiểm chứng.

Ví dụ chữ ký của repository:

~~~java
interface OrderReadRepository {
    Optional<OrderEntity> findVisibleByIdAndTenantId(UUID id, String tenantId);
}
~~~

Nếu quyền thực tế là **owner, shared-user, tổ chức, phòng ban** chứ không chỉ tenant, phương thức truy vấn cũng phải thể hiện tập tài nguyên người gọi được phép xem. Repository chỉ được phép trả hàng hợp lệ trong tập đó, không nên trả hàng rồi “chữa” bằng một if trong controller.

### 12.3. Controller công khai: 410 chỉ khi có tombstone đáng tin

~~~java
@RestController
@RequestMapping("/v1/help/articles")
class PublicArticleController {
    private final PublicArticleRepository articles;
    private final ArticleMapper mapper;

    PublicArticleController(
        PublicArticleRepository articles,
        ArticleMapper mapper
    ) {
        this.articles = articles;
        this.mapper = mapper;
    }

    @GetMapping("/{slug}")
    ResponseEntity<ArticleDto> get(@PathVariable String slug) {
        PublicArticle article = articles.findByPublicSlug(slug)
            .orElseThrow(PublicNotFoundException::new);

        if (article.isPermanentlyWithdrawn()) {
            throw new PublicGoneException();
        }
        if (!article.isPublished()) {
            throw new PublicNotFoundException();
        }
        return ResponseEntity.ok(mapper.toDto(article));
    }
}
~~~

Repository công khai có thể giữ tombstone để biết tài liệu nào đã bị rút vĩnh viễn. **Truy vấn công khai không được trả dữ liệu nháp hoặc riêng tư ngoài hợp đồng.** Nếu bài viết được chuyển URI, cân nhắc logic redirect riêng và kiểm tra URL đích phù hợp; không tự biến mọi bản ghi rút thành 410.

### 12.4. Trả lỗi trung tính bằng ProblemDetail

~~~java
@RestControllerAdvice
class ApiProblemHandler {

    @ExceptionHandler(ResourceNotVisibleException.class)
    ResponseEntity<ProblemDetail> hiddenNotFound() {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .cacheControl(CacheControl.noStore())
            .body(problem(
                HttpStatus.NOT_FOUND,
                "Không tìm thấy tài nguyên."
            ));
    }

    @ExceptionHandler(PublicNotFoundException.class)
    ResponseEntity<ProblemDetail> publicNotFound() {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .cacheControl(
                CacheControl.maxAge(Duration.ofSeconds(60)).cachePublic()
            )
            .body(problem(
                HttpStatus.NOT_FOUND,
                "Không tìm thấy tài nguyên."
            ));
    }

    @ExceptionHandler(PublicGoneException.class)
    ResponseEntity<ProblemDetail> publicGone() {
        return ResponseEntity.status(HttpStatus.GONE)
            .cacheControl(
                CacheControl.maxAge(Duration.ofMinutes(5)).cachePublic()
            )
            .body(problem(
                HttpStatus.GONE,
                "Tài liệu này không còn được cung cấp."
            ));
    }

    private static ProblemDetail problem(HttpStatus status, String detail) {
        ProblemDetail p = ProblemDetail.forStatusAndDetail(status, detail);
        p.setTitle(status.getReasonPhrase());
        p.setType(URI.create(
            status == HttpStatus.GONE
                ? "https://api.example.com/problems/gone"
                : "https://api.example.com/problems/not-found"
        ));
        return p;
    }
}
~~~

Ở đây, ResourceNotVisibleException, PublicNotFoundException và PublicGoneException là **exception nghiệp vụ riêng cần định nghĩa**. Tầng xác thực/ủy quyền của Spring Security vẫn sở hữu **401**, **403** phù hợp; handler chỉ làm rõ sự khác biệt giữa lỗi riêng tư và kết quả public cacheable.

Các import như HttpStatus, ResponseEntity, ProblemDetail, CacheControl, Duration, URI và các annotation Spring được lược bớt để tập trung vào chính sách. Trong ứng dụng thật, có thể dùng cùng một exception mapper, miễn response công khai/riêng tư không bị áp dụng nhầm cache policy.

### 12.5. Những lỗi triển khai phổ biến

Không dùng logic này:

~~~java
// Mẫu không an toàn: làm lộ sự tồn tại giữa các tenant.
OrderEntity order = orderRepository.findById(id)
    .orElseThrow(ResourceNotVisibleException::new);

if (!order.getTenantId().equals(authenticatedTenantId)) {
    throw new AccessDeniedException("Order exists, but belongs to another tenant");
}
~~~

Nếu exception dẫn tới 403 hoặc body khác biệt, client có thể suy ra ID tồn tại. Thay bằng truy vấn **tập có quyền nhìn thấy**, rồi dùng chung 404. Dĩ nhiên, phân quyền vẫn phải được thực thi ở cả tầng truy vấn và các thao tác cập nhật, không chỉ ở GET.

## 13. Mô tả hợp đồng 404/410 trong OpenAPI

OpenAPI nên nêu rõ resource riêng tư có thể trả 404 khi **không tồn tại hoặc không được phép tiết lộ**, trong khi 410 chỉ được công bố cho resource **công khai** có chính sách gỡ lâu dài.

Ví dụ rút gọn theo OpenAPI 3.1:

~~~yaml
openapi: 3.1.0
info:
  title: Resource Visibility API
  version: 1.0.0
paths:
  /v1/orders/{orderId}:
    get:
      operationId: getOrder
      summary: Xem đơn hàng được phép truy cập
      description: >
        Trả 404 cả khi ID không tồn tại và khi resource
        không hiển thị cho principal hiện tại.
      security:
        - bearerAuth: []
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        "200":
          description: Đơn hàng hiển thị cho người gọi
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Order"
        "401":
          description: Thiếu hoặc không có thông tin xác thực hợp lệ
          headers:
            WWW-Authenticate:
              description: Thử thách xác thực Bearer phù hợp
              schema:
                type: string
        "404":
          description: Resource không tồn tại hoặc không được tiết lộ
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/Problem"
  /v1/help/articles/{slug}:
    get:
      operationId: getPublicArticle
      summary: Xem tài liệu công khai
      parameters:
        - name: slug
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: Tài liệu đang phát hành
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Article"
        "404":
          description: Không có biểu diễn công khai hiện tại
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/Problem"
        "410":
          description: Tài liệu công khai đã được gỡ bỏ lâu dài
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/Problem"
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
  schemas:
    Order:
      type: object
      properties:
        id:
          type: string
          format: uuid
        status:
          type: string
      required: [id, status]
    Article:
      type: object
      properties:
        slug:
          type: string
        title:
          type: string
      required: [slug, title]
    Problem:
      type: object
      properties:
        type:
          type: string
          format: uri-reference
        title:
          type: string
        status:
          type: integer
        detail:
          type: string
        requestId:
          type: string
      required: [type, title, status]
~~~

**Lưu ý hợp đồng:**

- Không mô tả 410 cho đơn hàng riêng tư nếu thực tế API luôn ẩn trạng thái xóa bằng 404.
- Có thể bổ sung **403** cho endpoint có quyền thực hiện thao tác cụ thể, nếu chính sách cho phép công khai sự tồn tại resource và việc thiếu quyền.
- Mô tả **Cache-Control** của 404/410/response riêng tư bằng quy ước API và các kiểm thử header; OpenAPI không tự thiết lập hành vi cache cho runtime.
- Phân biệt **schema lỗi nhất quán** với **thông điệp nội bộ**. Không đưa lý do “thuộc tenant khác” vào public description dành cho client.
- Cập nhật hợp đồng khi đổi chính sách gỡ bỏ hoặc chuyển URI. Việc đổi 404 thành 410 có thể ảnh hưởng crawler, cache và client tự động.

## 14. Kiểm thử: đúng HTTP và không lộ sự tồn tại

Kiểm thử nên bao gồm **hai lớp**: kiểm tra hợp đồng HTTP (mã, body, header) và kiểm tra **bảo mật phân quyền** (người gọi không thể suy ra tài nguyên nào nằm ngoài phạm vi của mình). Chỉ có test “ID không tìm thấy trả 404” là chưa đủ.

### 14.1. Ma trận test đề xuất

| Ca kiểm thử | Điều kiện | Kỳ vọng |
|---|---|---|
| T01 | GET đơn của chính tenant, đủ quyền | 200 và dữ liệu đúng |
| T02 | GET đơn không tồn tại, token hợp lệ | 404, body trung tính, Cache-Control: no-store |
| T03 | GET đơn có thật nhưng thuộc tenant khác | **404 với type/title/detail tương đương T02** |
| T04 | GET đơn đã ẩn khỏi chủ tài khoản theo hợp đồng | 404, không lộ thời điểm xóa hoặc lịch sử |
| T05 | GET đơn, thiếu token | 401 và WWW-Authenticate thích hợp |
| T06 | GET đơn, token sai hoặc hết hạn | 401 theo tầng bảo mật |
| T07 | GET tài liệu công khai đang phát hành | 200, nội dung công khai |
| T08 | GET slug tài liệu không biết | 404 |
| T09 | GET slug công khai có tombstone gỡ lâu dài | 410 |
| T10 | GET tài liệu công khai chỉ tạm ẩn | 404, không phải 410 |
| T11 | GET tài liệu riêng tư khác tenant dù tombstone đã xóa | 404, không phải 410 |
| T12 | HEAD đơn của tenant khác | 404, không có response body |
| T13 | HEAD tài liệu công khai đã gỡ lâu dài | 410, không có response body |
| T14 | GET đơn với If-None-Match của resource khác tenant | Không được trả 304 làm lộ resource |
| T15 | GET đơn với ID sai cú pháp | 400 nếu hợp đồng yêu cầu UUID hợp lệ, không tiết lộ tài nguyên |
| T16 | DELETE lặp lại trên resource người gọi sở hữu | Kết quả đúng hợp đồng (204/404/410 tùy mô hình), không gây side effect thêm |
| T17 | GET đơn không tồn tại hoặc bị ẩn qua CDN/cache | Không lưu và không tái dùng response riêng tư cho user khác |
| T18 | Thử tìm cùng ID qua GET, HEAD, search, count, route con | Không có đường vòng tiết lộ tồn tại |

**Không cần body giống từng byte giữa T02 và T03** nếu response luôn tạo requestId hoặc timestamp riêng. Cần thống nhất phần có thể quan sát để phân biệt trường hợp, nhất là **status, type, title, detail, header bảo mật và cấu trúc body**. Với hệ thống nhạy cảm cao, thực hiện thêm kiểm thử thống kê chênh lệch thời gian phản hồi, nhưng không coi độ trễ bằng nhau tuyệt đối là điều kiện dễ đạt.

### 14.2. MockMvc minh họa cho API đa tenant

Đoạn mã sau là **ví dụ test tích hợp**, giả định fixture đã tạo một đơn thuộc tenant-a, một ID chưa tồn tại và một bài viết công khai được đánh dấu gỡ lâu dài. Phần seed dữ liệu và import được lược bớt:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ResourceVisibilityContractTest {
    @Autowired
    MockMvc mvc;

    // Fixture giả định tạo dữ liệu thật trong DB test:
    UUID foreignTenantOrderId;
    UUID unknownOrderId;

    @Test
    void orderOfOtherTenantIsNotFound() throws Exception {
        mvc.perform(
                get("/v1/orders/{id}", foreignTenantOrderId)
                    .with(jwt().jwt(
                        token -> token.claim("tenant_id", "tenant-b")
                    ))
            )
            .andExpect(status().isNotFound())
            .andExpect(header().string(
                "Cache-Control", containsString("no-store")
            ))
            .andExpect(jsonPath("$.title").value("Not Found"))
            .andExpect(jsonPath("$.detail")
                .value("Không tìm thấy tài nguyên."));
    }

    @Test
    void unknownOrderHasSameNotFoundContract() throws Exception {
        mvc.perform(
                get("/v1/orders/{id}", unknownOrderId)
                    .with(jwt().jwt(
                        token -> token.claim("tenant_id", "tenant-b")
                    ))
            )
            .andExpect(status().isNotFound())
            .andExpect(header().string(
                "Cache-Control", containsString("no-store")
            ))
            .andExpect(jsonPath("$.title").value("Not Found"))
            .andExpect(jsonPath("$.detail")
                .value("Không tìm thấy tài nguyên."));
    }

    @Test
    void publicPermanentlyWithdrawnArticleIsGone() throws Exception {
        mvc.perform(get("/v1/help/articles/{slug}", "retired-guide"))
            .andExpect(status().isGone())
            .andExpect(jsonPath("$.title").value("Gone"));
    }
}
~~~

Hàm jwt() trong **spring-security-test** có thể dựng principal thử nghiệm mà **không chạy quá trình xác minh chữ ký token thật**. Do đó, ngoài những test quyền tại controller/service, cần test cấu hình resource server với token thiếu/hỏng/hết hạn và claim không hợp lệ ở môi trường tích hợp để xác nhận hành vi 401/challenge và ranh giới tin cậy.

### 14.3. Những kiểm thử cần chạy ngoài unit test

- **Security integration:** xác minh các route được bảo vệ, token có audience/issuer sai bị chặn, tenantId không được client giả mạo.
- **Contract test:** so sánh response với OpenAPI, bao gồm Content-Type: application/problem+json, Cache-Control và WWW-Authenticate.
- **Cache test:** tạo 404 cho resource công khai, sau đó phát hành tài liệu mới; kiểm tra độ trễ cache/invalidation. Với resource riêng tư, thử hai người dùng khác tenant qua cùng CDN để bảo đảm không có cache trộn quyền.
- **Enumeration test:** dùng tập ID tồn tại, không tồn tại và đã xóa, xác nhận status/body/header không lộ phân loại nội bộ; đo timing theo nhiều mẫu nếu đây là một rủi ro đã được xác định.
- **Lifecycle test:** chuyển public article từ PUBLISHED sang TEMPORARILY_HIDDEN rồi PERMANENTLY_WITHDRAWN, xác minh mã và cache thay đổi đúng hợp đồng.
- **HEAD/conditional requests:** kiểm tra HEAD không có body và conditional GET không trả 304 cho resource chưa được phép thấy.

Không nên chỉnh mã trả 404 chỉ để test hiển thị đúng status rồi bỏ qua **truy vấn quyền ở tầng dữ liệu**. Một test thành công khi resource không tồn tại không chứng minh API đã chống được **IDOR/BOLA** (truy cập object vượt quyền).

## 15. Bài tập thực hành thiết kế chính sách trạng thái

### 15.1. Đề bài

Một nền tảng học trực tuyến có API:

~~~text
GET    /v1/courses/{courseId}
GET    /v1/courses/{courseId}/lessons/{lessonId}
GET    /v1/me/submissions/{submissionId}
DELETE /v1/me/submissions/{submissionId}
GET    /v1/docs/{slug}
~~~

Hệ thống có các quy định:

- Course có trạng thái **PUBLIC**, **DRAFT** hoặc **ARCHIVED**. PUBLIC được xem bởi mọi người; DRAFT chỉ giảng viên và quản trị viên có quyền; ARCHIVED có thể vẫn được xem bởi người có quyền nội bộ.
- Submission là bài nộp riêng tư; người học không được biết người khác có submission với ID nào.
- Tài liệu **/v1/docs/{slug}** công khai, có thể được phát hành, tạm ẩn hoặc thu hồi lâu dài. Hệ thống ghi được tombstone của những tài liệu đã từng phát hành công khai.
- Endpoint submission yêu cầu xác thực Bearer và lưu kết quả theo quyền owner.

**Hãy đưa ra HTTP status và lý do** cho các tình huống:

1. Khách chưa đăng nhập mở course PUBLIC.
2. Khách chưa đăng nhập mở course DRAFT.
3. Học viên đã đăng nhập nhưng không có quyền mở course DRAFT.
4. Học viên gọi GET một submission của người khác.
5. Học viên gọi GET một submission ID chưa từng tồn tại.
6. Học viên gọi GET submission của mình nhưng đã bị ẩn khỏi giao diện theo chính sách.
7. Học viên chưa gửi token khi gọi GET /v1/me/submissions/{id}.
8. Người dùng mở docs slug chưa từng tồn tại.
9. Người dùng mở docs slug đã được công bố và rút vĩnh viễn.
10. Người dùng mở docs slug mới chỉ tạm ngừng xuất bản.
11. Người dùng gọi DELETE một submission của mình hai lần.
12. Người dùng gửi HEAD tới submission của người khác.

### 15.2. Lời giải gợi ý

| Tình huống | Đáp án gợi ý | Giải thích |
|---|---|---|
| 1 | **200** | Course công khai hiện có biểu diễn |
| 2 | **404** | Chính sách không tiết lộ course nháp cho khách ngoài |
| 3 | **404** | Che giấu sự tồn tại với người không có quyền nhìn thấy |
| 4 | **404** | Submission riêng tư thuộc người khác |
| 5 | **404** | Phản hồi giống tình huống 4 |
| 6 | **404** | Submission đã ẩn theo hợp đồng; không dùng 410 để lộ lịch sử |
| 7 | **401** | Endpoint yêu cầu xác thực; phải kèm WWW-Authenticate phù hợp |
| 8 | **404** | Không có biểu diễn công khai và không có bằng chứng gỡ lâu dài |
| 9 | **410** | Tombstone công khai xác nhận việc thu hồi lâu dài |
| 10 | **404** | Chưa khẳng định không trở lại; 410 không phù hợp |
| 11 | **204 rồi 204**, hoặc **204 rồi 404** | Phải thống nhất hợp đồng DELETE; side effect không được nhân đôi |
| 12 | **404** và **không có body** | HEAD áp dụng chính sách nhìn thấy như GET |

Ở tình huống 2, nếu hệ thống có route công khai cho cả khóa học nháp nhưng bắt buộc đăng nhập trước khi đánh giá quyền thì có thể chọn 401 cho người chưa xác thực; **bài tập giả định API public course có thể tra cứu biểu diễn công khai mà không bắt đăng nhập**. Việc mô tả rõ tiền đề là quan trọng để tránh dùng một status cho mọi kiến trúc.

### 15.3. Bài tập mở rộng: phát hiện kênh rò rỉ

Nhóm backend đã sửa GET /v1/me/submissions/{id} để luôn trả 404 cho ID không hiển thị. Nhưng:

~~~text
GET /v1/me/submissions/777                 -> 404
HEAD /v1/me/submissions/777                -> 403
GET /v1/me/submissions?ids=777             -> {"count": 1}
GET /v1/me/submissions/777/attachments     -> 410
~~~

**Yêu cầu:** chỉ ra những cách phát hiện submission tồn tại, rồi đề xuất test và chỉnh hợp đồng.

**Phân tích:** HEAD 403 xác nhận trạng thái quyền khác GET; count phản ánh bản ghi ngoài phạm vi; 410 của attachments làm lộ lịch sử gỡ. Cần áp dụng cùng truy vấn phạm vi quyền cho list/batch, dùng 404/ẩn ở resource con nếu resource cha không hiển thị, đồng nhất HEAD với GET về trạng thái có thể công bố, và thêm test xuyên các route. **Không chỉ sửa message lỗi**.

## 16. Những phản mẫu và checklist rà soát

| Phản mẫu | Hệ quả | Cách sửa |
|---|---|---|
| Trả 410 cho mọi row có deleted_at | Tiết lộ lịch sử resource riêng tư; nhầm xóa mềm với gỡ lâu dài | Phân loại resource công khai/riêng tư và lifecycle |
| Dùng 403 cho “ID người khác”, 404 cho “ID không có” | Dò được ID hợp lệ | Truy vấn theo phạm vi nhìn thấy, trả 404 chung |
| Trả 404 cho cả thiếu token, bỏ qua WWW-Authenticate | Client không biết cần xác thực; sai hợp đồng bảo mật đã công bố | Để tầng auth xử lý 401 khi thiếu credential |
| Tra cứu bằng ID trước rồi mới kiểm tra tenant, trả lý do chi tiết | Rò rỉ metadata; dễ mắc BOLA/IDOR | Điều kiện tenant/ACL tại query và policy layer |
| Body của 404 chứa ownerId, trạng thái xóa hay tenant | Dù status chung vẫn lộ dữ liệu | ProblemDetail trung tính cho client, log chi tiết nội bộ |
| CDN cache public phản hồi 404 theo người dùng | User này nhận lỗi của user khác hoặc lộ metadata | no-store/private policy, xác minh cache key |
| Cache 410 quá lâu cho URI có thể khôi phục | Client tiếp tục xem resource là không còn | Dùng 404 khi chưa chắc, TTL/invalidation thích hợp |
| Nhầm trạng thái đơn CANCELED với resource đã biến mất | Mất khả năng tra cứu đơn vẫn tồn tại | 200 với trạng thái nghiệp vụ, hoặc mã hành động phù hợp |
| GET trả 404 nhưng HEAD/batch trả 403/410 | Lộ tồn tại qua đường vòng | Contract test toàn bộ route và phương thức |
| Dựa vào UUID ngẫu nhiên để bỏ kiểm tra quyền | Lộ ID qua log/URL vẫn thành truy cập trái quyền | Phân quyền bắt buộc cho mỗi request |

### Checklist áp dụng vào dự án REST API

- [ ] Mỗi nhóm resource có **chính sách công khai/riêng tư, owner/tenant và vòng đời** rõ ràng.
- [ ] Phân biệt **404 không có hoặc không tiết lộ** với **410 đã gỡ lâu dài và được phép công bố**.
- [ ] Định nghĩa 401/403 cùng 404; **WWW-Authenticate** hoạt động đúng khi cần xác thực.
- [ ] Lọc resource bằng **principal/tenant/ACL đáng tin cậy** trước khi trả trạng thái về ID.
- [ ] Body lỗi không đưa ra **owner, tenant, lịch sử xóa, thông tin nội bộ** khi phải ẩn.
- [ ] GET, HEAD, resource con, batch, list, count, search áp dụng cùng phạm vi nhìn thấy.
- [ ] Cache-Control được chỉ định rõ cho public 404/410 và private 404/401/403; thử qua cache/CDN.
- [ ] 410 dùng khi có bằng chứng phù hợp về **gỡ bỏ lâu dài**, không suy đoán từ mọi thao tác DELETE.
- [ ] DELETE, PUT/PATCH có semantics/idempotency rõ, không tự áp một status cho mọi phương thức.
- [ ] Hợp đồng OpenAPI nêu đủ response 404/410/401/403 theo chính sách thực tế và schema lỗi nhất quán.
- [ ] Test phân biệt ID có thật khác tenant, ID không có, ID đã xóa, token sai/hết hạn, HEAD/304, cache và route con.
- [ ] Log, metrics, tracing và rate limit đủ phát hiện enumeration mà không tiết lộ dữ liệu nhạy cảm.

**Thông điệp cần ghi nhớ:** **404 là một câu trả lời về biểu diễn hiện tại *và* quyền tiết lộ thông tin; 410 là một tuyên bố mạnh hơn về việc resource không còn khả dụng lâu dài.** Trước khi chọn mã trạng thái, hãy hỏi người gọi có quyền biết resource từng hoặc đang tồn tại hay không. Sau đó thể hiện chính sách nhất quán trong truy vấn, HTTP status, body, cache, OpenAPI và bộ kiểm thử.
