# Standing privilege count: đếm quyền đặc quyền thường trực trong PAM

## 1. Chỉ số này cho biết điều gì?

**Standing privilege** là quyền đặc quyền mà một chủ thể được duy trì sẵn để sử dụng, thay vì chỉ được cấp cho một nhiệm vụ cụ thể trong một khoảng thời gian ngắn có kiểm soát. Ví dụ, tài khoản được gắn thường xuyên vào nhóm quản trị production có standing privilege ngay cả khi người dùng chưa đăng nhập trong nhiều tuần.

**Standing privilege count** đo số lượng quyền đặc quyền thường trực theo một đơn vị đếm đã thống nhất. Chỉ số giúp chương trình Privileged Access Management (PAM) trả lời: “Trong phạm vi đang đo, có bao nhiêu quyền mạnh vẫn luôn sẵn sàng cho các danh tính sử dụng?”

Một con số giảm có thể cho thấy tổ chức đã chuyển từ quyền quản trị cố định sang Just-in-Time (JIT), thu hẹp quyền hoặc loại bỏ quyền không cần thiết. Tuy nhiên, con số đó chỉ có ý nghĩa khi phạm vi, cách chuẩn hóa và độ đầy đủ của dữ liệu được giữ nhất quán.

Trong bài này, đơn vị chính là **quan hệ quyền thường trực có hiệu lực đã chuẩn hóa**, gọi ngắn là *standing entitlement*. Đồng thời, ta báo cáo số danh tính có ít nhất một standing entitlement để thấy quyền đang tập trung vào bao nhiêu chủ thể. Đây là một hợp đồng đo lường minh họa; khi triển khai phải xác nhận đơn vị mà công cụ PAM và tổ chức thực sự sử dụng.

> Mười tài khoản quản trị, mười lần gán role và mười quyền có hiệu lực là ba đại lượng khác nhau. Không dùng chúng thay thế cho nhau dưới cùng một nhãn.

## 2. Phân biệt quyền thường trực, phiên truy cập và credential

Một tài khoản có thể không có phiên hoạt động nhưng vẫn giữ quyền quản trị thường trực. Vì vậy, “không có session” không có nghĩa là “không có standing privilege”.

Tương tự, thời hạn của credential và thời hạn của quyền là hai yếu tố khác nhau:

- Một credential ngắn hạn được cấp liên tục cho một workload có quyền quản trị cố định không tự làm quyền đó trở thành JIT.
- Một mật khẩu được vault quản lý và luân chuyển thường xuyên có thể bảo vệ credential tốt hơn, nhưng quyền quản trị của tài khoản vẫn có thể tồn tại liên tục.
- Một grant có ngày hết hạn xa vẫn có thể được xem là standing theo chính sách nếu quyền được duy trì sẵn, không gắn với nhiệm vụ và cửa sổ truy cập ngắn.
- Một role đủ điều kiện kích hoạt nhưng chưa được kích hoạt khác với một grant đang có hiệu lực.

JIT cũng cần được chứng minh bằng trạng thái thực tế. Grant được gắn nhãn “temporary” nhưng tự gia hạn vô hạn, không thu hồi được hoặc vẫn để lại đường quản trị cố định cần được điều tra. Không tự loại mọi grant có trường `expires_at` ra khỏi chỉ số.

Đối với grant JIT đang trong cửa sổ hợp lệ, có nhiệm vụ rõ ràng và cơ chế hết hạn được thực thi, bài này ghi nhận nó là **quyền đặc quyền tạm thời đang hoạt động**, không phải standing entitlement. Chỉ số riêng phải theo dõi số grant JIT đang hoạt động và các grant quá hạn để tránh tạo điểm mù.

## 3. Chốt hợp đồng đo lường trước khi đếm

Một định nghĩa dùng được trong vận hành cần có tối thiểu các thành phần sau.

