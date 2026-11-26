Một hệ thống quản lý đơn hàng chuyển từ classpath sang module path nhưng module nghiệp vụ chưa khai báo requires đối với module truy cập dữ liệu; tác vụ biên dịch không còn nhìn thấy lớp JDBC từng dùng bình thường.
Một thư viện thanh toán xuất interface cho ứng dụng khách nhưng không khai báo exports package tương ứng trong module descriptor; module tiêu thụ không thể import API dù JAR đã nằm trên module path.
Một dịch vụ báo cáo khai báo exports package chứa DTO nhưng công cụ serialization dùng reflection để đọc field private; khi triển khai theo JPMS, dữ liệu xuất bị thiếu vì quyền truy cập sâu không được mở.
Một nền tảng xử lý hồ sơ chỉ mở package cho một framework qua opens có đích cụ thể; khi thay framework bằng thư viện khác, thao tác ánh xạ đối tượng gặp lỗi truy cập ở runtime.
Một module API công khai phụ thuộc kiểu trả về thuộc module khác nhưng chỉ khai báo requires thông thường; ứng dụng khách không đọc được module chứa kiểu đó như hợp đồng API ban đầu.
Một dự án chia module thành phần lõi và phần giao diện nhưng để hai package cùng tên ở hai named module; bước phân giải module thất bại khi cả hai được đưa vào cùng cấu hình chạy.
Một nhóm phát triển tạo vòng phụ thuộc requires giữa hai module nghiệp vụ; bản build dừng ở giai đoạn phân giải dù các lớp trước đây gọi lẫn nhau khi dùng classpath.
Một ứng dụng chuyển thư viện của bên thứ ba thành automatic module nhưng phụ thuộc vào tên module suy ra từ tên tệp JAR; sau khi nhà cung cấp đổi tên artifact, module descriptor của ứng dụng không còn phân giải được.
Một hệ thống chạy hai phiên bản dependency có cùng tên module tự động trên module path; JVM không thể xác định ranh giới module theo cấu hình mà đội triển khai đang kỳ vọng.
Một nền tảng tích hợp còn giữ một thư viện trên classpath và đưa module nghiệp vụ lên module path; module có tên cố sử dụng lớp chỉ nằm trong unnamed module nên không biên dịch như trước.
Một dịch vụ quản lý tài sản đặt JAR modular trên classpath nhưng tưởng exports và requires được áp dụng đầy đủ; chương trình chạy khác kết quả kiểm tra ranh giới phụ thuộc trên module path.
Một thư viện kiểm tra dữ liệu khai báo requires static cho module annotation tùy chọn; khi chạy tính năng thực sự cần lớp trong module đó, một số môi trường không có dependency và gặp lỗi tải kiểu.
Một cổng API dùng exports chỉ định một module tiêu thụ nhưng nhóm phát triển thêm ứng dụng quản trị khác; module mới không thể truy cập package mặc dù lớp bên trong đều public.
Một công cụ DI dùng setAccessible với constructor private của lớp trong named module; sau khi chuyển từ classpath sang module path, request đầu tiên phát sinh InaccessibleObjectException.
Một nền tảng plugin truyền ClassLoader riêng để tải lớp theo tên rồi cố gọi method public từ package không exports; thao tác reflection vẫn bị hạn chế bởi ranh giới module dù phương thức có modifier public.
Một hệ thống khởi động thêm tùy chọn mở package cho mọi module để chữa lỗi reflection; sau đó plugin không đáng tin cậy cũng có khả năng truy cập sâu vào nội bộ vốn chỉ dành cho một framework.
Một dịch vụ backend triển khai module descriptor chỉ liệt kê requires trực tiếp, nhưng một library thực hiện nạp lớp bằng tên ở runtime; jdeps chưa phản ánh hết phụ thuộc động và sản phẩm lỗi khi cắt giảm module.
Một nền tảng xử lý ảnh dùng ServiceLoader trong named module nhưng không khai báo uses cho SPI; khi khởi chạy trên module path, tác vụ phát hiện provider không thành công.
Một ứng dụng công bố SPI trong module riêng nhưng module triển khai không khai báo provides tương ứng; provider chạy được trên classpath cũ nhưng biến mất khi thử nghiệm JPMS.
Một công cụ ký số đặt provider ở module phụ thuộc nhưng module đó không được phân giải vào cấu hình chạy; ServiceLoader trả danh sách trống dù file provider đã có trong bộ cài.
Một nền tảng thay đổi ModuleLayer để nạp plugin trong runtime; provider thuộc layer mới không xuất hiện khi code khám phá service chỉ xét layer khởi động.
Một cổng quản lý module tạo layer mới có class loader riêng; đối tượng implement cùng tên interface với layer khác không thể ép kiểu như giả định của hệ thống plugin.
Một bộ công cụ quản trị dùng Module.getResourceAsStream để đọc cấu hình nội bộ; sau khi tổ chức lại vị trí resource và package, đường dẫn từng hợp lệ không còn tìm thấy tệp.
Một dự án đưa các lớp tiện ích không có package vào một named module; javac từ chối cách bố trí này dù chúng từng chạy được trong ứng dụng nhỏ trên classpath.
Một nền tảng dùng reflection để phân tích generic và annotation của thư viện ngoài; sau khi đóng gói JPMS, khả năng đọc metadata vẫn có nhưng quyền tạo instance private lại không được cấp.
Một hệ thống có module riêng chỉ mở một package qua opens và module khác chỉ xuất API qua exports; đội tích hợp nhầm hai quyền này nên kiểm thử biên dịch và kiểm thử serialization cho kết quả trái ngược.
Một thư viện hỗ trợ nhiều bản Java xây multi-release JAR chứa lớp được tối ưu cho JDK hiện đại; khi thay cấu trúc phiên bản bên trong artifact, bản chạy trên JDK khác chọn implementation không như đội kiểm thử dự kiến.
Một đội triển khai sử dụng jdeps để liệt kê phụ thuộc module trước khi nâng JDK; thư viện truy cập dịch vụ bằng ServiceLoader và class name cấu hình không được thể hiện đầy đủ trong báo cáo phụ thuộc tĩnh.
Một ứng dụng ERP đổi từ thư viện nguyên khối sang nhiều JPMS module nhưng vẫn giữ các package dùng chung và reflection xuyên module; sau khi nâng cấp, chỉ một vài endpoint lỗi khi truy cập metadata nội bộ.
Một cổng thương mại tạo danh sách trạng thái đơn bằng List.of rồi cố thêm trạng thái tạm trong bước hiển thị; lỗi UnsupportedOperationException chỉ xuất hiện khi người dùng bật bộ lọc nâng cao.
Một hệ thống cấu hình dùng List.of chứa giá trị null để đại diện trường chưa thiết lập; bước khởi động thất bại dù danh sách Java có thể sửa trước đó chấp nhận cách biểu diễn này.
Một dịch vụ tạo Set.of từ các mã quyền cấu hình và dữ liệu chứa hai mã trùng nhau; constructor ném IllegalArgumentException khi triển khai cấu hình từ một tenant cụ thể.
Một cổng tổng hợp khuyến mãi dùng Map.of với khóa trùng nhau sau khi gộp hai danh sách; bộ tạo map thất bại trước khi màn hình quản trị hiển thị kết quả.
Một ứng dụng đặt hàng chuyển sang Map.of để công bố bảng giá cố định; quy trình nhập hàng vẫn gọi put trên map này nên bị từ chối khi một nhà cung cấp đổi giá.
Một nền tảng dữ liệu tạo Map.ofEntries từ danh sách bản ghi và gặp giá trị null của một thuộc tính tùy chọn; một batch nhập dữ liệu cũ bắt đầu lỗi ở bước đóng gói kết quả.
Một dịch vụ báo cáo xuất danh mục từ Set.of theo thứ tự đã nhập; thứ tự duyệt tập không được cam kết khiến các bản CSV phát hành có thứ tự cột không nhất quán.
Một hệ thống lưu quyền người dùng lấy các đối tượng mutable trong List.of và xem danh sách như snapshot bất biến; sau khi một tác vụ khác sửa phần tử, nội dung quyền đã công bố cũng thay đổi.
Một thư viện kiểm thử dựa vào hai lần gọi List.of tạo ra hai instance độc lập; phép kiểm tra identity không phù hợp với hợp đồng của các collection factory và có kết quả khó dự đoán.
Một cổng nhập mã sản phẩm dùng Map.entry để tạo danh sách entry trước khi gộp map; khi khóa hoặc giá trị chưa có dữ liệu, việc dựng entry phát sinh lỗi.
Một dịch vụ quản lý tồn kho chuyển cấu hình lớn sang Map.of nhưng vượt giới hạn số cặp key-value của các overload thông thường; bản build không chọn được phương thức tương ứng.
Một ứng dụng nhận JSON và lưu thuộc tính trong collection factory bất biến; bộ phận cập nhật dữ liệu vẫn coi đối tượng trả về là collection có thể sửa và chỉ lỗi với nhánh chỉnh sửa.
Một nền tảng phân tích xử lý luồng giao dịch đã sắp theo thời gian bằng Stream.takeWhile; khi gặp giao dịch đầu tiên ngoài khoảng, phần còn lại không được xem xét dù trong nguồn có bản ghi hợp lệ nằm sau.
Một dịch vụ lọc giá dùng takeWhile trên stream phát sinh từ HashSet không có thứ tự đảm bảo; tập phần tử được giữ thay đổi giữa các lần chạy và không phản ánh điều kiện lọc toàn cục.
Một ứng dụng xử lý log dùng Stream.dropWhile để bỏ phần header; khi một dòng dữ liệu giống header xuất hiện ở giữa luồng, nhóm vận hành nhầm rằng nó cũng sẽ bị loại.
Một bộ phân tích dữ liệu dùng dropWhile trên stream không có encounter order cố định; số phần tử bị bỏ thay đổi khi pipeline chạy song song.
Một ứng dụng tổng hợp giao dịch truyền stream vô hạn vào takeWhile với điều kiện không bao giờ sai; tác vụ tiếp tục đọc dữ liệu thay vì kết thúc trong khoảng thời gian mà đội vận hành dự kiến.
Một nền tảng lập lịch dùng Stream.iterate với điều kiện dừng để sinh các mốc ngày; khi ranh giới bằng ngày cuối cùng, lịch xuất ra thiếu một mốc vì nhóm phát triển không kiểm tra điều kiện bao gồm biên.
Một dịch vụ nghiên cứu tạo dữ liệu bằng Stream.iterate có predicate phụ thuộc vào trạng thái mutable; khi bật xử lý song song, tập giá trị sinh ra không còn khớp giả định về tính thuần của pipeline.
Một công cụ nhập danh bạ tạo Stream.ofNullable từ một trường thiếu dữ liệu; bước thu thập phía sau chỉ nhận stream rỗng và một bản ghi bị loại mà không có log về nguyên nhân.
Một nền tảng báo cáo dùng Stream.ofNullable để chuyển giá trị tùy chọn thành stream; nhóm phát triển kỳ vọng luôn nhận một phần tử nên phép thống kê số bản ghi đầu vào bị sai.
Một dịch vụ khách hàng dùng Optional.stream để gộp kết quả nhiều truy vấn; khi kết quả rỗng, số phần tử đầu ra nhỏ hơn số truy vấn và thuật toán ghép theo chỉ số bị lệch.
Một ứng dụng đặt vé dùng Optional.ifPresentOrElse để hiển thị vé hoặc cảnh báo; nhánh cảnh báo thực hiện I/O ném exception và đội phát triển tưởng API sẽ tự chuyển sang giá trị dự phòng.
Một hệ thống tải cấu hình dùng Optional.or để lấy cấu hình thay thế; supplier truy vấn nguồn phụ bị lỗi khi cấu hình chính rỗng nhưng cơ chế khôi phục không ghi rõ lỗi bắt nguồn từ đâu.
Một nền tảng phân phối sản phẩm truyền supplier có side effect vào Optional.or; kiểm thử kỳ vọng supplier được gọi ở mọi lượt nên bỏ sót trường hợp cấu hình chính đã có giá trị.
Một công cụ sinh danh sách thông báo kết hợp Optional.stream với flatMap; sau nâng cấp, nhóm QA chưa kiểm tra các trường hợp tất cả Optional rỗng và số phần tử thực tế bằng không.
Một dịch vụ thực hiện pipeline Stream song song với takeWhile và dropWhile trên dữ liệu lớn có thứ tự; throughput suy giảm vì phép xử lý phải tôn trọng encounter order trong những trường hợp biên.
Một ứng dụng chuyển kết quả API thành Optional và dùng ifPresentOrElse để gửi thông báo; khi một nhánh không nhận được bản ghi, hành động thông báo trùng lặp do xử lý retry không có idempotency.
Một hệ thống cảm biến dùng Flow.Publisher để phát dữ liệu liên tục nhưng Subscriber không gọi request trên Subscription; luồng xử lý kết nối thành công mà không nhận được bản tin nào.
Một cổng thu thập sự kiện gọi request với số lượng âm để điều chỉnh tốc độ; publisher báo lỗi theo hợp đồng Flow và subscriber không còn tiếp tục nhận dữ liệu.
Một nền tảng giám sát Subscriber gọi request(Long.MAX_VALUE) ngay khi subscribe để bỏ giới hạn; khi nguồn phát quá nhanh, bộ xử lý không kịp xử lý và hàng đợi nội bộ tăng.
Một ứng dụng thương mại dùng SubmissionPublisher.submit liên tục để gửi sự kiện trong giờ cao điểm; tốc độ subscriber chậm khiến thread phát bị chặn do bộ đệm đạt giới hạn.
Một dịch vụ thanh toán phát bản ghi qua SubmissionPublisher nhưng đóng publisher ngay sau khi gửi dữ liệu; bộ kiểm thử chưa kiểm chứng tất cả subscriber nhận tín hiệu hoàn thành và số bản ghi thực tế.
Một hệ thống thông báo tạo Subscriber rồi quên lưu Subscription để hủy khi người dùng thoát; sự kiện tiếp tục gửi đến đối tượng không còn phiên giao diện hợp lệ.
Một cổng xử lý đơn hàng tự xây Flow.Publisher gửi onNext đồng thời từ nhiều thread cho cùng một Subscriber; state của bộ đọc bị cập nhật tranh chấp và thứ tự thông điệp khác hợp đồng.
Một ứng dụng lập chỉ mục tiếp tục gọi onNext sau onComplete khi đóng nguồn dữ liệu; một phần subscriber ghi log sự kiện không hợp lệ và từ chối kết quả đã xử lý.
Một hệ thống giám sát có Subscriber ném lỗi từ onNext; publisher không có chiến lược báo lỗi phù hợp làm một chuỗi sự kiện bị ngắt mà đội vận hành chỉ thấy thiếu số liệu.
Một nền tảng xử lý ảnh nối Flow.Processor ở giữa publisher và subscriber; processor chỉ chuyển dữ liệu nhưng không chuyển tín hiệu hủy nên nguồn vẫn xử lý ảnh sau khi người dùng hủy tác vụ.
Một dịch vụ telemetry dùng SubmissionPublisher với executor chung cho các tác vụ CPU nặng; khi tải cao, việc giao sự kiện tới subscriber bị trì hoãn dù publisher còn dung lượng bộ đệm.
Một ứng dụng điều phối dựa vào giá trị ước lượng độ trễ từ SubmissionPublisher.submit để quyết định sự kiện nào đã được xử lý; dashboard báo hoàn thành khi nhiều subscriber vẫn đang chờ.
Một cổng dữ liệu dùng SubmissionPublisher.offer với chính sách bỏ sự kiện khi đầy buffer; số bản tin nhận được thấp hơn số bản tin gửi nhưng hệ thống không ghi nhận tỷ lệ mất.
Một hệ thống thương mại tạo nhiều Subscriber cho cùng Flow.Publisher nhưng một subscriber không xử lý request đúng; hiệu năng của các consumer khác bị ảnh hưởng trong mô hình phân phối đang dùng.
Một dịch vụ xử lý cảnh báo cho phép subscriber gọi cancel sau khi đã nhận tín hiệu lỗi; các tác vụ cleanup không quản lý đúng trạng thái Subscription và để lại tham chiếu lâu dài.
Một ứng dụng đo cảm biến chuyển từ listener callback sang Flow nhưng bộ kiểm thử chỉ chạy một subscriber; lỗi backpressure và hoàn tất tín hiệu xuất hiện khi có nhiều subscriber với tốc độ khác nhau.
Một nhóm phát triển dùng JShell để kiểm tra nhanh các biểu thức xử lý đơn hàng; mã chạy được trong phiên tương tác nhưng bản build production không có các import và dependency giống môi trường JShell.
Một cổng đào tạo khởi chạy JShell với classpath từ máy lập trình viên; khi CI chạy trong container sạch, các ví dụ phụ thuộc vào thư viện ngoài không còn biên dịch.
Một thư viện dạy Java chạy lệnh JShell theo từng đoạn; khi người học đặt lại tên biến trong snippet sau, các câu lệnh đã lưu trước đó không còn hoạt động như màn hình ví dụ ban đầu.
Một nhóm vận hành dùng JShell để kiểm tra phương thức private của ứng dụng; khi chuyển sang named module, quyền reflection vẫn bị giới hạn và kết quả thử nghiệm khác trên classpath.
Một nền tảng kiểm tra bài tập dùng API JShell đánh giá đoạn mã do người dùng gửi; nhóm bảo mật tưởng rằng kiểm tra cú pháp và chạy trong JShell đồng nghĩa mã đã được cách ly khỏi tài nguyên máy chủ.
Một ứng dụng huấn luyện tạo nhiều phiên JShell trong cùng JVM nhưng không đóng các phiên cũ; số tiến trình và tài nguyên hỗ trợ thực thi tăng sau nhiều lượt nộp bài.
Một công cụ đào tạo thu thập kết quả từ JShell.eval và chỉ hiển thị giá trị của snippet cuối; các sự kiện lỗi và chẩn đoán biên dịch ở snippet trước không được báo cho học viên.
Một nền tảng thử nghiệm sử dụng JShell để nhập một package từ module không được phân giải; câu lệnh import thất bại dù JAR tương ứng đã xuất hiện trong thư mục ứng dụng.
Một nhóm QA dùng JShell để kiểm chứng API của phiên bản JDK đang cài; tài liệu phát hành lại tuyên bố mọi kết quả tương thích với runtime LTS cũ mà chưa chạy kiểm tra ở phiên bản đó.
Một dịch vụ tạo runtime image bằng jlink từ đồ thị module chính rồi nạp plugin ghi log qua classpath lúc chạy; plugin không khởi động được vì module java.logging không có trong image rút gọn.
Một nền tảng xử lý ảnh dùng jlink để tạo image nhỏ nhưng bỏ các provider cần thiết của ServiceLoader; tính năng giải mã một định dạng hiếm không còn hoạt động sau đóng gói.
Một ứng dụng phân phối bộ cài jlink cho Linux và sao chép nguyên runtime image đó sang Windows; tiến trình không khởi động được vì image phụ thuộc nền tảng đích.
Một hệ thống thương mại chạy được với JDK đầy đủ nhưng image do jlink tạo thiếu module charset hoặc tài nguyên locale cần cho khách quốc tế; một phần văn bản đa ngôn ngữ hiển thị sai.
Một cổng ngân hàng tạo runtime image qua jlink rồi bật tính năng TLS mới; cấu hình provider bảo mật không được mang sang image rút gọn đúng cách khiến kết nối tới đối tác thất bại.
Một dịch vụ quản trị dùng jlink để giảm kích thước container nhưng sau đó cần JavaCompiler tại runtime; image không chứa jdk.compiler nên chức năng biên dịch động không thể sử dụng.
Một ứng dụng dùng jlink với module tự động tạo từ thư viện cũ; công cụ không chấp nhận cấu hình module theo cách đội phát triển kỳ vọng và pipeline đóng gói bị dừng.
Một hệ thống phát hành tạo image jlink trước khi dependency runtime được bổ sung; khi triển khai plugin mới, module không tồn tại trong image dù bản build đầy đủ đã đưa JAR vào gói bổ sung.
Một nhóm DevOps giảm kích thước image với tùy chọn của jlink nhưng không chạy kiểm thử khởi động thực tế; thao tác lấy resource và certificate hoạt động khác trên JDK đầy đủ.
Một nền tảng thương mại xây runtime image bằng jlink từ JDK khác với bản dùng để compile; trong production, lỗi tương thích giữa bytecode, module graph và runtime chỉ xuất hiện khi chạy một tính năng hiếm.
Một dịch vụ triển khai cố tính thời gian sống của tiến trình con từ ProcessHandle.info; một số giá trị thông tin không có trên hệ điều hành đích nên màn hình quản trị không có dữ liệu như mong đợi.
Một ứng dụng xử lý video đăng ký ProcessHandle.onExit để dọn tệp tạm; khi tiến trình con treo lâu, callback không hoàn tất và tệp tạm tích lũy qua nhiều lần xử lý.
Một công cụ thực thi job dùng ProcessHandle.descendants để tìm tất cả tiến trình con; khi cây tiến trình thay đổi đồng thời, dữ liệu nhận được không đủ để xác định chính xác những tiến trình cần giám sát.
Một hệ thống kiểm toán dùng StackWalker để tìm lớp gọi nghiệp vụ; cấu hình StackWalker thiếu tùy chọn giữ Class reference làm truy xuất caller class không đáp ứng yêu cầu.
Một thư viện ghi log dùng StackWalker để xác định nguồn lỗi và lấy nhiều stack frame; khi gọi trong đường xử lý nóng, chi phí thu thập stack làm độ trễ request tăng.
Một ứng dụng cập nhật bộ đếm đồng thời dùng VarHandle truy cập field nhưng chọn access mode không phù hợp với quy tắc hiển thị bộ nhớ; hai thread hiếm khi nhìn thấy trạng thái theo thứ tự mong đợi.
Một nền tảng dữ liệu dùng VarHandle compareAndSet để thay số dư khi nhiều worker cùng cập nhật; bộ xử lý không kiểm tra thất bại do cạnh tranh nên một số thay đổi hợp lệ bị bỏ qua.
Một dịch vụ chạy CompletableFuture.orTimeout cho tác vụ gọi đối tác; khi chạm thời hạn, giao diện nhận lỗi timeout nhưng công việc I/O phía dưới chưa chắc đã thực sự ngừng.
Một công cụ gửi email dùng CompletableFuture.completeOnTimeout để tạo giá trị dự phòng; thao tác mạng vẫn chạy tiếp làm số email được gửi không khớp số lần màn hình báo đã hoàn thành.
Một thư viện hỗ trợ các API Java 9 nhưng còn khách hàng chạy Java 8; module được build bằng JDK hiện đại không dùng --release thích hợp nên một số method gọi được ở CI nhưng thiếu khi triển khai trên runtime cũ.
