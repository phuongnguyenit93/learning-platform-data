# Unauthorized attempt count — Đếm lần truy cập đặc quyền không được phép

Trong quản lý truy cập đặc quyền (Privileged Access Management, PAM), một yêu cầu vào máy chủ, lấy credential từ vault, nâng quyền hoặc thực thi tác vụ quản trị có thể bị từ chối vì không đáp ứng chính sách. **Unauthorized attempt count** đo số lần thử như vậy trong một phạm vi và khoảng thời gian đã xác định.

Một con số như “1.200 lần không được phép trong ngày” chỉ có ích khi người đọc biết hệ thống đã đếm gì: 1.200 bản ghi log, 1.200 yêu cầu thực sự, hay 1.200 phiên có ít nhất một lệnh bị chặn? Ba cách đếm có thể cho kết quả rất khác nhau. Bài học này xây dựng một định nghĩa dùng được trong vận hành PAM, cách xử lý log trùng, ví dụ tính toán và cách sử dụng số liệu để điều tra hoặc cải thiện kiểm soát truy cập.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Xác định đơn vị đếm, cửa sổ thời gian và phạm vi của unauthorized attempt count.
- Phân biệt từ chối xác thực, từ chối cấp quyền, yêu cầu bổ sung xác minh và lỗi kỹ thuật.
- Thiết kế luồng dữ liệu từ điểm thực thi chính sách đến bảng chỉ số có thể truy nguyên.
- Khử trùng sự kiện mà vẫn giữ lại những lần thử độc lập, kể cả retry liên tục.
- Đọc số đếm cùng tỷ lệ, độ phủ telemetry và bối cảnh JIT/JEA, vault, tài khoản dịch vụ, phiên quản trị.
- Biến biến động chỉ số thành một hành động có người chịu trách nhiệm và bằng chứng kiểm chứng.

## 2. Chốt định nghĩa trước khi xây dashboard

### 2.1. Định nghĩa vận hành của bài học

Trong bài này, **một unauthorized attempt** là một lần thử truy cập đặc quyền riêng biệt, thuộc phạm vi báo cáo, đã nhận quyết định từ chối thực sự tại điểm thực thi chính sách cấp quyền.

Định nghĩa này có bốn điều kiện:

1. Có một lần thử hoặc yêu cầu có thể phân biệt với lần thử khác.
2. Yêu cầu thuộc loại truy cập đặc quyền đang đo.
3. Có bằng chứng quyết định cấp quyền là từ chối, không suy ra từ việc thiếu log thành công.
4. Chính sách ở chế độ thực thi, không chỉ mô phỏng hoặc ghi nhận “sẽ từ chối”.

Tên chỉ số trên dashboard nên làm rõ phạm vi, chẳng hạn **“Số lần thử bị PAM từ chối cấp quyền — production”**. Nếu tổ chức dùng “unauthorized attempts” để bao gồm cả đăng nhập thất bại, hãy công bố định nghĩa rộng đó và tách các thành phần. Không trộn hai nghĩa trong cùng một chuỗi thời gian mà không đổi phiên bản định nghĩa.

Một lần bị chặn chỉ chứng minh rằng yêu cầu cụ thể không được chính sách cho phép tại thời điểm đánh giá. Nó chưa chứng minh người thực hiện là kẻ tấn công, cũng chưa chứng minh chính sách được cấu hình đúng.

### 2.2. Đơn vị đếm phải có ranh giới rõ ràng

| Đơn vị | Ví dụ | Câu hỏi mà số liệu trả lời |
|---|---|---|
| Lần thử cấp quyền | Một yêu cầu mở phiên SSH bị từ chối | Có bao nhiêu lần yêu cầu đã nhận quyết định từ chối? |
| Bản ghi quan sát | Gateway và connector cùng ghi một lần từ chối | Hệ thống log đã thu được bao nhiêu bản ghi? |
| Phiên | Một phiên có ba lệnh bị chặn | Có bao nhiêu phiên chứa ít nhất một hành vi bị chặn? |
| Chủ thể | Một service account bị chặn 500 lần | Có bao nhiêu chủ thể khác nhau gặp từ chối? |
| Tài nguyên | Mười máy chủ bị truy cập ngoài quyền | Có bao nhiêu tài nguyên khác nhau được nhắm đến? |
| Cụm hành vi | Một chiến dịch dò nhiều tài nguyên | Có bao nhiêu nhóm hoạt động liên quan cần điều tra? |

Các đơn vị bổ sung giúp giải thích số đếm nhưng không thay thế cho nhau. Nếu một tài khoản thử 500 yêu cầu độc lập, unauthorized attempt count là 500; unique subject count có thể chỉ là 1.

### 2.3. Chọn mức đo cho từng cơ chế PAM

| Cơ chế kiểm soát | Lần thử được tính | Lưu ý về ranh giới |
|---|---|---|
| Mở phiên quản trị | Yêu cầu kết nối bị từ chối vì thiếu quyền tới target | Một phiên đã mở không đồng nghĩa mọi hành động sau đó đều hợp lệ |
| Truy cập vault | Yêu cầu đọc hoặc checkout secret bị từ chối | Không ghi giá trị secret vào dữ liệu chỉ số |
| JIT | Yêu cầu kích hoạt quyền bị policy engine từ chối | Yêu cầu đang chờ duyệt chưa phải quyết định từ chối cuối cùng |
| JEA hoặc giới hạn lệnh | Một yêu cầu thực thi lệnh ngoài tập cho phép bị chặn | Phân biệt lần mở phiên với lần thực thi lệnh trong phiên |
| Nâng quyền | Yêu cầu nâng quyền quản trị bị từ chối | Cần biết điểm thực thi và kết quả thực tế |
| Tài khoản dịch vụ | Một lời gọi có đặc quyền bị từ chối theo chính sách | Retry tự động có thể tạo nhiều lần thử hợp lệ về đơn vị đếm |

