# Ghi quyết định kiến trúc bằng ADR: bối cảnh, lựa chọn và hệ quả

Một sơ đồ kiến trúc cho biết hệ thống **được tổ chức như thế nào**: thành phần nào gọi thành phần nào, dữ liệu đi qua đâu, mạng và compute đặt ở vùng nào. Nhưng chỉ nhìn sơ đồ, người mới tham gia dự án thường không biết **vì sao** nhóm chọn managed database thay vì tự quản, **vì sao** chỉ triển khai một region hay **vì sao** thông báo được xử lý bằng hàng đợi.

**Architecture Decision Record (ADR)** là một tài liệu ngắn, có phiên bản, ghi lại **một quyết định kiến trúc quan trọng**, bối cảnh dẫn đến quyết định, các lựa chọn được xem xét, lý do chọn và hệ quả được chấp nhận. ADR giúp quyết định có thể được giải thích, phản biện, kiểm chứng và xem lại khi giả định thay đổi. Nó không thay thế bản thiết kế chi tiết, sơ đồ, runbook hay tài liệu cấu hình, mà kết nối chúng bằng **lý do ra quyết định**.

Trong học phần thiết kế kiến trúc đám mây, ADR đặc biệt hữu ích vì quyết định về **mạng, compute, dữ liệu và mô hình triển khai** luôn có đánh đổi giữa **độ tin cậy, bảo mật, hiệu năng, khả năng mở rộng, chi phí và vận hành**. Thực hành Well-Architected khuyến khích xem những đánh đổi này bằng bằng chứng thay vì dựa vào tên dịch vụ hoặc sở thích cá nhân.

Sau bài học, bạn có thể:

- Phân biệt ADR với sơ đồ kiến trúc, tài liệu thiết kế, ticket triển khai và nhật ký thay đổi.
- Xác định **khi nào một quyết định cần ADR**, phạm vi nào là vừa đủ và ai cần tham gia.
- Viết ADR tự chứa với **bối cảnh, động lực, các phương án, quyết định và hệ quả**.
- Ghi lại yêu cầu phi chức năng, giả định, bằng chứng và tiêu chí kiểm chứng cho quyết định cloud.
- Quản lý vòng đời ADR từ đề xuất đến được chấp nhận, thay thế hoặc không còn áp dụng.
- Đọc và phản biện một ADR theo góc nhìn Well-Architected.

## 1. ADR giải quyết vấn đề gì?

Hãy hình dung một nhóm xây ứng dụng đặt lịch. Tháng đầu tiên, nhóm chọn managed relational database vì cần transaction và muốn giảm công quản trị. Sáu tháng sau, thành viên mới thấy database này trên sơ đồ nhưng không biết lý do. Người đó đề xuất chuyển sang NoSQL vì “mở rộng dễ hơn”. Nếu không có ADR, nhóm phải đào lại cuộc họp, tin nhắn và trí nhớ của các thành viên.

Một ADR tốt cho phép người đọc hiểu:

1. **Lúc quyết định, vấn đề gì phải được giải quyết?**
2. **Những yêu cầu và giới hạn nào thật sự chi phối lựa chọn?**
3. **Nhóm đã xem xét phương án nào, tại sao không chọn chúng?**
4. **Giải pháp nào được chọn và trong phạm vi nào?**
5. **Nhóm chấp nhận lợi ích, chi phí, rủi ro và việc phải làm tiếp nào?**
6. **Điều kiện nào khiến quyết định cần được xem lại?**

ADR còn tạo **đường truy vết** từ mục tiêu nghiệp vụ đến kiến trúc thực thi. Ví dụ: “không được đặt trùng khung giờ” → “cần bảo đảm tính nhất quán tại điểm ghi” → “chọn database hỗ trợ transaction và constraint phù hợp” → “kiểm thử nhiều yêu cầu đặt lịch đồng thời”.

### ADR không phải tài liệu nào?

| Tài liệu | Trả lời chính | Quan hệ với ADR |
| --- | --- | --- |
| **Sơ đồ kiến trúc** | Hệ thống gồm những thành phần và mối nối nào? | ADR lý giải các lựa chọn thể hiện trên sơ đồ |
| **Tài liệu thiết kế / RFC** | Toàn bộ giải pháp được phân tích, thống nhất và triển khai như thế nào? | Một RFC có thể dẫn tới nhiều ADR, mỗi ADR ghi một quyết định |
| **ADR** | Tại sao chọn phương án này thay vì phương án khác? | Lưu quyết định, căn cứ, đánh đổi và điều kiện xem lại |
| **Ticket / backlog item** | Ai làm việc gì, khi nào? | Thực hiện một hoặc nhiều hệ quả/hành động từ ADR |
| **Runbook** | Khi triển khai, vận hành hoặc gặp lỗi thì làm gì? | Cụ thể hóa hoạt động vận hành đã cam kết trong ADR |
| **Architecture review / Well-Architected report** | Rủi ro và điểm cần cải thiện nằm ở đâu? | Có thể tạo ADR mới hoặc yêu cầu đánh giá lại ADR cũ |
| **Changelog / release note** | Phiên bản nào đã thay đổi? | Thông báo thay đổi, không nhất thiết ghi lý do dài hạn |

Không nên đưa toàn bộ tài liệu thiết kế hàng chục trang vào một ADR. ADR cần **đủ độc lập để hiểu được quyết định**, đồng thời liên kết đến sơ đồ, PoC, kết quả thử tải, ước tính chi phí và runbook khi cần.

## 2. Khi nào cần viết ADR?

Một thay đổi xứng đáng có ADR khi nó **ảnh hưởng đáng kể đến kiến trúc hoặc khó đảo ngược**, có **nhiều phương án hợp lý**, hoặc liên quan đến **rủi ro, trách nhiệm, chi phí dài hạn**.

Ví dụ thường nên ghi ADR:

- Chọn mô hình **single-region, multi-AZ hay multi-region** và mức RTO/RPO cần đạt.
- Chọn **managed database quan hệ, NoSQL, hoặc tự quản database**.
- Chọn **VM, managed container platform, Kubernetes, PaaS hay serverless** cho một workload.
- Chọn **đồng bộ hay hàng đợi sự kiện** cho một luồng nghiệp vụ.
- Quyết định **phân tách tài khoản, ranh giới mạng, kết nối private và quản lý danh tính**.
- Chấp nhận dùng một **dịch vụ đặc thù nhà cung cấp** và xác định rủi ro chuyển đổi.
- Chọn chiến lược **mã hóa, quản lý khóa, sao lưu và khôi phục** có ảnh hưởng lớn.
- Chuyển từ **modular monolith** sang microservices hoặc thay đổi ownership dữ liệu.

Ví dụ thường **không cần ADR riêng**: tăng kích thước instance tạm thời trong một khoảng thử tải đã được duyệt, sửa nhãn tài nguyên, đổi tên biến nội bộ, chỉnh ngưỡng alert theo quy trình có sẵn. Nếu những việc này thay đổi cam kết SLO, chi phí lớn hoặc mô hình bảo mật thì vẫn có thể trở thành quyết định cần ADR.

