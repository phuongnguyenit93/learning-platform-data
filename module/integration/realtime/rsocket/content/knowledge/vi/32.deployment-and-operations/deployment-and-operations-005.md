# Giới hạn số kết nối, số luồng, bộ nhớ và tài nguyên hệ điều hành

## Mục tiêu

RSocket hỗ trợ giao tiếp bất đồng bộ, hai chiều và reactive trên TCP hoặc WebSocket. Một kết nối có thể mang nhiều tương tác đồng thời theo các kiểu request-response, fire-and-forget, request-stream và request-channel. Cơ chế multiplexing giúp giảm số kết nối cần mở, nhưng cũng khiến một kết nối có thể mang lượng công việc rất lớn. Nếu chỉ giới hạn số socket mà không giới hạn stream, hàng đợi, bộ nhớ và công việc phía sau, một client hoặc một tenant vẫn có thể làm cạn tài nguyên của server.

Khi triển khai RSocket, cần xác định rõ ngân sách cho từng lớp: kết nối vật lý, tương tác RSocket, công việc đang xử lý, dữ liệu đang đệm và tài nguyên của hệ điều hành. Các giới hạn phải phối hợp với backpressure, xác thực tenant, khả năng của database và các dịch vụ phụ thuộc. Mục tiêu là giữ độ trễ trong ngưỡng phục vụ, cô lập tenant khi quá tải và để hệ thống từ chối có kiểm soát trước khi tiến trình hoặc máy chủ bị cạn tài nguyên.

## 1. Phân biệt kết nối, stream và mức đồng thời

Một số đại lượng thường bị gọi chung là “số kết nối”, nhưng chúng mô tả các tài nguyên khác nhau:

| Đại lượng | Ý nghĩa | Tài nguyên chịu tác động |
| --- | --- | --- |
| Kết nối TCP/WebSocket | Socket và phiên RSocket giữa hai đầu | File descriptor, bộ nhớ nền, bảng kết nối, keepalive |
| Stream RSocket đang hoạt động | Một tương tác logic được multiplex trên kết nối | Trạng thái stream, bộ đệm, bộ phát dữ liệu và thời gian sống của tương tác |
| Công việc đang thực thi | Handler, truy vấn DB hoặc lời gọi dịch vụ đang chạy | CPU, connection pool, thread hoặc scheduler |
| Hàng đợi đang chờ | Yêu cầu đã nhận nhưng chưa được xử lý | Heap/direct memory, độ trễ và nguy cơ tăng tải dây chuyền |
| Demand của một stream | Số phần tử mà bên nhận đã yêu cầu từ publisher | Lượng dữ liệu được phép phát theo backpressure |

Một kết nối RSocket có thể mang nhiều stream. Vì vậy, giới hạn số kết nối không tự động giới hạn số stream. Tương tự, giới hạn số stream không bảo đảm số truy vấn database đồng thời nằm trong khả năng của connection pool.

Các kiểu tương tác có đặc điểm tài nguyên khác nhau:

- **Request-response** thường có vòng đời ngắn, nhưng lưu lượng cao vẫn có thể tạo nhiều handler và truy vấn đồng thời.
- **Fire-and-forget** không chờ phản hồi ở phía gửi, nhưng server vẫn phải xác thực, nhận, xếp lịch và xử lý yêu cầu. Không nên coi kiểu này là miễn phí.
- **Request-stream** có thể tồn tại lâu và phát nhiều phần tử. Cần giới hạn số stream, thời gian sống, tốc độ phát và dữ liệu đang đệm.
- **Request-channel** có dữ liệu đi theo cả hai chiều. Cần kiểm soát demand và bộ đệm của cả luồng vào lẫn luồng ra.

REQUEST_N là tín hiệu demand của một stream: nó cho biết bên nhận sẵn sàng nhận thêm bao nhiêu phần tử. Đây là cơ chế backpressure ở cấp stream, không phải quota tổng số stream đang mở hay số handler đang chạy. Một client vẫn có thể mở rất nhiều stream, mỗi stream chỉ yêu cầu một phần tử. Hệ thống phải áp dụng giới hạn riêng cho số tương tác và mức đồng thời xử lý.

