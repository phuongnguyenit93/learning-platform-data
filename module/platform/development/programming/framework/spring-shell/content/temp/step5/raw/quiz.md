Câu 1. Trong Spring Shell 4, cặp annotation nào phù hợp để khai một command method trong bean được quét?
A. @Component trên class và @Command trên method
B. @RestController trên class và @GetMapping trên method
C. @Repository trên class và @Query trên method
D. @Configuration trên class và @Bean trên method
Đáp án đúng: A

Câu 2. Với @Command(name="deploy") trong Spring Shell 4, name quy định nội dung nào?
A. Tên command mà người dùng gọi trong CLI
B. Tên bean của DataSource kết nối tới server
C. Tên file cấu hình application.yml của command
D. Tên gói Java mà Spring Boot sẽ quét component
Đáp án đúng: A

Câu 3. Trong mô hình annotation legacy của Spring Shell 3, cặp nào đăng ký command thông thường?
A. @Component trên class và @GetMapping trên method
B. @ShellComponent trên class và @ShellMethod trên method
C. @Configuration trên class và @Transactional trên method
D. @Controller trên class và @EventListener trên method
Đáp án đúng: B

Câu 4. Trong Spring Shell 4, cách lập trình nào có thể tạo command thành Spring bean?
A. Trả về Command dựng bằng Command.builder() từ @Bean
B. Trả về Controller dựng bằng RouterFunctions.route()
C. Trả về Runnable thông qua @Scheduled ở @Bean
D. Trả về JwtDecoder được tạo trong SecurityFilterChain
Đáp án đúng: A

Câu 5. Trong Spring Shell 4, CommandRegistry chủ yếu quản lý dữ liệu nào?
A. Các kết nối JDBC trong pool của ứng dụng command
B. Các HTTP endpoint được DispatcherServlet tự đăng ký
C. Tập command đăng ký để Shell tra cứu và thực thi
D. Các message queue của ứng dụng đang chạy lệnh CLI
Đáp án đúng: C

Câu 6. Nếu class chứa @Command bị loại khỏi component scan, điều gì có thể xảy ra?
A. Command tự trở thành built-in dù class không là bean
B. Command không được phát hiện và đăng ký từ class đó
C. Command tự được đọc từ tệp pom.xml khi chạy CLI
D. Command chuyển thành REST endpoint thay vì CLI method
Đáp án đúng: B

Câu 7. Với @Option(longName="region") trong Spring Shell 4, cú pháp nào biểu diễn option dài?
A. /region eu-west khi gọi command có option region
B. -region eu-west khi gọi command có option region
C. region:eu-west khi gọi command có option region
D. Cú pháp --region eu-west của option region
Đáp án đúng: D

Câu 8. Trong Spring Shell 4, @Argument(index=0) thường định nghĩa điều gì?
A. Đối số vị trí đầu tiên của command được khai báo
B. Option dạng dài với tên index xuất hiện sau dấu --
C. Giá trị trả về của command dưới dạng exit status
D. Phím nóng của command được gắn vào giao diện TUI
Đáp án đúng: A

Câu 9. Cú pháp nào hợp lệ cho option dài --limit nhận giá trị 10 trong Spring Shell 4?
A. Dùng --limit=10 hoặc --limit 10 theo cách parser hỗ trợ
B. Dùng /limit:10 hoặc /limit 10 theo cú pháp Win32
C. Dùng limit:10 hoặc limit=10 mà không có tiền tố --
D. Dùng --limit tự suy ra 10 mà không truyền giá trị
Đáp án đúng: A

Câu 10. Với @Option(shortName='n',longName="name"), cặp cú pháp nào tương đương?
A. Dùng --n Alice và -name Alice cho cùng một option
B. Dùng /n Alice và /name Alice cho cùng một option
C. Dùng -n Alice và --name Alice tương đương
D. Dùng n=Alice và name=Alice không cần tiền tố nào
Đáp án đúng: C

