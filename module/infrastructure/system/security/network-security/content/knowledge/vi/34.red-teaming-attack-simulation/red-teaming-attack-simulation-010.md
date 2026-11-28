# Bảo vệ dữ liệu sản xuất trong bài diễn tập

## 1. Vì sao bảo vệ dữ liệu là ranh giới quan trọng nhất của red team?

Trong một cuộc diễn tập red team, mục tiêu là **đánh giá khả năng phòng thủ trước hành vi tấn công giả định**: hệ thống nào có thể bị tiếp cận, kiểm soát nào phát hiện hoạt động bất thường, đội phòng thủ phản ứng ra sao và còn những đường rủi ro nào cần khắc phục. Một kết quả diễn tập thành công không đòi hỏi phải lấy được dữ liệu khách hàng thật, làm gián đoạn ứng dụng hoặc chứng minh khả năng phá hoại bằng cách gây thiệt hại thực tế.

**Dữ liệu sản xuất (production data)** là dữ liệu đang phục vụ hoạt động thực của tổ chức, gồm thông tin khách hàng, nhân viên, giao dịch, nhật ký vận hành, thông tin xác thực, khóa mã hóa, bí mật ứng dụng, cơ sở dữ liệu, tệp lưu trữ, ảnh chụp hệ thống và bản sao lưu. Một số dữ liệu tưởng là “phụ” như tên bảng, schema, danh sách đối tượng lưu trữ, hostname, địa chỉ email hay session ID vẫn có thể nhạy cảm khi kết hợp với các nguồn khác.

Một bài diễn tập thiếu giới hạn có thể gây hậu quả ngay cả khi người thực hiện có thiện chí:

- Một phép kiểm chứng quyền đọc vô tình tải hàng nghìn bản ghi cá nhân thay vì chỉ kiểm tra quyền truy cập.
- Packet capture hoặc công cụ proxy lưu nội dung HTTPS đã giải mã, session token và dữ liệu biểu mẫu của khách hàng.
- Ảnh chụp màn hình chứa mật khẩu, khóa API hoặc thông tin người dùng; sau đó bị đưa vào báo cáo chia sẻ rộng.
- Việc mô phỏng đánh cắp dữ liệu dùng kênh Internet không kiểm soát và đưa dữ liệu thật ra khỏi môi trường doanh nghiệp.
- Một tài khoản thử nghiệm có quyền quá rộng thực hiện thao tác ghi, xóa, mã hóa hoặc tạo bản sao chứa dữ liệu sản xuất.
- Nhật ký, bản dump hoặc tập tin tạm của đội diễn tập tồn tại quá thời hạn, tạo thêm điểm có thể bị xâm phạm.

Bài này thuộc chương **Red team và mô phỏng tấn công mạng** của module **SECURITY_NETWORK_SECURITY**. Các lớp phòng vệ phân đoạn mạng, firewall, VPN, IDS/IPS, bảo vệ DNS, Wi-Fi, cloud và xác thực kết nối cung cấp cả phạm vi tiếp cận lẫn khả năng quan sát. Mục tiêu của bài là kết hợp hoạt động đánh giá an ninh với **đảm bảo tính bí mật, toàn vẹn và sẵn sàng của hệ thống sản xuất**, ngay cả khi phải thử nghiệm các kịch bản xâm nhập gần với thực tế.

### Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt bằng chứng đủ để chứng minh rủi ro với dữ liệu thật không cần thu thập.
2. Thiết lập **Rules of Engagement (ROE)** xác định rõ phạm vi dữ liệu, thao tác được phép, giới hạn và cơ chế dừng khẩn cấp.
3. Thiết kế bộ dữ liệu giả lập, tài khoản thử nghiệm và canary/honeytoken để kiểm chứng đường tấn công mà không làm lộ tài sản thật.
4. Áp dụng nguyên tắc ít quyền, ít dữ liệu, thời gian truy cập ngắn, kiểm soát truyền dữ liệu và bảo vệ bằng chứng.
5. Xử lý tình huống vô tình nhìn thấy dữ liệu nhạy cảm hoặc phát hiện nguy cơ ảnh hưởng tính toàn vẹn/sẵn sàng.
6. Lập báo cáo, bàn giao, dọn dẹp và xác minh sau diễn tập với bằng chứng có thể kiểm toán.

## 2. Sáu nguyên tắc phải luôn đúng

Trong một bài diễn tập có khả năng chạm tới sản xuất, cần định nghĩa các **bất biến bảo vệ dữ liệu** ngay từ trước khi triển khai.

| Bất biến | Cách hiểu | Cách xác minh |
|---|---|---|
| **Không sao chép dữ liệu thật khi không được phê duyệt rõ ràng** | Chứng minh quyền truy cập bằng dữ liệu giả, metadata hoặc kết quả được kiểm soát | Log truy vấn/export, xác nhận dung lượng và loại dữ liệu được thu |
| **Không thay đổi dữ liệu nghiệp vụ sản xuất** | Không tạo, sửa, xóa giao dịch/khách hàng/đơn hàng thật để chứng minh quyền | Audit trail thay đổi, cơ sở dữ liệu, checksum theo phạm vi thích hợp |
| **Không chuyển dữ liệu thật ra kênh không được duyệt** | Chỉ dùng canary/synthetic payload và đích nhận kiểm soát để mô phỏng exfiltration | Egress firewall, proxy/DLP, log receiver, định danh payload thử |
| **Không lưu bí mật lâu hơn cần thiết** | Token, cookie, khóa, dump, PCAP, screenshot được hạn chế hoặc không thu | Kiểm kê bằng chứng, phân quyền và thời hạn lưu |
| **Không vượt phạm vi hay thời gian được phép** | Tài sản, danh tính, vùng mạng, công cụ, cửa sổ và giới hạn tải đúng ROE | Scope inventory, lịch hoạt động, nhật ký phê duyệt |
| **Có thể dừng, cô lập và khôi phục** | Mỗi hoạt động có owner, điểm dừng, liên hệ khẩn cấp và phương án rollback | Dry run, kiểm tra liên lạc, backup/restore plan và xác nhận cleanup |

**Không được suy ra** “đã có quyền thực hiện red team” đồng nghĩa được phép thu thập tùy ý dữ liệu khách hàng hay trích xuất cơ sở dữ liệu. Quyền thử nghiệm hệ thống và quyền sử dụng dữ liệu là **hai quyết định riêng**, thường do các chủ sở hữu khác nhau phê duyệt.

## 3. Phân loại và kiểm kê dữ liệu trước khi bắt đầu

### 3.1. Dữ liệu nhạy cảm không chỉ là bảng khách hàng

