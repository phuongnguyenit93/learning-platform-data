# Directory synchronization — đồng bộ thư mục danh tính

Một nhân viên đã chuyển phòng hoặc nghỉ việc trong hệ thống nhân sự, nhưng tài khoản ở directory và ứng dụng đích vẫn giữ trạng thái cũ. Những dữ liệu nguồn đúng chưa đủ bảo đảm quyền truy cập đúng nếu thay đổi không đến được nơi thực thi.

**Directory synchronization** là quá trình duy trì dữ liệu danh tính hoặc những quan hệ được quản lý giữa nguồn và một hay nhiều thư mục, identity store hoặc hệ thống đích. Quá trình này có thể tạo tài khoản, cập nhật thuộc tính, điều chỉnh membership và phản ánh trạng thái vòng đời theo một hợp đồng xác định.

Đồng bộ an toàn cần nhiều hơn thao tác sao chép field. Hệ thống phải nhận diện đúng đối tượng, biết nguồn nào có thẩm quyền, phát hiện thay đổi, áp dụng đúng thứ tự, xử lý lỗi và kiểm chứng trạng thái ở đích. Trong IAM, một thay đổi bị bỏ sót có thể giữ lại quyền cũ; một thay đổi bị hiểu sai có thể vô hiệu hóa hàng loạt tài khoản hợp lệ.

## 1. Mục tiêu và các ranh giới khái niệm

Sau bài học, bạn có thể:

- Phân biệt directory synchronization với replication, federation và xác thực.
- Thiết kế phạm vi đồng bộ, quyền làm chủ thuộc tính và phép ánh xạ định danh.
- Giải thích khác biệt giữa full sync, delta sync và đối soát.
- Quản lý checkpoint mà không làm mất thay đổi chưa áp dụng.
- Xử lý giao lại, xung đột, lỗi từng phần và trạng thái chưa biết sau timeout.
- Kiểm chứng tác động của đồng bộ đến vòng đời tài khoản và quyền thực tế.

| Khái niệm | Câu hỏi chính |
| --- | --- |
| Directory synchronization | Những bản ghi hoặc quan hệ được quản lý ở đích đã phản ánh nguồn theo hợp đồng chưa? |
| Database/directory replication | Các bản sao của một hệ thống đang được sao chép theo cơ chế nội bộ như thế nào? |
| Federation/SSO | Hệ thống nhận tin cậy thông tin xác thực hoặc danh tính từ bên phát hành như thế nào? |
| Authentication | Chủ thể có chứng minh được phương tiện xác thực theo yêu cầu không? |
| Authorization | Chủ thể có được thực hiện hành động này trên tài nguyên này không? |

Một người có thể SSO thành công nhưng ứng dụng đích chưa có tài khoản hoặc còn giữ role cũ. Ngược lại, có tài khoản được đồng bộ không chứng minh người dùng đã đăng nhập, hoàn tất MFA hay có mọi quyền nghiệp vụ.

## 2. Bắt đầu bằng hợp đồng đồng bộ

### 2.1. Phạm vi cần được xác định trước khi chạy

Ví dụ một hợp đồng minh họa:

```text
Nguồn: directory doanh nghiệp A
Đích: ứng dụng quản lý tài liệu
Tenant: tenant-a
Đối tượng: nhân viên thuộc tập được phê duyệt cho ứng dụng
Thuộc tính nguồn quản lý: tên hiển thị, phòng ban chính, trạng thái sử dụng
Quan hệ nguồn quản lý: membership do rule tài liệu phòng ban tạo
Ngoài phạm vi: quyền đặc biệt được cấp qua quy trình độc lập
```

Hợp đồng còn phải quy định nguồn có thẩm quyền, cách nhận diện đối tượng, xử lý thay đổi hiệu lực tương lai, lỗi, thu hồi và điều kiện xem là hoàn tất. Các giá trị trong bài là dữ liệu thiết kế minh họa, không phải cấu hình của một nhà cung cấp cụ thể.

### 2.2. Quyền làm chủ theo từng field và quan hệ

| Dữ liệu | Nguồn làm chủ trong ví dụ | Hành vi tại đích |
| --- | --- | --- |
| Phòng ban chính | Nguồn tổ chức đã được xác minh | Chỉ connector được ủy quyền cập nhật |
| Tên hiển thị | Directory theo mapping đã duyệt | Cập nhật bản sao theo hợp đồng |
| Tùy chọn giao diện | Người dùng tại ứng dụng | Connector không ghi đè |
| Nhóm tài liệu theo phòng | Rule provisioning | Theo dõi lý do cấp và thu hồi |
| Ngoại lệ kiểm toán | Quy trình phê duyệt riêng | Không tự xóa vì không có trong nguồn phòng ban |
| Security hold cục bộ | Quy trình bảo mật được ủy quyền | Không bị field active từ nguồn khác tự gỡ |

Đồng bộ hai chiều không có nghĩa hai phía đều được sửa mọi field. Nếu không tách thẩm quyền, một bản sao cũ có thể ghi ngược lên nguồn và tạo vòng lặp thay đổi.

### 2.3. Scope là một phần của trạng thái đồng bộ

Scope có thể gồm tenant, loại đối tượng, filter, nhánh directory, các thuộc tính được chọn và quyền truy cập của connector. Một checkpoint của scope cũ không tự hợp lệ cho scope mới.

