# Đã lập inventory privilege

## 1. Mục tiêu của checklist

Trước khi đưa một hệ thống hoặc một đợt mở rộng PAM vào production, đội vận hành cần trả lời được: **ai hoặc workload nào có thể thực hiện hành động đặc quyền, trên tài nguyên nào, qua đường truy cập nào, ai chịu trách nhiệm và bằng chứng này còn mới đến đâu?**

Inventory privilege là bản kiểm kê các quan hệ quyền truy cập đặc biệt. Nó bao gồm tài khoản, nhóm, role, quyền được gán, khả năng nâng quyền và đường truy cập tới hệ thống nhạy cảm. Danh sách tài khoản trong vault chỉ là một phần của inventory: một tài khoản có thể đã vào vault nhưng vẫn có quyền ngoài phạm vi dự kiến; một workload có thể không giữ mật khẩu lâu dài nhưng vẫn có thể nhận role quản trị.

Mục “Đã lập inventory privilege” được đánh dấu hoàn thành khi có dữ liệu đủ dùng để đưa ra quyết định, có đối soát và có người xác nhận. Một tệp được xuất thành công hoặc một màn hình discovery hiển thị nhiều tài khoản chưa đủ để kết luận đã hoàn tất.

Sau bài này, người học có thể:

- Xác định phạm vi kiểm kê và đơn vị dữ liệu cần theo dõi.
- Phân biệt danh tính, credential, quyền được gán và quyền có thể sử dụng trong thực tế.
- Lập inventory cho tài khoản con người, tài khoản dịch vụ và workload.
- Phát hiện khoảng trống bằng cách đối soát nhiều nguồn.
- Chuẩn bị bằng chứng và quyết định đạt, chưa đạt hoặc chấp nhận ngoại lệ có giới hạn cho gate production.

Trong bài, các tên hệ thống, ID, mốc thời gian và ngưỡng kiểm tra đều là ví dụ thiết kế. Tổ chức cần định nghĩa phạm vi, độ mới dữ liệu và tiêu chí phê duyệt phù hợp với hệ thống của mình.

## 2. Kiểm kê cái gì: quan hệ quyền, không chỉ tên tài khoản

### 2.1. Định nghĩa thực dụng về privilege

Một quyền cần được xem xét trong inventory PAM nếu nó cho phép kiểm soát hệ thống, đọc hoặc thay đổi dữ liệu nhạy cảm, thay đổi cơ chế bảo vệ, hoặc cấp quyền tương đương cho danh tính khác. Ví dụ:

- Quản trị hệ điều hành, cơ sở dữ liệu, thiết bị mạng hoặc control plane.
- Đọc, cấp phát, thay đổi hay khôi phục secret và khóa quan trọng.
- Tạo role, thay đổi policy hoặc thêm thành viên vào nhóm quản trị.
- Thay đổi pipeline, artifact hoặc cấu hình triển khai có thể tác động production.
- Tắt logging, sửa retention, thay đổi cảnh báo hoặc xóa bằng chứng.
- Khôi phục backup, truy cập snapshot hoặc điều khiển hạ tầng phục hồi.
- Mạo danh, nhận role hoặc sửa một workload vốn đã có quyền cao hơn.

Không phải tài khoản có chữ `admin` nào cũng có quyền cao, và không phải quyền cao nào cũng nằm trong tài khoản có tên dễ nhận biết. Phân loại phải dựa trên khả năng và phạm vi tác động.

### 2.2. Tách các đối tượng dễ nhầm lẫn

| Đối tượng | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Danh tính, principal | Ai hoặc thành phần nào được hệ thống nhận diện? | Nhân viên trực ca, service principal của ứng dụng |
| Tài khoản trên đích | Danh tính đăng nhập hoặc thực thi ở đâu? | Tài khoản local trên một máy chủ |
| Credential | Bằng chứng xác thực nào được sử dụng? | Tham chiếu SSH key hoặc secret trong vault |
| Grant, membership | Quan hệ cấp quyền nào đang tồn tại? | Thành viên nhóm được gán role vận hành |
| Quyền hiệu lực | Sau kế thừa và điều kiện, có thể làm gì? | Khởi động lại một nhóm dịch vụ production |
| Đường truy cập | Đi tới đích bằng cách nào? | Qua bastion, broker PAM hoặc API trực tiếp |
| Quyền nhận được theo yêu cầu | Có thể kích hoạt hoặc nhận quyền nào? | Role eligible chỉ có hiệu lực sau phê duyệt JIT |

Một principal có nhiều credential; một credential có thể được sao chép hoặc sử dụng sai phạm vi; một principal có thể có nhiều grant trên nhiều đích. Vì vậy, số credential không thể dùng thay cho số danh tính hay số quan hệ quyền.

