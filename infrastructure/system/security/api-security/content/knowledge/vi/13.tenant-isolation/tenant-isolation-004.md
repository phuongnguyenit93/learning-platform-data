# Cross-tenant access test cho mọi endpoint

Trong chương **Tenant isolation** của module `SECURITY_API_SECURITY`, kiểm thử cross-tenant xác minh rằng một principal thuộc tenant này không thể đọc, sửa, xóa, suy ra hoặc gây tác động lên dữ liệu của tenant khác. Kiểm thử phải bao phủ mọi endpoint và mọi đường truy cập dữ liệu, không chỉ endpoint xem chi tiết một bản ghi. Một API có thể bảo vệ tốt `GET /orders/{id}` nhưng vẫn làm lộ dữ liệu qua danh sách, tìm kiếm, export, nested resource, GraphQL resolver, file download hoặc background job.

Mục tiêu là biến tenant boundary thành một thuộc tính có thể kiểm chứng tự động: với mỗi thao tác, server chỉ trả dữ liệu và thực hiện side effect trong phạm vi tenant cùng quan hệ được phép của principal. Bài viết trình bày cách lập danh mục endpoint, tạo fixture nhiều tenant, xây dựng ma trận test, kiểm tra cả response lẫn trạng thái hệ thống, và đưa kiểm thử vào CI.

## 1. Xác định điều gì cần được chứng minh

Cross-tenant access test kiểm tra ranh giới giữa các tenant trong toàn bộ luồng request. Một request bị từ chối đúng khi đồng thời thỏa mãn các điều kiện sau:

- Không trả dữ liệu của tenant ngoài phạm vi, kể cả field lồng nhau, metadata, count, facet, snippet hoặc trạng thái tồn tại của tài nguyên nếu chính sách yêu cầu che giấu.
- Không trả nội dung tài nguyên ngoài phạm vi và không thực hiện hành động thay đổi hoặc side effect trên tài nguyên đó.
- Không tạo message, job, file, giao dịch hoặc lời gọi dịch vụ ngoài ý muốn.
- Không dùng tenant ID do client tự khai báo làm căn cứ cấp quyền.
- Không để cache, cursor, token, file URL hoặc tác vụ nền mang quyền từ tenant khác sang request hiện tại.
- Không làm rò dữ liệu qua log, error response, header, trace hoặc kênh truy cập gián tiếp.

Không đồng nhất “response là `403` hoặc `404`” với “tenant isolation đã được bảo đảm”. Response code chỉ là một phần của kết quả. Một endpoint có thể trả `404` nhưng vẫn tạo bản ghi, phát event hoặc gửi email trước khi từ chối. Test cần xác minh cả trạng thái dữ liệu và các tác động phụ.

### 1.1. Phân biệt tenant isolation với quyền truy cập trong tenant

Hai loại kiểm tra cần được bao phủ riêng:

| Loại kiểm tra | Câu hỏi | Ví dụ |
|---|---|---|
| Cross-tenant | Principal của tenant A có chạm được dữ liệu tenant B không? | User A thử đọc đơn hàng thuộc B |
| Intra-tenant authorization | Principal trong cùng tenant có đúng quyền trên đối tượng không? | Viewer của A thử xóa project chỉ owner được xóa |

Một user có thể là thành viên của nhiều tenant. Trong trường hợp đó, membership ở tenant B không tự động mở rộng quyền ở tenant A. Test phải xác minh quyền theo tenant đang hoạt động và quan hệ cụ thể với đối tượng.

### 1.2. Xác định endpoint toàn cục có chủ đích

Không phải mọi endpoint đều thuộc một tenant. Ví dụ, trang trạng thái dịch vụ, danh mục quốc gia hoặc tài liệu API có thể là tài nguyên toàn cục. Với mỗi endpoint như vậy, ghi rõ lý do không áp dụng tenant filter, dữ liệu được phép công khai và quyền cần có nếu endpoint không dành cho mọi người.

Không để endpoint bị bỏ qua chỉ vì chưa xác định được tenant. Trạng thái “global” phải là quyết định thiết kế được review và có test tương ứng, không phải mặc định cho route không nằm trong danh mục.

## 2. Lập danh mục endpoint và đường truy cập

Muốn test mọi endpoint, trước tiên phải có danh sách đầy đủ. Dùng OpenAPI, router/controller mapping và danh sách handler thực tế để tạo inventory. OpenAPI là nguồn tốt để bắt đầu nhưng có thể bỏ sót endpoint nội bộ, GraphQL, websocket, webhook, actuator, download route hoặc consumer xử lý job.

Với mỗi operation, ghi các thông tin:

