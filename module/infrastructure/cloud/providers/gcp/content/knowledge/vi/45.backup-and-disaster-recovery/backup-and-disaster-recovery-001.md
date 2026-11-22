# Xác định RPO, RTO và phân hạng workload GCP

Khi một ứng dụng trên Google Cloud ngừng hoạt động hoặc dữ liệu bị hỏng, câu hỏi đầu tiên không phải là "nên bật backup nào?", mà là: **nghiệp vụ chịu được gián đoạn bao lâu và có thể mất tối đa bao nhiêu dữ liệu?** Hai câu trả lời này trở thành cơ sở để thiết kế, cấp ngân sách, ưu tiên phục hồi và kiểm tra khả năng phục hồi thảm họa.

Bài học thuộc chương **Sao lưu và phục hồi thảm họa** của module **CLOUD_PROVIDERS_GCP**. Trong lộ trình tìm hiểu Google Cloud từ project, IAM, VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu, bài này giúp người học chuyển mục tiêu kinh doanh thành yêu cầu kỹ thuật có thể đo lường, lựa chọn chiến lược backup/DR phù hợp và theo dõi độ tin cậy cùng chi phí.

Bài học tập trung vào **xác định mục tiêu và phân hạng workload**, không mặc định mọi hệ thống đều phải active-active hoặc có RPO bằng 0.

Sau bài học, bạn có thể:

- Giải thích Recovery Point Objective (RPO), Recovery Time Objective (RTO), MTPD và mối quan hệ với availability.
- Tính mức mất dữ liệu và thời gian phục hồi từ một timeline giả định.
- Thực hiện Business Impact Analysis (BIA), tìm dependency và xếp hạng workload theo mức độ ảnh hưởng.
- Thiết lập các tier minh họa, gắn tier với RPO/RTO được chủ sở hữu nghiệp vụ phê duyệt.
- Phân biệt backup, replication, high availability và disaster recovery.
- Lựa chọn sơ bộ chiến lược cold/warm/hot và các building block Google Cloud theo từng workload.
- Viết recovery plan, xác minh RPO/RTO qua diễn tập và theo dõi rủi ro còn lại.

> **Nguyên tắc:** RPO và RTO là *mục tiêu cần đạt*, không phải thông số tự động được Google Cloud bảo đảm chỉ vì bạn bật một dịch vụ. Chỉ khi khôi phục thử trên kịch bản phù hợp, đo thời gian và đối chiếu dữ liệu, nhóm mới có bằng chứng về năng lực phục hồi thực tế.

## 1. RPO là gì?

**Recovery Point Objective (RPO)** là khoảng thời gian mất dữ liệu tối đa mà nghiệp vụ có thể chấp nhận khi xảy ra sự cố nghiêm trọng.

Nếu RPO = 15 phút, thiết kế phải cho phép phục hồi dữ liệu đến một thời điểm không quá 15 phút trước khi sự cố làm gián đoạn việc ghi dữ liệu. RPO nói về **độ cũ tối đa của điểm dữ liệu có thể khôi phục**, không trực tiếp nói về số bản ghi hoặc số tiền bị mất.

~~~mermaid
flowchart LR
    A["10:00<br/>Điểm khôi phục cuối"]
    B["10:15<br/>Sự cố"]
    C["Sau sự cố<br/>Khôi phục bản dữ liệu"]
    A -->|"Khoảng mất dữ liệu tiềm năng: 15 phút"| B
    B --> C
~~~

### 1.1. Ví dụ tính RPO quan sát được

Giả sử:

- 09:50:00: có recovery point hợp lệ gần nhất.
- 10:00:00: hệ thống gặp sự cố làm mất toàn bộ dữ liệu chưa được bảo vệ.
- 10:30:00: bản phục hồi hoàn tất.

Khi đó:

\[
RPO_{\text{quan sát}} = 10{:}00 - 09{:}50 = 10\ \text{phút}
\]

Bản phục hồi có thể hoàn tất 30 phút sau sự cố nhưng RPO vẫn là 10 phút. Thời gian chờ hệ thống phục hồi được tính ở **RTO**, không phải RPO.

Nếu trong 10 phút hệ thống xử lý trung bình 50 đơn hàng/phút, số đơn hàng cần hòa giải hoặc có nguy cơ mất theo một ước tính sơ bộ là:

\[
50\ \text{đơn/phút} \times 10\ \text{phút} = 500\ \text{đơn}
\]

Con số 500 là *ước lượng theo tốc độ giao dịch*, không phải mức mất dữ liệu chắc chắn. Tùy replication, transactions đã commit, hàng đợi, khả năng replay và cơ chế đối soát, thiệt hại thực tế có thể khác.

### 1.2. Những điều RPO không chứng minh

- RPO = 0 **không** có nghĩa không bao giờ xảy ra lỗi nghiệp vụ.
- Có backup mỗi 15 phút **không tự động** bảo đảm RPO 15 phút: job có thể chạy trễ, lỗi, không nhất quán hoặc chưa kịp lưu sang vùng khôi phục.
- Replication gần thời gian thực **không nhất thiết** có RPO bằng 0: asynchronous replica có thể chậm và chưa nhận transaction cuối.
- Backup chỉ của database không chứng minh toàn workload đạt RPO: file đính kèm, queue, cache, search index hoặc external state có thể có recovery point khác.

**RPO phải được đánh giá cho dữ liệu nghiệp vụ quan trọng ở cả đường ghi và các hệ thống phụ thuộc, không chỉ cho một backup job riêng lẻ.**

## 2. RTO là gì?

**Recovery Time Objective (RTO)** là thời gian gián đoạn tối đa mà nghiệp vụ chấp nhận, tính từ khi dịch vụ không còn đáp ứng mức chức năng đã thỏa thuận đến khi dịch vụ đã được phục hồi và xác nhận đủ khả năng hoạt động.

Ví dụ: RTO = 60 phút có nghĩa đội vận hành phải khôi phục được dịch vụ đủ để phục vụ nghiệp vụ trong vòng một giờ kể từ khi gián đoạn bắt đầu. "Máy chủ đã chạy" chưa hẳn là đã đạt RTO nếu database chưa sẵn sàng hoặc người dùng chưa đăng nhập/tạo đơn được.

### 2.1. RTO bao gồm những bước nào?

~~~mermaid
flowchart LR
    F["Sự cố bắt đầu"] --> DET["Phát hiện / xác định"]
    DET --> DEC["Quyết định kích hoạt DR"]
    DEC --> REST["Khôi phục dữ liệu và hạ tầng"]
    REST --> VAL["Xác minh kỹ thuật / nghiệp vụ"]
    VAL --> TRA["Chuyển traffic / mở dịch vụ"]
    TRA --> OK["Dịch vụ đủ điều kiện hoạt động"]
~~~

Có thể chia ngân sách RTO như sau:

| Thành phần | Thời gian mục tiêu minh họa |
|---|---:|
| Phát hiện và phân loại | 5 phút |
| Phê duyệt failover | 5 phút |
| Khởi tạo hạ tầng/khôi phục dữ liệu | 25 phút |
| Kiểm thử và xác minh | 15 phút |
| Chuyển traffic/DNS/route | 10 phút |
| **Tổng** | **60 phút** |

Trong sự cố thật, các bước có thể chồng lấn nhưng không được âm thầm bỏ qua thời gian phát hiện, xác minh hoặc traffic chuyển chậm. Cần đo theo một mốc thống nhất mà business owner phê duyệt.

