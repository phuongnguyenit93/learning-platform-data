# Phát hiện nỗ lực đi vòng PAM (PAM bypass attempt)

## 1. PAM bypass attempt là gì?

Trong quản trị truy cập đặc quyền, **PAM bypass attempt** là hành vi cố sử dụng quyền quản trị ngoài những kiểm soát bắt buộc của mô hình PAM đã được phê duyệt. Kiểm soát đó có thể gồm xác thực mạnh, phê duyệt yêu cầu, cấp quyền có thời hạn, lấy credential qua vault, đi qua broker, ghi nhận phiên hoặc giới hạn thao tác trên đích.

Điểm cần xác định là **kiểm soát nào thực sự bắt buộc đối với đường truy cập cụ thể**. Không phải mọi kết nối quản trị không qua một jump host đều là bypass. Một workload dùng danh tính ngắn hạn theo chính sách máy với máy có thể hoàn toàn hợp lệ; ngược lại, một quản trị viên đã mở phiên PAM vẫn có thể dùng một tài khoản khác để thao tác ngoài phiên đó.

Ví dụ: chính sách của máy chủ `db-prod-07` yêu cầu mọi phiên quản trị tương tác phải được broker PAM cấp, gắn với một yêu cầu còn hiệu lực và được ghi nhận. Một người thử đăng nhập trực tiếp bằng tài khoản quản trị cục bộ từ máy cá nhân đã tạo ra dấu hiệu cần điều tra. Nếu đích chặn kết nối thì đây có thể là một nỗ lực bị ngăn chặn. Nếu đích chấp nhận đăng nhập đặc quyền, rủi ro và mức độ ưu tiên tăng lên, nhưng vẫn phải đối chiếu ngoại lệ và độ tin cậy của bằng chứng trước khi kết luận.

Bài học tập trung vào cách thiết kế phát hiện, thu thập bằng chứng và xử lý cảnh báo. Mục tiêu là trả lời được bốn câu hỏi:

1. Ai hoặc workload nào đang sử dụng quyền gì trên tài nguyên nào?
2. Đường truy cập và quyền đó có được chính sách cho phép tại thời điểm xảy ra không?
3. PAM, hệ điều hành, mạng và control plane cung cấp bằng chứng gì?
4. Đây là nỗ lực bị chặn, truy cập trái chính sách đã thành công, ngoại lệ hợp lệ hay khoảng trống quan sát?

## 2. Xác định ranh giới PAM trước khi viết rule

### 2.1. Biến yêu cầu quản trị thành điều kiện kiểm chứng được

Mô tả “mọi truy cập phải qua PAM” chưa đủ để xây dựng detection. Với từng nhóm tài nguyên, cần biết loại truy cập nào nằm trong phạm vi và bằng chứng nào thể hiện việc tuân thủ.

| Thành phần chính sách | Câu hỏi cần trả lời | Ví dụ điều kiện |
|---|---|---|
| Tài nguyên | Đích nào thuộc phạm vi? | Máy chủ production có định danh tài sản ổn định |
| Chủ thể | Người dùng, service account hay workload? | Quản trị viên tương tác dùng danh tính cá nhân |
| Loại quyền | Quyền nào được coi là đặc quyền? | Đăng nhập quản trị, nâng quyền, sửa vai trò, đọc credential |
| Đường truy cập | Có bắt buộc broker, gateway hoặc endpoint control không? | Phiên SSH tương tác phải xuất phát từ broker được cấp phép |
| Cấp quyền | Quyền được cấp trong khoảng nào, cho đối tượng nào? | JIT cho một tài khoản và một tập tài nguyên cụ thể |
| Phê duyệt | Điều kiện nào tạo quyền sử dụng hợp lệ? | Yêu cầu được phê duyệt và chưa bị thu hồi |
| Quan sát | Những sự kiện nào phải được ghi lại? | Đích ghi nhận phiên; broker phát sự kiện bắt đầu và kết thúc |
| Ngoại lệ | Trường hợp nào được đi theo đường khác? | Break-glass có người chịu trách nhiệm, hạn dùng và kiểm tra sau sự kiện |

Một chính sách có thể bắt buộc vault và JIT nhưng không bắt buộc session proxy cho API. Khi đó, thiếu phiên proxy không tự động là bypass. Ngược lại, việc một người vừa checkout mật khẩu không chứng minh kết nối trực tiếp của người đó được phép nếu chính sách vẫn bắt buộc broker.

### 2.2. Phân biệt các lớp kiểm soát

Các lớp sau có liên quan nhưng không thay thế cho nhau:

- **Quản lý credential:** ai được lấy hoặc sử dụng mật khẩu, key, token và trong bao lâu.
- **Quản lý quyền:** ai được kích hoạt vai trò hoặc nâng quyền, phạm vi và thời hạn ra sao.
- **Quản lý đường truy cập:** kết nối có phải đi qua một điểm kiểm soát được phê duyệt hay không.
- **Quản lý phiên và lệnh:** phiên nào được quan sát, ghi lại hoặc giới hạn thao tác.
- **Quản trị ngoại lệ:** khi nào được dùng đường khẩn cấp, cách báo động và đối soát sau đó.

Một phiên có credential hợp lệ nhưng đi sai đường vẫn có thể vi phạm. Một phiên đi qua broker nhưng dùng quyền đã bị thu hồi cũng cần điều tra. Detection phải nêu rõ lớp kiểm soát bị tác động, tránh dùng một nhãn bypass cho mọi lỗi PAM.

## 3. Những nhóm dấu hiệu thường gặp

### 3.1. Truy cập quản trị trực tiếp vào tài nguyên được bảo vệ

Dấu hiệu điển hình là đăng nhập đặc quyền vào đích có chính sách bắt buộc broker, trong khi đường kết nối được quan sát nằm ngoài tập đường cho phép.

