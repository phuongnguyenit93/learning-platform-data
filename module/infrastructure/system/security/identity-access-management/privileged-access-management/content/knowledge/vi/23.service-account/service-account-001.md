# Service account inventory

Một chương trình Privileged Access Management (PAM) không thể kiểm soát đầy đủ quyền đặc biệt nếu chỉ biết các tài khoản quản trị viên là con người. Nhiều tác vụ quan trọng chạy dưới danh tính của ứng dụng, dịch vụ nền, pipeline triển khai hoặc tác vụ định kỳ. Những danh tính đó có thể đọc dữ liệu nhạy cảm, sửa cấu hình hoặc truy cập nhiều hệ thống trong thời gian dài mà ít khi xuất hiện trong quy trình cấp quyền cho nhân viên.

**Service account inventory** là danh mục có kiểm chứng về các tài khoản dịch vụ và quan hệ của chúng với workload, chủ sở hữu, quyền truy cập, phương thức xác thực và vòng đời vận hành. Mục tiêu không phải thu thập danh sách tên đăng nhập càng dài càng tốt. Mục tiêu là trả lời được: tài khoản này đại diện cho công việc gì, ai chịu trách nhiệm, đang được sử dụng ở đâu, có thể tác động tới đâu và phải xử lý thế nào khi có sự cố.

Trong phạm vi bài học này, service account là danh tính dùng để một phần mềm hoặc tác vụ thực hiện công việc, thay vì đại diện trực tiếp cho một người đang tương tác. Đây là quy ước kiểm kê; tên đối tượng và cơ chế xác thực cụ thể có thể khác nhau giữa hệ điều hành, cơ sở dữ liệu, nền tảng container và dịch vụ đám mây.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt service account với workload, credential, vai trò và người sở hữu.
- Xác định các nhóm danh tính máy cần kiểm kê trong một chương trình PAM.
- Thiết kế bản ghi inventory có đủ thông tin để quyết định và vận hành.
- Hợp nhất dữ liệu từ nhiều nguồn mà không gộp nhầm tài khoản hoặc làm mất quan hệ phụ thuộc.
- Phát hiện tài khoản chưa rõ chủ sở hữu, quyền quá rộng, credential dùng chung và phạm vi kiểm soát chưa đầy đủ.
- Dùng inventory làm đầu vào cho least privilege, vault, luân chuyển credential, truy cập ngắn hạn và ứng phó sự cố.

Đầu ra thực hành của bài là một danh mục tài khoản dịch vụ có thể đối soát, kèm danh sách ngoại lệ và hành động ưu tiên. Đây là nền tảng cho các bước kiểm soát tiếp theo, chưa phải bằng chứng rằng mọi tài khoản đã được bảo vệ đầy đủ.

## 2. Vì sao inventory phải đi trước các biện pháp kiểm soát

Giả sử tổ chức bật luân chuyển mật khẩu tự động cho tài khoản `svc_payment_batch`. Trong danh mục hiện có, tài khoản này chỉ được gắn với một tác vụ xử lý thanh toán. Thực tế, cùng credential còn nằm trong một dịch vụ đối soát và một lịch chạy báo cáo cũ.

Sau khi mật khẩu đổi:

1. Tác vụ thanh toán lấy được mật khẩu mới từ nơi lưu trữ được quản lý.
2. Dịch vụ đối soát tiếp tục dùng mật khẩu cũ và bắt đầu lỗi.
3. Lịch chạy báo cáo chỉ chạy cuối tháng nên lỗi chưa xuất hiện ngay.
4. Nhóm vận hành khôi phục mật khẩu cũ để cứu dịch vụ, làm mất hiệu lực kiểm soát vừa triển khai.

Sai sót gốc không nằm ở thao tác đổi mật khẩu. Sai sót nằm ở việc thiếu quan hệ giữa tài khoản, credential và các consumer đang sử dụng credential đó.

Một inventory đủ tốt giúp trả lời các quyết định cụ thể:

| Quyết định | Thông tin inventory cần cung cấp |
| --- | --- |
| Đưa tài khoản vào vault | Chủ sở hữu, credential nào cần quản lý, consumer nào lấy credential, cách chuyển đổi |
| Giảm quyền | Công việc thực tế, tài nguyên đích, quyền hiệu lực, bằng chứng nhu cầu |
| Luân chuyển credential | Tất cả consumer đã biết, cách nạp lại credential, lịch chạy, cửa sổ thay đổi |
| Chuyển sang danh tính ngắn hạn | Workload có thể lấy danh tính bằng cơ chế nào, bên nào phát hành, giới hạn tin cậy |
| Xử lý rò rỉ | Phạm vi ảnh hưởng, các đường truy cập, owner liên hệ, cách thu hồi và khôi phục |
| Ngừng sử dụng | Phụ thuộc đã được kiểm tra, bằng chứng không còn nhu cầu, kế hoạch vô hiệu hóa và theo dõi |

Với danh tính máy, cần ghi bằng chứng phù hợp như sự kiện xác thực, sử dụng secret, phát hành token và thao tác quản trị. Không phải mọi tài khoản dịch vụ đều tạo ra một phiên tương tác có thể quay lại màn hình; không nên dùng việc có session recording làm tiêu chí duy nhất để đánh giá độ bao phủ PAM.

## 3. Những đối tượng dễ bị nhầm với nhau

### 3.1. Danh tính không phải credential

Danh tính là đối tượng mà hệ thống nhận diện và cấp quyền. Credential là phương tiện hoặc bằng chứng được dùng trong quá trình xác thực.

