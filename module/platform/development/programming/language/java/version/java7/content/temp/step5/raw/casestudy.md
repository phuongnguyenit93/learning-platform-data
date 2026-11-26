Một dịch vụ nhập dữ liệu CSV phải đọc nhiều tệp liên tiếp và có thể gặp lỗi phân tích giữa chừng; hãy phân tích cách thiết kế vòng đời tài nguyên để không rò rỉ file handle khi xử lý thất bại.
Một API xuất báo cáo vừa ghi dữ liệu vừa nén ra tệp đích, trong đó các luồng có quan hệ bọc lồng nhau; hãy xác định yêu cầu quản lý quyền sở hữu và thứ tự đóng tài nguyên khi có ngoại lệ.
Một batch job mở đồng thời kết nối cơ sở dữ liệu, câu lệnh và tập kết quả, nhưng một bước truy vấn có thể thất bại; hãy đặt ra tình huống kiểm chứng mọi tài nguyên được giải phóng trên các nhánh thực thi.
Một bộ tải tệp cần bảo đảm cả lỗi đọc nội dung và lỗi đóng stream đều được ghi nhận mà không đánh mất nguyên nhân chính; hãy phân tích hợp đồng báo lỗi cho trường hợp này.
Một ứng dụng desktop ghi cấu hình qua writer và phải xử lý ngoại lệ ngay cả khi dữ liệu đã được ghi thành công nhưng thao tác đóng tài nguyên thất bại; hãy mô tả các kết quả cần phân biệt.
Một thư viện nhận InputStream do người gọi truyền vào, trong khi phương thức xử lý tự tạo thêm reader bên ngoài; hãy xác định trách nhiệm đóng tài nguyên khi API được dùng bởi nhiều nhóm.
Một chương trình xử lý ảnh cần khóa tài nguyên thiết bị qua đối tượng tùy chỉnh và giải phóng ngay khi thoát một khối thao tác; hãy đặt yêu cầu về giao diện tài nguyên và hành vi khi cleanup thất bại.
Một công cụ di chuyển dữ liệu phải chạy tác vụ tạo tệp tạm, đọc tệp gốc rồi ghi kết quả và có thể dừng ở bất kỳ bước nào; hãy xác định những trạng thái và tài nguyên cần kiểm soát.
Một job ETL bỏ qua lỗi định dạng từng bản ghi nhưng không được bỏ qua lỗi mở hoặc đóng tệp dữ liệu; hãy thiết kế các trường hợp kiểm thử đường lỗi và đường hoàn tất.
Một hệ thống log sử dụng nhiều AutoCloseable trong một thao tác và cần giữ thứ tự giải phóng nhất quán dù khởi tạo tài nguyên thứ hai thất bại; hãy mô tả tình huống lỗi cần tái hiện.
Một chương trình sao lưu truyền file handle qua nhiều tầng và có nguy cơ cả caller lẫn callee cùng đóng; hãy phân tích yêu cầu xác định chủ sở hữu tài nguyên trước khi triển khai.
Một nhóm phát triển nâng cấp mã cũ có hàng loạt khối finally đóng tài nguyên với nguy cơ làm che lỗi gốc; hãy nêu bài toán refactor mà vẫn giữ nguyên hợp đồng exception của API.
Một dịch vụ mở hàng chục nghìn tệp nhỏ trong một ngày và thỉnh thoảng báo quá giới hạn file descriptor; hãy xây dựng bối cảnh chẩn đoán rò rỉ tài nguyên và yêu cầu đo lường.
Một quy trình ghi tài liệu PDF gặp lỗi trong phần ghi nội dung nhưng việc đóng output cũng ném lỗi; hãy đặt các yêu cầu kiểm tra exception chính và danh sách lỗi kèm theo.
Một job đọc kho dữ liệu lớn có nhiệm vụ tự hủy khi client ngắt kết nối; hãy phân tích cách bảo đảm tài nguyên được đóng dù luồng điều khiển bị gián đoạn.
Một thư viện chuyển đổi file sử dụng đối tượng AutoCloseable do bên thứ ba cung cấp và không rõ việc close có đồng thời flush; hãy đặt ra các test kiểm chứng tính toàn vẹn file đầu ra.
Một dịch vụ nhập đơn hàng nhận cả lỗi định dạng số và lỗi đọc tệp cần cùng một quy trình phản hồi, trong khi lỗi xác thực dữ liệu phải xử lý riêng; hãy mô tả bài toán phân nhóm ngoại lệ phù hợp.
Một hàm đọc cấu hình có thể gặp nhiều loại ngoại lệ không liên quan nhưng đều cần gắn chung correlation ID trước khi truyền lên tầng trên; hãy phân tích cách tránh mất thông tin nguyên nhân.
Một API thư viện hiện có hợp đồng khai báo ngoại lệ hẹp, nhưng code nâng cấp phải bắt lại rồi ném tiếp các lỗi từ hai nhánh khác nhau; hãy đánh giá yêu cầu giữ chính xác kiểu ngoại lệ công khai.
Một ứng dụng batch đang lặp lại cùng một khối xử lý cho nhiều loại lỗi I/O và parsing, khiến thông báo thiếu nhất quán; hãy xác định mục tiêu refactor mà không vô tình thay đổi đường phục hồi.
Một quy trình giao dịch cần retry khi lỗi mạng tạm thời nhưng phải dừng khi vi phạm ràng buộc dữ liệu; hãy xây dựng tình huống phân loại exception và ngăn retry sai.
Một hàm kiểm tra file có cả lỗi quyền truy cập và lỗi không tồn tại, nhưng hai tình huống dẫn tới quyết định nghiệp vụ khác nhau; hãy đặt yêu cầu lựa chọn cấu trúc xử lý ngoại lệ.
Một người bảo trì đề xuất thay nhiều catch bằng một multi-catch rồi sửa trực tiếp biến exception trong khối xử lý; hãy nêu vấn đề cần phát hiện qua kiểm tra biên dịch và hợp đồng ngôn ngữ.
Một dịch vụ phân tích JSON muốn gộp các loại lỗi thành thông báo thống nhất nhưng vẫn giữ khả năng phân loại lỗi gốc ở tầng monitoring; hãy đặt bài toán thiết kế đường truyền exception.
Một thư viện legacy chứa các khối catch lồng nhau khiến một lỗi bị bắt ở nhánh quá rộng trước nhánh cụ thể; hãy xây dựng kịch bản kiểm tra hành vi trước và sau khi tinh gọn.
Một hệ thống kiểm soát truy cập tệp muốn ghi nhận lỗi từ hai loại IOException chuyên biệt và phản hồi khác nhau tùy mã lỗi; hãy xác định yêu cầu kiểm thử khi thay đổi cách bắt ngoại lệ.
Một codebase Java lớn có nhiều lời gọi khởi tạo collection generic với kiểu lặp lại ở cả hai vế, và nhóm muốn rút gọn cú pháp; hãy nêu tình huống đánh giá tính dễ đọc và mức ngôn ngữ tối thiểu.
Một thư viện public dùng constructor generic trong nhiều ngữ cảnh overload, và việc rút gọn kiểu làm kết quả biên dịch thay đổi; hãy phân tích yêu cầu kiểm tra kiểu được suy luận sau refactor.
Một framework xử lý sự kiện có một đoạn code cũ dùng anonymous class generic cần nâng cấp trên JDK hiện đại; hãy đặt bài toán phân biệt giới hạn cú pháp Java 7 với cú pháp đã phát triển sau đó.
Một ứng dụng quản lý mã sản phẩm có logic rẽ nhánh theo các giá trị String do khách hàng gửi, bao gồm chữ hoa, chữ thường và null; hãy xây dựng trường hợp kiểm thử đầy đủ khi đổi cách phân nhánh.
Một dịch vụ phân loại định dạng tài liệu dùng nhánh xử lý theo phần mở rộng chuỗi, nhưng dữ liệu có thể bị chuẩn hóa khác nhau; hãy mô tả yêu cầu tránh chọn sai đường xử lý.
Một hệ thống thiết bị ghi cờ trạng thái dưới dạng các bit và lập trình viên muốn các literal dễ đọc hơn; hãy nêu bài toán kiểm tra các giá trị âm, bit cao và giới hạn kiểu số.
Một cấu hình ngân sách chứa các literal số nguyên rất lớn với dấu phân tách cho dễ đọc và đã gây lỗi khi đặt dấu sai vị trí; hãy xây dựng yêu cầu review mã và kiểm thử biên dịch.
Một công cụ nhập dữ liệu chuyển đổi số nhị phân từ cấu hình thành các bit flag, rồi áp dụng toán tử mask; hãy đặt tình huống kiểm tra phép dịch bit và vấn đề tràn kiểu.
Một thư viện còn hỗ trợ nhiều mức JDK dùng các cú pháp được giới thiệu từ Java 7 và được biên dịch bằng JDK rất mới; hãy mô tả cách kiểm chứng source level và API level không vượt phạm vi cam kết.
Một dịch vụ nhận đường dẫn do người dùng gửi có thể chạy trên Windows và Linux; hãy phân tích yêu cầu xây dựng, chuẩn hóa và kiểm tra Path mà không giả định ký tự phân tách cố định.
Một ứng dụng xuất báo cáo phải kết hợp thư mục cấu hình với tên file đến từ người dùng và không cho ghi ra ngoài vùng làm việc; hãy đặt tình huống kiểm tra traversal và phạm vi đường dẫn hợp lệ.
Một hệ thống đồng bộ cần so sánh hai đường dẫn có thể khác nhau về thành phần tương đối, symlink hoặc cách viết tên; hãy xác định yêu cầu phân biệt so sánh cú pháp và xác định cùng file thực tế.
Một chương trình quản lý bản dựng phải tìm đường dẫn gốc và phần tử cuối cùng của tệp cấu hình trên nhiều hệ điều hành; hãy mô tả các trường hợp đường dẫn rỗng, tương đối và có root.
Một service đọc file cấu hình bằng Path nhưng thư mục làm việc của tiến trình có thể thay đổi giữa môi trường phát triển và production; hãy nêu yêu cầu xác định đường dẫn dựa trên vị trí rõ ràng.
Một ứng dụng chuyển dữ liệu giữa hai ổ đĩa hoặc file system provider khác nhau và đang phụ thuộc vào thuộc tính cụ thể của filesystem; hãy đặt bài toán kiểm chứng tính di động của thao tác tệp.
Một job xử lý tài liệu phải kiểm tra trước khi mở file xem có tồn tại nhưng file có thể biến mất ngay sau kiểm tra; hãy mô tả tình huống race condition cần được xử lý.
Một dịch vụ cho phép người dùng chọn thư mục tải xuống có thể đang bị thay bằng symbolic link giữa hai thao tác; hãy xây dựng kịch bản kiểm soát đường dẫn an toàn.
Một công cụ tìm file theo mẫu glob phải hoạt động với tên chứa dấu cách, ký tự Unicode và ký tự đặc biệt; hãy đặt yêu cầu kiểm thử PathMatcher theo từng filesystem.
Một ứng dụng lưu trữ cần tạo cây thư mục theo năm, tháng và ngày với nhiều tiến trình cạnh tranh tạo cùng nhánh; hãy mô tả trường hợp idempotence và lỗi phân quyền.
Một hệ thống nhập file thường phải ghi ra thư mục mới nhưng thư mục cha có thể chưa tồn tại và đôi khi là tệp thông thường; hãy đặt tình huống xử lý khác nhau cho từng trạng thái.
Một dịch vụ tạo file cấu hình không được vô tình ghi đè bản cấu hình đang dùng khi có hai worker cùng khởi tạo; hãy mô tả yêu cầu thao tác tạo file và kiểm thử cạnh tranh.
Một pipeline nhận tệp upload muốn ghi dữ liệu ra tệp tạm rồi công bố thành tệp chính thức chỉ khi toàn bộ nội dung hợp lệ; hãy xây dựng tình huống kiểm soát lỗi và tính nguyên tử.
Một hệ thống xuất hóa đơn phải di chuyển tệp tạm sang đường dẫn công khai nhưng triển khai có thể nằm trên các filesystem khác nhau; hãy đặt yêu cầu về atomic move và phương án khi không được hỗ trợ.
Một job sao lưu muốn chép file có hoặc không có metadata tùy cấu hình nghiệp vụ và đích có thể đã tồn tại; hãy mô tả tình huống kiểm thử các chính sách sao chép.
Một ứng dụng di chuyển dữ liệu cần phân biệt thay đổi tên trên cùng ổ đĩa với sao chép–xóa giữa hai ổ; hãy đặt bài toán phân tích rủi ro khi thao tác move thất bại giữa chừng.
Một chương trình dọn bộ nhớ đệm xóa các tệp cũ trong thư mục nhưng phải tránh xóa tệp mới phát sinh sau lúc quét; hãy mô tả yêu cầu kiểm tra dấu thời gian và concurrency.
Một ứng dụng đọc file cấu hình có thể nhận dữ liệu UTF-8 hoặc định dạng cũ được khai báo tường minh; hãy đặt tình huống không phụ thuộc charset mặc định của tiến trình.
Một bộ nhập CSV cần xử lý file hàng gigabyte mà không giữ toàn bộ dữ liệu trong bộ nhớ; hãy mô tả yêu cầu về cách đọc theo dòng và đóng tài nguyên khi người dùng hủy tác vụ.
Một dịch vụ ghi log cần bổ sung dòng vào file liên tục nhưng cũng có tiến trình khác đọc file; hãy xây dựng tình huống phân biệt append, truncate và create theo hợp đồng OpenOption.
Một chương trình phân tích văn bản đọc hàng triệu dòng và có thể phát sinh IOException ở giữa luồng; hãy đặt bài toán báo lỗi, dừng đọc và giải phóng resource đúng thời điểm.
Một dịch vụ xử lý file ZIP nhận dữ liệu từ khách hàng và muốn duyệt entry qua filesystem provider; hãy xác định điều kiện môi trường, bảo mật đường dẫn và vòng đời provider cần kiểm tra.
Một ứng dụng truy cập dữ liệu trong hệ thống tệp ảo qua FileSystemProvider cần tránh giả định mọi thao tác đều hỗ trợ như đĩa cục bộ; hãy nêu các trường hợp kiểm thử tính năng và ngoại lệ.
Một công cụ sao lưu phải thống kê tổng số tệp và dung lượng trong cây thư mục rất lớn mà không làm tăng heap tuyến tính theo toàn bộ danh sách; hãy mô tả bài toán duyệt cây có kiểm soát.
Một tiện ích quét antivirus cần bỏ qua nhánh thư mục không có quyền đọc, ghi nhận lỗi nhưng vẫn tiếp tục các nhánh còn lại; hãy xây dựng tình huống duyệt cây và báo cáo lỗi.
Một bộ tìm kiếm tài liệu quét cây thư mục có symbolic link trỏ ngược về thư mục cha; hãy mô tả yêu cầu tránh vòng lặp vô hạn và xử lý sự kiện chu trình.
Một công cụ quản lý media có chính sách chỉ duyệt thư mục thực, không lần theo symbolic link; hãy xác định cách kiểm thử với đường dẫn liên kết hợp lệ và liên kết gãy.
Một chương trình xuất danh sách tệp cần lọc theo độ sâu thư mục và không được quét toàn bộ cây khi người dùng giới hạn phạm vi; hãy mô tả bài toán tối ưu traversal.
Một ứng dụng đồng bộ thư mục muốn chọn file theo kích thước và thời điểm sửa, trong khi file có thể đổi sau khi lấy metadata; hãy đặt yêu cầu kiểm soát tính nhất quán.
Một hệ thống dọn dữ liệu phải xóa cây thư mục chứa tệp read-only và symlink mà không chạm tới vị trí ngoài thư mục gốc; hãy xây dựng các tình huống lỗi và kiểm chứng hậu điều kiện.
Một job kiểm tra phân quyền cần lấy quyền POSIX trên Linux nhưng chạy thử trên Windows; hãy mô tả tình huống kiểm tra hỗ trợ attribute view và xử lý khi không có.
Một công cụ quản trị Windows cần xem ACL của file trước khi quyết định có cập nhật quyền không; hãy đặt yêu cầu đánh giá đúng FileAttributeView và nguyên tắc quyền tối thiểu.
Một chương trình phát hiện thay đổi file dựa trên `lastModifiedTime` nhưng filesystem có độ phân giải thời gian khác nhau; hãy mô tả bài toán tránh bỏ sót cập nhật sát nhau.
Một dịch vụ phát hành artifact cần xác thực tệp đích có đúng là regular file, không phải directory hoặc symbolic link; hãy nêu kịch bản kiểm tra thuộc tính và race condition.
Một ứng dụng kho ảnh lưu cả tệp gốc và symlink để tiết kiệm dung lượng, nhưng thao tác copy có yêu cầu khác nhau với mỗi loại; hãy xây dựng tình huống phân biệt sao chép liên kết và nội dung.
Một phần mềm kiểm tra tính toàn vẹn dùng nội dung file và metadata trước khi ký số, trong khi một tiến trình khác có thể chỉnh sửa file; hãy đặt yêu cầu phát hiện thay đổi trong lúc đọc.
Một công cụ quét thư mục muốn ghi nhận FileVisitResult để quyết định tiếp tục, bỏ nhánh hay dừng toàn bộ; hãy xây dựng tình huống nghiệp vụ với một nhánh bị lỗi.
Một job lập chỉ mục hàng triệu tài liệu cần gom lỗi truy cập từ một số file nhưng vẫn tạo báo cáo cuối có số file thành công và thất bại; hãy mô tả trạng thái cần quản lý trong quá trình duyệt.
Một ứng dụng theo dõi thư mục upload muốn nhận thông báo khi có file mới thay vì quét toàn bộ mỗi giây; hãy thiết kế tình huống quản lý vòng đời một WatchService.
Một dịch vụ nạp lại cấu hình theo thay đổi file gặp các sự kiện tạo, sửa và xóa liên tiếp trong vài mili giây; hãy đặt yêu cầu chống xử lý lặp và đọc dữ liệu đang ghi dở.
Một editor lưu file bằng cách ghi tệp tạm rồi đổi tên, khiến watcher không luôn thấy cùng loại sự kiện sửa file; hãy nêu yêu cầu chấp nhận nhiều mẫu sự kiện filesystem.
Một daemon đăng ký WatchService cho nhiều thư mục con mà cấu trúc cây có thể mở rộng trong runtime; hãy mô tả tình huống cần theo dõi thư mục mới phát sinh.
Một thư mục ghi log có lưu lượng ghi rất cao có thể làm tràn hàng đợi sự kiện theo dõi; hãy xác định trạng thái mất sự kiện cần phát hiện và cách kiểm chứng dữ liệu lại.
Một service watcher đang chờ sự kiện thì tiến trình nhận lệnh dừng và cần kết thúc gọn; hãy xây dựng kịch bản kiểm soát thread, interrupt và đóng WatchService.
Một ứng dụng chạy trên filesystem mạng thấy thông báo thay đổi file đến trễ hoặc bị gộp; hãy mô tả yêu cầu không coi watcher là nguồn sự thật duy nhất.
Một worker xử lý tài liệu dựa trên sự kiện tạo file nhưng file có thể bị xóa trước khi worker mở; hãy đặt tình huống race condition và xử lý lỗi.
Một hệ thống giám sát muốn theo dõi thời điểm file bị đổi quyền chứ không chỉ nội dung, nhưng backend WatchService có tập sự kiện khác nhau; hãy nêu bài toán xác minh khả năng được hỗ trợ.
Một dịch vụ tải video cần đọc nhiều vùng khác nhau của cùng một file theo vị trí để phục vụ các HTTP range request; hãy mô tả yêu cầu chọn I/O theo vị trí và giới hạn bộ nhớ.
Một bộ xử lý tệp dung lượng lớn cần đọc một phần dữ liệu vào ByteBuffer, nhưng mỗi lần đọc có thể nhận ít byte hơn yêu cầu; hãy đặt bài toán bảo đảm đủ dữ liệu trước khi giải mã.
Một công cụ chuyển đổi dữ liệu ghi qua FileChannel và muốn kiểm chứng số byte thực sự đã được ghi khi thiết bị lưu trữ chịu tải; hãy mô tả trường hợp partial write.
Một ứng dụng trao đổi dữ liệu qua socket bất đồng bộ phải xử lý request đồng thời mà không giữ một thread riêng cho mỗi kết nối; hãy xây dựng tình huống quản lý completion và timeout.
Một server nhận nhiều kết nối bằng AsynchronousServerSocketChannel nhưng client có thể ngắt giữa quá trình xử lý; hãy đặt yêu cầu quản lý trạng thái request và cleanup.
Một dịch vụ sao chép file qua `FileChannel.transferTo` kỳ vọng sao chép hết dữ liệu trong một lần gọi, nhưng môi trường chỉ truyền được một phần; hãy mô tả bài toán kiểm soát tiến độ.
Một bộ đọc ảnh nhị phân sử dụng buffer chia sẻ giữa nhiều callback I/O và thỉnh thoảng dữ liệu bị ghi đè; hãy đặt yêu cầu phân định quyền sở hữu và vòng đời ByteBuffer.
Một client mạng cần xác định khi nào kết quả đọc bất đồng bộ bằng không byte, kết thúc luồng hoặc phát sinh lỗi; hãy mô tả các trường hợp cần phân biệt để xử lý an toàn.
Một hệ thống tải file có nhiều thao tác ghi bất đồng bộ vào các vị trí khác nhau của cùng một file; hãy đánh giá yêu cầu tránh chồng vùng và xác nhận thứ tự hoàn tất.
Một ứng dụng truyền dữ liệu nhị phân dùng ByteBuffer nhưng đôi khi đọc nhầm các byte cũ do chưa chuyển chế độ đọc và ghi; hãy xây dựng tình huống kiểm thử trạng thái buffer.
Một bộ xử lý bản ghi cố định muốn đọc đúng khung byte từ AsynchronousFileChannel nhưng không bảo đảm mỗi completion chứa trọn một bản ghi; hãy mô tả yêu cầu kết hợp các lần đọc.
Một hệ thống phục vụ tệp tĩnh muốn tiết kiệm bộ nhớ khi chuyển file lớn sang channel đích và phải tương thích nhiều hệ điều hành; hãy nêu các yếu tố cần benchmark và phương án dự phòng.
Một ứng dụng đóng asynchronous channel trong lúc các tác vụ đọc chưa hoàn tất và nhận lỗi không ổn định; hãy đặt yêu cầu quản lý vòng đời channel khi shutdown.
Một thư viện streaming cần xử lý đầu vào theo UTF-8 nhưng dữ liệu có thể chia cắt giữa các ByteBuffer ở giữa một ký tự nhiều byte; hãy xây dựng trường hợp kiểm thử giải mã đúng.
Một công cụ sao lưu có hai file system provider với mức hỗ trợ channel khác nhau; hãy mô tả tình huống chọn chiến lược I/O mà không coi mọi provider tương đương.
Một tác vụ phân tích log hàng trăm gigabyte được chia thành nhiều khoảng byte để xử lý song song; hãy đặt yêu cầu tránh cắt dòng giữa các khoảng và gom kết quả đúng.
Một hệ thống xử lý ảnh lớn có thể chia theo vùng độc lập, nhưng số vùng nhỏ tạo overhead task quá cao; hãy xác định bài toán lựa chọn ngưỡng chia việc cho Fork/Join.
Một dịch vụ tính tổng hàng triệu số dùng nhiều tác vụ chia nhỏ rồi hợp kết quả và phải bảo đảm không tràn số; hãy mô tả tình huống kiểm tra correctness và throughput.
Một chương trình tính histogram song song vô tình cập nhật chung một mảng đếm mutable dẫn đến mất dữ liệu; hãy nêu yêu cầu thiết kế trạng thái từng tác vụ và bước hợp kết quả.
Một ứng dụng xử lý cây thư mục tạo tác vụ Fork/Join đệ quy trên mỗi thư mục nhưng gặp độ sâu cây bất thường; hãy đặt tình huống cân bằng số task và ngăn stack overflow.
Một nhóm phát triển sử dụng ForkJoinPool cho hàng nghìn thao tác chờ HTTP đồng bộ khiến worker bị kẹt; hãy mô tả bài toán phân biệt CPU-bound với blocking I/O.
Một dịch vụ tạo thumbnail xử lý hàng vạn ảnh nhỏ với số task vượt xa số lõi CPU; hãy xác định tín hiệu hiệu năng cần đo để tránh chia việc quá nhỏ.
Một mô hình tìm kiếm đệ quy có các nhánh kích thước rất khác nhau và CPU không được tận dụng đều; hãy xây dựng tình huống đánh giá work stealing trong ForkJoinPool.
Một ứng dụng báo cáo dùng RecursiveTask để tính từng phần rồi join, nhưng kết quả đôi lúc thiếu một nhánh; hãy đặt yêu cầu kiểm chứng mọi tác vụ con được kết hợp đúng.
Một công cụ chuyển đổi dữ liệu khởi chạy ForkJoinPool tùy chỉnh cho mỗi request và không giải phóng tài nguyên; hãy nêu bài toán quản lý pool dùng chung và thời điểm shutdown.
Một job xử lý dữ liệu đã có quy tắc hủy khi người dùng đóng trang, nhưng các tác vụ Fork/Join con vẫn chạy; hãy mô tả yêu cầu truyền tín hiệu dừng và kiểm soát kết quả một phần.
Một thư viện song song cần giữ đúng thứ tự ghép chuỗi từ các nhánh tính toán, nhưng Fork/Join có thể chạy nhánh theo thứ tự khác; hãy đặt tình huống kiểm chứng tính quyết định.
Một tác vụ đếm tệp dùng RecursiveAction để cập nhật bộ đếm chung không thread-safe; hãy mô tả lỗi có thể xuất hiện và yêu cầu kiểm thử concurrent mutation.
Một nhóm phải so sánh tác vụ Fork/Join với xử lý tuần tự trên tập dữ liệu nhỏ, vừa và lớn; hãy đặt bài toán benchmark có warm-up và dữ liệu đại diện.
Một ứng dụng sử dụng common ForkJoinPool đồng thời với các tác vụ nền khác và thỉnh thoảng thấy độ trễ tăng; hãy nêu yêu cầu kiểm tra cạnh tranh tài nguyên và cách ly workload.
Một chương trình duyệt đồ thị song song phải loại bỏ node đã thăm để tránh xử lý lặp và các nhánh có thể gặp cùng node; hãy xây dựng tình huống đồng bộ trạng thái hợp lý.
Một bộ tổng hợp số thập phân chạy song song cho kết quả sai khác rất nhỏ giữa các lần chạy; hãy đặt yêu cầu đánh giá thứ tự phép cộng số thực và mức chính xác cần cam kết.
Một tiến trình điều phối nhiều giai đoạn tải dữ liệu cần thay đổi số lượng worker giữa các giai đoạn mà không cố định từ đầu; hãy mô tả kịch bản phối hợp bằng cơ chế barrier linh hoạt.
Một batch job có ba giai đoạn đọc, kiểm tra và ghi; mọi worker phải hoàn tất giai đoạn trước mới chuyển sang giai đoạn sau; hãy đặt yêu cầu đồng bộ tiến độ mà không tạo race condition.
Một thuật toán đa pha có một worker bị lỗi trước khi báo hoàn tất, khiến các worker còn lại chờ mãi; hãy mô tả chiến lược phát hiện lỗi và hủy phối hợp.
Một hệ thống tải dữ liệu có worker được tạo động và hủy sau khi xử lý xong, nhưng số lượng worker đồng bộ thay đổi theo tải; hãy đặt tình huống đăng ký và rút khỏi các pha.
Một ứng dụng mô phỏng chạy nhiều vòng cập nhật trạng thái đồng thời và cần phân biệt kết thúc pha hiện tại với kết thúc toàn bộ bài toán; hãy xác định các trạng thái cần theo dõi.
Một nhóm tối ưu thuật toán đang dùng barrier có số thành viên cố định nhưng workload thường xuyên thay đổi; hãy xây dựng tình huống đánh giá lại cơ chế phối hợp và giới hạn tài nguyên.
Một dịch vụ cấp phát ID song song dùng chung một `Random` gây cạnh tranh khi nhiều thread cùng tạo số thử nghiệm; hãy đặt yêu cầu giảm contention mà vẫn có kiểm thử có thể tái lập.
Một hệ thống phân tải tạo giá trị ngẫu nhiên độc lập cho từng worker và chạy trên nhiều lõi; hãy mô tả bài toán phân biệt generator theo thread với generator phục vụ yêu cầu mật mã.
Một service phát sinh mã xác minh đăng nhập định dùng tiện ích tạo số ngẫu nhiên cho tác vụ đồng thời; hãy đặt tình huống phát hiện yêu cầu bảo mật trước khi lựa chọn generator.
Một chương trình mô phỏng Monte Carlo chạy nhiều tác vụ với seed khác nhau và kết quả cần tái hiện khi kiểm thử; hãy xác định điều kiện ghi nhận seed và cấu hình thực thi.
Một module xử lý đồng thời dùng `ConcurrentLinkedDeque` làm hàng đợi hai đầu và phát sinh thao tác quan sát size liên tục; hãy mô tả yêu cầu đánh giá độ chính xác snapshot và chi phí đo kích thước.
Một dịch vụ phối hợp worker qua TransferQueue cần biết khi nào producer thực sự chuyển giao phần tử cho consumer, thay vì chỉ đặt vào bộ đệm; hãy xây dựng tình huống kiểm thử trao đổi.
Một pipeline nhận dữ liệu phải điều tiết khi hàng đợi công việc chạm giới hạn nhưng vẫn cho phép các producer hủy chờ; hãy mô tả kịch bản backpressure và interrupt.
Một library triển khai API yêu cầu tham số Path không được null nhưng được gọi từ nhiều module; hãy đặt yêu cầu chỉ rõ vị trí xác thực đầu vào và thông điệp lỗi nhất quán.
Một hệ thống nhận đầu vào đường dẫn Unicode hỗn hợp dạng chuẩn hóa và cần quyết định xem hai tệp có cùng tên trên hệ điều hành khác nhau hay không; hãy mô tả bài toán tương thích filesystem.
Một ứng dụng dùng `StandardCharsets.UTF_8` để đọc metadata từ tệp văn bản trên nhiều máy và đôi khi gặp byte không hợp lệ; hãy đặt yêu cầu phân biệt lỗi decoding với dữ liệu thiếu.
Một dự án đang chuyển từ `java.io.File` sang `Path` trong dịch vụ sao lưu và phải giữ đúng xử lý file tương đối, symlink và quyền truy cập; hãy xây dựng bộ trường hợp hồi quy.
Một ứng dụng Android hoặc môi trường JDK rút gọn không cung cấp đầy đủ filesystem provider như máy phát triển; hãy đặt yêu cầu nhận diện khả năng API trước khi bật một tính năng.
Một hệ thống kiểm thử file I/O chỉ chạy trên Linux nhưng sẽ triển khai cả Windows, nơi quy tắc khóa file và tên tệp khác nhau; hãy mô tả ma trận kiểm thử cần xây dựng.
Một chương trình chuyển đổi tài liệu cần duy trì quyền POSIX trên hệ thống có hỗ trợ, nhưng không được thất bại hoàn toàn trên hệ thống khác; hãy đặt tình huống kiểm tra capability và fallback.
Một ứng dụng giải nén nhận ZIP không tin cậy với tên entry chứa các thành phần đường dẫn cha và symlink; hãy mô tả yêu cầu giới hạn nơi ghi file và ngăn vượt thư mục đích.
Một sản phẩm phải chạy bằng JDK hiện đại và còn mã sử dụng API NIO.2 từ Java 7; hãy đặt bài toán kiểm tra hành vi thực tế thay vì dựa trên ví dụ từ các hệ điều hành cũ.
Một nhóm nâng cấp JDK thấy một số tham số JVM cũ từng được khuyến nghị cho Fork/Join hoặc file I/O nay không còn phù hợp; hãy nêu yêu cầu loại bỏ phụ thuộc cấu hình lịch sử và đo lại.
Một hệ thống phục hồi sau sự cố cần so sánh tính toàn vẹn của file trước và sau khi copy, đồng thời không bỏ qua lỗi đóng stream; hãy mô tả kiểm thử end-to-end cần thiết.
Một dịch vụ giám sát sản xuất kết hợp watcher, xử lý file và pool CPU để chuyển đổi dữ liệu theo thời gian thực; hãy đặt tình huống truy tìm điểm nghẽn, mất sự kiện và quá tải hàng đợi.
Một ứng dụng triển khai container bị giới hạn bộ nhớ, CPU và file descriptor trong khi thực hiện nhiều thao tác NIO.2 và Fork/Join; hãy nêu các giới hạn vận hành và số liệu cần quan sát.
Một nhóm code review nhận bản refactor Java 7 thay đổi try-with-resources, multi-catch, Path và Fork/Join cùng lúc; hãy xây dựng yêu cầu chia nhỏ kiểm thử để phát hiện thay đổi hợp đồng hành vi.
