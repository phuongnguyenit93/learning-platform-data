# Trách nhiệm nhóm vận hành trong quản trị bảo mật

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của nhóm vận hành (Operations, SRE, Platform/Infrastructure Operations) trong chương trình **security assurance** liên tục.
- Phân biệt trách nhiệm **thực thi control**, **sở hữu rủi ro**, **đánh giá độc lập** và **phê duyệt ngoại lệ**; sử dụng ma trận RACI để tránh bỏ sót hoặc chồng chéo trách nhiệm.
- Tổ chức những hoạt động vận hành liên quan đến cấu hình an toàn, quản lý quyền, bí mật, lỗ hổng, thay đổi, giám sát, ứng phó sự cố và khôi phục.
- Biến nghĩa vụ vận hành thành yêu cầu có thể kiểm tra và lưu **bằng chứng xác thực, đúng phạm vi, đúng thời điểm**.
- Đánh giá năng lực vận hành qua kịch bản thực tế, phát hiện điểm thiếu, đưa ra phương án khắc phục và kiểm chứng lại.

## 1. Vì sao nhóm vận hành có trách nhiệm bảo mật?

Trong quản trị bảo mật, một control chỉ thực sự có hiệu lực khi được **triển khai, duy trì và giám sát** trong môi trường chạy thực tế. Mã nguồn đã kiểm thử trên CI có thể hoạt động với quyền tối thiểu, nhưng cấu hình production bị thay đổi, tài khoản cũ chưa thu hồi hoặc hệ thống logging bị ngắt có thể khiến kết luận bảo mật ban đầu không còn giá trị.

**Nhóm vận hành** gồm những người chịu trách nhiệm vận hành hệ thống và hạ tầng: Operations, SRE, nhóm nền tảng, quản trị cloud, mạng, hệ điều hành hoặc quản trị cơ sở dữ liệu. Tùy tổ chức, một người có thể đảm nhiệm nhiều vai trò, nhưng trách nhiệm và quyền quyết định vẫn phải được xác định rõ.

Trong module **SECURITY_SECURITY_ASSURANCE**, mục tiêu không chỉ là "vận hành không xảy ra sự cố", mà là có **bằng chứng đáng tin** rằng các mục tiêu bảo mật được đáp ứng xuyên suốt vòng đời: từ phân tích rủi ro, yêu cầu và security controls đến kiểm thử, audit, khắc phục phát hiện và đánh giá lại trong quá trình phát triển/vận hành.

Ví dụ: với mục tiêu "chỉ nhóm trực vận hành được phép thay đổi cấu hình production theo quy trình đã phê duyệt", một ticket thay đổi hoặc sơ đồ phân quyền không đủ để kết luận đã đạt. Cần kết hợp **quyền IAM thực tế**, lịch sử phê duyệt, bản ghi thực thi, trạng thái triển khai và kiểm tra sự thay đổi ngoài quy trình.

### Những việc nhóm vận hành phải chứng minh

| Khẳng định cần kiểm chứng | Ví dụ bằng chứng | Giới hạn thường gặp |
| --- | --- | --- |
| Máy chủ/cluster đang áp dụng cấu hình an toàn | Kết quả kiểm tra cấu hình có timestamp, phạm vi tài sản, revision và người review | Một snapshot không chứng minh cấu hình luôn đúng trong toàn kỳ đánh giá. |
| Quyền production được cấp theo nguyên tắc tối thiểu | Export quyền thực tế, log cấp/thu hồi, biên bản rà soát quyền, thử quyền trên tài khoản kiểm thử | Một danh sách quyền không chứng minh không có đường truy cập gián tiếp hoặc tài khoản dùng chung. |
| Log bảo mật đang được chuyển về hệ thống tập trung | Kiểm tra end-to-end từ sự kiện thử tới bộ thu, dashboard độ trễ/độ bao phủ và cảnh báo mất log | Chỉ thấy agent "running" chưa chứng minh sự kiện tới được nơi lưu. |
| Sao lưu có thể phục hồi | Kết quả restore drill kèm thời gian, checksum/kiểm tra dữ liệu và quyết định của người chịu trách nhiệm | Job backup "success" chưa chứng minh dữ liệu khôi phục dùng được. |
| Lỗ hổng được xử lý theo rủi ro | Danh sách tài sản, phát hiện, ticket, bản vá triển khai, kết quả scan lại và ngoại lệ có thời hạn | Đóng ticket hoặc cập nhật package ở repository chưa chứng minh production đã sửa. |

## 2. Phạm vi trách nhiệm và ranh giới quyền hạn

Không có một mô hình tổ chức duy nhất áp dụng cho mọi công ty. Dù vậy, cần tách bốn loại trách nhiệm:

1. **Thực hiện (execution):** ai cấu hình, thay đổi, giám sát và ứng cứu.
2. **Chịu trách nhiệm cuối cùng (accountability):** ai sở hữu kết quả đối với một mục tiêu/control hoặc quyết định rủi ro.
3. **Tư vấn, đánh giá (advisory/assessment):** ai đặt tiêu chí bảo mật, review thiết kế, kiểm thử và đánh giá bằng chứng.
4. **Phê duyệt chấp nhận rủi ro:** ai có thẩm quyền chấp nhận ngoại lệ và chịu trách nhiệm theo dõi rủi ro tồn dư.

Nhóm vận hành thường chịu trách nhiệm thực thi nhiều control môi trường chạy, nhưng **không mặc nhiên** có quyền tự chấp nhận mọi rủi ro hoặc tự xác nhận kết quả audit mà họ là đối tượng được đánh giá. Quyền phê duyệt do chính sách tổ chức quy định, tương xứng mức độ rủi ro.

