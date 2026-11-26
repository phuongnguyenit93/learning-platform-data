Một API đặt hàng Spring Boot gọi TaskExecutor để gửi email xác nhận; khi traffic tăng, tác vụ email chiếm hết worker của executor dùng chung và các công việc thanh toán nền bắt đầu trễ.
Nhóm triển khai ThreadPoolTaskExecutor với corePoolSize nhỏ và queueCapacity rất lớn; dù đã tăng maxPoolSize, số thread hoạt động vẫn gần mức core trong lúc hàng nghìn tác vụ chờ trong queue.
Một hệ thống báo cáo đặt queueCapacity bằng không để đẩy công việc trực tiếp cho thread pool; khi xuất hàng loạt báo cáo, executor từ chối tác vụ sớm hơn dự kiến dù CPU chưa sử dụng hết.
Đội vận hành đặt corePoolSize bằng số CPU cho workload gọi HTTP chậm; phần lớn worker bị chặn chờ mạng và throughput giảm trong khi mức sử dụng CPU thấp.
Một dịch vụ xử lý ảnh tăng maxPoolSize gấp nhiều lần số core; các tác vụ mã hóa ảnh tranh chấp CPU và thời gian hoàn tất trung bình lại tăng khi lượng thread lớn.
Nhóm công nghệ dùng một ThreadPoolTaskExecutor chung cho tác vụ gửi SMS và xử lý file lớn; những file vài GB làm queue tích tụ và thông báo bảo mật không được gửi đúng hạn.
Ứng dụng cấp voucher sử dụng CallerRunsPolicy khi executor đầy; request HTTP tự thực thi tác vụ cấp voucher kéo dài và p99 latency tăng mạnh vào giờ cao điểm.
Đội phát triển cấu hình AbortPolicy để báo quá tải; một endpoint đã trả mã thành công trước khi submit tác vụ mới và không biết công việc nền bị từ chối.
Một hệ thống tích hợp dùng DiscardPolicy để giảm tải; trong đợt khuyến mãi, hàng trăm tác vụ đồng bộ tồn kho biến mất mà không có exception hoặc nhật ký lỗi rõ ràng.
Nhóm chọn DiscardOldestPolicy cho queue thông báo; sự kiện thanh toán có trước bị loại để dành chỗ cho công việc mới, khiến một số hóa đơn không được gửi.
Ứng dụng định nghĩa nhiều TaskExecutor bean nhưng không cấu hình rõ executor mặc định; sau khi thêm thư viện mới, @Async được chạy trên executor khác với bản cấu hình đã kiểm thử.
Đội đặt tên bean taskExecutor cho xử lý báo cáo; các phương thức @Async khác cũng dùng pool này ngoài dự kiến và cùng tranh chấp worker khi phát sinh tải.
Một microservice cấu hình executor bằng ThreadPoolTaskExecutor nhưng quên kích hoạt vòng đời bean trong môi trường tự tạo; khi gọi submit, tác vụ không được chấp nhận như trong Spring context hoàn chỉnh.
Nhóm khai báo custom TaskExecutor chỉ dùng ở profile production; @Async chạy đúng ở test nhưng production sử dụng policy từ chối và thông số pool hoàn toàn khác.
Một dịch vụ sử dụng SimpleAsyncTaskExecutor cho mỗi request upload; số tác vụ song song tăng theo traffic và số thread tạo ra trở thành gánh nặng của hệ điều hành.
Đội đặt giới hạn concurrency cho SimpleAsyncTaskExecutor để tránh tạo quá nhiều task; khi đạt ngưỡng, thread gọi tác vụ bị chặn lâu khiến API đồng bộ chậm ngoài dự đoán.
Ứng dụng chuyển executor sang chế độ virtual thread trên Java 21; nhóm vẫn kỳ vọng tham số maxPoolSize giới hạn số tác vụ như thread pool cũ và tạo quá nhiều lời gọi database đồng thời.
Một job kiểm tra hóa đơn tạo thread riêng bằng new Thread thay vì dùng TaskExecutor Spring quản lý; khi ứng dụng shutdown, những tác vụ đang chạy không được quan sát hoặc đóng theo cùng vòng đời.
Nhóm dùng ExecutorService tự tạo trong một singleton bean và không dừng khi context đóng; sau triển khai nhiều phiên bản, tiến trình cũ vẫn giữ thread không mong muốn.
Ứng dụng có tên thread mặc định giống nhau trên nhiều pool; log lỗi từ xử lý đơn hàng và lập báo cáo bị trộn khiến đội hỗ trợ không phân biệt được nguồn công việc.
Đội vận hành muốn đánh giá độ bão hòa executor nhưng dashboard chỉ hiển thị số thread đang chạy; queue length và số tác vụ bị từ chối không có metric nên sự cố được phát hiện muộn.
Một ứng dụng đặt keepAliveSeconds rất thấp cho worker vượt core size; trong chuỗi traffic bùng nổ liên tiếp, thread bị tạo và hủy liên tục khiến latency dao động.
Nhóm dùng allowCoreThreadTimeOut để giảm tài nguyên lúc nhàn rỗi; tác vụ đầu tiên sau nhiều giờ yên lặng gặp độ trễ khởi động worker mà SLA chưa tính đến.
Dịch vụ đẩy dữ liệu lên cloud có queueCapacity không giới hạn; trong sự cố đối tác kéo dài, dữ liệu chờ chiếm heap và pod bị OOM trước khi đội vận hành thấy lỗi.
Đội phát triển dùng pool tách biệt cho tác vụ đọc và ghi nhưng cấu hình nhầm qualifier; một công việc ghi rất chậm vẫn vào pool phục vụ truy vấn khách hàng.
Một hệ thống tính điểm thưởng sử dụng TaskExecutor.execute và ném RuntimeException trong Runnable; request tạo đơn không nhận được exception nhưng log nền chứa lỗi mà monitoring không bắt.
Nhóm chuyển sang submit để lấy Future từ executor; exception được giữ trong kết quả Future nhưng không ai gọi get nên lỗi xử lý biến mất khỏi nhật ký nghiệp vụ.
Ứng dụng phân phối 10.000 tác vụ con qua TaskExecutor; mỗi tác vụ đều chờ Future của tác vụ khác trong cùng pool nhỏ và toàn bộ tiến trình bị kẹt.
Đội dùng một worker để tải file rồi chờ hai bước xử lý phụ cũng chạy trên cùng executor; khi pool đầy, công việc chính chờ mãi dù queue vẫn có nhiều task chưa được xử lý.
Nhóm đặt thời gian chờ của HTTP gateway ngắn hơn thời gian nằm trong executor queue; client retry tạo yêu cầu mới trong khi tác vụ của yêu cầu cũ vẫn chờ để chạy.
Một API gửi yêu cầu xây PDF nền, rồi trả 202 Accepted; khi pool quá tải, nhiệm vụ không vào được hàng đợi nhưng response vẫn nói đã tiếp nhận thành công.
Đội công nghệ tăng số pod Spring Boot để giảm queue delay; các pod cùng mở pool lớn khiến số connection đến một database dùng chung vượt giới hạn.
Ứng dụng phân chia batch thành nhiều Runnable và không giới hạn số task chờ; dù mỗi task rất nhỏ, overhead lưu và lập lịch task chiếm đáng kể thời gian xử lý.
Nhóm chạy một tác vụ CPU-bound trong pool mặc định vốn phục vụ blocking I/O; kết quả load test cho thấy các request ít CPU vẫn chậm do tranh chấp cùng worker.
Một endpoint hỗ trợ hủy yêu cầu báo cáo khi người dùng thoát trang; Future bị cancel nhưng tác vụ dùng API không phản ứng với interrupt vẫn tiếp tục ghi file lớn.
Đội triển khai shutdownNow khi context kết thúc; các Runnable bị interrupt giữa lúc ghi file khiến hệ thống lưu các báo cáo chưa hoàn chỉnh mà không có trạng thái bù.
Ứng dụng bật graceful shutdown và cho phép executor chờ tác vụ xong; thời hạn Kubernetes terminationGracePeriodSeconds ngắn hơn thời gian chờ nên process bị kill khi vẫn còn việc.
Nhóm đặt awaitTerminationSeconds dài cho ứng dụng xử lý realtime; một worker giữ lock vô thời hạn làm rollout kẹt và nhiều pod cũ không thể thoát.
Một service ngừng nhận request mới trong graceful shutdown nhưng TaskExecutor vẫn nhận tác vụ từ listener nội bộ; queue không giảm như dự toán trước khi container bị dừng.
Đội triển khai tăng queueCapacity giữa một đợt tải mà không restart; cấu hình executor đang hoạt động không tự thay đổi cấu trúc hàng đợi như ý định của đội vận hành.
Một ứng dụng xuất trace theo thread name rồi đổi pool khi runtime; cùng giao dịch trải qua nhiều worker và dashboard hiểu sai thành nhiều giao dịch độc lập.
Nhóm tích hợp @Async lên method gửi email nhưng chưa bật @EnableAsync trong cấu hình Spring; email vẫn được gửi trên thread request và thời gian phản hồi không giảm.
Ứng dụng gắn @Async lên private method trong service đặt hàng; lời gọi vẫn chạy đồng bộ vì method không được AOP proxy intercept theo cách đội phát triển dự kiến.
Đội phát triển gọi method @Async từ một method khác trong cùng bean; self-invocation bỏ qua proxy và việc tính toán nặng vẫn giữ thread HTTP.
Nhóm khai báo @Async trên một class có nhiều method nghiệp vụ; một method cần chạy đồng bộ cũng bất ngờ được đưa vào executor sau khi đổi annotation ở cấp lớp.
Ứng dụng có service được tạo bằng new trong đoạn bootstrap; phương thức mang @Async không chạy qua Spring bean nên không có tác dụng như khi dùng dependency injection.
Đội công nghệ đặt @Async("mailExecutor") cho email, nhưng bean executor được đổi tên khi refactor; chức năng gửi email lỗi trong lần xử lý đầu ở production.
Nhóm cài đặt nhiều cấu hình AsyncConfigurer ở các module; app khởi động với executor mặc định không đúng và nhiệm vụ dự kiến ưu tiên cao bị đưa vào pool batch.
Một service dùng @Async trên method trả void rồi gặp exception khi gọi nhà cung cấp SMS; client đã nhận thành công và không có Future để kiểm tra việc gửi thất bại.
Đội phát triển viết AsyncUncaughtExceptionHandler chỉ log message lỗi; khi exception xảy ra, thông tin orderId và tenantId không có trong log để xử lý bù.
Ứng dụng dùng @Async method trả CompletableFuture<Receipt>; một caller bỏ qua giá trị trả về và mất thông tin lỗi khi tạo hóa đơn thất bại.
Nhóm gọi @Async method trả Future rồi lập tức gọi get trong controller; HTTP request vẫn chờ toàn bộ thời gian xử lý nên tính năng không đem lại phản hồi nhanh mong muốn.
Đội triển khai đặt @Async method thực hiện ghi hai database; khi một database lỗi, caller không có cơ chế đối chiếu trạng thái từng nguồn đã được ghi.
Một API tính điểm rủi ro chạy @Async và trả CompletableFuture; khi executor quá tải, việc submit thất bại ngay trong thread caller trước khi có kết quả bất đồng bộ như nhóm tưởng.
Nhóm gắn @Async vào listener ứng dụng sau khi publish event; hai request có cùng customerId được xử lý song song và listener cập nhật thứ tự sự kiện ngược nhau.
Ứng dụng có @Async method tham chiếu một request-scoped bean; worker chạy sau khi request đã kết thúc nên gặp lỗi scope không hoạt động.
Đội phát triển đọc HttpServletRequest bên trong @Async method; khi thread nền bắt đầu, request object không còn vòng đời như lúc controller đang chạy.
Nhóm giữ SecurityContextHolder trong ThreadLocal để lấy userId; sau khi @Async chuyển sang thread pool, tác vụ audit không thấy danh tính người dùng hoặc thấy ngữ cảnh không phù hợp.
Ứng dụng dùng InheritableThreadLocal để chuyển tenantId sang @Async; thread pool tái sử dụng worker cũ khiến một số tác vụ giữ tenantId của request trước.
Đội sử dụng DelegatingSecurityContextAsyncTaskExecutor cho tác vụ liên quan tài khoản; một code path gọi executor gốc nên không truyền được cùng security context.
Nhóm cấu hình TaskDecorator để chép MDC sang thread mới; decorator không được áp dụng ở executor khác khiến traceId biến mất ở một nửa luồng xử lý.
Một dịch vụ gắn correlation ID bằng MDC nhưng không xóa trạng thái khi worker kết thúc; task kế tiếp tái sử dụng thread và log nhầm mã request trước.
Ứng dụng xử lý đơn đa ngôn ngữ truyền LocaleContext từ controller; email @Async dùng locale mặc định và gửi bằng ngôn ngữ không đúng với lựa chọn khách.
Đội phát triển lưu transaction ID trong ThreadLocal của request; @Async ghi một bảng phụ bằng transaction riêng nhưng audit ghi nhầm rằng hai bước cùng thuộc một transaction.
Nhóm gọi repository JPA bên trong @Async sau khi controller transaction kết thúc; entity lazy được chuyển thẳng sang worker và ném LazyInitializationException khi đọc association.
Một API đặt hàng gọi @Async method được đánh dấu @Transactional; người dùng thấy dữ liệu chính đã commit nhưng dữ liệu phụ chỉ xuất hiện khi transaction của worker hoàn tất.
Đội mong @Async kế thừa transaction từ caller; một exception trong worker không rollback bản ghi đã commit trong thread request nên dữ liệu ở hai bảng lệch nhau.
Nhóm kết hợp @Transactional và @Async trên cùng logic thanh toán; thứ tự proxy và ngữ cảnh thực thi không phù hợp với giả định nghiệp vụ rằng toàn bộ workflow có một transaction duy nhất.
Ứng dụng có hai @Async method ghi cùng một row theo dữ liệu đọc trước; lần ghi sau ghi đè thông tin của lần trước mà test tuần tự không phát hiện.
Đội vận hành phát hiện @Async method gọi endpoint bên ngoài nhưng không có connect timeout; vài worker bị giữ vô hạn và queue đầy trong sự cố mạng.
Nhóm tạo một CompletableFuture bằng supplyAsync mà không truyền Executor Spring; nhiệm vụ chạy trên ForkJoinPool.commonPool thay vì pool đã được giám sát và giới hạn.
Ứng dụng gọi thenApply trên CompletableFuture và thực hiện phép tính CPU nặng; callback chạy trên thread hoàn thành future trước đó, làm worker I/O bị chặn ngoài kế hoạch.
Đội dùng thenApplyAsync để tách giai đoạn xử lý nhưng không cung cấp Executor; số tác vụ trong common pool tăng mà dashboard ThreadPoolTaskExecutor không thể hiện.
Nhóm có ba CompletableFuture truy vấn thông tin khách rồi dùng allOf; một future thất bại nhưng hai lời gọi bên ngoài đã gây side effect trước khi kết quả tổng được đánh dấu lỗi.
Ứng dụng dùng anyOf để chọn phản hồi nhanh nhất trong hai nhà cung cấp; lời gọi còn lại không được hủy và vẫn chiếm connection pool dù không cần kết quả.
Đội triển khai thenCombine cho hai Future phụ thuộc hai hệ thống; khi một hệ thống chậm vô hạn, response tổng không hoàn tất dù hệ thống còn lại đã có dữ liệu.
Nhóm xử lý lỗi bằng exceptionally và trả dữ liệu mặc định; API hiển thị trạng thái thành công nhưng không còn dấu hiệu nhà cung cấp giá đang ngừng hoạt động.
Ứng dụng dùng handle để chuyển exception thành kết quả dự phòng; một lỗi phân quyền cũng được coi như timeout nên client nhận dữ liệu không đúng quyền truy cập.
Đội phát triển xâu chuỗi thenApply để gọi một API trả CompletableFuture; kết quả trở thành future lồng nhau và bước sau chạy trước khi dữ liệu nghiệp vụ thực sự sẵn sàng.
Nhóm dùng thenCompose để nối hai thao tác cần kết quả của nhau; khi lần gọi thứ hai thất bại, log chỉ ghi tên chain mà không giữ correlation ID của request đầu.
Ứng dụng dùng CompletableFuture.join trong luồng request để gom kết quả; khi tác vụ con lỗi, exception được bọc thành CompletionException khiến exception handler hiện tại phân loại sai.
Đội dùng CompletableFuture.get với timeout cho một truy vấn chậm; future báo timeout nhưng thao tác JDBC trong worker có thể vẫn tiếp tục giữ connection sau đó.
Nhóm đặt orTimeout trên CompletableFuture tạo file; client nhận timeout nhưng task chưa bị hủy và vẫn ghi file lên storage khi người dùng đã gửi yêu cầu khác.
Ứng dụng dùng completeOnTimeout với response dự phòng; kết quả tác vụ gốc hoàn tất muộn và một callback khác vẫn thực hiện ghi dữ liệu dù response đã dự phòng.
Đội gọi cancel(true) cho CompletableFuture khi khách ngắt kết nối; thư viện HTTP bên dưới không dừng cuộc gọi đang chạy và tiếp tục tiêu tốn tài nguyên.
Nhóm tạo một loạt future bằng supplyAsync rồi chờ allOf; một lỗi OutOfMemoryError hoặc rejected task lúc tạo khiến một phần tác vụ đã bắt đầu nhưng danh sách kết quả không đầy đủ.
Ứng dụng chia công việc xuất báo cáo thành 2.000 future nhỏ; mỗi future giữ một phần dữ liệu lớn và bộ nhớ bị tiêu thụ trước khi các kết quả được ghép.
Đội phát triển sử dụng một Future để lưu trạng thái xử lý thanh toán; sau khi pod restart, CompletableFuture chỉ tồn tại trong bộ nhớ và không thể truy vấn tiến độ tác vụ cũ.
Nhóm cần xử lý nhiều CompletableFuture cùng cập nhật tổng điểm; biến tổng dùng chung không bảo đảm đồng bộ nên kết quả thấp hơn số điểm đã tính.
Ứng dụng gửi 100 lời gọi REST song song qua CompletableFuture; HTTP client connection pool chỉ có 10 kết nối và nhiều future chờ nhau thay vì cải thiện thông lượng.
Đội gọi future kết quả của một job trong chính worker dùng pool một thread; worker bị block chờ job khác đang chờ lịch chạy trên cùng pool gây deadlock.
Nhóm chạy các future truy vấn cache trên virtual threads nhưng một bước đồng bộ hóa rộng khóa các phép tính; throughput không cải thiện dù số task đồng thời tăng.
Ứng dụng cần giữ thứ tự kết quả khuyến mãi theo input; các future hoàn tất không theo thứ tự khiến response ghép theo thời điểm hoàn thành và mã ưu đãi bị gán nhầm khách.
Đội ghi trạng thái từng bước vào mutable Map dùng chung giữa callback Future; khi nhiều callback cùng thêm key, kết quả và exception xuất hiện không ổn định.
Nhóm dùng CompletableFuture.runAsync để ghi audit nền; không có người chờ future và lỗi ghi audit không được phát hiện cho tới đợt đối soát cuối tháng.
Ứng dụng thêm timeout ở tầng CompletableFuture nhưng không có timeout của HTTP client; số lời gọi đã báo timeout vẫn giữ socket gây cạn tài nguyên sau nhiều lượt thử lại.
Đội xử lý retry bằng cách tạo CompletableFuture mới sau mỗi lỗi; trong đợt sự cố downstream, số lời gọi đang chạy tăng mạnh và gây bão tải khi dịch vụ hồi phục.
Nhóm gửi một request gồm nhiều future lấy dữ liệu từ ba backend; kết quả cuối cùng ghi sai tenant vì một callback đọc ngữ cảnh người dùng từ ThreadLocal không được truyền.
Ứng dụng kiểm tra Future.isDone để suy ra giao dịch đã thành công; trạng thái đã hoàn tất cũng có thể là hoàn tất với exception nên báo cáo kết quả không chính xác.
Đội tạo CompletableFuture trong một bean singleton và dùng lại cho nhiều request; request đầu hoàn thành future khiến những request sau nhận dữ liệu cũ của khách trước.
Nhóm dùng whenComplete để ghi metric; callback đo được thời gian hoàn tất nhưng một exception trong callback làm các bước phụ thuộc bị đánh dấu lỗi dù dữ liệu gốc hợp lệ.
Ứng dụng dùng CompletableFuture.allOf để tổng hợp nhiều dịch vụ; một future bị hủy giữa chừng và endpoint chưa có cách phân biệt hủy chủ động với lỗi hệ thống.
Đội chạy batch với CompletableFuture và một executor dùng queue nhỏ; chỉ một phần future được tạo thành công trước khi TaskRejectedException, trong khi request vẫn đã ghi lịch sử công việc.
Nhóm nhận callback HTTP thành công rồi publish kết quả cho future; request chờ phía client đã hết hạn và object callback bị giữ lại làm bảng trạng thái trong bộ nhớ ngày càng lớn.
Một hệ thống tài chính phải bảo vệ khóa tài khoản khi chạy callback Future; hai bước đọc-sửa-ghi riêng biệt có thể xen kẽ với callback khác dù từng thao tác map thread-safe.
Ứng dụng định nghĩa @Scheduled(fixedRate) cho job cập nhật tỷ giá; tác vụ kéo dài hơn chu kỳ và các lượt chạy bị trễ liên tục, khiến lịch thực tế lệch so với nhịp cấu hình.
Đội chuyển job từ fixedRate sang fixedDelay sau một lần chậm; thời điểm chạy tính từ lúc tác vụ trước kết thúc nên số lần đồng bộ mỗi giờ khác dự toán.
Nhóm đặt cron chạy gửi email tổng kết lúc 00:00; server chạy ở timezone UTC trong khi người dùng muốn bắt đầu ngày theo múi giờ Việt Nam.
Ứng dụng xuất báo cáo lúc 02:30 hằng ngày theo một timezone có daylight saving time; vào ngày chuyển giờ, lịch cron có thể bỏ qua hoặc chuyển thời điểm dự định.
Đội vận hành có ba replica ứng dụng cùng bật @Scheduled xử lý đối soát; cả ba pod chạy job mỗi đêm và ghi trùng báo cáo vì lịch Spring chỉ nằm trong từng tiến trình.
Nhóm triển khai Spring scheduling nhưng quên @EnableScheduling trong cấu hình production; endpoint HTTP hoạt động bình thường còn tác vụ dọn dữ liệu không bao giờ chạy.
Ứng dụng tạo bean có method @Scheduled trong một class không được component scan; đội hỗ trợ chỉ thấy không có bản ghi log của job mà không phát hiện thiếu đăng ký bean.
Đội đặt hai annotation @Scheduled cho cùng method để chạy hai khung giờ; một số lần chạy gần nhau có thể chồng lấp và cùng cập nhật dữ liệu ngày hiện tại.
Nhóm có nhiều @Scheduled job sử dụng scheduler mặc định chỉ một thread; tác vụ chốt sổ kéo dài hai giờ khiến job dọn phiên và cập nhật cache không chạy đúng giờ.
Ứng dụng cấu hình ThreadPoolTaskScheduler poolSize lớn để chạy job song song; hai job cùng xóa file tạm đang dùng và một báo cáo khách hàng bị hỏng.
Đội kỹ thuật dùng @Scheduled(cron) cho thao tác gửi hàng chục nghìn email; một kỳ chạy kéo dài sang kỳ tiếp theo và trạng thái gửi bị lặp giữa hai lượt.
Nhóm đặt initialDelay ngắn cho job làm sạch dữ liệu; khi Spring context vừa khởi động, database migration chưa sẵn sàng và job chạy lỗi ngay lần đầu.
Ứng dụng có một @Scheduled method dùng dữ liệu cache được tạo bởi event khởi động; lần chạy đầu xảy ra trước khi cache hoàn tất và ghi dữ liệu thiếu.
Đội sử dụng cron expression nhập từ cấu hình; một bản deploy mang giá trị không hợp lệ làm bean scheduling không được khởi tạo và dịch vụ không hoàn thành startup.
Nhóm thay cron qua môi trường cấu hình nhưng không restart ứng dụng; lịch đã đăng ký vẫn hoạt động theo giá trị ban đầu khiến job không chạy vào khung giờ mới.
Ứng dụng cần tạm dừng một job khi bảo trì; cờ feature flag đổi ở runtime nhưng method @Scheduled vẫn được scheduler kích hoạt trong mọi chu kỳ.
Đội cho phép người quản trị tạo lịch đồng bộ dữ liệu động; các Trigger được đăng ký nhiều lần sau khi cấu hình cập nhật khiến một job thực thi trùng.
Nhóm dùng SchedulingConfigurer để cấu hình task registrar; một job đã có annotation @Scheduled lại được đăng ký thủ công và chạy hai lần theo cùng lịch.
Ứng dụng có cron chạy ngày cuối tháng để chốt hóa đơn; cấu hình biểu thức không diễn tả được tất cả ngày đặc biệt mà nhóm nghiệp vụ mong đợi.
Đội triển khai cron job có thời gian chờ phân tán qua nhiều ngày lễ; khi một lần chạy bị lỗi, lần chạy lịch tiếp theo vẫn bắt đầu mà không biết công việc trước chưa hoàn tất.
Nhóm gắn @Async lên @Scheduled method để job không giữ scheduler thread; mỗi tick tạo một tác vụ mới và các công việc kéo dài chồng lấp, vượt giới hạn kết nối database.
Ứng dụng dùng fixedDelay cho tác vụ đã chuyển sang @Async; scheduler method trả ngay sau submit nên khoảng nghỉ thực tế không còn tính từ lúc toàn bộ công việc nền kết thúc.
Đội có @Scheduled method trả CompletableFuture nhưng không theo dõi kết quả; job ném lỗi bên trong future mà lịch chạy tiếp như thể chu kỳ trước thành công.
Nhóm định nghĩa job xuất dữ liệu có lock Java synchronized để tránh chồng lấp; khi triển khai nhiều pod, mỗi pod có lock riêng nên xuất hai bản báo cáo cùng thời điểm.
Ứng dụng dùng Spring @Scheduled để thực thi thao tác mang tính độc quyền; một lần rolling update khiến pod cũ và pod mới cùng chạy job trong khoảng giao nhau.
Đội phát triển dùng scheduleAtFixedRate với khoảng lặp rất ngắn; khi hệ thống quá tải, các đợt chạy bị dồn lại và tiêu thụ phần lớn CPU cho tác vụ nền.
Nhóm vận hành yêu cầu job cập nhật tỷ giá chỉ chạy trong giờ giao dịch; máy chủ deploy ở vùng có timezone khác khiến cron chạy ngoài thời gian cho phép.
Ứng dụng có công việc tạo báo cáo dùng CronTrigger; lần chạy bị trễ do hệ thống ngừng lâu, nhóm nghiệp vụ tưởng mọi kỳ đã lỡ sẽ tự được thực thi bù.
Đội phát triển thử lịch @Scheduled bằng cách gọi thẳng method; bộ test không phát hiện cron sai timezone hoặc không có TaskScheduler trong context thật.
Nhóm dùng TaskScheduler.schedule với ScheduledFuture để lên lịch hủy session; sau khi restart pod, các future đã lên lịch trong bộ nhớ biến mất và session không được hủy theo thời điểm dự kiến.
Ứng dụng đăng ký timer dọn tệp từ nhiều request; không có cách quản lý và hủy các ScheduledFuture cũ nên hàng nghìn timer tồn tại dù tệp đã bị xóa.
Đội đặt thời gian chạy cho ScheduledFuture dựa trên đồng hồ hệ thống; khi thời gian máy chủ nhảy do đồng bộ NTP, kết quả thực thi bị lệch với deadline nghiệp vụ.
Nhóm sử dụng ThreadPoolTaskScheduler để chạy job gửi email và cleanup; khi cleanup bị chặn I/O, những lịch gửi quan trọng bị lùi dù các request vẫn trả lời nhanh.
Ứng dụng gửi event mỗi giây theo @Scheduled nhưng không thể kết nối broker trong một khoảng; lỗi được ghi log nhưng lần sau vẫn chạy mà không có dữ liệu của những lần thất bại.
Đội đổi số thread scheduler khi tăng số job; một task mutable được lập lịch đồng thời trên nhiều thread và dữ liệu trạng thái trong bean bị hỏng.
Nhóm xây job tổng hợp hóa đơn chỉ tính theo LocalDate.now; khi scheduler chạy chậm qua nửa đêm, kỳ dữ liệu được tổng hợp không còn trùng kỳ đã lên lịch.
Ứng dụng đặt cron expression để chạy mỗi thứ Hai; vào ngày lễ công ty muốn bỏ qua nhưng cơ chế lịch hiện không có ngữ cảnh lịch nghiệp vụ nên vẫn cập nhật dữ liệu.
Đội phát triển cấu hình scheduled job cho mỗi tenant bằng cách tạo bean động; tenant bị vô hiệu hóa nhưng tác vụ đã lên lịch vẫn tiếp tục truy vấn cơ sở dữ liệu.
Nhóm ghi timestamp bắt đầu job nhưng không ghi thời điểm kết thúc; những chu kỳ @Scheduled thất bại bị dashboard tính là đã xử lý dù kết quả chưa commit.
Ứng dụng có một job phát lại message lỗi; retry lặp lại theo lịch mà không phân biệt lỗi vĩnh viễn, dẫn tới cùng poison message được xử lý bất tận.
Đội dùng cron cho job dọn dữ liệu có deadline gắt; khi DST hoặc timezone thay đổi, thời gian thực thi khác lịch pháp lý mà nhóm tuân thủ đã quy định.
Nhóm chạy ứng dụng có scheduler mặc định trong test nhưng production cấu hình nhiều scheduler; thứ tự và tính song song giữa các job thay đổi làm lộ race condition.
Ứng dụng khởi động trên Java 21 với virtual threads cho @Async; mỗi tác vụ có thread riêng nhưng database connection pool chỉ có 20 kết nối nên hàng nghìn tác vụ cùng chờ.
Đội chuyển từ ThreadPoolTaskExecutor sang SimpleAsyncTaskExecutor bật virtual threads; giới hạn tối đa tác vụ đang xử lý trước đây không còn do pool size chi phối.
Nhóm dùng virtual threads cho tác vụ gọi HTTP blocking; hệ thống chịu được nhiều tác vụ chờ nhưng API đối tác chỉ cho phép 100 kết nối đồng thời và trả 429 hàng loạt.
Ứng dụng gửi SMS với một virtual thread cho mỗi khách hàng; số lời gọi tăng nhanh làm cạn quota và khiến thông báo bảo mật bị chậm dù thread rẻ hơn platform thread.
Đội vận hành bật virtual threads trong cấu hình Spring Boot; một thư viện bên thứ ba dùng synchronized quanh I/O chậm trên Java 21 khiến carrier threads bị pin và throughput giảm.
Nhóm chuyển một job CPU-bound sang virtual threads; độ trễ tính toán không cải thiện vì số CPU core vẫn là giới hạn xử lý tác vụ nặng.
Ứng dụng có nhiều tác vụ dùng ThreadLocal chứa object lớn; khi tạo số lượng virtual threads rất cao, bộ nhớ dùng cho dữ liệu theo thread vượt dự toán.
Đội đặt pool of virtual threads để tái sử dụng nhằm tiết kiệm tạo thread; mô hình cấp virtual thread theo task và giả định pool truyền thống không còn phù hợp với thiết kế này.
Nhóm triển khai virtual threads trong một service JPA; nhiều thread có thể cùng thực thi nhưng EntityManager và transaction context không thể chia sẻ trực tiếp giữa các nhiệm vụ.
Ứng dụng dùng virtual threads cho mọi request và tăng số lượng request song song; connection pool Redis, MongoDB và PostgreSQL vẫn có giới hạn nhỏ nên queue chờ chuyển sang các downstream.
Đội bật spring.threads.virtual.enabled trên ứng dụng Boot mới; cấu hình cùng tên không có hiệu lực ở một phiên bản ứng dụng khác và hành vi triển khai giữa hai cụm lệch nhau.
Nhóm vận hành dùng virtual-thread-per-task executor nhưng metric chỉ đo active platform threads; dashboard hiển thị tải thấp dù hàng nghìn tác vụ đang chờ I/O.
Ứng dụng tạo thread dump khi sự cố virtual threads; đội hỗ trợ dùng quy trình đọc dump truyền thống nên khó phân biệt hàng nghìn task đang chờ lock, I/O hay semaphore.
Đội chạy @Scheduled job trên scheduler dùng virtual threads; khi mọi thread còn lại là daemon hoặc không có cơ chế giữ tiến trình hoạt động phù hợp, ứng dụng nền có thể kết thúc ngoài ý muốn.
Nhóm chuyển scheduler sang virtual-thread-friendly implementation nhưng giữ logic fixedDelay; một tác vụ chậm làm lịch khác bị trễ vì đặc điểm bộ điều phối không giống cách pool cũ chia việc.
Ứng dụng dùng ThreadLocal để lưu tenantId trong các virtual threads; mỗi tác vụ mới không tự nhận thông tin context từ request hiện tại và truy vấn dùng tenant mặc định.
Đội dùng InheritableThreadLocal cho audit trên virtual thread; task được tạo ở một ngữ cảnh hệ thống không mong đợi nên danh tính người dùng khác với request đã kích hoạt.
Nhóm phát triển giữ một lock lớn quanh vùng truy cập database; sau khi chuyển sang virtual threads, lượng tác vụ chờ lock tăng trong khi throughput hầu như không đổi.
Ứng dụng chạy nhiều virtual threads cùng gọi driver cũ dùng blocking synchronization; thời gian chờ bị dồn lên carrier threads và latency tăng mạnh khi traffic đột biến.
Đội sử dụng một Semaphore để bảo vệ lời gọi đến API ngoài; khi khách hủy request, virtual thread vẫn chờ permit và không có cơ chế rõ ràng để ngừng công việc quá hạn.
Nhóm mở hàng chục nghìn virtual threads để xử lý các file upload; dữ liệu giữ trong mỗi task lớn khiến heap bị chiếm dù chi phí stack của thread thấp.
Ứng dụng đưa xử lý mã hóa CPU-bound vào virtual-thread executor cùng các thao tác I/O; tác vụ mã hóa vẫn cạnh tranh CPU và làm deadline của những yêu cầu quan trọng bị trễ.
Đội vận hành xây chỉ số hiệu năng theo thread count; sau khi dùng virtual threads, mối liên hệ giữa số thread và dung lượng bộ nhớ khác trước nên cảnh báo quá tải không kích hoạt.
Nhóm thiết kế timeout cho virtual-thread task khi đợi lock; việc interrupt không được thư viện đồng bộ cũ xử lý như kỳ vọng và tiến trình vẫn giữ tài nguyên.
Ứng dụng sử dụng virtual threads cùng ThreadPoolTaskExecutor truyền thống ở hai module; TaskDecorator và cách truyền MDC không đồng nhất làm trace của workflow bị tách.
Đội QA benchmark virtual threads chỉ bằng I/O giả lập; production có JDBC, thư viện đồng bộ hóa và remote calls thực nên số carrier bị pin và chi phí chờ khác xa kết quả test.
Nhóm chuyển phần gửi email sang virtual threads nhưng chưa giới hạn số email đang chờ; một sự cố mail server tạo rất nhiều task và tài nguyên phụ trợ khác bị cạn.
Ứng dụng định nghĩa @Async trên bean singleton giữ biến currentUser mutable; hai request cùng chạy dẫn tới email của khách A được gửi kèm thông tin khách B.
Đội phát triển dùng ArrayList làm buffer kết quả trong một singleton service; nhiều @Async worker cùng thêm dữ liệu gây mất phần tử hoặc lỗi khi duyệt.
Nhóm lưu trạng thái tổng doanh thu vào một trường long trong singleton; các lần tăng từ nhiều task chồng nhau và kết quả cuối nhỏ hơn số tiền đã ghi trong database.
Ứng dụng đánh dấu biến trạng thái bằng volatile để an toàn concurrency; thao tác đọc-sửa-ghi nhiều bước vẫn bị race và tổng số tác vụ hoàn tất bị tính thiếu.
Đội sử dụng AtomicInteger để cấp số thứ tự trong một pod; sau khi tăng lên nhiều replica, hai pod vẫn phát số trùng vì bộ đếm chỉ tồn tại trong bộ nhớ mỗi tiến trình.
Nhóm dùng ConcurrentHashMap lưu quota theo khách; hai thao tác kiểm tra rồi cập nhật riêng lẻ không nguyên tử và cho phép vượt hạn mức dưới tải đồng thời.
Ứng dụng chứa SimpleDateFormat trong một singleton bean được nhiều executor worker sử dụng; định dạng ngày đôi khi sai dù request không có ngoại lệ rõ ràng.
Đội lưu cache mutable HashMap trong bean shared; một scheduled job thay dữ liệu trong lúc controller duyệt map làm request thất bại không ổn định.
Nhóm dùng synchronized trên method xử lý tất cả tenant; chỉ một tenant gửi công việc chậm cũng chặn các tenant khác và làm tăng thời gian chờ toàn hệ thống.
Ứng dụng có tác vụ A giữ khóa Order rồi chờ khóa Inventory, trong khi tác vụ B giữ Inventory rồi chờ Order; khi tải cao hai luồng tạo deadlock và dừng xử lý.
Đội phát triển nhận lock nhưng có nhánh exception không release; sau sự cố ngắn, mọi task khác chờ lock và queue executor tăng liên tục.
Nhóm dùng ReentrantReadWriteLock cho cache cấu hình; một scheduler liên tục đọc trong khi yêu cầu cập nhật cần write lock và không thể áp bản cấu hình mới đúng hạn.
Ứng dụng dùng CountDownLatch chờ ba tác vụ nền trước khi trả response; một nhánh xử lý lỗi không đếm xuống khiến request treo đến khi gateway timeout.
Đội điều phối nhiều job bằng CyclicBarrier; một worker thất bại giữa chừng làm các worker khác chờ và không thể kết thúc batch theo SLA.
Nhóm dùng Phaser để phối hợp các phần việc xuất báo cáo; một tác vụ không deregister khi bị hủy khiến pha tiếp theo không bao giờ bắt đầu.
Ứng dụng xử lý một file theo nhiều luồng và dùng mutable HashSet lưu ID đã xử lý; cùng một ID có thể vượt qua kiểm tra đồng thời và được ghi hai lần.
Đội phát triển tối ưu bằng cách chia một JDBC Connection cho nhiều CompletableFuture; các thao tác SQL xen kẽ và trạng thái giao dịch trở nên khó dự đoán.
Nhóm sử dụng một EntityManager JPA được giữ trong singleton service; nhiều @Async method dùng chung session và gặp lỗi trạng thái managed entity hoặc concurrency.
Ứng dụng chia sẻ một mutable DTO giữa các listener đồng thời; listener kiểm tra dữ liệu đọc được trạng thái trung gian chưa hoàn chỉnh của listener cập nhật.
Đội thực hiện optimistic locking khi hai tác vụ cập nhật cùng một entity; TaskExecutor tự động retry sau exception nhưng sử dụng lại entity stale và lỗi lặp.
Nhóm chạy job dọn cache và request đọc cache cùng lúc; dữ liệu bị xóa giữa bước kiểm tra và lấy giá trị nên controller phát sinh NullPointerException.
Ứng dụng dùng @Async để trích xuất thông tin người dùng và cập nhật session; session đã hết hạn khi worker bắt đầu nhưng tác vụ vẫn ghi thông tin nhạy cảm vào cache.
Đội xây kiểm tra quyền dựa vào SecurityContext trong listener đồng thời; khi context bị truyền sai, tác vụ nền đọc thông tin tenant khác mà audit không thể giải thích.
Nhóm có executor riêng cho công việc ưu tiên cao nhưng pool dùng chung connection database; tác vụ batch vẫn làm pool JDBC cạn và thao tác ưu tiên bị chậm.
Ứng dụng sử dụng retry kết hợp timeout cho tác vụ gửi yêu cầu đối tác; mỗi retry tạo task mới dù task trước chưa kết thúc, dẫn tới cùng giao dịch được gửi nhiều lần.
Đội quản trị dùng Circuit Breaker cho các HTTP call trong @Async; circuit mở nhanh nhưng queue trước executor vẫn giữ hàng nghìn công việc không còn ý nghĩa.
Nhóm đẩy công việc lâu vào executor nội bộ để tránh giữ request thread; node crash làm công việc mất hoàn toàn vì không có queue bền vững hoặc trạng thái phục hồi.
Ứng dụng báo API thành công ngay khi submit tác vụ nền; sau khi container restart, tác vụ không được lưu và khách hàng tin rằng báo cáo đã hoàn tất.
Đội cấp task ID bằng số thứ tự trong RAM để tra cứu tiến độ; hai pod sinh cùng ID và trạng thái trả về cho khách bị lẫn giữa hai tác vụ khác nhau.
Nhóm xử lý job idempotent theo requestId nhưng chỉ lưu dấu đã chạy trong local map; khi có nhiều replica, cùng task được xử lý lại trên node khác.
Ứng dụng dùng @Scheduled để quét các công việc chưa hoàn tất ở database; hai replica cùng chọn một row và thực hiện cùng tác vụ trước khi ghi trạng thái đang chạy.
Đội dùng transaction database quanh task chạy lâu để tránh tranh chấp; lock giữ qua lời gọi API ngoài khiến các giao dịch nhỏ bị nghẽn hàng phút.
Nhóm tăng số worker đọc queue công việc ngoài nhưng hệ thống upstream chỉ có một partition; worker mới không nhận được thêm dữ liệu và throughput không cải thiện.
Ứng dụng triển khai bulkhead theo TaskExecutor tách pool đọc/ghi; một dependency chung như HTTP client pool vẫn trở thành nút thắt khiến các pool không thực sự độc lập.
Đội quản trị muốn dừng tác vụ theo yêu cầu người dùng; một task đang thực thi không kiểm trạng thái hủy và tiếp tục tạo file sau khi hệ thống trả đã hủy.
Nhóm ghi trạng thái 'completed' ngay khi CompletableFuture chạy xong; callback cuối cần upload lên S3 vẫn chưa hoàn tất nên client tải file nhận lỗi 404.
Ứng dụng dùng MDC và ThreadLocal phục vụ audit trên nhiều executor; một task chuyển từ worker pool sang scheduler không giữ trace parent nên nhật ký bị chia nhỏ.
Đội đánh giá @Async chỉ bằng unit test gọi thẳng method; vì bỏ qua Spring proxy, testcase không phản ánh thời điểm trả kết quả và ngoại lệ ở production.
Nhóm chạy SpringBootTest với một executor đồng bộ để dễ assertion; test đều đạt trong khi production chạy song song và lỗi tranh chấp state chỉ xuất hiện ở tải thực.
Ứng dụng có test @Async với CompletableFuture và timeout ngắn cố định; trên máy CI bị quá tải, task hợp lệ chưa kịp chạy làm test flaky.
Đội kiểm thử scheduled job bằng cách gọi method trực tiếp; cấu hình cron, timezone và @EnableScheduling không được thực thi nên lỗi lịch chỉ xuất hiện sau triển khai.
Nhóm dùng ThreadPoolTaskScheduler trong production nhưng test chạy scheduler một thread; test không phát hiện hai công việc định kỳ cùng sửa một bản ghi vào một thời điểm.
Ứng dụng kiểm thử hủy Future bằng mock không tôn trọng interruption; khi dùng HTTP driver thật, tác vụ vẫn chạy dù cancel và gây side effect sau timeout.
Đội chạy load test với 20 người dùng nhưng production có 5.000 request đồng thời; queue executor chỉ đầy và phát TaskRejectedException ở quy mô mà test chưa đo.
Nhóm benchmark số thread bằng cách dùng tác vụ sleep; kết quả không đại diện công việc CPU, JDBC và synchronized thực nên cấu hình pool đưa lên production sai lệch.
Ứng dụng đo thời gian xử lý của task tính từ lúc worker bắt đầu; thời gian chờ lâu trong executor queue không được tính và dashboard báo latency thấp dù khách nhận kết quả rất trễ.
Đội vận hành chỉ nhìn CPU khi đánh giá ThreadPoolTaskExecutor; hàng nghìn task chờ network làm CPU thấp nhưng queue tăng và deadline người dùng liên tục bị vượt.
Nhóm cấp quota tác vụ theo người dùng bằng bộ đếm trong RAM; sau khi restart hoặc scale, quota bị đặt lại và một khách có thể chiếm toàn bộ queue executor.
Ứng dụng gọi @Async từ một request đã bị client ngắt kết nối; tác vụ vẫn đang chạy nhưng không có chính sách giữ, hủy hoặc lưu kết quả để tiếp tục.
Đội mở tracing cho @Scheduled job có lời gọi CompletableFuture; spans ở các callback không cùng traceId vì phần truyền ngữ cảnh không đi qua executor đã cấu hình.
Nhóm thay executor trong Spring sau khi gặp sự cố overload; configuration rollback khiến tên bean hoặc chính sách từ chối khác và nhiều job nền hoạt động không giống trước.
Ứng dụng cập nhật phiên bản Spring Framework và JDK trong cùng release; hành vi virtual threads và executor khác bản cũ nhưng bài kiểm thử chỉ xác nhận không có exception.
Đội triển khai rolling restart cho ứng dụng có tác vụ async dài khi container nhận SIGTERM; pod cũ bị kill trước khi hoàn tất và pod mới không biết công việc nào cần tiếp tục.
Nhóm cần bảo đảm email chốt sổ chỉ được gửi một lần; cùng scheduled task chạy trên hai pod trong lúc deploy và cả hai đều tạo lệnh gửi mới.
Ứng dụng có nhiều @Async method trong bean singleton được chia sẻ giữa request và scheduler; trạng thái tạm của một tác vụ bị tác vụ khác ghi đè tạo dữ liệu báo cáo sai.
Đội vận hành đặt deadline nghiệp vụ cho mỗi task nhưng không có cách theo dõi lúc tạo, lúc bắt đầu và lúc hoàn tất; những task đã quá hạn vẫn được chạy khi queue rỗng trở lại.
Nhóm lưu queue các tác vụ trong bộ nhớ TaskExecutor cho một quy trình đối soát quan trọng; khi mất điện, mọi tác vụ chưa được chạy biến mất mà database không có dấu vết khôi phục.
