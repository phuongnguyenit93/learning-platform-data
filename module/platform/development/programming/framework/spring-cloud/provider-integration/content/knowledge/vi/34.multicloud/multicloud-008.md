# Đánh giá chi phí di chuyển, độ nhất quán và kế hoạch chuyển đổi

Chuyển một workload Spring Boot sang cloud provider khác là quyết định về kiến trúc và vận hành, đồng thời là quyết định tài chính. Một dịch vụ có giá lưu trữ thấp hơn vẫn có thể làm tổng chi phí tăng nếu phát sinh egress, request, replication, kết nối riêng, vận hành hai nền tảng hoặc công sức chuyển đổi. Tương tự, một đích đến có thông lượng cao nhưng cung cấp mô hình nhất quán khác nguồn có thể làm thay đổi hành vi nghiệp vụ.

Vì vậy, trước khi chọn AWS, Azure hay Google Cloud làm đích, cần trả lời ba câu hỏi: tổng chi phí sở hữu trong khoảng thời gian dự kiến là bao nhiêu; hệ thống cần bảo đảm mức nhất quán nào cho từng loại dữ liệu; và chiến lược chuyển đổi nào đáp ứng được giới hạn downtime, RPO, RTO và rủi ro nghiệp vụ. Các thư viện Spring Cloud giúp ứng dụng tích hợp với dịch vụ managed của từng provider, nhưng không tự giải quyết bài toán kinh tế hoặc làm cho ngữ nghĩa dịch vụ trở nên tương đương.

## Mục tiêu

Sau bài học, bạn có thể:

- Xây dựng mô hình tổng chi phí sở hữu (TCO) cho workload hiện tại, workload đích và giai đoạn chuyển tiếp.
- Ước tính chi phí truyền dữ liệu, chạy song song, đồng bộ thay đổi, kiểm thử và rollback.
- Phân biệt các mức nhất quán và xác định mức cần thiết theo nghiệp vụ.
- Đánh giá ảnh hưởng của replication lag, retry, thứ tự message và dual-write.
- Chọn chiến lược chuyển đổi theo dung lượng, downtime, rủi ro và khả năng quay lui.
- Thiết lập tiêu chí go/no-go có thể đo lường trước khi cutover.

## 1. Đặt bài toán kinh tế đúng phạm vi

Không so sánh riêng giá một VM, một GB lưu trữ hoặc một triệu request. Phải so sánh chi phí để cung cấp cùng một năng lực nghiệp vụ với cùng mức dịch vụ. Nếu workload đích cần thêm replica, cache, gateway, private endpoint hoặc công cụ quan sát để đạt SLO tương đương, các khoản đó phải xuất hiện trong mô hình.

Chọn một khoảng thời gian đánh giá, thường là 12, 24 hoặc 36 tháng tùy chu kỳ ngân sách và hợp đồng. Dùng cùng giả định về tải, tăng trưởng, tính sẵn sàng, retention, backup, vùng triển khai và số người vận hành cho cả nguồn và đích. Tách ba nhóm chi phí:

| Nhóm | Thành phần điển hình | Thời điểm phát sinh |
|---|---|---|
| Chi phí một lần | Phân tích tương thích, thiết kế, viết adapter, migration tool, truyền dữ liệu ban đầu, kiểm thử, đào tạo | Trước và trong migration |
| Chi phí chuyển tiếp | Hai môi trường cùng chạy, replication, egress, đối soát, môi trường kiểm thử, hỗ trợ ngoài giờ | Trong cửa sổ chuyển đổi và rollback |
| Chi phí định kỳ | Compute, storage, database, request, network, backup, observability, support, nhân lực vận hành | Sau cutover |

TCO trong khoảng thời gian đánh giá có thể biểu diễn như sau:

\[
TCO = C_{one\text{-}time} + C_{transition} + \sum_{m=1}^{N} C_{steady,m}
\]

Trong đó (N) là số tháng dự báo. Nếu so sánh với việc tiếp tục chạy trên nguồn, tính cả chi phí nguồn trong cùng kỳ và các khoản tiết kiệm hoặc chi phí tránh được. Không cộng trùng chi phí nguồn: phần nguồn vẫn chạy trong giai đoạn chuyển tiếp thuộc `C_transition`, còn chi phí sau khi ngừng nguồn không còn thuộc steady state của đích.

Ngoài số tiền, ghi nhận các chỉ số hỗ trợ quyết định như thời gian hoàn vốn, chi phí trên một giao dịch, chi phí trên một GB dữ liệu hoạt động, công sức vận hành mỗi tháng và giá trị của việc giảm phụ thuộc nhà cung cấp. Những yếu tố khó quy đổi thành tiền cần được ghi thành lợi ích hoặc rủi ro riêng, tránh ép chúng vào một con số thiếu căn cứ.

## 2. Ước tính các cấu phần chi phí

### 2.1. Compute và nền tảng chạy ứng dụng