### 2.3. Đơn vị kiểm kê đề xuất

Đơn vị nền tảng là một **quan hệ quyền có thể giải thích được**:

```text
Principal có ID ổn định
  -> grant trực tiếp / nhóm / role / trust
  -> tập hành động và phạm vi tài nguyên
  -> điều kiện, thời hạn và trạng thái quyền
  -> đường truy cập
  -> owner, bằng chứng và lần xác minh
```

Trong hệ thống dữ liệu thực tế, có thể tách danh tính, tài nguyên, grant và evidence thành các bảng riêng rồi liên kết bằng ID. Không bắt buộc dồn tất cả vào một dòng rất dài. Điều bắt buộc là truy ngược được quan hệ mà không làm mất nguồn gốc hay điều kiện.

Nếu một nhóm cấp quyền trên 20 máy chủ, có thể lưu một grant với phạm vi tài nguyên đã định nghĩa và lưu danh sách thành viên riêng. Tuy nhiên, báo cáo phải phân biệt rõ “một grant trên một tập tài nguyên” với “20 tài nguyên được bao phủ”, tránh cộng lẫn hai mẫu số.

## 3. Chốt phạm vi trước khi discovery

### 3.1. Lập sổ phạm vi độc lập với kết quả quét

Đầu tiên, lập danh sách hệ thống được kỳ vọng có mặt trong đợt đánh giá. Nguồn có thể là danh mục tài sản, danh mục dịch vụ, danh sách tài khoản cloud, thiết kế triển khai và xác nhận của owner. Sau đó mới đối chiếu với dữ liệu discovery.

Nếu chỉ lấy các hệ thống quét được làm mẫu số, một hệ thống chưa kết nối sẽ biến mất khỏi báo cáo và tỷ lệ coverage có thể trông như 100%. Tài nguyên chưa truy vấn được phải tiếp tục xuất hiện với trạng thái chưa xác minh.

| Nhóm phạm vi | Nội dung quyền cần tìm | Điểm dễ bỏ sót |
| --- | --- | --- |
| Directory và IdP | Nhóm quản trị, role, membership lồng nhau | Principal bên ngoài hoặc quyền khôi phục tài khoản |
| Máy chủ Windows/Linux | Local admin, sudo, role vận hành, SSH trust | Tài khoản local không đi qua directory |
| Cơ sở dữ liệu | Role quản trị, owner, quyền đọc dữ liệu nhạy cảm | Quyền cấp lại role hoặc phục hồi dữ liệu |
| Cloud và nền tảng container | Role, policy, trust, workload identity | Eligible role, scope kế thừa, nhận role xuyên miền |
| Vault và nền tảng PAM | Quyền quản trị, đọc secret, thay đổi policy | Người có thể tự sửa cơ chế kiểm soát |
| CI/CD và kho artifact | Quyền đổi pipeline, runner, release, deploy | Người sửa pipeline để sử dụng quyền của workload |
| Thiết bị mạng và hạ tầng quản lý | Tài khoản quản trị, đường quản trị tập trung | Tài khoản cục bộ hoặc đường truy cập dự phòng |
| Backup và phục hồi | Quyền restore, đọc snapshot, quản lý khóa | Đường lấy dữ liệu ngoài hệ thống đang chạy |
| Nhà cung cấp | Tài khoản liên kết, nhóm vendor, truy cập từ xa | Quyền hết hợp đồng nhưng còn membership |
| Break-glass | Danh tính khẩn cấp, cách kích hoạt và người giữ | Quyền luôn tồn tại dù không có phiên sử dụng gần đây |

Không phải mọi dòng đều áp dụng cho mọi đợt triển khai. Một mục ngoài phạm vi phải có lý do, owner và ranh giới rõ ràng; không dùng `N/A` để che một mục chưa kiểm tra.

### 3.2. Định nghĩa ranh giới đủ cụ thể

Phạm vi nên ghi được:

- Môi trường: production, disaster recovery, hoặc staging có đường tác động production.
- Tenant, account, subscription, cluster, site và vùng mạng liên quan.
- Loại tài nguyên, danh sách hoặc quy tắc lựa chọn tài nguyên.
- Tài khoản con người, tài khoản máy, service account, workload và vendor.
- Quyền trực tiếp, quyền kế thừa, quyền có thể kích hoạt, quyền khẩn cấp.
- Thời điểm snapshot, khoảng thời gian quan sát và nguồn dữ liệu được dùng.
- Các loại trừ được phê duyệt cùng ngày hết hạn rà soát.

Một pipeline nằm trong môi trường phát triển nhưng có thể triển khai production vẫn tạo đường đặc quyền vào production. Ranh giới bảo mật cần đi theo khả năng tác động, không chỉ theo nhãn môi trường.

## 4. Bộ thông tin tối thiểu cho inventory

