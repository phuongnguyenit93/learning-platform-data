# Rủi ro tích lũy trong đánh giá và bảo đảm an toàn thông tin

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **rủi ro tích lũy** (*accumulated / cumulative risk*) là gì, vì sao nhiều rủi ro nhỏ, ngoại lệ kéo dài hoặc sự phụ thuộc chung có thể dẫn tới mức phơi lộ đáng kể.
- Phân biệt **tích lũy theo thời gian**, **tổng hợp danh mục rủi ro**, **rủi ro tương quan**, **rủi ro tập trung** và **rủi ro dây chuyền**; nhận diện khi nào các cơ chế này xảy ra đồng thời.
- Xây dựng kịch bản từ tài sản, luồng dữ liệu, trust boundary, điểm yếu và phụ thuộc; đánh giá hiệu lực control ở cấp **toàn hệ thống**, không chỉ từng thành phần.
- Nhận biết giới hạn của việc cộng các risk score theo thang thứ bậc; sử dụng một số công thức xác suất có điều kiện khi các giả định phù hợp.
- Thu thập **bằng chứng** để kiểm chứng mức phơi lộ, mối quan hệ phụ thuộc, khả năng phát hiện, khắc phục và mức rủi ro còn lại.
- Xây dựng kế hoạch theo dõi, giảm thiểu và đánh giá lại rủi ro tích lũy trong quá trình phát triển, triển khai và vận hành.

## 1. Rủi ro tích lũy là gì?

**Rủi ro tích lũy** là tình trạng mức phơi lộ hoặc hậu quả rủi ro **gia tăng, chồng lấp hoặc biến đổi** khi các nguồn rủi ro cùng tồn tại, cùng ảnh hưởng một mục tiêu/tài sản, kéo dài qua nhiều khoảng thời gian, hoặc phụ thuộc vào những thành phần và biện pháp kiểm soát chung. Trong thực hành, thuật ngữ này không chỉ một phép cộng số học cố định; cần mô tả rõ **đang tích lũy yếu tố nào và theo cơ chế nào**.

Ví dụ: một dịch vụ thanh toán có ba vấn đề riêng:

1. Quyền IAM của workload rộng hơn nhu cầu thực tế.
2. Một endpoint xuất dữ liệu kiểm tra quyền thiếu nhất quán.
3. Cảnh báo truy cập dữ liệu bất thường không hoạt động do mất log.

Mỗi vấn đề có thể được đánh giá riêng. Khi cùng tồn tại, chúng có thể tạo điều kiện cho một sự kiện **truy cập rộng, tải dữ liệu hàng loạt và không bị phát hiện kịp thời**. Tác động thực tế có thể lớn hơn nhận định thu được nếu chỉ đánh giá ba ticket độc lập.

Trong module **SECURITY_SECURITY_ASSURANCE**, mục đích của đánh giá rủi ro không dừng ở một con số. Tổ chức phải xây dựng **lập luận có bằng chứng** rằng những mục tiêu bảo mật được đáp ứng: từ phân tích rủi ro, yêu cầu, security controls đến kiểm thử, audit, ghi nhận phát hiện và khắc phục. Rủi ro tích lũy đặc biệt quan trọng vì **control đơn lẻ đạt** chưa đủ bảo đảm **mục tiêu toàn hệ thống đạt**.

### Phân biệt các khái niệm gần nhau

| Khái niệm | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **Rủi ro riêng lẻ** (*individual risk*) | Kịch bản gây hại cụ thể là gì? | Endpoint A cho phép user đọc tài liệu tenant khác. |
| **Rủi ro tích lũy theo thời gian** | Mức phơi lộ thay đổi thế nào khi thiếu hụt kéo dài hoặc lặp lại? | Quyền tạm thời tồn tại nhiều tháng, qua nhiều đợt deploy. |
| **Rủi ro tổng hợp** (*aggregate / portfolio risk*) | Nhiều kịch bản cùng tác động đến mục tiêu/tài sản nào? | Các đường đọc, export và backup đều có thể làm lộ một tập dữ liệu. |
| **Rủi ro tương quan** | Những kịch bản nào cùng tăng/giảm do một nguyên nhân? | Cùng một IAM role quá rộng được dùng ở nhiều service. |
| **Rủi ro tập trung** (*concentration risk*) | Một thành phần chung thất bại ảnh hưởng bao nhiêu hệ thống? | Một identity provider hoặc secret manager phục vụ tất cả dịch vụ. |
| **Rủi ro dây chuyền** (*cascading risk*) | Một sự cố có tạo thêm các sự cố nối tiếp không? | CI bị chiếm → artifact bị sửa → nhiều workload triển khai mã độc. |
| **Rủi ro còn lại** (*residual risk*) | Sau khi control được triển khai và kiểm chứng, phần rủi ro nào còn tồn tại? | Còn khả năng bị lạm dụng tài khoản có quyền hợp lệ. |

**Không đồng nhất rủi ro tích lũy với “số lượng lỗ hổng”.** Một rủi ro tập trung nghiêm trọng có thể quan trọng hơn hàng trăm cảnh báo nhẹ; nhiều cảnh báo có thể cùng mô tả một nguyên nhân hoặc một hậu quả nên không được đếm hai lần.

## 2. Những cơ chế khiến rủi ro tích lũy

### 2.1. Tăng mức phơi lộ theo thời gian

Một thiếu hụt bảo mật chưa được khắc phục tiếp tục tồn tại qua các chu kỳ vận hành. Trong thời gian đó có thể xuất hiện thêm tài sản, tài khoản, khách hàng, đường truy cập hoặc mối đe dọa mới.

Ví dụ: một tài khoản quản trị được cấp quyền “tạm thời” để xử lý sự cố nhưng không được thu hồi. Sau nhiều tháng, tài khoản có thể tồn tại trong backup cấu hình, script và quy trình của nhiều đội. Lỗ hổng ban đầu không nhất thiết trở nên dễ khai thác hơn theo cấp số nhân, nhưng **cửa sổ phơi lộ** và số nguồn phụ thuộc có thể tăng.

