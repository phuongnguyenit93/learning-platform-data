# Policy enforcement gần resource

## 1. Vì sao thực thi chính sách gần tài nguyên?

Trong IAM theo hướng Zero Trust, một request đi qua gateway hoặc xuất phát từ mạng nội bộ chưa đủ để kết luận nó được phép sử dụng mọi tài nguyên phía sau. Quyết định truy cập cần gắn với chủ thể, hành động và tài nguyên cụ thể; nơi thực thi phải ngăn được thao tác không được phép trước khi dữ liệu bị lộ hoặc trạng thái bị thay đổi.

**Policy enforcement gần resource** là đặt việc thực thi chính sách tại ranh giới kiểm soát tài nguyên, nơi có thể hiểu đúng đối tượng, thao tác và tác động của yêu cầu. “Gần” ở đây chủ yếu là gần về trách nhiệm và khả năng kiểm soát, không chỉ là cùng máy chủ hoặc cùng vùng mạng.

Ví dụ:

```http
GET /tenants/tenant-an/documents/doc-82
```

Gateway có thể biết token hợp lệ và caller được gọi Documents API. Nhưng Documents Service mới biết:

- `doc-82` thực sự thuộc tenant nào.
- Tài liệu có bị giới hạn cho một nhóm riêng không.
- Chủ thể có quyền đọc toàn bộ hay chỉ một số trường.
- Tài liệu đang ở trạng thái cho phép truy cập hay đã bị khóa.
- Request hiện tại có yêu cầu tải tệp gốc hoặc tạo một liên kết chia sẻ hay không.

Nếu chỉ kiểm tra “người dùng đã đăng nhập” ở gateway, ứng dụng vẫn có thể trả nhầm tài liệu của tenant khác. Đặt enforcement ở ranh giới tài nguyên giúp chính sách được áp dụng với thông tin đúng và trước tác động cần bảo vệ.

## 2. Phân biệt nơi quyết định và nơi thực thi

Có thể tách các trách nhiệm sau:

| Thành phần | Trách nhiệm | Ví dụ |
|---|---|---|
| Policy administration | Soạn, phê duyệt và phân phối chính sách | Quy tắc ai được đọc tài liệu mật |
| Nguồn thuộc tính | Cung cấp dữ liệu cần cho quyết định | Membership, nhóm, mức phân loại tài liệu |
| Policy decision point, PDP | Đánh giá chính sách với các đầu vào | Trả ALLOW, DENY hoặc kết quả chưa thể quyết định |
| Policy enforcement point, PEP | Cho phép, giới hạn hoặc chặn tác động | Documents Service chỉ trả trường được phép |

Các tên này mô tả trách nhiệm; một ứng dụng nhỏ có thể thực hiện nhiều trách nhiệm trong cùng một tiến trình.

**Tập trung quản lý chính sách không đòi hỏi tập trung mọi enforcement vào gateway.** Một PDP dùng chung có thể cung cấp quyết định cho nhiều PEP tại các dịch vụ sở hữu tài nguyên. Ngược lại, PEP có thể đánh giá một bản chính sách được phân phối cục bộ mà vẫn tuân theo quy trình quản lý chính sách chung.

Điều quan trọng là ranh giới rõ ràng:

- PDP quyết định dựa trên các đầu vào và phiên bản chính sách.
- PEP bảo đảm hành động thực tế khớp với quyết định.
- Nguồn thuộc tính phải có thẩm quyền đối với thông tin nó cung cấp.
- Thành phần quản trị chính sách không được mở cho client tự sửa quyền.

Một kết quả ALLOW bị bỏ qua điều kiện kèm theo, hoặc được dùng cho tài nguyên khác, là một lỗi enforcement dù PDP đã đánh giá đúng.

## 3. Gateway, service và nơi lưu trữ bảo vệ các lớp khác nhau