## 2. Thiết kế quota theo nhiều lớp

Không có một ngưỡng duy nhất phù hợp cho mọi triển khai. Nên chia quota theo vị trí có thể kiểm soát:

1. **Tại cổng vào hoặc transport:** giới hạn số kết nối được chấp nhận trên mỗi instance, tốc độ tạo kết nối và kích thước frame tối đa. Lớp này bảo vệ socket, file descriptor và bộ nhớ nền.
2. **Tại phiên RSocket:** đếm số tương tác đang hoạt động trên từng kết nối. Có thể đặt giới hạn riêng cho request-response, stream và channel nếu đặc tính tải khác nhau.
3. **Tại lớp ứng dụng:** giới hạn số công việc đang thực thi trên toàn instance và trên từng tenant. Đây là nơi biết danh tính tenant và mức dịch vụ được cấp.
4. **Tại từng phụ thuộc:** giới hạn số truy vấn DB, lời gọi HTTP, tác vụ CPU và thao tác ghi. Quota của RSocket không thay thế giới hạn của các connection pool hoặc dịch vụ phía sau.
5. **Tại hàng đợi:** đặt giới hạn số phần tử và tổng byte được chờ. Khi hàng đợi đầy, từ chối sớm hoặc áp dụng chính sách giảm tải đã định.

Nên phân biệt bốn loại quota:

- **Quota kết nối:** số socket đồng thời của một client, tenant hoặc toàn instance.
- **Quota đồng thời:** số tương tác hoặc công việc đang chạy tại cùng thời điểm.
- **Quota tốc độ:** số yêu cầu hoặc thông điệp được nhận trong một khoảng thời gian, thường dùng token bucket hoặc sliding window.
- **Quota bộ đệm:** số phần tử hoặc số byte được giữ trong hàng đợi và trong các stream.

Giới hạn tốc độ không thay thế giới hạn đồng thời. Một tenant có thể gửi với tốc độ vừa phải nhưng mở stream kéo dài, khiến số stream đang sống tăng dần. Ngược lại, giới hạn đồng thời không ngăn được một tenant gửi các yêu cầu ngắn với tốc độ quá cao. Cần chọn cả hai khi mô hình tải yêu cầu.

### Quota ở cấp kết nối và cấp stream

Quota kết nối nên được kiểm tra trước hoặc ngay khi server chấp nhận phiên. Có thể đặt ngưỡng ở load balancer, transport server hoặc một lớp admission control của ứng dụng. Quota cấp kết nối nên bao gồm:

- Giới hạn tổng kết nối trên mỗi instance để bảo vệ file descriptor và bộ nhớ nền.
- Giới hạn kết nối theo danh tính client hoặc tenant để một tenant không chiếm toàn bộ socket.
- Giới hạn tốc độ kết nối mới để tránh reconnect storm khi instance khởi động lại.
- Chính sách idle timeout, keepalive và drain khi triển khai phiên bản mới.

Quota stream cần được kiểm tra khi nhận một tương tác mới. Theo dõi số stream đang hoạt động trên từng kết nối, từng tenant và toàn instance. Nếu vượt ngưỡng, từ chối tương tác mới với lỗi ứng dụng có thể nhận biết và hướng dẫn client retry có backoff. Không xếp vô hạn các yêu cầu vượt quota vào hàng đợi.

Một số stack RSocket hỗ trợ cơ chế **Lease** của giao thức. Responder có thể cấp cho requester một số lượt yêu cầu trong một khoảng thời gian. Lease hữu ích để điều tiết lượng request từ peer và phối hợp với khả năng phục vụ hiện tại. Tuy nhiên, Lease không thay thế quota theo tenant, quota đồng thời ở handler, giới hạn bộ nhớ hoặc giới hạn database. Cần xác minh thư viện client/server đang dùng có hỗ trợ và đã bật cơ chế này đúng cách hay chưa.

Giới hạn frame hoặc payload tối đa cũng cần được cấu hình riêng. Một stream ít phần tử nhưng mỗi payload rất lớn vẫn có thể tiêu thụ nhiều bộ nhớ. Giới hạn kích thước frame giúp chặn đầu vào bất thường, nhưng không thay thế giới hạn tổng byte đang đệm trong suốt vòng đời stream.