Cần kết hợp ít nhất ba dữ kiện: tài nguyên đang thuộc phạm vi chính sách, phiên hoặc kết nối thực tế tại đích, và thông tin đường truy cập đủ tin cậy. Địa chỉ IP đơn lẻ thường chưa đủ vì NAT, gateway, proxy hoặc broker theo vùng có thể làm thay đổi địa chỉ nhìn thấy.

Kết nối bị từ chối bởi firewall chỉ chứng minh có lưu lượng tới một đường bị chặn. Nó chưa chứng minh người gửi đã có credential quản trị hoặc đã chủ đích đi vòng PAM. Cảnh báo nên phản ánh đúng mức bằng chứng, chẳng hạn “thử truy cập cổng quản trị ngoài đường cho phép”, thay vì khẳng định đã có phiên đặc quyền.

### 3.2. Dùng credential ngoài quan hệ cấp phát dự kiến

Một credential được quản lý trong vault có thể xuất hiện trong hoạt động không khớp người nhận, tài nguyên, thời gian hoặc phương thức sử dụng được cho phép. Những tình huống đáng chú ý gồm:

- Tài khoản vừa được checkout nhưng đăng nhập từ một nguồn không thuộc người hoặc workload nhận credential.
- Credential đã hết thời hạn sử dụng theo chính sách nhưng tiếp tục tạo phiên mới.
- Một tài khoản chia sẻ được dùng đồng thời trên các đích không thuộc phạm vi cấp phát.
- Tài khoản lẽ ra chỉ được broker sử dụng lại xuất hiện trong phiên tương tác trực tiếp.

Không ghi mật khẩu, private key hay bearer token vào log để chứng minh việc sử dụng. Dùng ID của đối tượng credential, phiên bản credential nếu hệ thống cung cấp, audit ID và quan hệ cấp phát. Với tài khoản dùng chung, trùng tên tài khoản không đủ để quy trách nhiệm cho một người; cần chuỗi bằng chứng bổ sung.

### 3.3. Tiếp tục hoặc mở rộng quyền ngoài phạm vi JIT/JEA

JIT giới hạn thời gian được cấp quyền; JEA giới hạn khả năng quản trị cần thiết. Những tín hiệu liên quan gồm yêu cầu nâng quyền cho tài nguyên ngoài phạm vi đã phê duyệt, sử dụng vai trò khác với vai trò được cấp, hoặc tạo phiên mới sau khi quyền đã hết hạn hay bị thu hồi.

Cần phân biệt **thời hạn được phép mở phiên** và **thời hạn phiên được phép tiếp tục tồn tại**. Hết thời hạn JIT không mặc nhiên đồng nghĩa mọi phiên hiện hữu phải bị đóng ngay; điều này phụ thuộc thiết kế và chính sách. Rule phải đối chiếu đúng loại thời hạn thay vì dùng một timestamp cho mọi quyết định.

### 3.4. Can thiệp vào thành phần cưỡng chế hoặc ghi nhận

Các thay đổi như dừng dịch vụ ghi phiên, sửa chính sách audit, vô hiệu hóa endpoint control, thay đổi cấu hình gateway hoặc gỡ cơ chế giới hạn nâng quyền có thể là tín hiệu chuẩn bị bypass.

Chỉ sự kiện thay đổi cấu hình chưa đủ kết luận độc hại. Cần đối chiếu người thực hiện, change đã duyệt, phạm vi, thời gian bảo trì, trạng thái sau thay đổi và hoạt động đặc quyền xuất hiện tiếp theo. Chuỗi “tắt kiểm soát → đăng nhập ngoài đường cho phép → thao tác nhạy cảm” thường có giá trị điều tra cao hơn từng sự kiện riêng lẻ.

Mất log không nhất thiết do can thiệp. Mất kết nối, lỗi collector, thay đổi định dạng hoặc hàng đợi chậm cũng tạo ra biểu hiện tương tự. Sự kiện kiểm soát bị thay đổi và sự kiện nguồn log không khỏe phải được phân loại riêng.

### 3.5. Thay đổi quyền hoặc danh tính để rời khỏi phạm vi PAM

Một người có thể tạo tài khoản quản trị khác, thêm SSH key, thêm credential cho ứng dụng hoặc thay đổi thành viên nhóm đặc quyền. Đó là các thay đổi cần được phát hiện, nhưng chỉ trở thành bằng chứng liên quan tới bypass khi gắn với chính sách và cách sử dụng tiếp theo.

Ví dụ: một tài khoản quản trị mới không được onboard vào PAM, sau đó đăng nhập trực tiếp vào tài nguyên bắt buộc broker. Chuỗi này cho thấy một khoảng trống kiểm soát rõ hơn việc chỉ phát hiện tài khoản mới.

Không giới hạn detection ở đăng nhập hệ điều hành. Cloud console, API quản trị, control plane của cơ sở dữ liệu, nền tảng container và công cụ quản trị từ xa đều có thể là bề mặt sử dụng quyền đặc biệt. Mỗi bề mặt cần mô hình cấp quyền và telemetry riêng.

## 4. Nguồn dữ liệu và chất lượng bằng chứng

### 4.1. Những nguồn cần tương quan

