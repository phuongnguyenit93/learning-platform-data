Một ứng dụng Jakarta EE được đóng gói thành WAR nhưng nhóm triển khai lên WildFly với context root trùng ứng dụng cũ; deployment báo thành công nhưng người dùng truy cập URL quen thuộc lại nhận nội dung của phiên bản trước.
Ứng dụng được biên dịch bằng JDK mới hơn runtime Java của Payara; deployment thất bại với UnsupportedClassVersionError dù WAR hợp lệ và chạy được trên máy phát triển.
Một WAR dùng Jakarta Servlet API nhưng vẫn đóng gói thư viện javax.servlet cũ; classloader nạp hai thế hệ API và ứng dụng gặp lỗi cast hoặc NoSuchMethodError khi khởi tạo filter.
Một EAR có hai module cùng đóng gói phiên bản khác nhau của thư viện logging; classloader isolation làm log từ EJB module và web module dùng cấu hình, binding hoặc provider khác nhau.
Ứng dụng dùng ServiceLoader để tìm JDBC driver nhưng thread context class loader tại thời điểm gọi trỏ tới module của server; provider nằm trong WAR không được phát hiện dù JAR đã có trong deployment.
Một module WildFly khai báo dependency tới module hệ thống nhưng thiếu export hoặc services import; lớp xuất hiện khi chạy local nhưng NoClassDefFoundError chỉ xảy ra sau khi deploy.
Ứng dụng được redeploy nhiều lần và tạo thread nền cùng ThreadLocal giữ tham chiếu tới class của deployment cũ; metaspace tăng dần và log cảnh báo classloader leak xuất hiện.
Deployment scanner nhìn thấy WAR trong lúc file vẫn đang được copy; server cố triển khai file chưa hoàn chỉnh và báo archive corrupted trước khi lần copy kết thúc.
Một nhóm triển khai ứng dụng bằng management CLI trên một node nhưng quên cập nhật node còn lại trong domain; load balancer phân phối request tới cả phiên bản mới và cũ.
Ứng dụng có deployment descriptor khai báo phiên bản Jakarta EE không được server hỗ trợ; parser từ chối cấu hình dù code chỉ dùng các API cơ bản.
CDI bean không được phát hiện vì archive thiếu bean-defining annotation và beans.xml phù hợp với chế độ discovery đang dùng; injection point báo unsatisfied dependency khi startup.
Một EJB singleton gọi method của request-scoped CDI bean từ scheduled task không có active request context; client proxy không tìm được context và ném ContextNotActiveException.
EJB singleton thực hiện tác vụ bảo trì lâu với container-managed concurrency mặc định; các lời gọi khác chờ lock và request pool cạn dù CPU server còn thấp.
Một EJB stateless bean giữ trạng thái người dùng trong field instance giữa các invocation; container tái sử dụng bean cho nhiều request và dữ liệu của người dùng bị trộn.
Ứng dụng tra cứu datasource qua java:comp/env/jdbc/Orders nhưng resource mapping trên server chỉ bind tên jdbc/Orders; JNDI lookup thất bại dù datasource đã được tạo và test connection thành công.
WildFly có JDBC driver được cài dưới dạng module nhưng module.xml tham chiếu sai tên artifact; datasource không khởi tạo và server báo không tìm thấy driver class.
Datasource pool chạm max-pool-size trong giờ cao điểm; request chờ lấy connection và cuối cùng timeout dù database còn khả năng xử lý thêm truy vấn.
Ứng dụng mở JDBC connection trong nhánh exception nhưng không đóng trong finally hoặc try-with-resources; active connections tăng dần cho tới khi pool cạn.
Datasource dùng validation query không còn hợp lệ sau khi đổi database; pool loại bỏ connection khỏe mạnh và tạo mới liên tục, làm latency tăng cùng số lần đăng nhập database.
DB password được rotate nhưng secret trong cấu hình application server chưa cập nhật đồng bộ; các connection mới nhận authentication failure trong khi connection cũ còn hoạt động tạm thời.
JPA persistence unit được cấu hình non-JTA datasource trong khi EJB method mong container-managed transaction; thao tác cập nhật không tham gia giao dịch chung như thiết kế.
Một entity có quan hệ LAZY được truy cập sau khi transaction và persistence context đã đóng; request gặp LazyInitializationException dù truy vấn ban đầu thành công.
Một EJB method dùng transaction attribute REQUIRED nhưng gọi dịch vụ bên ngoài mất 40 giây; transaction giữ connection và lock lâu hơn timeout, làm các request khác bị chặn.
Runtime đánh dấu transaction rollback-only sau một system exception; ứng dụng bắt exception và trả HTTP 200 nhưng commit cuối cùng vẫn thất bại với rollback exception.
Ứng dụng gọi REQUIRES_NEW trong vòng lặp hàng nghìn bản ghi; mỗi lần tạo transaction riêng và commit liên tục khiến database log flush cùng connection pool tăng tải.
JTA transaction bao gồm database và JMS nhưng XA recovery log được đặt trên thư mục tạm; sau restart, server không tìm được transaction log để hoàn tất hoặc rollback giao dịch dang dở.
Một resource manager XA bị mất kết nối giữa prepare và commit; giao dịch chuyển sang trạng thái in-doubt và dữ liệu trong database không khớp message đã gửi.
EJB Message-Driven Bean nhận message và cập nhật database; transaction bị rollback sau lỗi nhưng cấu hình redelivery không giới hạn khiến poison message lặp lại liên tục.
MDB được cấu hình concurrency quá cao so với kích thước datasource pool; nhiều consumer cùng nhận message nhưng chờ connection, làm queue lag tăng và throughput giảm.
JMS message bị gửi vào dead-letter queue sau nhiều lần redelivery; dashboard chỉ theo dõi queue chính nên nhóm vận hành không phát hiện message nghiệp vụ đang bị cách ly.
JMS producer gửi message trước khi database transaction commit; consumer xử lý event cho một đơn hàng sau đó bị rollback và không tìm thấy bản ghi đơn hàng tương ứng.
Ứng dụng dùng asynchronous method hoặc executor tự tạo bên trong transaction; transaction context không tự truyền sang thread mới và thao tác database chạy ngoài giao dịch dự kiến.
Ứng dụng yêu cầu role OrdersAdmin nhưng mapping trong deployment descriptor không khớp group name của security realm; người dùng đã xác thực vẫn nhận 403 từ EJB hoặc servlet.
WildFly Elytron xác thực thành công qua LDAP nhưng role decoder không chuyển group membership thành application roles; đăng nhập được nhưng mọi chức năng quản trị bị từ chối.
Payara dùng JDBC realm và truy vấn role theo cột không còn tồn tại sau migration schema; login thất bại hàng loạt dù thông tin tài khoản vẫn đúng.
Ứng dụng bật HTTPS nhưng certificate chain trên application server thiếu intermediate CA; một số client tin root CA đầy đủ kết nối được còn client khác báo lỗi xác thực chứng chỉ.
Admin console và management API của application server được bind ra interface công khai; firewall chỉ bảo vệ cổng ứng dụng và vô tình để lộ mặt phẳng quản trị.
Ứng dụng lưu session cookie nhưng thiếu Secure hoặc HttpOnly theo yêu cầu triển khai; reverse proxy kết thúc TLS và cookie có thể bị gửi qua kết nối không mã hóa hoặc đọc bởi script.
Cluster WildFly dùng JGroups discovery qua multicast nhưng network policy chặn multicast giữa các node; mỗi node khởi tạo view riêng và session replication không hoạt động.
Payara cluster có node tham gia group nhưng network latency cao; replication traffic trễ và người dùng chuyển node nhận session state cũ sau khi vừa cập nhật giỏ hàng.
Session replication lưu object trong session không serializable; request hoạt động khi sticky session còn hiệu lực nhưng failover sang node khác gây lỗi serialization và mất phiên.
Rolling deployment thay đổi class của object session trong khi node cũ và mới cùng phục vụ traffic; session serialized từ phiên bản cũ không deserialize được ở node mới.
Load balancer bật sticky session nhưng một node bị lỗi; người dùng bị ghim vào node đã chết và liên tục nhận 502 thay vì được chuyển sang node khỏe.
Một EJB singleton hoặc scheduled timer chạy trên từng node cluster mà không có cơ chế single-owner; tác vụ gửi hóa đơn được thực thi hai lần khi cluster có ba node.
Cluster cache dùng replication đồng bộ cho mọi thay đổi session; lượng write tăng làm request latency tăng và traffic east-west giữa các node bão hòa.
Mạng giữa các node cluster bị phân vùng; hai nhóm node cùng nhận mình là thành viên hợp lệ và thực hiện tác vụ leader-only, tạo split-brain hoặc xử lý trùng.
Thread pool HTTP đạt max threads vì request đồng bộ chờ API đối tác; queue tăng, response timeout xuất hiện dù CPU utilization không cao.
Datasource pool chỉ có 20 connection trong khi HTTP worker pool cho phép 200 request đồng thời; phần lớn worker chờ connection và server báo stuck threads.
Thread dump cho thấy nhiều worker ở trạng thái BLOCKED trên cùng monitor trong singleton bean; số request pending tăng nhưng CPU thấp vì các thread đang chờ lock.
Ứng dụng tạo thread riêng trong mỗi request thay vì dùng managed executor; số thread vượt giới hạn OS và container mất khả năng tạo thread mới.
Ứng dụng dùng ManagedExecutorService nhưng tác vụ không kết thúc và giữ context lâu; executor queue đầy, tác vụ mới bị từ chối dù request HTTP đã trả về.
Full GC xảy ra liên tục sau khi triển khai phiên bản mới; heap occupancy sau GC tăng đều và thời gian pause làm p99 latency vượt SLO.
Metaspace tăng sau mỗi lần hot redeploy vì classloader cũ còn được giữ bởi thread, JDBC driver hoặc static cache; heap dump không cho thấy object nghiệp vụ tăng tương ứng.
Server khởi động chậm do hàng loạt deployment đồng thời thực hiện migration schema và warm up cache; readiness probe timeout khiến Kubernetes restart pod trước khi startup hoàn tất.
Liveness probe chỉ kiểm tra process Java còn sống; datasource đã mất kết nối và JMS broker không truy cập được nhưng pod vẫn được coi là khỏe mạnh.
Ứng dụng trả HTTP 200 từ health endpoint dù một số deployment chưa hoàn tất migration; traffic được gửi vào node chưa sẵn sàng và người dùng gặp lỗi schema.
Access log của application server không có trace ID trong khi application log có MDC correlation ID; nhóm điều tra không nối được request chậm với stack trace tương ứng.
JMX metrics của thread pool và datasource không được expose sau khi thay đổi security policy; dashboard mất số liệu và đội vận hành nhầm với việc pool không có hoạt động.
Log server ghi OutOfMemoryError nhưng process bị kill trước khi heap dump hoàn tất; cấu hình heap dump path không có đủ dung lượng hoặc quyền ghi.
Một ứng dụng chạy tốt trên WildFly nhưng phụ thuộc API nội bộ của server; khi chuyển sang Payara, deployment thất bại vì module hoặc proprietary class không tồn tại.
Ứng dụng được nâng từ Java EE javax.* sang Jakarta EE jakarta.* nhưng một thư viện cũ vẫn dùng javax APIs; classloading thành công một phần nhưng injection hoặc servlet initialization thất bại.
Domain configuration trên một node được sửa trực tiếp bằng file thay vì management controller; khi controller đồng bộ lại, thay đổi bị ghi đè và node quay về cấu hình cũ.
Graceful shutdown được cấu hình ngắn hơn thời gian xử lý giao dịch đang chạy; node ngừng nhận request nhưng bị kill trước khi hoàn tất transaction và gửi response.
Server restart trong lúc đang có JMS deliveries và JTA transactions; recovery hoàn tất không đầy đủ do object store hoặc transaction log không bền vững, dẫn tới message duplicate hoặc giao dịch in-doubt.
Một Jakarta Connectors resource adapter được triển khai nhưng activation properties của outbound connection factory thiếu thông tin endpoint; adapter không tạo được managed connection tới ERP dù ứng dụng lookup JNDI thành công.
