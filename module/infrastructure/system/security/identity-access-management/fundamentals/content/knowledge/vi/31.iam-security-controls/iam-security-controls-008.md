# Authorization on every request

## 1. Kiểm tra quyền trên mỗi request nghĩa là gì?

**Authorization on every request** nghĩa là mỗi yêu cầu sử dụng tài nguyên được bảo vệ đều phải đi qua cơ chế quyết định và thực thi quyền phù hợp trước khi dữ liệu được tiết lộ hoặc hành động được thực hiện.

Một lần đăng nhập thành công không tạo ra quyền thực hiện mọi hành động trong phần còn lại của phiên. Mỗi request có thể nhắm tới một tài nguyên, tenant, trường dữ liệu hoặc thao tác khác, trong khi quyền và trạng thái hệ thống cũng có thể đã thay đổi.

Ví dụ, Lan được xem tài liệu `doc-82` trong tenant An. Điều đó chưa trả lời được Lan có được:

- Xem `doc-99` hay không.
- Xóa `doc-82` hay không.
- Đọc tài liệu của tenant Bình hay không.
- Tải tệp gốc có chứa dữ liệu nhạy cảm hay chỉ xem metadata.
- Tiếp tục truy cập sau khi membership bị đình chỉ.

Mỗi hành động trên là một yêu cầu cần được đánh giá theo ngữ cảnh tương ứng.

Nguyên tắc này không yêu cầu người dùng nhập mật khẩu hoặc thực hiện MFA ở mọi request. Nó cũng không bắt buộc mỗi request phải gọi một dịch vụ phân quyền từ xa hoặc truy vấn toàn bộ cơ sở dữ liệu. Điều bắt buộc là request không được bỏ qua kiểm soát quyền, và bằng chứng được sử dụng phải có phạm vi, hiệu lực và độ mới phù hợp với chính sách.

## 2. Xác thực và phân quyền là hai bước khác nhau

| Câu hỏi | Kiểm soát tương ứng | Ví dụ |
|---|---|---|
| Ai đang gửi request hoặc credential đại diện cho ai? | Authentication | Phiên hợp lệ ánh xạ tới subject `u-174` |
| Chủ thể đó được làm gì trên tài nguyên đang yêu cầu? | Authorization | Được đọc nhưng không được xóa tài liệu |
| Hành động được cho phép có được giới hạn đúng không? | Enforcement | Chỉ trả các trường được phép |
| Quyết định và hành động có thể được truy vết không? | Audit | Ghi subject, tenant, action, resource và kết quả |

Một token còn hạn và có chữ ký hợp lệ có thể giúp xác thực request. Nó không tự chứng minh chủ thể có quyền hiện tại trên mọi tài nguyên.

Tương tự, một session cookie hợp lệ không làm cho tất cả endpoint trong ứng dụng trở thành hợp lệ đối với người giữ cookie. Người dùng đã đăng nhập vẫn có thể gửi resource ID của người khác hoặc gọi một chức năng quản trị mà giao diện không hiển thị.

Một lỗi khái niệm thường gặp:

```text
nếu session đã đăng nhập:
    thực hiện hành động với resource ID client gửi
```

Điều kiện “đã đăng nhập” chỉ kiểm tra một phần của luồng. Trước hành động, hệ thống còn cần biết chủ thể được phép làm gì với đúng resource đó.

Các biện pháp như chống giả mạo request trong phiên cookie, xác thực đầu vào và bảo vệ injection vẫn cần thiết. Phân quyền trên mỗi request không thay thế các kiểm soát có mục tiêu khác.

## 3. Một quyết định quyền cần gắn với những gì?

Có thể biểu diễn yêu cầu phân quyền bằng các thành phần:

```text
subject
caller và ủy quyền nếu có
tenant hoặc phạm vi tổ chức
action
resource
thuộc tính và trạng thái liên quan
```

Ví dụ:

```text
subject = u-174
tenant  = tenant-an
action  = document.read
resource = doc-82
```

Quyết định cho bộ đầu vào này không tự được dùng cho `document.delete`, cho `doc-99` hoặc cho tenant khác.

### 3.1. Hành động nghiệp vụ

