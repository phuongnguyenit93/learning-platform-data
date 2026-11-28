# JIT adoption: đo mức độ áp dụng quyền truy cập đặc quyền đúng lúc

## 1. JIT adoption trả lời câu hỏi nào?

Trong quản lý truy cập đặc quyền (Privileged Access Management — PAM), Just-in-Time (JIT) là cách cấp quyền phục vụ một nhu cầu cụ thể trong một khoảng thời gian giới hạn. Người vận hành hoặc workload chỉ được nâng quyền khi đáp ứng chính sách; quyền tạm thời được thu hồi khi hết hạn hoặc công việc kết thúc. JIT có thể được triển khai bằng membership tạm thời, role assignment có thời hạn, credential ngắn hạn hoặc cơ chế trung gian cấp phiên truy cập.

**JIT adoption** thể hiện mức độ các nhu cầu truy cập đặc quyền trong phạm vi đo lường đã thực sự chuyển sang cơ chế JIT. Đây là chỉ số về mức sử dụng một kiểm soát, không tự chứng minh rằng tổ chức đã đạt least privilege hoặc loại bỏ mọi đường truy cập ngoài PAM.

Một nhóm có thể gửi nhiều yêu cầu JIT nhưng tiếp tục dùng tài khoản quản trị thường trực. Một hệ thống cũng có thể cấp credential ngắn hạn trong khi role đích vẫn rộng hơn nhu cầu công việc. Vì vậy, báo cáo cần phân biệt ba câu hỏi:

1. Những đối tượng nào đã được đưa vào phạm vi có thể sử dụng JIT?
2. Trong các lần truy cập đặc quyền đủ điều kiện, bao nhiêu lần thực sự đi qua JIT?
3. Việc dùng JIT có làm giảm quyền thường trực và thời gian tồn tại quyền hay không?

Bài học này tập trung vào cách định nghĩa, tính toán và diễn giải JIT adoption trong chương Metrics của PAM. Các con số, tên hệ thống và ngưỡng trong ví dụ là dữ liệu minh họa, không phải chuẩn bắt buộc cho mọi tổ chức.

## 2. Phân biệt JIT với các khái niệm dễ nhầm

| Khái niệm | Ý nghĩa | Quan hệ với JIT adoption |
|---|---|---|
| JIT | Cấp quyền theo nhu cầu và giới hạn thời gian | Là cơ chế cần chứng minh đã được dùng |
| Just Enough Administration — JEA | Giới hạn thao tác hoặc khả năng quản trị phù hợp nhiệm vụ | Cần đo riêng; quyền có thời hạn vẫn có thể quá rộng |
| Credential rotation | Thay credential theo lịch hoặc sự kiện | Rotation không tự loại bỏ quyền thường trực của tài khoản |
| Vault checkout | Cho phép lấy hoặc sử dụng credential qua vault | Chỉ được tính JIT nếu đáp ứng hợp đồng JIT đã thống nhất |
| Session recording | Ghi nhận hoạt động trong phiên đặc quyền | Cung cấp bằng chứng sử dụng, không tự tạo ra quyền tạm thời |
| Standing privilege | Quyền đặc quyền tồn tại liên tục, không cần kích hoạt theo nhu cầu | Là đường truy cập cần xem xét khi đánh giá hiệu quả chuyển đổi |
| Break-glass | Truy cập khẩn cấp theo chính sách riêng | Phải hiển thị rõ khi đưa vào hoặc loại khỏi mẫu số |

Ví dụ, mật khẩu của một tài khoản quản trị được đổi mỗi ngày và mọi lượt checkout đều được ghi log. Nếu người dùng vẫn có thể đăng nhập bằng một đường khác hoặc tài khoản luôn có đặc quyền mà không bị giới hạn thời gian sử dụng, không thể tự động xem mọi checkout là một lần JIT thành công.

Ngược lại, tài khoản đích có thể luôn giữ quyền quản trị nhưng người dùng chỉ được tiếp cận thông qua một broker trong thời gian được phê duyệt. Cách triển khai này có thể được tổ chức công nhận là JIT ở lớp truy cập nếu broker thực sự kiểm soát và chấm dứt khả năng truy cập. Tuy nhiên, báo cáo phải tách rõ **JIT ở lớp truy cập** với **quyền tạm thời trên chính tài nguyên đích**. Không được dùng nhãn thứ nhất để kết luận rằng quyền thường trực của tài khoản đích đã biến mất.

## 3. Xác định phạm vi và đơn vị đo trước khi chọn công thức

### 3.1. Phạm vi đo lường

Một định nghĩa có thể kiểm tra được cần nêu rõ:

- Môi trường: production, staging, development hoặc toàn bộ hệ thống.
- Loại chủ thể: nhân sự nội bộ, vendor, service account, workload hoặc máy tự động.
- Loại tài nguyên: máy chủ, cơ sở dữ liệu, thiết bị mạng, nền tảng cloud hoặc control plane.
- Nhóm hành động đặc quyền: quản trị cấu hình, vận hành dịch vụ, triển khai hoặc xử lý sự cố.
- Kỳ báo cáo và múi giờ.
- Các trường hợp loại trừ, người phê duyệt và thời điểm hết hiệu lực của ngoại lệ.

Không so sánh trực tiếp một tháng chỉ đo máy chủ Linux production với tháng kế tiếp đo thêm cloud và vendor nếu chưa giải thích thay đổi phạm vi.

### 3.2. Đơn vị đo

Chỉ số có thể tính theo người dùng, tài khoản, tài nguyên, lần kích hoạt hoặc thời gian. Mỗi đơn vị trả lời một câu hỏi khác nhau.

| Đơn vị | Câu hỏi được trả lời | Giới hạn cần lưu ý |
|---|---|---|
| Người dùng đang hoạt động | Bao nhiêu người có nhu cầu đặc quyền đã dùng JIT? | Một lần dùng thử cũng có thể làm người đó được tính |
| Tài nguyên | Bao nhiêu tài nguyên trong phạm vi có ít nhất một lượt JIT? | Không phản ánh tần suất truy cập hay đường truy cập còn lại |
| Lần truy cập đặc quyền | Bao nhiêu nhu cầu truy cập đã thực hiện bằng JIT? | Phải chuẩn hóa cách đếm giữa phiên dài, API và retry |
| Lần cấp quyền | Bao nhiêu quyền tạm thời được kích hoạt? | Quyền được cấp có thể chưa bao giờ được sử dụng |
| Thời gian có quyền | Bao nhiêu thời gian tiếp xúc đặc quyền gắn với JIT? | Cần xử lý các khoảng thời gian chồng lấn và quyền thường trực |

Một báo cáo có thể sử dụng nhiều đơn vị nhưng phải đặt tên riêng. Không gộp tỷ lệ người dùng và tỷ lệ phiên vào cùng một đường xu hướng “adoption”.

### 3.3. “Lần truy cập” cần có định nghĩa ổn định

Trong ví dụ của bài, **một lần truy cập đặc quyền** là một hoạt động logic đã được xác nhận, gắn với một chủ thể, một tài nguyên và một ngữ cảnh công việc. Hệ thống có thể biểu diễn nó bằng một session hoặc một activation được sử dụng.

Một yêu cầu API bị retry năm lần không đương nhiên là năm nhu cầu truy cập. Ngược lại, không nên gộp nhiều công việc độc lập của nhiều chủ thể thành một “phiên” chỉ vì chúng dùng chung một tài khoản đích.

Nếu nền tảng chưa thể chuẩn hóa cùng một đơn vị cho mọi loại tài nguyên, hãy báo cáo theo từng nhóm và công bố giới hạn tổng hợp.

## 4. Định nghĩa thế nào là một lần JIT hợp lệ?

Cần có một hợp đồng dữ liệu thống nhất giữa đội PAM, đội IAM, chủ tài nguyên và đội phân tích. Với một loại JIT ở lớp quyền đích, một lần truy cập thường cần các bằng chứng sau:

1. Chủ thể thực đã được định danh và liên kết với tài khoản hoặc workload sử dụng quyền.
2. Có quyết định chính sách hợp lệ cho phạm vi tài nguyên và thao tác được yêu cầu. Quyết định có thể tự động; không bắt buộc mọi lượt đều có người phê duyệt.
3. Có thời điểm kích hoạt và thời điểm hết hạn hữu hạn.
4. Phạm vi quyền được cấp khớp với quyết định.
5. Hoạt động đặc quyền thực tế xảy ra trong khoảng quyền còn hiệu lực và liên kết được với lần cấp quyền.
6. Có bằng chứng quyền tạm thời kết thúc hoặc bị thu hồi theo cơ chế của hệ thống.
7. Các phiên, token hoặc credential còn sống sau thu hồi được xử lý theo chính sách đã định.

**Thu hồi role, kết thúc session và làm mất hiệu lực token là các sự kiện khác nhau.** Một role assignment đã bị xóa không bảo đảm mọi token đã phát hành lập tức hết tác dụng. Một session đã đóng cũng không chứng minh rằng một API credential khác không còn dùng được.

Để báo cáo kịp thời, nên tách hai trạng thái:

- **JIT đang hiệu lực hoặc chờ bằng chứng kết thúc:** đã xác nhận cấp quyền và sử dụng đúng hạn, nhưng vòng đời chưa đóng hoặc log kết thúc chưa đến.
- **JIT đã xác nhận vòng đời:** đã đối chiếu đủ bằng chứng cấp, sử dụng và kết thúc theo hợp đồng.

Báo cáo chính thức cần nêu dùng trạng thái nào trong tử số. Nếu công bố số tạm tính theo sự kiện sử dụng, phải có cơ chế cập nhật khi xuất hiện lỗi thu hồi. Nếu chỉ dùng vòng đời đã đóng, cần cửa sổ hoàn thiện dữ liệu để không đánh rớt các lượt JIT hợp lệ ở cuối kỳ.

## 5. Bộ chỉ số nên đi cùng nhau

### 5.1. Tỷ lệ áp dụng theo lần truy cập đủ điều kiện

Chọn tập D gồm các lần truy cập đặc quyền đã xác nhận, nằm trong phạm vi và thuộc nhóm có thể áp dụng JIT theo chính sách. Chọn tập J là các phần tử trong D đáp ứng hợp đồng JIT của báo cáo.

~~~text
JIT adoption theo lần truy cập (%)
  = số lần truy cập JIT hợp lệ trong D
    / tổng số lần truy cập đặc quyền trong D
    × 100
~~~

Mẫu số phải lấy từ hoạt động đặc quyền thực tế của cả đường JIT và đường ngoài JIT. Chỉ đếm log từ cổng PAM sẽ bỏ sót truy cập trực tiếp, làm tỷ lệ cao một cách giả tạo.

Nếu không có lần truy cập nào trong D, kết quả là **N/A — không có quan sát**, không phải 0% hoặc 100%.

### 5.2. Tỷ lệ JIT trên toàn bộ lần truy cập trong phạm vi

Một nhóm tài nguyên có thể được loại khỏi tập đủ điều kiện vì giới hạn kỹ thuật. Việc loại trừ giúp phản ánh công việc hiện tại nhưng cũng có thể làm tỷ lệ đẹp hơn khi phần khó nhất bị gạt ra ngoài.

Do đó nên công bố thêm:

~~~text
JIT share toàn phạm vi (%)
  = số lần truy cập JIT hợp lệ
    / mọi lần truy cập đặc quyền trong phạm vi đã xác nhận
    × 100
~~~

Tên chỉ số này nhấn mạnh mẫu số rộng hơn. Đi kèm là số lần truy cập ngoại lệ, lý do và kế hoạch xử lý. Hai tỷ lệ không thể thay thế nhau.

### 5.3. Mức bao phủ chủ thể đang hoạt động

~~~text
Active-principal JIT adoption (%)
  = số chủ thể đang hoạt động có ít nhất một lần dùng JIT hợp lệ
    / số chủ thể có truy cập đặc quyền đủ điều kiện trong kỳ
    × 100
~~~

Đây là chỉ số hỗ trợ thay đổi hành vi. Nó không cho biết người đã dùng JIT còn truy cập ngoài JIT bao nhiêu lần.

Có thể bổ sung tỷ lệ chủ thể **chỉ dùng JIT trong tập đủ điều kiện**, kèm số chủ thể vẫn có standing privilege. Không đưa tất cả nhân viên vào mẫu số nếu nhiều người không có nhu cầu truy cập đặc quyền.

### 5.4. Tỷ lệ sử dụng sau khi được cấp quyền

~~~text
JIT grant utilization (%)
  = số lần cấp JIT đã được sử dụng
    / số lần cấp JIT hợp lệ trong cohort
    × 100
~~~

Tỷ lệ thấp có thể cho thấy người dùng xin quyền trước để dự phòng, TTL không phù hợp hoặc quy trình phê duyệt chậm. Chỉ số này cũng có thể bị ảnh hưởng bởi log sử dụng chưa đầy đủ; cần kiểm tra dữ liệu trước khi kết luận về hành vi.

### 5.5. Tỷ lệ xác nhận kết thúc đúng hạn

~~~text
JIT termination confirmation (%)
  = số grant đến hạn có bằng chứng kết thúc đúng chính sách
    / tổng số grant đến hạn cần xác nhận
    × 100
~~~

Mẫu số ở đây là grant đến hạn, khác mẫu số theo lần truy cập. Phải nêu rõ thời gian đệm vận hành cho phép, cách xử lý sự kiện đến muộn và điều kiện kiểm chứng trên đích.

### 5.6. Standing privilege còn lại

Báo cáo số tài khoản hoặc quan hệ đặc quyền thường trực còn tồn tại, đặc biệt trên tài nguyên nhạy cảm. Một “quan hệ đặc quyền” có thể được định danh bằng bộ:

~~~text
(chủ thể, tài nguyên hoặc phạm vi, role hoặc entitlement)
~~~