### Ma trận RACI tham khảo

**R** = trực tiếp thực hiện; **A** = người chịu trách nhiệm cuối cùng; **C** = được tham vấn; **I** = được thông báo. Với một hoạt động, nên xác định một vai trò **A** rõ ràng; tên nhóm dưới đây là ví dụ và phải điều chỉnh theo tổ chức.

| Hoạt động | Ops / SRE | Dev / Service team | Security / AppSec | Chủ sở hữu dịch vụ hoặc rủi ro | Audit độc lập |
| --- | --- | --- | --- | --- | --- |
| Duy trì inventory tài sản production, cấu hình nền tảng | **R** | C | C | **A** | I |
| Xây dựng và kiểm thử cơ chế phân quyền trong ứng dụng | C | **R** | C | **A** | I |
| Cấp, thay đổi, thu hồi quyền quản trị hạ tầng | **R** | I | C | **A** | I |
| Xây dựng tiêu chí hardening và yêu cầu log | **R** | C | **A** | C | I |
| Theo dõi cảnh báo và xử lý sự cố vận hành ban đầu | **R** | C | C | **A** | I |
| Phân tích và sửa lỗ hổng ở mã ứng dụng | C | **R** | C | **A** | I |
| Triển khai bản vá OS/runtime và kiểm tra hiệu lực | **R** | C | C | **A** | I |
| Rà soát evidence và kết luận trong cuộc audit độc lập | C | C | C | I | **R/A** |
| Quyết định chấp nhận rủi ro vượt ngưỡng | C | C | C | **A/R** | I |

**Lưu ý:** ma trận có tính minh họa. Trong tổ chức có SOC hoặc IAM riêng, họ có thể là R cho các mục tương ứng. Với quyết định liên quan toàn doanh nghiệp, A có thể thuộc CISO, lãnh đạo nghiệp vụ hoặc ủy ban rủi ro theo chính sách. Không nên máy móc gán một nhóm làm A ở mọi hệ thống.

### Trách nhiệm chia sẻ trong cloud

Khi dùng managed database, Kubernetes hay SaaS, nhà cung cấp có thể đảm trách một phần hạ tầng; khách hàng vẫn thường chịu trách nhiệm về **cấu hình dịch vụ, định danh, quyền truy cập, dữ liệu, ứng dụng và lựa chọn control** trong phạm vi mình quản lý. Ranh giới phải được ghi bằng **ma trận trách nhiệm cụ thể theo dịch vụ và hợp đồng**, không suy đoán rằng "đã lên cloud thì nhà cung cấp lo bảo mật".

Ví dụ: nhà cung cấp database quản lý vá hệ điều hành cho dịch vụ managed database, nhưng nhóm vận hành có thể vẫn cần cấu hình network policy, encryption, tài khoản kết nối, bản sao lưu, giám sát và cập nhật phiên bản engine theo nghĩa vụ được chia sẻ.

## 3. Đặt trách nhiệm vào vòng đời vận hành

~~~mermaid
flowchart TD
    A["Đánh giá tài sản, rủi ro và mục tiêu"] --> B["Định nghĩa control và người chịu trách nhiệm"]
    B --> C["Triển khai baseline, IAM, logging, backup"]
    C --> D["Kiểm tra trước khi phát hành"]
    D --> E["Giám sát trạng thái production và thay đổi"]
    E --> F{"Có drift, sự cố hoặc control không đạt?"}
    F -- "Không" --> G["Thu thập evidence, review định kỳ"]
    G --> E
    F -- "Có" --> H["Phân loại finding, giảm thiểu rủi ro"]
    H --> I["Sửa, triển khai, retest"]
    I --> G
~~~

| Giai đoạn | Trách nhiệm điển hình của nhóm vận hành | Đầu ra có thể kiểm tra |
| --- | --- | --- |
| Thiết kế nền tảng | Đưa ra yêu cầu vận hành về mạng, quyền, backup, log, khả năng cô lập và khôi phục | Thiết kế được review, ma trận control, tiêu chí chấp nhận |
| Xây dựng và triển khai | Thiết lập hạ tầng bằng cấu hình có quản lý phiên bản, chính sách quyền, secret, hardening và kiểm tra trước release | Pull request cấu hình, kết quả kiểm thử, deployment ID |
| Vận hành ổn định | Theo dõi drift, hiệu lực quyền, log, bản vá, backup, độ bao phủ phát hiện và tình trạng phụ thuộc | Snapshot, kết quả giám sát, ticket phát hiện, review |
| Thay đổi/sự cố | Đánh giá tác động, quản lý phê duyệt, phản ứng sự cố và khôi phục | Change record, incident timeline, quyết định, retest |
| Ngừng dịch vụ | Thu hồi danh tính/secret, kiểm soát lưu giữ hoặc hủy dữ liệu, đóng giám sát và tài nguyên | Biên bản decommission, chứng cứ thu hồi quyền và lưu giữ/xóa theo chính sách |

Vòng đời này phải có cả **thay đổi theo sự kiện** (ví dụ IAM permission drift hoặc lộ khóa) và **đánh giá theo chu kỳ**. Chỉ chạy review hàng quý không đủ khi control có thể bị phá vỡ bởi một deployment hôm nay.

## 4. Quản lý tài sản, cấu hình và baseline an toàn