| Nhóm dữ liệu | Ví dụ | Rủi ro trong diễn tập | Cách thay thế ưu tiên |
|---|---|---|---|
| **Thông tin định danh cá nhân** | Tên, số điện thoại, địa chỉ, hồ sơ nhân sự | Vi phạm quyền riêng tư, lộ thông tin, trách nhiệm xử lý | Hồ sơ tổng hợp giả, dữ liệu synthetic không truy ngược người thật |
| **Dữ liệu tài chính/giao dịch** | Đơn hàng, thanh toán, bảng lương | Sai lệch báo cáo hoặc rò rỉ dữ liệu tài chính | Bộ bản ghi test tách biệt có đánh dấu |
| **Tài khoản và bí mật** | API key, mật khẩu, private key, session cookie, JWT | Chiếm quyền ngoài dự kiến, tăng phạm vi ảnh hưởng | Credential thử nghiệm ít quyền, canary token vô hiệu với hệ thống thật |
| **Dữ liệu ứng dụng và sản phẩm** | Source code độc quyền, thông số cấu hình, công thức, thiết kế | Mất bí mật kinh doanh hoặc hỗ trợ kẻ tấn công khác | Metadata được phê duyệt, đoạn trích đã loại bỏ bí mật |
| **Thông tin hạ tầng** | Sơ đồ mạng, hostname, IP, rule firewall, IAM policy | Hỗ trợ vượt phân đoạn hoặc tiếp cận management plane | Mô hình hóa vùng mạng, ID tài sản được giả danh |
| **Log và packet capture** | HTTP header, DNS query, payload, auth event, trace | Có PII, secret, thông tin liên quan người dùng | Lọc theo trường, phân tích header/flow, khử định danh trước khi chia sẻ |
| **Snapshot/backup/DB dump** | Bản sao đầy đủ ổ đĩa, database export | Tập trung dữ liệu nhạy cảm, tăng hậu quả khi thất thoát | Snapshot của môi trường test hoặc kết quả giả lập |
| **Bằng chứng ảnh và video** | Ảnh màn hình console, dashboard, session recording | Ghi lại secret, dữ liệu khách hàng và thông tin ngoài phạm vi | Ảnh chụp có che dữ liệu, đoạn chứng cứ mô tả được kiểm soát |

**Mã hóa không làm dữ liệu hết nhạy cảm.** Bản mã, tệp backup đã mã hóa hoặc packet capture có TLS vẫn phải được phân loại và bảo vệ; metadata cũng có thể tiết lộ các quan hệ nhạy cảm.

### 3.2. Tạo data map tối thiểu

Trước diễn tập, thống nhất với chủ hệ thống về:

- **Hệ thống nguồn:** database, object storage, file share, SIEM, API, thiết bị mạng, log và endpoint có thể chứa dữ liệu thật.
- **Loại dữ liệu:** có PII, dữ liệu nhạy cảm khác, credential, log và tài liệu nội bộ hay không.
- **Đường dữ liệu:** nơi dữ liệu được xử lý, sao chép, lưu dự phòng, đồng bộ ra cloud hoặc đi qua mạng.
- **Độ nhạy và quyền:** người có quyền truy cập, thông tin nào hoàn toàn không được xem, nơi nào chỉ được quan sát metadata.
- **Giới hạn chứng cứ:** có được lấy ảnh chụp, tên đối tượng, số lượng bản ghi, hash, vài giá trị tổng hợp hoặc chỉ chấp nhận xác nhận bằng SOC?
- **Thời gian và nơi lưu:** kho chứng cứ được phê duyệt, retention, người chịu trách nhiệm xóa sau diễn tập.

Ví dụ bản đồ dữ liệu (giả định):

| Thành phần | Vai trò | Dữ liệu có thể gặp | Quy tắc diễn tập |
|---|---|---|---|
| Web API production | Tiếp nhận request người dùng | Session token, PII, giao dịch | Chỉ dùng tài khoản test và request synthetic |
| Application database | Lưu bản ghi hoạt động | Dữ liệu khách hàng/giao dịch | Không đọc hàng thật, không export; dùng bảng fixture hoặc phép thử được chứng kiến |
| SIEM | Thu log bảo mật | IP, username, header, payload tùy nguồn | Chỉ truy cập log đúng scope; trích bằng chứng đã che dữ liệu |
| Cloud object storage | Chứa tệp và backup | Bản sao tài liệu/dữ liệu thật | Chỉ kiểm tra cấu hình và đối tượng canary được cấp |
| VPN/IdP | Cấp phiên và danh tính | Token, thông tin định danh | Tài khoản thử nghiệm riêng, không mượn tài khoản nhân viên |
| DNS/Proxy | Phân giải và định tuyến egress | Query, URL, metadata truy cập | Chỉ thu thông tin phục vụ detection, giới hạn log retention |

## 4. Rules of Engagement: điều kiện để chạm tới hệ thống sản xuất

**Rules of Engagement (ROE)** phải trả lời được **ai** cho phép, **cái gì** được thử, **ở đâu**, **khi nào**, **bằng kỹ thuật nào**, **được quan sát loại dữ liệu gì** và **khi nào phải dừng**.

### 4.1. Trường bắt buộc trong phạm vi

- Danh sách tài sản rõ ràng: domain, IP/CIDR, ứng dụng, API, tenant/cloud account, vùng mạng, tài khoản và tổ chức sở hữu.
- Địa chỉ/vùng **không thuộc phạm vi**: hệ thống đối tác, khách hàng, môi trường chung, thiết bị OT/IoT nhạy cảm, hệ thống thanh toán, backup hoặc identity lõi nếu không được phê duyệt.
- Kỹ thuật/tác vụ được chấp thuận: discovery, cấu hình sai, thử phân đoạn, phiên đăng nhập kiểm soát, giả lập exfiltration với dữ liệu giả.
- Kỹ thuật/tác vụ bị cấm hoặc cần phê duyệt riêng: truy vấn hàng loạt bảng sản xuất, thay đổi dữ liệu thật, khai thác làm mất dịch vụ, chạy payload tự lan, dùng credential người thật, xóa log, triển khai persistence, ghi/đọc backup thật.
- Thời gian, tốc độ truy vấn, số kết nối, giới hạn kích thước request và mức độ đồng thời phù hợp SLA.
- Đầu mối phê duyệt, người giám sát trực, SOC/NOC liên quan, hotline, cơ chế **stop signal / kill switch**.
- Danh sách artifact được phép thu và đích lưu/nhận được duyệt; quy trình xử lý sự cố ngoài dự kiến.
- Cách chứng minh hoàn thành, điều kiện báo cáo và tiêu chuẩn dọn dẹp.

Khi phát hiện hệ thống ngoài danh sách nhưng có quan hệ từ kiến trúc sản xuất, nhóm diễn tập **không tự mở rộng scope**. Chuyển phát hiện cho người phê duyệt và chỉ tiếp tục sau khi cập nhật ROE.

### 4.2. Ví dụ ROE dưới dạng cấu hình tài liệu

~~~yaml
# Ví dụ mô tả nguyên tắc, KHÔNG phải file cấu hình chạy trực tiếp.
exercise_id: "RT-PROD-DATA-010"
environment: "production_with_synthetic_fixtures"
approved_assets:
  - "staging-like API endpoint explicitly assigned in production"
  - "dedicated test account"
approved_data:
  - "synthetic_customer_records tagged RT-010"
  - "canary_object with non-sensitive marker"
prohibited:
  - "bulk retrieval of real customer records"
  - "modifying or deleting real business data"
  - "copying real credentials, tokens or secrets"
  - "moving production records to external destinations"
  - "running disruptive payloads"
egress_destination: "approved internal test receiver only"
evidence:
  allowed: ["metadata", "sanitized screenshot", "test marker ID", "SOC alert reference"]
  forbidden: ["raw production dumps", "plaintext secrets", "unredacted PCAP payload"]
