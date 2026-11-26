Một nền tảng thương mại điện tử phát sự kiện đặt hàng lên topic Kafka để dịch vụ thanh toán, kho và thông báo xử lý độc lập; sau khi triển khai, nhóm vận hành phát hiện chỉ một trong ba dịch vụ nhận được một số sự kiện.
Ứng dụng ngân hàng cần các sự kiện mở, khóa và mở lại tài khoản được xử lý đúng thứ tự cho từng khách hàng; producer gửi cùng tài khoản vào nhiều partition khiến trạng thái cuối trong hệ thống đích đôi khi sai.
Thị trường vé trực tuyến dùng mã sự kiện làm key cho bản tin đặt vé; vài sự kiện nổi tiếng chiếm phần lớn lưu lượng và một partition quá tải dù các partition còn lại gần như nhàn rỗi.
Nhóm dữ liệu tăng số partition của topic đơn hàng để phục vụ tải cao hơn; các sự kiện mới của một mã đơn bắt đầu phân bố khác trước và thứ tự xử lý của các sự kiện quanh thời điểm mở rộng bị đảo.
Một dịch vụ Java/Spring Kafka phát sự kiện xác nhận thanh toán và nhận thông báo ghi thành công; ngay sau đó broker chứa leader gặp sự cố, khiến nhóm tích hợp nghi ngờ mức bảo đảm lưu bền của bản tin.
Cụm Kafka phục vụ xử lý hóa đơn vừa mất một broker; producer bắt đầu nhận lỗi khi ghi dù partition vẫn còn leader, trong lúc chính sách số replica đồng bộ tối thiểu được đặt cao.
Một broker dẫn đầu partition ngừng hoạt động giữa giờ cao điểm; các consumer tạm ngừng nhận dữ liệu rồi tiếp tục, nhưng một vài bản tin vừa được producer gửi chưa xuất hiện trong báo cáo.
Ứng dụng phân tích hành vi đính kèm toàn bộ dữ liệu phiên người dùng vào một sự kiện Kafka; các bản tin lớn bất thường bị producer hoặc broker từ chối trong khi bản tin nhỏ vẫn được xử lý.
Nhóm triển khai nén cho luồng sự kiện hàng triệu bản tin mỗi phút để giảm lưu lượng mạng; băng thông giảm nhưng CPU trên producer và broker tăng mạnh khiến độ trễ biến động.
Producer Spring Kafka gom sự kiện thành batch để tăng thông lượng; các thông báo xác thực giao dịch ít phát sinh phải chờ lâu hơn dự kiến trước khi đến consumer.
Trong đợt khuyến mãi, tốc độ phát sự kiện vượt khả năng nhận của broker; bộ đệm producer liên tục đầy và các luồng xử lý HTTP chờ gửi bản tin, làm thời gian phản hồi API tăng đột ngột.
Producer gửi nhiều yêu cầu ghi đồng thời và tự thử lại khi mạng lỗi; các sự kiện cập nhật hạn mức xuất hiện khác thứ tự ban đầu ở partition sau một đợt thử lại thất bại.
Dịch vụ thu phí sử dụng producer có cơ chế chống ghi trùng do thử lại nhưng vẫn sinh hai sự kiện nghiệp vụ khác nhau khi cùng yêu cầu từ khách được gửi hai lần; báo cáo thu phí có khoản tiền bị tính lặp.
Một hệ thống logistics dùng mã thiết bị làm key sự kiện, nhưng phiên bản ứng dụng mới bỏ trống key ở một số bản tin; hành trình của cùng xe bị ghép sai trình tự sau khi consumer xử lý song song.
Dịch vụ tạo đơn hàng ghi thành công vào cơ sở dữ liệu rồi mới gửi sự kiện Kafka; tiến trình bị dừng giữa hai thao tác nên kho hàng không nhận được thông tin về một số đơn đã tồn tại.
Một quy trình chuyển tiền phải phát đồng thời sự kiện ghi sổ và sự kiện thông báo sang hai topic Kafka; khi producer lỗi giữa các lần ghi, chỉ một bên nhận được dữ liệu của giao dịch.
Nhóm triển khai Kafka transactions cho chuỗi xử lý đọc từ Kafka rồi ghi sang topic khác; một consumer dùng thiết lập đọc chưa phù hợp nhìn thấy kết quả của giao dịch về sau bị hủy.
Dịch vụ gửi email tiêu thụ sự kiện Kafka và gọi nhà cung cấp email bên ngoài; sau khi email đã gửi, consumer chết trước khi ghi nhận offset nên cùng khách hàng nhận thư hai lần.
Consumer xử lý báo cáo gian lận mất nhiều phút cho mỗi bản tin; trong lúc xử lý lâu không poll tiếp, thành viên bị loại khỏi consumer group và partition chuyển sang một instance khác.
Ứng dụng xử lý đơn hàng dùng auto-commit offset theo lịch khi công việc thực sự còn nằm trong hàng đợi nội bộ; sau khi máy chủ khởi động lại, một số sự kiện đã được đánh dấu hoàn tất nhưng chưa cập nhật đơn hàng.
Consumer Spring Kafka ghi thay đổi sang hệ thống kế toán rồi mới commit offset; lỗi mạng xảy ra ngay trước commit và lần chạy kế tiếp thực hiện lại cùng thay đổi tài chính.
Topic xử lý khách hàng xuất hiện một bản tin JSON sai cấu trúc; consumer liên tục thất bại tại cùng offset khiến các bản tin hợp lệ đứng phía sau trong partition không tiến lên.
Một nền tảng gọi API chấm điểm tín dụng với giới hạn số lần mỗi phút từ consumer Kafka; khi đối tác trả lỗi tạm thời, việc thử lại liên tục làm cả partition bị chậm hàng giờ.
Dịch vụ bảo hiểm chuyển các sự kiện không giải mã được sang topic lỗi; dữ liệu lỗi có thể chứa giấy tờ tùy thân nhưng nhóm vận hành chưa có cách kiểm soát ai được đọc và khi nào phải xóa.
Một consumer group nghỉ hoạt động lâu hơn thời gian lưu giữ dữ liệu của topic; khi chạy lại, offset đã lưu trỏ tới các bản ghi không còn tồn tại nên pipeline thiếu dữ liệu lịch sử.
Nhóm triển khai nhiều phiên bản consumer trong giờ làm việc; mỗi lần một instance tham gia hoặc rời group, thời gian tiêu thụ bản tin ngắt quãng và thông lượng giảm mạnh.
Một topic có sáu partition được đọc bởi mười hai instance thuộc cùng consumer group; đội vận hành ngạc nhiên khi nhiều instance đứng rảnh dù số sự kiện đến rất lớn.
Bảng theo dõi chỉ báo tổng consumer lag thấp nhưng một partition chứa toàn sự kiện của khách hàng lớn bị chậm đáng kể; các thông báo dành cho khách này đến muộn trong khi đa số khách khác bình thường.
Nhóm phân tích muốn chạy lại toàn bộ sự kiện tháng trước để sửa phép tính; ứng dụng đọc lại dùng cùng group ID với tiến trình đang phục vụ production nên việc tiêu thụ dữ liệu mới bị ảnh hưởng.
Topic Kafka chỉ giữ dữ liệu trong một số ngày vì giới hạn dung lượng; sau sự cố kéo dài, consumer phục hồi nhưng không còn đọc được những sự kiện phát sinh ở đầu khoảng gián đoạn.
Dịch vụ duy trì trạng thái hiện tại của sản phẩm bằng topic có log compaction; một sản phẩm đã xóa vẫn xuất hiện ở hệ thống nhận vì sự kiện xóa và quá trình dọn dữ liệu không được hiểu nhất quán.
Một consumer mới khởi động cần dựng lại bảng giá hiện tại từ topic compacted; dữ liệu nhiều phiên bản theo key tồn tại trong log và thứ tự đọc làm trạng thái tạm thời thay đổi trước khi bắt kịp cuối topic.
Nhóm phát triển thêm trường bắt buộc vào schema của sự kiện thanh toán; các consumer cũ đang dùng phiên bản schema trước đó không còn giải mã được bản tin phát từ producer mới.
Nhiều dịch vụ dùng chung topic và quản lý schema qua registry; một thay đổi định dạng được chấp nhận ở môi trường thử nghiệm nhưng gây lỗi cho consumer đọc lại dữ liệu lịch sử trong production.
Kafka Connect lấy dữ liệu khách hàng từ cơ sở dữ liệu quan hệ bằng lần snapshot ban đầu rồi đọc thay đổi liên tục; các bản ghi được cập nhật sát lúc chuyển chế độ xuất hiện trùng hoặc thiếu ở kho đích.
Kafka Connect sink ghi sự kiện đặt hàng vào kho tìm kiếm; task bị khởi động lại sau khi ghi dữ liệu nhưng trước khi xác nhận tiến độ, làm một số tài liệu ở đích bị thêm hai lần.
Connector đồng bộ dữ liệu vận hành có nhiều task; một task liên tục thất bại vì bản ghi không hợp lệ trong khi các task khác vẫn chạy, khiến bảng điều khiển chung hiển thị trạng thái dễ gây hiểu nhầm.
Một connector chạy ổn định nhiều tháng thì ngừng lấy dữ liệu từ hệ thống CRM sau khi thông tin xác thực được xoay vòng; các topic vẫn tồn tại nhưng dữ liệu cập nhật không còn xuất hiện.
Nhóm phát triển đổi tên cột mã khách hàng trong cơ sở dữ liệu nguồn; pipeline Kafka Connect tiếp tục phát bản tin nhưng dịch vụ đích không còn khớp cấu trúc dữ liệu mong đợi.
Ứng dụng Kafka Streams tính số đơn trong cửa sổ năm phút theo thời điểm sự kiện; thiết bị di động gửi bù dữ liệu cũ và tổng đã hiển thị trên dashboard bắt đầu lệch với số liệu sau xử lý lại.
Hệ thống kiểm soát gian lận dùng Kafka Streams nối luồng giao dịch với dữ liệu hạn mức theo khách hàng; hai nguồn có cách chia partition khác nhau nên kết quả ghép bị thiếu hoặc không ổn định.
Nhóm vận hành bổ sung bước gom nhóm sự kiện theo mã nhà cung cấp trong ứng dụng Kafka Streams; sau thay đổi, lưu lượng mạng giữa các broker tăng và độ trễ pipeline tăng đáng kể.
Ứng dụng Kafka Streams dùng state store để giữ tổng chi tiêu theo tài khoản; sau khi một instance mất máy, việc dựng lại trạng thái từ changelog kéo dài khiến phân vùng được chuyển sang máy mới chưa phục vụ kịp.
Đội kỹ thuật đổi application.id của ứng dụng Kafka Streams trong lần triển khai mới; tiến trình bắt đầu xử lý lại lượng lớn dữ liệu, còn state store và offset của phiên bản cũ không được dùng như dự kiến.
Hệ thống phân tích sự kiện click nối stream tương tác với bảng thông tin sản phẩm; những sự kiện đến trước khi bản cập nhật bảng sản phẩm được tiêu thụ bị thiếu thuộc tính phân loại trong kết quả.
Ứng dụng Kafka Streams bật chế độ giao dịch để xử lý đúng một lần trong các thao tác đọc và ghi topic Kafka; một downstream độc lập còn ghi dữ liệu vào dịch vụ ngoài Kafka và ghi nhận kết quả bị trùng sau sự cố.
Cụm Kafka dùng KRaft được triển khai với hai controller hoạt động trên hai máy riêng; khi mất một máy, các thao tác cần quorum metadata không còn thực hiện được dù một số broker vẫn chạy.
Khi mất broker ở một khu vực mạng, nhiều partition của topic quan trọng không còn replica đủ điều kiện trở thành leader; các ứng dụng producer và consumer thấy lỗi trên từng tập partition khác nhau.
Cụm Kafka trải trên ba vùng sẵn sàng nhưng nhiều replica của cùng partition được đặt trong cùng một vùng; một lần mất vùng khiến khả năng phục vụ và độ bền dữ liệu của topic bị ảnh hưởng lớn hơn dự kiến.
Một replica chậm sao chép dữ liệu vì ổ đĩa quá tải và dần ra khỏi tập ISR; nhóm vận hành chỉ nhìn trạng thái broker còn sống nên bỏ qua dấu hiệu độ an toàn khi ghi dữ liệu giảm.
Một broker Kafka hết dung lượng ổ đĩa do topic lưu sự kiện lâu hơn dự kiến; producer liên tục lỗi, consumer không đọc được một số partition, còn cụm gặp khó khăn khi cân bằng lại dữ liệu.
Đội vận hành phân phối lại partition giữa các broker sau khi thêm máy; quá trình di chuyển dữ liệu cạnh tranh băng thông với luồng sản xuất khiến latency producer tăng đột biến.
Trong đợt bảo trì cụm KRaft, nhiều controller lần lượt khởi động lại nhưng một máy mất kết nối bất ngờ; trạng thái quorum và việc cập nhật metadata chập chờn khiến thao tác quản trị không ổn định.
Sau khi xoay vòng chứng chỉ TLS cho các broker Kafka, vài producer Java/Spring Kafka không kết nối được dù DNS và cổng dịch vụ vẫn hoạt động; lỗi xảy ra trước khi bản tin được gửi.
Một ứng dụng mới được cấp quyền ghi topic sự kiện nhưng consumer đi kèm không thể đọc hoặc tham gia group; nhóm vận hành thấy lỗi phân quyền khác nhau khi truy cập topic và group ID.
Đơn vị phân tích hành vi thu thập sự kiện chứa email và số điện thoại lên Kafka; các topic được lưu quá lâu và nhiều tài khoản dịch vụ có thể đọc lại dữ liệu nhạy cảm ngoài nhu cầu công việc.
Ứng dụng xử lý giao vận báo consumer lag bằng không nhưng số đơn giao thành công không tăng; tiến trình vẫn poll và commit offset dù bước ghi kết quả sang hệ thống đích liên tục thất bại.
Một team chỉ giám sát CPU và dung lượng Kafka mà không theo dõi request latency, under-replicated partitions và consumer lag; sau sự cố, họ khó phân biệt nghẽn broker, replication hay xử lý consumer.
Trong ngày mở bán, ứng dụng phân tích gửi lượng lớn sự kiện thử nghiệm lên cùng cụm Kafka với hệ thống thanh toán; một nhóm producer sử dụng tài nguyên quá mức làm độ trễ của các dịch vụ khác tăng.
Doanh nghiệp đồng bộ sự kiện Kafka sang cụm dự phòng ở khu vực khác; sau khi chuyển ứng dụng sang cụm dự phòng, các consumer tiếp tục từ vị trí không tương ứng và xảy ra thiếu hoặc lặp dữ liệu.
Nhóm bảo trì triển khai nâng cấp rolling các broker và client Kafka; ứng dụng cũ vẫn chạy nhưng một số tính năng protocol và khả năng xác thực không tương thích làm tốc độ ghi đọc giảm rõ rệt.
Một hệ thống truy vết sự kiện từ REST API qua Kafka đến dịch vụ vận chuyển; khi người dùng phản ánh một đơn bị xử lý hai lần, nhóm vận hành không liên kết được bản tin giữa log producer, consumer và giao dịch nghiệp vụ.
Một ứng dụng thời gian thực dùng timestamp do thiết bị đầu cuối cung cấp để tính trung bình doanh thu theo phút; đồng hồ trên một số thiết bị lệch nhiều giờ làm kết quả cửa sổ Kafka Streams biến động.
Nhà cung cấp logistics có consumer đọc sự kiện đơn hàng từ nhiều topic Kafka; trong khi mỗi partition vẫn giữ thứ tự, ứng dụng lại giả định thứ tự tuyệt đối giữa các topic và cập nhật trạng thái giao hàng sai.
Nhóm vận hành chuẩn bị khôi phục broker mới từ bản sao lưu cũ sau sự cố phần cứng; metadata cụm KRaft và dữ liệu log partition không còn cùng thời điểm khiến broker khởi động không như mong đợi.
