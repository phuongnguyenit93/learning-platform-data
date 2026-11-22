# Retain, retire, relocate, rehost, replatform, repurchase và refactor

## 1. Bảy chiến lược trong bài toán kiến trúc đám mây

Khi chuyển một hệ thống lên đám mây, câu hỏi đầu tiên không phải là “dùng máy ảo, container hay serverless?”, mà là **hệ thống này còn tạo ra giá trị gì, cần thay đổi đến đâu và tổ chức có thể chấp nhận rủi ro nào?** Mô hình **7R** là khung phân loại quyết định cho từng ứng dụng hoặc workload:

1. **Retain** — giữ lại ở môi trường hiện tại.
2. **Retire** — ngừng vận hành vì không còn cần thiết.
3. **Relocate** — chuyển nguyên môi trường ảo hóa sang hạ tầng tương đương trên đám mây.
4. **Rehost** — chuyển ứng dụng sang hạ tầng đám mây với thay đổi tối thiểu.
5. **Replatform** — điều chỉnh nền tảng chạy ứng dụng để tận dụng dịch vụ đám mây mà không thiết kế lại toàn bộ.
6. **Repurchase** — thay phần mềm hiện có bằng một sản phẩm/dịch vụ khác, thường là SaaS.
7. **Refactor (re-architect)** — thay đổi đáng kể mã nguồn hoặc kiến trúc để đáp ứng mục tiêu mới.

Đây là **bảy lựa chọn khác nhau**, không phải bảy bước bắt buộc phải đi qua theo thứ tự. Một danh mục ứng dụng có thể đồng thời dùng cả bảy cách; một hệ thống lớn cũng có thể áp dụng nhiều chiến lược cho các thành phần khác nhau.

Trong học phần **Cloud Architecture**, 7R kết nối yêu cầu nghiệp vụ với thiết kế **mạng, compute, dữ liệu và triển khai**, đồng thời buộc kiến trúc sư cân bằng năm mối quan tâm xuyên suốt: **độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành**. “Chuyển được lên cloud” chỉ là một kết quả kỹ thuật; quyết định tốt còn phải có lý do kinh doanh và tiêu chí nghiệm thu rõ ràng.

### Phân biệt migration và modernization

- **Migration (di chuyển)**: đổi nơi chạy, nơi lưu dữ liệu hoặc nền tảng triển khai của workload. Mục tiêu có thể là thoát trung tâm dữ liệu, tăng khả năng khôi phục, hoặc hoàn thành trước hạn chấm dứt hợp đồng.
- **Modernization (hiện đại hóa)**: thay đổi công nghệ, kiến trúc hoặc cách vận hành nhằm cải thiện năng lực dài hạn như phát hành nhanh, tự động mở rộng, kiểm soát lỗi hay giảm gánh nặng bảo trì.
- Một **rehost** có thể hoàn thành migration nhưng giữ nguyên nợ kỹ thuật. Một **refactor** thường là modernization sâu và có thể được triển khai từng phần sau khi đã di chuyển.

## 2. So sánh ý nghĩa và đánh đổi của từng R

| Chiến lược | Thực hiện | Tình huống thường phù hợp | Lợi ích chính | Rủi ro/giới hạn phải kiểm tra |
|---|---|---|---|---|
| **Retain** | Duy trì ứng dụng ở vị trí hiện tại, có kế hoạch đánh giá lại | Phụ thuộc thiết bị tại chỗ, ràng buộc pháp lý, chưa có phương án di chuyển an toàn | Tránh thay đổi vội vàng; bảo vệ hệ thống đặc thù | Vẫn chịu chi phí vận hành tại chỗ, rủi ro vòng đời thiết bị/phần mềm |
| **Retire** | Xác minh không còn người dùng/phụ thuộc rồi tắt, lưu trữ hoặc xóa đúng chính sách | Công cụ trùng chức năng, ứng dụng không còn phục vụ quy trình | Loại bỏ chi phí và bề mặt tấn công | Tắt nhầm tích hợp, mất dữ liệu cần lưu giữ hoặc khả năng kiểm toán |
| **Relocate** | Di chuyển máy ảo và cấu hình trong một hệ sinh thái ảo hóa tương thích | Có nhiều VM trên nền tảng ảo hóa và cần chuyển nhanh cả cụm | Ít sửa ứng dụng; giữ cách quản trị quen thuộc | Phụ thuộc bản quyền/hypervisor, giới hạn khả năng tận dụng dịch vụ cloud-native |
| **Rehost** | Đưa workload sang VM/IaaS đám mây, ít sửa phần mềm | Cần thoát data center sớm; ứng dụng ổn định nhưng chưa có ngân sách sửa | Thực hiện tương đối nhanh, dễ khoanh phạm vi | Vẫn phải vá OS/middleware, có thể tốn kém nếu giữ nguyên cấu hình quá lớn |
| **Replatform** | Đổi một phần nền tảng: managed database, container, managed runtime... | Ứng dụng còn phù hợp nhưng hạ tầng hiện tại khó vận hành | Giảm công quản trị và nâng khả năng mở rộng trong phạm vi nhất định | Khác biệt phiên bản/driver, hành vi kết nối, giới hạn dịch vụ quản lý |
| **Repurchase** | Chuyển sang sản phẩm khác, thường là SaaS, đồng thời đổi quy trình và dữ liệu | Nhu cầu chủ yếu là chức năng tiêu chuẩn như CRM, helpdesk | Giảm trách nhiệm xây dựng/phần mềm tự quản lý | Phí thuê bao, tích hợp, dữ liệu xuất nhập, khả năng tùy biến và lệ thuộc nhà cung cấp |
| **Refactor** | Thiết kế lại thành phần, luồng dữ liệu, giao tiếp, triển khai hoặc mô hình miền | Hệ thống cốt lõi cần phát hành nhanh, mở rộng linh hoạt, phục hồi tốt hơn | Mở ra năng lực mới phù hợp mục tiêu dài hạn | Tốn công, khó kiểm chứng, rủi ro thay đổi hành vi nghiệp vụ |

