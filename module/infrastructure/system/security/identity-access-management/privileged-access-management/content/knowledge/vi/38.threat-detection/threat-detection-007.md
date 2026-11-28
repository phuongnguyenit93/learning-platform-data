# Abuse of service account — Phát hiện lạm dụng tài khoản dịch vụ trong PAM

## 1. Mục tiêu bài học

Tài khoản dịch vụ được tạo để ứng dụng, tác vụ tự động hoặc workload truy cập tài nguyên mà không cần con người đăng nhập ở mỗi lần thực thi. Khi tài khoản này có quyền quản trị, giữ credential lâu dài hoặc được dùng trên nhiều hệ thống, một hành vi lạm dụng có thể ảnh hưởng đồng thời đến dữ liệu, hạ tầng và khả năng khôi phục.

Trong chương Threat detection của Privileged Access Management (PAM), mục tiêu của bài là giúp người học:

- Phân biệt hoạt động dịch vụ hợp lệ với hành vi dùng sai mục đích, lộ credential hoặc sử dụng quyền vượt quá phạm vi.
- Xây dựng ngữ cảnh phát hiện dựa trên chủ sở hữu, workload, đường đi truy cập, phiên và tài nguyên.
- Đối chiếu tín hiệu từ PAM, hệ thống xác thực, máy chủ, ứng dụng và nền tảng dữ liệu.
- Thiết kế quy tắc phát hiện có điều kiện, xử lý ngoại lệ và kiểm tra chất lượng dữ liệu.
- Điều tra, cô lập và khôi phục quyền truy cập mà vẫn tính đến phụ thuộc vận hành của dịch vụ.

PAM hỗ trợ kiểm kê quyền, vault, luân chuyển credential, JIT/JEA và ghi bằng chứng. Tuy nhiên, chỉ nhìn nhật ký vault hoặc số lần đăng nhập sẽ không đủ để kết luận tài khoản dịch vụ đang bị lạm dụng.

## 2. Hiểu đúng đối tượng cần giám sát

### 2.1. Tài khoản dịch vụ là gì?

Trong bài này, “tài khoản dịch vụ” chỉ danh tính được cấp cho phần mềm, tác vụ nền hoặc chuỗi tự động hóa. Tùy môi trường, đó có thể là tài khoản hệ điều hành, tài khoản cơ sở dữ liệu, danh tính ứng dụng, danh tính workload hoặc principal dùng để gọi API.

Không phải mọi tài khoản dịch vụ đều có quyền đặc biệt. Phạm vi PAM ưu tiên những tài khoản có thể quản trị tài nguyên, đọc dữ liệu nhạy cảm, cấp quyền tiếp, truy xuất secret hoặc điều khiển thành phần quan trọng. Các tài khoản ít quyền vẫn cần giám sát khi chúng có thể trở thành điểm khởi đầu của một chuỗi truy cập.

Ví dụ:

| Danh tính | Nhiệm vụ được phê duyệt | Rủi ro cần chú ý |
|---|---|---|
| `svc-billing-export` | Đọc dữ liệu tổng hợp và xuất báo cáo định kỳ | Đọc bảng chi tiết ngoài phạm vi, xuất dữ liệu đến đích lạ |
| `svc-deploy-prod` | Triển khai bản phát hành từ runner đã quản lý | Chạy từ máy cá nhân, đổi quyền hoặc secret ngoài kế hoạch |
| `svc-backup-db` | Sao lưu cơ sở dữ liệu vào kho đã chỉ định | Dùng quyền sao lưu để lấy dữ liệu ngoài tác vụ hoặc sửa chính sách lưu giữ |
| `workload-reconcile` | Gọi API nội bộ bằng danh tính workload | Token được dùng từ workload khác hoặc truy cập API quản trị |

Tên có tiền tố `svc-` chỉ là quy ước đặt tên. Không dùng tên làm nguồn duy nhất để phân loại danh tính. Cần danh mục có chủ sở hữu và dữ liệu đối chiếu với nơi tài khoản thực sự được sử dụng.

### 2.2. Phân biệt danh tính, credential, phiên và nơi thực thi

Bốn khái niệm này giúp tránh kết luận nhầm:

- **Danh tính:** đối tượng được hệ thống cấp quyền và ghi nhận là người thực hiện hành động.
- **Credential:** phương tiện chứng minh danh tính, chẳng hạn mật khẩu, khóa, chứng thư hoặc token.
- **Phiên:** ngữ cảnh truy cập đã được thiết lập; thời hạn phiên có thể khác thời hạn credential.
- **Nơi thực thi:** máy chủ, container, runner hoặc workload thực sự sử dụng quyền.

Credential có thể được lấy từ vault đúng quy trình nhưng sau đó được dùng ngoài nơi đã phê duyệt. Ngược lại, một workload dùng danh tính liên kết hoặc credential ngắn hạn có thể không tạo sự kiện checkout trong vault truyền thống.

Vì vậy, không có sự kiện vault không mặc nhiên đồng nghĩa với truy cập trái phép. Có sự kiện vault cũng không chứng minh mọi hành động sau đó là hợp lệ.

### 2.3. Những dạng lạm dụng thường gặp

Lạm dụng bao gồm cả việc bên ngoài chiếm credential và việc người có quyền sử dụng tài khoản sai mục đích:

