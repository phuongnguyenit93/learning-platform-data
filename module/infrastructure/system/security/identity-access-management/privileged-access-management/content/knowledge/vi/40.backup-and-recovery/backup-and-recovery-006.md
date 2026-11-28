# Restore test: kiểm chứng khả năng khôi phục hệ thống PAM

Một tác vụ backup báo thành công chỉ chứng minh quá trình tạo bản sao đã kết thúc theo kiểm tra của công cụ backup. Nó chưa chứng minh đội vận hành có thể dựng lại hệ thống Privileged Access Management (PAM), giải mã đúng dữ liệu, đăng nhập bằng cơ chế phục hồi, cấp quyền có kiểm soát và ghi lại bằng chứng sau sự cố.

Restore test là một cuộc kiểm thử có kế hoạch nhằm chứng minh chuỗi khôi phục đó bằng thao tác thực tế. Với PAM, câu hỏi nghiệm thu không dừng ở “dịch vụ đã chạy lại”, mà là: **hệ thống đã khôi phục có thể kiểm soát quyền đặc biệt một cách đúng đắn, trong thời gian cho phép, với trạng thái credential và quyền truy cập đã được đối chiếu hay chưa?**

Bài học tập trung vào kiểm thử khôi phục PAM trong môi trường được cấp phép và cách ly. Các bước mô tả là khung thiết kế trung lập với sản phẩm; cách sao lưu nhất quán, thứ tự phục hồi thành phần và thao tác với kho khóa phải theo cơ chế được sản phẩm thực tế hỗ trợ.

## 1. Mục tiêu của một restore test

Sau bài học, người học có thể:

- Phân biệt kiểm tra tính toàn vẹn bản sao với kiểm thử khôi phục dịch vụ PAM.
- Xác định các thành phần và phụ thuộc cần có để khôi phục một luồng truy cập đặc quyền.
- Thiết kế bài kiểm thử có môi trường cách ly, dữ liệu thử và giới hạn kết nối rõ ràng.
- Đo RPO, RTO và xác định phần thời gian thường bị bỏ sót.
- Xử lý rủi ro credential, quyền truy cập và phiên bị lệch về quá khứ sau restore.
- Xây dựng tiêu chí PASS/FAIL và gói bằng chứng có thể kiểm tra lại.

Một cuộc kiểm thử tốt phải tạo ra kết luận có giới hạn rõ ràng. Nếu chỉ khôi phục được cơ sở dữ liệu, kết luận là “khôi phục cơ sở dữ liệu đạt”; không mở rộng thành “PAM đã sẵn sàng phục vụ”.

## 2. Vì sao PAM cần kiểm thử khôi phục riêng?

PAM thường nằm trên đường truy cập tới những hệ thống cần dùng để khắc phục sự cố: máy chủ, thiết bị mạng, hạ tầng ảo hóa, dịch vụ danh tính hoặc kho bí mật của ứng dụng. Khi PAM ngừng hoạt động, tổ chức có thể mất cả công cụ quản lý quyền lẫn đường truy cập để sửa công cụ đó.

Có bốn lớp rủi ro cần kiểm chứng cùng nhau.

| Lớp | Điều cần chứng minh | Ví dụ thất bại dù dữ liệu đã restore |
| --- | --- | --- |
| Dữ liệu | Cấu hình, tài khoản, policy và quan hệ được phục hồi nhất quán | Kho bí mật có bản ghi nhưng thiếu metadata để xác định tài khoản đích |
| Mật mã | Dữ liệu được giải mã bằng đúng khóa, đúng cơ chế phục hồi | Backup còn nguyên nhưng không có quyền sử dụng khóa cần thiết |
| Chức năng | Luồng yêu cầu, phê duyệt, cấp quyền và truy cập hoạt động | Portal đăng nhập được nhưng session broker không mở được phiên |
| Kiểm soát | Least privilege, thu hồi, TTL và audit vẫn có hiệu lực | Bản sao cũ làm xuất hiện lại một grant đã bị thu hồi |

Tính sẵn sàng và tính an toàn phải được đánh giá độc lập. Một PAM hoạt động nhưng cấp lại quyền đã thu hồi không đáp ứng tiêu chí khôi phục an toàn. Ngược lại, một kho dữ liệu nguyên vẹn nhưng không thể phục vụ người dùng cũng chưa đáp ứng mục tiêu sẵn sàng.

## 3. Xác định phạm vi trước khi chọn bản backup

### 3.1. Đơn vị cần khôi phục là một dịch vụ có phụ thuộc

Một luồng truy cập PAM có thể đi qua nhiều thành phần:

```text
Người dùng thử
    -> xác thực và MFA
    -> yêu cầu quyền / phê duyệt
    -> policy / JIT
    -> vault hoặc cơ chế cấp credential
    -> session broker / connector
    -> máy đích thử nghiệm
    -> audit / giám sát / lưu bằng chứng
```

Không phải sản phẩm nào cũng có đầy đủ các thành phần này. Đội kiểm thử cần lập sơ đồ đúng với kiến trúc đang dùng, thay vì biến danh sách trên thành một yêu cầu cài đặt mặc định.

Phạm vi có thể gồm:

- Cơ sở dữ liệu cấu hình, inventory tài khoản và ánh xạ tài khoản với máy đích.
- Kho bí mật và metadata mô tả phiên bản, trạng thái luân chuyển, chủ sở hữu.
- Policy, role, nhóm, cấu hình phê duyệt và quy tắc JIT/JEA.
- Thành phần quản lý, session broker, gateway và connector.
- Chứng thư, trust store, cấu hình tích hợp và tham chiếu tới khóa.
- Kho audit, chỉ mục tìm kiếm và bản ghi phiên nếu chúng nằm trong mục tiêu phục hồi.
- Cấu hình kết nối tới hệ thống danh tính, MFA, DNS, NTP, PKI, KMS hoặc HSM.

Đánh dấu rõ thành phần nào được phục hồi từ backup, thành phần nào dựng lại từ cấu hình chuẩn, thành phần nào được giả lập và thành phần nào nằm ngoài kiểm thử.

### 3.2. Kiểm tra vòng phụ thuộc phục hồi

Một vòng phụ thuộc nguy hiểm có dạng:

```text
Muốn restore vault -> cần credential kho backup
Credential kho backup -> chỉ nằm trong vault đang hỏng
```

Tình huống tương tự có thể xuất hiện với tài khoản quản trị hypervisor, quyền dùng KMS, recovery material hoặc tài khoản truy cập hạ tầng mạng.

Restore test phải xác minh đội phục hồi có đường bootstrap độc lập theo thiết kế đã phê duyệt. Đường này cần có chủ sở hữu, kiểm soát truy cập, cách lấy vật liệu phục hồi và cách ghi nhận việc sử dụng.

Không đưa recovery material thật vào ticket hoặc báo cáo. Bằng chứng chỉ cần cho thấy đúng người có thể tiếp cận đúng vật liệu theo quy trình; không cần tiết lộ giá trị của vật liệu đó.

### 3.3. Chốt giả định sự cố

Mỗi kịch bản cần mô tả điều kiện ban đầu, ví dụ:

- Mất một node quản lý, nhưng dịch vụ khóa và hệ thống danh tính vẫn hoạt động.
- Mất toàn bộ site chính, cần sử dụng hạ tầng tại site dự phòng.
- Mất cơ sở dữ liệu, cần phục hồi tới một điểm nhất quán.
- Nghi ngờ môi trường chính bị xâm nhập, phải dựng môi trường sạch và chọn điểm phục hồi được đánh giá.
- Mất một phụ thuộc phục hồi quan trọng, cần chứng minh phương án thay thế đã được phê duyệt.

Khôi phục khi hạ tầng chính còn nguyên không đại diện đầy đủ cho kịch bản mất cả site. Một bài kiểm thử không nên nhận công lao cho những phụ thuộc chưa từng bị loại khỏi giả định.

## 4. RPO và RTO phải đo như thế nào?

### 4.1. RPO: điểm dữ liệu thực sự khôi phục được

Recovery Point Objective (RPO) là mục tiêu về mức mất dữ liệu chấp nhận được, thường biểu diễn bằng thời gian. Khi kiểm thử, cần xác định thời điểm dữ liệu nhất quán cuối cùng thực sự được khôi phục.

```text
Khoảng mất dữ liệu của kịch bản
    = thời điểm sự cố quy ước
      - thời điểm dữ liệu nhất quán cuối cùng khôi phục được
```

Tên file backup hoặc thời điểm tác vụ backup kết thúc chưa chắc là thời điểm dữ liệu nhất quán. Với chuỗi backup và nhật ký, phải xác định được điểm phục hồi được hỗ trợ và xác minh chuỗi dữ liệu cần thiết còn đủ.

Ví dụ:

- Tác vụ backup kết thúc lúc 09:00.
- Điểm dữ liệu nhất quán có thể khôi phục của bản đó là 08:55.
- Thời điểm sự cố giả lập là 09:10.

Khoảng mất dữ liệu của kịch bản là 15 phút, không phải 10 phút.

Đối với PAM, “mất 15 phút dữ liệu” còn có ý nghĩa bảo mật. Trong 15 phút đó có thể đã xảy ra luân chuyển credential, thu hồi quyền hoặc thay đổi policy. Cần xác định các thay đổi này bằng nguồn đối chiếu tin cậy và hòa giải trước khi đưa dịch vụ trở lại phạm vi sử dụng đã cam kết.

### 4.2. RTO: thời gian tới khi được nghiệm thu phục vụ

Recovery Time Objective (RTO) là mục tiêu thời gian để khôi phục hoạt động tới mức dịch vụ đã xác định. Trong kế hoạch kiểm thử, chốt mốc bắt đầu và điểm kết thúc trước khi thực hiện.

```text
Thời gian khôi phục quan sát được
    = thời điểm dịch vụ đạt tiêu chí nghiệm thu
      - mốc bắt đầu khôi phục đã thống nhất
```

Nếu mục tiêu vận hành tính từ lúc tuyên bố sự cố, bài kiểm thử phải tính cả việc huy động người, lấy quyền truy cập, tìm bản sao, dựng hạ tầng và xác minh kiểm soát. Không chỉ đo thời gian chạy lệnh restore.

Ví dụ với mốc bắt đầu là 09:10:

| Mốc | Thời điểm |
| --- | --- |
| Tuyên bố sự cố giả lập | 09:10 |
| Bắt đầu thao tác phục hồi | 09:12 |
| Dịch vụ quản lý khởi động được | 09:40 |
| Đối chiếu credential và quyền hoàn tất | 09:55 |
| Luồng truy cập cùng audit được nghiệm thu | 10:02 |

