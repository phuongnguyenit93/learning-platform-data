# Diễn tập khôi phục và đo kết quả so với mục tiêu

> **Ngữ cảnh:** Software Design Architecture → System Architecture → Microservices → Khôi phục thảm họa. Tài liệu trình bày cách thiết kế, tổ chức và đo lường diễn tập khôi phục thảm họa (disaster recovery drill/exercise) để chứng minh hệ thống có thể phục hồi đúng **thời gian, dữ liệu, tính nhất quán nghiệp vụ và mức dịch vụ** đã cam kết. Trọng tâm là RTO, RPO, quy trình game day, backup/PITR, chuyển vùng, dịch vụ phụ thuộc, recovery runbook, bằng chứng thực nghiệm và vòng cải tiến.

## 1. Vì sao “có backup” chưa đồng nghĩa “khôi phục được”?

Một kiến trúc microservices có thể lưu bản sao database định kỳ, chạy nhiều Pod trên Kubernetes và nhân bản dữ liệu qua hai vùng, nhưng vẫn không thể phục hồi đúng lúc khi gặp sự cố nghiêm trọng. Một số tình huống điển hình:

- Backup tồn tại nhưng chưa ai thử restore; khi cần mới phát hiện thiếu extension, thiếu khóa mã hóa, sai phiên bản DB hoặc backup bị lỗi.
- Database đã restore nhưng service chưa Ready vì secret/certificate, DNS, IAM hoặc network policy chưa được tạo ở vùng dự phòng.
- Ứng dụng có thể khởi động nhưng hàng đợi message, outbox, idempotency record hoặc trạng thái thanh toán bị thiếu so với dữ liệu DB đã phục hồi.
- Region failover hoạt động về mặt hạ tầng nhưng client/mobile vẫn dùng DNS cache, token issuer cũ hoặc endpoint bên thứ ba chưa whitelist IP vùng mới.
- Sao chép dữ liệu bất đồng bộ tạo độ trễ replication; số liệu “replica healthy” không chứng minh điểm khôi phục (RPO) đáp ứng mục tiêu.
- Đội vận hành không biết ai có quyền thực hiện failover, ai xác nhận dữ liệu nghiệp vụ và ai ra quyết định quay về vùng chính.
- Việc khôi phục hoàn tất trên dashboard nhưng người dùng không thể tạo đơn, thanh toán hoặc truy xuất trạng thái đơn.

**DR drill** là một thí nghiệm có kiểm soát nhằm kiểm chứng **khả năng phục hồi thực tế**, không chỉ kiểm tra sự tồn tại của kế hoạch. Nếu một bài diễn tập không ghi thời điểm, kết quả, bằng chứng và sai lệch so với mục tiêu thì rất khó chứng minh hệ thống sẵn sàng trước thảm họa.

**Nguyên tắc:** Kiến trúc DR là một giả thuyết; diễn tập và phép đo biến giả thuyết thành bằng chứng.

## 2. Phân biệt availability, resilience, disaster recovery và business continuity

| Khái niệm | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| High availability (HA) | Thành phần lỗi nhỏ có được tự thay thế mà không làm gián đoạn đáng kể? | Một Pod hoặc node hỏng, traffic chuyển sang replica còn khỏe |
| Resilience | Hệ thống chịu lỗi và giảm tác động thế nào? | Circuit breaker, retry budget, queueing, load shedding |
| Disaster recovery (DR) | Khi mất một phần hạ tầng/trạng thái lớn, khôi phục ở đâu và bao lâu? | Khôi phục DB từ backup hoặc failover sang region dự phòng |
| Business continuity (BC) | Doanh nghiệp tiếp tục hoạt động hoặc vận hành thủ công thế nào trong thời gian công nghệ gián đoạn? | Tiếp nhận đơn qua kênh dự phòng, đối soát sau |
| Incident response | Ai nhận sự cố, điều phối, giảm tác động và thông báo? | On-call, incident commander, runbook, stakeholder updates |
| Backup/restore | Có bản dữ liệu có thể dùng để khôi phục không? | Full backup + WAL/PITR + restore test |
| Failover/failback | Đổi nơi phục vụ sang hệ dự phòng và quay lại an toàn? | Active-passive regional traffic switch |

Không phải mọi sự cố đều là thảm họa. Một lần Pod restart thường xử lý bằng HA, không cần kích hoạt DR. DR cần cho các tình huống vượt khả năng phục hồi tự động thông thường: mất toàn vùng, corruption lan sang replica, xóa dữ liệu quan trọng, ransomware, mất khả năng truy cập control plane hoặc lỗi dependency kéo dài.

**Diễn tập phải nêu chính xác phạm vi mất mát**. “Tắt một Pod và nó tự lên lại” là bài resilience/HA, không chứng minh khôi phục region hoặc restore từ backup sẽ đạt RTO/RPO.

## 3. Các mục tiêu phải định nghĩa trước: RTO, RPO và mức dịch vụ

### 3.1. Recovery Time Objective (RTO)

**RTO** là khoảng thời gian mục tiêu tối đa cho phép từ mốc gián đoạn được định nghĩa đến lúc **khả năng phục vụ tối thiểu đã cam kết** được khôi phục.

Ví dụ: “Khi mất region chính, hành trình tạo đơn phải hoạt động trở lại trong 60 phút”. Cần ghi rõ:
- Bắt đầu đo từ khi sự cố thực tế bắt đầu, khi phát hiện sự cố hay khi tuyên bố DR? Những mốc này khác nhau; nên giữ đầy đủ cả ba.
- Điều gì được gọi là “hoạt động trở lại”: HTTP 200, tạo đơn bền vững, có thanh toán, hay số lượng lỗi đã trở về ngưỡng?
- Tỷ lệ traffic, tenant, region, năng lực xử lý và SLO phục hồi tối thiểu là bao nhiêu?

Chỉ đo từ lúc người vận hành bấm nút restore sau 20 phút triage sẽ **không phản ánh toàn thời gian gián đoạn từ góc nhìn khách hàng**. Có thể đo cả “technical recovery duration” từ khi kích hoạt quy trình, nhưng khi đánh giá RTO phải dùng mốc đã chốt trước để tránh thay đổi định nghĩa sau diễn tập.

### 3.2. Recovery Point Objective (RPO)

**RPO** là mức mất dữ liệu tối đa chấp nhận được tính theo thời gian tại thời điểm gián đoạn, không phải thời gian restore. Ví dụ RPO 5 phút có nghĩa trạng thái phục hồi không được bỏ sót các thay đổi bền vững quá 5 phút trước thời điểm sự cố theo định nghĩa dữ liệu liên quan.

Nếu database restore tới transaction cuối cùng ở 10:57 và thảm họa xảy ra lúc 11:00, thì **data recovery lag theo thời gian xấp xỉ 3 phút**. Nhưng nếu có một giao dịch thanh toán quan trọng lúc 10:58 bị thiếu, cần ghi nhận số bản ghi/tác động nghiệp vụ bị thiếu; “3 phút đạt RPO 5 phút” không có nghĩa đã đạt tính đúng đắn nghiệp vụ tuyệt đối.

RPO không có nghĩa mất dữ liệu được phép tùy ý. Một số domain như sổ cái thanh toán có thể yêu cầu không mất giao dịch đã xác nhận, cần thiết kế journal, đối soát với provider và cơ chế phục hồi khác.

### 3.3. Những mục tiêu bổ sung

- **Maximum Tolerable Period of Disruption (MTPD/MAO):** thời gian gián đoạn tối đa doanh nghiệp chịu được trước hậu quả không thể chấp nhận.
- **Work Recovery Time (WRT):** thời gian để hoàn tất việc phục hồi thao tác nghiệp vụ sau khi hệ công nghệ nền đã khả dụng, nếu tổ chức định nghĩa riêng.
- **Minimum Business Continuity Objective (MBCO):** mức dịch vụ tối thiểu cần duy trì trong khủng hoảng.
- **Recovery capacity:** phần trăm năng lực xử lý có thể phục vụ tại vùng phục hồi và thời gian đạt lại công suất đầy đủ.
- **Consistency objective:** độ đúng của đơn hàng, thanh toán, sự kiện, số dư và trạng thái cross-service.
- **Detection time:** khoảng thời gian từ khi gián đoạn đến lúc có tín hiệu và được xác nhận.
- **Escalation/decision time:** thời gian chờ quyền và quyết định kích hoạt DR.
- **Failback objective:** mức rủi ro và khoảng thời gian được phép khi quay về hệ chính.

RTO/RPO là hai trục khác nhau: restore nhanh từ một bản backup cũ có thể đạt RTO nhưng không đạt RPO; giữ dữ liệu rất mới trên một replica bị cô lập nhưng failover chậm cũng có thể đạt RPO mà trượt RTO.

## 4. Ánh xạ mục tiêu theo hành trình người dùng và dữ liệu

Không bắt đầu bằng “database của chúng ta RPO 15 phút”, mà hỏi **hành trình và dữ liệu nghiệp vụ nào cần được bảo vệ**.

| Hành trình / tài sản | Mục tiêu minh họa | Mức ưu tiên | Điều kiện khôi phục |
| --- | --- | --- | --- |
| Xác nhận thanh toán và đối soát | RTO 30 phút; không mất giao dịch đã ghi nhận | Rất cao | Ledger/transaction consistency, provider reconciliation |
| Tạo và tra cứu đơn | RTO 60 phút; RPO 5 phút có cơ chế phục hồi chênh lệch | Cao | Order state, outbox, idempotency records |
| Kiểm tra tồn kho | RTO 90 phút; dữ liệu nhất quán với reservation | Cao | Quantity/reservation được đối soát |
| Xem sản phẩm | RTO 2 giờ; có thể dùng cache hợp lệ | Trung bình | Mở được danh mục và tìm kiếm cơ bản |
| Recommendations | RTO 24 giờ hoặc degrade tạm | Thấp hơn | Ẩn/tải sau được mà không ảnh hưởng checkout |
| Analytics batch | Có thể trì hoãn, cần replay đầy đủ | Theo nhu cầu | Dữ liệu có thể rebuild từ event source |

Các mục tiêu trên chỉ để giải thích, **không phải mặc định** cho doanh nghiệp cụ thể. Phải quyết định theo BIA (Business Impact Analysis), nghĩa vụ pháp lý, contractual SLA, dữ liệu và trade-off chi phí.