1. Con người dùng tài khoản dịch vụ để đăng nhập tương tác và che khuất trách nhiệm cá nhân.
2. Credential bị dùng từ máy hoặc workload chưa được cấp phép.
3. Ứng dụng bị xâm nhập rồi sử dụng chính danh tính hợp lệ để truy cập tài nguyên khác.
4. Một pipeline bị sửa để chạy hành động quản trị vượt mục tiêu triển khai.
5. Tài khoản dùng chung bị tận dụng để vượt kiểm soát phê duyệt, JIT hoặc JEA.
6. Credential của dịch vụ đã ngừng hoạt động vẫn tiếp tục được sử dụng.
7. Tài khoản hợp lệ tạo thêm quyền, credential hoặc đường truy cập mà không có thay đổi được phê duyệt.

Điểm cần phát hiện là sự lệch khỏi mục đích đã xác định, không chỉ sự thất bại khi đăng nhập.

## 3. Xây dựng hồ sơ hành vi được phép

### 3.1. Mỗi tài khoản cần một hợp đồng sử dụng

Trước khi đặt ngưỡng cảnh báo, cần trả lời: tài khoản này được dùng bởi ai, từ đâu, để làm gì, trên tài nguyên nào và trong điều kiện nào?

Một hồ sơ tối thiểu có thể gồm:

| Nhóm thông tin | Nội dung cần quản lý | Giá trị cho phát hiện |
|---|---|---|
| Trách nhiệm | Chủ sở hữu ứng dụng, đội vận hành, người thay thế | Có đầu mối xác nhận mục đích sử dụng |
| Danh tính ổn định | ID principal, miền hoặc tenant, tên hiển thị | Tránh gộp nhầm các tài khoản cùng tên |
| Nguồn được phép | ID workload, nhóm runner, máy chủ, mạng và vùng | Phát hiện sử dụng từ nguồn lạ |
| Đường truy cập | Broker PAM, vault, danh tính workload, kết nối được phê duyệt | Nhận diện đường đi bị bỏ qua |
| Quyền | Role, nhóm, tài nguyên và hành động được cấp | So sánh quyền thực tế với nhu cầu |
| Nhịp hoạt động | Lịch chạy, múi giờ, retry, tác vụ thủ công đã cho phép | Giảm nhầm lẫn do lịch vận hành |
| Phụ thuộc | Ứng dụng, connection pool, job, secret và bên sử dụng | Đánh giá tác động khi cô lập hoặc rotate |
| Vòng đời | Ngày cấp, lần rà soát, trạng thái đang dùng hoặc đã nghỉ | Nhận diện tài khoản mồ côi, đã nghỉ nhưng còn hoạt động |
| Ngoại lệ | Phạm vi, người duyệt, lý do, thời hạn | Không biến ngoại lệ tạm thành miễn giám sát vĩnh viễn |

Danh mục “được phép” phải được quản lý thay đổi. Nếu chỉ lấy mọi hành vi từng quan sát làm baseline, một hành vi xấu tồn tại từ trước có thể được học thành hoạt động bình thường.

### 3.2. Ví dụ hồ sơ rút gọn

Đây là cấu hình minh họa, không phải schema bắt buộc của một sản phẩm:

```yaml
principal_id: principal-billing-export-01
display_name: svc-billing-export
identity_type: service_account
owner_team: billing-platform
purpose: export_daily_aggregated_report
allowed_workloads:
  - billing-report-job
allowed_source_assets:
  - runner-report-01
allowed_targets:
  - billing-reporting-db
allowed_actions:
  - read_approved_reporting_views
  - write_approved_report_bucket
interactive_login_allowed: false
credential_path: managed_vault_injection
timezone: Asia/Ho_Chi_Minh
schedule:
  start: "01:00"
  end: "02:00"
exceptions_require_expiry: true
```

Hồ sơ này không có nghĩa mọi lần chạy ngoài 01:00–02:00 đều là tấn công. Một lần chạy bù có thể hợp lệ, nhưng cần gắn với yêu cầu thay đổi, người phê duyệt và phạm vi cụ thể.

Nếu hạ tầng tự mở rộng, danh sách máy chủ tĩnh sẽ nhanh lỗi thời. Khi đó nên kết hợp ID workload, thuộc tính triển khai và nguồn inventory đáng tin cậy. IP nguồn chỉ là một thành phần ngữ cảnh vì nhiều máy có thể dùng chung NAT, proxy hoặc broker.

## 4. Thu thập và liên kết bằng chứng

### 4.1. Các nguồn nhật ký bổ sung cho nhau

| Nguồn | Dữ liệu hữu ích | Giới hạn cần hiểu |
|---|---|---|
| PAM và vault | Ai hoặc workload nào yêu cầu secret, phê duyệt, phiên broker, rotate | Không phải mọi mô hình credential đều có checkout |
| Hệ thống xác thực | Principal, kết quả xác thực, nguồn, loại đăng nhập hoặc token | Xác thực thành công chưa cho biết hành động nghiệp vụ |
| Máy chủ và workload | Tiến trình, cây tiến trình, host/container, phiên tương tác | Cần cấu hình thu thập phù hợp; không luôn có command đầy đủ |
| Ứng dụng và cơ sở dữ liệu | API, truy vấn, đối tượng dữ liệu, hành động và kết quả | Tài khoản ứng dụng dùng chung có thể làm mờ người khởi tạo |
| Control plane | Gán role, đổi policy, tạo credential, sửa cấu hình | Cần phân biệt người yêu cầu và principal thực thi |
| Pipeline và lịch chạy | Run ID, commit hoặc bản phát hành, runner, người kích hoạt | Run thành công không chứng minh mọi bước trong run đã an toàn |
| Inventory và thay đổi | Owner, môi trường, tài nguyên, maintenance, ngoại lệ | Dữ liệu cũ có thể tạo cảnh báo sai hoặc bỏ sót |

