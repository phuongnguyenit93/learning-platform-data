Một ứng dụng SaaS đăng ký OAuth client cho cổng quản trị nhưng sử dụng redirect URI của môi trường thử nghiệm khi chạy production; hãy xây dựng tình huống kiểm chứng đăng ký client và xử lý phản hồi ủy quyền.
Một ứng dụng di động không thể giữ bí mật client secret nhưng đội phát triển vẫn cấu hình client như ứng dụng bí mật; hãy đặt bài toán đánh giá kiểu client và chính sách luồng ủy quyền.
Một SPA chuyển từ implicit flow sang Authorization Code với PKCE nhưng cấu hình client vẫn cho phép các kiểu cấp quyền cũ; hãy xây dựng tình huống kiểm chứng phạm vi grant được chấp thuận.
Nền tảng B2B cho phép mỗi đối tác tự đăng ký nhiều redirect URI, trong đó một URI được nhập dưới dạng wildcard; hãy yêu cầu phân tích nguy cơ chuyển hướng mã ủy quyền sang đích ngoài ý muốn.
Một đối tác thay đổi tên miền callback sau khi chuyển nhà cung cấp hạ tầng, khiến các lần đăng nhập mới thất bại dù client vẫn còn hiệu lực; hãy đặt tình huống kiểm tra dữ liệu RegisteredClient và luồng chuyển hướng.
Hai môi trường staging và production chia sẻ cùng client ID nhưng dùng các chính sách scope và redirect URI khác nhau; hãy xây dựng bài toán kiểm chứng cách cô lập cấu hình giữa môi trường.
Hệ thống đa tenant dùng một client registration chung cho các công ty, nhưng chính sách consent cần tách biệt từng tenant; hãy đặt tình huống kiểm chứng ranh giới dữ liệu cấp quyền.
Một ứng dụng nội bộ trước đây chỉ có quyền đọc danh bạ nhưng bản phát hành mới yêu cầu thêm quyền xuất toàn bộ dữ liệu; hãy xây dựng ca xem xét thay đổi scope trong cấu hình client.
Một client từng được phép dùng Client Credentials để đọc dữ liệu máy chủ nay cần tác vụ thay mặt người dùng; hãy đặt tình huống đánh giá luồng cấp quyền và ngữ cảnh người sử dụng.
Đội vận hành thu hồi một client không còn hợp đồng nhưng các phiên truy cập hiện tại vẫn còn token đã phát; hãy xây dựng tình huống kiểm tra tác động của việc vô hiệu hóa client.
Một client bí mật được cấp secret có hạn sử dụng nhưng bộ đồng bộ chứng từ vẫn thử xác thực bằng secret cũ sau ngày hết hạn; hãy đặt bài toán kiểm tra điều kiện xác thực và chẩn đoán lỗi.
Hai đối tác được đăng ký với cùng tên hiển thị nhưng chính sách redirect và scope khác nhau; hãy xây dựng tình huống nhận diện đúng client trong màn hình consent và nhật ký hệ thống.
Một dịch vụ backend gửi thông tin xác thực client qua HTTP form trong khi server chỉ chấp nhận cách xác thực khác đã đăng ký; hãy đặt tình huống kiểm chứng sự khớp của phương thức xác thực client.
Một tổ chức luân chuyển client secret theo lịch, nhưng dịch vụ chạy nhiều phiên bản chưa đồng loạt áp dụng secret mới; hãy yêu cầu xây dựng kịch bản kiểm thử giai đoạn chuyển đổi cấu hình.
Client mới được tạo trong cơ sở dữ liệu quản trị nhưng Authorization Server vẫn nhận chính sách cũ do cache trong một node; hãy đặt tình huống kiểm tra tính nhất quán khi thay đổi RegisteredClient.
Một nhà phát triển vô tình đưa client secret vào gói JavaScript của trình duyệt, trong khi backend vẫn xem đây là confidential client; hãy xây dựng bài toán đánh giá ranh giới bảo mật của ứng dụng.
Một client gửi grant type không được đăng ký nhưng máy chủ vẫn có các endpoint chung cho nhiều luồng; hãy đặt tình huống xác minh quyết định cấp quyền đúng với từng client.
Hệ thống cấp phạm vi truy cập báo cáo theo hợp đồng đối tác, nhưng client đăng ký scope lớn hơn hợp đồng đang có hiệu lực; hãy yêu cầu phân tích cách kiểm chứng việc đăng ký quyền và quyền thực tế.
Một đối tác gửi redirect URI có khác biệt nhỏ về chữ hoa, port hoặc đường dẫn so với URI đã đăng ký; hãy xây dựng tình huống kiểm tra việc đối chiếu URI trong yêu cầu ủy quyền.
Ứng dụng nội bộ dùng một client ID cho cả web và mobile, khiến hai loại ứng dụng có yêu cầu xác thực và PKCE khác nhau; hãy đặt bài toán đánh giá rủi ro từ cách đăng ký client.
Một ứng dụng kế toán mở luồng Authorization Code nhưng tham số state bị mất khi quay lại callback, khiến hệ thống không thể liên kết phản hồi với yêu cầu ban đầu; hãy xây dựng ca kiểm thử.
Một attacker có thể thử đưa mã ủy quyền nhận từ một phiên đăng nhập vào callback của phiên khác; hãy đặt tình huống kiểm chứng khả năng gắn kết phản hồi với phiên yêu cầu.
Ứng dụng di động gửi code challenge theo PKCE nhưng code verifier ở bước đổi mã bị thay đổi sau khi chuyển ứng dụng sang background; hãy xây dựng ca kiểm tra lỗi đổi mã.
Một client công khai gửi yêu cầu ủy quyền không có PKCE dù chính sách bắt buộc dùng PKCE; hãy đặt bài toán xác minh hành vi Authorization Server khi nhận thiếu tham số.
Một luồng đăng nhập sử dụng PKCE với challenge method khác với phương thức mà client được phép dùng; hãy xây dựng tình huống kiểm tra tính hợp lệ của tham số và nguy cơ hạ mức bảo vệ.
Trong luồng Authorization Code, mã ủy quyền được dùng thành công một lần nhưng ứng dụng gửi lại yêu cầu đổi mã do timeout mạng; hãy đặt tình huống kiểm chứng xử lý tái sử dụng mã.
Mã ủy quyền được phát cho callback của cổng web nhưng được gửi tới token endpoint kèm redirect URI của cổng mobile; hãy xây dựng ca đánh giá điều kiện ràng buộc khi đổi mã.
Một người dùng mất nhiều phút xác thực đa yếu tố khiến mã ủy quyền đến thời điểm đổi mã đã quá hạn; hãy yêu cầu kiểm chứng thời gian sống và thông điệp lỗi phù hợp.
Hai tab trình duyệt đồng thời hoàn tất đăng nhập cùng một client, nhưng ứng dụng chỉ lưu một trạng thái giao dịch OAuth; hãy đặt bài toán kiểm tra việc phân biệt từng yêu cầu ủy quyền.
Một ứng dụng thay đổi scope giữa bước yêu cầu authorization code và bước đổi code lấy token; hãy xây dựng tình huống đánh giá giới hạn phạm vi được cấp qua toàn bộ luồng.
Người dùng bắt đầu đăng nhập ở tenant A nhưng đến callback client tự đổi tenant sang B trước khi đổi mã; hãy đặt bài toán xác minh sự ràng buộc ngữ cảnh trong giao dịch ủy quyền.
Một ứng dụng bị lỗi callback liên tục khởi động lại luồng đăng nhập và tạo nhiều yêu cầu cấp quyền chưa hoàn tất; hãy xây dựng tình huống quan sát khả năng xử lý vòng lặp.
Nhóm tích hợp muốn dùng Resource Owner Password Credentials cho ứng dụng mới dù hệ thống theo hướng OAuth 2.0 hiện đại; hãy đặt bài toán đánh giá tính phù hợp và phạm vi hỗ trợ của Authorization Server.
Một backend kết nối hệ thống kế toán bằng Client Credentials nhưng lại mong nhận thông tin danh tính của người dùng cuối trong token; hãy xây dựng tình huống kiểm chứng ngữ nghĩa của luồng cấp quyền.
Một hệ thống thanh toán yêu cầu quyền người dùng nhưng client chỉ gửi Client Credentials để gọi API duyệt giao dịch; hãy đặt tình huống phân biệt quyền ứng dụng và quyền được ủy quyền bởi người dùng.
Một thiết bị TV không có bàn phím cần luồng xác thực trên điện thoại, nhưng ứng dụng liên tục gửi yêu cầu polling tới token endpoint; hãy xây dựng ca kiểm thử quá trình cấp quyền cho thiết bị.
Người dùng nhập nhầm mã xác minh của thiết bị vào phiên của một thiết bị khác và xác nhận quyền; hãy đặt tình huống kiểm tra sự liên kết giữa thiết bị, người dùng và yêu cầu ủy quyền.
Một yêu cầu cấp quyền cho thiết bị đã hết hạn nhưng máy khách vẫn tiếp tục polling như đang chờ chấp thuận; hãy yêu cầu xây dựng kịch bản phân biệt trạng thái chờ, hết hạn và bị từ chối.
Một máy khách chưa được phép dùng device authorization vẫn cố kích hoạt luồng cấp quyền thiết bị; hãy đặt bài toán kiểm chứng quyền sử dụng grant theo cấu hình đã đăng ký.
Một thiết bị tại điểm bán bị mất trong lúc chờ nhân viên chấp thuận quyền; hãy xây dựng tình huống đánh giá trạng thái ủy quyền và khả năng ngăn thiết bị cũ nhận token.
Một ứng dụng ngân hàng yêu cầu quyền đọc tài khoản nhưng trang consent hiển thị nội dung khó hiểu khiến người dùng không nhận ra phạm vi dữ liệu; hãy xây dựng bài toán kiểm chứng thông tin đồng ý.
Một khách hàng từ chối cấp quyền truy cập lịch sử giao dịch trong màn hình consent, nhưng ứng dụng lại tiếp tục như đã được chấp thuận; hãy đặt tình huống kiểm thử nhánh từ chối cấp quyền.
Ứng dụng từng được người dùng đồng ý scope đọc thông tin, sau khi cập nhật yêu cầu thêm quyền chuyển khoản thì trang consent không xuất hiện; hãy xây dựng ca kiểm tra thay đổi phạm vi đã duyệt.
Một người dùng rút lại consent với ứng dụng đối tác, trong khi ứng dụng vẫn giữ refresh token đã được cấp trước đó; hãy yêu cầu đánh giá tác động thu hồi consent đến các phiên ủy quyền.
Một tài khoản đăng nhập vào hai tenant khác nhau và chấp thuận cùng một client, nhưng hệ thống dùng chung bản ghi consent cho cả hai; hãy xây dựng tình huống kiểm tra cô lập dữ liệu đồng ý.
Ứng dụng nội bộ được miễn consent theo chính sách tổ chức, nhưng client vừa được chuyển quyền sở hữu sang đối tác ngoài doanh nghiệp; hãy đặt bài toán kiểm chứng lại điều kiện miễn consent.
Sau khi lưu consent vào cơ sở dữ liệu, màn hình người dùng hiển thị một tập scope khác với tập đã cấp trong access token; hãy đặt tình huống đối chiếu dữ liệu đã đồng ý và quyền thực tế.
Một client bị đổi tên và mô tả sau khi người dùng đã chấp thuận quyền, khiến họ không nhận ra ứng dụng trong danh sách consent hiện có; hãy xây dựng bài toán đánh giá dấu vết cấp quyền.
Hệ thống cho phép quản trị viên xem lịch sử đồng ý nhưng bản ghi audit vô tình chứa mã ủy quyền và token; hãy đặt tình huống kiểm chứng yêu cầu bảo mật trong nhật ký consent.
Một tài khoản bị khóa sau khi từng cấp consent dài hạn cho ứng dụng di động; hãy xây dựng tình huống kiểm tra chính sách truy cập lại khi trạng thái người dùng thay đổi.
Một khách hàng đăng nhập qua OIDC nhưng client chỉ được đăng ký scope cho OAuth API, dẫn tới thiếu thông tin danh tính mong đợi; hãy đặt bài toán kiểm tra phạm vi và cấu hình client.
Ứng dụng đăng nhập qua OIDC gửi nonce trong yêu cầu nhưng ID token trả về không phù hợp với giá trị đã lưu phía client; hãy xây dựng tình huống đánh giá tính toàn vẹn của luồng xác thực.
Một client nhận ID token hợp lệ về chữ ký nhưng có audience trỏ tới một ứng dụng khác cùng công ty; hãy xây dựng ca kiểm thử xác thực ID token đúng người nhận.
Ứng dụng chỉ kiểm tra thời hạn ID token nhưng bỏ qua issuer, trong khi môi trường thử nghiệm và production dùng hai Authorization Server khác nhau; hãy đặt tình huống xác minh nguồn phát hành.
Một người dùng đăng nhập qua SSO rồi truy cập ứng dụng nhạy cảm yêu cầu xác thực mới, nhưng màn hình đăng nhập được bỏ qua nhờ phiên cũ; hãy đặt bài toán kiểm chứng yêu cầu xác thực lại.
Cổng khách hàng dùng tham số max_age để hạn chế độ cũ của lần xác thực, nhưng phiên trình duyệt đã tồn tại nhiều giờ; hãy xây dựng tình huống kiểm tra thời điểm xác thực ghi nhận trong ID token.
Một client muốn yêu cầu prompt theo luồng OIDC nhưng người dùng đang có phiên đăng nhập và chưa chấp thuận quyền mới; hãy đặt tình huống phân biệt trạng thái xác thực và consent.
Ứng dụng OIDC dùng UserInfo endpoint để đọc tên hiển thị, nhưng access token hiện không được cấp các scope cần cho thuộc tính này; hãy xây dựng ca kiểm chứng thông tin trả về theo quyền.
Một khách hàng thay đổi email nhưng ứng dụng phụ vẫn coi email là khóa định danh duy nhất của tài khoản OIDC; hãy đặt bài toán kiểm chứng lựa chọn định danh ổn định khi nhận claims.
Ứng dụng nhận claim email_verified không phù hợp với trạng thái xác minh thực tế của tài khoản, khiến client tự động cấp quyền nhạy cảm; hãy xây dựng tình huống kiểm tra tính nhất quán claims.
Hai client cùng thuộc một tổ chức nhưng chính sách hạn chế khả năng liên kết danh tính người dùng giữa các dịch vụ; hãy yêu cầu phân tích thiết kế và kiểm chứng giá trị subject trong OIDC.
Một ứng dụng đăng xuất bằng cơ chế OIDC nhưng chỉ xóa cookie ở client, còn phiên đăng nhập tại Authorization Server vẫn hoạt động; hãy đặt tình huống kiểm thử mong đợi của quy trình logout.
Một người dùng mở hai ứng dụng dựa trên cùng Authorization Server và logout khỏi một ứng dụng, nhưng đội phát triển chưa thống nhất phạm vi logout; hãy xây dựng bài toán kiểm tra hành vi phiên đăng nhập.
Một client OIDC lấy metadata discovery qua gateway có URL công khai khác host nội bộ, dẫn đến issuer và endpoint không khớp khi xác thực token; hãy đặt tình huống chẩn đoán.
Một ứng dụng kiểm tra thông tin khám phá OIDC nhưng danh sách thuật toán ký và grant được công bố không phù hợp cấu hình đang chạy; hãy xây dựng tình huống kiểm chứng tính chính xác metadata.
Một client sử dụng thông tin JWKS được cache trước đợt luân chuyển khóa nên không xác thực được ID token mới; hãy đặt bài toán quan sát việc cập nhật khóa ký trên đường đọc metadata.
Một người dùng có nhiều nhóm quyền nhưng các claims đưa vào ID token chứa cả thông tin nội bộ không cần thiết cho đăng nhập; hãy xây dựng tình huống đánh giá giới hạn dữ liệu danh tính.
Một client chỉ được phép đọc hồ sơ cơ bản, nhưng endpoint UserInfo vô tình trả về số định danh nhạy cảm từ hồ sơ người dùng; hãy xây dựng ca kiểm tra ranh giới claims được công bố.
Một client cũ dùng OAuth access token để suy ra việc người dùng đã đăng nhập thay vì xử lý ID token OIDC; hãy đặt tình huống kiểm chứng phân biệt mục đích sử dụng các token.
API tài nguyên nhận JWT có chữ ký hợp lệ nhưng scope không cho phép thực hiện thao tác ghi; hãy xây dựng tình huống kiểm thử việc phát hành token và quyết định bảo vệ tài nguyên.
Một access token được cấp cho dịch vụ phân tích nhưng được trình tới API thanh toán cùng issuer; hãy đặt bài toán xác minh ràng buộc audience của token với tài nguyên đích.
Một đối tác yêu cầu scope rộng hơn tập đã đăng ký trong lúc đổi mã lấy token, nhưng response vẫn chứa scope ngoài hợp đồng; hãy xây dựng tình huống kiểm chứng giới hạn quyền cấp.
Ứng dụng cần access token mang mã tenant đang chọn, nhưng khi người dùng chuyển tenant token cũ vẫn được dùng để gọi API tenant mới; hãy đặt tình huống đánh giá ngữ cảnh token.
Một client lấy token được tùy biến thêm vai trò nghiệp vụ nhưng bộ phận bảo mật phát hiện quyền không phản ánh thay đổi mới của tài khoản; hãy xây dựng bài toán kiểm chứng độ mới của claims.
Một hệ thống dùng opaque access token và resource server gọi introspection, nhưng khi Authorization Server tạm mất kết nối API vẫn xử lý yêu cầu với dữ liệu quyền cũ; hãy đặt tình huống kiểm thử lỗi hạ tầng.
Một API vốn xác thực JWT cục bộ được chuyển sang token tham chiếu, khiến bộ xác thực tài nguyên từ chối mọi request hợp lệ; hãy đặt tình huống kiểm chứng hợp đồng định dạng access token.
Một access token còn trong hạn nhưng quyền người dùng vừa bị thu hồi do phát hiện gian lận; hãy xây dựng tình huống đánh giá yêu cầu thu hồi và độ trễ có thể chấp nhận.
Một người dùng chia sẻ access token cho ứng dụng thứ ba, khiến request được gửi từ nguồn không mong đợi trong thời hạn token; hãy đặt bài toán đánh giá nguy cơ dùng lại bearer token.
Một JWT access token chứa nhiều quyền và thông tin hồ sơ làm kích thước header HTTP vượt giới hạn gateway; hãy xây dựng ca kiểm tra thiết kế claims và giới hạn hạ tầng.
Hệ thống cấp token cho hai nhóm API có chính sách thời gian sống khác nhau, nhưng client đang dùng chung cấu hình token cho mọi nghiệp vụ; hãy đặt tình huống kiểm tra hạn sử dụng theo loại client.
Ứng dụng di động được cấp refresh token để duy trì phiên, nhưng sau khi thiết bị bị đánh dấu mất thì refresh token vẫn đổi được access token; hãy đặt bài toán kiểm tra chính sách thu hồi.
Một client sử dụng refresh token rotation nhưng sau timeout mạng gửi lại refresh token cũ và nhận kết quả khác dự kiến; hãy xây dựng tình huống kiểm chứng xử lý sử dụng lại token.
Hai tiến trình trên cùng thiết bị đồng thời dùng một refresh token để lấy access token mới, dẫn tới xung đột trạng thái phiên; hãy yêu cầu xây dựng kịch bản kiểm thử tính đồng thời.
Một ứng dụng quản lý bán hàng giữ refresh token quá lâu trong môi trường chia sẻ máy tính và nhân viên đã nghỉ việc vẫn có thể mở phiên; hãy đặt bài toán đánh giá vòng đời cấp quyền.
Một client bị thay đổi chính sách không còn được cấp refresh token, nhưng authorization cũ vẫn chứa refresh token có thể sử dụng; hãy xây dựng tình huống kiểm chứng hiệu lực chính sách mới.
Một khách hàng logout khỏi ứng dụng nhưng refresh token lưu trên máy chủ chưa bị xử lý theo kỳ vọng sản phẩm; hãy đặt tình huống kiểm thử ranh giới giữa kết thúc phiên và thu hồi token.
Một đối tác gửi refresh token của client A tới token endpoint với thông tin xác thực của client B; hãy xây dựng tình huống kiểm chứng liên kết token với client ban đầu.
Một refresh token hết hạn được trình lên endpoint đổi token trong khi access token cũ vẫn còn hiệu lực; hãy đặt bài toán phân biệt kết quả theo từng loại token.
Một access token được đánh dấu thu hồi trong kho dữ liệu nhưng resource server vẫn chấp nhận JWT tự xác thực tới khi hết hạn; hãy xây dựng tình huống đánh giá giới hạn khả năng thu hồi ngay.
Một ứng dụng gửi lệnh thu hồi token nhưng không chứng minh được quyền của client với token đích; hãy đặt tình huống kiểm tra xác thực client và xử lý yêu cầu thu hồi.
Một resource server gọi introspection với thông tin xác thực không hợp lệ nhưng vẫn nhận được metadata token từ hệ thống giám sát; hãy xây dựng ca kiểm chứng bảo vệ dữ liệu tại endpoint introspection.
Một Authorization Server ký token bằng khóa mới nhưng metadata JWK Set chưa kịp xuất bản khóa công khai tương ứng; hãy đặt bài toán kiểm thử giai đoạn chuyển khóa ký.
Một nhóm vận hành xóa khóa ký cũ ngay khi thêm khóa mới, khiến nhiều token còn hiệu lực bị resource server từ chối; hãy xây dựng tình huống đánh giá vòng đời khóa.
Hai key trong bộ JWK dùng cùng key ID sau khi đồng bộ từ hai cụm máy chủ, khiến trình xác thực chọn khóa sai; hãy đặt tình huống kiểm chứng tính nhất quán định danh khóa.
Một khóa bí mật dùng để ký token vô tình xuất hiện trong phản hồi endpoint công bố khóa công khai; hãy xây dựng tình huống kiểm tra dữ liệu được xuất bản từ JWK Set.
Một nhà cung cấp HSM gặp sự cố tạm thời và Authorization Server không thể ký token mới, trong khi các token đã cấp vẫn đang được sử dụng; hãy xây dựng ca kiểm thử hành vi khi phụ thuộc ký khóa lỗi.
Đồng hồ của một node Authorization Server chậm hơn resource server vài phút nên token vừa phát bị báo chưa có hiệu lực; hãy đặt tình huống kiểm chứng claim thời gian và sai lệch đồng hồ.
Một môi trường thử nghiệm sao chép khóa ký production để kiểm thử nhanh, khiến token phát ở môi trường này có thể bị nhầm với token thật; hãy đặt bài toán đánh giá ranh giới khóa và issuer.
Một client xác thực bằng private_key_jwt nhưng JWT assertion có thời gian phát hành sai và định danh người nhận không khớp endpoint; hãy xây dựng tình huống kiểm tra bằng chứng xác thực.
Một token được ký bằng thuật toán khác so với thuật toán mà resource server được cấu hình chấp nhận; hãy đặt tình huống xác minh khả năng tương thích thuật toán và chính sách tin cậy.
Dịch vụ phát hành JWT cho hàng nghìn yêu cầu mỗi giây nhưng thao tác truy cập khóa ký trở thành điểm nghẽn, làm tăng lỗi timeout; hãy yêu cầu đánh giá độ trễ và khả năng chịu tải khi ký.
Một Authorization Server chạy nhiều replica nhưng mỗi replica sinh khóa ký riêng khi khởi động, khiến token phát ở replica này bị xác thực thất bại sau khi chuyển replica; hãy xây dựng bài toán kiểm chứng.
Sau khi thay đổi cổng API qua reverse proxy, Authorization Server công bố issuer theo địa chỉ nội bộ nên nhiều client báo lỗi issuer mismatch; hãy đặt tình huống kiểm tra cấu hình địa chỉ phát hành.
Một node cấp token nhưng node khác chưa đọc được authorization vừa tạo do độ trễ sao chép cơ sở dữ liệu; hãy xây dựng tình huống kiểm tra tính nhất quán giữa các replica.
Ứng dụng lưu RegisteredClient bằng bộ nhớ khi phát triển và triển khai hai replica production, khiến mỗi replica nhận ra danh sách client khác nhau; hãy đặt bài toán kiểm chứng lớp lưu trữ.
Một đợt triển khai mới thay đổi cấu trúc dữ liệu OAuth2Authorization trong database, nhưng một replica cũ vẫn đang xử lý refresh token; hãy xây dựng tình huống kiểm thử tương thích dữ liệu.
Một yêu cầu đổi authorization code lấy token bị hai request đồng thời xử lý trên hai replica, làm xuất hiện kết quả cấp token trùng hoặc lỗi không nhất quán; hãy đặt bài toán đánh giá giao dịch.
Máy chủ gặp sự cố ngay sau khi lưu authorization nhưng trước khi trả token cho client, khiến client gửi lại yêu cầu; hãy xây dựng ca kiểm thử trạng thái dữ liệu sau lỗi giữa chừng.
Một hệ thống di trú từ Authorization Server cũ lưu consent dưới dạng khác, khiến người dùng phải cấp quyền lại hoặc nhận scope ngoài mong đợi; hãy đặt tình huống đánh giá tính tương thích dữ liệu.
Bảng lưu authorization tăng nhanh do các token đã hết hạn vẫn tồn tại nhiều tháng, khiến token endpoint chậm trong giờ cao điểm; hãy xây dựng bài toán kiểm tra vòng đời dữ liệu lưu trữ.
Một thao tác thu hồi authorization đã hoàn tất trên database chính nhưng replica đọc của introspection chưa cập nhật; hãy đặt tình huống kiểm chứng mức độ nhất quán phù hợp yêu cầu bảo mật.
Một Authorization Server đa tenant dùng khóa tra cứu authorization thiếu tenant ID, khiến bản ghi của các tổ chức có thể bị nhầm; hãy xây dựng tình huống xác minh cách ly dữ liệu.
Một hệ thống chạy với database read-only trong quá trình bảo trì, khiến quy trình đăng nhập vẫn xác thực người dùng nhưng không lưu được consent mới; hãy đặt tình huống đánh giá lỗi cấp quyền.
Một đợt backup phục hồi dữ liệu authorization về thời điểm cũ, khiến refresh token đã thu hồi xuất hiện trở lại; hãy xây dựng tình huống kiểm thử hệ quả bảo mật của phục hồi dữ liệu.
Một dịch vụ lưu token tùy biến làm mất thông tin metadata cần cho introspection sau khi deploy, khiến token hợp lệ bị báo không hoạt động; hãy xây dựng bài toán kiểm chứng tương thích dữ liệu.
Một request authorization đi qua reverse proxy chỉ hỗ trợ HTTPS công khai, nhưng ứng dụng nhận scheme HTTP nội bộ khi tạo URL; hãy đặt tình huống kiểm tra liên kết và endpoint công bố.
Đội phát triển để trang consent và trang đăng nhập tùy biến ngoài phạm vi bảo vệ CSRF, khiến trình duyệt có thể gửi yêu cầu không mong muốn; hãy xây dựng bài toán đánh giá bảo vệ thao tác.
Một endpoint token vô tình được cấu hình tiếp nhận HTTP không mã hóa trên mạng nội bộ mà các proxy có thể đọc thông tin xác thực client; hãy đặt tình huống kiểm tra đường truyền.
Người dùng gặp lỗi redirect URI không hợp lệ trong yêu cầu authorization, nhưng trang lỗi cố gắng chuyển hướng tới URI do client cung cấp; hãy xây dựng tình huống đánh giá phản hồi lỗi.
Một công cụ giám sát vô tình ghi toàn bộ request đến token endpoint, bao gồm client secret và refresh token, vào hệ thống log tập trung; hãy đặt tình huống kiểm tra khả năng rò rỉ bí mật.
Một kẻ tấn công thử hàng loạt client ID và secret tại token endpoint, gây tăng tải cơ sở dữ liệu mà không ảnh hưởng endpoint khác; hãy xây dựng kịch bản quan sát và kiểm thử giới hạn tài nguyên.
Một ứng dụng có trang đăng nhập chung cho người dùng thường và quản trị viên, nhưng yêu cầu xác thực đa yếu tố của quản trị viên không được áp dụng trong một số luồng OAuth; hãy đặt tình huống kiểm chứng.
Một client OIDC gửi tham số đăng nhập bất thường nhằm bỏ qua bước consent mà ứng dụng khác phải thực hiện; hãy xây dựng ca kiểm tra chính sách tương tác của người dùng.
Một máy chủ dùng session cookie để xác thực người dùng ở authorization endpoint nhưng cookie có phạm vi domain rộng và chia sẻ với ứng dụng không liên quan; hãy đặt bài toán đánh giá ranh giới phiên.
Một thay đổi quy tắc truy cập làm endpoint JWK Set bị yêu cầu đăng nhập, khiến resource server không thể cập nhật khóa công khai; hãy xây dựng tình huống kiểm thử khả năng truy cập endpoint công bố.
Một endpoint quản trị client được thêm cạnh các endpoint OAuth công khai nhưng không có phân quyền riêng, cho phép tài khoản thường sửa redirect URI; hãy xây dựng ca kiểm chứng cách ly chức năng quản trị.
Một backend quản trị đổi scope của client mà không ghi nhận người thao tác, khiến đội bảo mật không xác định được ai đã cấp quyền mới; hãy đặt tình huống đánh giá dấu vết thay đổi cấu hình.
Một yêu cầu introspection được gửi tới node đang quá tải, làm thời gian xác thực tại các API tài nguyên tăng đột biến; hãy xây dựng tình huống kiểm thử tác động lan truyền.
Một chiến dịch khuyến mãi tạo đột biến số lượt đăng nhập, khiến cơ sở dữ liệu consent và authorization trở thành nút nghẽn; hãy đặt bài toán đo khả năng cấp token dưới tải.
Một cơ chế rate limit nhầm nhiều người dùng hợp lệ sau cùng một NAT thành một client đáng ngờ, khiến luồng đăng nhập bị từ chối hàng loạt; hãy xây dựng tình huống đánh giá giới hạn truy cập.
Một Authorization Server hoạt động sau proxy WAF nhưng WAF sửa hoặc loại bỏ tham số PKCE trong request, khiến chỉ một số client đăng nhập thất bại; hãy đặt tình huống chẩn đoán liên tầng.
Một đội phát triển chỉ kiểm thử phản hồi thành công của Authorization Code nhưng bỏ qua trường hợp client giả, redirect URI sai và code dùng lại; hãy xây dựng tình huống thiết kế kiểm thử âm tính.
Bộ kiểm thử tự động dùng cùng một account và consent giữa các lần chạy nên kết quả luồng OIDC phụ thuộc thứ tự test; hãy đặt bài toán kiểm tra tính cô lập dữ liệu và phiên.
Một bài test PKCE chỉ xác nhận đổi mã thành công với verifier đúng, còn verifier sai vẫn chưa được đưa vào bộ hồi quy; hãy xây dựng tình huống đánh giá mức độ bao phủ của kiểm thử.
Bộ kiểm thử token chỉ đọc claim và bỏ qua kiểm chứng chữ ký, issuer và audience, khiến một lỗi cấu hình khóa không được phát hiện; hãy đặt tình huống kiểm thử từ góc nhìn resource server.
Một đợt nâng cấp Spring Authorization Server thay đổi cấu hình endpoint và metadata, nhưng đội phát triển chỉ chạy unit test cho service lưu client; hãy xây dựng bài toán kiểm chứng luồng tích hợp.
Một trường hợp consent bị từ chối trong test vẫn tạo bản ghi authorization đã cấp scope, nhưng test chỉ kiểm tra URL callback; hãy xây dựng tình huống kiểm chứng trạng thái lưu trữ sau nhánh lỗi.
Một pipeline CI sử dụng bộ khóa ký và client secret chung với môi trường thử nghiệm, gây va chạm khi nhiều nhánh chạy test song song; hãy đặt tình huống xác minh tính độc lập của môi trường kiểm thử.
Một bộ kiểm thử chỉ dùng client bí mật với Authorization Code, nên không phát hiện việc client công khai có thể đổi mã khi thiếu PKCE; hãy xây dựng tình huống bổ sung ma trận kiểu client.
Một API backend sử dụng token từ môi trường staging nhưng resource server trong production vẫn chấp nhận vì cấu hình tin cậy quá rộng; hãy đặt bài toán kiểm tra ranh giới issuer và audience.
Sau khi mở rộng sang nhiều khu vực địa lý, các cụm Authorization Server có cấu hình đồng hồ, khóa ký và dữ liệu consent lệch nhau; hãy xây dựng tình huống kiểm thử hành trình đăng nhập xuyên khu vực.
Trong một đợt diễn tập sự cố, nhóm vận hành cần thu hồi khẩn cấp quyền truy cập của một client bị lộ secret khi hàng nghìn refresh token còn hiệu lực; hãy đặt bài toán đánh giá khả năng ứng phó.
Một tổ chức muốn chứng minh không có client không hợp lệ nào có thể nhận access token, nhưng test hiện chỉ kiểm tra một kiểu xác thực client; hãy xây dựng tình huống lập ma trận kiểm chứng grant và xác thực.
Một đợt triển khai bật OIDC cho ứng dụng cũ nhưng màn hình consent, UserInfo và logout không đồng bộ về phạm vi danh tính người dùng; hãy đặt tình huống xác định tiêu chí chấp nhận trước phát hành.
Đội vận hành theo dõi tỉ lệ lỗi token endpoint tăng cao nhưng dashboard không phân biệt lỗi cấu hình client, PKCE, consent và hạ tầng lưu trữ; hãy xây dựng tình huống thiết kế quan sát đủ để điều tra.
Một doanh nghiệp muốn di trú từ máy chủ cấp quyền tự xây sang Spring Authorization Server mà không làm gián đoạn các client hiện tại; hãy đặt tình huống kiểm chứng khả năng tương thích cấu hình, token và vòng đời phiên.
