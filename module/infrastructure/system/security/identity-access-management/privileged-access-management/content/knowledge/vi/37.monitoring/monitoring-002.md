# Session activity monitoring — Giám sát hoạt động phiên đặc quyền

## 1. Mục tiêu và phạm vi

Trong Privileged Access Management (PAM), **session activity monitoring** là việc quan sát và phân tích hoạt động của một phiên truy cập đặc quyền từ lúc yêu cầu truy cập được thực thi cho đến khi phiên kết thúc hoặc bị thu hồi. Mục tiêu là trả lời được bốn câu hỏi:

1. Ai hoặc workload nào thực sự sử dụng quyền?
2. Họ truy cập tài nguyên nào, thông qua đường nào và với quyền hiệu lực nào?
3. Hoạt động diễn ra có phù hợp mục đích, phạm vi và thời hạn đã được chấp thuận không?
4. Khi xuất hiện dấu hiệu bất thường, đội vận hành có đủ dữ liệu để đánh giá và xử lý kịp thời không?

Bài học tập trung vào **hoạt động bên trong phiên**: đăng nhập vào đích, thay đổi ngữ cảnh quyền, thao tác quản trị, truy cập tài nguyên, truyền tệp và kết thúc phiên. Các nguyên tắc áp dụng cho phiên SSH, RDP, quản trị cơ sở dữ liệu, phiên quản trị cloud và một số luồng API. Mức quan sát thực tế phụ thuộc giao thức, cơ chế truy cập và nguồn telemetry được triển khai.

Sau bài học, người học có thể thiết kế tập sự kiện tối thiểu, liên kết phiên với danh tính và phê duyệt, xây dựng quy tắc phát hiện có ngữ cảnh, phân loại cảnh báo và kiểm tra độ đầy đủ của giám sát.

Giám sát là một lớp phát hiện và tạo bằng chứng. Nó cần phối hợp với kiểm kê tài khoản, least privilege, JIT/JEA, vault, luân chuyển credential và kiểm soát đường truy cập. Một hoạt động nguy hiểm không trở nên an toàn chỉ vì đã được ghi nhận.

## 2. Phân biệt giám sát phiên với những chức năng gần nhau

| Chức năng | Câu hỏi chính | Đầu ra thường gặp | Giới hạn cần hiểu |
|---|---|---|---|
| Kiểm soát truy cập | Có cho phép bắt đầu hoặc tiếp tục truy cập không? | Quyết định cho phép, từ chối, quyền và thời hạn | Quyết định đúng lúc vào phiên chưa chứng minh mọi hoạt động sau đó hợp lệ |
| Giám sát hoạt động phiên | Trong phiên đang xảy ra điều gì, có cần chú ý không? | Sự kiện, trạng thái phiên, tín hiệu bất thường, cảnh báo | Chỉ thấy những gì nguồn telemetry cung cấp |
| Ghi hình hoặc ghi luồng phiên | Có thể xem lại phần tương tác đã thu không? | Video, luồng terminal, bản ghi giao thức | Không nhất thiết biểu diễn được đầy đủ tác động tại hệ thống đích |
| Audit logging | Sự kiện nào đã được hệ thống ghi lại để truy vết? | Nhật ký xác thực, thay đổi cấu hình, thao tác dữ liệu | Có thể đến trễ hoặc thiếu liên kết với yêu cầu PAM |
| Phân tích lệnh | Lệnh hoặc chuỗi hành động có ý nghĩa rủi ro gì? | Phân loại hành động, mẫu hành vi | Chuỗi lệnh hiển thị chưa luôn phản ánh tiến trình và kết quả thực tế |

Một phiên RDP có thể được ghi hình nhưng không có sự kiện cấu trúc về tiến trình đã chạy. Một phiên SSH có transcript terminal nhưng tác vụ được thực hiện qua kênh không tương tác lại không xuất hiện trong phần transcript đó. Một công cụ quản trị có thể ghi câu lệnh đã gửi nhưng không ghi đầy đủ kết quả tác động tại đích.

Vì vậy, cần mô tả chính xác **khả năng quan sát**, thay vì dùng chung nhãn “đã có recording” cho mọi loại phiên.

## 3. Mô hình phiên cần theo dõi

### 3.1. Danh tính yêu cầu khác tài khoản được dùng tại đích

Giả sử kỹ sư Linh yêu cầu quyền sửa cấu hình trên máy chủ cơ sở dữ liệu:

- Danh tính yêu cầu: `linh@example.test`.
- Mã yêu cầu: `req-8042`.
- Mã thay đổi: `chg-731`.
- Tài nguyên được duyệt: `db-prod-07`.
- Tài khoản đặc quyền tại đích: `db-maint`.
- Khoảng thời gian được duyệt: 30 phút.
- Mục đích: điều chỉnh cấu hình kết nối.

Nếu nhật ký tại máy chủ chỉ ghi “`db-maint` đã đăng nhập”, đội điều tra chưa thể quy trách nhiệm cho đúng người. PAM cần liên kết danh tính yêu cầu, phiên truy cập và tài khoản đích. Nếu Linh dùng `sudo`, chuyển tài khoản hoặc mở kết nối tiếp theo, chuỗi liên kết cũng cần được bảo toàn trong phạm vi telemetry cho phép.

Tài khoản kỹ thuật dùng chung đòi hỏi liên kết đặc biệt chặt chẽ. Việc một người đã được cấp credential không tự chứng minh rằng mọi hoạt động về sau dưới tài khoản đó đều do người ấy thực hiện.