| Nguồn | Bằng chứng hữu ích | Giới hạn phải biết |
|---|---|---|
| PAM/vault | Yêu cầu, phê duyệt, checkout, cấp quyền, thu hồi, phiên broker | Không nhất thiết quan sát được kết nối ngoài PAM |
| Đích được quản trị | Đăng nhập, kết quả xác thực, nâng quyền, thay đổi tài khoản | Tên tài khoản có thể chia sẻ; IP có thể là gateway |
| Identity provider | Danh tính ổn định, xác thực, phát token, hoạt động vai trò | Token được phát không chứng minh mọi lần sử dụng đều hợp lệ |
| Firewall/flow/gateway | Đường kết nối, nguồn, đích, giao thức, quyết định cho phép | Không tự chứng minh người dùng hoặc quyền của phiên |
| EDR/endpoint audit | Tiến trình, phiên người dùng, thay đổi dịch vụ và policy | Mức phủ, khả năng chống can thiệp khác nhau giữa các đích |
| Cloud hoặc platform audit | Chủ thể, vai trò, tài nguyên, hành động quản trị, kết quả | Có thể trễ và có chuỗi danh tính qua nhiều vai trò |
| Asset inventory/policy | Phạm vi PAM, owner, criticality, ngoại lệ, phiên bản policy | Inventory sai làm sai điều kiện áp dụng rule |
| Change/incident system | Bảo trì, break-glass, người chịu trách nhiệm, thời hạn | Một mã ticket tồn tại chưa đồng nghĩa thao tác được phép |

Không cần mọi nguồn cho mọi rule, nhưng mỗi kết luận phải chỉ rõ nguồn nào chứng minh nó. Nếu muốn kết luận có truy cập đặc quyền thành công, cần sự kiện thành công có thẩm quyền từ đích hoặc control plane tương ứng, không chỉ sự kiện mạng cho phép kết nối.

### 4.2. Chuẩn hóa theo định danh ổn định

Một mô hình sự kiện tối thiểu có thể gồm:

```json
{
  "event_id": "target-evt-7841",
  "event_time": "2026-10-15T02:12:05Z",
  "ingest_time": "2026-10-15T02:12:09Z",
  "source_type": "target_audit",
  "principal_issuer": "corp-idp",
  "principal_id": "person-1042",
  "target_account_id": "local-admin-17",
  "asset_id": "asset-db-prod-07",
  "action": "privileged_login",
  "outcome": "success",
  "access_mode": "interactive",
  "observed_connection_id": "conn-5810",
  "observed_source_zone": "admin-workstation",
  "policy_version": "pam-path-prod-v12"
}
```

Đây là schema minh họa do hệ thống phân tích chuẩn hóa, không phải định dạng log của một sản phẩm cụ thể. Chỉ điền `principal_id` nếu có bằng chứng ánh xạ hợp lệ. Nếu chỉ biết tài khoản đích, lưu danh tính con người là chưa xác định; không suy từ người checkout gần nhất.

Nên lưu thêm các quan hệ cần thiết khi có sẵn:

- ID phiên broker, ID phiên tại đích và cách hai ID được nối với nhau.
- ID yêu cầu, quyền được cấp, tài nguyên và loại truy cập được phê duyệt.
- Khoảng hiệu lực của phiên, quyền, ngoại lệ và cấu hình đường truy cập.
- Danh tính gốc, danh tính trung gian và vai trò cuối cùng của chuỗi ủy quyền.
- IP trước/sau NAT, cổng, giao thức và ID flow khi có dữ liệu mạng phù hợp.
- Nguồn ánh xạ, độ tin cậy và phiên bản của phép chuẩn hóa.

ID phiên trong một trường do client tự khai không phải bằng chứng đáng tin để bỏ qua cảnh báo. Quan hệ phiên cần được xác nhận bởi broker, đích, gateway hoặc nguồn có thẩm quyền. Không dùng so khớp một chuỗi bất kỳ trong tên tiến trình để coi phiên là hợp lệ.

### 4.3. Thời gian, độ trễ và tính đầy đủ

Tương quan cần dùng `event_time` để đánh giá chính sách tại thời điểm hoạt động và dùng `ingest_time` để theo dõi dữ liệu tới muộn. Đồng hồ lệch, mất sự kiện, thứ tự ingest đảo ngược và sự kiện kết thúc phiên tới chậm đều có thể làm sai kết quả.

Ví dụ, log tại đích tới lúc 02:12:09 nhưng sự kiện broker lúc 02:12:04 chỉ tới hệ thống phân tích lúc 02:14:20. Tại 02:12:10, kết luận “không có phiên PAM” là quá sớm nếu độ trễ thông thường cho phép tình huống này.

Mỗi pipeline nên có:

1. Ngân sách độ trễ theo nguồn và cơ chế đánh giá lại sự kiện tới muộn.
2. Theo dõi độ khỏe collector, độ lệch đồng hồ và tính liên tục của audit stream.
3. Khoảng lưu dữ liệu đủ cho các phiên dài và quyết định điều tra.
4. Chính sách xử lý khoảng thời gian chưa đủ bằng chứng, thay vì coi thiếu dữ liệu là phủ định chắc chắn.

Một watermark vượt thời điểm cần đối soát cho thấy pipeline đã xử lý dữ liệu tới mức kỳ vọng, nhưng **không chứng minh nguồn chưa từng làm mất sự kiện**. Vì vậy, sức khỏe nguồn và bằng chứng đường truy cập vẫn phải được xét riêng.

## 5. Thiết kế detection theo bằng chứng, không chỉ theo sự vắng mặt

### 5.1. Hai hướng phát hiện bổ sung cho nhau

**Hướng có bằng chứng dương:** quan sát một hành vi trái điều kiện rõ ràng, chẳng hạn đích ghi nhận đăng nhập đặc quyền thành công từ đường kết nối đã được xác minh là bị cấm theo policy hiệu lực. Đây là cơ sở mạnh để phát hiện vi phạm đường truy cập.

**Hướng đối soát thiếu quan hệ:** đích ghi nhận phiên đặc quyền nhưng chưa tìm được phiên broker hoặc quyền cấp phù hợp. Hướng này hữu ích để tìm khoảng trống, nhưng ban đầu chỉ nên coi là ứng viên cần đối soát. Sau cửa sổ chờ, nếu nguồn khỏe mà vẫn thiếu quan hệ thì có thể nâng ưu tiên điều tra; không tự biến sự vắng mặt thành bằng chứng tuyệt đối về ý đồ.