Khi một hành trình phụ thuộc nhiều service, đặt RTO của hành trình dựa trên **đường găng phục hồi**, không phải lấy RTO của một service duy nhất. Payment đã hoạt động nhưng Order chưa restore thì checkout vẫn chưa đạt RTO.

## 5. Chuẩn bị Business Impact Analysis (BIA) cho bài diễn tập

Trước khi chọn kịch bản, tập hợp:

1. Hành trình nào tạo doanh thu, giao dịch hoặc nghĩa vụ pháp lý?
2. Gián đoạn 5 phút, 1 giờ, 4 giờ, 24 giờ gây hậu quả gì?
3. Dữ liệu nào có thể tái tạo, dữ liệu nào là authoritative, dữ liệu nào không thể mất?
4. Dependency nội bộ/bên ngoài nào nằm trên critical path?
5. Có cơ chế vận hành thủ công hoặc degraded mode nào chấp nhận được?
6. Năng lực tối thiểu lúc khôi phục là bao nhiêu phần trăm tải đỉnh?
7. Quy định retention, residency, privacy, contractual obligations?
8. Ai chấp thuận mức mất dữ liệu và thời gian gián đoạn mục tiêu?
9. Có đủ ngân sách cho warm standby, backup, cross-region replication không?
10. Diễn tập có thể làm gián đoạn production hay không, quy trình phê duyệt là gì?

BIA giúp tránh xây dựng kiến trúc active-active cực đắt cho một báo cáo nội bộ có thể chạy lại sau một ngày, trong khi bỏ qua luồng thanh toán có yêu cầu mất dữ liệu gần bằng không.

## 6. Các cấp diễn tập: từ tabletop đến full failover

| Cấp | Bài diễn tập | Bằng chứng thu được | Điều chưa chứng minh |
| --- | --- | --- | --- |
| L0 – Documentation walk-through | Cùng đọc runbook, kiểm tra owner/link/permission | Kế hoạch có người hiểu, tài liệu không bị lạc | Không chứng minh restore thật |
| L1 – Tabletop | Mô phỏng sự cố, ra quyết định trên giấy/bridge | Escalation, vai trò, timeline, giao tiếp | Không đo chính xác RTO kỹ thuật |
| L2 – Restore isolated | Restore backup vào môi trường riêng | Backup dùng được, schema/data integrity, thời gian restore | Không chứng minh routing/capacity production |
| L3 – Component or dependency failure | Ngắt một dependency test, test replay/failover | Resilience/restore theo phạm vi service | Không chứng minh mất toàn region |
| L4 – Workflow/region rehearsal | Chạy các service và dependency thật trong môi trường tạm/dự phòng | End-to-end recovery, DNS/IAM/network, cross-service consistency | Có thể khác tải và quyền production |
| L5 – Controlled production game day | Chuyển traffic/failover thật trong giới hạn được phê duyệt | Bằng chứng gần nhất với điều kiện thực | Rủi ro cao, không thay kiểm tra data corruption |

Có thể tổ chức **tabletop thường xuyên**, restore backup hàng tuần/tháng theo rủi ro, và full regional drill theo lịch ít hơn với sự chuẩn bị kỹ. Không có lịch chung cho mọi hệ thống; chọn theo độ quan trọng, thay đổi kiến trúc và yêu cầu kiểm toán.

**Không tuyên bố đạt regional RTO** chỉ dựa trên thời gian một database restore test trong lab. Báo cáo cần ghi rõ **cấp diễn tập và những thành phần bị loại khỏi phạm vi**.

## 7. Thư viện kịch bản thảm họa nên được ưu tiên theo rủi ro

Một số kịch bản:

- **Mất toàn availability zone:** node/storage/network trong một zone không khả dụng.
- **Mất region:** ingress, service, database, broker và tài nguyên quản lý trong region chính không dùng được.
- **Lỗi control plane hoặc quyền quản trị:** không thể deploy/scale/xem trạng thái dù workload có thể còn chạy.
- **Database corruption:** lỗi dữ liệu lan sang replica; failover sang replica không chữa được, phải PITR tới trước thời điểm corruption.
- **Xóa dữ liệu nhầm:** bảng/object/topic bị xóa hoặc schema migration phá dữ liệu; backup/restore cần chứng minh.
- **Ransomware/credential compromise:** phải bảo vệ backup bất biến và tách credential; ứng phó phải phối hợp security, không khôi phục ngay vào môi trường còn bị chiếm quyền.
- **Object storage bucket bị lỗi/xóa:** app, media, artifact hoặc snapshot không truy cập được.
- **Message broker mất dữ liệu:** event logs, consumer offsets, outbox và DLQ có thể không đồng bộ với DB.
- **Secret/KMS outage:** có bản backup nhưng không giải mã được vì khóa hoặc access policy vắng mặt.
- **DNS/traffic routing failure:** vùng dự phòng đã khỏe nhưng người dùng vẫn đi vào endpoint chết.
- **Provider ngoài lỗi:** payment, email, identity provider hoặc DNS công cộng gián đoạn.
- **Network partition/split-brain:** hai phía nghĩ mình là primary, gây ghi trùng hoặc bất nhất.
- **Human error:** khôi phục nhầm version, chạy lệnh trên sai namespace, dùng sai runbook.

Một bài diễn tập nên chỉ định rõ **failure injection**, duration, mức cô lập, dữ liệu nào bị ảnh hưởng và điều kiện được phép dừng.

## 8. Phạm vi kiểm soát: không biến diễn tập thành sự cố thật

Mọi DR drill có thể tác động tới dữ liệu và traffic. Trước khi thực hiện:

- Có **owner, incident commander/drill lead, technical leads và observer** được chỉ định.
- Đã chọn môi trường phù hợp (local/staging/isolated clone/pre-production/controlled production).
- Có change approval theo rủi ro và thông tin tới stakeholder.
- Có pre-flight backup/snapshot và xác nhận khôi phục được theo chính sách.
- Có kill switch, rollback route, quỹ thời gian và ranh giới tài nguyên được phép tác động.
- Có dữ liệu synthetic hoặc tenant canary có thể xóa an toàn; không “thử xóa bảng production”.
- Có quyền hạn rõ ràng, MFA, break-glass có audit/TTL khi được phép.
- Có tiêu chí **abort immediately**: tăng lỗi quá ngưỡng, nghi mất dữ liệu, security signal, không còn đường quay lại.
- Có người theo dõi real-user SLO/capacity nếu thử trên production.
- Có kế hoạch kết thúc diễn tập, dọn tài nguyên và xác minh không còn traffic đi vào môi trường test.

**Diễn tập production có nguy cơ cao phải có sự cho phép và guardrail riêng.** Các ví dụ thao tác trong tài liệu nên được thử trên môi trường cô lập trước, không dùng làm lệnh phá hủy hạ tầng thật.

## 9. Xây dựng kế hoạch diễn tập một trang

Một exercise charter ngắn giúp tất cả thành viên hiểu điều đang được kiểm chứng:

~~~markdown
# DR Drill Charter – Checkout regional recovery

Exercise ID: DR-EXAMPLE-001
System: checkout (Gateway, Order, Inventory, Payment, DB, Broker)
Scenario: region chính không thể nhận traffic
Exercise type: isolated-region rehearsal
Environment: vùng thử nghiệm cô lập với dữ liệu tổng hợp
Business owner: Checkout Product
Drill lead: SRE / Incident Commander
Technical owners: Platform, Database, Messaging, Order, Payment
Observers: Security, QA, Business Continuity

Objective:
- User journey restore RTO <= 60 phút (min. 50% baseline capacity)
- Order data RPO <= 5 phút, kiểm tra bằng event/transaction markers
- Không có double-charge/duplicate order business effect
- Có bằng chứng end-to-end synthetic checkout hoàn tất

Start condition:
- Health của recovery environment và quyền truy cập đã xác nhận
- Bản backup/replica, test marker, dashboard sẵn sàng
- Kill switch/rollback đã được kiểm tra

Abort condition:
- Dữ liệu nằm ngoài phạm vi test bị tác động
- Không thể cô lập traffic khỏi production
- Có dấu hiệu mất toàn vẹn không thể khôi phục
- Vượt timebox hoặc thiếu người quyết định

Evidence:
- Timeline, metrics, logs/traces, data checks, config revisions
- Checklist pass/fail, action owner và kế hoạch cải tiến
~~~

Các mục tiêu và tên chỉ là minh họa. Kế hoạch nên lưu trong hệ thống quản lý thay đổi hoặc tài liệu phiên bản hóa, có review của những người chịu trách nhiệm.

## 10. Sơ đồ phụ thuộc và thứ tự phục hồi

Một hệ thống microservices hiếm khi có thứ tự restore đơn giản “start tất cả container”. Ví dụ:

~~~text
Public DNS / Edge / Ingress
          |
          v
      API Gateway
          |
          v
     Identity/Secrets
          |
          +--------------------+
          |                    |
          v                    v
    Order Service        Payment Service
       |                      |
       v                      v
   Order DB              Payment DB / Provider
       |
       v
   Outbox Publisher ---> Broker ---> Inventory / Notification consumers
                                     |
                                     v
                                Downstream DB
~~~

**Đường găng phục hồi** thường đi qua quyền truy cập/secret, data plane, DB, service bootstrap, traffic routing và nghiệp vụ validation. Một số thành phần có thể khôi phục song song nếu không phụ thuộc nhau:

- Cluster/network/IAM cho vùng dự phòng.
- Database restore/PITR và broker recovery.
- Tái tạo application workloads bằng IaC/GitOps.
- Thiết lập secrets/certificates và DNS/traffic controls.
- Nạp cache có kiểm soát sau khi DB đã sẵn sàng.
- Reconcile event/outbox và khởi động consumer.
- Chạy synthetic business journeys cuối cùng.

**Đừng bật consumer/publisher ghi dữ liệu trước khi xác định điểm phục hồi và fencing.** Nếu region cũ có thể vẫn nhận write, việc khởi động region mới có thể tạo split-brain. Cần một quyền primary rõ ràng (fencing, lease/epoch, writer routing) theo khả năng hạ tầng.