Đối với Spring Boot, tính số instance hoặc pod, loại máy, CPU và memory request/limit, autoscaling, thời gian chạy, môi trường dự phòng và chi phí control plane nếu có. Một workload chạy 24/7 có cấu trúc chi phí khác một batch chỉ chạy vài giờ mỗi ngày. So sánh trên cùng tải và cùng SLO; nếu provider đích có hiệu năng mỗi core khác, cần benchmark để điều chỉnh số instance thay vì giữ nguyên cấu hình nguồn.

Tính cả chi phí Kubernetes hoặc nền tảng container, load balancer, NAT gateway, địa chỉ IP, service mesh và các dịch vụ nền cần thiết. Không giả định compute rẻ hơn đồng nghĩa toàn bộ nền tảng rẻ hơn.

### 2.2. Storage và cơ sở dữ liệu

Với object storage, tổng chi phí có thể gồm dung lượng trung bình theo lớp lưu trữ, số request PUT/GET/LIST, truy xuất dữ liệu ở lớp archive, versioning, lifecycle, replication, inventory, mã hóa và egress. Dữ liệu ít truy cập có thể rẻ khi lưu nhưng đắt khi phục hồi hoặc chuyển ra ngoài. Hãy dự báo theo phân bố tần suất truy cập thay vì áp một lớp lưu trữ cho toàn bộ object.

Với database managed, tính compute, storage, IOPS hoặc throughput provisioned, backup, read replica, high availability, license, proxy, kết nối và truyền dữ liệu. Nếu chuyển giữa hai engine, cộng chi phí chuyển schema, sửa truy vấn, kiểm thử tương thích và tối ưu lại index. Một database đích có đơn giá thấp nhưng cần nhiều read replica hoặc compute lớn hơn để đáp ứng latency có thể đắt hơn trong vận hành.

### 2.3. Messaging và tích hợp

Với queue, topic và event bus, tính số operation, kích thước message, số subscription, retention, retry, dead-letter, throughput đã cấp, kết nối và truyền liên vùng. Trong giai đoạn chạy song song, một sự kiện có thể được phát tới cả nguồn và đích hoặc được chuyển tiếp qua bridge; điều này làm tăng số operation và có thể tạo thêm egress.

Ước tính theo lưu lượng thực tế và cả lưu lượng lỗi. Nếu consumer đích chậm, retry và backlog có thể tăng mạnh số lần giao message. Đưa tỷ lệ retry, thời gian retention và tỷ lệ message vào DLQ vào kịch bản tải, thay vì chỉ dùng số message thành công trong ngày bình thường.

### 2.4. Network và truyền dữ liệu

Network thường là khoản bị bỏ sót khi so sánh cloud. Phân loại luồng dữ liệu theo hướng và điểm đến: internet egress, truyền giữa region, truyền giữa zone, kết nối hybrid, traffic qua NAT, private endpoint và traffic giữa các dịch vụ. Giá và cách tính phụ thuộc provider, region, loại kết nối và hợp đồng; phải lấy từ bảng giá hoặc calculator hiện hành tại thời điểm lập ngân sách.

Với một lần truyền dữ liệu ban đầu, công thức ước tính cơ bản là:

\[
C_{transfer} = V_{GB} \times P_{GB} + C_{request} + C_{temporary}
\]

Trong đó (V_{GB}) là lượng dữ liệu thực sự đi qua đường truyền, (P_{GB}) là đơn giá phù hợp với tuyến truyền, `C_request` là chi phí operation nếu có và `C_temporary` là chi phí staging hoặc lưu bản sao tạm. Nếu phải chuyển nhiều đợt, cộng từng đợt và tính lại phần dữ liệu thay đổi. Với nén hoặc lọc dữ liệu, dùng dung lượng thực tế sau biến đổi; không mặc định toàn bộ dữ liệu có thể nén.

Thời gian truyền lý thuyết có thể ước tính:

\[
T_{transfer} \approx \frac{V_{bytes}}{B_{effective}}
\]

`B_effective` là thông lượng thực tế sau khi tính giới hạn mạng, số luồng, mã hóa, giới hạn dịch vụ và thời gian retry. Kết quả lý thuyết chỉ dùng để lập kế hoạch ban đầu; cần đo bằng một mẫu dữ liệu đại diện trước khi cam kết cửa sổ downtime.

Ví dụ, 12 TB dữ liệu truyền với thông lượng hữu dụng trung bình 200 MB/s cần khoảng 16,7 giờ theo phép chia thập phân, chưa tính thời gian kiểm tra, retry, metadata, giới hạn API và phần thay đổi phát sinh trong lúc truyền. Nếu cửa sổ downtime chỉ cho phép hai giờ, không thể đợi đến lúc dừng hệ thống mới bắt đầu sao chép. Cần truyền trước, đồng bộ phần thay đổi và chỉ khóa ghi trong giai đoạn cuối.

### 2.5. Bảo mật, quan sát và hỗ trợ

