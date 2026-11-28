# Phát hiện tài khoản không owner

## 1. Vì sao thiếu owner là một khoảng trống trong PAM?

Trong quản lý quyền truy cập đặc biệt (Privileged Access Management — PAM), một tài khoản có quyền mạnh cần có **owner**, tức cá nhân hoặc nhóm được tổ chức giao trách nhiệm giải trình về mục đích, phạm vi quyền và vòng đời của tài khoản.

Tài khoản không có owner được xác nhận thường khó trả lời các câu hỏi vận hành:

- Tài khoản phục vụ người dùng, ứng dụng hay công việc nào?
- Ai xác nhận rằng quyền quản trị hiện tại còn cần thiết?
- Ai đánh giá ảnh hưởng trước khi đổi mật khẩu, khóa tài khoản hoặc giảm quyền?
- Ai chịu trách nhiệm khi tài khoản xuất hiện trong một sự cố?
- Ai phê duyệt việc tiếp tục sử dụng hoặc ngừng sử dụng?

Ví dụ, tài khoản svc-payroll có quyền quản trị cơ sở dữ liệu và đã được đưa vào vault. Trường owner vẫn trỏ tới một nhân viên đã rời công ty. Mật khẩu được bảo vệ không giải quyết được việc thiếu người xác nhận phụ thuộc, xét duyệt quyền và tiếp nhận xử lý sự cố.

Bài toán discovery ở đây là tìm các tài khoản **thiếu một quan hệ trách nhiệm hợp lệ và có thể vận hành**, đồng thời phân biệt chúng với trường hợp chỉ thiếu dữ liệu. Kết quả cần dẫn tới việc xác nhận owner, điều chỉnh kiểm soát hoặc xử lý vòng đời tài khoản dựa trên bằng chứng.

## 2. Owner là trách nhiệm, không chỉ là một trường dữ liệu

### 2.1. Một quan hệ ownership hợp lệ cần gì?

Một bản ghi tên hoặc địa chỉ thư chưa đủ. Quan hệ ownership nên đáp ứng các điều kiện phù hợp với chính sách tổ chức:

1. Xác định được tài khoản và phạm vi tài nguyên mà owner chịu trách nhiệm.
2. Tham chiếu tới cá nhân hoặc nhóm còn hợp lệ.
3. Có căn cứ giao trách nhiệm, chẳng hạn hồ sơ được duyệt hoặc xác nhận có thẩm quyền.
4. Có đầu mối tiếp nhận xét duyệt quyền, thay đổi và sự cố.
5. Có thời điểm xác nhận và quy tắc rà soát lại.

Owner có thể là **một nhóm chịu trách nhiệm**, không bắt buộc luôn là một cá nhân. Tuy nhiên, tên nhóm tồn tại trong directory chưa chứng minh nhóm đang vận hành, có người tiếp nhận hoặc đã chấp nhận trách nhiệm đối với tài khoản.

Một mô hình gồm nhóm chịu trách nhiệm và đầu mối vận hành có thể phù hợp hơn việc gắn lâu dài một tài khoản dịch vụ với người đã tạo nó.

### 2.2. Những vai trò thường bị nhầm với owner

| Vai trò hoặc dấu vết | Cho biết điều gì? | Vì sao chưa đủ để kết luận là owner? |
|---|---|---|
| Người tạo tài khoản | Ai thực hiện thao tác cấp ban đầu | Có thể là nhân viên hỗ trợ làm theo yêu cầu |
| Người đăng nhập gần nhất | Ai có hoạt động sử dụng được ghi nhận | Có thể chỉ đang xử lý sự cố hoặc dùng tài khoản được chia sẻ |
| Người giữ credential | Ai có quyền truy cập bí mật hoặc vận hành vault | Không nhất thiết quyết định mục đích và quyền của tài khoản |
| Chủ sở hữu máy chủ | Đội quản lý tài nguyên chứa tài khoản | Tài khoản có thể phục vụ ứng dụng của đội khác |
| Người phê duyệt yêu cầu cũ | Ai duyệt tại một thời điểm | Trách nhiệm có thể đã thay đổi |
| Giá trị owner của đối tượng kỹ thuật | Quan hệ sở hữu theo cơ chế của nền tảng | Có thể khác trách nhiệm quản trị theo chính sách PAM |
| Người phụ trách ứng dụng | Ai chịu trách nhiệm với ứng dụng | Chỉ là owner tài khoản khi có quan hệ ứng dụng–tài khoản và quy tắc trách nhiệm hợp lệ |

Có thể tách người chịu trách nhiệm về nghiệp vụ, người quản trị kỹ thuật và người quản lý credential thành các vai trò riêng. Điều quan trọng là các vai trò được mô tả rõ, không để mọi bên cùng nghĩ rằng bên khác đang chịu trách nhiệm.

### 2.3. Ownership trực tiếp và ownership qua ứng dụng

Một tài khoản có thể có owner gán trực tiếp. Một tài khoản khác có thể được quản lý theo quan hệ:

~~~text
Tài khoản dịch vụ
  -> được dùng riêng cho ứng dụng A
  -> ứng dụng A thuộc nhóm vận hành T
  -> chính sách giao T chịu trách nhiệm với tài khoản của A
  -> T đã xác nhận phạm vi và đầu mối tiếp nhận
~~~

Mô hình gián tiếp này có thể hợp lệ nếu được chính sách cho phép và có đủ bằng chứng. Không nên gắn nhãn “không owner” chỉ vì trường owner trực tiếp để trống.

Ngược lại, một nhãn application=A chưa đủ chứng minh cả chuỗi trên. Tài khoản có thể dùng chung cho nhiều ứng dụng, nhãn có thể cũ hoặc đội sở hữu ứng dụng chưa chấp nhận quản lý tài khoản đó.

## 3. Phân loại các dạng thiếu ownership

Cần dùng trạng thái đủ rõ để đội vận hành biết phải xác minh điều gì.

| Trạng thái minh họa | Dấu hiệu | Cách diễn giải |
|---|---|---|
| CONFIRMED_OWNER | Quan hệ trách nhiệm hợp lệ đã được xác nhận | Có owner theo tiêu chí đang áp dụng |
| MISSING_OWNER_RECORD | Đã đọc đủ nguồn bắt buộc nhưng không có quan hệ ownership hợp lệ được ghi nhận | Chưa có owner được ghi nhận; không khẳng định rằng không ai biết tài khoản |
| INVALID_OWNER_REFERENCE | Tham chiếu owner không còn nhận diện được hoặc trỏ sai đối tượng | Cần sửa quan hệ và xác nhận trách nhiệm |
| INACTIVE_OWNER | Cá nhân đã rời vai trò hoặc tổ chức; nhóm đã giải thể | Trách nhiệm cần được chuyển giao |
| UNRESOLVED_OWNER | Có dấu vết hoặc ứng viên nhưng chưa được xác nhận | Không tự động gán theo suy đoán |
| CONFLICTING_OWNER | Các nguồn đưa ra trách nhiệm mâu thuẫn trong cùng phạm vi | Cần phân xử hoặc làm rõ ranh giới trách nhiệm |
| DATA_GAP | Không đủ quyền đọc, dữ liệu quá cũ hoặc nguồn thu thập lỗi | Chưa đủ bằng chứng để kết luận ownership |

Tên trạng thái là mô hình để học, không phải chuẩn cấu hình của một sản phẩm cụ thể.

Một tài khoản có thể đồng thời có nhiều vấn đề, chẳng hạn owner đã nghỉ việc và thông tin ứng dụng không rõ. Nên lưu các lý do riêng thay vì ép mọi tình huống vào một nhãn duy nhất.

**Tài khoản mồ côi** thường được dùng để chỉ tài khoản không còn liên hệ hợp lệ với chủ thể hoặc đơn vị chịu trách nhiệm. Khi dùng thuật ngữ này, phải nêu tiêu chí cụ thể. Không lấy việc “không thấy đăng nhập gần đây” làm định nghĩa tài khoản mồ côi.

## 4. Những loại tài khoản cần được đưa vào phạm vi

Tài khoản không owner có thể xuất hiện ở nhiều lớp hạ tầng:

| Loại tài khoản | Nguyên nhân dễ mất owner | Điểm cần xác minh |
|---|---|---|
| Tài khoản quản trị cá nhân | Nhân viên rời công ty, chuyển bộ phận hoặc thay vai trò | Liên kết với người dùng, quyền còn lại, trạng thái tại từng hệ thống |
| Tài khoản quản trị cục bộ | Được tạo khi xử lý sự cố hoặc bởi bên triển khai | Người chịu trách nhiệm hiện tại, đường sử dụng và mục đích |
| Tài khoản dịch vụ | Người tạo rời đội, ứng dụng đổi chủ, tài khoản dùng chung | Dịch vụ sử dụng, phụ thuộc và đội vận hành |
| Bot và danh tính CI/CD | Pipeline bị chuyển kho mã hoặc đổi nhóm phụ trách | Ai sửa pipeline, ai quản lý danh tính triển khai và credential |
| Danh tính cloud hoặc workload | Tài nguyên được tạo tự động nhưng metadata ownership không được duy trì | Quan hệ với ứng dụng, dự án, môi trường và đội chịu trách nhiệm |
| Tài khoản nhà cung cấp | Hợp đồng kết thúc hoặc người đầu mối thay đổi | Đơn vị bảo trợ nội bộ, thời hạn sử dụng và quyền còn lại |
| Tài khoản khẩn cấp | Hiếm sử dụng, trách nhiệm bị bỏ quên qua nhiều lần thay đổi nhân sự | Người quản lý quy trình, giám sát và kiểm tra định kỳ |

Tài khoản bị vô hiệu hóa vẫn có thể cần giữ trong kiểm kê theo vòng đời, nhất là khi còn gán quyền hoặc có thể được kích hoạt lại. Không tự coi “disabled” là đã hoàn tất xử lý ownership.

Đối với danh tính ngắn hạn, thường cần gắn trách nhiệm ở workload, chính sách phát hành hoặc danh tính gốc. Không nhất thiết tạo một owner độc lập cho từng token hoặc từng phiên tạm thời, nhưng phải truy vết được ai chịu trách nhiệm với cơ chế sinh ra chúng.