Một chuỗi điều tra có thể đi theo luồng:

```text
Yêu cầu thay đổi hoặc lịch job
            ↓
Run / workload được phép
            ↓
Lấy credential hoặc nhận danh tính
            ↓
Xác thực và thiết lập phiên
            ↓
Hành động trên tài nguyên
            ↓
Kết quả, dữ liệu bị ảnh hưởng và bằng chứng
```

Luồng này giúp đặt câu hỏi ở từng mắt xích. Không phải môi trường nào cũng có đủ sự kiện để nối chuỗi hoàn chỉnh; khi thiếu, phải ghi rõ phần chưa quan sát được.

### 4.2. Chuẩn hóa các trường cần thiết

Một bản ghi phục vụ tương quan nên có, trong khả năng nguồn cung cấp:

- `event_time` và `ingest_time` để phân biệt thời điểm xảy ra với lúc hệ thống nhận log.
- `principal_id`, `principal_name`, `principal_type` và phạm vi định danh như tenant hoặc domain.
- `source_asset_id`, địa chỉ nguồn, ID workload và ID runner nếu có.
- `target_resource_id`, môi trường, độ nhạy và loại tài nguyên.
- `action`, `outcome`, loại đăng nhập, cơ chế xác thực và quyền được sử dụng.
- `session_id`, `request_id`, `run_id` hoặc trace ID để nối các sự kiện.
- Tham chiếu phiên PAM, sự kiện cấp credential, yêu cầu thay đổi và chủ sở hữu.
- Trạng thái chất lượng dữ liệu, ví dụ thiếu ánh xạ tài khoản hoặc nguồn chưa có log.

Không đưa mật khẩu, khóa riêng, token thô hoặc nội dung secret vào log và cảnh báo. Nếu cần tương quan credential, dùng ID hoặc phiên bản do hệ thống phát hành cung cấp. Không tự ghi secret rồi kỳ vọng che giấu ở bước sau.

### 4.3. Liên kết danh tính thực thi với người khởi tạo

Một job chạy dưới tài khoản dịch vụ có thể do con người kích hoạt. Nếu chỉ giữ trường tài khoản thực thi, đội điều tra sẽ không biết ai đã yêu cầu hành động.

Nên lưu chuỗi liên hệ:

```text
human_initiator → approved_request → pipeline_run
                → workload_identity → target_action
```

Không suy người khởi tạo chỉ từ người checkout secret gần nhất. Credential có thể được cache, chia sẻ ngoài thiết kế hoặc dùng cho nhiều phiên. Khi thiếu khóa nối đáng tin cậy, ghi nhận đây là mối liên hệ giả định cần xác minh.

## 5. Các nhóm tín hiệu phát hiện

### 5.1. Đăng nhập tương tác trái với mục đích tài khoản

Tài khoản chỉ dành cho job nền xuất hiện trong phiên terminal, desktop hoặc shell tương tác là tín hiệu cần kiểm tra.

Ngữ cảnh làm tín hiệu mạnh hơn:

- Nguồn là máy trạm cá nhân hoặc thiết bị chưa quản lý.
- Không có yêu cầu hỗ trợ, phê duyệt PAM hoặc ngoại lệ còn hiệu lực.
- Phiên thực hiện thay đổi quyền, truy cập secret hoặc điều khiển dịch vụ.
- Tài khoản chưa từng được phép dùng theo kiểu tương tác.

Tên tiến trình có chữ “shell” chưa đủ để khẳng định có con người đăng nhập. Nhiều job hợp lệ chạy script qua shell. Cần kết hợp loại đăng nhập, cây tiến trình, đặc điểm phiên, nguồn và lịch job.

### 5.2. Nguồn thực thi hoặc đường truy cập không được phép

Ví dụ: `svc-deploy-prod` chỉ được dùng trên runner đã quản lý nhưng lại truy cập từ một máy chủ không nằm trong nhóm triển khai.

Nên kiểm tra đồng thời:

- ID tài sản và ID workload có khớp inventory không?
- IP quan sát là IP máy thực thi, proxy hay broker PAM?
- Có chuyển vùng, scale-out hoặc thay runner đã được duyệt không?
- Cơ chế xác thực có phù hợp với hồ sơ tài khoản không?
- Có bằng chứng bỏ qua broker bắt buộc không?

Một kết nối mới từ cùng IP NAT có thể đến từ thiết bị khác. Một IP mới cũng có thể chỉ do thay đường mạng. Vì vậy, quy tắc nên ưu tiên định danh tài sản và workload, rồi dùng mạng để bổ sung.

### 5.3. Hành động vượt nhiệm vụ

Tài khoản đọc báo cáo thực hiện gán role, sửa cấu hình xác thực hoặc tạo credential mới là sự lệch về chức năng, kể cả khi hệ thống cho phép hành động đó.

Các câu hỏi quan trọng:

1. Quyền này có thực sự cần cho chức năng dịch vụ không?
2. Hành động có xuất hiện trong định nghĩa job và thay đổi được duyệt không?
3. Người hoặc workload nào đã yêu cầu thao tác?
4. Tài nguyên bị tác động có nằm trong phạm vi được phép không?
5. Hành động có mở thêm khả năng truy cập hoặc làm giảm khả năng quan sát không?

Phát hiện hành vi và least privilege hỗ trợ nhau: quyền dư tạo khả năng bị lạm dụng; nhật ký hành động cho biết khả năng đó đã được sử dụng hay chưa.

### 5.4. Bất thường về tài nguyên, dữ liệu và lưu lượng

