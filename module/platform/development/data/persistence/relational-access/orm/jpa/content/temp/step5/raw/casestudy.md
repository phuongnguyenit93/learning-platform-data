Trong hệ thống quản lý đơn hàng dùng Jakarta Persistence, bảng đơn hàng có khóa tự tăng nhưng entity lại nhận mã đơn do ứng dụng tự sinh; khi lưu một đơn mới, nhóm gặp lỗi trùng khóa và chưa thống nhất ai chịu trách nhiệm tạo định danh.
Ứng dụng SaaS dùng cặp tenantId và invoiceNumber làm khóa hóa đơn; hai entity biểu diễn cùng bản ghi vẫn bị xem là khác khi đưa vào Set vì cách thiết kế khóa ghép và quy tắc equals, hashCode chưa nhất quán.
Một entity hồ sơ khách hàng chỉ có constructor yêu cầu đầy đủ tham số; chương trình Java tự tạo đối tượng bình thường, nhưng cơ chế nạp entity từ database của provider không khởi tạo được nó.
Nhóm ánh xạ quan hệ một-nhiều giữa Customer và Order; ứng dụng chỉ thêm đơn vào danh sách ở Customer mà không cập nhật phía sở hữu khóa ngoại, khiến dữ liệu sau commit không có liên kết mong đợi.
Trong cửa hàng trực tuyến, quan hệ nhiều-nhiều giữa Product và Promotion dùng bảng nối; cùng chương trình khuyến mãi được thêm nhiều lần và team phải xác định rõ ý nghĩa danh tính của phần tử cùng khóa ghép bảng nối.
Ứng dụng tuyển dụng lưu Candidate và danh sách Attachment; khi xóa một phần tử khỏi collection, tập tin đính kèm vẫn tồn tại trong cơ sở dữ liệu dù đội sản phẩm muốn xóa dữ liệu không còn thuộc hồ sơ.
Một lập trình viên bật cascade REMOVE trên quan hệ Order tới bảng Currency dùng chung; thao tác xóa đơn hàng có nguy cơ tác động tới dữ liệu danh mục đang được các đơn khác tham chiếu.
Nhóm dùng Embeddable để ánh xạ hai địa chỉ giao hàng và thanh toán trong cùng bảng Customer; các cột street, city bị trùng tên và quá trình xây schema không phân biệt được hai nhóm thuộc tính.
Ứng dụng lưu trạng thái hợp đồng bằng enum ordinal; sau khi thêm một trạng thái mới vào giữa enum, các bản ghi cũ bị hiển thị với ý nghĩa khác mà không có migration dữ liệu.
Hệ thống bệnh viện chia Person thành Doctor và Patient với các thuộc tính khác nhau; team chuyển chiến lược inheritance mapping khi bảng đã có dữ liệu và báo cáo truy vấn đa hình không còn khớp số lượng trước đó.
Trong service thanh toán, một tham chiếu ManyToOne tới Merchant được tải cùng Transaction dù màn hình chỉ cần mã merchant; truy vấn trả về nhiều trường không dùng làm tăng chi phí khi xử lý lịch sử giao dịch.
Một API trả danh sách hóa đơn kèm từng khách hàng; lớp mapper truy cập thuộc tính liên kết trong vòng lặp và dashboard database ghi nhận một truy vấn gốc cùng hàng trăm truy vấn bổ sung.
Nhóm thêm fetch join vào collection OrderLine để tránh nhiều truy vấn, sau đó áp dụng phân trang kết quả Order; số đơn trong từng trang và cách thực thi truy vấn thay đổi bất thường.
Dịch vụ báo cáo truy vấn Order đồng thời fetch join danh sách Line và Tag; kết quả chứa nhiều hàng cho cùng một đơn, khiến nhóm nhầm số hàng SQL với số entity gốc cần hiển thị.
Một endpoint lấy chi tiết khách hàng từ entity đã tải trong transaction, sau đó đóng transaction mới chuyển entity sang tầng JSON; việc truy cập quan hệ lazy tại bước xuất response gây lỗi ở production.
Trang quản trị hiển thị danh sách đơn hàng và màn chi tiết với nhu cầu liên kết khác nhau; nhóm dùng chung một fetch plan lớn cho cả hai, khiến truy vấn danh sách tải quá nhiều dữ liệu.
Nhóm viết JPQL dùng tên bảng vật lý và tên cột của database thay cho tên entity và thuộc tính ánh xạ; câu truy vấn hoạt động với SQL thuần nhưng không được trình phân tích JPQL chấp nhận.
Trong chức năng tìm tài khoản chưa có người giới thiệu, lập trình viên xây biểu thức JPQL so sánh quan hệ bằng dấu bằng với null; kết quả bỏ sót những bản ghi cần tìm.
Ứng dụng xây bộ lọc động bằng Criteria API cho ngày đặt hàng, trạng thái và tổng tiền; một filter vắng mặt làm predicate trở thành điều kiện không đúng như nghiệp vụ, khiến trang tìm kiếm rỗng.
Trong một truy vấn Criteria, nhóm dùng đường dẫn thuộc tính dạng chuỗi thay cho metamodel được kiểm tra kiểu; việc đổi tên trường entity sau refactor chỉ gây lỗi khi endpoint tìm kiếm thực sự chạy.
Nhóm cho phép nhân viên tìm khách hàng theo tên tự nhập rồi nối trực tiếp giá trị vào chuỗi JPQL; một dấu nháy trong họ tên khiến truy vấn thất bại và việc xử lý đầu vào chưa được xác định.
Trong một request, EntityManager đã tải trạng thái hợp đồng rồi một batch khác cập nhật cùng hàng; lần find tiếp theo trong cùng persistence context vẫn trả dữ liệu cũ dù câu hỏi nghiệp vụ cần giá trị mới nhất.
Một entity mới có ID do database cấp sau khi lưu; ứng dụng thêm entity vào HashSet trước lúc nhận ID, rồi không còn tìm thấy phần tử theo cách so sánh hiện hành sau khi ID thay đổi.
Trong luồng cập nhật địa chỉ, entity được đọc ở request trước và truyền sang request sau như đối tượng thông thường; nhóm sửa field rồi chờ dirty checking tự ghi xuống database nhưng không có thay đổi nào được lưu.
Một màn hình cập nhật khách hàng gửi toàn bộ entity cũ về máy chủ; team dùng merge mà không xem xét trường đã thay đổi ở nơi khác, khiến dữ liệu cập nhật gần đây có nguy cơ bị ghi đè.
Ứng dụng gọi persist cho entity có tham chiếu tới đối tượng liên quan chưa được lưu; cấu hình cascade không phù hợp và lỗi chỉ xuất hiện khi provider flush thay đổi về database.
Nhóm phát hành hóa đơn gọi flush ngay sau khi ghi dữ liệu rồi coi đó là giao dịch đã thành công; một exception ở bước nghiệp vụ tiếp theo làm transaction rollback dù log trước đó ghi đã flush.
Dịch vụ nhập hàng loạt gọi persist cho hàng chục nghìn entity trong cùng persistence context; bộ nhớ tiến trình tăng nhanh vì các đối tượng và trạng thái theo dõi tiếp tục được giữ đến cuối batch.
Trong giao diện quản trị, một truy vấn JPQL bulk update khóa hàng nghìn tài khoản; các Account đang managed trong cùng transaction vẫn mang trạng thái cũ, dẫn đến logic tiếp theo đánh giá sai điều kiện.
Một batch xóa dữ liệu sử dụng JPQL bulk delete trong khi persistence context vẫn giữ các entity liên quan; nhóm thấy sự lệch nhau giữa dữ liệu đang giữ trong bộ nhớ và trạng thái thật ở database.
Service tạo tài khoản mới gọi persist ngoài transaction quản lý phù hợp; môi trường test đọc được entity trong bộ nhớ nhưng thao tác đồng bộ xuống cơ sở dữ liệu không diễn ra như dự kiến.
Chức năng đặt hàng ghi đơn và trừ tồn kho ở hai transaction tách biệt; nếu transaction thứ hai thất bại, đơn đã xuất hiện dù số lượng tồn chưa được cập nhật.
Hai nhân viên cùng chỉnh sửa ghi chú trên một đơn hàng; hệ thống không dùng cơ chế phát hiện cập nhật đồng thời nên thay đổi của người lưu sau ghi đè nội dung của người lưu trước.
Nhóm bổ sung trường version để dùng optimistic locking trên entity tồn kho; khi hai giao dịch sửa cùng hàng, một giao dịch nhận xung đột vào thời điểm flush hoặc commit nhưng UI đang báo lưu thành công.
Trong đợt giảm giá, nhiều request đặt cùng sản phẩm hiếm đồng thời; nhóm dùng optimistic lock nhưng lưu lượng retry cao và phải đánh giá tác động tới độ trễ cùng trải nghiệm khách hàng.
Dịch vụ giữ chỗ dùng pessimistic locking cho các bản ghi Seat; hai giao dịch khóa các ghế theo thứ tự ngược nhau nên một số request hết thời gian chờ hoặc bị database phát hiện deadlock.
Trước khi tạo tài khoản, API kiểm tra không tồn tại email trùng bằng truy vấn JPQL; hai request đồng thời đều vượt kiểm tra rồi cùng chèn, khiến nhóm phải xét ràng buộc duy nhất ở database.
Trong hệ thống kế toán, một truy vấn tổng hợp số dư chạy nhiều lần trong transaction dài; giao dịch khác liên tục thêm bút toán và kết quả thay đổi tùy isolation level của cơ sở dữ liệu.
Nhóm đặt callback vòng đời entity để gửi email ngay khi ghi nhận thanh toán; transaction sau đó rollback nhưng email vẫn đã gửi, khiến trạng thái ở hệ thống ngoài không khớp database.
Ứng dụng chạy tác vụ nền sau khi HTTP request kết thúc và chuyển cho tác vụ một entity còn tham chiếu lazy; thread nền không có persistence context phù hợp để nạp thêm dữ liệu khi xử lý.