Câu 11. Với @Option(defaultValue="dev"), mục tiêu cấu hình này trong Spring Shell 4 là gì?
A. Bắt người dùng luôn nhập dev ngay sau tên command
B. Đặt tên group mặc định cho command là dev
C. Lấy dev khi không truyền option tương ứng
D. Tự chuyển mọi input của option sang upper-case
Đáp án đúng: C

Câu 12. Với @Option(required=true), hành vi nào được mong đợi?
A. Báo thiếu option khi người dùng không cung cấp giá trị cần thiết
B. Tự gán null dù tham số đang được khai là bắt buộc
C. Tự phát sinh giá trị theo tên parameter trong Java method
D. Bỏ qua kiểm tra input và gọi method với chuỗi rỗng
Đáp án đúng: A

Câu 13. Trong Spring Shell 4, @Option(required=false) thường dùng để làm gì?
A. Cấm truyền option trong tất cả lời gọi command
B. Cho phép không truyền option khi gọi command
C. Chỉ chấp nhận input qua positional argument
D. Buộc người dùng truyền option hai lần liên tiếp
Đáp án đúng: B

Câu 14. Khi parameter command được khai kiểu int, lớp xử lý command cần thực hiện gì với input chuỗi?
A. Tạo bean JdbcTemplate để đọc số từ database command
B. Giữ chuỗi nguyên rồi ép mọi int thành String lúc runtime
C. Đổi chuỗi input sang int trước khi gọi method
D. Chỉ chấp nhận số nếu command đã được đánh dấu @Async
Đáp án đúng: C

Câu 15. Nếu gọi --count xyz với command cần giá trị số nguyên, kết quả nào phù hợp?
A. Tự biến xyz thành số 0 và tiếp tục chạy công việc
B. Báo lỗi chuyển đổi đối số thay vì coi xyz là số nguyên
C. Bỏ qua option rồi tự thêm một positional argument
D. Tự tải enum để tìm giá trị số nguyên tương ứng
Đáp án đúng: B

Câu 16. Để chặn password ngắn trên @Option của Spring Shell 4, cấu hình nào phù hợp?
A. Gắn @Transactional lên method để rollback khi password ngắn
B. Dùng @Order để đổi thứ tự command dựa trên độ dài
C. Dùng @Profile("prod") trên field chứa password
D. Áp Bean Validation như @Size(min=8) lên parameter
Đáp án đúng: D

Câu 17. Trong Spring Shell 4, phân biệt @Option với @Argument như thế nào?
A. Option chỉ dùng cho số nguyên; argument chỉ dùng cho chuỗi
B. Option nhận từ file YAML; argument chỉ lấy từ database
C. Option xác định mã thoát; argument xác định output style
D. Option mang tên như --name; argument được xác định theo vị trí
Đáp án đúng: D

Câu 18. Khi nhận chuỗi bí mật từ CLI, thực hành nào giúp giảm rủi ro lộ thông tin?
A. In toàn bộ secret cùng với command help để dễ gỡ lỗi
B. Gắn secret vào exception stacktrace khi parse input sai
C. Tránh ghi giá trị secret vào log hoặc help/output thông thường
D. Thêm secret vào lịch sử shell để người dùng chạy lại dễ dàng
Đáp án đúng: C

Câu 19. Lệnh built-in help của Spring Shell thường hỗ trợ mục đích gì?
A. Khám phá các command hiện có và mô tả sử dụng
B. Tạo tự động password mới cho command bị lỗi
C. Đăng ký mọi REST endpoint vào ServletContext
D. Chạy lại command cuối cùng bằng quyền administrator
Đáp án đúng: A

Câu 20. Khi tra cứu help cho một command cụ thể, thông tin nào hữu ích nhất?
A. Giá trị private key đang lưu trong biến môi trường
B. Mục đích command, các option và cú pháp sử dụng
C. Danh sách session cookie của tất cả user trong app
D. Mật khẩu được lưu trong file cấu hình deployment
Đáp án đúng: B

