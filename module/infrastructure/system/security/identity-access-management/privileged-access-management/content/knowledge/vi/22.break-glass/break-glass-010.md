# Diễn tập break-glass

## 1. Mục tiêu của bài học

Break-glass là cơ chế truy cập khẩn cấp được chuẩn bị trước để người có trách nhiệm có thể khôi phục dịch vụ hoặc xử lý sự cố khi con đường truy cập thông thường không còn phù hợp hoặc không hoạt động. Trong quản lý truy cập đặc quyền (PAM), cơ chế này có thể liên quan đến tài khoản quản trị, quyền quản trị dịch vụ, thiết bị hạ tầng, kho bí mật hoặc nền tảng định danh.

Một tài khoản khẩn cấp tồn tại trong danh sách kiểm kê chưa chứng minh tổ chức có khả năng phục hồi. Người trực có thể không tìm được hướng dẫn, người phê duyệt có thể vắng mặt, phương thức lấy credential có thể phụ thuộc chính hệ thống đang lỗi, hoặc quyền có thể không được thu hồi sau khi hệ thống đã hoạt động trở lại.

Diễn tập break-glass kiểm chứng toàn bộ chuỗi đó trong điều kiện có kiểm soát. Sau bài này, bạn có thể:

- Chuyển một rủi ro gián đoạn truy cập thành kịch bản diễn tập với kết quả đo được.
- Xác định người được phép kích hoạt, người thực hiện, người kiểm soát và quyền dừng.
- Kiểm tra least privilege, giới hạn thời gian kiểu JIT và giới hạn thao tác kiểu JEA trong đường truy cập khẩn cấp.
- Thu bằng chứng mà không phát tán credential.
- Chứng minh quyền và phiên đã được thu hồi, credential được xử lý đúng, hệ thống trở lại trạng thái bình thường.
- Biến phát hiện sau diễn tập thành công việc khắc phục và kiểm thử lại.

Bài học tập trung vào **cách chứng minh quy trình hoạt động**. Thiết kế chi tiết vault, lưu phiên và giám sát là các năng lực hỗ trợ; một buổi diễn tập phải kiểm tra các năng lực đó trong một tình huống thống nhất.

## 2. Diễn tập phải trả lời được những câu hỏi nào?

Một cuộc diễn tập có giá trị khi trả lời được ít nhất sáu câu hỏi.

| Câu hỏi | Điều cần chứng minh |
|---|---|
| Khi nào được kích hoạt? | Người trực nhận diện đúng điều kiện khẩn cấp và có căn cứ sự cố |
| Ai được quyết định? | Có thẩm quyền rõ ràng, xác minh danh tính và phương án thay thế khi người chính vắng mặt |
| Quyền nào được cấp? | Đúng người, đúng tài nguyên, đúng thao tác và đúng thời hạn |
| Khôi phục được việc gì? | Hoàn thành tác vụ phục hồi đã định nghĩa, có kiểm tra kết quả độc lập |
| Có thể biết chuyện gì đã xảy ra? | Bằng chứng đủ liên kết từ yêu cầu đến cấp quyền, phiên, thay đổi và thu hồi |
| Có thể quay lại trạng thái bình thường? | Không còn phiên, token, credential hoặc quyền tạm ngoài ý muốn |

Không nên chỉ đo thời gian đăng nhập. Đăng nhập nhanh nhưng thực hiện sai tài nguyên, thiếu bằng chứng hoặc để lại quyền quản trị thường trực vẫn là kết quả không đạt.

Cũng không nên đánh đồng “chưa từng sử dụng break-glass” với “break-glass hoạt động tốt”. Một cơ chế ít được dùng rất dễ bị sai lệch theo thời gian: người giữ khóa đổi vai trò, tài khoản bị vô hiệu hóa, đường mạng thay đổi hoặc tài liệu tham chiếu bị di chuyển.

## 3. Chọn mức diễn tập phù hợp

Không phải mọi buổi diễn tập đều cần ngắt một dịch vụ đang vận hành. Chọn mức độ dựa trên rủi ro, mục tiêu kiểm chứng và khả năng hoàn tác.

| Mức | Cách thực hiện | Chứng minh được | Hạn chế cần ghi nhận |
|---|---|---|---|
| Thảo luận trên bàn | Điều phối viên đưa tình huống; các vai trò mô tả quyết định, liên hệ và bằng chứng | Hiểu quy trình, trách nhiệm, điều kiện kích hoạt | Chưa chứng minh tài khoản, đường mạng hoặc công cụ thực sự hoạt động |
| Kiểm tra chức năng trong lab | Thực hiện chuỗi cấp quyền, thao tác và thu hồi trên tài nguyên thử nghiệm | Năng lực kỹ thuật và phối hợp trong môi trường đại diện | Có thể khác production về dependency, quy mô hoặc chính sách |
| Diễn tập tích hợp có kiểm soát | Nhiều nhóm phối hợp, có inject tình huống, hệ thống giám sát và kho bằng chứng thực | Điểm nối giữa định danh, PAM, vận hành và ứng phó sự cố | Cần điều phối và cơ chế dừng rõ ràng |
| Kiểm chứng giới hạn trên production | Chỉ một số thao tác được phê duyệt, trong cửa sổ và phạm vi nhỏ | Các giả định quan trọng của môi trường thật | Rủi ro cao hơn; cần quyết định thay đổi riêng và đường khôi phục đáng tin cậy |

Mỗi mức nên bổ sung cho mức trước. Một buổi thảo luận phát hiện không có người phê duyệt thay thế là lý do để sửa quy trình trước khi thực hiện diễn tập kỹ thuật phức tạp.