Một route có thể phục vụ nhiều khả năng khác nhau. Xem danh sách, xem chi tiết, tải tệp gốc, xuất hàng loạt và chia sẻ ra ngoài có thể cần các permission riêng.

Không đồng nhất “được gọi API” với “được thực hiện mọi thao tác mà API có thể gây ra”. Cũng không dùng HTTP method làm mô tả duy nhất của quyền; cần xét tác động nghiệp vụ thực sự.

### 3.2. Tài nguyên và tenant

Resource ID do client cung cấp là dữ liệu đầu vào, không phải bằng chứng sở hữu. Tenant ID trong URL hoặc header cũng chỉ là phạm vi được yêu cầu cho tới khi máy chủ kiểm tra nó với danh tính và chính sách.

Thuộc tính quan trọng của tài nguyên hiện có, như tenant, owner hoặc mức phân loại, cần lấy từ nguồn có thẩm quyền. Không tin một request tự khai `owner_id` là người gửi rồi cho phép sửa tài nguyên.

### 3.3. Trạng thái hiện tại

Ngoài role, có thể cần xét:

- Tài khoản có bị khóa không.
- Membership còn ACTIVE không.
- Tenant còn hoạt động không.
- Grant hoặc ủy quyền còn hiệu lực không.
- Tài nguyên có đang ở trạng thái cho phép thao tác không.
- Chính sách có yêu cầu xác thực gần đây hoặc điều kiện bổ sung không.

Các điều kiện phụ thuộc hành động và mô hình hệ thống. Không có một cờ `authorized=true` chung cho toàn bộ session thay thế được chúng.

## 4. Thiết kế luồng request có kiểm soát quyền

Một luồng điển hình:

```text
Nhận request
    |
    v
Xác thực và dựng identity context
    |
    v
Phân giải hành động, tenant và tài nguyên
    |
    v
Lấy thuộc tính và trạng thái cần thiết
    |
    v
Đánh giá quyền
    |
    +-- không được phép hoặc chưa đủ căn cứ --> dừng
    |
    v
Thực thi giới hạn bắt buộc
    |
    v
Đọc/ghi đúng tài nguyên đã đánh giá
    |
    v
Ghi nhận kết quả và trả response phù hợp
```

Pseudocode cho việc đọc tài liệu:

```text
readDocument(request):
    identity = authenticate(request)
    tenant = resolveRequestedTenant(request)

    resource = findDocumentMetadata(
        tenantId = tenant.id,
        documentId = request.documentId
    )

    if resource is absent:
        rejectAccordingToApiPolicy()

    state = loadAuthorizationState(identity, tenant, resource)

    decision = evaluate(
        identity = identity,
        action = "document.read",
        resource = resource,
        state = state
    )

    if decision.effect != ALLOW:
        rejectAccordingToApiPolicy()

    if not canApplyAllRequiredRestrictions(decision):
        rejectWithoutReturningDocument()

    return readAndRenderSameResource(resource, decision)
```

Đây là pseudocode mô tả trách nhiệm. `identity` phải được tạo từ cơ chế xác thực đáng tin cậy; request body không được tự cung cấp một đối tượng identity đã được coi là xác minh.

Service có thể cần đọc metadata nội bộ để đánh giá quyền, nhưng không được trả metadata đó cho caller trước khi được phép. Nội dung nhạy cảm cũng không được đi vào response hoặc log ở nhánh bị từ chối.

Một kết quả ALLOW có thể kèm giới hạn, như chỉ được xem metadata hoặc một tập trường. Nếu tầng trả dữ liệu không thực hiện được giới hạn bắt buộc, không được bỏ qua nó rồi trả toàn bộ entity.

## 5. Đặt kiểm tra ở nơi không dễ bị bỏ qua

### 5.1. Giao diện không phải nơi bảo vệ cuối cùng

Ẩn nút “Delete” giúp giao diện phù hợp với quyền, nhưng caller vẫn có thể gửi request trực tiếp. Máy chủ phải kiểm tra lại hành động xóa.

Tương tự, một danh sách tài liệu chỉ hiển thị tài liệu được phép không làm endpoint chi tiết an toàn. Client có thể yêu cầu một ID khác ngoài danh sách.

### 5.2. Gateway và service có trách nhiệm riêng

