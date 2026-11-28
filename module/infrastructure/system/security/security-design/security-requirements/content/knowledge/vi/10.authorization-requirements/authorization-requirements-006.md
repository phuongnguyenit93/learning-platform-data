# ABAC

## 1. ABAC giải quyết yêu cầu phân quyền nào?

**ABAC — Attribute-Based Access Control** là cách kiểm soát truy cập bằng chính sách đánh giá các thuộc tính của chủ thể, tài nguyên, hành động và ngữ cảnh. Một quyết định không chỉ hỏi người dùng có vai trò gì, mà còn hỏi vai trò đó có hiệu lực đối với tài nguyên nào, trong tenant nào, vào thời điểm nào và với điều kiện gì.

Ví dụ, câu “giảng viên được xem hồ sơ đánh giá” còn thiếu phạm vi. Một đặc tả đầy đủ hơn có thể là:

> Giảng viên đang hoạt động chỉ được đọc hồ sơ đánh giá của học phần mà họ đang được phân công trong cùng tenant. Hồ sơ hạn chế yêu cầu xác thực đủ mạnh còn mới. Hệ thống chỉ trả các trường được phép và phải từ chối nếu không xác nhận được phân công hoặc trạng thái thành viên.

Đây là một yêu cầu về **authorization**, tức quyết định chủ thể được làm gì với tài nguyên. Authentication, tức xác thực, cung cấp bằng chứng về danh tính và cách đăng nhập; đăng nhập thành công không tự tạo quyền đọc mọi tài nguyên.

Trong phạm vi thiết kế yêu cầu bảo mật, ABAC cần được mô tả đủ để:

- Liên kết điều kiện cho phép với rủi ro cần kiểm soát.
- Xác định nguồn và thời hạn tin cậy của từng thuộc tính.
- Chỉ ra nơi ra quyết định và nơi cưỡng chế quyết định.
- Đặc tả trường hợp thiếu dữ liệu, lỗi phụ thuộc, thu hồi quyền và cạnh tranh cập nhật.
- Tạo được tiêu chí nghiệm thu cho cả trường hợp được phép và bị từ chối.

ABAC không đồng nghĩa phải sử dụng một sản phẩm hay ngôn ngữ chính sách cụ thể. Một thư viện trong ứng dụng hoặc một dịch vụ quyết định tập trung đều có thể thực hiện mô hình này; giá trị nằm ở nghĩa của chính sách và khả năng cưỡng chế nhất quán.

## 2. Mô hình quyết định và quan hệ với các cách phân quyền khác

Có thể biểu diễn một yêu cầu quyết định như sau:

~~~text
decision = evaluate(
    subject,
    action,
    resource,
    environment,
    policyVersion
)
~~~

| Nhóm đầu vào | Ví dụ | Câu hỏi cần trả lời |
| --- | --- | --- |
| Chủ thể — subject | ID, trạng thái thành viên, vai trò, tổ chức, mức xác thực | Ai đang thực hiện và có tư cách gì? |
| Hành động — action | assessment.read, grade.update, grade.publish, grade.export | Đang xin thực hiện đúng thao tác nào? |
| Tài nguyên — resource | ID hồ sơ, tenant, chủ sở hữu, học phần, trạng thái, mức nhạy cảm | Quyền đang áp dụng lên đối tượng nào? |
| Ngữ cảnh — environment | Thời gian máy chủ, mức rủi ro phiên, mục đích đã phê duyệt | Điều kiện hiện tại có đáp ứng chính sách không? |
| Chính sách | Phiên bản quy tắc, cách kết hợp, nghĩa vụ kèm theo | Điều kiện nào quyết định và cần làm gì sau khi cho phép? |

Một thuộc tính chỉ có ý nghĩa bảo mật nếu có kiểu dữ liệu, nguồn tin cậy và cách xác định hiệu lực. Trường JSON tên “role” hoặc “tenantId” do client gửi không tự trở thành thuộc tính đáng tin.

ABAC có thể kết hợp với các mô hình khác:

| Cách biểu diễn | Trọng tâm | Cách phối hợp với ABAC |
| --- | --- | --- |
| RBAC | Quyền theo vai trò | Vai trò có thể là một thuộc tính, kèm điều kiện tenant, học phần và trạng thái |
| ACL | Danh sách quyền trên đối tượng | Mục cấp quyền cụ thể có thể trở thành bằng chứng cho một quy tắc |
| Quyền sở hữu | Quan hệ giữa người dùng và tài nguyên | So sánh subject ID với owner ID đáng tin |
| Phân quyền theo quan hệ | Đồ thị quan hệ như giảng viên của học phần | Dùng quan hệ đã được xác nhận làm dữ kiện của chính sách |

Không nên khẳng định cứ nhiều thuộc tính là an toàn hơn. Thêm một thuộc tính dễ giả mạo hoặc không rõ thời hạn có thể làm quyết định khó kiểm chứng hơn. Nếu vai trò đã diễn đạt đủ yêu cầu của một thao tác, không cần bổ sung ngữ cảnh không có mục đích.

## 3. Tình huống mẫu: hồ sơ đánh giá trong nền tảng học tập

Xét nền tảng phục vụ nhiều đơn vị đào tạo. Mỗi tenant có học viên, giảng viên và người duyệt kết quả. Một hồ sơ đánh giá có các thuộc tính:

~~~yaml
assessment:
  id: assessment-demo-01
  tenantId: tenant-demo-a
  learnerId: learner-demo-01
  courseId: course-demo-01
  state: REVIEWED
  classification: RESTRICTED
  lastEditorId: instructor-demo-02
  version: 12
~~~

