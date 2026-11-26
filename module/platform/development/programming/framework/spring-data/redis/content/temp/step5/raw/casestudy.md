Một dịch vụ Spring Boot dùng Spring Data Redis để lưu giỏ hàng, nhưng RedisConnectionFactory vẫn trỏ đến Redis trên laptop khiến bản triển khai staging truy cập nhầm dữ liệu của môi trường phát triển.
Nhóm vận hành chuyển Redis sang endpoint TLS, nhưng Lettuce client trong ứng dụng chưa tin chứng chỉ máy chủ nên toàn bộ thao tác RedisTemplate thất bại sau khi khởi động.
Ứng dụng dùng mật khẩu Redis từ secret manager nhưng ConnectionFactory chỉ nhận giá trị tại startup, khiến một số pod không thể tạo kết nối mới sau khi xoay credential.
Đội phát triển cấu hình Redis ACL user chỉ đọc cho tác vụ cập nhật giỏ hàng, khiến lệnh ghi thất bại trong production dù truy vấn đọc vẫn hoạt động.
Một service dùng Lettuce kết nối Redis qua DNS riêng nhưng pod tại vùng dự phòng không resolve được hostname, khiến failover ứng dụng không khôi phục được phiên giao dịch.
Nhóm chạy RedisTemplate đồng bộ trên luồng xử lý WebFlux, khiến các yêu cầu API bị chậm hàng loạt khi thời gian phản hồi của Redis tăng trong giờ cao điểm.
Một ứng dụng dùng ReactiveRedisTemplate nhưng chuỗi reactive không được subscribe ở nhánh xử lý nền, khiến trạng thái phiên không được ghi trong khi log vẫn báo tạo yêu cầu thành công.
Đội cấu hình connection timeout dài hơn ngân sách HTTP request, khiến thread tiếp tục chờ Redis sau khi gateway đã trả timeout cho người dùng.
Một Spring Boot service chia sẻ một pool Redis connections giữa request online và batch cập nhật lớn, khiến batch chiếm tài nguyên và những thao tác kiểm tra phiên bị xếp hàng.
Nhóm chuyển ứng dụng sang Redis 7 có ACL riêng nhưng một tính năng RedisTemplate vẫn yêu cầu lệnh không nằm trong quyền được cấp, khiến lỗi chỉ phát sinh khi khách dùng chức năng ít gặp.
Một dịch vụ dùng Jedis với pool quá nhỏ cho số worker đồng thời, khiến các request chờ borrow connection lâu dù CPU của Redis vẫn thấp.
Đội thay Lettuce client configuration để bật reconnect nhưng không kiểm tra trạng thái kết nối sau network partition, khiến một phần request tiếp tục lỗi trong lúc Redis đã hồi phục.
Ứng dụng đăng nhập dùng Redis làm kho session nhưng health endpoint chỉ kiểm tra HTTP, khiến pod vẫn READY khi không thể ghi session vào Redis.
Nhóm cấu hình Redis database index khác nhau cho các profile, nhưng khi chuyển từ standalone sang Redis Cluster ứng dụng vẫn kỳ vọng dùng nhiều logical databases ngoài database mặc định.
Một service chạy Redis trong container với port được ánh xạ qua proxy, nhưng địa chỉ Redis mà client nhận sau chuyển topology không thể truy cập từ mạng Kubernetes.
Đội triển khai Redis có giới hạn maxclients nhưng mỗi pod Spring Boot tạo nhiều RedisConnectionFactory độc lập, khiến autoscaling làm lệnh kết nối mới bị từ chối.
Ứng dụng dùng RedisTemplate cho dữ liệu quan trọng nhưng chỉ retry vô điều kiện mọi command khi timeout, khiến một lệnh tăng bộ đếm có thể được áp dụng hai lần.
Nhóm sử dụng Redis trên máy khác vùng địa lý với thời gian round-trip cao, khiến một chuỗi mười lệnh RedisTemplate liên tiếp làm API checkout vượt SLA.
Một service có nhiều profile Spring Boot với serializer và connection factory khác nhau, nhưng một bean RedisTemplate dùng nhầm kết nối staging khi chạy trong production.
Đội triển khai Redis qua TLS proxy nhưng tên chứng chỉ của endpoint không trùng hostname mà client sử dụng, khiến chỉ pod kết nối bằng alias nội bộ bị lỗi xác thực.
Một ứng dụng xử lý tài khoản đa tenant dùng key Redis chỉ theo userId, khiến hai tenant có cùng mã người dùng ghi đè giỏ hàng của nhau.
Nhóm lưu token đăng nhập với key chỉ chứa email, nhưng email của người dùng có thể thay đổi nên bản ghi session cũ không được thu hồi theo định danh mới.
Một service lưu trạng thái đơn dưới key có tên chung status mà không có namespace ứng dụng, khiến dữ liệu của nhiều microservice cùng Redis bị ghi đè.
Đội tạo key Redis bằng cách ghép chuỗi chứa dấu hai chấm và ký tự đặc biệt từ mã sản phẩm, khiến thao tác thống kê theo prefix không phân biệt đúng các thành phần định danh.
Một hệ thống dùng Redis để khóa theo orderId nhưng giá trị ID từ hai thị trường trùng nhau, khiến đơn ở thị trường này cản trở xử lý của thị trường khác.
Nhóm thay quy ước đặt key sau một bản phát hành nhưng không có cơ chế nhận biết dữ liệu theo prefix cũ, khiến bộ nhớ Redis giữ hàng triệu key không còn được truy cập.
Ứng dụng tìm mọi key giỏ hàng bằng lệnh quét toàn bộ keyspace trong mỗi request quản trị, khiến Redis phản hồi chậm khi số tài khoản tăng mạnh.
Đội xây chức năng xóa cache theo prefix bằng thao tác trên hàng triệu key cùng lúc, khiến request khác bị ảnh hưởng trong giờ cao điểm.
Một service dùng Redis hash để lưu hồ sơ khách nhưng field names được lấy trực tiếp từ dữ liệu đầu vào, khiến một khách tạo quá nhiều field làm bản ghi nặng bất thường.
Nhóm lưu toàn bộ lịch sử nhấp chuột của một người vào cùng một list Redis không giới hạn, khiến những tài khoản có lưu lượng lớn tiêu tốn bộ nhớ vượt dự toán.
Ứng dụng chọn key theo thời gian đến mili giây cho mỗi lần đọc sản phẩm, khiến cache gần như không bao giờ được tái sử dụng dù dữ liệu sản phẩm ít thay đổi.
Đội dùng key Redis cho dữ liệu tạm nhưng không thống nhất đơn vị TTL giữa giây và mili giây, khiến một số khóa hết hạn ngay sau khi tạo.
Một service tạo các key tạm theo requestId nhưng không gắn expiration, khiến bộ nhớ Redis tăng liên tục sau nhiều tháng triển khai.
Nhóm vận hành thấy nhiều key có prefix của phiên bản cũ nhưng không có metadata thuộc về job nào, khiến việc dọn dữ liệu khó tránh xóa nhầm khóa đang sử dụng.
Ứng dụng chia sẻ Redis giữa cache và hàng đợi công việc nhưng không tách prefix cùng chính sách tài nguyên, khiến đợt tăng cache tác động đến lệnh nghiệp vụ.
Đội dùng cùng Redis key cho khóa phân tán và bộ đếm thống kê ở hai service, khiến một service gặp lỗi WRONGTYPE sau khi service khác đổi cấu trúc dữ liệu.
Một backend đọc các key theo từng tài khoản nhưng chọn tên key dựa trên chuỗi URL chưa chuẩn hóa, khiến hai URL tương đương tạo bản ghi cache độc lập.
Nhóm dùng Redis hash lưu giá trị số tiền dưới dạng chuỗi với đơn vị không đồng nhất, khiến lệnh tăng số học không áp dụng được cho một phần dữ liệu lịch sử.
Ứng dụng mở tính năng tìm kiếm theo một pattern key rất rộng qua SCAN trong mỗi request, khiến cùng một báo cáo lặp nhiều lượt quét và tiêu thụ tài nguyên cụm.
Đội triển khai tenant mới có hàng chục triệu key nhưng báo cáo vận hành chỉ đếm tổng keyspace, khiến không phân biệt được tenant nào tạo áp lực bộ nhớ.
Một ứng dụng RedisTemplate sử dụng JDK serialization cho giá trị ở bản đầu, nhưng bản cập nhật đổi sang JSON khiến các cache entries cũ không được deserializer mới đọc được.
Nhóm dùng StringRedisTemplate để lưu JSON theo chuỗi nhưng một service khác dùng RedisTemplate với key serializer nhị phân, khiến hai ứng dụng không nhìn thấy cùng key theo tên hiển thị.
Một service chuyển entity Java thành JSON nhưng serializer không lưu đủ type information cho field đa hình, khiến dữ liệu trạng thái được đọc lại thành kiểu không phù hợp.
Đội phát triển sử dụng Jackson polymorphic typing không giới hạn kiểu khi đọc dữ liệu Redis không tin cậy, làm tăng rủi ro deserialization từ nội dung bị sửa trái phép.
Ứng dụng có Java record mới với một thuộc tính bắt buộc nhưng cache Redis còn JSON của bản cũ, khiến lỗi deserialization chỉ xuất hiện khi đọc khóa ít dùng.
Nhóm thay tên field trong DTO được lưu Redis nhưng không quản lý schema version, khiến các pod rolling deployment đọc dữ liệu của nhau không tương thích.
Một dịch vụ lưu BigDecimal trong Redis theo JSON với precision khác giữa hai thư viện, khiến chi phí tính toán sau khi đọc cache lệch so với database nguồn.
Đội chuyển thuộc tính thời gian từ epoch milliseconds sang ISO-8601 nhưng không phân biệt phiên bản serializer, khiến một số session hết hạn sai thời điểm.
Ứng dụng dùng hashValueSerializer khác với valueSerializer nhưng team kiểm tra dữ liệu bằng GET thông thường, khiến họ kết luận nhầm rằng Redis mất bản ghi.
Nhóm tạo RedisTemplate cho cả các object nghiệp vụ và token truy cập nhưng dùng chung serializer, khiến một nhánh ghi token thành JSON có dấu nháy ngoài dự kiến.
Một service sử dụng Java serialization cho danh sách đối tượng chứa serialVersionUID thay đổi, khiến các key được ghi ở bản phát hành trước không đọc được sau deploy.
Đội import dữ liệu Redis từ môi trường khác nhưng các key có prefix và kiểu serialization khác, khiến ứng dụng mới không nhận ra dữ liệu đã tồn tại.
Ứng dụng lưu object vào Redis hash bằng HashMapper nhưng phần converter bỏ qua các thuộc tính lồng sâu, khiến dữ liệu đọc lại mất một phần thông tin.
Nhóm dùng GenericJackson2JsonRedisSerializer cho nhiều loại dữ liệu nhưng một class được đổi package, khiến metadata type trong cache cũ tham chiếu kiểu không còn tồn tại.
Một hệ thống lưu chuỗi tiếng Việt vào Redis bằng nhiều charset giữa các producer, khiến tên khách đọc ra bị lỗi dấu khi qua một service mới.
Đội lưu binary thumbnail vào Redis như chuỗi UTF-8 rồi ghi lại, khiến checksum ảnh bị thay đổi trong khi thao tác set vẫn thành công.
Ứng dụng sử dụng key serializer mới nhưng không có kế hoạch cache invalidation cho key cũ, khiến memory usage tăng dù tỷ lệ hit của cache giảm mạnh.
Nhóm ghi dữ liệu có thuộc tính nhạy cảm bằng JSON serializer rồi bật Redis MONITOR để gỡ lỗi, khiến token và thông tin khách bị lộ trong công cụ vận hành.
Một service đang chạy hai phiên bản Java trong rolling deployment, nhưng một bản sử dụng serializer JDK còn bản kia JSON và liên tục ghi đè cùng cache key.
Đội xây contract test cho RedisTemplate chỉ xác nhận save/read bằng cùng serializer, khiến lỗi khi service khác viết cùng schema không được phát hiện.
Một ứng dụng dùng RedisTemplate.opsForValue để lưu trạng thái thiết bị nhưng reader khác kỳ vọng hash, khiến thao tác HGET trên key đó trả WRONGTYPE.
Nhóm quản lý số lần thử đăng nhập bằng lệnh tăng bộ đếm Redis, nhưng khi lần ghi đầu chưa đặt TTL thì những tài khoản cũ bị giới hạn lâu hơn chính sách.
Một service gọi GET rồi SET để tăng giá trị giới hạn tải, khiến hai request đồng thời cùng đọc số cũ và ghi lại một kết quả bị mất lượt tăng.
Đội dùng Redis Hash lưu thông tin sản phẩm nhưng thao tác update thay toàn bộ hash khi chỉ muốn sửa giá, khiến các thuộc tính do tiến trình khác thêm vào bị xóa.
Ứng dụng lưu các tác vụ đang chờ trong Redis List, nhưng hai worker thao tác đọc/xóa không nguyên tử làm một tác vụ bị lấy bởi cả hai worker.
Nhóm triển khai queue bằng List Redis nhưng worker mất kết nối sau khi loại phần tử khỏi list, khiến tác vụ biến mất dù chưa được hoàn tất.
Một service dùng blocking pop trên Redis List với timeout lớn nhưng thread pool dùng chung HTTP request, khiến các endpoint khác bị nghẽn khi queue rỗng.
Đội dùng Redis Set để theo dõi danh sách khách đã tham gia khuyến mãi, nhưng dữ liệu cần giữ thứ tự tham gia và API hiện không có thông tin thứ tự đó.
Ứng dụng sử dụng Set để quản lý user IDs nhưng một số ID được ghi dưới serializer khác nên cùng người xuất hiện như hai phần tử khác nhau.
Nhóm dùng Redis Sorted Set cho bảng xếp hạng theo điểm nhưng một khách có điểm bằng khách khác, khiến thứ tự hiển thị không theo quy tắc phụ mà sản phẩm yêu cầu.
Một API trả top 100 tài khoản từ Sorted Set nhưng nhiều request cùng cập nhật score, khiến bảng xếp hạng ở hai lượt đọc gần nhau có vị trí khác.
Đội dùng Sorted Set theo timestamp sự kiện, nhưng nhiều message trùng timestamp làm cách xử lý thứ tự cần một yếu tố định danh phụ chưa có.
Ứng dụng dùng Redis Geo để tìm cửa hàng gần khách, nhưng dữ liệu nhập hoán đổi kinh độ và vĩ độ khiến danh sách cửa hàng được đặt ở vị trí sai.
Nhóm lưu vị trí tài xế vào Redis Geo nhưng không dọn các tài xế đã offline, khiến API vẫn gợi ý người đã kết thúc ca làm.
Một service dùng HyperLogLog để ước lượng khách truy cập duy nhất nhưng dashboard tài chính lại sử dụng kết quả như số lượng chính xác để tính thưởng.
Đội dùng bitmap Redis để lưu trạng thái điểm danh theo ngày nhưng không có ánh xạ userId sang bit offset ổn định, khiến báo cáo điểm danh nhầm nhân viên.
Ứng dụng dùng bitfield cho bộ đếm năng lực nhỏ nhưng khi giá trị tăng vượt phạm vi lưu trữ, báo cáo hiển thị số bất thường trong giờ cao điểm.
Nhóm lưu một JSON lớn bằng key duy nhất và mỗi thay đổi nhỏ đều ghi lại toàn bộ giá trị, khiến băng thông và latency tăng khi dữ liệu hồ sơ phát triển.
Một service dùng Redis Hash để cập nhật hàng trăm field từ các request đồng thời, nhưng không có version của hồ sơ nên một số field bị sửa bởi dữ liệu cũ.
Đội muốn kiểm tra thành viên của hàng nghìn Redis Sets cho một báo cáo, nhưng ứng dụng gọi từng lệnh tuần tự từ mạng xa nên thời gian phản hồi kéo dài.
Ứng dụng sử dụng Sorted Set để trì hoãn tác vụ theo timestamp nhưng nhiều worker quét phần tử đến hạn rồi xóa sau, khiến cùng tác vụ được chạy nhiều lần.
Nhóm muốn lưu lịch sử chỉnh sửa theo event append-only nhưng chọn Hash và ghi đè field trạng thái, khiến dữ liệu thay đổi cũ không còn để điều tra.
Một dịch vụ cache ảnh nhị phân trong Redis nhưng một loại ảnh lớn bất thường làm chiếm quá nhiều memory và kích hoạt eviction cho các key quan trọng khác.
Đội sử dụng Redis Strings để lưu đối tượng session nhưng một số giá trị vượt kích thước thiết kế, khiến network và serializer chiếm nhiều thời gian khi đọc session.
Ứng dụng dùng pipeline để cập nhật nhiều Sorted Sets liên quan nhưng một lệnh thất bại giữa pipeline, khiến bảng xếp hạng theo vùng và toàn quốc khác nhau.
Một dự án Spring Data Redis ánh xạ user profile bằng @RedisHash nhưng keyspace đặt theo tên class bị đổi sau refactor, khiến repository không tìm ra hồ sơ phiên bản cũ.
Nhóm gắn @Id cho một trường không ổn định trong entity Redis repository, khiến thay đổi mã khách tạo hai object với hai key khác nhau.
Ứng dụng dùng @RedisHash với TTL ngắn cho session nhưng một thao tác save mới không tuân theo vòng đời dự kiến, khiến session được giữ lâu hơn thời hạn công bố.
Đội khai báo @TimeToLive trong entity dưới đơn vị không đồng nhất với dữ liệu nhập, khiến nhiều object hết hạn sớm hơn kỳ vọng.
Một repository sử dụng @Indexed trên thuộc tính email nhưng email có thể thay đổi, khiến truy vấn chỉ số phụ trả kết quả không tương ứng khi một luồng update thất bại.
Nhóm dùng Redis repositories tìm người dùng theo nhiều trường kết hợp tùy ý, nhưng mô hình secondary indexes không đáp ứng kiểu truy vấn linh hoạt như database quan hệ.
Ứng dụng dùng repository.findAll để hiển thị toàn bộ khách hàng từ Redis, khiến yêu cầu báo cáo kéo nhiều object vào JVM khi số key tăng lên hàng triệu.
Đội dùng repository.count để thống kê số account còn active nhưng key có TTL và housekeeping trễ, khiến số đếm cache không phản ánh số tài khoản được xác nhận ở database nguồn.
Một service xóa entity qua RedisRepository rồi cho rằng tất cả secondary index references được dọn tức thì, nhưng sự cố giữa các thao tác làm danh sách truy vấn phụ còn dữ liệu cũ.
Nhóm xây API đăng ký qua Redis repository với các tài khoản có email trùng, nhưng @Indexed không tự bảo đảm ràng buộc unique như SQL và tạo tài khoản trùng.
Ứng dụng muốn thêm trường mới vào @RedisHash entity sau deploy, nhưng data cũ trong Redis chưa có thuộc tính và constructor Java không cho phép null nên deserialize thất bại.
Đội áp TTL cho Redis repository và kỳ vọng sự kiện key-expired luôn được phát chính xác lúc hết hạn, khiến quy trình dọn quan hệ phụ bỏ sót dữ liệu trong một số lần restart.
Một hệ thống lưu shadow copies của Redis repository để phục vụ sự kiện hết hạn, nhưng bộ nhớ tăng mạnh khi số session ngắn hạn tăng đột biến.
Nhóm tắt keyspace notifications trên Redis vì chính sách vận hành, khiến event expiry mà ứng dụng repository trông chờ không còn xuất hiện.
Ứng dụng lưu cache entity vào Redis repository nhưng dùng cùng keyspace với Spring Cache ở một dịch vụ khác, khiến một lần @CacheEvict xóa nhầm dữ liệu hồ sơ.
Đội triển khai Redis repository trên Redis Cluster với secondary indexes, nhưng truy vấn và cập nhật index phụ đi qua nhiều keys/slots gây khác biệt hiệu năng so với standalone.
Một service lưu đối tượng user bằng repository rồi đọc cùng key qua RedisTemplate có serializer khác, khiến hai đường truy cập không hiểu cùng định dạng dữ liệu.
Nhóm dùng @Reference trong entity Redis để liên kết các object nhưng một object đích đã hết hạn, khiến API nhận tham chiếu không còn hợp lệ khi dựng DTO.
Ứng dụng muốn sort các user theo thời gian cập nhật bằng phương thức repository nhưng không có cấu trúc dữ liệu hỗ trợ sắp xếp, khiến thao tác đọc toàn bộ dữ liệu trở nên tốn kém.
Đội chạy test Spring Data Redis repository bằng Mock object map nhưng không xác minh cách các hash, index và key TTL thực sự được ghi trên server.
Một service lưu session đăng nhập trong Redis repository mà không cô lập tenant trong keyspace, khiến mã người dùng trùng giữa tổ chức có thể gây lẫn hồ sơ.
Nhóm xoay schema serialized entity Redis repository nhưng chưa kiểm chứng truy cập đồng thời từ hai phiên bản app, khiến giá trị vừa cập nhật không được bản cũ đọc lại.
Một ứng dụng gắn @Cacheable cho API tra sản phẩm nhưng key chỉ theo productId, khiến hai thị trường có cùng mã sản phẩm lấy nhầm giá của nhau.
Đội dùng RedisCacheManager với TTL một giờ cho giá khuyến mãi, nhưng giá có thể đổi sau vài phút và cache không được vô hiệu hóa khi quản trị viên cập nhật.
Một API tính tồn kho dùng @Cacheable cho số lượng còn lại nhưng không có quy tắc invalidate khi đặt hàng, khiến người dùng tiếp tục thấy mặt hàng đã hết.
Nhóm đặt @CacheEvict trên method cập nhật khách nhưng method được gọi qua self-invocation trong cùng bean, khiến cache vẫn giữ thông tin cũ.
Ứng dụng dùng @CachePut sau ghi database nhưng giao dịch database sau đó rollback, khiến Redis chứa trạng thái chưa từng được commit chính thức.
Đội cache kết quả tìm kiếm theo từ khóa nhưng key không tính đến filter quyền truy cập, khiến người dùng nhận kết quả đã cache của người có vai trò cao hơn.
Một service dùng Spring Cache để lưu response API chứa thông tin cá nhân nhưng không tách key theo tenant, khiến một cache hit tiết lộ hồ sơ của khách khác.
Nhóm đưa danh sách roles của user vào Redis Cache với TTL dài, khiến quyền vừa bị thu hồi vẫn được áp dụng trong thời gian còn hiệu lực.
Ứng dụng có hai @Cacheable methods dùng chung cache name nhưng key expressions tạo ra cùng chuỗi, khiến kết quả của hai loại dữ liệu bị đọc nhầm.
Đội sử dụng @CacheEvict(allEntries=true) mỗi khi thay đổi một cấu hình nhỏ, khiến hàng nghìn cache entries bị xóa và database hứng tải tăng đột biến.
Một website có hàng chục nghìn request tới key cache vừa hết hạn, khiến toàn bộ request cùng gọi database và tạo cache stampede.
Nhóm cache kết quả rỗng khi sản phẩm chưa tồn tại, nhưng sản phẩm được tạo ngay sau đó và người dùng vẫn thấy không có hàng do negative cache chưa hết hạn.
Ứng dụng dự kiến đặt TTL khác nhau cho từng product category nhưng cấu hình RedisCacheManager hiện chỉ định TTL theo cache name, khiến dữ liệu giữa nhóm hết hạn cùng chính sách không phù hợp.
Đội chọn TTL chính xác một giờ cho mọi key cache phổ biến, khiến nhiều key cùng hết hạn tại một thời điểm và backend chịu đợt tăng lưu lượng đồng loạt.
Một API dùng @Cacheable condition theo cấu hình tenant nhưng chỉ có kiểm thử với tenant mặc định, khiến một số tenant được cache dữ liệu không được phép lưu dài hạn.
Nhóm dùng @Caching kết hợp nhiều @CacheEvict nhưng một cache name không tồn tại trong cấu hình mới, khiến thao tác cập nhật trả lỗi sau khi database đã ghi xong.
Ứng dụng chạy rolling deployment với hai phiên bản DTO khác nhau nhưng dùng cùng cache prefix, khiến pod phiên bản cũ không deserialize được giá trị do pod mới tạo.
Đội bật serialization JSON cho Spring Cache nhưng những cache keys trước đó được tạo bằng Java serialization, khiến việc chuyển cấu hình làm tỷ lệ cache hit giảm mạnh.
Một service chạy cùng lúc cache cục bộ Caffeine và Redis mà không có quy tắc vô hiệu hóa cả hai tầng, khiến mỗi pod trả trạng thái sản phẩm khác nhau sau cập nhật.
Nhóm dùng Redis làm cache duy nhất cho dữ liệu giá nhưng không có fallback khi Redis mất kết nối, khiến API tra cứu thất bại dù database nguồn vẫn sẵn sàng.
Ứng dụng vô hiệu hóa key cache trước khi commit database, khiến request khác đọc lại giá cũ từ database và đưa giá cũ vào cache trước khi transaction hoàn tất.
Đội dùng cache key theo object Java có hashCode không ổn định giữa các phiên bản, khiến cùng request tạo nhiều key và bộ nhớ tăng nhanh.
Một hệ thống cache trạng thái chiến dịch mà không lưu version trong key, khiến rollback code không xóa dữ liệu cache mới không tương thích với quy tắc cũ.
Nhóm muốn biết tỷ lệ cache hit theo nghiệp vụ nhưng dashboard chỉ đếm lệnh GET trên Redis, khiến không phân biệt được cache miss, session lookup và lưu trạng thái.
Một dịch vụ đặt chính sách maxmemory eviction cho Redis dùng chung cache và session, khiến khi cache tăng đột biến các phiên đăng nhập bị xóa ngoài thời hạn.
Ứng dụng đặt noeviction trong Redis nhưng sử dụng nó làm cache dữ liệu không giới hạn, khiến lệnh ghi mới lỗi khi bộ nhớ đầy dù read cache vẫn hoạt động.
Đội dùng TTL cho cache nhưng những key quan trọng không có TTL do một path RedisTemplate khác ghi dữ liệu cùng prefix, khiến bộ nhớ tăng dần và eviction khó dự báo.
Một service đọc TTL của key để thông báo thời gian phiên còn lại, nhưng nhầm giá trị trả về khi key không tồn tại với trạng thái key không có expiration.
Nhóm chạy cập nhật field của Redis Hash và kỳ vọng mọi field có TTL độc lập như key, khiến một thuộc tính cần xóa sớm vẫn còn khi hash chưa hết hạn.
Ứng dụng dùng lệnh set giá trị mới cho cache key nhưng một nhánh không giữ chính sách expiration cũ, khiến dữ liệu phiên tạm thời trở thành key tồn tại lâu dài.
Đội sử dụng TTL làm thời hạn khóa xử lý đơn nhưng tác vụ đôi khi vượt thời gian TTL, khiến worker khác nhận khóa trước khi worker đầu hoàn tất.
Một dịch vụ xoay token và xóa key cũ ở Redis nhưng read replica chưa đồng bộ ngay, khiến yêu cầu xác thực có thể đọc trạng thái cũ trong khoảng thời gian ngắn.
Nhóm đo memory bằng số lượng key mà không xét độ lớn mỗi value và encoding cấu trúc dữ liệu, khiến dự toán tăng trưởng Redis không phản ánh thực tế.
Ứng dụng chạy job làm sạch dữ liệu cache bằng scan nhưng chỉ xử lý một vòng cursor đầu, khiến phần lớn key hết hạn nghiệp vụ vẫn tồn tại sau job.
Đội cấu hình eviction policy allkeys-lru cho Redis vừa lưu cache vừa dùng stream sự kiện, khiến áp lực bộ nhớ có thể loại dữ liệu sự kiện chưa xử lý.
Một service nhận thông báo hết hạn key để thu hồi tài nguyên ngoài Redis, nhưng consumer không kết nối tại thời điểm key expired và sự kiện không được phát lại.
Nhóm dựa vào keyspace notifications để tính chính xác số phiên kết thúc, nhưng Redis phát sự kiện expiration không bảo đảm đúng thời điểm tuyệt đối khi key hết TTL.
Ứng dụng triển khai kiểm thử TTL với giấc ngủ vài mili giây, khiến CI flaky do lịch event loop và độ trễ thao tác ở Redis khác nhau theo máy chạy.
Một hệ thống yêu cầu dữ liệu tạm chỉ được giữ tối đa vài phút nhưng Redis persistence và backup vẫn có thể chứa dữ liệu cũ, khiến chính sách xóa phải được đánh giá ngoài TTL.
Một service dùng Redis Pub/Sub để gửi lệnh hoàn tiền, nhưng subscriber ngắt mạng lúc publish và không có cơ chế phát lại lệnh đã bỏ lỡ.
Nhóm dùng RedisMessageListenerContainer cho các sự kiện cập nhật sản phẩm, nhưng sau một lần reconnect subscriber bị gián đoạn và dashboard chỉ theo dõi số publish thành công.
Ứng dụng công bố thông báo khách hàng qua Redis Pub/Sub nhưng mỗi instance subscriber đều thực hiện gửi email, khiến một sự kiện tạo nhiều email trùng.
Đội dùng cùng channel Pub/Sub cho sự kiện giá và sự kiện xóa tài khoản với hai payload schema khác nhau, khiến listener chung thỉnh thoảng không deserialize được message.
Một service publish event chứa dữ liệu người dùng vào channel Redis mà nhiều nhóm khác cùng subscribe, khiến thông tin nhạy cảm được phân phối ngoài phạm vi cần thiết.
Nhóm chuyển tên channel Pub/Sub sau deploy nhưng một phần subscriber vẫn dùng cấu hình cũ, khiến cập nhật chỉ xuất hiện ở vài ứng dụng trong rolling deployment.
Ứng dụng dùng Redis Pub/Sub để đồng bộ cache eviction giữa các pod nhưng một pod đang restart không nhận message, khiến cache cục bộ của pod đó giữ dữ liệu cũ.
Đội muốn xử lý thông báo Pub/Sub theo thứ tự nghiệp vụ trên nhiều instance, nhưng một subscriber bận CPU xử lý chậm và các bước gửi email bị trễ.
Một service gửi message qua RedisTemplate.convertAndSend và coi số subscriber trả về như xác nhận xử lý thành công, khiến trạng thái nghiệp vụ được đánh dấu hoàn tất sai.
Nhóm phát sự kiện trên pattern channel theo tenant nhưng một subscriber cấu hình pattern quá rộng, khiến nó nhận cả dữ liệu của tenant khác.
Ứng dụng có listener Pub/Sub gọi API bên ngoài đồng bộ rất chậm, khiến thread dispatch message bị nghẽn và các sự kiện sau xử lý muộn.
Đội dùng Redis Pub/Sub để kích hoạt đồng bộ hàng nghìn bản ghi sau reboot, nhưng subscriber khởi động sau khi publisher phát event nên dữ liệu không được làm mới.
Một service kiểm thử Pub/Sub chỉ trên một Redis node local nhưng production có Redis Cluster, khiến việc quan sát và phân phối message qua các node cần được xác minh theo topology thực.
Nhóm triển khai Pub/Sub cho thông báo vận hành mà không có mã correlation ID, khiến sau sự cố không thể xác định request gốc nào tạo ra message.
Ứng dụng muốn biết có bao nhiêu message Pub/Sub chưa xử lý nhưng chỉ lưu thông tin publish, khiến dashboard không thể hiện được backlog hoặc cơ chế ACK như hệ thống kỳ vọng.
Đội phát thay đổi role người dùng qua Pub/Sub nhưng một service bị mất kết nối trong giây lát, khiến quyền cache của service đó không được thu hồi kịp.
Một hệ thống dùng channel Redis Pub/Sub làm nguồn duy nhất để đồng bộ đơn hàng, nhưng subscriber crash sau khi nhận message và dữ liệu không được lưu bền để xử lý lại.
Nhóm gửi notification qua Redis Pub/Sub trong transaction database nhưng transaction rollback sau publish, khiến người nhận thấy một sự kiện không tồn tại ở nguồn chuẩn.
Ứng dụng có hai RedisMessageListenerContainer đăng ký cùng channel trong một service, khiến một message được xử lý hai lần trong cùng ứng dụng.
Đội thay serializer của Pub/Sub producer từ String sang JSON object trong khi consumer cũ còn hoạt động, khiến chỉ một số message được hiểu trong giai đoạn rollout.
Một dịch vụ dùng Redis Streams để ghi sự kiện mua hàng nhưng không giới hạn độ dài stream, khiến lịch sử event tích lũy và Redis memory tăng dần.
Nhóm tạo stream với XADD sau khi ghi database nhưng publish stream thất bại, khiến giao dịch đã commit không có sự kiện phục vụ đồng bộ downstream.
Một consumer group đọc Redis Stream qua XREADGROUP nhưng worker crash trước XACK, khiến record nằm trong pending entries list mà không có quy trình xử lý lại.
Ứng dụng gọi XACK ngay sau khi đọc stream record và trước khi ghi dữ liệu, khiến lỗi database sau đó làm record không được xử lý lại như nghiệp vụ mong muốn.
Đội chia consumer group theo nhiều vùng nhưng mỗi vùng dùng tên group khác nhau, khiến mỗi nhóm đều xử lý cùng stream event và tạo tác động trùng.
Nhóm dùng cùng consumer name cho nhiều instance trong Redis Streams group, khiến việc phân tích pending records và quyền sở hữu message không phản ánh từng worker thật.
Một service dùng StreamMessageListenerContainer nhưng chưa tạo consumer group trước khi đọc, khiến startup gặp lỗi chỉ trong môi trường Redis mới khởi tạo.
Đội bắt đầu đọc consumer group từ ký hiệu chỉ nhận message mới trong khi stream đã có dữ liệu lịch sử chưa xử lý, khiến backlog cũ không được đưa tới nhóm.
Ứng dụng sử dụng Redis Streams để xử lý hóa đơn nhưng không đọc pending entries sau restart, khiến nhiều record đang pending tồn tại mãi khi worker trước đã chết.
Nhóm sử dụng XAUTOCLAIM để nhận lại pending messages quá lâu nhưng không lưu số lần giao lại, khiến một record lỗi liên tục làm nhiều worker lặp lại cùng tác vụ.
Một service cập nhật group consumer pending state sau reconnect nhưng tên consumer bị thay đổi liên tục, khiến bảng theo dõi chứa nhiều consumer cũ không còn hoạt động.
Đội triển khai nhiều stream partitions bằng key theo tenant nhưng giám sát chỉ nhìn một stream, khiến backlog của một tenant lớn không được phát hiện.
Ứng dụng xử lý stream record chứa version DTO mới, nhưng worker phiên bản cũ vẫn đọc cùng group và không deserialize được một số record trong rolling deployment.
Nhóm gửi StreamRecords với serializer khác giữa RedisTemplate và StreamMessageListenerContainer, khiến trường amount được đọc thành byte array thay vì số như người dùng mong đợi.
Một service dùng Redis Streams cho event thanh toán nhưng record không có idempotency key, khiến giao lại sau timeout tạo yêu cầu thanh toán trùng.
Đội cấu hình trim stream theo MAXLEN quá ngắn trong đợt sự cố consumer, khiến một số record chưa xử lý bị loại khỏi dữ liệu stream trước khi được phục hồi.
Ứng dụng muốn replay sự kiện lịch sử từ một Stream nhưng chỉ giữ lại độ dài tối đa theo lưu lượng thường, khiến những ngày quá tải không đủ sự kiện để replay.
Nhóm thêm một consumer group mới sau khi stream chạy lâu nhưng không xác định điểm bắt đầu đọc, khiến hệ thống báo cáo bỏ toàn bộ dữ liệu lịch sử hoặc xử lý lại quá nhiều.
Một service ghi vào Redis Stream rồi dùng event ID làm thứ tự toàn cục cho nhiều stream key, khiến việc đối soát liên tenant sai khi so ID từ những stream độc lập.
Đội tăng số worker đọc Redis Stream nhưng mỗi record có thời gian xử lý khác nhau, khiến tác vụ cùng accountId có tác động ngoài thứ tự nghiệp vụ.
Ứng dụng dùng cùng Stream để xử lý event nhanh và event nặng, khiến những record xử lý lâu làm tăng tuổi chờ của các record phía sau trong consumer group.
Nhóm sử dụng Redis Streams cho retry có delay nhưng không có cơ chế sắp lịch riêng, khiến record lỗi quay lại xử lý ngay và gây tăng tải đối tác.
Một hệ thống di chuyển stream data sang Redis Cluster nhưng consumer vẫn dựa vào một lệnh đa key cross-slot, khiến tác vụ chỉ thất bại trên deployment cluster.
Đội muốn đánh giá stream lag nhưng chỉ đo XLEN, khiến số record đã ACK và số record pending bị hiểu nhầm thành backlog cần xử lý.
Ứng dụng dùng XREADGROUP với block dài trên thread pool nhỏ dùng chung API, khiến các request trực tuyến bị nghẽn khi số stream ít sự kiện.
Nhóm đánh dấu stream record đã xử lý bằng XACK nhưng không lưu kết quả nghiệp vụ cuối cùng, khiến việc audit không phân biệt record được xử lý thành công hay bị bỏ qua do lỗi.
Một service có hai bước ghi Redis và gửi email trong consumer stream, nhưng email thành công rồi ACK thất bại khiến record được giao lại và email gửi hai lần.
Đội xử lý nhiều tenant trong một stream group nhưng một tenant tạo record sai schema liên tục, khiến retry của nhóm này làm chậm toàn bộ các tenant còn lại.
Ứng dụng chạy Redis Streams trong Redis có chính sách eviction phù hợp cache, khiến dữ liệu event tồn đọng có nguy cơ bị ảnh hưởng khi memory chạm giới hạn.
Nhóm kiểm thử Redis Streams chỉ xác nhận XADD và XREAD trên local Redis nhưng không mô phỏng XACK thất bại, pending recovery và consumer group restart.
Một dịch vụ dùng RedisTemplate để thực hiện MULTI/EXEC nhưng các thao tác bên trong không dùng cùng kết nối, khiến kết quả không nằm trong transaction như developer kỳ vọng.
Đội dùng Redis transaction MULTI/EXEC để cập nhật hai khóa rồi kỳ vọng rollback mọi lệnh nếu một lệnh gặp lỗi runtime, khiến dữ liệu nghiệp vụ có nguy cơ cập nhật một phần.
Một ứng dụng thực hiện GET rồi MULTI/EXEC để trừ tồn kho mà không kiểm soát việc giá trị thay đổi giữa hai bước, khiến hai người cùng mua một sản phẩm cuối cùng.
Nhóm dùng WATCH để tránh ghi đè trạng thái đơn nhưng một tác vụ khác cập nhật cùng key liên tục, khiến nhiều transaction bị hủy và request khách timeout.
Một service cập nhật cache và số lần truy cập trong cùng transaction Redis nhưng lại gọi một hệ thống ngoài trước EXEC, khiến side effect ngoài Redis vẫn xảy ra khi transaction không được thực thi.
Đội dùng transaction trong RedisTemplate từ hai thread khác nhau và kỳ vọng trạng thái WATCH/MULTI được chia sẻ, khiến kiểm soát đồng thời không hoạt động như dự tính.
Ứng dụng chạy Redis Cluster với transaction trên hai key khác hash slot, khiến MULTI/EXEC bị lỗi chỉ sau khi chuyển từ Redis standalone.
Nhóm dùng Lua script để trừ hạn mức và ghi log đồng thời nhưng một key thuộc slot khác trong Redis Cluster, khiến script không được phép thao tác theo cách đã xây.
Một service dùng Lua script với vòng lặp trên hàng chục nghìn phần tử, khiến Redis bị chiếm event loop quá lâu và các request khác tăng latency.
Đội sử dụng Lua script để cấp lock có TTL nhưng không kiểm tra owner token khi giải phóng, khiến một worker có thể xóa khóa của worker khác sau khi lock hết hạn và được cấp lại.
Một ứng dụng dùng lệnh SETNX để tạo khóa nhưng gắn TTL trong lệnh thứ hai, khiến crash giữa hai bước có thể để lại khóa tồn tại vô thời hạn.
Nhóm dùng distributed lock Redis cho việc thanh toán mà không xem xét worker bị dừng lâu hơn lease, khiến hai worker có thể cùng xử lý một giao dịch.
Một service dựa vào Redis WATCH để thực thi cập nhật optimistic nhưng serializer của khóa phiên bản khác serializer của bản ghi, khiến điều kiện so sánh không hoạt động.
Đội sử dụng pipelining để chạy một tập lệnh ghi rồi đọc ngay trạng thái trung gian, nhưng logic gọi mong đợi kết quả của từng lệnh đồng bộ trước khi pipeline hoàn tất.
Ứng dụng gửi 10 nghìn Redis commands trong một pipeline không giới hạn, khiến client và Redis phải giữ quá nhiều response trong bộ nhớ khi mạng chậm.
Nhóm tăng pipeline batch size để giảm round-trip nhưng nhiều key rơi vào các Redis Cluster slots khác nhau, khiến việc định tuyến và gom batch khác so với standalone.
Một service dùng executePipelined cho các lệnh đã có giá trị trả về, nhưng code vẫn kiểm tra giá trị trả về ngay trong callback khiến nhánh nghiệp vụ đánh giá sai kết quả.
Đội triển khai pipeline trộn lệnh cập nhật counter với lệnh đọc báo cáo mà không kiểm soát yêu cầu phụ thuộc thứ tự, khiến response xử lý sai khi chuyển sang batch.
Ứng dụng dùng pipelining để giảm latency nhưng một command lỗi WRONGTYPE giữa batch, khiến việc báo cáo thành công chỉ dựa trên số lệnh đã gửi không phát hiện ghi lỗi.
Nhóm dùng batch RedisTemplate để cập nhật nhiều khóa nghiệp vụ nhưng kỳ vọng mọi command thành công hoặc thất bại nguyên tử, khiến dữ liệu lệch khi Redis trả lỗi một phần.
Một API cần đặt giới hạn truy cập cho khách bằng Redis counter nhưng lệnh tăng và kiểm tra hạn mức tách rời, khiến nhiều request song song vượt ngưỡng đã quy định.
Đội dùng Redis Sorted Set cho rate limiting theo cửa sổ trượt nhưng không dọn các timestamp cũ, khiến bộ nhớ và chi phí tính toán tăng theo số request lịch sử.
Ứng dụng cần bảo đảm chỉ xử lý một lần mỗi webhook nhưng khóa idempotency trong Redis hết TTL trước khi đối tác thử lại, khiến lệnh cũ được thực hiện lần nữa.
Nhóm dùng Redis để phát mã thứ tự đơn qua INCR nhưng Redis bị restore từ snapshot cũ, khiến một số mã đã phát có nguy cơ được cấp lại khi hệ thống hồi phục.
Một service lưu cấu hình feature flag trong Redis và thay nhiều key trong một pipeline, khiến các pod đọc tổ hợp giá trị cũ và mới giữa lúc cập nhật.
Đội tạo hàng triệu session locks trên Redis nhưng không có giám sát TTL và owner, khiến số lượng khóa không hết hạn tăng sau các lần lỗi.
Ứng dụng sử dụng transaction Redis cùng database PostgreSQL trong một request rồi coi hai thao tác là một giao dịch phân tán tự động rollback, khiến dữ liệu hai bên không nhất quán.
Nhóm lên lịch cập nhật 50 nghìn Redis keys qua script Lua một lần, khiến các request API khác bị chặn lâu trên node đang thực thi script.
Một ứng dụng cấu hình Redis primary và replica nhưng đọc session từ replica ngay sau write, khiến người dùng đôi lúc không thấy phiên vừa được tạo do replication lag.
Đội đặt read preference tới replica để giảm tải primary, nhưng các request kiểm tra quyền yêu cầu đọc thay đổi vừa thu hồi nên đôi lúc dùng dữ liệu cũ.
Một dịch vụ dùng Redis replica như nguồn đọc độc lập, nhưng khi primary mất mạng replica chưa nhận hết lệnh ghi, khiến sau failover một số dữ liệu phiên mới nhất bị mất.
Nhóm triển khai Sentinel để theo dõi Redis failover nhưng Spring Boot chỉ cấu hình một node Sentinel, khiến ứng dụng không tìm được primary mới khi node Sentinel đó ngừng.
Ứng dụng kết nối Redis Sentinel bằng hostname chỉ resolve được trên máy admin, khiến deployment Kubernetes không nhận được thông tin primary sau failover.
Đội chuyển Redis standalone sang Sentinel mà không cập nhật tên master trong cấu hình Spring Data Redis, khiến client không resolve được endpoint ghi.
Một service sử dụng Redis Cluster nhưng vẫn giả định mọi key cùng nằm trên một node, khiến lệnh đa key báo CROSSSLOT khi key names không dùng cùng hash tag.
Nhóm thiết kế Redis Cluster keys có hash tag theo tenantId để hỗ trợ thao tác đa key, nhưng một tenant lớn tạo hotspot trên một slot và throughput giảm.
Ứng dụng dùng MGET để lấy dữ liệu nhiều sản phẩm phân tán trên các slots Redis Cluster, khiến code chỉ thành công trên standalone và thất bại khi topology thay đổi.
Đội triển khai Redis Cluster sau proxy nhưng client không có topology refresh phù hợp, khiến RedisTemplate liên tục nhận MOVED/ASK khi slot migration diễn ra.
Một service Redis Cluster sử dụng địa chỉ node được quảng bá chỉ có thể truy cập trong một VLAN, khiến pod thuộc subnet khác lỗi sau khi nhận chuyển hướng slot.
Nhóm xây báo cáo sử dụng SCAN một node Redis Cluster và cho rằng đã thấy mọi key, khiến nhiều tài khoản không xuất hiện trong thống kê tổng.
Ứng dụng lưu một Stream trên Redis Cluster node đang được chuyển slot, nhưng consumer không kiểm tra lỗi MOVED và kết quả đọc có gián đoạn trong lúc rebalancing.
Đội thực hiện failover Redis Cluster khi một số shard có replica lag lớn, khiến dữ liệu cache chưa được nhân bản đầy đủ và tỷ lệ cache miss tăng đột ngột.
Một service dùng Redis như kho duy nhất cho dữ liệu thanh toán nhưng cấu hình persistence chỉ phù hợp cache, khiến crash node làm mất trạng thái quan trọng.
Nhóm bật RDB snapshots để dự phòng nhưng không đánh giá dữ liệu phát sinh giữa hai lần snapshot, khiến sau restore nhiều session và lệnh chưa được ghi nhận bị mất.
Ứng dụng chuyển sang AOF để giảm dữ liệu mất khi crash nhưng không đo overhead ghi đĩa, khiến p99 latency tăng rõ rệt khi traffic cao.
Đội dùng Redis replication cho dự phòng nhưng không diễn tập split-brain và chuyển primary, khiến hai nhóm app cập nhật các endpoint khác nhau trong thời gian lỗi mạng.
Một hệ thống triển khai Redis Cluster chỉ có một replica mỗi primary trên cùng availability zone, khiến mất cả zone có thể làm nhiều slots không sẵn sàng.
Nhóm chạy Redis cùng Kubernetes pod app trên node nhỏ nhưng không dự trữ memory cho Redis overhead, khiến OOM kill xảy ra vào giờ cao điểm.
Ứng dụng giữ nhiều connection Redis trong quá trình Sentinel failover mà không phân biệt lỗi kết nối tạm với lỗi quyền, khiến cơ chế retry che khuất vấn đề thật.
Đội dùng Redis Cluster làm cache nhưng không tính chi phí MOVED redirects và cross-zone traffic, khiến latency chênh lệch lớn giữa các namespace.
Một service bật Replica read cho tất cả requests nhằm giảm tải, khiến những API yêu cầu tính nhất quán mạnh hơn nhận dữ liệu cũ sau write.
Nhóm bảo mật bật ACL theo namespace Redis keys nhưng ứng dụng còn dùng một số commands với key prefix cũ, khiến chỉ nghiệp vụ ít dùng bị từ chối.
Ứng dụng chia sẻ Redis Cluster cho cache và session nhưng quota bộ nhớ không phân biệt loại dữ liệu, khiến một tenant có lưu lượng lớn gây eviction phiên của tenant khác.
Đội triển khai TLS cho Redis Cluster nhưng client chỉ tin certificate của seed node, khiến khi chuyển slot sang node khác kết nối mới bị từ chối.
Một service phát hành Redis Cluster với 3 shards nhưng performance test chỉ dùng key phân tán đều, khiến không phát hiện hotspot ở key của doanh nghiệp lớn.
Nhóm restore Redis data sau sự cố nhưng keyspace notification configuration khác trước, khiến các listener phụ thuộc expiration không nhận event dù dữ liệu đã về.
Ứng dụng tăng CPU Redis node nhưng không kiểm tra command latency theo loại dữ liệu, khiến những script Lua và lệnh duyệt tập lớn tiếp tục gây nghẽn.
Đội bật Redis ACL password rotation nhưng không xác định cách cập nhật credential cho các pool đang chạy, khiến một số client ngắt kết nối sau khi mật khẩu cũ thu hồi.
Một service Redis lưu session truy cập nhưng không phân biệt dữ liệu có thể tái tạo và dữ liệu bắt buộc giữ bền, khiến kế hoạch disaster recovery không đánh giá đúng hậu quả mất key.
Nhóm sử dụng Redis Testcontainers để kiểm thử RedisTemplate nhưng test chỉ chạy standalone và không bao phủ hash slot, MOVED/ASK hoặc Sentinel failover.
Ứng dụng unit test @Cacheable với cache manager in-memory, khiến lỗi serializer và TTL của RedisCacheManager chỉ xuất hiện sau khi triển khai production.
Đội test cơ chế tự động hết hạn key bằng Thread.sleep cố định quá ngắn, khiến CI thỉnh thoảng FAIL khi Redis xử lý expiration không đúng thời điểm test giả định.
Một bộ integration test chỉ xác nhận Redis Stream đã có record sau XADD, nhưng không thử pending entries, XACK và claim khi consumer chết giữa lúc xử lý.
Nhóm mock RedisTemplate trong test giao dịch nhưng không kiểm thử WATCH, MULTI/EXEC trên cùng connection, khiến lỗi optimistic locking không được phát hiện.
Ứng dụng kiểm thử Redis Pub/Sub bằng một publisher và subscriber luôn kết nối, khiến rủi ro mất message khi subscriber restart không được phản ánh trong test.
Đội chạy benchmark 100 GET trên localhost Redis nhưng production kết nối TLS xuyên zone, khiến lợi ích pipelining và giới hạn timeout bị đánh giá sai.
Một service tạo unit test RedisRepository với entity mới đủ field, nhưng không thử đọc hash từ bản ứng dụng cũ có tên field và serializer khác.
Nhóm chạy smoke test chỉ gọi PING Redis và đánh dấu integration khỏe, dù Redis đang đạt maxmemory và những lệnh ghi tiếp theo sẽ bị từ chối.
Ứng dụng đo số key Redis thay vì used_memory và evicted_keys, khiến đợt tăng kích thước value không kích hoạt cảnh báo dù bộ nhớ gần đầy.
Đội phát hiện Redis slowlog tăng nhưng dashboard không gắn command pattern và caller service, khiến một API dùng lệnh quét tập lớn làm chậm các hệ thống khác khó được khoanh vùng.
Một service báo tỷ lệ cache hit cao nhưng dữ liệu sản phẩm đang bị cache stale, khiến chỉ số hiệu năng che khuất sự cố cập nhật giá sau ghi database.
Nhóm dùng Redis INFO metrics cho cluster nhưng chỉ giám sát một primary, khiến một shard bị quá tải còn dashboard chung vẫn báo năng lực bình thường.
Ứng dụng log toàn bộ Redis commands và payload để debug, khiến session token và thông tin cá nhân bị ghi vào kho log tập trung ngoài chính sách bảo mật.
Đội muốn xác nhận bao nhiêu Redis Streams records còn pending nhưng dashboard chỉ đếm XLEN, khiến backlog chưa ACK không được cảnh báo đúng.
Một hệ thống phân tán dùng Redis counter để tính rate limit nhưng không có trace correlation giữa HTTP request và command Redis, khiến khó phân biệt trượt hạn mức với timeout.
Nhóm triển khai Redis key eviction trên production nhưng không theo dõi expired_keys và evicted_keys riêng, khiến việc key bị xóa do TTL bị nhầm với mất key do thiếu bộ nhớ.
Ứng dụng cần thu hồi quyền truy cập ngay khi HR khóa tài khoản nhưng đang dùng Redis Cache TTL dài và không có kiểm thử propagation, khiến tài khoản bị khóa vẫn truy cập vài phút.
Đội đánh giá độ an toàn Redis ACL bằng một user có quyền admin trong test, khiến quyền tối thiểu cho Spring Boot production chưa được kiểm chứng.
Một service xử lý lệnh quan trọng bằng Redis Streams nhưng kế hoạch khôi phục chỉ test restart app, không test mất primary trước khi record được replica nhân bản.
Nhóm nâng Redis server và Spring Data Redis cùng lúc nhưng test chỉ mock RedisConnectionFactory, khiến một thay đổi về codec và protocol chỉ lỗi khi chạy cluster thật.
Ứng dụng chuyển session cache từ Redis standalone sang cluster khi đang có hàng triệu key, nhưng không kiểm tra chiến lược di trú và TTL của khóa cũ nên hàng loạt người dùng bị đăng xuất.
Đội xây chức năng giới hạn tốc độ bằng Redis nhưng không kiểm thử nhiều API instances gọi cùng lúc vào một key, khiến tính đúng đắn của hạn mức chưa được chứng minh.
Một tổ chức yêu cầu chứng minh mọi cập nhật quyền truy cập đã được áp dụng cho cache phân tán, nhưng log Redis và ứng dụng không có version sự kiện, thời điểm ghi hoặc correlation ID chung.
