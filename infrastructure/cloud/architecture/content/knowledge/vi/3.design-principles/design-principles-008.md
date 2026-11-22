# Đánh giá ràng buộc nhà cung cấp và mức độ di chuyển thực sự cần thiết

Khi thiết kế kiến trúc đám mây, câu hỏi “có bị khóa vào một nhà cung cấp không?” thường được đặt quá sớm, trước cả câu hỏi “vì sao hệ thống cần chuyển nhà cung cấp?”. Vì lo ngại *vendor lock-in*, một nhóm có thể từ bỏ các dịch vụ managed phù hợp, tự quản nhiều thành phần và tăng chi phí vận hành, dù doanh nghiệp chưa có nhu cầu chuyển nền tảng. Ngược lại, bỏ qua hoàn toàn khả năng di chuyển có thể khiến một thay đổi hợp đồng, yêu cầu pháp lý hoặc sự cố chiến lược trở nên rất đắt đỏ.

Nguyên lý thực hành là **đánh giá ràng buộc theo tác động nghiệp vụ, xác suất và thời hạn cần thoát khỏi phụ thuộc**, rồi đầu tư mức di chuyển (*portability*) đủ cho những kịch bản đáng tin cậy. Mục tiêu không phải triệt tiêu mọi phụ thuộc. Một lựa chọn phụ thuộc vào dịch vụ cloud cụ thể có thể hợp lý nếu nó giảm thời gian ra mắt, cải thiện độ tin cậy hoặc giảm công vận hành tương xứng với chi phí chuyển đổi trong tương lai.

Bài học này thuộc mạch **Nguyên lý thiết kế kiến trúc đám mây**: từ yêu cầu nghiệp vụ đến quyết định mạng, compute, dữ liệu và triển khai, xét đồng thời độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành theo tư duy Well-Architected.

Sau bài học, bạn có thể:

- Phân biệt **phụ thuộc nhà cung cấp**, **chi phí chuyển đổi** và **khả năng di chuyển đã được kiểm chứng**.
- Nhận diện ràng buộc ở các lớp ứng dụng, dữ liệu, hạ tầng, bảo mật, công cụ vận hành và hợp đồng.
- Xác định mức di chuyển cần thiết bằng một kịch bản chuyển đổi cụ thể và thời hạn có thể chấp nhận.
- So sánh lợi ích dịch vụ cloud chuyên biệt với chi phí phát triển, vận hành và khả năng chuyển đổi.
- Đề xuất các ranh giới kiến trúc, thử nghiệm di chuyển và kế hoạch thoát phụ thuộc có thể nghiệm thu.

## 1. Ràng buộc nhà cung cấp là gì?

**Vendor lock-in** là tình huống việc thay đổi nhà cung cấp, dịch vụ hoặc mô hình vận hành trở nên khó khăn hay tốn kém vì hệ thống đã phụ thuộc vào công nghệ, dữ liệu, API, quy trình, hợp đồng hoặc kỹ năng gắn với lựa chọn hiện tại.

Ba khái niệm gần nhau nhưng khác nhau:

| Khái niệm | Câu hỏi thực tế | Ví dụ |
| --- | --- | --- |
| **Dependency — phụ thuộc** | Muốn hệ thống hoạt động, ta đang cần thành phần nào? | Ứng dụng gọi API lưu trữ đối tượng của cloud A. |
| **Switching cost — chi phí chuyển đổi** | Thay thành phần đó tốn bao nhiêu công, tiền, thời gian và rủi ro? | Phải đổi SDK, di chuyển tệp, đổi IAM và kiểm thử lại. |
| **Portability — khả năng di chuyển** | Có thể chạy hoặc chuyển dữ liệu sang môi trường mục tiêu trong điều kiện nào? | Đã triển khai thử ứng dụng ở cloud B và chứng minh dữ liệu khớp. |

Một ứng dụng dùng PostgreSQL trên cloud A vẫn có phụ thuộc vào cloud A: cấu hình mạng, IAM, backup, failover, monitoring và công cụ triển khai có thể riêng. Nhưng mức phụ thuộc của **mô hình dữ liệu** có thể thấp hơn nếu chỉ sử dụng tính năng PostgreSQL phổ biến và kiểm chứng việc xuất/nhập dữ liệu. Ngược lại, ứng dụng dùng API phân tích dữ liệu độc quyền có thể phụ thuộc sâu vào cú pháp truy vấn, cấu trúc sự kiện và cách tính phí.

**Không có kiến trúc “không phụ thuộc” tuyệt đối.** Tự dựng Kubernetes, Kafka hoặc database mã nguồn mở cũng tạo ra phụ thuộc vào phiên bản, công cụ, đội ngũ có kỹ năng và phương pháp vận hành. Câu hỏi hữu ích là *phụ thuộc nào mang lại giá trị, phụ thuộc nào gây rủi ro không chấp nhận được và chúng ta có bằng chứng gì?*

### Các dạng phụ thuộc thường bị bỏ sót

1. **API và SDK:** mã ứng dụng gọi trực tiếp chức năng độc quyền; event schema, câu lệnh truy vấn, workflow hoặc hình thức xác thực gắn với nhà cung cấp.
2. **Dữ liệu:** dữ liệu lớn, định dạng độc quyền, extension database, tính năng transaction, các pipeline phân tích và đường truyền ra ngoài tốn kém.
3. **Hạ tầng và mạng:** virtual network, subnet, load balancer, NAT, private endpoint, service discovery và cách ánh xạ zone/region.
4. **Định danh và bảo mật:** IAM role, workload identity, KMS, secret manager, audit, chính sách truy cập và khóa mã hóa.
5. **Vận hành:** CI/CD, logging, tracing, cảnh báo, backup, disaster recovery, runbook và kiến thức xử lý sự cố.
6. **Thương mại và tổ chức:** hợp đồng cam kết sử dụng, ưu đãi giá, giấy phép, hỗ trợ, kỹ năng nhân sự và chi phí thay đổi quy trình.

Nhà cung cấp có thể hỗ trợ xuất dữ liệu nhưng **không hỗ trợ một phương án tái tạo đầy đủ hành vi ứng dụng** ở nền tảng khác. Vì thế, một lời khẳng định như “dữ liệu luôn thuộc về chúng ta” chưa đủ để kết luận có thể di chuyển an toàn.

## 2. Bắt đầu bằng kịch bản thoát phụ thuộc, không bắt đầu bằng công nghệ