### Một quyết định, một ADR

Tiêu chí thực dụng là ADR nên diễn đạt được bằng **một câu quyết định**:

> Sử dụng managed PostgreSQL cho dữ liệu đặt lịch vì cần transaction nhất quán và đội vận hành nhỏ; kiểm chứng hiệu năng, phục hồi và chi phí trước production.

Nếu tài liệu đang đồng thời quyết định database, queue, Kubernetes, multi-region và mô hình danh tính, hãy tách thành nhiều ADR có liên kết. Mỗi quyết định có động lực, hệ quả, thời điểm thay đổi và người sở hữu khác nhau.

Ngược lại, đừng tách vụn đến mức mỗi cấu hình nhỏ cần một ADR. Mục tiêu là lưu **quyết định tồn tại lâu hơn một phiên triển khai**, không phải ghi lại mọi thao tác vận hành.

## 3. Cấu trúc cốt lõi của một ADR

Không có một khuôn duy nhất bắt buộc. Mẫu dưới đây cố ý giữ các trường cốt lõi dễ đọc, đồng thời bổ sung các trường giúp kiểm tra quyết định cloud.

| Thành phần | Nội dung cần ghi | Câu hỏi để tự kiểm tra |
| --- | --- | --- |
| **ID, tiêu đề, ngày, trạng thái** | Định danh ổn định, câu mô tả quyết định, tình trạng hiện tại | Người đọc tìm được quyết định và biết nó còn hiệu lực không? |
| **Bối cảnh (Context)** | Vấn đề, hiện trạng, yêu cầu nghiệp vụ, giới hạn và tác nhân quyết định | Vì sao nhóm phải quyết định ở thời điểm này? |
| **Động lực / tiêu chí (Decision drivers)** | NFR, rủi ro, ngân sách, thời gian, kỹ năng, tuân thủ, thứ tự ưu tiên | Dựa trên tiêu chí nào để so sánh? |
| **Phương án (Options considered)** | Các lựa chọn khả thi, kể cả giữ hiện trạng khi phù hợp | Nhóm đã tránh so sánh thiên lệch chưa? |
| **Quyết định (Decision)** | Phương án chọn, phạm vi áp dụng và các điều kiện | Ai phải triển khai điều gì? |
| **Lý do (Rationale)** | Vì sao phương án này đáp ứng tiêu chí tốt hơn ở bối cảnh hiện tại | Nếu điều kiện thay đổi, có thể đánh giá lại được không? |
| **Hệ quả (Consequences)** | Lợi ích, đánh đổi, rủi ro còn lại, tác động vận hành và công việc phát sinh | Đã nêu cả mặt bất lợi, trách nhiệm và chi phí chưa? |
| **Bằng chứng / kiểm chứng (Validation)** | PoC, benchmark, threat model, thử restore, chi phí, kết quả đo | Có cách chứng minh quyết định đáp ứng yêu cầu không? |
| **Điều kiện xem lại (Review triggers)** | Các sự kiện/giới hạn khiến ADR cần review | Khi nào quyết định có thể hết phù hợp? |
| **Liên kết (References)** | Sơ đồ, yêu cầu, tài liệu thử nghiệm, ADR liên quan | Người sau có kiểm tra lại dữ kiện được không? |

### 3.1. Bối cảnh không phải lời quảng cáo sản phẩm

Bối cảnh cần mô tả **vấn đề và sự thật liên quan**, không viết trước kết luận.

Chưa đủ:

> Chúng ta cần dùng Kubernetes vì nó là tiêu chuẩn hiện đại.

Hữu ích hơn:

> Đội phát triển có sáu kỹ sư, cần vận hành hai API Java và một worker. Tải chưa được đo đầy đủ; mục tiêu ra mắt trong tám tuần, có yêu cầu triển khai liên tục và phục hồi khi một instance lỗi. Nhóm hiện không có kỹ sư chuyên trách quản trị cluster.

Bối cảnh tốt giúp người đọc nhận ra tiêu chí đánh đổi: tốc độ triển khai, độ sẵn sàng, công vận hành và khả năng mở rộng.

### 3.2. Ghi rõ yêu cầu, giả định và ràng buộc

Phân biệt ba loại dữ kiện:

- **Yêu cầu đã xác nhận:** ví dụ dữ liệu khách hàng phải lưu trong vùng đã được phê duyệt theo hợp đồng.
- **Giả định cần kiểm chứng:** ví dụ lưu lượng đỉnh sẽ không vượt 300 yêu cầu/giây trong sáu tháng đầu.
- **Ràng buộc thực tế:** ví dụ ngân sách vận hành có giới hạn hoặc đội chưa có kỹ năng điều phối Kubernetes.

Nếu ghi một con số, phải nêu **nguồn**, **cách đo** hoặc ghi nhãn **giả định minh họa**. Một câu “cần nhanh” không đủ để chọn compute; “API đọc có p95 dưới 300 ms tại mức tải mục tiêu” tạo ra tiêu chí có thể thử tải.

### 3.3. Viết quyết định ở dạng khẳng định rõ phạm vi

Một quyết định tốt phải cho biết:

- **Chọn cái gì:** dịch vụ hay mô hình cụ thể.
- **Áp dụng ở đâu:** workload, môi trường, vùng và đường đi dữ liệu.
- **Chưa giải quyết gì:** các vấn đề sẽ có ADR hoặc thử nghiệm riêng.
- **Điều kiện bắt buộc:** bảo mật, độ tin cậy, dữ liệu, chi phí và những phép thử cần đạt.

Tránh câu “nên cân nhắc dùng database managed”. Nếu chưa quyết định, để trạng thái **Proposed**, nêu các lựa chọn và câu hỏi chưa giải quyết.

## 4. Quy trình đưa ra quyết định và viết ADR

Một ADR có giá trị khi được tạo **gần thời điểm ra quyết định**, trước khi toàn bộ chi phí chuyển đổi đã phát sinh. Quy trình có thể diễn ra trong một buổi review nhỏ, miễn là có thông tin và người có trách nhiệm phù hợp.

~~~mermaid
flowchart TD
    N["Phát hiện vấn đề cần quyết định"] --> C["Ghi bối cảnh, yêu cầu và giả định"]
    C --> O["Đề xuất các phương án khả thi"]
    O --> E["So sánh đánh đổi và thu bằng chứng"]
    E --> P["ADR trạng thái Proposed"]
    P --> R{"Review đủ căn cứ?"}
    R -- "Chưa" --> X["PoC, đo tải, threat model, ước tính chi phí"]
    X --> E
    R -- "Có" --> A["Chấp nhận quyết định và giao việc"]
    A --> V["Triển khai, đo và liên kết bằng chứng"]
    V --> T{"Giả định hoặc yêu cầu đổi?"}
    T -- "Chưa" --> V
    T -- "Có" --> S["Review và lập ADR thay thế nếu cần"]