Nếu chỉ mô phỏng sự cố IdP bằng một thẻ tình huống, báo cáo phải ghi đúng là mô phỏng. Không kết luận đã chứng minh khả năng sống sót khi IdP thực sự mất kết nối nếu đường truy cập vẫn sử dụng IdP bình thường.

### Phân biệt diễn tập và sự cố thật

Mọi thông điệp của buổi diễn tập cần có dấu hiệu nhận biết, ví dụ `EXERCISE` và mã `EX-PAM-017`. Tuy vậy, nhãn diễn tập không tự cấp quyền bỏ qua chính sách kiểm soát.

Nếu xuất hiện sự cố thật, người chỉ huy diễn tập có thể dừng hoạt động mô phỏng và chuyển việc xử lý sang quy trình sự cố. Ghi nhận thời điểm chuyển giao để tránh trộn hành động diễn tập với hành động ứng phó thực tế.

## 4. Bắt đầu bằng mục tiêu kinh doanh và điều kiện kích hoạt

Một kịch bản tốt bắt đầu bằng dịch vụ cần phục hồi, không bắt đầu bằng câu “hãy dùng tài khoản admin khẩn cấp”.

Ví dụ:

> Dịch vụ thanh toán nội bộ trong môi trường thử nghiệm không thể nhận cấu hình mới vì đường quản trị qua IdP và PAM thông thường không khả dụng. Đội trực phải thực hiện một thay đổi cấu hình đã được duyệt trên đúng một máy quản trị thử nghiệm, xác nhận sức khỏe dịch vụ, sau đó thu hồi toàn bộ quyền khẩn cấp và đóng bằng chứng.

Trong ví dụ này, khả năng phục hồi cần được tách thành hai phần:

1. Có thể thực hiện tác vụ quản trị cần thiết trong điều kiện giả định.
2. Có thể kết thúc trạng thái khẩn cấp mà không để lại quyền truy cập dư thừa.

Trước khi diễn tập, xác định:

- Tài nguyên đích, môi trường, chủ sở hữu và dữ liệu liên quan.
- Tác vụ cụ thể cần làm; ưu tiên một thao tác vô hại, xác định trước và hoàn tác được.
- Điều kiện nào khiến truy cập thông thường không đủ đáp ứng.
- Điều kiện nào cấm sử dụng đường khẩn cấp đã chọn, chẳng hạn nghi ngờ credential khẩn cấp bị lộ.
- Phạm vi tối đa của quyền, số người và số phiên.
- Mục tiêu thời gian phục hồi do chủ dịch vụ và tổ chức chấp nhận.
- Thời hạn cấp quyền và hạn thu hồi sau khi kết thúc tác vụ.
- Bằng chứng phải có để kết luận thành công.

**Không có một ngưỡng thời gian chung cho mọi hệ thống.** Một dịch vụ có mục tiêu phục hồi ngắn có thể cần nhiều chuẩn bị và kiểm chứng hơn. Mục tiêu thời gian không phải lý do tự động bỏ qua xác minh danh tính, kiểm soát phạm vi hoặc lưu bằng chứng.

## 5. Lập bản đồ dependency của đường khẩn cấp

Một lỗi thường gặp là thiết kế đường dự phòng có cùng điểm hỏng với đường chính.

Ví dụ, tài khoản khẩn cấp tồn tại ngoài IdP nhưng hướng dẫn lấy credential chỉ nằm trong cổng tài liệu yêu cầu đăng nhập qua IdP. Khi IdP lỗi, credential và hướng dẫn đều khó tiếp cận.

Hãy liệt kê dependency theo từng bước:

| Bước | Dependency cần xem xét | Câu hỏi diễn tập |
|---|---|---|
| Nhận biết sự cố | Dashboard, cảnh báo, kênh liên lạc | Khi dashboard không vào được, ai xác nhận ảnh hưởng? |
| Tìm hướng dẫn | Cổng tài liệu, phân quyền đọc, phiên bản runbook | Người trực có tìm được bản được kiểm soát và còn hiệu lực? |
| Xác minh và phê duyệt | IdP, danh bạ, điện thoại, người thay thế | Nếu kênh chính hỏng, phương án đã duyệt là gì? |
| Lấy hoặc kích hoạt credential | Vault, HSM, vật mang bí mật, người giữ thành phần | Đường này có phụ thuộc chính thành phần đang giả định lỗi? |
| Kết nối đến đích | DNS, mạng quản trị, bastion, VPN, thiết bị đầu cuối | Đường kết nối thay thế có được phép và có kiểm soát? |
| Thực hiện tác vụ | Vai trò, phạm vi quyền, API hoặc giao diện quản trị | Có đúng quyền cần thiết và giới hạn tác động? |
| Lưu bằng chứng | Log, bộ ghi phiên, đồng bộ thời gian, nơi nhận log | Khi collector lỗi, có nguồn bằng chứng bù đã duyệt? |
| Thu hồi và khôi phục | IdP/PAM/vault, quản lý phiên, cơ chế đổi bí mật | Có thể thu hồi ngay cả khi hệ thống chính chưa phục hồi? |

Các dependency phải được kiểm chứng bằng phương pháp phù hợp. Không cần vô hiệu hóa DNS hay IdP thật để kiểm tra bước tìm tài liệu; có thể bắt đầu bằng lab và mô phỏng có ghi nhãn. Những giả định chưa kiểm chứng trên môi trường thật phải được nêu trong báo cáo.

## 6. Phân vai và quyền dừng

Một người có thể giữ nhiều vai trong tổ chức nhỏ, nhưng các xung đột kiểm soát phải được nhận diện trước. Người thực hiện không nên tự chứng nhận mọi điều kiện thành công của chính mình.