Không chỉ đếm số nhóm IAM đã cấu hình vì một nhóm có thể cấp quyền cho nhiều tài nguyên. Phải kiểm tra cả quyền trực tiếp, quyền kế thừa, nested group và credential có khả năng truy cập ngoài PAM.

## 6. Ví dụ tính toán với dữ liệu đầy đủ

Một đội vận hành đo các lần truy cập production trong tháng. Đội đã thống nhất đơn vị đếm và đối chiếu log cổng PAM với log tài nguyên.

| Loại quan sát | Số lần | Trong tập đủ điều kiện? | JIT đã xác nhận vòng đời? |
|---|---:|---|---|
| JIT có đủ bằng chứng cấp, dùng và kết thúc | 720 | Có | Có |
| Truy cập bằng quyền thường trực | 120 | Có | Không |
| Truy cập trực tiếp bỏ qua luồng JIT | 60 | Có | Không |
| Dùng JIT nhưng chưa xác nhận kết thúc | 40 | Có | Chưa đủ bằng chứng |
| Hệ thống cũ có ngoại lệ kỹ thuật được duyệt | 60 | Không | Không |
| Tổng | 1.000 | 940 lần đủ điều kiện | 720 lần đã xác nhận |

Báo cáo dùng định nghĩa JIT đã xác nhận vòng đời:

~~~text
JIT adoption = 720 / 940 × 100 = 76,60%
JIT share toàn phạm vi = 720 / 1.000 × 100 = 72,00%
~~~

Nếu báo cáo tạm tính cho phép 40 lượt chờ bằng chứng kết thúc vào tử số, tỷ lệ tạm tính là:

~~~text
(720 + 40) / 940 × 100 = 80,85%
~~~

Phải gắn nhãn tạm tính và công bố 40 lượt chưa hoàn thiện. Không trộn tỷ lệ tạm tính 80,85% với tỷ lệ chính thức 76,60% trên cùng đường xu hướng mà không đánh dấu.

Trong cùng tháng, có 50 chủ thể có truy cập đủ điều kiện; 45 chủ thể đã dùng JIT ít nhất một lần:

~~~text
Active-principal JIT adoption = 45 / 50 × 100 = 90%
~~~

90% chủ thể đã thử hoặc sử dụng JIT không có nghĩa là 90% mọi lần truy cập đã đi qua JIT. Hai kết quả đang mô tả hai đơn vị khác nhau.

Giả sử ngoài ra có 30 lần cấp JIT hợp lệ nhưng không phát sinh sử dụng. Chúng không làm tăng tử số của tỷ lệ áp dụng theo truy cập. Chúng được phân tích trong chỉ số grant utilization của cohort tương ứng.

Các truy cập thất bại trước khi đặc quyền được sử dụng cũng không được đưa lẫn vào mẫu số “lần truy cập đã xác nhận”. Cần theo dõi chúng riêng để hiểu khả năng phục vụ của luồng JIT.

## 7. Thiết kế luồng dữ liệu và bằng chứng

### 7.1. Nguồn dữ liệu

Tối thiểu nên đối chiếu các nhóm nguồn:

- IAM hoặc hệ thống JIT: request, quyết định chính sách, activation, thời hạn và thu hồi.
- PAM hoặc session broker: phiên truy cập, tài khoản đích, liên kết người dùng thực và ngữ cảnh.
- Tài nguyên đích: đăng nhập, sử dụng đặc quyền, thay đổi membership hoặc role.
- Inventory: tài nguyên trong phạm vi, owner, độ nhạy cảm và loại nền tảng.
- Registry ngoại lệ: lý do, thời hạn, người chịu trách nhiệm và phê duyệt.
- Nguồn quan sát đường truy cập khác: xác định các lượt không đi qua cổng PAM.

Không cần mọi nền tảng tạo cùng một loại log; cần chúng ánh xạ được về mô hình chung với độ tin cậy được công bố.

### 7.2. Các trường quan trọng

| Trường | Mục đích |
|---|---|
| access_id | Định danh lần truy cập logic sau chuẩn hóa và khử trùng |
| principal_id | Định danh chủ thể thực; tránh nhầm với tài khoản đích dùng chung |
| principal_type | Phân biệt con người, vendor và workload |
| target_id | Liên kết tài nguyên với inventory |
| entitlement_scope | Mô tả role hoặc phạm vi đặc quyền thực tế |
| grant_id | Liên kết lần truy cập với grant JIT; có thể rỗng với truy cập khác |
| request_id | Đối chiếu nhu cầu và quyết định, không dùng thay cho access_id |
| event_time | Thời điểm hành động thực tế xảy ra |
| ingest_time | Thời điểm hệ thống phân tích nhận được sự kiện |
| activated_at, expires_at | Khoảng hiệu lực được cho phép |
| termination_evidence_at | Thời điểm có bằng chứng kết thúc theo cơ chế đã định |
| policy_version | Giải thích quyết định theo đúng chính sách tại thời điểm đó |
| eligibility_class | Phân loại đủ điều kiện, ngoại lệ hoặc chưa xác định |
| classification_reason | Lý do đưa vào tử số, mẫu số hoặc hàng chờ |
| evidence_reference | Tham chiếu đến bằng chứng được kiểm soát truy cập |