| Trường | Nội dung cần ghi |
|---|---|
| Operation ID | Định danh ổn định trong OpenAPI hoặc router |
| Method và path | Ví dụ `GET /v1/tenants/{tenantId}/orders/{orderId}` |
| Tài nguyên | Order, invoice, project, file, report... |
| Tenant source | Claim đã xác minh, tenant context, hoặc membership được tra cứu |
| Authorization | Quyền chức năng, membership, ownership, relationship |
| Dữ liệu đầu vào | Path, query, header, body, file, cursor, webhook payload |
| Tác động | Đọc, ghi, xóa, phát event, gọi dịch vụ ngoài, tạo job |
| Kênh gián tiếp | Cache, search, export, signed URL, queue, GraphQL... |
| Kết quả từ chối | `403`, `404` hoặc mã lỗi theo contract |
| Test ID | Tên test hoặc nhóm test chứng minh tenant boundary |

Phân loại operation theo hành vi để chọn kiểm thử phù hợp:

- **Read detail:** đọc một tài nguyên theo ID.
- **Read collection:** danh sách, pagination, search, filter, count, autocomplete.
- **Write:** tạo mới, cập nhật, xóa, chuyển trạng thái, upload.
- **Bulk:** thao tác với nhiều ID trong một request.
- **Nested:** tài nguyên con được truy cập qua tài nguyên cha.
- **Async:** export, import, báo cáo, job hoặc message xử lý sau.
- **Indirect:** file download, cache, GraphQL, websocket, webhook callback hoặc endpoint phụ.

Một operation có thể thuộc nhiều nhóm. Ví dụ tạo export là write ở bước tạo job và read ở bước worker thu thập dữ liệu; cần kiểm tra cả hai thời điểm.

### 2.1. Đừng chỉ quét controller công khai

Inventory cần bao gồm các route và luồng xử lý có thể truy cập dữ liệu tenant:

- REST controller và endpoint quản trị.
- GraphQL query, mutation, field resolver và subscription.
- Websocket message handler và channel subscription.
- Webhook nhận từ đối tác và callback gửi sang đối tác.
- Download/upload file và signed URL.
- Export/import, scheduled task và background worker.
- Search, reporting, analytics và endpoint thống kê.
- Internal API giữa các service.

Với mỗi kênh, xác định danh tính và tenant context được truyền bằng cách nào. Một message nội bộ vẫn cần được xác minh nguồn và phạm vi; việc nó đi qua queue hoặc mạng riêng không làm dữ liệu tự động đáng tin.

## 3. Tạo fixture có ít nhất hai tenant độc lập

Fixture là dữ liệu nền mà test sử dụng. Một fixture tốt phải tạo ra những trường hợp có thể phân biệt rõ tenant, membership và ownership.

Ví dụ bộ dữ liệu:

| Thành phần | Tenant A (`acme`) | Tenant B (`globex`) |
|---|---|---|
| User owner | `alice-a` | `bob-b` |
| User viewer | `viewer-a` | `viewer-b` |
| Project | `project-a` | `project-b` |
| Order | `order-a` | `order-b` |
| File | `file-a` | `file-b` |
| Membership | Active | Active |

Thêm một số trường hợp biên:

- User có membership active ở cả A và B nhưng role khác nhau theo từng tenant.
- User đã bị thu hồi membership ở A nhưng còn giữ token hoặc cursor cũ.
- User không thuộc tenant nào trong hai tenant.
- Service principal chỉ được cấp quyền trên một tenant.
- Đối tượng con có ID hợp lệ nhưng thuộc parent hoặc tenant khác.
- Hai tenant có tài nguyên cùng tên; nếu hệ thống cho phép ID giống nhau trong namespace tenant, tạo dữ liệu có cùng ID ở hai tenant để kiểm tra khóa ghép.
- Đối tượng đã chuyển tenant hoặc đã bị xóa theo trạng thái nghiệp vụ.

Không tái sử dụng fixture một cách khiến test phụ thuộc thứ tự chạy. Mỗi test hoặc test class cần dữ liệu cô lập, reset trạng thái rõ ràng và không dùng ID ngẫu nhiên không thể truy vết trong failure output.

### 3.1. Gắn tenant context với principal

Tạo token/session test tương ứng với từng principal. Claim tenant trong token chỉ được sử dụng sau khi test security layer xác minh token. Nếu API cho phép chọn tenant qua path hoặc header, hãy kiểm tra server xác minh membership của principal trong tenant được yêu cầu.

Ít nhất cần các cặp sau:

| Principal đã xác thực | Tenant được request | Mục tiêu |
|---|---|---|
| User A | A | Luồng hợp lệ trong tenant của mình |
| User A | B | Thử đổi tenant sang phạm vi khác |
| User B | A | Thử truy cập ngược lại |
| User A và B | A rồi B | Xác minh quyền được tính riêng theo tenant đang chọn |
| User đã bị thu hồi membership A | A | Xác minh quyền cũ hết hiệu lực theo policy |
| Service A | B | Xác minh service không được mở rộng phạm vi |

Nếu token chỉ đại diện một tenant, việc gửi tenant khác trong path/header phải bị từ chối. Nếu principal có thể chọn tenant, server cần tra cứu membership và tạo tenant context mới sau khi xác minh. Test phải phản ánh đúng semantics của hệ thống.