Không cộng vô điều kiện số từ chối mở phiên, số lệnh bị chặn và số lần checkout secret rồi gọi đó là “số lần đăng nhập thất bại”. Nếu cần tổng chung, đặt tên “tổng yêu cầu đặc quyền bị từ chối”, ghi rõ các loại yêu cầu được đưa vào và cho phép phân rã theo loại.

## 3. Từ chối cấp quyền khác với thất bại xác thực

Một luồng truy cập đặc quyền thường có nhiều bước: nhận diện chủ thể, xác thực, đánh giá chính sách, duyệt hoặc xác minh bổ sung, rồi thực thi. Kết quả ở mỗi bước có ý nghĩa riêng.

| Quan sát | Đưa vào số đếm của bài này? | Lý do |
|---|---|---|
| Mật khẩu sai trước khi xác thực thành công | Không | Đây là authentication failure; nên có chỉ số riêng |
| Đã xác thực nhưng thiếu entitlement vào máy chủ | Có | Quyết định cấp quyền đã từ chối và được thực thi |
| Chưa có grant JIT tại thời điểm yêu cầu, hệ thống từ chối | Có | Chưa đáp ứng điều kiện cấp quyền hiện hành |
| Yêu cầu JIT đang chờ người phê duyệt | Chưa | Trạng thái trung gian, chưa có quyết định cuối cùng |
| Hệ thống yêu cầu MFA bổ sung | Chưa | Challenge chưa tự nó là từ chối cuối cùng |
| Challenge thất bại, sau đó hệ thống ghi quyết định deny cuối cùng | Tùy hợp đồng phân loại | Chỉ tính nếu đây là quyết định cấp quyền terminal thuộc phạm vi đã công bố |
| Proxy timeout và không xác định được quyết định | Không đưa vào deny mặc định | Ghi nhận lỗi hoặc unknown; thiếu bằng chứng về quyết định |
| Policy ở audit-only ghi “would deny”, tác vụ vẫn chạy | Không | Đây là vi phạm mô phỏng, cần chỉ số riêng |
| JEA chặn một lệnh trong phiên đã được mở hợp lệ | Có ở mức lệnh | Quyền mở phiên và quyền thực thi lệnh là hai quyết định khác nhau |
| Không có log kết nối thành công | Không đủ dữ kiện | Không thể suy ra một lần từ chối từ sự vắng mặt của log |

Lỗi kỹ thuật có thể khiến hệ thống fail closed và chặn truy cập, nhưng vẫn nên tách **technical block** khỏi **policy deny** nếu log không thể hiện quyết định chính sách đáng tin cậy. Nếu tổ chức muốn báo cáo tổng mọi yêu cầu bị chặn, hãy công bố chỉ số tổng đó và các thành phần bên dưới.

Tương tự, việc người dùng tự hủy một yêu cầu không phải từ chối cấp quyền. Một yêu cầu đang chờ duyệt hết hạn cũng không nên tự động ánh xạ thành “bị tấn công”; cách phân loại phải phản ánh ngữ nghĩa của hệ thống và hợp đồng chỉ số.

## 4. Công thức và mẫu số

### 4.1. Số đếm cơ bản

Với cửa sổ nửa mở `W = [t0, t1)`, gọi `A(W)` là tập các lần thử riêng biệt có thời điểm quyết định trong cửa sổ. Gọi `eligible(a)` là điều kiện thuộc phạm vi báo cáo.

```text
UnauthorizedAttemptCount(W)
  = số phần tử a trong A(W) thỏa mãn:
      eligible(a) = true
      event_kind = AUTHORIZATION
      decision = DENY
      is_terminal = true
      control_mode = ENFORCE
      record_state = VALID
```

Cửa sổ `[t0, t1)` lấy sự kiện tại `t0`, loại sự kiện tại `t1`. Hai cửa sổ kế tiếp nhau vì vậy không đếm đôi một sự kiện đúng ranh giới.

`record_state = VALID` ở đây là nhãn chất lượng dữ liệu: bản ghi có đủ trường bắt buộc, không có xung đột chưa xử lý và đã qua quy trình khử trùng. Nó không có nghĩa hành động của chủ thể là hợp lệ.

### 4.2. Tỷ lệ từ chối

Để so sánh các thời kỳ có khối lượng truy cập khác nhau, dùng thêm:

```text
DenyRate(W)
  = UnauthorizedAttemptCount(W)
    / TerminalAuthorizationAttemptCount(W)
    × 100%
```

Trong hợp đồng của bài học, mẫu số là số lần thử cấp quyền terminal, ở chế độ thực thi, thuộc cùng phạm vi, có kết quả đáng tin cậy `ALLOW` hoặc `DENY`. `ERROR`, `UNKNOWN`, sự kiện xác thực và quyết định mô phỏng không nằm trong mẫu số này; chúng được báo cáo riêng.

Nếu mẫu số bằng 0, kết quả tỷ lệ là **N/A**, không mặc định là 0%. “Không có yêu cầu đã phân loại được” khác với “có yêu cầu và không có lần nào bị từ chối”.

Khi tính tỷ lệ toàn module, cộng tử số và mẫu số của các nhóm tương thích rồi chia. Không lấy trung bình đơn giản tỷ lệ của một nhóm có 2 yêu cầu với nhóm có 20.000 yêu cầu.

### 4.3. Chỉ số bổ sung nên đi cùng

- **Unique denied subjects:** số chủ thể riêng biệt có ít nhất một lần bị từ chối.
- **Unique targeted resources:** số tài nguyên bị nhắm đến bởi các lần thử bị từ chối.
- **Deny count theo reason:** thiếu entitlement, grant hết hạn, ngoài giờ, ngoài tập lệnh cho phép hoặc lý do đã chuẩn hóa khác.
- **Unknown/error count:** số yêu cầu hoặc quan sát chưa phân loại được và số lỗi trong luồng quyết định.
- **Telemetry freshness và coverage:** dữ liệu có mới, đầy đủ trong phạm vi dự kiến hay không.

