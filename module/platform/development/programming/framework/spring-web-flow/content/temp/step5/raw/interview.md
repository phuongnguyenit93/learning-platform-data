Bạn xác định trường hợp nào nên dùng Spring Web Flow thay cho điều hướng thuần Spring MVC Controller trong hành trình web nhiều bước như thế nào?
Bạn phân biệt một flow có trạng thái với chuỗi HTTP endpoints stateless theo vòng đời dữ liệu và khả năng tiếp tục phiên làm việc như thế nào?
Bạn mô tả mối quan hệ giữa flow definition, flow execution, state, event và transition trong Spring Web Flow ra sao?
Bạn xác định khi nào nên mô hình hóa quy trình đặt vé bằng flow thay vì lưu từng bước tùy ý trong HttpSession như thế nào?
Bạn phân biệt điều hướng theo event với điều hướng phụ thuộc trực tiếp vào URL khi thiết kế nhiều bước nhập liệu như thế nào?
Bạn đánh giá chi phí bảo trì của một flow definition lớn so với nhiều flows nhỏ có subflows dùng chung như thế nào?
Bạn thiết kế ranh giới giữa orchestration trong Web Flow và business rules trong service layer để tránh nhét nghiệp vụ vào cấu hình chuyển state như thế nào?
Bạn giải thích vì sao mô hình trạng thái tường minh giúp phát hiện các bước bị bỏ qua hoặc các transition không hợp lệ như thế nào?
Bạn chọn tiêu chí nào để xác định một hành trình còn thuộc cùng flow execution hay nên kết thúc và khởi tạo flow mới?
Bạn phân biệt một business transaction có thể kéo dài nhiều bước với database transaction nên có vòng đời ngắn ra sao?
Bạn thiết kế sơ đồ state cho quy trình đăng ký tài khoản gồm nhập thông tin, xác nhận email, duyệt lại và hoàn tất như thế nào?
Bạn xác định các hành trình song song trên hai browser tabs nên dùng cùng flow execution hay các execution riêng như thế nào?
Bạn đánh giá giới hạn của flow state nằm trên server khi số phiên làm việc đồng thời tăng nhanh ra sao?
Bạn mô tả những thông tin nào nên xuất hiện trong sơ đồ trạng thái để nhóm sản phẩm và kỹ thuật cùng kiểm tra điều hướng như thế nào?
Bạn thiết kế quy tắc đặt tên states và events để dễ đọc log mà không gắn cứng nhãn hiển thị giao diện với tên event như thế nào?
Bạn xác định vì sao Spring Web Flow không tự thay thế cơ chế xác thực, phân quyền hoặc kiểm soát giao dịch nghiệp vụ như thế nào?
Bạn đánh giá lúc nào một quy trình dài hàng ngày cần workflow engine bền vững thay vì chỉ dựa vào HTTP conversational flow như thế nào?
Bạn giải thích sự khác nhau giữa định nghĩa flow bất biến và dữ liệu của từng flow execution được tạo ra cho người dùng như thế nào?
Bạn thiết kế bước kết thúc flow để người dùng nhận được kết quả rõ ràng và có thể bắt đầu hành trình mới an toàn như thế nào?
Bạn phân tích nguy cơ coupling giữa flow definition và cấu trúc view templates khiến thay đổi giao diện làm hỏng điều hướng như thế nào?
Bạn mô tả cấu trúc tổng quát của một flow definition XML và cách các phần tử state được liên kết với nhau như thế nào?
Bạn xác định vai trò của start-state khi một flow có nhiều states nhưng người dùng phải đi từ một điểm vào hợp lệ như thế nào?
Bạn giải thích view-state dùng để hiển thị giao diện và chờ event từ browser thay vì tự động chuyển ngay sang state tiếp theo như thế nào?
Bạn phân biệt view-state với action-state khi một bước cần người dùng nhập liệu so với thực thi một thao tác trên server như thế nào?
Bạn mô tả action-state thực thi action và lựa chọn transition từ event kết quả mà action trả về như thế nào?
Bạn xác định khi nào dùng decision-state để chọn hướng đi bằng điều kiện thay vì gọi một service chỉ để trả event rẽ nhánh ra sao?
Bạn phân biệt end-state với view-state hiển thị màn hình cuối theo cách flow execution được đóng lại như thế nào?
Bạn giải thích subflow-state cho phép flow cha gọi một flow khác và nhận lại outcome như thế nào?
Bạn thiết kế flow có nhánh xác nhận đơn hàng và nhánh hủy để cả hai kết thúc rõ ràng bằng những states nào?
Bạn xác định cách biểu diễn một bước lựa chọn vận chuyển với các transitions khác nhau tùy option người dùng chọn như thế nào?
Bạn phân biệt transition dựa trên event name với transition có điều kiện guard khi nhiều điều kiện có thể cùng thỏa mãn như thế nào?
Bạn thiết kế thứ tự kiểm tra điều kiện rẽ nhánh để dữ liệu thiếu không rơi vào một nhánh xử lý nhạy cảm theo mặc định như thế nào?
Bạn mô tả tác động của một transition không có target state so với transition dẫn tới state khác theo hành vi flow engine như thế nào?
Bạn đánh giá khi nào nên giới hạn các events được chấp nhận tại từng state để client không tự nhảy qua bước bắt buộc như thế nào?
Bạn thiết kế một event quay lại bước trước sao cho người dùng không mất dữ liệu đã nhập hợp lệ như thế nào?
Bạn phân biệt event cancel với event submit khi cần bỏ những thay đổi chưa commit và chuyển đến kết quả kết thúc khác nhau như thế nào?
Bạn xác định cách xử lý một event lạ được gửi tới view-state để tránh điều hướng theo đường không được định nghĩa ra sao?
Bạn giải thích mục đích của on-start khi một flow cần chuẩn bị dữ liệu hoặc các biến trước khi state đầu tiên xuất hiện như thế nào?
Bạn phân biệt on-entry và on-exit của state khi cần tính lại dữ liệu hoặc dọn tài nguyên ở thời điểm chuyển trạng thái như thế nào?
Bạn thiết kế cách dùng on-render để chuẩn bị dữ liệu hiển thị mà không tạo side effect nghiệp vụ mỗi lần view được render lại như thế nào?
Bạn đánh giá rủi ro gọi service có side effect trong action được chạy lại sau refresh hoặc sau phục hồi flow như thế nào?
Bạn quyết định khi nào nên gán giá trị qua biểu thức của flow và khi nào nên gọi service rõ ràng để dễ kiểm thử như thế nào?
Bạn xác định cách truyền kết quả trả về của action sang một scope phù hợp để state tiếp theo sử dụng như thế nào?
Bạn phân biệt một transition đi sang state mới với việc render lại state hiện tại sau lỗi form validation như thế nào?
Bạn thiết kế cách xử lý business rule từ chối đơn hàng nhưng vẫn cho phép user sửa thông tin và gửi lại như thế nào?
Bạn đánh giá khi nào một decision-state có nhiều nhánh nên được tách thành business policy service thay vì dùng biểu thức ngày càng phức tạp ra sao?
Bạn xác định các lối thoát cho flow khi dữ liệu đã hết hạn hoặc quyền truy cập không còn hợp lệ ở bước tiếp theo như thế nào?
Bạn thiết kế flow xử lý thanh toán không cho phép event back quay lại thao tác đã tạo giao dịch tài chính như thế nào?
Bạn phân tích nguy cơ tạo vòng lặp state không có điều kiện dừng khiến request hoặc flow execution bị kẹt như thế nào?
Bạn mô tả cách bảo đảm mọi state có thể truy cập đều có đường đi hợp lệ tới một end-state theo yêu cầu nghiệp vụ như thế nào?
Bạn giải thích vì sao một flow event là kết quả của thao tác hoặc hành động nhưng không tự chứng minh hành động đã được commit bền vững như thế nào?
Bạn phân biệt request parameter dùng mang event với event kết quả do server-side action sinh ra theo độ tin cậy như thế nào?
Bạn xác định cách trình duyệt gửi event tới flow execution hiện hành qua cơ chế của Spring Web Flow như thế nào?
Bạn đánh giá tác động của việc client sửa tên event trong form submission và cách server giới hạn transitions được phép như thế nào?
Bạn thiết kế form nhiều nút submit với các events next, back và cancel mà vẫn kiểm soát được validation tương ứng như thế nào?
Bạn giải thích vai trò của biến execution key trong URL hoặc form khi trình duyệt gửi sự kiện tới một flow đang chạy như thế nào?
Bạn phân biệt flow execution key với business identifier của đơn hàng hoặc tài khoản khi lưu log và audit như thế nào?
Bạn xác định vì sao không được dựa chỉ vào flow execution key để cho phép truy cập dữ liệu của người dùng khác như thế nào?
Bạn thiết kế đường dẫn bắt đầu flow và đường dẫn tiếp tục flow để không trộn start request với request xử lý event như thế nào?
Bạn đánh giá tác động của browser refresh sau khi submit tới việc lặp event và khả năng tạo side effect trùng như thế nào?
Bạn xác định vai trò của Post/Redirect/Get trong trải nghiệm form và điều kiện nào Web Flow thực hiện redirect để duy trì execution state như thế nào?
Bạn phân biệt redirect sau khi flow tạm dừng với redirect sang trang kết quả bên ngoài flow khi cần tránh gửi lại form như thế nào?
Bạn thiết kế hành vi cho người dùng mở bookmark chứa execution key đã hết hiệu lực thay vì hiển thị lỗi server khó hiểu như thế nào?
Bạn phân tích tình huống người dùng nhấn Back của trình duyệt rồi submit một snapshot cũ của flow bằng cơ chế nào?
Bạn xác định cách lựa chọn chính sách hỗ trợ browser back button khi một số bước có thể lặp còn bước commit phải được bảo vệ như thế nào?
Bạn thiết kế tránh xử lý một event submit hai lần khi browser retry request sau mất kết nối như thế nào?
Bạn phân biệt bảo vệ double submit ở mức UI với idempotency key ở tầng service cho side effect quan trọng như thế nào?
Bạn giải thích flowScope khác requestScope về thời gian tồn tại của dữ liệu qua nhiều HTTP requests như thế nào?
Bạn phân biệt viewScope với flowScope khi dữ liệu chỉ phục vụ một màn hình nhập liệu hoặc cần giữ đến khi toàn hành trình kết thúc như thế nào?
Bạn xác định trường hợp nào flashScope phù hợp để chuyển thông báo qua bước điều hướng mà không lưu lâu trong flow như thế nào?
Bạn giải thích conversationScope có thể chia sẻ dữ liệu giữa flow cha và subflows trong cùng conversation như thế nào?
Bạn phân biệt conversationScope của Web Flow với HttpSession của Servlet container về phạm vi và số lượng flow executions như thế nào?
Bạn thiết kế lưu draft order trong flowScope nhưng chỉ đưa dữ liệu cần chia sẻ sang conversationScope khi subflow yêu cầu như thế nào?
Bạn đánh giá nguy cơ lưu entity JPA đang gắn persistence context vào flowScope qua nhiều HTTP requests như thế nào?
Bạn xác định cách tránh lưu object chứa password hoặc access token quá lâu trong viewScope hoặc flowScope như thế nào?
Bạn phân tích hậu quả dùng sessionScope cho mọi biến khi người dùng mở hai luồng thanh toán trong hai browser tabs như thế nào?
Bạn lựa chọn scope cho một danh sách options có thể cache và scope cho dữ liệu người dùng vừa nhập theo tính nhạy cảm như thế nào?
Bạn thiết kế quy trình dọn dữ liệu trong conversationScope khi subflow lỗi hoặc flow cha kết thúc sớm như thế nào?
Bạn xác định khi nào flow variables cần được khởi tạo lại ở flow start thay vì tái sử dụng dữ liệu từ execution cũ như thế nào?
Bạn phân biệt khai báo flow variable với gán dữ liệu trực tiếp vào scope khi cần kiểm soát kiểu và khởi tạo đối tượng như thế nào?
Bạn đánh giá rủi ro một biến cùng tên xuất hiện ở nhiều scopes và biểu thức resolve nhầm dữ liệu cũ như thế nào?
Bạn xác định cách giới hạn kích thước state được snapshot để không giữ danh sách hàng nghìn bản ghi trong session như thế nào?
Bạn thiết kế flow tiếp tục được sau khi instance ứng dụng restart và phân tích những điều kiện cần đối với storage của flow execution như thế nào?
Bạn giải thích cơ chế flow execution repository quản lý trạng thái các flow executions đang chạy như thế nào?
Bạn phân biệt FlowExecutor với FlowExecutionRepository theo trách nhiệm khởi tạo và tiếp tục flow so với lưu execution state như thế nào?
Bạn mô tả FlowExecutionKey giúp tra cứu execution trong repository và những giả định phải kiểm tra về tính hợp lệ của key ra sao?
Bạn đánh giá cách lưu execution snapshots ảnh hưởng đến browser back, memory consumption và consistency của flow state như thế nào?
Bạn xác định vì sao snapshot phục hồi trạng thái giao diện không mặc nhiên rollback thao tác đã commit vào cơ sở dữ liệu như thế nào?
Bạn thiết kế chính sách giới hạn số snapshots của một flow execution để người dùng vẫn quay lại được vài bước mà không tiêu thụ quá nhiều bộ nhớ như thế nào?
Bạn phân biệt session-backed flow execution repository với lựa chọn lưu trữ phù hợp khi ứng dụng triển khai nhiều instances như thế nào?
Bạn đánh giá rủi ro các nodes khác nhau deserialize flow execution không tương thích sau rolling deployment như thế nào?
Bạn xác định cách chuẩn bị migration hoặc kết thúc an toàn các flow executions còn đang mở khi thay đổi cấu trúc state definitions như thế nào?
Bạn thiết kế chính sách hết hạn cho một flow execution đang chờ người dùng hàng giờ thay vì để session giữ vô thời hạn như thế nào?
Bạn phân tích vì sao một session hết hạn làm flow execution key không còn tra cứu được dù business draft vẫn ở database như thế nào?
Bạn xác định cách khôi phục hành trình từ dữ liệu draft bền vững sau session timeout mà không tái sử dụng execution key cũ như thế nào?
Bạn đánh giá khi nào nên đưa trạng thái nghiệp vụ dài hạn vào database và chỉ dùng Web Flow giữ điều hướng ngắn hạn như thế nào?
Bạn thiết kế cơ chế liên kết draft ID với principal đã xác thực khi khởi tạo flow mới để người khác không mở được dữ liệu cũ như thế nào?
Bạn phân biệt state của flow engine với state trong bảng đơn hàng để quyết định nguồn sự thật khi chúng không khớp như thế nào?
Bạn xác định cách phát hiện flow execution không còn tồn tại và chuyển người dùng về bước bắt đầu hoặc trang phục hồi phù hợp như thế nào?
Bạn thiết kế xử lý một flow execution đã kết thúc nhưng browser vẫn gửi event tiếp theo từ trang lưu cache như thế nào?
Bạn giải thích subflow-state giúp tái sử dụng một hành trình con như chọn địa chỉ hoặc xác minh thông tin như thế nào?
Bạn phân biệt input mapping vào subflow với việc subflow đọc trực tiếp sessionScope của flow cha theo độ phụ thuộc như thế nào?
Bạn thiết kế truyền dữ liệu đầu vào cho subflow chọn phương thức vận chuyển nhưng không cho subflow sửa toàn bộ draft order như thế nào?
Bạn xác định cách subflow xuất kết quả về flow cha khi đi tới một end-state phù hợp như thế nào?
Bạn phân biệt subflow return event thành công với event hủy hoặc thất bại để flow cha chọn transition tiếp theo như thế nào?
Bạn đánh giá rủi ro subflow sửa conversationScope rồi trả cancel khiến flow cha vẫn nhìn thấy dữ liệu chưa được chấp nhận như thế nào?
Bạn thiết kế subflow có hợp đồng input/output rõ ràng để có thể được dùng ở nhiều parent flows mà không phụ thuộc tên states của cha như thế nào?
Bạn xác định khi nào một subflow nên chuyển thành độc lập flow thay vì nhúng sâu trong một conversation nhiều lớp như thế nào?
Bạn phân tích chi phí debug khi nhiều subflows lồng nhau cùng phát event có tên giống nhau nhưng ngữ nghĩa khác nhau ra sao?
Bạn kiểm thử nhánh subflow thành công và hủy để xác nhận parent flow nhận đúng outcomes và dữ liệu đầu ra như thế nào?
Bạn phân biệt form model với flow scope variable khi một view-state cần binding dữ liệu do người dùng gửi lên như thế nào?
Bạn giải thích vì sao chỉ định model cho view-state giúp Spring Web Flow thực hiện form binding và validation theo vòng đời của state như thế nào?
Bạn thiết kế form binding cho đối tượng đăng ký gồm email, địa chỉ và số điện thoại qua nhiều lần submit như thế nào?
Bạn xác định cách giới hạn những thuộc tính được phép bind để client không tự gán role hoặc trạng thái đã duyệt qua HTTP request như thế nào?
Bạn phân biệt binder configuration theo trường dữ liệu với kiểm tra business authorization tại service layer như thế nào?
Bạn đánh giá rủi ro mass assignment khi object có thuộc tính nhạy cảm nhưng binder cho phép cập nhật mọi property như thế nào?
Bạn thiết kế field binding cần thiết cho step nhập thông tin cá nhân nhưng không buộc các field của step sau phải có giá trị ngay như thế nào?
Bạn phân biệt required binding với validation constraint về ý nghĩa thiếu dữ liệu và lỗi giá trị như thế nào?
Bạn xác định khi nào nên tắt binding đối với một transition back hoặc cancel để không ghi đè draft bằng form chưa hợp lệ như thế nào?
Bạn phân tích một form submit có conversion error trước khi business validation chạy và cách hiển thị lỗi theo field ra sao?
Bạn thiết kế chuyển đổi dữ liệu ngày tháng hoặc enum trong form binding sao cho thông báo lỗi rõ và không phụ thuộc locale của máy chủ như thế nào?
Bạn phân biệt Spring Bean Validation với validation cơ chế của Web Flow khi xác định chỗ gắn các quy tắc kiểm tra dữ liệu như thế nào?
Bạn giải thích vai trò của ValidationContext khi validation cần biết view-state hiện tại hoặc những nhóm field vừa được gửi như thế nào?
Bạn thiết kế validation khác nhau cho bước nhập địa chỉ và bước xác nhận giao dịch mà vẫn tái sử dụng model như thế nào?
Bạn xác định cách trả validation errors qua MessageContext để giao diện hiển thị đúng trường và mức độ lỗi ra sao?
Bạn phân biệt lỗi input không hợp lệ với lỗi service bên ngoài tạm thời không khả dụng theo cách hiển thị và khả năng retry như thế nào?
Bạn đánh giá vì sao validation chỉ ở trình duyệt không đủ để bảo vệ transitions của flow trên server như thế nào?
Bạn xác định khi nào nên validation lại dữ liệu đã lưu trong flowScope trước khi thực hiện thao tác thanh toán cuối như thế nào?
Bạn thiết kế bảo vệ một form khỏi submit event next khi dữ liệu hợp lệ về định dạng nhưng không còn thỏa quy tắc nghiệp vụ như thế nào?
Bạn phân tích tác động của nhập liệu ở hai tabs cùng flow execution tới dữ liệu đã binding và các thông báo validation như thế nào?
Bạn xác định cách giữ lại dữ liệu form đã nhập khi validation thất bại và view-state được render lại như thế nào?
Bạn thiết kế test các trường hợp required field thiếu, lỗi type conversion, sai business rule và thao tác cancel bỏ qua validation như thế nào?
Bạn giải thích các thành phần FlowDefinitionRegistry, FlowExecutor và FlowHandlerMapping phối hợp với Spring MVC như thế nào?
Bạn phân biệt FlowHandlerMapping với RequestMappingHandlerMapping khi quyết định URL nào được xử lý bởi Web Flow hoặc controller thông thường như thế nào?
Bạn xác định vai trò của FlowHandlerAdapter khi Spring MVC dispatch request tới một flow như thế nào?
Bạn thiết kế đường URL cho một flow đăng ký và các controllers REST thông thường để không tạo mapping trùng nhau như thế nào?
Bạn giải thích FlowBuilderServices hỗ trợ cấu hình những dịch vụ dùng chung nào trong việc dựng flow definitions như thế nào?
Bạn xác định cách Spring bean được tham chiếu bởi action expressions và những rủi ro khi đặt logic nghiệp vụ trực tiếp vào biểu thức như thế nào?
Bạn phân biệt method call do flow action thực hiện với HTTP handler method do Spring MVC Controller tiếp nhận như thế nào?
Bạn thiết kế tích hợp flow với Thymeleaf hoặc một view technology tương thích mà vẫn duy trì model binding và event submission như thế nào?
Bạn đánh giá tác động của một view resolver không nhận ra tên view-state tới trải nghiệm lỗi khi người dùng vào flow như thế nào?
Bạn xác định cách truy cập những giá trị flowScope cần thiết trong view template mà không công bố toàn bộ dữ liệu nhạy cảm ra sao?
Bạn thiết kế điều hướng từ một controller sang flow start rồi quay lại trang kết quả thông thường sau end-state như thế nào?
Bạn phân tích sự cố cùng một flow chạy đúng trên local nhưng callback hoặc redirect sai hostname sau reverse proxy như thế nào?
Bạn xác định cách bảo đảm flow execution URLs dùng HTTPS public origin và không tiết lộ hostname nội bộ như thế nào?
Bạn thiết kế hoạt động chung của Spring Web Flow với Spring Security filters để chỉ user hợp lệ được bắt đầu hoặc tiếp tục hành trình như thế nào?
Bạn phân biệt việc bảo vệ URL bắt đầu flow với kiểm tra authorization trước một transition nhạy cảm trong flow đã mở như thế nào?
Bạn xác định cách kiểm tra quyền sở hữu business draft khi người dùng gửi lại execution key hợp lệ nhưng resource đã chuyển owner như thế nào?
Bạn thiết kế chặn event xác nhận cuối nếu quyền thanh toán đã bị thu hồi sau lúc người dùng mở màn hình trước đó như thế nào?
Bạn phân tích nguy cơ một flow execution được tạo trước khi login rồi tiếp tục sau khi user khác đăng nhập trong cùng browser như thế nào?
Bạn xác định cách kết hợp CSRF protection của Spring Security với form submit event của Spring Web Flow như thế nào?
Bạn đánh giá rủi ro CSRF khi browser tự gửi session cookie và client có thể phát event chuyển state không được dự định ra sao?
Bạn thiết kế lưu dữ liệu draft không chứa thông tin thẻ thanh toán hoặc token xác thực dài hạn qua nhiều flow snapshots như thế nào?
Bạn phân biệt khả năng đoán execution key với yêu cầu kiểm tra authentication và authorization độc lập ở các bước nhạy cảm như thế nào?
Bạn xác định cách tránh open redirect khi end-state nhận tham số địa chỉ trang trả về từ browser như thế nào?
Bạn thiết kế chính sách logout hủy khả năng tiếp tục các flow executions nhạy cảm đã tạo trước đó như thế nào?
Bạn phân tích khi người dùng đổi mật khẩu hoặc bị vô hiệu hóa account giữa flow, dữ liệu phiên và trạng thái quyền phải được xử lý ra sao?
Bạn xác định cách lưu audit trail cho các event xác nhận quan trọng mà không log raw execution key hoặc form payload nhạy cảm như thế nào?
Bạn thiết kế rate limiting cho event submit và tránh attacker tạo hàng nghìn flow executions trong một session như thế nào?
Bạn đánh giá session fixation và SameSite cookie settings ảnh hưởng tới việc quay lại flow sau bước đăng nhập như thế nào?
Bạn phân biệt scope authorization theo user, tenant và từng resource khi một flow có thể chuyển qua nhiều subflows như thế nào?
Bạn thiết kế action gọi một service transactional nhưng không giữ transaction mở trong lúc người dùng đang nhập liệu ở view-state như thế nào?
Bạn xác định khi nào nên commit draft vào database trước khi chuyển tới bước tiếp theo và khi nào chỉ nên cập nhật flowScope như thế nào?
Bạn phân tích tình huống service đã commit đơn hàng nhưng flow bị lỗi trước khi chuyển sang end-state và cách tránh tạo đơn hàng thứ hai như thế nào?
Bạn thiết kế idempotency key cho event confirm để refresh hoặc retry không tạo thêm thanh toán hay gửi email trùng như thế nào?
Bạn phân biệt rollback một database transaction với quay lại view-state trước trong trình duyệt theo tính nhất quán dữ liệu ra sao?
Bạn xác định cách xử lý optimistic locking failure khi draft được cập nhật qua hai tab hoặc từ một hệ thống ngoài như thế nào?
Bạn thiết kế flow kiểm tra version của đơn hàng trước commit và hiển thị thông báo có xung đột dữ liệu như thế nào?
Bạn đánh giá tác động khi một service action mất kết nối sau khi downstream đã xử lý thành công nhưng Web Flow chưa nhận kết quả như thế nào?
Bạn xác định khi nào nên tách thao tác mất nhiều phút thành background job và chuyển flow tới màn hình theo dõi trạng thái như thế nào?
Bạn thiết kế mô hình trạng thái cho một bước gọi dịch vụ bên ngoài có timeout, retry được và lỗi không thể phục hồi như thế nào?
Bạn phân biệt retry event hợp lệ do người dùng bấm lại với retry tự động của HTTP client khi có side effect như thế nào?
Bạn đánh giá khi nào nên triển khai cơ chế bù trừ nghiệp vụ thay vì cố rollback những side effects qua nhiều bước như thế nào?
Bạn xác định cách giữ thông tin lỗi tối thiểu trong flashScope hoặc viewScope mà không làm rò rỉ stack trace và credentials như thế nào?
Bạn thiết kế error transition khi action ném exception có thể phân loại được và một nhánh fallback cho lỗi không dự kiến như thế nào?
Bạn phân biệt transition theo event do business service trả về với cơ chế xử lý exception khi action không hoàn tất như thế nào?
Bạn xác định khi nào nên bắt exception và chuyển về view-state để user sửa dữ liệu thay vì kết thúc flow ngay như thế nào?
Bạn thiết kế trang phục hồi khi session hoặc flow execution expired nhưng business draft đã được lưu bền vững như thế nào?
Bạn phân tích lỗi không đọc được flow execution snapshot sau rolling deploy và cách giảm thiểu lỗi với các phiên đang mở như thế nào?
Bạn xác định cách xử lý một stale event từ trang cũ khi execution đã tiến sang state khác mà không âm thầm chấp nhận sai như thế nào?
Bạn thiết kế thông báo cho user khi hành trình không thể tiếp tục do dữ liệu nguồn đã thay đổi và cần bắt đầu lại như thế nào?
Bạn đánh giá khi nào lỗi binding nên được hiển thị ngay trên form và khi nào lỗi bảo mật phải chấm dứt yêu cầu như thế nào?
Bạn xác định cách đo số lượng flow executions đang hoạt động, trạng thái bị kẹt và thời gian hoàn thành hành trình như thế nào?
Bạn thiết kế metric chuyển đổi giữa các states và số lần validation thất bại mà không dùng execution key làm metric label như thế nào?
Bạn phân tích một flow có tỷ lệ abandon cao ở bước xác minh danh tính bằng dữ liệu latency, lỗi validation và các events nào?
Bạn xác định cách gắn correlation ID từ HTTP request qua action service và subflow mà không ghi dữ liệu form nhạy cảm vào traces như thế nào?
Bạn thiết kế logging state entry, event, transition và outcome đủ để chẩn đoán sự cố nhưng không lộ thông tin cá nhân như thế nào?
Bạn phân biệt audit log business commit với tracing hành trình Web Flow khi cần điều tra một giao dịch tranh chấp như thế nào?
Bạn xác định nguyên nhân memory tăng do flowScope chứa object graph lớn hoặc execution snapshots tích tụ bằng các chỉ số nào?
Bạn thiết kế timeout policy và cleanup cho những flow executions bị bỏ dở hàng giờ trên hệ thống có lượng truy cập lớn như thế nào?
Bạn đánh giá rủi ro mất phiên khi nhiều instances dùng local-only execution repository hoặc session store không được chia sẻ như thế nào?
Bạn thiết kế load test mở nhiều flow executions trên mỗi user để kiểm tra session size, locking và snapshot overhead như thế nào?
Bạn giải thích mục đích của AbstractXmlFlowExecutionTests khi kiểm thử behavior của flow definition mà không cần thao tác browser thật như thế nào?
Bạn phân biệt unit test của business service với flow execution test kiểm tra current state và transition theo event như thế nào?
Bạn thiết kế một bài test start flow và kiểm tra state đầu tiên được chọn đúng theo dữ liệu khởi tạo như thế nào?
Bạn sử dụng MockExternalContext để mô phỏng HTTP request parameters và user-triggered events trong flow execution test như thế nào?
Bạn kiểm thử view-state nhận event next, bind model và đi tới đúng state khi dữ liệu hợp lệ như thế nào?
Bạn thiết kế test event back không làm mất draft data nhưng event cancel phải kết thúc flow theo chính sách như thế nào?
Bạn kiểm thử lỗi validation khiến flow tiếp tục ở cùng view-state và MessageContext có thông báo tương ứng như thế nào?
Bạn thiết kế kiểm thử action-state có ba outcomes success, retryable-error và permanent-error bằng test doubles phù hợp như thế nào?
Bạn kiểm tra decision-state khi điều kiện rẽ nhánh ở ranh giới bằng, lớn hơn hoặc thiếu dữ liệu như thế nào?
Bạn thiết kế test subflow nhận đúng input, trả output và ánh xạ outcome về transition ở parent flow như thế nào?
Bạn phân biệt test flow definition đơn lẻ với integration test gồm Spring MVC, Spring Security và view rendering thực tế như thế nào?
Bạn kiểm thử một event không hợp lệ ở view-state để chứng minh flow không nhảy qua bước xác nhận bắt buộc như thế nào?
Bạn xác định cách kiểm thử concurrent requests trên cùng flow execution để phát hiện stale key, lost update hoặc lock contention như thế nào?
Bạn thiết kế bài test double submit event confirm để chứng minh business service chỉ thực hiện side effect một lần như thế nào?
Bạn kiểm thử phục hồi sau HTTP session timeout khi có và không có business draft lưu trong database như thế nào?
Bạn xây dựng test cho browser back và snapshot cũ để xác nhận bước đã commit không thể bị xử lý lại như thế nào?
Bạn lựa chọn khi nào cần chạy browser end-to-end test để phát hiện vấn đề JavaScript, CSRF token, redirect và cookie mà flow unit test bỏ sót như thế nào?
Bạn kiểm thử ứng dụng chạy sau reverse proxy khi flow execution URLs cần phản ánh scheme HTTPS và host công khai như thế nào?
Bạn thiết kế bài test hai browser tabs mở hai flow executions cho cùng user để chứng minh dữ liệu flowScope không bị trộn như thế nào?
Bạn đánh giá các test scenarios cần chạy trước khi nâng cấp phiên bản Spring Web Flow hoặc Spring Framework vì API integration và snapshot format có thể thay đổi như thế nào?
Bạn đề xuất kiến trúc Spring Web Flow cho một hành trình đặt hàng nhiều bước gồm states, events, binding/validation, subflows, scopes, MVC integration, bảo mật, recovery và kiểm thử như thế nào?