Thời gian khôi phục đầu cuối là 52 phút. Thời gian từ thao tác đầu tiên tới nghiệm thu là 50 phút. Cả hai số có ích, nhưng số thứ hai không thay thế số thứ nhất khi mục tiêu tính từ lúc tuyên bố sự cố.

Nếu bài kiểm thử dùng hạ tầng chuẩn bị sẵn hoặc vật liệu đã đặt sẵn, ghi rõ phần thời gian được loại khỏi phép đo. Kết quả đó chưa chứng minh toàn bộ RTO của kịch bản dựng lại từ đầu.

### 4.3. Điểm phục hồi sạch có thể cũ hơn mục tiêu thông thường

Trong kịch bản nghi ngờ xâm nhập, bản mới nhất không tự động là bản thích hợp nhất. Có thể cần một điểm phục hồi cũ hơn đã được đánh giá, đồng thời áp dụng thêm biện pháp kiểm soát trước khi phục vụ.

Báo cáo riêng:

- Điểm dữ liệu phục hồi.
- Cơ sở lựa chọn điểm đó.
- Khoảng mất dữ liệu thực tế.
- Mục tiêu có đạt hay không.
- Biện pháp bù đắp và quyết định xử lý phần không đạt.

Không thay đổi mục tiêu sau khi kiểm thử chỉ để biến kết quả thất bại thành đạt.

## 5. Chọn mức kiểm thử phù hợp

Các mức dưới đây bổ sung cho nhau, không thay thế lẫn nhau.

| Mức kiểm thử | Phạm vi chính | Kết luận có thể đưa ra |
| --- | --- | --- |
| Kiểm tra artifact | Đọc được bản sao, kiểm tra manifest và tính toàn vẹn | Artifact được chọn có thể đọc và vượt qua kiểm tra đã định |
| Khôi phục thành phần | Dựng lại một cơ sở dữ liệu hoặc một dịch vụ | Thành phần đó khôi phục được trong điều kiện thử |
| Khôi phục đầu cuối | Dựng luồng từ yêu cầu quyền tới truy cập máy đích thử | Luồng PAM đã chọn hoạt động và giữ các kiểm soát được kiểm tra |
| Diễn tập mất site | Thực hiện theo giả định site chính không sử dụng được | Phương án DR được kiểm chứng trong phạm vi phụ thuộc đã mô phỏng |
| Phục hồi sau xâm nhập | Môi trường sạch, điểm phục hồi được đánh giá, hòa giải trạng thái | Quy trình phục hồi an toàn được kiểm chứng theo giả định sự cố |

Có thể kiểm tra artifact thường xuyên hơn và chạy diễn tập đầu cuối theo lịch riêng. Tuy nhiên, tỷ lệ tác vụ backup thành công cao không bù được việc chưa từng thực hiện kiểm thử đầu cuối.

Việc chuyển sang một replica đang hoạt động cũng không tự chứng minh khả năng phục hồi từ backup. Replica có thể đã tiếp nhận lỗi logic hoặc trạng thái không mong muốn cùng với hệ thống chính.

## 6. Thiết kế môi trường cách ly

### 6.1. Cách ly phải được chứng minh

Khôi phục một bản sao PAM vào lab có thể đưa theo endpoint, job, connector và cấu hình tác vụ của môi trường thật. Nếu để chúng tự chạy, môi trường thử có thể luân chuyển credential, gửi yêu cầu hoặc mở phiên tới máy sản xuất.

Trước khi bật thành phần được khôi phục, cần xác minh:

- Mạng thử không có đường tới máy đích sản xuất và các API quản trị sản xuất nằm ngoài phạm vi.
- Egress được giới hạn tới những đích đã phê duyệt cho bài thử.
- DNS, tên dịch vụ, địa chỉ quảng bá và chứng thư không làm người dùng thật đi nhầm vào lab.
- Job luân chuyển, discovery, đồng bộ quyền, tác vụ lịch và connector chưa được phép chạy đều được vô hiệu hóa hoặc chặn ở lớp độc lập.
- Tích hợp email, webhook, ITSM và SIEM được chuyển tới đích thử hoặc được chặn theo kế hoạch.
- Bản clone không tự gia nhập cụm đang phục vụ thật.

Nút tắt scheduler trong ứng dụng không đủ làm bằng chứng duy nhất. Một lớp chặn kết nối độc lập giúp giảm rủi ro khi trạng thái job trong bản backup khác với dự kiến.

Có thể dùng kiểm tra kết nối bị từ chối, log firewall hoặc flow log để chứng minh ranh giới mạng. Chỉ thực hiện phép thử tới những địa chỉ và dịch vụ thuộc phạm vi đã được cấp phép.

### 6.2. Môi trường thử vẫn chứa dữ liệu nhạy cảm

Nếu sử dụng backup sản xuất, bản khôi phục có thể chứa bí mật, lịch sử phiên, tên tài khoản và cấu hình nhạy cảm. Môi trường thử phải được bảo vệ tương xứng với dữ liệu đó.

Dùng dữ liệu tổng hợp khi mục tiêu kiểm thử cho phép. Nếu cần kiểm thử tính đại diện bằng backup thật, giới hạn người truy cập, nơi lưu, thời gian giữ và cách hủy dữ liệu theo kế hoạch.

Không xuất mật khẩu, private key, token hoặc recovery material để chứng minh restore thành công. Không ghi chúng vào console, ảnh chụp màn hình hoặc báo cáo.

### 6.3. Xác định phụ thuộc thật và phụ thuộc thay thế

