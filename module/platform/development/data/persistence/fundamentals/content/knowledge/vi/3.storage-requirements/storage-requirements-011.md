# Lập tiêu chí lựa chọn kho dữ liệu từ nhu cầu thực tế

Trong chương **Yêu cầu lưu trữ** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**, nhiệm vụ quan trọng không phải chọn ngay một sản phẩm cơ sở dữ liệu quen thuộc, mà là chuyển nhu cầu của ứng dụng thành **bộ tiêu chí có thể kiểm chứng**. Bộ tiêu chí đó dẫn dắt việc chọn mô hình dữ liệu, lược đồ, truy vấn, chỉ mục, giao dịch, mức cô lập, kiểm soát đồng thời và ranh giới persistence trong Java. Nó còn quyết định khả năng xử lý lỗi kết nối, tiến hóa schema, bảo mật, sao lưu, khôi phục và tối ưu hiệu năng.

Một hệ thống đặt vé có thể cần xác nhận một chỗ ngồi duy nhất trong vài trăm mili giây, lưu lịch sử thanh toán nhiều năm, tìm kiếm sự kiện theo từ khóa và phân tích doanh thu theo ngày. Các công việc này cùng liên quan đến dữ liệu nhưng có **đặc tính tải và cam kết khác nhau**. Ép tất cả vào một loại kho dữ liệu chỉ vì muốn “đơn giản hóa kiến trúc” có thể dẫn đến sai lệch dữ liệu, nghẽn truy vấn hoặc chi phí vận hành cao.

Sau bài học, người học có thể:

- Chuyển mô tả nghiệp vụ thành yêu cầu cụ thể về tính đúng đắn, hình dạng truy vấn, quy mô, độ trễ, khả dụng và khôi phục.
- Phân biệt **điều kiện bắt buộc** với **tiêu chí để tối ưu/đánh đổi**; xây dựng ma trận lựa chọn có trọng số và bằng chứng.
- So sánh kho quan hệ, tài liệu, khóa–giá trị, tìm kiếm, dữ liệu phân tích và các kho chuyên dụng trong đúng ngữ cảnh.
- Thiết kế thử nghiệm chứng minh lựa chọn bằng workload thật, bao gồm lỗi mạng, ghi cạnh tranh, tăng trưởng dữ liệu và phục hồi.
- Ghi lại quyết định kiến trúc cùng giả định, rủi ro và ngưỡng cần đánh giá lại.

## 1. “Kho dữ liệu” ở đây có nghĩa gì?

Trong bài này, **kho dữ liệu (data store)** là thành phần lưu giữ dữ liệu phục vụ ứng dụng: database quan hệ, document database, key–value store, hệ tìm kiếm, kho phân tích, time-series database hoặc object storage. **Data warehouse** chỉ là một nhóm kho dữ liệu chuyên về phân tích, không phải tên gọi chung cho mọi nơi lưu trữ.

Cần xác định vai trò của mỗi kho trước khi so sánh:

| Vai trò | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| **Nguồn có thẩm quyền** | Quyết định trạng thái nghiệp vụ đúng và thực hiện các lệnh ghi hợp lệ | Đơn đặt vé, số chỗ còn lại, giao dịch thanh toán |
| **Mô hình đọc** | Truy vấn nhanh theo nhu cầu hiển thị; có thể tái dựng từ nguồn | Danh sách sự kiện đang mở bán, hồ sơ công khai |
| **Cache** | Giảm độ trễ và tải truy vấn | Danh sách chương trình nổi bật trong thời gian ngắn |
| **Kho phân tích** | Tổng hợp dữ liệu lịch sử và đo lường xu hướng | Số vé bán theo giờ, doanh thu theo kênh |
| **Backup/archive** | Khôi phục hoặc giữ lịch sử theo chính sách | Bản sao nhất quán, WAL lưu trữ, tệp lưu lâu dài |

Một sản phẩm có thể đảm nhận nhiều vai trò, nhưng **vai trò không tự biến đổi theo công nghệ**. Một read replica không tự trở thành bản sao lưu có lịch sử; một cache có cơ chế persistence không mặc nhiên thích hợp làm nguồn chuẩn cho mọi giao dịch; một warehouse tính tổng tốt không nhất thiết đáp ứng luồng đặt chỗ có tranh chấp cao.

## 2. Bắt đầu từ hành vi nghiệp vụ, không bắt đầu từ sản phẩm

Hãy mô tả các hành động thật của người dùng và những gì xảy ra khi hệ thống sai. Ví dụ nền tảng đặt vé:

1. Người dùng mở trang tìm kiếm sự kiện theo thành phố, thời gian và từ khóa.
2. Người dùng chọn ghế, hệ thống giữ chỗ trong một khoảng thời gian.
3. Hệ thống nhận kết quả thanh toán; đơn chuyển sang trạng thái đã xác nhận khi đủ điều kiện.
4. Nhân viên xem báo cáo tổng số vé đã bán theo địa điểm, sự kiện và thời gian.
5. Khi một giao dịch không rõ kết quả do mất kết nối, bộ phận hỗ trợ cần đối soát được.

Mỗi bước phải được làm rõ bằng **dữ liệu, mẫu truy cập, hệ quả khi sai và chỉ số chấp nhận**:

| Nghiệp vụ | Mẫu dữ liệu và truy cập | Tính đúng đắn cần bảo vệ | Đặc điểm thường gặp |
| --- | --- | --- | --- |
| Giữ ghế | Đọc/ghi theo `event_id`, `seat_id`; nhiều người cạnh tranh cùng một ghế | Không có hai giữ chỗ đang hiệu lực cho cùng một ghế | Giao dịch ngắn, đồng thời cao, ghi có điều kiện |
| Thanh toán | Tra theo `payment_id`/mã ngoài; đổi trạng thái và lưu dấu vết | Không xử lý cùng kết quả thanh toán thành hai tác động | Idempotency, audit, lỗi commit không rõ kết quả |
| Tìm kiếm sự kiện | Lọc đa điều kiện, sắp xếp, có thể tìm toàn văn | Dữ liệu trình bày đúng theo mức độ mới đã công bố | Chủ yếu đọc; có thể chấp nhận trễ |
| Trang “vé của tôi” | Tra đơn theo `customer_id` và phân trang | Sau khi thanh toán, trạng thái hiển thị không đánh lừa khách | Đọc chọn lọc, đôi khi cần read-your-writes |
| Báo cáo bán vé | Quét lịch sử, JOIN, GROUP BY theo nhiều chiều | Không đếm trùng và định nghĩa metric thống nhất | Truy vấn phân tích, dữ liệu lớn, chấp nhận trễ có giới hạn |

Từ bảng này có thể thấy **không có một yêu cầu độ trễ hoặc nhất quán duy nhất cho cả hệ thống**. Đối với việc giữ ghế, quyết định đúng tại nơi ghi quan trọng hơn một bản cache rất nhanh. Đối với tìm kiếm, truy vấn nhanh và chỉ mục văn bản có thể quan trọng hơn giao dịch nhiều hàng. Đối với dashboard, độ mới dữ liệu và chất lượng chỉ số quan trọng hơn khả năng UPDATE một hàng trong vài mili giây.

### 2.1. Đặt câu hỏi trước khi ghi yêu cầu

- Ai hoặc hệ thống nào được phép tạo, sửa, xóa và truy vấn dữ liệu? Dữ liệu nào là nguồn có thẩm quyền?
- Luồng nào không thể chấp nhận trạng thái cũ? Luồng nào chấp nhận dữ liệu chậm vài giây hoặc vài phút?
- Khóa truy vấn chính, bộ lọc, cách sắp xếp, số kết quả trả về và kiểu JOIN thực tế là gì?
- Có cập nhật cạnh tranh vào cùng đối tượng không? Quy tắc nào phải đúng ngay cả khi nhiều request đến cùng lúc?
- Dữ liệu hiện có bao nhiêu, tăng nhanh cỡ nào, giữ bao lâu và bao nhiêu phần trăm là “nóng”?
- Khi kết nối bị cắt đúng lúc commit, thao tác được gửi lại sẽ ra sao?
- Mất một máy, một vùng hoặc xóa nhầm dữ liệu gây hậu quả gì? RPO/RTO được yêu cầu thế nào?
- Nhóm vận hành có kinh nghiệm, ngân sách, chính sách bảo mật và giới hạn triển khai nào?

Khi chưa trả lời được, ghi rõ **giả định cần kiểm chứng**. Không biến giả định thành thông số kỹ thuật đã được chấp nhận.

## 3. Viết yêu cầu có thể đo và kiểm tra được

Các câu như “truy vấn nhanh”, “không bao giờ mất dữ liệu”, “hỗ trợ nhiều người dùng” chưa đủ để so sánh công nghệ. Một yêu cầu tốt có **phạm vi, ngưỡng, điều kiện tải, cách đo và người chấp nhận**.

Ví dụ dưới đây là **bộ số liệu giả định để luyện lập yêu cầu**, không phải chuẩn chung cho mọi ứng dụng:

| ID | Yêu cầu có thể kiểm chứng | Đối tượng kiểm tra | Mức ưu tiên |
| --- | --- | --- | --- |
| R1 | Không xác nhận hai giữ chỗ còn hiệu lực cho cùng ghế khi có 500 yêu cầu đồng thời tranh chấp | Kiểm thử cạnh tranh và đối soát ràng buộc | Bắt buộc |
| R2 | API giữ ghế đạt p95 không quá 250 ms và p99 không quá 700 ms tại 300 request/s, trên dữ liệu và phần cứng mục tiêu | Load test end-to-end | Mục tiêu quan trọng |
| R3 | Có định danh yêu cầu để nhận diện retry; không tạo thêm giữ chỗ sau khi client mất phản hồi commit | Kiểm thử ngắt mạng và gửi lại cùng request ID | Bắt buộc |
| R4 | Trang kết quả tìm kiếm cập nhật thay đổi đã xác nhận trong vòng 60 giây ở ít nhất 99% sự kiện | Theo dõi lag end-to-end | Mục tiêu |
| R5 | Báo cáo 12 tháng hoàn thành trong 10 giây ở p95 với 20 truy vấn đồng thời | Benchmark truy vấn phân tích | Mục tiêu |
| R6 | Dữ liệu giao dịch đạt RPO không quá 5 phút và RTO không quá 45 phút trước sự cố đã định nghĩa | Diễn tập mất cụm và restore | Bắt buộc |
| R7 | Dữ liệu khách hàng và thanh toán tuân thủ quyền truy cập tối thiểu, mã hóa và quy định lưu trữ áp dụng | Rà soát quyền, cấu hình và quy trình | Bắt buộc |
| R8 | Có thể triển khai thay đổi schema tương thích trong thời gian hai phiên bản ứng dụng cùng chạy | Thử expand–migrate–contract | Quan trọng |

