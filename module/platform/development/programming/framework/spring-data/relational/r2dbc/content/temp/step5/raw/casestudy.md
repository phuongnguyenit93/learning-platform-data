Một dịch vụ đặt hàng chuyển từ JDBC sang Spring Data R2DBC, nhưng cấu hình kết nối vẫn dùng URL kiểu JDBC khiến ConnectionFactory không khởi tạo được khi deploy.
Một ứng dụng WebFlux tích hợp PostgreSQL qua R2DBC trên máy phát triển, nhưng image production thiếu driver tương ứng và lỗi chỉ xuất hiện khi tạo kết nối đầu tiên.
Một nhóm đổi database từ PostgreSQL sang MariaDB nhưng giữ cách xử lý tham số và kiểu dữ liệu của dialect cũ, khiến một số lệnh SQL không chạy trên môi trường mới.
Một hệ thống chạy R2DBC với kết nối TLS bắt buộc, nhưng certificate của server được xoay còn client sử dụng truststore cũ nên các request mới thất bại.
Một dịch vụ quản lý đơn có pool kết nối R2DBC rất nhỏ, khiến khi WebFlux nhận nhiều yêu cầu đồng thời thời gian chờ lấy kết nối vượt SLA dù SQL chạy nhanh.
Một ứng dụng cấu hình quá nhiều kết nối R2DBC cho mỗi replica, khiến khi autoscaling tổng số connection vượt giới hạn của database và các Pod mới không thể phục vụ.
Một nhóm dùng ConnectionFactory riêng cho dữ liệu khách hàng và báo cáo, nhưng repository quản lý giao dịch được nối nhầm factory nên đọc dữ liệu từ schema khác.
Một hệ thống dùng cơ sở dữ liệu managed thay đổi endpoint sau failover, nhưng các kết nối cũ trong pool bị lỗi liên tiếp và client không khôi phục như đội trực mong đợi.
Một ứng dụng khai báo R2DBC URL trỏ vào địa chỉ localhost khi chạy container, khiến tiến trình không kết nối được tới database dù cấu hình chạy bằng IDE thành công.
Một nhóm phát triển dùng profile test với database nhúng, nhưng production dùng kiểu dữ liệu không được test hỗ trợ nên một truy vấn hoạt động khác giữa hai môi trường.
Một dịch vụ gặp lỗi xác thực sau khi credential database được xoay, nhưng pool tiếp tục giữ các kết nối cũ và việc tạo kết nối mới trả lỗi gián đoạn.
Một ứng dụng dùng proxy database giới hạn thời gian sống connection, nhưng R2DBC pool trả lại các connection đã bị đóng khiến lỗi xuất hiện ở request đầu sau thời gian rảnh.
Một hệ thống có nhiều API đọc nhỏ nhưng cùng dùng connection pool với tác vụ báo cáo nặng, khiến truy vấn báo cáo chiếm hết connection và ảnh hưởng đường thanh toán.
Một nhóm giả định kết nối R2DBC mặc nhiên không tốn thread, nhưng driver phải chờ mạng quá lâu và request vẫn tích tụ trong hàng đợi pool khi dependency chậm.
Một dịch vụ sử dụng ConnectionFactory với schema mặc định không đúng, khiến lệnh tìm bảng theo tên ngắn thành công ở staging nhưng trả lỗi không tồn tại ở production.
Một hệ thống có các database replica dành cho đọc và một primary dành cho ghi, nhưng cấu hình R2DBC của service không phân biệt nguồn truy cập nên các câu INSERT bị gửi tới replica chỉ đọc.
Một ứng dụng khai báo hai ConnectionFactory cho dữ liệu khách hàng và báo cáo, nhưng repository và DatabaseClient được inject khác nguồn khiến cùng workflow đọc hai schema không như dự kiến.
Một nhóm mở cổng mạng database chỉ cho subnet cũ, khiến các Pod mới trong vùng autoscaling không kết nối được dù DNS và credential đều đúng.
Một hệ thống chạy database cùng cloud region với phần lớn service nhưng đặt một nhóm worker xa khu vực, khiến latency của từng roundtrip R2DBC tăng rõ trong báo cáo cuối ngày.
Một dịch vụ ghi nhận thời gian chờ connection pool tăng cao nhưng chỉ giám sát thời gian câu SQL, khiến đội trực kết luận sai rằng database query vẫn ổn.
Một ứng dụng cấu hình timeout kết nối dài hơn deadline từ API gateway, khiến request đã bị hủy ở gateway nhưng acquisition vẫn còn chờ tài nguyên phía database.
Một nhóm chạy nhiều môi trường với cùng username database và quyền rộng, khiến cấu hình sai schema có thể cho ứng dụng staging truy cập bảng nghiệp vụ production.
Một hệ thống nhập dữ liệu theo lô mở nhiều subscription ghi song song, khiến pool bị chiếm gần hết bởi batch job và người dùng không còn kết nối để tra cứu.
Một dịch vụ có kết nối R2DBC qua load balancer mạng, nhưng khi node database bị thay thế các transaction dài bị hủy và ứng dụng không phân loại đúng lỗi tạm thời.
Một ứng dụng bật logging chi tiết của driver để điều tra lỗi, nhưng connection options và tham số SQL chứa thông tin nhạy cảm xuất hiện trong hệ thống log chung.
Một nhóm cấu hình R2dbcTransactionManager cho một ConnectionFactory, nhưng truy vấn ở service khác dùng factory thứ hai khiến giả định giao dịch chung giữa các thao tác không đúng.
Một ứng dụng quản lý khách hàng dùng @Table để ánh xạ entity, nhưng tên bảng trong database có tiền tố riêng còn entity giữ tên mặc định nên repository không tìm được bảng.
Một dịch vụ đổi tên Java property customerCode, nhưng dữ liệu và cột SQL vẫn dùng tên legacy nên thao tác đọc entity không còn nhận mã khách chính xác.
Một hệ thống sử dụng @Column để chỉ định cột tên chứa dấu gạch dưới, nhưng custom query dùng tên Java property và trả kết quả thiếu dữ liệu.
Một nhóm để khóa chính ở trường @Id kiểu Long, nhưng bảng thật dùng khóa UUID nên quá trình tạo entity từ kết quả truy vấn xảy ra lỗi chuyển kiểu.
Một ứng dụng tạo ID ở tầng client nhưng bảng database cũng sinh ID tự động, khiến một số entity được xem là mới hoặc đã tồn tại không đúng với mong đợi của luồng save.
Một dịch vụ dùng @Version để bảo vệ cập nhật số lượng tồn, nhưng hai request giữ cùng entity cũ và một request gặp optimistic locking failure ngay trong đợt flash sale.
Một hệ thống lưu số tiền dưới dạng số dấu phẩy động trong entity, khiến thao tác tính khuyến mãi và đối soát tài chính có sai số khi dữ liệu qua R2DBC mapping.
Một nhóm thêm cột NOT NULL trong migration nhưng dữ liệu cũ vẫn thiếu giá trị, khiến entity mới đọc được nhưng lần ghi sau bị database từ chối.
Một ứng dụng dùng enum trạng thái đơn hàng được lưu dưới dạng chuỗi, nhưng dữ liệu lịch sử chứa giá trị enum đã bỏ khỏi Java nên converter không đọc được.
Một dịch vụ nhận timestamp từ nhiều timezone, nhưng entity ánh xạ vào LocalDateTime và không lưu thông tin múi giờ khiến thứ tự giao dịch hiển thị sai.
Một hệ thống đổi cột kiểu JSON sang cấu trúc nested, nhưng custom converter của Spring Data R2DBC vẫn mong format trước đó và lỗi chỉ xảy ra trên một phần dữ liệu.
Một nhóm dùng một entity class cho hai bảng có schema gần giống nhau, nhưng thuộc tính bắt buộc của bảng thứ nhất vắng mặt ở bảng thứ hai gây lỗi khi tái sử dụng mapper.
Một ứng dụng ánh xạ khóa chính tổng hợp gồm hai cột như một @Id đơn giản, khiến phương thức findById không biểu diễn được đầy đủ định danh nghiệp vụ của bảng.
Một hệ thống lưu quan hệ khách hàng và địa chỉ ở hai bảng, nhưng đội phát triển kỳ vọng R2DBC tự lazy-load địa chỉ khi truy cập property entity như một ORM truyền thống.
Một nhóm định nghĩa trường List trong entity đơn hàng và coi đó là quan hệ một-nhiều tự động, khiến việc lưu order không tạo các dòng order_item như thiết kế nghiệp vụ.
Một ứng dụng có cột is_active nullable nhưng entity dùng boolean nguyên thủy, khiến việc phân biệt trạng thái thiếu dữ liệu và false không còn rõ trong API.
Một dịch vụ lưu dữ liệu số dưới nhiều kiểu SQL khác nhau ở các environment, khiến conversion thành BigDecimal cho báo cáo bị lỗi ở một bảng staging.
Một nhóm dùng constructor bất biến cho entity với nhiều tham số, nhưng tên cột trả về từ query không khớp tên property khiến Spring Data không dựng được đối tượng.
Một hệ thống đặt tên cột theo quy tắc viết hoa có dấu trích dẫn trong database, nhưng tên mà naming strategy suy ra không khớp khiến thao tác INSERT báo không có cột.
Một ứng dụng thêm field trạng thái mới trong entity mà chưa chạy migration schema, khiến lệnh ghi theo repository bắt đầu thất bại sau khi rollout bản mới.
Một dịch vụ đọc entity từ truy vấn projection thiếu một trường bắt buộc của constructor, khiến mapping chỉ lỗi trên endpoint danh sách chứ không lỗi ở findById.
Một nhóm dùng converter riêng cho thông tin được mã hóa, nhưng một đường update bằng DatabaseClient ghi trực tiếp dạng chuỗi thuần khiến lần đọc qua repository không giải mã được.
Một hệ thống thay đổi kiểu dữ liệu cột account_id từ integer sang varchar, nhưng cache entity và contract API còn giả định số khiến dữ liệu chuyển đổi không đồng nhất.
Một ứng dụng có cột version do database trigger cập nhật nhưng entity cũng dùng @Version, khiến điều kiện cập nhật theo phiên bản và giá trị thực tế không trùng.
Một nhóm lưu địa chỉ khách trong một cột JSON nhưng UI cần tìm theo phường, khiến truy vấn repository theo thuộc tính Java nested không hoạt động như giả định về cột quan hệ.
Một dịch vụ ánh xạ trường createdAt chỉ đọc do database sinh giá trị, nhưng đường lưu entity vẫn ghi null vào cột đó và không nhận timestamp mặc định.
Một hệ thống sử dụng khóa định danh được cấp bằng sequence database, nhưng luồng tạo entity không nhận giá trị ID mới trước khi gửi thông báo cho service khác.
Một ứng dụng lưu metadata mở rộng bằng custom converter, nhưng khi schema JSON của nguồn đối tác thay đổi các document cũ và mới không còn cùng biểu diễn Java.
Một nhóm triển khai reactive CrudRepository cho đơn hàng, nhưng component khác inject repository kiểu blocking tương tự và event loop bị giữ bởi đường truy cập dữ liệu cũ.
Một dịch vụ dùng ReactiveCrudRepository.findAll trên bảng giao dịch hàng triệu dòng, khiến endpoint yêu cầu collectList và tạo áp lực heap rất lớn.
Một ứng dụng gọi save trên entity có ID đã tồn tại nhưng hàng tương ứng vừa bị xóa, khiến lệnh cập nhật không tìm được bản ghi và API chưa có cách phân loại lỗi phù hợp.
Một nhóm dùng findByEmail trả Mono một khách hàng, nhưng database không có unique constraint nên dữ liệu email trùng làm đường truy vấn không còn đáp ứng giả định một kết quả.
Một hệ thống truy vấn theo trạng thái qua repository method, nhưng tên property đã đổi trong entity còn tên method cũ nên repository lỗi khi sử dụng.
Một ứng dụng đặt phương thức findTopByOrderByCreatedAtDesc cho bản ghi mới nhất, nhưng nhiều dòng có cùng timestamp khiến lựa chọn kết quả không ổn định khi dữ liệu tăng.
Một dịch vụ dùng derived query theo một cột chưa có index, khiến endpoint vẫn phản hồi nhanh ở test nhỏ nhưng chậm bất thường khi production có nhiều đơn.
Một nhóm muốn tìm đơn theo cả người dùng và khoảng ngày, nhưng repository method chỉ lọc mã người dùng rồi service lọc thêm trong bộ nhớ khiến tải database và mạng cao.
Một ứng dụng dùng repository.deleteById trong luồng xử lý đặt hàng, nhưng một bản ghi liên quan có foreign key khiến database từ chối xóa dù entity đã được tìm thấy.
Một hệ thống gửi HTTP 200 ngay sau khi tạo Mono lưu entity nhưng không subscribe hoặc return publisher, khiến request kết thúc mà SQL INSERT chưa từng được thực thi.
Một nhóm gọi repository.save hai lần trên cùng một publisher lạnh qua hai subscriptions, khiến thao tác ghi có thể chạy lại và phát sinh xung đột khóa hoặc tác dụng phụ.
Một dịch vụ dùng findById rồi save để tăng số lượng tồn, nhưng hai request đồng thời cùng đọc giá trị cũ và làm thất lạc một lần tăng.
Một ứng dụng dùng repository.count để thống kê đơn và findAll để trả danh sách, nhưng hai phép truy vấn diễn ra ở thời điểm khác nhau nên tổng số và kết quả trang không khớp.
Một nhóm khai báo query method trả Flux<Order> cho danh sách tìm kiếm nhưng controller chuyển ngay thành List, khiến khả năng streaming bị mất và bộ nhớ tăng khi khách yêu cầu nhiều dữ liệu.
Một hệ thống yêu cầu tìm lịch sử giao dịch theo thứ tự ngày, nhưng repository query không có ORDER BY nên thứ tự của các kết quả thay đổi giữa các lần gọi.
Một ứng dụng chuyển từ lưu đơn bằng JDBC sang reactive repository, nhưng một service cũ vẫn giữ phương thức trả entity đồng bộ và dùng block trong luồng request.
Một nhóm khai báo @Query trên reactive repository và dùng tham số tên khác với placeholder SQL, khiến chỉ trường hợp có bộ lọc thứ hai phát sinh lỗi binding.
Một dịch vụ dùng repository projection trả tóm tắt tài khoản, nhưng query alias không tương ứng property của DTO khiến màn hình nhận nhiều trường null.
Một hệ thống cho phép người dùng tìm theo tên sản phẩm không giới hạn kết quả, nhưng reactive repository phát quá nhiều dòng và API consumer xử lý không kịp.
Một ứng dụng sử dụng deleteAll để dọn test data nhưng test vô tình dùng ConnectionFactory production, khiến dữ liệu đang vận hành có nguy cơ bị xóa.
Một nhóm cập nhật entity từ DTO chứa giá trị null ở các trường chưa gửi, khiến thao tác save vô tình thay các cột hiện có bằng null thay vì giữ nguyên.
Một dịch vụ thực hiện query theo email đã chuẩn hóa nhưng database lưu nhiều cách viết khác nhau, khiến người dùng đăng nhập bằng chữ hoa không tìm được tài khoản cũ.
Một hệ thống có hai bảng lưu loại đơn hàng khác nhau nhưng cùng tên entity, khiến repository của module sau được cấu hình @Table sai và ghi sang bảng không mong muốn.
Một ứng dụng cần cập nhật một field của dòng báo cáo nhưng gọi save toàn entity đọc từ snapshot cũ, khiến những cột vừa được tiến trình khác sửa bị ghi đè.
Một nhóm dùng R2dbcEntityTemplate cho truy vấn động theo nhiều tùy chọn, nhưng một điều kiện được ghép sai thứ tự khiến các bản ghi thuộc tenant khác lọt vào danh sách.
Một dịch vụ tìm nhiều order IDs qua R2dbcEntityTemplate, nhưng danh sách đầu vào rất lớn gây query dài và tăng thời gian thực thi ở database.
Một hệ thống cập nhật trạng thái invoice theo điều kiện hiện tại bằng template, nhưng không kiểm tra số dòng bị ảnh hưởng nên API báo thành công dù trạng thái không phù hợp.
Một ứng dụng dùng R2dbcEntityTemplate để lấy dữ liệu phân trang, nhưng phần query đếm tổng chưa cùng điều kiện lọc và UI hiển thị số trang sai.
Một nhóm dùng R2dbcEntityTemplate để select dữ liệu JSON vào custom DTO, nhưng các property nested không được converter nhận diện giống mapping entity.
Một dịch vụ cập nhật hàng loạt thông qua template ở nhiều điều kiện, nhưng khi một điều kiện lọc bị bỏ trống thao tác tác động tới nhiều dòng hơn dự kiến.
Một hệ thống dùng R2dbcEntityTemplate cho cả bảng giao dịch và bảng lưu trữ, nhưng Entity class có @Table trỏ bảng cũ nên luồng chuyển dữ liệu không đọc đúng nơi.
Một nhóm dùng DatabaseClient để chạy SQL tự viết, nhưng tên alias trong SELECT khác field của mapper khiến kết quả doanh thu bị gán vào sai thuộc tính.
Một ứng dụng ghép điều kiện ORDER BY từ tham số HTTP bằng chuỗi trực tiếp, khiến người dùng có thể điều khiển thành phần SQL ngoài danh sách cột được phép.
Một dịch vụ sử dụng named parameters trong DatabaseClient nhưng truyền tham số kiểu thời gian không phù hợp với driver, khiến truy vấn lọc ngày chỉ lỗi trên một database cụ thể.
Một nhóm viết SQL JOIN giữa orders và order_items nhưng map mỗi row thành Order đầy đủ, khiến một đơn xuất hiện lặp nhiều lần và tổng số đơn bị đếm sai.
Một hệ thống sử dụng LEFT JOIN để hiển thị khách chưa có đơn, nhưng đặt điều kiện của bảng đơn trong WHERE khiến khách không có giao dịch bị loại khỏi báo cáo.
Một ứng dụng xây native query dùng cú pháp UPSERT riêng của một database, nhưng khi chuyển sang một R2DBC driver khác lệnh đó không còn hợp lệ.
Một dịch vụ dùng DatabaseClient để update theo ID, nhưng không kiểm tra affected rows nên một yêu cầu sửa bản ghi vừa bị xóa được coi là đã hoàn thành.
Một nhóm thực hiện SQL INSERT vào bảng có generated ID qua DatabaseClient, nhưng phần mapping kết quả không lấy được ID cần gắn vào thông báo nghiệp vụ.
Một hệ thống đọc một Result từ DatabaseClient rồi thao tác với đối tượng sau khi luồng kết quả đã đóng, khiến truy cập dữ liệu row không còn hợp lệ trong callback khác.
Một ứng dụng dùng query chạy trên bảng lớn nhưng thiếu LIMIT ở endpoint gợi ý tìm kiếm, khiến server phát hàng triệu rows dù người dùng chỉ muốn mười đề xuất.
Một nhóm viết SQL theo kiểu PostgreSQL trong query thủ công và ghép dấu placeholder theo driver đó, khiến chạy integration test bằng database khác bị lỗi cú pháp.
Một dịch vụ nhập dữ liệu từ CSV bằng DatabaseClient từng dòng, khiến hàng chục nghìn roundtrips qua mạng làm tiến trình nhập kéo dài hơn lịch cho phép.
Một hệ thống dùng update một số cột qua DatabaseClient nhưng service khác vẫn giữ entity đã đọc trước đó, khiến lần save sau có nguy cơ ghi đè cột vừa chỉnh.
Một ứng dụng cần lấy dữ liệu phân cấp qua recursive CTE, nhưng query trả nhiều hàng cùng root và mapper hiện tại không tái tạo được cấu trúc cây mong đợi.
Một nhóm dùng điều kiện LIKE để tìm mô tả sản phẩm trong database lớn, nhưng không có chiến lược index phù hợp nên SQL chạy lâu dù R2DBC không chặn event loop.
Một dịch vụ trả báo cáo tổng hợp qua SQL window functions, nhưng mapping DTO không xử lý kiểu số lớn và bị overflow khi dữ liệu nhiều kỳ được cộng dồn.
Một hệ thống chạy SQL SELECT từ replica đọc rồi ngay lập tức UPDATE qua primary, nhưng dữ liệu đọc bị trễ và nghiệp vụ ghi dựa trên snapshot không còn chính xác.
Một ứng dụng dùng custom SQL để cập nhật bảng nhạy cảm, nhưng không đưa tenant_id vào điều kiện WHERE khiến request có thể thay đổi dòng của khách hàng khác.
Một nhóm dùng DatabaseClient trong phần điều tra lỗi và log toàn bộ bind values, khiến thông tin cá nhân và secret từ truy vấn xuất hiện trong log được nhiều nhóm đọc.
Một dịch vụ chuyển điểm thưởng giữa hai tài khoản bằng hai repository.save độc lập, nhưng lần ghi thứ hai thất bại khiến tổng điểm không còn cân bằng.
Một ứng dụng đặt @Transactional trên method reactive nhưng thực hiện một lời gọi save bằng subscribe thủ công ở bên ngoài publisher trả về, khiến thao tác đó không theo vòng đời transaction dự kiến.
Một nhóm dùng R2dbcTransactionManager nhưng một nhánh nghiệp vụ vẫn truy cập bằng JDBC Connection, khiến nhóm tưởng cả hai nguồn dữ liệu được rollback cùng nhau.
Một hệ thống đặt transaction ở service method trả Mono nhưng lỗi xuất hiện sau khi subscription bị hủy, khiến đội vận hành không biết phần ghi đã commit hay bị rollback.
Một dịch vụ dùng TransactionalOperator cho chuỗi thao tác tạo đơn và giảm tồn kho, nhưng một side effect gọi API giao vận bên trong chuỗi có thể chạy lại khi transaction retry.
Một ứng dụng cần ghi lịch sử thanh toán khi cập nhật số dư, nhưng audit được gửi bất đồng bộ qua publisher không gắn với transaction khiến hai trạng thái không đồng bộ.
Một nhóm áp dụng @Transactional cho method trả void khởi động xử lý reactive, khiến transaction không bao trùm những lệnh SQL chạy sau khi method kết thúc.
Một hệ thống giữ connection trong transaction để đọc hàng trăm nghìn rows, khiến các API ngắn khác xếp hàng chờ trong pool và phản hồi chậm dù không lock cùng bảng.
Một ứng dụng tạo hai truy vấn song song trong cùng reactive transaction, nhưng việc điều phối nhiều thao tác trên một connection làm kết quả khác dự đoán về khả năng song song.
Một dịch vụ dùng isolation level mặc định khi đọc tồn kho rồi cập nhật, nhưng hai giao dịch đồng thời làm phép kiểm tra số lượng không còn phù hợp trạng thái tại lúc commit.
Một nhóm xây retry khi transaction gặp deadlock, nhưng trong callback còn gửi email xác nhận nên một đơn hợp lệ có thể khiến khách nhận nhiều email.
Một ứng dụng dùng onErrorResume để biến lỗi ghi SQL thành Mono.empty bên trong transaction, khiến chuỗi hoàn tất không còn thể hiện thất bại nghiệp vụ theo dự tính.
Một hệ thống nhận timeout ở thời điểm COMMIT qua R2DBC, nhưng API không biết giao dịch đã được ghi chưa và retry tạo đơn mới có thể làm trùng dữ liệu.
Một nhóm dùng optimistic locking với @Version cho tồn kho nhưng không xử lý lỗi conflict ở tầng API, khiến request đồng thời bị trả HTTP 500 như lỗi hạ tầng.
Một dịch vụ cập nhật trạng thái đơn bằng SQL custom không có điều kiện version, khiến hàng ghi bị thay đổi mà cơ chế optimistic locking của repository không phát hiện.
Một ứng dụng đọc đơn bằng replica rồi chuyển tiền trên primary, nhưng độ trễ replication khiến giao dịch được xác nhận theo trạng thái đơn đã cũ.
Một hệ thống dùng transaction DB để ghi đơn rồi phát sự kiện Kafka trước commit, khiến consumer có thể nhận sự kiện cho dữ liệu sẽ bị rollback.
Một nhóm mở transaction cho bước gọi HTTP đối tác có độ trễ cao, khiến connection DB bị giữ lâu và số lượng giao dịch chờ tăng khi đối tác chậm.
Một dịch vụ cần kiểm tra uniqueness của mã đơn trước khi INSERT, nhưng hai request đồng thời cùng vượt qua bước kiểm tra và một request gặp vi phạm unique constraint.
Một ứng dụng ghi hai bảng thuộc hai database khác nhau trong một workflow, nhưng nhóm nghiệp vụ cho rằng một R2dbcTransactionManager tự bảo đảm atomicity xuyên cả hai.
Một hệ thống có method @Transactional gọi method khác trong cùng object thông qua self-invocation, khiến đội phát triển kỳ vọng advice giao dịch áp dụng giống khi gọi qua Spring proxy.
Một dịch vụ dùng TransactionalOperator áp lên nhánh xử lý nhưng một phép ghi được tạo ở publisher khác không được compose vào nhánh đó, khiến audit thiếu sau khi request thành công.
Một nhóm hủy HTTP request khi client disconnect, nhưng transaction reactive vẫn đang thực thi một lệnh mutation và không rõ tác dụng phụ đã được database chấp nhận hay chưa.
Một ứng dụng lưu đơn cùng các item trong transaction, nhưng khi một item vi phạm foreign key toàn bộ chuỗi lỗi và người dùng chỉ nhận thông báo chung không nêu item.
Một hệ thống dùng một connection cho transaction và thực hiện nhiều nested service calls, nhưng một service cố tạo giao dịch với cấu hình khác khiến ranh giới commit khó dự đoán.
Một ứng dụng WebFlux gọi repository reactive rồi chặn bằng block ở controller, khiến các event-loop threads bị giữ và throughput giảm dù driver R2DBC không chặn kiểu JDBC.
Một nhóm dùng map để xử lý Mono tìm tài khoản nhưng callback chạy CPU nặng hàng trăm mili giây, khiến các request khác cùng event loop bị tăng latency.
Một dịch vụ tạo Mono từ query nhưng return trước khi subscription được tạo ở một nhánh nghiệp vụ, khiến endpoint trả dữ liệu mặc định mà truy vấn không bao giờ chạy.
Một hệ thống dùng cache() trên một publisher query và kỳ vọng mỗi request luôn lấy bản ghi mới nhất, khiến người dùng thấy trạng thái cũ sau các lần cập nhật.
Một ứng dụng zip hai Mono truy vấn độc lập, nhưng một Mono không có dữ liệu nên toàn bộ kết quả không được phát và màn hình trống dù nhánh còn lại hợp lệ.
Một nhóm dùng flatMap với concurrency không giới hạn để ghi hàng chục nghìn đơn, khiến hàng đợi connection pool và số lệnh chờ database tăng mạnh.
Một hệ thống xử lý Flux đơn hàng rồi collectList trước khi trả JSON, khiến API dùng bộ nhớ theo số dòng thay vì phát kết quả dần cho client.
Một dịch vụ áp dụng backpressure ở subscriber nhưng query SQL trả tập kết quả trung gian rất lớn, khiến tài nguyên database vẫn bị tiêu thụ nặng ngoài kỳ vọng.
Một ứng dụng dùng publishOn chuyển scheduler trong luồng xử lý, nhưng code lấy tenant ID từ ThreadLocal khiến đường truy cập R2DBC sau đó chọn sai schema.
Một nhóm dùng Reactor Context để mang correlation ID nhưng một callback tự tạo thread và đọc ThreadLocal cũ, khiến log outbound SQL không còn cùng trace của request.
Một hệ thống đọc Flux dữ liệu từ database và gửi qua Server-Sent Events, nhưng client mạng chậm làm tiến trình giữ tài nguyên truy vấn lâu hơn thời gian dùng dự kiến.
Một ứng dụng dùng Flux.take để lấy vài bản ghi đầu rồi hủy subscription, nhưng đội vận hành không đo việc giải phóng connection và cursor phía database sau cancellation.
Một dịch vụ lồng nhiều reactive repository calls trong vòng for với subscribe thủ công, khiến controller xác nhận thành công trước khi các lệnh ghi hoàn tất hoặc thất bại.
Một nhóm áp dụng retryWhen cho thao tác INSERT không idempotent sau lỗi mạng, khiến lần thử lại có thể tạo bản ghi hoặc sự kiện trùng khi lần đầu đã được commit.
Một ứng dụng dùng switchIfEmpty để tạo khách hàng khi findByEmail không có kết quả, nhưng hai request đồng thời đều cố tạo khách với cùng email.
Một hệ thống kết hợp repository reactive với một JDBC library kiểm tra quyền trong filter WebFlux, khiến thread của request bị chặn bởi truy vấn JDBC dù các phần còn lại là reactive.
Một dịch vụ dùng onErrorContinue để bỏ qua dòng dữ liệu lỗi trong batch, khiến số lần ghi thất bại không được kiểm đếm đầy đủ trong báo cáo đối soát.
Một nhóm đặt timeout lên Mono save nhưng không phân biệt hủy publisher với việc server đã hoàn tất mutation, khiến retry ở tầng API làm phát sinh xử lý lại.
Một ứng dụng sử dụng Flux.share cho dữ liệu từ database tới hai subscriber, nhưng một subscriber đến muộn và không nhận các hàng đã được phát trước đó.
Một hệ thống tạo nhiều request reactive đến cùng tenant nhưng mỗi request thực hiện N truy vấn theo từng item, khiến tổng roundtrip tăng rất nhanh khi số item lớn.
Một dịch vụ dùng concatMap để bảo đảm thứ tự ghi phiếu, nhưng một phiếu có SQL cực chậm làm toàn bộ hàng đợi phía sau bị giữ lại.
Một ứng dụng dùng parallel() trên Flux rồi gọi repository reactive ở nhiều rail, nhưng thực tế database vẫn giới hạn số connection nên thời gian xử lý không cải thiện.
Một nhóm đưa thao tác mã hóa nặng vào map của pipeline đọc dữ liệu, khiến event loop quá tải và metric cho thấy R2DBC query nhanh nhưng HTTP response vẫn chậm.
Một hệ thống dùng một publisher query lạnh trong nhiều bước xử lý mà không chia sẻ kết quả, khiến mỗi subscription thực hiện lại SQL và trả dữ liệu ở thời điểm khác nhau.
Một dịch vụ phản hồi WebFlux bằng Flux từ truy vấn SQL nhưng trình duyệt ngắt kết nối giữa chừng, khiến số bản ghi đã gửi không trùng với số row database truy vấn.
Một nhóm trộn Flux của hai query vào báo cáo nhưng không giữ thứ tự theo timestamp, khiến giao dịch được hiển thị sai trình tự khi kết quả đến xen kẽ.
Một ứng dụng tự chuyển lỗi SQL duplicate key thành HTTP 404, khiến client nghĩ bản ghi không tồn tại thay vì mã giao dịch đã được tạo trước đó.
Một hệ thống nhận R2DBC transient connection exception giữa nhiều request, nhưng bộ lọc lỗi trả chung HTTP 500 và đội trực không phân biệt database mất kết nối với constraint violation.
Một nhóm retry tất cả lỗi repository, khiến truy vấn sai cú pháp và lỗi validation cũng bị thực thi lặp nhiều lần mà không thể thành công.
Một dịch vụ nhận HTTP request bị timeout khi đợi pool connection, nhưng dashboard chỉ ghi SQL execution duration nên không thể định vị điểm nghẽn trước lúc chạy query.
Một ứng dụng gặp lỗi chuyển kiểu dữ liệu khi đọc row, nhưng error handler trả Mono.empty làm giao diện hiển thị như tài khoản chưa có đơn.
Một hệ thống ghi transaction rollback sau khi validation thất bại, nhưng log chỉ có exception cuối khiến đội hỗ trợ không biết dữ liệu đầu vào nào bị từ chối.
Một nhóm đặt retry với backoff giống nhau cho toàn bộ replica sau khi database failover, khiến các yêu cầu thử lại tập trung vào cùng thời điểm và gây quá tải lần hai.
Một dịch vụ sử dụng R2DBC pool có timeout acquire ngắn hơn nhu cầu giờ cao điểm, khiến nhiều request lỗi dù database đang xử lý ổn định các connection đã được cấp.
Một ứng dụng mở quá nhiều transaction đọc lâu để giữ snapshot, khiến việc thay schema và bảo trì database bị chậm do các truy vấn còn đang chạy.
Một hệ thống chạy nhiều SQL statements trên một transaction, nhưng khi lỗi ở câu thứ ba đội phát triển chưa xác định được trạng thái rollback và thông tin gửi tới user.
Một nhóm mong phương thức repository tự tạo bảng nếu chưa có, nhưng ứng dụng R2DBC không có migration schema phù hợp và lỗi table not found xuất hiện khi launch môi trường mới.
Một dịch vụ áp dụng Flyway để migration qua JDBC còn ứng dụng chạy R2DBC, nhưng migration dùng sai connection URL và schema triển khai không có các cột cần thiết.
Một ứng dụng chạy SQL migration đồng thời với nhiều Pod startup, khiến các lệnh ALTER TABLE cạnh tranh và một số instance không hoàn tất quá trình khởi động.
Một hệ thống có cột bắt buộc vừa được thêm nhưng phiên bản cũ vẫn chạy trong rolling deployment, khiến các câu INSERT của instance cũ thiếu giá trị cần thiết.
Một nhóm tạo unique index cho email nhưng database có nhiều hàng trùng từ trước, khiến triển khai constraint thất bại dù bộ code R2DBC mới khởi tạo bình thường.
Một dịch vụ áp dụng index cho truy vấn phân trang theo ngày nhưng vẫn dùng OFFSET lớn, khiến API đọc những trang cuối có latency tăng theo lượng dữ liệu.
Một ứng dụng xây composite index theo thứ tự cột không phù hợp điều kiện query phổ biến, khiến database planner chọn full scan trên bảng hàng triệu dòng.
Một nhóm kiểm thử query có LIKE trên bảng nhỏ rồi deploy production không có full-text index, khiến tính năng tìm sản phẩm phản hồi quá chậm trong giờ cao điểm.
Một hệ thống dùng SQL EXPLAIN ở một môi trường nhưng cấu trúc index của production khác, khiến kế hoạch truy vấn và số lượng hàng được đọc không giống kết quả benchmark.
Một dịch vụ dùng SELECT toàn bộ cột cho trang danh sách nhưng bảng chứa JSON payload lớn, khiến truyền dữ liệu qua mạng chiếm phần lớn thời gian phản hồi.
Một nhóm thêm ORDER BY theo cột có nhiều giá trị trùng mà không định nghĩa thứ tự phụ, khiến người dùng thấy các mục lặp khi chuyển trang trong lúc có insert mới.
Một ứng dụng đọc đơn theo tenant và trạng thái, nhưng index chỉ phủ trạng thái khiến query vẫn phải xem lượng lớn dữ liệu tenant khác trước khi lọc.
Một hệ thống phân mảnh dữ liệu theo ngày nhưng custom SQL không chứa điều kiện phân vùng, khiến query phải đọc nhiều partition không liên quan.
Một nhóm sử dụng SQL JOIN để trả graph nhỏ của khách và đơn, nhưng do nhiều quan hệ một-nhiều cùng join kết quả trung gian tăng gấp bội ngoài dự kiến.
Một dịch vụ lưu ngày giờ bằng timestamp không có timezone nhưng API lọc theo UTC, khiến truy vấn ranh giới ngày bỏ sót giao dịch của chi nhánh ở vùng khác.
Một ứng dụng phân trang hàng triệu bản ghi bằng LIMIT/OFFSET, nhưng user yêu cầu tiếp tục từ vị trí cuối và nhiều INSERT mới làm thứ tự kết quả không ổn định.
Một hệ thống chạy query báo cáo tổng doanh thu mỗi request, khiến database phải aggregate lại cùng dữ liệu hàng triệu row và pool connection bị chiếm quá lâu.
Một nhóm truy vấn theo ID đơn trên bảng không có primary key hay index đúng, khiến từng thao tác nhỏ đọc quá nhiều dòng và tăng CPU khi traffic lên cao.
Một dịch vụ có schema multi-tenant tách riêng theo khách nhưng cùng ConnectionFactory, khiến một request dùng schema từ request trước nếu trạng thái kết nối bị quản lý không đúng.
Một ứng dụng nhận tenant_id từ HTTP header mà không xác thực quyền, khiến SQL có filter tenant vẫn có thể trả dữ liệu của khách hàng khác theo input giả mạo.
Một nhóm ghép table name từ query parameter cho DatabaseClient nhưng chỉ bind các giá trị cột, khiến phần tên bảng có nguy cơ bị điều khiển ngoài danh sách được phép.
Một hệ thống lưu hồ sơ nhạy cảm trong bảng chung nhưng một custom repository query bỏ điều kiện tenant_id, khiến một endpoint có thể trả hồ sơ ngoài quyền truy cập.
Một ứng dụng đưa SQL bind parameters chứa mật khẩu vào log DEBUG, khiến đội vận hành đọc được dữ liệu cần che giấu khi điều tra một query timeout.
Một dịch vụ trả lỗi database trực tiếp về body HTTP, khiến thông tin tên bảng, schema và cấu trúc nội bộ lộ ra cho người dùng cuối.
Một nhóm dùng tài khoản database có quyền quản trị cho API chỉ đọc, khiến nếu service bị xâm nhập tác động tiềm năng lớn hơn phạm vi tìm kiếm thông thường.
Một hệ thống ghi audit khi người dùng thay đổi số dư nhưng log audit nằm ở nguồn khác không chung transaction, khiến khi một thao tác rollback audit vẫn ghi thành công.
Một dịch vụ cần xóa dữ liệu cá nhân nhưng quy trình chỉ xóa bảng chính, khiến dữ liệu trong bảng lịch sử và cache tiếp tục còn sau khi người dùng xác nhận.
Một ứng dụng gửi email xác nhận sau khi database ghi đơn thành công, nhưng một lần HTTP timeout ở giữa chuỗi khiến client gọi lại và người nhận có thể nhận hai email.
Một nhóm tạo API reactive ghi hàng loạt theo request nhưng không giới hạn kích thước payload, khiến khách gửi hàng chục nghìn bản ghi và áp lực connection tăng đột biến.
Một hệ thống mở WebFlux endpoint streaming dữ liệu qua Flux, nhưng token của người dùng hết hạn giữa một stream kéo dài và đội chưa có chính sách kiểm quyền tương ứng.
Một dịch vụ dùng Reactor Context để truyền thông tin quyền truy cập, nhưng một đoạn code lấy principal từ ThreadLocal và chọn sai tenant sau khi đổi scheduler.
Một nhóm bật metrics R2DBC cho database URL chứa user và password, khiến thông tin kết nối nhạy cảm có nguy cơ bị lưu trong nhãn quan sát nếu xử lý không cẩn thận.
Một ứng dụng chỉ đo p95 HTTP latency mà không tách pool acquisition và SQL execution, khiến khi throughput giảm đội trực không biết nên điều tra pool hay query.
Một hệ thống xuất metric gắn customer_id cho từng câu SQL, khiến số lượng time series tăng theo số khách và chi phí metrics vượt mức vận hành cho phép.
Một nhóm bật distributed tracing cho WebFlux nhưng custom DatabaseClient không được instrument như đường repository, khiến trace mất phân đoạn truy vấn SQL quan trọng.
Một dịch vụ có query chậm theo thời điểm nhưng log không mang correlation ID của request, khiến điều tra không biết truy vấn thuộc thao tác người dùng nào.
Một ứng dụng chỉ giám sát số connection đang mở, nhưng không đo pending acquire nên không phát hiện các request đang xếp hàng chờ pool khi tải cao.
Một hệ thống triển khai ba replica tăng lên hai mươi replica, nhưng dashboard không gộp pool metrics theo instance nên tổng số connection thực vượt ngưỡng mà không cảnh báo.
Một nhóm chạy performance test chỉ trên một luồng xử lý, khiến lỗi queue ở pool và contention khi nhiều Mono thực thi đồng thời không được phát hiện trước release.
Một dịch vụ có R2DBC driver trả lỗi rời rạc trong quá trình failover nhưng log gộp tất cả thành timeout, khiến đội vận hành không phân biệt mạng lỗi và deadlock.
Một ứng dụng chỉ đếm successful subscriptions khi tạo Mono mà chưa thực sự subscribe, khiến dashboard báo đã xử lý đơn nhiều hơn số row thực được ghi.
Một nhóm chạy đơn song song rồi retry dưới cùng correlation ID nhưng không ghi attempt number, khiến log của các lần thử bị trộn và khó truy nguyên kết quả cuối.
Một hệ thống chuyển R2DBC driver phiên bản mới mà không kiểm tra pool metrics và timeout behavior, khiến biểu đồ lỗi thay đổi mà không xác định được khác biệt thư viện.
Một dịch vụ dùng Testcontainers cho PostgreSQL trong integration test nhưng thiếu bước chạy migration, khiến suite chỉ kiểm được đường tìm bảng không tồn tại thay vì query thực tế.
Một ứng dụng kiểm thử repository reactive bằng StepVerifier chỉ cho nhánh thành công, khiến lỗi duplicate key và cancellation không có assertion tương ứng.
Một nhóm test transaction với hai save thành công nhưng không ép lỗi ở câu SQL thứ hai, khiến khả năng rollback khi ghi nhiều bảng chưa được xác minh.
Một hệ thống chỉ test API WebFlux với một request, khiến hai thao tác đồng thời cùng sửa row không phát hiện lỗi lost update hoặc optimistic locking.
Một dịch vụ dùng H2/JDBC để kiểm thử repository trong khi production chạy R2DBC với PostgreSQL, khiến bài test không đi qua driver và SQL dialect thực của ứng dụng.
Một ứng dụng mock ReactiveCrudRepository trả Mono.just(entity), nhưng production sử dụng publisher lạnh có lỗi kết nối khi subscribe nên đường error handling chưa được kiểm thử.
Một nhóm kiểm thử WebFlux controller bằng WebTestClient nhưng service mock trả dữ liệu sẵn, khiến lỗi tích hợp TransactionalOperator và ConnectionFactory không xuất hiện.
Một hệ thống kiểm thử thời gian chờ database bằng sleep trong test, khiến kết quả không ổn định và không mô phỏng đúng pool acquire timeout dưới tải.
Một ứng dụng dùng test rollback transaction theo kiểu imperative, nhưng method thực tế trả Mono chưa subscribe nên bài kiểm tra không chạy các thao tác dữ liệu cần xác minh.
Một nhóm mock DatabaseClient chỉ trả một row, khiến lỗi mapping nhiều row từ JOIN vào DTO bị phát hiện quá muộn khi production có dữ liệu thật.
Một dịch vụ kiểm thử batch insert vài trăm bản ghi nhưng production xử lý hàng triệu record, khiến nguy cơ memory pressure từ collectList và connection contention bị bỏ qua.
Một hệ thống chỉ kiểm thử thứ tự phản hồi của hai Flux ở môi trường đơn luồng, khiến race condition giữa các publisher chạy song song không được đánh giá đầy đủ.
Một ứng dụng test tenant isolation chỉ với một tenant, khiến câu SQL custom thiếu WHERE tenant_id không được phát hiện trước khi nhiều khách cùng sử dụng.
Một nhóm không thử client disconnect giữa reactive database stream, khiến việc giải phóng connection sau cancellation chưa được xác minh khi HTTP bị hủy.
Một dịch vụ dùng fake ConnectionFactory trong unit test nên không kiểm các lỗi TLS, credential rotation và pool stale connection chỉ xuất hiện trên database thật.
Một hệ thống có regression tests cho câu SQL SELECT nhưng không test update affected-row count, khiến API báo thành công dù bản ghi đã bị xóa ở request khác.
Một ứng dụng chỉ đo thời gian chạy câu SQL trong benchmark, khiến thời gian startup, bind parameters, pool waiting và serialization bị bỏ khỏi SLA API.
Một nhóm dùng schema migration chạy trên JDBC trong test nhưng production dùng database profile khác, khiến bảng mới có tên cột khác và repository lỗi khi deploy.
Một dịch vụ test retry với kết quả timeout trước khi SQL được gửi, khiến tình huống database đã commit rồi client mất response chưa được xác minh.
Một hệ thống có transaction reactive phối hợp nhiều repositories, nhưng test chỉ gọi từng repository riêng nên ranh giới transaction thực tế chưa được đánh giá.
Một ứng dụng cần read-after-write cho đơn hàng vừa tạo, nhưng integration test chỉ đọc từ primary và bỏ qua replica lag sẽ gặp khi sản xuất đọc từ nguồn khác.
Một nhóm dùng Spring Data R2DBC cho tác vụ cập nhật đêm nhưng không kiểm tra shutdown khi có transaction chưa hoàn tất, khiến tác vụ bị kill có trạng thái khó đối chiếu.
Một dịch vụ cần đồng bộ số lượng tồn với ERP nhưng chỉ ghi DB thành công trước khi gọi ERP, khiến lỗi API bên ngoài tạo chênh lệch mà transaction DB không thể tự xử lý.
Một hệ thống dùng R2dbcEntityTemplate trong luồng xử lý yêu cầu lớn nhưng không đặt giới hạn số row, khiến một người dùng có thể gây memory pressure khi request tập hợp dữ liệu lớn.
Một ứng dụng chuẩn bị chạy trên Kubernetes nhiều vùng nhưng chưa kiểm tra database failover và giới hạn connection theo vùng, khiến lần chuyển vùng đầu gây lỗi hàng loạt.
