# Kiểm chứng sau di chuyển và tối ưu kiến trúc mới

> **Phạm vi:** Di chuyển và hiện đại hóa trong CLOUD_ARCHITECTURE. Bài học hướng dẫn cách xác nhận một hệ thống đã di chuyển lên đám mây đáp ứng yêu cầu nghiệp vụ, an toàn dữ liệu và vận hành; sau đó dùng bằng chứng đo lường để tối ưu kiến trúc theo các đánh đổi giữa độ tin cậy, bảo mật, hiệu năng, khả năng mở rộng và chi phí, dựa trên tư duy Well-Architected.

## 1. Vì sao di chuyển thành công vẫn cần kiểm chứng?

Một ứng dụng khởi động được trên hạ tầng đám mây mới chỉ chứng tỏ rằng một phần của quá trình triển khai đã hoạt động. Chưa thể kết luận khách hàng hoàn tất giao dịch đúng, dữ liệu không thất lạc, hệ thống chịu được tải cao, đội vận hành xử lý được sự cố hay hóa đơn hằng tháng nằm trong ngân sách. Khi chuyển từ máy chủ tại chỗ sang máy ảo, container hoặc dịch vụ được quản lý, hành vi của hệ thống có thể thay đổi vì độ trễ mạng, quy tắc định tuyến, chính sách truy cập, giới hạn kết nối, cơ chế lưu trữ và trách nhiệm vận hành cũng thay đổi.

Hai công việc liên tiếp cần được phân biệt:

1. **Kiểm chứng sau di chuyển (post-migration validation):** thu thập bằng chứng rằng hệ thống mới đáp ứng các điều kiện chấp nhận đã thống nhất. Việc này bắt đầu từ diễn tập, tiếp tục trong chuyển lưu lượng và kéo dài qua giai đoạn ổn định.
2. **Tối ưu kiến trúc mới (post-migration optimization):** sử dụng kết quả đo thực tế để điều chỉnh tài nguyên, luồng xử lý, cấu trúc dữ liệu và cách vận hành. Mục tiêu là tạo ra giá trị bền vững, không đơn thuần làm ứng dụng chạy nhanh nhất bằng mọi giá.

Một cuộc di chuyển chỉ nên được xem là hoàn tất về mặt vận hành khi **các hành trình nghiệp vụ quan trọng được xác minh**, hệ thống có thể quan sát và khôi phục, rủi ro tồn đọng có chủ sở hữu, đồng thời đội tiếp nhận biết cách triển khai, phát hiện và xử lý sự cố.

### 1.1. Kết quả học tập

Sau bài này, người học có thể:

- Biến yêu cầu nghiệp vụ thành tiêu chí chấp nhận có thể đo và có người chịu trách nhiệm.
- Thiết kế kiểm chứng theo lớp: chức năng, tính đúng đắn dữ liệu, tích hợp, hiệu năng, bảo mật, độ tin cậy và vận hành.
- Xây dựng điều kiện quyết định tiếp tục, tạm dừng hoặc quay lui khi chuyển lưu lượng.
- Đọc tín hiệu thực tế để chọn biện pháp tối ưu phù hợp, nhận diện đánh đổi giữa các trụ cột Well-Architected.
- Lập báo cáo bằng chứng và hồ sơ quyết định kiến trúc để chuyển giao cho vận hành.

## 2. Đặt tiêu chí chấp nhận trước khi đo

### 2.1. Xác định ranh giới và đường cơ sở

Trước tiên cần liệt kê các thành phần và luồng có ảnh hưởng đến người dùng: giao diện, API, xử lý nền, kho dữ liệu, hàng đợi, nhà cung cấp thanh toán, hệ thống định danh, DNS, mạng kết nối và dịch vụ giám sát. Với mỗi thành phần, xác định dữ liệu được đọc/ghi ở đâu, phụ thuộc nào là đồng bộ hoặc bất đồng bộ, và ai được phép thay đổi cấu hình.

**Đường cơ sở (baseline)** nên được đo tại hệ thống cũ trong một khoảng đại diện cho ngày thường, giờ cao điểm, công việc định kỳ và những lần tăng tải có thể dự đoán. Thực tế có thể sử dụng khoảng một đến hai tuần nếu chu kỳ kinh doanh phù hợp; không có một độ dài cố định áp dụng cho mọi hệ thống. Ghi lại đồng thời phiên bản ứng dụng, quy mô dữ liệu, cấu hình, khu vực triển khai, phân phối yêu cầu và thời điểm quan sát. Nếu hệ thống cũ đã chậm hoặc thiếu an toàn, không biến mọi chỉ số cũ thành mục tiêu bắt buộc của hệ thống mới.

Các thuật ngữ cần dùng nhất quán:

| Khái niệm | Ý nghĩa | Lưu ý khi sử dụng |
|---|---|---|
| **SLI (Service Level Indicator)** | Chỉ số đo chất lượng phục vụ, như tỷ lệ giao dịch thành công, độ trễ hoặc độ mới dữ liệu | Phải quy định cách đo, mẫu số, phạm vi và cửa sổ thời gian |
| **SLO (Service Level Objective)** | Mục tiêu định lượng cho một hoặc nhiều SLI | Là mục tiêu chấp nhận về chất lượng dịch vụ, cần gắn với nhu cầu nghiệp vụ |
| **p95/p99 latency** | Mốc độ trễ mà khoảng 95%/99% số yêu cầu quan sát có thời gian xử lý không vượt quá | Đo trên cùng loại hành trình và tải; trung bình có thể che các yêu cầu chậm |
| **RTO (Recovery Time Objective)** | Thời gian khôi phục tối đa mà doanh nghiệp chấp nhận sau sự cố | Phải làm rõ từ thời điểm nào đến khi nào được xem là phục hồi |
| **RPO (Recovery Point Objective)** | Khoảng mất dữ liệu tối đa chấp nhận được tính theo thời điểm phục hồi | Bản sao dữ liệu và sao lưu chỉ có ý nghĩa khi đo được dữ liệu có thể khôi phục |
| **Error budget** | Phần sai lệch được cho phép bởi SLO trong một kỳ đánh giá | Cách tính phụ thuộc SLI: theo yêu cầu, theo thời gian hoặc theo sự kiện |
| **Canary** | Phát hành tới một phần nhỏ lưu lượng/nhóm người dùng trước khi mở rộng | Chỉ hữu ích khi có phép đo, giới hạn rủi ro và cơ chế dừng |

Ví dụ, SLO tỷ lệ yêu cầu thành công **99,9%** trên tổng số yêu cầu hợp lệ trong 30 ngày cho phép tối đa **0,1% yêu cầu lỗi** theo định nghĩa SLI. Không được mặc nhiên quy đổi thành số phút ngừng dịch vụ nếu SLI đang đo theo số yêu cầu. Ngược lại, một SLO theo thời gian khả dụng sẽ cần phương pháp đếm thời gian riêng.

