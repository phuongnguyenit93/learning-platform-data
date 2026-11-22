# Quyền đọc object sau khi upload

Upload thành công chỉ chứng minh server đã nhận hoặc lưu một file. Nó không tự động cấp quyền đọc file cho mọi người biết được file ID, đường dẫn hoặc object key. Trong API bảo mật, quyền upload, xem metadata, preview, download, chia sẻ và xóa phải được xác định riêng theo principal, tenant, object, trạng thái file và mục đích nghiệp vụ.

Lỗi phổ biến là endpoint upload kiểm tra đăng nhập nhưng các đường đọc phía sau chỉ nhận file ID rồi trả nội dung từ object storage. Người dùng có thể thay ID để đọc file của người khác (IDOR/BOLA), truy cập file tenant khác, dùng thumbnail/export endpoint bỏ qua kiểm tra hoặc chia sẻ signed URL quá rộng. Cần áp dụng object-level authorization cho toàn bộ vòng đời file và mọi đường truy cập, kể cả khi dữ liệu được phục vụ qua CDN, object storage hoặc background worker.

## 1. Xác định tài sản và ranh giới quyền đọc

Một file thường có nhiều thành phần liên quan:

- **File record:** metadata trong database như file ID, uploader, tenant, trạng thái, phân loại dữ liệu và thời điểm tạo.
- **Object bytes:** nội dung thực tế trong filesystem, object storage hoặc storage service.
- **Derived objects:** thumbnail, preview, bản chuyển đổi PDF, OCR text, transcript, checksum hoặc metadata được trích xuất.
- **Access capability:** signed URL, download token hoặc quyền chia sẻ tạm thời.
- **Processing artifacts:** file tạm, bản quarantine, bản scan, export và dữ liệu do background job tạo ra.

Quyền đọc phải bao phủ mọi thành phần có thể tiết lộ nội dung gốc hoặc thông tin nhạy cảm. Nếu endpoint download kiểm tra owner nhưng thumbnail URL công khai, người dùng vẫn có thể đọc một phần nội dung. Nếu file gốc được bảo vệ nhưng OCR text trong search index không có ACL tương ứng, dữ liệu vẫn bị lộ.

### 1.1. Các câu hỏi cần trả lời

Với mỗi file, hệ thống phải biết:

1. Ai đã upload file?
2. File thuộc tenant, workspace, project, case hoặc object nghiệp vụ nào?
3. Ai được xem metadata và ai được đọc nội dung?
4. Có nhóm, role hoặc người được chia sẻ quyền đọc không?
5. File đã qua kiểm tra bảo mật và ở trạng thái được phép đọc chưa?
6. File có bị xóa, thu hồi, quarantine hoặc hết hạn không?
7. Signed URL hoặc cache nào đã được tạo?
8. Preview, thumbnail, OCR và export có kế thừa cùng policy không?
9. Khi owner, membership hoặc ACL thay đổi, quyền đọc được cập nhật thế nào?
10. Ai đã đọc, chia sẻ hoặc tải file và sự kiện đó được audit ở đâu?

Không thể trả lời những câu hỏi này chỉ bằng cách kiểm tra file ID có tồn tại trong storage.

## 2. Tách quyền upload khỏi quyền đọc

Upload và read là các action khác nhau. Nhân viên có thể được phép gửi chứng từ vào hồ sơ nhưng chỉ người phụ trách hồ sơ mới được xem chứng từ đó. Một người dùng có thể upload avatar của chính họ nhưng không được xem file riêng tư của người dùng khác.

Một policy có thể biểu diễn theo principal, action và resource:

| Thành phần | Ví dụ |
|---|---|
| Principal | User, service account, support operator |
| Action | upload, read_metadata, preview, download, share, delete |
| Resource | File record và object bytes |
| Context | Tenant, workspace, project, owner, trạng thái file, classification |
| Decision | allow hoặc deny kèm policy/version |

Không suy luận quyền đọc chỉ vì:

- Người dùng đã đăng nhập.
- Người dùng là người upload.
- Người dùng biết file ID.
- Người dùng thuộc cùng tổ chức nhưng không thuộc cùng tenant/project.
- File nằm trong bucket hoặc prefix mà client có thể đoán.
- Frontend đã hiển thị nút download.

Các điều kiện này có thể là dữ kiện đầu vào của policy, nhưng không tự tạo ra quyền đọc.

### 2.1. Uploader không phải lúc nào cũng là reader