### 3.2. Vòng đời của một phiên

Một mô hình thực tế có thể theo dõi các trạng thái:

```text
Yêu cầu đã duyệt
      |
      v
Khởi tạo phiên --> Kết nối thất bại
      |
      v
Đang hoạt động --> Mất quan sát / mất kết nối
      |                    |
      |                    v
      |              Xác minh trạng thái tại đích
      v
Kết thúc hoặc bị thu hồi
      |
      v
Đối soát log và đóng hồ sơ phiên
```

“PAM đã ngắt kết nối” và “mọi quyền tại đích đã hết hiệu lực” là hai trạng thái cần được kiểm tra riêng. Token, phiên con, tiến trình nền hoặc credential còn hiệu lực có thể tồn tại tùy hệ thống.

Không nên đánh dấu phiên đã được thu hồi hoàn toàn chỉ từ việc giao diện PAM không còn hiển thị kết nối.

### 3.3. Phiên tương tác và hoạt động máy

Với phiên do con người thực hiện, đơn vị giám sát thường là kết nối quản trị có thời điểm bắt đầu và kết thúc rõ ràng.

Với service account hoặc workload, một “phiên” có thể cần biểu diễn bằng:

- Lần cấp credential hoặc lease.
- Lần xác thực vào tài nguyên.
- Khoảng hoạt động của một workload instance.
- Chuỗi yêu cầu API dùng cùng định danh hoặc ngữ cảnh thực thi.

Không ép mọi hoạt động API vào mô hình video phiên tương tác. Cần xác định đơn vị quan sát phù hợp để vẫn truy được từ workload tới quyền, tài nguyên và thao tác.

## 4. Kiến trúc thu thập hoạt động phiên

Một luồng giám sát phổ biến gồm các thành phần sau:

```text
Danh tính + yêu cầu + chính sách
              |
              v
     PAM gateway / broker --------> Sự kiện phiên PAM
              |
              v
       Hệ thống được quản trị ----> Audit / agent / telemetry tại đích
              |                                  |
              +---------------+------------------+
                              v
                  Thu thập và chuẩn hóa
                              |
                              v
               Tương quan danh tính, phiên, quyền
                              |
                              v
               Phát hiện --> Cảnh báo --> Xử lý
                              |
                              v
                   Lưu giữ bằng chứng có kiểm soát
```

### 4.1. Quan sát tại gateway hoặc broker

Gateway thường có ngữ cảnh mạnh về yêu cầu truy cập: người yêu cầu, phê duyệt, tài khoản được cấp, đích kết nối và thời hạn.

Điểm cần kiểm tra là gateway có thực sự quan sát được hoạt động bên trong giao thức hay chỉ chuyển tiếp kết nối. Nếu luồng được mã hóa xuyên suốt mà gateway không có cơ chế quan sát phù hợp, không thể mặc định gateway đọc được nội dung lệnh.

Một đường truy cập đi vòng gateway cũng có thể tạo phiên hoàn toàn nằm ngoài nguồn log này.

### 4.2. Quan sát tại hệ thống đích

Audit của hệ điều hành, agent bảo mật, log cơ sở dữ liệu hoặc audit của control plane có thể bổ sung:

- Tiến trình hoặc hành động quản trị đã thực thi.
- Thay đổi cấu hình và quyền.
- Tài nguyên bị truy cập.
- Kết quả thành công hoặc thất bại.
- Các hoạt động không đi qua terminal tương tác.

Nguồn tại đích có thể dùng tài khoản hoặc mã phiên khác với gateway. Cần có cơ chế liên kết, đồng thời phải thừa nhận trường hợp chưa đủ dữ liệu để kết nối chắc chắn.

### 4.3. Quan sát ở lớp ứng dụng và cloud

Khi người quản trị dùng công cụ đồ họa, API hoặc cloud console, audit tại ứng dụng hoặc control plane thường cung cấp ngữ nghĩa tốt hơn dữ liệu màn hình.

Ví dụ, sự kiện “thêm thành viên vào vai trò quản trị” hữu ích hơn ảnh chụp một trang giao diện. Tuy nhiên, audit của từng dịch vụ có phạm vi, độ trễ và cấu hình riêng; cần kiểm thử trên chính luồng được quản lý.

### 4.4. Kết hợp nhiều nguồn mà không khẳng định quá mức

Một chuỗi suy luận có thể gồm:

1. PAM xác nhận Linh mở phiên tới `db-prod-07`.
2. Hệ điều hành ghi nhận tiến trình chạy dưới tài khoản `db-maint`.
3. Audit cơ sở dữ liệu ghi nhận thay đổi cấu hình.
4. Các sự kiện chia sẻ mã tương quan hoặc có liên kết được chứng minh qua ngữ cảnh kết nối.

Nếu chỉ có cùng tên tài khoản và thời gian gần nhau, đó là liên kết yếu hơn so với mã phiên được truyền và kiểm chứng. Trường hợp nhiều người đồng thời dùng chung tài khoản phải được đánh dấu mơ hồ, không gán chắc cho một người.

## 5. Tập sự kiện và trường dữ liệu tối thiểu

### 5.1. Các sự kiện cần cân nhắc