Gateway có thể xác thực, giới hạn route hoặc kiểm tra scope tổng quát. Service sở hữu tài nguyên thường có thông tin để kiểm tra tenant, owner, nhóm và trạng thái đối tượng.

Không bỏ kiểm tra quyền ở service chỉ vì request đã đi qua gateway. Cần bảo đảm các đường gọi nội bộ hoặc đường khác tới service không làm mất lớp kiểm soát bắt buộc.

Danh tính gateway hoặc một workload quen thuộc cũng không chứng minh caller được hành động thay mọi người dùng. Luồng thay mặt cần bảo toàn subject, caller, phạm vi ủy quyền và đích nhận phù hợp.

### 5.3. Các điểm vào khác HTTP controller

Cùng một thao tác nghiệp vụ có thể được gọi từ:

- API người dùng.
- API quản trị.
- Consumer của queue.
- Scheduler.
- CLI vận hành.
- Một service khác.
- Workflow tự động.

Nếu chỉ kiểm tra ở controller mà một job gọi trực tiếp hàm ghi dữ liệu, nguyên tắc chưa được bao phủ.

Có thể đặt enforcement tại một ranh giới service dùng chung, hoặc thiết kế PEP thích hợp cho từng đường. Điều cần chứng minh là mọi đường thực hiện tác động đều có kiểm tra quyền tương ứng, không chỉ là code có xuất hiện một hàm `checkPermission`.

## 6. Kiểm tra ở mức đối tượng và trường dữ liệu

### 6.1. Mức đối tượng

Lan được đọc một tài liệu không có nghĩa được đọc mọi tài liệu cùng loại.

Ví dụ, truy vấn có tenant scope:

```sql
SELECT document_id, tenant_id, owner_id, classification, version
FROM documents
WHERE tenant_id = :requested_and_checked_tenant_id
  AND document_id = :document_id;
```

Điều kiện tenant giúp giới hạn việc phân giải tài nguyên, nhưng vẫn cần kiểm tra quyền theo tài liệu nếu chính sách yêu cầu. Trong cùng tenant, tài liệu có thể chỉ cho một nhóm cụ thể đọc.

Ngược lại, kiểm tra role mà sau đó thực hiện truy vấn không giữ tenant scope có thể làm kết quả được áp dụng sai phạm vi.

### 6.2. Mức trường

Quyền chỉnh hồ sơ có thể chỉ bao gồm tên hiển thị và số liên lạc. Không vì vậy cho phép cập nhật `role`, `tenant_id` hoặc trạng thái xác thực bằng cùng một payload.

Cần xác định những trường được phép ghi và những hành động nhạy cảm cần permission riêng. Không bind mọi field từ request vào entity rồi hy vọng quyền trên endpoint đã đủ.

Ở chiều đọc, một người có thể được xem thông tin yêu cầu hỗ trợ nhưng không được xem ghi chú mật hoặc credential đi kèm. Response cần phản ánh đúng quyền trên dữ liệu, thay vì serialize toàn bộ đối tượng nội bộ.

### 6.3. Quan hệ tài nguyên

Với URL như:

```http
GET /projects/project-12/documents/doc-82
```

Cần xác minh `doc-82` thực sự thuộc `project-12`, rồi đánh giá quyền theo các quan hệ đúng. Không kiểm tra quyền trên project được phép rồi tải một document ID không liên quan ở bước sau.

## 7. Mỗi request không nhất thiết là một lần đọc lại mọi dữ liệu

Cơ chế phân quyền có thể dùng policy cục bộ, session phía máy chủ, token có phạm vi hoặc cache quyết định. Tuy vậy, cách tối ưu phải giữ đúng ý nghĩa và giới hạn của bằng chứng.

### 7.1. Snapshot trong token

Role hoặc scope trong token thường phản ánh thông tin ở lúc phát hành. Nó có thể không còn khớp sau khi quyền bị thay đổi.

Scope cũng thường là giới hạn của những hành động mà credential có thể yêu cầu, không phải bằng chứng độc lập rằng subject được phép đối với mọi resource ID.

Cần xác định rõ điều kiện nào API chấp nhận từ token, điều kiện nào phải lấy từ trạng thái hiện tại và cơ chế thu hồi áp dụng.