### 4.1. Các nhóm field cần có

| Nhóm | Field minh họa | Ý nghĩa khi xét gate |
| --- | --- | --- |
| Định danh | `record_id`, `principal_id`, `target_id`, `grant_id` | Liên kết ổn định và chống trùng do đổi tên |
| Nguồn danh tính | `identity_source`, `principal_type`, `display_name` | Phân biệt local, directory, workload và vendor |
| Phạm vi | `environment`, `resource_scope`, `target_type` | Biết quyền ảnh hưởng tới đâu |
| Quyền | `role_ref`, `grant_path`, `capabilities`, `conditions` | Giải thích quyền trực tiếp, kế thừa và điều kiện |
| Trạng thái | `assignment_state`, `valid_from`, `valid_until` | Phân biệt standing, eligible và active theo thời gian |
| Đường truy cập | `access_paths`, `pam_coverage` | Thấy cả đường đã kiểm soát và đường còn lại |
| Credential | `credential_type`, `credential_ref`, `rotation_owner` | Liên kết quản lý credential mà không sao chép secret |
| Trách nhiệm | `business_owner`, `technical_owner`, `reviewer` | Có người giải thích nhu cầu và người kiểm tra |
| Nhu cầu, rủi ro | `purpose`, `criticality`, `risk_disposition` | Đặt mức ưu tiên và quyết định xử lý |
| Bằng chứng | `evidence_refs`, `observed_at`, `verified_at` | Chứng minh kết luận dựa trên trạng thái nào |
| Vòng đời | `review_due_at`, `change_ref`, `exception_ref` | Duy trì inventory sau thời điểm nghiệm thu |

Đây là một schema minh họa để thiết kế inventory, không phải yêu cầu thay đổi schema metadata bài học.

### 4.2. Dùng ID ổn định và giữ ngữ cảnh tên

Không dùng riêng `username` làm khóa duy nhất. Hai máy chủ có thể đều có tài khoản tên `root`; một người có tài khoản thường và tài khoản quản trị; tên role có thể giống nhau giữa hai tenant.

Ví dụ khóa nhận diện tài khoản local nên gắn với hệ thống nguồn và định danh tài nguyên. Nếu nền tảng có immutable ID hoặc object ID phù hợp, lưu ID đó và giữ `display_name` để con người đọc. Khi tài nguyên được tái tạo, cần xác định đó là cùng một thực thể logic hay một instance mới trước khi gộp lịch sử.

Khử trùng lặp không đồng nghĩa xóa bản ghi khác nhau vì chúng có cùng tên hiển thị. Ngược lại, cùng một grant được nhìn thấy qua hai nguồn phải được liên kết bằng chứng, tránh đếm thành hai quyền độc lập.

### 4.3. Không đưa giá trị secret vào inventory

Inventory được lưu tham chiếu credential, loại xác thực, nơi quản lý và tình trạng luân chuyển. Không lưu mật khẩu, private key, token còn dùng được, recovery code hoặc nội dung kết nối chứa secret.

Thông tin inventory vẫn nhạy cảm vì mô tả đường quản trị và điểm còn thiếu kiểm soát. Cần phân quyền đọc, ghi, xuất dữ liệu và bảo vệ evidence tương ứng. Một liên kết evidence chỉ có giá trị nếu người kiểm tra được cấp quyền phù hợp để đọc nó.

## 5. Thu thập và đối soát theo một quy trình có thể lặp lại

### Bước 1 — Xác nhận nguồn và quyền thu thập

Với từng nguồn, ghi owner, phạm vi truy vấn, thời điểm, bộ lọc và tình trạng kết nối. Dùng cơ chế truy vấn được phê duyệt, ưu tiên quyền đọc phù hợp. Không coi việc công cụ không trả dữ liệu là bằng chứng không có quyền.

Cần phân biệt ít nhất bốn kết quả: truy vấn thành công có dữ liệu; truy vấn thành công và xác nhận không có đối tượng phù hợp; truy vấn thiếu quyền hoặc thất bại; nguồn chưa được kết nối. Hai kết quả cuối là khoảng trống cần xử lý.

### Bước 2 — Lấy các tập dữ liệu bổ sung cho nhau

Nguồn danh tính cho biết principal tồn tại và thuộc nhóm nào. Cấu hình tại đích cho biết role hay quyền nào được áp dụng. Dữ liệu PAM cho biết tài khoản và đường truy cập nào đang được quản lý. Log cho biết các hành động đã quan sát được trong khoảng thời gian nhất định.

Không nguồn nào tự trả lời toàn bộ câu hỏi. Một phiên PAM hợp lệ không chứng minh đích đã chặn mọi đường trực tiếp. Không có log sử dụng cũng không chứng minh một grant đã bị thu hồi.