Quy tắc đơn giản “uploader được đọc file” có thể phù hợp với ứng dụng cá nhân, nhưng không phù hợp với mọi nghiệp vụ:

- Nhân viên upload hóa đơn vào hồ sơ khách hàng; nhóm kế toán được đọc theo assignment.
- Người dùng upload tài liệu vào ticket; agent được đọc theo quyền ticket.
- Service account tạo file export; chỉ requester và operator được phép đọc kết quả.
- Một người rời workspace; file vẫn thuộc workspace và người còn quyền có thể tiếp tục đọc.
- File được upload nhầm; uploader có thể cần quyền yêu cầu xóa nhưng không được tự cấp quyền cho người khác.

Thiết kế quyền cần dựa trên chủ sở hữu nghiệp vụ của resource và quan hệ truy cập, không chỉ dựa vào người tạo bản ghi.

### 2.2. Quyền metadata và quyền nội dung

Metadata có thể tự nó là dữ liệu nhạy cảm: tên file, tên khách hàng, kích thước, loại tài liệu, thời gian tạo, người upload, trạng thái xử lý hoặc quan hệ với hồ sơ.

Có thể tách quyền:

- **file:read-metadata:** xem tên, loại, kích thước và trạng thái được phép.
- **file:preview:** xem preview hoặc rendition.
- **file:download:** lấy bytes gốc.
- **file:share:** tạo hoặc thay đổi quyền chia sẻ.
- **file:delete:** xóa hoặc yêu cầu xóa.

Một user có thể được xem file tồn tại nhưng không được tải nội dung, hoặc được xem preview đã che dữ liệu nhưng không được download bản gốc. Không trả toàn bộ metadata chỉ vì user không được đọc bytes.

## 3. Xây dựng policy theo tenant, owner và ACL

Một mô hình quyền đọc thực tế thường kết hợp nhiều quan hệ:

1. **Tenant boundary:** file thuộc tenant nào; principal có membership hợp lệ không?
2. **Parent resource:** file gắn với project, case, order, message hoặc record nào?
3. **Owner/uploader:** principal có quan hệ owner hoặc uploader được policy công nhận không?
4. **Role/assignment:** principal có role hoặc assignment phù hợp trong parent resource không?
5. **Explicit ACL/share grant:** file có được chia sẻ cho user/group cụ thể không?
6. **Classification:** file có thuộc nhóm confidential, restricted hoặc legal hold không?
7. **Lifecycle state:** file có ở trạng thái AVAILABLE và chưa bị thu hồi/xóa không?
8. **Purpose/context:** action có hợp lệ với mục đích, session hoặc workflow hiện tại không?

Ví dụ policy:

- User chỉ đọc file khi cùng tenant, có quyền đọc parent project và file ở trạng thái AVAILABLE.
- Người được chia sẻ trực tiếp có thể đọc nếu grant còn hiệu lực, đúng action và không vượt tenant boundary.
- Support operator chỉ đọc khi có quyền hỗ trợ phù hợp, lý do truy cập và audit theo quy trình.
- Service account chỉ đọc file phục vụ job được cấp scope và resource cụ thể.

Không cộng dồn quyền một cách tùy tiện. Nếu ACL cấp read nhưng tenant membership đã bị thu hồi, policy cần xác định rõ tenant boundary có ưu tiên deny hay không. Với dữ liệu tenant, thường nên coi tenant isolation là điều kiện bắt buộc trước mọi grant khác.

### 3.1. Quy tắc deny-by-default

Khi thiếu owner, tenant, parent resource, trạng thái hoặc policy không xác định, mặc định từ chối đọc. Không dùng logic “nếu không tìm thấy ACL thì cho phép uploader hoặc user đăng nhập”.

Decision function nên nhận principal đã xác thực, action, file record và context đáng tin cậy. Không lấy role hoặc tenant từ request body rồi dùng trực tiếp để ra quyết định.

### 3.2. Tránh quyền kế thừa quá rộng

Nếu file gắn với project, có thể kế thừa quyền từ project. Nhưng cần xác định:

- Thành viên project có được đọc mọi file hay chỉ file trong folder/label được cấp?
- Guest có quyền đọc project có được đọc file restricted không?
- File được chuyển sang project khác có giữ ACL cũ không?
- Khi user bị remove khỏi project, quyền đọc file và derived objects bị thu hồi lúc nào?
- File được share riêng có còn truy cập được khi project membership mất không?

