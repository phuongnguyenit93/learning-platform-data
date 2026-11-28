# System scope

Trong chương **Inventory và ownership**, system scope là phạm vi hệ thống được xác định để tổ chức kiểm kê và quản trị truy cập đặc quyền. Phạm vi này làm rõ những tài nguyên, danh tính, credential và đường quản trị nào liên quan đến một hệ thống, cùng ranh giới trách nhiệm với các hệ thống khác.

Đối với quản lý truy cập đặc quyền (PAM), một danh sách máy chủ chưa đủ mô tả system scope. Quyền quản trị có thể đến từ nhóm danh tính, nền tảng triển khai, tài khoản dịch vụ, kho credential, hệ thống sao lưu hoặc kênh hỗ trợ của bên thứ ba. Nếu bỏ qua các quan hệ đó, inventory có thể trông đầy đủ nhưng vẫn thiếu những đường truy cập có tác động lớn.

Bài học hướng đến việc xây dựng phạm vi đủ rõ để kiểm kê quyền, xác định ownership, áp dụng đặc quyền tối thiểu, JIT/JEA, vault, luân chuyển credential và lưu bằng chứng phục vụ kiểm toán hoặc ứng phó sự cố. Các mô hình dữ liệu trong bài là minh họa, không phải schema của một sản phẩm cụ thể.

## 1. Kết quả cần đạt

Sau bài học, người học có thể:

- Mô tả phạm vi hệ thống bằng mục đích, ranh giới và tập đối tượng có định danh rõ ràng.
- Phân biệt phạm vi quản trị PAM với danh mục tài sản, phạm vi discovery và phạm vi cấp quyền.
- Ghi nhận tài nguyên trực tiếp, phụ thuộc dùng chung, phần loại trừ và phần chưa xác minh.
- Liên kết hệ thống với danh tính, credential, quyền và chủ thể chịu trách nhiệm.
- Quản lý thay đổi phạm vi khi hạ tầng, ownership hoặc đường truy cập thay đổi.
- Đo độ bao phủ mà không bỏ qua tài nguyên lỗi, dữ liệu cũ hoặc phụ thuộc chưa rõ chủ sở hữu.

## 2. System scope trả lời những câu hỏi nào?

Một scope hữu ích cần trả lời được:

1. Hệ thống phục vụ mục đích gì và có định danh quản lý nào?
2. Những tài nguyên nào được đưa vào phạm vi quản trị trực tiếp?
3. Những danh tính và đường quyền nào có thể tác động đến chúng?
4. Credential được cấp phát hoặc lưu ở đâu, do ai quản lý?
5. Hệ thống phụ thuộc vào những nền tảng hoặc bên cung cấp nào?
6. Ai chịu trách nhiệm cho từng quyết định và thay đổi liên quan?
7. Những phần nào đã xác minh, bị loại trừ có căn cứ hoặc còn chưa biết?

Có thể diễn đạt phạm vi bằng một câu khởi đầu:

> Scope `sys-orders-prod` bao gồm các tài nguyên vận hành dịch vụ xử lý đơn hàng production của Acme, danh tính quản trị và dịch vụ có quyền trên các tài nguyên đó, cùng quan hệ tới nền tảng danh tính, vault, triển khai và sao lưu liên quan. Phần nền tảng dùng chung được liên kết với scope của đội chịu trách nhiệm thay vì mặc nhiên chuyển toàn bộ trách nhiệm quản trị sang đội orders.

Câu này cần được bổ sung bằng dữ liệu có thể đối chiếu. Những cụm như “các máy liên quan” hoặc “mọi thứ của đội orders” không đủ để quyết định một đối tượng cụ thể có thuộc phạm vi hay không.

### 2.1. Phân biệt các loại phạm vi

| Khái niệm | Mục đích | Không tự tạo ra điều gì? |
|---|---|---|
| Danh mục tài sản toàn tổ chức | Biết tổ chức có những tài sản nào | Trách nhiệm và quan hệ PAM chi tiết cho từng hệ thống |
| System scope trong inventory PAM | Xác định đối tượng và quan hệ cần quản trị cho một hệ thống | Quyền truy cập trực tiếp cho mọi thành viên của hệ thống |
| Phạm vi discovery được phép | Xác định nơi và dữ liệu collector được thu thập | Quyền quét hoặc đọc mọi phụ thuộc được nhắc đến trong sơ đồ |
| Phạm vi grant JIT/JEA | Giới hạn quyền của một chủ thể trong một công việc | Quyền trên toàn bộ system scope |
| Phạm vi đánh giá hoặc kiểm toán | Xác định đối tượng và tiêu chí được kiểm tra | Bằng chứng rằng mọi phần ngoài phạm vi đều an toàn |