Các giá trị chỉ dùng để minh họa hợp đồng dữ liệu. Mức nhạy cảm trong tình huống này gồm INTERNAL và RESTRICTED, được định nghĩa bằng enum; không suy ra thứ bậc từ phép so sánh chuỗi theo bảng chữ cái.

Một số rủi ro cần chuyển thành yêu cầu:

| Mã rủi ro | Tình huống | Tác động | Điều kiện bảo vệ cần thiết |
| --- | --- | --- | --- |
| R-AB-01 | Sửa ID tài nguyên hoặc tenant trong request | Đọc dữ liệu đơn vị khác | Ràng buộc tenant giữa chủ thể, quyền và tài nguyên |
| R-AB-02 | Tự khai vai trò hoặc phân công | Nhận quyền không được cấp | Thuộc tính từ nguồn có thẩm quyền |
| R-AB-03 | Dùng thông tin thành viên cũ sau khi bị thu hồi | Tiếp tục truy cập trái phép | Thời hạn thuộc tính và độ trễ thu hồi hữu hạn |
| R-AB-04 | Dùng endpoint danh sách, export hoặc trường lồng nhau | Lộ hàng hoặc trường ngoài quyền | Cưỡng chế trên tập kết quả và từng trường |
| R-AB-05 | Thay trạng thái hồ sơ sau kiểm tra quyền | Ghi vào tài nguyên đã không còn đủ điều kiện | Liên kết quyết định với phiên bản và thao tác ghi |
| R-AB-06 | Dùng quyền rộng của dịch vụ thay quyền người dùng | Dịch vụ trở thành bên thực hiện thay trái phép | Kiểm soát actor, người ủy quyền và phạm vi ủy quyền |
| R-AB-07 | Lỗi bộ quyết định nhưng ứng dụng vẫn cho qua | Mất kiểm soát truy cập | Không cấp quyền khi không có quyết định hợp lệ |
| R-AB-08 | Cùng người sửa và tự công bố kết quả | Bỏ qua kiểm soát nghiệp vụ | Tách nhiệm vụ tại thời điểm công bố |

Hệ thống chọn các quy tắc nghiệp vụ minh họa sau:

| Chủ thể và hành động | Điều kiện cần | Phạm vi kết quả |
| --- | --- | --- |
| Học viên đọc hồ sơ | Thành viên còn hiệu lực, cùng tenant, đúng learner ID, hồ sơ PUBLISHED | Chỉ điểm và phản hồi công khai của mình |
| Giảng viên đọc hồ sơ | Thành viên còn hiệu lực, cùng tenant, đang được phân công học phần | Các trường phục vụ chấm và rà soát theo chính sách |
| Giảng viên sửa điểm | Đủ điều kiện phân công, hồ sơ DRAFT | Chỉ các trường được phép sửa; không đổi tenant hoặc chủ sở hữu |
| Người duyệt công bố | Có quyền duyệt học phần, hồ sơ REVIEWED, khác lastEditorId | Chuyển trạng thái theo luồng công bố |
| Người xuất báo cáo | Có quyền export riêng và phê duyệt phạm vi còn hiệu lực | Chỉ tenant, học phần, hàng và trường đã được duyệt |
| Quản trị thành viên | Có quyền quản lý thành viên | Không mặc nhiên có quyền đọc nội dung đánh giá |

Với hồ sơ RESTRICTED, thao tác đọc của cán bộ trong ví dụ yêu cầu bằng chứng xác thực mạnh có tuổi không quá 15 phút; công bố yêu cầu không quá 5 phút. Đây là ngưỡng giả định cho tình huống, không phải chuẩn mặc định cho mọi hệ thống.

“Xác thực mạnh” cần được ánh xạ sang các phương thức và claim mà hệ thống thực sự xác minh. Không kiểm tra một boolean “mfa=true” do client tự khai.

## 4. Đặc tả thuộc tính như một hợp đồng dữ liệu bảo mật

### 4.1. Mỗi thuộc tính cần có chủ sở hữu

Một danh mục thuộc tính nên nêu kiểu, nguồn, ai được thay đổi, phạm vi và thời hạn. Ví dụ:

| Thuộc tính | Nguồn có thẩm quyền | Kiểu và ý nghĩa | Quy tắc tin cậy |
| --- | --- | --- | --- |
| subject.id | Hệ thống định danh đã xác minh | ID ổn định của chủ thể | Không thay bằng ID tùy ý trong request |
| subject.membership | Sổ thành viên của tenant | Tenant, trạng thái, phiên bản | Quyền tenant được kiểm tra trên bản ghi còn hiệu lực |
| subject.courseAssignments | Sổ phân công học phần | Tập quan hệ có thời gian hiệu lực | Không suy ra chỉ từ tên vai trò “giảng viên” |
| authentication.strength | Kết quả xác thực được xác minh | Mức/phương thức có định nghĩa | Kiểm tra nguồn, đối tượng nhận và ngữ nghĩa claim |
| authentication.authenticatedAt | Sự kiện xác thực phù hợp | Thời điểm UTC | Không thay bằng thời điểm refresh token hoặc thời điểm mở trang |
| resource.tenantId | Kho dữ liệu sở hữu hồ sơ | ID tenant | Không lấy tenant của tài nguyên từ body để quyết định |
| resource.state, version | Bản ghi nghiệp vụ | Enum và số phiên bản | Dùng trong cả kiểm tra quyền và điều kiện ghi |
| delegation.scope | Kho phê duyệt hoặc bằng chứng ủy quyền hợp lệ | Người ủy quyền, actor, hành động, tài nguyên, hạn dùng | Phải gắn với đúng mục đích và bên nhận |
| environment.now | Đồng hồ máy chủ được kiểm soát | Thời gian UTC | Không dùng giờ do client cung cấp để kéo dài quyền |