### 2.2. RTO quan sát được

Giả sử người dùng không đặt được đơn từ 10:00 và smoke test nghiệp vụ trên hạ tầng dự phòng PASS lúc 10:42, traffic mở trở lại lúc 10:45. RTO quan sát được là **45 phút**, không phải 42 phút.

Nếu đội hạ tầng báo "instance Ready" lúc 10:20 nhưng service vẫn lỗi xác thực đến 10:45, không thể lấy 20 phút làm RTO của toàn ứng dụng.

## 3. RPO, RTO, availability và các khái niệm gần nhau

| Thuật ngữ | Câu hỏi | Ví dụ |
|---|---|---|
| RPO | Có thể mất tối đa bao nhiêu *thời gian dữ liệu*? | 15 phút |
| RTO | Hệ thống có thể gián đoạn tối đa bao lâu? | 1 giờ |
| MTPD/MAO | Gián đoạn tối đa trước khi thiệt hại trở nên không chấp nhận được? | 4 giờ |
| Availability SLO | Tỷ lệ thời gian dịch vụ có thể phục vụ? | 99,9% theo tháng |
| SLA | Cam kết dịch vụ và điều kiện pháp lý/hợp đồng? | Cam kết, ngoại lệ, trách nhiệm, tín dụng dịch vụ |
| Backup retention | Giữ recovery points trong bao lâu? | 30 ngày |
| Data durability | Xác suất dữ liệu được lưu an toàn lâu dài? | Thuộc tính của giải pháp lưu trữ |
| Recovery consistency | Dữ liệu khôi phục có hợp lệ về mặt giao dịch? | Không có đơn hàng thiếu dòng chi tiết |

**RTO nên không vượt MTPD**, đồng thời thường cần chừa thời gian để nghiệp vụ xác minh và đưa quy trình thủ công trở lại bình thường.

RPO, RTO và availability có quan hệ nhưng không thể thay thế nhau. Một hệ thống có uptime cao trong tháng vẫn có thể không đáp ứng RPO khi bị lỗi dữ liệu nghiêm trọng; một hệ thống có backup tốt vẫn có thể mất hàng giờ để phục hồi.

### 3.1. High Availability khác Disaster Recovery

**High Availability (HA)** giảm gián đoạn do lỗi thành phần có phạm vi hẹp, ví dụ một zone hoặc instance. **Disaster Recovery (DR)** chuẩn bị phục hồi khi lỗi lớn xảy ra: mất region, xóa nhầm, ransomware, dữ liệu bị hỏng, sai cấu hình lan rộng hoặc mất năng lực vận hành.

| Tình huống | HA có thể hỗ trợ? | DR thường cần? |
|---|---|---|
| Một VM hỏng | Có, nếu có instance group/replica | Có thể không |
| Một zone lỗi | Có, nếu thiết kế regional/multi-zone | Tùy mức độ |
| Cả region không khả dụng | HA trong một region không đủ | Có |
| Xóa dữ liệu bằng thao tác nhầm | Replica có thể sao chép sai/xóa | Cần backup/PITR |
| Ransomware/credential compromise | Replica có thể bị ảnh hưởng | Cần backup cô lập/immutable và IAM recovery |
| Sai release khiến toàn bộ API trả 500 | Rollback nhanh có thể đủ | Cần runbook kiểm soát phạm vi |
| Mất key cần để giải mã backup | HA không giải quyết | Phải thiết kế khôi phục key và quyền |

Bật multi-zone không tự tạo multi-region DR; bật cross-region replica cũng không thay thế backup sạch phục vụ khôi phục dữ liệu bị xóa/hỏng.

## 4. Bắt đầu từ Business Impact Analysis (BIA)

BIA giúp xác định mức độ ưu tiên dựa trên **ảnh hưởng tới nghiệp vụ**, thay vì chỉ dựa trên sự yêu thích của nhóm kỹ thuật với một dịch vụ.

### 4.1. Các đầu vào của BIA

Mỗi workload cần được khảo sát theo:

1. **Chức năng nghiệp vụ:** hệ thống phục vụ điều gì và hoạt động nào bị dừng khi nó lỗi?
2. **Doanh thu/tài chính:** doanh thu, chi phí đền bù, chi phí thủ công, ảnh hưởng chuỗi cung ứng.
3. **Pháp lý/tuân thủ:** dữ liệu bắt buộc giữ, nghĩa vụ thông báo, deadline báo cáo, data residency.
4. **Khách hàng:** bao nhiêu người bị ảnh hưởng và mức độ nghiêm trọng?
5. **An toàn/vận hành:** có liên quan đến an toàn con người, kiểm soát truy cập, chống gian lận không?
6. **Dữ liệu:** tốc độ ghi, sự kiện đã xác nhận, khả năng replay và nguồn dữ liệu gốc.
7. **Thời điểm:** cuối tháng, giờ cao điểm, batch nightly, cuối quý có khác ngày thường không?
8. **Phụ thuộc:** hệ thống nhận dạng, network, DNS, KMS, secrets, API đối tác, queue, database.
9. **Phương án thủ công:** nếu ngừng hệ thống, có thể tiếp tục công việc bằng quy trình khác hay không?
10. **Ngân sách và năng lực vận hành:** chi phí duy trì dự phòng, nhân sự trực, mức tự động hóa.

### 4.2. Phỏng vấn chủ sở hữu nghiệp vụ

Không nên hỏi đơn giản "muốn RTO bao nhiêu?" vì phần lớn bên nghiệp vụ sẽ trả lời "càng ngắn càng tốt". Hãy thử câu hỏi gắn với thiệt hại:

- Nếu hệ thống dừng 15 phút, điều gì xảy ra? Nếu 1 giờ, 4 giờ hoặc 24 giờ thì sao?
- Có giao dịch nào đã thông báo thành công cho khách hàng mà tuyệt đối không thể mất không?
- Nếu mất 10 phút dữ liệu, có thể tái tạo từ event log, hệ thống thanh toán hay batch nguồn không?
- Sau khi API hoạt động lại, nhân viên cần bao lâu để xác minh số dư hoặc hoàn tất công việc thủ công?
- Hệ thống nào buộc phải hoạt động trước để workload này trở lại?
- Mức chi phí nào được chấp thuận để giảm RTO từ 8 giờ xuống 1 giờ?

### 4.3. Bảng BIA mẫu

| Workload | Ảnh hưởng sau 1 giờ | Sau 8 giờ | Sau 24 giờ | Dữ liệu có thể replay? | Chủ sở hữu |
|---|---|---|---|---|---|
| Checkout/Orders | Mất giao dịch, đơn hàng bị treo | Doanh thu và CSKH ảnh hưởng lớn | Không chấp nhận | Một phần | Commerce Lead |
| Identity/SSO | Người dùng không đăng nhập được | Nhiều hệ thống phụ thuộc tê liệt | Không chấp nhận | Không phải vấn đề chính | Security Lead |
| Analytics dashboard | Báo cáo tạm thời không xem được | Nhóm vận hành mất quan sát | Trễ báo cáo | Có thể tái xử lý | Data Lead |
| Batch đối soát | Delay trong giờ bình thường | Nguy cơ lỡ deadline | Phụ thuộc lịch thanh toán | Có, nếu event/input còn | Finance Ops |
| Kho lưu tài liệu lịch sử | Ảnh hưởng nhỏ | Ảnh hưởng nhỏ | Một số yêu cầu truy xuất chậm | Không nếu file gốc mất | Records Lead |