Không lưu password, private key hoặc raw token vào dữ liệu metrics. Bảng điều hành không cần chứa bí mật để chứng minh rằng một quyền đã được cấp và dùng.

### 7.3. Tương quan sự kiện

Một luồng phổ biến có thể biểu diễn như sau:

~~~text
Nhu cầu → Quyết định → Cấp quyền → Dùng quyền → Kết thúc quyền
                          ↘ Không sử dụng, tự hết hạn
~~~

Dùng grant_id hoặc một correlation ID do nền tảng hỗ trợ là lựa chọn tốt hơn việc chỉ ghép theo thời gian. Nếu phải ghép theo principal, target và khoảng hiệu lực, cần nhận diện trường hợp nhiều grant chồng lấn. Không gán tùy ý một hoạt động cho grant “gần nhất” rồi xem đó là bằng chứng chắc chắn.

Một grant có thể phục vụ nhiều lần truy cập hợp lệ. Một lần truy cập có thể cần nhiều entitlement. Mô hình dữ liệu phải xử lý quan hệ này trước khi tổng hợp; join trực tiếp các bảng một-nhiều có thể nhân số đếm.

## 8. Ví dụ truy vấn trên dữ liệu đã chuẩn hóa

Giả sử có bảng phân tích access_fact, mỗi hàng là một access_id duy nhất. Các cột boolean đã được phân loại từ bằng chứng, không chỉ từ tên ứng dụng:

~~~sql
SELECT
    COUNT(*) AS in_scope_accesses,
    SUM(CASE WHEN jit_eligible THEN 1 ELSE 0 END)
        AS eligible_accesses,
    SUM(CASE WHEN jit_eligible AND jit_lifecycle_confirmed
             THEN 1 ELSE 0 END)
        AS confirmed_jit_accesses,
    100.0
        * SUM(CASE WHEN jit_eligible AND jit_lifecycle_confirmed
                   THEN 1 ELSE 0 END)
        / NULLIF(
            SUM(CASE WHEN jit_eligible THEN 1 ELSE 0 END),
            0
          ) AS jit_adoption_pct,
    100.0
        * SUM(CASE WHEN jit_eligible AND jit_lifecycle_confirmed
                   THEN 1 ELSE 0 END)
        / NULLIF(COUNT(*), 0) AS jit_share_all_scope_pct
FROM access_fact
WHERE in_scope = TRUE
  AND privileged_use_confirmed = TRUE
  AND eligibility_class IN ('ELIGIBLE', 'APPROVED_EXCEPTION')
  AND event_time >= :period_start
  AND event_time < :period_end;
~~~

Trong mô hình minh họa này:

- jit_eligible là TRUE đúng khi eligibility_class là ELIGIBLE.
- jit_lifecycle_confirmed chỉ TRUE khi bằng chứng đã đáp ứng định nghĩa báo cáo.
- APPROVED_EXCEPTION thuộc toàn phạm vi nhưng không thuộc tập đủ điều kiện.
- Bản ghi có eligibility_class chưa xác định được giữ trong hàng chờ riêng, đồng thời phải báo số lượng và tỷ lệ của hàng chờ.
- Các tham số thời gian được chuyển về cùng chuẩn thời gian trước khi chạy.
- Khoảng thời gian nửa kín, từ đầu kỳ đến trước đầu kỳ sau, tránh đếm hai lần ở ranh giới.

Kết quả NULL do mẫu số bằng 0 cần hiển thị N/A. Không tự thay NULL bằng 100.

Nếu còn hàng chờ phân loại, cột in_scope_accesses trong kết quả trên chỉ là số quan sát đã phân loại, chưa phải toàn bộ phạm vi thực tế. Dashboard phải đặt tên hiển thị phù hợp, công bố hàng chờ và coi kết quả là tạm tính khi phần chưa phân loại đáng kể. Không âm thầm bỏ chúng để tỷ lệ tăng.

Truy vấn chỉ minh họa phép tổng hợp. Việc xác thực nguồn, khử trùng, tương quan grant và xác nhận thu hồi cần được thực hiện trước; không thể suy ra các điều kiện đó từ công thức phần trăm.

