# Policy versioning

## 1. Vì sao policy cần được quản lý phiên bản?

Trong ABAC (Attribute-Based Access Control), quyết định truy cập phụ thuộc vào thuộc tính của chủ thể, tài nguyên, hành động và môi trường. Một thay đổi nhỏ trong điều kiện của policy có thể làm hàng nghìn người dùng được cấp thêm quyền hoặc mất quyền đang cần cho công việc.

Ví dụ, một hệ thống quản lý hóa đơn đang cho phép nhân viên đọc hóa đơn của cùng bộ phận trong cùng tenant. Đội bảo mật muốn bổ sung yêu cầu: hóa đơn có mức phân loại confidential chỉ được đọc từ thiết bị do tổ chức quản lý. Đó là thay đổi hành vi phân quyền, dù mã policy chỉ thêm một điều kiện.

Nếu đội vận hành chỉ sửa trực tiếp file đang chạy, các câu hỏi sau rất khó trả lời:

- Request bị từ chối lúc 09:05 đã được đánh giá bằng policy nào?
- Mọi bộ đánh giá policy đã nhận phiên bản mới hay mới chỉ một phần?
- Người dùng bị mất quyền do policy thay đổi hay do thuộc tính bộ phận thay đổi?
- Có thể quay lại phiên bản trước mà không mở lại lỗ hổng vừa được khắc phục không?
- Ai đã duyệt thay đổi và những trường hợp quyền nào đã được kiểm thử?

**Policy versioning** là quản lý danh tính, nội dung, quan hệ phụ thuộc và lịch sử triển khai của policy qua từng phiên bản có thể truy vết. Mục tiêu là biết chính xác bộ quy tắc nào tạo ra quyết định nào, đưa thay đổi vào hoạt động có kiểm soát và phục hồi khi cần.

Trong nền tảng IAM, việc này hỗ trợ nguyên tắc ít quyền nhất: thay đổi quyền phải có chủ đích, có bằng chứng và có khả năng xác định phạm vi ảnh hưởng. Versioning không tự làm policy đúng; nó tạo điều kiện để đánh giá và vận hành policy một cách đáng tin cậy.

## 2. Phân biệt các loại phiên bản

Từ “version” dễ gây nhầm lẫn nếu dùng cho nhiều đối tượng khác nhau.

| Đối tượng | Ví dụ minh họa | Dùng để trả lời |
| --- | --- | --- |
| Danh tính policy | invoice-read | Đây là quy tắc nghiệp vụ nào? |
| Revision của policy | invoice-read/r19 | Nội dung cụ thể nào của quy tắc? |
| Commit nguồn | Một Git commit đầy đủ | Nội dung nguồn và lịch sử sửa đổi nằm ở đâu? |
| Artifact digest | SHA-256 của gói triển khai | Các byte triển khai có đúng gói đã duyệt không? |
| Release policy | authz-release-105 | Bộ policy và dữ liệu tĩnh nào được phát hành cùng nhau? |
| Phiên bản hợp đồng input | authorization-input/v3 | Các thuộc tính có tên, kiểu và ý nghĩa gì? |
| Phiên bản engine | Một bản engine được ghim cụ thể | Thành phần nào diễn giải policy? |
| Thế hệ kích hoạt | activation-generation 805 | Lần chuyển trạng thái triển khai nào mới hơn? |

Policy ID giữ ổn định khi quy tắc tiếp tục phục vụ cùng một mục đích. Revision thay đổi khi tạo một nội dung mới. Release có thể chứa nhiều policy, thư viện dùng chung và bảng dữ liệu phục vụ quyết định.

Một policy revision có thể xuất hiện trong nhiều release nếu nội dung của nó không đổi. Ngược lại, cùng một nhãn release không nên trỏ đến các nội dung khác nhau theo thời gian.

### 2.1. Nhãn dễ đọc và danh tính bất biến

Nhãn như v2.1.0 giúp con người giao tiếp. Digest giúp xác định nội dung. Hai giá trị phục vụ hai mục đích khác nhau.

Nếu nhãn v2.1.0 hôm nay trỏ tới gói A, ngày mai lại trỏ tới gói B, log chỉ ghi nhãn đó sẽ không còn đủ để tái dựng lịch sử. Vì vậy, sau khi công bố, ánh xạ giữa revision và nội dung cần được giữ bất biến. Muốn sửa thì phát hành revision mới.

Git commit cũng chưa đủ để định danh toàn bộ kết quả chạy nếu quá trình build kéo dependency hoặc dữ liệu ngoài mà không ghim phiên bản. Cần ghi lại cả đầu vào build và artifact thực tế được triển khai.

Digest xác nhận tính toàn vẹn khi có digest kỳ vọng đáng tin cậy. Tự tính hash của một file bất kỳ không chứng minh file đó đến từ người có thẩm quyền. Chữ ký và cơ chế phân phối tin cậy giải quyết thêm bài toán nguồn gốc.

### 2.2. Không nhầm version policy với version ngôn ngữ

Policy có thể mang revision r19 nhưng được viết theo một phiên bản ngôn ngữ policy khác. Tương tự, schema input v3 không nói rằng policy đã ở revision thứ ba.

