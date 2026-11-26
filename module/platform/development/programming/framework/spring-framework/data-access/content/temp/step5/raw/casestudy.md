Một dịch vụ đặt hàng Spring Boot dùng DataSource chung cho API và batch đêm, nhưng batch giữ nhiều kết nối quá lâu khiến request thanh toán chờ lấy connection rồi timeout.
Nhóm cấu hình JDBC URL của DataSource cho production bằng hostname lấy từ profile staging, khiến ứng dụng chạy bình thường nhưng mọi đơn thử nghiệm được ghi vào cơ sở dữ liệu thật.
Ứng dụng chuyển PostgreSQL sang cluster có TLS nhưng cấu hình DataSource vẫn dùng kết nối không mã hóa, khiến khởi động thất bại sau khi máy chủ bắt buộc xác thực chứng chỉ.
Đội vận hành xoay mật khẩu database định kỳ nhưng pool vẫn giữ credential cũ khi mở kết nối mới, khiến lỗi đăng nhập xuất hiện ngẫu nhiên trong thời gian triển khai.
Một service có hai DataSource beans cho báo cáo và giao dịch, nhưng JdbcTemplate được inject nhầm bean nên thao tác cập nhật đơn hàng bị gửi vào replica chỉ đọc.
Nhóm dùng cùng DataSource cho nhiều tenant nhưng tenant context lưu trong ThreadLocal không được chuyển vào tác vụ async, khiến query của một khách chạy trên schema mặc định.
Ứng dụng dùng AbstractRoutingDataSource để định tuyến vùng dữ liệu, nhưng routing key được xác định sau khi transaction đã lấy connection khiến một phần request truy cập sai tenant.
Đội thêm DataSource riêng cho bảng kiểm toán nhưng @Primary được gắn không đúng, khiến các service cũ bắt đầu đọc dữ liệu từ database audit thay vì database nghiệp vụ.
Một chương trình xử lý hóa đơn sử dụng SimpleDriverDataSource cho tải production cao, khiến mỗi truy vấn mở kết nối mới và độ trễ tăng mạnh ở giờ cao điểm.
Nhóm chạy test với EmbeddedDatabase nhưng production dùng PostgreSQL có kiểu số và quy tắc timestamp khác, khiến cùng RowMapper trả kết quả lệch trên dữ liệu thật.
Ứng dụng tạo DataSource bằng JDBC URL có tham số múi giờ sai, khiến dữ liệu được ghi đúng số nhưng báo cáo theo ngày dịch chuyển quanh nửa đêm.
Đội giới hạn số kết nối database ở mức thấp nhưng các microservice đều tạo pool lớn, khiến khi autoscale database từ chối kết nối mới dù từng pod vẫn dưới hạn mức.
Một service dùng tài khoản database có quyền chỉnh schema cho tác vụ chỉ đọc sản phẩm, khiến sự cố lộ credential từ ứng dụng mở rộng phạm vi phá hoại ngoài nhu cầu.
Nhóm triển khai DataSource qua secret manager nhưng một pod chưa nhận được secret mới trong rollout, khiến chỉ một nhóm request thất bại vì sai mật khẩu.
Ứng dụng chuyển từ Oracle sang PostgreSQL nhưng vẫn giữ một số connection properties dành cho Oracle, khiến khả năng kiểm soát session khác giữa test và production.
Đội cấu hình connection validation query chỉ chạy được trên một DBMS, khiến một nhóm pod báo không lấy được connection dù database mới vẫn khỏe.
Một service dùng DataSource với tùy chọn autoCommit thay đổi bởi một thư viện phụ, khiến thao tác ghi ngoài transaction không có vòng đời commit như nhóm kỳ vọng.
Nhóm sử dụng database replica cho các truy vấn đọc sau ghi, nhưng replication lag làm API trả đơn hàng cũ ngay sau khi khách vừa thanh toán thành công.
Ứng dụng triển khai nhiều DataSource cho từng khu vực nhưng chung cache statement cấu hình không phù hợp, khiến kiểm tra latency tăng mạnh chỉ tại một vùng.
Đội thay đổi DNS database primary trong sự cố nhưng connection pool vẫn giữ các socket cũ, khiến service tiếp tục lỗi kết nối một thời gian sau khi primary mới hoạt động.
Một dịch vụ đọc cấu hình database từ biến môi trường nhưng hostname có ký tự trống ở cuối, khiến kết nối được thử lặp mà log không cho thấy nguyên nhân rõ ràng.
Nhóm khởi chạy một ứng dụng mới với DataSource dùng kết nối tới database chưa được migration, khiến health kiểm tra JDBC thành công nhưng API liên tục lỗi thiếu bảng.
Ứng dụng đặt applicationName trong JDBC connection trùng cho mọi microservice, khiến đội DBA khó xác định service nào giữ các transaction dài trong hệ thống.
Đội muốn dùng PostgreSQL read replica cho báo cáo nhưng một lệnh lưu dữ liệu phát sinh trong service báo cáo, khiến request chỉ lỗi khi chuyển sang vùng đọc dự phòng.
Một chương trình đồng bộ dùng tài khoản database có quyền theo schema nhưng thiết lập default schema khác trên từng node, khiến cùng truy vấn không chỉ rõ schema đọc từ bảng khác nhau.
Nhóm dùng connection pool HikariCP với maximumPoolSize quá nhỏ so với số request đồng thời, khiến thời gian chờ kết nối chiếm phần lớn latency của API.
Một service tăng maximumPoolSize theo số thread nhưng không xét max_connections toàn cụm, khiến các pod tự cạnh tranh và database bị nghẽn sau autoscaling.
Đội cấu hình connectionTimeout HikariCP dài hơn timeout HTTP gateway, khiến thread của ứng dụng vẫn chờ pool sau khi khách đã nhận lỗi.
Ứng dụng đặt maxLifetime của connection vượt vòng đời do load balancer database áp đặt, khiến socket bị đóng ở giữa truy vấn và phát sinh lỗi không đều.
Nhóm không cấu hình idleTimeout phù hợp cho workload dao động, khiến database phải quản lý nhiều idle sessions suốt đêm dù request đã giảm về gần không.
Một service có transaction đọc báo cáo kéo dài vài phút và giữ connection trong toàn bộ thời gian tạo PDF, khiến pool không còn chỗ cho những truy vấn ngắn của người dùng.
Đội tạo connection bằng DataSource.getConnection trong mỗi vòng lặp nhưng nhánh exception không đóng tài nguyên, khiến số active connections tăng đều cho tới khi pool cạn.
Ứng dụng dùng JdbcTemplate nhưng đồng thời tạo PreparedStatement thủ công mà không đóng ResultSet, khiến tài nguyên JDBC bị rò rỉ trong job chạy liên tục.
Nhóm bật leakDetectionThreshold ở HikariCP rất thấp và coi mọi cảnh báo là leak, khiến job báo cáo hợp lệ tạo hàng trăm log cảnh báo giả.
Một service phát hiện pool pending threads tăng cao nhưng dashboard chỉ theo dõi database CPU, khiến nguyên nhân timeout do connection acquisition bị bỏ qua.
Đội khởi tạo một HikariDataSource mới cho mỗi tenant request thay vì tái dùng pool, khiến số socket tới PostgreSQL tăng theo lưu lượng khách.
Ứng dụng có pool minimumIdle lớn trên hàng chục pod, khiến hệ thống chiếm gần toàn bộ connection slots ngay cả khi traffic chưa đến.
Nhóm mở transaction rồi gọi HTTP đối tác trong cùng luồng trước khi commit, khiến connection database bị giữ lâu trong thời gian mạng đối tác chậm.
Một service có query nhanh nhưng mỗi request tải hàng trăm bản ghi rồi serialize chậm trong transaction, khiến pool chờ tăng dù SQL execution time thấp.
Đội đặt validationTimeout quá ngắn khi database ở vùng khác, khiến nhiều connection khỏe bị xem là không hợp lệ trong đợt network jitter.
Ứng dụng không kiểm tra connection pool shutdown khi context bị đóng, khiến các lần chạy integration test nối tiếp để lại socket tới database thử nghiệm.
Nhóm cho rằng JDBC DataSource luôn cung cấp thread safety nhưng một cấu hình tùy biến giữ state của một connection trong singleton, khiến kết quả bị trộn khi hai request đồng thời.
Một service dùng connection pool ở hai vùng nhưng connection validation chạy qua DNS chập chờn, khiến một vùng tăng lỗi borrow dù query trên connection đang mở vẫn thành công.
Đội tăng thread pool xử lý HTTP nhưng không điều chỉnh giới hạn kết nối tới database, khiến p95 latency tăng vì request chủ yếu chờ connection.
Ứng dụng dùng HikariCP với các metrics disabled nên không phân biệt connection pool exhaustion và lock contention ở database khi API timeout.
Nhóm cấu hình socketTimeout của JDBC driver bằng giá trị quá lớn, khiến một truy vấn treo giữ connection dù cancellation từ HTTP request đã xảy ra.
Một service chỉ dùng một Connection thủ công cho toàn bộ batch và chia sẻ qua nhiều worker, khiến thao tác PreparedStatement của hai luồng tác động chéo transaction state.
Đội thay đổi isolation level trên connection lấy từ pool nhưng trả lại mà không đảm bảo trạng thái được quản lý phù hợp, khiến request kế tiếp có hành vi khác dự kiến.
Ứng dụng gọi JdbcTemplate.queryForObject để lấy khách theo email nhưng dữ liệu thực có hai hồ sơ trùng email, khiến endpoint báo lỗi thay vì trả một hồ sơ theo hợp đồng.
Nhóm sử dụng JdbcTemplate.queryForObject cho tài khoản chưa được tạo, nhưng không phân biệt kết quả rỗng với lỗi hạ tầng và API trả mã 500 cho việc không tồn tại.
Một service dùng JdbcTemplate.queryForList cho lịch sử giao dịch hàng triệu dòng, khiến JVM tăng memory đột ngột khi khách yêu cầu xuất toàn bộ lịch sử.
Đội viết RowMapper cho bản ghi đơn hàng nhưng mapper lấy cột theo vị trí, khiến thay đổi thứ tự SELECT sau refactor làm trạng thái và số tiền bị ánh xạ nhầm.
Ứng dụng sử dụng RowMapper đọc cột DECIMAL vào double, khiến phép tính số tiền làm tròn khác nhau ở một số hóa đơn có nhiều chữ số thập phân.
Nhóm đọc timestamp SQL vào LocalDateTime nhưng server lưu theo UTC còn API hiển thị múi giờ địa phương, khiến ngày thanh toán sai gần thời điểm đổi ngày.
Một service dùng BeanPropertyRowMapper với tên cột tiếng Anh không khớp thuộc tính Java, khiến một số field DTO âm thầm nhận null sau khi schema đổi.
Đội ánh xạ enum trạng thái từ DB nhưng dữ liệu cũ chứa giá trị không còn trong enum Java, khiến toàn bộ trang báo cáo lỗi khi chạm một bản ghi lịch sử.
Ứng dụng xây RowMapper đọc SQL NULL ở cột integer bằng API trả số nguyên mặc định, khiến bản ghi chưa có điểm tín dụng bị diễn giải là 0.
Nhóm dùng JdbcTemplate.queryForMap để lấy một hàng nhưng SQL trả nhiều dòng khi khách có hai địa chỉ, khiến một API tưởng đơn giản phát sinh ngoại lệ ngoài dự kiến.
Một service truy vấn order cùng order_items bằng JOIN nhưng RowMapper tạo một Order mới trên mỗi dòng, khiến một đơn có nhiều mặt hàng xuất hiện trùng trong response.
Đội sử dụng ResultSetExtractor để dựng cây dữ liệu cha-con nhưng không phân biệt khóa định danh bị null ở LEFT JOIN, khiến các đơn không có item được dựng với item rỗng giả.
Ứng dụng dùng RowCallbackHandler để xử lý từng bản ghi báo cáo nhưng callback giữ toàn bộ DTO trong list, khiến lợi ích xử lý dòng bị mất khi số dữ liệu tăng.
Nhóm viết query SELECT * cho màn hình khách hàng rồi chuyển các trường sang response, khiến cột nội bộ mới được thêm vào database có nguy cơ lộ qua API.
Một service dùng SingleColumnRowMapper để đọc danh sách IDs nhưng SQL trả thêm cột debug, khiến kết quả parse lỗi chỉ trong một nhánh truy vấn.
Đội sử dụng SqlRowSet để cho controller trả dữ liệu sau khi transaction kết thúc, nhưng việc chuyển đổi kiểu ngày và null khác ResultSet mapper hiện có.
Ứng dụng đọc BLOB ảnh sản phẩm qua RowMapper của danh sách phân trang, khiến mỗi request nạp dữ liệu nhị phân lớn dù UI chỉ cần tên và mã sản phẩm.
Nhóm dùng JdbcTemplate.queryForStream để xuất bản ghi nhưng controller không đóng stream khi khách hủy download, khiến connection bị giữ lâu sau request.
Một service trả Stream từ query method ra ngoài @Transactional method, khiến lúc stream được tiêu thụ thì connection và ResultSet không còn trong vòng đời dự kiến.
Đội viết ResultSetExtractor dùng mã định danh customerId làm key nhưng hai tenant có cùng ID, khiến khi dựng aggregate nhiều tenant dữ liệu bị gộp nhầm.
Ứng dụng đổi tên cột order_status thành status nhưng câu query dùng alias khác ở môi trường production, khiến RowMapper thất bại khi đọc cột cũ.
Nhóm ánh xạ JSON text ở một cột thành DTO nhưng dữ liệu lịch sử có schema khác, khiến quá trình đọc kết quả JDBC bị lỗi cho những đơn được tạo trước đợt nâng cấp.
Một service cần đọc số lớn từ BIGINT nhưng DTO dùng int, khiến các định danh đơn mới vượt giới hạn kiểu Java và response có giá trị sai.
Đội dùng JdbcTemplate.query trả danh sách với LIMIT từ đầu vào chưa được giới hạn, khiến một khách đặt giá trị rất lớn và ứng dụng phải xử lý kết quả vượt mức bộ nhớ.
Ứng dụng xử lý cùng bản ghi SQL từ hai kiểu driver nhưng getObject trả kiểu ngày khác nhau, khiến custom mapper chỉ hỗ trợ driver cũ và lỗi sau di trú.
Nhóm dùng JdbcTemplate với SQL builder tự nối chuỗi từ email người dùng, khiến ký tự trích dẫn làm query sai và tạo nguy cơ SQL injection.
Một service tra cứu khách theo danh sách ID nhưng tạo chuỗi IN bằng cách nối ID do client gửi, khiến request có hàng nghìn giá trị làm SQL dài và khó kiểm soát.
Đội nhận tham số ngày từ API nhưng bind dưới dạng chuỗi locale, khiến một số ngày 03/04 được database hiểu khác giữa hai môi trường.
Ứng dụng sử dụng PreparedStatementSetter cho truy vấn theo kho nhưng bind tham số thứ hai và thứ ba sai thứ tự, khiến kết quả sai chỉ khi cả hai bộ lọc cùng được sử dụng.
Nhóm viết truy vấn với nhiều dấu hỏi positional parameters rồi thêm bộ lọc tùy chọn, khiến chỉ một tổ hợp điều kiện bị lệch vị trí bind.
Một service dùng named parameter trong JdbcClient với cùng tên ở nhiều chỗ nhưng một nhánh đặt sai tên, khiến chỉ request chọn điều kiện khuyến mãi lỗi binding.
Đội nhập số tiền từ HTTP dưới dạng chuỗi rồi bind vào cột DECIMAL với quy tắc chuyển đổi ngầm của database, khiến giá trị dấu phẩy thập phân bị từ chối tại một quốc gia.
Ứng dụng có truy vấn theo địa bàn nhưng dùng giá trị wildcard từ người dùng để tạo LIKE pattern, khiến ký tự phần trăm trong tên sản phẩm làm kết quả quá rộng.
Nhóm dựng câu ORDER BY từ tham số client mà không giới hạn tên cột, khiến request có thể tác động cấu trúc câu SQL ngoài các lựa chọn sort sản phẩm cho phép.
Một service dùng JdbcTemplate để tìm khách theo UUID nhưng bind giá trị dưới dạng text, khiến query trên database mới không dùng được chỉ mục như ở môi trường cũ.
Đội chuyển các tham số timestamp sang OffsetDateTime nhưng một driver chưa hỗ trợ kiểu bind đang chọn, khiến truy vấn chỉ lỗi khi người dùng cung cấp khoảng thời gian.
Ứng dụng dùng PreparedStatement với batch nhiều loại câu lệnh nhưng danh sách tham số không còn khớp cấu trúc SQL sau lần refactor, khiến một số hàng được ghi sai field.
Nhóm cần tìm sản phẩm có tên chứa dấu gạch dưới, nhưng biểu thức LIKE tự xây hiểu dấu dưới là wildcard và trả những mặt hàng không cùng mã.
Một service chọn database schema từ tham số tenant do client gửi mà không đối chiếu quyền, khiến người dùng có thể yêu cầu truy vấn trên schema của tổ chức khác.
Đội cấu hình JDBC driver cho parameter metadata nhưng custom query builder thêm điều kiện khi một giá trị null, khiến SQL trả khác kỳ vọng do phép so sánh NULL.
Ứng dụng dùng JdbcTemplate.query với danh sách tham số gồm collection không được chuyển thành placeholders tương ứng, khiến truy vấn theo nhiều mã sản phẩm không hoạt động.
Nhóm muốn bind một tên bảng động theo tenant như value parameter nhưng JDBC prepared statement không hỗ trợ identifier binding như cột dữ liệu, khiến cách xây truy vấn gặp lỗi.
Một service xây query với NamedParameterJdbcTemplate nhưng map tham số chứa hai khóa tương đương viết hoa khác nhau, khiến một nhánh request dùng giá trị không dự kiến.
Đội dự tính tránh SQL injection bằng PreparedStatement nhưng phần câu điều kiện JOIN vẫn được nối từ giá trị HTTP đầu vào, khiến đường tấn công còn tồn tại ngoài values.
Ứng dụng sử dụng JdbcClient.sql để lấy số liệu đơn nhưng thay đổi từ positional sang named binding mà còn một placeholder cũ, khiến test đơn giản PASS còn filter mở rộng lỗi.
Nhóm nâng Spring Framework có JdbcClient và dùng cùng câu SQL từ repository cũ, nhưng hàm trả về một giá trị lại gặp nhiều hàng trong dữ liệu production.
Một service dùng JdbcClient để đọc ProductDTO và kỳ vọng tự khớp tên thuộc tính nhưng query trả alias khác với Java model, khiến một phần field không được điền.
Đội trộn JdbcClient với JdbcTemplate trong một service nhưng dùng hai DataSource khác nhau, khiến một lần ghi có vẻ thành công trong khi đường đọc mới không thấy dữ liệu.
Ứng dụng chọn JdbcClient để giảm boilerplate nhưng một số API vẫn cần custom RowMapper xử lý JSON lồng sâu, khiến các phương thức đọc trả shape khác nhau cho cùng bảng.
Nhóm dùng JdbcClient bind theo tên cho thông tin khách nhưng một tham số tùy chọn null bị bỏ khỏi map, khiến query báo thiếu binding chỉ khi khách không nhập số điện thoại.
Một service muốn lấy bản ghi duy nhất bằng JdbcClient nhưng query đối soát có nhiều dòng hợp lệ, khiến ngoại lệ sai số lượng kết quả bị chuyển thành lỗi nội bộ.
Đội triển khai lưu tiền bằng JdbcClient trong transaction nhưng một phương thức helper dùng DataSource.getConnection trực tiếp, khiến hai câu SQL không cùng connection như mong đợi.
Ứng dụng dùng JdbcClient trả Optional từ truy vấn hồ sơ nhưng controller coi không tìm thấy như một lỗi database, khiến API từ chối đăng ký tài khoản mới.
Nhóm di trú từ JdbcTemplate sang JdbcClient nhưng giữ một interceptor log chưa che tham số nhạy cảm, khiến dữ liệu thẻ thanh toán xuất hiện trong SQL logs.
Một service dùng JdbcClient cho một phần cập nhật giỏ hàng nhưng đọc từ JdbcTemplate qua replica, khiến ngay sau mutation cùng request nhận giá trị cũ.
Đội thay kết quả query từ danh sách sang single-object trong JdbcClient mà không cập nhật test cho nhiều dòng, khiến lỗi chỉ lộ khi sản phẩm có nhiều biến thể.
Ứng dụng bind một enum bằng Java tên hiển thị khác với giá trị database lưu, khiến bản JdbcClient mới không trả dòng dù cùng SQL chạy được với JdbcTemplate cũ.
Nhóm dùng JdbcClient để thực thi SQL cập nhật nhưng không kiểm tra số hàng affected, khiến API trả thành công dù đơn đã bị xóa hoặc phiên bản đã đổi.
Một service trông đợi JdbcClient tự quản lý transaction độc lập, nhưng method được gọi ngoài transaction nên hai cập nhật liên tiếp có thể chỉ một lệnh được commit.
Đội dùng SqlParameterSource để map một DTO nhiều thuộc tính nhưng DTO đổi tên field, khiến tên tham số câu UPDATE không còn dữ liệu phù hợp trong một nhánh.
Ứng dụng sử dụng NamedParameterJdbcTemplate với collection IDs rất lớn, khiến số lượng placeholders vượt giới hạn của driver hoặc cơ sở dữ liệu trong báo cáo khách hàng.
Nhóm dùng MapSqlParameterSource cho điều kiện bắt buộc nhưng có trường timestamp null, khiến một lệnh cập nhật ghi SQL NULL và làm hỏng bộ lọc báo cáo.
Một service dùng SimpleJdbcInsert để thêm sản phẩm nhưng schema database tự tạo cột audit mới bắt buộc, khiến insert không còn thành công sau migration.
Đội khai báo SimpleJdbcInsert sử dụng generated key từ cột ID khác tên thực, khiến API không có ID cho tài nguyên vừa tạo dù SQL insert đã được thực thi.
Ứng dụng nhập lô dữ liệu và dùng SimpleJdbcInsert cho mỗi hàng, nhưng số lần round-trip tới database tăng mạnh khi batch đạt hàng trăm nghìn bản ghi.
Nhóm gọi JdbcTemplate.update để sửa giá nhưng không kiểm tra affected rows, khiến một request update sản phẩm không tồn tại vẫn được coi là đã thay đổi thành công.
Một service dùng JdbcTemplate.update cho optimistic update theo version, nhưng hai request đồng thời cùng gửi version cũ và một request không sửa dòng nào mà API không phát hiện.
Đội cập nhật số dư bằng hai câu UPDATE tách rời không có ranh giới transaction, khiến lỗi giữa hai câu làm tổng số tiền giữa tài khoản nguồn và đích không cân bằng.
Ứng dụng tạo bản ghi order rồi lấy generated key bằng GeneratedKeyHolder, nhưng trigger của DB và cấu hình driver thay đổi khiến key được lấy không đúng cách API kỳ vọng.
Nhóm gán createdAt bằng thời gian JVM trong khi database dùng CURRENT_TIMESTAMP cho các bản ghi khác, khiến thứ tự cập nhật giao dịch theo thời gian không nhất quán giữa các pod.
Một service dùng JdbcTemplate cho upsert sản phẩm nhưng các môi trường PostgreSQL và MySQL có cú pháp conflict handling khác nhau, khiến chức năng chỉ chạy ở một DBMS.
Đội gộp nhiều cập nhật giá vào cùng câu UPDATE không có điều kiện tenant, khiến một lần chạy chương trình điều chỉnh giá ảnh hưởng cả doanh nghiệp khác.
Ứng dụng cần xóa tài khoản nhưng bảng quan hệ còn foreign key, khiến lệnh JdbcTemplate.update trả lỗi constraint và API không giải thích được nguyên nhân nghiệp vụ.
Nhóm dùng ResultSetExtractor để lấy dữ liệu sau UPDATE bằng cú pháp RETURNING của một DBMS, nhưng môi trường chạy database khác không hỗ trợ hợp đồng tương ứng.
Một service gọi INSERT rồi SELECT riêng để xác minh kết quả mà không kiểm soát hai luồng cập nhật cạnh tranh, khiến dữ liệu được đọc không còn là bản vừa ghi.
Đội tạo nhiều bản ghi nhập kho trong một request nhưng một phần SQL chạy trước validation nghiệp vụ, khiến thông tin tạm được lưu khi một item cuối không hợp lệ.
Ứng dụng lưu số tiền có precision cao nhưng schema cột DECIMAL nhỏ hơn yêu cầu sản phẩm, khiến lỗi chỉ xảy ra với hóa đơn lớn dù mapper Java chấp nhận giá trị.
Nhóm cần phân biệt số hàng cập nhật bằng 0 với exception database, nhưng tầng service gộp cả hai thành trạng thái thành công làm mất dữ liệu đầu ra kỳ vọng.
Một service chuẩn bị câu SQL update có WHERE chứa tenantId nhưng một request async không mang tenant context, khiến thao tác ghi sửa nhầm bản ghi trong schema mặc định.
Đội dùng JdbcTemplate.batchUpdate để nạp 50 nghìn giao dịch nhưng driver không hỗ trợ batching hiệu quả, khiến tốc độ chậm hơn kỳ vọng từ môi trường test.
Ứng dụng gửi batchUpdate gồm nhiều lệnh nhưng một dòng vi phạm unique constraint, khiến xử lý batch có phần đã thành công và trạng thái trả về không đáp ứng kỳ vọng all-or-nothing.
Nhóm thực hiện nhập giá sản phẩm bằng JdbcTemplate.batchUpdate mà không kiểm tra mảng update counts, khiến những mặt hàng không khớp điều kiện vẫn được báo đã cập nhật.
Một service sử dụng BatchPreparedStatementSetter nhưng đặt kích thước batch lớn hơn danh sách dữ liệu, khiến lệnh lấy phần tử cuối bị lỗi khi chạy nhập kho.
Đội nạp dữ liệu qua batchUpdate trong transaction lớn vài triệu hàng, khiến khóa và transaction log tăng mạnh và các API cập nhật trực tuyến bị chậm.
Ứng dụng chia batch thành nhiều chunk nhưng ghi tiến độ trước khi chunk được commit, khiến sau crash job bỏ qua các bản ghi chưa được lưu thật.
Nhóm dùng batchUpdate và retry toàn bộ lô khi timeout, khiến các dòng đã insert thành công bị lặp hoặc vi phạm khóa duy nhất sau lần chạy lại.
Một service chạy parallel batch updates trên cùng bảng nhưng các worker không cố định thứ tự khóa, khiến database gặp deadlock khi hai lô chạm cùng các sản phẩm.
Đội dùng batchUpdate từ nhiều threads nhưng chia sẻ một mutable parameter array, khiến một số dòng được bind giá trị của dòng khác khi tải tăng.
Ứng dụng nhập danh sách khách từ CSV nhưng trường email có dấu ngoặc và ký tự lạ, khiến batch viết SQL bằng chuỗi nối bị lỗi tại những dòng dữ liệu thật.
Nhóm muốn đồng bộ sự kiện sản phẩm qua batchUpdate nhưng mỗi chunk cần phát Kafka event sau commit, khiến trạng thái đã phát và trạng thái DB có thể lệch khi worker lỗi.
Một service tính toán tổng doanh thu theo lô rồi ghi nhiều bảng trong một transaction dài, khiến các truy vấn báo cáo khác chờ lock và vượt SLO.
Đội xử lý cập nhật tồn kho số lượng lớn qua batchUpdate nhưng một lệnh trả số hàng affected khác 1, khiến job vẫn đánh dấu đầy đủ dù có sản phẩm không tồn tại.
Ứng dụng nhập dữ liệu thời gian từ nhiều thị trường với các format khác nhau nhưng batch setter bind chuỗi trực tiếp, khiến chỉ các dòng từ một quốc gia bị từ chối.
Nhóm dùng transaction cho toàn bộ batch import nhưng vẫn gọi API bên ngoài trong mỗi vòng lặp, khiến connection bị giữ trong khi đối tác chậm hoặc lỗi mạng.
Một service đồng bộ tất cả khách bằng một batch SQL khổng lồ trên database dùng replication, khiến replication lag tăng và báo cáo đọc từ replica bị cũ.
Đội muốn đánh giá thông lượng batch nhưng benchmark chỉ dùng dữ liệu cùng schema và không có duplicate keys, khiến tình huống xử lý lỗi từng dòng không được đo.
Ứng dụng gặp BatchUpdateException nhưng tầng Spring chỉ log một nguyên nhân chung, khiến nhóm không biết bản ghi nào vi phạm ràng buộc trong lô.
Nhóm chuyển driver JDBC và kết quả batch update trả SUCCESS_NO_INFO cho một số hàng, khiến logic đối soát cũ hiểu nhầm rằng số hàng được cập nhật bằng 0.
Một service dùng JdbcTemplate batch cho mỗi phân vùng tenant nhưng quên ràng buộc transaction context theo tenant, khiến chunk được ghi vào database sai khu vực.
Đội muốn dùng batch để giảm round-trip nhưng batch chứa nhiều SQL khác nhau chứ không cùng statement, khiến cách gom lệnh không tương thích với setter đang có.
Ứng dụng cập nhật dữ liệu lô rồi trả tổng số hàng sửa, nhưng sum update counts không xử lý các giá trị đặc biệt của JDBC nên số liệu hiển thị không chính xác.
Nhóm lập trình job retry các batch thất bại mà không có idempotency key, khiến số lần ghi dữ liệu kiểm toán lớn hơn số event nguồn sau restart.
Một service xử lý 100 nghìn đơn đêm bằng một transaction duy nhất rồi gặp lỗi ở cuối, khiến hàng giờ nhập liệu phải rollback và lịch chạy bị vượt hạn.
Đội triển khai batchUpdate vào cơ sở dữ liệu có trigger tạo dữ liệu phụ, nhưng báo cáo chỉ đo rows affected của bảng chính và không nhìn thấy áp lực ghi tăng.
Ứng dụng cập nhật bằng nhiều batch có checkpoint nhưng dữ liệu nguồn được sửa trong lúc batch chạy, khiến các chunk sau dùng ảnh chụp dữ liệu khác thời điểm.
Nhóm gọi một stored procedure kiểm tra tín dụng qua SimpleJdbcCall nhưng tên schema của procedure khác giữa staging và production, khiến chỉ môi trường thật báo không tìm thấy.
Một service dùng SimpleJdbcCall tự phát hiện tham số procedure nhưng tài khoản production bị hạn chế metadata access, khiến việc gọi procedure lỗi trước khi thực thi nghiệp vụ.
Đội khai báo input parameter cho stored procedure theo thứ tự cũ sau khi DBA thêm một tham số mới, khiến kết quả xử lý hóa đơn chỉ sai ở những đơn có loại thuế đặc biệt.
Ứng dụng gọi stored procedure trả nhiều OUT parameters nhưng mapper chỉ đọc một trường status, khiến mã lỗi chi tiết bị bỏ qua và API trả thành công sai.
Nhóm nâng cấp database package chứa stored procedure mà đầu ra REF CURSOR đổi tên, khiến RowMapper ứng dụng không nhận được danh sách giao dịch như trước.
Một service dùng SimpleJdbcCall để lấy dữ liệu báo cáo nhưng stored procedure mở cursor lớn và không được xử lý trong vòng đời connection phù hợp, khiến pool bị giữ quá lâu.
Đội gọi procedure thực hiện nhiều lệnh cập nhật và kỳ vọng @Transactional Java rollback mọi tác động, nhưng procedure có hành vi transaction riêng không được phân tích rõ.
Ứng dụng nhận mã trả về từ function cơ sở dữ liệu nhưng custom mapper coi giá trị null là thành công, khiến lỗi nghiệp vụ bị hiển thị như đã xử lý.
Nhóm gọi procedure trên Oracle nhưng integration test chỉ dùng H2 không hỗ trợ cùng kiểu OUT parameter, khiến vấn đề tương thích không được phát hiện trước production.
Một service dùng JdbcTemplate.call trực tiếp cho nghiệp vụ có nhiều result sets, nhưng code đọc sai thứ tự result sets khi procedure thay đổi hợp đồng đầu ra.
Đội để SimpleJdbcCall tự dùng database metadata ở mỗi request mà không tái sử dụng cấu hình phù hợp, khiến thời gian chuẩn bị gọi tăng rõ khi lưu lượng lớn.
Ứng dụng gọi procedure với tên tài khoản chứa ký tự Unicode nhưng parameter binding chọn sai kiểu dữ liệu, khiến các hồ sơ có dấu không được xử lý.
Nhóm dùng stored procedure để cấp mã đơn hàng nhưng trong đợt network timeout không rõ procedure đã chạy hay chưa, khiến client retry và có nguy cơ tạo mã trùng.
Một service chuyển procedure từ SQL Server sang PostgreSQL nhưng tầng Spring vẫn kỳ vọng cùng cách biểu diễn kết quả và tham số, khiến chuyển đổi database không đồng nhất.
Đội gọi stored procedure với tham số nhạy cảm trong hệ thống tài chính nhưng logger hiện ghi toàn bộ parameter values khi có exception, khiến dữ liệu khách xuất hiện trong log.
Ứng dụng nhận nhiều cursor kết quả từ procedure nhưng đưa toàn bộ vào list trước khi trả trang báo cáo, khiến bộ nhớ tăng mạnh khi dữ liệu lịch sử lớn.
Nhóm triển khai function database trả giá trị số thập phân nhưng SimpleJdbcCall mapper ép thành int, khiến số tiền lớn bị làm tròn hoặc vượt giới hạn.
Một service có hai procedure cùng tên trong các schema khác nhau, nhưng cấu hình currentSchema thay đổi theo DataSource khiến request ở một số tenant gọi nhầm procedure.
Đội thay quyền execute cho service account sau audit bảo mật, khiến SimpleJdbcCall hoạt động ở môi trường dev nhưng bị từ chối trên production.
Ứng dụng dùng procedure để cập nhật nhiều bảng nhưng không có dấu vết transaction ID từ Java, khiến đội vận hành khó truy vết lỗi SQL trong quy trình phức tạp.
Nhóm nhận OUT parameter là mã trạng thái và INOUT là số dư, nhưng sau nâng cấp procedure logic ánh xạ INOUT không nhất quán với DTO trả về.
Một service thực hiện JdbcTemplate.update trên bảng có unique constraint nhưng tầng API bắt tất cả DataAccessException và trả lỗi 500 thay vì thể hiện xung đột nghiệp vụ.
Đội dựa vào DuplicateKeyException để xử lý việc tạo khách trùng nhưng DBMS mới dùng mã lỗi khác và translator chưa được cấu hình như mong đợi.
Ứng dụng gửi một query đến bảng không tồn tại sau migration, nhưng lớp service nuốt BadSqlGrammarException rồi trả danh sách rỗng khiến lỗi triển khai bị che khuất.
Nhóm xử lý DataIntegrityViolationException bằng cách retry tự động, khiến cùng request tạo dữ liệu vi phạm ràng buộc bị thử lại hàng chục lần vô ích.
Một service cần phân biệt database down với no row found, nhưng catch DataAccessException chung khiến API chuyển cả hai thành 404 và khách tưởng hồ sơ bị xóa.
Đội ghi log nguyên SQLException cùng SQL và tất cả bind values, khiến token và thông tin khách bị lưu ở hệ thống quan sát ngoài chính sách.
Ứng dụng chuyển sang driver vendor khác nhưng một lỗi timeout được dịch sang loại DataAccessException không như tầng retry dự kiến, khiến client retry sai loại thao tác.
Nhóm sử dụng SQLExceptionTranslator tùy chỉnh cho database legacy nhưng chỉ map một vài error codes, khiến các lỗi deadlock mới không được phân loại trong production.
Một service bắt transient data access exception rồi retry trong cùng transaction đã bị đánh dấu rollback-only, khiến mọi lần retry tiếp theo không thể commit như kỳ vọng.
Đội coi mọi TransientDataAccessException đều an toàn để retry, nhưng lệnh INSERT đã có thể được database thực thi trước khi connection timeout nên có nguy cơ trùng nghiệp vụ.
Ứng dụng dùng UncategorizedSQLException từ một driver mới nhưng dashboard chỉ theo dõi lỗi truy cập dữ liệu đã phân loại, khiến số sự cố kết nối bị báo thiếu.
Nhóm muốn trả thông tin lỗi cột dữ liệu sai định dạng từ SQL tới frontend nhưng mapper exception đang lộ nguyên tên bảng và schema database nội bộ.
Một service gặp DeadlockLoserDataAccessException hoặc dạng deadlock tương ứng theo driver, nhưng chính sách backoff không đủ khiến hai worker tiếp tục va chạm khóa.
Đội viết catch EmptyResultDataAccessException rồi coi người dùng không có quyền cũng như không tồn tại, khiến cơ chế API không phân biệt lỗi phân quyền và thiếu dữ liệu.
Ứng dụng gọi queryForObject trên một truy vấn nhiều dòng làm phát sinh IncorrectResultSizeDataAccessException nhưng hệ thống ghi nhận là lỗi database tạm thời và retry liên tục.
Nhóm dùng exception translation ở một repository nhưng một helper khác gọi JDBC trực tiếp không qua lớp dịch lỗi, khiến hai đường truy cập cùng lỗi trả hai loại exception khác nhau.
Một service cần xác định lỗi pool exhaustion nhưng log chỉ thấy DataAccessResourceFailureException, khiến đội trực điều tra database slow query thay vì số kết nối chờ.
Đội thay DataSource vendor và chuyển JDBC driver nhưng vẫn dùng error code translation dành cho DBMS trước, khiến ràng buộc khóa duy nhất bị diễn giải sai trong một số API.
Ứng dụng nuốt exception ở tầng DAO và trả object mặc định, khiến @Transactional method phía trên vẫn commit những thay đổi trước đó dù một bước lưu thất bại.
Nhóm bắt exception checked riêng và throw lại ngoại lệ nghiệp vụ nhưng mặc định rollback rule không giống kỳ vọng, khiến một phần dữ liệu vẫn được commit sau request lỗi.
Một service cập nhật bảng kế toán theo hai câu JdbcTemplate.update nhưng method không có transaction, khiến lỗi câu thứ hai vẫn để lại bút toán đã ghi ở câu đầu.
Đội đặt @Transactional trên một helper private rồi gọi nội bộ, khiến transaction không được mở dù log đang cho thấy hàm được thực thi bình thường.
Ứng dụng dùng @Transactional trên method public nhưng được gọi từ cùng bean, khiến đường xử lý batch bỏ qua proxy và các cập nhật không còn cùng ranh giới transaction.
Nhóm đánh dấu @Transactional trên hàm tra cứu báo cáo nhưng bên trong gọi API đối tác chậm, khiến connection database bị giữ suốt thời gian chờ mạng.
Một service đánh dấu readOnly=true trên transaction đọc nhưng một helper bên dưới thực hiện UPDATE, khiến hành vi ghi khác nhau giữa các database và connection settings.
Đội dùng propagation REQUIRES_NEW để ghi audit nhưng pool không đủ connection khi nhiều outer transactions đang mở, khiến thao tác audit chờ kết nối và request bị deadlock tài nguyên.
Ứng dụng thực hiện transaction NESTED với savepoint nhưng DataSource/transaction manager không hỗ trợ cách lồng như test giả định, khiến batch phát sinh lỗi khi gặp dòng sai.
Nhóm gọi một method @Transactional từ executor thread mà không chuyển transaction context, khiến thao tác ghi nền không thuộc transaction của yêu cầu HTTP ban đầu.
Một service sử dụng @Async để xử lý email trong transaction cập nhật tài khoản, khiến email được gửi trước khi transaction commit và người dùng nhận thông báo về thay đổi đã rollback.
Đội mở một transaction với isolation READ_COMMITTED nhưng dùng giá trị đọc nhiều lần để tính tồn kho, khiến hàng được thay đổi giữa hai lần đọc và quyết định nhập hàng sai.
Ứng dụng có báo cáo dựa trên nhiều truy vấn nhưng isolation hiện tại cho phép dữ liệu thay đổi giữa các câu SELECT, khiến tổng và chi tiết không khớp trong cùng báo cáo.
Nhóm thiết lập isolation SERIALIZABLE cho mọi giao dịch ghi nhỏ mà không đo tỉ lệ transaction abort, khiến hệ thống nhận nhiều lỗi retry dưới tải cao.
Một service đọc số dư rồi trừ trong hai bước không khóa/version, khiến hai request đồng thời đều cho phép rút số tiền vượt hạn mức.
Đội dùng @Transactional để cập nhật database A và gửi message RabbitMQ, nhưng broker từ chối message sau khi commit khiến hệ thống ngoài không nhận được sự kiện thay đổi.
Ứng dụng có hai DataSource và hai local transaction managers nhưng method dùng @Transactional không chỉ rõ manager, khiến chỉ một database được rollback khi bước còn lại lỗi.
Nhóm thực hiện giao dịch chuyển tiền giữa hai cơ sở dữ liệu khác nhau và nghĩ DataSourceTransactionManager tự đảm bảo atomicity cho cả hai nguồn, khiến bút toán lệch sau sự cố.
Một service cần trả lại trạng thái chính xác khi transaction bị timeout, nhưng client chỉ nhận HTTP 500 trong lúc server đã ghi một phần thao tác trước khi rollback.
Đội chạy SELECT FOR UPDATE từ JdbcTemplate rồi gọi thư viện mở connection khác, khiến câu UPDATE không hưởng lock đang giữ như nhóm dự kiến.
Ứng dụng dùng DataSourceUtils để lấy connection trong transaction ở một đường truy cập nhưng helper khác tự gọi DriverManager, khiến hai SQL statements không cùng session.
Nhóm dùng TransactionAwareDataSourceProxy cho thư viện legacy nhưng một thành phần kết nối qua DataSource gốc không nhất quán, khiến ranh giới transaction khác nhau giữa các helper.
Một service đặt isolation level trên connection raw rồi gọi JdbcTemplate ở connection do Spring quản lý, khiến mức cách ly thực tế của câu SQL không như kỳ vọng.
Đội có một @Transactional method chèn order và giảm tồn kho, nhưng ngoại lệ nghiệp vụ được catch rồi không throw tiếp làm Spring commit order dù tồn kho không giảm.
Ứng dụng gửi request xác minh tín dụng trong transaction và retry HTTP khi lỗi, khiến database lock bị giữ lâu và nhiều lệnh ghi khác chờ nhau.
Nhóm đặt transaction timeout quá ngắn cho job import lớn, khiến job rollback gần cuối nhưng log báo lỗi từ SQL cuối mà không nêu đủ nguyên nhân timeout.
Một service thực hiện @Transactional(readOnly=true) cho API danh sách nhưng truy vấn dùng SELECT với khóa đặc biệt, khiến transaction chiếm tài nguyên database không cần thiết.
Đội chạy nhiều worker cập nhật cùng productId theo các khóa khác thứ tự, khiến deadlock xảy ra theo từng đợt tải dù mỗi câu SQL đều ngắn.
Ứng dụng dựa vào transaction rollback để thu hồi file upload đã gửi tới S3, khiến database rollback thành công nhưng file bên ngoài vẫn tồn tại khi lỗi.
Nhóm muốn ghi log thất bại vào bảng audit ngay cả khi transaction chính rollback, nhưng thao tác audit đang dùng cùng transaction nên bản ghi chẩn đoán cũng bị mất.
Một service dùng TransactionTemplate cho nhiều bước tạo đơn nhưng callback gọi một DAO mở transaction mới ngoài ý định, khiến trạng thái được commit từng phần.
Đội kết hợp TransactionTemplate và @Transactional ở cùng luồng xử lý nhưng propagation không được kiểm tra, khiến một nhánh business tạo transaction lồng khác kỳ vọng.
Ứng dụng nhận exception khi transaction commit vì constraint deferred, nhưng controller đã chuẩn bị thông báo thành công dựa trên kết quả từ các câu update trước đó.
Nhóm cần retry transaction sau deadlock nhưng đặt retry interceptor ở bên trong @Transactional advice, khiến lần thử tiếp theo dùng transaction đã lỗi.
Một service cập nhật ngân sách và đơn hàng trong một transaction nhưng gửi sự kiện từ @TransactionalEventListener trước/không đúng phase, khiến consumer thấy dữ liệu chưa được commit.
Đội áp isolation REPEATABLE_READ trong test H2 nhưng production ở PostgreSQL khác biệt về phantom và snapshot, khiến logic kiểm tra hàng tồn có kết quả khó dự đoán.
Ứng dụng dùng JdbcTemplate để đọc cùng bản ghi trong transaction rồi gọi thư viện ORM với session riêng, khiến hai đường truy cập không cùng nhìn thấy trạng thái mới.
Nhóm tối ưu truy vấn bằng cách gọi jdbcTemplate ngay trong transaction lớn nhưng một truy vấn tạo temporary table giữ session state, khiến connection pool tái sử dụng có kết quả khó kiểm soát.
Một service chạy transaction retry sau lỗi kết nối nhưng không có idempotency key của yêu cầu, khiến khách retry sau timeout có thể tạo hai đơn tương tự.
Đội cần xóa thông tin khách và audit trong hai bảng nhưng ranh giới transaction chỉ bao quanh một repository, khiến bản ghi audit còn khi dữ liệu khách đã được xóa.
Ứng dụng xử lý đồng thời hai giao dịch tạo đơn cho cùng mã khuyến mãi, nhưng kiểm tra số lượt còn lại bằng SELECT không khóa nên chấp nhận vượt hạn mức.
Nhóm triển khai database read/write splitting và route theo @Transactional(readOnly=true), nhưng một đường service gọi method readOnly nội bộ không qua proxy nên request đi vào primary ngoài dự kiến.
Một service gắn @Transactional trên controller nhưng stream dữ liệu tới HTTP response sau khi method kết thúc, khiến ResultSet chưa được tiêu thụ đã bị đóng.
Đội dùng @Transactional và custom JDBC connection callback đổi schema theo tenant, nhưng khi exception xảy ra schema context không được quản lý nhất quán cho yêu cầu kế tiếp.
Ứng dụng dùng SQLExceptionTranslator để chuẩn hóa lỗi nhưng một class DAO trả Optional.empty khi connection timeout, khiến application cache lưu kết quả không tồn tại lâu dài.
Nhóm lưu kết quả truy vấn SQL vào cache ngay trong transaction trước commit, khiến request khác nhận giá trị mới trong khi database cuối cùng rollback.
Một service dùng JdbcTemplate để đọc tài khoản có thông tin nhạy cảm nhưng SQL log hiện ghi đầy đủ tham số định danh khách và cả giá trị response khi lỗi.
Đội kiểm soát SQL injection bằng bind variables cho WHERE nhưng tên cột sort vẫn nhận trực tiếp từ request, khiến endpoint báo cáo còn bề mặt truy vấn nguy hiểm.
Ứng dụng nhận tenantId từ JWT nhưng một DAO xây SQL theo input tenantId truyền từ URL, khiến khách có thể thử truy vấn partition thuộc tenant khác.
Nhóm sử dụng database account có quyền DELETE toàn bảng cho API chỉ đọc báo cáo, khiến rủi ro từ thông tin xác thực bị lộ vượt nhu cầu nghiệp vụ.
Một service có SQL query lọc dữ liệu theo tenant nhưng một endpoint thống kê dùng JdbcTemplate khác bỏ điều kiện tenant, khiến số tổng hợp tiết lộ quy mô khách khác.
Đội truy vấn dữ liệu cá nhân qua PostgreSQL với role dùng chung nhiều team, khiến audit chỉ thấy service account thay vì xác định request/người dùng đã đọc.
Ứng dụng dùng JdbcTemplate gọi procedure thanh toán nhưng không ràng buộc quyền theo chi nhánh, khiến một nhân viên ở chi nhánh A có thể cập nhật số liệu của chi nhánh B.
Nhóm bật SQL debug logs trên production để điều tra lỗi binding nhưng log chứa số thẻ, email và secret, khiến dữ liệu nhạy cảm được lưu ngoài hệ thống nguồn.
Một service cho phép khách tải báo cáo PDF từ query SQL nhưng không giới hạn phạm vi thời gian, khiến yêu cầu nhiều năm chiếm connection và memory lâu bất thường.
Đội dùng một tài khoản database cho mọi tenant nhưng không có policy lọc bản ghi trong mỗi query, khiến lỗi lập trình nhỏ có thể trả dữ liệu ngoài vùng được phép.
Ứng dụng triển khai mTLS tới database nhưng một pool config không kiểm tra hostname, khiến kết nối có thể tin một server không đúng danh tính trong mạng nội bộ.
Nhóm quay vòng khóa mã hóa field nhạy cảm trong database nhưng RowMapper của phiên bản cũ không xử lý metadata mới, khiến một số hồ sơ không đọc được sau nâng cấp.
Một service cho phép lọc theo keyword bất kỳ nhưng không giới hạn độ dài tham số, khiến query LIKE trên bảng lớn tiêu tốn tài nguyên và ảnh hưởng người dùng khác.
Đội thêm index cho trường email nhưng truy vấn JdbcTemplate lại dùng hàm biến đổi phía cột, khiến query plan không sử dụng index như kỳ vọng.
Ứng dụng chạy SQL SELECT * trên bảng đơn hàng có BLOB đính kèm mới, khiến lượng dữ liệu truyền qua JDBC tăng mạnh và endpoint danh sách trở nên chậm.
Nhóm thực hiện truy vấn offset pagination tới hàng triệu dòng, khiến request trang sâu phải xử lý nhiều dòng bị bỏ qua và latency tăng liên tục.
Một service dùng keyset pagination theo thời gian tạo nhưng có nhiều đơn cùng timestamp, khiến khi lật trang có bản ghi bị lặp hoặc bỏ sót.
Đội triển khai query tổng hợp với JOIN nhiều bảng lớn nhưng không kiểm tra execution plan, khiến API dashboard dùng JDBC vượt timeout khi dữ liệu tăng.
Ứng dụng cần đọc báo cáo 50 triệu dòng nhưng dùng JdbcTemplate.queryForList nạp tất cả kết quả vào heap, khiến pod bị OOM trước khi xuất file.
Nhóm bật fetchSize cho streaming query nhưng driver/database có hành vi transaction khác, khiến những cải tiến đọc theo luồng không có hiệu quả trong production.
Một service có câu SQL dùng CTE phức tạp và RowMapper nhẹ, nhưng metrics chỉ đo thời gian chuyển DTO nên team không nhận ra phần lớn latency nằm ở database.
Đội cache kết quả JdbcTemplate cho giá sản phẩm mà không có sự kiện invalidation khi batch cập nhật, khiến người dùng nhìn thấy giá cũ sau chiến dịch.
Ứng dụng đọc dữ liệu từ replica nhưng report yêu cầu đối soát dữ liệu ngay sau giao dịch, khiến replication lag làm tổng doanh số tạm lệch.
Nhóm vận hành chỉ đo HTTP latency mà không đo connection acquisition/query execution, khiến sau release không phân biệt được pool starvation và câu SQL chậm.
Một service sử dụng SQL query chứa ORDER BY không ổn định cho trang kết quả nhiều bản ghi có cùng điểm, khiến trang sau trùng dữ liệu khi có insert mới.
Đội viết custom RowMapper tạo nhiều object trung gian không cần thiết cho mỗi hàng, khiến GC tăng mạnh khi hệ thống xuất báo cáo lớn.
Ứng dụng sử dụng JdbcClient cho nhiều truy vấn tổng hợp nhỏ trong vòng lặp nhưng mỗi lần đều round-trip sang database, khiến request có kiểu N+1 calls dù không dùng ORM.
Nhóm dùng PreparedStatement cache của JDBC driver nhưng tạo SQL có số lượng placeholders thay đổi theo từng yêu cầu, khiến hiệu quả cache thấp khi traffic tăng.
Một service triển khai bulk read với query IN chứa hàng chục nghìn IDs, khiến database gặp giới hạn số bind parameters và không ổn định dưới tải.
Đội có truy vấn lọc theo status enum nhưng một cột được lưu bằng VARCHAR không nhất quán chữ hoa, khiến query dùng index không tìm đủ bản ghi cũ.
Ứng dụng chạy một transaction báo cáo dài với isolation mạnh, khiến các job dọn dữ liệu cũ bị chặn bởi snapshot đang mở lâu.
Nhóm theo dõi tối ưu SQL bằng slow-query log nhưng không gắn requestId hoặc tenantId đã ẩn danh, khiến khó gắn câu query chậm với workflow gây tải.
Một service tối ưu database pool size để giảm p99 nhưng tải đỉnh còn đến từ batch đêm cùng nguồn, khiến kết quả đo trong giờ thấp điểm không dự báo đúng sự cố.
Đội thêm @Transactional lên mọi phương thức đọc để đảm bảo nhất quán nhưng không đánh giá thời gian giữ connection khi xử lý response, khiến pool cạn vào giờ cao điểm.
Ứng dụng muốn chuyển dữ liệu sang database mới nhưng hardcoded dialect SQL trong JdbcTemplate khiến những truy vấn LIMIT/OFFSET và generated key không tương thích.
Nhóm nâng JDBC driver và Spring Framework đồng thời nhưng integration tests chỉ mock JdbcTemplate, khiến lỗi mã hóa timestamp và transaction thật không được phát hiện.
Một service dùng @JdbcTest cho repository nhưng Test database tự động thay thế DataSource production bằng H2, khiến cú pháp PostgreSQL đặc thù không được kiểm chứng.
Đội tạo RowMapper test với dữ liệu đầy đủ nhưng production có cột optional null, khiến mapper chỉ lỗi khi khách chưa cung cấp địa chỉ.
Ứng dụng sử dụng Testcontainers PostgreSQL cho truy vấn nhưng chỉ kiểm tra đọc một bản ghi, khiến batchUpdate partial failures và rollback chưa được kiểm tra.
Nhóm chạy hai test suites song song trên cùng database schema và mỗi suite xóa bảng khi kết thúc, khiến kết quả CI phụ thuộc thứ tự chạy.
Một service test JdbcTemplate.batchUpdate với mười dòng hợp lệ nhưng không thử dòng trùng khóa giữa batch, khiến cách xử lý lỗi từng hàng bị bỏ sót trước release.
Đội kiểm tra SqlParameterSource với dữ liệu ASCII nhưng không dùng email có dấu cộng hoặc tên tiếng Việt, khiến lỗi binding và encoding chỉ xuất hiện trên hồ sơ thật.
Ứng dụng test transaction bằng method không qua Spring proxy, khiến bộ test tưởng @Transactional rollback tốt dù runtime đường gọi thật không mở transaction.
Nhóm mô phỏng database deadlock bằng mock ném exception nhưng không thử giao dịch thật với hai connections, khiến retry và rollback logic chưa được xác nhận.
Một service kiểm thử API tạo đơn với một request tuần tự nhưng chưa chạy hai cập nhật đồng thời trên cùng productId, khiến lỗi mất cập nhật tồn kho chỉ xuất hiện giờ cao điểm.
Đội kiểm thử connection leak bằng cách gọi JdbcTemplate vài lần rồi kết thúc, khiến nhánh ResultSet streaming bị bỏ dở không được thử trong tải kéo dài.
Ứng dụng cần chứng minh DAO không để lộ SQL injection nhưng test chỉ truyền mã sản phẩm hợp lệ, khiến chuỗi chứa trích dẫn hoặc điều kiện động chưa được xác minh.
Nhóm viết unit test cho SQLExceptionTranslator với một mã lỗi vendor nhưng không thử mã timeout/deadlock thực trong database production, khiến chính sách retry sai trong sự cố.
Một service dùng SimpleJdbcCall cho procedure có nhiều OUT parameters nhưng Testcontainers chưa có migration tạo procedure, khiến bài test bị bỏ qua và production gặp lỗi.
Đội kiểm tra stored procedure trên PostgreSQL local nhưng không chạy tích hợp với Oracle thật, khiến cách xử lý REF CURSOR và metadata tham số chưa được đánh giá.
Ứng dụng test pool với một pod duy nhất nhưng triển khai production 30 pod, khiến hạn mức max_connections bị vượt khi rolling update làm hai bản cùng tồn tại.
Nhóm benchmark database bằng truy vấn chỉ lấy một dòng, khiến vấn đề memory và fetch size khi streaming vài triệu dòng không được phát hiện.
Một service kiểm thử lỗi kết nối bằng cách dừng database trước request, nhưng không mô phỏng kết nối chết giữa một transaction nhiều bước khiến trạng thái retry khó suy ra.
Đội có integration test database rollback sau exception RuntimeException nhưng không kiểm tra checked exception, khiến quy tắc rollback với ngoại lệ nghiệp vụ chưa được chứng minh.
Ứng dụng dùng @JdbcTest và rollback test transaction mặc định nhưng production chạy DAO ngoài transaction, khiến case tạo nhiều bản ghi có trạng thái khác môi trường thử nghiệm.
Nhóm kiểm thử đọc sau ghi trên primary nhưng không thử replica delay, khiến API triển khai đọc từ replica trả dữ liệu cũ ngay sau khi tạo đơn.
Một service chỉ kiểm tra số hàng affected là dương trong test cập nhật, khiến SQL thiếu WHERE tenantId vẫn PASS khi fixture chỉ có một doanh nghiệp.
Đội dùng nhiều transaction managers nhưng test chỉ khởi tạo một DataSource, khiến lỗi rollback không đồng bộ giữa hai database không bị phát hiện trước production.
Ứng dụng muốn theo dõi connection leak nhưng CI không đo active/idle pool metrics sau mỗi job, khiến rò rỉ kết nối tích lũy qua nhiều request không có cảnh báo.
Nhóm chạy batch import test với dữ liệu cố định và không thử retry sau network timeout, khiến lệnh nhập đã commit nhưng response mất vẫn có thể được lặp lại khi chạy thật.
Một service chuyển SimpleJdbcCall từ metadata lookup sang khai báo tham số nhưng pipeline không thử thay đổi schema procedure, khiến lỗi chỉ xuất hiện sau khi DBA deploy.
Đội kiểm tra SQL trả đúng dữ liệu nhưng không đo query plan và index ở dataset lớn, khiến endpoint findByEmail vẫn timeout khi số khách tăng lên hàng triệu.
Ứng dụng có dao đọc dữ liệu cá nhân bằng JdbcClient nhưng test chỉ xác nhận số hàng, không kiểm chứng scope quyền tenant nên có nguy cơ lộ dữ liệu qua bộ lọc bị thiếu.
Nhóm cần đo độ trễ giữa SQL execute và mapping DTO nhưng tracing chỉ tạo span HTTP chung, khiến một regression của RowMapper không thể phân biệt với network database.
Một service cần audit cập nhật bút toán nhưng log chỉ lưu HTTP status mà không có transaction ID kết nối database, khiến khó đối soát khi một request retry sau timeout.
Đội muốn xác minh quy trình failover database, nhưng test chỉ khởi động lại Spring Boot chứ không mô phỏng primary đổi địa chỉ trong lúc pool đang có transaction.
Ứng dụng áp dụng masking log ở controller nhưng SQL instrumentation ghi bind parameters nguyên văn, khiến thông tin cá nhân vẫn vào kho quan sát tập trung.
Nhóm triển khai read/write split trong service dùng JdbcTemplate nhưng health dashboard chỉ kiểm tra primary, khiến replica bị lỗi mà ứng dụng vẫn báo cơ sở dữ liệu khỏe.
Một công ty yêu cầu chứng minh toàn bộ thay đổi tồn kho đã nằm trong một transaction và không có retry trùng, nhưng log không chứa correlation ID chung giữa HTTP, JDBC và batch events.