**p95** là mức mà 95% phép đo nằm ở hoặc dưới ngưỡng, không phải thời gian trung bình. Để so sánh công bằng, phải xác định cách tạo tải, kích thước dữ liệu, phần cứng, tỷ lệ đọc/ghi, trạng thái cache và cách đo từ client đến database. Kết quả một bài test 100 hàng trong máy phát triển không chứng minh hệ thống đáp ứng 100 triệu hàng ở tải thật.

### 3.1. Lưu lượng và dung lượng phải có mô hình tăng trưởng

Ví dụ giả định:

- Hệ thống khởi đầu với 8 triệu vé, 120 triệu sự kiện clickstream và tăng thêm 1,2 triệu vé mỗi tháng.
- Mỗi đơn trung bình có 2,5 dòng vé; có lịch sử giao dịch, index, WAL, replica và backup cần tính riêng.
- Giờ cao điểm có tỷ lệ read:write khoảng 8:1, nhưng thao tác giữ ghế cùng nhắm một sự kiện có thể tạo **hot key**.
- Báo cáo cần giữ ba năm, dữ liệu giao dịch nhạy cảm có thời hạn lưu theo chính sách riêng.

Ước lượng dung lượng không chỉ bằng `số_hàng × kích_thước_payload`. Cần tính overhead của bản ghi, index, WAL, bản sao, snapshot/backup, dữ liệu tạm, lịch sử và khả năng tăng đột biến. Đo mẫu dữ liệu thật để cập nhật các giả định này.

## 4. Chuyển nhu cầu thành nhóm tiêu chí lựa chọn

Một bộ tiêu chí hữu ích phải bao phủ cả tính đúng đắn lẫn chi phí vận hành:

| Nhóm tiêu chí | Câu hỏi quyết định | Cách tìm bằng chứng |
| --- | --- | --- |
| **Nhất quán và giao dịch** | Có cần atomicity trên nhiều hàng/thực thể, unique constraint, foreign key, isolation? | Tạo race test, rollback test, xem semantics commit |
| **Truy vấn và mô hình dữ liệu** | Lọc theo khóa, JOIN, full-text, aggregation, time series hay truy xuất document? | Tập truy vấn thật, execution plan, chỉ mục |
| **Độ trễ và throughput** | p95/p99 bao nhiêu ở tải đỉnh? Có hot key hoặc giao dịch dài? | Benchmark với lượng dữ liệu và đồng thời thực tế |
| **Độ mới** | Cần read-your-writes hay chấp nhận replica/cache lag? | Kiểm thử đồng bộ và đo lag xuyên hệ thống |
| **Dung lượng và tăng trưởng** | Tốc độ tăng, retention, archive, partition, khả năng scale? | Dự báo dữ liệu, thử tăng gấp nhiều lần |
| **Khả dụng và phục hồi** | Failover, backup, PITR, RPO, RTO, xử lý xóa nhầm? | Diễn tập lỗi và restore có đo thời gian |
| **Bảo mật và quản trị** | Phân quyền, mã hóa, kiểm toán, phân vùng dữ liệu, vị trí lưu? | Kiểm tra cấu hình, audit trail, chính sách |
| **Tiến hóa và tích hợp** | Migration schema, CDC/outbox, driver Java, observability? | Thử deploy hai phiên bản, thử pipeline |
| **Chi phí vòng đời** | Phí hạ tầng, vận hành, mở rộng, backup, dữ liệu truyền, nhân lực? | Dự toán theo tải hiện tại và 12–24 tháng |
| **Năng lực đội ngũ** | Có vận hành, xử lý sự cố, tối ưu query và phục hồi được không? | Diễn tập runbook, đánh giá kỹ năng |

### 4.1. Điều kiện loại trừ và tiêu chí tối ưu

Chia yêu cầu thành hai nhóm:

1. **Điều kiện bắt buộc (hard constraints):** không được vi phạm. Ví dụ, phải bảo vệ bất biến “một ghế không có hai giữ chỗ hợp lệ”, đáp ứng yêu cầu địa điểm lưu dữ liệu, có cơ chế khôi phục đáp ứng RPO/RTO, hoặc có chức năng phân quyền tối thiểu.
2. **Tiêu chí đánh đổi (trade-offs):** cân nhắc sau khi phương án đã vượt qua điều kiện bắt buộc. Ví dụ, chi phí tháng, khả năng mở rộng đọc, mức tự động hóa, tiện lợi khi đổi schema, độ trễ báo cáo.

