Một nền tảng bán hàng dùng SQL để tính doanh thu theo tháng; sau khi join bảng đơn với nhiều dòng sản phẩm và nhiều phiếu giảm giá, tổng tiền bị nhân lên dù từng bảng nguồn đều đúng.
Một cổng quản lý khách hàng lọc tài khoản chưa có số điện thoại bằng điều kiện so sánh thông thường với NULL; báo cáo thiếu những bản ghi trống mà bộ phận chăm sóc khách hàng muốn nhận diện.
Một hệ thống quản lý kho dùng LEFT JOIN để liệt kê cả sản phẩm chưa có giao dịch; khi thêm điều kiện lọc trạng thái giao dịch trong WHERE, những sản phẩm chưa giao dịch biến mất khỏi kết quả.
Một báo cáo nhân sự gộp số nhân viên theo chi nhánh bằng GROUP BY; nhóm phát triển thêm một cột tên quản lý không có quy tắc tổng hợp khiến truy vấn lỗi hoặc kết quả không như thiết kế.
Một dịch vụ thống kê muốn chỉ giữ những cửa hàng có trên 100 đơn hoàn tất; bộ truy vấn đặt điều kiện dựa vào số đếm ở giai đoạn lọc bản ghi nên không thể hiện đúng quy tắc tổng hợp.
Một cổng thương mại dùng ROW_NUMBER để chọn giao dịch gần nhất theo thời gian; khi hai giao dịch có cùng timestamp, bản ghi được chọn thay đổi giữa các lần chạy mà không có tiêu chí phá hòa.
Một API phân trang chỉ dùng LIMIT và OFFSET mà không xác định thứ tự dữ liệu; sau khi hệ quản trị thay kế hoạch thực thi, khách hàng thấy mục bị lặp hoặc thiếu khi chuyển trang.
Một bộ phận tài chính dùng DISTINCT để loại dòng trùng sau phép join; việc loại trùng che khuất sự khác nhau giữa nhiều khoản hoàn tiền thật và làm doanh thu thấp hơn số thực tế.
Một dịch vụ kiểm tra danh sách khách bị khóa dùng NOT IN với một truy vấn con có thể trả NULL; nhiều khách hợp lệ không xuất hiện trong danh sách dù mã của họ không thuộc tập bị khóa.
Một cổng kiểm kê dùng truy vấn SQL lồng nhau có tương quan cho từng sản phẩm; khi số sản phẩm tăng mạnh, cùng một mô tả kết quả cho thời gian chạy cao hơn dự toán của nhóm vận hành.
Một báo cáo đối soát áp dụng hàm biến đổi lên cột ngày trong điều kiện lọc; trên bảng giao dịch lớn, hệ quản trị không chọn được kế hoạch truy cập như lúc điều kiện dùng trực tiếp dữ liệu đã đánh chỉ mục.
Một hệ thống phân tích giá chỉ mô tả điều kiện join giữa nhiều bảng; khi dữ liệu phân bố lệch và thống kê cũ, optimizer chọn thứ tự join làm truy vấn chậm bất thường ở một chi nhánh.
Một dịch vụ xây truy vấn với Common Table Expression để làm rõ các bước tổng hợp; nhóm vận hành giả định CTE luôn tạo bảng tạm nên lý giải sai kế hoạch thực thi trên phiên bản cơ sở dữ liệu mới.
Một hệ thống theo dõi quan hệ người giới thiệu sử dụng recursive CTE; dữ liệu có chu trình giữa các tài khoản khiến việc duyệt quan hệ tạo nhiều bản ghi hoặc không kết thúc như dự kiến.
Một nền tảng kế toán tạo materialized view cho báo cáo doanh thu; sau một ngày nhập thêm giao dịch, báo cáo từ view vẫn phản ánh thời điểm làm mới cũ chứ không phải trạng thái tức thời.
Một cổng tìm kiếm dùng so sánh chuỗi trong SQL; collation của môi trường production coi một số chữ hoa, chữ thường hoặc dấu là tương đương trong khi kiểm thử dùng quy tắc khác.
Một dịch vụ thống kê lọc giao dịch theo ngày trong SQL; timestamp được lưu theo UTC nhưng người dùng chọn ngày địa phương nên các giao dịch sát nửa đêm bị tính vào ngày khác.
Một hệ thống đặt hàng xây báo cáo bằng truy vấn khai báo trên dữ liệu đang được cập nhật; hai lần chạy ở mức cô lập giao dịch khác nhau cho tổng không khớp dù biểu thức SQL không đổi.
Một nền tảng thanh toán dùng SQL UPSERT để mô tả trạng thái đơn mong muốn; hai request có cùng khóa nghiệp vụ nhưng payload khác nhau khiến thứ tự ghi và điều kiện xung đột quyết định dữ liệu cuối.
Một công cụ quản trị nhận điều kiện lọc SQL từ một DSL do người dùng nhập; tầng chuyển đổi không giới hạn biểu thức phức tạp nên một truy vấn hợp lệ vẫn tiêu tốn quá nhiều tài nguyên cơ sở dữ liệu.
Một dịch vụ nhập hóa đơn chuyển danh sách bản ghi thành Java Stream với map để chuẩn hóa dữ liệu; chưa có terminal operation nên việc ghi nhật ký đặt trong map không diễn ra như nhóm phát triển dự kiến.
Một nền tảng tính điểm tạo Stream từ danh sách học viên và muốn dùng pipeline đó cho hai báo cáo; sau khi một terminal operation đã tiêu thụ luồng, lượt tính thứ hai phát sinh lỗi.
Một cổng thương mại dùng filter rồi findAny để lấy một sản phẩm còn hàng; khi bật parallel stream, sản phẩm được chọn không ổn định dù dữ liệu nguồn giống nhau.
Một dịch vụ ngân hàng dùng parallelStream để cộng số tiền và cập nhật một biến tích lũy bên ngoài lambda; khi chạy nhiều luồng, tổng có lúc thấp hơn giá trị đối soát.
Một hệ thống phân tích sử dụng reduce trên Stream với phép toán phụ thuộc thứ tự và không có tính kết hợp; kết quả chạy tuần tự khác chạy song song trên cùng dãy sự kiện.
Một nền tảng logistics dùng Stream.sorted với comparator không nhất quán ở các trường hợp bằng nhau; thứ tự kết quả thay đổi và các tác vụ phụ thuộc thứ tự phân xe bị ảnh hưởng.
Một dịch vụ quản lý tài khoản dùng distinct trên Stream các DTO mutable; khi thuộc tính tham gia equals và hashCode thay đổi, số bản ghi được giữ không giống quy tắc trùng lặp nghiệp vụ.
Một ứng dụng tổng hợp log dùng Collectors.toMap để lập bảng theo mã phiên; dữ liệu có hai sự kiện cùng mã phiên khiến quá trình thu thập thất bại ở batch cao điểm.
Một báo cáo kinh doanh dùng groupingBy rồi duyệt Map kết quả để hiển thị nhóm theo thứ tự; thứ tự nhóm không được bảo đảm như danh sách mong đợi của giao diện.
Một cổng tuyển dụng dùng stream với peek để gửi email thông báo khi xét từng ứng viên; thay đổi cách pipeline dừng sớm khiến một phần email không được gửi.
Một dịch vụ phân tích sự kiện dùng takeWhile trên luồng không có thứ tự xác định; tập dữ liệu được giữ lại khác kết quả lọc toàn bộ mà nhóm nghiệp vụ đang kỳ vọng.
Một nền tảng nhận dữ liệu liên tục tạo Stream vô hạn rồi gọi sorted trước limit; chức năng lấy một số ít sự kiện đầu tiên không trả kết quả trong thời gian cho phép.
Một ứng dụng đọc tệp nhiều gigabyte dùng Files.lines kết hợp Stream để lọc lỗi; đường xử lý exception bỏ qua việc đóng luồng khiến số file handle đang mở tăng theo yêu cầu.
Một hệ thống đơn hàng đặt tác vụ ghi database trong map của Stream; khi pipeline có lỗi ở giữa hoặc thực thi lại, tác dụng phụ đã xảy ra một phần và dữ liệu không còn dễ đối soát.
Một dịch vụ đề xuất sản phẩm dùng flatMap để kết hợp danh sách từ nhiều nhà cung cấp; một nguồn có giá trị null làm lỗi chỉ xuất hiện khi terminal operation bắt đầu đánh giá pipeline.
Một cổng thống kê đổi vòng lặp sang Stream để tăng tính khai báo; với tập dữ liệu rất lớn và nhiều phép boxing, bộ nhớ cấp phát tăng dù biểu thức lọc và tổng hợp được viết ngắn hơn.
Một ứng dụng phân loại quyền dùng Optional.stream để gom các giá trị có thể vắng mặt; báo cáo vẫn ghép kết quả theo chỉ số đầu vào nên các trường rỗng làm dữ liệu hai cột bị lệch.
Một nền tảng theo dõi tiến trình dùng stream song song với forEach để ghi kết quả ra tệp; thứ tự dòng trong tệp khác thứ tự đầu vào khiến bộ kiểm toán tưởng dữ liệu đã bị xáo trộn.
Một hệ thống phân tích quan hệ gia đình mô tả quan hệ tổ tiên bằng các quy tắc logic đệ quy; dữ liệu chứa chu trình khiến engine thử các đường suy diễn lặp đi lặp lại và không trả kết quả như mong đợi.
Một bộ kiểm tra chính sách suy luận rằng người dùng không có bản ghi quyền thì không được phép truy cập; dữ liệu quyền đồng bộ trễ khiến việc coi thiếu sự kiện là phủ định tạo quyết định sai.
Một hệ thống phát hiện gian lận dùng Datalog để suy ra mạng lưới tài khoản liên quan; số quan hệ tăng mạnh khiến tập sự kiện suy diễn trung gian lớn hơn nhiều so với dữ liệu gốc.
Một thư viện quy tắc xác định khách hàng đủ điều kiện ưu đãi bằng nhiều mệnh đề; hai rule có điều kiện giao nhau cho cùng khách những kết luận khác nhau mà tài liệu chưa định nghĩa ưu tiên.
Một cổng phê duyệt diễn giải quy tắc logic chứa lượng từ và biến dùng chung; bộ chuyển đổi DSL vô tình dùng các biến khác nhau cho cùng một thực thể khiến những hồ sơ không liên quan bị ghép.
Một hệ thống đối chiếu dữ liệu nhận mã khách hàng dạng số và dạng chuỗi từ hai nguồn sự kiện; engine unification không ghép hai giá trị mà nghiệp vụ coi là cùng một khách.
Một nền tảng phát hiện bất thường dựa vào sự kiện logic có thời gian hiệu lực; quy tắc không xét mốc thời gian nên suy luận vẫn dùng trạng thái đã hết hạn của một tài khoản.
Một công cụ suy luận quan hệ dựa trên cơ chế chỉ bổ sung fact; khi nhân viên bị thu hồi quyền, các kết luận đã tạo từ fact cũ vẫn xuất hiện trong báo cáo truy cập.
Một dịch vụ xử lý yêu cầu hỗ trợ kết hợp các rule có điều kiện phủ định với quan hệ đệ quy; một số công cụ suy diễn không chấp nhận cấu trúc rule này như nhóm phát triển dự kiến.
Một nền tảng chấm điểm rủi ro dùng nhiều rule để phân loại giao dịch; bộ phận kiểm toán cần giải thích fact và rule nào dẫn đến kết luận nhưng hệ thống chỉ xuất nhãn cuối cùng.
Một doanh nghiệp cần phân ca cho nhân viên với kỹ năng, giới hạn giờ và yêu cầu nghỉ phép; mô hình CSP mô tả đủ quy tắc nhưng chưa ràng buộc các quyết định đã chốt nên lịch mới thay đổi ca cũ.
Một trung tâm hội nghị dùng ràng buộc AllDifferent để gán phòng cho phiên họp; một nhóm phiên có ít phòng khả dụng hơn số phiên đồng thời nhưng solver mất nhiều thời gian mới phát hiện vô nghiệm.
Một cơ sở sản xuất quy định thứ tự công đoạn và tài nguyên máy giới hạn; mô hình đặt thời điểm bắt đầu thành biến nhưng chưa liên kết độ dài công đoạn nên lịch hợp lệ theo biến lại chồng chéo thực tế.
Một nền tảng giao hàng muốn giảm tổng quãng đường nhưng vẫn phải thỏa mọi khung giờ nhận hàng; nhóm mô hình hóa biến điều kiện giờ bắt buộc thành khoản phạt nên nghiệm có điểm thấp vẫn giao trễ.
Một hệ thống phân phòng cho nhân viên dùng các phòng có sức chứa như nhau; engine thử nhiều phép hoán đổi nhãn phòng tương đương và chi phí tìm kiếm tăng dù lịch nghiệp vụ không thay đổi.
Một ứng dụng phân công tài xế dùng propagation thu hẹp miền nhân sự sau khi một chuyến được gán; một điều kiện bằng lái bị bỏ sót khiến solver vẫn giữ tài xế không đủ điều kiện cho chuyến.
Một tổ chức xếp lịch thi dùng backtracking với chiến lược thử môn có nhiều phòng trước; đến gần cuối tìm kiếm mới phát hiện môn chỉ có một phòng phù hợp bị xung đột.
Một nền tảng tối ưu kho trả về trạng thái UNKNOWN khi hết thời gian; hệ thống phía trên coi trạng thái này là vô nghiệm và từ chối đơn hàng dù chưa có chứng minh mâu thuẫn.
Một công ty vận tải dùng mô hình ràng buộc với hai mục tiêu chi phí và số xe; đội quản lý thay mức ưu tiên nhưng cấu hình solver vẫn giữ hàm mục tiêu cũ nên phương án không đáp ứng chính sách mới.
Một dịch vụ phân công kỹ sư nhận nghiệm được solver đánh dấu khả thi; khi ánh xạ ID biến về nhân sự thật, một kỹ sư bị giao hai việc cùng giờ mà bước kiểm tra cuối chưa phát hiện.
Một công ty bảo hiểm mô tả mức phí bằng DSL với các điều kiện theo tuổi, vùng và gói bảo hiểm; hai quy tắc cùng phù hợp một hồ sơ nhưng engine chọn kết quả khác nhau khi thứ tự khai báo đổi.
Một cổng khuyến mãi cho phép nhân viên viết điều kiện giảm giá trong DSL; một quy tắc không kiểm tra giới hạn tiền tối đa làm đơn hàng có tổng thanh toán âm ở trường hợp biên.
Một bộ máy workflow nhận mô tả các trạng thái chờ duyệt và được duyệt; khi một sự kiện đến hai lần, cùng chuyển trạng thái kích hoạt tác vụ thanh toán hai lần.
Một thư viện tích hợp tạo truy vấn SQL qua DSL kiểu an toàn; khi schema đổi tên cột nhưng mã sinh chưa cập nhật, yêu cầu chạy ở production vẫn tham chiếu cột cũ.
Một hệ thống quản trị chuyển biểu thức điều kiện từ DSL sang cây cú pháp trừu tượng; hai toán tử có mức ưu tiên khác nhau bị nhóm xử lý gộp cùng cấp và quy tắc giá không còn đúng.
Một cổng kiểm tra hợp đồng dùng JSON Schema để yêu cầu mã khách và danh sách sản phẩm; payload chứa thêm trường mà một dịch vụ chấp nhận còn dịch vụ khác từ chối vì cách cấu hình schema khác nhau.
Một nền tảng xử lý sự kiện dùng schema khai báo cho trường tùy chọn; khi một phiên bản mới đổi ý nghĩa của giá trị mặc định, những sự kiện cũ được diễn giải sai mà không có lỗi parse.
Một hệ thống phân quyền mô tả allow và deny trong policy DSL; khi hai chính sách đồng thời phù hợp với một tài nguyên, đội phát triển chưa định nghĩa rõ quy tắc kết hợp kết quả.
Một dịch vụ API dùng GraphQL để cho khách khai báo trường dữ liệu cần nhận; truy vấn lồng nhiều tầng quan hệ làm số lần truy cập database tăng mạnh dù payload trả về không lớn.
Một nền tảng phân tích cho phép người dùng nhập truy vấn GraphQL với aliases và nhiều nhánh; cơ chế giới hạn chỉ đếm số trường trên bề mặt nên chi phí truy vấn thực vượt ngân sách đã định.
Một cổng quản lý biểu mẫu mô tả kiểm tra hợp lệ bằng DSL; một điều kiện chỉ áp dụng khi quốc gia là Việt Nam vẫn bị kích hoạt khi người dùng chọn quốc gia khác.
Một hệ thống tạo báo cáo cung cấp template khai báo với biểu thức thay thế dữ liệu; template do khách hàng nhập có thể truy cập trường nhạy cảm không nằm trong hợp đồng báo cáo.
Một công ty áp dụng chính sách phân phối công việc bằng file YAML khai báo; hai nhánh triển khai dùng bộ parser khác nhau và đọc một giá trị kiểu chuỗi thành kiểu dữ liệu không tương thích.
Một nền tảng đào tạo dùng file khai báo để cấu hình pipeline nhiều bước; hai tác vụ có phụ thuộc vào cùng một artifact nhưng dependency graph không biểu diễn quan hệ này nên thứ tự chạy không đảm bảo.
Một nhóm DevOps khai báo ba bản sao của dịch vụ trong Kubernetes Deployment; hệ thống autoscaling đồng thời điều chỉnh số replica khiến cấu hình Git và trạng thái đang chạy liên tục khác nhau.
Một ứng dụng dùng Kubernetes Service với selector khai báo không khớp label của pod; Deployment vẫn đạt số replica mong muốn nhưng toàn bộ request đến service không tìm được endpoint.
Một hệ thống đặt hàng thay ConfigMap trong Git và mong các pod đang chạy tự đọc lại mọi giá trị; sau reconcile, một phần instance tiếp tục dùng cấu hình đã nạp khi khởi động.
Một nền tảng thương mại khai báo readiness probe chỉ kiểm tra cổng HTTP mở; pod được đưa vào nhận traffic dù kết nối database chưa sẵn sàng làm các yêu cầu đầu tiên lỗi.
Một hệ thống triển khai ghi yêu cầu CPU và giới hạn RAM trong manifest; dưới tải đỉnh, pod bị throttling hoặc bị dừng vì vượt bộ nhớ dù desired state vẫn được controller duy trì.
Một đội vận hành sửa trực tiếp cấu hình Deployment để xử lý sự cố; GitOps controller ghi đè thay đổi vào lần đồng bộ tiếp theo khiến lỗi quay trở lại mà không có commit mới.
Một dịch vụ tài chính dùng GitOps để đồng bộ nhiều cụm; một cụm có policy admission chặt hơn khiến cùng một manifest hợp lệ ở staging nhưng bị từ chối ở production.
Một nền tảng chia sẻ dữ liệu khai báo PersistentVolumeClaim cho kho tệp; cấu hình lưu trữ mới không tương thích với volume đã cấp khiến controller không đạt trạng thái mong muốn.
Một công ty dùng Terraform khai báo hạ tầng mạng nhưng kỹ sư thay đổi rule firewall trực tiếp trên cloud; kế hoạch áp dụng tiếp theo đề xuất điều chỉnh ngoài ý định ban đầu của nhóm bảo mật.
Một hệ thống IaC tạo bucket lưu tài liệu rồi sau đó đổi tên tài nguyên logic trong cấu hình; công cụ lập kế hoạch xem đó là thay đổi danh tính và có nguy cơ tác động dữ liệu hiện hữu.
Một nền tảng dùng Terraform state chung cho hai pipeline triển khai; khi chạy đồng thời, thao tác quản lý trạng thái xung đột và một môi trường không nhận được cấu hình mới.
Một nhóm phát triển khai báo tài nguyên cloud có chứa thông tin kết nối nhạy cảm; tệp state và log kế hoạch có thể lưu dữ liệu này trong khi quyền truy cập kho artifact quá rộng.
Một hệ thống tạo Kubernetes Job theo cấu hình desired state để chạy batch; khi Job thất bại và controller thử lại, tác vụ có side effect ghi dữ liệu gây ra bản ghi trùng lặp.
Một dịch vụ triển khai qua Helm dùng giá trị mặc định cho image tag; các môi trường áp dụng cùng chart nhưng kéo các phiên bản image khác nhau khi tag di động được cập nhật.
Một nền tảng phân quyền khai báo NetworkPolicy chặn lưu lượng ngoài nhóm được phép; selector namespace không đúng làm một số pod vẫn truy cập được mạng trái với mong đợi của đội bảo mật.
Một ứng dụng gặp lỗi do cấu hình trường bất biến của tài nguyên Kubernetes bị thay đổi; controller liên tục thử reconcile nhưng không tạo được trạng thái đã khai báo.
Một nền tảng có operator tùy chỉnh reconcile tài nguyên mỗi lần nhận sự kiện; bộ điều khiển luôn ghi lại cùng giá trị dù không có thay đổi khiến vòng lặp reconcile và lượng sự kiện tăng mạnh.
Một công ty dùng manifest Kubernetes để mô tả phiên bản ứng dụng; khi rolling update, yêu cầu sẵn sàng của các pod mới không đạt khiến trạng thái thực tế chỉ được cập nhật một phần.
Một dashboard khai báo giao diện dựa trên trạng thái tìm kiếm nhưng code thay đổi trực tiếp một object lồng nhau; framework không nhận diện thay đổi theo cơ chế quan sát hiện tại nên kết quả không hiển thị.
Một ứng dụng quản lý đơn hàng dùng danh sách thành phần UI được render theo dữ liệu; khi các phần tử thiếu key ổn định, trạng thái chọn của một hàng chuyển sang hàng khác sau khi sắp xếp.
Một cổng hỗ trợ khách hàng dùng binding hai chiều giữa form và model; sự kiện cập nhật từ server và thao tác gõ của người dùng xảy ra gần nhau khiến ô nhập hiển thị giá trị cũ.
Một trang báo cáo mô tả bảng và bộ lọc qua state; tác vụ gọi API được kích hoạt ngay trong quá trình render làm cùng một request được gửi nhiều lần khi framework render lại.
Một ứng dụng web khai báo giao diện đáp ứng với CSS Grid; phần tử có kích thước nội dung tối thiểu lớn hơn vùng chứa khiến bố cục tràn ngang ở màn hình nhỏ dù số cột được mô tả hợp lệ.
Một nền tảng quản trị dùng nhiều selector CSS mô tả màu cảnh báo; quy tắc đặc hiệu và thứ tự nguồn khiến cảnh báo quan trọng không có màu như bộ thiết kế dự kiến.
Một ứng dụng render giao diện phía server rồi hydrate ở trình duyệt; state ban đầu phụ thuộc thời gian hoặc locale của máy khách khiến cây UI khai báo không khớp HTML đã nhận.
Một hệ thống biểu mẫu khai báo trường bắt buộc theo schema nhưng nút gửi dùng trạng thái hợp lệ được cache; khi người dùng xóa dữ liệu, nút vẫn cho gửi yêu cầu không đúng hợp đồng.
Một nền tảng theo dõi trực tiếp hiển thị dữ liệu từ luồng sự kiện và trạng thái mong muốn của UI; một component giữ state cũ sau khi ngắt kết nối nên giao diện báo dữ liệu như còn cập nhật.
Một thư viện component cho phép khai báo hiệu ứng phụ khi một giá trị đổi; dependency được mô tả thiếu khiến hiệu ứng không chạy ở lần thay đổi dữ liệu liên quan tiếp theo.
Một nhóm quản trị chuyển quy trình thủ công sang cấu hình khai báo; khi người dùng thay đổi dữ liệu nguồn trong lúc engine chạy, kết quả không khớp snapshot mà bộ phận kiểm toán kỳ vọng.
Một đội phát triển đo hiệu năng SQL và Stream chỉ bằng số dòng biểu thức khai báo; hệ thống chậm hơn sau thay đổi dù ý nghĩa đầu ra giống nhau vì kế hoạch thực thi và chi phí trung gian khác.
Một nền tảng dùng hai engine để diễn giải cùng một bộ quy tắc DSL; khác biệt về giá trị null, so sánh chuỗi và ép kiểu khiến hai môi trường phân loại cùng hồ sơ thành kết quả khác nhau.
Một cổng quyết định tín dụng xuất kết luận từ bộ quy tắc khai báo; bộ phận kiểm toán yêu cầu biết phiên bản quy tắc và dữ liệu nào dẫn tới quyết định nhưng hệ thống chỉ lưu kết quả cuối.
Một hệ thống orchestration mô tả trạng thái đích của hàng trăm dịch vụ; khi một tài nguyên liên tục bị sửa bởi controller khác, vòng reconcile không hội tụ và số lần ghi tăng mạnh.
Một doanh nghiệp đưa các điều kiện ưu tiên vào rule engine để dễ thay đổi; nhóm QA chỉ kiểm thử một vài đầu vào mẫu và chưa kiểm chứng trường hợp biên, quy tắc xung đột hoặc trạng thái vô nghiệm.
Một đội dữ liệu xem pipeline khai báo là không có tác dụng phụ vì không thấy vòng lặp tường minh; thực tế một phép biến đổi gọi dịch vụ ngoài khiến việc chạy lại dữ liệu gây ra thông báo trùng.
Một cổng vận hành có cấu hình desired state được áp dụng thành công nhưng hệ thống chưa đạt mục tiêu dịch vụ; bộ giám sát chỉ đo trạng thái tài nguyên chứ không đo chức năng nghiệp vụ thực tế.
Một nền tảng phân tích dùng truy vấn khai báo trên dữ liệu lớn rồi chuyển một phần xử lý sang Java Stream; kết quả logic tương tự nhưng sai khác thứ tự, NULL và bộ nhớ làm báo cáo giữa hai nhánh không khớp.