Cần ghi rõ **ngày phát hiện, ngày bắt đầu phơi lộ nếu biết, ngày đánh giá, ngày dự kiến xử lý, thay đổi trong thời gian mở**. Không nên suy ra chính xác xác suất tích lũy chỉ từ số ngày ticket tồn tại nếu thiếu dữ liệu về tần suất sự kiện.

### 2.2. Nhiều đường tấn công dẫn tới cùng một hậu quả

Một mục tiêu có thể thất bại qua nhiều con đường: API công khai, nội bộ, export, sao lưu, bản sao dữ liệu, token bị lộ, quản trị viên hoặc bên thứ ba.

~~~mermaid
flowchart LR
    A["API đọc thiếu authorization"] --> X["Lộ dữ liệu khách hàng"]
    B["Export endpoint không giới hạn tenant"] --> X
    C["Storage bucket mở sai quyền"] --> X
    D["Backup chứa dữ liệu không được bảo vệ"] --> X
~~~

Ngay cả khi sửa một đường, các đường khác vẫn có thể tạo ra cùng hậu quả. Khi kết luận “mục tiêu bảo mật được đáp ứng”, cần đánh giá **tất cả đường trọng yếu trong phạm vi claim**, thay vì chỉ kiểm chứng endpoint có báo cáo.

### 2.3. Cộng hưởng giữa các điểm yếu

Có trường hợp một điểm yếu chưa đủ gây hậu quả nghiêm trọng nhưng trở nên nguy hiểm khi kết hợp với điểm yếu khác. Ví dụ:

- **A:** token chỉ được bảo vệ bằng một secret dùng chung, đã bị lộ trong log.
- **B:** dịch vụ chấp nhận token có claim quyền cao mà không xác minh đầy đủ nguồn phát hành.
- **C:** quyền truy cập storage của dịch vụ rộng hơn phạm vi dữ liệu cần xử lý.

Một kẻ tấn công có thể phải kết hợp A, B và C để mở đường lấy dữ liệu. Cách xử lý chỉ giảm một vấn đề nhưng không kiểm tra lại attack path có thể bỏ sót biến thể khác. Mặt khác, nếu có **biện pháp chặn độc lập, được kiểm chứng**, chuỗi tấn công có thể bị ngắt dù vẫn còn một thiếu hụt ở thành phần khác.

### 2.4. Phụ thuộc và nguyên nhân chung

Khi nhiều service dùng chung control hoặc hạ tầng, một lỗi có thể làm suy giảm đồng thời nhiều bảo vệ. Các nguồn chung thường là:

- Identity provider, IAM role, thiết bị ký hoặc kho khóa/secret.
- API gateway, WAF, hệ thống DNS, proxy hoặc service mesh.
- CI/CD runner, artifact registry, base image, thư viện dùng chung.
- Hệ thống logging, cảnh báo, backup, restore và dịch vụ cấp thời gian.
- Nhà cung cấp cloud, khu vực triển khai, network path hoặc đội ngũ có quyền quản trị.

Một dashboard với **10 service đều có điểm rủi ro “Medium”** không thể hiện đầy đủ sự thật nếu tất cả dựa vào một IAM credential duy nhất. Khi credential đó lộ, hậu quả có thể diễn ra **đồng thời**; các sự kiện này không độc lập.

### 2.5. Khuếch đại tác động và chuỗi sự cố

Sự cố ban đầu có thể làm mất nhiều mục tiêu: chiếm CI pipeline làm sai artifact, artifact độc hại làm lộ khóa, khóa bị lộ giúp xóa backup, mất backup làm tăng tác động ransomware. Lúc này tổ chức phải đánh giá **kịch bản dây chuyền** với tác động cuối cùng, không chỉ cộng tác động của từng bước.

## 3. Mô tả risk scenario để không đếm trùng

Đánh giá tích lũy tốt cần các **kịch bản rõ ràng**, có cùng kỳ đánh giá và ranh giới tài sản nhất quán.

Mỗi risk scenario nên trả lời:

1. **Tài sản/mục tiêu:** dữ liệu, tính sẵn sàng, tài chính, quyền riêng tư hoặc an toàn.
2. **Tác nhân hoặc sự kiện:** ai/cái gì gây tác động, chủ ý hay vô tình.
3. **Điều kiện và điểm yếu:** quyền, cấu hình, dependency, đường truy cập, thiếu kiểm tra.
4. **Chuỗi sự kiện:** những bước nào cần xảy ra hoặc những đường thay thế nào có thể dẫn tới hậu quả.
5. **Phạm vi và thời gian:** service, tenant, môi trường, version, khu vực, kỳ đánh giá.
6. **Hậu quả:** dữ liệu/khả năng nào bị ảnh hưởng và quan hệ với các risk scenario khác.
7. **Control và bằng chứng hiện có:** kiểm soát nào đang chặn/giảm hậu quả, hiệu lực đã được kiểm chứng ra sao.
8. **Bất định và giả định:** điều chưa biết, nguồn số liệu, giới hạn của đánh giá.

Ví dụ:

| ID | Kịch bản | Hậu quả | Quan hệ |
| --- | --- | --- | --- |
| R-01 | API export thiếu kiểm tra quyền cấp đối tượng | Lộ báo cáo qua export | Có thể cùng hậu quả với R-02 |
| R-02 | Object storage policy cho phép tải từ identity quá rộng | Lộ cùng báo cáo qua bucket | Cùng mục tiêu dữ liệu với R-01 |
| R-03 | Pipeline kiểm tra hành vi tải bất thường bị ngắt | Không phát hiện/tăng thời gian xử lý lộ dữ liệu | **Khuếch đại** tác động của R-01, R-02 |
| R-04 | CI secret được dùng chung bởi nhiều service | Nếu bị chiếm, nhiều service mất tính toàn vẹn | Phụ thuộc/nguồn chung, tác động rộng |

Không cộng bốn risk score để tạo “total score”. Nếu R-01 và R-02 cùng cho khả năng rò **cùng một tập dữ liệu**, việc cộng nguyên vẹn tổn thất của hai kịch bản có thể **đếm trùng hậu quả**; nếu R-03 làm tăng thời gian bị khai thác mà không phát hiện, bỏ qua nó lại **đánh giá thiếu** tác động.

### Sơ đồ phụ thuộc để review