**Mức độ thay đổi không đồng nghĩa với mức độ tốt hơn.** Một hệ thống sắp ngừng sử dụng có thể nên retire thay vì refactor. Một ứng dụng ổn định, ít thay đổi có thể rehost hợp lý hơn việc tách thành microservices. Ngược lại, bê nguyên thiết kế thiếu khả năng phục hồi sang cloud sẽ không tự tạo ra high availability.

### Những ranh giới dễ nhầm lẫn

**Relocate và rehost:** Relocate bảo toàn phần lớn mô hình ảo hóa hiện hữu bằng cách chuyển workload giữa các môi trường tương thích, chẳng hạn một cụm máy ảo trên nền tảng ảo hóa được hỗ trợ ở đám mây. Rehost chuyển hệ điều hành/ứng dụng sang tài nguyên compute mới như cloud VM; có thể phải chuyển định dạng máy, mạng, ổ đĩa và công cụ quản trị. Cả hai ít thay đổi logic nghiệp vụ, nhưng **điểm chuyển giao trách nhiệm nền tảng** khác nhau.

**Rehost và replatform:** Đổi địa chỉ VM nhưng giữ nguyên dịch vụ cơ sở dữ liệu tự quản lý thường là rehost. Chuyển database sang dịch vụ quản lý, sau khi kiểm tra tương thích và sửa cấu hình/kết nối, là một ví dụ replatform. Chạy ứng dụng trong container cũng **không tự động** là replatform hay refactor; phải xem phạm vi thay đổi thực tế.

**Replatform và refactor:** Replatform chủ yếu thay phần hạ tầng/runtime mà vẫn giữ cấu trúc nghiệp vụ chính. Refactor thay đáng kể mã nguồn, ranh giới dịch vụ hoặc mô hình giao tiếp/dữ liệu, chẳng hạn tách xử lý đơn hàng thành các dịch vụ có hợp đồng API và sự kiện.

**Repurchase và replatform:** Đưa CRM tự phát triển lên một managed runtime là replatform; thay nó bằng CRM SaaS là repurchase vì tổ chức đổi sản phẩm và cần chuyển dữ liệu, người dùng, quy trình.

**Retain và retire:** Retain nghĩa là tiếp tục chịu trách nhiệm vận hành và xem xét lại vào mốc xác định. Retire nghĩa là kết thúc vòng đời ứng dụng sau khi đã xử lý dữ liệu, tích hợp, quyền truy cập và chứng cứ kiểm toán.

## 3. Thu thập dữ kiện trước khi chọn R

Quyết định 7R được đưa ra ở cấp **workload/ứng dụng**, dựa trên dữ kiện. Không nên áp dụng một nhãn chung cho cả công ty hoặc lựa chọn chỉ theo ngôn ngữ lập trình.

| Nhóm thông tin | Câu hỏi cần trả lời | Tác động đến quyết định |
|---|---|---|
| Giá trị nghiệp vụ | Ai dùng, tần suất nào, có thể bỏ hoặc thay sản phẩm không? | Ưu tiên retire/repurchase hay đầu tư dài hạn |
| Mức độ quan trọng | Hệ thống ngừng 1 giờ ảnh hưởng ra sao? SLA/SLO, RTO, RPO là bao nhiêu? | Thiết kế HA/DR, phương án cutover và rollback |
| Kiến trúc hiện tại | OS, runtime, database, batch, hàng đợi, VM/hypervisor, phiên bản hỗ trợ? | Khả thi của relocate/rehost/replatform |
| Phụ thuộc | API, DNS, chứng thực, tệp chia sẻ, thiết bị, lịch tác vụ, hệ thống thanh toán? | Thứ tự các migration wave; cần hybrid connectivity |
| Dữ liệu | Khối lượng, tốc độ thay đổi, độ nhạy cảm, nơi được phép lưu trữ, thời hạn giữ? | Cách đồng bộ, vị trí đặt dữ liệu, kiểm soát truy cập |
| Bảo mật & tuân thủ | IAM, mã hóa, quản lý khóa, nhật ký, yêu cầu kiểm toán, lưu trú dữ liệu? | Landing zone và ràng buộc kiến trúc |
| Chi phí | Giá license, thiết bị, mạng, lưu trữ, vận hành, dual-run và lưu lượng ra? | TCO và khả năng chi trả theo từng giai đoạn |
| Đội ngũ & thời hạn | Năng lực cloud, thời gian chuyển, mức chấp nhận thay đổi? | Chọn đường đi đủ an toàn trong thời gian cho phép |