### 2.2. Ma trận chấp nhận có thể kiểm toán

Mỗi tiêu chí cần có **mốc mục tiêu, phương pháp đo, cửa sổ đánh giá, bằng chứng và người phê duyệt**. Bảng dưới là ví dụ minh họa cho dịch vụ thương mại điện tử; các con số phải được điều chỉnh theo cam kết nghiệp vụ, ngân sách và tính chất dữ liệu thực tế.

| Nhóm | Tiêu chí minh họa | Cách xác minh | Người xác nhận |
|---|---|---|---|
| Nghiệp vụ | Đặt hàng và thanh toán hoạt động; không phát sinh thanh toán lặp do retry | Bài thử end-to-end, đối soát mã giao dịch và idempotency key | Product owner + QA |
| Dữ liệu | Không thiếu đơn đã xác nhận tại mốc đối soát; tổng tiền khớp sau khi chuẩn hóa quy tắc | Snapshot nhất quán, đối soát theo lô, kiểm tra ngoại lệ | Data owner |
| Hiệu năng | p95 API đặt hàng ≤ 400 ms ở mức 300 yêu cầu/giây | Kiểm thử tải có dữ liệu đại diện và đo từ một điểm quan sát cố định | Tech lead + SRE |
| Độ tin cậy | RTO ≤ 60 phút, RPO ≤ 5 phút cho kịch bản thảm họa đã xác định | Diễn tập khôi phục, kiểm tra dữ liệu và nghiệp vụ sau phục hồi | SRE + business owner |
| Bảo mật | Không còn phát hiện nghiêm trọng/cao chưa được chấp nhận rủi ro; luồng quyền đúng thiết kế | Rà soát IAM, quét lỗ hổng, thử truy cập ngoài quyền | Security owner |
| Vận hành | Có log, metric, trace, cảnh báo hữu ích và runbook được diễn tập | Mô phỏng sự cố, kiểm tra người trực nhận cảnh báo | Operations owner |
| Chi phí | Có phân bổ chi phí và ngưỡng ngân sách cho các môi trường | Báo cáo theo nhãn, dashboard chi phí và kiểm tra cảnh báo | FinOps/Finance |

Đối với quyết định **go/no-go**, không nên lấy trung bình các tiêu chí để che một thất bại nghiêm trọng: một lỗi mất đơn hàng, rò rỉ bí mật hoặc không thể khôi phục dữ liệu có thể khiến toàn bộ lần chuyển đổi phải dừng dù tốc độ và chi phí đều tốt.

### 2.3. Các cổng quyết định

~~~mermaid
flowchart LR
    A["Đường cơ sở và tiêu chí chấp nhận"] --> B["Diễn tập di chuyển"]
    B --> C{"Đạt điều kiện trước cutover?"}
    C -- "Chưa" --> D["Khắc phục và diễn tập lại"]
    D --> B
    C -- "Đạt" --> E["Chuyển lưu lượng có kiểm soát"]
    E --> F{"Guardrail có vi phạm?"}
    F -- "Có" --> G["Dừng tăng tải, xử lý hoặc rollback"]
    G --> B
    F -- "Không" --> H["Ổn định và chuyển giao"]
    H --> I["Đo, tối ưu, đánh giá lại"]
~~~

Ba thời điểm kiểm chứng là **trước cutover** (chứng minh sẵn sàng), **trong cutover** (phát hiện suy giảm khi lưu lượng thật xuất hiện) và **sau cutover** (xác minh dữ liệu, độ ổn định, khả năng khôi phục và chi phí qua chu kỳ hoạt động). Dấu hiệu tốt ở một thời điểm không thay thế phép đo ở thời điểm khác.

## 3. Kiểm chứng nhiều lớp

### 3.1. Hạ tầng, cấu hình và kết nối

Kiểm tra cấu hình triển khai thực tế so với kiến trúc đã duyệt và mã hạ tầng (Infrastructure as Code):

- Vùng địa lý/availability zone, mạng riêng, subnet, bảng định tuyến, NAT, VPN hoặc đường kết nối chuyên dụng, quy tắc firewall và security group.
- Cân bằng tải, kiểm tra sức khỏe, TLS/chứng chỉ, tên miền, thời gian sống bản ghi DNS và hành vi của máy khách khi DNS thay đổi.
- Quyền truy cập đến cơ sở dữ liệu, kho đối tượng, secret manager, dịch vụ định danh và nhà cung cấp bên ngoài.
- Cấu hình môi trường, phiên bản runtime, container image, biến cấu hình, số lượng bản sao, giới hạn CPU/bộ nhớ, dung lượng ổ và quota dịch vụ.
- Nơi lưu khóa, cơ chế mã hóa, vùng lưu trữ log, chính sách sao lưu và thời gian giữ bản ghi.

Một phép ping thành công hoặc HTTP 200 từ trang chủ không xác nhận toàn bộ luồng. Cần kiểm thử đường đi **từ người dùng qua DNS/TLS/load balancer/API tới dữ liệu và tích hợp**, bao gồm cả đường đi của worker chạy nền và chiều kết nối ra ngoài.

### 3.2. Chức năng và bất biến nghiệp vụ

Thử nghiệm theo những **hành trình có giá trị**: đăng nhập, tra cứu, tạo đơn, thanh toán, hoàn tiền, xuất báo cáo và đồng bộ đối tác. Mỗi hành trình nên có dữ liệu vào, kết quả mong đợi, dữ liệu liên quan và dấu vết quan sát.

Đặc biệt, kiểm tra **bất biến nghiệp vụ** thay vì chỉ đếm mã trạng thái thành công:

- Một mã yêu cầu thanh toán chỉ tạo ra một tác động tài chính dù client hoặc queue gửi lại nhiều lần. Dùng idempotency key, ràng buộc duy nhất và kiểm tra trạng thái giao dịch; không giả định mạng hay message broker đảm bảo tác động chỉ xảy ra một lần.
- Không thể bán lượng hàng vượt quy tắc tồn kho khi nhiều yêu cầu đến đồng thời.
- Đơn hàng có trạng thái thanh toán thành công phải tham chiếu được đến giao dịch hợp lệ.
- Quyền của từng vai trò không tăng do cấu hình IAM hoặc mapping danh tính thay đổi.

Bao phủ cả các nhánh lỗi: timeout, retry, request trùng, token hết hạn, dịch vụ bên thứ ba không phản hồi, xử lý chậm và dữ liệu chứa ký tự Unicode hoặc múi giờ khác nhau.

### 3.3. Tính toàn vẹn và độ mới dữ liệu

Di chuyển dữ liệu thường phối hợp **bản chụp ban đầu (snapshot)** và **bắt thay đổi (CDC/change data capture)**. Nếu hệ thống cũ vẫn ghi trong lúc chuyển, so sánh hai cơ sở dữ liệu ở hai thời điểm khác nhau có thể tạo ra sai lệch giả hoặc che dấu bản ghi bị bỏ sót.

