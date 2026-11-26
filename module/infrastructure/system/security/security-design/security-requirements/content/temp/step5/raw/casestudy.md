Một ứng dụng quản lý hồ sơ khách hàng được yêu cầu phải an toàn nhưng tài liệu sản phẩm chưa xác định dữ liệu nào nhạy cảm, hành vi nào cần ngăn chặn và tiêu chí nào chứng minh hệ thống đạt yêu cầu.
Threat model xác định kẻ tấn công có thể chiếm tài khoản người dùng nhưng backlog chỉ ghi yêu cầu chung là tăng cường đăng nhập, không nêu điều kiện kích hoạt MFA hoặc cách kiểm thử.
Một yêu cầu bảo mật ghi rằng mật khẩu phải mạnh nhưng không quy định độ dài tối thiểu, danh sách mật khẩu bị cấm, giới hạn thử sai hay cách xác minh chính sách được thực thi.
Ứng dụng phục vụ nhân viên và đối tác bên ngoài; nhóm phân tích yêu cầu xác thực chưa phân biệt mức độ đảm bảo danh tính và chính sách phiên cho hai nhóm người dùng.
Một hệ thống xử lý giao dịch có yêu cầu MFA nhưng không xác định thao tác nào cần xác thực tăng cường, thời gian hiệu lực của lần xác thực gần nhất và hành vi khi yếu tố thứ hai không khả dụng.
Yêu cầu đăng nhập qua SSO chỉ nêu hỗ trợ nhà cung cấp danh tính mà không xác định issuer, audience, chữ ký, thời hạn assertion và cách xử lý replay.
Một API dùng bearer token nhưng đặc tả không quy định audience, scope, thời hạn, cơ chế thu hồi hoặc hành vi khi token hết hạn giữa một tác vụ dài.
Nhóm sản phẩm yêu cầu người dùng duy trì đăng nhập trong 30 ngày; nhóm bảo mật cần làm rõ giới hạn idle timeout, absolute lifetime, rotation và điều kiện chấm dứt phiên sau sự cố.
Ứng dụng hỗ trợ khôi phục tài khoản qua email nhưng yêu cầu chưa quy định token dùng một lần, thời hạn, chống dò tài khoản và thu hồi các phiên hiện hữu.
Một tính năng cho phép đổi địa chỉ email đăng nhập; đặc tả chưa nêu bước xác minh chủ tài khoản, thông báo đến địa chỉ cũ và xử lý khi yêu cầu bị chiếm đoạt.
Nhân viên hỗ trợ có thể xem hồ sơ khách hàng; yêu cầu phân quyền chỉ ghi theo vai trò mà chưa mô tả giới hạn theo tenant, vùng dữ liệu, quan hệ sở hữu và mục đích truy cập.
Một API nhận object identifier từ client; đặc tả chưa yêu cầu kiểm tra quyền trên từng object nên người dùng có thể thử truy cập dữ liệu của người khác.
Quản trị viên cần quyền khẩn cấp để hỗ trợ production; yêu cầu chưa quy định phê duyệt, thời hạn quyền, ghi nhận lý do và hậu kiểm sau khi sử dụng.
Hệ thống có nhiều nhóm quyền lồng nhau; yêu cầu phân quyền không nói rõ cách xử lý xung đột giữa quyền cho phép, quyền từ chối và quyền kế thừa.
Một dịch vụ nội bộ gọi API của dịch vụ khác bằng service identity; đặc tả chỉ nêu xác thực giữa dịch vụ mà chưa quy định định danh workload, audience và quyền tối thiểu.
Ứng dụng đa tenant lưu dữ liệu chung trong cùng cơ sở dữ liệu; yêu cầu bảo mật chưa nêu cách cô lập tenant trong truy vấn, cache, tìm kiếm và export.
Một nghiệp vụ cho phép nhân viên xuất báo cáo; yêu cầu chưa phân biệt quyền xem dữ liệu trên màn hình với quyền tải toàn bộ dữ liệu về thiết bị.
Dữ liệu khách hàng gồm thông tin định danh và dữ liệu thanh toán; đặc tả chưa gắn từng loại dữ liệu với yêu cầu mã hóa, masking, retention và quyền truy cập.
Một luồng tích hợp gửi dữ liệu cá nhân sang nhà cung cấp phân tích; yêu cầu chưa nêu trường dữ liệu được phép chia sẻ, mục đích, vùng lưu trữ và thời hạn xóa.
Ứng dụng cần mã hóa dữ liệu lưu trữ; yêu cầu chỉ ghi phải dùng encryption at rest mà không xác định phạm vi volume, backup, replica, snapshot và cách quản lý khóa.
Một API truyền dữ liệu nhạy cảm qua mạng nội bộ; yêu cầu chưa nêu phiên bản TLS tối thiểu, xác minh danh tính peer và cách xử lý chứng thư hết hạn.
Nhóm phát triển muốn lưu thông tin thanh toán trong log để hỗ trợ điều tra; yêu cầu logging chưa quy định trường nào phải che, trường nào bị cấm và ai được đọc log.
Một hệ thống cần audit các thay đổi quyền truy cập; đặc tả chưa yêu cầu ghi actor, target, thời điểm, nguồn yêu cầu, kết quả và tính toàn vẹn của bản ghi.
Yêu cầu lưu log trong một năm chưa phân biệt log bảo mật, log nghiệp vụ và dữ liệu cá nhân; nhóm chưa xác định cơ sở lưu giữ và quy trình xóa an toàn.
Đội vận hành cần phát hiện đăng nhập bất thường; yêu cầu chỉ nói phải có cảnh báo mà không quy định tín hiệu, ngưỡng, độ trễ phát hiện, người nhận và SLA xử lý.
Một dịch vụ có yêu cầu chống brute force nhưng tiêu chí nghiệm thu chỉ kiểm tra một IP; chưa có kịch bản phân tán nguồn, password spraying hoặc ảnh hưởng người dùng hợp lệ.
Ứng dụng upload tài liệu; yêu cầu bảo mật chưa xác định giới hạn kích thước, loại nội dung, thời gian xử lý, cách cô lập parser và hành vi khi tệp độc hại.
Một chức năng tìm kiếm nhận biểu thức lọc do client cung cấp; đặc tả chưa nêu giới hạn độ sâu, độ phức tạp, thời gian chạy và cách ngăn truy vấn gây cạn tài nguyên.
API công khai có yêu cầu rate limit nhưng chưa xác định đơn vị tính theo tài khoản, token, IP, tenant hay endpoint và cách phản hồi khi vượt ngưỡng.
Một hệ thống xử lý webhook từ đối tác; yêu cầu chưa quy định xác minh chữ ký, timestamp, chống replay, giới hạn payload và xử lý sự kiện gửi trùng.
Ứng dụng cần đạt độ sẵn sàng cao; yêu cầu bảo mật và phục hồi chưa xác định RTO, RPO, thời gian phát hiện, thời gian cô lập và tiêu chí khôi phục an toàn.
Một cơ sở dữ liệu chứa dữ liệu quan trọng được sao lưu hằng ngày; đặc tả chưa yêu cầu mã hóa bản sao, kiểm soát quyền restore, kiểm thử khôi phục và bảo vệ khỏi xóa đồng thời.
Hệ thống phải tiếp tục hoạt động khi nhà cung cấp danh tính gián đoạn; yêu cầu chưa xác định hành vi fail-open hay fail-closed cho từng chức năng nhạy cảm.
Một dịch vụ có thể chạy ở chế độ degraded khi hệ thống audit không khả dụng; nhóm cần xác định thao tác nào phải dừng và cách bảo toàn bằng chứng trước khi tiếp tục.
Yêu cầu bảo mật cho API mới được viết sau khi kiến trúc đã hoàn tất; không có liên kết từ rủi ro, trust boundary và data flow đến từng yêu cầu cần triển khai.
Backlog chứa nhiều yêu cầu bảo mật nhưng không gắn mã rủi ro, control owner hoặc thành phần kiến trúc; khi một rủi ro thay đổi nhóm không biết yêu cầu và kiểm thử nào cần xem lại.
Một yêu cầu bảo mật ghi phải ngăn truy cập trái phép nhưng không có điều kiện đầu vào, kết quả mong đợi hoặc phép thử âm tính để xác định đạt hay không.
Nhóm QA có tiêu chí kiểm thử chức năng nhưng chưa có security acceptance criteria; các kiểm thử phân quyền, session expiry và xử lý lỗi bị bỏ khỏi kế hoạch release.
Một yêu cầu ghi hệ thống phải phản hồi nhanh trong khi thực hiện kiểm tra chống lạm dụng; chưa có ngưỡng độ trễ và tải thử để đánh giá đánh đổi giữa bảo mật và hiệu năng.
Ứng dụng cần hỗ trợ thiết bị cũ không còn cập nhật; yêu cầu bảo mật chưa quy định phiên bản giao thức tối thiểu, thời hạn ngoại lệ và điều kiện loại bỏ thiết bị.
Nhà cung cấp bên thứ ba xử lý dữ liệu và xác thực người dùng; yêu cầu tích hợp chưa quy định trách nhiệm kiểm soát, thông báo sự cố, bằng chứng kiểm toán và quyền đánh giá.
Một SDK bên ngoài được nhúng vào ứng dụng khách; đặc tả chưa xác định dữ liệu SDK được phép thu thập, endpoint đích, quyền thiết bị và cách cập nhật khi có lỗ hổng.
Pipeline triển khai có thể bỏ qua bước security scan khi build khẩn cấp; yêu cầu release chưa xác định gate bắt buộc, thẩm quyền phê duyệt ngoại lệ và kiểm tra bù sau triển khai.
Một thay đổi schema làm thêm trường chứa dữ liệu nhạy cảm; quy trình quản lý yêu cầu không kích hoạt đánh giá phân loại dữ liệu, masking, logging và retention liên quan.
Đội phát triển thay đổi luồng đăng nhập từ mật khẩu sang passkey; bộ yêu cầu cũ vẫn giả định password reset và không bao phủ đăng ký, thu hồi hoặc khôi phục authenticator.
Một ứng dụng bổ sung tính năng chia sẻ tài liệu công khai theo liên kết; yêu cầu chưa xác định entropy của link token, thời hạn, thu hồi, phạm vi quyền và khả năng lập chỉ mục.
Chức năng xóa tài khoản được triển khai nhưng chưa có yêu cầu xác định dữ liệu nào phải xóa, dữ liệu nào phải giữ theo nghĩa vụ và thời hạn xóa bản sao trong backup.
Yêu cầu lưu trữ dữ liệu theo khu vực địa lý chưa mô tả cách xử lý log, telemetry, backup và bản sao hỗ trợ vận hành được gửi ra ngoài khu vực.
Một nhóm đề xuất dùng CAPTCHA để chống bot; yêu cầu chưa xác định điều kiện kích hoạt, khả năng tiếp cận, phương án cho người dùng không thể hoàn thành và cách đo hiệu quả.
Một hệ thống hỗ trợ quyền truy cập tạm thời; yêu cầu chưa nêu thời gian tối đa, tự động hết hạn, gia hạn, thu hồi sớm và cách xác minh quyền đã mất hiệu lực.
Nhóm bảo mật yêu cầu mọi secret phải được xoay vòng định kỳ; đặc tả chưa xác định loại secret, chu kỳ, overlap, phát hiện thất bại và tiêu chí xác nhận credential cũ đã bị thu hồi.
Một ứng dụng ghi nhận sự kiện bảo mật không đồng bộ; yêu cầu chưa quy định thứ tự, chống mất log, xử lý queue đầy và cách phát hiện khoảng trống trong audit trail.
Đội sản phẩm cần chứng minh một yêu cầu bảo mật đã được triển khai; hiện tại không có liên kết từ requirement đến commit, cấu hình, test case, kết quả kiểm thử và bằng chứng production.
Trong một kỳ đánh giá, threat model thay đổi vì thêm đối tác và API mới; quy trình quản lý yêu cầu chưa xác định cách phân tích tác động và cập nhật tiêu chí nghiệm thu liên quan.
Một yêu cầu bảo mật được đánh dấu hoàn thành sau khi code merge; chưa có bằng chứng cấu hình production, kiểm thử triển khai và giám sát vận hành đáp ứng tiêu chí đã đặt ra.
Ban quản lý chấp nhận ngoại lệ cho một yêu cầu chưa đáp ứng vì phụ thuộc hệ thống cũ; hồ sơ không ghi rủi ro còn lại, biện pháp bù trừ, người phê duyệt và ngày hết hạn.
Một yêu cầu được áp dụng cho mọi hệ thống dù một số workload có mức nhạy cảm và mô hình đe dọa khác nhau; nhóm chưa có quy tắc phân tầng yêu cầu theo rủi ro.
Một sản phẩm hoạt động ở nhiều quốc gia với quy định dữ liệu khác nhau; bộ yêu cầu chưa chỉ rõ yêu cầu pháp lý nào áp dụng cho tenant, loại dữ liệu và khu vực triển khai nào.
Một hệ thống thay đổi từ kiến trúc đơn khối sang microservices; yêu cầu bảo mật cũ không đề cập service-to-service identity, phân đoạn mạng, traceability và xử lý lỗi giữa các dịch vụ.
