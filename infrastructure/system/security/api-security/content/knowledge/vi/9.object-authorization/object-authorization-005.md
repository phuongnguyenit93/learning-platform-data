# ID tuần tự không phải cơ chế bảo mật

Nhiều API dùng ID tăng dần để định danh bản ghi, chẳng hạn `/api/invoices/1001`, `/api/invoices/1002` hoặc `/api/users/501`. ID tuần tự thuận tiện cho database, log và việc tham chiếu tài nguyên. Tuy nhiên, nếu hệ thống dựa vào việc người dùng khó đoán ID tiếp theo để bảo vệ dữ liệu, endpoint có thể bị khai thác bằng cách thử các ID lân cận.

ID là cách xác định **đối tượng nào** đang được yêu cầu. Authorization là quyết định **caller có được phép thực hiện hành động nào trên đối tượng đó** hay không. Hai việc này phải được thiết kế riêng. Một ID khó đoán có thể làm giảm khả năng dò tìm tài nguyên, nhưng không chứng minh quyền truy cập. Ngược lại, ID tuần tự không tự tạo ra lỗ hổng nếu mọi endpoint đều kiểm tra quyền đối với object đúng cách.

Trong API Security, cần thiết kế phân quyền theo endpoint, object và luồng nghiệp vụ. Không được xem ID tăng dần, UUID, slug hay một chuỗi khó đoán là bằng chứng rằng caller sở hữu tài nguyên.

## 1. Vì sao ID tuần tự dễ bị dò tìm?

Giả sử một hệ thống hóa đơn cung cấp endpoint:

```http
GET /api/invoices/1001
GET /api/invoices/1002
GET /api/invoices/1003
```

Người dùng hợp lệ có thể nhìn thấy ID `1002` trong URL hoặc response. Nếu API không kiểm tra quyền trên từng hóa đơn, họ có thể thay ID thành `1001` hoặc `1003` để thử đọc hóa đơn của người khác. Script có thể tự động gửi hàng nghìn request và thu thập các bản ghi tồn tại.

Việc dò ID thường được gọi là *enumeration*. Kẻ tấn công có thể khai thác nó để:

- Đọc hồ sơ, hóa đơn, đơn hàng hoặc tệp của người dùng khác.
- Sửa, xóa, hủy hoặc phê duyệt object ngoài phạm vi được giao.
- Ước lượng số lượng bản ghi, tốc độ tăng trưởng hoặc hoạt động của doanh nghiệp.
- Tìm các object có giá trị cao, ví dụ hóa đơn lớn, tài khoản quản trị hoặc tài liệu mới tạo.
- Kết hợp ID tìm được với endpoint khác để mở rộng phạm vi truy cập.

ID tuần tự còn có thể để lộ thông tin về thứ tự tạo hoặc quy mô dữ liệu. Đây là rủi ro về khả năng suy luận và thu thập dữ liệu; mức độ ảnh hưởng thực tế phụ thuộc vào dữ liệu và quyền của endpoint.

## 2. Enumeration không đồng nghĩa với authorization failure

Không phải cứ dùng ID tuần tự là API bị lỗi bảo mật. Vấn đề xảy ra khi server trả về hoặc thay đổi object mà caller không được phép truy cập.

| Tình huống | Đánh giá |
|---|---|
| ID tuần tự, endpoint kiểm tra owner/tenant trước khi trả dữ liệu | Có thể an toàn; ID có thể đoán nhưng quyền vẫn được thực thi |
| ID ngẫu nhiên, endpoint chỉ kiểm tra người dùng đã đăng nhập | Vẫn có lỗi BOLA nếu người dùng dùng ID bị lộ để truy cập object của người khác |
| ID tuần tự, endpoint không kiểm tra quyền trên object | Có nguy cơ enumeration dẫn đến Broken Object Level Authorization (BOLA) |
| UUID hoặc opaque ID, endpoint kiểm tra quyền object và tenant | Có hai lớp giảm rủi ro: ID khó đoán và authorization đúng |

Lỗi *Broken Object Level Authorization* (BOLA), thường liên quan đến *Insecure Direct Object Reference* (IDOR), xuất hiện khi API không thực thi quyền trên object mà caller tham chiếu. Thay ID trong path, query, body hoặc header có thể làm lộ lỗi này.