Câu 21. Với @Command(group="User Management"), group phục vụ nhu cầu nào?
A. Chạy command trên thread pool có tên User Management
B. Tạo database schema User Management khi startup
C. Tự tạo REST prefix /User-Management cho command
D. Gom các command vào nhóm hiển thị trong help
Đáp án đúng: D

Câu 22. Để nội dung help dễ hiểu, description của command nên cung cấp gì?
A. Mô tả ngắn đúng tác dụng và phạm vi của command
B. Đường dẫn file log chứa stacktrace của mọi lần thực thi
C. Danh sách IP của server đang chạy command hiện tại
D. Chuỗi hash của mọi dependency dùng trong ứng dụng
Đáp án đúng: A

Câu 23. Trong phiên Shell tương tác với JLine, phím Tab thường giúp gì?
A. Chạy command ngay lập tức và đóng terminal sau xử lý
B. Đề xuất cách hoàn thiện tên command hoặc option đang nhập
C. Đổi tất cả input thành positional argument kiểu String
D. Gửi command hiện tại sang background thread của JVM
Đáp án đúng: B

Câu 24. Spring Shell 4 dùng CompletionProvider chủ yếu cho công việc gì?
A. Chạy toàn bộ command nhằm kiểm tra kết quả trước khi người dùng Enter
B. Tự xác thực token OAuth2 khi command có tham số tên user
C. Cung cấp gợi ý hoàn thành input dựa trên ngữ cảnh đang nhập
D. Lưu output của tất cả lần chạy vào bộ nhớ để hoàn tác
Đáp án đúng: C

Câu 25. FileNameCompletionProvider phù hợp nhất với loại tham số nào?
A. Mật khẩu tài khoản được che dưới dạng dấu sao
B. Đường dẫn file hoặc thư mục được nhập trên terminal
C. Client secret OAuth2 nằm trong secret manager
D. Giá trị số lượng bản ghi cần tính từ cơ sở dữ liệu
Đáp án đúng: B

Câu 26. Nếu CompletionProvider phụ thuộc vào input người dùng, cách thiết kế nào thích hợp?
A. Thực hiện thao tác xóa dữ liệu để phát hiện command hợp lệ
B. Chặn thread đến khi command được thực thi xong
C. Tự ghi lại input vào database như một lần thực thi thật
D. Trả các đề xuất liên quan mà tránh side effect tốn kém
Đáp án đúng: D

Câu 27. Một command chỉ dùng sau khi connect thành công nên được kiểm soát bằng gì?
A. ExitStatusExceptionMapper tự kết nối server trước mọi command
B. FileNameCompletionProvider tự đăng nhập vào dịch vụ ngoài
C. AvailabilityProvider kiểm tra trạng thái kết nối trước khi dùng
D. CommandRegistry xóa command mỗi khi kết nối chưa sẵn sàng
Đáp án đúng: C

Câu 28. Khi một command đã được đăng ký nhưng chưa available, cách phản hồi nào hữu ích?
A. Âm thầm xóa command khỏi registry và không để lại mô tả
B. Thông báo vì sao command hiện không thể chạy để người dùng xử lý
C. Cứ chạy command rồi mặc nhiên bỏ qua mọi tiền điều kiện
D. Thay command bằng một HTTP redirect tới trang login
Đáp án đúng: B

Câu 29. Trong Spring Shell 4, ExitStatusExceptionMapper phục vụ mục đích nào?
A. Chuyển @Option thành @Argument trước khi command được gọi
B. Tạo danh sách completion từ tên method có @Command
C. Đổi Bean Validation constraint thành một command mới
D. Ánh xạ exception sang ExitStatus có thông điệp lỗi
Đáp án đúng: D

Câu 30. Với Command API programmatic của Spring Shell 4, kết quả chạy command có thể biểu diễn bằng gì?
A. ResponseEntity chứa HTTP status của Servlet controller
B. Authentication chứa principal và authorities của user
C. Pageable chứa số trang command đang được chạy
D. ExitStatus chứa mã và thông điệp trạng thái thực thi
Đáp án đúng: D