| Vị trí | Có thể kiểm soát tốt | Giới hạn cần nhận biết |
|---|---|---|
| Gateway | Xác thực đầu vào, giới hạn route, kiểm tra đích và scope tổng quát | Thường thiếu trạng thái đối tượng và quan hệ nghiệp vụ chi tiết |
| Service sở hữu tài nguyên | Quyền theo đối tượng, tenant, hành động và thuộc tính nghiệp vụ | Cần bao phủ các đường gọi và bảo vệ credential truy cập dữ liệu |
| Proxy hoặc sidecar | Danh tính workload, kết nối và các quy tắc có đầu vào phù hợp | Không tự hiểu mọi bản ghi hoặc trường nghiệp vụ trong payload |
| Cơ sở dữ liệu | Quyền thao tác bảng, hàng hoặc cơ chế cách ly được cấu hình | Không tự hiểu toàn bộ ý nghĩa người dùng và workflow nếu không được cung cấp đúng |
| Object storage | Quyền đọc/ghi object và cơ chế truy cập được nó hỗ trợ | Có thể không biết membership hiện tại nếu chỉ nhận một quyền tải đã cấp |

Các lớp này bổ sung cho nhau. Không nhất thiết lặp cùng một biểu thức ở mọi nơi, nhưng mỗi lớp phải có trách nhiệm rõ và không tạo một đường bỏ qua quyết định bắt buộc.

Ví dụ, gateway xác thực credential; service kiểm tra quyền `document.read` trên tài liệu; truy vấn có tenant scope; storage chỉ cho service hoặc một cơ chế tải được kiểm soát đọc object. Nếu một bucket lại cho đọc công khai, PEP ở service không còn kiểm soát được đường tải trực tiếp.

Một sidecar nằm cạnh ứng dụng về mặt triển khai cũng chưa chắc đủ gần về mặt ngữ nghĩa. Nếu sidecar chỉ biết URL `/documents/doc-82` mà không có thuộc tính tài liệu đáng tin cậy, nó không thể tự suy ra tenant, owner hoặc mức phân loại.

## 4. Điều kiện để PEP có hiệu lực

### 4.1. Không thể bỏ qua

Mọi đường sử dụng tài nguyên trong phạm vi chính sách phải đi qua một điểm thực thi thích hợp. Điều này bao gồm:

- API bên ngoài.
- API gọi nội bộ giữa các service.
- Giao diện quản trị.
- Tác vụ nền và scheduler.
- Consumer của queue.
- API batch, export và tìm kiếm.
- Đường tải object trực tiếp.
- Kết nối dài hoặc stream dữ liệu.

Chỉ đặt annotation ở controller HTTP không bảo vệ một hàm nghiệp vụ mà job nền có thể gọi trực tiếp. Cần đặt enforcement tại một ranh giới dùng chung phù hợp, hoặc bảo đảm từng đường có PEP tương ứng và được kiểm soát.

### 4.2. Có đầu vào đáng tin cậy

PEP cần nhận identity context đã được xác minh và thuộc tính tài nguyên từ nguồn có thẩm quyền.

Không lấy `owner_id`, `classification` hoặc `tenant_id` trong request body làm mô tả sự thật của đối tượng hiện có. Với tài nguyên tạo mới, các trường do client đề xuất vẫn phải được kiểm tra quyền thiết lập; không cho người dùng tự gán tenant hoặc owner để mở rộng quyền.

### 4.3. Thực thi trước tác động

Kiểm tra quyền sau khi gửi response, ghi dữ liệu hoặc phát sự kiện đã chứa dữ liệu là quá muộn.

Với thao tác ghi, cần xác định thời điểm kiểm tra và tính nhất quán với dữ liệu thực sự được cập nhật. Với thao tác đọc, dữ liệu không được đi ra ngoài ranh giới được phép trước khi quyết định và các giới hạn trả về đã được áp dụng.

### 4.4. Bảo vệ chính PEP và cấu hình của nó

Nếu client có thể tắt enforcement bằng một header hoặc sửa policy bundle, vị trí PEP không còn ý nghĩa. Quyền thay đổi chính sách, cấu hình fallback và danh tính chạy service phải được quản lý như các quyền nhạy cảm.

Một PEP trong code cũng không thể tự ngăn mọi hành vi của một tiến trình đã bị chiếm quyền nếu tiến trình đó giữ credential dữ liệu quá rộng. Cần kết hợp giới hạn quyền dữ liệu, cách ly workload và các kiểm soát lưu trữ tương ứng với ranh giới cần bảo vệ.

## 5. Ràng buộc quyết định với thao tác thực tế

Một yêu cầu đánh giá quyền thường cần ít nhất:

```text
subject + caller/ủy quyền nếu có
tenant
action
resource
các thuộc tính và trạng thái cần thiết
```