## 4. Ma trận test cross-tenant cho từng operation

Không có một payload duy nhất phù hợp cho mọi endpoint. Hãy kết hợp loại operation, vị trí dữ liệu đầu vào, quan hệ tài nguyên và side effect để tạo test case. Mục tiêu là ít nhất có một test tenant isolation phù hợp cho mỗi operation và mở rộng thêm khi endpoint có nhiều đường truy cập.

### 4.1. Ma trận cơ bản theo hành vi

| Loại operation | Test hợp lệ | Test cross-tenant bắt buộc | Điều cần xác minh |
|---|---|---|---|
| GET detail | User A đọc object A | User A yêu cầu object B | Không có dữ liệu B trong response hoặc metadata |
| GET list | User A xem collection A | Collection có dữ liệu A và B | Chỉ trả bản ghi được phép; count/cursor cũng đúng |
| Search/filter | Tìm object A | Query khớp cả object A và B | Không lộ hit, snippet, facet hoặc total của B |
| POST create | User A tạo object trong A | Gửi `tenantId=B` hoặc parent ID thuộc B | Object không được tạo trong B |
| PUT/PATCH | User A cập nhật object A | User A cập nhật object B | Dữ liệu B không đổi; không có side effect |
| DELETE | User A xóa object A | User A xóa object B | Object B còn nguyên và không phát event xóa |
| Nested resource | User A thao tác child A thuộc parent A | Ghép parent A với child B hoặc parent B với child A | Quan hệ cha-con và tenant đều được kiểm tra |
| Bulk | User A thao tác danh sách ID A | Trộn ID A và B | Kết quả đúng semantics all-or-nothing/partial |
| Export | User A tạo export A | Thử filter, ID hoặc job scope B | File chỉ chứa dữ liệu được phép |
| File download | User A tải file A | Dùng file ID hoặc signed URL của B | Không tải được nội dung B |
| Async job | User A tạo job A | Job tham chiếu tài nguyên B hoặc membership bị thu hồi | Worker kiểm tra lại tenant và grant theo policy |

### 4.2. Biến đổi request có hệ thống

Với endpoint có tenant context, thay đổi từng nguồn dữ liệu có thể ảnh hưởng đến phạm vi:

- Path tenant ID: đổi A thành B.
- Path resource ID: giữ tenant A nhưng thay ID bằng object B.
- Parent/child ID: dùng parent A cùng child B.
- Query parameter: thêm `tenantId=B`, `ownerId` hoặc filter khác nếu endpoint hỗ trợ.
- Header: thử tenant header, organization header hoặc custom scope header.
- JSON body: thêm hoặc sửa `tenantId`, `ownerId`, `createdBy`, `accountId`.
- Bulk array: trộn ID A, B và ID không tồn tại.
- Cursor/page token: tái sử dụng cursor được phát hành trong tenant A ở tenant B.
- File metadata: thay object key, storage path hoặc resource reference.
- Webhook/job payload: thay tenant/resource reference và xác minh chữ ký hoặc danh tính producer.

Chỉ thử các trường có liên quan đến contract và kiến trúc endpoint. Nếu một trường không được hỗ trợ, test nên xác minh request bị từ chối hoặc trường bị bỏ qua đúng theo contract. Không mặc định mọi endpoint phải nhận `tenantId` trong body.

### 4.3. Thử cả ID hợp lệ và ID không tồn tại

Một test chỉ dùng ID ngẫu nhiên không tồn tại có thể không phát hiện BOLA. Luôn có trường hợp dùng ID thật của tenant khác, vì đó là điều kiện kiểm tra quan trọng nhất. Đồng thời thử ID không tồn tại để xác minh API không tạo ra khác biệt phản hồi làm lộ sự tồn tại của tài nguyên nếu chính sách yêu cầu che giấu.

Nếu ID toàn cục và không thể trùng giữa tenant, vẫn phải kiểm tra tenant predicate. Tính khó đoán hoặc duy nhất của UUID không thay thế authorization.

## 5. Kiểm thử đọc dữ liệu: detail, list, search và metadata

Đọc dữ liệu không chỉ là lấy nội dung một bản ghi. Các thông tin phụ có thể tiết lộ sự tồn tại hoặc quy mô dữ liệu của tenant khác.

### 5.1. Detail endpoint

Với `GET /orders/{orderId}`, thực hiện ít nhất hai request: user A đọc `order-a` thành công và user A thử đọc `order-b`. Kết quả từ chối phải theo contract, ví dụ `404` để che giấu tài nguyên hoặc `403` khi chính sách cho phép công bố sự tồn tại. Kiểm tra response không chứa customer name, amount, trạng thái, tenant ID hoặc error detail của order B.

