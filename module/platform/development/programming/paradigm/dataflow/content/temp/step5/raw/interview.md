Bạn giải thích tư tưởng cốt lõi của dataflow programming và sự khác biệt với chương trình điều khiển bằng chuỗi câu lệnh như thế nào?
Bạn phân biệt sự phụ thuộc dữ liệu với thứ tự câu lệnh được viết trong mã nguồn khi lập lịch thực thi như thế nào?
Bạn mô tả vai trò của node và edge trong dataflow graph và ý nghĩa của một giá trị di chuyển giữa các node ra sao?
Bạn phân biệt node biểu diễn phép tính với edge biểu diễn quan hệ phụ thuộc trong một đồ thị xử lý dữ liệu như thế nào?
Bạn thiết kế dataflow graph cho quy trình đọc dữ liệu, chuẩn hóa, lọc và tổng hợp kết quả như thế nào?
Bạn giải thích điều kiện nào cho phép một node thực thi khi dữ liệu đầu vào của nó đã sẵn sàng ra sao?
Bạn phân biệt data-driven execution với control-driven execution dựa trên nguyên nhân kích hoạt một tác vụ như thế nào?
Bạn dựa trên những tiêu chí nào để chọn dataflow graph thay vì chuỗi lời gọi hàm lồng nhau?
Bạn xác định những trường hợp dataflow graph làm mã khó theo dõi hơn một chuỗi bước tuần tự đơn giản ra sao?
Bạn phân biệt static dataflow graph và dynamic dataflow graph khi tập tác vụ có thể thay đổi trong lúc chạy như thế nào?
Bạn giải thích cách sử dụng thứ tự topo để lập lịch các node trong một dataflow DAG như thế nào?
Bạn phát hiện một chu trình phụ thuộc không hợp lệ trong dataflow DAG và xác định những bước cần sửa như thế nào?
Bạn phân biệt chu trình phụ thuộc gây deadlock với vòng phản hồi có state hoặc delay được thiết kế chủ đích ra sao?
Bạn xây dựng mô hình dataflow có feedback loop để thực hiện phép lặp mà vẫn xác định điều kiện dừng như thế nào?
Bạn giải thích cách token, event hoặc record mang dữ liệu có thể kích hoạt node ở các mô hình dataflow khác nhau ra sao?
Bạn phân biệt dataflow xử lý một tập hữu hạn với streaming dataflow xử lý dòng sự kiện có thể không kết thúc như thế nào?
Bạn lựa chọn mô hình push hoặc pull khi nguồn và bộ xử lý có đặc tính tốc độ khác nhau ra sao?
Bạn phân tích ảnh hưởng của việc tách một phép tính thành nhiều node rất nhỏ đối với overhead lập lịch và truyền dữ liệu như thế nào?
Bạn thiết kế cách gộp những node đơn giản liên tiếp để giảm overhead nhưng vẫn giữ ranh giới quan sát cần thiết ra sao?
Bạn giải thích vì sao dataflow programming không tự động đồng nghĩa với thực thi song song trên nhiều lõi CPU như thế nào?
Bạn xác định những nhánh độc lập trong graph có thể chạy song song mà không thay đổi kết quả cuối cùng như thế nào?
Bạn phân biệt task parallelism giữa các node với data parallelism trên nhiều partition của cùng một node như thế nào?
Bạn đánh giá tác động của độ rộng graph và số lượng worker đến throughput khi có bottleneck ở một node như thế nào?
Bạn sử dụng critical path của DAG để ước lượng giới hạn giảm latency khi tăng mức song song như thế nào?
Bạn thiết kế cách mô hình hóa side effect trong graph để tránh thực thi lặp làm thay đổi kết quả nghiệp vụ ra sao?
Bạn phân biệt pure transformation với stateful operation khi muốn bảo đảm kết quả lặp lại từ cùng một input như thế nào?
Bạn phân tích những nguyên nhân khiến một pipeline nhìn như hàm thuần nhưng vẫn không deterministic khi chạy concurrent ra sao?
Bạn xác định những điều kiện nào để cache kết quả node theo input mà không bỏ sót phiên bản dữ liệu và cấu hình?
Bạn thiết kế cách truyền metadata về nguồn gốc, timestamp và correlation ID qua các edge để phục vụ truy vết ra sao?
Bạn lựa chọn hợp đồng dữ liệu cho từng edge nhằm tránh truyền object mutable dùng chung giữa các node như thế nào?
Bạn phân biệt việc truyền immutable value với việc truyền tham chiếu tới một buffer có thể bị thay đổi bởi node khác như thế nào?
Bạn phân tích cách side effect không được quản lý có thể làm một nhánh graph ảnh hưởng đến nhánh độc lập khác ra sao?
Bạn thiết kế một dataflow graph để tính hai chỉ số độc lập từ cùng tập sự kiện mà không xử lý dữ liệu nguồn dư thừa như thế nào?
Bạn giải thích mục đích của fan-out khi một giá trị nguồn cần được gửi tới nhiều nhánh xử lý ra sao?
Bạn phân biệt broadcast toàn bộ dữ liệu với partition theo key khi phân phối input cho nhiều worker như thế nào?
Bạn thiết kế phép fan-in nhận kết quả từ nhiều node và xác định điều kiện để một downstream node bắt đầu xử lý ra sao?
Bạn phân biệt join chờ tất cả input với merge phát ra phần tử ngay khi từng nhánh có dữ liệu như thế nào?
Bạn giải thích sự khác nhau giữa zip hai luồng theo vị trí phần tử và combine-latest theo trạng thái giá trị mới nhất ra sao?
Bạn lựa chọn zip hay merge khi hai nguồn có tốc độ phát không đều và độ dài có thể khác nhau như thế nào?
Bạn phân tích rủi ro một nhánh fan-in chậm khiến nhánh còn lại phải buffer ngày càng nhiều dữ liệu như thế nào?
Bạn thiết kế logic timeout hoặc giá trị dự phòng khi một node fan-in không nhận được một trong các kết quả phụ thuộc ra sao?
Bạn xác định cách bảo toàn tương quan giữa phản hồi từ các nhánh fan-out thuộc nhiều request chạy đồng thời như thế nào?
Bạn phân biệt phép join theo khóa nghiệp vụ với phép join chỉ dựa trên thứ tự phần tử đi tới như thế nào?
Bạn thiết kế cách phân biệt inner join và outer join khi một record không có đối tác ghép từ luồng thứ hai như thế nào?
Bạn phân tích giới hạn của join trên hai luồng vô hạn khi hệ thống không có ranh giới thời gian hoặc cơ chế dọn state ra sao?
Bạn lựa chọn keyed join, lookup join hoặc enrichment bất đồng bộ theo đặc điểm dữ liệu tham chiếu như thế nào?
Bạn thiết kế node loại bản ghi trùng trước phép join mà không loại nhầm các sự kiện hợp lệ giống nội dung ra sao?
Bạn phân biệt bản ghi đến muộn với bản ghi bị mất khi hai luồng được ghép theo event time như thế nào?
Bạn giải thích sự khác nhau giữa processing time và event time khi tính các chỉ số từ luồng sự kiện ra sao?
Bạn mô tả vai trò của watermark trong việc ước lượng tiến độ event time của một stream processor như thế nào?
Bạn thiết kế chiến lược xử lý late events khi dữ liệu đến sau watermark nhưng vẫn có giá trị nghiệp vụ ra sao?
Bạn phân biệt fixed window, sliding window và session window theo cách nhóm phần tử theo thời gian như thế nào?
Bạn lựa chọn tumbling window hay sliding window khi báo cáo cần thống kê không chồng lắp hoặc cập nhật theo thời gian trượt ra sao?
Bạn giải thích vì sao window theo số phần tử khác window theo thời gian về lượng dữ liệu và điều kiện đóng window như thế nào?
Bạn thiết kế phép tổng hợp theo key và window sao cho state được giải phóng khi không còn cần thiết ra sao?
Bạn phân tích hệ quả của clock skew giữa các nguồn dữ liệu phân tán lên phép ghép và tổng hợp theo thời gian như thế nào?
Bạn lựa chọn chính sách cập nhật kết quả khi một late event làm thay đổi giá trị của window đã phát ra ra sao?
Bạn phân biệt append-only result với retract hoặc upsert result khi các window có thể được tính lại như thế nào?
Bạn kiểm thử window aggregation với timestamp ở ranh giới, sự kiện trễ và trường hợp không có dữ liệu như thế nào?
Bạn phân tích ảnh hưởng của key cardinality cao đến kích thước state và hiệu năng của một node tổng hợp như thế nào?
Bạn thiết kế chính sách TTL hoặc state eviction mà không xóa dữ liệu còn cần cho một phép join hợp lệ ra sao?
Bạn giải thích vai trò của scheduler trong việc chọn node sẵn sàng thực thi khi nhiều node đồng thời nhận đủ input như thế nào?
Bạn phân biệt eager scheduling với demand-driven scheduling theo chi phí tính toán không cần thiết ra sao?
Bạn thiết kế thứ tự ưu tiên xử lý những node nằm trên critical path để giảm end-to-end latency như thế nào?
Bạn phân tích trường hợp node downstream không thể chạy dù upstream còn CPU nhàn rỗi do thiếu một dependency ra sao?
Bạn lựa chọn thread pool cho node CPU-bound và I/O-bound dựa trên tính chất blocking của từng stage như thế nào?
Bạn giải thích tại sao một scheduler không giới hạn số task có thể tạo hàng đợi lớn dù graph chỉ có ít loại node như thế nào?
Bạn thiết kế cơ chế giới hạn số tác vụ inflight tại một stage gọi API bên ngoài có quota như thế nào?
Bạn phân biệt task queue capacity với số phần tử stream đang được buffer giữa hai stage ra sao?
Bạn đánh giá rủi ro head-of-line blocking khi một worker phải xử lý các job có thời lượng rất khác nhau như thế nào?
Bạn lựa chọn work stealing hoặc phân phối theo partition cố định khi tải giữa các node không cân bằng như thế nào?
Bạn phân tích những rủi ro về thứ tự và tính xác định của kết quả khi các phần việc được chuyển giữa worker như thế nào?
Bạn xác định giới hạn tăng tốc khi một node tuần tự đứng giữa nhiều nhánh chạy song song ra sao?
Bạn thiết kế phép batching tại stage đắt đỏ để cân bằng throughput và thời gian chờ gom batch như thế nào?
Bạn phân biệt micro-batching với xử lý từng event theo ảnh hưởng đến độ trễ và khả năng khôi phục như thế nào?
Bạn đánh giá khi nào vectorized processing giúp giảm overhead so với xử lý record-by-record trong cùng pipeline ra sao?
Bạn giải thích backpressure giải quyết tình huống nguồn phát nhanh hơn khả năng xử lý của downstream như thế nào?
Bạn phân biệt cơ chế backpressure với việc chỉ tăng kích thước buffer dựa trên khả năng kiểm soát lượng dữ liệu tồn đọng ra sao?
Bạn thiết kế một bounded queue giữa producer và consumer để hệ thống chịu tải mà không cạn heap ra sao?
Bạn đánh giá ảnh hưởng của chiến lược block producer, drop event và reject request lên tính đúng đắn nghiệp vụ như thế nào?
Bạn lựa chọn drop-oldest, drop-latest hoặc gửi lỗi khi dashboard chỉ cần giá trị gần đây so với hệ thống tài chính cần đủ mọi sự kiện như thế nào?
Bạn thiết kế cơ chế truyền tín hiệu downstream demand ngược lên upstream trong pipeline nhiều stage như thế nào?
Bạn phân biệt rate limiting tại nguồn với flow control theo dung lượng còn lại của consumer ra sao?
Bạn giải thích tại sao tăng kích thước buffer chỉ trì hoãn sự cố nếu tốc độ đến duy trì cao hơn tốc độ xử lý như thế nào?
Bạn xác định dấu hiệu quá tải qua queue depth, queue age và số lượng inflight records như thế nào?
Bạn thiết kế policy xử lý khi downstream ngừng nhận dữ liệu nhưng upstream không thể tạm dừng hoàn toàn ra sao?
Bạn phân tích ảnh hưởng của backpressure tới fairness khi nhiều tenant cùng dùng một pipeline như thế nào?
Bạn lựa chọn partitioned queues để tránh một nguồn chậm hoặc nóng làm nghẽn các nguồn độc lập ra sao?
Bạn đánh giá nguy cơ deadlock khi hai stage tạo vòng feedback cùng chờ buffer của nhau có chỗ trống như thế nào?
Bạn thiết kế cơ chế timeout và cancellation cho thao tác chờ buffer mà không để mất dữ liệu đã được xác nhận xử lý ra sao?
Bạn giải thích vì sao khối lượng dữ liệu tồn đọng có thể gây áp lực lên bộ nhớ ngay cả khi CPU usage thấp như thế nào?
Bạn tính toán giới hạn bộ nhớ cho buffer dựa trên kích thước bản ghi, số partition và lượng dữ liệu inflight như thế nào?
Bạn phân biệt mục tiêu latency với throughput khi chọn kích thước batch và giới hạn buffer như thế nào?
Bạn thiết kế cơ chế đo thời gian từ lúc nhận event đến lúc kết quả được phát để đánh giá backpressure thực sự ra sao?
Bạn mô tả cách CompletableFuture biểu diễn một node kết quả phụ thuộc vào tác vụ bất đồng bộ khác như thế nào?
Bạn phân biệt CompletableFuture.thenApply với thenCompose khi node kế tiếp trả ra giá trị trực tiếp hay một Future khác như thế nào?
Bạn thiết kế đồ thị Future dùng thenCombine để ghép hai nhánh độc lập trước khi chuyển sang bước tổng hợp như thế nào?
Bạn lựa chọn allOf hoặc anyOf khi một node cần chờ toàn bộ kết quả hoặc chỉ một nhánh đáp ứng trước ra sao?
Bạn giải thích cách exception của một upstream Future ảnh hưởng đến các stage downstream chưa chạy như thế nào?
Bạn thiết kế cơ chế fallback hoặc xử lý partial results khi một trong ba nhánh CompletableFuture bị lỗi ra sao?
Bạn phân biệt exceptionally, handle và whenComplete theo việc thay đổi kết quả hay chỉ quan sát trạng thái lỗi như thế nào?
Bạn giải thích vì sao thenApply không mặc định thực thi trên một thread mới khi upstream hoàn thành như thế nào?
Bạn lựa chọn thenApplyAsync với executor chỉ định khi một phép biến đổi có thể chặn hoặc tiêu tốn nhiều CPU như thế nào?
Bạn phân tích nguy cơ thread starvation khi một stage của CompletableFuture dùng join để chờ công việc được xếp vào cùng executor nhỏ ra sao?
Bạn thiết kế graph CompletableFuture có giới hạn concurrency khi mỗi node thực hiện network request như thế nào?
Bạn phân biệt timeout trên Future của bước cuối với cancellation thật sự của các tác vụ upstream đang chạy như thế nào?
Bạn thiết kế deadline chung cho toàn graph và xử lý việc dừng các nhánh chưa hoàn tất ra sao?
Bạn phân tích những giới hạn của CompletableFuture khi cần xử lý dòng phần tử dài liên tục thay vì một kết quả duy nhất như thế nào?
Bạn lựa chọn CompletableFuture hay API Reactive Streams cho luồng xử lý hữu hạn nhiều bước và luồng dữ liệu liên tục theo tiêu chí nào?
Bạn giải thích cách biến một đồ thị Future thành tập tác vụ dễ quan sát với tên stage và thời gian chờ cụ thể như thế nào?
Bạn kiểm thử một graph CompletableFuture bằng các Future được điều khiển thủ công để ép thứ tự hoàn thành khác nhau ra sao?
Bạn thiết kế test cho fan-in CompletableFuture khi một nhánh lỗi sớm và các nhánh khác hoàn thành muộn ra sao?
Bạn phân tích vì sao callback có side effect có thể chạy hai lần trong logic retry bên ngoài Future nếu không kiểm soát idempotency như thế nào?
Bạn mô tả mô hình Publisher, Subscriber, Subscription và Processor của Reactive Streams theo quan hệ truyền dữ liệu như thế nào?
Bạn phân biệt luồng dữ liệu Publisher phát ra nhiều phần tử với Future thường biểu diễn một kết quả như thế nào?
Bạn giải thích vai trò của Subscription.request trong việc thể hiện demand từ subscriber tới publisher ra sao?
Bạn thiết kế subscriber chỉ yêu cầu thêm phần tử sau khi đã xử lý một phần dữ liệu được cấp như thế nào?
Bạn giải thích tại sao publisher phát onNext vượt số phần tử được yêu cầu qua Subscription.request lại vi phạm hợp đồng Reactive Streams?
Bạn phân biệt request với số lượng âm hoặc bằng không và request hợp lệ theo yêu cầu của Reactive Streams như thế nào?
Bạn phân tích yêu cầu tuần tự hóa các tín hiệu onNext, onError và onComplete đối với cùng một subscriber ra sao?
Bạn thiết kế cách kết thúc stream bằng onComplete khi không còn dữ liệu mà không phát tín hiệu tiếp theo ra sao?
Bạn phân biệt onError với một bản ghi lỗi nghiệp vụ được biểu diễn như dữ liệu bình thường trong stream như thế nào?
Bạn phân tích cách một subscriber dùng cancel để ngừng nhận phần tử và những nguồn lực publisher cần giải phóng như thế nào?
Bạn giải thích tại sao onSubscribe phải diễn ra trước khi subscriber nhận dữ liệu hoặc tín hiệu kết thúc như thế nào?
Bạn thiết kế subscriber xử lý từng message mà không block thread gọi callback quá lâu như thế nào?
Bạn phân biệt thread safety của một Publisher với khả năng nhiều subscriber nhận tín hiệu độc lập như thế nào?
Bạn xác định cách quản lý demand riêng cho mỗi subscriber khi cùng đăng ký vào một nguồn dữ liệu như thế nào?
Bạn so sánh cold publisher với hot publisher theo thời điểm bắt đầu phát và khả năng subscriber bỏ lỡ dữ liệu ra sao?
Bạn đánh giá cách chia sẻ một hot stream cho nhiều consumer có tốc độ khác nhau mà không để consumer chậm kéo bộ nhớ tăng vô hạn như thế nào?
Bạn thiết kế pipeline Publisher qua Processor rồi đến Subscriber có thể truyền demand qua nhiều tầng như thế nào?
Bạn phân biệt map và filter trên reactive pipeline theo cách cập nhật demand khi một phần tử bị loại bỏ ra sao?
Bạn phân tích tác động của operator flatMap phát nhiều inner publisher đến thứ tự kết quả và số phần tử inflight như thế nào?
Bạn thiết kế cơ chế giới hạn concurrency của flatMap để tránh tạo quá nhiều tác vụ mạng đồng thời ra sao?
Bạn lựa chọn concatMap thay vì flatMap khi thứ tự giữa các bản ghi có ý nghĩa nghiệp vụ như thế nào?
Bạn đánh giá những rủi ro khi trộn API blocking và non-blocking trong reactive stage trên event-loop như thế nào?
Bạn xác định cách chuyển công việc blocking sang scheduler thích hợp mà vẫn tránh tạo số thread không giới hạn ra sao?
Bạn giải thích java.util.concurrent.Flow là API chuẩn thể hiện các interface Reactive Streams từ Java 9 và khác thư viện reactive đầy đủ như thế nào?
Bạn lựa chọn SubmissionPublisher cho một ví dụ đơn giản và xác định những giới hạn khi dùng nó làm hệ thống event streaming production như thế nào?
Bạn phân tích cơ chế buffer và xử lý chậm của SubmissionPublisher theo chính sách chờ hoặc xử lý phần tử bị bỏ ra sao?
Bạn thiết kế test Subscriber cho trường hợp request từng phần, cancel sớm và lỗi ở publisher như thế nào?
Bạn kiểm chứng các tín hiệu reactive không bị phát sau onError hoặc onComplete bằng bộ test nào?
Bạn phân biệt reactive backpressure ở mức giao thức với việc chỉ đặt bounded queue ở một stage nội bộ như thế nào?
Bạn lựa chọn giải pháp Flow API, Reactor hoặc RxJava theo nhu cầu operator, scheduling, tích hợp và độ phức tạp vận hành ra sao?
Bạn chẩn đoán vì sao một reactive pipeline lazy không thực hiện phép xử lý khi chưa có subscriber và demand như thế nào?
Bạn thiết kế cơ chế propagation correlation context qua các callback reactive khi thread có thể thay đổi giữa các stage ra sao?
Bạn giải thích vì sao ThreadLocal không phải luôn là cách đáng tin cậy để giữ request context trong reactive execution như thế nào?
Bạn đánh giá thời điểm cần chuyển từ API push không có demand thành reactive Publisher có backpressure như thế nào?
Bạn phân biệt trạng thái local của một node với state được chia sẻ giữa nhiều instance của node trong xử lý phân tán như thế nào?
Bạn thiết kế chiến lược partition theo key để mọi event của cùng entity tới đúng worker giữ state tương ứng ra sao?
Bạn phân tích tình huống phân phối key không đều gây data skew và làm một partition thành bottleneck như thế nào?
Bạn lựa chọn hash partitioning, range partitioning hoặc custom partitioner theo khả năng cân tải và bảo đảm thứ tự như thế nào?
Bạn xác định rủi ro thay đổi số partition khiến một key được chuyển sang worker khác trong khi state cũ chưa được di dời ra sao?
Bạn thiết kế quy trình rescale pipeline có state để chuyển ownership giữa worker mà không mất hoặc nhân đôi cập nhật như thế nào?
Bạn phân biệt operator state với keyed state theo cách checkpoint và phục hồi khi thay đổi số worker ra sao?
Bạn giải thích vì sao checkpoint cần phản ánh một trạng thái nhất quán giữa nhiều node và các dữ liệu đang nằm trên edge như thế nào?
Bạn thiết kế cơ chế checkpoint cho graph nhiều nhánh để tránh ghi nhận state không tương thích với vị trí đọc nguồn như thế nào?
Bạn phân biệt aligned checkpoint và unaligned checkpoint theo ảnh hưởng của backpressure tới thời gian tạo checkpoint ra sao?
Bạn xác định cách khôi phục nguồn phát từ offset cùng snapshot state khi một worker gặp sự cố như thế nào?
Bạn phân tích mối liên hệ giữa retry, replay và việc một event có thể được xử lý nhiều lần trong pipeline như thế nào?
Bạn phân biệt at-most-once và at-least-once delivery khi nguồn hoặc processor có thể bị mất kết nối ra sao?
Bạn giải thích vì sao exactly-once state update bên trong stream engine không tự bảo đảm external side effect chỉ xảy ra một lần như thế nào?
Bạn thiết kế sink idempotent dùng event ID để tránh ghi trùng khi pipeline đọc lại một đoạn dữ liệu ra sao?
Bạn lựa chọn transactional sink hoặc cơ chế ghi có điều kiện khi yêu cầu tính nhất quán giữa kết quả và offset nguồn như thế nào?
Bạn phân tích rủi ro một sink ghi thành công nhưng processor chết trước khi xác nhận checkpoint như thế nào?
Bạn thiết kế cơ chế dead-letter queue khi một record lỗi không thể xử lý dù đã retry trong giới hạn như thế nào?
Bạn phân biệt lỗi tạm thời cần retry với lỗi dữ liệu không hợp lệ cần cô lập để tránh tắc toàn pipeline như thế nào?
Bạn lựa chọn retry backoff và jitter để tránh tạo retry storm khi nhiều partition cùng gặp lỗi dependency như thế nào?
Bạn xác định cách đặt timeout cho một node phân tán sao cho thất bại được truyền về các nhánh phụ thuộc mà không treo graph ra sao?
Bạn thiết kế xử lý poison message giữ nguyên thông tin nguồn nhưng không để cùng bản ghi vô hạn ngăn các record phía sau như thế nào?
Bạn đánh giá rủi ro khi một pipeline phụ thuộc trạng thái cục bộ không được lưu checkpoint và kết quả sai sau khi worker restart ra sao?
Bạn thiết kế cơ chế phát hiện duplicate event mà không lưu vô hạn toàn bộ định danh từ quá khứ như thế nào?
Bạn phân biệt tính nhất quán của event-time aggregation với consistency của database chứa kết quả cuối ra sao?
Bạn đánh giá sự khác nhau giữa event ordering theo từng partition và thứ tự toàn cục của một pipeline phân tán như thế nào?
Bạn xác định khi nào cần giữ thứ tự per-key và khi nào có thể cho phép out-of-order để tăng mức song song như thế nào?
Bạn giải thích ảnh hưởng của network partition và transient failure đối với độ trễ fan-in khi các node chạy trên nhiều máy như thế nào?
Bạn thiết kế chính sách phân loại kết quả đầy đủ, kết quả từng phần và thất bại khi một node upstream không truy cập được như thế nào?
Bạn lựa chọn schema versioning và chiến lược tương thích khi producer và consumer được triển khai ở các thời điểm khác nhau ra sao?
Bạn phân tích rủi ro thay đổi kiểu field hoặc đơn vị đo ở một edge làm các node downstream diễn giải sai dữ liệu như thế nào?
Bạn thiết kế phép validation trên ranh giới node để phát hiện schema mismatch trước khi dữ liệu đi sâu vào pipeline như thế nào?
Bạn đánh giá khi nào có thể deploy lại riêng một node và khi nào thay đổi hợp đồng dữ liệu đòi hỏi phối hợp nhiều node như thế nào?
Bạn thiết kế cách cache hoặc materialize output trung gian để giảm tính lại sau lỗi mà vẫn bảo đảm cache key phản ánh phiên bản xử lý ra sao?
Bạn xác định những rủi ro bảo mật khi một node xử lý dữ liệu nhạy cảm rồi phát cả payload vào trace hoặc metrics như thế nào?
Bạn phân tích cách phân quyền truy cập giữa các stage phân tán khi pipeline dùng nhiều credential và backend khác nhau như thế nào?
Bạn lựa chọn mô hình cô lập tenant trong dataflow khi không muốn luồng dữ liệu của tenant này làm nghẽn hoặc lộ dữ liệu tenant khác ra sao?
Bạn thiết kế test đơn vị cho một node thuần dữ liệu với input, output và xử lý lỗi độc lập scheduler như thế nào?
Bạn xây dựng bộ kiểm thử tính đúng của graph fan-out/fan-in với các thứ tự hoàn thành upstream khác nhau ra sao?
Bạn sử dụng virtual clock hoặc test scheduler để kiểm tra timeout và window mà không phụ thuộc vào Thread.sleep như thế nào?
Bạn mô phỏng consumer chậm để xác minh backpressure giới hạn kích thước buffer và không làm mất record ngoài chính sách như thế nào?
Bạn thiết kế property-based test cho pipeline để kiểm tra tính bất biến của tổng số lượng hoặc tổng giá trị khi chia partition khác nhau ra sao?
Bạn phân tích vì sao stress test chạy thành công không đủ chứng minh graph không có race hoặc deadlock như thế nào?
Bạn xác định cách tái hiện một lỗi nondeterministic bằng input cố định, kiểm soát scheduling và ghi dấu sự kiện ra sao?
Bạn thiết kế integration test làm worker crash ngay giữa checkpoint và sink commit để xác minh hành vi replay ra sao?
Bạn kiểm tra khả năng khôi phục state của một operator sau khi tăng hoặc giảm số worker qua những kịch bản nào?
Bạn xây dựng bài kiểm thử schema evolution giữa hai phiên bản producer và consumer được chạy đồng thời như thế nào?
Bạn phân biệt unit test của từng node với end-to-end test của cả graph về những lỗi mà mỗi loại có thể phát hiện ra sao?
Bạn thiết kế sơ đồ quan sát graph với throughput, latency và error rate tại từng node để xác định bottleneck như thế nào?
Bạn xác định cách đo queue wait, processing time và end-to-end lag riêng biệt trong một stream pipeline ra sao?
Bạn phân tích vì sao downstream lag tăng dù upstream processing time thấp khi bottleneck nằm ở network hoặc buffer như thế nào?
Bạn lựa chọn những metrics về demand, requested count và pending signals để chẩn đoán reactive subscriber không tiêu thụ dữ liệu ra sao?
Bạn thiết kế distributed tracing qua các stage bất đồng bộ bằng correlation ID và span relationships như thế nào?
Bạn đánh giá tác động của sampling tracing tới khả năng quan sát một lỗi xảy ra hiếm gặp trong dataflow graph như thế nào?
Bạn sử dụng critical path tracing để xác định node đang quyết định latency cuối cùng của một request fan-out như thế nào?
Bạn phân tích lý do p99 latency của pipeline không bằng tổng đơn giản p99 latency của từng node ra sao?
Bạn thiết kế benchmark so sánh sequential pipeline, CompletableFuture graph và reactive pipeline trên cùng workload đại diện như thế nào?
Bạn xác định cách cô lập ảnh hưởng của CPU, bộ nhớ, network và external service khi đo hiệu năng một dataflow graph ra sao?
Bạn lựa chọn tối ưu operator fusion, batching hoặc partitioning sau khi metrics cho thấy một stage tiêu tốn phần lớn thời gian như thế nào?
Bạn giải thích ảnh hưởng của serialization overhead tới throughput khi các node chạy ở tiến trình khác nhau so với cùng JVM như thế nào?
Bạn thiết kế graceful shutdown cho pipeline để ngừng nhận event mới, xử lý hết phần đang chờ và giải phóng tài nguyên như thế nào?
Bạn xác định điều kiện kết thúc của một batch DAG và sự khác nhau với việc đóng một streaming pipeline vô hạn ra sao?
Bạn xây dựng quy trình rollout một thay đổi graph qua canary và so sánh checksum kết quả để phát hiện semantic regression như thế nào?
Một graph có hai node chờ đầu ra của nhau khiến pipeline dừng tiến triển, bạn sẽ tìm chu trình và thiết kế lại feedback như thế nào?
Một phép join trên hai stream liên tục làm state tăng không giới hạn, bạn sẽ xác định ranh giới window và chính sách eviction ra sao?
Một producer gửi event nhanh gấp nhiều lần consumer khiến heap liên tục tăng, bạn sẽ bổ sung demand hoặc backpressure tại ranh giới nào?
Một subscriber gọi Subscription.request với giá trị không hợp lệ rồi nhận lỗi terminal, bạn sẽ kiểm tra hợp đồng Reactive Streams và sửa code như thế nào?
Một graph CompletableFuture bị treo vì callback block trên executor nhỏ, bạn sẽ phân tích phụ thuộc và cấu hình scheduler ra sao?
Một pipeline phân tán tạo kết quả trùng sau khi worker crash và replay, bạn sẽ kiểm tra checkpoint, offset và idempotent sink như thế nào?
Một phép tổng hợp theo event time bỏ sót sự kiện đến muộn, bạn sẽ kiểm tra watermark và chính sách cập nhật window như thế nào?
Một partition chứa key nóng làm throughput toàn pipeline giảm mạnh, bạn sẽ đo data skew và điều chỉnh partitioning như thế nào?
Một bản cập nhật schema làm node downstream đọc sai đơn vị dữ liệu dù chương trình không ném exception, bạn sẽ thiết kế validation và compatibility test ra sao?
Một pipeline reactive chạy đúng khi một subscriber đăng ký nhưng bị nghẽn khi có thêm subscriber chậm, bạn sẽ kiểm tra demand và chiến lược multicast ra sao?
Bạn xây dựng checklist review dataflow programming gồm graph dependencies, scheduling, state ownership, backpressure, failure recovery, observability và kiểm thử như thế nào?