Tách hai hướng giúp đội vận hành biết cảnh báo nào cần xử lý một kết nối trái chính sách và cảnh báo nào cần làm rõ khả năng quan sát.

### 5.2. Điều kiện khớp một hoạt động hợp lệ

Một hoạt động có thể được coi là phù hợp khi khớp các điều kiện bắt buộc trong policy áp dụng:

```text
valid_activity =
    policy_applies_at(event_time)
    AND principal_binding_is_valid
    AND target_and_account_are_in_scope
    AND access_mode_is_allowed
    AND required_grant_is_valid_at(event_time)
    AND required_path_is_verified
    AND required_session_is_bound_to_target_activity
    AND no_applicable_revocation_before(event_time)
```

Đây là mô hình khái niệm. Những điều kiện không bắt buộc theo policy không nên bị ép áp dụng. Ví dụ, API workload không cần phiên tương tác nếu chính sách của nó quy định danh tính workload và audit API thay cho session proxy.

Khoảng thời gian nên được định nghĩa nhất quán, chẳng hạn `[start, end)` với thời điểm bắt đầu được tính và thời điểm kết thúc không được tính. Nếu chưa có sự kiện kết thúc phiên, chỉ xem phiên còn hiệu lực theo lease hoặc heartbeat được tin cậy và giới hạn thời gian cụ thể; không mặc định nó còn hiệu lực vô hạn.

Đối với phiên đã được mở hợp lệ, hoạt động sau đó phải đối chiếu chính sách duy trì phiên. Không áp dụng máy móc điều kiện “grant còn hiệu lực để mở phiên” cho mọi sự kiện trong phiên nếu cơ chế được phê duyệt có quy tắc khác.

### 5.3. Luồng quyết định minh họa

```text
Hoạt động quản trị được quan sát
    |
    +-- Policy không yêu cầu kiểm soát PAM tương ứng
    |      -> Chuyển bộ rule phù hợp, không gán nhãn bypass ở rule này
    |
    +-- Ngoại lệ hợp lệ, đúng chủ thể/đích/thời gian/phạm vi
    |      -> Theo dõi và đối soát theo quy trình ngoại lệ
    |
    +-- Có bằng chứng dương cho thấy đường truy cập bị cấm
    |      -> Cảnh báo vi phạm; phân biệt bị chặn và thành công
    |
    +-- Khớp đầy đủ quan hệ PAM bắt buộc
    |      -> Ghi nhận đối soát thành công
    |
    +-- Thiếu quan hệ bắt buộc
           |
           +-- Dữ liệu chưa tới đủ hoặc nguồn không khỏe
           |      -> Pending hoặc telemetry gap
           |
           +-- Đã đủ điều kiện đối soát, vẫn không khớp
                  -> Cảnh báo nghi ngờ bypass để điều tra
```

Đường truy cập “chưa biết” không đồng nghĩa đường truy cập “bị cấm”. Rule cần phân biệt ít nhất ba trạng thái: cho phép, bị cấm, chưa xác định.

### 5.4. Pseudocode cho đối soát phiên

Đoạn dưới mô tả logic phân loại, không phải lệnh thực thi trên hệ thống đích hoặc truy vấn dành riêng cho một SIEM:

```text
for activity in normalized_privileged_activities:
    policy = effective_policy(activity.asset_id, activity.event_time)

    if policy is missing or asset_binding_is_uncertain(activity):
        emit("policy_or_inventory_gap", activity)
        continue

    requirements = policy.for_mode(activity.access_mode)
    if requirements is not applicable:
        continue

    exception = matching_exception(activity, policy)
    if exception is valid:
        emit("exception_activity_for_review", activity, exception)
        continue

    path = verify_observed_path(activity, policy)
    if path == "explicitly_forbidden":
        emit("suspected_pam_path_violation", activity,
             evidence=path.evidence,
             result=activity.outcome)
        continue

    if not reconciliation_window_ready(activity):
        defer(activity)
        continue

    if not required_sources_healthy(activity, requirements):
        emit("telemetry_gap", activity)
        continue

    binding = resolve_required_pam_binding(activity, requirements)
    if binding == "verified_valid":
        record_reconciliation_success(activity)
    elif binding == "verified_invalid":
        emit("suspected_pam_authorization_violation", activity,
             evidence=binding.evidence)
    else:
        emit("unmatched_privileged_activity", activity)
```

`resolve_required_pam_binding` cần xét yêu cầu, grant, đường truy cập và phiên theo đúng phạm vi. Tìm thấy một phiên PAM có cùng người dùng trong cùng giờ không đủ. Một người có thể mở phiên hợp lệ tới máy A và đồng thời truy cập trực tiếp vào máy B.

Khi dữ liệu tới muộn làm thay đổi kết luận, cập nhật cảnh báo hiện có bằng bằng chứng mới và giữ lịch sử quyết định. Không xóa dấu vết cảnh báo ban đầu hoặc sinh lặp vô hạn cùng một sự kiện.

## 6. Các rule cụ thể có thể xây dựng

### 6.1. Rule: truy cập ngoài đường quản trị được phép

**Điều kiện:** tài nguyên thuộc phạm vi bắt buộc broker; một hoạt động quản trị được quan sát trên đường đã được xác minh là không được phép.

**Bằng chứng nên có:** policy hiệu lực, sự kiện đích hoặc mạng, quan hệ nguồn/đích, loại truy cập, kết quả và thông tin ngoại lệ.

**Phân loại:** kết nối bị chặn, xác thực thất bại, hoặc đăng nhập đặc quyền thành công. Ba trường hợp này không được ghi cùng một kết luận về tác động.

