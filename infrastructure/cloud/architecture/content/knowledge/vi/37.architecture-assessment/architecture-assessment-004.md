# Proof of concept để kiểm chứng giả định rủi ro cao

## 1. Vì sao cần PoC khi đánh giá kiến trúc đám mây?

Trong **CLOUD_ARCHITECTURE**, thiết kế ứng dụng đám mây bắt đầu từ yêu cầu nghiệp vụ rồi mới lựa chọn mạng, compute, dữ liệu và cách triển khai. Một sơ đồ hợp lý trên giấy chưa đủ chứng minh rằng ứng dụng có thể đạt độ tin cậy, bảo mật, hiệu năng, khả năng mở rộng, chi phí và mục tiêu vận hành mong muốn.

**Proof of concept (PoC)** là một thử nghiệm có phạm vi và thời gian giới hạn, được thiết kế để thu thập **bằng chứng cho một hoặc vài giả định kiến trúc còn nhiều bất định**. Giá trị của PoC không nằm ở việc dựng một hệ thống trông giống sản phẩm, mà ở khả năng khiến nhóm kiến trúc đưa ra quyết định tốt hơn: tiếp tục, điều chỉnh, chọn phương án khác hoặc dừng.

Ví dụ: nhóm đề xuất đưa API lên dịch vụ container managed, nhưng vẫn giữ cơ sở dữ liệu giao dịch tại trung tâm dữ liệu cũ. Giả định “độ trễ xuyên mạng không đáng kể” có thể chi phối thành công của toàn bộ kế hoạch. Một PoC đo thời gian xử lý giao dịch thực qua kết nối hybrid dưới tải đỉnh sẽ hữu ích hơn việc xây toàn bộ giao diện người dùng của ứng dụng mới.

Kết thúc bài, bạn có thể:

- Nhận diện những giả định **tác động lớn, chưa có bằng chứng** trong kiến trúc đích.
- Viết giả thuyết có thể bác bỏ, chỉ số kiểm chứng và ngưỡng chấp nhận rõ ràng.
- Thiết kế thí nghiệm có baseline, dữ liệu đại diện, cấu hình kiểm soát và khả năng tái lập.
- Đọc kết quả PoC đúng giới hạn, tránh nhầm một lần thử thành chứng nhận sẵn sàng production.
- Lập hồ sơ quyết định kiến trúc có truy vết từ yêu cầu đến dữ liệu thử nghiệm và bước tiếp theo.

## 2. Phân biệt PoC với những hoạt động gần giống

| Hoạt động | Câu hỏi chính | Đầu ra ưu tiên | Dấu hiệu hoàn tất |
| --- | --- | --- | --- |
| Khảo sát / discovery | Hệ thống hiện tại là gì, có phụ thuộc nào? | Inventory, dependency map, yêu cầu | Đã nhận diện đối tượng và khoảng trống thông tin quan trọng |
| Technical spike | Công nghệ này hoạt động ra sao, API sử dụng thế nào? | Kiến thức, mẫu mã nhỏ, bài học | Đủ hiểu để ước lượng hoặc chọn hướng nghiên cứu |
| **PoC** | Giả định rủi ro cao này có đúng trong điều kiện mục tiêu? | Dữ liệu đo, kết luận đạt/không đạt/chưa đủ bằng chứng | Đủ bằng chứng để quyết định có điều kiện |
| Prototype | Trải nghiệm hoặc thiết kế tương tác có phù hợp? | Bản mẫu để thảo luận/thử với người dùng | Giải đáp câu hỏi về cách dùng, luồng nghiệp vụ |
| MVP | Sản phẩm tối thiểu có tạo giá trị với người dùng thật? | Chức năng đưa vào sử dụng có kiểm soát | Đo được phản hồi và giá trị |
| Pilot | Phương án gần production có hoạt động trong vận hành thực tế? | Kết quả thử nghiệm quy trình, con người, hệ thống | Đạt cổng chấp nhận để mở rộng triển khai |

Một PoC có thể được triển khai bằng một vài thành phần thật, nhưng không mặc định phải có đầy đủ tính năng, HA, CI/CD, autoscaling hay quy trình phát hành chuẩn production. **Những thuộc tính đang được kiểm chứng phải đủ thật để kết quả có ý nghĩa**. Nếu PoC nhằm chứng minh failover, không thể bỏ qua cấu hình đa vùng sẵn sàng chỉ vì muốn làm nhanh.

## 3. Chọn đúng giả định có rủi ro cao

### 3.1. Bắt đầu từ quyết định cần đưa ra

Đừng bắt đầu bằng “thử công nghệ X cho biết”. Trước tiên xác định **quyết định kiến trúc đang bị chặn bởi điều gì chưa biết**:

- Có nên giữ CSDL on-premises khi đưa API lên cloud không?
- CSDL managed có tương thích giao dịch, extension và tải đỉnh hiện tại không?
- Container autoscaling có tăng đủ nhanh khi lượng truy cập tăng gấp ba?
- Mã hóa và truy cập dữ liệu có đáp ứng điều kiện bắt buộc của tổ chức không?
- Khả năng khôi phục có đạt RTO/RPO sau khi mất một vùng sẵn sàng không?
- Lưu trữ đối tượng kết hợp CDN có đáp ứng độ trễ và chi phí truyền dữ liệu mong đợi không?