## 3. Bảo đảm công bằng giữa các tenant

Nếu nhiều tenant dùng chung một RSocket server, quota toàn cục đơn thuần không bảo đảm công bằng. Tenant có lưu lượng lớn có thể chiếm hết permit trước khi tenant nhỏ được phục vụ. Cần kết hợp giới hạn toàn cục với ngân sách riêng cho từng tenant.

Một chính sách cơ bản có thể gồm:

- **Giới hạn kết nối theo tenant:** ngăn một tenant mở quá nhiều socket.
- **Giới hạn stream đang hoạt động theo tenant:** ngăn một tenant chiếm toàn bộ slot tương tác.
- **Giới hạn công việc đồng thời theo tenant:** bảo vệ CPU, database và dịch vụ phụ thuộc.
- **Giới hạn tốc độ và byte theo tenant:** kiểm soát burst và payload lớn.
- **Hàng đợi có giới hạn theo tenant:** một tenant đầy hàng đợi không làm các tenant khác phải chờ phía sau.
- **Ngân sách toàn cục:** tổng tất cả tenant vẫn phải nằm trong khả năng của instance.

Danh tính tenant phải được lấy từ kết quả xác thực đáng tin cậy, chẳng hạn principal hoặc metadata đã được xác minh. Không dùng một trường tenant do client tự gửi mà chưa kiểm tra làm khóa quota. Nếu một tenant có nhiều kết nối, quota của tenant phải được chia sẻ giữa các kết nối đó; quota chỉ đếm trên từng socket có thể bị vượt bằng cách mở thêm socket.

Khi các tenant có gói dịch vụ khác nhau, có thể cấp quota theo trọng số hoặc mức dịch vụ. Một bộ điều phối công bằng có thể lấy công việc luân phiên từ hàng đợi từng tenant theo trọng số. Cần đặt giới hạn cả số phần tử lẫn số byte cho mỗi hàng đợi. Hàng đợi công bằng nhưng không giới hạn kích thước vẫn có thể làm cạn heap.

Không nên giữ permit chỉ cho thao tác bắt đầu rồi thả ngay khi stream được tạo nếu mục tiêu là giới hạn số stream sống đồng thời. Với request-stream hoặc request-channel dài hạn, permit biểu diễn mức đồng thời phải được giữ cho đến khi stream hoàn tất, lỗi hoặc bị hủy. Nếu cần quota tốc độ, dùng token bucket riêng và tiêu thụ token tại thời điểm nhận yêu cầu.

Ví dụ sau minh họa quota đồng thời theo tenant cho một handler request-response bằng Reactor:

~~~java
Mono<Reply> handle(TenantId tenantId, Request request) {
    return Mono.defer(() -> {
        TenantQuota quota = quotas.forTenant(tenantId);
        if (!quota.tryAcquire()) {
            return Mono.error(new TenantOverloadedException());
        }

        // defer chuyển cả lỗi phát sinh đồng bộ trong handler thành tín hiệu lỗi.
        // doFinally giải phóng permit khi complete, error hoặc cancel.
        return Mono.defer(() -> applicationService.handle(request))
                .doFinally(signal -> quota.release());
    });
}
~~~

Với request-stream hoặc request-channel, áp dụng cùng nguyên tắc cho Flux và giữ permit trong toàn bộ vòng đời publisher. Trong triển khai thực tế, bộ quota nên quản lý đồng thời ngân sách toàn cục và ngân sách tenant. Khi lấy nhiều permit, cần có thao tác reserve có rollback rõ ràng nếu một bước thất bại; tránh chờ khóa hoặc semaphore blocking trên event loop. Cần kiểm tra cả đường hủy để permit không bị rò rỉ khi client ngắt kết nối.

Khi quá tải, phản hồi nên nhất quán: cho client biết yêu cầu bị từ chối do quota, có thể retry hay không, và khoảng backoff phù hợp nếu có. Retry cần có jitter và giới hạn số lần. Nếu tất cả client cùng retry ngay lập tức, tải có thể tăng mạnh hơn sau khi server vừa từ chối.