Một hệ nhanh hơn 20% nhưng không đáp ứng ràng buộc giao dịch bắt buộc **không được chọn chỉ vì tổng điểm cao**. Một document database có thể hỗ trợ giao dịch nhiều tài liệu; một distributed SQL database có thể hỗ trợ SQL và mở rộng ngang; nhưng phải kiểm tra **phiên bản, cấu hình, phạm vi transaction, độ trễ và hành vi lỗi cụ thể** của sản phẩm, không quyết định bằng nhãn loại kho.

### 4.2. Phân biệt capability với guarantee

“Hỗ trợ transaction”, “có replication”, “có backup”, “có index” là danh sách khả năng, chưa phải bảo đảm:

- Transaction có phạm vi một hàng, một partition hay nhiều đối tượng? Isolation ngăn được hiện tượng đồng thời nào?
- Sau khi trả commit thành công, WAL đã được ghi theo điều kiện durability nào? Hệ thống có thể mất các commit gần nhất khi failover không?
- Read replica có thể trễ bao lâu, ứng dụng đọc lại chính thay đổi của mình bằng cách nào?
- Backup có PITR không, có phục hồi thử được, snapshot có nhất quán với dữ liệu và WAL không?
- Index hỗ trợ đúng predicate, sort, JOIN, full-text và mức cardinality của truy vấn thật không?

Không có công nghệ nào tự mang đến mọi guarantee nếu cấu hình hoặc cách sử dụng của ứng dụng sai.

## 5. So sánh các nhóm kho dữ liệu theo mẫu truy cập

| Nhóm kho | Mạnh trong tình huống nào | Những giới hạn cần kiểm chứng |
| --- | --- | --- |
| **Cơ sở dữ liệu quan hệ giao dịch** | Trạng thái nghiệp vụ có ràng buộc, giao dịch, JOIN, truy vấn chọn lọc, schema rõ | Scale ghi, tranh chấp hot row, chi phí JOIN lớn, migration và index |
| **Document database** | Đối tượng có cấu trúc lồng nhau, thường đọc/ghi theo aggregate, field có thể thay đổi | Giao dịch nhiều document, unique constraint, JOIN, index, thay đổi schema và phân tán |
| **Key–value store** | Tra cứu bằng khóa, session, cache, bộ đếm hoặc trạng thái đơn giản | Truy vấn linh hoạt, xử lý nhiều khóa, độ bền và eviction/TTL tùy cấu hình |
| **Search engine** | Tìm toàn văn, lọc đa chiều, ranking, autocomplete | Độ mới sau index, giao dịch và nguồn chuẩn, cập nhật/xóa dữ liệu |
| **Kho phân tích dạng cột / warehouse** | Quét nhiều bản ghi, tổng hợp, phân tích nhiều chiều | Ghi/UPDATE từng dòng, độ trễ nạp, concurrency và chi phí scan |
| **Time-series database** | Chuỗi đo liên tục theo thời gian, downsampling, retention, truy vấn cửa sổ | Cardinality nhãn, thay đổi bản ghi cũ, giao dịch nghiệp vụ |
| **Object storage** | Tệp lớn, ảnh, tài liệu, log lưu dài hạn, dữ liệu phân tích dạng file | Truy vấn từng thực thể, transaction liên tệp, độ trễ và đồng bộ metadata |

Đừng đánh đồng loại kho với từng sản phẩm cụ thể. Cùng một nhóm vẫn có khác biệt lớn về concurrency, tính nhất quán, mô hình index, bảo mật, hỗ trợ Java và chi phí. Lựa chọn cuối cần dựa trên tài liệu phiên bản đang triển khai và kết quả thử nghiệm.

### 5.1. Tại sao không chọn một kho duy nhất cho mọi việc?

Với hệ đặt vé, một phương án có thể là:

~~~mermaid
flowchart LR
    C["Ứng dụng Java"] -->|"Đặt vé / thanh toán"| T[("Kho giao dịch có thẩm quyền")]
    C -->|"Tìm sự kiện"| S[("Kho tìm kiếm")]
    C -->|"Đọc nhanh"| K[("Cache")]
    T -->|"Outbox / CDC"| P["Pipeline đồng bộ"]
    P --> S
    P --> A[("Kho phân tích")]
    A --> B["Dashboard"]
    T -->|"Backup nhất quán + nhật ký"| R[("Kho phục hồi tách biệt")]
~~~

Kho giao dịch là nơi xác nhận đặt chỗ và thanh toán. Hệ tìm kiếm và kho phân tích được cập nhật theo hợp đồng độ mới; cache có thể mất và tái dựng. Backup phục vụ khôi phục, không phải thay thế cơ sở dữ liệu đang xử lý.

Nhưng **mỗi kho mới tạo thêm một chi phí**: đồng bộ, retry, phát hiện trùng, quản lý schema, phân quyền, kiểm toán, cảnh báo và khôi phục. Nếu ứng dụng nhỏ và truy vấn phân tích nhẹ, dùng một kho quan hệ với index và truy vấn phù hợp có thể là lựa chọn tốt hơn. Chỉ tách khi có bằng chứng về nhu cầu, rủi ro hoặc giới hạn hiệu năng.

## 6. Ma trận đánh giá có trọng số