### 7.2. Cache quyết định

Một cache an toàn về ý nghĩa cần xét những đầu vào ảnh hưởng tới quyền, chẳng hạn:

```text
subject + tenant + action + resource
+ caller/ủy quyền nếu chính sách sử dụng
+ phiên bản quyền và thuộc tính liên quan
```

Có thể dùng phiên bản hoặc cơ chế vô hiệu hóa thay cho việc nhồi mọi thuộc tính vào khóa. Nhưng cache chỉ theo user ID không đủ nếu người dùng có quyền khác nhau theo tenant và tài nguyên.

Một ALLOW cho đọc tài liệu không được dùng cho xóa tài liệu. Một ALLOW trước khi tài liệu chuyển thành hạn chế không được giữ vô hạn sau thay đổi đó.

### 7.3. Độ trễ thu hồi

Giả sử:

```text
T0: Lan được cấp quyền đọc.
T1: API cho phép một request hợp lệ.
T2: Quyền của Lan bị thu hồi.
T3: Lan gửi request mới bằng token còn hạn.
```

T3 cần được xử lý theo cơ chế thu hồi và giới hạn độ trễ mà hệ thống đã định nghĩa. Nếu yêu cầu thu hồi tức thời, kiến trúc phải có cơ chế kiểm tra đủ mới hoặc vô hiệu hóa tương ứng; chỉ chờ token tự hết hạn không đáp ứng yêu cầu đó.

Không tuyên bố “đã kiểm tra trên mỗi request nên thu hồi ngay” khi mỗi lần kiểm tra vẫn dùng cùng một snapshot cũ.

## 8. Cạnh tranh giữa kiểm tra và thực hiện

Kiểm tra ở đầu request chưa tự bảo đảm điều kiện còn đúng ở thời điểm cập nhật.

Ví dụ:

```text
1. Request được phép sửa vì Lan là owner.
2. Một giao dịch khác chuyển owner.
3. Request đầu tiên ghi dữ liệu theo kết quả cũ.
```

Cần xác định điểm nhất quán mà nghiệp vụ yêu cầu và những thay đổi làm quyết định mất hiệu lực.

Các biện pháp có thể gồm:

- Giao dịch với cơ chế khóa được các luồng liên quan cùng tuân thủ.
- Kiểm tra phiên bản tài nguyên khi ghi.
- Kiểm tra phiên bản quyền hoặc trạng thái grant theo cơ chế phù hợp.
- Thao tác dữ liệu có điều kiện.
- Đánh giá lại trước một giai đoạn nhạy cảm của workflow.

Ví dụ kiểm tra phiên bản đối tượng:

```sql
UPDATE documents
SET title = :new_title,
    version = version + 1
WHERE tenant_id = :checked_tenant_id
  AND document_id = :checked_document_id
  AND version = :evaluated_version;
```

Câu lệnh này giúp phát hiện tài liệu đã thay đổi so với phiên bản được đánh giá. Nó chưa tự xử lý thay đổi membership hoặc policy nằm ở nơi khác. Cần có cơ chế tương ứng với từng điều kiện muốn bảo đảm.

Nếu không còn hàng nào khớp, ứng dụng cần xử lý kết quả thay vì báo cập nhật thành công. Không chuyển nhánh không khớp thành một lần thử lại bỏ kiểm tra quyền hoặc bỏ tenant scope.

## 9. Danh sách, batch, export và request lặp

### 9.1. Danh sách và tìm kiếm

Quyền gọi endpoint tìm kiếm không cho phép trả toàn bộ kết quả trong hệ thống.

Có thể biểu diễn chính sách bằng bộ lọc truy vấn hoặc đánh giá phù hợp trên tập tài nguyên. Không bắt buộc mỗi hàng phải gọi PDP từ xa riêng lẻ, nhưng kết quả cuối cùng và dữ liệu liên quan phải nằm trong phạm vi được phép.

Tổng số kết quả, facet, gợi ý, preview và số trang cũng có thể tiết lộ dữ liệu ngoài quyền. Không chỉ ẩn nội dung từng hàng mà bỏ qua các trường tổng hợp này.

### 9.2. Batch

