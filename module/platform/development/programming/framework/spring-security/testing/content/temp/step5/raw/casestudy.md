Một API quản lý đơn hàng chạy đúng khi thử qua trình duyệt, nhưng bài MockMvc trả 200 cho người chưa đăng nhập vì nhóm chỉ dựng controller độc lập; hãy xây dựng tình huống kiểm chứng chuỗi lọc bảo mật trong kiểm thử.
Một bài kiểm thử controller với MockMvc cấp sẵn người dùng có ROLE_ADMIN nhưng quên tích hợp cấu hình Spring Security nên cả tài khoản thường cũng thực hiện được thao tác xóa; hãy đặt bài toán xác định giá trị thực của phép thử.
Một endpoint tài khoản trả 401 cho khách chưa xác thực và 403 cho nhân viên không đủ quyền, nhưng bộ test hiện chỉ kiểm tra rằng cả hai đều thất bại; hãy xây dựng tình huống kiểm chứng khác biệt hai nhánh.
Một thay đổi ở SecurityFilterChain cho phép mọi request dưới /api/v2, trong khi test chỉ gọi đường dẫn /api/v1; hãy yêu cầu xây dựng ca MockMvc phát hiện quyền truy cập ngoài ý muốn ở phiên bản mới.
Một API đọc đơn hàng yêu cầu quyền ORDER_READ nhưng @WithMockUser trong test luôn gán ROLE_ADMIN, khiến các lần thay đổi quyền chi tiết không bị phát hiện; hãy đặt tình huống đánh giá dữ liệu danh tính kiểm thử.
Một controller dùng tham số Principal để ghi nhận người phê duyệt, nhưng bài test chỉ xác minh HTTP 200 mà không kiểm tra chủ thể được lưu trong dữ liệu; hãy xây dựng ca kiểm chứng luồng danh tính.
Một cổng dịch vụ có ba SecurityFilterChain với các đường dẫn chồng lấn, khiến endpoint quản trị đi vào chuỗi dành cho khách; hãy đặt tình huống kiểm tra hiệu lực phân quyền qua MockMvc.
Một endpoint GET công khai và endpoint POST cùng đường dẫn yêu cầu đăng nhập, nhưng bài test chỉ xác minh quyền truy cập theo URL; hãy xây dựng tình huống kiểm chứng ranh giới theo HTTP method.
Một bộ kiểm thử dùng @WebMvcTest cho controller thanh toán nhưng không đưa vào cấu hình bảo mật thực tế, làm kết quả phân quyền khác với khi chạy đầy đủ ứng dụng; hãy đặt bài toán đánh giá phạm vi test slice.
Một API có request matcher theo biến đường dẫn và ID của khách hàng, nhưng các bài test đều dùng ID thuộc cùng người đăng nhập; hãy xây dựng ca MockMvc phát hiện truy cập ngang quyền.
Một chức năng export dữ liệu trả file khi có quyền, nhưng test chỉ kiểm tra status mà không xác minh dữ liệu trong response được giới hạn theo người gọi; hãy đặt tình huống kiểm chứng nội dung kết quả.
Một endpoint ẩn thông tin tài nguyên không thuộc người dùng bằng phản hồi 404 thay vì 403, nhưng bộ kiểm thử coi mọi mã 4xx là đạt; hãy xây dựng tình huống đánh giá tính chính xác của hợp đồng lỗi.
Một request xóa nhiều bản ghi có phần tử thuộc người khác và controller chỉ từ chối ở cuối luồng, sau khi một số bản ghi đã bị xóa; hãy đặt bài toán kiểm tra tác dụng phụ khi phân quyền thất bại.
Một bài MockMvc kiểm tra redirect sau đăng nhập bằng form nhưng không xác minh session mới hoặc danh tính của request tiếp theo; hãy xây dựng tình huống kiểm thử hành trình xác thực nhiều bước.
Một biểu mẫu đăng nhập đúng mật khẩu nhưng tài khoản đã bị khóa, trong khi test chỉ mô phỏng trường hợp mật khẩu sai; hãy đặt tình huống phân biệt các kết quả xác thực và phản hồi.
Một tài khoản có username chứa ký tự Unicode được phép đăng nhập thực tế nhưng bộ kiểm thử chỉ dùng username ASCII; hãy yêu cầu xây dựng tình huống xác minh ánh xạ danh tính trên request.
Một endpoint đổi email có xác thực nhưng POST thiếu CSRF token vẫn thành công trong môi trường test do cấu hình test vô tình tắt CSRF; hãy xây dựng tình huống kiểm tra bảo vệ HTTP thực tế.
Một nhóm sửa lỗi 403 bằng cách thêm CSRF token vào mọi request nhưng bỏ qua trường hợp người dùng không có quyền đổi mật khẩu; hãy đặt bài toán phân biệt kiểm tra CSRF và kiểm tra authority.
Một ứng dụng có form upload multipart và kiểm tra CSRF, nhưng test MockMvc chỉ gửi JSON nên không phát hiện lỗi khi người dùng tải ảnh đại diện; hãy xây dựng ca kiểm chứng request theo định dạng thật.
Một backend dùng cookie phiên để cập nhật giỏ hàng, trong khi các bài test chỉ gửi Bearer token không cần CSRF; hãy đặt tình huống kiểm tra nhánh xác thực bằng session.
Một bộ kiểm thử chống CSRF chỉ có request thiếu token, nhưng chưa đánh giá token giả hoặc token thuộc phiên khác; hãy xây dựng tình huống xác minh ràng buộc token với request hợp lệ.
Một ứng dụng vừa thay đổi cơ chế lưu CSRF token giữa session và cookie nhưng bài test vẫn dùng token tạo sẵn không đi qua hành trình trình duyệt; hãy đặt tình huống kiểm tra vòng đời token.
Một request preflight CORS OPTIONS bị yêu cầu đăng nhập trước khi trình duyệt gửi POST thật, nhưng test tích hợp chỉ gửi POST trực tiếp; hãy xây dựng tình huống kiểm chứng tiền kiểm.
Một frontend được phép gọi API với credentials, nhưng response thực tế trả CORS header không tương thích và MockMvc chỉ xác minh HTTP status; hãy đặt bài toán kiểm tra header mà trình duyệt nhận được.
Một ứng dụng giới hạn nguồn CORS theo danh sách đối tác, nhưng test dùng origin hợp lệ duy nhất và chưa thử origin lạ; hãy xây dựng tình huống kiểm chứng request bị chặn hoặc không được cấp quyền đọc chéo nguồn.
Một proxy thêm security headers bên ngoài ứng dụng, trong khi MockMvc báo thiếu HSTS dù production có header; hãy đặt tình huống xác định phạm vi kiểm thử ở các tầng triển khai.
Một trang quản trị yêu cầu CSP và X-Content-Type-Options nhưng test chỉ kiểm tra Content-Type; hãy xây dựng tình huống đánh giá bộ header bảo mật theo hợp đồng.
Một trang báo cáo được phép nhúng trong website đối tác nhưng test không kiểm tra CSP frame-ancestors, khiến cấu hình mới cho phép mọi origin nhúng; hãy đặt bài toán kiểm chứng quy tắc phản hồi.
Một endpoint nội bộ trả lỗi 500 khi xảy ra sự cố nhưng response không còn security headers như khi thành công; hãy xây dựng tình huống kiểm thử header trên nhánh lỗi.
Một ứng dụng sử dụng đường dẫn mã hóa có thể bị HTTP firewall từ chối trước controller, nhưng test gọi trực tiếp method Java nên bỏ qua toàn bộ đường đi HTTP; hãy đặt tình huống tái hiện bằng MockMvc.
Một client cũ sử dụng dấu chấm phẩy trong đường dẫn và bị firewall từ chối, trong khi đội phát triển đã miễn toàn bộ URL để sửa lỗi; hãy xây dựng tình huống kiểm tra hồi quy với đường dẫn đáng ngờ.
Một nhóm thay đổi cấu hình logout nhưng test chỉ kiểm tra 302 mà không xác minh session của request kế tiếp đã mất quyền truy cập; hãy xây dựng tình huống kiểm thử hiệu lực đăng xuất.
Một ứng dụng giới hạn phiên đăng nhập đồng thời nhưng bài kiểm thử chỉ có một request dùng một session; hãy đặt bài toán kiểm chứng phản hồi khi cùng tài khoản đăng nhập từ hai trình duyệt.
Một tài khoản vừa đổi mật khẩu nhưng phiên được tạo trước đó vẫn có thể gọi API nhạy cảm, trong khi bộ test không mô phỏng trạng thái sau đổi mật khẩu; hãy xây dựng tình huống đánh giá vòng đời phiên.
Một controller tạo session không mong muốn dù endpoint API được công bố là stateless, nhưng MockMvc chỉ xác minh body JSON; hãy đặt tình huống kiểm tra cookie và trạng thái phiên.
Một biểu mẫu thay đổi địa chỉ gửi request thành công sau đăng nhập bằng remember-me, dù thao tác này yêu cầu xác thực đầy đủ; hãy xây dựng tình huống kiểm thử mức độ xác thực.
Một test dùng @WithMockUser để truy cập endpoint yêu cầu xác thực lại gần đây, nhưng không mô phỏng thời điểm đăng nhập; hãy đặt bài toán kiểm chứng chính sách xác thực theo ngữ cảnh.
Một ứng dụng kết hợp Basic Authentication cho hệ thống cũ và form login cho người dùng, nhưng test chỉ dùng danh tính giả lập và bỏ qua cách phân tích header Authorization; hãy xây dựng tình huống kiểm tra đường xác thực thật.
Một API nhận Authorization header sai định dạng và trả lỗi 500 thay vì phản hồi xác thực thất bại; hãy đặt tình huống kiểm thử dữ liệu header bất thường.
Một ứng dụng đa ngôn ngữ chuyển hướng về trang đăng nhập sau 401, nhưng client API mong nhận JSON; hãy xây dựng tình huống kiểm chứng entry point khác nhau theo nhóm endpoint.
Một controller gắn @PreAuthorize giới hạn quyền sửa giá, nhưng test gọi trực tiếp đối tượng tạo bằng new và vẫn sửa được giá; hãy đặt tình huống kiểm chứng phép thử có đi qua method security proxy.
Một service dùng @PostAuthorize để kiểm tra quyền với đối tượng trả về, nhưng bài kiểm thử chỉ gọi repository và chưa quan sát quyết định bảo mật; hãy xây dựng tình huống kiểm chứng kết quả method.
Một method trả danh sách hồ sơ được lọc theo quyền, nhưng bài test chỉ assert số lượng khi mọi hồ sơ đều của cùng người dùng; hãy đặt tình huống kiểm chứng rò rỉ trong tập kết quả.
Một tài khoản có quyền duyệt hóa đơn của chi nhánh A nhưng gọi cùng service trên hóa đơn của chi nhánh B vẫn thành công trong test khi thiếu dữ liệu kiểm thử chéo chi nhánh; hãy xây dựng tình huống đánh giá ngữ cảnh.
Một service giao dịch tự gọi method khác cùng bean được gắn chính sách phân quyền và bài test hiện không nhận ra khác biệt này; hãy đặt bài toán kiểm tra hiệu lực ranh giới method khi tự gọi.
Một tính năng chỉ từ chối một phần bản ghi trong thao tác hàng loạt, nhưng test kiểm tra quyền bằng ID đầu tiên rồi bỏ qua các ID còn lại; hãy xây dựng tình huống xác minh tính toàn vẹn nghiệp vụ.
Một tác vụ async gửi thông báo thay mặt người dùng nhưng SecurityContext không xuất hiện ở thread xử lý, khiến permission check thất bại trên CI; hãy đặt tình huống kiểm chứng lan truyền ngữ cảnh.
Một request được xử lý qua CompletableFuture và test đồng bộ trả 200 trước khi hành vi được bảo vệ xảy ra; hãy xây dựng tình huống xác định thời điểm assert bảo mật.
Một event listener gọi service có method security mà không có người dùng tương tác trong thread, nhưng unit test thiết lập SecurityContext thủ công và vẫn xanh; hãy đặt tình huống đánh giá sự tương đồng với runtime.
Một bài kiểm thử method security chạy đúng khi gọi riêng lẻ nhưng thất bại khi chạy cả suite vì SecurityContext từ test trước còn sót; hãy xây dựng tình huống kiểm chứng cô lập danh tính giữa các test.
Một lớp test sử dụng @WithMockUser ở cấp lớp nhưng một phương thức cần kiểm tra truy cập ẩn danh, khiến kết quả trái với ý định ca âm tính; hãy đặt bài toán kiểm tra phạm vi annotation.
Một ca thử dùng @WithAnonymousUser cho endpoint đọc công khai, nhưng không bao phủ phản hồi khi có Principal hợp lệ mà thiếu quyền; hãy xây dựng tình huống phân biệt hai nhóm người gọi.
Một ứng dụng có custom Authentication principal mang tenant và phòng ban, trong khi @WithMockUser không cung cấp các thuộc tính này; hãy đặt tình huống kiểm chứng chính sách theo thuộc tính người dùng.
Một test sử dụng @WithUserDetails để nạp danh tính từ cơ sở dữ liệu nhưng fixture thiếu account status, làm kết quả khác production; hãy xây dựng tình huống đánh giá dữ liệu danh tính khởi tạo.
Một nhóm bổ sung custom security test annotation để đại diện nhân viên ngân hàng, nhưng quyền gán trong annotation đã lỗi thời sau đợt đổi cấu trúc role; hãy đặt tình huống xác minh độ tin cậy của fixture.
Một service nhận Authentication từ SecurityContextHolder, nhưng test chỉ inject tên người dùng vào tham số controller và vẫn báo thành công; hãy xây dựng tình huống kiểm tra ngữ cảnh bảo mật thực sự.
Một suite dùng cùng đối tượng SecurityContext mutable cho nhiều test song song khiến người dùng của ca này xuất hiện trong ca khác; hãy xây dựng tình huống kiểm chứng tính độc lập khi chạy parallel.
Một chính sách method sử dụng vai trò được thừa hưởng qua role hierarchy, nhưng @WithMockUser trong test chỉ có role trực tiếp và kết quả khác môi trường thật; hãy đặt bài toán kiểm chứng hierarchy.
Một bộ test chỉ kiểm tra authority WRITE_USER nhưng chính sách production dùng tên ROLE_USER_ADMIN, khiến test giả lập quyền không phản ánh dữ liệu token thực; hãy xây dựng tình huống đánh giá ánh xạ quyền.
Một hệ thống cho nhân viên quyền truy cập tạm thời, nhưng test tạo danh tính có authority mà không mô phỏng thời hạn hết hiệu lực; hãy đặt tình huống kiểm chứng chính sách theo thời gian.
Một người dùng đăng nhập thành công nhưng chưa hoàn tất MFA, trong khi test gán thẳng role cao nhất qua @WithMockUser; hãy xây dựng tình huống kiểm tra các trạng thái xác thực trung gian.
Một tổ chức muốn kiểm thử bảo mật cấp method mà không khởi động server HTTP, nhưng kết quả phải dùng đúng cấu hình phương thức đang chạy ở production; hãy đặt tình huống xác định phạm vi context cần kiểm tra.
Một bài test có thể tạo Authentication thành công nhưng khi xóa quyền khỏi tài khoản trong cơ sở dữ liệu request kế tiếp vẫn giữ authority cũ; hãy đặt tình huống đánh giá cập nhật danh tính và SecurityContext.
Một ứng dụng truyền danh tính qua endpoint gateway rồi vào service nội bộ, nhưng test chỉ dựng SecurityContext tại service và bỏ qua bước xác thực đầu vào; hãy xây dựng tình huống kiểm chứng luồng tin cậy.
Một bài MockMvc dùng jwt() để gán JWT giả lập và truy cập API thành công, trong khi resource server production từ chối token do chữ ký sai; hãy đặt tình huống phân biệt kiểm thử phân quyền với xác thực token thật.
Một JWT từ nhà cung cấp danh tính chứa scope và roles ở claim tùy biến, nhưng mockJwt của test gán sẵn authority hợp lệ nên không phát hiện lỗi converter; hãy xây dựng tình huống kiểm tra ánh xạ claim.
Một API tài chính chỉ cho token có audience dành cho payments, nhưng bài test jwt() không kiểm tra audience và vẫn nhận HTTP 200; hãy đặt bài toán đánh giá phạm vi trách nhiệm của test giả lập.
Một token giả lập mang scope invoice.read nhưng API tạo hóa đơn dùng nhầm quyền đọc, khiến test chỉ kiểm tra trường hợp có cả hai scope vẫn xanh; hãy xây dựng tình huống kiểm chứng phân tách quyền đọc và ghi.
Một resource server hỗ trợ opaque token qua introspection nhưng nhóm test toàn bộ bằng JWT giả lập, khiến lỗi cấu hình endpoint introspection không được phát hiện; hãy đặt tình huống bổ sung ca tích hợp phù hợp.
Một API kiểm tra token đã hết hạn ở lớp xác thực JWT, nhưng test dùng jwt() với claim exp quá khứ và vẫn cho request đi qua; hãy yêu cầu đánh giá giới hạn của post-processor giả lập.
Một hệ thống thêm issuer tin cậy mới nhưng vô tình chấp nhận token từ issuer staging, trong khi test chỉ cung cấp danh tính có role; hãy xây dựng bài toán kiểm chứng cấu hình tin cậy.
Một client truyền Bearer token sai định dạng hoặc thiếu token, nhưng bộ test chỉ dùng jwt() để mô phỏng yêu cầu đã được xác thực; hãy đặt tình huống kiểm tra bộ lọc đầu vào.
Một endpoint đọc hồ sơ cần JWT với scope profile.read và subject trùng chủ sở hữu, nhưng bài test chỉ mô phỏng authority mà không tạo quan hệ với subject; hãy xây dựng tình huống kiểm chứng mức đối tượng.
Một JWT truy cập tenant B chứa cùng role với tenant A, nhưng dữ liệu kiểm thử đều thuộc tenant A nên không thấy lỗi cách ly; hãy đặt tình huống kiểm tra yêu cầu chéo tenant.
Một microservice chuyển từ vai trò lưu trong claim roles sang claim permissions, nhưng test chưa cập nhật fixture JWT theo token do IdP cấp; hãy xây dựng tình huống phát hiện hợp đồng claims thay đổi.
Một cổng API nhận JWT qua cookie thay vì Authorization header, nhưng bài test luôn cung cấp jwt() trực tiếp và bỏ qua đường nhận thông tin xác thực; hãy xây dựng tình huống kiểm tra luồng token thực tế.
Một endpoint yêu cầu xác thực bằng OAuth2 Login, nhưng test oauth2Login() chỉ giả lập đăng nhập thành công và bỏ qua lỗi redirect URI ở Authorization Server; hãy đặt tình huống xác định kiểm thử nào cần bao phủ.
Một trang quản lý hồ sơ hiển thị tên từ OAuth2User, nhưng test chỉ gán username mặc định và không tạo attributes giống nhà cung cấp; hãy xây dựng tình huống kiểm tra ánh xạ thuộc tính.
Một OAuth2 client được cấp access token với scope hạn chế, nhưng test oauth2Client() mặc định không phản ánh scope thực tế và vẫn gọi API đối tác thành công; hãy đặt bài toán kiểm chứng quyền ủy quyền.
Một ứng dụng OIDC sử dụng oidcLogin() để giả lập danh tính nhưng bộ test không chứa claim email_verified, khiến chính sách tạo tài khoản thử nghiệm không được xác thực đúng; hãy đặt tình huống kiểm chứng claims.
Một cổng OIDC ánh xạ vai trò từ claim groups trong ID token, nhưng test oidcLogin() đưa authority trực tiếp nên không phát hiện lỗi ánh xạ; hãy xây dựng tình huống đánh giá ranh giới giả lập.
Một client OIDC sau logout vẫn còn phiên tại Identity Provider, nhưng test chỉ xóa SecurityContext và cho rằng logout toàn hệ thống đã hoàn tất; hãy đặt tình huống xác định phạm vi kiểm thử.
Một màn hình OIDC cho phép đăng nhập bằng nhiều nhà cung cấp, nhưng test chỉ dùng provider mặc định khiến lỗi cấu hình registration phụ không xuất hiện; hãy xây dựng tình huống bao phủ nhiều client registration.
Một API yêu cầu nhận OAuth2 access token đại diện người dùng thật, nhưng bài test gán authentication machine-to-machine cùng scope và trả 200; hãy đặt tình huống phân biệt chủ thể và loại grant.
Một trang OAuth2 Login phải chuyển người dùng chưa đăng nhập sang IdP, nhưng test chỉ sử dụng oauth2Login() và không quan sát quá trình khởi tạo đăng nhập; hãy xây dựng tình huống kiểm chứng điểm bắt đầu luồng.
Một bộ test Resource Server sử dụng opaqueToken() để gán principal với authorities nhưng không kiểm tra phản hồi khi introspection trả inactive; hãy đặt tình huống đánh giá nhánh token không còn hiệu lực.
Một API truy vấn báo cáo dùng claims từ JWT để chọn chi nhánh, nhưng test chỉ assert HTTP 200 mà không đối chiếu dữ liệu chi nhánh được trả; hãy xây dựng tình huống phát hiện rò rỉ do ánh xạ claims.
Một dịch vụ dùng @AuthenticationPrincipal để truy cập OidcUser trong controller nhưng test gán JwtAuthenticationToken nên bị ClassCastException; hãy đặt tình huống kiểm tra loại authentication theo endpoint.
Một ứng dụng dùng JWT giả lập với thời hạn dài để test phân quyền nhưng không có ca tích hợp kiểm tra cấu hình JwtDecoder và JWK Set; hãy đặt bài toán xây dựng ranh giới kiểm thử.
Một tài khoản bị thu hồi quyền trên IdP nhưng access token JWT cũ còn hiệu lực, trong khi test luôn dựng mới authority mỗi request; hãy xây dựng tình huống kiểm tra chính sách thu hồi trong vòng đời token.
Một REST API dùng WebFlux SecurityWebFilterChain nhưng nhóm chỉ chạy MockMvc, khiến các route Reactive mới không được kiểm chứng; hãy đặt tình huống thiết kế ca WebTestClient phù hợp.
Một API Reactive yêu cầu xác thực trên GET /accounts, nhưng bài WebTestClient gắn mockUser() không tích hợp security config nên request ẩn danh vẫn lấy được dữ liệu; hãy xây dựng tình huống xác minh bộ lọc WebFlux.
Một endpoint WebFlux trả Mono chứa dữ liệu cá nhân, nhưng test chỉ kiểm tra HTTP status mà không kiểm tra việc lọc bản ghi theo principal; hãy đặt tình huống kiểm chứng nội dung response.
Một ứng dụng Reactive có endpoint POST sử dụng WebSession và CSRF, nhưng bài test chỉ gửi mockJwt() và bỏ qua nhánh cookie của trình duyệt; hãy xây dựng tình huống kiểm tra các cơ chế xác thực.
Một WebFlux gateway bị CORS preflight từ origin đối tác chặn trước xác thực, nhưng test chỉ gọi GET có mockUser() và không gửi OPTIONS; hãy đặt tình huống kiểm chứng đường tiền kiểm.
Một route Reactive cho phép nhiều authority nhưng test chỉ thử manager; hãy yêu cầu xây dựng ma trận request được phép và bị từ chối với mockUser() theo từng vai trò.
Một endpoint WebFlux dùng hasScope để kiểm tra quyền trong JWT, nhưng mockJwt() không mang scope như production mà test vẫn cấp trực tiếp authority; hãy xây dựng tình huống phát hiện khác biệt.
Một bài WebTestClient dùng mockOidcLogin() để truy cập trang cá nhân nhưng dữ liệu được trả dựa trên tenant trong claim tùy biến; hãy đặt tình huống kiểm chứng phân tách tenant.
Một ứng dụng WebFlux gọi service ngoài qua WebClient trong khi test mock authentication tại inbound request, nhưng outbound request thiếu thông tin được phép gửi; hãy đặt tình huống kiểm tra phạm vi truyền token.
Một request Reactive đi qua publishOn và method authorization chạy ở luồng khác, khiến SecurityContext không có trong Reactor Context như kỳ vọng; hãy xây dựng tình huống tái hiện bằng WebTestClient.
Một chương trình chuyển từ Spring MVC sang WebFlux nhưng vẫn dùng SecurityContextHolder trong service xử lý Reactive, khiến kết quả kiểm thử không ổn định; hãy đặt bài toán kiểm chứng nơi lưu ngữ cảnh.
Một endpoint Reactive xử lý lô giao dịch bằng Flux, trong đó một phần tử bị từ chối quyền sau khi phần tử đầu đã ghi dữ liệu; hãy xây dựng tình huống kiểm tra tác dụng phụ trong luồng bị hủy.
Một ứng dụng dùng WebTestClient kiểm thử POST hợp lệ nhưng không có tình huống thiếu CSRF token, khiến phép thử bỏ sót lỗi cấu hình trong WebFilter; hãy đặt bài toán hoàn chỉnh ca âm tính.
Một trang đăng nhập Reactive tạo WebSession sau xác thực, nhưng bài test chỉ gọi API với mockUser() và bỏ qua cookie thực tế; hãy xây dựng tình huống xác minh phiên xuyên nhiều request.
Một endpoint Reactive stream cập nhật quyền người dùng giữa luồng, nhưng test chỉ xem dữ liệu đầu tiên và không nhận ra phần tử về sau lộ dữ liệu; hãy đặt tình huống kiểm tra hành vi luồng nhiều phần tử.
Một route WebFlux có fallback trả thông tin nội bộ khi service chính lỗi, nhưng test phân quyền chỉ chạy nhánh thành công; hãy xây dựng tình huống kiểm chứng truy cập khi đi vào nhánh dự phòng.
Một hệ thống Hybrid có gateway Reactive và backend Servlet, trong đó request bị từ chối ở gateway nhưng backend vẫn cho truy cập trực tiếp; hãy đặt bài toán kiểm chứng phòng vệ ở cả hai tầng.
Một ứng dụng Reactive có hai SecurityWebFilterChain khác nhau theo đường dẫn, nhưng route mới của admin khớp vào chuỗi public; hãy xây dựng tình huống kiểm tra thứ tự matcher trên WebTestClient.
Một WebFlux handler trả lỗi 500 và mất security headers dù response bình thường có CSP; hãy đặt tình huống kiểm thử header trên nhánh exception.
Một ứng dụng có cả request HTTP và WebSocket cho dữ liệu phòng chat, nhưng test HTTP có quyền thành công không chứng minh subscription được bảo vệ; hãy xây dựng tình huống xác định phạm vi bảo mật cần kiểm chứng.
Một thay đổi cấu hình khiến endpoint sse Reactive cho khách vãng lai stream dữ liệu của nhân viên đăng nhập, trong khi bài test chỉ kiểm tra kết nối được mở; hãy đặt tình huống kiểm chứng dữ liệu qua SSE.
Một test WebFlux được viết bằng WebTestClient.bindToController không nạp cấu hình SecurityWebFilterChain, nhưng người viết kết luận route đã được bảo vệ; hãy đặt tình huống kiểm tra độ trung thực của test harness.
Một bộ kiểm thử WebFlux hoạt động khi chạy một mình nhưng thất bại ngẫu nhiên khi chạy song song do chia sẻ mock security context; hãy đặt tình huống đánh giá khả năng cô lập trạng thái.
Một dự án dùng hai profile bảo mật cho staging và production, nhưng các bài test MockMvc chỉ chạy profile development với toàn bộ request được phép; hãy xây dựng tình huống tổ chức kiểm chứng đúng cấu hình.
Một bài test chuyên biệt cho filter bảo mật xanh khi chạy độc lập, nhưng ứng dụng thật có thứ tự filter khác khiến request thiếu header vẫn lọt qua; hãy đặt tình huống xác định mức kiểm chứng tích hợp cần thiết.
Một nhóm thêm lớp filter ghi audit rồi thay đổi thứ tự so với Spring Security, khiến log không ghi được danh tính hoặc ghi nhầm request bị từ chối; hãy xây dựng tình huống kiểm tra thứ tự xử lý.
Một API hỗ trợ cả CORS và CSRF được sửa để mở thêm origin đối tác, nhưng test chỉ kiểm tra nguồn hợp lệ mà không xác minh người dùng của nguồn đó có quyền ghi; hãy xây dựng ca kết hợp.
Một tính năng đặt hàng yêu cầu quyền ORDER_WRITE nhưng test hiện chỉ xác minh có role và bỏ qua số tiền giới hạn theo cấp nhân viên; hãy đặt tình huống đánh giá kiểm chứng chính sách theo ngữ cảnh.
Một API đa tenant lấy tenant ID từ header do client gửi và bài test tạo người dùng cùng tenant với header, nên chưa phát hiện client tự chọn tenant người khác; hãy xây dựng ca truy cập trái phép.
Một hệ thống lưu tài liệu theo ACL nhưng test chỉ kiểm tra quyền truy cập vào controller, không thử object ID do người dùng khác sở hữu; hãy đặt bài toán kiểm chứng phân quyền ở cấp bản ghi.
Một trang liệt kê tài liệu áp dụng quyền người dùng vào kết quả truy vấn nhưng test chỉ assert số lượng khi tất cả dữ liệu có cùng chủ; hãy xây dựng tình huống đánh giá khả năng lọc không đúng.
Một hệ thống tự động hóa tạo test data toàn quyền để tránh lỗi 403, khiến nhiều endpoint không còn ca âm tính có ý nghĩa; hãy đặt tình huống đánh giá ma trận vai trò và quyền.
Một người dùng bị xóa khỏi nhóm trong lúc session vẫn còn, nhưng bộ test chỉ kiểm tra quyền lúc đăng nhập; hãy xây dựng tình huống xác minh cập nhật quyền theo thời gian.
Một tài khoản hỗ trợ khách hàng có quyền xem hồ sơ nhưng không có quyền xuất CSV, trong khi test chỉ kiểm tra request GET trả danh sách; hãy đặt tình huống kiểm chứng đường xuất dữ liệu.
Một ứng dụng có hai endpoint tương đương cho bản mobile và web, nhưng chỉ endpoint web được test CSRF và method security; hãy xây dựng tình huống thiết kế kiểm chứng nhất quán.
Một chức năng nhận file từ người dùng gửi request multipart chứa mã hồ sơ ngoài quyền sở hữu; bài test chỉ kiểm tra định dạng upload mà không kiểm tra ranh giới bản ghi; hãy đặt tình huống kiểm chứng.
Một hệ thống sử dụng HSTS, CSP và các header phòng vệ nhưng test chỉ kiểm tra trạng thái HTTP và bỏ qua phản hồi từ proxy; hãy đặt tình huống xác định bề mặt cần đo trong pipeline.
Một bộ kiểm thử lấy 403 làm kết quả mong đợi nhưng vẫn phát email và lưu audit success sau request bị chặn; hãy đặt tình huống kiểm tra trạng thái sau thao tác không được phép.
Một luồng xác thực cập nhật SecurityContext nhưng sau redirect tài khoản của người dùng trước vẫn xuất hiện trong session dùng chung của test; hãy xây dựng tình huống kiểm chứng cô lập phiên.
Một backend cấu hình httpBasic cho máy chủ nội bộ nhưng mobile app dùng bearer JWT, và test chỉ gán người dùng bằng annotation nên không phát hiện nhầm SecurityFilterChain; hãy xây dựng tình huống kiểm tra đường xác thực.
Một dự án áp dụng Testcontainers cho cơ sở dữ liệu quyền, nhưng test bảo mật vẫn mock repository khiến truy vấn thực tế thiếu tenant filter không bị phát hiện; hãy đặt bài toán đánh giá điểm cần tích hợp dữ liệu thật.
Một dịch vụ thuê ngoài yêu cầu bảo vệ quyền ở gateway và controller, nhưng test tại gateway chỉ kiểm tra 401 và chưa thử truy cập backend bỏ qua gateway; hãy xây dựng tình huống kiểm chứng phòng vệ nhiều lớp.
Một lần nâng cấp Spring Security thay đổi mặc định xử lý request matcher và gây lỗi với URL có dấu gạch chéo cuối, nhưng test chỉ gửi URL chuẩn; hãy đặt tình huống kiểm tra hồi quy.
Một lỗi ánh xạ quyền sau khi nâng cấp JwtAuthenticationConverter chỉ xuất hiện với claim roles là mảng, trong khi test JWT tạo claim thành chuỗi; hãy xây dựng tình huống so sánh fixture với dữ liệu thực tế.
Một bộ kiểm thử tích hợp chạy xanh trên laptop nhưng thất bại trên CI vì data fixture dùng clock hệ thống để tính thời hạn phiên; hãy đặt tình huống kiểm chứng tính tái lập theo thời gian.
Một suite test dùng chung MockMvc và trạng thái session giữa các phương thức, làm thứ tự chạy ảnh hưởng phản hồi đăng nhập; hãy đặt tình huống phát hiện sự phụ thuộc vào thứ tự.
Một đội phát triển tắt toàn bộ security filter trong bài test để tăng tốc pipeline, khiến việc mở endpoint nhạy cảm qua thay đổi cấu hình không bị phát hiện; hãy đặt tình huống đánh giá rủi ro và mức kiểm chứng.
Một ứng dụng dùng @WithMockUser cho mọi request trong MockMvc, nên ca kiểm tra truy cập ẩn danh vẫn xanh dù endpoint vô tình mở công khai; hãy xây dựng tình huống xác định ca âm tính thiếu.
Một endpoint phát token không nằm trong phạm vi spring-security-test thông thường và cần kiểm tra ký token thật, nhưng nhóm dùng JWT giả lập để kết luận toàn bộ quy trình OAuth an toàn; hãy đặt tình huống xác định phạm vi kiểm chứng.
Một pipeline có hàng trăm ca security test nhưng không phân biệt test phân quyền mô phỏng với test xác thực token thật, khiến báo cáo chất lượng gây hiểu nhầm; hãy xây dựng tình huống thiết kế tiêu chí báo cáo.
Một tổ chức yêu cầu chứng minh mọi API quản trị đều từ chối ẩn danh và nhân viên thường, nhưng hiện chỉ có ca happy path cho quản trị viên; hãy đặt bài toán lập ma trận kiểm thử quyền truy cập.
Một lỗ hổng cho phép sửa hồ sơ của người khác đã được vá, nhưng regression test chỉ kiểm tra chủ hồ sơ sửa thành công; hãy xây dựng tình huống ghi nhận ca tái hiện lỗi ban đầu.
Một endpoint mới cho phép xuất dữ liệu nhạy cảm được thêm vào hệ thống nhưng không có security test vì chưa được liệt kê trong danh sách thủ công; hãy đặt tình huống đánh giá độ bao phủ theo route.
Một báo cáo CI cho thấy số ca MockMvc tăng nhưng lỗi phân quyền production vẫn xảy ra ở luồng WebFlux, khiến nhóm cần phân bổ lại kiểm thử; hãy xây dựng tình huống đánh giá test coverage theo stack.
Một hệ thống đa môi trường có chính sách role khác nhau giữa staging và production, nhưng test sử dụng authority hardcode chung; hãy đặt tình huống kiểm chứng sự tương thích với cấu hình triển khai.
Một test security đã kiểm tra status 403 khi bị từ chối nhưng không xác minh response không lộ tên đầy đủ, email hoặc danh sách bản ghi; hãy xây dựng tình huống đánh giá bảo mật nội dung lỗi.
Một tổ chức nâng cấp OIDC provider và các claims danh tính thay đổi, nhưng bộ kiểm thử chỉ mock UserDetails chứ không chạy OAuth2/OIDC test support; hãy đặt tình huống cập nhật ma trận kiểm chứng.
Một hệ thống sử dụng login session cho web và JWT cho API, nhưng bộ kiểm thử không tách loại danh tính nên mọi test chỉ dùng cùng @WithMockUser; hãy xây dựng tình huống chọn fixture theo bối cảnh.
Một endpoint Reactive mới sử dụng authorization manager theo trạng thái đơn hàng, nhưng test WebTestClient chỉ kiểm tra người có authority mà không tạo đơn đã khóa; hãy đặt tình huống kiểm chứng dữ liệu nghiệp vụ.
Một thay đổi yêu cầu MFA cho thao tác chuyển tiền nhưng regression test chỉ chứng minh người dùng đã đăng nhập có quyền; hãy xây dựng tình huống kiểm chứng mức xác thực và kết quả bị từ chối.
Một nhóm muốn đảm bảo request bị từ chối không làm thay đổi database, thông điệp gửi đi hoặc cache, nhưng test hiện chỉ so sánh mã HTTP; hãy đặt bài toán xác định phép quan sát tác dụng phụ.
Một hệ thống đa tenant cho phép user thuộc hai tenant đăng nhập bằng OIDC, nhưng test chỉ dùng một cấu hình subject và không kiểm tra tenant hiện hành; hãy xây dựng tình huống kiểm tra ngữ cảnh người dùng.
Một công ty yêu cầu kiểm tra toàn bộ đường truy cập file gồm REST API, link download và trình xem trước, nhưng security test chỉ bảo vệ API danh sách; hãy đặt tình huống lập ca kiểm chứng các đường vào tương đương.
Một nhóm tạo custom WithSecurityContextFactory dùng principal giả lập, nhưng factory không dọn ngữ cảnh khi test thất bại nên một ca sau nhận quyền quản trị; hãy đặt tình huống kiểm tra tính cô lập fixture.
Một API dùng Bearer token thật đi qua gateway nhưng test MockMvc chạy sau gateway và gán JWT giả, khiến lỗi loại bỏ Authorization header ở gateway không được phát hiện; hãy xây dựng tình huống kiểm chứng end-to-end.
Một đợt triển khai dùng session cookie mới làm các phép thử MockMvc vẫn xanh nhưng người dùng thật bị chuyển về login sau mỗi request, vì test không mô phỏng cookie xuyên nhiều request; hãy đặt tình huống xây dựng ca hành trình.
Một dự án ghi nhận nhiều lỗi kiểm thử bảo mật giả vì WebTestClient chạy với SecurityWebFilterChain khác ứng dụng thật, nhưng chưa có tài liệu phân biệt các mode bind; hãy đặt bài toán xác minh harness.
Một nhóm muốn dùng cùng bảng yêu cầu quyền cho kiểm thử Servlet và Reactive nhưng cấu hình thực thi khác nhau ở hai stack, dẫn đến kết quả trái ngược trên cùng API logic; hãy xây dựng tình huống đối chiếu.
Một báo cáo kiểm toán phát hiện thiếu ca kiểm thử token bị vô hiệu hóa, truy cập chéo tenant, CSRF và lỗi ngữ cảnh Reactive dù toàn bộ test hiện đều xanh; hãy đặt tình huống ưu tiên hoàn thiện kiểm thử.
