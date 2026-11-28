# Phát hiện tài khoản đặc quyền

## 1. Discovery là bước xác định quyền đang thực sự tồn tại

Trong quản lý quyền truy cập đặc biệt (Privileged Access Management — PAM), **discovery** là quá trình tìm, chuẩn hóa và xác minh các tài khoản cùng đường cấp quyền có thể tác động đến tài nguyên nhạy cảm. Kết quả cần cho biết tài khoản nào có khả năng gì, trên tài nguyên nào, nhờ cơ chế nào, ai chịu trách nhiệm và bằng chứng còn đủ mới hay không.

Một danh sách người dùng có chữ admin trong tên chưa phải kết quả discovery đáng tin cậy. Tài khoản tên bình thường có thể là thành viên của nhiều nhóm lồng nhau rồi nhận quyền quản trị. Một tài khoản dịch vụ có thể sửa pipeline triển khai, từ đó tác động đến một danh tính triển khai mạnh hơn. Ngược lại, tài khoản tên admin-report có thể chỉ được xem báo cáo.

Discovery phục vụ các quyết định thực tế trong PAM:

- Kiểm kê quyền đặc biệt của con người, tài khoản dịch vụ và workload.
- Tìm quyền thường trực để thu hẹp theo least privilege hoặc chuyển sang JIT/JEA.
- Xác định credential và phụ thuộc cần quản lý bằng vault, luân chuyển hoặc cơ chế credential tạm thời.
- Xác định phiên và thao tác cần giám sát.
- Cung cấp bằng chứng cho kiểm toán và khoanh vùng khi ứng phó sự cố.

Phát hiện là bước tạo ra hiểu biết và bằng chứng. Nó không tự đồng nghĩa với việc đã thu hồi quyền, đưa credential vào vault hay bật giám sát phiên. Những việc đó cần được triển khai và xác minh riêng trên các hệ thống liên quan.

## 2. Phân biệt danh tính, tài khoản, credential và quyền

Nếu mô hình dữ liệu gộp các khái niệm này thành một cột “user”, discovery sẽ dễ trùng lặp hoặc bỏ sót.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Danh tính chủ thể | Con người hoặc workload mà tổ chức cần nhận diện | Nhân viên Lan; workload sao lưu dữ liệu |
| Tài khoản hoặc principal | Biểu diễn kỹ thuật được hệ thống dùng để xác thực hoặc phân quyền | Tài khoản cục bộ; tài khoản directory; service principal |
| Credential | Phương tiện chứng minh hoặc sử dụng danh tính | Mật khẩu, khóa, chứng thư, token |
| Nhóm hoặc role | Cấu trúc tập hợp chủ thể hoặc định nghĩa tập quyền | Nhóm vận hành; role quản trị cơ sở dữ liệu |
| Gán quyền | Quan hệ trao quyền trong một phạm vi và điều kiện cụ thể | Tài khoản được gán role trên một dự án |
| Quyền hiệu lực | Khả năng được hệ thống cho phép sau khi xét các quy tắc liên quan | Được thay đổi cấu hình xác thực trên máy đích |
| Chủ sở hữu chịu trách nhiệm | Cá nhân hoặc nhóm phải giải trình và quyết định vòng đời sử dụng | Nhóm nền tảng sở hữu tài khoản triển khai |

Một người có thể sở hữu nhiều tài khoản. Một tài khoản dùng chung có thể được nhiều người sử dụng. Một tài khoản dịch vụ có thể có nhiều credential. Do đó, số người, số tài khoản và số credential không thể thay thế cho nhau trong báo cáo.

Nhóm và role cần được kiểm kê để giải thích đường cấp quyền, nhưng không mặc nhiên được tính như các tài khoản đăng nhập. Một role có thể được nhận tạm thời; phiên phát sinh từ role cần được liên kết với chủ thể gốc thay vì bị coi là một người hoàn toàn mới.

Credential là một đối tượng cần quản trị, không phải lúc nào cũng là một danh tính độc lập. Ví dụ, nhiều khóa cùng thuộc một tài khoản không nên làm tài khoản đó bị đếm thành nhiều tài khoản đặc quyền khác nhau.

## 3. Định nghĩa “đặc quyền” trước khi tìm

Tài khoản đặc quyền là tài khoản có khả năng thực hiện các hành động với mức tác động cần được kiểm soát đặc biệt trong phạm vi đang xét. Không chỉ những quyền mang tên “administrator” mới thuộc phạm vi PAM.

Các nhóm khả năng đáng quan tâm gồm:

| Nhóm khả năng | Ví dụ về tác động |
|---|---|
| Quản trị hệ thống | Thay cấu hình hệ điều hành, quản lý dịch vụ, cài phần mềm |
| Quản trị danh tính | Tạo tài khoản, đặt lại credential, thêm người vào nhóm quản trị |
| Quản trị quyền | Gán role, sửa chính sách truy cập, thay điều kiện cấp quyền |
| Kiểm soát bí mật | Đọc, phát hành, thay đổi hoặc sử dụng credential nhạy cảm |
| Kiểm soát dữ liệu nhạy cảm | Đọc diện rộng, xuất dữ liệu, sửa hoặc xóa dữ liệu quan trọng |
| Kiểm soát cơ chế bảo vệ | Tắt log, đổi cấu hình giám sát, sửa chính sách bảo mật |
| Điều khiển hạ tầng và triển khai | Sửa pipeline, điều khiển agent, triển khai mã vào môi trường quan trọng |
| Khả năng mạo danh hoặc chuyển vai trò | Thực thi dưới danh tính khác hoặc nhận role mạnh hơn |