| Nhóm sự kiện | Ví dụ | Mục đích giám sát |
|---|---|---|
| Khởi tạo phiên | Yêu cầu kết nối, xác thực đích thành công hoặc thất bại | Xác nhận phiên thực sự được mở và tới đúng đích |
| Ngữ cảnh quyền | Dùng tài khoản quản trị, nâng quyền, đổi tài khoản | Theo dõi quyền hiệu lực trong quá trình làm việc |
| Hoạt động quản trị | Chạy tác vụ, sửa cấu hình, thay đổi thành viên vai trò | So sánh hành động với mục đích đã duyệt |
| Di chuyển tài nguyên | Mở kết nối tới hệ thống khác, dùng tài nguyên ngoài phạm vi | Phát hiện mở rộng hoạt động sang đích chưa được duyệt |
| Di chuyển dữ liệu | Truyền tệp, xuất dữ liệu, dùng clipboard nếu có khả năng quan sát | Đánh giá nguy cơ đưa dữ liệu ra khỏi vùng cho phép |
| Kiểm soát phiên | Cảnh báo, yêu cầu xác minh, giám sát trực tiếp, thu hồi | Lưu dấu quyết định vận hành |
| Kết thúc | Đăng xuất, timeout, mất kết nối, kết thúc cưỡng chế | Đối soát vòng đời và quyền còn tồn tại |
| Sức khỏe thu thập | Mất heartbeat, hàng đợi tăng, lỗi gửi, log đến trễ | Phân biệt không có hoạt động với mất dữ liệu |

Một số cơ chế như clipboard hoặc truyền tệp chỉ khả dụng ở những giao thức và cấu hình cụ thể. Trong hồ sơ thiết kế phải ghi “có quan sát”, “quan sát một phần” hoặc “không quan sát” cho từng khả năng.

### 5.2. Các trường cần có để tương quan

Một sự kiện chuẩn hóa nên cân nhắc các nhóm trường:

- **Định danh:** mã sự kiện, mã phiên PAM, mã phiên hoặc kết nối tại đích.
- **Chủ thể:** người yêu cầu hoặc workload, tài khoản đích, quyền hiệu lực.
- **Ủy quyền:** mã yêu cầu, mã phê duyệt, chính sách áp dụng, thời hạn.
- **Tài nguyên:** đích được duyệt, đích thực tế, môi trường, mức độ quan trọng.
- **Hoạt động:** loại hành động, đối tượng tác động, kết quả, mức quan sát.
- **Thời gian:** thời điểm xảy ra tại nguồn, thời điểm nhận, múi giờ hoặc UTC, sai lệch đồng hồ nếu biết.
- **Nguồn và chất lượng:** hệ thống phát sự kiện, phiên bản schema, dấu hiệu mất dữ liệu.
- **Bằng chứng:** tham chiếu tới log hoặc bản ghi được bảo vệ, nếu có.

Địa chỉ IP và tên tài khoản là ngữ cảnh hữu ích nhưng không nên được xem là định danh duy nhất. NAT, proxy, tái sử dụng địa chỉ hoặc tài khoản dùng chung có thể làm chúng không đủ để phân biệt chủ thể.

### 5.3. Ví dụ sự kiện đã giảm dữ liệu nhạy cảm

Ví dụ dưới đây là schema minh họa, không phải định dạng bắt buộc của một sản phẩm:

```json
{
  "schema_version": "1",
  "event_id": "evt-90218",
  "event_type": "privileged_action",
  "event_time": "2026-11-27T02:12:30Z",
  "ingest_time": "2026-11-27T02:12:33Z",
  "pam_session_id": "ps-8042-01",
  "target_session_id": "ts-611",
  "request_id": "req-8042",
  "change_id": "chg-731",
  "requester_id": "linh@example.test",
  "target_account": "db-maint",
  "effective_role": "database-maintenance",
  "approved_target": "db-prod-07",
  "observed_target": "db-prod-07",
  "action_category": "configuration_update",
  "object_type": "database_parameter",
  "result": "success",
  "source": "target-audit",
  "observation_mode": "structured_event",
  "correlation_confidence": "high",
  "sensitive_fields": "omitted",
  "evidence_ref": "evidence://pam/ps-8042-01/evt-90218"
}
```

Sự kiện cho biết một thay đổi cấu hình đã được quan sát. Nó chưa đủ để kết luận thay đổi đó đúng với `chg-731`; cần đối chiếu tham số và giá trị được duyệt ở nguồn có quyền truy cập phù hợp.

Không đưa mật khẩu, private key, token hoặc toàn bộ nội dung kết quả nhạy cảm vào sự kiện chỉ để “đủ bằng chứng”. Tham chiếu bằng chứng cũng phải chịu kiểm soát truy cập, không được trở thành đường dẫn công khai tới bản ghi gốc.

## 6. Liên kết hoạt động với phạm vi đã được duyệt

### 6.1. Đừng chỉ kiểm tra tên người dùng

Ngữ cảnh phê duyệt nên đủ để trả lời:

- Ai được sử dụng quyền, và qua phương thức xác thực nào?
- Được truy cập tài nguyên nào hoặc tập tài nguyên nào?
- Được sử dụng vai trò hoặc tài khoản nào?
- Được thực hiện nhóm tác vụ gì?
- Quyền có hiệu lực trong thời gian nào?
- Có điều kiện về thiết bị, vị trí hoặc giám sát bổ sung không?

Một phiên đăng nhập hợp lệ vẫn có thể thực hiện hành động ngoài mục đích. Nếu phê duyệt chỉ ghi “sửa hệ thống” mà không có phạm vi hữu ích, giám sát khó phân biệt bảo trì bình thường với hành động vượt quyền.

