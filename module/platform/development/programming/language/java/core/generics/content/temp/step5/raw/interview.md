Bạn giải thích Generics giải quyết những hạn chế nào của cách dùng Object và ép kiểu thủ công trong Java?
Bạn phân biệt an toàn kiểu tại thời điểm biên dịch với kiểm tra kiểu tại runtime khi sử dụng Generics như thế nào?
Bạn thiết kế một lớp Box<T> để lưu và trả về dữ liệu đúng kiểu mà không yêu cầu mã gọi ép kiểu ra sao?
Bạn giải thích ý nghĩa của tham số kiểu T trong khai báo lớp và đối số kiểu String khi tạo đối tượng như thế nào?
Bạn phân biệt tham số kiểu của lớp với kiểu thực tế được truyền khi sử dụng lớp đó ra sao?
Bạn lựa chọn tên E, K, V, T hoặc R cho các tham số kiểu để diễn đạt vai trò của chúng như thế nào?
Bạn đánh giá lợi ích và hạn chế của việc khai báo một lớp với nhiều tham số kiểu như Pair<K,V> ra sao?
Bạn thiết kế một interface Repository<ID, E> để bảo đảm kiểu khóa và kiểu thực thể được kiểm tra khi compile như thế nào?
Bạn giải thích cách một lớp triển khai generic interface với kiểu cố định khác với lớp tiếp tục khai báo type parameter ra sao?
Bạn phân tích sự khác biệt giữa List<String>, List<Integer> và List<Object> trong hệ thống kiểu của Java như thế nào?
Bạn giải thích vì sao List<String> không phải là subtype của List<Object> mặc dù String là subtype của Object ra sao?
Bạn so sánh tính bất biến của generic type argument với tính hiệp biến của mảng Java và các đánh đổi về type safety như thế nào?
Bạn dùng List<?> để viết phương thức chấp nhận danh sách chưa biết kiểu phần tử mà không làm mất an toàn kiểu ra sao?
Bạn phân biệt List<?> với raw type List theo thông tin kiểu còn được compiler kiểm tra như thế nào?
Bạn phân biệt các thao tác đọc và ghi hợp lệ trên tham chiếu kiểu List<?> dựa trên những bảo đảm nào của compiler?
Bạn giải thích vì sao một List<?> không cho phép thêm đối tượng tùy ý dù bản thân danh sách có thể thay đổi ra sao?
Bạn thiết kế một generic method để hoán đổi hai phần tử của danh sách bất kỳ mà không ép kiểu không kiểm soát như thế nào?
Bạn phân biệt generic method với phương thức dùng type parameter đã khai báo ở cấp lớp ra sao?
Bạn giải thích vị trí khai báo <T> trong generic method và cách compiler suy luận kiểu trả về ra sao?
Bạn thiết kế một generic constructor trong một lớp không generic và xác định tình huống phù hợp để sử dụng như thế nào?
Bạn phân biệt generic static method với việc dùng type parameter của lớp trong static context theo quy tắc nào?
Bạn giải thích vì sao static field không thể có kiểu T là tham số kiểu của generic class ra sao?
Bạn phân tích lợi ích của diamond operator khi khởi tạo các collection generic so với viết lặp type argument như thế nào?
Bạn xác định khi nào compiler không thể suy luận kiểu của biểu thức generic và cần khai báo type argument rõ ràng ra sao?
Bạn sử dụng explicit type witness cho một generic method khi kiểu suy luận không đáp ứng hợp đồng mong muốn như thế nào?
Bạn phân biệt type inference ở lời gọi phương thức với phép ép kiểu tại runtime về khả năng phát hiện lỗi ra sao?
Bạn đánh giá tác động của target typing đối với kiểu được suy luận cho biểu thức generic khi gán hoặc trả về như thế nào?
Bạn phân tích trường hợp kết hợp diamond operator và anonymous class khiến hành vi suy luận kiểu cần được chú ý ra sao?
Bạn lựa chọn sử dụng var hay khai báo kiểu tường minh khi kiểu suy luận của một generic factory method không rõ ràng ra sao?
Bạn giải thích vai trò của bounded type parameter trong việc cho phép gọi các phương thức của một kiểu cha như thế nào?
Bạn thiết kế phương thức tìm giá trị lớn nhất bằng <T extends Comparable<T>> và đánh giá giới hạn của ràng buộc đó ra sao?
Bạn phân tích lý do một API có thể dùng Comparable<? super T> thay cho Comparable<T> để chấp nhận thêm kiểu hợp lệ như thế nào?
Bạn khai báo một type parameter có ràng buộc lớp cha và nhiều interface mà vẫn tuân thủ thứ tự bound của Java như thế nào?
Bạn phân biệt multiple bounds của type parameter với việc một lớp được kế thừa trực tiếp nhiều class như thế nào?
Bạn giải thích intersection type giúp một phương thức generic sử dụng đồng thời nhiều hợp đồng hành vi ra sao?
Bạn đánh giá khi nào dùng <T extends Number> hợp lý và khi nào nên dựa vào một interface nghiệp vụ thay vì Number như thế nào?
Bạn phân tích rủi ro khi ràng buộc type parameter quá chặt làm giảm khả năng tái sử dụng của API ra sao?
Bạn giải thích recursive type bound trong Enum<E extends Enum<E>> hoặc Comparable<T> hỗ trợ quan hệ kiểu như thế nào?
Bạn thiết kế self-referential generic type cho một builder hoặc fluent API mà vẫn giới hạn ép kiểu không an toàn ra sao?
Bạn phân biệt type parameter bound với wildcard bound khi thiết kế phương thức nhận collection như thế nào?
Bạn giải thích ý nghĩa của upper-bounded wildcard trong List<? extends Number> khi đọc phần tử từ collection ra sao?
Bạn xác định kiểu giá trị nào có thể đọc an toàn từ List<? extends Number> và lý do giới hạn thao tác thêm phần tử như thế nào?
Bạn phân tích vì sao List<? extends Number> có thể tham chiếu List<Integer> hoặc List<Double> nhưng không chấp nhận thêm Number tùy ý ra sao?
Bạn giải thích ý nghĩa của lower-bounded wildcard trong List<? super Integer> khi collection được dùng làm đích nhận dữ liệu như thế nào?
Bạn xác định những giá trị nào có thể thêm an toàn vào List<? super Integer> và kiểu dữ liệu đọc ra được bảo đảm ra sao?
Bạn áp dụng nguyên tắc PECS để thiết kế phương thức sao chép phần tử từ collection nguồn sang collection đích như thế nào?
Bạn phân biệt producer và consumer dựa trên cách một tham số collection được sử dụng bên trong phương thức ra sao?
Bạn thiết kế chữ ký cho phương thức chỉ duyệt hoặc thống kê phần tử để tránh dùng wildcard có giới hạn không cần thiết như thế nào?
Bạn giải thích vì sao List<? extends Object> không tương đương hoàn toàn với List<Object> về khả năng ghi dữ liệu như thế nào?
Bạn phân tích sự khác biệt giữa List<? extends T> và một type parameter <E extends T> khi phương thức cần liên hệ kiểu của nhiều tham số ra sao?
Bạn chọn wildcard hay type parameter có tên khi kiểu trả về cần liên hệ chính xác với kiểu phần tử đầu vào như thế nào?
Bạn giải thích wildcard capture là gì và vì sao compiler coi kiểu ẩn trong List<?> là một kiểu cụ thể chưa biết như thế nào?
Bạn thiết kế helper method generic để xử lý một thao tác trên List<?> bị compiler từ chối do wildcard capture ra sao?
Bạn phân tích vì sao hoán đổi hai phần tử trong cùng List<?> có thể hợp lệ qua một helper generic dù thêm phần tử tùy ý không hợp lệ như thế nào?
Bạn so sánh List<?>, List<? extends Number> và List<? super Integer> trong một bài toán API đọc ghi dữ liệu như thế nào?
Bạn lựa chọn wildcard bound nào cho Comparator khi thuật toán cần so sánh phần tử kiểu T, và vì sao?
Bạn giải thích vai trò của Comparator<? super T> trong thuật toán sắp xếp tập các đối tượng kiểu T như thế nào?
Bạn thiết kế generic method nhận Function<? super T, ? extends R> để ánh xạ phần tử sang một kiểu kết quả khác ra sao?
Bạn phân tích cách áp dụng PECS cho Consumer<? super T> và Supplier<? extends T> trong API xử lý bất đồng bộ như thế nào?
Bạn lựa chọn kiểu generic cho một phương thức addAll sao cho collection nguồn có thể chứa subtype của phần tử đích như thế nào?
Bạn giải thích vì sao Collections.copy có chữ ký cho phép nguồn và đích dùng các kiểu khác nhau nhưng vẫn an toàn ra sao?
Bạn thiết kế API xuất dữ liệu có tham số đầu vào là Iterable<? extends T> mà không buộc consumer biết implementation cụ thể như thế nào?
Bạn đánh giá tác động đến tính dễ đọc khi một public API lồng nhiều wildcard và bounded type parameter như thế nào?
Bạn xử lý một chữ ký generic phức tạp bằng cách đặt tên abstraction hoặc tách phương thức mà không mất type safety ra sao?
Bạn giải thích type erasure là gì và nó ảnh hưởng đến generic type argument trong bytecode như thế nào?
Bạn phân biệt kiểm tra kiểu do compiler thực hiện với thông tin type argument còn tồn tại trong metadata của class file ra sao?
Bạn mô tả cách type erasure thay thế một type parameter không bound hoặc có bound bằng kiểu tương ứng trong bytecode như thế nào?
Bạn giải thích tại sao có thể tồn tại cast được compiler chèn vào khi đọc phần tử từ một generic collection ra sao?
Bạn phân tích một ClassCastException xảy ra muộn khi một raw reference đã đưa phần tử sai kiểu vào List<String> như thế nào?
Bạn xác định vì sao không thể tạo trực tiếp một instance bằng biểu thức new T() trong generic class như thế nào?
Bạn thiết kế factory hoặc Supplier<T> để tạo đối tượng kiểu T mà không phụ thuộc vào thông tin type argument bị xóa ra sao?
Bạn giải thích lý do không thể dùng instanceof List<String> để kiểm tra tham số kiểu của danh sách tại runtime như thế nào?
Bạn phân biệt phép kiểm tra instanceof List<?> hợp lệ với phép kiểm tra một parameterized type cụ thể không thể thực hiện như thế nào?
Bạn sử dụng Class<T> làm type token để kiểm tra và ép kiểu giá trị runtime một cách có kiểm soát ra sao?
Bạn phân tích giới hạn của Class<T> khi cần biểu diễn List<String> hoặc Map<String,Integer> đầy đủ tại runtime như thế nào?
Bạn giải thích vì sao List<String>.class không phải class literal hợp lệ và những cách khác để mô tả generic type ra sao?
Bạn thiết kế một type reference hoặc type token dựa trên parameterized superclass để giữ thông tin generic cho thư viện serialization như thế nào?
Bạn phân biệt Type, Class, ParameterizedType và TypeVariable trong Java reflection khi đọc chữ ký generic như thế nào?
Bạn sử dụng getGenericSuperclass và getGenericInterfaces để khảo sát khai báo generic của một class ra sao?
Bạn phân tích vì sao reflection có thể đọc generic signature của lớp nhưng không thể tự biết type argument của mọi instance sau erasure như thế nào?
Bạn đánh giá khi nào type token của Jackson hoặc HTTP client giúp tránh mất thông tin kiểu khi deserialize danh sách đối tượng ra sao?
Bạn xác định cách kiểm chứng dữ liệu runtime đã deserialize thật sự phù hợp với generic type mà API công bố như thế nào?
Bạn giải thích vì sao không thể khai báo một phương thức overload chỉ khác List<String> và List<Integer> do type erasure như thế nào?
Bạn thiết kế lại hai overload bị trùng erasure bằng tên phương thức hoặc abstraction rõ nghĩa như thế nào?
Bạn phân biệt method signature ở mức Java source với method descriptor trong JVM khi generics bị xóa ra sao?
Bạn mô tả cơ chế compiler tạo bridge method để duy trì đa hình sau khi type erasure như thế nào?
Bạn dùng ví dụ lớp triển khai Comparable<String> để giải thích bridge method kết nối lời gọi qua kiểu bị xóa ra sao?
Bạn phân tích vì sao stack trace hoặc reflection có thể xuất hiện method synthetic hoặc bridge mà mã nguồn không khai báo như thế nào?
Bạn kiểm tra bridge method bằng javap hoặc Method.isBridge để điều tra lỗi liên quan overriding generic ra sao?
Bạn đánh giá ảnh hưởng của việc thay đổi bound hoặc generic method signature đến khả năng tương thích nhị phân của thư viện như thế nào?
Bạn giải thích vì sao Java không cho phép tạo generic array bằng new T[n] khi thành phần kiểu không reifiable như thế nào?
Bạn phân biệt mảng Java kiểm tra kiểu phần tử ở runtime với List<T> chủ yếu được kiểm tra tại compile time ra sao?
Bạn phân tích điều gì khiến phép gán một mảng subtype cho biến mảng supertype có thể gây ArrayStoreException như thế nào?
Bạn đánh giá sự khác nhau giữa new List<String>[n] và new List<?>[n] theo quy tắc tạo mảng generic của Java ra sao?
Bạn giải thích heap pollution là gì và nó có thể xuất hiện khi generic reference trỏ đến dữ liệu không đúng kiểu ra sao?
Bạn phân tích một trường hợp generic varargs method tạo heap pollution do mảng tham số bị alias hoặc ghi giá trị không hợp lệ ra sao?
Bạn phân biệt @SafeVarargs với @SuppressWarnings về ý nghĩa bảo đảm an toàn và vị trí nên sử dụng như thế nào?
Bạn xác định điều kiện một generic varargs method thực sự an toàn trước khi thêm @SafeVarargs như thế nào?
Bạn thiết kế API nhận List<List<T>> hoặc collection thay cho generic array để giảm nguy cơ heap pollution ra sao?
Bạn kiểm tra và xử lý unchecked conversion warning khi truyền raw collection vào API generic như thế nào?
Bạn phân biệt unchecked cast với một phép cast runtime được JVM kiểm tra đầy đủ về type argument như thế nào?
Bạn giới hạn phạm vi @SuppressWarnings("unchecked") khi cần tích hợp một API cũ không generic theo cách nào?
Bạn thiết kế adapter chuyển raw collection sang List<T> bằng cách xác thực từng phần tử tại runtime như thế nào?
Bạn đánh giá vì sao việc bỏ qua cảnh báo compiler về unchecked operation có thể che giấu lỗi an toàn kiểu trong production ra sao?
Bạn giải thích giới hạn của Generics với primitive type và cách autoboxing ảnh hưởng đến bộ nhớ, CPU như thế nào?
Bạn lựa chọn List<Integer> hay mảng int[] trong một bài toán xử lý số lượng dữ liệu lớn dựa trên những yếu tố nào?
Bạn phân tích vì sao type parameter không thể dùng trong catch clause hoặc khai báo generic class kế thừa Throwable như thế nào?
Bạn giải thích quy tắc generic method có thể khai báo checked exception phụ thuộc type parameter theo cách nào?
Bạn đánh giá những hạn chế khi một type parameter được dùng trong static context hoặc một biểu thức instanceof ra sao?
Bạn thiết kế lớp generic bất biến có các field final để consumer không thể làm thay đổi trạng thái qua API trả về như thế nào?
Bạn phân biệt kiểu trả về List<T> với List<? extends T> trong thiết kế API khi caller cần sửa collection ra sao?
Bạn xây dựng API fluent builder dùng type parameter để giữ lại kiểu kết quả qua nhiều bước cấu hình ra sao?
Bạn kiểm soát khả năng thay thế implementation khi một generic interface được mở rộng bởi nhiều repository cụ thể như thế nào?
Bạn giải thích cách generic subtype kế thừa một parameterized superclass và ràng buộc các type parameter được lan truyền ra sao?
Bạn thiết kế một generic abstract class mà subclass cố định một type argument còn subclass khác tiếp tục để mở như thế nào?
Bạn đánh giá vì sao dùng raw base class trong một hệ phân cấp generic có thể tạo lỗi overriding và cảnh báo không mong muốn ra sao?
Bạn phân biệt covariance và contravariance tại vị trí sử dụng wildcard với cách khai báo variance ở ngôn ngữ khác như thế nào?
Bạn giải thích vì sao Java Generics áp dụng use-site variance và sự lựa chọn đó ảnh hưởng đến thiết kế thư viện như thế nào?
Bạn phân tích vì sao new ArrayList<? extends Number>() không hợp lệ nhưng new ArrayList<>() có thể suy luận kiểu từ ngữ cảnh như thế nào?
Bạn phân tích các giới hạn và suy luận của diamond operator khi bên trái chứa wildcard type như thế nào?
Bạn thiết kế chữ ký generic cho một hàm merge hai danh sách subtype thành collection chung mà vẫn tránh cast không an toàn ra sao?
Bạn sử dụng type inference để kết hợp Optional.map và flatMap mà không tạo Optional lồng nhau như thế nào?
Bạn phân biệt chữ ký của Stream.map, Stream.flatMap và Collectors.toMap theo mối liên hệ giữa các type parameter ra sao?
Bạn xử lý trường hợp Stream.collect không suy luận được kiểu collector mong muốn bằng cách điều chỉnh chữ ký hoặc khai báo kiểu ra sao?
Bạn giải thích tác động của overloaded method lên việc compiler chọn target type cho lambda và generic method như thế nào?
Bạn điều tra một thông báo lỗi ambiguous method call xuất hiện sau khi thêm overload generic bằng cách nào?
Bạn xác định vì sao lambda có tham số không khai báo kiểu có thể cần ngữ cảnh target type mới compile được như thế nào?
Bạn so sánh cách generic method inference xử lý method reference với lambda tương đương trong một trường hợp overload như thế nào?
Bạn thiết kế Comparator.comparing với key extractor generic để sắp xếp dữ liệu theo nhiều tiêu chí ra sao?
Bạn phân tích khi nào Optional<T> giúp mô tả khả năng thiếu giá trị rõ hơn việc trả về null từ generic repository như thế nào?
Bạn đánh giá rủi ro khi khai báo public API trả về Object thay vì một type parameter thích hợp trong mã mới ra sao?
Bạn thiết kế test compile-time cho những kết hợp kiểu phải hợp lệ và không hợp lệ trong một generic library như thế nào?
Bạn lựa chọn cách dùng compiler warnings như -Xlint:unchecked để phát hiện điểm yếu về Generics trong CI ra sao?
Bạn kiểm thử một generic collection với nhiều implementation và subtype khác nhau để xác minh hành vi của API ra sao?
Bạn thiết kế unit test cho một method <T extends Comparable<? super T>> khi xử lý danh sách rỗng hoặc chỉ có một phần tử như thế nào?
Bạn phân biệt lỗi dữ liệu runtime với lỗi hợp đồng generic khi test một adapter đọc đối tượng từ nguồn không type-safe ra sao?
Bạn xác định những tiêu chí review để tránh raw type, unchecked cast và wildcard quá rộng trong public API như thế nào?
Bạn so sánh khả năng bảo trì của API generic rất tổng quát với một số interface chuyên biệt hơn theo yêu cầu nghiệp vụ ra sao?
Bạn lập kế hoạch chuyển mã dùng raw List hoặc Map sang khai báo generic mà vẫn bảo đảm tương thích với client hiện có như thế nào?
Bạn đánh giá cách bổ sung type parameter vào API thư viện cũ ảnh hưởng đến source compatibility và binary compatibility ra sao?
Bạn thiết kế lộ trình loại bỏ helper ép kiểu không kiểm soát sau khi đưa Generics vào codebase như thế nào?
Một method nhận List<Number> không chấp nhận List<Integer>, bạn sẽ phân tích nguyên nhân và thiết kế lại chữ ký như thế nào?
Một thuật toán cần đọc Number từ nguồn và ghi Integer vào đích nhưng code báo lỗi wildcard capture, bạn sẽ áp dụng PECS và helper như thế nào?
Một API dùng List<? super Integer> rồi ép mọi phần tử đọc được thành Integer, bạn sẽ giải thích rủi ro và sửa lại ra sao?
Một thư viện deserialize JSON thành List<Map> dù consumer kỳ vọng List<Order>, bạn sẽ xác định thiếu sót trong type token như thế nào?
Một chương trình ném ClassCastException sau khi dùng raw List kết hợp List<String>, bạn sẽ truy tìm nơi phát sinh heap pollution như thế nào?
Một generic varargs method chạy đúng trong vài test nhưng lỗi khi mảng tham số bị sửa qua Object[], bạn sẽ thiết kế lại API như thế nào?
Một lớp con override phương thức generic nhưng javap hiển thị thêm bridge method, bạn sẽ giải thích mục đích và kiểm tra tính tương thích ra sao?
Một nhóm thêm overload chỉ khác List<String> và List<Long> rồi gặp name clash, bạn sẽ phân tích erasure và đề xuất hợp đồng thay thế như thế nào?
Một generic factory cần tạo T tại runtime nhưng compiler không chấp nhận new T(), bạn sẽ lựa chọn Supplier<T> hay Class<T> theo những tiêu chí nào?
Sau khi nâng cấp Java hoặc dependency, một lời gọi method reference trở nên ambiguous, bạn sẽ điều tra type inference và overload resolution như thế nào?
Một public API trả về List<? extends Entity> khiến client không thể thêm dữ liệu hợp lệ, bạn sẽ xem lại quyền ghi và kiểu trả về ra sao?
Bạn xây dựng bộ tiêu chí thiết kế và kiểm thử Generics cho một Java library dựa trên an toàn kiểu, khả năng suy luận, PECS và giới hạn runtime như thế nào?