Cần gắn mỗi khả năng với tài nguyên và phạm vi. Quyền quản trị một môi trường thử nghiệm không tự trở thành quyền quản trị môi trường sản xuất. Quyền đọc một bảng công khai cũng khác quyền xuất toàn bộ dữ liệu khách hàng.

### 3.1. Quyền trực tiếp và quyền gián tiếp

**Quyền trực tiếp** được gán thẳng cho tài khoản, chẳng hạn một role quản trị trên máy chủ.

**Quyền gián tiếp** đến qua nhóm, role kế thừa, quan hệ nhận vai trò hoặc khả năng điều khiển thành phần đang dùng quyền mạnh hơn.

~~~text
Tài khoản Lan
  -> thành viên nhóm Vận hành
  -> nhóm Vận hành thuộc nhóm Quản trị máy chủ
  -> nhóm Quản trị máy chủ được quản trị máy S1
~~~

Chỉ liệt kê thành viên trực tiếp của nhóm Quản trị máy chủ có thể bỏ sót Lan. Discovery cần thu thập đủ các cạnh quan hệ để giải thích đường đi này.

Một đường khác có tính điều kiện:

~~~text
Tài khoản build-bot
  -> sửa được nội dung pipeline
  -> pipeline có thể chạy bằng danh tính triển khai
  -> danh tính triển khai có quyền trên môi trường sản xuất
~~~

Đường thứ hai cần xác minh thêm: thay đổi có bắt buộc duyệt không, người sửa có kích hoạt được không, credential có được cung cấp cho nhánh đó không, môi trường đích có giới hạn riêng không? Chỉ thấy hai đầu của đường đi chưa đủ khẳng định tài khoản đã có quyền thực thi toàn bộ hành động ở cuối đường.

### 3.2. Ứng viên khác với quyền đã xác minh

Một mô hình kết luận rõ ràng có thể gồm:

- **Ứng viên:** có dấu hiệu liên quan đến đặc quyền nhưng chưa đủ dữ liệu.
- **Đã xác minh theo bằng chứng:** dữ liệu và quy tắc liên quan đủ để kết luận có khả năng cụ thể trong phạm vi đã xét.
- **Chưa xác định:** thiếu chính sách, điều kiện hoặc dữ liệu cần thiết để kết luận.
- **Không thuộc định nghĩa đặc quyền đang áp dụng:** đã đánh giá và không đáp ứng tiêu chí đó trong phạm vi, thời điểm đã ghi nhận.

Không dùng một trạng thái “không đặc quyền” để chứa cả kết quả đã đánh giá và trường hợp chưa đọc được dữ liệu. Hai trường hợp này có ý nghĩa rủi ro khác nhau.

## 4. Xác định phạm vi và nguồn dữ liệu

Discovery nên bắt đầu bằng một danh sách nguồn đã được phép khảo sát: môi trường, tenant, directory, dự án, cụm, máy chủ, cơ sở dữ liệu hoặc thiết bị. Với mỗi nguồn, cần ghi phạm vi, người phụ trách, phương thức kết nối và giới hạn thu thập.

Danh sách tài sản hiện có giúp tạo phạm vi ban đầu nhưng có thể thiếu hệ thống. Vì vậy, cần đối chiếu với nhiều nguồn quản trị sẵn có như danh mục tài sản, nền tảng cấp phát, cấu hình kết nối và thông tin từ đội vận hành. Không diễn giải việc thiếu một tài sản trong danh mục thành bằng chứng tài sản đó không tồn tại.

Các nhóm nguồn thường cần xem xét:

| Nguồn | Đối tượng cần phát hiện | Quan hệ hoặc thông tin quan trọng |
|---|---|---|
| Directory hoặc nhà cung cấp danh tính | Tài khoản người dùng, nhóm, danh tính ứng dụng | Thành viên nhóm, nhóm lồng nhau, role, trạng thái tài khoản |
| Hệ điều hành và máy chủ | Tài khoản cục bộ, nhóm quản trị, tài khoản chạy dịch vụ | Quyền quản trị cục bộ, cơ chế nâng quyền, chủ thể thực thi dịch vụ |
| Nền tảng cloud | Principal, role, danh tính workload | Gán quyền, phạm vi tài nguyên, điều kiện và quan hệ nhận role |
| Cơ sở dữ liệu | Tài khoản, role và nhóm truy cập | Quyền quản trị, kế thừa role, phạm vi dữ liệu |
| Nền tảng container hoặc điều phối | Tài khoản dịch vụ, chủ thể được gán quyền | Role binding, phạm vi cụm hoặc namespace, khả năng điều khiển workload |
| CI/CD và tự động hóa | Tài khoản bot, agent, danh tính triển khai | Ai sửa được pipeline, ai kích hoạt được, danh tính thực thi |
| Thiết bị mạng và quản trị hạ tầng | Tài khoản quản trị thiết bị, nguồn xác thực tập trung | Mức quyền, phương thức truy cập, tài khoản khẩn cấp |
| Vault và hệ thống PAM hiện có | Tài khoản hoặc credential đã được quản lý | Chủ sở hữu, tài nguyên liên kết, trạng thái quản lý và luân chuyển |

