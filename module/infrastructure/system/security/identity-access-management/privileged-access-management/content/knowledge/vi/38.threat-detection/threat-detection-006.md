# Lateral movement: phát hiện di chuyển ngang trong môi trường PAM

## 1. Mục tiêu bài học

Lateral movement, hay di chuyển ngang, là việc một tác nhân mở rộng khả năng truy cập từ điểm đã kiểm soát sang hệ thống, tài khoản hoặc miền tin cậy khác. Trong môi trường quản trị đặc quyền, điều đáng lo không chỉ là một lần đăng nhập bất thường: một danh tính hợp lệ, credential được lấy đúng quy trình hoặc phiên quản trị đang hoạt động cũng có thể trở thành mắt xích của chuỗi xâm nhập.

Bài học thuộc chương Threat detection của module Privileged Access Management (PAM). Trọng tâm là nhận diện và điều tra sự dịch chuyển quyền truy cập giữa các tài sản nhạy cảm, đồng thời kết hợp kiểm kê đặc quyền, least privilege, JIT/JEA, vault và giám sát phiên để giảm phạm vi ảnh hưởng.

Sau bài học, người học có thể:

- Phân biệt di chuyển ngang với nâng quyền, đăng nhập từ xa và quản trị nhiều máy hợp lệ.
- Mô hình hóa quan hệ giữa người yêu cầu, tài khoản thực thi, nguồn truy cập, phiên PAM và tài sản đích.
- Xây dựng tín hiệu phát hiện có xét phê duyệt, hành vi nền và chất lượng bằng chứng.
- Lập trình tự điều tra, cô lập và thu hồi quyền phù hợp với loại danh tính.
- Thiết kế bài kiểm tra bằng dữ liệu mô phỏng, bao gồm cả truy cập hợp lệ và tình huống thiếu log.

Các ví dụ dưới đây dùng tên tài sản, danh tính và dữ liệu giả lập. Mã giả mô tả logic phòng thủ, không phải cú pháp triển khai sẵn của một SIEM hay sản phẩm PAM cụ thể.

## 2. Hiểu đúng di chuyển ngang

### 2.1. Những khái niệm dễ nhầm

| Khái niệm | Câu hỏi chính | Ví dụ trong môi trường quản trị |
| --- | --- | --- |
| Initial access | Tác nhân vào môi trường bằng cách nào? | Một máy quản trị bị chiếm quyền điều khiển |
| Privilege escalation | Quyền trên một phạm vi đã có tăng lên ra sao? | Một tài khoản thường có thêm quyền quản trị trên cùng máy |
| Lateral movement | Khả năng truy cập lan sang đâu? | Từ máy quản trị sang máy ứng dụng rồi tới máy cơ sở dữ liệu |
| Remote administration | Có hoạt động quản trị từ xa nào? | Kỹ sư dùng SSH tới một máy đã được cấp quyền |
| Persistence | Khả năng quay lại được duy trì thế nào? | Xuất hiện phương thức truy cập mới ngoài vòng đời được duyệt |

Một hành động có thể thuộc nhiều nhóm. Việc sử dụng một tài khoản mạnh hơn trên máy đích khác vừa mở rộng phạm vi tài sản vừa thay đổi mức đặc quyền. Ngược lại, đăng nhập SSH hoặc RDP thành công đơn lẻ chưa đủ để kết luận có di chuyển ngang độc hại.

Điểm phân biệt nằm ở ngữ cảnh: nguồn truy cập có phù hợp không, người hoặc workload nào thực sự khởi tạo, quyền được cấp tới đâu, chuỗi hoạt động có vượt mục đích đã duyệt hay không.

### 2.2. Đặc quyền làm thay đổi phạm vi ảnh hưởng

Một credential quản trị được dùng lại trên nhiều máy tạo ra quan hệ phụ thuộc nguy hiểm: sự cố ở một đầu có thể mở đường tới nhiều đầu khác. Tương tự, tài khoản dịch vụ có quyền vượt nhu cầu của ứng dụng có thể trở thành cầu nối giữa các vùng vốn được tách biệt về nghiệp vụ.

Tuy nhiên, không nên chỉ đếm số máy mà một tài khoản truy cập. Một hệ thống quản lý cấu hình có thể được phép làm việc trên hàng trăm máy; một tài khoản chỉ xuất hiện trên hai máy lại có thể vượt từ môi trường kiểm thử sang hạ tầng sản xuất trọng yếu.

Vì vậy, phạm vi ảnh hưởng cần xét đồng thời:

1. Số tài sản và chức năng nghiệp vụ có thể tiếp cận.
2. Mức quyền trên từng tài sản.
3. Ranh giới tin cậy bị vượt qua.
4. Thời hạn và khả năng tái sử dụng của quyền hoặc credential.
5. Khả năng truy nguyên hành động về người hay workload chịu trách nhiệm.

## 3. Mô hình một đường di chuyển ngang

### 3.1. Tách người yêu cầu khỏi tài khoản thực thi

Trong PAM, tên người đăng nhập cổng quản trị thường khác tài khoản xuất hiện ở hệ điều hành đích:

```text
Người yêu cầu:          user:linh.ops
Thiết bị khởi tạo:      asset:admin-ws-07
Yêu cầu được duyệt:     grant:G-417
Phiên PAM:             session:P-208
Tài khoản thực thi:     account:prod-admin-23
Đích được duyệt:        asset:app-prod-02
Hành động được duyệt:   restart_application
Thời hạn:               09:00–09:20 UTC
```

Nếu chỉ nhóm log theo `prod-admin-23`, hai người dùng độc lập có thể bị gộp thành một chuỗi. Nếu chỉ nhóm theo `linh.ops`, những bước thực thi dưới tài khoản dịch vụ hoặc danh tính được ủy quyền lại có thể bị bỏ sót.

Hồ sơ điều tra nên giữ cả danh tính nguồn và danh tính thực thi, cùng loại quan hệ giữa chúng. Quan hệ này có thể là sử dụng tài khoản qua broker, lấy secret từ vault, ủy quyền hoặc chuyển sang một danh tính workload. Mỗi loại cần bằng chứng riêng; trùng tên hoặc gần nhau về thời gian không đủ chứng minh quan hệ.

