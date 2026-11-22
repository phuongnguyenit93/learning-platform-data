# Ước lượng người dùng, lưu lượng, dung lượng dữ liệu và tốc độ tăng trưởng

Một bản thiết kế cloud cần trả lời hai câu hỏi trước khi chọn dịch vụ hay cấu hình máy: **hệ thống phải xử lý bao nhiêu tải** và **tải đó thay đổi thế nào theo thời gian**? Câu trả lời ảnh hưởng trực tiếp đến cách chọn compute, cơ sở dữ liệu, cache, hàng đợi, mạng, cơ chế mở rộng, khả năng chịu lỗi và ngân sách.

Trong giai đoạn **yêu cầu kiến trúc**, ước lượng là quá trình chuyển mục tiêu kinh doanh thành những đại lượng có thể đo, kiểm chứng và dùng để ra quyết định. Các con số ban đầu có thể chưa chính xác; điều quan trọng là nêu rõ giả định, đơn vị, khoảng biến thiên và cách sẽ xác minh chúng. Một dự báo “có một triệu người dùng” chưa đủ để xác định một hệ thống cần bao nhiêu tài nguyên.

## 1. Cần ước lượng những gì?

| Đại lượng | Ý nghĩa | Câu hỏi kiến trúc cần trả lời |
| --- | --- | --- |
| Người dùng đăng ký | Tổng số tài khoản đã tạo, bao gồm tài khoản không hoạt động | Quy mô dữ liệu hồ sơ và vòng đời tài khoản? |
| MAU (Monthly Active Users) | Người dùng hoạt động trong một tháng | Quy mô sản phẩm và mức tăng trưởng dài hạn? |
| DAU (Daily Active Users) | Người dùng hoạt động trong một ngày | Khối lượng công việc trong một ngày điển hình? |
| Phiên/ngày và thao tác/phiên | Mức độ sử dụng của một người dùng | Có bao nhiêu lời gọi API, giao dịch và sự kiện? |
| RPS/QPS/TPS | Requests, queries hoặc transactions mỗi giây; phải nói rõ đo ở lớp nào | API, database và hệ thống phụ trợ chịu tải bao nhiêu? |
| Đồng thời (concurrency) | Phiên đang hoạt động, yêu cầu đang xử lý hoặc kết nối đang mở | Cần bao nhiêu tài nguyên đồng thời? |
| Băng thông và lưu lượng truyền | Byte/giây tại thời điểm cao điểm và byte/tháng | Mạng, CDN, load balancer và chi phí truyền dữ liệu? |
| Dung lượng dữ liệu | Dữ liệu hiện có, phát sinh, chỉ mục, bản sao, bản sao lưu | Dung lượng lưu trữ, chiến lược sao lưu, phân tầng dữ liệu? |
| Tốc độ tăng trưởng | Mức thay đổi của người dùng, yêu cầu, dữ liệu và kích thước payload | Khi nào cần mở rộng hoặc thay đổi thiết kế? |

Các con số này **không thay thế nhau**. Ví dụ, 100.000 DAU có thể tạo ra vài chục hoặc vài nghìn RPS tùy số thao tác, số API mỗi thao tác và mức tập trung tải theo thời gian. Tương tự, 10.000 người dùng đang mở ứng dụng không đồng nghĩa có 10.000 HTTP request đang được máy chủ xử lý.

Nên gắn mỗi phép đo với **thành phần và ranh giới hệ thống**: request tại CDN, request đến API gateway, request đã vào ứng dụng và truy vấn đến database thường là bốn đại lượng khác nhau. Phân biệt lưu lượng đến (ingress) và lưu lượng đi (egress), đặc biệt khi ước lượng chi phí cloud.

## 2. Chuyển yêu cầu nghiệp vụ thành giả định có thể tính

Trước khi áp dụng công thức, hãy mô tả các hành trình chính: đăng nhập, xem danh sách, tìm kiếm, đặt lịch, thanh toán, tải tệp, đồng bộ nền, nhận thông báo. Mỗi hành trình có cách sử dụng và chi phí xử lý khác nhau.