stop_conditions:
  - "unexpected access to real sensitive data"
  - "impact on production integrity or availability"
  - "out-of-scope asset reached"
  - "unexpected data egress"
contacts:
  exercise_lead: "defined_in_runbook"
  business_owner: "defined_in_runbook"
  security_incident_lead: "defined_in_runbook"
cleanup:
  retention: "defined by approved data handling policy"
  verification_owner: "defined_in_runbook"
~~~

Đây là mẫu để diễn đạt giới hạn. Trong thực tế tên tài sản, mức truy cập, các trường hợp ngoại lệ và chủ sở hữu phải được ghi trong tài liệu phê duyệt chính thức.

### 4.3. Cơ chế phê duyệt hai lớp

Có thể tách:

1. **Phê duyệt bài diễn tập:** được phép thực hiện hoạt động trên tài sản mục tiêu, trong thời gian và phương pháp xác định.
2. **Phê duyệt xử lý dữ liệu:** được phép truy cập nhóm dữ liệu nào, cách che/ghi nhận, thời gian lưu giữ và nơi sử dụng.

Nếu có một phép thử thật sự cần nhìn một phần dữ liệu sản xuất, phải có **ủy quyền cụ thể bằng văn bản**, nguyên tắc tối thiểu hóa, người giám sát và phương án bảo vệ phù hợp chính sách. Mặc định nên chọn phương pháp chứng minh ít tiếp xúc dữ liệu hơn.

## 5. Dùng dữ liệu tổng hợp và canary thay cho dữ liệu thật

### 5.1. Synthetic data và fixture

**Synthetic data** là dữ liệu được tạo để có cấu trúc, kích thước và quan hệ tương tự dữ liệu nghiệp vụ nhưng không đại diện người hoặc giao dịch thật. Ví dụ ứng dụng thương mại điện tử có thể tạo:

- Khách hàng giả với email thuộc miền dành cho tài liệu hoặc miền test do tổ chức kiểm soát.
- Đơn hàng và giá trị giao dịch giả có ID và trạng thái được gắn nhãn `RT-010`.
- Tệp PDF giả chứa chuỗi đánh dấu kiểm thử, không có thông tin khách hàng thật.
- Account test chỉ có quyền với một tập dữ liệu hoặc bucket thử nghiệm.
- Token thử nghiệm không có hiệu lực trên production thật hoặc có quyền chỉ đọc tài sản canary.

**Không lấy dữ liệu thật rồi đổi vài ký tự mà mặc định gọi là synthetic.** Dữ liệu bị “mask một phần” vẫn có thể tái định danh hoặc giữ nội dung nhạy cảm. Việc tạo dữ liệu giả từ thống kê thật cũng cần đánh giá rủi ro nếu tập quá nhỏ hoặc có trường hiếm.

### 5.2. Canary / honeytoken

**Canary** là một đối tượng kiểm thử được thiết kế để khi bị truy cập hoặc di chuyển sẽ để lại dấu vết: tệp giả, khóa giả vô hiệu, bản ghi trong hệ thống test, URL nội bộ kiểm soát hoặc marker duy nhất.

Ví dụ đối tượng tài liệu:

~~~json
{
  "record_type": "synthetic_exercise_marker",
  "exercise": "RT-010",
  "marker_id": "CANARY-RT010-42",
  "contains_real_customer_data": false,
  "purpose": "validate access-control and detection",
  "owner": "security-test-team",
  "expires_at": "defined_in_exercise_plan"
}
~~~

Mỗi canary cần có **owner, thời hạn, nơi đặt, quyền, dự kiến cảnh báo và bước dọn dẹp**. Đặt canary ở nơi nhóm diễn tập được phép tiếp cận; không được biến canary thành credential thật hoặc truy cập ra hệ thống không được duyệt.

### 5.3. Chứng minh quyền truy cập theo cấp độ tăng dần

| Cấp chứng minh | Bằng chứng thu được | Tác động lên dữ liệu |
|---|---|---|
| **Cấu hình/phân quyền** | ACL/IAM policy, mô hình truy cập, quyền của principal thử nghiệm | Không cần đọc bản ghi |
| **Metadata** | Tên tài nguyên đã được cho phép, trạng thái kết nối, phản hồi phân quyền | Hạn chế tối đa payload |
| **Đối tượng canary** | Đọc đúng marker synthetic hoặc thông báo truy cập fixture | Không đọc hàng thật |
| **Quan sát từ phía defender** | SOC ghi nhận request, ID tài khoản, policy decision, flow | Team red không phải giữ dữ liệu thực |
| **Đánh giá quyền có điều kiện** | Chủ hệ thống xác thực phạm vi quyền dựa trên log hoặc cấu hình | Không cần trích xuất dữ liệu thật |

Khi cấp bằng chứng thấp đã đủ kết luận “nguy cơ truy cập trái phép”, **không cần nâng lên dump, export hay exfiltration thật**. Một lỗi phân quyền nghiêm trọng có thể được ghi nhận chính xác ngay cả khi đội diễn tập chủ động không đọc dữ liệu.

## 6. Kiểm soát truy cập vào sản xuất trong quá trình diễn tập

### 6.1. Danh tính tách biệt và ít quyền

Sử dụng **tài khoản chuyên dụng cho diễn tập**, với quyền tách khỏi tài khoản cá nhân/quản trị thực, có MFA hoặc xác thực mạnh theo chính sách, định danh rõ ràng trong audit log và thời hạn hết hiệu lực.

Các nguyên tắc:

- Chỉ cấp quyền đến **tài sản trong scope** và **fixture cần thiết**; không dùng tài khoản quản trị toàn cục nếu kiểm thử không đòi hỏi.
- Quyền truy cập dữ liệu thật được hạn chế ở chính nơi chứa dữ liệu bằng RBAC/ABAC, row-level security, object policy hoặc policy API phù hợp.
- Dùng credential ngắn hạn, có kiểm soát thu hồi và không tái sử dụng sau diễn tập.
- Nếu phải thử cơ chế leo thang quyền, ưu tiên **môi trường nhân bản không chứa dữ liệu thật** hoặc đánh giá bằng metadata để chứng minh khả năng vượt quyền.
- Ghi lại danh tính, nguồn mạng, thời gian phiên và mapping tới người phụ trách để SOC phân biệt hoạt động được phê duyệt và sự cố thật.

**Không tắt các kiểm soát của production chỉ để “dễ diễn tập”**: MFA, DLP, firewall, logging, EDR, xác minh chứng chỉ hoặc encryption-at-rest cần tiếp tục hoạt động trừ khi thay đổi được phê duyệt rõ và có phương án hoàn nguyên.

### 6.2. Kiểm soát theo vùng mạng và đường truyền

Cấu hình hoặc kiểm tra các lớp bảo vệ liên quan:

| Lớp | Yêu cầu trong diễn tập |
|---|---|
| **Network segmentation / firewall** | Chỉ cho phép luồng test đúng từ nguồn được cấp phép đến tài sản trong scope; deny các vùng ngoài scope |
| **VPN / bastion** | Tài khoản và nguồn truy cập được ghi log; không chia sẻ phiên quản trị; giới hạn thời gian và quyền |
| **IDS/IPS / WAF** | Tiếp tục thực thi; thống nhất nhãn/timestamp cho hoạt động mô phỏng để phân tích phát hiện |
| **DNS / proxy egress** | Chỉ cho truy vấn/đích kiểm thử theo kế hoạch; ngăn dữ liệu đi ra kênh ngoài kiểm soát |
| **Wi-Fi / NAC** | Test VLAN/SSID riêng, không tự chuyển thiết bị thử sang VLAN chứa dữ liệu nhạy cảm |
| **Cloud / IAM / security group** | Dùng role riêng, scope resource theo tag, cảnh báo thay đổi quyền hoặc object storage |
| **Logging / SIEM** | Bật telemetry cho phiên test và các thay đổi liên quan; hạn chế log chứa payload nhạy cảm |

Đội red team có thể cần kiểm tra khả năng phát hiện của SOC, nhưng hoạt động **deconfliction** không đồng nghĩa cho phép bỏ qua bảo vệ dữ liệu. Chỉ rõ điều kiện nào được phép không tiết lộ trước cho SOC, và **kênh liên lạc khẩn cấp** vẫn phải luôn hoạt động.

### 6.3. Giảm nguy cơ làm gián đoạn hệ thống

Mặc dù trọng tâm là dữ liệu, mất tính sẵn sàng cũng có thể dẫn tới mất dữ liệu hoặc ảnh hưởng quy trình nghiệp vụ.

- Đặt ngưỡng lưu lượng, số request đồng thời, thời gian chờ, kích thước response và tốc độ truy vấn.
- Chỉ thử thao tác **read-only** khi đã xác minh không có side effect (một HTTP GET hoặc SQL SELECT vẫn có thể kích hoạt xử lý phức tạp hoặc truy vấn tốn tài nguyên).
- Không chạy thử mã hóa dữ liệu, xóa dữ liệu, tắt backup, làm đầy ổ đĩa, chạy lệnh phá hoại hoặc thay đổi IAM diện rộng trên production.
- Đảm bảo có backup và phương án khôi phục **đã được kiểm chứng bởi chủ hệ thống**; không tự tạo snapshot production rồi tải về máy đội diễn tập.
- Có cửa sổ test thích hợp, theo dõi CPU/memory/DB connections/latency và người trực có quyền dừng.

## 7. Mô phỏng rò rỉ dữ liệu mà không chuyển dữ liệu thật

Mục tiêu của một bài **exfiltration simulation** là kiểm tra: liệu hệ thống có chặn hoặc phát hiện ý định đưa thông tin ra ngoài, hệ thống ghi nhận những chỉ báo nào và SOC phản ứng ra sao.

### 7.1. Các cách kiểm chứng an toàn hơn

1. **Marker-only:** gửi một chuỗi canary nhỏ, không chứa dữ liệu thật, tới máy nhận nằm trong mạng và tài khoản do tổ chức kiểm soát.
2. **Telemetry-only:** tạo event mô phỏng với ID duy nhất để kiểm thử rule DLP/IDS/SIEM mà không thực hiện truyền dữ liệu qua biên sản xuất.
3. **Tabletop:** đưa log/flow mẫu cho SOC phân loại, sử dụng khi không được phép gửi traffic mô phỏng.
4. **Dry-run / blocked egress:** kiểm thử rằng chính sách ngăn request tới đích giả định và thu log tại điểm từ chối.
5. **Reproduction trong lab:** sao chép cấu hình và logic kiểm soát vào môi trường không có dữ liệu thật, kiểm chứng hành vi mà không tạo lưu lượng production nguy hiểm.

**Không dùng mẫu dữ liệu khách hàng thật, dump DB, bí mật hoặc credential thực làm payload.** Không cần chứng minh có thể đánh cắp 10 GB để kết luận một tài khoản có quyền đọc ngoài phạm vi; test nên tìm lượng bằng chứng **nhỏ nhất đủ chứng minh**.

### 7.2. Cấu trúc một phép thử mô phỏng

~~~mermaid
flowchart TD
  A["Xác định giả thuyết về khả năng rò rỉ"] --> B["Chọn canary hoặc log mô phỏng, không có dữ liệu thật"]
  B --> C["Phê duyệt nguồn, đích nhận, giao thức và thời gian"]
  C --> D["Kiểm tra firewall/DLP/IDS và giới hạn tốc độ"]
  D --> E["Thực hiện một probe có ID duy nhất"]
  E --> F["Đối chiếu log mạng, DLP, SOC và test receiver"]
  F --> G{"Có dữ liệu ngoài phạm vi hay tác động bất thường?"}
  G -->|Có| H["Dừng ngay, xử lý sự cố và bảo toàn bằng chứng tối thiểu"]
  G -->|Không| I["Ghi kết quả, xóa canary/phiên và xác minh cleanup"]
~~~

Một phép thử chỉ thành công khi **test receiver được phép nhận đúng canary**, số lần gửi/byte đúng như phê duyệt, không có tài liệu sản xuất được truyền và telemetry thu được đủ để đánh giá cơ chế phòng thủ. Nếu DLP chặn, đó có thể là **kết quả bảo mật mong đợi**, không phải lý do tìm cách vòng tránh ngoài ROE.

### 7.3. Tránh hiểu nhầm về chỉ số “bytes transferred”

Flow log chỉ biết số byte giữa hai điểm, thường không thể chứng minh đó là dữ liệu nhạy cảm hay nội dung tập tin nào. Một HTTP status thành công cũng không tự chứng minh đã lấy được bản ghi. Cần kết hợp **ID canary**, log ứng dụng, quyết định DLP/proxy và log máy nhận; không suy diễn quá phạm vi quan sát.

## 8. Khi phát hiện dữ liệu nhạy cảm ngoài dự kiến: dừng ở đâu?

Giả sử khi kiểm chứng một lỗi phân quyền, công cụ hiển thị một bản ghi khách hàng thật, token production hoặc một danh sách tệp backup không thuộc scope. Cách xử lý phải ưu tiên **ngăn tạo thêm bản sao và hạn chế lan truyền**.

### Quy trình tối thiểu

1. **Dừng thao tác phát sinh dữ liệu mới:** không cuộn tiếp, không export, không mở thêm tệp, không truy vấn tiếp để “xác nhận” khi chưa được phép.
2. **Không chia sẻ nội dung vào chat/ticket rộng:** chỉ ghi mô tả ít dữ liệu nhất như thời điểm, tài sản, loại dữ liệu, tài khoản, phản hồi tổng quát; không dán mật khẩu, token hoặc PII.
3. **Bảo toàn bằng chứng cần thiết một cách có kiểm soát:** ưu tiên request ID, response code, resource ID đã che, policy decision, log máy chủ hoặc xác nhận của chủ dữ liệu. Nếu công cụ tự ghi payload, bảo vệ file và hạn chế quyền truy cập.
4. **Thông báo đầu mối theo ROE:** exercise lead và chủ dữ liệu/security lead; nếu nghi có sự cố thật, kích hoạt quy trình ứng phó thay vì tiếp tục diễn tập.
5. **Đánh giá đường rò rỉ thứ cấp:** clipboard, terminal scrollback, shell history, proxy capture, screenshot, cloud sync, log aggregator hoặc công cụ tự động upload.
6. **Quyết định tiếp tục hay dừng:** chỉ tiếp tục sau khi chủ sở hữu đánh giá và xác nhận hướng xử lý; nếu cần, đổi sang canary, lab hoặc phép thử không chạm dữ liệu.