Quy tắc kế thừa phải được ghi rõ và kiểm thử. Không để một endpoint dùng quyền project còn endpoint khác chỉ kiểm tra uploader.

## 4. Bảo vệ mọi đường đọc file

Không chỉ endpoint download mới cần authorization. Inventory tất cả đường có thể trả bytes hoặc metadata:

| Đường truy cập | Quyền cần kiểm tra |
|---|---|
| GET file metadata | read_metadata, tenant và trạng thái |
| GET file content/download | download, tenant, parent/ACL và AVAILABLE |
| GET thumbnail/preview | preview, rendition state và AVAILABLE |
| PDF render/page image | preview hoặc permission riêng |
| OCR/transcript/text extraction | read_content hoặc quyền dữ liệu tương đương |
| Export archive/ZIP | quyền đọc từng file và quyền export |
| Search result/snippet | quyền đọc metadata/nội dung được trích |
| Share link creation | share |
| Signed URL issuance | download/preview tại thời điểm cấp |
| Re-download qua CDN | Cache policy phải giữ đúng quyền |
| Background job đọc file | workload identity và authorization theo resource |
| Admin/support access | quyền đặc biệt, purpose và audit |

Một lỗi thường gặp là controller download kiểm tra permission nhưng thumbnail được lưu ở URL public hoặc route khác không gọi cùng service authorization. Hãy tập trung policy trong service dùng chung hoặc lớp authorization mà tất cả đường đọc đều gọi đến.

### 4.1. Không tin file ID hoặc object key do client gửi

File ID là selector để tìm resource, không phải credential. UUID ngẫu nhiên giảm khả năng đoán nhưng không thay thế authorization.

Object key như đường dẫn lưu trữ không nên được client tự chọn hoặc tự quyết định. Lưu storage key nội bộ trong database; client chỉ nhận opaque file ID. Khi xử lý request, server tìm file record theo ID, kiểm tra quyền rồi mới lấy storage key từ record đã xác minh.

Không cho client gửi trực tiếp bucket name, storage path hoặc filesystem path. Tránh nối path từ user input; điều đó có thể gây path traversal, đọc nhầm file hoặc truy cập prefix ngoài phạm vi.

## 5. Vòng đời file và trạng thái được phép đọc

File vừa upload không nhất thiết an toàn để đọc ngay. Một luồng phổ biến:

~~~mermaid
flowchart TD
    A[Upload initiated] --> B[Temporary or quarantine storage]
    B --> C[Validate size and format]
    C --> D[Malware scan and content inspection]
    D -->|Pass| E[AVAILABLE]
    D -->|Fail| F[REJECTED]
    E --> G[Read, preview or download with authorization]
    G --> H[Revoked, expired or delete requested]
    H --> I[UNAVAILABLE / DELETED]
~~~

Có thể dùng các trạng thái:

| Trạng thái | Ý nghĩa | Cho phép user đọc nội dung? |
|---|---|---|
| PENDING_UPLOAD | Đang chờ client upload | Không |
| QUARANTINED | Đã nhận bytes, đang cách ly | Chỉ scanner/processor được cấp quyền |
| SCANNING | Đang kiểm tra malware/format | Chỉ worker được cấp quyền |
| AVAILABLE | Đã đạt kiểm tra và sẵn sàng | Có, sau object authorization |
| REJECTED | Không đạt policy | Không |
| REVOKED | Quyền hoặc file đã bị thu hồi | Không |
| DELETE_PENDING | Đang xử lý xóa | Thường từ chối đọc mới |
| DELETED | Đã xóa hoặc không còn khả dụng | Không |

Không dựa vào extension hoặc Content-Type do client gửi để đánh dấu file an toàn. Scanner cần đọc bytes thực tế, kiểm tra định dạng và giới hạn parser. Nếu xử lý bất đồng bộ, chỉ chuyển sang AVAILABLE sau khi tất cả bước bắt buộc thành công.

### 5.1. Tách storage quarantine và storage phục vụ

Có thể lưu file chưa kiểm tra trong bucket/prefix riêng tư dành cho quarantine. Chỉ scanner/worker có quyền đọc vùng đó. Khi file đạt kiểm tra, chuyển hoặc promote sang vùng lưu trữ dành cho nội dung khả dụng.

Không đặt file quarantine vào public bucket hoặc tạo signed URL cho user trong lúc đang scan. Nếu cần cho uploader xem tiến trình, trả metadata trạng thái thay vì bytes.

### 5.2. Xử lý thất bại và retry