Mỗi câu hỏi đều kết nối với một **mục tiêu nghiệp vụ hoặc yêu cầu phi chức năng (NFR)**. Nếu chưa biết tác động khi giả định sai, chưa đủ cơ sở để ưu tiên nó.

### 3.2. Lập danh sách và xếp hạng bất định

Có thể dùng một cách chấm đơn giản để sắp xếp thảo luận:

- **Tác động (I):** 1 = nhỏ, 5 = có thể làm thất bại mục tiêu chính.
- **Mức chưa chắc chắn (U):** 1 = đã có dữ liệu phù hợp, 5 = gần như chưa có bằng chứng.
- **Mức lan rộng (E):** 1 = ảnh hưởng một phần nhỏ, 5 = ảnh hưởng nhiều workload/khách hàng.

**Điểm ưu tiên thăm dò = I × U × E** (từ 1 đến 125). Đây là **thang điểm định tính**, không phải công thức tính xác suất thất bại. Yêu cầu pháp lý hoặc an toàn có thể là cổng bắt buộc, cần giải quyết bất kể điểm.

| Giả định | I | U | E | Điểm | Cách kiểm chứng phù hợp |
| --- | ---: | ---: | ---: | ---: | --- |
| Kết nối hybrid đủ nhanh cho giao dịch đồng bộ | 5 | 4 | 5 | 100 | PoC tải và đo latency đầu cuối |
| CSDL managed tương thích truy vấn/extension | 5 | 4 | 4 | 80 | PoC di chuyển schema, chạy SQL thật |
| Autoscaling đáp ứng tải đột biến | 4 | 3 | 4 | 48 | PoC tăng tải có quan sát scale-out |
| Định dạng log được đội vận hành truy vấn thuận tiện | 2 | 2 | 2 | 8 | Spike hoặc dùng công cụ sẵn có |

Ngoài điểm, ước lượng **chi phí để học được câu trả lời** và **khả năng đổi quyết định**. Nếu hai giả định cùng tác động lớn, ưu tiên giả định có thể kiểm chứng nhanh và có thể khiến nhóm đổi phương án. Đừng dùng PoC tốn kém để tái khám phá một sự thật đã được chứng minh bằng tài liệu và phép thử sát điều kiện của mình.

### 3.3. Chọn phạm vi thử

Một PoC tốt thường kiểm chứng một rủi ro chính và một số điều kiện cần thiết đi kèm. Chẳng hạn, thử latency hybrid nên có đường truyền, hệ quản trị dữ liệu, tỷ lệ read/write và cách triển khai API gần thực tế, nhưng không cần đầy đủ trang quản trị hoặc thiết kế mỹ thuật.

Có thể dùng nguyên tắc: **nếu bỏ thành phần này thì kết luận có thay đổi hoặc mất giá trị không?** Nếu không, cân nhắc loại khỏi PoC.

## 4. Viết giả thuyết có thể bác bỏ

Một tuyên bố mơ hồ như “dịch vụ managed đủ nhanh” không cho biết kết quả nào là đạt.

Hãy ghi theo mẫu:

> **Với** khối lượng và kiến trúc được mô tả, **khi** xảy ra điều kiện thử X, **thì** chỉ số Y phải đạt ngưỡng Z trong khoảng thời gian T; **nếu không**, cần xem xét phương án thay thế.

Ví dụ:

**H1 – Hiệu năng:** Với 180 yêu cầu/giây và tỷ lệ 70% đọc, 30% ghi trong 20 phút, API đặt hàng chạy trên container cloud và truy cập CSDL qua kết nối hybrid đạt **p95 latency không quá 300 ms**, **tỷ lệ lỗi dưới 0,5%** và **không làm rơi lượt thử phát sinh do thiếu tài nguyên load generator**.

**H2 – Khả năng phục hồi:** Với cấu hình CSDL managed đã dự kiến, khi chủ động thực hiện failover theo kịch bản đã phê duyệt, dịch vụ khôi phục thao tác tạo đơn trong **20 phút**, và mất dữ liệu được đo theo giao dịch xác nhận thành công không vượt quá **5 phút**.

**H3 – Bảo mật:** Với luồng truy cập đã xác định, người dùng không được cấp quyền không thể đọc bảng giao dịch; mọi truy cập nhạy cảm cần được ghi lại theo chính sách, kể cả khi thành phần ứng dụng khởi động lại.

Trước khi chạy, định nghĩa rõ:

| Thành phần | Câu hỏi phải trả lời |
| --- | --- |
| Giả thuyết | Mệnh đề nào đang có thể sai? |
| Quyết định | Nếu đạt/không đạt, lựa chọn kiến trúc thay đổi thế nào? |
| Biến tác động | Tải, kích thước dữ liệu, vị trí mạng, cấu hình, tình huống lỗi? |
| Biến quan sát | Latency, error rate, lag, RTO/RPO, chi phí, log kiểm toán? |
| Ngưỡng | Mức đạt, mức không đạt, vùng cần thử thêm là gì? |
| Bằng chứng | Nguồn dữ liệu, thời điểm, phương pháp và tệp kết quả nào? |
| Giới hạn | Yếu tố nào PoC chưa thử hoặc chỉ mô phỏng? |
| Người quyết định | Ai phê duyệt tiêu chí và diễn giải kết quả? |

