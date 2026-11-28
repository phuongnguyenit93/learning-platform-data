# Access review completion trong PAM

## 1. Chỉ số này trả lời điều gì?

**Access review completion** là mức độ hoàn tất việc rà soát các quyền truy cập nằm trong một phạm vi đã xác định. Trong quản lý truy cập đặc quyền (PAM), phạm vi đó có thể là quyền quản trị máy chủ, quyền sử dụng tài khoản dùng chung qua vault, vai trò quản trị cơ sở dữ liệu, quyền kích hoạt JIT hoặc quyền vận hành một tài khoản dịch vụ.

Một chiến dịch access review thường yêu cầu người có thẩm quyền trả lời: **chủ thể này có còn cần quyền này trên tài nguyên này, với phạm vi và thời hạn hiện tại hay không?**

Tỷ lệ hoàn tất giúp người quản lý nhận biết tiến độ ra quyết định. Nó không tự chứng minh rằng quyết định đúng, quyền thừa đã được gỡ bỏ hay hệ thống đã tuân thủ mọi yêu cầu kiểm toán.

Ví dụ, một chiến dịch có 200 mục cần rà soát và đã có 150 quyết định hợp lệ:

```text
Decision completion = 150 / 200 × 100% = 75%
```

Con số 75% chưa cho biết:

- Bao nhiêu quyết định được đưa ra trước hạn.
- Người duyệt có đủ thẩm quyền và bằng chứng hay chỉ bấm chấp thuận hàng loạt.
- Các quyền bị yêu cầu thu hồi đã thực sự biến mất ở hệ thống đích hay chưa.
- Những tài khoản chưa được kiểm kê có bị bỏ ngoài chiến dịch hay không.

Do đó, trong bài này, **completion mặc định là hoàn tất quyết định rà soát hợp lệ**. Việc xử lý thay đổi quyền được đo riêng bằng remediation completion và tỷ lệ đóng toàn bộ vòng đời. Tổ chức có thể chọn định nghĩa khác, nhưng phải ghi rõ trong hợp đồng chỉ số và dùng nhất quán.

## 2. Xác định đơn vị đếm trước khi đặt mục tiêu

### 2.1. Không mặc định một tài khoản bằng một mục rà soát

Một tài khoản có thể có nhiều quyền trên nhiều hệ thống. Nếu chỉ đếm tài khoản, việc duyệt một quyền có thể vô tình làm toàn bộ tài khoản trông như đã hoàn tất.

Một mục rà soát đặc quyền nên gắn với một đối tượng đủ cụ thể, chẳng hạn:

```text
Chiến dịch
  + chủ thể hoặc bên chịu trách nhiệm
  + tài khoản / danh tính
  + quyền hoặc vai trò
  + tài nguyên đích
  + phạm vi áp dụng của quyền
```

Đây là mô hình tham khảo, không phải khóa bắt buộc cho mọi nền tảng. Tổ chức cần điều chỉnh theo cách cấp quyền thực tế và tạo một `review_item_id` ổn định cho từng mục.

Ví dụ:

| Mục | Danh tính | Quyền được rà soát | Hệ thống đích | Nội dung cần quyết định |
|---|---|---|---|---|
| R-101 | Nhân sự vận hành A | Quyền sử dụng tài khoản quản trị qua vault | Cụm máy chủ sản xuất | Có còn cần quyền sử dụng tài khoản không? |
| R-102 | Nhân sự vận hành A | Quyền kích hoạt vai trò JIT | Cơ sở dữ liệu sản xuất | Phạm vi, điều kiện và thời hạn có còn phù hợp không? |
| R-103 | Tài khoản dịch vụ B | Vai trò quản trị ứng dụng | Hệ thống tích hợp | Ứng dụng có cần toàn bộ vai trò này không? |
| R-104 | Nhóm nhà cung cấp C | Quyền mở phiên đặc quyền | Thiết bị mạng | Hợp đồng và cửa sổ hỗ trợ còn hiệu lực không? |

R-101 hoàn tất không làm R-102 hoàn tất. Với tài khoản dịch vụ, việc không có một cá nhân đăng nhập trực tiếp không loại bỏ trách nhiệm rà soát; chủ ứng dụng hoặc chủ dịch vụ cần chịu trách nhiệm phù hợp.

### 2.2. Quyền qua nhóm, quyền JIT và tài khoản dùng chung

Cách đếm phải phản ánh con đường thực tế dẫn đến đặc quyền:

- **Quyền qua nhóm:** xác định đang rà soát thành viên nhóm, việc gán vai trò cho nhóm hay cả hai lớp. Không cộng hai lớp thành một mẫu số mơ hồ.
- **JIT:** rà soát điều kiện đủ để yêu cầu hoặc kích hoạt quyền, phạm vi được phép và chính sách phê duyệt. Không coi mỗi lần kích hoạt là một mục access review định kỳ nếu chiến dịch không được thiết kế như vậy.
- **Tài khoản dùng chung:** rà soát cả bên có quyền sử dụng tài khoản và trách nhiệm sở hữu tài khoản theo phạm vi chiến dịch. Không lấy số credential trong vault thay cho số người có quyền sử dụng.
- **Tài khoản dịch vụ:** rà soát nhu cầu nghiệp vụ, owner, quyền thực tế và phụ thuộc ứng dụng. Credential đã được luân chuyển không có nghĩa quyền đã được rà soát.
- **Quyền thừa kế:** ghi rõ phạm vi và chuỗi thừa kế để người duyệt không chấp thuận một nhãn vai trò mà không hiểu tài nguyên bị ảnh hưởng.