Sau khi sàng lọc điều kiện bắt buộc, nhóm có thể chấm các lựa chọn đủ điều kiện theo thang **1–5** (1: chưa phù hợp; 5: rất phù hợp) và trọng số tổng **100**. Điểm tổng dùng để minh bạch đánh đổi; nó không thay thế thử nghiệm hay điều kiện bắt buộc.

Ví dụ bảng chấm **giả định** cho *kho giao dịch chính của ứng dụng đặt vé*. Các điểm chỉ minh họa cách tính, không phải kết luận tổng quát về mọi sản phẩm:

| Tiêu chí | Trọng số (%) | Phương án A: SQL quan hệ | Phương án B: document store |
| --- | ---: | ---: | ---: |
| Hỗ trợ ràng buộc, tính đúng đắn | 30 | 5 | 3 |
| Truy vấn nghiệp vụ theo nhiều khóa | 20 | 5 | 3 |
| Giao dịch nhiều đối tượng | 15 | 5 | 3 |
| Hiệu năng ở tải dự kiến | 15 | 4 | 4 |
| Thay đổi schema và tích hợp | 10 | 4 | 5 |
| Vận hành, khôi phục và kỹ năng đội | 10 | 4 | 3 |
| **Điểm tổng có trọng số / 100** | **100** | **93** | **67** |

Cách tính điểm là `Σ(trọng số × điểm/5)`; ví dụ A: `30×5/5 + 20×5/5 + 15×5/5 + 15×4/5 + 10×4/5 + 10×4/5 = 93`. B: `30×3/5 + 20×3/5 + 15×3/5 + 15×4/5 + 10×5/5 + 10×3/5 = 67`.

**Lưu ý:** điểm của một sản phẩm thực tế phải được chứng minh bằng yêu cầu và thử nghiệm. Nếu một phương án không thỏa điều kiện bắt buộc, ghi **LOẠI** thay vì dùng điểm số để hợp thức hóa lựa chọn. Hãy ghi nguồn của mỗi điểm (test, benchmark, đánh giá vận hành) và mức độ tin cậy. Người chấm cũng cần thảo luận trọng số với chủ sở hữu nghiệp vụ để tránh ma trận tự củng cố sở thích công nghệ.

### 6.1. Không dùng cùng một ma trận cho hai workload khác nhau

Đối với dashboard phân tích, trọng số có thể chuyển sang scan bytes, thời gian tổng hợp, dung lượng dữ liệu lịch sử, cập nhật tăng dần, chi phí tính toán và khả năng tách tài nguyên. Một warehouse có thể được ưu tiên cho dashboard mà hoàn toàn không phù hợp với đường ghi giữ ghế. Đầu ra có thể là **một kho chính và một kho chuyên dụng bổ trợ**, miễn trách nhiệm và luồng dữ liệu rõ ràng.

## 7. Chứng minh lựa chọn bằng PoC và workload đại diện

**Proof of Concept (PoC)** cần trả lời câu hỏi “phương án có đáp ứng tiêu chí đã định trong điều kiện thực tế không?”, không chỉ “ứng dụng có kết nối tới database thành công không?”.

### 7.1. Thiết kế thí nghiệm

1. **Đóng băng giả định:** cấu hình máy, phiên bản DB, dataset, số index, pool Java, schema, tỷ lệ read/write và concurrency; ghi rõ khác biệt giữa các phương án.
2. **Sinh dữ liệu giống thật:** phân bố khóa nóng/lạnh, số dòng theo thời gian, nhiều trạng thái đơn, dữ liệu đủ lớn để index và cache không che giấu chi phí.
3. **Chạy luồng nghiệp vụ:** đặt ghế với tranh chấp cùng khóa, xác nhận thanh toán, tra cứu đơn, tìm kiếm và báo cáo đa chiều. Dùng các query thực thay vì chỉ `SELECT 1`.
4. **Đo chuẩn:** throughput, p50/p95/p99 end-to-end, lỗi, conflict, retry, lock wait, I/O, CPU, heap, số trang quét, tốc độ tăng WAL và backup.
5. **Chèn lỗi:** ngắt mạng khi commit, kill tiến trình, restart DB, failover, chậm đồng bộ, sự kiện đến lặp và thiếu tài nguyên.
6. **Thử phục hồi:** restore backup và các log cần thiết vào môi trường độc lập, đo RPO/RTO, kiểm tra tính toàn vẹn và tính tương thích schema.
7. **Ghi kết quả:** đánh dấu PASS/FAIL theo từng yêu cầu cùng bằng chứng; cập nhật điểm số hoặc loại phương án.

Không được kết luận một kho “chịu 300 request/s” chỉ từ throughput của công cụ benchmark. Nếu truy vấn đọc trả dữ liệu cũ, tác vụ giữ ghế bị trùng hoặc client bỏ qua lỗi, số request/s cao không chứng minh hệ thống đúng.

### 7.2. Ví dụ hai phép đo khác nhau

| Kiểm thử | Kết quả đạt yêu cầu phải thể hiện |
| --- | --- |
| 500 client đồng thời giữ cùng một ghế | Có tối đa một giữ chỗ hợp lệ tại thời điểm kiểm tra; mọi client còn lại nhận kết quả rõ ràng; không có ghi dở |
| 20 dashboard phân tích 12 tháng trong lúc có tải đặt vé đỉnh | Truy vấn phân tích đạt ngưỡng của nó **và** p95/p99 đặt vé vẫn trong SLO |