**Điều chỉnh:** broker theo vùng, NAT đã biết, kết nối qua gateway, IPv6, giao thức quản trị thay thế và cơ chế quản trị cloud đã được phê duyệt. Danh sách đường cho phép phải dựa trên inventory có owner và lịch sử thay đổi, không chỉ một tập IP nhập tay không có hạn dùng.

### 6.2. Rule: hoạt động không khớp quyền cấp bắt buộc

**Điều kiện:** thao tác đặc quyền cần một grant cụ thể nhưng grant đó không hợp lệ cho chủ thể, tài nguyên, tài khoản, loại hành động hoặc thời gian tương ứng.

**Bằng chứng nên có:** audit thao tác từ đích, bản grant và lịch sử thu hồi, quan hệ danh tính và policy áp dụng. Với chuỗi assume-role hoặc ủy quyền, phải giữ cả chuỗi thay vì chỉ so tên vai trò cuối.

**Điều chỉnh:** thời hạn mở phiên khác thời hạn duy trì phiên; grant theo nhóm tài nguyên phải được đánh giá theo membership có hiệu lực tại thời điểm hoạt động. Inventory hôm nay không nhất thiết phản ánh phạm vi được cấp hôm qua.

### 6.3. Rule: thay đổi kiểm soát rồi xuất hiện hoạt động ngoài phạm vi

**Điều kiện:** thay đổi nhạy cảm đối với audit, agent, gateway hoặc cơ chế nâng quyền, tiếp theo là hoạt động đặc quyền liên quan trong một cửa sổ phù hợp.

**Bằng chứng nên có:** actor của thay đổi, đối tượng bị đổi, trước/sau nếu có, ticket bảo trì, sự kiện sử dụng quyền và độ khỏe telemetry.

**Điều chỉnh:** cửa sổ thời gian và quan hệ phải có ý nghĩa. Hai sự kiện gần nhau nhưng trên tài nguyên, người dùng và hạ tầng không liên quan không nên bị ghép chỉ vì cùng timestamp gần nhau.

### 6.4. Rule: tài khoản hoặc credential quản trị mới ngoài quản lý

**Điều kiện:** tài khoản, key hoặc credential mới có quyền đặc biệt được tạo ngoài luồng được phê duyệt; sau đó có hành vi sử dụng trên tài nguyên thuộc phạm vi PAM.

**Bằng chứng nên có:** sự kiện tạo/sửa quyền, trạng thái onboarding tại thời điểm sử dụng, owner và audit lần sử dụng đầu tiên.

**Điều chỉnh:** có thể tồn tại khoảng thời gian đồng bộ hợp lệ giữa provisioning và onboarding. Khoảng thời gian đó phải được chính sách quy định, theo dõi và giới hạn; không được coi mọi tài khoản mới là ngoại lệ vô thời hạn.

### 6.5. Rule: break-glass không đáp ứng điều kiện

**Điều kiện:** dùng tài khoản hoặc đường khẩn cấp nhưng không có ngoại lệ khớp, sử dụng ngoài thời hạn/phạm vi, thiếu người chịu trách nhiệm hoặc tiếp tục dùng sau khi tình huống khẩn cấp kết thúc.

Break-glass được thiết kế để duy trì khả năng ứng cứu khi một phần hệ thống bình thường không hoạt động. Vì vậy, việc thiếu một bước phê duyệt trực tuyến có thể phù hợp chính sách khẩn cấp. Rule phải kiểm tra quy trình dành riêng cho break-glass, bao gồm bằng chứng tại chỗ và yêu cầu đối soát sau sự kiện nếu hệ thống trung tâm đang gián đoạn.

Không suppress toàn bộ mọi hoạt động của tài khoản khẩn cấp. Một ngoại lệ hợp lệ vẫn cần cảnh báo theo dõi, owner và kiểm tra đóng ngoại lệ.

## 7. Tình huống tương quan từ đầu đến cuối

Giả sử tài nguyên `asset-db-prod-07` yêu cầu phiên tương tác qua broker, trừ ngoại lệ khẩn cấp được cấp cho đúng tài khoản và tài nguyên. Những bản ghi sau là dữ liệu giả lập phục vụ học tập.

| Thời điểm sự kiện | Sự kiện | Ý nghĩa ban đầu |
|---|---|---|
| 02:00:00 | Cấp grant `grant-402` cho người A, tài nguyên X | Chỉ cho phép đúng phạm vi của grant |
| 02:03:10 | Broker mở phiên `pam-610` tới tài nguyên X | Chưa chứng minh hoạt động trên tài nguyên khác |
| 02:12:05 | Đích `db-prod-07` ghi đăng nhập quản trị thành công | Có hoạt động cần đối soát |
| 02:12:06 | Gateway xác nhận kết nối đi từ vùng workstation trực tiếp | Bằng chứng về đường truy cập |
| 02:12:12 | Collector của đích và broker đều khỏe | Hỗ trợ đánh giá chất lượng dữ liệu |
| 02:14:30 | Hết cửa sổ chờ theo cấu hình ví dụ, chưa có binding hợp lệ | Có thể hoàn tất lần đối soát hiện tại |

Phân tích đúng không phải “A có một phiên PAM, vậy mọi truy cập của A đều được phép”. Grant và phiên đang có chỉ tới tài nguyên X. Cần xác minh `db-prod-07` có nằm trong phạm vi đó hay không, tài khoản đích nào được dùng và có quan hệ phiên tin cậy nào nối tới hoạt động 02:12:05 hay không.

Nếu policy tại 02:12:05 bắt buộc broker và gateway chứng minh đường trực tiếp bị cấm, có thể phát cảnh báo về vi phạm đường truy cập ngay khi bằng chứng đủ. Cửa sổ chờ vẫn hữu ích cho đối soát bổ sung, nhưng không bắt buộc trì hoãn xử lý một kết nối đang gây rủi ro đã được xác nhận bằng bằng chứng dương.