Ví dụ, “được gọi endpoint tài liệu” là một quyền quá thô để thay thế quyền đọc một tài liệu cụ thể.

Cần ràng buộc các phần sau:

| Phần ràng buộc | Lỗi nếu bỏ qua |
|---|---|
| Subject | Quyết định của người này bị dùng cho người khác |
| Tenant | Quyền tenant An bị dùng trong tenant Bình |
| Action | ALLOW đọc bị dùng cho xóa hoặc chia sẻ |
| Resource | ALLOW với tài liệu thứ nhất bị dùng cho tài liệu thứ hai |
| Điều kiện và phiên bản liên quan | Quyết định cũ bị dùng sau khi tài liệu hoặc quyền đã thay đổi |
| Người nhận và hiệu lực nếu quyết định được truyền đi | Kết quả bị dùng sai service hoặc ngoài thời gian cho phép |

Nếu service nhận một kết quả đánh giá từ thành phần khác, nó cần xác thực nguồn và kiểm tra các ràng buộc. Một header `X-Policy-Decision: ALLOW` do caller tự khai không phải bằng chứng phân quyền.

Không coi quyền sử dụng HTTP GET là quyền đọc mọi đối tượng phía sau route. Hành động nghiệp vụ phải được xác định rõ: đọc metadata, tải nội dung, xuất hàng loạt và tạo liên kết chia sẻ có thể có chính sách khác nhau.

## 6. Luồng đọc tài liệu có enforcement gần resource

Giả sử Lan thuộc tenant An. Lan yêu cầu đọc `doc-82`.

Một luồng khái niệm:

```text
1. Xác minh credential và dựng identity context.
2. Phân giải tenant mục tiêu của request.
3. Tải metadata tối thiểu của tài liệu trong tenant đó.
4. Lấy trạng thái quyền và thuộc tính có liên quan.
5. Đánh giá action document.read trên đúng tài liệu.
6. Nếu không được phép, dừng.
7. Áp dụng các giới hạn bắt buộc của quyết định.
8. Đọc/biểu diễn dữ liệu được phép và trả kết quả.
```

Việc service nội bộ đọc metadata để đánh giá không đồng nghĩa client được đọc metadata đó. Service cần có quyền hệ thống thích hợp để thực hiện việc phân giải, đồng thời tránh ghi thông tin nhạy cảm vào log hoặc trả nó trước quyết định.

Pseudocode:

```text
readDocument(request, verifiedIdentity):
    tenant = resolveRequestedTenant(request)
    resource = findMetadataWithinTenant(tenant.id, request.documentId)

    if resource is absent:
        rejectUsingApiResponsePolicy()

    authorizationState = loadCurrentAuthorizationState(
        verifiedIdentity, tenant, resource
    )

    decision = policy.evaluate(
        identity = verifiedIdentity,
        action = "document.read",
        resource = resource,
        authorizationState = authorizationState
    )

    if decision.effect != ALLOW:
        rejectUsingApiResponsePolicy()

    if cannotEnforce(decision.requiredRestrictions):
        rejectWithoutReturningData()

    content = readContentForSameResource(resource)
    return applyRequiredRestrictions(content, decision)
```

Đây là pseudocode mô tả trách nhiệm, không phải một framework bảo mật hoàn chỉnh. `verifiedIdentity` phải đến từ luồng xác thực, không được bind trực tiếp từ request body.

Điểm đáng chú ý là `readContentForSameResource` phải giữ đúng tài nguyên vừa đánh giá. Nếu code kiểm tra `doc-82` rồi dùng một object key khác do client truyền để tải nội dung, ràng buộc đã bị phá vỡ.

Nếu nội dung hoặc thuộc tính liên quan thay đổi giữa bước đánh giá và đọc, service cần cơ chế phù hợp, chẳng hạn đọc phiên bản đã đánh giá hoặc kiểm tra lại các thay đổi có ảnh hưởng tới quyền.

## 7. Tenant scope ở truy vấn dữ liệu

PEP tại service nên đi cùng thao tác dữ liệu được giới hạn đúng phạm vi.

Ví dụ truy vấn metadata:

```sql
SELECT document_id, tenant_id, owner_id, classification, version
FROM documents
WHERE tenant_id = :verified_tenant_id
  AND document_id = :document_id;
```

