Bạn giải thích nhu cầu scaling trong Spring Batch khác tối ưu hóa một tác vụ xử lý dữ liệu đơn lẻ như thế nào?
Bạn sẽ xác định mục tiêu throughput, thời gian hoàn thành và mức sử dụng tài nguyên cho một batch job ra sao?
Bạn phân biệt mở rộng theo chiều dọc và mở rộng theo chiều ngang trong một hệ thống batch như thế nào?
Bạn đánh giá những điều kiện nào cho thấy cần thay đổi kiến trúc thay vì chỉ tăng CPU hoặc bộ nhớ?
Bạn sẽ phân loại workload batch theo CPU-bound, I/O-bound và mức độ phụ thuộc dữ liệu như thế nào?
Bạn giải thích vai trò của Job, Step và StepExecution khi thiết kế một luồng batch có thể mở rộng ra sao?
Bạn phân biệt xử lý chunk-oriented với tasklet khi xem xét khả năng chia nhỏ công việc như thế nào?
Bạn sẽ quyết định ranh giới transaction của một chunk dựa trên rủi ro và chi phí rollback ra sao?
Bạn xác định những giai đoạn đọc, xử lý và ghi nào có thể chạy song song mà không làm sai kết quả như thế nào?
Bạn đánh giá tác động của một bước xử lý có thứ tự bắt buộc lên khả năng scaling của toàn job ra sao?
Bạn phân biệt độ trễ của một chunk với thời gian hoàn thành toàn bộ job như thế nào?
Bạn sẽ xây dựng mô hình năng lực dự kiến từ số bản ghi, kích thước dữ liệu và thời gian xử lý trung bình ra sao?
Bạn giải thích vì sao tăng số thread không nhất thiết làm tăng tốc độ hoàn thành job như thế nào?
Bạn thiết kế thí nghiệm tìm giới hạn scaling trước khi đưa batch job lên production ra sao?
Bạn lựa chọn cách bắt đầu từ một baseline tuần tự để so sánh với các mô hình song song như thế nào?
Bạn xác định các chỉ số cần đo ở reader, processor và writer để tìm bottleneck như thế nào?
Bạn phân biệt thời gian đợi kết nối cơ sở dữ liệu với thời gian CPU xử lý business rule ra sao?
Bạn sẽ xác định query chậm hoặc thiếu index có phải nguyên nhân khiến batch job chạy lâu như thế nào?
Bạn kiểm tra ảnh hưởng của độ lớn result set tới bộ nhớ và thời gian đọc dữ liệu ra sao?
Bạn phân tích tác động của số lượng round-trip tới database trong từng chunk như thế nào?
Bạn lựa chọn giữa tối ưu SQL và tăng concurrency dựa trên thông số đo đạc nào?
Bạn sẽ đo độ trễ commit, rollback và thời gian lock khi nhiều worker ghi đồng thời ra sao?
Bạn đánh giá tác động của connection pool lên throughput của multi-threaded step như thế nào?
Bạn phân biệt nghẽn ở nguồn dữ liệu với nghẽn ở message broker khi vận hành batch phân tán ra sao?
Bạn xác định các điểm tranh chấp lock, unique index và transaction isolation khiến throughput giảm như thế nào?
Bạn sẽ đo CPU utilization, GC pause và heap usage để phân biệt bottleneck tính toán với vấn đề cấp phát bộ nhớ ra sao?
Bạn đánh giá sự khác biệt giữa số bản ghi mỗi giây và số bản ghi thành công mỗi giây như thế nào?
Bạn xây dựng biểu đồ throughput theo số thread hoặc partition để tìm điểm bão hòa ra sao?
Bạn sẽ tính toán chi phí thiết lập worker và overhead điều phối khi quyết định mức độ song song như thế nào?
Bạn xác định có hiện tượng data skew khi một nhóm khóa chứa nhiều bản ghi hơn các nhóm khác ra sao?
Bạn phân biệt bài toán tối ưu tốc độ của một job với tối ưu tổng năng lực chạy nhiều job đồng thời như thế nào?
Bạn lựa chọn cách phân bổ CPU, RAM và I/O giữa batch job và workload giao dịch trực tuyến ra sao?
Bạn giải thích vai trò của TaskExecutor khi cấu hình multi-threaded step trong Spring Batch như thế nào?
Bạn mô tả cách một chunk-oriented step có thể xử lý nhiều chunk đồng thời khi được cấu hình thực thi đa luồng ra sao?
Bạn sẽ lựa chọn TaskExecutor phù hợp với một multi-threaded step dựa trên workload và tài nguyên như thế nào?
Bạn phân tích sự khác nhau giữa concurrency của step và kích thước thread pool như thế nào?
Bạn xác định giới hạn số thread để không vượt quá khả năng phục vụ của database và hệ thống ngoài ra sao?
Bạn sẽ thiết kế queue thực thi có giới hạn thay vì tích tụ vô hạn các chunk đang chờ như thế nào?
Bạn mô tả rủi ro khi reader có trạng thái được dùng đồng thời bởi nhiều thread như thế nào?
Bạn phân biệt một ItemReader stateless với ItemReader giữ cursor hoặc vị trí đọc như thế nào?
Bạn xác định khi nào một ItemProcessor có thể chạy đa luồng mà không cần đồng bộ hóa trạng thái ra sao?
Bạn phân tích vì sao một ItemWriter dùng bộ đệm chung có thể gây lỗi khi nhiều chunk cùng ghi như thế nào?
Bạn lựa chọn biện pháp đồng bộ hóa một reader không thread-safe và cân nhắc ảnh hưởng đến throughput như thế nào?
Bạn sẽ đánh giá tradeoff giữa khóa đồng bộ quanh reader và chuyển sang partitioning ra sao?
Bạn mô tả những trường hợp một adapter đồng bộ reader bảo vệ truy cập nhưng không giải quyết hết vấn đề restart như thế nào?
Bạn xác định cách đảm bảo mỗi bản ghi nguồn chỉ được một worker xử lý trong multi-threaded step ra sao?
Bạn phân biệt thứ tự đọc, thứ tự xử lý và thứ tự commit trong một step đa luồng như thế nào?
Bạn sẽ thiết kế logic ghi không phụ thuộc thứ tự chunk trong những trường hợp nào?
Bạn phân tích khả năng race condition khi processor sửa một biến đếm hoặc bộ nhớ cache dùng chung như thế nào?
Bạn lựa chọn scope và vòng đời bean cho reader, processor hoặc writer có trạng thái ra sao?
Bạn giải thích vai trò của StepScope khi tạo tài nguyên riêng theo StepExecution như thế nào?
Bạn phân biệt việc tạo bean step-scoped với việc tự động bảo đảm thread safety trong cùng một StepExecution ra sao?
Bạn sẽ quản lý transaction khi nhiều thread thực thi các chunk độc lập như thế nào?
Bạn xác định cách xử lý lỗi commit của một chunk mà các chunk khác đã hoàn tất ra sao?
Bạn đánh giá tác động của retry và skip tới các chunk chạy đồng thời như thế nào?
Bạn thiết kế idempotent writer để một chunk được thực thi lại không tạo bản ghi trùng như thế nào?
Bạn phân tích rủi ro chia sẻ EntityManager hoặc Hibernate session giữa các thread xử lý batch như thế nào?
Bạn sẽ kiểm thử concurrency để phát hiện mất bản ghi hoặc xử lý trùng trong multi-threaded step ra sao?
Bạn lựa chọn cách giới hạn thời gian thực thi và số tác vụ đang chờ của TaskExecutor như thế nào?
Bạn xác định chỉ số nào cho thấy tăng thread pool chỉ làm tăng contention mà không tăng throughput ra sao?
Bạn giải thích cách parallel steps khác multi-threaded step về đơn vị được thực thi đồng thời như thế nào?
Bạn sẽ xác định những Step nào có thể chạy song song mà không phụ thuộc đầu ra của nhau ra sao?
Bạn mô tả cách thiết kế một Flow gồm các Step và ghép nhiều Flow song song như thế nào?
Bạn giải thích vai trò của split và TaskExecutor khi triển khai parallel flows trong Spring Batch như thế nào?
Bạn sẽ lựa chọn parallel steps khi các nhánh xử lý thuộc những miền dữ liệu độc lập như thế nào?
Bạn phân biệt phụ thuộc dữ liệu và phụ thuộc tài nguyên khi quyết định hai Step có thể chạy song song ra sao?
Bạn đánh giá nguy cơ deadlock khi hai Step cùng cập nhật các bảng dùng chung như thế nào?
Bạn sẽ thiết kế điểm đồng bộ để chỉ chạy bước tổng hợp sau khi các nhánh song song hoàn tất ra sao?
Bạn xác định cách xử lý khi một nhánh parallel flow thất bại nhưng các nhánh khác đã thành công như thế nào?
Bạn phân biệt trạng thái hoàn thành của Flow, StepExecution và JobExecution trong một job có parallel steps như thế nào?
Bạn sẽ thiết kế restart để không chạy lại nhánh đã hoàn tất nếu không cần thiết ra sao?
Bạn phân tích cách chia sẻ JobExecutionContext giữa các nhánh song song có thể tạo tranh chấp như thế nào?
Bạn thiết kế cách tổng hợp số lượng bản ghi đã xử lý từ các Step song song ra sao?
Bạn sẽ phân bổ thread pool cho các Flow chạy song song mà không cạn tài nguyên hệ thống như thế nào?
Bạn đánh giá chi phí khởi động parallel steps khi mỗi Step xử lý rất ít dữ liệu như thế nào?
Bạn sẽ lựa chọn chia theo Step nghiệp vụ hay theo partition dữ liệu khi một job có nhiều công đoạn ra sao?
Bạn mô tả khái niệm partitioning trong Spring Batch và mục tiêu phân chia một Step thành nhiều phần độc lập như thế nào?
Bạn phân biệt manager Step và worker Step trong mô hình partitioning ra sao?
Bạn giải thích vai trò của Partitioner trong việc tạo tập phân vùng và ExecutionContext cho mỗi phân vùng như thế nào?
Bạn sẽ chọn tiêu chí chia partition theo dải ID, thời gian, khóa khách hàng hoặc tệp dữ liệu như thế nào?
Bạn thiết kế range partition không bỏ sót hoặc xử lý trùng bản ghi ở ranh giới như thế nào?
Bạn phân tích tác động của khoảng khóa không liên tục đối với partition theo dải ID ra sao?
Bạn sẽ giải quyết tình huống một partition có nhiều dữ liệu hơn hẳn các partition khác như thế nào?
Bạn xác định chiến lược chia partition theo hash khi ID phân bố không đều như thế nào?
Bạn thiết kế partition theo tệp khi mỗi file có kích thước và độ phức tạp khác nhau ra sao?
Bạn so sánh partition tĩnh với phân chia công việc động khi khối lượng xử lý không đồng đều như thế nào?
Bạn sẽ đặt tên partition nhất quán để hỗ trợ checkpoint và restart như thế nào?
Bạn giải thích vì sao partition key ổn định quan trọng khi chạy lại một job thất bại ra sao?
Bạn thiết kế ExecutionContext của từng worker Step để truyền phạm vi dữ liệu an toàn như thế nào?
Bạn phân biệt JobParameters với StepExecutionContext khi truyền thông tin partition ra sao?
Bạn xác định những dữ liệu nào không nên ghi vào ExecutionContext vì kích thước lớn hoặc nhạy cảm như thế nào?
Bạn sẽ cấu hình giá trị gridSize dựa trên số partition mong muốn và khả năng worker ra sao?
Bạn phân biệt gridSize với kích thước thread pool hoặc số worker thực tế như thế nào?
Bạn đánh giá tác động của partition quá nhỏ lên overhead điều phối và metadata như thế nào?
Bạn phân tích tác động của partition quá lớn lên cân bằng tải và khả năng phục hồi như thế nào?
Bạn sẽ dùng TaskExecutorPartitionHandler trong trường hợp nào và giới hạn của mô hình chạy cục bộ ra sao?
Bạn giải thích vai trò của PartitionHandler khi phân công worker Step và nhận kết quả như thế nào?
Bạn thiết kế ranh giới transaction độc lập giữa các partition để tránh ảnh hưởng lẫn nhau như thế nào?
Bạn xác định cách bảo đảm phạm vi đọc của các worker không giao nhau khi nguồn dữ liệu biến động ra sao?
Bạn phân tích rủi ro khi dữ liệu nguồn được thêm hoặc cập nhật trong lúc job đang chạy như thế nào?
Bạn lựa chọn snapshot, mốc thời gian hoặc watermark để giữ tập dữ liệu xử lý nhất quán ra sao?
Bạn sẽ thiết kế query reader theo partition sao cho tận dụng index và tránh full scan lặp lại như thế nào?
Bạn phân biệt cách partition theo khóa nghiệp vụ với cách chia offset trên một bảng lớn như thế nào?
Bạn đánh giá tại sao pagination bằng offset có thể kém hiệu quả khi dữ liệu thay đổi và số trang lớn như thế nào?
Bạn sẽ sử dụng khóa sắp xếp ổn định để chia trang và phục hồi tiến độ như thế nào?
Bạn thiết kế worker Step sử dụng StepScope để đọc startId và endId của partition ra sao?
Bạn phân tích điều gì xảy ra khi hai partition cùng cố ghi một khóa duy nhất vào bảng đích ra sao?
Bạn sẽ bảo vệ writer khỏi tác dụng phụ trùng khi phân vùng dữ liệu không hoàn toàn độc lập như thế nào?
Bạn xác định cách tổng hợp trạng thái COMPLETED, FAILED hoặc STOPPED từ nhiều partition thành kết quả manager Step ra sao?
Bạn sẽ xử lý partition thất bại trong khi những partition khác đã hoàn thành như thế nào?
Bạn thiết kế cơ chế restart chỉ xử lý lại partition còn dang dở trong các điều kiện nào?
Bạn phân tích vì sao thay đổi cách đặt tên partition giữa các lần chạy có thể ảnh hưởng restart như thế nào?
Bạn sẽ kiểm thử độ phủ dữ liệu của Partitioner với khoảng rỗng, khóa âm và khoảng chồng lấn ra sao?
Bạn xây dựng kiểm thử để xác minh số bản ghi đầu ra bằng tổng số bản ghi từ từng partition như thế nào?
Bạn phân biệt remote partitioning với local partitioning về nơi worker Step chạy và cách điều phối ra sao?
Bạn mô tả trách nhiệm của manager và worker khi phân phối partition qua hệ thống nhắn tin như thế nào?
Bạn sẽ lựa chọn remote partitioning khi một máy không đủ CPU, RAM hoặc khả năng I/O như thế nào?
Bạn giải thích sự khác nhau giữa remote partitioning và remote chunking về nơi dữ liệu được đọc như thế nào?
Bạn sẽ quyết định chọn remote chunking khi manager có thể đọc dữ liệu nhưng processor hoặc writer tốn tài nguyên như thế nào?
Bạn phân tích bottleneck khi một manager duy nhất đọc toàn bộ dữ liệu trong remote chunking ra sao?
Bạn mô tả vòng đời một chunk được gửi tới remote worker và kết quả phản hồi về manager như thế nào?
Bạn xác định yêu cầu đối với broker khi phân phối công việc giữa nhiều remote worker như thế nào?
Bạn sẽ thiết kế message chứa định danh job, step và partition để tránh lẫn các lần chạy ra sao?
Bạn phân tích tác động của message bị phát lại tới việc thực thi partition hoặc chunk như thế nào?
Bạn xác định cách áp dụng idempotency cho worker khi nhận lại cùng một yêu cầu công việc ra sao?
Bạn sẽ xử lý worker bị mất kết nối sau khi ghi dữ liệu nhưng trước khi xác nhận hoàn tất như thế nào?
Bạn phân biệt việc broker xác nhận đã nhận yêu cầu với việc batch worker đã commit transaction ra sao?
Bạn thiết kế retry ở tầng messaging để không tạo nhiều worker xử lý cùng một partition ngoài kiểm soát như thế nào?
Bạn sẽ giới hạn số công việc remote đang thực thi để tránh làm quá tải database chung ra sao?
Bạn đánh giá cách scale số worker khi throughput tăng nhưng manager vẫn có tài nguyên giới hạn như thế nào?
Bạn xác định điều kiện cần chia nhiều manager job hoặc thay chiến lược phân phối công việc ra sao?
Bạn thiết kế cơ chế phát hiện worker chết hoặc mất heartbeat trong thời gian xử lý dài như thế nào?
Bạn sẽ quyết định khi nào một partition được phép cấp lại cho worker khác ra sao?
Bạn phân tích nguy cơ worker cũ vẫn đang chạy khi partition đã được giao lại như thế nào?
Bạn xác định cách dùng lease hoặc cơ chế fencing để giảm rủi ro hai worker cùng ghi dữ liệu ra sao?
Bạn sẽ thiết kế sự tương thích về version giữa manager và worker khi deploy dần các phiên bản như thế nào?
Bạn kiểm tra khả năng serialize và deserialize ExecutionContext hoặc message giữa các worker ra sao?
Bạn sẽ quản lý cấu hình kết nối, credential và quyền của remote worker theo nguyên tắc tối thiểu như thế nào?
Bạn thiết kế theo dõi lỗi mạng và độ trễ broker mà không nhầm với lỗi xử lý nghiệp vụ ra sao?
Bạn đánh giá lựa chọn remote partitioning so với Kubernetes Jobs hoặc bộ lập lịch ngoài theo yêu cầu nào?
Bạn sẽ thiết kế cách graceful shutdown worker để không bỏ dở hoặc ghi trùng chunk như thế nào?
Bạn phân biệt thread-safe với restart-safe đối với reader, processor và writer như thế nào?
Bạn giải thích vì sao một bean stateless vẫn cần kiểm tra thread safety của dependency mà nó gọi như thế nào?
Bạn sẽ rà soát những biến mutable trong ItemProcessor có thể gây race condition ra sao?
Bạn thiết kế cache dùng chung trong processor sao cho không làm sai dữ liệu khi nhiều thread truy cập như thế nào?
Bạn phân tích tác động của một reader có bộ đếm trang nội bộ khi bị nhiều thread dùng chung như thế nào?
Bạn xác định thời điểm cần đồng bộ hóa truy cập đến một tài nguyên chỉ cho phép thao tác tuần tự ra sao?
Bạn sẽ giảm vùng khóa đồng bộ để tăng throughput mà vẫn bảo toàn dữ liệu như thế nào?
Bạn phân biệt thread confinement theo worker với việc chia sẻ một singleton bean trên toàn bộ job ra sao?
Bạn thiết kế writer dùng batch insert có thể chạy đồng thời trên nhiều connection như thế nào?
Bạn đánh giá nguy cơ writer sử dụng cùng một file output từ nhiều partition như thế nào?
Bạn sẽ thiết kế tên file đầu ra riêng theo partition để tránh ghi đè hoặc trộn dữ liệu ra sao?
Bạn xử lý bước hợp nhất các file kết quả sau khi mọi partition hoàn tất như thế nào?
Bạn xác định chính sách đồng bộ hóa khi nhiều partition gọi cùng một REST API có rate limit ra sao?
Bạn sẽ tránh sử dụng một EntityManager không phù hợp để chia sẻ giữa các thread như thế nào?
Bạn phân tích cách transaction isolation ảnh hưởng đến dữ liệu đọc khi nhiều partition chạy đồng thời ra sao?
Bạn thiết kế phương án retry trên lỗi deadlock hoặc lock timeout trong một chunk như thế nào?
Bạn lựa chọn skip policy cho bản ghi lỗi dữ liệu mà không làm mất khả năng đối soát như thế nào?
Bạn xác định cách đặt retry limit và skip limit dựa trên tác động nghiệp vụ ra sao?
Bạn sẽ ghi nhận số lần retry và số bản ghi bị skip theo từng StepExecution hoặc partition như thế nào?
Bạn phân biệt rollback của chunk với rollback toàn bộ job khi một lỗi xảy ra như thế nào?
Bạn phân tích tác động của thao tác gọi API bên ngoài không tham gia transaction tới khả năng restart ra sao?
Bạn sẽ thiết kế idempotency key cho thao tác ghi dữ liệu hoặc gọi dịch vụ bên ngoài của một item như thế nào?
Bạn xử lý tình huống DB commit thành công nhưng ghi trạng thái checkpoint thất bại ra sao?
Bạn giải thích vai trò của JobRepository đối với metadata JobExecution và StepExecution trong một job có khả năng restart như thế nào?
Bạn phân biệt trạng thái COMPLETED, FAILED và STOPPED khi quyết định có thể restart job như thế nào?
Bạn xác định JobInstance dựa trên identifying JobParameters và tác động tới việc chạy lại như thế nào?
Bạn thiết kế JobParameters để các lần chạy lịch trình không vô tình tạo một JobInstance mới khi đang cần restart ra sao?
Bạn sẽ xác định những bước đã hoàn thành có cần thực thi lại khi restart job theo quy tắc nào?
Bạn phân biệt restart một JobExecution bị lỗi với chạy một JobInstance mới xử lý lại cùng dữ liệu như thế nào?
Bạn thiết kế checkpoint cho reader để khôi phục chính xác vị trí đọc sau lỗi như thế nào?
Bạn phân tích rủi ro khi dữ liệu nguồn thay đổi thứ tự giữa hai lần restart ra sao?
Bạn lựa chọn commit interval để cân bằng tần suất checkpoint, chi phí giao dịch và dữ liệu phải xử lý lại như thế nào?
Bạn sẽ kiểm tra các giả định về thứ tự chunk khi nhiều thread commit theo thời điểm khác nhau ra sao?
Bạn thiết kế chiến lược đối soát khi số bản ghi đã xử lý theo metadata lệch với dữ liệu thực tế ở đích như thế nào?
Bạn phân biệt bảo đảm ít nhất một lần xử lý với tác dụng nghiệp vụ đúng một lần trong batch như thế nào?
Bạn đánh giá khi nào nên dùng unique constraint hoặc upsert để chống trùng trong writer ra sao?
Bạn sẽ ngăn một partition thất bại làm mất tiến độ đã hoàn tất của các partition khác như thế nào?
Bạn xác định cơ chế xử lý khi job bị dừng thủ công đúng lúc nhiều transaction vẫn đang chạy như thế nào?
Bạn thiết kế thủ tục khôi phục sau crash của manager trong khi remote workers vẫn còn hoạt động ra sao?
Bạn phân tích khả năng job bị chạy trùng do scheduler gửi cùng yêu cầu nhiều lần như thế nào?
Bạn sẽ xây dựng cơ chế ngăn hai instance cùng chạy một workload có thể gây xung đột dữ liệu ra sao?
Bạn phân biệt stop, restart và abandon job trong một quy trình vận hành có kiểm soát như thế nào?
Bạn xác định ranh giới khi nào cần can thiệp thủ công thay vì để retry tự động tiếp tục như thế nào?
Bạn sẽ xây dựng runbook xử lý một partition bị kẹt kéo dài hoặc liên tục thất bại ra sao?
Bạn lựa chọn các chỉ số cần hiển thị để vận hành batch job với nhiều StepExecution như thế nào?
Bạn theo dõi read count, write count, filter count, skip count và rollback count để đánh giá chất lượng xử lý như thế nào?
Bạn phân biệt thời gian chờ trong queue thực thi với thời gian xử lý thực tế của một chunk ra sao?
Bạn sẽ đo độ phân bố thời gian xử lý theo partition để phát hiện partition chậm bất thường như thế nào?
Bạn đánh giá tác động của connection pool saturation lên latency của các worker đang hoạt động ra sao?
Bạn thiết kế dashboard cho CPU, memory, GC, I/O và số thread của các batch worker như thế nào?
Bạn sẽ gắn correlation ID cho JobExecution, StepExecution và partition khi ghi log ra sao?
Bạn phân biệt log lỗi ở manager với log lỗi ở worker trong kiến trúc remote partitioning như thế nào?
Bạn xác định những trường hợp cần bật tracing từ manager qua broker đến worker như thế nào?
Bạn sẽ thiết kế cảnh báo dựa trên thời gian job vượt SLA thay vì chỉ dựa trên trạng thái FAILED ra sao?
Bạn xác định dấu hiệu retry storm hoặc nhiều partition bị lỗi cùng nguyên nhân hạ nguồn như thế nào?
Bạn thiết kế cơ chế giới hạn tổng số worker và chunk đồng thời khi nhiều job được kích hoạt cùng lúc như thế nào?
Bạn phân tích tác động của việc chạy batch giờ cao điểm lên các transaction online dùng chung database ra sao?
Bạn sẽ xây dựng lịch chạy và chính sách ưu tiên giữa batch job quan trọng và job nền như thế nào?
Bạn lựa chọn cách dừng hoặc giảm tốc job khi dependency vượt ngưỡng rate limit ra sao?
Bạn thiết kế kiểm soát log để vẫn điều tra được lỗi mà không ghi lộ dữ liệu cá nhân trong batch ra sao?
Bạn xác định thông tin cần lưu trong audit trail khi một job được restart hoặc chạy lại thủ công như thế nào?
Bạn sẽ quản lý retention của metadata batch và lịch sử log để không làm tăng dung lượng vô hạn ra sao?
Bạn thiết kế khả năng chạy lại một khoảng dữ liệu theo thời gian mà không ảnh hưởng dữ liệu đã hoàn tất như thế nào?
Bạn đánh giá khi nào nên chia workload lớn thành nhiều JobInstance độc lập thay vì một job partitioned duy nhất như thế nào?
Bạn sẽ lập kế hoạch nâng cấp ứng dụng Spring Batch khi có job đang chạy và worker ở nhiều phiên bản ra sao?
Bạn thiết kế thử nghiệm tải để so sánh step tuần tự, multi-threaded step và partitioned step trên cùng dữ liệu như thế nào?
Bạn sẽ kiểm thử tính chính xác khi số thread tăng nhưng thứ tự hoàn thành chunk thay đổi ra sao?
Bạn xây dựng bộ dữ liệu thử nghiệm có khóa trùng, bản ghi rỗng và partition không cân bằng như thế nào?
Bạn kiểm thử Partitioner để chắc chắn mọi bản ghi thuộc chính xác một partition như thế nào?
Bạn mô phỏng reader có trạng thái bị truy cập đồng thời để phát hiện lỗi thread safety ra sao?
Bạn sẽ kiểm thử việc một writer bị retry sau khi đã ghi dữ liệu thành công để phát hiện bản ghi trùng như thế nào?
Bạn xây dựng bài kiểm thử job restart sau khi worker lỗi ở giữa chunk như thế nào?
Bạn kiểm thử partition thành công trước đó có bị xử lý lại ngoài mong muốn khi restart manager như thế nào?
Bạn mô phỏng database deadlock giữa các worker để kiểm tra retry và rollback như thế nào?
Bạn sẽ kiểm thử remote worker bị mất kết nối sau commit nhưng trước khi gửi kết quả ra sao?
Bạn kiểm tra phản ứng của hệ thống khi manager mất kết nối broker trong lúc nhiều partition vẫn đang chạy như thế nào?
Bạn xây dựng kiểm thử tải khi tăng worker vượt ngưỡng connection pool để tìm điểm bão hòa ra sao?
Bạn sẽ đánh giá tính ổn định của throughput ở p95 hoặc p99 thời gian chunk thay vì chỉ nhìn giá trị trung bình như thế nào?
Bạn kiểm thử một job song song có nhiều nhánh Flow khi một nhánh thất bại và các nhánh khác thành công như thế nào?
Bạn kiểm tra số lượng đầu ra và checksum dữ liệu giữa cách chạy tuần tự với cách chạy song song như thế nào?
Bạn xây dựng integration test cho trạng thái JobRepository khi nhiều worker cập nhật metadata đồng thời như thế nào?
Bạn sẽ xác nhận các StepExecution và partition được đóng đúng trạng thái sau một lần shutdown có kiểm soát ra sao?
Bạn thiết kế chaos test cho broker, database và worker để đánh giá độ tin cậy của batch phân tán như thế nào?
Bạn lựa chọn tiêu chí chấp nhận về tính đúng, khả năng restart và throughput trước khi đưa chiến lược scaling vào production ra sao?
Nếu batch job chạy lâu nhưng CPU thấp và nhiều thread chờ database, bạn sẽ chẩn đoán và tối ưu như thế nào?
Nếu tăng từ bốn lên mười sáu thread khiến throughput giảm, bạn sẽ kiểm tra những tài nguyên và tranh chấp nào?
Nếu một reader dùng cursor bị đọc trùng khi multi-threaded step chạy, bạn sẽ thay đổi thiết kế như thế nào?
Nếu một Step cần xử lý nhiều file độc lập với kích thước khác nhau, bạn sẽ lựa chọn parallel steps hay partitioning như thế nào?
Nếu dữ liệu có một vài khách hàng chiếm phần lớn số bản ghi, bạn sẽ thiết kế partition để giảm skew ra sao?
Nếu hai partition cùng ghi vào một bảng có unique constraint và xảy ra deadlock, bạn sẽ xử lý thế nào?
Nếu worker remote ghi thành công nhưng broker phát lại yêu cầu do mất acknowledgment, bạn sẽ bảo đảm idempotency ra sao?
Nếu manager khởi động lại giữa lúc các remote worker đang chạy, bạn sẽ kiểm tra và khôi phục trạng thái như thế nào?
Nếu một partition chạy chậm gấp mười lần các partition khác, bạn sẽ cân nhắc điều chỉnh phạm vi dữ liệu và số worker ra sao?
Nếu job bị restart sau khi dữ liệu nguồn đã thay đổi, bạn sẽ tránh bỏ sót hoặc ghi trùng bản ghi như thế nào?
Nếu nhiều JobInstance cùng chạy và làm cạn connection pool, bạn sẽ thiết lập giới hạn đồng thời và ưu tiên ra sao?
Nếu một job phân tán phải đáp ứng SLA chặt chẽ, bạn sẽ thiết kế đo lường, retry, stop và cảnh báo như thế nào?
Nếu phải chọn giữa multi-threaded step, parallel flows, local partitioning và remote partitioning cho một pipeline lớn, bạn sẽ trình bày tiêu chí quyết định nào?
Nếu phải đưa Spring Batch workload dữ liệu lớn lên production, bạn sẽ thiết kế kiểm thử hiệu năng, restart, bảo mật và runbook vận hành ra sao?