Đơn vị đếm phải đủ chi tiết để tạo hành động sửa đổi, nhưng không chia nhỏ tùy tiện nhằm làm đẹp tỷ lệ.

## 3. Xây dựng mẫu số có thể giải trình

### 3.1. Chốt phạm vi chiến dịch

Trước khi phát hành yêu cầu rà soát, cần xác định:

1. Các môi trường, tài nguyên, loại tài khoản và loại quyền nằm trong phạm vi.
2. Nguồn kiểm kê: IAM, thư mục, vault, hệ thống JIT và trạng thái quyền tại đích.
3. Mốc chụp dữ liệu, múi giờ, thời hạn và chính sách áp dụng.
4. Quy tắc khử trùng lặp và nhận diện đối tượng.
5. Người chịu trách nhiệm quyết định, quy trình chuyển giao và xử lý thiếu owner.
6. Điều kiện để quyết định được tính là hợp lệ.
7. Cách xử lý quyền phát sinh, bị thay đổi hoặc biến mất trong khi chiến dịch đang chạy.

Nếu phạm vi chỉ gồm tài khoản trong vault, dashboard phải ghi rõ điều đó. Không đổi tên thành “toàn bộ đặc quyền doanh nghiệp” khi chưa đối soát với nguồn phát hiện quyền ngoài PAM.

### 3.2. Mẫu số cố định và mẫu số động

Có hai cách triển khai thường gặp:

| Cách đo | Đặc điểm | Điểm cần kiểm soát |
|---|---|---|
| Chiến dịch theo snapshot | Danh sách đủ điều kiện được chốt tại một mốc | Theo dõi quyền mới bằng luồng bổ sung; không âm thầm xóa mục khó xử lý |
| Rà soát liên tục | Mục được thêm theo sự kiện, tuổi quyền hoặc hạn định kỳ | Cố định quy tắc chọn cohort và công bố số mục vào/ra mỗi kỳ |

Với chiến dịch snapshot, việc chuyển reviewer không làm giảm mẫu số. Một mục bị chặn vì thiếu dữ liệu vẫn cần được giải quyết; nó không tự trở thành ngoài phạm vi.

Nếu phát hiện bản ghi trùng, quyền đã bị xóa trước mốc chụp hoặc tài nguyên bị đưa vào nhầm, có thể hiệu chỉnh phạm vi theo quy trình được phê duyệt. Phải giữ dấu vết trước/sau và lý do, không sửa hồi tố số liệu mà không thông báo.

Một bản ghi “quyền đã biến mất” cũng cần được xác minh tại đích. Tùy chính sách, nó có thể được đóng với kết quả xác minh đã gỡ hoặc được ghi nhận là hiệu chỉnh phạm vi. Hai cách này không được trộn lẫn tùy tiện trong cùng chuỗi thời gian.

### 3.3. Chỉ đếm các mục đến hạn khi báo cáo quá hạn

Tại thời điểm báo cáo `T`, đặt:

```text
E(T) = tập mục hợp lệ, thuộc phạm vi và đã đến hạn tại T
C(T) = tập mục trong E(T) có quyết định hợp lệ tại T

Decision completion(T) = |C(T)| / |E(T)| × 100%
```

Mẫu số này phù hợp để báo cáo tình trạng các mục đã đến hạn. Nếu muốn theo dõi tiến độ cả chiến dịch trước hạn, sử dụng toàn bộ tập đủ điều kiện của chiến dịch và đặt tên riêng, ví dụ `campaign_progress`.

Không so sánh trực tiếp hai dashboard khi một bên dùng tất cả mục được giao và bên còn lại chỉ dùng các mục đến hạn.

Khi mẫu số bằng 0, trả về **N/A — không có mục đủ điều kiện**, không tự trả 100%. Cần phân biệt “không có việc phải làm” với “đã hoàn tất toàn bộ việc phải làm”.

## 4. Một quyết định hợp lệ gồm những gì?

### 4.1. Không chỉ là một nút bấm

Để tính vào tử số, một mục cần đáp ứng điều kiện mà tổ chức đã công bố. Ví dụ:

- Đối tượng rà soát được nhận diện rõ và không bị nhầm phiên bản quyền.
- Reviewer được phân công hợp lệ và có thẩm quyền theo chính sách.
- Có kết luận rõ: giữ quyền, thu hồi hoặc giảm/thay đổi phạm vi.
- Có căn cứ đáp ứng chính sách, chẳng hạn nhu cầu công việc, chủ ứng dụng xác nhận hoặc ngoại lệ được phê duyệt.
- Hoàn tất các lớp duyệt bắt buộc, nếu chính sách yêu cầu nhiều người.
- Có thời điểm hoàn tất và bằng chứng đủ để truy vết.
- Không còn yêu cầu bổ sung thông tin hay trạng thái quyết định bị vô hiệu hóa.