Nếu điều kiện thứ hai thất bại, không nhất thiết phải thay database giao dịch. Có thể tối ưu query, tạo bảng tổng hợp, giới hạn concurrency hoặc chuyển dashboard sang hệ đọc/warehouse riêng. Lựa chọn nào tốt nhất phụ thuộc bằng chứng đo và chi phí vận hành.

## 8. Ranh giới persistence Java ảnh hưởng đến quyết định

Trong Java, lựa chọn kho lưu trữ phải đi cùng **hợp đồng repository** và quy tắc xử lý lỗi. Một repository tốt không chỉ cung cấp CRUD; nó phải thể hiện bất biến, định danh yêu cầu và các tính chất giao dịch mà nghiệp vụ cần.

Ví dụ hợp đồng nghiệp vụ:

~~~java
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

record HoldResult(UUID holdId, Instant expiresAt) {}

interface SeatHoldRepository {
    // Trả lại kết quả đã lưu nếu cùng requestId được xử lý lại.
    Optional<HoldResult> findByRequestId(UUID requestId);

    // Phải bảo vệ quy tắc: tối đa một giữ chỗ hợp lệ cho cùng ghế.
    HoldResult holdSeat(
            UUID eventId, String seatId, UUID customerId, UUID requestId);
}
~~~

Phương thức `holdSeat` là **hợp đồng**, chưa có triển khai. Nếu dùng database quan hệ, việc giữ chỗ có thể được hiện thực bằng khóa/unique constraint, transaction và cơ chế hết hạn giữ chỗ được mô hình chính xác. Không nên cho rằng một chỉ mục unique trên `(event_id, seat_id)` của mọi phiếu đã hết hạn sẽ tự giải quyết được quy tắc “đang hiệu lực”: cần trạng thái hiệu lực, cơ chế giải phóng và cách chống race rõ ràng. Nếu dùng kho khác, phải chứng minh bất biến tương đương bằng khả năng transaction và conditional write thực tế.

### 8.1. Minh họa kiểm tra cập nhật nguyên tử với JDBC

Trường hợp đơn giản hơn là giữ số lượng vé còn lại trong một hàng `event_inventory` có khóa chính `event_id`, cột `available` có ràng buộc không âm và `version` là số nguyên:

~~~sql
CREATE TABLE event_inventory (
    event_id UUID PRIMARY KEY,
    available INTEGER NOT NULL CHECK (available >= 0),
    version BIGINT NOT NULL DEFAULT 0
);

-- Cập nhật nguyên tử; phải bind cùng quantity dương ở cả hai vị trí.
UPDATE event_inventory
SET available = available - ?,
    version = version + 1
WHERE event_id = ?
  AND available >= ?;
~~~

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.UUID;
import javax.sql.DataSource;

public final class InventoryWriter {
    private final DataSource transactionStore;

    public InventoryWriter(DataSource transactionStore) {
        this.transactionStore = transactionStore;
    }

    public boolean decrease(UUID eventId, int quantity) throws SQLException {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        String sql = "UPDATE event_inventory "
                + "SET available = available - ?, version = version + 1 "
                + "WHERE event_id = ? AND available >= ?";

        try (Connection connection = transactionStore.getConnection()) {
            connection.setAutoCommit(false);
            try {
                int changed;
                try (PreparedStatement statement =
                        connection.prepareStatement(sql)) {
                    statement.setInt(1, quantity);
                    statement.setObject(2, eventId);
                    statement.setInt(3, quantity);
                    changed = statement.executeUpdate();
                }

                if (changed != 1) {
                    connection.rollback();
                    return false;
                }
                connection.commit();
                return true;
            } catch (SQLException | RuntimeException error) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            }
        }
    }
}
~~~

Đây chỉ minh họa **cập nhật có điều kiện trong một giao dịch cục bộ**, không phải toàn bộ nghiệp vụ giữ chỗ. Hệ thống thật cần lưu phiếu giữ, trạng thái và thời hạn, yêu cầu idempotent, quyền truy cập và event/outbox trong cùng ranh giới giao dịch phù hợp. Nếu kết nối mất trong lúc `COMMIT`, client có thể không biết giao dịch đã hoàn tất hay chưa; phải kiểm tra bằng định danh yêu cầu/phiếu giữ thay vì lặp thao tác trừ số lượng. Cơ chế giữ ghế cụ thể phải giải quyết thêm hết hạn và giải phóng chỗ.

Chính yêu cầu này giúp đánh giá data store: phải có công cụ để bảo vệ ràng buộc cập nhật đồng thời, cùng cơ chế truy vết và phục hồi được cam kết. **SQL thuận tiện là một yếu tố; tính đúng của thao tác mới là tiêu chí quyết định.**

## 9. Lựa chọn còn phải đáp ứng lỗi kết nối, schema và bảo mật

Một database vượt qua benchmark vẫn có thể không phù hợp nếu không bảo đảm những điều kiện vận hành sau.

### 9.1. Retry, replication và khả dụng