Cần ghi cả **khung giờ nhạy cảm**: batch đối soát có thể Tier 2 ngày thường nhưng là Tier 1 vào ngày khóa sổ. Thiết kế tier có thể cần profile theo giai đoạn vận hành.

## 5. Chọn RPO/RTO từ thiệt hại, không từ tính năng dịch vụ

Quy trình quyết định:

1. Xác định MTPD từ mức thiệt hại được phép.
2. Đặt **RTO mục tiêu** thấp hơn MTPD, có buffer cho thông tin khách hàng, kiểm tra và công việc thủ công.
3. Xác định giá trị dữ liệu ghi mới: giao dịch nào có thể tái dựng, giao dịch nào là tài sản pháp lý.
4. Đặt **RPO mục tiêu** từ mức mất dữ liệu tối đa chấp nhận được.
5. Xác định workload có cần phục hồi cùng các hệ thống phụ thuộc không.
6. Đề xuất ít nhất hai phương án kỹ thuật với chi phí/độ phức tạp khác nhau.
7. Cho business owner và risk/compliance owner ký duyệt mức mục tiêu.
8. Kiểm thử giải pháp, đo actual RPO/RTO rồi xác nhận gap.

### 5.1. Công thức lượng hóa mất dữ liệu

Nếu tốc độ tạo giao dịch mới trung bình là V (giao dịch/phút) và RPO được đo bằng M phút:

\[
\text{Giao dịch có nguy cơ mất ước tính} = V \times M
\]

Ví dụ hệ thống checkout tạo 200 giao dịch/phút và RPO mục tiêu 5 phút:

\[
200 \times 5 = 1.000\ \text{giao dịch}
\]

Một nghìn giao dịch có nguy cơ mất có thể không được nghiệp vụ chấp nhận. Khi đó cần cân nhắc RPO thấp hơn, durable event log, idempotent replay hoặc kiến trúc replication/commit khác. Không tự tuyên bố RPO bằng 0 nếu chưa chứng minh cách bảo toàn dữ liệu đã xác nhận thành công.

### 5.2. Chi phí gián đoạn ước tính

~~~text
Chi phí gián đoạn ≈
  doanh thu/lợi nhuận bị ảnh hưởng
  + nhân công và vận hành khẩn cấp
  + phí phạt/đền bù
  + thiệt hại khách hàng và uy tín (khó định lượng)
~~~

Đây là khung phân tích, không phải công thức kế toán chuẩn. Phải tránh cộng trùng doanh thu và lợi nhuận hoặc đánh đồng doanh thu bị trì hoãn với doanh thu bị mất vĩnh viễn.

## 6. Phân hạng workload: Tier 0, 1, 2, 3

Không có một bộ ngưỡng Tier 0–3 mặc định áp dụng cho mọi công ty hoặc do Google Cloud công bố như SLA. Bảng dưới đây chỉ là **mẫu chính sách nội bộ** để diễn tập. Mỗi tổ chức cần tự xác định và phê duyệt ngưỡng.

| Tier minh họa | Mức độ ảnh hưởng | RPO mục tiêu minh họa | RTO mục tiêu minh họa | Ví dụ |
|---|---|---:|---:|---|
| Tier 0 – Tối quan trọng | Ngừng là mất giao dịch/gián đoạn diện rộng, có rủi ro nghiêm trọng | ≤ 1 phút | ≤ 15 phút | Hệ thống thanh toán hoặc core identity có yêu cầu đặc biệt |
| Tier 1 – Quan trọng | Doanh thu/khách hàng chịu ảnh hưởng lớn | ≤ 15 phút | ≤ 1 giờ | Orders API, đặt lịch, giao dịch nghiệp vụ |
| Tier 2 – Thiết yếu | Có cách vận hành thay thế tạm thời | ≤ 4 giờ | ≤ 8 giờ | Quản trị nội bộ, ETL gần ngày |
| Tier 3 – Khả dụng trì hoãn | Truy xuất ít thường xuyên, có thể chờ | ≤ 24 giờ | ≤ 72 giờ | Kho lịch sử, môi trường lab |

Các ngưỡng trên **không phải năng lực đã đạt được** của Cloud Run, Cloud SQL, Cloud Storage hoặc một giải pháp cụ thể. Đây là các mục tiêu kinh doanh để đánh giá thiết kế.

### 6.1. Tiêu chí phân hạng

Chọn tier từ nhiều chiều, không chỉ từ số request/giây:

| Tiêu chí | Tier cao khi | Tier thấp hơn khi |
|---|---|---|
| Thiệt hại tài chính | Mỗi phút ngừng gây thiệt hại đáng kể | Mất ít chi phí, có thể hoãn |
| Dữ liệu | Không thể tái tạo giao dịch đã xác nhận | Có thể replay từ nguồn khác |
| Pháp lý | Vi phạm nghĩa vụ/kỳ hạn quan trọng | Có khoảng thời gian xử lý linh hoạt |
| Số người ảnh hưởng | Phần lớn khách hàng và nhân viên | Nhóm nhỏ, không khẩn cấp |
| Phụ thuộc | Nhiều workload quan trọng cần nó | Ít hệ thống phụ thuộc |
| Workaround | Không có | Có quy trình thủ công được kiểm chứng |
| Thời điểm nhạy cảm | Cao điểm, cuối kỳ, thanh toán | Tác vụ batch có thể lùi |

**Tier phải được doanh nghiệp đồng thuận**, còn đội kỹ thuật đánh giá tính khả thi và chi phí. Không tự chọn Tier 0 chỉ vì hệ thống dùng công nghệ mới.

### 6.2. Ví dụ phương pháp chấm điểm

Có thể dùng ma trận chấm 1–5 điểm trên bốn trục, mỗi trục có trọng số minh họa:

| Trục | Trọng số minh họa |
|---|---:|
| Thiệt hại kinh doanh và khách hàng | 40% |
| Rủi ro mất dữ liệu/tuân thủ | 30% |
| Phụ thuộc của hệ thống khác | 20% |
| Thiếu phương án vận hành thay thế | 10% |

~~~text
Risk score =
  0.40 × business_impact
+ 0.30 × data_compliance_impact
+ 0.20 × dependency_impact
+ 0.10 × workaround_absence
~~~

Nếu Orders API có các điểm 5, 4, 4, 4 thì:

\[
0,4(5) + 0,3(4) + 0,2(4) + 0,1(4) = 4,4
\]

Score 4,4 gợi ý mức ưu tiên cao, nhưng **không tự động suy ra RPO/RTO**. Business owner cần đối chiếu thiệt hại theo thời gian, khả năng replay và chi phí để chốt giá trị cụ thể. Có thể đặt quy tắc chấm điểm nội bộ, song phải được review định kỳ.

## 7. Dependency tier: khi một workload thấp trở thành điểm lỗi của Tier 0

Workload không tồn tại độc lập. Checkout API có thể cần IAM/SSO, DNS, secret, message broker, database, payment gateway và cấu hình VPC.

~~~mermaid
flowchart TD
    CHECK["Checkout API<br/>Tier 1"] --> DB["Cloud SQL orders<br/>Tier 1"]
    CHECK --> ID["Identity / SSO<br/>Shared dependency"]
    CHECK --> SEC["Secret Manager + KMS"]
    CHECK --> NET["DNS / Load Balancer / VPC"]
    CHECK --> MQ["Pub/Sub order events"]
    MQ --> WORKER["Fulfillment worker<br/>Tier 2 nếu xử lý trễ được"]
