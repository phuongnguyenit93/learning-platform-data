Nhóm platform quyết định chuyển từ cơ sở dữ liệu quan hệ sang lưu trữ tài liệu nhưng chỉ ghi dòng 'MongoDB linh hoạt hơn' trong wiki; sáu tháng sau không ai biết các yêu cầu truy vấn và giới hạn giao dịch lúc lựa chọn.
Đội backend chọn Kafka thay cho REST đồng bộ để truyền sự kiện đơn hàng; bản ghi quyết định chỉ liệt kê lợi ích mà không nêu chi phí vận hành broker và độ phức tạp xử lý trùng.
Trong một dự án thương mại điện tử, hai phương án triển khai monolith theo module và microservice được thảo luận; ADR chỉ lưu phương án được chọn nên nhóm mới không hiểu vì sao phương án còn lại bị loại.
Một hệ thống xử lý dữ liệu cá nhân cần lưu thông tin tại Việt Nam; tài liệu chọn cloud region không ghi ràng buộc pháp lý làm bối cảnh và một nhóm khác đề xuất di chuyển dữ liệu sang vùng khác.
Đội kiến trúc chọn sử dụng cache phân tán vì yêu cầu phản hồi nhanh; ADR không ghi giả định về lưu lượng hoặc thời gian tồn tại dữ liệu nên bản thiết kế bị áp dụng cho một workload khác.
Trong dự án ngân hàng, lựa chọn optimistic locking được ghi lại như quy tắc bất biến; khi tải ghi tăng đột biến, đội vận hành chưa biết những điều kiện nào sẽ buộc xem lại lựa chọn đó.
Một kỹ sư viết ADR mô tả cách dùng library mới nhưng không nêu vấn đề kiến trúc cần giải quyết; reviewer không xác định được đây là quyết định dài hạn hay hướng dẫn triển khai tạm thời.
Nhóm thiết kế xác thực cần chọn giữa session phía server và JWT; bản ghi chỉ mô tả cú pháp token mà không so sánh khả năng thu hồi phiên, độ phức tạp vận hành và yêu cầu đăng xuất.
Đội hạ tầng quyết định dùng một cụm database chung cho các tenant nhưng không ghi hậu quả về cô lập tài nguyên; khi xuất hiện tenant lớn gây nghẽn, nhóm sản phẩm bất ngờ trước đánh đổi đã chấp nhận.
Trong ứng dụng đặt lịch, nhóm chọn xử lý đồng bộ để đơn giản hóa trải nghiệm; ADR không nêu mức thời gian phản hồi được chấp nhận nên các service sau thêm nhiều lời gọi nối tiếp.
Một ADR khẳng định NoSQL có độ mở rộng tốt hơn SQL trong mọi trường hợp; thành viên mới nhận định lựa chọn thiếu bằng chứng benchmark gắn với dạng truy vấn thực tế của hệ thống.
Đội chọn giải pháp tự xây thay vì mua dịch vụ ngoài cho tìm kiếm; tài liệu không ghi chi phí duy trì, năng lực nhân sự hoặc rủi ro khóa nhà cung cấp ở các phương án được đánh giá.
Nhóm bảo mật chấp thuận mã hóa trường nhạy cảm ở tầng ứng dụng; hậu quả đối với tìm kiếm, index và khóa mã hóa không được mô tả khiến team dữ liệu gặp trở ngại khi làm báo cáo.
Một ADR lựa chọn giao thức gRPC nhưng không chỉ ra những consumer cần truy cập qua trình duyệt hoặc mạng bị chặn HTTP/2; đến lúc tích hợp đối tác mới phát sinh chi phí adapter.
Kiến trúc sư viết ADR về phân vùng dữ liệu theo khách hàng nhưng bỏ qua phương án chuyển tenant sang phân vùng khác; khi một tenant tăng quy mô, đội không biết giới hạn ban đầu.
Trong hệ thống nhiều ngôn ngữ, nhóm chọn UTC làm thời điểm lưu trữ; bản ghi không nêu hệ quả đối với thao tác nhập giờ địa phương và các ngày chuyển giờ mùa hè.
Đội kỹ thuật bàn chọn framework tại cuộc họp nhưng không lưu người tham gia, ngày chốt và tình trạng phê duyệt; hai nhóm triển khai khác nhau vì đều nghĩ quyết định chưa cuối cùng.
Một kỹ sư tạo ADR với trạng thái Accepted ngay sau khi đề xuất; các nhóm ảnh hưởng chưa review và chỉ phát hiện tác động tới pipeline triển khai khi code đã merge.
Nhóm phát hành ADR Proposed về tách database theo service, nhưng ticket triển khai được giao ngay như thể ADR đã được thông qua; team không thống nhất thời điểm được phép bắt đầu thay đổi.
Trong buổi review, ba thành viên nêu ý kiến trái chiều về cách chia bounded context; bản ghi cuối cùng chỉ chứa lựa chọn mà không phản ánh rủi ro hoặc quan điểm phản biện quan trọng.
Đội kiến trúc đạt đồng thuận về phương án cache nhưng điều kiện chấp nhận phụ thuộc thử nghiệm tải; ADR chuyển sang Accepted trước khi kết quả thử nghiệm được ghi nhận.
Trong repository có hai ADR cùng đề xuất chọn công nghệ message queue khác nhau, cả hai đều mang trạng thái Accepted; người xây service mới không biết văn bản nào còn hiệu lực.
Một nhóm thay đổi từ polling sang CDC nhưng xóa ADR cũ rồi viết tài liệu mới; sau đó không thể truy vết lý do thiết kế polling trước đây và điều kiện khiến quyết định bị thay thế.
Đội vận hành dừng hỗ trợ một JDK cũ theo quyết định mới; ADR trước đó vẫn ở trạng thái Accepted và không liên kết với tài liệu thay thế nên tài liệu công khai bị mâu thuẫn.
Nhóm thử nghiệm event sourcing trong một module, sau đó quyết định không áp dụng; ADR thử nghiệm bị xóa như một thất bại thay vì lưu nguyên nhân từ chối cho những người đánh giá lại sau này.
Trong dự án di chuyển dữ liệu, ADR từng chấp thuận một chiến lược migration nhưng dự án bị hủy do thay đổi ngân sách; trạng thái tài liệu không phản ánh rằng quyết định không còn được triển khai.
Một team đặt tên ADR theo tên người viết và ngày không có mã ổn định; khi đổi thư mục trong repository, liên kết từ ticket và pull request tới quyết định bị hỏng.
Đội có hơn một trăm ADR rải rác trong ba repository; khi phát triển tính năng mới, kỹ sư không tìm được các quyết định liên quan đến lưu trữ, bảo mật và tính nhất quán dữ liệu.
Nhóm viết ADR cho giới hạn độ trễ API nhưng không liên kết với đặc tả SLA, kết quả thử nghiệm hoặc ticket; reviewer khó xác minh bối cảnh được nêu có còn đúng.
Một pull request thay đổi cơ chế retry của mọi service nhưng không chỉ ra ADR đang áp dụng; code và quyết định về giới hạn retry bắt đầu khác nhau sau vài đợt bảo trì.
Ứng dụng mới đã thay cơ chế xác thực, nhưng sơ đồ kiến trúc và ADR vẫn mô tả lựa chọn cũ; nhân viên onboarding thiết kế sai một tính năng vì tin vào tài liệu đã lỗi thời.
Nhóm phân tích một sự cố lớn do cache stale; hậu kiểm chỉ sửa code mà không đối chiếu ADR trước đó từng chấp nhận dữ liệu cũ tối đa năm phút.
Một cuộc review ADR bị kéo dài vì mọi người tranh luận tên class và cấu trúc method thay vì nguyên tắc phân tách service; văn bản không xác định rõ mức quyết định cần chốt.
Đội backend ghi mỗi thay đổi cấu hình nhỏ thành một ADR mới; số lượng tài liệu tăng nhanh nhưng các lựa chọn có ảnh hưởng dài hạn lại khó được nhận diện.
Trong công ty có hai sản phẩm, một team muốn tái sử dụng ADR chọn database của sản phẩm khác mà không xem xét chênh lệch lưu lượng, thời gian truy vấn và yêu cầu giao dịch.
Người chịu trách nhiệm ADR rời dự án; một năm sau điều kiện sử dụng thư viện bảo mật thay đổi nhưng không có quy trình xác định ai sở hữu việc đánh giá lại quyết định.
Một ADR ghi 'giảm chi phí 30%' như hệ quả kỳ vọng của chuyển workload sang dịch vụ managed; sau ba tháng, kết quả chi phí cao hơn dự kiến nhưng không có nơi ghi đánh giá hậu quyết định.
Nhóm kiến trúc ghi một phương án như lựa chọn tạm thời trong giai đoạn MVP nhưng không nêu thời hạn hoặc tín hiệu cần xem xét lại; nhiều năm sau nó vẫn được coi là chính sách cố định.
Đội xây quy trình review ADR nhưng yêu cầu phê duyệt của toàn bộ tổ chức cho mọi quyết định; một thay đổi nội bộ nhỏ bị chặn hàng tuần dù chỉ ảnh hưởng một nhóm.
Trong đợt kiểm toán, công ty cần giải thích ai chấp thuận lưu sự kiện trong bảy năm và vì sao; lịch sử thay đổi ADR trong repository có nhiều lần sửa trực tiếp vào bản Accepted mà không ghi nhận phương án trước.