~~~

**Bước 1 — Chốt câu hỏi quyết định.** Ví dụ: “Lựa chọn nơi lưu dữ liệu đặt lịch có yêu cầu chống đặt trùng là gì?”. Một câu hỏi hẹp giúp tránh tranh luận lan sang toàn bộ nền tảng.

**Bước 2 — Ghi bối cảnh và người chịu tác động.** Đối chiếu yêu cầu từ product, SRE, security, data và tài chính khi liên quan; phân biệt sự thật hiện tại với dự báo.

**Bước 3 — Đề xuất phương án hợp lý.** Nêu ít nhất các phương án có thể đáp ứng mục tiêu, bao gồm giữ hiện trạng nếu đó là một lựa chọn. Tránh tạo phương án yếu một cách giả tạo chỉ để làm nổi bật phương án mong muốn.

**Bước 4 — So sánh bằng tiêu chí đã thống nhất.** Xem độ tin cậy, bảo mật, tốc độ ra mắt, hiệu năng, chi phí, vận hành, dữ liệu, ràng buộc nhà cung cấp và khả năng đảo ngược. Độ quan trọng của từng tiêu chí phải dựa trên nghiệp vụ.

**Bước 5 — Thu bằng chứng ở chỗ rủi ro cao.** PoC, load test, restore test, mô hình quyền, thử failover, đo log delivery hoặc ước tính chi phí dựa trên cấu hình/tải cụ thể. Đừng chỉ ghi “nhà cung cấp hỗ trợ HA” như bằng chứng RTO đã đạt.

**Bước 6 — Quyết định, ghi hệ quả và điều kiện kiểm chứng.** Người có thẩm quyền chấp nhận hoặc từ chối; tạo ticket cho công việc cần thực hiện và chọn chỉ số kiểm tra.

**Bước 7 — Bảo quản lịch sử.** Khi thay đổi, liên kết ADR mới với ADR cũ và giữ nguyên lịch sử lựa chọn ban đầu, để người sau hiểu vì sao thiết kế tiến hóa.

### Ai chịu trách nhiệm?

| Vai trò | Trách nhiệm trong ADR |
| --- | --- |
| **Người đề xuất / Author** | Nêu bối cảnh, phương án, bằng chứng và nội dung dự thảo |
| **Decision owner / Approver** | Chấp nhận đánh đổi và quyết định trong phạm vi được ủy quyền |
| **Reviewers** | Kiểm tra tính đúng đắn, hậu quả về security, reliability, data, cost và khả năng vận hành |
| **Implementers** | Tạo thay đổi và kiểm thử theo quyết định; báo khi giả định sai |
| **Người duy trì kiến trúc** | Giữ liên kết, trạng thái và lịch review được cập nhật |

Một nhóm nhỏ có thể để một người đảm nhiệm nhiều vai trò, nhưng cần rõ **ai có quyền chấp nhận rủi ro**. Ý kiến của reviewer về một nguy cơ bảo mật không tự biến thành trách nhiệm của reviewer nếu doanh nghiệp chấp nhận rủi ro đó.

## 5. Ví dụ ADR hoàn chỉnh: chọn database cho dịch vụ đặt lịch

**Tình huống giả định:** Một nhóm xây ứng dụng đặt lịch khám tư vấn trên cloud. Ứng dụng cần ngăn hai khách hàng đặt cùng một bác sĩ trong cùng một khung giờ cố định. Có sáu kỹ sư, một người kiêm nhiệm vận hành. Hệ thống dự kiến tăng trưởng nhưng chưa có số liệu dài hạn.

Các thông số dưới đây **chỉ là dữ kiện minh họa cho bài học**, không phải cam kết của dịch vụ cloud:

| Điều kiện | Giá trị giả định | Ý nghĩa |
| --- | --- | --- |
| Dự báo cao điểm | 250 yêu cầu/giây toàn ứng dụng, 20 yêu cầu đặt lịch/giây | Cần thử tải đúng tỷ lệ đọc/ghi, giao dịch cạnh tranh |
| Tính đúng đắn | Không có hai lịch thành công cho cùng bác sĩ + khung giờ | Cần ràng buộc dữ liệu tại điểm ghi |
| SLO | 99,9% giao dịch đặt lịch hợp lệ thành công trong 30 ngày | Cần xác định SLI, xử lý lỗi phụ thuộc và giám sát |
| RTO | Tối đa 60 phút | Phải thử khôi phục theo kịch bản sự cố |
| RPO | Tối đa 15 phút | Backup/replication và khả năng phục hồi cần đo |
| Ngân sách | Đội ngũ và chi phí vận hành có giới hạn | Ưu tiên giảm công tự quản khi có lợi |
| Khả năng thay đổi | Tải có thể tăng gấp đôi trong đợt khuyến mại | Cần cơ chế scale và đánh giá nút thắt |

### ADR-007 — Chọn managed relational database cho giao dịch đặt lịch

> **ID:** ADR-007  
> **Trạng thái:** Accepted  
> **Ngày chấp nhận:** 2026-11-18 (minh họa)  
> **Chủ sở hữu:** Nhóm phụ trách Booking  
> **Phạm vi:** dữ liệu lịch hẹn thuộc Booking Service, môi trường production  
> **Liên quan:** sơ đồ dữ liệu Booking, yêu cầu SLO/RTO/RPO, kế hoạch thử tải và phục hồi

#### Bối cảnh

Booking Service phải lưu giao dịch đặt lịch sao cho **không có hai giao dịch cùng chiếm một khung giờ đã xác định**. Dữ liệu lịch hẹn có liên hệ với khách hàng, bác sĩ, trạng thái và lịch sử thay đổi. Đội vận hành nhỏ, chưa có năng lực trực và bảo trì cluster database tự quản liên tục. Hệ thống cần phục hồi được khi xảy ra lỗi instance hoặc sự cố dữ liệu.

Cần lựa chọn nơi lưu dữ liệu có transaction phù hợp, giữ được tính đúng đắn khi nhiều request đồng thời, hỗ trợ backup/restore và có tổng chi phí vận hành chấp nhận được.

#### Động lực quyết định

1. **Ưu tiên cao nhất:** bảo toàn tính đúng đắn của giao dịch đặt lịch ngay cả khi API gửi lại request hoặc nhiều request cạnh tranh.
2. **Độ tin cậy:** giải pháp cần có thiết kế HA, backup và kế hoạch phục hồi được diễn tập so với RTO/RPO đã thống nhất.
3. **Khả năng vận hành:** giảm gánh nặng quản trị OS, patching, failover và backup so với đội ngũ hiện có.
4. **Hiệu năng:** đáp ứng tải dự báo dựa trên phép thử, theo dõi p95/p99, khả năng kết nối và tranh chấp khóa.
5. **Chi phí:** xem giá dịch vụ theo cấu hình, storage/IOPS, backup, mạng, monitoring và nhân lực.
6. **Khả năng thay thế:** dữ liệu có thể trích xuất, schema và extension được kiểm kê, quy trình restore được thử.