**Giả thuyết phải có khả năng thất bại.** Nếu mọi kết quả đều có thể được diễn giải là “công nghệ khả thi”, thiết kế thử nghiệm chưa đủ sắc nét.

## 5. Thiết kế thí nghiệm có đối chứng và tính đại diện

### 5.1. Phác họa chuỗi nguyên nhân cần kiểm chứng

Giả sử đang kiểm chứng độ trễ của phương án đưa API lên cloud nhưng giữ dữ liệu tại chỗ:

~~~mermaid
flowchart LR
    C[Load generator] --> G[Ingress / Load balancer]
    G --> API[API trên cloud]
    API --> NET[Kết nối hybrid]
    NET --> DB[(CSDL on-prem)]
    API --> OBS[Logs / Metrics / Traces]
    NET --> OBS
    DB --> OBS
~~~

Trong phép thử, cần quan sát cả độ trễ API từ phía client và các thành phần con như thời gian DNS, TLS, kết nối DB, truy vấn, hàng đợi kết nối, retry. Nếu chỉ có p95 cuối cùng, nhóm sẽ biết phương án thất bại nhưng khó xác định **vì sao**.

### 5.2. Baseline, biến thể và đối chứng

Giữ một **baseline** đại diện cho kiến trúc hiện có hoặc mức dịch vụ đang hoạt động, rồi so sánh với một hay nhiều lựa chọn:

| Nhóm | API | CSDL | Mục đích |
| --- | --- | --- | --- |
| Baseline | On-premises | On-premises | Đo mức hiện tại dưới tải tương đương |
| A | Container managed trên cloud | On-premises qua hybrid | Kiểm tra giả định network và runtime |
| B | Container managed trên cloud | Managed DB trên cloud | Kiểm tra phương án giảm network hop |

So sánh chỉ có ý nghĩa khi môi trường, dữ liệu, workload và cách đo tương đương. Nếu B nhanh hơn vì được cấp máy lớn gấp bốn, chưa thể khẳng định nguyên nhân là do kiến trúc dữ liệu.

### 5.3. Dữ liệu và tải phải giống những điểm có thể gây lỗi

Một mô hình kiểm thử cần nêu:

- **Dữ liệu:** dung lượng, phân phối giá trị, index, tỷ lệ hot key, khóa ngoại, kích thước bản ghi, tỷ lệ truy vấn nặng. Có thể tạo dữ liệu giả tổng hợp theo phân bố thực tế; tránh sao chép dữ liệu nhạy cảm trái chính sách.
- **Workload:** hành trình nghiệp vụ, tỷ lệ đọc/ghi, phiên, truy vấn đồng thời, batch và tác vụ nền.
- **Mức tải:** trung bình, tải đỉnh, tăng tải đột ngột, tải kéo dài và giai đoạn giảm tải.
- **Môi trường:** region/zone, loại compute, cấu hình DB, phiên bản runtime, subnet, DNS, phương thức kết nối.
- **Vị trí đặt công cụ tải:** phù hợp với người dùng hoặc đường đi mạng mục tiêu; load generator không được trở thành nút nghẽn.
- **Độ dài chạy:** đủ khởi động cache/JIT/connection pool, đạt trạng thái ổn định và quan sát autoscaling; có nhiều lần chạy khi cần đánh giá biến thiên.
- **Nhiễu:** thông báo triển khai khác, thay đổi quota, dịch vụ cùng chia sẻ tài nguyên, giới hạn tài khoản, cache đã nóng hay lạnh.

**Không dùng dữ liệu quá nhỏ để suy ra hiệu năng ở quy mô dữ liệu lớn** nếu câu hỏi liên quan đến index, phân vùng, khóa, compaction hoặc thời gian restore. Có thể bắt đầu nhỏ để phát hiện lỗi sớm rồi tăng đến kích thước có giá trị đối với giả thuyết.

### 5.4. Khống chế sai số đo

- Đồng bộ mốc thời gian và dùng công cụ đo đầu cuối ở phía client.
- Báo cáo p50, p95, p99 khi phù hợp; không dùng latency trung bình che giấu đuôi phân phối.
- Ghi cả số yêu cầu hoàn tất, yêu cầu thất bại, yêu cầu bị bỏ khi generator thiếu capacity và các lần retry.
- Đo nhiều lần hoặc nhiều khoảng thời gian, lưu biến thiên và thông tin cấu hình thay vì chỉ chọn lần đẹp nhất.
- Phân biệt **thời gian phản hồi ở client** với thời gian xử lý bên trong dịch vụ.
- Theo dõi bão hòa CPU, RAM, connection pool, IOPS, throughput, queue depth và giới hạn dịch vụ.
- Với phép thử so sánh chi phí, phải kiểm soát sự khác biệt tài nguyên và bao gồm thành phần tính phí liên quan.

## 6. Liên kết PoC với các trụ cột Well-Architected

Một PoC không nhất thiết kiểm chứng tất cả trụ cột cùng lúc, nhưng quyết định phải nêu tác động và khoảng trống theo các góc nhìn sau. Tên trụ cột và hướng dẫn chi tiết có thể khác giữa các cloud provider.