Tính chi phí secret manager, KMS/Key Vault/Cloud KMS, audit log, security posture, vulnerability scanning, log ingestion, metric, trace, alert và lưu giữ dữ liệu quan sát. Việc bật audit chi tiết hoặc lưu log lâu hơn có thể làm chi phí tăng, nhưng giảm thời gian điều tra và hỗ trợ yêu cầu kiểm toán.

Tính gói support của provider, chi phí dịch vụ chuyên gia migration và thời gian của đội nền tảng, bảo mật, dữ liệu, phát triển và vận hành. Nhân lực nội bộ không miễn phí chỉ vì không có hóa đơn cloud riêng. Ước tính số ngày công theo vai trò, chi phí cơ hội và mức hỗ trợ cần thiết trong cửa sổ cutover.

## 3. Lập bảng tính TCO và phân tích độ nhạy

Một bảng tính có thể chia theo từng dịch vụ và môi trường. Mỗi dòng nên có đơn vị đo, lượng sử dụng, đơn giá, nguồn của đơn giá, giả định và chủ sở hữu xác nhận. Không nhập một con số tổng duy nhất mà không giữ lại các thành phần để có thể điều chỉnh khi tải thay đổi.

| Thành phần | Nguồn hiện tại | Đích sau migration | Giai đoạn song song | Cơ sở ước tính |
|---|---:|---:|---:|---|
| Compute Spring Boot | Giờ instance/pod | Giờ instance/pod | Cả hai môi trường | Tải và SLO |
| Object storage | GB-tháng và request | GB-tháng và request | Bản sao ở cả hai | Dung lượng, lớp lưu trữ, access pattern |
| Database | Compute, GB, IOPS, backup | Compute, GB, IOPS, backup | Nguồn + đích + CDC | Query profile, HA, retention |
| Messaging | Operation, throughput, retention | Operation, throughput, retention | Bridge/dual publish | Message rate, size, retry |
| Network | Egress, NAT, private link | Egress, NAT, private link | Replication và đồng bộ | Byte theo tuyến |
| Security/observability | KMS, secret, log, trace | KMS, secret, log, trace | Audit hai phía | Retention và mức giám sát |
| Nhân lực và hỗ trợ | Vận hành hiện tại | Vận hành đích | Migration/cutover | Ngày công và mức support |

Tạo ít nhất ba kịch bản:

- **Cơ sở:** tải và tốc độ tăng trưởng dự kiến, thời gian chuyển đổi theo kế hoạch, tỷ lệ retry thông thường.
- **Bất lợi:** dữ liệu tăng nhanh, truyền chậm, CDC lag cao, cần kéo dài dual-run, nhiều request bị retry hoặc phải rollback.
- **Thuận lợi:** có thể nén/lọc dữ liệu, cửa sổ chuyển ngắn, workload đích dùng tài nguyên hiệu quả hơn và nguồn được ngừng sớm.

Chạy phân tích độ nhạy cho các biến tác động lớn: dung lượng dữ liệu, egress, thời gian chạy song song, số replica, tỷ lệ tăng trưởng, tỷ lệ cache hit, số operation và retention. Ví dụ, nếu mỗi tuần trì hoãn việc ngừng nguồn làm phát sinh thêm một tuần compute, database, backup và support, khoản chi phí đó cần hiện ra trong mô hình. Xác định biến nào làm TCO thay đổi mạnh nhất để tập trung đo thử trước.

Nếu dùng chiết khấu dòng tiền, quy đổi các khoản phát sinh theo thời điểm và tỷ lệ chiết khấu do bộ phận tài chính cung cấp. Với quyết định kỹ thuật thông thường, một bảng chi phí theo tháng cùng kịch bản có thể đủ; đừng tạo độ chính xác giả khi đơn giá, mức sử dụng hoặc thời gian migration vẫn chưa được xác minh.

## 4. Chọn mức nhất quán phù hợp với nghiệp vụ

Nhất quán mô tả cách các client nhìn thấy dữ liệu sau khi có cập nhật. Không có một mức nhất quán tối ưu cho mọi dữ liệu. Sổ dư tài khoản, trạng thái đơn hàng và cấu hình quyền thường cần bảo đảm mạnh hơn cache, chỉ số phân tích hoặc feed có thể cập nhật trễ.

Một số khái niệm thường gặp:

| Mô hình | Hành vi chính | Ví dụ sử dụng phù hợp |
|---|---|---|
| Strong/linearizable consistency | Sau khi ghi thành công, lần đọc tiếp theo quan sát được giá trị mới theo một thứ tự toàn cục hợp lệ | Trạng thái cần quyết định tức thời, chẳng hạn hạn mức hoặc thao tác cấp phát duy nhất |
| Read-your-writes | Client đọc được thay đổi mà chính client vừa ghi | Trang hồ sơ sau khi người dùng cập nhật thông tin |
| Monotonic reads | Một client không nhìn thấy phiên bản dữ liệu cũ hơn sau khi đã thấy phiên bản mới hơn | Trạng thái phiên hoặc tiến trình nhiều bước |
| Causal consistency | Các thao tác có quan hệ nhân quả được quan sát theo đúng thứ tự | Quy trình tạo bản ghi rồi phát sự kiện liên quan |
| Eventual consistency | Nếu không có cập nhật mới và hệ thống tiếp tục hoạt động, các replica cuối cùng hội tụ | Cache, search index, dữ liệu phân tích hoặc bản đọc phụ |