~~~

Một dependency có tier thấp hơn nhưng là **điều kiện bắt buộc** để khôi phục checkout thì mục tiêu phục hồi của dependency phải được đánh giá theo đường đi khôi phục end-to-end. Ví dụ, nếu login không thể dùng vì SSO đang down, Orders API có thể chạy nhưng vẫn không được xem là phục hồi.

Tuy nhiên không phải mọi dependency phải chạy trước khi service phục hồi. Nếu gửi email có thể được queue lại, hệ thống email có thể có RTO dài hơn. Phân biệt:

- **Hard dependency:** thiếu nó thì luồng nghiệp vụ chính không dùng được.
- **Soft dependency:** thiếu nó nhưng service có degraded mode, queue, cache hoặc xử lý bù.
- **Recovery dependency:** không nằm trong request path thường ngày nhưng bắt buộc để DR, ví dụ Cloud KMS key, Terraform state, backup vault, DNS/IAM quyền breakglass.

Một service dùng chung có thể phải đạt **mục tiêu nghiêm ngặt nhất** trong số các hard dependencies mà nó phục vụ, hoặc có phương án fallback được kiểm chứng.

## 8. Lập Workload Recovery Register

Một bảng đăng ký giúp kiểm soát việc phân hạng và bàn giao:

| Trường | Ví dụ |
|---|---|
| Workload ID | orders-api-prod |
| Business owner | Commerce Lead |
| Technical owner | Platform Team |
| Chức năng | Đặt hàng và thanh toán |
| Tier | Tier 1 |
| RPO target | 15 phút |
| RTO target | 60 phút |
| MTPD | 4 giờ |
| Peak load | 500 requests/phút |
| Data stores | Cloud SQL PostgreSQL, Cloud Storage |
| Hard dependencies | IAM, DNS, VPC, Cloud SQL, Secret Manager |
| Threat scenarios | Zone/region outage, corruption, accidental deletion |
| DR pattern | Warm standby hoặc phương án đã duyệt |
| Backup/replication | PITR + cross-region recovery plan |
| Runbook | Internal link hoặc tài liệu có version |
| Last drill / achieved RPO | Ngày, phút, kết quả |
| Last drill / achieved RTO | Ngày, phút, kết quả |
| Exception & owner | Nếu chưa đạt mục tiêu |
| Review date | Ngày review BIA tiếp theo |

Ví dụ YAML ghi yêu cầu (chỉ là mẫu hồ sơ, **không phải manifest GCP**):

~~~yaml
workload_id: orders-api-prod
service_name: orders-api
business_owner: commerce-lead
technical_owner: platform-team
classification:
  tier: 1
  rpo_target_minutes: 15
  rto_target_minutes: 60
  mtpd_minutes: 240
recovery_scope:
  scenarios:
    - regional_outage
    - database_corruption
    - accidental_deletion
  hard_dependencies:
    - cloud-sql-orders
    - runtime-identity
    - dns
    - kms-key
evidence:
  last_drill_date: null
  measured_rpo_minutes: null
  measured_rto_minutes: null
  approved_by: null
~~~

Lưu ý: một field measured_* trống nghĩa là **chưa có bằng chứng**. Không tự điền bằng giá trị target.

## 9. Phân biệt mất zone, mất region và lỗi dữ liệu logic

RPO/RTO phải được xác định theo **kịch bản**. Một kiến trúc có thể đạt RTO rất thấp với lỗi máy trong một zone nhưng phục hồi chậm khi cả region gặp sự cố.

| Kịch bản | Tác động có thể có | Cần kiểm tra |
|---|---|---|
| VM/pod crash | Instance đơn không chạy | Restart, autoscaling, health checks |
| Zone outage | Một phần compute/storage trong region lỗi | Multi-zone deployment, regional HA |
| Region outage | Compute/network/database region không dùng được | Secondary region, data availability, DNS/routing |
| Xóa nhầm dữ liệu | Dữ liệu logic sai nhưng hạ tầng vẫn chạy | Backup/PITR, versioning, deletion protection |
| Ransomware/compromised admin | Backup và dữ liệu live cùng bị tác động | IAM separation, immutable vault, recovery credentials |
| Bad deploy | Code/schema không tương thích | Rollback/roll-forward, schema compatibility, backups |
| Third-party outage | Payment/SSO/email ngoài cloud lỗi | Fallback, queue, degrade, contract/SLA |
| Cloud KMS key unavailable | Không giải mã data/backup khi cần | Key location, IAM recovery và kế hoạch cross-region |

Một DR plan có thể có nhiều target: Tier 1 với RTO ≤15 phút cho zone outage nhưng ≤60 phút cho region outage, nếu nghiệp vụ chấp thuận. Các ngoại lệ phải thể hiện rõ trong SLA/SLO và runbook, không dùng một con số để che mọi tình huống.

## 10. Cold, warm và hot: ba mẫu DR cơ bản

Google Cloud Disaster Recovery Planning Guide mô tả ba nhóm chiến lược: **cold, warm, hot**.

~~~mermaid
flowchart LR
    A["Cold<br/>Khôi phục từ backup<br/>Ít tài nguyên dự phòng"] --> B["Warm<br/>Có sẵn hạ tầng một phần<br/>Dữ liệu được đồng bộ"]
    B --> C["Hot<br/>Hạ tầng phục vụ sẵn<br/>Nhanh hơn, phức tạp hơn"]
~~~

| Pattern | Trạng thái dự phòng | RTO/RPO kỳ vọng định tính | Chi phí và độ phức tạp | Phù hợp |
|---|---|---|---|---|
| Cold | Lưu backup/IaC, tạo hoặc bật tài nguyên khi có sự cố | RTO dài; RPO phụ thuộc backup | Thấp hơn, thao tác restore nhiều | Tier 3, một số Tier 2 |
| Warm | Hạ tầng/data replica có sẵn một phần, cần promote/scale/cutover | RTO trung bình; RPO phụ thuộc lag | Trung bình | Tier 1/2 tùy target |
| Hot | Nhiều thành phần hoạt động sẵn ở điểm DR, routing/failover nhanh | RTO thấp; RPO tùy replication/commit | Cao, phức tạp | Tier 0/1 nghiêm ngặt |

**Hot không đồng nghĩa RPO bằng 0.** Nếu cả hai region dùng asynchronous replication, transaction chưa sang secondary vẫn có thể mất. Với active-active, cần giải quyết conflict, ordering, idempotency và consistency; không thể chỉ triển khai hai bản Cloud Run rồi gọi đó là active-active DR.

### 10.1. Câu hỏi khi chọn mẫu

- Dữ liệu thay đổi liên tục hay chỉ nhập một lần mỗi ngày?
- Có sẵn capacity và quota trong region dự phòng không?
- Có thể recreate web/app bằng IaC trong bao lâu?
- Database cần restore hoàn toàn hay có replica để promote?
- Network, secrets, IAM, DNS và certificate có được phục hồi đồng bộ không?
- Có kiểm tra dữ liệu mới nhất trước khi cho hệ thống nhận writes không?
- Ai có quyền kích hoạt runbook khi region chính không thể truy cập?

Thiết kế phải tính cả **chi phí trạng thái chờ** và **chi phí vận hành diễn tập**, không chỉ tiền backup.