Quy trình đối soát đáng tin cậy gồm:

1. Chốt **mốc nhất quán**: transaction log position, CDC offset, timestamp có quy ước rõ hoặc một snapshot giao dịch tương đương. Lưu mốc này cùng báo cáo.
2. Đảm bảo hệ đích đã áp dụng đầy đủ các thay đổi đến mốc được chọn. Giám sát **replication lag**, số sự kiện chờ và lỗi xử lý CDC.
3. So sánh **số lượng theo phân vùng có nghĩa**, khóa chính, tổng nghiệp vụ, quan hệ khóa ngoại, kiểm tra null và các trường hợp biên. Không chỉ so sánh tổng số dòng.
4. Với tập dữ liệu lớn, đối chiếu theo lô/chunk bằng checksum của bản ghi đã **chuẩn hóa cùng cách tuần tự hóa**; lấy mẫu có chủ đích các bản ghi nhạy cảm, giá trị lớn và bản ghi vừa cập nhật.
5. Xử lý nguyên nhân khác biệt: chuyển đổi định dạng, timezone, precision của số thập phân, collation, encoding, quy tắc làm tròn, bản ghi xóa mềm và giao dịch chưa hoàn tất.
6. Ghi lại sai lệch, cho chạy lại phép kiểm và chỉ đóng hạng mục sau khi dữ liệu khớp hoặc có chấp nhận rủi ro có thẩm quyền.

Ví dụ truy vấn đối soát đơn hàng theo ngày trên **cả nguồn và đích**, cùng một mốc nhất quán và cùng quy tắc lọc:

~~~sql
SELECT
    CAST(created_at AS DATE) AS order_day,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_value,
    SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END) AS paid_count
FROM orders
WHERE created_at < :cutoff
GROUP BY CAST(created_at AS DATE)
ORDER BY order_day;
~~~

Đây là truy vấn minh họa, **không tự tạo snapshot nhất quán**. Trong môi trường có ghi liên tục, điều kiện thời gian trên cột ứng dụng chưa đủ nếu update/delete vẫn xảy ra sau mốc; cần dùng snapshot, log position hoặc cơ chế versioning phù hợp với hệ quản trị dữ liệu. Khi so sánh giá trị tiền, ưu tiên kiểu số thập phân chính xác, không quy đổi sang số thực dấu phẩy động. Với dữ liệu cá nhân, báo cáo chỉ chứa số liệu tổng hợp và mã tham chiếu đã che thông tin nhạy cảm.

**Lưu ý khi rollback:** nếu hệ mới đã nhận lệnh ghi sau khi chuyển, việc quay về cơ sở dữ liệu cũ chỉ an toàn khi có chiến lược đưa các ghi mới về nguồn cũ hoặc đưa dịch vụ về trạng thái không nhận ghi trong quá trình đồng bộ. Không bật hai hệ thống cùng làm nguồn ghi chính nếu chưa thiết kế và kiểm chứng giải quyết xung đột; nếu không có thể gây **split-brain**, tạo đơn và giao dịch mâu thuẫn.

### 3.4. Tích hợp và xử lý bất đồng bộ

Đối với queue, event bus, webhook, scheduler và job nền, đo thêm số thông điệp tồn (backlog), tuổi thông điệp cũ nhất, thời gian hoàn thành đầu cuối, tỷ lệ retry và dead-letter queue (DLQ). Một API trả về 202 Accepted chưa chứng minh công việc phía sau đã thành công.

Kiểm tra khi thông điệp đến **trùng, muộn hoặc không đúng thứ tự**; khi consumer bị khởi động lại; và khi đối tác gửi webhook lặp. Cơ chế retry cần có backoff và giới hạn; nhiệm vụ không xử lý được phải được phát hiện, lưu bằng chứng và có quy trình xử lý DLQ. Đồng hồ hệ thống, múi giờ và lịch chạy batch cũng cần được đối chiếu vì lịch tác vụ có thể thay đổi sau di chuyển.

### 3.5. Hiệu năng và khả năng mở rộng

Chạy phép thử với **dữ liệu, tỷ lệ đọc/ghi, kích thước payload và phân phối lưu lượng gần thực tế**. Ghi rõ load generator đặt ở đâu; nếu máy phát tải quá yếu hoặc đặt xa hơn so với người dùng thật, kết quả có thể bị hiểu sai.

| Dạng kiểm thử | Câu hỏi cần trả lời | Chỉ số theo dõi |
|---|---|---|
| Baseline/comparison | Luồng mới có tương đương hoặc tốt hơn điều kiện chấp nhận không? | p50/p95/p99, throughput, error rate |
| Load | Hệ thống ổn định ở mức tải dự kiến không? | Độ trễ theo tải, CPU/memory, DB connections |
| Stress | Giới hạn nằm ở đâu và thất bại diễn ra ra sao? | Điểm bão hòa, timeout, tỷ lệ lỗi, backpressure |
| Spike | Autoscaling phản ứng kịp khi tải tăng đột biến không? | Thời gian scale, cold start, độ dài queue |
| Soak | Có rò rỉ tài nguyên hoặc suy giảm kéo dài không? | Memory trend, pool usage, lock wait, disk |
| Failure/recovery | Khi một thành phần hỏng, hệ thống suy giảm và hồi phục thế nào? | Tỷ lệ thành công, failover time, dữ liệu sai lệch |

Không kết luận chỉ từ CPU. CPU thấp nhưng p95 cao có thể do truy vấn chậm, connection pool cạn, gọi API xa vùng, khóa dữ liệu hoặc hàng đợi chờ. Phân tách độ trễ bằng distributed trace, database query plan và metric theo từng dependency. Khi so sánh trước/sau, giữ tương đương workload, phiên bản, kích thước dữ liệu, cache warm-up và thời gian đo.

### 3.6. Khả năng khôi phục và độ tin cậy

Tách các loại lỗi để thử đúng cơ chế:

- **Lỗi instance/pod:** health check, khởi động lại, phân phối lại lưu lượng.
- **Lỗi availability zone:** hạ tầng nhiều vùng sẵn sàng có thực sự loại bỏ điểm lỗi đơn không; dữ liệu và worker có thể tiếp tục xử lý không.
- **Lỗi cơ sở dữ liệu:** failover, khả năng ứng dụng tái kết nối, giao dịch đang thực hiện, connection pool và chiến lược retry.
- **Lỗi vùng địa lý/thảm họa:** kích hoạt kịch bản DR theo phương án thực tế, xác minh dữ liệu khôi phục, DNS/định tuyến và các phụ thuộc ngoài vùng.
- **Lỗi do con người hoặc mã độc:** khả năng phục hồi bản sao lưu độc lập, quyền xóa/ghi bản sao lưu, kiểm tra tính toàn vẹn.