#### Các phương án xem xét

| Phương án | Lợi ích chính | Chi phí/rủi ro | Đánh giá trong bối cảnh |
| --- | --- | --- | --- |
| **A. Managed relational database hỗ trợ transaction** | Giảm việc tự quản, có cơ chế backup/HA tùy cấu hình; phù hợp dữ liệu quan hệ | Phụ thuộc dịch vụ và quota; vẫn cần thiết kế HA/DR, kiểm tra failover, chi phí cơ sở | **Chọn**, có điều kiện kiểm chứng |
| **B. PostgreSQL tự quản trên VM** | Kiểm soát cấu hình sâu, linh hoạt extension và phiên bản | Đội tự chịu patching, backup, replication, failover, monitoring và trực sự cố | Chưa phù hợp năng lực vận hành hiện tại |
| **C. NoSQL document/key-value managed** | Có thể phù hợp access pattern đơn giản và scale theo khóa | Cần thiết kế lại transaction, uniqueness, quan hệ và truy vấn; khác biệt semantics giữa dịch vụ | Chưa có lợi ích đủ rõ để đổi phức tạp dữ liệu |

So sánh này không khẳng định NoSQL không có transaction hoặc VM không đáng tin cậy. Tính năng, giới hạn và độ tin cậy thực tế phụ thuộc công nghệ và cách triển khai cụ thể; đánh giá ở đây gắn với **yêu cầu và năng lực đội ngũ đã nêu**.

#### Quyết định

Sử dụng **managed relational database tương thích PostgreSQL** cho dữ liệu đặt lịch trong Booking Service. Thiết lập giao dịch và ràng buộc duy nhất ở database phù hợp với mô hình khung giờ, triển khai theo cấu hình HA đã được lựa chọn, có backup và quy trình khôi phục. Trước khi production, xác nhận đầy đủ bằng thử nghiệm tải, cạnh tranh giao dịch và restore.

Với lịch chia thành **khung giờ cố định**, ví dụ khóa tự nhiên có thể là **(doctor_id, slot_start)**. Đối với cuộc hẹn có **khoảng thời gian thay đổi và có thể chồng lấn**, unique constraint đơn giản không đủ; phải thiết kế ràng buộc chống chồng lấn hoặc cơ chế đồng bộ giao dịch phù hợp. Quy tắc tính đúng đắn cần được kiểm thử độc lập với số instance API.

#### Lý do lựa chọn

Phương án A đáp ứng mô hình quan hệ và giao dịch của sản phẩm, đồng thời giảm công vận hành database so với B. Phương án C không thể hiện lợi ích cần thiết cho bài toán hiện tại trong khi tạo thêm công thiết kế và kiểm thử các quy tắc nhất quán. Nhóm chấp nhận chi phí managed service và sự phụ thuộc vào nhà cung cấp để ưu tiên **tính đúng đắn và khả năng vận hành**.

#### Hệ quả tích cực

- Domain có thể biểu diễn quan hệ, constraint và transaction rõ ràng.
- Giảm phần việc quản trị hạ tầng database mà nhóm phải trực tiếp duy trì.
- Có khả năng triển khai backup/HA theo dịch vụ được chọn nếu cấu hình và thử nghiệm đáp ứng yêu cầu.
- Dễ thực hiện các truy vấn liên quan đến lịch hẹn và trạng thái trong mô hình hiện tại.

#### Hệ quả bất lợi và rủi ro còn lại

- Chi phí tối thiểu, storage/IOPS, backup và đường truyền có thể cao hơn dự báo, cần kiểm soát ngân sách.
- Database vẫn có giới hạn kết nối, tài nguyên và quota; tăng số instance API có thể khiến database quá tải.
- Failover có thể ngắt kết nối đang mở hoặc khiến một số giao dịch trả lỗi; ứng dụng cần timeout, retry an toàn và idempotency.
- Đội ngũ vẫn phải quản trị schema, query, index, migration, quyền dữ liệu, mã hóa, secret và chất lượng backup.
- Sự phụ thuộc vào phiên bản, extension, cơ chế HA và dịch vụ managed có thể làm tăng chi phí chuyển cloud về sau.
- Backup hay replication tồn tại không tự chứng minh RPO 15 phút hoặc RTO 60 phút; cần đo bằng diễn tập.

#### Hành động và phép thử bắt buộc

| Hành động | Chủ trách nhiệm | Bằng chứng nghiệm thu |
| --- | --- | --- |
| Thiết kế constraint và transaction chống đặt trùng | Backend / Data | Test cạnh tranh cùng khung giờ: chỉ một booking hợp lệ được chấp nhận |
| Kiểm thử idempotency và retry khi kết nối lỗi | Backend | Một request lặp không tạo thêm lịch hẹn hoặc tác dụng phụ ngoài ý muốn |
| Thiết lập giới hạn kết nối và đo tải | Backend / Platform | Kết quả p95, error rate, connection pool và khả năng chịu 250 RPS giả định |
| Cấu hình backup và diễn tập restore | Platform / DBA | Thời gian và lượng dữ liệu mất thực tế so với RTO/RPO |
| Xác nhận IAM, TLS, mã hóa và truy cập mạng | Security / Platform | Các phép thử cho phép/từ chối, kiểm kê quyền và log audit |
| Lập dashboard và cảnh báo | SRE / Platform | Có metric về lỗi transaction, độ trễ, storage, backup và kết nối |
| Ước lượng chi phí trên tải cơ sở và cao điểm | Platform / Finance | Báo cáo cấu hình, mức dùng, rủi ro chi phí và ngưỡng cảnh báo |
| Kiểm tra khả năng xuất/nhập dữ liệu | Backend / Platform | Đối soát bản dữ liệu thử ở môi trường độc lập |

#### Điều kiện xem lại

- Tải ghi thực tế hoặc contention vượt ngưỡng đã nghiệm thu.
- SLO/RTO/RPO không còn đạt dù đã điều chỉnh trong phạm vi thiết kế.
- Yêu cầu dữ liệu, vùng lưu trú, tính năng mới hoặc hợp đồng nhà cung cấp thay đổi.
- Chi phí dịch vụ vượt ngưỡng được duyệt sau khi tính các phương án tối ưu.
- Cần tích hợp mô hình dữ liệu mới mà thiết kế hiện tại không đáp ứng hợp lý.

#### Phần chưa được quyết định

ADR này **không chọn nhà cung cấp cloud cụ thể**, không chốt region, kích thước instance, chỉ số IOPS, cách cấu hình connection pool hay cơ chế DR đa region. Các chi tiết này cần được xác nhận bằng thiết kế triển khai, benchmark và ADR khác nếu là quyết định kiến trúc quan trọng.

### Rút ra từ ví dụ

