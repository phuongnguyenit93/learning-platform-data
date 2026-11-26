Một dịch vụ đặt vé dùng mã chuyến bay chứa dấu cộng và dấu gạch chéo để tạo URI bằng cách nối chuỗi; HTTP client gọi nhầm đường dẫn khi mã thực tế có các ký tự đặc biệt.
Ứng dụng Java ghép base URL của đối tác với đường dẫn đặt hàng, nhưng cấu hình môi trường có hoặc thiếu dấu gạch chéo cuối làm request chuyển sang endpoint khác nhau.
Trang quản lý kho truyền nhiều giá trị category trong query string; các bản HTTP client mới và cũ mã hóa danh sách theo hai cách khiến kết quả lọc không nhất quán.
Client tra cứu hóa đơn gửi mã khách hàng bắt đầu bằng các số 0 qua tham số truy vấn; bộ chuyển đổi tham số tại một phiên bản ứng dụng làm mất phần số 0 và trả dữ liệu sai khách.
Ứng dụng đặt lịch gửi tên khách có dấu tiếng Việt trong URI; khi chạy sau reverse proxy, một số ký tự Unicode bị biến đổi và dịch vụ đích không tìm thấy bản ghi.
Dịch vụ giao nhận nhận địa chỉ email làm một phần của path; email có ký tự @ hoặc dấu phần trăm khiến URL được ghi vào log khác URL gửi thực tế.
Một HTTP client gửi query parameter filters rỗng trong khi API đối tác phân biệt rõ không truyền filters với truyền filters không có giá trị; các báo cáo của hai chi nhánh có kết quả khác nhau.
Ứng dụng phân trang nhận đường dẫn nextPage là URL tuyệt đối từ hệ thống đối tác; sau đợt thay đổi cấu hình, client chuyển request sang hostname nội bộ không thể truy cập.
Client tra cứu giao dịch đi qua gateway có tiền tố /partner/api; lần cấu hình base URI mới làm mất tiền tố này và mọi request chỉ lỗi trên môi trường production.
API đối tác trả HTTP 301 khi đổi hostname; client tự động đi theo redirect nhưng header Authorization không được gửi ở request tới địa chỉ mới và toàn bộ truy vấn bị từ chối.
Một HTTP client tải tệp qua URL ký sẵn có chứa nhiều tham số chữ ký; lớp dựng URI mã hóa lại ký tự phần trăm khiến server xác nhận chữ ký không hợp lệ.
Ứng dụng truy vấn danh sách sản phẩm với dấu cách trong tham số search; một môi trường biến dấu cách thành dấu cộng và môi trường khác dùng phần trăm mã hóa, làm bộ máy tìm kiếm trả kết quả khác nhau.
Một SDK thanh toán tự tạo header Host trong khi URL trỏ tới gateway có tên miền riêng; reverse proxy định tuyến sai backend dù kết nối TCP và TLS được thiết lập thành công.
Dịch vụ kế toán chuyển header mã vùng từ X-Region sang một tên khác; HTTP client vẫn gửi header cũ và có lúc ghi chứng từ vào vùng mặc định.
Client gọi API nhận hàng đặt Content-Type là application/json dù body là tệp CSV; gateway chấp nhận kết nối nhưng provider trả HTTP 415 ở một số tuyến xử lý.
Ứng dụng báo giá gửi Accept chỉ nhận XML trong khi API đối tác mới chỉ hỗ trợ JSON; một số request trả HTTP 406 sau lần nâng cấp thư viện HTTP.
HTTP client gửi danh sách ngôn ngữ qua Accept-Language, nhưng một phiên bản SDK thay thứ tự ưu tiên; bản mô tả sản phẩm được trả bằng ngôn ngữ khác kỳ vọng của cửa hàng.
Dịch vụ tải báo cáo dùng header If-None-Match với ETag lưu từ lần trước; client không xử lý được phản hồi HTTP 304 và ghi file báo cáo rỗng vào kho lưu trữ.
Ứng dụng lấy biểu phí sử dụng gzip nhưng một proxy đã giải nén body mà vẫn giữ metadata Content-Encoding; HTTP client cố giải nén lần nữa và báo lỗi đọc response.
Một đối tác gửi response bằng truyền dữ liệu từng phần không có Content-Length; ứng dụng Java chỉ chấp nhận response có độ dài được khai báo và bỏ dở tải tập tin lớn.
Ứng dụng web gọi HTTP API qua client dùng chung nhưng bổ sung header tenant vào cấu hình mặc định; request của hai khách hàng liên tiếp nhận sai dữ liệu sau khi header trước đó bị giữ lại.
Client phục vụ báo cáo theo dõi chuyển tiếp X-Correlation-Id từ request đầu vào; một số đường gọi qua dịch vụ trung gian làm mất header nên không thể ghép log giữa các hệ thống.
Dịch vụ tích hợp gửi HTTP GET tới endpoint xem trạng thái nhưng bên cung cấp đôi lúc tạo nghiệp vụ khi nhận GET; proxy tự thử lại sau lỗi mạng và dẫn tới thao tác không mong đợi.
Ứng dụng tạo đơn qua HTTP POST nhận timeout ngay sau khi gửi body; khi nhân viên bấm lưu lại, hệ thống đối tác có hai đơn cho cùng một yêu cầu mua hàng.
Client cập nhật tồn kho bằng PUT trên cùng một tài nguyên; hai request phát sinh gần nhau bị mạng đảo thứ tự khiến trạng thái cuối cùng không phản ánh thao tác mới nhất.
Ứng dụng gửi PATCH để thay đổi địa chỉ giao hàng nhưng payload đôi khi chứa trường city là null; provider hiểu null là xóa thành phố trong khi màn hình khách hàng chỉ muốn giữ nguyên.
Client hủy đơn qua HTTP DELETE nhận HTTP 404 khi yêu cầu được lặp sau timeout; hệ thống ghi nhận thất bại dù đơn đã bị xóa trong lần gọi trước.
Ứng dụng kiểm tra trạng thái dịch vụ bằng HTTP HEAD, nhưng thư viện client vẫn cố phân tích body JSON và báo lỗi dù response không có body theo thiết kế.
Dịch vụ gửi tệp đính kèm qua multipart/form-data dùng nhiều phần gồm metadata và tệp; sau khi cập nhật SDK, tên phần chứa file không khớp hợp đồng và provider bỏ qua nội dung.
HTTP client xuất báo cáo gửi body JSON rất lớn trong một request; đường truyền chậm làm tăng mức sử dụng RAM vì toàn bộ body được lưu trong bộ nhớ trước khi gửi.
Ứng dụng quản lý đơn nhận HTTP 201 kèm Location cho đơn mới nhưng chỉ đọc body; khi provider chuyển sang trả body rỗng, client không biết mã đơn vừa tạo.
Client tra cứu thông tin qua API trả HTTP 204 cho hồ sơ chưa có dữ liệu bổ sung; bộ giải mã JSON vẫn cố đọc body và phát sinh lỗi khi xử lý response hợp lệ.
Dịch vụ thanh toán trả HTTP 200 với JSON chứa trạng thái nghiệp vụ FAILED; hệ thống gọi chỉ kiểm tra mã HTTP nên thông báo cho người dùng rằng giao dịch đã hoàn tất.
Ứng dụng theo dõi phản hồi của đối tác nhận HTTP 207 cho kết quả từng mục trong một lô; client coi mọi mã 2xx là thành công toàn bộ và không nhận ra một số mục thất bại.
Client tra cứu sản phẩm phân biệt lỗi HTTP 404 và 410 để quyết định giao diện hiển thị; sau khi chuyển sang cơ chế xử lý lỗi chung, cả hai bị gom thành cùng một ngoại lệ.
Ứng dụng trả lại lỗi xác thực cho người dùng khi upstream trả HTTP 502; hệ thống monitoring ghi nhận sai nhóm sự cố vì client không tách lỗi gateway với lỗi nghiệp vụ.
HTTP client gặp response JSON không đúng schema khi upstream deploy dở phiên bản; một trường số đột ngột trở thành chuỗi và việc deserialize làm hỏng cả lô dữ liệu.
Dịch vụ vận chuyển bổ sung enum trạng thái mới vào response; client Java dùng enum đóng từ phiên bản SDK cũ và ném exception khi gặp trạng thái mới.
API tra cứu giao dịch chuyển trường số tiền từ integer sang decimal; client Java dùng kiểu số nguyên và làm tròn sai khi nhận giao dịch có phần thập phân.
Đối tác trả các mã lỗi theo chuẩn problem details JSON nhưng một client chỉ tìm trường message cũ; màn hình hỗ trợ không hiển thị được nguyên nhân xác thực hoặc validation.
Client gọi API quản lý khách hàng gắn Basic Authentication vào mọi request; sau khi luồng chuyển sang HTTPS qua một proxy doanh nghiệp, một số request đến provider không mang thông tin xác thực.
Ứng dụng dùng Bearer token có thời hạn ngắn để gọi API ngân hàng; những request ở cuối thời hạn token thỉnh thoảng nhận HTTP 401 do chênh lệch đồng hồ giữa các hệ thống.
Nhiều luồng trong ứng dụng cùng thấy access token hết hạn và đồng thời gọi endpoint refresh; nhà cung cấp giới hạn số lần refresh khiến một số request nghiệp vụ bị từ chối.
Client OAuth2 lấy token cho scope chỉ đọc nhưng sau một bản cập nhật bắt đầu gọi endpoint tạo giao dịch; token còn hiệu lực nhưng mọi request mới trả HTTP 403.
Ứng dụng tích hợp nhiều tenant lưu token truy cập trong bộ nhớ dùng chung; dưới tải đồng thời, request tới hệ thống vận chuyển đôi lúc mang token của tenant khác.
Client ký request tới API tài chính dựa trên URI và body, nhưng lớp HTTP tự sắp xếp lại thứ tự query parameter; nhà cung cấp từ chối chữ ký chỉ ở các yêu cầu có nhiều tham số.
Đội bảo mật xoay vòng chứng chỉ client mTLS trong giờ cao điểm; một số instance Java dùng chứng chỉ mới còn connection tồn tại lâu vẫn mang thông tin phiên trước khi luân chuyển.
Khi nâng chứng chỉ TLS máy chủ đối tác, ứng dụng chạy JDK cũ không tin cậy chuỗi chứng chỉ mới; client ngừng gọi API trong khi thử bằng trình duyệt trên máy phát triển vẫn thành công.
Ứng dụng kiểm tra chứng chỉ TLS bằng hostname của endpoint cũ; sau khi chuyển qua load balancer với domain mới, quá trình bắt tay TLS thất bại dù DNS đã phân giải đúng.
HTTP client hoạt động khi gọi trực tiếp nhưng bị từ chối trong môi trường doanh nghiệp có proxy yêu cầu xác thực; request nhận HTTP 407 trước khi đến ứng dụng đích.
Dịch vụ gọi API có hai loại proxy tùy môi trường, nhưng cấu hình proxy trong JDK HttpClient khác cấu hình JVM toàn cục; production đi tuyến mạng khác staging và gặp lỗi kết nối.
Trong một đợt thay đổi DNS của nhà cung cấp, ứng dụng Java tiếp tục gọi địa chỉ IP cũ lâu hơn dự kiến; một số pod báo lỗi kết nối còn các pod khởi động mới hoạt động bình thường.
HTTP client dùng connect timeout vài giây nhưng không giới hạn thời gian đọc response; một API đối tác chấp nhận kết nối rồi không gửi dữ liệu khiến hàng trăm request bị giữ vô hạn.
Ứng dụng tải dữ liệu từ đối tác đặt read timeout quá ngắn so với thời gian tính báo cáo; phần lớn request thành công khi thử trực tiếp nhưng bị ngắt dưới tải thực tế.
Client thiết lập timeout riêng cho từng lần gọi nhưng luồng nghiệp vụ có ba dịch vụ phụ thuộc; tổng thời gian thực thi vượt SLA HTTP đầu vào dù mỗi cuộc gọi riêng đều nằm dưới timeout.
API cung cấp response theo streaming và đôi lúc ngừng gửi thêm chunk trong nhiều phút; HTTP client giữ kết nối mở vì request đã nhận được byte đầu tiên trước timeout.
Trong đợt mạng nghẽn, client hết thời gian chờ trước khi upstream trả kết quả; backend upstream vẫn xử lý xong và tạo hóa đơn dù caller đã báo thất bại.
Một ứng dụng sử dụng JDK HttpClient.send đồng bộ trong các thread xử lý HTTP đầu vào; khi đối tác chậm, thread pool của ứng dụng cạn khiến cả các endpoint nội bộ không phụ thuộc đối tác cũng bị chậm.
Ứng dụng Java dùng HttpClient.sendAsync để gọi hàng nghìn API nhưng không giới hạn số request cùng lúc; khi đối tác giảm năng lực phục vụ, số tác vụ chờ và lượng bộ nhớ ứng dụng tăng mạnh.
Client JDK HttpClient gửi request có body lấy từ luồng một lần; sau lỗi kết nối, lần thử gửi lại không còn dữ liệu body đầy đủ dù request trước có payload hợp lệ.
Một ứng dụng chuyển từ JDK HttpClient HTTP/1.1 sang HTTP/2; khi đi qua proxy cũ, một số luồng được reset và chỉ các request đồng thời cao mới phát sinh lỗi.
Hệ thống dùng HTTP/2 multiplex nhiều request trên một kết nối; khi kết nối bị đóng bất thường, nhiều tác vụ đang chạy đồng thời thất bại và cùng kích hoạt cơ chế thử lại.
Ứng dụng đặt hàng sử dụng Spring RestClient, nhưng cấu hình xử lý HTTP 4xx như lỗi hệ thống làm các trường hợp validation được retry liên tục và ảnh hưởng tốc độ xử lý đơn.
Nhóm chuyển từ RestTemplate sang Spring RestClient; một endpoint trả body lỗi theo định dạng riêng không còn được ánh xạ thành ngoại lệ nghiệp vụ mà giao diện đang xử lý.
RestClient gọi API trả HTTP 204 nhưng cấu hình giải mã bắt buộc có đối tượng phản hồi; tác vụ đồng bộ trạng thái bị đánh dấu lỗi dù provider xử lý yêu cầu thành công.
Ứng dụng Spring WebClient gọi nhiều service từ luồng reactive, nhưng một đoạn xử lý sử dụng block để lấy dữ liệu; dưới tải cao xuất hiện lỗi luồng event loop và độ trễ tăng bất thường.
WebClient lấy body response thành một đối tượng lớn bằng bodyToMono; provider trả danh sách hàng trăm nghìn dòng khiến ứng dụng vượt giới hạn bộ đệm dữ liệu.
Ứng dụng dùng WebClient.retrieve nhưng chỉ cấu hình nhánh thành công; khi provider trả JSON lỗi chi tiết với HTTP 409, dữ liệu lỗi nghiệp vụ cần cho người dùng bị mất.
WebClient tải luồng sự kiện từ đối tác nhưng người dùng đóng màn hình giữa chừng; kết nối upstream vẫn tiếp tục đọc dữ liệu và tiêu tốn tài nguyên sau khi subscriber đã ngừng.
Đội phát triển triển khai retryWhen cho WebClient sau mọi lỗi; khi upstream trả HTTP 400 do dữ liệu không hợp lệ, nhiều lần request giống hệt nhau làm tăng tải mà không thay đổi kết quả.
Một luồng Reactor dùng WebClient gọi ba nguồn dữ liệu song song; một request bị timeout làm toàn bộ phản hồi tổng hợp thất bại mặc dù hai nguồn còn lại đã trả dữ liệu hợp lệ.
WebClient dùng chung connection pool cho API thanh toán và API báo cáo; khi hàng nghìn báo cáo tải đồng thời, các yêu cầu thanh toán chờ lấy connection và vượt SLA.
Ứng dụng RestClient mở connection mới cho mỗi request thay vì sử dụng pool ổn định; trong giờ cao điểm, số kết nối TCP và thời gian bắt tay TLS tăng làm độ trễ tăng mạnh.
Connection pool của HTTP client giữ nhiều kết nối nhàn rỗi; load balancer đối tác đóng các kết nối này trong đêm khiến request đầu tiên buổi sáng thường bị connection reset.
Ứng dụng nhận response có body lớn nhưng bỏ qua việc đóng hoặc tiêu thụ response stream; sau một thời gian hoạt động, HTTP client không còn connection khả dụng trong pool.
Dịch vụ xử lý hàng nghìn request tới cùng upstream có giới hạn số kết nối đồng thời; hàng đợi đợi connection trong client tăng dù CPU server thấp và số request chưa hoàn tất ngày càng lớn.
Client HTTP giữ kết nối Keep-Alive qua một cổng NAT dùng chung; khi phiên NAT hết hạn trước kết nối phía client, request tiếp theo thỉnh thoảng bị reset sau lúc bắt đầu gửi.
Ứng dụng gọi hai API ở hai miền khác nhau với connection pool và giới hạn giống nhau; một API có phản hồi cực chậm chiếm phần lớn connection làm API còn lại bị trì hoãn.
Trong thời gian đối tác trả HTTP 503, một nhóm instance cùng retry ngay lập tức và đồng bộ theo nhịp; lưu lượng dồn thành đỉnh cao liên tiếp sau mỗi lần upstream hồi phục.
Nhà cung cấp trả HTTP 429 kèm Retry-After bằng thời điểm tuyệt đối, nhưng đồng hồ của các node client lệch nhau; các node thử lại không cùng thời điểm chờ và một số tiếp tục bị giới hạn.
Client thanh toán retry POST khi gặp socket timeout mà không biết upstream đã ghi nhận tiền; những giao dịch của khách kết thúc với hai lần thu tiền.
HTTP client thử lại trên HTTP 500, nhưng phản hồi thực tế xuất hiện sau khi upstream đã gửi email xác nhận; khách hàng nhận nhiều email trong cùng một thao tác.
Client nhận HTTP 408 từ một proxy giữa đường; hệ thống retry không phân biệt request đã gửi hết body hay chưa và đôi lúc phát sinh tác động lặp ở hệ thống đối tác.
Một ứng dụng gọi API tồn kho chấp nhận retry GET nhiều lần, nhưng tổng thời gian retry vượt thời hạn của đơn đặt hàng; kết quả đến muộn được ghi vào giao dịch đã hủy.
Khi đối tác bắt đầu trả HTTP 429 do quota, ứng dụng bỏ qua header gợi ý thời gian chờ và liên tục thử lại; phần lớn worker bị chiếm bởi những request chưa thể thành công.
Đội cấu hình retry trong cả lớp SDK và API gateway; một lần lỗi từ provider tạo nhiều lần gọi nhân lên khiến giới hạn lưu lượng của đối tác bị vượt rất nhanh.
Ứng dụng dùng circuit breaker cho API kiểm tra tín dụng nhưng trạng thái mở vẫn được xử lý như lỗi mạng thông thường; hệ thống ngoài liên tục nhận request khi năng lực phục vụ chưa ổn định.
Trong đợt mất mạng giữa hai trung tâm dữ liệu, HTTP client gửi một phần request body rồi gặp connection reset; log chỉ ghi lỗi đọc response và không biết phía provider đã nhận được bao nhiêu dữ liệu.
Một API phản hồi JSON theo chunked transfer nhưng mất kết nối sau khi gửi nửa tài liệu; client nhận HTTP 200 rồi thất bại khi parse nội dung mà hệ thống giám sát chỉ ghi nhận thành công.
Client bị phân giải DNS lỗi vài phút dù dịch vụ đích vẫn hoạt động; hệ thống retry trên địa chỉ cũ khiến backlog đồng bộ tích tụ sau khi DNS được khôi phục.
Ứng dụng đẩy log toàn bộ header và body của HTTP client để tìm lỗi tích hợp; dữ liệu có access token và thông tin cá nhân bắt đầu xuất hiện trong hệ thống log tập trung.
Đội vận hành chỉ đo thời gian xử lý server nên không thấy thời gian client chờ lấy connection, DNS, TLS và nhận body; các request chậm không có dấu hiệu tương ứng trong dashboard.
Một tác vụ xuất hóa đơn gọi chuỗi HTTP API qua nhiều dịch vụ nhưng client không chuyển traceparent; khi phát sinh timeout, đội trực không thể liên hệ request đầu vào với cuộc gọi downstream lỗi.
Ứng dụng gắn nhãn URL đầy đủ chứa ID giao dịch vào metric thời gian gọi HTTP; khi lưu lượng tăng, số lượng chuỗi thời gian giám sát vượt giới hạn của hệ thống metrics.
Client ghi nhận mọi exception thành lỗi HTTP 500 dù nhiều request thực tế gặp DNS failure hoặc TLS handshake failure trước khi có response; nhóm hỗ trợ không xác định được tầng gây sự cố.
Bộ kiểm thử HTTP client chỉ dùng mock server trả HTTP 200 ngay lập tức; sau khi triển khai, request có kết nối được thiết lập chậm và body gửi từng chunk làm chương trình bị treo.
Đội kiểm thử retry bằng cách trả HTTP 503 giả nhưng không kiểm chứng số request thực sự phát ra; sản phẩm vô tình gửi lại các POST không an toàn trong trường hợp timeout.
Một mock HTTP server trong test trả response có Content-Length dài hơn body thực tế; HTTP client của ứng dụng đợi đến hết timeout thay vì xử lý một response hoàn chỉnh.
Ứng dụng cần xử lý chứng chỉ TLS hết hạn và server gửi chuỗi chứng chỉ sai; môi trường test chỉ dùng endpoint HTTP thường nên những tình huống này không được phát hiện trước production.
Trong bài kiểm thử mạng, proxy cố ý cắt kết nối ngay sau khi client gửi hết body request; ứng dụng có kết quả khác nhau giữa JDK HttpClient và Spring WebClient khi xác định giao dịch thành công hay thất bại.
Đội test sử dụng server giả luôn trả dữ liệu nhanh, nhưng production đôi khi gửi response hợp lệ từng byte một; tiến trình đồng bộ kéo dài quá thời gian được cấp dù từng khoảng chờ nhỏ không vượt timeout.