Một tài khoản có thể đồng thời có mật khẩu, khóa công khai được đăng ký và nhiều credential còn hiệu lực trong giai đoạn chuyển đổi. Ngược lại, một credential bị sao chép tới nhiều nơi không biến thành nhiều danh tính khác nhau.

Ví dụ:

~~~text
Danh tính:
  directory-prod / object-7f3a

Credential đang biết:
  password-ref-01
  public-key-fingerprint-02

Consumer:
  payment-worker
  reconciliation-job
~~~

Inventory phải giữ được các quan hệ này. Nếu chỉ có cột “tên tài khoản” và “mật khẩu đã đổi”, bạn không biết credential nào còn hiệu lực và ai còn sử dụng nó.

Không lưu mật khẩu, private key, token, mã khôi phục hoặc nội dung secret trong inventory. Chỉ lưu tham chiếu tới kho quản lý được cấp quyền, loại credential và metadata cần thiết. Ngay cả đường dẫn secret hoặc tên workload cũng có thể nhạy cảm; inventory cần được bảo vệ như dữ liệu vận hành quan trọng.

### 3.2. Danh tính không phải workload

Workload là ứng dụng, tiến trình, job hoặc dịch vụ đang thực hiện công việc. Tài khoản là danh tính workload dùng khi truy cập một tài nguyên hoặc chạy trong một miền bảo mật.

Một workload có thể sử dụng nhiều danh tính: danh tính để chạy tiến trình, tài khoản cơ sở dữ liệu và danh tính để gọi một API. Một danh tính cũng có thể bị nhiều workload dùng chung. Vì vậy, quan hệ này thường không phải một-một.

Cần kiểm kê cả hai chiều:

- Từ tài khoản: workload nào đang dùng tài khoản?
- Từ workload: workload đang dùng những danh tính nào để chạy và truy cập hệ thống khác?

Chiều thứ hai giúp phát hiện lỗ hổng mà việc xuất danh sách tài khoản không thể chỉ ra, chẳng hạn một job cấu hình dùng credential cá nhân của kỹ sư.

### 3.3. Vai trò không phải lúc nào cũng là tài khoản

Một vai trò có thể là tập quyền, hoặc là đối tượng có thể được đảm nhận để nhận quyền tạm thời, tùy nền tảng. Không nên tự động đếm mọi role thành một service account độc lập.

Hãy ghi rõ:

- Danh tính gốc nào được phép sử dụng vai trò.
- Điều kiện hoặc quan hệ tin cậy cho phép sử dụng.
- Phạm vi tài nguyên mà vai trò có thể tác động.
- Bằng chứng việc đảm nhận vai trò và việc sử dụng quyền.

Khi một workload dùng token ngắn hạn, inventory thường quản lý danh tính workload, cấu hình tin cậy và quyền được cấp. Không cần tạo một bản ghi tài khoản bền vững cho từng token hay từng lần khởi chạy.

### 3.4. Owner không phải tài khoản đang sở hữu file

“Owner” trong inventory là bên chịu trách nhiệm giải thích nhu cầu, phê duyệt thay đổi và xử lý vòng đời của tài khoản. Đây không phải khái niệm chủ sở hữu file trên hệ điều hành.

Nên phân biệt ít nhất:

- **Owner nghiệp vụ hoặc dịch vụ:** xác nhận tài khoản phục vụ quy trình nào và còn cần hay không.
- **Owner kỹ thuật:** biết cấu hình, consumer, triển khai và khôi phục.
- **Bên vận hành kiểm soát:** quản lý vault, cơ chế luân chuyển hoặc nền tảng danh tính.

Một nhóm có thể đảm nhiệm nhiều vai trò trong tổ chức nhỏ, nhưng trách nhiệm vẫn cần được ghi rõ. Người tạo tài khoản không tự động trở thành owner lâu dài. Một tên nhóm cũng chưa đủ nếu không có kênh liên hệ và cơ chế nhận trách nhiệm.

## 4. Phạm vi kiểm kê

Phạm vi phải bám vào cách danh tính được sử dụng, không chỉ vào quy ước tên như `svc_`. Tên là tín hiệu khám phá, không phải bằng chứng đầy đủ.

Các nhóm thường cần xem xét:

| Nhóm | Ví dụ | Câu hỏi kiểm kê |
| --- | --- | --- |
| Tài khoản dịch vụ trong hệ điều hành hoặc directory | Danh tính chạy dịch vụ nền, tác vụ theo lịch | Chạy trên máy nào, ai triển khai, có đăng nhập tương tác được không? |
| Tài khoản ứng dụng và cơ sở dữ liệu | Tài khoản kết nối dữ liệu, tài khoản tích hợp | Ứng dụng nào dùng, được thao tác trên schema hoặc dữ liệu nào? |
| Danh tính workload trên nền tảng | Danh tính cho container, máy ảo, tác vụ xử lý | Workload nào được gắn danh tính, giới hạn cấp quyền nằm ở đâu? |
| Danh tính tự động hóa | Bot triển khai, job sao lưu, pipeline | Có thể thay đổi môi trường nào, credential được phân phối qua đường nào? |
| Tài khoản tích hợp dịch vụ ngoài | Bot hoặc client kết nối hệ thống khác | Bên nào sở hữu, phạm vi API nào được phép, thu hồi bằng cách nào? |
| Tài khoản dùng sai mục đích | Tài khoản cá nhân được nhúng trong một job | Ai chịu trách nhiệm chuyển đổi và tác động khi nhân sự thay đổi? |

