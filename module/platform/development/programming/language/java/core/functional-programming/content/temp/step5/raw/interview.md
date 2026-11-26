Bạn giải thích phong cách lập trình hàm trong Java khác mã mệnh lệnh khi xử lý một tập dữ liệu như thế nào?
Bạn phân biệt functional programming của Java với ngôn ngữ thuần hàm về khả năng chứa mutable state ra sao?
Bạn sẽ nhận diện pure function thông qua đầu vào, đầu ra và side effects theo tiêu chí nào?
Bạn phân biệt referential transparency với một method chỉ có tên gọi mang tính hàm như thế nào?
Bạn sẽ xác định lợi ích của immutable data khi ghép nhiều phép biến đổi trên cùng dữ liệu ra sao?
Bạn phân tích vì sao tránh sửa collection đầu vào làm việc kiểm thử và sử dụng lại hàm đơn giản hơn như thế nào?
Bạn sẽ so sánh vòng for với Stream pipeline theo độ rõ ràng và khả năng kiểm soát luồng như thế nào?
Bạn phân biệt declarative style với imperative style mà không giả định kiểu nào luôn nhanh hơn ra sao?
Bạn sẽ quyết định khi nào một vòng lặp dễ hiểu hơn chuỗi map, filter và reduce theo tiêu chí nào?
Bạn mô tả higher-order function trong Java thông qua functional interface được nhận hoặc trả về như thế nào?
Bạn sẽ đưa một quy tắc lọc hardcode thành Predicate được truyền vào method theo cách nào?
Bạn phân tích vì sao quá nhiều lambda lồng nhau có thể khiến logic khó theo dõi hơn như thế nào?
Bạn sẽ thiết kế API nhận hành vi thay vì nhiều cờ boolean điều khiển các nhánh xử lý ra sao?
Bạn phân biệt tính bất biến của object với biến local effectively final theo nghĩa nào?
Bạn sẽ xác định ranh giới giữa phép biến đổi thuần túy và bước thực hiện I/O hay logging như thế nào?
Bạn mô tả cách function composition giúp tái sử dụng các quy tắc biến đổi nhỏ như thế nào?
Bạn sẽ tách một hàm vừa gọi database vừa ánh xạ DTO để mỗi phần có thể kiểm thử độc lập ra sao?
Bạn phân tích tại sao mutation ẩn trong pipeline có thể làm kết quả phụ thuộc thứ tự thực thi như thế nào?
Bạn sẽ lựa chọn tạo immutable snapshot hay mutation cục bộ để cân bằng tính rõ ràng và chi phí memory ra sao?
Bạn phân biệt functional interface với callback bất kỳ dựa trên hợp đồng abstract method nào?
Bạn sẽ thiết kế luồng xử lý tránh bắt buộc kiểm tra null và exception ở mọi bước như thế nào?
Bạn phân tích vì sao code viết theo phong cách hàm chưa chắc thread-safe khi có shared mutable state như thế nào?
Bạn sẽ giải thích việc tách dữ liệu đầu vào, transformation và output làm giảm coupling như thế nào?
Bạn sẽ đề xuất tiêu chí review một pipeline theo readability, side effects, complexity và error handling ra sao?
Bạn giải thích Single Abstract Method (SAM) xác định một functional interface trong Java như thế nào?
Bạn phân biệt annotation @FunctionalInterface với điều kiện compiler xác định một interface là functional ra sao?
Bạn mô tả vì sao interface có default và static methods vẫn có thể là functional interface như thế nào?
Bạn sẽ xác định ảnh hưởng của phương thức tương ứng public methods của Object tới việc đếm SAM ra sao?
Bạn phân biệt Function, Predicate, Consumer và Supplier theo đầu vào, giá trị trả về và tác dụng nào?
Bạn sẽ dùng Function<T,R> ánh xạ entity thành DTO trong một API ra sao?
Bạn mô tả Predicate<T>.test được sử dụng trong điều kiện lọc theo chính sách nào?
Bạn sẽ lựa chọn Consumer<T> khi cần xử lý side effect nhưng không có kết quả trả về như thế nào?
Bạn phân biệt Supplier<T> với Function<T,R> khi nguồn giá trị chỉ được gọi lúc cần ra sao?
Bạn sẽ sử dụng BiFunction<T,U,R> khi một phép tính phụ thuộc hai giá trị đầu vào như thế nào?
Bạn phân biệt BiPredicate và BiConsumer về hợp đồng trả kết quả hoặc thực hiện hành động ra sao?
Bạn sẽ lựa chọn UnaryOperator<T> thay cho Function<T,T> theo ngữ nghĩa nào?
Bạn mô tả BinaryOperator<T> như trường hợp đặc biệt của BiFunction<T,T,T> như thế nào?
Bạn sẽ dùng Comparator<T> dưới dạng lambda khi sắp xếp dữ liệu nhiều tiêu chí ra sao?
Bạn phân biệt Runnable với Callable<V> về return value và checked exception như thế nào?
Bạn sẽ dùng ToIntFunction<T> để trích xuất primitive int mà không cần boxing ra sao?
Bạn phân biệt IntPredicate, IntConsumer và IntSupplier với bản generic về primitive specialization như thế nào?
Bạn sẽ sử dụng IntUnaryOperator và LongBinaryOperator trong một phép biến đổi số theo trường hợp nào?
Bạn phân tích vì sao không nên dựa vào object identity ổn định của một lambda expression qua các lần đánh giá ra sao?
Bạn sẽ định nghĩa custom functional interface khi các interface JDK không diễn đạt rõ domain contract ra sao?
Bạn phân tích trade-off của custom interface cho phép checked exception so với Function chuẩn như thế nào?
Bạn sẽ đọc compiler error thế nào nếu một interface vô tình có hai abstract methods không tương thích?
Bạn mô tả generic type parameters giúp một custom functional interface tái sử dụng cho nhiều data types ra sao?
Bạn phân biệt default method với SAM implementation được lambda cung cấp theo cơ chế nào?
Bạn sẽ thiết kế functional interface cho validation trả thông tin lỗi thay vì chỉ boolean như thế nào?
Bạn phân tích vì sao custom interface tên quá chung chung khiến callback API khó hiểu ra sao?
Bạn sẽ lựa chọn Optional, result object hay exception cho return type của custom validator theo trường hợp nào?
Bạn mô tả primitive functional interfaces giúp giảm autoboxing trong xử lý dữ liệu lớn ra sao?
Bạn sẽ sử dụng Predicate.not trên bản Java hỗ trợ khi một điều kiện cần đảo ngược như thế nào?
Bạn sẽ kiểm thử custom functional interface bằng lambda và method reference theo những đặc trưng nào?
Bạn giải thích lambda expression thực thi hợp đồng một functional interface mà không cần anonymous class như thế nào?
Bạn phân biệt cú pháp lambda không tham số, một tham số và nhiều tham số ra sao?
Bạn mô tả target typing cho phép compiler suy luận kiểu lambda từ ngữ cảnh gán như thế nào?
Bạn sẽ xác định vì sao cùng một lambda hợp lệ với functional interface này nhưng lỗi với interface khác ra sao?
Bạn phân biệt expression lambda với block lambda khi cần nhiều statement hoặc return như thế nào?
Bạn sẽ giải thích tại sao block lambda có return value phải khớp functional method signature như thế nào?
Bạn phân tích vì sao một lambda đứng riêng không có target type có thể không biên dịch ra sao?
Bạn sẽ xác định tác động của generic method type inference khi truyền lambda làm argument như thế nào?
Bạn phân biệt overload resolution giữa các functional interfaces khi một lambda có thể phù hợp nhiều chữ ký ra sao?
Bạn sẽ xử lý ambiguous overload khi compiler không chọn được phương thức từ target type như thế nào?
Bạn mô tả lambda capture local variable và method parameters trong scope bên ngoài như thế nào?
Bạn giải thích effectively final có ý nghĩa gì với local variable được lambda capture?
Bạn sẽ xác định vì sao không thể gán lại local variable đã capture mà vẫn biên dịch như thế nào?
Bạn phân biệt capture reference effectively final với việc thay đổi mutable object mà reference đó trỏ tới ra sao?
Bạn phân tích nguy cơ capture ArrayList rồi cập nhật trong parallel stream gây race condition như thế nào?
Bạn sẽ thay việc tăng counter ngoài lambda bằng reduce hoặc collect theo cách nào?
Bạn phân biệt this trong lambda với this trong anonymous inner class về instance được tham chiếu ra sao?
Bạn sẽ xác định quy tắc shadowing tên local variables trong lambda khác anonymous class như thế nào?
Bạn mô tả tại sao return trong lambda không phải return của method bao ngoài như thế nào?
Bạn phân biệt checked exception và runtime exception trong lambda gán cho Function chuẩn ra sao?
Bạn sẽ thiết kế xử lý IOException khi lambda gọi một API có checked exception mà không nuốt lỗi như thế nào?
Bạn phân tích rủi ro lambda quá dài làm mờ trách nhiệm và khó debug hơn ra sao?
Bạn sẽ tách lambda phức tạp thành named method hoặc method reference để dễ đọc như thế nào?
Bạn mô tả invokedynamic thường xuất hiện trong cách javac biên dịch lambda theo cơ chế nào?
Bạn phân biệt lambda với anonymous class về identity và semantics của this ra sao?
Bạn sẽ giải thích vì sao không nên serialize lambda để lưu workflow nghiệp vụ lâu dài như thế nào?
Bạn phân tích rủi ro giả định lambda luôn được khởi tạo mới hoặc luôn tái sử dụng instance ra sao?
Bạn sẽ dùng lambda trong Comparator.comparing và thenComparing để sắp xếp nhiều tiêu chí như thế nào?
Bạn sẽ kiểm thử lambda có side effects khi callback có thể chạy nhiều lần hoặc bị short-circuit như thế nào?
Bạn phân biệt capture constructor parameter với đọc instance field trong callback chạy về sau ra sao?
Bạn giải thích method reference là cách biểu diễn một lambda gọi phương thức có sẵn trong trường hợp nào?
Bạn phân biệt ClassName::staticMethod với instance::instanceMethod theo receiver được cố định ra sao?
Bạn mô tả TypeName::instanceMethod lấy receiver từ tham số đầu của functional method như thế nào?
Bạn sẽ dùng String::trim thay lambda gọi trim trong pipeline theo tiêu chí nào?
Bạn phân biệt SomeClass::new với lambda gọi constructor theo target type như thế nào?
Bạn sẽ sử dụng array constructor reference như int[]::new khi cần cấp phát mảng theo kích thước ra sao?
Bạn giải thích method reference cũng đòi hỏi target functional interface để compiler kiểm tra compatibility như thế nào?
Bạn sẽ phân tích overload resolution của một referenced method khi có nhiều phiên bản nhận tham số ra sao?
Bạn phân biệt bound method reference với unbound method reference theo thời điểm chọn receiver như thế nào?
Bạn phân tích tại sao tạo bound method reference từ receiver null có thể thất bại trước khi callback chạy ra sao?
Bạn sẽ xác định type inference của generic method reference khi gán vào Function như thế nào?
Bạn mô tả hạn chế của method reference khi cần giữ nguyên một đối số cố định mà referenced method chưa nhận sẵn như thế nào?
Bạn sẽ chọn lambda thay method reference khi cần biến đổi input trước khi gọi method như thế nào?
Bạn phân tích nguy cơ constructor reference có side effects nhưng chỉ thực thi khi Stream terminal operation chạy ra sao?
Bạn sẽ kiểm tra checked exception của referenced method với signature của functional interface như thế nào?
Bạn phân biệt method reference capture một receiver với kết quả được method trả về khi callback thực thi ra sao?
Bạn sẽ quyết định khi nào một method reference quá ngắn nhưng làm mất ý nghĩa nghiệp vụ so với lambda ra sao?
Bạn sẽ dùng Objects::nonNull trong điều kiện lọc và xác định ngữ nghĩa đối với null như thế nào?
Bạn mô tả Comparator.comparing nhận method reference làm key extractor như thế nào?
Bạn sẽ thiết kế negative test cho constructor reference để phát hiện input không hợp lệ như thế nào?
Bạn giải thích Function.andThen và Function.compose khác nhau về thứ tự thực thi hai phép biến đổi như thế nào?
Bạn sẽ hợp thành các bước chuẩn hóa chuỗi, validate và chuyển thành value object bằng Function như thế nào?
Bạn phân biệt Predicate.and, Predicate.or và Predicate.negate theo logic điều kiện nào?
Bạn mô tả short-circuit trong Predicate.and hoặc Predicate.or ảnh hưởng việc gọi predicate tiếp theo như thế nào?
Bạn phân tích vì sao đặt side effects trong predicate làm kết quả phụ thuộc thứ tự kết hợp ra sao?
Bạn sẽ sử dụng Function.identity trong một collector khi muốn giữ nguyên key hoặc value như thế nào?
Bạn phân biệt Consumer.andThen và Function.andThen về việc có return value ra sao?
Bạn sẽ xây dựng các quy tắc validation tái sử dụng bằng Predicate composition thay nhiều if trùng lặp như thế nào?
Bạn mô tả một method nhận Function như chiến lược mapping có thể mở rộng API ra sao?
Bạn sẽ thiết kế function trả về Predicate đã được cấu hình ngưỡng nghiệp vụ theo cách nào?
Bạn phân tích rủi ro closure giữ mutable configuration khiến function không còn deterministic ra sao?
Bạn sẽ chọn function composition thay class chiến lược riêng khi hành vi không có nhiều dependencies như thế nào?
Bạn phân biệt composition đồng bộ với việc hợp thành CompletableFuture khi kết quả đến bất đồng bộ ra sao?
Bạn sẽ dùng UnaryOperator.identity hoặc Function.identity cho phép biến đổi giữ nguyên giá trị trong trường hợp nào?
Bạn phân tích nguy cơ gọi database trong Predicate.test cho mỗi phần tử Stream có hàng triệu records như thế nào?
Bạn sẽ thiết kế validation pipeline giữ được lý do thất bại thay vì gộp mọi điều kiện thành boolean như thế nào?
Bạn sẽ sắp xếp Predicate có chi phí cao và thấp nhằm tận dụng short-circuit mà vẫn giữ đúng ngữ nghĩa như thế nào?
Bạn phân biệt Function trả Optional.empty với Function ném exception khi tính toán thất bại ra sao?
Bạn sẽ tránh dùng Function<Object,Object> làm mất type safety trong API nhận callback như thế nào?
Bạn mô tả điều kiện identity và associative combiner quan trọng thế nào trong phép gộp song song ra sao?
Bạn sẽ dùng BinaryOperator.minBy hoặc maxBy cùng Comparator để chọn kết quả tốt hơn như thế nào?
Bạn phân tích khi nào chuỗi function compositions quá dài nên thay bằng các method có tên domain rõ ràng ra sao?
Bạn sẽ kiểm thử từng hàm đơn lẻ và một chain Function.compose/andThen theo bất biến nào?
Bạn giải thích Optional<T> biểu diễn giá trị có thể vắng mặt khác null reference theo mục đích thiết kế nào?
Bạn phân biệt Optional.empty với null truyền trong API cũ về tính rõ ràng của hợp đồng như thế nào?
Bạn sẽ chọn Optional.of, ofNullable hoặc empty khi tạo giá trị từ nguồn input như thế nào?
Bạn mô tả tại sao Optional.of(null) và Optional.ofNullable(null) có hành vi khác nhau ra sao?
Bạn sẽ dùng Optional.map để biến đổi giá trị chỉ khi có mặt như thế nào?
Bạn phân biệt Optional.map với flatMap khi mapping function đã trả Optional như thế nào?
Bạn phân tích tại sao Optional.map trả null có thể âm thầm biến kết quả thành empty ra sao?
Bạn sẽ dùng Optional.filter khi chỉ muốn giữ giá trị đáp ứng business predicate như thế nào?
Bạn phân biệt Optional.orElse với orElseGet về eager và lazy evaluation của fallback ra sao?
Bạn sẽ giải thích vì sao biểu thức cấp phát resource trong orElse được tính ngay cả khi Optional không rỗng như thế nào?
Bạn mô tả Optional.orElseThrow nhận Supplier exception để thể hiện lỗi not-found như thế nào?
Bạn sẽ phân biệt Optional.get và orElseThrow không đối số về cách diễn đạt điều kiện dự kiến có dữ liệu ra sao?
Bạn phân tích rủi ro gọi Optional.get không kiểm tra khiến lỗi absence chỉ đổi tên như thế nào?
Bạn sẽ dùng Optional.ifPresentOrElse ở phiên bản JDK phù hợp khi có hai nhánh xử lý ra sao?
Bạn phân biệt ifPresent thực hiện side effect với map tạo Optional kết quả mới như thế nào?
Bạn sẽ dùng Optional.or để thử nguồn Optional dự phòng theo chính sách nào?
Bạn mô tả Optional.stream tạo không hoặc một phần tử cho Stream pipeline như thế nào?
Bạn sẽ sử dụng Stream.ofNullable để xử lý một input có thể null trên JDK hỗ trợ như thế nào?
Bạn phân tích tại sao Optional không tự động phù hợp làm field của mọi JPA entity hoặc domain object ra sao?
Bạn sẽ đánh giá Optional nên được dùng làm return type hay parameter theo API contract nào?
Bạn phân biệt Optional chứa chuỗi rỗng với Optional.empty dưới một quy tắc validation ra sao?
Bạn sẽ dùng OptionalInt và OptionalDouble khi làm việc với primitive results để tránh boxing ra sao?
Bạn phân tích vì sao OptionalDouble.empty không thể thay bằng số 0 khi tính average trên dữ liệu rỗng như thế nào?
Bạn sẽ thiết kế service lookup trả Optional cho not-found nhưng tách lỗi database theo cơ chế nào?
Bạn phân biệt Optional biểu diễn absence với Result/Either lưu chi tiết lỗi theo nhu cầu nào?
Bạn sẽ giảm chuỗi Optional.flatMap quá sâu gây khó đọc bằng cách chia các bước có tên như thế nào?
Bạn sẽ viết tests cho Optional có mặt, không có mặt, chuỗi rỗng và exception trong mapper như thế nào?
Bạn giải thích Stream API xử lý một chuỗi phần tử khác Collection lưu trữ phần tử ở đặc điểm nào?
Bạn phân biệt intermediate operations và terminal operations theo thời điểm pipeline được chạy như thế nào?
Bạn mô tả lazy evaluation của filter và map trước khi terminal operation được gọi ra sao?
Bạn sẽ giải thích vì sao xây một pipeline không có terminal operation thì callback thường chưa chạy như thế nào?
Bạn phân tích vì sao một Stream không được dùng lại sau terminal operation theo lifecycle nào?
Bạn sẽ xử lý IllegalStateException khi code cố reuse một Stream đã được consume như thế nào?
Bạn mô tả cách tạo Stream từ Collection.stream, Arrays.stream và Stream.of như thế nào?
Bạn sẽ sử dụng Stream.empty hoặc Stream.builder khi tạo nguồn dữ liệu theo trường hợp nào?
Bạn phân biệt Stream.generate với Stream.iterate theo nguồn giá trị và tính hữu hạn ra sao?
Bạn sẽ dùng Stream.iterate có predicate dừng ở JDK tương thích để tạo dãy hữu hạn như thế nào?
Bạn phân tích rủi ro terminal operation chạy mãi trên Stream vô hạn nếu không có giới hạn hoặc short-circuit ra sao?
Bạn sẽ dùng limit hoặc takeWhile để hạn chế số phần tử cần duyệt theo cách nào?
Bạn phân biệt takeWhile với filter trên ordered stream khi gặp phần tử đầu tiên không hợp lệ ra sao?
Bạn sẽ dùng dropWhile loại phần tiền tố liên tiếp thỏa điều kiện theo ý nghĩa nào?
Bạn phân biệt encounter order với thứ tự callback hoàn tất khi pipeline xử lý song song ra sao?
Bạn sẽ chọn findFirst, findAny hoặc anyMatch dựa trên yêu cầu dừng sớm và thứ tự như thế nào?
Bạn mô tả allMatch và noneMatch xử lý Stream rỗng theo logic nào?
Bạn sẽ giải thích vì sao findAny không bảo đảm chọn phần tử đầu tiên trong ordered stream ra sao?
Bạn phân tích tại sao peek không nên dùng làm transform chính hoặc yêu cầu correctness cho side effects như thế nào?
Bạn sẽ xác định vì sao callback trong peek có thể bị bỏ qua bởi short-circuit hoặc stream optimization ra sao?
Bạn phân biệt forEach với forEachOrdered trong parallel stream về thứ tự tác dụng phụ như thế nào?
Bạn sẽ thiết kế pipeline không phụ thuộc mutation ẩn bên trong map và filter ra sao?
Bạn mô tả Spliterator với các đặc tính ORDERED, SIZED và DISTINCT ảnh hưởng tối ưu pipeline như thế nào?
Bạn sẽ xác định khi nào nguồn Stream cần được close bằng try-with-resources ra sao?
Bạn phân biệt Stream từ Collection với Files.lines về vòng đời tài nguyên như thế nào?
Bạn sẽ so sánh Stream.toList và Collectors.toList theo bảo đảm mutability trên JDK tương ứng như thế nào?
Bạn phân tích vì sao không thể giả định Collectors.toList luôn trả ArrayList cho phép add phần tử ra sao?
Bạn sẽ giải thích tại sao chuyển từ List sang Stream không tự động giảm lượng dữ liệu đầu vào đã nằm trong RAM như thế nào?
Bạn phân biệt pipeline chứa stateful operation và pipeline chỉ có stateless operation về buffering như thế nào?
Bạn sẽ xác định khi nào một Stream pipeline nhiều nhánh khó hiểu hơn vòng lặp rõ ràng ra sao?
Bạn giải thích Stream.filter và Stream.map khác nhau ở việc giữ hoặc biến đổi phần tử như thế nào?
Bạn phân biệt map với flatMap khi một input tạo nhiều outputs theo trường hợp nào?
Bạn sẽ dùng flatMap để chuyển danh sách đơn hàng thành Stream các dòng hàng ra sao?
Bạn mô tả Stream.mapMulti có thể tránh tạo các Stream con khi phát ít phần tử trên JDK hỗ trợ như thế nào?
Bạn sẽ dùng mapToInt và mapToLong khi tính toán primitive để tránh autoboxing ra sao?
Bạn phân biệt IntStream, LongStream và DoubleStream với Stream wrapper types về chi phí và API như thế nào?
Bạn sẽ dùng IntStream.range và rangeClosed khi cần dãy chỉ số với biên phù hợp như thế nào?
Bạn phân tích vì sao dùng IntStream.range để truy cập List theo index không luôn rõ ràng hơn duyệt trực tiếp ra sao?
Bạn mô tả distinct dựa trên equals/hashCode của các phần tử để loại trùng như thế nào?
Bạn sẽ tránh dùng distinct với objects bị mutate khiến hashCode thay đổi trong lúc chạy như thế nào?
Bạn sẽ dùng sorted cùng Comparator.comparing và thenComparing theo nhiều tiêu chí ra sao?
Bạn phân biệt Stream.sorted với List.sort về khả năng làm thay đổi collection ban đầu như thế nào?
Bạn sẽ dùng min hoặc max với Comparator nhưng xử lý trường hợp nguồn rỗng ra sao?
Bạn mô tả reduce với identity và accumulator tính kết quả tổng hợp như thế nào?
Bạn phân biệt reduce trả Optional với overload có identity trả giá trị thường ra sao?
Bạn sẽ giải thích vì sao accumulator của reduce cần associative để chạy song song đúng như thế nào?
Bạn phân tích vì sao phép trừ làm reduce song song cho kết quả phụ thuộc cách chia partitions ra sao?
Bạn sẽ quyết định dùng collect thay reduce khi cần xây cấu trúc mutable theo lý do nào?
Bạn mô tả collect với supplier, accumulator và combiner xử lý partial results như thế nào?
Bạn phân biệt reduce có mutable accumulator với collect về contract và nguy cơ shared mutation ra sao?
Bạn sẽ dùng anyMatch và noneMatch thay vì tự đếm số phần tử thỏa điều kiện theo mục tiêu nào?
Bạn phân tích vì sao Stream.count có thể được tối ưu mà không gọi mọi callback peek ở một số nguồn ra sao?
Bạn sẽ dự đoán kết quả skip và limit khi Stream không có encounter order ổn định như thế nào?
Bạn phân biệt sorted và distinct là stateful intermediate operations với filter và map về memory cost ra sao?
Bạn sẽ thiết kế pipeline không cần intermediate collection dư thừa mà vẫn dễ debug như thế nào?
Bạn mô tả cách xử lý null trong map để bước sau không gây NullPointerException như thế nào?
Bạn sẽ đo chi phí allocation của pipeline nhiều flatMap thay vì giả định luôn nhanh hơn vòng lặp ra sao?
Bạn sẽ xác định cách exception từ map khiến terminal operation dừng sớm mà chưa xử lý các phần tử khác như thế nào?
Bạn sẽ sử dụng Stream.concat đúng mức khi kết hợp nguồn dữ liệu mà không tạo pipeline quá sâu ra sao?
Bạn giải thích Collectors.toList, toSet và toCollection khác nhau về loại container và bảo đảm API như thế nào?
Bạn sẽ dùng Collectors.toCollection khi cần chỉ định chính xác implementation của Collection kết quả ra sao?
Bạn phân biệt Collectors.toUnmodifiableList với toList về mutability và chính sách null như thế nào?
Bạn sẽ dùng Collectors.mapping để đổi giá trị trước khi downstream collector nhận phần tử như thế nào?
Bạn mô tả Collectors.groupingBy tạo map phân nhóm với classifier và downstream collector như thế nào?
Bạn sẽ kết hợp groupingBy và Collectors.counting để đếm bản ghi theo trạng thái ra sao?
Bạn phân biệt Collectors.partitioningBy và groupingBy khi phân loại chỉ có hai nhóm boolean như thế nào?
Bạn sẽ xác định vì sao Collectors.toMap cần merge function nếu có duplicate keys như thế nào?
Bạn sẽ thiết kế toMap merge function chọn phiên bản mới nhất mà vẫn xử lý null theo contract như thế nào?
Bạn phân tích rủi ro merge function luôn chọn phần tử đầu vào trước khi dữ liệu không có thứ tự ổn định ra sao?
Bạn sẽ dùng Collectors.filtering làm downstream collector để giữ một nhóm không có phần tử phù hợp như thế nào?
Bạn sẽ sử dụng Collectors.flatMapping khi mỗi đối tượng góp nhiều phần tử vào nhóm như thế nào?
Bạn phân biệt Collectors.summingInt với Collectors.averagingDouble theo dữ liệu và giới hạn số học ra sao?
Bạn sẽ dùng Collectors.summarizingInt để tổng hợp count, min, max, sum và average trong một lần duyệt như thế nào?
Bạn phân tích tại sao phép cộng floating-point có thể cho kết quả hơi khác khi thứ tự phần tử thay đổi ra sao?
Bạn sẽ dùng Collectors.joining kết hợp delimiter, prefix và suffix để xây chuỗi đầu ra ra sao?
Bạn mô tả Collectors.collectingAndThen tạo kết quả cuối sau khi downstream collector hoàn tất như thế nào?
Bạn sẽ dùng Collectors.reducing làm downstream collector khi các collector chuyên biệt không phù hợp như thế nào?
Bạn phân biệt groupingByConcurrent với groupingBy về concurrency, encounter order và kiểu map trả về ra sao?
Bạn sẽ chọn Collectors.toConcurrentMap khi dữ liệu có key được xử lý song song theo tiêu chí nào?
Bạn phân tích vì sao Collector.Characteristics.CONCURRENT không biến arbitrary mutable object thành thread-safe ra sao?
Bạn sẽ thiết kế custom Collector với supplier, accumulator, combiner và finisher như thế nào?
Bạn mô tả Collector.Characteristics.IDENTITY_FINISH ảnh hưởng nghĩa vụ của finisher ra sao?
Bạn phân biệt Collector.Characteristics.UNORDERED với CONCURRENT khi Stream thực thi song song như thế nào?
Bạn sẽ xác định khi nào accumulator có thể mutate result container riêng mà không vi phạm non-interference ra sao?
Bạn phân tích vì sao combiner phải gộp partial results đúng khi Stream được chia thành các partitions ra sao?
Bạn sẽ kiểm thử custom Collector cho nguồn rỗng, một phần tử và nhiều partitions theo invariants nào?
Bạn sẽ tránh chia sẻ một mutable ArrayList giữa các supplier calls của custom Collector như thế nào?
Bạn sẽ dùng mapFactory trong groupingBy khi cần LinkedHashMap giữ thứ tự khóa ra sao?
Bạn phân tích vì sao collector trả Map không tự bảo đảm thứ tự keys nếu không chỉ định implementation như thế nào?
Bạn sẽ dùng Collectors.teeing trên JDK hỗ trợ để tính hai số liệu từ một nguồn như thế nào?
Bạn sẽ trả record tổng hợp từ collector thay vì Map với key strings khi nào?
Bạn giải thích Stream.parallel tạo parallel stream xử lý phần tử bằng cơ chế nào?
Bạn phân biệt Collection.parallelStream với việc gọi parallel trên một Stream tuần tự ra sao?
Bạn mô tả ForkJoinPool.commonPool thường liên quan thế nào tới parallel stream và khả năng chia sẻ threads như thế nào?
Bạn sẽ đánh giá lợi ích parallel hóa dựa trên kích thước nguồn, chi phí xử lý từng phần tử và split cost ra sao?
Bạn phân tích vì sao blocking I/O trong parallelStream có thể gây nghẽn common pool như thế nào?
Bạn sẽ dùng Spliterator characteristics đánh giá nguồn có thể chia đều thành nhiều tasks ra sao?
Bạn phân biệt kết quả sequential và parallel khi operations không phụ thuộc encounter order như thế nào?
Bạn sẽ xác định vì sao shared mutable side effects trong map/filter khiến parallelStream không an toàn ra sao?
Bạn phân tích vai trò của stateless behavioral parameters và non-interference đối với Stream correctness ra sao?
Bạn sẽ xây reduce associative với identity hợp lệ để kết quả không phụ thuộc cách chia dữ liệu như thế nào?
Bạn phân biệt forEach và forEachOrdered khi parallel pipeline có yêu cầu thứ tự ra sao?
Bạn sẽ chọn findAny thay findFirst khi kết quả có thể là bất cứ phần tử nào theo chính sách nào?
Bạn phân tích chi phí ordered distinct và sorted trong parallel stream so với unordered source ra sao?
Bạn sẽ dùng unordered khi không cần encounter order nhưng vẫn giữ đúng kết quả ra sao?
Bạn mô tả cách skip/limit trên ordered parallel stream có thể cần phối hợp giữa các partitions như thế nào?
Bạn sẽ giải thích sai khác kết quả floating-point reduction do thứ tự cộng không hoàn toàn associative ra sao?
Bạn phân biệt thread-safe collector với an toàn của shared state ngoài stream đang được lambda cập nhật ra sao?
Bạn sẽ chọn groupingByConcurrent khi không cần thứ tự và collector có đặc tính phù hợp ra sao?
Bạn phân tích vì sao parallelStream để ghi database row-by-row không tự giới hạn số connections ra sao?
Bạn sẽ thiết kế bounded ExecutorService thay parallelStream nếu cần giới hạn concurrency tường minh như thế nào?
Bạn sẽ benchmark parallel và sequential bằng JMH có warm-up và tiêu thụ kết quả đúng ra sao?
Bạn phân tích vì sao một lần đo nhanh hơn trên máy developer chưa chứng minh production sẽ cải thiện ra sao?
Bạn sẽ nhận biết khi boxing, allocations và GC tiêu thụ hết lợi ích xử lý song song như thế nào?
Bạn sẽ kiểm thử parallel reduce nhiều lần để phát hiện accumulator không associative như thế nào?
Bạn phân biệt thread-safety của Function với khả năng nó được gọi đồng thời bởi nhiều worker threads ra sao?
Bạn sẽ thiết kế nguyên tắc không parallel hóa pipelines nhỏ hoặc xử lý phần tử rất rẻ như thế nào?
Bạn giải thích checked exception ảnh hưởng việc gán lambda cho Function và Consumer chuẩn của JDK như thế nào?
Bạn sẽ tạo adapter đổi IOException thành UncheckedIOException cho một pipeline đọc dữ liệu theo hợp đồng nào?
Bạn phân biệt dùng UncheckedIOException với việc bắt lỗi rồi âm thầm trả fallback như thế nào?
Bạn phân tích vì sao catch toàn bộ Exception rồi trả null trong Stream.map làm mất nguyên nhân thất bại ra sao?
Bạn sẽ dùng Result object hoặc sealed result type để giữ giá trị và thông tin lỗi theo từng phần tử như thế nào?
Bạn phân biệt fail-fast transformation với batch xử lý cần ghi nhận lỗi của tất cả bản ghi ra sao?
Bạn sẽ thiết kế ThrowingFunction để biểu diễn callback ném checked exception mà vẫn có type-safety như thế nào?
Bạn mô tả cách chuyển ThrowingFunction sang Function khi tích hợp với Stream API như thế nào?
Bạn phân tích vì sao exception ném trong một mapper khiến Stream pipeline dừng trước khi xử lý hết nguồn ra sao?
Bạn sẽ dùng try-with-resources để bảo đảm nguồn Files.lines được đóng cả khi pipeline ném exception như thế nào?
Bạn sẽ tránh ghi thông tin nhạy cảm trong log lỗi của lambda xử lý dữ liệu khách hàng như thế nào?
Bạn phân biệt Optional.empty là không có giá trị với lỗi thực thi một phép tính như thế nào?
Bạn sẽ chọn result type giàu thông tin thay Optional khi validation có nhiều nguyên nhân thất bại ra sao?
Bạn sẽ tách các biến đổi thuần túy khỏi hành vi cập nhật database hoặc phát thông báo theo cách nào?
Bạn phân tích nguy cơ sửa Collection đang duyệt bằng forEach dẫn tới ConcurrentModificationException như thế nào?
Bạn sẽ lựa chọn Collection.removeIf hay filter rồi collect khi cần loại bỏ phần tử theo nhu cầu mutability nào?
Bạn sẽ viết unit tests cho từng Function rồi kiểm thử integration của cả pipeline theo trường hợp nào?
Bạn sẽ dùng immutable test fixtures để ngăn shared state làm các tests phụ thuộc thứ tự ra sao?
Bạn phân tích vì sao test dựa trên thứ tự side effects của parallel stream có thể flaky như thế nào?
Bạn sẽ kiểm thử short-circuit anyMatch mà không giả định predicate chạy trên mọi phần tử ra sao?
Bạn sẽ chứng minh orElseGet chỉ gọi Supplier khi Optional vắng mặt bằng unit test nào?
Bạn sẽ thiết kế property-based tests cho một function composition giữ bất biến dữ liệu ra sao?
Bạn sẽ dùng JUnit parameterized tests để bao phủ null, empty, duplicates và boundary values của mapper như thế nào?
Bạn sẽ nhận biết API thêm ở JDK mới như mapMulti, toList và teeing khi cấu hình javac --release như thế nào?
Bạn sẽ kiểm tra benchmark không bị đo lệch do thiếu tiêu thụ kết quả của Stream pipeline như thế nào?
Bạn sẽ quyết định API công khai nhận Function hay interface theo domain khi phải mô tả error contract phức tạp ra sao?
Nếu lambda cố tăng local counter gây lỗi effectively final, bạn sẽ viết lại bằng reduction như thế nào?
Nếu hai overloads đều chấp nhận lambda, bạn sẽ dùng target typing để phân tích lỗi ambiguous call ra sao?
Nếu lambda capture mutable List rồi chạy parallelStream gây dữ liệu thiếu hoặc trùng, bạn sẽ loại bỏ side effects ra sao?
Nếu bound method reference tạo từ null receiver thất bại, bạn sẽ thay đổi điều kiện tạo callback như thế nào?
Nếu Optional.orElse gọi database ngay cả khi giá trị đã tồn tại, bạn sẽ dùng orElseGet và kiểm tra fallback như thế nào?
Nếu Optional.map trả null làm kết quả biến mất, bạn sẽ làm rõ mapping contract và error handling ra sao?
Nếu Stream.filter có logging nhưng không có terminal operation, bạn sẽ giải thích và sửa lazy pipeline như thế nào?
Nếu Stream đã được count rồi tiếp tục map gây exception, bạn sẽ tạo lại nguồn hoặc tái sử dụng dữ liệu như thế nào?
Nếu findAny chọn các phần tử khác nhau khi parallel, bạn sẽ đánh giá yêu cầu thứ tự và lựa chọn findFirst ra sao?
Nếu Stream.toList trả list không thể sửa nhưng code cũ tiếp tục add, bạn sẽ tạo mutable collection tường minh như thế nào?
Nếu Collectors.toMap lỗi duplicate key, bạn sẽ thiết kế merge function đúng nghiệp vụ như thế nào?
Nếu groupingBy cho kết quả mutable ngoài dự kiến, bạn sẽ thay downstream collector để kiểm soát mutability ra sao?
Nếu custom Collector chạy tuần tự đúng nhưng song song sai, bạn sẽ kiểm tra supplier, accumulator và combiner như thế nào?
Nếu reduce dùng phép trừ cho kết quả khác nhau ở parallel stream, bạn sẽ sửa tính kết hợp của phép tính ra sao?
Nếu peek được dùng để cập nhật cache nhưng không chạy đủ, bạn sẽ tách side effect khỏi Stream pipeline như thế nào?
Nếu mapper gọi network và parallelStream gây quá nhiều kết nối, bạn sẽ thay bằng bounded executor như thế nào?
Nếu Files.lines tạo file descriptor leak, bạn sẽ kiểm tra và sửa vòng đời Stream bằng try-with-resources như thế nào?
Nếu IOException không compile trong lambda Function, bạn sẽ chọn ThrowingFunction adapter hoặc result type ra sao?
Nếu lookup trả Optional.empty cả khi lỗi database, bạn sẽ thiết kế API phân biệt not-found với lỗi thực thi như thế nào?
Nếu chuyển một vòng lặp nhiều điều kiện thành Stream pipeline, bạn sẽ chọn Function, Predicate, Optional và Collectors thế nào để giữ đúng hành vi?