## 5. Nguồn dữ liệu và bằng chứng

### 5.1. Kết hợp nhiều nguồn theo vai trò của chúng

| Nguồn | Dữ liệu có ích | Giới hạn cần lưu ý |
|---|---|---|
| Directory hoặc hệ thống danh tính | Định danh ổn định, trạng thái tài khoản, nhóm, quan hệ với con người | Trạng thái kỹ thuật không luôn phản ánh đầy đủ trách nhiệm công việc |
| Nguồn vòng đời nhân sự được phép sử dụng | Tình trạng làm việc, chuyển vai trò hoặc kết thúc hợp đồng | Chỉ dùng thuộc tính cần thiết, theo thẩm quyền và chính sách truy cập |
| Danh mục ứng dụng và dịch vụ | Đội sở hữu, đầu mối, quan hệ ứng dụng–tài nguyên | Có thể chậm cập nhật hoặc chưa liệt kê tài khoản dùng chung |
| Hồ sơ cấp tài khoản và thay đổi | Người yêu cầu, mục đích, trách nhiệm đã phê duyệt | Hồ sơ cũ cần được đối chiếu với tình trạng hiện tại |
| Vault hoặc PAM | Mã tham chiếu credential, owner khai báo, quy trình sử dụng | Owner trên vault có thể là người vận hành kho bí mật |
| Cấu hình dịch vụ và triển khai | Tài khoản được dùng ở đâu, workload liên quan | Không được thu nội dung bí mật không cần thiết |
| Log xác thực và giám sát phiên | Hoạt động sử dụng, chủ thể được gắn với phiên | Người dùng thực tế không tự động là người chịu trách nhiệm |
| Xác nhận của đơn vị có thẩm quyền | Chấp nhận trách nhiệm và phạm vi hiện tại | Cần ghi người xác nhận, thời điểm và căn cứ |

Không có một nguồn duy nhất luôn đúng cho mọi loại tài khoản. Tổ chức cần quy định nguồn nào có thẩm quyền cho định danh con người, nguồn nào cho quan hệ ứng dụng và nguồn nào cho quyết định ownership.

### 5.2. Phân biệt quan sát với kết luận

Ví dụ:

~~~text
Quan sát:
- Tài khoản svc-billing tham chiếu owner employee-17.
- Nguồn vòng đời nhân sự cho biết employee-17 đã rời tổ chức.
- Chưa có bản ghi chuyển giao hợp lệ trong các nguồn bắt buộc đã đọc đủ.

Kết luận:
- Ownership hiện tại không còn hợp lệ theo chính sách.
- Cần xác định người hoặc nhóm tiếp nhận.

Không được suy ra:
- Tài khoản chắc chắn không còn được sử dụng.
- Có thể khóa hoặc đổi credential ngay mà không đánh giá ảnh hưởng.
~~~

Nếu nguồn nhân sự không truy cập được, kết luận phù hợp là chưa xác minh được tình trạng owner. Không dùng lỗi đọc để ghi rằng người đó đã nghỉ việc hoặc không tồn tại.

## 6. Mô hình dữ liệu cho một phát hiện

Nên lưu dữ liệu đủ để người khác tái hiện lý do kết luận, đồng thời tránh chứa credential hoặc thông tin cá nhân không cần thiết.

~~~yaml
finding:
  finding_id: owner-gap-021
  account:
    source_scope: database-production-a
    source_object_id: account-104
    display_name: svc-billing
    account_type: service
    enabled: true
  privilege:
    capability: administer_database
    target_reference: database-01
    evidence_reference: privilege-observation-104
  ownership:
    assessment: INACTIVE_OWNER
    declared_owner:
      owner_type: person
      owner_reference: employee-17
    ownership_scope: account_lifecycle_and_access_review
    assessment_reasons:
      - declared_owner_no_longer_in_organization
      - no_valid_transfer_record_observed
    proposed_owner_reference: team-billing-platform
    proposed_owner_status: unconfirmed
    confirmation_reference: null
  collection:
    account_source_result: complete
    ownership_sources_result: complete
    observed_at: '2026-11-26T04:00:00Z'
    run_reference: discovery-run-014
  workflow:
    state: awaiting_owner_confirmation
    handling_team_reference: team-identity-governance
    review_due_at: '2026-11-30T04:00:00Z'
~~~

Đây là cấu trúc minh họa, không phải cấu hình chạy trực tiếp. Các mốc thời gian cũng chỉ phục vụ ví dụ, không đặt ra SLA chung.

Những điểm quan trọng:

- **Owner khai báo** và **owner đề xuất** là hai trường khác nhau.
- Có một đội xử lý phát hiện không có nghĩa đội đó đã nhận ownership của tài khoản.
- Trạng thái thu thập tài khoản và trạng thái thu thập thông tin owner được lưu riêng.
- Bằng chứng về đặc quyền và bằng chứng về ownership là hai chuỗi khác nhau.
- Nếu đánh giá dựa trên dữ liệu cũ, phải thể hiện độ mới và giới hạn của kết luận.