| Thành phần | Câu hỏi cần chốt | Ví dụ trong bài |
|---|---|---|
| Phạm vi | Đo hệ thống, môi trường và tenant nào? | Production của đơn vị Payments |
| Thời điểm | Snapshot biểu diễn trạng thái lúc nào? | 09:00 UTC, ngày đo giả lập |
| Chủ thể | Đếm con người, workload hay cả hai? | Human, service account và break-glass |
| Đặc quyền | Hành động nào đủ mạnh để tính? | Quản trị hệ thống, triển khai production, đọc secret quản trị |
| Thường trực | Điều kiện nào phân biệt standing với JIT? | Quyền duy trì sẵn theo chính sách phân loại đã duyệt |
| Đơn vị | Đếm danh tính, grant hay entitlement? | Entitlement có hiệu lực sau loại trùng |
| Scope | Wildcard, tổ chức và tài nguyên đơn lẻ được chuẩn hóa thế nào? | Dùng scope key được quản lý, giữ thông tin độ rộng |
| Đường kế thừa | Có phân tích nhóm lồng nhau, role và policy không? | Có, trong giới hạn khả năng của từng nguồn |
| Chất lượng dữ liệu | Dữ liệu thiếu hoặc chưa xác định được biểu diễn thế nào? | Tách UNKNOWN; không đổi thành 0 |
| Phiên bản | Định nghĩa có thay đổi giữa các kỳ không? | `standing-count-v1` |

Các giá trị trong bảng là lựa chọn minh họa, không phải ngưỡng bắt buộc cho mọi hệ thống.

### 3.1. Danh tính phải có khóa ổn định

Không dùng display name làm khóa chính. Hai tài khoản cùng tên ở hai tenant có thể là hai chủ thể khác nhau. Ngược lại, một tài khoản xuất hiện dưới nhiều alias trong cùng hệ thống không nên tự động biến thành nhiều danh tính.

Khóa chủ thể nên chứa namespace của nguồn, tenant hoặc miền và định danh bất biến mà nguồn cung cấp. Nếu ánh xạ nhiều tài khoản về một con người, báo cáo thêm số người riêng; vẫn giữ số tài khoản đặc quyền vì mỗi tài khoản là một bề mặt cần quản lý.

Đối với workload, phân biệt danh tính logic với bản sao runtime. Nếu một workload tạo hàng nghìn pod nhưng đều sử dụng cùng một danh tính được cấp quyền, không để số pod làm tăng giả số standing entitlement. Ngược lại, các danh tính runtime thực sự độc lập cần được xử lý theo hợp đồng đã chốt.

### 3.2. Danh mục đặc quyền phải phản ánh tác động

Một capability có thể là `system.administer`, `production.deploy` hoặc `admin-secret.read`. Tên capability là ví dụ nội bộ; điều quan trọng là định nghĩa rõ nó cho phép làm gì.

Quyền sửa policy, thêm thành viên nhóm quản trị hoặc lấy credential quản trị có thể tạo đường tới đặc quyền, dù tên role không chứa từ “admin”. Danh mục đo cần bao gồm các đường nâng quyền đã xác nhận trong phạm vi phân tích. Nếu công cụ chưa đánh giá được chúng, ghi rõ giới hạn thay vì khẳng định đã đo toàn bộ quyền có hiệu lực.

Không chia một capability thành nhiều capability nhỏ chỉ để tăng độ chi tiết rồi so trực tiếp với chuỗi số cũ. Thay đổi danh mục có thể làm chỉ số tăng dù không có grant mới.

## 4. Định nghĩa bằng tập hợp

Tại thời điểm `t`, đặt:

```text
E(t) = tập entitlement đặc quyền có hiệu lực trong phạm vi đo

Mỗi entitlement được chuẩn hóa thành:
(principal_key, resource_scope_key, capability_key)
```

Một entitlement có thể được suy ra từ nhiều đường cấp quyền: gán trực tiếp, nhóm, nhóm lồng nhau hoặc role. Trong đơn vị đếm của bài, các đường cấp cùng một bộ ba không làm tăng số entitlement.

Đặt `S(t)` là tập entitlement trong `E(t)` được xác nhận là standing theo chính sách:

```text
Standing entitlement count(t) = |S(t)|

Standing privileged identity count(t)
    = số principal_key khác nhau xuất hiện trong S(t)
```

Hai số này nên hiển thị cạnh nhau. Chúng trả lời hai câu hỏi:

- Có bao nhiêu quan hệ quyền thường trực?
- Có bao nhiêu danh tính đang nắm ít nhất một quan hệ như vậy?

Nếu một người có quyền quản trị ba scope khác nhau, standing identity count có thể là 1 trong khi standing entitlement count là 3. Nếu hai đường khác nhau cùng cấp một capability trên cùng scope cho người đó, số entitlement vẫn là 1, nhưng số đường cấp quyền có thể là 2.

### 4.1. “Có hiệu lực” không chỉ là “có bản ghi allow”

Để đưa một quan hệ vào `E(t)`, cần xem xét các yếu tố mà nền tảng thực sự áp dụng: trạng thái chủ thể, membership, điều kiện của policy, phạm vi tài nguyên, thời gian hiệu lực và cơ chế deny hoặc giới hạn quyền tương ứng.