Một tài khoản đã nằm trong vault chưa chắc là toàn bộ tài khoản đặc quyền của tài nguyên. Ngược lại, một tài khoản đặc quyền được phát hiện nhưng chưa có trong vault không mặc nhiên là sai phạm; có thể hệ thống dùng credential tạm thời hoặc cơ chế quản lý khác. Cần đối chiếu với chính sách áp dụng cho loại tài khoản đó.

Thông tin đăng nhập và log sử dụng giúp biết tài khoản có hoạt động gần đây hay không. Chúng không thay thế dữ liệu cấu hình quyền: không có log sử dụng chưa chứng minh rằng quyền không tồn tại.

## 5. Thiết kế luồng discovery có thể kiểm chứng

~~~mermaid
flowchart TD
    A[Xác định phạm vi và tiêu chí đặc quyền] --> B[Thu thập từ nguồn được phép]
    B --> C[Chuẩn hóa tài khoản và quan hệ]
    C --> D[Đánh giá quyền và điều kiện]
    D --> E[Liên kết chủ sở hữu và ngữ cảnh]
    E --> F[Đối soát kết quả và khoảng trống]
    F --> G[Ưu tiên xử lý và theo dõi thay đổi]
    G --> B
~~~

### 5.1. Thu thập bằng danh tính phù hợp

Dùng danh tính thu thập có quyền đọc cần thiết trong đúng phạm vi. Một số hệ thống yêu cầu quyền đọc dữ liệu bảo mật cao hơn quyền đọc thông thường; cần ghi nhận và giới hạn quyền đó thay vì mặc định cấp quyền quản trị toàn bộ cho collector.

Collector cần được quản lý như một danh tính dịch vụ có độ nhạy cao:

- Có người hoặc nhóm chịu trách nhiệm.
- Được giới hạn nguồn, tài nguyên và thao tác.
- Credential được bảo vệ, có vòng đời phù hợp.
- Hoạt động được ghi log để phân biệt với truy cập quản trị của con người.
- Không có quyền thay đổi cấu hình chỉ vì công việc hiện tại là đọc cấu hình.

Không kiểm chứng một đường đặc quyền bằng cách tự ý đăng nhập mạo danh, tạo tài khoản mới hoặc thực thi thay đổi trên hệ thống đích. Đánh giá cấu hình và bằng chứng là bước đầu; thử nghiệm chủ động chỉ thực hiện trong phạm vi được phép và có phương án vận hành riêng.

### 5.2. Thu thập cả trạng thái của lần thu thập

Ngoài các tài khoản và quan hệ, cần biết lần thu thập thành công đến đâu:

~~~text
source_id
scope_requested
scope_observed
collection_started_at
collection_finished_at
collection_result: complete | partial | failed
unreadable_objects
pagination_complete
collector_identity_reference
error_reference
~~~

Đây là mô hình trường thông tin minh họa. Trạng thái complete phải có ý nghĩa được định nghĩa, chẳng hạn đã đọc đủ tất cả trang dữ liệu của phạm vi đó theo khả năng API và quyền của collector. Nó không chứng minh rằng ngoài phạm vi không còn tài sản nào khác.

Nếu API chỉ trả về trang đầu hoặc bỏ qua đối tượng không đủ quyền đọc, kết quả không nên được công bố như một kiểm kê hoàn chỉnh. “Không có bản ghi” và “không đọc được bản ghi” phải có cách biểu diễn khác nhau.

### 5.3. Chuẩn hóa trước khi kết luận

Dữ liệu từ nguồn khác nhau cần được chuyển về mô hình chung nhưng vẫn giữ dấu vết nguồn. Không bỏ mất điều kiện cấp quyền, tên miền hoặc phạm vi tài nguyên chỉ để có một bảng ngắn hơn.

Ví dụ, hai bản ghi sau không nên bị gộp theo tên:

~~~text
source = host-A, account_id = local-1001, account_name = operator
source = host-B, account_id = local-1001, account_name = operator
~~~

Cả tên lẫn mã cục bộ có thể giống nhau trên hai máy khác nhau nhưng vẫn là hai tài khoản riêng biệt. Khóa nhận diện phải bao gồm phạm vi nguồn và loại đối tượng thích hợp.

## 6. Mô hình một bản ghi phát hiện

Một bản ghi hữu ích cần giữ được bằng chứng cho kết luận. Đoạn YAML dưới đây mô tả dữ liệu minh họa, không phải cấu hình cho một sản phẩm cụ thể:

~~~yaml
finding:
  finding_id: finding-042
  account:
    source_scope: directory-lab
    source_object_id: principal-218
    display_name: ops-lan
    type: human_admin
    enabled: true
  responsibility:
    owner_reference: team-platform
    owner_status: confirmed
  target:
    source_scope: host-lab
    resource_id: server-01
    environment: production
  privilege:
    capability: administer_operating_system
    assignment_kind: indirect_group_membership
    path:
      - principal-218
      - group-ops
      - group-server-admins
      - server-01
    assessment: verified_from_configuration
    conditions_reference: policy-evaluation-042
  evidence:
    source_references:
      - directory-observation-012
      - host-observation-031
    observed_at: '2026-11-26T03:00:00Z'
    collection_run: run-007
    collection_result: complete
  lifecycle:
    review_state: awaiting_owner_review
    management_state: not_yet_assessed
~~~

Giá trị verified_from_configuration chỉ nêu loại bằng chứng, không giả vờ đã thực hiện đăng nhập thành công. Nếu đã có kiểm chứng được phép tại điểm đích, cần ghi loại bằng chứng bổ sung đó riêng.

Những nhóm dữ liệu thường cần có:

| Nhóm | Câu hỏi mà dữ liệu phải trả lời |
|---|---|
| Định danh ổn định | Đây là đối tượng nào tại nguồn nào? |
| Tài nguyên và phạm vi | Quyền áp dụng trên đâu, trong môi trường nào? |
| Khả năng và đường cấp quyền | Làm được gì, trực tiếp hay qua những quan hệ nào? |
| Điều kiện và giới hạn | Có cửa sổ thời gian, phê duyệt, điều kiện ngữ cảnh hoặc giới hạn khác không? |
| Trách nhiệm | Ai chịu trách nhiệm, đã xác nhận hay mới suy đoán? |
| Bằng chứng và độ mới | Dựa trên nguồn nào, quan sát lúc nào, nguồn có đọc đủ không? |
| Trạng thái xử lý | Đã được xét duyệt, quản lý hoặc chấp nhận ngoại lệ chưa? |

Không lưu giá trị mật khẩu, private key hoặc token vào bản ghi discovery. Nếu cần nối với vault hoặc hệ thống cấp credential, dùng mã tham chiếu và metadata được phép đọc.

## 7. Nhận diện trùng lặp và liên kết danh tính

### 7.1. Khóa kỹ thuật và tên hiển thị

Tên tài khoản có thể đổi; địa chỉ thư có thể thay đổi hoặc được tái sử dụng; tài khoản bị xóa có thể được tạo lại với tên cũ. Cần ưu tiên mã đối tượng ổn định do nguồn cung cấp và giữ kèm phạm vi nguồn.

Ví dụ khóa logic:

~~~text
account_key = (source_scope, object_type, source_object_id)
~~~

Ngay cả với mã ổn định, phải hiểu quy tắc vòng đời tại nguồn. Nếu hệ thống cho phép tái sử dụng mã sau khi xóa, cần thêm bằng chứng tạo mới hoặc thông tin phiên bản để không nối nhầm lịch sử.

### 7.2. Một người có nhiều tài khoản

Lan có thể có tài khoản làm việc thông thường, tài khoản quản trị directory và tài khoản cục bộ khẩn cấp được giao trách nhiệm. Liên kết chúng với Lan giúp xét quyền tổng thể, nhưng các tài khoản vẫn cần vòng đời và bằng chứng độc lập.

Không gộp tất cả thành một dòng khiến mất thông tin tài khoản nào được khóa, tài khoản nào đang hoạt động và tài khoản nào còn credential chưa được quản lý.

### 7.3. Tài khoản dịch vụ và tài khoản dùng chung

Tên svc-backup là một dấu hiệu, không phải chứng minh đầy đủ về loại tài khoản. Cần đối chiếu với dịch vụ sử dụng, cấu hình triển khai và đội sở hữu. Một tài khoản dịch vụ vẫn có thể bị con người dùng để đăng nhập nếu hệ thống không giới hạn.

Với tài khoản dùng chung, cần phân biệt:

- Chủ sở hữu chịu trách nhiệm về tài khoản.
- Những người được phép sử dụng.
- Người thực sự đã sử dụng trong một phiên cụ thể.

Không lấy người đăng nhập gần nhất làm chủ sở hữu mặc định. Việc gán sai chủ sở hữu có thể làm quy trình xét duyệt quyền trở nên hình thức.

## 8. Đánh giá quyền hiệu lực và đường đặc quyền

Một phép hợp đơn giản của tất cả role chưa chắc phản ánh quyền hiệu lực. Nhiều hệ thống còn xét điều kiện, giới hạn phạm vi, trạng thái kích hoạt, quy tắc từ chối hoặc cơ chế phân quyền riêng.

Một cách đánh giá có cấu trúc:

1. Bắt đầu từ tài khoản hoặc principal cần xét.
2. Mở rộng các quan hệ thành viên nhóm và kế thừa trong phạm vi được phép.
3. Xác định role, khả năng nhận role và gán quyền liên quan.
4. Gắn từng quyền với tài nguyên và điều kiện áp dụng.
5. Đánh giá theo ngữ nghĩa của hệ thống đích, gồm các cơ chế giới hạn liên quan.
6. Ghi lại đường cấp quyền, kết luận và phần dữ liệu còn thiếu.