Các dấu hiệu có thể gồm truy cập tài nguyên lần đầu, đọc phạm vi dữ liệu lớn hơn thông lệ hoặc ghi đến một đích chưa được phê duyệt.

Cần phân biệt:

- Lưu lượng tăng vì khối lượng công việc tăng hay vì truy cập bất thường?
- Số hàng hoặc byte tăng do thay đổi dữ liệu, backfill hay thay đổi truy vấn?
- Đích nhận dữ liệu mới có thuộc dự án hợp lệ không?
- Có cùng lúc sự kiện lấy secret, tạo phiên mới hoặc thay quyền không?

“Lần đầu quan sát thấy” chỉ có ý nghĩa trong phạm vi dữ liệu lưu giữ. Nếu log chỉ có bảy ngày, không được diễn đạt thành “chưa từng xảy ra”.

### 5.5. Tài khoản đã nghỉ, mồ côi hoặc im lặng lâu ngày hoạt động lại

Một tài khoản đã được xác nhận ngừng sử dụng nhưng có xác thực thành công cần được xử lý ưu tiên.

Trước khi kết luận, kiểm tra:

- Trạng thái nghỉ đã được cập nhật chính thức hay chỉ là ghi chú chưa duyệt?
- Có tác vụ phục hồi, kiểm thử định kỳ hoặc DR sử dụng tài khoản không?
- Sự kiện là hoạt động mới hay log đến muộn?
- Tên đã được tái sử dụng cho principal khác chưa?

Principal ID và mốc vòng đời giúp tránh gộp hai danh tính có cùng tên. Tài khoản chỉ “không thấy log” không mặc nhiên đã nghỉ; có thể chưa được thu thập đầy đủ.

### 5.6. Hoạt động bất thường quanh việc đổi credential

Ví dụ đáng chú ý:

- Tạo credential bổ sung ngoài quy trình.
- Secret được cấp cho workload không thuộc danh sách bên sử dụng.
- Liên tục có lỗi xác thực sau rotation từ một nguồn không có trong inventory.
- Có hành động nhạy cảm trong phiên đã thiết lập trước khi credential bị thu hồi.

Không giả định rotate mật khẩu sẽ kết thúc mọi phiên hoặc vô hiệu hóa mọi token. Cách thu hồi phụ thuộc cơ chế xác thực và hệ thống đích. Log lỗi sau rotate cũng có thể chỉ ra consumer hợp lệ chưa được cập nhật.

### 5.7. Chuỗi tín hiệu quan trọng hơn từng sự kiện đơn lẻ

Ví dụ một chuỗi cần ưu tiên:

```text
Nguồn chưa được phép
    → tài khoản dịch vụ xác thực thành công
    → truy cập tài nguyên quản trị ngoài nhiệm vụ
    → tạo thêm quyền hoặc credential
```

Chuỗi này có độ đáng ngờ cao hơn một lần đăng nhập ngoài giờ. Tuy nhiên, “độ đáng ngờ cao” vẫn là căn cứ để điều tra và xử lý theo runbook, không phải bằng chứng duy nhất xác nhận danh tính người thực hiện.

## 6. Thiết kế quy tắc phát hiện có thể vận hành

### 6.1. Tách điều kiện vi phạm chính sách khỏi bất thường thống kê

Hai loại phát hiện cần được diễn giải khác nhau:

| Loại | Ví dụ | Cách diễn giải |
|---|---|---|
| Vi phạm điều kiện được duyệt | Tài khoản cấm tương tác nhưng có phiên tương tác đã xác định | Có căn cứ so với chính sách hiện hành |
| Sai lệch so với quan sát | Số tài nguyên truy cập cao hơn lịch sử gần đây | Cần xác minh baseline và thay đổi nghiệp vụ |
| Kết hợp nhiều tín hiệu | Nguồn lạ, thao tác quản trị và không có thay đổi hợp lệ | Ưu tiên điều tra vì nhiều bằng chứng hỗ trợ |

Nếu chưa có hồ sơ được duyệt, một mô hình bất thường không thể tự quyết định thế nào là hành vi được phép.

### 6.2. Mã giả cho đăng nhập tương tác không được phép

Mã sau diễn đạt logic, không phải câu lệnh chạy trực tiếp trên SIEM:

```text
FOR EACH successful_authentication_event:
    identity = lookup_identity_by_stable_id(event.principal_id)

    IF identity.type != "service_account":
        CONTINUE

    IF identity.policy.interactive_login_allowed != false:
        CONTINUE

    IF event.interaction_classification != "confirmed_interactive":
        CONTINUE

    exception = lookup_scoped_exception(
        principal_id = event.principal_id,
        source_asset_id = event.source_asset_id,
        target_resource_id = event.target_resource_id,
        event_time = event.event_time
    )

    IF exception.is_valid_and_covers_this_action:
        record_observation("approved_exception")
    ELSE:
        create_alert(
            rule = "SERVICE_ACCOUNT_UNAPPROVED_INTERACTIVE_USE",
            evidence = event,
            policy_version = identity.policy.version,
            missing_context = list_missing_fields(event)
        )
```

Thiếu owner hoặc thiếu mapping không phải lý do tự động bỏ qua sự kiện. Có thể tạo cảnh báo về chất lượng kiểm kê hoặc giảm độ chắc chắn của kết luận, đồng thời giữ bằng chứng để bổ sung.

Ngoại lệ phải khớp tài khoản, nguồn, đích, hành động và thời gian áp dụng. Một ticket hợp lệ cho triển khai không tự động hợp thức hóa việc tạo credential mới.

### 6.3. Mã giả cho chuỗi nguồn lạ và hành động nhạy cảm