Không mặc định mọi hệ thống có cùng thứ tự ưu tiên policy. Một bộ thu thập chỉ liệt kê role assignment chưa đủ để tuyên bố đã tính quyền có hiệu lực đầy đủ.

Khi chưa xác định được hiệu lực, dùng trạng thái `UNKNOWN`. Không tự coi bản ghi là an toàn vì thiếu log sử dụng, cũng không tự coi mọi bản ghi cấu hình là quyền chắc chắn đang dùng được.

### 4.2. Wildcard không tương đương tài nguyên đơn lẻ

Theo hợp đồng ví dụ, một entitlement có scope toàn tenant có thể được đếm là 1. Một entitlement giới hạn trên một máy cũng có thể được đếm là 1. Tác động của chúng rất khác nhau.

Vì vậy, ngoài số đếm phải báo cáo tối thiểu:

- Số entitlement có scope rộng hoặc wildcard.
- Phân bố theo cấp độ rủi ro và môi trường.
- Số entitlement trên tài sản quan trọng.
- Số danh tính không xác định được owner.

Nếu cần một chỉ số đã nhân theo từng tài nguyên, đặt tên riêng và cố định tập tài nguyên dùng để khai triển. Khi tài nguyên tăng, số khai triển có thể tăng dù policy không đổi. Không trộn cách đếm đó với cách đếm theo scope key.

## 5. Nguồn dữ liệu và đường đi từ grant tới metric

Một pipeline tối thiểu có thể được hình dung như sau:

```text
Nguồn danh tính + membership + policy + trạng thái tài nguyên
                         |
                         v
       Xác định hiệu lực và đường kế thừa quyền
                         |
                         v
    Chuẩn hóa principal / scope / capability, giữ provenance
                         |
                         v
          Phân loại standing / JIT / eligible / unknown
                         |
                         v
             Loại trùng entitlement tại snapshot
                         |
                         v
        Count + phân nhóm + kiểm tra chất lượng dữ liệu
```

Đây là luồng xử lý logic. Tùy hệ thống, một số bước có thể được nền tảng nguồn thực hiện sẵn; cần biết phần nào là dữ liệu quan sát được và phần nào là kết quả suy diễn.

### 5.1. Dữ liệu cần thu thập

Nguồn thường bao gồm directory hoặc IdP, hệ điều hành, IAM của cloud, cơ sở dữ liệu, nền tảng container, công cụ triển khai và vault/PAM. Không bắt buộc mọi tổ chức dùng đủ các nguồn đó; chỉ đưa vào phạm vi những nguồn đã được khai báo và kiểm kê.

Mỗi entitlement nên truy được về bằng chứng:

```text
snapshot_id
observed_at
source_collected_at
source_system
principal_key
principal_type
resource_scope_key
capability_key
effective_state
access_mode
owner_key
evidence_reference
classification_version
```

Metadata bổ sung như đường membership, policy ID, ngày hết hạn, mức quan trọng của tài sản và trạng thái thu hồi giúp giải thích số liệu. Bản ghi đo lường không cần chứa mật khẩu, token, private key hoặc nội dung secret.

### 5.2. Giữ cả entitlement và đường cấp quyền

Loại trùng trong bảng metric không có nghĩa là xóa provenance.

Ví dụ, Alice có quyền quản trị từ cả grant trực tiếp và nhóm `ProdAdmins`. Metric chỉ tính một entitlement, nhưng thao tác thu hồi phải xử lý cả hai đường. Xóa grant trực tiếp rồi thấy entitlement vẫn còn là kết quả đúng, không phải lỗi bộ đếm.

Dữ liệu đường cấp quyền có thể nằm trong bảng khác với khóa liên kết tới entitlement. Cách này cho phép trả lời đồng thời “có bao nhiêu quyền?” và “cần sửa ở đâu để quyền thực sự biến mất?”.

### 5.3. Snapshot phải đủ nhất quán

Nếu membership lấy lúc 09:00 nhưng role definition lấy từ ba ngày trước, phép suy ra quyền có thể sai. Ghi thời gian thu thập từng nguồn, quy định độ trễ chấp nhận được và đánh dấu nguồn quá hạn.

Nếu thiếu một connector, không xóa các quyền của nguồn đó khỏi tổng rồi công bố số giảm như một thành tựu. Có thể giữ bản quan sát gần nhất để hỗ trợ điều tra, nhưng phải gắn nhãn cũ và không mô tả nó là trạng thái hiện tại đã xác nhận.