Mã giả để tìm các đường ứng viên:

~~~text
for principal in discovered_principals:
    relationships = traverse_authorized_relationships(
        principal,
        stop_on_cycle = true,
        stay_inside_allowed_scope = true
    )

    for candidate_path in relationships:
        if candidate_path.is_incomplete:
            record_unknown(candidate_path, missing_evidence)
            continue

        evaluation = evaluate_target_authorization_semantics(
            candidate_path,
            observed_policies,
            applicable_conditions
        )

        record_assessment(candidate_path, evaluation, evidence_references)
~~~

Đây là mô tả thuật toán, không phải một bộ đánh giá quyền dùng chung cho mọi nền tảng. Cần xử lý vòng lặp nhóm, phân trang và giới hạn độ sâu. Nếu dừng duyệt vì giới hạn kỹ thuật, ghi là đường đi chưa được khảo sát đủ; không kết luận rằng không còn quyền gián tiếp.

### 8.1. Quyền đủ điều kiện kích hoạt khác quyền đang hoạt động

Một người có thể đủ điều kiện nhận role JIT nhưng chưa kích hoạt. Discovery nên lưu cả hai trạng thái:

- Có khả năng yêu cầu hoặc kích hoạt quyền theo chính sách.
- Quyền hiện đang hoạt động, với hạn cuối nếu có.

Cả hai đều quan trọng, nhưng không nên báo cáo mọi quyền đủ điều kiện như quyền quản trị thường trực đang hoạt động. Đồng thời, khả năng tự kích hoạt một role mạnh vẫn cần được xét về điều kiện, kiểm soát và bằng chứng.

### 8.2. Đường điều khiển gián tiếp cần mô tả điều kiện

Một tài khoản sửa được pipeline chưa chắc sửa được pipeline chạy trên sản xuất. Một người quản trị một kho mã chưa chắc đọc được credential triển khai. Cần ghi rõ các điều kiện nối đường đi thay vì biến đồ thị ứng viên thành một kết luận chắc chắn.

Nếu chưa đọc được cấu hình bảo vệ nhánh, quy tắc phê duyệt hoặc phạm vi cấp bí mật, giữ đường đi ở trạng thái chưa xác định và yêu cầu xác minh. Không cần thực hiện hành vi khai thác để mô tả điều kiện còn thiếu.

## 9. Tìm chủ sở hữu và ưu tiên xử lý

Kết quả discovery cần có người tiếp nhận. Một phát hiện đặc quyền không có chủ sở hữu dễ nằm mãi trong báo cáo mà không được xử lý.

Nguồn liên kết chủ sở hữu có thể gồm danh mục ứng dụng, hồ sơ cấp tài khoản, cấu hình triển khai, nhóm vận hành và xác nhận của quản lý tài nguyên. Cần ghi mức độ xác nhận: đã xác nhận, suy đoán từ nguồn nào hoặc chưa xác định.

**Không xác định được chủ sở hữu** là một trạng thái cần điều tra, không tự động là lệnh xóa tài khoản. Tài khoản đó có thể đang phục vụ sao lưu, khôi phục, tích hợp hoặc tác vụ định kỳ quan trọng.

Ưu tiên nên xét nhiều chiều:

| Yếu tố | Ví dụ cần chú ý |
|---|---|
| Mức tác động | Có thể đổi quyền, đọc bí mật, tắt giám sát hoặc tác động nhiều tài nguyên |
| Phạm vi tài nguyên | Hạ tầng sản xuất, danh tính trung tâm, dữ liệu nhạy cảm |
| Khả năng truy cập | Đường đăng nhập trực tiếp, đường quản trị qua nhiều hệ thống |
| Mức tồn tại | Quyền thường trực, credential dài hạn, tài khoản dùng chung |
| Quản trị vòng đời | Không có chủ sở hữu, người sở hữu đã rời tổ chức, thiếu mục đích sử dụng |
| Dấu hiệu sử dụng | Hoạt động bất thường hoặc không phù hợp chức năng được khai báo |
| Chất lượng bằng chứng | Nguồn chưa đủ hoặc quá cũ khiến mức phơi nhiễm chưa xác định |

Không có dấu hiệu sử dụng gần đây không đồng nghĩa không cần tài khoản. Tài khoản khẩn cấp có thể hiếm khi dùng nhưng vẫn phải được quản lý chặt. Ngược lại, hoạt động thường xuyên không chứng minh rằng quyền rộng là hợp lý.

Các hướng xử lý sau xác nhận có thể là: giữ quyền với phạm vi hẹp hơn, chuyển sang JIT/JEA, quản lý credential bằng vault, dùng danh tính workload phù hợp, giám sát phiên hoặc loại bỏ quyền không còn cần thiết. Với tài khoản dịch vụ, phải xác định phụ thuộc và phương án khôi phục trước khi đổi credential hoặc thu hồi quyền.

## 10. Discovery liên tục và đối soát thay đổi

Discovery một lần chỉ mô tả các nguồn đã quan sát tại thời điểm đó. Tài khoản mới, role mới, quyền tạm thời và thay đổi nhóm có thể xuất hiện ngay sau lần thu thập.

Nên phối hợp:

- **Thu thập theo sự kiện:** nhận thay đổi từ nguồn hỗ trợ để giảm độ trễ phát hiện.
- **Đối soát định kỳ:** đọc lại trạng thái trong phạm vi để phát hiện sự kiện bị bỏ lỡ và sửa sai lệch.
- **Khảo sát theo yêu cầu:** cập nhật các nguồn liên quan khi có thay đổi lớn hoặc sự cố.

Sự kiện có thể đến trễ, trùng hoặc sai thứ tự. Mỗi lần cập nhật cần giữ dấu thời gian, mã đối tượng và khả năng nhận diện sự kiện đã xử lý. Một sự kiện cũ không nên tự ghi đè trạng thái mới hơn mà không có quy tắc đối soát.

### 10.1. Không thấy lại không có nghĩa đã bị xóa

Giả sử lần trước có svc-backup, lần sau không thấy. Các khả năng gồm:

- Tài khoản đã được xóa.
- Tài khoản chuyển sang phạm vi khác.
- Collector mất quyền đọc.
- API lỗi hoặc trả thiếu trang.
- Bộ lọc hoặc cấu hình thu thập thay đổi.

Chỉ nên kết luận xóa hoặc mất quyền khi có bằng chứng phù hợp: sự kiện xóa đáng tin cậy, phản hồi xác nhận tại nguồn hoặc một lần đối soát hoàn chỉnh với ngữ nghĩa nguồn cho phép kết luận đó. Trong thời gian chưa rõ, giữ bản ghi lịch sử và đánh dấu cần xác minh.

### 10.2. Quyền ngắn hạn và danh tính tạm thời

Một role JIT tồn tại vài phút có thể không xuất hiện trong một lần quét hàng ngày. Với trường hợp này, cần khai thác dữ liệu cấp quyền hoặc sự kiện kích hoạt bên cạnh ảnh chụp trạng thái.

Không đếm mỗi phiên tạm thời như một tài khoản quản trị lâu dài. Nên liên kết phiên với danh tính gốc, lần cấp quyền, thời hạn và tài nguyên. Mặt khác, không bỏ qua sự tồn tại của phiên đặc quyền chỉ vì principal gốc có vẻ không có quyền thường trực.

## 11. Độ bao phủ và chất lượng kết quả

“Đã tìm thấy 200 tài khoản” là số lượng quan sát, không cho biết đã khám phá được bao nhiêu phần của môi trường.

Một báo cáo độ bao phủ cần phân biệt:

| Chỉ số | Cách hiểu |
|---|---|
| Tài nguyên trong phạm vi đã biết | Mẫu số theo danh sách nguồn đang được quản lý |
| Tài nguyên thu thập hoàn chỉnh | Đọc đủ dữ liệu cần thiết theo tiêu chí đã định nghĩa |
| Tài nguyên thu thập một phần | Đã có dữ liệu nhưng thiếu đối tượng, quyền đọc hoặc quan hệ |
| Tài nguyên thu thập thất bại | Không có lần thu thập hợp lệ cho kỳ quan sát |
| Phát hiện chưa rõ chủ sở hữu | Đã tìm thấy nhưng chưa gắn trách nhiệm xác nhận |
| Phát hiện chưa đánh giá đủ quyền | Có đường ứng viên nhưng thiếu điều kiện hoặc bằng chứng |
| Bản ghi quá thời gian làm mới | Bằng chứng cũ hơn ngưỡng phù hợp với rủi ro của nguồn |

Ví dụ, có 12 máy chủ trong phạm vi đã biết: 9 máy thu thập hoàn chỉnh, 2 máy một phần và 1 máy thất bại. Tỷ lệ hoàn chỉnh của phạm vi đó là 9 / 12 = 75%. Không nên cộng 2 máy một phần rồi công bố đã hoàn chỉnh hơn 90%.

Con số 75% cũng không mô tả các máy chủ chưa có trong danh sách phạm vi. Báo cáo cần nêu cơ sở hình thành mẫu số và thời điểm cập nhật danh sách tài sản.

Trong 9 máy thu thập hoàn chỉnh, nếu có 8 tài khoản có quyền trực tiếp và thêm 4 tài khoản khác chỉ có quyền gián tiếp, có thể báo 12 tài khoản đặc quyền khác nhau trong tập đã quan sát. Nếu một tài khoản xuất hiện ở cả hai nhóm thì phải khử trùng theo định danh trước khi tính tổng.

Không nên dùng một điểm tin cậy duy nhất để che mất các thiếu hụt quan trọng. Một kết quả có đầy đủ chủ sở hữu nhưng thiếu dữ liệu quyền đích vẫn chưa đủ để xác nhận quyền hiệu lực.

## 12. Thu thập an toàn và bảo vệ dữ liệu discovery

Dữ liệu discovery là bản đồ các điểm quyền lực của hệ thống. Nếu bị lộ, nó có thể giúp người khác biết tài khoản nào có khả năng quản trị, tài nguyên nào quan trọng và đường cấp quyền nào đáng chú ý.

Các nguyên tắc vận hành:

1. **Giới hạn phạm vi:** chỉ kết nối nguồn đã được phép; không tự mở rộng sang mạng, tenant hoặc môi trường khác khi thấy quan hệ tham chiếu.
2. **Ưu tiên truy vấn đọc:** dùng API và kênh quản trị phù hợp để đọc cấu hình. Không tự đổi membership, đặt lại mật khẩu hoặc thử credential trong luồng discovery thông thường.
3. **Không thu bí mật không cần thiết:** thu metadata và tham chiếu. Tránh kéo toàn bộ nội dung cấu hình hoặc biến môi trường khi chỉ cần tên chủ thể và quan hệ quyền.
4. **Kiểm soát tải:** giới hạn đồng thời, phân trang đúng và thử lại có giới hạn để không làm nghẽn directory, thiết bị hoặc dịch vụ quản trị.
5. **Tôn trọng lỗi xác thực:** không lặp vô hạn một credential lỗi; việc thử lại không kiểm soát có thể gây khóa tài khoản hoặc nhiễu cảnh báo.
6. **Bảo vệ kết quả:** giới hạn người xem, bảo vệ đường truyền và nơi lưu, ghi log truy cập, đặt thời gian lưu phù hợp.
7. **Giữ dấu vết thay đổi:** mọi quyết định sau discovery cần nối được với phát hiện, bằng chứng và người xét duyệt.

Nếu phải đọc một cấu hình có thể chứa bí mật, cần có cơ chế chỉ lấy trường cần thiết hoặc loại bỏ dữ liệu nhạy cảm trước khi lưu vào kết quả và log. Không đưa credential vào báo cáo để “chứng minh có quyền”.

## 13. Ví dụ xử lý một đợt discovery

Một đội nền tảng muốn kiểm kê quyền trên máy chủ ứng dụng, cơ sở dữ liệu và hệ thống triển khai. Mục tiêu là tìm quyền thường trực, tài khoản dịch vụ chưa có người chịu trách nhiệm và các đường truy cập ngoài cơ chế PAM đang có.

### 13.1. Những phát hiện ban đầu

| Phát hiện | Bằng chứng hiện có | Kết luận ban đầu |
|---|---|---|
| ops-lan quản trị máy ứng dụng | Đường nhóm lồng nhau và gán quyền tại máy | Đặc quyền gián tiếp đã được xác minh từ cấu hình |
| svc-backup có quyền quản trị cơ sở dữ liệu | Gán role trực tiếp; chưa có chủ sở hữu xác nhận | Đặc quyền đã xác minh, trách nhiệm chưa rõ |
| build-bot sửa được pipeline triển khai | Có quyền sửa pipeline; chưa đọc đủ điều kiện chạy sản xuất | Đường đặc quyền ứng viên, cần bổ sung bằng chứng |
| admin-report chỉ xem trạng thái | Đã đọc đủ chính sách cho phạm vi xem trạng thái | Không phân loại là quản trị chỉ dựa vào tên |
| break-glass-01 ít khi sử dụng | Tài khoản khẩn cấp được khai báo; quyền tại đích đã xác minh | Vẫn là tài khoản đặc quyền cần quản lý |

### 13.2. Xác minh và chuyển sang xử lý

Với ops-lan, đội cần xác nhận mục đích công việc và phạm vi quyền. Nếu nhiệm vụ chỉ cần khởi động lại một dịch vụ, có thể đề xuất JEA thay cho quyền quản trị toàn máy và JIT thay cho membership thường trực.

Với svc-backup, chưa vội khóa hoặc đổi mật khẩu. Đội xác định ứng dụng, lịch chạy, các nơi sử dụng credential và người chịu trách nhiệm. Sau đó mới lập phương án giảm role hoặc quản lý credential có kiểm chứng phục hồi.

Với build-bot, thu thập tiếp các điều kiện pipeline trong đúng phạm vi được phép. Nếu thiếu quyền đọc, phát hiện vẫn giữ trạng thái chưa xác định; không nâng thành “đã kiểm soát sản xuất” hoặc đóng là “an toàn”.

Với break-glass-01, mục tiêu là xác nhận cơ chế kiểm soát truy cập khẩn cấp, người chịu trách nhiệm, giám sát sử dụng và xử lý credential sau sử dụng. Việc không có đăng nhập gần đây không phải lý do đủ để loại khỏi kiểm kê.

### 13.3. Theo dõi thay đổi sau xử lý

Sau khi áp dụng thay đổi, cần đọc lại nguồn đích để xác nhận quyền đã giảm, cơ chế JIT/JEA hoạt động đúng hoặc credential đã được quản lý theo thiết kế. Một ticket được đóng chưa đủ chứng minh trạng thái quyền tại đích đã thay đổi.

Discovery tiếp tục quan sát để phát hiện membership bị thêm lại, tài khoản dịch vụ mới hoặc một đường truy cập khác thay thế đường vừa loại bỏ.

## 14. Bài thực hành với dữ liệu giả lập

Bài thực hành này có thể làm bằng bảng và sơ đồ, không cần quét mạng hay sử dụng credential thật.

### 14.1. Dữ liệu đầu vào

Có ba tài nguyên: máy S1, cơ sở dữ liệu D1 và pipeline P1. Mọi mã dưới đây đều là giả lập.