Trong OPA, manifest bundle có trường revision để định danh revision của bundle. Đây là một chuỗi định danh, không phải cam kết rằng hệ thống sẽ hiểu thứ tự số học hoặc ý nghĩa nghiệp vụ của nhãn. [Tài liệu OPA về bundle manifest](https://www.openpolicyagent.org/docs/management-bundles).

## 3. Phải version những gì ngoài mã policy?

Một mô hình đơn giản của quyết định ABAC là:

~~~text
decision = evaluate(
    policy_release,
    trusted_attribute_input,
    engine_configuration
)
~~~

Nếu policy tra thêm dữ liệu ngoài, tập đầu vào thực tế còn bao gồm dữ liệu mà nó đọc trong lần đánh giá. Vì vậy, lưu mã policy là cần thiết nhưng chưa đủ.

### 3.1. Quy tắc và phụ thuộc tĩnh

Các đối tượng nên được gắn chặt với release khi chúng ảnh hưởng đến quyết định gồm:

- Policy entry point và những policy được gọi gián tiếp.
- Thư viện so sánh tenant, phân loại dữ liệu hoặc xử lý thời gian.
- Danh mục hành động và ánh xạ vai trò sang khả năng.
- Bảng thứ bậc phân loại tài liệu, nếu hệ thống sử dụng.
- Cấu hình kết hợp nhiều kết quả policy và cách xử lý lỗi.
- Schema input, schema output và bộ test tương ứng.

Ví dụ, policy không đổi nhưng bảng ánh xạ “support có thể export” được bổ sung thì tập quyền đã thay đổi. Nếu bảng này nằm trong bundle, thay đổi nó cần tạo release mới.

### 3.2. Thuộc tính động

Trạng thái nhân viên, tenant đang hoạt động, quyền sở hữu tài nguyên và mức tin cậy của thiết bị thường thay đổi độc lập với policy.

Không cần phát hành policy mới mỗi khi một nhân viên chuyển phòng ban. Tuy nhiên, cần biết nguồn thuộc tính, thời điểm đọc và mức độ mới của dữ liệu. Khi cần điều tra, có thể lưu snapshot tối thiểu hoặc mã tham chiếu đến lịch sử thuộc tính, theo chính sách lưu trữ của hệ thống.

Versioning policy không thay thế việc thu hồi tài khoản hoặc cập nhật quyền. Một policy hoàn toàn đúng vẫn có thể cho phép truy cập sai nếu nó nhận thuộc tính tenant hoặc trạng thái tài khoản đã lỗi thời.

### 3.3. Hợp đồng giữa các thành phần IAM

Bốn vai trò thường gặp giúp xác định nơi cần quản lý thay đổi:

- PAP (Policy Administration Point) là nơi soạn, duyệt và quản lý policy.
- PDP (Policy Decision Point) đánh giá policy để tạo quyết định.
- PIP (Policy Information Point) cung cấp thuộc tính phục vụ quyết định.
- PEP (Policy Enforcement Point) chặn hoặc cho phép thao tác theo quyết định.

Các vai trò này có thể được triển khai trong cùng một tiến trình hoặc tách thành dịch vụ. Versioning phải tính đến quan hệ giữa chúng, đặc biệt khi một bên thay đổi tên thuộc tính hoặc ý nghĩa kết quả.

Nếu PDP trả thêm nghĩa vụ “che số tài khoản” nhưng PEP chưa hiểu nghĩa vụ đó, việc nhận được Permit chưa bảo đảm thao tác được thực thi đúng. Hợp đồng output và khả năng thực thi nghĩa vụ cũng là phụ thuộc của release.

## 4. Ví dụ xuyên suốt: thay đổi quyền đọc hóa đơn

Xét ứng dụng SaaS có nhiều tenant. Quy tắc chung của cả hai revision là:

1. Chủ thể đã được xác thực và tài khoản đang hoạt động.
2. Chủ thể và hóa đơn thuộc cùng tenant.
3. Chủ thể thuộc bộ phận sở hữu hóa đơn.
4. Hành động là invoice:read.

Phiên bản mới bổ sung điều kiện thiết bị cho hóa đơn confidential. Đây là ví dụ do bài học xây dựng; các trường và mã revision không phải schema mặc định của một sản phẩm.

### 4.1. Input đã được chuẩn hóa

~~~json
{
  "subject": {
    "id": "employee-27",
    "tenant_id": "tenant-a",
    "department": "finance",
    "active": true
  },
  "resource": {
    "id": "invoice-91",
    "tenant_id": "tenant-a",
    "owner_department": "finance",
    "classification": "confidential"
  },
  "action": "invoice:read",
  "environment": {
    "device_managed": false
  }
}
~~~

Đây là input PDP nhận sau khi hệ thống lấy và kiểm tra thuộc tính từ các nguồn được tin cậy. Không cho người gọi tự khai tenant, bộ phận hoặc trạng thái thiết bị rồi coi đó là bằng chứng phân quyền.

Hợp đồng input quy định rõ các trường bắt buộc, kiểu boolean thực sự của active và device_managed, cùng tập giá trị classification được hỗ trợ. Không tự chuyển chuỗi "false" thành true hoặc gán một mức phân loại không biết thành public.

### 4.2. Hai revision bằng mã giả

~~~text
# Mã giả; không phải cú pháp của một engine cụ thể.

base_allowed(input):
    require subject.tenant_id is a non-empty trusted string
    require resource.tenant_id is a non-empty trusted string
    require subject.department is a non-empty trusted string
    require resource.owner_department is a non-empty trusted string
    require subject.active is a boolean
    require resource.classification is one of:
        public, internal, confidential

    return subject.active == true
       AND subject.tenant_id == resource.tenant_id
       AND subject.department == resource.owner_department
       AND action == "invoice:read"

invoice_read_r18(input):
    return base_allowed(input)

invoice_read_r19(input):
    if NOT base_allowed(input):
        return false

    if resource.classification == "confidential":
        return environment.device_managed is exactly boolean true

    return true
~~~

Các lệnh require biểu diễn kiểm tra hợp đồng: đầu vào thiếu hoặc sai kiểu dẫn đến lỗi đánh giá hoặc kết quả không cho phép, tùy thiết kế đã công bố. Chúng không được bỏ qua để tiếp tục cấp quyền.

Với input ở trên, r18 cho phép còn r19 từ chối. Nếu thiết bị chuyển thành managed và những điều kiện khác vẫn đúng, cả hai cùng cho phép.

Nếu thiếu device_managed đối với tài liệu confidential, r19 không cấp Permit. Khi tích hợp engine thực, cần quy định rõ kết quả đó được biểu diễn là Deny, NotApplicable hay Indeterminate và PEP xử lý thế nào. Không mặc định rằng mọi engine đều có cùng mô hình kết quả.

### 4.3. Thay đổi nào thực sự xảy ra?

Gọi A18 là tập input được r18 cho phép và A19 là tập input được r19 cho phép.

~~~text
A19 nằm trong hoặc bằng A18

Quyền bị thu hẹp:
    A18 trừ A19

Quyền được mở thêm:
    A19 trừ A18
~~~

Với đúng mã giả trên và cùng đầu vào hợp lệ, r19 không mở thêm quyền. Nó thu hẹp quyền đối với hóa đơn confidential trên thiết bị không đáp ứng điều kiện.

Điều này không có nghĩa thay đổi chắc chắn an toàn để triển khai ngay. Quy trình tài chính có thể đang dựa vào thiết bị chưa đăng ký. Ngoài ra, một người dùng mất quyền đọc có thể chuyển sang endpoint export nếu endpoint đó được bảo vệ không đồng nhất.

Khi đánh giá thay đổi, phải kiểm tra cả mục tiêu bảo mật và những luồng công việc được cho phép. Không dùng tỷ lệ Deny cao hơn làm bằng chứng duy nhất cho chất lượng policy.

## 5. Semantic versioning có đủ không?

Có thể dùng MAJOR.MINOR.PATCH nếu đội thống nhất rõ hợp đồng của cách đánh số. Tuy nhiên, policy không có cùng khái niệm tương thích đơn giản như một thư viện lập trình.

Một thay đổi chỉ sửa một dòng vẫn có thể mở quyền truy cập giữa các tenant. Một thay đổi giữ nguyên tên field nhưng chuyển đơn vị thời gian từ giây sang mili giây có thể phá vỡ ý nghĩa của điều kiện.

| Loại thay đổi | Tác động cần xem xét |
| --- | --- |
| Sửa mô tả không tham gia đánh giá | Có thể không đổi quyết định; vẫn cần truy vết nguồn |
| Bổ sung hành động được phép | Mở rộng tập quyền, cần xem xét phạm vi |
| Thêm điều kiện MFA hoặc thiết bị | Thu hẹp quyền, có thể làm gián đoạn nghiệp vụ |
| Đổi tên hoặc ý nghĩa thuộc tính | Có thể phá hợp đồng giữa PIP, PDP và PEP |
| Đổi cách kết hợp nhiều policy | Có thể thay đổi ưu tiên Allow/Deny trên diện rộng |
| Nâng engine hoặc thư viện dùng chung | Cần kiểm tra lại hành vi trên tập input mục tiêu |

Một quy ước thực tế là giữ revision bất biến cho máy, dùng nhãn dễ đọc cho con người và ghi riêng loại thay đổi: mở quyền, thu hẹp quyền, thay đổi hợp đồng hoặc bảo trì không dự kiến đổi quyết định.

Đừng suy ra “patch nên không cần kiểm tra quyền”. Mức độ kiểm tra phụ thuộc tác động thực tế và tài nguyên được bảo vệ, không phụ thuộc riêng nhãn version.

## 6. Gói phát hành và bằng chứng phê duyệt

Một release cần cho phép truy ngược từ artifact đang chạy về nguồn và ý định thay đổi. Có thể dùng một hồ sơ phát hành tách khỏi gói policy.

~~~yaml
# Hồ sơ minh họa do hệ thống phát hành tự định nghĩa.
# Các giá trị trong dấu <> là chỗ điền, không phải dữ liệu triển khai.
release_id: authz-release-105
policy_revisions:
  invoice-read: r19
source_commit: "<full-git-commit>"
artifact:
  digest_algorithm: SHA-256
  digest: "<sha256-of-the-final-policy-artifact>"
input_contract: authorization-input/v3
output_contract: authorization-decision/v2
engine_build: "<exact-engine-build>"
static_data_revision: authorization-catalog-42
change_reference: IAM-248
approved_test_evidence: "<immutable-test-report-reference>"
rollback_target: authz-release-104
~~~

Digest trong ví dụ là hash của artifact policy, còn hồ sơ phát hành nằm ngoài artifact đó để tránh yêu cầu tự hash chính mình. Nếu cần ký hồ sơ, phải quy định rõ phần nội dung được ký và cách xác thực khóa ký.

Hồ sơ cần liên kết đến bằng chứng phê duyệt thực tế. Ghi một trường approved: true mà không kiểm soát ai được ghi và không giữ lịch sử không tạo ra quy trình duyệt đáng tin cậy.

Một artifact đã qua kiểm thử nên được đưa từ môi trường kiểm thử sang production bằng cùng digest. Build lại ở mỗi môi trường có thể đưa vào dependency hoặc dữ liệu khác, khiến bằng chứng kiểm thử không còn áp dụng trực tiếp.

Cấu hình riêng theo môi trường vẫn có thể khác, nhưng những giá trị ảnh hưởng đến quyền phải được quản lý và truy vết. Không để một biến môi trường không được ghi nhận âm thầm biến policy “chỉ cùng tenant” thành “mọi tenant”.

## 7. Quy trình thay đổi từ đề xuất đến kích hoạt

~~~mermaid
flowchart TD
    A["Đề xuất thay đổi quyền"] --> B["Soạn policy và test"]
    B --> C["Review nghiệp vụ và bảo mật"]
    C --> D["Build artifact bất biến"]
    D --> E["Kiểm thử và so sánh quyết định"]
    E --> F["Shadow trên dữ liệu phù hợp"]
    F --> G["Canary có thực thi"]
    G --> H["Mở rộng triển khai"]
    H --> I["Xác minh revision đang hoạt động"]
    G --> J["Dừng hoặc rollback theo tiêu chí"]
~~~

Sơ đồ biểu diễn một quy trình tham khảo. Một hệ thống nhỏ có thể gộp một số công đoạn, nhưng vẫn cần giữ các bằng chứng: nội dung nào thay đổi, ai duyệt, đã kiểm tra gì và môi trường thực tế đang thực thi phiên bản nào.

### 7.1. Mô tả thay đổi bằng hành vi quyền

Đề xuất cho r19 nên nói rõ:

“Người dùng cùng bộ phận, cùng tenant chỉ được đọc hóa đơn confidential khi thiết bị do tổ chức quản lý.”

Mô tả “thêm kiểm tra device_managed” chưa đủ. Reviewer cần biết nhóm người dùng nào thay đổi quyền, đầu vào thiếu được xử lý ra sao, endpoint nào bị tác động và các ngoại lệ có được phép tồn tại hay không.

Nếu cần ngoại lệ, nó phải là thay đổi quyền có điều kiện cụ thể, người chịu trách nhiệm và thời hạn. Không thêm một nhóm bypass rộng chỉ để tránh xử lý những ca bị từ chối trong thử nghiệm.

### 7.2. Tách người soạn và người duyệt phù hợp

Quy trình IAM thường cần sự tham gia của chủ sở hữu tài nguyên và người chịu trách nhiệm bảo mật. Một bên xác nhận nghiệp vụ được phép; bên còn lại kiểm tra tenant boundary, quyền tối thiểu và tác động bảo mật.

Quyền sửa kho mã không nên mặc nhiên đồng nghĩa quyền phát hành policy production. Các quyền tạo, duyệt và kích hoạt release là quyền quản trị IAM cần được kiểm soát và kiểm toán.

## 8. Kiểm thử thay đổi policy

Kiểm thử cần nêu rõ quyết định mong đợi theo yêu cầu nghiệp vụ. Không lấy chính kết quả của policy mới làm đáp án rồi kết luận test đã đúng.

### 8.1. Ma trận quyết định cho ví dụ hóa đơn

Các hàng dưới đây giả định những điều kiện không được nhắc đến đều hợp lệ.

| Trường hợp | r18 | r19 | Ý nghĩa |
| --- | --- | --- | --- |
| Cùng tenant, cùng bộ phận, internal | Permit | Permit | Luồng hợp lệ vẫn hoạt động |
| Confidential, thiết bị managed | Permit | Permit | Luồng đáp ứng yêu cầu mới |
| Confidential, thiết bị unmanaged | Permit | Không Permit | Thu hẹp quyền có chủ đích |
| Confidential, thiếu thuộc tính thiết bị | Permit | Không Permit | Không có bằng chứng đáp ứng điều kiện |
| Confidential, device_managed là chuỗi "true" | Permit | Không Permit | Không chấp nhận sai kiểu thay cho bằng chứng |
| Khác tenant, thiết bị managed | Không Permit | Không Permit | Ranh giới tenant được giữ |
| Khác bộ phận | Không Permit | Không Permit | Không mở quyền ngoài phạm vi |
| Tài khoản không hoạt động | Không Permit | Không Permit | Thu hồi tài khoản vẫn có hiệu lực |
| Hành động invoice:export | Không Permit | Không Permit | Policy đọc không tự cấp quyền export |
| Classification không được hỗ trợ | Không Permit | Không Permit | Input ngoài hợp đồng không được coi là public |

“Không Permit” ở đây mô tả yêu cầu thực thi: PEP không thực hiện thao tác được bảo vệ. Bộ test tích hợp cần kiểm tra thêm mã quyết định hoặc lỗi cụ thể theo contract đã chọn.

### 8.2. Các lớp kiểm thử

Unit test kiểm tra policy với những input cụ thể, bao gồm cả Allow và Deny. Integration test xác nhận thuộc tính thực sự đi từ PIP qua PDP tới PEP đúng tên, kiểu và nguồn tin cậy. Kiểm thử đầu cuối xác nhận endpoint thực sự chặn thao tác, kể cả đường truy cập thay thế.

Có thể kiểm tra các bất biến quan trọng trên nhiều input:

- Không có Permit khi subject.tenant_id khác resource.tenant_id.
- Tài khoản không hoạt động không được đọc hóa đơn.
- Policy đọc không cấp quyền cho hành động export.
- Với r19, hóa đơn confidential không được đọc nếu device_managed không phải boolean true.

Đây là thuộc tính mong đợi của ví dụ, không phải kết luận tự động cho mọi thiết kế ABAC. Khi hệ thống cho phép truy cập liên tenant có ủy quyền rõ ràng, bất biến phải được viết lại để phản ánh chính xác phạm vi cho phép.

OPA cung cấp cơ chế viết và chạy test cho policy bằng Rego. Việc engine hỗ trợ test giúp xây dựng kiểm tra tự động, nhưng đội triển khai vẫn phải xác định tình huống và đáp án nghiệp vụ. [Tài liệu OPA về kiểm thử policy](https://www.openpolicyagent.org/docs/policy-testing).

### 8.3. So sánh hai phiên bản trên cùng tập input

Với cùng input x, tính quyết định của bản cũ và bản mới rồi phân loại:

~~~text
Permit  -> Permit       Giữ quyền
Permit  -> Không Permit Thu hẹp quyền
Không Permit -> Permit  Mở quyền
Không Permit -> Không Permit  Chưa thấy thay đổi quyền
~~~

Nếu output còn chứa bộ lọc dữ liệu, trường được phép trả về hoặc nghĩa vụ thực thi, cần so sánh các phần đó. Hai kết quả cùng Permit vẫn có thể cho phép nhìn thấy dữ liệu khác nhau.

Một tập replay không xuất hiện chênh lệch không chứng minh hai policy tương đương trên mọi input. Nó chỉ cung cấp bằng chứng trong phạm vi các trường hợp đã được đánh giá. Những ca hiếm như truy cập liên tenant phải có test chủ động, không chỉ chờ xuất hiện trong log.

## 9. Shadow evaluation và canary

### 9.1. Shadow: quan sát mà chưa đổi quyền thực thi

Trong shadow mode, quyết định đang có hiệu lực vẫn đến từ release hiện hành. Release ứng viên nhận cùng một bản input được chuẩn hóa và tạo kết quả để so sánh, nhưng kết quả đó chưa dùng để cấp hoặc từ chối quyền thực tế.

~~~text
Một bản input đã chụp tại thời điểm đánh giá
    -> PDP hiện hành -> PEP thực thi
    -> PDP ứng viên -> ghi chênh lệch để phân tích
~~~

Nếu hai lần đánh giá tự lấy thuộc tính ở hai thời điểm khác nhau, chênh lệch có thể do dữ liệu thay đổi chứ không phải policy. Các lời gọi thời gian hiện tại hoặc nguồn dữ liệu ngoài cũng phải được kiểm soát khi cần so sánh có ý nghĩa.

Shadow nên tránh thực hiện tác dụng phụ. Việc gửi thông báo hoặc thay đổi dữ liệu theo output ứng viên sẽ làm phép thử ảnh hưởng hệ thống dù quyết định chưa được thực thi.

Đối với r19, cần đo những trường hợp confidential sẽ bị từ chối và kiểm tra đó có đúng nhóm thiết bị không đáp ứng yêu cầu hay do hệ thống chưa thu thập được thuộc tính.

### 9.2. Canary: áp dụng thật cho một phạm vi nhỏ

Canary sử dụng release mới để thực thi trên một cohort có kiểm soát, chẳng hạn một nhóm tenant nội bộ đã sẵn sàng.

Phạm vi canary nên được chọn ổn định và phù hợp với luồng nghiệp vụ. Nếu mỗi request ngẫu nhiên chạy một revision khác nhau, người dùng có thể lúc đọc được, lúc không đọc được cùng một tài nguyên.

Những chỉ số hữu ích gồm tỷ lệ Deny theo hành động, số lần thiếu thuộc tính, lỗi đánh giá, độ trễ PDP và phân bố revision đang hoạt động. Cần tách theo tenant hoặc nhóm tài nguyên phù hợp để một tỷ lệ trung bình không che mất sự cố của một nhóm nhỏ.

Ngưỡng dừng cần được thỏa thuận trước khi triển khai. Ví dụ, mọi chênh lệch mở quyền ngoài phạm vi đã duyệt phải được điều tra; nhóm r19 không nên xuất hiện trường hợp mới cho phép truy cập khác tenant.

## 10. Triển khai trong hệ thống phân tán

### 10.1. Phân biệt trạng thái mong muốn với trạng thái thực tế

Kho cấu hình có thể đã trỏ tới release-105 nhưng một số PDP vẫn chạy release-104. Các nguyên nhân có thể là lỗi tải gói, lỗi xác thực, bundle không tương thích hoặc mất kết nối.

Một mô hình trạng thái đơn giản là:

~~~text
desired_release  = release mà control plane yêu cầu
downloaded_release = release đã tải về
active_release   = release đang dùng để quyết định
~~~

Chỉ thông báo “đã phát hành” từ pipeline chưa chứng minh các request đã dùng phiên bản mới. Cần nhận trạng thái kích hoạt từ những PDP phục vụ đúng phạm vi rollout và đối chiếu với log quyết định.

OPA có Status API báo revision bundle đã kích hoạt thành công và lỗi kích hoạt. Đây là một ví dụ cụ thể cho việc quan sát trạng thái thực thi, thay vì chỉ dựa vào trạng thái của kho artifact. [Tài liệu OPA Status](https://www.openpolicyagent.org/docs/management-status).

### 10.2. Kích hoạt một bộ policy nhất quán

Giả sử policy invoice-read/r19 cần thư viện tenant-check/r7 và bảng classification-42. Không nên cập nhật từng thành phần bằng cách ghi đè trực tiếp trong khi request vẫn đọc chúng.

Một cách triển khai là chuẩn bị toàn bộ release mới, kiểm tra đủ phụ thuộc, rồi chuyển tham chiếu đang hoạt động sang snapshot mới một cách nguyên tử trong phạm vi một PDP. Request đang xử lý cần có quy ước rõ ràng về snapshot được dùng.

Tính nguyên tử bên trong một PDP không đồng nghĩa toàn bộ cụm chuyển phiên bản cùng lúc. Muốn bảo đảm theo tenant, giao dịch hoặc mức rủi ro, hệ thống cần thêm điều phối, routing hoặc cơ chế từ chối phục vụ khi không đáp ứng yêu cầu.

Không giả định mọi engine hỗ trợ transaction nhiều bundle. Nếu các policy phụ thuộc chặt chẽ, đóng gói và kiểm tra cơ chế kích hoạt của engine trước khi chọn cách tách bundle.

### 10.3. Client không được tùy chọn policy dễ hơn

Trường revision trong request có thể hữu ích cho thử nghiệm nội bộ, nhưng không được để một người dùng không tin cậy chọn revision cũ nhằm bỏ qua điều kiện mới.

Việc chọn release có hiệu lực cần do hệ thống kiểm soát theo tenant, môi trường hoặc giai đoạn triển khai. Dữ liệu do client gửi có thể là đầu vào cần xác minh; nó không tự trở thành quyền chọn cơ chế phân quyền.

## 11. Versioning và cache quyết định

Cache có thể giữ Permit được tạo bởi r18 sau khi hệ thống chuyển sang r19. Khi đó, PDP đã cập nhật đúng nhưng PEP vẫn cho đọc hóa đơn confidential trên thiết bị unmanaged.

Khóa cache cần phản ánh những yếu tố làm thay đổi quyết định. Một ví dụ khái niệm là:

~~~text
cache_key = hash(
    effective_policy_release,
    normalized_action,
    subject_authorization_context,
    resource_authorization_context,
    relevant_environment_context
)
~~~

Đây không phải hướng dẫn lưu nguyên dữ liệu nhạy cảm vào khóa cache. Hệ thống có thể sử dụng ID, phiên bản trạng thái và fingerprint được thiết kế phù hợp.

Chỉ thêm revision vào cache key cũng chưa đủ. Nếu tài khoản bị khóa hoặc tài nguyên đổi tenant mà release không đổi, kết quả cũ vẫn có thể sai. Cần kết hợp TTL, cập nhật phiên bản thuộc tính hoặc cơ chế vô hiệu hóa cache theo yêu cầu thu hồi quyền.

Khi rollback cũng phải xử lý cache theo release thực sự được kích hoạt. Không giữ kết quả tính từ policy mới rồi gắn nhãn là kết quả của policy cũ.

Với thao tác có tác động lớn, còn cần xem xét khoảng thời gian giữa kiểm tra quyền và sử dụng tài nguyên. Nếu tài nguyên hoặc thuộc tính bảo mật thay đổi trong khoảng đó, versioning policy không tự giải quyết vấn đề time-of-check/time-of-use.

## 12. Rollback và kiểm soát phát lại phiên bản cũ

Rollback là đưa một release đã biết trở lại làm phiên bản có hiệu lực. Nó cần một target cụ thể, tương thích với môi trường hiện tại và còn được phép sử dụng.

### 12.1. Trình tự rollback tham khảo

1. Xác định release gây lỗi, phạm vi bị ảnh hưởng và artifact đang thực sự hoạt động.
2. Kiểm tra target rollback còn đáp ứng yêu cầu bảo mật và hợp đồng dữ liệu hiện hành.
3. Tạo thao tác kích hoạt mới trỏ tới artifact target đã xác minh.
4. Theo dõi từng PDP trong phạm vi rollback và xử lý cache tương ứng.
5. Chạy những kiểm tra quyền trọng yếu, xác nhận trạng thái thực thi và lưu bằng chứng.

Không sửa lại byte của release cũ cho “đúng với hiện tại”. Nếu cần thay nội dung, đó là một release mới.

### 12.2. Khi nào rollback mở lại quyền không được phép?

Trong ví dụ, r19 chặn thiết bị unmanaged. Quay lại r18 sẽ mở lại chính nhóm quyền đó. Nếu yêu cầu thiết bị managed là biện pháp cần thiết để chặn một sự cố đang diễn ra, rollback toàn bộ có thể không phù hợp.

Một lựa chọn có thể là phát hành r20 sửa lỗi thu thập thuộc tính, triển khai biện pháp chặn ở lớp thực thi trong phạm vi đã duyệt hoặc tạm dừng thao tác bị ảnh hưởng. Lựa chọn cụ thể phải dựa vào nguyên nhân sự cố và quyền vận hành đã được cấp.

“Bản trước từng chạy tốt” không đồng nghĩa nó vẫn phù hợp với trạng thái bảo mật hiện tại.

### 12.3. Phân biệt nội dung cũ và lệnh kích hoạt mới

Nếu cơ chế chống phát lại chỉ chấp nhận số revision tăng dần, rollback về nội dung cũ có thể bị chặn. Nếu bỏ hoàn toàn kiểm tra thứ tự, một lệnh triển khai cũ đến muộn có thể ghi đè release mới.

Có thể tách hai danh tính:

~~~text
Generation 804 -> artifact của release-105
Generation 805 -> artifact của release-104  # rollback đã được duyệt
Generation 803 -> bị từ chối vì là lệnh kích hoạt cũ
~~~

Generation biểu diễn thứ tự lệnh triển khai được tin cậy; artifact biểu diễn nội dung policy. Một lần kích hoạt mới có thể trỏ tới nội dung cũ khi được phép.

Đây là thiết kế điều phối tham khảo, không phải chức năng mặc định của mọi engine. Chống phát lại cũng cần xác thực nguồn lệnh; một con số tăng dần do client tùy ý cung cấp không tạo ra bảo đảm.

## 13. Tương thích schema và migration thuộc tính

Giả sử r19 sử dụng device_managed nhưng PIP cũ chưa cung cấp field này. Nếu phát hành r19 trước khi cập nhật nguồn thuộc tính, nhiều request hợp lệ sẽ không được cấp quyền.

Một kế hoạch migration có thể gồm:

1. Công bố hợp đồng input mới và định nghĩa nguồn tin cậy của thuộc tính.
2. Cập nhật PIP và lớp chuẩn hóa input để cung cấp dữ liệu, đồng thời đo tỷ lệ thiếu.
3. Chạy release ứng viên ở shadow, kiểm tra cả dữ liệu và chênh lệch quyền.
4. Chỉ bắt đầu canary khi cohort mục tiêu có khả năng cung cấp thuộc tính đúng.
5. Giữ khả năng đọc hợp đồng cũ trong thời gian rollback nếu cần.
6. Loại bỏ hợp đồng cũ sau khi hết cửa sổ tương thích đã xác định.

Việc thêm field vào JSON có thể không phá cú pháp của consumer cũ, nhưng việc policy bắt buộc field đó có thể phá hành vi cấp quyền. Cần kiểm tra tương thích ở mức ý nghĩa.

Không dùng giá trị mặc định rộng quyền chỉ để che thiếu dữ liệu trong migration. Với device_managed, thiếu bằng chứng không nên bị diễn giải thành thiết bị đã được quản lý.

Tương tự, đổi từ department sang departments không chỉ là đổi tên. Phải quy định rõ phép so sánh mới là “thuộc ít nhất một bộ phận”, “thuộc tất cả” hay “bộ phận hiện hành”, rồi kiểm tra tác động quyền.

## 14. Audit: gắn quyết định với phiên bản thực thi

Khi điều tra một quyết định, log nên giúp trả lời ai yêu cầu gì, vào lúc nào, bằng release nào và kết quả nào đã được PEP thực thi.

Một bản ghi minh họa, không phải schema log chuẩn của OPA:

~~~json
{
  "decision_id": "decision-8f21",
  "timestamp": "2026-01-15T02:05:00Z",
  "subject_ref": "employee-27",
  "resource_ref": "invoice-91",
  "action": "invoice:read",
  "effective_release": "authz-release-105",
  "policy_revision": "invoice-read/r19",
  "pdp_instance": "pdp-zone-a-03",
  "input_contract": "authorization-input/v3",
  "attribute_evidence_ref": "evidence-371",
  "result": "Deny",
  "reason_code": "MANAGED_DEVICE_REQUIRED"
}
~~~

Timestamp chỉ là dữ liệu minh họa. Mã lý do do hệ thống thiết kế và cần phù hợp với những thông tin được phép tiết lộ cho từng đối tượng.

effective_release phải lấy từ snapshot PDP thực sự sử dụng, không lấy nhãn mới nhất của control plane sau khi quyết định đã xảy ra.

Không nhất thiết ghi toàn bộ input, token hoặc thông tin cá nhân vào log. Có thể che dữ liệu, giữ các trường cần thiết và tham chiếu tới bằng chứng được kiểm soát truy cập. Việc tái hiện quyết định cần cân bằng nhu cầu điều tra với chính sách lưu trữ và bảo vệ dữ liệu.

OPA hỗ trợ decision log chứa thông tin truy vấn cùng metadata bundle, giúp liên kết quyết định với nội dung policy. Phạm vi dữ liệu được lưu vẫn cần được cấu hình phù hợp với hệ thống cụ thể. [Tài liệu OPA Decision Logs](https://www.openpolicyagent.org/docs/management-decision-logs).

### 14.1. Replay phục vụ điều tra khác với quyết định hiện tại

Nếu replay để trả lời “vì sao lúc đó được phép”, phải dùng policy, dữ liệu và ngữ cảnh tương ứng với thời điểm đó trong phạm vi bằng chứng còn lưu.

Nếu đánh giá xem “bây giờ có được phép không”, phải dùng trạng thái hiện tại. Không lấy Permit lịch sử để cho phép một thao tác hiện tại sau khi tài khoản hoặc quyền đã bị thu hồi.

Khi không có đủ snapshot thuộc tính hoặc phụ thuộc ngoài, cần ghi nhận giới hạn tái hiện thay vì kết luận chắc chắn rằng policy là nguyên nhân duy nhất.

## 15. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Ghi đè nội dung dưới cùng revision | Log không xác định được byte thực tế | Tạo revision mới và giữ ánh xạ bất biến |
| Chỉ version mã, bỏ quên bảng dữ liệu | Không giải thích được thay đổi quyền | Gắn phụ thuộc tĩnh với release |
| Cho client chọn revision | Có thể quay về điều kiện dễ hơn | Hệ thống tin cậy quyết định release |
| Chỉ test trường hợp được phép | Bỏ sót mở quyền ngoài phạm vi | Thêm ca Deny, sai tenant, thiếu và sai kiểu thuộc tính |
| Thấy pipeline thành công là kết thúc | Một số PDP có thể còn chạy bản cũ | Xác minh active release trong phạm vi rollout |
| Giữ cache Permit qua thay đổi policy | Thực thi quyền của bản trước | Gắn cache với release và quản lý freshness thuộc tính |
| Rollback không kiểm tra schema | Bản cũ không hiểu dữ liệu hiện tại | Giữ ma trận tương thích và kiểm tra target |
| Suy ra an toàn từ nhãn PATCH | Bỏ qua thay đổi ngữ nghĩa quyền | Review tập quyền thay đổi thực tế |
| Gắn latest vào mọi log | Mất dấu revision đã quyết định | Ghi revision thực tế tại thời điểm đánh giá |

Một lỗi nữa là phân loại mọi Deny phát sinh sau deploy thành lỗi policy. Trước tiên cần xác định revision thực thi, nguồn input, kết quả đánh giá và hành vi PEP. Policy, dữ liệu thuộc tính, hợp đồng tích hợp và cache là các nguyên nhân khác nhau nhưng có thể cùng biểu hiện thành “người dùng không truy cập được”.

## 16. Bài tập vận dụng

### Tình huống 1: r19 không đổi nhưng người dùng mất quyền

Một nhân viên từng đọc được hóa đơn confidential, sau đó bị từ chối dù policy revision vẫn là r19.

Hãy kiểm tra trạng thái tài khoản, bộ phận, tenant, phân loại hóa đơn, độ mới của bằng chứng thiết bị và cache. Cùng revision không có nghĩa cùng input, nên quyết định khác nhau chưa chứng minh policy bị thay đổi ngoài kiểm soát.

### Tình huống 2: rollback vẫn còn một nhóm bị từ chối

Control plane trỏ lại release-104 nhưng một số request vẫn bị từ chối vì MANAGED_DEVICE_REQUIRED.

Cần đối chiếu active release của PDP phục vụ request, kiểm tra routing và cache, rồi xem có lớp PEP nào vẫn thực thi điều kiện mới hay không. Nhãn mong muốn của control plane không đủ để kết luận rollback đã có hiệu lực toàn bộ.

### Tình huống 3: thay đổi tưởng là thu hẹp nhưng lại mở quyền

Đội phát triển thêm điều kiện thiết bị, đồng thời sửa thư viện kiểm tra tenant. So sánh hai phiên bản xuất hiện một trường hợp khác tenant chuyển từ Không Permit sang Permit.

Không kết luận release chỉ thu hẹp quyền dựa vào điều kiện mới. Phải xem toàn bộ diff và phụ thuộc của release, giữ test tái hiện trường hợp mở quyền, rồi sửa và phát hành một artifact mới qua quy trình kiểm tra.

### Tình huống 4: thiết kế bằng chứng phát hành

Với yêu cầu thêm điều kiện MFA cho hành động invoice:export, hãy xác định:

- Những policy, schema và nguồn thuộc tính nào cần thay đổi?
- Các trường hợp nào phải tiếp tục Permit, phải chuyển sang Deny hoặc phải bị chặn do thiếu bằng chứng?
- Cohort nào phù hợp để canary và theo dõi chỉ số gì?
- Release nào có thể rollback, và rollback có mở lại quyền vừa bị hạn chế không?
- Log nào giúp phân biệt thiếu MFA, sai tenant và PDP chạy sai revision?

Một phương án tốt phải gắn được yêu cầu nghiệp vụ với test, artifact được duyệt và trạng thái đang thực thi. Đó là giá trị cốt lõi của policy versioning trong vận hành IAM.