Đối với data corruption, restore cả broker và DB tới mốc không tương thích có thể làm phát lại hoặc làm mất sự kiện; phải thiết kế recovery boundary theo transaction/outbox/consumer offsets.

## 11. Đo RTO bằng timeline có mốc định nghĩa trước

Một timeline minh họa:

| Mốc | Thời điểm | Ý nghĩa |
| --- | --- | --- |
| T0 – fault begins | 10:00:00 | Region chính không còn phục vụ synthetic journey |
| T1 – detected | 10:02:20 | Alert/SLO xác nhận lỗi |
| T2 – declared | 10:05:00 | Incident commander kích hoạt DR |
| T3 – action begins | 10:08:00 | Bắt đầu restore/failover |
| T4 – infrastructure ready | 10:24:00 | Network, cluster, DB, broker đạt health cơ sở |
| T5 – applications ready | 10:37:00 | Workloads Ready, ingress/identity hoạt động |
| T6 – business verified | 10:48:00 | Synthetic checkout bền vững đạt điều kiện |
| T7 – steady state | 10:55:00 | Latency/error/capacity ổn định theo acceptance window |

Nếu RTO được định nghĩa T0 → T6, **observed RTO = 48 phút**. Nếu người báo cáo đo T3 → T5, chỉ là 29 phút kỹ thuật, không phải RTO user journey. Có thể công bố cả hai với nhãn chính xác.

Các phần của RTO quan sát được:

- Detection: T1 − T0 = 2 phút 20 giây.
- Decision/coordination: T3 − T1 = 5 phút 40 giây.
- Infrastructure and data recovery: T4 − T3 = 16 phút.
- Workload readiness: T5 − T4 = 13 phút.
- Business validation: T6 − T5 = 11 phút.
- Stabilization beyond minimal RTO: T7 − T6 = 7 phút.

Tổng của từng chặng chỉ đúng nếu mốc nối tiếp thực; khi hoạt động song song, phân tích bằng **critical path/DAG** thay vì cộng mọi task duration. Nếu các mốc không đo được, ghi rõ thời gian là ước tính và nguồn bằng chứng.

### 11.1. Đồng hồ và nguồn thời gian

- Dùng timestamp có timezone/UTC và đồng bộ đồng hồ của host.
- Dùng hệ giám sát hoặc test harness độc lập ghi mốc bắt đầu/tác động.
- Ghi cả **event time** và **ingestion time** nếu telemetry có delay.
- Với cùng một process, dùng monotonic time cho elapsed duration.
- Khi cross-region có clock skew, dùng common collector hoặc xác minh NTP/clock drift, không suy luận thứ tự chỉ từ log timestamp.
- Ghi mốc **user journey actually succeeded** thay vì chỉ lần đầu Pod Ready.

## 12. Đo RPO bằng marker dữ liệu và đối soát, không chỉ replication lag

RPO thường khó đo đúng hơn RTO. Một thiết kế phổ biến là đưa các **test markers** có timestamp/sequence vào authoritative store trước khi diễn tập, với tốc độ ghi đều và ID duy nhất.

Ví dụ bảng test trong DB cô lập:

~~~sql
CREATE TABLE recovery_probe_markers (
    marker_id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    sequence_no BIGINT NOT NULL UNIQUE,
    payload_checksum TEXT NOT NULL
);
~~~

Test writer định kỳ tạo record có sequence tăng, timestamp UTC và checksum của payload. Ghi **commit acknowledgement** bên ngoài vùng dự kiến gặp sự cố, ví dụ một controller/observer trong vùng độc lập. Sau restore, tìm **marker đã xác nhận commit cuối cùng còn hiện diện** và so sánh với tập marker đã xác nhận trước T0.

Cần cẩn trọng:

- Đừng lấy timestamp máy client chưa đồng bộ làm nguồn duy nhất.
- Không chỉ kiểm tra `MAX(created_at)` trên restored DB nếu một số marker giữa chuỗi bị thiếu.
- So sánh **tập marker/sequence contiguous**, checksum và số lượng bản ghi.
- Phân biệt marker đã commit với marker được gửi nhưng chưa xác nhận commit.
- Đo cả logical data validity: foreign keys, ledger balance, outbox/event state.
- Nếu ghi ở nhiều shard/partition, cần marker riêng theo data domain; một marker toàn DB có thể không đại diện cho mọi partition.
- Nếu sử dụng stream/CDC, kiểm tra đến log position/checkpoint cụ thể và khả năng replay.

Ví dụ T0 lúc 11:00, các marker cuối cùng đã xác nhận trước sự cố gồm số 1000 ở 10:58, 1001 ở 10:59, 1002 ở 10:59:50; sau restore chỉ còn đến 1001. Nếu marker 1001 commit ở 10:59 và marker 1002 commit sau đó đã mất, tuổi điểm phục hồi cuối là khoảng 1 phút; **không được kết luận dữ liệu không mất**. Ghi rõ phần transaction mất, khoảng thời gian và danh sách có thể tái tạo.

Nếu bất kỳ record nào bên trong khoảng đã phục hồi bị thiếu ngẫu nhiên, có thể có integrity issue dù `max timestamp` trông hợp lý.

## 13. Ghi nhận lượng dữ liệu mất và mức chênh lệch nghiệp vụ

Bên cạnh observed RPO time, báo cáo cần:

| Thước đo | Ý nghĩa |
| --- | --- |
| Last durable commit before failure | Mốc/sequence xác nhận dữ liệu trước sự cố |
| Last recovered contiguous commit | Mốc/sequence liên tục cuối cùng được tìm thấy sau restore |
| RPO observed | Chênh lệch thời gian theo định nghĩa đã chốt |
| Missing committed records | Số record đã commit nhưng không có trong restored store |
| Unexpected extra records | Dữ liệu phát sinh ở vùng khác/chưa được hợp nhất |
| Integrity validation errors | Checksum mismatch, referential integrity, balance mismatch |
| Outbox events needing replay | Event durable chưa publish/consumer chưa xử lý |
| Business transactions needing reconciliation | Thanh toán/đơn hàng/trả hàng kết quả chưa rõ |
| Data reconstruction duration | Thời gian bổ sung để phục hồi dữ liệu có thể tái tạo |
| Residual loss/exceptions | Tổn thất còn lại không thể tự khôi phục |

**RPO 5 phút không cho phép bỏ qua correctness:** Ví dụ một Order xác nhận thành công nhưng Payment Ledger bị mất hoặc Provider đã charge mà Order không biết. Cần có kế hoạch đối soát và quy định rõ dữ liệu nào **zero-loss** hoặc **recoverable via external source of truth**.

Với RPO theo thời gian, hãy ghi rõ đồng hồ, cách xác định commit và population. Không cộng các khoảng mất dữ liệu của nhiều database thành một số RPO tổng mà không giải thích consistency model.

## 14. Thiết kế backup phù hợp với diễn tập

Để restore test thực sự hữu ích, inventory backup nên có:

- Loại backup: full, incremental/differential, snapshot, WAL/binlog, PITR.
- Nguồn dữ liệu, phiên bản engine, schema và các extension.
- Backup schedule, retention, replication region/account.
- Độ trễ backup completion và verification.
- Encryption, KMS key ID và khả năng giải mã trong recovery environment.
- Access control, immutable storage/Object Lock nếu phù hợp chống ransomware.
- Kiểm tra tính nhất quán snapshot cho nhiều volume/service.
- Đường dẫn metadata/checksum và hướng dẫn tìm bản phù hợp.
- Chính sách retention của backup và dữ liệu nhạy cảm.
- Thời gian restore theo dung lượng và tốc độ storage thực tế.

**Backup success job không phải restore proof.** Một job báo “Completed” chỉ chứng minh quá trình tạo bản sao kết thúc theo logic công cụ. Diễn tập cần restore sang instance riêng và chạy integrity checks; nếu restore volume mà ứng dụng không thể giải mã dữ liệu do thiếu KMS, kết quả vẫn thất bại.

Không thử cơ chế “restore” bằng cách chạy backup trực tiếp lên database production đang hoạt động. Cần dùng instance/schema/cluster khác với network và credentials riêng.

## 15. Point-in-time recovery (PITR) cho lỗi xóa/corruption

Tình huống: một migration sai lúc 10:35 làm hỏng bảng Order. Standby replica đã nhận thay đổi xấu, nên failover replica không khắc phục được. Phải restore tới **mốc trước lỗi**, sau đó quyết định xử lý các giao dịch xảy ra giữa mốc restore và mốc hiện tại.

~~~text
10:00  Full backup / base snapshot
10:01  WAL/binlog stream
...
10:34  Last known good point
10:35  Corrupting migration
10:36  More transactions accepted (some may be valid)
10:45  Detection and DR decision
       |
       v
Restore base + replay logs to safe target
       |
       v
Validate schema/data
       |
       v
Reconcile valid transactions after target
```

Các bước phải được lập kế hoạch:

1. Xác định last known good recovery point bằng audit/change timeline.
2. Xác minh backup và toàn bộ log segments cần cho PITR có thể truy cập.
3. Khởi tạo DB restore **cô lập**, pin engine và extension.
4. Replay logs đến target đã chọn, tránh lặp lại migration corrupt.
5. Chạy integrity checks và test queries trên bản restore.
6. Xác định giao dịch hợp lệ được commit sau target; có thể cần replay từ outbox/provider/journal.
7. Phê duyệt cutover và fencing writer cũ.
8. Mở traffic theo canary và quan sát dữ liệu nghiệp vụ.

**PITR đạt RTO nhanh nhưng có thể tạo một khoảng mất logic lớn hơn RPO** nếu nhiều giao dịch xảy ra sau điểm target. Báo cáo phải phản ánh cả thời gian restore, dữ liệu không có trong bản restore và khả năng khôi phục bằng đối soát.

## 16. Khôi phục multi-service state: database không phải nguồn trạng thái duy nhất

Trong microservices, transaction có thể trải rộng Order DB, Payment DB, Inventory DB, outbox, Kafka, cache và external provider. Restore từng thành phần tới thời điểm khác nhau dẫn tới trạng thái không đồng nhất.

Ví dụ:

~~~text
Order DB:    order=PAID
Payment DB: authorization=PENDING
Provider:   payment=CAPTURED
Outbox:     OrderPaid event not yet published
Kafka:      consumer already processed OrderPaid once
Inventory:  stock reserved
```