Vì vậy, không nên kết luận rằng đổi số `1002` thành UUID là đã sửa xong BOLA. Nếu người dùng có thể lấy UUID từ link, response, log, email hoặc một endpoint khác, họ vẫn có thể gửi UUID đó. Server vẫn phải xác minh quyền truy cập.

## 3. ID là định danh, không phải credential

Một credential chứng minh danh tính hoặc quyền được cấp. ID thông thường chỉ giúp tìm một object. Không thiết kế hệ thống theo quy tắc “biết ID là được truy cập”.

Ví dụ, `invoiceId` có thể xuất hiện trong URL gửi qua email cho khách hàng. Điều đó không có nghĩa mọi người nhận được URL đều có quyền xem hóa đơn. Khi người dùng mở link, server vẫn cần xác thực danh tính hoặc xác minh một cơ chế chia sẻ có chủ đích, có giới hạn và có thể thu hồi.

Không dùng các giá trị sau làm bằng chứng duy nhất về quyền:

- ID trong path, query parameter hoặc request body.
- `ownerId`, `userId`, `tenantId` do client gửi lên.
- UUID, ULID, Snowflake ID, slug hoặc mã tham chiếu có độ dài lớn.
- ID được ẩn trong giao diện hoặc chỉ được gửi từ ứng dụng chính thức.
- Một URL khó đoán nhưng không có cơ chế xác thực/ủy quyền phù hợp.

Nếu sản phẩm cần chia sẻ tài nguyên qua link, hãy tạo một *share token* riêng có entropy cao, scope rõ ràng, thời hạn, khả năng thu hồi và giới hạn hành động. Share token là credential mang quyền được thiết kế rõ ràng; nó khác với ID của object. Không tái sử dụng khóa chính database làm share token.

## 4. Kiểm tra quyền theo actor, action và object

Mỗi request truy cập object nên được đánh giá theo ít nhất các yếu tố:

| Yếu tố | Câu hỏi | Ví dụ |
|---|---|---|
| Actor | Ai đang gọi? | Principal có subject `user-123` đã được xác thực |
| Action | Caller muốn làm gì? | Đọc, sửa, xóa, tải xuống, hủy hoặc phê duyệt |
| Object | Object nào bị tác động? | Hóa đơn có ID trong path |
| Scope/context | Quyền áp dụng trong phạm vi nào? | Owner, tenant, quan hệ được ủy quyền hoặc nhóm phụ trách |
| Business state | Trạng thái hiện tại có cho phép hành động không? | Hóa đơn đã phát hành có thể không còn được sửa |

Ví dụ, quyền `invoices:read` chỉ xác định caller được gọi chức năng đọc hóa đơn. Nó chưa nói caller được đọc mọi hóa đơn. Hệ thống cần kết hợp quyền chức năng với quan hệ trên object:

```text
Cho phép đọc khi:
  principal đã xác thực
  AND principal có quyền invoices:read
  AND invoice thuộc tenant được phép
  AND principal là owner hoặc có quan hệ truy cập hợp lệ
```

Với thao tác ghi, bổ sung quyền thuộc tính và điều kiện nghiệp vụ. Người mua có thể được đổi địa chỉ nhận hàng nhưng không được tự sửa `totalAmount`, `paidAt` hoặc `paymentStatus`.

## 5. Giới hạn truy vấn ngay trong phạm vi được phép

Một cách triển khai hiệu quả là đưa điều kiện quyền vào truy vấn dữ liệu. Ví dụ endpoint đọc hóa đơn của khách hàng:

```java
@RestController
@RequestMapping("/api/invoices")
@RequiredArgsConstructor
class InvoiceController {
    private final InvoiceService invoiceService;
    private final IdentityMapper identityMapper;

    @GetMapping("/{invoiceId}")
    @PreAuthorize("hasAuthority('SCOPE_invoices:read')")
    InvoiceResponse getInvoice(
            @PathVariable UUID invoiceId,
            @AuthenticationPrincipal Jwt jwt) {
        UUID customerId = identityMapper.customerId(jwt);
        return invoiceService.getForCustomer(invoiceId, customerId);
    }
}
```