Một bản kiểm kê tối thiểu nên ghi: **chủ sở hữu ứng dụng, người chịu trách nhiệm kỹ thuật, môi trường, mức quan trọng, phụ thuộc hai chiều, nguồn dữ liệu, ràng buộc, R đề xuất, bằng chứng và ngày đánh giá lại**. Nếu chưa biết ai sử dụng hệ thống, quyết định retire vẫn chỉ là giả thuyết.

### Sơ đồ định hướng ban đầu

~~~mermaid
flowchart TD
    A["Khảo sát workload và yêu cầu nghiệp vụ"] --> B{"Còn cần hệ thống?"}
    B -- "Không" --> R1["Retire: xác minh phụ thuộc và lưu trữ dữ liệu"]
    B -- "Có" --> C{"Đã đủ điều kiện di chuyển?"}
    C -- "Chưa" --> R2["Retain: ghi rõ trở ngại và ngày xem xét lại"]
    C -- "Rồi" --> D{"Chức năng có thể thay bằng sản phẩm phù hợp?"}
    D -- "Có và hiệu quả" --> R3["Repurchase: đánh giá SaaS và chuyển dữ liệu"]
    D -- "Không" --> E{"Cần thay đổi kiến trúc sâu để đạt mục tiêu?"}
    E -- "Có" --> R4["Refactor: chia giai đoạn và kiểm soát rủi ro"]
    E -- "Không" --> F{"Có nền tảng ảo hóa tương thích để chuyển nguyên môi trường?"}
    F -- "Có, phù hợp TCO" --> R5["Relocate"]
    F -- "Không / không phù hợp" --> G{"Thay nền tảng một phần có lợi và tương thích?"}
    G -- "Có" --> R6["Replatform"]
    G -- "Không" --> R7["Rehost"]
~~~

Sơ đồ chỉ để **khởi tạo phương án**, không thay thế phân tích chi phí, an toàn và kiến trúc. Các nhánh “có” đều cần bằng chứng; đôi khi workload vừa phù hợp SaaS vừa cần tùy biến sâu, hoặc một phần được retain trong khi phần khác replatform.

## 4. Áp dụng 7R vào một danh mục ứng dụng

Giả sử doanh nghiệp bán lẻ muốn rời trung tâm dữ liệu trong 12 tháng, giảm công vận hành và giữ ổn định hệ thống bán hàng. Bảng dưới là **ví dụ giả định**, dùng để minh họa cách mỗi workload có thể nhận một quyết định riêng:

| Workload | Chiến lược dự kiến | Lý do và điều kiện kèm theo |
|---|---|---|
| Ứng dụng báo cáo không còn người dùng, thay bởi BI mới | **Retire** | Kiểm tra người dùng cuối, lịch tác vụ và thời hạn lưu báo cáo rồi tắt |
| Phần mềm quản lý thiết bị trong nhà máy, dùng driver chuyên dụng | **Retain** | Cần giữ kết nối thiết bị tại chỗ; đặt mốc đánh giá sau khi có gateway tương thích |
| Cụm VM nội bộ trên nền tảng ảo hóa được hỗ trợ tại cloud | **Relocate** | Ưu tiên di chuyển nhanh cả cụm; kiểm tra license, đường truyền, độ trễ |
| Ứng dụng ERP cũ chạy trên VM, bản quyền và runtime chưa sẵn sàng đổi | **Rehost** | Chuyển VM trước; lập kế hoạch vá phiên bản, kiểm tra chi phí compute |
| API quản lý kho có thể chuyển database sang dịch vụ quản lý | **Replatform** | Kiểm tra schema, extension, connection pool và failover |
| Công cụ CRM tự xây nhưng chức năng chủ yếu theo quy trình tiêu chuẩn | **Repurchase** | Đánh giá SaaS, nhập dữ liệu, SSO, quyền truy cập và phí thuê bao |
| Nền tảng đặt hàng có tải cao, phát hành liên tục, phụ thuộc nhiều module | **Refactor** | Tách dần các năng lực cần mở rộng riêng, bảo đảm nhất quán đơn hàng |