Trước khi đầu tư tính di chuyển, hãy ghi rõ **vì sao**, **khi nào**, **cái gì** cần chuyển và **mức gián đoạn** nghiệp vụ chấp nhận được.

### Những kịch bản có thể dẫn đến di chuyển

| Kịch bản kích hoạt | Điều cần xác minh | Hướng chuẩn bị tương ứng |
| --- | --- | --- |
| Điều khoản hợp đồng hoặc chi phí thay đổi đáng kể | Chi phí chênh lệch sau thuế, egress, vận hành, thời hạn cam kết | Theo dõi chi phí thay thế và các mốc gia hạn; có ước lượng migration |
| Yêu cầu lưu trú dữ liệu hoặc tuân thủ mới | Vùng được phép lưu dữ liệu, xử lý, backup và truy cập hỗ trợ | Data inventory, kiểm tra khả năng xuất/nhập và vùng triển khai khả dụng |
| Nhà cung cấp dừng dịch vụ hoặc thay đổi API | Ngày hết hỗ trợ, API thay thế, giới hạn tương thích | Cô lập tích hợp, kế hoạch nâng cấp hoặc thay thế dịch vụ |
| Mua bán, sáp nhập hoặc thống nhất nền tảng | Thời hạn chuyển, hệ thống đích, phân quyền, phụ thuộc liên tổ chức | Bản đồ dịch vụ, dữ liệu, hợp đồng và thử nghiệm trên đích |
| Khả năng cung cấp dịch vụ không còn đáp ứng mục tiêu | Vấn đề thuộc sản phẩm, kiến trúc sử dụng hay thực tế nhà cung cấp? | Đo SLO và nguyên nhân; thử khả năng thay thế thành phần liên quan |
| Yêu cầu khách hàng triển khai trong môi trường riêng | Khách cần cấu hình riêng, dữ liệu riêng hay toàn bộ workload chạy ở hạ tầng của họ? | Xác định ranh giới triển khai và hợp đồng vận hành cụ thể |

Một phương án thoát cần có **đích đến khả thi**. “Có thể chuyển sang cloud bất kỳ” là một yêu cầu khó kiểm chứng. “Có thể chuyển API đặt lịch và dữ liệu khách hàng từ cloud A sang cloud B trong tối đa 90 ngày làm việc kỹ thuật, với một cửa sổ ngừng ghi đã thỏa thuận” là giả định có thể thiết kế và thử.

### Bộ câu hỏi xác định nhu cầu thật

- **Trigger:** Điều kiện nào khiến công ty buộc phải chuyển? Ai có quyền ra quyết định?
- **Phạm vi:** Toàn bộ ứng dụng, chỉ database, một nhóm khách hàng hay vùng triển khai cụ thể?
- **Thời hạn:** Cần khôi phục vài giờ sau thảm họa hay cần di chuyển có kế hoạch trong vài tháng?
- **Dữ liệu:** Khối lượng, tốc độ phát sinh, yêu cầu nhất quán, giới hạn residency, thời gian lưu giữ?
- **Ngừng dịch vụ:** Có được ngừng ghi hoặc triển khai theo từng nhóm người dùng? Tối đa bao lâu?
- **Ngân sách và nhân lực:** Có đội ngũ vận hành đồng thời hai môi trường hay không?
- **Kiểm chứng:** Bằng chứng nào chứng minh kịch bản thành công: restore test, cutover rehearsal, p95, error rate, đối soát dữ liệu?

**Phân biệt hai mục tiêu:** khôi phục dịch vụ sau khi một region gặp sự cố (**disaster recovery, DR**) và thay một nhà cung cấp bằng nhà cung cấp khác (**provider exit/migration**) là hai bài toán khác nhau. Một hệ thống multi-zone hoặc multi-region trên cùng cloud có thể đáp ứng RTO/RPO của sự cố hạ tầng mà không tạo ra khả năng di chuyển xuyên nhà cung cấp. Ngược lại, dữ liệu có thể xuất sang cloud B trong hai tuần nhưng không thể giúp dịch vụ phục hồi trong 30 phút.

## 3. Chọn mức di chuyển phù hợp thay vì mặc định “cloud agnostic”

Khả năng di chuyển có nhiều mức và nhiều lớp. Có thể chỉ cần **xuất dữ liệu và thay dịch vụ theo kế hoạch**, không nhất thiết phải chạy cùng ứng dụng ở hai cloud mọi lúc.

| Mức | Điều có thể làm | Thời gian và chi phí tương đối | Trường hợp phù hợp |
| --- | --- | --- | --- |
| **M0 — Có bản đồ phụ thuộc** | Hiểu hệ thống dùng gì, lưu dữ liệu ở đâu, biết điều kiện thoát | Thấp; chưa chứng minh di chuyển được | Sản phẩm mới, chưa có yêu cầu chuyển cụ thể |
| **M1 — Dữ liệu có thể xuất và phục hồi** | Trích xuất theo định dạng đã hiểu, chuyển và kiểm tra dữ liệu ở đích | Vừa; cần thử nghiệm restore và đối soát | Cần bảo vệ quyền kiểm soát dữ liệu, kế hoạch chuyển dài hạn |
| **M2 — Có kế hoạch thay thế theo lớp** | Thay database/queue/storage hoặc API qua adapter và kịch bản migration | Vừa đến cao; cần phân tách ranh giới, test hợp đồng | Có rủi ro thực tế ở một vài thành phần chủ chốt |
| **M3 — Triển khai lại được trên nền tảng thứ hai** | Dựng môi trường, triển khai ứng dụng và vận hành các chức năng chính ở đích | Cao; vận hành, IAM, mạng, monitoring đều cần chuyển | Có nghĩa vụ hỗ trợ môi trường khác hoặc kế hoạch chuyển rõ |
| **M4 — Vận hành chủ động trên nhiều nhà cung cấp** | Phục vụ tải/khôi phục qua nhiều cloud với dữ liệu và vận hành đã đồng bộ | Rất cao; phát sinh bài toán dữ liệu và phân tán | Chỉ khi lợi ích, nghĩa vụ hợp đồng hoặc thời gian khôi phục thực sự đòi hỏi |

Đây là **thang tham khảo để thảo luận**, không phải tiêu chuẩn chung hay chứng nhận trưởng thành. Một hệ thống có thể ở M2 đối với storage nhưng M0 đối với identity; không nên gộp thành một nhãn “portable”.

### Tính di chuyển phải được tách theo chiều

**Application portability:** mã ứng dụng có chạy trên runtime hoặc môi trường khác không?