Ví dụ, connector trước đây đọc mọi nhân viên, sau đó bị giới hạn chỉ còn một phòng. Các đối tượng không xuất hiện có thể chỉ nằm ngoài phạm vi mới, không phải đã nghỉ việc. Cần quản lý thay đổi scope như một thay đổi cấu hình có tác động đến dữ liệu và quyền.

## 3. Liên kết đúng đối tượng qua các hệ thống

### 3.1. Dùng định danh nguồn ổn định và mapping rõ ràng

Một bản mapping có thể là:

```json
{
  "tenantId": "tenant-a",
  "sourceSystem": "corp-directory-a",
  "sourceObjectId": "source-user-901",
  "internalSubjectId": "subject-2048",
  "targetSystem": "document-app",
  "targetObjectId": "target-user-733",
  "managedBy": "connector-docs-a"
}
```

Khóa liên kết cần chứa miền nguồn và tenant phù hợp, không chỉ một chuỗi trông có vẻ duy nhất. Mapping phải được lưu bền vững và có ràng buộc ngăn một đối tượng nguồn bị gắn nhầm sang nhiều tài khoản theo cách ngoài hợp đồng.

Username, email và vị trí trong cây tổ chức có thể thay đổi. Một lần đổi tên hoặc di chuyển entry không nên tự tạo ra một người dùng mới nếu nguồn vẫn xác định đó là cùng đối tượng.

### 3.2. Không tự gộp tài khoản chỉ vì email trùng

Khi một connector mất mapping, tìm thấy tài khoản cùng email ở đích chưa đủ để tự nhận quyền quản lý nó. Địa chỉ có thể được tái sử dụng, thuộc một nguồn khác hoặc là tài khoản có sẵn ngoài phạm vi connector.

Luồng khôi phục mapping cần kiểm tra các bằng chứng và quy tắc correlation đã được duyệt. Khi không xác định được, đánh dấu xung đột để xử lý thay vì ghi đè tài khoản đầu tiên tìm thấy.

### 3.3. Phân biệt ID nguồn và ID do đích cấp