Sau khi chọn R, tổ chức phải tạo **bản ghi quyết định kiến trúc (ADR)** ghi rõ: bối cảnh, các phương án đã cân nhắc, quyết định, lý do, giả định, rủi ro còn lại và mốc kiểm tra. “Rehost vì nhanh” chưa đủ nếu không ghi rằng ứng dụng vẫn sử dụng database tự quản lý và cần chiến dịch hiện đại hóa tiếp theo.

## 5. Đánh giá đánh đổi bằng Well-Architected

Well-Architected giúp kiểm tra một phương án migration ở nhiều chiều, không chỉ về tốc độ. Sáu trụ cột phổ biến được áp dụng như sau:

| Trụ cột | Câu hỏi đánh giá kiến trúc sau di chuyển |
|---|---|
| **Operational Excellence — Vận hành xuất sắc** | Triển khai có tự động hóa? Có runbook, cảnh báo, trực vận hành và quản lý thay đổi? |
| **Security — Bảo mật** | IAM theo quyền tối thiểu? Secret, mã hóa, khóa, phân đoạn mạng, nhật ký kiểm toán được bảo vệ? |
| **Reliability — Độ tin cậy** | Thành phần lỗi có được thay thế/phục hồi? Đã kiểm tra backup/restore, failover, RTO/RPO? |
| **Performance Efficiency — Hiệu quả hiệu năng** | Độ trễ qua mạng hybrid, cấu hình compute, IOPS, cache, giới hạn kết nối có đáp ứng tải? |
| **Cost Optimization — Tối ưu chi phí** | Đã tính phí thực tế, right-sizing, license, lưu lượng liên vùng/ra Internet và tài nguyên rảnh? |
| **Sustainability — Bền vững** | Có giảm tài nguyên nhàn rỗi và cải thiện mức sử dụng tài nguyên theo nhu cầu thực? |

Các mục tiêu có thể xung đột. Ví dụ:

- Dùng **hai vùng khả dụng** thường cải thiện độ sẵn sàng nhưng tăng chi phí và yêu cầu thiết kế dữ liệu phù hợp.
- Chuyển database sang **managed service** giảm gánh nặng bảo trì hạ tầng, nhưng cần kiểm tra tính năng, chính sách backup và quyền truy cập của dịch vụ.
- **Tự động mở rộng** hữu ích với tải biến động, nhưng ứng dụng có phiên đăng nhập lưu tại bộ nhớ cục bộ hoặc phụ thuộc disk riêng sẽ cần thay đổi.
- **Tách microservices** có thể cho phép triển khai độc lập nhưng cũng tạo thêm network hop, distributed tracing, quản lý lỗi và nhất quán dữ liệu.

Vì vậy, mỗi phương án 7R phải có **mục tiêu đo được**: ví dụ p95 latency dưới ngưỡng nghiệp vụ, RTO tối đa 60 phút, RPO tối đa 5 phút, chi phí chạy tháng nằm trong ngân sách, và thời gian phát hành giảm sau refactor. Đây là **ví dụ ngưỡng**, không phải mặc định áp dụng cho mọi hệ thống; giá trị cuối cùng phải do bên nghiệp vụ chấp thuận.

## 6. Từ lựa chọn R đến kiến trúc đích

### 6.1. Mạng và môi trường nền (landing zone)

Trước khi đưa production lên cloud, cần xác định tài khoản/project/subscription, phân tách môi trường, cấu trúc mạng, DNS, địa chỉ IP, tuyến kết nối và kiểm soát truy cập. Khi ứng dụng còn phụ thuộc tại chỗ, phải tính **độ trễ, băng thông, tính sẵn sàng và chi phí** của VPN hoặc đường kết nối riêng.

Đừng chỉ kiểm tra kết nối chiều ứng dụng gọi database: còn có callback, webhook, DNS nội bộ, đồng bộ danh tính, SMTP, máy chủ license, dịch vụ giám sát và hệ thống đối tác. Kiểm soát inbound/outbound, private endpoint, firewall/security group và phân tách secret phải được diễn giải từ luồng dữ liệu thực tế.

### 6.2. Compute và mô hình triển khai

- **Relocate/rehost:** xác định VM sizing, image, disk, khả năng chuyển đổi hypervisor, vùng triển khai và quy trình vá OS. Kiểm thử boot, driver, agent, thời gian khôi phục và hiệu năng storage.
- **Replatform:** xác định tác động của managed runtime, container orchestration hoặc PaaS lên health check, session, filesystem, cấu hình, kết nối database, giới hạn dịch vụ và CI/CD.
- **Refactor:** xây hợp đồng API và sự kiện, xử lý timeout/retry, idempotency, backpressure, phân tách ownership dữ liệu và khả năng tương thích ngược trong quá trình chuyển.
- **Repurchase:** thiết kế SSO/IAM, tích hợp, đồng bộ dữ liệu, data export, khả năng audit và phương án rời nhà cung cấp.

