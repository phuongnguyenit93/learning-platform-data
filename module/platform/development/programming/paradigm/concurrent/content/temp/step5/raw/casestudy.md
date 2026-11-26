Một dịch vụ đặt vé nhận hai yêu cầu giữ chỗ gần như đồng thời cho ghế cuối cùng, trong khi hệ thống chỉ có một lõi CPU; hãy phân tích khả năng xen kẽ tác vụ và rủi ro bán trùng ghế.
Một công cụ nhập dữ liệu có bước tải tệp qua mạng và bước phân tích nội dung nặng CPU, hai bước hiện được thực hiện xen kẽ; hãy đánh giá các điểm nghẽn khi tăng số tác vụ đồng thời.
Một hệ thống báo cáo chạy mười tác vụ độc lập nhưng CPU chỉ có hai lõi vật lý, người dùng kỳ vọng tốc độ nhanh gấp mười; hãy phân biệt khả năng tiến triển đồng thời và xử lý song song thực sự.
Một API tổng hợp thông tin khách hàng gọi ba dịch vụ bên ngoài có độ trễ không ổn định, yêu cầu phản hồi dưới một giây; hãy phân tích thời gian chờ và cách các tác vụ ảnh hưởng đến nhau.
Một ứng dụng xử lý ảnh vừa đọc tệp, vừa giải nén và vừa ghi kết quả, nhưng thiết bị lưu trữ đã bão hòa; hãy đánh giá hiệu quả thực tế của việc tăng mức đồng thời.
Một tác vụ đồng bộ hóa phải bảo đảm hai hành động xảy ra theo đúng thứ tự, trong khi các tác vụ không liên quan có thể tiến triển tự do; hãy xác định quan hệ thứ tự cần được bảo vệ.
Một chương trình có một luồng giao diện và nhiều tác vụ tính toán nền, thỉnh thoảng giao diện ngừng phản hồi dù CPU còn rảnh; hãy phân tích sự khác biệt giữa chờ đồng bộ và chạy song song.
Một dịch vụ chuyển đổi video tăng gấp đôi số worker nhưng throughput không đổi khi ghi vào cùng một ổ đĩa; hãy xác định nguồn tranh chấp cần quan sát trước khi mở rộng tiếp.
Một hệ thống thanh toán phát hành hóa đơn sau khi ghi giao dịch thành công, nhưng quá trình gửi email có thể chậm hoặc thất bại; hãy phân tích ranh giới giữa tác vụ phụ thuộc và tác vụ độc lập.
Một nhóm thử nghiệm chạy các công việc bất đồng bộ theo thứ tự hoàn thành thay vì thứ tự gửi, khiến bản ghi trạng thái bị xáo trộn; hãy đánh giá yêu cầu về ordering của nghiệp vụ.
Một chương trình lập lịch hàng nghìn tác vụ nhỏ trên nhiều lõi nhưng chi phí phân phối lớn hơn thời gian tính toán; hãy phân tích khi nào concurrency tạo thêm overhead.
Một server có hàng trăm kết nối chủ yếu chờ dữ liệu đầu vào, nhưng một số ít kết nối tiêu thụ CPU dài; hãy mô tả tác động của phân phối tác vụ đến độ trễ yêu cầu khác.
Một ứng dụng triển khai trên máy ảo bị giới hạn hai CPU dù host có nhiều lõi, và số luồng được cấu hình theo host; hãy phân tích kỳ vọng về parallelism và mức tranh chấp.
Một hệ thống xử lý các thao tác trên cùng tài khoản theo thứ tự, nhưng có thể xử lý nhiều tài khoản độc lập đồng thời; hãy xác định bất biến về thứ tự cần kiểm tra.
Một ứng dụng truyền luồng sự kiện sang bộ hiển thị thời gian thực, khi nguồn phát nhanh hơn màn hình cập nhật; hãy phân tích sự khác biệt giữa tốc độ tạo tác vụ và khả năng hoàn thành.
Một nhóm thấy hai thread không chạy cùng một thời điểm trong log rồi kết luận không có race; hãy đánh giá vai trò của interleaving và độ tin cậy của dữ liệu quan sát.
Một service tạo một tác vụ riêng cho mỗi bản ghi trong lô hàng triệu phần tử và bị cạn bộ nhớ dù CPU chưa bão hòa; hãy đánh giá chi phí quản lý tác vụ.
Một workflow gồm truy vấn kho, xác nhận giá và đặt hàng; kết quả của mỗi bước phụ thuộc bước trước nhưng vài nhánh kiểm tra có thể độc lập; hãy phân tích đồ thị phụ thuộc.
Một chương trình dùng bốn worker cho nhiều công việc ngắn, nhưng một worker bị giữ bởi tác vụ I/O vô hạn; hãy phân tích hiện tượng giảm khả năng tiến triển của các tác vụ còn lại.
Một quy trình nhập dữ liệu vừa phải hoàn thành sớm vừa phải trả về kết quả theo thứ tự dòng gốc, dù từng dòng xử lý lâu khác nhau; hãy phân tích các ràng buộc concurrency và ordering.
Một giỏ hàng lưu tổng tiền trong biến chia sẻ và hai request cùng cập nhật số lượng sản phẩm, thỉnh thoảng tổng tiền nhỏ hơn dự kiến; hãy xác định dạng mất cập nhật có thể xuất hiện.
Một bộ đếm lượt xem tăng từ nhiều luồng và kết quả thấp hơn tổng số request hoàn tất, dù phép đọc cuối không ném lỗi; hãy phân tích tính nguyên tử của thao tác cập nhật.
Một thread cập nhật cờ dừng worker nhưng worker khác chạy vòng lặp lâu mà không thấy cờ thay đổi; hãy phân tích yêu cầu về visibility giữa các luồng.
Một ứng dụng tạo đối tượng cấu hình gồm nhiều trường rồi công bố tham chiếu trước khi khởi tạo xong, khiến worker đọc được trường mặc định; hãy phân tích rủi ro unsafe publication.
Một cache chia sẻ bản đồ mutable và một tác vụ cập nhật trong khi tác vụ khác đang lặp qua entry, thỉnh thoảng xuất hiện trạng thái không nhất quán; hãy đánh giá hợp đồng truy cập.
Một đối tượng phiên người dùng có hai trường liên quan được cập nhật riêng rẽ, reader đôi lúc thấy trạng thái mới của trường này và cũ của trường kia; hãy phân tích yêu cầu atomicity nhiều trường.
Một chương trình dùng biến volatile làm bộ đếm tăng đồng thời và vẫn mất cập nhật, dù mọi thread nhìn thấy giá trị mới; hãy phân biệt visibility với phép read-modify-write.
Một dịch vụ thay tham chiếu cấu hình bất biến khi reload nhưng vẫn cho phép chỉnh sửa các collection lồng bên trong, gây kết quả không dự đoán được; hãy phân tích mức bất biến thực tế.
Một bảng trạng thái được khởi tạo trong static initializer rồi nhiều thread chỉ đọc, nhưng một thread khác thay đổi phần tử bên trong sau khi phát hành; hãy đánh giá giới hạn an toàn của việc khởi tạo.
Một nhóm thêm logging và lỗi race biến mất khi chạy thử, trong khi bản production vẫn gặp; hãy phân tích tác động của timing đến khả năng tái hiện lỗi.
Một ứng dụng ghi số dư và lịch sử giao dịch vào hai cấu trúc shared memory khác nhau, request đồng thời quan sát được số dư mà không thấy bản ghi tương ứng; hãy xác định bất biến cần kiểm chứng.
Một luồng xử lý thông báo hoàn tất bằng biến Boolean thông thường và luồng khác kiểm tra liên tục, kết quả phụ thuộc tối ưu hóa của JIT; hãy đặt vấn đề về happens-before.
Một thư viện có getter trả về trực tiếp danh sách mutable nội bộ cho nhiều request song song, và một request xóa phần tử trong lúc request khác tính tổng; hãy phân tích ranh giới sở hữu dữ liệu.
Một chức năng thay danh sách cấu hình bằng thao tác gán tham chiếu nguyên tử, nhưng các đối tượng con vẫn bị sửa sau đó; hãy đánh giá liệu snapshot của reader có nhất quán không.
Một dịch vụ có trường final trỏ đến đối tượng mutable và đội ngũ cho rằng toàn bộ đồ thị đối tượng được bảo vệ khỏi race; hãy phân tích giả định đó qua các luồng cập nhật.
Một ứng dụng giữ một object cấu hình trong thread-local để tránh chia sẻ, nhưng tác vụ tiếp theo được chạy trên thread khác và không thấy giá trị; hãy phân tích ngữ cảnh thực thi.
Một hệ thống kiểm thử gọi cùng lúc hai thao tác kiểm tra rồi cập nhật quyền sở hữu, cả hai đều đọc thấy tài nguyên chưa thuộc ai; hãy phân tích điều kiện cạnh tranh kiểu check-then-act.
Một nhóm dùng copy-on-write cho bảng định tuyến đọc nhiều nhưng cập nhật liên tục mỗi giây, và bộ nhớ tăng đột biến; hãy đánh giá đánh đổi giữa nhất quán snapshot và chi phí sao chép.
Một worker ghi nhiều trường rồi đặt cờ ready cho reader khác, nhưng không có hợp đồng đồng bộ rõ ràng; hãy phân tích mối quan hệ cần có giữa các phép ghi và phép đọc.
Một hệ thống hiển thị trạng thái job dựa trên nhiều bản sao cache tại các thread khác nhau và thi thoảng báo đã hoàn tất khi log vẫn còn ghi; hãy phân tích điểm quan sát nhất quán.
Hai tác vụ chuyển tiền lần lượt khóa tài khoản nguồn rồi tài khoản đích theo các hướng ngược nhau, và cả hai đều đứng chờ; hãy phân tích điều kiện hình thành deadlock.
Một worker giữ khóa kho hàng trong lúc gọi dịch vụ giao vận chậm hàng chục giây, khiến các đơn khác bị tắc; hãy đánh giá phạm vi critical section và tác động tới throughput.
Một hàm đọc cấu hình dùng khóa đọc nhưng có lúc nâng sang khóa ghi khi phát hiện thiếu dữ liệu, nhiều request đứng chờ nhau; hãy phân tích rủi ro nâng cấp khóa.
Một service sử dụng lock có timeout để cập nhật trạng thái, đôi khi hết thời gian chờ ngay trong cao điểm; hãy đánh giá ngữ nghĩa thất bại và dữ liệu chưa được cập nhật.
Một ứng dụng bắt exception trong đoạn giữ khóa nhưng quên giải phóng ở một nhánh lỗi, khiến request khác treo vĩnh viễn; hãy xác định cách quan sát vòng đời khóa.
Một hàng đợi có producer và consumer dùng điều kiện chờ, đôi khi consumer thức dậy khi hàng đợi vẫn rỗng; hãy phân tích điều kiện phải được tái kiểm tra.
Một tác vụ chờ điều kiện trên monitor nhưng producer chỉ phát tín hiệu trước khi consumer bắt đầu chờ, dẫn đến treo ngẫu nhiên; hãy phân tích nguy cơ mất tín hiệu.
Một nhóm áp dụng một khóa toàn cục cho cả việc tra cứu và cập nhật bảng người dùng, trong giờ cao điểm phần lớn request chỉ đọc vẫn bị chặn; hãy đánh giá mức độ tranh chấp.
Một hệ thống có hai nguồn tài nguyên cần khóa đồng thời trong nhiều luồng, thay đổi thứ tự lấy khóa theo từng code path; hãy phân tích khả năng chờ vòng và phương án đánh giá thứ tự.
Một worker ưu tiên cao bị kẹt vì worker ưu tiên thấp giữ khóa quá lâu, gây trễ thời hạn xử lý; hãy đánh giá vấn đề đảo ưu tiên trong môi trường lập lịch.
Một lock không bảo đảm fairness khiến một tác vụ thường xuyên bị vượt qua dù nhiều request khác hoàn tất; hãy phân tích starvation và tiêu chí công bằng.
Một chương trình dùng synchronized quanh thao tác đọc file lớn, người đọc khác phải chờ cả lúc I/O bị trì hoãn; hãy phân tích ảnh hưởng khi đặt I/O bên trong critical section.
Một dịch vụ sử dụng hai điều kiện chờ trên cùng một khóa và phát nhầm tín hiệu cho nhóm consumer không liên quan, làm throughput suy giảm; hãy phân tích cách đo hành vi wake-up.
Một nhóm thêm nhiều khóa nhỏ để tăng độ song song, nhưng dữ liệu liên quan nằm trải qua nhiều khóa và trạng thái trung gian bị lộ; hãy đánh giá tính nhất quán liên vùng.
Một chuỗi worker sử dụng semaphore giới hạn số kết nối tới cơ sở dữ liệu, nhưng khi một task bị hủy permit không được hoàn trả; hãy phân tích dấu hiệu rò rỉ permit.
Một hệ thống barrier đợi đủ tám tác vụ phân tích cùng hoàn thành, nhưng một tác vụ thất bại trước khi đến barrier và các tác vụ khác đứng chờ; hãy phân tích đường phục hồi.
Một workflow xử lý đơn dùng latch chờ các bước khởi động, nhưng được tái sử dụng cho đợt tiếp theo mà trạng thái không được đặt lại; hãy đánh giá vòng đời của primitive đồng bộ.
Một nhóm đổi từ khóa độc quyền sang khóa đọc-ghi, sau đó một luồng ghi liên tục bị trì hoãn khi lượng reader rất lớn; hãy phân tích trade-off throughput và fairness.
Một worker cầm khóa rồi chờ Future của tác vụ khác, trong khi tác vụ khác cần chính khóa đó để hoàn thành; hãy phân tích deadlock do chờ kết quả bất đồng bộ.
Một dịch vụ thỉnh thoảng bị nghẽn và thread dump xuất hiện hàng trăm luồng ở trạng thái BLOCKED trên cùng monitor; hãy xác định thông tin cần thu thập để điều tra nguồn khóa.
Một bộ đếm lượt truy cập tăng rất nhanh trên nhiều lõi bằng một atomic variable nhưng bắt đầu có contention; hãy đánh giá khả năng mở rộng và độ chính xác cần đạt.
Một kho hàng dùng CAS để giảm tồn kho, hai tác vụ đọc cùng giá trị cũ rồi một tác vụ cập nhật thất bại; hãy phân tích cách xác định trạng thái giao dịch của tác vụ thất bại.
Một danh sách liên kết lock-free dùng CAS trên đầu danh sách và gặp trường hợp con trỏ từ A sang B rồi quay về A; hãy phân tích nguy cơ ABA khi kiểm chứng cập nhật.
Một hệ thống kiểm soát hạn mức bằng hai biến atomic độc lập cho số giao dịch và tổng tiền, đôi lúc vượt hạn mức kết hợp; hãy đánh giá bất biến cần được giữ đồng thời.
Một ứng dụng dùng atomic reference chứa đối tượng cấu hình nhưng sửa các field mutable của đối tượng tại chỗ, khiến nhiều reader thấy dữ liệu không nhất quán; hãy phân tích giới hạn atomicity của tham chiếu.
Một worker thực hiện vòng CAS retry khi tải cao, tỷ lệ thử lại tăng mạnh nhưng vẫn không tiến triển; hãy đánh giá liveness và chi phí spin trong giờ cao điểm.
Một counter phục vụ metrics được đọc gần thời gian thực và nhóm muốn đổi sang bộ đếm phân tán giảm contention, nhưng có yêu cầu snapshot chính xác từng lần; hãy phân tích đánh đổi.
Một hệ thống giữ trạng thái phiên bằng immutable object được thay qua atomic reference, nhưng hai yêu cầu cập nhật hai trường khác nhau trên cùng phiên; hãy phân tích khả năng mất cập nhật.
Một bộ lập lịch sử dụng CAS trên trạng thái tác vụ từ queued sang running, trong khi tác vụ hủy muốn chuyển sang canceled; hãy đánh giá các chuyển trạng thái cạnh tranh.
Một cache dùng compute-if-absent dưới tải lớn, nhiều request cùng yêu cầu key mới và chức năng dựng giá trị có side effect; hãy phân tích ràng buộc về số lần thực thi.
Một dịch vụ tính tổng doanh thu trên bộ đếm atomic và đồng thời reset về không mỗi giờ, đôi lúc mất một phần số liệu; hãy phân tích tính tuyến tính của các thao tác.
Một thuật toán lock-free có nhiều reader nhưng một writer liên tục thất bại CAS, dù hệ thống vẫn hoàn thành các thao tác khác; hãy phân biệt lock-freedom với starvation của cá thể.
Một nhóm thay khóa bằng atomic Boolean kiểm tra busy rồi cập nhật nhiều bản ghi mutable, và gặp trạng thái hiển thị dở dang; hãy phân tích ranh giới của biến atomic.
Một đối tượng trạng thái yêu cầu hai field phải thay đổi cùng thời điểm, nhưng nhóm chỉ dùng hai compare-and-set riêng lẻ; hãy xác định kịch bản phá vỡ bất biến.
Một dịch vụ đặt lệnh tài chính sử dụng idempotency token trong cấu trúc concurrent, hai tác vụ trùng token vẫn gọi hệ thống thanh toán; hãy đánh giá tính nguyên tử của kiểm tra và đăng ký.
Một worker dùng vòng lặp busy-spin chờ cờ trạng thái atomic trong môi trường CPU quota thấp, khiến tác vụ khác chậm bất thường; hãy phân tích tác động lên scheduler.
Một bảng thống kê nhiều khóa được cập nhật đồng thời, kết quả tổng số khóa từ nhiều atomic counters không trùng snapshot tại một thời điểm; hãy đánh giá yêu cầu nhất quán khi đọc tổng.
Một thư viện concurrent collection cho phép iteration weakly consistent, nhưng bộ phận kế toán muốn báo cáo bất biến theo thời điểm; hãy phân tích sự khác biệt giữa duyệt an toàn và snapshot.
Một chương trình ghi trạng thái mới bằng atomic reference kèm version nhưng version đôi khi bị quay vòng về giá trị cũ sau thời gian dài; hãy phân tích nguy cơ xác nhận sai trạng thái.
Một hệ thống ưu tiên latency thấp áp dụng kỹ thuật không khóa cho cấu trúc phức tạp, song việc thu hồi node an toàn với reader chưa hoàn tất chưa được thiết kế; hãy đánh giá bài toán quản lý vòng đời bộ nhớ.
Một API gửi cùng lúc nhiều lệnh qua ExecutorService nhưng không giới hạn số tác vụ chờ, hàng đợi tăng cho đến khi heap cạn; hãy phân tích mối quan hệ giữa tốc độ nhận việc và năng lực worker.
Một request yêu cầu hai kết quả Future rồi gọi lấy kết quả lần lượt, tác vụ đầu rất chậm khiến kết quả thứ hai đã sẵn sàng nhưng chưa được dùng; hãy đánh giá khả năng chờ không cần thiết.
Một dịch vụ hủy Future khi người dùng đóng trang, nhưng tác vụ I/O vẫn chạy ở nền và tiếp tục chiếm kết nối; hãy phân tích ngữ nghĩa cancellation và giới hạn interrupt.
Một hệ thống tạo thread pool cố định cho cả truy vấn database chờ lâu và tính toán CPU nhanh, phần CPU bị nghẽn dù còn lõi rảnh; hãy đánh giá hiện tượng task starvation.
Một batch có mười nghìn Future được submit nhưng một Future không hoàn thành, bước tổng hợp chờ mãi dù phần lớn kết quả có sẵn; hãy phân tích chính sách timeout và partial result.
Một worker bị interrupt khi đang xử lý dữ liệu nhưng catch exception rồi tiếp tục làm việc mà không báo hủy, khiến shutdown kéo dài; hãy đánh giá tính nhất quán của trạng thái hủy.
Một dịch vụ gọi nhiều CompletableFuture và hoàn thành exceptionally một nhánh, nhánh tổng hợp không chạy như nhóm mong đợi; hãy phân tích lan truyền lỗi trong đồ thị bất đồng bộ.
Một chương trình đăng ký callback trên CompletableFuture nhưng callback chậm lại chạy trên thread hoàn thành tác vụ, ảnh hưởng latency của request khác; hãy phân tích execution context.
Một thao tác thanh toán trả Future cho người gọi, nhưng request kết thúc sớm và Future thất bại mà không ai quan sát; hãy đánh giá trách nhiệm theo dõi kết quả cuối.
Một nhóm dùng executor một luồng cho tác vụ A và A lại submit B vào cùng executor rồi chờ B hoàn tất, khiến chương trình không tiến triển; hãy xác định chu trình phụ thuộc gây tắc.
Một hệ thống đặt timeout chỉ trên bước chờ Future nhưng không dừng tác vụ thật sau timeout, các kết nối bị chiếm lâu sau khi client đã nhận lỗi; hãy phân tích vòng đời tác vụ.
Một dịch vụ khởi động nhiều executor trong từng request nhưng quên đóng, số thread và tài nguyên tiến trình tăng đều theo thời gian; hãy đánh giá kế hoạch quản lý ownership.
Một API gửi tác vụ ghi sổ kế toán rồi trả thành công ngay khi submit, nhưng executor từ chối nhận việc khi quá tải; hãy phân tích thời điểm nào có thể cam kết kết quả nghiệp vụ.
Một bộ thu thập dữ liệu dùng completion order để xử lý kết quả sớm, nhưng báo cáo cần giữ thứ tự của danh sách đầu vào; hãy đánh giá yêu cầu phối hợp kết quả.
Một hệ thống đặt retry cho CompletableFuture sau lỗi tạm thời, nhưng không giới hạn số lần, khiến tải trên downstream tăng đúng lúc nó gặp sự cố; hãy phân tích chính sách phục hồi.
Một ứng dụng dùng một executor cho nhiều tenant, tenant có lô công việc rất lớn khiến tenant khác chờ lâu; hãy phân tích công bằng và cô lập tài nguyên giữa nhóm tác vụ.
Một job nền cần bị hủy khi người dùng cập nhật cấu hình, nhưng cancellation có thể đến ngay sau khi tác vụ phát thông báo hoàn tất; hãy phân tích cuộc đua giữa complete và cancel.
Một workflow có bước tính giá độc lập và bước kiểm tra quyền bắt buộc; khi kiểm tra quyền thất bại, phép tính giá vẫn tiếp tục tốn CPU; hãy đánh giá việc liên kết vòng đời các Future.
Một hệ thống dùng callback nối nhiều tầng và chỉ một nhánh ghi log exception, các lỗi khác bị nuốt rồi báo thành công; hãy phân tích cách quan sát và quy trách nhiệm lỗi.
Một đội vận hành muốn graceful shutdown executor trong thời hạn ngắn khi cập nhật phiên bản, nhưng vài tác vụ ghi file không phản hồi interrupt; hãy phân tích lựa chọn bảo toàn dữ liệu và thời gian chờ.
Một cổng API dùng một platform thread cho mỗi kết nối có thời gian chờ mạng dài, số thread hệ điều hành tăng đột biến; hãy đánh giá khi chuyển sang virtual threads sẽ thay đổi chi phí nào.
Một dịch vụ có hàng chục nghìn virtual threads chủ yếu chờ I/O, nhưng một số tác vụ tính toán thuần CPU mất vài giây; hãy phân tích giới hạn parallelism và tác động lên carrier threads.
Một request được xử lý bằng virtual thread và gọi thư viện native bị blocking, trong lúc thread dump cho thấy carrier bị giữ lâu; hãy đánh giá điểm cần đo về pinning.
Một ứng dụng trên JDK mới vẫn dùng synchronized trong virtual threads và nhóm mặc định thay toàn bộ sang ReentrantLock; hãy phân tích tính phù hợp của quyết định theo phiên bản runtime.
Một dịch vụ dùng ThreadLocal giữ đối tượng phân tích dữ liệu lớn cho từng virtual thread, bộ nhớ tăng dù số carrier rất ít; hãy đánh giá chi phí state theo số tác vụ.
Một hệ thống tạo virtual thread cho mỗi yêu cầu tới database nhưng connection pool chỉ có vài chục slot, nhiều nghìn tác vụ đứng chờ; hãy phân tích giới hạn tài nguyên thực tế.
Một tác vụ trong virtual thread thực hiện khóa monitor rồi gọi thư viện JNI chặn lâu; hãy đánh giá các nguyên nhân có thể giữ carrier ngay cả trên JDK được cải tiến.
Một nhóm triển khai virtual threads lên máy có CPU quota thấp và đặt mục tiêu tăng tốc thuật toán nén CPU-bound gấp mười; hãy kiểm tra kỳ vọng về throughput.
Một service sử dụng virtual threads với hàng nghìn kết nối websocket idle, nhưng thiết bị mạng và file descriptor bị đầy; hãy phân tích vì sao tiết kiệm thread không đồng nghĩa vô hạn I/O.
Một API tạo virtual thread cho mỗi retry của cùng request mà không có deadline tổng, số tác vụ tăng khi downstream gặp lỗi; hãy đánh giá khả năng kiểm soát tải.
Một ứng dụng chuyển các tác vụ sang virtual threads và thấy thread dump có rất nhiều thread ở trạng thái WAITING, nhóm cho rằng đó là deadlock; hãy phân tích cần quan sát gì thêm.
Một hệ thống giữ ngữ cảnh request trong ThreadLocal và spawn tác vụ con trên virtual thread mới, log của con thiếu correlation id; hãy phân tích yêu cầu truyền ngữ cảnh.
Một thư viện dùng thread affinity để giữ trạng thái phiên C native, nhưng ứng dụng chạy qua virtual threads có cơ chế mount/unmount; hãy đánh giá giả định về thread thực thi.
Một service đo latency ở thời điểm virtual thread bắt đầu và kết thúc, nhưng thời gian chờ semaphore chiếm phần lớn; hãy phân tích cách phân rã độ trễ thành chờ và xử lý.
Một đội dùng virtual threads cho từng sự kiện telemetry, trong khi downstream chỉ nhận một nghìn sự kiện mỗi giây; hãy phân tích nguy cơ dồn hàng và thiếu backpressure.
Một tác vụ trong virtual thread bị hủy trong lúc đang chờ I/O, nhưng thư viện không phản hồi gián đoạn theo mong đợi; hãy đánh giá tính bảo đảm của cancellation.
Một hệ thống dùng virtual threads nhưng executor cấp phát kết nối database trong một synchronized section dài, throughput vẫn thấp; hãy phân tích điểm tranh chấp còn tồn tại.
Một ứng dụng dùng virtual threads cho rất nhiều tác vụ ngắn và đo hiệu năng trên máy developer khác quota CPU production, dẫn tới kết luận trái ngược; hãy đánh giá thiết kế benchmark.
Một dịch vụ có hàng trăm nghìn virtual threads đợi một lệnh xác nhận duy nhất từ người dùng, nhưng hệ thống cần shutdown sau ba mươi giây; hãy phân tích quản lý vòng đời tác vụ.
Một tác vụ kiểm thử trên virtual threads phụ thuộc đồng hồ thực và điều kiện sắp lịch, liên tục thất bại ngẫu nhiên khi chạy CI; hãy xác định cách hiểu vấn đề determinism.
Một API cần lấy báo giá từ ba nhà cung cấp trong cùng một request, nhưng một nhà cung cấp treo lâu; hãy phân tích cách quản lý nhóm tác vụ và deadline chung theo structured concurrency.
Một workflow có hai tác vụ con lấy dữ liệu khách hàng và địa chỉ, một tác vụ gặp lỗi trong khi tác vụ kia còn chờ; hãy đánh giá chính sách kết thúc và hủy tác vụ liên quan.
Một request đã trả lỗi cho client nhưng các công việc con vẫn tiếp tục ghi log và gọi dịch vụ bên ngoài, gây rò rỉ tài nguyên; hãy phân tích ranh giới vòng đời cha và con.
Một nhóm chuyển từ các Future tách rời sang một phạm vi tác vụ có cấu trúc, nhưng bộ phận nghiệp vụ muốn giữ kết quả thành công khi một nhánh thất bại; hãy phân tích chính sách kết quả.
Một hệ thống thực hiện hai truy vấn tìm kiếm độc lập và chỉ cần phản hồi hợp lệ đầu tiên, nhưng truy vấn còn lại tiếp tục chạy tốn tài nguyên; hãy đánh giá ngữ nghĩa chọn kết quả và hủy.
Một tác vụ cha cần hoàn tất sau khi tất cả tác vụ con thực sự dừng, nhưng một thư viện con không phản hồi cancellation; hãy đánh giá rủi ro khi đóng phạm vi xử lý.
Một giao dịch nghiệp vụ có một tác vụ con gửi thông báo không thiết yếu, nhưng chính sách chung lại coi mọi lỗi con là lỗi giao dịch; hãy phân tích ranh giới của nhóm tác vụ.
Một service phải đáp ứng deadline toàn request, song mỗi tác vụ con được cấu hình timeout riêng nên tổng thời gian vượt SLA; hãy xác định quan hệ timeout cần kiểm tra.
Một nhóm áp dụng structured concurrency qua API JDK đang có trạng thái phụ thuộc phiên bản, nhưng pipeline build dùng nhiều JDK khác nhau; hãy phân tích khả năng tương thích và phát hành.
Một API tạo tác vụ con trong một scope rồi để tham chiếu kết quả thoát ra ngoài khi scope đã đóng, khiến lỗi xuất hiện muộn; hãy phân tích ownership và lifetime của kết quả.
Một workflow có ba tác vụ con ghi dữ liệu vào cùng một cấu trúc mutable của cha, mặc dù vòng đời đã được quản lý có cấu trúc; hãy đánh giá tính an toàn của trạng thái chia sẻ.
Một hệ thống xử lý file mở nhiều tác vụ con, khi người dùng hủy request thì một tác vụ đang ghi tệp tạm và tác vụ khác đang đóng resource; hãy phân tích tính nhất quán của cleanup.
Một nhóm cần thu hồi dấu vết và exception của từng tác vụ con để điều tra một yêu cầu thất bại, nhưng thông tin lỗi chỉ hiển thị ở tác vụ cha; hãy đánh giá khả năng quan sát.
Một API đặt thời hạn hoàn tất nhóm tác vụ theo đồng hồ hệ thống, các máy triển khai lệch giờ nhau dẫn đến timeout không nhất quán; hãy phân tích cách định nghĩa deadline.
Một service nhận yêu cầu streaming rất dài nhưng nhóm structured tasks được thiết kế như request-response ngắn, scope sống quá lâu gây giữ tài nguyên; hãy đánh giá mô hình vòng đời.
Một nhóm muốn dùng structured concurrency để xử lý hàng triệu item trong batch bằng một scope duy nhất, hệ thống tăng mạnh số tác vụ đang chờ; hãy phân tích phạm vi concurrency và giới hạn tải.
Một ứng dụng cần kết hợp kết quả hai hệ thống nhưng một nhánh trả dữ liệu lỗi thời dù thành công, phạm vi structured tasks chỉ báo completed; hãy phân tích sự khác nhau giữa completion và validity.
Một tác vụ con có thời gian xử lý lâu hơn cha dự tính, task cha bị interrupt và trả kết quả thiếu, nhóm chưa xác định cách truyền gián đoạn; hãy phân tích xử lý hủy trong cây tác vụ.
Một dịch vụ dùng structured tasks kết hợp với message broker, phạm vi request đóng trước khi message được broker xác nhận; hãy phân tích cam kết hoàn tất ở ranh giới ngoài tiến trình.
Một nhóm thử bản nâng JDK cho structured concurrency mà thay đổi cách diễn giải ngoại lệ và chính sách hủy, nhưng chỉ chạy happy-path tests; hãy đề xuất phạm vi tình huống cần đánh giá mà không giả định API cố định.
Một hệ thống xử lý đơn hàng gửi message giữa các thành phần độc lập, nhưng hai consumer cùng nhận và xử lý trùng event thanh toán; hãy phân tích hợp đồng giao nhận và tính lặp an toàn.
Một producer nhận dữ liệu cảm biến nhanh hơn worker tiêu thụ và bộ đệm tăng liên tục, dù từng consumer hoạt động đúng; hãy phân tích ranh giới áp lực ngược trong pipeline.
Một hàng đợi có dung lượng giới hạn bắt đầu đầy khi downstream chậm, producer không có chính sách phản hồi tải; hãy đánh giá các kết quả nghiệp vụ khi thông điệp không được nhận.
Một hệ thống gửi tác vụ qua channel và giả định thứ tự nhận bằng thứ tự hoàn thành, nhưng nhiều consumer xử lý khác thời gian; hãy phân tích yêu cầu về ordering.
Một ứng dụng trao đổi thông điệp bất biến giữa các worker nhưng truyền kèm tham chiếu tới danh sách mutable dùng chung, gây kết quả không ổn định; hãy đánh giá quyền sở hữu dữ liệu.
Một actor giữ trạng thái tài khoản nội bộ và nhận các message cộng trừ tiền từ nhiều nguồn, nhưng hệ thống bên ngoài thỉnh thoảng gửi lại message sau timeout; hãy đánh giá xử lý trùng lặp.
Một nhóm chuyển từ shared-memory lock sang message passing nhưng callback của consumer vẫn sửa cache toàn cục không đồng bộ; hãy phân tích phần rủi ro concurrency còn sót lại.
Một mô hình worker pool nhận tác vụ qua hàng đợi nhưng task nặng chiếm hết worker trong khi task ưu tiên cao chờ lâu; hãy đánh giá chính sách fairness của queue.
Một hệ thống có nhiều partition để xử lý song song theo khóa khách hàng, nhưng một khách hàng có lưu lượng vượt trội làm partition quá tải; hãy phân tích hiện tượng hot key.
Một tiến trình truyền message qua channel có bounded buffer, khi consumer bị dừng mà producer vẫn phát, một loạt producer bị block; hãy đánh giá cơ chế phát hiện và phục hồi.
Một ứng dụng cần phát báo cáo theo đúng thứ tự sự kiện nhưng message được xử lý lại sau lỗi và đến trễ; hãy phân tích yêu cầu thứ tự theo version và độ trễ.
Một nhóm dùng hàng đợi không giới hạn để tránh mất dữ liệu khi service ngoài chậm, nhưng memory tăng đến mức JVM dừng; hãy đánh giá đánh đổi giữa lưu lượng đỉnh và tính sẵn sàng.
Một channel có nhiều producer cùng ghi và một consumer đọc, nhưng consumer gộp dữ liệu theo nguồn mà thiếu dấu kết thúc từng luồng; hãy phân tích tiêu chí hoàn tất của mỗi nhóm.
Một dịch vụ dùng message passing để giảm chia sẻ memory, nhưng producer cần biết khi nào tác vụ đã bền vững ở phía consumer; hãy phân biệt các mốc chấp nhận, xử lý và xác nhận.
Một worker nhận thông điệp đã được deserialize thành object mutable rồi gửi cùng instance sang worker thứ hai trước khi hoàn thành cập nhật; hãy đánh giá ranh giới an toàn dữ liệu.
Một hệ thống nhận event từ hai nguồn có đồng hồ không đồng bộ, sau đó gộp theo timestamp để cập nhật trạng thái; hãy phân tích việc suy luận thứ tự nhân quả.
Một pipeline streaming chỉ cấp thêm credit khi consumer đã xử lý xong, nhưng credit đôi lúc không được hoàn lại sau exception; hãy đánh giá biểu hiện tắc nghẽn tích lũy.
Một hệ thống cần ngắt producer khi downstream lỗi để tránh mất dữ liệu, nhưng việc ngắt xảy ra muộn sau hàng nghìn message đã phát; hãy phân tích giới hạn in-flight.
Một actor nhận lệnh thay đổi cấu hình trong lúc đang xử lý một batch lớn, yêu cầu lệnh mới có hiệu lực với một ranh giới rõ ràng; hãy phân tích quan hệ thứ tự giữa các thông điệp.
Một kiến trúc fan-out gửi cùng công việc cho ba consumer khác nhau rồi cần kết hợp phản hồi, nhưng một consumer không phản hồi; hãy đánh giá timeout và tình trạng tác vụ còn tồn tại.
Một service trong production tăng p99 latency theo giờ cao điểm, dù mức CPU chỉ khoảng một nửa, thread dump cho thấy nhiều task đang đợi lock; hãy xác định dữ liệu cần thu thập để đánh giá contention.
Một ứng dụng xuất metrics cho số tác vụ đang chạy, số tác vụ xếp hàng và thời gian chờ nhưng các metric được lấy tại các thời điểm khác nhau; hãy phân tích tính nhất quán của dashboard.
Một nhóm bật quá nhiều debug logging tại các method nóng và lỗi race biến mất, nhưng throughput giảm một nửa; hãy đánh giá ảnh hưởng của instrumentation lên timing.
Một dịch vụ có pool kết nối nhỏ và hàng nghìn Future chờ database, hệ thống điều hành chỉ thấy CPU còn rảnh; hãy phân tích điểm bão hòa tài nguyên bên ngoài CPU.
Một bộ xử lý streaming có thời gian service trung bình ổn định nhưng tail latency tăng khi nhiều worker tranh cùng khóa; hãy xác định cách đo phân bố thời gian chờ.
Một hệ thống có memory leak từ task đã bị client hủy, heap dump còn giữ nhiều callback và Future chưa hoàn tất; hãy phân tích vòng đời tham chiếu còn tồn tại.
Một ứng dụng xử lý batch theo nhiều executor lồng nhau, trong lúc shutdown một pool đã dừng nhưng pool khác vẫn submit tác vụ vào nó; hãy phân tích cuộc đua trạng thái vận hành.
Một dịch vụ thường xuyên tăng số lượng worker khi backlog lớn nhưng throughput không tăng do downstream giới hạn kết nối, đồng thời tỉ lệ retry tăng; hãy đánh giá vòng phản hồi tải.
Một hệ thống cập nhật cấu hình số worker trong lúc pool đang xử lý hàng chục nghìn tác vụ, có request bị từ chối không nhất quán; hãy phân tích chuyển đổi cấu hình an toàn.
Một nhóm không thu thập nguyên nhân exception của task bất đồng bộ mà chỉ dựa vào lỗi trả về cho client, dẫn đến khó xác định công đoạn hỏng; hãy xác định yêu cầu trace context.
Một service đang bảo trì cố gắng dừng các worker trong năm giây nhưng một số đang chờ socket không timeout, khiến triển khai dồn phiên bản; hãy đánh giá giới hạn graceful shutdown.
Một hệ thống dùng circuit breaker với worker pool dùng chung, khi một downstream lỗi kéo dài, hàng đợi chờ và retry tiêu thụ hết worker; hãy phân tích tương tác giữa chính sách phục hồi.
Một ứng dụng có hai phiên bản library native cùng truy cập trạng thái toàn cục theo giả định thread-safe khác nhau, chỉ crash khi chạy song song; hãy đánh giá nguồn dữ liệu điều tra.
Một bộ tổng hợp số liệu chạy nhiều task và in thông báo thành công khi đa số task kết thúc, nhưng vài task bị hủy chưa hoàn trả resource; hãy phân tích tiêu chí hoàn tất vận hành.
Một API phụ thuộc ba microservice chạy đồng thời, khi một phía timeout, log của những phía còn lại không cùng trace id; hãy đánh giá khả năng theo dõi quan hệ cha-con.
Một hệ thống báo tỉ lệ hoàn thành công việc cao nhưng backlog tăng vì số tác vụ đến vượt số tác vụ hoàn tất, đội ngũ chỉ xem số job thành công; hãy phân tích thước đo năng lực thực.
Một ứng dụng xử lý đồng thời trên môi trường container bị throttling CPU, thời gian giữ lock kéo dài bất thường dù không có thay đổi mã nguồn; hãy đánh giá yếu tố môi trường.
Một dịch vụ sử dụng nhiều read-write locks nhưng báo cáo thời gian chờ tổng không cho biết lock nào gây nghẽn, khiến nhóm tăng thêm worker vô ích; hãy phân tích chiến lược đo.
Một worker pool có nhiệm vụ ưu tiên theo deadline, nhưng công việc dài chiếm hết slot khi tác vụ ngắn khẩn cấp đến sau; hãy đánh giá mối quan hệ ưu tiên và tài nguyên.
Một hệ thống thu thập log xảy ra mất thứ tự giữa nhiều thread, nhóm dựa vào timestamp tường để suy ra happens-before; hãy phân tích giới hạn của quan sát thời gian.
Một bài test race condition tạo hai thread rồi ngủ một khoảng cố định trước khi assert, chạy ổn định trên laptop nhưng thất bại trong CI; hãy đánh giá độ tin cậy của cách phối hợp test.
Một bộ kiểm thử chuyển tiền chạy nhiều luồng cùng cập nhật số dư và đôi khi tổng tiền hệ thống bị thay đổi, trong khi unit test từng phương thức đều đạt; hãy xác định bất biến cần kiểm tra.
Một test deadlock chỉ chạy một lần với hai tài khoản cố định, nhưng production gặp khóa vòng khi có hàng trăm tài khoản; hãy phân tích không gian lịch thực thi chưa được bao phủ.
Một nhóm dùng stress test random scheduling trong thời gian ngắn và chưa thấy lỗi, rồi kết luận cấu trúc lock-free hoàn toàn đúng; hãy đánh giá giới hạn của bằng chứng thử nghiệm.
Một hệ thống thử cancellation bằng Future nhưng chỉ kiểm tra trạng thái done của Future, còn task nền có thể tiếp tục ghi database; hãy phân tích kiểm chứng cần phân biệt.
Một bài test Future dựa vào việc gọi callback theo thứ tự đăng ký, nhưng executor có thể chạy trên nhiều luồng; hãy đánh giá tính chính xác của giả định thứ tự.
Một API dùng virtual threads vượt qua throughput test nhưng heap tăng theo request; hãy thiết kế bối cảnh kiểm thử liên quan dữ liệu ThreadLocal và lifecycle của tác vụ.
Một hệ thống message passing có chính sách at-least-once nhưng test chỉ gửi mỗi event một lần, không bao phủ retry hoặc duplication; hãy phân tích kịch bản nghiệp vụ cần đánh giá.
Một nhóm muốn đo scalability từ một tới mười sáu worker trên máy bốn lõi CPU, nhưng không giữ nguyên workload và cache warm-up; hãy đánh giá tính so sánh của benchmark.
Một service đặt hàng yêu cầu không phát sinh đơn trùng khi client retry đồng thời, nhưng kiểm thử chỉ gửi request tuần tự; hãy xác định lỗ hổng của mô hình tải thử.
Một nhóm dùng Thread.sleep để chờ worker hoàn tất thay vì quan sát tín hiệu hoàn thành, test đôi lúc không đủ thời gian trên CI; hãy phân tích tính xác định của điều kiện thành công.
Một hệ thống phải hỗ trợ partial failure của ba tác vụ con, nhưng test structured concurrency chỉ kiểm tra cả ba cùng thành công; hãy xác định các đường lỗi cần được phân biệt.
Một ứng dụng sử dụng atomic counters cho thống kê realtime và kiểm thử thấy tổng dao động khi nhiều luồng đọc, đội ngũ cho rằng bộ đếm lỗi; hãy phân tích cách định nghĩa snapshot kiểm thử.
Một service kiểm thử idempotency bằng hai consumer xử lý cùng message nhưng hệ thống mock ghi theo thứ tự cố định, khác hẳn broker thực; hãy đánh giá mức thực tế của phép thử.
Một bài test tính liveness chỉ kiểm tra rằng worker hoàn tất trong một lần chạy, nhưng worker ưu tiên thấp có thể starvation dưới tải dài; hãy phân tích yêu cầu thời lượng và phân bố tải.
Một hệ thống đánh giá lock contention bằng profiler nhưng chưa phân biệt thời gian block trên monitor và thời gian chờ I/O, dẫn đến kết luận chưa đáng tin; hãy xác định phép đo còn thiếu.
Một nhóm thay đổi chiến lược thread pool cùng lúc nâng CPU quota và giảm latency downstream, sau đó khẳng định cải thiện nhờ thread pool; hãy đánh giá thiết kế thử nghiệm.
Một ứng dụng đặt timeout cho tác vụ cha nhưng test không kiểm tra rằng các Future con đã dừng và tài nguyên được trả lại; hãy phân tích điều kiện cleanup cần xác minh.
Một hệ thống concurrency đạt tất cả unit tests nhưng gặp lỗi về thứ tự message khi restart giữa chừng, test chưa mô phỏng shutdown và recovery; hãy đánh giá mức bao phủ.
Một dịch vụ phát hành phiên bản mới cần giữ đúng tính nhất quán khi traffic tăng gấp ba, đội ngũ chỉ benchmark throughput tổng và bỏ qua lỗi race; hãy xác định tiêu chí nghiệm thu cần quan sát.