**Sao lưu có lịch chạy thành công chưa phải là khôi phục đã được chứng minh.** Cần thực sự phục hồi dữ liệu, khởi chạy ứng dụng, kiểm tra giao dịch và ghi lại thời gian từ khi sự cố bắt đầu đến khi chức năng quan trọng hoạt động lại (RTO đo được). Đo RPO bằng chênh lệch giữa thời điểm dữ liệu hợp lệ mới nhất có thể phục hồi và thời điểm sự cố đã định nghĩa. Bảo đảm các số đo bám đúng kịch bản, ví dụ lỗi một AZ khác với mất cả vùng.

Thử nghiệm chịu lỗi nên có giới hạn tác động, kịch bản dừng rõ ràng và lịch được đồng ý; không cần gây sự cố trên sản xuất nếu môi trường thử nghiệm phù hợp có thể chứng minh yêu cầu. Tuy vậy, cần ghi lại giới hạn của mô phỏng, nhất là với DR và hành vi phụ thuộc nhà cung cấp.

### 3.7. Bảo mật và tuân thủ

Kiểm tra lại **mô hình trách nhiệm chia sẻ** theo loại dịch vụ đám mây đã chọn. Chuyển cơ sở dữ liệu sang dịch vụ quản lý có thể giảm công việc vá hệ điều hành, nhưng đội ứng dụng vẫn chịu trách nhiệm về quyền truy cập dữ liệu, cấu hình an toàn, sao lưu, phân loại và quản trị dữ liệu.

Các nhóm kiểm tra chính gồm:

- **Danh tính và quyền:** quyền tối thiểu cho người và service account, định danh workload, MFA với tài khoản đặc quyền, tách môi trường, không cấp quyền wildcard không cần thiết.
- **Mạng và bề mặt tấn công:** thành phần nào có IP công khai, rule inbound/outbound, phân đoạn mạng, kết nối riêng, WAF, chống lạm dụng và giới hạn tốc độ.
- **Dữ liệu và bí mật:** TLS trên đường truyền, mã hóa lưu trữ, quản trị khóa, vòng đời secret, không đưa mật khẩu/token vào image, biến log hoặc repository.
- **Phát hiện và ứng phó:** audit log có thời gian và định danh chính xác, lưu trữ chống sửa đổi khi cần, cảnh báo thay đổi quyền và truy cập bất thường.
- **Tuân thủ:** vị trí lưu dữ liệu, thời hạn lưu/xóa, phân quyền truy cập theo dữ liệu nhạy cảm và các yêu cầu pháp lý/khách hàng hiện hành áp dụng cho hệ thống.

Ghi rõ phạm vi quét và phát hiện còn tồn đọng. Câu “không phát hiện lỗ hổng” không đồng nghĩa “chắc chắn không có lỗ hổng”.

### 3.8. Khả năng quan sát và sẵn sàng vận hành

Tối thiểu phải trả lời được: **cái gì đang hỏng, ảnh hưởng đến ai, từ khi nào, tại lớp nào và ai xử lý**. Hệ thống observability nên có:

- **Metrics:** lưu lượng, lỗi, độ trễ, saturation; thêm chỉ số đặc thù như đơn được xác nhận, giao dịch trùng, lag CDC, tuổi thông điệp.
- **Logs:** cấu trúc thống nhất, có timestamp, request/correlation ID, môi trường và phiên bản; che PII, bí mật và dữ liệu thanh toán.
- **Traces:** theo dõi hành trình qua API, database, cache, queue và dịch vụ ngoài.
- **Alerts:** gắn với SLO/ảnh hưởng người dùng, mức ưu tiên, thời gian đánh giá, người nhận và runbook; hạn chế cảnh báo ồn từ chỉ số máy chủ đơn lẻ.
- **Runbooks:** cách xác định triệu chứng, quyền truy cập, lệnh an toàn để chẩn đoán, bước khôi phục, cách thông báo và đường leo thang.

Trước khi bàn giao, thử ít nhất một tình huống như tăng lỗi thanh toán hoặc queue bị nghẽn và xác nhận người trực **thực sự nhận cảnh báo và thực hiện được** quy trình. Đồng thời kiểm tra audit trail cho các thao tác triển khai và thay đổi cấu hình.

## 4. Cutover, canary và rollback có kiểm soát

**Cutover** là thời điểm chuyển người dùng hoặc nguồn ghi chính sang môi trường mới; nó không nhất thiết là một thao tác duy nhất. Cơ chế chuyển phù hợp phụ thuộc mức rủi ro, khả năng tương thích dữ liệu và độ dễ đảo ngược.

### 4.1. Trước khi chuyển

Hoàn thành và ký xác nhận các điều kiện:

1. Phiên bản, cấu hình và người sở hữu từng hệ thống được đóng băng theo quy trình thay đổi; có snapshot/backup và đã kiểm tra khả năng khôi phục.
2. Dữ liệu được đồng bộ tới mốc thỏa thuận, lag nằm trong ngưỡng; với hệ ghi liên tục có quy trình khóa ghi ngắn hoặc chuyển quyền **single-writer** được diễn tập.
3. Kiểm thử chức năng, hiệu năng, bảo mật và vận hành quan trọng đã đạt; các ngoại lệ có chủ sở hữu và người chấp nhận rủi ro.
4. Dashboard và cảnh báo theo dõi nguồn cũ, nguồn mới, dữ liệu, tài nguyên, lỗi nghiệp vụ đã sẵn sàng.
5. Có thông điệp liên lạc, đầu mối ra quyết định, thời điểm kiểm tra và phương án dừng/khôi phục thực thi được.

### 4.2. Trong khi chuyển

Có thể dùng blue-green, canary theo nhóm người dùng hoặc tăng dần tỷ lệ yêu cầu. Ví dụ cấu hình **giả mã minh họa** cho một đợt chuyển có đo guardrail; đây không phải cú pháp trực tiếp của công cụ triển khai cụ thể:

~~~yaml
rollout:
  strategy: canary
  traffic_steps_percent: [1, 5, 25, 50, 100]
  minimum_observation_minutes_per_step: 20
  guardrails:
    checkout_success_rate_min: 0.9995
    checkout_p95_ms_max: 400
    replication_lag_seconds_max: 10
  critical_stop_conditions:
    - confirmed_order_missing
    - duplicate_payment_effect_detected
    - secret_exposure_detected
  on_breach: pause_and_invoke_runbook
~~~

Ngưỡng, tỷ lệ chuyển và thời gian quan sát là **ví dụ**, không phải khuyến nghị mặc định. Nếu lưu lượng ít, 20 phút có thể không đủ mẫu để kết luận; cần đánh giá độ tin cậy thống kê và đủ giao dịch quan trọng. Mọi ngưỡng phải có nguồn đo độc lập và quy trình xử lý khi metric mất dữ liệu. Nếu dùng mô hình ghi dữ liệu dùng chung, chuyển lưu lượng đọc thường dễ hơn chuyển quyền ghi; phải xác minh tính tương thích phiên bản schema và khả năng rollback của ứng dụng.