## 4. Quản lý heap, direct memory và buffer

Một tiến trình Java dùng nhiều vùng nhớ. Heap chứa object Java; direct memory chứa các vùng nhớ ngoài heap thường được dùng cho I/O; ngoài ra còn metaspace, code cache, stack của thread, cấu trúc native của JVM, TLS và thư viện hệ thống. Vì vậy, đặt -Xmx bằng giới hạn RAM của container có thể khiến tiến trình bị hệ điều hành kill dù heap chưa đầy.

Trong ứng dụng RSocket dùng Reactor Netty, payload và dữ liệu mạng có thể đi qua ByteBuf và pooled allocator. Direct buffer giúp giảm một số lần copy giữa heap và native I/O, nhưng vẫn tiêu thụ RAM của container. Bộ cấp phát có thể giữ lại vùng nhớ để tái sử dụng; số liệu heap thấp không có nghĩa tổng bộ nhớ tiến trình thấp.

Hãy lập ngân sách theo tổng bộ nhớ:

~~~text
RAM container
  >= heap tối đa
   + ngân sách direct/native buffer
   + metaspace và code cache
   + tổng stack của các thread
   + TLS, thư viện native và cấu trúc runtime
   + phần dự phòng cho hệ điều hành và biến động tải
~~~

Đây là mô hình ngân sách, không phải công thức dự đoán chính xác. Các thành phần cần được đo trên đúng JDK, Netty, cấu hình allocator và giới hạn container đang triển khai. -Xmx giới hạn heap; -XX:MaxDirectMemorySize có thể đặt giới hạn cho direct buffer do JVM quản lý. Cần kiểm tra hành vi của phiên bản Netty đang dùng và theo dõi cả RSS hoặc working set của container.

Các nguyên tắc kiểm soát bộ nhớ:

- Giới hạn kích thước frame/payload đầu vào và kích thước thông điệp sau giải mã.
- Giới hạn số phần tử và tổng byte của mọi queue, buffer và batch.
- Duy trì backpressure xuyên suốt từ publisher đến consumer; tránh tạo hàng đợi không giới hạn.
- Tránh các thao tác như gom toàn bộ stream vào danh sách, cache vô hạn hoặc buffer không có giới hạn.
- Đặt giới hạn cho số stream dài hạn và số consumer chậm.
- Theo dõi heap, GC, direct memory, RSS và số byte đang đệm theo tenant.
- Với API Netty dùng ByteBuf có reference count, tuân thủ quy tắc ownership và release của thư viện. Không giữ payload lâu hơn cần thiết và không tự release một buffer mà tầng khác vẫn sở hữu.

Backpressure chỉ có tác dụng khi được duy trì qua toàn bộ pipeline. Nếu một operator chuyển dữ liệu sang queue không giới hạn, hoặc handler nhận dữ liệu nhanh rồi ghi vào một cấu trúc giữ mọi phần tử, áp lực bộ nhớ vẫn tăng dù giao thức có REQUEST_N. Các operator buffer nên có kích thước tối đa và chính sách rõ ràng khi đầy: từ chối, drop theo nghiệp vụ hoặc ngắt stream.

## 5. Giới hạn của hệ điều hành

### File descriptor và socket

Trên Linux, mỗi socket TCP thường chiếm một file descriptor trong tiến trình. Kết nối RSocket vào, kết nối đi tới dịch vụ khác, file log, file cấu hình và các tài nguyên mở khác cùng dùng ngân sách descriptor. Khi chạm giới hạn nofile, server có thể không accept được kết nối mới hoặc không mở được tài nguyên cần thiết.

Kiểm tra giới hạn của tiến trình chạy ứng dụng, chẳng hạn ulimit -n, cấu hình service manager hoặc giới hạn của container runtime. Ngưỡng cần đủ cho số socket vào và ra cực đại dự kiến, cộng thêm descriptor cho log, file và phần dự phòng. Theo dõi số descriptor đang mở và cảnh báo trước khi tiến gần giới hạn. Không đặt giới hạn chỉ dựa trên số kết nối inbound nếu ứng dụng còn mở nhiều kết nối outbound.