Một phát hiện nên dùng khóa có phạm vi nguồn và mã đối tượng ổn định. Không ghép chỉ bằng username hoặc địa chỉ thư. Tài khoản tên giống nhau ở hai máy có thể thuộc hai dịch vụ khác nhau; một tên cũ có thể được tái sử dụng sau khi tài khoản bị xóa.

## 7. Quy trình phát hiện từng bước

### 7.1. Bước 1 — Xác định phạm vi và tiêu chí ownership

Chọn các nguồn và loại tài khoản được phép kiểm kê. Xác định trước:

- Owner có thể là cá nhân, nhóm hay cả hai.
- Quan hệ ownership qua ứng dụng có được chấp nhận không.
- Nguồn nào bắt buộc phải đọc để kết luận.
- Điều kiện nào khiến owner không còn hợp lệ.
- Bằng chứng được coi là còn mới trong từng phạm vi.
- Ai có thẩm quyền xác nhận hoặc phân xử tranh chấp.

Nếu chưa có định nghĩa, đội discovery rất dễ tạo ra hai sai lệch: tài khoản có owner gián tiếp hợp lệ bị báo thiếu, còn tài khoản có một địa chỉ thư cũ lại được báo đạt.

### 7.2. Bước 2 — Kiểm kê tài khoản và quyền

Thu thập các tài khoản trong phạm vi cùng trạng thái, loại tài khoản, tài nguyên và khả năng đặc quyền. Lưu cả kết quả thu thập: hoàn chỉnh, một phần hay thất bại.

Ưu tiên truy vấn metadata bằng danh tính đọc có phạm vi phù hợp. Không lấy mật khẩu hoặc thử đăng nhập chỉ để biết tài khoản có owner hay không.

### 7.3. Bước 3 — Thu thập quan hệ trách nhiệm

Đọc thông tin owner trực tiếp, mapping ứng dụng, hồ sơ cấp tài khoản và nguồn xác minh cá nhân hoặc nhóm. Giữ lại mã tham chiếu và thời điểm quan sát.

Phải phân biệt:

- Trường tồn tại và có giá trị.
- Trường được đọc thành công nhưng để trống.
- Trường không được phép đọc.
- Nguồn hoặc đối tượng không truy cập được.

Chỉ trường hợp thứ hai mới là bằng chứng trường đó chưa ghi owner. Những trường hợp lỗi hoặc thiếu quyền là khoảng trống dữ liệu.

### 7.4. Bước 4 — Đánh giá tính hợp lệ

Mã giả:

~~~text
for account in observed_accounts:
    evidence = collect_required_ownership_evidence(account)

    if not evidence.sufficient_for_policy:
        record(DATA_GAP, missing_sources, preliminary_candidates)
        continue

    claims = resolve_direct_and_permitted_indirect_ownership(evidence)

    if claims.is_empty:
        record(MISSING_OWNER_RECORD, evidence)
        continue

    issues = []

    for claim in claims:
        if not claim.resolves_to_expected_identity:
            issues.add(INVALID_OWNER_REFERENCE)
        elif not claim.owner_is_currently_eligible:
            issues.add(INACTIVE_OWNER)
        elif not claim.has_valid_responsibility_basis:
            issues.add(UNRESOLVED_OWNER)

    if claims.conflict_in_the_same_responsibility_scope:
        issues.add(CONFLICTING_OWNER)

    if issues.is_empty and claims.cover_required_responsibility:
        record(CONFIRMED_OWNER, claims, evidence)
    else:
        record(issues, claims, evidence)
~~~

Các hàm trên đại diện cho chính sách tổ chức, không phải thuật toán có thể dùng nguyên trạng cho mọi nền tảng. Nếu nhiều nguồn ghi hai vai trò bổ sung cho nhau, đó không nhất thiết là xung đột. Chỉ đánh dấu mâu thuẫn khi các bên đưa ra tuyên bố không tương thích trong cùng phạm vi trách nhiệm.

### 7.5. Bước 5 — Xác minh ứng viên với đơn vị có thẩm quyền

Dùng các dấu vết để đề xuất nơi tiếp nhận, nhưng giữ trạng thái chưa xác nhận cho tới khi có căn cứ hợp lệ. Nội dung xác minh cần đủ cụ thể: tài khoản nào, dùng ở đâu, quyền gì và trách nhiệm nào đang được giao.

Không tự điền owner bằng đội gần giống tên tài khoản hoặc người có nhiều đăng nhập nhất.

### 7.6. Bước 6 — Cập nhật và đối soát lại

Sau khi ownership được xác nhận, cập nhật nguồn quản trị có thẩm quyền, liên kết các hệ thống cần thiết và đọc lại để kiểm chứng. Giữ lịch sử thay đổi; không xóa bằng chứng cũ khiến quá trình chuyển giao không thể truy vết.

Nếu kết luận tài khoản không còn cần thiết, chuyển sang quy trình ngừng sử dụng có đánh giá phụ thuộc và xác minh kết quả tại đích.

## 8. Dùng dấu vết để tìm owner mà không biến suy đoán thành sự thật