Một tài nguyên thuộc scope orders không có nghĩa mọi kỹ sư orders được quản trị tài nguyên đó. Một vault được ghi là phụ thuộc cũng không cho phép collector tự đọc secret bên trong. Các quyền thực thi vẫn phải được cấp theo cơ chế riêng.

### 2.2. Ranh giới mạng chỉ là một phần dữ liệu

Một subnet có thể chứa nhiều hệ thống. Một hệ thống có thể trải qua nhiều mạng, vùng triển khai hoặc dịch vụ bên ngoài. Địa chỉ IP, hostname và đường dẫn hiển thị có thể thay đổi hoặc được tái sử dụng.

Vì vậy, không dùng riêng dải IP hoặc tên thư mục làm định nghĩa hệ thống. Nên kết hợp định danh tài sản, miền quản lý, mục đích nghiệp vụ, môi trường, quan hệ triển khai và nguồn kiểm kê đáng tin cậy.

## 3. Những lớp cần xem xét trong phạm vi PAM

| Lớp | Ví dụ | Câu hỏi về phạm vi |
|---|---|---|
| Tài nguyên nghiệp vụ | Ứng dụng, cơ sở dữ liệu, workload xử lý đơn hàng | Đối tượng nào trực tiếp cung cấp chức năng của hệ thống? |
| Hạ tầng chứa hoặc vận hành | Máy chủ, cụm chạy workload, thiết bị mạng | Quyền ở lớp cha có thể tác động tới những scope nào? |
| Danh tính | Người quản trị, nhóm, service account, workload identity | Ai nhận quyền trực tiếp hoặc qua quan hệ nhóm? |
| Credential | Mật khẩu, API key, khóa và tham chiếu vault | Credential xác thực cho danh tính nào, ở những đích nào? |
| Kênh quản trị | Broker, cổng quản trị, API điều khiển, kênh hỗ trợ | Có đường nào đi ngoài cơ chế PAM dự kiến? |
| Cấp phát và triển khai | Pipeline, runner, công cụ cấu hình | Ai có thể thay workload hoặc chèn cấu hình đặc quyền? |
| Sao lưu và khôi phục | Tài khoản backup, kho bản sao, luồng restore | Ai có thể đọc dữ liệu hoặc khôi phục hệ thống theo cách vượt kiểm soát thường ngày? |
| Kiểm soát và bằng chứng | Nền tảng danh tính, audit log, giám sát phiên | Ai quản lý kiểm soát và liệu hệ thống có phụ thuộc vào chúng để vận hành an toàn? |

Không nhất thiết mọi đối tượng đều do một đội trực tiếp quản trị. Điều quan trọng là biết quan hệ, mức ảnh hưởng và đầu mối trách nhiệm. Nếu scope chỉ chứa phần chạy ứng dụng nhưng bỏ sót pipeline có thể triển khai mã vào production, inventory chưa phản ánh đầy đủ đường quản trị.

## 4. Phân loại quan hệ với hệ thống

Nên tách **quan hệ với scope** khỏi **trạng thái quản lý PAM** và **trạng thái thu thập dữ liệu**. Ba câu hỏi này khác nhau:

- Đối tượng có liên quan hoặc thuộc phạm vi này không?
- Đối tượng đã được quản lý theo yêu cầu PAM chưa?
- Có dữ liệu mới và đầy đủ về đối tượng không?

Một máy có thể chắc chắn thuộc phạm vi nhưng chưa onboard vào PAM và hiện đang không truy vấn được. Không đổi nó thành ngoài phạm vi để làm báo cáo đạt tỷ lệ cao hơn.

### 4.1. Các nhóm cần thể hiện rõ