Service chỉ truy vấn hóa đơn thuộc khách hàng được xác định từ principal:

```java
@Service
@RequiredArgsConstructor
class InvoiceService {
    private final InvoiceRepository invoiceRepository;
    private final InvoiceMapper invoiceMapper;

    @Transactional(readOnly = true)
    InvoiceResponse getForCustomer(UUID invoiceId, UUID customerId) {
        Invoice invoice = invoiceRepository
                .findByIdAndCustomerId(invoiceId, customerId)
                .orElseThrow(InvoiceNotFoundException::new);

        return invoiceMapper.toResponse(invoice);
    }
}
```

Repository có thể định nghĩa:

```java
Optional<Invoice> findByIdAndCustomerId(UUID id, UUID customerId);
```

`customerId` phải được ánh xạ từ danh tính đã xác minh hoặc từ quan hệ tài khoản đáng tin cậy. Không lấy `customerId` do request gửi lên rồi dùng nó làm phạm vi truy vấn. Nếu hệ thống hỗ trợ nhân viên, đại diện hoặc quyền chia sẻ, hãy thể hiện quan hệ đó trong policy/truy vấn thay vì bỏ điều kiện owner một cách tùy tiện.

Truy vấn theo `id` và owner giúp tránh tải nhầm object trước khi kiểm tra quyền. Một cách khác là truy vấn object theo ID rồi gọi authorization service trước khi trả dữ liệu; cách đó vẫn có thể an toàn nếu không có đường code nào đọc hoặc trả dữ liệu trước khi kiểm tra. Điều quan trọng là mọi đường truy cập đều áp dụng cùng một policy.

## 6. Kiểm soát tenant và quan hệ được ủy quyền

Trong hệ thống multi-tenant, kiểm tra owner đơn lẻ có thể chưa đủ. Một object có thể thuộc tenant A, còn caller có quyền quản lý nhiều tenant hoặc được ủy quyền trong một phạm vi nhất định.

Ví dụ điều kiện truy cập hóa đơn có thể là:

```sql
SELECT i.*
FROM invoice i
WHERE i.public_id = :invoice_id
  AND i.tenant_id = :tenant_id
  AND (
      i.customer_id = :subject_id
      OR EXISTS (
          SELECT 1
          FROM invoice_access_grant g
          WHERE g.invoice_id = i.id
            AND g.subject_id = :subject_id
            AND g.permission = 'READ'
            AND g.revoked_at IS NULL
            AND g.expires_at > CURRENT_TIMESTAMP
      )
  );
```

Đây là ví dụ minh họa; policy thực tế có thể khác. `tenant_id` và `subject_id` cần đến từ principal/context đã xác minh hoặc được server suy ra từ quan hệ đáng tin cậy. Không cho client thay `tenant_id` trong body để chuyển phạm vi truy cập.

Khi có quyền ủy quyền, cần kiểm tra tối thiểu:

- Grant có thuộc đúng object và đúng tenant không?
- Grant có cấp đúng action không, hay chỉ cho đọc mà không cho sửa?
- Grant có hết hạn hoặc bị thu hồi chưa?
- Người cấp quyền còn quyền để chia sẻ object không?
- Quyền có được phép chuyển tiếp cho người khác hay không?

Đừng mặc định quyền của quản trị viên ở tenant này áp dụng cho tenant khác. Quyền cross-tenant cần được mô tả và kiểm toán rõ ràng.

## 7. UUID và opaque ID có ích gì?

ID ngẫu nhiên hoặc opaque ID làm cho việc đoán object tiếp theo khó hơn. Chúng có thể giảm enumeration tự động và hạn chế việc lộ thứ tự tạo bản ghi. Đây là lớp phòng thủ bổ sung, không phải authorization.