Một bảng giả định đầu vào nên chứa:

| Nhóm | Thông tin cần thu thập | Nguồn ưu tiên |
| --- | --- | --- |
| Quy mô | DAU/MAU hiện tại, mục tiêu 3–12–24 tháng, phân khúc và khu vực | Analytics, số liệu kinh doanh, dự báo sản phẩm |
| Hành vi | Phiên/người/ngày, thời lượng phiên, thao tác/phiên, tần suất theo tính năng | Product analytics, khảo sát, prototype |
| Ứng dụng | Số API cho mỗi thao tác, kích thước request/response, retry và polling | API logs, tracing, đo thực tế trên client |
| Phân bố thời gian | Giờ cao điểm, ngày trong tuần, mùa vụ, chiến dịch, sự kiện đồng loạt | Biểu đồ lịch sử theo phút/giờ, kế hoạch marketing |
| Dữ liệu | Số bản ghi phát sinh, kích thước thực tế, tệp đính kèm, chỉ mục, thời gian lưu | Schema, mẫu dữ liệu, chính sách lưu giữ |
| Chất lượng dịch vụ | SLO độ trễ, tỉ lệ lỗi, tính sẵn sàng, RPO/RTO | Yêu cầu nghiệp vụ và cam kết vận hành |

Nếu là hệ thống mới chưa có dữ liệu, dùng giả định dựa trên hành trình người dùng và lập **ba kịch bản thấp / cơ sở / cao**. Đánh dấu độ tin cậy của từng giả định; chẳng hạn DAU từ analytics có độ tin cậy cao hơn số request/phiên suy từ phỏng vấn.

### Phân nhóm theo loại tải

Không nên gom toàn bộ request vào một loại. Một thiết kế tối thiểu thường tách:

- **Đọc tương tác:** xem nội dung, tra cứu, tìm kiếm; thường nhạy với độ trễ và có thể được cache.
- **Ghi giao dịch:** đặt chỗ, thanh toán, cập nhật trạng thái; cần kiểm soát tính nhất quán, trùng lặp và khả năng khôi phục.
- **Tác vụ nền:** đồng bộ, gửi email, xử lý ảnh, tính báo cáo; thường có thể xử lý bất đồng bộ qua queue.
- **Truyền tệp và media:** tải ảnh/video/tài liệu; lưu lượng byte có thể lớn dù số request thấp.
- **Luồng thời gian thực:** WebSocket, streaming, thông báo trực tiếp; số kết nối và thời gian giữ kết nối có thể quan trọng hơn RPS.

Ví dụ, một lần người dùng nhấn “Đặt chỗ” có thể tạo một HTTP request nhưng gây ra nhiều thao tác database, hàng đợi và dịch vụ bên ngoài. Vì vậy cần tính **tải theo từng lớp**, không coi RPS của API là QPS của database.

## 3. Tính request, cao điểm và đồng thời

Giả sử:

- \(D\): số người dùng hoạt động mỗi ngày (DAU).
- \(S\): số phiên trung bình mỗi người dùng mỗi ngày.
- \(A\): số lời gọi API trung bình trong một phiên, sau khi đã tính các request nền phù hợp.
- \(B\): hệ số tập trung tải của giờ/phút cao điểm so với mức trung bình cả ngày.
- \(C\): hệ số tăng tải của ngày chiến dịch so với ngày thường.

Với giả định sử dụng tương đối đồng đều giữa các nhóm người dùng:

\[
N_{\text{ngày}} = D \times S \times A
\]

\[
RPS_{\text{trung bình}} = \frac{N_{\text{ngày}}}{86\,400}
\]

\[
RPS_{\text{đỉnh ngày thường}} \approx RPS_{\text{trung bình}} \times B
\]

\[
RPS_{\text{đỉnh chiến dịch}} \approx RPS_{\text{trung bình}} \times B \times C
\]