### Khi vô tình gặp bí mật xác thực

Bí mật thật (mật khẩu, private key, API key, session token) cần được coi là **nhạy cảm cao**, kể cả khi chưa dùng. Không sao chép vào báo cáo. Đề xuất chủ hệ thống đánh giá thu hồi, xoay vòng hoặc vô hiệu hóa theo phạm vi thích hợp, ghi nhận thời điểm xuất hiện và nơi có thể đã được lưu. Nếu có dấu hiệu credential đã bị người khác sử dụng, chuyển thành điều tra sự cố theo quy trình.

### Khi có dấu hiệu dữ liệu thật đã rời hệ thống

Dừng phép thử và kích hoạt quy trình phân loại sự cố: xác định **nguồn, đích, thời gian, khối lượng, loại dữ liệu, người có quyền truy cập bản sao** và phạm vi ảnh hưởng. Không tự tuyên bố đó là sự cố bắt buộc thông báo hay tự xóa dấu vết; người phụ trách dữ liệu và pháp lý/quyền riêng tư của tổ chức quyết định các nghĩa vụ tương ứng.

## 9. Bảo vệ bằng chứng: thu ít, mã hóa, giới hạn chia sẻ

Bằng chứng chất lượng cao không nhất thiết phải chứa dữ liệu thô. Ví dụ để chứng minh một chính sách cho phép sai, có thể lưu:

- ID của tài khoản thử nghiệm, nhóm quyền và tài nguyên canary.
- Policy/rule ID, request ID, response status và timestamp.
- Log IAM/firewall/SIEM đã loại bỏ trường nhạy cảm.
- Kết quả kiểm tra truy cập tới marker giả.
- Bản chụp màn hình **đã che** giá trị nhạy cảm với chú thích rõ ràng.

### 9.1. Data handling pipeline

~~~mermaid
flowchart LR
  A["Phát hiện trong scope"] --> B["Chọn bằng chứng tối thiểu"]
  B --> C["Loại bỏ/che token, PII, payload không cần"]
  C --> D["Mã hóa tại nơi lưu, gắn owner và quyền"]
  D --> E["Kiểm tra nội dung trước khi chia sẻ"]
  E --> F["Báo cáo bằng tham chiếu và dữ kiện đã che"]
  F --> G["Hết hạn lưu -> xác minh xóa theo quy định"]
~~~

Các bước kiểm soát cần phù hợp từng loại bằng chứng:

| Loại | Thu thập được khuyến nghị | Điều cần tránh |
|---|---|---|
| **Ảnh chụp UI** | Chỉ vùng cần minh họa, che PII/secret, giữ bản gốc giới hạn nếu chính sách yêu cầu | Chụp cả màn hình có khách hàng, browser profile, token và màn hình ngoài scope |
| **HTTP request/response** | Method, path đã che, status, request ID, header an toàn | Authorization header, Cookie, body chứa dữ liệu thật |
| **SQL/database evidence** | Schema/quyền được duyệt, tài khoản test, thao tác fixture, row count đã phê duyệt | Export bảng thật hoặc chụp hàng dữ liệu cá nhân |
| **Cloud IAM/object storage** | Resource policy, role, bucket test/canary, audit event | Tải object thật, snapshot production, secret manager values |
| **PCAP** | Flow metadata, capture filter theo scope, các trường tối thiểu | Full payload từ nhiều người dùng, giải mã TLS hàng loạt không cần thiết |
| **Endpoint/log** | Process/network metadata, audit event ID, timestamp | Memory dump hoặc thu toàn bộ thư mục người dùng nếu không được duyệt |

**Che dữ liệu trước khi chia sẻ** phải áp dụng lên bản báo cáo xuất ra, file đính kèm và thumbnail. Nếu có bản gốc chưa che vì yêu cầu điều tra, lưu trong kho hạn chế và có người chịu trách nhiệm, không nhân bản tự do.

### 9.2. Tính toàn vẹn và chuỗi bàn giao

Với mỗi artifact cần giữ:

- Người thu thập, thời điểm, mục đích, tài sản và test case liên quan.
- Đường dẫn hoặc mã định danh trong kho chứng cứ được phê duyệt.
- Dấu hash của artifact nếu quy trình yêu cầu, định dạng, phiên bản công cụ và trạng thái đã che hay chưa.
- Mọi lần truy cập, chuyển giao, xuất báo cáo và thay đổi phạm vi chia sẻ.
- Thời hạn giữ, quyết định xóa và người xác nhận xóa.

Hash giúp phát hiện một file bị thay đổi nhưng **không tự bảo đảm file được thu hợp pháp, đầy đủ hay sạch dữ liệu nhạy cảm**. Phải kết hợp provenance, audit trail và phân quyền.

Ví dụ manifest bằng chứng:

~~~yaml
exercise_id: "RT-PROD-DATA-010"
artifact_id: "EVID-010-03"
source: "application security audit event"
collected_at: "2026-11-28T14:35:00+07:00"
collector: "authorized_exercise_operator"
description: "Attempt to access synthetic record was denied"
contains_real_personal_data: false
contains_credentials: false
sanitized: true
storage_reference: "approved-evidence-vault/item-03"
classification: "internal-restricted"
access_owner: "security-assessment-lead"
retention_and_deletion: "per-approved-policy"
~~~

## 10. Giảm tiếp xúc dữ liệu khi xử lý PCAP, log và ảnh chụp

### 10.1. Packet capture trong mạng sản xuất

PCAP thô có thể chứa **nội dung HTTP không mã hóa, metadata TLS, DNS, thông tin xác thực và nhiều luồng ngoài phạm vi**. Khi điều tra tính hiệu quả IDS/IPS hay phân đoạn trong bài diễn tập:

1. Chọn **điểm capture, cửa sổ thời gian, IP/port và nguồn test** theo ROE; tránh capture cả VLAN với người dùng thật nếu không cần.
2. Ưu tiên **NetFlow/IPFIX, firewall allow/deny, Zeek metadata, IDS alert** và log ứng dụng khi các nguồn đó đủ kiểm chứng.
3. Nếu phải dùng PCAP, dùng filter và retention tối thiểu; xác minh công cụ không tự động đồng bộ lên cloud cá nhân.
4. Không tự giải mã TLS, trích xuất cookie, session token hoặc tải toàn bộ payload nếu không thuộc phép thử được duyệt.
5. Che các trường nhạy cảm khi làm báo cáo và ghi rõ giới hạn quan sát do encryption, sampling hoặc điểm đặt sensor.

Một lệnh phân tích offline không cần lấy nội dung payload:

~~~bash
# Phân tích offline file capture đã được thu thập hợp lệ.
# Chỉ lấy metadata tối thiểu cho kết nối liên quan; không trích payload.
tshark -r approved-exercise.pcapng \
  -Y "ip.addr == 192.0.2.10 && tcp.port == 443" \
  -T fields \
  -e frame.time_utc -e ip.src -e ip.dst \
  -e tcp.srcport -e tcp.dstport -e tcp.len
~~~

Địa chỉ `192.0.2.10` thuộc dải tài liệu; thay bằng IP fixture được phê duyệt. Bản thân PCAP vẫn có thể chứa payload nhạy cảm, nên chỉ chạy lệnh này trên nguồn chứng cứ được phép; xuất trường tối thiểu **không tự làm sạch file gốc**.