| Nhóm quan hệ | Cách xử lý trong inventory |
|---|---|
| Tài nguyên trong phạm vi quản trị trực tiếp | Liệt kê định danh, ownership, trạng thái quản lý và bằng chứng hiện tại |
| Phụ thuộc dùng chung | Liên kết tới đối tượng hoặc scope chịu trách nhiệm; ghi đường ảnh hưởng và phần trách nhiệm giữa hai bên |
| Đối tượng ngoài phạm vi có căn cứ | Lưu lý do, người quyết định, thời điểm và điều kiện cần xem lại |
| Đối tượng nghi thuộc phạm vi nhưng chưa xác minh | Giữ trạng thái chờ xác minh, người xử lý và hạn xử lý theo chính sách |

Phân loại phụ thuộc dùng chung không có nghĩa loại rủi ro khỏi đánh giá. Ví dụ, nền tảng danh tính do đội khác quản lý vẫn có thể cấp quyền quản trị vào hệ thống orders.

Một hệ thống bên ngoài tổ chức có thể chỉ được quan sát qua giao diện tích hợp và cam kết trách nhiệm. Scope cần mô tả phần có thể quản trị và bằng chứng có thể nhận, thay vì coi toàn bộ hạ tầng của nhà cung cấp là tài sản được phép quét.

### 4.2. Căn cứ loại trừ và ngoại lệ là hai việc khác nhau

Một máy development có thể nằm ngoài scope production nếu ranh giới được xác minh rõ. Một máy production chưa đáp ứng yêu cầu PAM vẫn thuộc scope; trường hợp đó có thể cần xử lý hoặc ngoại lệ có thời hạn, không phải loại khỏi scope.

Tương tự, không truy vấn được máy là khoảng trống quan sát. Không có chủ sở hữu là khoảng trống ownership. Cả hai đều không tự chứng minh đối tượng nằm ngoài phạm vi.

Ngoại lệ cần ghi đối tượng, yêu cầu chưa đáp ứng, rủi ro, người chịu trách nhiệm, kiểm soát bổ sung và mốc xem lại. Nhãn ngoại lệ không làm quyền rộng hoặc credential chưa được quản lý trở nên ít ảnh hưởng hơn.

## 5. Xác định membership bằng định danh đáng tin cậy

### 5.1. Định danh hệ thống và tài nguyên

Nên có `system_id` ổn định và một phiên bản scope. Tài nguyên được nhận diện bằng định danh của nguồn quản lý thích hợp, kèm miền quản lý hoặc tenant để tránh trùng.

Ví dụ:

```text
system_id: sys-orders-prod
scope_version: 4
resource_authority: compute-acme
resource_id: vm-04c2
```

Tên hiển thị `orders-prod-02` giúp người đọc hiểu đối tượng nhưng không phải bằng chứng duy nhất. Nếu máy bị xóa rồi tạo lại, cần xác định đó là vòng đời tài sản mới hay cùng đối tượng được thay đổi. Không tự chuyển quan hệ quyền và ownership chỉ vì tên giống nhau.

### 5.2. Nhãn và selector

Nhãn như `service=orders` hoặc `environment=production` hỗ trợ tìm ứng viên. Tuy nhiên, nhãn có thể sai, cũ hoặc bị thay đổi bởi người có quyền triển khai.

Có hai cách quản lý membership thường cần phân biệt:

| Cách | Điểm mạnh | Điều cần kiểm soát |
|---|---|---|
| Danh sách tài nguyên đã chốt | Dễ xác định tập đối tượng của một phiên bản scope | Quy trình bổ sung/xóa khi hạ tầng thay đổi |
| Quy tắc chọn động | Phù hợp hạ tầng được tạo và hủy thường xuyên | Nguồn thuộc tính, quyền sửa nhãn, giới hạn miền và cơ chế đối soát |

Với scope động, nên lưu quy tắc và kết quả phân giải tại những thời điểm cần kiểm tra. Không chỉ lưu một selector rồi mất khả năng trả lời “những tài nguyên nào thuộc scope vào lúc xảy ra sự cố?”.

Tài nguyên mới khớp selector có thể được đưa vào luồng kiểm kê theo chính sách đã định, nhưng điều đó không tự tạo grant quản trị hoặc cho phép collector vượt phạm vi thu thập được giao. Nếu thuộc tính mâu thuẫn, cần giữ trạng thái chưa xác minh và điều tra nguồn thay vì chọn giá trị thuận tiện nhất.

### 5.3. Quan hệ cha–con