Đọc ADR-007, người mới biết **vì sao** database xuất hiện trong sơ đồ, những quyết định nào đã được cân nhắc và điều gì cần đo trước khi tuyên bố kiến trúc đạt SLO. Họ cũng thấy một quyết định **Accepted** không đồng nghĩa toàn bộ phép thử đã hoàn tất. Các điều kiện để triển khai production có thể vẫn là công việc phải thực hiện.

ADR không được dùng như bằng chứng thay cho thử nghiệm. Một câu “chọn HA database để đạt RTO 60 phút” chỉ là **mục tiêu thiết kế** nếu chưa có kết quả failover/restore đo được.

## 6. Mẫu Markdown ADR dùng lại trong dự án

Một nhóm có thể thống nhất tên file, biểu mẫu và nơi lưu. Mẫu sau đủ ngắn để người ra quyết định thực sự viết và đủ cụ thể để reviewer đánh giá:

~~~markdown
# ADR-<ID>: <Một câu mô tả quyết định>

- Trạng thái: Proposed | Accepted | Rejected | Superseded | Deprecated
- Ngày: YYYY-MM-DD
- Người đề xuất:
- Người quyết định:
- Phạm vi: workload, môi trường, region hoặc thành phần áp dụng
- ADR liên quan / thay thế:

## Bối cảnh

Vấn đề đang giải quyết là gì?
Hiện trạng, yêu cầu nghiệp vụ, ràng buộc, giả định cần kiểm chứng?
Nguồn của SLO, RTO/RPO, tải, ngân sách và quy định?

## Động lực / tiêu chí quyết định

- Tiêu chí 1 (mức ưu tiên, nguồn):
- Tiêu chí 2 (mức ưu tiên, nguồn):
- ...

## Phương án được xem xét

### Phương án A
- Lợi ích:
- Bất lợi và rủi ro:

### Phương án B
- Lợi ích:
- Bất lợi và rủi ro:

## Quyết định

Chọn phương án ... cho phạm vi ...
Điều kiện / ngoại lệ ...

## Lý do

Vì sao phương án được chọn đáp ứng tiêu chí tốt hơn?
Giả định trọng yếu nào dẫn đến kết luận?

## Hệ quả

- Tích cực:
- Bất lợi / trade-off:
- Rủi ro còn lại:
- Chi phí và trách nhiệm vận hành:

## Kiểm chứng / công việc tiếp theo

- Phép thử / số đo / tiêu chí đạt:
- Owner / thời hạn / liên kết ticket:

## Điều kiện xem lại

- Trigger thay đổi yêu cầu, dữ liệu, chi phí, tải hoặc rủi ro:

## Tham chiếu

- Sơ đồ:
- PoC / benchmark / threat model:
- Yêu cầu nghiệp vụ / SLO / hợp đồng:
~~~

**Lưu ý:** Các nhãn trạng thái là quy ước đội ngũ tự thống nhất. Có tổ chức chỉ dùng Proposed, Accepted và Superseded; một số dùng Rejected hoặc Deprecated. Quan trọng là **định nghĩa trạng thái rõ** và không nhập nhằng giữa “quyết định được duyệt” với “tính năng đã triển khai”.

### Ví dụ cấu trúc thư mục

~~~text
docs/
  architecture/
    overview.md
    booking-deployment.mmd
    decisions/
      0001-use-managed-relational-database.md
      0002-asynchronous-notifications.md
      0003-multi-az-deployment.md
    reviews/
      booking-well-architected-2026-11.md
~~~

Đây chỉ là **quy ước minh họa**, không đòi hỏi tạo các file này trong bài học. Mỗi ADR nên có **ID cố định**, tiêu đề dễ tìm và liên kết trong mục lục quyết định. Chọn cách đặt tên mà đội ngũ duy trì được lâu dài.

## 7. Quản lý vòng đời ADR khi kiến trúc thay đổi

Một hệ thống cloud luôn thay đổi tải, cấu hình, quy định và đội ngũ. ADR phải giúp **biết khi nào quyết định còn hiệu lực** và **theo dõi lý do thay đổi**.

| Trạng thái | Ý nghĩa thực tế | Việc tiếp theo |
| --- | --- | --- |
| **Proposed** | Đang lấy phản hồi hoặc kiểm chứng, chưa chốt | Review, PoC, làm rõ rủi ro và người quyết định |
| **Accepted** | Quyết định được chấp nhận trong phạm vi đã ghi | Tạo công việc triển khai và theo dõi kết quả |
| **Rejected** | Phương án/đề xuất này không được chấp nhận | Giữ lý do để tránh lặp lại tranh luận thiếu dữ kiện |
| **Superseded** | Quyết định đã được một ADR mới thay thế | Dẫn đến ADR mới; giữ lý do và lịch sử cũ |
| **Deprecated** | Không còn nên dùng cho thay đổi mới; phạm vi sử dụng cần được quản lý | Nêu kế hoạch ngừng dùng hoặc điều kiện loại bỏ |

Các trạng thái có thể được tinh giản theo quy trình thực tế. Không nên gán trạng thái **Accepted** chỉ vì file Markdown đã được merge; người quyết định cần thực sự chấp nhận nội dung và hệ quả.

### Vì sao không nên âm thầm viết lại ADR cũ?

Giả sử ADR-007 đã quyết định dùng relational database. Sau một năm, tải và mô hình dữ liệu thay đổi, nhóm chọn phân mảnh dữ liệu hoặc dùng database khác. Nếu chỉ sửa ADR-007 cho khớp kiến trúc hiện tại, lịch sử “vì sao trước đây chọn như vậy?” sẽ bị mất.

Thay vào đó:

1. Viết ADR mới với **bối cảnh và dữ liệu mới**, ví dụ ADR-021.
2. Dẫn rõ **Supersedes ADR-007** và chỉ ra điều kiện làm quyết định cũ không còn phù hợp.
3. Cập nhật ADR-007 thành **Superseded by ADR-021**.
4. Liên kết kế hoạch migration, phép thử và các sơ đồ đang phản ánh quyết định mới.
5. Giữ ADR-007 để người đọc hiểu lựa chọn cũ đã hợp lý ra sao ở thời điểm đó.

Có thể sửa lỗi chính tả hoặc bổ sung liên kết bằng chứng cho ADR cũ mà không đổi bản chất quyết định; nên dùng lịch sử phiên bản để minh bạch. Với thay đổi **ý nghĩa quyết định**, ADR mới thường rõ ràng hơn.

### ADR phản ánh quyết định; cấu hình phản ánh hiện trạng

Hai nguồn thông tin không đồng nghĩa:

- ADR nói **điều đã được chấp nhận và vì sao**.
- IaC, cấu hình và sơ đồ triển khai đã đối soát nói **điều thực sự đang chạy**.