`verified_tenant_id` ở đây là tenant mục tiêu đã được đưa qua luồng kiểm tra phù hợp với identity context; nó không đơn thuần là một chuỗi đáng tin chỉ vì biến được đặt tên như vậy.

Truy vấn có tenant scope giúp ngăn việc lấy nhầm đối tượng ngoài phạm vi, nhưng không thay thế quyền theo tài liệu. Trong cùng tenant, một tài liệu có thể chỉ cho một nhóm cụ thể xem.

Tương tự, kiểm tra role ở service không thay thế điều kiện truy vấn. Nếu sau ALLOW, truy vấn chỉ dùng một ID do client có thể đổi sang tài nguyên khác, service vẫn có thể đọc sai dữ liệu.

Ở tầng cơ sở dữ liệu, có thể bổ sung cơ chế hạn chế hàng hoặc quyền thao tác phù hợp. Khi áp dụng tenant context lên connection, phải quản lý vòng đời cẩn thận với connection pool: context của request trước không được rò sang request sau. Quyền vận hành có khả năng bỏ qua lớp hạn chế này cũng cần được nhận diện và giới hạn.

## 8. Ghi dữ liệu và khoảng cách giữa kiểm tra với sử dụng

Một vấn đề thường gặp là time-of-check to time-of-use: quyền được kiểm tra ở thời điểm đầu, nhưng dữ liệu hoặc quyền thay đổi trước khi thao tác được thực hiện.

Ví dụ:

```text
T1: Lan được phép sửa tài liệu vì là owner.
T2: Quyền sở hữu được chuyển cho người khác.
T3: Request cũ của Lan vẫn cập nhật tài liệu.
```

Cần xác định ý nghĩa nhất quán của nghiệp vụ: thao tác được quyết định theo trạng thái tại thời điểm nào, và thay đổi nào phải làm nó thất bại.

Các cách xử lý có thể gồm:

- Khóa các bản ghi liên quan trong giao dịch, với quy tắc khóa được các luồng cập nhật tương ứng cùng tuân theo.
- Kiểm tra phiên bản tài nguyên khi ghi để phát hiện tài nguyên đã thay đổi.
- Kiểm tra phiên bản quyền hoặc trạng thái thu hồi bằng cơ chế nhất quán thích hợp.
- Thực hiện một thao tác dữ liệu có điều kiện phản ánh các điều kiện cần bảo vệ.
- Đánh giá lại khi chuyển tới một giai đoạn nhạy cảm của workflow dài.

Ví dụ cập nhật có kiểm tra phiên bản tài nguyên:

```sql
UPDATE documents
SET title = :new_title,
    version = version + 1
WHERE tenant_id = :verified_tenant_id
  AND document_id = :document_id
  AND version = :evaluated_resource_version;
```

Nếu số hàng cập nhật bằng 0, service không được báo thành công như thể đã cập nhật đúng tài nguyên. Nó cần xử lý trường hợp không còn khớp theo hợp đồng API.

Câu SQL trên chỉ phát hiện thay đổi phiên bản tài liệu. Nó chưa bảo đảm quyền thành viên hoặc chính sách không đổi giữa hai thời điểm. Muốn bảo vệ những điều kiện đó, cần thêm cơ chế cho trạng thái quyền tương ứng; không coi optimistic locking trên tài liệu là giải pháp tự động cho mọi cuộc đua phân quyền.

Sau khi ghi thành công, sự kiện hoặc tác vụ phát sinh cũng cần giữ phạm vi tenant và ý nghĩa hành động. Không phát một lệnh tiếp theo dùng quyền quản trị rộng hơn mà bỏ mất các giới hạn đã đánh giá.

## 9. Kết quả ALLOW có thể kèm giới hạn bắt buộc

Một quyết định không nhất thiết chỉ là boolean.

Ví dụ:

```json
{
  "effect": "ALLOW",
  "required_restrictions": {
    "readable_fields": ["document_id", "title", "summary"],
    "download_original": false
  },
  "decision_id": "decision-728",
  "policy_version": "documents-policy-17"
}
```

Đây là schema minh họa. PEP chỉ được thực hiện hành động nếu nó hiểu và thực thi được những giới hạn bắt buộc.

Nếu API vẫn serialize toàn bộ entity, gồm cả `confidential_notes`, kết quả ALLOW không có nghĩa response đó được phép. Cần trả một biểu diễn đã được giới hạn đúng.