Một batch có nhiều ID cần kiểm tra quyền đối với các phần tử liên quan, không chỉ ID đầu tiên hoặc tenant của request.

Ứng dụng phải xác định hợp đồng: toàn bộ cùng thành công hay cho phép kết quả từng phần. Nếu yêu cầu nguyên tử, cần kết hợp đánh giá quyền với cơ chế thực hiện dữ liệu phù hợp; không cập nhật vài đối tượng rồi mới phát hiện một đối tượng bị cấm.

### 9.3. Export

Quyền xem một trang dữ liệu không nhất thiết bao gồm quyền xuất toàn bộ. Export cần xem xét phạm vi, số lượng, loại dữ liệu và nơi nhận theo chính sách.

Job export còn cần được kiểm tra tại lúc thực thi theo mô hình grant hoặc ủy quyền đã chọn. File kết quả là một tài nguyên riêng; tải file cũng cần có quyền thích hợp.

### 9.4. Retry và idempotency

Idempotency giúp tránh lặp tác động, không thay thế phân quyền.

Một request lặp có cùng idempotency key vẫn cần được gắn với chủ thể, tenant và thao tác đúng. Không cho một người dùng nhận lại response nhạy cảm của người khác chỉ vì đoán được hoặc tái sử dụng key.

Khi quyền đã thay đổi, việc trả kết quả cũ hoặc cho tiếp tục truy cập cần tuân theo chính sách hiện tại và hợp đồng của thao tác. Không dùng “đã chạy lần trước” làm lý do bỏ mọi kiểm tra ở request sau.

## 10. Async, kết nối dài và liên kết truy cập trực tiếp

### 10.1. Queue và tác vụ nền

Message có `user_id` không tự chứng minh job được hành động thay người đó. Consumer cần xác thực nguồn và kiểm tra grant hoặc ủy quyền theo mô hình đã chọn.

Người khởi tạo được lưu cho audit và chủ thể có quyền thực thi có thể khác nhau. Một job hệ thống có grant riêng cần được đánh giá như workload; một job theo ủy quyền người dùng cần tôn trọng giới hạn và hiệu lực của ủy quyền.

Tenant bị khóa hoặc grant hết hạn trước lúc consumer chạy phải được xử lý theo chính sách, thay vì mặc định cho phép vì message được tạo trước đó.

### 10.2. WebSocket và stream

Xác thực khi mở kết nối không tự cấp quyền cho mọi message và subscription trên kết nối.

Cần kiểm tra khi đăng ký tài nguyên hoặc kênh mới, khi thực hiện hành động và khi điều kiện yêu cầu đánh giá lại xuất hiện. Với luồng server chủ động đẩy dữ liệu, phải có cơ chế ngừng gửi khi quyền thay đổi theo yêu cầu thu hồi.

Không nhất thiết kiểm tra lại từng byte dữ liệu. Cần xác định đơn vị hành động, điểm đánh giá lại và độ trễ chấp nhận được, sao cho phiên dài không trở thành quyền vô thời hạn.

### 10.3. Liên kết tải trực tiếp

Một URL cho phép tải object có thể đóng vai trò quyền truy cập trong điều kiện mà nơi lưu trữ thực thi. Việc cấp URL phải được phân quyền và phạm vi tải cần được giới hạn phù hợp.

Sau khi URL được phát hành, khóa phiên ứng dụng không tự bảo đảm URL hết hiệu lực. Nếu cần thu hồi sớm, kiến trúc phải dùng cơ chế được nơi phục vụ object hỗ trợ hoặc một cổng tải có thể kiểm tra quyền.

### 10.4. Cache response và các biến thể request

Không để cache response có dữ liệu riêng tái sử dụng kết quả cho subject hoặc tenant khác chỉ vì URL giống nhau.

Request chỉ lấy metadata, HEAD hoặc request có điều kiện vẫn có thể tiết lộ sự tồn tại, phiên bản hoặc thuộc tính tài nguyên. Chúng cần đi qua chính sách phù hợp; không mặc định bỏ kiểm tra vì không trả toàn bộ nội dung.

## 11. Xử lý thiếu bằng chứng, lỗi và tài nguyên công khai