Không phải service account nào cũng có quyền đặc biệt. Tuy nhiên, nên bắt đầu từ quần thể danh tính máy trong phạm vi đã chọn rồi phân loại mức đặc quyền. Nếu chỉ tìm nhóm “Administrators”, bạn có thể bỏ sót tài khoản chỉ có quyền đọc nhưng đọc được dữ liệu rất nhạy cảm, hoặc tài khoản triển khai có thể sửa mã sẽ chạy dưới quyền cao hơn.

Phạm vi cũng cần ghi giới hạn: những hệ thống nào đã được khảo sát, hệ thống nào chưa có nguồn dữ liệu và loại tài khoản nào đang nằm ngoài đợt kiểm kê. Không biến “chưa quan sát được” thành “không tồn tại”.

## 5. Mô hình dữ liệu tối thiểu

Một bảng phẳng có thể phù hợp khi bắt đầu, nhưng nên giữ các thực thể và quan hệ rõ ràng. Khi quy mô tăng, chúng có thể được tách thành nhiều bảng hoặc đối tượng liên kết.

~~~mermaid
flowchart LR
    O["Nhóm chịu trách nhiệm"] -->|quản lý| I["Danh tính dịch vụ"]
    W["Workload / job"] -->|sử dụng| I
    I -->|xác thực bằng| C["Tham chiếu credential"]
    I -->|được cấp| G["Quyền / quan hệ tin cậy"]
    G -->|tác động tới| R["Tài nguyên đích"]
    E["Nguồn và bằng chứng"] -->|xác nhận| I
    E -->|xác nhận| W
    E -->|xác nhận| G
~~~

### 5.1. Các trường quan trọng

| Nhóm trường | Nội dung nên có | Lý do |
| --- | --- | --- |
| Định danh | ID nội bộ, nền tảng, miền hoặc tenant, native ID, tên hiển thị | Tránh gộp nhầm tài khoản trùng tên |
| Mục đích | Mô tả công việc, dịch vụ liên quan, môi trường | Phân biệt nhu cầu hợp lệ với tài khoản không rõ công dụng |
| Trách nhiệm | Owner dịch vụ, owner kỹ thuật, kênh liên hệ, lần xác nhận gần nhất | Có bên chịu trách nhiệm khi thay đổi hoặc xảy ra sự cố |
| Consumer | Workload, nơi triển khai, instance hoặc mẫu triển khai, lịch chạy | Xác định phụ thuộc và phạm vi thay đổi |
| Quyền | Quyền được cấp, quyền hiệu lực đã kiểm tra, tài nguyên, đường nâng quyền | Đánh giá tác động thực tế |
| Xác thực | Loại credential, nơi quản lý, tham chiếu, hạn hoặc kỳ quản lý nếu có | Chuẩn bị luân chuyển, thu hồi và chuyển đổi |
| Hoạt động | Lần dùng quan sát được, nguồn log, cửa sổ bao phủ, độ trễ | Diễn giải đúng tín hiệu đang dùng hoặc không thấy dùng |
| Vòng đời | Ngày tạo nếu biết, trạng thái vận hành, thời điểm rà soát, kế hoạch kết thúc | Ngăn danh tính tồn tại vô thời hạn |
| Kiểm soát | Vault, giám sát, chính sách ngắn hạn, ngoại lệ có hạn | Phân biệt tài khoản đã biết với tài khoản đã được bảo vệ |
| Bằng chứng | Nguồn, thời điểm thu thập, phương pháp, độ tin cậy, mâu thuẫn | Cho phép kiểm tra và tái hiện quyết định |

Không bắt buộc biết mọi giá trị trong lần nhập đầu tiên. Giá trị chưa biết phải được ghi nhận minh bạch và đi kèm người xử lý, thay vì điền dữ liệu suy đoán để làm đẹp báo cáo.

### 5.2. Khóa định danh

Một khóa thực dụng có thể được xây từ:

~~~text
platform + authority_scope + native_object_id
~~~

Trong đó:

- `platform` phân biệt nền tảng hoặc hệ thống.
- `authority_scope` là miền quản lý danh tính, chẳng hạn directory, tenant hoặc máy cục bộ.
- `native_object_id` là mã đối tượng ổn định mà nguồn cung cấp, nếu có.

Ví dụ, hai máy có thể cùng có tài khoản cục bộ tên `backup` nhưng đó là hai đối tượng khác nhau. Một tài khoản bị xóa rồi tạo lại cùng tên cũng không nên mặc nhiên được nối với lịch sử của đối tượng cũ.

Nếu hệ thống không cung cấp ID ổn định, phải ghi rõ khóa thay thế, giới hạn của nó và bằng chứng liên kết. Không dùng tên hiển thị làm khóa duy nhất mà không ghi nhận rủi ro này.

### 5.3. Tránh gộp mọi trạng thái vào một cột

Các câu hỏi sau độc lập với nhau:

- Tài khoản còn được kích hoạt không?
- Owner đã xác nhận chưa?
- Dữ liệu inventory có đủ không?
- Đã có vault hoặc cơ chế quản lý tương ứng chưa?
- Credential còn hiệu lực không?
- Tài khoản đang chờ ngừng sử dụng hay chỉ tạm dừng?

Một tài khoản có thể đang hoạt động, owner đã xác nhận, nhưng chưa được đưa vào cơ chế quản lý credential. Một tài khoản đã vô hiệu hóa vẫn cần lưu lịch sử để điều tra và chứng minh quá trình ngừng sử dụng.

Nếu chỉ có cột `status: done`, người đọc không biết điều gì thực sự đã hoàn tất.

## 6. Ví dụ bản ghi inventory