Nếu thuộc tính đi qua token hoặc thông điệp ký số, chữ ký chỉ là một phần của việc xác minh. Cần kiểm tra bên phát hành, bên nhận, thời hạn, phạm vi và ánh xạ claim. Một token hợp lệ về mật mã vẫn có thể chứa quyền đã cũ hoặc không dành cho dịch vụ hiện tại.

Định danh tài nguyên trong request có thể được dùng để tìm đối tượng. Các thuộc tính để ra quyết định phải lấy từ đối tượng thật hoặc bằng chứng đáng tin gắn đúng đối tượng đó. Không cho phép client ghi đè chúng bằng cùng tên trường.

### 4.2. Thuộc tính thiếu, sai kiểu và chưa biết

Chính sách cần phân biệt:

- Thuộc tính tồn tại và có giá trị không đáp ứng điều kiện.
- Thuộc tính không có.
- Nguồn thuộc tính không truy cập được.
- Dữ liệu sai kiểu, enum không biết hoặc thời điểm không hợp lệ.
- Dữ liệu có mặt nhưng quá cũ so với hành động yêu cầu.

Ví dụ, classification thiếu không được mặc định thành INTERNAL. Một timestamp parse lỗi không được biến thành “vừa xác thực xong”. Danh sách phân công không tải được không được hiểu là mọi học phần đều hợp lệ.

Nếu thuộc tính là điều kiện bắt buộc của quyền đang xét, không có giá trị đáng tin thì không được cấp quyền. Có thể biểu diễn kết quả là không xác định hoặc từ chối theo hợp đồng; điều quan trọng là điểm thực thi không diễn giải lỗi thành cho phép.

Với thời gian, cần quy định biên. Trong ví dụ, bằng chứng còn mới khi tuổi không âm và không lớn hơn ngưỡng đã chọn. Timestamp tương lai ngoài sai lệch đồng hồ được cho phép phải bị xử lý như dữ liệu không hợp lệ, không làm tuổi xác thực âm rồi được chấp nhận.

## 5. Viết chính sách có ngữ nghĩa rõ ràng

### 5.1. Không suy ra quyền từ một thuộc tính riêng lẻ

Ví dụ một quy tắc đọc dành cho giảng viên, viết dưới dạng mã giả:

~~~text
permit assessment.read when:
    subject.active == true
    and membership.active == true
    and membership.tenantId == resource.tenantId
    and subject.hasRole("INSTRUCTOR", resource.tenantId)
    and assignedToCourse(subject.id, resource.courseId) == true
    and resource.classification is a known value
    and (
        resource.classification == INTERNAL
        or (
            resource.classification == RESTRICTED
            and authentication.strength satisfies STAFF_STRONG
            and 0 <= authentication.ageSeconds <= 900
        )
    )
~~~

Đây chỉ là một quy tắc cho phép, không phải toàn bộ chính sách. Các thuộc tính active, role, membership và phân công phải tuân theo danh mục nguồn ở trên. Cấu trúc if/and/or cần được kiểm thử để tránh một nhánh làm mất điều kiện tenant hoặc trạng thái.

Đối với công bố, bổ sung điều kiện:

~~~text
permit grade.publish when:
    commonTenantAndMembershipConditions
    and canApproveCourse(subject.id, resource.courseId)
    and resource.state == REVIEWED
    and subject.id != resource.lastEditorId
    and authentication.strength satisfies PUBLISH_STRONG
    and 0 <= authentication.ageSeconds <= 300
~~~

So sánh với lastEditorId phải sử dụng người thực sự sửa gần nhất theo dữ liệu nghiệp vụ. Khi có dịch vụ sửa thay người dùng, lưu cả actor và người chịu trách nhiệm nghiệp vụ để không vô tình vượt yêu cầu tách nhiệm vụ.

### 5.2. Quy định cách kết hợp nhiều quy tắc

Một bộ chính sách có thể tạo các kết quả:

| Kết quả | Ý nghĩa |
| --- | --- |
| Permit | Có quy tắc cho phép với đủ dữ kiện |
| Deny | Có quy tắc cấm áp dụng |
| NotApplicable | Quy tắc không áp dụng cho yêu cầu này |
| Indeterminate | Không quyết định được do lỗi, thiếu dữ kiện hoặc biểu thức không hợp lệ |

Hệ thống mẫu chọn cách kết hợp cho tập chính sách áp dụng:

1. Có Deny thì kết quả cuối là Deny.
2. Nếu không có Deny nhưng có Indeterminate thì không cho phép; trả kết quả Indeterminate cho điểm thực thi.
3. Nếu không có hai kết quả trên và có ít nhất một Permit thì kết quả là Permit.
4. Chỉ có NotApplicable hoặc không có quy tắc cho phép thì kết quả cuối là Deny.

Nếu không xác định được bộ chính sách nào cần áp dụng, kết quả cũng không được là Permit. Quy tắc mặc định từ chối giúp một action mới không tự mở quyền vì chưa được cấu hình.

Các cách kết hợp khác có thể hợp lệ ở thiết kế khác. Tuy nhiên, phải mô tả rõ ưu tiên, phạm vi áp dụng và xử lý lỗi; không để mỗi thư viện hoặc mỗi nhóm tự chọn. Không nên dùng thứ tự file ngẫu nhiên như một cơ chế ưu tiên ngầm.

### 5.3. Permit có thể kèm nghĩa vụ bắt buộc

Một quyết định có thể yêu cầu:

~~~yaml
decision:
  result: Permit
  policyVersion: abac-demo-v3
  obligations:
    - type: FIELD_PROJECTION
      fields:
        - score
        - publicFeedback
    - type: SECURITY_AUDIT
      event: ASSESSMENT_READ
~~~

