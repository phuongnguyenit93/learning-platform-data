Một nền tảng thương mại điện tử chạy 30 microservice trên Kubernetes nhưng mỗi nhóm tự lưu log trong container; khi dịch vụ thanh toán lỗi, pod đã được thay thế và đội trực không còn log của phiên bản vừa hỏng.
Một ứng dụng Java ghi log vào cả stdout và tệp trong container, trong khi Filebeat thu thập cả hai nguồn; trên Kibana cùng một exception xuất hiện hai lần với timestamp gần như giống nhau.
Đội triển khai Filebeat trên các node Kubernetes nhưng chỉ chọn một số đường dẫn log container; dịch vụ chạy ở node mới không xuất hiện trong Elasticsearch dù pod vẫn ghi log liên tục.
Một ứng dụng ghi stack trace Java thành nhiều dòng; Filebeat gửi mỗi dòng thành sự kiện riêng khiến người điều tra chỉ thấy nửa cuối exception và mất thông tin nguyên nhân gốc.
Nhóm vừa thay cấu hình multiline cho stack trace, nhưng một số log ngắn ngay sau exception bị ghép vào sự kiện lỗi trước đó; số lượng sự kiện và thời gian trong dashboard trở nên sai lệch.
Một dịch vụ ghi JSON log trên stdout và Logstash tiếp tục áp bộ phân tích văn bản tự do; một số bản ghi JSON bị bỏ hoặc mất trường level sau đợt phát hành định dạng mới.
Filebeat đang theo dõi tệp log của ứng dụng nhưng hệ thống xoay tệp và xóa bản cũ rất nhanh; trong giờ cao điểm một phần sự kiện biến mất trước khi agent đọc kịp.
Ứng dụng Java liên tục ghi vào tệp đã được đổi tên bởi logrotate, trong khi Filebeat bắt đầu đọc tệp mới; đội vận hành thấy log của cùng service bị chia giữa hai file sau thời điểm rotation.
Một máy chủ chạy nhiều bản sao ứng dụng ghi vào tệp có tên khác nhau mỗi lần khởi động; cấu hình input Filebeat quá hẹp nên các file mới không được thu thập.
Agent chạy bằng tài khoản không có quyền đọc thư mục audit log trên máy Linux; Kibana hiển thị đầy đủ application log nhưng không có bất kỳ sự kiện audit nào kể từ ngày siết quyền.
Đội kỹ thuật cập nhật cấu hình parser cho một loại log nhưng bỏ qua nhãn phân biệt nguồn; log Nginx và log Spring Boot bị xử lý cùng một pipeline rồi xuất hiện nhiều trường sai kiểu.
Một container ngừng hoạt động đột ngột khi host hết đĩa; file log cục bộ chưa được agent chuyển hết lên máy trung tâm và các sự kiện cuối trước khi lỗi không thể tìm được.
Ứng dụng ghi log ở múi giờ địa phương nhưng Filebeat không truyền đủ thông tin múi giờ; Kibana xếp các lỗi trước thời điểm request thực tế vài giờ.
Một số node Kubernetes lệch đồng hồ hệ thống, khiến log gateway xuất hiện sau log backend dù request đã đi qua gateway trước; nhóm ứng cứu dựng timeline sự cố sai thứ tự.
Filebeat đọc lại các tệp cũ sau khi mất registry state trong lúc container được tạo lại; Elasticsearch có thêm hàng nghìn bản ghi trùng dù không có traffic nghiệp vụ mới.
Đội triển khai Elastic Agent cùng Filebeat độc lập trên một số máy; hai agent thu thập cùng tệp, làm số lượng sự kiện và chi phí ingest cao gấp đôi trên các máy đó.
Nhóm chuyển từ Beats độc lập sang Elastic Agent quản lý qua Fleet; một số host vẫn giữ cấu hình cũ nên log gửi đến hai data stream khác nhau và dashboard thiếu tính nhất quán.
Elastic Agent đã được đăng ký trên Fleet nhưng policy chưa có integration thu thập log của ứng dụng; máy hiển thị trạng thái healthy song Elasticsearch không nhận được log nghiệp vụ.
Một nhóm máy chủ ở chi nhánh không kết nối được Fleet Server qua proxy doanh nghiệp; Elastic Agent vẫn có tiến trình chạy nhưng không nhận được thay đổi chính sách thu thập mới.
Agent được chuyển sang kết nối HTTPS với Fleet Server sử dụng CA nội bộ; một số host báo lỗi chứng chỉ và mất khả năng cập nhật policy sau khi CA được xoay.
Một hệ thống thu thập log từ nhiều môi trường dev, staging và production nhưng resource labels không nhất quán; cùng một service hiển thị trong hai không gian tìm kiếm khác nhau.
Đội vận hành muốn phân loại log ứng dụng theo tenant, nhưng agent chỉ biết metadata của pod và namespace; các sự kiện nhiều tenant trong cùng tiến trình không thể được phân biệt chính xác.
Logstash nhận log qua Beats input nhưng pipeline đầu vào chưa gắn nhãn nguồn ứng dụng; các filter dựa trên đường dẫn tệp phân loại nhầm khi nhóm phát triển đổi tên thư mục log.
Một dịch vụ gửi bản ghi JSON với trường message chứa chuỗi JSON lồng bên trong; Logstash parse lớp ngoài thành công nhưng các thuộc tính nghiệp vụ quan trọng vẫn nằm trong chuỗi văn bản.
Nhóm dùng grok để xử lý access log Nginx; một bản phát hành thêm trường upstream_response_time làm nhiều sự kiện không khớp pattern và chuyển vào nhánh lỗi.
Pipeline Logstash áp grok quá phức tạp lên hàng trăm nghìn bản ghi mỗi giây; CPU tăng mạnh trong khi cấu trúc log thực tế có các phần được phân tách cố định.
Một file log CSV của hệ thống legacy có giá trị chứa dấu phẩy bên trong dấu nháy kép; Logstash tách sai cột và nhập mã khách hàng vào trường số tiền.
Ứng dụng thay đổi thứ tự trường trong log văn bản mà chưa thông báo đội vận hành; cùng một grok pattern vẫn khớp một phần nhưng giá trị IP và response time bị đảo chỗ.
Một số log Java có ký tự Unicode và emoji, còn các tệp khác dùng bảng mã cũ; sau khi nhập vào pipeline tập trung, Kibana hiển thị thông điệp bị lỗi mã hóa.
Logstash dùng date filter đọc timestamp ISO 8601 nhưng một service phát định dạng ngày tháng không kèm múi giờ; các sự kiện được gán @timestamp khác với thời điểm diễn ra.
Một pipeline dùng thời điểm ingest làm @timestamp cho log đến muộn qua đường truyền chi nhánh; trong khoảng mất mạng, các sự cố hôm trước xuất hiện như thể vừa xảy ra.
Nhóm muốn giữ cả thời điểm sự kiện lẫn thời điểm Elasticsearch nhận dữ liệu, nhưng pipeline chỉ lưu một trường thời gian; điều tra lỗi truyền log không phân biệt được độ trễ vận chuyển với sự cố ứng dụng.
Một số sự kiện có trường status là chuỗi chữ trong khi những sự kiện khác có status là số; Elasticsearch từ chối phần dữ liệu mới vì mapping của trường đã được tạo trước đó.
Service Java đổi trường latency_ms từ số sang chuỗi có hậu tố 'ms'; dashboard thống kê phân vị latency dừng hiển thị đúng dù Discover vẫn tìm được message tương ứng.
Một đội đặt trường user trong JSON log lúc là đối tượng, lúc là chuỗi; mapping conflict xuất hiện khi ingest từ nhiều phiên bản ứng dụng vào cùng data stream.
Hàng nghìn loại thuộc tính tùy ý được đưa vào event.fields từ request payload; số mapping fields của index tăng nhanh và cụm Elasticsearch phải xử lý nhiều field mới liên tục.
Nhóm chuẩn hóa log Nginx và Spring Boot theo Elastic Common Schema (ECS) nhưng một đội dùng client.ip cho IP proxy, đội khác dùng cho IP người dùng; dashboard địa chỉ nguồn cho kết quả trái ngược.
Log của một ứng dụng đặt service.name bằng tên Kubernetes deployment còn log dịch vụ khác dùng tên artifact Java; cùng service bị tách thành hai nhóm dù chạy chung một phiên bản.
Một pipeline Logstash xóa message sau khi trích xuất trường và quên giữ nội dung gốc cho loại log lỗi; khi parser sai, người trực không còn chuỗi ban đầu để đối chiếu.
Đội kỹ thuật áp mutate filter đổi tên nhiều trường ở Logstash nhưng downstream dashboard vẫn truy vấn tên cũ; sau phát hành log vẫn tới Elasticsearch nhưng các biểu đồ trống.
Một pipeline nhánh lỗi thêm tag _grokparsefailure cho hàng nghìn log mới; cảnh báo chỉ dựa trên số event đầu vào nên đội trực không nhận ra chất lượng dữ liệu đang suy giảm.
Logstash lọc bỏ các request 2xx để giảm dung lượng, nhưng nhóm điều tra cần so sánh tỷ lệ request thành công với lỗi 5xx trong cùng khoảng thời gian và không còn dữ liệu nền.
Một đội dùng drop filter để loại bỏ health check nhưng biểu thức khớp quá rộng, khiến một endpoint nghiệp vụ có tên đường dẫn tương tự cũng biến mất khỏi kho log.
Pipeline thu thập log có cột chứa email và số điện thoại; nhóm chuẩn hóa nội dung nhưng chưa ẩn danh dữ liệu trước khi gửi đến hệ thống lưu trữ tập trung dùng chung.
Đội vận hành bật log debug chứa Authorization header trong thời gian sự cố; các bản ghi nhạy cảm được lưu cả ở Logstash, Elasticsearch và snapshot mà chưa có chính sách xử lý.
Một service gửi địa chỉ IP thực của khách qua X-Forwarded-For; pipeline chỉ lưu IP Nginx proxy, khiến phân tích sự cố theo vị trí người dùng bị sai lệch.
Logstash chuyển log đến Elasticsearch bằng bulk output nhưng máy chủ trả HTTP 429 trong đợt nhập dữ liệu lớn; hàng đợi gửi tăng liên tục và log hiển thị chậm hơn thực tế.
Một cụm Elasticsearch ngừng hoạt động vài phút; Logstash chạy với hàng đợi chỉ ở bộ nhớ và khởi động lại trong lúc mất kết nối, dẫn tới khoảng trống dữ liệu sau phục hồi.
Nhóm bật persistent queue của Logstash trên volume tạm trong container; khi pod được tạo lại sau sự cố, các event đang đợi gửi không còn trên ổ đĩa mới.
Một pipeline Logstash nhận dữ liệu từ Kafka rất nhanh nhưng exporter Elasticsearch xử lý chậm; consumer lag tăng, persistent queue gần đầy và agent bắt đầu chịu áp lực ngược.
Logstash dùng một pipeline nặng để xử lý mọi nguồn log; khi parser của một ứng dụng sinh lỗi liên tục, các nguồn còn lại cũng chậm gửi tới Elasticsearch.
Đội cấu hình dead-letter queue cho các sự kiện bị Elasticsearch từ chối, nhưng không có quy trình đọc lại dữ liệu sau khi sửa mapping; dashboard tiếp tục thiếu log từ một ngày quan trọng.
Logstash retry một lô bulk sau timeout mạng dù Elasticsearch có thể đã lưu một phần bản ghi; cùng sự kiện xuất hiện trùng khi pipeline không có cơ chế định danh tài liệu ổn định.
Hệ thống muốn theo dõi tính đầy đủ của pipeline nhưng chỉ có metric tổng số event vào Logstash; không có cách đối chiếu số bị loại, số lỗi parse, số đã gửi và số đã lưu.
Nhóm tăng số worker và batch size của Logstash để tăng throughput; heap JVM và thời gian GC tăng, còn Elasticsearch bắt đầu từ chối bulk request trong giờ cao điểm.
Một máy Logstash có nhiều pipeline nhưng cấu hình queue và worker không phản ánh độ ưu tiên nguồn audit; khi hệ thống gặp nghẽn, log audit quan trọng đến muộn hơn log debug.
Một cụm Elasticsearch có ba node nhưng shard của data stream log được phân bổ không đồng đều; một node dùng gần hết đĩa và CPU trong khi các node còn lại nhàn rỗi.
Đội vận hành tạo một index mới mỗi giờ cho mọi dịch vụ nhỏ; số lượng shard và index metadata tăng nhanh dù nhiều index chỉ chứa vài nghìn bản ghi.
Một data stream chứa log của hàng trăm service có tốc độ ghi rất khác nhau; rollover theo dung lượng chung khiến một số service không có ranh giới lưu trữ phù hợp nhu cầu điều tra riêng.
Nhóm định tuyến event vào index dựa trên trường environment nhưng nhiều log thiếu trường đó; một số sự kiện production được lưu trong index mặc định có vòng đời ngắn hơn.
Một nhóm chuyển từ index theo ngày sang data stream nhưng ứng dụng ingest vẫn cố ghi trực tiếp bằng thao tác cập nhật tài liệu; các sự kiện bị từ chối trong khi data stream hoạt động với kiểu ghi thêm.
Elasticsearch nhận log thông qua ingest pipeline nhưng pipeline index template của data stream trỏ tới processor đã đổi tên; một số bản ghi mới không được lưu khi rolling deployment.
Đội quản trị thay index template cho log tương lai và kỳ vọng mapping của các index cũ tự thay đổi; Kibana vẫn gặp lỗi field conflict khi truy vấn toàn bộ lịch sử.
Một trường error_code được tự động phân tích như text; người trực tìm theo mã chính xác nhưng nhận cả những bản ghi có mã chứa các token tương tự.
Log message được index để tìm kiếm toàn văn nhưng truy vấn exact-match theo message gốc trả ít kết quả hơn dự kiến do analyzer tách và chuẩn hóa từ.
Nhóm lưu mọi trường JSON ở cả text và keyword, làm kích thước index tăng nhanh; nhiều trường chỉ dùng để hiển thị lại mà không được tìm kiếm hay tổng hợp.
Một bộ truy vấn Kibana lọc trên trường response_time dạng keyword; dashboard không thể tính histogram số học như nhóm mong muốn vì dữ liệu đã được lưu sai kiểu.
Elasticsearch heap tăng mạnh sau khi nhóm chạy aggregation có cardinality rất cao trên trường trace_id; các truy vấn dashboard khác chậm đi trong cùng khoảng thời gian.
Đội trực chạy truy vấn wildcard bắt đầu bằng ký tự bất kỳ trên message của hàng trăm triệu log; CPU tăng cao và nhiều người dùng Kibana nhận timeout khi tìm lỗi.
Nhóm thay đổi analyzer cho một trường đã index trong hàng trăm triệu tài liệu; các bản ghi cũ và mới cho kết quả tìm kiếm khác nhau sau đợt cập nhật mapping.
Đội vận hành tạo quá nhiều primary shard cho một index log nhỏ; chi phí quản lý shard và heap tăng nhưng tốc độ tìm kiếm không cải thiện tương ứng.
Một index ghi log lớn có quá ít primary shard so với lưu lượng; một số node nhận nhiều thao tác ghi hơn hẳn các node khác và bulk ingestion trở thành điểm nghẽn.
Cụm Elasticsearch tăng số replica nhằm cải thiện khả năng tìm kiếm, nhưng tốc độ ghi và lưu trữ tăng ngoài dự tính; ingest bắt đầu chậm trong đợt nhập log lớn.
Elasticsearch chuyển trạng thái yellow sau khi một data node ngừng hoạt động; log mới vẫn được ghi nhưng một phần replica chưa được phân bổ nên mức an toàn dữ liệu bị giảm.
Một index trở thành red sau khi hai node hỏng gần như đồng thời; người trực không thể tìm log sự cố ở một số khoảng thời gian và chưa có bản sao khôi phục đã được kiểm chứng.
Ổ đĩa một data node chạm ngưỡng watermark khiến Elasticsearch hạn chế phân bổ shard và có thể chặn ghi ở các index chịu ảnh hưởng; Logstash tiếp tục gửi nhưng backlog tăng liên tục.
Một nhóm tăng dung lượng ổ đĩa để chữa lỗi đầy cluster nhưng policy ILM vẫn giữ log chi tiết không giới hạn; sau vài tuần vấn đề dung lượng tái diễn.
Đội đặt ILM xóa log sau bảy ngày cho mọi loại dữ liệu; bộ phận an ninh cần kiểm tra truy cập trái phép sau ba tháng nhưng log audit đã bị xóa.
Log ứng dụng cần tra cứu thường xuyên trong ba ngày đầu và hiếm dùng sau sáu tháng; cấu hình hiện giữ toàn bộ trên node hot đắt tiền trong một năm nên chi phí tăng mạnh.
Nhóm áp ILM đưa index cũ sang tier warm trước khi các thao tác rollover hoàn tất đúng; một số index tiếp tục nhận log nhưng đã nằm trên phần cứng ít tối ưu cho ghi.
Đội sử dụng searchable snapshots cho dữ liệu log lâu năm; trong một cuộc điều tra truy cập trái phép, truy vấn bản ghi cũ chậm hơn đáng kể so với dữ liệu trên hot tier.
Một index được đưa sang tier cold có khả năng truy vấn hạn chế hơn trước, nhưng dashboard Kibana vẫn truy vấn toàn bộ thời gian một năm theo cùng tần suất; latency tăng và chi phí tài nguyên đột biến.
Nhóm áp chính sách rollover theo max_age nhưng bỏ qua dung lượng thực tế; ngày khuyến mãi lượng log tăng gấp mười làm một index chưa rollover trở nên quá lớn.
Đội thiết lập snapshot repository cho Elasticsearch nhưng chưa kiểm thử khôi phục một data stream sau khi xóa nhầm; khi gặp sự cố, không biết bản sao có đủ index metadata và dữ liệu hay không.
Một quản trị viên xóa index theo nhầm biểu thức tên; Kibana mất toàn bộ log của một service trong ngày và hệ thống chưa có quy trình xác nhận phạm vi khôi phục dữ liệu.
Elasticsearch phục hồi sau outage bằng cách replay các request từ buffer; số document count tăng nhưng dashboard có dữ liệu trùng do các event cũ được gửi lại với ID mới.
Nhóm giảm độ dài retention để tiết kiệm đĩa mà không thống nhất với yêu cầu pháp lý và vận hành; khi cần đối chiếu lịch sử sự cố một năm trước, dữ liệu không còn.
Đội cấu hình lifecycle cho data stream mới nhưng một số index cũ vẫn nằm ngoài policy; dung lượng cluster tiếp tục tăng dù dashboard ILM cho biết policy mới hoạt động.
Người vận hành xem Elasticsearch cluster health xanh nên kết luận hệ thống logging khỏe; trong cùng thời điểm Logstash bị tắc và Elasticsearch không có log mới trong gần một giờ.
Một service Java gửi log với service.name thay đổi theo pod name sau rollout; Kibana Discover cho thấy nhiều dòng log nhưng dashboard theo service cố định gần như trống.
Người dùng Kibana chỉ tìm log trong 15 phút gần nhất trong khi sự kiện mới được ingest muộn hơn một giờ; truy vấn theo @timestamp không hiển thị các bản ghi mà nhóm nghĩ đã thất lạc.
Đội điều tra chọn data view bao phủ index logs-web-* nhưng log của mobile backend được ghi vào logs-mobile-*; bộ lọc trong Kibana không bao giờ thấy lỗi từ ứng dụng di động.
Một dashboard Lens đếm tổng request thành công qua log Nginx nhưng dữ liệu đã được thu thập cả tại proxy và backend; số lượt truy cập được hiển thị gần gấp đôi thực tế.
Nhóm tạo Kibana visualization tổng số lỗi 500 theo environment, nhưng môi trường staging và production có nhãn khác tên; biểu đồ gộp chung hoặc bỏ sót một phần dữ liệu.
Dashboard tìm kiếm sử dụng trường user.id của ECS nhưng pipeline ingest một số log dưới user_id; khi điều tra một tài khoản, kết quả chỉ có log từ vài service.
Một chuyên viên dùng KQL để tìm log lỗi theo status và đường dẫn, nhưng cú pháp lọc chuỗi trên trường analyzed text khác với truy vấn chính xác mong đợi; nhiều sự kiện không liên quan xuất hiện.
Đội vận hành muốn tìm giao dịch theo trace.id từ log Spring Boot đến Nginx, nhưng pipeline proxy không giữ correlation ID nên việc nối các sự kiện giữa hệ thống phải dựa vào timestamp gần đúng.
Một request qua gateway, order-service và payment-service sinh log có trace.id nhưng một số event có trường dạng chữ hoa khác; liên kết giữa Kibana Discover và trace viewer bị đứt.
Trong một outage, Kibana báo thời gian không thể truy vấn dữ liệu nhưng Elasticsearch API vẫn trả kết quả; dashboard đang dùng quyền truy cập hoặc data view khác với tài khoản quản trị thử nghiệm.
Nhóm tạo alert trong Kibana khi số log lỗi vượt ngưỡng, nhưng các bản ghi bị gửi muộn vào hôm sau; cảnh báo kích hoạt sau khi sự cố đã kết thúc từ lâu.
Đội vận hành đặt cảnh báo dựa trên tổng số log ERROR mỗi phút; sau khi bật debug và đổi cách phân loại log, số thông báo tăng dù tỷ lệ request lỗi thực tế không thay đổi.
Một nhân viên được phép xem log của một môi trường staging nhưng có thể chuyển data view sang production; chính sách Kibana Spaces chưa phản ánh đầy đủ ranh giới quyền đọc dữ liệu.
Nhóm cấp quyền đọc toàn bộ index logs-* cho các thành viên hỗ trợ; Kibana cho phép xem cả log chứa thông tin thanh toán mà nhóm này không có nhu cầu nghiệp vụ.
Đội bảo mật sử dụng field-level security để ẩn email nhưng một pipeline mới lưu email trong message chưa được làm sạch; người dùng chỉ có quyền hạn chế vẫn tìm thấy dữ liệu cá nhân trong log thô.
Hệ thống nhiều tenant lưu log cùng index và dựa vào bộ lọc dashboard để phân tách dữ liệu; người dùng đổi truy vấn và nhìn thấy bản ghi của tenant khác vì quyền truy cập không giới hạn ở tầng Elasticsearch.
Elasticsearch và Kibana được truy cập qua mạng nội bộ nên nhóm chưa bật TLS cho kết nối client; sau khi mở VPN cho đối tác, lưu lượng quản trị và thông tin xác thực đi qua vùng mạng ít tin cậy hơn.
Một Logstash output sử dụng tài khoản Elasticsearch có quyền quản trị toàn cụm; khi thông tin xác thực bị lộ trong tệp cấu hình, phạm vi rủi ro lớn hơn nhu cầu chỉ ghi log.
Đội vận hành lưu mật khẩu và API key cho Beats, Logstash cùng Elasticsearch trực tiếp trong repository; sau khi thay đổi quyền đọc repository, nhiều bí mật tích hợp cần được rà soát.
Một bộ Elastic Agent hết hạn API key sau thay đổi chính sách bảo mật; Fleet hiển thị lỗi xác thực và log ứng dụng từ các host liên quan không còn được gửi.
Logstash gửi log tới Elasticsearch qua TLS nhưng không tin CA vừa được xoay; sau đợt gia hạn chứng chỉ, pipeline tích lũy hàng đợi dù cluster vẫn hoạt động bình thường.
Đội bật audit logging của Elasticsearch sau một sự cố quyền truy cập, nhưng bản ghi audit và application log được giữ chung chính sách ILM ngắn ngày; điều tra sau vài tháng thiếu lịch sử thay đổi quyền.
Nhóm điều tra phát hiện dữ liệu nhạy cảm đã vào index log trước khi bộ lọc che thông tin được áp dụng; các snapshot cũ và bản sao dữ liệu vẫn còn nội dung chưa được làm sạch.
Đội triển khai giới hạn số truy vấn đồng thời trên Elasticsearch nhưng dashboard Kibana có nhiều panel tự refresh mỗi vài giây; trong giờ cao điểm các truy vấn người dùng bị trì hoãn.
Một truy vấn log rất lớn lấy hàng trăm nghìn kết quả bằng phân trang sâu; Kibana và ứng dụng tìm kiếm nội bộ phản hồi chậm dù chỉ cần xác định vài dòng quan trọng.
Một chương trình xuất log phục vụ đối soát đọc rất nhiều tài liệu từ Elasticsearch trong giờ cao điểm; search latency tăng và việc ingest log mới cũng bị ảnh hưởng bởi CPU/heap dùng chung.
Đội phát triển xem slow logs của Elasticsearch và thấy nhiều truy vấn trên trường message; chưa phân biệt được thời gian nằm ở phân tích truy vấn, truy xuất shard hay tổng hợp kết quả.
Ứng dụng gửi bản ghi audit ít nhưng quan trọng, còn dịch vụ debug tạo hàng triệu log mỗi giờ; khi pipeline gặp nghẽn, cả hai loại sự kiện đến muộn và đội chưa có tiêu chí ưu tiên.
Trong một ca trực, dashboard báo số lượng event giảm đột ngột nhưng error rate ứng dụng vẫn tăng; nhóm chưa có metric giám sát đầy đủ từ Filebeat, Logstash tới Elasticsearch để xác định nơi mất dữ liệu.
Đội SRE đổi cấu hình grok parser, ILM và Kibana dashboard trong cùng một lần phát hành; sau đó báo cáo lỗi không khớp nhưng không có baseline để phân biệt sai lệch ingest, schema hay visualization.
Một sự cố diễn ra lúc 02:15, nhưng người điều tra chỉ dùng từ khóa 'timeout' trong Kibana và bỏ qua lọc theo service, environment, thời gian cũng như trace.id; kết quả quá nhiều và không xây được timeline nguyên nhân.
Trong lúc khắc phục sự cố dữ liệu, đội trực khôi phục Elasticsearch từ snapshot sang cluster mới; dữ liệu đã trở lại nhưng Kibana báo thiếu data view và các truy vấn dựa trên alias cũ không hiển thị.
Một team thay đổi ngưỡng cảnh báo dung lượng storage để giảm nhiễu; sau đó cụm vượt disk watermark trước khi có người kiểm tra log pipeline, khiến nhiều sự kiện quan trọng không được index đúng hạn.
