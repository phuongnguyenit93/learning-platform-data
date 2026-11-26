Bạn giải thích vì sao thay đổi lược đồ cơ sở dữ liệu cần được quản lý bằng migration có phiên bản như thế nào?
Bạn phân biệt migration có kiểm soát với chỉnh sửa schema thủ công trực tiếp trên từng môi trường ra sao?
Bạn xác định các yêu cầu nghiệp vụ và kỹ thuật cần có trước khi đề xuất một migration như thế nào?
Bạn phân biệt thay đổi cấu trúc, thay đổi dữ liệu và thay đổi dữ liệu tham chiếu trong kế hoạch migration ra sao?
Bạn đánh giá mức độ rủi ro của một thay đổi schema từ quy mô dữ liệu và các ứng dụng phụ thuộc như thế nào?
Bạn tổ chức lịch sử thay đổi schema để người mới có thể tái tạo một database từ đầu ra sao?
Bạn thiết kế quy ước đặt tên và đánh số migration để dễ theo dõi khi nhiều người cùng phát triển như thế nào?
Bạn xác định một migration nên chứa bao nhiêu thay đổi để vừa dễ review vừa dễ xử lý lỗi ra sao?
Bạn quyết định khi nào cần tách một thay đổi lớn thành nhiều migration liên tiếp như thế nào?
Bạn liên kết migration với mã nguồn ứng dụng và phiên bản phát hành theo cách nào?
Bạn xác định schema nào là nguồn sự thật khi cấu trúc giữa development, staging và production khác nhau ra sao?
Bạn kiểm chứng một môi trường có đúng phiên bản schema mà ứng dụng yêu cầu bằng cách nào?
Bạn phát hiện schema drift do thao tác thủ công hoặc script ngoài quy trình như thế nào?
Bạn xử lý trường hợp một nhóm đã thay đổi schema trên production nhưng chưa bổ sung migration vào repository ra sao?
Bạn thiết kế quy trình kiểm duyệt migration khi nhiều nhóm cùng sở hữu một database như thế nào?
Bạn kiểm soát thứ tự áp dụng migration trong các nhánh phát triển được hợp nhất không theo thứ tự ra sao?
Bạn xử lý hai migration phát triển độc lập cùng thay đổi một bảng trước khi merge như thế nào?
Bạn đánh giá tác động của việc chỉnh sửa một migration đã chạy ở production như thế nào?
Bạn tổ chức migration riêng cho từng service trong kiến trúc microservices dùng chung hạ tầng database ra sao?
Bạn quản lý migration trong hệ thống có nhiều schema hoặc nhiều database phụ thuộc lẫn nhau như thế nào?
Bạn chọn thay đổi tương thích ngược hay yêu cầu nâng cấp đồng thời ứng dụng và database dựa trên tiêu chí nào?
Bạn định nghĩa khả năng tương thích giữa phiên bản ứng dụng cũ, mới và schema chuyển tiếp như thế nào?
Bạn giải thích chiến lược expand–migrate–contract bằng ví dụ đổi cấu trúc dữ liệu ra sao?
Bạn bổ sung cột mới mà vẫn cho phép các phiên bản ứng dụng cũ tiếp tục ghi dữ liệu như thế nào?
Bạn thiết kế bước chuyển dữ liệu từ cột cũ sang cột mới khi ứng dụng còn đang hoạt động ra sao?
Bạn xác định thời điểm an toàn để ngừng đọc hoặc ghi vào cột cũ như thế nào?
Bạn quyết định lúc nào có thể xóa một cột đã ngừng sử dụng từ ứng dụng ra sao?
Bạn xử lý việc đổi tên cột mà không làm hỏng những bản ứng dụng chưa được cập nhật như thế nào?
Bạn thiết kế thay đổi tên bảng khi nhiều dịch vụ vẫn sử dụng tên cũ ra sao?
Bạn chuyển một trường dạng chuỗi sang kiểu số mà vẫn xử lý được dữ liệu không hợp lệ như thế nào?
Bạn thay đổi độ dài cột mà không làm mất dữ liệu hoặc gây lỗi ghi ngoài ý muốn ra sao?
Bạn đưa một cột từ cho phép NULL sang NOT NULL theo các bước an toàn như thế nào?
Bạn thêm giá trị mặc định cho cột mới mà vẫn kiểm soát tác động tới dữ liệu hiện có ra sao?
Bạn thiết kế bổ sung ràng buộc UNIQUE khi dữ liệu đang có bản ghi trùng như thế nào?
Bạn xác định cách xử lý dữ liệu vi phạm CHECK hoặc khóa ngoại trước khi bật ràng buộc ra sao?
Bạn chuyển khóa chính tự nhiên sang khóa thay thế trong một hệ thống đang có nhiều bảng tham chiếu như thế nào?
Bạn lên kế hoạch thay đổi khóa ngoại khi quan hệ nghiệp vụ giữa các bảng được tổ chức lại ra sao?
Bạn quyết định nên dùng view hoặc lớp tương thích tạm thời trong quá trình chuyển schema như thế nào?
Bạn quản lý sự khác biệt giữa ứng dụng đọc từ cấu trúc cũ và ứng dụng đọc từ cấu trúc mới ra sao?
Bạn kiểm thử chiến lược dual write khi hai trường hoặc hai bảng phải cùng được cập nhật như thế nào?
Bạn phát hiện và sửa chênh lệch dữ liệu do dual write thất bại ở một nhánh ra sao?
Bạn dùng feature flag hoặc cơ chế chuyển tuyến để giảm rủi ro khi đổi đường đọc dữ liệu như thế nào?
Bạn xác định thời điểm bật ràng buộc mới mà không làm lỗi giao dịch của ứng dụng cũ ra sao?
Bạn đánh giá thay đổi nào có thể triển khai không downtime và thay đổi nào cần cửa sổ bảo trì như thế nào?
Bạn lập kế hoạch triển khai nhiều bước khi hệ thống dùng rolling deployment hoặc blue–green deployment ra sao?
Bạn xác định trình tự triển khai schema, dữ liệu và ứng dụng để tránh khoảng thời gian không tương thích như thế nào?
Bạn kiểm chứng phương án ứng dụng rollback về phiên bản trước có còn chạy được với schema mới ra sao?
Bạn thiết kế thay đổi schema cho nhiều vùng triển khai có lịch nâng cấp khác nhau như thế nào?
Bạn kiểm soát việc giữ lại cấu trúc cũ quá lâu sau khi ứng dụng đã chuyển sang cấu trúc mới ra sao?
Bạn đặt tiêu chí quyết định kết thúc giai đoạn chuyển tiếp và thực hiện bước contract như thế nào?
Bạn phân biệt data migration với backfill dữ liệu đã tồn tại theo những điều kiện nào?
Bạn chọn thực hiện chuyển đổi dữ liệu trong migration hay bằng một công việc chạy riêng dựa trên yếu tố nào?
Bạn thiết kế backfill cho bảng có hàng trăm triệu bản ghi mà không khóa hệ thống quá lâu ra sao?
Bạn xác định kích thước batch, tần suất chạy và giới hạn tài nguyên cho backfill như thế nào?
Bạn thiết kế công việc backfill có thể tiếp tục sau khi tiến trình bị dừng giữa chừng ra sao?
Bạn bảo đảm backfill chạy lại không tạo bản ghi trùng hoặc ghi đè dữ liệu mới hơn như thế nào?
Bạn xử lý các bản ghi được ứng dụng cập nhật đồng thời trong lúc backfill như thế nào?
Bạn xác định cách theo dõi tiến độ backfill và ước lượng phần công việc còn lại ra sao?
Bạn lựa chọn khóa phân trang hoặc điều kiện truy cập để quét dữ liệu ổn định khi backfill như thế nào?
Bạn xử lý bản ghi lỗi riêng lẻ trong một batch mà không làm dừng toàn bộ quá trình như thế nào?
Bạn lưu dấu các bản ghi không chuyển đổi được để kiểm tra và xử lý sau như thế nào?
Bạn xác định cách kiểm tra tính đầy đủ và chính xác của dữ liệu sau chuyển đổi ra sao?
Bạn đối chiếu số lượng bản ghi, tổng kiểm tra và ràng buộc nghiệp vụ giữa dữ liệu cũ và mới như thế nào?
Bạn thiết kế kiểm tra mẫu và kiểm tra toàn bộ dữ liệu khi xác minh migration theo những tiêu chí nào?
Bạn tránh việc kiểm tra dữ liệu sau migration gây quá tải database sản xuất như thế nào?
Bạn bảo vệ khả năng truy vết khi một phép chuyển đổi dữ liệu làm mất thông tin ban đầu ra sao?
Bạn xác định khi nào nên giữ bản sao dữ liệu gốc để phục hồi một bước chuyển đổi không thể đảo ngược như thế nào?
Bạn xử lý dữ liệu nguồn không tuân thủ giả định nghiệp vụ của migration ra sao?
Bạn lập kế hoạch chuyển đổi từ một bảng lớn thành nhiều bảng có quan hệ như thế nào?
Bạn chuyển dữ liệu từ nhiều bảng sang một bảng mới mà không làm mất lịch sử quan hệ ra sao?
Bạn kiểm soát thứ tự cập nhật các bảng có khóa ngoại phụ thuộc lẫn nhau như thế nào?
Bạn đánh giá nguy cơ đếm trùng hoặc bỏ sót dữ liệu khi migration diễn ra đồng thời với luồng sự kiện như thế nào?
Bạn kiểm tra ảnh hưởng của timezone, encoding và precision tới dữ liệu sau chuyển kiểu như thế nào?
Bạn xử lý giá trị mặc định và trường NULL để không làm thay đổi ý nghĩa nghiệp vụ trong quá trình chuyển đổi ra sao?
Bạn thiết kế quy trình hòa giải dữ liệu sau migration nếu có chênh lệch so với nguồn như thế nào?
Bạn giải thích vai trò transaction khi thực hiện DDL và data migration như thế nào?
Bạn xác định những lệnh DDL nào hỗ trợ transaction ở engine được sử dụng bằng cách nào?
Bạn đánh giá rủi ro khi công cụ migration mặc định chạy nhiều lệnh trong một transaction ra sao?
Bạn xác định lệnh thay đổi schema nào có thể giữ khóa lâu trên bảng đang được ghi liên tục như thế nào?
Bạn đo hoặc ước lượng thời gian khóa của một migration trước khi triển khai production ra sao?
Bạn lựa chọn chiến lược thêm index trên bảng lớn để giảm thời gian chặn giao dịch như thế nào?
Bạn đánh giá ảnh hưởng của việc tạo index lên CPU, I/O và tốc độ ghi trong giờ cao điểm ra sao?
Bạn xác định lúc nào nên tạo index trước và lúc nào nên áp dụng ràng buộc sau như thế nào?
Bạn thiết kế ngưỡng lock timeout và statement timeout phù hợp cho migration như thế nào?
Bạn xử lý migration bị chờ khóa bởi một giao dịch dài mà không làm gián đoạn toàn hệ thống ra sao?
Bạn phát hiện và xử lý deadlock phát sinh giữa migration với giao dịch ứng dụng như thế nào?
Bạn chọn khoảng thời gian triển khai dựa trên lưu lượng, kích thước bảng và khả năng phục hồi ra sao?
Bạn kiểm soát số lượng migration hoặc backfill được phép chạy đồng thời trên cùng database như thế nào?
Bạn xác định ảnh hưởng của replication lag trong khi migration thay đổi nhiều dữ liệu ra sao?
Bạn kiểm tra khả năng đọc trên replica sau khi primary áp dụng migration như thế nào?
Bạn đánh giá rủi ro khi một thay đổi schema gây tăng kích thước transaction log ra sao?
Bạn thiết kế điểm dừng an toàn cho một migration dài khi có tín hiệu suy giảm dịch vụ như thế nào?
Bạn quyết định giữa công cụ schema migration và các kỹ thuật thay bảng trực tuyến theo điều kiện nào?
Bạn giải thích khác biệt giữa rollback schema và rollback dữ liệu sau khi ứng dụng đã ghi theo định dạng mới ra sao?
Bạn phân loại migration có thể đảo ngược và migration chỉ nên sửa tiến bằng những tiêu chí nào?
Bạn thiết kế migration đảo ngược cho thao tác thêm bảng hoặc thêm cột mà không gây mất dữ liệu ra sao?
Bạn xử lý rollback khi một cột cũ đã bị xóa và dữ liệu mới không còn đủ để tái tạo nó như thế nào?
Bạn lập kế hoạch forward fix khi rollback sẽ gây rủi ro lớn hơn so với sửa lỗi tại chỗ ra sao?
Bạn xác định dữ liệu nào sẽ bị ảnh hưởng nếu chạy script rollback sau một khoảng thời gian ứng dụng đã hoạt động ra sao?
Bạn lập kịch bản khôi phục database từ backup khi migration làm hỏng dữ liệu như thế nào?
Bạn xác định cách phối hợp point-in-time recovery với các giao dịch hợp lệ phát sinh sau migration ra sao?
Bạn lựa chọn giữa khôi phục một phần dữ liệu và khôi phục toàn bộ database dựa trên tiêu chí nào?
Bạn kiểm chứng tính sẵn sàng của backup và tài nguyên restore ngay trước khi chạy migration rủi ro cao ra sao?
Bạn định nghĩa điều kiện dừng triển khai và quyết định rollback dựa trên số liệu vận hành như thế nào?
Bạn thiết kế quy trình xử lý migration thất bại sau khi một phần DDL đã được commit như thế nào?
Bạn xác định thay đổi nào đã được áp dụng thực tế khi trạng thái công cụ migration báo lỗi ra sao?
Bạn tránh chạy lại thao tác phá hủy trong lúc phục hồi từ một migration chưa hoàn tất như thế nào?
Bạn lưu hồ sơ thao tác sửa chữa thủ công để sau đó lịch sử migration vẫn đáng tin cậy như thế nào?
Bạn phân tích nguyên nhân một migration thành công ở staging nhưng thất bại tại production như thế nào?
Bạn thiết kế migration script có thể được review độc lập trước khi thực thi ra sao?
Bạn lựa chọn Flyway hay Liquibase dựa trên mô hình phát triển, loại database và quy trình release như thế nào?
Bạn mô tả cơ chế theo dõi migration đã áp dụng của Flyway trong một dự án như thế nào?
Bạn tổ chức versioned migration và repeatable migration của Flyway cho những loại thay đổi nào?
Bạn đặt quy ước tên script Flyway để người review nhận biết thứ tự và mục đích ra sao?
Bạn xử lý sự thay đổi checksum khi nội dung một migration Flyway đã chạy bị chỉnh sửa như thế nào?
Bạn quyết định dùng baseline Flyway khi đưa công cụ vào database đang có sẵn schema ra sao?
Bạn kiểm tra điểm baseline được chọn có tương ứng với trạng thái thực tế của database như thế nào?
Bạn xử lý migration bị thiếu hoặc sai thứ tự do merge nhánh bằng cách nào?
Bạn đánh giá khi nào cho phép áp dụng migration ngoài thứ tự trong Flyway và rủi ro kèm theo ra sao?
Bạn thiết kế các script repeatable cho view hoặc stored procedure mà vẫn quản lý thay đổi có thể kiểm chứng như thế nào?
Bạn xác định trường hợp nào phải dùng lệnh repair của Flyway và cần kiểm tra điều gì trước đó ra sao?
Bạn kiểm soát placeholder và cấu hình theo môi trường trong migration Flyway như thế nào?
Bạn xác định cách Flyway phối hợp khóa thực thi để tránh hai pipeline cùng thay đổi schema ra sao?
Bạn kiểm tra lịch sử Flyway sau khi chạy migration và trước khi cho phép ứng dụng khởi động như thế nào?
Bạn mô tả cơ chế quản lý changelog và changeSet của Liquibase theo cách dễ review như thế nào?
Bạn lựa chọn cách xác định id, author và đường dẫn changeSet để tránh xung đột khi làm việc nhóm ra sao?
Bạn phân biệt changeSet viết bằng SQL với changeSet khai báo trong XML, YAML hoặc JSON theo các yêu cầu nào?
Bạn dùng preconditions của Liquibase để bảo vệ một thay đổi chỉ hợp lệ ở trạng thái schema nhất định như thế nào?
Bạn thiết kế rollback cho changeSet Liquibase và kiểm chứng logic đảo ngược ra sao?
Bạn xác định khi nào không thể tin tưởng rollback tự sinh và cần viết hướng xử lý riêng như thế nào?
Bạn sử dụng contexts hoặc labels để kiểm soát changeSet theo môi trường và phạm vi triển khai như thế nào?
Bạn cân nhắc việc dùng runOnChange hoặc runAlways trong Liquibase để tránh chạy lại ngoài ý muốn ra sao?
Bạn kiểm tra cơ chế khóa changelog của Liquibase và xử lý trường hợp khóa tồn tại sau sự cố như thế nào?
Bạn dùng công cụ diff của Liquibase để phát hiện sai lệch schema nhưng vẫn kiểm soát chất lượng script như thế nào?
Bạn xác định sự khác nhau giữa trạng thái tracking của công cụ và trạng thái schema thực tế ra sao?
Bạn xử lý cơ sở dữ liệu đã được tạo thủ công trước khi đưa Liquibase vào quản lý như thế nào?
Bạn tổ chức file changelog theo tính năng hoặc theo phiên bản để bảo đảm lịch sử dễ theo dõi ra sao?
Bạn quyết định khi nào dùng tính năng đặc thù Flyway hoặc Liquibase và khi nào giữ SQL di động giữa các engine ra sao?
Bạn kiểm thử script migration trên đúng loại và phiên bản database dự kiến triển khai như thế nào?
Bạn xác định các kiểm thử cần có để bảo đảm một database mới có thể chạy toàn bộ lịch sử migration ra sao?
Bạn kiểm thử nâng cấp từ snapshot schema cũ lên phiên bản mới trong CI bằng cách nào?
Bạn xây dựng bộ dữ liệu kiểm thử có NULL, bản ghi trùng, kích thước lớn và ràng buộc phức tạp như thế nào?
Bạn kiểm tra data migration có xử lý đúng các tình huống biên mà dữ liệu sản xuất có thể gặp ra sao?
Bạn đánh giá migration có thể chạy lại an toàn sau lỗi mạng hoặc pipeline bị hủy bằng cách nào?
Bạn tổ chức kiểm thử tương thích ứng dụng cũ và mới với schema ở giai đoạn chuyển tiếp như thế nào?
Bạn kiểm thử rollback ứng dụng khi schema mới đã được áp dụng bằng cách nào?
Bạn đưa kiểm tra checksum và tính nhất quán lịch sử migration vào CI như thế nào?
Bạn xây dựng pipeline CI/CD để tự động kiểm tra migration trước khi cho phép triển khai ra sao?
Bạn xác định thời điểm chạy migration trong pipeline so với build và triển khai ứng dụng như thế nào?
Bạn xử lý việc nhiều instance ứng dụng đồng thời khởi động và đều muốn chạy migration ra sao?
Bạn quyết định nên chạy migration bằng job triển khai riêng hay khi ứng dụng khởi động theo tiêu chí nào?
Bạn thiết kế quyền database riêng cho tiến trình migration và quyền tối thiểu cho ứng dụng như thế nào?
Bạn quản lý secret kết nối và thông số môi trường trong pipeline mà không đưa vào repository ra sao?
Bạn lựa chọn cơ chế phê duyệt thay đổi schema có rủi ro cao trước khi triển khai production như thế nào?
Bạn thiết kế cổng kiểm tra trước triển khai dựa trên backup, dung lượng và tình trạng replication ra sao?
Bạn mô tả thứ tự phát hành migration trong chiến lược rolling deployment của một dịch vụ như thế nào?
Bạn xử lý xung đột khi hai pipeline độc lập triển khai migration tới cùng database ra sao?
Bạn thiết kế cơ chế ghi nhận ai đã chạy migration, phiên bản nào và kết quả thực thi ra sao?
Bạn theo dõi thời lượng, lỗi, số dòng chuyển đổi và tác động tới độ trễ ứng dụng sau migration như thế nào?
Bạn chọn các chỉ số và câu truy vấn kiểm tra sức khỏe ngay sau thay đổi schema ra sao?
Bạn xác định thời gian cần giữ trạng thái giám sát tăng cường sau một migration lớn như thế nào?
Bạn tổ chức cảnh báo khi migration thành công nhưng ứng dụng bắt đầu phát sinh lỗi truy vấn ra sao?
Bạn xác định tiêu chí để chặn release nếu schema giữa các môi trường không đồng nhất như thế nào?
Bạn kiểm thử khả năng triển khai lại cùng một phiên bản ứng dụng và migration mà không tạo thay đổi ngoài ý muốn ra sao?
Bạn lập kế hoạch thay đổi schema nhiều tenant khi các tenant có kích thước dữ liệu rất khác nhau như thế nào?
Bạn kiểm soát tiến độ và xử lý lỗi khi cần chạy migration trên hàng trăm database của các tenant ra sao?
Bạn thiết kế chiến lược rollout từng phần để phát hiện rủi ro trước khi triển khai rộng như thế nào?
Bạn xác định cách quản lý sự khác biệt schema có chủ đích giữa những khách hàng sử dụng nhiều phiên bản ứng dụng ra sao?
Bạn đánh giá ảnh hưởng của migration trên database dùng partitioning hoặc sharding như thế nào?
Bạn xử lý việc thay đổi schema phải diễn ra trên nhiều shard trong khi dịch vụ vẫn ghi dữ liệu ra sao?
Bạn quản lý thứ tự thay đổi ở database nguồn và các hệ thống đồng bộ dữ liệu downstream như thế nào?
Bạn kiểm tra ảnh hưởng của migration đến công cụ CDC hoặc luồng sự kiện dựa trên thay đổi bảng ra sao?
Bạn thiết kế phương án chuyển đổi trường dữ liệu khi API hoặc hợp đồng sự kiện bên ngoài chưa thể thay đổi đồng thời như thế nào?
Bạn chuẩn bị tài liệu vận hành migration gồm tiền điều kiện, thời gian dự kiến, bước xác minh và phương án phục hồi ra sao?
Bạn tổ chức review thay đổi schema với DBA, lập trình viên và đội vận hành theo những câu hỏi nào?
Bạn ghi lại quyết định kỹ thuật và các giả định của migration để người khác có thể bảo trì như thế nào?
Bạn phân tích nguyên nhân lặp lại của các migration lỗi để cải tiến quy trình phát triển như thế nào?
Bạn chọn những tiêu chí nào để chứng minh một quy trình schema migration an toàn, có thể tái hiện và phù hợp CI/CD?