### 10.2. Log thường chứa dữ liệu vượt nhu cầu

Nhiều access log ghi URL query string có token, user ID hoặc nội dung tìm kiếm. Debug log có thể ghi body và authorization header. Cần giảm khả năng log thu dữ liệu thật bằng:

- Sử dụng account và request fixture thay vì người thật.
- Chọn mức log phù hợp với test, tránh bật debug payload rộng cho toàn production.
- Thiết lập masking/redaction ở collector khi có thể.
- Hạn chế truy cập raw logs; điều tra bằng ID event và chỉ mở bản gốc khi có phê duyệt.
- Kiểm tra log receiver, alert notification và dashboard có tự đưa trường nhạy cảm vào email/chat không.

**Một bản ghi đã được che có thể vẫn mang tính nhạy cảm** nếu giữ IP/người dùng/timestamp kết hợp có thể nhận diện. Áp dụng chính sách bảo vệ phù hợp.

## 11. Ngăn dữ liệu bị rò rỉ qua công cụ và kênh làm việc

Đội diễn tập có thể dùng laptop, terminal, proxy phân tích lưu lượng, SIEM, công cụ làm báo cáo, kho mã, ticket, clipboard và dịch vụ cộng tác. Đây cũng là các nơi dữ liệu có thể bị phát tán ngoài ý muốn.

### 11.1. Kiểm soát workstation và máy nhận

- Dùng thiết bị kiểm thử do tổ chức quản lý, full-disk encryption, cập nhật bảo mật và EDR theo chính sách.
- Hạn chế quyền lưu, mount, USB, clipboard sync và các công cụ tự upload dữ liệu vào kho cá nhân.
- Nếu dùng test receiver, triển khai trong vùng do tổ chức kiểm soát, có access log và chỉ nhận **marker synthetic**.
- Đặt quota cho số artifact, kích thước tệp và thời hạn giữ; kiểm soát outbound qua firewall/proxy.
- Không đưa secret/PII vào command line, shell history, biến môi trường hiển thị trong log hoặc issue tracker.

### 11.2. CI/CD và dịch vụ bên ngoài

Không tự gửi log, PCAP, memory dump, screenshot hoặc mẫu dữ liệu sản xuất cho công cụ SaaS, kho Git, trình phân tích online, hệ thống ticket của bên thứ ba hoặc mô hình AI bên ngoài nếu chưa có phê duyệt xử lý dữ liệu tương ứng. Dùng bản đã khử định danh hoặc mô phỏng khi chuẩn bị tài liệu, demo và đào tạo.

**Thực hành tốt:** báo cáo chứa **tham chiếu** tới một chứng cứ lưu trong kho có quyền kiểm soát; người xem chỉ được truy cập nội dung nếu được chủ dữ liệu cho phép.

## 12. Kênh phối hợp với blue team và cơ chế dừng khẩn cấp

Red team thường đánh giá cả khả năng phát hiện và ứng phó của SOC. Một số bài diễn tập là **blind exercise**, chỉ ít người biết trước. Nhưng bảo vệ dữ liệu cần một cơ chế an toàn có thể **vượt qua bí mật của bài diễn tập khi khẩn cấp**.

### 12.1. Các vai trò cần có

| Vai trò | Trách nhiệm |
|---|---|
| **Exercise sponsor / chủ phạm vi** | Phê duyệt mục tiêu, mức rủi ro và giới hạn hoạt động |
| **Chủ hệ thống/chủ dữ liệu** | Xác định tài sản/dữ liệu được phép tiếp xúc và phê duyệt ngoại lệ |
| **Red team lead** | Triển khai đúng ROE, duy trì kiểm kê hoạt động, dừng khi vượt ngưỡng |
| **Safety controller / white cell** | Giữ kênh liên lạc độc lập, giải quyết xung đột giữa bí mật diễn tập và an toàn sản xuất |
| **SOC/blue team** | Giám sát, phát hiện và xử lý theo kịch bản; tiếp nhận tín hiệu an toàn cần dừng |
| **NOC/SRE / IT operations** | Theo dõi hiệu năng, availability, dependency và phối hợp rollback |
| **Incident response / privacy/legal** | Đánh giá khi có sự cố thật, xử lý dữ liệu lộ và nghĩa vụ liên quan |

### 12.2. Điều kiện dừng (stop conditions)

Phải dừng ngay hoạt động tương ứng nếu xuất hiện:

- Dữ liệu sản xuất nhạy cảm bị xem/thu/đẩy ra ngoài ngoài phạm vi được cho phép.
- Khả năng ghi/xóa/sửa dữ liệu thật ngoài ROE, hoặc thấy tác động sai lệch nghiệp vụ.
- Dấu hiệu làm giảm availability (latency, lỗi, queue backlog, DB saturation) vượt ngưỡng phê duyệt.
- Phát hiện đã chạm tài sản ngoài scope hoặc một môi trường dùng chung của đối tác.
- Mất khả năng giám sát, mất kênh liên lạc an toàn, không còn chứng cứ để xác nhận dữ liệu test.
- Cảnh báo có thể là một cuộc tấn công thật trùng thời gian diễn tập và không thể phân biệt an toàn.
- Lộ credential thật, phát sinh luồng outbound ngoài kế hoạch hoặc công cụ vô tình lưu raw dump/PCAP nhạy cảm.

Nếu không chắc điều kiện đã vượt ngưỡng, **ưu tiên tạm dừng phần công việc liên quan** và chuyển thông tin cho safety controller. Dừng một test không mặc nhiên phải tắt mọi dịch vụ production; cách giảm thiểu phải theo thẩm quyền và runbook.

### 12.3. Quy trình ứng phó

~~~mermaid
flowchart TD
  A["Thực hiện test trong ROE"] --> B{"Phát hiện dữ liệu thật, tác động hoặc sai phạm scope?"}
  B -->|Không| C["Tiếp tục kiểm chứng bằng synthetic evidence"]
  C --> A
  B -->|Có hoặc chưa rõ| D["Dừng thao tác liên quan, không tạo thêm bản sao"]
  D --> E["Thông báo white cell / lead / chủ dữ liệu"]
  E --> F["Bảo toàn chứng cứ tối thiểu và kiểm tra mức ảnh hưởng"]
  F --> G{"Có dấu hiệu sự cố an ninh thực?"}
  G -->|Có| H["Kích hoạt incident response theo quy trình"]
  G -->|Không hoặc chưa xác định| I["Đánh giá scope và biện pháp khắc phục"]
  H --> J["Quyết định tiếp tục, thay thế bằng lab hoặc hủy test"]
  I --> J
  J --> K["Ghi quyết định, owner, thời gian, cleanup và xác minh"]
~~~

## 13. Dọn dẹp và xác minh sau bài diễn tập

**Cleanup là một bước bắt buộc của đánh giá an ninh**, không chỉ là xóa vài tập tin trên máy của red team.

### Những đối tượng cần kiểm kê