Ví dụ dưới đây là dữ liệu minh họa, không chứa secret. Tên trường chỉ là thiết kế tham khảo, không phải schema bắt buộc của một sản phẩm PAM.

~~~yaml
inventory_id: sai-0042

identity:
  platform: example-directory
  authority_scope: directory-prod
  native_object_id: object-7f3a
  display_name: svc_invoice_export
  identity_type: service_account
  environment: production
  enabled: true

purpose:
  service: invoice-export
  description: Xuất dữ liệu hóa đơn đã chốt sang hệ thống kế toán

ownership:
  service_owner_team: finance-platform
  technical_owner_team: finance-runtime
  contact_ref: team-directory/finance-runtime
  owner_confirmation: confirmed
  last_confirmed_at: "2026-11-20"

consumers:
  - workload_id: invoice-export-nightly
    deployment_scope: production-batch
    schedule: Hằng ngày sau khi chốt dữ liệu
    dependency_evidence_ref: deployment-record/export-nightly
  - workload_id: invoice-export-retry
    deployment_scope: production-batch
    schedule: Theo yêu cầu khôi phục tác vụ lỗi
    dependency_evidence_ref: runbook/export-retry

access:
  privileged: true
  privilege_reason: Có thể thực hiện thủ tục xuất tập dữ liệu tài chính
  target_refs:
    - database/finance-prod
  verified_effective_scope:
    - Thực thi thủ tục xuất dữ liệu được phê duyệt
    - Ghi vào thư mục trao đổi của quy trình xuất
  interactive_use: prohibited_by_policy
  effective_access_verified_at: "2026-11-21"

authentication:
  method: password
  credential_refs:
    - credential-metadata/cred-017
  secret_location_ref: vault-reference/finance/invoice-export
  consumer_refresh_method: Tải lại cấu hình qua quy trình triển khai được quản lý

activity:
  last_observed_at: "2026-11-25T18:05:00Z"
  evidence_window_start: "2026-10-01T00:00:00Z"
  evidence_window_end: "2026-11-25T23:59:59Z"
  source_ref: evidence/authentication-summary-017
  coverage_note: Có log của đích chính; cần đối soát thêm tác vụ retry

controls:
  credential_management: managed
  rotation_readiness: dependency_validation_pending
  monitoring: authentication_and_export_job_events
  exception_ref: none

lifecycle:
  operational_state: active
  inventory_state: needs_dependency_confirmation
  review_due_at: "2026-12-20"

provenance:
  - source: directory-export
    collected_at: "2026-11-25T08:00:00Z"
  - source: workload-config-review
    collected_at: "2026-11-25T09:00:00Z"
~~~

Có ba điểm đáng chú ý trong bản ghi:

1. Tài khoản đã có cơ chế quản lý credential nhưng chưa sẵn sàng luân chuyển cho mọi consumer. Hai trạng thái không được đánh đồng.
2. Chính sách cấm tương tác không tự chứng minh rằng nền tảng đã chặn mọi đường đăng nhập tương tác. Cần bằng chứng kiểm tra cấu hình và thử nghiệm phù hợp.
3. Log cho thấy hoạt động ở một đích, nhưng chưa xác nhận đầy đủ tác vụ retry. Bản ghi giữ lại khoảng trống đó để tiếp tục xử lý.

## 7. Quy trình xây dựng inventory

### 7.1. Xác định phạm vi và bên chịu trách nhiệm

Bắt đầu bằng một phạm vi có thể kiểm chứng, chẳng hạn các workload production của một dịch vụ và những hệ thống chúng truy cập. Ghi rõ môi trường, hệ thống, nhóm vận hành và thời điểm chụp dữ liệu.

Thống nhất trước định nghĩa:

- Thế nào là một tài khoản dịch vụ trong phạm vi kiểm kê.
- Thế nào là quyền đặc biệt đối với từng loại tài nguyên.
- Thế nào là owner đã xác nhận.
- Dữ liệu nào đủ để ghi “đã biết consumer”.
- Ngoại lệ phải có người nhận trách nhiệm và hạn rà soát ra sao.

Nếu thiếu các định nghĩa này, các nhóm có thể dùng cùng một từ nhưng báo cáo các đối tượng khác nhau.

### 7.2. Thu thập từ nhiều nguồn bổ sung cho nhau

| Nguồn | Giúp thấy | Hạn chế |
| --- | --- | --- |
| Directory hoặc danh sách tài khoản nền tảng | Đối tượng, trạng thái, thuộc tính, nhóm | Không chứng minh ứng dụng nào đang dùng |
| Cấu hình dịch vụ, scheduler và triển khai | Danh tính được khai báo cho workload | Có thể là cấu hình cũ, chưa triển khai hoặc bị ghi đè |
| Vault và hệ thống phân phối secret | Credential đã được quản lý, lịch sử truy cập tham chiếu | Không thấy credential nằm ngoài phạm vi quản lý |
| Log xác thực và log tài nguyên | Hoạt động đã quan sát và đích truy cập | Bị giới hạn bởi retention, chất lượng và độ bao phủ |
| Cấu hình quyền và quan hệ tin cậy | Khả năng truy cập hoặc đảm nhận quyền | Quyền hiệu lực có thể cần tổng hợp nhiều lớp |
| Danh mục ứng dụng, IaC và hồ sơ triển khai | Liên kết dịch vụ, môi trường, nhóm phụ trách | Không bảo đảm trạng thái thực tế khớp khai báo |
| Xác nhận của owner | Mục đích, lịch chạy hiếm, phụ thuộc ngoài tài liệu | Có thể thiếu hoặc dựa trên trí nhớ |

