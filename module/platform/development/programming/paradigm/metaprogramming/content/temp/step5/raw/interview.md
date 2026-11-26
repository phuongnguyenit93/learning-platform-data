Bạn giải thích siêu lập trình là gì và phân biệt chương trình xử lý dữ liệu với chương trình phân tích hoặc tạo ra mã như thế nào?
Bạn phân biệt metaprogramming tại compile time với runtime metaprogramming về thời điểm có thông tin và chi phí thực thi ra sao?
Bạn lựa chọn code generation, reflection hoặc cấu hình khai báo khi cần loại bỏ đoạn mã lặp theo những tiêu chí nào?
Bạn phân tích sự khác nhau giữa một chương trình tự mô tả qua metadata và một chương trình tự sửa mã của nó như thế nào?
Bạn giải thích vai trò của cú pháp, ngữ nghĩa và hệ thống kiểu trong việc biến đổi chương trình mà không làm sai hành vi ra sao?
Bạn phân biệt thao tác trên chuỗi source code với thao tác trên AST khi cần đổi tên hoặc tái cấu trúc mã như thế nào?
Bạn đánh giá tác động của metaprogramming đến khả năng đọc hiểu, debug và onboarding của một nhóm phát triển ra sao?
Bạn xác định những trường hợp code generation làm API dễ dùng hơn và những trường hợp khiến chi phí bảo trì tăng như thế nào?
Bạn thiết kế ranh giới giữa mã do người viết và mã được sinh tự động để tránh chỉnh sửa nhầm vào output như thế nào?
Bạn phân biệt template-based generation với syntax-aware transformation về khả năng bảo toàn cấu trúc chương trình ra sao?
Bạn giải thích khái niệm staging khi một phép tính được thực hiện ở giai đoạn tạo mã thay vì runtime như thế nào?
Bạn phân tích các nguồn thông tin chỉ có tại compile time và thông tin chỉ xuất hiện khi ứng dụng đang chạy như thế nào?
Bạn lựa chọn static analysis hay runtime instrumentation khi cần kiểm tra quy tắc sử dụng API trong một codebase như thế nào?
Bạn thiết kế một quy trình tạo mã bảo đảm cùng input và cấu hình luôn sinh ra output có thể tái lập ra sao?
Bạn đánh giá rủi ro đưa timestamp hoặc đường dẫn máy phát triển vào source code được sinh trong quá trình build như thế nào?
Bạn phân biệt introspection với intercession khi hệ thống chỉ đọc metadata hoặc chủ động thay đổi cách thực thi ra sao?
Bạn giải thích vai trò của reflection trong introspection mà không mặc định nó có thể truy cập mọi thành viên của một class như thế nào?
Bạn phân tích giới hạn của việc suy ra ý nghĩa nghiệp vụ từ tên class, tên method hoặc annotation khi xây công cụ tự động như thế nào?
Bạn lựa chọn cách mô tả quy tắc sinh mã bằng schema, annotation hay DSL theo nhu cầu mở rộng và kiểm thử ra sao?
Bạn thiết kế bước xác thực input cho trình sinh mã khi schema hoặc template đến từ nguồn không tin cậy như thế nào?
Bạn giải thích macro ở mức khái niệm và điểm khác nhau giữa mở rộng macro với gọi hàm thông thường ra sao?
Bạn phân biệt textual macro expansion với AST-based macro expansion về rủi ro phá vỡ cú pháp như thế nào?
Bạn giải thích vấn đề variable capture trong một macro không có cơ chế vệ sinh tên và xây dựng ví dụ để phát hiện ra sao?
Bạn phân tích mục tiêu của hygienic macro và giới hạn của việc chỉ ghép chuỗi định danh để tránh trùng tên như thế nào?
Bạn đánh giá khi nào một macro expansion có thể vô tình đánh giá đối số nhiều lần và làm thay đổi side effect ra sao?
Bạn phân biệt quotation và unquotation trong các hệ thống macro dựa trên cấu trúc cú pháp theo cách nào?
Bạn thiết kế một phép mở rộng macro biểu diễn điều kiện kiểm tra nhưng vẫn bảo toàn thứ tự đánh giá của biểu thức đầu vào ra sao?
Bạn phân biệt khả năng metaprogramming hiện có trong Java với hệ thống hygienic macro tổng quát của các ngôn ngữ chuyên biệt như thế nào?
Bạn lựa chọn annotation processing hoặc code generation thay cho việc giả định có thể khai báo macro trực tiếp trong cú pháp Java ra sao?
Bạn phân biệt compile-time constant với đoạn mã được đánh giá bởi công cụ build trong một hệ thống siêu lập trình như thế nào?
Bạn thiết kế cách hiển thị source code sau macro expansion hoặc code generation để hỗ trợ việc review và chẩn đoán ra sao?
Bạn phân tích ảnh hưởng của macro expansion đến thông báo lỗi compiler khi lỗi nằm trong mã đã được tạo ra như thế nào?
Bạn lựa chọn giải pháp metaprogramming có nguồn gốc rõ ràng cho mỗi đoạn mã sinh ra để tăng khả năng truy vết ra sao?
Bạn giải thích AST biểu diễn chương trình thành những node nào và quan hệ giữa node cha với các biểu thức con ra sao?
Bạn phân biệt AST với parse tree về mức chi tiết cú pháp và mục tiêu sử dụng của công cụ phân tích mã như thế nào?
Bạn thiết kế một phép duyệt AST để tìm các lời gọi method theo tên và vị trí mà không dùng tìm kiếm chuỗi đơn giản ra sao?
Bạn phân biệt visitor pattern với phép duyệt đệ quy thủ công khi xây công cụ thao tác AST như thế nào?
Bạn giải thích ý nghĩa của source position và symbol resolution khi một công cụ cần báo lỗi đúng dòng mã như thế nào?
Bạn phân tích vì sao hai định danh có cùng tên trong AST chưa chắc tham chiếu đến cùng một symbol như thế nào?
Bạn thiết kế phép đổi tên biến trên AST mà không gây xung đột với biến cùng tên ở scope khác như thế nào?
Bạn phân biệt AST thô sau parse với cây đã được gắn kiểu hoặc symbol sau bước semantic analysis ra sao?
Bạn xác định những điều kiện phải kiểm tra trước khi biến đổi thứ tự hai biểu thức có thể gây side effect như thế nào?
Bạn thiết kế static analyzer phát hiện phép gọi API không được phép tại những vị trí cụ thể của source code ra sao?
Bạn đánh giá giới hạn của phân tích AST khi một lời gọi thực tế được quyết định bằng dynamic dispatch hoặc reflection như thế nào?
Bạn phân biệt công cụ đọc AST qua API được hỗ trợ với việc sửa cây nội bộ của javac bằng API không ổn định như thế nào?
Bạn lựa chọn javac Tree API cho phân tích source hay Class-File API cho phân tích bytecode dựa trên loại thông tin cần thu thập ra sao?
Bạn thiết kế phép kiểm thử cho một AST transformation bằng cách so sánh hành vi trước và sau biến đổi như thế nào?
Bạn phân tích rủi ro mất comment, formatting hoặc source mapping khi công cụ xây lại mã nguồn từ AST ra sao?
Bạn giải thích annotation trong Java đóng vai trò metadata và phân biệt nó với hành vi tự động được thực thi bởi framework như thế nào?
Bạn phân biệt annotation declaration với annotation instance xuất hiện trên một class, method hoặc field như thế nào?
Bạn xác định tác động của @Target khi một annotation chỉ được phép đặt trên những loại phần tử cụ thể ra sao?
Bạn phân biệt retention SOURCE, CLASS và RUNTIME theo khả năng hiện diện của metadata ở các giai đoạn xử lý như thế nào?
Bạn thiết kế annotation có các element bắt buộc, element mặc định và những kiểu giá trị hợp lệ như thế nào?
Bạn giải thích lý do annotation element không thể nhận một object mutable tùy ý làm giá trị như thế nào?
Bạn phân biệt type-use annotation với annotation trên declaration và ý nghĩa của chúng khi kiểm tra kiểu ra sao?
Bạn thiết kế một công cụ nhận diện annotation trên type argument mà không chỉ duyệt annotation của field như thế nào?
Bạn giải thích ảnh hưởng của @Repeatable đến cách biểu diễn và đọc nhiều annotation cùng loại trên một declaration ra sao?
Bạn phân tích phạm vi của @Inherited khi annotation trên superclass được đọc từ subclass theo quy tắc Java như thế nào?
Bạn thiết kế một runtime validator đọc annotation nhưng vẫn kiểm tra dữ liệu thực tế thay vì tin rằng metadata tự thực thi validation ra sao?
Bạn xác định cách xử lý annotation không có retention RUNTIME khi reflection không trả về nó như thế nào?
Bạn phân biệt việc tìm annotation trực tiếp với tra cứu metadata trong class hierarchy khi xây framework ra sao?
Bạn thiết kế chiến lược tương thích khi thay đổi annotation element của một thư viện được nhiều dự án sử dụng như thế nào?
Bạn đánh giá rủi ro gắn quá nhiều chính sách nghiệp vụ vào annotation khiến hành vi chương trình khó phát hiện từ mã nguồn như thế nào?
Bạn giải thích mục tiêu của annotation processing trong javac và phân biệt nó với runtime reflection như thế nào?
Bạn mô tả vai trò của javax.annotation.processing.Processor trong việc nhận metadata và tham gia các vòng xử lý lúc compile như thế nào?
Bạn thiết kế một AbstractProcessor nhận diện annotation nghiệp vụ rồi sinh lớp hỗ trợ tương ứng ra sao?
Bạn phân biệt Element, TypeMirror và AnnotationMirror trong mô hình ngôn ngữ dành cho annotation processor như thế nào?
Bạn giải thích vì sao processor cần dùng TypeElement và TypeMirror thay vì luôn cố nạp class bằng Class.forName như thế nào?
Bạn xác định cách truy cập method, parameter và type information qua javax.lang.model mà không phụ thuộc reflection runtime ra sao?
Bạn sử dụng Elements và Types để kiểm tra quan hệ kiểu và tìm declaration được compiler nhận diện như thế nào?
Bạn thiết kế phép kiểm tra annotation chỉ hợp lệ trên method có chữ ký phù hợp và báo lỗi tại đúng element ra sao?
Bạn phân biệt cách sử dụng Messager để báo ERROR, WARNING và NOTE theo tác động của từng mức tới build ra sao?
Bạn xây dựng thông báo lỗi processor có tên symbol và vị trí để người dùng sửa annotation sai dễ dàng như thế nào?
Bạn mô tả vai trò của Filer trong việc sinh Java source file hoặc resource từ một annotation processor ra sao?
Bạn phân tích vì sao processor không nên ghi đè tùy ý lên source file đã tồn tại trong quá trình build như thế nào?
Bạn thiết kế quy tắc đặt tên file sinh ra để hai processor hoặc hai element không tạo cùng một tên như thế nào?
Bạn giải thích các vòng annotation processing và cách source file được sinh có thể được xử lý ở vòng tiếp theo như thế nào?
Bạn xác định ý nghĩa của RoundEnvironment.processingOver đối với việc hoàn tất xử lý và xuất báo cáo như thế nào?
Bạn phân tích rủi ro sinh thêm source file không đúng vòng hoặc cứ sinh lại file khiến build lỗi như thế nào?
Bạn thiết kế processor xử lý collection element theo thứ tự ổn định để output có thể tái lập giữa các lần build ra sao?
Bạn phân biệt supported annotation types với supported source version khi khai báo năng lực của processor như thế nào?
Bạn đánh giá tác động của thay đổi JDK đến source version của annotation processor và cách lựa chọn mức tương thích ra sao?
Bạn phân biệt annotation processor discovery qua service registration với cấu hình processor path tường minh của build tool ra sao?
Bạn giải thích lý do nên tách dependency processor khỏi runtime dependency của ứng dụng khi có thể như thế nào?
Bạn thiết kế kiểm thử biên dịch cho annotation processor bao gồm source hợp lệ, source lỗi và nội dung file được sinh ra sao?
Bạn phân tích khả năng incremental compilation bị ảnh hưởng khi processor đọc thông tin không được khai báo hoặc sinh nhiều output phụ thuộc nhau như thế nào?
Bạn lựa chọn kiến trúc processor tạo mã độc lập theo từng element hay tạo một registry tổng hợp theo các ràng buộc nào?
Bạn phân biệt annotation processing được hỗ trợ chính thức với việc can thiệp AST nội bộ javac có thể vỡ khi nâng JDK như thế nào?
Bạn đánh giá khi nào nên dùng annotation processor để sinh mapper thay vì reflection tạo mapper tại runtime ra sao?
Bạn giải thích vai trò của reflection API trong việc khám phá class, constructor, method và field tại runtime như thế nào?
Bạn phân biệt Class.getMethods với Class.getDeclaredMethods khi xây công cụ liệt kê API thực tế của một kiểu dữ liệu ra sao?
Bạn lựa chọn Class.getField hoặc Class.getDeclaredField theo mục tiêu tra cứu thành viên được kế thừa hay khai báo trực tiếp như thế nào?
Bạn giải thích vì sao Modifier và metadata của Method chưa đủ để chứng minh một lời gọi dynamic có hợp đồng nghiệp vụ hợp lệ như thế nào?
Bạn phân biệt kiểu tham số thực tế của Method với thông tin generic signature có thể được phản ánh qua reflection ra sao?
Bạn thiết kế một bộ kiểm tra generic return type có xét tới ParameterizedType và giới hạn của type erasure như thế nào?
Bạn phân tích vì sao reflection không thể tự suy ra kiểu phần tử thực tế của mọi collection generic sau type erasure ra sao?
Bạn xác định thời điểm Class.forName có thể dẫn đến khởi tạo class và cách tránh side effect khi chỉ cần đọc metadata như thế nào?
Bạn phân biệt tra cứu constructor qua reflection với gọi new trực tiếp về kiểm tra kiểu và lỗi runtime như thế nào?
Bạn thiết kế một plugin loader nhận class theo cấu hình nhưng xác minh interface bắt buộc trước khi khởi tạo ra sao?
Bạn phân tích cách Method.invoke biểu diễn exception do method đích ném và cách giữ nguyên nguyên nhân gốc khi báo lỗi như thế nào?
Bạn đánh giá rủi ro truyền sai kiểu đối số hoặc số lượng đối số khi gọi method qua reflection và cách kiểm chứng trước khi gọi ra sao?
Bạn phân biệt quyền truy cập Java theo source code với các kiểm tra access được reflection áp dụng tại runtime như thế nào?
Bạn giải thích ảnh hưởng của strong encapsulation trong JPMS lên setAccessible và deep reflection như thế nào?
Bạn xác định cách chẩn đoán InaccessibleObjectException khi framework cố đọc private field thuộc package chưa được mở ra sao?
Bạn phân biệt exports với opens trong module descriptor khi một thành phần cần gọi public API hoặc dùng reflection trên non-public members như thế nào?
Bạn thiết kế cấu hình module opens có phạm vi phù hợp thay vì mở mọi package chỉ để giải quyết một lỗi reflection như thế nào?
Bạn đánh giá khi nào cập nhật framework để dùng API được hỗ trợ là giải pháp bền vững hơn thêm --add-opens như thế nào?
Bạn giải thích giới hạn của việc dùng reflection để tự động inject dependency khi các quan hệ khởi tạo có chu trình như thế nào?
Bạn thiết kế bộ nhớ đệm cho metadata Method hoặc Constructor mà không giữ class loader không còn sử dụng trong bộ nhớ ra sao?
Bạn phân tích rủi ro một object graph được dựng bằng reflection nhưng bỏ qua constructor validation hoặc invariant nghiệp vụ như thế nào?
Bạn lựa chọn MethodHandle thay Method.invoke khi cần liên kết lời gọi động có nhiều lần thực thi theo những tiêu chí nào?
Bạn giải thích vai trò của MethodHandles.Lookup và lookup modes trong việc giới hạn quyền truy cập method động như thế nào?
Bạn phân biệt MethodType với Method phản ánh trong reflection khi biểu diễn chữ ký lời gọi động ra sao?
Bạn giải thích sự khác nhau giữa MethodHandle.invokeExact và invoke trong kiểm tra kiểu lời gọi như thế nào?
Bạn thiết kế bộ adapter dùng MethodHandle.asType để chuyển chữ ký lời gọi trong phạm vi chuyển đổi hợp lệ ra sao?
Bạn phân tích rủi ro truyền MethodHandle qua một API mà caller có thể sử dụng quyền truy cập đã được cấp từ nơi khác ra sao?
Bạn phân biệt privateLookupIn với việc bỏ qua hệ thống module access khi muốn liên kết private method như thế nào?
Bạn đánh giá lợi ích của MethodHandle combinators khi cần ghép lời gọi động thay vì dựng mã Java dạng chuỗi như thế nào?
Bạn giải thích mục đích của VarHandle khi cần truy cập field hoặc phần tử mảng với các chế độ memory ordering khác nhau như thế nào?
Bạn phân biệt VarHandle.getVolatile và các chế độ getAcquire hoặc getOpaque theo yêu cầu visibility như thế nào?
Bạn thiết kế thao tác compareAndSet qua VarHandle để cập nhật field đồng thời mà không dùng reflection thông thường như thế nào?
Bạn phân tích rủi ro chọn memory ordering quá yếu cho một giao thức publication giữa nhiều thread như thế nào?
Bạn giải thích vai trò của invokedynamic trong việc liên kết lời gọi động được compiler hoặc runtime sử dụng như thế nào?
Bạn phân biệt bootstrap method của invokedynamic với constructor hoặc static initializer của class như thế nào?
Bạn đánh giá chi phí và rủi ro khi xây một runtime code generator thay vì sử dụng MethodHandles trên đối tượng đã có sẵn ra sao?
Bạn mô tả cách java.lang.reflect.Proxy và InvocationHandler phối hợp tạo đối tượng đại diện cho các interface tại runtime như thế nào?
Bạn thiết kế một InvocationHandler ghi nhận thời gian gọi method mà vẫn chuyển tiếp đúng tham số và kết quả ra sao?
Bạn phân biệt proxy dựa trên java.lang.reflect.Proxy với class-based proxy sử dụng cơ chế tạo subclass ra sao?
Bạn xác định giới hạn của JDK dynamic proxy khi service không triển khai interface cần được đại diện như thế nào?
Bạn phân tích vì sao class final hoặc sealed hierarchy có thể ngăn cơ chế proxy tạo subclass nhưng không mặc định ngăn proxy interface như thế nào?
Bạn thiết kế một proxy kiểm tra quyền truy cập trước khi gọi service thực và tránh ghi lộ thông tin nhạy cảm ra log như thế nào?
Bạn giải thích cách InvocationHandler nhận Method và mảng arguments khi method của interface được gọi như thế nào?
Bạn phân biệt việc xử lý equals, hashCode và toString trên proxy với việc chuyển tiếp các method nghiệp vụ ra sao?
Bạn xác định cách xử lý Object methods để proxy không vi phạm hợp đồng equals hoặc làm rò rỉ đối tượng đích như thế nào?
Bạn thiết kế xử lý checked exception phát sinh từ InvocationHandler phù hợp với throws clause của interface như thế nào?
Bạn phân tích cơ chế Method.invoke bọc exception từ method đích và cách InvocationHandler chuyển tiếp nguyên nhân gốc ra sao?
Bạn phân biệt proxy handler điều phối lời gọi mặc định trên interface với gọi một method thông thường của target như thế nào?
Bạn xác định cách sử dụng API được hỗ trợ để gọi default method của interface trên proxy trong JDK hiện đại ra sao?
Bạn phân tích nguy cơ recursion vô hạn khi InvocationHandler lại gọi chính method trên object proxy như thế nào?
Bạn thiết kế cách lấy danh sách interface và chọn class loader phù hợp khi tạo proxy cho một plugin đã được nạp động ra sao?
Bạn giải thích tác động của module visibility và khả năng truy cập interface đến việc tạo JDK dynamic proxy như thế nào?
Bạn phân biệt proxy intercept lời gọi qua interface với lời gọi nội bộ trên đối tượng target không đi qua proxy ra sao?
Bạn thiết kế test xác minh proxy chỉ áp dụng validation một lần cho mỗi lần đi qua boundary mong muốn như thế nào?
Bạn phân tích rủi ro một proxy chain nhiều lớp làm sai thứ tự authorization, caching và logging như thế nào?
Bạn lựa chọn decorator viết tay hoặc dynamic proxy cho cơ chế chặn lời gọi đơn giản theo khả năng debug và hiệu năng ra sao?
Bạn đánh giá nguy cơ giữ target hoặc class loader trong InvocationHandler khiến plugin không được unload như mong đợi như thế nào?
Bạn phân biệt API proxy chạy lúc runtime với annotation processor sinh wrapper ở compile time theo thời điểm phát hiện lỗi như thế nào?
Bạn giải thích bytecode transformation khác source-level AST transformation ở mức thông tin và thời điểm can thiệp như thế nào?
Bạn mô tả cấu trúc class file gồm constant pool, fields, methods và attributes theo mục tiêu một công cụ phân tích bytecode ra sao?
Bạn phân biệt class binary name, JVM descriptor và generic signature khi đọc một method từ class file như thế nào?
Bạn sử dụng javap để kiểm chứng instruction và descriptor được compiler tạo ra từ một đoạn mã Java như thế nào?
Bạn giải thích vai trò của JVM verifier trong việc từ chối bytecode vi phạm tính an toàn kiểu hoặc cấu trúc điều khiển ra sao?
Bạn phân tích vì sao thay đổi instruction có thể yêu cầu cập nhật stack map frames và metadata điều khiển luồng như thế nào?
Bạn thiết kế bước instrumentation đo thời gian phương thức mà vẫn xử lý đúng nhiều nhánh return và exception ra sao?
Bạn đánh giá rủi ro chèn code vào constructor trước khi đối tượng được khởi tạo đầy đủ từ góc nhìn quy tắc bytecode như thế nào?
Bạn phân biệt tạo class file mới với biến đổi một class file đã tồn tại theo yêu cầu metadata và kiểm thử ra sao?
Bạn lựa chọn thư viện ASM, Byte Buddy hoặc Class-File API chính thức của JDK hiện đại theo loại biến đổi và môi trường chạy như thế nào?
Bạn phân biệt Class-File API đã được chuẩn hóa trên JDK hỗ trợ với phiên bản preview từng có trên JDK cũ ra sao?
Bạn thiết kế một phép biến đổi bytecode giữ nguyên chữ ký public và exception semantics của method gốc như thế nào?
Bạn phân tích rủi ro làm lệch LineNumberTable hoặc thông tin debug khi chèn instruction mới vào method ra sao?
Bạn kiểm tra bytecode được sinh bằng javap và chạy verifier trước khi đưa vào pipeline build như thế nào?
Bạn giải thích ảnh hưởng của class file version khi một công cụ tạo bytecode cho runtime cũ hơn compiler đang dùng ra sao?
Bạn phân biệt hỗ trợ đọc class file mới với khả năng JVM mục tiêu thực thi instruction hoặc attribute mà nó chưa hỗ trợ như thế nào?
Bạn đánh giá nguy cơ transform bytecode nhiều lần làm xuất hiện logic logging hoặc tracing lặp lại như thế nào?
Bạn thiết kế cơ chế đánh dấu instrumentation đã áp dụng để tránh duplicate transformation khi lớp bị xử lý lần nữa như thế nào?
Bạn mô tả những khả năng chính của java.lang.instrument.Instrumentation trong việc theo dõi và biến đổi class ở runtime ra sao?
Bạn phân biệt Java agent khởi động qua premain với agent được nạp động và những ràng buộc vận hành đi kèm ra sao?
Bạn xác định cách ClassFileTransformer tham gia chu trình định nghĩa hoặc biến đổi class theo cơ chế Instrumentation như thế nào?
Bạn phân biệt retransformClasses với redefineClasses theo đầu vào và điều kiện hỗ trợ của JVM như thế nào?
Bạn phân tích những thay đổi cấu trúc class nào thường không được phép khi retransform hoặc redefine một class đã nạp như thế nào?
Bạn thiết kế agent chỉ instrumentation những package đã chọn nhằm tránh biến đổi class của chính agent hoặc thư viện logging ra sao?
Bạn đánh giá rủi ro deadlock hoặc recursion trong ClassFileTransformer khi transformer gọi những API kích hoạt thêm class loading như thế nào?
Bạn kiểm tra các điều kiện hỗ trợ retransformation của JVM trước khi cấu hình agent như thế nào?
Bạn phân tích chính sách an toàn khi cho phép dynamic agent loading trên JDK hiện đại thay vì mặc định nó luôn khả dụng như thế nào?
Bạn phân biệt Java agent quan sát hành vi với việc ghi đè policy bảo mật hoặc thay đổi logic nghiệp vụ ngoài kiểm soát như thế nào?
Bạn thiết kế test instrumentation để bảo đảm method gốc trả cùng kết quả và ném cùng loại lỗi trước và sau khi biến đổi như thế nào?
Bạn đánh giá overhead của instrumentation khi method được gọi với tần suất rất cao và cách giới hạn phạm vi như thế nào?
Bạn phân tích trách nhiệm của class loader trong việc tìm và định nghĩa class, đồng thời phân biệt với các bước linking do JVM thực hiện ra sao?
Bạn phân biệt loading, linking và initialization trong vòng đời class và thời điểm code có side effect có thể chạy ra sao?
Bạn giải thích cơ chế parent delegation của class loader và mục tiêu tránh tạo ra nhiều bản định nghĩa không tương thích như thế nào?
Bạn thiết kế custom class loader để nạp class plugin từ nguồn được phê duyệt mà vẫn kiểm soát namespace như thế nào?
Bạn phân biệt parent-first và child-first loading khi plugin cần phụ thuộc thư viện có phiên bản khác ứng dụng chính ra sao?
Bạn phân tích vì sao hai class có cùng binary name nhưng do class loader khác nhau định nghĩa có thể không ép kiểu cho nhau như thế nào?
Bạn xác định nguyên nhân ClassCastException có thông báo hai tên class giống nhau trong một môi trường plugin nhiều loader ra sao?
Bạn phân biệt ClassNotFoundException và NoClassDefFoundError dựa trên ngữ cảnh nạp và liên kết class như thế nào?
Bạn thiết kế quy trình debug LinkageError khi hai phiên bản thư viện không tương thích được nạp vào cùng runtime ra sao?
Bạn phân tích ý nghĩa của package sealing và cơ chế kiểm tra package metadata khi nhiều JAR tham gia class loading như thế nào?
Bạn xác định tác động của thread context class loader đến việc ServiceLoader tìm provider trong ứng dụng modular hoặc container như thế nào?
Bạn phân biệt việc đọc resources bằng class loader với việc nạp và khởi tạo một class tương ứng ra sao?
Bạn giải thích điều kiện để class và class loader có thể được garbage collector giải phóng sau khi ngừng sử dụng plugin như thế nào?
Bạn thiết kế cleanup cho plugin để đóng executor, gỡ listener và giải phóng references trước khi bỏ class loader ra sao?
Bạn phân tích nguy cơ ThreadLocal hoặc static registry giữ class của plugin khiến class loader vẫn bị giữ trong heap như thế nào?
Bạn đánh giá rủi ro định nghĩa class từ bytecode không tin cậy trong cùng JVM và lý do class loader riêng không phải sandbox bảo mật ra sao?
Bạn lựa chọn tiến trình cách ly hoặc môi trường kiểm soát riêng khi bắt buộc thực thi code không tin cậy theo những tiêu chí nào?
Bạn phân biệt ranh giới module của JPMS với không gian tên do class loader xác định khi phân tích một lỗi truy cập ra sao?
Bạn thiết kế cách dùng ServiceLoader hoặc module layer để phát hiện implementation mà không hard-code class name như thế nào?
Bạn giải thích vì sao ServiceLoader không bảo đảm mọi provider có thể khởi tạo thành công và cách xử lý lỗi provider ra sao?
Bạn phân tích rủi ro giữ Method hoặc Class trong cache toàn cục khi module layer hoặc plugin loader cần được tháo khỏi bộ nhớ như thế nào?
Bạn đánh giá cách theo dõi số class được load và unload bằng JFR, JMX hoặc class-loading logs để điều tra memory leak như thế nào?
Bạn xác định những giả định về class loader mà framework DI hoặc ORM thường đặt ra và cách kiểm thử trong môi trường plugin như thế nào?
Bạn đánh giá rủi ro bảo mật khi dùng metadata hoặc tên class do client cung cấp để quyết định kiểu đối tượng được khởi tạo qua reflection ra sao?
Bạn thiết kế allowlist các loại plugin và constructor hợp lệ để tránh instantiation những class không nằm trong phạm vi cho phép ra sao?
Bạn phân tích nguy cơ injection khi công cụ sinh mã ghép trực tiếp tên field, biểu thức hoặc string không được escape từ schema như thế nào?
Bạn thiết kế bước escape và validation các định danh Java được tạo tự động để đầu ra vẫn là source hợp lệ và an toàn ra sao?
Bạn xác định cách bảo vệ dữ liệu nhạy cảm khi metadata hoặc annotation chứa cấu hình được ghi vào generated source và artifact như thế nào?
Bạn giải thích vì sao strong encapsulation chỉ giới hạn một số quyền truy cập nhưng không thay thế phân quyền nghiệp vụ của ứng dụng như thế nào?
Bạn đánh giá rủi ro mở toàn bộ package nội bộ qua --add-opens chỉ để giúp một thư viện cũ chạy được ra sao?
Bạn thiết kế bộ tiêu chí kiểm tra nguồn gốc, checksum và quyền chạy của một Java agent bên thứ ba trước khi triển khai như thế nào?
Bạn phân tích cách transformer hoặc plugin làm thay đổi ranh giới tin cậy của một ứng dụng ngay cả khi API của ứng dụng không thay đổi ra sao?
Bạn lựa chọn cách logging các lần code generation hoặc bytecode transformation để hỗ trợ audit mà không ghi secret ra sao?
Bạn phân biệt reflection overhead với chi phí thực của lời gọi nghiệp vụ để quyết định có cần tối ưu bằng method handle hoặc code generation như thế nào?
Bạn thiết kế benchmark so sánh gọi method trực tiếp, reflection, method handle và proxy có kiểm soát JIT warm-up như thế nào?
Bạn đánh giá nguy cơ benchmark bị sai vì JIT loại bỏ kết quả hoặc tối ưu khác nhau giữa các đường gọi như thế nào?
Bạn phân tích ảnh hưởng của sinh quá nhiều class động đến metaspace, class loading time và thời gian khởi động như thế nào?
Bạn thiết kế cơ chế cache proxy hoặc generated class theo contract và class loader mà vẫn tránh rò rỉ bộ nhớ ra sao?
Bạn xác định cách đo thời gian compile tăng thêm do annotation processor và phân biệt với thời gian chạy ứng dụng như thế nào?
Bạn đánh giá đánh đổi giữa chi phí build dài hơn với việc loại bỏ reflection hoặc validation động ở runtime ra sao?
Bạn thiết kế chiến lược tương thích khi định dạng class file thay đổi qua các phiên bản JDK trong khi công cụ phải hỗ trợ nhiều runtime như thế nào?
Bạn phân tích cách một thư viện metaprogramming phụ thuộc API nội bộ javac có thể thất bại khi nâng JDK và kế hoạch thay thế ra sao?
Bạn kiểm tra build reproducibility của mã được sinh bằng cách so sánh artifact giữa hai môi trường có cùng input như thế nào?
Bạn thiết kế test compile-fail để xác minh processor thực sự chặn những khai báo annotation vi phạm hợp đồng như thế nào?
Bạn xây dựng snapshot test cho generated source nhưng vẫn tránh khóa cứng vào thứ tự phần tử không mang ý nghĩa ngữ nghĩa như thế nào?
Bạn lựa chọn golden-file test, property-based test hay integration test khi cần xác nhận bytecode transformation không đổi hành vi nghiệp vụ như thế nào?
Bạn thiết kế kiểm thử chạy trên class loader khác nhau để phát hiện lỗi tương thích interface và vòng đời plugin ra sao?
Bạn đánh giá ảnh hưởng của shading hoặc relocation package đến reflection, annotation name và ServiceLoader metadata như thế nào?
Bạn phân tích cách tối ưu native image hoặc AOT hạn chế một số hình thức reflection và dynamic class generation, rồi lập kế hoạch cấu hình thay thế ra sao?
Bạn thiết kế khả năng fallback khi runtime không hỗ trợ dynamic proxy hoặc instrumentation mà hệ thống vẫn phải thực hiện chức năng cốt lõi như thế nào?
Bạn thiết kế cơ chế truy vết lỗi từ generated code về schema hoặc annotation gốc để người dùng có thể sửa đúng đầu vào ra sao?
Bạn thiết kế tài liệu hợp đồng của một công cụ tạo mã bao gồm input, output, quyền truy cập, phiên bản và cách debug ra sao?
Một annotation processor không sinh file ở vòng đầu nhưng file phát sinh ở vòng sau bị xử lý lặp, bạn sẽ điều tra lifecycle và quy tắc tạo output như thế nào?
Một framework không thể gọi private constructor sau khi chuyển sang Java có strong encapsulation, bạn sẽ chẩn đoán module access và chọn cách sửa bền vững ra sao?
Một dynamic proxy ghi log vô hạn vì InvocationHandler tự gọi method trên chính proxy, bạn sẽ nhận diện vòng lặp và thiết kế lại invocation như thế nào?
Một proxy dựa trên interface không thể đại diện cho service chỉ có class concrete, bạn sẽ đánh giá adapter hoặc class-based proxy theo giới hạn nào?
Một agent chèn bytecode khiến class không qua verifier sau khi bổ sung nhánh exception, bạn sẽ kiểm tra stack map frames và metadata như thế nào?
Một công cụ tạo class file chạy được trên JDK mới nhưng lỗi trên runtime cũ, bạn sẽ xác định class file version và instruction không tương thích ra sao?
Hai plugin định nghĩa class cùng tên nhưng không thể trao đổi object dù chữ ký hiển thị giống nhau, bạn sẽ chẩn đoán class loader identity như thế nào?
Một môi trường ứng dụng không unload được plugin sau khi dừng, bạn sẽ tìm các tham chiếu từ ThreadLocal, static cache và class loader như thế nào?
Một generator sinh source khác nhau giữa CI và máy phát triển dù input nghiệp vụ giống nhau, bạn sẽ kiểm tra nguồn nondeterminism ra sao?
Một API dùng reflection dựa trên tên class do client gửi lên dẫn đến nguy cơ khởi tạo type không mong muốn, bạn sẽ thay đổi hợp đồng và ranh giới tin cậy như thế nào?
Bạn xây dựng checklist review siêu lập trình bao gồm tính đúng đắn ngữ nghĩa, type safety, API được hỗ trợ, bảo mật, hiệu năng, khả năng debug và tương thích như thế nào?
