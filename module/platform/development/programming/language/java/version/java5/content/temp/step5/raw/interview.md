Bạn giải thích vì sao Generics được đưa vào Java 5 và giúp phát hiện lỗi kiểu dữ liệu sớm hơn cách sử dụng Object như thế nào?
Bạn thiết kế một lớp lưu trữ có type parameter để người gọi không phải ép kiểu thủ công khi lấy dữ liệu ra sao?
Bạn phân biệt type parameter trong khai báo lớp với type argument được truyền khi khởi tạo lớp generic như thế nào?
Bạn đánh giá lợi ích của việc khai báo nhiều type parameter trong một interface lưu trữ cặp khóa và giá trị ra sao?
Bạn phân biệt generic class với generic method về phạm vi của type parameter và cách compiler suy luận kiểu như thế nào?
Bạn thiết kế một static generic method nhận và trả về cùng kiểu dữ liệu mà không phụ thuộc type parameter của lớp chứa nó ra sao?
Bạn giải thích tại sao List<String> không phải subtype của List<Object> dù String kế thừa Object như thế nào?
Bạn so sánh tính invariant của generic type argument với tính covariant của mảng Java theo tác động đến an toàn kiểu ra sao?
Bạn sử dụng unbounded wildcard để viết một phương thức chỉ đọc danh sách thuộc mọi kiểu phần tử như thế nào?
Bạn phân biệt List<?> với raw type List theo mức độ kiểm tra an toàn kiểu mà compiler vẫn thực hiện ra sao?
Bạn xác định vì sao không thể thêm đối tượng tùy ý vào List<?> dù danh sách thực tế có thể thay đổi như thế nào?
Bạn thiết kế API nhận List<? extends Number> khi thuật toán chỉ cần đọc phần tử theo nguyên tắc nào?
Bạn phân tích giới hạn của thao tác ghi lên List<? extends Number> khi kiểu phần tử cụ thể chưa được biết ra sao?
Bạn áp dụng List<? super Integer> khi đưa số nguyên vào một collection đích và kiểm soát kiểu giá trị đọc ra như thế nào?
Bạn vận dụng nguyên tắc PECS để thiết kế phương thức sao chép phần tử từ collection nguồn sang collection đích ra sao?
Bạn phân biệt dùng wildcard với type parameter có tên khi kiểu của nhiều tham số và kiểu trả về cần liên hệ với nhau như thế nào?
Bạn thiết kế phương thức generic tìm phần tử lớn nhất với ràng buộc Comparable<? super T> theo những điều kiện nào?
Bạn giải thích vai trò của bounded type parameter khi phương thức cần gọi hành vi do một interface định nghĩa ra sao?
Bạn sử dụng multiple bounds của type parameter để yêu cầu đồng thời một class cha và các interface như thế nào?
Bạn phân tích rủi ro khi một API công khai đặt bound quá chặt làm giảm khả năng tái sử dụng trong hệ thống như thế nào?
Bạn giải thích type erasure ảnh hưởng đến generic type argument tại runtime và bytecode như thế nào?
Bạn phân biệt kiểm tra kiểu lúc compile với phép ép kiểu được compiler chèn vào sau type erasure ra sao?
Bạn giải thích tại sao instanceof List<String> không phải phép kiểm tra runtime hợp lệ và xây dựng cách kiểm tra dữ liệu thay thế như thế nào?
Bạn thiết kế cơ chế truyền Class<T> vào một factory generic để tạo hoặc kiểm tra đối tượng khi type argument không còn reifiable ra sao?
Bạn phân biệt thông tin generic signature có thể đọc bằng reflection với kiểu thực tế của từng phần tử collection tại runtime như thế nào?
Bạn phân tích vì sao không thể khai báo hai overload chỉ khác List<String> và List<Integer> trên cùng một lớp ra sao?
Bạn giải thích mục đích của bridge method do compiler sinh ra khi generic method được override sau type erasure như thế nào?
Bạn sử dụng javap hoặc reflection để điều tra một bridge method xuất hiện trong class file mà mã nguồn không khai báo ra sao?
Bạn xác định nguyên nhân heap pollution khi raw collection được truyền vào code dùng Generics và gây ClassCastException muộn như thế nào?
Bạn thiết kế phương án chuyển raw List từ API cũ sang List<T> bằng kiểm tra từng phần tử thay vì unchecked cast tùy tiện ra sao?
Bạn giải thích vì sao không thể tạo trực tiếp generic array bằng new T[n] và lựa chọn cấu trúc dữ liệu thay thế như thế nào?
Bạn phân tích rủi ro của generic varargs khi một mảng tham số bị ghi giá trị sai kiểu qua tham chiếu Object[] như thế nào?
Bạn lựa chọn phạm vi áp dụng @SuppressWarnings cho một unchecked conversion không thể tránh được để không che giấu các cảnh báo khác ra sao?
Bạn xác định những điều kiện phải xác minh trước khi dùng @SafeVarargs trong mã Java hiện đại liên quan đến generic varargs như thế nào?
Bạn thiết kế kiểm thử compile-time để bảo đảm những tổ hợp generic type không hợp lệ bị compiler từ chối như thế nào?
Bạn đánh giá cách bổ sung Generics vào public API của thư viện cũ mà vẫn xem xét source compatibility và binary compatibility ra sao?
Bạn giải thích mục tiêu của enum trong Java 5 so với việc dùng các hằng số int hoặc String để biểu diễn trạng thái như thế nào?
Bạn thiết kế enum cho trạng thái đơn hàng với tập giá trị hợp lệ mà không cho phép caller tự tạo trạng thái khác ra sao?
Bạn phân biệt identity của enum constant với việc so sánh chuỗi tên trạng thái khi kiểm tra điều kiện nghiệp vụ như thế nào?
Bạn giải thích vì sao enum có thể khai báo field, constructor và method để gắn dữ liệu hoặc hành vi cho mỗi constant như thế nào?
Bạn thiết kế constant-specific method implementation khi từng giá trị enum cần một hành vi xử lý khác nhau ra sao?
Bạn phân biệt enum implements interface với enum extends một class tùy ý theo giới hạn của hệ thống kiểu Java như thế nào?
Bạn sử dụng EnumSet để quản lý tập trạng thái hoặc quyền với bảo đảm type safety và hiệu năng theo cách nào?
Bạn lựa chọn EnumMap thay cho HashMap khi toàn bộ khóa đều là constant của cùng một enum theo tiêu chí nào?
Bạn đánh giá rủi ro khi lưu enum.ordinal vào database và thay đổi thứ tự khai báo constant sau này như thế nào?
Bạn thiết kế ánh xạ mã định danh nghiệp vụ ổn định cho enum thay vì phụ thuộc vào tên hoặc thứ tự constant ra sao?
Bạn phân biệt Enum.valueOf với việc parse một mã nghiệp vụ do client cung cấp và xử lý giá trị không hợp lệ như thế nào?
Bạn giải thích cách một switch trên enum giúp xác định các nhánh xử lý và kiểm thử tập trạng thái như thế nào?
Bạn thiết kế cách phát hiện enum constant mới chưa được xử lý khi refactor switch ở một phiên bản Java hiện đại ra sao?
Bạn phân tích sự khác nhau giữa enum singleton và một static instance thông thường về kiểm soát số lượng instance như thế nào?
Bạn kiểm thử một enum chứa hành vi riêng theo constant mà không chỉ xác minh tên hoặc ordinal như thế nào?
Bạn giải thích annotation trong Java dùng để mô tả metadata và hỗ trợ kiểm tra hoặc xử lý mã nguồn như thế nào?
Bạn phân biệt annotation declaration với việc gắn annotation lên class, method, field hoặc parameter như thế nào?
Bạn thiết kế annotation nghiệp vụ khai báo rõ các phần tử bắt buộc và giá trị mặc định theo yêu cầu nào?
Bạn phân biệt các kiểu dữ liệu hợp lệ của annotation element với kiểu đối tượng tùy ý có trạng thái mutable như thế nào?
Bạn giải thích vai trò của @Target khi giới hạn vị trí một annotation được phép xuất hiện trong mã nguồn ra sao?
Bạn phân biệt RetentionPolicy.SOURCE, CLASS và RUNTIME theo khả năng sử dụng metadata trong compiler hoặc reflection như thế nào?
Bạn dùng @Retention(RUNTIME) để đọc annotation từ một class bằng reflection trong ứng dụng hiện đại ra sao?
Bạn giải thích tác dụng của @Override khi phát hiện lỗi ghi sai chữ ký phương thức trong quan hệ kế thừa như thế nào?
Bạn phân biệt @Deprecated với việc xóa API ngay lập tức khi lập kế hoạch chuyển mã client sang phương thức mới ra sao?
Bạn lựa chọn cách giải thích hoặc tài liệu hóa API thay thế cho một declaration được đánh dấu @Deprecated theo tiêu chí nào?
Bạn sử dụng @SuppressWarnings ở phạm vi nhỏ nhất để xử lý cảnh báo đã được kiểm chứng mà không che giấu lỗi khác như thế nào?
Bạn phân tích vì sao annotation không tự động thực thi logic xác thực chỉ nhờ có mặt trên một field như thế nào?
Bạn thiết kế một runtime validator đọc annotation rồi áp dụng quy tắc dữ liệu, đồng thời xử lý trường hợp annotation vắng mặt ra sao?
Bạn phân biệt annotation được kế thừa theo @Inherited trên class với annotation trên method hoặc interface như thế nào?
Bạn xác định khi nào custom annotation phù hợp hơn một cấu hình tường minh để API vẫn dễ tìm hiểu và kiểm thử như thế nào?
Bạn phân tích cách annotation processing của javac hiện đại tạo mã hoặc kiểm tra cấu trúc dựa trên metadata mà annotation cung cấp ra sao?
Bạn thiết kế quy tắc tránh phụ thuộc vào tên reflection hoặc implementation detail của annotation khi nâng cấp framework như thế nào?
Bạn kiểm thử một thành phần sử dụng annotation khi annotation có retention hoặc target không phù hợp như thế nào?
Bạn giải thích cú pháp enhanced for được đưa vào Java 5 giúp đơn giản hóa việc duyệt mảng và Iterable như thế nào?
Bạn phân biệt enhanced for với vòng for dùng index khi thuật toán cần cập nhật phần tử tại vị trí cụ thể ra sao?
Bạn giải thích cách Iterable và Iterator liên quan đến khả năng một collection dùng được trong enhanced for như thế nào?
Bạn thiết kế một class triển khai Iterable<T> để consumer có thể duyệt dữ liệu bằng enhanced for ra sao?
Bạn phân tích vì sao thay phần tử đang duyệt bằng phép gán cho biến lặp không tự động cập nhật phần tử trong collection như thế nào?
Bạn xác định rủi ro ConcurrentModificationException khi xóa phần tử khỏi collection trong quá trình enhanced for ra sao?
Bạn lựa chọn Iterator.remove hoặc phương thức removeIf có trong Java hiện đại khi cần xóa phần tử có điều kiện như thế nào?
Bạn phân biệt iteration order của List, HashSet và LinkedHashSet khi cùng dùng enhanced for như thế nào?
Bạn thiết kế phép duyệt một collection lớn mà không vô tình tạo bản sao toàn bộ dữ liệu chỉ để dùng enhanced for ra sao?
Bạn giải thích cơ chế autoboxing chuyển primitive sang wrapper và unboxing chuyển wrapper về primitive như thế nào?
Bạn phân biệt giá trị null của Integer với giá trị 0 của int khi xử lý dữ liệu số có thể thiếu ra sao?
Bạn phân tích nguyên nhân NullPointerException khi tự động unbox một Integer đang là null như thế nào?
Bạn lựa chọn primitive hoặc wrapper trong API dựa trên khả năng biểu diễn null, hiệu năng và hợp đồng dữ liệu như thế nào?
Bạn giải thích vì sao phép so sánh == giữa hai wrapper có thể tạo kết quả khác với equals dù nội dung số giống nhau ra sao?
Bạn kiểm tra rủi ro dựa vào cache của Integer.valueOf thay vì so sánh giá trị một cách rõ ràng như thế nào?
Bạn phân tích chi phí cấp phát, boxing và unboxing khi xử lý lượng lớn số nguyên qua generic collections ra sao?
Bạn xác định tác động của numeric promotion và overload resolution khi primitive, wrapper và varargs cùng tham gia một lời gọi method như thế nào?
Bạn lựa chọn mảng primitive hoặc IntStream trên JDK hiện đại để giảm overhead của List<Integer> trong workload số học như thế nào?
Bạn thiết kế test cho trường hợp số lớn, null và ép kiểu nhằm phát hiện lỗi boxing hoặc tràn số ngoài ý muốn ra sao?
Bạn giải thích varargs giúp phương thức chấp nhận số lượng đối số thay đổi và compiler biểu diễn tham số đó như một mảng như thế nào?
Bạn phân biệt cách gọi một phương thức varargs với không đối số, nhiều đối số và một mảng đã có sẵn như thế nào?
Bạn đánh giá nguy cơ overload ambiguity khi một method có varargs cạnh tranh với các overload nhận primitive hoặc wrapper ra sao?
Bạn giải thích quy tắc đặt tham số varargs ở cuối danh sách parameter và tác động đến lời gọi phương thức ra sao?
Bạn phân tích khả năng method sửa nội dung mảng được truyền vào varargs và cách hạn chế side effect như thế nào?
Bạn sử dụng varargs trong public API khi số lượng tham số nhỏ và cùng ngữ nghĩa, so với truyền List<T>, theo tiêu chí nào?
Bạn phân biệt static import với import một class về những thành viên nào có thể gọi bằng tên ngắn ra sao?
Bạn đánh giá khi nào static import các hằng số hoặc method giúp code rõ ràng hơn và khi nào làm nguồn gốc tên khó nhận biết như thế nào?
Bạn xử lý trường hợp static import từ nhiều class gây trùng tên method hoặc constant bằng những cách nào?
Bạn giải thích covariant return types cho phép phương thức override trả về subtype cụ thể hơn và lợi ích đối với API như thế nào?
Bạn phân biệt overriding có covariant return với overloading chỉ khác parameter tại thời điểm compile như thế nào?
Bạn đánh giá cách compiler giữ binary compatibility khi một override dùng covariant return và có thể xuất hiện bridge method ra sao?
Bạn giải thích vai trò của java.util.concurrent được bổ sung từ Java 5 trong việc chuẩn hóa quản lý thread và chia sẻ dữ liệu như thế nào?
Bạn phân biệt việc tạo Thread trực tiếp với gửi tác vụ vào ExecutorService theo trách nhiệm và vòng đời như thế nào?
Bạn lựa chọn Runnable và Callable<T> khi tác vụ có hoặc không có kết quả hoặc checked exception như thế nào?
Bạn thiết kế một phương thức gửi Callable<T> vào ExecutorService và nhận kết quả qua Future<T> ra sao?
Bạn phân biệt execute với submit khi muốn quan sát lỗi và kết quả của một tác vụ như thế nào?
Bạn giải thích hành vi của Future.get khi tác vụ chưa xong và cách tránh chặn vô thời hạn như thế nào?
Bạn dùng Future.get với timeout để áp giới hạn chờ và phân loại TimeoutException với lỗi thực thi tác vụ ra sao?
Bạn phân tích ExecutionException bao bọc lỗi từ Callable và cách truy vết nguyên nhân thực tế như thế nào?
Bạn giải thích khi nào Future.cancel(true) gửi yêu cầu ngắt và vì sao nó không bảo đảm tác vụ dừng ngay lập tức như thế nào?
Bạn thiết kế một tác vụ có thể bị hủy bằng interruption mà không làm mất trạng thái interrupt ngoài ý muốn ra sao?
Bạn phân biệt trạng thái isDone và isCancelled của Future khi tác vụ hoàn thành, lỗi hoặc bị hủy như thế nào?
Bạn lựa chọn invokeAll, invokeAny hoặc submit từng Future khi xử lý nhóm tác vụ có điều kiện hoàn thành khác nhau ra sao?
Bạn sử dụng ExecutorCompletionService để thu kết quả theo thứ tự hoàn thành thay vì thứ tự gửi tác vụ như thế nào?
Bạn thiết kế một service giới hạn thời gian xử lý nhiều tác vụ và thu hồi tài nguyên khi một phần tác vụ thất bại ra sao?
Bạn phân biệt shutdown với shutdownNow của ExecutorService về việc nhận tác vụ mới và cố gắng dừng tác vụ cũ ra sao?
Bạn viết quy trình đóng ExecutorService có chờ kết thúc, xử lý timeout và khôi phục interrupt status như thế nào?
Bạn đánh giá khác biệt giữa fixed thread pool, single-thread executor và cached thread pool theo độ lớn workload và khả năng quá tải như thế nào?
Bạn phân tích rủi ro hàng đợi không giới hạn trong thread pool khi tốc độ tiếp nhận vượt khả năng xử lý lâu dài như thế nào?
Bạn thiết kế ThreadPoolExecutor với core size, max size, queue capacity và rejection policy phù hợp tải dự kiến ra sao?
Bạn xác định cách xử lý RejectedExecutionException để hệ thống báo quá tải thay vì mất tác vụ âm thầm như thế nào?
Bạn giải thích vai trò của ThreadFactory trong việc đặt tên thread, thiết lập thuộc tính và hỗ trợ chẩn đoán như thế nào?
Bạn lựa chọn ScheduledExecutorService để lập lịch tác vụ thay vì tự tạo thread ngủ trong vòng lặp như thế nào?
Bạn phân biệt scheduleAtFixedRate với scheduleWithFixedDelay khi thời gian chạy tác vụ thay đổi như thế nào?
Bạn thiết kế tác vụ định kỳ có cơ chế giám sát lỗi để tránh dừng lịch lặng lẽ khi một lần chạy ném exception ra sao?
Bạn phân tích lý do executor không tự bảo đảm thứ tự hoàn thành của các tác vụ dù chúng được submit theo thứ tự như thế nào?
Bạn giải thích Java Memory Model được làm rõ ở Java 5 giúp xác định khả năng nhìn thấy ghi dữ liệu giữa các thread như thế nào?
Bạn phân biệt data race với race condition ở cấp nghiệp vụ bằng ví dụ nhiều thread cập nhật cùng một bộ đếm ra sao?
Bạn mô tả quan hệ happens-before và vai trò của nó trong bảo đảm visibility và ordering như thế nào?
Bạn phân biệt atomicity, visibility và ordering khi đánh giá một biến được dùng chung giữa nhiều thread như thế nào?
Bạn giải thích vì sao đánh dấu volatile cho một biến cờ giúp truyền tín hiệu dừng giữa các thread theo những điều kiện nào?
Bạn phân tích vì sao volatile không làm cho phép tăng biến đếm bằng read-modify-write trở thành atomic như thế nào?
Bạn thiết kế giao thức xuất bản một đối tượng đã khởi tạo qua volatile reference để tránh đọc trạng thái chưa nhất quán ra sao?
Bạn xác định happens-before giữa một volatile write và các volatile read tiếp theo của cùng biến theo quy tắc nào?
Bạn giải thích cách synchronized thiết lập mutual exclusion và memory visibility khi nhiều thread vào cùng critical section như thế nào?
Bạn phân biệt khóa monitor của synchronized instance method với synchronized static method theo đối tượng được dùng làm khóa ra sao?
Bạn phân tích nguy cơ deadlock khi hai thread lấy nhiều monitor lock theo thứ tự khác nhau và đề xuất quy ước tránh lỗi như thế nào?
Bạn lựa chọn synchronized hay ReentrantLock dựa trên nhu cầu thử lấy khóa, ngắt lúc chờ và thời gian chờ giới hạn ra sao?
Bạn sử dụng tryLock với timeout để giảm nguy cơ một tác vụ chờ khóa vô hạn trong hệ thống như thế nào?
Bạn thiết kế cấu trúc try-finally khi sử dụng Lock để bảo đảm unlock ngay cả khi mã trong critical section ném exception ra sao?
Bạn giải thích tính reentrant của ReentrantLock và khác biệt giữa hold count với số thread cùng giữ khóa như thế nào?
Bạn phân tích đánh đổi khi bật fairness cho ReentrantLock hoặc Semaphore theo throughput và nguy cơ starvation ra sao?
Bạn phân biệt Condition.await và Condition.signal với wait và notify của monitor về cách phối hợp thread như thế nào?
Bạn giải thích vì sao điều kiện chờ thường phải được kiểm tra bằng vòng while khi dùng Condition thay vì giả định signal luôn thỏa điều kiện ra sao?
Bạn thiết kế producer-consumer bằng Condition và Lock mà không để mất tín hiệu hoặc để consumer đọc dữ liệu rỗng như thế nào?
Bạn sử dụng ReentrantReadWriteLock khi số tác vụ đọc nhiều hơn tác vụ ghi và xác định những giới hạn của mô hình như thế nào?
Bạn đánh giá rủi ro lock upgrade hoặc starvation khi dùng read lock và write lock trong một cache đồng thời ra sao?
Bạn so sánh synchronized collection với ConcurrentHashMap khi nhiều thread đọc ghi các khóa độc lập như thế nào?
Bạn giải thích vai trò của ConcurrentHashMap khi cập nhật giá trị đồng thời mà không khóa toàn bộ cấu trúc theo cách dùng HashMap thông thường ra sao?
Bạn sử dụng computeIfAbsent của ConcurrentHashMap trên JDK hiện đại để khởi tạo giá trị theo khóa và kiểm soát mapping function ra sao?
Bạn phân tích vì sao chuỗi thao tác get rồi put riêng lẻ trên concurrent map không tự trở thành một giao dịch atomic như thế nào?
Bạn xác định cách iteration trên ConcurrentHashMap phản ánh các cập nhật đồng thời và giới hạn tính nhất quán của snapshot ra sao?
Bạn lựa chọn CopyOnWriteArrayList khi workload đọc rất nhiều nhưng hiếm khi sửa và giải thích chi phí của mỗi lần ghi như thế nào?
Bạn phân biệt iterator snapshot của CopyOnWriteArrayList với iterator có cơ chế fail-fast trong một collection không đồng bộ như thế nào?
Bạn thiết kế hàng đợi producer-consumer bằng BlockingQueue để thực hiện backpressure thay vì sử dụng polling liên tục ra sao?
Bạn lựa chọn ArrayBlockingQueue có dung lượng cố định hay LinkedBlockingQueue có cấu hình giới hạn theo nhu cầu bộ nhớ như thế nào?
Bạn phân biệt put, offer và offer với timeout của BlockingQueue khi hệ thống muốn kiểm soát quá tải như thế nào?
Bạn xác định cách tác vụ đang chờ take hoặc put phản ứng với interruption và thiết kế shutdown sạch ra sao?
Bạn sử dụng CountDownLatch để đợi một tập tác vụ hoàn thành giai đoạn khởi tạo theo cách nào?
Bạn phân biệt CountDownLatch chỉ dùng một lần với CyclicBarrier có thể tái sử dụng qua nhiều vòng phối hợp như thế nào?
Bạn phân tích nguy cơ một worker không đến barrier khiến các worker khác bị kẹt và cách quản lý timeout ra sao?
Bạn sử dụng Semaphore để giới hạn số lời gọi I/O đồng thời tới một dịch vụ bên ngoài như thế nào?
Bạn thiết kế cấu trúc acquire và release của Semaphore trong try-finally để không làm rò rỉ permit khi có exception ra sao?
Bạn phân biệt Semaphore với một thread pool cố định khi cần kiểm soát đồng thời nhưng tác vụ chạy trên nhiều executor như thế nào?
Bạn giải thích vai trò của AtomicInteger và compareAndSet trong cập nhật dữ liệu chia sẻ mà không cần mutex cho mọi phép toán như thế nào?
Bạn phân tích một vòng lặp CAS và cách nó xử lý tình huống nhiều thread cùng cập nhật trạng thái ban đầu ra sao?
Bạn thiết kế bộ đếm đồng thời bằng AtomicInteger và xác định trường hợp cần dùng kiểu số lớn hơn như thế nào?
Bạn phân biệt getAndIncrement với hai lời gọi get rồi set về tính nguyên tử của phép cập nhật như thế nào?
Bạn dùng AtomicReference để chuyển trạng thái một đối tượng theo CAS mà không thực hiện cập nhật mất dữ liệu như thế nào?
Bạn giải thích vấn đề ABA trong thuật toán CAS và đánh giá khi nào cần version hoặc AtomicStampedReference ra sao?
Bạn lựa chọn synchronized, ReentrantLock hay atomic variable khi bất biến cần cập nhật nhiều field cùng lúc theo tiêu chí nào?
Bạn giải thích bảo đảm visibility của final field sau khi constructor hoàn tất với điều kiện object không bị công bố sớm như thế nào?
Bạn thiết kế một class bất biến để chia sẻ an toàn giữa nhiều thread mà không cần đồng bộ các thao tác đọc ra sao?
Bạn phân tích vì sao double-checked locking chỉ an toàn khi biến giữ singleton được công bố đúng theo Java Memory Model ra sao?
Bạn đánh giá lợi ích và giới hạn của việc dùng enum singleton thay cho double-checked locking trong Java hiện đại như thế nào?
Bạn phân biệt happens-before do Thread.start, Thread.join và Future.get thiết lập khi chia sẻ kết quả công việc như thế nào?
Bạn thiết kế kiểm thử đồng thời tìm lỗi race condition mà không dựa vào Thread.sleep để tạo thứ tự thực thi giả định ra sao?
Bạn sử dụng thread dump và JFR để phân biệt thread bị BLOCKED vì lock với thread WAITING vì tác vụ phối hợp như thế nào?
Bạn đánh giá cách phối hợp executor, bounded queue và timeout để tránh cạn tài nguyên khi có nhiều request đến cùng lúc như thế nào?
Bạn giải thích vai trò của Scanner và Formatter được bổ sung ở Java 5 trong đọc hoặc trình bày dữ liệu có định dạng như thế nào?
Bạn lựa chọn Locale rõ ràng khi sử dụng Formatter hoặc String.format để tạo dữ liệu máy đọc ổn định qua các môi trường ra sao?
Bạn phân biệt định dạng số bằng Formatter cho người dùng với cách serialize một giá trị số trong giao thức API như thế nào?
Bạn thiết kế thao tác đọc số với Scanner có kiểm tra dữ liệu sai định dạng mà không làm chương trình dừng bất ngờ ra sao?
Bạn phân tích tác động của Locale đến việc Scanner diễn giải dấu thập phân khi nhập dữ liệu từ nhiều quốc gia như thế nào?
Bạn đánh giá tại sao Scanner không phải lựa chọn tối ưu cho mọi pipeline nhập văn bản dung lượng lớn như thế nào?
Một API cũ trả về raw List gây ClassCastException trong mã generic, bạn sẽ xác thực dữ liệu và chuyển chữ ký API như thế nào?
Một danh sách Integer chứa null khiến phép cộng tự động unbox thất bại, bạn sẽ thiết kế hợp đồng null và kiểm thử ra sao?
Một enum được lưu trong database bằng ordinal dẫn đến dữ liệu đổi nghĩa sau khi thêm constant, bạn sẽ sửa cách lưu và migration như thế nào?
Một annotation khai báo retention không phù hợp khiến framework không đọc được ở runtime, bạn sẽ chẩn đoán và sửa hợp đồng metadata ra sao?
Một tác vụ submit vào ExecutorService ném exception nhưng log không hiển thị lỗi, bạn sẽ kiểm tra Future và cơ chế quan sát tác vụ như thế nào?
Một dịch vụ dùng fixed thread pool nhưng hàng đợi tăng không giới hạn khi backend chậm, bạn sẽ xây dựng backpressure và chính sách từ chối ra sao?
Một biến đếm khai báo volatile vẫn bị mất lượt cập nhật dưới tải cao, bạn sẽ phân tích tính nguyên tử và chọn cơ chế đồng bộ như thế nào?
Một worker dùng ReentrantLock quên unlock khi exception khiến các request khác bị treo, bạn sẽ sửa cấu trúc kiểm soát tài nguyên ra sao?
Một BlockingQueue không có giới hạn làm bộ nhớ tăng liên tục trong lúc producer nhanh hơn consumer, bạn sẽ điều chỉnh capacity và cách xử lý timeout như thế nào?
Một CompletableFuture pipeline mới phải tích hợp với thư viện Java 5 cũ trả Future, bạn sẽ thiết kế adapter và bảo toàn timeout, cancellation như thế nào?
Bạn xây dựng checklist review những nền tảng Java 5 còn dùng trong Java hiện đại, tập trung vào Generics, enum, annotation, concurrency và an toàn bộ nhớ như thế nào?
