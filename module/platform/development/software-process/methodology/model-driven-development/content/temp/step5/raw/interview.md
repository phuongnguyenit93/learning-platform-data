Model-Driven Development thay đổi vai trò của mô hình trong vòng đời phát triển phần mềm so với cách dùng sơ đồ chỉ để trao đổi như thế nào?
Bạn xác định những phần nào của hệ thống phù hợp để mô tả bằng mô hình trước khi viết mã dựa trên tiêu chí nào?
Khi một quy tắc nghiệp vụ chỉ xuất hiện trong code mà không nằm trong mô hình, bạn đánh giá hệ quả đối với cách làm model-driven ra sao?
Bạn phân biệt mô hình miền, mô hình kiến trúc và mô hình triển khai theo mục đích và mức trừu tượng như thế nào?
Bạn làm rõ ranh giới giữa mô hình độc lập nền tảng và mô hình gắn với một công nghệ triển khai bằng cách nào?
Một metamodel mô tả những khái niệm và quan hệ nào để các mô hình cụ thể có thể tuân thủ cùng một ngôn ngữ?
Bạn sẽ thiết kế metamodel cho quy trình phê duyệt với trạng thái, chuyển tiếp và vai trò người dùng như thế nào?
Bạn phân biệt metamodel với một mô hình được tạo ra theo metamodel đó qua ví dụ nào?
Khi định nghĩa DSL cho một lĩnh vực, bạn lựa chọn các khái niệm và thuật ngữ từ chuyên gia nghiệp vụ ra sao?
Bạn so sánh DSL dạng văn bản và dạng đồ họa về khả năng đọc, kiểm tra khác biệt và bảo trì như thế nào?
Bạn thiết kế cú pháp trừu tượng và cú pháp cụ thể của DSL để tránh trộn hình thức biểu diễn với ý nghĩa miền ra sao?
Nếu người dùng DSL có thể mô tả hai trạng thái trùng tên, bạn sẽ xác định ràng buộc hợp lệ ở lớp nào?
Bạn kiểm chứng tính đúng đắn về cấu trúc và ngữ nghĩa của mô hình bằng các quy tắc nào?
Khi một trạng thái không thể truy cập từ trạng thái bắt đầu, bạn sẽ phát hiện lỗi mô hình bằng cách nào?
Bạn lựa chọn ví dụ hợp lệ và phản ví dụ nào để kiểm thử bộ kiểm tra mô hình trước khi áp dụng cho nhóm phát triển?
Bạn phân biệt kiểm tra tĩnh trên mô hình với mô phỏng hành vi mô hình bằng những loại lỗi có thể phát hiện?
Khi hai quy tắc trong mô hình mâu thuẫn, bạn tổ chức trao đổi với chuyên gia để xác nhận ý định nghiệp vụ như thế nào?
Bạn xác định đầu vào, đầu ra và các quy tắc ánh xạ của một phép chuyển đổi mô hình sang mô hình khác ra sao?
Bạn mô tả quá trình chuyển một mô hình nghiệp vụ thành mô hình thiết kế chi tiết mà vẫn giữ các ràng buộc quan trọng như thế nào?
Khi phép chuyển đổi làm mất thông tin, bạn sẽ chỉ ra giới hạn và cách kiểm chứng thông tin bị mất ra sao?
Bạn phân biệt chuyển đổi model-to-model với model-to-text trong một chuỗi tạo mã như thế nào?
Bạn thiết kế quy tắc sinh interface, lớp và cấu hình từ mô hình để tên gọi và cấu trúc được nhất quán ra sao?
Khi mô hình thay đổi một tên thuộc tính, bạn xác định những tệp mã và hợp đồng cần sinh lại như thế nào?
Bạn tổ chức phần mã sinh tự động và phần mã viết tay để tránh ghi đè chỉnh sửa của lập trình viên ra sao?
Bạn sẽ lựa chọn extension point hoặc partial implementation để giữ logic tùy biến ngoài vùng mã được sinh như thế nào?
Nếu sinh mã nhiều lần từ cùng một mô hình, bạn kiểm chứng kết quả có tính xác định và tái lập bằng cách nào?
Bạn quản lý phiên bản của generator để hai nhóm dùng cùng mô hình không tạo ra kết quả khác biệt ra sao?
Khi cập nhật template sinh mã, bạn đánh giá phạm vi tác động lên các mô hình hiện có và cách kiểm thử hồi quy như thế nào?
Bạn xác định mô hình hay mã nguồn là nguồn sự thật khi cả hai đều có thể được chỉnh sửa bằng cách nào?
Trong trường hợp cần round-trip engineering, bạn xử lý những thay đổi thủ công trong mã mà mô hình chưa biểu diễn được ra sao?
Bạn đánh giá rủi ro của việc cố đồng bộ hai chiều giữa mô hình và code trong một dự án nhiều người tham gia như thế nào?
Bạn thiết kế cơ chế phát hiện mô hình và mã sinh đã lệch nhau trong quá trình review như thế nào?
Khi metamodel bổ sung một thuộc tính bắt buộc, bạn sẽ chuyển đổi các mô hình phiên bản cũ an toàn ra sao?
Bạn lựa chọn cách đánh số phiên bản và quy tắc tương thích của DSL để không làm hỏng mô hình đang sử dụng như thế nào?
Bạn lưu trữ và review mô hình trong quản lý phiên bản để người đọc nhận biết thay đổi ngữ nghĩa thay vì chỉ thay đổi định dạng ra sao?
Bạn kiểm soát tình trạng xung đột khi hai thành viên cùng sửa các thành phần liên quan trong một mô hình như thế nào?
Bạn sẽ tích hợp bước validate mô hình và sinh mã vào pipeline CI ở các điểm kiểm soát nào?
Khi bước sinh mã thất bại ở CI nhưng chạy được trên máy cá nhân, bạn kiểm tra dependency và môi trường thực thi như thế nào?
Bạn thiết kế kiểm thử cho mã được sinh để xác nhận hành vi đúng chứ không chỉ bảo đảm mã biên dịch thành công ra sao?
Bạn sử dụng truy vết giữa yêu cầu, phần tử mô hình, mã sinh và ca kiểm thử để phân tích ảnh hưởng thay đổi như thế nào?
Khi một tính năng vượt khả năng biểu đạt của DSL, bạn đánh giá mở rộng ngôn ngữ hay xử lý bằng mã viết tay ra sao?
Bạn phát hiện dấu hiệu một DSL quá tổng quát khiến chuyên gia nghiệp vụ khó đọc và khó xác minh bằng cách nào?
Bạn lựa chọn hạt nhân khái niệm tối thiểu cho metamodel nhằm giảm độ phức tạp nhưng vẫn hỗ trợ nhu cầu thực tế như thế nào?
Bạn sẽ xây dựng một thử nghiệm nhỏ để so sánh thời gian phát triển theo mô hình với lập trình trực tiếp ra sao?
Bạn đo chi phí tạo và bảo trì metamodel, DSL, generator và tài liệu hướng dẫn bằng những chỉ số nào?
Khi quy tắc nghiệp vụ thay đổi thường xuyên, bạn đánh giá MDD giúp giảm công sức hay chỉ chuyển chi phí sang sửa generator như thế nào?
Bạn xác định những loại lỗi do generator có thể lan rộng trên nhiều sản phẩm và xây dựng cơ chế phát hiện sớm ra sao?
Bạn thiết kế thông báo lỗi sinh mã ra sao để chỉ rõ phần tử mô hình không hợp lệ và cách khắc phục?
Khi chuyển một nhóm từ cách viết code trực tiếp sang Model-Driven Development, bạn chuẩn bị đào tạo và quy trình review nào?
Bạn quyết định có tiếp tục đầu tư tự động hóa từ mô hình dựa trên chất lượng, tốc độ thay đổi và chi phí sở hữu dài hạn ra sao?