| Góc nhìn | Giả định rủi ro thường gặp | Kiểu thử nghiệm và bằng chứng |
| --- | --- | --- |
| **Operational excellence – Vận hành** | Nhóm có thể phát hiện, triển khai và xử lý sự cố? | Triển khai bằng IaC, diễn tập rollback, bảng cảnh báo, runbook |
| **Security – Bảo mật** | Phân quyền và kiểm soát dữ liệu hoạt động như thiết kế? | Thử truy cập bị từ chối, kiểm tra mã hóa, secrets, audit trail |
| **Reliability – Độ tin cậy** | Hệ thống chịu được lỗi instance, zone, kết nối? | Fault injection có giới hạn, failover, backup/restore, đo RTO/RPO |
| **Performance efficiency – Hiệu năng** | Đủ throughput và latency ở tải mục tiêu? | Load test, stress test, scale-out, kiểm tra bottleneck |
| **Cost optimization – Chi phí** | Chi phí vận hành phù hợp ngân sách dưới tải thực? | Đo resource-hours, lưu trữ, request, network egress, dự báo TCO |
| **Sustainability – Bền vững** | Tài nguyên có thể được sử dụng hiệu quả? | Right-sizing, idle capacity, autoscaling, vòng đời dữ liệu |

Bảo mật và tuân thủ có thể chứa **hard gate**: một kết quả tốt về latency không cho phép bỏ qua yêu cầu lưu trú dữ liệu hoặc quyền truy cập bắt buộc.

## 7. Định nghĩa chỉ số, ngưỡng và cách kết luận

### 7.1. Các chỉ số nên chọn theo giả thuyết

| Nhóm | Chỉ số gợi ý | Lưu ý diễn giải |
| --- | --- | --- |
| Hiệu năng | Throughput, p50/p95/p99 latency, timeout, error rate | Đo từ góc nhìn người dùng và ở tải xác định |
| Mở rộng | Thời gian scale-out, độ trễ trong spike, queue depth, backlog | Cần đo cả tốc độ xử lý backlog sau spike |
| Dữ liệu | Replication lag, chênh lệch bản ghi, lỗi đối soát, transaction consistency | Lag nhỏ chưa chứng minh mọi giao dịch đúng |
| Tin cậy | Thời gian phát hiện, RTO thực nghiệm, mất dữ liệu/RPO thực nghiệm | Định nghĩa mốc sự cố và mốc khôi phục trước thử |
| Bảo mật | Số trường hợp truy cập trái phép thành công, coverage audit, secrets lộ trong log | Thành công của kiểm tra âm tính là bị từ chối đúng cách |
| Vận hành | Thời gian triển khai, khôi phục phiên bản, thời gian chẩn đoán | Ghi cả thao tác thủ công còn lại |
| Chi phí | Chi phí theo giờ chạy, trên giao dịch, egress, backup, giám sát | Phân biệt chi phí PoC với chi phí dự báo production |

**Tỷ lệ lỗi** = số yêu cầu được xác định là lỗi / tổng yêu cầu được phát ra trong tập đo tương ứng. Cần định nghĩa trước lỗi nghiệp vụ khác gì lỗi hạ tầng và cách xử lý retry.

**RTO thực nghiệm** = thời điểm dịch vụ đáp ứng trở lại tiêu chí tối thiểu đã định − thời điểm bắt đầu sự cố. **Mất dữ liệu thực tế** cần đo dựa trên giao dịch đã được xác nhận thành công trước sự cố và trạng thái khôi phục, không chỉ dựa trên cấu hình replication.

**Chi phí trên 1.000 giao dịch** = tổng chi phí được quy cho workload trong kỳ / số giao dịch thành công × 1.000. Phải mô tả rõ khoản tính vào tử số: compute, CSDL, storage, truyền dữ liệu, backup, monitoring, dịch vụ dùng chung và mức phân bổ. Không suy giá production từ một phiên chạy ngắn chỉ vài phút khi còn idle, chi phí cố định hoặc cam kết sử dụng.

### 7.2. Ví dụ tiêu chí kết luận

| Kết luận | Khi nào dùng | Quyết định đi kèm |
| --- | --- | --- |
| **Đạt trong phạm vi thử** | Mọi tiêu chí đã định cho giả thuyết được đáp ứng với bằng chứng hợp lệ | Tiếp tục bước pilot hoặc thiết kế chi tiết, còn các cổng khác |
| **Không đạt** | Một hoặc nhiều tiêu chí thiết yếu thất bại trong phép thử hợp lệ | Đổi thiết kế hoặc phương án; chỉ chạy lại nếu có thay đổi |
| **Chưa đủ bằng chứng** | Kịch bản thiếu đại diện, sai số lớn, công cụ tải nghẽn, thiếu số liệu | Bổ sung đo hoặc thiết kế lại thử nghiệm |
| **Dừng vì rủi ro** | Có tín hiệu vi phạm an toàn, ngân sách, ảnh hưởng hệ thật | Dừng thử, cô lập môi trường và xử lý rủi ro |

Không thay ngưỡng sau khi nhìn kết quả chỉ để ghi “đạt”. Nếu mục tiêu nghiệp vụ thật sự thay đổi, ghi phiên bản tiêu chí mới, lý do và thực hiện lại phép đánh giá tương ứng.

## 8. Quy trình xây dựng và chạy PoC