| Vai trò | Trách nhiệm chính |
|---|---|
| Chủ dịch vụ | Xác định tác vụ phục hồi, chấp nhận ảnh hưởng và xác nhận dịch vụ hoạt động |
| Người chỉ huy diễn tập | Quản lý phạm vi, thời gian, inject, quyết định dừng và chuyển giao khi có sự cố thật |
| Người phê duyệt có thẩm quyền | Kiểm tra điều kiện kích hoạt, danh tính, phạm vi và thời hạn |
| Người thực hiện | Sử dụng đúng quyền, tài nguyên và thao tác được duyệt |
| Người kiểm soát hoặc chứng kiến | Kiểm tra các điểm kiểm soát độc lập theo chính sách dual control |
| Đội PAM/định danh | Hỗ trợ cấp quyền, hết hạn, thu hồi, đối soát tài khoản và credential |
| Đội giám sát | Nhận cảnh báo, liên kết sự kiện và bảo quản bằng chứng |
| Người quan sát | Ghi thời gian, trở ngại, hành vi lệch runbook và các giả định |
| Chủ hành động khắc phục | Nhận phát hiện, đặt hạn sửa và cung cấp kết quả kiểm thử lại |

Quy định rõ người thay thế cho các vai trò trọng yếu. Không đợi đến khi diễn tập mới tìm người có quyền phê duyệt.

**Quyền dừng phải thực thi được.** Mỗi người tham gia cần biết cách yêu cầu dừng; người chỉ huy và chủ dịch vụ cần có thẩm quyền chấm dứt hoạt động theo tiêu chí đã thống nhất. Đội kỹ thuật phải biết cụ thể phiên nào cần ngắt, quyền nào cần thu hồi và thao tác nào cần hoàn tác.

Dual control không chỉ là hai người có mặt trong một cuộc gọi. Điểm kiểm soát phải xác định một người làm gì, người thứ hai kiểm tra gì và bằng chứng nào ghi nhận sự kiểm tra đó. Nếu hai người cùng dùng một danh tính chia sẻ mà không có cơ chế quy trách nhiệm cá nhân, việc đối soát sẽ yếu.

## 7. Thiết kế kịch bản và các tình huống bổ sung

Nên thiết kế một kịch bản nền đơn giản, sau đó thêm inject để kiểm tra từng giả định. Inject là một thông tin hoặc sự kiện mà điều phối viên đưa vào trong quá trình diễn tập.

### 7.1. Kịch bản nền: đường truy cập quản trị thông thường gián đoạn

Điều kiện ban đầu:

- Có tài khoản hoặc cơ chế khẩn cấp đã kiểm kê và có chủ sở hữu.
- Người tham gia có thiết bị quản trị, danh tính và vai trò phù hợp.
- Tài nguyên thử nghiệm có trạng thái gốc đã ghi nhận.
- Tác vụ được phép là sửa một cấu hình thử nghiệm xác định trước.
- Quyền được giới hạn ở tài nguyên đó và thời hạn được phê duyệt.
- Có cách kiểm tra độc lập việc khôi phục dịch vụ và thu hồi truy cập.

Đích đến của diễn tập là tác vụ hoàn thành, quyền kết thúc và bằng chứng đầy đủ; không phải chỉ lấy được credential.

### 7.2. Inject theo mục tiêu

| Inject | Mục tiêu kiểm tra | Hành vi mong đợi |
|---|---|---|
| Người phê duyệt chính không phản hồi | Khả năng chuyển cấp | Dùng người thay thế đã được chỉ định, ghi nhận thời gian chờ |
| Tài liệu chính không truy cập được | Khả năng tiếp cận runbook | Dùng bản dự phòng được kiểm soát, kiểm tra phiên bản |
| Collector log trung tâm gián đoạn | Khả năng duy trì bằng chứng | Thực hiện phương án bù đã duyệt hoặc dừng theo chính sách |
| Yêu cầu thêm quyền ngoài phạm vi | Kiểm soát least privilege | Từ chối hoặc quay lại quy trình phê duyệt mới |
| Phiên sắp hết hạn nhưng tác vụ chưa xong | Kiểm soát JIT | Đánh giá lại và phê duyệt gia hạn nếu được phép; không tự kéo dài |
| Có dấu hiệu credential bị tiết lộ | Phân biệt phục hồi với nghi ngờ xâm phạm | Không tiếp tục tin vào credential đó; chuyển sang ứng phó và đường tin cậy khác |
| Kênh phê duyệt có dấu hiệu giả mạo | Xác minh danh tính | Xác thực qua phương án được duyệt trước khi cấp quyền |
| Dịch vụ bình thường trở lại sớm | Kết thúc quyền khẩn cấp | Thu hồi theo nhu cầu thực tế, không giữ quyền chỉ vì còn thời hạn |

Không dồn mọi inject vào buổi đầu. Quá nhiều biến động có thể khiến không xác định được nguyên nhân thất bại. Chỉ thêm độ khó khi chuỗi nền đã hoạt động và có dữ liệu đo đáng tin cậy.

### 7.3. Kiểm tra âm tính

Kiểm tra âm tính chứng minh một hành động **không được phép** bị chặn, chẳng hạn:

- Người không có vai trò phù hợp không thể kích hoạt quyền.
- Tài khoản được cấp cho một máy thử nghiệm không quản trị được máy thử nghiệm khác.
- Credential hoặc quyền tạm không còn tạo được phiên mới sau thu hồi.
- Phiên hiện hữu đã kết thúc và không tiếp tục thực hiện thao tác đặc quyền.
- Gia hạn không xảy ra khi chưa có quyết định phê duyệt cần thiết.