Nếu endpoint trả object có quan hệ lồng nhau, kiểm tra cả nested customer, payment, attachment, comment và audit metadata. Đối tượng cha thuộc A không cho phép serializer trả nested object thuộc B do quan hệ dữ liệu sai.

### 5.2. Collection và pagination

Seed dữ liệu xen kẽ A và B, sau đó gọi list bằng principal A. Kiểm tra mọi phần tử thuộc tập được phép của A. Không chỉ kiểm tra trang đầu: chạy qua nhiều trang và xác minh không có bản ghi B xuất hiện ở page tiếp theo.

Kiểm tra:

- `totalElements`, `totalCount` hoặc tổng kết quả chỉ tính dữ liệu caller được phép xem.
- `nextCursor` và `previousCursor` không mã hóa hoặc tham chiếu dữ liệu B theo cách có thể khai thác.
- Cursor phát hành ở A không thể bỏ qua filter khi dùng trong B.
- Sorting, grouping và pagination được thực hiện trên tập dữ liệu đã lọc theo quyền.
- Không trả tên tenant, owner, ID hoặc metadata của B trong page summary.

Một implementation lọc dữ liệu sau khi truy vấn toàn bộ collection có thể trả đúng các phần tử nhưng vẫn lộ count, tốn tài nguyên và tạo race. Kiểm thử integration cần xác minh query/repository scope hoặc kết quả database phù hợp, không chỉ dựa vào UI.

### 5.3. Search, filter, autocomplete và aggregate

Search index và reporting store phải áp dụng tenant filter ở phía server. Test query có từ khóa khớp dữ liệu ở cả A và B, sau đó kiểm tra:

- Hits chỉ chứa tài liệu caller được phép xem.
- Snippet và highlight không chứa nội dung B.
- Facet, bucket, group count và total không tiết lộ dữ liệu ngoài phạm vi.
- Autocomplete không gợi ý tên khách hàng, project hoặc tài liệu B.
- Bộ lọc `owner`, `status`, `createdBy` không thể mở rộng phạm vi.
- Export kết quả search dùng cùng policy với endpoint search.

Aggregate có thể làm lộ thông tin ngay cả khi không trả từng bản ghi. Nếu một báo cáo cho biết số giao dịch hoặc doanh thu của tenant B, đó vẫn là rò rỉ cross-tenant.

## 6. Kiểm thử ghi dữ liệu và side effect

Với endpoint tạo, cập nhật, xóa hoặc chuyển trạng thái, response từ chối chưa đủ. Cần chụp trạng thái trước request và so sánh sau request.

### 6.1. Create

Gửi request tạo tài nguyên trong tenant A nhưng chèn `tenantId=B`, `ownerId` thuộc B hoặc parent ID thuộc B. Kiểm tra server lấy tenant và actor từ security context, không tin các trường do client tự khai báo.

Kết quả mong đợi có thể là từ chối trường lạ, bỏ qua trường server-managed hoặc từ chối quan hệ parent ngoài phạm vi theo contract. Dù chọn semantics nào, object mới không được tạo trong B và không được gắn với tài nguyên B.

### 6.2. Update và delete

Với object B, user A thử đổi field bình thường, field nhạy cảm và trạng thái. Kiểm tra:

- Giá trị lưu trữ không thay đổi.
- `updatedAt`, version hoặc audit row không bị thay đổi ngoài ý muốn.
- Không phát event `OrderUpdated`, `ResourceDeleted` hoặc message tương đương.
- Không gọi dịch vụ ngoài, gửi thông báo hoặc tạo tác vụ nền.
- Response không trả representation của object B.

Nếu endpoint có optimistic locking, test cả version hợp lệ và version cũ để bảo đảm conflict không bỏ qua tenant predicate.

### 6.3. Bulk operations

Với danh sách `[objectA1, objectB1]`, contract cần quy định all-or-nothing hay partial success.

- **All-or-nothing:** nếu có một ID ngoài phạm vi, không đối tượng nào bị thay đổi.
- **Partial success:** chỉ đối tượng caller được phép mới được xử lý; response liệt kê kết quả theo cách không tiết lộ thông tin của ID ngoài phạm vi.

Không chấp nhận hành vi ngẫu nhiên phụ thuộc thứ tự ID hoặc transaction. Test thêm danh sách trùng ID, ID không tồn tại và danh sách lớn sát giới hạn.

### 6.4. Side effect phải được kiểm tra riêng

Theo loại nghiệp vụ, kiểm tra số lượng hoặc nội dung của:

- Outbox event và message trong queue.
- Email, SMS, push notification hoặc webhook đã gửi.
- Payment/refund, inventory reservation hoặc shipment request.
- File được tạo, thay thế hoặc xóa.
- Audit record và trạng thái workflow.
- Background job hoặc scheduled task.

Nếu một request bị từ chối nhưng đã phát message trước khi transaction rollback, hệ thống vẫn có thể tạo side effect ngoài ý muốn. Với external service, dùng mock hoặc sandbox trong test và xác minh không có request được gửi.