### 6.2. Theo dõi thay đổi quyền trong phiên

Một người có thể vào phiên bằng quyền thấp rồi nâng quyền trong quá trình thao tác. Cần quan sát sự kiện chuyển ngữ cảnh nếu nguồn hỗ trợ:

```text
Danh tính Linh
  -> yêu cầu req-8042
  -> phiên PAM ps-8042-01
  -> tài khoản đích db-maint
  -> nâng quyền hoặc đổi vai trò
  -> hành động quản trị tại db-prod-07
```

Nếu chỉ lưu tài khoản ban đầu, cảnh báo có thể đánh giá sai quyền thực tế được dùng.

JEA hoặc cơ chế giới hạn tác vụ giúp thu hẹp hành động được phép. Giám sát vẫn cần kiểm tra hoạt động thực tế, kết quả thực thi và những đường có thể bỏ qua giới hạn đó.

### 6.3. Theo dõi kết nối tiếp theo

Trong một phiên tới máy chủ A, người quản trị có thể mở kết nối tới B. Nếu PAM chỉ ghi đích ban đầu A, hoạt động tại B có thể bị bỏ sót.

Cách xử lý gồm kiểm soát đường mạng phù hợp, thu thập telemetry ở đích và liên kết phiên con khi có dữ liệu. Không nên coi sự xuất hiện của kết nối thứ hai là vi phạm trong mọi trường hợp: một số tác vụ bảo trì cần nhiều đích, nhưng phạm vi đó phải được định nghĩa và kiểm chứng.

### 6.4. Thời hạn JIT và thời gian phiên

Cần xác định rõ chính sách khi quyền JIT hết hạn:

- Ngăn tạo phiên mới.
- Thu hồi quyền hoặc lease.
- Yêu cầu kết thúc phiên hiện có.
- Cho phép khoảng xử lý có kiểm soát đối với tác vụ đang chạy.

Các hành vi này phụ thuộc thiết kế. Giám sát nên kiểm tra riêng thời hạn cấp quyền, tình trạng kết nối và hoạt động còn tiếp diễn tại đích.

## 7. Thiết kế phát hiện bất thường

### 7.1. Kết hợp hành động, quyền và ngữ cảnh

Một tín hiệu đơn lẻ thường chưa đủ để phân loại mức nghiêm trọng. Có thể xem xét đồng thời:

- Mức nhạy cảm của tài nguyên.
- Quyền được sử dụng và phạm vi phê duyệt.
- Loại hành động và kết quả thực tế.
- Thời điểm, thiết bị và đường truy cập.
- Chuỗi hoạt động trước và sau tín hiệu.
- Độ tin cậy của liên kết danh tính.
- Độ đầy đủ của telemetry.

Ví dụ, xuất một tệp cấu hình trong cửa sổ bảo trì có thể bình thường. Xuất dữ liệu lớn từ hệ thống sản xuất, qua đích chưa được duyệt và sau khi quyền đã hết hạn cần được đánh giá khác.

### 7.2. Một số nhóm quy tắc hữu ích

| Tín hiệu | Ngữ cảnh cần bổ sung | Hướng đánh giá |
|---|---|---|
| Hành động quản trị ngoài phạm vi yêu cầu | Nội dung yêu cầu, loại tác vụ được duyệt, tài nguyên | Xác minh có mở rộng quyền trái phép hay yêu cầu thiếu chi tiết |
| Hoạt động tiếp diễn sau thời hạn | Chính sách JIT, trạng thái thu hồi, thời gian tại nguồn | Kiểm tra quyền và phiên thực tế tại đích |
| Thay đổi cơ chế ghi log hoặc giám sát | Thay đổi đã được duyệt, nguồn telemetry độc lập | Xem xét khả năng làm mất khả năng quan sát |
| Thêm tài khoản hoặc cấp vai trò mạnh | Mục đích bảo trì, người phê duyệt, đối tượng được cấp | Đánh giá nguy cơ tạo quyền tồn tại lâu dài |
| Truy cập đích khác đích được duyệt | Danh sách đích hợp lệ, kết nối con, mục đích | Phân biệt tác vụ nhiều đích với mở rộng trái phép |
| Nhiều thất bại rồi thành công | Lỗi cấu hình, credential rotation, địa chỉ nguồn | Xác minh tấn công, dùng sai credential hoặc sự cố vận hành |
| Mất telemetry khi phiên còn hoạt động | Health của collector, log tại đích, độ trễ pipeline | Điều tra khoảng mù và độ tin cậy của các kết luận |

Thay đổi logging là tín hiệu đáng chú ý, nhưng cũng có thể nằm trong một yêu cầu bảo trì chính đáng. Cảnh báo phải giữ được bằng chứng và ngữ cảnh để người xử lý quyết định.

### 7.3. Ví dụ logic phát hiện

Mã giả dưới đây minh họa một quy tắc phát hiện; nó không tự thực hiện thu hồi phiên:

```text
khi nhận privileged_action:
    chuẩn hóa thời gian và nguồn sự kiện
    loại bỏ bản sao theo event_id trong phạm vi nguồn

    nếu chưa liên kết chắc với phiên:
        tạo mục cần đối soát danh tính
        không gán chắc trách nhiệm cho một người

    tìm phạm vi phê duyệt của phiên

    nếu observed_target nằm ngoài tập đích đã duyệt:
        tạo cảnh báo "target_scope_mismatch"

    nếu hành động xảy ra sau thời hạn quyền
       và không có gia hạn hợp lệ:
        tạo cảnh báo "activity_after_expiry"

    nếu loại hành động ảnh hưởng cơ chế audit:
        đính kèm mã thay đổi và tình trạng collector
        tạo cảnh báo theo mức quan trọng của tài nguyên
```