Không nên mặc định “cloud = serverless” hoặc “modernization = microservices”. Chọn compute sau khi đã có **mục tiêu tải, đặc điểm trạng thái, vận hành và kỹ năng của đội ngũ**.

### 6.3. Dữ liệu: điểm quyết định rủi ro cutover

Đối với dữ liệu quan trọng, kế hoạch phải trả lời:

1. **Nguồn sự thật (source of truth)** nằm ở đâu trước, trong và sau chuyển đổi?
2. Di chuyển bằng **backup/restore**, dump/import, replication, CDC hay đồng bộ ở tầng ứng dụng?
3. Có thể tạm ngừng ghi không? Nếu không, sẽ duy trì tính nhất quán và thứ tự cập nhật thế nào?
4. So khớp dữ liệu bằng gì: số bản ghi, checksum, tổng giao dịch, đối soát nghiệp vụ?
5. Có dữ liệu nhạy cảm, yêu cầu mã hóa, xóa dữ liệu hoặc lưu trú trong khu vực cụ thể không?
6. Nếu rollback, dữ liệu phát sinh sau khi chuyển hướng lưu lượng sẽ được xử lý thế nào?

**RPO** là lượng dữ liệu tối đa có thể mất được nghiệp vụ chấp nhận (thường đo bằng thời gian); **RTO** là thời gian tối đa để khôi phục dịch vụ sau gián đoạn. Snapshot hoặc replication có độ trễ không tự bảo đảm RPO bằng 0. Cần thử phục hồi bằng tình huống thật, đo số liệu và ghi rõ hạn chế của cơ chế đang dùng.

Đối với hệ thống đặt hàng/thanh toán, nên tránh trạng thái **ghi đồng thời vào hai database độc lập mà không có cơ chế điều phối rõ ràng**. Đường quay lại phiên bản cũ cần tính cả lược đồ dữ liệu, event đã phát, giao dịch đang xử lý và dữ liệu mới tạo sau cutover.

## 7. Quy trình migration theo các đợt có kiểm soát

Một chương trình có thể tổ chức thành sáu pha. Mỗi pha cần đầu ra và điểm xác nhận (gate) trước khi sang pha kế tiếp:

| Pha | Công việc trọng tâm | Điều kiện có thể chuyển tiếp |
|---|---|---|
| **1. Discover** | Kiểm kê ứng dụng, chủ sở hữu, dependencies, dòng dữ liệu, chi phí nền | Có bản đồ phụ thuộc và mức độ quan trọng; loại bỏ mục “không rõ chủ” |
| **2. Assess & decide** | Đề xuất 7R, phân tích TCO/rủi ro, thiết kế đích, ghi ADR | Phương án được xác nhận bởi nghiệp vụ, bảo mật, vận hành |
| **3. Prepare** | Thiết lập landing zone, IAM, mạng, logging, backup, CI/CD, runbook | Kiểm thử kết nối, quyền, bảo mật và khôi phục tối thiểu đạt yêu cầu |
| **4. Pilot & migrate** | Làm đợt thử tải thấp; chuyển ứng dụng/dữ liệu theo wave | Kiểm chứng chức năng, hiệu năng, đối soát dữ liệu và cửa sổ cutover |
| **5. Cutover & stabilize** | Chuyển traffic, theo dõi chỉ số, xử lý lỗi, sẵn sàng rollback | Hoạt động ổn định theo SLO trong thời gian theo dõi đã thống nhất |
| **6. Optimize & close** | Right-size, tối ưu chi phí, xóa tài nguyên cũ, cập nhật tài liệu | Hoàn tất chứng cứ bàn giao, DR test và ngừng chi phí không còn cần |

### Sắp xếp migration wave

Một **wave** nên gom các ứng dụng có phụ thuộc chặt chẽ hoặc cùng cửa sổ thay đổi. Có thể bắt đầu bằng workload ít ảnh hưởng, nhưng pilot phải đại diện đủ cho rủi ro thực tế: mạng hybrid, đồng bộ dữ liệu, IAM, nhật ký, khả năng quan sát và khôi phục.

Ví dụ, dịch vụ web và database ở hai bên kết nối hybrid với độ trễ cao có thể chạy chậm dù từng máy riêng lẻ đạt benchmark. Di chuyển từng máy theo danh sách mà không xét **đồ thị phụ thuộc** thường tạo lỗi khó phát hiện. Với nhóm liên quan, quyết định rõ thành phần nào chuyển cùng lúc, thành phần nào giữ lại và điều kiện cho giai đoạn vận hành lai.

### Runbook cho một lần cutover

Một runbook đủ dùng cần có **người phụ trách, mốc thời gian, thao tác, cách kiểm chứng, điều kiện dừng và quyền ra quyết định**. Trình tự tham khảo:

1. Chốt cửa sổ bảo trì và người liên hệ; kiểm tra backup/restore gần nhất, sức khỏe môi trường đích và quyền truy cập khẩn cấp.
2. Kiểm tra replication và độ trễ dữ liệu; nếu cần, bật chế độ chỉ đọc hoặc ngừng ghi có kiểm soát.
3. Hoàn tất đồng bộ, thực hiện kiểm tra nhất quán và thử giao dịch nghiệp vụ.
4. Chuyển traffic qua DNS/load balancer/routing; kiểm tra cả TTL, session và các kết nối tồn tại lâu.
5. Theo dõi tỷ lệ lỗi, p95/p99 latency, độ trễ replication, backlog queue, hoạt động thanh toán và chỉ số nghiệp vụ.
6. Quyết định **tiếp tục** hay **rollback** theo ngưỡng đã được duyệt; xử lý giao dịch phát sinh trong thời gian chuyển trước khi phục hồi đường cũ.
7. Trong giai đoạn ổn định, theo dõi tăng cường rồi mới ngừng tài nguyên cũ khi đã hết thời hạn cần thiết.

**Rollback không phải chỉ trỏ DNS ngược lại.** Với ứng dụng có ghi dữ liệu, rollback còn là bài toán tương thích schema, dữ liệu mới và side effect sang hệ thống ngoài. Nếu không thể đảo ngược an toàn, phải xây phương án **roll-forward** và nêu rõ rủi ro trước khi cutover.

## 8. Tình huống xuyên suốt: hiện đại hóa nền tảng đặt hàng

### Bối cảnh và yêu cầu

Giả sử hệ thống đặt hàng chạy một ứng dụng monolith Java trên hai VM, dùng một PostgreSQL tự quản lý, kết nối cổng thanh toán và gửi email đồng bộ. Mỗi đợt khuyến mãi lưu lượng tăng mạnh; triển khai phiên bản mới thường cần bảo trì. Các con số dưới đây **chỉ là giả định bài tập**:

- Mục tiêu mở rộng: chịu tải đỉnh gấp 4 lần ngày thường.
- Mục tiêu vận hành: triển khai với thời gian gián đoạn tối thiểu.
- Mục tiêu phục hồi: RTO không quá 60 phút, RPO không quá 5 phút, **cần xác nhận riêng** mức chấp nhận thất thoát dữ liệu với nghiệp vụ đặt hàng/thanh toán.
- Giới hạn: doanh nghiệp có sáu tháng để rời data center nhưng chưa đủ nguồn lực viết lại toàn bộ.

### So sánh ba cách khả thi

**Phương án A — Rehost toàn bộ:** chuyển monolith và PostgreSQL lên VM đám mây. Nhanh để thoát data center; đội ngũ vẫn phải tự quản lý database, backup, patch và HA. Nếu ứng dụng vẫn có trạng thái phiên trên VM, tăng số máy có thể gây lỗi đăng nhập hoặc giỏ hàng.

**Phương án B — Replatform chọn lọc:** ứng dụng chạy trên nền tảng compute có health check/autoscaling phù hợp; PostgreSQL chuyển sang dịch vụ quản lý tương thích. Cần thử extension, encoding, collation, phiên bản, transaction, connection pool, replication và hiệu năng truy vấn. Mục tiêu là giảm rủi ro vận hành trước, chưa tách module nghiệp vụ.

**Phương án C — Refactor theo lát cắt:** giữ lõi đặt hàng hiện hữu, tách xử lý email/thông báo thành consumer bất đồng bộ; về sau chỉ tách phần catalog hoặc tìm kiếm khi có nhu cầu tải và ownership rõ. Sự kiện liên quan đơn hàng cần **transactional outbox** (hoặc giải pháp tương đương), consumer **idempotent**, cơ chế retry và dead-letter queue để giảm nguy cơ mất/trùng side effect. Không tách ngay giao dịch đặt hàng/thanh toán thành nhiều database nếu chưa giải quyết nhất quán nghiệp vụ.

Một lộ trình có thể là **replatform ở giai đoạn một, refactor các điểm nghẽn ở giai đoạn hai**. Nếu hạn rời data center gấp hơn độ sẵn sàng của replatform, có thể rehost trước và chấp nhận bước trung gian; cần ghi chi phí chạy song song và kế hoạch xóa nợ kỹ thuật. Sự lựa chọn phụ thuộc bằng chứng đo đạc, không dựa vào xu hướng công nghệ.

### Phác họa kiến trúc mục tiêu theo giai đoạn

~~~mermaid
flowchart LR
    U["Người dùng"] --> E["DNS / WAF / Load balancer"]
    E --> A["Ứng dụng đặt hàng<br/>nhiều instance"]
    A --> D[("PostgreSQL managed<br/>backup + HA")]
    A --> O["Outbox / phát sự kiện"]
    O --> Q["Hàng đợi sự kiện"]
    Q --> N["Worker gửi thông báo"]
    A --> P["Cổng thanh toán bên ngoài"]
    A -.-> M["Logging / metrics / tracing"]
    N -.-> M