Khi mỗi bước mở rộng hoàn tất, kiểm tra cùng lúc: lỗi người dùng, phân bố độ trễ, tình trạng DB/queue, đối soát giao dịch mới và trạng thái tích hợp. **Dừng tăng lưu lượng ngay** khi guardrail quan trọng bị vi phạm; điều tra và quyết định khắc phục tại chỗ hay rollback theo runbook. Không cố tăng lưu lượng vì “đa số các dashboard vẫn xanh”.

### 4.3. Chọn rollback an toàn

Rollback cần được thiết kế **trước cutover**, với các tình huống cụ thể:

| Tình huống | Hướng xử lý có thể phù hợp | Điều kiện cần xác minh |
|---|---|---|
| Phiên bản ứng dụng mới lỗi, schema còn tương thích | Hạ lưu lượng về phiên bản cũ | Bản cũ đọc/ghi được dữ liệu mới, tránh xử lý lặp |
| Cấu hình mạng/định tuyến sai | Phục hồi định tuyến/cấu hình đã kiểm chứng | Kết nối, DNS cache, timeout và phiên người dùng |
| Hệ mới đã nhận ghi nhưng cần quay về cơ sở dữ liệu cũ | Đóng băng quyền ghi, đồng bộ ngược hoặc xử lý khôi phục có kiểm soát | Tính đầy đủ/thứ tự giao dịch, duy nhất nguồn ghi, đối soát |
| Thay đổi schema không tương thích hoặc mất dữ liệu | Kích hoạt kế hoạch phục hồi dữ liệu và quy trình sự cố | Điểm khôi phục, giới hạn mất dữ liệu, tác động nghiệp vụ |

Không phải mọi thay đổi đều rollback tự động được. Ví dụ, một phép xóa cột dữ liệu hoặc thay đổi định dạng có mất thông tin cần kế hoạch **roll-forward**, sao lưu/restore hay migration bù. Đặt ưu tiên bảo toàn dữ liệu và dừng ghi khi chưa có cách quay lui chắc chắn.

### 4.4. Sau cutover: giai đoạn ổn định

Trong giai đoạn theo dõi tăng cường (hypercare), so sánh chỉ số hệ mới với baseline và điều kiện chấp nhận trong đủ các chu kỳ sử dụng quan trọng. Kiểm tra các việc chạy theo ngày/tuần như tổng hợp báo cáo, đóng sổ, gửi thông báo, hết hạn token và lưu trữ dữ liệu. Đóng sự cố theo mức độ ảnh hưởng, lưu bằng chứng và xác định rõ mốc đội dự án chuyển trách nhiệm sang đội vận hành thường xuyên.

Chỉ giải phóng nguồn cũ và các cơ chế đồng bộ tạm thời sau khi đã xác minh ràng buộc lưu trữ, chính sách giữ dữ liệu, năng lực rollback và thời điểm kết thúc hypercare; nếu xóa sớm, khả năng đối soát hoặc khôi phục sẽ mất.

## 5. Tối ưu kiến trúc dựa trên bằng chứng

Sau di chuyển, ứng dụng đã chạy trong điều kiện hạ tầng thực tế, do đó có thể đo những vấn đề mà môi trường diễn tập bỏ sót. Tuy nhiên, tối ưu có mục tiêu: **giữ hoặc cải thiện trải nghiệm người dùng, độ tin cậy và bảo mật trong ngân sách và độ phức tạp vận hành chấp nhận được**.

Một chu kỳ tối ưu có kiểm soát:

1. **Quan sát:** lấy SLI, traces, profiles, query plans, chi phí và phản hồi nghiệp vụ; xác định thời điểm và nhóm người dùng bị ảnh hưởng.
2. **Đặt giả thuyết:** nêu thành phần gây vấn đề và bằng chứng dự kiến, chẳng hạn “p95 tăng do giới hạn connection pool khi autoscaling”.
3. **Chọn thay đổi nhỏ:** điều chỉnh một vài biến có thể đảo ngược, có tiêu chí thành công và điều kiện dừng.
4. **Thử nghiệm:** so sánh ở tải, dữ liệu và khoảng thời gian tương đương; theo dõi cả chỉ số bảo vệ như error rate, RPO/RTO và chi phí.
5. **Chốt và ghi nhận:** giữ, điều chỉnh hoặc hoàn tác; cập nhật IaC, dashboard, runbook và bản ghi quyết định kiến trúc (ADR).

### 5.1. Chẩn đoán trước khi tăng tài nguyên

| Dấu hiệu | Giả thuyết cần kiểm tra | Thử nghiệm/tối ưu có thể thực hiện | Đánh đổi cần theo dõi |
|---|---|---|---|
| p95 tăng nhưng CPU ứng dụng thấp | Truy vấn DB chậm, chờ khóa, gọi dịch vụ xa hoặc cạn pool | Traces, EXPLAIN, đo thời gian chờ, điều chỉnh index/pool | Index tăng chi phí ghi/lưu trữ; pool quá lớn làm DB quá tải |
| CPU cao, nhiều pod mới tạo | Pod quá nhỏ, autoscale phản ứng muộn, xử lý tốn CPU | Right-size, profiling, HPA theo tín hiệu phù hợp | Tăng bản sao làm tăng kết nối DB và chi phí |
| Queue ngày càng dài | Consumer xử lý chậm, độc quyền tài nguyên, retry storm | Đo oldest-message-age, giới hạn concurrency, backpressure, DLQ | Scale worker có thể đẩy quá tải sang DB/đối tác |
| DB ổn nhưng client nhận timeout | DNS/TLS, load balancer, NAT, đường mạng hoặc API bên ngoài | Trace đầu cuối, kiểm tra timeouts, connection reuse và region placement | Giảm timeout quá mức có thể làm tăng retry/lỗi giả |
| Chi phí mạng tăng sau di chuyển | Truyền dữ liệu qua region/AZ, NAT, egress tới bên ngoài | Phân tích flow/cost, đặt dịch vụ gần nhau, endpoint riêng khi phù hợp | Gom thành phần có thể làm giảm khả năng chịu lỗi |
| Cache hit rate thấp, DB bị đọc lặp | TTL/key không phù hợp hoặc không có cache warming | Điều chỉnh cache có đo hit rate, thêm invalidation | Dữ liệu cũ, tăng bộ nhớ và độ phức tạp nhất quán |
| RTO thực tế vượt mục tiêu | Bước phục hồi thủ công, thiếu tự động hóa, phụ thuộc chưa sẵn sàng | Diễn tập, tự động hóa các bước lặp lại, chuẩn bị DR | Hạ tầng DR luôn hoạt động tăng chi phí |

### 5.2. Compute và khả năng mở rộng