### 3.2. Mô hình đồ thị

Có thể biểu diễn một lần truy cập thành cạnh có thuộc tính:

```text
Nguồn S
  --[danh tính P, giao thức R, thời điểm T,
     phiên X, quyền G, kết quả O, bằng chứng E]-->
Đích D
```

Một chuỗi đáng điều tra:

```text
admin-ws-07
  └─[PAM P-208, được duyệt]─> app-prod-02
                                └─[nguồn phía đích ghi nhận]─> db-prod-01
                                                                  └─> backup-core-01
```

Cạnh đầu hợp lệ không làm các cạnh tiếp theo tự động hợp lệ. Quyền tới `app-prod-02` không đồng nghĩa được phép dùng chính máy này làm nguồn tới `db-prod-01`.

Tuy nhiên, một đồ thị vẽ được chưa chắc là chuỗi xâm nhập đã được chứng minh. Cần phân biệt:

- **Đường truy cập có thể xảy ra:** suy từ cấu hình quyền và khả năng kết nối.
- **Đường hoạt động đã quan sát:** có log cho thấy từng cạnh đã diễn ra.
- **Đường hoạt động được liên kết chắc chắn:** ngoài từng cạnh, có bằng chứng nối các cạnh về đúng phiên, tiến trình hoặc danh tính.

Khoảng cách giữa ba mức này phải được thể hiện trong báo cáo. Không biến một đường tiềm năng trong dữ liệu kiểm kê thành kết luận đã có truy cập thực tế.

### 3.3. Không suy đường đi chỉ từ địa chỉ IP

PAM broker, bastion, NAT và proxy có thể khiến nhiều người dùng xuất hiện với cùng IP. Một phiên hợp lệ qua broker cũng có thể làm IP tại máy đích khác IP thiết bị người dùng.

Nên ưu tiên định danh ổn định của tài sản và phiên, kết hợp log kết nối của broker với log phía đích. Khi chỉ có IP, cần xét khoảng thời gian ánh xạ, nguồn cấp địa chỉ và mức tin cậy. Không nên kết luận rằng mọi truy cập qua cùng bastion đều do cùng người hoặc rằng một IP luôn đại diện cho một máy cố định.

## 4. Những dạng hoạt động cần quan sát

| Dạng hoạt động | Biểu hiện có thể thấy | Ngữ cảnh cần kiểm tra |
| --- | --- | --- |
| Truy cập quản trị giữa các máy | Phiên SSH, RDP hoặc kênh quản trị từ xa tới đích mới | Có đúng thiết bị nguồn, đích và cửa sổ thay đổi không? |
| Dùng credential trên nhiều tài sản | Một tài khoản xuất hiện ở các đích ngoài tập thường dùng | Credential có dùng chung, bị lấy ngoài broker hay thuộc job quản lý tập trung không? |
| Vượt tầng quản trị | Nguồn ở tầng ứng dụng truy cập hệ thống quản trị danh tính hoặc sao lưu | Có chính sách cho phép đúng hướng và đúng chức năng không? |
| Tài khoản dịch vụ có hành vi tương tác | Danh tính workload xuất hiện trong loại phiên thường dành cho người | Có cơ chế bảo trì được duyệt và ánh xạ người chịu trách nhiệm không? |
| Hoạt động sau phiên PAM | Máy đã được quản trị tiếp tục tạo kết nối đặc quyền mới | Phiên cũ đã kết thúc chưa; tác vụ nền nào vẫn được phép chạy? |
| Thực thi trên máy đích | Sau xác thực có bằng chứng hoạt động quản trị hoặc tiến trình liên quan | Có khớp mục đích, quyền hạn và phiên không? |
| Chuỗi đa môi trường | Từ workload nội bộ chuyển sang control plane hoặc tài khoản cloud khác | Quyền ủy quyền và ranh giới tài nguyên được giới hạn thế nào? |

Các giao thức hoặc công cụ quản trị không tự mang tính độc hại. Cùng một kênh có thể phục vụ bảo trì, tự động hóa hoặc hành vi xâm nhập. Tín hiệu có giá trị khi giải thích được hành vi nào vượt quan hệ truy cập mong đợi.

Một lượt xác thực thất bại chỉ chứng minh có nỗ lực xác thực. Một lượt thành công thường chứng minh đạt một bước truy cập, nhưng chưa mặc nhiên chứng minh đã chạy lệnh, truy cập dữ liệu hay điều khiển toàn bộ máy. Những kết luận đó cần bằng chứng tương ứng.

## 5. Thu thập dữ liệu đủ để nối chuỗi

### 5.1. Các lớp bằng chứng

| Nguồn dữ liệu | Giá trị chính | Giới hạn cần nhớ |
| --- | --- | --- |
| PAM request và approval | Ai xin quyền, lý do, tập đích, quyền và thời hạn | Quyền được duyệt không chứng minh mọi hoạt động sau đó hợp lệ |
| PAM session và broker | Ánh xạ người dùng, tài khoản đích, phiên và đường kết nối | Có thể không thấy truy cập đi thẳng hoặc hoạt động bên trong một kênh mã hóa |
| Vault audit | Ai hoặc workload nào lấy credential, phiên bản và thời điểm | Secret đã được lấy không chứng minh nó đã được dùng trên máy nào |
| Xác thực phía đích và nhà cung cấp danh tính | Danh tính, nguồn, đích, kết quả xác thực | Một sự kiện chưa chắc mô tả đầy đủ chuỗi ủy quyền hay hoạt động tiếp theo |
| Telemetry máy chủ hoặc endpoint | Tiến trình, phiên đăng nhập, kết nối và tác vụ quản trị | Độ đầy đủ phụ thuộc cấu hình thu thập và sức khỏe agent |
| Network flow hoặc firewall | Quan hệ nguồn–đích, thời điểm và kết quả kết nối quan sát được | Kết nối mạng không tự xác định người hay chứng minh xác thực thành công |
| Audit của nền tảng và control plane | Hành động API, danh tính thực thi, tài nguyên và kết quả | Cần nối chuỗi ủy quyền và danh tính workload |
| Kiểm kê tài sản và chính sách | Vai trò máy, mức quan trọng, tầng tin cậy, đường truy cập cho phép | Dữ liệu cũ có thể làm sai đánh giá rủi ro |