~~~mermaid
flowchart TD
    A[Quyết định bị chặn bởi bất định] --> B[Ưu tiên giả định rủi ro cao]
    B --> C[Viết giả thuyết và ngưỡng]
    C --> D[Thiết kế kịch bản, baseline, dữ liệu]
    D --> E[Xây môi trường thử có kiểm soát]
    E --> F[Đo baseline và biến thể]
    F --> G{Bằng chứng đủ tin cậy?}
    G -- Chưa --> H[Kiểm tra nhiễu / cải tiến phép đo]
    H --> F
    G -- Có --> I{Giả thuyết đạt?}
    I -- Đạt --> J[Đề xuất pilot và hard gates]
    I -- Không --> K[Chọn hướng khác hoặc sửa thiết kế]
    J --> L[ADR và backlog bước tiếp]
    K --> L
~~~

### Bước 1: Chốt quyết định, ngân sách và thời hạn

Ghi người bảo trợ nghiệp vụ, người có quyền quyết định kiến trúc, giới hạn thời gian và chi phí. Chọn số giả thuyết ít nhưng quan trọng. Định nghĩa **stop condition**: khi vượt ngân sách, gây ảnh hưởng hệ dùng chung, phát hiện rủi ro bảo mật hoặc đã đủ bằng chứng để bác bỏ giả thuyết.

### Bước 2: Chuẩn bị thiết kế thử

Tạo **test plan** với ma trận điều kiện thử, tải, dữ liệu, ngưỡng và cách đo. Chọn baseline tương đương. Định nghĩa trước cách tái lập: phiên bản mã, ảnh container, cấu hình IaC, seed dữ liệu, lệnh triển khai và vị trí lưu kết quả.

### Bước 3: Dựng môi trường tối thiểu an toàn

Thiết lập tài khoản/project thử tách khỏi production, quyền tối thiểu, mã hóa, quản lý secrets, cấu hình mạng hạn chế truy cập, ngân sách/cảnh báo và người sở hữu tài nguyên. Dùng dữ liệu tổng hợp hoặc dữ liệu đã được xử lý theo chính sách. Với fault injection, xác nhận blast radius và phương án dừng tức thì.

**IaC có ích** vì giúp tạo lại đúng cấu hình và giảm khác biệt giữa các lần thử. Sau PoC cần dọn hạ tầng và dữ liệu theo chính sách; lưu lại dữ liệu đo, cấu hình và quyết định cần truy vết.

### Bước 4: Chạy thử sơ bộ để kiểm tra công cụ

Chạy tải nhỏ để xác minh instrument, log, đường đi mạng, dữ liệu test và độ chính xác thống kê. Nếu generator không tạo nổi tải đã định, phải sửa cách tạo tải trước khi kết luận hệ thống tốt hay xấu.

### Bước 5: Chạy baseline và các biến thể

Dùng kịch bản giống nhau, ghi nhận thời điểm, cấu hình, version và sự kiện ngoại lai. Thứ tự chạy có thể ảnh hưởng cache và tải dùng chung; nếu có thể, lặp lại theo thứ tự cân bằng và phân biệt cold/warm start.

### Bước 6: Phân tích và ra quyết định

Đối chiếu ngưỡng đã xác định, tìm nguyên nhân của sai lệch, xem rủi ro còn lại và các trụ cột chưa kiểm chứng. Kết luận phải có một trong ba trạng thái **đạt, không đạt, chưa đủ bằng chứng**, cùng hành động cụ thể.

## 9. Ví dụ triển khai kịch bản kiểm tra hiệu năng

Một phép thử giả định dùng công cụ sinh tải có thể cấu hình như sau. Đây là **mẫu ý tưởng cho API đọc đã có trong môi trường thử**, chưa đại diện cho toàn bộ hành trình đặt hàng đọc/ghi.

~~~javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    peak_read: {
      executor: 'constant-arrival-rate',
      rate: 180,
      timeUnit: '1s',
      duration: '20m',
      preAllocatedVUs: 150,
      maxVUs: 500,
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<300'],
    http_req_failed: ['rate<0.005'],
    dropped_iterations: ['count==0'],
  },
};

export default function () {
  const url = __ENV.API_URL + '/api/orders/seeded-read';
  const response = http.get(url, {
    headers: { 'X-Test-Run': 'architecture-poc' },
  });
  check(response, {
    'HTTP 200': (r) => r.status === 200,
  });
}
~~~

Cần khai báo **API_URL** trỏ đến môi trường thử, bảo đảm endpoint phù hợp với application fixture và không đặt bí mật trong mã. Đường dẫn **/api/orders/seeded-read** là placeholder, phải thay bằng endpoint đọc đã tồn tại trong hệ thống thử.

Để kiểm chứng H1 ở phần 4, phải **bổ sung các kịch bản ghi thật trên dữ liệu thử** với tỷ lệ 70/30, payload và logic nghiệp vụ đại diện; nếu chỉ chạy đoạn mã đọc ở trên, **chưa đủ** kết luận H1. Cần bổ sung metrics cho ứng dụng, kết nối DB, độ trễ mạng và lỗi nghiệp vụ. Không dùng tài khoản hoặc giao dịch thanh toán thật để tạo tải.

## 10. Tình huống xuyên suốt: chọn cách đặt CSDL khi di chuyển API

### 10.1. Bối cảnh

Một doanh nghiệp đang đánh giá kiến trúc đích cho dịch vụ đặt hàng:

- API hiện chạy trên máy ảo tại trung tâm dữ liệu nội bộ, truy cập CSDL quan hệ.
- Nhóm muốn triển khai API lên container managed để giảm khối lượng vận hành và thuận tiện mở rộng.
- Hai phương án đang xét: **A** giữ CSDL tại chỗ qua kết nối hybrid và **B** di chuyển sang CSDL managed trong cloud.
- Yêu cầu giả định: tải đỉnh **180 yêu cầu/giây**, khoảng **70% đọc/30% ghi**, p95 không vượt **300 ms**, tỷ lệ lỗi dưới **0,5%**. Mục tiêu khôi phục hệ thống là **RTO ≤ 20 phút** và **RPO ≤ 5 phút** ở kịch bản đã định.

Yêu cầu này chỉ là ví dụ học tập. Trong dự án thật, các ngưỡng phải do chủ sở hữu nghiệp vụ chấp thuận theo SLO và mức tổn thất có thể chấp nhận.

### 10.2. Thiết kế phép thử

~~~mermaid
flowchart TB
    L[Load generator theo giao dịch mẫu] --> S{Phương án}
    S --> A[API trên cloud - A]
    S --> B[API trên cloud - B]
    A --> N[Hybrid connection]
    N --> D1[(CSDL tại chỗ)]
    B --> D2[(Managed DB trên cloud)]
    A --> O[Telemetry / Trace]
    B --> O
    D1 --> O
    D2 --> O
~~~

Thiết lập cùng version API và bộ giao dịch. Sao chép cấu trúc và dữ liệu tổng hợp có phân phối, chỉ mục, kích thước gần với môi trường mục tiêu. Chạy ít nhất một lượt tải ổn định, một lượt tăng tải và một lượt thử sự cố liên quan đến rủi ro chính. Ghi riêng những khác biệt không thể kiểm soát hoàn toàn như loại đĩa, nhân bản dữ liệu và trạng thái cache.

**Giả thuyết quan trọng**:

- **H1:** A đạt ngưỡng hiệu năng ở 180 yêu cầu/giây.
- **H2:** B đạt ngưỡng hiệu năng ở cùng tải.
- **H3:** B đạt RTO/RPO trong phép diễn tập failover có xác nhận giao dịch.
- **H4:** B đáp ứng yêu cầu kiểm soát truy cập, nhật ký và vị trí lưu dữ liệu.

### 10.3. Kết quả minh họa, không phải số đo thực tế

Giả sử ba lượt đo cùng điều kiện tạo ra kết quả tổng hợp đại diện dưới đây:

| Chỉ số | Baseline nội bộ | A – API cloud + DB tại chỗ | B – API + managed DB cloud | Tiêu chí |
| --- | ---: | ---: | ---: | --- |
| p95 ở 180 req/s | 210 ms | **410 ms** | **240 ms** | ≤ 300 ms |
| p99 ở 180 req/s | 390 ms | 880 ms | 420 ms | Theo dõi xu hướng |
| Tỷ lệ lỗi | 0,2% | 0,4% | 0,2% | Dưới 0,5% |
| RTO khi failover DB | Chưa thử | Chưa thử | 12 phút | ≤ 20 phút |
| RPO thực nghiệm | Chưa thử | Chưa thử | 30 giây | ≤ 5 phút |
| Đối soát giao dịch của tập thử | Khớp | Khớp | Khớp | Không có sai khác chưa giải thích |
| Audit / yêu cầu vị trí dữ liệu | Cần rà soát | Cần rà soát | **Chưa đủ bằng chứng** | Hard gate |

**Diễn giải**:

1. **H1 không đạt** vì p95 của A vượt ngưỡng. Trace giả định cho thấy gọi CSDL đồng bộ nhiều lượt qua hybrid làm tăng tổng latency; nhóm cần kiểm tra thêm bằng breakdown truy vấn, không được khẳng định chắc nguyên nhân từ con số p95 đơn lẻ.
2. **H2 đạt trong điều kiện đo**: B thỏa p95 và tỷ lệ lỗi ở tải mục tiêu. Chưa được kết luận B sẽ đạt mọi tải hoặc mọi khu vực người dùng.
3. **H3 đạt trong một kịch bản diễn tập**, nhưng cần kiểm chứng các kiểu lỗi khác, dữ liệu lớn hơn hoặc điều kiện vận hành thực khi thực hiện pilot.
4. **H4 chưa đủ bằng chứng**, nên B chưa được xem là đủ điều kiện go-live cho đến khi đánh giá bảo mật và tuân thủ hoàn tất.

**Quyết định có điều kiện:** không ưu tiên A ở kiến trúc hiện tại; đưa B vào thiết kế chi tiết và pilot nếu đáp ứng hard gate, kết quả kiểm thử dữ liệu, chi phí và quy trình vận hành. Lưu A như lựa chọn cần tái thiết kế nếu doanh nghiệp bắt buộc giữ dữ liệu tại chỗ, chẳng hạn giảm số round-trip hoặc thay giao tiếp đồng bộ bằng cơ chế phù hợp với tính nhất quán nghiệp vụ.

### 10.4. Nếu kết quả “đẹp” nhưng kết luận vẫn sai?

