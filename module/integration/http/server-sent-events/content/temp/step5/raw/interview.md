Bạn sẽ giải thích Server-Sent Events giải quyết nhu cầu giao tiếp nào giữa server và client trong một hệ thống web?
Bạn phân biệt SSE với cơ chế HTTP polling trong việc cập nhật dữ liệu gần thời gian thực như thế nào?
Bạn sẽ chọn SSE thay vì WebSocket dựa trên những đặc điểm nào của luồng trao đổi dữ liệu?
Bạn phân biệt tính một chiều của SSE với các hình thức tương tác hai chiều trong ứng dụng như thế nào?
Khi nào việc kết hợp SSE để nhận sự kiện và HTTP API để gửi lệnh là một thiết kế hợp lý?
Bạn phân tích các đánh đổi về kết nối lâu dài, hạ tầng và độ trễ khi dùng SSE như thế nào?
Bạn sẽ xác định loại dữ liệu nào nên gửi dưới dạng sự kiện và loại nào nên lấy qua API thông thường ra sao?
Bạn sẽ đánh giá những rủi ro gì trước khi chọn SSE cho thông báo nghiệp vụ quan trọng?
Bạn mô tả vòng đời kết nối SSE từ khi trình duyệt mở yêu cầu đến khi nhận sự kiện như thế nào?
Bạn giải thích vì sao SSE dùng một HTTP response kéo dài để chuyển nhiều sự kiện như thế nào?
Bạn sẽ xác định endpoint SSE và tập người dùng được phép đăng ký theo ranh giới nghiệp vụ ra sao?
Bạn phân biệt kết nối SSE với cơ chế stream qua WebSocket hoặc HTTP streaming thông thường như thế nào?
Bạn thiết kế luồng cập nhật tiến độ công việc dài hạn bằng SSE như thế nào?
Bạn sẽ dùng SSE để cập nhật bảng theo dõi số liệu mà vẫn kiểm soát tính mới của dữ liệu ra sao?
Bạn giải quyết yêu cầu phát thông báo cho nhiều nhóm người dùng bằng SSE và kênh phân phối sự kiện như thế nào?
Bạn xác định mục tiêu về độ trễ, tính liên tục và khả năng mất sự kiện cho một luồng SSE ra sao?
Bạn giải thích ý nghĩa của Content-Type text/event-stream trong một HTTP response như thế nào?
Bạn sẽ định dạng một sự kiện SSE có nhiều dòng dữ liệu trong trường data như thế nào?
Bạn phân biệt các trường data, event, id và retry trong định dạng event-stream như thế nào?
Bạn giải thích vai trò của dòng trống trong việc kết thúc một sự kiện SSE như thế nào?
Bạn sẽ xử lý nhiều dòng data liên tiếp khi client nhận một sự kiện như thế nào?
Bạn phân tích hành vi khi sự kiện SSE không có trường event và cách client lắng nghe nó ra sao?
Bạn sẽ xác định tên sự kiện tùy biến để người tiêu thụ hiểu rõ ý nghĩa nghiệp vụ như thế nào?
Bạn sử dụng trường id trong SSE để phục vụ khả năng khôi phục sau ngắt kết nối như thế nào?
Bạn giải thích ảnh hưởng của một trường id rỗng đối với trạng thái ghi nhớ định danh sự kiện của EventSource như thế nào?
Bạn đánh giá những ràng buộc nào khi thiết kế định danh sự kiện duy nhất và có thứ tự?
Bạn phân biệt retry field trong luồng SSE với chính sách thử lại request ở tầng ứng dụng như thế nào?
Bạn sử dụng dòng comment trong event-stream để hỗ trợ giữ kết nối ra sao?
Bạn sẽ xử lý dữ liệu Unicode và ký tự xuống dòng khi xây dựng event-stream đúng chuẩn như thế nào?
Bạn sẽ truyền payload JSON qua trường data mà vẫn giữ ranh giới sự kiện SSE chính xác ra sao?
Bạn thiết kế schema cho payload sự kiện để tương thích giữa nhiều phiên bản frontend như thế nào?
Bạn sẽ phân biệt một sự kiện mang toàn bộ trạng thái với một sự kiện chỉ chứa phần thay đổi như thế nào?
Bạn đánh giá tác động của việc gửi payload quá lớn lên độ trễ và bộ nhớ của kết nối SSE ra sao?
Bạn sẽ xây dựng quy tắc không gửi dữ liệu nhạy cảm vào các sự kiện chia sẻ giữa nhiều client như thế nào?
Bạn sẽ xử lý sự kiện thiếu trường bắt buộc hoặc không parse được payload JSON ở client ra sao?
Bạn mô tả cách tạo EventSource trên trình duyệt và quản lý URL đăng ký luồng như thế nào?
Bạn phân biệt event handler cho message mặc định với addEventListener cho sự kiện được đặt tên như thế nào?
Bạn sử dụng các sự kiện open, message và error để theo dõi trạng thái kết nối ra sao?
Bạn giải thích ý nghĩa các trạng thái CONNECTING, OPEN và CLOSED của EventSource như thế nào?
Bạn sẽ dùng phương thức close của EventSource ở những thời điểm nào trong vòng đời giao diện?
Bạn ngăn việc tạo nhiều EventSource dư thừa khi component frontend được render hoặc điều hướng lại như thế nào?
Bạn giải quyết tình huống người dùng mở nhiều tab cùng đăng ký một SSE endpoint ra sao?
Bạn sẽ cập nhật UI như thế nào để tránh render lại toàn bộ danh sách khi có nhiều sự kiện liên tục?
Bạn thiết kế cơ chế tạm ngừng hiển thị hoặc gộp sự kiện khi giao diện không theo kịp tốc độ cập nhật ra sao?
Bạn lựa chọn cách hiển thị trạng thái mất kết nối cho người dùng trong một bảng điều khiển trực tiếp như thế nào?
Bạn phân biệt lỗi kết nối tạm thời với việc client chủ động đóng EventSource trong logic giao diện như thế nào?
Bạn sẽ tích hợp SSE vào ứng dụng có state management mà vẫn tránh dữ liệu cũ ghi đè dữ liệu mới ra sao?
Bạn giải thích hành vi reconnect tự động của EventSource khi kết nối bị ngắt bất ngờ như thế nào?
Bạn phân tích vai trò của HTTP Last-Event-ID khi client kết nối lại ra sao?
Bạn thiết kế server dùng Last-Event-ID để phát lại các sự kiện client chưa nhận như thế nào?
Bạn sẽ quyết định lưu lịch sử sự kiện trong bao lâu dựa trên nhu cầu khôi phục và lưu lượng như thế nào?
Bạn xử lý tình huống Last-Event-ID trỏ đến sự kiện đã bị xóa khỏi bộ nhớ lưu trữ ra sao?
Bạn phân biệt truyền sự kiện ít nhất một lần với yêu cầu xử lý chính xác một lần ở phía client như thế nào?
Bạn thiết kế cơ chế loại trùng sự kiện khi reconnect có thể phát lại sự kiện cuối như thế nào?
Bạn sẽ tạo quy tắc sắp xếp sự kiện khi dữ liệu nguồn đến từ nhiều partition hoặc service ra sao?
Bạn xử lý các khoảng trống trong chuỗi event ID để client không bỏ qua thay đổi quan trọng như thế nào?
Bạn thiết kế một phương án lấy snapshot khi client đã bỏ lỡ quá nhiều sự kiện để replay ra sao?
Bạn sẽ lựa chọn giữa replay theo event ID và đồng bộ lại toàn bộ trạng thái dựa trên yêu cầu nào?
Bạn xử lý trường hợp client bắt đầu đăng ký luồng giữa lúc snapshot đang được tải như thế nào?
Bạn sẽ tránh tình trạng hiển thị trạng thái cũ khi event đến không đúng thứ tự ra sao?
Bạn phân biệt việc server phát sự kiện thành công với việc client đã xử lý sự kiện trong giao diện như thế nào?
Bạn sẽ xác định cách khôi phục nếu event ID thay đổi ý nghĩa sau khi triển khai phiên bản server mới ra sao?
Bạn thiết kế cách kết nối lại theo tốc độ hợp lý khi hàng nghìn client cùng mất mạng như thế nào?
Bạn giải thích các giới hạn của retry field khi muốn triển khai chiến lược backoff có jitter như thế nào?
Bạn sẽ quyết định khi nào server nên chủ động kết thúc luồng và ngăn client tự kết nối lại ra sao?
Bạn kiểm tra cách client phản ứng khi SSE endpoint trả các mã HTTP khác nhau như thế nào?
Bạn xử lý tình huống server gửi response hợp lệ HTTP nhưng Content-Type không phải text/event-stream ra sao?
Bạn thiết kế cách phát heartbeat để proxy không đóng kết nối nhàn rỗi như thế nào?
Bạn lựa chọn khoảng thời gian heartbeat dựa trên timeout của mạng và chi phí gửi dữ liệu ra sao?
Bạn phân biệt việc nhận heartbeat với việc nhận sự kiện nghiệp vụ khi đánh giá sức khỏe luồng như thế nào?
Bạn xử lý trường hợp thiết bị chuyển từ Wi-Fi sang mạng di động khiến SSE bị gián đoạn ra sao?
Bạn sẽ thiết kế SSE endpoint trong Spring MVC bằng SseEmitter như thế nào?
Bạn giải thích sự khác nhau giữa trả SseEmitter và trả một HTTP response thông thường trong Spring MVC ra sao?
Bạn lựa chọn timeout của SseEmitter dựa trên giới hạn hạ tầng và đặc điểm kết nối như thế nào?
Bạn sẽ sử dụng SseEmitter.event để thiết lập tên sự kiện, dữ liệu và ID một cách nhất quán ra sao?
Bạn quản lý các callback onCompletion, onTimeout và onError của SseEmitter để giải phóng tài nguyên như thế nào?
Bạn thiết kế registry theo dõi SseEmitter đang hoạt động mà không giữ các kết nối đã đóng ra sao?
Bạn sẽ bảo vệ cấu trúc quản lý emitter khỏi tranh chấp khi nhiều luồng cùng đăng ký hoặc ngắt kết nối như thế nào?
Bạn xử lý IOException khi gửi SSE qua SseEmitter trong trường hợp client đã ngắt kết nối ra sao?
Bạn sẽ đồng bộ các lần gọi send khi nhiều tác vụ cùng muốn ghi vào một SseEmitter như thế nào?
Bạn thiết kế cơ chế phát sự kiện tới nhiều SseEmitter mà không để một client chậm kéo dài toàn bộ lượt phát ra sao?
Bạn phân tích chi phí luồng và tài nguyên của ứng dụng Spring MVC khi duy trì nhiều kết nối SSE như thế nào?
Bạn tích hợp nguồn sự kiện từ hàng đợi hoặc broker với SseEmitter theo cơ chế nào để tránh chặn luồng xử lý?
Bạn xử lý tình huống SseEmitter bị timeout đúng lúc server đang gửi một sự kiện như thế nào?
Bạn sẽ triển khai cơ chế loại bỏ client không còn hợp lệ trong một dịch vụ Spring MVC nhiều instance ra sao?
Bạn so sánh những điều kiện khiến SseEmitter đơn giản hơn hoặc khó mở rộng hơn phương án reactive như thế nào?
Bạn sẽ triển khai SSE endpoint bằng Spring WebFlux trả Flux<ServerSentEvent> như thế nào?
Bạn giải thích vai trò của ServerSentEvent builder trong việc xây dựng tên, ID, retry và data ra sao?
Bạn sử dụng MediaType.TEXT_EVENT_STREAM trong WebFlux để xác lập loại nội dung phản hồi như thế nào?
Bạn phân biệt Flux phát dữ liệu hữu hạn với một luồng SSE được thiết kế kéo dài như thế nào?
Bạn giải thích khái niệm cold publisher và hot publisher khi nhiều client đăng ký một luồng SSE ra sao?
Bạn sẽ phân phối một nguồn sự kiện tới nhiều subscriber trong Reactor theo cách nào?
Bạn đánh giá nguy cơ mất sự kiện khi dùng multicast sink cho client tham gia muộn như thế nào?
Bạn quyết định khi nào dùng cơ chế replay trong Reactor thay vì một event store bền vững ra sao?
Bạn sử dụng các tín hiệu hủy subscription để giải phóng kết nối và tài nguyên trong WebFlux như thế nào?
Bạn xử lý lỗi trong Flux sao cho client có thể biết việc kết nối bị đóng và server không giữ subscription rò rỉ ra sao?
Bạn xác định các đoạn mã blocking cần tách khỏi event loop của WebFlux như thế nào?
Bạn lựa chọn scheduler cho thao tác blocking bên ngoài luồng reactive theo tiêu chí nào?
Bạn thiết kế pipeline reactive để biến đổi sự kiện nhưng không làm sai thứ tự theo thực thể nghiệp vụ như thế nào?
Bạn so sánh cách quản lý vòng đời client giữa Spring MVC SseEmitter và Spring WebFlux như thế nào?
Bạn sẽ chọn Spring MVC hay WebFlux cho hệ thống dựa trên số kết nối, loại nguồn dữ liệu và kinh nghiệm vận hành ra sao?
Bạn giải thích sự khác biệt giữa backpressure của Reactive Streams và khả năng kiểm soát tốc độ của EventSource trên trình duyệt như thế nào?
Bạn xác định các tầng có thể tích tụ dữ liệu khi producer nhanh hơn mạng hoặc client như thế nào?
Bạn sẽ đặt giới hạn bộ đệm cho từng kết nối SSE dựa trên dung lượng bộ nhớ và SLA ra sao?
Bạn xử lý client quá chậm bằng các chiến lược drop, coalesce hoặc ngắt kết nối trong điều kiện nào?
Bạn cân nhắc điều gì khi áp dụng onBackpressureBuffer, onBackpressureDrop hoặc onBackpressureLatest trong Reactor?
Bạn đảm bảo việc loại bớt sự kiện không làm sai lệch trạng thái nghiệp vụ ở client bằng cách nào?
Bạn thiết kế quy tắc ưu tiên sự kiện khi phải giảm tải mà vẫn bảo toàn cảnh báo quan trọng ra sao?
Bạn sẽ phân biệt luồng sự kiện cần đầy đủ lịch sử với luồng chỉ cần giá trị mới nhất như thế nào?
Bạn xác định thông số nào cho biết SSE server đang tiêu thụ bộ nhớ quá mức do client chậm ra sao?
Bạn thiết kế cơ chế giới hạn số kết nối SSE trên một người dùng hoặc tài khoản như thế nào?
Bạn sẽ xác thực người dùng khi mở SSE endpoint trong trình duyệt dựa trên các giới hạn của EventSource ra sao?
Bạn giải thích khó khăn khi cần truyền Authorization header tùy chỉnh với EventSource gốc của trình duyệt như thế nào?
Bạn cân nhắc dùng cookie phiên, token hoặc một thư viện SSE client thay thế theo yêu cầu bảo mật như thế nào?
Bạn sẽ bảo vệ credential trong cookie của kết nối SSE bằng các thuộc tính bảo mật thích hợp ra sao?
Bạn phân tích rủi ro khi đưa access token vào query string của SSE URL và cách hạn chế như thế nào?
Bạn lựa chọn chính sách CORS cho endpoint SSE khi frontend và backend nằm ở các origin khác nhau ra sao?
Bạn giải thích vai trò của withCredentials khi EventSource kết nối tới dịch vụ khác origin như thế nào?
Bạn sẽ kiểm soát quyền đăng ký kênh sự kiện theo người dùng và loại dữ liệu như thế nào?
Bạn thiết kế cơ chế ngừng phát dữ liệu khi quyền truy cập của người dùng bị thu hồi trong một kết nối dài như thế nào?
Bạn sử dụng TLS để bảo vệ nội dung SSE và thông tin xác thực trên đường truyền như thế nào?
Bạn sẽ kiểm soát rò rỉ dữ liệu giữa các tenant khi cùng một nguồn sự kiện được phân phối qua nhiều kết nối ra sao?
Bạn cân nhắc cách phòng chống lạm dụng kết nối và từ chối dịch vụ trên SSE endpoint như thế nào?
Bạn sẽ áp dụng kiểm tra Origin và các chính sách cookie khi SSE sử dụng phiên đăng nhập ra sao?
Bạn phân biệt yêu cầu xác thực lúc bắt đầu kết nối với việc kiểm tra quyền trên từng sự kiện gửi đi như thế nào?
Bạn thiết kế audit và logging cho đăng ký SSE mà không ghi thông tin nhạy cảm từ payload ra sao?
Bạn phân tích cách reverse proxy có thể buffer response SSE và ảnh hưởng đến độ trễ như thế nào?
Bạn sẽ cấu hình proxy buffering và các response header để sự kiện được chuyển tiếp kịp thời ra sao?
Bạn chọn giá trị timeout ở reverse proxy, load balancer và application server sao cho phù hợp với SSE như thế nào?
Bạn đánh giá tác động của HTTP/1.1 connection limit trong trình duyệt khi ứng dụng mở nhiều EventSource như thế nào?
Bạn phân tích sự khác biệt về multiplexing của HTTP/2 đối với số kết nối SSE đồng thời ra sao?
Bạn sẽ kiểm tra proxy hoặc CDN có hỗ trợ truyền response streaming đúng cách như thế nào?
Bạn xử lý việc gateway hoặc proxy tự động nén và tích tụ các chunk sự kiện trước khi gửi tới client ra sao?
Bạn sẽ quyết định có sử dụng Cache-Control và cơ chế tắt biến đổi response cho SSE endpoint như thế nào?
Bạn phân biệt sự kiện bị trễ do buffer ứng dụng với sự kiện bị trễ do proxy hoặc mạng ra sao?
Bạn kiểm tra tác động của thời gian sống kết nối tối đa do một tầng hạ tầng áp đặt như thế nào?
Bạn sẽ triển khai SSE qua nhiều instance server khi client kết nối đến các instance khác nhau ra sao?
Bạn phân biệt lợi ích và hạn chế của sticky session với việc dùng broker chia sẻ sự kiện giữa các instance như thế nào?
Bạn thiết kế event ID và khả năng replay khi reconnect được load balancer đưa tới instance khác như thế nào?
Bạn xử lý việc một instance đang gửi SSE bị dừng để nâng cấp mà client vẫn khôi phục được trạng thái ra sao?
Bạn lựa chọn hệ thống phân phối event giữa các instance dựa trên yêu cầu fan-out và lưu lịch sử như thế nào?
Bạn xác định giới hạn file descriptor, connection pool và bộ nhớ cho một hệ thống hàng chục nghìn kết nối như thế nào?
Bạn phân tích sự khác biệt giữa tải khi có nhiều kết nối nhàn rỗi và tải khi có nhiều sự kiện được phát đồng thời ra sao?
Bạn sẽ thiết kế cơ chế chống reconnect storm khi một khu vực mạng hoặc cụm dịch vụ được khôi phục như thế nào?
Bạn kiểm tra tác động của việc deploy nhiều phiên bản SSE server lên định dạng payload mà client đang sử dụng ra sao?
Bạn sử dụng những chỉ số nào để theo dõi số kết nối, tần suất reconnect, tốc độ sự kiện và độ trễ phát tới client?
Bạn sẽ đo thời gian từ lúc sự kiện phát sinh đến khi trình duyệt xử lý nó như thế nào?
Bạn xác định ngưỡng cảnh báo cho emitter rò rỉ, bộ đệm tăng và số kết nối bị ngắt bất thường ra sao?
Bạn sẽ gắn correlation ID giữa sự kiện nghiệp vụ, broker và SSE response để truy vết như thế nào?
Bạn thiết kế log khi client ngắt kết nối thường xuyên mà không tạo quá nhiều dữ liệu vận hành ra sao?
Bạn tổ chức test cho bộ định dạng SSE để xác minh nhiều dòng data, event ID và dấu phân cách sự kiện như thế nào?
Bạn sẽ kiểm thử trình duyệt nhận đúng sự kiện mặc định và sự kiện có tên riêng bằng EventSource ra sao?
Bạn mô phỏng mất kết nối và kiểm thử reconnect cùng Last-Event-ID như thế nào?
Bạn kiểm thử client nhận sự kiện trùng sau replay và không cập nhật trạng thái sai như thế nào?
Bạn xây dựng integration test cho Spring MVC SseEmitter để kiểm tra sự kiện, timeout và dọn dẹp kết nối ra sao?
Bạn kiểm thử Spring WebFlux trả Flux<ServerSentEvent> trong điều kiện hủy subscription và lỗi nguồn dữ liệu như thế nào?
Bạn thiết kế kiểm thử tải để đánh giá hàng nghìn kết nối SSE mà không nhầm số kết nối với throughput ra sao?
Bạn mô phỏng client đọc chậm để kiểm tra giới hạn buffer và chiến lược backpressure như thế nào?
Bạn kiểm tra HTTP headers, CORS, cookie và quyền truy cập của SSE endpoint trong môi trường thử nghiệm ra sao?
Bạn sẽ kiểm thử SSE chạy qua reverse proxy thực tế để phát hiện buffering hoặc timeout sai như thế nào?
Bạn thiết kế kiểm thử chaos khi ngắt một instance trong cụm để đánh giá reconnect và replay như thế nào?
Bạn đo sự khác biệt về sử dụng tài nguyên giữa SseEmitter và WebFlux trong cùng một workload như thế nào?
Bạn định nghĩa tiêu chí chấp nhận về độ trễ, độ tin cậy và tiêu thụ tài nguyên trước khi đưa SSE lên production ra sao?
Nếu một dashboard chậm nhận sự kiện dù server đã gửi thành công, bạn sẽ xác định nguyên nhân ở ứng dụng, proxy hay trình duyệt như thế nào?
Nếu một client mất mạng mười phút và event store chỉ giữ lịch sử ngắn, bạn sẽ thiết kế cơ chế phục hồi trạng thái như thế nào?
Nếu người dùng mở nhiều tab khiến kết nối HTTP/1.1 bị giới hạn, bạn sẽ thay đổi thiết kế phía client hoặc hạ tầng ra sao?
Nếu SseEmitter không được dọn dẹp sau khi trình duyệt đóng tab, bạn sẽ tìm và sửa nguyên nhân rò rỉ tài nguyên như thế nào?
Nếu một Flux phát nhanh hơn khả năng đọc của một client, bạn sẽ lựa chọn chính sách buffer và xử lý sự kiện nào?
Nếu SSE dùng cookie để xác thực qua nhiều origin, bạn sẽ kiểm tra những yếu tố nào khi trình duyệt không mở được stream?
Nếu load balancer chuyển client reconnect sang instance khác, bạn sẽ đảm bảo event ID và replay được xử lý nhất quán ra sao?
Nếu hệ thống cần gửi cảnh báo quan trọng lẫn số liệu cập nhật thường xuyên, bạn sẽ thiết kế hai loại sự kiện và quy tắc giảm tải như thế nào?
Nếu một đợt deploy gây reconnect đồng loạt của hàng nghìn client, bạn sẽ chuẩn bị khả năng phục hồi và quan sát hệ thống ra sao?
Nếu phải xây dựng hệ thống thông báo SSE từ đầu bằng Spring MVC hoặc WebFlux, bạn sẽ trình bày các quyết định về hợp đồng, độ tin cậy, bảo mật, proxy và kiểm thử như thế nào?