Một hệ thống danh tính giả lập có thể đủ để kiểm tra luồng chức năng nhưng chưa chứng minh tích hợp với hệ thống danh tính dự phòng thật. Tương tự, một kho khóa thử không chứng minh khả năng tiếp cận vật liệu khóa phục hồi của môi trường vận hành.

Ghi nhãn từng phụ thuộc:

```yaml
dependency_coverage:
  identity_provider: test_instance
  target_system: synthetic_host
  key_service: approved_recovery_test_path
  audit_sink: isolated_collector
  production_connectivity: denied
```

Đây là ví dụ mô tả phạm vi, không phải cấu hình triển khai cho một sản phẩm cụ thể.

## 7. Chuẩn bị hợp đồng kiểm thử và dữ liệu mốc

Một bài kiểm thử nên có hồ sơ được thống nhất trước khi thực hiện.

```yaml
restore_test:
  id: PAM-RESTORE-EXERCISE-042
  scenario: loss_of_management_plane
  environment: isolated_recovery_lab
  backup_id: backup-example-042
  recovery_point_utc: "2030-04-18T01:55:00Z"
  incident_reference_utc: "2030-04-18T02:10:00Z"
  objectives:
    rpo_minutes: 15
    rto_minutes: 60
    rto_start: incident_declaration
    rto_end: approved_end_to_end_acceptance
  required_checks:
    - authorized_access
    - unauthorized_access_denied
    - grant_expiry
    - credential_reconciliation
    - audit_delivery
  stop_conditions:
    - unexpected_production_connectivity
    - secret_exposure
    - unexpected_credential_change
```

Các con số và thời điểm trong ví dụ chỉ phục vụ diễn giải; mục tiêu thực tế phải xuất phát từ yêu cầu dịch vụ.

### 7.1. Vai trò cần có

- Người điều phối chốt phạm vi, mốc thời gian và quyết định dừng.
- Người vận hành thực hiện runbook và ghi nhận từng bước.
- Người quản lý khóa hoặc recovery material thực hiện phần việc được phân quyền.
- Chủ hệ thống đích xác nhận trạng thái credential và tác động nghiệp vụ trong phạm vi thử.
- Người nghiệm thu đối chiếu tiêu chí với bằng chứng.

Có thể một người kiêm nhiều vai trò nếu chính sách cho phép, nhưng không làm mất yêu cầu phân tách trách nhiệm hoặc quorum đã được thiết kế cho quy trình phục hồi.

### 7.2. Tạo các mốc kiểm chứng không chứa bí mật

Với dữ liệu thử, có thể tạo trước backup:

- Một tài khoản quản trị thử thuộc đúng nhóm được phép.
- Một tài khoản thử không có quyền truy cập.
- Một policy yêu cầu phê duyệt cho tài sản nhạy cảm giả lập.
- Một grant có TTL xác định.
- Một yêu cầu bị từ chối.
- Một phiên thử có mã tương quan.
- Một phiên bản credential được đánh dấu bằng ID hoặc thời điểm luân chuyển.

Sau điểm backup, tạo thêm các thay đổi có kiểm soát để kiểm tra lệch trạng thái, chẳng hạn thu hồi grant hoặc luân chuyển credential trên máy đích thử.

Bằng chứng đối chiếu dùng ID, timestamp, kết quả xác thực và trạng thái. Không cần lưu giá trị credential, cũng không dùng hash của mật khẩu làm bằng chứng mặc định.

## 8. Runbook kiểm thử khôi phục đầu cuối

### Bước 1 — Ghi nhận điểm xuất phát

Ghi mã bài thử, người tham gia, giả định sự cố, bản backup được chọn và các mốc RPO/RTO. Xác nhận nguồn thời gian của các thành phần để có thể đối chiếu log.

Chốt trước những việc được chuẩn bị sẵn. Nếu lab đã có hạ tầng, certificate hoặc image cài đặt, ghi rõ chúng có nằm trong thời gian đo hay không.

### Bước 2 — Chứng minh ranh giới cách ly

Kiểm tra đường mạng, endpoint và trạng thái job trước khi dịch vụ có khả năng thực thi tác vụ được bật. Ghi lại kết quả của các phép kiểm tra được cấp phép.

Nếu phát hiện kết nối ngoài phạm vi hoặc thay đổi credential không mong đợi, kích hoạt điều kiện dừng. Giữ lại bằng chứng, cô lập thành phần liên quan và đánh giá tác động trước khi tiếp tục.

Không tiếp tục restore với giả định rằng sẽ sửa endpoint sau khi hệ thống đã chạy.

### Bước 3 — Chuẩn bị hạ tầng và phụ thuộc bootstrap

Dựng nền tảng, lưu trữ, nguồn thời gian, phân giải tên và các phụ thuộc được xác định trong kế hoạch. Xác nhận phiên bản phần mềm và đường phục hồi tương thích với bản backup.

Đảm bảo có thể truy cập bản sao và sử dụng cơ chế khóa phục hồi bằng quy trình độc lập đã phê duyệt. Không tạm thời nới quyền quản trị rộng để che đi một bước bootstrap thất bại.

### Bước 4 — Xác minh bộ backup

Kiểm tra danh tính bản sao, thời điểm phục hồi, thành phần đi kèm và tính đầy đủ của chuỗi backup nếu có.