Thu thập metadata với quyền đọc phù hợp. Không cần xuất nội dung credential để biết một tài khoản tồn tại hoặc một workload tham chiếu tới secret nào.

Đặc biệt, công cụ tìm kiếm cấu hình không được đưa giá trị secret vào log, ticket hoặc bảng inventory. Nếu phát hiện credential lộ trong cấu hình, tạo hồ sơ xử lý theo quy trình sự cố và chỉ lưu tham chiếu được kiểm soát.

### 7.3. Chuẩn hóa và đối chiếu

Sau khi nhập dữ liệu:

1. Chuẩn hóa môi trường, nền tảng và miền quản lý.
2. Liên kết bản ghi theo ID ổn định; giữ tên cũ như alias khi cần.
3. Tách quan hệ consumer khỏi bản ghi danh tính để tránh lặp hoặc mất dữ liệu.
4. Đính kèm nguồn và thời điểm cho thông tin quan trọng.
5. Ghi nhận mâu thuẫn, chưa vội chọn giá trị làm trạng thái cuối.

Ví dụ, directory báo tài khoản đã bị vô hiệu hóa nhưng log có sự kiện thành công sau đó. Cần kiểm tra tài khoản có đúng cùng ID không, thời gian của log, thời điểm thu thập, loại sự kiện và khả năng credential hoặc phiên đã được cấp trước đó còn sử dụng được. Không tự kết luận rằng directory sai hoặc log sai.

Khi xác định quyền, ghi cả quyền trực tiếp và các đường cấp quyền gián tiếp liên quan như nhóm, vai trò, quan hệ tin cậy hoặc khả năng sửa thành phần khác. Không coi một lần xuất nhóm thành viên là mô tả hoàn chỉnh quyền hiệu lực trên mọi tài nguyên.

### 7.4. Xác nhận owner và consumer

Gửi owner một tập câu hỏi có thể trả lời được:

- Tài khoản phục vụ chức năng nào?
- Những workload nào đang sử dụng?
- Môi trường và tài nguyên đích nào liên quan?
- Có tác vụ theo quý, cuối năm hoặc chỉ chạy khi khôi phục không?
- Credential được lấy và nạp lại như thế nào?
- Ai phê duyệt thay đổi quyền, luân chuyển và ngừng sử dụng?
- Bằng chứng hoặc tài liệu nào xác nhận các câu trả lời?

Owner xác nhận mục đích không có nghĩa mọi quyền hiện tại đều hợp lý. Danh sách consumer do owner cung cấp cũng cần được đối chiếu với cấu hình và hoạt động quan sát được.

Đối với tài khoản dùng chung, phải ghi từng consumer đã biết và người chịu trách nhiệm cho từng quan hệ. Không ghi “dùng cho nhiều hệ thống” rồi coi như đã hoàn tất kiểm kê.

### 7.5. Phân loại và lập danh sách hành động

Phân loại dựa trên khả năng tác động và chất lượng kiểm soát:

- Quyền có thể thay đổi hệ thống, dữ liệu hoặc cơ chế cấp quyền khác.
- Mức nhạy cảm và mức quan trọng của tài nguyên.
- Số consumer và môi trường cùng sử dụng danh tính.
- Credential tồn tại lâu, được sao chép rộng hoặc chưa rõ nơi quản lý.
- Khả năng truy cập tương tác hoặc truy cập từ vùng không dự kiến.
- Chất lượng owner, log và bằng chứng phụ thuộc.

Không nên chỉ chấm điểm theo độ dài mật khẩu hoặc số ngày từ lần dùng gần nhất. Tài khoản phục hồi thảm họa có thể ít hoạt động nhưng có phạm vi tác động rất lớn.

Mỗi vấn đề nên tạo ra hành động rõ ràng, chẳng hạn “xác nhận consumer của job khôi phục trước ngày X” hoặc “tách danh tính staging khỏi production”, kèm owner xử lý. “Cần cải thiện bảo mật” không phải một hành động có thể nghiệm thu.

### 7.6. Duy trì bằng sự kiện và rà soát định kỳ

Inventory không hoàn tất một lần rồi đứng yên. Cần cập nhật khi:

- Tạo, đổi tên, vô hiệu hóa hoặc xóa danh tính.
- Thêm workload, consumer hoặc tài nguyên đích.
- Đổi owner hoặc giải thể nhóm.
- Thay cơ chế xác thực, credential hoặc nơi quản lý.
- Thay quyền, quan hệ tin cậy hoặc đường truy cập.
- Phát hiện sự cố, cấu hình lệch hoặc tài khoản ngoài danh mục.

Kết hợp cập nhật theo sự kiện với đối soát định kỳ. Tần suất cụ thể phải phù hợp mức rủi ro, tốc độ thay đổi và khả năng quan sát của hệ thống; không có một khoảng thời gian duy nhất phù hợp cho mọi tài khoản.

## 8. Đánh giá các dấu hiệu rủi ro thường gặp

### 8.1. Chưa rõ owner

Cần phân biệt:

- Chưa thu thập được thông tin owner.
- Nhóm được ghi trong dữ liệu đã giải thể.
- Người được ghi nhận không xác nhận trách nhiệm.
- Tài khoản không còn nhu cầu sử dụng sau khi đã kiểm tra.

Ba trường hợp đầu là khoảng trống trách nhiệm, chưa đủ để kết luận có thể xóa tài khoản.

Gán người điều phối xử lý ngoại lệ, hạn xác minh và biện pháp kiểm soát tạm thời phù hợp. Tài khoản có quyền cao mà không rõ owner cần được ưu tiên vì khó ra quyết định nhanh khi có sự cố.