## 6. Ví dụ đếm có quyền kế thừa và JIT

Giả sử snapshot `T0` của Payments production có các bản ghi sau. Tên danh tính và scope đều là dữ liệu giả lập.

| Bản ghi | Chủ thể | Capability và scope | Đường cấp hoặc trạng thái | Tính standing? |
|---|---|---|---|---|
| 1 | Alice | `system.administer / vm-prod` | Grant trực tiếp, có hiệu lực | Có |
| 2 | Alice | `system.administer / vm-prod` | Nhóm quản trị, có hiệu lực | Trùng entitlement của dòng 1 |
| 3 | Bob | `database.administer / db-payments` | Role DBA cố định | Có |
| 4 | Bob | `admin-secret.read / vault-payments` | Policy đọc secret quản trị cố định | Có |
| 5 | CI workload | `production.deploy / payments-api` | Role triển khai cố định | Có |
| 6 | Break-glass | `platform.administer / prod-platform` | Tài khoản khẩn cấp giữ quyền sẵn | Có |
| 7 | Carol | `system.administer / vm-prod` | JIT hợp lệ cho một nhiệm vụ, trong cửa sổ cấp | Không, theo dõi ở chỉ số JIT |
| 8 | Dave | `database.administer / db-payments` | Chỉ eligible, chưa kích hoạt | Không phải grant đang có hiệu lực |
| 9 | Eric | `system.administer / vm-prod` | Đã yêu cầu thu hồi nhưng quyền vẫn có hiệu lực | Có |
| 10 | Frank | `database.administer / db-payments` | Grant hết hạn, đã xác nhận không còn hiệu lực | Không |

Kết quả:

```text
Standing entitlement count(T0) = 6
Standing privileged identity count(T0) = 5

Danh tính được tính: Alice, Bob, CI workload, Break-glass, Eric.
Bob giữ 2 entitlement; Alice có 2 đường cấp cho 1 entitlement.
```

Chỉ đếm số dòng có grant cố định sẽ đếm thừa Alice. Chỉ đếm người dùng sẽ bỏ mất sự khác biệt giữa Bob và các danh tính chỉ có một entitlement. Loại Eric vì ticket đã đóng sẽ đếm thiếu nếu quyền vẫn sử dụng được.

Tại `T1`, đội vận hành hoàn thành hai thay đổi:

1. Thu hồi cả hai đường standing của Alice, xác nhận hiệu lực đã mất; Alice chuyển sang JIT.
2. Thu hồi quyền đọc secret quản trị của Bob và xác nhận đã mất quyền; role DBA của Bob vẫn còn.

Khi phạm vi và phương pháp không đổi:

```text
Standing entitlement count(T1) = 4
Standing privileged identity count(T1) = 4

Mức giảm entitlement tuyệt đối = 6 - 4 = 2
Mức giảm entitlement tương đối = (6 - 4) / 6 × 100% ≈ 33,3%
```

Eric vẫn được tính cho đến khi bằng chứng hiệu lực cho thấy quyền đã mất theo phạm vi kiểm tra. Nếu Eric còn token hoặc session giữ được đặc quyền, quy trình thu hồi cần xem xét phần đó; chỉ xóa role assignment chưa đủ cho mọi nền tảng.

Không diễn giải mức giảm 33,3% là “rủi ro đã giảm 33,3%”. Rủi ro còn phụ thuộc loại quyền, độ rộng scope, khả năng truy cập và giá trị tài sản.

## 7. Minh họa truy vấn trên snapshot đã chuẩn hóa

Ví dụ SQL dưới đây chỉ minh họa cách tổng hợp một snapshot. Nó không thay thế bộ phân tích quyền kế thừa hoặc policy của hệ thống nguồn và không giả định một sản phẩm PAM cụ thể.

Giả sử bảng `effective_privilege_snapshot` có ràng buộc duy nhất:

```text
(snapshot_id, principal_key, resource_scope_key, capability_key)
```

Mỗi dòng đã là một entitlement đặc quyền được chuẩn hóa, không phải một đường grant. Nếu chưa loại trùng ở đầu vào, phải làm bước đó trước khi dùng `COUNT(*)`.

Các cột phân loại:

```text
effective_state = EFFECTIVE | INEFFECTIVE | UNKNOWN
access_mode     = STANDING | JIT | ELIGIBLE | NONE | UNKNOWN
principal_type = HUMAN | WORKLOAD | BREAK_GLASS | OTHER
```