~~~mermaid
flowchart TD
    ID["Identity provider / IAM"] --> S1["Service A"]
    ID --> S2["Service B"]
    CI["CI/CD và artifact registry"] --> S1
    CI --> S2
    S1 --> DB["Dữ liệu khách hàng"]
    S2 --> DB
    LOG["Log collector chung"] -. "Giám sát" .-> S1
    LOG -. "Giám sát" .-> S2
    DB --> OUT["Mục tiêu: bảo vệ bí mật và toàn vẹn"]
~~~

Khi một node chung gặp sự cố, cần xem **blast radius** (phạm vi ảnh hưởng) đến các service và mục tiêu. Sơ đồ không thay cho kiểm tra cấu hình và quyền thực tế; đó là mô hình giả thuyết cần xác nhận bằng inventory và evidence.

## 4. Có thể tổng hợp điểm rủi ro như thế nào?

Các tổ chức có thể dùng đánh giá định tính, bán định lượng hoặc định lượng. Cần **công bố trước phương pháp và giới hạn**; đừng trộn score từ các thang khác nhau rồi diễn giải như số đo có cùng đơn vị.

### 4.1. Tránh cộng risk score thứ bậc

Trong ma trận 5×5, một điểm thường tính bằng:

\[
\text{Score} = \text{Likelihood}_{1..5}\times\text{Impact}_{1..5}
\]