### 8.2. Không quan sát thấy hoạt động

Không thấy đăng nhập trong 30 ngày không chứng minh tài khoản không được dùng. Có thể:

- Tác vụ chỉ chạy cuối quý.
- Log chỉ lưu được một phần khoảng thời gian.
- Một giao thức hoặc tài nguyên đích chưa được thu thập.
- Ứng dụng giữ kết nối dài hoặc dùng token đã cấp.
- Tên trong log khác alias hiện tại.

Trước khi đề xuất ngừng sử dụng, kiểm tra chu kỳ nghiệp vụ, cấu hình, log đúng nguồn và xác nhận owner. Có thể dùng quy trình vô hiệu hóa có kiểm soát, theo dõi lỗi và khả năng khôi phục theo thay đổi được phê duyệt. Inventory tự nó không phải lệnh xóa hàng loạt tài khoản ít hoạt động.

### 8.3. Nhiều workload dùng chung một tài khoản

Rủi ro gồm phạm vi ảnh hưởng lớn, khó quy trách nhiệm, luân chuyển phức tạp và quyền bị cộng dồn để đáp ứng tất cả consumer.

Hướng xử lý thường là tách danh tính theo nhu cầu, môi trường và ranh giới tin cậy phù hợp. Tuy nhiên, việc tách cần kiểm tra khả năng nền tảng, phụ thuộc triển khai và kế hoạch chuyển đổi. Không tạo danh tính mới rồi coi credential cũ đã hết được sử dụng.

### 8.4. Danh tính production xuất hiện trong môi trường khác

Ví dụ, một job thử nghiệm sử dụng cùng tài khoản cơ sở dữ liệu với production. Cần kiểm tra cả quyền thực tế lẫn đường truy cập mạng, nơi phân phối credential và quyền sửa cấu hình job.

Một nhãn `environment: production` trong danh mục không ngăn credential được sử dụng ở nơi khác. Phải đối chiếu nhãn với bằng chứng triển khai và hoạt động.

### 8.5. Đã ở vault nhưng chưa kiểm soát được toàn bộ

Một bản sao credential nằm trong vault không bảo đảm:

- Mọi consumer đều lấy credential từ vault.
- Credential không còn bản sao ngoài quản lý.
- Các khóa hoặc credential khác của tài khoản đã được kiểm kê.
- Có thể luân chuyển mà không gián đoạn.
- Quyền của tài khoản đã tối thiểu.
- Sự kiện sử dụng được ghi và đối soát đầy đủ.

Vì vậy, inventory cần trạng thái kiểm soát theo từng khía cạnh và bằng chứng đi kèm, thay vì chỉ có ô đánh dấu “PAM: Yes”.

## 9. Chuyển inventory thành kế hoạch kiểm soát PAM

### 9.1. Least privilege

Dùng mục đích và hoạt động hợp lệ để đề xuất tập quyền cần thiết. So sánh với quyền hiệu lực đã kiểm tra, đánh dấu phần dư và lập kế hoạch thử nghiệm với owner.

Hoạt động quan sát được chỉ là một nguồn bằng chứng. Một quyền chưa được sử dụng trong cửa sổ log vẫn có thể cần cho khôi phục hoặc tác vụ theo mùa. Phải giải thích và kiểm tra nhu cầu đó trước khi quyết định.

### 9.2. Quản lý credential và luân chuyển

Inventory cung cấp danh sách credential, nơi quản lý và consumer. Từ đó xác định:

- Credential nào phải được đưa vào cơ chế quản lý.
- Consumer nào cần thay cách lấy hoặc làm mới credential.
- Khi nào có thể có hai credential hợp lệ trong giai đoạn chuyển đổi nếu nền tảng hỗ trợ.
- Làm thế nào kiểm tra consumer dùng được credential mới.
- Khi nào thu hồi credential cũ và theo dõi lỗi sau thay đổi.

Đưa tài khoản vào danh mục là bước khám phá. Xác nhận mọi consumer hoạt động sau thay đổi mới là một phần bằng chứng cho luân chuyển thành công.

### 9.3. Danh tính và quyền ngắn hạn

Khi nền tảng và workload hỗ trợ, có thể giảm phụ thuộc vào credential dài hạn bằng cơ chế nhận danh tính hoặc quyền có thời hạn.

Inventory vẫn cần ghi danh tính gốc, bên phát hành, đối tượng được phép nhận, điều kiện tin cậy và phạm vi tài nguyên. Token ngắn hạn không sửa được quan hệ tin cậy quá rộng hoặc workload bị gắn quyền vượt nhu cầu.

JIT và JEA có thể được áp dụng theo khả năng của hệ thống để giới hạn thời gian hoặc phạm vi thao tác. Không nên gán cơ học một quy trình phê duyệt tương tác của con người cho mọi lần chạy của một dịch vụ tự động; cần thiết kế phù hợp yêu cầu vận hành và bằng chứng kiểm soát.

### 9.4. Ứng phó sự cố

Khi một credential bị nghi lộ, inventory cần giúp trả lời nhanh:

1. Credential thuộc danh tính nào và còn phương thức xác thực nào khác?
2. Danh tính có quyền ở những tài nguyên nào?
3. Workload và nhóm nào sẽ bị ảnh hưởng khi thu hồi?
4. Có thể giảm phạm vi, thay credential hoặc tạm dừng consumer theo cách nào?
5. Cần giữ lại những log và bằng chứng gì?