Đối với một hệ thống có hai lớp duyệt bắt buộc, người quản lý đã duyệt nhưng chủ tài nguyên chưa duyệt thì mục đó chưa hoàn tất. Không tính từng thao tác duyệt như các mục độc lập.

### 4.2. Mô hình trạng thái tham khảo

```text
Chưa giao / Thiếu owner
          ↓
       Đã giao
          ↓
      Đang rà soát
          ↓
   Cần bổ sung dữ liệu ───→ Quay lại rà soát
          ↓
   Quyết định hợp lệ
       ├─ Giữ quyền ───────────────→ Đóng theo chính sách
       ├─ Thu hồi ─→ Thực thi ─→ Xác minh tại đích ─→ Đóng
       └─ Giảm quyền → Thực thi → Xác minh tại đích → Đóng
```

“Quyết định hợp lệ” và “đóng” là hai mốc khác nhau. Với quyết định giữ quyền, có thể không có thay đổi kỹ thuật cần triển khai; việc đóng vẫn phải đáp ứng các điều kiện còn lại của chính sách.

Một ngoại lệ được phê duyệt có thể là cơ sở giữ quyền có điều kiện nếu chính sách cho phép và đã hoàn tất quy trình duyệt. Khi đó phải gắn ngày hết hạn, owner và điều kiện kiểm soát. Một yêu cầu xin ngoại lệ đang chờ duyệt không phải quyết định hoàn tất.

### 4.3. Các trường hợp không được tính hoàn tất

| Tình huống | Cách ghi nhận trong mô hình của bài |
|---|---|
| Reviewer mở màn hình hoặc đọc email nhắc việc | Chưa hoàn tất |
| Reviewer chuyển mục cho người khác | Chưa hoàn tất; vẫn thuộc mẫu số |
| Đã chọn “giữ” nhưng thiếu lớp duyệt bắt buộc | Chưa có quyết định hợp lệ |
| Thiếu owner hoặc không xác định được quyền hiệu lực | Bị chặn; không loại khỏi mẫu số chỉ vì khó xử lý |
| Đã quyết định thu hồi nhưng hệ thống đích vẫn còn quyền | Hoàn tất quyết định; remediation và đóng vòng đời chưa hoàn tất |
| Đã quyết định giảm quyền nhưng API chỉ báo tiếp nhận yêu cầu | Chưa xác minh remediation |
| Ngoại lệ đang xin phê duyệt | Chưa hoàn tất |
| Quyết định cũ bị mở lại do dữ liệu sai | Không tiếp tục tính là quyết định hợp lệ ở trạng thái hiện tại |

Nếu dashboard dùng một trạng thái duy nhất tên `DONE`, rất dễ làm lẫn các tình huống trên. Nên lưu riêng trạng thái quyết định, trạng thái remediation và trạng thái đóng.

## 5. Bộ chỉ số đi kèm

### 5.1. Tỷ lệ hoàn tất quyết định

```text
Decision completion
  = số mục có quyết định hợp lệ
    / số mục đủ điều kiện trong cohort
    × 100%
```

Giữ quyền, thu hồi và giảm quyền đều có thể là quyết định hợp lệ. Tỷ lệ chỉ phản ánh hoàn tất quy trình quyết định, không đánh giá một loại kết luận là “tốt hơn” loại khác.

### 5.2. Tỷ lệ hoàn tất đúng hạn

```text
On-time decision completion
  = số mục có quyết định hợp lệ hoàn tất không muộn hơn hạn của mục
    / số mục đủ điều kiện đã đến hạn
    × 100%
```

Mẫu số là toàn bộ mục đến hạn, không chỉ các mục đã hoàn tất. Nếu chia số quyết định đúng hạn cho số quyết định đã hoàn tất, đó là một tỷ lệ khác và có thể che giấu nhiều mục chưa được xử lý.

Một quyết định hoàn tất sau hạn làm tăng completion hiện tại nhưng không được đổi thành đúng hạn. Nếu thời hạn được gia hạn, cần lưu hạn ban đầu và hạn mới để báo cáo cả hiệu quả theo cam kết ban đầu lẫn tiến độ theo thời hạn được phê duyệt.

### 5.3. Remediation completion

```text
Remediation completion
  = số mục cần sửa quyền đã thực thi và xác minh đạt yêu cầu
    / số mục có quyết định hợp lệ yêu cầu sửa quyền
    × 100%
```

Cohort và thời điểm tính phải được công bố. Trong chiến dịch snapshot, có thể báo cáo toàn bộ quyết định sửa quyền hiện tại; để đánh giá SLA xử lý, dùng riêng các hành động remediation đã đến hạn.

Thu hồi quyền trong PAM không luôn tương đương xóa tài khoản. Hành động có thể là gỡ thành viên nhóm, bỏ quyền checkout, gỡ vai trò tại đích, hạ phạm vi JIT hoặc chấm dứt quyền của nhà cung cấp. Cần xác minh đúng đường truy cập đã bị loại bỏ.

### 5.4. Tỷ lệ đóng toàn bộ vòng đời