Nếu không có dữ liệu gateway và log broker đang bị trễ bất thường, kết luận phải thận trọng hơn: đây là hoạt động đặc quyền chưa đối soát được trong điều kiện thiếu telemetry. Đội vận hành cần xử lý cả hoạt động tại đích và khoảng trống dữ liệu, thay vì đóng cảnh báo như một false positive hoặc khẳng định đã có bypass.

Các thời lượng trong tình huống chỉ để minh họa. Độ trễ chờ và mức ưu tiên thực tế cần dựa trên nguồn log, yêu cầu phản ứng và thiết kế hệ thống của tổ chức.

## 8. Ưu tiên cảnh báo và playbook điều tra

### 8.1. Tách mức độ tin cậy khỏi mức độ tác động

**Độ tin cậy** phản ánh bằng chứng có đủ để khẳng định điều gì. **Tác động tiềm tàng** phản ánh giá trị của tài nguyên và quyền bị sử dụng. Một cảnh báo chưa xác định được actor vẫn có thể cần xử lý gấp nếu là phiên quản trị thành công vào hệ thống quan trọng.

Có thể ưu tiên theo các yếu tố:

- Hoạt động bị chặn hay đã thành công; có thao tác nhạy cảm tiếp theo hay không.
- Mức quan trọng và độ nhạy cảm của tài nguyên.
- Quyền quản trị cục bộ, quyền toàn miền, quyền cloud hay quyền trên kho credential.
- Bằng chứng đường bị cấm, grant bị thu hồi hoặc kiểm soát bị can thiệp.
- Phạm vi lan rộng tới nhiều tài nguyên hoặc nhiều tài khoản.
- Chất lượng ánh xạ danh tính và sức khỏe các nguồn dữ liệu.

Không hạ mức nghiêm trọng chỉ vì actor được ánh xạ thành một tài khoản quản trị quen thuộc. Đó có thể là tài khoản đang bị sử dụng ngoài dự kiến.

### 8.2. Trình tự triage

1. **Xác minh điều kiện rule:** policy nào áp dụng tại thời điểm sự kiện, tài nguyên có nằm trong phạm vi, và control nào bắt buộc?
2. **Xác minh sự kiện gốc:** nguồn có thẩm quyền, action, outcome, thời điểm và định danh đích có khớp không?
3. **Xác định actor:** nối danh tính gốc, tài khoản đích, grant, phiên và kết nối; ghi rõ phần chưa xác định.
4. **Đối soát luồng hợp lệ:** phiên broker, quyền JIT, credential checkout, workload policy, change và break-glass.
5. **Kiểm tra telemetry:** log tới muộn, collector gián đoạn, đổi parser, NAT hoặc inventory chưa cập nhật.
6. **Đánh giá hoạt động liên quan:** nâng quyền, thay đổi tài khoản, sửa audit, truy cập bí mật và thao tác trên tài nguyên khác.
7. **Chọn phản ứng theo bằng chứng và playbook:** hạn chế đường truy cập, thu hồi quyền hoặc chấm dứt phiên khi phù hợp; bảo toàn bằng chứng cần thiết.
8. **Ghi kết luận và hành động sửa:** vi phạm, nỗ lực bị chặn, ngoại lệ hợp lệ, lỗi cấu hình hoặc thiếu khả năng quan sát.

Truy vấn điều tra cần giữ được mối quan hệ nhân quả có chứng cứ. Một IP nguồn dùng chung không đủ để gán mọi hoạt động trên IP đó cho một cá nhân. Nếu chưa quy được actor, báo cáo bằng tài khoản và phiên đã xác minh thay vì điền tên suy đoán.

### 8.3. Phản ứng có phạm vi

Với phiên trái chính sách đang hoạt động, có thể áp dụng playbook đóng phiên cụ thể, thu hồi grant liên quan hoặc chặn đường truy cập cụ thể. Với credential nghi bị lộ, cần xem xét các phiên và token còn hiệu lực, dependency của service account và quy trình luân chuyển tương ứng.

Luân chuyển mật khẩu không bảo đảm mọi phiên đã xác thực trước đó sẽ dừng. Thu hồi grant cũng có thể cần hành động riêng để kết thúc phiên hoặc thu hồi token. Detection nên theo dõi bằng chứng sau phản ứng: phiên đã đóng, đường bị chặn, quyền đã thu hồi và hoạt động có tiếp diễn hay không.

Đối với break-glass, giữ được khả năng khôi phục hệ thống là một yêu cầu vận hành. Phản ứng phải theo playbook khẩn cấp đã thống nhất, có người chịu trách nhiệm và bằng chứng, tránh tự động vô hiệu hóa mọi phương thức quản trị chỉ dựa trên một cảnh báo thiếu log.

## 9. Nội dung tối thiểu của một cảnh báo hữu ích

Một cảnh báo nên cho người xử lý biết điều gì đã được chứng minh và điều gì còn chưa rõ. Ví dụ:

```yaml
alert_type: suspected_pam_path_violation
activity_result: privileged_login_success
asset_id: asset-db-prod-07
target_account_id: local-admin-17
principal_resolution: unresolved
policy_version: pam-path-prod-v12
required_control: brokered_interactive_access
observed_path: verified_direct_connection
exception_check: no_matching_exception_at_event_time
pam_binding: not_found_after_reconciliation_window
source_health: healthy_with_known_coverage
confidence_basis:
  - authoritative_target_login_event
  - verified_gateway_connection
  - effective_path_policy
evidence_refs:
  - target-evt-7841
  - gateway-evt-5820
open_questions:
  - resolve_human_or_workload_origin
  - determine_post_login_activity
```

