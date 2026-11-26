Bạn mô tả vai trò của Grafana trong hệ thống quan sát metrics, logs và traces như thế nào?
Bạn phân biệt Grafana với các backend lưu trữ và xử lý telemetry như Prometheus, Loki và Tempo ra sao?
Bạn xác định mục tiêu vận hành nào cần giải quyết trước khi thiết kế dashboard cho một dịch vụ như thế nào?
Bạn lựa chọn các tín hiệu phù hợp để dashboard phản ánh availability, latency, traffic và saturation ra sao?
Bạn phân biệt dashboard phục vụ trực ca với dashboard phân tích xu hướng và capacity planning như thế nào?
Bạn thiết kế cấu trúc dashboard từ chỉ số tổng thể đến chi tiết instance hoặc endpoint theo nguyên tắc nào?
Bạn xác định người xem, câu hỏi cần trả lời và hành động tiếp theo trước khi thêm panel như thế nào?
Bạn đánh giá một dashboard có thể hành động được bằng những tiêu chí nào?
Bạn tổ chức dashboard theo service, team, environment và nghiệp vụ để người dùng tìm nhanh ra sao?
Bạn lựa chọn cách tái sử dụng dashboard mẫu mà vẫn giữ được khác biệt giữa các dịch vụ như thế nào?
Bạn phân biệt dashboard tổng quan với dashboard chuyên biệt cho một sự cố hoặc một dependency ra sao?
Bạn xác định những chỉ số không nên đặt chung một biểu đồ vì khác đơn vị hoặc ngữ nghĩa như thế nào?
Bạn sắp xếp thứ tự panel để người trực nhận ra phạm vi ảnh hưởng trước khi đi vào chi tiết như thế nào?
Bạn đánh giá dashboard quá nhiều panel ảnh hưởng tới thời gian tải và khả năng tập trung ra sao?
Bạn xác định cách đo hiệu quả dashboard thông qua thời gian phát hiện và khoanh vùng sự cố như thế nào?
Bạn xây dựng quy ước tên dashboard và folder để tránh trùng lặp trong một tổ chức lớn ra sao?
Bạn phân biệt datasource UID, tên hiển thị và loại datasource trong cấu hình Grafana như thế nào?
Bạn cấu hình Prometheus datasource để Grafana truy vấn đúng endpoint và môi trường ra sao?
Bạn xác định khi nào Grafana cần truy cập Prometheus trực tiếp và khi nào nên dùng proxy datasource như thế nào?
Bạn kiểm tra TLS, authentication và network access khi Grafana không kết nối được Prometheus ra sao?
Bạn phân biệt lỗi datasource unavailable với lỗi truy vấn PromQL không hợp lệ như thế nào?
Bạn thiết kế datasource Loki và xác minh Grafana truy vấn được logs theo tenant hoặc namespace ra sao?
Bạn cấu hình datasource Tempo để truy vấn trace và liên kết với các nguồn telemetry khác như thế nào?
Bạn xác định những thông tin cần khai báo để Grafana truy cập backend qua reverse proxy ra sao?
Bạn kiểm tra timeout và giới hạn response khi datasource trả về lượng dữ liệu lớn như thế nào?
Bạn lựa chọn chế độ truy cập browser hay server proxy dựa trên kiến trúc mạng và bảo mật ra sao?
Bạn quản lý datasource credentials bằng secure settings thay vì lưu bí mật trong dashboard như thế nào?
Bạn phân biệt datasource mặc định với datasource được chọn riêng trong từng panel như thế nào?
Bạn thiết kế datasource variables để chuyển môi trường hoặc cluster mà không nhân bản dashboard ra sao?
Bạn xử lý datasource UID thay đổi giữa staging và production khi provisioning dashboard như thế nào?
Bạn kiểm tra vì sao datasource test thành công nhưng panel vẫn trả lỗi truy vấn ra sao?
Bạn tổ chức nhiều Prometheus datasource theo region hoặc cluster mà vẫn dễ so sánh dữ liệu như thế nào?
Bạn đánh giá lợi ích và rủi ro khi dùng datasource federation hoặc một Prometheus tổng hợp trong Grafana ra sao?
Bạn xác định datasource nào cần quyền chỉ đọc và giới hạn truy vấn phù hợp như thế nào?
Bạn cấu hình datasource proxy để tránh trình duyệt người dùng truy cập trực tiếp backend nội bộ ra sao?
Bạn kiểm tra sự tương thích phiên bản datasource plugin sau khi nâng cấp Grafana như thế nào?
Bạn phân biệt truy vấn trực tiếp tới backend với truy vấn qua datasource plugin về khả năng hỗ trợ tính năng ra sao?
Bạn xác định cách tổ chức datasource provisioning để các môi trường có cấu hình nhất quán như thế nào?
Bạn sử dụng Query Inspector để kiểm tra request, response và thời gian truy vấn ra sao?
Bạn xác định nguyên nhân một datasource trả dữ liệu nhưng Grafana không thể diễn giải thành time series như thế nào?
Bạn phân biệt query range với instant query khi xây dựng panel Prometheus như thế nào?
Bạn viết PromQL để thể hiện request rate theo service và route trong một dashboard như thế nào?
Bạn lựa chọn rate, increase hoặc irate cho biểu đồ tốc độ request theo khoảng thời gian nào?
Bạn giải thích vì sao cần áp dụng rate cho từng counter trước khi tổng hợp nhiều instance như thế nào?
Bạn xây dựng truy vấn error ratio có điều kiện traffic tối thiểu để tránh tỷ lệ lỗi nhiễu ra sao?
Bạn lựa chọn histogram_quantile để hiển thị p95 latency từ histogram Prometheus như thế nào?
Bạn xác định nhãn le cần được giữ khi tổng hợp histogram bucket trước khi tính percentile ra sao?
Bạn phân biệt percentile tính từ histogram tổng hợp với trung bình latency của các instance như thế nào?
Bạn chọn khoảng rate window phù hợp với scrape interval và độ phân giải dashboard như thế nào?
Bạn kiểm tra một biểu đồ bị rỗng do range selector quá ngắn so với số mẫu scrape như thế nào?
Bạn sử dụng aggregation theo service, instance, namespace hoặc region để trả lời câu hỏi vận hành nào?
Bạn xác định label nào cần giữ lại để dashboard có thể drill down tới instance gặp vấn đề như thế nào?
Bạn kiểm tra vector matching hoặc phép join trong PromQL khi panel không trả kết quả như mong đợi ra sao?
Bạn phân biệt giá trị zero với vector rỗng khi thiết kế biểu đồ và stat panel như thế nào?
Bạn xử lý metric không tồn tại trong một số môi trường mà không làm panel hiển thị sai ý nghĩa như thế nào?
Bạn lựa chọn legend format để biểu đồ có thể phân biệt nhiều series mà không hiển thị quá nhiều nhãn ra sao?
Bạn xác định nguyên nhân một truy vấn PromQL chạy tốt trong Prometheus UI nhưng chậm trong Grafana như thế nào?
Bạn sử dụng min step, max data points và query resolution để kiểm soát số điểm dữ liệu trả về ra sao?
Bạn đánh giá tác động của dashboard time range dài tới chi phí và thời gian truy vấn Prometheus như thế nào?
Bạn sử dụng recording rules khi panel có phép tổng hợp nặng được nhiều dashboard dùng chung như thế nào?
Bạn xác định sự khác nhau giữa dashboard query và alert query để tránh dùng sai độ phân giải dữ liệu ra sao?
Bạn xây dựng biểu đồ so sánh traffic hiện tại với cùng khung thời gian ngày trước bằng PromQL như thế nào?
Bạn kiểm tra timezone và timestamp khi so sánh dữ liệu giữa các region như thế nào?
Bạn lựa chọn unit, decimals và threshold để panel hiển thị số liệu Prometheus đúng ngữ nghĩa ra sao?
Bạn sử dụng transformations để đổi tên, sắp xếp hoặc lọc các field của kết quả truy vấn như thế nào?
Bạn phân biệt phép biến đổi dữ liệu ở Grafana với phép tổng hợp trực tiếp trong PromQL ra sao?
Bạn xác định khi nào nên dùng transformation join và khi nào nên viết truy vấn kết hợp ở datasource như thế nào?
Bạn kiểm tra join transformation có làm nhân bản hàng do khóa ghép không duy nhất ra sao?
Bạn lựa chọn merge, join by field hoặc concatenate theo cấu trúc dữ liệu cần trình bày như thế nào?
Bạn xác định thứ tự transformations ảnh hưởng đến kết quả panel như thế nào?
Bạn xử lý field type không nhất quán sau transformation để tránh hiển thị sai như thế nào?
Bạn đánh giá tác động của transformation phía Grafana lên bộ nhớ trình duyệt khi kết quả có hàng trăm nghìn bản ghi ra sao?
Bạn quyết định khi nào nên lọc dữ liệu tại datasource thay vì tải toàn bộ về Grafana rồi mới transform như thế nào?
Bạn sử dụng field overrides để áp dụng unit, màu và threshold riêng cho từng series như thế nào?
Bạn lựa chọn visualization phù hợp giữa time series, stat, gauge, bar gauge, table, heatmap và histogram theo câu hỏi nào?
Bạn xác định khi nào gauge có thể gây hiểu nhầm do không thể hiện xu hướng theo thời gian như thế nào?
Bạn thiết kế stat panel hiển thị giá trị hiện tại và mức thay đổi so với kỳ trước ra sao?
Bạn cấu hình threshold theo mức warning và critical mà vẫn bảo đảm người xem hiểu ý nghĩa màu sắc như thế nào?
Bạn xác định cách biểu diễn giá trị null hoặc no data để phân biệt thiếu dữ liệu với trạng thái bình thường ra sao?
Bạn lựa chọn cách hiển thị đơn vị thời gian, byte, phần trăm và tốc độ để tránh đọc sai số liệu như thế nào?
Bạn sử dụng table panel để hiển thị top endpoint có error rate cao và cho phép sắp xếp ra sao?
Bạn thiết kế heatmap latency từ histogram bucket để quan sát phân bố thay vì chỉ xem percentile như thế nào?
Bạn kiểm tra panel có đang hiển thị dữ liệu đã được reduce hoặc aggregate ngoài dự kiến bằng cách nào?
Bạn đánh giá khi nào nên dùng panel repeat theo service và khi nào nên dùng một bảng tổng hợp như thế nào?
Bạn thiết kế panel có nhiều query A, B và C để so sánh nguồn dữ liệu hoặc nhóm đối tượng ra sao?
Bạn sử dụng expressions để kết hợp kết quả query trong Grafana theo trường hợp nào?
Bạn xác định giới hạn của Grafana expressions so với phép tính tại Prometheus hoặc backend khác như thế nào?
Bạn kiểm tra query refId và dependency giữa các query khi panel có nhiều nguồn dữ liệu ra sao?
Bạn tổ chức legend và tooltip để người xem so sánh series mà không làm biểu đồ quá rối như thế nào?
Bạn thiết kế dashboard có annotation cho deploy event và incident để liên hệ thay đổi với metric ra sao?
Bạn lựa chọn dashboard links và data links để điều hướng từ tổng quan đến chi tiết như thế nào?
Bạn tạo liên kết từ một service panel sang dashboard khác bằng các biến service và environment ra sao?
Bạn truyền thời gian đang chọn và biến lọc qua dashboard link như thế nào?
Bạn xác định rủi ro tạo URL link chứa thông tin nhạy cảm hoặc token trong data link ra sao?
Bạn thiết kế liên kết từ metric đến log query Loki theo service, pod và time range như thế nào?
Bạn cấu hình liên kết từ log record sang trace bằng trace ID và datasource Tempo ra sao?
Bạn phân biệt derived fields của Loki với data links của panel trong việc mở trace liên quan như thế nào?
Bạn xác định điều kiện cần có trong log labels hoặc structured metadata để tạo liên kết trace chính xác ra sao?
Bạn thiết kế liên kết từ trace span sang log query để điều tra cùng một request như thế nào?
Bạn kiểm tra một trace-to-logs link trả về quá nhiều log do thiếu bộ lọc service hoặc time range ra sao?
Bạn sử dụng Explore để chuyển từ metric bất thường sang logs và traces liên quan như thế nào?
Bạn phân biệt Explore với dashboard trong quá trình điều tra sự cố ra sao?
Bạn sử dụng split view trong Explore để so sánh hai query hoặc hai nguồn dữ liệu như thế nào?
Bạn lựa chọn time range và time shift khi đối chiếu log hoặc metric trước và sau một deployment ra sao?
Bạn xây dựng truy vấn LogQL để lọc logs theo service, namespace và severity như thế nào?
Bạn phân biệt stream selector với pipeline stages trong LogQL khi lọc nội dung log ra sao?
Bạn lựa chọn label index và structured metadata để cân bằng khả năng tìm kiếm với cardinality của Loki như thế nào?
Bạn sử dụng parser stages để trích xuất status code hoặc duration từ structured logs như thế nào?
Bạn xác định cách tạo metric từ log query bằng LogQL để theo dõi số lỗi theo thời gian ra sao?
Bạn thiết kế biểu đồ tỷ lệ log ERROR có xét tổng số request để tránh diễn giải sai như thế nào?
Bạn phân biệt logs được lọc ở stream selector với logs được lọc sau khi parse nội dung ra sao?
Bạn kiểm tra truy vấn LogQL chậm do selector quá rộng hoặc pipeline parse tốn tài nguyên như thế nào?
Bạn xác định ảnh hưởng của log labels có cardinality cao tới hiệu năng Loki và Explore như thế nào?
Bạn dùng log context hoặc surrounding lines để hiểu chuỗi sự kiện quanh một lỗi như thế nào?
Bạn lựa chọn cách hiển thị log dạng table hoặc logs view theo loại điều tra như thế nào?
Bạn kiểm tra vì sao log có trong backend nhưng Explore không tìm thấy do time range hoặc timezone như thế nào?
Bạn thiết kế dashboard log volume theo service và severity mà không cần index mọi nội dung log ra sao?
Bạn xác định cách chuyển từ log query sang metric panel để so sánh số lỗi với throughput như thế nào?
Bạn xây dựng truy vấn TraceQL để tìm trace theo service, span name hoặc status như thế nào?
Bạn phân biệt TraceQL với truy vấn theo trace ID chính xác trong Explore như thế nào?
Bạn lựa chọn điều kiện tìm trace có span lỗi và latency vượt ngưỡng ra sao?
Bạn thiết kế truy vấn tìm trace có dependency chậm dựa trên thời lượng span như thế nào?
Bạn xác định giới hạn truy vấn trace khi backend Tempo chỉ có một phần dữ liệu do sampling như thế nào?
Bạn sử dụng trace search để xác định service hoặc operation đóng góp nhiều nhất vào latency ra sao?
Bạn lựa chọn cách hiển thị trace waterfall để giải thích quan hệ parent-child và thời gian chờ như thế nào?
Bạn xác định nguyên nhân trace không hiển thị đủ span khi dữ liệu được ingest không đầy đủ ra sao?
Bạn thiết kế liên kết từ dashboard service overview tới trace search có sẵn bộ lọc service và thời gian như thế nào?
Bạn kiểm tra trace datasource có trả đúng resource attributes để Grafana hiển thị service name như thế nào?
Bạn phân biệt trace search với trace metrics khi muốn xem xu hướng latency trên thời gian dài ra sao?
Bạn kết hợp metrics từ Prometheus và traces từ Tempo để xác định ảnh hưởng của một dependency như thế nào?
Bạn xác định khi nào cần dùng exemplars để liên kết metric sample với trace tương ứng như thế nào?
Bạn cấu hình exemplar support và datasource mapping để mở trace từ điểm dữ liệu metric ra sao?
Bạn xử lý trường hợp exemplar có trace ID nhưng trace đã hết retention hoặc bị sampling loại bỏ như thế nào?
Bạn thiết kế một luồng điều tra RED từ request rate sang error logs và trace lỗi ra sao?
Bạn thiết kế dashboard USE cho host hoặc container và liên kết tới logs của workload tương ứng như thế nào?
Bạn phân biệt dashboard theo tín hiệu với dashboard theo service khi tổ chức điều tra xuyên hệ thống ra sao?
Bạn sử dụng dashboard variables để lọc theo cluster, namespace, service và instance như thế nào?
Bạn lựa chọn query variable, custom variable và constant variable theo mục tiêu tái sử dụng nào?
Bạn thiết kế biến phụ thuộc để danh sách service thay đổi theo cluster đang chọn như thế nào?
Bạn xác định cách dùng multi-value variable và include all option trong truy vấn Prometheus ra sao?
Bạn kiểm tra regex hoặc multi-value formatting khiến PromQL hoặc LogQL lọc sai như thế nào?
Bạn lựa chọn refresh mode cho variable để danh sách cập nhật mà không tạo nhiều truy vấn không cần thiết ra sao?
Bạn phân biệt variable refresh khi dashboard load với khi time range thay đổi như thế nào?
Bạn thiết kế biến datasource để cùng một dashboard chạy được trên nhiều môi trường như thế nào?
Bạn xác định rủi ro variable cho phép người xem chọn datasource ngoài phạm vi được cấp quyền ra sao?
Bạn tổ chức biến environment và cluster để dashboard không trộn dữ liệu production với staging như thế nào?
Bạn sử dụng ad hoc filters để lọc dữ liệu linh hoạt trong Explore hoặc dashboard ra sao?
Bạn kiểm tra panel repeat khi variable có nhiều giá trị và số lượng panel tăng quá lớn như thế nào?
Bạn đánh giá ảnh hưởng của nhiều query variable lồng nhau lên thời gian tải dashboard ra sao?
Bạn thiết kế default variable values để dashboard mở ra luôn hiển thị phạm vi có ý nghĩa như thế nào?
Bạn xử lý trường hợp variable không có giá trị tương ứng trong một môi trường mới như thế nào?
Bạn phân biệt dashboard variable với template variable của provisioning như thế nào?
Bạn xác định cách giữ biến và lựa chọn của người dùng khi chia sẻ một dashboard link ra sao?
Bạn kiểm tra dashboard có hoạt động đúng khi người xem không có quyền truy cập một datasource variable cụ thể như thế nào?
Bạn thiết kế Grafana alert rule dựa trên metric query và điều kiện đánh giá như thế nào?
Bạn phân biệt Grafana-managed alert rule với data source-managed alert rule theo nơi thực thi và quản lý ra sao?
Bạn xác định khi nào nên dùng alert rule tại Prometheus và khi nào dùng unified alerting của Grafana như thế nào?
Bạn thiết kế pending period và evaluation interval để giảm cảnh báo nhiễu nhưng vẫn phát hiện sự cố kịp thời ra sao?
Bạn phân biệt trạng thái No Data, Error, Normal, Pending và Alerting trong Grafana alerting như thế nào?
Bạn xác định hành vi cần có khi query không trả dữ liệu hoặc datasource lỗi trong một alert rule như thế nào?
Bạn tổ chức labels và annotations để alert có service, team, severity và runbook link như thế nào?
Bạn lựa chọn notification policy để định tuyến alert theo team, environment và mức độ nghiêm trọng ra sao?
Bạn thiết kế contact point và notification template để thông báo có đủ bối cảnh xử lý như thế nào?
Bạn phân biệt grouping, mute timing và silencing trong Grafana Alerting ra sao?
Bạn kiểm tra một alert firing nhưng không gửi thông báo do notification policy hoặc contact point như thế nào?
Bạn xác định cách tránh alert trùng lặp khi cùng sự cố được phát hiện bởi Grafana và Prometheus như thế nào?
Bạn thiết kế alert dựa trên SLO burn rate và liên kết tới dashboard error budget ra sao?
Bạn kiểm tra alert rule có dùng đúng datasource và đúng query refId sau khi provisioning như thế nào?
Bạn kiểm thử alert bằng dữ liệu giả lập và xác nhận toàn bộ đường đi đến contact point ra sao?
Bạn xác định những cảnh báo chỉ nên hiển thị trên dashboard và những cảnh báo cần gửi tới người trực như thế nào?
Bạn thiết kế dashboard hiển thị trạng thái alert theo service mà không biến dashboard thành danh sách cảnh báo quá tải ra sao?
Bạn phân biệt annotation do người dùng tạo với annotation tự động từ alert hoặc event source như thế nào?
Bạn lựa chọn chính sách mute hoặc silence trong cửa sổ bảo trì để tránh che mất sự cố ngoài phạm vi ra sao?
Bạn xác định cách kiểm tra alert recovery và thông báo resolved có được gửi đúng như mong đợi ra sao?
Bạn tổ chức quyền truy cập Grafana theo tổ chức, folder, dashboard và datasource như thế nào?
Bạn phân biệt quyền Viewer, Editor, Admin và quyền theo folder trong mô hình phân quyền Grafana ra sao?
Bạn thiết kế RBAC để một nhóm chỉ sửa dashboard của mình nhưng vẫn xem dashboard dùng chung như thế nào?
Bạn xác định rủi ro cấp quyền Editor trên datasource khi người dùng có thể truy vấn dữ liệu ngoài phạm vi như thế nào?
Bạn lựa chọn folder permissions và datasource permissions để phân tách môi trường production với staging ra sao?
Bạn kiểm tra một dashboard bị chia sẻ công khai hoặc qua snapshot có thể lộ dữ liệu nhạy cảm như thế nào?
Bạn tổ chức SSO và role mapping để cấp quyền Grafana theo nhóm người dùng như thế nào?
Bạn đánh giá việc bật anonymous access trong một môi trường nội bộ có những rủi ro nào?
Bạn quản lý API token và service account token cho automation mà không dùng tài khoản cá nhân như thế nào?
Bạn xác định cách giới hạn quyền của service account chỉ đủ provisioning dashboard hoặc datasource ra sao?
Bạn kiểm tra audit log hoặc lịch sử thay đổi để xác định ai đã sửa một dashboard như thế nào?
Bạn thiết kế chính sách bảo vệ datasource credentials và secret trong dashboard JSON ra sao?
Bạn phân biệt dashboard variables với quyền lọc dữ liệu thực sự ở backend như thế nào?
Bạn xác định vì sao ẩn một panel hoặc variable không phải là biện pháp kiểm soát truy cập dữ liệu ra sao?
Bạn bảo vệ các plugin datasource và panel trước nguy cơ cài extension không được phê duyệt như thế nào?
Bạn đánh giá rủi ro plugin bên thứ ba có quyền truy cập dữ liệu hoặc trình duyệt như thế nào?
Bạn lựa chọn cách giới hạn quyền truy cập Explore khi người dùng chỉ được xem một số dashboard đã duyệt ra sao?
Bạn tổ chức phân quyền giữa người tạo dashboard, người phê duyệt và người trực vận hành như thế nào?
Bạn kiểm tra cấu hình reverse proxy, HTTPS và cookie khi Grafana chạy sau ingress như thế nào?
Bạn xác định ảnh hưởng của root_url và serve_from_sub_path khi Grafana được phục vụ dưới một đường dẫn con ra sao?
Bạn phân biệt lỗi đăng nhập SSO với lỗi datasource authentication khi người dùng mở dashboard như thế nào?
Bạn thiết kế provisioning datasource bằng file cấu hình để môi trường mới được khởi tạo nhất quán ra sao?
Bạn tổ chức provisioning dashboard từ file JSON và folder mapping như thế nào?
Bạn phân biệt provisioning dashboard với tạo hoặc sửa dashboard trực tiếp qua giao diện như thế nào?
Bạn xác định cách Grafana xử lý dashboard được provisioning khi người dùng chỉnh sửa trên UI ra sao?
Bạn kiểm soát allowUiUpdates hoặc cơ chế tương đương để tránh drift giữa file cấu hình và trạng thái runtime như thế nào?
Bạn thiết kế cấu trúc repository cho dashboard JSON, datasource provisioning và alert rules ra sao?
Bạn quản lý UID dashboard ổn định để link và alert không bị hỏng khi chuyển môi trường như thế nào?
Bạn xử lý xung đột UID khi import dashboard từ nhiều nhóm hoặc nhiều nguồn khác nhau ra sao?
Bạn kiểm tra dashboard JSON có chứa datasource UID hoặc ID không hợp lệ trong môi trường đích bằng cách nào?
Bạn sử dụng Grafana API hoặc Terraform provider để quản lý dashboard và datasource theo quy trình nào?
Bạn lựa chọn provisioning file, API hoặc Infrastructure as Code theo khả năng review và rollback như thế nào?
Bạn thiết kế CI để kiểm tra JSON dashboard, datasource reference và rule trước khi deploy ra sao?
Bạn kiểm thử dashboard sau provisioning bằng smoke query tới Prometheus, Loki và Tempo như thế nào?
Bạn tổ chức canary rollout dashboard mới cho một folder hoặc nhóm người dùng trước khi áp dụng rộng ra sao?
Bạn xác định cách rollback dashboard và alert rule khi thay đổi làm hỏng trải nghiệm trực ca như thế nào?
Bạn quản lý thay đổi dashboard có phụ thuộc vào metric hoặc log schema vừa được đổi tên ra sao?
Bạn phân biệt dashboard version history với version control trong Git về khả năng kiểm toán như thế nào?
Bạn kiểm tra cấu hình provisioning có idempotent khi triển khai lại nhiều lần hay không ra sao?
Bạn xác định cách xóa dashboard cũ đã provisioning mà không vô tình xóa dashboard do nhóm khác quản lý như thế nào?
Bạn tổ chức review thay đổi dashboard để phát hiện query tốn tài nguyên hoặc panel gây hiểu nhầm ra sao?
Bạn đánh giá tác động của nâng cấp Grafana tới dashboard JSON schema và plugin compatibility như thế nào?
Bạn lập kế hoạch nâng cấp Grafana mà bảo đảm dashboard và datasource vẫn hoạt động như thế nào?
Bạn phân biệt lỗi query chậm ở Grafana với lỗi backend Prometheus, Loki hoặc Tempo như thế nào?
Bạn sử dụng Query Inspector để đo thời gian request, kích thước response và lỗi datasource ra sao?
Bạn xác định nguyên nhân dashboard tải chậm do quá nhiều panel chạy đồng thời như thế nào?
Bạn đánh giá ảnh hưởng của refresh interval quá ngắn lên tải backend và trình duyệt ra sao?
Bạn lựa chọn dashboard time range mặc định để cân bằng thông tin hữu ích với chi phí truy vấn như thế nào?
Bạn kiểm tra query có bị chạy nhiều lần do panel repeat hoặc variable refresh như thế nào?
Bạn xác định khi nào cần cache datasource query và khi nào dữ liệu cần tính mới gần thời gian thực ra sao?
Bạn phân biệt query timeout, max data points và giới hạn response size khi panel không hiển thị đầy đủ dữ liệu như thế nào?
Bạn tối ưu PromQL hoặc LogQL khi panel chỉ cần top vài đối tượng nhưng truy vấn đang lấy toàn bộ dữ liệu ra sao?
Bạn kiểm tra transformations đang chạy trên hàng triệu dòng thay vì đẩy lọc xuống backend như thế nào?
Bạn đánh giá ảnh hưởng của nhiều datasource và nhiều plugin tới bộ nhớ trình duyệt ra sao?
Bạn xác định một panel rỗng do không có dữ liệu, lỗi query hay lỗi mapping field bằng cách nào?
Bạn xử lý timezone, daylight saving và khoảng thời gian không có mẫu khi dashboard so sánh nhiều region như thế nào?
Bạn phân biệt lỗi frontend JavaScript với lỗi API backend khi một dashboard chỉ hiển thị trang trắng ra sao?
Bạn kiểm tra log Grafana và trạng thái plugin khi datasource plugin không khởi tạo được như thế nào?
Bạn điều tra vì sao một dashboard hiển thị dữ liệu khác nhau giữa người dùng có role khác nhau như thế nào?
Bạn xác định nguồn gây ra panel bị nhân đôi hoặc legend bị sai sau khi đổi query như thế nào?
Bạn xử lý sự cố dashboard mất datasource sau khi restore hoặc migrate Grafana database như thế nào?
Bạn kiểm tra việc import dashboard từ phiên bản mới hơn gây lỗi field hoặc visualization ra sao?
Bạn xây dựng runbook từ một panel bất thường tới query, datasource và backend để xác định nguyên nhân gốc như thế nào?
Bạn xác định các tiêu chí nghiệm thu dashboard Grafana dựa trên độ chính xác, khả năng drill down, hiệu năng, bảo mật và khả năng bảo trì như thế nào?