Tên trạng thái là ví dụ thiết kế. Snapshot được chọn phải có manifest phạm vi và phiên bản hợp đồng đo lường đi kèm.

### 7.1. Tổng số entitlement và danh tính

```sql
SELECT
    COUNT(*) AS standing_entitlement_count,
    COUNT(DISTINCT principal_key) AS standing_identity_count
FROM effective_privilege_snapshot
WHERE snapshot_id = :snapshot_id
  AND effective_state = 'EFFECTIVE'
  AND access_mode = 'STANDING';
```

Query không loại bỏ quyền chỉ vì nó đã nằm trong danh sách “được chấp thuận ngoại lệ” hoặc đã có ticket thu hồi. Ngoại lệ là ngữ cảnh quản trị, không làm quan hệ quyền tự biến mất.

### 7.2. Phân nhóm theo loại danh tính

```sql
SELECT
    principal_type,
    COUNT(*) AS standing_entitlement_count,
    COUNT(DISTINCT principal_key) AS standing_identity_count
FROM effective_privilege_snapshot
WHERE snapshot_id = :snapshot_id
  AND effective_state = 'EFFECTIVE'
  AND access_mode = 'STANDING'
GROUP BY principal_type
ORDER BY standing_entitlement_count DESC;
```

Loại danh tính phải được chuẩn hóa nhất quán. Nếu một tài khoản khẩn cấp trước đây được gắn `HUMAN` rồi được chuyển sang `BREAK_GLASS`, thay đổi đó làm dịch chuyển số giữa các nhóm nhưng không nhất thiết làm thay đổi tổng.

### 7.3. Theo dõi phần chưa đủ dữ liệu

```sql
SELECT COUNT(*) AS unresolved_entitlement_count
FROM effective_privilege_snapshot
WHERE snapshot_id = :snapshot_id
  AND (
      effective_state = 'UNKNOWN'
      OR (
          effective_state = 'EFFECTIVE'
          AND access_mode = 'UNKNOWN'
      )
  );
```

Đây chỉ là số bản ghi đã phát hiện nhưng chưa phân loại đủ. Nó không đo được quyền chưa được phát hiện do connector mất dữ liệu hoặc thiếu hệ thống trong inventory. Vì vậy, phải có chỉ số độ phủ nguồn riêng.

Ví dụ cách hiển thị:

```text
Standing entitlement đã xác nhận: 124
Entitlement chưa xác định hiệu lực/chế độ: 17
Nguồn cập nhật đúng hạn: 8/9
Trạng thái so sánh với kỳ trước: CHƯA ĐỦ ĐIỀU KIỆN
```

Không cộng máy móc 17 vào 124 để gọi đó là tổng standing chính xác; cũng không ngầm coi 17 là 0.

### 7.4. So sánh hai kỳ bằng danh sách thay đổi

Ngoài chênh lệch tổng, đối chiếu theo bộ khóa entitlement để tạo hai danh sách:

```text
Added standing entitlements
    = S(T1) trừ S(T0)

Removed standing entitlements
    = S(T0) trừ S(T1)
```

Phần tăng và phần giảm có thể bù nhau. Tổng giữ nguyên không có nghĩa là trạng thái quyền không đổi.

Mỗi entitlement rời khỏi tập standing cần có lý do: thu hồi, chuyển JIT đã xác nhận, thay đổi phạm vi được phê duyệt, thay đổi phân loại hoặc sửa lỗi dữ liệu. Chỉ các lý do thực sự làm giảm quyền thường trực mới nên được tính là kết quả khắc phục.

## 8. Đọc xu hướng mà không bị số liệu đánh lừa

### 8.1. So sánh cùng phạm vi

Giả sử tháng trước đo 100 hệ thống, tháng này chỉ có dữ liệu của 70 hệ thống. Số standing entitlement giảm từ 500 xuống 350 chưa chứng minh đã loại bỏ 150 entitlement.

Báo cáo nên có:

- Tổng trong phạm vi hiện tại.
- Số thay đổi trên tập hệ thống chung giữa hai kỳ.
- Phần tăng/giảm do thêm hoặc bớt hệ thống.
- Phần thay đổi do danh mục capability hoặc thuật toán phân tích.
- Phần thay đổi do hoạt động thu hồi hoặc chuyển JIT.

Nếu thay đổi định nghĩa lớn, tạo baseline mới hoặc tính lại lịch sử bằng cùng một định nghĩa khi có đủ dữ liệu. Không nối hai chuỗi khác phương pháp mà bỏ chú thích.

