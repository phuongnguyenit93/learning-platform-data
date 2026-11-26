Bạn sẽ giải thích Prometheus giải quyết những nhu cầu giám sát nào trong hệ thống dịch vụ phân tán?
Bạn sẽ phân biệt metrics, logs và traces khi tìm nguyên nhân một API chậm bất thường như thế nào?
Bạn sẽ mô tả mô hình dữ liệu chuỗi thời gian của Prometheus từ tên metric, labels, sample đến timestamp ra sao?
Bạn sẽ phân biệt một time series với một metric name khi cùng tên có nhiều tổ hợp nhãn như thế nào?
Bạn sẽ giải thích cơ chế pull-based scraping của Prometheus khác với mô hình push metrics như thế nào?
Bạn sẽ xác định tiêu chí nào khiến một hệ thống phù hợp hoặc không phù hợp với Prometheus tự vận hành?
Bạn sẽ so sánh Prometheus với hệ thống lưu trữ log khi cần thống kê độ trễ và tỷ lệ lỗi như thế nào?
Bạn sẽ chọn các chỉ số nào để giám sát một API theo mô hình RED và giải thích giá trị vận hành của chúng ra sao?
Bạn sẽ áp dụng mô hình USE để theo dõi CPU, bộ nhớ, đĩa và mạng của một máy chủ như thế nào?
Bạn sẽ liên kết SLI và SLO với các metric cần thu thập trước khi xây dựng dashboard như thế nào?
Bạn sẽ phân biệt độ trễ do client quan sát với thời gian xử lý ứng dụng mà Prometheus đang đo ra sao?
Bạn sẽ xác định giới hạn của Prometheus khi cần tra cứu từng sự kiện riêng lẻ hoặc lưu toàn bộ request ra sao?
Bạn sẽ thiết kế quy ước đặt tên metric để thể hiện đơn vị và ý nghĩa phép đo nhất quán như thế nào?
Bạn sẽ phân biệt các loại metric counter, gauge, histogram và summary qua một ứng dụng web thực tế như thế nào?
Bạn sẽ xác định các nguồn dữ liệu metrics cần thu thập từ ứng dụng, node, database và network như thế nào?
Bạn sẽ mô tả đường đi từ ứng dụng instrument metrics đến Prometheus, recording rules, Grafana và cảnh báo như thế nào?
Bạn sẽ xây dựng sơ đồ scrape một ứng dụng có nhiều replica và xác định Prometheus truy cập endpoint nào ra sao?
Bạn sẽ giải thích vai trò của HTTP metrics endpoint và exposition format khi Prometheus thu thập dữ liệu như thế nào?
Bạn sẽ kiểm tra endpoint metrics có trả dữ liệu hợp lệ và mã HTTP thành công bằng những bước nào?
Bạn sẽ lựa chọn scrape_interval và evaluation_interval theo nhu cầu phát hiện sự cố và chi phí hệ thống ra sao?
Bạn sẽ đánh giá mối quan hệ giữa scrape_timeout, scrape_interval và thời gian endpoint phản hồi như thế nào?
Bạn sẽ đánh giá tác động của scrape chậm và scrape timeout đến tính đầy đủ của chuỗi thời gian khi số target tăng ra sao?
Bạn sẽ phân biệt job và instance labels trong cấu hình scrape và cách chúng thể hiện trên dashboard ra sao?
Bạn sẽ giải thích vai trò của các metric up, scrape_duration_seconds và scrape_samples_scraped khi kiểm tra target như thế nào?
Bạn sẽ phân biệt target không reachable, endpoint trả lỗi và ứng dụng chưa phát sinh metric bằng dấu hiệu nào?
Bạn sẽ đánh giá tác động của việc thay đổi scrape_interval đến độ phân giải đồ thị và chi phí lưu trữ như thế nào?
Bạn sẽ giải thích Prometheus đánh dấu series stale khi target ngừng xuất metrics hoặc biến mất khỏi discovery như thế nào?
Bạn sẽ điều tra vì sao metric của một instance không còn xuất hiện dù ứng dụng vẫn phản hồi request bình thường như thế nào?
Bạn sẽ sử dụng cấu hình scrape tĩnh trong tình huống nào và xác định hạn chế khi số instance thay đổi ra sao?
Bạn sẽ mô tả cách service discovery cập nhật danh sách target động trong Prometheus như thế nào?
Bạn sẽ lựa chọn Kubernetes service discovery cho Pod, Service hoặc EndpointSlice dựa trên đối tượng cần giám sát ra sao?
Bạn sẽ phân biệt target labels xuất phát từ service discovery với nhãn do ứng dụng xuất ra như thế nào?
Bạn sẽ tổ chức scrape metrics trong Kubernetes khi workload nằm ở nhiều namespace và môi trường khác nhau ra sao?
Bạn sẽ kiểm tra vì sao Pod mới có endpoint metrics nhưng chưa xuất hiện trong danh sách Targets như thế nào?
Bạn sẽ phân biệt cấu hình Prometheus Operator, ServiceMonitor và PodMonitor theo cách khám phá endpoint như thế nào?
Bạn sẽ kiểm tra namespace selector, label selector và port name khi một ServiceMonitor không tạo target như mong đợi ra sao?
Bạn sẽ xác định tác động của RBAC và network policy khi Prometheus không thể khám phá hoặc scrape Pod như thế nào?
Bạn sẽ chọn cách giám sát endpoint bên ngoài Kubernetes mà không làm lẫn nhãn môi trường như thế nào?
Bạn sẽ so sánh file-based service discovery và discovery do nền tảng cloud cung cấp về tính cập nhật và vận hành ra sao?
Bạn sẽ thiết kế cấu hình scrape riêng cho endpoint yêu cầu TLS hoặc xác thực HTTP như thế nào?
Bạn sẽ kiểm tra lỗi chứng chỉ, SNI hoặc quyền truy cập khi endpoint metrics HTTPS bị scrape thất bại ra sao?
Bạn sẽ bảo vệ endpoint metrics khỏi truy cập công khai nhưng vẫn cho Prometheus thu thập đúng cách như thế nào?
Bạn sẽ phân biệt relabel_configs và metric_relabel_configs theo thời điểm và đối tượng được biến đổi ra sao?
Bạn sẽ giải thích các nhãn nội bộ bắt đầu bằng dấu gạch dưới kép trong quá trình relabeling target như thế nào?
Bạn sẽ xây dựng quy tắc relabeling để chuyển metadata Kubernetes thành nhãn service và namespace có ích ra sao?
Bạn sẽ dùng hành động keep hoặc drop trong relabeling để chỉ thu thập target phù hợp như thế nào?
Bạn sẽ thiết kế quy tắc thay đổi __address__ hoặc __metrics_path__ khi target cần đi qua địa chỉ truy cập khác ra sao?
Bạn sẽ đánh giá ảnh hưởng của labelmap, labeldrop và labelkeep đối với tính nhất quán của các target labels như thế nào?
Bạn sẽ kiểm tra thứ tự áp dụng nhiều quy tắc relabeling để giải thích vì sao target bị loại bỏ ra sao?
Bạn sẽ sử dụng giao diện hoặc thông tin discovery của Prometheus để kiểm tra nhãn trước và sau relabeling như thế nào?
Bạn sẽ lựa chọn metric_relabel_configs để loại metric không cần thiết mà vẫn không che giấu metric kiểm tra scrape như thế nào?
Bạn sẽ phân biệt giảm số target được scrape với giảm số metric được ingest sau scrape về chi phí ra sao?
Bạn sẽ xác định cách bảo đảm job và instance labels vẫn có ý nghĩa khi proxy hoặc load balancer nằm giữa Prometheus và target như thế nào?
Bạn sẽ giải thích Counter phù hợp với những sự kiện tăng dần nào và xử lý reset sau restart ra sao?
Bạn sẽ phân biệt giá trị counter tích lũy với tốc độ tăng của counter khi xây dựng dashboard như thế nào?
Bạn sẽ sử dụng rate và increase cho counter để tránh hiểu sai biểu đồ sau khi một process restart ra sao?
Bạn sẽ xác định vì sao Gauge phù hợp cho số kết nối đang mở hoặc bộ nhớ đang dùng nhưng không phù hợp để đếm tổng request?
Bạn sẽ giải thích cách histogram biểu diễn số lượng quan sát theo bucket, tổng giá trị và số lần đo như thế nào?
Bạn sẽ lựa chọn bucket boundaries của histogram dựa trên SLO độ trễ và độ chính xác cần thiết ra sao?
Bạn sẽ đánh giá chi phí số chuỗi thời gian phát sinh khi bật nhiều bucket trên mọi endpoint như thế nào?
Bạn sẽ phân biệt histogram truyền thống với native histogram theo định dạng, lưu trữ và khả năng truy vấn ra sao?
Bạn sẽ giải thích summary tạo quantile ở phía ứng dụng khác histogram tính quantile ở phía server như thế nào?
Bạn sẽ dùng ví dụ phân phối độ trễ nào để chứng minh không thể lấy trung bình p99 của các instance thành p99 toàn dịch vụ?
Bạn sẽ chọn histogram hay summary khi cần tổng hợp p95 latency của nhiều replica bằng tiêu chí nào?
Bạn sẽ đọc một histogram HTTP latency có nhãn le để hiểu ý nghĩa bucket tích lũy như thế nào?
Bạn sẽ phát hiện metric có đơn vị không nhất quán khi ứng dụng xuất milliseconds nhưng tên metric biểu thị seconds ra sao?
Bạn sẽ thiết kế metric theo kết quả thành công, thất bại và loại thao tác mà không ghi dữ liệu cá nhân vào labels như thế nào?
Bạn sẽ xử lý metric trả NaN, Inf hoặc dữ liệu không hợp lệ từ một exporter bằng những kiểm tra nào?
Bạn sẽ giải thích các kiểu dữ liệu instant vector, range vector, scalar và string trong PromQL như thế nào?
Bạn sẽ phân biệt instant query và range query khi vẽ biểu đồ hoặc kiểm tra giá trị tại một thời điểm ra sao?
Bạn sẽ viết một truy vấn PromQL chọn các series của một metric theo label service và environment như thế nào?
Bạn sẽ so sánh bộ lọc nhãn chính xác và regex trong PromQL về kết quả và chi phí truy vấn như thế nào?
Bạn sẽ phân biệt selector không khớp series nào với giá trị sample bằng không trong một truy vấn PromQL ra sao?
Bạn sẽ dùng sum, avg, min, max và count để tổng hợp metrics giữa nhiều instance như thế nào?
Bạn sẽ thiết kế truy vấn sum by để giữ nhãn service nhưng bỏ nhãn pod trong đồ thị lưu lượng như thế nào?
Bạn sẽ phân biệt sum by và sum without khi muốn kiểm soát các nhãn còn lại của kết quả ra sao?
Bạn sẽ sử dụng rate cho counter HTTP requests để tính request mỗi giây trên cửa sổ thời gian phù hợp như thế nào?
Bạn sẽ phân biệt rate và irate khi phân tích xu hướng dài hạn so với biến động ngắn của counter ra sao?
Bạn sẽ chọn increase hay rate khi báo cáo tổng số sự kiện và tốc độ sự kiện trong một cửa sổ thời gian ra sao?
Bạn sẽ xử lý việc rate trả kết quả nhiễu khi cửa sổ truy vấn chứa quá ít sample ra sao?
Bạn sẽ phân biệt delta, idelta và deriv trên gauge với rate trên counter qua các tình huống đo khác nhau như thế nào?
Bạn sẽ xác định một counter bị reset dựa trên truy vấn và phân biệt với việc target bị thay thế ra sao?
Bạn sẽ dùng histogram_quantile với sum by le và nhãn dịch vụ để ước lượng p95 latency như thế nào?
Bạn sẽ tính tỷ lệ request vượt ngưỡng SLO bằng histogram bucket và tổng count như thế nào?
Bạn sẽ đánh giá sai số quantile của histogram khi các bucket quá rộng quanh ngưỡng quan trọng như thế nào?
Bạn sẽ sử dụng avg_over_time, max_over_time và min_over_time để tìm hiện tượng spike ngắn trên gauge ra sao?
Bạn sẽ sử dụng count_over_time và changes để phân biệt số sample với số lần giá trị thay đổi trong một khoảng thời gian ra sao?
Bạn sẽ phân biệt phép tính trung bình theo thời gian trên một series với trung bình giữa nhiều instance tại cùng thời điểm như thế nào?
Bạn sẽ dùng offset để so sánh metric hiện tại với cùng thời điểm ngày trước hoặc tuần trước như thế nào?
Bạn sẽ đánh giá giới hạn của phép so sánh offset khi tải theo mùa hoặc số instance thay đổi ra sao?
Bạn sẽ lựa chọn subquery khi cần dùng kết quả tính rate làm đầu vào cho hàm theo thời gian ra sao?
Bạn sẽ phân biệt các toán tử so sánh dùng để lọc vector với toán tử có bool modifier trong PromQL như thế nào?
Bạn sẽ xử lý việc cộng hoặc chia hai vector có tập labels khác nhau bằng quy tắc vector matching như thế nào?
Bạn sẽ giải thích on và ignoring giúp chọn nhãn ghép cặp khi kết hợp hai metric như thế nào?
Bạn sẽ quyết định khi nào dùng group_left hoặc group_right cho phép ghép nhiều-một mà không tạo kết quả sai ra sao?
Bạn sẽ kiểm tra lỗi many-to-many matching not allowed trong PromQL bằng cách phân tích nhãn và số series như thế nào?
Bạn sẽ dùng or, and và unless để kết hợp hoặc loại trừ tập series trong những tình huống chẩn đoán nào?
Bạn sẽ tính tỷ lệ HTTP 5xx trên tổng request mà vẫn giữ đúng nhãn của từng service như thế nào?
Bạn sẽ tránh phép chia tạo giá trị không xác định khi mẫu số có thể bằng không bằng chiến lược truy vấn nào?
Bạn sẽ sử dụng label_replace hoặc label_join để xử lý sự khác biệt nhãn giữa các exporter như thế nào?
Bạn sẽ thiết kế truy vấn phát hiện sự thiếu vắng một metric bằng absent hoặc absent_over_time ra sao?
Bạn sẽ phân biệt việc không có sample mới do target down với service thực sự có lưu lượng bằng không như thế nào?
Bạn sẽ chọn bước thời gian query_range để cân bằng độ chi tiết với chi phí và khả năng đọc đồ thị như thế nào?
Bạn sẽ phân tích tác động của lookback delta và staleness markers đến kết quả truy vấn tại một thời điểm ra sao?
Bạn sẽ xác định sai lệch trong truy vấn khi thay đổi window rate từ một phút lên năm phút bằng phép kiểm chứng nào?
Bạn sẽ kiểm tra tại sao kết quả truy vấn trong Prometheus expression browser khác đồ thị Grafana dù dùng cùng biểu thức ra sao?
Bạn sẽ giải thích recording rule giúp giảm chi phí truy vấn lặp lại và tạo metric dẫn xuất như thế nào?
Những tiêu chí về độ phức tạp, tần suất truy vấn và chi phí nào giúp bạn quyết định tạo recording rule?
Bạn sẽ thiết kế tên và labels của recording rule để phân biệt metric gốc với metric đã được tổng hợp ra sao?
Bạn sẽ tổ chức rule files và rule groups theo nhóm ứng dụng hoặc mục tiêu vận hành như thế nào?
Bạn sẽ giải thích evaluation_interval ảnh hưởng đến độ mới của recording rule và thời điểm cảnh báo ra sao?
Bạn sẽ kiểm tra tính nhất quán và độ trễ của recording rule phụ thuộc vào kết quả một rule group khác ra sao?
Bạn sẽ kiểm tra lỗi biểu thức hoặc nhãn của recording rule trước khi triển khai bằng công cụ nào?
Bạn sẽ tổ chức unit test cho recording rule với dữ liệu giả lập để kiểm tra kết quả tổng hợp như thế nào?
Bạn sẽ phân biệt alerting rule với recording rule về điều kiện kích hoạt và dữ liệu kết quả như thế nào?
Bạn sẽ thiết kế alerting rule dựa trên tỷ lệ lỗi thay vì số lỗi tuyệt đối để tránh báo động sai khi lưu lượng biến đổi ra sao?
Bạn sẽ sử dụng for trong alerting rule để hạn chế cảnh báo do spike ngắn mà vẫn không phát hiện quá chậm như thế nào?
Bạn sẽ giải thích trạng thái inactive, pending và firing của một alert qua chuỗi metric theo thời gian như thế nào?
Bạn sẽ lựa chọn keep_firing_for khi cần giảm hiện tượng alert chập chờn trong một sự cố kéo dài ra sao?
Bạn sẽ tạo cảnh báo target down và phân biệt với cảnh báo ứng dụng còn reachable nhưng không phục vụ request như thế nào?
Bạn sẽ đặt labels severity, team và service trong alert mà không tạo một alert mới cho mỗi giá trị động ra sao?
Bạn sẽ sử dụng annotations để đính kèm mô tả, dashboard và runbook cho người trực vận hành như thế nào?
Bạn sẽ kiểm tra rule phát cảnh báo nhiều lần vì nhãn instance thay đổi sau rollout bằng cách nào?
Bạn sẽ phân biệt chức năng đánh giá alerting rule trong Prometheus và chức năng phân phối cảnh báo của Alertmanager ra sao?
Bạn sẽ thiết kế nhóm cảnh báo, route, inhibition và silence để giảm nhiễu trong một sự cố dây chuyền như thế nào?
Bạn sẽ xác định vì sao alert đang firing trong Prometheus nhưng chưa có thông báo tới kênh on-call ra sao?
Bạn sẽ thiết kế cảnh báo burn rate cho SLO theo nhiều cửa sổ thời gian để cân bằng phát hiện nhanh và ít false positive như thế nào?
Bạn sẽ kiểm thử alerting rules bằng các sample đại diện cho trạng thái bình thường, lỗi ngắn và lỗi kéo dài ra sao?
Bạn sẽ quản lý phiên bản của rule và kiểm tra thay đổi trong CI trước khi reload Prometheus như thế nào?
Bạn sẽ giải thích cấu trúc TSDB của Prometheus gồm head block, WAL và các block lưu trên đĩa ra sao?
Bạn sẽ mô tả quá trình một sample mới được ghi vào head và WAL rồi trở thành dữ liệu của block như thế nào?
Bạn sẽ đánh giá vai trò của WAL trong khôi phục sau restart và các giới hạn của bảo đảm dữ liệu ra sao?
Bạn sẽ phân biệt retention theo thời gian và retention theo dung lượng khi quản lý ổ đĩa Prometheus như thế nào?
Bạn sẽ ước lượng dung lượng TSDB từ samples per second, số series và thời gian lưu giữ như thế nào?
Bạn sẽ đánh giá tác động của churn time series do Pod thay đổi hoặc labels động đến bộ nhớ và WAL ra sao?
Bạn sẽ xác định dấu hiệu memory pressure tăng vì active series nhiều chứ không phải vì số target tăng như thế nào?
Bạn sẽ giải thích compaction và retention xóa block cũ theo vòng đời dữ liệu như thế nào?
Bạn sẽ kiểm tra các nguyên nhân khiến Prometheus sử dụng nhiều CPU khi thực hiện compaction hoặc truy vấn lớn ra sao?
Bạn sẽ phân biệt số series đang hoạt động với tổng số series từng tồn tại trong khoảng retention như thế nào?
Bạn sẽ nhận biết tình huống ổ đĩa gần đầy có nguy cơ làm scrape, ghi dữ liệu hoặc truy vấn thất bại ra sao?
Bạn sẽ xác định quy trình snapshot TSDB phục vụ backup và các lưu ý về tính nhất quán như thế nào?
Bạn sẽ phân biệt khôi phục từ snapshot với kỳ vọng có đủ mọi sample mới phát sinh sau snapshot ra sao?
Bạn sẽ so sánh Prometheus federation và remote write theo mục tiêu tổng hợp, lưu trữ dài hạn và khả năng truy vấn như thế nào?
Bạn sẽ lựa chọn kiến trúc nhiều Prometheus độc lập theo cluster so với một Prometheus tập trung dựa trên yêu cầu nào?
Bạn sẽ thiết kế high availability với hai Prometheus scrape cùng target mà vẫn kiểm soát dữ liệu trùng khi tập hợp ra sao?
Bạn sẽ đánh giá giới hạn của Prometheus local TSDB khi cần truy vấn dữ liệu nhiều tháng hoặc nhiều vùng như thế nào?
Bạn sẽ chọn giải pháp remote storage phù hợp khi cần retention dài hạn và khả năng truy vấn xuyên cluster bằng tiêu chí nào?
Bạn sẽ phân biệt remote write queue, shard và retry khi đường truyền tới hệ thống lưu trữ ngoài bị chậm như thế nào?
Bạn sẽ nhận biết remote write backlog và nguy cơ mất sample sau khoảng lỗi kéo dài bằng metric nào?
Bạn sẽ đánh giá tác động của remote write đến CPU, bộ nhớ, băng thông và chi phí của Prometheus ra sao?
Bạn sẽ sử dụng external labels để phân biệt cluster, region hoặc replica trong hệ thống nhiều Prometheus như thế nào?
Bạn sẽ lựa chọn Pushgateway cho một batch job ngắn hạn và xác định rủi ro stale metrics sau khi job hoàn thành ra sao?
Bạn sẽ phân tích nguy cơ mất thông tin tình trạng hoạt động và lưu lại metric cũ khi dùng Pushgateway cho ứng dụng chạy lâu dài ra sao?
Bạn sẽ thiết kế phát hiện job chạy thất bại khi batch job không đẩy được metric hoàn thành như thế nào?
Bạn sẽ chọn node_exporter, blackbox_exporter hoặc ứng dụng tự instrument khi cần đo hạ tầng và tính sẵn sàng dịch vụ ra sao?
Bạn sẽ phân biệt đo ứng dụng từ bên trong với black-box probe từ bên ngoài về khả năng phát hiện lỗi như thế nào?
Bạn sẽ sử dụng blackbox exporter để kiểm tra DNS, TCP, HTTP hoặc TLS và phân tích metric kết quả ra sao?
Bạn sẽ xác định giới hạn của việc dùng exporter trung gian khi dữ liệu nguồn bị lỗi hoặc tốc độ lấy mẫu khác scrape interval như thế nào?
Bạn sẽ tạo datasource Prometheus trong Grafana và xác minh kết nối, quyền và phạm vi dữ liệu như thế nào?
Bạn sẽ thiết kế dashboard Grafana hiển thị request rate, error rate, latency và saturation cho một service ra sao?
Bạn sẽ cấu hình biến dashboard theo environment, service và instance mà không tạo truy vấn tốn kém như thế nào?
Bạn sẽ phân biệt panel dạng time series, stat, table và heatmap theo loại dữ liệu Prometheus như thế nào?
Bạn sẽ tổ chức unit và legend của một panel để không nhầm bytes, seconds và requests per second như thế nào?
Bạn sẽ xác định giới hạn của việc xem histogram như một đường trung bình khi muốn điều tra tail latency ra sao?
Bạn sẽ xây dựng dashboard từ recording rules để giảm tải cho Prometheus khi nhiều người cùng truy cập như thế nào?
Bạn sẽ phân biệt Grafana panel bị no data với Prometheus target down qua các bước kiểm tra nào?
Bạn sẽ kiểm tra Grafana time range, query step và rate interval khi đồ thị hiển thị khác expression browser ra sao?
Bạn sẽ thiết kế dashboard liên kết đến log hoặc traces bằng labels tương ứng để hỗ trợ chẩn đoán như thế nào?
Bạn sẽ xác định quyền truy cập phù hợp để tránh người dùng xem hoặc sửa dashboards và metrics của môi trường nhạy cảm ra sao?
Bạn sẽ đánh giá chi phí truy vấn Grafana khi refresh quá thường xuyên và dashboard có nhiều panel nặng như thế nào?
Bạn sẽ thiết lập quy trình provision dashboard và datasource bằng cấu hình phiên bản để tránh chỉnh sửa thủ công thiếu kiểm soát ra sao?
Bạn sẽ giải thích cardinality của labels ảnh hưởng đến số series và tài nguyên Prometheus như thế nào?
Bạn sẽ ước lượng số series mới khi thêm nhãn user_id, route, status và instance vào một metric ra sao?
Bạn sẽ so sánh nhãn route template với raw URL chứa ID để xác định nguồn bùng nổ cardinality như thế nào?
Bạn sẽ thiết kế quy ước nhãn cho endpoint, method, status và environment mà vẫn hỗ trợ truy vấn điều tra ra sao?
Bạn sẽ phát hiện một metric chứa tag động do input người dùng và quyết định sửa ở instrumentation hay metric relabeling như thế nào?
Bạn sẽ dùng các chỉ số về head series, samples ingested và series churn để điều tra Prometheus tăng RAM như thế nào?
Bạn sẽ kiểm tra một truy vấn PromQL tốn nhiều bộ nhớ do phép ghép vector hoặc regex trên nhãn có cardinality cao ra sao?
Bạn sẽ phân biệt tăng số sample theo thời gian với tăng số series do labels mới về chi phí lưu trữ như thế nào?
Bạn sẽ xác định metric nào nên được loại bỏ hoặc tổng hợp để giữ chi phí trong ngân sách mà không mất tín hiệu SLO ra sao?
Bạn sẽ đánh giá nguy cơ metric_relabel_configs che khuất lỗi thực sự khi loại bỏ nhiều series để giảm cardinality như thế nào?
Bạn sẽ thiết kế ngưỡng cảnh báo cho số active series, TSDB disk usage và scrape failures để phát hiện quá tải sớm ra sao?
Bạn sẽ giới hạn truy vấn quá rộng hoặc dashboard bất hợp lý để bảo vệ hệ thống giám sát khỏi cạn tài nguyên như thế nào?
Bạn sẽ lập quy trình review metric mới bao gồm tên, unit, label cardinality, mục đích và chi phí như thế nào?
Bạn sẽ kiểm tra cấu hình Prometheus và rule files trước khi reload để tránh gián đoạn thu thập như thế nào?
Bạn sẽ đánh giá tác động của lỗi cấu hình discovery khiến toàn bộ target biến mất sau reload bằng những bước nào?
Bạn sẽ phân biệt lỗi scrape, lỗi TSDB, lỗi remote write và lỗi truy vấn bằng dashboard nội bộ của Prometheus ra sao?
Bạn sẽ tổ chức cập nhật Prometheus theo từng instance để giảm rủi ro mất quan sát trong lúc nâng cấp như thế nào?
Bạn sẽ kiểm soát quyền truy cập giao diện Prometheus, API truy vấn và endpoint quản trị theo ranh giới mạng nào?
Bạn sẽ bảo vệ token, certificate và thông tin xác thực của scrape target khi Prometheus chạy trên Kubernetes ra sao?
Bạn sẽ kiểm tra Prometheus có đang ghi dữ liệu từ endpoint không đáng tin cậy và nguy cơ metric poisoning như thế nào?
Bạn sẽ phân biệt nhãn lấy từ target và nhãn xuất bởi ứng dụng để tránh giả mạo thông tin service hoặc environment ra sao?
Bạn sẽ thiết kế quy trình kiểm thử phục hồi khi Prometheus bị mất Pod, đầy đĩa hoặc lỗi WAL như thế nào?
Nếu target hiển thị DOWN nhưng gọi endpoint metrics trực tiếp thành công, bạn sẽ kiểm tra discovery, relabeling, TLS và đường mạng ra sao?
Nếu ServiceMonitor tồn tại nhưng Prometheus không thấy target nào, bạn sẽ lần theo selector, port và RBAC như thế nào?
Nếu một dashboard báo tỷ lệ lỗi âm hoặc đột ngột bằng không sau rollout, bạn sẽ kiểm tra counter reset và cách tổng hợp ra sao?
Nếu p99 latency của nhiều instance đều cao nhưng biểu đồ tổng hợp lại thấp, bạn sẽ kiểm tra histogram và truy vấn quantile như thế nào?
Nếu remote write queue tăng liên tục mà local scrape vẫn khỏe, bạn sẽ phân tích backlog, băng thông và backend nhận ghi ra sao?
Nếu Prometheus tăng RAM đột biến sau một bản phát hành, bạn sẽ điều tra nhãn động, series churn và metric mới theo trình tự nào?
Nếu alert đang firing nhưng on-call không nhận thông báo, bạn sẽ phân biệt lỗi đánh giá rule với routing và inhibition của Alertmanager ra sao?
Nếu Grafana hiển thị No data trong khi Prometheus expression browser có sample, bạn sẽ kiểm tra datasource, labels và query time range như thế nào?
Nếu TSDB gần đầy trước hạn retention, bạn sẽ phân tích ingest rate, histogram buckets, cardinality và lựa chọn giảm tải như thế nào?
Nếu một query PromQL bị timeout chỉ khi người dùng chọn khoảng thời gian dài, bạn sẽ tối ưu biểu thức, step hoặc recording rules ra sao?
Bạn sẽ thiết kế kiến trúc Prometheus cho hệ thống Java trên Kubernetes gồm discovery, relabeling, PromQL, rules, Grafana, HA và retention theo SLO như thế nào?