So sánh thời gian phải dùng thời điểm xảy ra sự kiện với chính sách xử lý sai lệch đồng hồ. Một log nhận sau khi quyền hết hạn có thể mô tả hành động đã xảy ra trước đó. Dùng `ingest_time` thay cho `event_time` trong mọi trường hợp sẽ tạo cảnh báo sai.

### 7.4. Hạn chế của quy tắc dựa trên chuỗi lệnh

Không nên chỉ tìm từ khóa trong terminal rồi kết luận tác động:

- Lệnh có thể là nội dung đang được xem hoặc nhập trong trình soạn thảo.
- Một công cụ có thể thực hiện cùng tác vụ qua API hoặc giao diện đồ họa.
- Script, alias, shell khác và phiên không tương tác làm chuỗi hiển thị khác đi.
- Lệnh đã gửi có thể thất bại hoặc không tạo tác động như dự kiến.
- Một chuỗi tưởng là vô hại có thể gọi script làm thay đổi hệ thống.

Khi có thể, kết hợp hành động ở đích, tiến trình, đối tượng bị thay đổi và kết quả. Đánh dấu rõ tín hiệu là “đã quan sát ý định”, “đã thực thi” hay “đã xác nhận tác động”.

### 7.5. Baseline và ngoại lệ

Baseline nên được xây dựng theo vai trò, tài nguyên, môi trường và loại tác vụ. Không dùng một ngưỡng chung cho mọi tài khoản.

Ngoại lệ cần có chủ sở hữu, phạm vi và ngày hết hạn. Một ngoại lệ để giảm cảnh báo cho đợt bảo trì không nên vô tình bỏ giám sát toàn bộ phiên tương lai của tài khoản quản trị.

Theo dõi cả cảnh báo sai và trường hợp bỏ sót đã biết. Giảm số lượng cảnh báo không tự chứng minh chất lượng phát hiện tốt hơn.

## 8. Giám sát trực tiếp và xử lý cảnh báo

### 8.1. Quy trình xử lý tối thiểu

Một cảnh báo hữu ích nên dẫn tới hành động rõ ràng:

1. Xác nhận cảnh báo thuộc đúng phiên, chủ thể và tài nguyên.
2. Kiểm tra thời gian, nguồn sự kiện và chất lượng tương quan.
3. Đối chiếu yêu cầu, phê duyệt, mã thay đổi và cửa sổ bảo trì.
4. Xác minh hành động đã thành công, thất bại hay chỉ mới được quan sát một phần.
5. Đánh giá tác động và khả năng hoạt động còn tiếp diễn.
6. Chọn phản ứng theo thẩm quyền và runbook.
7. Ghi quyết định, người xử lý, thời điểm và tham chiếu bằng chứng.

Việc xem trực tiếp màn hình hoặc terminal là một quyền đặc biệt. Người giám sát phải được phân quyền và mọi lần truy cập bản ghi hoặc theo dõi trực tiếp cần có audit.

### 8.2. Các mức phản ứng

| Phản ứng | Khi nào có thể phù hợp | Điều kiện cần kiểm tra |
|---|---|---|
| Bổ sung ngữ cảnh và theo dõi | Tín hiệu yếu, chưa xác nhận vi phạm | Không bỏ qua tín hiệu mạnh khác hoặc mất telemetry |
| Liên hệ xác minh qua kênh được duyệt | Cần phân biệt bảo trì với sử dụng trái phép | Xác thực đúng người, không dựa riêng vào thông tin trong phiên nghi vấn |
| Tăng cường giám sát hoặc yêu cầu xác thực bổ sung | Hoạt động nhạy cảm, cần xác minh danh tính hoặc mục đích | Cơ chế có hỗ trợ và quyền thao tác đã được quy định |
| Thu hồi hoặc kết thúc phiên | Vi phạm được xác nhận, rủi ro đang tiếp diễn, hoặc theo quy tắc khẩn cấp | Thẩm quyền, tác động vận hành, khả năng thu hồi ở đích |
| Kích hoạt ứng phó sự cố | Nghi ngờ lộ credential, lạm dụng quyền hoặc thay đổi gây hại | Phối hợp PAM, SOC, chủ hệ thống và người phụ trách sự cố |

Không tự động kết thúc mọi phiên có điểm rủi ro cao. Tác vụ đang chạy có thể liên quan đến dịch vụ quan trọng. Chính sách phản ứng phải nêu những trường hợp được tự động hóa, các điều kiện dừng khẩn cấp và cách xử lý ảnh hưởng vận hành.

Ngược lại, yêu cầu xác minh không được trở thành lý do trì hoãn khi runbook đã cho phép phản ứng khẩn cấp trước hành vi nguy hiểm rõ ràng.

### 8.3. Sau khi kết thúc phiên

Thu hồi phiên chưa kết thúc toàn bộ công việc. Tùy tình huống, cần xác minh:

- Kết nối tại đích đã đóng.
- Quyền tạm, token hoặc lease đã bị thu hồi theo thiết kế.
- Credential cần luân chuyển đã được xử lý.
- Phiên con và tiến trình nền đã được đánh giá.
- Tài khoản, khóa hoặc vai trò mới tạo đã được kiểm tra.
- Thay đổi cấu hình và dữ liệu đã được chủ hệ thống đối soát.
- Bằng chứng và timeline đã được bảo toàn.

Luân chuyển credential ngăn một số lần sử dụng tiếp theo nhưng không nhất thiết chấm dứt token, kết nối hoặc tiến trình đã tồn tại. Cần kiểm tra từng loại trạng thái thay vì dùng một thao tác thay cho tất cả.

## 9. Bảo vệ dữ liệu giám sát và bằng chứng

### 9.1. Thu thập theo mục đích

Dữ liệu phiên có thể chứa secret, dữ liệu khách hàng, nội dung màn hình hoặc thông tin nội bộ. Thiết kế thu thập nên xác định:

- Trường nào thực sự cần để phát hiện và điều tra.
- Nội dung nào cần loại bỏ hoặc che trước khi lưu.
- Nguồn nào có khả năng thu nhầm secret.
- Ai được xem metadata, nội dung chi tiết và bản ghi gốc.
- Thời hạn lưu theo yêu cầu đã xác định của tổ chức.

Che một giá trị trên giao diện xem lại không đồng nghĩa dữ liệu gốc trong kho lưu đã được loại bỏ. Cần kiểm tra điểm che dữ liệu và phạm vi áp dụng: sự kiện, transcript, video, chỉ mục tìm kiếm, export và bản sao lưu.

Không dùng hash mật khẩu hoặc token như một cách “ẩn an toàn” mặc định để lưu chúng vào log. Cách an toàn hơn thường là không thu thập secret và dùng định danh tham chiếu không bí mật.

### 9.2. Tách quyền và kiểm soát truy cập

Các quyền nên được cân nhắc riêng:

- Vận hành phiên.
- Xem trạng thái và metadata.
- Theo dõi trực tiếp.
- Xem lại recording.
- Xuất bằng chứng.
- Thay đổi chính sách giám sát.
- Quản trị kho lưu trữ.

Người có quyền đặc quyền tại hệ thống đích không nên mặc nhiên có quyền xóa hoặc sửa bằng chứng về chính phiên của mình.

Quyền xem bản ghi cũng nên tuân theo least privilege, có mục đích sử dụng và audit. Dữ liệu giám sát cần được mã hóa khi truyền, khi lưu và quản lý khóa phù hợp với mô hình vận hành.

### 9.3. Tính toàn vẹn và khả năng truy vết

Đối với hồ sơ cần bảo toàn, có thể lưu mã sự kiện, nguồn, thời gian nhận, mã tương quan và thông tin kiểm tra toàn vẹn. Các cơ chế lưu trữ hạn chế sửa đổi hoặc chữ ký cần được thiết kế cùng với phân quyền và quản lý khóa.

Hash giúp phát hiện thay đổi khi có giá trị tham chiếu đáng tin cậy. Nó không tự chứng minh dữ liệu đã đầy đủ, nguồn phát trung thực hoặc không có sự kiện bị bỏ trước lúc thu thập.

Khi xuất bằng chứng, ghi rõ ai xuất, thời điểm, phạm vi, mã hồ sơ và kiểm tra toàn vẹn. Tránh xuất bản ghi gốc vào kênh trao đổi không được kiểm soát.

## 10. Giám sát chính hệ thống giám sát

### 10.1. Không có log khác với không có hoạt động

Một dashboard trống có thể do:

- Không có phiên hoạt động.
- Collector hoặc agent dừng.
- Đường truyền lỗi.
- Audit tại đích bị tắt.
- Pipeline bị nghẽn hoặc hết dung lượng.
- Schema thay đổi làm parser bỏ sự kiện.
- Đồng hồ sai khiến truy vấn không thấy dữ liệu trong khoảng đang xem.

Vì vậy, phải có tín hiệu sức khỏe độc lập như heartbeat, độ trễ nhận, số sự kiện lỗi, hàng đợi và mức sử dụng dung lượng.

### 10.2. Phân biệt các trạng thái chất lượng

Có thể biểu diễn chất lượng giám sát của từng phiên bằng những trạng thái như:

- **Đầy đủ theo thiết kế:** các nguồn bắt buộc hoạt động và đã đối soát.
- **Giảm khả năng quan sát:** thiếu một nguồn hoặc độ trễ vượt ngưỡng.
- **Chưa xác định:** chưa đủ dữ liệu để khẳng định phiên và hoạt động đã khớp.
- **Mất quan sát:** nguồn bắt buộc bị ngắt trong khi phiên còn khả năng tiếp diễn.

“Đầy đủ theo thiết kế” vẫn chỉ có nghĩa là đủ so với tập nguồn và phạm vi đã cam kết. Nó không có nghĩa nhìn thấy mọi hành động có thể xảy ra trên hệ thống.

### 10.3. Chính sách khi mất khả năng ghi nhận

Tổ chức cần quyết định trước cách xử lý khi recording hoặc telemetry bắt buộc không khả dụng:

- Có cho phép mở phiên mới không?
- Phiên hiện có có được tiếp tục không?
- Có cơ chế truy cập khẩn cấp được kiểm soát không?
- Ai chấp nhận rủi ro và trong thời gian bao lâu?
- Cần nguồn bằng chứng thay thế nào?
- Khi phục hồi sẽ đối soát ra sao?