Điểm thực thi phải hiểu và hoàn thành các nghĩa vụ bắt buộc trước khi phát hành dữ liệu hoặc hoàn tất hành động tương ứng. Nếu không hỗ trợ FIELD_PROJECTION thì không được trả toàn bộ đối tượng để “tạm cho chạy”.

Việc nhận Permit không kết thúc trách nhiệm bảo mật. Dữ liệu đầu ra, nghĩa vụ audit và điều kiện cập nhật vẫn phải tuân theo hợp đồng quyết định.

## 6. Xác định nơi ra quyết định và nơi thực thi

Bốn vai trò kiến trúc thường dùng khi mô tả ABAC:

| Vai trò | Trách nhiệm |
| --- | --- |
| PAP — Policy Administration Point | Soạn, phê duyệt, phiên bản hóa và phát hành chính sách |
| PIP — Policy Information Point | Cung cấp thuộc tính hoặc thông tin cần đánh giá |
| PDP — Policy Decision Point | Đánh giá chính sách trên bộ dữ kiện |
| PEP — Policy Enforcement Point | Chặn hoặc cho thao tác tiếp tục và thực hiện nghĩa vụ |

Các vai trò không bắt buộc là bốn dịch vụ riêng. Dù triển khai cùng tiến trình hay qua mạng, yêu cầu vẫn phải chỉ ra ai sở hữu từng trách nhiệm.

~~~mermaid
flowchart LR
    C["Client"] --> S["API / nghiệp vụ với PEP"]
    S -->|"Chủ thể, action, resource reference"| D["PDP"]
    D --> I["PIP: thành viên, phân công, ngữ cảnh"]
    D --> P["Chính sách đã phát hành từ PAP"]
    S --> R["Kho tài nguyên có tenant và version"]
    D -->|"Quyết định và nghĩa vụ"| S
    S --> O["Kết quả được lọc / thao tác có điều kiện"]
    S --> A["Audit đã giảm thiểu dữ liệu"]
~~~

PEP phải có mặt ở nơi thực sự trả dữ liệu hoặc tạo tác động, bao gồm API, xử lý thông điệp và tác vụ nền. Ẩn nút trong giao diện chỉ cải thiện trải nghiệm; người dùng vẫn có thể gọi API trực tiếp.

Trong một kiến trúc dịch vụ, cần nêu có tin cậy quyết định từ bên gọi hay đánh giá lại. Nếu truyền một bằng chứng quyết định, nó phải gắn đúng chủ thể, actor, action, tài nguyên, phiên bản, thời hạn và bên nhận. Không chấp nhận một header “authorized=true” do client hoặc một dịch vụ không được ủy quyền tự gửi.

PEP phải giới hạn thời gian đợi PDP. Trong tình huống mẫu, hết thời gian hoặc không có kết quả hợp lệ thì dừng thao tác và trả lỗi dịch vụ phù hợp; không chuyển sang chế độ cho phép mặc định. Việc chọn timeout cụ thể phải gắn với mục tiêu hiệu năng và tính sẵn sàng của sản phẩm.

## 7. Cưỡng chế trên hàng, trường và thao tác tổng hợp

### 7.1. Quyền đọc một hồ sơ khác quyền đọc một danh sách

Một endpoint danh sách có thể trả dữ liệu của nhiều chủ thể. Yêu cầu “kiểm tra quyền với ID đầu tiên” không bao phủ các hàng còn lại.

Trong tình huống mẫu, danh sách của học viên phải giới hạn theo tenant, learner ID và trạng thái PUBLISHED, sau đó chỉ chiếu các trường cho phép. Phân trang, tổng số bản ghi, biểu đồ và kết quả tìm kiếm cũng phải tính trên phạm vi được phép. Không để count hoặc facet làm lộ hồ sơ mà các hàng đã bị ẩn.

Có thể đưa điều kiện lọc vào truy vấn hoặc đánh giá từng đối tượng trong một tập hữu hạn. Cần chứng minh rằng tập hàng được trả không rộng hơn chính sách. Nếu một bộ dịch chính sách không hỗ trợ biểu thức nào đó, phải từ chối hoặc dùng đường xử lý đã được chứng minh tương đương; không tự bỏ điều kiện khó dịch.

Đọc dữ liệu rộng rồi lọc sau có thể vẫn làm lộ qua cache, debug hoặc telemetry. Thiết kế cần giảm dữ liệu đi qua ranh giới không cần thiết và kiểm soát đường xử lý nội bộ.

### 7.2. Đọc và ghi từng trường là các quyền khác nhau

Quyền đọc hồ sơ không tự bao gồm quyền đọc internalReview hoặc dữ liệu liên hệ của học viên. Quyền sửa điểm không bao gồm sửa tenantId, learnerId, courseId hay trạng thái công bố.

Danh sách trường được phép ghi phải được cưỡng chế ở máy chủ. Nếu client gửi thêm trường nhạy cảm, hệ thống phải từ chối hoặc xử lý theo hợp đồng API đã công bố; không bind toàn bộ body vào đối tượng lưu trữ rồi hy vọng chính sách cấp đối tượng đã đủ.

Các trường lồng nhau, resolver GraphQL và tài nguyên liên kết cần cùng sự chú ý. Quyền với hồ sơ không mặc nhiên là quyền với mọi đối tượng được tham chiếu từ hồ sơ đó.

### 7.3. Export và xử lý hàng loạt cần hợp đồng riêng

Trong ví dụ, grade.export là action riêng, có phê duyệt phạm vi và mục đích từ nguồn tin cậy. Tham số purpose do client gửi chỉ là thông tin xin phép; nó không chứng minh phê duyệt.

Yêu cầu export cần xác định:

- Tenant, học phần, hàng và trường thuộc phạm vi được duyệt.
- Cách xử lý khi một phần dữ liệu không được phép.
- Thời điểm đánh giá quyền khi tạo job, khi job chạy và khi tải kết quả.
- Thời hạn giữ file và cơ chế ngăn người khác tải bằng cách chia sẻ ID.
- Hành vi khi quyền bị thu hồi trước khi job kết thúc.

Tình huống mẫu chọn từ chối toàn bộ một lệnh ghi hàng loạt nếu có phần tử không được phép; không ghi một phần ngoài ý muốn. Export chỉ tạo dữ liệu theo phạm vi được phép và phải kiểm tra quyền tải ở thời điểm tải.

Một liên kết ký sẵn có thể tiếp tục cấp khả năng tải đến khi hết hạn. Nếu nó không hỗ trợ kiểm tra lại và thu hồi trong giới hạn đã cam kết, cần chọn cơ chế tải khác hoặc điều chỉnh yêu cầu một cách minh bạch. Không tuyên bố đã thu hồi quyền trong khi file vẫn công khai hoặc liên kết còn dùng được.

## 8. Cache, độ mới và thu hồi quyền

### 8.1. Phân biệt cache thuộc tính với cache quyết định

Cache thuộc tính lưu dữ kiện như thành viên hoặc phân công. Cache quyết định lưu kết quả cho một tổ hợp chủ thể, action, tài nguyên và ngữ cảnh. Hai loại có thể có thời hạn khác nhau, nhưng tổng hành vi phải đáp ứng yêu cầu thu hồi.

Hệ thống mẫu đặt mục tiêu: sau khi việc thu hồi thành viên hoặc phân công được commit tại nguồn có thẩm quyền, không cho phép quyết định mới dựa vào quyền đó sau tối đa 60 giây. Mốc 60 giây là yêu cầu minh họa, cần được chứng minh từ kiến trúc; chỉ đặt TTL bằng 60 giây ở một lớp chưa đủ.

Nếu cache nhiều tầng tự làm mới tuổi khi sao chép dữ liệu cũ, tuổi thực có thể vượt giới hạn. Dữ kiện phải giữ thời điểm quan sát, thời điểm hiệu lực hoặc version của nguồn; sao chép từ cache không được biến dữ liệu cũ thành mới.

### 8.2. Khóa và thời hạn cache phải bao phủ mọi phụ thuộc

Một cache chỉ dùng subject ID và resource ID có thể trả nhầm quyền giữa action đọc và export, giữa hai tenant, hoặc giữa các actor ủy quyền khác nhau.

Khóa hoặc điều kiện kiểm tra cache cần bao phủ các dữ kiện ảnh hưởng quyết định, chẳng hạn:

- Chủ thể, realm và tenant được xét.
- Actor và phạm vi ủy quyền nếu có.
- Action cụ thể, tài nguyên và phiên bản liên quan.
- Phiên bản chính sách và phiên bản thuộc tính bảo mật.
- Mức xác thực, thời điểm xác thực và ngữ cảnh có hiệu lực.

Nếu không thể biểu diễn một phụ thuộc thay đổi an toàn trong cache, có thể không cache quyết định đó. Không chọn khóa ngắn hơn chỉ để tăng tỷ lệ cache hit.

Thời điểm hết hiệu lực của kết quả không được muộn hơn ràng buộc sớm nhất:

~~~text
decision.validUntil <= min(
    thời hạn thuộc tính dùng để quyết định,
    thời hạn bằng chứng ủy quyền,
    thời điểm hết độ mới của xác thực,
    biên thời gian của điều kiện môi trường,
    thời hạn cache theo chính sách
)
~~~

Ví dụ, bằng chứng xác thực đã gần hết ngưỡng 5 phút không được tạo một quyết định công bố còn sống thêm 5 phút tính từ lúc đánh giá. Phải giữ mốc thời gian gốc.

### 8.3. Thu hồi có phạm vi thực tế

Thu hồi quyền có thể ngăn lần đọc mới nhưng không thu lại được nội dung đã tải về. Với stream, job và file export, cần định nghĩa điểm kiểm tra tiếp theo, cách hủy và phần dữ liệu có thể đã được phát hành.

Không dùng thông báo vô hiệu hóa cache như bảo đảm duy nhất nếu thông báo có thể thất lạc. Cần có giới hạn độ cũ hoặc cơ chế đồng bộ đủ để giữ cam kết. Khi không xác nhận được trạng thái đáng tin cho hành động nhạy cảm, dừng cấp quyền theo hợp đồng lỗi đã chọn.

## 9. Ngăn sai lệch giữa kiểm tra quyền và thực hiện thao tác

**TOCTOU — time of check to time of use** là khoảng cách giữa lúc kiểm tra điều kiện và lúc sử dụng kết quả. Ví dụ, giảng viên được phép sửa một hồ sơ DRAFT ở version 12; trước khi ghi, người khác chuyển hồ sơ sang PUBLISHED ở version 13.

Nếu ứng dụng vẫn cập nhật theo ID mà không kiểm tra phiên bản, quyền vừa đánh giá không còn gắn với trạng thái được dùng. Một cách biểu diễn điều kiện ghi:

~~~sql
UPDATE assessment
SET score = :newScore,
    last_editor_id = :actorId,
    version = version + 1
WHERE id = :resourceId
  AND tenant_id = :authorizedTenant
  AND state = 'DRAFT'
  AND version = :authorizedVersion;
~~~

Đây là ví dụ điều kiện dữ liệu, không thay thế PDP hoặc toàn bộ giao dịch nghiệp vụ. Nếu không cập nhật được hàng nào, không được tự thử lại bằng cách bỏ tenant, state hay version; cần đọc và đánh giá lại hoặc trả xung đột theo hợp đồng.