| Loại định danh | Đặc điểm | Lưu ý bảo mật |
|---|---|---|
| Số tăng dần | Dễ index, dễ đọc và dễ đoán | Không dùng tính khó đoán để bảo vệ dữ liệu |
| UUID v4 | Có phần ngẫu nhiên lớn, không thể hiện thứ tự tạo theo thời gian | Vẫn phải kiểm tra quyền; UUID bị lộ vẫn có thể được dùng để gọi API |
| UUID v7 | Có thành phần thời gian giúp sắp xếp theo thời điểm tạo | Không xem tính khó đoán của toàn bộ giá trị là bí mật; timestamp có thể làm lộ thứ tự/thời gian |
| ULID | Có thứ tự theo thời gian và phần ngẫu nhiên | Có thể suy ra thời điểm tạo; không dùng như credential |
| Snowflake-style ID | Thường mã hóa thời gian và thông tin worker/sequence | Có thể lộ thông tin vận hành và dễ dự đoán một phần |
| Opaque random ID | Chuỗi ngẫu nhiên không mang ý nghĩa nghiệp vụ | Giảm khả năng đoán nhưng vẫn cần authorization và quản lý rò rỉ |

Nếu muốn ID công khai khó đoán, hãy tạo bằng cryptographically secure random generator với entropy đủ lớn (ví dụ ít nhất 128 bit ngẫu nhiên), mã hóa ở dạng URL-safe và không tái sử dụng. Không tự tạo ID bằng timestamp, counter cộng salt cố định hoặc `Random` không an toàn.

Một thiết kế phổ biến là dùng khóa chính nội bộ cho database và public ID riêng cho API:

```text
Database:
  id = 84721                 (internal primary key)
  public_id = "r8K...xQ"     (opaque external reference)

API:
  GET /api/invoices/r8K...xQ
```

Việc tách ID nội bộ và public ID giúp tránh phơi lộ cấu trúc database, hỗ trợ thay đổi mô hình lưu trữ và giảm khả năng đoán tài nguyên. Tuy vậy, public ID vẫn chỉ là định danh; truy vấn phải giới hạn theo quyền của caller.

## 8. Không để ID trong endpoint phụ làm hỏng authorization

Một API có thể kiểm tra quyền ở endpoint chi tiết nhưng bỏ sót ở các endpoint khác. Kẻ tấn công thường tìm đường vòng qua danh sách, tìm kiếm, tải tệp, thao tác hàng loạt hoặc endpoint lồng nhau.

### Danh sách và tìm kiếm

`GET /api/invoices` cần áp dụng tenant/owner filter ở server trước khi phân trang và tính tổng. Không trả toàn bộ danh sách rồi lọc bằng JavaScript ở client. Tổng số bản ghi, facet, autocomplete và export cũng có thể tiết lộ object ngoài phạm vi.

### Tải xuống và tệp đính kèm

`GET /api/invoices/{id}/pdf` cần kiểm tra quyền trên hóa đơn và trên tệp liên quan. Không giả định biết đường dẫn lưu trữ hoặc object key là đủ quyền tải xuống. URL ký (*pre-signed URL*) cần scope, thời hạn ngắn và quyền chỉ đọc/ghi đúng object.

### Object lồng nhau

Với `GET /api/orders/{orderId}/items/{itemId}`, server phải xác minh item thực sự thuộc order được chỉ định và caller có quyền trên order đó. Không chỉ kiểm tra `itemId` tồn tại. Điều kiện quan hệ nên được xác minh trong truy vấn hoặc service.

### Batch và bulk operations

Với `POST /api/invoices/bulk-export` nhận danh sách ID, phải kiểm tra quyền trên từng object. Một ID không được phép không nên khiến server âm thầm xuất dữ liệu của object đó. Hợp đồng cần quy định xử lý all-or-nothing hay kết quả từng phần, và response không được tiết lộ chi tiết nhạy cảm về object ngoài phạm vi.

### Webhook, event và background job

Khi xử lý tác vụ bất đồng bộ, lưu lại actor, tenant, quyền và mục đích đã được xác minh tại thời điểm tạo job. Worker cần kiểm tra rằng quyền vẫn còn hiệu lực nếu nghiệp vụ yêu cầu, hoặc dùng một service identity có quyền giới hạn rõ ràng. Không tin ID trong message chỉ vì message đến từ queue nội bộ.

## 9. Status code và cách tránh tiết lộ sự tồn tại của object

Khi caller truy cập một object không thuộc quyền, API cần chọn cách phản hồi phù hợp với chính sách sản phẩm:

- `403 Forbidden`: caller đã được xác thực nhưng không có quyền trên tài nguyên. Cách này rõ nghĩa nhưng có thể tiết lộ object tồn tại.
- `404 Not Found`: có thể dùng chung cho object không tồn tại và object nằm ngoài phạm vi caller, nhằm hạn chế dò tìm sự tồn tại.
- `401 Unauthorized`: dùng khi thiếu hoặc không hợp lệ thông tin xác thực, theo quy tắc authentication của API.

Không có một lựa chọn status code đúng cho mọi sản phẩm. Điều quan trọng là phản hồi không tiết lộ dữ liệu nhạy cảm và không tạo ra khác biệt dễ khai thác giữa ID tồn tại nhưng bị cấm và ID không tồn tại nếu chính sách yêu cầu che giấu.

Ngoài status code, cần xem xét:

- Nội dung response và mã lỗi có cho biết object tồn tại không?
- Response time có khác biệt rõ rệt giữa hai trường hợp không?
- Pagination total, header, cache hoặc redirect có tiết lộ thông tin không?
- Log có bị trả lại qua endpoint hỗ trợ hoặc debug không?

Không nên cố làm mọi response có thời gian tuyệt đối giống nhau bằng cách thêm delay tùy tiện; cách đó có thể tạo thêm vấn đề hiệu năng. Hãy giảm các khác biệt không cần thiết và bảo đảm policy truy cập được thực thi trước khi trả thông tin.

## 10. Rate limit và phát hiện hành vi dò ID

Authorization là lớp ngăn truy cập trái phép; rate limit và giám sát giúp giảm khả năng tự động hóa, phát hiện hành vi bất thường và bảo vệ tài nguyên. Có thể theo dõi:

- Một principal thử truy cập nhiều object ID khác nhau trong thời gian ngắn.
- Nhiều request liên tiếp bị từ chối với cùng một pattern tăng dần.
- Một client/API key truy vấn nhiều tenant hoặc nhiều owner không liên quan.
- Tỷ lệ `403`, `404` hoặc lỗi object lookup tăng đột biến.
- Request quét nhiều endpoint khác nhau với cùng một dải ID.
- Tải xuống hoặc export bất thường về số lượng, kích thước hoặc thời điểm.

Rate limit có thể áp dụng theo principal, client, tenant, IP và loại thao tác. Với thao tác nhạy cảm như export, tải tài liệu hoặc truy vấn tìm kiếm tốn kém, cần quota riêng. IP không phải định danh duy nhất của người dùng vì nhiều người có thể dùng chung NAT và attacker có thể đổi IP; kết hợp nhiều tín hiệu để tránh khóa nhầm người dùng hợp lệ.

Log nên ghi principal đã xác thực, action, object reference dạng phù hợp, quyết định allow/deny, tenant context, correlation ID và lý do policy ở mức nội bộ. Không ghi token, dữ liệu cá nhân đầy đủ hoặc nội dung hóa đơn vào log chỉ để điều tra enumeration.

## 11. Cache không được bỏ qua quyền object

Một endpoint có authorization đúng ở lần truy cập đầu vẫn có thể làm lộ dữ liệu nếu cache dùng khóa chỉ dựa trên URL và chia sẻ response giữa nhiều người dùng. Ví dụ cache key `/api/invoices/1002` có thể trả dữ liệu của người dùng A cho người dùng B nếu cache không phân biệt security context.

Với dữ liệu riêng tư:

- Thực thi authorization trước khi trả dữ liệu từ cache, hoặc bảo đảm cache partition theo principal/tenant và policy phù hợp.
- Không dùng cache public cho response phụ thuộc vào danh tính hoặc quyền của caller.
- Đặt header cache phù hợp; với response nhạy cảm có thể dùng `Cache-Control: private` hoặc `no-store` tùy yêu cầu.
- Khi quyền chia sẻ hoặc trạng thái owner thay đổi, làm mất hiệu lực cache tương ứng.
- Không coi cache key khó đoán là biện pháp bảo vệ dữ liệu.

CDN, reverse proxy, application cache và cache ở client đều cần được xem xét. Kiểm thử phải mô phỏng hai principal khác nhau truy cập cùng một URL để xác minh không có rò rỉ chéo.