## 7. Kiểm thử tenant context, membership và thu hồi quyền

Tenant context thường được hình thành từ token, session hoặc tenant selector. Test phải xác minh nguồn context và thời điểm quyền có hiệu lực.

Các trường hợp cần có:

1. Token A truy cập object A: được phép theo role/relationship.
2. Token A đổi tenant path/header thành B: bị từ chối nếu token không có membership B.
3. User có membership A và B: quyền được tính theo tenant đang hoạt động, không dùng role của tenant còn lại.
4. Membership A bị thu hồi: request mới bị từ chối theo thời hạn hiệu lực đã công bố.
5. Token được phát hành trước khi thu hồi: hệ thống xử lý theo cơ chế revocation, token lifetime hoặc membership revalidation đã chọn.
6. Role hạ từ admin xuống viewer: các thao tác ghi không tiếp tục được phép bởi cache hoặc claim cũ ngoài thời hạn được chấp nhận.
7. Service principal A gọi service B: audience, scope và tenant grant không cho phép mở rộng quyền.
8. Tenant bị khóa hoặc suspended: endpoint dữ liệu áp dụng cùng policy cho request đồng bộ và tác vụ nền.

Nếu hệ thống cho phép chọn tenant ở mỗi request, test chuyển qua lại A/B trong cùng session. Đảm bảo request tenant B không kế thừa context, cache hoặc transaction state của request A.

## 8. Kiểm thử các kênh gián tiếp

Cross-tenant bug thường xuất hiện khi dữ liệu đi qua thành phần khác với REST controller chính.

### 8.1. File upload, download và signed URL

- User A không thể tải file B bằng cách thay file ID hoặc storage key.
- Endpoint cấp signed URL xác minh quyền trước khi ký.
- Signed URL chỉ cho phép object và method dự kiến, có thời hạn phù hợp.
- URL của B không được trả trong response hoặc log của A.
- Upload không thể ghi đè object key thuộc B.
- Metadata file, thumbnail, preview và OCR output cũng giữ tenant scope.

Test signed URL cần phân biệt quyền tại thời điểm cấp URL với quyền khi sử dụng URL. Signed URL thường là bearer capability có thể tiếp tục hoạt động đến khi hết hạn; thiết kế phải chọn thời hạn và cơ chế thu hồi phù hợp với độ nhạy cảm.

### 8.2. Export, import và background job

Khi user A yêu cầu export, job cần giữ tenant context và actor identity đã xác minh. Worker phải truy vấn dữ liệu theo tenant và policy, không nhận danh sách ID tùy ý rồi đọc bằng quyền service rộng.

Test các tình huống:

- A tạo export chỉ chứa dữ liệu A.
- A thay filter hoặc resource ID để yêu cầu dữ liệu B.
- A xem job status hoặc download file export của B.
- Membership A bị thu hồi trước khi worker chạy hoặc trước khi download.
- Retry job không làm mất tenant context hoặc dùng lại context từ job trước.
- Import không thể gán record vào tenant B bằng field trong file CSV/JSON.

Với job chạy lâu, contract cần quy định quyền được chốt lúc enqueue hay được kiểm tra lại lúc thực thi/download. Test phải phản ánh semantics đó.

### 8.3. GraphQL và websocket

GraphQL có thể kiểm tra quyền ở resolver gốc nhưng bỏ sót field resolver hoặc nested relation. Test query yêu cầu nhiều tenant-aware field trong cùng một request, alias, fragment, batch và pagination. Kiểm tra cả error path không trả dữ liệu một phần của tenant B.

Với websocket, xác minh tenant context ở thời điểm handshake và khi subscribe vào channel. User A không được subscribe topic B bằng cách thay tenant ID hoặc resource ID. Khi membership bị thu hồi, kết nối/subscription phải bị đóng hoặc quyền được đánh giá lại theo policy.

### 8.4. Webhook và service-to-service

Webhook cần xác minh chữ ký hoặc cơ chế xác thực producer, chống replay và ánh xạ external account sang tenant phía server. Không tin `tenantId` trong payload chỉ vì chữ ký hợp lệ; chữ ký chứng minh nguồn gửi, còn mapping tenant vẫn phải được xác minh.

Với service-to-service, kiểm thử audience, scope, workload identity và delegation. Một service có quyền tenant A không được dùng token của nó để truy cập B. Nếu có cross-tenant grant hợp lệ, kiểm thử đúng phạm vi grant, thời hạn và audit.

## 9. Ví dụ kiểm thử integration với Spring Boot

Ví dụ dưới đây minh họa hai tenant có dữ liệu riêng và dùng JWT test principal. Route và repository là ví dụ; cần điều chỉnh theo API thực tế. Helper `seedTenantsAndOrders()` cần reset hoặc tạo fixture cô lập cho từng test, gồm tenant A/B, user A/B và order tương ứng; không để dữ liệu từ lần chạy trước làm test phụ thuộc thứ tự.