Nếu scanner timeout, parser lỗi hoặc job chưa hoàn tất, file phải tiếp tục ở trạng thái chưa khả dụng. Retry cần idempotent và không tạo nhiều bản ghi file/ACL. Nếu một file đã bị REJECTED hoặc REVOKED, retry job cũ không được tự đưa nó trở lại AVAILABLE nếu chưa có quyết định mới được phê duyệt.

## 6. Thiết kế API đọc file

Một API có thể dùng các route riêng:

~~~http
GET /api/files/{fileId}
GET /api/files/{fileId}/content
GET /api/files/{fileId}/preview
POST /api/files/{fileId}/share
DELETE /api/files/{fileId}
~~~

Mỗi operation cần permission riêng. Ví dụ:

| Operation | Kiểm tra chính |
|---|---|
| GET /files/{id} | read_metadata, tenant và trạng thái |
| GET /files/{id}/content | download, tenant, parent/ACL và AVAILABLE |
| GET /files/{id}/preview | preview, rendition state và AVAILABLE |
| POST /files/{id}/share | share, recipient policy, expiry và audit |
| DELETE /files/{id} | delete, owner/role, legal hold và workflow |

Không dựa vào việc frontend ẩn route hoặc nút. Người dùng có thể gọi trực tiếp method/path nếu biết endpoint.

### 6.1. Trình tự xử lý download

Một luồng server-side nên:

1. Xác thực principal từ session/token.
2. Tìm file record theo file ID trong phạm vi tenant hoặc catalog phù hợp.
3. Kiểm tra trạng thái file là AVAILABLE.
4. Kiểm tra action file:download.
5. Kiểm tra parent resource, owner, membership hoặc ACL.
6. Lấy storage key từ record đã xác minh.
7. Đọc object qua storage identity riêng của service.
8. Trả stream với headers an toàn và audit outcome.

Không lấy object bytes trước rồi mới kiểm tra quyền. Điều này có thể gây lãng phí tài nguyên, tạo side channel hoặc vô tình ghi nội dung vào cache/log trước khi quyết định deny.

### 6.2. Ví dụ Spring service

~~~java
public DownloadResult download(
        AuthenticatedPrincipal principal,
        UUID fileId) {

    FileRecord file = fileRepository.findById(fileId)
            .orElseThrow(NotFoundException::new);

    if (file.getStatus() != FileStatus.AVAILABLE) {
        throw new NotFoundException();
    }

    fileAuthorization.requireAllowed(
            principal, FileAction.DOWNLOAD, file);

    StorageObject object = storageClient.open(file.getStorageKey());

    auditService.recordFileRead(
            principal.id(), file.getId(), FileAction.DOWNLOAD);

    return new DownloadResult(
            object.stream(),
            file.getSafeDownloadName(),
            file.getVerifiedContentType(),
            object.length());
}
~~~

Đây là ví dụ cấu trúc. Trong hệ thống multi-tenant, repository nên giới hạn theo tenant context đã xác minh hoặc authorization service phải kiểm tra tenant trước khi truy cập bytes. Việc trả 404 cho file không tồn tại hoặc file ngoài phạm vi có thể giúp giảm enumeration; chọn status theo hợp đồng API và giữ hành vi nhất quán.

### 6.3. Không chỉ dùng annotation ở controller

Annotation như PreAuthorize có thể bảo vệ function-level permission, nhưng thường không đủ để kiểm tra quan hệ cụ thể giữa principal và file. Object policy cần nhận file record và context của nó.

Có thể dùng cả hai lớp:

~~~java
@PreAuthorize("hasAuthority('file:download')")
@GetMapping("/api/files/{fileId}/content")
public ResponseEntity<StreamingResponseBody> download(
        @PathVariable UUID fileId,
        Authentication authentication) {
    // Service vẫn kiểm tra object, tenant, trạng thái và ACL.
}
~~~

Annotation chỉ là lớp đầu; service/repository phải thực thi object-level authorization. Background job hoặc internal caller có thể gọi service mà không đi qua controller, nên policy không nên chỉ nằm ở web layer.

## 7. Bảo vệ object storage và storage key

Object storage nên được cấu hình private-by-default:

- Bucket/container không public; block public access ở cấp account/bucket nếu nền tảng hỗ trợ.
- Service dùng workload identity/role có quyền tối thiểu trên đúng bucket và prefix.
- Client không nhận credential storage có quyền list/read toàn bucket.
- Storage key được sinh ở server, không dùng nguyên filename do client gửi làm key.
- Tách prefix hoặc bucket theo môi trường và mục đích; không coi prefix là authorization duy nhất.
- Không cho client ghi đè object của user khác bằng key đoán được.
- Versioning, retention và deletion policy phù hợp với nghiệp vụ.
- Log truy cập storage ở mức đủ để điều tra, không ghi credential.

Một bucket private vẫn có thể bị lộ nếu API cấp signed URL quá rộng hoặc IAM role của service có quyền đọc toàn bộ dữ liệu. Hãy giới hạn cả API policy lẫn quyền storage.

### 7.1. Server-side mapping

Mô hình nên là:

- Client gửi file ID.
- Database map file ID sang tenant, parent, status, ACL và storage key.
- Authorization service ra quyết định.
- Storage client dùng service identity để đọc object key nội bộ.

Không để client gửi bucket/key rồi backend chỉ kiểm tra bucket name. Không dùng storage key bí mật như cơ chế phân quyền.

## 8. Signed URL và download token

Signed URL thường là bearer capability: bất kỳ ai có URL còn hiệu lực đều có thể dùng nó trong phạm vi method/object/expiry đã ký. Người nhận URL không nhất thiết phải đăng nhập lại với API.

Vì vậy, chỉ phát hành signed URL sau khi server xác thực principal và kiểm tra đầy đủ quyền đọc file. URL phải gắn với đúng object, method, thời hạn và các điều kiện cần thiết.

### 8.1. Quy tắc khi phát hành signed URL

- Kiểm tra file:download hoặc file:preview trước khi ký.
- Chỉ ký đúng object key/version đã được xác minh.
- Giới hạn method (ví dụ GET), thời hạn ngắn và response disposition/content type nếu storage hỗ trợ.
- Không ký quyền list bucket, ghi object hoặc đọc prefix rộng.
- Không để client tự cung cấp bucket/key trong yêu cầu ký.
- Không log URL đầy đủ vì query string thường chứa chữ ký/token.
- Không đưa URL vào analytics, referrer hoặc thông báo có thể bị chia sẻ ngoài ý muốn.
- Ghi audit ai yêu cầu URL, file nào, action và thời hạn.

Signed URL có thể được dùng lại cho đến khi hết hạn trong nhiều hệ thống object storage. Không gọi nó là single-use nếu nền tảng không bảo đảm điều đó. Nếu cần one-time download, cần một gateway/token service kiểm soát trạng thái sử dụng hoặc cơ chế tương đương.

### 8.2. Thu hồi quyền sau khi đã phát hành URL

Thu hồi ACL trong database không nhất thiết vô hiệu hóa ngay signed URL đã phát hành. URL có thể tiếp tục hoạt động tới expiry, tùy nền tảng và cách ký.

Nếu cần thu hồi tức thời:

- Phục vụ download qua application/proxy để kiểm tra quyền ở mỗi request.
- Dùng token ngắn hạn có thể revoke/introspect ở gateway.
- Dùng object version/key rotation hoặc policy thu hồi ở storage nếu nền tảng hỗ trợ và đã đánh giá tác động.
- Giảm TTL để thu hẹp khoảng thời gian rủi ro.

Phải mô tả rõ trade-off giữa hiệu năng, chi phí và khả năng revoke. Không hứa rằng xóa ACL sẽ vô hiệu hóa mọi URL đã gửi đi.

## 9. CDN, cache và preview

CDN có thể lưu bytes hoặc preview sau lần đọc đầu tiên. Nếu cache key không phân biệt quyền truy cập, một user được phép có thể làm nóng cache rồi user khác đọc cùng object qua cache mà không đi qua authorization.

Với file riêng tư:

- Dùng private cache policy hoặc không cache ở shared cache nếu không thể bảo đảm authorization.
- Nếu dùng CDN signed URL/cookie, giới hạn resource, method và expiry.
- Đảm bảo cache key chứa các yếu tố xác thực capability cần thiết; không loại bỏ query signature khỏi cache key một cách sai lệch.
- Không cache response theo user mà thiếu partitioning phù hợp.
- Dùng Cache-Control: private, no-store cho nội dung rất nhạy cảm khi cần.
- Khi ACL hoặc file state thay đổi, có quy trình purge/invalidate cache và signed capability theo thiết kế.
- Tránh trả header CORS hoặc cache metadata khiến response của origin/user này bị tái sử dụng cho origin/user khác.

### 9.1. Preview và thumbnail cũng là dữ liệu

