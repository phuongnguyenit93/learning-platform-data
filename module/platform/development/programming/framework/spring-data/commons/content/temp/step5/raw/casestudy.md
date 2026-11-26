Một nền tảng bán lẻ khai báo OrderRepository kế thừa Repository nhưng không có các phương thức CRUD công khai; nhóm phát triển kỳ vọng tìm được save khi triển khai một màn hình chỉnh sửa đơn hàng.
Ứng dụng quản lý khách hàng dùng CrudRepository cho thao tác lưu và đọc; sau lần nâng Spring Data, đội kỹ thuật đổi sang PagingAndSortingRepository và phát hiện các phương thức CRUD cũ không còn nằm trong interface đã chọn.
Nhóm phát triển chọn ListCrudRepository để trả danh sách sản phẩm; bộ xử lý hiện tại vẫn khai báo nhận Iterable và việc kiểm tra các kết quả rỗng trở nên không thống nhất giữa các module.
Một dịch vụ tài chính định nghĩa Repository với kiểu ID là Long nhưng entity thực tế dùng UUID; lỗi chỉ xuất hiện khi người dùng tra cứu giao dịch bằng mã định danh thật.
Đội bảo trì tạo một interface repository cơ sở chứa phương thức dùng chung; Spring Data cố tạo bean cho chính interface trừu tượng này và báo không tìm được domain type khi khởi động.
Một ứng dụng chứa hai interface repository có tên giống nhau ở hai package; cơ chế component scan tạo bean khó phân biệt và một service nhận repository của miền dữ liệu khác.
Nhóm quản lý kho bật repository scanning quá rộng sau khi tách thành nhiều module; interface ở module thử nghiệm được tạo thành bean production và kết nối đến nguồn dữ liệu không mong muốn.
Ứng dụng sử dụng nhiều loại Spring Data module cùng trên classpath; một repository không có đặc điểm nhận diện store rõ ràng khiến cấu hình nhiều kho dữ liệu không thể chọn module quản lý phù hợp.
Một dự án dùng interface Repository tùy biến để ẩn delete khỏi nghiệp vụ; service khác vẫn truy cập được thao tác xóa qua một bean repository rộng hơn và vi phạm giới hạn quyền được kỳ vọng.
Nhóm viết generic base repository cho nhiều entity nhưng đặt giới hạn type parameter không phù hợp; một repository chuyên biệt không thể được tạo proxy dù class domain đã được ánh xạ.
Dịch vụ đơn hàng cần lưu entity mới và cập nhật entity đã có bằng save; cùng payload nhưng trạng thái nhận diện entity mới thay đổi khi ID được ứng dụng tự gán trước khi lưu.
Một hệ thống giao vận dùng ID gán từ bên ngoài thay vì database; Spring Data nhận diện aggregate có ID sẵn như dữ liệu đã tồn tại và quá trình persist khác với kỳ vọng của nhóm phát triển.
Ứng dụng kế toán triển khai Persistable để tùy chỉnh isNew; cờ isNew giữ nguyên sau lần lưu đầu khiến cùng đối tượng tiếp tục được xử lý như entity mới ở những lần lưu kế tiếp.
Một service lưu nhiều bản ghi bằng saveAll rồi dùng số lượng trả về để kết luận mọi bản ghi đã commit; một ngoại lệ ở tầng lưu trữ khiến thực tế dữ liệu không đúng như giả định.
Nhóm phát triển dùng findById cho hồ sơ khách hàng và gọi get trực tiếp lên Optional; API trả lỗi 500 khi khách cung cấp mã không tồn tại thay vì phản hồi nghiệp vụ phù hợp.
Ứng dụng thay đổi kiểu ID từ số sang chuỗi sau khi tích hợp nguồn dữ liệu mới; các request cũ vẫn truyền số và repository đọc sai đối tượng ở một số luồng.
Một dịch vụ hỗ trợ khách hàng gọi deleteById nhiều lần vì client tự động retry; các kho dữ liệu hoặc phiên bản thư viện có hành vi khác nhau khi bản ghi đã không còn.
Nhóm quản trị dùng existsById để kiểm tra trước khi lưu bản ghi mới; hai request đồng thời đều nhận kết quả chưa tồn tại và tạo xung đột dữ liệu khi ghi.
Một ứng dụng gọi count trên repository sau mỗi lần hiển thị dashboard; bộ dữ liệu hàng chục triệu bản ghi làm thao tác đếm trở thành điểm nghẽn dù trang chỉ cần vài dòng.
Dịch vụ xuất dữ liệu dùng findAll rồi lọc kết quả bằng Java; lượng khách hàng tăng mạnh khiến memory của ứng dụng tăng theo toàn bộ tập dữ liệu.
Nhóm tích hợp xóa tất cả dữ liệu qua deleteAll trong một công việc bảo trì; sự khác biệt giữa các backing store về transaction và bulk operation khiến kết quả sau lỗi khó dự đoán.
Ứng dụng lưu danh sách aggregate có quan hệ lồng nhau; một lời gọi save được nhóm phát triển hiểu là tự động lưu mọi object liên quan dù khả năng cascade phụ thuộc module lưu trữ.
Một hệ thống cập nhật thông tin khách hàng ở hai tiến trình; cả hai đọc cùng phiên bản entity rồi lần ghi sau ghi đè thông tin của lần trước mà bộ test CRUD đơn luồng không phát hiện.
Nhóm quản lý số dư dùng trường version để phát hiện cập nhật cạnh tranh; một module Spring Data khác không xử lý cơ chế khóa theo cách giống JPA và hai tiến trình vẫn tranh chấp.
Ứng dụng xây repository cho kho document NoSQL và kho quan hệ; cả hai cùng gọi save nhưng quy tắc thay thế document và cập nhật từng cột tạo ra tác động khác khi trường không có giá trị.
Một dịch vụ ghi lịch sử thay đổi chỉ sau khi save trả về; repository bên dưới xử lý ghi bất đồng bộ nên thứ tự giữa cập nhật dữ liệu và bản ghi audit không như kỳ vọng.
Nhóm phát triển thêm phương thức findByEmail vào CustomerRepository; tên thuộc tính domain đã đổi từ email sang primaryEmail làm proxy repository không thể tạo khi khởi động.
Một ứng dụng tìm kiếm đơn hàng dùng findByStatusAndCreatedAtAfter; khi đổi kiểu status sang enum mới, một số giá trị client gửi lên không còn tương thích với derived query.
Dịch vụ kho định nghĩa findByWarehouseAddressCity; domain đồng thời có thuộc tính warehouseAddress và object warehouse.address nên trình phân tích tên phương thức chọn đường thuộc tính khác kỳ vọng.
Nhóm làm chức năng lọc khách hàng theo tên có chứa từ khóa bằng findByNameContaining; dữ liệu chứa phần trăm và dấu gạch dưới làm kết quả khác giữa những module lưu trữ.
Một trang quản trị cần tìm email không phân biệt chữ hoa chữ thường; phương thức findByEmailIgnoreCase chạy đúng ở môi trường test nhưng production có collation và store khác.
Ứng dụng tìm sản phẩm theo giá nằm giữa hai giới hạn; truy vấn derived Between được dùng với đầu mút làm tròn khác nên sản phẩm đúng tại ranh giới bị tính sai.
Nhóm thiết kế phương thức findByStatusOrPriorityAndRegion; kết quả không khớp nhóm điều kiện nghiệp vụ vì thứ tự kết hợp AND và OR trong tên phương thức không được hiểu thống nhất.
Một service tìm giao dịch theo trạng thái không phải CANCELLED; các bản ghi có status null xuất hiện trong kho dữ liệu nhưng truy vấn phủ định cho kết quả khác bộ lọc Java.
Ứng dụng xử lý hợp đồng tìm theo trường nested customer.address.zipCode; khi một thuộc tính ở giữa có thể null, các store trả kết quả khác với kỳ vọng của sản phẩm.
Nhóm phát triển thêm dấu gạch dưới vào tên phương thức truy vấn để làm rõ ranh giới thuộc tính lồng nhau; một thay đổi tên field làm phương thức cũ trở thành không hợp lệ.
Một dự án chuyển domain field từ active sang isActive; derived query findByActive không còn tìm được property phù hợp và lỗi xảy ra ngay khi Spring tạo bean.
Ứng dụng quản lý hóa đơn dùng findTop10ByCustomerIdOrderByCreatedAtDesc; nhiều hóa đơn có cùng timestamp làm kết quả top 10 thay đổi giữa các lượt truy vấn.
Nhóm dùng findFirstByOrderByUpdatedAtDesc để lấy tài liệu mới nhất; dữ liệu được nhập lại từ hệ thống cũ có updatedAt giống nhau khiến bản ghi được chọn không ổn định.
Dịch vụ thống kê có findDistinctByCustomerName; đội sản phẩm tưởng loại được bản ghi khách hàng trùng tên nhưng truy vấn vẫn trả nhiều entity khác ID.
Ứng dụng muốn đếm số khách hàng khác nhau qua countDistinctByLastName; kết quả lệch so với số họ duy nhất mà người dùng đếm trên giao diện.
Một backend cung cấp phương thức existsByUsernameIgnoreCase; hai người dùng đăng ký gần đồng thời với cách viết chữ hoa khác nhau khiến việc kiểm tra tồn tại không đủ để ngăn trùng.
Nhóm triển khai deleteByStatus cho một store dữ liệu; callback và số lượng đối tượng được xóa khác giữa cách xóa theo từng entity với thao tác xóa hàng loạt.
Ứng dụng có phương thức findByLastLoginIsNull; dữ liệu cũ dùng chuỗi rỗng thay cho null khiến chức năng tìm tài khoản chưa đăng nhập bỏ sót nhiều người.
Nhóm phát triển dùng findByTagsContains với một collection field; khi chuyển repository sang kho dữ liệu khác, khả năng biểu diễn phép tìm trong collection không tương đương.
Dịch vụ CRM tìm số điện thoại bằng regex trong một loại document store; khi chuyển sang repository module khác, nhóm vẫn kỳ vọng derived query hỗ trợ cùng toán tử.
Một hệ thống đa tenant truyền tenantId qua method argument; một derived query ở repository mới bỏ sót điều kiện tenant và có nguy cơ trả về dữ liệu của khách hàng khác.
Nhóm triển khai query lookup strategy chỉ chấp nhận truy vấn được khai báo; các phương thức derived query hoạt động ở môi trường dev nhưng bean production không thể khởi tạo.
Ứng dụng vừa có named query vừa có derived query cùng tên; sau khi chuyển cấu hình lookup, repository dùng nguồn truy vấn khác và kết quả lọc không còn giống trước.
Một repository sử dụng phương thức có phần tên được parser suy luận thành property; khi entity thêm field mới trùng tên một đoạn, truy vấn được phân giải theo đường khác dự kiến.
Nhóm phát triển mở rộng repository với các phương thức tùy biến; tên phương thức của fragment trùng phương thức derived query khiến hành vi được gọi khác trước khi ghép module.
Ứng dụng dùng Pageable để phục vụ danh sách đơn hàng; backend nhận page=1 từ API như trang đầu nhưng PageRequest diễn giải chỉ số trang theo cách khác giao diện.
Nhóm thiết kế endpoint phân trang có tham số size không giới hạn; một client gửi size rất lớn khiến repository đọc và serialize hàng trăm nghìn bản ghi trong một request.
Ứng dụng sử dụng Page để hiển thị một trang sản phẩm; khi bộ dữ liệu tăng hàng chục triệu, truy vấn tính tổng bản ghi làm request chậm hơn nhiều so với truy vấn lấy nội dung trang.
Đội phát triển đổi từ Page sang Slice để giảm thời gian đếm; giao diện cũ vẫn kỳ vọng có totalPages và hiển thị thông tin không còn được trả về.
Một dịch vụ xem lịch sử giao dịch sử dụng offset pagination; khi giao dịch mới liên tục được thêm, khách lật trang và gặp một số bản ghi lặp hoặc bị bỏ qua.
Nhóm bổ sung Sort theo createdAt cho repository; hai bản ghi có cùng thời gian vẫn đổi thứ tự giữa các trang vì tiêu chí sắp xếp không đủ phân biệt.
Ứng dụng cho phép người dùng sắp xếp theo bất kỳ tên field gửi từ HTTP; một yêu cầu dùng thuộc tính không tồn tại gây lỗi repository và trả 500 cho toàn trang.
Một trang tìm kiếm nhận chuỗi sort chứa thuộc tính nested; store hiện tại không hỗ trợ cùng đường sắp xếp như kho quan hệ khiến kết quả production khác test.
Nhóm phát triển lưu một PageRequest làm biến chia sẻ và cố thay giá trị page trong nhiều request; đối tượng phân trang được dùng lại khiến giao diện luôn hiển thị trang đầu.
Ứng dụng hiển thị lịch sử theo Sort.Direction.DESC; đối tác cung cấp thông số ASC/DESC không hợp lệ ở một số request và service không có cách thống nhất để xử lý.
Nhóm hỗ trợ khách hàng muốn đưa bản ghi chưa có updatedAt lên đầu; mỗi loại database xử lý giá trị null trong sắp xếp theo quy tắc khác nhau và danh sách bị đảo.
Một API trả kết quả sắp xếp theo tên không phân biệt dấu; bộ tiêu chí Sort trong Spring Data không biểu diễn được quy tắc collation cụ thể như giao diện mong đợi.
Ứng dụng dùng Sort.TypedSort để xây tiêu chí sắp xếp an toàn kiểu; công cụ phân tích native image phát hiện proxy được tạo tại runtime làm quá trình build cần được xem xét.
Một bộ xử lý báo cáo dùng Page.map để đổi entity thành DTO; metadata phân trang vẫn giữ tổng số item ban đầu dù một số DTO bị loại bởi logic phía ứng dụng.
Nhóm tự tạo PageImpl từ danh sách đã lọc nhưng truyền totalElements của truy vấn gốc; client thấy số trang còn lại không khớp số bản ghi thực có thể xem.
Một service dùng Slice để cuộn vô hạn danh sách bài viết; nội dung trang cuối có đúng page size khiến nút tải tiếp được xác định sai trong một đợt import.
Ứng dụng thiết kế API duyệt dữ liệu với ScrollPosition để tránh offset lớn; các bản ghi thay đổi khóa sắp xếp trong lúc cuộn khiến kết quả bị lặp qua nhiều lần lấy tiếp.
Nhóm dựa vào keyset pagination khi sắp xếp theo trường không duy nhất; một số bản ghi cùng khóa không còn được đưa vào cửa sổ tiếp theo.
Một ứng dụng dùng offset sâu để xuất toàn bộ dữ liệu; độ trễ tăng theo số trang và công việc batch bị dừng giữa chừng dù các trang đầu trả rất nhanh.
Đội phát triển thêm sort nhiều trường vào pageable endpoint; một hệ thống khác vẫn gửi cú pháp sort cũ nên request bị phân tích thành thứ tự không mong muốn.
Ứng dụng hiển thị Page<Product> ra JSON trực tiếp; sau khi nâng Spring Data, cấu trúc metadata của Page khác hợp đồng mà ứng dụng di động đang phụ thuộc.
Nhóm thống kê cache kết quả Page theo số trang nhưng bỏ qua bộ lọc và sort trong cache key; người dùng nhận dữ liệu của truy vấn khác dù repository thực thi đúng.
API tìm người dùng sử dụng interface-based projection chỉ lấy tên và email; một lần mở rộng giao diện thêm trường profile khiến truy vấn và lượng dữ liệu đọc khác so với dự toán.
Nhóm phát triển dùng projection interface với getter có tên không khớp thuộc tính entity; lỗi chỉ xuất hiện khi client yêu cầu response dạng rút gọn trên một luồng ít dùng.
Ứng dụng dùng closed projection cho danh sách đơn; sau khi thêm phép tính trong getter bằng SpEL, hiệu năng truy vấn thay đổi vì dữ liệu cần để tính không còn đơn giản.
Một dịch vụ cho phép dynamic projection theo loại màn hình; khi truyền projection DTO mới, khả năng khởi tạo kết quả không tương thích constructor của class.
Nhóm thay đổi tên tham số constructor của DTO projection; cùng query chạy được trong môi trường build cũ nhưng kết quả không còn ánh xạ đầy đủ sau nâng cấp công cụ biên dịch.
Ứng dụng trả nested projection CustomerView có AddressView; khi render hàng trăm khách, số lần đọc dữ liệu liên quan tăng ngoài dự kiến trên backend hiện tại.
Nhóm thêm default method vào projection để ghép tên đầy đủ; một số bản ghi không có middleName và dữ liệu trả về không nhất quán với logic hiển thị.
Dịch vụ CRM dùng projection getter kiểu Optional cho trường điện thoại; dữ liệu nguồn chứa giá trị rỗng nhưng client hiểu absence khác với null của API trước.
Một API public trả interface projection được serialize trực tiếp bởi Jackson; sau khi thêm getter nội bộ, một thuộc tính không định đưa ra ngoài xuất hiện trong response.
Nhóm dùng projection để che số tài khoản; một loại projection khác được chọn động lại chứa entity đầy đủ, khiến endpoint vô tình trả trường nhạy cảm.
Ứng dụng tạo DTO projection qua constructor với kiểu số nguyên cho tổng chi phí; dữ liệu production dùng decimal khiến ánh xạ dữ liệu bị lỗi hoặc mất độ chính xác.
Đội phát triển giả định mọi store đều tối ưu truy xuất theo trường của projection; khi chuyển từ JPA sang document store, số byte đọc và số truy vấn không giảm như kỳ vọng.
Một dịch vụ dùng projection cho báo cáo theo nhiều bảng; thay đổi cấu trúc entity lồng nhau khiến cùng getter trả object null ở một module lưu trữ nhưng không ở module khác.
Nhóm tìm kiếm muốn trả các thuộc tính đã tính toán như tổng số đơn; projection của Spring Data không thể hiện trực tiếp cách tổng hợp mà đội sản phẩm kỳ vọng từ tập dữ liệu nguồn.
Ứng dụng dùng nhiều projection trên cùng repository method để phục vụ API web và mobile; một phiên bản client cũ yêu cầu trường đã đổi tên và lỗi mapping không được phát hiện trong test.
Một hệ thống chăm sóc khách hàng sử dụng Query by Example để tìm khách theo họ tên; probe có giá trị mặc định cho một trường boolean nên truy vấn vô tình loại các tài khoản không tương ứng.
Nhóm triển khai Example.of với đối tượng chứa cả trường phân loại không được người dùng nhập; kết quả tìm kiếm bị thu hẹp dù form chỉ yêu cầu tìm theo tên.
Ứng dụng tìm sản phẩm theo tên chứa chuỗi bằng ExampleMatcher; cấu hình mặc định so khớp khác với kỳ vọng tìm kiếm gần đúng khiến nhiều kết quả phù hợp không xuất hiện.
Một dịch vụ CRM cho phép tìm tên không phân biệt hoa thường; ExampleMatcher được áp cho field họ nhưng không áp cho field tên và cùng từ khóa cho kết quả khác nhau.
Nhóm dùng matcher startsWith cho mã hàng; trong khi kho dữ liệu nhận tên viết hoa và dấu tiếng Việt, cách so sánh chuỗi phụ thuộc khả năng của store thực tế.
Ứng dụng lọc các đơn chưa được gán nhân viên bằng probe có assignedTo null; Query by Example không phân biệt rõ ý định tìm giá trị null với việc bỏ qua field đó trong nhiều trường hợp.
Một API cần tìm khoảng thời gian bắt đầu và kết thúc; nhóm thử biểu diễn bằng hai thuộc tính trong một QBE probe nhưng kết quả không thỏa quan hệ khoảng theo yêu cầu nghiệp vụ.
Nhóm bán hàng muốn truy vấn điều kiện A hoặc đồng thời B và C; QBE đơn giản không đáp ứng cách nhóm điều kiện phức tạp như một cây biểu thức boolean tùy ý.
Ứng dụng thiết kế tìm kiếm có wildcard và regex do khách hàng nhập; ExampleMatcher ở một kho dữ liệu chỉ hỗ trợ một tập matcher nhất định nên hành vi khác trên kho mới.
Đội phát triển dùng ExampleMatcher để bỏ qua field id; sau khi đổi tên ID property, bộ lọc vô tình có thêm điều kiện định danh và không còn trả kết quả.
Một hệ thống khách hàng cần so khớp thuộc tính nested address.city; probe chứa object address chưa có city khiến kết quả phụ thuộc cách store xử lý dữ liệu lồng nhau.
Nhóm sử dụng QueryByExampleExecutor cùng Pageable để tìm thiết bị; danh sách sắp xếp theo hai tiêu chí vẫn thiếu kết quả khi nhiều bản ghi có cùng giá trị sort.
Ứng dụng cho phép người dùng chọn exact, contains hoặc startsWith; một màn hình vẫn giữ ExampleMatcher cũ trong cache và áp cách tìm không đúng cho request mới.
Nhóm dùng QBE để tìm sản phẩm gần giống trong danh mục; người dùng mong so khớp ngữ nghĩa nhưng kết quả chỉ phản ánh phép so sánh thuộc tính mà store hỗ trợ.
Đội QA kiểm thử Query by Example trên database in-memory; production chạy kho dữ liệu khác và khả năng ignore case hoặc pattern matching cho kết quả không tương đương.
Một service dùng QBE để đếm số tài khoản theo bộ lọc; số count trả về khác kết quả của truy vấn phân trang do hai nhánh code áp matcher không giống nhau.
Ứng dụng quản lý hồ sơ bật auditing để lưu createdDate và lastModifiedDate; sau khi chuyển module lưu trữ, các annotation đã có nhưng timestamp không được cập nhật lúc save.
Nhóm phát triển chỉ khai báo @CreatedBy trên entity; job nhập dữ liệu chạy không có phiên đăng nhập nên createdBy rỗng và hệ thống kiểm toán không biết tác nhân thực hiện.
Dịch vụ quản trị dùng AuditorAware để lấy username từ SecurityContext; một tác vụ @Async đổi thread khiến người tạo bản ghi không được xác định giống trong HTTP request.
Một hệ thống đa tenant lưu tenant user ID trong @LastModifiedBy; khi tài khoản nhân viên bị vô hiệu hóa, truy vấn lịch sử không còn hiển thị người sửa theo cách sản phẩm cần.
Đội phát triển dùng @CreatedDate với LocalDateTime; các ứng dụng chạy ở hai timezone tạo timestamp không so sánh được theo thứ tự thực tế khi tổng hợp báo cáo.
Một dịch vụ nhận dữ liệu lịch sử từ hệ thống cũ; khi lưu bằng repository, auditing ghi thời gian import thay cho thời gian tạo nghiệp vụ gốc nên báo cáo thống kê sai.
Nhóm quản lý hợp đồng sử dụng entity bất biến cho thông tin tạo và sửa; việc gán audit fields lúc lưu không tương thích với cách construct aggregate ở một store.
Ứng dụng dùng @LastModifiedDate để ghi thời điểm sửa mỗi khi save được gọi dù dữ liệu không thay đổi; một màn hình xem tài liệu vô tình gọi save và tạo lịch sử sửa không cần thiết.
Đội phát triển muốn phân biệt người dùng và tác vụ hệ thống trong @CreatedBy; các job chạy vào nửa đêm đều có cùng giá trị mặc định khiến việc kiểm toán không thể truy ngược chương trình nguồn.
Một hệ thống tài chính cần độ chính xác timestamp đến microsecond; audit fields bị làm tròn khác nhau giữa các kho dữ liệu khiến so sánh lần sửa gần nhau cho kết quả mâu thuẫn.
Nhóm phát triển ghi audit vào các entity có quan hệ; một aggregate root được cập nhật làm nested object đổi theo nhưng trường lastModifiedDate của object lồng nhau không như mong đợi.
Ứng dụng sử dụng @LastModifiedBy để theo dõi thay đổi quyền; khi một Consumer xử lý event ngoài context người dùng, thông tin tác nhân bị lấy từ thread đã phục vụ request trước.
Dịch vụ khách hàng cần che thông tin danh tính trong log nhưng auditing vẫn lưu đầy đủ tài khoản quản trị; chính sách bảo vệ dữ liệu và nhu cầu truy xuất lịch sử đang mâu thuẫn.
Nhóm quản trị nâng cấp Spring Data và thay cấu hình enable auditing; một entity chỉ được lưu qua đường bulk operation không phát sinh lifecycle callback như đội QA kỳ vọng.
Một repository có save phương thức trả về entity đã lưu; nhóm nghiệp vụ đọc createdDate trên instance truyền vào thay vì instance trả về và gặp giá trị rỗng ở môi trường sử dụng immutable entity.
Ứng dụng có nhiều AuditorAware bean cùng kiểu nhưng cấu hình auditing không chỉ rõ bean phù hợp; khi bật thêm module bảo mật, thông tin người sửa trở nên không ổn định.
Đội phát triển viết repository fragment để bổ sung thao tác tìm gần đúng; một tên phương thức trùng với phương thức đã có trong interface và đội QA không rõ implementation nào được gọi.
Một module định nghĩa custom base repository class cho tất cả aggregate; sau khi đổi cấu hình factory, các repository của một datastore không sử dụng lớp nền tùy biến và thiếu bước kiểm toán.
Ứng dụng có hai repository fragment cần cùng một service xác thực; khi bean được khai báo theo hai tên khác nhau, Spring chọn implementation không đúng cho một fragment.
Nhóm viết method default trong interface repository để kết hợp nhiều truy vấn; khi gọi từ service, ranh giới transaction và số kết nối giữ lâu hơn so với dự đoán ban đầu.
Một đội muốn dùng repository method chung cho hai backing store; implementation tận dụng phương thức đặc thù của một module làm service thất bại khi dùng store còn lại.
Ứng dụng tổ chức domain model có entity và value object; MappingContext của từng module diễn giải metadata của một thuộc tính lồng nhau khác nhau và query mapping không nhất quán.
Nhóm chuyển đổi trường userId từ String thành một value object; repository method vẫn nhận String nên object mapping không còn khớp dữ liệu trong kho.
Dịch vụ quản lý sản phẩm dùng custom converter để lưu Money; sau khi nâng phiên bản, metadata của amount thay đổi và derived query lọc theo tiền trả kết quả không phù hợp.
Ứng dụng đăng ký callback dựa vào metadata entity ID; khi một domain dùng composite ID, logic giả định chỉ có một scalar ID làm thao tác lưu thất bại.
Nhóm sử dụng PersistentEntity để kiểm kiểu entity tại runtime; một class DTO không được Spring Data xem là persistent entity nhưng pipeline vẫn cố truy cập metadata lưu trữ của nó.
Ứng dụng thay tên một field domain nhưng không cập nhật mapping annotation của datastore; property path trong derived query còn đúng trên Java nhưng đọc sai trường đã tồn tại trong database.
Một hệ thống có nhiều loại kho dữ liệu cùng lưu customerId; metadata type conversion của repository JPA và MongoDB không tương thích khi dùng chung một value object ID.
Nhóm dùng @DomainEvents để phát sự kiện khi aggregate được lưu; một đường cập nhật bulk đi thẳng vào store khiến sự kiện không xuất hiện dù dữ liệu đã thay đổi.
Ứng dụng định nghĩa @AfterDomainEventPublication để xóa danh sách sự kiện đã phát; khi save thất bại sau khi callback chạy ở một luồng, đội vận hành không biết liệu event có được phát hay chưa.
Nhóm xây luồng đồng bộ dữ liệu dựa vào domain events từ repository; một tác vụ gọi saveAll cho nhiều aggregate và số sự kiện phát ra khác với số bản ghi đã thay đổi.
Ứng dụng dùng DomainClassConverter trong web layer để ánh xạ path ID thành entity; request với ID không tồn tại tạo ra kết quả khác với exception handler mà nhóm API đang sử dụng.
Đội phát triển hỗ trợ Pageable và Sort từ tham số HTTP qua web support; nhiều endpoint dùng cùng tên tham số page nên khi nhúng hai bảng vào một trang, dữ liệu điều khiển bị xung đột.
Nhóm thêm metadata xác định domain ID theo một custom annotation; cơ chế repository hiện không nhận ra property là ID và các thao tác CRUD không thực thi như dự kiến.
Ứng dụng chuyển từ kho quan hệ sang document store nhưng giữ nguyên repository interface và tên query method; một phần điều kiện lồng nhau vẫn biên dịch được nhưng semantics dữ liệu khác.
Một dịch vụ sở hữu cả repository đồng bộ và ReactiveCrudRepository; controller WebFlux gọi nhầm repository blocking nên event-loop bị giữ khi truy vấn database chậm.
Nhóm xử lý sự kiện khai báo reactive repository cho store chưa có driver không chặn tương ứng; phương thức trả Publisher nhưng I/O thực tế vẫn giữ thread lâu hơn kỳ vọng.
Ứng dụng sử dụng repository fragment chung cho môi trường blocking và reactive; API trả kiểu không phù hợp làm composition giữa các method gặp lỗi runtime.
Một hệ thống thử nghiệm derived query trên H2 trong khi production dùng PostgreSQL; phân biệt hoa thường, timestamp và null sorting khiến kết quả truy vấn không giống nhau.
Đội QA dùng Mockito mock CrudRepository trong test service; logic mapping ID và @Version của repository thật không được kiểm nên lỗi chỉ xuất hiện khi chạy integration test.
Nhóm phát triển chạy repository integration test với một tập bản ghi nhỏ; phương thức phân trang trả đúng hai trang nhưng performance của count query trên dữ liệu lớn không được đánh giá.
Ứng dụng chạy test query derivation trên MongoDB giả lập nhưng production sử dụng phiên bản server khác; toán tử tìm trên nested collection được xử lý khác và lọc thiếu kết quả.
Đội kiểm thử project dùng projection DTO để giảm dữ liệu; test chỉ so sánh field có giá trị, bỏ qua null và type conversion nên lỗi chỉ xuất hiện với dữ liệu thật.
Nhóm thực hiện migration đổi ID của aggregate từ Long sang UUID; các bản ghi cũ vẫn dùng ID số và repository mới không tra cứu được lịch sử cần thiết.
Một ứng dụng phục vụ nhiều tenant dùng cùng repository chung; derived query trả dữ liệu hợp lệ về mặt cú pháp nhưng thiếu bộ lọc tenant ở một luồng tìm kiếm.
Đội vận hành tăng số instance chạy tác vụ cập nhật trạng thái; repository thực hiện save trên entity đọc cũ và những thay đổi cạnh tranh có thể bị ghi đè nếu store không cung cấp khóa phù hợp.
Một dịch vụ tạo API truy vấn nhiều kiểu datastore dựa vào cùng contract; tính năng tìm regex, phân trang, projection và auditing được giả định hỗ trợ đầy đủ khiến một module bị lỗi khi triển khai.
Nhóm bảo trì nâng Spring Data Commons nhưng giữ các module store ở phiên bản khác thế hệ; bean repository khởi tạo sai và lỗi chỉ xuất hiện trong profile tích hợp nhiều kho.
Ứng dụng dùng PageRequest với kích thước lớn làm đầu vào của một endpoint công khai; client gửi page cực lớn khiến phép tính offset vượt giới hạn xử lý an toàn của backend.
Đội phát triển cho phép client truyền tên property tùy ý vào Sort; một truy vấn sort theo trường nhạy cảm vô tình tiết lộ thứ tự nội bộ của dữ liệu không được phép công khai.
Nhóm phân tích tạo QBE probe từ object nhận trực tiếp từ client; một thuộc tính hệ thống không được hiển thị trong giao diện vẫn có thể được gửi và làm thay đổi phạm vi truy vấn.
Một service công bố Pageable response dùng Page metadata; sau khi backend chuyển sang Slice để giảm tải, ứng dụng mobile vẫn dựa vào totalElements và hiển thị trang điều hướng sai.
Nhóm tích hợp lưu metadata auditing trong cùng aggregate chứa tài liệu bí mật; một projection được dùng cho báo cáo vô tình trả createdBy và lastModifiedBy ngoài phạm vi quyền của người xem.