```java
@SpringBootTest
@AutoConfigureMockMvc
class OrderTenantIsolationIT {

    private static final UUID TENANT_A = UUID.fromString(
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");
    private static final UUID TENANT_B = UUID.fromString(
            "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb");
    private static final UUID ORDER_A = UUID.fromString(
            "11111111-1111-1111-1111-111111111111");
    private static final UUID ORDER_B = UUID.fromString(
            "22222222-2222-2222-2222-222222222222");

    @Autowired MockMvc mockMvc;
    @Autowired JdbcTemplate jdbc;

    @BeforeEach
    void setUp() {
        seedTenantsAndOrders();
    }

    @Test
    void tenantAUserCanReadOwnOrder() throws Exception {
        mockMvc.perform(get("/v1/tenants/{tenantId}/orders/{orderId}",
                        TENANT_A, ORDER_A)
                .with(jwt().jwt(token -> token
                        .subject("user-a")
                        .claim("tenant_id", TENANT_A.toString()))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(ORDER_A.toString()));
    }

    @Test
    void tenantAUserCannotReadTenantBOrder() throws Exception {
        mockMvc.perform(get("/v1/tenants/{tenantId}/orders/{orderId}",
                        TENANT_A, ORDER_B)
                .with(jwt().jwt(token -> token
                        .subject("user-a")
                        .claim("tenant_id", TENANT_A.toString()))))
            .andExpect(status().isNotFound());

        Integer stillExists = jdbc.queryForObject(
                "select count(*) from orders where id = ? and tenant_id = ?",
                Integer.class, ORDER_B, TENANT_B);
        assertThat(stillExists).isEqualTo(1);
    }

    @Test
    void tenantAUserCannotSelectTenantBInPath() throws Exception {
        mockMvc.perform(get("/v1/tenants/{tenantId}/orders/{orderId}",
                        TENANT_B, ORDER_B)
                .with(jwt().jwt(token -> token
                        .subject("user-a")
                        .claim("tenant_id", TENANT_A.toString()))))
            .andExpect(status().isNotFound());
    }
}
```

Đoạn test giả định contract che giấu tài nguyên ngoài phạm vi bằng `404`; nếu API công bố `403`, hãy assert theo contract đã chọn. Có thể bổ sung assertion để response không chứa marker nhạy cảm được seed trong order B. `jwt()` là post-processor của Spring Security Test tạo một principal đã xác thực cho test; nó không kiểm tra chữ ký JWT, issuer hoặc audience. Các điều kiện xác minh token cần có integration test riêng cho decoder/resource server. Test ở đây cần giữ security chain và authorization thực tế của ứng dụng, không mock phần tenant authorization, để kiểm tra cả filter, context resolver, service và repository.

### 9.1. Kiểm tra cập nhật không tạo side effect

Với endpoint ghi, chụp giá trị trước request, số event/outbox và số job. Sau request bị từ chối, xác minh tất cả giữ nguyên:

```java
@Test
void tenantAUserCannotChangeTenantBOrder() throws Exception {
    String originalAddress = jdbc.queryForObject(
            "select shipping_address from orders where id = ?",
            String.class, ORDER_B);
    Integer eventCountBefore = jdbc.queryForObject(
            "select count(*) from outbox_events where aggregate_id = ?",
            Integer.class, ORDER_B.toString());

    mockMvc.perform(patch("/v1/tenants/{tenantId}/orders/{orderId}",
                    TENANT_A, ORDER_B)
            .with(jwt().jwt(token -> token
                    .subject("user-a")
                    .claim("tenant_id", TENANT_A.toString())))
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {"shippingAddress":"Address controlled by tenant A"}
                """))
        .andExpect(status().isNotFound());

    String addressAfter = jdbc.queryForObject(
            "select shipping_address from orders where id = ?",
            String.class, ORDER_B);
    Integer eventCountAfter = jdbc.queryForObject(
            "select count(*) from outbox_events where aggregate_id = ?",
            Integer.class, ORDER_B.toString());

    assertThat(addressAfter).isEqualTo(originalAddress);
    assertThat(eventCountAfter).isEqualTo(eventCountBefore);
}
```

Đây là minh họa cho một side effect được lưu trong database. Nếu ứng dụng gửi email, gọi payment gateway hoặc publish message trực tiếp, hãy dùng fake server, mock transport hoặc test broker để xác minh không có lời gọi nào xảy ra. Với outbox, cần kiểm tra đúng transaction và trạng thái commit/rollback của ứng dụng.

### 9.2. Test helper không được tạo lỗ hổng

Test helper nên tạo token qua cơ chế test của framework nhưng vẫn giữ các claim cần kiểm tra. Không viết helper luôn gắn tenant ID từ path vào JWT vì như vậy test sẽ vô tình hợp thức hóa tenant do client yêu cầu. Principal và tenant claim cần là hai đầu vào độc lập để có thể thử mismatch.