Kiểm tra checksum giúp phát hiện một số dạng sai hỏng, nhưng checksum chỉ đáng tin khi giá trị đối chiếu đến từ nguồn được bảo vệ. Checksum nằm ngay cạnh một bản sao có thể bị sửa đồng thời không tự chứng minh tính xác thực của bản sao.

Xác minh manifest hoặc cơ chế xác thực mà hệ thống sử dụng, quyền đọc bản sao và điều kiện giải mã. Nếu nghi ngờ xâm nhập, việc bản sao nguyên vẹn về byte không đồng nghĩa dữ liệu bên trong sạch.

### Bước 5 — Restore theo thứ tự được hỗ trợ

Thực hiện trình tự khôi phục của sản phẩm, bao gồm quan hệ nhất quán giữa cơ sở dữ liệu, kho bí mật, metadata, cấu hình và vật liệu mật mã.

Không giả định có thể ghép tùy ý cơ sở dữ liệu lúc T1 với kho bí mật lúc T2. Nếu sản phẩm hỗ trợ phục hồi theo điểm thời gian hoặc chuỗi nhật ký, dùng đúng cơ chế và xác nhận điểm nhất quán đã đạt.

Với khóa do KMS/HSM quản lý, kiểm thử phải dùng phương án phục hồi được hỗ trợ cho thiết kế đó. Không giả định khóa luôn có thể xuất ra file hoặc có thể phục hồi chỉ bằng bản backup của ứng dụng PAM.

Ghi thời điểm bắt đầu, kết thúc và lỗi của từng giai đoạn. Nếu phải thao tác ngoài runbook, ghi lại thao tác cùng lý do để cập nhật quy trình sau bài thử.

### Bước 6 — Khởi động có kiểm soát

Bật từng thành phần cần thiết trong môi trường cách ly. Kiểm tra sức khỏe dịch vụ, liên kết thành phần, chứng thư, trust, cấu hình kết nối và khả năng truy cập dữ liệu.

Đăng nhập quản trị thành công chỉ là một checkpoint kỹ thuật. Chưa tuyên bố đạt RTO nếu những kiểm tra quyền, credential và audit bắt buộc còn chưa hoàn tất.

### Bước 7 — Hòa giải trạng thái sau điểm phục hồi

Đối chiếu dữ liệu phục hồi với nguồn tin cậy cho các thay đổi sau điểm backup:

- Credential đã được luân chuyển hoặc bị vô hiệu hóa.
- Tài khoản và quyền đã bị thu hồi.
- Thiết bị hoặc tài khoản đã bị loại khỏi phạm vi quản lý.
- Policy và cấu hình trust đã thay đổi.
- Phiên, token hoặc grant có thể không còn hợp lệ.

Trong lab, đối chiếu bằng các thay đổi tổng hợp đã chuẩn bị. Khi áp dụng quy trình cho phục hồi thật, nguồn đối chiếu có thể là hệ thống danh tính, hệ thống đích, nhật ký độc lập hoặc hồ sơ thay đổi được bảo vệ, tùy kiến trúc.

Không sao chép trạng thái từ một nguồn chưa đáng tin trong kịch bản xâm nhập chỉ để làm hai phía khớp nhau.

### Bước 8 — Thử luồng truy cập và các kiểm soát âm

Thực hiện các luồng đại diện theo tiêu chí đã chốt. Bao gồm cả trường hợp được phép và trường hợp phải bị từ chối.

Đối với JIT/JEA, xác minh phạm vi, TTL và giới hạn thao tác thực tế. Đối với phiên qua broker, xác minh mở phiên tới máy đích thử và khả năng quy thuộc phiên về đúng người dùng, yêu cầu và tài khoản đích.

Không chỉ nhìn cấu hình hiển thị trên portal. Một policy tồn tại trong cơ sở dữ liệu chưa chứng minh nó đã được áp dụng trên luồng truy cập thực tế.

### Bước 9 — Xác minh audit và bằng chứng phiên

Tạo sự kiện mới sau restore và lần theo mã tương quan qua các thành phần. Kiểm tra sự kiện được chuyển tới kho log thử, timestamp có thể đối chiếu, danh tính và kết quả đủ để giải thích hành động.

Nếu khả năng xem lại bản ghi phiên cũ nằm trong mục tiêu, chọn mẫu dữ liệu đã định và xác minh truy xuất được bằng cơ chế được hỗ trợ. Việc tạo được log mới không chứng minh các bản ghi cũ đã được phục hồi.

### Bước 10 — Nghiệm thu, đóng bài thử và xử lý tồn tại

Chốt thời điểm nghiệm thu, tính các chỉ số, ghi kết quả từng tiêu chí và phân loại giới hạn kiểm thử. Đưa mỗi lỗi thành một đầu việc có chủ sở hữu và điều kiện kiểm thử lại.

Khi kết thúc, xử lý tài nguyên lab và dữ liệu nhạy cảm theo kế hoạch. Không để lại bản clone PAM chạy với cấu hình hoặc credential còn hiệu lực ngoài thời gian thử.

## 9. Bẫy quan trọng: vault và máy đích không cùng phiên bản credential

Giả sử có chuỗi sự kiện sau:

```text
T1: Vault và máy đích thử đều dùng credential phiên bản A.
T2: Tạo backup chứa phiên bản A.
T3: Hệ thống luân chuyển; vault và máy đích thử chuyển sang phiên bản B.
T4: Restore vault từ T2; máy đích thử vẫn đang ở phiên bản B.
```