### 8.2. Tỷ lệ giảm cần baseline hợp lệ

Công thức giảm theo baseline là:

```text
Reduction rate
    = (baseline_count - current_count) / baseline_count × 100%
```

Chỉ dùng khi baseline lớn hơn 0 và hai số so sánh được. Nếu baseline bằng 0, tỷ lệ không xác định; báo số tăng/giảm tuyệt đối thay vì chia cho 0 hoặc tự hiển thị 100%.

Nếu số hiện tại lớn hơn baseline, kết quả âm biểu thị mức tăng theo công thức này. Đừng ép về 0 để biểu đồ trông đẹp hơn.

### 8.3. “Tỷ lệ standing” phải ghi rõ mẫu số

Có thể định nghĩa:

```text
Standing identity ratio
    = số danh tính có ít nhất một standing privilege
      / số danh tính có ít nhất một quyền đặc quyền có hiệu lực
      × 100%
```

Một danh tính vừa có standing vừa có JIT vẫn xuất hiện một lần ở tử và một lần ở mẫu theo định nghĩa trên.

Tỷ lệ theo danh tính không tương đương tỷ lệ theo entitlement. Tỷ lệ có mẫu số bao gồm quyền JIT cũng dễ dao động khi số phiên JIT thay đổi. Bởi vậy, count tuyệt đối, tỷ lệ và phạm vi phải xuất hiện cùng nhau.

### 8.4. Count bằng 0 chưa chứng minh không còn đường tấn công

Kết quả 0 chỉ nói rằng không có entitlement standing được xác nhận trong phạm vi và định nghĩa đang đo.

Nó có thể đồng thời tồn tại với tài sản chưa kiểm kê, quyền chưa phân tích được, đường nâng quyền gián tiếp hoặc eligible role có điều kiện kích hoạt quá yếu. Các vấn đề đó cần chỉ số và kiểm tra bổ sung, không nên bị che bởi một ô dashboard màu xanh.

## 9. Các nhóm quyền cần xử lý thận trọng

### 9.1. Tài khoản khẩn cấp

Tài khoản break-glass giữ sẵn quyền quản trị vẫn tạo standing privilege. Việc credential được niêm phong, giám sát và chỉ mở trong trường hợp khẩn cấp là biện pháp kiểm soát bổ sung.

Nên báo cáo riêng nhóm này với owner, lý do tồn tại, điều kiện sử dụng và kỳ rà soát. Nếu nó nằm trong phạm vi đo, giữ nó trong tổng; không loại chỉ để đạt mục tiêu “zero standing”.

### 9.2. Service account và workload

Một dịch vụ có thể cần một số quyền liên tục để thực hiện chức năng. Mục tiêu là loại quyền dư thừa và thu hẹp quyền cần thiết, không thu hồi toàn bộ quyền làm ngừng hệ thống.

Phân biệt quyền nghiệp vụ liên tục với quyền quản trị quá rộng. Ví dụ, workload cần cập nhật một tài nguyên cụ thể không mặc nhiên cần quản trị toàn bộ tenant. Theo dõi thêm scope, credential exposure, owner và cơ chế kiểm soát thay đổi của workload.

### 9.3. Eligible role và khả năng tự kích hoạt

Role chỉ đủ điều kiện kích hoạt, chưa có hiệu lực, không thuộc standing entitlement của ví dụ. Tuy nhiên, nếu chủ thể có thể tự kích hoạt liên tục, không có ràng buộc nhiệm vụ hoặc có đường bỏ qua kiểm soát, phần rủi ro đó vẫn phải được theo dõi.

Có thể dùng chỉ số riêng như số eligible role không có điều kiện kích hoạt phù hợp hoặc số lần gia hạn liên tiếp bất thường. Không tự đổi định nghĩa standing theo từng trường hợp mà không cập nhật hợp đồng đo lường.

### 9.4. Grant đang thu hồi

Một workflow có thể đi qua các trạng thái:

```text
Phát hiện → Phê duyệt thu hồi → Gửi lệnh → Nguồn chấp nhận
          → Xác nhận quyền mất hiệu lực → Đóng việc
```

Metric cần phản ánh trạng thái quyền, không chỉ trạng thái workflow. Với hệ thống có độ trễ, cache hoặc session độc lập, cần ghi nhận thời điểm nào đã xác nhận mất hiệu lực và phần nào chưa kiểm chứng.

