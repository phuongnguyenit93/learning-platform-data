Một sàn thương mại điện tử phát webhook OrderCreated với trường orderId là chuỗi, nhưng bản phát hành mới chuyển sang số nguyên khiến hệ thống kho mất các mã đơn có số 0 ở đầu.
Đối tác thanh toán bổ sung trạng thái PARTIALLY_REFUNDED vào webhook RefundUpdated, trong khi ứng dụng kế toán Spring chỉ nhận diện các trạng thái cũ và bỏ qua nhiều khoản hoàn tiền.
Dịch vụ giao hàng đổi tên trường deliveredAt thành completedAt trong payload webhook mà không tăng phiên bản sự kiện; màn hình lịch sử vận đơn không còn hiển thị thời điểm giao hàng.
Webhook CustomerUpdated đôi lúc bỏ trường email khi khách chưa xác minh, nhưng bên nhận vẫn giả định email luôn tồn tại và từ chối toàn bộ sự kiện cập nhật khách hàng.
Một nền tảng bảo hiểm phát webhook PolicyChanged chứa cả object trước và sau thay đổi; với hợp đồng mới chưa từng có trạng thái trước đó, consumer không xử lý được giá trị null.
Hệ thống CRM phát webhook CustomerDeleted chỉ chứa customerId, trong khi consumer vẫn đòi đủ họ tên và số điện thoại như các sự kiện tạo mới nên không xóa được bản sao dữ liệu.
Đội thương mại điện tử thêm trường giá trị đơn hàng với đơn vị tiền tệ không được mô tả rõ; hai hệ thống nhận webhook OrderPaid ghi nhận số tiền khác nhau cho cùng một giao dịch.
Webhook ShippingStatusChanged ghi timestamp theo giờ địa phương nhưng không có offset múi giờ; dashboard của đối tác sắp xếp sai thời điểm giao hàng giữa hai quốc gia.
Ứng dụng nhận webhook từ nhiều đối tác dùng chung đường dẫn, nhưng các bên sử dụng trường eventType và type với ý nghĩa khác nhau, làm sự kiện hủy bị phân loại thành cập nhật thường.
Nhà cung cấp chuyển payload webhook từ JSON object đơn sang JSON array cho lô nhiều đơn; Spring controller cũ vẫn giải mã một đối tượng và trả lỗi cho toàn bộ lô.
Payload webhook InvoiceIssued chứa trường amount biểu diễn giá trị trước thuế ở một đối tác và sau thuế ở đối tác khác; bộ phận đối soát phát hiện sai số sau khi gộp dữ liệu.
Nhà phát hành webhook thêm trường chứa object lồng nhau có kích thước rất lớn; ứng dụng nhận nạp toàn bộ body vào bộ nhớ trước khi validate và tăng RAM đột biến.
Dịch vụ thanh toán gửi cùng eventId trong cả header và body nhưng đôi lúc hai giá trị không khớp sau lần đổi gateway; consumer không biết bản ghi nào là định danh chính thức.
Webhook định nghĩa phiên bản payload qua header nhưng một số request không mang header sau khi đi qua proxy; hệ thống nhận giải mã theo schema mới và từ chối thông điệp hợp lệ theo phiên bản cũ.
Nhà cung cấp cập nhật mẫu payload trên trang tài liệu nhưng webhook production vẫn phát cấu trúc cũ trong nhiều ngày; nhóm tích hợp kiểm thử theo mẫu mới và gặp lỗi liên tục khi triển khai.
Một cửa hàng đăng ký sự kiện payment.succeeded trên trang cấu hình đối tác nhưng endpoint chỉ nhận payment.completed; hoạt động thu tiền diễn ra bình thường mà webhook không đến.
Nền tảng đăng ký webhook theo từng chi nhánh nhưng một tài khoản mới không được gắn đúng branchId; webhook được gửi tới cả đơn hàng của chi nhánh khác.
Đội vận hành thay URL webhook sau khi đổi tên miền nhưng tài khoản cũ vẫn đăng ký endpoint cũ; đơn hàng phát sinh từ nhóm khách hàng này không cập nhật hệ thống nội bộ.
Đối tác hỗ trợ cơ chế đăng ký webhook qua API, nhưng trong lần khởi động lại ứng dụng tạo thêm một subscription giống hệt; một sự kiện được gửi nhiều lần tới cùng endpoint.
Hệ thống cho phép người dùng tự đăng ký webhook URL tùy ý; một khách hàng cấu hình địa chỉ nội bộ khiến dịch vụ phát sự kiện cố kết nối đến tài nguyên riêng trong mạng của doanh nghiệp.
Nhà cung cấp yêu cầu xác minh quyền sở hữu endpoint bằng một challenge request trước khi kích hoạt; ứng dụng Spring chỉ triển khai POST sự kiện nên quá trình đăng ký luôn bị từ chối.
Đối tác gửi request kiểm tra endpoint định kỳ sau khi đăng ký; gateway chặn request này vì thiếu header nghiệp vụ và subscription tự chuyển sang trạng thái không hoạt động.
Một tenant hủy đăng ký sự kiện giao hàng nhưng hệ thống phát vẫn còn các delivery đang chờ; webhook tiếp tục đến sau thời điểm hủy và phía nhận không biết xử lý ra sao.
Nhân viên thay đổi danh sách sự kiện quan tâm nhưng bộ lọc ở phía phát chưa đồng bộ; webhook CustomerCreated vẫn đến trong khi webhook CustomerDisabled cần thiết lại không xuất hiện.
Nhà cung cấp tạm ngừng endpoint sau nhiều lần trả lỗi 5xx nhưng không gửi thông báo trong ứng dụng quản trị; queue nhận sự kiện của doanh nghiệp giảm lưu lượng bất ngờ và dữ liệu bị thiếu.
Cùng một webhook endpoint được dùng cho môi trường staging và production, trong khi mỗi môi trường sử dụng bộ khóa và payload khác nhau; các thử nghiệm vô tình cập nhật đơn hàng thật.
Đối tác xoay vòng URL nhận webhook từ /callbacks/v1 sang /callbacks/v2 nhưng DNS và gateway còn định tuyến song song; một số sự kiện đến cả hai phiên bản ứng dụng trong giai đoạn chuyển đổi.
Ứng dụng nhận webhook dùng Spring MVC xử lý thanh toán và ghi database ngay trong request HTTP; vào đợt cao điểm, thời gian phản hồi vượt hạn chờ của bên phát dù giao dịch vẫn hoàn tất.
Nhà cung cấp webhook chấp nhận bất kỳ mã 2xx là đã giao thành công, nhưng ứng dụng Spring trả HTTP 202 ngay khi nhận và một tác vụ nền có thể thất bại sau đó khiến không còn lần gửi lại.
Receiver trả HTTP 200 trước khi nội dung webhook được ghi bền vào hệ thống; khi pod khởi động lại ngay sau phản hồi, một loạt sự kiện không còn ở bất kỳ queue nào.
Gateway giới hạn kích thước HTTP body dưới mức payload webhook hoàn tiền theo lô; nhiều sự kiện hợp lệ bị trả HTTP 413 trước khi request tới Spring controller.
Đối tác gửi webhook với Content-Type có tham số charset, trong khi bộ lọc tiếp nhận chỉ chấp nhận chuỗi Content-Type khớp tuyệt đối; một phần request bị từ chối dù chứa JSON hợp lệ.
Spring controller khai báo chỉ nhận application/json, nhưng một nhà cung cấp gửi webhook JSON với Content-Type text/plain; hệ thống ghi nhận HTTP 415 và đối tác bắt đầu retry liên tục.
Endpoint tiếp nhận webhook cần đọc header tùy chỉnh chứa mã sự kiện nhưng reverse proxy vô tình loại bỏ header này; request đến controller với đầy đủ body mà không thể định tuyến xử lý.
Ứng dụng Spring trả HTTP 204 khi tiếp nhận webhook thành công, nhưng nhà cung cấp chỉ chấp nhận đúng HTTP 200 và thử gửi lại liên tục các sự kiện đã xử lý.
Hệ thống theo dõi webhook chỉ kiểm tra HTTP status, trong khi receiver luôn trả HTTP 200 kèm body báo lỗi nghiệp vụ; nhà cung cấp dừng retry và dữ liệu giữa hai hệ thống sai lệch.
Nhà cung cấp gửi webhook theo từng batch có sự kiện hợp lệ và không hợp lệ; receiver trả một mã HTTP chung cho cả batch và không thể hiện sự kiện nào đã được lưu.
Ứng dụng Spring đọc JSON thành DTO rồi trả HTTP 400 khi gặp giá trị enum mới; nhà cung cấp xem đây là lỗi cuối cùng và ngừng chuyển tiếp những cập nhật trạng thái tiếp theo.
Một máy chủ webhook receiver bị cạn thread xử lý vì truy vấn database chậm; phía phát bắt đầu nhận timeout dù load balancer vẫn báo tất cả pod đang khỏe mạnh.
Hệ thống tích hợp có URL webhook luôn chuyển hướng HTTP 307 sang endpoint mới; thư viện gửi của đối tác không đi theo redirect đối với POST và các sự kiện bị giữ tại nơi phát.
Đội bảo mật bổ sung bước kiểm tra CAPTCHA cho mọi POST công khai trên gateway; các request webhook không có trình duyệt bị từ chối trước khi Spring controller tiếp nhận.
Nhà cung cấp ký HMAC trên byte gốc của JSON body, nhưng ứng dụng Spring deserialize rồi serialize lại để xác minh; cùng dữ liệu nghiệp vụ với thứ tự key khác làm chữ ký sai.
API gateway tự động thay đổi định dạng xuống dòng của payload trước khi chuyển cho Spring receiver; chữ ký HMAC hợp lệ tại bên phát nhưng không còn hợp lệ trên body mà ứng dụng nhận.
Hệ thống tính HMAC dựa trên UTF-8 nhưng một dịch vụ tích hợp cũ giải mã body theo encoding khác khi chứa tên tiếng Việt; webhook chỉ bị từ chối với khách hàng có dấu.
Đối tác gửi chữ ký ở header X-Webhook-Signature theo định dạng có tiền tố thuật toán; ứng dụng nhận cắt nhầm phần tiền tố và luôn báo lỗi xác minh dù bí mật đúng.
Nhà cung cấp đổi cách mã hóa HMAC từ chuỗi hex sang Base64 nhưng chưa cập nhật tất cả endpoint; một số phiên bản receiver xem các chữ ký mới là dữ liệu không hợp lệ.
Ứng dụng hỗ trợ nhiều đơn vị bán hàng nhưng lưu một HMAC secret dùng chung; webhook từ đối tác A đôi lúc được xác minh bằng secret của đối tác B và bị từ chối.
Trong đợt luân chuyển secret HMAC, bên phát có lúc ký bằng khóa mới khi một số instance Spring vẫn chỉ biết khóa cũ; tỷ lệ webhook thất bại tăng theo từng pod.
Nhà cung cấp gửi đồng thời timestamp và HMAC trong header, nhưng đồng hồ của cluster receiver lệch vài phút; các webhook mới bị đánh dấu hết hiệu lực một cách không nhất quán.
Receiver chỉ kiểm tra chữ ký HMAC hợp lệ mà không ghi nhận định danh đã nhận; một request webhook hợp lệ bị phát lại nhiều giờ sau vẫn tạo thêm giao dịch nghiệp vụ.
Một nhóm phát triển vô tình log toàn bộ header và payload webhook chứa HMAC secret dạng cấu hình và thông tin cá nhân; dữ liệu nhạy cảm bắt đầu xuất hiện trong hệ thống log tập trung.
Endpoint webhook công khai chấp nhận request có header chữ ký nhưng thiếu trường bắt buộc trong chuỗi dữ liệu được ký; một bên gửi mới có khả năng làm thay đổi trường này mà không khiến xác minh thất bại.
Ứng dụng xác minh HMAC dựa trên đường dẫn và timestamp theo tài liệu cũ, còn nhà cung cấp chỉ ký raw body theo phiên bản mới; webhook được chuyển tới endpoint chính xác nhưng luôn trả 401.
Đội tích hợp cấu hình HMAC verification trong một Spring filter nhưng các endpoint lỗi trả HTTP 500 trước khi filter ghi nhận mã nguyên nhân; nhóm trực không phân biệt được khóa sai với body bị biến đổi.
Nhà cung cấp webhook dùng mTLS để xác thực máy nhận sau khi tăng yêu cầu bảo mật, nhưng certificate chain trên load balancer chưa được làm mới và đợt phát sự kiện tiếp theo thất bại khi bắt tay TLS.
Webhook receiver yêu cầu IP nguồn nằm trong danh sách cho phép, nhưng nhà cung cấp chuyển sang dải IP mới mà không thông báo kịp; đơn hàng mới vẫn tạo nhưng không tới được hệ thống hậu cần.
Một đối tác bật kiểm tra chứng chỉ TLS của webhook endpoint và phát hiện chứng chỉ đã hết hạn trong đêm; các thông điệp chưa giao tiếp tục tích tụ trong hệ thống bên phát.
Nhà cung cấp phát lại webhook trên các địa chỉ IP phân phối khác nhau; cơ chế giới hạn theo IP của gateway chặn bất ngờ nhiều lần gửi hợp lệ trong giờ cao điểm.
Một receiver lưu HMAC secret chung cho sandbox và production; khi đối tác chuyển cấu hình môi trường, các webhook kiểm thử có thể đi vào luồng xử lý dữ liệu thật.
Nhà cung cấp đặt lịch retry khi webhook trả HTTP 503, nhưng receiver vừa khôi phục cơ sở dữ liệu bị một làn sóng request dồn đến đồng thời và quá tải lần thứ hai.
Đối tác retry webhook theo khoảng cách tăng dần, nhưng endpoint chỉ lưu được sự kiện sau thời gian giữ retry của nhà cung cấp; các cập nhật trong đợt bảo trì dài bị mất hẳn.
Trong một sự cố mạng ngắn, receiver đã ghi nhận thanh toán nhưng response HTTP 200 bị mất trên đường về; bên phát retry cùng webhook và hệ thống tạo thêm khoản ghi nhận tiền.
Nhà cung cấp gửi lại webhook sau HTTP 429 nhưng không tôn trọng Retry-After từ receiver; lưu lượng sự kiện vẫn vượt ngưỡng giới hạn tiếp nhận của ứng dụng Spring.
Ứng dụng webhook xử lý lỗi kiểm tra dữ liệu bằng HTTP 500 thay vì lỗi cố định; nhà cung cấp tiếp tục retry một payload không hợp lệ và giữ queue giao hàng tăng không ngừng.
Đối tác xem HTTP 401 do sai secret HMAC là lỗi không thể retry; sau lần xoay secret thất bại kéo dài, các sự kiện thuộc khoảng thời gian này không còn trong lịch sử gửi lại.
Nhóm vận hành yêu cầu gửi lại hàng nghìn webhook từ dashboard của nhà cung cấp sau khi sửa lỗi; các webhook này trùng với một phần request đã từng được xử lý thành công.
Webhook về đơn đặt hàng có eventId duy nhất nhưng provider thực hiện redelivery với deliveryId mới; receiver dùng deliveryId để chống trùng và tạo hai bản ghi cho một sự kiện.
Hệ thống CRM ghi dấu webhook đã xử lý ngay sau khi nhận HTTP request rồi mới cập nhật database; một lỗi ghi dữ liệu khiến các lần retry hợp lệ bị từ chối như sự kiện trùng.
Ứng dụng Spring ghi cập nhật nghiệp vụ vào database rồi mới ghi marker đã xử lý webhook; khi pod chết giữa hai thao tác, lần gửi lại thực hiện cập nhật nghiệp vụ một lần nữa.
Webhook PaymentRefunded có hai delivery được phát từ hai khu vực của provider và đến đồng thời; hai instance receiver cùng không tìm thấy eventId đã xử lý và cùng tạo bản ghi hoàn tiền.
Một trường hợp nghiệp vụ hủy rồi khôi phục đơn tạo hai webhook khác nhau có cùng orderId; receiver chống trùng chỉ bằng orderId và làm mất sự kiện khôi phục hợp lệ.
Receiver chỉ lưu dấu sự kiện đã xử lý trong bộ nhớ của một pod; sau khi autoscaling thay pod, các webhook retry cũ được thực thi lần hai dù hệ thống đã xử lý trước đó.
Nhà cung cấp sử dụng cùng một eventId cho nhiều tenant do mã sự kiện chỉ duy nhất trong từng tài khoản; hệ thống nhận dùng khóa toàn cục và bỏ qua sự kiện hợp lệ của tenant thứ hai.
Đội phát hành thêm trường version cho webhook và đồng thời thay cơ chế tạo eventId; dữ liệu cũ trong bộ nhớ chống trùng khiến sự kiện từ định dạng mới bị loại sai.
Webhook cập nhật trạng thái giao hàng đến theo thứ tự DELIVERED rồi IN_TRANSIT sau một đợt retry; màn hình theo dõi vận đơn bị quay lại trạng thái đang vận chuyển.
Hệ thống xuất hóa đơn gửi webhook InvoicePaid trước khi InvoiceCreated vì hai tác vụ xuất phát từ các queue khác nhau; receiver không tìm thấy bản ghi hóa đơn để cập nhật.
Trong lúc một webhook CustomerUpdated đang chờ retry, một webhook cập nhật mới hơn đã được xử lý; lần gửi lại cũ ghi đè thông tin liên hệ vừa cập nhật của khách.
Nhà cung cấp phát riêng webhook OrderCancelled và OrderRefunded, nhưng thời gian gửi không bảo đảm thứ tự; hệ thống receiver từ chối hoàn tiền khi trạng thái hủy chưa được cập nhật.
Một hệ thống bên nhận sắp xếp sự kiện theo timestamp do nhiều server phát sinh; đồng hồ các server bị lệch khiến những sự kiện thực tế mới hơn được xem như cũ.
Receiver dùng số sequence có thể khởi động lại từ 1 sau khi đối tác chuyển môi trường; các webhook mới bị bỏ qua vì số sequence thấp hơn bản ghi cuối ở hệ thống đích.
Đội phát triển giả định mỗi webhook là toàn bộ trạng thái đối tượng, nhưng provider chỉ gửi thay đổi cục bộ; khi các sự kiện đến sai thứ tự, thông tin trong ứng dụng thiếu nhiều trường.
Webhook MembershipExpired đến trước webhook MembershipExtended do mạng chập chờn; tài khoản khách đã gia hạn vẫn bị khóa truy cập trong vài giờ.
Hệ thống webhook nhận vào nhanh hơn tốc độ ghi database trong chiến dịch flash sale; hàng đợi sự kiện chưa xử lý dài dần, còn phía phát vẫn nhận HTTP 200 cho mọi request.
Receiver ghi webhook vào queue rồi worker xử lý sau; khi queue đạt giới hạn dung lượng, API tiếp nhận vẫn trả HTTP 202 khiến nhà cung cấp đánh dấu đã giao thành công.
Spring webhook endpoint gọi trực tiếp ba dịch vụ nội bộ trong luồng request; khi một dịch vụ chậm, lượng kết nối HTTP vào và số thread chờ tăng vọt.
Ứng dụng xử lý webhook chạy nhiều consumer song song trên một queue chung; với cùng một đơn hàng, hai sự kiện cập nhật bị chạy đồng thời và trạng thái cuối khác nhau giữa các lần thử.
Đội vận hành tăng số worker xử lý webhook để giảm backlog, nhưng số connection tới database chạm ngưỡng và tỷ lệ lỗi xử lý sự kiện tăng dù HTTP endpoint vẫn khỏe.
Một tenant lớn gửi lượng webhook gấp hàng chục lần các tenant khác; queue dùng chung khiến các sự kiện thanh toán của cửa hàng nhỏ phải chờ nhiều phút.
Webhook EventCreated chứa tệp đính kèm nhúng Base64 rất lớn; bộ nhớ của API receiver và thời gian ghi queue tăng theo kích thước payload, gây ảnh hưởng cả event nhỏ.
Nhà cung cấp đẩy hàng chục nghìn webhook ngay sau một đợt bảo trì; autoscaling receiver chỉ dựa vào CPU nên không phản ánh backlog trong queue xử lý.
Consumer webhook gọi API đối tác có giới hạn kết nối thấp; khi tăng concurrency của queue, API nhận HTTP 429 và lượng thông điệp retry tăng nhanh hơn thông điệp mới.
Đội bảo trì tắt worker queue vài giờ nhưng HTTP endpoint vẫn chấp nhận webhook; dashboard vận hành chỉ thấy tỉ lệ 2xx tốt trong khi nhiều sự kiện đã quá hạn nghiệp vụ.
Spring receiver thực hiện xác minh HMAC và giải mã payload rất lớn trực tiếp trên request thread; trong chiến dịch marketing, request bị xếp hàng từ bước xác minh trước khi vào queue.
Nhà cung cấp gửi các webhook heartbeat và webhook nghiệp vụ qua cùng endpoint; các heartbeat mật độ cao làm giới hạn request bị chạm, khiến thông báo thanh toán đến muộn.
Đội giám sát chỉ đếm webhook HTTP 2xx nhận vào mà không theo dõi số sự kiện hoàn tất xử lý; dashboard hiển thị thành công dù tồn tại hàng nghìn bản ghi bị lỗi trong queue.
Trong đợt sự cố, hệ thống phát webhook ghi log request ID nhưng receiver chỉ lưu eventId; nhóm trực không ghép được lịch sử retry của nhà cung cấp với log xử lý nội bộ.
Đối tác yêu cầu thông báo tình trạng delivery theo từng subscription, nhưng ứng dụng chỉ có một metric chung cho mọi webhook; lỗi của một khách hàng bị che khuất trong lưu lượng tổng.
Nhóm bảo mật kiểm tra nhật ký và thấy raw payload webhook chứa thông tin khách hàng được lưu vô thời hạn để điều tra lỗi; quy trình vận hành thiếu thời hạn lưu và phạm vi truy cập rõ ràng.
Receiver thêm logging cho từng request webhook nhưng vô tình đưa eventId chưa chuẩn hóa vào nhãn metrics; số lượng time series tăng mạnh theo số sự kiện nhận được.
Đội kiểm thử chỉ gửi webhook hợp lệ một lần bằng công cụ HTTP; sau triển khai, provider gửi lại cùng eventId nhiều lần và ứng dụng tạo dữ liệu trùng mà test không phát hiện.
Mock provider trong môi trường test luôn gửi webhook theo đúng thứ tự tạo, thanh toán rồi hoàn tiền; production phát thông điệp qua nhiều worker khiến các trạng thái đến đảo lộn.
Bộ test xác minh HMAC tính chữ ký trên JSON đã được chuẩn hóa, còn provider ký raw body có khoảng trắng khác; test pass nhưng webhook thật thường xuyên bị từ chối.
Trong kiểm thử mạng, proxy ngắt kết nối sau khi receiver ghi queue nhưng trước khi trả HTTP 200; một sự kiện được phát lại và logic tiếp nhận hoạt động khác khi chạy hai pod.
Đội kiểm thử tải gửi request liên tục với tốc độ đều nhưng provider thực tế dồn hàng nghìn webhook theo lô sau thời gian mất kết nối; queue và connection pool cạn khi sự cố lặp lại.
Nhà cung cấp bổ sung mẫu event schema mới trong sandbox trước production; hệ thống CI chỉ test webhook tạo đơn và không phát hiện sự kiện thay đổi địa chỉ giao hàng bị parse lỗi.
Một webhook endpoint trả HTTP 500 khi database lỗi ngắn, nhưng công cụ test chỉ assert response body thay vì số lần provider retry và trạng thái xử lý cuối cùng.
Ứng dụng Spring ghi nhận thời điểm webhook đến nhưng không ghi thời điểm sự kiện phát sinh và thời điểm xử lý hoàn tất; đội vận hành không phân biệt được chậm từ phía provider hay backlog nội bộ.
Nhóm hỗ trợ cần phát lại webhook thất bại trong một khoảng thời gian nhưng không lưu đủ metadata về phiên bản payload và tenant; các bản ghi cũ trở nên khó tái xử lý chính xác.
Nhà cung cấp gửi thông báo ngừng dịch vụ qua webhook kỹ thuật cùng loại với sự kiện nghiệp vụ; bộ lọc sự kiện bên nhận bỏ qua thông báo này nên không chuẩn bị cho một lần gián đoạn đã được báo trước.
