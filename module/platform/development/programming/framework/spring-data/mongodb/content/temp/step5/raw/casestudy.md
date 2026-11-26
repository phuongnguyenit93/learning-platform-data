Một dịch vụ đặt hàng dùng Spring Data MongoDB đọc URI kết nối từ biến môi trường; khi triển khai production, URI vẫn trỏ vào database thử nghiệm và các đơn hàng mới xuất hiện sai môi trường.
Nhóm vận hành chuyển MongoDB sang replica set nhưng chuỗi kết nối vẫn chỉ định một node không còn khả dụng; ứng dụng khởi động được nhưng các thao tác ghi thường xuyên bị server selection timeout.
Một ứng dụng Spring Boot dùng tên miền SRV để kết nối MongoDB Atlas; DNS trong cụm Kubernetes không phân giải được bản ghi cần thiết nên dịch vụ chỉ lỗi ở môi trường production.
Đội kỹ thuật tạo MongoClient mới cho từng HTTP request thay vì tái sử dụng client do Spring quản lý; số kết nối tới MongoDB tăng đột ngột khi lượng người dùng lớn.
Một API tra cứu sản phẩm đặt connection pool MongoDB rất nhỏ; khi chạy chiến dịch flash sale, nhiều request chờ lấy kết nối dù cụm database vẫn còn tài nguyên xử lý.
Nhóm tăng kích thước pool để giảm thời gian chờ; MongoDB bắt đầu chạm giới hạn kết nối khi hàng chục pod ứng dụng cùng khởi chạy và tỷ lệ timeout tăng.
Một dịch vụ cập nhật hồ sơ dùng readPreference ưu tiên secondary; ngay sau khi ghi thành công, request đọc tiếp có lúc trả về thông tin cũ do độ trễ replication.
Đội vận hành áp readConcern khác nhau giữa các môi trường; báo cáo vừa ghi một giao dịch nhưng query kiểm tra chưa nhìn thấy dữ liệu theo cách nhóm nghiệp vụ kỳ vọng.
Ứng dụng quản lý số dư đặt writeConcern không phù hợp yêu cầu chịu lỗi; node primary gặp sự cố ngay sau khi API báo đã ghi thành công và một số thay đổi không còn sau chuyển quyền.
Nhóm triển khai MongoDB client với socket timeout ngắn; truy vấn tổng hợp lớn đôi khi bị ngắt kết nối dù cụm vẫn thực thi pipeline phía sau.
Một hệ thống xử lý tài liệu bật TLS cho MongoDB; khi CA của nhà cung cấp được thay mới, một nhóm container thiếu truststore tương ứng và liên tục lỗi bắt tay.
Ứng dụng quản trị lấy username/password từ Secret mount trong Kubernetes; khi thông tin xác thực được xoay vòng, kết nối mới bị từ chối còn pool cũ vẫn phục vụ được một thời gian.
Nhóm dùng cùng tài khoản database cho dịch vụ đọc công khai và job dọn dữ liệu; một lỗi phân quyền trong service web có thể xóa document ngoài phạm vi cần thiết.
Một sản phẩm SaaS lưu dữ liệu khách hàng vào nhiều database trên cùng MongoDB cluster; cấu hình MongoDatabaseFactory dùng database mặc định cho một nhánh và ghi chéo dữ liệu tenant.
Đội tích hợp đổi tên collection khi nâng cấp dịch vụ; repository đã trỏ tới collection mới nhưng MongoTemplate trong job báo cáo vẫn đọc tên cũ và thống kê bị lệch.
Ứng dụng kết nối tới MongoDB qua proxy mạng nội bộ; các lệnh đọc đơn giản chạy được nhưng một lần bầu primary mới làm client không tìm được topology phù hợp để ghi.
Nhóm lưu đơn hàng bằng entity đánh dấu @Document; collection thực tế sử dụng tên khác quy ước mặc định nên repository đọc trả rỗng mặc dù dữ liệu đã có.
Một hệ thống CRM ánh xạ trường @Id của Customer thành String; dữ liệu cũ có _id dạng ObjectId và dữ liệu mới có _id dạng chuỗi khiến cùng mẫu ID được tra cứu khác nhau.
Đội nhập dữ liệu lịch sử gán _id từ mã khách hàng thay vì ObjectId; hai nguồn cùng có mã địa phương giống nhau và xảy ra xung đột khóa trong lúc ghi.
Ứng dụng dùng @Field để đổi tên thuộc tính lastLoginAt khi lưu document; một bản báo cáo viết trực tiếp truy vấn bằng tên Java cũ nên không tìm được bản ghi.
Nhóm thêm @TypeAlias cho các subtype của tài liệu thanh toán; sau khi đổi tên alias ở bản release mới, document cũ không còn được ánh xạ đúng kiểu nghiệp vụ.
Một dịch vụ lưu nhiều loại thông báo trong cùng collection với _class; khi đội vận hành tắt thông tin kiểu để giảm kích thước document, một số subtype đọc lại thành class cơ sở.
Nhóm chuyển trường amount từ Double sang Decimal128 bằng mapping của Spring Data MongoDB; document được ghi ở hai kiểu trong thời gian rolling deployment và phép tổng hợp bị sai lệch.
Ứng dụng lưu giá tiền bằng BigDecimal nhưng dữ liệu nhập từ hệ thống khác có trường amount dạng chuỗi; Mongo converter không diễn giải được một số document cũ khi tra cứu.
Một hệ thống xử lý lịch hẹn ánh xạ Instant và LocalDateTime từ BSON Date; người dùng ở hai timezone nhận ngày hẹn khác nhau dù cùng xem một document.
Nhóm phát triển đổi trường status từ String thành enum; những document lịch sử chứa giá trị đã ngừng hỗ trợ làm toàn bộ trang liệt kê đơn hàng gặp lỗi mapping.
Ứng dụng MongoDB lưu thuộc tính optional trong một số document nhưng thiếu hẳn field ở document khác; logic Java phân biệt null với giá trị mặc định không giống truy vấn MongoDB.
Đội triển khai dùng constructor binding cho immutable document; khi thêm tham số bắt buộc mới, các document cũ thiếu field không còn được khởi tạo như kỳ vọng.
Một entity có property tên khác cấu trúc lưu trong BSON và dùng custom converter; sau khi sửa converter, query trên thuộc tính đó không trả được dữ liệu theo định dạng cũ.
Ứng dụng quản lý sản phẩm nhúng danh sách giá theo chi nhánh trực tiếp trong document; khi số lượng chi nhánh tăng hàng nghìn, một document ngày càng lớn và thời gian cập nhật tăng mạnh.
Nhóm lưu toàn bộ lịch sử trạng thái đơn hàng trong mảng embedded events; đơn hàng tồn tại lâu năm dần tiến gần giới hạn kích thước BSON document của MongoDB.
Đội thiết kế collection người dùng với danh sách thiết bị có thể mở rộng vô hạn; một thao tác cập nhật toàn bộ document làm tăng tải mạng và xung đột ghi trong giờ cao điểm.
Một hệ thống tách địa chỉ khỏi Customer thành collection riêng và dùng @DocumentReference; khi xóa địa chỉ, các customer cũ vẫn giữ tham chiếu không còn tồn tại.
Nhóm sử dụng @DBRef để gắn nhiều sản phẩm với Order; màn hình danh sách cần hiển thị 100 đơn khiến hệ thống phát sinh nhiều lượt truy cập collection liên quan.
Ứng dụng bật lazy @DBRef để tiết kiệm truy vấn; khi serializer truy cập thuộc tính sau khi đóng context hoặc trong môi trường proxy hạn chế, API phát lỗi ở một số response.
Nhóm triển khai tham chiếu giữa hai database của MongoDB; cách biểu diễn reference và quyền truy cập khác với mô hình nhúng dữ liệu khiến bước đọc chi tiết tài liệu thất bại.
Một entity chứa danh sách địa chỉ embedded với hai phần tử cùng ID nội bộ; tác vụ thay một địa chỉ cập nhật nhầm phần tử vì khóa nhận diện trong mảng chưa đủ rõ.
Đội tích hợp lưu các khóa tùy biến của khách dưới dạng Map; một số key có dấu chấm hoặc ký tự đặc biệt làm đường cập nhật và truy vấn không hành xử như field thông thường.
Một sản phẩm nhận JSON có nhiều thuộc tính không biết trước; sau khi chuyển dữ liệu vào Document động, ứng dụng vô tình cho phép client ghi đè một field hệ thống đang dùng để phân quyền.
Nhóm dùng @Version trên document tồn kho để phát hiện cập nhật cạnh tranh; hai request sửa cùng SKU gây OptimisticLockingFailureException mà API hiện coi là lỗi máy chủ ngẫu nhiên.
Một dịch vụ thay thế toàn bộ document từ payload không có version; thông tin @Version và các trường metadata được lưu bởi request trước bị ghi đè ngoài dự kiến.
Ứng dụng nhận dữ liệu từ file CSV rồi gọi saveAll cho hàng nghìn document; một số bản ghi đã có _id bị coi là cần thay thế, làm mất các field không có trong dữ liệu nhập.
Đội bán hàng dùng repository save để cập nhật một field của hồ sơ khách; object được dựng từ request thiếu các thuộc tính khác và bản lưu cuối không còn dữ liệu trước đó.
Một job đồng bộ sản phẩm sử dụng findById rồi save; trong khi đó một tác vụ khác sửa tồn kho và thay đổi của tác vụ đầu ghi đè lên tài liệu mới hơn.
Nhóm thêm @CreatedDate và @LastModifiedDate cho document; một đường thao tác cập nhật bằng MongoTemplate bỏ qua callback entity nên trường thời gian sửa không được điền như đường repository save.
Một ứng dụng dùng AuditorAware để lưu @CreatedBy; khi Kafka Consumer xử lý sự kiện không có SecurityContext, document được ghi thiếu người tạo trong khi HTTP request vẫn có giá trị.
Đội kỹ thuật gắn lifecycle callback để chuẩn hóa số điện thoại trước khi lưu; thao tác bulk update trực tiếp không chạy cùng callback khiến collection tồn tại hai định dạng số.
Ứng dụng dùng BeforeSaveCallback để mã hóa field nhạy cảm; một quy trình nhập dữ liệu sử dụng raw Mongo driver ghi thẳng nên document mới không được xử lý giống đường repository.
Nhóm triển khai đổi tên field trong domain nhưng không di chuyển dữ liệu đã lưu; MongoDB cho phép schema linh hoạt nên lỗi chỉ bộc lộ khi đọc các hồ sơ lịch sử.
Một hệ thống có nhiều phiên bản ứng dụng chạy cùng lúc trong đợt rolling; bản cũ không hiểu trường mới trong document và trả dữ liệu thiếu khi cùng một người dùng chuyển pod.
Đội phát triển dùng CrudRepository cho MongoDB và định nghĩa findByCustomerId; ở dữ liệu production, customerId được lưu dưới nhiều kiểu BSON nên kết quả tra cứu thiếu hồ sơ.
Ứng dụng có derived query findByCustomerAddressCity; sau khi thay địa chỉ embedded thành reference, tên property path còn tồn tại nhưng truy vấn không có semantics như thiết kế trước.
Nhóm bán hàng xây findByStatusAndCreatedAtBetween; mốc thời gian được nhập theo giờ địa phương trong khi BSON Date được lưu theo UTC làm các đơn cuối ngày bị bỏ qua.
Một API cung cấp findByNameContainingIgnoreCase; collection chứa hàng triệu khách và truy vấn regex không tận dụng index theo cách đội kỹ thuật kỳ vọng.
Đội phát triển dùng findByTagsContaining trên mảng tags; dữ liệu cũ có phần tử là object thay vì string khiến việc tìm theo nhãn cho kết quả không nhất quán.
Ứng dụng gọi findFirstByCustomerIdOrderByCreatedAtDesc để lấy giao dịch cuối; hai document cùng timestamp tạo thứ tự khác nhau giữa hai request.
Nhóm dùng repository findByEmail trả một Customer; dữ liệu lịch sử có email trùng nhưng chưa có unique index, khiến method gặp lỗi khi query trả nhiều document.
Một dịch vụ cho phép tìm bằng ví dụ qua QueryByExampleExecutor; probe có trạng thái boolean mặc định nên vô tình loại nhiều người dùng mà form không yêu cầu lọc.
Nhóm dùng ExampleMatcher để tìm tên không phân biệt hoa thường; một số locale và cách chuẩn hóa dấu tiếng Việt khiến kết quả không giống tìm kiếm nghiệp vụ mong muốn.
Một trang sản phẩm dùng PageRequest để duyệt collection lớn; client gửi page quá sâu và MongoDB phải bỏ qua số lượng document khổng lồ trước khi trả kết quả.
Đội vận hành thấy query lấy 20 sản phẩm rất nhanh nhưng Page<Product> phản hồi chậm; truy vấn count tổng số bản ghi trở thành phần tốn thời gian nhất.
Ứng dụng đổi Page thành Slice để tránh đếm; giao diện mobile cũ vẫn dựa vào totalPages để hiển thị nút chuyển trang và hoạt động sai.
Nhóm sắp xếp danh sách đơn theo updatedAt nhưng nhiều document có cùng thời điểm; offset pagination làm một số đơn xuất hiện lặp hoặc biến mất khi dữ liệu được cập nhật.
Một API cho phép client truyền tên field vào Sort; request sort theo thuộc tính nested không tồn tại dẫn tới kết quả hoặc chi phí xử lý khác mong đợi.
Ứng dụng dùng interface projection chỉ trả tên và email; khi bổ sung trường nhạy cảm trong getter, response công khai có thể chứa dữ liệu không dành cho người xem.
Nhóm triển khai DTO projection cho native MongoDB query; tên field trong BSON không khớp constructor DTO khiến một số thuộc tính nhận null ở production.
Đội phát triển dùng repository method chỉ để lấy hai field bằng projection; một bước serialization vẫn truy cập object lồng nhau và phát sinh truy vấn bổ sung ngoài dự kiến.
Một hệ thống phân trang danh sách sự kiện cần vị trí ổn định; document mới được thêm liên tục và việc dùng skip/limit làm kết quả bị trùng giữa các trang.
Ứng dụng MongoTemplate đọc dữ liệu bằng Criteria theo tenantId và trạng thái; một nhánh xây Query bỏ điều kiện tenant khiến nhân viên xem được đơn hàng của tổ chức khác.
Nhóm sử dụng Criteria.orOperator để tìm sản phẩm theo nhiều đặc điểm; điều kiện bắt buộc về quyền truy cập được ghép sai với OR làm truy vấn trả tài liệu ngoài phạm vi.
Một dịch vụ áp dụng regex cho mã sản phẩm từ tham số tìm kiếm; chuỗi người dùng gửi có ký tự đặc biệt làm truy vấn khớp nhiều document hơn dự kiến.
Đội phát triển dùng MongoTemplate.findOne với bộ lọc không duy nhất; khi xuất hiện nhiều document thỏa điều kiện, kết quả được chọn không ổn định giữa các lần gọi.
Ứng dụng dùng MongoTemplate.updateFirst để cập nhật hồ sơ theo địa chỉ email; email trùng trong dữ liệu cũ khiến một bản ghi bất kỳ được cập nhật còn bản ghi đúng không thay đổi.
Nhóm đồng bộ trạng thái đơn hàng dùng updateMulti; một điều kiện lọc thiếu trạng thái cũ khiến cả các đơn đã hoàn tất cũng bị đổi trạng thái.
Một API điều chỉnh thông số định mức dùng phép increment trên field có document cũ lưu dạng chuỗi; một số giao dịch báo lỗi vì kiểu BSON không phù hợp phép toán.
Đội kỹ thuật dùng upsert cho bản ghi tồn kho theo SKU; hai request đồng thời không có unique index trên SKU tạo hai document cùng mã hàng.
Ứng dụng sử dụng findAndModify để cấp số thứ tự phiếu; khi điều kiện lọc không ổn định, nhiều request lấy số thứ tự từ những document cấu hình khác nhau.
Nhóm sử dụng findAndReplace để thay nội dung Customer; payload mới không có trường createdAt và lịch sử tạo bị mất sau khi thao tác ghi hoàn tất.
Một hệ thống quản lý giỏ hàng dùng push để bổ sung item; request bị retry sau timeout khiến cùng sản phẩm được thêm hai lần vào mảng.
Đội phát triển dùng addToSet để ngăn trùng phần tử; object item có thêm field timestamp nên MongoDB vẫn coi hai lần thêm là hai object khác nhau.
Ứng dụng cần cập nhật số lượng của một item trong mảng lineItems; positional operator nhắm sai phần tử khi đơn có hai biến thể cùng productId.
Nhóm sửa nhiều phần tử lồng nhau bằng arrayFilters; cấu hình định danh phần tử không khớp dữ liệu thực làm chỉ một phần danh sách được cập nhật.
Một service xóa thông tin thẻ thanh toán bằng unset; đường truy vấn nhầm tên field đã được đổi qua @Field nên dữ liệu nhạy cảm còn trong document.
Đội phát triển chạy bulkOperations để nhập dữ liệu lớn; một lỗi unique index giữa batch làm số dòng được ghi khác mong đợi nhưng dashboard chỉ ghi nhận số request thành công.
Ứng dụng dùng BulkMode.UNORDERED để tăng throughput; khi một item lỗi, thứ tự xử lý và trạng thái của các item còn lại khác giả định tuần tự của nghiệp vụ.
Nhóm thao tác MongoTemplate để lưu hàng nghìn document trong một lần gọi; giới hạn batch hoặc kích thước message khiến công việc fail chỉ khi có file nguồn rất lớn.
Một API nhận patch JSON từ client; cách chuyển đổi patch thành Update cho phép sửa trường ownerId vốn phải được quản lý nội bộ.
Đội bảo trì gọi remove với Query quá rộng sau khi tên thuộc tính đổi; nhiều document lịch sử bị xóa vì điều kiện bắt buộc không được đưa vào thao tác.
Ứng dụng chạy aggregation với $match theo trạng thái đơn hàng sau bước $group; hệ thống phải xử lý số lượng document trung gian lớn hơn nhiều so với khi lọc dữ liệu đầu vào.
Nhóm phân tích doanh thu dùng Aggregation.group theo customerId; dữ liệu nguồn có cùng ID ở hai tenant nên kết quả tổng hợp bị cộng lẫn doanh thu của nhiều tổ chức.
Một báo cáo dùng $unwind mảng sản phẩm trong Order; các order không có item biến mất khỏi báo cáo mặc dù cần được tính là đơn rỗng.
Đội phát triển dùng $lookup để kết hợp đơn hàng với khách hàng ở collection khác; khi tập đơn tăng lớn, truy vấn phải duyệt nhiều document và vượt giới hạn thời gian của API.
Ứng dụng thống kê tổng tiền dùng aggregation trên field amount; dữ liệu có cả kiểu Double và Decimal128 làm phép cộng và định dạng đầu ra khác kỳ vọng.
Nhóm dùng $project để chỉ giữ trường cần hiển thị; sau khi đổi tên cột trong mapping domain, một field dùng ở bước $group tiếp theo không còn tồn tại.
Một hệ thống phân loại đơn theo khoảng doanh thu bằng $bucket; các giá trị đúng tại ranh giới khiến số lượng ở hai nhóm khác báo cáo Excel mà tài chính đang đối chiếu.
Đội kinh doanh tạo biểu đồ phân bố giá với $bucketAuto; khi dữ liệu đầu vào thay đổi nhiều, ranh giới nhóm tự điều chỉnh làm kết quả tháng này khó so với tháng trước.
Ứng dụng tổng hợp đơn theo tháng bằng toán tử ngày của MongoDB; thời điểm ghi ở UTC khiến giao dịch cuối ngày bị xếp sang tháng khác theo múi giờ thị trường.
Nhóm tính số giao dịch duy nhất qua $addToSet rồi đếm phần tử; một nhóm khách có số lượng giao dịch khổng lồ làm document kết quả aggregation tăng bất thường.
Một dashboard dùng $facet để trả kết quả phân trang và tổng số cùng lúc; khi filter nhiều trường không có index phù hợp, cả hai nhánh đều trở thành điểm nghẽn.
Đội vận hành dựng pipeline Aggregation gồm $sort rồi $limit ở vị trí không phù hợp với cách nhóm dữ liệu; danh sách sản phẩm top bán chạy trả kết quả sai.
Ứng dụng báo cáo vùng địa lý dùng $geoNear; tài liệu tọa độ lưu sai thứ tự kinh độ và vĩ độ làm khoảng cách tính được không phản ánh vị trí thực.
Nhóm tìm khách ở khu vực gần một điểm bằng aggregation; collection chưa có index không gian phù hợp nên truy vấn chỉ lỗi trên môi trường production.
Một API tìm kiếm full-text kết hợp text score và filter nhãn; kết quả ranking thay đổi sau khi nhóm sửa ngôn ngữ index khiến sản phẩm tiếng Việt bị đẩy xuống.
Đội phân tích dùng aggregation với $count sau $unwind nhiều mảng; số lượng giao dịch bị nhân lên theo số phần tử của từng mảng và báo cáo doanh thu sai.
Ứng dụng xuất báo cáo theo ngày thông qua aggregation trả hàng trăm nghìn bản ghi; API cố gom toàn bộ kết quả vào một List khiến heap tăng và phản hồi timeout.
Nhóm chia pipeline aggregation thành nhiều bước trong Java; một bước mong nhận kiểu Long nhưng MongoDB trả Decimal128 khiến việc map kết quả sang DTO phát sinh lỗi.
Đội phát triển sử dụng MongoTemplate.aggregate với output class ánh xạ thiếu field _id của nhóm; nhiều hàng báo cáo bị gộp nhầm khi đưa sang Map ở tầng service.
Một hệ thống thống kê trạng thái theo thời gian thực đọc từ secondary; aggregation ngay sau khi ghi không bao gồm message mới nhất và dashboard có độ trễ khó giải thích.
Ứng dụng tra cứu đơn theo customerId và createdAt; index đơn trên từng field đã có nhưng explain cho thấy query vẫn quét lượng lớn document khi kết hợp lọc và sort.
Nhóm thêm compound index theo thứ tự createdAt rồi status; truy vấn thường lọc theo status trước và sắp xếp ngày nên không tận dụng index hiệu quả như dự đoán.
Đội vận hành tạo unique index trên email trong collection khách hàng; thao tác build index thất bại vì các document lịch sử có email trùng hoặc thiếu field.
Một ứng dụng cần cho phép nhiều người chưa có email nhưng ngăn email trùng khi đã cung cấp; unique index thông thường gây lỗi với các document thiếu giá trị và tạo tài khoản bị chặn.
Nhóm dùng partial unique index cho mã tài khoản còn hiệu lực; khi đổi trạng thái một tài khoản đã xóa mềm, thao tác cập nhật va chạm với tài khoản khác có cùng mã.
Đội triển khai TTL index cho session; nhân viên kỳ vọng session hết hạn đúng giây nhưng MongoDB xóa bất đồng bộ khiến một số tài liệu còn tồn tại thêm một khoảng thời gian.
Một hệ thống có yêu cầu lưu lịch sử sự kiện tối thiểu 90 ngày; sau khi thay đổi TTL index, dữ liệu cũ bị xóa sớm hơn thời gian giữ bắt buộc.
Nhóm bổ sung text index cho chức năng tìm tên sản phẩm; khi collection đã có text index theo cấu hình cũ, việc thay schema tìm kiếm không diễn ra như dự định.
Một ứng dụng tìm địa điểm giao hàng dùng GeoJSON; một số document lưu tọa độ theo định dạng không hợp lệ khiến quá trình tạo 2dsphere index thất bại.
Đội phát triển tạo index trên các field của array embedded; một truy vấn có nhiều phần tử trong cùng mảng cho kết quả và hiệu năng khác giả định về multikey index.
Ứng dụng theo dõi trạng thái đơn có nhiều index trên các trường ít dùng; tỷ lệ insert giảm và dung lượng lưu trữ index tăng nhanh sau đợt nạp dữ liệu lớn.
Nhóm vận hành xóa một index vì cho rằng không còn cần; sau đó một báo cáo chạy cuối tuần bị tăng thời gian quét collection từ giây lên phút.
Đội phát triển dùng wildcard index cho các thuộc tính sản phẩm linh hoạt; số lượng key tăng lớn khiến chi phí ghi và bộ nhớ index vượt dự toán.
Ứng dụng tìm khách theo tên với collation không phân biệt hoa thường; index tạo bằng collation khác khiến query không đi theo index được kỳ vọng.
Nhóm dựng index cho trường giá và trạng thái; truy vấn lọc trên field đã chuyển từ Number sang String làm so sánh phạm vi không còn phù hợp.
Một service dùng sparse index để tối ưu các document có trường tùy chọn; truy vấn cần tìm cả document thiếu trường không thể dựa vào index theo cách đội phát triển kỳ vọng.
Đội QA kiểm tra tốc độ truy vấn trên collection chỉ có 500 document; production có hàng chục triệu document và MongoDB chọn execution plan hoàn toàn khác.
Ứng dụng hiển thị thống kê độ trễ từ driver; dashboard chỉ ghi thời gian Java method, không có dữ liệu docsExamined và keysExamined để biết vì sao query chậm.
Nhóm tối ưu truy vấn bằng hint chỉ định index; sau một lần migration xóa index cũ, endpoint lỗi vì truy vấn vẫn mang hint không còn hợp lệ.
Một collection được shard theo tenantId; một query báo cáo không có điều kiện shard key khiến MongoDB phải phân tán truy vấn tới nhiều shard và thời gian trả kết quả tăng.
Đội vận hành chọn shard key theo mã sản phẩm tăng dần; phần lớn dữ liệu mới đi vào một vùng khóa và sinh hotspot ghi vào một shard.
Ứng dụng cần unique trên mã đơn hàng toàn cluster; một quy tắc định danh không phù hợp với shard key khiến việc áp ràng buộc không thực hiện được như ở collection không shard.
Nhóm triển khai MongoTransactionManager cho luồng tạo đơn và trừ tồn kho; môi trường phát triển dùng MongoDB standalone nên transaction không bắt đầu được dù lệnh ghi đơn lẻ hoạt động.
Một dịch vụ bán vé cập nhật hai collection trong cùng transaction; thao tác gọi API đối tác được thực hiện giữa giao dịch khiến transaction giữ tài nguyên lâu và dễ timeout.
Đội phát triển giả định mọi lệnh update trong một document cần transaction nhiều tài liệu; throughput giảm vì xử lý thừa trong khi yêu cầu nghiệp vụ chủ yếu là thao tác đơn document.
Ứng dụng ghi đơn hàng rồi ghi lịch sử vào collection thứ hai; khi không có transaction bao quanh hai thao tác, một lỗi giữa chừng để lại đơn không có bản ghi audit.
Nhóm dùng @Transactional cho method nội bộ được gọi từ cùng class; lần ghi dữ liệu thứ nhất vẫn commit dù lần ghi thứ hai ném exception vì proxy transaction không được kích hoạt.
Một service gửi email trước khi commit MongoDB transaction; email đến khách nhưng transaction bị abort do xung đột ghi ở collection tồn kho.
Đội vận hành thấy lỗi transient transaction khi primary được bầu lại; logic retry chạy lại cả quy trình và phát sinh side effect ngoài MongoDB nhiều lần.
Một API xử lý hai request cùng trừ cùng SKU trong transaction; một request bị write conflict và app trả lỗi chung khiến khách không biết giao dịch đã được thực hiện chưa.
Nhóm quản lý tài khoản dùng optimistic locking qua @Version trên document; một bulk update ngoài repository không tăng version và luồng sau không phát hiện thay đổi cạnh tranh.
Ứng dụng gọi findAndModify tăng số lượt sử dụng voucher; hai request có điều kiện lọc chưa ràng buộc số lượt còn lại dẫn tới số dư quota âm.
Đội phát triển bật readConcern snapshot trong một giao dịch báo cáo; transaction lớn và kéo dài khiến bộ nhớ cùng tài nguyên của MongoDB bị áp lực.
Một service dùng MongoTemplate với session gắn transaction nhưng gọi thêm raw driver không sử dụng session đó; cập nhật thứ ba vẫn commit khi transaction chính rollback.
Nhóm tích hợp hai cluster MongoDB khác nhau trong cùng nghiệp vụ; @Transactional trên một MongoTransactionManager không bao phủ được thao tác ghi sang cluster thứ hai.
Một job cập nhật hàng nghìn document trong một transaction; khi dữ liệu hoặc contention tăng, transaction bị abort và toàn bộ batch phải xử lý lại.
Đội QA chạy kiểm thử transaction trên standalone local MongoDB; test không mô phỏng được replica set production và kết quả rollback bị hiểu sai.
Ứng dụng lưu dữ liệu từ request rồi đọc ngay qua secondary trong một quy trình; người dùng thấy thông tin cũ mặc dù transaction ghi trên primary vừa thành công.
Một hệ thống có MongoDB replica set chạy rolling upgrade; một request transaction kéo dài vượt thời hạn cho phép và thất bại giữa chừng trong khi query đọc khác vẫn hoạt động.
Nhóm phát triển chuyển repository blocking sang ReactiveMongoRepository; controller WebFlux vẫn gọi block trên event-loop và làm các request khác chậm đi khi MongoDB quá tải.
Ứng dụng sử dụng ReactiveMongoTemplate trả Flux hàng nghìn document; tầng HTTP gom toàn bộ dữ liệu vào List trước khi trả nên không còn lợi ích streaming mong đợi.
Một endpoint reactive sử dụng publisher lạnh để cập nhật document; service tạo Mono nhưng không có subscriber nên thao tác ghi không diễn ra dù HTTP request trả thành công.
Đội phát triển dùng retry trên Mono ghi dữ liệu; lỗi kết nối xuất hiện sau khi MongoDB đã ghi thành công khiến cùng cập nhật không idempotent được thực thi hai lần.
Ứng dụng reactive truy vấn nhiều collection theo từng item bằng flatMap không giới hạn concurrency; connection pool bị chiếm hết và p99 latency tăng đột ngột.
Nhóm sử dụng ReactiveMongoRepository trong một Function xử lý event; code không giữ subscription phù hợp nên xử lý event hoàn tất trước khi thao tác lưu kết thúc.
Đội tích hợp tạo ReactiveMongoTemplate cho một database phụ; các operator được kết hợp với ReactiveMongoRepository đang trỏ database chính làm dữ liệu ở hai nguồn không thống nhất.
Ứng dụng reactive dùng switchIfEmpty để xử lý trường hợp không tìm thấy ID; một nhánh trả Mono.empty như kết quả thành công và API phản hồi body rỗng ngoài hợp đồng.
Nhóm thiết kế backpressure cho Flux kết quả MongoDB; client đọc chậm và bộ đệm ở tầng serialization tăng dù cursor của database vẫn còn mở.
Một dịch vụ dùng tailable cursor trên capped collection để theo dõi sự kiện; khi collection chưa được tạo đúng loại, luồng theo dõi không hoạt động như kỳ vọng.
Ứng dụng bắt MongoDB change stream để đồng bộ tìm kiếm; khi resume token không được lưu bền vững, tiến trình restart bỏ qua những thay đổi xảy ra trong lúc dịch vụ dừng.
Nhóm xử lý change stream sau kỳ nghỉ dài; resume token tham chiếu lịch sử đã hết trong oplog và đồng bộ không thể tiếp tục từ vị trí cũ.
Một dịch vụ nhận change stream từ nhiều collection; khi có thao tác cập nhật làm thay đổi cấu trúc document, pipeline mapping vẫn mong schema cũ và dừng xử lý sự kiện.
Đội dùng reactive transaction cho hai thao tác MongoDB; một lời gọi được thực thi ngoài cùng reactive chain làm thay đổi không tham gia transaction của publisher chính.
Ứng dụng triển khai cancellation khi client ngắt kết nối; reactive query bị hủy nhưng một tác vụ phụ đã bắt đầu ghi dữ liệu và trạng thái cuối không còn được theo dõi.
Nhóm QA dùng @DataMongoTest để kiểm repository; môi trường test chỉ có dữ liệu ít trường và không phát hiện việc document cũ thiếu field bắt buộc khi map vào entity mới.
Đội phát triển chạy test bằng MongoDB giả lập có ít chức năng; aggregation dùng toán tử đặc thù hoạt động khác trên MongoDB server thật ở production.
Ứng dụng sử dụng Testcontainers MongoDB để kiểm aggregation; bộ test tạo collection mới nhưng chưa xây index production, nên mọi query chạy nhanh và không lộ sai lệch hiệu năng.
Nhóm kiểm thử @Transactional với Testcontainers MongoDB chưa cấu hình replica set; bài test thất bại ở bước mở transaction thay vì kiểm logic rollback mong muốn.
Một dịch vụ triển khai migration tài liệu khi thêm field mới; test chỉ chạy với document mới nên những document cũ không có field đó không được kiểm tra.
Đội QA cần kiểm thử unique index ngăn mã khách hàng trùng; test setup không tạo index nên hai document trùng được insert mà bộ test vẫn báo hợp lệ.
Ứng dụng dùng @Indexed cho trường hết hạn session; bộ test không chạy đủ lâu và không mô phỏng TTL monitor nên chưa xác minh được chính sách xóa dữ liệu.
Nhóm kiểm tra OptimisticLockingFailureException bằng hai lần save tuần tự; cùng một entity instance được dùng lại nên không tái hiện xung đột giữa hai phiên xử lý độc lập.
Một bộ test reactive dùng StepVerifier để kiểm Flux đọc dữ liệu; nhánh hủy subscription trước khi ghi xong không được kiểm và một số thao tác nền bị bỏ sót.
Đội tích hợp chạy test change stream trên database thử nghiệm; test không tạo sự kiện liên tục hoặc không có đủ lịch sử oplog nên logic resume sau sự cố chưa được kiểm.
Ứng dụng lưu dữ liệu tiền tệ hỗn hợp kiểu BSON; dữ liệu test được tạo chỉ bằng converter mới nên lỗi đọc document lịch sử chỉ xuất hiện ở production.
Nhóm chạy load test endpoint MongoDB với dữ liệu đã nằm trong RAM; khi tập dữ liệu lớn hơn cache máy chủ, thời gian đọc ổ đĩa làm latency tăng mạnh ngoài kết quả benchmark.
Một service tăng throughput bằng bulk write nhưng không theo dõi writeErrors theo từng item; dashboard báo đã nhập toàn bộ tệp trong khi hàng trăm document bị từ chối.
Đội vận hành ghi slow query log ở database nhưng không gắn correlation ID từ request Spring Boot; khi p95 của API tăng, nhóm không xác định được query nào thuộc yêu cầu của khách.
Ứng dụng dùng micrometer để đo latency repository; một phần độ trễ phát sinh khi đổi BSON thành object Java không được tách khỏi thời gian MongoDB xử lý query.
Nhóm bật DEBUG log của MongoDB driver để điều tra lỗi mapping; thông tin khách hàng và credential trong URI kết nối có nguy cơ xuất hiện trong hệ thống log dùng chung.
Một hệ thống có query đầy đủ điều kiện tenant nhưng aggregation pipeline báo cáo dùng nhầm MongoTemplate mặc định; nhân viên có thể xem số liệu của những tenant khác.
Đội vận hành chuyển dữ liệu sang sharded cluster; một công việc cập nhật theo mã ID nhưng thiếu shard key làm số shard được truy cập tăng ngoài dự kiến.
Ứng dụng thiết kế xóa mềm document khách hàng nhưng TTL index còn gắn vào cùng collection; tài liệu được lưu phục vụ kiểm toán vẫn bị dọn tự động sau thời hạn cũ.
Nhóm khôi phục backup MongoDB từ snapshot một ngày trước; resume token change stream và checkpoint đồng bộ vẫn ở thời điểm mới hơn khiến dữ liệu tìm kiếm không khớp collection đã khôi phục.
Đội triển khai sửa cấu hình readPreference khi failover; API đọc báo cáo ổn định nhưng endpoint kiểm tra trạng thái giao dịch đôi lúc hiển thị thông tin chưa được cập nhật.