Hệ số \(B\) nên lấy từ biểu đồ lưu lượng thực tế, ví dụ tỉ lệ giữa RPS cao điểm trong **cửa sổ 1 hoặc 5 phút** và RPS trung bình ngày. Hệ số \(C\) chỉ dùng để mô tả một thay đổi **chưa nằm trong dữ liệu cơ sở**; nếu số DAU đã là DAU của chiến dịch thì không nhân thêm \(C\). Hệ số của giờ cao điểm cũng không mô tả được đợt đổ tải vài giây khi mở bán vé hay gửi thông báo đồng loạt: trường hợp đó phải kiểm tra đỉnh ở độ phân giải ngắn hơn.

Nếu phân tách đọc/ghi theo tỉ lệ \(p_{\text{đọc}}\) và \(p_{\text{ghi}}\):

\[
RPS_{\text{đọc}} = RPS_{\text{tổng}} \times p_{\text{đọc}}, \qquad
RPS_{\text{ghi}} = RPS_{\text{tổng}} \times p_{\text{ghi}}
\]

Để dự báo tải database, tiếp tục nhân với số truy vấn thực sự đi tới database trên mỗi request. Cần trừ phần được phục vụ bởi cache và cộng các truy vấn phụ, retry hoặc job nền; cache hit rate có thể thay đổi mạnh khi mới triển khai hoặc khi dữ liệu vừa hết hạn.

### Hai khái niệm concurrency dễ nhầm

**Phiên hoạt động đồng thời** có thể ước lượng sơ bộ từ số phiên mở trong ngày và thời lượng phiên:

\[
\text{Phiên đồng thời trung bình}
\approx \frac{\text{phiên/ngày} \times \text{thời lượng phiên (giây)}}{86\,400}
\]

**Request đang xử lý đồng thời** sử dụng hệ thức Little khi hệ thống ở trạng thái ổn định:

\[
L \approx \lambda \times W
\]

Trong đó \(L\) là số request đang xử lý, \(\lambda\) là request/giây và \(W\) là thời gian xử lý trung bình tính bằng giây. Ví dụ 400 RPS với thời gian phản hồi trung bình 0,25 giây tương đương khoảng **100 request in-flight**, không phải 400 người dùng. Đây là quan hệ ước lượng; nếu hàng đợi đang tích tụ hoặc request treo lâu, số đang chờ có thể tăng nhanh. Với WebSocket, cần đo số kết nối cùng lúc và mức bộ nhớ trên mỗi kết nối riêng.

## 4. Tính lưu lượng mạng và băng thông

Số request và số byte phản ánh hai loại áp lực khác nhau. Một API trả JSON nhỏ có thể chịu nhiều RPS nhưng ít băng thông; tải video có thể có số request thấp nhưng tiêu thụ nhiều egress.

\[
\text{Egress/ngày (byte)} =
\sum_i N_{i,\text{ngày}} \times \text{response byte trung bình}_i
\]

\[
\text{Băng thông egress đỉnh (bit/s)}
\approx RPS_{\text{đỉnh}} \times \text{response byte/request} \times 8
\]

Khi dùng KB, MB và GB theo hệ thập phân: 1 KB = 1.000 byte, 1 GB = \(10^9\) byte. Nếu dùng KiB, MiB và GiB thì các hệ số là 1.024; phải ghi rõ đơn vị để tránh sai lệch.

Khi lập ngân sách và cấu hình mạng, cần tính thêm:

- Payload thực tế sau nén, header, TLS và giao thức; đo ở vị trí tương ứng với khoản chi phí cần dự báo.
- Cache/CDN hit và tỉ lệ request quay về origin: byte tới người dùng có thể khác byte từ origin.
- Upload, download, truy cập liên vùng/khác availability zone, sao chép dữ liệu, backup và lưu lượng giữa các dịch vụ.
- Payload lớn bất thường, retry, download trùng lặp, WebSocket và luồng media riêng.

Đừng dùng thông lượng mạng trung bình tháng để kiểm tra điểm nghẽn ở đỉnh phút hoặc giây. Ngược lại, cũng không nhân băng thông đỉnh với số giây cả tháng để dự báo hóa đơn: phải dùng biểu đồ hoặc giả định phân bố lưu lượng theo thời gian.