```text
A = successful_authentication_events
    WHERE principal_type == "service_account"
    AND source_is_outside_approved_workload_scope

B = successful_target_actions
    WHERE action_category IN (
        "privilege_change",
        "credential_creation",
        "sensitive_configuration_change"
    )

CANDIDATES = correlate(
    A, B,
    strongest_available_keys = (
        principal_id,
        session_id,
        request_id,
        workload_id,
        target_resource_id
    ),
    event_time_window = locally_validated_window
)

FOR EACH candidate:
    evaluate_approved_change_scope(candidate)
    attach_identity_owner_and_dependencies(candidate)
    attach_original_event_references(candidate)
    state_correlation_confidence(candidate)
    create_or_update_case(candidate)
```

Nếu chỉ có `principal_id` và khoảng thời gian, có thể gộp nhầm hai job chạy song song dưới cùng tài khoản. Cảnh báo phải nói rõ mức tin cậy của liên kết. Không tự biến hai sự kiện gần nhau thành một phiên duy nhất.

### 6.4. Cửa sổ thời gian, ngưỡng và chống trùng

Không có ngưỡng chung phù hợp mọi dịch vụ. Một job báo cáo chạy mỗi ngày khác hoàn toàn một API xử lý liên tục.

Khi chọn ngưỡng, cân nhắc:

- Nhịp công việc, giờ cao điểm và lịch backfill.
- Độ trễ log và sai lệch đồng hồ.
- Thời gian tồn tại phiên hoặc token.
- Mức nhạy cảm của tài nguyên.
- Khả năng vận hành xử lý cảnh báo và độ đầy đủ của dữ liệu.

Có thể dùng cửa sổ 15 phút trong một bài kiểm thử minh họa, nhưng phải xác nhận bằng dữ liệu thực trước khi dùng cho production. Cửa sổ đó không phải chuẩn bắt buộc.

Dedup nên gộp các sự kiện cùng principal, nguồn, phiên và nhóm hành động phù hợp, đồng thời giữ số lượng và toàn bộ tham chiếu. Không được gộp đến mức che khuất việc hành vi lan sang đích mới.

## 7. Ưu tiên cảnh báo theo tác động và độ tin cậy

Tách hai câu hỏi: “Nếu đúng, ảnh hưởng đến đâu?” và “Bằng chứng hiện tại mạnh đến mức nào?”

| Tình huống | Tác động dự kiến | Đánh giá ban đầu |
|---|---|---|
| Job chạy bù ngoài giờ, nguồn và hành động đúng phạm vi | Có thể thấp hoặc trung bình tùy dữ liệu | Cần kiểm tra lịch và phê duyệt |
| Phiên tương tác từ máy không quản lý với tài khoản cấm tương tác | Cao nếu tài khoản có quyền đặc biệt | Ưu tiên xác minh và hạn chế phiên theo runbook |
| Tài khoản đọc báo cáo gán quyền quản trị | Cao | Lệch mục đích rõ; kiểm tra log thay quyền và nguồn yêu cầu |
| Tài khoản đã nghỉ xác thực thành công vào hệ thống nhạy cảm | Cao | Xác minh vòng đời, nguồn và phiên đang tồn tại |
| Log vault không có trong khi mô hình dùng danh tính workload | Chưa thể xác định | Kiểm tra đúng đường xác thực trước khi kết luận |
| Hệ thống đích ngừng gửi log | Mất khả năng quan sát | Xử lý vấn đề telemetry; không coi là bằng chứng dịch vụ an toàn |

Bảng là định hướng, không phải SLA. Mức ưu tiên cuối cùng phụ thuộc quyền thực tế, môi trường, dữ liệu bị ảnh hưởng và quy trình ứng phó của tổ chức.

Một cảnh báo hữu ích nên nêu rõ:

- Tài khoản nào, principal ID nào và chủ sở hữu nào.
- Hành vi nào lệch khỏi điều kiện được phê duyệt.
- Tài nguyên và quyền nhạy cảm nào liên quan.
- Các sự kiện gốc hỗ trợ nhận định.
- Ngoại lệ hoặc thay đổi nào đã được kiểm tra.
- Những phần ngữ cảnh còn thiếu.
- Bước xác minh tiếp theo và đội chịu trách nhiệm.

## 8. Điều tra một ca lạm dụng nghi ngờ

### 8.1. Tình huống minh họa

`svc-billing-export` chỉ được phép đọc view tổng hợp trên cơ sở dữ liệu báo cáo từ `runner-report-01`. Đăng nhập tương tác không được cho phép.

Trong dữ liệu mô phỏng, hệ thống phát hiện:

| Thời điểm | Sự kiện | Ý nghĩa cần kiểm tra |
|---|---|---|
| 10:14 | Xác thực thành công từ `host-admin-23` | Nguồn nằm ngoài hồ sơ được duyệt |
| 10:15 | Có phiên được nguồn log phân loại là tương tác | Có thể vi phạm điều kiện sử dụng |
| 10:17 | Hành động thay đổi quyền trên cơ sở dữ liệu | Vượt nhiệm vụ xuất báo cáo |
| 10:19 | Truy cập một tập dữ liệu ngoài view được phê duyệt | Cần xác định phạm vi dữ liệu đã đọc |

Chuỗi sự kiện tạo nghi ngờ mạnh, nhưng chưa cho biết credential bị lấy bằng cách nào hoặc ai thực sự điều khiển phiên.

### 8.2. Xác minh danh tính và thời gian

Đầu tiên đối chiếu principal ID, domain hoặc tenant để tránh nhầm với tài khoản cùng tên. Chuẩn hóa múi giờ, giữ timestamp gốc và kiểm tra độ trễ thu thập.

