Một dịch vụ hồ sơ khách hàng xây dựng Mono truy vấn thông tin nhưng không có thành phần nào subscribe, khiến phía vận hành tưởng truy vấn đã chạy dù cơ sở dữ liệu chưa nhận yêu cầu.
Ứng dụng kiểm tra tồn kho tạo Mono từ lời gọi dịch vụ có tác dụng phụ ngay lúc khai báo pipeline, khiến thao tác giữ hàng xảy ra trước cả thời điểm người dùng xác nhận đơn.
Một job đối soát dùng cùng một Mono nguồn lạnh cho hai subscriber, khiến cả hai lần đăng ký đều kích hoạt lại truy vấn đắt đỏ tới hệ thống thanh toán.
Trang quản trị đăng ký lại Flux đọc lịch sử đơn hàng mỗi khi mở tab, khiến một luồng dữ liệu nguồn lạnh bắt đầu tải lại từ đầu và tạo thêm chi phí truy vấn.
Một dịch vụ xác thực mong Mono trả kết quả null khi không tìm thấy tài khoản, nhưng luồng nguồn không phát phần tử nào và các bước xử lý phía sau không chạy như dự kiến.
Một API xóa dữ liệu dùng Mono chỉ biểu diễn hoàn tất thao tác, nhưng tầng gọi lại cố đọc một giá trị trả về và kết luận nhầm rằng lệnh xóa thất bại.
Đội báo cáo gom toàn bộ Flux giao dịch không giới hạn thành một danh sách trước khi xuất thống kê, khiến bộ nhớ tăng cho đến khi tiến trình Java bị dừng.
Một ứng dụng tạo Flux từ tập dữ liệu có thể thay đổi trong lúc xử lý, khiến các lần subscribe ở những thời điểm khác nhau nhìn thấy nội dung không giống nhau.
Dịch vụ gửi thông báo phát một Mono chứa lỗi tra cứu địa chỉ, nhưng bên gọi chỉ log lúc xây dựng pipeline nên không thấy lỗi phát sinh khi dữ liệu thực sự được yêu cầu.
Một màn hình theo dõi tiến trình subscribe hai lần vào nguồn dữ liệu có thao tác ghi trạng thái, khiến cùng một mốc hoàn tất được ghi nhận lặp lại ngoài dự kiến.
Hệ thống khóa học dùng Mono cho thao tác có thể không có kết quả, nhưng bước ghép với một Mono thông tin giáo viên không tạo phản hồi khi phía nguồn thứ nhất hoàn tất rỗng.
Ứng dụng tra cứu tài khoản sử dụng giá trị mặc định cho cả trường hợp không tìm thấy dữ liệu và sự cố kết nối, khiến báo cáo không phân biệt tài khoản vắng mặt với lỗi kỹ thuật.
Một dịch vụ quản lý thiết bị nhận Flux vô hạn các bản đo nhưng thành phần xuất tệp chỉ được thiết kế cho luồng có tín hiệu hoàn tất, khiến tác vụ xuất không bao giờ kết thúc.
Nền tảng học tập phát một Mono kết quả có thể thành công hoặc lỗi, nhưng nhóm tích hợp lại chờ nhiều giá trị tiến độ từ cùng Mono và không nhận được các mốc trung gian.
Một ứng dụng phản hồi khi không tìm thấy khách hàng bằng luồng rỗng, nhưng giao diện xử lý như phản hồi bị treo do không phân biệt onComplete với onNext.
Job tổng hợp hóa đơn dùng map để gọi API trả Mono cho mỗi hóa đơn, khiến subscriber nhận các publisher lồng nhau thay vì kết quả hóa đơn như hợp đồng yêu cầu.
Nền tảng bán vé dùng flatMap để kiểm tra nhiều ghế đồng thời, nhưng kết quả trả về không theo thứ tự danh sách ghế ban đầu và giao diện gán nhầm số thứ tự.
Dịch vụ cập nhật điểm thi dùng concatMap cho hàng nghìn phép tính độc lập, khiến toàn bộ công việc bị kéo dài khi một phép tính ở đầu luồng phản hồi rất chậm.
Một hệ thống xử lý yêu cầu theo thứ tự nguồn nhưng vẫn muốn gọi nhiều dịch vụ ngoài cùng lúc, trong khi cách ghép hiện tại làm kết quả hoàn tất trước được ghi trước.
Ứng dụng chăm sóc khách hàng merge hai luồng sự kiện từ tổng đài và email, nhưng thời gian sự kiện phát ở từng nguồn khác nhau khiến danh sách hiển thị không còn theo thứ tự nghiệp vụ.
Một luồng kiểm toán concat dữ liệu từ hai nguồn, nhưng nguồn đầu liên tục phát sự kiện không kết thúc khiến sự kiện của nguồn thứ hai không bao giờ được đưa tới subscriber.
Hệ thống so sánh giá zip dữ liệu từ ba nhà cung cấp, nhưng một nhà cung cấp hoàn tất rỗng nên không có bộ kết quả tổng hợp dù hai bên còn lại đã phản hồi.
Ứng dụng hiển thị thông tin vận chuyển kết hợp các luồng cập nhật mới nhất, nhưng dashboard không xuất bản ghi nào trước khi tất cả nguồn có ít nhất một giá trị.
Một trang tìm kiếm phát truy vấn mới khi người dùng gõ, nhưng kết quả truy vấn chậm trước đó đến sau và ghi đè danh sách của từ khóa mới.
Dịch vụ xác minh địa chỉ lọc bỏ các bản ghi không hợp lệ, nhưng bước sau luôn giả định có ít nhất một phần tử nên một số yêu cầu hợp lệ rỗng bị kết luận sai.
Nền tảng thống kê dùng distinct trên Flux mã thiết bị hoạt động liên tục nhiều ngày, khiến trạng thái ghi nhớ các mã đã thấy tăng mãi khi thiết bị mới xuất hiện.
Một job phát hành báo cáo dùng buffer thu thập bản ghi theo số lượng, nhưng luồng dữ liệu thấp vào ban đêm khiến bản báo cáo đợi quá lâu mới xuất được một lô.
Ứng dụng tiếp nhận telemetry dùng window tách luồng theo thời gian, nhưng các cửa sổ con không được tiêu thụ đầy đủ làm số liệu tổng hợp thiếu các khoảng dữ liệu.
Một hệ thống phân loại sự kiện theo mã khách hàng bằng groupBy, nhưng các nhóm ít hoạt động không có consumer tiếp nhận khiến pipeline ngày càng khó giải phóng bộ nhớ.
Ứng dụng hiển thị giá mới nhất sử dụng phép lấy phần tử cuối từ Flux không kết thúc, khiến giá không bao giờ xuất hiện dù giá đã liên tục được phát.
Một dịch vụ lấy phần tử đầu tiên từ Flux cập nhật hồ sơ rồi dừng, khiến các thay đổi quyền xảy ra ngay sau đó không được hiển thị trên dashboard.
Dịch vụ báo cáo dùng reduce cộng tổng trên một luồng sự kiện chạy liên tục, khiến tổng số dự kiến chỉ xuất hiện khi hệ thống ngắt nguồn thay vì lúc người dùng mở trang.
Một ứng dụng gọi zip để ghép thông tin đơn hàng với Mono gửi email chỉ có tín hiệu hoàn tất, khiến bước tạo nội dung phản hồi không được thực hiện.
Trang kiểm kê dùng defaultIfEmpty trả một đối tượng giả khi không có sản phẩm, khiến bản ghi giả bị ghi nhầm thành dữ liệu thực ở bộ phận bán hàng.
Một nguồn sự kiện được share cho nhiều màn hình, nhưng mỗi màn hình đăng ký ở thời điểm khác nhau nên màn hình mở sau bỏ lỡ thông báo đã phát trước đó.
Hệ thống phát thông báo từ nguồn lạnh rồi chia sẻ cho nhiều subscriber, nhưng khi tất cả người xem rời trang việc đọc nguồn dừng và kết nối mới phải khởi tạo lại dữ liệu.
Một dịch vụ lưu kết quả Mono tra cứu tỷ giá bằng cache không có hạn sử dụng, khiến người dùng truy vấn lại nhiều giờ sau vẫn nhận tỷ giá cũ.
Một Mono gọi API ngoài được cache cả kết quả lỗi, khiến các lần đăng ký sau tiếp tục nhận lỗi cũ dù nhà cung cấp đã hoạt động lại.
Nền tảng phát sự kiện thể thao giữ lại lịch sử cho subscriber đến muộn, nhưng thông báo cũ được phát lại như cập nhật mới khiến giao diện hiểu nhầm trận đấu quay về hiệp trước.
Một ứng dụng xem trạng thái đơn mở mới Flux hot sau khi thanh toán hoàn tất, nhưng subscription vừa tạo không nhận được sự kiện xác nhận đã phát trước đó.
Dịch vụ theo dõi học viên tạo nguồn Flux lạnh cho mỗi người dùng thay vì chia sẻ kết nối upstream, khiến số kết nối đến hệ thống học tập tăng theo số tab.
Một bộ đo nhiệt độ sản xuất dữ liệu nhanh hơn tốc độ dashboard đọc, khiến hàng đợi của subscriber tăng dần trong khi độ trễ thông báo đã vượt nhu cầu nghiệp vụ.
Client Reactor đăng ký với yêu cầu ban đầu chỉ một phần tử rồi không cấp thêm demand, khiến server tiếp tục hoạt động nhưng subscriber không thấy các thông báo tiếp theo.
Một Flux tùy chỉnh phát liên tục mà bỏ qua số phần tử downstream yêu cầu, khiến consumer giới hạn demand vẫn bị dồn dữ liệu vào bộ nhớ.
Nhóm tích hợp dùng Flux.create chuyển callback từ thư viện cũ, nhưng callback nhận hàng nghìn bản tin mỗi giây còn subscriber đọc rất chậm nên bộ đệm phát không kiểm soát được.
Ứng dụng giám sát áp dụng chính sách bỏ bớt dữ liệu khi quá tải, khiến những cảnh báo có ý nghĩa nghiệp vụ quan trọng bị mất cùng với mẫu đo thường xuyên.
Dashboard chỉ cần trạng thái thiết bị mới nhất nhưng vẫn lưu toàn bộ cập nhật đến muộn, khiến việc xử lý thông báo cũ làm màn hình chậm dần sau nhiều giờ.
Hệ thống giao nhận dùng bộ đệm hữu hạn để bảo vệ subscriber, nhưng khi xuất hiện đợt cao điểm luồng chuyển sang lỗi tràn bộ đệm và tác vụ bị dừng giữa chừng.
Một producer sự kiện nội bộ phát theo tốc độ tối đa bất kể nhu cầu, nhưng consumer dùng giới hạn xử lý tuần tự nên backlog vẫn tăng ngay cả khi CPU còn dư.
Nhóm phân tích dùng limitRate để điều chỉnh số phần tử yêu cầu từ upstream, nhưng ứng dụng nhầm lượng request với số phần tử có thể xử lý đồng thời trong phần nghiệp vụ.
Một pipeline dùng flatMap gọi nhiều API ngoài cùng lúc, khiến số yêu cầu đang xử lý vượt hạn mức mà nhà cung cấp đặt ra dù tốc độ dữ liệu đầu vào ổn định.
Một ứng dụng dùng parallel để tính điểm cho nhiều học viên, nhưng kết quả được gom lại không theo thứ tự và số thứ tự ghi lên bảng xếp hạng bị đảo.
Hệ thống phát bản ghi từ nguồn nhanh vào một subscriber rất chậm, nhưng nhóm vận hành chỉ đo tốc độ producer nên không phát hiện độ trễ tích lũy ở phía nhận.
Một bộ điều phối thông báo xử lý tín hiệu lỗi upstream như dữ liệu thông thường, khiến subscriber nhận bản tin thành công giả dù nguồn đã phát onError và kết thúc.
Ứng dụng dự phòng lỗi dùng onErrorReturn trả danh sách trống cho mọi lỗi, khiến giao diện hiểu sai sự cố mạng thành không có đơn hàng.
Dịch vụ lấy hồ sơ lỗi do hết hạn token nhưng nhánh onErrorResume tự chuyển sang dữ liệu cache cũ, khiến thông tin quyền truy cập không phản ánh chính sách hiện tại.
Một nhóm gắn doOnError để ghi log rồi kỳ vọng luồng tiếp tục phát các phần tử còn lại, nhưng subscriber vẫn nhận tín hiệu lỗi kết thúc pipeline.
Pipeline xử lý bản ghi sai định dạng dùng onErrorContinue, nhưng một số operator không có hành vi tiếp tục như nhóm dự kiến khiến phần tử lỗi ảnh hưởng cả luồng.
Một API điều phối sử dụng onErrorComplete cho tất cả lỗi của bước thanh toán, khiến người dùng nhận trạng thái hoàn tất dù không có xác nhận tiền đã thu.
Job nhập dữ liệu dùng retry không giới hạn khi database mất kết nối lâu, khiến tác vụ treo và tạo lưu lượng kết nối lặp lại trong suốt sự cố.
Một pipeline dùng retryWhen sau thao tác ghi hóa đơn chưa idempotent, khiến lỗi phản hồi tạm thời dẫn đến hóa đơn được tạo nhiều lần.
Nhiều luồng Reactor cùng retry theo khoảng chờ giống nhau sau khi dịch vụ chung phục hồi, khiến đợt lưu lượng dồn vào đối tác lớn hơn trước khi lỗi.
Dịch vụ gọi API ngoài đặt timeout cho phép lấy thông tin nhanh, nhưng một số yêu cầu bị hủy trong khi server ngoài vẫn tiếp tục thực hiện tác vụ tốn kém.
Ứng dụng xử lý bộ dữ liệu lớn chỉ muốn cảnh báo khi khoảng cách giữa hai bản ghi quá lâu, nhưng nhóm đặt timeout trên Mono gom toàn bộ Flux khiến tác vụ bị hủy sau một thời gian cố định.
Một hệ thống import sử dụng onErrorMap để đổi ngoại lệ kỹ thuật thành lỗi nghiệp vụ, nhưng mất thông tin nguyên nhân gốc khiến điều tra sự cố khó xác định máy chủ lỗi.
Job thu thập sự kiện muốn nhận tất cả kết quả đã xử lý kể cả khi một nguồn lỗi, nhưng tổ hợp pipeline kết thúc ngay khi gặp lỗi đầu tiên và hủy các nguồn khác.
Dịch vụ phân tích ghi log lỗi tại nhiều tầng operator, khiến cùng một lỗi phát sinh một lần được ghi thành hàng chục sự cố trong dashboard.
Một luồng kiểm tra hóa đơn chỉ đặt checkpoint ở cuối pipeline dài, khiến thông tin đánh dấu lỗi không đủ phân biệt nhiều bước xử lý tương tự khi điều tra stack trace.
Nền tảng thông báo có nhánh fallback trả một đối tượng rỗng khi hệ thống chính lỗi, khiến cơ chế giám sát khó phân biệt fallback được kích hoạt với kết quả nghiệp vụ bình thường.
Một pipeline chuyển đổi bản ghi gặp lỗi sau khi đã phát nhiều giá trị, nhưng ứng dụng gọi lại toàn bộ nguồn và tạo ra các thông báo trùng lặp ở các bước trước.
Ứng dụng Java thực hiện lời gọi JDBC chặn luồng ngay trong pipeline trên thread xử lý sự kiện, khiến nhiều yêu cầu reactive khác cùng thread bị chậm.
Dịch vụ thông báo dùng một scheduler dành cho tác vụ tính toán để chạy truy vấn file chậm, khiến các phép xử lý CPU khác bị giữ lại trong hàng đợi.
Một tác vụ được chuyển sang boundedElastic nhưng có số lượng lời gọi chặn tăng đột ngột, khiến hàng đợi tác vụ của scheduler vượt khả năng phục vụ.
Nhóm phát triển thêm nhiều subscribeOn trong cùng một nhánh và mong mỗi operator ở giữa đổi scheduler riêng, nhưng cách thực thi luồng nguồn không phân bố thread như dự kiến.
Pipeline xử lý đơn hàng sử dụng publishOn giữa hai bước, khiến các operator phía sau chạy trên thread khác và mã dùng ThreadLocal không tìm thấy thông tin request.
Một ứng dụng ghi metric theo tên thread thay vì mã giao dịch, khiến các phép xử lý của cùng một Mono chạy qua nhiều scheduler bị đếm thành nhiều giao dịch độc lập.
Dịch vụ chạy các tác vụ CPU nặng trên scheduler single dùng chung, khiến một phép tính dài làm chậm toàn bộ chuỗi xử lý của các khách hàng khác.
Một job gửi thông báo thử nghiệm tạo scheduler riêng cho từng subscription mà không giải phóng chúng, khiến số lượng thread của JVM tăng theo số request.
Hệ thống tiếp nhận sự kiện dùng parallel trên máy chủ có ít lõi nhưng vẫn thực hiện lời gọi chặn bên trong mỗi rail, khiến throughput giảm dù số tác vụ hoạt động nhiều hơn.
Một luồng xử lý đổi scheduler nhiều lần trong cùng pipeline, khiến chi phí chuyển context tăng cao trong khi thời gian tính toán của từng phần tử rất nhỏ.
Một dịch vụ dùng block để lấy kết quả Mono ngay trên scheduler được đánh dấu non-blocking, khiến lời gọi bị từ chối dù Mono có thể hoàn tất và request không trả được kết quả.
Trang thương mại điện tử subscribe thủ công trong phương thức xử lý rồi trả về trước khi nhánh ghi dữ liệu kết thúc, khiến caller nhận thành công dù thao tác sau đó thất bại.
Nền tảng học tập dùng block trong vòng lặp xử lý từng học viên, khiến các yêu cầu truy vấn vốn độc lập bị thực hiện nối tiếp và thời gian hoàn tất tăng mạnh.
Một luồng ghi dữ liệu được dispose khi người dùng rời trang, nhưng thao tác ở hệ thống ngoài đã bắt đầu trước đó vẫn có thể hoàn thành và cập nhật trạng thái.
Hệ thống dùng take để giới hạn số phần tử nhận từ nguồn vô hạn, nhưng nhóm vận hành kỳ vọng nguồn tiếp tục xử lý những phần tử sau khi downstream đã hủy.
Một tác vụ streaming thực hiện doOnComplete để giải phóng tài nguyên, nhưng khi client hủy subscription giữa chừng callback hoàn tất không chạy và kết nối vẫn được giữ.
Ứng dụng đăng ký callback doOnCancel để theo dõi hủy luồng, nhưng một số pipeline kết thúc lỗi nên không có log cleanup dù tài nguyên vẫn cần được thu hồi.
Một job tải file dùng using để mở InputStream theo subscription, nhưng người dùng hủy tác vụ khi mới đọc một phần dữ liệu và nhóm chưa xác minh tài nguyên đã được đóng.
Dịch vụ ghi tệp bất đồng bộ dùng usingWhen để điều phối mở và đóng tài nguyên, nhưng bước đóng gặp lỗi khiến trạng thái hoàn tất của giao dịch không rõ ràng.
Hệ thống streaming trả kết quả trước khi callback giải phóng kết nối bất đồng bộ hoàn tất, khiến pool kết nối tạm thời bị cạn khi người dùng gửi yêu cầu liên tiếp.
Một nhóm tạo pipeline có bước dọn dẹp chỉ được kích hoạt khi có phần tử dữ liệu, khiến nguồn hoàn tất rỗng không đóng được tài nguyên được mở lúc đăng ký.
Ứng dụng đổi dữ liệu từ service bên ngoài sang Flux nhưng không chuyển tín hiệu hủy về nguồn, khiến các phép đọc I/O vẫn tiếp tục sau khi người dùng đóng tab.
Một hệ thống đọc dữ liệu thời gian thực dùng Flux hot được tạo từ listener cũ, nhưng mỗi lần kết thúc subscription listener không được gỡ và callback cũ vẫn giữ tham chiếu bộ nhớ.
Ứng dụng nhận sự kiện từ nhiều thread rồi cùng emit vào một Sink, nhưng dưới tải cao một số lần phát nhận kết quả từ chối vì phát đồng thời không được tuần tự hóa.
Một dịch vụ dùng unicast Sink để phát tác vụ nội bộ, nhưng đội tích hợp thêm subscriber thứ hai và subscription mới không được chấp nhận như mong đợi.
Nền tảng cảnh báo dùng multicast Sink loại directBestEffort khi chưa có người nghe, khiến sự kiện phát trước lúc dashboard subscribe không có lịch sử để phát lại.
Một hệ thống phát sự kiện tới nhiều người dùng dùng multicast Sink loại directAllOrNothing, nhưng chỉ một subscriber hết demand đã khiến lần emit mới bị từ chối dù những người khác còn sẵn sàng.
Ứng dụng giữ tất cả sự kiện trong replay Sink cho khách hàng đăng nhập muộn, khiến bộ nhớ tăng không giới hạn sau vài tuần vận hành.
Hệ thống thông báo dùng replay Sink lưu các bản tin trước đó, nhưng nhân viên đổi tài khoản trong cùng ứng dụng rồi nhận lại sự kiện thuộc phiên đăng nhập cũ.
Một producer gọi emitNext sau khi Sink đã được complete, khiến ứng dụng tưởng thông báo vẫn được gửi dù downstream không thể nhận thêm sự kiện.
Dịch vụ dự kiến chỉ có một nguồn phát vào Sink, nhưng khi ứng dụng mở rộng nhiều instance các lần phát sự kiện không được phối hợp nên người dùng thấy bản tin thiếu hoặc trùng.
Một hệ thống hiển thị kết quả thi dùng Sink multicast với bộ đệm chờ subscriber chậm, khiến lượng dữ liệu giữ trong bộ đệm và độ trễ cập nhật tăng khi một màn hình không theo kịp.
Nhóm triển khai sử dụng Sink có bộ đệm hữu hạn để chứa sự kiện chờ, nhưng khi không có người tiêu thụ đủ nhanh kết quả emit cho biết bộ đệm đã quá tải.
Ứng dụng cần lưu trace ID xuyên chuỗi Mono sau khi publishOn đổi thread, nhưng chỉ đặt trace ID trong ThreadLocal nên log của bước tiếp theo không có cùng mã.
Một dịch vụ đa tenant dùng Context để mang tenant ID của từng subscription, nhưng một thư viện nội bộ đọc ThreadLocal thay vì ngữ cảnh reactive và đôi khi truy vấn sai tenant.
Đội phát triển đặt contextWrite ở cuối một nhánh pipeline rồi mong các thao tác nằm ngoài nhánh cũng nhận cùng metadata, khiến một phần log bị mất thông tin tương quan.
Một nguồn Flux được share giữa nhiều người dùng có Context khác nhau, nhưng bước gọi chung giả định chỉ có một Context và gắn nhầm định danh người dùng cho sự kiện.
Hệ thống kiểm toán dùng Context để mang mã người khởi tạo thao tác, nhưng một callback được thực thi ngoài chuỗi subscription không tìm được mã đó trong log.
Ứng dụng cấp quyền truy cập dựa trên metadata gắn với subscription, nhưng thành phần chuyển callback sang publisher không chuyển tiếp đúng Context nên truy vấn không còn thông tin phân quyền.
Một ứng dụng reactive chạy qua nhiều tầng operator và scheduler, nhưng các công cụ ghi log truyền thống không tự biết Context nên trace ID chỉ xuất hiện ở một số bước.
Một pipeline lấy dữ liệu theo tenant nhưng cùng cache kết quả giữa nhiều subscription mà không tách theo tenant, khiến dữ liệu của khách hàng này xuất hiện trong phiên khách hàng khác.
Nhóm kiểm thử dùng StepVerifier mong đợi ba bản tin theo thứ tự, nhưng flatMap gọi nhiều dịch vụ có thời gian phản hồi khác nhau khiến test lúc đạt lúc lỗi.
Một bài test dùng Thread.sleep để chờ Flux có delay phát sự kiện, khiến bộ kiểm thử chạy lâu và thất bại ngẫu nhiên trên môi trường CI tải cao.
Đội phát triển dùng StepVerifier với virtual time cho luồng delay, nhưng publisher đã được tạo trước thời điểm kích hoạt đồng hồ ảo nên phép kiểm tra vẫn phải đợi thời gian thật.
Một test với StepVerifier chỉ xác minh onComplete sau một Mono rỗng, nhưng bỏ sót việc một nhánh có thể bị kết thúc bằng onError trong điều kiện đầu vào đặc biệt.
Nhóm QA dùng TestPublisher phát hai tín hiệu kết thúc liên tiếp để thử lỗi giao thức, nhưng pipeline ứng dụng không có cách thể hiện sự khác biệt giữa các hành vi nguồn hợp lệ và sai chuẩn.
Một bài kiểm thử áp dụng StepVerifier cho Flux vô hạn mà không có điều kiện dừng, khiến bộ test treo lâu và không bao giờ đưa ra kết quả kiểm tra.
Ứng dụng có nhánh fallback khi API ngoài lỗi, nhưng test chỉ phát dữ liệu thành công nên không phát hiện nhánh lỗi làm nuốt mất thông tin nghiệp vụ.
Một test xác minh số phần tử sau buffer nhưng không kiểm tra nội dung từng lô, khiến bản ghi bị gom sai nhóm vẫn vượt qua bộ kiểm thử.
Đội triển khai dùng StepVerifier kiểm tra backpressure của Flux tùy chỉnh, nhưng test luôn yêu cầu không giới hạn nên lỗi bỏ qua demand không xuất hiện.
Một bài test nguồn hot subscribe sau khi sự kiện đầu đã phát, nhưng bộ kiểm thử vẫn mong nhận cả sự kiện cũ và liên tục báo sai trên máy CI.
Ứng dụng đóng subscription giữa lúc đang ghi tệp bất đồng bộ, nhưng các bài kiểm thử chỉ kiểm tra khi hoàn tất bình thường nên lỗi rò rỉ tài nguyên không được phát hiện.
Dịch vụ xử lý lỗi dùng retryWhen sau kết nối tạm thời, nhưng bài kiểm thử dựa vào thời gian thật làm chạy chậm và không xác minh chính xác số lần thử trước khi báo lỗi.
Hệ thống dùng Sinks để phát trạng thái theo thời gian thực, nhưng bộ test chỉ dùng một thread phát nên không phát hiện lỗi do hai producer emit đồng thời.
Một dashboard nhận dữ liệu từ Flux được cache, nhưng bộ kiểm thử chỉ chạy một subscription nên không phát hiện subscriber thứ hai nhận lại dữ liệu quá cũ.
Nền tảng xử lý hồ sơ gắn doFinally để ghi metric kết thúc, nhưng bài test chỉ xác minh thành công và không đo trường hợp bị hủy sau khi người dùng ngắt kết nối.
Một dịch vụ reactive bị tăng bộ nhớ sau nhiều giờ chạy, nhưng telemetry chỉ ghi số phần tử đã xử lý mà không đo lượng phần tử chờ, số subscription và queue scheduler đang tồn.
