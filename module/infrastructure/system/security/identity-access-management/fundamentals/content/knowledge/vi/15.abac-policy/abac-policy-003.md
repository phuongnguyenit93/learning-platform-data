# Resource attributes: thuộc tính tài nguyên trong ABAC

## 1. Vì sao cùng một người dùng lại nhận các quyết định khác nhau?

Lan là biên tập viên của một nền tảng học tập. Lan được sửa khóa học do mình phụ trách trong tenant A khi khóa học còn là bản nháp. Cùng tài khoản và phiên đăng nhập đó, Lan không được sửa khóa học của tenant B hoặc tự thay đổi một khóa học đã xuất bản.

Vai trò editor mô tả một phần khả năng của Lan. Để quyết định yêu cầu cụ thể, hệ thống còn cần biết:

```text
Khóa học thực tế thuộc tenant nào?
Ai là chủ sở hữu?
Trạng thái hiện tại là gì?
Nội dung có mức phân loại nào?
Đối tượng nào đang được yêu cầu truy cập?
```

Những dữ kiện mô tả đối tượng được bảo vệ là **resource attributes**, hay thuộc tính tài nguyên. Trong các tài liệu mô hình truy cập, chúng cũng có thể được gọi là thuộc tính của object.

NIST định nghĩa ABAC là cách xác định quyền thực hiện thao tác thông qua đánh giá thuộc tính của chủ thể, đối tượng, thao tác và có thể cả điều kiện môi trường theo chính sách. Thuộc tính tài nguyên là một nhóm dữ kiện của quyết định đó. [NIST SP 800-162: Guide to ABAC Definition and Considerations](https://www.nist.gov/publications/guide-attribute-based-access-control-abac-definition-and-considerations-0)

Trong module nền tảng IAM, resource attributes kết nối danh tính và quyền được cấp với đối tượng thật mà hệ thống đang bảo vệ. Chúng bổ sung cho RBAC, quan hệ phân công và các điều kiện xác thực; không tự thay thế việc thực thi phân quyền tại backend.

Sau bài học, người học có thể:

- Chọn các thuộc tính tài nguyên có ý nghĩa đối với policy.
- Thiết kế schema, kiểu dữ liệu và quy tắc xử lý thuộc tính thiếu.
- Phân biệt dữ kiện có thẩm quyền với giá trị client tự khai.
- Kiểm soát việc sửa thuộc tính có khả năng làm thay đổi quyền.
- Xử lý độ mới, kế thừa, bản sao và dữ liệu dẫn xuất.
- Kiểm chứng rằng policy sử dụng đúng tài nguyên và đúng phiên bản dữ kiện.

## 2. Thuộc tính tài nguyên nằm ở đâu trong quyết định?

### 2.1. Phân biệt bốn nhóm dữ kiện

| Nhóm | Mô tả | Ví dụ |
|---|---|---|
| Subject attributes | Dữ kiện về chủ thể đang yêu cầu | Danh tính, membership, trạng thái tài khoản |
| Resource attributes | Dữ kiện về đối tượng được bảo vệ | Tenant, owner, classification, trạng thái khóa học |
| Action | Hành động đang được thực hiện | `course.read`, `course.edit`, `course.publish` |
| Environment hoặc context | Dữ kiện về lần thực hiện yêu cầu | Thời điểm, bằng chứng xác thực, thông tin môi trường đã xác minh |

Một giá trị có tên giống nhau có thể xuất hiện ở nhiều nhóm nhưng mang nghĩa khác nhau:

```text
subject.tenantMemberships:
    người dùng có tư cách trong những tenant nào

resource.tenantId:
    tài nguyên thực tế thuộc tenant nào

request.requestedTenantId:
    client đang yêu cầu làm việc trong tenant nào
```

Ba dữ kiện này không thay thế lẫn nhau. Policy phải đối chiếu chúng theo mô hình tenant của ứng dụng.

### 2.2. Attribute là dữ kiện, policy là quy tắc

`ownerId=user-lan` là một thuộc tính. Nó không tự có nghĩa Lan được xóa, chia sẻ hoặc xuất bản tài nguyên.

Một chính sách có thể cho owner sửa bản nháp, nhưng yêu cầu một người có trách nhiệm khác xuất bản. Chính sách khác có thể chỉ coi owner là thông tin quản lý mà không cấp quyền riêng.

Tương tự, `classification=PUBLIC` không tự biến mọi endpoint thành công khai. Ứng dụng còn có thể yêu cầu tài nguyên đã xuất bản, visibility phù hợp hoặc một quyền truy cập cụ thể.

Cần tránh biến tên thuộc tính thành quy tắc ngầm nằm rải rác ở nhiều service.

### 2.3. Attribute không nhất thiết là một cột

Thuộc tính có thể được:

- Lưu trực tiếp trên bản ghi.
- Đọc từ dịch vụ sở hữu tài nguyên.
- Suy ra từ quan hệ đã được xác minh.
- Kế thừa từ container theo quy tắc chính sách.
- Tính toán từ dữ liệu khác bằng cơ chế được kiểm soát.

Điều quan trọng là ý nghĩa, nguồn và độ mới của kết quả. Việc dữ kiện được đóng gói thành JSON không tự làm nó đáng tin cậy.

## 3. Những thuộc tính thường có ích

| Thuộc tính minh họa | Câu hỏi được trả lời | Vai trò có thể có trong policy |
|---|---|---|
| `resourceId` | Đây là đối tượng nào? | Ràng buộc quyết định vào đúng tài nguyên |
| `resourceType` | Đối tượng thuộc loại nào? | Chọn action và schema thích hợp |
| `tenantId` | Tài nguyên thuộc miền tổ chức nào? | Kiểm soát truy cập xuyên tenant |
| `ownerId` | Ai được ghi nhận là chủ sở hữu? | Kết hợp với trách nhiệm và hành động cụ thể |
| `classification` | Nội dung thuộc mức phân loại nào? | Áp dụng điều kiện bảo vệ tương ứng |
| `state` | Đối tượng đang ở giai đoạn nào? | Giới hạn sửa, duyệt, xuất bản hoặc lưu trữ |
| `visibility` | Tài nguyên được chủ đích chia sẻ theo cách nào? | Phân biệt nội bộ, nhóm hoặc công khai |
| `parentId` | Tài nguyên thuộc container nào? | Xác minh quan hệ và quy tắc kế thừa |
| `audienceGroupIds` | Nhóm nào nằm trong tập người nhận dự kiến? | Kết hợp với membership đã xác minh |
| `version` | Dữ liệu đang ở phiên bản nào? | Phối hợp quyết định và thao tác cập nhật |

Không phải tài nguyên nào cũng cần mọi thuộc tính. Một tenant, một khóa học và một phiên đăng ký học có thể có schema khác nhau.

Không nên thu thập dữ liệu không cần thiết chỉ để policy “có thể dùng sau”. Thuộc tính càng nhiều, chi phí quản lý ý nghĩa, nguồn, độ mới và quyền truy cập càng lớn.

### 3.1. Danh tính tài nguyên cần ổn định và đủ phân biệt

Nếu ID chỉ duy nhất trong một tenant, danh tính logic có thể cần kết hợp:

```text
resourceType + tenantId + resourceId
```

Nếu hệ thống có ID duy nhất toàn cục, tenant vẫn có thể là thuộc tính bắt buộc của policy cho loại tài nguyên đó.

Không dựa vào tên hiển thị hoặc slug có thể đổi để thay thế định danh khi điều đó tạo nguy cơ trỏ nhầm đối tượng. Một quyết định cho phép đối với khóa học A không được áp dụng cho khóa học B chỉ vì hai đối tượng có cùng tiêu đề.

### 3.2. Thuộc tính nghiệp vụ và thuộc tính bảo mật có thể giao nhau

Tiêu đề khóa học có thể chỉ phục vụ giao diện. `tenantId` thường trực tiếp ảnh hưởng đến ranh giới quyền.

Một thuộc tính tưởng như nghiệp vụ, chẳng hạn `state`, lại có thể quyết định người dùng được sửa hay xuất bản. Khi policy bắt đầu dùng nó, các đường thay đổi thuộc tính đó trở thành một phần của cơ chế kiểm soát truy cập.

Vì vậy, cần quản lý danh mục các thuộc tính mà policy thật sự phụ thuộc, thay vì chỉ gắn nhãn “security metadata” cho một vài cột.

## 4. Thiết kế một schema rõ ràng

### 4.1. Snapshot tài nguyên minh họa

Ví dụ dưới đây mô tả dữ kiện khóa học mà ứng dụng có thể chuyển cho bộ đánh giá:

```json
{
  "resourceType": "Course",
  "resourceId": "course-a101",
  "tenantId": "tenant-a",
  "ownerId": "user-lan",
  "classification": "INTERNAL",
  "state": "DRAFT",
  "visibility": "TENANT",
  "audienceGroupIds": ["content-team-a"],
  "version": 17
}
```

Đây là mô hình dữ liệu minh họa, không phải request được phép nhận nguyên xi từ client và coi là sự thật.

Metadata phục vụ vận hành như nguồn cung cấp, thời điểm đọc hoặc phiên bản schema có thể được giữ cùng snapshot. Chúng có thể giúp kiểm tra nguồn và giải thích quyết định, nhưng không tự tạo bảo đảm độ mới nếu không có cơ chế cập nhật tương ứng.

### 4.2. Mỗi thuộc tính cần một hợp đồng

| Thuộc tính | Kiểu và miền giá trị minh họa | Nguồn có thẩm quyền |
|---|---|---|
| `resourceType` | Một loại tài nguyên được hệ thống nhận diện | Dịch vụ ứng dụng và định tuyến nội bộ |
| `tenantId` | Định danh tenant hợp lệ, bắt buộc với Course | Dữ liệu sở hữu khóa học |
| `ownerId` | Định danh chủ sở hữu theo quy tắc vòng đời | Quy trình gán hoặc chuyển sở hữu |
| `classification` | PUBLIC, INTERNAL hoặc CONFIDENTIAL | Quy trình phân loại được cấp quyền |
| `state` | Giá trị trạng thái được hỗ trợ | Máy trạng thái nghiệp vụ |
| `visibility` | Chế độ chia sẻ được định nghĩa | Quy trình chia sẻ có kiểm soát |
| `audienceGroupIds` | Tập định danh nhóm | Cấu hình chia sẻ được xác minh |
| `version` | Giá trị phiên bản theo hợp đồng kho dữ liệu | Dịch vụ lưu trữ tài nguyên |

Các giá trị trong bảng thuộc ví dụ của bài. Không có một danh sách classification hoặc state chung cho mọi hệ thống ABAC.

Hợp đồng còn cần xác định thuộc tính nào bắt buộc, thuộc tính nào có thể không tồn tại, ai được sửa và quy tắc chuẩn hóa.

### 4.3. Không so sánh mức phân loại bằng thứ tự chuỗi

Cách kiểm tra như sau không có ý nghĩa bảo mật nếu thứ tự chưa được định nghĩa:

```text
subject.clearance >= resource.classification
```

Nếu hai trường là chuỗi, thứ tự từ điển của PUBLIC, INTERNAL và CONFIDENTIAL không thể thay cho quan hệ được phép truy cập.

Ngay cả khi mã hóa bằng số, policy vẫn cần xác định ý nghĩa của thứ tự. Một số mô hình có thêm nhóm chuyên môn hoặc compartment nên không thể chỉ dùng một mức cao thấp.

Trong ví dụ nền tảng học tập, ứng dụng dùng một hàm chính sách được định nghĩa rõ cho từng classification, thay vì suy từ tên.

### 4.4. Schema hỗ trợ đúng kiểu, không chứng minh nguồn đáng tin

Cedar là một ví dụ công cụ cho phép khai báo kiểu entity cùng tên, kiểu và tính tùy chọn của attribute để hỗ trợ validation policy. Tài liệu cũng phân biệt cách xử lý thuộc tính tùy chọn và lỗi khi truy cập thuộc tính không tồn tại. [Cedar schema overview](https://docs.cedarpolicy.com/schema/schema.html)

Schema có thể phát hiện việc dùng số ở nơi cần chuỗi hoặc tham chiếu sai thuộc tính. Nó không chứng minh rằng `tenantId` do một bên cung cấp thật sự là tenant của tài nguyên.

Ứng dụng vẫn cần kiểm tra dữ liệu nhận từ các nguồn và sử dụng đúng cơ chế validation của công cụ được triển khai.

## 5. Nguồn dữ liệu và ranh giới tin cậy

### 5.1. Định danh trong request chỉ là đầu vào tra cứu

Client có thể yêu cầu:

```http
PATCH /tenants/tenant-a/courses/course-a101
Content-Type: application/json

{
  "title": "Nội dung mới",
  "tenantId": "tenant-b",
  "ownerId": "user-lan",
  "classification": "PUBLIC"
}
```

Route và body biểu đạt điều client muốn làm. Chúng không chứng minh các thuộc tính hiện tại của khóa học.

Trong thiết kế của bài, backend tải metadata có thẩm quyền của `course-a101`, xác minh nó thuộc tenant được yêu cầu và kiểm tra quyền đối với hành vi thật sự được thực hiện.

Một endpoint sửa tiêu đề không được âm thầm nhận các trường làm đổi tenant, owner hoặc classification chỉ vì chúng xuất hiện trong JSON.

### 5.2. Không thay thế dữ kiện đã lưu bằng payload

Một lỗi phổ biến là dựng resource cho policy bằng cách trộn body lên entity:

```text
resourceForAuthorization = storedResource + clientPayload
```

Nếu client đưa `ownerId` của chính mình vào payload rồi policy kiểm tra owner, yêu cầu có thể được cho phép nhờ thuộc tính chưa từng tồn tại trên tài nguyên.

Phải phân biệt:

```text
currentResource:
    sự thật hiện tại dùng để kiểm tra quyền đối với tài nguyên

proposedChanges:
    tập thay đổi mà chủ thể đang đề nghị

resultingResource:
    trạng thái kết quả chỉ được chấp nhận nếu mọi kiểm tra cần thiết đều đạt
```

Một số hành động cần đánh giá cả trạng thái hiện tại lẫn trạng thái đề xuất. Điều đó không có nghĩa trạng thái đề xuất được quyền thay thế bằng chứng hiện tại.

### 5.3. Quản lý thuộc tính là một trách nhiệm có thẩm quyền

NIST SP 800-205 nhấn mạnh thuộc tính cần được thiết lập, phát hành, lưu trữ và quản lý dưới một thẩm quyền, với cơ chế cập nhật và thu hồi thích hợp. [Attribute Considerations for Access Control Systems](https://www.nist.gov/publications/attribute-considerations-access-control-systems)

Với mỗi thuộc tính nhạy cảm, nhóm triển khai nên biết dịch vụ nào sở hữu, ai có thể thay đổi, thay đổi được kiểm toán ở đâu và các bên sử dụng nhận phiên bản mới như thế nào.

Một nhãn do dịch vụ nội bộ gửi vẫn cần hợp đồng nguồn và kiểm soát đường ghi. “Nội bộ” không tự có nghĩa mọi dữ kiện đều đúng hoặc mọi caller đều được sửa thuộc tính bảo mật.

## 6. Thiếu, null, rỗng và không hợp lệ là các trường hợp khác nhau

### 6.1. Đừng làm mất nguyên nhân thiếu dữ kiện

| Trường hợp | Ví dụ | Ý nghĩa cần xác định |
|---|---|---|
| Thuộc tính không có trong dữ liệu | Không có khóa `classification` | Schema cho phép thiếu hay dữ liệu bị lỗi? |
| Null được khai báo rõ | `ownerId: null` | Tài nguyên chưa có owner theo quy trình hay chưa xác định? |
| Chuỗi rỗng | `tenantId: ""` | Thường không phải tenant hợp lệ trong ví dụ |
| Tập rỗng | `audienceGroupIds: []` | Có thể có nghĩa không chia sẻ với nhóm nào |
| Giá trị lạ | `classification: "UNKNOWN_NEW"` | Chưa được schema và policy hiện tại hỗ trợ |
| Sai kiểu | `tenantId: 123` | Không phù hợp hợp đồng định danh |
| Lỗi nguồn dữ liệu | Dịch vụ thuộc tính timeout | Chưa đọc được sự thật, khác với một tập rỗng có chủ đích |

Nếu nguồn dữ liệu lỗi nhưng ứng dụng thay bằng `[]`, một điều kiện phủ định có thể hiểu sai rằng tài nguyên không có nhóm hạn chế.

Tương tự, không nên đổi mọi giá trị không biết thành PUBLIC. Việc “không đọc được mức phân loại” không chứng minh nội dung đã được xác nhận công khai.

### 6.2. Điều kiện phủ định dễ cho lọt giá trị lạ

Ví dụ:

```text
allowRead nếu resource.classification != "CONFIDENTIAL"
```

Điều kiện này có thể cho phép một giá trị mới, sai chính tả hoặc không được nhận diện, tùy cách engine xử lý kiểu và dữ liệu thiếu.

Một quy tắc rõ hơn cho nhánh chỉ hỗ trợ nội dung thông thường là:

```text
resource.classification phải tồn tại
AND có đúng kiểu
AND thuộc tập {"PUBLIC", "INTERNAL"}
AND thỏa mọi điều kiện đọc khác của nhánh đó
```

Nội dung CONFIDENTIAL được xử lý bằng policy riêng. Giá trị mới cần được bổ sung có chủ đích vào schema và quy tắc, thay vì vô tình được hưởng quyền qua phép so sánh khác nhau.

### 6.3. Không giả định mọi engine đều tự từ chối khi có lỗi

Một lỗi đọc attribute có thể làm một rule thất bại, nhưng engine còn có quy tắc kết hợp nhiều policy. Không nên giả định một rule lỗi sẽ luôn biến toàn bộ quyết định thành deny.

Ứng dụng cần hợp đồng rõ ràng: với những thuộc tính bắt buộc cho hành động này, dữ liệu không hợp lệ hoặc không có nguồn xác minh không được trở thành căn cứ cho phép.

Có thể thực hiện kiểm tra snapshot đầu vào trước khi đánh giá, phân biệt kết quả lỗi với không khớp rule, và xử lý kết quả theo cơ chế của engine cụ thể.

### 6.4. Thuộc tính tùy chọn vẫn cần ý nghĩa

Nếu `ownerId` có thể null đối với khóa học đang chờ phân công, policy owner không được khớp với một principal không xác định hoặc bỏ qua hoàn toàn điều kiện owner.

Nếu `audienceGroupIds` là tập rỗng, policy phải xác định đó là không chia sẻ qua nhóm, không phải chia sẻ với tất cả.

Sự vắng mặt có thể là một trạng thái hợp lệ, nhưng ý nghĩa đó phải nằm trong hợp đồng, không được suy ra bằng các giá trị mặc định tiện lợi trong code.

## 7. Ví dụ quyết định dựa trên resource attributes

### 7.1. Chính sách chỉnh sửa minh họa

Trong ví dụ nền tảng học tập, người dùng chỉ được sửa bản nháp thuộc sở hữu của mình khi:

```text
principal đang hoạt động
AND có membership hợp lệ trong tenant của khóa học
AND có grant course.edit bao gồm tài nguyên này
AND resource.resourceType = Course
AND resource.state = DRAFT
AND resource.ownerId = principal.id
AND yêu cầu classification được đáp ứng
```

Quy tắc cố ý kết hợp role hoặc grant với thuộc tính tài nguyên. Owner không tự được sửa nếu không có grant; người có grant cũng không tự được sửa bản nháp của người khác theo chính sách này.

Một tổ chức có thể cho editor được phân công sửa thay owner. Khi đó cần một căn cứ quan hệ hoặc policy tương ứng, không nên âm thầm bỏ điều kiện owner trong mọi trường hợp.

### 7.2. Pseudocode đánh giá

```text
canEditOwnDraft(principal, resource, facts):
    nếu snapshot tài nguyên không hợp lệ:
        trả kết quả không thể cho phép kèm nguyên nhân phù hợp

    nếu principal không hoạt động:
        trả DENY

    nếu resource.resourceType != Course:
        trả DENY

    nếu membership có thẩm quyền không bao gồm resource.tenantId:
        trả DENY

    nếu không có grant course.edit còn hiệu lực
       với scope bao gồm chính resource này:
        trả DENY

    nếu resource.state != DRAFT:
        trả DENY

    nếu resource.ownerId không xác định
       hoặc resource.ownerId != principal.id:
        trả DENY

    nếu không có căn cứ đáp ứng policy classification:
        trả DENY

    trả ALLOW gắn với danh tính và phiên bản tài nguyên đã đánh giá
```

Đây là pseudocode cho quy tắc minh họa, không phải cú pháp của một sản phẩm hay một engine tổng quát.

Hàm kiểm tra classification cần sử dụng các giá trị được nhận diện cùng dữ kiện chủ thể đáng tin cậy. Nó không được dùng nội dung `clearance` hoặc `classification` do client tự khai để bỏ qua điều kiện.

### 7.3. Đọc, sửa và xuất bản có thể dùng các attribute khác nhau

| Action | Những thuộc tính có thể liên quan | Điều không nên suy ra |
|---|---|---|
| `course.read` | Tenant, visibility, classification, audience | Được đọc thì được xuất toàn bộ dữ liệu |
| `course.edit` | Tenant, owner hoặc phân công, state | Là owner thì được đổi tenant |
| `course.publish` | Tenant, state, kết quả duyệt, người gửi duyệt | State hợp lệ thì mọi principal đều được xuất bản |
| `course.transferOwnership` | Owner hiện tại, tenant, chủ thể đích | Được sửa nội dung thì được chuyển owner |
| `course.reclassify` | Classification hiện tại và đề xuất | Được đọc nội dung mật thì được hạ phân loại |

Không cần gửi mọi thuộc tính của tài nguyên cho mọi quyết định. Cần đủ dữ kiện cho action đang xử lý, có schema và quy tắc rõ ràng.

### 7.4. MFA và SSO không biến thành thuộc tính tài nguyên

MFA thành công là bằng chứng liên quan lần xác thực hoặc phiên của chủ thể. Nó có thể là điều kiện bổ sung cho thao tác thay đổi classification, nhưng không làm khóa học đổi tenant hoặc owner.

Một claim role từ SSO cũng không chứng minh thuộc tính mới nhất của khóa học. Những dữ kiện về tài nguyên thường phải được giải quyết tại ứng dụng hoặc dịch vụ quản lý tài nguyên theo hợp đồng đã định.

## 8. Sửa thuộc tính có thể là sửa quyền

### 8.1. Phân biệt chỉnh nội dung với quản trị metadata bảo mật

Các thay đổi sau có thể trực tiếp làm thay đổi tập chủ thể được truy cập:

```text
tenantId
ownerId
classification
visibility
audienceGroupIds
parentId
```

Nếu endpoint sửa tiêu đề bind toàn bộ payload vào entity, người dùng có thể thay owner hoặc visibility ngoài ý định của chức năng.

Thiết kế có thể sử dụng command riêng, whitelist field hoặc một bộ phân tích thay đổi có kiểm tra quyền đầy đủ. Điều cần bảo đảm là tác động thực tế được kiểm tra, không chỉ tên endpoint.

### 8.2. Chuyển owner

Một thao tác chuyển sở hữu cần đánh giá quyền trên trạng thái hiện tại trước khi cập nhật.

Máy chủ còn có thể cần xác minh owner mới tồn tại, thuộc tenant phù hợp, có tư cách nhận tài nguyên và đáp ứng những yêu cầu nghiệp vụ đã đặt ra.

Không kiểm tra quyền chuyển owner bằng cách trước tiên thay `ownerId` thành người gọi rồi áp dụng policy owner. Đó là dùng kết quả chưa được chấp nhận làm căn cứ cho chính hành động cần kiểm soát.

### 8.3. Chuyển tenant

Đổi tenant có thể ảnh hưởng binding, nhóm chia sẻ, container cha, dữ liệu con và các bản sao.

Một thao tác như vậy thường cần một quy trình chuyển tài nguyên rõ ràng: quyền đưa tài nguyên ra khỏi phạm vi nguồn, quyền đưa vào phạm vi đích và quy tắc xử lý các quan hệ liên quan.

Không coi đổi `tenantId` là cập nhật một chuỗi thông thường. Nếu chính sách quy định tenant bất biến cho loại tài nguyên đó, các endpoint thông thường phải từ chối thay đổi và quy trình quản trị cần tuân thủ mô hình riêng.

### 8.4. Hạ phân loại hoặc mở visibility

Giả sử chỉ người có điều kiện đặc biệt mới được đọc tài liệu CONFIDENTIAL. Nếu một người có quyền sửa tiêu đề đồng thời được tự hạ classification xuống PUBLIC, người đó có thể làm thay đổi ranh giới truy cập.

Cần có quyền phù hợp cho hành vi thay đổi và kiểm tra điều kiện trên cả giá trị hiện tại lẫn giá trị đề xuất. Theo chính sách cụ thể, có thể cần phê duyệt hoặc xác minh nội dung trước khi công bố.

Xóa nhãn classification cũng có thể là hành động nhạy cảm nếu việc thiếu nhãn làm thay đổi policy. Không chỉ bảo vệ thao tác đặt giá trị mà bỏ ngỏ đường xóa.

### 8.5. Tạo tài nguyên mới

Khi chưa có bản ghi, quyền tạo được xét trong phạm vi chứa như tenant hoặc thư mục.

Backend chọn tenant và các giá trị được kiểm soát từ ngữ cảnh đã xác minh hoặc từ yêu cầu tạo đã được cấp quyền tương ứng. Không nhận owner, classification hoặc parent tùy ý mà không xác minh.

Giá trị mặc định phải có ý nghĩa bảo vệ rõ ràng. Nếu một tài nguyên cần phân loại trước khi sử dụng, trạng thái chờ phân loại có thể được thiết kế để chưa được chia sẻ, thay vì tự coi là PUBLIC.

## 9. Tài nguyên phân cấp và attribute kế thừa

### 9.1. Không phải mọi thuộc tính đều có cùng phép kế thừa

Giả sử bài học thuộc khóa học, còn khóa học thuộc tenant:

```text
tenant-a
    -> course-a101
        -> lesson-a101-01
```

Những câu hỏi cần trả lời gồm:

- Tenant của bài học được lưu trực tiếp hay suy ra từ khóa học?
- Classification ở khóa học có đặt giới hạn cho mọi bài học không?
- Owner của khóa học có tự là owner của tài liệu đính kèm không?
- Visibility của bài học có được rộng hơn visibility của khóa học không?
- Di chuyển một bài học sang khóa học khác có làm thay đổi quyền không?

Không dùng một phép “child ghi đè parent” cho tất cả attribute nếu chưa xác định chính sách.

### 9.2. Ví dụ quy tắc phân loại hiệu lực

Trong một chính sách giả định chỉ có một chuỗi mức phân loại đã định nghĩa, ứng dụng có thể quy định:

```text
Nếu một ancestor bắt buộc bảo vệ CONFIDENTIAL,
đối tượng con không được hạ mức bảo vệ bằng nhãn PUBLIC.
```

Đó là quy tắc của hệ thống minh họa, không phải tính chất tự nhiên của ABAC.

Có thể lưu classification trực tiếp và tính classification hiệu lực từ cả đường container. Khi làm vậy, cần xác minh quan hệ cha con, namespace, vòng đời và phiên bản dữ liệu được sử dụng.

Không chỉ tin `parentId` do client gửi để nhận các thuộc tính có lợi của một container khác.

### 9.3. Di chuyển container là thay đổi bảo mật

Chuyển một tài liệu từ thư mục nội bộ sang thư mục công khai có thể thay đổi người được truy cập, dù bản thân tài liệu không đổi nội dung.

Quyền move cần kiểm tra phạm vi nguồn và đích theo policy. Các thuộc tính hiệu lực, chỉ mục tìm kiếm và cache phải được cập nhật hoặc xử lý theo cơ chế nhất quán đã thiết kế.

Nếu dữ liệu con lưu bản sao thuộc tính của parent, việc đổi parent có thể cần cập nhật nhiều đối tượng. Phải xác định trong thời gian chuyển tiếp bên nào có thẩm quyền, thay vì để các service tự chọn giá trị khác nhau.

## 10. Độ mới và khoảng cách giữa kiểm tra với sử dụng

### 10.1. Quyết định phải gắn với dữ kiện đã đọc

Xét diễn tiến:

```text
T1: resource thuộc tenant-a, owner=user-lan, state=DRAFT, version=17.
T2: một thao tác hợp lệ chuyển trạng thái hoặc owner.
T3: yêu cầu cũ ghi nội dung dựa trên snapshot ở T1.
```

Một policy đúng trên snapshot cũ vẫn có thể tạo tác động sai nếu hệ thống không kiểm soát thay đổi đồng thời.

Với thao tác ghi, có thể dùng khóa phù hợp, kiểm tra phiên bản, điều kiện cập nhật hoặc giao thức phối hợp khác. Lựa chọn phụ thuộc yêu cầu nhất quán và nơi dữ kiện được quản lý.

### 10.2. Ví dụ cập nhật có điều kiện

Sau khi quyết định cho phép sửa bản nháp trên snapshot version 17, ứng dụng có thể sử dụng một cập nhật có điều kiện như:

```sql
UPDATE course
SET content = :new_content,
    version = version + 1
WHERE id = :course_id
  AND tenant_id = :authorized_tenant_id
  AND state = 'DRAFT'
  AND version = :authorized_resource_version;
```

Đây là SQL minh họa cho một kho dữ liệu có cơ chế version tương ứng. Các tham số phải được bind; điều kiện quyền đầy đủ vẫn được đánh giá trước đó.

Nếu không có bản ghi nào được cập nhật, ứng dụng không được bỏ điều kiện version rồi thử ghi lại. Cần xử lý xung đột theo hợp đồng, tải dữ kiện mới và đánh giá lại nếu muốn thực hiện một lần thử mới.

Điều kiện version chỉ bảo vệ các thuộc tính có thay đổi được phản ánh trong version đó. Nó không tự phát hiện việc grant bị thu hồi ở một dịch vụ khác hoặc thuộc tính bên ngoài thay đổi mà version bản ghi không tăng.

### 10.3. Cache thuộc tính cần nhận diện đúng đối tượng

Một cache key chỉ dùng `resourceId` có thể sai nếu ID chỉ duy nhất trong tenant. Cần có đủ thành phần phân biệt theo mô hình định danh của hệ thống.

Cache còn cần phiên bản, thời hạn hoặc cơ chế vô hiệu hóa phù hợp với attribute đang dùng. Việc thay đổi classification, tenant hoặc parent có thể yêu cầu vô hiệu hóa cả dữ liệu suy ra.

TTL ngắn chỉ giới hạn một phần thời gian dữ kiện cũ được chấp nhận. Nó không tự bảo đảm một thao tác thu hồi hoặc hạ quyền có hiệu lực tức thì.

### 10.4. Nhiều nguồn thuộc tính

Nếu tenant nằm trong cơ sở dữ liệu khóa học, classification ở một catalog và quan hệ chia sẻ ở dịch vụ khác, một snapshot quyết định có thể chứa dữ liệu đọc ở những thời điểm khác nhau.

Cần xác định mức nhất quán cho phép, thuộc tính nào phải có phiên bản hoặc bằng chứng độ mới, và hành vi khi nguồn bắt buộc không khả dụng.

Đối với thao tác rủi ro cao, chấp nhận dữ liệu cũ cần là quyết định chính sách rõ ràng. Không âm thầm dùng bản sao cũ nhất chỉ để mọi yêu cầu tiếp tục được cho phép.

## 11. Danh sách, bản sao và dữ liệu dẫn xuất

### 11.1. Mỗi dòng có thể có thuộc tính khác nhau

Một API danh sách có thể trả nhiều khóa học với tenant, owner hoặc classification khác nhau.

Không kiểm tra quyền trên khóa học đầu tiên rồi dùng kết quả cho mọi bản ghi. Cần xây dựng tập tài nguyên được phép theo policy và áp dụng việc phân trang, tính tổng, mở rộng quan hệ theo hợp đồng không làm lộ dữ liệu ngoài phạm vi.

Ví dụ, người dùng chỉ được đọc khóa học của tenant A không nên nhận tổng số khóa học mật của tenant B qua trường `totalCount`.

Có thể dịch một phần điều kiện sang truy vấn dữ liệu hoặc dùng cơ chế lọc phù hợp khác. Cần bảo đảm bộ lọc phản ánh đúng policy, không bỏ điều kiện classification hoặc quan hệ chỉ vì tầng truy vấn chưa có dữ kiện đó.

### 11.2. Thuộc tính của một đối tượng không bao phủ mọi trường

Một hồ sơ đăng ký học có thể chứa tên học viên, email, điểm, ghi chú hỗ trợ và thông tin nội bộ.

Cho phép đọc bản ghi không nhất thiết đồng nghĩa cho phép mọi trường. Có thể cần projection theo action hoặc một quyết định riêng cho dữ liệu nhạy cảm hơn.

Khi một phần dữ liệu được tách thành tài nguyên độc lập, tài nguyên mới cũng cần định danh, nguồn thuộc tính và policy tương ứng. Việc di chuyển field sang một endpoint khác không tự thay đổi quyền.

### 11.3. File xuất là một tài nguyên mới cần được quản lý

Một báo cáo CSV lấy dữ liệu từ nhiều khóa học có thể chứa thông tin nhạy cảm hơn mô tả của một khóa học riêng lẻ.

Cần xác định cho file kết quả:

```text
định danh và tenant
dữ liệu nguồn và phạm vi đã được phép xuất
classification hoặc quy tắc bảo vệ phù hợp
người nhận và quyền tải
thời hạn lưu hoặc khả năng truy cập theo chính sách
nguồn gốc và phiên bản cần thiết để truy vết
```

Không tự gắn PUBLIC cho file chỉ vì job kỹ thuật tạo ra nó hoặc vì nó được lưu trong một bucket khác.

API tạo báo cáo và điểm tải file là hai đường truy cập cần được bảo vệ. Nếu dùng URL có chữ ký, phải xem xét đúng quyền truy cập mà URL đó trao cùng thời hạn và khả năng vô hiệu hóa của cơ chế đang sử dụng.

### 11.4. Dữ liệu dẫn xuất không có một phép phân loại tự động chung

Một file tổng hợp từ nhiều nguồn cần một policy xác định cách kết hợp giới hạn. Không phải mọi trường hợp đều chỉ lấy giá trị phân loại cao nhất hoặc kế thừa nhãn của bản ghi đầu tiên.

Kết quả thống kê đã tổng hợp vẫn có thể tiết lộ thông tin, nhất là với nhóm nhỏ. Ngược lại, một quy trình biến đổi được kiểm soát có thể tạo ra sản phẩm có cách chia sẻ khác dữ liệu nguồn.

Quy tắc cho phép thay đổi mức bảo vệ phải được xác định và kiểm chứng; không suy ra từ việc dữ liệu đã được đổi định dạng, nén hoặc mã hóa.

### 11.5. Copy và restore cũng là đường ghi thuộc tính

Sao chép khóa học có thể cần chọn owner mới, tenant đích và tập chia sẻ mới. Không giữ nguyên mọi thuộc tính của nguồn một cách máy móc, nhưng cũng không được bỏ các giới hạn cần bảo toàn.

Khôi phục từ backup có thể đưa metadata bảo mật về trạng thái cũ. Quy trình restore phải xác định cách hòa giải với các thay đổi quyền, owner hoặc classification đã xảy ra sau thời điểm backup.

Các job import và đồng bộ có quyền ghi metadata vì thế cũng nằm trong phạm vi quản trị IAM, không chỉ là thao tác dữ liệu phụ trợ.

## 12. Quan sát và bảo vệ chính metadata phân quyền

### 12.1. Attribute có thể là dữ liệu nhạy cảm

Owner, tập nhóm được chia sẻ, classification và quan hệ container có thể làm lộ cấu trúc tổ chức hoặc sự tồn tại của nội dung mật.

Một endpoint “xem attributes” cần có quyền truy cập riêng phù hợp. Không nên trả toàn bộ snapshot dùng cho policy cho người gọi chỉ để giải thích vì sao bị từ chối.

Tương tự, dịch vụ cung cấp thuộc tính cần được xác thực và giới hạn quyền đọc, ghi. Có thể cho bộ đánh giá đọc metadata tối thiểu phục vụ quyết định mà không trao cho caller khả năng đọc toàn bộ nội dung tài nguyên.

### 12.2. Ghi nhận đủ để truy vết

Một bản ghi minh họa có thể là:

```json
{
  "event": "authorization_decision",
  "requestId": "req-example",
  "action": "course.edit",
  "resourceType": "Course",
  "resourceId": "course-a101",
  "resourceVersion": 17,
  "attributeSchemaVersion": "course-authz-v1",
  "policyVersion": "policy-example",
  "decision": "DENY",
  "reasonCode": "RESOURCE_STATE_NOT_EDITABLE"
}
```

Schema này chỉ phục vụ ví dụ. Có thể cần ghi thêm principal, tenant và nguồn dữ kiện với mức chi tiết phù hợp.

Không mặc định ghi toàn bộ snapshot, audience, nội dung tài nguyên hoặc thông tin cá nhân vào log. Token, cookie và credential không phải bằng chứng cần sao chép vào nhật ký quyết định.

Một mã tham chiếu nguồn, phiên bản và dấu thời gian có thể hữu ích hơn việc lưu mọi giá trị, nhưng phải phù hợp nhu cầu điều tra và khả năng truy xuất lại.

### 12.3. Phân biệt lỗi dữ liệu với từ chối hợp lệ

Các lý do như:

```text
OWNER_MISMATCH
RESOURCE_TENANT_MISMATCH
ATTRIBUTE_SOURCE_UNAVAILABLE
UNSUPPORTED_CLASSIFICATION
STALE_RESOURCE_VERSION
```

giúp nhóm vận hành phân biệt sự cố nguồn dữ liệu với hành vi bị policy từ chối.

Thông tin chẩn đoán nội bộ không nhất thiết được công khai cho client. Phản hồi bên ngoài cần tuân thủ hợp đồng API và tránh tiết lộ tài nguyên mà người gọi không được biết.

Cần theo dõi tỷ lệ thuộc tính thiếu, giá trị lạ, lỗi nguồn và việc cập nhật metadata bị từ chối. Những tín hiệu này hỗ trợ phát hiện một bản import sai schema hoặc một đường ghi đang làm hỏng dữ kiện quyền.

## 13. Thay đổi schema và vòng đời thuộc tính

### 13.1. Đổi schema có thể đổi quyết định truy cập

Giả sử policy cũ hiểu classification gồm ba giá trị, nhưng dịch vụ dữ liệu bắt đầu phát hành một giá trị mới.

Nếu một nhánh dùng điều kiện “khác CONFIDENTIAL”, giá trị mới có thể vô tình được cho phép. Nếu policy dùng tập giá trị nhận diện, nó có thể từ chối cho đến khi được cập nhật.

Cần xác định hành vi tương thích cho engine, schema và nguồn dữ liệu trước khi mở rộng miền giá trị. Không chọn mặc định rộng chỉ để tránh lỗi hiển thị.

Đổi tên `tenantId`, đổi kiểu ID hoặc thay ý nghĩa `ownerId` cũng là thay đổi hợp đồng bảo mật, không chỉ refactor dữ liệu.

### 13.2. Đưa một thuộc tính mới vào sử dụng

Một quy trình thiết kế có thể gồm:

1. Định nghĩa ý nghĩa, miền giá trị và owner dữ liệu.
2. Xác định quyền ghi và các đường tạo, import, copy, restore.
3. Chuẩn bị dữ liệu cho các tài nguyên đã tồn tại.
4. Kiểm tra schema, nguồn và các policy bị ảnh hưởng.
5. Thử các quyết định đại diện, bao gồm dữ liệu thiếu và lỗi nguồn.
6. Kích hoạt ràng buộc theo phạm vi đã xác định.
7. Theo dõi lỗi, độ mới và khả năng giải thích quyết định.

Trong giai đoạn chuyển tiếp, tài nguyên chưa có thuộc tính phải được xử lý theo quy tắc rõ ràng. Không âm thầm cho qua chỉ vì dữ liệu backfill chưa hoàn tất.

### 13.3. Thuộc tính không còn dùng cũng cần được quản lý

Một attribute không còn xuất hiện trong policy chính vẫn có thể được ứng dụng cũ, job hoặc bộ lọc tìm kiếm sử dụng.

Trước khi ngừng phát hành hoặc đổi nguồn, cần xác minh các consumer và cách xử lý tương thích. Để hai nguồn cùng phát hành giá trị mâu thuẫn mà không quy định nguồn có thẩm quyền có thể tạo quyết định khác nhau giữa các service.

## 14. Các tình huống kiểm chứng khi triển khai

Bảng dưới là kế hoạch kiểm chứng cho mô hình minh họa, không phải thông báo đã chạy kiểm thử trên một ứng dụng thực tế.

| Tình huống | Kết quả cần bảo đảm |
|---|---|
| Owner có grant edit sửa bản nháp đúng tenant | Tác vụ hợp lệ được phép |
| Owner không có grant cần thiết | Không tự nhận quyền chỉ vì là owner |
| Có grant nhưng tài nguyên thuộc người khác | Đúng điều kiện owner hoặc quan hệ được policy cho phép |
| Client thay tenant trong body | Không thay sự thật hiện tại dùng để đánh giá |
| Client tự nhận owner trong payload | Không nhận quyền trên tài nguyên nhờ giá trị đề xuất |
| Client gửi classification PUBLIC cho dữ liệu mật | Không bỏ qua nguồn phân loại có thẩm quyền |
| Thiếu classification hoặc tenant bắt buộc | Không tự chuyển thành đối tượng công khai hoặc không giới hạn |
| Classification có giá trị mới chưa hỗ trợ | Không lọt qua nhánh kiểm tra phủ định |
| Tập audience rỗng | Có đúng nghĩa không chia sẻ qua nhóm theo policy |
| Nguồn thuộc tính timeout | Không được hiểu là một giá trị rỗng thuận lợi |
| Parent của tài nguyên không đúng tenant | Không kế thừa thuộc tính từ container không hợp lệ |
| Di chuyển tài nguyên sang container khác | Kiểm tra quyền và cập nhật thuộc tính hiệu lực |
| Owner, state hoặc classification đổi giữa kiểm tra và ghi | Phối hợp phiên bản hoặc cơ chế nhất quán được áp dụng |
| Quyền thay đổi ở nguồn ngoài bản ghi | Không tuyên bố version bản ghi phát hiện được mọi thay đổi |
| ID trùng giữa hai tenant trong cache | Không dùng snapshot của tenant khác |
| API danh sách và totalCount | Không tiết lộ dữ liệu ngoài tập được phép |
| Báo cáo tổng hợp và điểm tải kết quả | Có thuộc tính và cơ chế bảo vệ phù hợp dữ liệu thực tế |
| Import, copy hoặc restore metadata | Không tạo đường sửa thuộc tính bảo mật ngoài quyền |
| Client gọi endpoint chẩn đoán attribute | Không làm lộ metadata vượt quyền |
| Thêm thuộc tính hoặc đổi miền giá trị | Policy và consumer có hành vi tương thích đã định |

Với thao tác bị từ chối, cần kiểm tra cả dữ liệu sau xử lý và tác động bên ngoài. Không được thay owner, phát sự kiện hoặc tạo file công khai rồi mới trả lỗi quyền.

Với thao tác được phép, cần kiểm tra đúng tài nguyên, đúng trường dữ liệu và đúng phạm vi. Mã phản hồi thành công không chứng minh snapshot mà policy đã dùng là đúng.

## 15. Cách thiết kế attributes cho một loại tài nguyên mới

Khi bổ sung một tài nguyên như “đề kiểm tra”, nhóm triển khai có thể đi qua các câu hỏi:

| Câu hỏi | Kết quả cần làm rõ |
|---|---|
| Policy cần biết gì về đề? | Tenant, owner, trạng thái, mức bảo vệ và quan hệ cần thiết |
| Ai xác nhận mỗi dữ kiện? | Dịch vụ hoặc quy trình có thẩm quyền |
| Ai được thay đổi? | Permission quản trị hoặc nghiệp vụ tương ứng |
| Khi thiếu thì sao? | Ngữ nghĩa tùy chọn hoặc hành vi không thể cho phép |
| Dữ kiện có thể cũ bao lâu? | Hợp đồng độ mới theo từng hành động |
| Có parent hoặc bản sao không? | Quy tắc kế thừa, chuyển container và dữ liệu dẫn xuất |
| Quyết định áp dụng ở đâu? | API, job, truy vấn, file tải xuống và các đường liên quan |
| Giải thích bằng chứng thế nào? | Định danh, phiên bản và thông tin quan sát phù hợp |

Resource attributes có giá trị khi chúng mô tả đúng đối tượng thực tế, được quản lý bởi nguồn có thẩm quyền và được sử dụng với ý nghĩa rõ ràng trong policy. Một điều kiện ABAC được viết chính xác vẫn không bảo vệ được tài nguyên nếu dữ kiện đầu vào có thể bị người gọi thay thế hoặc đã mất liên hệ với đối tượng đang được truy cập.

