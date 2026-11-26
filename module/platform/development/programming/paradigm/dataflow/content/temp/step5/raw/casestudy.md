Một hệ thống xử lý đơn hàng có bước kiểm tra tồn kho, tính phí và tạo hóa đơn, nhưng nhóm đang chạy mọi bước theo một danh sách cố định; hãy phân tích cách biểu diễn quan hệ phụ thuộc dữ liệu khi có những bước độc lập.
Một công cụ xây dựng báo cáo nhận hai nguồn doanh thu và chi phí rồi tạo bảng lợi nhuận, đôi lúc bảng được xuất trước khi một nguồn hoàn tất; hãy xác định điều kiện sẵn sàng của tác vụ tổng hợp.
Một pipeline nhận dữ liệu cảm biến theo thời gian thực, nhưng bước làm sạch không tạo đầu ra cho những bản ghi lỗi; hãy đánh giá ảnh hưởng của việc thiếu dữ liệu tới các bước phụ thuộc.
Một hệ thống tạo biểu đồ từ các tập dữ liệu đầu vào nhưng hai yêu cầu đồng thời vô tình dùng chung bộ đệm đang được sửa; hãy phân tích ranh giới sở hữu dữ liệu giữa các nút xử lý.
Một đội chuyển quy trình tuần tự sang mô hình dataflow và kỳ vọng mọi nút đều chạy cùng lúc, trong khi nhiều nút cần đầu ra của nút trước; hãy đánh giá khả năng song song thực tế của đồ thị.
Một hệ thống chấm điểm tín dụng có một bước phụ thuộc cả hồ sơ khách hàng và lịch sử nợ, nhưng hai nguồn cập nhật với tốc độ khác nhau; hãy phân tích thời điểm dữ liệu đủ điều kiện để tính điểm.
Một pipeline tạo bản xem trước ảnh cho ba kích thước và chỉ cần tệp gốc đã được giải mã, nhưng triển khai đang chờ tất cả bản xem trước trước đó; hãy xác định những phụ thuộc không cần thiết.
Một công cụ lập đồ thị tác vụ phát hiện đường nối từ nút cuối quay lại nút ban đầu mà không có trạng thái trì hoãn; hãy đánh giá tác động của chu trình này đối với tiến độ xử lý.
Một dịch vụ dùng cùng đầu ra chuẩn hóa khách hàng cho ba nhánh tính thưởng, phân nhóm và gửi thông báo, nhưng chuẩn hóa lại bị chạy ba lần; hãy phân tích việc dùng chung kết quả trong đồ thị.
Một pipeline phân tích tài liệu có nút trích xuất văn bản rồi nhiều nút phát hiện ngôn ngữ và phân loại, nhưng một nút gặp lỗi; hãy đánh giá ảnh hưởng tới những nhánh không phụ thuộc trực tiếp.
Một nhóm quan sát các nút dataflow hoàn thành theo thứ tự khác nhau giữa hai lần chạy và cho rằng kết quả đã sai; hãy phân tích yêu cầu về thứ tự thực thi và tính xác định của đầu ra.
Một dịch vụ chuyển dữ liệu đầu vào thành các bản ghi bất biến nhưng một tác vụ phía sau vẫn sửa trực tiếp object rồi chuyển cho nhánh khác; hãy đánh giá nguy cơ lan truyền trạng thái dùng chung.
Một pipeline phân tích rủi ro bỏ qua bước tra cứu khi đầu vào không đủ thông tin, nhưng đồ thị vẫn có nút phụ thuộc đang chờ mãi; hãy xác định cách định nghĩa hoàn tất của nhánh có điều kiện.
Một hệ thống nhập dữ liệu liên tục từ hai thiết bị và nhóm muốn chạy lại chỉ những tác vụ bị ảnh hưởng khi một thiết bị cập nhật; hãy phân tích yêu cầu nhận diện phần đồ thị cần tính lại.
Một ứng dụng tạo kết quả cuối từ nhiều bước xử lý thuần nhưng một bước đọc thời gian hệ thống và sinh đầu ra khác nhau mỗi lượt; hãy đánh giá tính tái lập của quá trình tính toán.
Một đồ thị dữ liệu có nguồn đọc tệp, nút chuyển đổi, nút ghép và sink lưu trữ, nhưng chưa xác định nơi phát sinh lỗi dữ liệu; hãy phân tích trách nhiệm kiểm tra hợp đồng tại ranh giới các nút.
Một công cụ đề xuất sản phẩm dùng kết quả phân nhóm khách hàng ở cả luồng realtime và batch, nhưng hai luồng có vòng đời dữ liệu khác nhau; hãy đánh giá khả năng tái sử dụng cùng phép biến đổi.
Một quy trình tính giá dùng dữ liệu từ năm bộ phận, một bộ phận gửi lại dữ liệu cũ sau khi đã gửi dữ liệu mới; hãy phân tích nhận diện phiên bản đầu vào hợp lệ cho nút tổng hợp.
Một hệ thống xử lý luồng dữ liệu có nút nhận đầu vào nhanh nhưng nút kết xuất chỉ hoạt động theo từng đợt, dẫn đến backlog; hãy đánh giá cách mô hình dataflow thể hiện tốc độ tiến triển khác nhau.
Một đội thiết kế đồ thị tác vụ tự thay đổi nhánh khi nhận metadata runtime, nhưng bộ lập lịch chỉ biết đồ thị lúc khởi động; hãy xác định yêu cầu quản lý các phụ thuộc phát sinh động.
Một đồ thị xử lý tài chính có hai nhánh tính thuế và phí cùng phụ thuộc một bước tra cứu tỷ giá, nhưng bước tỷ giá thất bại; hãy phân tích những nút phải chờ và những nút vẫn có thể tiến triển.
Một pipeline xử lý video có ba nhánh nhận cùng dữ liệu khung hình, một nhánh chậm hơn hẳn hai nhánh còn lại; hãy đánh giá tác động của fan-out lên bộ nhớ lưu đầu ra trung gian.
Một hệ thống gom kết quả tìm kiếm từ bốn nhà cung cấp, nhưng một nhà cung cấp trả về sau hạn phản hồi; hãy phân tích hợp đồng hoàn tất của nút fan-in khi thiếu một đầu vào.
Một workflow chỉ cần một trong hai nguồn định danh khách hàng nhưng đồ thị đang buộc chờ cả hai; hãy đánh giá cách phân biệt phụ thuộc bắt buộc và phụ thuộc thay thế.
Một nút tổng hợp nhận kết quả từ ba tác vụ mà không biết chúng thuộc cùng phiên yêu cầu hay không, khiến dữ liệu bị ghép chéo; hãy xác định thông tin định danh cần đi cùng các cạnh dữ liệu.
Một nhóm biểu diễn dữ liệu vắng mặt và dữ liệu lỗi bằng cùng một giá trị null, làm nút phía sau không phân biệt được hai tình huống; hãy phân tích hợp đồng đầu ra của nút nguồn.
Một ứng dụng ghép hai bản ghi theo mã giao dịch, nhưng bản ghi từ hệ thống đối tác có thể đến rất muộn; hãy đánh giá thời hạn chờ và vòng đời trạng thái của nút ghép.
Một đồ thị phát hiện gian lận có hai lần chạy cùng lúc cho một khách hàng, đầu ra của lần chạy cũ đến sau lần chạy mới; hãy phân tích yêu cầu nhất quán theo phiên bản tính toán.
Một hệ thống lưu cache kết quả của nút chuyển đổi, sau đó cập nhật quy tắc chuyển đổi nhưng vẫn dùng cache cũ; hãy đánh giá cách xác định tính hợp lệ của kết quả đã lưu.
Một đội thêm một cạnh phụ thuộc mới giữa hai nút đang chạy, khiến vài tác vụ đã bắt đầu trước khi phụ thuộc mới hoàn thành; hãy phân tích an toàn khi thay đổi đồ thị trong runtime.
Một workflow có nhánh xuất PDF và nhánh gửi email cùng phụ thuộc dữ liệu báo cáo, nhưng gửi email vô tình chạy trước khi PDF hoàn tất; hãy làm rõ kiểu phụ thuộc dữ liệu và điều kiện nghiệp vụ.
Một hệ thống có nút phát nhiều kết quả cho một đầu vào, nhưng nút fan-in đang đếm số đầu ra cố định; hãy đánh giá cách xác nhận đủ dữ liệu trước khi tổng hợp.
Một graph scheduler nhận hai bản ghi cùng khóa trong một khoảng ngắn và kích hoạt cùng nút hai lần, trong khi đầu ra phải duy nhất; hãy phân tích rủi ro khởi chạy trùng lặp.
Một pipeline xử lý tài liệu thay đổi định dạng đầu ra của một nút từ danh sách thành bản ghi đơn, nhưng các nút nhận chưa được nâng cấp; hãy đánh giá tính tương thích của hợp đồng cạnh.
Một nút tổng hợp cần dữ liệu của đúng một ngày, nhưng một trong các nhánh upstream trả dữ liệu hôm trước do cache; hãy phân tích cơ chế nhận diện bộ đầu vào nhất quán.
Một đồ thị tác vụ có nút tính toán rất đắt được hai sink sử dụng, nhưng mỗi sink kích hoạt một phiên tính riêng; hãy đánh giá mối quan hệ giữa chia sẻ kết quả và cô lập lỗi.
Một workflow có hai nhánh độc lập cùng ghi vào bảng trạng thái chung thay vì phát kết quả qua cạnh đồ thị, dẫn đến mất cập nhật; hãy phân tích tính đúng đắn của phần trạng thái nằm ngoài dataflow.
Một công cụ dựng báo cáo chỉ thể hiện các cạnh dữ liệu mà không thể hiện tác vụ có side effect, khiến hai thao tác ghi xảy ra sai thứ tự; hãy xác định các phụ thuộc cần được mô hình hóa.
Một bộ lập lịch đồ thị nhận một input mới trong lúc nút downstream đang tính từ input cũ, khiến kết quả có cả hai phiên; hãy phân tích ranh giới snapshot của một lần tính toán.
Một graph engine đánh dấu nút hoàn thành ngay sau khi phát kết quả vào hàng đợi, nhưng sink thực tế chưa nhận hay lưu dữ liệu; hãy phân tích ý nghĩa các trạng thái hoàn tất trong đồ thị.
Một pipeline thương mại điện tử đọc luồng click và luồng mua hàng, hai luồng có tỷ lệ sự kiện rất khác nhau; hãy phân tích cách ghép thông tin mà không chờ không giới hạn.
Một hệ thống giám sát nhận metrics từ hai vùng địa lý và dùng timestamp thiết bị để gộp, nhưng đồng hồ thiết bị lệch nhau; hãy đánh giá độ tin cậy của thứ tự sự kiện.
Một bộ xử lý ghép hai luồng theo vị trí phần tử, nhưng luồng thứ nhất thỉnh thoảng mất bản ghi còn luồng thứ hai không mất; hãy phân tích hậu quả của giả định về cặp dữ liệu.
Một dịch vụ phát một sự kiện đến hai nhánh cảnh báo và lưu trữ, nhánh lưu trữ chạy chậm làm nhánh cảnh báo cũng trễ; hãy đánh giá sự phụ thuộc tốc độ giữa các nhánh.
Một pipeline xử lý dữ liệu cảm biến dùng cửa sổ một phút nhưng nhiều sự kiện có event time đến muộn; hãy phân tích ý nghĩa của việc đóng cửa sổ và sửa kết quả đã phát.
Một hệ thống phân tích giao dịch đẩy tất cả sự kiện của nhiều khách hàng vào một nhóm duy nhất, khiến bộ nhớ trạng thái tăng; hãy đánh giá cách phân chia trạng thái theo khóa nghiệp vụ.
Một luồng thiết bị có thể tạm ngừng phát dữ liệu vài giờ, trong khi luồng khác vẫn hoạt động và nút ghép cứ chờ thiết bị vắng mặt; hãy đánh giá cơ chế xác định luồng im lặng.
Một ứng dụng gửi dữ liệu qua các bước parse, validate và enrich, nhưng bước validate có thể loại nhiều bản ghi; hãy phân tích thay đổi cardinality và tác động đến bộ đếm đầu ra.
Một hệ thống nhận dữ liệu từ file batch và luồng realtime rồi ghép theo khách hàng, nhưng thời điểm hiệu lực của mỗi bản ghi khác nhau; hãy phân tích ngữ nghĩa chọn dữ liệu cần kết hợp.
Một dịch vụ phân tích nhật ký vừa phát kết quả tổng hợp theo cửa sổ vừa chuyển các bản ghi sai định dạng sang luồng riêng, nhưng một sink lỗi; hãy đánh giá chính sách xử lý từng nhánh.
Một pipeline có bước chuyển đổi không giữ encounter order dù bộ phận kế toán cần báo cáo theo thứ tự nhập, khiến kết quả được in xáo trộn; hãy phân tích vị trí cần bảo đảm ordering.
Một hệ thống realtime dùng thao tác gom theo key nhưng số key tăng liên tục theo phiên người dùng, làm state không được giải phóng; hãy đánh giá vòng đời trạng thái của từng nhóm.
Một dịch vụ xử lý ảnh tạo luồng thumbnail và metadata rồi ghép kết quả khi cùng ảnh đã hoàn tất, nhưng thumbnail có nhiều biến thể; hãy xác định nguyên tắc tương ứng giữa các đầu ra.
Một ứng dụng ghép cảnh báo nhiệt độ từ hai nguồn với sai lệch truyền dữ liệu vài giây, không có quy tắc ghép theo thời gian; hãy phân tích chất lượng dữ liệu đầu ra.
Một pipeline sự kiện nhận bản sửa giao dịch sau khi đã xuất thống kê cuối ngày, làm tổng doanh thu không còn chính xác; hãy đánh giá ngữ nghĩa cập nhật hoặc bù trừ kết quả.
Một hệ thống truyền dữ liệu có bước chuẩn hóa tên khách hàng rồi phân tích địa chỉ và phân tích rủi ro ở hai nhánh, nhưng phân tích địa chỉ được nhân bản thừa; hãy đánh giá phụ thuộc và chia sẻ biến đổi.
Một dịch vụ phân phối log đến ba hệ thống tiêu thụ có yêu cầu độ trễ khác nhau, nhưng cùng chia sẻ một buffer đầy; hãy phân tích cách yêu cầu từng subscriber tác động đến toàn pipeline.
Một công cụ xử lý âm thanh thực hiện chuỗi lọc và nén, một bộ lọc cần mẫu tương lai còn bước nén phát kết quả ngay; hãy phân tích độ trễ nội tại của các phép biến đổi phụ thuộc cửa sổ.
Một pipeline đọc dữ liệu CSV có schema thay đổi theo phiên tệp, nhưng bước sau giả định thứ tự cột cố định; hãy đánh giá hợp đồng dữ liệu khi ghép nhiều tệp khác phiên bản.
Một hệ thống ghép báo giá từ nhiều nguồn nhưng một nguồn gửi bản tin lặp lại do reconnect, khiến tổng hợp nhận hai giá trị cho cùng lần cập nhật; hãy phân tích nhận diện trùng lặp trong bước merge.
Một đồ thị tính toán có hai mươi tác vụ độc lập nhưng scheduler chỉ chạy một tác vụ mỗi lượt, dù còn nhiều lõi CPU rảnh; hãy phân tích ràng buộc lập lịch đang giới hạn throughput.
Một pipeline xử lý tài liệu có một bước giải mã nặng CPU nằm trên đường đi của mọi yêu cầu, còn các bước khác chủ yếu chờ I/O; hãy xác định đường găng ảnh hưởng latency.
Một graph engine tạo một tác vụ cho từng dòng trong tệp hàng triệu dòng, làm chi phí lập lịch vượt thời gian xử lý dòng; hãy đánh giá độ hạt tác vụ phù hợp với workload.
Một hệ thống chạy nhiều nhánh song song rồi ghép kết quả, nhưng một nhánh luôn chậm gấp mười nhánh còn lại; hãy phân tích tác động của straggler lên thời gian hoàn thành toàn đồ thị.
Một bộ lập lịch ưu tiên những nút đã sẵn sàng theo thứ tự thêm vào hàng đợi, khiến nút quan trọng gần deadline luôn bị trì hoãn; hãy đánh giá yêu cầu công bằng và ưu tiên.
Một pipeline CPU-bound tăng số worker từ bốn lên sáu mươi bốn trên máy tám lõi và throughput giảm; hãy phân tích tác động của scheduling overhead và tranh chấp tài nguyên.
Một ứng dụng có nhiều nút truy cập cùng cơ sở dữ liệu, lập lịch chạy tất cả cùng lúc làm connection pool cạn; hãy đánh giá giới hạn đồng thời theo loại tài nguyên.
Một hệ thống phân tán gửi dữ liệu trung gian qua mạng giữa các node dù hai tác vụ phụ thuộc có thể chạy cùng máy; hãy phân tích tác động data locality đến chi phí trao đổi.
Một bộ lập lịch graph dùng cùng executor cho tác vụ dài đang chờ mạng và tác vụ ngắn kết hợp kết quả, làm bước tổng hợp bị starvation; hãy phân tích sự phụ thuộc vào worker pool.
Một workflow có mười nghìn nhánh được khởi chạy khi một file lớn đến, nhưng chỉ một trăm nhánh được phép truy cập API đối tác; hãy đánh giá cách giới hạn lượng việc đang chờ.
Một hệ thống gọi hai tác vụ độc lập rồi luôn chờ tác vụ đầu tiên trước khi xử lý kết quả của tác vụ thứ hai đã hoàn tất; hãy phân tích chi phí chờ do chính sách scheduler.
Một nhóm tăng kích thước batch để giảm overhead nhưng kết quả realtime bắt đầu trễ quá SLA; hãy đánh giá đánh đổi giữa throughput và thời gian chờ tạo batch.
Một pipeline có nhiều stage, stage đầu hoàn tất rất nhanh rồi chiếm hết bộ nhớ bằng dữ liệu trung gian trong khi stage sau chậm; hãy xác định độ mất cân bằng cần đo.
Một scheduler gán cùng số worker cho mọi stage dù một stage dùng GPU và stage khác dùng CPU, khiến tài nguyên không được tận dụng; hãy đánh giá ràng buộc năng lực từng loại node.
Một hệ thống đặt retry tác vụ thất bại vào đầu hàng đợi với ưu tiên cao, các tác vụ mới hợp lệ chờ lâu khi downstream đang lỗi; hãy phân tích hiện tượng starvation.
Một workflow muốn dừng sớm khi đã có kết quả đủ tốt nhưng vẫn để các nhánh tìm kiếm phụ tiếp tục tiêu thụ CPU; hãy đánh giá trách nhiệm hủy tác vụ không còn cần thiết.
Một graph engine tự phân phối lại tác vụ khi một worker phản hồi chậm, nhưng worker cũ vẫn tiếp tục xử lý và cả hai cùng ghi sink; hãy phân tích ngữ nghĩa thực thi trùng lặp.
Một hệ thống chạy nhiều phép tính có state dùng chung trên các worker khác nhau, kết quả thay đổi theo lịch chạy dù đầu vào giống nhau; hãy đánh giá tính xác định và khả năng cô lập trạng thái.
Một pipeline dùng tác vụ ưu tiên thấp để làm sạch cache nhưng chúng chiếm hết worker khi đột ngột có dữ liệu quan trọng; hãy xác định chính sách lập lịch cần kiểm thử ở tải đỉnh.
Một đội đo scheduler chỉ bằng số tác vụ hoàn tất mỗi giây nhưng không đo thời gian chờ sẵn sàng của từng nút, nên không thấy nút nghẽn; hãy đánh giá các metric còn thiếu.
Một luồng telemetry nhận mười nghìn bản ghi mỗi giây nhưng bước ghi kho dữ liệu chỉ nhận hai nghìn, buffer tăng mãi; hãy phân tích hệ quả của chênh lệch tốc độ sản xuất và tiêu thụ.
Một pipeline sử dụng hàng đợi hữu hạn giữa hai stage nhưng producer vẫn tiếp tục tạo việc khi hàng đợi đầy, các bản ghi bị từ chối không được quan sát; hãy đánh giá hợp đồng quá tải.
Một subscriber chỉ yêu cầu thêm dữ liệu sau khi xử lý xong batch trước, trong khi upstream phát nhanh khi mới đăng ký; hãy phân tích yêu cầu điều tiết từ downstream.
Một ứng dụng xử lý click dùng buffer rất lớn để giảm áp lực ngược, nhưng một đợt traffic đột biến khiến heap cạn; hãy đánh giá giới hạn an toàn của việc lưu đệm.
Một pipeline xử lý thông báo chọn bỏ bớt event khi quá tải nhưng bộ phận kiểm toán yêu cầu không mất giao dịch, hãy đánh giá khác biệt về yêu cầu dữ liệu giữa các nhánh.
Một hệ thống giới hạn producer ở mức nghìn sự kiện mỗi giây, trong khi consumer có thể xử lý nhanh hơn khi tải thấp và chậm hơn khi tải cao; hãy đánh giá độ thích ứng của kiểm soát tốc độ.
Một graph engine có hai downstream cùng dùng một luồng dữ liệu, một subscriber rất chậm giữ bộ đệm chung không thể giải phóng; hãy phân tích tương tác backpressure tại fan-out.
Một pipeline phát tín hiệu backpressure về upstream nhưng upstream là nguồn UDP không thể chờ, các bản tin tiếp tục tới; hãy đánh giá giới hạn kiểm soát nguồn dữ liệu.
Một producer bị block vì buffer đầy và đang giữ khóa mà consumer cần để tiêu thụ, toàn hệ thống đứng yên; hãy phân tích khả năng deadlock do backpressure.
Một worker tiêu thụ xong dữ liệu nhưng không cập nhật tín hiệu nhu cầu sau khi gặp ngoại lệ, upstream dừng phát dù buffer còn chỗ; hãy đánh giá đường phục hồi của cơ chế điều tiết.
Một hệ thống chỉ theo dõi kích thước hàng đợi mà không theo dõi thời gian chờ của item, có backlog nhỏ nhưng các bản ghi cũ bị trì hoãn rất lâu; hãy phân tích mức độ đáp ứng thời gian thực.
Một API gắn timeout vào bước ghi vào hàng đợi đầy, nhưng client tự retry ngay với tốc độ cao hơn ban đầu; hãy đánh giá vòng phản hồi tải giữa client và pipeline.
Một nguồn sự kiện phát luồng không giới hạn, còn mỗi phần tử cần gọi dịch vụ downstream theo hạn mức kết nối; hãy phân tích số phần tử in-flight có thể an toàn.
Một pipeline sử dụng nhiều buffer nhỏ theo stage, tổng số bản ghi đang chờ vẫn vượt dự toán bộ nhớ; hãy đánh giá cách tính lượng dữ liệu in-flight toàn đồ thị.
Một hệ thống phân phối sự kiện cho hai mục tiêu quan trọng, một mục tiêu chậm khiến mục tiêu nhanh bị chặn và vi phạm SLA; hãy phân tích hợp đồng delivery và cô lập tốc độ.
Một bộ xử lý truyền dữ liệu dùng chiến lược drop-oldest khi đầy, nhưng người dùng cần tái dựng đúng lịch sử thay đổi trạng thái; hãy đánh giá rủi ro mất tính nhân quả.
Một subscriber phát nhu cầu lớn ngay đầu phiên nhưng không thực sự xử lý kịp, làm nhiều dữ liệu tồn trong vùng đệm; hãy phân tích sự khác nhau giữa demand khai báo và năng lực thực.
Một pipeline đang shutdown trong lúc producer bị chặn vì backpressure, shutdown không hoàn tất do thiếu tín hiệu đánh thức; hãy đánh giá vòng đời chấm dứt của các bên.
Một hệ thống streaming cho phép tốc độ nguồn biến động theo mùa, cấu hình buffer cố định đạt test ngày thường nhưng thất bại ở tải đỉnh; hãy phân tích chiến lược kiểm thử giới hạn.
Một graph scheduler giảm tốc độ phát đầu vào để bảo vệ sink, nhưng một nhánh tính toán cần thời gian khởi động lâu và bị thiếu dữ liệu liên tục; hãy đánh giá sự phối hợp tốc độ ở nhiều stage.
Một API tổng hợp thông tin khách hàng bằng CompletableFuture chạy tra cứu hồ sơ và điểm tín dụng độc lập, nhưng thao tác tổng hợp đôi khi bắt đầu trước khi đủ kết quả; hãy phân tích quan hệ phụ thuộc cần biểu diễn.
Một workflow dùng CompletableFuture để xác thực rồi tải dữ liệu phụ thuộc kết quả xác thực, nhưng triển khai tạo một Future lồng trong Future; hãy đánh giá cách phần còn lại của đồ thị nhận trạng thái hoàn thành.
Một hệ thống dùng CompletableFuture để tính giá và phí giao hàng song song, nhưng chỉ quan sát kết quả một nhánh rồi trả response; hãy phân tích điều kiện hoàn tất của bước kết hợp.
Một dịch vụ có nhiều stage CompletableFuture cùng dùng executor nhỏ, callback chậm làm các task khác xếp hàng lâu; hãy đánh giá cách phân bổ execution context.
Một tác vụ CompletableFuture kết thúc exceptionally nhưng callback phục hồi trả giá trị mặc định sai nghiệp vụ, khiến báo cáo kết quả vẫn thành công; hãy phân tích chính sách lan truyền lỗi.
Một nhóm tạo hàng nghìn CompletableFuture cho mỗi request trong khi downstream chỉ chấp nhận ít kết nối, backlog tăng mạnh; hãy đánh giá khả năng kiểm soát số task in-flight.
Một request đặt timeout ở CompletableFuture kết quả nhưng tác vụ gốc vẫn gọi database sau khi client đã nhận lỗi; hãy phân tích khác biệt giữa timeout kết quả và hủy việc thực.
Một workflow dùng allOf để đợi nhiều tác vụ, một tác vụ bị treo vĩnh viễn và không có deadline; hãy đánh giá điểm hoàn tất hoặc thất bại của toàn bộ đồ thị.
Một API cần phản hồi từ nguồn nhanh nhất trong nhiều nguồn dự phòng, nhưng những lời gọi chậm vẫn chiếm tài nguyên sau khi có kết quả; hãy đánh giá trách nhiệm quản lý vòng đời các nhánh.
Một thư viện tạo stage xử lý bất đồng bộ rồi bỏ tham chiếu đến Future trả về, một lỗi nền không xuất hiện trong log; hãy phân tích khả năng quan sát ngoại lệ của chuỗi.
Một callback CompletableFuture dùng đối tượng request mutable chung, trong khi thread xử lý HTTP đã cập nhật object cho lần gọi khác; hãy đánh giá tính an toàn dữ liệu giữa các stage.
Một tác vụ trong executor một luồng lại chờ một CompletableFuture được lên lịch trong chính executor đó, khiến graph không tiến triển; hãy phân tích phụ thuộc giữa task và worker.
Một ứng dụng ghép kết quả hai Future nhưng một nhánh trả dữ liệu cũ từ cache, trạng thái hoàn tất vẫn bình thường; hãy đánh giá ranh giới giữa completion và tính hợp lệ dữ liệu.
Một hệ thống chuyển lỗi từ một Future thành chuỗi thông báo chung, làm caller không phân biệt timeout, từ chối và dữ liệu sai; hãy phân tích hợp đồng lỗi của từng cạnh.
Một callback async cập nhật bảng thống kê khi kết quả hoàn tất, nhưng callback có thể chạy đồng thời với thao tác đọc báo cáo; hãy đánh giá điểm chia sẻ state ngoài đồ thị.
Một dịch vụ đặt lịch chạy một tác vụ phụ không bắt buộc trong chuỗi CompletableFuture chính, nhưng lỗi tác vụ phụ làm request thất bại; hãy xác định chính sách phụ thuộc nghiệp vụ cần làm rõ.
Một batch có nhiều CompletableFuture kết thúc không theo thứ tự đầu vào, trong khi file đầu ra yêu cầu giữ thứ tự bản ghi gốc; hãy đánh giá cách biểu diễn quan hệ vị trí kết quả.
Một tác vụ cha bị hủy khi người dùng ngắt kết nối, nhưng các CompletableFuture con đã bắt đầu vẫn tiếp tục gửi lệnh ra ngoài; hãy phân tích phạm vi hiệu lực của cancellation.
Một hệ thống dùng callback trong chuỗi CompletableFuture để mở transaction nhưng luồng callback chuyển sang executor khác giữa chừng, ngữ cảnh transaction không có; hãy đánh giá ranh giới thực thi.
Một nhóm nâng phiên bản JDK rồi đổi cấu hình executor và đo thấy CompletableFuture chậm hơn, nhưng không phân biệt thời gian chờ hàng đợi với thời gian xử lý; hãy đánh giá thiết kế phép đo.
Một Publisher phát dữ liệu cảm biến và Subscriber xử lý từng bản ghi, nhưng Subscriber không phát thêm nhu cầu sau batch đầu; hãy phân tích tiến độ của luồng theo hợp đồng Reactive Streams.
Một pipeline Reactive Streams có một subscriber nhận dữ liệu qua mạng rất chậm, còn publisher tiếp tục tăng tốc; hãy đánh giá cơ chế điều tiết nhu cầu và giới hạn lưu đệm.
Một ứng dụng nhận tín hiệu onError trong luồng nhưng vẫn kỳ vọng cùng subscription tiếp tục phát dữ liệu bình thường; hãy phân tích hợp đồng vòng đời của stream sau tín hiệu kết thúc.
Một publisher dữ liệu tài chính được chia sẻ cho nhiều subscriber, một subscriber đăng ký muộn bỏ lỡ bản tin trước đó; hãy đánh giá ngữ nghĩa hot và cold sources.
Một luồng ánh xạ các bản ghi thành tác vụ bất đồng bộ và kết quả hoàn thành lộn thứ tự, bộ phận báo cáo đòi thứ tự nguồn; hãy phân tích yêu cầu ordering ở operator.
Một pipeline chuyển công việc sang scheduler khác ở một stage, nhưng một callback vẫn dùng dữ liệu gắn với thread trước đó; hãy đánh giá giới hạn truyền ngữ cảnh qua ranh giới lịch.
Một reactive pipeline bị một operator blocking giữ worker trong thời gian dài, dù downstream đã sẵn sàng nhận; hãy xác định điểm cần chẩn đoán về scheduling.
Một subscriber gửi yêu cầu rất lớn rồi xử lý từng phần tử bằng I/O chậm, gây tràn buffer nội bộ của một operator; hãy đánh giá ý nghĩa điều khiển demand.
Một hệ thống có operator retry khi lỗi mạng nhưng sự kiện trước lỗi đã tạo side effect ghi dữ liệu, dẫn đến bản ghi trùng; hãy phân tích tác động của resubscription.
Một publisher phát dữ liệu không giới hạn và một operator gom toàn bộ phần tử trước khi phát, ứng dụng không bao giờ có đầu ra; hãy đánh giá tính phù hợp của phép gom với nguồn mở.
Một dịch vụ có hai luồng Reactive Streams độc lập cần ghép dữ liệu theo mã yêu cầu, nhưng một phía trả kết quả chậm; hãy đánh giá vòng đời state giữ các bản ghi chưa ghép.
Một subscriber hủy subscription sau khi người dùng đóng trang, nhưng công việc xử lý đã được chuyển vào một executor phụ vẫn chạy; hãy phân tích phạm vi cancellation.
Một hệ thống dùng processor chia sẻ một danh sách mutable cho nhiều tín hiệu onNext xảy ra ở các thread khác nhau, kết quả bị xáo trộn; hãy đánh giá yêu cầu tuần tự hóa tín hiệu.
Một pipeline reactive ghi log trước mỗi bước rồi thấy số dòng log khác số dòng sink nhận do lọc và retry, nhóm dùng số log để suy ra mất dữ liệu; hãy phân tích ngữ nghĩa đo đếm theo stage.
Một subscriber vừa nhận onComplete vừa gặp callback async đang xử lý dữ liệu cũ, kết quả cuối đôi khi thiếu bản ghi; hãy đánh giá ranh giới hoàn tất của các công việc đã tách rời.
Một producer tạo luồng từ hàng đợi external nhưng việc hủy subscription không ngừng đọc hàng đợi, connection vẫn tiêu thụ tài nguyên; hãy đánh giá hợp đồng cleanup.
Một pipeline reactive có nhiều operator ánh xạ CPU-bound cùng chạy trên một scheduler nhỏ, còn I/O đầu vào rảnh; hãy phân tích rủi ro resource starvation.
Một dịch vụ dùng luồng chia sẻ cho dashboard realtime, nhiều client nối vào cùng nguồn và tốc độ xử lý khác nhau; hãy đánh giá ảnh hưởng của một client chậm lên những client khác.
Một team chuyển xử lý danh sách hữu hạn sang reactive pipeline, nhưng vẫn gọi thao tác blocking lấy kết quả bên trong một callback của cùng scheduler; hãy phân tích nguy cơ tự gây nghẽn.
Một hệ thống triển khai Reactive Streams trên nhiều dịch vụ nối qua mạng, nhóm cho rằng backpressure tự động đi xuyên mọi giao thức HTTP và message broker; hãy đánh giá các ranh giới cần kiểm chứng.
Một pipeline phân tán phân vùng dữ liệu theo mã khách hàng, nhưng một khách hàng có lưu lượng lớn gấp trăm lần người khác; hãy phân tích hiện tượng skew và tác động đến nút chậm.
Một graph engine chuyển dữ liệu trung gian giữa các máy qua mạng nhiều lần cho cùng một nhóm khóa, chi phí truyền vượt thời gian xử lý; hãy đánh giá vai trò vị trí dữ liệu.
Một worker xử lý một partition bị mất kết nối sau khi ghi một phần kết quả, bộ lập lịch gửi lại công việc cho worker khác; hãy phân tích nguy cơ ghi trùng tại sink.
Một pipeline dữ liệu phân tán checkpoint thành công trạng thái xử lý nhưng chưa xác nhận thông điệp đầu vào, sau restart một phần sự kiện được đọc lại; hãy đánh giá tính nhất quán trạng thái và offset.
Một hệ thống yêu cầu exactly-once ở bảng dữ liệu đích nhưng nguồn có thể gửi lại bản ghi và sink không hỗ trợ giao dịch; hãy phân tích phạm vi cam kết end-to-end cần kiểm chứng.
Một ứng dụng dùng các worker nằm ở ba vùng địa lý để ghép dữ liệu, sự chậm trễ của một vùng khiến các cửa sổ khác ngừng hoàn tất; hãy đánh giá ràng buộc thời gian trong phân tán.
Một job dataflow phân tán có bước shuffle theo key làm CPU của nhiều worker rảnh còn network của một worker bão hòa; hãy xác định điểm nghẽn và sự phân phối tải.
Một nhóm nâng phiên bản schema dữ liệu ở một nửa cụm xử lý trong rolling deployment, worker cũ không giải mã được thông điệp mới; hãy phân tích tính tương thích giữa các cạnh liên phiên bản.
Một graph engine lưu state tổng hợp trong bộ nhớ worker rồi worker bị restart, kết quả sau phục hồi khác trước khi lỗi; hãy đánh giá khả năng khôi phục trạng thái và replay.
Một hệ thống phát dữ liệu tới nhiều partition nhưng giả định mọi bản tin toàn cụm giữ đúng thứ tự gửi, thực tế các sink thấy thứ tự khác; hãy phân tích phạm vi bảo đảm ordering.
Một pipeline đồng bộ kho dữ liệu nhận sự kiện cập nhật và sự kiện xóa cùng một thực thể, retry làm sự kiện cũ đến sau sự kiện xóa; hãy đánh giá cơ chế nhận diện thứ tự phiên bản.
Một dịch vụ stream processing dùng thời gian hệ thống của từng node để đóng cửa sổ, đồng hồ lệch khiến cùng một bản ghi bị tính vào hai khoảng khác nhau; hãy phân tích yếu tố đồng hồ.
Một worker hoàn tất tính toán nhưng không thể gửi xác nhận về coordinator do phân vùng mạng, coordinator cấp lại task cho worker mới; hãy đánh giá sự khác nhau giữa thực thi và ghi nhận hoàn tất.
Một chương trình phân tán tải toàn bộ bảng tham chiếu vào từng worker để join, bảng tăng vượt RAM của máy nhỏ nhất; hãy phân tích giới hạn của cách phân phối dữ liệu tham chiếu.
Một nhóm chạy lại một phần đồ thị sau khi thay nguồn dữ liệu, nhưng những kết quả downstream đã lưu không bị đánh dấu vô hiệu; hãy đánh giá tính nhất quán của incremental recomputation.
Một hệ thống chạy graph job theo giờ trên cụm dùng chung, scheduler di chuyển tác vụ giữa node có sức mạnh CPU và GPU khác nhau; hãy phân tích ràng buộc tài nguyên theo stage.
Một pipeline phân tán xử lý dữ liệu nhạy cảm, bản ghi trung gian được gửi sang node ngoài vùng được phép lưu trữ; hãy đánh giá yêu cầu vị trí xử lý và ranh giới tin cậy.
Một dịch vụ đọc message broker rồi đẩy vào graph phân tán, có hai cơ chế retry độc lập ở broker và ở graph, các bản ghi bị nhân đôi; hãy phân tích tương tác của các lớp phục hồi.
Một job xử lý lớn trải qua nhiều worker, chỉ một worker chậm vì đĩa local yếu và toàn bộ bước fan-in chờ; hãy phân tích cách xác định straggler từ số liệu vận hành.
Một hệ thống cần xác minh kết quả tổng hợp có thể tái lập sau khi mất một vùng dữ liệu, nhưng nguồn sự kiện có hạn lưu trữ ngắn; hãy phân tích phụ thuộc giữa replay và chính sách retention.
Một dashboard thể hiện throughput toàn pipeline ổn định nhưng p99 latency tăng cao do một stage giữ bản ghi lâu; hãy xác định những thước đo theo stage cần quan sát.
Một graph job hoàn tất sai số tổng doanh thu nhưng tất cả các task đều báo thành công, các log không chỉ ra nguồn của bản ghi; hãy phân tích yêu cầu truy vết data lineage.
Một hệ thống đo tổng số phần tử đầu vào và đầu ra nhưng các operator có thể lọc, nhân bản và gom phần tử, đội vận hành gọi mọi chênh lệch là mất dữ liệu; hãy đánh giá ngữ nghĩa từng metric.
Một pipeline có nhiều nhánh retry và hàng nghìn correlation id, log của một đơn hàng xuất hiện trên các worker khác nhau; hãy phân tích nhu cầu theo dõi quan hệ nhân quả.
Một ứng dụng phân tán phát cảnh báo nếu hàng đợi có hơn một nghìn bản ghi, nhưng tốc độ tiêu thụ thay đổi rất mạnh giữa các giờ; hãy đánh giá tín hiệu backlog thay cho thời gian chờ.
Một nhóm bật ghi log toàn bộ payload ở mỗi nút dataflow để tìm lỗi rồi làm lộ dữ liệu cá nhân trong hệ thống quan sát; hãy phân tích ranh giới an toàn của instrumentation.
Một pipeline báo số lỗi bằng không dù khách hàng không nhận được bản ghi vì sự kiện bị drop khi quá tải, hệ thống không theo dõi drop count; hãy xác định khoảng trống quan sát.
Một graph engine có các node trả kết quả sau vài giây nhưng một sink chỉ flush dữ liệu mỗi phút, monitoring đánh dấu hoàn tất ngay tại node trước sink; hãy đánh giá tiêu chí hoàn tất thực tế.
Một workflow chạy lại do timeout sau khi đã gửi yêu cầu thanh toán, metric chỉ đếm lần task thành công mà không đếm side effect ở downstream; hãy phân tích sai lệch giữa metric và thực tế nghiệp vụ.
Một hệ thống nhận dữ liệu IoT có tốc độ ổn định nhưng sau mỗi lần checkpoint xuất hiện đợt tăng latency, đội ngũ không phân tách thời gian checkpoint khỏi thời gian xử lý; hãy đánh giá nguồn số liệu cần có.
Một pipeline xử lý ảnh có giai đoạn CPU và GPU, tổng CPU usage thấp nhưng hàng đợi trước GPU liên tục tăng; hãy phân tích cách xác định nút nghẽn qua metric tài nguyên.
Một dịch vụ chuyển đổi dữ liệu chạy trong container bị CPU throttling, thời gian hoàn tất tăng dù số worker và đồ thị không đổi; hãy đánh giá tác động của môi trường đến lịch tác vụ.
Một hệ thống thay đổi schema đầu vào mà không tăng version trong metadata, kết quả gộp sai sau một ngày triển khai; hãy phân tích nhu cầu kiểm tra provenance của dữ liệu và transform.
Một graph workflow phát sinh lỗi hiếm gặp khi hai sự kiện cùng khóa đến gần nhau, nhưng trace chỉ ghi thứ tự nhận tại sink chứ không ghi thứ tự qua các stage; hãy đánh giá độ đầy đủ của trace.
Một đội thu metric với nhãn chứa mã khách hàng cho mọi nút, số chuỗi thời gian tăng không giới hạn; hãy phân tích đánh đổi giữa độ chi tiết và chi phí quan sát.
Một pipeline dùng cache ở nhiều stage nhưng monitoring chỉ ghi cache hit chung, không phân biệt dữ liệu đúng phiên bản; hãy đánh giá khả năng phát hiện stale result.
Một nhóm điều tra lỗi dataflow bằng cách replay dữ liệu production vào staging, nhưng môi trường staging có khác version transform và nguồn tham chiếu; hãy đánh giá tính tái lập của kết quả.
Một hệ thống muốn rollback bản triển khai pipeline khi chất lượng dữ liệu suy giảm, nhưng các event đã được xử lý bởi schema mới; hãy phân tích điều kiện an toàn của rollback.
Một dịch vụ dataflow nhận cấu hình động từ control plane, một nửa worker đã áp dụng cấu hình mới còn nửa kia chưa, dashboard báo kết quả phân tán; hãy đánh giá ranh giới phiên bản vận hành.
Một ứng dụng graph processing có một stage không phát output nhiều giờ do thiếu một luồng đầu vào, nhưng số worker vẫn hoạt động bình thường; hãy xác định cách phát hiện stalled progress.
Một bài test dataflow chỉ kiểm tra kết quả cuối của một đường tuyến tính, trong khi production có hai nhánh fan-in/fan-out và dữ liệu tới khác thứ tự; hãy đánh giá độ bao phủ của test.
Một nhóm tạo dữ liệu thử với mỗi sự kiện đến đúng một lần, nhưng môi trường thực có retry và message lặp, kết quả tổng hợp bị nhân đôi; hãy phân tích các trường hợp cần mô phỏng.
Một unit test dùng Thread.sleep để đợi CompletableFuture hoàn thành, thường đạt trên laptop nhưng lỗi trong CI tải cao; hãy đánh giá tính xác định của tiêu chí đồng bộ kiểm thử.
Một hệ thống thử backpressure bằng một producer chậm và subscriber nhanh, trong production subscriber thường chậm hơn nguồn hàng chục lần; hãy xác định tải cần tái hiện.
Một pipeline gộp hai luồng theo event time nhưng test chỉ có dữ liệu đến đúng thứ tự timestamp, không kiểm tra sự kiện muộn; hãy đánh giá các lịch đến cần thử.
Một nhóm kiểm tra error handling bằng cách làm một nút ném ngoại lệ, nhưng không kiểm tra các nút đang chạy và buffer còn dữ liệu; hãy phân tích tình huống cleanup chưa được bao phủ.
Một benchmark scheduler tăng số worker từ một lên ba mươi hai nhưng đồng thời đổi kích thước batch và số CPU cấp cho container; hãy đánh giá tính so sánh của kết quả.
Một dataflow graph có thể thay đổi động, test chỉ tạo đồ thị không có chu trình trong lúc khởi động, còn production thêm cạnh lúc chạy; hãy đánh giá không gian kiểm thử vòng phụ thuộc.
Một hệ thống phân tán thử recovery bằng cách restart worker khi rảnh, nhưng lỗi thật xảy ra giữa lúc ghi sink và xác nhận nguồn; hãy xác định cửa sổ sự cố cần kiểm chứng.
Một workflow dùng CompletableFuture với một executor có một worker trong test và nhiều worker trong production, lỗi race chỉ xảy ra ở production; hãy đánh giá cấu hình test.
Một pipeline streaming có dữ liệu đầu vào vô hạn nhưng test luôn kết thúc sau một trăm bản ghi, không phát hiện state tích lũy ngày càng tăng; hãy phân tích thử nghiệm vòng đời dài.
Một nhóm kiểm thử chỉ so multiset đầu ra mà không so thứ tự, trong khi người nhận cần chuỗi thay đổi theo phiên bản của cùng tài khoản; hãy xác định tính chất dữ liệu cần xác nhận.
Một chương trình dataflow dùng cache theo input hash và test chỉ thay dữ liệu mà không thay phiên bản thuật toán, sau nâng cấp kết quả cũ được dùng lại; hãy đánh giá kịch bản cache invalidation.
Một hệ thống có subscriber gửi nhu cầu từng phần tử nhưng test luôn cấp demand không giới hạn, nên không phát hiện vi phạm Reactive Streams; hãy xác định loại kiểm thử hợp đồng còn thiếu.
Một dịch vụ có hai sink với cam kết nghiệp vụ khác nhau, test xác nhận một sink thành công rồi coi toàn đồ thị hoàn tất; hãy phân tích điều kiện nghiệm thu ở nhiều đầu ra.
Một nhóm muốn chứng minh kết quả của các phép biến đổi thuần không phụ thuộc lịch xử lý, nhưng chỉ chạy một thứ tự input và một số worker cố định; hãy đánh giá thử nghiệm tính xác định.
Một pipeline cần phục hồi sau checkpoint nhưng test chỉ khởi động lại job từ dữ liệu đầu tiên, không nạp trạng thái checkpoint; hãy đánh giá khả năng chứng minh phục hồi thực tế.
Một hệ thống có ba vùng xử lý, thử nghiệm chỉ làm một worker chậm thay vì cắt mạng giữa các vùng, rồi kết luận fault tolerance đạt yêu cầu; hãy đánh giá dạng sự cố chưa được mô phỏng.
Một nhóm đặt mục tiêu giảm p99 latency của dataflow, nhưng benchmark chỉ báo throughput tổng và chưa có phân bố thời gian chờ theo nút; hãy đánh giá tiêu chí đo đạt mục tiêu.
Một bản phát hành mới thay graph topology, schema và backpressure cùng lúc, kiểm thử phát hiện giảm throughput nhưng không thể quy nguyên nhân; hãy phân tích thiết kế thử nghiệm nâng cấp.
