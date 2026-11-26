Một dịch vụ quản lý đơn hàng dùng Spring Data JDBC ánh xạ Order bằng @Table; bảng production đặt tên khác chiến lược mặc định khiến repository báo không tìm thấy bảng khi ứng dụng bắt đầu đọc dữ liệu.
Nhóm phát triển thêm @Id cho trường mã giao dịch dạng UUID; dữ liệu lịch sử lưu khóa dưới dạng chuỗi khác chuẩn khiến repository findById không tìm được nhiều giao dịch cũ.
Một ứng dụng lập hóa đơn chuyển từ khóa chính Long sang String để đồng bộ với đối tác; phương thức repository vẫn nhận Long nên truy vấn theo ID phát sinh lỗi chuyển kiểu.
Đội xây dựng schema dùng tên cột có chữ hoa và ký tự đặc biệt; Spring Data JDBC sinh SQL khác giữa PostgreSQL và H2 nên test chạy được nhưng production báo không tìm thấy cột.
Một dịch vụ bán vé dùng @Column để ánh xạ seatNumber sang cột có tên khác; sau khi đổi tên property Java, một repository tùy biến vẫn truy vấn theo tên cột cũ.
Nhóm phát triển lưu số tiền bằng BigDecimal nhưng cột database định nghĩa precision quá nhỏ; đơn hàng giá trị lớn bị lỗi lúc INSERT dù các unit test domain đều thành công.
Ứng dụng vận tải ánh xạ trạng thái đơn hàng bằng enum; khi thêm phần tử enum mới, dữ liệu cũ và mới dùng cách biểu diễn khác khiến thao tác đọc gặp lỗi.
Một hệ thống ghi nhận lịch hẹn bằng LocalDateTime trong entity; các node chạy ở hai múi giờ khác nhau hiển thị lịch giao hàng không giống dữ liệu mà khách đã nhập.
Đội kỹ thuật dùng Instant cho thời điểm thanh toán nhưng database lưu timestamp không có múi giờ; báo cáo chốt ngày lệch khi dữ liệu đến từ nhiều khu vực.
Một ứng dụng Spring Data JDBC lưu giá trị tiền tệ bằng value object Money; JdbcConverter không có cấu hình chuyển đổi tương ứng nên lần lưu đầu gặp lỗi kiểu dữ liệu.
Nhóm thay mapping từ số điện thoại String sang value object PhoneNumber; dữ liệu legacy có ký tự không hợp lệ làm bộ chuyển đổi thất bại ngay khi đọc trang khách hàng.
Một dịch vụ đặt hàng sử dụng @Embedded cho địa chỉ giao nhận; hai địa chỉ thu tiền và giao hàng có cùng tên thuộc tính khiến schema sinh ra tên cột bị trùng.
Ứng dụng lưu nhiều @Embedded value object có thể không tồn tại; khi các cột bên trong đều null, object được dựng lại khác với giá trị rỗng mà nghiệp vụ mong muốn.
Nhóm dùng immutable record để mô hình hóa địa chỉ đơn hàng; constructor persistence không thể ánh xạ đúng một trường mới được thêm vào bảng sau đợt migration.
Một entity được thiết kế bất biến với nhiều constructor; Spring Data JDBC không xác định được constructor dùng khi đọc lại aggregate và endpoint chỉ lỗi khi gặp dữ liệu thực.
Đội phát triển thêm @PersistenceCreator cho constructor chứa trường mới; các hàng dữ liệu cũ không có giá trị đó khiến việc tái tạo entity thất bại trong luồng báo cáo.
Một ứng dụng dùng class Kotlin bất biến với giá trị mặc định cho trường tùy chọn; trường null từ database được diễn giải khác giá trị mặc định khi ánh xạ aggregate.
Nhóm đặt tên cột tùy biến qua NamingStrategy; một bản nâng thư viện làm tên cột của value object được xây khác so với schema đã quản lý bằng Flyway.
Một hệ thống có khóa chính dạng composite tự tạo ở tầng nghiệp vụ; repository mặc định không thể xử lý như một scalar ID theo thiết kế đang dùng.
Đội bảo trì lưu entity có ID được gán từ API đối tác; Spring Data JDBC nhận diện aggregate có ID khác null là đã tồn tại và thao tác ghi không như dự định.
Nhóm triển khai Persistable để tự quyết định entity mới hay cũ; thuộc tính isNew không được cập nhật sau khi lưu khiến cùng aggregate vẫn bị coi là mới ở lần ghi kế tiếp.
Một hệ thống sử dụng @Version để nhận biết entity mới với ID gán thủ công; khi nhập bản ghi có version không phù hợp, thao tác đầu tiên phát sinh lỗi cập nhật ngoài kỳ vọng.
Ứng dụng cấp số phiếu bằng sequence của PostgreSQL; tại môi trường MySQL, đường cấp số tương ứng không tồn tại khiến chức năng tạo phiếu lỗi ở production.
Nhóm dùng BeforeConvertCallback để tự gán ID cho aggregate mới; một callback khác cũng thay đổi ID khiến khóa của các entity con không còn tham chiếu đúng aggregate root.
Một ứng dụng yêu cầu mã định danh được sinh từ database khi INSERT; sau khi đổi JDBC driver, giá trị generated key không được đọc theo cách repository mong đợi.
Đội phát triển dùng một instance entity để gọi save nhiều lần; sau lần lưu, ID trong đối tượng được trả về thay đổi nhưng service tiếp tục dùng instance cũ thiếu khóa.
Một dịch vụ đăng ký tài khoản lưu @Table Customer có version và createdAt; payload cập nhật dựng object mới chỉ chứa các trường gửi từ client làm trường nghiệp vụ khác bị mất.
Một ứng dụng Domain-Driven Design đặt Order làm aggregate root chứa nhiều OrderItem; đội sản phẩm xem item là entity độc lập và muốn cập nhật item từ repository riêng.
Nhóm thiết kế kho hàng dùng Warehouse chứa nhiều Bin như các entity con; khi lưu lại một Warehouse chỉ nạp một phần bin, các bin không nằm trong collection bị xóa ngoài mong đợi.
Ứng dụng đặt hàng có aggregate Order với List<LineItem>; thao tác save sau khi đổi địa chỉ giao hàng vẫn phát sinh nhiều DELETE và INSERT cho line item không thay đổi.
Đội phát triển thiết kế aggregate chứa lịch sử trạng thái tăng theo từng sự kiện; khi số phần tử con lên hàng chục nghìn, việc lưu root ngày càng chậm và tạo áp lực ghi.
Một dịch vụ giao hàng sử dụng @MappedCollection cho danh sách các điểm giao; sau khi thay đổi tên cột khóa ngoại, các điểm giao đã lưu không còn được tải khi đọc aggregate.
Nhóm ánh xạ quan hệ root với child qua @MappedCollection(idColumn) nhưng schema dùng tên khóa ngoại khác; đọc root thành công trong khi collection con luôn rỗng.
Ứng dụng lưu danh sách item có thứ tự bằng @MappedCollection(keyColumn); khi sắp xếp lại item trong Java, dữ liệu đọc sau save cho thứ tự khác màn hình.
Đội phát triển đổi collection con từ List thành Set; equals và hashCode của child chỉ dùng ID chưa được sinh nên một số item mới bị loại khỏi tập hợp trước khi lưu.
Một service dùng Map để lưu các mức phí theo vùng bên trong aggregate; dữ liệu trong keyColumn không phù hợp kiểu key Java khiến việc ánh xạ Map khi đọc thất bại.
Nhóm quản lý giỏ hàng cho phép hai request thay đổi hai item khác nhau; mỗi request đọc cả root rồi save khiến bản lưu đến sau có thể ghi đè thay đổi của request kia.
Ứng dụng muốn cập nhật riêng giá của một LineItem bằng cách thay đổi object đã đọc; không có persistence context kiểu JPA nên lệnh kết thúc method không tự đồng bộ dữ liệu.
Đội phát triển lấy Order từ repository, đổi trạng thái và trả HTTP 200 mà không gọi save; lần đọc kế tiếp vẫn thấy trạng thái cũ dù service đã sửa object trong bộ nhớ.
Một hệ thống có aggregate Customer chứa nhiều địa chỉ; service chỉ cần đổi email nhưng mỗi lần save tạo nhiều lệnh ghi xuống bảng địa chỉ vì collection thuộc cùng aggregate.
Nhóm tách hóa đơn và thanh toán thành hai aggregate root; họ gắn một Payment object trực tiếp trong Invoice và vô tình khiến vòng đời của hai aggregate bị quản lý chung.
Ứng dụng bán lẻ dùng AggregateReference<Product,Long> từ OrderItem tới Product; khi xóa sản phẩm, các item cũ vẫn mang ID reference và đọc chi tiết đơn thiếu tên hàng.
Đội kỹ thuật muốn tự động tải Product khi đọc Order; AggregateReference chỉ giữ định danh nên response không có dữ liệu sản phẩm như cách mapping JPA trước đây.
Nhóm thiết kế một quan hệ hai chiều giữa Customer và Order theo entity reference; Spring Data JDBC không quản lý association như persistence context khiến cách biểu diễn graph không phù hợp với vòng đời aggregate.
Một hệ thống đặt hàng cho phép đổi chủ sở hữu Order sang Customer khác; aggregate lưu khóa tham chiếu mới nhưng báo cáo đang lưu thông tin chủ cũ ở bảng phụ.
Đội phát triển mô hình hóa Many-to-Many trực tiếp giữa User và Role; chức năng gán vai trò gặp khó vì mỗi bên đều được xem là aggregate root độc lập.
Ứng dụng cần đọc Order cùng Customer và Warehouse trên một màn hình; nhiều repository call theo từng order tạo hàng trăm lượt truy cập database dù root chỉ có reference ID.
Nhóm muốn biểu diễn tham chiếu cùng aggregate trong nhiều service; một service xóa root làm các AggregateReference của service khác trở thành định danh không tồn tại.
Đội sản phẩm yêu cầu cập nhật một địa chỉ được hàng nghìn khách dùng chung; địa chỉ hiện đang nằm dưới nhiều aggregate root khác nhau và dữ liệu bị phân mảnh khi sửa.
Một hệ thống kế toán có aggregate Invoice với LineItem và TaxDetail; child bị gán ID của một root khác nhưng save root mới cố tạo lại child dưới khóa ngoại hiện tại.
Nhóm nhập Order từ hệ thống cũ nhưng thiếu dòng con trong vài file; khi save aggregate partial, dữ liệu item cũ bị xóa vì mô hình coi collection đang gửi là trạng thái mới toàn bộ.
Ứng dụng dùng event handler thêm LineItem sau khi root vừa lưu; một listener khác đã đọc aggregate trước khi child được lưu và báo thiếu sản phẩm trên đơn.
Đội kỹ thuật truyền entity con từ một aggregate sang aggregate khác mà giữ nguyên ID; khi cả hai root được save, khóa con và quan hệ sở hữu không còn nhất quán.
Một service xử lý hoàn tiền yêu cầu đơn và các lần thanh toán lưu trong cùng giao dịch; hai loại dữ liệu nằm trong aggregate khác nhau và code đang kỳ vọng một save là đủ.
Nhóm triển khai domain event cho Order khi trạng thái được xác nhận; listener phát thông báo nhưng transaction ghi aggregate thất bại nên người dùng nhận sự kiện không tồn tại.
Ứng dụng phát @DomainEvents từ aggregate sau repository save; tác vụ ghi bằng SQL tùy chỉnh ngoài repository không kích hoạt cùng cơ chế event và downstream thiếu bản tin.
Một đội dùng @AfterDomainEventPublication để xóa event chờ trong root; một lỗi xảy ra sau khi event được phát nhưng trước commit khiến dữ liệu nguồn và thông báo không khớp.
Nhóm vận hành thiết kế Order aggregate lớn với nhiều cấp nested child; query đọc chi tiết và chuỗi câu lệnh lưu tăng nhanh theo số lượng child khiến thời gian phản hồi vượt SLA.
Một nền tảng giao nhận tách DeliveryAttempt thành aggregate riêng để giảm kích thước Order; báo cáo cũ vẫn mong Order có toàn bộ attempts mà không truy vấn thêm dữ liệu.
Ứng dụng quản lý vé giữ SeatReservation là entity con của Show; hàng nghìn khách đặt vé đồng thời cạnh tranh cập nhật cùng một version root dù họ chọn những ghế khác nhau.
Nhóm áp unique constraint trên child row theo aggregate root; khi save sử dụng xóa và chèn lại children, một số bản ghi tạm thời va chạm constraint với thao tác đồng thời.
Một service bán hàng có Customer aggregate giữ mảng địa chỉ khổng lồ; câu truy vấn đọc thông tin liên hệ đơn giản vẫn kéo theo dữ liệu con không cần thiết.
Đội thiết kế aggregate root chứa cả lịch sử audit đã bất biến; mỗi lần sửa trạng thái đơn, collection lịch sử bị ghi lại làm chi phí I/O tăng không tương ứng giá trị thay đổi.
Nhóm định nghĩa CrudRepository<Order,Long> nhưng trong service vẫn dùng một implementation JdbcTemplate riêng; hai đường ghi có quy tắc lưu child khác nhau và dữ liệu không nhất quán.
Một ứng dụng chuyển từ JPA sang Spring Data JDBC và giữ JpaRepository trong một interface; bộ repository không thể tạo theo store mới dù các method CRUD về tên vẫn giống nhau.
Đội phát triển dùng ListCrudRepository cho aggregate Customer; sau khi refactor thành PagingAndSortingRepository riêng, service không còn thấy các method save và delete đã dùng.
Ứng dụng định nghĩa repository method findByCustomerId; property Java đổi từ customerId thành customerRef làm Spring Data phân giải truy vấn không đúng như schema mới.
Nhóm bán hàng dùng derived query findByStatusAndCreatedAtAfter; bản ghi cũ có trạng thái null và đơn cuối ngày bị loại khỏi thống kê không phù hợp yêu cầu nghiệp vụ.
Một service dùng findByNameContainingIgnoreCase với kho PostgreSQL; một lượng lớn dữ liệu có dấu tiếng Việt khiến kết quả so khớp khác với khả năng tìm kiếm mà giao diện công bố.
Đội kỹ thuật thêm property Order.customer.address.city nhưng Customer là aggregate riêng; derived query không thể duyệt association giống JPA như code cũ mong đợi.
Nhóm cần lọc Invoice theo tổng giá trị của các line item; derived query chỉ diễn đạt property đơn giản trong khi điều kiện tổng hợp nằm ở nhiều hàng con.
Ứng dụng tìm Order gần nhất theo khách bằng findFirstByCustomerIdOrderByCreatedAtDesc; hai đơn có cùng timestamp khiến kết quả không ổn định giữa các lần truy vấn.
Một API cho phép lọc sản phẩm theo các điều kiện tùy chọn; repository derived method dài có nhiều OR và AND làm tập kết quả không đúng với quy tắc nghiệp vụ.
Đội vận hành thêm unique index cho email khách hàng; một method existsByEmail vẫn không bảo đảm ngăn hai request tạo cùng email trong điều kiện cạnh tranh.
Nhóm phát triển gọi repository count trên bảng đơn hàng nhiều triệu dòng ở mỗi lần mở dashboard; endpoint bắt đầu chậm dù chỉ hiển thị một trang dữ liệu.
Một hệ thống dữ liệu lịch sử dùng deleteById trên một aggregate root; service vẫn giả định các child rows được xóa đúng thứ tự dù có foreign key sang dữ liệu bên ngoài aggregate.
Đội xây API quản trị có findAll để xuất toàn bộ Order; hàng triệu aggregate và children được nạp vào heap làm container bị OOM trong giờ cao điểm.
Một service dùng @Query với SQL tùy chỉnh để chọn danh sách sản phẩm; query trả đúng cột root nhưng thiếu dữ liệu child mà nghiệp vụ đang mong truy cập khi dựng response.
Nhóm định nghĩa @Query dùng tên thuộc tính Java thay vì tên cột database; phương thức repository khởi động được nhưng SQL lỗi khi lần đầu được thực thi.
Ứng dụng dùng named parameters trong @Query để lọc trạng thái đơn; khi tên tham số method được đổi, SQL không còn bind đúng nên trang quản trị liên tục trả lỗi.
Đội phát triển chuyển một JPQL query từ phiên bản JPA sang @Query của Spring Data JDBC; cú pháp sử dụng tên entity và JOIN FETCH gây lỗi vì tầng mới thực thi SQL trực tiếp.
Nhóm báo cáo tạo SQL JOIN nhiều bảng cho Invoice và LineItem; mỗi hóa đơn bị nhân thành nhiều dòng và kết quả repository được gom không như mong đợi.
Một API sử dụng @Query SQL tổng hợp doanh thu theo chi nhánh; repository method trả về entity Invoice dù projection từ SQL chỉ có các trường group và total.
Đội làm báo cáo ngày dùng @Query với function của PostgreSQL; bộ test chạy H2 không hỗ trợ cùng cú pháp khiến test fail dù SQL production hợp lệ.
Ứng dụng tạo báo cáo MySQL với câu SQL dùng alias trùng từ khóa dành riêng; H2 chấp nhận cú pháp nhưng production từ chối khi query được thực thi.
Nhóm tích hợp dùng @Modifying trong repository để update một thuộc tính; aggregate đã đọc trước đó trong bộ nhớ vẫn giữ dữ liệu cũ và code tưởng được đồng bộ tự động.
Một service gọi custom update theo SQL nhưng quên ràng buộc tenantId; lệnh cập nhật thay đổi cả các đơn thuộc tổ chức khác khi dùng ID từ nguồn bên ngoài.
Đội phát triển muốn đếm số bản ghi vừa update bằng @Modifying; một số mã xử lý coi giá trị trả về là ID entity thay vì số dòng bị ảnh hưởng.
Ứng dụng sử dụng custom SQL để cộng hàng tồn; bộ lọc không kiểm số lượng còn lại nên hai request đồng thời có thể làm số dư kho xuống âm.
Nhóm áp câu SQL INSERT tùy biến vào bảng child của Order; lần save root kế tiếp ghi lại collection và làm thay đổi dữ liệu được thêm trực tiếp trước đó.
Đội công nghệ dùng SQL UPDATE trực tiếp thay đổi version column; lần lưu lại qua repository gặp OptimisticLockingFailureException dù người dùng chỉ sửa một trường khác.
Một service lấy dữ liệu theo @Query trả projection DTO; alias của cột SQL không khớp tên field DTO và nhiều giá trị bị null trong kết quả API.
Nhóm báo cáo dùng RowMapper tùy biến để tạo object tổng hợp; một lần thêm cột nullable khiến mapper chuyển kiểu sai với dữ liệu production.
Ứng dụng có column amount lưu DECIMAL nhưng DTO query khai báo Integer; giao dịch lớn bị mất phần thập phân khi đọc qua projection đơn giản.
Đội phát triển tạo repository fragment cho truy vấn theo vùng địa lý; interface fragment được đăng ký nhưng implementation không được ghép vào repository ở môi trường CI.
Một custom repository method truy vấn JSON column của PostgreSQL; sau khi chuyển MySQL, cú pháp SQL đặc thù không tương thích dù domain model không đổi.
Nhóm xây JdbcAggregateTemplate để lưu aggregate ngoài repository mặc định; một đường lưu khác qua JdbcTemplate bỏ qua callbacks và auditing đã được cài.
Ứng dụng dùng JdbcAggregateTemplate để xóa root theo ID; hệ thống báo xóa thành công nhưng một bảng liên kết bên ngoài aggregate còn dữ liệu mồ côi.
Một backend quản lý hợp đồng dùng Pageable để duyệt dữ liệu; phần SQL tùy biến đã có ORDER BY riêng và sort do client truyền không được áp đúng thứ tự yêu cầu.
Đội phát triển trả Page<Order> từ repository nhưng query đếm đi theo một bộ lọc khác query lấy dữ liệu; giao diện hiển thị số trang sai khi bật nhiều điều kiện.
Ứng dụng dùng Slice để giảm chi phí count nhưng client vẫn dựa vào totalElements; chức năng cuộn danh sách bị lỗi sau khi đổi kiểu kết quả.
Nhóm dùng offset pagination trên bảng giao dịch đang nhận dữ liệu mới; người dùng chuyển trang và gặp bản ghi lặp hoặc bỏ sót trong khoảng thời gian thống kê.
Một service sắp xếp Order theo createdAt khi nhiều đơn cùng thời gian; thứ tự các hàng giữa hai request không ổn định làm xuất báo cáo bị trùng.
Đội QA gửi Pageable size cực lớn tới endpoint tìm kiếm; repository tải quá nhiều aggregate và bộ nhớ cạn trong lúc ánh xạ các collection con.
Nhóm triển khai API sắp xếp theo field được user cung cấp; client yêu cầu sort trên thuộc tính không tồn tại khiến SQL sinh ra lỗi ở production.
Một ứng dụng cần phân trang theo cursor của giao dịch; code hiện dùng offset sâu trên bảng nhiều triệu dòng và độ trễ tăng theo số trang.
Đội xây query lọc dữ liệu theo Customer rồi sort theo child field; tên property của @MappedCollection không được ánh xạ theo cách mà custom SQL kỳ vọng.
Nhóm tích hợp đổi database dialect từ H2 sang PostgreSQL; câu SQL phân trang có cách sử dụng LIMIT/OFFSET khác và bộ test đơn giản không phát hiện.
Một ứng dụng đặt chỗ có @Transactional trên service tạo Order rồi giữ Seat; lệnh thứ hai lỗi nhưng Order đã được ghi trước đó do hai repository call chạy trong hai transaction riêng.
Đội phát triển gọi save(Order) rồi gửi email trước khi transaction commit; thao tác gửi đã thành công nhưng database rollback vì unique constraint ở bước cuối.
Nhóm viết @Transactional trên method private tạo hợp đồng; lời gọi nội bộ không đi qua proxy và các thay đổi không còn được rollback cùng nhau.
Một service có method @Transactional gọi từ method khác cùng class; nhóm muốn propagation riêng nhưng không có transaction interceptor hoạt động ở lời gọi tự thân.
Đội quản lý tồn kho cập nhật lượng hàng rồi gọi API đối tác trong cùng transaction; network chậm giữ lock và connection JDBC lâu khiến các request khác bị chờ.
Ứng dụng chạy batch save nhiều aggregate trong một transaction; một bản ghi lỗi sát cuối làm rollback hàng nghìn thay đổi trong khi dashboard đã hiển thị số item đã xử lý.
Nhóm phát triển cho rằng save là thao tác chỉ thay một field như dirty checking của JPA; việc ghi lại aggregate khiến child collection bị xóa và tái tạo trong cùng transaction.
Ứng dụng thay đổi field trên root đã đọc mà không gọi repository.save; sau khi method kết thúc database không có thay đổi vì Spring Data JDBC không quản lý trạng thái entity đã đọc.
Đội triển khai transaction readOnly cho method cần điều chỉnh trạng thái sau khi đọc; lệnh save thực sự có hành vi khác với dự định khi transaction được cấu hình chỉ đọc.
Một dịch vụ kế toán dùng transaction propagation REQUIRES_NEW để ghi log; nghiệp vụ chính rollback nhưng bản ghi log đã commit khiến nhân viên hiểu sai tình trạng giao dịch.
Nhóm dùng transaction isolation mặc định khi kiểm tra còn vé; hai người dùng cùng đọc còn một ghế và đều yêu cầu lưu đặt chỗ vào lúc cao điểm.
Ứng dụng thực hiện nhiều truy vấn đọc cùng dữ liệu trong một transaction; request khác cập nhật bảng giữa hai lần đọc khiến điều kiện nghiệp vụ thay đổi ngoài dự đoán.
Đội vận hành thấy deadlock giữa hai service cập nhật Order và Inventory theo thứ tự khác nhau; lỗi chỉ xảy ra dưới tải đồng thời và không xuất hiện trong test tuần tự.
Nhóm cấu hình @Transactional rollbackFor không bao gồm một loại exception nghiệp vụ checked; database vẫn commit một phần thay đổi dù service trả lỗi cho khách.
Một dịch vụ sử dụng TransactionTemplate quanh ba repository call; thao tác thứ ba được thực thi trong một scheduler riêng nên không cùng transaction của hai thao tác đầu.
Đội kỹ thuật mở transaction rồi truyền aggregate sang thread pool để cập nhật; context giao dịch không tự đi cùng thread và dữ liệu ghi không còn tính nguyên tử như kỳ vọng.
Một ứng dụng phát domain event trong transaction trước khi commit; Consumer xử lý event đọc database nhưng chưa thấy Order tương ứng ở thời điểm sự kiện đến.
Nhóm áp @Version lên aggregate Order để ngăn cập nhật đồng thời; request thứ hai đọc version cũ và save gây OptimisticLockingFailureException trong luồng đặt hàng.
Một hệ thống tồn kho bỏ @Version khi chuyển từ JPA sang Spring Data JDBC; hai request cập nhật cùng root làm thay đổi của người đến trước bị ghi đè âm thầm.
Đội ứng dụng nhận payload cập nhật thiếu trường version; repository không thể xác nhận đối tượng có còn mới nhất và người dùng sửa dữ liệu từ màn hình cũ.
Nhóm phát triển tự gán version bằng dữ liệu client thay vì trạng thái đang lưu; một request cố tình gửi version phù hợp trong khi nội dung thay đổi không được kiểm chứng đầy đủ.
Một service gặp OptimisticLockingFailureException và retry bằng chính object đã lỗi; version vẫn cũ nên các lượt thử lại đều thất bại trong giờ cao điểm.
Ứng dụng dùng @Version cho root có nhiều child; hai người dùng sửa hai child khác nhau vẫn tranh chấp version của cùng root và một người bị từ chối lưu.
Đội triển khai bulk update SQL trực tiếp bỏ qua version; request sau dùng repository.save không phát hiện cập nhật cạnh tranh theo cách nhóm bảo trì mong đợi.
Một hệ thống áp dụng pessimistic lock thủ công bằng SELECT FOR UPDATE trong JdbcTemplate; một repository query khác không giữ cùng transaction nên khóa bảo vệ không còn hiệu lực.
Nhóm vận hành cấu hình lock wait timeout trên PostgreSQL nhưng test dùng H2; dưới tải thực, nhiều request đợi lâu hơn giả định và trả lỗi muộn.
Một job làm mới danh mục đọc rồi ghi nhiều aggregate; hai worker không có cơ chế phối hợp nên cùng thay đổi một root và tăng tỷ lệ optimistic lock failure.
Đội lưu phiên bản lịch sử đơn hàng thành child entity; save root lỗi optimistic locking nhưng hệ thống vẫn gửi thông báo rằng lịch sử đã được ghi.
Nhóm phát triển dùng @CreatedDate và @LastModifiedDate cho Customer; một đường cập nhật SQL thuần không chạy auditing callback nên thời gian sửa không được cập nhật.
Ứng dụng bật @CreatedBy qua AuditorAware dựa vào SecurityContext; job ban đêm không có người dùng đăng nhập nên trường người tạo null và vi phạm NOT NULL constraint.
Đội tích hợp xác định người sửa qua @LastModifiedBy; khi xử lý event Kafka ở thread khác, audit ghi tên mặc định khác người khởi phát thao tác nghiệp vụ.
Một dịch vụ đồng bộ dữ liệu lịch sử gọi repository.save trên bản ghi đã có ID; auditing ghi thời gian nhập hiện tại và làm sai ngày tạo dữ liệu gốc.
Nhóm triển khai BeforeConvertCallback sinh mã khách hàng; khi callback chạy lại lúc cập nhật, mã đã cấp bị thay đổi và các bảng tham chiếu không còn trỏ đúng khách.
Ứng dụng có BeforeSaveCallback ghi thông tin audit; custom SQL update trong một fragment bypass callback khiến kết quả ở hai đường ghi khác nhau.
Đội dùng AfterSaveCallback để gửi sự kiện; transaction SQL có thể rollback sau callback và downstream vẫn nhận một message về aggregate chưa được lưu bền vững.
Một service dùng AfterConvertCallback để làm giàu entity bằng dữ liệu cache; một màn hình chỉ đọc vẫn hiển thị field từ cache cũ không khớp nội dung bảng.
Nhóm phát triển phát @DomainEvents khi save aggregate; một job cập nhật qua JdbcTemplate không tạo event và hệ thống báo cáo downstream thiếu dữ liệu.
Ứng dụng có @AfterDomainEventPublication xóa danh sách event chờ; khi thao tác ghi bị lỗi sau đó, danh sách sự kiện trong bộ nhớ không còn giống dữ liệu chưa commit.
Đội bảo trì dùng immutable aggregate chứa createdAt và updatedAt; sau khi save trả về instance mới, service đọc instance cũ và thấy audit field chưa được cập nhật.
Một hệ thống cần ghi tên service account khi sửa dữ liệu tự động; AuditorAware chỉ trả username của HTTP request nên các tác vụ định kỳ không có tác nhân hợp lệ.
Nhóm quản trị dùng custom converter cho encrypted email; một query derived theo email plaintext không còn tìm được row lưu cipher text như nghiệp vụ cần.
Ứng dụng chuyển một thuộc tính value object thành ba cột embedded; dữ liệu cũ chỉ có một cột nên thao tác đọc aggregate thất bại sau triển khai.
Đội thay schema cho @MappedCollection nhưng không chạy migration child table; repository load root thành công rồi lỗi lúc tải danh sách con.
Nhóm deploy phiên bản mới có tên bảng child khác trong khi các pod cũ vẫn chạy; hai phiên bản luân phiên ghi cùng aggregate theo các mapping không tương thích.
Một ứng dụng mở repository scanning quá rộng khi có cả Spring Data JDBC và JPA; một interface repository không được gán rõ cho store phù hợp nên bean khởi tạo lỗi.
Đội triển khai nhiều DataSource với một named bean mặc định; repository Spring Data JDBC đọc tài liệu từ database khác với JdbcTemplate đang ghi trong cùng service.
Nhóm dùng AbstractRoutingDataSource để phân vùng tenant; transaction đã lấy connection trước khi xác định tenant nên request thứ hai vẫn truy vấn dữ liệu của tenant trước.
Một hệ thống SaaS tự tạo schema riêng cho từng tổ chức; SQL repository không truyền schema ở một nhánh khiến dữ liệu được ghi vào public schema ngoài mong muốn.
Đội quản lý quyền truy cập dựa trên tenantId trong query; custom SQL lấy entity theo ID mà không kèm tenantId nên lộ dữ liệu nhạy cảm của khách hàng khác.
Ứng dụng có unique constraint dựa trên mã khách hàng và chi nhánh; kiểm tra exists trước INSERT không ngăn được trùng khi hai request đồng thời thực thi.
Nhóm dùng @DataJdbcTest để kiểm repository nhưng database test là H2; production PostgreSQL có tên cột, constraint và cú pháp SQL khác khiến lệnh tùy chỉnh lỗi.
Một đội kiểm thử mapping aggregate với bảng chỉ có root; bộ test không tạo child table nên không phát hiện lỗi @MappedCollection cho tới khi chạy chức năng chi tiết.
Ứng dụng dùng Testcontainers PostgreSQL cho integration test; container chưa chạy migration Flyway giống production nên @Query đọc trường không tồn tại ở môi trường thật.
Nhóm kiểm thử optimistic locking bằng hai lần save liên tiếp trên cùng instance; test không sử dụng hai bản sao đọc ở cùng version nên không tái hiện xung đột thực tế.
Một bộ test @Transactional mặc định rollback mọi thay đổi; lỗi unique constraint chỉ được kiểm khi transaction commit ở production nhưng không xuất hiện trong test.
Đội phát triển mock CrudRepository trong unit test; những đặc điểm xóa và tạo lại child rows khi save không được kiểm chứng cho aggregate thực tế.
Nhóm cần test khả năng giữ nguyên dữ liệu child khi update root; bộ test chỉ so sánh số item mà không đối chiếu ID và metadata của child đã bị tái tạo.
Ứng dụng triển khai lịch sử đơn hàng trên hai bảng; integration test chỉ assert root được lưu mà không kiểm các row bị xóa và thêm trong child table.
Đội QA tạo dữ liệu thử với ID auto increment; production có mã ID được cấp từ hệ thống ngoài nên behavior phân biệt insert và update khác đường test.
Nhóm kiểm thử custom SQL bằng dữ liệu ASCII; production có tên khách chứa emoji và dấu tiếng Việt khiến conversion, collation hoặc độ dài cột xảy ra lỗi.
Ứng dụng test transaction trên H2 với một thread; những deadlock và lock wait xảy ra trên PostgreSQL khi nhiều worker cập nhật cùng aggregate không được tái hiện.
Đội dùng @DataJdbcTest cho SQL thuần nhưng không kiểm callback auditing; trường thời gian được gắn đúng trên đường repository trong khi fragment SQL bỏ qua cập nhật.
Một API lấy hàng trăm Order và đọc children theo từng root; log SQL cho thấy một truy vấn lấy root rồi nhiều truy vấn tải collection gây độ trễ giống N+1.
Nhóm phát triển tăng index cho bảng Order nhưng quên index khóa ngoại trên bảng LineItem; đọc aggregate có nhiều child trở thành truy vấn chậm dù truy vấn root rất nhanh.
Ứng dụng lưu aggregate với hàng nghìn item trong một save; số DELETE và INSERT vào bảng con tăng mạnh và gây áp lực write ahead log trong giờ cao điểm.
Đội vận hành thay đổi cấu hình JdbcTemplate fetch size; một luồng xuất dữ liệu lớn vẫn gom mọi aggregate vào List và hết bộ nhớ trước khi gửi response.
Nhóm triển khai connection pool nhỏ cho ứng dụng JDBC; transaction ghi nhiều aggregate giữ connection quá lâu khiến request mới hết thời gian chờ.
Ứng dụng bật SQL debug logging để điều tra lỗi @Query; giá trị parameter chứa địa chỉ và thông tin cá nhân được ghi vào log tập trung không phù hợp yêu cầu bảo mật.
Đội xây báo cáo theo ngày dùng query count và Pageable; SQL lọc theo cột timestamp chưa có index khiến thời gian response tăng theo quy mô bảng.
Nhóm làm batch nhập dữ liệu bằng saveAll; mỗi aggregate có nhiều child nên số lệnh ghi tăng mạnh, trong khi dashboard chỉ đo số lần gọi repository.
Ứng dụng quản lý hợp đồng yêu cầu soft delete; repository.deleteById đang xóa thật root và các children khiến lịch sử không còn phục vụ kiểm toán.
Đội vận hành chuyển dữ liệu từ JPA sang Spring Data JDBC; màn hình cũ vẫn kỳ vọng lazy loading và dirty checking khiến response thiếu dữ liệu và thay đổi không được lưu.
Nhóm khôi phục database từ snapshot trước migration; bản ứng dụng mới không thể ánh xạ một field embedded vừa được thêm và không có cách theo dõi những aggregate nào lỗi khi đọc.
Ứng dụng bị SIGTERM khi đang save aggregate Order lớn; transaction rollback nhưng một sự kiện phát ra trước commit đã được consumer xử lý và làm hệ thống khác lệch trạng thái.
Đội nâng Spring Data JDBC và Spring Boot trong cùng release; schema cũ vẫn đúng nhưng converter hay chiến lược nhận diện entity mới thay đổi khiến một số save không còn tương thích.