Một dashboard hữu ích không chỉ nêu số đếm mà còn cho biết **dữ liệu nào đang vắng mặt**.

## 5. Hợp đồng chỉ số tối thiểu

Trước khi công bố chỉ số, chủ sở hữu PAM và nhóm dữ liệu nên thống nhất một bản mô tả ngắn. Ví dụ dưới đây là hợp đồng minh họa, không phải cấu hình bắt buộc của một sản phẩm.

| Thuộc tính | Giá trị minh họa |
|---|---|
| Tên | PAM enforced authorization deny count |
| Phiên bản ngữ nghĩa | `authz-attempt-v1` |
| Đơn vị | Một lần thử cấp quyền terminal riêng biệt |
| Phạm vi | Các điểm thực thi PAM đã đăng ký, môi trường production |
| Loại yêu cầu | Session open, secret read/checkout, JIT activation, command execution |
| Điều kiện đưa vào | Deny terminal, enforce, dữ liệu valid |
| Điều kiện loại ra | Authentication-only, dry-run, test, pending, challenge trung gian, unknown |
| Thời gian | Thời điểm quyết định; lưu UTC; hiển thị múi giờ công bố |
| Khử trùng | Event ID theo nguồn, sau đó attempt ID theo hợp đồng tương quan |
| Dữ liệu đến muộn | Cửa sổ provisional trước khi kết thúc thời gian chờ đã quy định |
| Chủ sở hữu | Nhóm vận hành PAM; nhóm dữ liệu chịu trách nhiệm pipeline |
| Phản hồi | Drill-down tới bằng chứng và ticket xử lý theo mức độ |

Nếu thay đổi từ đếm log sang đếm attempt, từ một gateway sang toàn hạ tầng, hoặc bổ sung chặn lệnh vào phạm vi, cần đánh dấu thay đổi trên biểu đồ. Một bước nhảy do mở rộng phạm vi không được trình bày như một đợt tấn công mới.

## 6. Mô hình sự kiện và khả năng truy nguyên

### 6.1. Các trường cần thiết

| Trường | Mục đích |
|---|---|
| `source_system`, `source_event_id` | Nhận diện một quan sát trong phạm vi nguồn, chống thu lại cùng log |
| `attempt_uid` | Nhận diện lần thử cấp quyền sau bước tương quan |
| `parent_request_id` | Liên kết các bước hoặc quyết định con khi có hợp đồng rõ ràng |
| `event_time`, `ingested_at` | Phân biệt thời điểm quyết định và thời điểm tiếp nhận |
| `environment`, `enforcement_point` | Xác định phạm vi và điểm thực thi |
| `subject_ref`, `subject_type` | Nhận diện tham chiếu tới người dùng, workload hoặc tài khoản dịch vụ |
| `resource_ref`, `resource_tier` | Xác định target và mức nhạy cảm |
| `action_class` | Phân loại mở phiên, lấy secret, kích hoạt quyền hoặc thực thi lệnh |
| `event_kind`, `decision`, `is_terminal` | Xác định loại sự kiện và quyết định cuối cùng |
| `control_mode`, `enforcement_result` | Phân biệt thực thi với mô phỏng, ghi nhận kết quả tại điểm chặn |
| `reason_code`, `policy_version` | Giải thích vì sao bị từ chối và chính sách nào có hiệu lực |
| `record_state`, `semantic_version` | Kiểm soát chất lượng và phiên bản định nghĩa |

Không phải sản phẩm nào cũng cung cấp đủ các trường này. Khi thiếu, ghi rõ giới hạn. Không tự sinh một ID tương quan có vẻ chính xác rồi công bố là đã khử trùng hoàn toàn.

### 6.2. Sự kiện minh họa

```json
{
  "source_system": "pam-gateway-prod-a",
  "source_event_id": "evt-8f4c",
  "attempt_uid": "authz-req-2b17",
  "event_time": "2026-05-12T10:03:20Z",
  "ingested_at": "2026-05-12T10:03:23Z",
  "environment": "production",
  "enforcement_point": "session-gateway",
  "subject_ref": "subject-7c2e",
  "subject_type": "HUMAN",
  "resource_ref": "resource-db-admin-04",
  "resource_tier": "CRITICAL",
  "action_class": "SESSION_OPEN",
  "event_kind": "AUTHORIZATION",
  "decision": "DENY",
  "is_terminal": true,
  "control_mode": "ENFORCE",
  "enforcement_result": "BLOCKED",
  "reason_code": "ENTITLEMENT_MISSING",
  "policy_version": "policy-27",
  "record_state": "VALID",
  "semantic_version": "authz-attempt-v1"
}
```

Các định danh trong ví dụ là giả lập. Trong dữ liệu thật, không lưu password, token, private key, nội dung secret hay toàn bộ dòng lệnh có thể chứa credential. Dùng tham chiếu tới bằng chứng được kiểm soát quyền truy cập khi cần điều tra chi tiết.

Nếu giả danh hóa chủ thể, cơ chế phải cho phép tương quan trong phạm vi báo cáo cần thiết. Một keyed HMAC có quản lý khóa phù hợp thường giải quyết bài toán khác với việc băm không khóa một tên người dùng dễ đoán. Việc đổi khóa hoặc đổi quy tắc chuẩn hóa phải được tính đến khi đếm chủ thể duy nhất qua nhiều kỳ.

## 7. Khử trùng mà không làm mất hành vi

### 7.1. Trùng do vận chuyển

Một collector có thể gửi lại cùng sự kiện khi mất kết nối hoặc chưa nhận được xác nhận. Nếu `source_system` và `source_event_id` giống nhau, đây thường là cùng một quan sát được chuyển lại.

```text
ObservationKey = (source_system, source_event_id)
```

Không giả định `source_event_id` duy nhất trên toàn tổ chức. Hai hệ thống khác nhau có thể cùng dùng số thứ tự `1001`.