Thumbnail có thể vẫn lộ khuôn mặt, số chứng từ, nội dung trang đầu hoặc thông tin cá nhân. OCR text có thể chứa gần như toàn bộ nội dung. Các derived object phải có ACL và lifecycle phù hợp với file gốc.

Nếu preview được tạo từ file đã bị revoke hoặc xóa, phải ngăn việc tiếp tục truy cập rendition còn sót. Có thể dùng cùng file ID và authorization service, hoặc lưu quan hệ parent-child và kiểm tra trạng thái/ACL của parent mỗi lần đọc.

## 10. Chia sẻ file và quyền truy cập được ủy quyền

Nếu nghiệp vụ cần chia sẻ file, mô hình hóa share grant rõ ràng thay vì biến file thành public.

Một grant có thể gồm:

| Trường | Ý nghĩa |
|---|---|
| file_id | Resource được chia sẻ |
| grantee_type/id | User, group hoặc integration nhận quyền |
| actions | read, preview hoặc download |
| expires_at | Thời điểm hết hạn |
| created_by | Principal cấp quyền |
| revoked_at | Thời điểm thu hồi |
| constraints | Password, domain, purpose hoặc download limit nếu có |

### 10.1. Kiểm soát người cấp quyền

Người tạo share phải có file:share hoặc quyền tương ứng. Không phải ai có file:read cũng được phép chia sẻ tiếp. Cần ngăn người nhận cấp lại quyền nếu policy không cho phép (delegation/reshare).

### 10.2. Link chia sẻ công khai

Nếu nghiệp vụ bắt buộc link không cần đăng nhập:

- Coi link là secret bearer capability.
- Sinh token ngẫu nhiên đủ mạnh, không dùng file ID làm token.
- Lưu hash/token reference phía server nếu cần revoke.
- Giới hạn action, file, expiry và có thể giới hạn download count.
- Không cho phép list hoặc duyệt file khác.
- Có thể yêu cầu password hoặc xác minh recipient theo mức nhạy cảm.
- Thu hồi được link và audit việc tạo/truy cập.
- Không để token xuất hiện trong log, referrer hoặc analytics.

Link share không nên mặc định là vĩnh viễn. Với dữ liệu nhạy cảm, ưu tiên xác thực recipient và grant theo danh tính.

## 11. Tenant isolation và truy cập qua parent resource

File thường gắn với parent resource như project, case, order, message hoặc workspace. Kiểm tra quyền nên theo quan hệ đã lưu, không theo tenant ID do client gửi.

Ví dụ truy vấn:

~~~sql
SELECT f.*
FROM files f
JOIN projects p ON p.id = f.project_id
JOIN project_members pm ON pm.project_id = p.id
WHERE f.id = :fileId
  AND p.tenant_id = :verifiedTenantId
  AND pm.user_id = :principalId
  AND pm.can_read_files = TRUE
  AND f.status = 'AVAILABLE';
~~~

Truy vấn minh họa cần được điều chỉnh theo schema và role thực tế. Điểm quan trọng là ràng buộc file, parent, tenant và principal trong cùng quyết định. Nếu lấy file record theo ID toàn cục rồi chỉ kiểm tra tenant ở một nhánh code khác, dễ phát sinh lỗi bỏ sót.

Kiểm tra tenant cho tất cả đường đọc: metadata, content, preview, download, export, search, signed URL và background job. Không giả định file đã thuộc project thì mọi member đều được đọc nếu project có tài liệu restricted.

## 12. Background jobs, export và service identity

File thường được đọc bởi scanner, OCR worker, thumbnail service, archive exporter hoặc integration. Những service này cần quyền riêng và scope tối thiểu.

- Worker chỉ đọc bucket/prefix và trạng thái file cần cho job.
- Message/job payload chỉ mang file ID và correlation ID; không tin storage key hoặc tenant do message producer tự khai báo nếu chưa xác minh.
- Worker xác minh file còn tồn tại, đúng tenant, đúng trạng thái và job còn hiệu lực trước khi đọc.
- Quyền của requester có thể cần được kiểm tra lại lúc job chạy, nhất là job export có thể chờ lâu trong queue.
- Nếu workflow cần snapshot quyền tại thời điểm yêu cầu, lưu policy decision/version, thời điểm, requester và lý do; định nghĩa rõ khi nào quyết định bị vô hiệu.
- Output export phải có owner, tenant, expiry và ACL riêng; không tự động public vì được tạo bởi service account.
- Khi requester bị thu hồi quyền trước khi tải export, download service phải áp dụng policy đã định nghĩa và audit.