Đối với tài sản trọng yếu, nên có tối thiểu hai góc nhìn độc lập cho những bước quan trọng, chẳng hạn log PAM và log phía đích. Hai bản sao cùng một sự kiện đi qua hai pipeline không phải hai bằng chứng độc lập.

### 5.2. Hợp đồng dữ liệu chuẩn hóa

Một bản ghi chuẩn hóa nên đủ để trả lời “ai, từ đâu, tới đâu, dùng quyền gì, khi nào, làm gì, biết từ nguồn nào”. Ví dụ mô phỏng:

```json
{
  "event_id": "evt-006-02",
  "event_time": "2026-05-12T09:08:00Z",
  "ingest_time": "2026-05-12T09:08:06Z",
  "event_kind": "remote_authentication",
  "outcome": "success",
  "actor_id": null,
  "execution_principal_id": "account:prod-admin-23",
  "source_asset_id": "asset:app-prod-02",
  "target_asset_id": "asset:db-prod-01",
  "protocol": "ssh",
  "pam_session_id": null,
  "grant_id": null,
  "evidence_source": "target_auth_audit",
  "source_event_ref": "db-prod-01/auth/771",
  "attribution_confidence": "unresolved"
}
```

Trong bản ghi này, tên người khởi tạo, phiên PAM và grant chưa được xác định. Giá trị `null` thể hiện thiếu ánh xạ, không có nghĩa chắc chắn truy cập không được cấp phép. Một bước tương quan có thể bổ sung liên kết sau đó, kèm bằng chứng và mức tin cậy, nhưng phải giữ được dữ liệu gốc.

Các trường mở rộng hữu ích gồm định danh tenant hoặc realm, định danh thiết bị, loại tài khoản, phương thức xác thực, phiên đăng nhập trên đích, tham chiếu tiến trình, tầng tài sản, hành động và phiên bản chính sách.

Không lưu mật khẩu, private key, token hay nội dung secret vào sự kiện tương quan. Khi cần nối lần lấy credential với lần sử dụng, dùng định danh đối tượng credential hoặc phiên bản từ hệ thống quản lý, không sao chép giá trị bí mật.

### 5.3. Danh tính và thời gian là điều kiện nền

Một tên như `administrator` có thể tồn tại độc lập trên nhiều máy. Định danh nên chứa phạm vi tài khoản: local account của máy nào, tài khoản domain nào, workload thuộc tenant nào. Tên hiển thị thay đổi không được làm mất liên kết lịch sử.

Nên giữ cả thời gian xảy ra và thời gian nhận sự kiện. Đồng hồ lệch, log đến muộn và pipeline mất dữ liệu có thể tạo ra thứ tự giả. Quy tắc tương quan cần khoảng dung sai, cơ chế tiếp nhận sự kiện đến trễ và khả năng cập nhật kết luận.

Nếu log đích chỉ ghi nhận sau vài phút, cảnh báo ban đầu có thể mang trạng thái “cần xác minh”. Không nên tự động nâng mức chắc chắn chỉ vì hết thời gian chờ; hết thời gian chỉ là điều kiện xử lý dữ liệu, không tạo ra bằng chứng mới.

## 6. Phân biệt quyền được duyệt với hoạt động hợp lệ

Một grant nên được đánh giá theo một tập điều kiện cụ thể:

```text
Grant hợp lệ cho một sự kiện khi:
  đúng chủ thể được cấp quyền hoặc đúng chuỗi ủy quyền
  AND đúng tài khoản hoặc vai trò thực thi
  AND đúng tài sản đích
  AND đúng nguồn hoặc đường kết nối nếu chính sách yêu cầu
  AND đúng loại hành động
  AND nằm trong khoảng hiệu lực
  AND chưa bị thu hồi theo chính sách áp dụng
```

Đây là mô hình khái niệm. Mỗi nền tảng có thể thực thi các điều kiện ở những điểm khác nhau; dữ liệu phát hiện phải biết điều kiện nào thực sự được kiểm soát và điều kiện nào chỉ được kiểm tra sau sự kiện.

Phép đối chiếu cần trả ít nhất ba kết quả:

| Kết quả | Ý nghĩa | Hướng xử lý |
| --- | --- | --- |
| MATCH | Bằng chứng hiện có khớp phạm vi được duyệt | Tiếp tục xét hành vi; không tự đóng mọi cảnh báo |
| MISMATCH | Có dữ kiện cụ thể trái phạm vi được duyệt | Nêu rõ điều kiện lệch và bằng chứng |
| UNKNOWN | Thiếu dữ liệu để xác định | Tìm bổ sung nguồn, không đổi thành MISMATCH |

Ví dụ, một grant chỉ cho `app-prod-02` trong 20 phút không bao phủ truy cập tới `db-prod-01`, dù cùng tài khoản và cùng khoảng thời gian. Ngược lại, nếu hệ thống chưa nhận log grant thì chưa đủ cơ sở nói rằng “không có phê duyệt”.

TTL của quyền JIT cũng cần được hiểu chính xác. Hết thời hạn cấp quyền có thể chặn lần cấp quyền mới nhưng không nhất thiết hủy mọi phiên đang mở, token đã phát hành hoặc tác vụ đã bắt đầu. Cần biết cơ chế thực tế để đánh giá truy cập sau thời hạn và để thu hồi đúng đối tượng.

Một grant khớp hoàn toàn vẫn có thể được sử dụng trong phiên đã bị chiếm quyền. Do đó, đối chiếu grant là một lớp bằng chứng; nguồn thiết bị, chuỗi hành động và hành vi trên đích vẫn phải được quan sát.

## 7. Các tín hiệu phát hiện quan trọng

### 7.1. Một nguồn truy cập nhiều đích mới