Không thể sửa bằng cách “cho tất cả service restart”. Cần xác định:

- Authoritative source of truth cho từng domain.
- Khả năng replay event từ outbox hoặc immutable log.
- Consumer idempotency và dedupe keys.
- Sagas/compensations cho các bước đã hoàn tất một phần.
- Reconciliation với payment provider và finance/ledger.
- Snapshot/checkpoint consistency giữa các store nếu có.
- Các side effect không thể đảo ngược (email, SMS, charge, shipping dispatch).
- Quy trình đánh dấu “uncertain outcome” thay vì đoán thất bại.

Một DR drill có giá trị phải có **test giao dịch xuyên service** trước/sau failure, không chỉ đối chiếu số row của database. Ví dụ xác minh một command ID tạo đúng một order và một payment effect dù event delivery/replay xảy ra nhiều lần.

## 17. Broker recovery, offsets, outbox và DLQ

Các vấn đề thường bị bỏ sót:

- Kafka topic có retention ngắn hơn thời gian outage, event cũ mất trước khi consumer phục hồi.
- Consumer offsets được restore đến mốc khác so với DB consumer, gây skip hoặc replay message.
- Event đã publish nhưng outbox vẫn đánh dấu chưa publish khi DB khôi phục; sẽ có duplicate.
- Event đã được xử lý nhưng bảng idempotency/dedupe chưa khôi phục cùng trạng thái; redelivery sinh tác động trùng.
- DLQ và retry topics không được đưa vào backup/replication; mất danh sách sự kiện lỗi cần xử lý.
- RabbitMQ unacked deliveries được redeliver sau failover; consumer không chuẩn bị idempotency.
- Schema registry/compatibility artifacts bị thiếu ở vùng DR, consumer không deserialize được event cũ.

**Quy tắc:** Khi restore broker hoặc offset, phải đối chiếu DB consumer/outbox và bảo đảm mỗi event có business effect phù hợp. Không reset offset về latest để “lag=0” nếu điều đó bỏ qua nghiệp vụ chưa xử lý.

Diễn tập có thể tạo một tập message đánh dấu sequence, cố tình crash consumer ở điểm trước/sau commit/ack rồi khôi phục; assert dữ liệu bền vững cuối cùng và số side effects không trùng. Nếu không thể khôi phục broker đầy đủ, kế hoạch phải nêu rõ cơ chế tái tạo event từ nguồn khác.

## 18. Chuyển vùng: active-passive, pilot light, warm standby, active-active

| Chiến lược | Năng lực vùng dự phòng | Ưu điểm | Rủi ro chính |
| --- | --- | --- | --- |
| Backup and restore | Hạ tầng/DB có thể chưa chạy, khởi tạo khi cần | Chi phí vận hành thấp hơn | RTO dài, phụ thuộc provisioning và restore |
| Pilot light | Hạ tầng dữ liệu/cốt lõi duy trì ở mức tối thiểu | Phục hồi nhanh hơn cold restore | Khởi tạo app/capacity vẫn mất thời gian |
| Warm standby | Một phần hệ thống luôn chạy và nhận replication | RTO thường ngắn hơn | Chi phí và rủi ro cấu hình drift |
| Active-passive | Một site chính, site dự phòng theo chính sách | Đường đi write rõ nếu fencing tốt | Cutover, data lag, capacity và permission |
| Active-active | Nhiều region cùng nhận traffic/write | Khả năng phục vụ cao khi lỗi vùng | Consistency, conflict resolution, split-brain rất phức tạp |

Không có một chiến lược tối ưu cho mọi domain. Đối với dữ liệu tài chính, multi-writer không có quy tắc conflict rõ có thể tệ hơn active-passive. Một hệ thống không cần RTO phút có thể chọn backup/restore để giảm chi phí và độ phức tạp.

**Diễn tập phải khớp strategy thật**. Chỉ khởi động một bản copy ứng dụng ở vùng thứ hai không chứng minh failover thành công nếu database, KMS, auth, DNS và provider integration vẫn trỏ về vùng chính.

## 19. Chuỗi thao tác regional failover

Một quy trình tổng quát cho active-passive:

1. Phát hiện và phân loại tình trạng mất vùng chính.
2. Quyết định kích hoạt DR theo policy và business impact.
3. **Fencing primary writer** hoặc chứng minh vùng chính không thể tiếp tục nhận write.
4. Xác định replication position và dữ liệu có nguy cơ mất.
5. Promote standby data store và bảo vệ khỏi split-brain.
6. Kiểm tra broker/queue, schema registry, KMS, secrets và dependencies cần thiết.
7. Khởi động hoặc scale workloads vùng dự phòng, chạy readiness thực.
8. Chuyển routing (DNS/anycast/global LB/edge) theo thiết kế.
9. Chạy synthetic test theo user journey và kiểm tra security/authorization.
10. Quan sát error rate, p95/p99 latency, capacity, queue age và data reconciliation.
11. Công bố trạng thái khôi phục **có điều kiện** khi đạt mức tối thiểu đã định.
12. Tiếp tục đối soát, tăng capacity, xử lý backlog và chuẩn bị kế hoạch failback.

**DNS TTL không phải công tắc tức thời.** Client có thể cache lâu hơn TTL, kết nối HTTP/2/WebSocket còn mở và các edge proxy có chu kỳ cập nhật riêng. Phải đo hiệu quả routing bằng synthetic probes từ nhiều điểm, không chỉ nhìn record DNS mới.

Failover có thể tạo khả năng xử lý thấp hơn bình thường. Nếu mục tiêu RTO được tính ở 50% capacity, phải ghi rõ đó là **minimum recovered service**, không gọi là phục hồi full load.

## 20. Bảo vệ chống split-brain và thay đổi primary

Trong network partition, site chính có thể vẫn chạy nhưng không còn nhìn thấy control plane. Nếu site DR cũng được bật nhận write, cùng một order có thể được cập nhật khác nhau ở hai nơi.

Biện pháp theo khả năng hạ tầng:

- Quorum/leader election với fencing token hoặc epoch đơn điệu.
- Lease được kiểm soát và tính đến clock/network failure.
- Chỉ một writer được traffic router và database chấp thuận.
- Database promotion có thao tác bảo vệ/lock primary cũ.
- Application kiểm tra epoch/fencing token trước mutation trọng yếu.
- Idempotency keys và conflict detection giúp giảm side effects khi replay.
- Quy trình “quarantine old primary” trước khi reconnect/failback.

**Một diễn tập failover chỉ an toàn khi có thể xác định vùng nào được phép ghi**. Nếu không xác minh fencing, không nên mở traffic production ghi vào standby chỉ vì replica đã quảng cáo healthy.

## 21. Infrastructure as Code và configuration drift

DR chỉ có thể lặp lại nếu hạ tầng vùng dự phòng được tạo lại từ source of truth:

- Terraform/Pulumi/CloudFormation hoặc công cụ IaC tương đương.
- Kubernetes manifests/Helm/Kustomize/GitOps với version đã kiểm chứng.
- Secret references/identity roles/network policy được tái lập.
- Ingress/domain/certificate/registry access có khả năng hoạt động khi primary outage.
- Database engine/extensions/storage classes/backup repository có version phù hợp.
- Application artifacts được pin bằng immutable digest, không lệ thuộc tag latest.
- Feature flag, runtime config, migration và event schema versions tương thích.
- External providers biết IP/region/callback URLs của vùng DR khi cần.

Một diễn tập nên đo **thời gian provisioning** riêng và phát hiện những thao tác thủ công chưa được mã hóa. Nếu chỉ một người biết cách tạo subnet hoặc cấp IAM, đó là single point of failure trong runbook.

**Không đưa bí mật vào code hoặc Markdown DR plan**. IAM/KMS/secret manager cần được kiểm tra bằng test principal được cấp quyền phù hợp, đồng thời đảm bảo khôi phục được khi chính account/region chính không truy cập được.

## 22. IAM, KMS và security trong khôi phục

Restore thường đòi quyền cao. Các lỗi phổ biến:

- Bản backup được mã hóa bằng key chỉ có trong region/account đã mất.
- Recovery service account không có quyền đọc snapshot, tạo volume, promote DB hoặc cập nhật routing.
- Chứng chỉ TLS đã hết hạn, trust chain/callback URL chưa cấu hình ở vùng phụ.
- Secret được copy thủ công từ production, tạo nguy cơ rò rỉ.
- Security team không có trong kế hoạch ransomware/credential compromise.
- Cơ chế break-glass đòi vào SSO/identity provider đang outage.

Runbook cần quy định:

1. Ai có quyền kích hoạt DR và quyền tối thiểu của từng action?
2. Quyền break-glass được cấp, audit và thu hồi thế nào?
3. Backup encryption keys có thể dùng tại vùng dự phòng không?
4. Có cơ chế khôi phục identity/SSO/DNS khi dependency chính không khả dụng không?
5. Dữ liệu khôi phục có tuân thủ residency và privacy policy không?
6. Ai phê duyệt mở traffic sau khi xác minh security posture?
7. Làm sao bảo toàn forensic evidence khi nghi ransomware?
8. Khi nào cần cô lập backup immutable khỏi credential bị chiếm quyền?

Diễn tập với dữ liệu synthetic và quyền hẹp có thể kiểm tra phần lớn routing và permission. Không sử dụng tài khoản admin production chỉ để “cho test chạy dễ”.

## 23. Diễn tập khôi phục từ backup: chuỗi bước thực tế

Ví dụ bài isolated restore của Order Database:

~~~text
Pre-flight:
  - Chốt backup ID, database version, recovery target và run ID
  - Chuẩn bị VPC/namespace hoặc DB instance riêng
  - Xác minh test KMS key/access và storage quota
  - Ghi số rows/checksum/markers tại nguồn trước exercise

Execute:
  1. Bắt đầu đo thời gian từ mốc đã định
  2. Tạo instance đích cô lập
  3. Restore snapshot/base backup
  4. Apply WAL/binlog/PITR đến recovery target
  5. Start DB, kiểm tra schema/extensions
  6. Chạy integrity probes, marker checks
  7. Start Order Service với config test
  8. Chạy synthetic create/read/order state
  9. Verify outbox/idempotency/replay constraints
  10. Ghi thời gian, trạng thái và evidence