### Ephemeral port, TIME_WAIT và conntrack

Khi client mở kết nối TCP outbound, hệ điều hành cấp một local ephemeral port cho tuple kết nối. Một client tạo quá nhiều kết nối ngắn tới cùng đích có thể cạn dải port khả dụng hoặc tạo nhiều socket ở trạng thái TIME_WAIT. NAT, firewall và conntrack của hạ tầng cũng có giới hạn riêng.

RSocket multiplexing và tái sử dụng kết nối dài hạn thường giúp giảm số socket outbound so với mở một kết nối cho từng yêu cầu. Theo dõi số kết nối outbound, phân bố trạng thái TCP, dải ip_local_port_range, bảng conntrack và số kết nối trên mỗi đích. Chỉ điều chỉnh sysctl sau khi đo được nút thắt và hiểu tác động tới toàn node; không dùng việc thay đổi TIME_WAIT như giải pháp mặc định cho thiết kế tạo kết nối quá nhiều.

### Thread và stack

Mỗi thread Java có stack native. Nếu tạo thread theo từng request hoặc từng stream, bộ nhớ stack và chi phí lập lịch sẽ tăng nhanh. RSocket và Reactor được thiết kế để multiplex nhiều tương tác trên một số ít event loop; số stream không nên được ánh xạ thành số thread.

Kiểm soát thread pool cho các tác vụ blocking và CPU-bound. Đặt giới hạn số thread, hàng đợi và chính sách từ chối cho từng pool. Thay đổi -Xss chỉ sau khi kiểm tra độ sâu stack của ứng dụng và kiểm thử; stack nhỏ hơn có thể gây StackOverflowError, còn stack quá lớn làm tăng bộ nhớ native khi số thread cao.

### Giới hạn CPU và container

Container có thể bị giới hạn CPU bằng quota hoặc cpuset. JVM và thư viện mạng cần được cấu hình theo số CPU mà tiến trình thực sự được cấp, không theo số core của máy host. CPU throttling có thể làm event loop trễ, keepalive timeout và độ trễ p99 tăng dù số request không đổi. Cần theo dõi CPU usage, throttling, run queue và độ trễ của event loop trong môi trường container thực tế.

## 6. Event loop, scheduler và concurrency

Event loop của Netty xử lý sự kiện I/O cho nhiều channel. Một event loop bị chặn có thể làm chậm tất cả channel được gán cho nó. Không chạy truy vấn đồng bộ, gọi HTTP blocking, thao tác file blocking, Thread.sleep() hoặc xử lý CPU nặng trực tiếp trên event loop.

Với công việc blocking, chuyển sang scheduler hoặc executor riêng có giới hạn số thread và queue. Với công việc CPU-bound, dùng pool có kích thước phù hợp CPU được cấp. boundedElastic có thể phù hợp cho một số tích hợp blocking, nhưng vẫn phải quan sát số thread, queue và thời gian chờ; một queue lớn chỉ trì hoãn lúc quá tải và làm tăng độ trễ. Với tải quan trọng, cân nhắc executor riêng để có ngân sách và chính sách từ chối rõ ràng.

Không nên tăng số event loop hoặc thread chỉ để xử lý triệu chứng độ trễ. Trước hết xác định event loop có bị block hay không, downstream có chậm hay không, queue có tăng hay không và CPU có bị throttling hay không. Tăng thread có thể làm tăng context switching, stack memory và tranh chấp tài nguyên.

Giữ concurrency ở từng tầng:

- Số stream đang hoạt động trên mỗi kết nối và mỗi tenant.
- Số handler đang thực thi trên instance.
- Số thao tác đồng thời tới database, cache và dịch vụ bên ngoài.
- Số tác vụ blocking hoặc CPU-bound trong từng executor.
- Số phần tử và byte đang chờ trong từng queue.

Giới hạn downstream thường thấp hơn khả năng nhận request của RSocket server. Ví dụ, nếu database chỉ chịu được một số truy vấn đồng thời nhất định, handler cần áp dụng giới hạn trước khi lấy kết nối DB. Nếu chỉ giới hạn tại database pool, hàng nghìn stream có thể chờ lấy connection và chiếm bộ nhớ trong thời gian dài.