Các kiểm tra phải được giới hạn ở tài nguyên thử nghiệm đã duyệt và tránh gây khóa tài khoản ngoài ý muốn. Một kiểm tra đăng nhập mới bị từ chối chưa đủ chứng minh phiên đang mở hoặc token đã phát hành đều mất hiệu lực.

## 8. Chuẩn bị trước buổi diễn tập

### 8.1. Hồ sơ kế hoạch tối thiểu

Kế hoạch cần có mã diễn tập, phiên bản runbook, mục tiêu, phạm vi, vai trò, kịch bản, phương pháp mô phỏng, thời gian, tiêu chí đạt/dừng, kế hoạch hoàn tác và kho bằng chứng.

Nếu có thao tác production, hoàn thành quy trình quản lý thay đổi tương ứng trước khi bắt đầu. Kế hoạch diễn tập không thay thế quyền phê duyệt một thay đổi vận hành.

Một mẫu hồ sơ có thể được biểu diễn như sau. Đây là **dữ liệu kế hoạch minh họa**, không phải cấu hình để nhập trực tiếp vào sản phẩm PAM:

~~~yaml
exercise_id: EX-PAM-017
label: EXERCISE
environment: isolated-lab
service: payment-simulator
scenario: normal-admin-path-unavailable
runbook_revision: BG-RB-12
target:
  resource_id: lab-admin-01
  permitted_action: restore-approved-test-setting
limits:
  maximum_active_sessions: 1
  grant_duration_minutes: 30
  recovery_objective_minutes: 20
  revoke_after_work_minutes: 5
roles:
  commander: exercise-role-commander
  approver: exercise-role-approver
  operator: exercise-role-operator
  observer: exercise-role-observer
evidence:
  incident_reference: EX-INC-017
  repository_reference: EX-EVID-017
stop_conditions:
  - unexpected-production-impact
  - target-identity-mismatch
  - suspected-credential-exposure
  - required-control-unavailable-without-approved-compensation
~~~

Các mốc 20, 30 và 5 phút trong ví dụ là giả định của buổi diễn tập. Chúng phải được thay bằng yêu cầu đã được tổ chức phê duyệt, không dùng như chuẩn áp dụng chung.

### 8.2. Kiểm tra sẵn sàng

Trước khi bắt đầu, xác nhận:

- Danh sách tài nguyên và tài khoản đúng với phạm vi.
- Những người tham gia đã nhận lịch và biết kênh điều phối.
- Runbook có phiên bản; hướng dẫn và kênh liên hệ dự phòng truy cập được.
- Có trạng thái gốc hoặc phương án hoàn tác phù hợp với tác vụ.
- Cơ chế phê duyệt và người thay thế sẵn sàng.
- Hệ thống ghi nhận thời gian và sự kiện có thể đối soát.
- Kho bằng chứng có phân quyền, người chịu trách nhiệm và chính sách lưu giữ.
- Mẫu ghi nhận không yêu cầu chụp hay sao chép bí mật.
- Có phương thức ngắt phiên và thu hồi khi quyền JIT không hết hạn như dự kiến.
- Người quan sát biết dữ liệu nào là thật, dữ liệu nào là inject.

Có thể kiểm tra trạng thái cấu hình của tài khoản khẩn cấp mà không tiết lộ giá trị credential cho cả đội. Việc cần kiểm chứng khả năng lấy credential phải diễn ra tại bước có thẩm quyền, theo cơ chế được thiết kế.

## 9. Quy trình thực hiện từng bước

### Bước 1 — Mở diễn tập và xác nhận ranh giới

Người chỉ huy công bố mã diễn tập, thời gian bắt đầu, tài nguyên đích, vai trò, tiêu chí dừng và kênh báo sự cố thật. Người quan sát ghi lại phiên bản runbook cùng trạng thái ban đầu.

Mọi người xác nhận cùng hiểu tài nguyên nào nằm trong phạm vi. Nếu tên hiển thị hoặc địa chỉ mơ hồ, dừng để xác minh định danh tài nguyên thay vì đoán.

### Bước 2 — Đưa tình huống và đánh giá điều kiện kích hoạt

Người trực tiếp nhận inject hoặc hiện tượng thử nghiệm, đánh giá ảnh hưởng và kiểm tra con đường quản trị thông thường theo runbook. Không thử lặp vô hạn nếu quy trình đã có điểm chuyển sang đường khẩn cấp.

Ghi căn cứ: lỗi nào xảy ra, dịch vụ nào bị ảnh hưởng, nguồn xác nhận nào được dùng và vì sao cần break-glass.

### Bước 3 — Mở yêu cầu và xác minh danh tính

Liên kết yêu cầu truy cập với hồ sơ diễn tập hoặc hồ sơ sự cố. Xác minh người yêu cầu bằng phương thức đã duyệt. Kênh liên lạc khẩn cấp có thể khác kênh bình thường, nhưng cần có căn cứ tin cậy.

Không chấp nhận chỉ một tin nhắn “tôi là quản trị viên, đang rất gấp” làm bằng chứng danh tính.

### Bước 4 — Phê duyệt phạm vi và thời hạn

Người có thẩm quyền xác nhận tài nguyên, quyền, tác vụ, người sử dụng, thời hạn và yêu cầu chứng kiến. Nếu chính sách có cơ chế khẩn cấp thay cho luồng phê duyệt thông thường, phải diễn tập đúng cơ chế đó và nghĩa vụ rà soát sau sử dụng.

Sự chậm trễ của phê duyệt là một phát hiện vận hành; không tự xóa điểm kiểm soát khỏi quy trình chỉ để đạt thời gian mục tiêu.