Thu hồi credential không đồng nghĩa mọi kết nối, token hoặc phiên đã cấp đều chấm dứt ngay trên mọi nền tảng. Runbook phải xác định việc hủy phiên, thu hồi token hoặc cô lập bổ sung khi có liên quan.

## 10. Chỉ số đánh giá chất lượng inventory

Chỉ số cần đi kèm phạm vi, thời điểm và định nghĩa. Một tỷ lệ đẹp trên tập dữ liệu chưa đầy đủ có thể tạo cảm giác kiểm soát sai.

### 10.1. Tỷ lệ owner đã xác nhận

~~~text
Tỷ lệ owner xác nhận =
  Số danh tính trong phạm vi có owner xác nhận còn hiệu lực
  / Tổng số danh tính đã khám phá trong phạm vi
~~~

“Có tên owner” và “owner đã xác nhận” là hai điều khác nhau. Cần quy định xác nhận có hiệu lực đến khi nào hoặc sự kiện nào buộc xác nhận lại.

### 10.2. Tỷ lệ danh tính đã có liên kết consumer

~~~text
Tỷ lệ có liên kết consumer =
  Số danh tính có ít nhất một consumer được xác nhận bằng bằng chứng
  / Tổng số danh tính thuộc nhóm kỳ vọng có consumer
~~~

Chỉ số này cho biết đã có liên kết, không chứng minh đã tìm đủ mọi consumer. Theo dõi thêm số danh tính đang chờ xác minh phụ thuộc và các phát hiện consumer mới sau những lần đối soát.

Với tài khoản dự phòng, cần ghi runbook và nhu cầu dự kiến thay vì bịa một workload đang hoạt động để tăng tỷ lệ.

### 10.3. Độ bao phủ nguồn kiểm kê

~~~text
Độ bao phủ nguồn =
  Số nguồn hoặc hệ thống trong phạm vi đã thu thập và đối soát
  / Tổng số nguồn hoặc hệ thống đã cam kết trong phạm vi
~~~

Nguồn được đếm phải có tiêu chí hoàn tất rõ ràng. Chỉ kết nối được API mà chưa đọc đủ đối tượng hoặc không phát hiện lỗi phân trang chưa phải thu thập hoàn tất.

Không dùng số tài khoản trong vault làm mẫu số cho độ bao phủ toàn bộ danh tính máy. Cách đó loại bỏ ngay những tài khoản nằm ngoài vault mà chương trình cần phát hiện.

### 10.4. Ngoại lệ và độ mới dữ liệu

Theo dõi thêm:

- Tài khoản có quyền cao chưa rõ owner.
- Tài khoản có consumer chưa xác minh.
- Bản ghi quá hạn rà soát.
- Nguồn thu thập thất bại hoặc dữ liệu quá cũ.
- Ngoại lệ quá hạn và thời gian xử lý.
- Tài khoản mới phát hiện chưa có quyết định quản lý.

Độ mới cần đánh giá theo từng loại thông tin. Owner vừa xác nhận hôm qua không làm cho bản xuất quyền cách đây một năm trở thành dữ liệu quyền hiện hành.

## 11. Bài thực hành: kiểm kê một luồng xuất báo cáo

### 11.1. Bối cảnh

Dịch vụ Atlas Export tạo báo cáo doanh thu. Nhóm vận hành cung cấp các dữ kiện:

- Directory có tài khoản `svc_atlas_export`, đang được kích hoạt.
- Một job hằng đêm dùng tài khoản này để đọc dữ liệu và tạo tệp báo cáo.
- Cấu hình job production và staging đều tham chiếu cùng một credential.
- Vault đã có một bản ghi cho credential.
- Danh mục ứng dụng ghi owner là một nhân viên đã chuyển nhóm.
- Log cơ sở dữ liệu chỉ có 14 ngày, thấy hoạt động từ production.
- Runbook mô tả một tác vụ xuất lại dữ liệu khi khôi phục, nhưng chưa rõ nơi triển khai.
- Tài khoản có thêm quyền sửa cấu hình một thủ tục dữ liệu; chưa có bằng chứng nhu cầu.

### 11.2. Yêu cầu

Tạo bản ghi inventory và bảng hành động. Không suy đoán rằng staging không sử dụng tài khoản chỉ vì log hiện có chưa thấy hoạt động của staging.

Bản ghi phải có:

1. Định danh gồm miền quản lý và ID đối tượng nếu thu thập được.
2. Mục đích và các consumer đã biết, kèm trạng thái xác minh.
3. Owner được ghi nhận hiện tại và tình trạng chưa xác nhận.
4. Tham chiếu credential, không có giá trị secret.
5. Quyền đang biết và phần chưa giải thích được.
6. Cửa sổ log, giới hạn bằng chứng và dữ liệu còn thiếu.
7. Hành động có bên phụ trách và điều kiện nghiệm thu.

### 11.3. Hướng xử lý tham khảo

| Phát hiện | Cách ghi nhận | Hành động tiếp theo |
| --- | --- | --- |
| Owner cũ chuyển nhóm | Owner chưa xác nhận, chưa kết luận tài khoản vô chủ hoàn toàn | Nhóm vận hành dịch vụ nhận điều phối và tìm owner có trách nhiệm |
| Production và staging cùng tham chiếu credential | Hai consumer khai báo, cần đối chiếu trạng thái triển khai | Xác minh đường dùng thực tế và lập phương án tách danh tính phù hợp |
| Credential đã có trong vault | Có bằng chứng lưu trong vault, chưa đủ kết luận mọi consumer lấy từ đó | Kiểm tra cách phân phối và làm mới ở từng consumer |
| Tác vụ khôi phục chưa rõ | Phụ thuộc chưa được xác minh | Tìm cấu hình, owner runbook và kiểm thử có kiểm soát |
| Quyền sửa thủ tục chưa giải thích | Quyền có khả năng tác động cao hơn nhu cầu đọc được mô tả | Owner và bên quản trị dữ liệu xác nhận nhu cầu, thử giảm quyền |
| Log chỉ bao phủ 14 ngày | Không đủ chứng minh lịch sử dài hạn hoặc tác vụ chạy hiếm | Bổ sung bằng chứng cấu hình và chu kỳ nghiệp vụ |