Phát hiện sự tăng đột biến số đích quản trị từ một nguồn hoặc một phiên có thể giúp nhận ra hành vi mở rộng phạm vi. Tuy nhiên, cần so với chức năng của nguồn: máy quản trị cá nhân khác hệ thống triển khai tập trung.

Đơn vị phân tích nên là danh tính–nguồn–vai trò công việc, không chỉ danh tính. Một tài khoản xuất hiện trên mười máy qua hệ thống điều phối đã biết có ý nghĩa khác khi nó xuất hiện từ một máy ứng dụng vốn không được làm nguồn quản trị.

Cảnh báo nên giữ danh sách đích, tập đích mới, mức quan trọng và các ranh giới bị vượt qua. Một số đếm tổng hợp không đủ để điều tra.

### 7.2. Truy cập nối tiếp qua máy trung gian

Chuỗi A → B rồi B → C đáng chú ý nếu B không được phép làm nguồn quản trị hoặc C nằm ngoài phạm vi cấp quyền. Sự gần nhau về thời gian chỉ là tín hiệu ban đầu.

Để tăng độ tin cậy, tìm liên kết giữa phiên trên B và kết nối từ B tới C, chẳng hạn định danh phiên đăng nhập, quan hệ tiến trình hoặc bằng chứng broker. Nếu không có liên kết, báo cáo “hai cạnh gần nhau cần xác minh”, thay vì khẳng định người ở A đã khởi tạo cạnh B → C.

### 7.3. Vượt ranh giới tin cậy hoặc tầng quản trị

Một chuyển tiếp tới hệ thống danh tính, backup, điều phối hạ tầng hoặc control plane có thể cần ưu tiên hơn nhiều kết nối trong cùng nhóm máy ứng dụng.

Ranh giới không chỉ là subnet. Nó có thể là production với non-production, tenant khác nhau, phạm vi khách hàng khác nhau hoặc tài sản thuộc nhóm quản trị khác. Chính sách và kiểm kê phải mô tả ranh giới có ý nghĩa đối với tổ chức.

### 7.4. Tài khoản dịch vụ được dùng sai kiểu

Tài khoản dịch vụ thường có tập nguồn, đích và loại hành động tương đối xác định. Các thay đổi cần chú ý gồm xuất hiện trên nguồn mới, sử dụng trong phiên tương tác hoặc truy cập tài sản ngoài chức năng của workload.

Trước khi kết luận, kiểm tra cơ chế bảo trì, thay đổi kiến trúc và quan hệ ủy quyền hợp lệ. Ngoại lệ cần giới hạn theo nguồn, đích, hành động và thời hạn; không miễn toàn bộ cảnh báo chỉ vì tài khoản thuộc nhóm “service account”.

### 7.5. Truy cập đặc quyền không ánh xạ được với PAM

Một lần xác thực thành công không có phiên PAM tương ứng có thể cho thấy đi vòng broker, credential được sử dụng trực tiếp hoặc dữ liệu PAM chưa được nối đầy đủ.

Cảnh báo cần phân biệt “đã xác minh đường truy cập đi thẳng” với “chưa tìm thấy ánh xạ”. Kiểm tra cả đường truy cập khẩn cấp, cơ chế tự động hóa được duyệt và sức khỏe pipeline trước khi chọn hành động ứng phó.

### 7.6. Hành vi tiếp diễn sau thu hồi

Nếu một danh tính tiếp tục tạo phiên hoặc thực hiện hành động sau khi quyền đã bị thu hồi, cần xác định chính xác đối tượng nào vẫn còn hiệu lực: phiên hiện hữu, credential tĩnh, token, chứng thư hay quyền trong hệ thống đích.

Đổi mật khẩu không tự bảo đảm đóng mọi phiên và thu hồi mọi token. Việc kiểm tra hậu thu hồi phải quan sát hoạt động thực tế từ các nguồn phù hợp, thay vì chỉ dựa vào phản hồi thành công của API quản trị.

## 8. Xây dựng quy tắc tương quan có thể giải thích

### 8.1. Tách phát hiện cạnh khỏi liên kết chuỗi

Một thiết kế thuận tiện cho vận hành gồm hai lớp:

1. **Lớp sự kiện truy cập:** tạo bản ghi chuẩn cho từng nỗ lực, lần truy cập thành công hoặc hành động quản trị.
2. **Lớp tương quan:** liên kết các bản ghi thành chuỗi có bằng chứng, đánh giá phạm vi quyền và tạo hồ sơ điều tra.

Việc tách lớp giúp tránh coi một kết nối mạng là một phiên xác thực thành công. Nó cũng cho phép cập nhật chuỗi khi log đến muộn, trong khi vẫn giữ được sự kiện ban đầu.

Mã giả sau minh họa quy tắc cho truy cập nối tiếp:

```text
FOR mỗi sự kiện truy cập thành công e2:
    kiểm tra schema, phạm vi tenant và định danh tài sản
    loại bản sao dựa trên nguồn và định danh sự kiện gốc

    tìm các sự kiện e1 sao cho:
        e1.target_asset_id = e2.source_asset_id
        thời điểm phù hợp cửa sổ tương quan và dung sai đồng hồ

    FOR mỗi cặp ứng viên (e1, e2):
        link = tìm_bằng_chứng_liên_kết(e1, e2)
        authorization = đối_chiếu_quyền_cho_e2()
        boundary = đánh_giá_ranh_giới(e2.source, e2.target)
        baseline = so_với_hành_vi_đã_xác_minh()
        quality = đánh_giá_độ_đầy_đủ_telemetry()

        IF chỉ trùng thời gian hoặc tài khoản dùng chung:
            lưu giả thuyết, không khẳng định cùng tác nhân

        IF có điều kiện đáng điều tra:
            tạo hoặc cập nhật hồ sơ gồm:
                sự kiện và tham chiếu gốc
                các liên kết đã chứng minh
                các liên kết còn giả thuyết
                authorization MATCH / MISMATCH / UNKNOWN
                ranh giới, tài sản trọng yếu và mức ảnh hưởng
                độ tin cậy, dữ liệu còn thiếu và lý do cảnh báo
```