Các thuật ngữ này mô tả tính chất hệ thống ở những phạm vi khác nhau; tên gọi hoặc mức bảo đảm cụ thể của dịch vụ managed có thể khác. Phải đọc tài liệu của database, storage hoặc broker đích và kiểm tra trong điều kiện lỗi, failover, multi-region. Không suy ra rằng hai dịch vụ có cùng consistency chỉ vì cả hai đều cung cấp API `GET` và `PUT`.

### 4.1. Xác định yêu cầu theo luồng nghiệp vụ

Với mỗi luồng đọc/ghi, ghi rõ:

- Ai là writer có thẩm quyền và có bao nhiêu writer đồng thời?
- Sau khi ghi, client nào cần thấy dữ liệu mới và trong thời gian bao lâu?
- Có cho phép đọc dữ liệu cũ không? Nếu có, cũ tối đa bao lâu?
- Có yêu cầu thứ tự giữa các sự kiện hoặc giữa nhiều bản ghi không?
- Nếu hai nơi ghi cùng một khóa, quy tắc giải quyết xung đột là gì?
- Khi provider hoặc network bị phân vùng, nghiệp vụ ưu tiên tính sẵn sàng hay từ chối ghi để giữ nhất quán?

Chuyển các câu trả lời thành tiêu chí đo được. Ví dụ: sau khi API cập nhật trạng thái đơn hàng trả thành công, API truy vấn trạng thái phải thấy phiên bản mới trong vòng hai giây ở cùng khu vực; consumer phải xử lý sự kiện theo thứ tự trong từng `orderId`; bản sao phân tích được phép trễ tối đa năm phút. Các ngưỡng chỉ là ví dụ, cần được chủ sở hữu nghiệp vụ xác nhận.

### 4.2. Nhất quán trong database và replication

Database primary/replica thường có độ trễ sao chép. Đọc từ replica có thể rẻ hoặc giảm tải primary, nhưng ngay sau khi ghi có thể trả dữ liệu cũ. Nếu nghiệp vụ cần read-your-writes, có thể đọc từ primary trong một khoảng thời gian, dùng session consistency nếu dịch vụ hỗ trợ, hoặc đợi replica đạt watermark đã ghi nhận.

Trong migration bằng CDC, cần phân biệt thời điểm bản ghi được commit ở nguồn với thời điểm thay đổi được áp dụng ở đích. Theo dõi log sequence number (LSN), binlog position hoặc checkpoint tương ứng với engine và công cụ đang dùng. Khi cutover, phải biết đích đã nhận và áp dụng đến vị trí nào; chỉ thấy replication process đang chạy không chứng minh dữ liệu đã bắt kịp.

Schema migration cũng ảnh hưởng consistency. Dùng chiến lược expand-and-contract khi cần tương thích giữa phiên bản cũ và mới: thêm cột hoặc cấu trúc tương thích, triển khai code có thể đọc/ghi theo giai đoạn, backfill dữ liệu, chuyển đọc, rồi mới loại bỏ cấu trúc cũ sau thời gian an toàn. Tránh thay đổi schema phá vỡ tương thích khi nguồn và đích cùng chạy.

### 4.3. Nhất quán trong event và messaging

Phần lớn hệ thống message phân tán cung cấp giao nhận at-least-once hoặc có khả năng giao lại trong một số tình huống. Vì vậy, consumer cần idempotent. Không coi một cấu hình “exactly-once” ở một dịch vụ là bảo đảm giao dịch nghiệp vụ xuyên qua database, broker và API bên ngoài.

Đặt event ID duy nhất, lưu dấu vết xử lý cùng transaction nghiệp vụ khi có thể, và dùng Transactional Outbox để tránh tình trạng database commit nhưng message không được phát. Consumer có thể dùng Inbox hoặc bảng processed-event để bỏ qua event đã áp dụng. Nếu cần thứ tự, xác định partition key hoặc session theo aggregate như `orderId`; không dựa vào thứ tự toàn cục nếu broker không cam kết điều đó.

Khi chuyển broker, một message có thể đã được xử lý ở nguồn nhưng được replay sang đích. Cần có chính sách deduplication xuyên suốt thời gian chuyển, đủ lâu hơn thời hạn retry và replay. Đối soát số message đã nhận không thay thế đối soát kết quả nghiệp vụ.

## 5. Các chiến lược chuyển đổi và đánh đổi

