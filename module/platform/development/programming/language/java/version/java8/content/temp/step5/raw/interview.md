Bạn phân tích những hạn chế của anonymous class trong việc truyền hành vi mà lambda expression của Java 8 giúp khắc phục ra sao?
Bạn phân biệt lambda expression với anonymous inner class về phạm vi biến, từ khóa this và khả năng định danh đối tượng ra sao?
Bạn thiết kế một phương thức nhận lambda để tách thuật toán lọc dữ liệu khỏi điều kiện nghiệp vụ cụ thể như thế nào?
Bạn giải thích vai trò của target typing khi compiler suy luận kiểu tham số và kiểu trả về của lambda như thế nào?
Bạn xác định vì sao lambda không có kiểu độc lập và phải tương thích với một functional interface trong ngữ cảnh sử dụng ra sao?
Bạn phân biệt dạng lambda biểu thức với dạng lambda block khi logic cần nhiều câu lệnh và trả về giá trị như thế nào?
Bạn mô tả các trường hợp có thể lược bỏ kiểu tham số hoặc dấu ngoặc trong cú pháp lambda mà vẫn hợp lệ như thế nào?
Bạn giải thích vì sao biến local được lambda capture phải final hoặc effectively final trong Java như thế nào?
Bạn phân tích rủi ro khi lambda capture một reference đến object mutable dù biến reference là effectively final ra sao?
Bạn thiết kế cách truyền giá trị bất biến vào callback để tránh race condition khi lambda được gọi bất đồng bộ như thế nào?
Bạn phân biệt captured variable với field của object khi một lambda có thể chạy sau khi phương thức tạo ra nó đã trả về ra sao?
Bạn giải thích cách this bên trong lambda tham chiếu đến instance bao quanh thay vì một instance lambda riêng như thế nào?
Bạn dựa trên tiêu chí nào để giữ lambda ngắn tại nơi sử dụng hoặc tách logic thành một phương thức có tên?
Bạn thiết kế một Runnable bằng lambda và giải thích cách xử lý exception phát sinh trong công việc được chạy ra sao?
Bạn phân biệt Runnable với Callable<T> khi biểu diễn tác vụ bằng lambda theo yêu cầu kết quả và checked exception như thế nào?
Bạn xác định nguyên nhân compiler từ chối lambda ném checked exception trong một functional interface không khai báo exception đó như thế nào?
Bạn thiết kế một adapter an toàn để gọi API có checked exception từ lambda mà vẫn giữ thông tin lỗi ra sao?
Bạn phân tích cách overload nhiều functional interface có chữ ký tương tự làm lời gọi lambda trở nên ambiguous như thế nào?
Bạn xử lý lỗi ambiguous method call khi một lambda khớp nhiều overload bằng cách điều chỉnh kiểu đích như thế nào?
Bạn giải thích vì sao kiểu trả về của biểu thức lambda ảnh hưởng đến quá trình compiler chọn overload ra sao?
Bạn đánh giá rủi ro đặt side effect trong lambda được thư viện gọi lại nhiều lần hoặc không gọi trong một số nhánh như thế nào?
Bạn kiểm thử một lambda có trạng thái bên ngoài để phát hiện hành vi phụ thuộc thứ tự thực thi như thế nào?
Bạn phân biệt runtime object đại diện lambda với giả định rằng mỗi lần đánh giá lambda đều tạo một anonymous class mới ra sao?
Bạn giải thích tại sao không nên dựa vào class name, identity hoặc chi tiết triển khai của đối tượng lambda trong hợp đồng API như thế nào?
Bạn xác định cách lambda thay đổi cấu trúc stack trace và lựa chọn log để truy vết lỗi khi debug ra sao?
Bạn thiết kế một API callback có hợp đồng rõ về thời điểm gọi, số lần gọi và thread thực thi để lambda phía client dùng an toàn như thế nào?
Bạn giải thích functional interface là gì và vai trò của single abstract method đối với việc dùng lambda như thế nào?
Bạn xác định cách compiler xử lý một interface chứa một abstract method cùng nhiều default hoặc static method khi kiểm tra tính functional ra sao?
Bạn giải thích vì sao các phương thức có chữ ký tương ứng với phương thức public của Object không nhất thiết làm mất tính functional của interface như thế nào?
Bạn sử dụng @FunctionalInterface để bảo vệ hợp đồng SAM khi bảo trì một interface được nhiều lambda tham chiếu ra sao?
Bạn thiết kế một functional interface nghiệp vụ có tên mô tả ý nghĩa thay vì lạm dụng Function cho mọi callback như thế nào?
Bạn phân biệt Predicate<T>, Function<T,R>, Consumer<T> và Supplier<T> theo dữ liệu vào và kết quả đầu ra như thế nào?
Bạn lựa chọn UnaryOperator<T> thay cho Function<T,T> khi đầu vào và đầu ra cùng kiểu theo ngữ nghĩa nào?
Bạn thiết kế phép biến đổi kết hợp hai giá trị bằng BinaryOperator<T> và xác định các yêu cầu của operation ra sao?
Bạn giải thích vai trò của BiFunction<T,U,R> khi kết quả phụ thuộc hai tham số có kiểu khác nhau như thế nào?
Bạn sử dụng Predicate.and, or và negate để tạo điều kiện lọc có thể đọc được mà không nhân đôi logic ra sao?
Bạn phân tích ảnh hưởng của thứ tự đánh giá và short-circuit khi kết hợp nhiều Predicate có thể tốn tài nguyên như thế nào?
Bạn phân biệt Function.compose với Function.andThen bằng cách theo dõi thứ tự biến đổi dữ liệu như thế nào?
Bạn thiết kế chuỗi xử lý qua các Function có kiểu đầu ra và đầu vào tương thích mà không cần ép kiểu thủ công như thế nào?
Bạn đánh giá trường hợp sử dụng Consumer.andThen phù hợp và rủi ro khi callback đầu tiên ném exception ra sao?
Bạn lựa chọn IntPredicate, IntFunction hoặc ToIntFunction để giảm chi phí boxing trong một pipeline xử lý nhiều số nguyên như thế nào?
Bạn phân biệt Supplier<T> với một factory có tham số khi cần trì hoãn tạo đối tượng hoặc tính toán giá trị ra sao?
Bạn thiết kế cách tiêm Clock, Supplier hoặc Function vào một service để kiểm thử logic không phụ thuộc trạng thái toàn cục như thế nào?
Bạn phân tích lợi ích và giới hạn của default method khi bổ sung hành vi vào một interface đã được thư viện phát hành như thế nào?
Bạn giải thích cách compiler giải quyết default method khi class và interface cung cấp các method có chữ ký trùng nhau như thế nào?
Bạn xử lý xung đột default method khi một class triển khai hai interface có cùng phương thức mặc định ra sao?
Bạn lựa chọn override hoặc gọi InterfaceName.super.method khi cần kết hợp hành vi mặc định từ nhiều interface như thế nào?
Bạn phân biệt static method trong interface với default method theo cách caller sử dụng và khả năng override ra sao?
Bạn đánh giá tính tương thích mã nguồn và hành vi khi bổ sung default method vào public API có nhiều implementation như thế nào?
Bạn xác định lúc nào nên đưa logic chung vào default method và lúc nào nên dùng helper hoặc service riêng như thế nào?
Bạn thiết kế test cho default method nhằm bảo đảm implementation cũ không bị thay đổi hành vi ngoài ý muốn ra sao?
Bạn đánh giá những trường hợp nên thay lambda bằng method reference để tăng tính rõ ràng của mã ra sao?
Bạn phân biệt tham chiếu static method với bound instance method reference khi truyền callback như thế nào?
Bạn mô tả cơ chế unbound instance method reference dạng Type::instanceMethod và cách đối tượng nhận lời gọi được truyền vào ra sao?
Bạn thiết kế một Stream map dùng method reference đến instance method mà vẫn suy luận đúng kiểu phần tử như thế nào?
Bạn phân biệt constructor reference với Supplier hoặc Function khi tạo đối tượng từ những chữ ký constructor khác nhau như thế nào?
Bạn sử dụng array constructor reference khi một generic collector yêu cầu tạo mảng kết quả như thế nào?
Bạn xác định cách overload resolution và target type quyết định một method reference trỏ đến overload nào ra sao?
Bạn phân tích vì sao một method reference có thể không tương thích với functional interface dù một lambda bọc thêm logic vẫn biên dịch được như thế nào?
Bạn lựa chọn lambda thay method reference khi cần kiểm tra null, bổ sung argument hoặc biến đổi trước lời gọi như thế nào?
Bạn giải thích rủi ro method reference đến instance mutable khi callback được thực thi bởi thread khác ra sao?
Bạn thiết kế một API nhận method reference mà vẫn xử lý checked exception theo hợp đồng của functional interface như thế nào?
Bạn kiểm thử việc refactor từ lambda gọi phương thức sang method reference để giữ nguyên thứ tự xử lý và side effect ra sao?
Bạn giải thích mục tiêu của Stream API và khác biệt với việc duyệt Collection bằng vòng lặp trực tiếp như thế nào?
Bạn phân biệt Stream là một pipeline thao tác với dữ liệu và Collection là cấu trúc lưu trữ theo những đặc điểm nào?
Bạn mô tả các thành phần nguồn dữ liệu, intermediate operations và terminal operation trong một Stream pipeline như thế nào?
Bạn giải thích ý nghĩa của tính lazy của intermediate operations và thời điểm các phần tử thật sự được xử lý ra sao?
Bạn phân tích tại sao một pipeline chỉ có filter và map nhưng thiếu terminal operation không thực hiện tính toán như mong đợi như thế nào?
Bạn kiểm chứng hành vi của filter và map qua logging mà không dựa vào giả định mọi phần tử chạy qua từng bước theo từng lượt toàn bộ danh sách ra sao?
Bạn phân biệt map với flatMap khi mỗi phần tử đầu vào có thể tương ứng với một hoặc nhiều phần tử đầu ra như thế nào?
Bạn thiết kế pipeline flatMap để biến một danh sách đơn hàng thành luồng các dòng sản phẩm mà không tạo danh sách lồng nhau như thế nào?
Bạn lựa chọn filter trước map hay map trước filter dựa trên khả năng thay đổi kiểu và chi phí tính toán ra sao?
Bạn phân biệt sorted với distinct và xác định điều kiện để phép loại bỏ phần tử trùng phản ánh đúng yêu cầu nghiệp vụ ra sao?
Bạn giải thích equals và hashCode ảnh hưởng đến tính đúng đắn của Stream.distinct trên custom class ra sao?
Bạn đánh giá chi phí bộ nhớ của distinct và sorted khi Stream nhận một tập dữ liệu rất lớn hoặc không bị chặn như thế nào?
Bạn phân biệt limit với skip khi thực hiện phân trang và xác định vấn đề nếu nguồn dữ liệu chưa có thứ tự ổn định ra sao?
Bạn phân tích vì sao limit trên một ordered parallel stream có thể có chi phí khác với limit trên luồng unordered ra sao?
Bạn thiết kế pipeline sử dụng peek để quan sát debug mà không phụ thuộc vào nó cho một side effect nghiệp vụ bắt buộc như thế nào?
Bạn giải thích vì sao Stream chỉ được tiêu thụ một lần và xử lý IllegalStateException khi tái sử dụng pipeline ra sao?
Bạn lựa chọn Supplier<Stream<T>> khi cần thực hiện nhiều terminal operation độc lập trên cùng nguồn dữ liệu như thế nào?
Bạn phân biệt Stream.of, Arrays.stream và Collection.stream theo nguồn đầu vào và kiểu phần tử như thế nào?
Bạn thiết kế pipeline xử lý số nguyên bằng IntStream để tránh boxing không cần thiết so với Stream<Integer> ra sao?
Bạn phân biệt mapToInt, boxed và mapToObj khi chuyển đổi giữa primitive stream và object stream như thế nào?
Bạn sử dụng IntStream.range và rangeClosed để sinh các chỉ số hoặc khoảng số mà không mắc lỗi biên như thế nào?
Bạn đánh giá khi nào Stream.generate hoặc Stream.iterate cần giới hạn phần tử để tránh pipeline không kết thúc như thế nào?
Bạn giải thích vì sao Stream API không tự động biến thao tác đọc file hoặc network thành xử lý bất đồng bộ như thế nào?
Bạn xử lý tài nguyên của Stream được tạo từ Files.lines bằng try-with-resources theo cách nào?
Bạn phân biệt findFirst với findAny về yêu cầu thứ tự và cơ hội tối ưu trên parallel stream ra sao?
Bạn thiết kế điều kiện xử lý bằng anyMatch, allMatch hoặc noneMatch khi chỉ cần kết quả boolean thay vì thu thập mọi phần tử như thế nào?
Bạn phân tích ý nghĩa của short-circuit trong anyMatch hoặc findFirst và ảnh hưởng đến side effect nằm trong pipeline như thế nào?
Bạn phân biệt count với việc collect toàn bộ phần tử rồi lấy kích thước theo yêu cầu bộ nhớ và tính chất nguồn ra sao?
Bạn giải thích cách Stream.min và max sử dụng Comparator, cùng cách thể hiện trường hợp luồng rỗng như thế nào?
Bạn thiết kế phép sắp xếp nhiều tiêu chí bằng Comparator.comparing, thenComparing và reversed mà không sai thứ tự ưu tiên ra sao?
Bạn phân biệt sorted trên Stream với việc sắp xếp List tại chỗ bằng List.sort theo side effect lên dữ liệu đầu vào như thế nào?
Bạn giải thích vai trò của reduce và điều kiện một phép kết hợp phù hợp để chạy tuần tự lẫn song song như thế nào?
Bạn phân tích yêu cầu associativity của accumulator trong reduce và hậu quả khi dùng phép trừ hoặc phép nối trạng thái mutable ra sao?
Bạn thiết kế một phép reduce có identity phù hợp cho tập dữ liệu rỗng và giải thích ảnh hưởng của identity lên kết quả như thế nào?
Bạn so sánh reduce với collect khi kết quả cần chứa collection mutable hoặc trạng thái gom nhóm như thế nào?
Bạn giải thích vai trò của supplier, accumulator và combiner trong phép collect ba tham số như thế nào?
Bạn phân tích vì sao dùng một ArrayList chia sẻ ngoài pipeline làm đích thêm phần tử từ parallel stream là không an toàn như thế nào?
Bạn sử dụng Collectors.toList để thu kết quả mà không giả định implementation hoặc mutability được API bảo đảm ra sao?
Bạn lựa chọn collector tạo collection cụ thể bằng toCollection khi caller yêu cầu ArrayList hoặc LinkedHashSet như thế nào?
Bạn thiết kế collector groupingBy để nhóm đơn hàng theo trạng thái và giải thích dạng dữ liệu kết quả như thế nào?
Bạn lựa chọn groupingBy hoặc partitioningBy khi cần phân nhóm theo khóa nghiệp vụ hoặc phân chia theo một điều kiện boolean như thế nào?
Bạn sử dụng mapping, filtering hoặc collectingAndThen trên JDK hiện đại khi cần kết hợp các bước thu thập theo nhóm ra sao?
Bạn thiết kế thao tác counting, summingInt hoặc averagingDouble để tổng hợp dữ liệu và xử lý tập trống như thế nào?
Bạn lựa chọn summarizingInt hoặc phương án gom thống kê khác để tránh duyệt lại dữ liệu nhiều lần ra sao?
Bạn giải thích cách Collectors.toMap xử lý duplicate key và thiết kế merge function theo hợp đồng dữ liệu như thế nào?
Bạn phân tích vì sao toMap có thể thất bại khi các phần tử đầu vào sinh ra cùng một khóa mà không có chiến lược gộp ra sao?
Bạn thiết kế collector toMap giữ thứ tự theo nguồn bằng map factory thích hợp và nêu các điều kiện cần kiểm chứng như thế nào?
Bạn phân biệt groupingBy với groupingByConcurrent về tính đồng thời và đặc tính thứ tự của kết quả như thế nào?
Bạn sử dụng Collectors.joining để tạo chuỗi kết quả có delimiter, prefix và suffix mà không tự quản lý dấu phân cách ra sao?
Bạn đánh giá vì sao việc thu gom dữ liệu vào bộ nhớ không phù hợp với pipeline đọc hàng triệu dòng nếu chỉ cần aggregate ngắn như thế nào?
Bạn giải thích ranh giới non-interference và statelessness của lambda trong Stream API để tránh kết quả không xác định ra sao?
Bạn phân tích vì sao thay đổi cấu trúc collection nguồn trong khi stream đang chạy có thể gây lỗi hoặc kết quả không đáng tin cậy như thế nào?
Bạn thiết kế pipeline không side effect để có thể chuyển từ sequential stream sang parallel stream an toàn hơn ra sao?
Bạn phân biệt encounter order của nguồn dữ liệu với thứ tự thực thi callback trong parallel stream như thế nào?
Bạn so sánh forEach với forEachOrdered khi thứ tự quan sát side effect là một yêu cầu của ứng dụng ra sao?
Bạn xác định khi nào gọi unordered có thể giúp giảm ràng buộc xử lý và khi nào nó làm thay đổi hợp đồng kết quả ra sao?
Bạn đánh giá chi phí chia nhỏ dữ liệu, gộp kết quả và điều phối tác vụ khi dùng parallel stream cho tập dữ liệu nhỏ như thế nào?
Bạn phân tích ảnh hưởng của blocking I/O trong parallel stream đến tài nguyên thread và độ trễ của những tác vụ khác ra sao?
Bạn lựa chọn một executor có kiểm soát thay parallel stream khi tác vụ cần giới hạn số lời gọi network đồng thời như thế nào?
Bạn giải thích vai trò của Spliterator khi nguồn stream cần được phân chia cho thực thi song song như thế nào?
Bạn đánh giá các đặc tính ORDERED, SIZED và DISTINCT của Spliterator ảnh hưởng đến tối ưu pipeline ra sao?
Bạn thiết kế benchmark so sánh vòng lặp, sequential stream và parallel stream có warm-up, kết quả tiêu thụ thực sự và dữ liệu đại diện như thế nào?
Bạn đánh giá những chi phí điều phối nào có thể khiến parallel stream chạy chậm hơn sequential stream với phép map đơn giản?
Bạn xác định cách kiểm thử kết quả pipeline khi nguồn có giá trị null hoặc operation có thể ném exception như thế nào?
Bạn phân biệt lỗi xảy ra tại bước intermediate operation với thời điểm lỗi xuất hiện khi terminal operation kích hoạt pipeline ra sao?
Bạn thiết kế cách tách một Stream pipeline quá dài thành các phương thức có tên để người bảo trì hiểu các quy tắc nghiệp vụ như thế nào?
Bạn giải thích mục tiêu của Optional trong Java 8 khi biểu diễn kết quả có thể không tồn tại mà không dùng null tùy tiện như thế nào?
Bạn phân biệt Optional.empty, Optional.of và Optional.ofNullable theo cách xử lý giá trị null ra sao?
Bạn thiết kế API tìm kiếm trả Optional<T> thay vì null và hướng dẫn caller xử lý cả trường hợp có hoặc không có kết quả như thế nào?
Bạn giải thích vì sao Optional.get không nên được gọi mà không có bảo đảm về sự hiện diện của giá trị như thế nào?
Bạn phân biệt isPresent với cách xử lý qua map, flatMap hoặc orElseGet để tránh kiểm tra rồi lấy giá trị thủ công ra sao?
Bạn dùng Optional.map để biến đổi giá trị nếu tồn tại mà vẫn giữ được trạng thái rỗng như thế nào?
Bạn phân biệt Optional.map với Optional.flatMap khi callback đã trả Optional và cần tránh Optional lồng nhau ra sao?
Bạn thiết kế chuỗi Optional để lấy một thuộc tính từ đối tượng lồng nhau mà không viết nhiều điều kiện null như thế nào?
Bạn phân tích sự khác nhau giữa orElse và orElseGet về thời điểm tính giá trị dự phòng cũng như side effect ra sao?
Bạn lựa chọn orElseThrow để chuyển Optional rỗng thành exception nghiệp vụ có thông báo rõ nghĩa như thế nào?
Bạn giải thích vì sao Optional không bảo đảm tự động kiểm tra hợp lệ nội dung của một object không null như thế nào?
Bạn giải thích vì sao dùng Optional.ofNullable có thể che giấu lỗi khi một API được cam kết không bao giờ trả về null như thế nào?
Bạn phân biệt dùng Optional làm kiểu trả về với việc sử dụng Optional làm field, parameter hoặc phần tử của collection theo mức rõ ràng API ra sao?
Bạn phân tích khó khăn khi serializer hoặc ORM xử lý Optional như một field của entity và thiết kế dữ liệu thay thế như thế nào?
Bạn thiết kế cách chuyển Stream.findFirst thành Optional rồi cung cấp giá trị dự phòng mà không duyệt lại dữ liệu ra sao?
Bạn lựa chọn OptionalInt, OptionalLong hoặc OptionalDouble khi kết quả primitive có thể vắng mặt và muốn tránh boxing như thế nào?
Bạn xác định cách phân biệt kết quả bằng 0 với không có kết quả khi dùng OptionalInt trong phép tính thống kê ra sao?
Bạn so sánh Optional với một kiểu Result chứa lỗi nghiệp vụ khi cần cung cấp cả nguyên nhân thất bại như thế nào?
Bạn kiểm thử API trả Optional với đầu vào rỗng, dữ liệu hợp lệ và dữ liệu có thể null trong các tầng trung gian ra sao?
Bạn giải thích mục tiêu thiết kế java.time trong Java 8 để thay thế những bất tiện của Date và Calendar khi biểu diễn thời gian như thế nào?
Bạn phân biệt LocalDate, LocalTime và LocalDateTime theo việc chứa thông tin ngày, giờ hoặc cả hai nhưng không có múi giờ ra sao?
Bạn giải thích vì sao LocalDateTime không xác định duy nhất một Instant trên dòng thời gian toàn cầu như thế nào?
Bạn lựa chọn Instant để lưu thời điểm xảy ra sự kiện trong hệ thống phân tán thay cho ngày giờ địa phương theo những tiêu chí nào?
Bạn phân biệt OffsetDateTime với ZonedDateTime theo thông tin offset cố định và quy tắc múi giờ vùng như thế nào?
Bạn thiết kế dữ liệu đặt lịch theo múi giờ địa phương của người dùng và xác định thông tin cần lưu để áp dụng quy tắc DST đúng như thế nào?
Bạn sử dụng ZoneId và ZoneOffset để diễn đạt múi giờ vùng với độ lệch UTC hiện thời khác nhau ra sao?
Bạn giải thích tại sao cùng một ZoneId có thể có offset khác nhau ở hai thời điểm trong năm như thế nào?
Bạn phân tích tình huống LocalDateTime nằm trong khoảng giờ không tồn tại do chuyển sang daylight saving time và cách xử lý nghiệp vụ ra sao?
Bạn thiết kế cách giải quyết một giờ địa phương bị lặp lại trong DST overlap khi tạo thời điểm tuyệt đối như thế nào?
Bạn phân biệt atZone với thao tác đổi múi giờ giữ nguyên Instant khi hiển thị sự kiện ở một địa phương khác như thế nào?
Bạn lựa chọn withZoneSameInstant hoặc withZoneSameLocal trên ZonedDateTime theo ý nghĩa nghiệp vụ cần bảo toàn như thế nào?
Bạn phân tích vì sao cộng một ngày trên ZonedDateTime có thể khác cộng đúng 24 giờ khi vượt qua thời điểm đổi DST ra sao?
Bạn phân biệt Period với Duration khi tính khoảng cách theo lịch và khoảng thời gian theo giây hoặc nano giây như thế nào?
Bạn thiết kế phép tính tuổi từ LocalDate bằng Period và xử lý ngày sinh vào năm nhuận ra sao?
Bạn sử dụng Duration.between để đo khoảng thời gian giữa hai Instant mà không phụ thuộc múi giờ hiển thị như thế nào?
Bạn phân biệt ChronoUnit.DAYS.between với Duration.toDays khi dữ liệu là ngày theo lịch so với thời điểm cụ thể như thế nào?
Bạn giải thích tại sao cộng một tháng bằng plusMonths cần quy tắc với ngày cuối tháng mà không phải số ngày cố định ra sao?
Bạn lựa chọn TemporalAdjusters khi tìm ngày làm việc hoặc ngày cuối tháng mà không tự tính chỉ số ngày như thế nào?
Bạn phân biệt DateTimeFormatter dạng bất biến với SimpleDateFormat mutable khi chia sẻ formatter giữa nhiều thread như thế nào?
Bạn thiết kế DateTimeFormatter có Locale và pattern rõ ràng để parse ngày người dùng nhập mà không phụ thuộc cấu hình máy ra sao?
Bạn giải thích vì sao yyyy và YYYY có thể cho năm khác nhau ở ranh giới năm theo quy ước lịch như thế nào?
Bạn lựa chọn ResolverStyle nghiêm ngặt khi parse ngày tháng nhằm từ chối dữ liệu không hợp lệ thay vì tự điều chỉnh âm thầm ra sao?
Bạn phân tích sự khác nhau giữa định dạng ISO-8601 có offset và định dạng ngày giờ địa phương không ghi timezone như thế nào?
Bạn thiết kế chuyển đổi giữa Instant và kiểu thời gian cũ như java.util.Date ở ranh giới tích hợp mà không làm mất ý nghĩa thời điểm ra sao?
Bạn xác định cách biểu diễn UTC nhất quán trong database và chuyển đổi cho UI theo ZoneId của người xem như thế nào?
Bạn giải thích tại sao không nên lưu một timestamp chỉ bằng chuỗi ngày giờ không offset khi nhiều service chạy ở những múi giờ khác nhau ra sao?
Bạn lựa chọn Clock.fixed để kiểm thử timeout và deadline mà không phụ thuộc thời gian thực của máy như thế nào?
Bạn thiết kế service nhận Clock qua constructor rồi dùng Instant.now(clock) để kiểm thử thời điểm hết hạn như thế nào?
Bạn dùng Clock.offset hoặc Clock.tick trong phép thử hay mô phỏng và nhận diện giới hạn độ phân giải của từng nguồn như thế nào?
Bạn phân tích ảnh hưởng của cấu hình time zone mặc định lên LocalDate.now khi test chạy ở CI và máy phát triển khác nhau ra sao?
Bạn thiết kế tập kiểm thử cho khoảng thời gian qua ngày cuối tháng, năm nhuận và thời điểm đổi DST như thế nào?
Bạn giải thích vì sao Instant và LocalDate có hợp đồng so sánh khác nhau khi một service cần xếp thứ tự sự kiện ra sao?
Bạn thiết kế phép so sánh ZonedDateTime theo Instant hoặc thứ tự ngày giờ địa phương tùy theo ý nghĩa nghiệp vụ như thế nào?
Bạn đánh giá giới hạn của việc sử dụng System.currentTimeMillis để tính elapsed time so với System.nanoTime trong đo thời lượng như thế nào?
Bạn lựa chọn ZoneRules khi cần kiểm tra offset hợp lệ của một LocalDateTime trước khi lên lịch theo vùng như thế nào?
Bạn thiết kế kế hoạch cập nhật dữ liệu timezone của runtime để không áp dụng quy tắc DST đã cũ cho lịch tương lai như thế nào?
Bạn phân tích vì sao hai hệ thống sử dụng bản dữ liệu múi giờ khác nhau có thể tính ra Instant khác nhau từ cùng lịch địa phương ra sao?
Bạn giải thích CompletableFuture bổ sung mô hình kết hợp tác vụ bất đồng bộ cho các API Future truyền thống của Java như thế nào?
Bạn thiết kế chuỗi CompletableFuture dùng thenApply và thenCompose để tránh lồng nhiều future khi các bước phụ thuộc kết quả nhau ra sao?
Bạn phân biệt thenApply với thenApplyAsync và cách lựa chọn executor khi kiểm soát thread chạy continuation ra sao?
Bạn sử dụng thenCombine để ghép kết quả của hai công việc độc lập và quản lý lỗi của từng nhánh như thế nào?
Bạn phân biệt thenAccept, thenRun và whenComplete theo việc có nhận kết quả, side effect hoặc quan sát lỗi ra sao?
Bạn thiết kế xử lý ngoại lệ bằng exceptionally và handle sao cho phân biệt lỗi với giá trị hợp lệ ra sao?
Bạn xác định rủi ro khi gọi join hoặc get trên CompletableFuture trong thread xử lý request có giới hạn tài nguyên như thế nào?
Bạn đánh giá điều kiện cần giới hạn concurrency và đặt timeout trong pipeline CompletableFuture khi backend có độ trễ thất thường ra sao?
Bạn thiết kế cơ chế propagation của correlation ID qua các stage bất đồng bộ mà không giả định ThreadLocal tự theo task như thế nào?
Bạn kiểm thử một chuỗi CompletableFuture với nhánh thành công, thất bại và cancellation mà không phụ thuộc Thread.sleep như thế nào?
Bạn phân biệt Base64 encoder hoặc decoder của java.util.Base64 với phép mã hóa bảo mật hoặc hash nội dung ra sao?
Bạn lựa chọn Base64 URL-safe encoding cho dữ liệu trong URL và kiểm tra padding theo hợp đồng protocol như thế nào?
Bạn phân tích vì sao chuyển Base64 sang văn bản cần dùng charset rõ ràng nếu dữ liệu gốc biểu diễn một String như thế nào?
Bạn đánh giá rủi ro khi dùng parallel stream hoặc CompletableFuture để tối ưu một tác vụ nhỏ nhưng tạo thêm overhead điều phối như thế nào?
Một lambda không compile vì biến local được sửa sau khi capture, bạn sẽ xác định nguyên nhân và thiết kế lại luồng dữ liệu như thế nào?
Một Stream pipeline thay đổi collection nguồn từ bên trong forEach rồi ném lỗi, bạn sẽ loại bỏ side effect và thiết kế phép biến đổi như thế nào?
Một parallel stream cho kết quả tổng sai khi dùng accumulator mutable dùng chung, bạn sẽ phân tích associativity và collector phù hợp ra sao?
Một đoạn code dùng Optional.orElse gọi truy vấn dự phòng dù Optional đã có giá trị, bạn sẽ chẩn đoán và thay cách xử lý như thế nào?
Một service dùng LocalDateTime để trao đổi thời điểm tuyệt đối giữa hai quốc gia và tạo sai lệch dữ liệu, bạn sẽ thiết kế lại hợp đồng thời gian ra sao?
Một tác vụ đặt lịch bị kích hoạt hai lần khi DST overlap, bạn sẽ xác định offset và quy tắc xử lý lịch theo nghiệp vụ như thế nào?
Một pipeline CompletableFuture treo khi số tác vụ blocking tăng nhanh, bạn sẽ kiểm tra executor, timeout và cách áp giới hạn như thế nào?
Bạn xây dựng checklist review Java 8 còn phù hợp hiện nay dựa trên type safety, side effect, stream laziness, Optional, java.time và concurrency như thế nào?
