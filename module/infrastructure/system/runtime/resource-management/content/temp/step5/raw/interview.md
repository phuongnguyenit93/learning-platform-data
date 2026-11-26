Bạn sẽ mô tả các nhóm tài nguyên mà một ứng dụng runtime thường sử dụng và mối quan hệ giữa chúng như thế nào?
Bạn sẽ phân biệt tài nguyên do JVM quản lý với tài nguyên do hệ điều hành cấp phát trực tiếp ra sao?
Bạn sẽ xây dựng ngân sách CPU, bộ nhớ và I/O cho một dịch vụ dựa trên tải dự kiến bằng cách nào?
Bạn sẽ xác định giới hạn tài nguyên phù hợp cho một ứng dụng khi chạy trên máy chủ dùng chung như thế nào?
Bạn sẽ giải thích vì sao việc cấp phát tài nguyên không giới hạn có thể làm ảnh hưởng các workload khác ra sao?
Bạn sẽ phân biệt mức sử dụng tài nguyên hiện tại, mức đỉnh và tốc độ tăng theo thời gian khi lập kế hoạch capacity như thế nào?
Bạn sẽ xác định vòng đời cấp phát, sử dụng và thu hồi của một tài nguyên runtime bằng những điểm kiểm soát nào?
Bạn sẽ thiết kế ownership rõ ràng cho file, socket, buffer và connection để tránh giải phóng sai hoặc rò rỉ như thế nào?
Bạn sẽ lựa chọn giữa tái sử dụng tài nguyên và tạo mới theo từng request dựa trên chi phí nào?
Bạn sẽ đánh giá tác động của việc giữ tài nguyên lâu hơn cần thiết đối với khả năng mở rộng của ứng dụng ra sao?
Bạn sẽ phân biệt CPU utilization của process với CPU quota và CPU throttling trong container như thế nào?
Bạn sẽ xác định một ứng dụng bị nghẽn CPU hay đang chờ I/O bằng những chỉ số runtime và hệ điều hành nào?
Bạn sẽ phân tích ảnh hưởng của thread contention và context switching đến throughput của ứng dụng như thế nào?
Bạn sẽ lựa chọn số worker hoặc thread xử lý dựa trên số CPU khả dụng và đặc tính tác vụ ra sao?
Bạn sẽ giải thích vì sao số CPU mà JVM nhìn thấy có thể khác số CPU vật lý của máy chủ như thế nào?
Bạn sẽ thiết kế giới hạn concurrency để một đợt traffic tăng không làm CPU bị bão hòa ra sao?
Bạn sẽ xác định khi nào nên dùng CPU profiling để tìm hot path thay vì chỉ tăng số core như thế nào?
Bạn sẽ phân biệt heap memory, metaspace, code cache và native memory trong một tiến trình JVM ra sao?
Bạn sẽ lựa chọn kích thước heap tối thiểu và tối đa dựa trên workload, container limit và headroom cho native memory như thế nào?
Bạn sẽ giải thích mối quan hệ giữa object allocation rate, garbage collection và latency của request ra sao?
Bạn sẽ nhận biết memory leak trong heap khác với việc heap tăng tạm thời do workload hoặc cache như thế nào?
Bạn sẽ phân tích heap dump để tìm object được giữ lại ngoài dự kiến và đường tham chiếu gây giữ bộ nhớ ra sao?
Bạn sẽ phân biệt retained heap với shallow size khi xác định object nào đang chiếm bộ nhớ thực sự như thế nào?
Bạn sẽ đánh giá tác động của allocation churn khi ứng dụng tạo nhiều object ngắn hạn dù heap sau GC vẫn thấp ra sao?
Bạn sẽ lựa chọn cách giảm allocation trong đường xử lý nóng mà không làm code khó bảo trì như thế nào?
Bạn sẽ giải thích off-heap memory được dùng trong những trường hợp nào và các chi phí quản lý đi kèm ra sao?
Bạn sẽ phân biệt direct ByteBuffer, heap ByteBuffer và native allocation về vòng đời cùng khả năng thu hồi như thế nào?
Bạn sẽ xác định giới hạn direct memory và xử lý lỗi cấp phát direct buffer khi heap vẫn còn dung lượng ra sao?
Bạn sẽ phân tích rủi ro khi ứng dụng giữ tham chiếu đến buffer pool hoặc native memory lâu hơn dự kiến như thế nào?
Bạn sẽ theo dõi native memory của JVM để tìm phần tiêu thụ không xuất hiện trong heap dump bằng cách nào?
Bạn sẽ phân biệt memory leak trong Java heap với native memory leak hoặc memory mapping leak ra sao?
Bạn sẽ đánh giá ảnh hưởng của page cache và resident set size đến tổng memory footprint của ứng dụng trong container như thế nào?
Bạn sẽ giải thích thread tiêu thụ những loại tài nguyên nào ngoài CPU khi được tạo trong JVM ra sao?
Bạn sẽ xác định giới hạn số thread phù hợp dựa trên stack size, bộ nhớ native và nhu cầu concurrency như thế nào?
Bạn sẽ phân biệt platform thread và virtual thread về chi phí tài nguyên cùng giới hạn sử dụng ra sao?
Bạn sẽ lựa chọn thread pool hay virtual thread cho một dịch vụ I/O-bound theo đặc điểm workload nào?
Bạn sẽ thiết kế bounded thread pool với queue và rejection policy để ngăn số tác vụ chờ tăng vô hạn như thế nào?
Bạn sẽ xác định queue capacity phù hợp cho executor bằng latency mục tiêu, tốc độ xử lý và burst traffic ra sao?
Bạn sẽ phân tích tình huống thread pool cạn worker dù CPU utilization thấp bằng những giả thuyết nào?
Bạn sẽ phân biệt thread leak với thread đang chờ hợp lệ hoặc pool có kích thước lớn theo cấu hình như thế nào?
Bạn sẽ chẩn đoán deadlock, lock contention và thread starvation từ thread dump ra sao?
Bạn sẽ xử lý tác vụ bị treo để không giữ worker thread vô thời hạn bằng timeout, cancellation hoặc cơ chế nào?
Bạn sẽ giải thích vì sao cần khôi phục trạng thái interrupt khi bắt và xử lý InterruptedException như thế nào?
Bạn sẽ xác định những tài nguyên cần đóng khi một request bị timeout hoặc bị hủy giữa chừng ra sao?
Bạn sẽ mô tả các giới hạn file descriptor hoặc handle của process và cách chúng ảnh hưởng đến ứng dụng như thế nào?
Bạn sẽ nhận diện file descriptor leak qua số lượng file hoặc socket đang mở tăng liên tục ra sao?
Bạn sẽ thiết kế vòng đời mở, đọc ghi và đóng file để tránh giữ descriptor khi xử lý exception như thế nào?
Bạn sẽ phân biệt file descriptor đã bị xóa tên nhưng vẫn đang mở với file đã thực sự giải phóng dung lượng ra sao?
Bạn sẽ xác định giới hạn socket và ephemeral port có thể gây lỗi kết nối khi tải tăng như thế nào?
Bạn sẽ phân biệt socket leak với connection pool lớn nhưng ổn định bằng những dấu hiệu nào?
Bạn sẽ thiết lập connect timeout, read timeout và idle timeout cho socket theo mục tiêu latency nào?
Bạn sẽ phân tích ảnh hưởng của TIME_WAIT và connection churn đến việc cạn ephemeral port ra sao?
Bạn sẽ lựa chọn keep-alive và connection reuse để giảm chi phí bắt tay mạng mà không giữ kết nối nhàn rỗi quá lâu như thế nào?
Bạn sẽ xác định kích thước connection pool phù hợp với giới hạn database, số worker và concurrency của ứng dụng ra sao?
Bạn sẽ phân biệt pool exhaustion với database chậm khi request phải chờ lấy connection như thế nào?
Bạn sẽ thiết kế acquisition timeout, max lifetime và idle timeout cho connection pool theo đặc tính backend ra sao?
Bạn sẽ xử lý connection bị stale hoặc bị database đóng khi đang nằm trong pool bằng cách nào?
Bạn sẽ đánh giá tác động của retry khi connection pool đã cạn và database đang quá tải như thế nào?
Bạn sẽ thiết lập giới hạn tổng connection khi một ứng dụng chạy nhiều replica để không vượt khả năng database ra sao?
Bạn sẽ giải thích buffer pooling giúp giảm allocation nhưng có thể làm tăng memory retention như thế nào?
Bạn sẽ lựa chọn kích thước và số lượng buffer dựa trên message size, throughput và giới hạn bộ nhớ ra sao?
Bạn sẽ ngăn một consumer giữ buffer hoặc message payload quá lâu sau khi xử lý xong bằng cơ chế nào?
Bạn sẽ phân tích ảnh hưởng của queue không giới hạn đến heap, latency và khả năng phục hồi khi downstream chậm như thế nào?
Bạn sẽ thiết kế backpressure để tốc độ producer không vượt quá khả năng xử lý bền vững của consumer ra sao?
Bạn sẽ lựa chọn giữa chờ, từ chối, giảm tải hoặc bỏ tác vụ khi hệ thống đạt ngưỡng tài nguyên theo tiêu chí nào?
Bạn sẽ phân biệt load shedding chủ động với lỗi ngẫu nhiên do hệ thống đã hết tài nguyên như thế nào?
Bạn sẽ xác định giới hạn concurrency và queue riêng cho từng dependency để tránh một backend chậm chiếm hết tài nguyên như thế nào?
Bạn sẽ thiết kế bulkhead isolation cho các nhóm request có mức độ quan trọng và dependency khác nhau ra sao?
Bạn sẽ giải thích vì sao timeout cần được truyền xuyên suốt các tầng thay vì mỗi tầng tự chờ một khoảng độc lập như thế nào?
Bạn sẽ lựa chọn deadline, cancellation và retry budget để giới hạn tổng thời gian cùng tài nguyên của một request ra sao?
Bạn sẽ xác định các metric JVM cần theo dõi để phát hiện heap pressure, GC overhead và allocation bất thường như thế nào?
Bạn sẽ kết hợp heap usage, GC pause, allocation rate và live thread count để phân tích suy giảm hiệu năng ra sao?
Bạn sẽ phân biệt heap committed với heap used và heap max khi đọc dashboard JVM như thế nào?
Bạn sẽ theo dõi direct memory, metaspace và native memory để nhận biết áp lực bộ nhớ ngoài heap bằng cách nào?
Bạn sẽ lựa chọn các chỉ số container như working set, RSS, memory limit và CPU throttling để đánh giá runtime footprint ra sao?
Bạn sẽ xác định vì sao process có thể bị OOMKilled dù heap usage chưa chạm mức tối đa của JVM như thế nào?
Bạn sẽ thiết kế dashboard kết hợp JVM metrics, process metrics và container metrics để thấy được toàn bộ giới hạn tài nguyên ra sao?
Bạn sẽ phân biệt resource leak với resource saturation do lưu lượng tăng cao nhưng hệ thống vẫn thu hồi đúng cách như thế nào?
Bạn sẽ xây dựng quy trình điều tra khi số thread, socket hoặc file descriptor tăng đều sau mỗi đợt traffic ra sao?
Bạn sẽ xác định những bằng chứng cần thu thập trước khi restart một process đang có dấu hiệu resource exhaustion như thế nào?
Bạn sẽ thiết kế bài kiểm thử tải và soak test để phát hiện rò rỉ tài nguyên chỉ xuất hiện sau nhiều giờ vận hành ra sao?
Bạn sẽ kiểm chứng rằng tài nguyên được thu hồi đúng khi request thành công, ném exception, timeout hoặc bị cancel như thế nào?
Bạn sẽ đặt tiêu chí nghiệm thu về giới hạn CPU, memory, thread, file, socket, pool, timeout và khả năng phục hồi trước khi đưa runtime vào production ra sao?