## 9. Thời gian, cohort và chất lượng dữ liệu

### 9.1. Chọn thời điểm đưa một quan sát vào kỳ

Có thể dùng thời điểm bắt đầu truy cập để xác định kỳ báo cáo. Nếu session kéo qua nửa đêm, session vẫn chỉ được tính một lần ở kỳ bắt đầu. Khi đo thời gian đặc quyền, phần thời gian mới cần chia theo từng kỳ.

Phải phân biệt:

- Cohort theo thời điểm yêu cầu: phù hợp phân tích nhu cầu và phê duyệt.
- Cohort theo thời điểm kích hoạt: phù hợp phân tích vòng đời grant.
- Cohort theo thời điểm sử dụng: phù hợp tỷ lệ áp dụng theo truy cập.

Không lấy grant được tạo tháng trước làm mẫu số của grant utilization tháng này rồi so với các lượt sử dụng chỉ tạo trong tháng này nếu hai tập không cùng cohort.

### 9.2. Dữ liệu đến muộn và vòng đời chưa đóng

Một lượt dùng JIT lúc cuối tháng có thể chưa hết hạn trước thời điểm dashboard chạy. Đây không tự động là một lỗi thu hồi.

Cần quy định thời điểm chốt số, khoảng chờ dữ liệu và cách cập nhật báo cáo. Ví dụ tổ chức có thể hiển thị dashboard vận hành hằng ngày với nhãn tạm tính, rồi chốt báo cáo tháng sau cửa sổ hoàn thiện đã thỏa thuận. Khoảng chờ phải dựa vào độ trễ nguồn và thời hạn quyền thực tế, không chọn để che giấu sự cố.

Grant đã đến hạn mà thiếu bằng chứng kết thúc là trạng thái cần điều tra. Không đồng nhất “thiếu log” với “quyền vẫn tồn tại”, nhưng cũng không mặc định “không có log lỗi” là đã thu hồi thành công.

### 9.3. Kiểm tra chất lượng dữ liệu

Trước khi diễn giải xu hướng, cần biết:

- Các nguồn bắt buộc có gửi log đủ và đúng hạn không?
- access_id có bị trùng do replay, retry hoặc nhiều collector không?
- Đồng hồ giữa nguồn cấp quyền và đích có lệch đáng kể không?
- Có bao nhiêu hoạt động không ánh xạ được về principal hoặc target?
- Inventory có đủ tài nguyên nhạy cảm không?
- Sự kiện kết thúc đang xác nhận thu hồi thực tế hay chỉ xác nhận lệnh đã gửi?
- Có thay đổi schema, connector hoặc chính sách phân loại trong kỳ không?

Các chỉ số dữ liệu như tỷ lệ tài nguyên có telemetry, độ trễ sự kiện và số quan sát chưa phân loại nên đặt cạnh JIT adoption. Không thể khẳng định tỷ lệ chính xác trên toàn phạm vi khi còn những vùng chưa quan sát được.

## 10. Phân tích theo nhóm để tránh kết luận sai

Tỷ lệ tổng hợp có thể tăng trong khi nhóm rủi ro cao nhất không tiến bộ. Ví dụ, workload phát sinh hàng chục nghìn hoạt động JIT ngắn hạn có thể lấn át vài chục lượt quản trị trực tiếp vào hệ thống thanh toán.

Nên phân tích tối thiểu theo:

- Mức nhạy cảm của tài nguyên.
- Production và môi trường khác.
- Con người, vendor và workload.
- Nền tảng hoặc cơ chế JIT.
- Nhóm vận hành và owner tài nguyên.
- Loại công việc: vận hành thường ngày, triển khai, khẩn cấp.
- Quyền thường trực, bypass, ngoại lệ và dữ liệu chưa xác định.

Tỷ lệ tổng hợp theo lượt cần tính bằng **tổng tử số chia tổng mẫu số**, không lấy trung bình đơn giản các tỷ lệ của nhóm.

Ví dụ, nhóm A có 9/10 lượt JIT, nhóm B có 10/100 lượt JIT. Tỷ lệ chung là 19/110 = 17,27%, không phải trung bình của 90% và 10% bằng 50%.

Nếu tổ chức muốn ưu tiên rủi ro, có thể thiết kế thêm một điểm số có trọng số theo nhóm tài nguyên. Phải công bố cách chọn trọng số và báo riêng với tỷ lệ theo lượt; không đổi tên điểm số thành “phần trăm truy cập JIT”.

## 11. Đặt mục tiêu gắn với vận hành

Không có một ngưỡng adoption duy nhất phù hợp mọi tổ chức. Mục tiêu nên xuất phát từ baseline, độ nhạy cảm, khả năng nền tảng và lộ trình loại bỏ quyền thường trực.