Những điều kiện liên quan đến cùng kho dữ liệu có thể được bảo đảm bằng giao dịch, khóa hoặc kiểm tra phiên bản phù hợp. Với thuộc tính nằm ở dịch vụ khác, cần xác định mô hình nhất quán và độ trễ được chấp nhận; không giả định một giao dịch cục bộ đã đóng mọi khoảng cạnh tranh.

Trong ví dụ, độ trễ thu hồi quyền bên ngoài vẫn chịu giới hạn 60 giây đã công bố. Nếu một hành động cần thu hồi có hiệu lực tức thời tại commit, phải thiết kế cơ chế phối hợp tương ứng và có bằng chứng; không chỉ đổi câu mô tả thành “kiểm tra lại”.

Đối với công bố kết quả, quy tắc khác lastEditorId và state REVIEWED phải được kiểm tra trên trạng thái được commit. Đổi người chịu trách nhiệm trong request hoặc dùng tài khoản dịch vụ không được vô hiệu hóa tách nhiệm vụ.

## 10. Ủy quyền và phân biệt người dùng với dịch vụ

Khi một dịch vụ xử lý thay người dùng, có thể có ít nhất hai danh tính:

| Danh tính | Ý nghĩa |
| --- | --- |
| Subject nghiệp vụ | Người mà quyền truy cập đang được đánh giá |
| Actor thực thi | Dịch vụ hoặc người đang thực hiện yêu cầu |
| Người ủy quyền, nếu khác subject | Bên đã cấp một phạm vi thực hiện thay |

Cần mô tả rõ trường hợp nào hệ thống dùng quyền của dịch vụ, trường hợp nào dùng phạm vi ủy quyền và trường hợp nào cần điều kiện của cả hai. Trong ví dụ export thay học viên, quyền kỹ thuật đọc kho dữ liệu của worker không tự trở thành quyền xuất mọi hồ sơ.

Một hợp đồng an toàn cho tác vụ thực hiện thay có thể yêu cầu actor được phép làm loại tác vụ đó, bằng chứng ủy quyền còn hiệu lực, action và tài nguyên nằm trong phạm vi được cấp, đồng thời các điều kiện nghiệp vụ áp dụng vẫn đạt. Việc ủy quyền không được mở rộng phạm vi chỉ vì worker có tài khoản cơ sở dữ liệu rộng.

Job nền cần lưu tham chiếu subject, actor, tenant, scope và nguồn phê duyệt; không lưu mật khẩu hay token dài hạn của người dùng để “giữ quyền”. Khi chạy trễ, đánh giá lại theo chính sách dành cho thời điểm thực thi.

Nếu có truy cập khẩn cấp, cần một chính sách ngoại lệ riêng: người được quyền kích hoạt, lý do có thể kiểm chứng, thời hạn, phạm vi, audit và rà soát sau đó. Không thêm một điều kiện “admin=true thì bỏ mọi kiểm tra” làm đường vòng không quản lý.

## 11. Quản trị chính sách, audit và hành vi lỗi

### 11.1. Chính sách là thành phần có vòng đời

Người sửa policy có thể làm thay đổi quyền của nhiều người dùng. Do đó cần quyền riêng cho quản trị chính sách, lịch sử thay đổi, phê duyệt tương ứng mức rủi ro và khả năng quay lại phiên bản trước.

Bản chính sách cần có ID, version, phạm vi action/resource, phiên bản lược đồ thuộc tính và thời điểm có hiệu lực. Một yêu cầu không được vô tình đánh giá nửa bộ quy tắc cũ và nửa bộ mới vì đang cập nhật.

Trước phát hành, cần kiểm tra cú pháp, kiểu thuộc tính và các vector cho phép/từ chối quan trọng. Có thể đánh giá song song một bản ứng viên để so sánh kết quả; bản ứng viên không được cấp quyền thật chỉ vì đang ở chế độ thử.

Khi rollback, phải xét cả cache và schema thuộc tính. Khôi phục file policy nhưng giữ cache Permit của phiên bản vừa thu hồi không tạo ra trạng thái nhất quán.

### 11.2. Audit đủ giải thích nhưng không làm lộ dữ liệu

Một sự kiện quyết định có thể bao gồm:

~~~json
{
  "eventType": "AUTHORIZATION_DECISION",
  "requestId": "server-demo-request",
  "subjectRef": "subject-demo",
  "actorRef": "service-demo",
  "tenantRef": "tenant-demo-a",
  "action": "grade.publish",
  "resourceRef": "assessment-demo-01",
  "resourceVersion": 12,
  "policyVersion": "abac-demo-v3",
  "decision": "Deny",
  "reasonCode": "SEPARATION_OF_DUTIES"
}
~~~

Ví dụ chỉ chứa dữ liệu giả. Mã lý do nội bộ giúp điều tra, nhưng không nhất thiết được trả nguyên vẹn cho client. Không ghi toàn bộ hồ sơ, điểm, nhận xét, token hoặc toàn bộ tập thuộc tính vào log chỉ để giải thích một quyết định.

Phải xác định dữ liệu nào cần giữ để tái hiện quyết định: version policy, version dữ kiện hoặc tham chiếu đến snapshot được bảo vệ. Chỉ giữ version policy mà không biết thuộc tính lúc đó có thể không đủ giải thích.

Nếu audit là nghĩa vụ bắt buộc, yêu cầu phải nói khi nào được coi là đã hoàn thành. Tình huống mẫu đòi hỏi sự kiện được ghi bền vững hoặc đưa vào outbox bền vững được chấp nhận trước khi phát hành dữ liệu nhạy cảm hay commit tác động liên quan. Nếu không thực hiện được nghĩa vụ, không tiếp tục trả dữ liệu. Không yêu cầu phải đợi hệ thống phân tích tập trung xử lý xong sự kiện nếu hợp đồng đã cho phép outbox.