- Account thử nghiệm, role IAM, khóa/API token, session VPN, rule tạm thời và quyền được cấp trong ROE.
- Canary/honeytoken, bản ghi synthetic, đối tượng trong bucket, file fixture, inbox test.
- VM/container/tooling agent, reverse proxy/test receiver, dịch vụ debug, port forward, DNS record và tài nguyên cloud được tạo cho bài tập.
- Capture file, screenshot, terminal output, log export, báo cáo nháp, local cache, clipboard history trong phạm vi kiểm soát.
- Snapshot/test backup được tạo đặc biệt cho diễn tập; cơ chế backup định kỳ của production không bị thay đổi ngoài phê duyệt.
- Alert suppression/tuning ngoại lệ, temporary firewall rules hoặc bypass nếu đã được cấp phép.

### Cách hoàn tất có chứng cứ

1. **Ngừng mọi phiên và job thử nghiệm.** Kiểm tra không còn process, scheduler hay tác nhân tự chạy.
2. **Thu hồi quyền tạm:** revoke token/session, vô hiệu hóa tài khoản và trả cấu hình chính sách về trạng thái đã phê duyệt.
3. **Loại bỏ fixture/canary:** đối chiếu danh sách đã tạo, xóa ở môi trường được phép theo chính sách; tránh lệnh xóa hàng loạt với pattern có thể trúng dữ liệu thật.
4. **Dọn bằng chứng ở nơi không được phép lưu:** loại bỏ bản sao không cần và xác nhận nơi chứa dữ liệu còn lại đúng kho phê duyệt, có retention.
5. **Xác minh integrity và availability:** chủ hệ thống xác nhận dữ liệu nghiệp vụ, backup, dịch vụ và logging hoạt động bình thường; điều tra mọi sai lệch.
6. **Đóng quyền truy cập:** xác nhận firewall/ACL/IAM, rule tạm, DNS, object permission, monitoring exceptions trở về trạng thái mục tiêu.
7. **Lập biên bản:** tài sản đã kiểm tra, bằng chứng, người xác nhận, ngoại lệ đang mở, ngày dự kiến xử lý và hạn lưu artifact.

### Phân biệt xóa artifact và hủy chứng cứ sự cố

Nếu trong diễn tập xuất hiện một **sự cố an ninh thật**, không xóa các chứng cứ liên quan theo lịch cleanup thông thường. Đội ứng phó và chủ dữ liệu sẽ quyết định bảo toàn, quyền truy cập, thời hạn lưu và điều kiện tiêu hủy. Việc “dọn dẹp” để khôi phục môi trường **không được phá hủy bằng chứng cần thiết**.

## 14. Ví dụ thực tế

### Tình huống A — Phát hiện database user có quyền đọc quá rộng

**Bối cảnh:** một tài khoản dịch vụ có quyền truy vấn nhiều bảng sản xuất ngoài nhu cầu. Nhóm red team được phép đánh giá quyền nhưng không được đọc thông tin khách hàng.

**Cách kiểm chứng an toàn:**

1. Đối chiếu role, object privilege và quyền của account từ metadata/audit log.
2. Dùng một bảng fixture có marker giả để kiểm tra khả năng truy cập nếu chủ hệ thống đã chuẩn bị.
3. Nếu metadata đủ chứng minh nguy cơ, ghi nhận phát hiện mà **không truy vấn hàng thật**.
4. Chuyển khuyến nghị thu hẹp quyền, row-level access và logging cho chủ dữ liệu.

**Bằng chứng:** account test, bảng quyền đã che thông tin nhạy cảm, request ID, kết quả fixture. **Không cần:** SELECT trên toàn bộ bảng khách hàng hay DB export.

### Tình huống B — Cloud bucket lộ quyền liệt kê object

**Bối cảnh:** policy bucket cloud có thể cho phép principal thử nghiệm liệt kê các tên object ngoài mong đợi. Bucket cũng chứa tài liệu kinh doanh thật.

**Cách kiểm chứng:** xác minh policy bằng control-plane audit hoặc công cụ phân tích quyền, dùng prefix/bucket canary có thể kiểm soát. Nếu quyền liệt kê tên object thật được thể hiện rõ qua policy, không chạy lệnh tải nội dung object.

**Kết quả:** báo cáo quyền có thể dẫn đến lộ thông tin và khuyến nghị giới hạn principal/resource. Chỉ tải object synthetic đã được duyệt.

### Tình huống C — Mô phỏng exfiltration qua HTTPS

**Bối cảnh:** SOC muốn biết proxy/DLP có phát hiện transfer lớn từ máy chủ ứng dụng ra ngoài. ROE không cho phép chuyển dữ liệu khách hàng.

**Giải pháp:** tạo payload giả có marker riêng, chỉ gửi tới endpoint nội bộ hoặc kênh kiểm thử đã phê duyệt; giới hạn byte và tốc độ. Đối chiếu firewall, proxy, DLP, SIEM và receiver. Nếu chính sách yêu cầu chặn, kết quả chặn là một **PASS của biện pháp phòng thủ**.

**Không thực hiện:** upload backup, log chứa PII, token hoặc kết nối tới dịch vụ nhận bên ngoài chưa được phê duyệt.

### Tình huống D — Proxy tự lưu Authorization header

**Bối cảnh:** công cụ kiểm thử lưu toàn bộ request/response và vô tình có token production trong history.

**Phản ứng:** dừng capture, giới hạn quyền truy cập file lưu trữ, thông báo safety controller, đề nghị chủ tài khoản đánh giá revoke/rotation, xác định bản sao và telemetry đi kèm. Cấu hình filter/masking, dùng tài khoản fixture mới trước khi tiếp tục.

**Bài học:** bảo vệ dữ liệu phải áp dụng cho **công cụ kiểm thử**, không chỉ cho hệ thống mục tiêu.

### Tình huống E — Test tác động DB ngoài dự kiến

**Bối cảnh:** thao tác nhìn có vẻ đọc đơn thuần làm truy vấn database chậm, connection pool đầy và tăng lỗi ứng dụng.

**Phản ứng:** dừng test theo ngưỡng availability, thông báo NOC/SRE và chủ hệ thống, quan sát phục hồi, giữ query ID/timestamp/metrics mà không copy dữ liệu. Chuyển phần kiểm thử tiếp theo sang lab hoặc dùng đánh giá quyền/metadata.

**Bài học:** read-only chưa chắc không gây hại; hạn chế tài nguyên và theo dõi khả dụng là biện pháp bảo vệ dữ liệu sản xuất.

### Tình huống F — Tập ảnh chụp chứa dữ liệu nhân viên thật

**Bối cảnh:** screenshot của dashboard chứng minh một lỗi access control nhưng có tên và thông tin liên hệ nhân viên.

**Phản ứng:** không phát tán ảnh gốc trong kênh dự án; che/redact ở bản chia sẻ, kiểm soát bản gốc nếu cần điều tra, ghi rõ nội dung được sử dụng và loại bỏ bản không cần theo retention. Có thể dùng ảnh tái hiện từ môi trường fixture thay cho ảnh production.

**Bài học:** “bằng chứng” cũng là dữ liệu phải được quản lý bằng phân quyền và mục đích rõ ràng.

## 15. Đo lường và báo cáo kết quả bảo vệ dữ liệu

Bên cạnh số lượng kỹ thuật phát hiện, báo cáo cần cho thấy bài diễn tập đã **kiểm soát tác động lên production** thế nào.