~~~

Sơ đồ là một **thiết kế tham khảo**, không mặc định tất cả dịch vụ đều cần ở giai đoạn đầu. Cần bổ sung kiểm soát IAM, mạng riêng, mã hóa, secret, phân vùng lỗi, backup, kiểm thử restore và giới hạn tải theo yêu cầu thực tế. Hệ thống chỉ được công nhận đạt RTO/RPO sau khi diễn tập và đo kết quả.

### Bằng chứng nghiệm thu của ví dụ

- **Nghiệp vụ:** tạo/sửa/hủy đơn, thanh toán, hoàn tiền, email, lịch batch, tích hợp kho và đối soát chạy đúng.
- **Dữ liệu:** số lượng và trạng thái đơn khớp theo đối soát; không có giao dịch “mồ côi”; xử lý sự kiện trùng an toàn.
- **Độ tin cậy:** thử lỗi một instance/điểm hạ tầng; chứng minh restore và failover phù hợp yêu cầu.
- **Hiệu năng:** kiểm thử tải thường và tải đỉnh, theo dõi p95 latency, CPU, database connections và queue lag.
- **Bảo mật:** xác thực/ủy quyền đúng, secret không nằm trong image, truy cập database được giới hạn, audit log đáp ứng quy định.
- **Vận hành/chi phí:** dashboard, cảnh báo có owner; hóa đơn chạy thử và dự báo TCO nằm trong phạm vi đã duyệt.

## 9. Quyết định theo điểm số: hỗ trợ, không thay thế kiến trúc

Khi có nhiều phương án hợp lệ, dùng ma trận có trọng số để thảo luận minh bạch. Ví dụ, với nền tảng đặt hàng ở trên, cho điểm **1–5 (5 là tốt nhất)** theo giả định của nhóm:

| Tiêu chí | Trọng số | Rehost | Replatform | Refactor ngay |
|---|---:|---:|---:|---:|
| Rủi ro triển khai thấp | 25% | 4 | 4 | 2 |
| Hoàn thành nhanh | 20% | 5 | 4 | 2 |
| TCO ba năm thuận lợi | 20% | 3 | 4 | 3 |
| Dễ vận hành | 15% | 2 | 4 | 5 |
| Linh hoạt phát triển/mở rộng | 20% | 2 | 4 | 5 |
| **Điểm tổng có trọng số** | **100%** | **3,30/5** | **4,00/5** | **3,25/5** |

Cách tính: **điểm tổng = tổng (trọng số × điểm tiêu chí)**, với trọng số ở dạng 0–1. Ví dụ Replatform: 0,25 × 4 + 0,20 × 4 + 0,20 × 4 + 0,15 × 4 + 0,20 × 4 = **4,00**.

Bảng chỉ minh họa phương pháp; điểm phải được nhóm nghiệp vụ, kỹ thuật, an ninh và tài chính thống nhất dựa trên số liệu. **Điều kiện bắt buộc** như residency, yêu cầu pháp lý, tính tương thích hoặc RTO/RPO là **điểm loại trực tiếp**: phương án vi phạm không được “cứu” bằng tổng điểm cao.

### Đừng nhầm chi phí hạ tầng với tổng chi phí sở hữu

Một mô hình TCO tối thiểu trong 3 năm có thể tính:

~~~text
TCO_3_năm =
  chi_phí_chuyển_đổi_một_lần
  + chi_phí_compute_storage_network_36_tháng
  + chi_phí_license_và_SaaS_36_tháng
  + chi_phí_nhân_sự_vận_hành_36_tháng
  + chi_phí_dual_run_và_hệ_thống_tại_chỗ_còn_lại
  + chi_phí_backup_DR_giám_sát_bảo_mật
  + chi_phí_rời_nhà_cung_cấp_nếu_có
~~~

Tránh bỏ quên network egress, truy xuất dữ liệu liên vùng, hỗ trợ, bản quyền OS/database, thời gian đội ngũ phát triển và chi phí tắt hệ thống cũ. Với **Retire**, cần tính cả lưu trữ dữ liệu tuân thủ; với **Repurchase**, cần tính phí theo user/giao dịch và khả năng xuất dữ liệu; với **Refactor**, tính chi phí phát triển và vận hành hai kiến trúc trong thời gian chuyển tiếp.

## 10. Các lỗi thường gặp và cách phòng tránh