### Bước 5 — Kích hoạt hoặc lấy quyền khẩn cấp

Thực hiện cơ chế được thiết kế: cấp vai trò tạm, lấy credential từ vault, kích hoạt tài khoản dự phòng hoặc sử dụng quy trình có nhiều người kiểm soát.

Ghi mã tham chiếu quyền hoặc bản ghi truy cập; không đưa giá trị mật khẩu, khóa riêng, seed MFA hay token vào ticket, chat hoặc ảnh bằng chứng.

Ngay sau khi cấp, xác nhận phạm vi và thời hạn đúng như phê duyệt. Nếu hệ thống cấp rộng hơn dự kiến, dừng hoặc thu hồi trước khi tiếp tục.

### Bước 6 — Kết nối và kiểm tra khả năng quan sát

Xác nhận đúng tài nguyên đích và đúng danh tính/phiên. Kiểm tra cảnh báo sử dụng break-glass được gửi đến đúng nơi và có người nhận xử lý.

Nếu cơ chế ghi phiên bắt buộc không hoạt động, áp dụng chính sách đã duyệt: dừng hoặc sử dụng kiểm soát bù cụ thể. Không tự coi việc “có người đang nhìn màn hình” tương đương một bản ghi phiên có thể truy xuất và bảo vệ.

### Bước 7 — Thực hiện tác vụ tối thiểu và xác nhận dịch vụ

Thực hiện đúng thao tác phục hồi đã duyệt. Ghi trước/sau ở mức đủ chứng minh kết quả, tránh sao chép dữ liệu nhạy cảm không cần thiết.

Chủ dịch vụ hoặc người kiểm tra độc lập xác nhận kết quả bằng tín hiệu chức năng: yêu cầu thử nghiệm thành công, cấu hình đúng hoặc dịch vụ đạt điều kiện sức khỏe đã định nghĩa. Một câu “lệnh chạy không báo lỗi” không luôn đủ chứng minh dịch vụ đã phục hồi.

### Bước 8 — Kiểm tra giới hạn và xử lý tình huống bổ sung

Thực hiện kiểm tra âm tính đã duyệt và các inject trong kế hoạch. Ví dụ, thử một thao tác không được cấp trên tài nguyên thử nghiệm thứ hai và ghi nhận bị từ chối.

Nếu cần thêm quyền để hoàn thành công việc, quay lại bước phê duyệt thích hợp. Không mở rộng phạm vi âm thầm trong cùng phiên.

### Bước 9 — Kết thúc truy cập và phục hồi trạng thái kiểm soát

Sau khi tác vụ hoàn tất hoặc khi dừng diễn tập:

1. Kết thúc các phiên khẩn cấp.
2. Thu hồi quyền tạm, entitlement hoặc membership được cấp.
3. Xử lý token, khóa hoặc credential phát sinh theo thiết kế của nền tảng.
4. Luân chuyển hoặc thay thế credential khẩn cấp khi chính sách yêu cầu, đặc biệt nếu đã tiết lộ cho người sử dụng.
5. Kiểm tra tài khoản, cấu hình và tài nguyên trở lại trạng thái thiết kế.
6. Xác minh lại đường quản trị thông thường trước khi rời đường khẩn cấp.

Đổi mật khẩu không mặc nhiên ngắt mọi phiên hay vô hiệu hóa mọi token. Thu hồi quyền, kết thúc phiên và luân chuyển credential là các việc liên quan nhưng khác nhau; phải kiểm tra từng cơ chế áp dụng.

Tài khoản break-glass được thiết kế luôn sẵn sàng không nhất thiết phải bị vô hiệu hóa sau mỗi lần diễn tập. Đích cần đạt là **trạng thái sẵn sàng an toàn theo thiết kế**, không phải áp dụng một thao tác vô hiệu hóa chung cho mọi kiến trúc.

### Bước 10 — Đối soát bằng chứng và đóng diễn tập

Đối chiếu yêu cầu, phê duyệt, bản ghi cấp quyền, phiên, thao tác, kết quả dịch vụ và bằng chứng thu hồi. Chủ dịch vụ xác nhận không còn tác động ngoài ý muốn.

Nếu thiếu chứng cứ thu hồi, kết quả phải ghi chưa xác minh đầy đủ, dù dịch vụ đã hoạt động. Chỉ đóng việc sau khi đã xử lý các nghĩa vụ bắt buộc hoặc chuyển giao rõ ràng với chủ sở hữu và thời hạn.

## 10. Tiêu chí dừng và hoàn tác

Tiêu chí dừng cần cụ thể đủ để người điều phối ra quyết định ngay.

| Tình huống | Hành động trước mắt | Điều kiện để tiếp tục |
|---|---|---|
| Có ảnh hưởng ngoài dự kiến đến production | Dừng thao tác diễn tập, bảo vệ dịch vụ và thông báo người phụ trách | Được đánh giá và quyết định lại theo quy trình phù hợp |
| Nhầm tài nguyên hoặc danh tính | Không thực hiện thêm thay đổi, xác minh và thu hồi quyền nhầm | Định danh đúng và có phê duyệt phù hợp |
| Nghi lộ credential | Hạn chế sử dụng, kích hoạt xử lý sự cố, thu hồi/thay bí mật theo kế hoạch | Có đường truy cập tin cậy và quyết định của người có thẩm quyền |
| Thiếu kiểm soát bắt buộc | Không tự tiếp tục theo suy đoán | Có kiểm soát bù đã được chấp thuận hoặc điều chỉnh buổi diễn tập |
| Không thu hồi được phiên/quyền | Chuyển sang xử lý tồn dư truy cập, duy trì giám sát | Chứng minh đã khống chế hoặc xử lý quyền còn lại |
| Tác vụ vượt phạm vi ban đầu | Tạm dừng phần việc ngoài phạm vi | Đã đánh giá lại rủi ro và phê duyệt thay đổi cần thiết |