Sau đó xác định các sự kiện có cùng phiên hay chỉ cùng tên tài khoản. Nếu không có session ID chung, kết hợp nguồn, target, request ID và tiến trình; ghi rõ giới hạn của phép nối.

### 8.3. Kiểm tra hoạt động được phê duyệt

Tra cứu thay đổi, hỗ trợ sự cố và ngoại lệ trong đúng khoảng thời gian. Hỏi chủ sở hữu về mục đích hành động, run ID và nguồn thực thi.

Lời xác nhận “đó là job của đội tôi” chưa đủ nếu không giải thích được việc dùng máy ngoài phạm vi và thay quyền. Ngược lại, một runbook hỗ trợ hợp lệ có thể giải thích đăng nhập tương tác nhưng không bao phủ truy cập dữ liệu bổ sung.

### 8.4. Xác định phạm vi tác động

Điều tra theo câu hỏi cụ thể:

1. Có những phiên nào đang hoạt động dưới principal này?
2. Credential hoặc token nào có khả năng đã được sử dụng, được cấp lúc nào?
3. Tài khoản đã truy cập các tài nguyên nào ngoài hồ sơ?
4. Có quyền, credential, policy hay cấu hình nào mới được tạo?
5. Những hệ thống nào dùng chung credential hoặc có phụ thuộc với tài khoản?
6. Có hành vi tương tự từ nguồn đó với principal khác không?
7. Log có đủ để xác định dữ liệu đã đọc, sửa hoặc xuất không?

Không suy “không có truy vấn trong log” thành “không có truy cập dữ liệu” khi audit truy vấn chưa được bật hoặc bị thiếu.

### 8.5. Bảo toàn bằng chứng

Lưu tham chiếu sự kiện gốc, ID phiên, bản ghi thay đổi, trạng thái quyền trước và sau, phiên bản hồ sơ sử dụng và quyết định xử lý. Nếu có bản ghi phiên PAM, liên kết vào hồ sơ vụ việc theo chính sách lưu giữ.

Bằng chứng cần có thời gian, nguồn, người thu thập, quyền truy cập và kiểm tra tính toàn vẹn theo quy trình nội bộ. Tránh sao chép secret hoặc dữ liệu khách hàng không cần thiết vào ticket.

Đội điều tra cũng phải dùng danh tính cá nhân có truy vết và quyền phù hợp. Không dùng chính tài khoản dịch vụ bị nghi ngờ để điều tra vì điều đó làm nhiễu timeline.

## 9. Cô lập và khôi phục có tính đến phụ thuộc

### 9.1. Chọn biện pháp theo mức độ khẩn cấp

Tắt một tài khoản đặc quyền có thể chặn hành vi xấu nhưng cũng làm gián đoạn nhiều dịch vụ. Phụ thuộc vận hành cần được biết trước trong inventory, thay vì bắt đầu tìm khi sự cố đã xảy ra.

Các biện pháp có thể xem xét theo runbook và thẩm quyền:

- Kết thúc phiên đáng ngờ nếu hệ thống hỗ trợ.
- Chặn nguồn thực thi không được phép hoặc cách ly workload bị ảnh hưởng.
- Giới hạn tạm quyền và tài nguyên được truy cập.
- Thu hồi credential hoặc token liên quan bằng cơ chế được hệ thống hỗ trợ.
- Vô hiệu hóa tài khoản khi rủi ro tiếp diễn và quy trình ứng phó yêu cầu.
- Chuyển sang danh tính thay thế đã chuẩn bị, với quyền hẹp và thời hạn rõ ràng.

Không nhất thiết phải làm theo thứ tự cố định. Khi đang có hành vi phá hoại hoặc rò rỉ tiếp diễn, việc cô lập khẩn cấp có thể phải thực hiện trước khi hoàn tất mọi bước thu thập bằng chứng.

### 9.2. Rotation là một phần của khôi phục

Nếu credential có nguy cơ lộ, kế hoạch đổi cần xác định đầy đủ consumer, nơi phân phối và cơ chế cache.

Một trình tự khôi phục có kiểm soát có thể gồm:

1. Hạn chế nguồn hoặc workload bị nghi ngờ để tránh credential mới tiếp tục bị lấy.
2. Xác định các phiên, token và credential liên quan.
3. Phát hành credential thay thế và cập nhật đúng consumer.
4. Thu hồi credential cũ, token hoặc phiên theo khả năng thực tế của nền tảng.
5. Kiểm tra tác vụ nghiệp vụ, lỗi xác thực và quyền còn tồn tại.
6. Theo dõi lại hành vi và đối chiếu trạng thái cuối với hồ sơ được duyệt.

Thứ tự phát hành và thu hồi phải theo cơ chế của hệ thống và mức độ khẩn cấp. Không giữ credential bị nghi lộ chỉ để tránh bất tiện vận hành khi đã có yêu cầu cô lập khẩn cấp.

Rotation có trạng thái “thành công” trong vault chưa đủ chứng minh mọi consumer đã cập nhật. Cần kiểm tra kết nối mới và phiên cũ, bao gồm connection pool hoặc token đã được phát hành trước đó.

### 9.3. Loại bỏ nguyên nhân gốc

Nếu ứng dụng bị xâm nhập, chỉ đổi secret sẽ không giải quyết được việc ứng dụng tiếp tục sử dụng quyền hợp lệ sai mục đích.