Nếu cùng ObservationKey nhưng nội dung quyết định mâu thuẫn, không âm thầm chọn bản ghi mới nhất rồi coi là dữ liệu sạch. Giữ bằng chứng, đánh dấu xung đột và xử lý theo quy tắc nguồn; số liệu liên quan cần hiển thị trạng thái chưa xác nhận.

### 7.2. Trùng do nhiều tầng cùng quan sát

Gateway, policy engine và connector có thể cùng ghi một lần từ chối. Sau khi khử trùng vận chuyển, vẫn có ba quan sát về một lần thử.

```text
Gateway observation ─┐
Policy observation ─┼─> attempt_uid = A01 ─> một lần thử bị từ chối
Connector observation ┘
```

Chỉ gộp khi hợp đồng tương quan chứng minh đó là cùng một quyết định hoặc cùng lần thử ở đơn vị đang đo. Một trace ID dùng cho toàn bộ workflow chưa chắc là attempt ID: cùng workflow có thể chứa một quyết định mở phiên và nhiều quyết định thực thi lệnh.

Quy tắc tương quan cần phân biệt:

- Quan sát lặp của cùng quyết định.
- Nhiều bước trung gian của cùng lần thử.
- Nhiều quyết định con khác nhau trong cùng yêu cầu nghiệp vụ.
- Nhiều retry thực sự tạo lần thử mới.

### 7.3. Retry là lần thử mới khi có quyết định mới

Một service account gửi lại 100 yêu cầu đọc secret, mỗi yêu cầu đều được hệ thống đánh giá và từ chối riêng, tạo ra 100 lần thử. Không gộp thành một chỉ vì subject, resource và action giống nhau trong một phút.

Có thể xây thêm **incident group** để điều tra 100 lần đó như một cụm. Chỉ số nhóm sự cố và số lần thử vẫn phải giữ riêng.

Ngược lại, việc collector chuyển lại một log 100 lần không tạo ra 100 lần thử. Khi không có ID đủ tin cậy để phân biệt hai trường hợp, báo giới hạn dữ liệu và tách số đếm ước lượng khỏi số đếm đã xác nhận.

### 7.4. Không gộp theo phiên một cách tùy tiện

Một phiên quản trị có thể mở thành công nhưng bị chặn ba yêu cầu lệnh khác nhau. Với đơn vị `COMMAND_EXECUTION`, số đếm là 3. Dùng session ID làm khóa duy nhất sẽ làm mất hai lần thử.

Tương tự, một chính sách chặn nhiều điều kiện của cùng yêu cầu không nhất thiết tạo nhiều attempt. Có thể giữ nhiều reason trên một attempt hoặc chọn primary reason theo hợp đồng, nhưng tổng số reason không được mặc định bằng tổng số lần thử.

## 8. Luồng xử lý dữ liệu

```text
Log từ điểm thực thi PAM
  → xác minh nguồn và chuẩn hóa schema
  → lưu quan sát gốc theo quyền truy cập phù hợp
  → khử trùng theo ObservationKey
  → tương quan quan sát thành lần thử
  → phân loại terminal / enforce / deny / phạm vi
  → cập nhật bảng lần thử chuẩn hóa
  → tổng hợp theo cửa sổ và các chiều hữu hạn
  → dashboard, cảnh báo, liên kết bằng chứng
```

Bảng lần thử chuẩn hóa cần có một dòng cho mỗi `attempt_uid` theo phiên bản ngữ nghĩa. Nó phải bảo toàn tham chiếu về các quan sát nguồn đã tạo ra dòng đó.

Pseudocode minh họa:

```text
for each observation:
    validate required fields and trusted source
    if invalid:
        route to data-quality handling
        continue

    if same observation key already exists:
        compare payload or stable decision fields
        if conflicting:
            mark conflict; preserve evidence
        continue

    store observation
    correlate using the approved source-specific contract
    if attempt identity or final decision is unresolved:
        retain as unresolved; do not manufacture a deny
        continue

    upsert canonical attempt with source references
    recompute affected event-time aggregates when required
```

Một pipeline chỉ tăng counter mỗi khi nhận được log sẽ khó sửa sai khi một sự kiện đến muộn, một bản ghi bị nhận lại hoặc một quyết định được phân loại lại. Vì vậy, bảng sự kiện hoặc bảng lần thử có thể truy nguyên thường là nền tảng cho báo cáo; counter vận hành là một cách trình bày bổ sung.

## 9. Ví dụ đếm từ dữ liệu thô

Giả sử báo cáo cho production trong cửa sổ UTC **`[10:00, 10:15)`**, chỉ đo quyết định cấp quyền thực thi. Dữ liệu giả lập sau đã có hợp đồng liên kết attempt rõ ràng.

| Quan sát | Attempt | Nội dung | Cách xử lý |
|---|---|---|---|
| O01 | A01 | Gateway ghi deny terminal lúc 10:01 | Một lần từ chối |
| O02 | A01 | Bản chuyển lại của đúng event ở O01 | Bỏ trùng vận chuyển |
| O03 | A01 | Connector xác nhận cùng quyết định O01 | Gắn bằng chứng vào A01, không tăng số đếm |
| O04 | A02 | Deny terminal lúc 10:02 | Một lần từ chối |
| O05 | A03 | Retry mới, deny terminal lúc 10:02:05 | Một lần từ chối khác |
| O06 | A04 | Sai mật khẩu, dừng ở bước authentication | Sang chỉ số xác thực |
| O07 | A05 | Yêu cầu xác minh bổ sung lúc 10:04 | Trạng thái trung gian |
| O08 | A05 | Allow terminal sau xác minh lúc 10:05 | Một lần cho phép trong mẫu số |
| O09 | A06 | Would deny nhưng policy ở dry-run | Sang chỉ số mô phỏng |
| O10 | A07 | Lỗi nguồn, không xác định được quyết định | Một trường hợp unknown/error |
| O11 | A08 | Deny thuộc môi trường test | Ngoài phạm vi production |
| O12 | A09 | Deny terminal lúc 10:10 | Một lần từ chối |
| O13 | A10 | Deny terminal đúng 10:15 | Thuộc cửa sổ kế tiếp |
| O14 | A11 | Allow terminal lúc 10:12 | Một lần cho phép trong mẫu số |