### Bước 3 — Chuẩn hóa và mở rộng quan hệ quyền

Chuẩn hóa môi trường, ID, loại principal và thời gian; giữ nguyên giá trị gốc ở evidence hoặc field nguồn khi cần đối chiếu. Mở rộng membership lồng nhau, role kế thừa và các trust đã xác định trong phạm vi.

Tách **quyền tiềm năng** khỏi **quyền đang có hiệu lực ở snapshot**. Với JIT, phải có cả người đủ điều kiện nhận quyền, chính sách kích hoạt và các lần kích hoạt liên quan. Nếu chỉ quét membership đang active, inventory sẽ bỏ sót quyền có thể nhận ngay sau khi kiểm kê.

Quyền hiệu lực có thể phụ thuộc deny, điều kiện truy cập, phạm vi tài nguyên, policy tại nhiều tầng và thời hạn. Nếu chưa tính được đầy đủ, đánh dấu `effective_access_unverified` hoặc mô tả giới hạn xác minh; không biến một phép hợp đơn giản các role thành khẳng định chắc chắn.

### Bước 4 — Đối soát các chênh lệch

```text
Tập tài nguyên thuộc phạm vi
    so với tài nguyên truy vấn thành công
        -> khoảng trống discovery

Grant quản trị tại đích
    so với inventory quan hệ quyền
        -> grant chưa được ghi nhận

Inventory quyền thuộc diện phải qua PAM
    so với tài khoản / đường truy cập do PAM quản lý
        -> khoảng trống onboarding hoặc coverage

Principal có quyền
    so với danh mục owner và vòng đời nhân sự / workload
        -> quyền không có owner hoặc không còn nhu cầu

Hoạt động đặc quyền quan sát trong log
    so với inventory tại thời điểm hoạt động
        -> hoạt động chưa giải thích được
```

Đối soát cần dùng định danh và thời gian phù hợp. Grant vừa được tạo sau snapshot không chứng minh snapshot cũ sai; nó chứng minh cần cơ chế cập nhật. Tuy nhiên, nếu quyền đã tồn tại trước snapshot nhưng nguồn kiểm kê bỏ sót, đó là lỗi bao phủ.

### Bước 5 — Yêu cầu owner xác nhận

Business owner xác nhận nhu cầu nghiệp vụ và mức ảnh hưởng; technical owner xác nhận cách cấp quyền, đường truy cập và phụ thuộc; reviewer kiểm tra bằng chứng theo cơ chế của tổ chức.

Với service account, tên một phòng ban hoặc người đã nghỉ việc không phải owner vận hành hữu ích. Nên có nhóm chịu trách nhiệm có kênh liên lạc, người trực thay thế và quy trình bàn giao. Tài khoản dùng chung vẫn phải có owner của tài khoản, đồng thời có cách truy nguyên người dùng ở từng phiên khi áp dụng.

### Bước 6 — Phân loại từng chênh lệch và đóng bằng chứng

Mỗi chênh lệch phải có trạng thái, người xử lý và hạn xử lý. Các kết luận hữu ích gồm: quyền hợp lệ đã xác minh; quyền cần điều chỉnh; đối tượng chưa xác minh; quyền cần thu hồi; ngoại lệ đang có hiệu lực.

Việc inventory ghi nhận “cần thu hồi” không đồng nghĩa quyền đã bị thu hồi. Khi thay đổi được thực hiện qua quy trình riêng, phải đọc lại nguồn tại đích và cập nhật bằng chứng để đóng mục. Không vô hiệu hóa tài khoản dịch vụ chỉ để làm đẹp báo cáo mà chưa đánh giá phụ thuộc và kế hoạch phục hồi.

### Bước 7 — Chốt baseline cho đợt xét production

Gắn phiên bản snapshot, phạm vi, thời điểm, báo cáo đối soát và xác nhận owner vào hồ sơ go-live. Sau đó duy trì dữ liệu sống bằng thay đổi và discovery định kỳ. Một baseline chỉ mô tả thời điểm xét duyệt, không thay thế inventory đang vận hành.

## 6. Ví dụ một bản ghi quyền đã được giải thích

Ví dụ sau mô tả một workload triển khai ứng dụng. Các trường credential chỉ là tham chiếu giả lập, không chứa secret.