- **Right-sizing:** dựa trên percentile CPU, RAM, IO, thời điểm cực đại và sức chứa dự phòng; không chỉ nhìn mức dùng trung bình.
- **Autoscaling:** chọn tín hiệu gần nhu cầu thực như yêu cầu đang chờ, CPU có tương quan với tải, số thông điệp/worker; cấu hình min/max, thời gian khởi động, cooldown và sức chứa của các dependency.
- **Tính không trạng thái:** tránh giữ session quan trọng trên một instance; dùng bộ lưu trạng thái phù hợp để rolling deploy và tự phục hồi dễ hơn.
- **Điều tiết tải:** rate limit, queue, backpressure và circuit breaker giúp tránh sụp đổ dây chuyền; timeout/retry phải có giới hạn và jitter khi phù hợp.
- **Phân rã dịch vụ:** chỉ tách dịch vụ khi có ranh giới nghiệp vụ và lợi ích độc lập triển khai/scale đủ lớn. Thêm microservice cũng thêm cuộc gọi mạng, dữ liệu phân tán và nghĩa vụ quan sát.

Khi scale API từ 4 lên 20 instance, nếu mỗi instance mở tối đa 100 kết nối thì hệ có thể tạo tới 2.000 kết nối, trong khi DB chịu được ít hơn nhiều. Do đó phải tính **ngân sách kết nối toàn hệ thống**, sử dụng pooling phù hợp, giới hạn số instance hoặc thay đổi cách truy vấn trước khi đơn thuần tăng số lượng máy.

### 5.3. Dữ liệu, lưu trữ và độ trễ

Kiểm tra query plan, index được dùng thật, kích thước giao dịch, connection pool, tỷ lệ cache miss, đỉnh IOPS và độ trễ giữa các thành phần. Có thể phân vùng bảng lớn, dùng read replica cho truy vấn chịu được độ trễ sao chép, cache dữ liệu đọc nhiều, tối ưu batch hoặc chọn loại lưu trữ phù hợp. Mỗi giải pháp cần nêu **tính nhất quán**: đọc từ replica có thể chưa thấy giao dịch vừa ghi; cache cần chiến lược hết hạn và vô hiệu hóa; batching giảm overhead nhưng tăng độ trễ từng sự kiện.

Đặt dữ liệu gần nơi xử lý giúp giảm độ trễ nhưng phải cân bằng yêu cầu vùng dữ liệu, tính sẵn sàng nhiều vùng và chi phí truyền. Dịch chuyển dữ liệu giữa region hoặc qua public egress có thể làm tăng cả latency và hóa đơn. Trước khi thay đổi sơ đồ dữ liệu, xác định cách triển khai tương thích ngược theo giai đoạn và đường khôi phục nếu migration thất bại.

### 5.4. Tối ưu chi phí bằng FinOps

Đám mây tính phí theo nhiều chiều: thời gian compute, dung lượng, IOPS, yêu cầu, log, truyền dữ liệu, managed service, snapshot và tài nguyên dự phòng. Vì vậy **giảm số máy** chưa chắc giảm tổng hóa đơn.

Thực hành nên bắt đầu bằng nhãn/cost allocation nhất quán (ứng dụng, đội sở hữu, môi trường, cost center), dashboard ngân sách và tỷ lệ chi phí cho một đơn vị giá trị. Ví dụ:

**Chi phí trên 1.000 đơn thành công** = 1.000 × (chi phí đám mây phân bổ cho dịch vụ đặt hàng trong kỳ) / (số đơn thành công cùng kỳ).

Chỉ số này giúp phân biệt hóa đơn tăng do lưu lượng tăng với chi phí đơn vị tăng do kiến trúc kém hiệu quả. Khi so sánh, giữ nhất quán các chi phí chung, dữ liệu đầu vào, khuyến mại và cách tính đơn thành công. Những hướng tối ưu thường có hiệu quả gồm:

- Xóa hoặc tắt tài nguyên thử nghiệm không cần thiết, điều chỉnh lifecycle của object và log theo yêu cầu lưu giữ.
- Right-size tài nguyên có dư thừa, chọn cơ chế autoscale, dùng reserved/commitment discount **sau khi** có nhu cầu ổn định và đánh giá rủi ro cam kết.
- Giảm dữ liệu truyền không cần thiết; kiểm tra phí NAT, cross-zone/cross-region, egress và phí truy vấn.
- Xác định rõ **dự phòng nào là bắt buộc** để đạt SLO/RTO/RPO; không cắt HA hoặc backup chỉ vì thấy tài nguyên “nhàn rỗi”.

Chi phí là một tiêu chí bảo vệ cùng với chất lượng dịch vụ. Một tối ưu giúp giảm 20% hóa đơn nhưng tăng lỗi thanh toán là tối ưu thất bại đối với sản phẩm thu phí giao dịch.

### 5.5. Vận hành và bảo mật sau khi tối ưu

Mọi thay đổi kiến trúc cần đi qua CI/CD, kiểm thử bảo mật, chính sách cấu hình và quan sát tương ứng. Quyền quá rộng được cấp tạm trong quá trình di chuyển cần thu hồi; secret tạm phải luân chuyển; rule mạng và bản sao lưu tạm cần rà soát. Bổ sung kiểm tra drift của IaC và các kiểm soát policy-as-code ở nơi phù hợp.

Tối ưu alert theo mức ảnh hưởng người dùng: một spike CPU ngắn có thể bình thường, còn tỷ lệ thanh toán thất bại tăng dù CPU thấp có thể là sự cố nghiêm trọng. Xem lại dashboard và runbook sau mỗi thay đổi để đội trực không chẩn đoán dựa trên sơ đồ kiến trúc đã lỗi thời.

## 6. Đánh giá bằng tư duy Well-Architected

Well-Architected là cách đặt câu hỏi có hệ thống về các quyết định thiết kế và rủi ro. Số lượng, tên trụ cột và hướng dẫn chi tiết có thể khác nhau theo framework của từng nhà cung cấp; bảng sau dùng sáu góc nhìn phổ biến để đánh giá kiến trúc đám mây.

| Góc nhìn | Câu hỏi kiến trúc | Bằng chứng và hành động điển hình |
|---|---|---|
| **Vận hành xuất sắc** | Có thể triển khai, quan sát, phục hồi và học từ sự cố nhất quán không? | IaC, runbook, dashboard SLI, diễn tập và postmortem |
| **Bảo mật** | Ai truy cập được tài nguyên và dữ liệu; kiểm soát có kiểm chứng không? | Quyền tối thiểu, phân đoạn mạng, quản lý khóa/secret, audit |
| **Độ tin cậy** | Nếu một máy, AZ, dịch vụ hoặc region ngừng hoạt động thì sao? | Kiểm thử failover, backup/restore, RTO/RPO thực đo, giới hạn tải |
| **Hiệu quả hiệu năng** | Tài nguyên và mô hình xử lý có đáp ứng độ trễ, thông lượng và tăng trưởng không? | Load test, trace, right-sizing, index và thử nghiệm scale |
| **Tối ưu chi phí** | Chi phí có tương xứng giá trị, được phân bổ và theo dõi liên tục không? | Cost allocation, unit economics, budgets và phân tích egress |
| **Bền vững** | Có tránh lãng phí tài nguyên và xử lý/lưu dữ liệu dư thừa không? | Giảm chạy nhàn rỗi, cải thiện hiệu suất tài nguyên, vòng đời dữ liệu |