Teardown:
  - Xác minh không có traffic production vào DB test
  - Lưu evidence đã redact
  - Xóa instance, volume, secret test theo policy
~~~

Đo riêng: thời gian truy cập backup, provisioning, restore bytes, WAL replay, schema validation, service startup, business verification. Nếu restore rất nhanh nhưng kiểm tra dữ liệu mất 40 phút, đó vẫn là phần của RTO tùy mốc định nghĩa.

**Không dùng database production làm đích restore.** Việc overwrite có thể xóa dữ liệu sống và khiến “diễn tập” trở thành thảm họa thật.

## 24. Diễn tập mất broker: những điều cần xác minh

Giả sử Kafka primary không sẵn sàng, Order vẫn ghi outbox và publisher chờ. Một bài DR cần:

- Producer không làm mất event đã commit trong outbox.
- Khi broker phục hồi, publisher phát lại với message ID/idempotency key ổn định.
- Consumer khôi phục offset/checkpoint tương thích với DB side effects.
- Dedupe store đã được khôi phục để không tạo duplicate authorization/notification.
- Các topic quan trọng, partitioning, ACL, schema registry và retention được tái tạo.
- DLQ/retry topics có thể phục hồi hoặc có quy trình tái tạo.
- `oldest_message_age` giảm và throughput xử lý đủ để drain backlog.
- Không dùng “lag=0 sau reset latest” làm dấu hiệu thành công.
- Xác minh trạng thái nghiệp vụ cuối của các Order test.
- Đo thời gian từ khi broker outage đến khi workflow hoàn thành lại.

Cần phân biệt **service recovered** (broker chấp nhận message) và **business recovered** (backlog đã xử lý hoặc được quản lý trong ngưỡng). Nếu RTO chỉ yêu cầu nhận đơn mới mà backlog được drain sau, phải nêu riêng mục tiêu backlog recovery và nguy cơ dữ liệu chậm.

## 25. Kịch bản mất external provider và chế độ suy giảm

Không phải lỗi dependency bên ngoài nào cũng kích hoạt DR hạ tầng. Có thể cần business continuity:

- Payment provider chính lỗi, provider dự phòng được lựa chọn theo chính sách nếu cho phép.
- Không có provider thay thế, Order chuyển PENDING_PAYMENT và không hiển thị thành công giả.
- Thông báo email chậm nhưng checkout được commit; dùng outbox và retry.
- Identity provider không truy cập được; session hiện hành có thể tiếp tục trong giới hạn chính sách hoặc ứng dụng từ chối thao tác nhạy cảm.
- Search mất index; có thể dùng cache/catalog simplified theo dữ liệu được phép.
- DNS ngoài lỗi; global edge failover có thể cần provider/zone riêng.

Diễn tập phải kiểm tra user journey và correctness. Một payment timeout sau khi provider đã charge là kết quả không rõ; cần reconciliation trước retry, không coi “timeout” là chắc chắn thất bại.

Không bỏ authentication, authorization hoặc validation khi sang DR mode trừ khi có chính sách rủi ro cụ thể đã được phê duyệt; availability không được đánh đổi bằng vi phạm bảo mật.

## 26. Tạo synthetic business transactions để đo phục hồi

Chỉ probe GET /health/ready không đủ chứng minh hệ thống đã hoạt động. Tạo **synthetic journey** với dữ liệu an toàn:

1. Tạo test customer/tenant riêng.
2. Gửi một request đặt đơn với `commandId`/idempotency key duy nhất.
3. Xác minh Order được ghi bền vững.
4. Kiểm tra Inventory reservation và trạng thái thanh toán giả lập/sandbox.
5. Xác minh outbox event và consumer effect tương ứng.
6. Gọi read API để kiểm tra dữ liệu sau khôi phục.
7. Ghi trace ID, event IDs, timestamps và consistency check.
8. Cleanup theo chính sách, không xóa bản ghi cần làm bằng chứng trước khi lưu báo cáo.

Nên có probe chạy **trước khi kích hoạt failure, trong quá trình và sau khi recovery**. Dữ liệu probe phải đủ khả năng xác định:
- Thời điểm cuối cùng nhận transaction thành công trước lỗi.
- Thời điểm đầu tiên có transaction thành công bền vững sau lỗi.
- Những command đã được nhận nhưng không có kết quả rõ.
- Các event được phát/nhận trùng hoặc mất.
- Thời gian hoàn tất một hành trình thực tế từ góc người dùng.

Dùng test account sandbox/canary được tách khỏi khách hàng thật và giới hạn tác động. Một kết quả HTTP 200 kèm body hợp lệ vẫn chưa đủ nếu data write thực tế rollback hoặc một bước thanh toán chưa kết thúc.

## 27. Mô hình trạng thái cho bài diễn tập

Một drill có thể theo state machine:

~~~text
PLANNED
   |
   v
PRE_FLIGHT_CHECKED
   |
   v
ARMED (backup, abort, approvals verified)
   |
   v
FAILURE_INJECTED / SCENARIO_STARTED
   |
   v
DETECTED
   |
   v
DR_DECLARED
   |
   v
RECOVERING
   |
   v
TECHNICAL_SERVICE_READY
   |
   v
BUSINESS_VERIFIED
   |
   v
STABILIZING
   |
   +--> ABORTED (nếu đạt stop condition)
   |
   v
COMPLETED
   |
   v
EVIDENCE_REVIEWED / ACTIONS_ASSIGNED
```

Mỗi transition nên có:
- Timestamp và nguồn thời gian.
- Actor/automation ID chịu trách nhiệm.
- Sự kiện hoặc metric làm bằng chứng.
- Target môi trường, artifact/config version.
- Những rủi ro/thao tác còn mở.
- Điều kiện chuyển bước hoặc dừng.

Không bỏ trạng thái ABORTED khỏi báo cáo: nếu phải dừng vì nguy cơ mất dữ liệu, diễn tập chưa chứng minh được mục tiêu và vẫn tạo một phát hiện có giá trị về guardrail.

## 28. Các vai trò trong buổi diễn tập

| Vai trò | Trách nhiệm |
| --- | --- |
| Exercise sponsor/business owner | Phê duyệt mục tiêu RTO/RPO theo impact, chấp thuận phạm vi |
| Drill lead / incident commander | Điều phối, quyết định nhánh hành động và dừng diễn tập |
| Safety officer | Theo dõi blast radius, stop conditions và quyền production |
| Database recovery lead | Backup/PITR/replica, consistency và replication checkpoints |
| Platform/network lead | IaC, cluster, IAM, traffic routing, DNS, certificates |
| Messaging lead | Broker, topics/queues, consumer offsets, outbox, DLQ |
| Application/service owners | Khởi động, config, readiness, user journey correctness |
| Business verifier | Xác nhận đơn hàng/thanh toán và quy trình nghiệp vụ |
| Observer/timekeeper | Ghi mốc, evidence, sai lệch và các bước thủ công |
| Communications lead | Thông báo stakeholder, status, next update theo scope |

Một người có thể kiêm vai trò khi bài diễn tập nhỏ; với full failover không nên để cùng một người vừa thao tác nguy hiểm vừa làm timekeeper duy nhất. Người quan sát độc lập giúp đo mốc khách quan.

**Primary và secondary on-call** phải hiện diện hoặc có đường escalation rõ; một DR plan phụ thuộc duy nhất vào một kỹ sư đang nghỉ sẽ khó đạt RTO dù kiến trúc kỹ thuật hoàn hảo.

## 29. Ngân sách thời gian RTO theo từng pha

Giả sử mục tiêu phục hồi hành trình checkout 60 phút:

| Pha | Budget hoạch định | Chỉ số |
| --- | ---: | --- |
| Detection và alert acknowledgment | 5 phút | T0 → xác nhận |
| Tuyên bố DR và quyết định failover | 5 phút | Xác nhận → approve |
| Fencing + xác định recovery point | 5 phút | Quyết định → data plan |
| DB/infra recovery, chạy song song phù hợp | 20 phút | Critical recovery path |
| Khởi động app và route traffic | 10 phút | Readiness + synthetic ingress |
| Business validation, canary và ổn định tối thiểu | 10 phút | Checkout success |
| Dự phòng | 5 phút | Unknowns |
| **Tổng** | **60 phút** | |

Con số trên là phân bổ minh họa. Không được cộng thời gian của các công việc song song như thể nối tiếp; dùng critical path. Nếu chỉ riêng restore backup chiếm 50 phút khi mục tiêu là 60 phút, còn 10 phút cho detection, decision và business verification là quá ít; kiến trúc backup/standby hoặc quy trình phải được cải tiến.

**RTO target khác RTO observed.** Nếu bài diễn tập đạt 58 phút nhưng diễn ra trong giờ ít traffic với data set bằng 10% production, ghi rõ điều kiện; không suy rộng thành cam kết sẽ đạt 60 phút khi thảm họa thật xảy ra ở peak load.

## 30. Phương pháp thu bằng chứng đo lường

Bằng chứng nên có khả năng kiểm chứng độc lập:

- Alert event và SLI/RUM hoặc synthetic failure timestamps.
- Timeline từ incident bridge/chat, người thực hiện và quyết định.
- Cloud/Kubernetes events cho provisioning, scheduling, rollout và readiness.
- Backup job IDs, snapshot metadata, restore job IDs, WAL positions/checksums.
- Replication lag, last durable commit và marker sequence.
- Database integrity query results, counts/checksums, reconciliation summary.
- Logs/traces cho synthetic journeys, correlation/transaction IDs.
- DNS/global LB routing changes, endpoint health theo nhiều vị trí.
- Error rate, latency p95/p99, throughput, queue age và saturation trong recovery.
- KMS/IAM access checks và audit events (không công bố secret).
- Resource/cost footprint của DR environment, nếu quan trọng.
- Post-exercise anomalies và cleanup evidence.

**Không lưu mật khẩu, token, full database dumps hoặc dữ liệu PII vào báo cáo.** Lưu tham chiếu có quyền đến nơi bảo quản evidence phù hợp. Một screenshot dashboard không có query/window/timestamp đủ rõ có thể khó so sánh qua những lần diễn tập.

## 31. Template báo cáo kết quả diễn tập

~~~markdown
# DR Exercise Report – <exercise-id>

## Scope
- System / user journeys:
- Failure scenario:
- Environment / region / workload:
- Exercise level:
- Artifact/config revisions:
- Date/timezone:
- Drill lead, owners, observers:

## Objectives and results
| Metric | Target | Observed | Result | Evidence |
| --- | --- | --- | --- | --- |
| End-to-end journey RTO | 60 min | 48 min | Met | synthetic trace/timeline |
| Order data RPO | 5 min | 3 min | Met | marker/commit ledger |
| Missing committed business records | 0 for critical ledger | 0 | Met | reconciliation |
| Minimum capacity | 50% baseline | 45% | Not met | load test |
| First stable checkout | within RTO | T6 | Met | journey monitor |

## Timeline
- T0:
- T1:
- ...
- Tn:

## Recovery steps
- Actions, owners, decisions, risks and rollback paths.

## Data integrity
- Markers, missing transactions, outbox/offset and ledger results.

## Gaps
- What failed / what was untested / assumptions.

## Action items
- Owner, priority, due date, verification test.

## Final decision
- Meets objective / partially meets / does not meet
- Conditions for next drill.
```

