Một hệ thống bán vé dùng một JMS queue cho cả xử lý thanh toán và gửi email, nhưng hai nhóm consumer khác chức năng cùng đọc queue khiến mỗi giao dịch chỉ được một nhóm nhìn thấy.
Dịch vụ thông báo chuyển từ JMS queue sang topic để nhiều ứng dụng nhận cùng sự kiện, nhưng một số consumer vẫn chỉ nhận được từng phần thông điệp sau lần thay đổi đích gửi.
Một publisher Java gửi trạng thái giao hàng vào topic trong khi ứng dụng báo cáo tắt để bảo trì; sau khi khởi động lại, báo cáo không có các sự kiện đã phát trong khoảng ngừng hoạt động.
Hai instance dùng cùng client ID cho durable JMS topic subscription trong thời gian triển khai mở rộng, khiến kết nối của một instance bị từ chối và lượng thông báo xử lý giảm.
Đội vận hành tạo hai durable subscription khác tên cho cùng ứng dụng phân tích; mỗi sự kiện xuất hiện hai lần trong dữ liệu báo cáo dù publisher chỉ gửi một thông điệp.
Ứng dụng giao dịch thay đổi tên durable subscription sau một đợt phát hành; thông điệp tồn ở subscription cũ không đến consumer mới dù broker vẫn lưu chúng.
Trong hệ thống quản lý đơn hàng, hai consumer trên cùng queue phải xử lý các sự kiện theo thứ tự đơn; khi tăng số instance Java, sự kiện của một đơn được hoàn tất không đúng thứ tự.
Một hệ thống đa tenant dùng chung topic để gửi sự kiện hóa đơn; consumer của một tenant vô tình nhận thông điệp thuộc tenant khác sau khi thay đổi cách đặt thuộc tính chọn lọc.
Đội triển khai ActiveMQ Artemis khai báo address dùng định tuyến MULTICAST nhưng producer lại dự kiến phân phối công việc đến đúng một worker; mỗi nhiệm vụ bắt đầu được thực hiện nhiều lần.
Ứng dụng khai báo queue với định tuyến ANYCAST trong Artemis nhưng hệ thống phát sự kiện muốn nhiều nhóm nhận độc lập; chỉ một nhóm ghi nhận được bản cập nhật tồn kho.
Một địa chỉ Artemis được gắn đồng thời các queue ANYCAST và MULTICAST; khi Java producer không chỉ rõ kỳ vọng routing, số thông điệp ở các nhóm tiêu thụ không khớp nhau.
Ứng dụng Java kết nối Artemis gửi thông điệp tới address chưa có queue phù hợp; producer không báo lỗi tức thì nhưng bộ phận vận hành không tìm thấy yêu cầu ở nơi cần xử lý.
Một dịch vụ đặt hàng tạo queue tự động trong Artemis khi lần đầu chạy; sau khi phân tách môi trường, tên address trùng giữa hai tenant làm dữ liệu luân chuyển sai.
Hệ thống sử dụng Virtual Topic của ActiveMQ Classic để mỗi dịch vụ có bản sao sự kiện; khi chuyển sang Artemis, cấu hình mới tạo các queue có tên khác và một số consumer không nhận dữ liệu.
Đội ứng dụng dựa vào composite destination trong ActiveMQ Classic để gửi thông báo đến nhiều nơi; khi chuyển broker, ứng dụng Java báo đã publish nhưng một số đích không còn nhận được thông điệp.
Một cửa hàng dùng JMS message selector lọc theo region và priority nhưng publisher chuyển thuộc tính priority từ số sang chuỗi; queue vẫn tăng trong khi consumer không nhận các giao dịch mới.
Consumer nhận sự kiện qua selector theo mã chi nhánh; sau khi nhà phát thay tên property từ branchId thành branchCode, backlog tăng mà broker không ghi nhận lỗi ứng dụng.
Nền tảng bảo hiểm gắn nhiều thuộc tính trên message để route theo loại hồ sơ, nhưng một consumer dùng selector có điều kiện logic không phù hợp khiến yêu cầu của nhóm ưu tiên bị bỏ lại.
Ứng dụng tạo temporary queue cho lời đáp trong mô hình request/reply JMS; kết nối bị ngắt trước khi có kết quả khiến phản hồi của dịch vụ xét duyệt không còn đến nơi.
Hệ thống xử lý báo giá tạo temporary reply queue mới cho mỗi request nhưng không giải phóng ổn định; số tài nguyên tạm trên broker tăng liên tục khi lưu lượng lớn.
Producer gửi nhiều yêu cầu vào cùng queue và dùng JMSCorrelationID để ghép lời đáp; một phiên bản Java mới không gán correlation ID nhất quán khiến kết quả trả về nhầm đơn hàng.
Một hệ thống gọi RPC giả lập qua JMS với thời hạn chờ ngắn; worker trả phản hồi sau timeout và ứng dụng đầu vào đã đóng phiên, làm các reply trễ tồn đọng.
Dịch vụ kế toán gửi TextMessage chứa JSON nhưng consumer Java cũ lại kỳ vọng ObjectMessage; lỗi chuyển đổi kiểu xuất hiện sau khi một nhóm nâng cấp riêng.
Ứng dụng sử dụng ObjectMessage chứa đối tượng Java được tuần tự hóa; sau khi nâng phiên bản class trên phía phát, consumer phiên bản cũ không giải mã được các thông điệp mới.
Thông điệp hóa đơn được gửi bằng BytesMessage chứa dữ liệu nhị phân nhưng bộ phận audit đọc như văn bản UTF-8; dữ liệu lưu lại bị biến đổi và không thể đối soát.
Một producer gửi mã khách hàng qua JMS property với kiểu số, trong khi các mã có số 0 đầu được yêu cầu giữ nguyên; consumer hiển thị sai khách sau khi nhận dữ liệu.
Nhóm thiết kế sử dụng JMSMessageID làm mã nghiệp vụ tồn tại xuyên các lần phát lại thủ công; sau một đợt replay, hệ thống đích không còn nhận diện đúng yêu cầu gốc.
Ứng dụng phát sự kiện với JMSExpiration ngắn trong giai đoạn cao điểm; nhiều thông điệp đã hết hạn khi consumer hoạt động trở lại, khiến báo cáo ngày thiếu giao dịch.
Nhóm vận hành đặt thời hạn sống của thông điệp lên vài phút nhưng một tác vụ xuất chứng từ thường chờ hàng giờ trong queue; những chứng từ đến hạn không còn được xử lý.
Producer đặt JMSPriority cao cho yêu cầu khẩn cấp nhưng consumer tiếp tục xử lý một lượng lớn thông điệp cũ đã prefetch; yêu cầu ưu tiên bị chờ lâu hơn SLA.
Một ứng dụng cần trì hoãn việc xử lý sự kiện hủy chỗ đến thời điểm hết hạn; sau khi chuyển từ ActiveMQ Classic sang Artemis, các thông điệp hẹn giờ không còn đến thời điểm dự kiến.
Ứng dụng bán lẻ gửi tin nhắn delivery mode NON_PERSISTENT để tăng thông lượng; khi broker khởi động lại đột ngột, những thông báo thanh toán chưa nhận bị mất.
Nhóm chuyển sang gửi thông điệp PERSISTENT nhưng disk lưu journal của Artemis thường xuyên đầy trong mùa cao điểm, làm độ trễ producer tăng và các request đặt hàng bị treo.
Java producer phát JMS message thành công theo log ứng dụng nhưng mất kết nối trước khi nhận được xác nhận kết quả; lần gửi lại sau đó khiến hệ thống đích nhận hai thông điệp cho cùng giao dịch.
Dịch vụ xuất hóa đơn bật chế độ gửi không đồng bộ và ghi nhận thành công ngay khi đưa message vào bộ đệm client; một lần kết nối đứt giữa chừng làm hệ thống nguồn cho rằng hóa đơn đã được gửi.
Ứng dụng Java tạo mới Connection, Session và MessageProducer cho mỗi sự kiện giao hàng; khi có hàng nghìn request đồng thời, số kết nối broker tăng nhanh và thời gian gửi bị kéo dài.
Một ứng dụng dùng chung JMS Session giữa nhiều thread để tiết kiệm tài nguyên; dưới tải đồng thời, consumer gặp lỗi trạng thái và kết quả nhận thông điệp không ổn định.
Dịch vụ thông báo chạy JMSContext theo vòng đời request HTTP nhưng không giải phóng sau lỗi; lượng connection và session trên broker tăng theo thời gian hoạt động.
Spring JMS listener khởi động trước khi địa chỉ broker sẵn sàng; ứng dụng báo trạng thái sống nhưng listener không nhận thông điệp sau khi broker được khôi phục.
Một listener Java dùng AUTO_ACKNOWLEDGE và ghi nhận đơn vào cơ sở dữ liệu trước khi trả kết quả xử lý; khi database lỗi, nhóm phát hiện hành vi nhận lại thông điệp khác kỳ vọng.
Consumer sử dụng CLIENT_ACKNOWLEDGE để xác nhận riêng từng giao dịch, nhưng một Session nhận nhiều thông điệp và việc acknowledge sau một giao dịch khiến các thông điệp khác cũng được đánh dấu đã nhận.
Một ứng dụng dùng DUPS_OK_ACKNOWLEDGE để giảm chi phí xác nhận; sau khi kết nối bị gián đoạn, một số giao dịch được giao lại trong khi consumer không chuẩn bị cho việc trùng.
Consumer nhận ObjectMessage rồi ném exception trong listener nhưng chế độ acknowledgement hiện tại không dẫn đến lần giao lại như nhóm vận hành kỳ vọng; thông điệp lỗi không còn trong queue.
Ứng dụng sử dụng transacted JMS Session nhưng một nhánh xử lý lỗi thoát khỏi hàm mà không commit hoặc rollback; consumer giữ nhiều thông điệp trong trạng thái chưa hoàn tất.
Worker Java nhận hàng chục thông điệp trong cùng JMS transaction rồi gặp lỗi ở thông điệp cuối; cả lô được giao lại và những tác động bên ngoài đã hoàn tất trước đó có nguy cơ bị lặp.
Người dùng gọi API thanh toán, ứng dụng lưu giao dịch vào database rồi gửi JMS message trong transaction riêng; khi broker lỗi sau khi database commit, dịch vụ kho không biết đơn đã thanh toán.
Consumer JMS gửi yêu cầu tới hệ thống ngân hàng rồi commit JMS transaction; khi ứng dụng chết giữa hai thao tác, khoản thu đã xảy ra nhưng thông điệp vẫn có thể được giao lại.
Một hệ thống khai báo XA transaction cho cả database và ActiveMQ, nhưng trong môi trường production có thành phần không tham gia đúng giao dịch phân tán; đôi lúc dữ liệu và message ở hai phía khác nhau.
Đội bảo trì đổi cấu hình transaction manager của Spring JMS; những consumer trước đây rollback khi lỗi nay commit message dù cập nhật nghiệp vụ thất bại.
Ứng dụng xử lý batch đóng JMS Session trước khi commit do exception ở bước cuối; broker giao lại hàng trăm thông điệp dù một phần file xuất đã được ghi thành công.
Trong quá trình thử nghiệm, consumer gọi recover trên Session sau lỗi tạm thời; các thông điệp được giao lại với trạng thái và thứ tự khác dự kiến, khiến logic phía nhận báo giao dịch trùng.
Một producer gửi đồng thời dữ liệu thanh toán đến hai queue khác nhau trong hai JMS Session; yêu cầu thứ nhất được gửi thành công còn yêu cầu thứ hai thất bại khi kết nối mất.
Hệ thống xử lý một nghiệp vụ bằng nhiều message phụ thuộc nhau, nhưng sender đặt chúng trong các transaction riêng; một lần lỗi giữa chừng khiến consumer thấy trạng thái không nhất quán.
Một listener Spring dùng concurrency cao và tích hợp với database theo transaction độc lập; dưới tải, hai thông điệp của cùng khách cùng cập nhật số dư và gây mất thay đổi.
Consumer Java nhận thông điệp đã xử lý thành công nhưng mất kết nối trước acknowledgement; sau khi broker chuyển phiên, cùng lệnh đặt hàng lại xuất hiện ở một instance khác.
Đội triển khai thêm tính năng gửi email xác nhận trong callback JMS; khi email gửi thành công nhưng transaction xử lý message rollback, khách hàng nhận nhiều email cho cùng đơn.
Một thông điệp tính phí luôn gây lỗi vì dữ liệu đầu vào không đúng định dạng; consumer rollback liên tục và số lần xử lý tăng mà backlog bình thường không giảm.
Ứng dụng Java đọc JMSXDeliveryCount để quyết định hướng xử lý sự kiện lỗi, nhưng sau khi đổi broker và cơ chế gửi lại, số lần nhận được ghi nhận khác trước.
ActiveMQ Classic được cấu hình redelivery delay trong ứng dụng Java; khi bật thêm cấu hình liên quan trên broker, thông điệp lỗi xuất hiện lại vào thời điểm khác dự kiến.
Consumer xử lý API đối tác chậm và thường bị ngắt trước khi hoàn tất; cùng một message xuất hiện ở nhiều lần xử lý, trong khi lịch sử retry không ghi rõ lỗi nào gây ra từng lần.
Đội vận hành giới hạn số lần redelivery cho đơn hàng lỗi nhưng cấu hình DLQ khác nhau giữa hai môi trường; môi trường production giữ thông điệp lỗi trong queue chính quá lâu.
Thông điệp chứa địa chỉ giao hàng không hợp lệ bị chuyển sang DLQ, nhưng nhóm hỗ trợ chỉ theo dõi queue chính nên không phát hiện hàng nghìn đơn chưa được xử lý.
Sau khi đổi tên dead-letter address của Artemis, thông điệp bị từ chối biến mất khỏi queue nguồn nhưng không xuất hiện trong queue xử lý lỗi mà nhóm đang theo dõi.
ActiveMQ Classic chuyển các thông điệp hỏng của nhiều nghiệp vụ vào một DLQ dùng chung; đội đối soát không thể xác định nhanh thông điệp nào thuộc luồng thanh toán cần khôi phục.
Hệ thống Artemis có các quy tắc dead-letter khác nhau theo địa chỉ; một queue mới không được áp đúng chính sách và lưu mãi thông điệp lỗi trong queue chính.
Đội hỗ trợ phát lại một loạt message từ DLQ sau khi sửa bug, nhưng một số sự kiện trong đó đã được xử lý thành công trước khi gặp lỗi acknowledgement.
Một sự kiện trong DLQ chứa schema cũ đã bị bỏ khỏi ứng dụng; sau khi nhóm vận hành thử phát lại, listener hiện tại tiếp tục từ chối và vòng lặp lỗi lặp lại.
Consumer phân loại mọi exception thành lỗi có thể thử lại, kể cả thông điệp thiếu trường bắt buộc; nhiều message không bao giờ xử lý được nhưng liên tục chiếm năng lực queue.
Đội triển khai trì hoãn redelivery cho thông báo giao vận, nhưng yêu cầu nghiệp vụ hết hạn trước lần thử lại cuối; hệ thống vẫn cố thực hiện thao tác đã không còn hợp lệ.
Ứng dụng dùng JMS selector để chỉ nhận message mới chưa từng thử lại; các message đã bị giao lại bị bỏ khỏi luồng xử lý chính và dồn tồn đọng không ai nhận.
Trong lúc nâng cấp, một consumer cũ và một consumer mới cùng kết nối queue; phiên bản cũ liên tục từ chối message có schema mới, làm tỷ lệ redelivery tăng dù phiên bản mới hoạt động tốt.
Artemis kích hoạt cơ chế flow control khi một queue tăng quá nhanh; producer Java trong luồng HTTP bị chặn, dẫn đến hàng loạt request frontend hết thời gian chờ.
ActiveMQ Classic đạt giới hạn bộ nhớ dành cho một destination trong mùa flash sale; các producer bị tắc và số lượng thao tác chưa hoàn tất trên ứng dụng tăng vọt.
Đội đặt giới hạn dung lượng địa chỉ Artemis theo cấu hình vận hành; khi đầy, một số thông điệp bị từ chối trong khi các ứng dụng Java vẫn ghi log gửi thành công.
Queue báo cáo có hàng triệu message nhưng mỗi consumer chỉ xử lý vài message mỗi giây; mức sử dụng disk và thời gian khởi động lại broker tăng đến ngưỡng không đáp ứng SLA.
Consumer ActiveMQ Classic sử dụng prefetch lớn trong khi thời gian xử lý từng đơn không đồng đều; một instance giữ rất nhiều message còn các instance khác nhàn rỗi.
Đội giảm prefetch xuống rất nhỏ để cân bằng tải, nhưng thông lượng ứng dụng lại giảm đáng kể khi nhiều thông điệp có kích thước nhỏ và xử lý nhanh.
Một producer đặt kích thước payload JMS rất lớn vì đính kèm toàn bộ tệp hóa đơn; broker dùng nhiều bộ nhớ, thời gian lưu persistent message tăng và consumer bắt đầu timeout.
Hệ thống phát sự kiện marketing qua topic tới hàng chục nhóm consumer; một subscription ngừng đọc trong nhiều ngày và dung lượng lưu trữ của broker tiếp tục tăng.
Một topic phục vụ cả ứng dụng online và hệ thống tổng hợp ban đêm; consumer online cần dữ liệu ngay nhưng hàng đợi durable của hệ thống tổng hợp làm nguồn lực broker bị thiếu.
Trong quá trình ActiveMQ Classic failover, nhiều Java consumer tự kết nối lại rồi nhận những message chưa ACK trước sự cố; doanh nghiệp phát hiện nhiều bản ghi giao dịch bị tạo lặp.
Artemis triển khai high availability với live và backup; khi node chính mất kết nối mạng, ứng dụng gặp khoảng gián đoạn dài hơn mức cho phép dù backup đã được bật.
Sau khi chuyển sang node dự phòng Artemis, một số queue và subscription không được phục hồi đúng như nhóm vận hành kỳ vọng; các listener Java kết nối lại nhưng báo thiếu dữ liệu.
ActiveMQ Classic chạy hai broker có kết nối chuyển tiếp message; sai lệch cấu hình mạng broker làm một sự kiện bị gửi qua nhiều đường và xuất hiện trùng ở queue đích.
Hệ thống tích hợp nhiều site qua mạng broker ActiveMQ Classic; khi WAN chập chờn, thông điệp mới và thông điệp tồn đọng được chuyển đến site khác với độ trễ rất khác nhau.
Nhóm vận hành triển khai rolling upgrade broker nhưng ứng dụng Java chỉ cấu hình một URL kết nối; khi node đó ngừng, toàn bộ producer và consumer mất khả năng trao đổi message.
Ứng dụng dùng failover transport của ActiveMQ Classic; khi kết nối bị chuyển sang broker khác, các request đồng bộ theo JMS vẫn chờ đến hết thời hạn và gây backlog.
Một dịch vụ chuyển từ ActiveMQ Classic sang Artemis nhưng vẫn sử dụng endpoint và giả định protocol cũ; một số phiên bản client OpenWire hoạt động khác nhau và nhiều consumer không khởi tạo được.
Nhóm đang di chuyển các queue từ ActiveMQ Classic sang Artemis, nhưng các message tồn chưa xử lý chỉ còn trên broker cũ; ứng dụng đã đổi địa chỉ kết nối nhưng báo thiếu dữ liệu lịch sử.
Trong quá trình chuyển từ Classic Virtual Topics sang Artemis, nhóm tạo queue mới cho từng subscriber nhưng chưa thống nhất cách chọn message cũ; số liệu báo cáo giữa hai hệ thống không khớp.
Đội triển khai Java JMS dùng thư viện và namespace API của hai thế hệ khác nhau; sau khi đổi client library, ứng dụng biên dịch được nhưng khởi tạo ConnectionFactory trên production thất bại.
Ứng dụng Spring JMS cũ tích hợp ActiveMQ Classic thông qua cấu hình riêng; khi chuyển sang Artemis, tên queue đúng nhưng thông điệp được route khác do address/routing type không tương thích với kỳ vọng.
Nhân viên hỗ trợ thay mật khẩu tài khoản broker nhưng các pod Java vẫn giữ credential trong cấu hình cũ; khi có sự cố kết nối, chỉ những pod kết nối lại mới bắt đầu bị từ chối.
Đội bảo mật giới hạn quyền gửi và nhận theo destination; một service chỉ cần consume nhưng bị cấu hình có quyền ghi, làm các thử nghiệm nội bộ có thể phát message vào queue nghiệp vụ.
Artemis giới hạn quyền theo address và vai trò, nhưng nhóm tạo queue mới không kế thừa đúng cấu hình truy cập; application đăng nhập thành công mà không thể tạo hoặc consume queue cần thiết.
Hệ thống ActiveMQ Classic cho phép anonymous connection trên một connector phục vụ mạng nội bộ; sau khi chuyển hạ tầng sang vùng mạng rộng hơn, broker nhận request từ ứng dụng chưa được định danh.
Nhà cung cấp chứng chỉ TLS cho broker cập nhật chuỗi CA; một số JVM có truststore cũ không kết nối được, trong khi những instance mới khởi động ở môi trường khác vẫn hoạt động.
Ứng dụng Java sử dụng mTLS để truy cập Artemis nhưng chứng chỉ client hết hạn trong lúc service đang chạy; sau khi broker chuyển node, nhiều consumer không thể kết nối lại.
Một nhóm ứng dụng chia sẻ cùng tài khoản JMS cho cả thanh toán và thông báo; khi cần thu hồi quyền của một service, toàn bộ service liên quan bị ảnh hưởng.
Broker ghi log thông điệp lỗi với payload nhạy cảm từ hệ thống thanh toán; nhóm kiểm toán phát hiện số thẻ và thông tin khách hàng trong log mà nhiều nhân sự vận hành có quyền xem.
Consumer dùng ObjectMessage nhận dữ liệu từ một ứng dụng bên ngoài; trong đợt cập nhật, broker/client từ chối giải mã class không nằm trong danh sách được tin cậy khiến luồng nghiệp vụ bị gián đoạn.
Hệ thống đặt hàng triển khai JMS client qua một proxy mạng cắt phiên kết nối nhàn rỗi; nhiều consumer chỉ báo lỗi khi có thông điệp mới sau vài giờ không hoạt động.
Đội giám sát chỉ dựa vào số lượng message trong queue và bỏ qua message đã được dispatch nhưng chưa ACK; dashboard hiển thị backlog thấp dù các worker bị treo.
ActiveMQ Classic và Artemis cùng phục vụ một hệ thống trong giai đoạn chuyển đổi; metric redelivery và số lượng consumer có tên tương tự nhưng ý nghĩa hiển thị khác khiến bộ phận vận hành đánh giá sai năng lực.
Ứng dụng tạo mới durable subscription mỗi lần triển khai với tên khác nhau; số subscription không hoạt động và message tồn trên broker tăng nhưng không được báo cáo.
Trong ngày cao điểm, broker có CPU thấp nhưng disk journal đạt ngưỡng cảnh báo; các lệnh gửi persistent message chậm rõ rệt và API đặt hàng bị ảnh hưởng.
Quá trình sao lưu broker diễn ra khi hàng triệu thông điệp vẫn đang được gửi và xác nhận; sau bài tập phục hồi, đội kiểm thử thấy trạng thái queue không trùng với thời điểm nghiệp vụ mong muốn.
Đội vận hành khôi phục cấu hình queue và address vào broker Artemis mới nhưng không có message store tương ứng; ứng dụng kết nối thành công mà các đơn đang chờ từ trước sự cố không xuất hiện.
Một producer ghi log kết quả gửi thành công nhưng không gắn mã tương quan chung với transaction nghiệp vụ; khi người dùng khiếu nại thiếu thông báo, đội trực không xác định được message đã đi đến bước nào.
Ứng dụng có nhiều JMS listener nhưng không giám sát tỷ lệ lỗi chuyển DLQ theo từng destination; những lỗi của hàng đợi quan trọng bị che khuất bởi lưu lượng bình thường của các queue khác.
Trong đợt cao điểm, nhà cung cấp vận chuyển chậm xử lý khiến hàng đợi trả lời JMS tăng nhanh; dashboard chỉ theo dõi queue yêu cầu nên nhóm vận hành không nhận ra các kết quả đã hoàn tất nhưng không được tiêu thụ.
Một đợt chuyển vùng dữ liệu làm thời gian đi qua broker tăng mạnh nhưng ứng dụng chỉ đo thời gian xử lý consumer; SLA bị vi phạm dù từng listener báo thực thi nhanh.
Đội kiểm thử chỉ gửi một message vào queue với một consumer, nhưng production có nhiều session, rollback và failover nên xuất hiện lỗi giao dịch trùng chưa được mô phỏng.
Bộ kiểm thử producer/consumer Java dùng mock JMS provider không mô phỏng đúng acknowledgement và redelivery; bản triển khai thật mất message khi worker gặp lỗi giữa các bước nghiệp vụ.
Một nhóm xây test failover chỉ kiểm tra việc ứng dụng kết nối lại broker, nhưng không kiểm tra các message đang in-flight trước lúc node bị tắt; lỗi ghi nhận đơn trùng chỉ xuất hiện sau triển khai.
Trong bài kiểm thử bảo trì, queue vẫn có message nhưng listener không tự đăng ký lại sau khi broker khôi phục; ứng dụng báo trạng thái khỏe mạnh và không ai phát hiện backlog tăng cho đến sáng hôm sau.