Một cơ sở dữ liệu của orders có thể nằm trên máy chủ cơ sở dữ liệu dùng chung. Scope ứng dụng cần chỉ rõ đối tượng con và liên kết tới đối tượng cha. Quyền quản trị máy chủ cha có thể ảnh hưởng đến nhiều cơ sở dữ liệu; quyền trên một cơ sở dữ liệu không nhất thiết cho phép quản trị cả máy chủ.

Khi thống kê, không cộng lẫn số máy, số cơ sở dữ liệu và số workload mà không nêu đơn vị. Một asset cha và hai đối tượng con có thể là ba bản ghi inventory nhưng không phải ba máy vật lý độc lập.

## 6. Gắn ownership theo loại trách nhiệm

Từ “owner” có thể che giấu nhiều trách nhiệm khác nhau. Cần làm rõ ai quyết định nhu cầu, ai vận hành và ai quản lý credential.

| Vai trò | Trách nhiệm có thể được giao |
|---|---|
| Chủ sở hữu hệ thống | Xác nhận mục đích, phạm vi nghiệp vụ và nhu cầu quyền liên quan |
| Chủ sở hữu kỹ thuật | Duy trì kiến trúc, tài nguyên, phụ thuộc và tác động thay đổi |
| Chủ sở hữu danh tính/tài khoản dịch vụ | Xác nhận mục đích, vòng đời và consumer của danh tính |
| Đơn vị quản lý credential | Bảo vệ, cấp phát, luân chuyển và xử lý sự cố credential theo thẩm quyền |
| Chủ sở hữu nền tảng dùng chung | Quản trị lớp hạ tầng hoặc dịch vụ ảnh hưởng tới nhiều hệ thống |
| Đơn vị quản trị PAM | Vận hành cơ chế kiểm soát, đối soát và bằng chứng theo phạm vi được giao |

Tổ chức có thể gộp hoặc tách vai trò, nhưng mỗi quyết định phải có đầu mối chịu trách nhiệm rõ. Trong mô hình minh họa, mỗi scope có một đầu mối chịu trách nhiệm chính và các vai trò kỹ thuật được liên kết theo chức năng.

Một đội đứng tên scope không tự được cấp quyền đọc toàn bộ secret của hệ thống. Người tạo tài khoản hoặc người chỉnh bản ghi gần nhất cũng không mặc nhiên là owner hợp lệ.

Nếu owner là một nhóm, cần có định danh nhóm, đầu mối đang hoạt động và cách phân công khi thay ca hoặc chuyển đội. Nếu owner rời tổ chức, quan hệ cần được rà soát và bàn giao; không chỉ đổi chuỗi tên trong inventory mà bỏ qua trách nhiệm cấp quyền và credential còn tồn tại.

### Phụ thuộc dùng chung cần trách nhiệm hai phía

Ví dụ, đội nền tảng quản lý vault, còn đội orders quản lý danh tính dịch vụ và danh sách consumer. Trước luân chuyển, cần biết ai cập nhật secret, ai cập nhật consumer, ai kiểm tra kết quả và ai xử lý nếu có lỗi.

Nếu chỉ ghi “vault thuộc đội nền tảng”, phần phụ thuộc vận hành của orders vẫn chưa được giải quyết. Ngược lại, giao mọi trách nhiệm vault cho orders chỉ vì họ dùng một secret là mô tả sai ranh giới.

## 7. Mô hình inventory tham khảo

Bản ghi sau là **YAML minh họa**, không phải cấu hình để thực thi truy cập hoặc discovery:

```yaml
system_id: sys-orders-prod
scope_version: 4
scope_state: active
purpose: Van hanh dich vu xu ly don hang production
management_domain: acme
environment: production
accountability:
  system_owner_ref: team-orders-service
  technical_owner_ref: team-orders-operations
  ownership_confirmation_ref: OWN-204
membership:
  mode: fixed_set
  direct_resources:
    - authority: compute-acme
      resource_id: vm-04c2
      resource_type: virtual_machine
    - authority: compute-acme
      resource_id: vm-77b1
      resource_type: virtual_machine
    - authority: database-acme
      resource_id: db-orders
      resource_type: database
    - authority: jobs-acme
      resource_id: job-orders-backup
      resource_type: backup_job
shared_dependencies:
  - dependency_ref: identity-platform-acme
    responsible_scope_ref: sys-identity-platform
    relationship: can_issue_privileged_identity
  - dependency_ref: vault-prod-acme
    responsible_scope_ref: sys-credential-platform
    relationship: supplies_service_credentials
  - dependency_ref: runner-shared-acme
    responsible_scope_ref: sys-delivery-platform
    relationship: can_deploy_to_system
identity_inventory_ref: inventory-identities-orders-prod
credential_metadata_ref: inventory-credential-refs-orders-prod
scope_decision_ref: SCOPE-118
review_due_at: '2026-12-10T17:00:00+07:00'
```