Nếu sau khi gửi lệnh không còn đủ dữ liệu để đánh giá, chuyển phần đó sang chưa xác định theo hợp đồng, đồng thời giữ nó trong hàng đợi điều tra. Không ghi nhận một lần giảm đã xác nhận chỉ từ việc thiếu quan sát.

## 10. Biến kết quả thành kế hoạch giảm quyền

Một danh sách khắc phục hữu ích thường gồm chủ thể, entitlement, nguồn cấp, owner, rủi ro, hành động dự kiến và bằng chứng hoàn tất.

Trình tự thực tế có thể là:

1. Xác nhận entitlement và các đường cấp quyền còn hiệu lực.
2. Liên hệ owner qua quy trình hiện có để xác nhận nhu cầu.
3. Chọn cách xử lý: thu hồi, thu hẹp scope, thay role hoặc chuyển sang JIT/JEA.
4. Thực hiện trong quy trình thay đổi phù hợp với hệ thống.
5. Xác minh quyền cũ đã mất và đường truy cập cần thiết vẫn hoạt động.
6. Thu snapshot mới, ghi rõ entitlement đã rời tập standing vì lý do gì.

**JEA — Just Enough Administration** có thể giảm tập capability hoặc scope mà vẫn để lại một số quyền thường trực cần thiết. JIT và JEA tác động khác nhau: JIT giới hạn thời gian; JEA giới hạn quyền được làm. Hai cơ chế có thể kết hợp.

Ưu tiên xử lý dựa trên tác động, không chỉ số lượng. Loại bỏ một quyền quản trị toàn bộ production thường có giá trị khác với loại bỏ nhiều quyền hẹp trên hệ thống thử nghiệm.

Không tự động thu hồi chỉ từ dashboard nếu chưa có quy trình đánh giá nhu cầu và ảnh hưởng. Chỉ số dùng để định hướng và theo dõi; hành động lên hệ thống cần có ngữ cảnh và cơ chế triển khai của tổ chức.

## 11. Dashboard và bằng chứng cần đủ để giải thích con số

Một dashboard vận hành gọn nhưng có ích có thể gồm:

| Thành phần | Nội dung cần hiển thị |
|---|---|
| Count chính | Standing entitlement count |
| Count đồng hành | Số danh tính có standing privilege |
| Phân nhóm | Human, workload, break-glass; owner; môi trường |
| Mức tác động | Scope rộng, tài sản quan trọng, capability rủi ro cao |
| Thay đổi | Added/removed so với kỳ trước và lý do |
| Chất lượng | Nguồn đủ dữ liệu, độ mới, UNKNOWN, lỗi thu thập |
| Ngoại lệ | Số quyền được chấp thuận giữ lại và kỳ rà soát |
| Hợp đồng | Phạm vi, thời điểm snapshot, phiên bản định nghĩa |

Để một số liệu có thể kiểm chứng, lưu manifest snapshot, thời gian thu thập, phiên bản phân loại, truy vấn hoặc phiên bản pipeline và tham chiếu bằng chứng của entitlement. Giữ đủ dữ liệu để giải thích chênh lệch giữa các kỳ.

Thông tin quyền và membership có thể nhạy cảm. Chỉ cấp quyền đọc cần thiết cho kho dữ liệu metric; báo cáo tổng hợp không nên tiết lộ credential hay nội dung phiên quản trị.

Nếu nguồn hỗ trợ bằng chứng thu hồi, lưu tham chiếu tương ứng. Một ticket “done” có ích cho truy vết quy trình, nhưng không tự thay thế bằng chứng trạng thái quyền.

## 12. Lỗi đo lường thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Đếm role assignment như entitlement hiệu lực | Sai do kế thừa, trùng đường hoặc policy hạn chế | Phân tích hiệu lực, chuẩn hóa và giữ provenance |
| Đếm một nhóm quản trị là một danh tính | Che số thành viên thực sự nhận quyền | Mở rộng membership trong phạm vi phân tích |
| Loại tài khoản đã lâu không đăng nhập | Bỏ sót quyền vẫn sẵn sàng | Dùng trạng thái quyền, không dùng hoạt động làm tiêu chí duy nhất |
| Coi credential rotation là loại standing privilege | Báo thành công dù quyền không đổi | Tách metric credential và metric quyền |
| Loại break-glass hoặc ngoại lệ khỏi tổng một cách âm thầm | Làm số liệu thiếu phạm vi | Giữ trong tổng đã khai báo và phân nhóm riêng |
| Bỏ quyền ngay khi có yêu cầu revoke | Ghi giảm trước khi quyền mất hiệu lực | Xác nhận trạng thái sau thu hồi |
| Đổi capability catalog nhưng giữ baseline cũ | Tạo xu hướng giả | Phiên bản hóa và giải thích thay đổi |
| Coi mất connector là count bằng 0 | Biến lỗi thu thập thành thành tích | Gắn trạng thái dữ liệu thiếu, chặn so sánh sai |
| Trộn scope toàn tenant với scope một máy mà không phân nhóm | Count không thể hiện mức tác động | Báo độ rộng scope và mức quan trọng |
| Chỉ nhìn chênh lệch tổng | Bỏ qua quyền tăng và giảm bù nhau | Xem danh sách added/removed |