Ví dụ: R-01 có \`L=4, I=4, score=16\`; R-02 có \`L=3, I=4, score=12\`. **Không thể kết luận “tổng rủi ro = 28/25”**. Các mức L/I là bậc đánh giá, không phải xác suất hay thiệt hại tuyệt đối; hai rủi ro có thể chia sẻ hậu quả, đường khai thác hoặc control.

Các lựa chọn minh bạch hơn:

- Giữ **score từng kịch bản** và xếp ưu tiên theo chính sách.
- Nhóm kịch bản theo **cùng tài sản, mục tiêu hoặc nguyên nhân**; vẽ dependency/attack path.
- Tạo **kịch bản tổng hợp** (ví dụ “nhiều đường gây lộ dữ liệu tenant”) rồi chấm L/I của kịch bản tổng hợp **một lần** theo rubric.
- Ghi rõ các **rủi ro tập trung** và tình huống tác động thảm họa cần chuyển cấp ngoài ngưỡng ma trận.
- Khi dữ liệu và mô hình cho phép, sử dụng định lượng có xét quan hệ phụ thuộc và tránh đếm trùng.

Không dùng \`MAX(score)\` như một “tổng rủi ro” phổ quát; mức cao nhất có thể hữu ích cho **sàng lọc ban đầu**, nhưng bỏ qua số lượng đường tấn công hoặc tác động chung.

### 4.2. Xác suất nhiều sự kiện: công thức chỉ đúng khi đủ giả định

Nếu các sự kiện \(E_1,\ldots,E_n\) có xác suất tương ứng \(p_1,\ldots,p_n\), **độc lập** và cùng nằm trong một kỳ đánh giá, xác suất **ít nhất một sự kiện** xảy ra là:

\[
P(E_1\cup\cdots\cup E_n)=1-\prod_{i=1}^{n}(1-p_i)
\]

Minh họa: giả sử có **10 đường gây lỗi độc lập**, mỗi đường có xác suất tạo ra sự kiện gây hại 2% trong cùng một năm (giả định dùng để giải thích, **không phải số liệu thực**):

\[
P(\text{ít nhất một sự kiện})=1-0.98^{10}\approx18.3\%
\]

Một sự kiện riêng có 2%, nhưng sự tồn tại của nhiều đường độc lập làm tăng xác suất xuất hiện **ít nhất một** sự kiện. Tuy nhiên, nếu các đường có chung IAM role, chung dữ liệu hoặc kẻ tấn công, chúng **không độc lập**. Khi đó công thức trên có thể cho kết quả sai; cần mô hình tương quan, phân tích nguyên nhân chung hoặc giới hạn xác suất phù hợp dữ liệu.

Với hai sự kiện bất kỳ:

\[
P(A\cup B)=P(A)+P(B)-P(A\cap B)
\]

Phần giao \(P(A\cap B)\) cần được tính hoặc ước lượng có căn cứ để không đếm trùng.

### 4.3. Tích lũy theo thời gian

Giả sử cùng một loại sự kiện có xác suất \(p\) trong **mỗi chu kỳ không chồng lấp**, các chu kỳ là độc lập và \(p\) giữ ổn định. Xác suất **ít nhất một sự kiện trong \(n\) chu kỳ** là:

\[
P(\text{ít nhất một trong n chu kỳ})=1-(1-p)^n
\]

Ví dụ *minh họa về toán học*: nếu xác suất một sự kiện trong một lần thay đổi là 5%, qua sáu lần thay đổi độc lập thì \(1-0.95^6\approx26.5\%\).

Đây **không** phải công thức để tự động biến “ticket mở sáu tháng” thành phần trăm chính xác: thay đổi/tấn công thực tế có thể không độc lập, xác suất không ổn định, control và phạm vi có thể thay đổi, và một sự kiện có thể xảy ra nhiều lần.

### 4.4. Thiệt hại kỳ vọng và vấn đề phụ thuộc

Với một biến tổn thất \(L\) được xác định rõ (ví dụ tiền thiệt hại trong năm), giá trị kỳ vọng \(E[L]\) có thể sử dụng trong mô hình định lượng phù hợp. Tính tuyến tính của kỳ vọng cho phép:

\[
E[L_1+\cdots+L_n]=E[L_1]+\cdots+E[L_n]
\]

**Ngay cả khi các biến phụ thuộc**, điều này đúng về mặt toán học, *nếu* \(L_i\) là các thành phần tổn thất **không bị đếm trùng** của tổng đang xét. Nhưng mức thiệt hại cực đoan, xác suất vượt ngưỡng, phân phối tổn thất và rủi ro tập trung **phụ thuộc mạnh vào tương quan**. Không cộng “ước tính thiệt hại toàn phần” của nhiều kịch bản cùng làm mất một cơ sở dữ liệu rồi coi đó là tổn thất thực.

Dữ liệu thiếu, phân phối có đuôi dày và những biến cố hiếm khiến kết quả định lượng bất định; cần ghi giả định, kịch bản xấu và độ nhạy thay vì công bố một con số duy nhất như sự thật chắc chắn.

## 5. Risk register thể hiện rủi ro tích lũy thế nào?

Một risk register chỉ liệt kê score, owner và deadline có thể bỏ sót quan hệ chung. Nên có thêm thông tin để review ở cấp hệ thống và danh mục:

| Trường | Nội dung |
| --- | --- |
| Risk ID / scenario | Kịch bản cụ thể và nguồn gây hại |
| Objective / asset | Mục tiêu, dữ liệu hoặc năng lực bị ảnh hưởng |
| Scope / period | Service, môi trường, version, kỳ đánh giá |
| Likelihood / impact | Rubric và lập luận cho mức đánh giá |
| Common dependency | IAM, CI, logging, key service, database, nhà cung cấp chung |
| Related risk IDs | Các đường thay thế, điều kiện kết hợp, chung hậu quả |
| Control IDs / status | Biện pháp phòng ngừa, phát hiện, ứng phó; hiệu lực đã được test chưa |
| Evidence refs | Kết quả test, cấu hình thực tế, audit, incident, change, deployment |
| Exposure start / age | Thời điểm bắt đầu thiếu hụt, thời gian tồn tại (nếu có căn cứ) |
| Residual risk / confidence | Rủi ro còn lại và độ tin cậy; giới hạn đánh giá |
| Owner / treatment | Người chịu trách nhiệm, kế hoạch khắc phục, ngoại lệ và cấp phê duyệt |
| Review triggers | Thay đổi cấu hình, quyền, dependency, sự cố, thời hạn hoặc audit |

Có thể gắn **risk cluster ID** cho các rủi ro chia sẻ một tài sản hoặc nguyên nhân, ví dụ \`CLUSTER-TENANT-ISOLATION\`, để chạy truy vấn và đánh giá chúng cùng nhau.

### Mẫu hồ sơ nhóm rủi ro

Các giá trị trong dấu \`<...>\` dưới đây là placeholder, không phải kết quả kiểm chứng thực tế:

~~~yaml
cluster_id: CLUSTER-CUSTOMER-DATA-01
objective: "Ngăn đọc trái phép dữ liệu khách hàng"
scope:
  services: ["report-service", "export-worker", "storage"]
  environment: production
  assessment_period: "<ASSESSMENT_PERIOD>"
shared_assets:
  - "customer-report-data"
shared_dependencies:
  - "workload-identity-role"
  - "central-log-collector"
related_risks:
  - R-01
  - R-02
  - R-03
scenarios:
  alternative_paths:
    - "API export thiếu authorization"
    - "Storage policy cấp quyền quá rộng"
  impact_amplifier:
    - "Mất khả năng phát hiện tải dữ liệu bất thường"
aggregation_method: "scenario-based, reviewed; ordinal scores not summed"
control_refs:
  - CTRL-AUTHZ-01
  - CTRL-IAM-01
  - CTRL-LOG-01
evidence_refs:
  - "<NEGATIVE_AUTHZ_TEST>"
  - "<ACTUAL_IAM_POLICY_SNAPSHOT>"
  - "<LOG_END_TO_END_TEST>"
  - "<DEPLOYMENT_AND_BUILD_REFERENCES>"
residual_assessment: "<RATIONALE_AND_STATUS>"
confidence: "<HIGH_MEDIUM_LOW_WITH_REASON>"
owner: "<RISK_OWNER>"
reviewer: "<ASSESSOR>"
last_reviewed_at: "<ISO_8601_UTC>"
review_triggers:
  - "Thay đổi quyền IAM hoặc luồng dữ liệu"
  - "Log collector không nhận đủ event"
  - "Xuất hiện incident hoặc phát hiện mới"
limitations: "<UNTESTED_PATHS_OR_UNCERTAINTIES>"
~~~

Không có trường \`aggregate_score\` tự động vì chưa có phương pháp đáng tin để suy ra. Nếu tổ chức công bố một chỉ số danh mục, phải nêu **đơn vị, trọng số, nguồn dữ liệu, cách xử lý tương quan và ý nghĩa ra quyết định**.

## 6. Ví dụ hệ thống Java: nhiều thiếu hụt cùng dẫn tới lộ dữ liệu

**Bối cảnh:** nền tảng phục vụ doanh nghiệp gồm:

- \`report-api\`: Spring Boot API đọc và xuất báo cáo theo tenant.
- \`export-worker\`: nhận yêu cầu xuất file bất đồng bộ qua queue.
- \`object-storage\`: lưu file CSV tạm thời.
- Identity provider và IAM role dùng chung.
- Central logging phục vụ kiểm toán và phát hiện tải dữ liệu bất thường.

### Phát hiện ban đầu

| Finding | Vấn đề | Nếu đánh giá riêng |
| --- | --- | --- |
| **F-01** | \`report-api\` kiểm tra role USER nhưng chưa xác minh tenant của report ở tuyến export | Đường tải dữ liệu trái phép qua API |
| **F-02** | \`export-worker\` dùng service account có quyền đọc nhiều bucket ngoài phạm vi | Tăng phạm vi dữ liệu có thể truy xuất khi workload bị lạm dụng |
| **F-03** | Kết quả upload CSV tồn tại quá lâu hoặc URL tải không gắn quyền truy cập đúng | Tạo thêm đường lộ cùng báo cáo |
| **F-04** | Log của event export không tới bộ thu tập trung trong một số deployment | Thiếu quan sát và phát hiện chậm |
| **F-05** | Quyền khẩn cấp đã cấp trước đó chưa thu hồi | Mở thêm đường truy cập có quyền cao |

Nếu mỗi nhóm chỉ nhận ticket thuộc service của mình, không ai nhất thiết xem được **toàn bộ đường dữ liệu và các control chung**.

### Phân tích chuỗi sự kiện

~~~mermaid
flowchart TD
    U["User ngoài tenant / credential bị lạm dụng"] --> A["API export kiểm tra quyền thiếu"]
    A --> Q["Queue yêu cầu tạo CSV"]
    Q --> W["Export worker với IAM quyền rộng"]
    W --> S["CSV trong object storage"]
    S --> X["Tải hoặc chia sẻ ngoài phạm vi"]
    X --> LOSS["Lộ báo cáo khách hàng"]
    LOG["Log pipeline bị lỗi"] -. "Giảm khả năng phát hiện và khoanh vùng" .-> LOSS
    IAM["Quyền khẩn cấp chưa thu hồi"] -. "Tạo đường truy cập thay thế" .-> S
~~~

Một phương án điều tra:

1. Xác định những **đường có thể tạo cùng hậu quả**: API, queue/job ID, storage URL, quyền direct bucket, đường admin.
2. Kiểm tra **phụ thuộc chung**: IAM role của worker, quyền ký URL, dịch vụ cấp token, log collector và CI pipeline.
3. Xác định **điều kiện kết hợp**: việc thay report ID có đủ tạo được CSV không, hoặc còn yêu cầu token/job ownership nào khác?
4. Xác định **control bù trừ có thật**: gateway policy, giới hạn quyền bucket, thời hạn URL, audit log và phát hiện tự động.
5. Đánh giá kịch bản lộ dữ liệu **toàn hệ thống**, cùng mức tác động và độ phơi lộ theo đúng trạng thái đã kiểm chứng.
6. Liệt kê phần **chưa kiểm chứng** để không hạ residual risk chỉ dựa trên kỳ vọng.

### Thiết kế phương án giảm rủi ro

| Control | Trách nhiệm chính (minh họa) | Tiêu chí kiểm chứng |
| --- | --- | --- |
| Kiểm tra quyền theo tenant và resource ở API và worker | Developer, Service Owner | User tenant A không thể tạo hoặc nhận file của tenant B, kể cả job ID bị thay |
| Giới hạn quyền workload và phân tách bucket | Platform/Ops với Developer | Effective IAM permission chỉ cho phép truy cập tài nguyên được giao; test quyền từ chối |
| Tạo URL tải ngắn hạn, ràng buộc người nhận và phạm vi | Developer với Platform | Link không hợp lệ/đã hết hạn/bị dùng sai ngữ cảnh bị từ chối theo thiết kế |
| Bảo vệ và dọn CSV tạm thời | Developer, Ops | Truy vấn trạng thái lưu giữ, xóa theo policy, audit được hoạt động dọn dẹp |
| Log đầy đủ và phát hiện hành vi xuất bất thường | Security Operations, Ops, Developer | Kiểm thử end-to-end từ event export thử tới rule, alert và người xử lý |
| Thu hồi quyền khẩn cấp, review thay đổi | Ops / IAM | Permission snapshot, log cấp/thu hồi, review quyền |
| Xác nhận phiên bản đã sửa ở production | Release/Platform cùng Developer | Commit/test result gắn với image digest, deployment và runtime config |

**Điểm cốt lõi:** test API từ chối sai tenant là cần thiết nhưng chưa đủ nếu URL tải CSV trực tiếp vẫn công khai hoặc IAM của worker vẫn cho truy cập ngoài phạm vi. Ngược lại, một rule logging đạt không sửa được đường lộ; nó có thể giúp giảm thời gian phát hiện và tác động nếu quy trình phản ứng cũng được kiểm chứng.

## 7. Bằng chứng cần thu thập để đánh giá rủi ro tích lũy

Trong security assurance, **bằng chứng (evidence)** phục vụ một **khẳng định (claim)** cụ thể. Với rủi ro tích lũy, claim thường liên quan **nhiều control và đường tấn công**, nên cần bằng chứng của cả **từng control** và **sự phối hợp giữa chúng**.

| Mục tiêu đánh giá | Bằng chứng trực tiếp phù hợp | Điều chưa được chứng minh chỉ từ bằng chứng đó |
| --- | --- | --- |
| Mọi đường export áp dụng authorization | Integration/end-to-end tests theo tenant, loại action, job ID và link tải | Các đường chưa nằm trong test hoặc bản production khác phiên bản |
| IAM role không vượt quyền cần thiết | Policy thực tế và kết quả thử quyền cho phép/từ chối | Không có đường cấp quyền gián tiếp qua role khác hoặc dịch vụ phụ |
| Log và cảnh báo hoạt động xuyên tuyến | Event thử, collector event ID, kết quả rule, alert tới đúng on-call | Không có khoảng trống telemetry khác hoặc cấu hình sẽ giữ nguyên về sau |
| Tài nguyên tạm không bị lộ kéo dài | Cấu hình TTL, test hết hạn, kết quả quét storage có phạm vi và thời gian | Toàn bộ bản sao dữ liệu trong hệ thống khác cũng đã xóa |
| Chỉnh sửa đã tới production | Commit, build ID, image digest, deployment ID, runtime check | Không có regression ở luồng khác |
| Khắc phục finding có hiệu quả | Test tái hiện trước sửa, test pass sau sửa, review và kết quả retest | Mọi biến thể của cùng loại lỗ hổng đã bị loại trừ |

### “Một lần test pass” và “assurance liên tục”

Một điểm yếu có thể biến mất trong build mới rồi xuất hiện lại do thay đổi policy, migration hoặc rollback. Nên thu thập bằng chứng **có mốc thời gian và phiên bản**, định nghĩa trigger đánh giá lại và xác định người chịu trách nhiệm.

Hồ sơ evidence có thể dùng các trường:

~~~yaml
evidence_id: EV-CUMULATIVE-001
claim_id: CLAIM-CUSTOMER-DATA-01
cluster_id: CLUSTER-CUSTOMER-DATA-01
risk_ids: [R-01, R-02, R-03]
control_ids: [CTRL-AUTHZ-01, CTRL-IAM-01, CTRL-LOG-01]
environment: production
service_versions: "<REVIEWED_VERSIONS_AND_DIGESTS>"
assessment_window: "<START_AND_END>"
method: "Cross-service authorization, IAM and logging verification"
artifact_refs:
  - "<CI_NEGATIVE_TEST_REPORT>"
  - "<RUNTIME_POLICY_SNAPSHOT>"
  - "<CONTROLLED_END_TO_END_EVENT_AND_ALERT>"
  - "<PRODUCTION_DEPLOYMENT_RECORD>"
result: "<PASS_FAIL_INCONCLUSIVE>"
evidence_owner: "<OWNER>"
independent_reviewer: "<REVIEWER>"
limitations: "<KNOWN_GAPS>"
reassessment_trigger: "<CONDITION_OR_DATE>"
~~~

**Không coi YAML mẫu hoặc screenshot dashboard là bằng chứng đã đủ.** Khi audit, assessor cần đối chiếu hiện vật gốc, nguồn tạo, phiên bản, phạm vi, thời gian, kết quả, giới hạn và dấu vết review. Bằng chứng chứa dữ liệu nhạy cảm phải được kiểm soát truy cập, bảo quản và che thông tin phù hợp.

## 8. Đánh giá risk score khi các rủi ro có mối quan hệ

### Bước 1: Đánh giá riêng từng kịch bản

Chọn phương pháp chấm điểm thống nhất (ví dụ likelihood 1–5 và impact 1–5), ghi **rationale**. Risk score 5×5 là công cụ bán định lượng; mức 4 không đồng nghĩa xác suất 80%, mức 20 không có nghĩa thiệt hại gấp đôi mức 10.

### Bước 2: Xác định quan hệ

| Quan hệ | Câu hỏi |
| --- | --- |
| **Đường thay thế (OR)** | Chỉ một trong nhiều đường đã đủ gây hậu quả chưa? |
| **Điều kiện kết hợp (AND)** | Có cần đồng thời những điều kiện nào để gây hậu quả? |
| **Nguyên nhân chung** | Các kịch bản có cùng khóa, quyền, hệ thống log, thư viện, nhà cung cấp hay nhóm vận hành không? |
| **Khuếch đại tác động** | Control phát hiện/khôi phục thất bại có thể làm tăng thời gian và phạm vi hậu quả không? |
| **Thứ tự thời gian** | Một sự cố có tạo điều kiện cho sự cố kế tiếp hoặc làm giảm khả năng phục hồi không? |

### Bước 3: Đánh giá kịch bản tổng hợp

Ví dụ, sau khi kiểm tra đường API, storage và IAM, assessor đưa ra một kịch bản tổng hợp: “Người dùng hoặc workload trái phép có thể lấy dữ liệu khách hàng qua ít nhất một đường trong chuỗi export; hoạt động này có thể kéo dài do logging thiếu”. Đánh giá likelihood/impact cho **toàn kịch bản tổng hợp**, với bằng chứng hỗ trợ và những điều kiện chưa rõ, thay vì cộng 5 số score.

### Bước 4: Đánh giá residual risk có căn cứ

Giả sử đã sửa và kiểm chứng authorization, IAM, URL, TTL, logging trên đúng deployment. Có thể **xem xét** giảm likelihood hoặc impact nếu control thực tế làm thay đổi kịch bản; mức giảm phải được giải thích. Nếu mới merge PR nhưng chưa triển khai và test, cần ghi là **mức kỳ vọng sau xử lý**, chưa phải residual đã được chứng minh.

### Bước 5: Quyết định theo risk appetite và quyền hạn

Nếu rủi ro tổng hợp còn cao hoặc có hậu quả cực lớn, chuyển cấp theo chính sách; xác định biện pháp xử lý, owner, deadline và điều kiện review. Ngoại lệ đã phê duyệt chỉ là **quyết định chấp nhận rủi ro**, không làm control không đạt biến thành đạt.

## 9. Ví dụ Java 17: minh họa phép tính xác suất có điều kiện

Đoạn code sau minh họa **phần toán học** để người học thấy hiệu ứng “nhiều cơ hội xảy ra”. **Nó không tự suy ra rủi ro thật từ số endpoint, số CVE hoặc số ticket**. Chỉ dùng phép tính khi đầu vào là xác suất được ước lượng có căn cứ và giả định độc lập/đồng nhất phù hợp.

~~~java
import java.util.List;

public final class CumulativeProbabilityExample {
    // Ít nhất một sự kiện trong các sự kiện độc lập.
    static double anyIndependentEvent(List<Double> probabilities) {
        double probabilityNone = 1.0;
        for (double p : probabilities) {
            if (!Double.isFinite(p) || p < 0.0 || p > 1.0) {
                throw new IllegalArgumentException("p phải thuộc [0, 1]");
            }
            probabilityNone *= (1.0 - p);
        }
        return 1.0 - probabilityNone;
    }

    // Lặp n chu kỳ độc lập, cùng xác suất p và cùng định nghĩa sự kiện.
    static double repeatedIndependentPeriods(double p, int periods) {
        if (!Double.isFinite(p) || p < 0.0 || p > 1.0 || periods < 0) {
            throw new IllegalArgumentException("Dữ liệu đầu vào không hợp lệ");
        }
        return 1.0 - Math.pow(1.0 - p, periods);
    }

    public static void main(String[] args) {
        double tenPaths = anyIndependentEvent(
                List.of(0.02, 0.02, 0.02, 0.02, 0.02,
                        0.02, 0.02, 0.02, 0.02, 0.02));
        double sixPeriods = repeatedIndependentPeriods(0.05, 6);

        System.out.printf("Mười đường độc lập: %.1f%%%n", 100.0 * tenPaths);
        System.out.printf("Sáu chu kỳ độc lập: %.1f%%%n", 100.0 * sixPeriods);
        // Khoảng 18.3% và 26.5% (giả định minh họa).
    }
}
~~~

Để mở rộng thành mô hình thực tế, cần có **dữ liệu hiệu chuẩn, định nghĩa tập sự kiện, xác suất có điều kiện, phụ thuộc giữa kịch bản, khoảng tin cậy và phân tích độ nhạy**. Nếu thiếu các điều kiện đó, một cách đánh giá định tính có tài liệu tốt thường đáng tin hơn một con số “chính xác đến hai chữ số” nhưng giả định sai.

## 10. Quản trị danh mục rủi ro: tránh thiếu sót và trùng lặp

Đánh giá tổng hợp đòi hỏi **giao trách nhiệm xuyên hệ thống**:

| Vai trò (tham khảo) | Trách nhiệm trọng tâm |
| --- | --- |
| **Risk owner** | Chịu trách nhiệm quyết định xử lý/chấp nhận rủi ro theo thẩm quyền; xem rủi ro cấp dịch vụ hoặc danh mục |
| **Service Owner / Tech Lead** | Mô tả tài sản, luồng dữ liệu, dependency và ảnh hưởng giữa các service |
| **Developer** | Sửa control ứng dụng, xây dựng negative/regression tests, cung cấp commit và test evidence |
| **Ops / SRE / Platform** | Kiểm tra quyền/cấu hình runtime, IAM, deployment, logging, backup, drift và hiện vật vận hành |
| **Security / AppSec / SOC** | Hướng dẫn phương pháp, phân tích attack path, review control và phát hiện/ứng cứu |
| **Assessor / Audit** | Kiểm tra bằng chứng và kết luận theo thẩm quyền, độc lập khi yêu cầu |
| **Lãnh đạo/chủ sở hữu nghiệp vụ** | Xác định risk tolerance, ưu tiên nguồn lực, quyết định với rủi ro vượt thẩm quyền các nhóm kỹ thuật |

Những rủi ro cùng chia sẻ một tài sản hoặc control cần có **người điều phối tổng hợp**; không mặc định một ticket do một nhóm sở hữu là “đã xử lý mọi hệ quả”. Ma trận RACI riêng của tổ chức cần nêu ai là **A** (chịu trách nhiệm cuối cùng) cho cluster, ai làm **R** (thực hiện), ai được tham vấn và ai nhận thông báo.

### Khắc phục theo đúng mối quan hệ nguyên nhân

Giả sử ba service cùng dùng chung một secret bị lộ. Tạo ba ticket đổi mật khẩu có thể là cần thiết, nhưng còn phải:

1. Xác định mọi nơi secret được dùng hoặc sao chép (mã, CI, deployment, log, backup).
2. Thu hồi credential cũ và tạo credential mới bằng quy trình quản lý khóa phù hợp.
3. Kiểm tra các quyền phát sinh từ credential và dấu vết lạm dụng trong cửa sổ phơi lộ.
4. Loại bỏ cơ chế tái đưa secret vào log hoặc image; tách identity giữa các service nếu phù hợp.
5. Xác minh từng service hoạt động với credential mới và credential cũ không còn có thể dùng.
6. Đánh giá lại risk cluster trên toàn phạm vi; ghi finding và rủi ro chưa loại trừ.

Chỉ đổi chuỗi secret trong một repository không chứng minh rủi ro tập trung đã được loại bỏ.

## 11. Theo dõi tích lũy rủi ro trong phát triển và vận hành

Một chương trình security assurance liên tục cần các **trigger đánh giá lại**.

| Khi nào | Điều cần đánh giá lại | Bằng chứng quan trọng |
| --- | --- | --- |
| Tính năng mới hoặc thêm endpoint | Đường truy cập chung, data flow, quyền theo đối tượng | Threat model, tests, review |
| Tăng người dùng, dữ liệu, tenant | Phạm vi ảnh hưởng, blast radius và impact | Inventory, phân loại dữ liệu, kiểm tra quyền |
| Chia sẻ IAM role/secret giữa dịch vụ | Rủi ro tập trung, phụ thuộc và khả năng lây lan | Effective IAM policy, secret inventory, test quyền |
| Thay CI, base image, registry | Rủi ro ảnh hưởng hàng loạt tới supply chain | Build provenance, artifact digest, pipeline review |
| Log pipeline bị lỗi | Khả năng phát hiện và thời gian phơi lộ chưa quan sát | Ingestion health, thử event, incident timeline |
| Finding tồn tại quá hạn | Kỳ phơi lộ, thay đổi môi trường, giới hạn ngoại lệ | Finding age, change records, scans và review |
| Bản vá hoặc control được triển khai | Còn đường bypass nào khác, có giảm thật exposure không | Retest, runtime config, deployment ID |
| Sự cố hoặc thông tin đe dọa mới | Likelihood, impact, điều kiện kết hợp và residual risk | Incident evidence, threat model, risk register |
| Sắp audit hoặc ngoại lệ hết hạn | Độ đầy đủ, hiệu lực và lịch sử của evidence | Review decision, audit trail, evidence register |

### Bộ chỉ số nên đi cùng nhau

Có thể theo dõi **số risk cluster có phụ thuộc chung**, số finding chưa khắc phục theo **tuổi** và mức rủi ro, tỷ lệ tài sản có owner, tỷ lệ control quan trọng có test end-to-end còn hiệu lực, số ngoại lệ quá hạn, số deployment thay đổi ranh giới tin cậy chưa được review, tỷ lệ log nguồn quan trọng đạt coverage và thời gian phát hiện/khắc phục.

Các chỉ số trên là **tín hiệu quản trị**, không phải một phép tính “tổng rủi ro” tự động. Đếm số finding có thể tăng chỉ vì chất lượng phát hiện được cải thiện; số ticket đóng có thể tăng dù kịch bản chung vẫn chưa được chặn. Luôn phân tích xu hướng cùng **mức phơi lộ, chất lượng bằng chứng và thay đổi control**.

## 12. Bài thực hành: nhận diện nguyên nhân chung trong CI/CD

**Tình huống:** tổ chức có bốn dịch vụ Spring Boot chạy ở các namespace khác nhau. Cả bốn được build bằng cùng một runner CI có quyền push artifact và triển khai production. Một token truy cập artifact registry được lưu dưới dạng biến môi trường chung, có quyền ghi vào mọi repository image. Gần đây nhóm phát hiện token đã xuất hiện trong log của một job; mỗi service có một ticket riêng mức Medium. Chưa có bằng chứng token bị dùng trái phép.

Hãy thực hiện:

1. Mô tả **một risk scenario tổng hợp** và phân biệt nó với bốn ticket riêng.
2. Chỉ ra những **phụ thuộc và nguyên nhân chung** cùng các đường có thể dẫn tới sửa artifact hoặc triển khai ngoài dự kiến.
3. Những khẳng định nào có thể đưa ra khi chưa có log sử dụng token đầy đủ? Vì sao “không thấy bị khai thác” chưa đủ?
4. Đề xuất control giúp giảm rủi ro **tập trung**, không chỉ đổi token.
5. Lập danh sách bằng chứng và tiêu chí kiểm tra để xem rủi ro còn lại đã thực sự giảm chưa.
6. Phân công người chịu trách nhiệm xuyên bốn dịch vụ và xác định trigger đánh giá lại.

### Lời giải định hướng

| Vấn đề | Phân tích |
| --- | --- |
| **Risk scenario** | Nếu credential CI bị lộ và được sử dụng trái phép, attacker có thể sửa hoặc phát hành artifact cho nhiều service, gây mất tính toàn vẹn và hậu quả dây chuyền trên production. |
| **Nguyên nhân chung** | Runner/credential/pipeline và quyền artifact registry chia sẻ; cần biết runner có quyền deploy tới tất cả namespace không và những phê duyệt nào thực sự được thực thi. |
| **Giới hạn bằng chứng** | Log chưa đủ không chứng minh đã có hoặc không có lạm dụng; phải điều tra cửa sổ phơi lộ và ghi rõ điều chưa quan sát được. |
| **Giảm thiểu** | Thu hồi token cũ, loại bỏ secret khỏi log, cấp credential ngắn hạn hoặc danh tính workload phù hợp, phân quyền theo repository/service, tách quyền push và deploy, kiểm soát artifact provenance và phê duyệt quan trọng. |
| **Kiểm tra** | Xác minh token cũ bị từ chối, secret không còn xuất trong log, quyền mới chỉ thao tác đúng repo, build/deploy theo chính sách, mọi service dùng artifact đã được xác minh. |
| **Điều phối** | Platform/CI và Security cùng các Service Owner đánh giá cluster; risk owner có thẩm quyền quyết định kế hoạch và ngoại lệ; assessor đối chiếu evidence. |

Không được khẳng định “toàn bộ hệ thống đã bị xâm nhập” chỉ vì token xuất hiện trong log; đồng thời không được kết luận “không có rủi ro” khi không có tín hiệu cảnh báo. Đánh giá đúng phải phân biệt **khả năng phơi lộ, khả năng khai thác, bằng chứng sự kiện thực tế và độ tin cậy của điều tra**.

## 13. Các sai lầm thường gặp

| Ngộ nhận | Vấn đề | Cách làm phù hợp |
| --- | --- | --- |
| “Cộng risk score tất cả service ra tổng rủi ro.” | Điểm 1–5 mang tính thứ bậc, có thể trùng hậu quả và quan hệ phụ thuộc | Đánh giá theo risk cluster, scenario và phương pháp rõ |
| “Năm risk Medium nghĩa là chắc chắn Critical.” | Số lượng không cho biết quan hệ, mức phơi lộ và hậu quả | Phân tích đường thay thế, nguyên nhân chung, tác động toàn hệ thống |
| “Mọi rủi ro độc lập nên dùng \(1-\prod(1-p)\).” | Dùng chung credential, IAM, hạ tầng làm mất giả định độc lập | Kiểm tra phụ thuộc và lựa chọn mô hình/ước lượng có căn cứ |
| “Đã bật WAF nên có thể tự giảm rủi ro tổng hợp.” | WAF có thể không chặn luồng nội bộ, token hợp lệ hoặc truy cập storage | Test end-to-end theo các đường gây hại, xác minh runtime |
| “Sửa một endpoint là hết rủi ro dữ liệu.” | Còn export, backup, direct storage và các đường phụ | Xác định scope, retest toàn nhóm control liên quan |
| “Không có alert đồng nghĩa chưa xảy ra gì.” | Log có thể thiếu hoặc detection chưa bao phủ | Kiểm tra độ phủ telemetry, thời gian mất log và nguồn dữ liệu khác |
| “Chấp nhận ngoại lệ một lần là đủ mãi mãi.” | Kỳ phơi lộ, asset, rủi ro và control có thể đổi | Hạn hiệu lực, owner, trigger đánh giá lại và điều kiện chấp nhận |
| “Trung bình score giảm là đảm bảo an toàn tốt hơn.” | Có thể che rủi ro tập trung nghiêm trọng hoặc đánh giá chủ quan | Kết hợp score, dependency, evidence và các kịch bản tác động lớn |

## 14. Ghi nhớ và câu hỏi tự kiểm tra

- **Rủi ro tích lũy** phát sinh khi thiếu hụt kéo dài, có nhiều đường gây hại, nhiều control cùng yếu, hoặc cùng phụ thuộc một thành phần; phải nêu rõ **cơ chế tích lũy**.
- **Không cộng cơ học risk score 5×5**. Điểm là công cụ ưu tiên trong mô hình được định nghĩa, không phải xác suất hay đơn vị tiền tệ.
- Công thức xác suất nhiều sự kiện chỉ có ý nghĩa khi **giả định độc lập, kỳ đánh giá và định nghĩa sự kiện** đã được xác lập; rủi ro tương quan cần phân tích riêng.
- **Một control được kiểm chứng đạt không tự bảo đảm mục tiêu toàn hệ thống đạt**; cần xét các đường thay thế, điều kiện kết hợp và nguồn chung.
- **Bằng chứng security assurance** phải gắn đúng claim, control, phiên bản, môi trường, nguồn, thời điểm, phương pháp, kết quả và giới hạn.
- Risk register nên biểu diễn **dependency, related risks, risk cluster, độ tin cậy, owner, thời gian tồn tại và trigger review**; mọi lần hạ residual risk cần bằng chứng hiệu lực control.
- Đánh giá là **quá trình liên tục trong phát triển và vận hành**, gắn khắc phục finding với test hồi quy, xác nhận bản deploy và kiểm chứng lại mục tiêu bảo mật.

**Câu hỏi tự kiểm tra:** Nếu hai API cùng đọc một cơ sở dữ liệu và cùng sử dụng IAM role, nhưng cả hai đạt security integration test, bạn cần thêm những bằng chứng gì để kết luận rủi ro lộ dữ liệu đã được kiểm soát ở production?

**Gợi ý:** xác minh permission thực tế của role chung; các đường truy cập storage, export, batch và backup; bản build/deployment; kiểm tra quyền ở môi trường đích; logging và detection end-to-end; những khoảng trống chưa đánh giá. Mỗi kết luận phải giới hạn trong phạm vi của bằng chứng đã thu thập.
