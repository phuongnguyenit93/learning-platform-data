Một nền tảng bán lẻ dùng Spring Integration để nhận đơn từ nhiều kênh; khi thêm nguồn sự kiện mới, MessageChannel chung không còn phân biệt được nguồn phát và dữ liệu được xử lý sai chính sách.
Nhóm triển khai IntegrationFlow cho xác nhận thanh toán; một bean channel không được đặt đúng tên khiến gateway gửi message vào kênh không có consumer và request bị treo.
Ứng dụng đồng bộ tồn kho sử dụng DirectChannel nối các service activator; một handler gọi API ngoài rất chậm khiến luồng nhận message bị giữ lại và các request khác tăng độ trễ.
Đội chuyển DirectChannel sang ExecutorChannel để giảm thời gian chờ; một tác vụ ném lỗi ở worker nhưng thread gửi không còn nhận exception như trong luồng đồng bộ trước đó.
Nhóm dùng QueueChannel làm bộ đệm khi nhập đơn hàng; lượng message tăng liên tục trong giờ cao điểm khiến bộ nhớ bị lấp dù throughput phía nhận không thay đổi.
Một dịch vụ phân phối thông báo dùng PublishSubscribeChannel để kích hoạt email và audit; một subscriber synchronous ném exception làm một subscriber khác không hoàn tất như đội nghiệp vụ mong đợi.
Đội cấu hình PublishSubscribeChannel với TaskExecutor chạy subscriber song song; các sự kiện cùng một khách được xử lý không theo thứ tự phát và bản audit hiển thị trạng thái cũ.
Nhóm chuyển một số bước sang PriorityChannel để xử lý đơn VIP; message ưu tiên thấp bị tồn lâu khi số đơn ưu tiên cao tăng liên tục trong chiến dịch.
Ứng dụng đặt một RendezvousChannel giữa hệ thống nhận và xử lý; trong lúc downstream ngừng hoạt động, producer bị chặn chờ bên nhận và các kết nối đầu vào hết hạn.
Đội dùng ExecutorChannel với hàng đợi không giới hạn trong luồng tra cứu giá; khi downstream lỗi, message tích tụ và tác vụ mới không đạt deadline của API.
Nhóm xây các luồng Spring Integration trong nhiều @Configuration khác nhau; hai module dùng chung tên inputChannel và message bị chuyển tới handler ngoài nghiệp vụ dự kiến.
Ứng dụng thêm WireTap để ghi bản sao message ra hệ thống giám sát; payload chứa dữ liệu cá nhân đi vào kênh audit có phạm vi quyền truy cập quá rộng.
Đội cấu hình channel interceptor để gắn correlation ID; một nhánh gửi message trực tiếp tới handler không qua channel đó nên log cuối luồng thiếu mã tương quan.
Nhóm triển khai MessageHandler có trạng thái mutable trong singleton; nhiều thread qua ExecutorChannel đồng thời cập nhật biến đếm và kết quả thống kê thấp hơn thực tế.
Ứng dụng cần thay đổi routing runtime mà không restart; một integration flow được đăng ký động nhưng tên channel mới trùng flow đang chạy và message đi vào hai nhánh khác nhau.
Đội sử dụng IntegrationFlowContext để quản lý luồng theo tenant; một tenant bị vô hiệu hóa nhưng flow cũ vẫn nhận message và tiếp tục cập nhật dữ liệu.
Nhóm tách message giữa kênh vào và xử lý bằng bridge; bridge được đăng ký hai lần sau refactor làm cùng đơn hàng được gửi hai lượt tới hệ thống đích.
Ứng dụng xây luồng event thời gian thực bằng FluxMessageChannel; một subscriber xử lý chậm làm nhóm vận hành khó xác định vị trí backlog giữa Reactor và message endpoint.
Đội chuyển input channel từ đồng bộ sang bất đồng bộ mà không sửa quy tắc giao dịch; thao tác chính commit trước khi message downstream hoàn tất khiến dữ liệu ở hai hệ thống lệch.
Nhóm sử dụng PollableChannel để lấy công việc từ queue; scheduler poller chỉ có một thread và một handler bị kẹt khiến các queue khác không được phục vụ.
Ứng dụng đặt queueCapacity của task executor thấp; khi số message tăng, một phần tác vụ bị từ chối ngay sau khi adapter đã nhận dữ liệu nguồn.
Đội có một channel chấp nhận nhiều kiểu payload; một service activator nhận String trong khi router gửi DTO mới và việc dispatch thất bại ở runtime.
Nhóm dùng MessageHeaders chứa các thuộc tính lớn của tập tin; khi message được chuyển qua nhiều kênh, bộ nhớ tăng vì metadata được giữ cùng payload.
Ứng dụng gửi thông tin người dùng trong headers để tái dùng giữa nhiều nhánh; dữ liệu quyền thay đổi trước khi handler cuối chạy và quyết định phân quyền dựa trên thông tin đã cũ.
Đội đưa nhiều MessageChannel vào cùng luồng xử lý cho nhiều khách; thiếu tenant trong headers khiến nhánh cuối có thể ghi kết quả vào namespace không tương ứng.
Một hệ thống thanh toán dùng HeaderValueRouter phân nhánh theo loại giao dịch; một đối tác đổi tên header và các thanh toán hợp lệ đi vào default channel.
Nhóm định tuyến bằng PayloadTypeRouter giữa đơn hàng trực tuyến và offline; một loại DTO kế thừa interface chung được chuyển tới handler không phù hợp sau khi tích hợp nguồn mới.
Ứng dụng dùng router dựa trên nội dung địa chỉ giao hàng; trường country bị null ở dữ liệu legacy và biểu thức định tuyến ném exception trước khi message đến kênh dự phòng.
Đội xây router chọn kênh theo giá trị region trong metadata; các region mới chưa được đăng ký channel nên giao dịch được gửi tới kênh không có consumer.
Nhóm dùng recipient-list router để gửi sự kiện đăng ký tài khoản đến email và CRM; khi một recipient lỗi, trạng thái xử lý của các recipient còn lại khó đối soát.
Ứng dụng triển khai dynamic router gọi service cấu hình ngoài; dịch vụ cấu hình mất kết nối làm toàn bộ message dừng ở bước định tuyến dù các handler đích vẫn hoạt động.
Đội dùng method-based Router chọn luồng theo trạng thái đơn; trạng thái mới được bổ sung nhưng không có nhánh tương ứng và message bị bỏ khỏi quy trình.
Nhóm kiểm tra routing tới defaultOutputChannel; một thay đổi cấu hình làm message chưa được nhận dạng bị xử lý như giao dịch thông thường thay vì ghi nhận riêng.
Ứng dụng đặt resolutionRequired cho router theo cách không phù hợp; một key kênh không tồn tại gây exception lan tới gateway và API trả 500 khi nhận message hợp lệ.
Đội muốn phân nhánh giao dịch theo mức phí và tenant; router chỉ nhìn mức phí nên các giao dịch thuộc hai tenant cùng đi tới service chung không có kiểm soát quyền.
Nhóm dùng router theo XPath để xử lý chứng từ XML; đối tác thay namespace và các chứng từ không còn khớp điều kiện định tuyến.
Ứng dụng dùng router theo JSON path để xác định loại sự kiện; JSON của nguồn mới chứa field có tên trùng ở hai cấp làm rule đọc sai giá trị.
Đội cấu hình routing slip cho luồng duyệt hồ sơ nhiều bước; sau khi loại bỏ một endpoint, message vẫn mang địa chỉ cũ và bị treo ở giữa quy trình.
Nhóm áp routing slip để thay đổi thứ tự kiểm tra bằng headers; một header có thể sửa từ bên ngoài làm thông điệp bỏ qua bước kiểm tra bắt buộc.
Ứng dụng cho phép một message đi qua hai service kiểm soát rủi ro; router phát hai nhánh nhưng không có thông tin nào giúp hệ thống xác định cả hai đã hoàn tất.
Đội định tuyến dữ liệu tới nhiều vùng địa lý theo cấu hình hiện tại; khi cấu hình đổi giữa hai lượt gửi, bản sao của cùng sự kiện đi vào hai vùng khác nhau.
Nhóm dùng RecipientListRouter để broadcast trạng thái đặt vé; một kênh không có subscriber nhưng vẫn được tính là đã phát hành và dashboard hiển thị số gửi thành công không chính xác.
Ứng dụng chỉ gửi sự kiện cho partner có hợp đồng đang hiệu lực; router đọc cache hợp đồng cũ khiến message tiếp tục đi đến partner đã hết quyền nhận.
Đội kiểm thử Router bằng một loại payload chuẩn; case có header thiếu, kiểu sai và nhiều điều kiện trùng nhau không được kiểm nên lỗi chỉ xuất hiện dưới tải thật.
Nhóm cần giám sát tỉ lệ message đi mỗi nhánh Router; metric chỉ đếm đầu vào toàn flow nên không phát hiện một nhánh xử lý đang không còn nhận dữ liệu.
Một ứng dụng chăm sóc khách hàng dùng Filter bỏ qua sự kiện không đủ điều kiện; khi điều kiện lọc thay đổi, nhiều message biến mất mà không có log nguyên nhân bị loại.
Nhóm lọc đơn hàng theo trạng thái APPROVED; upstream gửi trạng thái Approved và các message hợp lệ bị đánh dấu không đủ điều kiện do khác chữ hoa.
Đội dùng SpEL Filter kiểm tổng giá trị giao dịch; một payload có amount null làm expression ném lỗi nhưng đội hỗ trợ nhầm là Filter từ chối nghiệp vụ.
Ứng dụng cấu hình discardChannel cho message không đạt kiểm tra; một bước downstream xem discard là kết quả thành công và báo cáo số đơn hoàn tất bị tăng sai.
Nhóm đặt throwExceptionOnRejection để phản hồi các message bị từ chối; API gateway nhận lỗi kỹ thuật thay vì thông tin nghiệp vụ của các giao dịch không hợp lệ.
Đội thêm Filter để tránh sự kiện trùng; các message thiếu idempotency key bị loại cả khi là sự kiện đầu tiên của một đơn.
Ứng dụng chỉ cho phép event thuộc tenant đã đăng ký; Filter dựa vào header do client cung cấp và thiếu bước xác thực nguồn nên tin nhắn không đáng tin có thể đi qua.
Nhóm dùng Filter trước router để giảm tải; một số sự kiện đáng lẽ phải đi nhánh audit cũng bị loại và lịch sử xử lý không còn đầy đủ.
Đội đặt Filter theo số lần retry trong message header; khi header không được truyền qua transformer, cùng message bị lặp lại mà không chạm ngưỡng giới hạn.
Ứng dụng xử lý yêu cầu hoàn tiền có Filter chặn số âm; kiểu dữ liệu thay từ BigDecimal sang String khiến một số request lọt qua hoặc bị lỗi chuyển kiểu.
Nhóm cấu hình Filter trên collection message; predicate kiểm một trường nested gây lỗi khi đối tác gửi event phiên bản cũ không có trường đó.
Đội muốn audit những message Filter loại bỏ; kênh discard không được nối tới nguồn lưu bền vững và không có bằng chứng khi khách khiếu nại.
Ứng dụng đồng bộ hợp đồng từ nhiều partner; Filter dựa vào timestamp nguồn nhưng clock lệch làm các bản cập nhật mới bị xem là cũ và bỏ.
Nhóm dùng Filter để loại các giao dịch có dấu hiệu gian lận; service kiểm tra điều kiện cần truy vấn ngoài và việc lọc chặn luồng nhận message ở giờ cao điểm.
Đội thay đổi rule Filter tại runtime; các replica còn dùng điều kiện cũ nên một loại message được chấp nhận ở node này nhưng bị loại ở node khác.
Ứng dụng có Filter kiểm trạng thái giao dịch và đồng thời ghi audit trong predicate; khi message được retry, bản ghi audit được tạo nhiều lần dù kết quả lọc không đổi.
Nhóm cần phân biệt Filter rejection và handler failure; cả hai hiện đi chung một errorChannel nên hệ thống cảnh báo không biết phải liên hệ nghiệp vụ hay vận hành.
Ứng dụng dùng Message Transformer chuyển CSV đơn hàng sang DTO; một trường giá có dấu phẩy thập phân khiến dữ liệu được parse sai mà không phát sinh exception.
Đội cấu hình Transformer đổi JSON sang XML cho partner cũ; đối tác thêm field bắt buộc mới nhưng mapping không truyền trường đó và request bị từ chối.
Nhóm dùng @Transformer đổi kiểu payload từ String sang Order; một upstream gửi byte array sau thay đổi adapter làm conversion thất bại ở runtime.
Ứng dụng có Transformer làm sạch thông tin khách trước khi lưu; một trường nhạy cảm mới không được xóa khỏi payload và theo các nhánh khác tới log.
Đội tạo Transformer trả về Message mới nhưng không giữ correlation header; Aggregator ở phía sau không còn xác định được những fragment cùng thuộc một request.
Nhóm chuyển đổi thời điểm giao dịch thành định dạng của đối tác; timezone được lấy theo máy chủ khiến ngày thanh toán bị lệch giữa các vùng.
Ứng dụng định dạng số tiền trong Transformer bằng Double; đơn hàng lớn bị sai số khi thông tin tiền tệ đi qua nhiều bước biến đổi.
Đội chuyển một DTO thành Map dùng cho router; tên key thay đổi nhưng router vẫn dùng key cũ và message rơi vào nhánh mặc định.
Nhóm có Transformer gọi API để lấy tên khách từ customerId; mỗi message thêm một lời gọi mạng và luồng đơn bị chậm khi hệ thống CRM không phản hồi.
Ứng dụng chuyển nội dung PDF thành metadata để xử lý; Transformer giữ toàn bộ file trong bộ nhớ và nhiều giao dịch đồng thời làm container hết heap.
Đội sử dụng Content Enricher bổ sung danh mục sản phẩm; một mã sản phẩm không tồn tại làm phần bổ sung trả null và handler cuối không thể tạo hóa đơn.
Nhóm dùng Header Enricher thêm traceId và tenantId; một header từ message gốc có cùng tên bị ghi đè và mất thông tin phục vụ audit.
Ứng dụng cần bỏ một số header nội bộ trước khi gửi ra partner; Transformer chỉ thay payload khiến header chứa token nội bộ vẫn theo message tới outbound adapter.
Đội dùng Transformer để thay đổi cấu trúc message sau khi ký số; byte payload khác làm chữ ký không còn hợp lệ tại endpoint đối tác.
Nhóm chuyển các địa chỉ giao hàng sang chuẩn quốc tế; Transformer chuẩn hóa sai mã vùng không phổ biến và hàng hóa bị định tuyến nhầm kho.
Ứng dụng hợp nhất dữ liệu từ hai phiên bản hợp đồng sự kiện; một event có field nullable mà Transformer coi bắt buộc khiến dữ liệu lịch sử không được đồng bộ.
Đội thêm Transformer để chỉ lấy danh sách item hợp lệ; kết quả mất thứ tự sản phẩm được người dùng chọn và downstream tạo hóa đơn khác yêu cầu.
Nhóm sử dụng Message Converter tùy chỉnh giữa các kênh; một số DTO không có converter tương ứng và chỉ lỗi khi gửi qua nhánh ít sử dụng.
Ứng dụng chuyển file mã hóa sang dữ liệu gốc tại Transformer; khi giải mã lỗi, raw encrypted content bị đưa vào error log và lộ thông tin không cần thiết.
Đội dùng Transformer đổi payload sang đối tượng mutable dùng chung; hai worker xử lý song song làm thông tin của đơn này ghi đè đơn khác.
Nhóm tạo Transformer trả kết quả dạng List để chuẩn bị fan-out; handler sau xử lý danh sách như một payload duy nhất thay vì các message riêng lẻ.
Một hệ thống gửi phiếu xuất kho dùng Splitter tách danh sách mặt hàng; một đơn có 500 item tạo nhiều message và vượt ngưỡng xử lý của downstream trong giờ cao điểm.
Đội cấu hình Splitter cho batch giao dịch theo ngày; danh sách rỗng không tạo fragment nào và Gateway đợi phản hồi đến hết thời gian timeout.
Nhóm dùng Splitter tách từng trang dữ liệu nguồn; khi một trang không tải được, các trang đã tách vẫn được xử lý và bản báo cáo tổng hợp không đầy đủ.
Ứng dụng tách file CSV thành nhiều thông điệp dòng; một dòng lỗi encoding làm luồng ngừng trong khi các dòng trước đã ghi vào database.
Đội chia một shipment thành nhiều kiện hàng bằng Splitter; mỗi fragment mất thông tin parent shipment nên hệ thống vận chuyển không đối chiếu được đơn gốc.
Nhóm dùng Splitter trả Iterator để giảm bộ nhớ; nguồn dữ liệu bị đóng trước khi Iterator được đọc hết khiến nhiều fragment bị bỏ.
Ứng dụng tách hóa đơn thành các nhóm dòng để tính thuế; trình tự fragment bị thay đổi khi đưa vào ExecutorChannel và kết quả tổng không đúng thứ tự kỳ vọng.
Đội dùng Splitter sau một Transformer tạo List; một phần tử null được chuyển thành fragment không hợp lệ và handler con ném exception.
Nhóm cấu hình Splitter lồng nhau cho order và package; correlation và sequence headers ở cấp trong làm mất thông tin nhóm cấp ngoài.
Ứng dụng dùng Splitter cho XML chứa hàng chục nghìn node; việc tạo mọi fragment ngay một lúc làm số object trong heap tăng nhanh.
Đội tách thông tin kiểm kê theo kho bằng Splitter; một warehouseId bị thiếu ở fragment và route dữ liệu sang kho mặc định không phù hợp.
Nhóm dùng Splitter phát fragment tới nhiều worker; một fragment retry trùng tạo hai kết quả và bước Aggregator phía sau tính dư số lượng.
Ứng dụng tách một yêu cầu xác minh tài khoản thành nhiều bước kiểm tra; bước kiểm tra ảnh không có dữ liệu trả về làm quy trình khó biết đã nhận đủ kết quả.
Đội cần bảo toàn mã batch qua Splitter; một Header Enricher đặt lại correlation ID ở mỗi fragment khiến downstream tạo nhiều nhóm độc lập.
Nhóm dùng Splitter để tạo các message với sequenceNumber và sequenceSize; một nhánh lọc bớt fragment nhưng Aggregator vẫn chờ đủ sequenceSize ban đầu.
Ứng dụng phân phối fragment theo priority giữa các executor; fragment đến không theo số thứ tự và kết quả export được ghép sai bố cục.
Đội tách các mục đặt hàng thành message độc lập; cùng một mã SKU xuất hiện nhiều lần và một bước loại trùng xóa mất số lượng cần xử lý.
Nhóm kiểm thử Splitter với danh sách ba item; production có dữ liệu rỗng, cực lớn và nested split nhưng bộ test chưa phản ánh thay đổi cấu trúc nhóm.
Ứng dụng xử lý một hợp đồng dài qua Splitter rồi dùng Aggregator để gom kết quả; một fragment không bao giờ phản hồi làm group lưu trong bộ nhớ vô thời hạn.
Đội thiết kế Aggregator theo correlationId của đơn hàng; hai tenant cùng dùng orderId và một group chứa kết quả thuộc hai khách hàng khác nhau.
Nhóm dùng Aggregator chờ đủ mọi kết quả đối soát; một fragment bị Filter loại bỏ nhưng release strategy vẫn đợi số lượng ban đầu và không phát response.
Ứng dụng tạo correlation ID mới cho mỗi retry fragment; kết quả của cùng một batch nằm trong các group khác nhau khiến không group nào hoàn tất.
Đội cấu hình Aggregator với release strategy dựa trên sequenceSize; message thiếu header sequenceSize do adapter mới khiến nhóm bị giữ đến timeout.
Nhóm dùng Aggregator để gom điểm từ nhiều nguồn; các nguồn trả kết quả theo thời gian khác nhau và group bị release sớm trước khi nhận nguồn chậm.
Ứng dụng đặt groupTimeout cho Aggregator và phát kết quả partial; bộ phận báo cáo hiểu partial như đã hoàn tất và chốt sai doanh thu.
Đội cấu hình expireGroupsUponCompletion; một fragment đến muộn sau khi group đã hoàn tất tạo group mới và gửi bản tổng hợp thứ hai.
Nhóm muốn lưu nhóm chưa hoàn tất qua restart; Aggregator đang dùng SimpleMessageStore trong RAM nên toàn bộ group chờ bị mất khi pod dừng.
Ứng dụng dùng JdbcMessageStore làm lưu trữ group; schema database của message store chưa được migrate ở production nên các group không được lưu bền vững.
Đội dùng RedisMessageStore cho Aggregator; khi replication lag hoặc TTL thay đổi, group không còn đầy đủ và luồng trả kết quả thiếu fragment.
Nhóm chạy Aggregator trên nhiều instance ứng dụng; các fragment cùng correlationId đến những pod khác nhau và mỗi instance giữ một phần kết quả.
Ứng dụng cần gom kết quả theo cửa sổ thời gian; groupTimeout dựa trên thời gian chờ không phù hợp với sự kiện đến trễ từ mạng của đối tác.
Đội sử dụng correlationStrategy lấy customerId thay vì transactionId; các giao dịch của cùng khách được gom chung vào một group và mất ranh giới nghiệp vụ.
Nhóm dùng Aggregator trả danh sách theo thứ tự nhận; fragment được xử lý song song làm thứ tự item trong file xuất thay đổi giữa hai lần thực thi.
Ứng dụng đánh dấu group hoàn thành khi nhận signal đặc biệt; signal đến trước một fragment chậm khiến báo cáo thiếu kết quả nhưng vẫn được gửi.
Đội muốn chỉ trả kết quả khi mọi chi nhánh xác nhận; một chi nhánh trả cùng xác nhận hai lần và Aggregator đếm thành đủ số phản hồi.
Nhóm thêm custom MessageGroupProcessor để gộp đơn hàng; một field tiền tệ khác đơn vị không được xét nên tổng hợp nhiều currency bị sai.
Ứng dụng nhận lại fragment trùng sau retry từ HTTP; group hiện không phân biệt messageId cũ và mới nên tính phần trăm tiến độ vượt 100%.
Đội cấu hình Aggregator để loại group hết hạn; thông tin về fragment thiếu không được ghi audit và đội hỗ trợ không xác định được bước nào thất bại.
Nhóm dùng Aggregator sau fan-out ba nhánh; chỉ hai nhánh gửi kết quả do nhánh thứ ba trả void và quy trình chờ mãi không có thông báo chẩn đoán.
Ứng dụng muốn phát kết quả tạm trước khi hoàn tất group; một client nhận nhiều bản tổng hợp nhưng không phân biệt partial với final và ghi đè dữ liệu đúng.
Đội dùng group khóa theo correlationId trong cơ sở dữ liệu; khi nhiều worker cùng cập nhật một group nóng, lock contention làm throughput suy giảm.
Nhóm kiểm tra Aggregator bằng ba message đến đúng thứ tự; sự cố thực tế chỉ phát sinh khi fragment đến trễ, lặp hoặc không đến và group đã hết hạn.
Một dịch vụ truyền thông tin nhập khẩu qua Resequencer; các message đến ngược thứ tự nhưng thiếu sequenceNumber nên luồng không sắp xếp được như mong muốn.
Đội dùng Resequencer trước khi cập nhật trạng thái kiện hàng; một sự kiện bị mất làm các sự kiện sau bị giữ lại và UI không cập nhật kịp.
Nhóm cấu hình timeout cho Resequencer; khi hết thời gian chờ, việc phát chuỗi không đầy đủ làm trạng thái nghiệp vụ nhảy cóc qua bước kiểm tra.
Ứng dụng chạy sequence theo từng khách; correlation key không chứa tenant nên sự kiện giống mã khách từ hai vùng bị sắp chung và trả thứ tự sai.
Đội dùng resequencing cho file dữ liệu lớn; bộ đệm giữ hàng nghìn message mà không có giới hạn hợp lý làm heap tăng trong lúc nguồn gửi bị gián đoạn.
Nhóm triển khai Aggregator và Resequencer trong một flow; sequence header bị tạo lại sau Splitter thứ hai nên thông điệp được xếp theo cấp nhóm không mong muốn.
Ứng dụng tạo Gateway interface bằng @MessagingGateway cho OrderService; replyChannel chưa có subscriber trả kết quả và HTTP request gọi gateway đợi đến timeout.
Đội thiết kế request-reply qua MessagingGateway; một handler chỉ gửi command tới hệ thống ngoài mà không có reply nên caller đồng bộ luôn chờ dù lệnh đã được nhận.
Nhóm cấu hình defaultRequestChannel cho gateway; sau khi đổi tên channel trong IntegrationFlow, proxy vẫn gửi tới kênh cũ và không nhận được phản hồi.
Ứng dụng có gateway method trả OrderResponse; handler trả payload kiểu Map không có converter tương ứng và gateway lỗi khi chuyển kết quả về DTO.
Đội áp @Gateway trên các method của cùng interface; một method cần request channel riêng nhưng đang dùng default channel và bị xử lý bởi service khác.
Nhóm gọi gateway từ transaction ghi đơn hàng; downstream xử lý async sau commit nhưng caller vẫn nghĩ response gateway phản ánh toàn bộ transaction thành công.
Ứng dụng đặt replyTimeout của gateway quá ngắn; hệ thống đối tác xử lý hợp lệ chậm hơn ngưỡng và client gửi lại yêu cầu tạo giao dịch trùng.
Đội để sendTimeout khác với replyTimeout trong gateway; queue channel đầy khiến thời gian đưa message vào luồng dài hơn SLA nhưng nhóm chỉ đo timeout chờ trả lời.
Nhóm dùng gateway trả CompletableFuture cho kiểm tra tồn kho; một nhánh lỗi ném exception trong worker và controller không theo dõi kết quả bất đồng bộ.
Ứng dụng sử dụng gateway để gửi một file lớn; payload mutable bị thay đổi trước khi consumer async xử lý nên kết quả không còn giống dữ liệu thời điểm gọi.
Đội tạo GatewayProxyFactoryBean thủ công trong một module legacy; bean chưa gắn đúng conversion service và response từ một handler không được ánh xạ.
Nhóm thiết lập errorChannel cho gateway; exception ở handler được gửi dưới dạng ErrorMessage nhưng caller vẫn nhận timeout thay vì thông tin thất bại có ngữ nghĩa.
Ứng dụng có hai gateway gọi chung flow theo cùng headers; tên replyChannel của request đầu bị copy sang request thứ hai và kết quả được trả cho caller sai.
Đội dùng gateway khi đồng bộ hóa danh mục sản phẩm; hệ thống đích trả xác nhận đã nhận nhưng nghiệp vụ gốc coi đó là đã ghi dữ liệu cuối cùng.
Nhóm gắn requestId vào gateway headers; một service transformer bỏ header làm không thể đối chiếu response với API request gốc.
Ứng dụng gọi gateway bằng phương thức void cho tác vụ bắt buộc; gateway không có phản hồi về thành công cuối và giao diện vẫn hiển thị đã đồng bộ.
Đội gọi gateway nội bộ khi Servlet request gần hết hạn; message có thể tiếp tục chạy sau khi HTTP timeout và khách gửi yêu cầu trùng ở lần thử lại.
Nhóm muốn một gateway phục vụ nhiều tenant với cấu hình channel riêng; tenantId bị lưu trong field singleton và request đồng thời có thể gửi sai kênh.
Ứng dụng chuyển gateway từ đồng bộ sang bất đồng bộ; exception trước đây ném về caller nay xuất hiện trên errorChannel và bộ phận hỗ trợ không nhận được cảnh báo.
Một ứng dụng nhận bản tin từ file inbound adapter theo poller; khi xử lý file mất nhiều phút, lịch poll tiếp theo không bắt đầu và các file mới nằm chờ quá SLA.
Nhóm nhận sự kiện JMS qua inbound channel adapter; message được ack từ broker trong khi một downstream async handler vẫn chưa commit và dữ liệu có nguy cơ mất khi pod dừng.
Ứng dụng dùng HTTP inbound gateway làm đầu vào cho IntegrationFlow; router gửi tới kênh chỉ xử lý one-way và kết nối HTTP bị treo chờ reply.
Đội ingest tệp từ FTP bằng poller; một file đang được đối tác ghi dở bị tải ngay và Splitter phát ra danh sách dòng chưa hoàn chỉnh.
Nhóm cấu hình poller fixedDelay cho nhập dữ liệu; từng batch ngày càng lớn khiến khoảng cách thực giữa các lần lấy dữ liệu vượt kế hoạch.
Ứng dụng chạy nhiều replica cùng poll một thư mục chung; không có cơ chế phối hợp lấy file nên hai pod gửi cùng file vào một flow.
Đội quản lý thư mục inbound có file rất lớn; poller tải nhiều file trong một lượt và adapter giữ quá nhiều tài nguyên ở đầu flow.
Nhóm sử dụng QueueChannel giữa inbound adapter và handler; message rời nguồn nhưng chưa có cơ chế xác nhận bền vững khi process bị kill.
Ứng dụng dùng Service Activator ghi dữ liệu sau Transformer; transaction chỉ bao quanh handler cuối và các side effect trước đó không rollback cùng nhau.
Đội cấu hình outbound adapter gửi request HTTP từ flow; đối tác trả 202 Accepted nhưng trạng thái công việc trong cơ sở dữ liệu vẫn đang chờ xác nhận cuối.
Nhóm dùng Kafka outbound adapter sau Router; sự kiện đã được gửi broker nhưng transaction database gốc bị rollback khiến hệ thống khác xử lý dữ liệu không tồn tại.
Ứng dụng gửi message qua AMQP outbound gateway đợi reply; message được tiêu thụ nhưng reply routing key sai và gateway báo timeout.
Đội thêm Channel Adapter gửi email ở nhánh cuối; SMTP đã chấp nhận message nhưng báo cáo trong IntegrationFlow đánh dấu chắc chắn thư tới inbox.
Nhóm nhận webhook đối tác qua HTTP gateway và phát nhiều nhánh; một nhánh lỗi không được quản lý nhưng HTTP response đã trả 200 khiến đối tác không retry.
Ứng dụng dùng Poller trên bảng outbox chưa gửi; hai worker đọc cùng bản ghi và phát hai message do chưa kiểm soát tranh chấp khi poll.
Đội dùng FileWritingMessageHandler lưu báo cáo; một fragment lỗi sau khi phần đầu file đã được ghi và khách nhận bản báo cáo không đầy đủ.
Nhóm triển khai một flow kết hợp inbound và outbound gateway; chờ phản hồi đồng bộ xuyên nhiều adapter làm thread đầu vào bị chiếm khi downstream có sự cố.
Ứng dụng dùng retry advice cho Service Activator gọi API thanh toán; request đầu đã thành công nhưng response timeout dẫn tới retry và tạo hai khoản thu.
Đội đặt RequestHandlerRetryAdvice cho một handler nhận message từ queue; retry nhiều lần trong cùng thread giữ consumer và backlog tăng ở các partition khác.
Nhóm chọn backoff cố định cho lỗi HTTP 503; hàng nghìn message cùng retry sau cùng khoảng thời gian khiến đối tác vừa phục hồi bị quá tải lần nữa.
Ứng dụng thử lại vô hạn lỗi chuyển schema không hợp lệ; message độc vẫn chiếm worker và các giao dịch hợp lệ ở phía sau không được xử lý.
Đội dùng retry cho toàn bộ IntegrationFlow; một nhánh tạo side effect đã hoàn tất trước khi nhánh khác lỗi nên các lần retry gây dữ liệu bị ghi lặp.
Nhóm cấu hình ErrorMessageSendingRecoverer sau số lần thử tối đa; payload lỗi được gửi kênh giám sát nhưng không đủ correlation ID để đối chiếu với giao dịch gốc.
Ứng dụng phân biệt lỗi tạm thời và lỗi vĩnh viễn chưa rõ; cùng chính sách retry được áp cho lỗi mạng lẫn lỗi dữ liệu thiếu trường bắt buộc.
Đội muốn đưa message không xử lý được vào dead-letter channel; kênh này không có consumer bền vững nên message mất khi tiến trình restart.
Nhóm nhận được ErrorMessage từ errorChannel nhưng chỉ ghi log exception; failedMessage và headers bị bỏ nên không xác định được bước router nào gây lỗi.
Ứng dụng có global errorChannel dùng chung nhiều flow; cùng một error handler biến lỗi của báo cáo tùy chọn thành lỗi nghiêm trọng cho nghiệp vụ thanh toán.
Đội khai báo errorChannel riêng cho một flow; gateway vẫn dùng errorChannel mặc định nên exception của một nhánh không đến bộ phận đang theo dõi.
Nhóm dùng PublishSubscribeChannel cho errorChannel; một subscriber gửi cảnh báo lỗi thì chính nó lỗi và hệ thống khó xác định xử lý lỗi ban đầu đã hoàn thành hay chưa.
Ứng dụng muốn gửi ErrorMessage về caller đồng bộ; một worker async phát lỗi sau khi gateway đã timeout và không còn replyChannel hợp lệ.
Đội xử lý lỗi trong transformer bằng cách trả payload rỗng; Filter phía sau coi đó là dữ liệu hợp lệ và sự kiện lỗi không vào errorChannel.
Nhóm triển khai error handler riêng cho router và aggregator; lỗi ở bước phát kết quả cuối bị ghi vào kênh sai do headers của message đã thay đổi.
Ứng dụng lấy exception cause từ ErrorMessage để phân loại; một wrapper exception khác xuất hiện sau nâng framework và lỗi transient bị hiểu thành permanent.
Đội ghi nguyên payload vào error log để debug; message có thông tin định danh cá nhân và token xác thực bị lưu vào hệ thống log tập trung.
Nhóm gửi bản tin lỗi qua message queue để xử lý thủ công; số lần thử lại không được lưu khiến nhân viên phát lại một poison message liên tục.
Ứng dụng muốn retry từ đúng bước thất bại của flow; dữ liệu chỉ lưu message gốc nên các bước có side effect thành công bị chạy lại khi replay.
Đội xây cơ chế cảnh báo khi số ErrorMessage tăng; metric chỉ đếm exception không phân biệt lỗi validation, timeout và thiếu kênh đích.
Nhóm có một errorChannel nhận cả lỗi chuyển kiểu và lỗi cơ sở dữ liệu; nhánh fallback chuyển tất cả thành HTTP 200 và hệ thống báo sai trạng thái đồng bộ.
Ứng dụng đẩy message lỗi sang một kênh bù; bước bù lỗi tiếp tục phát ErrorMessage về kênh gốc tạo vòng lặp xử lý lỗi không kết thúc.
Đội dùng correlationId từ header mặc định khi Splitter phát fragment; một Transformer tạo message mới không giữ header và kết quả không vào group cần thiết.
Nhóm dùng correlation ID bằng orderId cho nhiều lượt thanh toán một đơn; Aggregator vô tình gộp kết quả của các lượt thanh toán khác nhau.
Ứng dụng tạo correlation ID theo UUID ở gateway đầu vào; khi retry qua queue, một gateway khác sinh UUID mới và trace của cùng giao dịch bị chia đôi.
Đội muốn theo dõi từng fragment của một batch; sequenceNumber được log nhưng thiếu sequenceSize nên không phân biệt batch chưa hoàn tất với fragment thất lạc.
Nhóm dùng header tenantId và correlationId ghép thành khóa nhóm; một client được phép đặt cả hai header mà không có xác thực khiến kết quả từ các tenant bị trộn.
Ứng dụng dùng MessageHistory để theo dõi flow; một số endpoint không bật tracking và lịch sử kết quả thiếu đoạn chuyển qua router động.
Đội gắn traceId bằng header enricher trước Splitter; một nhánh HTTP outbound không chuyển header nên log ở hệ thống đối tác không còn cùng dấu vết.
Nhóm dùng WireTap để ghi sự kiện đến từng channel; dữ liệu bản sao được gửi bất đồng bộ và thứ tự log khác với thứ tự message xử lý thực tế.
Ứng dụng vận hành cần biết message dừng ở đâu giữa 12 bước; hiện chỉ có log inbound và outbound nên không xác định được handler hoặc filter làm mất message.
Đội đặt cùng tên message channel trong ba flow độc lập; số liệu Micrometer gộp lại và không thể nhận biết nhánh đang có backlog cao.
Nhóm theo dõi số message được Router nhận và gửi; số lượng tăng gấp đôi do recipient-list routing nhưng dashboard coi mọi tăng trưởng là message trùng.
Ứng dụng ghi metric Aggregator group size và timeout; nhãn correlationId được thêm vào mỗi metric khiến số lượng time series tăng theo từng giao dịch.
Đội tính SLA của gateway chỉ đến lúc message được đưa vào channel; quá trình xử lý async kéo dài nhưng dashboard báo độ trễ thấp hơn thời gian khách nhận kết quả.
Nhóm muốn đo số message bị Filter bỏ và số message lỗi kỹ thuật; cả hai được đánh dấu dropped nên bộ phận nghiệp vụ không phân biệt được nguyên nhân.
Ứng dụng gửi event qua nhiều integration flows theo region; trace không có tên route và tenantId khiến một sự cố chỉ hiện thành nhiều timeout rời rạc.
Đội bật message tracing để chẩn đoán; log chứa toàn bộ payload rất lớn và làm ảnh hưởng throughput ở hệ thống xử lý hàng triệu message.
Nhóm dùng Control Bus để điều chỉnh endpoint runtime; một thao tác tắt nhầm poller khiến luồng không còn nhận dữ liệu mà không có cảnh báo rõ ràng.
Ứng dụng có flow được đăng ký và dừng động; metric của channel cũ vẫn tồn tại sau khi flow bị hủy khiến dashboard hiển thị năng lực xử lý sai.
Đội chạy luồng xử lý trên nhiều pod; mỗi pod có QueueChannel riêng nhưng giám sát chỉ tổng hợp số message đầu vào và không thấy một pod đang ùn tắc.
Nhóm đặt retry metrics trên handler cuối; lỗi tại Router xảy ra sớm hơn không được đếm và tỷ lệ thành công của luồng bị thổi phồng.
Ứng dụng gửi một message qua PublishSubscribeChannel tới ba nhánh; hệ thống chỉ ghi một correlation ID mà không có branch ID nên không biết nhánh nào đã thất bại.
Đội phân tích nhóm Aggregator còn mở; log không có tuổi nhóm và số fragment đã nhận khiến khó quyết định xử lý trường hợp thiếu dữ liệu.
Nhóm cần theo dõi việc chuyển đổi schema của Transformer; tỷ lệ message parse lỗi tăng sau đối tác đổi payload nhưng không có metric tách theo schema version.
Ứng dụng kiểm thử IntegrationFlow cho luồng nhập đơn; testcase chỉ gửi một message hợp lệ nên không phát hiện Router thiếu default channel cho dữ liệu mới.
Đội dùng MockIntegrationContext thay handler thực bằng mock; test xác minh input được nhận nhưng bỏ qua việc outbound gateway không trả reply khi production chạy.
Nhóm kiểm thử Filter bằng message có trạng thái đúng; thiếu testcase null và rejection làm luồng errorChannel chưa được đánh giá thực tế.
Ứng dụng kiểm Transformer với dữ liệu ASCII; tên khách tiếng Việt và số decimal theo locale làm kết quả conversion sai khi lên production.
Đội kiểm Splitter bằng batch ba item; các batch rỗng, cực lớn hoặc nested split không được thử nên header sequence bị sai trên dữ liệu thực.
Nhóm kiểm Aggregator bằng các fragment theo đúng thứ tự; dữ liệu production đến trễ, lặp và thiếu fragment làm group timeout nhưng bộ test vẫn xanh.
Ứng dụng viết integration test cho Gateway với DirectChannel; production dùng ExecutorChannel và lỗi timeout hoặc context propagation không được tái hiện.
Đội kiểm error flow bằng cách ném một RuntimeException trực tiếp; exception thực bị bọc trong MessagingException làm bộ phân loại lỗi chọn chính sách retry khác.
Nhóm dùng IntegrationFlow test giả lập partner luôn trả 200; kịch bản 429, 503, timeout và response đã nhận rồi mất kết nối chưa được kiểm.
Ứng dụng bật transaction rollback trong Spring test; một outbound adapter vẫn gửi message ra broker thật nên test kết thúc để lại side effect không thể rollback.
Đội kiểm correlation qua header do testcase tự thêm; adapter production không giữ header đó và Aggregator không nhận đủ fragment khi triển khai.
Nhóm chạy test nhiều flow cùng ApplicationContext; shared channels và errorChannel vẫn giữ message từ testcase trước khiến assertion phụ thuộc thứ tự chạy.
Ứng dụng dùng QueueChannel.receive với timeout ngắn trong test; máy CI tải cao làm message hợp lệ chưa kịp đến và testcase thất bại ngẫu nhiên.
Đội khởi động poller thực trong IntegrationFlow test; file fixture bị đọc trước khi testcase đăng ký spy handler và sự kiện cần assert bị bỏ qua.
Nhóm thử idempotency bằng một message duy nhất; khi upstream retry cùng sự kiện sau timeout, downstream thực hiện side effect lần thứ hai ngoài ý muốn.
Ứng dụng kiểm group persistence của Aggregator bằng SimpleMessageStore; production dùng JDBC store và lỗi schema hoặc transaction không được phát hiện.
Đội dùng Testcontainers cho adapter JMS và database; testcase shutdown container trước khi poller dừng gây lỗi không ổn định khi teardown.
Nhóm mở rộng integration tests cho nhiều tenant; fixture chỉ chứa tenant mặc định nên việc trộn correlation ID giữa tenant không bị phát hiện.
Ứng dụng sử dụng StepVerifier để kiểm nhánh reactive trong Spring Integration; một phép biến đổi blocking trên Reactor scheduler thật không xuất hiện trong stub tức thì.
Đội đưa một MessageHandler giả vào flow qua mock; trạng thái headers sau outbound adapter thực không được assert và lỗi mất traceId vẫn lọt qua test.
Nhóm chạy load test với 100 message; backlog của QueueChannel chỉ xảy ra khi traffic gấp hàng trăm lần nên cấu hình pool được đánh giá quá lạc quan.
Ứng dụng chuyển từ XML integration configuration sang Java DSL; một endpoint được đăng ký hai lần và cùng message được ghi xuống database hai lượt.
Đội dùng Java DSL để tạo flow với các nhánh router; một nhánh không có terminal handler khiến message được phát nhưng không tạo kết quả nghiệp vụ.
Nhóm cấu hình channel qua annotation và DSL song song; bean name khác nhau nhưng cùng mục đích làm phần giám sát không biết flow nào đang thực sự được sử dụng.
Ứng dụng bật wiretap, retry và audit trong một IntegrationFlow; khi traffic tăng, phần ghi nhật ký trở thành nút thắt và thông báo ưu tiên bị chậm.
Đội triển khai rolling restart với group Aggregator chưa đủ fragment; pod cũ dừng trước khi lưu group và pod mới không thể hoàn tất batch đang xử lý.
Nhóm thiết kế graceful shutdown cho poller và executor; luồng đầu vào ngừng lấy message nhưng worker chưa hoàn tất khi Kubernetes gửi SIGTERM và xóa container.
Ứng dụng tăng số replica để xử lý đơn nhanh hơn; message groups nằm trên bộ nhớ từng instance và các fragment bị phân tán khiến Aggregator không release.
Đội nâng cấp Spring Integration cùng Spring Framework; một biểu thức routing cũ thay đổi cách convert payload và message đi nhánh khác dù API ngoài không đổi.
Nhóm triển khai schema version mới cho message sau Transformer; downstream service cũ không đọc được payload trong giai đoạn canary và errorChannel tăng đột ngột.
Ứng dụng thêm một nhánh recipient-list để gửi thông báo marketing; một nhánh phụ đang lỗi nhưng hệ thống coi toàn bộ message xử lý thất bại và gửi lại thông báo giao dịch.
Đội muốn hỗ trợ phát lại message từ dead-letter channel; message gốc thiếu version của rule Filter và Router nên lần phát lại đi sang nhánh khác thời điểm ban đầu.
Nhóm áp retention ngắn cho MessageGroupStore để tiết kiệm dung lượng; một batch từ đối tác thường đến chậm hơn retention và bị mất fragment cuối.
Ứng dụng xử lý quy trình trả hàng qua Gateway, Router và Aggregator; một worker hoàn tất muộn sau khi order đã bị hủy vẫn cập nhật kết quả dựa trên trạng thái cũ.
Đội xây luồng tách nghĩa vụ thanh toán và vận chuyển với các service activator; lỗi tại nhánh vận chuyển sau khi thu tiền khiến hai hệ thống không còn trạng thái thống nhất.
Nhóm muốn đánh giá end-to-end thông qua nhiều message channels; hiện không có correlation ID xuyên từ HTTP inbound gateway đến outbox nên không thể chứng minh kết quả ứng với yêu cầu nào.