### 11.3. Phân loại lỗi mà vẫn giữ mặc định không cấp quyền

| Tình huống | Hành vi yêu cầu |
| --- | --- |
| Không có policy cho action mới | Từ chối |
| Thuộc tính bắt buộc thiếu, sai kiểu hoặc quá cũ | Không cấp quyền; ghi mã lỗi nội bộ phù hợp |
| PDP timeout hoặc trả cấu trúc không hợp lệ | Dừng thao tác; không dùng Permit mặc định |
| Nghĩa vụ lọc trường không được hỗ trợ | Không trả đối tượng đầy đủ |
| Version tài nguyên thay đổi trước ghi | Đánh giá lại hoặc trả xung đột; không bỏ điều kiện |
| Cache không xác nhận được version/quyền hiệu lực | Không dùng kết quả cũ ngoài hợp đồng |
| Audit bắt buộc không ghi được bền vững | Không hoàn tất thao tác được nghĩa vụ bảo vệ |

Từ chối do chính sách và lỗi hệ thống có thể dùng mã phản hồi khác theo hợp đồng API. Tuy nhiên, phản hồi công khai không được tiết lộ dữ liệu tài nguyên để giải thích vì sao người gọi không được xem. Có thể chọn 403 hoặc che sự tồn tại bằng 404 cho một số tài nguyên, miễn thực hiện nhất quán trên danh sách, chi tiết và tuyến liên quan.

## 12. Viết yêu cầu ABAC và truy vết đến tiêu chí kiểm thử

Một yêu cầu mẫu đầy đủ:

| Trường | Nội dung |
| --- | --- |
| ID | SR-ABAC-02 |
| Mục tiêu | Ngăn truy cập hồ sơ ngoài tenant được cấp |
| Rủi ro | R-AB-01, R-AB-02 |
| Phạm vi | Đọc, tìm kiếm, ghi, export và tải hồ sơ đánh giá |
| Nghĩa vụ | Chỉ cho phép khi tenant của tài nguyên khớp phạm vi tenant còn hiệu lực của chủ thể; điều kiện lấy từ nguồn tin cậy |
| Điểm cưỡng chế | PEP tại API và job; điều kiện dữ liệu ở nơi truy xuất hoặc cập nhật |
| Hành vi lỗi | Không xác nhận được tenant hoặc membership thì không cấp quyền |
| Bằng chứng | Ca sửa ID, tenant, alias, tác vụ nền, truy vấn danh sách và cache |
| Chủ sở hữu | Nhóm nghiệp vụ xác định phạm vi; nhóm định danh/quyền triển khai; nhóm dữ liệu bảo đảm điều kiện truy xuất |
| Giới hạn | Không thu hồi bản dữ liệu đã được người dùng tải hợp lệ |
| Ngoại lệ | Có phạm vi, người chịu trách nhiệm, thời hạn và kiểm soát bù được duyệt |

Một bộ yêu cầu cho tình huống có thể được tổ chức như sau:

| ID | Nghĩa vụ chính | Rủi ro và bằng chứng |
| --- | --- | --- |
| SR-ABAC-01 | Đầu vào quyết định gắn đúng subject, actor, action và tài nguyên | Chống thay danh tính/action; kiểm thử request bị sửa |
| SR-ABAC-02 | Cách ly tenant trên mọi đường truy cập | R-AB-01; kiểm thử chéo tenant và dữ liệu tổng hợp |
| SR-ABAC-03 | Nguồn, kiểu, hiệu lực và độ mới của thuộc tính có hợp đồng | R-AB-02, R-AB-03; giả mạo, null, enum lạ, dữ liệu cũ |
| SR-ABAC-04 | Ngữ nghĩa kết hợp và mặc định từ chối được cố định | R-AB-07; Permit/Deny/Indeterminate/NotApplicable |
| SR-ABAC-05 | Mọi đường tạo tác động có PEP và thực hiện nghĩa vụ | R-AB-04, R-AB-07; API trực tiếp, job, resolver |
| SR-ABAC-06 | Quyền theo hàng, trường, bulk và export có phạm vi | R-AB-04; count, projection, mass assignment, file tải |
| SR-ABAC-07 | Cache và thu hồi giữ giới hạn 60 giây của tình huống | R-AB-03; cache nhiều tầng, mất thông báo, token cũ |
| SR-ABAC-08 | Quyết định ghi gắn với trạng thái và version thực thi | R-AB-05; cạnh tranh cập nhật và điều kiện commit |
| SR-ABAC-09 | Phạm vi ủy quyền không bị mở rộng bởi actor | R-AB-06; worker và job chạy trễ |
| SR-ABAC-10 | Phát hành, kiểm thử và rollback policy có quản trị | R-AB-07; phiên bản, cache và schema |
| SR-ABAC-11 | Audit có thể giải thích quyết định và giảm thiểu dữ liệu | Điều tra sự cố; lỗi audit và kiểm tra dữ liệu ghi |
| SR-ABAC-12 | Tách nhiệm vụ và độ mới xác thực được cưỡng chế | R-AB-08; người sửa tự công bố và bằng chứng quá hạn |

Mỗi ID cần được nối với thiết kế và bằng chứng thực tế. Các mã trên là minh họa cấu trúc đặc tả, không phải bộ yêu cầu mặc định áp dụng cho mọi module hay sản phẩm.

## 13. Kế hoạch nghiệm thu: chứng minh quyền đúng cả khi có lỗi

Các ca sau là kế hoạch kiểm thử của tình huống, không phải kết quả đã thực hiện.