Không mặc định mọi hệ thống phải cùng một cách fail-open hoặc fail-closed. Quyết định phụ thuộc mức quan trọng của tài nguyên và yêu cầu vận hành, nhưng phải có chủ sở hữu, phạm vi và dấu vết quyết định.

Nếu một khoảng dữ liệu đã mất không thể khôi phục, hồ sơ phải thể hiện khoảng mù đó. Không tạo lại các sự kiện phỏng đoán để làm timeline trông liên tục.

## 11. Tình huống thực hành xuyên suốt

### 11.1. Bối cảnh

Linh được duyệt truy cập `db-prod-07` trong 30 phút để điều chỉnh một tham số theo `chg-731`. PAM cấp phiên `ps-8042-01` bằng tài khoản `db-maint`.

Tập dữ liệu giả lập có các sự kiện:

| Thời điểm UTC | Nguồn | Sự kiện |
|---|---|---|
| 02:00:00 | PAM | Bắt đầu thời hạn quyền, kết thúc dự kiến 02:30:00 |
| 02:02:10 | PAM gateway | Phiên tới `db-prod-07` được mở |
| 02:12:30 | Audit đích | Thay đổi tham số thành công |
| 02:18:00 | Audit đích | Cấp thêm một vai trò quản trị cho tài khoản khác |
| 02:19:10 | Collector health | Không nhận heartbeat từ nguồn audit đích |
| 02:20:00 | PAM gateway | Phiên vẫn có kết nối |
| 02:24:00 | Thu thập trung tâm | Nhận muộn một sự kiện có event time 02:17:40 |
| 02:30:00 | PAM | Hết thời hạn quyền, phát yêu cầu thu hồi |
| 02:31:00 | Nguồn tại đích | Ghi nhận phiên hoặc tác vụ vẫn còn hoạt động |

Các mốc thời gian và tên tài nguyên chỉ phục vụ bài tập.

### 11.2. Phân tích

**Thay đổi tham số lúc 02:12:30:** cần đối chiếu tham số thực tế với `chg-731`. Chỉ biết hành động thành công chưa đủ kết luận đúng yêu cầu.

**Cấp vai trò lúc 02:18:00:** có thể ngoài mục đích điều chỉnh tham số. Cần kiểm tra đối tượng được cấp, vai trò, người thực hiện và có phê duyệt bổ sung hay không. Nếu chưa đủ dữ liệu gán danh tính, phải thể hiện mức tin cậy tương quan.

**Mất heartbeat lúc 02:19:10:** cần mở vấn đề mất khả năng quan sát, kiểm tra nguồn độc lập và chính sách tiếp tục phiên. Không suy ra rằng Linh đã tắt audit chỉ từ heartbeat bị mất.

**Sự kiện đến muộn lúc 02:24:00:** sắp xếp timeline theo thời điểm xảy ra 02:17:40, đồng thời giữ thời điểm nhận để đánh giá độ trễ. Kiểm tra có sai lệch đồng hồ hoặc bản sao hay không.

**Hoạt động lúc 02:31:00:** cần xác minh đó là kết nối còn mở, tiến trình nền hay hành động quản trị mới. Đối chiếu chính sách hết hạn và kết quả thu hồi thực tế.

### 11.3. Hồ sơ xử lý mong đợi

Hồ sơ cuối cần nêu được:

1. Những hành động phù hợp, chưa xác định và ngoài phạm vi đã xác nhận.
2. Liên kết danh tính cùng bằng chứng và mức tin cậy.
3. Khoảng thời gian giảm hoặc mất khả năng quan sát.
4. Quyết định phản ứng, người có thẩm quyền và thời điểm.
5. Kết quả xác minh quyền, kết nối và tác vụ sau thu hồi.
6. Tham chiếu bằng chứng đã được bảo vệ.

Nếu chưa xác định được hành vi cấp vai trò có hợp lệ không, trạng thái phù hợp là “đang xác minh”, không tự kết luận “an toàn” chỉ vì phiên đã kết thúc.

## 12. Kiểm thử thiết kế giám sát

Thực hiện các bài kiểm tra trong môi trường thử nghiệm hoặc tài nguyên được phép, dùng tài khoản và dữ liệu giả lập.

| Bài kiểm tra | Kết quả cần quan sát |
|---|---|
| Mở phiên hợp lệ, thực hiện tác vụ đã duyệt, đăng xuất | Liên kết được yêu cầu, danh tính, tài khoản đích, hoạt động và kết thúc |
| Đăng nhập thất bại rồi thành công | Giữ đủ kết quả từng lần, không nhập nhằng thành một lần đăng nhập |
| Nâng quyền trong phiên | Thấy quyền hiệu lực mới khi nguồn hỗ trợ; nếu không, ghi rõ khoảng thiếu |
| Thực hiện tác vụ ngoài phạm vi giả lập | Cảnh báo có yêu cầu và phạm vi để đối chiếu |
| Mở kết nối thứ hai tới đích thử nghiệm | Quan sát hoặc chỉ ra rõ điểm mù đối với phiên con |
| Ngắt collector bằng kịch bản kiểm thử được duyệt | Có cảnh báo sức khỏe và trạng thái phiên giảm khả năng quan sát |
| Gửi log trễ hoặc lặp lại sự kiện | Timeline đúng theo chính sách thời gian, không nhân đôi hành động |
| Để quyền thử nghiệm hết hạn | Kiểm chứng kết quả ở gateway, quyền tại đích và tác vụ còn tồn tại |
| Chèn chuỗi secret giả vào luồng thử nghiệm | Xác minh cơ chế giảm dữ liệu ở các vị trí lưu và xuất được kiểm tra |
| Mở hoặc xuất recording bằng tài khoản không đủ quyền | Truy cập bị chặn và có audit theo thiết kế |