Một cửa sổ 15 phút có thể dùng để minh họa trong bài kiểm tra, nhưng không phải ngưỡng mặc định cho mọi môi trường. Cửa sổ quá ngắn bỏ sót hoạt động chậm; cửa sổ quá dài làm tăng các liên kết trùng hợp. Có thể dùng nhiều cửa sổ phù hợp từng loại công việc và cập nhật hồ sơ theo sự kiện mới.

Không nên nối chuỗi xuyên tenant, realm hoặc phạm vi tài khoản chỉ vì chuỗi tên giống nhau. Những quan hệ xuyên phạm vi phải có ánh xạ hoặc bằng chứng ủy quyền rõ ràng.

### 8.2. Hành vi nền phải có nguồn gốc

Hành vi thường gặp không tự đồng nghĩa hành vi hợp lệ. Nếu lấy mọi truy cập quá khứ làm dữ liệu “bình thường”, một hoạt động xâm nhập kéo dài có thể dần trở thành baseline.

Nên xây dựng baseline từ công việc đã được xác minh, có chủ sở hữu và phạm vi cụ thể:

- Tập nguồn và đích theo vai trò quản trị hoặc workload.
- Loại giao thức, hành động và quyền cần dùng.
- Cửa sổ vận hành, chu kỳ công việc và lượng thay đổi dự kiến.
- Những ranh giới luôn cần phê duyệt bổ sung.
- Ngày rà soát, nguồn dữ liệu và thời hạn của ngoại lệ.

Với danh tính mới hoặc tài sản mới, đánh dấu thiếu lịch sử. Không đánh giá “không có bất thường” chỉ vì chưa đủ dữ liệu để so sánh.

Các thay đổi hợp lệ nên cập nhật baseline sau xác minh, không để một ngoại lệ tạm thời âm thầm trở thành quyền truy cập lâu dài.

### 8.3. Tách mức ảnh hưởng khỏi độ tin cậy

Một cảnh báo tới hệ thống rất quan trọng có thể có mức ảnh hưởng tiềm năng lớn nhưng độ tin cậy thấp vì thiếu log nguồn. Ngược lại, một truy cập ngoài phạm vi đã được chứng minh tới máy thử nghiệm có thể có độ tin cậy cao nhưng mức ảnh hưởng thấp hơn.

Có thể dùng hai trục độc lập:

| Trục | Căn cứ minh họa |
| --- | --- |
| Ảnh hưởng | Mức quan trọng của đích, loại quyền, ranh giới bị vượt và số hệ thống liên quan |
| Độ tin cậy | Chất lượng định danh, bằng chứng nối phiên, mức đầy đủ của log và kết quả đối chiếu quyền |

Điểm số, nếu sử dụng, phải là công cụ sắp xếp ưu tiên được hiệu chỉnh bằng dữ liệu thực tế. Một tổng điểm cao không thay thế việc nêu rõ hành vi và bằng chứng.

Tổ chức có thể ưu tiên điều tra ngay cảnh báo “ảnh hưởng cao, độ tin cậy thấp” để bổ sung dữ liệu. Điều đó không có nghĩa đủ căn cứ thực hiện mọi hành động cô lập tự động.

### 8.4. Hồ sơ cảnh báo nên chứa gì?

Một cảnh báo hữu ích phải giúp người trực ca tiếp tục điều tra mà không phải dựng lại toàn bộ ngữ cảnh:

```yaml
alert_type: suspected_lateral_movement
case_id: CASE-LM-006
first_observed_at: "2026-05-12T09:08:00Z"
last_observed_at: "2026-05-12T09:08:03Z"
observed_path:
  - "asset:admin-ws-07 -> asset:app-prod-02"
  - "asset:app-prod-02 -> asset:db-prod-01"
actor_attribution: linked_to_session_with_endpoint_evidence
pam_session_id: "session:P-208"
execution_principal_id: "account:prod-admin-23"
authorization: MISMATCH
mismatch_reason: target_not_in_grant
impact: high
confidence: high
evidence_refs:
  - "pam/session/P-208"
  - "app-prod-02/endpoint/552"
  - "db-prod-01/auth/771"
missing_evidence:
  - "complete command history on database host"
recommended_next_step: "Validate target activity and contain the linked access path"
```

Đây là schema minh họa cho cảnh báo, không phải nội dung cấu hình bắt buộc của sản phẩm. Trong tình huống này, mức tin cậy cao xuất phát từ bằng chứng liên kết cụ thể đã nêu; nếu chỉ có hai log xác thực rời rạc thì phải hạ mức quy kết.

Nên giữ phiên bản quy tắc, phiên bản chính sách, các giả định và những lần cập nhật kết luận. Khi dữ liệu mới làm một cảnh báo chuyển từ UNKNOWN sang MATCH, lịch sử ban đầu vẫn cần được lưu để giải thích quyết định vận hành.

## 9. Tình huống điều tra xuyên một phiên PAM

### 9.1. Bối cảnh và dữ liệu ban đầu

Đội vận hành duyệt cho Linh khởi động lại ứng dụng trên `app-prod-02`. Tài khoản `prod-admin-23` là tài khoản quản trị tập trung đã được kiểm kê; trong ví dụ này, nó không phải hai local account trùng tên trên hai máy khác nhau.

Grant G-417 chỉ cho phép đích `app-prod-02`, nguồn quản trị đã đăng ký và hành động `restart_application` từ 09:00 tới 09:20 UTC. `app-prod-02` không được phép làm máy trung gian quản trị tới `db-prod-01`.

| Thời điểm UTC | Quan sát | Ý nghĩa trực tiếp |
| --- | --- | --- |
| 09:01:00 | PAM tạo phiên P-208 từ admin-ws-07 tới app-prod-02 | Có một phiên tới đích được duyệt |
| 09:04:00 | Telemetry ghi nhận tác vụ khởi động lại ứng dụng | Hành động này phù hợp mục đích grant |
| 09:08:00 | db-prod-01 ghi xác thực thành công của prod-admin-23 từ app-prod-02 | Có một cạnh truy cập mới ngoài đích được duyệt |
| 09:08:02 | Telemetry trên app-prod-02 liên kết kết nối đi ra với phiên đăng nhập đã ánh xạ P-208 | Tăng độ tin cậy liên kết cạnh mới với phiên PAM |
| 09:08:03 | Audit phía db-prod-01 ghi hoạt động quản trị tiếp theo | Có bằng chứng vượt bước xác thực |
| 09:09:00 | Hệ thống tương quan phát cảnh báo | Cần xác minh hành động và ngăn phạm vi ảnh hưởng tiếp tục mở rộng |