Một số dấu vết giúp thu hẹp phạm vi điều tra:

| Dấu vết | Có thể gợi ý điều gì? | Cần xác minh thêm |
|---|---|---|
| Tên tài khoản giống tên dịch vụ | Có thể liên quan ứng dụng đó | Có đúng ứng dụng, môi trường và phiên bản hiện tại không? |
| Tài khoản xuất hiện trong cấu hình workload | Có quan hệ sử dụng kỹ thuật | Workload có dùng chung tài khoản với hệ thống khác không? |
| Nhãn team hoặc application | Nhóm hoặc ứng dụng được khai báo | Nhãn còn mới và có căn cứ giao trách nhiệm không? |
| Hồ sơ cấp quyền ban đầu | Mục đích tại thời điểm tạo | Mục đích và người chịu trách nhiệm đã thay đổi chưa? |
| Hoạt động từ một nhóm máy | Phạm vi sử dụng có thể có | Máy nguồn có phải proxy, agent hoặc hạ tầng dùng chung không? |
| Người thường mở phiên PAM | Một người sử dụng thường xuyên | Người đó có thẩm quyền và đã nhận trách nhiệm vòng đời không? |

Có thể dùng mức tin cậy để xếp thứ tự xác minh ứng viên. Mức tin cậy cao vẫn không thay thế quyết định giao trách nhiệm khi chính sách yêu cầu xác nhận.

Đặc biệt, không coi địa chỉ thư khớp gần đúng hoặc tên giống nhau là bằng chứng định danh. Cần dùng mã cá nhân hoặc mã nhóm ổn định từ nguồn phù hợp, đồng thời xét khả năng đổi tên và tái sử dụng định danh.

## 9. Ưu tiên xử lý dựa trên mức tác động

Không có owner là một vấn đề quản trị quyền; nó không tự chứng minh tài khoản đã bị xâm nhập. Tuy nhiên, mức tác động có thể cao khi tài khoản đó giữ quyền mạnh và không ai tiếp nhận xử lý.

Các yếu tố nên dùng để ưu tiên:

- Khả năng đổi quyền, cấp tài khoản, đọc bí mật hoặc tắt giám sát.
- Quyền trên hệ thống danh tính trung tâm, môi trường sản xuất hoặc dữ liệu nhạy cảm.
- Đường truy cập trực tiếp và khả năng sử dụng credential ngoài cơ chế kiểm soát.
- Credential dài hạn, tài khoản dùng chung hoặc quyền thường trực.
- Dấu hiệu sử dụng bất thường, nhất là sau khi người owner cũ rời tổ chức.
- Mức rõ của phụ thuộc và khả năng khôi phục khi thay đổi.
- Khoảng thời gian kể từ lần xác nhận ownership gần nhất.

Ví dụ thứ tự xử lý có thể là:

| Phát hiện | Lý do ưu tiên | Hành động đầu tiên phù hợp |
|---|---|---|
| Tài khoản đổi được quyền danh tính, owner đã nghỉ, đang có hoạt động bất thường | Mức tác động cao và có dấu hiệu cần điều tra | Kích hoạt phối hợp ứng phó sự cố và kiểm soát truy cập theo thẩm quyền |
| Tài khoản dịch vụ quản trị dữ liệu sản xuất, chưa có owner xác nhận | Quyền mạnh và rủi ro gián đoạn nếu xử lý vội | Xác định đội tiếp nhận, phụ thuộc và biện pháp tạm thời |
| Tài khoản ít quyền trên lab, owner chưa rõ | Tác động thấp hơn trong phạm vi đã biết | Xác minh theo quy trình và thời hạn phù hợp |

Không chọn biện pháp khóa hàng loạt chỉ vì một cột owner rỗng. Ngược lại, cũng không để rủi ro tồn tại vô thời hạn vì chưa tìm được người chịu trách nhiệm. Cần có đơn vị xử lý tạm thời, thời hạn và cơ chế nâng cấp quyết định.

## 10. Từ phát hiện đến ownership được xác nhận

Một luồng xử lý rõ ràng:

~~~mermaid
flowchart TD
    A[Phát hiện khoảng trống ownership] --> B{Đủ bằng chứng để kết luận?}
    B -->|Chưa đủ| C[Bổ sung dữ liệu và sửa nguồn thu thập]
    C --> B
    B -->|Đủ| D[Xác định ứng viên và đơn vị tiếp nhận]
    D --> E{Xác nhận tài khoản còn cần?}
    E -->|Có| F[Giao trách nhiệm với phạm vi rõ ràng]
    E -->|Không| G[Đánh giá phụ thuộc và ngừng sử dụng]
    E -->|Chưa rõ| H[Quản lý tạm thời và nâng cấp quyết định]
    H --> D
    F --> I[Cập nhật nguồn và xác minh lại]
    G --> I
    I --> J[Lưu bằng chứng và theo dõi thay đổi]
~~~

### 10.1. Một lần nhận ownership nên xác nhận gì?