Không dùng mẫu này để suy ra toàn bộ nguồn đã hoàn hảo: `healthy_with_known_coverage` chỉ có nghĩa nguồn vượt các kiểm tra đã định nghĩa trong phạm vi được quan sát. Những phần không có telemetry phải được thể hiện trong evidence hoặc câu hỏi điều tra.

Các trường như mật khẩu, secret, nội dung private key hoặc toàn bộ bearer token không thuộc payload cảnh báo. Dẫn chiếu tới bằng chứng được kiểm soát truy cập thay vì sao chép dữ liệu nhạy cảm không cần thiết.

Với một ứng viên chỉ thiếu binding, đổi loại cảnh báo thành `unmatched_privileged_activity`, ghi đường truy cập là `unknown` nếu chưa xác minh, và nêu rõ tình trạng nguồn. Không tái sử dụng nhãn `verified_direct_connection` khi chưa có bằng chứng cho đường trực tiếp.

## 10. False positive, false negative và cách điều chỉnh

| Tình huống | Nguy cơ sai | Cách xử lý |
|---|---|---|
| Broker mới chưa có trong inventory | Cảnh báo đường truy cập hợp lệ | Cập nhật cấu hình có owner, thời điểm hiệu lực và kiểm tra dữ liệu |
| Log phiên PAM tới muộn | Coi thiếu binding là bypass | Đối soát lại theo event time, có cửa sổ chờ và lịch sử cập nhật |
| NAT làm nhiều nguồn trùng IP | Quy nhầm actor hoặc đường truy cập | Dùng connection ID, flow và ánh xạ gateway có thẩm quyền |
| Service account không tương tác | Ép luồng máy với máy vào rule của con người | Áp policy theo access mode và loại principal |
| Break-glass hợp lệ | Cảnh báo vi phạm không đúng điều kiện | Khớp ngoại lệ chính xác và tiếp tục theo dõi hậu kiểm |
| Phiên mở hợp lệ kéo dài qua hạn JIT | Nhầm thời hạn mở phiên với duy trì phiên | Tách chính sách admission và session lifetime |
| Kẻ sử dụng đi qua một host được tin cậy | Bỏ sót vì allowlist IP | Yêu cầu binding phiên, actor và grant; không chỉ tin nguồn mạng |
| Tài khoản quản trị mới chưa onboard | Không thấy trong danh sách tài khoản PAM | Kết hợp inventory quyền thực tế và audit thay đổi đặc quyền |
| Collector tại đích bị mất log | Bỏ sót hoạt động hoặc hiểu sai sự vắng mặt | Giám sát sức khỏe nguồn và đối chiếu control plane/mạng |
| Giao thức hoặc đường quản trị khác | Chỉ giám sát SSH/RDP nên bỏ sót | Kiểm kê bề mặt quản trị, API và cơ chế quản trị từ xa được dùng |

Điều chỉnh tốt làm tăng độ chính xác nhưng vẫn giữ phạm vi phát hiện. Không loại trừ rộng một nhóm quản trị viên, toàn bộ subnet nội bộ hoặc mọi tài khoản emergency để giảm số lượng cảnh báo. Ngoại lệ cần có điều kiện khớp, owner, lý do, thời hạn và cơ chế kiểm tra lại.

Một ngoại lệ chỉ để giảm nhiễu kỹ thuật không nên âm thầm biến thành quyền truy cập mới. Nếu thực tế vận hành khác policy, cần sửa chính sách hoặc đường truy cập theo quy trình quản trị thay vì chỉ sửa rule để bỏ qua chênh lệch.

## 11. Kiểm thử detection bằng dữ liệu và môi trường thử nghiệm

Mục đích kiểm thử là xác nhận rule phân biệt đúng các tình huống, giữ đủ bằng chứng và hoạt động được khi dữ liệu không tới theo thứ tự. Có thể bắt đầu bằng replay sự kiện giả lập, sau đó kiểm chứng bằng các phiên quản trị kiểm soát được trong môi trường thử nghiệm phù hợp.

| Ca kiểm thử | Đầu vào | Kết quả mong đợi |
|---|---|---|
| Phiên bình thường | Đích, grant và broker khớp đầy đủ | Đối soát thành công |
| Thử kết nối ngoài đường | Mạng chặn kết nối quản trị | Cảnh báo nỗ lực bị chặn; không ghi thành công |
| Đăng nhập trực tiếp thành công | Policy bắt buộc broker, bằng chứng đường trực tiếp | Cảnh báo vi phạm đường với bằng chứng gốc |
| Sai phạm vi grant | Cùng người nhưng khác tài nguyên được cấp | Không dùng grant không liên quan để cho qua |
| Broker log tới muộn | Đích tới trước, broker tới trong ngân sách trễ | Pending rồi đối soát lại, tránh cảnh báo lặp |
| Mất log broker | Nguồn không khỏe, thiếu binding | Telemetry gap hoặc cảnh báo có giới hạn kết luận rõ ràng |
| Ngoại lệ còn hiệu lực | Khớp actor, tài khoản, đích, mode và thời gian | Theo dõi ngoại lệ; không gán vi phạm của rule này |
| Ngoại lệ hết hạn | Hoạt động xảy ra sau thời điểm kết thúc | Không suppress vì ngoại lệ cũ |
| API workload hợp lệ | Policy máy với máy không yêu cầu proxy tương tác | Không ép thiếu session proxy thành bypass |
| Phiên dài hợp lệ | Mở trong hạn, duy trì theo policy riêng | Đánh giá theo đúng session lifetime |
| ID phiên giả trong metadata client | Chuỗi ID tồn tại nhưng không có binding đáng tin | Không coi là phiên hợp lệ |
| Thay đổi kiểm soát rồi truy cập | Có sự kiện can thiệp và hoạt động liên quan | Tương quan đúng tài nguyên/actor và nâng ưu tiên |