```text
End-to-end closure
  = số mục có quyết định hợp lệ và đã đáp ứng điều kiện đóng
    / số mục đủ điều kiện trong cohort
    × 100%
```

Đối với mục giữ quyền, điều kiện đóng có thể gồm hoàn tất bằng chứng và các lớp phê duyệt. Đối với mục thu hồi/giảm quyền, cần thêm bằng chứng thực thi thành công và xác minh tại đích.

Nếu tổ chức đặt tên “access review completion” cho chỉ số đóng toàn bộ vòng đời, phải mô tả rõ điều đó; không ghép số của mô hình này với số chỉ tính quyết định.

### 5.5. Backlog, tuổi tồn và mức độ quan trọng

Bên cạnh tỷ lệ, nên hiển thị số lượng tuyệt đối:

- Mục đến hạn nhưng chưa có quyết định hợp lệ.
- Mục bị chặn vì thiếu owner, dữ liệu hoặc xung đột reviewer.
- Mục có quyết định sửa quyền nhưng remediation chưa hoàn tất.
- Mục quá hạn theo các khoảng tuổi phù hợp, ví dụ 1–7 ngày, 8–30 ngày và trên 30 ngày.
- Mục bị mở lại, quyết định không hợp lệ hoặc bằng chứng không đủ.

Tuổi quá hạn được tính từ hạn của mục đến thời điểm báo cáo, chỉ áp dụng khi chưa đáp ứng mốc cần đo. Tuổi tồn remediation cần dùng hạn remediation riêng, không lấy hạn ra quyết định thay thế.

Có thể tính tỷ lệ theo trọng số rủi ro nếu trọng số được định nghĩa trước:

```text
Weighted completion = tổng trọng số mục hoàn tất / tổng trọng số mục đủ điều kiện
```

Không dùng tỷ lệ có trọng số để thay thế hoàn toàn số lượng thực. Một điểm trọng số tự đặt sau khi chiến dịch chạy có thể khiến số liệu mất khả năng so sánh.

## 6. Ví dụ đầy đủ: 75% quyết định nhưng chưa đóng 75%

Một chiến dịch rà soát quyền đặc quyền có dữ liệu nguồn ban đầu:

```text
240 bản ghi nguồn
  - 20 bản ghi trùng được xác nhận
  = 220 mục duy nhất
  - 20 mục ngoài phạm vi được phê duyệt trước khi chốt
  = 200 mục đủ điều kiện
```

Cohort 200 mục đã được chốt. Tại thời điểm báo cáo, tất cả đều đã đến hạn. Trong chiến dịch có 12 lượt đổi reviewer, nhưng việc đổi reviewer không tạo thêm mục và không làm giảm mẫu số.

Kết quả hiện tại:

| Kết quả | Số mục |
|---|---:|
| Quyết định giữ quyền hợp lệ | 110 |
| Quyết định thu hồi hợp lệ | 30 |
| Quyết định giảm quyền hợp lệ | 10 |
| Chưa có quyết định hợp lệ | 50 |
| **Tổng** | **200** |

Trong 150 quyết định hợp lệ, 130 hoàn tất trước hoặc đúng hạn và 20 hoàn tất muộn. Trong 50 mục chưa hoàn tất, có 8 mục đang thiếu thông tin owner; 8 mục này vẫn nằm trong mẫu số 200.

Về remediation:

| Nhóm cần thay đổi | Cần xử lý | Đã thực thi và xác minh | Chưa xác minh hoàn tất |
|---|---:|---:|---:|
| Thu hồi | 30 | 22 | 8 |
| Giảm quyền | 10 | 7 | 3 |
| **Tổng** | **40** | **29** | **11** |

Giả sử toàn bộ 110 mục giữ quyền đã đáp ứng điều kiện đóng, còn 29 mục sửa quyền đã được xác minh và đóng, ta có:

```text
Decision completion        = 150 / 200 = 75,0%
On-time decision completion = 130 / 200 = 65,0%
Remediation completion     = 29 / 40   = 72,5%
End-to-end closure         = 139 / 200 = 69,5%

Backlog quyết định         = 50 mục
Backlog remediation        = 11 mục
```

Hai backlog ở đây thuộc hai giai đoạn khác nhau. Các mục chưa có quyết định chưa được tính vào nhóm 40 mục đã có quyết định yêu cầu sửa quyền.

Nếu báo cáo “75% đã an toàn”, người đọc có thể hiểu sai rằng các quyền cần thu hồi đã được gỡ tương ứng. Báo cáo phù hợp hơn là:

> Chiến dịch đã hoàn tất quyết định cho 150/200 mục; 130/200 mục được quyết định đúng hạn. Có 11 mục đã được yêu cầu sửa quyền nhưng chưa xác minh hoàn tất. Tổng cộng 139/200 mục đã đóng toàn bộ vòng đời.

Việc giữ số đếm cùng tỷ lệ làm rõ quy mô công việc còn lại và giảm hiểu lầm do làm tròn.

## 7. Thiết kế dữ liệu và phép tính có thể tái tạo

### 7.1. Dữ liệu tối thiểu

Một bản ghi phục vụ tổng hợp có thể gồm:

| Nhóm | Trường minh họa | Mục đích |
|---|---|---|
| Định danh | campaign_id, review_item_id, assignment_snapshot_key | Tránh đếm trùng, nối đúng snapshot |
| Phạm vi | target_id, environment, entitlement_id, risk_tier | Phân tích nơi quyền được áp dụng |
| Trách nhiệm | owner_id, reviewer_id, reviewer_role | Xác định trách nhiệm và thẩm quyền |
| Thời hạn | snapshot_at, due_at, original_due_at | Tính cohort và đúng hạn |
| Quyết định | decision, decision_valid, decision_completed_at | Xác định tử số |
| Sửa quyền | remediation_required, remediation_due_at, target_verified_at | Tách quyết định và thực thi |
| Đóng | closed_at, closure_valid | Đo toàn bộ vòng đời |
| Bằng chứng | policy_version, evidence_ref, event_version | Truy vết và tái tạo |

`assignment_snapshot_key` cần giữ ổn định theo mục quyền trong snapshot. Không dùng reviewer hiện tại trong khóa định danh, vì đổi người duyệt không được tạo bản sao của cùng một mục.

Không đặt mật khẩu, private key, token hoặc credential thô vào bằng chứng. Dùng tham chiếu tới kho bằng chứng có kiểm soát truy cập; dữ liệu danh tính trên dashboard cũng cần được giới hạn theo vai trò.

### 7.2. Ví dụ SQL tổng hợp

Ví dụ dưới đây dùng cú pháp gần PostgreSQL và giả định bảng `review_item_as_of` là **trạng thái hợp lệ tại thời điểm báo cáo**, mỗi `review_item_id` chỉ có một dòng cho một chiến dịch. Đây là mô hình minh họa; tên trường và cú pháp tham số phụ thuộc hệ thống thực tế.

```sql
WITH due_items AS (
    SELECT review_item_id,
           due_at,
           decision_valid,
           decision_completed_at,
           remediation_required,
           target_verified_at,
           closure_valid,
           closed_at
    FROM review_item_as_of
    WHERE campaign_id = :campaign_id
      AND eligible = TRUE
      AND due_at <= :as_of
),
counts AS (
    SELECT COUNT(*) AS due_count,
           COUNT(*) FILTER (
               WHERE decision_valid = TRUE
                 AND decision_completed_at IS NOT NULL
                 AND decision_completed_at <= :as_of
           ) AS decided_count,
           COUNT(*) FILTER (
               WHERE decision_valid = TRUE
                 AND decision_completed_at IS NOT NULL
                 AND decision_completed_at <= due_at
           ) AS on_time_count,
           COUNT(*) FILTER (
               WHERE decision_valid = TRUE
                 AND decision_completed_at <= :as_of
                 AND remediation_required = TRUE
           ) AS remediation_count,
           COUNT(*) FILTER (
               WHERE decision_valid = TRUE
                 AND decision_completed_at <= :as_of
                 AND remediation_required = TRUE
                 AND target_verified_at IS NOT NULL
                 AND target_verified_at <= :as_of
           ) AS remediated_count,
           COUNT(*) FILTER (
               WHERE decision_valid = TRUE
                 AND decision_completed_at <= :as_of
                 AND closure_valid = TRUE
                 AND closed_at IS NOT NULL
                 AND closed_at <= :as_of
           ) AS closed_count
    FROM due_items
)
SELECT due_count,
       decided_count,
       on_time_count,
       remediation_count,
       remediated_count,
       closed_count,
       ROUND(100.0 * decided_count
             / NULLIF(due_count, 0), 2) AS decision_completion_pct,
       ROUND(100.0 * on_time_count
             / NULLIF(due_count, 0), 2) AS on_time_completion_pct,
       ROUND(100.0 * remediated_count
             / NULLIF(remediation_count, 0), 2) AS remediation_completion_pct,
       ROUND(100.0 * closed_count
             / NULLIF(due_count, 0), 2) AS end_to_end_closure_pct
FROM counts;
```

Trong ví dụ này, remediation cũng bị giới hạn trong cohort các mục rà soát đã đến hạn. Nếu cần báo cáo toàn bộ remediation đang đến hạn theo SLA riêng, tạo cohort remediation riêng và ghi rõ sự khác biệt.

Phép tính chỉ đáng tin nếu lớp dữ liệu đầu vào bảo đảm:

- Quyết định đã hoàn tất các lớp duyệt bắt buộc trước khi đặt `decision_valid = TRUE`.
- `target_verified_at` chỉ được đặt sau khi đối soát trạng thái quyền đạt yêu cầu, không phải ngay khi gửi lệnh.
- `closure_valid` kiểm tra đầy đủ điều kiện đóng, không phải cờ được bật bằng tay để tăng tỷ lệ.
- Các timestamp được chuẩn hóa và không lấy trạng thái phát sinh sau `:as_of`.
- Không có nhiều dòng cho cùng một mục do join lịch sử phê duyệt hoặc remediation.

Nếu join một mục với ba sự kiện duyệt rồi dùng `COUNT(*)`, mẫu số có thể tăng từ một thành ba. Cách khắc phục là dựng trạng thái chuẩn một dòng/mục trước khi tổng hợp, không chỉ thêm `DISTINCT` ở cuối để che lỗi mô hình.