Giả sử B chạy nhanh vì tập dữ liệu chỉ có 5.000 bản ghi và cache luôn nóng, trong khi production có hàng trăm triệu bản ghi, truy vấn khóa và batch cuối ngày. Khi đó kết quả chưa đủ đại diện. Quyết định hợp lý là mở rộng dữ liệu thử hoặc thu hẹp phạm vi kết luận thành “đạt với bộ dữ liệu nhỏ”, không mặc nhiên khẳng định production sẽ đạt.

## 11. Đánh giá rủi ro còn lại và cổng chuyển tiếp

Một PoC hiếm khi giảm rủi ro về 0. Cần chỉ rõ **đã chứng minh điều gì, chưa chứng minh điều gì, hậu quả nếu giả định tiếp tục sai**.

| Giả định đã thử | Rủi ro còn lại | Hành động tiếp theo | Người chịu trách nhiệm |
| --- | --- | --- | --- |
| P95 đủ tốt ở tải đỉnh | Chưa thử flash crowd 3× và batch giờ cao điểm | Stress test và kiểm tra quota/autoscaling | Application + Platform lead |
| Failover DB trong 12 phút | Chưa thử mất đường kết nối mạng và lỗi logic | Diễn tập thêm và kiểm tra backup/restore | DBA + SRE |
| Dữ liệu thử khớp | Chưa đối chiếu tất cả extension, collation, edge case giao dịch | Migration rehearsal trên dữ liệu đã xử lý an toàn | DBA + Data owner |
| Bảo mật chưa hoàn tất | IAM, audit, residency có thể chưa đáp ứng | Threat modeling và review security/compliance | Security + Legal/Compliance |
| Chi phí chấp nhận được trong PoC | Chưa tính egress, backup, vận hành song song, cam kết | Dự báo TCO theo kịch bản 1–3 năm | FinOps + Architect |

Để chuyển sang pilot hoặc triển khai, tổ chức có thể yêu cầu **cổng**: có chủ sở hữu nghiệp vụ; đủ tài liệu mạng và dữ liệu; kiểm tra IAM, mã hóa, audit; restore đã thử; có cảnh báo và runbook; chi phí nằm trong giới hạn; có kế hoạch cutover/rollback hoặc forward-fix cho dữ liệu. Ngưỡng và thẩm quyền phê duyệt phải được thiết lập theo độ quan trọng của workload.

## 12. Báo cáo kết quả PoC để người khác kiểm tra được

Bản báo cáo ngắn nhưng có bằng chứng thường hữu ích hơn nhiều ảnh chụp dashboard không giải thích. Một biểu mẫu có thể dùng lại:

~~~yaml
poc:
  id: POC-ARCH-004
  decision: "Giữ CSDL tại chỗ hay chuyển cùng API lên cloud?"
  owner: "Architecture lead"
  reviewed_by: ["Application owner", "DBA", "Security", "Operations"]
  hypothesis:
    id: H1
    statement: "Phương án A đạt p95 <= 300 ms ở 180 req/s"
    business_reason: "Đáp ứng SLO tạo đơn trong giờ cao điểm"
  scope:
    workload: "70% read / 30% write"
    data: "Synthetic data with representative distribution"
    environment: "Container cloud to database over hybrid link"
  acceptance:
    p95_ms_max: 300
    error_rate_max: 0.005
    dropped_iterations_max: 0
  evidence:
    run_id: "run-001"
    config_version: "git-sha-or-release-id"
    dashboard: "internal-evidence-link"
    raw_results: "internal-artifact-path"
  conclusion: "FAIL"
  limitation: "Chưa thử gián đoạn liên kết hybrid"
  decision_next: "Đánh giá phương án B và giảm round-trip"
~~~

Nội dung trên là mẫu dữ liệu, không phải kết quả của một hệ thống thật. Đường dẫn và định danh cần thay bằng nơi lưu hồ sơ thực tế có phân quyền phù hợp.

Một báo cáo hoàn chỉnh nên trả lời:

- **Vì sao thử:** yêu cầu nào và quyết định nào đang bị chặn?
- **Thử gì:** sơ đồ, giả thuyết, điều kiện, dữ liệu, cấu hình, phiên bản.
- **Đo thế nào:** công cụ, phía đo, thời lượng, số lần lặp, độ tin cậy của mẫu.
- **Thấy gì:** số liệu thô hoặc liên kết tới bằng chứng, ngưỡng, sai lệch và bất thường.
- **Kết luận gì:** đạt, không đạt hoặc chưa đủ; phạm vi áp dụng và điều chưa biết.
- **Quyết định nào:** chọn/tạm loại phương án, công việc còn lại, người duyệt và thời điểm rà soát.

Có thể ghi quyết định bằng **Architecture Decision Record (ADR)**: bối cảnh, các lựa chọn, chứng cứ, quyết định, hệ quả và điều kiện xem xét lại. Một ADR có thể dẫn tới nhiều PoC; mỗi PoC nên trỏ ngược về ADR để người đọc hiểu mục đích.