Một thỏa thuận mục tiêu minh họa có thể gồm:

- Tăng tỷ lệ áp dụng trên các hệ thống đã hỗ trợ JIT theo từng quý.
- Có owner và ngày hết hạn cho mọi ngoại lệ kỹ thuật.
- Không tăng standing privilege trên nhóm tài nguyên nhạy cảm nếu chưa được xét duyệt.
- Xử lý mọi grant quá hạn mà chưa xác nhận kết thúc theo quy trình sự cố vận hành.
- Theo dõi thời gian chờ và tỷ lệ hoàn thành công việc để bảo đảm JIT đáp ứng nhu cầu.

Không nâng adoption bằng cách bắt người dùng mở nhiều lượt JIT không cần thiết. Một công việc được gộp thành ít phiên hợp lý có thể làm số phiên JIT giảm nhưng cải thiện vận hành.

Mục tiêu cần quy định tử số, mẫu số, kỳ đo, nguồn dữ liệu, owner chỉ số và điều kiện chốt số. Khi đổi định nghĩa, phải ghi phiên bản và giải thích ảnh hưởng đến khả năng so sánh.

## 12. Từ chỉ số thấp đến hành động cải tiến

### 12.1. Nhiều người dùng JIT nhưng còn nhiều lượt ngoài JIT

Kiểm tra các nhóm đã dùng JIT ít nhất một lần nhưng vẫn duy trì đường quản trị thường trực. Nguyên nhân có thể là runbook cũ, công cụ không tích hợp, tác vụ nền hoặc quyền kế thừa chưa được thu hồi.

Hành động phù hợp là xác định đường truy cập, owner và nhu cầu công việc; hoàn thiện luồng JIT rồi xử lý quyền dư theo quy trình thay đổi. Chỉ đào tạo thêm người dùng sẽ không giải quyết quyền kế thừa còn tồn tại.

### 12.2. Nhiều yêu cầu được cấp nhưng không sử dụng

Đối chiếu thời gian phê duyệt với thời điểm công việc cần bắt đầu. Xem người dùng có xin trước để đề phòng, chọn TTL quá dài hoặc không sử dụng được quyền sau khi kích hoạt hay không.

Đừng diễn giải tất cả grant không dùng là lạm dụng. Công việc có thể đã bị hủy hoặc hệ thống đã tự phục hồi trước khi cần thao tác.

### 12.3. Adoption cao nhưng quyền kết thúc không được xác nhận

Ưu tiên điều tra cơ chế thu hồi, connector, session và vòng đời credential. Một lỗi thu hồi có thể biến quyền tạm thời thành quyền tồn tại lâu hơn dự kiến. Chỉ số áp dụng cao không bù được khiếm khuyết này.

Sau xử lý, cập nhật lại phân loại và báo cáo bị ảnh hưởng nếu hợp đồng chỉ số yêu cầu bằng chứng kết thúc.

### 12.4. Adoption giảm sau khi mở rộng inventory

Tách ảnh hưởng do thêm tài nguyên vào phạm vi với thay đổi hành vi trên nhóm cũ. Có thể hiển thị song song:

- Xu hướng trên phạm vi ổn định.
- Tỷ lệ toàn phạm vi hiện tại.
- Số tài nguyên mới và backlog chuyển đổi.

Việc phát hiện thêm truy cập ngoài JIT có thể làm tỷ lệ xấu đi nhưng cải thiện hiểu biết về rủi ro. Không loại dữ liệu mới chỉ để giữ đường xu hướng tăng.

## 13. Các cách đo tạo ra kết quả gây hiểu nhầm

**Đếm yêu cầu đã phê duyệt thay cho hoạt động sử dụng.** Một request đã được duyệt có thể không kích hoạt, không dùng được hoặc không hề được sử dụng.

**Chỉ lấy log của cổng JIT làm mẫu số.** Khi không quan sát đường khác, báo cáo chỉ nói về lưu lượng qua cổng, không nói về toàn bộ truy cập đặc quyền.

**Thu hẹp tập đủ điều kiện khi gặp hệ thống khó chuyển đổi.** Ngoại lệ phải có căn cứ, owner và thời hạn; luôn hiển thị ảnh hưởng của chúng trong tỷ lệ toàn phạm vi.

**Xem credential ngắn hạn là bằng chứng duy nhất.** Credential có thể đi kèm đặc quyền quá rộng, thời hạn thực tế khác dự kiến hoặc cơ chế session sống lâu hơn credential.

**Bỏ qua standing privilege của cùng chủ thể.** Một người có thể dùng JIT cho phần lớn công việc nhưng vẫn giữ quyền admin thường trực. Adoption cần đi cùng kiểm kê quyền.