Không có một chiến lược migration phù hợp với mọi workload. Chọn phương án dựa trên kích thước dữ liệu, khả năng tương thích, downtime tối đa, mức chấp nhận chạy song song và khả năng quay lui.

| Chiến lược | Cách thực hiện | Ưu điểm | Chi phí/rủi ro |
|---|---|---|---|
| Big-bang/offline | Dừng ghi, sao chép dữ liệu, kiểm tra rồi khởi động ở đích | Quy trình đơn giản, tránh đồng bộ song song kéo dài | Downtime lớn; cửa sổ chuyển phụ thuộc tốc độ truyền và kiểm tra |
| Online migration với CDC | Tải ban đầu, đồng bộ thay đổi liên tục, khóa ghi ngắn ở cuối | Giảm downtime, có checkpoint để đối soát | Tốn chi phí replication và vận hành; phải xử lý schema và lag |
| Blue-green | Dựng môi trường đích đầy đủ, kiểm thử rồi chuyển traffic | Có thể chuyển traffic nhanh và kiểm soát theo đợt | Tốn chi phí hai môi trường; dữ liệu và write sau chuyển cần kế hoạch riêng |
| Canary | Chuyển một phần traffic hoặc một nhóm tenant trước | Giới hạn phạm vi ảnh hưởng, quan sát hành vi thực tế | Phải phân tuyến nhất quán; dữ liệu dùng chung có thể làm kết quả khó cô lập |
| Strangler/phased | Chuyển từng capability hoặc service theo ranh giới nghiệp vụ | Chia nhỏ rủi ro, ưu tiên phần có lợi ích cao | Thời gian dài, tồn tại nhiều provider và lớp định tuyến |
| Shadow read | Gửi bản đọc phụ tới đích để so sánh kết quả, không trả kết quả phụ cho user | Kiểm tra tương thích trên tải thực | Tăng read cost và tải; phải loại bỏ side effect và dữ liệu nhạy cảm không cần thiết |

Blue-green mô tả cách duy trì hai phiên bản môi trường, còn canary mô tả cách phân phối traffic. Có thể kết hợp chúng. CDC là kỹ thuật đồng bộ dữ liệu, không phải một chiến lược traffic độc lập; nó thường được dùng cùng blue-green hoặc phased migration.

### 5.1. Khi nào chọn từng cách

Big-bang có thể hợp lý với ứng dụng nhỏ, dữ liệu ít, thời gian dừng được chấp nhận và có bản backup đã kiểm thử. Online migration phù hợp khi dữ liệu lớn hoặc downtime thấp, nhưng chỉ khi công cụ hỗ trợ engine và topology, đội vận hành hiểu checkpoint và có khả năng đối soát.

Phased migration phù hợp khi hệ thống có ranh giới nghiệp vụ rõ, chẳng hạn chuyển kho tài liệu trước rồi mới chuyển messaging. Cần giữ hợp đồng API và quy tắc ownership rõ ràng giữa hai phía. Nếu một giao dịch nghiệp vụ ghi vào nhiều capability ở hai provider, độ trễ và lỗi một phần sẽ làm thiết kế phức tạp hơn.

Shadow read hữu ích để so sánh kết quả đọc, nhưng không được phát sinh hành động phụ như tạo object, gửi email, trừ tiền hoặc ghi message. Với dữ liệu có tính riêng tư, chỉ sao chép phần tối thiểu cần kiểm thử và tuân thủ chính sách truy cập, lưu giữ.

## 6. Quản lý consistency trong thời gian chạy song song

Giai đoạn dual-run thường là phần tốn kém và khó kiểm soát nhất. Cần xác định rõ “dual-run” đang nói tới chạy hai bản ứng dụng, đọc từ hai nơi hay ghi vào hai nơi. Ba trường hợp này có rủi ro rất khác nhau.

- **Hai bản ứng dụng cùng chạy, một nơi ghi:** có thể an toàn nếu chỉ một môi trường được phép xử lý write hoặc có cơ chế phân quyền writer rõ ràng.
- **Shadow read từ hai nơi:** dùng để so sánh kết quả; đích không được gây side effect. So sánh phải chuẩn hóa thứ tự, timestamp, trường mặc định và sai khác được chấp nhận.
- **Dual-write vào hai nơi:** dễ tạo trạng thái một bên thành công, bên kia thất bại. Chỉ sử dụng khi có cơ chế giải quyết xung đột, idempotency, retry, reconciliation và quy tắc chọn nguồn có thẩm quyền.

Mẫu an toàn hơn cho nhiều hệ thống là single-writer: tại một thời điểm chỉ một provider nhận write có thẩm quyền. Có thể dùng fencing token hoặc epoch tăng dần để ngăn instance cũ tiếp tục ghi sau khi quyền writer đã chuyển. Chỉ đổi biến môi trường hoặc DNS chưa đủ làm hàng rào writer vì process cũ có thể vẫn giữ connection và credential.