- Đúng tài khoản, tài nguyên và môi trường.
- Mục đích sử dụng hiện tại.
- Ứng dụng, dịch vụ hoặc nhóm người được phép dùng.
- Người hoặc nhóm có thẩm quyền xét duyệt quyền.
- Đầu mối đánh giá thay đổi credential và xử lý sự cố.
- Trách nhiệm duy trì thông tin và chuyển giao khi tổ chức thay đổi.

Nếu tài khoản phục vụ nhiều ứng dụng, cần xác định ranh giới trách nhiệm hoặc kế hoạch tách tài khoản. Điền tên một đội nhưng không xác định đội đó chịu trách nhiệm cho phần nào sẽ giữ nguyên khoảng trống.

### 10.2. Owner tạm thời và ngoại lệ

Một đội có thể được giao quản lý tạm thời theo quyết định có thẩm quyền. Cần ghi rõ phạm vi được giao, hạn rà soát, hạn chế truy cập và điều kiện kết thúc.

Đội xử lý ticket không tự động trở thành owner. Chỉ khi trách nhiệm tạm thời đã được giao rõ thì mới được báo theo trạng thái đó. Báo cáo cũng phải tách owner tạm thời khỏi owner dài hạn đã xác nhận nếu chính sách yêu cầu.

Ngoại lệ cần có người chấp nhận rủi ro, phạm vi, thời hạn và biện pháp bù. Không đóng phát hiện chỉ vì “chưa tìm được owner”; đó vẫn là công việc chưa được giải quyết hoặc rủi ro đang được chấp nhận có thời hạn.

## 11. Xử lý kỹ thuật sau khi đã xác định trách nhiệm

Ownership hợp lệ là cơ sở để quản lý quyền, không thay thế kiểm soát kỹ thuật.

### 11.1. Với tài khoản quản trị con người

Kiểm tra tài khoản còn gắn với người đúng vai trò hay không, quyền nào còn cần và có thể chuyển sang JIT/JEA không. Nếu người đã rời tổ chức, xử lý tài khoản và quyền theo quy trình vòng đời; đừng chỉ đổi trường owner sang người quản lý rồi giữ toàn bộ quyền cũ.

Đối với tài khoản dùng chung, cần có cách liên kết phiên với người sử dụng thực tế. Nhóm chịu trách nhiệm đã được xác nhận không giải quyết được việc không biết ai thực hiện thao tác.

### 11.2. Với tài khoản dịch vụ

Trước khi đổi credential hoặc giảm quyền, xác định:

1. Những dịch vụ, tác vụ định kỳ, agent và pipeline đang dùng.
2. Nơi tham chiếu credential và cơ chế cập nhật.
3. Quyền tối thiểu cần cho từng phụ thuộc.
4. Khả năng kiểm tra, quay lui và xác minh sau thay đổi.
5. Phương án thay bằng danh tính workload hoặc credential tạm thời nếu phù hợp.

Một tài khoản dịch vụ không owner có thể đang duy trì chức năng quan trọng. Quá trình xác minh phụ thuộc phải được thực hiện có giới hạn và tránh thu thập giá trị bí mật vào báo cáo.

### 11.3. Với tài khoản khẩn cấp

Tài khoản break-glass cần đơn vị chịu trách nhiệm với toàn bộ quy trình: điều kiện sử dụng, cách lấy quyền, ghi nhận phiên hoặc hoạt động, kiểm tra sau sử dụng và xử lý credential.

Việc không có đăng nhập gần đây không làm mất nhu cầu khẩn cấp. Cần kiểm tra mục đích và khả năng vận hành thay vì xóa tài khoản chỉ vì ít hoạt động.

### 11.4. Với tài khoản không còn cần thiết

Ngừng sử dụng nên có kế hoạch theo mức rủi ro: xác nhận phụ thuộc, giới hạn hoặc vô hiệu hóa theo quyết định được duyệt, thu hồi quyền và credential liên quan, theo dõi ảnh hưởng rồi hoàn tất vòng đời.

Thứ tự cụ thể phụ thuộc hệ thống. Trong tình huống sự cố, biện pháp cô lập khẩn cấp có thể cần được thực hiện sớm theo thẩm quyền. Trong thay đổi thông thường, không tự giả định có thể vô hiệu hóa mà không ảnh hưởng dịch vụ.

## 12. Duy trì ownership khi nhân sự và hệ thống thay đổi

Discovery một lần sẽ nhanh chóng lỗi thời nếu chỉ xác nhận owner mà không gắn với vòng đời.

Các sự kiện nên kích hoạt đối soát:

| Sự kiện | Điều cần kiểm tra |
|---|---|
| Nhân viên nghỉ hoặc đổi vai trò | Các tài khoản quản trị và trách nhiệm dịch vụ liên quan đã được xử lý chưa? |
| Nhóm giải thể hoặc đổi chức năng | Quan hệ ownership còn trỏ tới đơn vị có khả năng tiếp nhận không? |
| Ứng dụng chuyển đội vận hành | Tài khoản, vault, pipeline và hồ sơ ownership đã được chuyển đồng bộ chưa? |
| Kết thúc hợp đồng nhà cung cấp | Đầu mối bảo trợ và quyền truy cập còn hợp lệ không? |
| Tạo tài khoản hoặc workload mới | Có ownership ngay từ cấp phát và liên kết được với ứng dụng không? |
| Thay đổi quyền mạnh | Owner có còn phù hợp với phạm vi trách nhiệm mới không? |
| Tài khoản hoạt động trở lại | Ownership cũ có còn hợp lệ trước khi khôi phục sử dụng không? |