Không thể đánh giá hệ thống khi không biết tài sản nào tồn tại, đang được ai sở hữu hoặc có điểm truy cập nào.

Nhóm vận hành cần phối hợp xây dựng **inventory có chủ sở hữu** cho máy ảo, cluster, namespace, database, storage bucket, dịch vụ managed cloud, tài khoản đặc quyền, endpoint công khai, certificate và luồng log quan trọng. Inventory nên có ID duy nhất, môi trường, mức nhạy cảm, vai trò nghiệp vụ, owner và liên kết đến deployment/configuration hiện hành.

**Baseline bảo mật** là bộ quy tắc cấu hình được duyệt (chẳng hạn mặc định từ chối truy cập công khai, cấu hình mã hóa, giới hạn quyền, cấu hình TLS, thời gian lưu log). Một baseline có ý nghĩa khi được so sánh với **trạng thái thực tế** và có quy trình xử lý sai lệch (*configuration drift*).

Ví dụ với một dịch vụ API Java/Spring Boot:

- Chính sách ingress chỉ cho phép lưu lượng qua gateway/đường mạng dự kiến.
- Process/container chạy với quyền phù hợp; hạn chế quyền root hoặc đặc quyền không cần thiết.
- Cấu hình bảo mật của runtime, container và hệ điều hành được quản lý theo phiên bản.
- Endpoint quản trị như Actuator chỉ được mở với đúng phạm vi mạng và cơ chế xác thực cần thiết.
- Tài khoản service-to-service có quyền vừa đủ; secret không đặt trực tiếp trong image hoặc commit.
- Log bảo mật, metric và tín hiệu về cấu hình được gửi về nơi tập trung có quyền quản trị phù hợp.

**Kiểm tra bằng chứng:** lấy revision IaC được phê duyệt, đối chiếu cấu hình cluster/API thực tế, kết quả kiểm tra policy và change record; dùng thêm test truy cập có kiểm soát khi cần. File IaC được review chỉ chứng minh **ý định cấu hình**, không tự chứng minh production đang chạy đúng revision.

Khi phát hiện drift, cần phân loại: thay đổi hợp lệ đã phê duyệt, thay đổi khẩn cấp chưa được hợp thức hóa, lỗi công cụ, hoặc thay đổi trái phép. Không nên tự động ghi đè mọi drift nếu có nguy cơ phá vỡ dịch vụ; quy trình cần quy định trường hợp tự sửa, trường hợp cô lập và trường hợp chuyển người phê duyệt.

## 5. Quản trị định danh, quyền truy cập và bí mật

Quyền quản trị hạ tầng có thể vô hiệu hóa các control khác. Vì vậy, vận hành cần thực hiện và chứng minh:

1. **Quyền tối thiểu:** chỉ cấp quyền thực sự cần theo vai trò/công việc, tách quyền read-only và quyền thay đổi, giới hạn phạm vi tài nguyên và thời gian khi có thể.
2. **Quản lý vòng đời truy cập:** yêu cầu có phê duyệt; cấp, sửa, thu hồi khi thay đổi công việc/nghỉ việc; review định kỳ và khi có sự kiện rủi ro.
3. **Tài khoản đặc quyền và khẩn cấp:** xác thực mạnh, ghi nhật ký thao tác, cấp quyền theo nhu cầu; quy trình `break-glass` phải có lý do, thời hạn, giám sát và review sau sử dụng.
4. **Định danh máy và service account:** tránh tài khoản chia sẻ không thể truy vết; giới hạn quyền workload, workload identity, API token và khả năng impersonation.
5. **Bí mật và khóa:** dùng kho secret/keys phù hợp, hạn chế người đọc, luân chuyển và thu hồi khi có nghi vấn; tránh secret trong source, image, artifact, output CI hay log.
6. **Phân tách nhiệm vụ:** với thay đổi rủi ro cao, người triển khai và người phê duyệt hoặc xác minh nên được phân vai theo chính sách; có đường xử lý khẩn cấp được ghi nhận.

Một bảng xuất cấu hình RBAC chỉ là **bằng chứng thiết kế/trạng thái quyền**. Để kết luận kiểm soát hiệu quả, cần thêm thử nghiệm bằng tài khoản test, kiểm tra đường leo thang đặc quyền, và các dấu vết cấp/thu hồi thực tế.

Ví dụ một kỹ sư trực cần quyền sửa network policy trong một giờ để khắc phục sự cố. Hồ sơ thích hợp gồm ticket sự cố, người phê duyệt, cấp quyền tạm thời, thao tác đã thực hiện, kiểm tra tác động, bằng chứng thu hồi và review sau khẩn cấp.

## 6. Quản lý lỗ hổng và bản vá trong production

Nhóm vận hành thường chịu trách nhiệm cập nhật thành phần hạ tầng, base image, OS, runtime, cluster add-on, cấu hình và sản phẩm của nhà cung cấp trong phạm vi được giao. Nhóm phát triển thường sửa lỗi trong code hoặc dependency ứng dụng; hai nhóm phải phối hợp khi khắc phục đòi hỏi thay đổi cả ứng dụng lẫn hạ tầng.

Chu trình điển hình:

1. **Phát hiện:** từ scan tài sản, inventory image/dependency, cảnh báo nhà cung cấp, kiểm thử xâm nhập hoặc báo cáo sự cố.
2. **Triage theo rủi ro thực:** xét mức độ ảnh hưởng, khả năng khai thác, tài sản phơi lộ, dữ liệu xử lý, control bù trừ và độ tin cậy của phát hiện.
3. **Gán chủ sở hữu và thời hạn:** phân công sửa, ưu tiên, tiêu chí xác nhận; deadline phụ thuộc chính sách và rủi ro của tổ chức.
4. **Triển khai có kiểm soát:** thử khả năng tương thích, lên kế hoạch thay đổi, rollout và rollback; cân nhắc biện pháp giảm thiểu tạm thời nếu bản vá chưa sẵn sàng.
5. **Retest:** xác nhận phiên bản/điều kiện lỗi đã được sửa trên **đúng môi trường**, kiểm tra hồi quy và theo dõi lỗ hổng còn mở.
6. **Ngoại lệ:** nếu không thể xử lý đúng hạn, chủ sở hữu rủi ro có thẩm quyền phê duyệt trong phạm vi và thời hạn xác định; Ops theo dõi hiệu lực biện pháp bù trừ.

**Ví dụ:** pipeline đã chuyển image của dịch vụ Java từ bản runtime có lỗ hổng sang bản vá mới, nhưng deployment production vẫn trỏ tới image digest cũ. Báo cáo CI "đã vá" không đủ. Cần đối chiếu image digest đang chạy, kết quả scan lại và tình trạng rollout. Nếu có nhiều replica, phải kiểm tra toàn bộ phạm vi được nêu trong yêu cầu.

## 7. Logging, giám sát và phát hiện hành vi bất thường

Nhóm vận hành cần đảm bảo **tín hiệu bảo mật tồn tại, được chuyển đúng nơi, còn toàn vẹn và có người xử lý**. Mục tiêu không chỉ là chạy hệ thống logging.

Một danh mục sự kiện thường gồm: đăng nhập/quyền đặc biệt, thay đổi IAM, thay đổi cấu hình hạ tầng, dùng tài khoản khẩn cấp, truy cập trái phép, thay đổi chính sách mạng, thay đổi secret, vô hiệu hóa logging, điều chỉnh retention và sự kiện backup/restore.

Với từng nguồn, nên xác định:

| Câu hỏi | Yêu cầu vận hành |
| --- | --- |
| Ai tạo sự kiện? | Dịch vụ hoặc thiết bị nguồn được định danh; log có phiên bản schema. |
| Ghi nhận điều gì? | Actor/service identity, action, resource ID, kết quả, thời gian, trace/correlation ID và môi trường khi phù hợp. |
| Có dữ liệu nhạy cảm không? | Không ghi password, token, private key, payload cá nhân không cần thiết; áp dụng che/redaction. |
| Log có được nhận đầy đủ? | Giám sát ingest rate, độ trễ, heartbeat, khoảng trống và lỗi parse. |
| Ai được xem/sửa/xóa? | Quyền phân tách, thời hạn lưu và audit log cho các thao tác trên kho log. |
| Ai trực xử lý? | Alert owner, lịch on-call, ngưỡng ưu tiên, escalation và runbook đã kiểm tra. |

### Ví dụ một control có thể đánh giá

**Claim:** "Sự kiện thay đổi quyền production từ cloud IAM được chuyển tới bộ thu tập trung và cảnh báo khi luồng sự kiện ngừng hoạt động".

Để có thể kiểm tra, nhóm vận hành xác định nguồn IAM thuộc phạm vi, mô tả những event type bắt buộc, cửa sổ quan sát, ngưỡng trễ nhận, đường kiểm thử và người nhận cảnh báo. Có thể ghi nhận control dưới dạng cấu hình *minh họa*:

~~~yaml
control_id: OPS-LOG-01
objective: "Phát hiện thay đổi quyền IAM trên production"
scope:
  environment: production
  event_types:
    - IAM_POLICY_CHANGED
    - PRIVILEGED_ROLE_GRANTED
owner: platform-operations
reviewer: security-operations
validation:
  method: "Tạo sự kiện thử được phê duyệt và kiểm tra end-to-end"
  expected: "Sự kiện có đủ ID và xuất hiện trong bộ thu đúng ngưỡng đã thống nhất"
  evidence:
    - "<TEST_EVENT_ID>"
    - "<COLLECTOR_EVENT_URI>"
    - "<PIPELINE_HEALTH_REPORT>"
    - "<ALERT_TEST_RESULT>"
limitations: "Không bao phủ nguồn IAM chưa đưa vào inventory"
~~~

Đây là **metadata về tiêu chí và bằng chứng**, không phải cấu hình tự chạy của một công cụ monitoring. Khi sử dụng cần thay giá trị mẫu bằng ID/hiện vật thực, tiêu chí thời gian được chủ sở hữu phê duyệt và phương pháp kiểm tra đã quan sát.

Cần kiểm thử định kỳ theo chuỗi **tạo event thử → event đến collector → rule phát hiện → cảnh báo đến đúng người → xử lý hoặc xác nhận**. Dashboard "healthy" không đủ nếu pipeline âm thầm bỏ mất một loại sự kiện quan trọng.

## 8. Sao lưu, phục hồi và khả năng duy trì hoạt động

Khả năng phục hồi là một phần trọng yếu của vận hành an toàn. Nhóm vận hành cần hỗ trợ mục tiêu **tính sẵn sàng** và, trong nhiều hệ thống, **toàn vẹn** của dữ liệu khôi phục sau tấn công hoặc sự cố.

Hai khái niệm cần định nghĩa:

- **RPO (Recovery Point Objective):** mức mất dữ liệu tối đa có thể chấp nhận được, tính theo thời gian.
- **RTO (Recovery Time Objective):** khoảng thời gian mục tiêu để khôi phục dịch vụ hoặc chức năng được chỉ định.