Service account có thể cần đọc file để xử lý, nhưng điều đó không đồng nghĩa mọi người dùng có quyền đọc kết quả. Phân biệt quyền của worker với quyền của requester.

## 13. Đồng bộ ACL, thu hồi và race condition

Một số lỗi xuất hiện khi quyền thay đổi giữa lúc kiểm tra và lúc trả bytes:

- User bị remove khỏi project nhưng signed URL cũ vẫn hoạt động.
- File bị revoke sau authorization check nhưng trước khi storage read hoàn tất.
- ACL được cập nhật trong database nhưng CDN vẫn phục vụ bản cache.
- Thumbnail được tạo trước khi file bị xóa và endpoint rendition không kiểm tra parent state.
- Job export bắt đầu khi user có quyền nhưng hoàn tất sau khi quyền đã bị thu hồi.

Xác định yêu cầu nhất quán cho từng loại dữ liệu. Với nội dung nhạy cảm, nên kiểm tra quyền ngay trước khi stream hoặc cấp capability và giảm thời gian giữa decision với read. Có thể dùng transaction/version check, short-lived grant, storage key versioning hoặc proxy download để kiểm soát tốt hơn.

Không phải mọi hệ thống đều có thể thu hồi bytes đã tải về. Sau khi user hợp lệ đã download file, hệ thống không thể đảm bảo xóa bản sao trên thiết bị của họ. Cần phân biệt thu hồi quyền truy cập tiếp theo với thu hồi bản sao đã được tải.

### 13.1. File bị xóa

Xóa file cần bao gồm:

- File record và trạng thái truy cập.
- Object gốc trong storage theo retention policy.
- Thumbnail/preview/OCR/derived object.
- Cache/CDN và signed capability theo khả năng nền tảng.
- Export/archive có chứa file.
- Search index, backup hoặc replica theo retention/legal hold.

Nếu phải giữ bản gốc vì legal hold, trạng thái nghiệp vụ có thể là unavailable cho user nhưng retained trong vùng lưu trữ hạn chế. Không dùng một cờ deleted đơn giản rồi bỏ quên derived data.

## 14. Audit và giám sát quyền đọc

Ghi sự kiện truy cập để có thể điều tra việc lộ file:

- Principal/client/service identity.
- Tenant và parent resource.
- File ID và action (metadata, preview, download, share, delete).
- Kết quả allow/deny và policy reason code.
- Request ID, timestamp, source context phù hợp.
- Signed URL issued: expiry, scope và identifier, không ghi URL/chữ ký đầy đủ.
- Download bytes/range hoặc số lần truy cập nếu nghiệp vụ cần.
- Admin/support access và purpose code.
- ACL change, share create/revoke và file state transition.

Không log file content, raw signed URL, access token, cookie hoặc secret storage. Tên file và metadata cũng có thể nhạy cảm; redact hoặc phân loại theo policy.

Theo dõi bất thường như một user tải nhiều file ngoài pattern, một tenant liên tục dò file ID, nhiều lần 403/404, signed URL được sử dụng từ nhiều nguồn khác nhau hoặc truy cập file sau khi membership đã bị thu hồi.

## 15. Kiểm thử bảo mật quyền đọc sau upload

Dùng hai user, hai tenant, nhiều role và file fixture khác nhau. Kiểm thử tất cả route đọc, không chỉ download.