Câu 31. Để script biết command gặp lỗi nghiệp vụ, cách báo lỗi nào dễ tự động hóa?
A. Chỉ đổi màu output thành đỏ nhưng luôn báo trạng thái OK
B. Trả mã thất bại có nghĩa thay vì chỉ in dòng thông báo lỗi
C. Chỉ bật debug stacktrace và giữ mã thoát thành công
D. Gửi chuỗi lỗi ra help rồi vẫn báo command thành công
Đáp án đúng: B

Câu 32. Khi command gặp lỗi và có dữ liệu nhạy cảm, cách xử lý output nào nên chọn?
A. In nguyên Authorization header để người dùng sao chép lại
B. Ghi cả secret và stacktrace ra stdout của workflow CI
C. Không đưa token hay password vào phản hồi lỗi
D. Trả đầy đủ private key trong trường error.message
Đáp án đúng: C

Câu 33. Khác biệt sử dụng chính giữa interactive và non-interactive CLI là gì?
A. Interactive chỉ hỗ trợ HTTP request; non-interactive chỉ JDBC
B. Interactive bắt buộc dùng OAuth2; non-interactive bắt buộc LDAP
C. Interactive cần database; non-interactive không nạp ApplicationContext
D. Interactive nhận lệnh liên tục; non-interactive chạy từ đối số/script
Đáp án đúng: D

Câu 34. Thuộc tính nào được tài liệu Spring Shell dùng để tắt chế độ interactive?
A. spring.main.web-application-type=servlet để tắt terminal
B. spring.shell.interactive.enabled=false để chuyển runner phù hợp
C. spring.security.enabled=false để bỏ chế độ tương tác
D. spring.datasource.initialize=false để chạy một command
Đáp án đúng: B

Câu 35. NonInteractiveShellRunner phù hợp nhất với trường hợp nào?
A. Duy trì prompt JLine và đọc từng phím cho tới khi quit
B. Đăng ký command như REST endpoint trong DispatcherServlet
C. Chạy command dòng lệnh, không mở prompt tương tác
D. Chạy tất cả method @Command song song khi startup
Đáp án đúng: C

Câu 36. Khi muốn chạy CLI qua cron/CI, thao tác nào giúp kết quả tái lập tốt hơn?
A. Dựa vào các câu lệnh trước đó trong lịch sử shell cá nhân
B. Yêu cầu người vận hành nhập password bằng prompt mỗi lần CI
C. Truyền command, input và config rõ ràng cho job
D. Bắt cron đọc history file để chọn command gần nhất
Đáp án đúng: C

Câu 37. Built-in script trong Spring Shell 4 hỗ trợ tác vụ nào?
A. Biên dịch Java source thành native executable trong runtime
B. Đọc file lệnh và thực thi nhiều command theo thứ tự
C. Tạo bảng SQL tạm thời rồi chạy command bằng JDBC
D. Tự lập kế hoạch chạy command theo lịch cron hệ điều hành
Đáp án đúng: B

Câu 38. Trong script file Spring Shell, cách tổ chức nội dung nào thuận tiện để chạy tuần tự?
A. Đặt mọi command vào một JSON array không qua parser
B. Ghi mỗi command thành một class với main method riêng
C. Ghi method Java rồi để Shell tự biên dịch khi đọc file
D. Đặt mỗi command trên một dòng theo thứ tự mong muốn
Đáp án đúng: D

Câu 39. Khi chạy script nhận từ nguồn chưa đáng tin, biện pháp nào phù hợp?
A. Cho script chạy với quyền admin để tránh lỗi file access
B. Bỏ validation vì script không được người dùng nhập trực tiếp
C. Tự chạy lại command lỗi vô hạn tới khi được phép truy cập
D. Giới hạn nguồn lệnh và quyền của tiến trình trước khi thực thi
Đáp án đúng: D