**Data portability:** schema, dữ liệu, lịch sử sự kiện, khóa và metadata có trích xuất, biến đổi, nhập và xác thực được không?

**Infrastructure portability:** có thể dựng networking, compute, storage, IAM và cấu hình dịch vụ ở đích bằng quy trình lặp lại được không?

**Operational portability:** dashboard, log, alert, CI/CD, backup/restore, runbook, kiểm toán và đội ngũ có vận hành thành công ở đích không?

**Contractual portability:** điều khoản xuất dữ liệu, chấm dứt hợp đồng, quyền dùng phần mềm, giới hạn egress và cam kết hỗ trợ có cho phép thực hiện kế hoạch không?

Một container image chạy được ở môi trường B mới chứng minh **một phần tính tương thích runtime**; chưa chứng minh transaction database, kết nối mạng, hệ thống quyền, khả năng quan sát hay failover hoạt động đúng. Kubernetes và Terraform hỗ trợ tự động hóa và tính lặp lại, nhưng không tự làm cho các dịch vụ managed, IAM hay mạng trở nên giống nhau.

## 4. Lập bản đồ phụ thuộc và đánh giá rủi ro có trọng tâm

Đầu tiên, lập danh sách các thành phần nằm trên đường phục vụ hành trình nghiệp vụ quan trọng. Với mỗi phụ thuộc, ghi **nó được dùng để làm gì**, **mức chuyên biệt**, **dữ liệu bị ảnh hưởng**, **thời gian thay thế** và **hậu quả khi không thể thay thế**.

Ví dụ ứng dụng đặt lịch tư vấn trực tuyến gồm API, database lịch hẹn, hàng đợi gửi email và kho tệp:

| Thành phần | Dấu hiệu ràng buộc | Tác động nếu phải rời nhà cung cấp | Độ khó chuyển tương đối | Hành động hợp lý |
| --- | --- | --- | --- | --- |
| API nghiệp vụ chạy container | Container chuẩn, nhưng cấu hình ingress và identity riêng | Trung bình | Vừa | Tách cấu hình môi trường; thử build/deploy ở đích |
| Managed PostgreSQL | Dùng SQL/extension, backup và cơ chế failover của nhà cung cấp | Cao vì chứa dữ liệu đặt lịch | Vừa đến cao | Kiểm kê extension, thử logical export/restore, đối soát dữ liệu |
| Managed queue | SDK, metadata, retry, dead-letter policy riêng | Trung bình đến cao | Vừa | Cô lập publish/consume; thiết kế idempotency |
| Object storage | SDK, IAM và URL được ký bởi nhà cung cấp | Trung bình | Vừa; phụ thuộc dung lượng | Tách API lưu tệp; thử di chuyển đối tượng và metadata |
| IAM/KMS | Role, chính sách và khóa mật mã phụ thuộc nền tảng | Rất cao nếu làm mất khả năng đọc dữ liệu | Cao | Lập bản đồ quyền và phương án giải mã/chuyển mã hợp lệ |
| Logging/monitoring | Query, metric, alert và retention riêng | Cao trong vận hành sau cutover | Vừa đến cao | Chuẩn hóa tên tín hiệu; có dashboard và cảnh báo ở đích |
| Hợp đồng và mạng | Cam kết chi tiêu, giá xuất dữ liệu, IP allowlist | Tùy điều khoản và lưu lượng | Vừa đến cao | Kiểm tra mốc cam kết, ước tính egress, cập nhật phụ thuộc đối tác |

Mỗi đội có thể sử dụng thang định tính **thấp / vừa / cao** để xếp hàng ưu tiên; nếu cần chấm điểm, phải nêu rõ cách xác định tác động, khả năng xảy ra và độ khó chuyển. Điểm số tự tạo chỉ hỗ trợ thảo luận, không thay thế bằng chứng hay sự đồng thuận của chủ nghiệp vụ.

Một cách đơn giản để chọn việc trước là hỏi:

1. **Nếu không đổi được thành phần này, điều gì xảy ra?** Gián đoạn doanh thu, mất dữ liệu, không tuân thủ hay chỉ chậm phát triển một tính năng?
2. **Kịch bản buộc phải đổi có thật sự xảy ra trong khoảng hoạch định không?** Có hợp đồng, quy định, yêu cầu khách hàng hoặc tín hiệu sản phẩm cụ thể?
3. **Thành phần mất bao lâu để thay và có thể thử trước với chi phí hợp lý không?**

Kết quả thường không phải “cần portable toàn bộ”. Có thể cần đầu tư **M1 cho dữ liệu khách hàng**, **M2 cho hàng đợi**, còn việc tái tạo toàn bộ môi trường production trên cloud thứ hai được hoãn đến khi xuất hiện yêu cầu rõ ràng.

## 5. Thiết kế ranh giới để có khả năng thay thế ở đúng vị trí

Một ranh giới kiến trúc tốt giúp **cách dùng dịch vụ trong nghiệp vụ** ít bị chi phối bởi SDK và API cụ thể. Tuy vậy, không phải mọi cloud API đều cần một abstraction tự xây.

### 5.1. Cô lập sự phụ thuộc ở các điểm giao tiếp hợp lý

Với ứng dụng đặt lịch, domain cần hai khả năng: lưu lịch hẹn và phát sự kiện thông báo. Domain không nhất thiết phải biết tên sản phẩm queue hay database. Có thể xác định interface cho các hành vi mà nghiệp vụ cần, đặt adapter phía hạ tầng để chuyển lời gọi.

~~~mermaid
flowchart TD
    UI[Web hoặc mobile client] --> API[HTTP API]
    API --> SVC[Booking domain service]
    SVC --> REPO[BookingRepository contract]
    SVC --> PUB[NotificationPublisher contract]
    REPO --> DBAD[Database adapter]
    PUB --> QAD[Queue adapter]
    DBAD --> DB[(Managed relational database)]
    QAD --> Q[(Managed message queue)]
    Q --> WORKER[Notification worker]
    WORKER --> MAIL[Email/SMS provider]
~~~

Ví dụ interface nghiệp vụ bằng Java:

~~~java
import java.time.Instant;
import java.util.UUID;

public interface BookingRepository {
    // Việc tránh đặt trùng phải được bảo đảm cả ở transaction/constraint dữ liệu.
    Booking createIfSlotAvailable(UUID customerId, UUID slotId);
}

public interface NotificationPublisher {
    // Định nghĩa semantics: idempotency, retry và xử lý lỗi.
    void bookingConfirmed(UUID bookingId, Instant occurredAt);
}
~~~