| Dấu hiệu | Vì sao nguy hiểm | Cách kiểm soát |
|---|---|---|
| “Chuyển hết theo rehost để nhanh” | Giữ lại lỗi thiết kế và chi phí VM không tối ưu | Đặt mốc tối ưu hóa, right-sizing và ADR cho bước kế tiếp |
| “Cứ microservices là hiện đại” | Tăng độ phức tạp dữ liệu, network, release và quan sát | Chỉ tách theo nhu cầu độc lập rõ, có năng lực vận hành |
| Chỉ di chuyển server, quên tích hợp | Lỗi DNS, batch, identity, đường truyền và callback | Dependency mapping và kiểm thử luồng end-to-end |
| Gắn nhãn retire vì “không thấy ai dùng” | Có thể còn job ẩn, nghĩa vụ lưu giữ hoặc audit | Xác nhận owner, access log, backup, retention, phụ thuộc |
| Repurchase nhưng bỏ qua quy trình | SaaS không khớp trường dữ liệu, quyền và workflow | Gap analysis, dữ liệu mẫu, thử tích hợp và kế hoạch đào tạo |
| Cutover không có thử nghiệm rollback | Dữ liệu mới làm đường quay lại mất an toàn | Thử rehearsal, đồng bộ và đối soát, xác định điểm không thể đảo ngược |
| Chỉ tính giá VM so với server | Bỏ sót chi phí chuyển, license, network, dual-run | So sánh TCO và tác động vận hành theo cùng mốc thời gian |
| Retain nhưng không có ngày đánh giá lại | Hệ thống cũ tiếp tục tích lũy rủi ro và chi phí | Gắn owner, điều kiện kích hoạt đánh giá và mốc rà soát |

## 11. Bài tập áp dụng

Bạn là kiến trúc sư cloud cho một doanh nghiệp có bốn workload:

**(A)** Hệ thống chấm công cũ không còn ai đăng nhập từ sau khi chuyển sang nền tảng mới, nhưng dữ liệu liên quan hồ sơ nhân sự phải được giữ theo chính sách. **(B)** Hệ thống sản xuất dùng thiết bị serial chuyên dụng, nhà sản xuất chưa hỗ trợ chạy ngoài nhà máy. **(C)** API báo giá có mã nguồn còn được bảo trì, database tự quản lý tốn nhiều công và cần giảm rủi ro failover. **(D)** Công cụ chăm sóc khách hàng tự xây chỉ có các nghiệp vụ tiêu chuẩn, đội ngũ đang cân nhắc SaaS.

Hãy thực hiện:

1. Chọn **một R ưu tiên** cho mỗi workload, nêu ít nhất hai bằng chứng cần kiểm chứng trước khi chốt.
2. Với (C), đề xuất kiến trúc đích sơ bộ: mạng, compute, database, backup/DR, logging và quyền truy cập; chỉ rõ việc gì thuộc trách nhiệm của nhà cung cấp cloud và của đội ngũ ứng dụng.
3. Với (A) và (D), thiết kế cách giữ/xuất dữ liệu, đối soát và điều kiện ngừng hệ thống cũ.
4. Chọn một workload để lập **runbook cutover**, trong đó có tiêu chí go/no-go, cách kiểm chứng và kịch bản rollback.
5. Nêu ít nhất một **đánh đổi Well-Architected** giữa tin cậy, chi phí, hiệu năng, bảo mật hoặc vận hành.

**Gợi ý tự kiểm tra:** (A) nghiêng về **Retire**, nhưng phải giữ hồ sơ đúng chính sách; (B) **Retain** có điều kiện và mốc đánh giá lại; (C) thường là **Replatform** nếu database/runtime tương thích; (D) có thể là **Repurchase** nếu SaaS đáp ứng dữ liệu, tích hợp, bảo mật, chi phí và cách làm việc của người dùng. Nếu có bằng chứng mới, lựa chọn cũng có thể thay đổi.

## 12. Danh sách kiểm tra trước khi ký duyệt phương án 7R

- [ ] Workload có owner, yêu cầu nghiệp vụ, mức quan trọng và phụ thuộc được xác minh.
- [ ] R được chọn có **lý do, phương án thay thế và điều kiện loại trực tiếp**; không dựa vào khẩu hiệu.
- [ ] Kiến trúc đích nêu rõ mạng, compute, dữ liệu, IAM, monitoring, backup, HA/DR và trách nhiệm vận hành.
- [ ] RTO/RPO, SLO, performance, security và compliance có tiêu chí nghiệm thu đo được.
- [ ] Dữ liệu được đối soát; cutover và rollback/roll-forward có thử diễn tập.
- [ ] TCO gồm chuyển đổi, dual-run, licensing, network và vận hành dài hạn.
- [ ] Có migration wave, runbook, người quyết định go/no-go và kế hoạch chuyển giao.
- [ ] Với **Retain**, có ngày đánh giá lại; với **Retire**, có chứng cứ ngừng phụ thuộc và bảo toàn dữ liệu; với các R còn lại, có bước tối ưu hóa sau migration.

**Nguyên tắc cốt lõi:** 7R là quyết định **dựa trên giá trị và rủi ro của từng workload**. Kiến trúc đám mây thành công khi đáp ứng yêu cầu nghiệp vụ và chứng minh được khả năng vận hành, bảo mật, phục hồi, mở rộng và chi phí theo mục tiêu đã thống nhất.