```yaml
record_id: inv-rel-0042
principal:
  id: workload:deploy-order-prod
  display_name: order-prod-deployer
  type: workload
  identity_source: ci-identity-provider
target:
  id: cluster:commerce-prod
  environment: production
  resource_scope: namespace/orders
grant:
  id: grant:orders-release
  role_ref: role:namespace-release
  grant_path:
    - workload:deploy-order-prod
    - federated-trust:order-release
    - role:namespace-release
  capabilities:
    - update-approved-workloads
    - read-deployment-status
  assignment_state: eligible
  conditions:
    - subject-must-match-approved-release-job
    - audience-must-match-deployment-service
  max_session_minutes: 20
access:
  paths:
    - ci-runner-to-cluster-api
  pam_coverage: alternative_workload_control
credential:
  type: short_lived_federated_token
  reference: identity-config:order-release-federation
  static_secret_present: false
ownership:
  business_owner: team:order-service
  technical_owner: team:platform-release
  reviewer: team:access-governance
purpose: Deploy approved versions of the order service
verification:
  observed_at: '2026-11-26T08:00:00Z'
  verified_at: '2026-11-26T09:00:00Z'
  effective_access_state: verified_for_documented_conditions
  evidence_refs:
    - evidence:release-trust-snapshot-042
    - evidence:cluster-role-binding-042
    - evidence:release-permission-check-042
lifecycle:
  review_due_at: '2026-12-26T09:00:00Z'
  change_ref: change:example-042
  exception_ref: null
```

Đọc bản ghi này cần rút ra được ba điều:

1. Đây là một danh tính máy có thể nhận quyền theo điều kiện; không giữ token đang hoạt động vẫn phải được kiểm kê.
2. Quyền giới hạn theo namespace và công việc release; tên role không đủ chứng minh giới hạn, cần evidence của policy, binding và trust.
3. Workload đi theo cơ chế kiểm soát dành cho máy thay vì phiên tương tác con người. Giá trị `alternative_workload_control` chỉ là phân loại; tính đầy đủ của kiểm soát phải được kiểm chứng ở gate tương ứng.

Thời hạn session tối đa không đồng nghĩa quyền bị thu hồi tức thì ở mọi lớp. Inventory phải mô tả thời gian và cơ chế thực tế của nền tảng, kể cả các credential hoặc phiên đã được cấp trước khi policy thay đổi.

## 7. Ví dụ đối soát trước go-live

Một dịch vụ giả lập có sáu hệ thống thuộc phạm vi xét duyệt: directory, hai máy chủ, một cơ sở dữ liệu, một pipeline và một vault. Cả sáu được truy vấn thành công. Sau chuẩn hóa, nhóm tìm được tám quan hệ quyền cần đánh giá.

| ID | Quan hệ quyền | Kết quả kiểm tra ban đầu | Quyết định xử lý |
| --- | --- | --- | --- |
| R1 | Nhóm SRE nhận quyền vận hành máy chủ A | Có owner, scope và bằng chứng JIT | Đã xác minh |
| R2 | Admin local trên máy chủ A | Có owner, đã liên kết PAM | Đã xác minh inventory; gate PAM xét riêng |
| R3 | Service account ứng dụng trên DB | Có quyền rộng hơn mô tả nhu cầu | Ghi nhận đầy đủ, chuyển xử lý quyền thừa |
| R4 | Workload release nhận role triển khai | Trust và scope đã giải thích được | Đã xác minh |
| R5 | Tài khoản break-glass trên vault | Có owner và hồ sơ quản lý | Đã xác minh; gate diễn tập xét riêng |
| R6 | Nhóm vendor quản trị máy chủ B | Membership tồn tại, chưa có owner xác nhận | Chưa đạt yêu cầu owner |
| R7 | Role đọc backup DB | Có owner, thiếu bằng chứng scope thực tế | Chưa xác minh |
| R8 | Nhóm sửa pipeline release | Ban đầu không có trong file inventory | Bổ sung và xác minh đường tác động production |

Nhóm đã thu thập được 6/6 hệ thống và đã ghi nhận 8/8 quan hệ quyền đã phát hiện. Nhưng hai con số đó không làm R6 và R7 biến mất. Đội xét duyệt phải thấy rõ owner còn thiếu và khả năng chưa được giải thích.

R3 minh họa ranh giới giữa các gate: inventory có thể ghi nhận đúng một quyền không an toàn. Gate “đã kiểm kê” không tự chứng minh least privilege đạt. Tuy vậy, phát hiện rủi ro từ inventory vẫn phải đi vào quyết định go-live chung thay vì bị bỏ qua vì không thuộc tên checklist này.

Nếu chính sách của đợt triển khai yêu cầu mọi quyền production rủi ro cao có owner và được xác minh, R6 hoặc R7 có thể chặn gate cho đến khi khắc phục hoặc được xử lý bằng cơ chế ngoại lệ được phép. Không tự gắn `PASS` chỉ vì bản ghi đã tồn tại.

## 8. Bộ tiêu chí nghiệm thu inventory

Checklist nên được điền cùng liên kết evidence, người xác nhận và thời điểm, thay vì chỉ có dấu tích.

