Một sàn thương mại điện tử đang chuyển từ các đường dẫn theo hành động sang REST API cho danh mục sản phẩm, biến thể màu và kích cỡ; ứng dụng web và đối tác bán hàng hiện dùng các cách định danh khác nhau nên thường truy xuất nhầm tài nguyên.
Ứng dụng giao đồ ăn cho phép nhà hàng sửa giá, mô tả và trạng thái bán của từng món; khi nhân viên chỉ thay giá, dữ liệu mô tả do người khác vừa cập nhật lại bị ghi đè trong cùng yêu cầu HTTP.
Hệ thống quản lý vận tải cho tài xế đổi một phần địa chỉ giao hàng khi đang trên đường; một số khách hàng gửi toàn bộ đối tượng địa chỉ, số khác chỉ gửi trường thay đổi, khiến hợp đồng cập nhật không nhất quán.
Cổng đăng ký lớp học nhận yêu cầu ghi danh từ ứng dụng di động; khi mạng chập chờn, ứng dụng gửi lại yêu cầu và sinh hai lượt đăng ký cho cùng học viên, làm sai số chỗ còn trống.
Nền tảng đặt vé máy bay cần xử lý yêu cầu hủy vé qua API; có vé còn được hoàn, có vé đã làm thủ tục bay, nhưng khách hàng nhận cùng một mã phản hồi dù thao tác hủy có thành công hay không.
Ứng dụng bán lẻ tạo đơn hàng rồi chuyển qua xác nhận và giao vận; một đối tác muốn thay đổi trực tiếp trạng thái đã giao bằng yêu cầu cập nhật, trong khi hệ thống chỉ cho phép những bước chuyển trạng thái nhất định.
Dịch vụ hoàn tiền nhận yêu cầu từ cổng chăm sóc khách hàng; nhân viên bấm gửi hai lần và bộ cân bằng tải thử lại khi hết thời gian chờ, khiến một giao dịch có nguy cơ hoàn tiền nhiều lần.
Trong đợt mở bán giới hạn, hàng nghìn yêu cầu mua cùng một sản phẩm đi vào REST API gần như đồng thời; số lượng tồn kho hiển thị còn hàng nhưng vài đơn đã xác nhận vượt lượng thực tế.
Hệ thống bán vé sự kiện cho phép giữ ghế trong thời gian ngắn; hai khách cùng chọn một ghế và cùng nhận kết quả giữ chỗ thành công dù ghế chỉ có thể thuộc về một đơn.
Một API chuyển khoản nội bộ gọi hệ thống thanh toán xử lý mất nhiều phút; ứng dụng khách ngắt kết nối sau vài giây và không biết giao dịch đang chờ, đã hoàn tất hay đã thất bại.
Dịch vụ tạo hồ sơ bảo hiểm trả về mã thành công khi tiếp nhận hồ sơ mới nhưng không cung cấp thông tin rõ ràng để ứng dụng gọi tiếp lấy tài nguyên vừa tạo, khiến khách hàng không xác định được hồ sơ nào đã được lưu.
Ứng dụng khám bệnh gửi dữ liệu đặt lịch thiếu mã bác sĩ, đôi khi gửi khung giờ đã bị người khác chiếm; cả hai trường hợp đều hiển thị thông báo lỗi chung nên người dùng không biết phải sửa dữ liệu hay chọn lịch khác.
Ứng dụng quản lý nhân sự gọi API bằng phiên đăng nhập đã hết hạn, còn tài khoản khác đăng nhập hợp lệ nhưng không có quyền xem bảng lương; hai trường hợp nhận cùng phản hồi khiến client xử lý đăng nhập lại không đúng.
Một phòng khám cho nhân viên lễ tân xem lịch hẹn và bác sĩ xem bệnh án; API chỉ kiểm tra người gọi đã đăng nhập nên lễ tân có thể truy cập dữ liệu bệnh án qua đường dẫn trực tiếp.
Nền tảng phần mềm phục vụ nhiều doanh nghiệp sử dụng mã khách hàng trong URI; người dùng thuộc doanh nghiệp A thay mã trong yêu cầu và nhìn thấy hóa đơn của doanh nghiệp B dù quyền truy cập đã được kiểm tra ở giao diện.
Hệ thống quản lý cộng tác viên thu hồi quyền của một tài khoản ngay sau khi kết thúc hợp đồng; ứng dụng vẫn giữ access token còn hiệu lực và tiếp tục sửa dữ liệu dự án trong vài phút.
Một đối tác tích hợp truyền khóa truy cập REST API trong tham số URL; bản ghi truy cập của reverse proxy và công cụ phân tích lưu lại toàn bộ URL, khiến thông tin xác thực xuất hiện ở nhiều nơi ngoài hệ thống chính.
Cổng thông tin khách hàng trả về địa chỉ, số điện thoại và lịch sử giao dịch; dữ liệu của một người đôi khi xuất hiện trên màn hình người khác sau khi đi qua lớp cache chung của hệ thống.
Trang bán hàng hiển thị giá và số lượng tồn qua API; proxy vẫn trả dữ liệu đã lưu trong khi chương trình khuyến mãi vừa kết thúc, làm khách đặt hàng theo mức giá không còn hiệu lực.
Một sản phẩm bị thu hồi khỏi danh mục nhưng đường dẫn công khai của sản phẩm vẫn trả nội dung cũ từ CDN; nhân viên vận hành không biết bao lâu thông tin đã bị gỡ mới biến mất khỏi các điểm truy cập.
Ứng dụng di động kiểm tra bảng tin cập nhật liên tục qua REST API; dù không có bài viết mới, hàng nghìn thiết bị vẫn tải lại toàn bộ phản hồi và tiêu tốn băng thông đáng kể.
Hai nhân viên cùng sửa một hồ sơ nhà cung cấp trên màn hình khác nhau; người lưu sau làm mất thay đổi của người lưu trước, dù cả hai đã xem phiên bản dữ liệu hợp lệ tại thời điểm mở trang.
API lịch sử giao dịch phân trang theo vị trí đang phục vụ ứng dụng ngân hàng; khi có giao dịch mới chen vào đầu danh sách, người dùng lướt trang tiếp theo thấy bản ghi lặp lại hoặc bị bỏ sót.
Hệ thống bình luận có hàng triệu bản ghi, người dùng tải thêm theo thời gian; các bình luận cùng thời điểm tạo khiến thứ tự qua các trang không ổn định khi nhiều người đăng đồng thời.
Trang quản trị yêu cầu API trả tổng số bản ghi cùng từng trang kết quả; bộ lọc trên tập dữ liệu hàng chục triệu dòng khiến thao tác đếm làm thời gian phản hồi tăng mạnh.
Khách hàng tìm khách sạn theo giá và đánh giá; nhiều kết quả có cùng giá nhưng thứ tự thay đổi giữa các lần gọi, khiến một khách sạn xuất hiện ở hai trang khác nhau.
Dịch vụ tìm kiếm bất động sản nhận bộ lọc nhiều quận, khoảng giá và từ khóa có ký tự đặc biệt; liên kết được ứng dụng tạo ra đôi khi bị máy chủ hiểu sai tham số truy vấn.
API bán vé bị một đối tác gọi liên tục trong lúc mở bán; lưu lượng của đối tác này chiếm gần hết năng lực phục vụ khiến người dùng thông thường liên tục gặp lỗi và không biết khi nào có thể thử lại.
Nền tảng học trực tuyến cho quản trị viên nhập danh sách hàng trăm học viên trong một yêu cầu; có bản ghi hợp lệ và bản ghi trùng email, nhưng phản hồi hiện tại không cho biết bản ghi nào đã được tạo.
Hệ thống kế toán cho tải báo cáo giao dịch một năm qua REST API; truy vấn và tạo tệp mất quá thời gian chờ của gateway, khiến client gửi lại nhiều lần và phát sinh tác vụ trùng lặp.
Nhóm phát triển cập nhật hành vi một endpoint trong dịch vụ Java/Spring nhưng tài liệu OpenAPI vẫn ghi cấu trúc phản hồi cũ; nhóm ứng dụng di động sinh client từ tài liệu và gặp lỗi khi triển khai.
Ứng dụng đặt phòng đã phát hành nhiều phiên bản trên điện thoại; API muốn đổi tên và kiểu dữ liệu trường ngày nhận phòng nhưng phiên bản ứng dụng cũ vẫn phải tiếp tục hoạt động.
Một dịch vụ giao hàng bổ sung trường tùy chọn vào JSON phản hồi; phiên bản ứng dụng cũ có bộ giải mã nghiêm ngặt và bắt đầu từ chối phản hồi có trường mà nó chưa biết.
API lập hóa đơn trao đổi đơn giá, thuế và tổng tiền giữa hệ thống bán hàng và kế toán; bên gửi dùng số thực còn bên nhận làm tròn theo cách khác, tạo chênh lệch tiền trên hóa đơn.
Nền tảng đặt lịch làm việc phục vụ khách ở nhiều múi giờ; dữ liệu API chỉ ghi ngày giờ địa phương nên cuộc hẹn bị hiển thị sai khi khách du lịch đổi múi giờ hoặc khu vực chuyển giờ mùa hè.
API cập nhật hồ sơ khách hàng phân biệt trường không được gửi, trường có giá trị rỗng và trường mang giá trị null không rõ ràng; nhiều yêu cầu sửa một thuộc tính vô tình xóa thông tin liên hệ đã lưu.
Hệ thống gồm nhiều dịch vụ REST trả lỗi theo các cấu trúc JSON khác nhau; ứng dụng web không thể xác định nhất quán mã lỗi nghiệp vụ, trường dữ liệu sai và thông điệp phù hợp để hiển thị.
Một lỗi kết nối cơ sở dữ liệu làm API trả chi tiết exception và đường dẫn nội bộ trong phản hồi; thông tin vận hành nhạy cảm xuất hiện trên màn hình người dùng và trong báo cáo lỗi do trình duyệt gửi về.
Giao diện quản lý bán hàng chạy trên tên miền khác với REST API; các yêu cầu đọc dữ liệu hoạt động nhưng yêu cầu cập nhật có header xác thực bị trình duyệt chặn trước khi gửi tới máy chủ.
Ứng dụng bảo hiểm cho khách tải ảnh giấy tờ và tệp PDF qua REST API; một số bản tải vượt giới hạn kích thước hoặc mang loại nội dung không đúng, nhưng hệ thống xử lý lỗi thiếu thống nhất.
Cổng phân phối tài liệu cho phép tải các tệp lớn qua API; mạng di động thường ngắt giữa chừng và ứng dụng phải tải lại từ đầu, làm khách hàng mất dữ liệu đã nhận và tốn dung lượng.
API tra cứu đơn hàng cần gọi dịch vụ vận chuyển bên thứ ba; khi bên thứ ba phản hồi chậm, toàn bộ yêu cầu treo tới lúc gateway hết thời gian chờ dù dữ liệu đơn hàng nội bộ vẫn có sẵn.
Đội vận hành điều tra một yêu cầu thanh toán đi qua gateway và nhiều dịch vụ; nhật ký của các thành phần không có thông tin liên kết chung, trong khi việc ghi nguyên payload có thể làm lộ dữ liệu cá nhân.
Màn hình quản trị hiển thị 50 đơn hàng cùng thông tin khách mua và mặt hàng; một lần gọi REST API kích hoạt hàng trăm truy vấn cơ sở dữ liệu, khiến thời gian tải tăng đột biến khi dữ liệu lớn.
API quản lý tài khoản nhận đối tượng JSON có nhiều thuộc tính; người dùng tự bổ sung trường vai trò quản trị vào yêu cầu sửa hồ sơ và hệ thống có nguy cơ ghi thay đổi mà người đó không được phép.
Dịch vụ y tế cho bệnh nhân chia sẻ kết quả xét nghiệm với bác sĩ theo thời hạn đồng ý; sau khi bệnh nhân rút quyền, đường dẫn tài nguyên cũ vẫn được truy cập bằng tài khoản bác sĩ.
Nhóm bảo trì một API Spring thường chỉ kiểm thử trường hợp phản hồi thành công; sau lần thay đổi bộ lọc xác thực, các yêu cầu sai dữ liệu và thiếu quyền vẫn vượt qua bộ kiểm thử nhưng lỗi khi tích hợp.
Trong kiểm thử tải API đặt phòng, nhiều yêu cầu từ cùng tài khoản được gửi đồng thời tới chức năng đặt chỗ và hủy chỗ; dữ liệu cuối cùng không khớp với phản hồi mà các client đã nhận.
Ứng dụng quản lý dự án xóa mềm một công việc để phục vụ kiểm toán; màn hình chi tiết, danh sách, liên kết cũ và API của đối tác lại thể hiện tài nguyên đã xóa theo những cách khác nhau.
Một REST API quản lý kho được cả ứng dụng nội bộ lẫn đối tác sử dụng; thao tác xóa một địa điểm lưu trữ có hàng hóa và lịch sử kiểm kê liên quan khiến các hệ thống không thống nhất về trạng thái tài nguyên.
