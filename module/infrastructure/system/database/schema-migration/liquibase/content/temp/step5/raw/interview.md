Liquibase giải quyết những vấn đề nào của việc thay đổi schema bằng các câu lệnh SQL chạy thủ công?
Bạn phân biệt trạng thái schema mong muốn với lịch sử changeset đã thực thi trong cơ chế quản lý migration như thế nào?
Changelog và changeset có vai trò khác nhau như thế nào trong một dự án Liquibase?
Bạn tổ chức cấu trúc thư mục và changelog gốc của ứng dụng để dễ mở rộng và kiểm soát thứ tự migration ra sao?
Những yếu tố nào xác định danh tính duy nhất của một changeset trong Liquibase?
Bạn lựa chọn cách đặt id và author cho changeset để nhóm phát triển dễ truy vết lịch sử như thế nào?
Bạn cân nhắc sử dụng XML, YAML, JSON hoặc formatted SQL changelog theo đặc điểm dự án như thế nào?
Bạn kiểm tra cú pháp và cấu trúc của một formatted SQL changelog để Liquibase nhận diện đúng changeset bằng cách nào?
Bạn phân biệt include và includeAll khi chia changelog thành nhiều file và kiểm soát thứ tự thực thi như thế nào?
Việc đổi đường dẫn file changelog hoặc dùng logicalFilePath ảnh hưởng thế nào đến nhận diện changeset đã chạy?
Bạn quyết định phạm vi một changeset khi cần tạo bảng, thêm khóa ngoại và tạo index liên quan như thế nào?
Bạn chọn change type khai báo sẵn hay câu lệnh SQL riêng theo mức độ tương thích và khả năng kiểm chứng ra sao?
Bạn mô hình hóa việc tạo bảng, thay đổi cột và thêm constraint trong Liquibase sao cho dễ review như thế nào?
Bạn xử lý khác biệt về kiểu dữ liệu giữa các hệ quản trị khi cùng một changelog chạy trên nhiều database như thế nào?
Bạn phân biệt thay đổi schema với seed data và dữ liệu nghiệp vụ cần backfill trong một đợt migration như thế nào?
Bạn tổ chức loadData hoặc loadUpdateData để nạp dữ liệu tham chiếu và kiểm tra chạy lặp lại an toàn ra sao?
Những tiêu chí nào khiến bạn tách các câu lệnh SQL phức tạp sang sqlFile thay vì viết trực tiếp trong changeset?
Bạn đánh giá rủi ro khi dùng custom change hoặc mã nguồn tùy biến trong một migration như thế nào?
Vì sao việc sửa trực tiếp changeset đã chạy trên môi trường dùng chung có thể gây sai lệch lịch sử và checksum?
Bạn đề xuất cách sửa lỗi nghiệp vụ của một migration đã được triển khai mà vẫn giữ lịch sử rõ ràng ra sao?
Checksum của changeset được Liquibase sử dụng để kiểm chứng điều gì?
Khi Liquibase báo checksum mismatch, bạn điều tra thay đổi nào trong repository và database trước khi xử lý?
Bạn chọn runOnChange cho những loại thay đổi nào và đánh giá tác động của việc chạy lại ra sao?
Bạn sử dụng runAlways trong tình huống nào và làm thế nào để việc chạy lại không gây tác dụng phụ ngoài ý muốn?
Bạn đánh giá khi nào validCheckSum phù hợp và khi nào nên tạo changeset mới để bảo đảm khả năng kiểm toán?
Bạn xử lý lệnh clearCheckSums theo quy trình kiểm chứng nào để không che khuất thay đổi lịch sử ngoài ý muốn?
Bạn mô tả mục đích của bảng DATABASECHANGELOG và những thông tin lịch sử có thể dùng để điều tra deployment như thế nào?
Bảng DATABASECHANGELOGLOCK được dùng để phối hợp thực thi migration đồng thời ra sao?
Bạn phân biệt một migration thực sự đang chạy với lock bị bỏ lại sau sự cố bằng những bằng chứng nào?
Bạn xử lý một lock chưa được giải phóng theo quy trình nào trước khi cân nhắc lệnh releaseLocks?
Bạn kiểm soát nguy cơ hai instance ứng dụng cùng kích hoạt Liquibase trong lúc scale-out như thế nào?
Bạn xác định thứ tự áp dụng các changeset mới khi nhiều nhóm cùng bổ sung file changelog như thế nào?
Bạn nhận diện các thay đổi có thể khiến migration không an toàn khi chạy lại hoặc khi bị gián đoạn giữa chừng ra sao?
Bạn đánh giá tính hỗ trợ transactional DDL của database đích trước khi thiết kế nhiều thao tác trong một changeset như thế nào?
Bạn cân nhắc thuộc tính runInTransaction khi database không hỗ trợ rollback DDL hoặc khi chạy thao tác đặc biệt như thế nào?
Precondition giúp kiểm soát điều kiện thực thi một changeset hoặc toàn bộ changelog như thế nào?
Bạn sử dụng tableExists, columnExists, dbms hoặc sqlCheck để kiểm tra tiền điều kiện trong các kịch bản nào?
Bạn kết hợp các điều kiện AND, OR và NOT trong precondition để biểu đạt quy tắc triển khai phức tạp như thế nào?
Bạn phân biệt onFail và onError trong precondition dựa trên nguyên nhân và cách xử lý migration như thế nào?
Bạn cân nhắc HALT, WARN, CONTINUE hoặc MARK_RAN cho một precondition không đạt dựa trên rủi ro nào?
Bạn phát hiện nguy cơ dùng MARK_RAN che giấu sự khác biệt schema giữa các môi trường như thế nào?
Bạn thiết kế precondition như thế nào để tránh bỏ qua việc cập nhật dữ liệu khi trạng thái chỉ đúng một phần?
Context và label trong Liquibase giúp chọn lọc changeset theo môi trường hoặc mục đích triển khai như thế nào?
Bạn đặt quy tắc sử dụng context và label như thế nào để migration bắt buộc không vô tình bị loại khỏi production?
Bạn quản lý giá trị changelog parameter khác nhau giữa môi trường phát triển, staging và production như thế nào?
Bạn sử dụng thuộc tính dbms để xử lý các đoạn migration dành riêng cho từng hệ quản trị ra sao?
Bạn phân biệt lệnh validate, status và history của Liquibase khi kiểm tra trước và sau deployment như thế nào?
Bạn dùng updateSQL để review SQL dự kiến được sinh ra trước khi chạy migration thật như thế nào?
Bạn kiểm chứng một changelog mới có thể chạy từ database trống và từ schema phiên bản trước bằng cách nào?
Bạn sử dụng snapshot và diff để tìm khác biệt schema nhưng vẫn tránh tự động áp dụng thay đổi ngoài ý muốn ra sao?
Bạn đánh giá kết quả generateChangeLog trước khi tạo baseline cho một database hiện hữu như thế nào?
Bạn xây dựng quy trình baseline khi database đã có bảng và dữ liệu nhưng chưa được quản lý bằng Liquibase như thế nào?
Bạn phát hiện schema drift do thay đổi thủ công ngoài Liquibase và lựa chọn cách hòa giải như thế nào?
Bạn phân biệt migration có rollback tự sinh được với migration cần viết rollback tường minh như thế nào?
Bạn viết và kiểm thử rollback của một changeset có SQL tùy chỉnh theo tiêu chí nào?
Bạn sử dụng tag và các cơ chế rollback theo tag, số lượng changeset hoặc thời điểm theo những tình huống nào?
Bạn dùng rollbackSQL để review tác động của phương án quay lui trước khi thực thi như thế nào?
Bạn đánh giá khả năng phục hồi dữ liệu khi một changeset đã xóa cột, xóa bảng hoặc ghi đè dữ liệu như thế nào?
Bạn kết hợp backup, restore và rollback của Liquibase để xử lý migration phá hủy dữ liệu ra sao?
Bạn phân biệt rollback schema với việc khôi phục dữ liệu nghiệp vụ đã thay đổi sau deployment như thế nào?
Bạn thiết kế thay đổi từ cột nullable sang NOT NULL cho bảng đang có dữ liệu như thế nào?
Bạn thêm unique constraint hoặc foreign key cho bảng lớn mà vẫn kiểm tra được dữ liệu vi phạm trước khi áp dụng ra sao?
Bạn đánh giá chiến lược tạo index trên bảng lớn để giảm thời gian khóa ghi và ảnh hưởng production như thế nào?
Bạn thực hiện đổi tên cột hoặc tách bảng trong lúc vẫn phải hỗ trợ các phiên bản ứng dụng đang chạy như thế nào?
Bạn áp dụng chiến lược expand-and-contract để thay đổi schema mà tránh gián đoạn dịch vụ ra sao?
Bạn thiết kế quy trình backfill theo lô để hạn chế transaction dài và áp lực I/O như thế nào?
Bạn kiểm tra tính đầy đủ và đúng đắn của dữ liệu sau một đợt backfill trước khi xóa schema cũ như thế nào?
Bạn lựa chọn thứ tự phát hành ứng dụng và database khi một tính năng yêu cầu đồng thời đổi schema và logic xử lý như thế nào?
Bạn xử lý tình huống ứng dụng cũ và ứng dụng mới cùng ghi dữ liệu trong giai đoạn rolling deployment ra sao?
Những yêu cầu phân quyền và kiểm toán nào khiến bạn triển khai migration bằng tài khoản database riêng với tài khoản ứng dụng?
Bạn cấu hình Liquibase với Spring Boot để tìm changelog và kết nối đúng DataSource như thế nào?
Bạn kiểm soát việc Spring Boot tự chạy Liquibase lúc khởi động trong hệ thống có nhiều instance như thế nào?
Bạn xử lý trường hợp migration thất bại khiến Spring Boot không khởi động được theo quy trình khôi phục nào?
Bạn tổ chức các cấu hình Liquibase cho nhiều DataSource hoặc nhiều schema trong cùng ứng dụng như thế nào?
Bạn tích hợp việc kiểm tra changelog và chạy migration trong pipeline CI/CD theo những bước kiểm soát nào?
Bạn xây dựng kiểm thử migration trên database tạm thời hoặc container để phát hiện lỗi trước khi merge như thế nào?
Bạn xác minh khả năng rollback trong CI bằng những kiểm thử nào ngoài việc kiểm tra câu lệnh chạy thành công?
Bạn quản lý thông tin kết nối, mật khẩu và quyền triển khai trong CI/CD để hạn chế lộ bí mật như thế nào?
Bạn tổ chức cơ chế phê duyệt hoặc chặn pipeline khi phát hiện SQL có nguy cơ khóa bảng hoặc xóa dữ liệu như thế nào?
Bạn kiểm soát xung đột khi hai nhánh tính năng cùng chỉnh changelog và được merge theo thứ tự khác nhau ra sao?
Bạn đối chiếu các changeset đã chạy giữa staging và production trước khi phát hành để tránh lệch lịch sử như thế nào?
Bạn giám sát thời gian chạy, log, số changeset và lỗi phát sinh để đánh giá chất lượng một đợt migration ra sao?
Khi migration đang chạy lâu hơn dự kiến và giữ khóa bảng, bạn điều tra từ database và Liquibase theo trình tự nào?
Bạn xử lý tình huống changeset đã thay đổi một phần dữ liệu nhưng pipeline báo lỗi giữa chừng như thế nào?
Bạn đánh giá khi nào nên tiếp tục bằng migration sửa lỗi thay vì chạy rollback trong một sự cố production?
Bạn xây dựng tiêu chí hoàn thành deployment gồm kiểm tra schema, dữ liệu, checksum và sức khỏe ứng dụng như thế nào?
Bạn lập kế hoạch diễn tập triển khai và phục hồi cho một thay đổi Liquibase quan trọng trước ngày phát hành ra sao?