## 10. Kiểm thử ở các tầng khác nhau

Mỗi tầng bắt được một loại lỗi. Chỉ dùng unit test policy không chứng minh controller đã gọi policy; chỉ dùng API test không luôn phát hiện constraint dữ liệu sai hoặc RLS bị cấu hình nhầm.

| Tầng | Nội dung | Ví dụ |
|---|---|---|
| Unit | Policy, tenant resolver, ownership rule | Principal A không có membership B |
| Repository/integration | Tenant predicate, join, update/delete scope | Query không trả object B cho context A |
| API integration | Security filter, controller, serialization, error mapping | JWT A gọi endpoint với ID B |
| Data integrity | Foreign key, unique key, RLS, transaction | Child A không thể tham chiếu parent B |
| Async integration | Queue consumer, export worker, retry | Job A không đọc dữ liệu B |
| End-to-end | Gateway, cache, search, storage và service thật | Request qua đường triển khai không rò dữ liệu |
| Security regression | IDOR/BOLA, tenant switching, metadata leak | Bộ test lặp lại cho mọi release |

Không cần chạy toàn bộ E2E cho mọi biến thể ở mỗi commit. Có thể chạy unit và integration trong mỗi pull request, sau đó chạy một bộ E2E đại diện trong pipeline release. Tuy nhiên, mọi operation phải có test tự động ở ít nhất tầng phù hợp và được truy vết trong inventory.

## 11. Tự động hóa coverage cho mọi endpoint

Một bộ test tốt cần chứng minh độ bao phủ, không chỉ có nhiều test case. Tạo bảng coverage với một dòng cho mỗi operation:

| Operation ID | Tenant-aware? | Cross-tenant test | Side-effect test | Kênh phụ | Trạng thái |
|---|---|---|---|---|---|
| `getOrder` | Có | `getOrder_deniesOtherTenant` | Không áp dụng | Cache | Có test |
| `listOrders` | Có | `listOrders_filtersOtherTenant` | Không áp dụng | Cursor/search | Có test |
| `updateOrder` | Có | `updateOrder_doesNotChangeOtherTenant` | Outbox | Event | Có test |
| `deleteProject` | Có | `deleteProject_deniesOtherTenant` | Event/job | Audit | Có test |
| `getServiceStatus` | Global | `status_isPublicAndTenantIndependent` | Không áp dụng | CDN | Có test |

Tên operation trong bảng chỉ là ví dụ. Trong dự án, có thể sinh danh sách operation từ OpenAPI rồi đối chiếu với test ID hoặc metadata tùy chỉnh. Build nên cảnh báo khi có operation mới chưa được phân loại tenant-aware/global hoặc chưa có test tương ứng.

### 11.1. Dùng contract metadata để đánh dấu phạm vi

OpenAPI có thể dùng extension nội bộ như `x-tenant-scope` để khai báo operation cần tenant isolation:

```yaml
paths:
  /v1/orders/{orderId}:
    get:
      operationId: getOrder
      x-tenant-scope: required
      responses:
        '200':
          description: Order returned within the active tenant
        '404':
          description: Order not found in the active tenant
```

Extension này chỉ là metadata phục vụ review và tooling; nó không tự enforce authorization. CI có thể so sánh danh sách operation mang `x-tenant-scope: required` với danh sách test. Mọi ngoại lệ `global` cần có lý do, người review và test chứng minh hành vi công khai/độc lập tenant là có chủ đích.

### 11.2. Không dùng coverage theo số lượng test làm bằng chứng duy nhất

Một operation có thể có mười test nhưng tất cả chỉ kiểm tra user A truy cập dữ liệu A. Coverage theo dòng code cũng không chứng minh policy đúng. Đo coverage theo tình huống: principal, tenant, object relation, operation, input mutation và side effect. Báo cáo cần chỉ ra operation nào thiếu tình huống cross-tenant, thay vì chỉ đếm tổng số test.

## 12. Cross-tenant access hợp lệ và cách test ngoại lệ

Một số chức năng cần truy cập nhiều tenant, chẳng hạn support agent, billing platform, migration hoặc báo cáo tổng hợp. Không nên làm cho test suite coi mọi cross-tenant access đều là lỗi nếu hệ thống có grant đặc biệt được thiết kế.

Với mỗi ngoại lệ, xác định:

- Principal hoặc workload nào được cấp quyền.
- Tenant, loại tài nguyên và operation được phép.
- Grant có thời hạn, điều kiện phê duyệt hoặc ticket tham chiếu hay không.
- Field nào được xem và dữ liệu nào phải mask.
- Audit event nào được tạo và ai có quyền xem.
- Cách thu hồi grant và hành vi sau khi hết hạn.

Test cần có cả trường hợp grant hợp lệ và grant không hợp lệ: đúng tenant/đúng object/đúng action được phép; sai tenant, sai resource, sai action, hết hạn hoặc đã thu hồi đều bị từ chối. Một `support:read` chung không nên tự động mở quyền đọc mọi loại dữ liệu.