## 5. Ước lượng dữ liệu và vòng đời lưu trữ

Đối với một loại dữ liệu phát sinh tương đối ổn định:

\[
\text{Dung lượng thô/ngày}
= \text{số bản ghi mới/ngày} \times \text{byte/bản ghi}
\]

\[
\text{Dung lượng có chỉ mục/overhead}
\approx \text{dung lượng thô} \times k
\]

\[
\text{Dung lượng của dữ liệu giữ trong } T \text{ ngày}
\approx \text{dung lượng/ngày} \times T
\]

Hệ số \(k\) phải được đo từ dữ liệu mẫu, vì index, MVCC, phân mảnh và cách mã hóa dữ liệu thay đổi theo engine. Công thức giữ \(T\) ngày giả định lưu lượng đều và xóa dữ liệu cũ thực sự giải phóng hoặc có thể tái sử dụng dung lượng; nếu dữ liệu đang tăng trưởng, phải cộng theo từng khoảng thời gian.

Không cộng lẫn các thành phần trước khi giải thích bản chất của chúng:

| Thành phần | Điều cần ước lượng |
| --- | --- |
| Bản ghi nghiệp vụ | Số lượng, kích thước, cập nhật/xóa, thời gian lưu theo quy định |
| Chỉ mục và metadata | Index, page overhead, lịch sử phiên bản, tombstone, phân mảnh |
| Log, metric, trace, audit | Sự kiện/giây, byte/sự kiện, sampling, retention |
| Object và media | Kích thước tệp, số bản sao/phiên bản, chính sách lifecycle |
| Replica | Số bản sao phục vụ HA/đọc; tính thêm dung lượng vật lý thực tế |
| Backup và PITR | Snapshot, incremental backup, log phục hồi, thời gian giữ |
| Bộ nhớ đệm | Working set và overhead bộ nhớ; khác với dữ liệu lưu trữ lâu dài |

Nếu có một primary và hai read replica cùng giữ toàn bộ dữ liệu, không được chỉ tính dung lượng của primary khi dự báo tài nguyên lưu trữ. Đồng thời, snapshot gia tăng không nhất thiết chiếm một bản sao đầy đủ mỗi ngày; chi phí phụ thuộc lượng khối dữ liệu thay đổi, tần suất và thời hạn giữ. Hãy dự báo backup bằng mẫu thực tế hoặc công cụ của nhà cung cấp.

Ngoài **số GB**, cần ước lượng **số thao tác đọc/ghi mỗi giây, IOPS, kích thước truy vấn, throughput, working set, khóa giao dịch và độ trễ**. Hai database cùng 500 GB có thể cần kiến trúc hoàn toàn khác nhau nếu một hệ thống đọc tuần tự theo lô và hệ thống kia thực hiện hàng nghìn giao dịch ngẫu nhiên mỗi giây.

## 6. Ví dụ xuyên suốt: ứng dụng đặt lịch

Một ứng dụng đặt lịch hoạt động tại nhiều khu vực đang chuẩn bị cho chiến dịch tăng trưởng. Đội dự án xây dựng bảng giả định *minh họa*, chưa phải số đo hay thông số cam kết của bất kỳ nhà cung cấp cloud nào.

| Giả định | Giá trị |
| --- | ---: |
| MAU / DAU ngày thường | 300.000 / 60.000 người |
| Phiên mỗi DAU mỗi ngày | 1,5 |
| HTTP API request mỗi phiên | 24 |
| Thời lượng một phiên | 8 phút |
| Hệ số đỉnh ngày thường \(B\) | 8 lần mức trung bình ngày |
| Ngày chiến dịch \(C\) | 2 lần tải ngày thường |
| Tỉ trọng API đọc / ghi | 85% / 15% |
| Dữ liệu egress trung bình/API response | 25 KB, hệ thập phân |
| Bản ghi đặt lịch mới | 0,12 bản ghi/DAU/ngày |
| Dung lượng một bản ghi đặt lịch | 2 KB thô; hệ số index/overhead 1,5 |
| Sự kiện phân tích | 10 sự kiện/DAU/ngày, trung bình 1 KB/sự kiện |
| Retention | Bản ghi đặt lịch: 3 năm; event: 90 ngày |
| Media lưu trữ | Đã có 400 GB; dự kiến thêm 40 GB/tháng |