| Tiêu chí | Bằng chứng tối thiểu có thể kiểm tra | Dấu hiệu chưa đạt |
| --- | --- | --- |
| Phạm vi đã được chốt | Danh sách hệ thống và loại quyền, owner ký xác nhận | Chỉ có danh sách những gì công cụ quét thấy |
| Nguồn discovery có trạng thái rõ | Kết quả thu thập, thời điểm, bộ lọc và lỗi | Nguồn lỗi được ghi là không có tài khoản |
| Danh tính được định danh ổn định | ID nguồn và liên kết tài khoản trên đích | Gộp mọi tài khoản cùng tên vào một người |
| Quyền được giải thích | Role, grant path, scope và điều kiện | Chỉ có cột `admin=yes` |
| Có quyền trực tiếp và kế thừa | Snapshot membership, binding, policy liên quan | Bỏ qua nhóm lồng nhau hoặc trust |
| Có quyền eligible và khẩn cấp | Danh sách quyền có thể kích hoạt và break-glass | Chỉ thống kê phiên đang active |
| Có non-human và vendor | Danh sách workload, service account, external principal | Chỉ kiểm kê nhân viên |
| Có owner và nhu cầu | Xác nhận của nhóm chịu trách nhiệm | Owner trống hoặc đã mất hiệu lực |
| Đường truy cập được ghi nhận | Sơ đồ hoặc danh sách đường quản trị và trạng thái kiểm soát | Mặc định vào vault là không còn đường khác |
| Các nguồn đã được đối soát | Báo cáo chênh lệch với tài sản, đích, PAM và log thích hợp | Mỗi nguồn có một file riêng, không khớp ID |
| Khoảng trống có quyết định | Issue hoặc ngoại lệ với owner và hạn xử lý | Dòng đỏ không ai nhận hoặc ngoại lệ vô thời hạn |
| Có baseline và cơ chế duy trì | Snapshot nghiệm thu, lịch rà soát, trigger cập nhật | Chỉ lập file một lần trước go-live |

### 8.1. Phân biệt đạt, chưa đạt và ngoại lệ

- **Đạt:** dữ liệu và bằng chứng đáp ứng tiêu chí đã được định nghĩa cho phạm vi xét duyệt.
- **Chưa đạt:** còn khoảng trống vượt điều kiện cho phép, ví dụ không truy vấn được một hệ thống trọng yếu hoặc không xác định được owner của quyền quản trị.
- **Ngoại lệ được chấp nhận:** đúng cơ chế mà tổ chức cho phép, có phạm vi hẹp, lý do, người có thẩm quyền chấp thuận, kiểm soát bù, owner, hạn hết hiệu lực và kế hoạch xử lý.

Ngoại lệ không làm một quyền chưa xác minh trở thành đã xác minh. Báo cáo phải giữ cả sự thật kỹ thuật và quyết định chấp nhận rủi ro. Nếu tiêu chí là bắt buộc và không cho ngoại lệ, người vận hành không được tự mở cơ chế ngoại lệ bằng cách đổi nhãn.

## 9. Đo coverage mà không tạo cảm giác an toàn giả

### 9.1. Tách các chỉ số có mẫu số khác nhau

```text
Coverage thu thập
  = số hệ thống trong phạm vi được truy vấn thành công
    / tổng số hệ thống trong phạm vi

Coverage owner
  = số quan hệ quyền đã có owner xác nhận hợp lệ
    / tổng số quan hệ quyền đang xét

Coverage xác minh
  = số quan hệ quyền đã giải thích và xác minh theo tiêu chí
    / tổng số quan hệ quyền đang xét

Coverage dữ liệu còn mới
  = số quan hệ quyền có bằng chứng còn trong cửa sổ độ mới
    / tổng số quan hệ quyền đang xét
```

“Tổng số quan hệ quyền đang xét” là tập được biết sau discovery và đối soát, không phải bằng chứng đã biết mọi quyền có thể tồn tại. Báo cáo luôn cần đi kèm coverage nguồn và các giới hạn đã biết.

Với tám quan hệ trong ví dụ, nếu bảy quan hệ có owner xác nhận thì coverage owner là 7/8 = 87,5%. Nếu R7 chưa có bằng chứng xác minh phù hợp thì phải ghi riêng tỷ lệ xác minh; không thay bằng tỷ lệ owner.

Không gộp các tỷ lệ bằng phép trung bình để tạo một điểm duy nhất rồi che mất hệ thống trọng yếu. Mười hệ thống ít rủi ro đã kiểm kê không bù cho một control plane production chưa truy vấn được.

### 9.2. Độ mới phụ thuộc loại quyền và sự kiện thay đổi

Cửa sổ độ mới nên xét tốc độ thay đổi và mức tác động. Một membership thay đổi nhiều lần mỗi ngày cần cơ chế cập nhật khác với danh mục thiết bị ít thay đổi.