Đây là ví dụ ranh giới logic. Code trên **không tự bảo đảm tính nguyên tử** giữa ghi database và phát sự kiện. Nếu business transaction phải được ghi trước rồi mới công bố sự kiện chắc chắn, có thể dùng **transactional outbox** và worker phát sự kiện; sau đó vẫn cần consumer idempotent vì gửi lặp có thể xảy ra.

Giá trị của interface nằm ở việc giữ nghiệp vụ rõ ràng và cho phép đổi adapter; chi phí là số lớp code và test hợp đồng phải bảo trì. Nếu toàn bộ tính năng chỉ dùng một cloud và không có kịch bản chuyển khả tín, viết “adapter trừu tượng cho mọi thứ” có thể làm chậm phát triển và giấu mất lợi ích riêng của dịch vụ.

### 5.2. Ưu tiên tiêu chuẩn mở khi chúng đáp ứng yêu cầu

Ví dụ:

- Dùng HTTP, TLS, OpenAPI hoặc giao thức có tài liệu rõ cho giao tiếp hệ thống phù hợp; ghi lại những extension đặc thù.
- Khi chọn relational database, đánh giá mức tuân theo SQL, PostgreSQL/MySQL semantics, extension, stored procedure và khả năng xuất/nhập *thực tế*.
- Sử dụng định dạng dữ liệu phổ biến và có version/schema rõ ràng khi trao đổi hoặc xuất dữ liệu; lưu metadata cần thiết để tái tạo.
- Dùng chuẩn quan sát như OpenTelemetry khi phù hợp để dễ chuyển dữ liệu trace/metric, nhưng vẫn cần ánh xạ alert, query và công cụ đích.
- Đóng gói runtime bằng container khi hợp lý, tách cấu hình và secrets khỏi image.

**Dùng chuẩn không bảo đảm khả năng di chuyển bằng một nút bấm.** Các nhà cung cấp có thể khác nhau về phiên bản, giới hạn quota, mức tương thích, semantics giao dịch, độ trễ, cơ chế khóa, xác thực hoặc hoạt động khi lỗi. Kiểm tra chức năng bình thường thôi chưa đủ; cần thử ở tình huống tải và lỗi.

### 5.3. Dùng dịch vụ chuyên biệt khi lợi ích được chứng minh

Chọn một dịch vụ serverless database hoặc workflow độc quyền có thể giảm đáng kể công quản trị, tự động mở rộng và giúp sản phẩm ra mắt nhanh. Đó là lợi ích kinh doanh thực sự. Khi chấp nhận ràng buộc sâu hơn, hãy ghi rõ:

- Tính năng độc quyền nào đang tạo giá trị và giá trị đó được đo bằng gì?
- Nếu bỏ tính năng này, giải pháp thay thế yêu cầu bao nhiêu code, hạ tầng và nhân lực?
- Có cách xuất dữ liệu và loại bỏ phụ thuộc theo từng phần không?
- Quy trình thay thế dự kiến mất bao lâu; chi phí và gián đoạn được ai chấp nhận?
- Khi nào cần xem lại quyết định: thay đổi giá, quy định, tải, yêu cầu khách hàng hay vòng đời dịch vụ?

Điều cần tránh không phải là “dùng bất kỳ dịch vụ proprietary nào”, mà là **không biết mình đang đánh đổi điều gì**.

## 6. Khả năng di chuyển dữ liệu khó hơn việc chuyển mã nguồn

Trong nhiều workload, phần tốn thời gian nhất là chuyển **dữ liệu đúng, đủ, an toàn và có thể kiểm chứng**, đặc biệt khi hệ thống vẫn phát sinh giao dịch trong lúc di chuyển.

### 6.1. Làm rõ “xuất được dữ liệu” nghĩa là gì

Kiểm kê:

- **Dữ liệu gốc:** bảng giao dịch, đối tượng lưu trữ, tệp, event, nội dung do người dùng tạo.
- **Cấu trúc:** schema, index, constraint, extension, collation, timezone, kiểu số, độ chính xác thời gian.
- **Metadata:** phiên bản tệp, quyền sở hữu, tag, retention, timestamp, checksum, liên kết tham chiếu.
- **Trạng thái phát sinh:** queue chưa xử lý, session, cache, materialized view, search index; quyết định phần nào cần di chuyển và phần nào có thể tái tạo.
- **Bảo vệ dữ liệu:** khóa mã hóa, quyền truy cập, xóa theo chính sách, nơi lưu backup và nghĩa vụ chứng minh xóa.

Ví dụ chuyển PostgreSQL sang một PostgreSQL managed khác: cần kiểm tra version, extension, collation, logical replication, identity/sequence, triggers, users/permissions và giới hạn kết nối. Sự tương đồng tên sản phẩm không có nghĩa hai môi trường hoàn toàn tương thích.

Với object storage, cần đối chiếu **số đối tượng, kích thước, checksum, metadata, quyền truy cập và trạng thái phiên bản**, thay vì chỉ nhìn tổng dung lượng. URL được ký, bucket policy và API truy cập thường cần điều chỉnh ở ứng dụng.

### 6.2. Những mô hình di chuyển phổ biến

| Cách di chuyển | Phù hợp khi | Rủi ro trọng yếu |
| --- | --- | --- |
| **Offline export/import** | Có thể ngừng ghi trong cửa sổ chuyển đổi | Downtime, thời gian xuất/nhập và xác thực |
| **Snapshot + incremental / CDC** | Dữ liệu lớn, muốn giảm khoảng ngừng ghi | Lag, thứ tự sự kiện, lỗi schema, thay đổi phát sinh khi đồng bộ |
| **Phân đợt theo khách hàng hoặc miền** | Kiến trúc cho phép phân tách và định tuyến | Dữ liệu tham chiếu chéo, trạng thái phân tán |
| **Dual-write có kiểm soát** | Có cơ chế phát hiện/đối soát sai lệch được thiết kế riêng | Partial write, thứ tự khác nhau, duplicate, không nhất quán |

**Không mặc định dual-write an toàn.** Ghi đồng thời vào hai hệ thống độc lập không tạo thành một transaction xuyên hệ thống. Nếu không xử lý lỗi một phía, retry, thứ tự và đối soát, sai lệch dữ liệu sẽ khó phát hiện. Khi có thể, ưu tiên một nguồn ghi chuẩn trong từng giai đoạn với cơ chế đồng bộ và cutover rõ ràng.

### 6.3. Kế hoạch cutover phải có điều kiện dừng và quay lại