### 9.2. Kết luận được phép rút ra

Có đủ căn cứ nói rằng đã xuất hiện hoạt động quản trị từ `app-prod-02` tới `db-prod-01` ngoài phạm vi grant G-417, và bằng chứng hiện có liên kết hoạt động này với phiên P-208.

Chưa đủ căn cứ nói Linh cố ý thực hiện hành vi xấu. Phiên hoặc thiết bị của người dùng có thể bị chiếm quyền, có thể có thay đổi không được ghi nhận, hoặc có vấn đề khác cần kiểm tra. Danh tính gắn với phiên là đầu mối điều tra, không tự chứng minh động cơ của một cá nhân.

Cũng chưa thể kết luận dữ liệu đã bị lấy, mọi quyền trên database đã bị kiểm soát hoặc các tài sản khác đã bị truy cập. Mỗi kết luận đó cần nguồn bằng chứng bổ sung.

### 9.3. Những bước xác minh tiếp theo

Người điều tra cần đối chiếu approval gốc và lịch sử thay đổi grant, kiểm tra độ tin cậy của ánh xạ phiên trên `app-prod-02`, lấy hoạt động phía database và xác định có phiên hoặc credential nào tiếp tục sử dụng được.

Đồng thời, rà soát hoạt động lân cận của cùng tài khoản, thiết bị nguồn và tài sản trung gian. Mở rộng phạm vi theo bằng chứng mới, không mặc định mọi truy cập của tài khoản trong nhiều ngày đều thuộc cùng sự cố.

Nếu telemetry chỉ cho thấy A → B và B → C nhưng không liên kết được phiên, kết luận phải thu hẹp thành “đã quan sát hai cạnh phù hợp một giả thuyết di chuyển ngang”. Việc thiếu bằng chứng liên kết ảnh hưởng mức quy kết, nhưng không xóa đi vi phạm chính sách nguồn–đích đã được chứng minh độc lập.

## 10. Giảm cảnh báo sai mà vẫn giữ khả năng phát hiện

### 10.1. Quản trị hàng loạt và triển khai tự động

Một nền tảng triển khai có thể truy cập nhiều máy trong một khoảng ngắn. Xác minh định danh workload, nguồn điều phối, tập đích, lịch triển khai và loại tác vụ trước khi coi số lượng đích lớn là bất thường.

Ngoại lệ phù hợp có thể là “workload triển khai X, từ nguồn Y, tới nhóm máy Z, cho hành động R, trong cửa sổ T”. Ngoại lệ “tài khoản X luôn được miễn” sẽ làm mất khả năng phát hiện khi cùng tài khoản được dùng từ nguồn khác.

### 10.2. Bảo trì qua bastion dùng chung

Nhiều người quản trị có thể cùng xuất hiện dưới IP của bastion. Cần dùng mapping của broker hoặc phiên đăng nhập trên bastion để phân biệt. Nếu không có dữ liệu này, giữ hạn chế quy kết trong cảnh báo; không chọn người dùng đầu tiên thấy trong log rồi gán mọi hoạt động cho họ.

### 10.3. Truy cập khẩn cấp

Break-glass có thể tạo ra đường truy cập khác luồng thông thường. Tuy vậy, cần có định danh cơ chế khẩn cấp, sự kiện kích hoạt, người chịu trách nhiệm, phạm vi, thời hạn và hậu kiểm.

Một trường nhãn “emergency” do bên gọi tự gửi không đủ để xác nhận ngoại lệ. Phải đối chiếu nguồn có thẩm quyền của quy trình khẩn cấp.

### 10.4. Thiếu log và thay đổi địa chỉ

Mất collector, ánh xạ tài sản lỗi hoặc log tới muộn có thể tạo ra tín hiệu “ngoài PAM”. Trạng thái sức khỏe telemetry nên được đưa vào cảnh báo như một thành phần chất lượng dữ liệu.

Không nên tắt toàn bộ phát hiện khi một nguồn log mất. Có thể tiếp tục cảnh báo về những cạnh đã được chứng minh, đồng thời nêu rõ phần xác minh quyền hoặc danh tính đang UNKNOWN.

## 11. PAM ngăn chặn và hỗ trợ phát hiện như thế nào?

| Kiểm soát | Tác dụng với di chuyển ngang | Giới hạn cần thiết kế bổ sung |
| --- | --- | --- |
| Kiểm kê và chủ sở hữu tài khoản | Làm rõ nơi một danh tính được phép hoạt động | Kiểm kê cũ hoặc tài khoản không quản lý tạo điểm mù |
| Least privilege | Giảm quyền và tập tài sản có thể tiếp cận | Quyền nhỏ nhưng kết hợp nhiều quan hệ vẫn có thể mở đường |
| Phân tầng quản trị | Giới hạn đường truy cập giữa các mức tin cậy | Cần kiểm soát nguồn, đích và danh tính thực tế |
| JIT | Giảm thời gian quyền cao được duy trì | Cần xử lý phiên, token và quyền đã phát sinh khi hết hạn |
| JEA | Giới hạn hoạt động quản trị cần thiết | Tập hành động phải được thiết kế và kiểm chứng theo nghiệp vụ |
| Vault và credential rotation | Quản lý việc cấp secret và giảm thời gian sử dụng lại | Secret đã lấy ra, phiên còn mở và cơ chế xác thực khác vẫn cần xem xét |
| Broker và session recording | Cung cấp điểm kiểm soát và bằng chứng truy nguyên | Truy cập đi vòng, kênh không quan sát được và phiên bị chiếm quyền vẫn có thể tồn tại |
| Segmentation và đường quản trị riêng | Thu hẹp khả năng kết nối từ tài sản bị xâm nhập | Kết nối được phép vẫn cần kiểm soát danh tính và hành động |