Ví dụ, nếu một dịch vụ có RPO 15 phút và RTO 2 giờ, việc tạo backup mỗi đêm rõ ràng không đủ để đáp ứng RPO trong kịch bản chỉ dựa vào backup đó. RPO/RTO phải được chủ sở hữu nghiệp vụ và nhóm kỹ thuật thống nhất theo rủi ro và khả năng thực tế.

Nhóm vận hành cần xác định tài sản có backup, lịch backup, quyền truy cập, mã hóa, khả năng chống sửa/xóa trái phép, lưu trữ ngoài vùng ảnh hưởng, quy trình restore và điều kiện chấp nhận. Quan trọng hơn, phải **thực hành khôi phục** trong môi trường được kiểm soát và đánh giá dữ liệu được khôi phục có chính xác, đầy đủ và an toàn không.

Bằng chứng có giá trị gồm: backup job ID, bản kê dữ liệu, cấu hình lưu giữ, kết quả restore test, thời gian khôi phục thực đo, kiểm tra tính toàn vẹn ứng dụng, người phê duyệt và finding còn tồn tại. Backup “SUCCESS” chỉ xác nhận một bước của quy trình, không đồng nghĩa mục tiêu khôi phục đạt.

## 9. Quản lý thay đổi, ngoại lệ và phân tách nhiệm vụ

Mỗi thay đổi production có thể làm thay đổi trạng thái assurance. Trước khi triển khai, nhóm vận hành nên cùng các bên liên quan xác định:

- Control hoặc tài sản nào chịu ảnh hưởng; liệu thay đổi có mở thêm cổng, tăng quyền, sửa dữ liệu, thay đổi hệ thống log hoặc cấu hình mật mã không.
- Ai review và phê duyệt theo mức rủi ro; ai triển khai; ai kiểm tra sau triển khai.
- Bài kiểm tra tự động/thu công nào cần chạy; tiêu chí dừng và rollback.
- Bằng chứng nào phải lưu: change ID, commit, build/deployment ID, thời điểm, người thao tác, kết quả test và trạng thái hệ thống sau thay đổi.

Thay đổi **khẩn cấp** có thể dùng quy trình rút gọn khi chính sách cho phép, nhưng vẫn cần ghi lý do, giới hạn phạm vi, log thao tác, kiểm tra hậu triển khai và review/phê duyệt hồi tố theo quy định.

**Ngoại lệ bảo mật** không phải một cách để chuyển một control "không đạt" thành "đạt". Một ngoại lệ có căn cứ cần nêu yêu cầu không đáp ứng, rủi ro tồn dư, control bù trừ, giới hạn áp dụng, người chấp nhận rủi ro, thời hạn và điều kiện xem xét lại. Ops theo dõi và thực thi những biện pháp trong phạm vi của họ; **người có thẩm quyền** ra quyết định chấp nhận rủi ro.

Trong hệ thống IaC/GitOps, không nên giả định mọi thay đổi đều qua repository: một thao tác trực tiếp trên cloud console vẫn có thể làm phát sinh drift. Cần đối chiếu desired state và actual state, theo dõi thao tác đặc quyền ngoài pipeline và xác định cách hợp thức hóa hoặc hoàn nguyên.

## 10. Ứng phó sự cố và bảo quản bằng chứng

Khi có dấu hiệu xâm nhập hoặc control mất hiệu lực, nhóm vận hành thường là người đầu tiên nhìn thấy triệu chứng hoặc thực hiện thao tác cô lập. Quy trình ứng phó cần phối hợp với SOC/Security, nhóm phát triển, chủ sở hữu dịch vụ và đầu mối pháp lý khi thích hợp.

~~~mermaid
flowchart TD
    D["Phát hiện cảnh báo / sai lệch"] --> T["Xác minh và phân loại mức độ"]
    T --> E["Kích hoạt điều phối, phân vai và escalation"]
    E --> P["Bảo toàn log và bằng chứng có thể mất"]
    P --> C["Cô lập / giảm tác động theo runbook"]
    C --> R["Khắc phục nguyên nhân, phục hồi có kiểm tra"]
    R --> V["Xác minh control và giám sát tái diễn"]
    V --> L["Hậu kiểm, cập nhật runbook và bằng chứng assurance"]
~~~

Một runbook vận hành nên trả lời rõ: điều kiện kích hoạt, người chỉ huy sự cố, phương thức liên lạc, quyền thực thi thao tác nguy hiểm, bước giảm thiểu, tiêu chí phục hồi, điểm cần lưu bằng chứng và cách chuyển cấp khi cần quyết định rủi ro lớn.

**Bảo quản bằng chứng** (*chain of custody*) đòi hỏi ghi lại nguồn, thời điểm thu, người thu, thao tác chuyển giao, nơi lưu và cách xác minh tính toàn vẹn. Không nhất thiết mọi sự cố đều cần điều tra pháp lý, nhưng việc xóa dữ liệu, rotate secret, tái tạo máy chủ hoặc dọn log thiếu kế hoạch có thể khiến mất thông tin để xác định nguyên nhân.

Ví dụ phát hiện workload đáng ngờ đang dùng credential cloud: cần phối hợp cô lập/thu hồi theo kế hoạch ứng cứu đã phê duyệt, đồng thời lưu dấu vết truy cập và đánh giá phạm vi lộ trước khi dữ liệu không còn. Thứ tự thao tác phải cân bằng **giảm thiểu thiệt hại ngay** với khả năng điều tra, không trì hoãn khẩn cấp chỉ để có bộ bằng chứng đẹp.