Kết quả của cửa sổ:

```text
Raw observations                         = 14
Unique enforced terminal DENY attempts   = 4  (A01, A02, A03, A09)
Unique enforced terminal ALLOW attempts  = 2  (A05, A11)
Terminal authorization denominator      = 6
Deny rate                               = 4 / 6 ≈ 66,7%
Unknown/error attempts                   = 1  (A07, báo riêng)
```

Đếm dòng log có chữ `deny` sẽ làm sai kết quả vì O02, O03, O09, O11 và O13 không được đưa vào theo cùng cách với O01. Đếm subject duy nhất cũng không thay thế được số lần thử, đặc biệt khi A02 và A03 là retry của cùng một tài khoản.

Giả sử sau đó nhận thêm A12: quyết định deny xảy ra lúc 10:12 nhưng tới collector lúc 10:22. Với báo cáo theo event time và quy tắc nhận dữ liệu muộn cho phép, cửa sổ cần được sửa thành **5 deny / 7 quyết định terminal ≈ 71,4%**. Dashboard phải cho biết cửa sổ đã được cập nhật, thay vì âm thầm coi cả hai phiên bản đều là số cuối cùng.

## 10. Truy vấn tổng hợp minh họa

Ví dụ SQL sau dùng cú pháp PostgreSQL và giả định bảng `pam_authz_attempts` đã là bảng lần thử chuẩn hóa. Pipeline phải bảo đảm `attempt_uid` duy nhất trong phạm vi bảng và phiên bản định nghĩa; truy vấn này không tự giải quyết tương quan log thô.

Các cột thời gian dùng kiểu có thông tin múi giờ. Thời điểm trong ví dụ chỉ là dữ liệu giả lập.

```sql
WITH eligible_terminal AS (
    SELECT
        attempt_uid,
        decision,
        action_class,
        reason_code
    FROM pam_authz_attempts
    WHERE decision_time >= TIMESTAMPTZ '2026-05-12 10:00:00+00'
      AND decision_time <  TIMESTAMPTZ '2026-05-12 10:15:00+00'
      AND environment = 'production'
      AND event_kind = 'AUTHORIZATION'
      AND control_mode = 'ENFORCE'
      AND is_terminal = TRUE
      AND record_state = 'VALID'
      AND semantic_version = 'authz-attempt-v1'
      AND decision IN ('ALLOW', 'DENY')
), totals AS (
    SELECT
        COUNT(*) AS terminal_attempts,
        COUNT(*) FILTER (WHERE decision = 'DENY') AS denied_attempts
    FROM eligible_terminal
)
SELECT
    denied_attempts,
    terminal_attempts,
    ROUND(
        100.0 * denied_attempts / NULLIF(terminal_attempts, 0),
        2
    ) AS deny_rate_percent
FROM totals;
```

Với tập dữ liệu ví dụ trước khi A12 tới muộn, kết quả mong đợi là:

```text
denied_attempts | terminal_attempts | deny_rate_percent
4              | 6                 | 66.67
```

Để phân tích lý do, giữ cùng bộ lọc và thay phần tổng hợp bằng nhóm `action_class`, `reason_code`. Một attempt có nhiều reason phải được biểu diễn theo quy tắc đã thống nhất; nếu bung một dòng thành nhiều reason, tổng các nhóm có thể vượt tổng attempt và cần ghi rõ điều đó.

Không dùng `COUNT(DISTINCT attempt_uid)` như cách che mọi lỗi dữ liệu. Nó có thể che bản ghi lặp nhưng không giải quyết việc cùng attempt xuất hiện với cả allow và deny, hoặc một ID bị dùng lại cho hai quyết định khác nhau. Những trường hợp đó phải được xử lý trước khi tổng hợp.

### Đối soát dữ liệu bị loại

Ngoài truy vấn chỉ số, lưu số lượng quan sát bị loại theo nhóm: trùng vận chuyển, ngoài phạm vi, dry-run, authentication-only, chưa terminal, thiếu trường, xung đột và đến muộn chưa xử lý. Các nhóm cần có quy tắc ưu tiên nếu muốn cộng thành một phép đối soát không chồng lấn.

Không kỳ vọng lấy “tổng log trừ tất cả nhóm loại” sẽ luôn bằng số attempt: nhiều log hợp lệ có thể cùng thuộc một attempt. Phép đối soát phải tách hai tầng **quan sát** và **lần thử**.

## 11. Cửa sổ thời gian, dữ liệu đến muộn và độ phủ

### 11.1. Event time và ingestion time

Event time trả lời “quyết định xảy ra khi nào”; ingestion time trả lời “hệ thống báo cáo biết việc đó khi nào”. Dùng ingestion time cho báo cáo hành vi sẽ đẩy một đợt sự kiện cũ vào thời điểm collector khôi phục kết nối.

Với phát hiện gần thời gian thực, nên theo dõi cả hai:

- Tổng hợp hành vi theo event time.
- Theo dõi độ trễ tiếp nhận bằng chênh lệch `ingested_at - event_time`, có xử lý đồng hồ nguồn sai lệch.
- Gắn nhãn provisional cho cửa sổ còn có thể nhận dữ liệu muộn.
- Có cơ chế sửa tổng hợp, backfill và lưu lần cập nhật báo cáo.

Ví dụ chính sách nội bộ có thể đặt thời gian chờ dữ liệu muộn là 15 phút. Đây là lựa chọn vận hành cần dựa trên đặc điểm nguồn và yêu cầu báo cáo, không phải ngưỡng mặc định áp dụng cho mọi PAM. Sự kiện đến sau thời gian chờ vẫn cần một chính sách: sửa báo cáo lịch sử, ghi bản điều chỉnh hoặc đưa vào hàng đợi đối soát.

