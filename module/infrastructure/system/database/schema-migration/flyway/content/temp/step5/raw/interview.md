Bạn sẽ giải thích schema migration là gì và vì sao ứng dụng cần quản lý thay đổi cơ sở dữ liệu theo phiên bản?
Bạn sẽ phân biệt việc thay đổi schema bằng tay với việc lưu migration trong hệ thống kiểm soát phiên bản như thế nào?
Flyway tham gia vào vòng đời phát triển, kiểm thử và triển khai ứng dụng tại những thời điểm nào?
Bạn sẽ mô tả mối quan hệ giữa mã nguồn ứng dụng, tập tin migration và trạng thái schema trên cơ sở dữ liệu như thế nào?
Bạn sẽ xác định khi nào nên tạo migration mới thay vì sửa trực tiếp một migration đã phát hành ra sao?
Bạn sẽ giải thích đặc điểm của versioned migration và repeatable migration bằng một ví dụ thay đổi hệ thống như thế nào?
Bạn sẽ phân biệt thao tác migrate, info, validate và baseline về mục đích và thời điểm sử dụng ra sao?
Bạn sẽ tổ chức thư mục migration trong repository để các thành viên tìm đúng lịch sử thay đổi như thế nào?
Bạn sẽ chọn quy ước đặt tên versioned migration để thể hiện phiên bản và mục đích thay đổi ra sao?
Bạn sẽ phân tích ý nghĩa của dấu phân cách và phần mô tả trong tên một tập tin migration SQL như thế nào?
Bạn sẽ thiết kế chuỗi migration ban đầu để tạo bảng, khóa chính, khóa ngoại và index cho một dịch vụ mới ra sao?
Bạn sẽ quyết định tách hay gộp các thay đổi schema trong một migration dựa trên những tiêu chí nào?
Bạn sẽ ghi chú lý do nghiệp vụ của một migration để người bảo trì hiểu quyết định thiết kế như thế nào?
Bạn sẽ lựa chọn migration SQL hay Java dựa trên loại thay đổi và khả năng kiểm thử như thế nào?
Bạn sẽ đánh giá ưu điểm và hạn chế của việc dùng SQL riêng cho từng hệ quản trị cơ sở dữ liệu trong Flyway ra sao?
Bạn sẽ thiết kế migration có thể chạy ổn định trên các môi trường phát triển, kiểm thử và sản xuất như thế nào?
Bạn sẽ kiểm tra sự tương thích của cú pháp SQL trong migration với phiên bản và dialect cơ sở dữ liệu ra sao?
Bạn sẽ kiểm soát những đối tượng cần tạo trước như schema, bảng và sequence để tránh lỗi phụ thuộc như thế nào?
Bạn sẽ xử lý thứ tự tạo bảng có quan hệ khóa ngoại vòng hoặc nhiều mức phụ thuộc như thế nào?
Bạn sẽ lập kế hoạch thay đổi kiểu dữ liệu của cột đang chứa dữ liệu thực tế mà không làm hỏng giá trị cũ ra sao?
Bạn sẽ thêm ràng buộc NOT NULL vào cột đang có bản ghi thiếu dữ liệu theo những bước nào?
Bạn sẽ thực hiện đổi tên cột được nhiều phiên bản ứng dụng sử dụng mà vẫn duy trì khả năng tương thích như thế nào?
Bạn sẽ phân biệt thay đổi schema và migration dữ liệu khi thiết kế quá trình nâng cấp cơ sở dữ liệu ra sao?
Bạn sẽ xây dựng migration dữ liệu có thể kiểm chứng số bản ghi, tính toàn vẹn và kết quả chuyển đổi như thế nào?
Bạn sẽ kiểm soát giao dịch và khối lượng cập nhật khi một migration cần xử lý hàng triệu dòng dữ liệu ra sao?
Bạn sẽ giải thích cách Flyway xác định thứ tự áp dụng các versioned migration như thế nào?
Khi có các phiên bản migration như V1, V2 và V10, bạn sẽ kiểm tra thứ tự thực thi và quy ước đánh số ra sao?
Bạn sẽ tổ chức phiên bản migration khi nhiều nhóm phát triển đồng thời cùng một sản phẩm như thế nào?
Khi hai nhánh Git cùng tạo migration mang một số phiên bản, bạn sẽ xử lý xung đột trước khi merge ra sao?
Bạn sẽ giải quyết tình huống một migration có phiên bản thấp hơn đã được thêm vào sau khi môi trường khác nâng cấp như thế nào?
Bạn sẽ cân nhắc việc cho phép out-of-order migration dựa trên những rủi ro về thứ tự phụ thuộc nào?
Bạn sẽ thiết kế repeatable migration cho một view được định nghĩa lại nhiều lần như thế nào?
Những loại đối tượng cơ sở dữ liệu nào phù hợp với repeatable migration hơn versioned migration?
Bạn sẽ giải thích Flyway nhận biết một repeatable migration cần chạy lại dựa trên nội dung và checksum như thế nào?
Bạn sẽ xử lý repeatable migration có phụ thuộc vào bảng hoặc function được tạo bởi versioned migration như thế nào?
Bạn sẽ sắp xếp và đặt tên repeatable migration có quan hệ phụ thuộc để tránh thứ tự thực thi không mong muốn ra sao?
Bạn sẽ viết repeatable migration để tạo hoặc thay thế view hay routine mà không thất bại vì đối tượng đã tồn tại như thế nào?
Bạn sẽ đánh giá tác động của việc sửa một tập tin repeatable migration đối với lần triển khai tiếp theo ra sao?
Bạn sẽ tránh việc một repeatable migration thay đổi dữ liệu theo cách không thể chạy lại an toàn như thế nào?
Bạn sẽ sử dụng placeholder khi nội dung repeatable migration cần được làm mới theo chính sách triển khai như thế nào?
Bạn sẽ quản lý giá trị placeholder cho môi trường khác nhau mà không đưa bí mật vào tập tin SQL ra sao?
Bạn sẽ kiểm chứng repeatable migration tạo ra kết quả mong đợi sau nhiều lần cập nhật định nghĩa đối tượng như thế nào?
Bạn sẽ giải thích vai trò của bảng schema history trong việc ghi lại các migration đã được Flyway áp dụng như thế nào?
Bạn sẽ tìm những thông tin nào trong schema history khi cần điều tra một lần migrate thất bại?
Bạn sẽ phân biệt phiên bản migration có trong repository với các bản ghi đã tồn tại trong schema history ra sao?
Bạn sẽ giải thích ý nghĩa của trạng thái migration thành công, thất bại, còn chờ và bị thiếu như thế nào?
Bạn sẽ sử dụng kết quả của Flyway info để đối chiếu lịch sử triển khai giữa hai môi trường ra sao?
Checksum giúp phát hiện những thay đổi nào đối với tập tin migration đã chạy, và bạn sẽ kiểm tra kết quả cảnh báo ra sao?
Khi validate báo checksum mismatch, bạn sẽ xác minh khác biệt mã nguồn và lịch sử triển khai theo trình tự nào?
Bạn sẽ quyết định khôi phục nội dung migration cũ hay tạo migration mới khi phát hiện thay đổi trái quy ước ra sao?
Bạn sẽ đánh giá rủi ro của việc thay đổi checksum trong schema history mà chưa xác minh schema thực tế như thế nào?
Bạn sẽ dùng validate như một điều kiện chặn trong pipeline trước khi thực thi migration ra sao?
Khi validate phát hiện migration thiếu hoặc khác biệt so với lịch sử, bạn sẽ xử lý mà vẫn giữ được tính kiểm toán như thế nào?
Bạn sẽ phân biệt trường hợp validate thất bại do thay đổi tập tin với trường hợp cơ sở dữ liệu đã bị chỉnh sửa trực tiếp như thế nào?
Bạn sẽ xác định baseline có ý nghĩa gì khi đưa một cơ sở dữ liệu đang tồn tại vào quản lý bằng Flyway?
Bạn sẽ chọn baseline version và cách kiểm kê schema hiện tại trước khi thiết lập baseline như thế nào?
Bạn sẽ phân biệt baseline với thao tác tạo schema mới từ các migration đầu tiên ra sao?
Bạn sẽ đánh giá các điều kiện cần kiểm tra trước khi sử dụng baselineOnMigrate trong một môi trường sản xuất như thế nào?
Bạn sẽ xử lý tình huống cơ sở dữ liệu đã có nhiều bảng nhưng schema history chưa tồn tại theo những bước nào?
Bạn sẽ đối chiếu một môi trường đã baseline với môi trường tạo từ đầu để phát hiện khác biệt schema như thế nào?
Bạn sẽ giải thích mục đích của Flyway repair và giới hạn của thao tác này trong việc sửa dữ liệu hay đối tượng database ra sao?
Bạn sẽ quyết định khi nào việc repair là hợp lý sau một migration thất bại và cần kiểm tra bằng chứng nào trước đó?
Bạn sẽ kiểm chứng đối tượng cơ sở dữ liệu vẫn nhất quán sau khi một migration thất bại giữa chừng như thế nào?
Bạn sẽ phân tích hành vi rollback của DDL khác nhau giữa các hệ quản trị và tác động đến migration ra sao?
Bạn sẽ xác định điều kiện để một migration chạy trong transaction và cách kiểm thử trên hệ quản trị đang dùng như thế nào?
Bạn sẽ thiết kế quy trình phục hồi khi migration tạo bảng thành công nhưng bước thay đổi dữ liệu sau đó thất bại ra sao?
Bạn sẽ phân biệt schema history ghi nhận sự cố với trạng thái thực tế của schema khi điều tra lỗi như thế nào?
Bạn sẽ thiết kế script sửa tiếp sau sự cố mà không dựa vào giả định mọi thao tác trước đó đã được rollback như thế nào?
Bạn sẽ đánh giá rủi ro và biện pháp bảo vệ khi ai đó yêu cầu dùng lệnh clean trên một database dùng chung như thế nào?
Bạn sẽ phân biệt vai trò của undo migration, migration tiến về phía trước và khôi phục từ backup trong các chiến lược phục hồi như thế nào?
Bạn sẽ lập kế hoạch rollback ứng dụng khi schema mới vẫn phải tương thích với phiên bản ứng dụng cũ như thế nào?
Bạn sẽ áp dụng mô hình expand-and-contract để chia một thay đổi cột hoặc bảng thành nhiều đợt triển khai ra sao?
Bạn sẽ kiểm tra các truy vấn đang sử dụng cột cũ trước khi xóa cột đó khỏi schema như thế nào?
Bạn sẽ tách bước bổ sung schema, backfill dữ liệu và bật chức năng ứng dụng mới để giảm rủi ro như thế nào?
Bạn sẽ lựa chọn thời điểm tạo unique constraint trên bảng lớn sau khi làm sạch dữ liệu trùng như thế nào?
Bạn sẽ giảm thời gian khóa bảng khi thêm cột, tạo index hoặc thay đổi constraint trên database đang có tải ra sao?
Bạn sẽ chuẩn bị kế hoạch sao lưu và điểm khôi phục trước một migration có thao tác xóa hoặc biến đổi dữ liệu như thế nào?
Bạn sẽ xác định chỉ số nào để đánh giá migration có thể hoàn thành trong cửa sổ triển khai cho phép?
Bạn sẽ thiết lập cấu hình Flyway trong Spring Boot để ứng dụng dùng đúng DataSource và schema mục tiêu như thế nào?
Bạn sẽ tổ chức vị trí tập tin migration trong dự án Spring Boot để ứng dụng và công cụ build cùng tìm được như thế nào?
Bạn sẽ kiểm soát việc Spring Boot tự chạy Flyway khi startup theo yêu cầu từng môi trường ra sao?
Bạn sẽ giải thích trình tự khởi chạy Flyway với JPA hoặc Hibernate và hệ quả của việc nhiều cơ chế cùng thay đổi schema như thế nào?
Bạn sẽ xác minh cấu hình migration của ứng dụng Java trỏ đúng database và schema mục tiêu trong từng môi trường như thế nào?
Bạn sẽ tách quyền tài khoản dùng để thực hiện migration khỏi quyền tài khoản chạy ứng dụng hằng ngày như thế nào?
Bạn sẽ bảo vệ URL kết nối, mật khẩu và thông tin nhạy cảm khi chạy Flyway từ Spring Boot hay CI/CD ra sao?
Bạn sẽ tích hợp việc chạy Flyway vào kiểm thử tích hợp dùng database tạm thời để xác nhận schema được tạo từ đầu như thế nào?
Bạn sẽ viết một bài kiểm thử xác minh constraint, index và dữ liệu mẫu sau khi thực thi toàn bộ migration như thế nào?
Bạn sẽ kiểm tra tính tương thích giữa schema sau migrate và entity hoặc truy vấn Spring Data JPA ra sao?
Bạn sẽ xác định ứng dụng nên chạy migration lúc khởi động hay giao cho một job triển khai độc lập theo tiêu chí nào?
Bạn sẽ xử lý trường hợp nhiều instance Spring Boot cùng khởi động và cùng yêu cầu migrate một cơ sở dữ liệu như thế nào?
Bạn sẽ quan sát và ghi log kết quả migrate trong Spring Boot để tìm nguyên nhân startup thất bại ra sao?
Bạn sẽ thiết kế pipeline CI chạy validate và migrate trên database kiểm thử trước khi chấp nhận thay đổi mã nguồn như thế nào?
Bạn sẽ xác minh một nhánh tính năng không chứa migration xung đột với các nhánh đã merge bằng những kiểm tra nào?
Bạn sẽ đưa Flyway vào quy trình phát hành ứng dụng để schema được nâng cấp đúng thời điểm và đúng phiên bản như thế nào?
Bạn sẽ quản lý cấu hình Flyway riêng cho môi trường development, staging và production mà vẫn dùng cùng tập tin migration như thế nào?
Bạn sẽ đặt cổng kiểm soát hoặc phê duyệt nào trước khi pipeline áp dụng migration có rủi ro làm mất dữ liệu?
Bạn sẽ giới hạn số tiến trình có quyền thực hiện migration đồng thời trong một quy trình triển khai nhiều service ra sao?
Bạn sẽ tổ chức release khi hai dịch vụ dùng chung một schema nhưng có lịch triển khai khác nhau như thế nào?
Bạn sẽ ghi nhận phiên bản ứng dụng, phiên bản migration và thời điểm triển khai để phục vụ điều tra sự cố như thế nào?
Bạn sẽ thiết kế bước dry-run hoặc rà soát SQL trước sản xuất tùy theo khả năng của công cụ và quy trình vận hành ra sao?
Bạn sẽ xác định những dấu hiệu nào khiến pipeline cần dừng trước khi tác động đến cơ sở dữ liệu thật?
Bạn sẽ thiết kế cảnh báo khi migrate kéo dài bất thường, bị kẹt khóa hoặc gặp lỗi quyền truy cập như thế nào?
Bạn sẽ xử lý tình huống pipeline deploy bị hủy sau khi Flyway đã cập nhật một phần schema ra sao?
Bạn sẽ kiểm tra xung đột giữa migration thủ công và migration do pipeline thực thi như thế nào?
Bạn sẽ xử lý yêu cầu chạy một thay đổi dữ liệu chỉ một lần trên production nhưng có thể thử nhiều lần trên staging ra sao?
Bạn sẽ thiết kế migration nạp dữ liệu tham chiếu để tránh ghi đè những thay đổi hợp lệ đã phát sinh trong vận hành như thế nào?
Bạn sẽ kiểm tra và giới hạn tác động của một câu UPDATE hoặc DELETE trong migration trước khi chạy trên tập dữ liệu lớn ra sao?
Bạn sẽ dùng chiến lược chia lô hay tiến trình backfill riêng khi migration dữ liệu quá lớn cho một lần triển khai như thế nào?
Bạn sẽ xác định cách khôi phục dữ liệu khi mapping mới làm mất thông tin hoặc biến đổi sai hàng loạt bản ghi như thế nào?
Bạn sẽ phân tích nguyên nhân một migration chạy nhanh ở staging nhưng chậm ở production dựa trên số liệu và điều kiện nào?
Bạn sẽ thiết kế tiêu chí thành công, phép đo dữ liệu trước và sau, và thủ tục bàn giao cho một migration quan trọng như thế nào?
Khi môi trường production bị chỉnh sửa schema ngoài Flyway, bạn sẽ điều tra drift và đưa hệ thống trở lại trạng thái được quản lý ra sao?
Bạn sẽ xây dựng checklist kiểm tra sau deploy để xác nhận ứng dụng, schema và dữ liệu cùng ở trạng thái tương thích như thế nào?