Cũng cần thử ranh giới thời gian: ngay trước khi grant bắt đầu, đúng thời điểm bắt đầu, ngay trước khi hết hạn và đúng thời điểm hết hạn. Thử dữ liệu trùng, sự kiện đảo thứ tự, broker failover và thay đổi IP để phát hiện giả định ẩn trong pipeline.

Tiêu chí đạt không chỉ là “rule đã nổ”. Cần xác nhận payload nêu đúng outcome, evidence có thể truy hồi, quan hệ danh tính không bị đoán, ngoại lệ được giới hạn và phản ứng không tác động nhầm phiên hợp lệ.

## 12. Chỉ số vận hành và cải tiến liên tục

Theo dõi cả khả năng phát hiện và chất lượng dữ liệu:

- **Mức phủ đối soát:** tỷ lệ hoạt động đặc quyền trong phạm vi có đủ nguồn và quan hệ để đánh giá. Mẫu số phải nêu rõ tập hoạt động quan sát được; không coi đây là tỷ lệ trên mọi hoạt động thực tế chưa nhìn thấy.
- **Mức phủ tài nguyên:** tài nguyên thuộc phạm vi PAM có audit tại đích, inventory chính sách và nguồn PAM hoạt động đầy đủ.
- **Độ trễ phát hiện:** từ event time tới lúc phát cảnh báo đủ điều kiện, tách phần chờ tương quan với phần chậm ingest.
- **Tỷ lệ cảnh báo chưa đối soát:** số hoạt động thiếu binding sau cửa sổ chờ, phân theo nguồn và nguyên nhân.
- **Kết quả điều tra:** vi phạm xác nhận, nỗ lực bị chặn, ngoại lệ, cấu hình sai và thiếu telemetry.
- **Chất lượng ngoại lệ:** số ngoại lệ quá hạn, thiếu owner hoặc được sử dụng vượt phạm vi.
- **Hiệu quả phản ứng:** thời gian xác minh phiên, thời gian hạn chế truy cập và bằng chứng hoạt động đã dừng sau xử lý.

Không tối ưu chỉ bằng số cảnh báo giảm. Giảm cảnh báo vì bỏ thu thập một nguồn hoặc suppress cả nhóm tài khoản làm mất khả năng phát hiện. Sau mỗi incident hoặc thay đổi kiến trúc, cập nhật policy mapping, kiểm tra các đường quản trị còn tồn tại và bổ sung ca kiểm thử tương ứng.

## 13. Bài tập tự đánh giá

### Tình huống A: một phiên PAM không chứng minh mọi hoạt động

Một quản trị viên có phiên broker tới máy A. Cùng thời điểm, máy B ghi nhận đăng nhập bằng tài khoản quản trị chia sẻ, nguồn là một gateway chung. Có thể kết luận người đó bypass PAM trên máy B không?

Chưa thể quy trách nhiệm chỉ từ dữ kiện này. Cần kiểm tra policy của B, đường kết nối thực tế, grant và binding tới phiên tại B. Tài khoản chia sẻ và IP gateway chung không đủ ánh xạ sang cá nhân. Có thể mở điều tra về hoạt động đặc quyền chưa đối soát trên B, đồng thời ghi rõ actor chưa xác định.

### Tình huống B: có checkout nhưng thiếu broker

Người dùng checkout đúng credential, sau đó đăng nhập trực tiếp vào máy thuộc phạm vi bắt buộc broker. Checkout có làm hoạt động hợp lệ không?

Không tự động. Checkout chứng minh một phần quan hệ cấp phát credential; điều kiện đường truy cập vẫn phải được đáp ứng. Nếu đường trực tiếp bị cấm và có bằng chứng xác minh, hoạt động có thể vi phạm dù credential được cấp hợp lệ.

### Tình huống C: mất nguồn log đúng lúc có cảnh báo

Đích ghi nhận quyền quản trị được dùng, nhưng broker không có sự kiện tương ứng và collector đang mất kết nối. Nên kết luận thế nào?

Có hoạt động cần điều tra và khoảng trống telemetry, nhưng sự vắng mặt của sự kiện broker chưa chứng minh bypass. Cần đối chiếu dữ liệu tại đích, mạng, grant, ngoại lệ và hoạt động liên quan; xử lý rủi ro theo bằng chứng hiện có và đánh giá lại khi nguồn phục hồi.

### Tình huống D: quyền hết hạn nhưng phiên còn hoạt động

Grant hết hạn lúc 10:00; phiên được mở lúc 09:55 vẫn có thao tác lúc 10:02. Điều này có luôn là bypass không?

Không. Cần đọc chính sách thời hạn phiên. Nếu yêu cầu chấm dứt mọi quyền sử dụng lúc 10:00 mà hoạt động vẫn thành công, đó là vi phạm cần điều tra. Nếu grant chỉ giới hạn thời điểm mở phiên và phiên được phép tồn tại theo lease riêng, hoạt động 10:02 có thể hợp lệ. Rule phải phản ánh đúng mô hình đã phê duyệt.

## 14. Những điểm cần ghi nhớ

PAM bypass attempt được phát hiện bằng cách đối chiếu **quyền, danh tính, đường truy cập, thời gian và tài nguyên** với chính sách hiệu lực. Thiếu log PAM là một tín hiệu để đối soát, không phải kết luận tự thân về ý đồ hoặc truy cập thành công.

Một detection có giá trị cần chỉ rõ kiểm soát bắt buộc nào bị nghi đi vòng, nguồn nào chứng minh hoạt động, outcome thực tế là gì và phần bằng chứng nào còn thiếu. Tách nỗ lực bị chặn, truy cập trái chính sách thành công, ngoại lệ hợp lệ và lỗi telemetry giúp đội vận hành chọn phản ứng đúng phạm vi, đồng thời tìm được khoảng trống phải sửa trong kiến trúc PAM.