`scope_state: active` chỉ biểu thị phiên bản phạm vi đang được sử dụng trong mô hình này. Nó không chứng minh mọi tài nguyên đã onboard, mọi owner còn hợp lệ hoặc mọi credential đã được luân chuyển.

Các trường tham chiếu inventory cần trỏ tới dữ liệu được kiểm soát và có xuất xứ. Bản ghi không chứa mật khẩu, token hoặc private key. Mỗi tài nguyên cần có trạng thái quản lý và quan sát riêng, thay vì suy từ trạng thái chung của scope.

### Quan hệ danh tính và quyền

Không nên chỉ thêm danh sách username vào scope. Một bản ghi quyền cần liên kết:

```text
Danh tính + nguồn thẩm quyền
    → vai trò/nhóm/ủy quyền
    → tập thao tác
    → tài nguyên đích
    → thời gian quan sát và bằng chứng
```

Một danh tính có thể có quyền ở nhiều scope. Nên giữ cùng định danh gốc và các quan hệ tới từng scope, thay vì tạo các tài khoản giả riêng trong inventory. Khi quyền của một nhóm dùng chung thay đổi, cần đánh giá mọi scope có liên quan.

### Quan hệ credential

Credential cần liên kết với danh tính, tài nguyên xác thực, consumer và đơn vị quản lý. Credential ở vault dùng chung có thể phục vụ một hoặc nhiều hệ thống. Nơi lưu secret không tự quyết định hệ thống nào chịu trách nhiệm cho nhu cầu sử dụng và phụ thuộc luân chuyển.

## 8. Quy trình xây dựng system scope

### Bước 1: Mô tả mục đích và ranh giới ban đầu

Ghi chức năng nghiệp vụ, môi trường, miền quản lý và đầu mối chịu trách nhiệm. Nêu loại tài nguyên và đường quản trị dự kiến, cùng giả định cần xác minh.

Không bắt đầu bằng kết luận rằng danh sách hiện có đã đầy đủ. Nó chỉ là tập ứng viên cho bước đối chiếu.

### Bước 2: Đối chiếu nguồn tài sản và trạng thái quan sát

So sánh danh mục quản lý với dữ liệu triển khai và kết quả discovery được phép. Tách tài nguyên đã xác minh, ứng viên chưa rõ và tài nguyên không thu được dữ liệu mới.

Nếu hai nguồn mâu thuẫn, giữ nguồn, thời điểm và lý do chọn kết luận. Không dùng bản cập nhật mới nhất làm chân lý mặc định nếu nguồn đó không có thẩm quyền đối với trường dữ liệu đang xét.

### Bước 3: Mở rộng sang đường quản trị và phụ thuộc

Xác định nhóm cấp quyền, tài khoản dịch vụ, credential, pipeline, backup và kênh hỗ trợ có thể tác động hệ thống. Với phụ thuộc dùng chung, liên kết tới scope hoặc đơn vị chịu trách nhiệm tương ứng.

Mở rộng bản đồ quan hệ không có nghĩa tự mở rộng quyền quét. Nếu thiếu dữ liệu ngoài phạm vi collector, tạo yêu cầu xác minh với đơn vị có thẩm quyền.

### Bước 4: Xác nhận ownership và phần loại trừ

Yêu cầu đầu mối có trách nhiệm xác nhận các phần liên quan. Ghi phần chưa được nhận trách nhiệm, xung đột giữa các đội và căn cứ cho loại trừ. Không biến một ô owner không rỗng thành bằng chứng đã có bàn giao.

### Bước 5: Chốt phiên bản và công bố trong quy trình quản trị

Lưu quyết định scope, phiên bản, thời điểm có hiệu lực và các khoảng trống đã biết. Nếu chính sách cho phép sử dụng scope khi còn một số thiếu sót, cần giữ rõ ngoại lệ và trách nhiệm xử lý. Không đánh dấu đầy đủ chỉ vì phiên bản đã được chấp nhận.