Nếu phải đồng bộ thay đổi, ghi nhận watermark/checkpoint. Mỗi bản ghi hoặc event cần thông tin định danh và phiên bản để xác định thay đổi nào đã được áp dụng. Khi hai phiên bản cùng cập nhật một entity, dùng optimistic locking/version hoặc quy tắc nghiệp vụ xác định; không tự động chọn timestamp mới hơn nếu đồng hồ không đồng bộ hoặc thứ tự thời gian không phản ánh quan hệ nhân quả.

## 7. Kế hoạch chuyển đổi theo các cổng kiểm soát

Một kế hoạch thực thi nên có chủ sở hữu, thời gian, lệnh/automation, tín hiệu quan sát và tiêu chí hoàn tất cho từng bước. Dưới đây là trình tự tham khảo cho migration online.

### Giai đoạn A – Khám phá và baseline

1. Lập inventory dịch vụ, dữ liệu, phụ thuộc, credential, endpoint và luồng network.
2. Đo baseline: request rate, latency, error rate, database load, message lag, chi phí tháng và tăng trưởng dữ liệu.
3. Xác nhận yêu cầu consistency, RPO/RTO, SLO, retention và cửa sổ downtime với chủ sở hữu nghiệp vụ.
4. Kiểm tra khả năng tương thích của database engine, SDK, Spring Boot, Spring Cloud và runtime.
5. Lập mô hình TCO ba kịch bản và phê duyệt ngân sách migration/dual-run.

### Giai đoạn B – Dựng và kiểm thử đích

1. Tạo tài nguyên đích, network, private endpoint, role, secret, key và backup.
2. Cấu hình adapter/provider trong Spring Boot qua profile hoặc cấu hình triển khai.
3. Chạy kiểm thử kết nối, quyền, TLS, quota và latency từ đúng runtime.
4. Chạy kiểm thử hợp đồng cho storage, database và messaging; kiểm thử lỗi timeout, throttling và credential hết hạn.
5. Chạy thử truyền một tập dữ liệu đại diện, đo thông lượng, chi phí và khả năng đối soát.

### Giai đoạn C – Đồng bộ và diễn tập

1. Chạy tải dữ liệu ban đầu và bật CDC hoặc đồng bộ tăng dần.
2. Theo dõi lag, checkpoint, retry, DLQ, checksum và chi phí egress.
3. Thực hiện shadow read hoặc canary trong phạm vi có thể kiểm soát.
4. Diễn tập cutover và rollback bằng dữ liệu/traffic thử nghiệm; đo thời gian thực tế.
5. Chốt runbook, người trực, kênh liên lạc và quyền thao tác trong cửa sổ chuyển đổi.

### Giai đoạn D – Cutover

1. Xác nhận go/no-go dựa trên các tiêu chí đã phê duyệt.
2. Thông báo cửa sổ thay đổi và bật chế độ bảo vệ phù hợp, ví dụ hạn chế thao tác quản trị hoặc tạm dừng batch.
3. Dừng producer hoặc khóa write ở nguồn; hoàn tất các giao dịch đang chạy và drain consumer theo kế hoạch.
4. Ghi lại watermark cuối ở nguồn; đợi đích áp dụng đến watermark và xác minh không còn lag ngoài ngưỡng.
5. Chạy đối soát dữ liệu và kiểm tra các invariant nghiệp vụ.
6. Chuyển fencing token/ownership của writer sang đích, sau đó chuyển traffic bằng gateway, feature flag hoặc DNS.
7. Bật canary, quan sát các chỉ số và mở rộng traffic khi đạt tiêu chí.

### Giai đoạn E – Ổn định và kết thúc

1. Theo dõi lỗi, latency, throughput, lag, retry, DLQ, quota, bảo mật và chi phí trong cửa sổ đã định.
2. Xác nhận backup và thử khôi phục từ đích.
3. Xử lý sai lệch còn lại bằng reconciliation có audit trail.
4. Kết thúc replication và ngừng tài nguyên nguồn sau khi hết cửa sổ rollback và được chủ sở hữu dữ liệu chấp thuận.
5. Cập nhật runbook, sơ đồ kiến trúc, dashboard, dự toán và phân công vận hành.

## 8. Tiêu chí go/no-go và rollback

Không quyết định cutover chỉ dựa vào việc ứng dụng đích khởi động thành công. Cần các cổng kiểm soát định lượng và người có quyền dừng thay đổi.

| Nhóm | Ví dụ tiêu chí go | Điều kiện no-go |
|---|---|---|
| Dữ liệu | Checksum và số lượng trong ngưỡng; mọi sai lệch có giải thích | Có bản ghi quan trọng thiếu hoặc sai chưa xử lý |
| Replication | Lag thấp hơn ngưỡng và đích đã áp dụng watermark cuối | Checkpoint chưa bắt kịp hoặc CDC lỗi không rõ nguyên nhân |
| Consistency | Các invariant nghiệp vụ và read-after-write test đạt | Có thể đọc dữ liệu cũ vượt mức nghiệp vụ cho phép |
| Bảo mật | Workload dùng đúng principal, quyền tối thiểu, secret và TLS hợp lệ | Còn credential tĩnh không kiểm soát hoặc quyền vượt phạm vi |
| Hiệu năng | p95/p99, throughput và error rate trong SLO | Đích throttling hoặc latency vượt ngưỡng đã duyệt |
| Khôi phục | Backup restore và rollback rehearsal đạt thời gian mục tiêu | Không bảo toàn được write phát sinh sau chuyển |
| Chi phí | Dự báo dual-run và steady-state trong ngân sách | Egress, replica hoặc support vượt giới hạn chưa có phê duyệt |

