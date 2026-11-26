Bạn xác định mục tiêu của hệ thống cảnh báo dựa trên sự cố ảnh hưởng người dùng thay vì chỉ số kỹ thuật đơn lẻ như thế nào?
Bạn phân biệt recording rule và alerting rule trong Prometheus theo mục đích và kết quả đánh giá ra sao?
Bạn giải thích hành trình từ metric được scrape đến rule evaluation, cảnh báo firing và thông báo cho người trực như thế nào?
Bạn quyết định chỉ số nào xứng đáng tạo cảnh báo thay vì chỉ hiển thị trên dashboard dựa trên tiêu chí nào?
Bạn phân biệt symptom-based alert với cause-based alert khi xây dựng chính sách giám sát dịch vụ ra sao?
Bạn xác định người chịu trách nhiệm phản ứng và hành động cần thiết trước khi tạo một alert như thế nào?
Bạn chuyển yêu cầu SLO của một dịch vụ thành tín hiệu cảnh báo có thể hành động ra sao?
Bạn đánh giá sự khác nhau giữa một cảnh báo phục vụ xử lý ngay và một cảnh báo phục vụ cải thiện dài hạn như thế nào?
Bạn tổ chức quy trình từ phát hiện dấu hiệu bất thường đến xác nhận tác động và xử lý sự cố ra sao?
Bạn xác định những yếu tố nào khiến một cảnh báo hữu ích nhưng không gây quá nhiều gián đoạn cho đội vận hành?
Bạn phân biệt metric, time series, sample và label set khi viết PromQL như thế nào?
Bạn giải thích cách Prometheus định danh một chuỗi thời gian bằng tên metric và tập nhãn ra sao?
Bạn xác định tác động của scrape interval đến độ trễ phát hiện và tính ổn định của một alert như thế nào?
Bạn phân biệt các metric type counter, gauge, histogram và summary khi chọn biểu thức cảnh báo ra sao?
Bạn lựa chọn metric counter để phát hiện tăng lỗi ứng dụng mà không suy diễn trực tiếp từ giá trị cộng dồn như thế nào?
Bạn quyết định nên dùng gauge hay counter cho một tín hiệu vận hành dựa trên hành vi cập nhật dữ liệu ra sao?
Bạn giải thích histogram bucket và các chuỗi _sum, _count có thể hỗ trợ cảnh báo độ trễ như thế nào?
Bạn đánh giá giới hạn của summary quantile khi muốn tổng hợp kết quả từ nhiều instance ra sao?
Bạn xác định những nhãn nào nên giữ trên metric để có thể định tuyến cảnh báo đến đúng người chịu trách nhiệm?
Bạn nhận diện nguy cơ label cardinality tăng khi dùng user ID, URL động hoặc request ID ra sao?
Bạn thiết kế quy ước tên metric, đơn vị và label để biểu thức PromQL dễ tái sử dụng như thế nào?
Bạn phân biệt metric ứng dụng và metric hạ tầng khi xác định triệu chứng của một sự cố như thế nào?
Bạn chọn bộ chỉ số request rate, error rate, duration và saturation để đánh giá sức khỏe một API ra sao?
Bạn thiết kế tín hiệu availability từ các request thành công và thất bại theo định nghĩa nghiệp vụ như thế nào?
Bạn kiểm tra metric đã được scrape đủ ổn định trước khi tạo rule phụ thuộc vào nó bằng cách nào?
Bạn viết bộ lọc instant vector theo tên metric và label để chọn đúng dịch vụ cần giám sát như thế nào?
Bạn lựa chọn bộ so khớp label bằng, khác, regex và phủ định regex mà tránh lấy nhầm chuỗi ra sao?
Bạn phân biệt instant vector và range vector khi viết biểu thức cho điều kiện alert như thế nào?
Bạn xác định khoảng thời gian quan sát phù hợp cho rate dựa trên scrape interval và mức dao động traffic ra sao?
Bạn sử dụng rate trên counter để đo tốc độ lỗi và diễn giải đơn vị kết quả như thế nào?
Bạn phân biệt rate, irate và increase trong cảnh báo tăng đột biến hoặc xu hướng kéo dài như thế nào?
Bạn giải thích vì sao tính rate trước rồi mới sum thường cần thiết khi tổng hợp counter có reset ra sao?
Bạn phát hiện trường hợp counter reset sau khi service khởi động lại và cách tránh kết luận sai như thế nào?
Bạn đánh giá sai số của increase khi số mẫu ít và khoảng thời gian rất ngắn ra sao?
Bạn thiết kế biểu thức tính tỷ lệ lỗi từ hai counter cùng tập nhãn như thế nào?
Bạn xử lý mẫu số bằng không khi tính error ratio cho endpoint ít traffic ra sao?
Bạn xác định ngưỡng traffic tối thiểu trước khi cảnh báo tỷ lệ lỗi cao như thế nào?
Bạn phân biệt sum, avg, min, max và count khi tổng hợp metric nhiều instance theo yêu cầu gì?
Bạn sử dụng sum by hoặc sum without để giữ đúng các nhãn cần thiết cho một cảnh báo ra sao?
Bạn phát hiện phép tổng hợp vô tình làm mất nhãn team hoặc service khiến Alertmanager định tuyến sai như thế nào?
Bạn lựa chọn phép so sánh PromQL với ngưỡng tĩnh cho metric gauge và kiểm tra đơn vị như thế nào?
Bạn giải thích sự khác nhau giữa phép lọc của toán tử so sánh và kết quả khi dùng bool modifier ra sao?
Bạn kết hợp and, or và unless để lọc hoặc loại trừ các chuỗi cảnh báo như thế nào?
Bạn phân tích các phép toán giữa hai vector có label set khác nhau khi kết quả không xuất hiện như mong đợi ra sao?
Bạn sử dụng on hoặc ignoring để làm rõ những label tham gia vector matching như thế nào?
Bạn quyết định khi nào dùng group_left hoặc group_right để kết hợp dữ liệu nhiều-một trong PromQL ra sao?
Bạn phát hiện lỗi many-to-many matching và thiết kế lại biểu thức để bảo đảm tính duy nhất như thế nào?
Bạn phân biệt metric từ hai job khác nhau cần join qua nhãn nào để tránh nhân số chuỗi ra sao?
Bạn sử dụng label_replace trong tình huống cần chuẩn hóa label mà không sửa được exporter như thế nào?
Bạn cân nhắc chuẩn hóa nhãn ở instrumentation, relabeling hay PromQL theo ưu và nhược điểm nào?
Bạn giải thích offset giúp so sánh trạng thái hiện tại với giai đoạn trước như thế nào?
Bạn lựa chọn các hàm avg_over_time, max_over_time hoặc min_over_time cho tín hiệu dao động nhanh như thế nào?
Bạn dùng changes hoặc resets để phát hiện thay đổi trạng thái và counter reset theo mục tiêu nào?
Bạn thiết kế cảnh báo khi metric gauge tăng liên tục thay vì chỉ vượt ngưỡng tại một thời điểm như thế nào?
Bạn đánh giá tác động của dùng subquery trong PromQL đến chi phí thực thi và độ chính xác của rule ra sao?
Bạn phân tích nguy cơ số lượng time series tăng mạnh khi dùng biểu thức PromQL có nhiều nhãn ra sao?
Bạn kiểm tra một biểu thức PromQL trên dashboard trước khi triển khai rule bằng những tình huống nào?
Bạn xác định nguyên nhân một biểu thức trả về vector rỗng dù exporter đang chạy như thế nào?
Bạn phân biệt kết quả vector rỗng với chuỗi có giá trị bằng không trong ngữ nghĩa alerting ra sao?
Bạn thiết kế PromQL để không gửi cảnh báo sai khi một metric chỉ xuất hiện lúc có lỗi như thế nào?
Bạn xử lý sự khác nhau giữa metric counter chưa từng được tạo và metric counter có giá trị không bằng cách nào?
Bạn đánh giá rủi ro khi áp dụng biểu thức or vector(0) mà làm mất các nhãn phục vụ định tuyến như thế nào?
Bạn sử dụng absent hoặc absent_over_time để phát hiện mất metric có chủ đích như thế nào?
Bạn phân biệt việc target down với mất một metric cụ thể khi target vẫn được scrape thành công ra sao?
Bạn kết hợp metric up với tín hiệu nghiệp vụ để nhận diện exporter hoặc ứng dụng không thể quan sát như thế nào?
Bạn xử lý Prometheus không scrape được target do service discovery thay đổi bằng cách nào?
Bạn phát hiện scrape thất bại liên tục mà không nhầm với lần restart ngắn bằng cách nào?
Bạn giải thích tác động của staleness và chuỗi ngừng xuất hiện lên quá trình đánh giá alert ra sao?
Bạn xác định nguy cơ cảnh báo tự biến mất khi chính metric cần giám sát biến mất như thế nào?
Bạn phân biệt missing data, no traffic và normal traffic trong rule về tỷ lệ lỗi ra sao?
Bạn thiết kế cảnh báo cho dịch vụ xử lý batch vốn không phát sinh metric liên tục như thế nào?
Bạn tránh kết luận job thất bại chỉ vì metric cuối cùng không được cập nhật đúng lúc ra sao?
Bạn quyết định khi nào cần heartbeat metric hoặc thông tin thời điểm chạy cuối để giám sát job như thế nào?
Bạn tính tuổi của lần xử lý gần nhất từ timestamp metric và phát hiện công việc bị treo ra sao?
Bạn kiểm tra nguồn dữ liệu thiếu do relabeling, exporter, mạng hay Prometheus bằng cách nào?
Bạn xây dựng cảnh báo độc lập về tính sẵn sàng của pipeline quan sát để tránh điểm mù như thế nào?
Bạn xác định thời gian chờ hợp lý trước khi cảnh báo thiếu dữ liệu khi scrape interval không cố định ra sao?
Bạn phân tích tình huống label của metric thay đổi sau deploy khiến rule cũ không còn kết quả như thế nào?
Bạn kiểm tra những nhãn mới hoặc mất đi có làm thay đổi identity của alert trong Prometheus ra sao?
Bạn tổ chức các rule group và file rule để tách dịch vụ, môi trường và loại tín hiệu như thế nào?
Bạn phân biệt interval đánh giá nhóm rule với scrape interval và hệ quả đối với thời gian phát hiện ra sao?
Bạn chọn evaluation interval cho một nhóm rule dựa trên chi phí truy vấn và yêu cầu phản ứng như thế nào?
Bạn đánh giá ảnh hưởng của nhiều rule tốn tài nguyên trong cùng nhóm lên lịch đánh giá ra sao?
Bạn giải thích cách Prometheus đánh giá recording rule theo chu kỳ và lưu kết quả thành time series mới như thế nào?
Bạn thiết kế tên recording rule theo mức tổng hợp, metric nguồn và phép tính để tránh hiểu nhầm ra sao?
Bạn xác định lợi ích của recording rule khi nhiều alert và dashboard cùng dùng một phép tính đắt như thế nào?
Bạn kiểm tra recording rule có giữ đúng nhãn service, region và environment sau khi tổng hợp ra sao?
Bạn dựa trên đặc điểm counter reset và mức tổng hợp nào để quyết định thứ tự tính rate trong recording rule?
Bạn phân biệt recording rule lưu rate với rule lưu tỷ lệ lỗi để tránh dùng sai đơn vị ra sao?
Bạn tránh sử dụng trung bình của các tỷ lệ khi các nhóm có lưu lượng khác nhau như thế nào?
Bạn thiết kế chuỗi recording rule nhiều tầng mà vẫn bảo đảm dữ liệu đầu vào sẵn sàng ở mỗi lần đánh giá ra sao?
Bạn phân tích vấn đề dependency giữa các rule group có lịch đánh giá độc lập như thế nào?
Bạn đánh giá tác động của recording rule tạo ra quá nhiều chuỗi mới tới bộ nhớ và lưu trữ ra sao?
Bạn đo lợi ích hiệu năng khi thay truy vấn trực tiếp bằng recording rule bằng cách nào?
Bạn kiểm tra recording rule có tạo dữ liệu đúng khi một số instance biến mất giữa chừng ra sao?
Bạn quyết định nhãn nào phải loại bỏ khỏi bản ghi tổng hợp để không làm sai ý nghĩa chỉ số ra sao?
Bạn quản lý thay đổi tên recording rule khi dashboard và alert cũ vẫn tham chiếu như thế nào?
Bạn kiểm tra tính tương thích của các recording rule với phiên bản Prometheus đang triển khai như thế nào?
Bạn xây dựng alerting rule YAML với trường alert, expr, for, labels và annotations ra sao?
Bạn phân biệt trạng thái inactive, pending và firing của một alerting rule như thế nào?
Bạn giải thích ý nghĩa của trường for trong việc loại bỏ biến động ngắn hạn trước khi phát cảnh báo ra sao?
Bạn xác định quan hệ giữa thời gian for và evaluation interval để dự đoán độ trễ kích hoạt như thế nào?
Bạn lựa chọn thời gian for khác nhau cho lỗi availability, thiếu dữ liệu và tài nguyên đầy dần như thế nào?
Bạn phân tích điều gì xảy ra nếu biểu thức alert trở thành false trong giai đoạn pending như thế nào?
Bạn kiểm tra trạng thái của một alert khi metric hoặc label set biến mất giữa các lần đánh giá ra sao?
Bạn đánh giá khi nào cần giữ alert firing thêm một khoảng thời gian khi tín hiệu biến mất chốc lát như thế nào?
Bạn thiết kế ngưỡng tĩnh dựa trên giới hạn tài nguyên thực thay vì chọn tùy ý ra sao?
Bạn sử dụng các ngưỡng warning và critical mà tránh tạo hai thông báo gây nhiễu cho cùng một sự cố như thế nào?
Bạn xác định khi nào nên cảnh báo xu hướng cạn tài nguyên thay vì giá trị sử dụng cao hiện tại ra sao?
Bạn xây dựng cảnh báo dung lượng đĩa còn lại có tính đến tốc độ tăng và thời gian phản ứng như thế nào?
Bạn phân biệt ngưỡng của latency trung bình và p95 hoặc p99 trong phát hiện trải nghiệm người dùng xấu ra sao?
Bạn thiết kế alert từ histogram để cảnh báo tỷ lệ request vượt ngưỡng latency cụ thể như thế nào?
Bạn sử dụng histogram_quantile để ước lượng phân vị latency và nêu những giới hạn cần kiểm chứng ra sao?
Bạn xác định cách tổng hợp các chuỗi _bucket theo nhãn le trước khi tính histogram_quantile như thế nào?
Bạn đánh giá tác động của ít request và bucket phân bố thưa đến độ ổn định của latency alert ra sao?
Bạn định nghĩa cảnh báo saturation dựa trên queue depth hoặc backlog thay vì chỉ CPU như thế nào?
Bạn xây dựng rule phát hiện workload bị nghẽn dù CPU tổng thể chưa cao như thế nào?
Bạn kiểm tra metric memory usage có bao gồm cache có thể thu hồi trước khi tạo cảnh báo như thế nào?
Bạn phân biệt cảnh báo số lần restart tăng với cảnh báo tiến trình không sẵn sàng ra sao?
Bạn xác định điều kiện cảnh báo flapping khi một dịch vụ liên tục chuyển trạng thái khỏe và lỗi như thế nào?
Bạn xây dựng cảnh báo tỷ lệ lỗi theo từng endpoint mà không tạo quá nhiều alert instance như thế nào?
Bạn xử lý các endpoint ít truy cập để ngưỡng tỷ lệ lỗi không gây cảnh báo nhiễu ra sao?
Bạn tạo cảnh báo cho một dependency chậm bằng cách kết hợp latency và tỷ lệ timeout như thế nào?
Bạn thiết kế rule theo tài nguyên của một instance và rule tổng thể theo service khác nhau như thế nào?
Bạn xác định mức aggregation phù hợp để không giấu một instance xấu trong trung bình của toàn cụm ra sao?
Bạn sử dụng nhãn severity, team, service và environment theo quy ước nhất quán như thế nào?
Bạn quyết định những giá trị label nào phải giữ ổn định để Alertmanager nhóm và khử trùng lặp đúng ra sao?
Bạn đánh giá hậu quả của đưa giá trị metric thay đổi liên tục vào label alert như thế nào?
Bạn thiết kế nhãn cluster, region và namespace để cảnh báo có đủ phạm vi xử lý ra sao?
Bạn xử lý xung đột label giữa kết quả PromQL, rule labels và external labels như thế nào?
Bạn viết annotation summary mô tả vấn đề ngắn gọn nhưng đủ bối cảnh như thế nào?
Bạn thiết kế annotation description có thông tin tài nguyên, mức độ ảnh hưởng và hành động kiểm tra như thế nào?
Bạn dùng template trong annotations để hiển thị nhãn và giá trị đo mà không làm thay đổi danh tính alert ra sao?
Bạn xác định đơn vị và cách định dạng giá trị trong thông điệp cảnh báo để người nhận không hiểu sai như thế nào?
Bạn bổ sung đường dẫn dashboard, log, trace hoặc runbook trong annotation theo những tiêu chí nào?
Bạn đánh giá nguy cơ chứa dữ liệu bí mật hoặc thông tin cá nhân trong label và annotation ra sao?
Bạn kiểm tra tính hữu ích của thông điệp khi một loạt alert cùng firing trên nhiều instance ra sao?
Bạn xác định alert nào có thể xử lý tự động và alert nào cần con người can thiệp theo tiêu chí nào?
Bạn phân biệt cảnh báo cần đánh thức người trực với cảnh báo chỉ cần tạo ticket như thế nào?
Bạn xác định thông tin cần có trong runbook liên kết từ alert để rút ngắn thời gian chẩn đoán ra sao?
Bạn giải thích luồng xử lý alert từ Prometheus sang Alertmanager và các receiver như thế nào?
Bạn phân biệt vai trò đánh giá điều kiện của Prometheus với nhóm, định tuyến và gửi thông báo của Alertmanager ra sao?
Bạn thiết kế cấu trúc route của Alertmanager để phân phối alert theo team, environment và severity như thế nào?
Bạn dùng matcher trong Alertmanager để tránh cảnh báo production bị gửi tới nhóm phụ trách staging ra sao?
Bạn giải thích grouping của Alertmanager giảm số thông báo nhưng có thể che khuất chi tiết nào như thế nào?
Bạn lựa chọn group_by phù hợp để nhóm cùng sự cố mà không gom các hệ thống độc lập vào nhau ra sao?
Bạn thiết lập group_wait, group_interval và repeat_interval dựa trên yêu cầu phản ứng và tránh spam như thế nào?
Bạn kiểm tra tác động của các interval Alertmanager tới thời điểm người trực nhận thông báo ra sao?
Bạn phân biệt deduplication của Alertmanager với việc Prometheus tạo nhiều alert instance khác label như thế nào?
Bạn giải quyết cảnh báo trùng lặp từ hai Prometheus chạy HA bằng thiết kế external labels như thế nào?
Bạn đánh giá tác động của nhãn replica lên khả năng khử trùng lặp alert HA ra sao?
Bạn thiết kế inhibition khi service down làm phát sinh hàng loạt cảnh báo con như thế nào?
Bạn xác định những điều kiện equal labels cần có để inhibition không chặn nhầm cảnh báo độc lập ra sao?
Bạn phân biệt inhibition rule với silence khi muốn giảm thông báo có chủ đích như thế nào?
Bạn tổ chức silence cho khung bảo trì mà không che mất các sự cố ngoài phạm vi ra sao?
Bạn xác định thời hạn và người chịu trách nhiệm cho silence để tránh bị quên kéo dài như thế nào?
Bạn kiểm tra vì sao alert đang firing trên Prometheus nhưng không có thông báo từ Alertmanager ra sao?
Bạn phân biệt lỗi định tuyến receiver, suppression và lỗi kết nối webhook khi điều tra thông báo bị mất như thế nào?
Bạn quản lý receiver, webhook và secret của kênh thông báo sao cho an toàn như thế nào?
Bạn thiết kế escalation khi cảnh báo nghiêm trọng chưa được xác nhận xử lý như thế nào?
Bạn quyết định khi nào gửi thông báo resolved để hỗ trợ người trực mà không gây nhiễu ra sao?
Bạn kiểm tra Alertmanager tiếp nhận alert và khử trùng lặp ra sao khi Prometheus kết nối lại sau sự cố?
Bạn xây dựng quy trình kiểm tra kênh cảnh báo định kỳ mà không tạo báo động giả trên production như thế nào?
Bạn định nghĩa SLI, SLO và error budget cho một API từ dữ liệu metric như thế nào?
Bạn xác định mẫu số request hợp lệ trong SLI availability để loại trừ những trường hợp không thuộc trách nhiệm dịch vụ ra sao?
Bạn xây dựng recording rule tính số request tốt và tổng request theo cùng phạm vi như thế nào?
Bạn tính error budget còn lại trong một kỳ SLO dựa trên tổng số request và mức lỗi chấp nhận như thế nào?
Bạn phân biệt cảnh báo vượt ngưỡng lỗi tĩnh với cảnh báo theo tốc độ tiêu thụ error budget ra sao?
Bạn giải thích ý nghĩa burn rate cao trong ngắn hạn so với burn rate thấp nhưng kéo dài như thế nào?
Bạn thiết kế cảnh báo multi-window multi-burn-rate cho sự cố lớn và suy giảm kéo dài ra sao?
Bạn lựa chọn các cửa sổ thời gian ngắn và dài để cân bằng tốc độ phát hiện với tín hiệu ổn định như thế nào?
Bạn đánh giá tác động của traffic thấp tới độ tin cậy của SLO error ratio và burn-rate alert ra sao?
Bạn xác định cách xử lý thiếu metric trong cửa sổ SLO mà không mặc nhiên xem là dịch vụ khỏe mạnh như thế nào?
Bạn thiết kế rule cho latency SLO dựa trên tỷ lệ request đạt ngưỡng thay vì chỉ lấy trung bình ra sao?
Bạn giải thích cách dùng histogram bucket để tính tỷ lệ request nhanh hơn một ngưỡng latency ra sao?
Bạn xử lý sự khác nhau giữa bucket latency của từng service và ngưỡng SLO chung trong hệ thống như thế nào?
Bạn đánh giá khi nào cần một SLO tổng thể và khi nào cần SLO riêng theo vùng hoặc phân khúc người dùng ra sao?
Bạn kiểm tra việc gộp các region có thể che giấu một vùng vi phạm SLO như thế nào?
Bạn liên kết alert SLO với dashboard error budget và chính sách dừng phát hành như thế nào?
Bạn quyết định mức severity dựa trên mức tiêu thụ error budget và phạm vi ảnh hưởng ra sao?
Bạn so sánh tính phù hợp của alert SLO với alert về CPU hoặc memory đối với việc đánh thức người trực như thế nào?
Bạn xác định tín hiệu nào cần cảnh báo trước khi SLO bị vi phạm nhưng vẫn hạn chế false positive ra sao?
Bạn kiểm chứng công thức SLO và recording rule trên dữ liệu mẫu bằng tính toán độc lập như thế nào?
Bạn kiểm tra cú pháp file rule bằng promtool trước khi đưa vào repository như thế nào?
Bạn sử dụng promtool test rules để mô phỏng time series đầu vào và kỳ vọng của alert như thế nào?
Bạn thiết kế test fixture thể hiện một counter tăng đều và một counter reset để kiểm tra PromQL ra sao?
Bạn kiểm thử thời điểm alert chuyển pending sang firing khi dùng for bằng các mốc thời gian nào?
Bạn tạo dữ liệu kiểm thử có một đợt lỗi ngắn hơn for để xác nhận alert không firing ra sao?
Bạn kiểm tra biểu thức alert khi metric bằng không, không tồn tại hoặc chỉ xuất hiện một phần bằng cách nào?
Bạn tổ chức các ca kiểm thử có thiếu scrape trong nhiều chu kỳ để phát hiện cảnh báo sai như thế nào?
Bạn kiểm chứng rule hoạt động khi label set thay đổi hoặc instance được thêm và loại bỏ ra sao?
Bạn tạo fixture nhiều instance và nhiều region để kiểm tra tổng hợp theo label bằng cách nào?
Bạn kiểm tra logic warning và critical có ngưỡng rõ ràng và không tạo thông báo mâu thuẫn ra sao?
Bạn thiết kế bài kiểm thử khi một target down nhưng metric lỗi ứng dụng không còn xuất hiện như thế nào?
Bạn kiểm thử trường hợp một service có lưu lượng bằng không để tránh cảnh báo tỷ lệ lỗi chia cho không ra sao?
Bạn xác định cách kiểm tra annotation template với những label có thể thiếu như thế nào?
Bạn kiểm tra giá trị recording rule bằng output series dự kiến trong unit test như thế nào?
Bạn thiết kế bộ kiểm thử ngưỡng SLO burn rate với cả lỗi đột biến và suy giảm chậm như thế nào?
Bạn dùng truy vấn PromQL trên dữ liệu lịch sử để dự đoán rule mới sẽ phát cảnh báo bao nhiêu lần ra sao?
Bạn phân biệt backtesting rule với chạy thử nghiệm trên một nhóm service nhỏ như thế nào?
Bạn đánh giá tính đại diện của dữ liệu test trước các chu kỳ traffic theo giờ hoặc theo ngày như thế nào?
Bạn kiểm tra rule mới có làm tăng chi phí query và số time series khi đưa vào production ra sao?
Bạn phát hiện những rule đánh giá chậm hoặc bỏ lỡ lần đánh giá dựa trên metric nội bộ Prometheus như thế nào?
Bạn theo dõi tổng số alert firing, pending và thời gian đánh giá để nhận biết thay đổi bất thường ra sao?
Bạn quản lý rule file trong Git theo owner, dịch vụ và môi trường để giảm xung đột như thế nào?
Bạn tổ chức code review cho thay đổi PromQL, ngưỡng, for và labels theo checklist nào?
Bạn xây dựng pipeline CI/CD để kiểm tra YAML, promtool và unit test trước khi deploy như thế nào?
Bạn kiểm tra tương thích cú pháp rule với phiên bản Prometheus mục tiêu trong pipeline bằng cách nào?
Bạn phân tách cấu hình rule dùng chung với ngưỡng riêng từng môi trường mà tránh copy không kiểm soát ra sao?
Bạn sử dụng template hoặc generator cho nhiều service mà vẫn cho phép xem diff rule thực tế như thế nào?
Bạn quản lý thay đổi recording rule có ảnh hưởng tới alert và dashboard phụ thuộc như thế nào?
Bạn thiết kế release từng phần cho bộ rule mới trước khi áp dụng toàn bộ cluster ra sao?
Bạn xác định cách thử rule ở chế độ không gửi thông báo tới người trực trước khi bật production như thế nào?
Bạn kiểm chứng một lần reload Prometheus đã nạp đủ rule mới và không giữ lại cấu hình lỗi ra sao?
Bạn kiểm tra kết quả reload và trạng thái rule qua UI hoặc API của Prometheus như thế nào?
Bạn lập phương án rollback khi rule mới gây quá nhiều cảnh báo hoặc làm tăng tài nguyên Prometheus ra sao?
Bạn tổ chức lịch sử thay đổi ngưỡng và lý do điều chỉnh để tránh lặp lại lỗi cũ như thế nào?
Bạn quản lý thay đổi Alertmanager route đồng bộ với label của rule Prometheus như thế nào?
Bạn xử lý conflict khi nhiều nhóm cùng chỉnh một rule hoặc nhãn severity trong cùng đợt phát hành ra sao?
Bạn xây dựng chính sách đặt tên alert ổn định để dashboard và automation không bị hỏng khi đổi rule như thế nào?
Bạn thiết kế cách loại bỏ alert cũ sau khi chuyển sang rule SLO mới mà không tạo khoảng trống giám sát ra sao?
Bạn đo số lần cảnh báo gây nhiễu và thời gian phản ứng trước và sau thay đổi rule như thế nào?
Bạn xây dựng quy trình rà soát alert không còn người sở hữu hoặc không có hành động xử lý như thế nào?
Bạn lựa chọn cách giảm alert fatigue bằng điều chỉnh điều kiện, for, grouping và inhibition theo dữ liệu thực tế như thế nào?
Bạn phân biệt false positive, false negative và alert không thể hành động khi đánh giá chất lượng rule ra sao?
Bạn phân tích vì sao cảnh báo CPU thường xuyên vượt ngưỡng nhưng không tương ứng suy giảm dịch vụ như thế nào?
Bạn xử lý alert flapping do metric dao động gần ngưỡng bằng phương pháp nào?
Bạn xác định nguy cơ bỏ sót sự cố ngắn nhưng nghiêm trọng khi tăng thời gian for bằng cách nào?
Bạn thiết kế cặp điều kiện bật và tắt có hysteresis hoặc chiến lược tương đương để giảm flapping ra sao?
Bạn phát hiện alert bắn hàng loạt vì mất nhãn tổng hợp sau khi refactor PromQL như thế nào?
Bạn xác định nguyên nhân một alert hiển thị pending mãi dù metric trên dashboard có lúc vượt ngưỡng ra sao?
Bạn điều tra lý do alert không firing dù biểu thức chạy thủ công trả ra giá trị vượt ngưỡng như thế nào?
Bạn xác định vì sao alert bỗng resolved khi target ngừng xuất metric bằng cách nào?
Bạn phân biệt lỗi recording rule không sinh dữ liệu với lỗi alert rule không khớp điều kiện ra sao?
Bạn điều tra một alert bị lặp lại liên tục sau khi label annotation hoặc label cấu hình bị thay đổi như thế nào?
Bạn xác định tác động của thay đổi scrape interval và evaluation interval đến rule for trong quá trình nâng cấp ra sao?
Bạn kiểm tra alert bị trễ vì truy vấn rule quá nặng hoặc Prometheus đang chịu tải bằng cách nào?
Bạn phân tích vì sao Alertmanager báo cùng sự cố từ nhiều replica Prometheus dù đã thiết lập HA ra sao?
Bạn xác định nơi bị mất thông báo khi alert có trạng thái firing nhưng không tới kênh trực như thế nào?
Bạn xử lý trường hợp silence vô tình chặn cảnh báo critical trong lúc bảo trì như thế nào?
Bạn thiết kế phép thử toàn tuyến từ metric giả lập tới thông báo và xác nhận xử lý ra sao?
Bạn kiểm tra alert SLO không phát hiện sự cố vì request thất bại không còn được tính vào metric như thế nào?
Bạn lập runbook chẩn đoán khi rule về đầy đĩa firing nhưng hệ thống tệp được mount khác với dự kiến ra sao?
Bạn phân biệt độ trễ tăng thực với tín hiệu thiếu ổn định do ít request hoặc histogram bucket thô như thế nào?
Bạn xác định những thông tin cần thu thập trước khi điều chỉnh một alert đã đánh thức người trực sai nhiều lần ra sao?
Bạn thiết kế quy trình xử lý sự cố quan sát khi cả Prometheus và Alertmanager đều không sẵn sàng như thế nào?
Bạn lựa chọn các chỉ tiêu nghiệm thu cho một bộ rule dựa trên tính đúng, độ trễ phát hiện, khả năng hành động và mức độ nhiễu ra sao?