Default deny có nghĩa request không có căn cứ cho phép phù hợp không được thực hiện tác động được bảo vệ. Thiếu một field bắt buộc hoặc lỗi đánh giá không nên trở thành quyền mặc định.

Cần phân biệt:

| Tình huống | Ý nghĩa |
|---|---|
| Credential không hợp lệ hoặc không đáp ứng yêu cầu xác thực | Chưa có danh tính được chấp nhận cho luồng |
| Danh tính hợp lệ nhưng không có quyền | Quyết định từ chối theo chính sách |
| Không thể lấy thuộc tính hoặc đánh giá policy | Lỗi vận hành hoặc chưa đủ căn cứ |
| Tài nguyên công khai theo một policy rõ ràng | Có thể cho anonymous thực hiện hành động được công khai |

Các tình huống này có thể cần phản hồi khác nhau, nhưng không được làm lộ dữ liệu trước khi quyền được xác nhận. Quy ước phản hồi cũng cần cân nhắc việc tiết lộ sự tồn tại của tài nguyên.

Khi hệ thống phân quyền lỗi, không chuyển sang “cho phép mọi user đã đăng nhập”. Nếu có chế độ suy giảm, nó cần được thiết kế trước với nguồn chính sách được tin cậy, hiệu lực và phạm vi hành động rõ ràng.

“Trên mỗi request” không có nghĩa buộc mọi trang công khai phải có user account. Nó có nghĩa quyền truy cập công khai cũng là một quyết định rõ ràng cho hành động và tài nguyên đó. Các endpoint hạ tầng hoặc request hỗ trợ giao thức cần có chính sách riêng; không được dùng chúng như lối vào để bỏ qua kiểm tra trên hành động nghiệp vụ.

Xác thực bổ sung có thể là điều kiện để cho phép một hành động nhạy cảm. Nhưng người đã bị thu hồi membership không được lấy lại quyền chỉ bằng việc thực hiện MFA.

## 12. Ví dụ kiểm chứng theo chuỗi request

Giả sử:

```text
Lan / tenant-an:
    doc-82: được đọc, không được xóa
    doc-99: không được đọc

Lan / tenant-binh:
    không có membership
```

Các request cần được xử lý độc lập theo đầu vào của chúng:

| Request hoặc thay đổi | Kết quả mong đợi |
|---|---|
| Đọc doc-82 trong tenant An | Trả dữ liệu trong phạm vi được phép |
| Đọc doc-99 bằng cùng session | Từ chối |
| Xóa doc-82 sau lần đọc thành công | Từ chối |
| Đổi tenant trong URL sang tenant Bình | Không sử dụng quyền tenant An |
| Gửi owner hoặc role tự khai trong body | Không lấy làm bằng chứng cấp quyền |
| Gọi endpoint nội bộ để đọc doc-99 | Vẫn kiểm tra quyền tương ứng |
| Batch chứa doc-82 và doc-99 | Áp dụng chính sách cho từng phần tử và hợp đồng batch |
| Lan bị đình chỉ rồi gọi lại bằng token còn hạn | Áp dụng cơ chế thu hồi với độ trễ đã xác định |
| PDP không trả lời | Không tự mở quyền |
| Một request lặp dùng idempotency key của người khác | Không trả lại dữ liệu ngoài quyền |
| Đăng ký thêm tài liệu trên WebSocket | Kiểm tra quyền đối với subscription mới |
| Một job cũ chạy sau khi tenant bị khóa | Xử lý theo trạng thái và grant hợp lệ hiện tại |

Audit hữu ích khi liên kết được subject, caller, tenant, action, resource, quyết định và kết quả thực thi. Không ghi token hoặc secret vào log. Những lần từ chối cũng cần có thông tin đủ để phân biệt lỗi cấu hình với hành vi yêu cầu ngoài phạm vi, trong giới hạn lưu trữ và truy cập đã được quy định.

Authorization on every request giữ cho quyền truy cập luôn gắn với hành động cụ thể thay vì một lần đăng nhập trong quá khứ. Kiểm soát này có hiệu lực khi bao phủ mọi đường thực hiện tác động, sử dụng ngữ cảnh đáng tin cậy và giữ đúng phạm vi cùng hiệu lực của các quyết định được dùng lại.