### Bước 1 — Suy ra request và đỉnh

Trong ngày thường:

1. Số phiên/ngày = \(60.000 \times 1,5 = 90.000\) phiên.
2. Số API request/ngày = \(90.000 \times 24 = 2.160.000\) request.
3. RPS trung bình = \(2.160.000/86.400 = 25\) RPS.
4. Đỉnh ngày thường = \(25 \times 8 = 200\) RPS.
5. Đỉnh ngày chiến dịch = \(25 \times 8 \times 2 = 400\) RPS.

Tại đỉnh chiến dịch, nếu tỉ lệ thao tác giữ nguyên, ứng dụng nhận khoảng **340 read RPS** và **60 write RPS**. Đây là lưu lượng tới API; số truy vấn SQL cần được đo riêng.

| Kịch bản | Request/ngày | RPS trung bình | RPS đỉnh theo giả định |
| --- | ---: | ---: | ---: |
| Ngày thường | 2.160.000 | 25 | 200 |
| Ngày chiến dịch, tải gấp đôi | 4.320.000 | 50 | 400 |

Phiên hoạt động đồng thời trung bình ngày thường là \(90.000 \times 480 / 86.400 = 500\) phiên. Nếu sự phân bố phiên đi theo hệ số đỉnh 8, có khoảng **4.000 phiên hoạt động tại đỉnh ngày thường**, hoặc **8.000 phiên tại đỉnh chiến dịch**. Trong khi đó, ở đỉnh chiến dịch với response time trung bình 0,25 giây, số HTTP request in-flight ước lượng là \(400 \times 0,25 = 100\). Ba giá trị 8.000, 400 và 100 đo ba điều khác nhau.

### Bước 2 — Suy ra băng thông và byte/tháng

Với response trung bình 25 KB:

- Egress API ngày thường: \(2.160.000 \times 25.000 = 54.000.000.000\) byte, tương đương **54 GB/ngày**.
- Nếu 30 ngày đều như ngày thường: **1,62 TB/tháng**, chưa kể media, CDN và các loại egress khác.
- Băng thông egress ở đỉnh chiến dịch: \(400 \times 25.000 \times 8 = 80.000.000\) bit/s, tức khoảng **80 Mb/s** ở ranh giới đo giả định.

Đây là kết quả của **payload trung bình**. Khi sizing mạng hoặc tính tiền cần thay bằng phân bố payload đo thực tế, tách traffic được CDN phục vụ và cộng các đường truyền liên quan. Ví dụ tệp ảnh không nên mặc định được tính trong 25 KB API response.

### Bước 3 — Suy ra dung lượng lưu trữ

**Đặt lịch:** \(60.000 \times 0,12 = 7.200\) bản ghi mới/ngày. Với 2 KB/bản ghi và hệ số 1,5, mức tăng ước tính là \(7.200 \times 2 \times 1,5 = 21.600\) KB, tức **21,6 MB/ngày**. Giữ đủ ba năm 365 ngày/năm với tải không đổi tương đương khoảng **23,65 GB** dữ liệu và chỉ mục trước khi tính replica/backup.

**Event analytics:** \(60.000 \times 10 = 600.000\) sự kiện/ngày, tạo khoảng **600 MB dữ liệu thô/ngày**. Nếu chỉ giữ 90 ngày và phát sinh đều, tập dữ liệu đang giữ khoảng **54 GB thô**; chưa tính chỉ mục, nén, metadata, replica và bản sao lưu.

**Media:** 400 GB hiện có cộng 40 GB/tháng dẫn đến khoảng **880 GB sau 12 tháng** trước replication, versioning và lifecycle. Kích thước media và retention có thể chi phối hóa đơn lưu trữ dù dữ liệu giao dịch tương đối nhỏ.