Một quy trình kiểm chứng điển hình:

1. Tạo đích có kiểm soát truy cập và chính sách dữ liệu phù hợp; xác nhận vùng lưu, quyền và khóa mã hóa.
2. Kiểm tra tương thích schema và cấu trúc; diễn tập chuyển một phần dữ liệu đã khử nhạy cảm hoặc dùng dữ liệu test thích hợp.
3. Chuyển bản dữ liệu đầu; đồng bộ thay đổi tiếp theo nếu chọn mô hình online.
4. Đối soát record count, checksum, tổng giá trị nghiệp vụ và tính toàn vẹn tham chiếu; kiểm tra dữ liệu nằm ngoài database như object và queue.
5. Kiểm tra latency, thông lượng, semantics giao dịch, retry và đường truy cập từ API ở đích.
6. Quyết định cửa sổ chặn ghi hoặc phương án chuyển luồng; đưa lag đồng bộ về ngưỡng được duyệt và đối soát lần cuối.
7. Chuyển traffic từng phần hoặc toàn bộ; theo dõi lỗi, tỷ lệ thành công, p95 và nhất quán dữ liệu.
8. Chỉ đóng môi trường cũ khi hết giai đoạn xác minh, retention và rollback đã được phê duyệt.

Điều kiện **go/no-go** cần định lượng từ trước: độ trễ đồng bộ cho phép, số bản ghi sai lệch, số giao dịch thất bại, cửa sổ downtime và ai có quyền dừng. Nếu sau cutover đã có ghi mới ở đích, rollback về nguồn cũ **không còn đơn giản là đổi DNS**; phải có kế hoạch đồng bộ ngược hoặc ngừng ghi và hợp nhất dữ liệu để tránh mất giao dịch.

## 7. Mạng, bảo mật và vận hành phải đi cùng kế hoạch chuyển

Di chuyển API và dữ liệu nhưng bỏ quên các lớp hỗ trợ sẽ tạo ra một hệ thống có thể chạy demo mà chưa thể vận hành production.

**Mạng:** vẽ lại luồng vào/ra, private endpoint, NAT, DNS, TLS termination, IP allowlist, kết nối với đối tác, firewall và đường truyền giữa region. Kiểm tra quota, giới hạn băng thông và egress. Nếu đồng bộ giữa hai cloud, đo latency và chi phí đường truyền thay vì giả định giống mạng nội bộ.

**Danh tính và phân quyền:** ánh xạ service identity, role, policy, secrets, trust boundary và quyền con người. Đánh giá tương đương về **hành vi được phép và bị từ chối**, không chỉ sao chép tên role. Kiểm tra audit trail để bảo đảm có bằng chứng sau chuyển.

**Mã hóa và khóa:** kiểm tra dữ liệu được mã hóa bằng khóa nào, khóa có thể sử dụng ở đích hay không, và có được phép giải mã rồi mã hóa lại trong một luồng an toàn không. Không giả định mọi cloud KMS cho phép xuất private key. Thiết kế trước quá trình chuyển mã hóa hoặc khôi phục bằng bản sao hợp lệ, dưới quyền kiểm soát và phân quyền phù hợp.

**Quan sát:** chuyển cả SLI/SLO, dashboard, cảnh báo, log retention, trace sampling và quy trình ứng cứu. Giữ correlation ID xuyên các luồng đồng bộ và bất đồng bộ nếu khả thi để điều tra lỗi khi chạy hai môi trường.

**Vận hành:** mô tả bootstrap, CI/CD, secret provisioning, backup, restore, scale, patching và rollback cho đích. Việc mang một bộ Terraform module sang cloud khác thường cần viết lại tài nguyên và chính sách. Hãy tổ chức IaC để **quản lý biến thể rõ ràng**, thay vì cố tạo một mô hình tài nguyên “chung nhất” đến mức không thể sử dụng đặc tính quan trọng của từng nền tảng.

**Tuân thủ:** xác nhận nơi xử lý dữ liệu, nơi lưu backup, log, người truy cập từ nước ngoài, quy trình xóa và cam kết với khách hàng. Một nhà cung cấp thứ hai không tự tạo ra tuân thủ nếu cấu hình và đường đi dữ liệu vẫn chưa đúng.

## 8. Đánh đổi giữa dịch vụ managed và tính di chuyển

Kiến trúc cần tối ưu **tổng giá trị và tổng chi phí sở hữu (TCO)** theo thời gian, không chỉ số lượng API riêng của nhà cung cấp.

| Tiêu chí | Dùng managed service chuyên biệt | Dùng công nghệ phổ biến / tự quản nhiều hơn |
| --- | --- | --- |
| Tốc độ ra mắt | Thường nhanh khi tính năng đáp ứng nhu cầu | Có thể tốn thời gian dựng và vận hành |
| Chăm sóc hạ tầng | Nhà cung cấp nhận một phần trách nhiệm theo loại dịch vụ | Đội ngũ chịu trách nhiệm lớn hơn về patch, backup, scale |
| Tính năng nâng cao | Có thể tối ưu và tích hợp sâu | Khả năng phụ thuộc triển khai, plug-in và năng lực đội |
| Chi phí chạy thường xuyên | Có thể tốt hoặc xấu tùy tải, quota, cách tính phí | Cũng có thể thấp hoặc cao; phải tính thời gian kỹ sư và on-call |
| Chi phí rời nền tảng | Có thể cao vì API, dữ liệu, hợp đồng và quy trình | Có thể thấp hơn ở một số lớp, nhưng vẫn phải chuyển mạng, IAM, dữ liệu, vận hành |
| Khả năng mở rộng | Phụ thuộc giới hạn và đặc tính dịch vụ | Phụ thuộc năng lực sizing, tuning và quản trị |

Không có cột nào luôn thắng. Ví dụ, một managed queue độc quyền có thể phù hợp với doanh nghiệp ít nhân lực SRE hơn việc tự vận hành một cụm message broker. Nếu queue là điểm cần chuyển do hợp đồng khách hàng, adapter và kiểm thử di chuyển có thể tạo đủ linh hoạt mà không cần tự quản toàn bộ hạ tầng.

### Mô hình chi phí ra quyết định

Chi phí của một phương án nên bao gồm:

~~~text
TCO theo kỳ = xây dựng ban đầu
            + chi phí cloud theo tải
            + chi phí vận hành, nhân sự, trực sự cố
            + kiểm thử, bảo mật và tuân thủ
            + chi phí chuyển đổi hoặc thoát phụ thuộc dự kiến
            + chi phí rủi ro/ngừng dịch vụ có cơ sở ước lượng