Không dùng secret thật để thử cơ chế che dữ liệu. Nếu một khả năng chưa được triển khai, kết quả kiểm thử nên nêu rõ chưa có độ bao phủ thay vì đánh dấu đạt chỉ vì một nguồn log khác vẫn tồn tại.

Các bằng chứng kiểm thử nên gắn với phiên cụ thể để người khác có thể lặp lại và hiểu giới hạn.

## 13. Chỉ số vận hành có ý nghĩa

### 13.1. Độ bao phủ phiên

Một cách đo minh họa:

```text
Độ bao phủ =
  Số phiên trong phạm vi có đủ nguồn telemetry bắt buộc
  ----------------------------------------------------
  Tổng số phiên được xác định thuộc phạm vi cần giám sát
```

Mẫu số phải đến từ nguồn kiểm kê hoặc đối soát đủ độc lập. Nếu chỉ đếm các phiên đã đi qua PAM, chỉ số có thể bỏ qua truy cập đi vòng và tạo cảm giác bao phủ cao giả tạo.

Nên tách theo giao thức, môi trường, tài nguyên và mức rủi ro, vì một tỷ lệ tổng dễ che khuất nhóm tài nguyên quan trọng bị thiếu giám sát.

### 13.2. Chất lượng và độ trễ

Các chỉ số khác gồm:

- Tỷ lệ phiên liên kết chắc với danh tính yêu cầu.
- Tỷ lệ sự kiện có đủ trường bắt buộc.
- Độ trễ từ lúc sự kiện xảy ra đến lúc nhận và tạo cảnh báo.
- Thời gian giảm hoặc mất khả năng quan sát.
- Thời gian xác minh, phân loại và phản ứng với cảnh báo.
- Tỷ lệ cảnh báo sai đã được xác minh.
- Số trường hợp bỏ sót được phát hiện qua kiểm thử hoặc điều tra.
- Tỷ lệ yêu cầu thu hồi có kết quả xác nhận tại đích.

Dùng phân vị hoặc phân bố độ trễ khi thích hợp; giá trị trung bình có thể che các khoảng trễ dài. Ngưỡng mục tiêu phải gắn với tài nguyên và khả năng phản ứng của tổ chức, không sao chép một con số chung cho mọi môi trường.

## 14. Sai lầm thường gặp

**Đồng nhất recording với giám sát đầy đủ.** Cần mô tả từng loại hành động có thể quan sát và nguồn dùng để xác minh.

**Chỉ lưu tên tài khoản quản trị.** Cần chuỗi liên kết từ người hoặc workload tới yêu cầu, phiên, quyền và tài nguyên.

**Kết luận từ một chuỗi lệnh.** Cần phân biệt nội dung hiển thị, thao tác đã gửi, thực thi và tác động.

**Dùng thời gian nhận để quyết định mọi vi phạm thời hạn.** Cần giữ cả event time, ingest time và chính sách xử lý sai lệch đồng hồ.

**Coi mất log là không có hoạt động.** Cần health telemetry và đánh dấu khoảng mù.

**Cho rằng kết thúc phiên là đã thu hồi mọi quyền.** Cần kiểm chứng token, lease, phiên con và tác vụ tại đích theo loại hệ thống.

**Thu thập toàn bộ nội dung để thuận tiện điều tra.** Cần giảm dữ liệu, tách quyền xem và kiểm tra việc che dữ liệu thực sự áp dụng ở đâu.

**Tự động phản ứng mà thiếu runbook.** Cần điều kiện kích hoạt, thẩm quyền và cách đánh giá tác động vận hành.

**Tắt rộng quy tắc để giảm nhiễu.** Cần ngoại lệ hẹp, có chủ sở hữu và thời hạn, cùng phép kiểm tra bỏ sót.

## 15. Tự kiểm tra kiến thức

1. Tại sao nhật ký “tài khoản admin đăng nhập thành công” chưa đủ để xác định người chịu trách nhiệm?
2. Recording màn hình và audit cấu trúc tại đích bổ sung cho nhau như thế nào?
3. Cần dữ liệu gì để đánh giá một hoạt động có vượt phạm vi phê duyệt không?
4. Một log nhận sau thời hạn JIT có luôn chứng minh hành động xảy ra sau thời hạn không?
5. Khi gateway đóng kết nối nhưng tiến trình nền còn chạy, cần xác minh những trạng thái nào?
6. Làm sao phân biệt không có hoạt động với mất khả năng quan sát?
7. Vì sao hash của bản ghi không tự chứng minh hồ sơ đầy đủ?
8. Khi nào một tín hiệu cần giám sát thêm, và khi nào có thể kích hoạt thu hồi theo runbook?

Một thiết kế giám sát phiên đạt yêu cầu khi có thể nối hành động với chủ thể và phạm vi quyền bằng dữ liệu đủ tin cậy, phát hiện được những sai lệch quan trọng, chỉ ra khoảng mù và hỗ trợ phản ứng có kiểm soát. Chất lượng đó phải được chứng minh bằng các phiên kiểm thử và đối soát thực tế.