Các luồng onboarding, rà soát quyền và kiểm toán phải dùng đúng phiên bản hoặc chỉ rõ thời điểm phân giải scope động. Nếu một công việc JIT chỉ cần một tài nguyên, grant vẫn phải thu hẹp riêng theo yêu cầu đó.

### Bước 6: Duy trì bằng sự kiện và đối soát

Cập nhật theo thay đổi triển khai, chuyển ownership, thêm quyền, đổi credential, tạo/hủy tài nguyên và phát hiện đường truy cập mới. Kết hợp đối soát định kỳ để tìm phần sự kiện bị thiếu.

Khi ngừng hệ thống, kiểm tra danh tính dịch vụ, credential, quyền từ xa, pipeline và tác vụ liên quan. Xóa tài sản khỏi danh mục chưa chứng minh các đường quyền đã được thu hồi.

## 9. Tình huống: phạm vi production và runner dùng chung

Đội orders có hai máy ứng dụng, một cơ sở dữ liệu và một tác vụ backup trong phạm vi trực tiếp như mô hình ở trên. Runner do đội nền tảng vận hành có khả năng triển khai vào orders production và một hệ thống khác.

### Các quyết định cần ghi nhận

| Đối tượng | Cách ghi trong scope orders | Ý nghĩa quản trị |
|---|---|---|
| Hai máy ứng dụng | Tài nguyên trực tiếp với định danh riêng | Kiểm kê quyền và đường truy cập trên từng máy |
| Cơ sở dữ liệu orders | Tài nguyên trực tiếp ở mức database | Không mặc nhiên cấp hoặc nhận trách nhiệm toàn bộ máy chủ database dùng chung |
| Tác vụ backup orders | Tài nguyên trực tiếp, liên kết danh tính chạy và đích backup | Không bỏ qua quyền đọc dữ liệu và khả năng khôi phục |
| Runner dùng chung | Phụ thuộc có quyền triển khai, liên kết scope nền tảng | Đánh giá đường đặc quyền từ runner tới production và trách nhiệm hai phía |
| Vault và nền tảng danh tính | Phụ thuộc có định danh và owner riêng | Xác định ai cấp credential hoặc quyền vào hệ thống |
| Máy development cùng tên dịch vụ | Ngoài scope production nếu đã xác minh ranh giới | Vẫn xem xét quan hệ credential hoặc quyền xuyên môi trường nếu có |

Giả sử discovery tìm thấy máy mới có nhãn `service=orders`, `environment=production`, nhưng danh mục triển khai không ghi nhận máy đó. Tài nguyên này cần trạng thái chờ xác minh, không tự động bị bỏ qua và cũng không tự được nhận mọi quyền quản trị của hệ thống.

Cần kiểm tra nguồn tạo tài nguyên, định danh, chủ sở hữu, quan hệ triển khai và đường truy cập. Nếu nó thực sự phục vụ production, cập nhật scope theo quy trình. Nếu nhãn sai, lưu căn cứ sửa kết luận. Nếu chưa xác định được, giữ khoảng trống và đầu mối xử lý.

### Khi runner bị nghi xâm nhập

Dựa vào quan hệ scope, đội ứng phó cần xác định các hệ thống runner có thể tác động, danh tính và credential mà runner được phép sử dụng, cùng các hoạt động triển khai liên quan. Không giới hạn điều tra ở nhãn owner của máy runner.

Ngược lại, quan hệ “có thể triển khai” chưa chứng minh hệ thống orders đã bị sửa đổi. Cần đối chiếu log, phiên bản triển khai, quyền hiệu lực và thời điểm. System scope hỗ trợ xác định nơi cần xem xét; kết luận sự cố vẫn cần bằng chứng hoạt động.

## 10. Quản lý thay đổi scope và tránh điểm mù

| Thay đổi | Việc cần cập nhật hoặc xác minh |
|---|---|
| Thêm tài nguyên | Membership, owner, nguồn định danh, quyền, credential và độ bao phủ |
| Chuyển đội vận hành | Xác nhận trách nhiệm, nhóm duyệt, danh tính dịch vụ và nghĩa vụ luân chuyển |
| Tạo lại máy dưới tên cũ | Vòng đời tài sản, định danh mới và quyền còn liên quan tới máy cũ |
| Dịch vụ chuyển sang nền tảng dùng chung | Quan hệ cha–con, trách nhiệm nền tảng và đường đặc quyền mới |
| Nhóm quản trị được thêm vào một tài nguyên | Scope bị ảnh hưởng, thành viên nhóm và mục đích cấp quyền |
| Credential bắt đầu phục vụ thêm consumer | Quan hệ liên scope, chủ sở hữu và phụ thuộc luân chuyển |
| Ngừng dịch vụ | Tài nguyên, quyền, tài khoản, secret, pipeline và tác vụ còn sót |
| Nguồn dữ liệu bị lỗi | Trạng thái quan sát và độ tin cậy; không tự thu hẹp scope |