Một thiết kế tốt giảm cả khả năng xảy ra lẫn chi phí điều tra. Ví dụ, credential riêng theo tài sản và quyền theo phiên giúp thu hẹp phạm vi ảnh hưởng, trong khi mapping ổn định giữa người dùng và tài khoản thực thi giúp xác định chuỗi hoạt động nhanh hơn.

Không nên xem việc “đã có PAM” là bằng chứng mọi đường quản trị đều đi qua PAM. Phải xác minh đường đi thẳng, tài khoản cục bộ, tự động hóa và cơ chế khẩn cấp có nằm trong phạm vi kiểm soát hay không.

## 12. Ứng phó khi nghi có di chuyển ngang

### 12.1. Ưu tiên chặn sự lan rộng và giữ bằng chứng

Trình tự thực tế phụ thuộc mức khẩn cấp. Nếu hoạt động đang tiếp diễn tới tài sản trọng yếu, việc cô lập có thể phải thực hiện ngay theo playbook đã phê duyệt, đồng thời thu thập bằng chứng trong khả năng cho phép.

Các đầu việc cần được phân công rõ:

1. Xác minh cảnh báo, thời gian, tài sản và những liên kết đã chứng minh.
2. Bảo toàn log gốc, audit grant, mapping phiên và tham chiếu sự kiện.
3. Chặn đường truy cập hoặc phiên liên quan theo phạm vi đã xác định.
4. Thu hồi quyền và phương tiện xác thực có khả năng tiếp tục bị sử dụng.
5. Mở rộng điều tra tới các cạnh hoặc danh tính có bằng chứng liên quan.
6. Xác minh hành động ứng phó thực sự có hiệu lực.

Thông tin bằng chứng nên gồm nguồn thu thập, người hoặc hệ thống thu thập, thời điểm, khoảng thời gian dữ liệu, giá trị kiểm tra toàn vẹn và quyền truy cập hồ sơ. Không đưa secret vào ticket điều tra.

### 12.2. Chọn đúng đối tượng thu hồi

| Đối tượng | Câu hỏi cần trả lời |
| --- | --- |
| Phiên PAM | Đã kết thúc được phiên hiện hữu hay chỉ chặn tạo phiên mới? |
| Tài khoản người dùng | Có cần chặn tạm, yêu cầu xác thực lại hoặc xử lý thiết bị nguồn không? |
| Credential tĩnh | Những hệ thống nào đang dùng và có thể cập nhật an toàn theo thứ tự nào? |
| Token hoặc chứng thư | Có cơ chế thu hồi hay phải chờ hết hạn; phiên nào vẫn còn hiệu lực? |
| Quyền JIT hoặc vai trò tạm thời | Quyền trên hệ thống đích đã được gỡ và xác minh chưa? |
| Tài khoản dịch vụ | Tác động tới workload nào; có cơ chế thay credential và kiểm tra phục hồi không? |
| Tài sản trung gian | Cần cô lập đường quản trị, máy hoặc phân đoạn nào để chặn cạnh tiếp theo? |

Đặc biệt với tài khoản dịch vụ, đổi credential hàng loạt khi chưa biết phụ thuộc có thể gây gián đoạn và che khuất hoạt động cần điều tra. Phạm vi thu hồi phải dựa trên bằng chứng và kế hoạch khôi phục của workload; điều này không loại trừ hành động khẩn cấp khi playbook yêu cầu ngăn thiệt hại đang xảy ra.

### 12.3. Kiểm tra hậu ứng phó

Một phản hồi “success” từ hệ thống quản trị chỉ chứng minh lệnh điều khiển được xử lý ở một mức nào đó. Cần kiểm tra thêm trạng thái phiên, quyền phía đích và những lần xác thực hoặc hành động phát sinh sau đó.

Xác minh cả truy cập hợp lệ của dịch vụ sau thay đổi, theo dõi các đường thay thế và ghi lại khoảng thời gian còn tồn tại rủi ro. Không đóng sự cố chỉ vì credential đã được xoay vòng.

## 13. Bài thực hành bằng dữ liệu mô phỏng

Bài thực hành chỉ cần các bản ghi giả lập trong bảng hoặc môi trường phân tích thử nghiệm. Không cần thực hiện hành vi di chuyển ngang trên hệ thống thật.

### 13.1. Chuẩn bị mô hình

Tạo mô hình bốn nhóm tài sản: máy quản trị, máy ứng dụng, máy dữ liệu và hệ thống sao lưu. Mỗi tài sản có định danh, tầng tin cậy và chủ sở hữu. Mỗi danh tính có loại tài khoản, nguồn hợp lệ, tập đích và quyền cần dùng.

Định nghĩa các sự kiện truy cập với thời gian, nguồn, đích, tài khoản thực thi, kết quả, phiên và tham chiếu bằng chứng. Tách dữ liệu approval khỏi dữ liệu hoạt động để kiểm tra được ba trạng thái MATCH, MISMATCH và UNKNOWN.

### 13.2. Bộ tình huống tối thiểu