**Trộn hoạt động con người và automation mà không phân nhóm.** Tần suất lớn của automation có thể làm kết quả tổng hợp che khuất vấn đề của con người và vendor.

**Cho rằng một grant bị từ chối là một lần thất bại adoption.** Từ chối đúng chính sách có thể là kết quả mong muốn. Theo dõi riêng hiệu quả ra quyết định và khả năng hoàn thành công việc hợp lệ.

**Thay đổi đơn vị đếm giữa các kỳ.** Chuyển từ đếm phiên sang đếm lệnh có thể làm tỷ lệ thay đổi mà hành vi không đổi.

## 14. Bài tập áp dụng

### Tình huống

Một phạm vi có 600 lần truy cập đặc quyền đã xác nhận trong tuần:

- 420 lượt JIT đã xác nhận vòng đời.
- 30 lượt đã dùng JIT nhưng chưa có bằng chứng kết thúc.
- 90 lượt dùng quyền thường trực dù tài nguyên đã hỗ trợ JIT.
- 20 lượt truy cập trực tiếp bỏ qua JIT trên tài nguyên đủ điều kiện.
- 40 lượt trên hệ thống có ngoại lệ kỹ thuật được duyệt.

Ngoài ra, 20 lần đăng nhập đặc quyền thất bại chưa phát sinh sử dụng; 15 grant hợp lệ chưa được dùng. Có 24 chủ thể có truy cập đủ điều kiện và 18 chủ thể dùng JIT đã xác nhận.

### Yêu cầu

1. Tính tỷ lệ áp dụng theo lần truy cập đủ điều kiện với định nghĩa vòng đời đã xác nhận.
2. Tính tỷ lệ JIT trên toàn phạm vi.
3. Tính tỷ lệ chủ thể đang hoạt động đã dùng JIT.
4. Giải thích cách xử lý 30 lượt chờ bằng chứng, 20 lần đăng nhập thất bại và 15 grant chưa dùng.
5. Chọn hai hành động cải tiến ưu tiên, nêu thêm bằng chứng cần thu thập.

### Gợi ý lời giải

Tập đủ điều kiện có 600 − 40 = 560 lượt. Tử số chính thức có 420 lượt.

~~~text
JIT adoption = 420 / 560 × 100 = 75,00%
JIT share toàn phạm vi = 420 / 600 × 100 = 70,00%
Active-principal adoption = 18 / 24 × 100 = 75,00%
~~~

30 lượt chờ bằng chứng vẫn thuộc mẫu số theo truy cập đủ điều kiện nhưng chưa vào tử số chính thức. Cần phân biệt grant còn trong hạn với grant đã quá hạn và log đến muộn.

20 lần đăng nhập thất bại và 15 grant chưa dùng không thuộc 600 lần sử dụng đã xác nhận. Chúng cần bảng phân tích riêng; không dùng chúng để làm tăng tử số hoặc thay mẫu số theo truy cập.

Hai hướng cải tiến hợp lý là điều tra 30 lượt thiếu bằng chứng kết thúc và phân tích 110 lượt thường trực hoặc bypass. Thứ tự ưu tiên cụ thể còn phụ thuộc độ nhạy cảm của đích, tình trạng quyền hiện tại và khả năng gián đoạn công việc.

## 15. Checklist cho một báo cáo JIT adoption có thể kiểm tra

- Đã xác định phạm vi, kỳ báo cáo, múi giờ và đơn vị đếm.
- Đã phân biệt JIT ở lớp truy cập với quyền tạm thời trên tài nguyên đích.
- Đã có định nghĩa bằng chứng để một lượt được tính vào tử số.
- Đã quan sát đường truy cập ngoài JIT và công bố vùng chưa có telemetry.
- Đã đặt tử số và mẫu số trong cùng tập, cùng kỳ và cùng đơn vị.
- Đã công bố ngoại lệ, hàng chờ phân loại và các vòng đời chưa đóng.
- Đã xử lý khử trùng, join một-nhiều, thời gian chồng lấn và dữ liệu đến muộn.
- Đã hiển thị standing privilege và chất lượng kết thúc quyền bên cạnh adoption.
- Đã phân nhóm tài nguyên nhạy cảm, con người, vendor và workload.
- Đã liên kết kết quả với owner, nguyên nhân và hành động cải tiến cụ thể.

JIT adoption hữu ích khi nó phản ánh những nhu cầu đặc quyền đã được thực hiện qua quyền có giới hạn thời gian, với mẫu số đủ rộng và bằng chứng đủ rõ. Giá trị quản trị của chỉ số nằm ở khả năng chỉ ra nơi còn quyền thường trực, đường bypass hoặc khoảng trống vận hành cần xử lý.