Khắc phục có thể bao gồm sửa workload, loại bỏ quyền dư, tách danh tính dùng chung, giới hạn nguồn, tăng kiểm soát phát hành và cải thiện log. Chỉ khôi phục đầy đủ quyền khi có bằng chứng đáp ứng điều kiện phục hồi và người có thẩm quyền đã chấp thuận theo quy trình.

## 10. Vai trò của PAM và kiểm soát phòng ngừa

### 10.1. Vault và phân phối secret

Vault giúp quản lý quyền lấy secret, lịch sử cấp và vòng đời credential. Quyền đọc secret phải giới hạn theo workload và mục đích; không cấp cho một nhóm rộng chỉ vì nhiều ứng dụng dùng chung nền tảng.

Cần giám sát cả sự kiện lấy secret và hành động tại hệ thống đích. Vault không tự ngăn một consumer hợp lệ sử dụng secret để làm việc ngoài mục đích.

### 10.2. Least privilege và tách danh tính

Tách tài khoản theo ứng dụng, môi trường và chức năng giúp:

- Thu hẹp phạm vi ảnh hưởng.
- Xác định owner và baseline rõ hơn.
- Cô lập một dịch vụ mà ít tác động sang dịch vụ khác.
- Đối chiếu quyền được cấp với hành động thực sự cần.

Nếu một tài khoản cùng lúc triển khai, sao lưu và xuất báo cáo, rất khó xây dựng chính sách phát hiện đủ chặt.

### 10.3. JIT và JEA

JIT giảm thời gian duy trì quyền đặc biệt khi workflow hỗ trợ cấp quyền theo yêu cầu hoặc theo thời hạn. JEA giới hạn thao tác hoặc khả năng được thực hiện trong những mô hình có hỗ trợ.

Đối với workload hoạt động liên tục, không ép quy trình phê duyệt thủ công cho mọi request. Cần thiết kế cấp quyền tự động có ràng buộc, thời hạn và truy vết phù hợp với hệ thống.

Dù quyền chỉ tồn tại trong thời gian ngắn, vẫn phải giám sát hành động xảy ra trong khoảng đó.

### 10.4. Danh tính workload và credential ngắn hạn

Giảm secret tĩnh có thể giảm rủi ro credential bị lưu lâu và tái sử dụng. Tuy nhiên, workload bị xâm nhập vẫn có thể sử dụng danh tính đang hợp lệ.

Do đó, cần kiểm tra điều kiện cấp danh tính, nguồn thực thi, phạm vi token và hành động tại đích. “Không dùng mật khẩu” không phải tiêu chí đủ để miễn giám sát lạm dụng.

### 10.5. Quyền khẩn cấp

Khi dịch vụ cần khôi phục gấp, cơ chế break-glass phải có người chịu trách nhiệm, thời hạn, ghi bằng chứng và rà soát sau sử dụng.

Không dùng tài khoản dịch vụ như một tài khoản khẩn cấp dùng chung không truy vết. Nếu buộc phải có ngoại lệ, cần định danh người khởi tạo và giới hạn cụ thể thay vì tắt toàn bộ cảnh báo.

## 11. Sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ tìm đăng nhập thất bại | Bỏ sót hành vi xấu dùng credential hợp lệ | Theo dõi hành động sau xác thực |
| Chỉ nhận diện tài khoản qua tên `svc-` | Thiếu danh tính workload hoặc gộp nhầm tài khoản | Dùng principal ID và inventory |
| Coi mọi shell là đăng nhập tương tác | Nhiễu từ job chạy script | Đối chiếu loại phiên, nguồn và cây tiến trình |
| Whitelist cả tài khoản sau một ticket | Miễn giám sát hành vi ngoài ngoại lệ | Ngoại lệ có phạm vi và hết hạn |
| Chỉ nhìn IP | Sai lệch do NAT, proxy và runner dùng chung | Kết hợp tài sản, workload và phiên |
| Coi checkout vault là sự phê duyệt mọi hành động | Bỏ sót hành vi sau khi lấy secret | Đối chiếu policy và log tại đích |
| Rotate rồi đóng sự cố | Phiên hoặc token cũ có thể còn dùng được | Kiểm tra thu hồi và hoạt động còn lại |
| Tự động tắt mọi tài khoản bị cảnh báo | Có thể gây gián đoạn dây chuyền | Áp dụng runbook theo tác động và mức tin cậy |
| Dùng lịch sử làm allowlist tuyệt đối | Học cả hành vi sai đã tồn tại | Kết hợp hồ sơ được phê duyệt và rà soát owner |
| Không thấy log thì coi là an toàn | Che khuất khoảng trống quan sát | Theo dõi độ đầy đủ và độ trễ telemetry |

## 12. Bài thực hành với dữ liệu mô phỏng

### 12.1. Đề bài

Dùng hồ sơ của `svc-billing-export` ở phần trước và bảng sự kiện giả định sau. Không cần dùng credential hoặc hệ thống production.

| Mã | Sự kiện | Ngữ cảnh đi kèm |
|---|---|---|
| A | Job chạy 01:20 từ runner đúng, chỉ đọc view được phép | Có run ID và lịch chạy |
| B | Job chạy bù 09:00 từ runner đúng | Ticket còn hiệu lực chỉ cho chạy lại báo cáo |
| C | Tài khoản đăng nhập tương tác từ máy cá nhân | Không có ngoại lệ |
| D | Tạo credential bổ sung từ runner đúng lúc 01:30 | Không thuộc nhiệm vụ và không có thay đổi bao phủ |
| E | Số byte đọc tăng gấp ba nhưng vẫn ở view được phép | Dữ liệu đầu vào tăng, cần xác minh |
| F | Không có log đích trong hai giờ | Collector đang lỗi; vẫn nhận log xác thực |
| G | Xác thực mới với tài khoản đã xác nhận nghỉ | Principal ID khớp danh tính đã nghỉ |
| H | Nhiều lỗi xác thực sau rotation từ host chưa kiểm kê | Chưa biết host là consumer hợp lệ hay nguồn khác |