Khi dừng, ưu tiên không gây thêm gián đoạn và không mất đường phục hồi cuối cùng. Trình tự thu hồi, đổi credential và khôi phục trạng thái phải phù hợp kiến trúc thực tế; có thể cần duy trì một đường quản trị tin cậy trong khi sửa đường còn lại.

Một buổi diễn tập dừng đúng tiêu chí không nhất thiết thất bại về tổ chức. Nó có thể chứng minh khả năng phát hiện và khống chế rủi ro. Tuy nhiên, mục tiêu phục hồi chưa được kiểm chứng thì vẫn phải ghi là chưa đạt và cần kiểm thử lại.

## 11. Bằng chứng cần thu

Mỗi bằng chứng cần gắn với mã diễn tập, nguồn, thời gian, người thu và vị trí lưu được kiểm soát.

| Nhóm bằng chứng | Ví dụ | Điều cần tránh |
|---|---|---|
| Điều kiện kích hoạt | Inject, cảnh báo, nhật ký lỗi đã rút gọn | Khẳng định mất dịch vụ thật khi chỉ mô phỏng |
| Danh tính và phê duyệt | Mã yêu cầu, người phê duyệt, thời điểm, phạm vi | Dùng một tài khoản chung làm mất khả năng quy trách nhiệm |
| Cấp quyền | Mã grant, tài nguyên, quyền, thời hạn | Chỉ lưu ảnh giao diện mà không biết nguồn và thời điểm |
| Sử dụng | Mã phiên, nhật ký thao tác, bản ghi phiên theo chính sách | Ghi credential trong transcript hoặc ảnh |
| Khôi phục | Kết quả kiểm tra chức năng, xác nhận chủ dịch vụ | Chỉ dựa vào việc đăng nhập thành công |
| Thu hồi | Sự kiện kết thúc phiên, xóa quyền tạm, kiểm tra từ chối | Chỉ chờ TTL rồi giả định tất cả truy cập đã hết |
| Trở lại bình thường | Kiểm tra đường quản trị thường, đối soát cấu hình | Để lại tài khoản hoặc cấu hình tạm chưa có chủ sở hữu |

Không cần sao chép mọi log vào một báo cáo duy nhất. Có thể dùng tham chiếu đến nguồn gốc có phân quyền và chính sách lưu giữ phù hợp. Nếu dùng bản xuất, cần bảo vệ nội dung và duy trì thông tin nguồn.

Mã băm có thể hỗ trợ phát hiện thay đổi của một bản xuất, nhưng không tự chứng minh dữ liệu gốc là đúng hoặc đầy đủ. Vẫn cần kiểm soát nguồn, quyền truy cập, thời gian và chuỗi bàn giao.

### Đối soát thời gian

Thống nhất múi giờ và cách ghi thời gian trước buổi diễn tập. Ưu tiên dấu thời gian có offset hoặc UTC, đồng thời ghi chênh lệch đồng hồ đã biết.

Ví dụ, nếu nhật ký của máy đích chậm hai phút so với PAM, sự kiện “thu hồi trước khi cấp quyền” có thể là sai lệch thời gian. Báo cáo phải chỉ rõ giới hạn đo thay vì sửa mốc thời gian để tạo một chuỗi đẹp mắt.

## 12. Đo kết quả đúng cách

Nên ghi các mốc riêng:

- `t0`: tình huống được đưa ra hoặc sự cố thử nghiệm bắt đầu.
- `t1`: người trực xác nhận điều kiện sử dụng break-glass.
- `t2`: phê duyệt hoàn tất.
- `t3`: quyền khẩn cấp sẵn sàng sử dụng.
- `t4`: tác vụ phục hồi hoàn tất và dịch vụ được xác nhận.
- `t5`: quyền cùng phiên khẩn cấp đã được thu hồi và kiểm chứng.
- `t6`: bằng chứng được đối soát và bàn giao đầy đủ.

Các khoảng đo:

~~~text
Thời gian nhận diện          = t1 - t0
Thời gian phê duyệt          = t2 - t1
Thời gian chuẩn bị truy cập  = t3 - t2
Thời gian phục hồi           = t4 - t0
Thời gian tồn dư sau tác vụ  = t5 - t4
Thời gian đóng bằng chứng    = t6 - t5
~~~

Trong một buổi diễn tập, các nhóm có thể làm song song; mô hình tuyến tính trên giúp đo chuỗi nền. Nếu hoạt động chồng lấn, lưu thời điểm thực tế và phân tích đường quyết định gây chậm, không cộng các khoảng chồng lấn thành tổng thời gian.

### Ví dụ đánh giá

Giả sử kế hoạch đã đặt mục tiêu phục hồi trong 20 phút, thu hồi trong 5 phút sau khi hoàn tất tác vụ và thời hạn cấp quyền là 30 phút:

| Mốc | Thời điểm tương đối |
|---|---:|
| Bắt đầu tình huống | Phút 0 |
| Xác nhận cần break-glass | Phút 3 |
| Phê duyệt xong | Phút 7 |
| Quyền dùng được | Phút 10 |
| Dịch vụ được xác nhận phục hồi | Phút 18 |
| Phiên và quyền đã thu hồi | Phút 24 |

Kết quả:

- Phục hồi trong 18 phút: đạt mục tiêu 20 phút.
- Thu hồi sau tác vụ mất 6 phút: không đạt mục tiêu 5 phút.
- Quyền đã kết thúc trước thời hạn cấp 30 phút không làm mất đi phát hiện chậm thu hồi.
- Cần xác định bước nào gây chậm: phát hiện phiên còn mở, đồng bộ quyền, thao tác thủ công hay thiếu người xác nhận.