Watermark là thông tin tiến độ xử lý theo hợp đồng pipeline, không phải bằng chứng tuyệt đối rằng mọi nguồn đã gửi đủ log.

### 11.2. Độ phủ phải có mẫu số

“Đã nhận log từ 80 điểm thực thi” chưa cho biết độ phủ nếu không biết có bao nhiêu điểm nằm trong phạm vi. Có thể theo dõi:

```text
SourceCoverage
  = số điểm thực thi trong phạm vi có telemetry đạt điều kiện
    / tổng số điểm thực thi phải được giám sát
```

Điều kiện “đạt” cần công bố, chẳng hạn có heartbeat mới và có bằng chứng luồng audit hoạt động. Heartbeat của collector không tự chứng minh sự kiện cấp quyền đang được thu đủ.

Độ phủ theo số điểm thực thi cũng không tương đương độ phủ rủi ro. Mất log của một gateway phục vụ tài nguyên trọng yếu có thể nghiêm trọng hơn nhiều nguồn test cùng mất log. Dashboard nên cho biết các điểm thiếu dữ liệu và mức nhạy cảm của tài nguyên liên quan.

### 11.3. Số 0 không luôn là tín hiệu tốt

Unauthorized attempt count bằng 0 có thể do:

- Không phát sinh yêu cầu bị từ chối trong phạm vi đã quan sát.
- Không có hoạt động quản trị trong kỳ.
- Audit pipeline ngừng nhận dữ liệu.
- Policy bị chuyển sang audit-only hoặc nới quyền quá mức.
- Truy cập đang đi qua đường ngoài PAM, không nằm trong telemetry hiện có.

Chỉ số này đo các lần từ chối **đã quan sát**, không đo đầy đủ mọi ý định truy cập trái phép trên toàn hạ tầng. Muốn đánh giá đường vòng PAM, cần thêm bằng chứng từ tài nguyên đích, mạng hoặc các hệ thống giám sát khác trong phạm vi được phép.

## 12. Diễn giải số liệu trong bối cảnh PAM

### 12.1. Tăng do kiểm soát được cải thiện

Sau khi triển khai least privilege, những hành động trước đây được cho phép có thể bắt đầu bị chặn. Số deny tăng trong thời gian đầu có thể phản ánh kiểm soát hoạt động, yêu cầu cũ chưa được điều chỉnh hoặc cả hai.

Đối chiếu với thời điểm rollout, action class và reason code. Không kết luận chính sách sai chỉ vì số tăng; cũng không kết luận hệ thống an toàn hơn chỉ vì chặn được nhiều yêu cầu.

### 12.2. Tăng do lỗi tích hợp hoặc retry storm

Một workload liên tục gọi vault bằng grant đã hết hạn có thể tạo hàng nghìn lần từ chối. Dấu hiệu thường gồm một số ít subject, cùng target, cùng action và reason, bắt đầu ngay sau một thay đổi cấu hình hoặc vòng đời credential.

Hành động phù hợp là xác minh chủ sở hữu workload, grant, thời điểm luân chuyển credential và chính sách retry. Dừng retry không cần thiết hoặc sửa cấu hình hợp lệ có thể giảm số đếm, nhưng không cấp thêm quyền rộng chỉ để làm dashboard đẹp hơn.

### 12.3. Tăng do hành vi cần điều tra

Một chủ thể thử nhiều tài nguyên nhạy cảm ngoài phạm vi công việc, liên tục kích hoạt quyền hoặc thử các lệnh ngoài tập JEA cần được xem xét. Mức ưu tiên tăng khi có thêm bằng chứng như nguồn truy cập bất thường, thay đổi credential gần đó hoặc một lần allow đáng chú ý sau chuỗi deny.

Một lần allow sau deny có thể là quyền JIT vừa được phê duyệt hợp lệ. Nó cũng có thể là thay đổi chính sách sai. Vì vậy cần nối sự kiện với phê duyệt và phiên bản policy, không tự coi quan hệ thời gian là bằng chứng xâm nhập.

### 12.4. Giảm do mất hiệu lực kiểm soát

Số deny giảm mạnh cùng lúc tỷ lệ allow tăng, phạm vi policy giảm hoặc một điểm thực thi ngừng gửi audit cần được kiểm tra. Giảm số từ chối không phải mục tiêu độc lập; mục tiêu là truy cập hợp lệ thông suốt và truy cập ngoài quyền được kiểm soát đúng.

## 13. Dashboard và cảnh báo có thể hành động

### 13.1. Một nhóm thông tin đủ để ra quyết định

Một màn hình vận hành có thể hiển thị:

1. Số deny theo cửa sổ, cùng phạm vi và trạng thái provisional/final.
2. Deny rate với tử số, mẫu số và lượng unknown/error.
3. Xu hướng theo action class, reason code và resource tier.
4. Số subject, tài nguyên riêng biệt liên quan; drill-down có kiểm soát quyền.
5. Độ mới dữ liệu, nguồn thiếu và các thay đổi policy gần thời điểm biến động.

Không dùng duy nhất bảng “top người bị từ chối” để đánh giá cá nhân. Một tài khoản dịch vụ lỗi có thể đứng đầu nhưng không thể so trực tiếp với người dùng có vài yêu cầu quản trị hiếm gặp.

### 13.2. Chọn chiều tổng hợp hữu hạn

Các nhãn như môi trường, action class, reason code chuẩn hóa và resource tier thường phù hợp để tổng hợp. User ID, request ID, địa chỉ IP hoặc nguyên văn command có độ phân biệt cao nên đặt trong kho sự kiện phục vụ drill-down, không tùy tiện đưa vào nhãn của hệ thống time-series.

Không để reason code trở thành thông điệp tự do chứa username, đường dẫn secret hoặc đối số lệnh. Ngoài vấn đề kích thước dữ liệu, các giá trị này có thể làm lộ thông tin nhạy cảm.