Các lỗi thường gặp gồm chỉ dùng CMDB mà không đối soát, xem mọi tài nguyên cùng subnet là một hệ thống, hoặc loại bỏ phụ thuộc do đội khác quản lý. Một lỗi khác là sao chép scope từ staging sang production rồi chỉ đổi tên, khiến danh tính hoặc credential xuyên môi trường không được kiểm tra.

Việc sửa scope cũng cần được kiểm soát. Nếu người có thể sửa membership dùng thao tác đó để đưa tài nguyên vào luồng cấp quyền tự động, thay đổi inventory có thể có tác động bảo mật. Vì vậy, các hệ thống sử dụng scope làm đầu vào chính sách phải kiểm tra nguồn, phiên bản và quyền chỉnh sửa phù hợp.

## 11. Đo độ bao phủ và lưu bằng chứng

### 11.1. Tách chỉ số theo câu hỏi

```text
Độ bao phủ quan sát tài nguyên =
    số tài nguyên trực tiếp có dữ liệu đủ mới theo tiêu chí đã định
    / tổng số tài nguyên trực tiếp trong phiên bản scope

Độ xác nhận ownership tài nguyên =
    số tài nguyên trực tiếp có ownership còn hợp lệ, đã được xác nhận
    / tổng số tài nguyên trực tiếp trong phiên bản scope

Độ rõ trách nhiệm phụ thuộc =
    số phụ thuộc có đơn vị chịu trách nhiệm và ranh giới đã xác minh
    / tổng số phụ thuộc cần xác minh
```

Ví dụ, scope có bốn tài nguyên trực tiếp nhưng một tài nguyên thu thập thất bại thì độ bao phủ quan sát là `3/4`, nếu ba tài nguyên còn lại đạt tiêu chí độ mới. Không loại tài nguyên lỗi khỏi mẫu số.

Nếu có ba phụ thuộc, trong đó hai đã rõ trách nhiệm còn một đang tranh luận giữa các đội, độ rõ trách nhiệm phụ thuộc là `2/3`. Không cộng ba phụ thuộc vào mẫu số tài nguyên trực tiếp rồi trình bày thành một tỷ lệ không rõ ý nghĩa.

Số tài nguyên có trong scope không phải số tài nguyên đã được quản lý PAM đầy đủ. Có thể cần thêm chỉ số onboarding, quản lý credential, rà soát quyền, hiệu lực thu hồi và bằng chứng hoạt động. Mỗi chỉ số phải có định nghĩa và đơn vị đếm rõ ràng.

Với scope động, lưu tập thành viên và thời điểm dùng để tính chỉ số. Khi mẫu số thay đổi, xu hướng phần trăm có thể thay đổi mà không có cải thiện kiểm soát; cần giải thích bằng số lượng và loại thay đổi.

### 11.2. Bằng chứng cần giữ

| Nhóm bằng chứng | Nội dung |
|---|---|
| Định nghĩa scope | System ID, mục đích, môi trường, phiên bản và thời điểm hiệu lực |
| Membership | Danh sách hoặc quy tắc chọn, nguồn thuộc tính, ảnh chụp kết quả cần thiết |
| Ownership | Vai trò, định danh người/đội, xác nhận và thời hạn xem lại |
| Quan hệ quyền | Danh tính, nhóm/role, thao tác, đích và thời gian quan sát |
| Phụ thuộc | Định danh, scope chịu trách nhiệm, đường ảnh hưởng và phần trách nhiệm mỗi bên |
| Quyết định | Căn cứ đưa vào/loại trừ, thay đổi, ngoại lệ và người có thẩm quyền |
| Chất lượng dữ liệu | Nguồn, độ mới, lỗi, mâu thuẫn và công việc khắc phục |