Sau T4, vault phục hồi chứa A trong khi máy đích cần B. Dữ liệu backup có thể hoàn toàn hợp lệ nhưng luồng truy cập thất bại.

Cách kiểm thử đúng:

1. Dùng tài khoản và máy đích tổng hợp thuộc phạm vi bài thử.
2. Ghi lại ID phiên bản hoặc mốc luân chuyển trước và sau backup.
3. Xác nhận bài thử phát hiện được trạng thái không khớp.
4. Thực hiện quy trình reconcile hoặc thiết lập lại credential được sản phẩm và chủ hệ thống đích hỗ trợ.
5. Kiểm tra luồng truy cập qua PAM thành công với trạng thái đã hòa giải.
6. Khi quy trình đã vô hiệu hóa phiên bản cũ, kiểm tra phiên bản cũ bị từ chối theo thiết kế.
7. Kiểm tra audit ghi lại việc hòa giải và người thực hiện.

Bước reconcile có thể cần tài khoản phục hồi hoặc cơ chế độc lập. Không mặc định mọi sản phẩm có cùng cách phát hiện và sửa lệch trạng thái.

Không kiểm chứng bằng cách ép máy đích sản xuất quay lại credential cũ trong backup. Trong lab, việc khôi phục cả vault lẫn máy đích về cùng snapshot cũng có thể làm biến mất tình huống lệch trạng thái cần kiểm thử; nếu dùng cách đó, phải có một nhánh thử riêng cho credential drift.

Đừng chỉ kiểm tra đăng nhập mới. Tùy loại credential, phiên hoặc token đã cấp trước đó có thể có vòng đời khác với mật khẩu vừa đổi. Tiêu chí phải nêu rõ loại quyền truy cập nào cần bị vô hiệu hóa và cách xác minh.

## 10. Quyền bị thu hồi không được sống lại ngoài ý muốn

Khôi phục policy hoặc cơ sở dữ liệu cũ có thể làm xuất hiện lại dữ liệu về quyền đã bị thu hồi sau backup.

Một kịch bản kiểm thử nên gồm:

```text
Trước backup: người dùng thử U có grant G tới máy đích thử H.
Sau backup: G bị thu hồi.
Sau restore: xác minh G không trở thành quyền truy cập sử dụng được
             trước khi hoàn tất bước đối chiếu và kiểm soát đã quy định.
```

Không có một câu trả lời chung rằng mọi bản backup sẽ tự biết các lần thu hồi xảy ra sau đó. Đội thiết kế cần xác định nguồn trạng thái hiện hành và hàng rào trước khi đưa hệ thống phục hồi vào phục vụ.

Với grant có TTL, kiểm tra cả thời gian của hệ thống phục hồi. Đồng hồ sai có thể làm kết quả đánh giá hạn dùng sai hoặc làm log khó đối chiếu.

Với break-glass, kiểm tra quyền dùng, người giữ, cơ chế giám sát và bước xử lý sau sử dụng. Một tài khoản phục hồi hoạt động không đủ nếu nó mở ra đường truy cập không thể quy thuộc hoặc không có quy trình đóng lại.

Nếu thử nghiệm phát hiện quyền cũ được cấp lại, đó là lỗi kiểm soát cần ghi nhận. Không bỏ qua chỉ vì bài thử “chủ yếu đo tốc độ restore”.

## 11. Ma trận nghiệm thu tối thiểu cho luồng đã chọn

Mỗi tiêu chí phải có kết quả mong đợi, bằng chứng quan sát và người xác nhận.

| Phép thử | Kết quả mong đợi | Bằng chứng phù hợp |
| --- | --- | --- |
| Đọc và giải mã dữ liệu | Truy cập được dữ liệu mẫu bằng cơ chế được hỗ trợ | ID bản sao, log phục hồi, ID đối tượng mẫu |
| Truy cập hợp lệ | Người dùng đúng vai trò đi qua đủ bước bắt buộc | Request ID, quyết định policy, session ID |
| Truy cập trái quyền | Người dùng thiếu quyền bị từ chối, không tới được đích | Sự kiện deny và đối chiếu ở luồng đích thử |
| Phê duyệt | Yêu cầu cần phê duyệt không được cấp trước khi đủ điều kiện | Lịch sử trạng thái yêu cầu và grant |
| JIT và TTL | Quyền có hiệu lực đúng phạm vi, hết hạn theo thiết kế | Mốc cấp, mốc hết hạn, kết quả thử sau hạn |
| Thu hồi sau điểm backup | Quyền cũ được xử lý theo quy trình trước phục vụ | Kết quả đối chiếu, sự kiện thu hồi hoặc chặn |
| Credential drift | Phát hiện lệch và hòa giải được bằng quy trình đã định | ID phiên bản, kết quả trước/sau, audit reconcile |
| Giám sát phiên | Phiên được quy thuộc và ghi nhận theo yêu cầu | Session ID, metadata, kết quả truy xuất mẫu |
| Audit sau restore | Sự kiện mới tới kho thu thập trong giới hạn đã chốt | Mã tương quan, thời gian gửi/nhận, kết quả truy vấn |
| Cách ly | Không có tương tác ngoài phạm vi được phép | Chính sách mạng và log kiểm tra ranh giới |

Bằng chứng đăng nhập bị từ chối phải đủ để giải thích nguyên nhân. Nếu tài khoản bị từ chối chỉ vì dịch vụ đích đang tắt, phép thử đó không chứng minh policy PAM đã chặn đúng.