Nên kết hợp thông tin theo sự kiện với đối soát định kỳ. Sự kiện có thể bị bỏ lỡ; dữ liệu định kỳ cũng có thể bỏ qua thay đổi ngắn hạn.

Khi một nguồn thu thập bị lỗi, không xóa quan hệ ownership chỉ vì lần đó không thấy lại. Giữ lịch sử và đánh dấu chưa xác minh được trạng thái hiện tại. Nếu các nguồn cập nhật không đồng thời, ghi thời điểm quan sát và tránh coi sự chậm đồng bộ ngắn hạn như bằng chứng chắc chắn có owner mồ côi.

## 13. Chỉ số và bằng chứng cho kiểm toán

### 13.1. Đo đúng mẫu số

Các chỉ số hữu ích gồm:

- Số tài khoản trong phạm vi đã quan sát.
- Số tài khoản đủ dữ liệu để đánh giá ownership.
- Số tài khoản có owner được xác nhận, tạm thời hoặc chưa xác nhận.
- Số phát hiện theo từng nguyên nhân: thiếu bản ghi, owner không còn hợp lệ, tham chiếu sai, mâu thuẫn.
- Số tài khoản đặc quyền cao còn khoảng trống ownership.
- Thời gian từ phát hiện tới xác nhận hoặc quyết định xử lý.
- Số phát hiện tái diễn sau chuyển giao hoặc thay đổi tổ chức.
- Số bản ghi quá hạn rà soát hoặc dùng bằng chứng quá cũ.

Ví dụ, quan sát được 48 tài khoản nhưng chỉ 40 tài khoản đủ dữ liệu để đánh giá. Trong số 40 đó, 28 có owner hợp lệ và 12 có vấn đề. Tỷ lệ 28 / 40 = 70% chỉ áp dụng cho tập **đã đánh giá đủ**. Cần báo riêng 8 tài khoản thiếu dữ liệu; không coi chúng là đạt hoặc đã được xử lý.

Các tài khoản chưa được quan sát vì nguồn lỗi hoặc ngoài danh mục vẫn là giới hạn độ bao phủ. Báo cáo phải nêu phạm vi và thời điểm, thay vì suy rộng tỷ lệ ra toàn bộ hạ tầng.

### 13.2. Bằng chứng cần giữ

| Nhóm bằng chứng | Nội dung |
|---|---|
| Định danh và phạm vi | Mã tài khoản, nguồn, tài nguyên, loại tài khoản và mức đặc quyền liên quan |
| Quan sát ban đầu | Owner được khai báo, nguồn tham chiếu, kết quả thu thập và thời điểm |
| Căn cứ kết luận | Vì sao owner thiếu hoặc không hợp lệ; dữ liệu nào còn thiếu |
| Xác minh | Ứng viên được xem xét, người có thẩm quyền xác nhận, phạm vi được nhận |
| Quyết định xử lý | Giao owner, giảm quyền, quản lý tạm thời, ngoại lệ hoặc ngừng sử dụng |
| Kiểm chứng sau xử lý | Kết quả đọc lại nguồn, trạng thái tại đích, các tồn tại chưa hoàn tất |

Không lưu mật khẩu, token hoặc khóa vào bằng chứng. Chỉ thu thuộc tính nhân sự cần cho việc xác minh, giới hạn người xem và áp dụng thời gian lưu thích hợp cho dữ liệu ownership, log và hồ sơ phê duyệt.

## 14. Bài thực hành: phân loại bảy tài khoản

Dùng dữ liệu giả lập dưới đây, không cần truy cập hệ thống thật. Giả định các tài khoản đều có quyền cần kiểm soát trong phạm vi PAM.

| Tài khoản | Quan sát | Trạng thái thu thập |
|---|---|---|
| svc-payroll | Owner là employee-12; người này đã rời tổ chức; không có chuyển giao hợp lệ | Đủ nguồn bắt buộc |
| ops-temp | Trường owner trống; không có mapping ứng dụng hoặc hồ sơ ownership khác | Đủ nguồn bắt buộc |
| svc-report | Không có owner trực tiếp; quan hệ tới ứng dụng A và nhóm T đã được xác nhận theo chính sách | Đủ nguồn bắt buộc |
| admin-shared | Nhóm T đã nhận trách nhiệm; log chưa liên kết được từng phiên với người sử dụng | Đủ nguồn ownership |
| svc-ci | Collector bị từ chối khi đọc nguồn ownership; chỉ thấy tên gợi ý liên quan CI | Thiếu dữ liệu ownership |
| svc-legacy | Owner tham chiếu group-88; nguồn có thẩm quyền xác nhận mã nhóm đó đã bị xóa | Đủ nguồn bắt buộc |
| svc-conflict | Hai nguồn có thẩm quyền khai báo hai đội khác nhau cho cùng trách nhiệm; chưa có quyết định phân xử | Đủ để xác định mâu thuẫn |