## 13. Những sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách khắc phục |
| --- | --- | --- |
| “Xây thử cho biết” mà không có giả thuyết | Không có tiêu chí kết thúc hoặc quyết định | Viết câu hỏi có thể bác bỏ và ngưỡng trước khi dựng |
| PoC quá rộng, giống xây sản phẩm mới | Tăng thời gian và chi phí, loãng trọng tâm | Cắt phạm vi theo rủi ro đang cần kiểm chứng |
| Chỉ demo happy path với dữ liệu nhỏ | Che giấu bottleneck, lỗi giao dịch và sự cố | Dùng dữ liệu, tải và edge case đại diện |
| Không có baseline hoặc đổi nhiều biến cùng lúc | Không biết cải thiện/hồi quy do đâu | Giữ điều kiện đối chứng và nhật ký cấu hình |
| Nhìn average latency, bỏ qua p95/p99 | Không thấy trải nghiệm chậm của một nhóm giao dịch | Ghi phân phối latency và tỷ lệ lỗi |
| Công cụ sinh tải bị nghẽn | Đo nhầm giới hạn công cụ thành giới hạn hệ thống | Theo dõi dropped iterations và nguồn lực của generator |
| Thử failover nhưng chỉ nhìn trạng thái máy | Không biết dịch vụ, giao dịch và dữ liệu đã khôi phục chưa | Đo khả năng phục vụ và đối soát giao dịch |
| Chỉ thử hiệu năng, bỏ qua bảo mật | Phương án nhanh có thể không được phép triển khai | Áp dụng hard gate và review tuân thủ |
| Nhận thành công của PoC là phê duyệt production | Bỏ sót vận hành, dữ liệu, chi phí và các kiểu lỗi khác | Chuyển tiếp qua pilot, rehearsal và go/no-go |
| Không lưu cấu hình và kết quả | Người khác không thể kiểm chứng hoặc tái lập | Lưu script, seed, IaC, run ID, metrics, ADR |
| Để tài nguyên thử chạy sau khi xong | Phát sinh chi phí và rủi ro dữ liệu | Có owner, budget, TTL và checklist dọn dẹp |

## 14. Bài thực hành: thiết kế PoC từ đầu đến quyết định

**Bối cảnh:** Một nền tảng thương mại điện tử muốn xử lý chiến dịch gấp **4 lần lưu lượng bình thường** bằng autoscaling container và hàng đợi. Nhóm đề xuất một hàng đợi managed nhưng chưa biết liệu consumer có xử lý kịp backlog trong 10 phút sau đợt tăng tải và có gây ghi đơn trùng hay không.

Hãy lập **PoC one-page** gồm:

1. Quyết định kiến trúc bị chặn, rủi ro nếu sai và giả thuyết có thể bác bỏ.
2. Khối lượng nền, đỉnh, thời gian spike, kích thước thông điệp và tỷ lệ lỗi giả lập.
3. Sơ đồ producer – queue – consumer – database và điểm đo telemetry.
4. Tiêu chí đạt cho backlog, thời gian tiêu thụ, số đơn trùng, tỷ lệ lỗi, chi phí.
5. Ba kịch bản: tải thường, spike 4×, consumer bị dừng rồi phục hồi.
6. Cách tạo dữ liệu tổng hợp, idempotency key, cơ chế đối soát và quy tắc xử lý retry.
7. Quyết định nếu kết quả đạt, không đạt hoặc chưa đủ dữ liệu.
8. Các điều kiện còn cần xác minh trước khi mở pilot/production.

**Gợi ý:** Không thể đánh giá “backlog hết trong 10 phút” nếu chưa định nghĩa mốc bắt đầu và kết thúc spike, tốc độ producer, tốc độ consumer và tiêu chí backlog về ngưỡng nào. Đừng xem queue báo rỗng là bằng chứng không mất hoặc không nhân bản đơn; cần đối chiếu danh sách giao dịch có định danh duy nhất với kết quả trong CSDL. Nếu đạt tại 4× nhưng không đạt khi một consumer ngừng, cần ghi rõ phạm vi kết luận và cân nhắc sửa mức tài nguyên, batch/acknowledge, retry, dead-letter queue hoặc thiết kế idempotent.

## 15. Checklist trước khi công bố kết quả

- [ ] Giả thuyết gắn với yêu cầu hoặc quyết định kiến trúc cụ thể.
- [ ] Có ngưỡng đạt/không đạt, điều kiện dừng và người xác nhận.
- [ ] Có baseline, dữ liệu, tải, môi trường và những giới hạn được ghi rõ.
- [ ] Mỗi lần chạy có mã phiên bản, cấu hình, thời gian và kết quả gốc.
- [ ] Công cụ đo đủ năng lực và các nguồn nhiễu quan trọng đã được ghi lại.
- [ ] Bằng chứng bao phủ tình huống làm giả định rủi ro cao có thể sai.
- [ ] Đã xem xét tác động bảo mật, độ tin cậy, vận hành, chi phí và mở rộng.
- [ ] Kết luận không vượt quá điều đã thử.
- [ ] Rủi ro còn lại, hard gates và nhiệm vụ tiếp theo có chủ sở hữu.
- [ ] Quyết định được ghi vào ADR hoặc hồ sơ đánh giá kiến trúc.

**Nguyên tắc cốt lõi:** PoC tốt nhất không phải là PoC “luôn thành công”, mà là PoC giúp **giảm bất định có ý nghĩa** trước khi tổ chức cam kết chi phí và rủi ro lớn. Với kiến trúc đám mây, một kết luận “giả định này sai” có bằng chứng vẫn là kết quả giá trị: nó giúp sửa thiết kế khi còn rẻ và an toàn để thay đổi.