Sau sự cố, kết luận "đã khôi phục" nên có bằng chứng: phiên bản sạch, quyền đã điều chỉnh, nguyên nhân được sửa, lỗ hổng được retest và giám sát không còn báo dấu hiệu tái diễn trong khoảng quan sát phù hợp. Báo cáo hậu kiểm giúp cập nhật control, không chỉ đánh dấu ticket đã đóng.

## 11. Xây dựng hồ sơ bằng chứng cho trách nhiệm vận hành

Security assurance đòi hỏi có **đường nối từ rủi ro đến mục tiêu, yêu cầu, control, hoạt động đánh giá và kết luận**. Một cách quản lý thực tế là gắn ID nhất quán:

| Bước | Minh họa |
| --- | --- |
| Rủi ro `RISK-OPS-01` | Thay đổi quyền IAM trái phép tạo quyền đọc dữ liệu nhạy cảm. |
| Mục tiêu `OBJ-OPS-01` | Chỉ thay đổi quyền theo phê duyệt và phát hiện nhanh thao tác ngoài quy trình. |
| Yêu cầu `REQ-OPS-01` | Mọi thay đổi IAM production có dấu vết có thể đối chiếu người thực hiện, lý do, thời gian, kết quả và cảnh báo. |
| Control `CTRL-OPS-01` | Cấp quyền giới hạn, phê duyệt thay đổi, thu log IAM tập trung và kiểm tra chênh lệch quyền. |
| Đánh giá `TEST-OPS-01` | Tạo một thay đổi quyền thử được kiểm soát; kiểm tra event, rule cảnh báo, người nhận và quyền thực tế. |
| Bằng chứng `EV-OPS-01` | IAM change event, phê duyệt, collector record, alert/ticket và snapshot quyền sau thay đổi. |
| Finding `FIND-OPS-01` | Một tài khoản quản trị không được giám sát; khắc phục bổ sung nguồn log và retest. |

### Mẫu evidence record

Mẫu dưới đây mang tính hướng dẫn; các giá trị trong dấu `<...>` là **placeholder**, không phải bằng chứng đã thu được:

~~~yaml
evidence_id: "EV-OPS-01"
risk_id: "RISK-OPS-01"
objective_id: "OBJ-OPS-01"
requirement_id: "REQ-OPS-01"
control_id: "CTRL-OPS-01"
claim: "Thay đổi IAM production có thể truy vết và phát hiện"
service: "<SERVICE_ID>"
environment: production
asset_scope: "<ACCOUNT_AND_RESOURCE_SCOPE>"
control_owner: "<ACCOUNTABLE_ROLE>"
operator: "<PERSON_OR_WORKLOAD_ID>"
reviewer: "<INDEPENDENT_REVIEWER>"
collected_at: "<ISO_8601_UTC>"
configuration_revision: "<IAC_COMMIT_OR_CONFIG_VERSION>"
deployment_or_change_id: "<CHANGE_ID>"
method: "<REVIEW_TEST_OR_OBSERVATION>"
result: "<PASS_FAIL_INCONCLUSIVE>"
artifact_refs:
  - "<ACCESS_CONTROL_SNAPSHOT>"
  - "<IAM_AUDIT_EVENT>"
  - "<CENTRAL_LOG_AND_ALERT_RESULT>"
limitations: "<KNOWN_GAPS_OR_SCOPE_EXCLUSIONS>"
retest_or_review_due: "<DATE_OR_TRIGGER>"
~~~

Một bản ghi YAML chỉ là **chỉ mục bằng chứng**. Người đánh giá phải kiểm tra được hiện vật gốc, phạm vi, phương pháp, nguồn gốc và tính toàn vẹn. Cần hạn chế quyền đọc, không sao chép token, private key, mật khẩu hay dữ liệu cá nhân không cần thiết vào báo cáo.

### Tiêu chí chất lượng của bằng chứng vận hành

1. **Có phạm vi rõ:** hệ thống nào, môi trường nào, tài sản nào, khoảng thời gian nào.
2. **Gắn với bản thực chạy:** ID change, image digest, version, cấu hình và định danh nguồn log.
3. **Có nguồn tin cậy:** nơi xuất phát, người/hệ thống tạo, khả năng xem lại log gốc và dấu vết sửa.
4. **Đủ để đánh giá claim:** ví dụ test restore thực tế với RPO/RTO, không chỉ kết quả backup job.
5. **Còn hiệu lực:** thay đổi IAM, patch, deploy hoặc sự cố có thể làm bằng chứng cũ không còn đại diện.
6. **Được review:** người xác nhận có tiêu chí, thẩm quyền và không phụ thuộc hoàn toàn vào người tự đánh giá công việc của mình ở nơi cần độc lập.
7. **Có thể truy lại finding:** kết quả không đạt phải dẫn tới chủ sở hữu, hạn xử lý, kiểm chứng lại và rủi ro tồn dư.

## 12. Lịch vận hành và chỉ số theo dõi assurance

Những hoạt động liên tục cần được đưa vào lịch làm việc và pipeline phù hợp, với trách nhiệm rõ ràng.