Từ các con số này, kiến trúc sư có thể tách database giao dịch, kho event/analytics và object storage, sau đó chọn chính sách retention, backup, truy xuất nóng/lạnh và phân vùng phù hợp.

### Bước 4 — Biến tải thành giả định compute và khả năng chịu lỗi

Giả sử **load test trên ứng dụng thực tế** cho thấy một instance phục vụ bền vững 150 RPS ở độ trễ SLO quy định. Để giữ tải mục tiêu ở mức 65% năng lực đã đo:

\[
\text{Năng lực thiết kế/instance} = 150 \times 0,65 = 97,5\ \text{RPS}
\]

\[
\text{Số instance theo throughput}
= \left\lceil \frac{400}{97,5} \right\rceil = 5
\]

**5 instance chỉ đáp ứng phép tính thông lượng**, chưa chứng minh tính sẵn sàng. Nếu yêu cầu chịu mất hoàn toàn một trong ba availability zone, một phương án để kiểm tra là bố trí **8 instance theo phân bố 3–3–2**: mất zone có 3 instance vẫn còn 5 instance, năng lực ước tính \(5 \times 97,5 = 487,5\) RPS. Thiết kế thực tế còn phụ thuộc sự cân bằng tải, năng lực database, hạn ngạch, kết nối mạng, thời gian autoscale, độ trễ phân vùng và việc đo kiểm sau sự cố.

Không thể suy ra cấu hình vCPU/RAM chỉ từ RPS. Benchmark phải bao gồm tỉ lệ đọc/ghi, kích thước payload, truy vấn backend, cache, độ trễ p95/p99, CPU, RAM, I/O và những điểm nghẽn của tải thực.

## 7. Dự báo tăng trưởng và xây dựng kịch bản

Với tốc độ tăng trưởng theo mỗi chu kỳ \(g\), một dự báo đơn giản là:

\[
V_t = V_0 \times (1+g)^t
\]

Trong đó \(V_0\) là giá trị ban đầu, \(t\) là số chu kỳ. Ví dụ DAU tăng **20% mỗi quý** trong bốn quý thì hệ số sau một năm là \(1,2^4 \approx 2,074\). Nếu hành vi sử dụng không đổi, đỉnh chiến dịch 400 RPS có thể trở thành khoảng **829 RPS** sau 12 tháng. Nhưng retention dữ liệu, số bản ghi trên mỗi người dùng, payload và mức cache hit có thể tăng theo quy luật khác; không nên tự động nhân mọi chỉ số với cùng hệ số.

Nên xem ít nhất ba kịch bản:

| Kịch bản | Giả định chủ đạo | Quyết định cần thử |
| --- | --- | --- |
| Thấp | Tăng trưởng chậm, request/phiên ổn định | Mức tài nguyên tối thiểu, chi phí cố định |
| Cơ sở | Dự báo sản phẩm khả tín nhất; tính cả mùa vụ | Ngân sách vận hành và lịch nâng cấp |
| Cao / đột biến | Chiến dịch thành công, sự kiện đồng loạt, retry tăng | Autoscale, queue, rate limiting, dự phòng và giới hạn chịu tải |

Ngoài tăng trưởng phần trăm, phải mô tả **thay đổi tính năng**. Chẳng hạn thêm tự động refresh mỗi 10 giây sẽ làm tăng số request ngay cả khi DAU giữ nguyên. Thêm video có thể thay đổi egress và lưu trữ theo cấp số lớn. Tăng ghi giao dịch có thể làm primary database trở thành nút thắt trước khi API server chạm ngưỡng CPU.

Với dữ liệu có retention hữu hạn, dự báo theo từng giai đoạn:

\[
\text{Dữ liệu đang giữ tại }t
\approx \sum_{d=t-T+1}^{t} \text{dữ liệu phát sinh ở ngày }d
\]

Công thức này cho thấy một tập log có chính sách giữ 90 ngày vẫn tăng dung lượng trong giai đoạn tải tăng, nhưng không tăng tuyến tính mãi mãi như dữ liệu nghiệp vụ không bị xóa. Cần cộng riêng dữ liệu lịch sử bắt buộc giữ, dữ liệu lưu trữ lạnh và khả năng hồi phục từ backup.