### 13.3. Kết hợp ngưỡng tuyệt đối và bối cảnh

Quy tắc minh họa, cần hiệu chỉnh trong môi trường thật:

```text
Nếu số deny trong 5 phút tăng mạnh so với nền tương ứng
và đạt lượng tối thiểu đủ ý nghĩa
và telemetry của nguồn liên quan đang đủ mới:
    tạo tín hiệu để phân loại nguyên nhân

Nếu có deny hướng vào tài nguyên trọng yếu
với điều kiện rủi ro đã được tổ chức xác định:
    áp dụng tuyến ưu tiên riêng, kể cả số lượng thấp

Nếu dữ liệu không đủ mới hoặc có xung đột lớn:
    tạo cảnh báo chất lượng dữ liệu
    hiển thị giới hạn của chỉ số hành vi
```

Không có một ngưỡng “100 lần là tấn công” áp dụng chung. Nền của một hệ thống có ít thao tác quản trị khác với nền của một hạ tầng tự động hóa nhiều workload.

Tỷ lệ cũng cần điều kiện lượng tối thiểu: 1 deny trên 1 yêu cầu là 100%, nhưng khác về quy mô với 10.000 deny trên 10.000 yêu cầu. Với tài nguyên rất nhạy cảm, một lần thử vẫn có thể đáng điều tra theo ngữ cảnh riêng.

### 13.4. Hạn chế cảnh báo lặp

Có thể gộp thông báo của cùng subject, action và target trong thời gian ngắn, ghi số lần phát sinh bổ sung vào cùng ticket. Việc gộp thông báo không được thay đổi số attempt gốc.

Một cảnh báo hữu ích cần chứa cửa sổ thời gian, số deny, mẫu số, action/reason chính, tài nguyên liên quan, tình trạng telemetry và đường dẫn tới bằng chứng. Không gửi credential hoặc nội dung secret vào thông báo.

## 14. Runbook xử lý một đợt tăng bất thường

### Bước 1 — Xác nhận số liệu có đáng tin

Kiểm tra phạm vi, cửa sổ, trạng thái dữ liệu muộn, nguồn mới được thêm và thay đổi phiên bản định nghĩa. Xác minh đây là số attempt, không phải log thô hoặc số alert.

Kiểm tra xung đột decision, sự kiện chuyển lại, độ lệch đồng hồ và nguồn bị mất. Nếu chỉ số chưa đáng tin, mở nhánh sửa telemetry đồng thời bảo toàn quan sát liên quan.

### Bước 2 — Thu hẹp cụm hành vi

Xem action class, reason, subject type, resource tier và thời điểm bắt đầu. Phân biệt một workload retry với nhiều chủ thể dò nhiều target. Tìm thay đổi policy, grant JIT, luân chuyển credential hoặc thay đổi tích hợp tương ứng.

### Bước 3 — Xác minh nghiệp vụ và quyền hiện hành

Đối chiếu entitlement, phê duyệt JIT, giới hạn JEA, tài nguyên đích và thời gian hiệu lực. Với tài khoản dịch vụ, xác định workload owner và quy trình cấp credential; không mặc định service account là chủ thể không có người chịu trách nhiệm.

Với break-glass, đối chiếu việc kích hoạt, thời hạn và bằng chứng duyệt theo quy trình riêng. Không đưa mọi hoạt động break-glass vào allowlist vô điều kiện chỉ vì là truy cập khẩn cấp.

### Bước 4 — Chọn hành động theo bằng chứng

| Kết luận đã có bằng chứng | Hành động minh họa |
|---|---|
| Workload dùng grant hết hạn, nhu cầu vẫn hợp lệ | Sửa luồng xin quyền hoặc vòng đời credential theo phạm vi cần thiết |
| Người dùng chọn nhầm target | Hướng dẫn lại danh mục target và quy trình yêu cầu quyền |
| Policy mapping sai với yêu cầu đã được duyệt | Sửa mapping có kiểm soát, ghi thay đổi và kiểm tra lại |
| Hành vi không phù hợp nhiệm vụ, có thêm tín hiệu rủi ro | Chuyển quy trình điều tra và ứng phó được ủy quyền |
| Pipeline thu lại cùng log hoặc tương quan sai | Sửa xử lý dữ liệu, tính lại cửa sổ và ghi nhận điều chỉnh |

Không tự thu hồi tài khoản, chấm dứt phiên hoặc mở rộng quyền chỉ từ số đếm. Các hành động đó phải theo thẩm quyền và quy trình ứng phó tương ứng.

### Bước 5 — Đóng vòng phản hồi

Ghi nguyên nhân, quyết định xử lý, ticket, người phụ trách, thời điểm thay đổi và bằng chứng sau xử lý. Theo dõi lại cả deny, allow, unknown và tác động đến tác vụ quản trị hợp lệ.

Nếu số deny giảm vì sửa retry storm nhưng tổng yêu cầu cũng giảm, đó là kết quả khác với giảm do cấp quyền mới. Báo cáo nên giải thích cơ chế thay đổi thay vì chỉ đưa phần trăm cải thiện.

## 15. Thực hành với dữ liệu giả lập

Bài tập không cần thử truy cập trái phép vào hạ tầng thật. Có thể dùng tập sự kiện giả lập hoặc môi trường lab đã được cấp quyền để kiểm chứng logic đo lường.

### Phần A — Tạo hợp đồng và tập dữ liệu

Viết một hợp đồng ngắn dùng định nghĩa của bài học. Tạo các quan sát O01–O14 ở phần ví dụ, gồm ID nguồn, attempt, loại sự kiện, quyết định, chế độ, môi trường và hai timestamp.

Lưu riêng quan sát gốc và danh sách attempt sau tương quan. A01 phải còn ba tham chiếu quan sát nhưng chỉ tạo một attempt. A02 và A03 phải là hai attempt dù cùng subject và resource.