| Thời điểm kích hoạt | Hoạt động vận hành | Bằng chứng cần duy trì |
| --- | --- | --- |
| Theo tín hiệu gần thời gian thực | Theo dõi thay đổi đặc quyền, log pipeline lỗi, drift quan trọng, cảnh báo đột biến | Event, alert, lịch sử điều tra/escalation |
| Khi release hoặc thay đổi cấu hình | Xác nhận phiên bản triển khai, đánh giá ảnh hưởng control, smoke/security checks và rollback plan | Deployment ID, change review, kết quả kiểm tra |
| Theo chu kỳ do chính sách quy định | Rà soát quyền, cập nhật lỗ hổng, kiểm tra backup/restore, xác minh rule cảnh báo, đánh giá ngoại lệ | Biên bản review, kết quả test, scan, ticket |
| Khi có nhân sự/đơn vị thay đổi | Thu hồi hoặc cập nhật quyền, secret, owner và on-call | Access record, kiểm chứng quyền hiện tại |
| Khi xảy ra sự cố hoặc phát hiện nghiêm trọng | Cô lập, bảo quản bằng chứng, khắc phục và retest | Timeline, evidence, quyết định và kết quả xác minh |
| Trước audit hoặc đánh giá lại | Đối chiếu các claim và evidence register, xác định phạm vi thiếu hoặc bằng chứng cũ | Danh sách control có/thiếu bằng chứng, các finding và kết luận |

Các chỉ số có thể giúp đánh giá hiệu quả, chẳng hạn: tỷ lệ tài sản có owner và log đầy đủ, tỷ lệ control được kiểm chứng trong thời hạn, số finding quá hạn theo rủi ro, độ trễ phát hiện lỗi log pipeline, tỷ lệ khôi phục đạt RTO/RPO trong bài tập, thời gian thu hồi quyền sau thay đổi nhân sự, tỷ lệ thay đổi ngoài quy trình được phát hiện.

**Tránh biến chỉ số thành mục tiêu hình thức.** Ví dụ "100% alert đã đóng" không phản ánh chất lượng xử lý nếu alert bị tắt tùy tiện hoặc tình huống chưa được điều tra. Cần theo dõi cả độ bao phủ, kết quả kiểm tra thực tế và lý do ngoại lệ.

## 13. Kịch bản thực hành: IAM drift trong hệ thống thanh toán

**Bối cảnh:** hệ thống thanh toán dùng dịch vụ Java/Spring Boot trên Kubernetes; workload cần truy cập một nhóm đối tượng trong object storage. Theo baseline, service account chỉ được đọc bucket dành riêng cho giao dịch. Trong đợt bảo trì, một vai trò cloud được mở rộng quyền tới mọi bucket trong tài khoản. Hệ thống vẫn hoạt động bình thường, CI xanh, nhưng monitoring phát hiện permission drift.

### Phân tích và điều phối

| Câu hỏi | Xử lý đề xuất | Bằng chứng cần lưu |
| --- | --- | --- |
| Ai có trách nhiệm xác minh sai lệch? | Ops/SRE xác định quyền thực tế, thời điểm và đường cấp quyền; Security tham gia đánh giá tác động. | IAM policy hiện hành, event thay đổi, change ID, inventory tài sản |
| Ai quyết định chấp nhận quyền mở rộng? | Chủ sở hữu rủi ro hoặc người được ủy quyền theo chính sách; không mặc nhiên là người sửa cấu hình. | Quyết định phê duyệt/không phê duyệt và phân tích rủi ro |
| Có thể ảnh hưởng dữ liệu nào? | Chủ dữ liệu và đội phát triển cùng Ops kiểm tra phạm vi bucket, truy cập gần đây và khả năng lạm dụng. | Danh sách tài nguyên liên quan, audit event, nhận định mức tác động |
| Khắc phục ra sao? | Áp dụng lại quyền tối thiểu, review người có thể sửa policy, sửa đường tạo drift trong IaC/quy trình. | PR cấu hình, change approval, rollout, policy snapshot |
| Chứng minh đã sửa bằng cách nào? | Kiểm thử cho phép đọc đúng bucket và từ chối bucket ngoài phạm vi bằng identity kiểm thử phù hợp. | Kết quả positive/negative test, event và chữ ký review |
| Bảo đảm không tái diễn? | Giám sát drift, báo động khi cấp quyền rộng, kiểm tra pipeline và runbook, đưa vào hoạt động kiểm tra định kỳ. | Tín hiệu alert thử, báo cáo scan, owner và lần review tiếp theo |

### Các bước giải quyết

1. **Xác minh tín hiệu:** phân biệt false positive với sai lệch thực tế; đối chiếu effective permissions, không chỉ file policy trên repository.
2. **Giảm thiểu tác động:** nếu phạm vi quyền bị mở rộng ngoài chính sách, kích hoạt đúng quy trình ứng cứu/rollback theo mức rủi ro; giữ log thay đổi và quyết định.
3. **Tìm nguyên nhân:** xác định ai/công cụ nào tạo thay đổi, vì sao baseline không chặn và nguồn drift có thể lặp lại không.
4. **Sửa nguyên nhân và xác minh:** thu hẹp quyền, kiểm tra tác động trên tài khoản thử, deploy config hợp lệ và kiểm tra hiệu lực ở production.
5. **Cập nhật assurance case:** bổ sung finding, evidence trước/sau, kết quả retest, rủi ro tồn dư và điều kiện đánh giá lại.

Điểm then chốt là **một thay đổi quyền có thể phá vỡ mục tiêu bảo mật mà không làm ứng dụng lỗi hoặc CI thất bại**. Trách nhiệm của nhóm vận hành là duy trì và cung cấp được bằng chứng về trạng thái thực thi, điều phối xử lý, và chuyển cấp quyết định rủi ro đúng người có thẩm quyền.