Tương tự, nếu audit không xuất hiện nhưng mọi phép truy cập đều thành công, kết quả đầu cuối vẫn không đạt khi audit là điều kiện bắt buộc.

## 12. Ghi kết quả và tránh PASS thiếu căn cứ

Có thể dùng bốn trạng thái:

- **PASS:** đã thực hiện và đáp ứng toàn bộ tiêu chí bắt buộc của phạm vi.
- **FAIL:** đã thực hiện nhưng ít nhất một tiêu chí bắt buộc không đạt.
- **BLOCKED:** chưa thể thực hiện đầy đủ vì thiếu phụ thuộc, quyền hoặc điều kiện cần thiết.
- **NOT TESTED:** nằm ngoài phần đã thực hiện; không được tính là đạt.

Ví dụ, thiếu quyền dùng recovery key dẫn tới không thể hoàn tất giải mã. Báo cáo phải phản ánh việc chưa chứng minh được khả năng khôi phục, thay vì ghi PASS vì “file backup vẫn còn”.

Nếu tổ chức dùng trạng thái “đạt có điều kiện”, phải nêu rõ tiêu chí nào chưa đạt và không dùng trạng thái đó để khẳng định mục tiêu bắt buộc đã được đáp ứng.

### 12.1. Chỉ số nên thu thập

- Thời gian huy động và tiếp cận vật liệu phục hồi.
- Thời gian chuẩn bị hạ tầng và phụ thuộc.
- Thời gian lấy bản sao, restore và kiểm tra dữ liệu.
- Thời gian hòa giải credential, quyền và cấu hình.
- Thời gian xác minh chức năng cùng audit.
- Tổng thời gian tới nghiệm thu.
- Điểm dữ liệu nhất quán thực sự đạt được.
- Số bước cần thao tác ngoài runbook và số tiêu chí chưa kiểm thử.

Không cộng máy móc thời gian của các công việc chạy song song để suy ra RTO. Tổng thời gian đầu cuối dựa trên hai mốc đã định; thời gian từng công việc dùng để tìm phần gây chậm.

### 12.2. Gói bằng chứng

Một gói bằng chứng nên cho phép người khác hiểu được bài thử mà không cần biết bí mật của hệ thống:

```text
Mã bài thử và phiên bản runbook
Giả định sự cố, phạm vi và phần được chuẩn bị sẵn
Mã backup, điểm phục hồi, cách kiểm tra tính toàn vẹn
Danh sách phụ thuộc thật / giả lập / chưa kiểm thử
Mốc thời gian đầu cuối và từng giai đoạn
Kết quả tiêu chí chức năng, quyền, credential và audit
Tham chiếu log, request ID, session ID đã được kiểm tra
Sai lệch, lỗi, chủ sở hữu và kế hoạch kiểm thử lại
Xác nhận xử lý dữ liệu và tài nguyên thử
```

Giữ bằng chứng trong nơi được phân quyền và có thời hạn lưu phù hợp. Che dữ liệu trước khi chụp hoặc xuất, thay vì phát tán bản chứa bí mật rồi mới xóa.

## 13. Ví dụ diễn tập: phục hồi được dịch vụ nhưng chưa đạt nghiệm thu

Một đội đặt mục tiêu cho kịch bản mất management plane:

- RPO tối đa 15 phút.
- RTO tối đa 60 phút tính từ tuyên bố sự cố.
- Bắt buộc có truy cập hợp lệ, từ chối trái quyền, xử lý credential drift và audit.
- Toàn bộ máy đích là máy thử; kết nối tới sản xuất bị chặn.

Kết quả quan sát:

| Hạng mục | Kết quả |
| --- | --- |
| Điểm dữ liệu phục hồi | Cách thời điểm sự cố giả lập 15 phút |
| Portal và dịch vụ quản lý | Hoạt động sau 31 phút |
| Credential drift | Phát hiện và hòa giải xong ở phút 48 |
| Luồng truy cập hợp lệ | Thành công ở phút 51 |
| Truy cập trái quyền | Bị từ chối đúng policy |
| Audit tới collector thử | Không nhận được sự kiện phiên mới |
| Hết thời gian mục tiêu | Audit vẫn chưa đạt |

Kết luận: RPO đạt trong kịch bản đã đo; kiểm thử đầu cuối FAIL và chưa chứng minh đạt RTO phục vụ theo tiêu chí đã chốt. Không lấy mốc portal khởi động ở phút 31 làm thời gian khôi phục hoàn chỉnh.

Đội xác định cấu hình trust tới collector thử chưa đúng sau restore, cập nhật runbook và kiểm thử lại. Lần chạy lại được ghi thành một lần thực hiện riêng, giữ cả kết quả thất bại ban đầu. Không sửa lịch sử để chỉ còn lần đạt.

Ví dụ này cho thấy restore test tạo giá trị bằng cách tìm ra phần dịch vụ chưa hồi phục đầy đủ, kể cả khi dữ liệu và portal đều có vẻ bình thường.

## 14. Những lỗi thiết kế thường gặp

### Chỉ kiểm tra một bản backup “đẹp”

Nếu người vận hành luôn chọn trước bản dễ phục hồi nhất, bài thử không phản ánh khả năng lấy đúng bản sao trong sự cố. Có thể thiết kế lịch chọn mẫu theo độ tuổi, loại backup, vị trí lưu và chuỗi phụ thuộc, phù hợp với mục tiêu dịch vụ.