## 11. Mapping các building block Google Cloud

| Workload/loại dữ liệu | Công cụ có thể dùng | Rủi ro cần lưu ý |
|---|---|---|
| Compute Engine disks | Snapshots, machine images, Backup and DR, regional disk khi phù hợp | Snapshot không mặc nhiên là app-consistent; restore VM/network cần thời gian |
| Cloud SQL | Automated backups, PITR, HA, cross-region replica, enhanced backup | HA một region khác cross-region DR; PITR và replica có kịch bản riêng |
| GKE | Regional cluster, Backup for GKE, IaC, image registry | Backup không tự tạo target cluster; restore Kubernetes objects/PVC phải test |
| Cloud Run | Container images, IaC, multi-region deployment, LB routing | Stateless service dễ dựng lại nhưng secret, network, database không tự phục hồi |
| Cloud Storage | Soft delete, Object Versioning, dual-/multi-region, turbo replication | Replication bất đồng bộ; versioning không bảo vệ việc xóa cả bucket |
| BigQuery | Time travel, fail-safe, table snapshots, cross-region replication tùy nhu cầu | Thời gian giữ dữ liệu và khả năng recovery khác nhau theo tính năng |
| Terraform/state | GCS backend với versioning, IAM, export config theo quy trình | State và credential có thể là recovery dependency |
| Secret Manager / Cloud KMS | Replication/location, secret version, key IAM và access recovery | Không có quyền/key để decrypt thì backup cũng không dùng được |
| Audit logs | Cloud Logging buckets, sinks, retention | Log cần phục vụ điều tra ngay khi production project gặp sự cố |

Các tính năng có điều kiện về region, edition, loại database, tier hoặc trạng thái hỗ trợ. Trước khi chọn phương án, kiểm tra tài liệu hiện hành và thực hiện proof-of-recovery trên workload cụ thể.

### 11.1. Cloud SQL: backup, PITR và HA

- **Automated backup** lưu recovery points theo lịch và retention; dữ liệu được khôi phục về trạng thái tại backup.
- **PITR** dùng backup/transaction log để khôi phục gần một thời điểm trước lỗi logic; với Cloud SQL PostgreSQL, thao tác PITR tạo **instance mới**, cần cấu hình lại kết nối/route và xác minh dữ liệu.
- **Regional HA** cho phép failover giữa các zone trong cùng region; không tự bảo vệ trước mất toàn region.
- **Cross-region replica** có thể giúp dựng chiến lược DR theo vùng, nhưng replication lag và promotion phải được quan sát; read replica không phải bản backup lịch sử sạch.

Không gán RTO cố định cho Cloud SQL vì thời gian PITR/restore thay đổi theo data volume, quota, cấu hình, network và các bước xác minh. Mỗi edition và phương thức tạo instance có thể có mặc định PITR khác nhau; **xác nhận cấu hình thực tế**, không suy từ tên dịch vụ.

### 11.2. Cloud Storage: durability không đồng nghĩa zero RPO

Cloud Storage regional lưu data có dự phòng giữa nhiều zone trong cùng region. Dual-region và multi-region phân tán dữ liệu sang các khu vực địa lý khác nhau nhưng replication giữa các region mặc định là bất đồng bộ.

Ở dual-region, **turbo replication** có thể hỗ trợ mục tiêu sao chép object mới sang region thứ hai trong 15 phút theo đặc tính dịch vụ. Điều đó không xác nhận toàn bộ hệ thống Orders API có RPO 15 phút: database, queue và metadata vẫn có giới hạn riêng.

**Soft delete** giúp phục hồi object/bucket bị xóa trong retention được cấu hình. **Object Versioning** giữ các phiên bản noncurrent để phục hồi phiên bản trước; tính năng này không tự bảo vệ khỏi xóa bucket. Nên chọn theo threat model và quản lý lifecycle/cost.

### 11.3. Backup for GKE

Backup for GKE có BackupPlan/RestorePlan để bảo vệ Kubernetes resource manifests và một số volume theo cấu hình. Restore có thể sang cluster khác, nhưng **target cluster phải tồn tại** và có agent/add-on cần thiết. Secret, cluster-scoped resource, dữ liệu bên ngoài cluster và bảo mật namespace cần được kiểm tra trong test.

Không giả định Backup for GKE tự khôi phục external Cloud SQL database, DNS, IAM hoặc tất cả tài nguyên hạ tầng. Sử dụng IaC và các backup/restore chuyên biệt cho hard dependencies.

### 11.4. Backup and DR service

Backup and DR là dịch vụ quản lý policy, lịch backup và recovery cho nhiều workload được hỗ trợ. Backup vault cung cấp cơ chế immutability/indelibility theo thuộc tính WORM để giảm rủi ro xóa/sửa backup.

Cấu hình immutability cần được thiết kế cùng retention, RBAC và breakglass. Không coi backup vault bất biến là đủ nếu dữ liệu bị mã hóa/hỏng **trước khi backup được tạo** hoặc key/identity phục hồi bị mất.

## 12. Ví dụ phân hạng trong một hệ thống bán hàng

Hệ thống thương mại gồm frontend, checkout, hàng đợi, warehouse, analytics và kho hóa đơn. BIA có thể đưa ra hồ sơ minh họa:

| Workload | Tier | RPO mục tiêu | RTO mục tiêu | Giải pháp sơ bộ |
|---|---|---:|---:|---|
| Checkout/Orders DB | Tier 1 | ≤ 5 phút | ≤ 60 phút | PITR + cross-region DR/replication đã kiểm thử |
| Customer identity | Tier 1 | ≤ 15 phút | ≤ 60 phút | Redundant identity path và credential recovery |
| Web frontend stateless | Tier 1 | N/A với image được version hóa | ≤ 30 phút | Multi-region image deploy và traffic routing |
| Fulfillment events | Tier 1 | ≤ 15 phút | ≤ 60 phút | Durable queue/replay, idempotency |
| Analytics reporting | Tier 2 | ≤ 4 giờ | ≤ 8 giờ | Backup/export và tái xử lý |
| Batch báo cáo cuối ngày | Tier 2 hoặc 1 trong cửa sổ khóa sổ | ≤ 4 giờ | ≤ 8 giờ hoặc ngắn hơn | Snapshot và replay batch |
| Archive hóa đơn | Tier 3 cho truy cập; retention nghiêm ngặt cho dữ liệu | ≤ 24 giờ hoặc không mất theo nghĩa vụ pháp lý | ≤ 72 giờ | Retention/immutability/soft delete + restore |

**N/A cho frontend stateless** chỉ áp dụng cho **runtime state có thể tái tạo** từ image/IaC. Nếu frontend lưu user upload, session hoặc cache không tái tạo được, dữ liệu đó có RPO riêng.

Ví dụ này cũng cho thấy **tier độ sẵn sàng** và **mức bảo tồn dữ liệu** đôi khi phải xét riêng. Kho hóa đơn không cần online trong 15 phút, nhưng tài liệu pháp lý có thể không được phép mất dù chỉ một file.

## 13. Tính RPO/RTO cho kịch bản Orders API

Giả sử nghiệp vụ phê duyệt:

- Orders API và PostgreSQL có RPO mục tiêu 5 phút, RTO mục tiêu 60 phút.
- Transaction rate giờ cao điểm: 120 giao dịch/phút.
- Sự cố ảnh hưởng database và Cloud Run app từ 14:00.
- Recovery point đã được phục hồi và đối chiếu có timestamp 13:56.
- 14:08 hoàn tất quyết định DR.
- 14:32 database mới sẵn sàng.
- 14:43 backend kiểm tra nghiệp vụ PASS.
- 14:49 frontend mở traffic và người dùng đặt đơn thành công.

Kết quả đo:

\[
RPO_{\text{đo}} = 14{:}00 - 13{:}56 = 4\ \text{phút}
\]

\[
RTO_{\text{đo}} = 14{:}49 - 14{:}00 = 49\ \text{phút}
\]

Về mặt thời gian, phép thử này **đạt** target 5 phút và 60 phút, nhưng chỉ có giá trị nếu recovery point thực sự nhất quán và số đơn hàng đối chiếu chính xác. Số giao dịch có nguy cơ cần reconciliation theo rate trung bình:

\[
120 \times 4 = 480\ \text{giao dịch}
\]

Nếu nghiệp vụ không chấp nhận bất kỳ giao dịch đã xác nhận nào bị mất, dù RPO tính bằng thời gian là 5 phút, thiết kế cần thêm durable order event hoặc reconciliation/replay. Điều này cho thấy một RPO thời gian không đủ thay thế tiêu chí toàn vẹn giao dịch.

### 13.1. Khi chỉ có daily backup

Nếu backup chạy mỗi ngày lúc 01:00, sự cố xảy ra lúc 23:45, điểm khôi phục gần nhất có thể cũ 22 giờ 45 phút. Thiết kế này không đáp ứng RPO 5 phút, cho dù thao tác restore diễn ra nhanh.

### 13.2. Khi PITR có thể phục hồi gần thời điểm lỗi

PITR có thể tạo recovery point gần hơn daily backup, nhưng phải kiểm tra thời gian transaction log khả dụng, tính nhất quán và khả năng tạo instance mới. RPO actual lấy từ **điểm có thể restore thành công**, không phải chỉ từ cờ "PITR enabled".

## 14. RTO end-to-end là đường găng, không phải tổng thời gian mỗi máy

Trong hệ thống nhiều thành phần, một số bước chạy song song; RTO của toàn workload bị quyết định bởi **critical path** từ incident đến lúc nghiệp vụ chạy được.

~~~mermaid
flowchart TD
    INC["Incident"] --> DEC["Declare DR"]
    DEC --> DATA["Restore / promote database"]
    DEC --> APP["Deploy app region dự phòng"]
    DEC --> IAM["Kiểm tra IAM / Secret / KMS"]
    DATA --> INT["Integration validation"]
    APP --> INT
    IAM --> INT
    INT --> TRA["Switch traffic"]
    TRA --> BIZ["Business smoke test"]
~~~

Ví dụ database cần 45 phút, deploy app 15 phút, IAM 10 phút, và các bước cùng bắt đầu sau quyết định DR. Nếu integration validation cần 10 phút, chuyển traffic 5 phút, business test 5 phút, thì RTO không phải 45+15+10+10+5+5 = 90 phút theo cách cộng giản đơn. Nếu các nhánh chạy song song, đường găng có thể là 45+10+5+5 cộng thời gian detect/decision.

Ngược lại, nếu app không thể dựng trước khi có DB hoặc IAM cần cấp thủ công sau restore, RTO có thể lâu hơn kế hoạch. Nên vẽ dependency graph với duration và người chịu trách nhiệm cho từng node.

## 15. Thiết kế recovery plan từ Tier

Một recovery plan có thể theo trình tự:

1. **Chọn scenario:** mất zone, region, dữ liệu hỏng, ransomware, sai cấu hình hay lỗi đối tác.
2. **Chọn target:** RPO/RTO cho từng scenario theo BIA.
3. **Lập inventory:** dữ liệu, application, hard dependency, IAM, DNS, key và network.
4. **Chọn pattern:** cold, warm, hot hoặc tổ hợp theo thành phần.
5. **Thiết kế bảo vệ dữ liệu:** backup frequency, log retention, replication, restore point, consistency.
6. **Thiết kế phục hồi compute:** images, IaC, capacity/quota ở DR region, deployment.
7. **Thiết kế quyền và network:** recovery identities, KMS/secret replication, certificate, LB routing.
8. **Viết runbook:** ai ra quyết định, thao tác, checklist, rollback/failback.
9. **Đặt quan sát:** lag, backup success, restore time, health và traffic.
10. **Diễn tập và đo:** phải có actual RPO/RTO, kiểm tra dữ liệu, owner sign-off.
11. **Ghi exception:** target chưa đạt, thiệt hại còn lại, kế hoạch và thời hạn xử lý.

### 15.1. Thông tin không thể thiếu trong runbook

| Trường | Nội dung |
|---|---|
| Incident trigger | Điều kiện kích hoạt DR, ai được declare |
| Recovery scope | Dịch vụ và dữ liệu nào phục hồi |
| Authority | Incident commander, DBA, network lead, business owner |
| Target | RPO/RTO và RTO checkpoint |
| Prerequisites | IAM, quota, backup, credentials, KMS, images, DNS |
| Steps | Các thao tác có điều kiện và câu lệnh đã kiểm thử |
| Validation | Dữ liệu nhất quán, API, auth, giao dịch mẫu |
| Traffic cutover | DNS/LB/routing, thời điểm primary thay đổi |
| Rollback/failback | Điều kiện và cách tránh split-brain |
| Communication | Thông báo nội bộ, khách hàng, pháp lý |
| Evidence | Event timeline, logs, kết quả đo, sign-off |

Không nên đặt toàn bộ runbook duy nhất trong region/project có thể bị sự cố. Cần có bản sao và quyền truy cập khẩn cấp tách biệt, phù hợp chính sách bảo mật.

## 16. Diễn tập DR: bằng chứng quan trọng hơn việc bật backup

Một hệ thống có backup mỗi giờ nhưng chưa restore lần nào **chưa chứng minh** được RTO hoặc tính sử dụng được của dữ liệu.

### 16.1. Ma trận bài kiểm tra

| Bài diễn tập | Tần suất ví dụ | Tiêu chí |
|---|---|---|
| Khôi phục một object bị xóa nhầm | Hàng tháng | Đúng object generation và metadata |
| Restore Cloud SQL tại thời điểm cụ thể | Hàng quý | Đúng schema/dữ liệu, phục hồi theo cửa sổ |
| Khôi phục một GKE namespace | Hàng quý | Manifests/PVC/app functional |
| Deploy Cloud Run ở region dự phòng | Hàng quý | Đúng image, IAM, secrets, VPC |
| Database replica promotion | Theo lịch được phê duyệt | Đo lag, write fencing, business checks |
| Region outage tabletop | Hàng quý | Runbook, người chịu trách nhiệm, quota |
| Full DR end-to-end | Ít nhất theo chu kỳ quản trị rủi ro | Measured RPO/RTO, sign-off |

Tần suất trong bảng chỉ để minh họa. Workload Tier 0/1 có thể cần test thường xuyên hơn và thay đổi sau mỗi thay đổi kiến trúc lớn.

### 16.2. Quy trình đo actual RPO

1. Tạo một tập dữ liệu kiểm thử có event ID, commit timestamp và checksum.
2. Ghi có kiểm soát trên hệ nguồn ở gần thời điểm giả lập sự cố.
3. Chốt thời điểm incident T_incident.
4. Phục hồi theo runbook, không thay đổi target ở giữa nếu không cần.
5. Kiểm tra ID/timestamp cuối cùng đã **commit và còn nhất quán**.
6. Tính actual RPO = T_incident - latest recoverable committed timestamp.
7. So sánh mục tiêu và ghi các bản ghi cần reconciliation.