### Phần B — Tính kết quả cơ sở

Áp dụng bộ lọc và tạo báo cáo cho `[10:00, 10:15)` UTC. Kết quả mong đợi là 4 deny, 2 allow, mẫu số 6 và tỷ lệ xấp xỉ 66,7%. Unknown/error A07 phải được nhìn thấy trong phần chất lượng hoặc trạng thái xử lý, không biến mất khỏi mọi báo cáo.

### Phần C — Kiểm tra các tình huống dễ sai

| Thay đổi dữ liệu | Kết quả mong đợi |
|---|---|
| Gửi lại O01 thêm 10 lần với cùng khóa quan sát | Số deny vẫn là 4 |
| Thêm một retry thật có attempt mới, deny trong cửa sổ | Số deny tăng thành 5, mẫu số thành 7 |
| Thêm một quan sát connector của A02 | Số deny không tăng nếu đã chứng minh cùng quyết định |
| Đổi A06 từ dry-run sang một attempt enforce mới, có bằng chứng chặn | Attempt enforce mới được tính theo thời điểm của nó; không sửa lịch sử mô phỏng để giả thành thực thi |
| Thêm deny lúc đúng 10:15 | Cửa sổ hiện tại không tăng |
| Nhận A12 tới muộn với event time 10:12 | Điều chỉnh cửa sổ theo chính sách dữ liệu muộn |
| Loại hết allow và deny khỏi cửa sổ | Số deny 0, mẫu số 0, tỷ lệ N/A |
| Cùng khóa quan sát nhưng payload đổi từ deny sang allow | Đánh dấu xung đột, không âm thầm chọn một phía |
| Một phiên có ba lệnh riêng biệt bị JEA chặn | Có ba attempt ở mức command, không gộp theo session |

Các hàng thay đổi là những kịch bản độc lập so với tập cơ sở, trừ khi bài lab quy định rõ cộng dồn.

### Phần D — Viết diễn giải

Viết ba câu cho người trực vận hành: số đã quan sát, giới hạn dữ liệu, hành động kế tiếp. Ví dụ:

> Trong cửa sổ 15 phút, PAM ghi nhận 4 lần từ chối cấp quyền trên 6 quyết định terminal đã phân loại, tương ứng 66,7%. Một yêu cầu khác chưa xác định được quyết định; cửa sổ còn provisional. Ưu tiên kiểm tra cụm retry A02–A03 và đối soát nguồn của A07 trước khi kết luận nguyên nhân biến động.

Đây là cách diễn giải có thể kiểm chứng; nó không gán toàn bộ từ chối thành tấn công và không che phần dữ liệu chưa rõ.

## 16. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách sửa |
|---|---|---|
| Đếm mọi dòng chứa chữ “denied” | Trùng log, lẫn dry-run và sai phạm vi | Chuẩn hóa decision và đếm theo attempt |
| Dùng cùng subject + target trong một phút làm khóa | Làm mất retry hoặc hành vi dò lặp | Dùng định danh lần thử theo hợp đồng nguồn |
| Trộn authentication failure với authorization deny | Không biết kiểm soát nào đang gặp vấn đề | Tách chỉ số, công bố định nghĩa tổng nếu cần |
| Dùng tổng phiên làm mẫu số cho deny ở mức lệnh | Tỷ lệ sai đơn vị, có thể khó diễn giải | Tử số và mẫu số cùng đơn vị quyết định |
| Trừ lỗi/unknown rồi không hiển thị chúng | Dashboard tạo cảm giác đầy đủ giả tạo | Báo riêng mức thiếu dữ liệu và chất lượng |
| Lấy trung bình tỷ lệ của các nhóm | Sai trọng số khi lưu lượng khác nhau | Cộng tử, cộng mẫu rồi chia |
| Mục tiêu quản trị là giảm deny về 0 | Khuyến khích nới quyền hoặc tắt log | Đánh giá hiệu lực kiểm soát và tác vụ hợp lệ cùng nhau |
| Dùng nguyên văn command hoặc secret path làm metric label | Dữ liệu phình lớn, có thể lộ thông tin | Dùng action/reason chuẩn hóa và tham chiếu bằng chứng |
| Không đánh dấu rollout hoặc mở rộng coverage | Nhầm thay đổi phạm vi với hành vi bất thường | Ghi chú thay đổi trên chuỗi thời gian |
| Xem log deny là bằng chứng mọi đường truy cập đều được chặn | Bỏ sót đường vòng PAM | Đánh giá thêm độ phủ và bằng chứng từ target |

## 17. Câu hỏi tự kiểm tra

1. Một lần thử có ba log từ gateway, engine và connector thì đếm bao nhiêu? Điều kiện nào cho phép gộp chúng?
2. Vì sao 500 retry bị đánh giá riêng không nên bị gộp thành một attempt?
3. Tại sao audit-only “would deny” không chứng minh truy cập đã bị ngăn?
4. Một phiên được mở hợp lệ nhưng có ba lệnh bị chặn nên được biểu diễn thế nào?
5. Nếu không có yêu cầu terminal trong cửa sổ, vì sao deny rate là N/A?
6. Số deny giảm về 0 trong khi một gateway mất log cần được diễn giải ra sao?
7. Khi một sự kiện deny tới muộn, dữ liệu lịch sử và trạng thái báo cáo phải thay đổi thế nào?
8. Những bằng chứng nào cần xem trước khi quy một đợt tăng deny thành hành vi tấn công?

Unauthorized attempt count hữu ích khi mỗi con số truy nguyên được về một đơn vị đã định nghĩa, một quyết định thực thi và một phạm vi quan sát rõ ràng. Trong vận hành PAM, hãy dùng nó để nhận ra nơi quyền truy cập, chính sách và hành vi đang không khớp nhau; sau đó kết hợp dữ liệu chất lượng, ngữ cảnh nghiệp vụ và bằng chứng phiên để chọn hành động phù hợp.