### 7.3. Báo cáo tại một thời điểm trong quá khứ

Bảng trạng thái hiện tại không đủ để trả lời chính xác “ngày cuối tháng trước đã hoàn tất bao nhiêu mục?” nếu sau đó có mục được mở lại, sửa quyết định hoặc đổi hạn.

Có thể dùng snapshot định kỳ hoặc lịch sử sự kiện có phiên bản. Khi tái tạo báo cáo, chỉ chọn phiên bản đã có hiệu lực tại thời điểm cần báo cáo, đồng thời giữ được thời điểm hệ thống ghi nhận.

Ví dụ một người duyệt quyết định ngày 28 nhưng sự kiện chỉ được nhập ngày 31:

- Báo cáo theo thời điểm nghiệp vụ cần quy tắc chấp nhận thời gian quyết định và bằng chứng.
- Báo cáo “hệ thống đã biết gì tại ngày 30” cần xét cả thời điểm ghi nhận.
- Nếu bổ sung dữ liệu làm thay đổi báo cáo đã phát hành, cần công bố bản điều chỉnh thay vì thay số âm thầm.

Không tin timestamp do client tự gửi để xác nhận đúng hạn nếu thiếu cơ chế xác thực và kiểm soát phù hợp.

## 8. Dashboard có thể dẫn tới hành động

### 8.1. Những nội dung nên hiển thị

Một dashboard vận hành nên trả lời được: còn bao nhiêu mục, rủi ro nằm ở đâu và ai cần xử lý.

Ví dụ cho chiến dịch ở phần trên:

```text
Phạm vi: đặc quyền sản xuất trong snapshot chiến dịch C-45
Mốc báo cáo: thời điểm đã công bố, kèm múi giờ

Quyết định hợp lệ:           150 / 200  (75,0%)
Quyết định đúng hạn:         130 / 200  (65,0%)
Đóng toàn bộ vòng đời:       139 / 200  (69,5%)
Sửa quyền đã xác minh:        29 / 40   (72,5%)

Chưa có quyết định:           50
  Trong đó thiếu thông tin owner: 8
Sửa quyền chưa xác minh xong: 11
```

Các lát cắt hữu ích gồm môi trường, chủ tài nguyên, loại tài khoản, mức rủi ro, reviewer và tuổi quá hạn. Chỉ đưa thông tin chi tiết danh tính cho người có quyền xem.

### 8.2. Tránh trung bình cộng tỷ lệ giữa các nhóm

Giả sử:

| Nhóm | Hoàn tất | Tổng mục | Tỷ lệ |
|---|---:|---:|---:|
| A | 9 | 10 | 90% |
| B | 50 | 100 | 50% |

Tỷ lệ toàn phạm vi là:

```text
(9 + 50) / (10 + 100) = 59 / 110 ≈ 53,64%
```

Không lấy `(90% + 50%) / 2 = 70%` làm tỷ lệ hoàn tất chung. Trung bình đó cho một nhóm 10 mục trọng lượng ngang với nhóm 100 mục.

Khi tổng hợp nhiều chiến dịch, cần xác định đang đếm “lần rà soát theo chiến dịch” hay “quyền duy nhất”. Cùng một quyền xuất hiện ở hai kỳ định kỳ có thể là hai nghĩa vụ rà soát hợp lệ, nhưng không phải hai quyền khác nhau.

### 8.3. Phân tích rủi ro phía sau một tỷ lệ cao

Một module PAM có thể đạt 98% completion, nhưng 2% còn lại chứa toàn bộ quyền quản trị cấp cao hoặc tài khoản khẩn cấp của môi trường quan trọng.

Vì vậy, báo cáo tổng cần đi kèm:

- Số mục quá hạn thuộc nhóm rủi ro cao.
- Backlog quyền của người đã nghỉ việc hoặc nhà cung cấp hết hợp đồng.
- Backlog tài khoản dịch vụ không có owner.
- Quyền thu hồi thất bại hoặc còn đường truy cập thay thế.
- Nhóm tài nguyên chưa có dữ liệu kiểm kê đáng tin.

Mục tiêu theo mức rủi ro, thời hạn và ngưỡng cảnh báo do tổ chức xác định. Các con số minh họa trong bài không phải yêu cầu pháp lý hay ngưỡng phù hợp chung cho mọi hệ thống.

## 9. Vận hành chiến dịch và xử lý ngoại lệ

### 9.1. Trước khi mở chiến dịch

Đối soát nguồn để phát hiện quyền ngoài PAM, tài khoản mồ côi và owner không còn phù hợp. Xác nhận reviewer có đủ thông tin về quyền hiệu lực, lịch sử sử dụng liên quan và nhu cầu nghiệp vụ.

Việc không có hoạt động gần đây là tín hiệu để xem xét, không phải bằng chứng duy nhất rằng quyền không cần thiết. Quyền khẩn cấp hoặc tác vụ bảo trì theo chu kỳ dài có thể ít được dùng nhưng vẫn cần cơ sở giữ quyền và kiểm soát riêng.

Nên kiểm tra khả năng thực thi quyết định thu hồi/giảm quyền trước khi chiến dịch bắt đầu. Một quy trình duyệt nhanh nhưng không có kênh thực thi sẽ chuyển backlog từ quyết định sang remediation.