Ví dụ ADR ghi dùng multi-AZ nhưng cấu hình đang có một instance trong một zone. Điều này là **sai lệch phải xử lý**, không phải bằng chứng kiến trúc đã hoàn thành. Nên có bước đối chiếu ADR với IaC, service inventory, SLO và kết quả thử nghiệm khi review.

## 8. So sánh phương án mà không giả tạo độ chính xác

Khi phải chọn giữa các kiến trúc cloud, một bảng đánh đổi rõ ràng hữu ích hơn nhận xét “phương án A tốt hơn” thiếu căn cứ.

Ví dụ chọn nơi chạy hai API Java và một worker cho đội nhỏ:

| Tiêu chí | VM tự quản | Managed container platform | Kubernetes tự quản / quản trị sâu |
| --- | --- | --- | --- |
| Tốc độ ra mắt | Phụ thuộc khả năng tự động hóa VM và quy trình patching | Thường nhanh nếu runtime được hỗ trợ | Cần cấu hình cluster, networking, bảo mật và vận hành |
| Khả năng kiểm soát | Cao ở cấp OS/runtime | Ít kiểm soát hạ tầng thấp hơn | Cao về workload scheduling và hệ sinh thái |
| Công vận hành | Đội chịu trách nhiệm OS, scaling và nhiều phần HA | Nhiều trách nhiệm hạ tầng do nền tảng đảm nhiệm | Cần năng lực cluster, networking, upgrades, observability |
| Tính linh hoạt | Chạy được workload đặc thù khi kiểm soát OS | Phù hợp workload stateless và nhiều worker | Hữu ích cho nhiều workload phức tạp/đội ngũ lớn |
| Phụ thuộc nền tảng | Image/VM, network, IAM, scripts | API triển khai và dịch vụ managed | Vẫn phụ thuộc cloud, cluster, add-on và storage |
| Chi phí | Compute + quản trị + dự phòng | Compute + dịch vụ + mức dùng + quản trị ứng dụng | Node/control plane/add-ons + nhân sự vận hành |

Không thể từ bảng định tính này kết luận chọn một phương án cho mọi tổ chức. Nếu thiếu thử tải, ngân sách hoặc kinh nghiệm đội ngũ, ADR phải đánh dấu **chưa đủ bằng chứng** và nêu phép thử cần làm.

### Khi nào nên chấm điểm có trọng số?

Một bảng điểm chỉ hữu ích khi có **tiêu chí đo được hoặc cách chấm đã thống nhất trước**. Ví dụ nhóm xác nhận vận hành đơn giản và giao hàng trong tám tuần quan trọng hơn khả năng kiểm soát hạ tầng thấp. Có thể đặt trọng số tương đối theo quyết định, nhưng phải:

- Công khai lý do trọng số, nguồn dữ liệu và phương pháp chấm.
- Không dùng điểm để thay thế kiểm tra **yêu cầu bắt buộc** như tuân thủ, bảo vệ dữ liệu hoặc giới hạn RTO.
- Xem kết quả chênh lệch nhỏ là tín hiệu cần kiểm chứng thêm, không phải sự thật chắc chắn.
- Thử độ nhạy: nếu thay một giả định, phương án được chọn có đổi không?

Ví dụ hai phương án hơn kém nhau vài điểm dựa trên chi phí ước lượng chưa có đơn giá thực tế thì kết luận có độ tin cậy thấp. Trong ADR, ghi rõ độ không chắc chắn sẽ có giá trị hơn tạo ra một con số “chính xác” không thể giải thích.

## 9. Viết hệ quả: phần thường bị thiếu nhất của ADR

Nhiều bản ADR ghi bối cảnh khá tốt rồi dừng ở “chọn A vì phù hợp”. **Hệ quả (consequences)** giúp đội ngũ biết chi phí và trách nhiệm phải chấp nhận sau khi lựa chọn. Đây là phần cần viết cả hệ quả **tốt**, **bất lợi**, **rủi ro còn lại** và **các việc phải làm để quyết định thành công**.

Hãy xem các câu hỏi sau khi viết hệ quả cho quyết định cloud:

| Khía cạnh Well-Architected | Hệ quả cần ghi |
| --- | --- |
| **Operational Excellence** | Ai vận hành, deploy, rollback, patch, theo dõi và xử lý sự cố? Có runbook và pipeline không? |
| **Security** | Ranh giới tin cậy, danh tính, IAM, dữ liệu nhạy cảm, encryption, audit và điểm cần threat model? |
| **Reliability** | Điểm lỗi còn lại, HA, backup, DR, RTO/RPO, retry và kịch bản failover phải thử? |
| **Performance Efficiency** | Giới hạn tải, p95/p99, quota, độ trễ mạng, bottleneck có thể xuất hiện ở đâu? |
| **Cost Optimization** | Chi phí cơ sở, theo tải, dữ liệu, egress, backup, log và công sức vận hành? |
| **Sustainability** | Sử dụng tài nguyên theo nhu cầu, tránh nhân bản thừa và retention không cần thiết? |

Ví dụ quyết định “đưa thông báo qua queue” có nhiều hệ quả:

**Tích cực:** request đặt lịch không phải đợi nhà cung cấp email; queue hấp thụ lưu lượng đột biến và cô lập lỗi downstream.

**Bất lợi:** người dùng có thể nhận thông báo trễ, cần theo dõi queue age, retry, dead-letter queue và thời gian giữ.

**Rủi ro dữ liệu:** thông điệp có thể đến lặp hoặc đến không theo thứ tự tùy dịch vụ; consumer phải idempotent, việc publish sau transaction cần có chiến lược như transactional outbox nếu yêu cầu không bỏ sót sự kiện.

**Công việc tiếp theo:** đo độ trễ gửi, thử ngắt dịch vụ email, giới hạn retry và thông báo khi hàng đợi bị nghẽn.

Đây là hệ quả có thể triển khai và kiểm chứng, hơn nhiều so với câu “queue tăng hiệu năng”.

### Ghi rủi ro chấp nhận có chủ sở hữu

Không phải rủi ro nào cũng xử lý ngay được. Có thể chấp nhận tạm thời triển khai một region nếu:

- Business owner đã chấp thuận tác động khi mất toàn region.
- Mục tiêu RTO/RPO và phụ thuộc được ghi rõ.
- Có backup, restore plan, thời điểm đánh giá lại hoặc điều kiện nâng cấp.
- Rủi ro được lưu trong danh sách theo dõi cùng chủ sở hữu.

Nếu quyết định không đạt yêu cầu bắt buộc, không được dùng câu “đã chấp nhận rủi ro” để hợp thức hóa việc vi phạm. Cần điều chỉnh phạm vi, yêu cầu hoặc thiết kế qua quy trình có thẩm quyền.

## 10. Gắn ADR với sơ đồ, số đo và triển khai

ADR cần liên kết với bằng chứng. Một sơ đồ Mermaid minh họa ứng dụng đặt lịch:

~~~mermaid
flowchart TD
    USER["Khách hàng"] --> API["Booking API<br/>Container instances"]
    API --> DB[("Managed relational DB<br/>Transaction / constraint")]
    API --> OUTBOX["Outbox events"]
    OUTBOX --> RELAY["Event relay"]
    RELAY --> Q["Managed queue"]
    Q --> WORKER["Notification worker"]
    WORKER --> MAIL["Email/SMS provider"]
    API --> OBS["Logs, metrics, traces"]
    WORKER --> OBS
~~~

Sơ đồ trả lời “luồng chạy qua đâu”, nhưng chưa đủ để biết:

- Vì sao API chạy container thay vì VM hoặc function?
- Vì sao database quan hệ là nguồn dữ liệu chuẩn?
- Vì sao dùng outbox, queue và worker thay vì gọi email trực tiếp?
- Vì sao chọn một region, nhiều zone và mức sao lưu hiện tại?

Mỗi câu hỏi quan trọng có thể dẫn đến một ADR riêng. Ví dụ:

| Quyết định | ADR tham khảo | Chứng cứ cần liên kết |
| --- | --- | --- |
| Database transaction cho đặt lịch | ADR-007 | Schema/constraint, concurrency test, restore test |
| Thông báo bất đồng bộ | ADR-008 | Sequence flow, retry/idempotency test, queue metrics |
| Compute cho API/worker | ADR-009 | Load test, capacity plan, cost estimate, rollback |
| Phạm vi HA và DR | ADR-010 | Sơ đồ region/zone, RTO/RPO, failover/restore drill |
| Phân quyền dịch vụ | ADR-011 | Data flow, IAM matrix, threat model, audit evidence |

Các ID này là **ví dụ cách liên kết**, không khẳng định các tài liệu tương ứng đã tồn tại trong repository.

### “Decision traceability” trong quy trình phát triển

Một đường truy vết rõ ràng có thể là:

~~~text
Nhu cầu: không đặt trùng khung giờ
      ↓
ADR-007: dùng transaction + constraint phù hợp
      ↓
Thiết kế: schema, quy tắc idempotency, API booking
      ↓
Thực thi: migration / IaC / cấu hình bảo mật
      ↓
Kiểm chứng: concurrency test + load test + restore test
      ↓
Vận hành: metric, alert, runbook, review thực tế
~~~

Khi một phép thử thất bại hoặc yêu cầu thay đổi, đường truy vết giúp xác định **quyết định nào cần điều chỉnh**. Nếu latency vượt SLO, cần điều tra query, khóa và connection pool trước khi kết luận lựa chọn database sai. Nếu mô hình đặt lịch chuyển từ khung cố định sang khoảng thời gian linh hoạt, cần xem lại thiết kế constraint và ADR có liên quan.

## 11. Những lỗi thường gặp và cách chỉnh

### Lỗi 1 — Chỉ ghi lựa chọn, không ghi lý do

**Chưa tốt:** “Dùng Kubernetes.”

**Cải thiện:** Nêu vì sao các khả năng điều phối, chính sách vận hành hoặc yêu cầu mở rộng cần thiết; phương án managed container nào đã được so sánh; đội ngũ có đủ năng lực chịu trách nhiệm cluster hay chưa.

### Lỗi 2 — Trình bày lựa chọn còn lại như phương án rơm

**Chưa tốt:** “VM lỗi thời, serverless rất chậm, nên phải dùng Kubernetes.”

**Cải thiện:** So sánh dựa trên workload, runtime, đội ngũ, độ trễ, quota, chi phí và năng lực hỗ trợ. Thừa nhận mỗi phương án có bối cảnh phù hợp.

### Lỗi 3 — Chỉ ghi hệ quả tích cực

**Chưa tốt:** “Managed database bảo đảm HA, không cần DBA.”

**Cải thiện:** Ghi những trách nhiệm vẫn thuộc đội dự án: schema, quyền, backup/restore, connection pool, chi phí, giám sát, thử failover và xử lý sự cố ứng dụng.

### Lỗi 4 — Dùng tính năng dịch vụ thay cho bằng chứng

**Chưa tốt:** “Có tính năng backup nên RPO chắc chắn đạt 15 phút.”

**Cải thiện:** Nêu cấu hình backup/PITR cụ thể, phép thử khôi phục, số đo dữ liệu mất và thời gian đạt trạng thái phục vụ; nếu chưa đo, đánh dấu là giả định.

### Lỗi 5 — Một ADR cố quyết định toàn bộ kiến trúc

**Chưa tốt:** Tài liệu hàng chục trang chọn cả network, compute, database, observability, DR và CI/CD.

**Cải thiện:** Tách các quyết định có thể thay đổi độc lập; liên kết bằng bản thiết kế hoặc index.

### Lỗi 6 — Không ghi những điều chưa quyết định

**Chưa tốt:** “Chọn PostgreSQL”, nhưng người đọc tưởng rằng phiên bản, topology, data residency, phương án restore đều đã chốt.

**Cải thiện:** Nêu phạm vi và các quyết định phụ thuộc cần bổ sung. Điều này ngăn các giả định được xem nhầm thành sự thật.

### Lỗi 7 — Sửa ADR sau khi hệ thống thay đổi mà không lưu lịch sử

**Chưa tốt:** Đổi tài liệu cũ từ single-region thành multi-region mà không ghi nguyên nhân.

**Cải thiện:** Tạo ADR thay thế; liên kết rõ quyết định cũ và kết quả kiểm chứng mới.

### Lỗi 8 — Viết ADR quá muộn hoặc chỉ để hoàn thành thủ tục

**Chưa tốt:** Tất cả tài nguyên đã triển khai; ADR được viết lại từ cấu hình mà không còn biết các lựa chọn từng xem xét.

**Cải thiện:** Viết khi chuẩn bị quyết định, trao đổi với người chịu trách nhiệm và cập nhật qua review; với kiến trúc kế thừa, ghi rõ “quyết định được tái dựng từ hiện trạng” và nguồn bằng chứng còn thiếu.

## 12. Thực hành: viết ADR cho mô hình triển khai ứng dụng cloud

### Đề bài

Một đội xây nền tảng đặt lịch dịch vụ với backend Java, API đọc lịch trống, API tạo lịch và worker gửi thông báo. Nhóm có năm kỹ sư, một người kiêm nhiệm vận hành; dự kiến ra mắt trong hai tháng. Tải lúc đỉnh **200 yêu cầu/giây**, p95 API đọc mục tiêu **dưới 300 ms** và SLO **99,9% giao dịch hợp lệ thành công trong 30 ngày**. Thông số này là **giả định để luyện tập**, chưa được chứng minh qua thử tải.

Bạn cần quyết định **mô hình compute cho API và worker**. Ba phương án sơ bộ:

- **A. VM:** tự quản các máy ảo, tạo image và script deploy, cấu hình cân bằng tải và autoscaling.
- **B. Managed container platform:** chạy các container stateless, dùng dịch vụ điều phối được quản lý và pipeline triển khai.
- **C. Kubernetes:** tự xây các thành phần quản trị cần thiết hoặc dùng Kubernetes được quản lý nhưng đội vẫn chịu trách nhiệm cấu hình workload, add-on và nâng cấp theo mô hình được chọn.