Yêu cầu:

1. Chỉ ra trường hợp vi phạm điều kiện, trường hợp bất thường cần xác minh và trường hợp thiếu khả năng quan sát.
2. Chọn bằng chứng tiếp theo cần lấy cho từng trường hợp.
3. Xác định trường hợp cần ưu tiên cao hơn dựa trên quyền và tài nguyên.
4. Mô tả biện pháp cô lập có thể áp dụng và tác động nghiệp vụ cần xem xét.
5. Viết một quy tắc phát hiện có ngoại lệ theo phạm vi và thời hạn.

### 12.2. Gợi ý lập luận

- **A:** phù hợp hồ sơ trong dữ liệu đã có; giữ truy vết, không cần cảnh báo chỉ vì dùng tài khoản dịch vụ.
- **B:** giờ chạy khác lịch nhưng có thể được ngoại lệ bao phủ. Cần kiểm tra ticket đúng principal, nguồn, hành động và thời gian.
- **C:** có dấu hiệu vi phạm điều kiện cấm tương tác; xác minh phân loại phiên và ưu tiên xử lý theo quyền thực tế.
- **D:** nguồn và giờ đúng không hợp thức hóa hành động tạo credential. Cần xem log thay đổi, người khởi tạo và quyền mới.
- **E:** có sai lệch về lượng; chưa đủ kết luận rò rỉ. Đối chiếu số lượng dữ liệu, phạm vi truy vấn và đích nhận.
- **F:** là vấn đề telemetry; không thể dùng khoảng trống log để kết luận không có hành động tại đích.
- **G:** ưu tiên cao vì trái vòng đời đã xác nhận; kiểm tra timestamp gốc, nguồn và phiên hoạt động.
- **H:** cần vừa điều tra credential cũ bị dùng vừa rà soát consumer còn thiếu. Lỗi sau rotation tự nó chưa phân biệt được hai khả năng.

Một kết quả thực hành tốt phải phân biệt điều đã chứng minh, điều chỉ mới nghi ngờ và dữ liệu còn thiếu.

## 13. Kiểm tra chất lượng phát hiện và điều kiện đóng vụ việc

### 13.1. Kiểm tra quy tắc bằng kịch bản có kiểm soát

Trước khi dùng một quy tắc để tự động cô lập, kiểm tra nó bằng dữ liệu mô phỏng hoặc môi trường được phép:

- Hoạt động hợp lệ trong lịch có bị cảnh báo nhầm không?
- Ngoại lệ đúng phạm vi có được nhận diện không?
- Ngoại lệ hết hạn hoặc sai đích có còn bị bỏ qua không?
- Phiên tương tác trái điều kiện có tạo cảnh báo không?
- Hai job cùng principal có bị nối nhầm thành một phiên không?
- Log đến muộn hoặc thiếu trường có được thể hiện rõ không?
- Cảnh báo có giữ tham chiếu sự kiện gốc và owner không?
- Khi principal bị đổi tên, quy tắc có tiếp tục theo dõi bằng ID không?

Đây là kiểm tra cho cơ chế phát hiện trong nội dung bài học. Mục tiêu là biết quy tắc quan sát được gì và giới hạn ở đâu, không phải tạo lưu lượng tấn công vào hệ thống thật.

### 13.2. Các chỉ số hữu ích

Có thể theo dõi tỷ lệ tài khoản đặc quyền có owner, tỷ lệ có hồ sơ sử dụng, tỷ lệ log nối được đến workload, độ trễ phát hiện, tỷ lệ cảnh báo cần xử lý và thời gian khôi phục credential.

Luôn ghi rõ mẫu số và phạm vi đo. Ví dụ “90% tài khoản có log” không thể hiện đầy đủ nếu không biết đang tính số tài khoản đã kiểm kê hay mọi danh tính thực tế.

Ít cảnh báo hơn không tự chứng minh hệ thống tốt hơn. Cần xem có giảm nhiễu mà vẫn phát hiện được kịch bản quan trọng, hay chỉ giảm khả năng quan sát.

### 13.3. Điều kiện đóng vụ việc

Một vụ việc nghi lạm dụng tài khoản dịch vụ chỉ nên được đóng khi đã có kết luận và căn cứ phù hợp với quy trình:

- Mục đích sử dụng được xác minh hoặc hành vi không hợp lệ được xác định rõ.
- Phạm vi quyền, phiên, credential và tài nguyên liên quan đã được đánh giá.
- Biện pháp cô lập, thu hồi hoặc khắc phục cần thiết đã thực hiện và kiểm tra.
- Consumer hợp lệ hoạt động sau khôi phục, các quyền hoặc credential phát sinh được xử lý.
- Khoảng trống dữ liệu còn lại được ghi nhận và giao người theo dõi.
- Hồ sơ sử dụng, phụ thuộc và quy tắc phát hiện được cập nhật có kiểm soát.
- Bằng chứng và quyết định được lưu theo yêu cầu truy vết.

Phát hiện lạm dụng tài khoản dịch vụ hiệu quả dựa trên mối liên hệ giữa danh tính, workload, quyền và hành động. Khi PAM cung cấp vòng đời credential và bằng chứng phiên, hệ thống đích cung cấp hành động thực tế, còn owner xác nhận mục đích, đội vận hành mới có căn cứ để xử lý đúng mức.
