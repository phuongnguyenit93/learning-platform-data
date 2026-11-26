Bạn lựa chọn JNI hay Foreign Function & Memory API cho một tính năng cần gọi thư viện C dựa trên những tiêu chí kỹ thuật nào?
Bạn giải thích ranh giới quản lý bộ nhớ, kiểm tra kiểu và xử lý lỗi khi Java gọi mã native như thế nào?
Bạn phân biệt API nguồn của thư viện C với ABI nhị phân mà JVM phải tuân thủ khi gọi hàm native ra sao?
Bạn đánh giá sự khác nhau về calling convention và cách truyền tham số giữa các nền tảng trước khi tích hợp thư viện native như thế nào?
Bạn kiểm chứng kích thước và cách biểu diễn các kiểu C như `int`, `long`, `size_t` và con trỏ khi ánh xạ sang Java bằng cách nào?
Bạn xử lý sự khác biệt về signedness của `char` và các kiểu số nguyên không dấu khi trao đổi dữ liệu giữa Java và C ra sao?
Bạn thiết kế ánh xạ một C struct có padding và yêu cầu alignment mà vẫn giữ đúng ABI như thế nào?
Bạn kiểm tra layout của struct lồng nhau và mảng struct khi chuyển dữ liệu qua ranh giới native bằng cách nào?
Bạn xử lý một C union mà các trường dùng chung vùng nhớ khi biểu diễn trên phía Java như thế nào?
Bạn đánh giá rủi ro khi ánh xạ C bit-field hoặc packed struct sang layout bộ nhớ có thể truy cập từ Java ra sao?
Bạn phân biệt việc truyền con trỏ tới một vùng nhớ với truyền bản sao giá trị qua ABI trong các API native như thế nào?
Bạn xây dựng hợp đồng ownership cho bộ đệm mà native code cấp phát và Java sử dụng bằng cách nào?
Bạn thiết kế giao tiếp giữa Java và một API C yêu cầu callback qua function pointer như thế nào?
Bạn phân biệt ưu nhược điểm của truy cập dữ liệu qua JNI, FFM và trao đổi bản sao khi thiết kế xử lý dữ liệu lớn ra sao?
Bạn xác định nguyên nhân một thư viện native nạp được trên máy phát triển nhưng không nạp được trong môi trường triển khai bằng cách nào?
Bạn phân biệt `System.load` và `System.loadLibrary` về cách chỉ định đường dẫn và tìm kiếm thư viện như thế nào?
Bạn chẩn đoán `UnsatisfiedLinkError` khi Java không tìm thấy thư viện hoặc symbol được yêu cầu bằng những bước nào?
Bạn kiểm tra sự khớp nhau giữa kiến trúc JVM và kiến trúc của thư viện native khi gặp lỗi nạp thư viện ra sao?
Bạn giải thích cách tên hàm JNI được liên kết với phương thức `native` và cách xử lý trường hợp phương thức overload như thế nào?
Bạn sử dụng cơ chế đăng ký native method bằng `RegisterNatives` trong tình huống nào và kiểm tra tính đúng đắn ra sao?
Bạn tận dụng `JNI_OnLoad` để kiểm tra phiên bản JNI và khởi tạo tài nguyên với những giới hạn vòng đời nào?
Bạn phân biệt `JavaVM` với `JNIEnv` và giải thích vì sao không thể dùng một `JNIEnv` tùy ý trên nhiều luồng như thế nào?
Bạn lấy `jclass`, `jmethodID` và `jfieldID` để truy cập thành viên Java từ native code như thế nào?
Bạn chẩn đoán `GetMethodID` không tìm thấy phương thức vì chữ ký JNI hoặc kiểu trả về không khớp ra sao?
Bạn giải thích vì sao `FindClass` có thể tìm lớp thành công trên luồng Java nhưng thất bại trong native callback từ luồng tự tạo như thế nào?
Bạn phân biệt local reference, global reference và weak global reference trong JNI về vòng đời và tác động đến GC ra sao?
Bạn quản lý local reference khi một hàm JNI tạo hàng nghìn đối tượng trong vòng lặp để tránh cạn bảng tham chiếu như thế nào?
Bạn tổ chức xóa global reference và tài nguyên native khi đối tượng sở hữu ở Java ngừng hoạt động bằng cách nào?
Bạn sử dụng weak global reference để liên kết metadata native với đối tượng Java mà vẫn cho phép GC thu hồi ra sao?
Bạn gắn một native thread vào JVM để gọi ngược mã Java và quản lý việc detach đúng thời điểm như thế nào?
Bạn kiểm tra và xử lý Java exception đang pending trong JNI trước khi thực hiện thêm các thao tác khác ra sao?
Bạn chuyển lỗi trả về từ hàm C thành ngoại lệ Java mà vẫn bảo toàn thông tin nguyên nhân như thế nào?
Bạn phân biệt Modified UTF-8 trong JNI với UTF-8 chuẩn khi trao đổi chuỗi với một thư viện C như thế nào?
Bạn sử dụng `GetStringChars` và `ReleaseStringChars` khi cần xử lý dữ liệu UTF-16 và giới hạn truy cập của chúng ra sao?
Bạn thiết kế chuyển đổi chuỗi có ký tự NUL nội bộ hoặc ký tự ngoài BMP giữa Java và C bằng cách nào?
Bạn xử lý khả năng copy hoặc pin dữ liệu khi dùng các hàm JNI `GetPrimitiveArrayElements` và `ReleasePrimitiveArrayElements` như thế nào?
Bạn lựa chọn chế độ release của mảng JNI khi native code chỉ đọc hoặc đã thay đổi dữ liệu bằng cách nào?
Bạn xác định trường hợp phù hợp và giới hạn thao tác trong vùng `GetPrimitiveArrayCritical` để không ảnh hưởng GC như thế nào?
Bạn dùng direct `ByteBuffer` để chia sẻ vùng nhớ native mà vẫn kiểm soát vòng đời địa chỉ phía C ra sao?
Bạn kiểm tra tính hợp lệ của con trỏ khi tạo `NewDirectByteBuffer` từ vùng nhớ do thư viện native sở hữu như thế nào?
Bạn xử lý một callback JNI từ native thread đang chạy đồng thời với thao tác đóng tài nguyên Java ra sao?
Bạn quyết định cache `jclass` hoặc `jmethodID` ở phía native như thế nào để tối ưu mà vẫn tôn trọng class unloading?
Bạn phân tích nguyên nhân memory leak khi mã native giữ tài nguyên ngoài heap dù Java heap vẫn ổn định bằng cách nào?
Bạn giải thích cách `MemorySegment` mô hình hóa vùng nhớ, giới hạn truy cập và vòng đời khi làm việc với FFM API như thế nào?
Bạn chọn `Arena.ofConfined`, `Arena.ofShared` hoặc cơ chế quản lý vòng đời khác cho một tác vụ FFM đa luồng như thế nào?
Bạn xác định thời điểm nên đóng `Arena` và cách bảo đảm không còn thao tác native nào dùng vùng nhớ đó ra sao?
Bạn phân tích nguyên nhân một `MemorySegment` không còn truy cập được sau khi arena sở hữu bị đóng như thế nào?
Bạn sử dụng `MemorySegment.asSlice` để truy cập một phần bộ đệm mà vẫn kiểm tra biên và alignment ra sao?
Bạn đọc và ghi dữ liệu bằng `ValueLayout` tương ứng với kiểu C mà không phụ thuộc giả định sai về kích thước kiểu như thế nào?
Bạn tạo `MemoryLayout` cho một struct có trường mảng, trường lồng nhau và padding theo ABI như thế nào?
Bạn dùng `MemoryLayout.PathElement` và `VarHandle` để truy cập một trường nằm sâu trong struct ra sao?
Bạn xác minh thứ tự byte và yêu cầu alignment của vùng nhớ native khi trao đổi dữ liệu nhị phân như thế nào?
Bạn xử lý một C struct được truyền hoặc trả về theo giá trị thay vì truyền con trỏ bằng cơ chế FFM như thế nào?
Bạn dùng `Linker.nativeLinker` và `FunctionDescriptor` để mô tả chữ ký hàm C cho một downcall như thế nào?
Bạn kiểm tra việc tìm symbol thông qua `SymbolLookup` khi một thư viện có nhiều phiên bản hoặc export symbol khác nhau ra sao?
Bạn thiết kế `MethodHandle` cho downcall sao cho chữ ký Java khớp với `FunctionDescriptor` và ABI native như thế nào?
Bạn xử lý một hàm C có tham số biến thiên như `printf` bằng cấu hình linker phù hợp và kiểm tra giới hạn ABI ra sao?
Bạn thu nhận trạng thái lỗi như `errno` sau lời gọi native mà không bị một lời gọi khác ghi đè bằng cách nào?
Bạn tạo upcall stub để C gọi vào Java và quản lý thời gian sống của callback theo arena như thế nào?
Bạn định nghĩa hợp đồng xử lý lỗi cho upcall để ngoại lệ Java không phá vỡ kỳ vọng của hàm native như thế nào?
Bạn kiểm soát truy cập theo luồng khi một upcall chạm vào `MemorySegment` được cấp phát trong confined arena ra sao?
Bạn xử lý trường hợp thư viện C lưu con trỏ để truy cập bất đồng bộ sau khi lời gọi downcall đã trả về như thế nào?
Bạn diễn giải con trỏ native trả về thành một `MemorySegment` có phạm vi truy cập phù hợp và tránh đọc vượt vùng nhớ ra sao?
Bạn thiết kế cách giải phóng vùng nhớ được cấp phát bởi thư viện native bằng đúng hàm giải phóng tương ứng như thế nào?
Bạn nhận diện các tình huống double free, use-after-free và dangling pointer khi Java và C cùng tham chiếu một vùng nhớ ra sao?
Bạn phân biệt vùng nhớ heap được truy cập qua `MemorySegment.ofArray` với vùng nhớ native khi truyền địa chỉ sang hàm C như thế nào?
Bạn đánh giá rủi ro của thao tác `MemorySegment.reinterpret` nếu kích thước vùng nhớ hoặc thời gian sống không được chứng minh ra sao?
Bạn xử lý NULL pointer và các giá trị sentinel đặc biệt trong hợp đồng API C khi ánh xạ sang Java như thế nào?
Bạn kiểm tra quyền truy cập native bị giới hạn theo module hoặc cấu hình runtime trước khi chạy chức năng FFM như thế nào?
Bạn thiết kế giới hạn kích thước và xác thực dữ liệu đầu vào trước khi chuyển chuỗi hoặc buffer không tin cậy cho native code ra sao?
Bạn xác định cách biên dịch hoặc tạo wrapper C cho thư viện C++ cần giao tiếp với Java nhằm tránh vấn đề name mangling và ABI như thế nào?
Bạn thiết kế cơ chế xử lý ngoại lệ C++ trong wrapper native để không cho ngoại lệ vượt qua ranh giới ABI C như thế nào?
Bạn kiểm tra quyền sở hữu và cách giải phóng chuỗi hoặc cấu trúc do thư viện Rust xuất qua C ABI khi Java sử dụng như thế nào?
Bạn giải quyết khác biệt về đường dẫn tìm thư viện, dependency và runtime loader giữa Windows, Linux và macOS ra sao?
Bạn xác định lỗi do thiếu thư viện phụ thuộc gián tiếp của một `.so`, `.dll` hoặc `.dylib` bằng cách nào?
Bạn quản lý tương thích phiên bản ABI và symbol khi cập nhật thư viện native nhưng vẫn giữ Java API hiện có như thế nào?
Bạn chuẩn bị bản phân phối ứng dụng kèm thư viện native theo hệ điều hành và kiến trúc CPU bằng cách nào?
Bạn xác minh một binary native được build với toolchain hoặc runtime C tương thích với môi trường đích như thế nào?
Bạn xử lý trường hợp cùng JVM cần nạp hai phiên bản thư viện native có symbol hoặc trạng thái toàn cục xung đột ra sao?
Bạn chẩn đoán JVM bị `SIGSEGV` hoặc access violation bằng crash log và native stack trace theo các bước nào?
Bạn dùng debugger native như GDB hoặc LLDB để đối chiếu Java thread và khung gọi C tại thời điểm crash như thế nào?
Bạn dùng AddressSanitizer hoặc UndefinedBehaviorSanitizer để phát hiện lỗi bộ nhớ của thư viện native trong quá trình kiểm thử ra sao?
Bạn xây dựng kiểm thử cạnh tranh để phát hiện race condition khi nhiều Java thread gọi một API native không thread-safe như thế nào?
Bạn thiết kế kiểm thử fuzzing cho ranh giới ánh xạ kiểu, chiều dài buffer và giá trị NULL của thư viện native ra sao?
Bạn đánh giá chi phí chuyển tiếp giữa Java và native bằng benchmark có warm-up và tách biệt chi phí cấp phát bộ nhớ như thế nào?
Bạn tối ưu luồng dữ liệu lớn qua JNI hoặc FFM để giảm copy nhưng vẫn giữ rõ quyền sở hữu bộ nhớ bằng cách nào?
Bạn thiết kế ma trận CI cho JNI và FFM trên các phiên bản JDK, hệ điều hành, CPU architecture và toolchain như thế nào?
Bạn xem xét những hạn chế hoặc thay đổi cần thiết khi đóng gói ứng dụng dùng JNI hay FFM thành native image như thế nào?
Bạn lập kế hoạch chuyển một thành phần từ JNI sang FFM API và kiểm chứng tương thích hành vi, hiệu năng và thu hồi tài nguyên ra sao?
Bạn xây dựng quy trình dừng ứng dụng để kết thúc callback, giải phóng arena, đóng handle và thư viện native theo thứ tự an toàn như thế nào?