### 14.1. Yêu cầu

1. Phân loại ownership và ghi lý do cho từng tài khoản.
2. Tách vấn đề ownership khỏi những vấn đề kiểm soát khác.
3. Chỉ ra nơi cần bổ sung bằng chứng, nơi cần chuyển giao trách nhiệm.
4. Chọn hành động tiếp theo mà chưa tự động khóa hoặc đổi credential.
5. Xác định bằng chứng cần có để đóng từng phát hiện.

### 14.2. Gợi ý kết quả

| Tài khoản | Kết luận phù hợp | Bước tiếp theo |
|---|---|---|
| svc-payroll | INACTIVE_OWNER | Tìm đơn vị tiếp nhận, xác minh phụ thuộc và thực hiện chuyển giao |
| ops-temp | MISSING_OWNER_RECORD | Xác định mục đích, ứng viên và người có thẩm quyền giao trách nhiệm |
| svc-report | CONFIRMED_OWNER qua quan hệ ứng dụng hợp lệ | Giữ bằng chứng chuỗi liên kết và lịch rà soát |
| admin-shared | Có owner; tồn tại vấn đề truy vết người dùng | Giữ ownership hợp lệ, xử lý riêng việc gắn phiên với người sử dụng |
| svc-ci | DATA_GAP | Sửa quyền đọc hoặc nguồn dữ liệu; không gán owner theo tên |
| svc-legacy | INVALID_OWNER_REFERENCE | Xác định nhóm kế thừa hoặc owner mới, rồi xác nhận |
| svc-conflict | CONFLICTING_OWNER | Phân xử trách nhiệm và cập nhật nguồn theo quyết định |

Tài khoản admin-shared cho thấy ownership và khả năng quy trách nhiệm cho thao tác là hai yêu cầu khác nhau. Có owner không có nghĩa mọi phiên đã được kiểm soát; thiếu dữ liệu người sử dụng cũng không tự làm owner biến mất.

### 14.3. Điều kiện đóng phát hiện

Với svc-payroll, chỉ đóng khi quan hệ trách nhiệm mới đã được xác nhận và cập nhật, hoặc tài khoản đã hoàn tất ngừng sử dụng theo quyết định có thẩm quyền. Chuyển ticket sang đội khác chưa đáp ứng điều kiện đó.

Với svc-ci, việc sửa kết nối chỉ giải quyết khoảng trống thu thập. Phải chạy lại đánh giá ownership trước khi kết luận có owner hợp lệ.

Với svc-conflict, hai đội cùng xác nhận rằng “đội kia phụ trách” chưa giải quyết mâu thuẫn. Cần một quyết định xác định bên chịu trách nhiệm hoặc tách rõ các phạm vi bổ sung cho nhau.

## 15. Các lỗi thường gặp và tiêu chí một phát hiện dùng được

| Lỗi | Hậu quả | Cách cải thiện |
|---|---|---|
| Trường owner có chữ là coi đạt | Tham chiếu cũ hoặc sai vẫn lọt qua | Kiểm tra định danh, tình trạng và căn cứ giao trách nhiệm |
| Trường owner trống là coi mồ côi | Báo sai tài khoản có ownership gián tiếp hợp lệ | Xét các mô hình được chính sách chấp nhận |
| Lỗi API bị coi là owner không tồn tại | Tạo kết luận thiếu owner từ dữ liệu không đầy đủ | Tách DATA_GAP và trạng thái thu thập |
| Gán người tạo hoặc người dùng gần nhất làm owner | Giao trách nhiệm sai người | Dùng dấu vết để đề xuất, yêu cầu căn cứ xác nhận |
| Tự đổi mật khẩu tài khoản dịch vụ | Gián đoạn phụ thuộc chưa được kiểm kê | Xác định ứng dụng, phụ thuộc và phương án thay đổi |
| Có trong vault là coi đã giải quyết ownership | Bảo vệ credential nhưng không có người xét duyệt quyền | Đánh giá riêng trách nhiệm và kiểm soát credential |
| Đổi owner nhưng giữ mọi quyền cũ | Trách nhiệm mới chưa gắn với least privilege | Rà soát nhu cầu quyền, JIT/JEA và cơ chế truy cập |
| Đóng phát hiện khi đã chuyển ticket | Không chứng minh trạng thái thực tế đã đổi | Xác nhận quyết định và đọc lại nguồn có thẩm quyền |

Một phát hiện có thể chuyển cho đội xử lý khi trả lời được: đây là tài khoản nào, quyền và tài nguyên liên quan là gì, ownership đang thiếu ở điểm nào, bằng chứng nào hỗ trợ kết luận, ai xử lý tiếp và điều kiện nào chứng minh đã hoàn tất.

Giá trị của discovery nằm ở việc biến một tài khoản “không biết ai phụ trách” thành một đối tượng có trách nhiệm rõ ràng hoặc một quyết định vòng đời được kiểm chứng. Điều đó tạo nền tảng để giảm quyền, quản lý credential, giám sát phiên và ứng phó sự cố mà không dựa vào suy đoán.