## 12. Kiểm thử object authorization với ID tuần tự và ID ngẫu nhiên

Kiểm thử cần chứng minh quyền được áp dụng bất kể kiểu ID. Chuẩn bị ít nhất hai người dùng A và B, hai tenant nếu hệ thống multi-tenant, cùng các object thuộc từng phạm vi.

| Tình huống | Kết quả cần xác minh |
|---|---|
| A đọc object của A | Được phép nếu actor có quyền chức năng và trạng thái hợp lệ |
| A thay ID tuần tự sang object của B | Không đọc được dữ liệu của B |
| A dùng UUID/public ID đã biết của B | Vẫn bị từ chối; tính khó đoán không được xem là quyền |
| A gửi `ownerId` hoặc `tenantId` của B trong body | Không thể chuyển quyền sở hữu hoặc phạm vi tenant |
| A cập nhật object của B bằng PUT/PATCH/DELETE | Không có thay đổi dữ liệu hoặc side effect |
| A truy cập file/export của object B | Không tải được nội dung hoặc tạo link tải trái phép |
| A gửi batch gồm ID của A và B | Xử lý đúng all-or-nothing hoặc partial policy; không làm lộ object B |
| A truy cập child ID không thuộc parent ID | Request bị từ chối theo quan hệ object |
| A tìm kiếm hoặc phân trang | Kết quả và total chỉ bao gồm object trong phạm vi A |
| Quyền chia sẻ hết hạn hoặc bị thu hồi | Truy cập bị từ chối sau khi policy có hiệu lực |
| Cache cùng URL giữa A và B | Không trả response của A cho B |
| ID không tồn tại và ID ngoài quyền | Phản hồi tuân theo chính sách chống enumeration |

Test cần kiểm tra cả response, database, event, notification và lời gọi downstream. Một request trả `404` nhưng vẫn phát event hủy object của người khác là lỗi authorization nghiêm trọng.

Nên có test tự động cho các method và endpoint liên quan, không chỉ endpoint `GET` chi tiết. Khi thêm endpoint mới, tái sử dụng bộ test actor/object matrix để tránh bỏ sót đường truy cập phụ.

## 13. Checklist thiết kế ID và object authorization

- [ ] ID chỉ được dùng để xác định object; không được dùng làm bằng chứng về quyền.
- [ ] Mọi endpoint đọc, ghi, xóa, export hoặc thao tác hàng loạt đều kiểm tra quyền trên object.
- [ ] Actor, action, object, tenant và điều kiện nghiệp vụ được xác định rõ.
- [ ] Danh tính và tenant context được lấy từ security context hoặc nguồn đáng tin cậy, không tin giá trị client tự khai.
- [ ] Truy vấn giới hạn theo owner/tenant/ACL hoặc policy tương ứng.
- [ ] UUID/opaque ID chỉ được xem là lớp giảm enumeration bổ sung.
- [ ] Nếu có share link, token chia sẻ là credential riêng, có scope, expiry và revoke.
- [ ] Endpoint danh sách, tìm kiếm, child resource, file, batch, export và background job áp dụng cùng policy.
- [ ] Status code, response, pagination, cache và timing không tiết lộ thông tin ngoài chính sách.
- [ ] Có rate limit và giám sát hành vi dò object ID.
- [ ] Có test chéo user/tenant với cả ID tuần tự lẫn ID ngẫu nhiên.
- [ ] Log ghi đủ sự kiện allow/deny mà không làm lộ token hoặc dữ liệu nhạy cảm.

## Kết luận

ID tuần tự giúp định danh bản ghi nhưng không phải cơ chế kiểm soát truy cập. Thay ID tuần tự bằng UUID hoặc opaque ID có thể giảm khả năng enumeration, song không ngăn người dùng truy cập object đã bị lộ ID nếu server thiếu authorization. API cần kiểm tra quyền theo actor, action, object, tenant và trạng thái nghiệp vụ ở mọi đường đọc/ghi, kể cả danh sách, tệp, batch và tác vụ nền. Khi ID chỉ làm nhiệm vụ định danh còn policy được thực thi ở server, hệ thống không phụ thuộc vào việc attacker có đoán được mã tài nguyên hay không.