Inventory về quyền và phụ thuộc có thể tiết lộ đường quản trị nhạy cảm. Cần kiểm soát người xem/sửa và thời gian lưu, đồng thời không lưu mật khẩu, token hay private key trong bản mô tả scope.

Một bản đồ kiến trúc đẹp chưa đủ thay thế bằng chứng: phải truy được tài nguyên cụ thể thuộc phiên bản nào và vì sao được phân loại như vậy.

## 12. Bài tập thiết kế và kiểm thử chấp nhận

### Tình huống thực hành

Một hệ thống production có hai máy ứng dụng, database trên nền tảng dùng chung, tác vụ backup và pipeline do đội khác vận hành. Có một nhóm quản trị miền được cấp quyền trên cả hệ thống này và một hệ thống khác. Một máy cũ không phản hồi nhưng chưa có bằng chứng đã ngừng hoạt động.

### Yêu cầu

1. Viết mục đích, ranh giới và định danh scope.
2. Chọn mức tài nguyên trực tiếp, liên kết đối tượng cha và phụ thuộc dùng chung.
3. Mô tả nhóm quản trị bằng cùng định danh gốc cùng các quan hệ tới từng hệ thống.
4. Gán trách nhiệm hệ thống, danh tính dịch vụ, credential và nền tảng.
5. Phân loại máy không phản hồi, nêu dữ liệu cần thêm để quyết định vòng đời.
6. Thiết kế cập nhật khi có máy mới và khi một owner chuyển đội.
7. Định nghĩa chỉ số độ bao phủ có giữ phần lỗi trong mẫu số.

### Hướng giải tham khảo

Giữ máy chưa xác minh vòng đời trong phạm vi cần xử lý, gắn dữ liệu cũ hoặc lỗi quan sát. Database được mô tả ở mức đối tượng của hệ thống và liên kết tới nền tảng chứa; pipeline và nhóm quản trị dùng chung được giữ như các quan hệ có thể tác động nhiều scope. Ownership được xác nhận theo loại trách nhiệm, không suy từ người tạo tài nguyên.

Mọi thay đổi có tác động membership hoặc trách nhiệm cần lịch sử và căn cứ. Một grant JIT cho công việc cụ thể vẫn phải chọn thao tác, tài nguyên và thời hạn riêng, ngay cả khi toàn bộ các đối tượng đã có trong inventory.

### Ma trận nghiệm thu bằng dữ liệu thực hành

| Ca kiểm tra | Kết quả mong đợi |
|---|---|
| Hai tài nguyên cùng tên ở hai môi trường | Không gộp sai; có định danh và miền quản lý rõ |
| Máy mới có nhãn phù hợp nhưng chưa rõ nguồn | Có quy tắc đưa vào kiểm kê hoặc chờ xác minh; không tự cấp quyền |
| Tài nguyên trong scope nhưng chưa onboard PAM | Giữ membership và trạng thái quản lý riêng |
| Collector không truy vấn được một tài nguyên | Báo khoảng trống, không loại tài nguyên khỏi mẫu số |
| Một nhóm cấp quyền tới nhiều hệ thống | Giữ cùng danh tính và quan hệ liên scope để đánh giá tác động |
| Database thuộc hạ tầng dùng chung | Phân biệt đối tượng con, lớp cha và trách nhiệm hai bên |
| Owner nghỉ việc hoặc chuyển đội | Phát hiện quan hệ cần bàn giao, lưu lịch sử và xác nhận mới |
| Credential có consumer ở scope khác | Thể hiện quan hệ dùng chung và trách nhiệm luân chuyển |
| Một tài nguyên bị loại trừ | Có căn cứ, quyết định, thời điểm và điều kiện xem lại |
| Hệ thống ngừng hoạt động | Đối soát quyền, danh tính, credential và tác vụ còn sót |
| Dùng scope để cấp grant cho một công việc | Quyền vẫn thu hẹp theo tài nguyên, thao tác và thời hạn được duyệt |
| Tính lại chỉ số cho một thời điểm cũ | Xác định được phiên bản scope hoặc tập thành viên tương ứng |

System scope có giá trị khi tạo được ranh giới có thể kiểm tra: biết phần nào cần quản trị, phần nào phụ thuộc bên khác, ai chịu trách nhiệm và dữ liệu nào còn thiếu. Ranh giới đó cần được duy trì cùng vòng đời tài sản và quyền để các bước PAM tiếp theo sử dụng đúng đối tượng và đúng bằng chứng.