Đánh giá tổng thể có thể là “đạt phục hồi, chưa đạt kết thúc truy cập”. Không ghi toàn bộ buổi diễn tập đạt chỉ vì một chỉ số tốt.

### Chỉ số bổ sung

Có thể theo dõi tỷ lệ kịch bản đạt đủ tiêu chí bắt buộc, số bước phải nhờ trợ giúp ngoài runbook, tỷ lệ bằng chứng bắt buộc truy xuất được và tỷ lệ hành động khắc phục đã kiểm thử lại.

Khi dùng tỷ lệ, luôn công bố mẫu số. “100% thu hồi thành công” trên một phiên ở lab không đủ chứng minh toàn bộ hệ thống đã đáp ứng ở quy mô production.

## 13. Các lỗi dễ bị che khuất

### 13.1. Chuẩn bị một đường tắt chỉ cho buổi diễn tập

Nếu đội diễn tập tạo một tài khoản đặc biệt mà vận hành bình thường không có, buổi diễn tập có thể chỉ chứng minh đường tắt đó hoạt động.

Cần dùng cơ chế đại diện cho thiết kế thực và ghi rõ mọi khác biệt của môi trường thử nghiệm. Những bước phải chuẩn bị riêng cũng là dữ liệu để đánh giá khả năng sẵn sàng.

### 13.2. Tất cả đều biết trước từng inject

Cho người thực hiện biết toàn bộ chi tiết có thể phù hợp trong buổi đào tạo ban đầu. Khi mục tiêu là kiểm tra khả năng ra quyết định, một số inject nên chỉ do điều phối viên giữ, trong phạm vi rủi ro và phương án dừng đã thống nhất.

Không dùng yếu tố bất ngờ để vượt qua quyền kiểm soát thay đổi hoặc tạo gián đoạn ngoài phạm vi.

### 13.3. Gộp mất khả năng truy cập với nghi ngờ xâm phạm

IdP không phản hồi và IdP có dấu hiệu bị kiểm soát bởi kẻ tấn công là hai tình huống khác nhau. Ở trường hợp thứ hai, một credential, thiết bị hoặc kênh phê duyệt liên quan có thể không còn đáng tin.

Diễn tập cần kiểm tra quyết định lựa chọn đường tin cậy phù hợp, không chỉ cố làm mọi thứ hoạt động trở lại thật nhanh.

### 13.4. Chỉ kiểm tra kết nối mới sau thu hồi

Đăng nhập mới bị từ chối nhưng phiên đang mở vẫn còn quyền là tồn dư truy cập. Kiểm tra cần bao phủ các loại phiên, token và entitlement có liên quan đến kịch bản, với bằng chứng riêng.

### 13.5. Luân chuyển credential gây gián đoạn khác

Nếu credential khẩn cấp bị dùng nhầm làm credential của dịch vụ, việc đổi bí mật có thể làm ứng dụng lỗi. Đây là phát hiện về kiểm kê, tách biệt danh tính hoặc dependency; không nên che bằng cách bỏ luân chuyển mãi mãi.

Cần xác định chủ sở hữu, ảnh hưởng và phương án sửa trước khi thực hiện thay đổi có thể gây gián đoạn.

### 13.6. Bằng chứng chứa bí mật

Một ảnh chụp vault hoặc transcript có thể vô tình lưu credential dài hạn. Việc có phân quyền kho bằng chứng không làm cho sao chép bí mật trở thành lựa chọn mặc định.

Thiết kế bằng chứng bằng mã tham chiếu, sự kiện và metadata. Nếu nghi ngờ đã ghi lộ bí mật, xử lý theo quy trình sự cố và kiểm soát bản sao; không chỉ xóa ảnh khỏi báo cáo rồi coi là xong.

## 14. Rút kinh nghiệm và khép vòng khắc phục

Tổ chức trao đổi ngắn ngay sau buổi diễn tập để ghi nhận sự kiện còn mới. Sau đó phân tích bằng chứng trước khi phát hành kết luận chính thức.

Mỗi phát hiện nên có:

1. Điều mong đợi theo kế hoạch hoặc runbook.
2. Điều thực tế đã xảy ra, có mã bằng chứng.
3. Ảnh hưởng đến phục hồi hoặc kiểm soát quyền.
4. Nguyên nhân đã xác định và phần còn là giả thuyết.
5. Chủ sở hữu, hành động, mức ưu tiên và thời hạn.
6. Phương pháp kiểm thử lại cùng điều kiện đóng.

Ví dụ:

| Phát hiện | Bằng chứng | Hành động | Tiêu chí đóng |
|---|---|---|---|
| Tìm runbook mất 6 phút vì cổng tài liệu phụ thuộc IdP | Nhật ký quan sát và thử truy cập | Cung cấp bản dự phòng có kiểm soát, chỉ định người cập nhật | Người trực khác tìm được bản đúng trong kịch bản IdP lỗi |
| Phiên còn hoạt động sau khi bỏ vai trò | Sự kiện thu hồi và kiểm tra phiên trong lab | Bổ sung cơ chế kết thúc phiên và bước xác minh | Phiên cũ mất khả năng thực hiện tác vụ theo mục tiêu đã duyệt |
| Cảnh báo gửi đến nhóm không còn trực | Bản ghi giao nhận cảnh báo | Sửa người nhận và cơ chế xác nhận tiếp nhận | Inject tạo cảnh báo đến đúng nhóm và có xác nhận |
| Người phê duyệt thay thế chưa có thẩm quyền | Đối chiếu ma trận trách nhiệm | Cập nhật phân công, quyền và hướng dẫn | Thay thế thực hiện được quyết định trong lần kiểm thử lại |