## 8. Từ bảng ước lượng đến lựa chọn kiến trúc

Các phép tính là đầu vào để đánh giá theo tư duy **Well-Architected**, luôn xét đồng thời độ tin cậy, bảo mật, hiệu năng, vận hành và chi phí.

| Phát hiện từ workload | Hệ quả thiết kế cần xem xét | Đánh đổi cần xác minh |
| --- | --- | --- |
| Read RPS cao, dữ liệu ít đổi | CDN/cache, chỉ mục truy vấn, read replica | Độ mới dữ liệu, cache invalidation, chi phí replica |
| Write RPS tăng đột biến | Queue, kiểm soát đồng thời, idempotency, backpressure | Độ trễ hoàn tất, thứ tự xử lý, tính nhất quán |
| Đỉnh vài giây cao hơn nhiều lần đỉnh giờ | Giới hạn tốc độ, preload, autoscale sớm, hàng chờ | Thời gian khởi động, giới hạn downstream |
| Media lớn, truy cập theo khu vực | Object storage và CDN | Egress, phân vùng địa lý, quyền truy cập |
| Event tăng nhanh, ít cần truy cập tức thời | Retention, nén, phân tầng nóng/lạnh | Tốc độ truy vấn lại và chi phí lưu giữ |
| Dữ liệu nghiệp vụ quan trọng | Replication, backup, kiểm thử khôi phục, RPO/RTO | Chi phí, độ trễ và phạm vi sự cố |
| Thông lượng tăng theo quý | Autoscale và dự báo giới hạn quota | Độ trễ scale-out, chi phí nhàn rỗi |

Đặc biệt, yêu cầu về **bảo mật và pháp lý** ảnh hưởng đến số bản sao, vùng lưu trữ và thời gian giữ dữ liệu. Không nên “giải quyết tăng trưởng” bằng cách giữ mọi log hoặc nhân bản dữ liệu cá nhân vô hạn. Thiết kế cần nêu quyền truy cập, mã hóa, vòng đời xóa dữ liệu và phương án phục hồi.

## 9. Kiểm chứng giả định và cập nhật dự báo

Quy trình hữu ích là:

~~~mermaid
flowchart LR
    A["Mục tiêu kinh doanh"] --> B["Hành trình và hành vi người dùng"]
    B --> C["DAU, request, byte, dữ liệu"]
    C --> D["Đỉnh, tăng trưởng, kịch bản"]
    D --> E["Sizing và phương án kiến trúc"]
    E --> F["Load test, đo thực tế, chaos/failover test"]
    F --> G["Điều chỉnh giả định và ngân sách"]
    G --> C
~~~

Đo ít nhất **RPS theo phút và giây**, latency p50/p95/p99, error rate, mức sử dụng CPU/RAM, DB QPS và kết nối, cache hit rate, queue depth/lag, byte ingress/egress và dung lượng dữ liệu. Load test nên có tải tăng dần, đỉnh ngắn, chạy tải ổn định kéo dài và kiểm tra phục hồi sau khi giảm tải. Kết quả cần gắn với SLO, vì “hệ thống xử lý 1.000 RPS” không có giá trị nếu phần lớn request timeout.

Trong load test:

1. Mô phỏng tỉ lệ hành trình, dữ liệu và payload thực; tránh chỉ gọi một endpoint nhẹ.
2. Đo trạng thái **ổn định** tại mỗi mức tải, kiểm tra độ trễ và lỗi trước khi kết luận throughput bền vững.
3. Ghi điểm nghẽn đầu tiên: ứng dụng, database, cache, pool kết nối, queue, mạng hay dịch vụ ngoài.
4. Kiểm tra autoscale và failover; đánh giá năng lực còn lại khi mất instance/zone và thời gian phục hồi.
5. Cập nhật bảng giả định bằng số liệu đo được cùng ngày đo, phạm vi và mức tin cậy.

Một mẫu bảng quyết định đơn giản:

| Chỉ số | Cơ sở hiện tại | Dự báo 12 tháng | Đỉnh cần chịu | Nguồn / độ tin cậy |
| --- | --- | --- | --- | --- |
| DAU | … | … | … | Analytics / cao |
| API RPS | … | … | … | Logs + mô hình / trung bình |
| DB read/write QPS | … | … | … | Tracing + benchmark / trung bình |
| Egress GB/tháng | … | … | … | CDN/network metrics / cao |
| Database GB | … | … | … | Schema + sample / trung bình |
| Event/log GB | … | … | … | Telemetry + retention / trung bình |
| Object storage GB | … | … | … | Storage inventory / cao |

Nên đặt cảnh báo và mốc xem xét lại khi dữ liệu thực tế khác dự báo, ví dụ request/phiên tăng 30%, cache hit giảm mạnh, database tiến gần giới hạn IOPS hoặc tốc độ tăng dữ liệu cao hơn kế hoạch. Các ngưỡng cụ thể cần xuất phát từ benchmark, SLO và thời gian cần để bổ sung năng lực.

## 10. Những sai lầm thường gặp

- **Dùng tổng tài khoản thay DAU để tính RPS:** bỏ qua mức hoạt động thực tế và dễ dẫn đến sizing lệch.
- **Dùng RPS trung bình để thiết kế cao điểm:** không tính phân bố giờ, mùa vụ và hiệu ứng nhiều người đồng loạt truy cập.
- **Nhân trùng hệ số cao điểm:** lấy DAU của ngày chiến dịch rồi tiếp tục nhân hệ số chiến dịch lần nữa.
- **Đồng nhất RPS API với QPS database:** bỏ qua cache, fan-out, số query/request và tác vụ nền.
- **Dùng RPS để suy ra người dùng đồng thời:** bỏ qua thời lượng phiên và thời gian xử lý request.
- **Chỉ tính dữ liệu thô:** thiếu chỉ mục, log, replica, backup, phiên bản object và thời gian giữ.
- **Quên đơn vị:** nhầm KB với KiB, Mb/s với MB/s, dữ liệu truyền một lần với dữ liệu lưu trữ.
- **Dùng một mức tăng trưởng chung cho mọi chỉ số:** hành vi người dùng, dữ liệu media và retention có thể thay đổi độc lập.
- **Sizing theo benchmark lý tưởng:** không xét p95/p99, lỗi, cold start, quota, sự cố vùng và nút thắt downstream.
- **Coi số ước lượng là cam kết:** không ghi nguồn, độ tin cậy, kịch bản và cơ chế kiểm chứng.

## 11. Bài tập tự kiểm tra

Một ứng dụng có 100.000 DAU; mỗi người dùng tạo 2 phiên/ngày, mỗi phiên gọi 15 API. Giờ cao điểm có tải gấp 6 lần trung bình ngày; mỗi response trung bình 40 KB, đo theo hệ thập phân; 20% request là ghi. Giả định không có traffic khác.

**Câu hỏi:** Ước lượng (1) request/ngày, (2) RPS trung bình và đỉnh, (3) egress API/ngày, (4) write RPS ở đỉnh.

**Đáp án để đối chiếu:**

1. \(100.000 \times 2 \times 15 = 3.000.000\) request/ngày.
2. \(3.000.000/86.400 \approx 34,7\) RPS trung bình; đỉnh \(\approx 208,3\) RPS.
3. \(3.000.000 \times 40.000 = 120.000.000.000\) byte, tức **120 GB/ngày**.
4. \(208,3 \times 20\% \approx 41,7\) write RPS ở API. Chưa thể suy ra DB write QPS nếu không biết mỗi API tạo bao nhiêu thao tác ghi.

Nếu yêu cầu một câu trả lời có thể dùng trong buổi review kiến trúc, đừng chỉ đưa bốn kết quả này: hãy bổ sung **giả định phân bố tải, nguồn kích thước response, SLO, kịch bản tăng trưởng và kế hoạch load test**. Chính các yếu tố đó quyết định con số có đủ tin cậy để chọn giải pháp cloud hay chưa.