| Ca | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| AT-AB-01 | Học viên đọc hồ sơ PUBLISHED của mình | Chỉ nhận trường được phép |
| AT-AB-02 | Đổi learner ID hoặc resource ID sang người khác | Không nhận hồ sơ, trường hoặc số đếm ngoài quyền |
| AT-AB-03 | Giữ vai trò hợp lệ nhưng sửa tenant trong URL/body/header | Không vượt cách ly tenant |
| AT-AB-04 | Giảng viên cùng tenant nhưng không có phân công học phần | Bị từ chối dù có vai trò INSTRUCTOR |
| AT-AB-05 | Tự gửi role, membership, classification hoặc mfa trong body | Thuộc tính không được dùng thay nguồn có thẩm quyền |
| AT-AB-06 | Thiếu classification, enum lạ hoặc không tải được phân công | Không mặc định sang mức ít nhạy cảm hoặc phân công rộng |
| AT-AB-07 | Một Permit cạnh tranh với Deny hoặc Indeterminate | Kết quả đúng ngữ nghĩa kết hợp đã chọn |
| AT-AB-08 | Gọi action chưa khai báo policy | Bị từ chối mặc định |
| AT-AB-09 | Gọi API trực tiếp, resolver lồng nhau và tuyến job | Điểm thực thi vẫn bảo vệ dữ liệu và tác động |
| AT-AB-10 | Thử ghi thêm tenantId hoặc learnerId cùng trường score | Không sửa được trường ngoài quyền |
| AT-AB-11 | Tìm kiếm, phân trang và lấy tổng số | Chỉ phản ánh tập dữ liệu trong quyền |
| AT-AB-12 | Bộ dịch lọc không hỗ trợ một điều kiện policy | Không trả tập dữ liệu rộng hơn bằng cách bỏ điều kiện |
| AT-AB-13 | Dùng cache cho action, tenant hoặc actor khác | Không tái sử dụng Permit ngoài phạm vi |
| AT-AB-14 | Thu hồi membership khi các cache đang nóng, làm mất sự kiện vô hiệu hóa | Sau tối đa 60 giây không cấp quyết định mới dựa trên quyền cũ |
| AT-AB-15 | Bằng chứng xác thực ở đúng ngưỡng 300 giây và ngay sau ngưỡng khi công bố | Đúng biên thời gian đã định nghĩa; không kéo dài bằng refresh token |
| AT-AB-16 | Chuyển hồ sơ từ DRAFT sang trạng thái khác giữa kiểm tra và ghi | Không ghi theo quyết định cũ; điều kiện version/state giữ hiệu lực |
| AT-AB-17 | Người vừa sửa kết quả tự công bố, kể cả qua worker | Không vượt tách nhiệm vụ bằng actor dịch vụ |
| AT-AB-18 | Thu hồi quyền sau khi tạo export nhưng trước khi chạy hoặc tải | Xử lý theo điểm kiểm tra và cam kết thu hồi của luồng |
| AT-AB-19 | PDP timeout, mất nguồn thuộc tính hoặc nghĩa vụ projection lỗi | Không trả dữ liệu hoặc tạo tác động trái hợp đồng |
| AT-AB-20 | Audit bắt buộc không có nơi ghi bền vững | Không hoàn tất thao tác được nghĩa vụ bảo vệ |
| AT-AB-21 | Phát hành policy mới trong khi có request và cache cũ | Mỗi quyết định dùng một phiên bản hợp lệ, không trộn ngữ nghĩa |
| AT-AB-22 | Rollback policy và dùng token/thuộc tính schema khác phiên bản | Không dùng Permit cũ hoặc dữ kiện không tương thích |

Cần có cả ca được phép để chứng minh chính sách không vô tình chặn toàn bộ người dùng. Khi có quyền đọc một phần, kiểm tra chính xác các trường vắng mặt và các tác động không xảy ra; chỉ nhìn mã HTTP là chưa đủ.

Đối với ca thu hồi, đo từ thời điểm commit tại nguồn đến quyết định mới cuối cùng còn dùng quyền cũ, qua mọi điểm truy cập liên quan. Đối với TOCTOU, điều khiển thứ tự hai giao dịch để chứng minh cửa sổ cạnh tranh được xử lý, thay vì chỉ chạy tuần tự.

## 14. Duy trì ABAC trong vòng đời phát triển

Ở giai đoạn phân tích, chủ sở hữu nghiệp vụ xác định ai được làm gì với tài nguyên nào và tác động của việc cấp sai. Ở giai đoạn thiết kế, nhóm chuyển các điều kiện thành thuộc tính có nguồn, policy có ngữ nghĩa và điểm thực thi rõ ràng.

Khi triển khai, lược đồ thuộc tính, action và obligation cần có quản lý phiên bản. Khi nghiệm thu, nối từng rủi ro với ca kiểm thử và dữ liệu quan sát. Trong vận hành, theo dõi tỷ lệ lỗi PDP/PIP, quyết định không xác định, độ trễ thu hồi, số lần từ chối bất thường và tác động lên người dùng hợp lệ.

Những thay đổi cần đánh giá lại gồm thêm tenant, thêm action, đổi nơi giữ dữ liệu thành viên, mở tuyến export, thay phiên bản token, thêm cache hoặc cho phép dịch vụ thực hiện thay người dùng. Một thuộc tính mới có cùng tên nhưng khác nghĩa cũng là thay đổi hợp đồng bảo mật.

ABAC hữu ích khi chính sách diễn đạt được quyền theo bối cảnh mà vẫn giải thích và kiểm chứng được. Yêu cầu hoàn chỉnh phải nối được mục tiêu bảo vệ với thuộc tính đáng tin, quy tắc rõ nghĩa, nơi cưỡng chế, độ trễ thu hồi và bằng chứng rằng dữ liệu không đi ra ngoài phạm vi đã cấp.