Một snapshot vừa tạo cũng có thể lỗi thời ngay sau thay đổi quan trọng. Các sự kiện như tạo quyền quản trị mới, đổi trust, chuyển owner, tiếp nhận vendor hoặc mở đường truy cập mới cần kích hoạt kiểm tra lại. Mốc rà soát định kỳ bổ sung cho trigger thay đổi, không thay thế nó.

### 9.3. Trường hợp không có dữ liệu

Nếu mẫu số bằng 0, không tự báo 100%. Ghi “không áp dụng” khi đã xác minh loại quyền không tồn tại trong phạm vi; ghi “chưa xác minh” nếu nguồn chưa có dữ liệu. Hai trạng thái này mang ý nghĩa quản trị khác nhau.

## 10. Giữ inventory đúng sau khi production hoạt động

### 10.1. Gắn với vòng đời cấp quyền

Quy trình cấp hoặc thay đổi quyền nên tạo hoặc cập nhật quan hệ inventory cùng ticket, owner, scope và thời hạn. Quy trình thu hồi phải cập nhật trạng thái sau khi xác minh tại đích.

Các trigger cần chú ý:

- Nhân viên vào, chuyển vị trí, nghỉ việc hoặc đổi nhóm trực.
- Tạo, đổi chủ sở hữu hoặc ngừng một service/workload.
- Tạo role, sửa policy, mở rộng scope hoặc đổi trust.
- Cấp, kích hoạt, gia hạn hoặc thu hồi quyền JIT.
- Thêm vendor, đổi hợp đồng hoặc kết thúc hỗ trợ.
- Thay credential, chuyển cơ chế xác thực hoặc đổi vault.
- Tạo, phục hồi, tái tạo hoặc ngừng một tài nguyên.

Tài nguyên tạm thời có thể được quản lý theo template và snapshot sự kiện phù hợp, nhưng vẫn cần biết danh tính nào có thể tác động loại tài nguyên đó và cách truy ngược instance khi có sự cố.

### 10.2. Phát hiện drift

Drift là chênh lệch giữa trạng thái quyền thực tế và trạng thái được kỳ vọng hoặc đã phê duyệt. Discovery theo lịch và sự kiện giúp phát hiện grant ngoài quy trình, owner không còn hợp lệ hoặc đường truy cập mới.

```text
Khi có thay đổi quyền hoặc đến lịch đối soát:
  lấy snapshot các nguồn trong phạm vi
  chuẩn hóa ID và thời gian
  so với baseline / thay đổi đã phê duyệt
  nếu có grant chưa giải thích được:
    tạo mục điều tra với owner và độ ưu tiên
    lưu bằng chứng, thời điểm phát hiện và phạm vi tác động
  chỉ đóng mục sau khi có xác minh và quyết định hợp lệ
```

Đây là logic minh họa cho quản trị inventory. Tự động thu hồi hoặc thay đổi quyền là một hành động khác, cần thiết kế riêng theo phụ thuộc và quy trình vận hành.

### 10.3. Lưu lịch sử đủ để điều tra

Không chỉ giữ trạng thái hiện tại. Khi điều tra một phiên xảy ra trong quá khứ, cần tái dựng principal, membership, scope và owner tại thời điểm đó. Lưu lịch sử thay đổi hoặc snapshot theo chính sách của tổ chức, cùng nguồn, mốc hiệu lực và mốc quan sát.

Mốc `observed_at` cho biết lúc hệ thống nhìn thấy dữ liệu; mốc hiệu lực cho biết quyền có giá trị khi nào. Hai mốc có thể khác nhau do độ trễ đồng bộ. Giữ sự khác biệt này để tránh quy trách nhiệm dựa trên membership hiện tại cho một hoạt động trong quá khứ.

## 11. Những lỗi thường làm checklist mất giá trị

| Cách làm dễ gặp | Vì sao gây sai lệch | Cách sửa trong inventory |
| --- | --- | --- |
| Xuất danh sách tài khoản vault rồi đóng checklist | Bỏ sót quyền ngoài vault và đường trực tiếp | Đối soát cấu hình tại đích và danh mục tài nguyên |
| Chỉ tìm tên chứa `admin` | Tên không phản ánh khả năng thực tế | Phân loại theo capability, grant và scope |
| Xem role được gán là toàn bộ quyền hiệu lực | Thiếu kế thừa, trust, deny và điều kiện | Ghi đường cấp quyền và mức xác minh |
| Chỉ kiểm kê tài khoản con người | Bỏ qua đường đặc quyền của workload | Có loại principal và owner riêng cho non-human |
| Bỏ eligible role vì chưa active | Bỏ sót khả năng nhận quyền trong tương lai gần | Lưu eligibility và activation tách biệt |
| Đánh dấu owner bằng người yêu cầu đầu tiên | Người yêu cầu có thể không chịu trách nhiệm vận hành | Lấy xác nhận từ nhóm sở hữu hiện tại |
| Xóa bản ghi tài nguyên truy vấn lỗi | Làm coverage tăng giả tạo | Giữ tài nguyên trong mẫu số và ghi lỗi |
| Không có log nên kết luận không có privilege | Nhầm quyền có thể dùng với hành vi đã quan sát | Xác minh grant; dùng log làm bằng chứng bổ sung |
| Copy secret vào bảng để tiện xử lý | Tạo thêm nơi lộ credential | Dùng tham chiếu và phân quyền evidence |
| Có record thì coi là kiểm soát đã đạt | Trộn việc biết quyền với việc giảm rủi ro | Ghi riêng inventory, coverage PAM và xử lý rủi ro |

