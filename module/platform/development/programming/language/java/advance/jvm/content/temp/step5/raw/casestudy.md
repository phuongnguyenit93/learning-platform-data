Một dịch vụ Java biên dịch bằng JDK mới chạy thành công tại máy phát triển nhưng báo UnsupportedClassVersionError trên máy chủ cũ; hãy xây dựng tình huống xác minh phiên bản class file và runtime.
Một ứng dụng cùng lúc chứa hai phiên bản thư viện có cùng tên lớp trong classpath, khiến phương thức được gọi khác với phiên bản mà đội phát triển đã biên dịch; hãy đặt bài toán kiểm tra lựa chọn class khi chạy.
Một nền tảng plugin tải hai bản sao của cùng một interface bằng các class loader khác nhau, khiến phép ép kiểu thất bại dù tên lớp và nội dung bytecode giống nhau; hãy xây dựng tình huống giải thích định danh kiểu.
Một ứng dụng server triển khai lại nhiều lần nhưng heap và metaspace tiếp tục tăng do class loader của phiên bản cũ không được thu hồi; hãy đặt tình huống truy tìm mối tham chiếu giữ class loader.
Một hệ thống plugin dùng cơ chế tải lớp riêng để cô lập thư viện, nhưng một plugin vô tình tải lớp nền tảng không tương thích với API của ứng dụng chủ; hãy xây dựng tình huống kiểm chứng chiến lược ủy quyền tải lớp.
Một lớp có khối khởi tạo tĩnh truy cập cấu hình chưa sẵn sàng nên lần sử dụng đầu tiên thất bại, còn những lần sau báo lỗi khác; hãy đặt tình huống phân tích trạng thái khởi tạo lớp.
Một ứng dụng có hai lớp khởi tạo tĩnh phụ thuộc vòng nhau và kết quả một trường dữ liệu thay đổi theo thứ tự sử dụng đầu tiên; hãy xây dựng tình huống kiểm tra thời điểm chuẩn bị và khởi tạo lớp.
Một thư viện được đưa vào classpath nhưng một phụ thuộc chỉ xuất hiện khi chạy chức năng hiếm dùng, khiến NoClassDefFoundError xảy ra sau nhiều ngày vận hành; hãy đặt bài toán kiểm chứng liên kết lớp.
Một đội triển khai cập nhật JAR cung cấp API nhưng giữ JAR consumer đã biên dịch theo chữ ký cũ, khiến request đầu tiên gặp NoSuchMethodError; hãy xây dựng tình huống phân tích tương thích nhị phân.
Một nhóm thay đổi kiểu thành viên từ phương thức instance sang static trong thư viện mà không biên dịch lại ứng dụng sử dụng, khiến lỗi liên kết xuất hiện tại runtime; hãy đặt tình huống xác minh hợp đồng bytecode.
Một bytecode transformer sửa phần class file cho mục đích tracing nhưng JVM báo VerifyError trước khi controller được gọi; hãy xây dựng tình huống kiểm tra tính hợp lệ của luồng điều khiển và kiểu.
Một chương trình sinh proxy lúc chạy và thất bại khi truy cập package của một Java module khác, dù cách gọi tương tự hoạt động trên classpath truyền thống; hãy đặt tình huống phân biệt giới hạn truy cập module.
Một công cụ reflection muốn truy cập thành viên không công khai của thư viện JDK và gặp lỗi sau khi nâng Java, nhưng tác giả cho rằng class loader bị hỏng; hãy xây dựng tình huống xác định nguyên nhân thực tế.
Một framework tạo lambda và dynamic call site ở runtime, nhưng nhóm đọc class file chỉ thấy lệnh invokedynamic mà không tìm được lớp triển khai trong mã nguồn; hãy đặt bài toán đối chiếu bytecode với hành vi thực thi.
Một ứng dụng dùng generic API qua nhiều phiên bản thư viện và phát sinh lỗi với phương thức bridge sau khi thay đổi kiểu trả về; hãy xây dựng tình huống kiểm chứng ảnh hưởng của type erasure.
Một thư viện định nghĩa hằng số biên dịch được nhúng vào các client cũ, khiến việc thay giá trị trong JAR không làm thay đổi hành vi client đang chạy; hãy đặt tình huống phân tích hằng số và liên kết.
Một ứng dụng đóng gói multi-release JAR hoạt động khác nhau giữa hai phiên bản Java mặc dù chỉ triển khai một artifact; hãy xây dựng tình huống xác minh phiên bản lớp thực tế được nạp.
Một module sử dụng ServiceLoader để khám phá nhà cung cấp dịch vụ nhưng danh sách implementation thay đổi khi chạy trong web container; hãy đặt tình huống đánh giá vai trò của context class loader.
Một hệ thống chạy agent có thể sửa bytecode ở thời điểm nạp lớp, khiến stack trace và hành vi khác với class file gốc đã biên dịch; hãy xây dựng tình huống thu thập chứng cứ về lớp đang thực thi.
Một đội vận hành dùng cơ chế thay lớp đang chạy nhưng thay đổi cấu trúc class vượt khả năng của runtime, khiến cập nhật thất bại sau khi đã dừng một số tác vụ; hãy đặt bài toán đánh giá giới hạn hotswap.
Một bộ kiểm thử bytecode cho thấy hai đoạn Java có cùng kết quả nghiệp vụ nhưng cách dùng operand stack và local variables khác nhau; hãy xây dựng tình huống xác minh khác biệt ở cấp class file.
Một ứng dụng chạy ổn định khi biên dịch toàn bộ mã nhưng lỗi tại runtime khi chỉ thay một interface chứa default method mới; hãy đặt tình huống phân tích lựa chọn phương thức trong quá trình liên kết.
Một framework nạp lớp theo tên từ cấu hình người dùng và vô tình kích hoạt khởi tạo tĩnh có tác dụng phụ ngoài mong đợi; hãy xây dựng tình huống kiểm chứng phân biệt tải, liên kết và khởi tạo.
Một dịch vụ có nhiều class loader do framework tạo, nhưng báo cáo heap chỉ cho thấy các đối tượng Class tăng liên tục mà chưa xác định được plugin gây ra; hãy đặt tình huống điều tra bộ nhớ metadata.
Một ứng dụng cần hỗ trợ JDK khác nhau ở nhiều môi trường và đang dùng tính năng bytecode mới, nhưng pipeline chỉ kiểm tra biên dịch chứ chưa xác minh class file ở runtime thấp nhất; hãy xây dựng tình huống kiểm tra phát hành.
Một API xử lý biểu thức đệ quy sâu trên dữ liệu hợp lệ nhưng đôi khi ném StackOverflowError trong production, dù kích thước heap còn dư; hãy đặt tình huống phân biệt giới hạn ngăn xếp với heap.
Một dịch vụ tạo rất nhiều platform thread với cấu hình stack lớn, khiến JVM không tạo được thêm luồng dù heap còn bộ nhớ; hãy xây dựng tình huống phân tích chi phí vùng nhớ của thread.
Một nhóm tăng heap để khắc phục lỗi không thể tạo native thread nhưng số luồng vẫn tăng và container bị dừng; hãy đặt bài toán xác định những vùng nhớ không được điều khiển bằng giới hạn heap.
Một ứng dụng chạy trong container có giới hạn bộ nhớ chặt, nhưng tổng RSS cao hơn nhiều so với heap đã sử dụng và tiến trình bị OOM kill; hãy xây dựng tình huống đo bộ nhớ ngoài heap.
Một chương trình sử dụng direct byte buffer cho mạng tốc độ cao và gặp lỗi cạn direct memory trong khi heap dump không cho thấy nhiều đối tượng lớn; hãy đặt tình huống kiểm chứng vòng đời vùng nhớ trực tiếp.
Một thư viện JNI giữ global reference tới hàng triệu đối tượng Java, khiến GC không thu hồi chúng dù code ứng dụng không còn tham chiếu; hãy xây dựng tình huống điều tra GC root từ mã native.
Một ứng dụng phát triển plugin mới mỗi giờ, khiến lượng metaspace tăng đến giới hạn và báo OutOfMemoryError mặc dù bộ đếm heap ổn định; hãy đặt bài toán kiểm tra vòng đời định nghĩa lớp.
Một dịch vụ có nhiều phương thức được JIT biên dịch và vùng code cache cạn, khiến hiệu năng giảm mạnh sau nhiều giờ chạy; hãy xây dựng tình huống xác minh giới hạn bộ nhớ dành cho mã máy.
Một nhóm xem sơ đồ runtime data areas trong đặc tả JVM và kết luận mọi bản JVM đều dùng cấu trúc metaspace giống HotSpot; hãy đặt tình huống đánh giá khác biệt giữa yêu cầu đặc tả và triển khai.
Một dịch vụ đo bộ nhớ từng frame khi đệ quy và cho rằng đối tượng tạo trong method luôn nằm trên stack, trong khi profiling cho kết quả khác; hãy xây dựng tình huống phân tích vòng đời object.
Một ứng dụng thao tác mảng lớn và ném OutOfMemoryError khi tạo array, nhưng đội vận hành chỉ xem số đối tượng mà không đo kích thước mảng; hãy đặt tình huống phân tích nhu cầu cấp phát.
Một module dùng memory-mapped file để đọc dữ liệu nhưng footprint của tiến trình cao hơn tổng heap và direct buffer được báo cáo; hãy xây dựng tình huống xác minh sự tương tác với bộ nhớ hệ điều hành.
Một nhóm chỉ đặt Xmx theo memory limit của container và không dành chỗ cho stack, metaspace cùng bộ nhớ native, khiến Pod bị kết thúc; hãy đặt tình huống thiết kế phép đo tổng tài nguyên.
Một ứng dụng được khởi động với lượng heap ban đầu thấp và heap tối đa cao, khiến độ trễ giai đoạn đầu biến động khi JVM mở rộng heap; hãy xây dựng tình huống đánh giá ảnh hưởng của cấu hình kích thước.
Một dịch vụ lưu dữ liệu nhạy cảm trong heap và tạo heap dump khi xảy ra lỗi, nhưng artifact chẩn đoán được chia sẻ rộng trong đội; hãy đặt bài toán kiểm chứng tính riêng tư của dữ liệu dump.
Một tiến trình chạy nhiều virtual thread để xử lý I/O, nhưng nhóm áp dụng cách tính bộ nhớ stack như khi dùng platform thread và đưa ra dự báo sai; hãy xây dựng tình huống đánh giá mô hình cấp phát.
Một ứng dụng liên tục tạo class động phục vụ template rendering, nhưng hệ thống giám sát chỉ đo heap nên không cảnh báo trước khi metaspace hết; hãy đặt tình huống xây dựng bộ chỉ số phù hợp.
Một nhóm theo dõi bộ nhớ sử dụng bằng công cụ hệ điều hành và bộ nhớ committed của JVM, nhưng hai con số chênh lệch lớn; hãy xây dựng tình huống xác định ý nghĩa của từng số liệu.
Một API trả về báo cáo chứa hàng triệu bản ghi và giữ toàn bộ kết quả trong bộ nhớ trước khi serialize, khiến heap tăng vọt rồi giảm sau GC; hãy đặt tình huống đánh giá tải cấp phát tạm thời.
Một service lưu object listener trong danh sách static nhưng không hủy đăng ký khi khách hàng rời hệ thống, khiến heap tăng theo số phiên từng hoạt động; hãy xây dựng tình huống truy tìm tham chiếu giữ object.
Một ứng dụng dùng cache HashMap không giới hạn theo ID giao dịch, khiến số lượng entry tiếp tục tăng dù các bản ghi không còn được truy cập; hãy đặt tình huống phân biệt cache hữu ích và memory leak.
Một service giữ dữ liệu của người dùng trong ThreadLocal của thread pool và không giải phóng sau request, khiến yêu cầu tiếp theo có thể thấy dữ liệu cũ; hãy xây dựng tình huống kiểm tra vòng đời tham chiếu.
Một hệ thống có chu trình tham chiếu giữa các object nhưng không còn GC root giữ chúng, trong khi nhóm khẳng định đây là nguyên nhân memory leak; hãy đặt tình huống phân tích reachability.
Một bộ cache dùng WeakReference để giữ các model có thể tái tạo, nhưng đối tượng biến mất ngay khi hệ thống thiếu tham chiếu mạnh khác; hãy xây dựng tình huống đánh giá hành vi bộ nhớ đệm.
Một ứng dụng dùng SoftReference để lưu ảnh đã xử lý và kết quả cache thay đổi khó đoán theo áp lực bộ nhớ; hãy đặt tình huống kiểm chứng chính sách lưu trữ phù hợp yêu cầu nghiệp vụ.
Một dịch vụ dùng PhantomReference và ReferenceQueue để theo dõi tài nguyên native, nhưng hàng đợi không được xử lý khi tải cao; hãy xây dựng tình huống đánh giá vòng đời tài nguyên bên ngoài heap.
Một thư viện vẫn phụ thuộc vào finalization để đóng tài nguyên đắt tiền, nhưng áp lực GC và thời gian dọn dẹp không phù hợp yêu cầu vận hành; hãy đặt tình huống kiểm chứng độ tin cậy dọn tài nguyên.
Một endpoint trả dữ liệu theo luồng nhưng lambda callback vô tình giữ tham chiếu tới toàn bộ danh sách kết quả, khiến các object lớn tồn tại sau khi gửi response; hãy xây dựng tình huống xác minh retention.
Một ứng dụng dùng String intern cho dữ liệu định danh tạo động từ request, khiến vùng dữ liệu string tăng bất thường sau nhiều giờ vận hành; hãy xây dựng tình huống kiểm tra tập giá trị giữ lại.
Một dịch vụ xử lý JSON tạo nhiều chuỗi trùng nhau và nhóm cân nhắc string deduplication của collector, nhưng chưa có dữ liệu về bộ nhớ và chi phí CPU; hãy đặt tình huống đánh giá lựa chọn tối ưu.
Một ứng dụng tạo nhiều object ngắn hạn trong vòng lặp nhưng heap vẫn ổn định, trong khi profiler báo allocation rate rất cao; hãy xây dựng tình huống phân biệt tốc độ cấp phát với memory leak.
Một nhóm giả định mỗi lần tạo object đều cấp phát trực tiếp trên heap mà không có tối ưu của JIT, dẫn tới kết luận sai khi so sánh số lần khởi tạo và dữ liệu allocation; hãy đặt bài toán kiểm chứng escape analysis.
Một API giữ những đối tượng lớn trong queue khi downstream chậm, làm old generation tăng và latency xấu đi dù GC vẫn chạy đều; hãy xây dựng tình huống truy tìm chủ sở hữu dữ liệu.
Một hệ thống dùng direct buffer và Cleaner để thu hồi tài nguyên, nhưng tốc độ tạo buffer vượt khả năng dọn dẹp làm native memory tăng; hãy đặt tình huống đánh giá vòng đời vùng nhớ.
Một chương trình sử dụng object pool để tránh cấp phát nhưng pool tăng không giới hạn khi tải đột biến rồi không giảm khi tải trở lại; hãy xây dựng tình huống đo chi phí lưu giữ.
Một service ghi nhận GC root giữ một cây object lớn thông qua static field, nhưng nhóm chỉ nhìn số lượng object từng loại trong heap histogram; hãy đặt tình huống đánh giá retained size.
Một chức năng phân tích ảnh tạo các mảng byte kích thước lớn khiến thời gian GC biến động mạnh khi lưu lượng tăng, nhưng lượng dữ liệu trả về tương đối nhỏ; hãy đặt tình huống phân tích vòng đời mảng.
Một ứng dụng phụ thuộc vào hành vi thu hồi object ngay khi biến cục bộ hết phạm vi, nhưng tài nguyên liên quan chỉ được giải phóng rất lâu sau đó; hãy đặt tình huống kiểm chứng giới hạn bảo đảm của GC.
Một dịch vụ thương mại điện tử có throughput ổn định nhưng p99 latency tăng mỗi khi GC dừng ứng dụng, khiến khách hàng báo timeout; hãy xây dựng tình huống đối chiếu GC pause với SLO.
Một hệ thống sử dụng G1 và liên tục xử lý các mảng rất lớn, khiến old generation xuất hiện nhiều vùng humongous và chu kỳ GC bất thường; hãy đặt tình huống phân tích mẫu cấp phát.
Một API có nhiều object sống ngắn nhưng young collection diễn ra quá thường xuyên, khiến CPU dành cho GC tăng; hãy xây dựng tình huống đánh giá allocation rate và cấu hình collector.
Một dịch vụ giữ cache sống lâu làm vùng old generation tăng đều sau mỗi lần deploy, nhưng nhóm chỉ xem số lần minor GC trong dashboard; hãy đặt tình huống xác định tín hiệu heap.
Một ứng dụng có pause budget nghiêm ngặt nên nhóm chuyển từ G1 sang collector đồng thời, nhưng CPU sử dụng và throughput thay đổi đáng kể; hãy đặt bài toán kiểm chứng tradeoff.
Một batch job tính toán ngắn chạy trong container nhỏ và đội phát triển đang áp dụng cấu hình GC của dịch vụ HTTP có heap lớn; hãy xây dựng tình huống đánh giá collector theo workload.
Một hệ thống G1 có các đợt mixed collection kéo dài hơn dự kiến sau khi cache được làm nóng, khiến độ trễ giao dịch tăng; hãy xây dựng tình huống đọc log GC và trạng thái heap.
Một dịch vụ tạo nhiều object vừa đủ sống sót qua các lần collection nên promotion lên old generation tăng mạnh dưới tải; hãy đặt tình huống kiểm tra tuổi thọ đối tượng.
Một ứng dụng báo lỗi thiếu vùng nhớ khi GC cần chuyển object sống giữa các vùng trong giờ cao điểm, dù trước đó heap tưởng còn trống; hãy xây dựng tình huống phân tích áp lực evacuation.
Một nhóm tăng heap tối đa để giảm tần suất GC nhưng tổng RSS vượt memory limit của Kubernetes và container bị kill; hãy đặt tình huống kiểm chứng ngân sách bộ nhớ.
Một dịch vụ gặp OutOfMemoryError với thông báo GC overhead limit exceeded sau nhiều giờ, trong khi nhóm khẳng định lỗi do một request lớn duy nhất; hãy đặt tình huống đối chiếu log và dữ liệu cấp phát.
Một chương trình thường xuyên chủ động yêu cầu full GC để giải phóng bộ nhớ và báo cáo latency có các khoảng dừng bất thường; hãy đặt tình huống kiểm tra ảnh hưởng của GC do ứng dụng yêu cầu.
Một dịch vụ dùng một collector trong môi trường thử nghiệm và collector khác ở production, khiến kết quả đo pause time không thể so sánh trực tiếp; hãy xây dựng tình huống chuẩn hóa điều kiện benchmark.
Một ứng dụng xử lý giao dịch ban đêm có heap occupancy ổn định nhưng RSS không giảm ngay sau GC, khiến đội vận hành cho rằng GC không thu hồi được object; hãy đặt bài toán đánh giá heap committed và RSS.
Một hệ thống xử lý nhiều WeakReference và SoftReference trong lúc áp lực bộ nhớ tăng, gây thêm thời gian xử lý tham chiếu trong một số chu kỳ GC; hãy đặt tình huống phân tích dữ liệu collector.
Một nền tảng dùng nhiều class loader cho plugin và việc class unloading diễn ra chậm, khiến metadata memory không giảm dù các plugin đã dừng; hãy đặt tình huống kiểm chứng điều kiện thu hồi lớp.
Một dịch vụ nâng heap để giảm pause nhưng giai đoạn marking đồng thời sử dụng nhiều CPU hơn và cạnh tranh với luồng nghiệp vụ; hãy xây dựng tình huống đánh giá chi phí collector.
Một ứng dụng đạt p99 mục tiêu ở tải trung bình nhưng GC pause tăng mạnh khi thêm 30% lưu lượng, dù dung lượng heap chưa chạm giới hạn; hãy đặt bài toán thiết kế thử tải.
Một ứng dụng triển khai trong container có giới hạn CPU thấp hơn số lõi mà JVM thấy trên máy host, khiến cấu hình luồng GC và hiệu năng không như dự báo; hãy đặt tình huống đánh giá nhận diện tài nguyên.
Một team so sánh hai collector dựa trên tổng số lần GC nhưng không đo thời gian dừng ứng dụng, throughput và dữ liệu sống; hãy đặt tình huống xác định tiêu chí đánh giá công bằng.
Một hệ thống có đột biến latency đúng lúc các luồng đến safepoint, nhưng log GC không cho thấy pause dài tương ứng; hãy xây dựng tình huống điều tra các hoạt động JVM tại safepoint.
Một ứng dụng có old generation liên tục gần đầy sau khi tải giảm, trong khi heap dump không cho thấy object tăng bất thường; hãy đặt tình huống phân biệt live set và cấu hình heap.
Một service streaming dùng buffer lớn và tạo nhiều object trung gian, khiến concurrent GC phải làm việc liên tục khi tải cao; hãy xây dựng tình huống tìm giới hạn năng lực xử lý.
Một đội vận hành thay đổi các cờ GC dựa trên kinh nghiệm từ JDK cũ mà chưa kiểm tra cờ còn hiệu lực trên JDK mới; hãy đặt bài toán kiểm chứng cấu hình khi nâng phiên bản.
Một hệ thống chỉ lưu log GC ở mức tổng hợp nên không xác định được thời điểm promotion và concurrent marking gây ảnh hưởng tới request; hãy xây dựng tình huống thiết kế dữ liệu chẩn đoán.
Một ứng dụng dùng profile CPU trong vài giây rồi kết luận collector gây nghẽn, trong khi request latency cao xuất hiện ở các khoảng khác; hãy đặt tình huống thiết kế cách quan sát đồng thời.
Một dịch vụ có quá nhiều request giữ object qua các chu kỳ GC, khiến tăng thời gian sống trung bình của object và áp lực old generation; hãy xây dựng tình huống đánh giá tương tác giữa tải và cấp phát.
Một nhóm tối ưu mã để giảm allocation nhưng kết quả số lần GC giảm mà p99 latency không cải thiện, khiến nhóm cần tìm nguyên nhân ngoài GC; hãy đặt tình huống xác minh hiệu quả thay đổi.
Một ứng dụng chạy chậm trong vài phút đầu rồi nhanh dần dù lượng dữ liệu không thay đổi, khiến người dùng nghi ngờ cơ sở dữ liệu; hãy xây dựng tình huống kiểm tra tiered compilation và thời gian làm nóng JIT.
Một service có một method xử lý rất nóng được tối ưu trong production, nhưng profile test không đủ tải nên không thể tái hiện hiệu năng; hãy đặt tình huống đánh giá ngưỡng và trạng thái JIT.
Một chương trình xử lý nhiều kiểu đối tượng qua cùng interface, khiến lời gọi ảo khó tối ưu hơn so với workload chỉ gặp một implementation; hãy xây dựng tình huống phân tích hình thái call site.
Một ứng dụng thay đổi phân bố dữ liệu đầu vào sau đợt phát hành, khiến mã máy được tối ưu theo giả định cũ phải deoptimize trong thời gian ngắn; hãy đặt tình huống điều tra biến động latency.
Một nhóm đo thời gian của một phép tính bằng vòng lặp nhỏ và kết luận một phương án nhanh gấp nhiều lần, nhưng kết quả biến đổi khi JIT tối ưu bỏ công việc không được quan sát; hãy đặt tình huống đánh giá benchmark.
Một ứng dụng có method lớn với nhiều nhánh và kết quả không được inline như các method nhỏ khác, khiến throughput giảm sau khi refactor; hãy xây dựng tình huống đo tác động inlining.
Một dịch vụ sau khi khởi động lại có CPU tăng do quá trình biên dịch JIT diễn ra cùng lúc với tải thật, khiến thời gian phản hồi đầu tiên xấu đi; hãy đặt tình huống đánh giá tác động startup.
Một ứng dụng dùng nhiều đoạn mã tự sinh ra ở runtime, khiến code cache đầy và các phương thức mới không được biên dịch như trước; hãy đặt tình huống kiểm tra trạng thái code cache.
Một ứng dụng thấy kết quả microbenchmark khác nhau rất lớn khi chạy với chế độ thông dịch và cấu hình JIT mặc định, khiến nhóm hiểu nhầm yêu cầu của đặc tả JVM về hiệu năng; hãy đặt tình huống phân biệt.
Một hệ thống tối ưu một đoạn vòng lặp dài nhờ OSR khi đang chạy, nhưng phép đo đầu tiên và các lần chạy sau có độ trễ rất khác; hãy đặt tình huống kiểm chứng mức độ warmup.
Một thư viện số học được JVM tối ưu qua intrinsic trên một kiến trúc CPU nhưng chậm trên môi trường máy khác, dù cùng bytecode Java; hãy xây dựng tình huống kiểm tra sự phụ thuộc triển khai.
Một nhóm kỳ vọng HotSpot tự vectorize mọi thao tác trên mảng lớn và đưa ra SLO dựa trên benchmark từ một máy duy nhất; hãy đặt bài toán đánh giá giới hạn tối ưu hóa và CPU.
Một chương trình dùng escape analysis và scalar replacement nên một số object không xuất hiện như dự đoán trong allocation profile, khiến đội phát triển nghi ngờ công cụ; hãy xây dựng tình huống phân tích.
Một ứng dụng có đường xử lý ngoại lệ hiếm dùng và latency tăng mạnh khi nhánh đó xuất hiện thường xuyên sau lỗi mạng, khiến dữ liệu profiling trước đây không còn đại diện; hãy đặt tình huống kiểm chứng tối ưu suy đoán.
Một dịch vụ sử dụng reflection trong đường xử lý nóng và nhóm giả định JIT không thể tối ưu bất kỳ lời gọi reflection nào, nhưng số liệu thực tế không đồng nhất; hãy đặt tình huống đánh giá thay vì suy đoán.
Một hệ thống thay đổi phiên bản JDK và hiệu năng tăng ở một số endpoint nhưng giảm ở endpoint khác, trong khi source code giữ nguyên; hãy xây dựng tình huống so sánh JIT, GC và thư viện runtime.
Một phương thức được gọi qua JNI nhiều lần trong một request và trở thành nút nghẽn dù phần mã native chạy rất nhanh; hãy đặt tình huống phân tích chi phí đi qua ranh giới JVM.
Một dịch vụ lập trình viên thay đổi cấu trúc object để giảm nhánh nhưng CPU profile cho thấy tác động trái ngược khi call site chuyển từ đơn hình sang đa hình; hãy đặt tình huống kiểm chứng.
Một batch job dùng biểu thức toán học phức tạp và mất nhiều thời gian khi chạy lần đầu, nhưng sau warmup hiệu năng tăng mạnh; hãy đặt tình huống định nghĩa điểm đo có ý nghĩa.
Một bộ benchmark chỉ chạy một phép đo mỗi phiên JVM và so sánh kết quả của hai thuật toán, khiến ảnh hưởng của JIT, cache và GC không được tách; hãy xây dựng tình huống đánh giá độ tin cậy.
Một ứng dụng đo CPU rất cao sau khi bật Java agent quan sát bytecode, nhưng nhóm chưa phân biệt chi phí instrumentation với chi phí chạy mã đã được JIT tối ưu; hãy đặt tình huống chẩn đoán.
Một hệ thống sử dụng nhiều method handle và invokedynamic, khiến hành vi runtime thay đổi sau khi cập nhật liên kết tại call site; hãy đặt tình huống xác minh bằng dữ liệu biên dịch và thực thi.
Một nhóm giảm số lần tạo object nhưng throughput lại giảm do vô tình làm mất cơ hội inlining hoặc tối ưu của HotSpot; hãy đặt bài toán đánh giá tác động toàn hệ thống.
Một chương trình có vòng lặp không đồng bộ đọc cờ dừng từ luồng khác nhưng đôi khi không kết thúc dù luồng kia đã đổi giá trị; hãy xây dựng tình huống kiểm chứng tính hiển thị bộ nhớ.
Một API cập nhật số lượt truy cập bằng phép cộng trên biến chia sẻ và kết quả nhỏ hơn tổng request khi chạy song song; hãy đặt tình huống phân tích thao tác nguyên tử.
Một dịch vụ đồng bộ hóa bằng một monitor duy nhất cho nhiều tài nguyên không liên quan, khiến throughput giảm khi tăng số request đồng thời; hãy xây dựng tình huống đánh giá lock contention.
Một nhóm báo cáo deadlock giữa hai luồng khóa hai tài nguyên theo thứ tự ngược nhau, nhưng các thread dump chỉ được lấy sau khi ứng dụng restart; hãy đặt tình huống thiết kế chẩn đoán.
Một ứng dụng dùng wait và notify để điều phối producer-consumer nhưng đôi khi bỏ lỡ tín hiệu và treo dù hàng đợi có dữ liệu; hãy đặt tình huống kiểm chứng điều kiện chờ.
Một luồng đang wait trên monitor được đánh thức nhưng điều kiện nghiệp vụ chưa thỏa, khiến nó xử lý dữ liệu sai; hãy xây dựng tình huống đánh giá khả năng thức dậy không gắn với điều kiện.
Một đối tượng cấu hình được công bố từ một thread sang thread khác trước khi hoàn tất khởi tạo, làm một số trường được quan sát ở trạng thái chưa hợp lệ; hãy đặt tình huống kiểm chứng safe publication.
Một nhóm dùng double-checked locking cho singleton nhưng chưa đối chiếu các bảo đảm của Java Memory Model về thứ tự đọc ghi; hãy đặt tình huống đánh giá an toàn bộ nhớ.
Một ứng dụng dùng final field trong object bất biến và nhóm cho rằng mọi tham chiếu tới object đó đều luôn được công bố an toàn bất kể cách xây dựng; hãy đặt tình huống kiểm chứng điều kiện khởi tạo.
Một tác vụ bị hủy bằng interrupt nhưng thread vẫn tiếp tục giữ lock và xử lý I/O vì thư viện nuốt trạng thái interrupt; hãy xây dựng tình huống đánh giá cơ chế hủy.
Một API sử dụng AtomicInteger để cập nhật bộ đếm nhưng vẫn xảy ra sai lệch khi cần đồng thời cập nhật hai trường liên quan; hãy đặt tình huống phân biệt atomicity cục bộ và bất biến tổng thể.
Một chương trình sử dụng compare-and-set lặp lại khi tranh chấp cao và CPU tăng mạnh dù không có luồng nào bị block trên monitor; hãy xây dựng tình huống kiểm tra contention.
Một ứng dụng có nhiều luồng sửa các trường nằm gần nhau trong bộ nhớ, khiến throughput không tăng khi thêm CPU dù các trường không chia sẻ logic; hãy đặt bài toán đánh giá false sharing.
Một dịch vụ dùng ThreadLocal để gắn thông tin người dùng, nhưng thread pool tái sử dụng luồng cho nhiều request nên có hiện tượng rò rỉ dữ liệu ngữ cảnh; hãy đặt tình huống kiểm tra cô lập.
Một ứng dụng chuyển sang virtual threads nhưng vẫn cấp phát ThreadLocal lớn cho từng tác vụ và bộ nhớ tăng mạnh dưới tải; hãy đặt tình huống đánh giá mô hình lưu trạng thái theo luồng.
Một hệ thống dùng virtual threads để gọi dịch vụ bên ngoài nhưng tài nguyên downstream chỉ cho phép ít kết nối đồng thời, khiến timeout tăng dù JVM tạo luồng rất nhanh; hãy đặt tình huống kiểm chứng giới hạn tài nguyên.
Một nhóm cho rằng virtual thread luôn bị pin khi vào synchronized block mà không xét phiên bản JDK đang triển khai, dẫn đến nhận định hiệu năng sai; hãy xây dựng tình huống đối chiếu hành vi theo runtime.
Một dịch vụ chuyển từ platform threads sang virtual threads nhưng vẫn dùng semaphore cho truy cập cơ sở dữ liệu và không thấy tăng throughput; hãy đặt tình huống đánh giá giới hạn xử lý.
Một ứng dụng dùng ForkJoinPool chung cho tính toán và thao tác I/O chặn lâu, khiến một số tác vụ CPU bị đói tài nguyên; hãy xây dựng tình huống kiểm tra lịch thực thi.
Một chương trình có hàng đợi executor không giới hạn, và dưới tải kéo dài hàng đợi tăng nhanh trong khi số worker không thay đổi; hãy đặt tình huống đánh giá áp lực bộ nhớ và độ trễ.
Một hệ thống dùng CompletableFuture kết hợp nhiều nguồn dữ liệu, nhưng một nhánh hoàn tất lỗi khiến các tác vụ khác vẫn chiếm tài nguyên lâu; hãy xây dựng tình huống kiểm chứng vòng đời tác vụ.
Một luồng Java đọc biến trạng thái được cập nhật từ thiết bị qua callback native, nhưng dữ liệu không được quan sát nhất quán giữa các CPU core; hãy đặt tình huống đánh giá quy tắc đồng bộ.
Một ứng dụng chạy parallel stream trên common pool, trong khi thư viện khác cũng dùng pool này cho công việc nền khiến p99 latency biến động; hãy xây dựng tình huống đánh giá cạnh tranh tài nguyên.
Một nhóm sử dụng nhiều volatile field để cập nhật các phần của cùng một cấu hình và cho rằng người đọc sẽ luôn thấy toàn bộ phiên bản nhất quán; hãy đặt bài toán kiểm chứng tính nguyên tử của nhóm thay đổi.
Một hệ thống dùng VarHandle với các chế độ truy cập bộ nhớ khác nhau giữa producer và consumer nhưng chưa có test chịu tải, khiến lỗi hiếm xuất hiện khi chạy trên máy nhiều lõi; hãy xây dựng tình huống xác minh.
Một ứng dụng đồng bộ hóa bằng lock có thứ tự công bằng và nhận thấy throughput thấp hơn dưới tải nặng, trong khi mục tiêu ban đầu là tránh luồng bị bỏ đói; hãy đặt tình huống đánh giá tradeoff.
Một thread pool xử lý request có nhiều công việc dài, khiến tác vụ ưu tiên cao bị xếp hàng dù CPU còn trống trên một số lõi; hãy đặt tình huống phân tích lập lịch và queue.
Một ứng dụng đánh giá concurrency qua test chỉ chạy trên một CPU core và không tái hiện data race xuất hiện trong production nhiều lõi; hãy xây dựng tình huống thiết kế phép thử đa luồng.
Một hệ thống gọi synchronized method từ nhiều endpoint và thấy các luồng ở trạng thái BLOCKED trong thread dump, nhưng nhóm nhầm lẫn với trạng thái WAITING; hãy đặt tình huống diễn giải trạng thái luồng.
Một nhóm dùng synchronized để bảo vệ cache nhưng thực hiện gọi mạng bên trong vùng khóa, khiến toàn bộ request xếp hàng khi backend chậm; hãy đặt tình huống phân tích thời gian giữ monitor.
Một chương trình có lỗi liveness chỉ xuất hiện khi một thread giữ lock và chờ CompletableFuture chạy trên executor cũng đang cần lock đó; hãy xây dựng tình huống kiểm chứng vòng phụ thuộc.
Một ứng dụng ghi nhận nhiều virtual thread đang chờ I/O nhưng CPU thấp, trong khi đội vận hành cho rằng số thread lớn đồng nghĩa CPU đã quá tải; hãy đặt tình huống đánh giá chỉ số thread.
Một tiến trình JVM dùng nhiều luồng ngắn hạn và nhận thấy chi phí context switching cao khi áp dụng platform threads cho mỗi request; hãy đặt tình huống phân tích ảnh hưởng hệ điều hành.
Một ứng dụng cập nhật cấu hình qua một immutable snapshot nhưng nhóm đọc từng trường từ các snapshot khác nhau trong cùng request, khiến kết quả nghiệp vụ không nhất quán; hãy đặt tình huống kiểm chứng việc công bố trạng thái.
Một service Java tăng CPU lên gần 100% sau deploy nhưng thread dump chỉ được lấy khi hết tải, khiến đội vận hành không xác định được method nóng; hãy đặt tình huống lựa chọn thời điểm thu thập profiling.
Một ứng dụng gặp deadlock hiếm khi hai batch job chạy đồng thời, nhưng dashboard chỉ báo request timeout mà không có dữ liệu trạng thái monitor; hãy xây dựng tình huống thu thập thread dump phù hợp.
Một dịch vụ xử lý nhanh trên staging nhưng production bị GC pause dài theo chu kỳ, trong khi logs chưa bật dữ liệu GC chi tiết; hãy đặt tình huống thiết kế quan sát có thể đối chiếu với request.
Một ứng dụng bị OOM kill bởi Kubernetes mà không xuất hiện Java OutOfMemoryError hoặc heap dump, khiến nhóm không thể kết luận heap leak; hãy đặt tình huống phân biệt lớp quản lý bộ nhớ.
Một hệ thống ghi nhận native memory tăng sau mỗi lần tải file qua JNI, nhưng heap histogram ổn định; hãy xây dựng tình huống xác định công cụ đo tài nguyên ngoài heap.
Một nhóm bật Native Memory Tracking chỉ khi hệ thống đã gần cạn bộ nhớ và muốn so sánh với mốc baseline từ trước lúc khởi động; hãy đặt tình huống đánh giá điều kiện sử dụng số liệu.
Một ứng dụng sản xuất dùng JFR để theo dõi allocation và lock contention nhưng bản ghi quá ngắn nên không bắt được spike xảy ra mỗi giờ; hãy xây dựng tình huống thiết kế thời gian quan sát.
Một dịch vụ yêu cầu phân tích allocation hotspot nhưng nhóm chỉ thu CPU sampling và không nhìn thấy phương thức tạo nhiều object ngắn hạn; hãy đặt tình huống lựa chọn chỉ số chẩn đoán.
Một ứng dụng có mức tải cao và heap dump lớn, khiến thao tác thu thập dữ liệu làm tăng pause và có nguy cơ ảnh hưởng SLA; hãy đặt tình huống đánh giá phương pháp điều tra phù hợp.
Một tổ chức lưu các bản JFR có chứa tên request, thông tin người dùng và đường dẫn nhạy cảm trên kho chia sẻ công khai; hãy đặt tình huống kiểm chứng an toàn artifact chẩn đoán.
Một dịch vụ có Java process đã restart sau crash và chỉ còn file hs_err từ lần trước, trong khi nhóm muốn phân tích lỗi native xảy ra trước khi JVM thoát; hãy đặt tình huống đánh giá dấu vết còn lại.
Một đội vận hành thay đổi cờ JVM để tối ưu trong production nhưng chưa kiểm tra cờ có còn được hỗ trợ và giá trị thực tế sau khi khởi động; hãy đặt tình huống kiểm chứng cấu hình.
Một service dùng CPU quota thấp trong container và được giám sát theo phần trăm CPU host, khiến đội phân tích đánh giá sai mức nghẽn; hãy xây dựng tình huống lựa chọn thước đo tài nguyên.
Một ứng dụng có GC log chỉ ghi thời điểm tương đối kể từ khi JVM khởi động, trong khi log HTTP dùng thời gian thực nên khó đối chiếu pause với request; hãy đặt tình huống chuẩn hóa mốc thời gian.
Một nhóm dùng jcmd để lấy thống kê class loading và thread trong production nhưng chưa có tiêu chí nhận biết số lượng tăng bất thường; hãy đặt tình huống xây dựng bộ chỉ số theo thời gian.
Một ứng dụng chạy Java ở các node có cấu trúc NUMA khác nhau và hiệu năng truy cập bộ nhớ biến động theo nơi container được đặt; hãy xây dựng tình huống kiểm chứng tính tương đồng phần cứng.
Một dịch vụ sử dụng rất nhiều socket nhưng số file descriptor hệ điều hành gần chạm giới hạn, khiến lỗi request tăng dù heap và CPU bình thường; hãy đặt tình huống phân biệt cạn tài nguyên OS.
Một đội thu heap histogram trong giờ cao điểm và thấy rất nhiều object của một kiểu phổ biến, nhưng chưa biết chúng thuộc cache hay request đang xử lý; hãy đặt tình huống kiểm tra đường giữ đối tượng.
Một ứng dụng mới bật Class Data Sharing để giảm công việc nạp lớp nhưng kết quả khởi động thay đổi theo cách đóng gói JAR và môi trường runtime; hãy đặt tình huống đánh giá điều kiện đo.
Một tổ chức muốn giảm startup của ứng dụng Java bằng cách thay nhiều tùy chọn JVM cùng lúc, khiến không thể xác định tác động riêng của CDS, JIT và heap; hãy đặt bài toán thiết kế thực nghiệm.
Một hệ thống nâng cấp JDK làm hành vi GC, JIT và class loading thay đổi, nhưng nhóm chỉ chạy unit test và chưa có baseline hiệu năng hay bộ nhớ; hãy xây dựng tình huống kiểm chứng phát hành.
Một nền tảng cần phân biệt lỗi được đặc tả JVM bảo đảm với tối ưu riêng của HotSpot, nhưng tài liệu đào tạo nội bộ coi mọi cờ và vùng nhớ HotSpot là chuẩn bắt buộc; hãy đặt tình huống đánh giá tính chính xác.
Một dịch vụ đa vùng dùng cùng cấu hình JVM trên máy giới hạn CPU và bộ nhớ rất khác nhau, khiến tỷ lệ request timeout chênh lệch lớn giữa các vùng; hãy đặt tình huống xác định yếu tố tài nguyên.
Một ứng dụng latency-sensitive được tối ưu qua benchmark trên máy trống nhưng chạy production cùng nhiều container khác, khiến CPU throttling và GC tranh chấp làm mất lợi ích; hãy xây dựng tình huống đánh giá điều kiện đo.
Một bộ kiểm thử hiệu năng chạy với dữ liệu nhỏ và heap lớn nên không phát hiện pause và memory pressure chỉ xuất hiện khi dữ liệu thực tăng lên hàng triệu bản ghi; hãy đặt tình huống thiết kế tập tải đại diện.
Một đội vận hành muốn chứng minh thay đổi từ platform threads sang virtual threads giúp tiết kiệm bộ nhớ nhưng không làm giảm tính đúng của phân quyền và dữ liệu request; hãy xây dựng tình huống lập tiêu chí nghiệm thu.
Một dịch vụ thường xuyên bị lỗi OutOfMemoryError, deadlock và thời gian khởi động dài sau nhiều bản nâng cấp, nhưng chưa có quy trình kết hợp heap, thread, GC, JIT và môi trường container; hãy đặt tình huống xây dựng phương pháp điều tra.