~~~

Chi phí chuyển nền tảng gồm cả kỹ sư, phát triển adapter, chuyển dữ liệu, egress, chạy song song, kiểm thử, làm lại IAM, quan sát, vận hành và rủi ro gián đoạn. Khi so sánh, phải cùng giả định về **tải, SLO, RTO/RPO, độ an toàn và thời gian hoạch định**.

**Ví dụ tính toán minh họa (USD, giả định, không phải giá thị trường):** Một công ty so sánh hai thiết kế cho 36 tháng:

- **Phương án A:** tận dụng managed service chuyên biệt với tổng vận hành 12.000 USD/tháng, không phát sinh đầu tư di chuyển trước.
- **Phương án B:** chọn khả năng chạy lại trên cloud thứ hai, chi phí vận hành 16.000 USD/tháng và công triển khai/kiểm thử ban đầu thêm 50.000 USD.
- Nếu phải rời nhà cung cấp trong 36 tháng, chi phí di chuyển ước tính A là 180.000 USD, B là 60.000 USD. Xác suất phải di chuyển trong kỳ được nhóm kinh doanh ước lượng sơ bộ là 25%.

Khi chỉ xét các khoản trên:

~~~text
Phí tăng thêm để chọn B trong 36 tháng
  = (16.000 - 12.000) × 36 + 50.000
  = 194.000 USD

Chi phí di chuyển kỳ vọng giảm nhờ B
  = (180.000 - 60.000) × 25%
  = 30.000 USD
~~~

Trong ví dụ này, **lợi ích giảm chi phí di chuyển kỳ vọng riêng lẻ chưa bù chi phí thêm của B**. Đây không phải kết luận rằng nên chọn A trong mọi trường hợp: còn phải đánh giá hậu quả không thể định giá tuyến tính như không tuân thủ, không đáp ứng hợp đồng, mất khách hàng chiến lược hoặc downtime kéo dài. Xác suất 25% chỉ là giả định để thấy cách suy nghĩ; không được trình bày như một dự báo có căn cứ nếu chưa có dữ liệu.

Đồng thời, **chi phí phòng tránh lock-in không cần đồng nghĩa 194.000 USD**. Một phương án trung gian có thể giữ dịch vụ managed của A, nhưng lập data inventory, thử export/restore và cô lập một vài API trọng yếu với chi phí thấp hơn nhiều. So sánh phải bao gồm phương án trung gian này.

### Ngưỡng nào đáng đầu tư?

Đầu tư tính di chuyển khi ít nhất một điều kiện có bằng chứng đủ mạnh:

1. **Yêu cầu bắt buộc:** luật, hợp đồng, quy định lưu trú dữ liệu hoặc khách hàng yêu cầu môi trường khác trong thời hạn xác định.
2. **Rủi ro kinh doanh khó chấp nhận:** nếu không thoát được, thiệt hại vượt ngưỡng doanh nghiệp chấp nhận dù xác suất không cao.
3. **Lợi ích kinh tế có thể đo:** sau khi tính toàn bộ TCO, thay đổi nhà cung cấp đem lại giá trị vượt chi phí và rủi ro.
4. **Khả năng thay đổi cao:** sản phẩm có nhu cầu triển khai on-premise, private cloud hoặc khu vực mà một nhà cung cấp không phục vụ được.
5. **Cơ hội thiết kế ranh giới chi phí thấp:** thêm abstraction tại đúng nơi, lưu dữ liệu theo định dạng phổ biến và thử restore có thể giảm rủi ro lớn với chi phí hợp lý.

## 9. Multi-region, multi-cloud và hybrid không giải quyết cùng một vấn đề

| Mô hình | Giải quyết tốt nhất | Điều chưa được bảo đảm |
| --- | --- | --- |
| **Một cloud, multi-AZ** | Sự cố instance/zone, HA theo khả năng dịch vụ | Sự cố cả region, phụ thuộc nhà cung cấp |
| **Một cloud, multi-region** | Một số kịch bản sự cố region, phục vụ địa lý | Khả năng rời nhà cung cấp, nhất quán dữ liệu tự động |
| **Multi-cloud active/passive** | Có sẵn một đích dự phòng nếu thiết kế và diễn tập đầy đủ | RTO/RPO không tự đạt; phải đồng bộ dữ liệu, bảo mật, vận hành |
| **Multi-cloud active/active** | Một số yêu cầu sử dụng nhiều nền tảng liên tục | Độ trễ liên cloud, split-brain, xung đột dữ liệu và độ phức tạp rất cao |
| **Hybrid cloud/on-premise** | Tích hợp tài nguyên tại chỗ hoặc yêu cầu vị trí dữ liệu | Tính tương thích hoàn toàn, vận hành rẻ hoặc dễ hơn |
| **Kế hoạch xuất/nhập định kỳ** | Giữ khả năng thoát về dài hạn với chi phí thường thấp hơn | Chuyển đổi ngay khi có sự cố nghiêm trọng |

**Multi-cloud là một lựa chọn kiến trúc có chi phí vận hành liên tục**, không phải cách mặc định để chứng minh độc lập nhà cung cấp. Đặc biệt, nhiều hệ thống không thể chạy active/active với hai database độc lập nếu không thiết kế rõ ownership, consistency, conflict resolution và quy trình phục hồi.

Nếu mục tiêu là chịu lỗi một availability zone với RTO tính bằng phút, multi-AZ có thể phù hợp. Nếu mục tiêu là có thể rời nhà cung cấp trong sáu tháng sau thay đổi hợp đồng, kế hoạch M1–M3 có thể đủ. Cả hai đều hợp lý nếu đáp ứng đúng rủi ro doanh nghiệp cần xử lý.

## 10. Quy trình đánh giá có thể áp dụng trong một buổi architecture review

Một vòng đánh giá nên tạo ra **quyết định kiểm chứng được** thay vì chỉ tạo danh sách công nghệ.

### Bước 1 — Cố định bối cảnh

Ghi hệ thống, người dùng, giao dịch quan trọng, lưu lượng, dữ liệu nhạy cảm, SLO và RTO/RPO. Xác nhận ai là người quyết định và ai chịu hậu quả nếu phải chuyển.

### Bước 2 — Chọn 1–3 kịch bản chuyển đổi khả tín