## 7. Ước lượng năng lực và đặt ngưỡng

Không nên chọn giới hạn dựa trên một con số mặc định hoặc chỉ dựa vào số core. Hãy đo chi phí biên của một kết nối, một stream và một đơn vị công việc trên đúng phiên bản ứng dụng cùng cấu hình triển khai.

Một số quan hệ giúp ước lượng ban đầu:

**Số stream trung bình đang hoạt động** có thể ước lượng bằng định luật Little:

~~~text
số stream hoạt động ≈ tốc độ bắt đầu stream mỗi giây × thời gian sống trung bình của stream
~~~

Ví dụ, stream được tạo liên tục nhưng sống lâu sẽ làm số stream đồng thời tăng ngay cả khi tốc độ bắt đầu không quá cao. Với request-stream và request-channel, thời gian sống là yếu tố quan trọng; chỉ đo request/giây sẽ bỏ sót mức tiêu thụ tài nguyên.

**Ngân sách kết nối an toàn** bị giới hạn bởi thành phần nhỏ nhất trong các ngân sách sau:

~~~text
C_safe = min(C_file_descriptor, C_memory, C_transport, C_policy)
~~~

**Ngân sách stream an toàn** phụ thuộc vào bộ nhớ cho trạng thái và buffer, khả năng CPU, downstream và mục tiêu độ trễ:

~~~text
S_safe = min(S_memory, S_cpu, S_downstream, S_latency)
~~~

Đây là cách phân rã bài toán, không phải các giá trị có sẵn. Các thành phần phải được xác định từ phép đo và kiểm thử. Sau khi có ngưỡng lý thuyết, đặt giới hạn vận hành thấp hơn để chừa chỗ cho burst, phân bố tải lệch giữa replica, reconnect và biến động của dịch vụ phụ thuộc.

Quy trình sizing nên thực hiện theo thứ tự:

1. Xác định SLO về throughput, p95/p99 latency, tỷ lệ lỗi và thời gian phục hồi.
2. Đo baseline khi tải thấp: bộ nhớ nền, số thread, file descriptor, event loop và chi phí của một kết nối.
3. Tăng dần số kết nối trong khi giữ số stream thấp để đo chi phí riêng của socket.
4. Giữ số kết nối ổn định rồi tăng số stream, thời gian sống và kích thước payload để đo chi phí stream và buffer.
5. Tăng concurrency của handler và downstream để tìm điểm bắt đầu tăng queue, throttling, GC hoặc độ trễ.
6. Lặp lại theo nhiều tenant và phân bố tải lệch; xác minh một tenant không thể chiếm toàn bộ ngân sách.
7. Chọn giới hạn vận hành dưới điểm bão hòa, có dự phòng cho replica mất đi và tải phân bố không đều.

Khi tính năng chạy trên nhiều replica, tổng quota lý thuyết là tổng quota từng instance chỉ khi tải được phân phối tương đối đều và quota thực sự được thực thi tại từng instance. Nếu cần quota toàn hệ thống theo tenant, phải có cơ chế phối hợp hoặc phân bổ ngân sách giữa các replica. Nếu không, mỗi replica có thể cấp toàn bộ quota tenant và tổng mức sử dụng vượt kế hoạch.

## 8. Thiết kế và chạy load test

Load test cần mô phỏng hành vi của kết nối lâu dài và stream multiplex, không chỉ gửi request-response ngắn qua một client. Bộ kịch bản nên có:

- **Ramp-up:** tăng từ từ số client, kết nối và stream để xác định điểm bắt đầu suy giảm.
- **Steady state:** giữ tải mục tiêu đủ lâu để quan sát GC, direct memory, pool và queue sau khi hệ thống ổn định.
- **Burst:** tăng nhanh lưu lượng để kiểm tra quota, backpressure và phản hồi từ chối.
- **Long-lived stream:** giữ request-stream và request-channel mở lâu, gồm cả consumer đọc chậm.
- **Connection churn:** tạo và đóng kết nối liên tục, mô phỏng reconnect sau khi pod hoặc mạng bị gián đoạn.
- **Tenant skew:** một tenant gửi tải lớn trong khi nhiều tenant nhỏ vẫn cần được phục vụ.
- **Payload mix:** dùng payload nhỏ, lớn và phân bố kích thước gần thực tế; kiểm tra giới hạn frame.
- **Failure và cancellation:** hủy stream giữa chừng, ngắt client, làm downstream chậm hoặc lỗi và xác minh permit được giải phóng.
- **Transport thực tế:** kiểm thử đúng TCP hoặc WebSocket, TLS, load balancer, timeout và giới hạn container như môi trường production.