Giả định database và queue đã được quyết định ở ADR khác. Trong bài này chỉ tập trung quyết định **compute**.

### Yêu cầu đầu ra

1. **Đặt tên ADR:** ID, tiêu đề diễn đạt quyết định, trạng thái Proposed, ngày, người đề xuất và người có quyền chấp nhận.
2. **Ghi bối cảnh:** luồng API/worker, tải, p95, SLO, nhân lực, thời hạn ra mắt, mức tự động hóa và các giả định chưa xác minh.
3. **Xác định tiêu chí:** ít nhất reliability, security, performance, scale, cost, operations; phân biệt yêu cầu bắt buộc và tiêu chí có thể đánh đổi.
4. **So sánh ba phương án:** nêu một lợi ích và một bất lợi có căn cứ cho mỗi phương án, không khẳng định công nghệ nào luôn tốt hơn.
5. **Viết quyết định đề xuất:** chọn một phương án, phạm vi production/nonproduction và lý do; nêu điều kiện làm phương án được chọn phù hợp.
6. **Ghi hệ quả:** ít nhất hai hệ quả tích cực, ba hệ quả bất lợi hoặc rủi ro và công việc theo sau.
7. **Chỉ ra phép thử:** triển khai một lát cắt API + worker, thử tải 200 RPS và cao điểm giả định, rolling update, lỗi instance/zone, retry và khả năng rollback.
8. **Đưa ra trigger review:** ví dụ khi tải tăng bốn lần, sản phẩm cần workload đặc thù, chi phí vượt ngưỡng hoặc đội ngũ hình thành năng lực nền tảng mới.

### Ví dụ một phần lời giải

**Quyết định đề xuất:** chọn managed container platform cho phiên bản đầu, vì đội nhỏ, thời hạn ra mắt ngắn và API/worker dự kiến đóng gói được thành container. Chạy nhiều bản sao API qua các miền lỗi phù hợp, triển khai worker theo giới hạn đồng thời và hàng đợi. Chỉ chấp nhận triển khai production sau khi thử tải, kiểm tra rollback và chứng minh các mục tiêu chất lượng trong phạm vi được duyệt.

**Hệ quả tích cực:** giảm việc quản trị OS và cluster so với phương án tự quản; sử dụng cùng cơ chế đóng gói, phát hành và quan sát cho API/worker.

**Hệ quả bất lợi:** phụ thuộc quota, cơ chế autoscale, giới hạn tài nguyên, vùng hỗ trợ và cách tính phí của nền tảng; chưa có bằng chứng p95 và SLO; cần kiểm tra cold start hoặc thời gian scale-out nếu nền tảng có đặc tính này; ứng dụng phải được thiết kế stateless và quản lý kết nối database hợp lý.

**Điều kiện xem lại:** tỷ lệ lỗi/p95 không đạt dù đã tối ưu đúng phạm vi, nhu cầu cấu hình runtime đặc thù phát sinh, hoặc TCO dài hạn thay đổi có căn cứ.

Đây là **một phương án minh họa**. Người học có thể chọn VM hoặc Kubernetes nếu chứng minh bối cảnh và đánh đổi khác đi. Tiêu chí đánh giá là **lý do, bằng chứng, hệ quả và khả năng kiểm chứng**, không phải trùng tên công nghệ với ví dụ.

### Rubric tự đánh giá

| Tiêu chí | Chưa đạt | Đạt | Tốt |
| --- | --- | --- | --- |
| **Bối cảnh** | Thiếu vấn đề, ràng buộc và tải | Có yêu cầu, giới hạn và giả định | Có nguồn, độ tin cậy và ảnh hưởng của giả định |
| **Phương án** | Chỉ có một lựa chọn | Có lựa chọn thực tế và mặt tốt/xấu | Có đánh đổi nhất quán theo tiêu chí và phương án hiện trạng |
| **Quyết định** | Mơ hồ, không rõ phạm vi | Khẳng định rõ lựa chọn, phạm vi, điều kiện | Có lý do ưu tiên, người chấp nhận và phần chưa quyết |
| **Hệ quả** | Chỉ ghi lợi ích | Ghi lợi ích, chi phí, rủi ro và việc tiếp theo | Gắn chủ sở hữu, mức ưu tiên và biện pháp kiểm soát |
| **Kiểm chứng** | Không có số đo | Có phép thử và ngưỡng thành công | Có quy trình đo, dữ liệu thử và trigger review |
| **Truy vết** | Không liên kết tài liệu | Có sơ đồ và ticket liên quan | Liên kết bằng chứng, triển khai, SLO và ADR khác |

## 13. Checklist trước khi chấp nhận ADR

- [ ] Tiêu đề diễn đạt **một quyết định** rõ ràng, không chỉ là tên công nghệ.
- [ ] Bối cảnh mô tả vấn đề, hiện trạng và nhu cầu nghiệp vụ thay vì bắt đầu từ kết luận.
- [ ] Yêu cầu đã xác nhận, giả định và ràng buộc được phân biệt.
- [ ] NFR quan trọng có số đo/ngưỡng hoặc kế hoạch đo; RTO/RPO không bị đồng nhất với tính năng nhà cung cấp.
- [ ] Các phương án là lựa chọn khả thi và được so sánh bằng tiêu chí có liên quan.
- [ ] Phương án được chọn có phạm vi, điều kiện và lý do đủ rõ để một nhóm khác thực hiện.
- [ ] Hệ quả ghi cả lợi ích, chi phí, rủi ro còn lại và trách nhiệm vận hành/bảo mật.
- [ ] Công việc theo sau có người phụ trách, phép thử, tiêu chí nghiệm thu và liên kết quản lý.
- [ ] Đã xem tác động theo các khía cạnh Well-Architected liên quan.
- [ ] Có link đến sơ đồ, kết quả PoC, benchmark, threat model, chi phí hoặc nguồn yêu cầu nếu có.
- [ ] Trạng thái và người chấp nhận được ghi rõ; Accepted không bị hiểu nhầm là đã triển khai.
- [ ] Có sự kiện kích hoạt review và cách thay thế ADR mà vẫn giữ lịch sử.

ADR tốt không cần dài hay phức tạp. Giá trị của nó nằm ở khả năng trả lời rõ **bối cảnh nào dẫn đến quyết định**, **vì sao lựa chọn này tốt hơn các phương án khác trong bối cảnh đó**, **những hệ quả nào được chấp nhận**, và **bằng chứng nào cho phép kiểm tra lại**. Khi sơ đồ kiến trúc trả lời “hệ thống được xây như thế nào”, ADR giữ lại phần quan trọng để kiến trúc phát triển có chủ đích: **“vì sao chúng ta đã chọn cách này?”**