- **Lỗi trước khi gửi lệnh:** có thể retry nếu điều kiện nghiệp vụ cho phép.
- **Lỗi trong lúc commit:** kết quả có thể **không xác định từ phía client**; cần idempotency key, khóa duy nhất hoặc truy vấn trạng thái đã xác nhận trước khi gửi lại.
- **Replica bất đồng bộ:** có thể phục vụ dữ liệu cũ; thao tác cần read-your-writes phải dùng đường đọc đáp ứng cam kết đó.
- **Failover:** cần xác định ai được ghi, cách ngăn hai primary, cách xử lý commit chưa sao chép và cách ứng dụng đổi kết nối.

### 9.2. Schema evolution

Nếu ứng dụng Java triển khai nhiều phiên bản cùng lúc, kho được chọn phải hỗ trợ chiến lược tương thích: **mở rộng schema → ghi/đọc dữ liệu mới và backfill → loại bỏ đường cũ**. Document store cũng cần kiểm soát phiên bản cấu trúc tài liệu và dữ liệu thiếu field; “schema linh hoạt” không đồng nghĩa “không phải migration”.

### 9.3. Bảo vệ và khôi phục dữ liệu

Quyết định cần bao gồm quyền truy cập tối thiểu, mã hóa khi truyền và lưu trữ theo nhu cầu, audit, retention, xóa dữ liệu theo chính sách, quản lý khóa và vị trí lưu. Với backup, kiểm tra có thể restore **đúng phiên bản** dữ liệu và ứng dụng trong RTO, với mức mất dữ liệu không vượt RPO. Replication không thay thế backup vì xóa nhầm hoặc dữ liệu sai có thể lan tới bản sao.

Đối với kho tìm kiếm hoặc phân tích có thể tái dựng, vẫn phải tính thời gian backfill và nguồn dữ liệu còn tồn tại. Nếu cần nhiều ngày để dựng lại dashboard quan trọng, “có thể tái dựng” chưa chắc đáp ứng RTO.

## 10. Tính chi phí vòng đời và thời điểm cần xem lại quyết định

Chi phí lựa chọn nên tính trong cả vòng đời, không chỉ phí lưu trữ theo GB:

| Thành phần | Câu hỏi cần ước lượng |
| --- | --- |
| Compute và I/O | Đọc/ghi đỉnh, query nặng, batch, index build, vacuum/compaction |
| Dung lượng | Dữ liệu gốc, index, replica, WAL, snapshot, backup, tăng trưởng |
| Network | Đồng bộ giữa vùng, truy xuất từ dịch vụ khác, export/import |
| Con người | Triển khai, cập nhật, giám sát, xử lý incident, đào tạo |
| Phục hồi | Diễn tập restore, giữ nhiều điểm phục hồi, độ dài thời gian downtime |
| Phụ thuộc sản phẩm | Độ khó chuyển dữ liệu, thay driver/query/API, giới hạn dịch vụ quản lý |

Hãy dự toán **hiện tại, 12 tháng và 24 tháng** theo nhiều kịch bản tăng trưởng. Một phương án rẻ khi dữ liệu ít có thể đắt khi lượng scan và egress tăng. Ngược lại, thêm một kho chuyên dụng quá sớm có thể khiến chi phí vận hành vượt lợi ích hiệu năng.

Nên định nghĩa **ngưỡng đánh giá lại**, ví dụ p95 giao dịch vượt SLO dù đã tối ưu truy vấn, báo cáo làm tăng lock wait hoặc CPU trên nguồn ghi, ingestion lag vượt ngưỡng liên tục, hoặc thời gian restore thực đo không đạt RTO. Khi xuất hiện ngưỡng đó, nhóm sẽ có dữ liệu để quyết định nâng cấp cấu hình, thay chỉ mục, tách tải hay đổi kiến trúc.

## 11. Mẫu ghi lại quyết định kiến trúc (ADR)

Mỗi lựa chọn nên có một bản ghi quyết định ngắn, đủ để người mới hiểu tại sao hệ thống dùng công nghệ đó:

~~~text
Tiêu đề: Chọn kho lưu giao dịch cho hệ thống đặt vé
Trạng thái: Đề xuất / Đã chấp nhận / Cần đánh giá lại

Nhu cầu:
- Giữ ghế không trùng ở 500 yêu cầu cạnh tranh
- p95 API giữ ghế <= 250 ms khi đạt 300 request/s
- RPO <= 5 phút; RTO <= 45 phút

Phạm vi:
- Nguồn chuẩn cho tồn ghế, phiếu giữ, đơn đặt vé
- Không bao gồm tìm kiếm toàn văn và dashboard phân tích

Điều kiện bắt buộc:
- Atomic update, kiểm soát đồng thời, idempotency
- Backup/restore thử được; phân quyền đáp ứng chính sách

Phương án xem xét:
- A: kho quan hệ giao dịch
- B: kho tài liệu có hỗ trợ transaction phù hợp

Bằng chứng:
- Workload, bộ dữ liệu, phiên bản, cấu hình, kết quả test
- Kiểm tra failover, restore, migration và chi phí dự báo

Quyết định và đánh đổi:
- Chọn phương án đạt điều kiện bắt buộc, chỉ rõ các rủi ro còn lại
- Xác định người sở hữu, thời điểm và ngưỡng đánh giá lại
~~~