| Chỉ số | Cách đo | Mục tiêu minh họa |
|---|---|---|
| Dữ liệu thật bị thu ngoài phê duyệt | Đối chiếu inventory, log và báo cáo sự cố | 0 sự kiện |
| Dữ liệu thật truyền đến đích ngoài scope | Egress/receiver audit, DLP, network flow | 0 sự kiện |
| Thao tác ghi/xóa ngoài scope | DB audit, API audit, cloud trail | 0 sự kiện |
| Tài sản ngoài scope được chạm tới | Inventory, network flow và alert | 0 sự kiện |
| Canary được nhận diện | Tỷ lệ các marker xuất hiện đúng trong telemetry | Theo mục tiêu detection của bài thử |
| Cảnh báo SOC đến nơi nhận | Alert latency, ticket/timeline | Theo SLO nội bộ |
| Tác động availability | Lỗi giao dịch, CPU/DB saturation, latency | Dưới ngưỡng đã duyệt |
| Artifact còn lưu ngoài kho được phép | Kiểm kê kết thúc và đối chiếu các bản sao | 0 bản sao không được duyệt |
| Quyền tạm còn tồn tại | IAM/network config diff sau cleanup | 0 quyền ngoài nhu cầu |
| Khả năng truy vết | Tỷ lệ test case có owner, thời gian, scope, evidence ref | Theo tiêu chuẩn kiểm toán được duyệt |

Không nên công bố “không có dữ liệu bị lộ” chỉ vì không thấy cảnh báo DLP. Phải đối chiếu với phạm vi quan sát, kiểm tra receiver, bản sao ở workstation và các kênh có thể thiếu telemetry. Báo cáo cần nêu rõ **độ bao phủ, điểm mù và phần chưa kiểm chứng**.

### Mẫu báo cáo một phát hiện

~~~yaml
finding_id: "RT-010-F01"
title: "Test principal has overly broad read permission"
environment: "production"
affected_asset: "business-api-role-example"
classification: "access-control-risk"
proof_method: "IAM metadata review and approved synthetic record"
real_data_accessed: false
real_data_exported: false
production_data_modified: false
evidence_refs:
  - "approved-vault/evidence-010-f01"
assumptions:
  - "Policy grants a broader resource scope than business requirement"
confidence: "high"
observed_limitations:
  - "No attempt to retrieve real customer records"
business_risk: "Potential unauthorized access to sensitive records"
recommendations:
  - "Reduce IAM resource scope"
  - "Add regression test for principal/resource mapping"
  - "Monitor denied and unusual access to sensitive resources"
cleanup_state: "test fixture and temporary role removed, owner verified"
~~~

Mức `confidence` được gắn với **điều đã quan sát**, không thổi phồng thành chứng minh dữ liệu đã bị đánh cắp.

## 16. Checklist trước, trong và sau bài diễn tập

### Trước khi bắt đầu

- [ ] Có ROE và phê duyệt riêng đối với tài sản, loại dữ liệu, thao tác và kênh truyền.
- [ ] Đã xác định owner, white cell, SOC/NOC, đường liên hệ khẩn cấp và stop conditions.
- [ ] Có data map: PII, bí mật, backup, log/PCAP, object storage và hệ thống đối tác.
- [ ] Đã chuẩn bị synthetic fixture, canary, account test và test receiver do tổ chức kiểm soát.
- [ ] Đã giới hạn IAM/RBAC, network segmentation, egress, tốc độ, dung lượng và thời gian phiên.
- [ ] Có kênh lưu chứng cứ mã hóa, phân quyền, danh mục artifact và chính sách retention.
- [ ] Có ngưỡng availability và phương án rollback/khôi phục được chủ hệ thống xác nhận.

### Trong quá trình thực hiện

- [ ] Mỗi thao tác có test case ID, tài sản, người thực hiện và thời gian.
- [ ] Chỉ thu lượng bằng chứng tối thiểu đủ kết luận; không trích xuất dữ liệu thật theo mặc định.
- [ ] Không tắt logging/DLP/MFA/firewall hoặc thay đổi dữ liệu nghiệp vụ ngoài ROE.
- [ ] Chỉ dùng payload synthetic và kênh test được phê duyệt cho bài mô phỏng rò rỉ.
- [ ] Theo dõi performance/availability và cảnh báo mất kiểm soát; dừng nếu vượt ngưỡng.
- [ ] Có cơ chế báo ngay khi gặp PII, secret, object ngoài scope hoặc dấu hiệu sự cố thật.

### Sau khi kết thúc

- [ ] Đã dừng mọi công cụ/job và xác nhận không còn lưu lượng test.
- [ ] Đã thu hồi token, session, tài khoản, quyền, rule hoặc cấu hình tạm.
- [ ] Đã kiểm kê, che và lưu đúng kho các bằng chứng còn cần thiết.
- [ ] Đã xử lý canary, fixture, test receiver, snapshot thử nghiệm và bản sao dữ liệu theo quy định.
- [ ] Chủ hệ thống xác nhận integrity, backup, availability và logging hoạt động bình thường.
- [ ] Có biên bản cleanup, exception còn mở, hạn xử lý và người xác nhận.
- [ ] Báo cáo nêu rõ bằng chứng, phát hiện, giới hạn kiểm thử và không suy diễn quá phạm vi.

## 17. Câu hỏi tự kiểm tra

1. Vì sao việc có quyền pentest ứng dụng không mặc nhiên cho phép export dữ liệu khách hàng từ database production?
2. So sánh ba cách chứng minh lỗi phân quyền: xem metadata IAM, truy cập record canary và tải bản ghi thật. Khi nào hai cách đầu đã đủ?
3. Một file PCAP của VLAN production có thể chứa những loại dữ liệu nhạy cảm nào, kể cả khi phần lớn lưu lượng dùng TLS?
4. Bạn sẽ thiết kế phép thử “exfiltration qua HTTPS” như thế nào để SOC có telemetry nhưng không có một byte dữ liệu thật rời hệ thống?
5. Nếu một thao tác SELECT rất chậm làm connection pool đầy, tại sao thao tác read-only vẫn phải dừng?
6. Khi công cụ proxy vô tình thu Authorization header có token production, những bước xử lý và báo cáo nào cần làm trước khi tiếp tục?
7. Những dữ liệu nào cần có trong chain-of-custody của một screenshot đã che thông tin nhạy cảm?
8. Một canary đặt trong bucket cloud nên có những thuộc tính gì để dễ phát hiện, dễ dọn dẹp và không gây ảnh hưởng nghiệp vụ?
9. Vì sao xóa các artifact ở laptop của red team chưa đủ để xác nhận cleanup?
10. Hãy viết ROE cho bài mô phỏng truy cập trái quyền giữa hai VLAN, trong đó không được phép đọc hay chỉnh sửa dữ liệu thật. Chỉ ra positive evidence, negative evidence, stop conditions và người chịu trách nhiệm xác minh.

**Điểm cần nhớ:** Bảo vệ dữ liệu sản xuất trong red team là **giới hạn thiết kế ngay từ đầu**, được thực thi trong từng thao tác và được kiểm chứng khi kết thúc. Bằng chứng tốt nhất là bằng chứng đủ để chứng minh lỗ hổng và khả năng phát hiện của đội phòng thủ, đồng thời không tạo thêm một sự cố bảo mật từ chính hoạt động kiểm thử.