Ví dụ: phải chuyển dữ liệu sang vùng được phép trong 12 tháng; hợp đồng của nhà cung cấp hết hạn sau 24 tháng; khách hàng doanh nghiệp yêu cầu một môi trường riêng. Không đưa “mọi nhà cung cấp có thể biến mất ngày mai” thành yêu cầu bắt buộc nếu chưa có phân tích rủi ro.

### Bước 3 — Kiểm kê phụ thuộc theo hành trình

Theo đường đi từ request đến database, queue, storage, hệ thống định danh, log và đối tác. Ghi tác động đến dữ liệu, mã nguồn, security, cấu hình và người vận hành.

### Bước 4 — Xác định mức di chuyển cần thiết cho từng thành phần

Chọn M0–M4 theo kịch bản, không chọn một mức chung cho toàn hệ thống. Ví dụ có thể yêu cầu thử export/restore dữ liệu mỗi quý (M1) nhưng chỉ cần tài liệu cách thay dịch vụ email (M0/M2 tùy mức thực thi).

### Bước 5 — So sánh ít nhất ba phương án

So sánh **managed chuyên biệt**, **managed nhưng có ranh giới thay thế** và **stack có thể chạy lại rộng hơn**. Với mỗi phương án, tính TCO, thời gian ra mắt, năng lực vận hành, bảo mật, độ tin cậy và thời gian thực hiện exit scenario.

### Bước 6 — Chạy thử điều chưa chắc chắn

Kiểm tra một phần dữ liệu thực tế đã bảo vệ phù hợp, deploy tối thiểu trên đích, đối soát chức năng, tải và dữ liệu; đo chi phí và thời gian. Thử nghiệm nhỏ có thể giúp tránh đầu tư multi-cloud tốn kém khi không cần thiết.

### Bước 7 — Ra quyết định và gắn thời điểm đánh giá lại

Lưu Architecture Decision Record (ADR): lựa chọn, phương án khác, giả định, tác động, rủi ro được chấp nhận, cách đo và điều kiện xem lại. Ràng buộc có thể là hợp lý hôm nay nhưng trở nên không phù hợp khi tải, sản phẩm hoặc thị trường thay đổi.

### Mẫu ADR cho quyết định về tính di chuyển

~~~yaml
id: ADR-012
title: Chon managed queue va giu kha nang thay adapter
status: accepted
context:
  - Ung dung can gui thong bao bat dong bo sau khi dat lich
  - Doi van hanh nho, chua co yeu cau multi-cloud
  - Can co kha nang thay queue khi thay doi hop dong
decision:
  - Dung managed queue cua cloud hien tai
  - Domain chi phu thuoc NotificationPublisher contract
  - Consumer idempotent, co retry va dead-letter policy
alternatives:
  - Tu van hanh message broker
  - Trien khai queue song song tren hai cloud
consequences:
  benefits: Giam cong van hanh va thoi gian ra mat
  constraints: Adapter, IAM va semantics queue van can viet lai khi chuyen
verification:
  - Thu publish/consume/duplicate/timeout
  - Thu thay adapter tai moi truong test
review_trigger:
  - Khach hang yeu cau ha tang khac
  - Chi phi, quota hoac dieu khoan nha cung cap thay doi dang ke
~~~

Mẫu này lưu quyết định kiến trúc, **không phải cấu hình chạy trực tiếp**. Việc dùng interface không loại bỏ yêu cầu kiểm tra chính sách retry, thứ tự thông điệp và giới hạn dịch vụ thực tế.

## 11. Thực hành: đánh giá một quyết định ràng buộc trong kiến trúc cloud

**Tình huống giả định:** Một nền tảng đặt lịch có 100.000 người dùng hoạt động hằng ngày, backend là container chạy trên dịch vụ managed ở cloud A, managed PostgreSQL, managed queue, object storage và công cụ quan sát của cloud A. Có khoảng 4 TB dữ liệu lịch sử và tệp đính kèm. Sản phẩm cần độ sẵn sàng tốt cho đặt lịch và bảo vệ dữ liệu khách hàng; nhóm kỹ thuật 8 người, không có đội vận hành multi-cloud riêng.

Doanh nghiệp có thể ký hợp đồng với một khách hàng yêu cầu xử lý dữ liệu trong một vùng chỉ cloud B hỗ trợ. Hiện chưa có hợp đồng ký kết; thời hạn triển khai nếu ký là **9 tháng**. Ban giám đốc hỏi: “Có cần viết lại tất cả theo Kubernetes và triển khai active/active ở hai cloud ngay không?”

### Nhiệm vụ

1. **Xác định trigger:** điều gì biến giả định về khách hàng thành nghĩa vụ chuyển thật? Cần xác nhận phạm vi khách hàng đó, vùng dữ liệu, quyền truy cập và ngày bàn giao nào?
2. **Lập bảng phụ thuộc:** đánh giá ít nhất database, queue, object storage, IAM/KMS, mạng, CI/CD và quan sát. Chỉ ra phụ thuộc có thể gây mất dữ liệu hoặc vi phạm hợp đồng.
3. **Chọn mức M0–M4 theo lớp:** trình bày vì sao mỗi lớp cần mức đó. Phân biệt khả năng chuyển một nhóm khách hàng sang cloud B với việc chạy toàn bộ hệ thống active/active.
4. **Đề xuất ba phương án:** giữ nguyên và chuẩn bị exit plan; tạo ranh giới và thử migration có chọn lọc; xây dựng môi trường thứ hai thường trực. So sánh chi phí, thời hạn, độ tin cậy, bảo mật và công sức vận hành.
5. **Thiết kế PoC trong phạm vi nhỏ:** dựng đường đi đặt lịch ở cloud B bằng dữ liệu test, thử export/restore có đối soát và đo thời gian; xác định rủi ro IAM, encryption, network và monitoring.
6. **Đưa ra điều kiện ra quyết định:** khi nào tăng từ M1/M2 lên M3? Chỉ số hoặc văn bản nào phải có trước khi đầu tư vận hành hai cloud liên tục?

### Hướng giải có cơ sở

Với dữ kiện đã cho, **chưa đủ bằng chứng để bắt buộc active/active đa đám mây**. Một hướng hợp lý là:

- Xác thực yêu cầu khách hàng và điều khoản data residency với bộ phận pháp chế/sản phẩm trước; quyết định phạm vi dữ liệu cần chuyển.
- Đặt ưu tiên cao cho **dữ liệu và khóa mã hóa**: kiểm kê loại dữ liệu, extension database, tệp, metadata, quyền, backup; diễn tập export/restore có checksum và đối soát nghiệp vụ.
- Đánh giá khả năng triển khai một lát cắt API và database trên cloud B (**M3 ở quy mô thử nghiệm**), chưa vận hành sản xuất song song lâu dài.
- Cô lập tích hợp queue, storage và identity ở những chỗ có lợi; tránh viết một abstraction “đa cloud” cho mọi dịch vụ khi chưa biết các nền tảng đích.
- Lập ngân sách migration và thời gian chạy song song nếu hợp đồng thành hiện thực; chuẩn bị checklist cutover, rollback và observability.

Nếu hợp đồng được ký với hạn 9 tháng, nhóm phải chuyển từ **nghiên cứu rủi ro** sang **kế hoạch delivery có mốc và người phụ trách**, kiểm chứng khả năng triển khai cloud B sớm. Nếu yêu cầu là phục vụ hai vùng độc lập lâu dài, xem xét phân vùng khách hàng, quản trị dữ liệu và vận hành hai môi trường. Nếu yêu cầu chỉ là lưu một tập dữ liệu trong vùng khác, có thể có giải pháp nhỏ hơn việc di chuyển toàn bộ hệ thống.

Không thể kết luận phương án cuối cùng chỉ bằng con số 4 TB hoặc số lượng người dùng. Cần đo băng thông chuyển dữ liệu, tốc độ thay đổi, throughput, độ phức tạp schema, yêu cầu pháp lý và năng lực đội ngũ.

### Tiêu chí nghiệm thu bài thực hành

Một bản đánh giá tốt phải trả lời được:

| Câu hỏi kiểm tra | Bằng chứng tối thiểu |
| --- | --- |
| Vì sao cần di chuyển? | Trigger và yêu cầu nghiệp vụ/tuân thủ có chủ sở hữu |
| Phải chuyển phần nào? | Data inventory, dependency map, ranh giới workload |
| Di chuyển trong bao lâu? | Ước lượng dựa trên PoC, dung lượng và quy trình cutover |
| Dữ liệu có đúng và an toàn không? | Đối soát, quyền, mã hóa, thử restore/cutover |
| Ở đích có vận hành được không? | CI/CD, dashboard, alert, runbook, load/failure test |
| Lợi ích có xứng chi phí không? | TCO cùng giả định, phương án thay thế, rủi ro chấp nhận |

## 12. Những ngộ nhận và lỗi thiết kế thường gặp

**“Dùng Docker/Kubernetes là đã portable.”** Container và bộ điều phối giải quyết một phần đóng gói/triển khai. Database, identity, mạng, secret, queue và vận hành vẫn có thể gắn sâu với nhà cung cấp.

**“Terraform viết một lần chạy ở mọi cloud.”** Terraform có thể quản lý nhiều provider, nhưng resource schema, khả năng dịch vụ, IAM và mạng khác nhau. Cần module/cấu hình riêng, kiểm thử và quy trình migration.

**“Open source thì không bị lock-in.”** Cần tính cả khả năng vận hành, phiên bản, plug-in, định dạng lưu, kỹ năng và hạ tầng hỗ trợ. Tự quản có thể tạo gánh nặng lớn hơn một dịch vụ managed phù hợp.

**“Chúng ta có thể export dữ liệu nên có thể chuyển nhanh.”** Khôi phục không chỉ là copy byte. Cần schema, metadata, quyền, khóa, đối soát, xử lý dữ liệu phát sinh và cutover an toàn.

**“Multi-cloud luôn giúp tăng độ sẵn sàng.”** Nếu dữ liệu chưa xử lý nhất quán, mạng liên cloud phụ thuộc, quy trình failover chưa thử hoặc đội vận hành bị phân tán, độ phức tạp có thể làm tăng nguy cơ sự cố.

**“Mọi API độc quyền đều xấu.”** Một dịch vụ managed chuyên biệt có thể giảm công bảo trì và cải thiện năng lực giao hàng. Vấn đề nằm ở rủi ro thay thế và thiếu kế hoạch kiểm soát rủi ro đó.

**“Chỉ cần chọn phương án rẻ nhất mỗi tháng.”** Phải tính tổng chi phí xây dựng, on-call, migration, egress, chạy song song, bảo mật, downtime và giới hạn hợp đồng.

**“Khả năng di chuyển có thể hoàn thiện khi cần chuyển.”** Khi yêu cầu chuyển bị ràng buộc bởi ngày pháp lý/hợp đồng, thiếu bản đồ dữ liệu và quyền có thể làm thời hạn không khả thi. Ít nhất nên có hồ sơ phụ thuộc và bằng chứng thử xuất/khôi phục cho dữ liệu quan trọng.

## 13. Checklist áp dụng trong review theo Well-Architected

| Khía cạnh | Câu hỏi kiểm tra liên quan đến ràng buộc nhà cung cấp |
| --- | --- |
| **Operational Excellence** | Runbook và pipeline có phụ thuộc nền tảng nào? Đội ngũ có vận hành và rollback ở đích không? |
| **Security** | IAM/KMS, secret, audit, quyền truy cập và residency có thể được bảo đảm khi chuyển không? |
| **Reliability** | Có phân biệt DR với provider exit? Đã thử restore, cutover và xử lý lỗi dữ liệu chưa? |
| **Performance Efficiency** | Độ trễ, throughput, quota, network egress và hành vi tải có được đo ở đích không? |
| **Cost Optimization** | Có tính TCO, cam kết hợp đồng, chi phí di chuyển, chạy song song và egress không? |
| **Sustainability** | Multi-cloud thường trực có làm tăng tài nguyên nhàn rỗi và lượng dữ liệu sao chép không cần thiết không? |

Một bản review có giá trị khi ghi được **giả định → bằng chứng → rủi ro → quyết định → người phụ trách → mốc kiểm tra lại**. Không cần đạt “điểm độc lập nhà cung cấp” cao nhất ở mọi lớp. Cần chứng minh rằng kiến trúc đáp ứng mục tiêu nghiệp vụ, hiểu rõ cái giá của những phụ thuộc đã chấp nhận và có đường xử lý đáng tin cậy khi điều kiện thay đổi.

Khả năng di chuyển là **một thuộc tính chất lượng được thiết kế theo nhu cầu**, giống như độ tin cậy hay bảo mật: phải có phạm vi, thời hạn, ngân sách, cách đo và mức chấp nhận rủi ro. Quyết định kiến trúc tốt giữ được tốc độ và lợi thế của cloud hiện tại, đồng thời bảo vệ doanh nghiệp trước những kịch bản chuyển đổi thật sự quan trọng.
