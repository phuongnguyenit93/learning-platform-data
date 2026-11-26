Bạn giải thích Stream API khác Collection về cách lưu trữ và xử lý các phần tử như thế nào?
Bạn mô tả source, intermediate operations và terminal operation tạo thành một Stream pipeline ra sao?
Bạn phân biệt lazy evaluation với eager computation khi viết chuỗi filter và map như thế nào?
Bạn sẽ xác định thời điểm các callback trong pipeline thực sự được thực thi theo terminal operation nào?
Bạn phân tích vì sao khai báo pipeline mà không gọi terminal operation thường không làm dữ liệu biến đổi ra sao?
Bạn mô tả internal iteration của Stream khác external iteration bằng vòng for như thế nào?
Bạn sẽ tạo Stream từ List, array, Stream.of và Stream.builder theo mục đích nào?
Bạn phân biệt Arrays.stream trên mảng int và mảng Integer về loại Stream nhận được ra sao?
Bạn sẽ dùng Stream.ofNullable trên JDK hỗ trợ khi một reference đầu vào có thể null như thế nào?
Bạn phân biệt Stream.generate với Stream.iterate khi tạo nguồn phần tử không biết trước số lượng ra sao?
Bạn sẽ dùng Stream.iterate có predicate dừng để tạo nguồn hữu hạn ở phiên bản JDK hỗ trợ như thế nào?
Bạn phân tích nguy cơ collect một infinite Stream không có limit hoặc short-circuit như thế nào?
Bạn sẽ giải thích vì sao Stream không được dùng lại sau khi terminal operation đã tiêu thụ ra sao?
Bạn sẽ thiết kế Supplier<Stream<T>> cho phép tạo nguồn mới mỗi lần thay vì tái sử dụng Stream cũ như thế nào?
Bạn phân biệt Stream được consumed với Stream được close theo lifecycle và bảo đảm API nào?
Bạn sẽ nhận diện encounter order của Stream tạo từ List, HashSet và LinkedHashSet như thế nào?
Bạn mô tả sự khác nhau giữa ordered Stream và việc callbacks chạy đúng thứ tự khi parallel như thế nào?
Bạn phân tích vì sao không thể coi một pipeline lazy là luôn tiết kiệm bộ nhớ nếu source đã nạp toàn bộ dữ liệu ra sao?
Bạn sẽ xác định khi nào lưu kết quả trung gian vào List giúp thuật toán dễ hiểu hơn một Stream chain như thế nào?
Bạn phân biệt Stream tuần tự và Stream song song ở semantics yêu cầu bảo toàn của kết quả như thế nào?
Bạn sẽ đánh giá vì sao side effects của lambda có thể phá non-interference với nguồn Stream ra sao?
Bạn mô tả việc source Collection bị sửa trong khi traversal có thể dẫn tới kết quả không xác định hoặc lỗi như thế nào?
Bạn sẽ chọn Stream hay vòng lặp imperative khi quy trình có nhiều nhánh và yêu cầu dừng sớm theo tiêu chí nào?
Bạn phân tích vì sao Stream không mặc định thay thế việc pagination dữ liệu ở tầng database như thế nào?
Bạn phân biệt filter với map theo thay đổi số phần tử và kiểu đầu ra như thế nào?
Bạn sẽ xây pipeline lọc records hợp lệ rồi ánh xạ thành DTO mà không mutate input ra sao?
Bạn mô tả map giữ quan hệ một-đổi-một còn flatMap hỗ trợ một-đổi-nhiều theo cơ chế nào?
Bạn sẽ dùng flatMap để biến danh sách đơn hàng thành luồng các dòng hàng như thế nào?
Bạn phân biệt map trả Stream<Stream<T>> với flatMap trả Stream<T> theo công dụng nào?
Bạn sẽ kiểm tra lý do flatMap có thể tạo nhiều Stream con ngắn sống và làm tăng allocation cost ra sao?
Bạn mô tả cách flatMap đóng các Stream con sau khi nội dung được sử dụng theo vòng đời nào?
Bạn sẽ dùng Stream.mapMulti khi cần phát zero hoặc nhiều kết quả mà không tạo Stream con như thế nào?
Bạn phân biệt mapMulti và flatMap khi triển khai bộ lọc sinh thêm bản ghi theo performance nào?
Bạn sẽ lựa chọn mapMultiToInt khi output là primitive int thay vì Integer như thế nào?
Bạn phân tích vì sao mapper ném exception làm pipeline dừng trước khi hết dữ liệu theo cách nào?
Bạn sẽ thay map có tác dụng sửa collection ngoài bằng collect theo hợp đồng nào?
Bạn mô tả chức năng peek trong Stream và rủi ro nếu dùng nó để bảo đảm ghi audit như thế nào?
Bạn phân tích vì sao một callback peek có thể không chạy nếu terminal operation được tối ưu ra sao?
Bạn sẽ giải thích distinct dùng equals và hashCode để xác định phần tử trùng như thế nào?
Bạn sẽ chẩn đoán distinct trả kết quả sai khi equals/hashCode của domain object không nhất quán ra sao?
Bạn phân tích memory cost của distinct khi source chứa hàng triệu giá trị khác nhau như thế nào?
Bạn sẽ dùng sorted với Comparator.comparing và thenComparing để sắp xếp nhiều tiêu chí như thế nào?
Bạn mô tả sorted khác filter ở việc phải duy trì trạng thái và có thể cần buffer phần tử ra sao?
Bạn phân biệt sorted ổn định trên ordered Stream với các phần tử so sánh bằng nhau theo bảo đảm nào?
Bạn sẽ dùng Stream.concat để kết hợp hai nguồn mà không mutate những collections ban đầu ra sao?
Bạn phân tích vì sao lồng quá nhiều Stream.concat có thể khiến pipeline khó đọc hoặc kém hiệu quả như thế nào?
Bạn sẽ quyết định cách xử lý null trước khi gọi sorted hoặc distinct trên source có giá trị khuyết như thế nào?
Bạn mô tả sự khác nhau giữa các stateless intermediate operations và stateful intermediate operations như thế nào?
Bạn giải thích limit và skip xử lý phần tử thế nào khi Stream có encounter order như thế nào?
Bạn phân biệt takeWhile với filter khi điều kiện không thỏa ở giữa một ordered Stream ra sao?
Bạn sẽ dùng dropWhile để bỏ một tiền tố dữ liệu thay vì lọc tất cả phần tử thỏa điều kiện như thế nào?
Bạn mô tả hành vi takeWhile trên unordered Stream có thể khác trực giác về tiền tố ra sao?
Bạn sẽ chọn findFirst thay vì findAny khi yêu cầu kết quả theo thứ tự đầu vào như thế nào?
Bạn phân biệt findAny với findFirst khi cho phép thực thi parallel như thế nào?
Bạn sẽ dùng anyMatch để dừng sớm ngay khi tìm thấy phần tử đáp ứng điều kiện như thế nào?
Bạn sẽ giải thích kết quả của allMatch và noneMatch khi Stream rỗng theo quy tắc logic nào?
Bạn phân tích vì sao short-circuit terminal operation không nhất thiết đánh giá hết mọi input ra sao?
Bạn sẽ kiểm thử predicate của anyMatch mà không giả định số lần callback chính xác như thế nào?
Bạn phân biệt forEach với forEachOrdered trong việc bảo đảm encounter order khi parallel ra sao?
Bạn sẽ xử lý Stream.findFirst trên một nguồn chứa null để tránh lỗi khi tạo Optional như thế nào?
Bạn mô tả min và max trả Optional nhằm biểu diễn nguồn không có phần tử như thế nào?
Bạn sẽ cân nhắc gọi unordered trước limit nếu business không cần encounter order như thế nào?
Bạn phân tích tại sao ordered parallel skip và limit có thể gây chi phí phối hợp giữa các tasks ra sao?
Bạn sẽ giải thích vì sao count có thể sử dụng thông tin kích thước source thay vì gọi mọi callback trong peek như thế nào?
Bạn sẽ xác định loại side effects nào không được đặt vào peek nếu muốn kết quả không phụ thuộc stream optimization ra sao?
Bạn mô tả Stream.toList tạo kết quả với đặc tính mutability nào ở JDK hỗ trợ như thế nào?
Bạn phân biệt Stream.toList với Collectors.toList về loại Collection và cam kết API ra sao?
Bạn sẽ sử dụng Collectors.toCollection để nhận ArrayList mutable khi cần cập nhật sau pipeline như thế nào?
Bạn phân tích vì sao Collections.unmodifiableList và một snapshot immutable không đồng nghĩa khi nguồn còn thay đổi ra sao?
Bạn sẽ thiết kế pagination ở data source thay vì kỳ vọng skip và limit trên Stream đã load hết nguồn theo tiêu chí nào?
Bạn mô tả tính không ổn định của findAny nếu dùng kết quả đó làm quyết định nghiệp vụ cần deterministic như thế nào?
Bạn sẽ chọn ordered sequential Stream hoặc explicit sort khi kết quả phải tái lập được qua nhiều lần chạy ra sao?
Bạn giải thích reduce với identity và accumulator thu gọn Stream thành một giá trị như thế nào?
Bạn phân biệt reduce không identity trả Optional với reduce có identity trả giá trị thường ra sao?
Bạn sẽ lựa chọn identity trung tính khi gộp các số nguyên, chuỗi hoặc tập hợp theo phép toán nào?
Bạn mô tả yêu cầu associative của accumulator để phép reduce có thể chạy song song như thế nào?
Bạn phân tích vì sao dùng phép trừ trong parallel reduce có thể cho kết quả khác sequential như thế nào?
Bạn sẽ viết reduction ba tham số để tạo kết quả kiểu U khác kiểu phần tử T như thế nào?
Bạn mô tả yêu cầu tương thích giữa combiner và accumulator trong reduce ba tham số ra sao?
Bạn sẽ phân biệt reduce với collect khi kết quả là một mutable List hoặc Map như thế nào?
Bạn phân tích vì sao mutable accumulator dùng sai trong reduce song song có thể làm mất dữ liệu ra sao?
Bạn sẽ dùng Integer.sum thay cho phép cộng lambda trong reduction khi nào?
Bạn mô tả IntStream, LongStream và DoubleStream giúp giảm boxing theo cách nào?
Bạn sẽ dùng mapToInt và IntStream.sum khi tổng hợp trường số của đối tượng như thế nào?
Bạn phân biệt mapToObj với boxed trên primitive Stream theo loại kết quả nào?
Bạn sẽ dùng IntStream.range và rangeClosed khi cần biên trái/phải của một dãy như thế nào?
Bạn mô tả OptionalInt và OptionalDouble từ min hoặc average khác số 0 hợp lệ như thế nào?
Bạn sẽ xử lý average trên Stream rỗng mà không báo cáo nhầm giá trị mặc định như thế nào?
Bạn phân tích nguy cơ overflow của IntStream.sum khi nguồn chứa nhiều số lớn như thế nào?
Bạn sẽ lựa chọn LongStream hay BigDecimal khi cộng các khoản tiền vượt phạm vi int như thế nào?
Bạn mô tả summaryStatistics giúp tính count, min, max, sum và average trong một lần duyệt ra sao?
Bạn phân tích vì sao floating-point reduction có thể lệch ở bit thấp khi thay đổi thứ tự cộng như thế nào?
Bạn sẽ kiểm thử phép gộp với số âm, số cực trị, NaN và infinity theo yêu cầu domain nào?
Bạn phân biệt DoubleStream.average với phép chia tổng theo số lượng phần tử trong các trường hợp biên ra sao?
Bạn sẽ cân nhắc short-circuit trước khi giảm toàn bộ source để tránh xử lý dữ liệu không cần thiết như thế nào?
Bạn phân tích vì sao thay đổi thứ tự cộng BigDecimal có thể khác với các quy tắc làm tròn được đặt theo từng bước ra sao?
Bạn giải thích collect terminal operation khác reduce ở khả năng tích lũy mutable container như thế nào?
Bạn sẽ dùng Collectors.toList, toSet và toCollection khi cần định dạng output khác nhau ra sao?
Bạn phân biệt toUnmodifiableList với Collectors.toList về tính bất biến và xử lý null như thế nào?
Bạn sẽ dùng Collectors.joining với delimiter, prefix và suffix để tạo chuỗi kết quả như thế nào?
Bạn mô tả Collectors.groupingBy tạo nhóm theo classifier vào một Map như thế nào?
Bạn sẽ kết hợp groupingBy với counting để đếm số bản ghi theo mỗi trạng thái ra sao?
Bạn phân biệt groupingBy với partitioningBy khi phép phân nhóm chỉ có hai giá trị boolean ra sao?
Bạn sẽ sử dụng Collectors.mapping làm downstream collector để nhóm key nhưng thu values đã biến đổi ra sao?
Bạn mô tả Collectors.filtering khác với filter toàn Stream trước groupingBy theo số nhóm kết quả như thế nào?
Bạn sẽ dùng Collectors.flatMapping để gom các phần tử con vào mỗi nhóm mà không tạo nested lists như thế nào?
Bạn phân tích vì sao groupingBy gặp lỗi khi classifier trả null và cách thiết kế key đại diện ra sao?
Bạn sẽ xây Map bằng Collectors.toMap với keyMapper và valueMapper như thế nào?
Bạn sẽ giải quyết duplicate keys trong toMap bằng merge function dựa trên quy tắc nghiệp vụ ra sao?
Bạn phân biệt merge function chọn bản ghi đầu hoặc cuối khi nguồn không có thứ tự ổn định như thế nào?
Bạn sẽ truyền mapFactory cho groupingBy hoặc toMap khi cần LinkedHashMap giữ thứ tự keys ra sao?
Bạn mô tả Collectors.collectingAndThen hỗ trợ chuyển kết quả mutable sang immutable như thế nào?
Bạn sẽ dùng summingInt, averagingDouble và summarizingInt trong downstream aggregate theo yêu cầu nào?
Bạn phân tích giới hạn của tính average với dữ liệu floating-point và số lượng lớn như thế nào?
Bạn sẽ kết hợp groupingBy và Collectors.maxBy để tìm bản ghi lớn nhất của mỗi nhóm ra sao?
Bạn mô tả Collectors.reducing là downstream collector khác reduce trên Stream gốc như thế nào?
Bạn sẽ dùng Collectors.teeing ở JDK hỗ trợ để tổng hợp hai thống kê trong một lượt như thế nào?
Bạn phân biệt toConcurrentMap với toMap khi pipeline chạy song song theo container trả về ra sao?
Bạn sẽ chọn groupingByConcurrent khi kết quả không yêu cầu preserve encounter order như thế nào?
Bạn phân tích vì sao Map trả từ Collector không luôn bảo đảm iteration order nếu không chỉ định mapFactory ra sao?
Bạn sẽ viết test collectors cho nguồn rỗng, duplicate keys và null values theo bất biến nào?
Bạn mô tả bốn thành phần supplier, accumulator, combiner và finisher của Collector<T,A,R> như thế nào?
Bạn phân biệt intermediate accumulation type A với result type R khi thiết kế custom Collector ra sao?
Bạn sẽ tạo container mới trong supplier cho mỗi nhánh tích lũy để tránh shared mutable state như thế nào?
Bạn mô tả accumulator tiếp nhận một phần tử và cập nhật state trong container như thế nào?
Bạn sẽ thiết kế combiner gộp hai partial states mà không mất dữ liệu khi parallel ra sao?
Bạn phân tích vì sao custom Collector dù dùng sequential vẫn phải có combiner đúng contract như thế nào?
Bạn sẽ dùng finisher chuyển mutable builder thành immutable result object theo yêu cầu nào?
Bạn mô tả ý nghĩa của Collector.Characteristics.IDENTITY_FINISH và khi nào được khai báo ra sao?
Bạn phân biệt Collector.Characteristics.UNORDERED và CONCURRENT theo các bảo đảm nào?
Bạn sẽ xác định khi nào accumulator có thể xử lý đồng thời trên cùng result container như thế nào?
Bạn phân tích rủi ro khai báo CONCURRENT cho accumulator dùng HashMap không thread-safe ra sao?
Bạn sẽ kiểm tra kết quả khi một Collector CONCURRENT nhưng không UNORDERED được dùng với ordered Stream như thế nào?
Bạn phân biệt overload Collector.of có finisher với overload chỉ dùng identity finisher theo cách nào?
Bạn sẽ tạo custom Collector tính count, min và max nhưng chỉ duyệt dữ liệu một lần như thế nào?
Bạn mô tả quy tắc associativity của combiner giúp hai cách phân hoạch cho cùng kết quả ra sao?
Bạn sẽ dùng property-based test đối chiếu sequential và parallel collect như thế nào?
Bạn phân tích vì sao sửa state của accumulator riêng khác với side effect cập nhật collection nguồn ra sao?
Bạn sẽ bảo đảm finisher không làm lộ mutable internal accumulator ra ngoài public API như thế nào?
Bạn sẽ thiết kế Collector giữ các lỗi validation của từng bản ghi thay vì dừng ở lỗi đầu tiên như thế nào?
Bạn mô tả vì sao combiner trả nhầm state chưa được gộp chỉ gây lỗi khi workload được parallel hóa như thế nào?
Bạn sẽ kiểm thử Collector với source rỗng, một phần tử và nhiều partitions ra sao?
Bạn phân tích khi nào custom Collector khó hiểu hơn các Collectors.groupingBy hoặc teeing có sẵn ra sao?
Bạn sẽ lựa chọn Collector hay Gatherer khi cần tổng hợp cuối pipeline hoặc phát các kết quả trung gian như thế nào?
Bạn sẽ kiểm tra việc khai báo UNORDERED có hợp lệ với yêu cầu xuất danh sách giữ thứ tự hay không ra sao?
Bạn giải thích Spliterator khác Iterator về khả năng phân tách nguồn để xử lý song song như thế nào?
Bạn mô tả tryAdvance nhận Consumer và trả boolean để điều khiển traversal ra sao?
Bạn sẽ dùng forEachRemaining xử lý phần còn lại của một Spliterator theo contract nào?
Bạn phân biệt trySplit với việc tự sao chép nửa List sang Collection mới như thế nào?
Bạn sẽ thiết kế trySplit không bỏ sót hoặc xử lý trùng các phần tử giữa hai partitions ra sao?
Bạn mô tả estimateSize khác getExactSizeIfKnown ở mức độ chính xác ra sao?
Bạn sẽ xác định khi nào Spliterator được phép công bố SIZED characteristic như thế nào?
Bạn phân biệt SUBSIZED với SIZED khi Spliterator được chia tiếp nhiều lần ra sao?
Bạn sẽ thiết kế ORDERED characteristic phản ánh đúng encounter order của nguồn như thế nào?
Bạn mô tả DISTINCT và SORTED characteristics giúp framework suy luận gì về pipeline ra sao?
Bạn sẽ cài đặt getComparator cho Spliterator có SORTED characteristic theo nghĩa nào?
Bạn phân tích vì sao khai báo SORTED sai có thể khiến Stream.sorted cho kết quả bất ngờ ra sao?
Bạn sẽ kiểm tra NONNULL trước khi cho rằng tất cả phần tử nguồn đều không null ra sao?
Bạn mô tả Spliterator.IMMUTABLE ảnh hưởng kỳ vọng nguồn có thể thay đổi trong lúc duyệt như thế nào?
Bạn phân biệt Spliterator.CONCURRENT với Collector.Characteristics.CONCURRENT về đối tượng được bảo vệ ra sao?
Bạn sẽ dùng Spliterators.spliteratorUnknownSize khi nguồn không thể biết trước số phần tử như thế nào?
Bạn mô tả StreamSupport.stream tạo pipeline từ Spliterator và cờ parallel theo cách nào?
Bạn sẽ thiết kế late-binding Spliterator để chỉ gắn nguồn khi traversal bắt đầu như thế nào?
Bạn phân tích vì sao custom Spliterator trên mutable List có thể gặp non-interference violation ra sao?
Bạn sẽ phân biệt fail-fast traversal và weakly consistent traversal của các concurrent collections như thế nào?
Bạn sẽ thiết kế cân bằng kích thước partitions khi mỗi phần tử có chi phí tính toán tương tự ra sao?
Bạn mô tả chi phí split và work stealing ảnh hưởng khả năng tăng tốc parallel Stream như thế nào?
Bạn sẽ viết test thu các partitions từ trySplit để kiểm tra phủ đủ toàn bộ phần tử như thế nào?
Bạn phân tích vì sao estimates sai hoặc characteristics sai có thể phá các tối ưu của Stream framework ra sao?
Bạn giải thích parallelStream và Stream.parallel cho phép xử lý các portions của nguồn như thế nào?
Bạn mô tả ForkJoinPool.commonPool thường liên quan gì tới parallel Stream và giới hạn kiểm soát nào?
Bạn sẽ quyết định khi nào CPU-bound transformation đủ lớn để đáng parallel hóa như thế nào?
Bạn phân tích vì sao blocking I/O trong parallel Stream có thể làm nghẽn common pool như thế nào?
Bạn sẽ chọn bounded ExecutorService thay parallel Stream khi cần giới hạn số requests đồng thời ra sao?
Bạn mô tả vai trò của Spliterator.trySplit và combiner trong parallel reduction như thế nào?
Bạn sẽ phát hiện source không chia đều khiến một worker xử lý phần lớn dữ liệu như thế nào?
Bạn sẽ dùng unordered nếu kết quả không phụ thuộc encounter order nhằm giảm đồng bộ theo tình huống nào?
Bạn phân biệt findAny và findFirst về chi phí khi ordered parallel Stream như thế nào?
Bạn sẽ xác định vì sao forEach không được dùng nếu downstream cần side effects theo đúng thứ tự ra sao?
Bạn phân tích chi phí của sorted, distinct và limit ở parallel Stream có thứ tự như thế nào?
Bạn sẽ giữ lambda stateless để tránh race condition khi parallel map và filter ra sao?
Bạn mô tả non-interference có tác dụng gì khi source bị sửa từ callback ra sao?
Bạn sẽ thay synchronizedList.add bên ngoài bằng collect mà vẫn bảo toàn thứ tự cần thiết như thế nào?
Bạn phân biệt concurrent Collector với việc combiner hợp nhất nhiều containers độc lập theo cơ chế nào?
Bạn sẽ viết reduce/collector có tính associative để kết quả đúng dù thay số worker như thế nào?
Bạn phân tích vì sao floating-point sum có thể hơi khác nhau giữa sequential và parallel pipeline như thế nào?
Bạn sẽ kiểm tra mutable object values dù Collection source là concurrent như thế nào?
Bạn mô tả vì sao callbacks không được giả định luôn chạy trên cùng thread với caller như thế nào?
Bạn sẽ kiểm soát logging context khi callbacks chạy trên workers khác và không tự động kế thừa ThreadLocal ra sao?
Bạn phân tích vì sao tăng parallelism có thể làm contention và GC lớn hơn lợi ích CPU ra sao?
Bạn sẽ benchmark parallel và sequential Stream bằng JMH với warm-up và dữ liệu đại diện như thế nào?
Bạn sẽ lựa chọn sequential cho pipeline nhỏ, I/O bound hoặc nhiều side effects theo tiêu chí nào?
Bạn sẽ kiểm thử một collector thiếu thread safety trên nhiều partitions để phát hiện data corruption như thế nào?
Bạn giải thích Stream Gatherers bổ sung khả năng stateful transformations cho Stream API ở JDK hỗ trợ như thế nào?
Bạn sẽ phân biệt phiên bản preview của Stream Gatherers với API ổn định từ JDK 24 như thế nào?
Bạn mô tả Stream.gather là intermediate operation khác collect terminal operation ra sao?
Bạn sẽ chọn Gatherer thay map hoặc flatMap khi cần giữ state qua các phần tử liên tiếp như thế nào?
Bạn phân biệt Gatherers.windowFixed và windowSliding theo số phần tử chia sẻ giữa các windows như thế nào?
Bạn sẽ xử lý cửa sổ cuối không đủ kích thước từ windowFixed theo behavior nào?
Bạn sẽ dùng Gatherers.windowSliding để tính một moving average từ ordered source ra sao?
Bạn phân tích memory overhead của sliding windows khi các windows chồng lấp nhiều phần tử như thế nào?
Bạn mô tả Gatherers.scan tạo running accumulation khác với reduce terminal như thế nào?
Bạn sẽ dùng Gatherers.scan với seed khi cần phát kết quả tích lũy sau mỗi input như thế nào?
Bạn phân biệt Gatherers.fold với Stream.reduce về vị trí trong pipeline và số outputs như thế nào?
Bạn sẽ tạo Gatherers.fold để tổng hợp state rồi tiếp tục map kết quả theo cách nào?
Bạn mô tả Gatherers.mapConcurrent giới hạn số tác vụ ánh xạ đồng thời theo tham số nào?
Bạn sẽ chọn mapConcurrent khi mapping có blocking calls và cần kiểm soát concurrency như thế nào?
Bạn phân tích vì sao mapConcurrent không tự bảo đảm rate limit hoặc giới hạn kết nối dịch vụ ngoài như thế nào?
Bạn sẽ so sánh mapConcurrent với parallelStream.map khi thực hiện các HTTP requests như thế nào?
Bạn mô tả initializer của custom Gatherer khởi tạo trạng thái tích lũy như thế nào?
Bạn sẽ thiết kế Gatherer.Integrator tiêu thụ input và phát zero hoặc nhiều output elements ra sao?
Bạn phân biệt Gatherer.Downstream.push với việc lưu mọi output vào một mutable List chung như thế nào?
Bạn sẽ kiểm tra điều kiện downstream không chấp nhận thêm output để hỗ trợ short-circuit ra sao?
Bạn mô tả ý nghĩa boolean result từ integrator ảnh hưởng việc xử lý các input tiếp theo như thế nào?
Bạn sẽ dùng finisher của Gatherer để xuất phần dữ liệu còn lại khi nguồn đã kết thúc ra sao?
Bạn sẽ thiết kế custom Gatherer nhận biết các lần đổi trạng thái trong chuỗi events như thế nào?
Bạn phân tích vì sao mutable state của Gatherer cần kiểm tra isolation và ownership khi chạy parallel ra sao?
Bạn sẽ xây combiner cho custom Gatherer nếu việc merge partitions có ý nghĩa hợp lệ như thế nào?
Bạn phân biệt Gatherer có combiner và không có combiner về khả năng tận dụng parallelism ra sao?
Bạn sẽ dùng Gatherer.andThen để kết hợp hai biến đổi stateful theo thứ tự như thế nào?
Bạn sẽ kiểm thử custom Gatherer với nguồn rỗng, một phần tử và cửa sổ không đầy ra sao?
Bạn phân tích vì sao integrator không thể giả định luôn nhận tất cả source elements nếu downstream short-circuit ra sao?
Bạn sẽ kiểm tra JDK version và preview flags trước khi sử dụng Stream.gather trong build pipeline như thế nào?
Bạn giải thích vì sao Stream từ List thường không cần close nhưng Files.lines cần quản lý file descriptor như thế nào?
Bạn sẽ dùng try-with-resources để đảm bảo đóng Files.lines khi pipeline chạy thành công hoặc thất bại ra sao?
Bạn phân biệt Files.lines với Files.readAllLines về RAM usage và stream lifecycle như thế nào?
Bạn sẽ dùng Files.walk để duyệt cây thư mục mà vẫn đóng Stream<Path> đúng lúc ra sao?
Bạn mô tả BaseStream.onClose hỗ trợ đăng ký cleanup handlers như thế nào?
Bạn phân tích vì sao terminal operation đã chạy hết không tự động đóng mọi resource-backed Stream ra sao?
Bạn sẽ tránh trả Stream gắn với database cursor đã bị đóng khỏi method theo thiết kế API nào?
Bạn sẽ phân biệt IOException khi mở nguồn với UncheckedIOException ném trong lazy traversal ra sao?
Bạn sẽ giữ root cause IOException khi bắt UncheckedIOException ở tầng I/O boundary như thế nào?
Bạn mô tả vì sao Function callback của Stream không trực tiếp khai báo checked exception như IOException ra sao?
Bạn sẽ thiết kế ThrowingFunction adapter hoặc result wrapper khi mỗi phần tử có thể lỗi như thế nào?
Bạn phân tích rủi ro catch Exception rồi trả null làm mất thông tin lỗi trong Stream.map ra sao?
Bạn sẽ chọn fail-fast hoặc collect mọi validation errors theo yêu cầu batch nào?
Bạn sẽ xử lý suppressed exception khi cả quá trình đọc và đóng resource đều gặp lỗi ra sao?
Bạn mô tả cách findFirst hoặc limit dừng sớm nhưng vẫn cần close file source trong finally như thế nào?
Bạn sẽ kiểm thử một source ném lỗi sau nhiều phần tử để xác minh close handler được gọi ra sao?
Bạn phân tích vì sao dùng parallel Stream trên nguồn I/O không tự cung cấp thread safety cho cursor ra sao?
Bạn sẽ đánh giá tác động khi một lazy pipeline được thực thi ngoài phạm vi transaction hoặc resource owner như thế nào?
Bạn sẽ thiết kế API nhận Consumer để xử lý resource-backed Stream trong phạm vi đóng được kiểm soát ra sao?
Bạn mô tả cách xử lý error reporting mà không log toàn bộ dữ liệu nhạy cảm trong source ra sao?
Bạn sẽ giới hạn input và buffer khi chuyển Stream từ network source để tránh tích lũy vô hạn ra sao?
Bạn sẽ xây test cho lifecycle Stream với success, exception và short-circuit termination ra sao?
Bạn sẽ phân tích Stream pipeline bị chậm bắt đầu từ source, intermediate operations và sink theo bước nào?
Bạn phân biệt throughput thấp do CPU với latency cao do I/O bên trong mapper như thế nào?
Bạn sẽ dùng JMH để so sánh Stream và vòng for với warm-up và cùng dataset như thế nào?
Bạn phân tích vì sao benchmark không tiêu thụ kết quả có thể bị JVM tối ưu bỏ công việc ra sao?
Bạn sẽ đo autoboxing overhead của Stream<Integer> so với IntStream trên dữ liệu lớn như thế nào?
Bạn mô tả chi phí chuyển boxed rồi mapToInt lặp lại có thể làm tăng allocations ra sao?
Bạn sẽ quyết định thứ tự filter và map dựa trên purity, chi phí và thay đổi semantics như thế nào?
Bạn phân tích vì sao sorted().limit(k) có thể tốn hơn giải pháp top-K dùng heap trên nguồn rất lớn ra sao?
Bạn sẽ đo memory cost của distinct khi số phần tử unique tăng mạnh như thế nào?
Bạn sẽ tối ưu groupingBy nhiều cấp khi Map và List trung gian sử dụng quá nhiều bộ nhớ ra sao?
Bạn phân biệt anyMatch short-circuit với collect hết rồi kiểm tra tồn tại phần tử như thế nào?
Bạn sẽ chọn mapMulti, flatMap, Collector hoặc Gatherer dựa trên output cardinality và state như thế nào?
Bạn mô tả vì sao pipeline có lazy không giảm RAM nếu toàn bộ dữ liệu đã load vào Collection trước đó ra sao?
Bạn sẽ đưa server-side filter và pagination vào query trước khi tạo Stream ở Java như thế nào?
Bạn phân tích vì sao tăng parallel threads chưa chắc giảm thời gian nếu workload quá nhỏ hoặc contention cao ra sao?
Bạn sẽ dùng JFR allocation profiling để tìm nơi phát sinh object allocations trong pipeline như thế nào?
Bạn sẽ thiết kế giới hạn xử lý dữ liệu lớn khi stream nguồn không có cơ chế backpressure thực sự như thế nào?
Bạn mô tả trade-off giữa memory, readability và speed khi thay pipeline dài bằng vòng lặp tường minh ra sao?
Bạn sẽ xác định khi nào custom Spliterator hay Gatherer khó bảo trì hơn code xử lý đơn giản như thế nào?
Bạn sẽ dùng profile production để xác minh một thay đổi tối ưu Stream thực sự cải thiện hiệu năng ra sao?
Nếu Stream.filter được khai báo nhưng callback không chạy, bạn sẽ kiểm tra terminal operation và lazy execution như thế nào?
Nếu gọi count rồi tiếp tục map trên cùng Stream gây lỗi, bạn sẽ thiết kế lại nguồn để duyệt nhiều lần ra sao?
Nếu Files.lines gây rò file descriptors, bạn sẽ dùng try-with-resources và kiểm tra close handlers như thế nào?
Nếu distinct không loại trùng đúng, bạn sẽ đánh giá equals/hashCode của source elements ra sao?
Nếu peek được dùng để ghi audit nhưng count bỏ qua callback đó, bạn sẽ chuyển thao tác ghi bắt buộc sang đâu để bảo đảm nó diễn ra?
Nếu Stream.toList tạo danh sách không sửa được, bạn sẽ dùng toCollection khi thực sự cần mutable List ra sao?
Nếu toMap ném Duplicate key exception, bạn sẽ chọn merge function tuân thủ luật nghiệp vụ như thế nào?
Nếu groupingBy classifier tạo null và pipeline lỗi, bạn sẽ biểu diễn giá trị khuyết thành key hợp lệ ra sao?
Nếu custom Collector chạy sequential đúng nhưng parallel sai, bạn sẽ kiểm tra supplier, combiner và characteristics như thế nào?
Nếu reduce dùng phép trừ cho kết quả khác giữa hai lần parallel, bạn sẽ thay bằng phép associative nào?
Nếu average của IntStream rỗng được báo thành 0, bạn sẽ xử lý OptionalDouble theo nghĩa nghiệp vụ ra sao?
Nếu IntStream.sum bị overflow ở tập số lớn, bạn sẽ đổi sang LongStream hoặc phép tính thích hợp như thế nào?
Nếu parallel Stream không tăng tốc, bạn sẽ điều tra splitting, work-stealing, contention và chi phí combiner ra sao?
Nếu custom Spliterator trả overlapping partitions, bạn sẽ kiểm thử mỗi phần tử được duyệt đúng một lần như thế nào?
Nếu concurrent collection thay đổi khi Stream đang duyệt, bạn sẽ xác định đặc tính weakly consistent của source ra sao?
Nếu custom Spliterator khai báo SORTED sai, bạn sẽ chẩn đoán thứ tự đầu ra như thế nào?
Nếu parallel forEach cập nhật HashMap gây mất dữ liệu, bạn sẽ đổi sang Collector phù hợp như thế nào?
Nếu ordered parallel limit chạy chậm, bạn sẽ xem xét unordered hoặc sequential theo yêu cầu nào?
Nếu windowSliding cho kết quả trung bình di động không đúng ở đầu nguồn, bạn sẽ kiểm tra kích thước cửa sổ như thế nào?
Nếu windowFixed trả cửa sổ cuối ít phần tử, bạn sẽ xác minh contract về cửa sổ chưa đủ như thế nào?
Nếu custom Gatherer đẩy output sau khi downstream không nhận nữa, bạn sẽ sửa integrator thế nào?
Nếu custom Gatherer có kết quả khác trên parallel Stream, bạn sẽ kiểm tra state isolation và combiner như thế nào?
Nếu mapConcurrent quá tải remote API, bạn sẽ kết hợp giới hạn concurrency và rate limit ra sao?
Nếu JDK của CI không hỗ trợ Stream.gather, bạn sẽ kiểm tra version và preview feature settings như thế nào?
Nếu một batch cần ghi lại mọi lỗi thay vì dừng ở item đầu, bạn sẽ thiết kế result wrapper và Collector như thế nào?
Nếu phải xử lý hàng triệu dòng file theo Stream, bạn sẽ thiết kế lazy parsing, error reporting và cleanup ra sao?
Nếu phải review Stream pipeline cho production, bạn sẽ kiểm tra non-interference, resources, ordering, collectors và hiệu năng ra sao?