Rollback phải xét dữ liệu đã ghi sau cutover. Nếu chưa có write ở đích, có thể chuyển traffic về nguồn sau khi xác nhận nguồn còn nhất quán. Nếu đích đã nhận write, phải đồng bộ ngược, phát lại log/outbox hoặc thực hiện reconciliation trước khi cho nguồn nhận write. Nếu không thể bảo toàn các thay đổi đó, phương án phù hợp có thể là roll-forward: sửa lỗi ở đích và giữ writer tại đích thay vì chuyển ngược một cách mù quáng.

Đặt thời hạn rõ cho cửa sổ rollback và xác định điều kiện kết thúc. Càng kéo dài dual-run, chi phí hai nền tảng, độ phức tạp quyền truy cập và nguy cơ lệch dữ liệu càng tăng. Nhưng ngừng nguồn quá sớm sẽ làm mất phương án phục hồi. Thời hạn cần dựa trên mức rủi ro và bằng chứng ổn định, không dựa vào cảm giác.

## 9. Ví dụ: đánh giá chuyển dịch vụ đơn hàng sang cloud đích

Giả sử một hệ thống Spring Boot xử lý đơn hàng dùng PostgreSQL managed, object storage và message broker. Dữ liệu database có dung lượng 2 TB, kho tài liệu 12 TB, lưu lượng 1.500 request/giây ở giờ cao điểm. Hệ thống cần downtime tối đa 15 phút, RPO gần bằng 0 cho đơn hàng đã xác nhận và cho phép chỉ số phân tích trễ tối đa năm phút.

**Đánh giá consistency.** Bảng đơn hàng và thanh toán cần một writer có thẩm quyền, transaction ACID và cơ chế chống xử lý trùng. Consumer phải idempotent theo event ID và giữ thứ tự theo `orderId` nếu quy trình nghiệp vụ yêu cầu. Search index và báo cáo có thể dùng eventual consistency với giới hạn trễ năm phút. Không cần buộc mọi dữ liệu phụ phải dùng mức nhất quán mạnh nếu nghiệp vụ không yêu cầu.

**Đánh giá chiến lược.** Sao chép 12 TB object trước bằng công cụ truyền dữ liệu chuyên dụng, sau đó đồng bộ thay đổi. Database dùng tải ban đầu cộng CDC nếu engine và topology hỗ trợ. Broker được chuyển bằng bridge hoặc phát lại event có event ID; trước cutover phải drain backlog hoặc xác nhận cách replay. Dùng blue-green cho runtime và canary cho traffic, đồng thời giữ single-writer.

**Đánh giá chi phí.** TCO gồm compute và database ở nguồn/đích trong giai đoạn song song, chi phí object ở cả hai nơi, truyền 12 TB ban đầu và phần thay đổi, CDC, message bridge, egress, backup, KMS, observability, support và nhân lực trực cutover. Mô hình cần thêm kịch bản cửa sổ rollback kéo dài một tuần và kịch bản phải truyền lại một phần dữ liệu. Đơn giá phải lấy theo region và hợp đồng thực tế; ví dụ này không giả định một mức giá cloud cụ thể.

**Go/no-go.** Chỉ chuyển writer khi CDC đã áp dụng tới watermark cuối, kiểm tra đơn hàng và thanh toán không có sai lệch, consumer đích không tạo duplicate side effect, latency đạt SLO và phương án bảo toàn write sau cutover đã được diễn tập. Nếu replication lag vượt ngưỡng hoặc kiểm thử rollback không bảo toàn được giao dịch mới, hoãn cutover.

Ví dụ cho thấy mức nhất quán có thể khác nhau theo loại dữ liệu, chiến lược có thể kết hợp CDC với blue-green/canary, và chi phí migration phải bao gồm cả khoảng thời gian hai môi trường cùng tồn tại.

## 10. Tích hợp các quyết định vào ứng dụng Spring Boot

Đưa lựa chọn provider và chế độ migration vào cấu hình có kiểm soát. Ví dụ:

```yaml
app:
  migration:
    mode: ${MIGRATION_MODE:source}
    write-owner: ${WRITE_OWNER:source}
    epoch: ${WRITE_EPOCH:1}
  consistency:
    order-read-after-write: primary
    analytics-max-lag: 5m
```