Câu 40. Vì sao command dùng trong batch nên tránh chờ prompt không điều kiện?
A. Vì input từ terminal luôn chuyển thành String rỗng trong CLI
B. Vì parser của Spring Shell cấm mọi boolean option ở batch
C. Vì job tự động có thể treo khi không có người nhập phản hồi
D. Vì mọi command có prompt sẽ tự đổi thành HTTP request
Đáp án đúng: C

Câu 41. Trong Command API programmatic của Spring Shell 4, cách ghi output nào phù hợp?
A. Dùng outputWriter lấy từ CommandContext để in kết quả
B. Chỉ ghi trực tiếp vào System.err để Shell coi như thành công
C. Thay CommandRegistry bằng System.out khi đăng ký command
D. Đặt text đầu ra trong request attribute của Servlet filter
Đáp án đúng: A

Câu 42. Với method gắn @Command trong Spring Shell 4, giá trị trả về String có thể được xử lý thế nào?
A. Được Shell hiển thị như kết quả của command sau khi thực thi
B. Được Shell tự chuyển thành tên command mới cho lần tiếp theo
C. Được dùng làm khóa JWT để xác thực lời gọi command khác
D. Được xem là Spring bean name và tự inject vào context
Đáp án đúng: A

Câu 43. Khi cần output CLI dễ đọc trên nhiều loại terminal, điều gì nên lưu ý?
A. Bắt toàn bộ terminal hỗ trợ màu 24-bit trong mọi môi trường
B. Chọn style phù hợp terminal, tránh ANSI không cần
C. Chỉ in binary bytes vì console không thể hiển thị Unicode
D. Trộn stdout và stderr mà không phân biệt dữ liệu với lỗi
Đáp án đúng: B

Câu 44. Khi CLI được script khác phân tích output, hướng thiết kế nào phù hợp?
A. Đổi ngẫu nhiên tên field trong output giữa các lần chạy
B. Chèn ANSI escape trong mọi trường dữ liệu machine-readable
C. Có định dạng ổn định như JSON và không trộn log vào dữ liệu
D. Chỉ xuất stacktrace thay cho giá trị thành công của command
Đáp án đúng: C

Câu 45. Với @ShellTest và ShellTestClient trong Spring Shell 4, cần kiểm thử điều gì?
A. Dùng sendCommand kiểm tra output lệnh qua ShellTestClient
B. Chỉ chạy unit test DAO và coi command parser đã đúng
C. Dùng MockMvc kiểm tra HTTP controller thay cho terminal
D. Chỉ so sánh bean definitions mà bỏ lệnh thực thi
Đáp án đúng: A

Câu 46. Trong Spring Shell 4, kiểm thử command yêu cầu nhập thêm từ prompt bằng cách nào?
A. Chỉ dùng ShellTestClient.sendCommand và mặc định bỏ qua prompt
B. Chỉ gửi tên command rồi coi input của prompt là chuỗi rỗng
C. Gửi dữ liệu prompt vào file application.yml thay vì test
D. Dùng ShellInputProvider trong ShellTestClient.sendCommand
Đáp án đúng: D

Câu 47. Để phân phối công cụ Spring Shell cho người dùng có JRE phù hợp, cách đóng gói nào hợp lý?
A. Chỉ phát file pom.xml rồi yêu cầu JRE tự build khi khởi động
B. Chỉ phát thư mục source chưa build để JLine tự biên dịch
C. Chỉ phát HTTP WAR bắt buộc deploy trên servlet container
D. Đóng gói thành Spring Boot executable JAR và chạy bằng java -jar
Đáp án đúng: D

Câu 48. Khi kiểm thử command ghi file CSV, cách nào giảm phụ thuộc vào máy chạy test?
A. Dùng thư mục tạm và fixture ổn định rồi assert nội dung file
B. Ghi file trực tiếp vào home của user để test dễ quan sát
C. Dùng bản ghi production để thay cho dữ liệu fixture kiểm thử
D. Chỉ assert một log SUCCESS mà không kiểm tra file kết quả
Đáp án đúng: A