### 9.2. Trong khi chiến dịch chạy

Nhắc việc theo mức độ quan trọng và thời gian còn lại. Đưa mục thiếu owner vào luồng phân công có trách nhiệm, thay vì để reviewer bất kỳ tự chấp thuận cho xong.

Khi người duyệt nghỉ phép hoặc chuyển công tác, ghi nhận chuyển giao, giữ định danh mục và lịch sử trách nhiệm. Không tạo mục mới với hạn mới chỉ để loại bỏ quá hạn của mục cũ.

Với quyền rủi ro cao, có thể cần ưu tiên xử lý hoặc áp dụng biện pháp hạn chế theo chính sách đã được phê duyệt. Không tự động thu hồi mọi quyền quá hạn nếu chưa đánh giá phụ thuộc ứng dụng và cơ chế phục hồi phù hợp.

### 9.3. Sau quyết định

Đội thực thi cần nhận được hành động cụ thể, không chỉ một nhãn “reject”. Ví dụ:

```text
Mục R-103:
- Gỡ vai trò quản trị toàn bộ khỏi tài khoản dịch vụ.
- Thay bằng quyền thực hiện tác vụ cần thiết theo phạm vi đã duyệt.
- Kiểm tra quyền hiệu lực tại hệ thống đích.
- Xác nhận ứng dụng vẫn thực hiện được tác vụ được phép.
- Lưu bằng chứng thay đổi và kết quả xác minh.
```

Việc kiểm tra chức năng không thay thế kiểm tra quyền, và ngược lại. Remediation đạt yêu cầu cần bảo đảm trạng thái quyền đúng với quyết định; thay đổi ứng dụng đi kèm cần có quy trình quản lý riêng.

Nếu thực thi thất bại, giữ mục mở ở giai đoạn remediation, ghi lý do, người xử lý và thời hạn. Không đổi kết luận thành “giữ quyền” chỉ để đóng ticket.

### 9.4. Kết thúc chiến dịch

Khi đóng chiến dịch, lưu báo cáo phạm vi, kết quả, số mục còn mở và các ngoại lệ được phê duyệt. Nếu còn mục tồn được chuyển sang luồng theo dõi khác, phải giữ liên kết để tránh mất trách nhiệm.

Chiến dịch được kết thúc về mặt lịch vận hành không có nghĩa các nghĩa vụ tồn đọng đã biến mất. Báo cáo cần phản ánh điều đó rõ ràng.

## 10. Chất lượng rà soát và những cách số liệu bị làm đẹp

### 10.1. Completion cao nhưng kiểm soát yếu

Các dấu hiệu cần được xem xét trong hoạt động bảo đảm chất lượng:

- Reviewer chấp thuận rất nhiều mục trong thời gian quá ngắn so với thông tin cần đánh giá.
- Tất cả quyết định có cùng một lý do chung chung, không liên hệ với nhu cầu quyền.
- Quyền của người đã nghỉ việc vẫn được giữ lại.
- Một reviewer tự duyệt quyền của mình trái với chính sách.
- Tỷ lệ giữ quyền cao bất thường nhưng không có giải trình hoặc mẫu kiểm tra hỗ trợ.
- Nhiều quyết định bị mở lại sau khi đối soát quyền hiệu lực.
- Quyết định thu hồi đã tồn tại lâu nhưng quyền vẫn còn tại đích.

Những dấu hiệu này là đầu vào điều tra, không tự chứng minh gian lận hoặc sai phạm. Một tỷ lệ giữ quyền cao có thể hợp lý nếu việc cấp quyền trước đó đã được kiểm soát tốt.

Có thể bổ sung tỷ lệ mẫu rà soát đạt yêu cầu, số quyết định bị vô hiệu hóa, số mục mở lại và mức đầy đủ của bằng chứng. Công bố cỡ mẫu và cách chọn mẫu; không suy rộng vô điều kiện kết quả của vài mục sang toàn bộ chiến dịch.

### 10.2. Các sai lệch thường gặp

| Sai lệch | Hậu quả | Cách kiểm soát |
|---|---|---|
| Xóa mục chưa có owner khỏi chiến dịch | Tỷ lệ tăng nhưng rủi ro vẫn tồn tại | Giữ trong mẫu số, theo dõi luồng phân công |
| Dời hạn hàng loạt rồi chỉ báo cáo hạn mới | Quá hạn cũ biến mất | Lưu hạn ban đầu, công bố thay đổi |
| Tính mở email hoặc bấm xác nhận là hoàn tất | Tiến độ hình thức | Kiểm tra điều kiện quyết định hợp lệ |
| Đóng ngay sau khi gửi API thu hồi | Quyền tại đích có thể chưa đổi | Đối soát trạng thái thực tế |
| Tạo lại mục khi đổi reviewer | Đếm trùng hoặc mất tuổi tồn | Giữ ID mục ổn định |
| Chỉ đo quyền đã vào vault | Bỏ sót quyền ngoài kiểm soát | Đo coverage và chất lượng kiểm kê riêng |
| Gộp tỷ lệ các nhóm bằng trung bình cộng | Sai tỷ lệ chung | Cộng tử số và mẫu số đúng cohort |
| Bỏ mọi ngoại lệ khỏi báo cáo | Che khuất quyền giữ có điều kiện | Hiển thị số ngoại lệ, hạn và owner |
| Chỉ báo phần trăm | Không thấy quy mô tồn | Hiển thị cả số đếm |