## 14. Những sai lầm cần tránh

| Nhận định thiếu cơ sở | Vấn đề | Thực hành phù hợp |
| --- | --- | --- |
| "Security đã review nên Ops không cần kiểm tra nữa." | Review lúc thiết kế không phản ánh drift trong production. | Kiểm tra trạng thái thực tế và báo thay đổi liên quan. |
| "Cloud provider chịu trách nhiệm toàn bộ." | Hợp đồng và loại dịch vụ quyết định ranh giới trách nhiệm. | Lập ma trận theo dịch vụ, giữ owner cho mỗi control. |
| "Pipeline xanh nghĩa là production an toàn." | Build test có thể khác cấu hình và tài nguyên thực thi. | Liên kết commit, build, deployment và kiểm tra runtime. |
| "Có backup tức là có thể phục hồi." | Restore có thể thất bại hoặc không đáp ứng mục tiêu thời gian. | Thử restore có dữ liệu đo và bằng chứng kiểm tra. |
| "Không có alert nghĩa là không có bất thường." | Rule có thể thiếu, nguồn log bị tắt hoặc tín hiệu bị mất. | Kiểm thử end-to-end và giám sát health của telemetry. |
| "Ai sửa lỗi cũng có thể tự phê duyệt mọi ngoại lệ." | Dễ thiếu đánh giá độc lập hoặc vượt thẩm quyền rủi ro. | Xác định trách nhiệm, cấp phê duyệt và lưu quyết định. |
| "Đã đóng ticket thì control đạt." | Chưa xác minh trạng thái sau sửa. | Retest ở đúng môi trường, lưu bằng chứng và reviewer. |

## 15. Bài tập tự kiểm tra

**Tình huống:** trong một tuần, đội SRE đã chuyển hệ thống thu log sang collector mới. Một tuần sau, audit phát hiện log truy cập đặc quyền của dịch vụ thanh toán bị mất trong một khoảng thời gian. Ticket migration ghi "Done", không có kết quả kiểm tra đầu cuối; SOC không nhận được cảnh báo gián đoạn log.

Hãy trả lời:

1. Những mục tiêu bảo mật và control nào bị ảnh hưởng? Ai cần tham gia đánh giá, xử lý và quyết định mức rủi ro?
2. Ticket "Done" hiện chứng minh được điều gì, và chưa chứng minh được điều gì?
3. Cần ưu tiên điều tra và lưu những bằng chứng nào trước khi thay cấu hình?
4. Cần thiết kế test và tiêu chí nghiệm thu nào để hạn chế tái diễn?
5. Phân biệt bằng chứng **đã sửa pipeline** với bằng chứng **đã đánh giá tác động của khoảng trống log**.

**Gợi ý lời giải:**

- **Mục tiêu:** truy vết trách nhiệm, phát hiện sự kiện đặc quyền và khả năng điều tra; control liên quan log forwarding, coverage, health monitoring và change management.
- **Phân vai:** Ops/SRE xác minh cấu hình và sửa pipeline; SOC/Security đánh giá tín hiệu và phạm vi bỏ sót; nhóm dịch vụ hỗ trợ xác định event bắt buộc; chủ sở hữu rủi ro quyết định cách xử lý hậu quả; audit xem xét kết luận độc lập theo nhiệm vụ.
- **Giới hạn ticket:** thể hiện công việc migration được báo hoàn tất, không chứng minh log đã chuyển đủ hoặc detection vận hành hiệu quả.
- **Bằng chứng ưu tiên:** cấu hình collector cũ/mới, change timeline, metric ingestion, nguồn log còn lưu ở ứng dụng/cloud, sự kiện đặc quyền, dấu vết thay đổi quyền và quyết định ứng cứu.
- **Retest:** tạo event đặc quyền được phê duyệt, theo dõi tới kho tập trung, phát hiện theo rule, thông báo đúng on-call, xác minh không mất event và giám sát heartbeat. Lưu event ID, timestamp, cấu hình phiên bản và kết quả reviewer.
- **Khoảng trống lịch sử:** pipeline đã sửa không làm những log bị thiếu tự xuất hiện. Cần đánh giá dữ liệu có thể khôi phục từ nguồn khác, khoảng thời gian và tài sản không quan sát được, tác động tiềm ẩn và rủi ro tồn dư; kết luận phải nêu giới hạn.

## Ghi nhớ

- Nhóm vận hành duy trì **hiệu lực thực tế** của security controls trên production và cung cấp bằng chứng về cấu hình, quyền, log, patch, backup, thay đổi và ứng phó sự cố.
- **RACI, chủ sở hữu control và thẩm quyền chấp nhận rủi ro** cần rõ ràng để không có trách nhiệm bị bỏ sót hoặc tự phê duyệt sai thẩm quyền.
- Bằng chứng bảo mật phải **gắn claim với phiên bản/môi trường, thời điểm, nguồn gốc và kết quả kiểm chứng**; trạng thái "Done" của ticket không đủ để chứng minh đạt mục tiêu.
- Mỗi drift, sự cố, thay đổi quyền, bản vá hoặc thay đổi triển khai có thể làm kết luận assurance cũ hết hiệu lực, đòi hỏi **đánh giá lại**.
- Security assurance liên tục là sự phối hợp giữa **Ops, Dev, Security, chủ sở hữu rủi ro và bộ phận đánh giá**, trong đó việc khắc phục phải đi kèm kiểm chứng và cập nhật bằng chứng.