## 13. Bài thực hành với dữ liệu giả lập

Bạn quản lý PAM cho một môi trường production có dữ liệu sau:

- Lan có quyền quản trị scope `linux-prod` qua hai nhóm khác nhau.
- Lan có thêm quyền quản trị scope `database-prod`.
- Một workload có quyền triển khai scope `api-prod` được duy trì liên tục.
- Một tài khoản break-glass có quyền quản trị scope `platform-prod`.
- Minh có grant JIT hợp lệ cho `linux-prod` trong thời gian bảo trì.
- Huy chỉ có eligible role chưa kích hoạt cho `database-prod`.
- Một nguồn IAM khác chưa cung cấp được dữ liệu đúng hạn.

Theo cùng đơn vị đếm của bài, trên **phần dữ liệu đã xác nhận**, kết quả là:

```text
Standing entitlement count = 4
Standing privileged identity count = 3

Lan: 2 entitlement.
Workload: 1 entitlement.
Break-glass: 1 entitlement.
```

Hai nhóm của Lan cùng cấp một capability trên cùng scope `linux-prod`, nên chỉ tạo một entitlement cho scope đó. Grant JIT của Minh và eligible role của Huy được theo dõi riêng.

Tuy nhiên, không được công bố “toàn bộ production chỉ còn 4 standing entitlement” vì còn một nguồn thiếu dữ liệu. Cần ghi số 4 là số đã xác nhận trong tập nguồn hiện có, kèm trạng thái độ phủ chưa đầy đủ.

Nếu xóa một trong hai membership của Lan:

```text
Standing entitlement count vẫn là 4.
Standing privileged identity count vẫn là 3.
Số đường cấp quyền của Lan giảm, nhưng entitlement linux-prod vẫn tồn tại.
```

Nếu sau đó thu hồi đường còn lại tới `linux-prod` và xác nhận quyền mất hiệu lực:

```text
Standing entitlement count giảm từ 4 xuống 3.
Standing privileged identity count vẫn là 3.
```

Lan vẫn có standing privilege trên `database-prod`. Bài tập này cho thấy vì sao giảm số entitlement không nhất thiết làm giảm số danh tính đặc quyền.

Để hoàn tất bài thực hành, hãy lập một bảng với các cột: chủ thể, scope, capability, các đường cấp, hiệu lực, chế độ truy cập, owner và bằng chứng. Sau đó thử thay một grant từ standing sang JIT, một nguồn từ đầy đủ sang thiếu và một scope từ tài nguyên đơn lẻ sang toàn tenant. Với mỗi thay đổi, giải thích count nào đổi, count nào giữ nguyên và giới hạn diễn giải.

## 14. Những điểm cần nhớ

Standing privilege count chỉ có ý nghĩa khi ghi rõ **đếm cái gì, trong phạm vi nào, tại thời điểm nào và dựa trên dữ liệu đầy đủ tới đâu**.

Trong hợp đồng của bài, entitlement được đếm theo bộ ba danh tính–scope–capability có hiệu lực; nhiều đường cấp trùng không tạo thêm entitlement. Số danh tính có standing privilege là chỉ số đồng hành, không phải tên khác của cùng một đại lượng.

Giảm quyền thường trực cần được xác nhận bằng trạng thái sau thay đổi. Vault, rotation, ticket thu hồi và thời hạn credential là các dữ kiện liên quan nhưng không tự chứng minh quyền thường trực đã bị loại bỏ.

Khi dùng metric để điều hành PAM, hãy đọc số đếm cùng độ rộng scope, tài sản quan trọng, loại danh tính, ngoại lệ và chất lượng dữ liệu. Mục tiêu là giảm quyền duy trì sẵn không cần thiết trong khi vẫn giữ khả năng vận hành được kiểm soát và có bằng chứng.
