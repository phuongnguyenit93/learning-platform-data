Bạn phân biệt xác thực danh tính với phân quyền trên từng đối tượng dữ liệu trong một API như thế nào?
Bạn giải thích object-level authorization là gì và quyết định quyền truy cập cần xét những thành phần nào của chủ thể, tài nguyên, hành động và ngữ cảnh như thế nào?
Bạn phân biệt Broken Object Level Authorization (BOLA) với lỗi xác thực, lỗi phân quyền chức năng và lỗi phân quyền thuộc tính như thế nào?
Bạn mô tả IDOR phát sinh khi ứng dụng tin vào object identifier do client cung cấp mà không kiểm tra quyền trên đối tượng đích như thế nào?
Bạn giải thích vì sao UUID khó đoán hoặc ID dạng opaque không thể thay thế kiểm tra quyền truy cập trên từng đối tượng như thế nào?
Bạn xây dựng threat model cho API quản lý tài liệu để xác định các thao tác đọc, sửa, xóa, chia sẻ và tải xuống có thể bị lạm dụng như thế nào?
Bạn xác định subject, resource, action và environment context trong một quyết định phân quyền đối với một bản ghi cụ thể như thế nào?
Bạn phân biệt quyền truy cập ở cấp chức năng với quyền truy cập một instance cụ thể của tài nguyên như thế nào?
Bạn thiết kế default-deny policy để mọi thao tác trên đối tượng đều bị từ chối cho tới khi có quy tắc cho phép rõ ràng như thế nào?
Bạn xử lý xung đột giữa quy tắc allow và deny khi một chủ thể đồng thời có nhiều vai trò hoặc quan hệ với cùng một đối tượng như thế nào?
Bạn phân biệt RBAC, ABAC và ReBAC trong việc biểu diễn quyền sở hữu, thuộc tính tài nguyên và quan hệ giữa các chủ thể như thế nào?
Bạn xác định khi nào role-based permission là chưa đủ và cần thêm điều kiện dựa trên owner, tenant, trạng thái hoặc quan hệ chia sẻ như thế nào?
Bạn thiết kế chính sách dựa trên thuộc tính để quyết định quyền theo chủ thể, loại tài nguyên, hành động, mức phân loại và ngữ cảnh như thế nào?
Bạn mô hình hóa quan hệ owner, editor, viewer và delegate để nhiều người cùng truy cập một đối tượng theo quyền khác nhau như thế nào?
Bạn phân biệt quyền sở hữu trực tiếp với quyền được chia sẻ hoặc được ủy quyền trên một đối tượng như thế nào?
Bạn xác định nguồn tin cậy của owner ID, tenant ID và subject identity thay vì lấy các giá trị này trực tiếp từ request body như thế nào?
Bạn xử lý trường hợp người dùng gửi object ID thuộc tài khoản khác trong path, query, header hoặc payload để ngăn truy cập trái phép như thế nào?
Bạn giải thích vì sao ẩn nút hoặc không trả object ID trong giao diện không đủ để bảo vệ API khỏi BOLA như thế nào?
Bạn thiết kế endpoint lấy chi tiết đối tượng để luôn ràng buộc truy vấn với danh tính và phạm vi quyền của người gọi như thế nào?
Bạn so sánh cách tải đối tượng trước rồi kiểm tra quyền với cách lọc quyền ngay trong truy vấn dữ liệu về độ an toàn và hiệu năng như thế nào?
Bạn xây dựng truy vấn danh sách chỉ trả về những đối tượng mà chủ thể hiện tại được phép xem thay vì tải toàn bộ rồi lọc ở tầng giao diện như thế nào?
Bạn xử lý endpoint tìm kiếm, autocomplete và bộ lọc để kết quả không tiết lộ tên, số lượng hoặc metadata của đối tượng ngoài phạm vi quyền như thế nào?
Bạn bảo đảm kiểm tra quyền nhất quán cho GET, POST, PUT, PATCH và DELETE trên cùng một đối tượng như thế nào?
Bạn phân tích rủi ro khi endpoint cập nhật kiểm tra quyền trên object ID trong URL nhưng lại cho phép client thay đổi owner ID hoặc tenant ID trong body như thế nào?
Bạn ngăn mass assignment hoặc property injection làm thay đổi trường ownership, tenant, classification hay access policy ngoài quyền của người gọi như thế nào?
Bạn phân biệt object-level authorization với field-level authorization khi một người được xem bản ghi nhưng chỉ được đọc một số thuộc tính của bản ghi đó như thế nào?
Bạn thiết kế response projection để loại bỏ trường nhạy cảm theo quyền mà không dựa vào việc frontend tự ẩn các trường như thế nào?
Bạn kiểm tra quyền trên cả đối tượng cha và đối tượng con khi API truy cập tài nguyên qua nested route như thế nào?
Bạn xử lý trường hợp người dùng có quyền xem project nhưng không có quyền xem một secret hoặc attachment nằm bên trong project như thế nào?
Bạn thiết kế quyền trên quan hệ giữa hai đối tượng để người dùng không thể tự gắn một tài liệu vào project mà họ không có quyền sửa như thế nào?
Bạn bảo vệ bulk read, bulk update và bulk delete khi một request chứa nhiều object ID thuộc nhiều chủ sở hữu hoặc tenant khác nhau như thế nào?
Bạn lựa chọn từ chối toàn bộ hay xử lý từng phần đối với bulk operation có một số đối tượng không được phép truy cập dựa trên yêu cầu nghiệp vụ và nguy cơ rò rỉ như thế nào?
Bạn kiểm soát GraphQL resolver hoặc API tương tự để quyền được kiểm tra ở từng node và field lồng nhau thay vì chỉ kiểm tra ở endpoint gốc như thế nào?
Bạn ngăn batch loader, data loader hoặc cơ chế gom truy vấn dùng chung cache trả dữ liệu của một chủ thể cho chủ thể khác như thế nào?
Bạn bảo đảm export, report, print view và file download chỉ bao gồm các đối tượng mà người yêu cầu có quyền truy cập như thế nào?
Bạn kiểm tra quyền khi truy cập file qua object storage hoặc signed URL sau khi quyền chia sẻ của người dùng đã bị thu hồi như thế nào?
Bạn thiết kế thời hạn và phạm vi của signed URL để liên kết tải xuống không trở thành quyền truy cập lâu dài ngoài chính sách như thế nào?
Bạn xử lý quyền truy cập vào thumbnail, preview, attachment và bản sao dẫn xuất để chúng không vô tình rộng hơn quyền của tài liệu gốc như thế nào?
Bạn áp dụng object-level authorization cho background job được tạo bởi người dùng để tác vụ vẫn kiểm tra đúng chủ thể và quyền tại thời điểm thực thi như thế nào?
Bạn ngăn một job queue hoặc scheduler dùng service identity có quyền quá rộng để thực hiện thao tác thay mặt người dùng mà bỏ qua quyền gốc như thế nào?
Bạn xác định quyền cần kiểm tra lại khi tác vụ bất đồng bộ chạy sau thời điểm người dùng tạo yêu cầu và quyền của họ có thể đã thay đổi như thế nào?
Bạn bảo vệ webhook, callback và endpoint nội bộ có tham chiếu object ID để chúng không trở thành đường truy cập thay thế bỏ qua chính sách chính như thế nào?
Bạn phân biệt quyền của người dùng cuối với quyền của service account khi một dịch vụ gọi dịch vụ khác để truy cập tài nguyên thay mặt người dùng như thế nào?
Bạn truyền danh tính và ngữ cảnh ủy quyền qua nhiều dịch vụ mà không tin cậy các header hoặc metadata do client tự gửi như thế nào?
Bạn xác định dịch vụ nào chịu trách nhiệm thực thi authorization khi một request đi qua API gateway, backend và data service như thế nào?
Bạn thiết kế tenant isolation để mọi truy vấn đọc, ghi, tìm kiếm và xóa đều bị giới hạn trong tenant đã được xác minh như thế nào?
Bạn xác định tenant context từ identity đã được xác thực và kiểm tra nó với resource ownership thay vì tin tenant ID trong URL như thế nào?
Bạn xử lý tình huống một người dùng thuộc nhiều tenant và chuyển tenant trong cùng một phiên để không trộn lẫn quyền hoặc dữ liệu như thế nào?
Bạn phân biệt cách ly tenant ở tầng ứng dụng, schema, database và row-level security theo mức bảo đảm cùng chi phí vận hành như thế nào?
Bạn sử dụng row-level security hoặc cơ chế lọc dữ liệu tương đương để phòng truy vấn quên điều kiện tenant như thế nào?
Bạn kiểm soát connection pool hoặc transaction context để tenant identity không bị rò rỉ giữa các request sử dụng lại cùng kết nối như thế nào?
Bạn thiết kế kiểm thử cross-tenant để phát hiện trường hợp người dùng tenant A đọc, sửa hoặc xóa đối tượng thuộc tenant B như thế nào?
Bạn xử lý tài nguyên dùng chung giữa nhiều tenant như catalog, template hoặc public object để phân biệt quyền truy cập toàn cục với quyền truy cập tenant như thế nào?
Bạn xác định quyền sở hữu khi đối tượng được chuyển từ user này sang user khác hoặc từ tenant này sang tenant khác như thế nào?
Bạn thiết kế quy trình transfer ownership có kiểm tra quyền của bên chuyển, bên nhận và các quan hệ chia sẻ đang tồn tại như thế nào?
Bạn thu hồi quyền chia sẻ khi thành viên rời nhóm hoặc bị loại khỏi tổ chức và bảo đảm quyền kế thừa cũng được cập nhật như thế nào?
Bạn xử lý quan hệ chia sẻ theo nhóm lồng nhau để thay đổi membership không tạo ra quyền thừa hoặc quyền truy cập tồn tại ngoài dự kiến như thế nào?
Bạn xác định precedence giữa quyền trực tiếp, quyền kế thừa từ group, quyền qua organization và quyền chia sẻ công khai như thế nào?
Bạn đánh giá nguy cơ một object được chuyển sang trạng thái archived, deleted hoặc restricted nhưng vẫn có thể truy cập qua endpoint cũ như thế nào?
Bạn bảo đảm quyền được kiểm tra tại thời điểm ghi dữ liệu để tránh TOCTOU khi ownership hoặc policy thay đổi giữa bước kiểm tra và cập nhật như thế nào?
Bạn thiết kế cập nhật nguyên tử có điều kiện theo owner, tenant hoặc policy version để tránh race condition làm phát sinh ghi trái phép như thế nào?
Bạn xác định khi nào cần thực hiện authorization lại trong transaction dài hoặc workflow nhiều bước để quyền đã bị thu hồi không tiếp tục được sử dụng như thế nào?
Bạn kiểm soát cache của kết quả authorization để một quyết định allow cũ không tiếp tục có hiệu lực sau khi quyền bị thu hồi như thế nào?
Bạn thiết kế cache key có xét subject, tenant, resource, action và policy version để tránh dùng chung kết quả phân quyền giữa các ngữ cảnh như thế nào?
Bạn xử lý cache dữ liệu object đã được lọc theo quyền khi cùng một tài nguyên được truy cập bởi nhiều vai trò khác nhau như thế nào?
Bạn bảo đảm search index, data warehouse, replica và read model áp dụng cùng ranh giới object-level authorization với nguồn dữ liệu chính như thế nào?
Bạn xác định rủi ro dữ liệu đã bị xóa hoặc thu hồi quyền nhưng vẫn xuất hiện trong cache, search result hoặc bản export cũ như thế nào?
Bạn thiết kế audit log cho quyết định truy cập đối tượng để có thể truy vết chủ thể, hành động, tài nguyên, kết quả và policy đã áp dụng như thế nào?
Bạn cân bằng mức chi tiết của audit log với yêu cầu bảo vệ dữ liệu cá nhân và tránh ghi nội dung tài nguyên nhạy cảm như thế nào?
Bạn xây dựng metric để phát hiện tỷ lệ authorization denied tăng bất thường, truy vấn ID tuần tự hoặc hành vi dò object ID như thế nào?
Bạn phân biệt truy cập bị từ chối hợp lệ với dấu hiệu enumeration hoặc BOLA probing dựa trên chuỗi request và phạm vi object ID như thế nào?
Bạn thiết kế response cho đối tượng không tồn tại và đối tượng tồn tại nhưng người gọi không có quyền để hạn chế việc suy đoán sự tồn tại của tài nguyên như thế nào?
Bạn đánh giá trade-off giữa trả 403 và 404 khi từ chối truy cập đối tượng để vừa đáp ứng API contract vừa hạn chế rò rỉ thông tin như thế nào?
Bạn xây dựng ma trận kiểm thử theo subject, role, tenant, ownership, action và trạng thái resource để bao phủ các quyết định allow và deny như thế nào?
Bạn thiết kế negative test cho việc thay object ID trong path, query, body, nested reference và batch payload để phát hiện IDOR như thế nào?
Bạn sử dụng property-based testing hoặc fuzzing để kiểm tra bất biến rằng chủ thể không thể đọc hoặc thay đổi tài nguyên ngoài phạm vi được cấp như thế nào?
Bạn kiểm thử các đường truy cập thay thế như export, download, search, GraphQL, background job và API phiên bản cũ để phát hiện policy bị bỏ sót như thế nào?
Bạn kiểm tra race condition giữa thu hồi quyền và thao tác cập nhật đồng thời bằng cách nào để xác minh không có ghi trái phép sau khi quyền hết hiệu lực?
Bạn xây dựng bộ test hồi quy cho policy khi thêm vai trò, loại tài nguyên hoặc quan hệ chia sẻ mới mà không làm mở rộng quyền ngoài ý muốn như thế nào?
Bạn xử lý sự cố phát hiện người dùng đọc được hồ sơ thuộc tenant khác bằng cách xác định phạm vi ảnh hưởng, thu hồi quyền và kiểm tra dữ liệu đã bị truy cập như thế nào?
Bạn xác lập tiêu chí nghiệm thu end-to-end để chứng minh mọi thao tác trên đối tượng đều kiểm tra quyền đúng chủ thể, đúng tenant và đúng hành động như thế nào?