Nếu dùng async replication, không lấy "lag báo cáo gần 0" thay cho việc xác minh transaction boundary thực trên bản phục hồi.

### 16.3. Quy trình đo actual RTO

1. Ghi thời điểm workload không còn đáp ứng business SLO.
2. Ghi thời điểm phát hiện, quyết định DR, bắt đầu restore, data ready, app ready.
3. Ghi kết quả technical smoke tests và business validation.
4. Chuyển traffic, kiểm tra chức năng cuối cùng.
5. Ghi thời điểm người dùng có thể hoàn tất luồng nghiệp vụ chính.
6. Tính actual RTO từ thời điểm outage đến thời điểm business function được khôi phục.
7. Đối chiếu target, gắn nguyên nhân chậm và action items.

Nên giữ event timeline với timestamp UTC/ISO 8601 để tránh nhầm timezone khi nhiều nhóm hoặc region phối hợp.

## 17. Phân biệt disaster recovery và business data reconciliation

Một hệ thống có thể vừa đạt RTO vừa có dữ liệu nghiệp vụ thiếu nhất quán. Ví dụ Orders API mở lại trong 30 phút, nhưng 200 đơn hàng đã gửi email xác nhận chưa tồn tại trong database mới.

Vì vậy tiêu chí nghiệm thu DR gồm:

- **Availability:** API hoặc website phục vụ lại.
- **Integrity:** database, file và event log nhất quán.
- **Correctness:** các nghiệp vụ cốt lõi chạy đúng.
- **Security:** IAM, encryption, network, auditing sau failover không bị suy giảm.
- **Financial reconciliation:** giao dịch không mất hoặc có sổ đối soát/đền bù đã phê duyệt.
- **Recoverability:** backup/DR mới tiếp tục hoạt động sau khi failover.

Khi ứng dụng đã ghi vào secondary, không đơn giản chuyển traffic về primary cũ. Cần chiến lược **failback** và xác định nguồn dữ liệu sự thật (source of truth), phòng tránh split-brain.

## 18. Ransomware và backup bất biến

DR không chỉ chống thiên tai hay lỗi hạ tầng. Xóa nhầm, tài khoản quản trị bị chiếm hoặc ransomware thường làm bản sao trực tuyến cũng bị sửa/xóa.

Các lớp bảo vệ quan trọng:

1. Backup không nằm trong cùng ranh giới quyền với application runtime.
2. Bật retention/immutability theo yêu cầu trong Backup and DR backup vault hoặc giải pháp phù hợp.
3. Thiết kế least privilege, IAM Conditions và audit logs cho thao tác xóa/sửa backup.
4. Bảo vệ KMS key, secret và breakglass identity; quản lý vị trí key nếu phải restore cross-region.
5. Tạo nhiều recovery points, không giữ đúng một bản mới nhất.
6. Kiểm tra malware/corruption và xác định thời điểm sạch trước khi restore.
7. Lưu bằng chứng thử nghiệm và runbook trong vị trí có thể truy cập khi primary project lỗi.

**Sao chép dữ liệu hỏng rất nhanh không phải là DR thành công.** Cần cả bản sao hoạt động và recovery points sạch theo thời gian.

## 19. Chi phí và trade-off của mục tiêu nghiêm ngặt

RPO/RTO thấp thường cần:

- Replication thường xuyên hoặc đồng bộ theo kiến trúc chấp nhận được.
- Compute standby được khởi chạy hoặc có khả năng provision nhanh.
- Quota và capacity tại region dự phòng.
- Backup retention, data transfer, storage, monitoring.
- Automation, failover scripts, tests và nhân sự trực.
- Thiết kế consistency, fencing và failback phức tạp hơn.

| Chi phí | Cold | Warm | Hot |
|---|---|---|---|
| Standby compute | Thấp | Một phần | Cao |
| Replication/data transfer | Tùy backup | Liên tục hoặc thường xuyên | Thường liên tục |
| Automation | Cần để giảm RTO | Nên có | Gần như bắt buộc |
| Kiểm thử failover | Cần | Cần | Cần và phức tạp |
| Thời gian phục hồi mục tiêu | Thường dài | Trung bình | Thường ngắn |

Với Tier 3, đầu tư active-active hai region có thể không hợp lý so với cold backup + IaC. Với Tier 0, chỉ dựa vào snapshot mỗi ngày thường không đạt yêu cầu. Quyết định kinh tế nên so sánh **chi phí giải pháp DR** với **thiệt hại kỳ vọng khi hệ thống không phục hồi kịp**, nhưng không bỏ qua các nghĩa vụ bảo vệ dữ liệu không thể quy ra tiền.

## 20. Các lỗi thường gặp khi xác định RPO/RTO

| Sai lầm | Vì sao nguy hiểm | Cách sửa |
|---|---|---|
| Mọi workload đều chọn RPO=0/RTO=0 | Chi phí và độ phức tạp có thể phi thực tế | BIA, xác định giới hạn và trade-off |
| Dùng tần suất backup làm RPO cam kết | Backup lỗi/trễ, chưa test restore | Đo actual recoverable point |
| Chỉ đo thời gian tạo VM mới | Bỏ qua detect, restore DB, IAM, smoke test, traffic | Đo RTO end-to-end |
| Gọi regional HA là multi-region DR | Region outage vẫn có thể làm dừng service | Thiết kế failure domain theo scenario |
| Coi async replica là backup | Xóa nhầm/ransomware có thể lan theo replica | Backup lịch sử và immutability |
| Không xếp tier cho IAM/DNS/KMS | DR app có thể thất bại vì thiếu quyền/key | Xem chúng là recovery dependencies |
| Tier được kỹ thuật tự chọn | Không phản ánh thiệt hại của nghiệp vụ | Business owner phê duyệt |
| RTO nhỏ hơn thời gian restore đã đo | Target không thực tế | Chuyển pattern hoặc đàm phán mục tiêu |
| Không kiểm tra business transaction | API healthy nhưng dữ liệu sai | Reconciliation và sign-off |
| Không có owner DR | Không ai dám promote/route production | Runbook và quyền quyết định rõ |
| Không kiểm tra capacity ở DR region | Failover gặp quota/capacity block | Quota review và capacity reservation nếu phù hợp |
| Không tính failback | Hai primary cùng nhận writes | Fencing và reconcile trước switchback |
| Không cập nhật tier khi workload đổi | Mục tiêu lỗi thời sau scale hoặc chuyển nghiệp vụ | BIA review định kỳ |

## 21. Bài thực hành: phân hạng bốn workload

Giả sử công ty bán hàng trực tuyến triển khai:

- **Orders API:** 100–300 đơn/phút, mỗi đơn đã xác nhận phải được xử lý đúng.
- **Identity service:** phần lớn API cần token đăng nhập; có fallback một số route nhưng không phải tất cả.
- **Analytics ETL:** dữ liệu lấy từ đơn hàng, có thể replay trong ngày.
- **Archive invoices:** truy xuất thưa, nhưng hóa đơn phải được lưu đúng hạn luật định.

### Nhiệm vụ 1: điền BIA

Cho mỗi workload, điền ảnh hưởng sau 15 phút, 1 giờ, 8 giờ, 24 giờ; khả năng workaround; có thể replay hay không; dependencies và owner.