Trong SCIM, `id` là định danh ổn định do service provider cấp; `externalId` do provisioning client cấp và được hiểu trong provisioning domain tương ứng. Hai trường không thể thay thế tùy ý cho nhau. [Nguồn: RFC 7643 — Common Attributes](https://www.rfc-editor.org/rfc/rfc7643.html#section-3.1).

Một connector có thể dùng external ID cùng tenant và miền provisioning để hỗ trợ correlation, nhưng vẫn phải lưu hoặc khôi phục mapping đến ID tài nguyên đích. Không giả định mọi server đều tự áp đúng ràng buộc duy nhất mà ứng dụng mong muốn cho external ID.

## 4. Full sync, delta sync và đối soát

### 4.1. Full synchronization

Full sync đọc toàn bộ tập đối tượng thuộc scope rồi so với trạng thái đang được quản lý ở đích. Nó hữu ích để khởi tạo baseline hoặc tìm chênh lệch không xuất hiện trong luồng thay đổi.

“Toàn bộ” ở đây là toàn bộ scope đã định nghĩa với quyền đọc tương ứng, không phải toàn bộ doanh nghiệp. Một lần chạy chỉ đọc được một phần dữ liệu không được đánh dấu thành baseline đầy đủ.

### 4.2. Delta synchronization

Delta sync đọc những thay đổi kể từ một trạng thái đã ghi nhận. Cơ chế có thể là change log, cookie, token delta hoặc API riêng của nhà cung cấp. Không phải mọi directory hoặc API đều hỗ trợ cùng một kiểu delta.

Nếu chỉ dùng filter theo `lastModified`, cần đánh giá độ chính xác timestamp, những bản ghi cùng thời điểm, thay đổi đồng thời và cách nhận biết xóa. Một truy vấn các hàng còn tồn tại sau timestamp không tự cho biết những hàng đã bị xóa.

### 4.3. Reconciliation — đối soát

Đối soát so sánh trạng thái mong muốn với trạng thái thực tế được quan sát ở đích. Nó có thể phát hiện connector đã bỏ sót, quản trị viên sửa tay hoặc một ứng dụng không áp dụng được thay đổi.

Delta giúp giảm lượng dữ liệu thường xuyên xử lý; đối soát giúp phát hiện sai lệch còn lại. Hai cơ chế bổ sung cho nhau khi hệ thống không thể coi việc giao mọi thay đổi là tuyệt đối đầy đủ.

### 4.4. Push và pull là cách vận chuyển, chưa phải bảo đảm hoàn tất

Pull yêu cầu connector chủ động lấy thay đổi. Push hoặc webhook báo có thay đổi, nhưng thông báo có thể chỉ là tín hiệu để đọc lại resource, không chứa trạng thái đầy đủ hoặc thứ tự toàn cục.

Cần đọc đúng hợp đồng của nguồn: message là snapshot, delta từng field, hay thông báo “hãy tải lại”. Không áp payload thiếu field như thể nó là toàn bộ hồ sơ mới.

## 5. Baseline đầy đủ và việc phát hiện đối tượng biến mất

### 5.1. Một lần quét nên có danh tính và trạng thái riêng

Một run có thể lưu `runId`, phiên bản cấu hình, scope fingerprint, điểm bắt đầu đọc, số trang và trạng thái hoàn tất. Mỗi đối tượng nguồn được ghi nhận đã xuất hiện trong run nào.

Chỉ sau khi xác nhận quét đầy đủ và có đủ bảo đảm của nguồn mới được xét các mapping trước đây có nhưng lần này vắng mặt. Các bước áp dụng xóa hoặc vô hiệu hóa vẫn phải theo hợp đồng và giới hạn quản lý đối tượng.

Không thực hiện “mọi đối tượng chưa nhìn thấy đều bị xóa” ngay sau trang đầu tiên. Không coi timeout ở trang cuối là một danh sách rỗng hợp lệ.

### 5.2. Phân trang không tự tạo snapshot nhất quán

Nếu đối tượng được thêm hoặc xóa trong lúc dùng phân trang theo offset, dữ liệu có thể dịch chuyển giữa các trang. Tổng số bản ghi hoặc việc đọc đến trang cuối chưa chắc chứng minh đã có một snapshot nhất quán tại một thời điểm.

SCIM quy định pagination không có trạng thái và client phải chuẩn bị cho kết quả có thể không nhất quán khi dữ liệu thay đổi giữa các request. [Nguồn: RFC 7644 — Pagination](https://www.rfc-editor.org/rfc/rfc7644.html#section-3.4.2.4).

Tùy nguồn, thiết kế có thể cần snapshot token, baseline kết hợp cửa sổ delta, kiểm tra lại đối tượng vắng mặt hoặc một quy trình đối soát bổ sung. Không suy ra bảo đảm snapshot từ tên một API “list all”.

### 5.3. Vắng mặt chưa đồng nghĩa đã bị xóa

| Hiện tượng | Khả năng cần kiểm tra |
| --- | --- |
| Số đối tượng giảm mạnh | Quyền connector thay đổi hoặc filter sai |
| Một đối tượng không được trả về | Ra khỏi scope, bị ẩn hoặc đã xóa |
| Một trang rỗng | Hết dữ liệu theo giao thức, hoặc vẫn còn continuation |
| Một nhóm ít thành viên hơn | Dữ liệu chưa đủ trang hoặc quan hệ đã đổi |
| Connector không truy cập được nguồn | Chưa biết trạng thái hiện hành |

Một tín hiệu xóa có thẩm quyền hoặc một lần xác minh vắng mặt theo hợp đồng có thể dẫn đến hành động thu hồi. Còn kết quả đọc thiếu phải giữ trạng thái chưa xác định và được xử lý như lỗi hoặc sai lệch.

Nếu hệ thống cần thu hồi khẩn cấp khi nghỉ việc, không nên chỉ dựa vào việc chờ một full scan kết luận đối tượng biến mất. Cần thiết kế đường nhận trạng thái vòng đời phù hợp với thời gian thu hồi yêu cầu.

## 6. Delta token và checkpoint

### 6.1. Checkpoint trả lời câu hỏi nào?

Có ít nhất ba mốc khác nhau:

```text
Đã đọc từ nguồn
    -> Đã ghi công việc cần áp dụng vào nơi lưu bền vững
        -> Đã áp dụng và kiểm chứng ở đích
```

Nếu một field chỉ tên `lastSync` được dùng cho cả ba, hệ thống dễ báo thành công khi mới nhận dữ liệu hoặc làm mất thay đổi chưa áp dụng.

`lastAttemptAt`, `lastSourceCaptureAt` và `lastTargetVerifiedAt` có thể phục vụ ba mục đích riêng. Tên field cụ thể tùy thiết kế; ý nghĩa phải đủ rõ để vận hành biết còn tồn tại quyền cũ ở đâu.

### 6.2. Hai mô hình checkpoint có thể dùng

**Mô hình xử lý trực tiếp:** đọc một đơn vị thay đổi, áp dụng, xác minh và ghi tiến độ theo cơ chế đủ an toàn. Không tiến checkpoint vượt thay đổi thất bại rồi bỏ quên nó. Những thay đổi phụ thuộc thứ tự cần được quản lý cùng luồng.

**Mô hình tách capture và apply:** đọc thay đổi, lưu bền vững từng công việc cùng thông tin replay, rồi mới tiến source checkpoint. Worker áp dụng các công việc độc lập theo hợp đồng thứ tự và cập nhật kết quả đích riêng.

Mô hình thứ hai có thể tiến checkpoint nguồn trong khi đích còn chờ, vì thay đổi đã được tiếp nhận bền vững. Nó không được gọi trạng thái đích đã đồng bộ khi những công việc đó còn thất bại hoặc đang chờ.

### 6.3. Không mất dữ liệu giữa capture và checkpoint

```text
page = readSource(savedCursor)
validatePageAndScope(page)

in a durable local transaction:
    persist work items for all relevant changes in page
    persist page metadata and deduplication identifiers
    save next source cursor allowed by the source protocol

commit
```

Pseudocode này giả định kho công việc và checkpoint tham gia cùng đơn vị commit cục bộ. Nếu chúng ở hai hệ thống không có bảo đảm đó, cần thiết kế cơ chế phục hồi tương ứng thay vì coi hai lệnh ghi liên tiếp là atomic.

Lỗi sau khi ghi công việc nhưng trước khi tiến cursor có thể dẫn đến đọc lại; deduplication giúp tránh tạo hiệu ứng lặp. Lỗi sau khi tiến cursor nhưng trước khi lưu công việc có thể làm mất thay đổi, nên thứ tự và ranh giới commit là trọng tâm của thiết kế.

### 6.4. Ví dụ token riêng của nhà cung cấp

Microsoft Graph delta query dùng `@odata.nextLink` để tiếp tục đọc các trang và `@odata.deltaLink` khi hoàn tất vòng hiện tại. Trang rỗng vẫn có thể còn nextLink; các state token là opaque, không được tự giải nghĩa hoặc sửa. [Nguồn: Microsoft Graph — Delta query overview](https://learn.microsoft.com/en-us/graph/delta-query-overview).

Đây là cơ chế của Microsoft Graph, không phải thuộc tính bắt buộc của mọi API directory. Khi dùng nó, connector phải tuân thủ hợp đồng URL, tham số và phạm vi của nguồn, đồng thời áp dụng đúng cơ chế lưu checkpoint đã chọn.

Cookie hoặc delta state có thể không còn được nguồn chấp nhận. Quy trình phải biết khi nào cần refresh hoặc khởi tạo baseline lại; không xóa hàng loạt tài khoản đích chỉ vì trạng thái delta không dùng được.

## 7. Áp dụng thay đổi bằng giao thức phù hợp

### 7.1. SCIM là giao diện quản lý resource

SCIM cho phép trao đổi và cập nhật User/Group theo schema và khả năng server hỗ trợ. Nó không tự định nghĩa toàn bộ thuật toán phát hiện thay đổi, nguồn có thẩm quyền hoặc quy trình thu hồi phiên của sản phẩm.

Một request minh họa để phản ánh trạng thái cần vô hiệu hóa:

```http
PATCH /scim/v2/Users/target-user-733 HTTP/1.1
Host: document-app.example.com
Authorization: Bearer <authorized-provisioning-token>
Content-Type: application/scim+json
If-Match: W/"target-version-41"

{
  "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations": [
    {
      "op": "replace",
      "path": "active",
      "value": false
    }
  ]
}
```

Ví dụ giả định server hỗ trợ PATCH và conditional update; ETag được lấy từ resource đã đọc. Không gửi một giá trị phiên bản tự đoán.

Trong SCIM, `active` diễn tả trạng thái quản trị của User với ý nghĩa cụ thể do service provider xác định. Connector phải hiểu hành vi của ứng dụng đích; không mặc định một lần ghi false đã thu hồi mọi phiên hoặc credential. [Nguồn: RFC 7643 — User Attributes](https://www.rfc-editor.org/rfc/rfc7643.html#section-4.1.1).

### 7.2. Cập nhật đúng phần mình quản lý

Nếu connector chỉ làm chủ department và display name, không ghi lại toàn bộ resource từ một bản cache cũ để đổi hai field ấy. Việc thay toàn bộ member list của một nhóm có thể làm mất các membership do nguồn khác quản lý.

Khi conditional update cho thấy resource đã thay đổi, đọc lại và tính chênh lệch theo quyền làm chủ hiện hành. Không bỏ điều kiện phiên bản rồi gửi lại payload cũ chỉ để request thành công.

### 7.3. LDAP synchronization tùy khả năng server

RFC 4533 mô tả LDAP Content Synchronization với các chế độ `refreshOnly`, `refreshAndPersist` và cookie trạng thái. Đây là một RFC thuộc loại Experimental; không thể giả định mọi LDAP server triển khai cơ chế này. [Nguồn: RFC 4533](https://www.rfc-editor.org/rfc/rfc4533.html).

Với bất kỳ sản phẩm directory nào, cần xác minh khả năng đồng bộ được hỗ trợ, cách xử lý cookie, scope, quyền đọc và trường hợp phải refresh. Dữ liệu đọc được qua LDAP Search thông thường không tự có mọi bảo đảm của một change tracking protocol.

## 8. Lỗi từng phần, retry và kết quả chưa biết

### 8.1. Phân loại lỗi trước khi quyết định thử lại

| Loại tình huống | Cách xử lý cần thiết |
| --- | --- |
| Dữ liệu không phù hợp schema hoặc mapping | Ghi rõ đối tượng lỗi, sửa dữ liệu hoặc cấu hình |
| Connector thiếu quyền hoặc credential không hợp lệ | Xử lý kết nối và phạm vi, không coi nguồn là rỗng |
| Bị giới hạn tốc độ hoặc lỗi tạm thời | Retry có giới hạn, backoff và tuân thủ chỉ dẫn của nguồn/đích |
| Resource thay đổi so với version đã đọc | Đọc lại và lập kế hoạch theo trạng thái hiện hành |
| Mapping không xác định được | Chuyển case correlation, tránh ghi nhầm đối tượng |
| Request timeout sau khi đã gửi | Xác minh kết quả trước khi phát lại thao tác có thể tạo hiệu ứng mới |

Không retry vô hạn một lỗi schema cố định. Không bỏ một công việc thu hồi quyền khỏi báo cáo chỉ vì nó đã được đưa vào hàng đợi lỗi.

Retry nên có số lần, thời điểm kế tiếp, phân loại lỗi và trạng thái cuối được quản lý. Khi cần can thiệp, phải nhìn thấy đối tượng và đích nào chưa phản ánh trạng thái đúng.

### 8.2. Timeout không chứng minh thao tác chưa xảy ra

Connector gửi lệnh tạo User, đích tạo thành công nhưng phản hồi bị mất. Gửi lại một POST tạo mới có thể sinh tài khoản thứ hai nếu đích không có cơ chế chống trùng phù hợp.

Có thể dùng cơ chế idempotency được nhà cung cấp hỗ trợ hoặc khôi phục kết quả bằng correlation đã được xác minh. Nếu tìm lại bằng external ID, phải kiểm tra tenant, miền provisioning, quyền quản lý và tính duy nhất theo hợp đồng. Không tự nhận quản lý tài khoản bất kỳ có cùng email.

Với thao tác cập nhật, đọc lại đích có thể cho biết trạng thái mong muốn đã đạt hay chưa. Nhưng nếu request được đích xử lý bất đồng bộ, một lần GET ngay sau timeout chưa chắc phản ánh kết quả cuối; cần dùng hợp đồng theo dõi operation của đích.

### 8.3. Idempotency là hiệu ứng ổn định, không chỉ cùng payload

Một thao tác đặt `active=false` có thể hướng tới cùng trạng thái khi được thực hiện nhiều lần. Một thao tác “thêm một lý do cấp quyền mới” có thể tạo nhiều bản ghi nếu không có khóa chống trùng.

Thay thế toàn bộ một danh sách có vẻ lặp ổn định nhưng vẫn sai nếu ghi đè membership không thuộc connector. Vì vậy idempotency cần đồng thời xét đối tượng, phạm vi làm chủ, trạng thái hiện hành và tác dụng phụ.

Hệ thống phải biết một lần retry là cùng công việc hay một yêu cầu mới dựa trên intent đã thay đổi. Không dùng mã công việc mới cho mọi lần retry rồi làm mất khả năng nhận diện giao lại.

### 8.4. Một đối tượng lỗi không được làm mất các thay đổi sau

Có thể cô lập đối tượng lỗi để những đối tượng độc lập tiếp tục được xử lý. Tuy nhiên, những thay đổi của cùng đối tượng hoặc có phụ thuộc phải giữ đúng hợp đồng thứ tự.

Nếu một group chưa tồn tại, công việc thêm thành viên phải chờ hoặc được lập kế hoạch lại. Nếu một tài khoản đang cần vô hiệu hóa, không được coi lỗi cập nhật tên hiển thị là lý do bỏ quên việc thu hồi.

Một hàng đợi lỗi là nơi lưu công việc chưa xử lý được, không phải bằng chứng hoàn tất đồng bộ. Cần có người chịu trách nhiệm, cảnh báo và cơ chế xử lý lại có kiểm soát.

## 9. Thứ tự thay đổi, xung đột và đồng bộ hai chiều

### 9.1. Phân biệt version nguồn, version đích và revision của intent

Một thiết kế có thể có ba loại giá trị:

```text
+ Source version: định danh phiên bản theo hợp đồng nguồn
+ Target version/ETag: dùng cho kiểm tra cập nhật resource đích
+ Desired revision: phiên bản intent hiện hành do bộ điều phối quản lý
```

Ba loại không tự so sánh được với nhau. ETag không phải revision nguồn, còn một cookie của stream không nhất thiết là version có thể xếp hạng của từng User.

Nếu nguồn bảo đảm thứ tự trong một phạm vi cụ thể, connector có thể dùng bảo đảm đó để xây dựng trạng thái hiện hành. Với nguồn chỉ gửi thông báo thay đổi, cần đọc lại trạng thái theo hợp đồng thay vì lấy thời điểm nhận làm thứ tự nghiệp vụ.

### 9.2. Lệnh cũ không được mở lại quyền đã thu hồi

Giả sử công việc cũ muốn đặt active, còn trạng thái mong muốn mới đã chuyển sang inactive. Worker cần kiểm tra intent hiện hành trước khi gửi và quản lý cạnh tranh theo đối tượng.

Một hàng đợi tuần tự hoặc khóa theo đối tượng giúp giảm xung đột, nhưng khóa cục bộ không tự ngăn một request đã gửi bị đích xử lý muộn. Khi outcome chưa rõ, cần giải quyết operation đang dở theo khả năng đích rồi tiếp tục hội tụ về trạng thái mới.

Nếu hệ thống cần bảo đảm mạnh rằng lệnh cũ không thể ghi sau lệnh mới, cần cơ chế được đích thực thi, hoặc một ranh giới kiểm soát truy cập khác đáp ứng yêu cầu đó. Không tuyên bố có bảo đảm chỉ vì worker có một cột lock hoặc lease trong database nội bộ.

### 9.3. Xung đột thuộc tính phải theo thẩm quyền

Nếu directory nói active nhưng ứng dụng đang giữ security hold được quy trình bảo mật cho phép, connector không tự gỡ hold để hai phía giống nhau. Có thể cần mô hình hai điều kiện độc lập:

```text
Được phép sử dụng theo vòng đời nguồn
+ Không có hạn chế cục bộ áp dụng
+ Các điều kiện xác thực và phân quyền khác
```

Tương tự, thông tin người dùng tự sửa ở ứng dụng không tự được ghi ngược vào department nguồn có thẩm quyền. Đồng bộ là thực thi hợp đồng, không phải ép mọi field ở mọi nơi có cùng một giá trị bằng bất kỳ cách nào.

### 9.4. Tránh vòng lặp echo

Khi hai connector cùng quan sát thay đổi do nhau tạo, chúng có thể phát lặp hoặc liên tục đảo giá trị. Cần theo dõi provenance, field ownership, phiên bản và trạng thái đã áp dụng.

Một source tag có ích khi được hệ thống kiểm soát. Không tin tag tùy ý do caller gửi để cho phép bỏ qua kiểm tra quyền hoặc nhận diện thay đổi là an toàn.

Trước khi triển khai hai chiều, phải xác định field nào truyền chiều nào, nguồn nào thắng trong tình huống cụ thể và ngoại lệ nào phải chuyển cho chủ sở hữu dữ liệu xử lý.

## 10. Vòng đời tài khoản và membership

### 10.1. Joiner — chuẩn bị và kích hoạt đúng thời điểm

Một tài khoản mới có thể được tạo sớm để chuẩn bị, nhưng không nên có quyền sử dụng nghiệp vụ trước thời điểm hoặc điều kiện đã được phê duyệt. Mapping, credential setup và trạng thái provisioning cũng có thể có vòng đời riêng.

Một event đã nhận hôm nay nhưng có hiệu lực tuần sau cần được lưu như thay đổi theo lịch. Không mở tài khoản sớm chỉ vì connector có thể gửi nó ngay.

Nếu kế hoạch onboarding bị hủy, lịch cũ không được tiếp tục kích hoạt tài khoản khi tới hạn. Bộ điều phối phải kiểm tra intent và trạng thái hiện hành trước hành động.

### 10.2. Mover — cấp mới và thu hồi cũ

Khi chuyển phòng, connector có thể cần cập nhật department và membership suy ra. Nếu chỉ thêm nhóm mới mà không kết thúc lý do cấp nhóm cũ, quyền sẽ tích lũy theo thời gian.

Membership nên có provenance, chẳng hạn rule ID, assignment nguồn và khoảng hiệu lực. Nếu cùng quyền còn được cấp bởi một ngoại lệ hợp lệ, cần tính quyền hiệu lực từ các lý do còn lại theo mô hình đã chọn.

Không gỡ mọi membership của người dùng rồi thêm lại những gì connector nhìn thấy nếu nó không làm chủ toàn bộ tập đó. Các quyền thủ công hoặc từ nguồn khác phải được xử lý theo hợp đồng riêng.

### 10.3. Leaver — kết thúc khả năng truy cập

Nguồn xác nhận nghỉ việc có thể dẫn đến vô hiệu hóa tài khoản, kết thúc các quan hệ được quản lý và kích hoạt quy trình xử lý phiên, token hoặc credential liên quan. Những hành động cụ thể tùy loại hệ thống đích.

Không coi xóa đối tượng nguồn, đặt inactive và xóa vật lý dữ liệu đích là một thao tác có ý nghĩa giống nhau. Việc giữ hồ sơ để audit không có nghĩa tiếp tục cho phép truy cập.

Nếu một đích tạm không truy cập được, báo rõ rằng tài khoản tại đích đó chưa được xác minh đã vô hiệu hóa. Các ranh giới khác như khả năng phát hành phiên mới và quyền truy cập ở ứng dụng phải được xử lý theo quy trình thu hồi đã thiết kế.

### 10.4. Group cũng có định danh và phụ thuộc

Đổi tên nhóm không nhất thiết tạo một nhóm mới. Nhóm cùng tên ở hai tenant không tự tương đương; một nhóm quản trị ở nguồn cũng không tự được ánh xạ thành quyền quản trị đích.

Nếu có nested group, cần xác định đích hỗ trợ quan hệ lồng hay connector phải chuyển thành membership hiệu lực. Việc tính quan hệ cần xử lý phụ thuộc và chu trình theo mô hình của hệ thống, tránh mở rộng tập thành viên ngoài ý định.

Nhóm bị xóa hoặc ra khỏi scope cần được xử lý đối với những quan hệ mà connector làm chủ. Không tự xóa mọi group cùng tên được tìm thấy ở đích.

## 11. Bảo vệ connector và phạm vi dữ liệu

### 11.1. Quyền đọc nguồn và ghi đích phải vừa đủ

Credential connector có thể đọc thông tin tổ chức rộng và thay đổi khả năng truy cập của nhiều người. Cần giới hạn tenant, loại resource, thuộc tính và hành động theo trách nhiệm.

Tách quyền cấu hình connector khỏi quyền vận hành công việc thông thường khi phù hợp. Một thay đổi filter hoặc rule ánh xạ có thể tác động đến hàng nghìn tài khoản mà không trực tiếp sửa từng tài khoản.

Secret được quản lý, luân chuyển và truyền theo cơ chế bảo vệ của hệ thống. Không đặt raw token, mật khẩu connector hoặc URL continuation chứa trạng thái nhạy cảm vào log công khai.

### 11.2. Chỉ trao đổi dữ liệu cần thiết

Một ứng dụng tài liệu thường không cần mọi thuộc tính nhân sự. Projection hoặc attribute allowlist giúp giảm dữ liệu được sao chép và giảm nguy cơ một field không được quản lý vô tình tham gia policy.

Không đưa password plaintext hoặc verifier vào feed thuộc tính thông thường chỉ để các kho giống nhau. Nếu tổ chức có cơ chế đồng bộ hoặc di chuyển credential riêng, nó cần một thiết kế và phạm vi bảo vệ riêng, không được suy ra từ quyền đồng bộ hồ sơ.

Dữ liệu source cũng phải được kiểm tra schema, kích thước, kiểu và mapping. Nguồn đã xác thực không có nghĩa mọi giá trị đều phù hợp với policy của đích.

### 11.3. Continuation và callback không phải URL tùy ý

Khi giao thức trả continuation URL, connector cần xử lý theo endpoint và hợp đồng đã tin cậy, không nhận một URL bất kỳ từ client rồi dùng credential provisioning gọi đến đó.

Tương tự, payload webhook cần được xác minh theo cơ chế nguồn và được gắn đúng tenant/subscription. Một thông báo không đủ căn cứ không được tự tạo hoặc thu hồi tài khoản.

### 11.4. Thay đổi số lượng lớn cần được phát hiện

Nguồn đột ngột trả ít hơn phần lớn dữ liệu có thể là lỗi scope hoặc quyền. Hệ thống nên có kiểm tra bất thường trước các hành động thu hồi hàng loạt suy ra từ một lần quét.

Đây không phải lý do bỏ qua mọi event nghỉ việc hợp lệ trong lúc một full scan lỗi. Cần tách tín hiệu vòng đời có thẩm quyền khỏi suy luận hàng loạt dựa trên sự vắng mặt không đủ bằng chứng.

## 12. Mô hình công việc và thuật toán điều phối

### 12.1. Lưu trạng thái để có thể phục hồi

Một work item nội bộ có thể là:

```json
{
  "workId": "work-901-74",
  "tenantId": "tenant-a",
  "sourceObjectId": "source-user-901",
  "targetSystem": "document-app",
  "targetObjectId": "target-user-733",
  "desiredRevision": 74,
  "operationClass": "RECONCILE_MANAGED_STATE",
  "status": "PENDING",
  "attemptCount": 0,
  "lastErrorCode": null,
  "sourceEvidenceRef": "evidence-hr-184",
  "configVersion": "docs-sync-v3"
}
```

Các field là schema minh họa. Work item cần đủ dữ liệu hoặc tham chiếu bền vững để xử lý lại; một ID trỏ tới dữ liệu đã bị xóa khỏi cache không đáp ứng yêu cầu này.

Một chuỗi trạng thái có thể gồm đã capture, đã mapping, chờ áp dụng, đã gửi, chưa rõ outcome, đã áp dụng, đã xác minh hoặc cần can thiệp. Chỉ các trạng thái có ý nghĩa kết thúc theo hợp đồng mới được tính là hoàn tất.

### 12.2. Worker áp dụng một đối tượng

```text
+ Nhận công việc với quyền xử lý theo cơ chế điều phối
+ Tải mapping và intent hiện hành của đúng tenant/đối tượng
+ Nếu công việc không còn phản ánh intent hiện hành:
+     hợp nhất hoặc lập lại kế hoạch theo hợp đồng snapshot/delta
+ Đọc trạng thái và version cần thiết ở đích
+ Tính thay đổi chỉ trong các field/quan hệ được quản lý
+ Kiểm tra lại điều kiện gửi và xử lý operation đang dở nếu có
+ Gửi thao tác theo khả năng của đích
+ Nếu kết quả không rõ:
+     lưu trạng thái chưa biết và tiến hành xác minh
+ Nếu đã có kết quả xác định:
+     đọc lại hoặc lấy bằng chứng cuối theo hợp đồng đích
+ Ghi kết quả, bằng chứng và phần việc còn thiếu
```

Các dòng bắt đầu bằng dấu cộng chỉ biểu diễn những bước của pseudocode. Trong triển khai, trạng thái, khóa và mọi chuyển tiếp phải có bảo đảm phù hợp thay vì dựa vào việc worker chạy liên tục không lỗi.

Đánh dấu một công việc bị thay thế chỉ an toàn khi trạng thái mới thật sự bao phủ tác động cần thiết. Không vứt bỏ một delta thu hồi chỉ vì đã có một delta đổi tên với revision lớn hơn.

### 12.3. Replay sau sự cố

Khi chạy lại, hệ thống phải biết công việc nào đã gửi, công việc nào có outcome chưa rõ và công việc nào đã được đích xác minh. Replay từ một cursor cũ có thể được chấp nhận nếu correlation, deduplication và xử lý thứ tự đúng.

Nếu mất mapping hoặc trạng thái đồng bộ, cần một quy trình phục hồi baseline và đối soát. Không giải quyết bằng cách xóa sạch tài khoản đích rồi tạo lại: cách đó có thể phá lịch sử, quyền, ownership tài nguyên và liên kết người dùng.

Phục hồi từ backup cũng có thể đưa intent cũ hoặc công việc kích hoạt cũ trở lại hàng đợi. Cần đối chiếu trạng thái nguồn và quyết định vòng đời hiện hành trước khi cho các thao tác đó tiếp tục.

## 13. Đo lường và kiểm chứng đồng bộ

### 13.1. Theo dõi độ trễ ở nhiều điểm

Các chỉ số có thể gồm:

- Độ trễ từ thay đổi hiệu lực ở nguồn đến khi connector nhận được.
- Độ trễ từ capture bền vững đến khi công việc bắt đầu áp dụng.
- Độ trễ từ thay đổi nguồn đến khi trạng thái cần thiết ở đích được xác minh.
- Số công việc chờ, lỗi, chưa rõ outcome và cần can thiệp.
- Số mapping xung đột, đối tượng lệch và membership chưa thu hồi.
- Tuổi của checkpoint và lần đối soát đầy đủ gần nhất.

Mốc thời gian cần cùng ngữ nghĩa và có chất lượng đồng hồ phù hợp để tính độ trễ. `lastAttemptAt` mới không chứng minh đích vừa được đồng bộ thành công.

Đặc biệt cần nhìn độ trễ thu hồi và cấp quyền riêng. Một hệ thống tạo tài khoản nhanh nhưng để lại quyền cũ nhiều giờ vẫn có vấn đề về vòng đời truy cập.

### 13.2. Bằng chứng ở mức đối tượng

Một log có ích ghi tenant, nguồn, ID nguồn/đích, loại thay đổi, phiên bản cấu hình, trạng thái xử lý, mã lỗi và bằng chứng xác minh cần thiết. Không cần ghi toàn bộ hồ sơ, secret hoặc token nguồn.

Audit cần giải thích được vì sao một tài khoản bị đổi trạng thái hoặc một membership bị gỡ. Câu “đã chạy sync lúc 10 giờ” không đủ trả lời tài khoản cụ thể đã được xử lý ra sao.

### 13.3. Ma trận tự thực hành

| Tình huống | Kỳ vọng | Điều cần kiểm chứng |
| --- | --- | --- |
| Một đối tượng đổi username nhưng giữ ID nguồn | Giữ liên kết subject và tài khoản đích | Không tạo danh tính mới vì đổi tên |
| Hai tenant có cùng email | Không tự gộp | Scope và correlation |
| Trang giữa của baseline bị timeout | Không kết luận các đối tượng chưa đọc đã bị xóa | Tính đầy đủ của scan |
| Trang rỗng nhưng có continuation | Tiếp tục theo giao thức | Không suy trang rỗng là kết thúc |
| Quyền đọc connector bị giảm | Phát hiện thay đổi hoặc thiếu bằng chứng | Không thu hồi hàng loạt theo dữ liệu thiếu |
| Cookie/delta state không còn hợp lệ | Refresh theo hợp đồng nguồn | Khôi phục mà không phá tài khoản đích |
| Crash sau capture trước apply | Work item vẫn có thể được xử lý lại | Độ bền của hàng đợi công việc |
| Crash quanh bước lưu cursor | Không mất thay đổi đã đọc | Ranh giới commit và deduplication |
| Timeout sau request tạo User | Xác minh outcome trước khi tạo lại | Tránh tài khoản trùng |
| Request cũ muốn active sau intent suspend | Không được xem lệnh cũ là trạng thái mong muốn mới | Thứ tự và kiểm soát operation đang dở |
| Cập nhật đích bị xung đột version | Đọc lại và replan | Không ghi đè bản cũ |
| Mover chỉ thêm nhóm mới | Bị phát hiện còn quyền cũ | Vòng đời lý do cấp membership |
| Membership còn lý do cấp độc lập hợp lệ | Được xử lý theo hợp đồng hợp nhất quyền | Không xóa ngoài quyền làm chủ |
| API đích nhận inactive nhưng phiên vẫn dùng được | Chưa tuyên bố thu hồi toàn bộ khả năng truy cập | Tách trạng thái tài khoản và phiên |
| Một work item nằm trong hàng đợi lỗi | Báo còn việc chưa hoàn tất | Không coi lỗi đã được chuyển đi là thành công |

Các hàng trên là kỳ vọng thực hành, không phải báo cáo rằng connector hoặc hạ tầng cụ thể đã được chạy và kiểm thử trong bài này.

## 14. Tình huống hoàn chỉnh: chuyển phòng rồi nghỉ việc

An được quản lý từ nguồn tổ chức A, có mapping ổn định đến một tài khoản ở ứng dụng tài liệu. Connector làm chủ trạng thái vòng đời và các membership tài liệu được suy ra theo phòng ban.

Lúc chuyển từ Finance sang Risk, capture lưu thay đổi cùng công việc bền vững. Bộ điều phối tính lại quan hệ hiện hành, kết thúc lý do cấp nhóm Finance từ assignment cũ và tạo lý do cấp nhóm Risk theo policy. Một ngoại lệ bàn giao, nếu đã được duyệt, được giữ riêng với thời hạn của nó.

Một bản tin Finance cũ đến muộn không được dùng để lập lại intent Finance. Hệ thống kiểm tra hợp đồng version hoặc tải lại trạng thái có thẩm quyền trước khi áp dụng.

Sau đó nguồn xác nhận An nghỉ việc. Công việc vô hiệu hóa được capture nhưng đích tạm không hoạt động. Source checkpoint có thể đã tiến nếu toàn bộ công việc liên quan đã được lưu bền vững; trạng thái đích vẫn phải báo chờ, không được hiển thị đã hoàn tất thu hồi.

Khi đích phục hồi, connector xử lý operation theo trạng thái hiện hành, xác minh tài khoản đích đã inactive và kết thúc các quan hệ được quản lý. Quy trình thu hồi phiên hoặc token được thực hiện theo khả năng và chính sách của hệ thống liên quan, với bằng chứng riêng nếu cần.

Nếu full scan đồng thời bị lỗi đọc một trang, lỗi đó không được biến thành lệnh vô hiệu hóa những người khác chưa được đọc. Cũng không được dùng lỗi scan làm lý do bỏ qua tín hiệu nghỉ việc hợp lệ của An.

Tình huống cho thấy đồng bộ có hai trách nhiệm song song: không làm mất thay đổi cần áp dụng và không suy diễn một thay đổi nguy hiểm từ dữ liệu chưa đủ căn cứ. Trạng thái hoàn tất phải dựa trên hợp đồng cùng bằng chứng ở những đích liên quan.

## 15. Những điểm cần ghi nhớ

Directory synchronization duy trì trạng thái được quản lý giữa các hệ thống theo phạm vi và thẩm quyền đã định. Nó cần định danh ổn định, mapping bền vững và cách xử lý thay đổi có ý nghĩa vòng đời.

Full scan, delta và đối soát có vai trò khác nhau. Checkpoint nguồn, công việc đã capture và trạng thái đã xác minh ở đích phải được phân biệt; tiến một cursor không tự chứng minh quyền đã được cấp hoặc thu hồi đúng.

Retry, version, thứ tự và kiểm chứng outcome là một phần của thiết kế. Mọi quyết định tạo, cập nhật, vô hiệu hóa hoặc gỡ membership cần đúng đối tượng, đúng phạm vi làm chủ và đủ bằng chứng để giải thích khi có sự cố.
