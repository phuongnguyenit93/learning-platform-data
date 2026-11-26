Phân tích phụ thuộc tĩnh giúp phát hiện những rủi ro kiến trúc nào trong một dự án Java?
Bạn phân biệt quan hệ phụ thuộc ở mức class, package, module và thư viện như thế nào?
Một quan hệ phụ thuộc xuất hiện ở mã nguồn có thể khác quan hệ phát hiện từ bytecode ra sao?
Bạn sẽ xác định hướng của một cạnh trong đồ thị phụ thuộc bằng cách nào?
Làm thế nào để phân biệt phụ thuộc trực tiếp với phụ thuộc bắc cầu trong một ứng dụng Java?
Bạn sẽ thu thập dữ liệu gì trước khi vẽ đồ thị phụ thuộc của một hệ thống nhiều module?
Những dấu hiệu nào trên đồ thị khiến bạn nghi ngờ một kiến trúc đang bị ghép nối quá chặt?
Bạn nhận diện một chu kỳ phụ thuộc giữa các package bằng cách nào?
Một chu kỳ giữa các class và một chu kỳ giữa các module khác nhau về tác động ra sao?
Khi phát hiện chu kỳ phụ thuộc, bạn đánh giá mức độ ưu tiên xử lý dựa trên tiêu chí nào?
Bạn sẽ thiết kế lại ranh giới interface như thế nào để phá chu kỳ mà vẫn giữ hành vi của hệ thống?
Các chỉ số phụ thuộc vào và phụ thuộc ra của một package giúp bạn đánh giá khả năng thay đổi thế nào?
Bạn sẽ phát hiện một module đang trở thành điểm tập trung phụ thuộc của toàn hệ thống bằng cách nào?
Trong dự án Java nhiều module, bạn kiểm tra module nào được phép tham chiếu module nào ra sao?
JPMS với module-info.java có thể thể hiện hoặc giới hạn phụ thuộc như thế nào?
Bạn sẽ giải thích tác động của requires, exports và opens lên ranh giới module như thế nào?
Khi hệ thống dùng reflection hoặc ServiceLoader, bạn đánh giá những giới hạn nào của phân tích phụ thuộc tĩnh?
Bạn sẽ chạy jdeps trên một tệp JAR để khám phá những phụ thuộc ở mức package như thế nào?
Các tùy chọn phân tích API công khai và xuất đồ thị của jdeps phục vụ những câu hỏi kiến trúc nào?
Khi jdeps báo thiếu lớp hoặc không thể giải quyết một dependency, bạn điều tra classpath và module path ra sao?
Bạn kết hợp kết quả jdeps với cấu hình công cụ build như thế nào để tránh kết luận sai?
Bạn sẽ dùng Maven dependency:tree để truy vết nguồn gốc của một dependency bắc cầu như thế nào?
Kết quả của Maven dependency:analyze cần được diễn giải ra sao khi có thư viện dùng qua reflection hoặc annotation processor?
Bạn sẽ kiểm tra các dependency ở từng configuration của Gradle bằng cách nào?
Khi Gradle chọn phiên bản thư viện ngoài dự kiến, bạn dùng dependencyInsight để tìm nguyên nhân như thế nào?
Cơ chế chọn phiên bản của Maven và Gradle có thể dẫn tới hai cây phụ thuộc khác nhau ra sao?
Bạn sẽ dùng Maven BOM hoặc Gradle platform để kiểm soát sự đồng bộ phiên bản của một nhóm thư viện như thế nào?
Một xung đột phiên bản bắc cầu có thể gây lỗi NoSuchMethodError hoặc ClassNotFoundException ở runtime như thế nào?
Bạn sẽ phân tích sự xuất hiện của nhiều bản sao cùng một class trong các JAR như thế nào?
Khi gặp split package hoặc automatic module trong JPMS, bạn đánh giá nguy cơ tương thích ra sao?
Các scope compile, runtime, test và provided ảnh hưởng thế nào đến kết quả phân tích phụ thuộc?
Bạn sẽ kiểm tra nguy cơ do việc dùng shading, relocation hoặc fat JAR che khuất phụ thuộc bằng cách nào?
Bạn kết hợp kiểm kê thư viện và công cụ SCA để phân biệt rủi ro kiến trúc với lỗ hổng bảo mật thế nào?
Một SBOM có thể giúp truy xuất quan hệ phụ thuộc và phạm vi ảnh hưởng khi xuất hiện CVE mới ra sao?
Khi chuẩn bị nâng cấp một thư viện lõi, bạn lập bản đồ những module và API bị ảnh hưởng như thế nào?
Bạn sẽ xác minh một dependency đã được khai báo nhưng không còn sử dụng trước khi gỡ bỏ bằng cách nào?
Nếu một pull request thêm dependency mới, bạn đánh giá chi phí vận hành và mức độ ghép nối ra sao?
Bạn sẽ chuyển nguyên tắc kiến trúc phân lớp thành các quy tắc kiểm tra phụ thuộc cụ thể như thế nào?
Trong ArchUnit, bạn sẽ định nghĩa quy tắc cấm tầng domain phụ thuộc trực tiếp vào infrastructure ra sao?
Bạn sẽ sử dụng ArchUnit để bảo vệ ranh giới giữa các package hoặc bounded context thế nào?
Khi một quy tắc ArchUnit thất bại, bạn truy vết đường phụ thuộc vi phạm về mã nguồn bằng cách nào?
Bạn sẽ xử lý trường hợp kết quả kiểm tra kiến trúc là false positive hoặc có ngoại lệ có chủ đích ra sao?
Khi hệ thống đang có nhiều vi phạm cũ, bạn thiết lập baseline và ngăn vi phạm mới xuất hiện như thế nào?
Bạn sẽ chọn những kiểm tra dependency nào để chạy trên mỗi pull request và những kiểm tra nào để chạy định kỳ?
Bạn sẽ đặt ngưỡng hoặc điều kiện fail CI cho chu kỳ phụ thuộc, dependency bị cấm và xung đột phiên bản ra sao?
Bạn sẽ thiết kế báo cáo CI thế nào để người sửa code hiểu được cạnh phụ thuộc vi phạm và hướng khắc phục?
Khi việc phân tích toàn bộ repository làm pipeline chậm, bạn tối ưu phạm vi kiểm tra mà vẫn giữ độ tin cậy như thế nào?
Bạn sẽ xác nhận kết quả phân tích trên máy phát triển và CI nhất quán về JDK, classpath và lockfile ra sao?
Khi một bản phát hành lỗi do classpath khác môi trường build, bạn sẽ thu thập bằng chứng và khoanh vùng dependency như thế nào?
Bạn sẽ đo hiệu quả của việc áp dụng chính sách kiểm soát phụ thuộc sau vài sprint bằng những tín hiệu nào?