Không bắt buộc thử mọi bản sao, nhưng cần biết phạm vi chọn mẫu và những loại bản sao chưa được kiểm chứng.

### Dựa hoàn toàn vào người nhớ thao tác

Một chuyên gia nhớ recovery key ở đâu và tự sửa vài bước còn thiếu có thể làm bài thử thành công nhưng runbook vẫn không sử dụng được bởi người được phân công khác.

Ghi mọi thao tác bổ sung và thử lại với người vận hành phù hợp. Mục tiêu là quy trình có thể lặp lại với nhân sự và quyền truy cập dự kiến.

### Đo thời gian sau khi mọi thứ đã sẵn sàng

Nếu bắt đầu đồng hồ sau khi đã dựng hạ tầng, cấp quyền và tải backup, kết quả chỉ đại diện cho một phần thao tác. Báo cáo riêng phần đó và không so sánh trực tiếp với RTO đầu cuối.

### Kiểm tra dữ liệu nhưng không kiểm tra hành vi

Số lượng policy hoặc tài khoản khớp không chứng minh người thiếu quyền bị chặn. Cần thử hành vi trên luồng truy cập thực tế.

### Thử credential drift bằng hệ thống sản xuất

Một phép thử không có cách ly có thể tạo ra chính sự cố mất truy cập mà đội đang muốn phòng tránh. Dùng máy đích thử và tài khoản thử để tái tạo lệch trạng thái; các kết nối thật chỉ được dùng nếu nằm trong phạm vi được phê duyệt riêng của bài thử.

### Kết thúc mà không đóng môi trường clone

Một bản clone còn chạy có thể giữ credential, bản ghi phiên và job đã được khôi phục. Bài thử cần có bước xử lý tài nguyên, dữ liệu và tài khoản tạm; xác nhận bước này bằng bằng chứng phù hợp.

## 15. Bài thực hành thiết kế

Thiết kế một restore test cho hệ thống PAM giả định gồm vault, cơ sở dữ liệu cấu hình, session broker và collector audit.

Các điều kiện:

- Backup được tạo trước một lần luân chuyển credential trên máy đích thử.
- Sau backup có một grant bị thu hồi.
- Môi trường phục hồi không được kết nối tới sản xuất.
- Mục tiêu RPO là 30 phút, RTO là 90 phút tính từ tuyên bố sự cố.
- Không được đưa bí mật vào log hoặc báo cáo.

Hãy lập kế hoạch có các phần sau:

1. Sơ đồ phụ thuộc và đường bootstrap để lấy backup cùng quyền dùng khóa.
2. Điểm phục hồi dự kiến và cách xác định dữ liệu nhất quán cuối cùng.
3. Cách chứng minh cách ly trước khi bật scheduler hoặc connector.
4. Phép thử làm lộ credential drift và quy trình hòa giải được giả định.
5. Phép thử ngăn grant đã thu hồi trở thành quyền sử dụng ngoài ý muốn.
6. Một luồng truy cập hợp lệ, một luồng trái quyền và bằng chứng audit tương ứng.
7. Mốc bắt đầu, kết thúc RTO cùng những phần chuẩn bị sẵn.
8. Điều kiện dừng, tiêu chí PASS/FAIL và cách đóng môi trường thử.

Một đáp án đạt không cần nêu lệnh của một sản phẩm cụ thể, nhưng phải giải thích được quan sát nào chứng minh từng tiêu chí. “Kiểm tra hệ thống hoạt động tốt” không phải một tiêu chí có thể nghiệm thu.

## 16. Các câu hỏi tự kiểm tra

**Vì sao kiểm tra checksum chưa đủ?**

Checksum chỉ hỗ trợ kiểm tra tính toàn vẹn theo giá trị đối chiếu đã chọn. Nó không chứng minh có thể giải mã, dựng đủ dịch vụ, áp dụng đúng quyền hoặc chọn được một trạng thái sạch sau xâm nhập.

**Vì sao portal đăng nhập được chưa phải mốc kết thúc RTO?**

Vì mức phục vụ đã cam kết có thể bao gồm truy cập máy đích, kiểm soát quyền, credential đã hòa giải và audit. Mốc kết thúc phải khớp tiêu chí được thống nhất trước bài thử.

**Nếu backup cũ hơn lần đổi mật khẩu trên máy đích thì điều gì xảy ra?**

Vault phục hồi có thể giữ credential không còn phù hợp với máy đích. Bài thử cần phát hiện lệch trạng thái và chứng minh quy trình hòa giải trong phạm vi được phép.

**Vì sao phải thử cả từ chối truy cập?**

Một hệ thống cấp được quyền cho người hợp lệ vẫn có thể cấp nhầm quyền cho người không hợp lệ. Kiểm soát âm giúp chứng minh ranh giới quyền còn hiệu lực sau restore.

**Nếu chỉ dùng hệ thống danh tính và kho khóa giả lập thì có thể kết luận gì?**

Có thể kết luận về phần chức năng đã thực hiện với các phụ thuộc giả lập. Chưa thể khẳng định đường phục hồi của các phụ thuộc vận hành thật đã được kiểm chứng.

Restore test hoàn chỉnh biến phương án backup thành bằng chứng phục hồi: dữ liệu có thể sử dụng, quyền được kiểm soát, credential được đối chiếu, hoạt động được ghi nhận và mức phục vụ đạt tiêu chí trong thời gian đã cam kết.