## 13. Quan sát và điều tra khi test phát hiện lỗi

Khi test thất bại, cần đủ thông tin để xác định operation, principal, tenant context và resource bị tác động mà không làm lộ dữ liệu thật.

Nên ghi trong kết quả test:

- Operation ID và test case.
- Principal test và tenant được xác minh.
- Tenant của tài nguyên mục tiêu.
- Mã response và correlation ID.
- Snapshot trước/sau của dữ liệu liên quan.
- Số lượng event, job, file hoặc external call.
- Policy decision code nếu hệ thống có ghi nhận.

Không đưa token thật, secret, dữ liệu cá nhân production hoặc toàn bộ payload nhạy cảm vào log CI. Dùng fixture giả lập và giá trị dễ nhận biết. Nếu phát hiện rò rỉ, giữ response body trong artifact bảo mật có giới hạn truy cập; tránh phát tán dữ liệu nhạy cảm qua log công khai.

Trong môi trường production, có thể theo dõi các tín hiệu như số lần truy cập chéo tenant bị từ chối, mẫu thử ID tuần tự, tăng đột biến `403/404`, query bất thường và thao tác support cross-tenant. Log sự kiện cần ghi actor, tenant context, resource type, action, decision và correlation ID ở mức tối thiểu.

## 14. Lỗi kiểm thử thường gặp

| Cách test chưa đủ | Vì sao bỏ sót lỗi | Cách cải thiện |
|---|---|---|
| Chỉ kiểm tra `403/404` | Request có thể đã tạo side effect | So sánh database, event, job và external call |
| Chỉ dùng ID không tồn tại | Không thử truy cập object B thật | Dùng ID hợp lệ từ tenant khác |
| Chỉ test detail endpoint | List, search, export hoặc file có thể rò | Inventory mọi operation và kênh phụ |
| Chỉ kiểm tra response items | Count, facet, cursor vẫn có thể lộ | Assert cả metadata và mọi trang |
| Mock policy trong API test | Bỏ qua lỗi wiring và repository | Dùng security chain và persistence thật trong integration test |
| Dùng token và tenant path cùng nguồn | Không tạo được mismatch | Tạo principal claim và requested tenant độc lập |
| Chỉ test một user mỗi tenant | Bỏ sót role, membership và share | Dùng nhiều principal với quan hệ khác nhau |
| Test job chỉ ở enqueue | Worker có thể chạy sai tenant | Kiểm tra cả thực thi, retry, status và download |
| Bỏ qua endpoint global | Ngoại lệ không có lý do hoặc test | Phân loại rõ và kiểm thử hành vi global |
| Đếm số test thay cho coverage | Test có thể lặp lại cùng happy path | Map test case theo operation và tình huống |

## 15. Checklist release tenant isolation

- [ ] Inventory bao gồm REST, GraphQL, websocket, webhook, internal API và async worker.
- [ ] Mỗi operation được đánh dấu tenant-aware hoặc global có lý do.
- [ ] Fixture có ít nhất hai tenant độc lập và nhiều principal/role.
- [ ] Có test dùng ID thật của tenant khác cho mọi operation đọc/ghi tài nguyên.
- [ ] Path, query, header, body, nested ID, bulk ID và cursor được kiểm tra theo contract.
- [ ] List, pagination, search, count, facet, autocomplete và export không lộ metadata tenant khác.
- [ ] Create/update/delete không tạo dữ liệu hoặc side effect ngoài tenant.
- [ ] Nested resource xác minh quan hệ parent-child và tenant.
- [ ] File, signed URL, cache, queue, job và retry giữ tenant context.
- [ ] Membership, role, token và grant bị thu hồi có hiệu lực theo semantics đã công bố.
- [ ] Cross-tenant privilege có test grant hợp lệ, sai phạm vi, hết hạn và thu hồi.
- [ ] Request bị từ chối không phát event, gửi thông báo hoặc gọi external service.
- [ ] Response, error, log và trace không làm lộ dữ liệu hoặc metadata ngoài phạm vi.
- [ ] Coverage được truy vết theo operation ID và là điều kiện trong CI.
- [ ] Test chạy độc lập, dữ liệu fixture được cô lập và không phụ thuộc thứ tự.

## Kết luận

Cross-tenant access test phải được thiết kế theo inventory operation và đường dữ liệu thực tế. Fixture nhiều tenant cùng principal có quan hệ khác nhau giúp phát hiện lỗi ở detail, collection, nested resource, bulk, search và tác vụ nền. Với mỗi request trái phép, hãy kiểm tra cả response, dữ liệu lưu trữ, metadata và side effect. Khi mọi operation được phân loại, có test ID truy vết và coverage được kiểm soát trong CI, tenant boundary trở thành một thuộc tính có thể kiểm chứng qua từng lần thay đổi API.