Chưa nên tự động đổi credential hoặc vô hiệu hóa tài khoản chỉ từ các dữ kiện trên. Trước hết cần giải quyết các phụ thuộc chưa rõ, xác định phạm vi ảnh hưởng và chuẩn bị thay đổi phù hợp. Nếu có dấu hiệu xâm phạm đang diễn ra, quyết định cô lập hoặc thu hồi thuộc quy trình ứng phó sự cố và có thể được ưu tiên khác với một đợt cải thiện thông thường.

### 11.4. Tiêu chí hoàn thành

Bài thực hành đạt khi người khác đọc bản ghi có thể xác định:

- Đối tượng nào được kiểm kê và vì sao không bị nhầm với tài khoản trùng tên.
- Thông tin nào được xác nhận, thông tin nào mới là khai báo và thông tin nào chưa biết.
- Các workload đã biết và phụ thuộc còn cần kiểm tra.
- Quyền nào gây lo ngại và nguồn bằng chứng tương ứng.
- Ai nhận từng hành động và bằng chứng nào cho phép đóng hành động.
- Vì sao việc có bản ghi trong vault chưa đủ để ghi “đã kiểm soát đầy đủ”.

## 12. Câu hỏi tự kiểm tra

**1. Có thể tìm tất cả service account bằng tiền tố `svc_` không?**

Không. Tiền tố hỗ trợ phát hiện nhưng có thể bỏ sót tài khoản không theo chuẩn, danh tính workload hoặc credential cá nhân được dùng cho tự động hóa. Cần đối chiếu danh sách tài khoản với cấu hình và hoạt động.

**2. Vì sao không dùng tên tài khoản làm khóa duy nhất?**

Tên có thể trùng ở nhiều miền hoặc máy, có thể đổi và có thể được tái sử dụng sau khi xóa đối tượng cũ. Khóa nên bao gồm phạm vi quản lý và native ID khi có.

**3. Một tài khoản không có hoạt động trong cửa sổ log có phải là tài khoản bỏ hoang không?**

Chưa đủ kết luận. Cần xét độ bao phủ log, chu kỳ tác vụ, cấu hình consumer và xác nhận nhu cầu. “Không thấy” là một quan sát có giới hạn.

**4. Vì sao inventory không lưu mật khẩu để thuận tiện cho người vận hành?**

Inventory dùng để ra quyết định và đối soát, không phải nơi phân phối secret. Lưu secret ở đây mở rộng phạm vi lộ lọt và làm khó kiểm soát truy cập; nên dùng tham chiếu tới nơi quản lý được cấp quyền.

**5. Danh tính dùng token ngắn hạn có cần kiểm kê không?**

Có. Cần kiểm kê danh tính, quan hệ tin cậy, workload nhận token và quyền có thể được cấp. Không cần biến mỗi token tạm thời thành một tài khoản bền vững.

**6. Tài khoản đã vào vault có thể đánh dấu hoàn tất PAM không?**

Chỉ có thể xác nhận khía cạnh đã có bằng chứng. Vẫn cần kiểm tra consumer, credential khác, quyền, luân chuyển, giám sát và vòng đời theo mục tiêu kiểm soát.

**7. Khi owner chưa rõ, có nên điền tên người tạo tài khoản để đóng ngoại lệ?**

Không. Người tạo chỉ là đầu mối điều tra. Owner phải nhận trách nhiệm hiện tại; khoảng trống nên được ghi nhận và giao xử lý minh bạch.

## 13. Checklist áp dụng

Trước khi coi một đợt inventory là có thể sử dụng cho quyết định PAM, hãy kiểm tra:

- Phạm vi đã được xác định, có cả danh sách hệ thống chưa khảo sát.
- Danh tính được phân biệt bằng phạm vi quản lý và ID phù hợp.
- Mục đích, owner và consumer có trạng thái xác nhận cùng nguồn bằng chứng.
- Quyền và tài nguyên đích được mô tả đủ để hiểu phạm vi ảnh hưởng.
- Credential chỉ được tham chiếu bằng metadata, không xuất secret vào danh mục.
- Quan hệ dùng chung, khác môi trường và tác vụ chạy hiếm đã được ghi nhận.
- Hoạt động quan sát được có cửa sổ thời gian và giới hạn nguồn.
- Trạng thái vận hành, chất lượng inventory và mức triển khai kiểm soát được tách rõ.
- Dữ liệu chưa biết, mâu thuẫn và ngoại lệ đều có người xử lý.
- Có cơ chế cập nhật khi thay đổi và đối soát định kỳ.

Service account inventory có giá trị khi biến được danh tính máy từ một cái tên khó giải thích thành một đối tượng có mục đích, trách nhiệm, phụ thuộc và bằng chứng rõ ràng. Từ nền tảng đó, tổ chức mới có thể thu hẹp quyền, quản lý credential, kiểm soát truy cập và xử lý sự cố mà hiểu được tác động tới dịch vụ.