Phân biệt:

- **Giới hạn bắt buộc:** điều kiện phải được thực thi để ALLOW có hiệu lực, chẳng hạn chỉ trả một tập trường.
- **Thông tin khuyến nghị:** dữ liệu hỗ trợ quan sát hoặc trải nghiệm, không tự thay đổi quyền nếu hợp đồng không quy định.

Không âm thầm bỏ qua một giới hạn bắt buộc mà phiên bản PEP hiện tại chưa hỗ trợ. Lỗi tương thích giữa PDP và PEP phải dẫn tới cách xử lý giữ nguyên ranh giới bảo vệ.

Việc ghi audit thông thường cũng cần được định nghĩa rõ. Nếu chính sách của một thao tác yêu cầu ghi nhận bền vững trước tác động, cơ chế thực thi phải đáp ứng điều kiện đó; không dùng một lệnh log không được kiểm tra kết quả để tuyên bố đã bảo đảm.

## 10. Tìm kiếm, batch, export và đường tải trực tiếp

### 10.1. Danh sách và tìm kiếm

Quyền gọi endpoint tìm kiếm không có nghĩa được nhận mọi kết quả.

Cần áp dụng phạm vi và chính sách vào việc lấy hoặc trả kết quả. Nếu chỉ tải toàn bộ dữ liệu rồi ẩn các dòng không được phép ở client, dữ liệu đã bị lộ.

Ngay cả khi lọc ở server trước response, các trường như tổng số kết quả, facet, gợi ý hoặc số trang cũng có thể tiết lộ thông tin ngoài quyền. Thiết kế cần xác định các giá trị này được tính trên tập dữ liệu nào và kiểm soát theo chính sách.

### 10.2. Batch

Một request có thể chứa nhiều resource ID. Kiểm tra quyền trên phần tử đầu tiên không bảo vệ những phần tử còn lại.

Phải xác định rõ batch là:

- Toàn bộ cùng thành công: mọi phần tử cần đạt điều kiện trước các tác động theo hợp đồng.
- Cho phép kết quả từng phần: mỗi phần tử được đánh giá và báo kết quả theo quy tắc không làm lộ dữ liệu bị cấm.

Nếu có yêu cầu nguyên tử, việc kiểm tra quyền đầy đủ vẫn phải kết hợp với cơ chế thực hiện dữ liệu phù hợp. Một vòng lặp đã cập nhật vài phần tử rồi mới phát hiện phần tử không có quyền không tạo ra một batch nguyên tử.

### 10.3. Export và job nền

Một request được chấp nhận để tạo job chưa nhất thiết là quyền đọc dữ liệu vô thời hạn. Worker cần được xác thực, có grant hoặc ủy quyền thích hợp, kiểm tra tenant và các điều kiện hiện hành theo thiết kế.

File export sinh ra là một tài nguyên mới cần bảo vệ. PEP phải bao phủ cả bước tạo, lưu và tải; không chỉ kiểm tra quyền khi nhấn nút “Export”.

### 10.4. Object storage và liên kết tải

Khi cấp một liên kết cho phép tải trực tiếp, một phần enforcement được giao cho nơi phục vụ object theo cơ chế của liên kết đó. Quyền tải cần được giới hạn về object, hành động và thời hạn phù hợp.

Nếu cần thu hồi sớm, hệ thống phải có cơ chế được nơi lưu trữ hỗ trợ hoặc đặt một cổng kiểm tra quyền ở đường tải. Không giả định việc khóa phiên ứng dụng tự làm mọi liên kết đã phát hành hết hiệu lực.

## 11. Cache, lỗi PDP và vận hành chính sách

### 11.1. Cache quyết định

Cache ALLOW giúp giảm độ trễ nhưng có thể giữ quyền cũ.

Việc dùng lại kết quả phải phản ánh những đầu vào có ảnh hưởng, chẳng hạn subject, caller/ủy quyền, tenant, action, resource, phiên bản quyền và thuộc tính tài nguyên liên quan. Cache chỉ theo user ID có thể dùng nhầm kết quả giữa tenant hoặc hành động.

Thời hạn và cơ chế vô hiệu hóa cần phù hợp yêu cầu thu hồi. Một quyết định cho tài liệu PUBLIC không được dùng tiếp sau khi tài liệu chuyển sang CONFIDENTIAL nếu thay đổi đó phải có hiệu lực ngay theo chính sách.