Các trụ cột **tác động lẫn nhau**. Duy trì máy dự phòng ở nhiều vùng tăng chi phí nhưng giảm rủi ro ngừng hoạt động; nén dữ liệu giảm lưu trữ và băng thông nhưng cần thêm CPU; lưu log chi tiết cải thiện điều tra nhưng tăng chi phí và rủi ro lộ dữ liệu nếu không che lọc. Vì vậy, mọi quyết định phải ghi rõ ưu tiên nghiệp vụ, giả định và đánh đổi đã được chấp nhận.

Một bản **Architecture Decision Record (ADR)** ngắn có thể gồm:

~~~text
ADR: Giới hạn pool kết nối DB của dịch vụ đặt hàng
Bối cảnh: Khi autoscale, số kết nối tăng làm DB chạm giới hạn.
Phương án: Giảm max pool mỗi instance; giới hạn max replicas;
           bổ sung metric connection wait và circuit breaker.
Đánh đổi: Có thể tăng chờ kết nối ở đỉnh tải nhưng bảo vệ DB.
Tiêu chí: p95 <= 400 ms; không tăng tỷ lệ lỗi;
          connections < ngưỡng an toàn đã đo.
Quyết định: Áp dụng/không áp dụng sau load test.
Chủ sở hữu, ngày đánh giá lại, link số liệu: ...
~~~

## 7. Tình huống xuyên suốt: chuyển hệ thống đặt hàng lên đám mây

### 7.1. Bối cảnh và kiến trúc đích

Giả sử một doanh nghiệp có ứng dụng đặt hàng chạy tại chỗ, bao gồm web/API, cơ sở dữ liệu quan hệ và worker xử lý thanh toán/xác nhận bất đồng bộ. Doanh nghiệp cần mở rộng vào đợt khuyến mại, tăng khả năng khôi phục và giảm thao tác vận hành máy chủ. Kiến trúc đích dùng load balancer, container phân bố trên nhiều availability zone, DB được quản lý, hàng đợi và hệ giám sát tập trung.

~~~mermaid
flowchart TB
    U["Người dùng"] --> Edge["DNS / CDN / WAF"]
    Edge --> LB["Load balancer"]
    subgraph Cloud["Mạng ứng dụng đám mây"]
        LB --> API["API container - nhiều AZ"]
        API --> DB[("Cơ sở dữ liệu quản lý")]
        API --> MQ["Hàng đợi sự kiện"]
        MQ --> W["Worker - nhiều AZ"]
        API --> OBS["Metrics / logs / traces"]
        W --> OBS
        DB --> BK["Backup và phương án DR"]
    end
    W --> PAY["Đối tác thanh toán"]
~~~

Sơ đồ chỉ thể hiện các khối chức năng, chưa thay thế thiết kế chi tiết về subnet, IAM, hướng kết nối, phân vùng dữ liệu hoặc việc các dịch vụ hỗ trợ multi-AZ đến đâu. Đặc biệt cần kiểm tra cơ chế bảo đảm một giao dịch thanh toán không bị lặp khi queue gửi lại thông điệp.

### 7.2. Tiêu chí trước cutover

Tất cả số liệu ở tình huống này **đều giả định để minh họa phương pháp**:

- Tải mục tiêu: 300 yêu cầu đặt hàng/giây theo profile đã xác định, gồm cả đọc sản phẩm và thao tác ghi.
- Độ trễ: p95 của API đặt hàng ≤ 400 ms ở tải mục tiêu.
- Chất lượng: tỷ lệ đặt hàng thành công ≥ 99,95% trong cửa sổ đánh giá; phân biệt lỗi người dùng nhập sai hợp lệ với lỗi hệ thống.
- Dữ liệu: không có đơn đã xác nhận hoặc tác động thanh toán bị thiếu/lặp sau khi chốt mốc đối soát.
- DR: RTO ≤ 60 phút; RPO ≤ 5 phút trong kịch bản mất vùng đã được thống nhất, đo bằng một lần diễn tập phục hồi.
- Chi phí: không vượt ngưỡng chi phí đơn vị đã thống nhất mà không có phê duyệt; log, backup và mạng đều được tính.

### 7.3. Kết quả kiểm chứng giả định và cách sửa

| Hạng mục | Quan sát lần đầu | Đánh giá/hành động | Kết quả sau sửa |
|---|---|---|---|
| Hành trình đặt hàng | Các case chính chạy qua; retry làm lộ một trường hợp webhook lặp | Bổ sung idempotency key và ràng buộc duy nhất | Không có tác động tài chính lặp trong bộ thử |
| Đối soát dữ liệu | Số lượng đơn khớp, tổng tiền một ngày lệch do timezone | Chuẩn hóa timezone và truy vấn cùng snapshot/CDC position | Sai lệch đã xác minh bằng 0 ở mốc đối soát |
| Độ trễ API p95 | 480 ms tại tải mục tiêu, **không đạt** | Trace cho thấy DB pool chờ khi API autoscale; điều chỉnh giới hạn pool và index | 335 ms tại cùng profile tải, **đạt** |
| Khôi phục DR | Restore hoạt động nhưng một bước DNS thủ công làm RTO cao | Diễn tập runbook, tự động hóa bước phù hợp và xác nhận quyền truy cập | RTO 42 phút, RPO 2 phút trong kịch bản thử |
| Chi phí đơn vị | Cao hơn đường cơ sở 24% | Phát hiện egress không cần thiết và tài nguyên nhàn rỗi | Cao hơn 5%, nằm trong ngưỡng giả định |

Trong dự án thật, cột “kết quả sau sửa” phải gắn với báo cáo đo, phạm vi mẫu, phiên bản và thời gian thực hiện. Một kịch bản DR thành công không chứng minh hệ thống chịu được **mọi** dạng thảm họa; nó chỉ là bằng chứng cho kịch bản, dữ liệu và phương thức đã thử.

Sau kết quả p95 không đạt, nhóm **không nên chỉ tăng số container**, vì làm thế có thể khiến DB cạn kết nối nhanh hơn. Trace và metric cho thấy nguồn nghẽn; sửa ở pool và truy vấn rồi chạy lại đúng profile tải mới chứng minh được tác dụng. Đây là ví dụ về tối ưu dựa trên chuỗi **triệu chứng → giả thuyết → phép đo → thay đổi → đo lại**.

### 7.4. Mẫu báo cáo chấp nhận

Báo cáo go/no-go nên có các trường đủ để người ngoài nhóm triển khai kiểm chứng được:

| Trường | Ví dụ nội dung |
|---|---|
| Phạm vi | Dịch vụ đặt hàng, API/worker/DB, khu vực đích, phiên bản phát hành |
| Mốc dữ liệu | ID snapshot, CDC position hoặc log sequence đã đối soát |
| Cửa sổ đo | Thời điểm bắt đầu/kết thúc có múi giờ, số lượng giao dịch và profile tải |
| Chỉ tiêu | SLI/SLO, RTO/RPO, các bất biến nghiệp vụ và mức chấp nhận |
| Bằng chứng | Liên kết báo cáo test, dashboard, query đối soát, logs, biên bản diễn tập |
| Sai lệch | Mô tả tác động, mức độ nghiêm trọng, người chịu trách nhiệm, hạn xử lý |
| Quyết định | GO / PAUSE / ROLLBACK / ACCEPTED RISK và người có thẩm quyền ký |
| Bàn giao | Runbook, sơ đồ hiện hành, cảnh báo, lịch trực, lịch đánh giá tối ưu |

Trong trường hợp còn lỗi nghiêm trọng ảnh hưởng tính đúng đắn dữ liệu hoặc khả năng khôi phục, báo cáo phải ghi **NO-GO/PAUSE**, ngay cả khi các bài thử còn lại đã qua.

## 8. Những ngộ nhận dễ làm sai quyết định

| Ngộ nhận | Vì sao sai | Cách làm đúng |
|---|---|---|
| “Ứng dụng mở được là đã migrate xong.” | Không kiểm tra nghiệp vụ, dữ liệu, bảo mật và vận hành | Dùng ma trận chấp nhận đa lớp |
| “Số dòng DB bằng nhau nghĩa là dữ liệu đúng.” | Giá trị có thể khác, bản ghi trùng hoặc chưa đồng bộ | Đối soát theo mốc nhất quán, khóa và tổng nghiệp vụ |
| “Có backup thì chắc chắn đạt RTO/RPO.” | Backup có thể không phục hồi được hoặc mất quá lâu | Diễn tập restore và đo RTO/RPO thực tế |
| “Tăng số instance sẽ luôn tăng throughput.” | Database, queue, network hoặc đối tác có thể là nút cổ chai | Đo saturation toàn tuyến và áp dụng backpressure |
| “Giảm chi phí càng nhiều càng tốt.” | Có thể làm giảm HA, bảo mật hoặc trải nghiệm khách hàng | Dùng cost per business unit cùng guardrail SLO |
| “Canary 5% xanh là có thể chuyển 100%.” | 5% có thể chưa chạm giới hạn tải, dữ liệu hoặc nhóm khách hàng đặc biệt | Tăng theo bước với đủ mẫu và kiểm tra ở tải cao |
| “Rollback ứng dụng là quay về trạng thái dữ liệu cũ.” | Schema và dữ liệu đã ghi có thể không tương thích | Lập kế hoạch đồng bộ và quyền ghi ngay từ trước cutover |
| “Mọi vấn đề phải giải quyết bằng microservices.” | Phân rã tăng mạng, phân tán dữ liệu và gánh nặng vận hành | Chỉ tách khi có lợi ích nghiệp vụ và bằng chứng rõ |

## 9. Bài thực hành: thiết kế một đợt chấp nhận kiến trúc

**Đề bài:** Một ứng dụng quản lý đơn hàng vừa chuyển từ máy ảo tại chỗ sang container và cơ sở dữ liệu quản lý trên đám mây. Trong giờ cao điểm, API vẫn trả 200 nhưng khách hàng báo thiếu email xác nhận; chi phí mạng tăng và đội vận hành chưa từng thử phục hồi dữ liệu.

Hãy xây dựng một hồ sơ kiểm chứng ngắn gồm:

1. **Ba hành trình nghiệp vụ** cần theo dõi và những bất biến cần giữ; ít nhất một hành trình phải đi qua queue/worker.
2. **Năm SLI/guardrail** có định nghĩa phép đo và cửa sổ đánh giá, bao gồm lỗi nghiệp vụ, độ trễ, xử lý nền, dữ liệu và khôi phục.
3. **Một phép đối soát** giữa hệ cũ và hệ mới có mốc nhất quán; chỉ rõ điều kiện để kết luận không mất đơn.
4. **Một kịch bản lỗi** phải diễn tập nhằm chứng minh RTO/RPO và quy trình cảnh báo.
5. **Hai giả thuyết tối ưu** cho chi phí mạng và backlog xử lý email, cùng phép đo để kiểm tra giả thuyết.
6. **Điều kiện GO/PAUSE/ROLLBACK** và cách bảo vệ các ghi mới đã phát sinh nếu phải quay lui.

Gợi ý cách suy nghĩ: “API trả 200” chỉ xác nhận một lớp đồng bộ. Muốn biết email đã gửi, phải theo dõi sự kiện được phát, thời gian nằm trong queue, kết quả worker, lỗi retry/DLQ và trạng thái từ nhà cung cấp email. Chi phí mạng tăng cần được bóc tách thành truyền giữa các vùng, NAT/egress và lưu lượng nội bộ trước khi thay đổi bố trí dịch vụ. Tình trạng chưa thử restore là khoảng trống bằng chứng về khôi phục, cần được đưa vào quyết định go/no-go tương ứng với mức độ quan trọng của dữ liệu.

## 10. Tự rà soát trước khi kết thúc migration

Sử dụng danh sách sau cho buổi bàn giao, đồng thời đính kèm bằng chứng cụ thể thay vì chỉ đánh dấu “đã kiểm tra”:

- [ ] Mỗi hành trình nghiệp vụ quan trọng có người sở hữu, kết quả thử và điều kiện chấp nhận.
- [ ] Dữ liệu đã được đối soát theo mốc nhất quán; các sai lệch được xử lý hoặc phê duyệt.
- [ ] Hiệu năng đã đo ở tải đại diện; kiểm tra được nút cổ chai và khả năng scale.
- [ ] Quyền truy cập, secret, mạng, log và yêu cầu bảo mật được rà soát ở môi trường thực.
- [ ] Backup có thể restore; RTO/RPO được đo cho kịch bản đã thống nhất.
- [ ] SLI, alert, runbook, người trực và quy trình sự cố đã được kiểm chứng.
- [ ] Cutover, guardrail, rollback/roll-forward và quyền ghi dữ liệu được mô tả rõ.
- [ ] Chi phí được phân bổ, có ngưỡng giám sát và phương án tối ưu theo số liệu.
- [ ] Các quyết định kiến trúc và đánh đổi Well-Architected được ghi nhận, có lịch đánh giá lại.
- [ ] Đội tiếp nhận vận hành có đủ quyền, tài liệu, bảng điều khiển và trách nhiệm rõ ràng.

**Điểm cốt lõi:** Chất lượng của một cuộc di chuyển được chứng minh bằng kết quả nghiệp vụ, dữ liệu, khả năng phục hồi và bằng chứng vận hành. Tối ưu kiến trúc là vòng lặp đo lường có mục tiêu: thay đổi một giả thuyết, kiểm chứng tác động lên toàn hệ thống và chấp nhận đánh đổi một cách minh bạch.