Bảng trên chỉ minh họa: nếu RTO/RPO đạt nhưng capacity đạt 45% thay vì mục tiêu 50%, **bài diễn tập chưa đạt đầy đủ acceptance criteria**. Không báo “DR pass” chỉ dựa trên hai chỉ số đẹp nhất. Đối với chỉ số không đo được, ghi `NOT_MEASURED`, không tự suy đoán là đạt.

## 32. Đánh giá pass/fail theo tiêu chí định trước

Có thể đặt tiêu chí:

**RTO – PASS** khi synthetic business journey đạt điều kiện trong ngưỡng từ mốc T0 đã định nghĩa, có bằng chứng và mức traffic tối thiểu.

**RPO – PASS** khi last recovered committed state nằm trong khoảng mục tiêu và không có thiếu dữ liệu bất thường ngoài chênh lệch đã được chấp nhận theo business policy.

**Integrity – PASS** khi critical ledger/order invariants, event/outbox và idempotency checks đạt; không có duplicate hoặc unexplained missing critical transaction.

**Security – PASS** khi region DR giữ authentication/authorization/encryption và quyền least privilege theo policy; không dùng bypass nguy hiểm để làm bài diễn tập xanh.

**Operational readiness – PASS** khi runbook, on-call/escalation, provisioning, evidence và recovery actions có thể thực hiện bởi người được phân công chứ không chỉ một tác giả hệ thống.

**Capacity – PASS** khi phục vụ được mức tải tối thiểu đã cam kết với error/latency guardrails trong observation window.

Nếu một tiêu chí chưa có bằng chứng, kết luận là **not verified**, không tự động pass. Nếu đã khôi phục dịch vụ nhưng còn payment reconciliation backlog không xác định, chưa thể kết luận phục hồi nghiệp vụ hoàn tất.

## 33. Ví dụ đo bằng bảng kết quả

Giả sử hai cuộc diễn tập cùng kịch bản regional failover:

| Chỉ số | Target | Drill 1 | Drill 2 |
| --- | ---: | ---: | ---: |
| Detect | ≤ 5 phút | 6 phút | 2 phút |
| Decision/approval | ≤ 5 phút | 12 phút | 4 phút |
| Data restore/promotion | ≤ 20 phút | 24 phút | 15 phút |
| App + routing | ≤ 15 phút | 18 phút | 11 phút |
| Business verification | ≤ 10 phút | 11 phút | 7 phút |
| User-journey RTO | ≤ 60 phút | 71 phút | 39 phút |
| Data RPO | ≤ 5 phút | 8 phút | 3 phút |
| Minimum usable capacity | ≥ 50% | 35% | 65% |
| Critical data integrity | Không lỗi | 1 inconsistency | Không lỗi |

Dữ liệu chỉ minh họa. Khi các pha thực tế chạy song song, tổng RTO ở bảng **không nhất thiết** bằng tổng các dòng phụ; quan hệ này phải được giải thích trong timeline thật. Sau Drill 1, action items có thể là:
- Tự động hóa quyền truy cập DR và giảm approval bottleneck.
- Bật replication lag alert và kiểm tra backup log chain.
- Pre-provision capacity ở vùng dự phòng.
- Bổ sung reconciliation cho outbox/consumer offsets.
- Đo synthetic checkout qua global LB, không chỉ gọi Pod IP.

Drill 2 nên kiểm tra lại các lỗi cũ bằng scenario đủ tương đương, đồng thời ghi rõ thay đổi workload/dataset để tránh so sánh sai.

## 34. Dashboard cho trạng thái khôi phục

Các tín hiệu nên đặt cùng nhau:

| Tín hiệu | Ý nghĩa |
| --- | --- |
| Journey success rate | Người dùng có hoàn tất tác vụ quan trọng được không |
| User-journey p95/p99 | Trải nghiệm sau khi khôi phục có đủ tốt không |
| API 5xx/timeouts | Phần lỗi kỹ thuật trên đường request |
| Healthy/available replicas | Năng lực application |
| Database replication lag | Rủi ro RPO trước failover |
| Backup age / last successful restore verification | Mức độ tin cậy dữ liệu |
| DB recovery progress / WAL replay | Tiến độ phục hồi |
| Kafka consumer lag / oldest message age | Backlog nghiệp vụ sau outage |
| Outbox pending count | Event đã commit nhưng chưa chuyển tiếp |
| Pending payment reconciliation | Số giao dịch outcome chưa rõ |
| Region traffic distribution | Routing/cutover đã chuyển đúng chưa |
| CPU/memory/pool wait | Capacity và saturation trong vùng DR |
| Synthetic business check | Bằng chứng end-to-end |
| Active incident/runbook state | Đang ở bước nào, người quyết định |

Một dashboard xanh ở mức CPU/Pod nhưng synthetic checkout vẫn thất bại là **chưa phục hồi user journey**. Ngược lại, synthetic test pass một lần chưa chứng minh đủ capacity/ổn định; cần observation window và traffic hợp lý.

## 35. So sánh việc phục hồi với SLO hoạt động thường ngày

**RTO** là cam kết cho một tình huống khôi phục sau gián đoạn. **SLO** là mục tiêu chất lượng trong vận hành bình thường hoặc cửa sổ đã định. Hai mục tiêu liên quan nhưng không thay thế nhau.

Ví dụ:
- RTO 60 phút: checkout có thể hoạt động lại ở mức công suất tối thiểu.
- SLO checkout bình thường: success rate và latency trong 28 ngày.
- Sau RTO, có thể cần **recovery performance objective**: trong 2 giờ đạt 80% capacity, trong 6 giờ đạt 100%, nếu nghiệp vụ đòi hỏi.
- Sự cố có thể tiêu thụ một lượng lớn error budget; “DR đạt RTO” không có nghĩa tháng đó SLO vẫn đạt.

Khi làm báo cáo, phân biệt:
1. RTO/RPO đạt hay không.
2. User SLO trong giai đoạn và sau sự cố bị ảnh hưởng ra sao.
3. Công việc tồn đọng được drain tới mức nào.
4. Dữ liệu nghiệp vụ được đối soát và bảo vệ như thế nào.
5. Các giới hạn giả định của bài diễn tập.

## 36. Kiểm thử khả năng phục hồi khi không có con người chủ chốt

Một rủi ro khác là kiến thức và quyền nằm ở một người. Có thể thiết kế diễn tập:

- Một kỹ sư không tham gia viết runbook phải chạy isolated restore.
- Primary on-call giả định vắng mặt; secondary thực hiện escalation.
- Một bước tạo tài nguyên ở region DR không được phép dùng quyền admin cá nhân.
- Người điều phối phải tìm dashboard/runbook qua service catalog, không hỏi tác giả.
- Tài liệu chỉ chứa link source of truth, không chứa secret hard-code.
- Có lịch bàn giao rõ khi diễn tập vượt một ca trực.

Đo thời gian tìm owner, thời gian xin quyền, số bước thủ công và thời gian đọc tài liệu. Nếu kỹ thuật restore chỉ mất 10 phút nhưng cần 40 phút để tìm người có quyền truy cập, đó là một phần quan trọng của RTO quan sát được.

## 37. Runbook khôi phục tốt cần gì?

Một runbook nên có:

1. **Trigger:** điều kiện kích hoạt, nguồn alert, business impact.
2. **Scope:** service/region/dataset/tenant nào được xử lý.
3. **Owner & permissions:** người thực hiện, người quyết định, escalation.
4. **Preconditions:** backup, fencing, quota, IAM/KMS, traffic state.
5. **Read-only checks:** trạng thái hệ thống và điểm phục hồi dữ liệu.
6. **Decision tree:** failover, PITR, restore backup hay degraded operation.
7. **Actions:** các bước có target chính xác, không dùng wildcard phá hủy.
8. **Expected result:** tín hiệu thành công sau mỗi bước.
9. **Abort & rollback:** khi nào dừng và quay lại.
10. **Data reconciliation:** event, payment, orders, inventory, offsets.
11. **Business validation:** synthetic journeys và capacity.
12. **Evidence & timeline:** dữ liệu phải ghi cho báo cáo.
13. **Communication:** cập nhật nội bộ/khách hàng và thời điểm tiếp theo.
14. **Failback:** quay về vùng chính sau khi tình trạng ổn định.
15. **Post-exercise:** cleanup, action items và lịch review.

Runbook cần được lưu có version và kiểm tra khi thay đổi topology, cloud account, schema, KMS, IAM, provider integration hoặc incident policy. Một checklist mở được nhưng mọi link đều cũ không phải runbook có khả năng thực thi.

## 38. Failback và tránh thảm họa thứ hai

Sau failover thành công sang region B, region A có thể phục hồi. Việc quay về không nên chỉ đảo DNS:

- Xác minh region A không còn writer cũ không được fence.
- Xây dựng luồng đồng bộ dữ liệu B → A, kiểm tra log/replication position.
- Đối soát các transaction phát sinh trong thời gian region B active.
- Kiểm tra event/outbox/offset, idempotency và external callbacks.
- Xác định cách tránh duplicate side effects trong giai đoạn chuyển hướng traffic.
- Thực hiện canary read trước khi cho phép write.
- Xác minh capacity, secret/permission, network và certificate.
- Quyết định thời gian quay về theo business risk, không vì mong muốn trở lại trạng thái quen thuộc.
- Có rollback nếu failback tạo lỗi.
- Ghi failback RTO riêng khi doanh nghiệp có mục tiêu.