Đây là cấu hình minh họa cho ứng dụng. Cần bảo vệ `write-owner` và `epoch` bằng cơ chế điều phối có thẩm quyền; không để mỗi instance tự quyết định độc lập. Có thể dùng feature flag hoặc control plane để đổi chế độ, nhưng phải bảo đảm các instance nhận cùng trạng thái và writer cũ bị fencing.

Một cổng nghiệp vụ giúp cô lập client của provider:

```java
public interface OrderRepository {
    Order findById(OrderId id);
    Order save(Order order);
}

public interface EventPublisher {
    void publish(OrderEvent event);
}
```

Adapter database và messaging chịu trách nhiệm kết nối dịch vụ managed tương ứng. Service nghiệp vụ giữ invariant như kiểm tra trạng thái đơn hàng và chống cập nhật trùng. Dùng Transactional Outbox khi cần bảo đảm thay đổi đơn hàng và sự kiện được ghi nhận cùng transaction; một publisher riêng gửi outbox tới broker và đánh dấu checkpoint sau khi được xác nhận.

Không tạo abstraction giả định mọi provider hỗ trợ cùng transaction hoặc cùng consistency. Hãy biểu diễn rõ các capability mà nghiệp vụ cần, kiểm thử contract trên từng adapter và kiểm thử tích hợp với dịch vụ thật hoặc môi trường tương thích. Đặc biệt kiểm thử failover, timeout, retry, stale read, duplicate delivery và quyền bị thu hồi.

## 11. Lỗi đánh giá thường gặp

| Sai lầm | Hệ quả | Cách khắc phục |
|---|---|---|
| So sánh đơn giá compute hoặc storage | Bỏ sót network, backup, request và nhân lực | So sánh TCO theo cùng tải và SLO |
| Bỏ qua thời gian dual-run | Ngân sách thiếu chi phí hai môi trường | Lập kịch bản chuyển tiếp và thời hạn rollback |
| Dùng ETag hoặc số object làm bằng chứng duy nhất | Có thể bỏ sót nội dung hoặc metadata sai | Dùng checksum phù hợp và đối soát thuộc tính nghiệp vụ |
| Giả định replica luôn đọc được bản ghi vừa ghi | Request có thể trả dữ liệu cũ | Xác định read-your-writes và chính sách đọc primary/replica |
| Dual-write không có idempotency | Tạo giao dịch hoặc side effect trùng | Single-writer, outbox/inbox và reconciliation |
| Coi DNS switch là rollback đầy đủ | Writer cũ hoặc connection cũ vẫn có thể hoạt động | Fencing writer, quản lý connection và đồng bộ write mới |
| Chỉ diễn tập đường đi thành công | Không biết xử lý khi CDC, DNS hoặc provider lỗi | Diễn tập rollback, retry, failover và phục hồi dữ liệu |
| Dùng giá cloud cũ trong ngân sách | Ước tính sai theo region/hợp đồng | Lưu nguồn và ngày lấy đơn giá, cập nhật trước phê duyệt |

## 12. Checklist trước khi phê duyệt migration

- [ ] TCO so sánh nguồn, đích và giai đoạn song song trong cùng khoảng thời gian.
- [ ] Đơn giá có nguồn, ngày cập nhật, region, đơn vị và giả định sử dụng.
- [ ] Đã tính egress, replication, request, backup, security, observability, support và nhân lực.
- [ ] Có kịch bản cơ sở, bất lợi và thuận lợi; xác định biến nhạy cảm nhất.
- [ ] Mỗi luồng dữ liệu có yêu cầu consistency, thứ tự, RPO/RTO và độ trễ cho phép.
- [ ] Có một writer có thẩm quyền và cơ chế fencing khi chuyển ownership.
- [ ] CDC hoặc công cụ đồng bộ có checkpoint, giám sát lag và quy trình reconciliation.
- [ ] Consumer idempotent; event có ID; dead-letter và replay được kiểm soát.
- [ ] Chiến lược migration phù hợp với downtime, dung lượng và khả năng tương thích.
- [ ] Cutover có go/no-go định lượng, người chịu trách nhiệm và cửa sổ giám sát.
- [ ] Rollback bảo toàn được write sau cutover hoặc có quyết định roll-forward rõ ràng.
- [ ] Backup restore, runbook và phương án liên lạc đã được diễn tập.
- [ ] Có thời hạn kết thúc dual-run và điều kiện ngừng tài nguyên nguồn.

Một quyết định chuyển đổi tốt cần chứng minh được cả ba mặt: chi phí toàn vòng đời nằm trong giới hạn, dữ liệu giữ đúng mức nhất quán mà nghiệp vụ cần và quy trình chuyển đổi có thể dừng hoặc phục hồi khi tiêu chí không đạt. Khi các giả định được đo, ghi nhận và kiểm chứng, đội dự án có thể lựa chọn provider và thời điểm migration dựa trên bằng chứng thay vì chỉ dựa vào đơn giá dịch vụ hoặc kỳ vọng về nền tảng mới.