### Nhiệm vụ 2: đề xuất tier

Một phân loại khởi đầu có thể là:

| Workload | Tier tham khảo | Cần lưu ý |
|---|---|---|
| Orders API | Tier 1 | RPO có thể phải chặt hơn nếu không được mất đơn |
| Identity | Tier 1 | Hard dependency của nhiều service, xem xét Tier 0 nếu toàn doanh nghiệp phụ thuộc |
| Analytics ETL | Tier 2 | RPO có thể dài vì replay được |
| Archive invoices | Tier 3 về truy cập; bảo vệ dữ liệu theo nghĩa vụ pháp lý | Không đánh đồng truy cập chậm với quyền mất tài liệu |

### Nhiệm vụ 3: chọn pattern

Với mỗi workload, đề xuất cold/warm/hot, GCP building blocks, estimated cost drivers và kế hoạch diễn tập. Không chỉ chọn theo tier: cần kiểm tra workload characteristics và dữ liệu cần bảo vệ.

### Nhiệm vụ 4: mô phỏng sự cố

Giả lập Orders API ngừng lúc 13:00, recovery point nhất quán gần nhất ở 12:58, API phục vụ lại và business smoke test PASS lúc 13:42.

\[
RPO_{\text{đo}} = 2\ \text{phút}, \qquad
RTO_{\text{đo}} = 42\ \text{phút}
\]

Nếu target là RPO ≤5 phút và RTO ≤60 phút thì trường hợp giả lập này đạt theo hai chỉ số, với điều kiện đã xác minh consistency. Lưu lại record của bài diễn tập và đặt action item nếu còn dependency chưa được test.

## 22. Checklist phê duyệt chính sách DR

- [ ] Có business owner và technical owner của từng workload.
- [ ] BIA đánh giá ảnh hưởng theo thời gian và khung giờ quan trọng.
- [ ] Có mục tiêu RPO, RTO và MTPD rõ ràng, có chữ ký phê duyệt.
- [ ] Phân hạng Tier được ghi nhận là chính sách nội bộ, không nhầm SLA của GCP.
- [ ] Có inventory dữ liệu, dependency graph và recovery dependencies.
- [ ] Mỗi failure scenario có recovery scope và mục tiêu phù hợp.
- [ ] HA, backup, replication và DR được phân biệt trong kiến trúc.
- [ ] Chọn cold/warm/hot dựa trên yêu cầu, tính khả thi và chi phí.
- [ ] Cloud SQL PITR/backup được bật và xác minh theo edition/config thực tế.
- [ ] Compute Engine/GKE/Cloud Run/Cloud Storage có đường phục hồi riêng.
- [ ] Secrets, IAM, KMS, DNS, load balancer, network và quota được tính trong RTO.
- [ ] Có bảo vệ backup trước xóa nhầm và ransomware.
- [ ] Có test khôi phục và dữ liệu test, không chỉ kiểm tra backup job success.
- [ ] Đo actual RPO/RTO, data integrity và business outcome sau diễn tập.
- [ ] Có quy trình failback không gây split-brain hoặc mất giao dịch.
- [ ] Không có target chưa đạt bị báo cáo như đã đạt; exception có owner và deadline.
- [ ] Có budget, alert và chu kỳ review BIA/DR plan.

## 23. Câu hỏi tự kiểm tra

**1. RPO 15 phút và RTO 1 giờ khác nhau ở đâu?**

RPO 15 phút giới hạn độ cũ của dữ liệu có thể phục hồi tại sự cố. RTO 1 giờ giới hạn thời gian gián đoạn đến khi nghiệp vụ hoạt động trở lại.

**2. Nếu backup chạy mỗi 30 phút, có chắc RPO = 30 phút không?**

Không. Backup có thể trễ, lỗi, dữ liệu chưa nhất quán hoặc không dùng được ở recovery site. Phải kiểm tra recovery point thực tế sau restore.

**3. Vì sao một hệ thống Tier 3 vẫn có thể cần bảo vệ dữ liệu rất nghiêm ngặt?**

Hệ thống có thể không cần online ngay nhưng lưu hóa đơn, hồ sơ hoặc dữ liệu phải giữ theo luật. RTO dài không đồng nghĩa được phép mất dữ liệu.

**4. Sự khác nhau giữa HA và DR?**

HA thường giảm gián đoạn do lỗi thành phần như VM/zone. DR bao gồm tình huống lớn hơn như mất region, dữ liệu hỏng hoặc ransomware và cần khả năng khôi phục dữ liệu/nghiệp vụ.

**5. Vì sao Cloud SQL cross-region replica không thay thế PITR/backup?**

Replica có thể sao chép thay đổi sai hoặc xóa nhầm. PITR/backup cung cấp các recovery points lịch sử để quay về trước khi dữ liệu bị phá hỏng.

**6. Muốn đo RTO đúng, phải dừng đồng hồ ở đâu?**

Khi người dùng hoặc luồng nghiệp vụ chính đã có thể hoạt động lại, sau khi dữ liệu, auth, dependencies và traffic được xác nhận; không dừng khi VM vừa Ready.

**7. Vì sao KMS, IAM và DNS có thể ảnh hưởng Tier của Orders API?**

Đây là hard hoặc recovery dependencies. Nếu thiếu key/quyền hoặc routing thì Orders không dùng được, dù container và database đã phục hồi.

**8. RPO gần 0 có luôn cần active-active không?**

Không nhất thiết. Cần phân tích giao dịch, consistency, replication và khả năng replay. Active-active không tự bảo đảm zero loss và có thể tăng khó khăn về conflict/failback.

## 24. Tài liệu tham khảo

- [Google Cloud Architecture Center: Disaster recovery planning guide](https://cloud.google.com/architecture/dr-scenarios-planning-guide)
- [Disaster recovery building blocks](https://cloud.google.com/architecture/dr-scenarios-building-blocks)
- [Disaster recovery scenarios for applications](https://cloud.google.com/architecture/dr-scenarios-applications)
- [Disaster recovery scenarios for data](https://cloud.google.com/architecture/dr-scenarios-data)
- [Cloud SQL for PostgreSQL: Backup and recovery overview](https://cloud.google.com/sql/docs/postgres/backup-recovery/backups)
- [Cloud SQL for PostgreSQL: Restore an instance](https://cloud.google.com/sql/docs/postgres/backup-recovery/restore)
- [Cloud SQL for PostgreSQL: Configure point-in-time recovery](https://cloud.google.com/sql/docs/postgres/backup-recovery/configure-pitr)
- [Cloud SQL for PostgreSQL: Perform point-in-time recovery](https://cloud.google.com/sql/docs/postgres/backup-recovery/pitr)
- [Google Cloud Backup and DR overview](https://cloud.google.com/backup-disaster-recovery/docs/concepts/backup-dr)
- [Backup for GKE overview](https://cloud.google.com/kubernetes-engine/docs/add-on/backup-for-gke/concepts/backup-for-gke)
- [Compute Engine: About disk snapshots](https://cloud.google.com/compute/docs/disks/snapshots)
- [Cloud Storage: Availability and durability](https://cloud.google.com/storage/docs/availability-durability)
- [Cloud Storage: Object Versioning](https://cloud.google.com/storage/docs/object-versioning)
- [Cloud Storage: Soft delete](https://cloud.google.com/storage/docs/soft-delete)