**Có thể tiếp tục vận hành ở vùng DR trong thời gian dài** nếu nó an toàn và ổn định hơn việc failback ngay. DR drill nên tập làm failback trên môi trường tạm nếu quy trình này có nhiều rủi ro.

## 39. Mẫu kịch bản game day: mất region theo phạm vi cô lập

~~~text
Preconditions
  - Dữ liệu synthetic và tài nguyên hoàn toàn tách production
  - DB/broker ở vùng chính và dự phòng có monitoring
  - Test writer đánh marker đều, record commit timestamps
  - Test runner gọi synthetic checkout liên tục
  - KMS/secrets, IAM và network DR đã được chuẩn bị
  - Recovery owner và safety observer đã xác nhận

Fault
  - Cô lập kết nối đến mô phỏng region chính
  - Không xóa tài nguyên hoặc backup thật

Observe
  - Đo T0 detection/impact
  - Primary on-call nhận page và phân loại
  - Incident commander chọn activate DR
  - Confirm writer fencing và replication position
  - Promote/restore data và launch workloads DR
  - Chuyển test traffic qua DR ingress
  - Synthetic checkout thành công, dữ liệu bền vững
  - Đối soát marker/order/payment/event, đo RPO
  - Load test tối thiểu trong observation window
  - Hoàn tất checklist và thu evidence

Abort
  - Hạ tầng ngoài phạm vi bị tác động
  - Phát hiện split-brain hoặc duplicate business effects
  - Không xác minh được dữ liệu/identity an toàn
  - Quá timebox hoặc mất khả năng rollback

Finish
  - Dừng fault injection, không mở writer cũ tùy tiện
  - Kiểm tra failback plan
  - Xóa test resources, hoàn tất báo cáo