| Tình huống | Dữ kiện mô phỏng | Kết quả mong đợi |
| --- | --- | --- |
| Quản trị hợp lệ | Nguồn, đích, tài khoản, hành động và thời gian đều khớp grant | MATCH; không gán kết luận xâm nhập chỉ vì dùng giao thức quản trị |
| Vượt đích được duyệt | Phiên tới máy ứng dụng tạo cạnh mới tới máy dữ liệu ngoài grant | MISMATCH cho cạnh mới; độ quy kết dựa trên bằng chứng liên kết |
| Hai phiên qua cùng bastion | Hai người dùng có cùng IP broker nhưng phiên khác nhau | Không gộp thành một tác nhân chỉ từ IP |
| Log approval tới muộn | Có truy cập thành công, grant chỉ xuất hiện ở pipeline sau đó | Ban đầu UNKNOWN, cập nhật MATCH khi đủ căn cứ; giữ lịch sử |
| Tài khoản dịch vụ đúng chức năng | Workload sao lưu truy cập nhiều đích trong phạm vi đã duyệt | Không coi fan-out đơn thuần là xâm nhập |
| Tài khoản dịch vụ sai nguồn | Cùng danh tính xuất hiện từ máy người dùng ngoài nguồn cho phép | Nêu rõ vi phạm nguồn và tìm bằng chứng hành động |
| Phiên khớp grant nhưng bị nghi chiếm quyền | Grant hợp lệ, có tín hiệu thiết bị hoặc hành động bất thường | Không đóng cảnh báo chỉ vì MATCH |
| Sau thu hồi còn hoạt động | Quyền bị gỡ nhưng phiên hiện hữu tiếp tục hành động | Xác định đối tượng còn hiệu lực và yêu cầu kiểm tra hậu thu hồi |
| Sai thứ tự nhận log | Sự kiện B → C đến trước A → B | Tương quan theo thời gian sự kiện và cập nhật khi đủ dữ liệu |
| Hai local account trùng tên | Tên tài khoản giống nhau nhưng thuộc hai máy độc lập | Không tự coi là một credential hoặc một danh tính duy nhất |

### 13.3. Sản phẩm người học cần hoàn thành

Người học xây dựng một hồ sơ cảnh báo cho từng tình huống đáng điều tra. Hồ sơ phải chỉ ra cạnh nào đã được quan sát, liên kết nào đã chứng minh, điều kiện quyền nào lệch, thông tin nào còn thiếu và bước xác minh kế tiếp.

Với tình huống hợp lệ, giải thích cụ thể vì sao dữ liệu khớp phạm vi. Với tình huống thiếu log, giữ UNKNOWN thay vì tạo một kết luận chắc chắn giả.

Cuối bài, thử phát lại cùng một sự kiện nhiều lần và đưa log đến trễ. Kết quả mong muốn là hồ sơ được cập nhật có lịch sử, không tạo hàng loạt sự cố trùng nhau hoặc thay đổi danh tính tác nhân một cách tùy tiện.

## 14. Đánh giá hiệu quả phát hiện

Nên đo hiệu quả theo khả năng quan sát và xử lý, thay vì chỉ đếm số cảnh báo:

- **Bao phủ telemetry:** tỷ lệ tài sản hoặc đường quản trị trong phạm vi có đủ nguồn log cần thiết; mẫu số phải dựa trên kiểm kê đã xác định.
- **Khả năng quy kết phiên:** tỷ lệ truy cập đặc quyền có thể nối tới đúng người hoặc workload bằng bằng chứng phù hợp.
- **Độ trễ phát hiện:** thời gian từ sự kiện đầu tiên đủ điều kiện quan sát tới cảnh báo; theo dõi riêng độ trễ thu thập log.
- **Chất lượng cảnh báo đã phân xử:** tỷ lệ cảnh báo hữu ích trong tập đã được điều tra, cùng các nguyên nhân gây nhiễu phổ biến.
- **Hiệu lực thu hồi:** thời gian từ quyết định ứng phó tới khi quyền, phiên và phương tiện xác thực liên quan được xác minh không còn dùng được theo mục tiêu ứng phó.
- **Tính đầy đủ của hồ sơ:** tỷ lệ vụ việc có bằng chứng gốc, lý do kết luận và lịch sử thay đổi trạng thái.

Tỷ lệ chính xác trên tập cảnh báo đã phân xử không cho biết hệ thống bỏ sót bao nhiêu hành vi. Để tìm điểm mù, cần các tình huống kiểm tra được phê duyệt, phát lại dữ liệu đã gắn nhãn và rà soát những đường truy cập chưa có telemetry.

Khi không biết thời điểm xâm nhập thực tế, không nên gán thời điểm log đầu tiên thành thời điểm bắt đầu sự cố. Ghi rõ mốc đo là “lần đầu quan sát” hay “lần đầu đủ bằng chứng phát hiện”.

## 15. Câu hỏi tự kiểm tra

1. Vì sao một lần SSH thành công chưa đủ chứng minh có di chuyển ngang độc hại?
2. Một grant cho máy ứng dụng còn hiệu lực có bao phủ lần truy cập tiếp theo tới máy dữ liệu không?
3. Hai truy cập qua cùng IP bastion cần thêm bằng chứng gì trước khi quy về cùng người dùng?
4. Điểm khác nhau giữa MISMATCH và UNKNOWN trong đối chiếu quyền là gì?
5. Vì sao xoay credential chưa bảo đảm mọi phiên đang hoạt động đã bị thu hồi?
6. Làm sao tránh để baseline học cả hoạt động xâm nhập kéo dài?
7. Khi nào có thể nói đã quan sát đường A → B → C, và khi nào chỉ có hai cạnh chưa liên kết chắc chắn?
8. Ngoại lệ cho workload quản trị hàng loạt nên giới hạn theo những chiều nào?

Các điểm cần nêu trong câu trả lời: kết quả xác thực khác mục đích và hành động; quyền phải đối chiếu đúng phạm vi; IP không phải danh tính; thiếu dữ liệu không phải bằng chứng vi phạm; phiên, token và credential có vòng đời khác nhau; baseline phải có nguồn đã xác minh; quy kết chuỗi cần bằng chứng liên kết; ngoại lệ cần giới hạn nguồn, đích, hành động, thời gian và chủ sở hữu.

## 16. Ghi nhớ khi áp dụng

Phát hiện di chuyển ngang trong PAM bắt đầu từ quan hệ truy cập mong đợi và các cạnh hoạt động đã được quan sát. Giá trị của cảnh báo nằm ở khả năng chỉ ra sự lệch phạm vi, truy nguyên danh tính và giải thích giới hạn bằng chứng.

Kiểm kê tốt, quyền tối thiểu, cấp quyền theo nhu cầu, kiểm soát đường quản trị và vòng đời credential giúp giảm số đường có thể bị sử dụng. Telemetry có định danh ổn định, đối chiếu grant ba trạng thái và xác minh hậu thu hồi giúp đội vận hành nhận ra, điều tra và chặn những đường vẫn phát sinh.