### 11.2. Khi không đánh giá được

Phải phân biệt DENY do chính sách với lỗi không thể đánh giá. Tuy vậy, lỗi không tự tạo quyền truy cập.

Ví dụ, timeout PDP không được biến thành:

```text
nếu policy service lỗi:
    cho phép mọi request nội bộ
```

Ứng dụng có thể có phương án hoạt động suy giảm đã được phê duyệt, như dùng bản chính sách cục bộ còn hợp lệ trong giới hạn nhất định. Cần định nghĩa thời hạn, nguồn tin cậy và loại hành động được xử lý. Không giữ một kết quả ALLOW vô hạn chỉ để tránh gián đoạn.

Phản hồi API cần vừa rõ về lỗi vận hành vừa hạn chế tiết lộ tài nguyên. Quy ước trả trạng thái hoặc thông báo phải được thiết kế nhất quán, không trả dữ liệu nhạy cảm trong nhánh lỗi trước khi quyết định được thực thi.

### 11.3. Phiên bản và rollout

Thay đổi chính sách cần đi cùng khả năng tương thích của PEP. PDP có thể phát sinh giới hạn mới mà PEP cũ chưa hiểu.

Một chế độ chỉ quan sát quyết định hữu ích để so sánh trước khi áp dụng, nhưng nó chưa thực thi bảo vệ mới. Trong giai đoạn đó, các kiểm soát đang bảo vệ tài nguyên phải tiếp tục hoạt động cho tới khi lớp mới được xác nhận và bật enforcement theo kế hoạch.

Audit nên liên kết decision ID, phiên bản policy, subject, tenant, action, resource và kết quả thực thi. Không ghi token hoặc secret để chứng minh request đã được xác thực.

## 12. Ví dụ xuyên suốt và các tình huống cần kiểm chứng

Giả sử:

```text
Lan thuộc tenant An.
Lan được đọc doc-82 nhưng không được đọc doc-99.
Reports Service gọi Documents Service thay Lan.
```

Gateway xác thực request và kiểm tra được phép gọi Reports API. Reports Service tạo yêu cầu đọc tài liệu với identity context và ủy quyền phù hợp. Documents Service là PEP gần tài nguyên: nó phân giải tài liệu, đánh giá quyền và thực thi giới hạn trước khi trả nội dung.

Các tình huống sau cần cho kết quả khác nhau:

| Tình huống | Kết quả mong đợi |
|---|---|
| Lan yêu cầu đọc doc-82 trong tenant An, mọi điều kiện đạt | Trả biểu diễn được phép |
| Lan đổi ID sang doc-99 | Không trả nội dung không được phép |
| Request được chuyển sang tenant Bình | Đánh giá lại phạm vi; không dùng quyền tenant An |
| Reports Service gọi trực tiếp Documents Service | Vẫn cần danh tính, ủy quyền và quyền tài nguyên phù hợp |
| Có ALLOW đọc nhưng request thực hiện xóa | Không sử dụng quyết định đọc cho thao tác xóa |
| Tài liệu đổi thuộc tính làm ảnh hưởng quyền | Phát hiện hoặc đánh giá lại theo cơ chế nhất quán đã định nghĩa |
| PDP yêu cầu che trường nhưng PEP không hỗ trợ | Không trả dữ liệu như thể không có giới hạn |
| Job export chạy sau khi tenant bị khóa | Xử lý theo trạng thái và quyền hiện hành, không mặc định tiếp tục |
| PDP timeout | Không tự mở quyền |
| Link tải object còn tồn tại sau khi khóa phiên | Xử lý theo khả năng thu hồi đã thiết kế, không giả định đã bị chặn |
| Connection hoặc cache bị tái sử dụng giữa tenant | Không làm context hoặc quyết định tenant trước rò sang tenant sau |

Policy enforcement gần resource có hiệu quả khi quyết định được gắn với đối tượng và hành động thực tế, không thể bị bỏ qua và được áp dụng trước tác động. Gateway, workload identity, PDP, PEP và kiểm soát lưu trữ cần phối hợp để giới hạn quyền trên toàn bộ đường dữ liệu, thay vì dựa vào một lần kiểm tra ở lối vào hệ thống.
