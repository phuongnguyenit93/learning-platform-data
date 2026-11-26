Một ứng dụng Spring Boot dùng Spring Data Cassandra lưu lịch sử đơn hàng theo khách, nhưng entity chỉ có orderId làm khóa khiến truy vấn tất cả đơn của một khách không phù hợp với cấu trúc bảng.
Nhóm phát triển ánh xạ một bảng Cassandra bằng @Table nhưng đặt tên trường Java khác tên cột trong keyspace, khiến một số thuộc tính khách hàng đọc được thành null sau khi deploy.
Một dịch vụ phân tích dùng @PrimaryKey cho một trường có thể thay đổi trong quy trình kinh doanh, khiến thao tác cập nhật mã tài khoản không phản ánh bản ghi cũ trong Cassandra.
Đội vận hành chuyển bảng từ khóa đơn sang composite primary key, nhưng entity Spring Data Cassandra vẫn ánh xạ khóa cũ và không tìm thấy những bản ghi vừa nhập.
Ứng dụng tạo @PrimaryKeyClass chứa tenantId và eventDate nhưng hai thuộc tính được đánh dấu loại khóa không phù hợp, làm cách Cassandra phân bố dữ liệu khác với thiết kế.
Một entity dùng @PrimaryKeyColumn cho cả partition key và clustering column, nhưng thứ tự khai báo không nhất quán với schema khiến truy vấn theo thời gian bị trả sai thứ tự.
Nhóm tích hợp ánh xạ @PrimaryKeyClass vào entity qua @PrimaryKey, nhưng DTO đầu vào bỏ thiếu một thành phần khóa khiến thao tác save thất bại với dữ liệu hợp lệ về nghiệp vụ.
Một ứng dụng lưu lịch sử trạng thái giao hàng theo mã vận đơn và thời điểm, nhưng timestamp từ hai nguồn có thể trùng nhau nên bản ghi mới ghi đè bản ghi trước.
Đội thiết kế clustering column theo thời gian tăng dần cho bảng nhật ký, nhưng API luôn yêu cầu 100 sự kiện mới nhất và việc đọc phải xử lý lượng dữ liệu không cần thiết.
Một service Spring Data Cassandra dùng kiểu UUID sinh ngẫu nhiên cho khóa cần sắp theo thời gian, khiến thứ tự clustering không phản ánh thời điểm phát sinh nghiệp vụ.
Nhóm chuyển kiểu khóa sự kiện từ UUID sang timeuuid nhưng các entity lịch sử còn dùng kiểu cũ, khiến serializer và truy vấn CQL không tương thích sau thay đổi.
Ứng dụng ánh xạ cột thời gian kiểu timestamp vào Java LocalDateTime mà không quy định múi giờ, khiến cùng sự kiện được hiển thị sang ngày khác giữa các vùng.
Một bảng Cassandra lưu số tiền dạng decimal, nhưng model Java dùng double trong entity nên dữ liệu thanh toán bị sai khác khi đọc rồi ghi lại nhiều lần.
Đội khai báo cột trạng thái trong Cassandra là text nhưng dùng enum Java với cách đặt tên mới, khiến các bản ghi cũ không thể chuyển đổi thành enum được hỗ trợ.
Ứng dụng lưu địa chỉ khách trong Cassandra UDT, nhưng entity Java chưa cập nhật mapping khi UDT bổ sung một thuộc tính bắt buộc, khiến một nhóm hồ sơ bị giải mã không đầy đủ.
Nhóm dùng collection dạng list để lưu lịch sử thao tác trong một hàng Cassandra, nhưng danh sách tăng không giới hạn theo tuổi thọ khách và bản ghi trở nên quá lớn.
Một entity Spring Data Cassandra lưu các nhãn sản phẩm ở kiểu set, nhưng API yêu cầu giữ thứ tự người dùng nhập nên kết quả hiển thị không nhất quán sau khi đọc.
Đội chuyển thuộc tính metadata từ map sang UDT để chuẩn hóa, nhưng một batch dữ liệu cũ còn sử dụng cấu trúc map và không được migration đúng cách.
Ứng dụng lưu một tập địa chỉ giao hàng bên trong collection của entity, nhưng yêu cầu chỉnh một địa chỉ riêng dẫn đến việc nhiều luồng cùng ghi đè toàn bộ tập dữ liệu.
Nhóm tạo entity bất biến bằng constructor trong Spring Data Cassandra, nhưng một trường cũ nullable không tương thích tham số non-null nên đọc dữ liệu lịch sử bị lỗi.
Một bảng có cột tên được Cassandra lưu dạng snake_case, nhưng quy tắc naming strategy trong ứng dụng đổi sau nâng cấp khiến repository đọc sai một số cột.
Đội dùng converter tùy biến cho dữ liệu nhị phân trong Cassandra, nhưng converter ghi và đọc dùng định dạng khác nên tệp đính kèm chỉ lỗi sau khi restart service.
Ứng dụng dùng cùng entity Cassandra cho API public và lưu trữ, nhưng thêm cột nội bộ nhạy cảm làm mapper phản hồi tự động đưa thông tin đó ra ngoài.
Nhóm tạo hai entity Java cùng trỏ một bảng Cassandra với kiểu dữ liệu khác nhau ở một cột, khiến dữ liệu được ghi từ một service không thể đọc bởi service kia.
Một microservice Spring Boot thay đổi @Table để trỏ tới bảng mới theo profile nhưng repository tại production vẫn dùng keyspace mặc định, khiến dữ liệu bị ghi vào môi trường sai.
Đội muốn dùng trường địa chỉ email làm partition key vì thường tra cứu bằng email, nhưng email có thể đổi và dữ liệu cũ cần được truy xuất theo lịch sử định danh.
Ứng dụng cần xem 50 giao dịch gần nhất của một tài khoản, nhưng bảng được thiết kế theo transactionId đơn lẻ và API phải gọi truy vấn hàng loạt để ghép kết quả.
Nhóm lưu tất cả sự kiện telemetry của thiết bị vào một partition theo deviceId, khiến thiết bị hoạt động nhiều năm tạo partition khổng lồ và truy vấn chậm dần.
Một hệ thống log chọn ngày làm partition key cho mọi thiết bị, khiến toàn bộ traffic giờ cao điểm tập trung vào một số token và gây hotspot trên cluster.
Đội phân phối đơn hàng theo tenantId nhưng một tenant lớn tạo nhiều lần lưu lượng hơn các tenant khác, khiến partition và node chứa tenant đó quá tải.
Ứng dụng dùng timestamp làm partition key cho sự kiện, nhưng mỗi mili giây chỉ chứa ít dữ liệu và truy vấn theo khoảng thời gian phải đọc rất nhiều partition.
Nhóm thiết kế một bảng phục vụ cả truy vấn theo khách và theo trạng thái đơn, nhưng CQL query theo trạng thái không cung cấp partition key và bị từ chối trên production.
Một dashboard yêu cầu lọc theo năm, khu vực và trạng thái nhưng bảng Cassandra chỉ được khóa theo mã sản phẩm, khiến từng tổ hợp bộ lọc không phù hợp đường truy vấn chính.
Đội phát triển muốn truy vấn danh sách sản phẩm theo danh mục và theo thương hiệu, nhưng chỉ tạo một bảng với partition key thuộc danh mục và kỳ vọng hai truy vấn có cùng hiệu năng.
Ứng dụng ghi sự kiện theo customerId và time bucket, nhưng API tìm một đơn cụ thể không biết bucket chứa bản ghi nên phải thử nhiều phân vùng.
Một dịch vụ phân tích chọn bucket một giờ cho giao dịch, nhưng các khách có lưu lượng rất khác nhau làm một số bucket quá rộng còn phần lớn bucket rỗng.
Nhóm chia dữ liệu telemetry theo bucket mỗi tháng, nhưng một thiết bị phát hàng triệu sự kiện mỗi ngày khiến partition vẫn quá lớn và thời gian đọc tăng mạnh.
Một hệ thống tạo bảng lookup riêng theo accountId để phục vụ API, nhưng thao tác ghi dữ liệu chính thành công còn ghi lookup thất bại khiến hai đường đọc trả kết quả khác nhau.
Đội phục vụ truy vấn đơn hàng theo ngày bằng bảng denormalized, nhưng khi trạng thái đơn thay đổi một bảng được cập nhật muộn hơn các bảng còn lại.
Ứng dụng muốn tìm top sản phẩm toàn hệ thống theo lượt xem nhưng Cassandra đang lưu lượt xem theo từng khách, khiến phép tổng hợp liên partition không đáp ứng độ trễ API.
Nhóm lưu danh sách người tham gia chương trình trong một partition toàn cục, khiến chiến dịch có hàng triệu người đăng ký tạo một phân vùng quá rộng để truy vấn.
Một API cho phép người dùng tùy ý chọn cột sắp xếp, nhưng Cassandra chỉ hỗ trợ ordering phù hợp với clustering key của bảng đã thiết kế nên nhiều lựa chọn không chạy được.
Đội thiết kế partition theo tenant và clustering theo createdAt, nhưng truy vấn cần thêm trạng thái mà không có cấu trúc truy xuất phù hợp khiến team định bật ALLOW FILTERING.
Ứng dụng muốn phân trang lịch sử giao dịch theo trạng thái ở nhiều tenant, nhưng mô hình hiện tại đòi quét phân vùng không liên quan trước khi có kết quả.
Nhóm sử dụng secondary index cho cột trạng thái chỉ có ba giá trị trên dữ liệu khổng lồ, khiến nhiều truy vấn có độ phân biệt thấp tạo tải lớn vào cluster.
Một dịch vụ đang dùng SAI index cho cột tìm kiếm mới, nhưng bài test chạy phiên bản Cassandra không hỗ trợ cấu hình index của môi trường production.
Đội lập schema Cassandra với materialized view phục vụ truy vấn phụ, nhưng độ trễ cập nhật và lỗi đồng bộ view làm hai API trả trạng thái chưa nhất quán.
Ứng dụng có bảng theo customerId để hiển thị lịch sử và bảng theo orderId để truy vấn chi tiết, nhưng không có quy tắc xác định bản ghi nào là nguồn chuẩn khi hai bảng lệch.
Một hệ thống lưu dữ liệu vị trí thiết bị theo tọa độ rồi cần tìm các thiết bị nằm trong bán kính, nhưng partition và CQL hiện tại không hỗ trợ truy vấn không gian theo yêu cầu.
Nhóm xây trang quản trị cho phép tìm chuỗi con trong mọi cột text, nhưng bảng Cassandra được tạo theo khóa truy vấn cụ thể và không hỗ trợ tìm kiếm linh hoạt như engine tìm kiếm.
Một service đọc tất cả hồ sơ của tenant rồi lọc theo quyền ở tầng ứng dụng, khiến tenant lớn phải tải quá nhiều bản ghi cho mỗi request.
Đội dùng cột trạng thái làm partition key cho bảng tác vụ, khiến gần như mọi tác vụ đang chờ dồn vào cùng partition và gây nghẽn ghi.
Ứng dụng thêm thuộc tính số điện thoại làm khóa phụ để tra cứu khách, nhưng dữ liệu điện thoại có thể trùng và được chuẩn hóa khác nhau giữa hai nguồn.
Nhóm cần hiển thị hàng nghìn kết quả theo thời gian trên tất cả chi nhánh, nhưng bảng chỉ sắp xếp thời gian bên trong từng partition của chi nhánh.
Một repository Spring Data Cassandra khai báo derived query theo trường không thuộc primary key, khiến phương thức chạy test dữ liệu ít nhưng bị từ chối hoặc tốn tài nguyên ở cluster thật.
Đội dùng CassandraRepository tìm bản ghi theo orderId nhưng entity dùng composite key, khiến call site chỉ truyền một phần khóa và API luôn trả kết quả không tìm thấy.
Ứng dụng sử dụng repository save cho bản cập nhật chỉ chứa vài trường, nhưng dữ liệu chưa được nạp đầy đủ khiến các cột khác có nguy cơ bị ghi đè không như ý định.
Nhóm kỳ vọng CassandraRepository save hoạt động như insert-only, nhưng hai request cùng khóa thực hiện upsert và bản ghi được ghi lại ngoài ý muốn.
Một repository dùng findAll để xuất dữ liệu báo cáo toàn bộ keyspace, khiến mỗi lượt export đọc lượng dữ liệu rất lớn và gây áp lực cho các node.
Đội triển khai phương thức deleteById cho entity có nhiều thành phần khóa, nhưng yêu cầu HTTP chỉ cung cấp ID công khai nên không thể định danh partition cần xóa.
Một dự án nâng phiên bản Spring Data Cassandra làm thay đổi cách ánh xạ lớp khóa composite, khiến repository test tự tạo dữ liệu mới PASS nhưng đọc dữ liệu cũ lỗi.
Ứng dụng thêm @Query CQL vào repository với điều kiện lọc theo một clustering column nhưng thiếu partition key, khiến endpoint hiển thị đơn hoạt động khác giữa các loại dữ liệu.
Nhóm khai báo @Query để đọc sự kiện theo ngày nhưng sử dụng chuỗi nối từ tham số người dùng, tạo rủi ro CQL injection và lỗi escape khi có ký tự đặc biệt.
Một method repository có tham số trạng thái tùy chọn, nhưng CQL tĩnh không phản ánh trường hợp tham số null và trả kết quả sai cho truy vấn lọc nâng cao.
Đội viết repository tìm đơn theo danh sách nhiều partition keys bằng IN rất lớn, khiến request gây tải fan-out khi khách nhập hàng nghìn mã.
Một service trả Slice dữ liệu từ repository nhưng controller tiếp tục chuyển sang Pageable với offset tùy ý, khiến API có vẻ hỗ trợ nhảy trang không phù hợp Cassandra.
Nhóm dùng phương thức count trên tập dữ liệu nhiều partition để hiển thị tổng số kết quả, khiến trang danh sách chậm dù chỉ cần hiển thị vài chục bản ghi.
Một ứng dụng dùng repository reactive cho màn hình theo dõi, nhưng service gọi block để chuyển sang DTO đồng bộ ngay trên event loop và làm giảm thông lượng dưới tải.
Đội tạo hai repositories cho cùng bảng nhưng mỗi repository sử dụng một converter khác nhau cho cột metadata, khiến dữ liệu ghi bởi tác vụ nền không đọc được ở API.
Một service đặt keyspace trong cấu hình repository và đồng thời dùng keyspace mặc định ở connection, khiến bản phát hành chạy trên staging nhưng production truy vấn sai keyspace.
Nhóm mock CassandraRepository bằng dữ liệu được sắp theo orderId trong unit test, nhưng kết quả thực tế của truy vấn Cassandra có thứ tự theo clustering columns khác.
Ứng dụng dùng @Query với LIMIT cố định cho API tải dữ liệu, nhưng client đưa page size lớn hơn khiến số bản ghi thực tế không đáp ứng hợp đồng trả về.
Một repository dựa vào contains trên collection có index ở một môi trường nhưng môi trường khác không triển khai cùng index, khiến truy vấn chỉ lỗi trên một cluster.
Đội khai báo projection để chỉ đọc vài trường, nhưng serializer vẫn yêu cầu giá trị bắt buộc của entity đầy đủ và lỗi khi cột không được truy xuất.
Một phương thức repository xóa nhiều entity theo IDs từ các partition khác nhau, nhưng API kỳ vọng thao tác toàn bộ hoặc không gì xảy ra như transaction SQL.
Ứng dụng di trú từ JPA sang CassandraRepository nhưng tiếp tục phụ thuộc vào lazy association giữa entity, khiến lớp service không lấy được dữ liệu liên kết như thiết kế cũ.
Một nhóm dùng CassandraTemplate để ghi lịch sử hàng loạt nhưng không truyền đủ thành phần primary key, khiến các record của hai nguồn có cùng timestamp ghi đè lên nhau.
Đội viết CQL thủ công qua CassandraTemplate để cập nhật một cột, nhưng entity sử dụng field mapping khác tên cột thực và bản cập nhật không ảnh hưởng dữ liệu mong đợi.
Ứng dụng dùng CassandraTemplate.select để đọc bảng mới nhưng query tự xây có keyspace khác default, khiến staging trả đúng còn production trả tập dữ liệu rỗng.
Nhóm cần cập nhật TTL cho một cột qua CassandraTemplate, nhưng không thống nhất cách đối soát thời điểm hết hạn giữa những lần ghi giá trị khác nhau.
Một luồng batch dùng CassandraTemplate insert từng event chậm, nhưng nhóm dự định gộp tất cả mutation vào batch lớn dù chúng thuộc nhiều partition không liên quan.
Đội sử dụng QueryBuilder để tạo CQL động theo các bộ lọc từ API, nhưng một tổ hợp điều kiện không có partition key khiến Cassandra phải từ chối truy vấn.
Ứng dụng có một bảng với nhiều cột clustering, nhưng query tạo qua CassandraTemplate dùng range trên cột trước rồi tiếp tục điều kiện không hợp lệ cho cột sau.
Nhóm dùng CassandraTemplate xóa toàn bộ hàng khi chỉ muốn xóa một cột dữ liệu hết hiệu lực, khiến thông tin khác của cùng partition biến mất khỏi API.
Một service nhận danh sách lệnh cập nhật và dùng CassandraTemplate trong vòng lặp, nhưng không kiểm soát số request đồng thời khiến driver bị quá tải khi nhận batch lớn.
Đội thực thi CQL với consistency mặc định qua CassandraTemplate nhưng bảng giao dịch cần chính sách đọc khác với bảng telemetry, khiến hành vi lỗi không nhất quán.
Một chương trình đối soát lưu CQL statement đã prepare trong singleton nhưng schema được thay đổi khi runtime, khiến chỉ một số câu query cũ bị lỗi sau rollout.
Nhóm dùng CassandraTemplate để lưu UDT chứa metadata sản phẩm, nhưng converter tùy chỉnh bỏ qua trường mới khiến dữ liệu được ghi bởi service khác không còn nguyên vẹn.
Ứng dụng định chèn record mới với điều kiện chưa tồn tại nhưng dùng CassandraTemplate insert thông thường, khiến request trùng ghi đè dữ liệu nghiệp vụ.
Đội tạo custom repository sử dụng CassandraOperations để phục vụ trang báo cáo, nhưng một method nạp toàn bộ partition vào list trước khi lọc khiến bộ nhớ JVM tăng mạnh.
Một dịch vụ phân tích dùng ReactiveCassandraTemplate phát Flux kết quả, nhưng consumer gọi collectList trên hàng triệu hàng và làm hết heap khi có hai job cùng chạy.
Nhóm dùng reactive Cassandra operations trên WebFlux nhưng tạo truy vấn riêng lẻ cho từng item trong Flux mà không giới hạn concurrency, khiến số request driver tăng bất thường.
Ứng dụng xử lý reactive result qua publishOn scheduler khác, nhưng ngữ cảnh tenant và trace được cất trong ThreadLocal nên không đi theo các callback phía sau.
Đội xây reactive endpoint đọc CQL phân trang, nhưng client hủy request giữa chừng mà luồng xử lý vẫn tiếp tục tiêu thụ tài nguyên phía database.
Một service reactive ghi Cassandra rồi phát thông điệp broker trong hai publisher tách rời, khiến lời gọi HTTP hoàn tất dù sự kiện downstream chưa được gửi.
Nhóm kiểm thử Reactor pipeline chỉ xác nhận Mono được tạo mà không subscribe, khiến thao tác ghi Cassandra chưa thực hiện trong lúc bài test vẫn báo PASS.
Ứng dụng dùng ReactiveCassandraRepository cho lịch sử và CassandraTemplate đồng bộ ở tác vụ khác, nhưng cấu hình consistency khác nhau làm hai đường đọc thấy trạng thái khác nhau.
Đội muốn chuyển một CassandraTemplate operation lâu sang bất đồng bộ, nhưng logic blocking vẫn chạy trên event loop WebFlux khiến nhiều request nhỏ bị chậm.
Một ứng dụng tính phí theo customerId nhưng thiết kế partition theo orderId, khiến thao tác tổng hợp tất cả đơn của một khách phải fan-out tới nhiều node.
Nhóm sử dụng một partition key là quốc gia của khách, nhưng nhóm khách ở một quốc gia chiếm đa số khiến node sở hữu token tương ứng bị nóng.
Đội thêm time bucket vào partition key để giảm kích thước partition, nhưng API đọc 90 ngày phải tìm nhiều bucket mà không có giới hạn số truy vấn song song.
Ứng dụng lưu event của từng cảm biến theo deviceId và ngày, nhưng thiết bị ở trạng thái lỗi phát hàng trăm nghìn event mỗi phút khiến một partition ngày vẫn quá lớn.
Nhóm dùng hash ngẫu nhiên làm một phần partition key để phân tán ghi, nhưng API truy vấn theo accountId không biết cách xác định các shard đang chứa dữ liệu.
Một bảng Cassandra lưu lần truy cập người dùng với partition theo userId, nhưng một tài khoản bot tạo lưu lượng rất lớn khiến các request khác trên node cùng token bị ảnh hưởng.
Đội lưu mọi trạng thái shipment vào một hàng với list tăng dần, khiến dữ liệu vượt kích thước mong đợi và lần ghi sau phải xử lý collection lớn.
Ứng dụng chọn clustering order tăng dần theo eventTime, nhưng thao tác đọc bản mới nhất liên tục phải sử dụng đường truy vấn không phù hợp với API.
Nhóm thiết kế bảng theo partition của tổ chức và clustering theo userId, nhưng tính năng xem bản ghi gần nhất theo thời gian không còn được tối ưu.
Một service giữ một partition cho toàn bộ dữ liệu hợp đồng của doanh nghiệp lớn, khiến việc repair và đọc partition tốn tài nguyên bất thường trong giờ cao điểm.
Đội dùng chuỗi ngày không chuẩn hóa làm thành phần partition key, khiến cùng ngày có hai biểu diễn và dữ liệu bị phân tán sang các partition khác nhau.
Ứng dụng truy vấn theo customerId nhưng record được ghi với customerId khác chữ hoa, khiến một số dữ liệu không tìm thấy dù đối tác cho rằng là cùng khách.
Nhóm dùng mã khu vực làm partition key khi ghi dữ liệu GPS, nhưng xe tập trung ở thành phố lớn khiến một vùng địa lý tạo hotspot liên tục.
Một service lưu số liệu doanh thu theo tháng trong một partition duy nhất, nhưng lượng giao dịch của tháng khuyến mãi làm kích thước và độ trễ đọc tăng đột biến.
Đội muốn lưu dữ liệu log 10 năm theo applicationId, nhưng không ước tính số hàng cho mỗi partition nên bảng cần quét hàng triệu bản ghi khi điều tra một giờ.
Một API hỗ trợ sắp xếp theo status khi partition có clustering order theo createdAt, khiến yêu cầu product mới không thể thực hiện bằng CQL đang có.
Nhóm dùng token range scan để xuất dữ liệu toàn cluster nhưng job chạy cùng giờ bán hàng cao điểm, khiến đọc tuần tự làm giảm tài nguyên cho request nghiệp vụ.
Ứng dụng ghi nhiều bản ghi có cùng composite key do timestamp bị làm tròn giây, khiến các event đến trong cùng giây bị ghi đè và khó truy vết.
Đội tính toán token distribution dựa trên số partition mà không xét kích thước mỗi partition, khiến cluster trông cân bằng về số khóa nhưng lệch dữ liệu nghiêm trọng.
Một dịch vụ có 20 node Cassandra nhưng một số partition rất lớn, khiến việc scale out chưa giảm độ trễ cho các truy vấn truy cập những partition đó.
Nhóm cấu hình keyspace replication factor cao hơn số node sẵn có trong môi trường test, khiến chính sách consistency hoạt động khác giữa test và production.
Một ứng dụng đặt consistency ONE cho đọc trạng thái đơn sau cập nhật nhưng nghiệp vụ kỳ vọng thấy bản ghi mới ngay, khiến request đọc từ replica chưa cập nhật trả trạng thái cũ.
Đội cấu hình consistency QUORUM cho ghi ở cụm nhiều datacenter nhưng một vùng bị mất kết nối, khiến tác vụ quan trọng bị timeout dù còn replica khác tiếp nhận được ghi.
Ứng dụng sử dụng LOCAL_QUORUM cho thao tác tại một datacenter nhưng triển khai thêm vùng mới với cấu hình keyspace không phù hợp, khiến nhiều request đọc thất bại.
Nhóm chỉ kiểm thử consistency LOCAL_ONE khi mạng ổn định, nhưng một lần lỗi replica làm dashboard đọc dữ liệu cũ và người dùng thấy trạng thái vừa cập nhật bị mất.
Một service ghi consistency thấp để tăng throughput rồi đọc từ một vùng khác ngay lập tức, khiến các giao dịch liên vùng không có mức hiển thị dữ liệu như sản phẩm mong đợi.
Đội thay consistency profile ở driver cho một nhóm CQL statements nhưng một custom CassandraTemplate path dùng profile mặc định, khiến hai endpoint nghiệp vụ có hành vi khác nhau.
Ứng dụng thực hiện counter update cho lượt xem rồi retry sau timeout, khiến bộ đếm tăng lần nữa dù request đầu có thể đã được áp dụng.
Nhóm lưu counter và dữ liệu đơn hàng thông thường trong cùng quy trình nghiệp vụ, nhưng kỳ vọng cả hai mutation được rollback như transaction quan hệ khi một bước thất bại.
Một bảng Cassandra theo dõi tồn kho cần chặn hai người cùng mua sản phẩm cuối, nhưng code thực hiện đọc rồi ghi bình thường và hai request đều thấy đủ hàng.
Đội dùng lightweight transaction IF NOT EXISTS cho mỗi sự kiện telemetry khối lượng rất lớn, khiến p99 ghi tăng mạnh khi có nhiều yêu cầu cạnh tranh.
Một service dựa vào compare-and-set qua LWT để cập nhật trạng thái đơn, nhưng không xử lý trường hợp điều kiện không thỏa và vẫn trả API đã thành công.
Nhóm dùng CQL conditional update theo version nhưng client retry với version cũ sau timeout, khiến trạng thái cuối của thao tác không thể suy ra chỉ từ kết quả HTTP.
Ứng dụng muốn bảo đảm transaction đồng thời trên hai partition Cassandra khác nhau bằng một batch statement, nhưng quy trình tài chính vẫn có thể gặp trạng thái trung gian không phù hợp.
Đội lập một logged batch rất lớn gồm hàng nghìn partition để ghi sự kiện, khiến coordinator bị quá tải và thời gian xử lý dao động theo tải cluster.
Một service coi batch Cassandra là cơ chế tối ưu mọi ghi hàng loạt, nhưng batch nhiều partition làm write latency tăng thay vì giảm khi lưu sự kiện từ nhiều khách.
Nhóm nhận duplicate event sau Kafka redelivery và dùng ghi Cassandra không kèm idempotency key, khiến các bản ghi thống kê theo sự kiện được cộng hoặc cập nhật lặp.
Ứng dụng dùng timestamp do client cung cấp để giải quyết ghi đồng thời, nhưng đồng hồ của hai producer lệch nhau khiến giá trị cũ thắng bản cập nhật mới.
Đội đồng bộ dữ liệu từ hai nguồn có clock skew nhưng dựa vào last-write-wins mặc định, khiến cùng entity đôi lúc khôi phục trạng thái đã bị thay thế.
Một service cần xác nhận người dùng đã đổi mật khẩu trước khi cho phép đăng nhập, nhưng mức consistency đọc của bảng trạng thái không phù hợp với yêu cầu an toàn.
Nhóm triển khai hai datacenter với replication không đồng đều, nhưng test consistency dùng cluster một datacenter nên không phát hiện cách hệ thống phản hồi khi mất một vùng.
Ứng dụng nhận timeout khi ghi Cassandra rồi trả lỗi cho khách, nhưng request có thể đã ghi thành công ở một số replica và lần retry không có ID giao dịch ổn định.
Đội cần điều tra lỗi read timeout Cassandra giữa giờ cao điểm nhưng metrics không phân biệt lỗi do số replica không đáp ứng và lỗi do client timeout quá ngắn.
Một service chạy repair không đều trên cluster nhiều node, khiến replica lệch dữ liệu tồn tại lâu và các mức consistency thấp trả kết quả khác nhau theo node.
Nhóm cập nhật trạng thái job bằng CQL bình thường từ nhiều workers, nhưng không có cơ chế kiểm soát ghi đồng thời khiến trạng thái DONE có thể bị ghi lại thành RUNNING.
Ứng dụng dùng Cassandra timestamp được cung cấp từ sự kiện để thực thi ghi, nhưng event đến muộn có timestamp lớn bất thường làm bản sửa sau đó không thể ghi đè như dự kiến.
Đội đặt TTL cho dữ liệu session nhưng logic Spring Boot giả định hàng bị xóa ngay tại thời điểm hết hạn, khiến hành vi đọc quanh ranh giới TTL khó đối soát.
Một service dùng TTL cho mỗi lần upsert dữ liệu khách, nhưng thời gian lưu được tính lại khi cập nhật từng cột khiến các thuộc tính của cùng hồ sơ hết hạn khác nhau.
Nhóm giữ event trong Cassandra 30 ngày bằng TTL, nhưng job đối soát hoạt động sau 45 ngày nên không còn đủ dữ liệu để xác minh giao dịch.
Ứng dụng cập nhật bản ghi có TTL cũ bằng một số thao tác ghi không chỉ định TTL, khiến dữ liệu mới có vòng đời khác kỳ vọng của nhóm bảo mật.
Đội cấu hình default_time_to_live cho bảng log trong Cassandra nhưng một số cột cần giữ lâu hơn theo quy định, khiến dữ liệu kiểm toán bị loại khi hết hạn.
Một service xóa số lượng lớn bản ghi Cassandra từng ngày, nhưng tombstone tích tụ làm truy vấn đọc dữ liệu hiện tại chậm đáng kể sau nhiều tháng.
Nhóm liên tục xóa và thêm phần tử trong collection lớn, khiến các truy vấn theo partition chạm nhiều tombstone và áp lực compaction tăng.
Ứng dụng dùng bảng time-series với TTL ngắn và cập nhật liên tục cùng partition, khiến tốc độ tạo tombstone cao hơn tốc độ dọn của cluster.
Đội rút gc_grace_seconds để giảm dung lượng nhưng một replica đã offline dài ngày trở lại với dữ liệu cũ, khiến nguy cơ dữ liệu đã xóa xuất hiện trở lại.
Một team xóa sự kiện chứa dữ liệu cá nhân rồi coi thao tác delete là xóa ngay mọi bản sao vật lý, trong khi SSTable và compaction còn vòng đời riêng.
Ứng dụng gửi truy vấn qua partition nhiều dữ liệu hết hạn, nhưng kết quả thực tế ít dòng trong khi hệ thống vẫn phải đọc và loại nhiều tombstone.
Nhóm đo dung lượng table sau khi xóa dữ liệu và dự kiến disk giảm tức thì, nhưng số SSTables chưa được compact khiến dung lượng vẫn cao hơn dự toán.
Một bảng dùng TWCS cho telemetry nhưng một số bản ghi được cập nhật muộn ngoài time window, khiến dữ liệu và tombstone không được dọn theo nhịp kỳ vọng.
Đội chuyển compaction strategy của bảng hot data mà không đánh giá tải đĩa và I/O khi compaction diễn ra, khiến latency đọc API tăng trong thời gian chuyển đổi.
Một service dùng TTL ngắn cho cache dữ liệu trên Cassandra nhưng API có hành vi đọc ngay sau khi hết hạn, khiến cache miss hàng loạt gây tải cho hệ thống nguồn.
Nhóm tạo bản ghi đánh dấu trạng thái deleted thay vì xóa, nhưng truy vấn API không lọc theo cờ này khiến người dùng vẫn thấy hồ sơ đã bị thu hồi.
Ứng dụng lưu đơn hàng kèm lịch sử trạng thái trong một partition, nhưng chỉ giữ cột trạng thái hiện tại bằng TTL khiến dữ liệu chính mất thông tin trước lịch sử.
Đội xử lý dữ liệu theo quy định lưu giữ khác nhau theo tenant, nhưng dùng default TTL chung cho bảng nên một số khách bị lưu quá hạn hoặc xóa quá sớm.
Một hệ thống xóa dữ liệu trên một datacenter trong lúc datacenter khác mất mạng lâu, khiến việc kiểm chứng trạng thái xóa sau khi khôi phục khó khăn.
Nhóm tạo job dọn partition cũ bằng nhiều lệnh delete lớn cùng lúc, khiến compaction và disk usage bùng lên trong cửa sổ bảo trì.
Ứng dụng dùng CassandraRepository để phân trang dữ liệu theo partition nhưng UI vẫn hiển thị số trang ngẫu nhiên kiểu SQL, khiến khách chọn trang 500 mà không có paging state tương ứng.
Đội lấy một trang kết quả bằng paging state của Cassandra, nhưng client truyền lại state sau khi đã thay đổi filter khiến dữ liệu bị thiếu hoặc trả sai thứ tự.
Một service đặt page size rất lớn cho báo cáo sự kiện, khiến driver nhận nhiều dữ liệu và bộ nhớ JVM tăng mạnh khi nhiều client cùng yêu cầu.
Nhóm gọi CassandraTemplate theo một partition chứa hàng triệu event rồi chuyển toàn bộ kết quả thành list, khiến request timeout dù API chỉ cần 100 dòng mới nhất.
Ứng dụng cho phép khách nhảy tới offset rất sâu trong lịch sử, nhưng Cassandra không cung cấp cơ chế skip rẻ như hệ SQL nên thời gian truy vấn tăng đột biến.
Đội xây endpoint paginated bằng paging state nhưng không kiểm tra state rỗng ở trang cuối, khiến client lặp lại trang cuối mãi không dừng.
Một API phân trang theo orderId và createdAt nhưng dữ liệu mới được chèn trong lúc người dùng đọc nhiều trang, khiến các trang có thể bị dịch chuyển theo thời điểm cập nhật.
Nhóm truyền paging state từ Cassandra lên URL công khai mà không kiểm soát việc gắn với filter và phiên bản API, khiến token từ phiên cũ gây lỗi hoặc trả dữ liệu ngoài mong đợi.
Ứng dụng trả cả tổng số bản ghi và một trang dữ liệu cho mỗi lần gọi, nhưng phép đếm trên nhiều partition làm request chậm hơn nhiều so với bản thân trang kết quả.
Đội sử dụng reactive paging với Flux Cassandra nhưng subscriber xử lý quá chậm, khiến các trang truy vấn tiếp theo tích tụ trong bộ nhớ ứng dụng.
Một service dùng CassandraRepository tìm tất cả giao dịch của một tài khoản nhưng không giới hạn page size, khiến khách có dữ liệu nhiều năm tạo phản hồi HTTP quá lớn.
Nhóm cấu hình page size ở driver và thêm LIMIT ở CQL nhưng không hiểu khác biệt giữa số hàng mỗi fetch và giới hạn tổng kết quả, khiến API trả thiếu dòng.
Ứng dụng tiếp nhận paging state được lưu lâu trong Redis, nhưng cluster đã nâng cấp schema và client không kiểm tra trạng thái token trước khi tiếp tục đọc.
Đội muốn hiển thị lịch sử theo ngày bằng nhiều bucket Cassandra, nhưng kết quả của từng partition được sắp đúng trong khi thứ tự chung giữa các bucket không được bảo đảm.
Nhóm chạy job export tuần tự từng partition với paging nhỏ, nhưng tốc độ bị giới hạn một luồng và thời gian hoàn thành vượt cửa sổ bảo trì.
Một ứng dụng truy vấn theo clustering range với LIMIT cố định nhưng page token bị sử dụng lại sau khi người dùng thay đổi sort direction, làm màn hình lặp dữ liệu.
Đội áp timeout 1 giây cho API Cassandra nhưng một số truy vấn phải đọc nhiều tombstone; retry cùng truy vấn liên tục gây thêm tải khi node đã quá bận.
Một service tạo PreparedStatement mới cho mỗi request có cùng CQL, khiến chi phí prepare và cache phía driver/server tăng trong lúc traffic bùng nổ.
Nhóm ghép tên bảng và điều kiện CQL theo tham số từ API, khiến truy vấn có thể thay đổi cấu trúc ngoài phạm vi đã cho phép và khó tận dụng prepared statements.
Ứng dụng triển khai nhiều pod Spring Boot mà mỗi pod tạo nhiều Cassandra sessions riêng, khiến số connections tới cluster vượt mức dự tính sau autoscaling.
Đội cấu hình contact points Cassandra bằng một node duy nhất và không thử khi node này chết, khiến pod mới không khởi tạo được session dù cluster còn node khỏe.
Một service Spring Boot dùng local datacenter name không khớp với topology Cassandra, khiến driver không chọn được node phù hợp và kết nối thất bại ở một vùng.
Nhóm triển khai cluster nhiều datacenter nhưng request tại vùng A bị định tuyến nhầm tới node vùng B vì cấu hình driver locality chưa phù hợp, khiến latency tăng mạnh.
Ứng dụng dùng Spring Data Cassandra trên Kubernetes nhưng không có policy xử lý hostname thay đổi khi node Cassandra được thay, khiến nhiều session mất kết nối trong đợt bảo trì.
Đội tăng số request đồng thời ở client mà không theo dõi in-flight requests trên driver, khiến các node Cassandra bị quá tải và lỗi timeout lan rộng.
Một service chọn speculative execution cho tất cả CQL requests, nhưng một nhóm mutation không thể được xem như đọc thuần nên phát sinh thêm tác động không mong đợi.
Nhóm bật retry tự động cho các counter updates sau timeout, khiến thống kê lượt truy cập tăng cao hơn số sự kiện thực tế đã xử lý.
Ứng dụng đo latency Cassandra ở mức trung bình thấp nhưng p99 tăng mạnh vào giờ cao điểm, trong khi dashboard không tách truy vấn theo bảng và partition size.
Đội tăng replication factor để cải thiện độ bền nhưng không đánh giá chi phí disk, repair và network traffic khi dữ liệu telemetry tăng nhanh.
Một cluster Cassandra chứa dữ liệu đa tenant nhưng một tenant gây truy vấn lớn không có quota hợp lý, khiến latency của các tenant nhỏ cũng tăng theo.
Nhóm muốn đánh giá cache của Cassandra qua metrics nhưng chỉ xem tỷ lệ cache hit, không đối chiếu số partition nóng và mức disk I/O trên node.
Ứng dụng gọi một CQL query chứa ALLOW FILTERING để giải quyết yêu cầu báo cáo khẩn, nhưng sau khi dữ liệu tăng mười lần API bắt đầu timeout liên tục.
Đội cho rằng thêm node luôn giải quyết được truy vấn theo partition key rất nóng, nhưng một partition lớn vẫn được phục vụ bởi số replica có giới hạn.
Một service gửi hàng trăm truy vấn Cassandra đồng thời trong một request báo cáo rồi đợi tất cả kết quả, khiến pool tài nguyên bị chiếm khi khách hàng tải nhiều báo cáo.
Nhóm lên lịch repair và compaction nặng cùng lúc với job export toàn bảng, khiến băng thông đọc/ghi và CPU tranh chấp làm hệ thống khách hàng chậm.
Ứng dụng dùng cùng session Cassandra cho nghiệp vụ online và ETL khối lượng lớn mà không kiểm soát rate limit, khiến batch tiêu thụ tài nguyên của request tức thời.
Đội thêm bảng denormalized cho một query mới nhưng không dự báo write amplification, khiến mỗi sự kiện cần cập nhật nhiều bảng và throughput ghi giảm.
Một dashboard quan sát chỉ theo dõi lỗi HTTP của Spring Boot mà không đo read/write timeout của Cassandra driver, khiến sự cố database bị nhận nhầm là lỗi API.
Nhóm cấu hình query logging đầy đủ tham số CQL cho việc chẩn đoán nhưng payload chứa dữ liệu cá nhân, khiến thông tin nhạy cảm xuất hiện trong log tập trung.
Ứng dụng triển khai sang Cassandra cluster production có bật TLS nhưng cấu hình Spring Boot client còn dùng connection không mã hóa từ môi trường test.
Đội cấp quyền Cassandra role cho keyspace chung quá rộng, khiến một microservice chỉ đọc báo cáo có thể sửa dữ liệu của luồng giao dịch khác.
Một dịch vụ lưu tenantId trong primary key nhưng không kiểm tra quyền người gọi trước khi tạo CQL, khiến khách có thể truy vấn partition của tenant khác bằng cách đổi ID.
Nhóm thay certificate trên Cassandra nodes nhưng truststore của ứng dụng không được cập nhật, khiến session hiện tại còn chạy mà pod khởi động lại không kết nối được.
Ứng dụng lưu thông tin đăng nhập Cassandra trong application.yml của JAR phát hành, khiến credential sản xuất có mặt trong artifact được chia sẻ với nhiều nhóm.
Đội xoay mật khẩu Cassandra của service account nhưng driver session chưa làm mới thông tin xác thực, khiến một phần pod bị lỗi khi mở kết nối mới.
Một service có dữ liệu cá nhân trong bảng Cassandra dùng TTL để hết hạn, nhưng chính sách pháp lý yêu cầu ghi dấu việc xóa và phạm vi replica đã được xử lý.
Nhóm cấu hình audit log cho truy vấn quản trị Cassandra nhưng ứng dụng thay đổi schema ngoài giờ bảo trì mà không có dấu vết phiên bản triển khai tương ứng.
Ứng dụng sử dụng Cassandra ở hai vùng chịu quy định data residency khác nhau, nhưng keyspace replication strategy sao chép dữ liệu khách sang vùng không được phép.
Đội phát triển migration Cassandra CQL trong CI nhưng test chỉ chạy trên một node local, khiến thay đổi replication và consistency không được đánh giá trước production.
Một service thêm cột vào bảng Cassandra rồi deploy code mới trước khi toàn bộ cluster có schema agreement, khiến một phần request đọc/ghi bị lỗi trong cửa sổ chuyển đổi.
Nhóm đổi tên cột đang được Spring Data Cassandra mapping nhưng các pod phiên bản cũ vẫn xử lý dữ liệu, khiến rolling deployment gặp lỗi tương thích schema.
Ứng dụng cần sửa kiểu dữ liệu primary key sau khi đã phát sinh hàng tỷ rows, nhưng nhóm dự kiến dùng một lệnh alter trực tiếp và không đánh giá phương án di trú dữ liệu.
Đội tạo bảng Cassandra mới để phục vụ một query khác nhưng backfill đọc dữ liệu từ bảng nguồn quá nhanh, khiến latency online tăng đột biến trong đợt triển khai.
Một service dual-write sang bảng cũ và mới khi chuyển mô hình partition key, nhưng một số request chỉ thành công ở một bảng làm hai API trả số liệu lệch nhau.
Nhóm sử dụng CassandraSchemaAction tự động tạo bảng cho Spring Boot dev nhưng production quản lý schema riêng, khiến tích hợp test không phản ánh thứ tự migration thực tế.
Ứng dụng nâng phiên bản Java driver cùng Spring Data Cassandra nhưng cấu hình datacenter và TLS cũ không còn tương thích, khiến pod khởi tạo session thất bại.
Đội dùng Testcontainers Cassandra cho integration test nhưng container khởi động với replication factor đơn giản, khiến kịch bản quorum và mất replica không được kiểm chứng.
Một repository test chạy trên Cassandra giả lập bằng dữ liệu vài hàng, khiến truy vấn không dùng partition key vẫn được chấp nhận ở thử nghiệm nhưng lỗi khi chạy cluster production.
Nhóm tạo dữ liệu kiểm thử với partition keys phân phối đều, nhưng production có một tenant lớn khiến benchmark không thể hiện hotspot theo tải thực.
Ứng dụng dùng CassandraTemplate trong test nhưng không kiểm thử các trường UDT, collections và TTL, khiến lỗi mapping chỉ xuất hiện khi đọc hồ sơ từ dữ liệu cũ.
Đội sử dụng một keyspace test chung cho nhiều CI jobs song song và mỗi job dọn sạch bảng khi hoàn thành, khiến những test khác thất bại ngẫu nhiên.
Một bộ test tích hợp Spring Boot kiểm tra CassandraRepository.save rồi đọc ngay ở cùng session, nhưng production có consistency thấp và hai datacenter nên hành vi không hoàn toàn giống.
Nhóm thử thao tác delete bằng cách kiểm tra ngay kết quả đọc, nhưng không mô phỏng replica offline dài ngày và khôi phục khi tombstone đã được dọn.
Ứng dụng kiểm thử phân trang với 20 records nên không tạo paging state tiếp theo, khiến lỗi hiển thị trang thứ hai chỉ được phát hiện khi dữ liệu thật tăng.
Đội QA đánh giá query latency qua cluster Cassandra một node trên laptop, nhưng production có topology nhiều datacenter và retry nên p99 khác biệt lớn.
Một service xử lý cập nhật cạnh tranh nhưng integration test chỉ thực hiện tuần tự trong một thread, khiến hai worker có thể ghi đè trạng thái của nhau sau deploy.
Nhóm tạo test cho LWT với IF NOT EXISTS khi không có cạnh tranh, nhưng không thử hai instance đồng thời cùng tạo một giao dịch nên hành vi xung đột chưa được xác minh.
Ứng dụng cần xử lý counter theo sự kiện Kafka nhưng test không mô phỏng redelivery sau Cassandra write timeout, khiến thống kê tăng trùng trong production.
Đội đổi chiến lược compaction cho bảng có TTL nhưng benchmark chỉ kiểm tra throughput ghi, không quan sát tombstone và read latency theo thời gian.
Nhóm tạo API lấy lịch sử theo ngày bằng nhiều time buckets nhưng bài test chỉ có dữ liệu ở một bucket, khiến lỗi sắp xếp toàn cục chưa được phát hiện.
Một hệ thống muốn thử khôi phục từ backup Cassandra nhưng chỉ khởi động lại service Spring Boot, khiến khả năng phục hồi dữ liệu và schema sau sự cố chưa được kiểm chứng.
Đội cập nhật DataStax Java driver nhưng pipeline chỉ chạy unit test mock CassandraOperations, khiến lỗi cấu hình policy và prepare CQL chỉ xuất hiện sau phát hành.
Một service gọi REST trả kết quả Cassandra theo tenant và page token, nhưng security test chỉ kiểm tra tenant ở trang đầu nên token từ tenant khác có thể được chấp nhận mà chưa bị phát hiện.
Nhóm vận hành cần rollback phiên bản Spring Boot sau khi đã đổi schema Cassandra, nhưng không thử đọc dữ liệu mới bằng entity mapping của phiên bản cũ nên kế hoạch rollback thiếu tin cậy.