“Đã sửa runbook” là kết quả của một hành động, chưa luôn là bằng chứng vấn đề đã hết. Với phát hiện kỹ thuật hoặc phối hợp, cần thử lại để chứng minh thay đổi có hiệu lực.

Tần suất diễn tập nên dựa trên rủi ro dịch vụ, kết quả lần trước và thay đổi kiến trúc. Ngoài lịch định kỳ, cần cân nhắc kiểm thử lại sau thay đổi IdP, PAM, vault, mạng quản trị, cơ chế MFA, người giữ trách nhiệm hoặc quy trình thu hồi.

## 15. Bài thực hành

### Bối cảnh

Bạn quản lý PAM cho một hệ thống thử nghiệm gồm dịch vụ ứng dụng, một máy quản trị và một tài nguyên ngoài phạm vi dùng để kiểm tra giới hạn quyền.

Đường truy cập thông thường được giả định gián đoạn. Đội cần thực hiện một thay đổi cấu hình vô hại trên máy quản trị thử nghiệm. Người phê duyệt chính không sẵn sàng; người thay thế đã được chỉ định từ trước. Credential thật và dữ liệu production không nằm trong bài tập.

### Yêu cầu

1. Viết kế hoạch một trang gồm mục tiêu, tài nguyên đích, vai trò, điều kiện kích hoạt, mục tiêu thời gian, tiêu chí dừng và hoàn tác.
2. Vẽ chuỗi dependency từ tìm runbook đến thu hồi quyền; đánh dấu phần vẫn phụ thuộc đường truy cập đang lỗi.
3. Soạn bảng inject tối đa ba tình huống, mỗi tình huống có hành vi mong đợi và bằng chứng.
4. Thực hiện ở lab hoặc diễn tập trên bàn nếu chưa có môi trường phù hợp; ghi rõ mức kiểm chứng.
5. Thu mốc thời gian, mã yêu cầu, mã quyền/phiên, kết quả tác vụ và bằng chứng thu hồi.
6. Thực hiện kiểm tra giới hạn quyền và kiểm tra kết thúc phiên trong phạm vi được duyệt.
7. Viết báo cáo có ít nhất một giả định chưa kiểm chứng và một hành động khắc phục có tiêu chí kiểm thử lại.

### Tiêu chí đánh giá

Một bài thực hành đạt khi:

- Giải thích được vì sao cần kích hoạt break-glass và ai có thẩm quyền.
- Quyền được giới hạn theo nhu cầu và có thời điểm kết thúc.
- Người khác có thể liên kết từ yêu cầu đến tác vụ và thu hồi bằng các mã bằng chứng.
- Không đưa giá trị credential vào hồ sơ.
- Xác nhận được kết quả dịch vụ và trạng thái truy cập sau diễn tập bằng hai nhóm kiểm tra riêng.
- Báo cáo phân biệt điều đã thực hiện, điều chỉ mô phỏng và điều chưa kiểm chứng.
- Những tiêu chí chưa đạt được giữ lại thành phát hiện, không bị xóa để ghi “thành công”.

## 16. Câu hỏi tự kiểm tra

**1. Vì sao lấy được mật khẩu khẩn cấp chưa đủ chứng minh diễn tập thành công?**

Vì còn phải chứng minh danh tính và phê duyệt đúng, kết nối đúng đích, hoàn thành tác vụ tối thiểu, lưu bằng chứng và kết thúc toàn bộ quyền truy cập phát sinh.

**2. Có cần làm IdP production ngừng hoạt động để diễn tập không?**

Không phải mặc định. Có thể bắt đầu bằng thảo luận, lab hoặc mô phỏng có giới hạn. Báo cáo phải phản ánh đúng mức kiểm chứng; thao tác trên production cần phạm vi, quyền phê duyệt và phương án phục hồi thích hợp.

**3. Nếu collector log lỗi giữa diễn tập thì có được tiếp tục không?**

Quyết định theo chính sách và kế hoạch đã duyệt. Nếu có kiểm soát bù phù hợp, thực hiện và ghi rõ giới hạn. Nếu điều kiện bắt buộc không còn được đáp ứng và không có phương án bù được chấp thuận, dừng phần việc liên quan.

**4. Vì sao đổi mật khẩu không thay thế kiểm tra thu hồi phiên?**

Cơ chế phiên và token có thể tiếp tục tồn tại độc lập với mật khẩu. Cần kiểm chứng từng loại truy cập áp dụng, không suy ra từ một thao tác quản lý bí mật.

**5. Diễn tập đạt mục tiêu phục hồi nhưng thiếu bằng chứng thu hồi được đánh giá thế nào?**

Ghi nhận phục hồi đạt, còn mục tiêu kết thúc truy cập chưa được chứng minh. Không kết luận đạt toàn bộ các kiểm soát bắt buộc.

**6. Khi nào có thể đóng một phát hiện?**

Khi hành động đã hoàn thành và bằng chứng kiểm thử lại đáp ứng tiêu chí đóng phù hợp. Việc giao người phụ trách hoặc cập nhật tài liệu đơn thuần chưa luôn đủ.

Diễn tập break-glass có giá trị khi tạo ra bằng chứng về khả năng phục hồi và khả năng kiểm soát quyền trong cùng một quy trình. Kết quả cần giúp tổ chức biết rõ điều gì đã hoạt động, điều gì còn yếu và phải kiểm chứng lại điều gì trước lần khẩn cấp tiếp theo.