Completion là chỉ số tiến độ. **Coverage** cho biết phạm vi đã được đưa vào rà soát so với quần thể cần kiểm soát; **decision quality** nói về chất lượng quyết định; **remediation** nói về thay đổi quyền. Bốn khía cạnh này hỗ trợ nhau nhưng không thay thế nhau.

## 11. Hợp đồng chỉ số mẫu

Có thể dùng bản mô tả sau khi triển khai dashboard:

```yaml
metric: pam_access_review_decision_completion
purpose: Theo dõi hoàn tất quyết định rà soát các mục đã đến hạn
unit: review_item
population:
  scope: Quyền đặc quyền thuộc snapshot chiến dịch được phê duyệt
  cohort: Mục đủ điều kiện có due_at không muộn hơn mốc báo cáo
numerator:
  rule: Quyết định hiện hành hợp lệ, hoàn tất trước hoặc tại mốc báo cáo
  outcomes:
    - retain
    - revoke
    - reduce
denominator:
  rule: Toàn bộ mục trong cohort, gồm mục bị chặn hoặc thiếu owner
zero_denominator: N_A
timestamps:
  storage: UTC
  display: Múi giờ được công bố cùng báo cáo
controls:
  - ID mục ổn định khi đổi reviewer
  - Lưu phiên bản chính sách và lịch sử hiệu chỉnh phạm vi
  - Tách completion khỏi remediation và closure
  - Không chứa credential trong bằng chứng
reporting:
  show_counts: true
  show_on_time: true
  show_overdue_by_risk: true
  show_remediation_backlog: true
```

Đây là cấu hình minh họa, không phải schema của một sản phẩm cụ thể. Khi áp dụng, cần bổ sung owner chỉ số, tần suất cập nhật, độ trễ dữ liệu, cách đối soát và quy trình sửa báo cáo.

Hợp đồng phải ổn định qua các kỳ. Nếu thay đổi định nghĩa, đánh dấu điểm thay đổi hoặc tính lại lịch sử theo cùng quy tắc trước khi so sánh xu hướng.

## 12. Bài tập thực hành

Một chiến dịch có 120 mục đủ điều kiện và tất cả đã đến hạn. Kết quả:

- 70 mục giữ quyền hợp lệ, đều đáp ứng điều kiện đóng.
- 20 mục thu hồi hợp lệ; đã xác minh thu hồi thành công 15 mục.
- 10 mục giảm quyền hợp lệ; đã xác minh hoàn tất 6 mục.
- 20 mục chưa có quyết định hợp lệ, trong đó 5 mục thiếu owner.
- Có 85 quyết định hợp lệ được hoàn tất trước hoặc đúng hạn.
- Không có quyết định bị mở lại và không có điều kiện đóng bổ sung chưa đáp ứng ở các mục đã xác minh.

Hãy xác định completion, on-time completion, remediation completion và end-to-end closure.

**Lời giải:**

```text
Quyết định hợp lệ = 70 + 20 + 10 = 100
Decision completion = 100 / 120 ≈ 83,33%

On-time completion = 85 / 120 ≈ 70,83%

Mục cần remediation = 20 + 10 = 30
Remediation hoàn tất = 15 + 6 = 21
Remediation completion = 21 / 30 = 70,00%

Mục đóng = 70 + 15 + 6 = 91
End-to-end closure = 91 / 120 ≈ 75,83%

Backlog quyết định = 20
Backlog remediation = 30 - 21 = 9
```

Năm mục thiếu owner nằm trong 20 mục chưa có quyết định và vẫn thuộc mẫu số 120. Không trừ chúng trước khi tính.

Nếu 5 mục thu hồi chưa xác minh vẫn có đặc quyền quản trị sản xuất, báo cáo cần nêu nhóm rủi ro này dù completion đã trên 80%. Hành động tiếp theo là giải quyết trách nhiệm rà soát của 20 mục và xử lý, xác minh 9 mục remediation còn lại theo mức độ quan trọng.

## 13. Những điểm cần ghi nhớ

Access review completion chỉ có ý nghĩa khi người đọc biết đang đếm mục nào, trong phạm vi nào, đến thời điểm nào và thế nào là quyết định hợp lệ.

Trong PAM, một quyết định thu hồi hoàn tất chưa đồng nghĩa quyền đã được gỡ bỏ. Theo dõi riêng quyết định, đúng hạn, remediation và đóng toàn bộ vòng đời giúp đội vận hành nhìn thấy công việc còn lại ở từng giai đoạn.

Luôn giữ số đếm cùng tỷ lệ, bảo toàn mẫu số có giải trình và đối soát quyền thực tế. Khi kết hợp với coverage, chất lượng quyết định và backlog theo rủi ro, chỉ số mới hỗ trợ được mục tiêu least privilege và trách nhiệm giải trình đối với đặc quyền.