| Chủ thể | Quan hệ đã quan sát | Thông tin bổ sung |
|---|---|---|
| ops-lan | Thành viên nhóm G-ops; G-ops thuộc G-admin; G-admin quản trị S1 | Đã đọc đủ các quan hệ liên quan |
| svc-backup | Được gán role quản trị trên D1 | Chưa xác nhận chủ sở hữu |
| build-bot | Sửa được P1; P1 có thể dùng danh tính triển khai | Chưa thu thập quy tắc phê duyệt và điều kiện cấp credential |
| admin-report | Chỉ đọc trạng thái S1 | Đã đánh giá đủ quyền trong phạm vi bài tập |
| orphan-ops | Được gán quyền quản trị trực tiếp trên S1 | Hồ sơ người phụ trách không còn hợp lệ |
| break-glass-01 | Có quyền quản trị trực tiếp trên S1 | Được khai báo dùng khẩn cấp, hiếm hoạt động |

### 14.2. Yêu cầu thực hiện

1. Tạo bản ghi riêng cho từng tài khoản, giữ mã nguồn và tài nguyên liên quan.
2. Vẽ đường quyền gián tiếp của ops-lan và nêu bằng chứng cần có ở từng cạnh.
3. Phân loại kết luận về đặc quyền; không dùng tên tài khoản làm tiêu chí quyết định.
4. Tách trạng thái đánh giá quyền khỏi trạng thái xác nhận chủ sở hữu.
5. Đề xuất dữ liệu cần bổ sung cho build-bot.
6. Chọn thứ tự xác minh tiếp và giải thích bằng mức tác động, độ rõ của bằng chứng và trách nhiệm sở hữu.

Kết quả mong đợi là có bốn tài khoản đã được xác minh có quyền quản trị theo dữ liệu bài tập: ops-lan, svc-backup, orphan-ops và break-glass-01. Tài khoản build-bot là đường ứng viên chưa đủ điều kiện để kết luận. Tài khoản admin-report không bị gắn nhãn quản trị chỉ vì có chữ admin.

### 14.3. Tình huống đối soát

Ở lần thu thập kế tiếp, collector không đọc được danh sách tài khoản của D1, đồng thời không thấy svc-backup trong kết quả mới.

Kết luận phù hợp là trạng thái mới của tài khoản tại D1 chưa xác định vì thu thập thất bại. Giữ bằng chứng lần trước, đánh dấu độ mới và xử lý lỗi nguồn. Không ghi tài khoản đã bị xóa, đã hết quyền hoặc đã được khắc phục chỉ vì nó vắng mặt trong kết quả mới.

Sau đó, giả sử một lần đọc hoàn chỉnh xác nhận role quản trị của svc-backup đã được thay bằng role hẹp hơn. Bản ghi mới cần giữ sự thay đổi cùng mốc thời gian và bằng chứng; lịch sử trước đó vẫn hữu ích cho kiểm toán và điều tra.

## 15. Những lỗi làm discovery mất giá trị

| Lỗi | Hậu quả | Cách cải thiện |
|---|---|---|
| Tìm theo tên admin, root, svc là chính | Bỏ sót tài khoản tên bình thường và báo nhầm tài khoản tên gợi ý | Dựa trên khả năng, gán quyền và đường quan hệ |
| Chỉ đọc tài khoản con người | Bỏ sót bot, dịch vụ, danh tính triển khai và workload | Kiểm kê cả danh tính phi con người |
| Chỉ đọc nhóm trực tiếp | Bỏ sót quyền qua nhóm lồng nhau hoặc role kế thừa | Thu thập và đánh giá đầy đủ đường cấp quyền |
| Gộp theo username | Nối nhầm tài khoản giữa các máy, tenant hoặc lần tạo mới | Dùng định danh có phạm vi nguồn và giữ lịch sử vòng đời |
| Coi mọi role được liệt kê là quyền hiệu lực | Không phản ánh điều kiện, trạng thái và giới hạn | Đánh giá theo ngữ nghĩa hệ thống đích; ghi phần chưa rõ |
| Coi lỗi đọc là không có quyền | Tạo kết quả âm tính giả | Báo rõ partial, failed và dữ liệu thiếu |
| Chỉ báo số tài khoản đã tìm thấy | Không thể đánh giá độ bao phủ | Báo cả phạm vi, chất lượng thu thập và độ mới |
| Tự đổi credential ngay sau phát hiện | Có thể làm hỏng dịch vụ và tác vụ nền | Xác định phụ thuộc, chủ sở hữu và phương án thay đổi trước |
| Tuyên bố đã quản lý vì đã phát hiện | Nhầm kiểm kê với kiểm soát đang thực thi | Theo dõi riêng trạng thái discovery và trạng thái quản lý PAM |

Một kết quả discovery dùng được phải nối được tài khoản với khả năng cụ thể, tài nguyên, đường cấp quyền, trách nhiệm và bằng chứng. Khi còn thiếu dữ liệu, việc chỉ ra chính xác khoảng trống giúp đội vận hành đưa ra quyết định đáng tin cậy hơn một danh sách tài khoản dài nhưng không giải thích được quyền đến từ đâu.