Trong suốt bài test, thu thập ít nhất:

| Nhóm | Chỉ số cần theo dõi |
| --- | --- |
| Kết nối | Kết nối active, kết nối mới/giây, reconnect, kết nối bị từ chối |
| Stream | Stream active theo loại và tenant, thời gian sống, stream bị cancel, stream bị từ chối |
| Xử lý | Throughput, concurrency handler, queue wait, tỷ lệ lỗi, retry |
| Độ trễ | p50, p95, p99 và thời gian xử lý của downstream |
| Bộ nhớ | Heap, GC pause, direct/native memory, RSS, byte đang đệm |
| Hệ điều hành | File descriptor, thread, socket state, ephemeral port và conntrack |
| Reactor/Netty | Event loop pending tasks, thời gian event loop bị block, allocator và buffer metrics |
| Container | CPU usage, CPU throttling, memory working set và số lần restart/OOM |

Một bài test đạt yêu cầu khi tải mục tiêu được duy trì trong SLO, bộ nhớ và số descriptor ổn định, queue không tăng liên tục, event loop không bị block kéo dài và quota từ chối đúng phạm vi. Khi một tenant vượt ngân sách, các tenant còn lại vẫn cần đạt mức dịch vụ đã cam kết. Sau burst, hệ thống phải trở lại trạng thái ổn định mà không cần restart.

Nên thử cả tình huống mất một replica. Tải chuyển sang các replica còn lại có thể khiến quota theo instance bị chạm sớm hơn dự kiến. Kiểm tra reconnect storm, phân bố lại kết nối dài hạn và hành vi của load balancer khi server drain hoặc khởi động lại.

## 9. Checklist trước khi đưa vào production

- [ ] Có giới hạn kết nối toàn instance và theo tenant/client.
- [ ] Có giới hạn stream active theo kết nối, tenant và instance.
- [ ] Có quota đồng thời cho handler và từng dịch vụ phụ thuộc.
- [ ] Có quota tốc độ và giới hạn số byte/phần tử trong queue.
- [ ] Tenant được xác định từ danh tính đã xác thực; quota được chia sẻ giữa các kết nối của cùng tenant.
- [ ] Permit được giải phóng khi complete, error và cancel.
- [ ] Backpressure được giữ xuyên suốt; không có buffer hoặc queue không giới hạn.
- [ ] Có ngân sách heap, direct/native memory và RSS phù hợp giới hạn container.
- [ ] Có giới hạn payload/frame và kiểm thử payload lớn.
- [ ] File descriptor, ephemeral port, conntrack và thread có đủ headroom.
- [ ] Event loop không thực hiện công việc blocking hoặc CPU nặng.
- [ ] Có metric, dashboard và cảnh báo cho connection, stream, memory, queue, event loop và OS.
- [ ] Load test bao gồm long-lived stream, tenant skew, burst, reconnect, cancellation và downstream chậm.
- [ ] Client có backoff và jitter khi bị từ chối; retry không tạo retry storm.
- [ ] Ngưỡng đã được kiểm tra khi mất replica và khi tải phân bố lệch.

## Kết luận

Khả năng multiplex của RSocket giúp dùng kết nối hiệu quả, nhưng không làm biến mất giới hạn của bộ nhớ, CPU, database hay hệ điều hành. Vận hành ổn định cần quota riêng cho socket, stream, công việc đồng thời, tốc độ và buffer; đồng thời áp dụng ngân sách công bằng theo tenant. Các ngưỡng cuối cùng phải xuất phát từ số liệu trên đúng môi trường triển khai và được xác nhận bằng load test có cả tải dài hạn lẫn tình huống quá tải.