| Nhóm | Tình huống | Kết quả mong đợi |
|---|---|---|
| Anonymous | Không credential gọi metadata/content | Từ chối nếu file không public |
| Uploader | Uploader đọc file của mình | Chỉ được nếu policy cho phép và file AVAILABLE |
| Other user | User B dùng file ID của User A | Không đọc được |
| Cross-tenant | User tenant B dùng ID file tenant A | Từ chối, không lộ bytes/metadata ngoài policy |
| Same project | Member project đọc file restricted | Chỉ được nếu role/ACL cho phép |
| ACL grant | User được share file với read | Được đọc trong phạm vi và thời hạn grant |
| ACL revoked | Thu hồi grant rồi gọi lại | Request mới bị từ chối |
| Metadata vs content | Có read_metadata nhưng không có download | Metadata được giới hạn; bytes bị từ chối |
| Preview bypass | Gọi thumbnail/preview trực tiếp | Áp dụng cùng object/tenant policy |
| OCR/search | Truy vấn extracted text hoặc snippet | Không lộ nội dung ngoài ACL file |
| Quarantine | Đọc trước khi scan xong | Không có đường đọc user-facing |
| Rejected file | File scan thất bại | Không được preview/download |
| Storage key tampering | Client gửi bucket/key/path khác | Server bỏ qua hoặc từ chối; không truy cập object khác |
| Signed URL | User không có quyền yêu cầu URL | Không phát hành capability |
| Signed URL expiry | Dùng URL sau expiry | Storage/proxy từ chối |
| Signed URL revocation | Thu hồi ACL sau khi URL đã cấp | Hành vi phù hợp với cam kết revoke và TTL |
| CDN cache | User A làm nóng cache, User B thử cùng URL | Không nhận bytes nếu không có capability/quyền |
| Delete | File bị xóa/revoke nhưng thumbnail còn | Không truy cập được rendition |
| Background job | Worker đọc file của tenant khác | Workload policy từ chối |
| Export | Export chứa file ngoài quyền requester | Không tạo hoặc không cho tải output trái phép |
| Race condition | ACL bị thu hồi trong lúc tạo link/job | Quy tắc nhất quán, không cấp quyền mới ngoài policy |
| Audit | Đọc thành công và bị từ chối | Có event phù hợp, không log secret hoặc nội dung |

### 15.1. Kiểm tra IDOR/BOLA trên toàn bộ route

Thay file ID của User A bằng file ID của User B ở từng endpoint:

~~~text
GET /api/files/{fileId}
GET /api/files/{fileId}/content
GET /api/files/{fileId}/preview
GET /api/files/{fileId}/download-url
~~~

Nếu một route trả bytes hoặc metadata trong khi route khác từ chối, đó là dấu hiệu policy không được dùng thống nhất. Kiểm tra cả ID trong path, query, body, nested resource và batch request.

### 15.2. Kiểm thử signed URL và cache

- Xác minh URL chỉ cho đúng method/object và hết hạn đúng lúc.
- Thử URL với object ID/key khác; chữ ký không được áp dụng cho object khác.
- Kiểm tra signed URL có bị log hoặc xuất hiện trong referrer không.
- Sau khi revoke, xác minh đúng hành vi đã cam kết; nếu URL vẫn sống tới expiry, TTL phải nằm trong giới hạn chấp nhận được.
- Gọi cùng resource qua CDN bằng hai principal khác nhau và xác minh cache không làm rò rỉ bytes.
- Kiểm tra preview, range request và content disposition theo policy.

## 16. Checklist trước khi phát hành

- [ ] Upload permission và read/download permission được mô hình hóa riêng.
- [ ] Mỗi file có file ID ổn định, tenant, parent, owner và classification.
- [ ] File ID/object key không được coi là credential.
- [ ] Storage bucket/container private-by-default; client không có quyền list/read trực tiếp ngoài policy.
- [ ] File chưa scan hoặc chưa đạt validation nằm trong quarantine và không thể đọc qua user-facing route.
- [ ] Mọi đường metadata, content, preview, thumbnail, OCR, search, export và signed URL đều có authorization.
- [ ] Policy kiểm tra tenant, parent membership, owner/ACL, action và lifecycle state.
- [ ] Derived object kế thừa hoặc kiểm tra lại quyền của file gốc.
- [ ] Signed URL chỉ được cấp sau authorization, giới hạn object/method/expiry và được coi là bearer capability.
- [ ] Có thiết kế revoke rõ ràng cho signed URL, CDN cache và share grant.
- [ ] CDN/shared cache không phục vụ bytes riêng tư cho principal khác.
- [ ] Background worker dùng workload identity và scope tối thiểu; requester được kiểm tra theo policy.
- [ ] Delete/revoke xử lý cả preview, thumbnail, OCR, export và cache theo retention policy.
- [ ] Audit ghi principal, tenant, file, action và outcome; không ghi bytes/token/signed URL.
- [ ] Có test IDOR/BOLA, cross-tenant, ACL revoke, preview bypass, signed URL, cache và race condition.

Quyền đọc file phải được quyết định ở server dựa trên principal, tenant, parent resource, ACL, action và trạng thái file. Mọi đường có thể tiết lộ bytes hoặc metadata—từ download, preview, OCR đến export và signed URL—đều phải tuân theo cùng policy. Storage private, signed URL ngắn hạn, cache có phân vùng và background worker với quyền tối thiểu giúp giảm rủi ro, nhưng không thay thế object-level authorization.