ADR phải ghi **bằng chứng của quyết định tại thời điểm lựa chọn**. Nếu dữ liệu, workload hoặc yêu cầu kinh doanh thay đổi, có thể thay quyết định; điều này không có nghĩa lựa chọn cũ sai trong bối cảnh trước đó.

## 12. Bài tập tình huống

Một nhóm đang xây dựng nền tảng đặt vé mới với các thông tin giả định:

- 50 nghìn người dùng truy cập đồng thời vào giờ mở bán; vài nghìn người tranh chấp vé của một sự kiện nổi bật.
- Phải ngăn bán vượt số ghế và xác nhận trùng thanh toán.
- Ứng dụng có tìm kiếm sự kiện bằng từ khóa, địa điểm và thời gian.
- Dashboard phân tích 24 tháng, chấp nhận dữ liệu chậm tối đa 10 phút.
- Hệ thống phải phục hồi sau khi mất cụm với RPO 5 phút và RTO 45 phút.
- Nhóm phát triển có kinh nghiệm Java/JDBC và vận hành database quan hệ; ít kinh nghiệm vận hành hệ tìm kiếm phân tán.

**Yêu cầu thực hành:**

1. Chia thành ít nhất ba workload: giao dịch, tìm kiếm và báo cáo; ghi năm truy vấn hoặc lệnh quan trọng nhất.
2. Đề xuất năm điều kiện bắt buộc và năm tiêu chí đánh đổi, nêu cách kiểm thử cho từng yêu cầu.
3. Xây dựng ma trận trọng số **riêng cho kho giao dịch**; không cộng điểm tìm kiếm vào cùng bảng nếu vai trò khác nhau.
4. Đề xuất kiến trúc dùng một kho hoặc nhiều kho, chỉ rõ nguồn có thẩm quyền, độ trễ đồng bộ và cách xử lý retry.
5. Thiết kế một PoC kiểm tra đồng thời giữ vé, thử mất kết nối khi commit, đo p95/p99 và restore một bản backup.
6. Viết một ADR ngắn trình bày lựa chọn, các bằng chứng cần hoàn thiện và thời điểm đánh giá lại.

**Hướng phân tích tham khảo:** bắt đầu bằng kho giao dịch có cơ chế ràng buộc và transaction đáp ứng giữ ghế; dùng truy vấn/index trong kho đó cho nhu cầu tìm kiếm đơn giản nếu đo vẫn đạt, và cân nhắc kho tìm kiếm riêng khi tính năng full-text hoặc quy mô truy vấn yêu cầu. Dashboard có thể bắt đầu từ truy vấn đọc được giới hạn rồi chuyển sang kho phân tích khi khối lượng hoặc nhu cầu tách tải rõ ràng. Pipeline outbox/CDC phải có chống trùng, đối soát và độ trễ quan sát được. Lựa chọn cuối cùng chỉ được xác nhận sau kiểm thử với tải tranh chấp và thử khôi phục.

## 13. Checklist trước khi chốt kho dữ liệu

- [ ] Đã mô tả luồng nghiệp vụ và nguồn dữ liệu chuẩn cho từng loại thông tin.
- [ ] Có truy vấn/lệnh ghi đại diện cùng yêu cầu đồng thời và dữ liệu mẫu đủ lớn.
- [ ] Đã xác định bất biến, phạm vi transaction, mức cô lập và tình huống commit không rõ kết quả.
- [ ] Mỗi yêu cầu hiệu năng có ngưỡng, tải, môi trường đo và người chấp nhận.
- [ ] Độ mới dữ liệu, read-your-writes và lag giữa các kho được định nghĩa.
- [ ] Dung lượng, tốc độ tăng trưởng, retention, index, replica và backup được ước lượng.
- [ ] Đã phân biệt điều kiện bắt buộc với tiêu chí chấm điểm có trọng số.
- [ ] Đã kiểm chứng tính năng của sản phẩm và phiên bản thực tế, kể cả giới hạn/đánh đổi.
- [ ] Có kết quả PoC về correctness, latency, concurrency, failover, schema migration và restore.
- [ ] Có phương án quản trị truy cập, dữ liệu nhạy cảm, audit và khôi phục đạt RPO/RTO.
- [ ] Đã tính chi phí vòng đời, năng lực đội ngũ và rủi ro phụ thuộc công nghệ.
- [ ] Quyết định được ghi lại bằng ADR và có ngưỡng đánh giá lại.

**Ghi nhớ:** Chọn kho dữ liệu là một **quyết định dựa trên workload và cam kết nghiệp vụ**. Hãy bắt đầu từ các tình huống phải đúng, biến chúng thành tiêu chí đo được, loại các phương án không đáp ứng điều kiện bắt buộc, so sánh đánh đổi bằng bằng chứng rồi thử nghiệm bằng dữ liệu và lỗi thực tế. Một kiến trúc persistence Java đáng tin cậy có thể sử dụng nhiều kho, nhưng phải luôn rõ **nơi nào được quyền ghi**, **độ mới của dữ liệu đọc** và **cách khôi phục khi sự cố xảy ra**.
