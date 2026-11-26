Một ứng dụng quản lý đơn hàng dùng Spring Data JPA ánh xạ Order thành entity; bảng production có cột order_id nhưng cấu hình @Column bị bỏ sót và Hibernate đọc nhầm tên cột sau khi nâng cấp naming strategy.
Nhóm phát triển đặt @Entity trên lớp Customer nhưng thiếu @Id cho mã định danh; dịch vụ khởi động thất bại khi tạo EntityManagerFactory dù các bài kiểm thử service bằng mock đều đạt.
Một hệ thống kế toán dùng @GeneratedValue cho mã hóa đơn nhưng database đã cấu hình sequence khác tên; việc tạo hóa đơn mới thất bại trong khi tra cứu hóa đơn cũ vẫn hoạt động.
Ứng dụng bán vé sử dụng IDENTITY cho khóa chính; khi nhập hàng chục nghìn vé bằng saveAll, nhóm vận hành thấy số lượt insert và thời gian xử lý lớn hơn đáng kể dự toán.
Một dịch vụ thanh toán chuyển chiến lược sinh ID từ sequence sang identity; các bản ghi được tạo đồng thời gây ra khoảng trống ID và một báo cáo cũ sai khi giả định ID liên tiếp.
Nhóm phát triển ánh xạ cột giá bán bằng Double trong entity; sau một tháng tính toán, tổng doanh thu lệch vài đơn vị nhỏ so với dữ liệu Decimal mà database đang lưu.
Ứng dụng quản lý hàng tồn dùng BigDecimal cho số lượng quy đổi; schema database định nghĩa precision và scale nhỏ hơn giá trị nghiệp vụ lớn nhất, khiến thao tác lưu thất bại ở production.
Đội kỹ thuật dùng enum ordinal cho trạng thái đơn hàng; khi thêm trạng thái mới vào giữa enum, các bản ghi đã lưu được đọc thành trạng thái không còn đúng ý nghĩa ban đầu.
Một ứng dụng lưu ngày hẹn giao hàng bằng LocalDateTime; các node chạy ở hai múi giờ khác nhau trả thời điểm giao hàng không đồng nhất dù cột database không thay đổi.
Nhóm định nghĩa trường ghi nhận thời điểm giao dịch bằng Instant nhưng schema sử dụng timestamp without time zone; báo cáo từ hai vùng triển khai hiển thị thời gian khác nhau.
Một dịch vụ nhận tên khách hàng tiếng Việt lưu bằng @Column length mặc định; nhiều hồ sơ có tên dài hơn giới hạn bị từ chối khi lưu dù dữ liệu hợp lệ theo yêu cầu sản phẩm.
Ứng dụng lưu địa chỉ dưới dạng @Embeddable; sau khi bổ sung trường mã vùng, hai embedded object cùng dùng trong một entity dẫn tới tên cột trùng nhau.
Một hệ thống quản lý thiết bị dùng @EmbeddedId gồm mã kho và mã thiết bị; sau khi đổi cách implement equals và hashCode, các thực thể cùng khóa bị xem là khác khi xử lý tập hợp.
Nhóm vận hành nhập dữ liệu cũ có khóa ghép nhưng repository dùng khóa đơn; các thao tác findById trả nhầm hoặc bỏ sót bản ghi khi mã trùng giữa hai chi nhánh.
Ứng dụng bán lẻ ánh xạ Customer có tập Order bằng @OneToMany; khi serialize trực tiếp entity thành JSON, tham chiếu hai chiều gây đệ quy và response không thể hoàn tất.
Dịch vụ quản lý dự án thêm @ManyToOne từ Task tới Project; một số task cũ có project_id null nhưng mapping đánh dấu bắt buộc, khiến đọc dữ liệu cũ bị lỗi.
Nhóm phát triển ánh xạ quan hệ @ManyToMany giữa User và Role; sau khi xóa một người dùng, các bản ghi join table còn tồn tại làm báo cáo phân quyền không thống nhất.
Một hệ thống bán hàng gắn cascade REMOVE cho quan hệ Order và Product dùng chung; khi xóa một order, thao tác xóa lan tới sản phẩm vẫn được nhiều đơn khác tham chiếu.
Ứng dụng hóa đơn có tập LineItem với orphanRemoval; khi cập nhật order bằng cách thay toàn bộ collection, nhiều line item chưa thay đổi vẫn bị xóa và tạo lại.
Nhóm nhập dữ liệu nhận một Order với nhiều LineItem; chỉ có phía không sở hữu quan hệ được cập nhật, khiến cột khóa ngoại trong database vẫn null sau khi save.
Đội bảo trì đổi quan hệ OneToMany từ List sang Set; cách định nghĩa equals của entity con chỉ dựa vào ID chưa sinh làm hai dòng hàng mới biến mất khỏi tập hợp.
Một ứng dụng lưu danh sách số điện thoại dưới dạng @ElementCollection; khi sửa một phần tử, SQL log cho thấy nhiều dòng của collection bị xóa và thêm lại gây tăng chi phí ghi.
Nhóm thiết kế entity kế thừa cho các loại phương tiện; sau khi đổi chiến lược JPA inheritance, truy vấn trả thông tin chung nhanh hơn nhưng báo cáo theo subtype phát sinh nhiều JOIN.
Một hệ thống thu phí dùng @MappedSuperclass chứa audit fields; một lớp con ghi đè mapping tên cột làm bảng phụ có dữ liệu thời gian khác định nghĩa chung.
Đội triển khai gán một entity thuộc tính @Transient cho giá trị tính tạm; nhóm tích hợp tưởng đó là cột được lưu nên dữ liệu mất sau khi đọc lại từ repository.
Ứng dụng bảo trì thiết bị dùng AttributeConverter để mã hóa trường serialNumber; khi tra cứu theo serialNumber bằng derived query, giá trị nhập được chuyển đổi không như cách người dùng dự đoán.
Nhóm phát triển thêm converter cho kiểu Money dùng chung; dữ liệu cũ ở production có đơn vị tiền tệ khác với mặc định mới khiến báo cáo giá trị không nhất quán.
Một service dùng JpaRepository với derived query findByEmailIgnoreCase để tìm khách; hệ thống có hai account khác chữ hoa nhưng cùng email chuẩn hóa nên trả nhiều kết quả khi method chỉ mong một khách.
Ứng dụng khai báo findByStatusAndCreatedAtBetween cho Order; khi truy vấn qua hai ranh giới ngày, bản ghi đúng tại phút cuối bị bỏ do định nghĩa mốc thời gian không đồng nhất.
Nhóm dùng findFirstByCustomerIdOrderByCreatedAtDesc để lấy đơn mới nhất; hai order có cùng timestamp nên mỗi lần gọi có thể trả ID khác nhau.
Một hệ thống quản lý hợp đồng định nghĩa findByCustomerAddressCity; sau khi model thêm thuộc tính customerAddress, parser derived query không còn suy luận đúng đường thuộc tính lồng nhau.
Nhóm phát triển thêm findByStatusOrPriorityAndRegion mà không phân nhóm điều kiện; danh sách đơn hàng ưu tiên hiển thị cả những đơn ngoài vùng được phép.
Một ứng dụng repository trả Optional<Order> cho câu tìm theo mã giao dịch; dữ liệu production chứa hai bản ghi trùng mã khiến truy vấn đơn lẻ phát sinh lỗi khi nhận nhiều kết quả.
Đội vận hành chạy existsById trước khi thêm mã vận đơn mới; hai giao dịch đồng thời cùng thấy chưa tồn tại và tạo ra xung đột unique constraint lúc lưu.
Một dịch vụ dùng countByStatus cho dashboard thời gian thực; bảng có hàng chục triệu dòng và truy vấn đếm liên tục gây áp lực lớn lên database giờ cao điểm.
Nhóm bán hàng định nghĩa deleteByExpiredTrue để dọn đơn tạm; sau khi thêm lifecycle callback, đội phát hiện hành vi callback khi xóa theo từng entity khác thao tác bulk delete.
Ứng dụng tích hợp sử dụng @Query JPQL với tên class entity đã đổi nhưng tên bảng SQL giữ nguyên; repository khởi tạo lỗi vì truy vấn vẫn tham chiếu tên entity cũ.
Nhóm phát triển dùng JPQL JOIN giữa Order và Customer để lấy dữ liệu báo cáo; điều kiện lọc ở WHERE khiến những order chưa gắn khách bị bỏ khỏi kết quả ngoài ý định.
Dịch vụ bảo hiểm sử dụng JPQL constructor expression để trả DTO; sau khi thay kiểu đối số constructor, query chạy đến lúc được gọi mới báo không thể tạo DTO.
Ứng dụng tìm kiếm sản phẩm dùng @Query với tham số tên; khi refactor tên biến method mà không sửa @Param, truy vấn trả lỗi binding trong một endpoint ít sử dụng.
Nhóm xây query động bằng cách nối phần điều kiện do người dùng nhập vào JPQL; một giá trị có ký tự đặc biệt làm truy vấn lỗi và đặt ra rủi ro truy vấn không an toàn.
Một hệ thống chấm công dùng JPQL FUNCTION để gọi hàm thời gian của database; test H2 thành công nhưng production PostgreSQL không chấp nhận cùng tên hàm hoặc kiểu tham số.
Đội phát triển dùng native SQL trong @Query để tổng hợp doanh thu nhiều bảng; khi đổi tên cột do migration, entity mapping vẫn hoạt động nhưng native query chỉ lỗi ở báo cáo cuối tháng.
Ứng dụng tìm kiếm dùng native query với alias không khớp getter của interface projection; một số field được trả null dù SQL console cho kết quả đúng.
Nhóm thêm native query trả Page<Invoice> nhưng không khai báo cách đếm phù hợp; số trang hiển thị sai khi SQL có GROUP BY và nhiều JOIN.
Một dịch vụ cần truy vấn phân tích theo window function SQL; nhóm thử chuyển nguyên truy vấn sang JPQL và ứng dụng lỗi khi parser không hỗ trợ biểu thức cụ thể.
Ứng dụng có query lọc theo danh sách ID; client gửi danh sách rỗng và SQL sinh ra không hợp lệ trên một database trong khi test dùng database khác vẫn đạt.
Nhóm viết JPQL tìm các Order không có LineItem; dữ liệu có nhiều order dòng trống nhưng cách dùng JOIN làm truy vấn không trả những bản ghi cần xử lý.
Một báo cáo hiển thị Order cùng nhiều Payment; JOIN cả hai collection một cách thiếu kiểm soát làm mỗi order xuất hiện nhiều dòng và tổng doanh thu bị nhân lên.
Đội phát triển dùng DISTINCT trong JPQL để tránh trùng kết quả; query count của Page vẫn tính theo các dòng JOIN nên totalElements sai với nội dung trang.
Ứng dụng quản lý hợp đồng chạy @Modifying update theo điều kiện trạng thái; sau khi thao tác hoàn tất, entity đã tải sẵn trong PersistenceContext vẫn chứa trạng thái cũ.
Nhóm thực hiện bulk delete bằng JPQL để tăng tốc; các callback xóa entity và quy tắc cascade mà nghiệp vụ từng dựa vào không chạy giống cách xóa từng entity.
Một service cập nhật hàng nghìn bản ghi bằng @Modifying nhưng method không chạy trong transaction ghi phù hợp; truy vấn lỗi tại runtime dù query đúng cú pháp.
Đội phát triển thêm clearAutomatically cho bulk update; sau khi method thực thi, các thay đổi chưa flush trong context bị bỏ và dữ liệu nghiệp vụ vừa sửa không còn được lưu.
Ứng dụng dùng native update để cộng tồn kho theo ID; hai hệ thống khác nhau cùng thay đổi tồn kho và bảng lịch sử ứng dụng không phản ánh được tác động trực tiếp này.
Nhóm xây Specification JPA để tìm đơn theo nhiều bộ lọc tùy chọn; một predicate luôn được thêm mặc dù user bỏ trống form làm danh sách bị loại quá nhiều bản ghi.
Một dịch vụ sử dụng Specification kết hợp AND/OR cho tìm khách hàng; điều kiện tenant được ghép sai nhánh OR khiến một truy vấn có thể đọc dữ liệu ngoài phạm vi tổ chức.
Đội phát triển xây Criteria API với JOIN nhiều bảng theo tùy chọn tìm kiếm; khi cả hai bộ lọc được bật, số dòng trả về tăng bất thường vì thiếu ràng buộc giữa các JOIN.
Ứng dụng dùng Query by Example để lọc sản phẩm; trường giá mặc định trong probe vô tình áp điều kiện bằng không làm người dùng không tìm thấy mặt hàng hợp lệ.
Nhóm QA tạo test Specification chỉ với một điều kiện; khi khách gửi đồng thời bộ lọc ngày, vùng và trạng thái, phương thức đếm cho phân trang trả kết quả khác query chính.
Một trang quản trị sử dụng PageRequest cho danh sách người dùng; client tính trang đầu là 1 còn repository đánh số từ 0 khiến giao diện bỏ qua trang đầu tiên.
Nhóm cấu hình Pageable với page size bằng giá trị do client gửi; một request không giới hạn có thể tạo truy vấn trả hàng trăm nghìn entity và tiêu tốn heap lớn.
Ứng dụng sử dụng Page<Order> để lấy 20 đơn và tổng số đơn; sau khi JOIN nhiều quan hệ, count query trở thành truy vấn chậm nhất của trang dù dữ liệu hiển thị ít.
Đội phát triển đổi endpoint từ Page sang Slice để giảm overhead đếm; ứng dụng di động cũ vẫn yêu cầu totalPages và không biết khi nào hết dữ liệu.
Một dịch vụ danh sách giao dịch dùng offset pagination; trong lúc người dùng lật trang, giao dịch mới được thêm làm một số dòng xuất hiện hai lần và số khác không bao giờ được hiển thị.
Nhóm sắp xếp sản phẩm theo updatedAt giảm dần; nhiều bản ghi có cùng timestamp dẫn tới thứ tự khác nhau giữa hai request phân trang sát nhau.
Ứng dụng cho phép người dùng gửi Sort theo tên field bất kỳ; một thuộc tính liên quan đến collection khiến truy vấn sort bị nhân dòng hoặc trả lỗi trên production.
Đội phát triển dùng native query cho báo cáo có Pageable; một thay đổi của database dialect khiến cách áp LIMIT/OFFSET khác môi trường test và trang cuối trả sai dữ liệu.
Một service dùng keyset scrolling theo createdAt và ID; một bản ghi đổi createdAt khi user đang cuộn khiến kết quả có nguy cơ bị bỏ qua hoặc lặp.
Nhóm xuất file nhiều triệu record bằng findAll; chương trình cạn bộ nhớ dù SQL query chỉ mất vài giây để database thực thi.
Ứng dụng trả Stream<Order> từ repository để xử lý từng record; stream được tiêu thụ sau khi transaction và EntityManager đã đóng nên đọc dữ liệu liên quan thất bại.
Một job xử lý hàng triệu item theo trang; trong mỗi trang, context giữ tất cả entity đã đọc làm bộ nhớ tăng dần dù mã nghiệp vụ chỉ cần kết quả đã tổng hợp.
Đội thiết kế endpoint tìm khách hàng bằng interface projection; truy vấn có nhiều nested relation nên trong lúc serialize, việc đọc thêm trường liên quan gây N+1 không được nhìn thấy trong test ít dữ liệu.
Ứng dụng trả DTO projection từ @Query JPQL; thứ tự đối số trong constructor expression khác constructor hiện có nên một endpoint trả lỗi khi có kết quả.
Nhóm thêm một getter SpEL vào open projection; thông tin hiển thị đúng nhưng query không còn được tối ưu như closed projection và latency tăng.
Một service dùng dynamic projection để phục vụ cả mobile và web; client API chọn loại DTO có dữ liệu nhạy cảm mà middleware phân quyền không kiểm soát.
Ứng dụng tạo interface projection trên native query; alias cột có dấu gạch dưới không khớp tên property Java khiến trường amountDue bị trả về null.
Đội phát triển chuyển projection từ entity sang record DTO; một trường mới không có trong query làm bộ ánh xạ thất bại ở runtime dù repository vẫn được tạo.
Nhóm đánh giá hiệu năng chỉ đo thời gian repository trả DTO; serializer gọi thêm getter lazy từ DTO lồng nhau làm số SQL thực tế nhiều hơn số đo trong service.
Ứng dụng gọi findAll cho 50 đơn rồi duyệt từng order.getItems; Hibernate phát một truy vấn cho danh sách order và nhiều truy vấn bổ sung theo từng đơn gây N+1.
Nhóm đổi quan hệ Order.customer thành EAGER để tránh LazyInitializationException; các endpoint chỉ cần số đơn vẫn tải dữ liệu khách hàng và tạo truy vấn dư thừa.
Một dịch vụ dùng LAZY cho danh sách item rồi chuyển entity trực tiếp ra JSON; serializer truy cập collection sau khi session đóng và ném LazyInitializationException.
Đội bật Open Session in View để trang chi tiết đọc được dữ liệu lazy; sau khi traffic tăng, query phát sinh trong quá trình render kéo dài thời gian giữ kết nối database.
Ứng dụng sử dụng JOIN FETCH để lấy Order và Customer; khi thêm truy vấn phân trang kèm collection fetch, các trang có thể bị cắt sai hoặc framework phải phân trang trong bộ nhớ.
Nhóm khai báo @EntityGraph cho màn hình chi tiết khách hàng; một lần thêm collection thứ hai làm số dòng JOIN tăng đột biến và request bị chậm.
Đội phát triển có hai quan hệ List kiểu bag cần fetch cùng lúc; khi thêm fetch join cho cả hai, Hibernate không thể tải đồng thời như yêu cầu mà nhóm chưa nhận ra.
Ứng dụng đặt hibernate.default_batch_fetch_size để giảm N+1; khi kích thước dữ liệu đầu vào thay đổi, số truy vấn giảm nhưng memory và thời gian xử lý vẫn tăng bất thường.
Một service chạy query lấy 100 Order nhưng mỗi Order chứa hàng nghìn LineItem; cách fetch toàn bộ quan hệ cho một trang danh sách khiến response nhỏ vẫn tải lượng dữ liệu quá lớn.
Nhóm dùng subselect fetch cho collection; trong một luồng truy vấn nhiều nhóm Order liên tiếp, số item được nạp vượt xa tập người dùng thực sự muốn xem.
Ứng dụng tìm đơn theo Product rồi join thêm các item của Order; entity result bị lặp theo số line item và thao tác đưa vào Set làm count trên màn hình không khớp SQL.
Đội vận hành phân tích slow query trên trang báo cáo; nguyên nhân không nằm ở SQL đầu tiên mà ở hàng trăm query lazy khi mapping kết quả thành DTO.
Một microservice tạo danh sách sản phẩm và truy cập category.name từ mỗi entity; môi trường test chỉ có ba category nên N+1 không được nhận biết trước khi production có hàng nghìn category.
Ứng dụng có transaction ở tầng service nhưng gọi repository theo nhiều bước; một bước trả về entity đã detach rồi các cập nhật ở bước sau không được tự theo dõi bởi dirty checking.
Nhóm xử lý đặt hàng cập nhật thuộc tính của managed entity trong @Transactional; sau khi refactor thành DTO rồi sửa DTO, thay đổi không còn tự động được flush xuống database.
Đội phát triển gọi save trong một service không có transaction bao quanh toàn bộ quy trình; từng repository call commit riêng làm workflow nghiệp vụ còn dữ liệu một phần khi bước cuối lỗi.
Một API chuyển tiền ghi trừ số dư tài khoản A rồi cộng vào tài khoản B; hai thao tác nằm trong transaction khác nhau và lỗi giữa chừng tạo chênh lệch tổng tiền.
Ứng dụng dùng @Transactional(readOnly=true) cho hàm truy vấn rồi gọi một method sửa entity bên trong; thay đổi không được ghi như nhóm tưởng ở một số cấu hình persistence.
Nhóm dùng @Transactional trên method private xử lý nghiệp vụ; lời gọi nội bộ không đi qua proxy khiến ranh giới transaction thực tế khác tài liệu thiết kế.
Một service dùng @Transactional cho method được gọi từ method khác cùng class; nhóm mong propagation riêng nhưng self-invocation không kích hoạt interceptor như kỳ vọng.
Ứng dụng gửi email thông báo khi giao dịch database còn mở; email đã gửi nhưng transaction bị rollback vì một constraint ở bước cuối.
Nhóm đặt @Transactional trên controller rồi gọi API đối tác kéo dài; connection database và lock bị giữ qua thời gian chờ mạng khiến throughput giảm.
Một job nhập sản phẩm xử lý hàng nghìn bản ghi trong một transaction; lỗi duy nhất gần cuối làm rollback toàn bộ và lock tồn tại nhiều phút.
Ứng dụng gọi saveAndFlush sau mỗi item để kiểm dữ liệu; lượng round trip SQL và flush tăng mạnh khiến chức năng nhập hàng loạt chậm đáng kể.
Một service dùng flush để ép SQL chạy trước khi gọi dịch vụ ngoài; transaction chưa commit nên bên ngoài vẫn không thể nhìn thấy dữ liệu mà service tưởng đã được lưu.
Nhóm đọc entity trong transaction rồi gọi EntityManager.clear; phần thay đổi chưa được flush trên entity bị detach và không được ghi sau khi kết thúc service.
Ứng dụng có phương thức nghiệp vụ với propagation REQUIRES_NEW để ghi audit; nghiệp vụ chính rollback nhưng bản ghi audit đã commit khiến báo cáo trạng thái phải diễn giải rõ sự khác biệt.
Nhóm dùng nested business call từ hai service khác nhau; một ngoại lệ đã đánh dấu transaction rollback-only nhưng controller vẫn cố commit và trả lỗi ngoài dự kiến.
Một dịch vụ dùng transaction isolation mặc định để kiểm số lượng vé còn lại; hai request đồng thời cùng thấy còn một vé và đều xác nhận đặt chỗ.
Ứng dụng phân bổ mã voucher trong transaction; khi hai nhân viên chọn cùng mã chưa dùng, một phiên bị lỗi khóa hoặc dữ liệu trùng tùy cách cập nhật.
Nhóm vận hành thấy deadlock khi hai transaction cập nhật Order và Inventory theo thứ tự đối nghịch; số lỗi tăng vào giờ cao điểm nhưng test tuần tự đều đạt.
Ứng dụng chạy một transaction truy vấn nhiều lần danh sách đơn chưa thanh toán; dữ liệu được thêm bởi phiên khác trong lúc đang xử lý khiến điều kiện nghiệp vụ thay đổi giữa các lượt đọc.
Một service tải entity Balance có @Version, hai request cùng tăng số dư; request thứ hai gặp OptimisticLockException khi phiên bản đã được người khác cập nhật.
Đội phát triển xóa trường @Version khỏi entity để giảm cột database; các cập nhật đồng thời không còn cơ chế phát hiện ghi đè và dữ liệu hồ sơ bị mất.
Ứng dụng dùng optimistic locking khi chỉnh hồ sơ nhưng API không truyền version; người dùng mở form cũ rồi lưu đè thay đổi của đồng nghiệp mà không có cảnh báo.
Nhóm thử retry OptimisticLockException ngay trên entity đã stale; mọi lần thử tiếp tục thất bại vì state và version ban đầu không được thay đổi.
Ứng dụng đặt @Lock(PESSIMISTIC_WRITE) trên repository method cấp mã khuyến mãi; nhiều request cùng tới khiến thời gian đợi lock tăng cao và client timeout.
Đội vận hành dùng pessimistic locking khi đọc danh sách đơn; một transaction chỉ xem dữ liệu giữ lock lâu khiến các thao tác cập nhật bị chặn.
Một service truyền lock timeout hint cho truy vấn JPA; môi trường PostgreSQL và database test diễn giải hoặc hỗ trợ timeout khác nhau khiến hành vi chờ khóa không tương đương.
Ứng dụng áp dụng @Lock(PESSIMISTIC_READ) để xem tồn kho; hai transaction cùng cố nâng lên lock ghi và gặp deadlock trong tình huống cạnh tranh.
Nhóm dùng query update trực tiếp thay đổi tồn kho nhưng không kiểm version; optimistic locking trên entity đã có không phát hiện cập nhật từ một luồng bulk.
Một hệ thống sản xuất lưu entity có version trong bảng; sau khi import dữ liệu legacy không có version, lần cập nhật đầu gặp vấn đề khi kiểm tra giá trị phiên bản.
Đội QA chỉ kiểm concurrency với hai thread trên H2; production PostgreSQL có isolation, deadlock và lock timeout khác khiến nhiều request đặt hàng thất bại.
Ứng dụng đặt transaction boundary quanh một xử lý bất đồng bộ CompletableFuture; luồng thực thi thứ hai không tự có cùng PersistenceContext nên truy cập lazy relation thất bại.
Nhóm gửi sự kiện application event trong transaction; listener ghi vào database khác trước khi transaction nguồn commit khiến event ghi nhận sự thay đổi sau đó bị rollback.
Một dịch vụ gọi repository từ handler WebFlux trên event-loop; thao tác JPA blocking làm chậm các request khác dù handler khai báo trả Mono.
Ứng dụng sử dụng EntityManager trong một thread pool tùy biến rồi chia sẻ instance cho nhiều worker; trạng thái managed entity và flush bị lẫn giữa các tác vụ.
Nhóm dùng auditing @CreatedDate và @LastModifiedDate cho entity hóa đơn; lịch sử import từ hệ thống cũ bị ghi thời gian hiện tại thay vì thời điểm tạo nghiệp vụ.
Ứng dụng bật @CreatedBy qua AuditorAware dựa vào SecurityContext; các tác vụ batch chạy không có user session nên trường người tạo trống và vi phạm ràng buộc NOT NULL.
Đội phát triển thêm @LastModifiedBy cho entity; một sự kiện Kafka xử lý trên thread riêng sử dụng danh tính mặc định không phù hợp với tài khoản đã gây ra thay đổi.
Một microservice đặt audit fields vào @MappedSuperclass; một entity con không được đăng ký auditing listener như dự kiến nên createdDate không được điền khi lưu.
Ứng dụng sử dụng @PrePersist callback để tính mã nghiệp vụ; một thao tác bulk insert thực hiện bên ngoài EntityManager không chạy callback và mã định danh bị thiếu.
Nhóm ghi audit log từ @PostUpdate listener; một lần flush và retry transaction khiến log ghi sự kiện đã sửa dù transaction cuối cùng chưa commit.
Một dịch vụ lấy thời gian từ database để thống nhất auditing nhưng một entity khác dùng đồng hồ của JVM; báo cáo sắp xếp lịch sử sửa có thứ tự không chính xác giữa hai nguồn.
Đội thiết kế soft delete bằng cột deletedAt; repository findAll mặc định vẫn trả entity đã xóa trong một luồng và làm lộ hồ sơ không còn hiệu lực.
Ứng dụng dùng bộ lọc tenant trong truy vấn JPQL tự viết; một native SQL báo cáo bỏ quên điều kiện tenant khiến dữ liệu của tổ chức khác xuất hiện trong kết quả.
Nhóm mã hóa trường số tài khoản bằng converter; native query projection trả chuỗi đã mã hóa thay vì giá trị được giải mã theo các truy vấn entity thông thường.
Một service dùng @DataJpaTest để kiểm repository với H2; SQL native chạy thành công ở test nhưng fail trên PostgreSQL vì kiểu JSONB và cú pháp đặc thù.
Đội kiểm thử repository bằng Testcontainers PostgreSQL; bộ test chỉ có schema được Hibernate tạo tự động nên không phát hiện migration Flyway khác production.
Ứng dụng chạy @DataJpaTest với rollback mặc định; bài test tạo nhiều dữ liệu thành công nhưng luồng thực tế commit gặp unique constraint được kiểm ở cuối transaction.
Nhóm QA viết test repository cho query có phân trang; database test chỉ có vài chục dòng nên không phát hiện kết quả sai khi count query chứa join trùng dữ liệu.
Một dịch vụ dùng @Sql để tạo dữ liệu kiểm thử; hai testcase chạy song song trên cùng database gây va chạm khóa chính và tạo kết quả flaky.
Đội kiểm thử lazy loading với Open Session in View được bật trong test; production tắt cấu hình này nên endpoint ném LazyInitializationException khi serialize.
Ứng dụng đo số SQL trong test khi lấy danh sách đơn; bộ dữ liệu chỉ một khách hàng nên không thể phát hiện N+1 tăng theo số order trong production.
Nhóm test cập nhật đồng thời bằng hai transaction; việc dùng chung EntityManager trong test làm cả hai request thấy cùng state cache và không tái hiện race thực tế.
Ứng dụng chạy test optimistic lock trên entity đã được lưu; test không dùng hai persistence context độc lập nên không phát hiện lỗi ghi đè khi hai người cùng sửa.
Đội phát triển nâng Hibernate và Spring Data JPA trong cùng đợt; một query JPQL tùy biến vẫn biên dịch nhưng runtime báo lỗi parser sau thay đổi phiên bản.
Nhóm đặt hibernate.hbm2ddl.auto=update trên production để tiện triển khai; một thay đổi entity làm schema tự điều chỉnh khác migration đã được phê duyệt.
Một hệ thống có bảng vài trăm triệu dòng; query derived theo trường chưa có index chậm hàng phút nhưng test repository vẫn trả kết quả đúng trên dữ liệu nhỏ.
Đội vận hành thêm index cho truy vấn tìm đơn theo trạng thái; báo cáo sắp xếp theo createdAt vẫn chậm vì tổ hợp điều kiện thực tế khác cấu trúc index.
Ứng dụng dùng fetch join để giảm N+1 cho báo cáo; join nhiều collection tạo số dòng trung gian khổng lồ và response chậm dù số SQL query rất ít.
Nhóm bật SQL logging mức DEBUG khi điều tra incident; các parameter chứa thông tin nhạy cảm xuất hiện trong log tập trung và tạo rủi ro bảo vệ dữ liệu.
Một dịch vụ tăng hibernate.jdbc.batch_size để tăng tốc insert; batch vẫn không đạt hiệu năng dự kiến vì chiến lược ID và cách flush không phù hợp.
Nhóm nhập dữ liệu với saveAll và chỉ nhìn số lần gọi repository; thời gian tăng vì persistence context giữ hàng trăm nghìn entity trước khi commit.
Ứng dụng dùng second-level cache cho danh mục sản phẩm; một hệ thống khác cập nhật database trực tiếp khiến cache giữ giá cũ dù dữ liệu SQL đã thay đổi.
Nhóm kích hoạt query cache cho báo cáo doanh thu; sau khi ghi dữ liệu bằng native SQL không được đồng bộ cache như dự kiến, kết quả người dùng xem bị cũ.
Ứng dụng có connection pool giới hạn nhỏ nhưng nhiều request @Transactional giữ kết nối trong lúc gọi dịch vụ ngoài; cuối ngày các request mới timeout dù database còn CPU rảnh.
Đội QA benchmark repository với dữ liệu nằm hoàn toàn trong cache; ở production đọc từ ổ đĩa và join nhiều bảng nên p95 latency cao hơn đáng kể.
Một endpoint trả Page<Entity> trực tiếp và chứa quan hệ customer/items; serializer kích hoạt thêm SQL và vô tình hiển thị thông tin khách hàng không thuộc phạm vi quyền người xem.
Nhóm tích hợp sau rollback ứng dụng vẫn dùng schema vừa được migration lên phiên bản mới; ánh xạ cột entity phiên bản cũ không còn tương thích và một số repository không thể truy vấn.
Ứng dụng chốt doanh thu đang chạy transaction dài thì Kubernetes gửi SIGTERM; tiến trình bị dừng trước commit khiến báo cáo API và dữ liệu đích phải được đối soát sau restart.
Đội phát triển chỉ kiểm thời gian query tại database; phần mapping hàng trăm nghìn entity và dirty checking của JPA tiêu tốn phần lớn CPU nhưng không xuất hiện trong slow SQL dashboard.
Nhóm xây báo cáo cuối tháng dựa trên entity audit fields; một loạt cập nhật @Modifying bulk không cập nhật lastModifiedDate như đường save thông thường nên dữ liệu báo cáo thiếu lịch sử thay đổi.