## 12. Bài thực hành: chuẩn bị hồ sơ nghiệm thu

### 12.1. Tình huống

Đội của bạn chuẩn bị mở PAM cho một dịch vụ production. Danh mục phạm vi có mười hệ thống. Công cụ discovery truy vấn thành công chín hệ thống; một máy chủ dự phòng chưa kết nối được.

Dữ liệu chín hệ thống cho thấy 24 quan hệ quyền. Trong đó, 21 quan hệ đã có owner xác nhận, hai tài khoản vendor chưa xác định owner hiện tại, một service account có owner nhưng chưa xác minh scope. Vault chứa credential hoặc tham chiếu cho 18 quan hệ. Có một workload dùng federation và một nhóm có quyền JIT eligible.

Các số liệu về vault, workload và JIT không được mặc định là các tập không giao nhau; cần kiểm tra ID để biết quan hệ nào thuộc tập nào.

### 12.2. Đầu ra cần lập

1. Bảng phạm vi mười hệ thống, trong đó máy chủ dự phòng vẫn được giữ với trạng thái thu thập thất bại.
2. Inventory 24 quan hệ đã phát hiện, ghi rõ các mục thiếu owner và thiếu xác minh scope.
3. Báo cáo chênh lệch giữa quyền tại đích, inventory và tập quản lý PAM; giải thích riêng workload và JIT.
4. Danh sách bằng chứng còn thiếu, người xử lý, thời hạn và điều kiện để xét lại.
5. Một quyết định gate dựa trên tiêu chí của tình huống, không dựa duy nhất vào số tài khoản trong vault.

### 12.3. Gợi ý đánh giá

Coverage thu thập là 9/10 = 90%. Coverage owner trên tập đã phát hiện là 21/24 = 87,5%. Chưa thể kết luận tập 24 quan hệ là đầy đủ vì một hệ thống chưa được kiểm kê.

Không thể suy ra ngay “PAM coverage = 18/24” là tỷ lệ kiểm soát đạt: cần biết quan hệ nào thuộc diện phải qua PAM, credential có thực sự gắn với grant đó không, và các đường truy cập liên quan đã được kiểm chứng chưa. Federation có thể phù hợp với workload nhưng vẫn phải được ghi nhận và kiểm tra điều kiện nhận quyền.

Nếu máy chủ dự phòng hoặc các quyền chưa có owner thuộc nhóm rủi ro bắt buộc phải xác minh trước go-live, quyết định hiện tại là chưa đạt. Một hồ sơ tốt chỉ rõ phần việc còn thiếu để chuyển sang đạt, thay vì xóa các dòng khó hoặc đổi mẫu số.

## 13. Mẫu xác nhận ngắn cho gate production

```text
CHECKLIST: Đã lập inventory privilege
Phạm vi / phiên bản baseline:
Thời điểm snapshot và cửa sổ độ mới:
Danh sách nguồn và tình trạng thu thập:
Số hệ thống trong phạm vi / đã thu thập:
Số quan hệ quyền đã phát hiện / đã xác minh:
Số quan hệ có owner xác nhận:
Các grant, đường truy cập hoặc nguồn chưa giải thích được:
Evidence và báo cáo đối soát:
Ngoại lệ được phép, người phê duyệt, kiểm soát bù và hạn:
Các mục chuyển sang gate khác:
Owner chịu trách nhiệm duy trì inventory:
Reviewer / thời điểm xác nhận:
Kết quả: ĐẠT / CHƯA ĐẠT / THEO CƠ CHẾ NGOẠI LỆ ĐƯỢC PHÉP
Điều kiện cần đáp ứng để xét lại:
```

Mẫu này giúp đội vận hành trình bày một kết luận có thể kiểm tra lại. Giá trị của inventory nằm ở việc giải thích được từng quan hệ quyền quan trọng và phơi bày được khoảng trống; số lượng dòng chỉ có ý nghĩa khi đi cùng phạm vi, thời gian và bằng chứng.