```

Đây là khung thao tác mô phỏng, không phải chỉ dẫn tắt một region production. Trên production, mọi failure injection/failover cần được phê duyệt riêng và có policy an toàn phù hợp.

## 40. Các yếu tố khiến RTO/RPO thực tế khác phòng lab

- Dataset test chỉ bằng 1% production; thời gian restore không đại diện.
- Backup được restore từ storage cùng region, trong khi thảm họa yêu cầu cross-region transfer.
- Thử lúc traffic thấp, không có hàng chờ và cache đã warm.
- Người viết runbook tự thao tác nên không tính thời gian học quy trình.
- Mock provider/SSO/DNS thay cho dependency thật, bỏ qua IAM và network.
- Không đo time to detect hoặc decision, chỉ đo lệnh restore.
- Sử dụng admin credentials được cấp sẵn, trong thực tế sẽ cần emergency access.
- Hệ vùng DR có quota cao hơn hoặc thấp hơn cấu hình production.
- Test chỉ kiểm tra 200 OK nhưng không đối soát data consistency.
- Source database có write burst nên replication lag lớn hơn bài thử.
- Diễn tập được báo trước, các nhóm và provider đều đã chuẩn bị đặc biệt.
- Không thử trường hợp backup bị corruption hoặc KMS key không sẵn.
- Chỉ đo một lần, bỏ qua phân bố và tính lặp lại.
- Không kiểm tra long-lived connections, DNS caching hoặc consumers.
- Recovery ở trạng thái degraded nhưng báo cáo như đã khôi phục full capacity.

Báo cáo nên có phần **“giới hạn khả năng suy rộng”** để chỉ ra kết quả áp dụng cho điều kiện nào. Một bài isolated restore đạt 20 phút không có nghĩa region failover chắc chắn 20 phút.

## 41. Tối ưu thứ tự công việc dựa trên critical path

Sau mỗi lần diễn tập, phân tích mốc và sơ đồ phụ thuộc để chọn nơi giảm RTO hiệu quả nhất.

Ví dụ:
- KMS/secret readiness: 8 phút.
- DB restore: 25 phút.
- Broker restore: 18 phút (có thể song song DB nếu đủ prerequisites).
- App startup: 10 phút sau DB/secret.
- DNS/traffic cutover: 5 phút.
- Business validation: 7 phút.

Nếu DB và broker restore song song, critical path chủ yếu đi qua DB 25 phút; tối ưu broker từ 18 xuống 10 phút có thể **không giảm RTO** nếu nó vẫn kết thúc trước DB. Tối ưu thời gian xác nhận quyền, DB restore hoặc app readiness có thể có lợi hơn.

Cần đo **wait time**: thời gian chờ người phê duyệt, chờ IP whitelist provider, chờ quota nâng, chờ IAM propagation. Những thành phần này thường chiếm RTO hơn bản thân lệnh kỹ thuật.

Đề xuất cải tiến nên ước lượng:
- Thời gian tiết kiệm trên đường găng.
- Chi phí hạ tầng và hoạt động.
- Rủi ro consistency/security mới.
- Độ tin cậy của automation.
- Điều kiện phải thử lại sau thay đổi.

## 42. Cải thiện RPO: không chỉ tăng tần suất backup

Nếu mục tiêu RPO nhỏ hơn backup interval hiện tại, cần xem xét:

- Database WAL/binlog archiving/PITR liên tục.
- Synchronous hoặc asynchronous replication phù hợp consistency/latency trade-off.
- Cross-region replication lag alert và fencing.
- Transactional outbox để tránh mất event giữa DB commit và broker publish.
- External immutable journal hoặc append-only ledger cho giao dịch quan trọng.
- CDC streams với checkpoint/log retention đủ.
- Idempotency/reconciliation để tái dựng side effects.
- Backup verification và immutability chống corruption/ransomware.
- Chia các domain dữ liệu thành nhiều tier RPO khác nhau.
- Đảm bảo encryption keys và metadata có thể phục hồi cùng dữ liệu.

Synchronous replication có thể giảm mất dữ liệu nhưng tăng latency write và chịu rủi ro availability khi liên kết xa lỗi. Không mặc định mọi dữ liệu cần RPO 0 và không giải thích chi phí. Với các giao dịch không thể mất, cần xác định **nguồn sự thật về commit** ở nhiều failure domains và test network partition/split-brain thực tế.

## 43. Cải thiện RTO: giảm những điểm phục hồi chậm

Những biện pháp:

- Duy trì warm standby hoặc pilot light cho thành phần phục hồi chậm.
- Pre-provision network, IAM, KMS, DNS và service accounts.
- Sao lưu artifact/container image vào registry độc lập hoặc mirror.
- Chuyển infrastructure và config sang IaC/GitOps.
- Tự động hóa bước restore theo runbook có guardrail và approval.
- Giảm kích thước backup/restore thời gian bằng incremental snapshots và log replay hiệu quả.
- Kiểm thử khả năng restore song song nhiều data stores.
- Chuẩn hóa health/readiness, graceful boot và cache warm-up.
- Tạo synthetic transaction có thể chạy chỉ bằng một thao tác.
- Giảm dependency không thiết yếu khỏi critical path của hành trình.
- Đặt recovery quotas/capacity đủ cho region dự phòng.
- Diễn tập on-call secondary để giảm thời gian tìm người.
- Chuẩn hóa failover/failback decision tree.

**Cẩn trọng:** Tăng tự động hóa không có guardrail có thể kích hoạt failover sai khi alert nhiễu. Những bước như promote DB, mở writer và route traffic phải có điều kiện fencing/identity rõ ràng.

## 44. Kiểm tra checksum và tính toàn vẹn

Một số kiểm tra kỹ thuật có thể tự động hóa:

| Kiểm tra | Mục đích |
| --- | --- |
| Backup file/object checksum | Phát hiện bit rot, file hỏng, thiếu segment |
| Restore application startup/migrations | Đảm bảo schema và extension sử dụng được |
| DB constraints / referential integrity | Phát hiện quan hệ dữ liệu sai |
| Row counts theo bảng/tier | Phát hiện thiếu dữ liệu lớn, không thay kiểm tra logic |
| Marker sequence continuity | Đo điểm phục hồi và khoảng thiếu |
| Event/outbox sequence | Kiểm tra continuity của pipeline |
| Ledger balance invariants | Đảm bảo giao dịch tài chính cân đối |
| Duplicate transaction detection | Phát hiện replay không idempotent |
| Encryption/decryption test | Xác nhận khả năng dùng KMS/key |
| Business synthetic transaction | Chứng minh end-to-end user journey |
| Access control test | Đảm bảo DR không bỏ qua authentication/authorization |

**Không lấy row count bằng nhau làm bằng chứng dữ liệu giống nhau.** Có thể một record bị sửa, một record mới thay thế hoặc dữ liệu thuộc khác tenant. Với dataset lớn, checksum theo partition và domain invariants có thể hiệu quả hơn full row-by-row compare; phải cân nhắc dữ liệu nhạy cảm và cost.

## 45. Ghi action items sau diễn tập

Mỗi gap cần một đầu ra có thể kiểm chứng:

| Gap | Action rõ | Owner | Verification |
| --- | --- | --- | --- |
| KMS permission thiếu | Bổ sung DR role với quyền tối thiểu | Security/Platform | Restore encrypted snapshot bằng DR role |
| RTO trượt do manual DNS | Tự động hóa cutover có approval/rollback | Platform | Rehearsal đo thời gian DNS propagation |
| RPO trượt khi backup lag | Bật WAL shipping và lag alert | Data Team | Marker drill chứng minh RPO target |
| Consumer replay gây duplicate | Thêm idempotency bằng event ID | Messaging/Product | Redelivery integration test |
| Không tìm thấy runbook | Link từ SLO alert/service catalog | SRE | Tabletop với người chưa biết hệ thống |
| DR capacity quá thấp | Tăng reserved quota và warm capacity | Platform/Finance | Load test ở recovery environment |
| Provider callback sai region | Cập nhật allowlist/callback strategy | Payment | Synthetic provider callback test |
| Không đo T0 | Thêm independent synthetic failure sensor | Observability | Report có T0/T1 tự động |

Action như “cần cẩn thận hơn” không đủ. Mỗi item nên có priority, owner, deadline, acceptance criteria và một diễn tập/test chứng minh sau khi sửa.

## 46. Tần suất và phạm vi diễn tập theo thay đổi

Không nên diễn tập mọi thứ cùng một cường độ. Có thể xác định lịch dựa trên:

- Data tier/criticality và mục tiêu RTO/RPO.
- Thay đổi lớn về DB engine, schema, storage hoặc KMS.
- Mở region mới, thay DNS/global load balancer.
- Thêm broker, CDC, outbox hoặc thay event semantics.
- Thay đổi IAM/network policy/secret manager.
- Incident gần đây cho thấy recovery gap.
- Phát hiện restore success giảm hoặc backup age vượt ngưỡng.
- Số lượng người trực mới, thay đổi ownership.
- Yêu cầu audit/compliance và giới hạn môi trường.

Ví dụ tổ chức có thể làm tabletop hàng quý, restore verification tự động hàng tuần và regional rehearsal định kỳ; đây chỉ là lựa chọn khởi đầu, không phải chu kỳ bắt buộc. Quan trọng hơn là có **lịch, scope, owner và bằng chứng** cho từng bài, không phải chỉ lịch trên giấy.

## 47. Checklist chuẩn bị diễn tập

- [ ] Có BIA, journey priorities, RTO/RPO và acceptance criteria được phê duyệt.
- [ ] Đã chọn failure scenario, exercise level và môi trường phù hợp.
- [ ] Có role: drill lead, safety, database, platform, messaging, service owner, business verifier.
- [ ] Có phân định quyền production, break-glass, escalation và stop conditions.
- [ ] Test resources/data được cách ly; không nhầm môi trường hoặc account.
- [ ] Backup/snapshot/log chain, KMS key và IAM có thể truy cập từ recovery environment.
- [ ] Artifact, manifests và schema version có thể pin/tái triển khai.
- [ ] Dependency graph, recovery sequence và writer fencing đã được xác định.
- [ ] Có marker writer/commit log và synthetic journeys để đo RTO/RPO.
- [ ] Có dashboard/tracing, đồng bộ thời gian và nơi lưu evidence an toàn.
- [ ] Có phương án cancel/rollback/teardown và kiểm tra blast radius.
- [ ] Kịch bản có thời gian và mức resource cap phù hợp.
- [ ] Đã xác định khả năng routing/capacity tối thiểu khi phục hồi.
- [ ] Có quy trình đối soát Order/Payment/Inventory/outbox/broker.
- [ ] Các stakeholder biết scope và cơ chế thông tin khi xảy ra tác động không mong muốn.

## 48. Checklist thực hiện và đo kết quả

- [ ] Ghi T0 theo nguồn bằng chứng được xác định trước.
- [ ] Ghi T1 detection, T2 declaration và T3 action start.
- [ ] Ghi mốc provisioning, restore, DB validation, service readiness.
- [ ] Ghi mốc đầu tiên synthetic journey thành công bền vững.
- [ ] Ghi thời điểm đạt capacity/latency/error acceptance trong observation window.
- [ ] Tính observed RTO đúng start/end definition; không loại bỏ thời gian quyết định.
- [ ] Đo RPO bằng commit markers/sequence, không chỉ replication dashboard.
- [ ] Đối chiếu missing/extra records, checksums và domain invariants.
- [ ] Kiểm tra outbox, broker, offsets, retries, DLQ và idempotency.
- [ ] Xác minh identity, authorization, secrets, KMS và TLS ở vùng DR.
- [ ] Xác nhận không có split-brain hoặc writer cũ nhận ghi sau cutover.
- [ ] Chỉ công bố pass khi tất cả acceptance criteria có bằng chứng.
- [ ] Ghi cả thất bại, giới hạn phạm vi và yếu tố không đo được.
- [ ] Teardown tài nguyên và kết thúc fault injection an toàn.
- [ ] Lưu report, action owner/deadline và kế hoạch diễn tập lại.

## 49. Các sai lầm phổ biến

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ có backup job xanh | Không biết có restore được không | Restore verification định kỳ |
| Chỉ đo từ lúc bấm restore | Che thời gian detect/escalate | Định nghĩa T0 → business recovery |
| RPO dựa trên replica lag đơn thuần | Không phát hiện gap/commit mất | Durable markers và reconciliation |
| Kiểm tra DB row count rồi gọi là thành công | Bỏ qua dữ liệu sai và cross-service consistency | Domain invariants + synthetic transactions |
| Tắt một Pod rồi gọi là DR region | Không chứng minh thảm họa toàn vùng | Scope/level và target rõ |
| Restore dữ liệu vào DB production | Tự gây mất dữ liệu | Isolated recovery environment |
| Không fence writer cũ | Split-brain và ghi trùng | Quorum/fencing/cutover policy |
| Reset Kafka offset về latest | Mất xử lý nghiệp vụ | Reconcile/checkpoint/replay an toàn |
| Retry payment bằng key mới | Double charge | Idempotency và provider reconciliation |
| Chỉ probe /health | Không biết checkout thật có hoạt động | End-to-end synthetic journey |
| Test bằng dataset quá nhỏ | RTO đo không đại diện | Dữ liệu và tải sát cấu hình thực, nêu giới hạn |
| Bỏ qua KMS/IAM | Có backup nhưng không giải mã được | Test restore với DR principal |
| Không có abort condition | Diễn tập lan thành incident thật | Safety lead, kill switch, blast radius |
| Không đo capacity sau failover | Service xanh nhưng không chịu được tải | Recovery load test và ngưỡng tối thiểu |
| Chỉ có một người biết runbook | Chậm khi người đó vắng | Secondary on-call và tabletop |
| Không tập failback | Lỗi lần thứ hai khi trở lại | Failback rehearsal có fencing/rollback |
| Báo pass dù một metric not measured | Tạo cảm giác an toàn sai | Pass/Fail/Not verified theo từng tiêu chí |
| Không gán owner cho gaps | Bài diễn tập không tạo cải tiến | Action items có deadline và verification |

## 50. Câu hỏi thường gặp

**RTO có bắt đầu từ lúc người trực nhấn nút kích hoạt DR không?**

Tùy chính sách định nghĩa, nhưng đối với tác động người dùng, nên tính từ mốc gián đoạn có thể xác định đến khi dịch vụ nghiệp vụ đã phục hồi ở mức cam kết. Có thể đo thêm thời gian kỹ thuật từ lúc activate, nhưng phải gắn nhãn riêng và không thay thế user impact duration.

**RPO 5 phút có nghĩa được phép mất mọi transaction trong 5 phút đó?**

Không. RPO là một mục tiêu kỹ thuật về điểm dữ liệu có thể khôi phục; dữ liệu tài chính, giao dịch đã xác nhận hoặc yêu cầu pháp lý có thể phải phục hồi đầy đủ bằng journal/reconciliation. Cần quy tắc riêng về business correctness, không chỉ số phút.

**Chỉ restore backup vào một DB test có được coi diễn tập DR thành công?**

Đó là bằng chứng quan trọng ở cấp isolated restore. Nó không chứng minh network, routing, identity, broker, cross-service consistency và business journey khi mất region. Hãy báo cấp bài diễn tập chính xác.

**RPO nên đo theo thời điểm snapshot hay theo giao dịch commit?**

Đối với correctness, nên căn cứ dữ liệu đã được xác nhận bền vững, recovery log position và marker sequence. Timestamp của snapshot hoặc lag dashboard chỉ là tín hiệu hỗ trợ; có thể bỏ qua gaps hoặc schema corruption.

**Nếu Pod và database lên khỏe rồi, có cần synthetic business test không?**

Có. Khả năng nhận HTTP health không chứng minh việc tạo đơn/thanhtoán/đọc dữ liệu đạt đúng ngữ nghĩa nghiệp vụ. Synthetic journey nên dùng dữ liệu an toàn, idempotency và xác minh durable state.

**Diễn tập trên production có bắt buộc không?**

Không cho mọi trường hợp. Thử production có giá trị cho routing và các dependency không mô phỏng được nhưng có rủi ro lớn; phải được phê duyệt, có stop conditions và quan sát tác động. Bắt đầu bằng tabletop, isolated restore và rehearsal môi trường riêng trước.

**Đã có multi-region replication thì còn cần backup không?**

Có. Replication có thể sao chép cả xóa nhầm, corruption hoặc ransomware; backup có retention/immutability và PITR phù hợp vẫn cần để khôi phục trạng thái trước lỗi. Kiểm tra cả key và quyền truy cập.

**Vì sao đạt RTO/RPO mà vẫn không nên tuyên bố DR hoàn toàn pass?**

Có thể thiếu security, thiếu capacity, còn duplicate payment, backlog nghiêm trọng hoặc data inconsistency. Diễn tập nên dùng bộ acceptance criteria gồm RTO, RPO, business correctness, minimum capacity và operational readiness.

**Nên khôi phục database trước hay service trước?**

Phụ thuộc dependency graph. Có thể dựng IAM/network/app infrastructure song song với restore, nhưng đừng bật writer/consumer trước khi dữ liệu, fencing và schema đủ an toàn. Phân tích critical path để sắp thứ tự.

**Có cần diễn tập failback về region chính không?**

Nên có nếu kế hoạch thực tế yêu cầu quay lại. Failback có thể tạo split-brain hoặc mất dữ liệu nếu không đồng bộ dữ liệu đã ghi ở vùng DR; cần runbook và rehearsal riêng.

**Một lần diễn tập đạt 48 phút có đảm bảo lần sau đạt RTO 60 phút không?**

Không. Dữ liệu, traffic, quyền, thời điểm, nhà cung cấp và failure mode có thể khác. Cần nhiều lần đo, ghi điều kiện và giới hạn, test biến thể/peak, đồng thời theo dõi các action items cải thiện.

---

**Nguyên lý ghi nhớ:** *Khả năng khôi phục thảm họa không được chứng minh bằng sơ đồ, backup job xanh hay Pod Ready. Nó được chứng minh bằng diễn tập an toàn có mục tiêu định nghĩa trước, timeline RTO đo từ tác động thật, RPO kiểm bằng dữ liệu commit và đối soát, synthetic business journeys, khả năng chịu tải, bảo mật, quyền thao tác và báo cáo sai lệch có người chịu trách nhiệm sửa.*