Câu 1: Một Stream cần biến đổi các phần tử thành nhóm ngay giữa pipeline; API nào phù hợp?
A. Stream.gather dùng Gatherer làm phép biến đổi trung gian.
B. Stream.collect thêm bước trung gian có trạng thái vào pipeline.
C. Stream.reduce tạo Stream mới cho các bước tiếp theo.
D. Stream.forEach trả pipeline mới để tiếp tục các bước xử lý.
Đáp án đúng: A

Câu 2: Cần gom log thành nhóm liên tiếp tối đa ba item không chồng lấp; dùng gì?
A. Gatherers.scan(...) tạo nhóm ba sau mỗi lần cộng dồn.
B. Gatherers.windowFixed(3) tạo nhóm tối đa ba phần tử.
C. Gatherers.fold(...) tạo nhóm mới sau mỗi item đọc được.
D. Gatherers.windowSliding(3) tạo nhóm ba không chồng lấp.
Đáp án đúng: B

Câu 3: Cần cửa sổ ba phép đo chồng lấp và dịch một mẫu mỗi lần; chọn gì?
A. Collectors.toList() chia nguồn thành các cửa sổ trượt.
B. Gatherers.windowFixed(3) phát cửa sổ dịch một phần tử.
C. Gatherers.windowSliding(3) phát các cửa sổ chồng lấp.
D. Gatherers.fold(...) phát cửa sổ ba item theo từng bước.
Đáp án đúng: C

Câu 4: Muốn phát tổng tích lũy sau từng bản ghi trong Stream, dùng gì?
A. Gatherers.fold(...) phát mọi trạng thái khi tích lũy.
B. Gatherers.windowFixed(...) tự tính tổng mọi bản ghi cũ.
C. Gatherers.mapConcurrent(...) tự tính các tổng trung gian.
D. Gatherers.scan(...) phát trạng thái tích lũy từng bước.
Đáp án đúng: D

Câu 5: Một pipeline chỉ cần kết quả gộp cuối cùng; Gatherer nào thích hợp?
A. Gatherers.fold(...) phát giá trị tích lũy cuối cùng.
B. Gatherers.windowSliding(...) giảm nguồn về một giá trị.
C. Gatherers.mapConcurrent(...) tự trả một giá trị cuối duy nhất.
D. Gatherers.scan(...) chỉ phát kết quả sau lúc hoàn tất.
Đáp án đúng: A

Câu 6: Mapper thực hiện I/O và cần giới hạn tám tác vụ đồng thời; nên dùng gì?
A. Gatherers.scan(...) luôn chạy đồng thời tám mapper.
B. Gatherers.windowFixed(8) giới hạn concurrency của I/O.
C. Gatherers.mapConcurrent(8, ...) giới hạn ánh xạ đồng thời.
D. Gatherers.fold(...) dùng executor tối đa tám luồng mặc định.
Đáp án đúng: C

Câu 7: Custom Gatherer cần state riêng khi pipeline được đánh giá; thành phần nào tạo nó?
A. Finisher tạo state trước lúc nhận phần tử đầu tiên.
B. Combiner tạo state mỗi khi integrator nhận phần tử.
C. Initializer khởi tạo state cho lượt chạy Gatherer.
D. Downstream tạo state trước khi initializer chạy.
Đáp án đúng: C

Câu 8: Một pipeline có gatherer nhưng chưa có terminal operation; điều gì đúng?
A. Gatherer tự tạo List trước khi terminal operation chạy.
B. Stream khởi tạo executor để chạy Gatherer nền.
C. Gatherer đọc toàn nguồn ngay khi được gắn vào pipeline.
D. Phép biến đổi có thể chưa được thực thi do tính lazy.
Đáp án đúng: D

Câu 9: Gatherer muốn gộp state khi chạy parallel; thành phần nào hỗ trợ?
A. Integrator tự hợp nhất mọi state không cần thành phần khác.
B. Initializer tự gộp state của mọi worker khi hoàn tất.
C. Finisher chia sẻ một state mutable giữa các threads.
D. Combiner chịu trách nhiệm hợp nhất state từ các phần.
Đáp án đúng: D

Câu 10: Một phần tử nguồn không được custom Gatherer phát xuống dưới; điều gì hợp lệ?
A. Gatherer phải phát đúng một output cho mỗi input.
B. Phần tử đó có thể không xuất hiện ở Stream kết quả.
C. Phần tử được thay bằng null để giữ số lượng đầu ra.
D. Pipeline lập tức kết thúc khi một input không phát ra.
Đáp án đúng: B

Câu 11: Tool cần đọc file .class mà không muốn JVM nạp lớp; dùng gì?
A. MethodHandles tự trích toàn bộ thuộc tính class file.
B. Class-File API đọc được cấu trúc class file.
C. ClassLoader.getResourceAsStream tự tạo ClassModel từ bytes.
D. Class.forName parse bytecode mà không phải nạp class.
Đáp án đúng: B

Câu 12: Một framework muốn sinh class bytes bằng API chuẩn Java 24; chức năng nào đúng?
A. Class-File API tự chạy lớp trước khi tạo class bytes.
B. Class-File API biên dịch class bytes thành native image.
C. Class-File API hỗ trợ xây dựng và ghi class file.
D. Class-File API cần tạo instance trước rồi sinh class file.
Đáp án đúng: C

Câu 13: Cần xem fields và methods từ file .class; model nào phù hợp?
A. ClassModel biểu diễn các thành phần của class file.
B. Reflection Class.getMethods phân tích code attributes.
C. MethodHandles.Lookup đọc trực tiếp mô hình file .class.
D. ClassLoader.getDefinedPackages liệt kê fields của class.
Đáp án đúng: A

Câu 14: Khi parse class bytes bằng Class-File API, static initializer có phải chạy không?
A. Có; class loader cần define class trước khi đọc file.
B. Không; phân tích class file không cần khởi tạo lớp.
C. Không; parser loại bỏ toàn bộ static initializer.
D. Có; static initializer phải chạy trước khi parser trả kết quả.
Đáp án đúng: B

Câu 15: Class sinh ở JDK 24 không tải được trên JDK 17; cần kiểm tra gì?
A. Major version của file class so với JVM đích.
B. Tên thư mục workspace có trùng tên Java package không.
C. Phần mở rộng của JAR có hợp với Windows hoặc Linux không.
D. Line endings của mã nguồn trước khi build có khác không.
Đáp án đúng: A

Câu 16: Sau transformation, annotation method bị mất; điều gì cần xem xét?
A. Class loader có tự khôi phục annotation sau khi load không.
B. JIT có tạo lại annotation sau khi method chạy không.
C. Có giữ metadata và attributes khi ghi class mới không.
D. GC có thu hồi annotation trước khi reflection đọc không.
Đáp án đúng: C

Câu 17: Muốn đọc requires và exports đã biên dịch trong module-info.class, dùng gì?
A. ModuleDescriptor tự ghi class file mới khi được đọc.
B. Class-File API có thể phân tích metadata module.
C. jdeps tự tạo module-info.class mỗi lần phân tích class.
D. ModuleLayer tự phân tích bytes của mọi module descriptor.
Đáp án đúng: B

Câu 18: Một plugin parse bằng Class-File API thành công; có thể kết luận an toàn thực thi không?
A. Không; API không thể đọc method của các lớp.
B. Không; parse hợp lệ không bảo đảm plugin an toàn.
C. Có; parser tự hạn chế quyền truy cập khi plugin chạy.
D. Có; class hợp lệ không thể thực hiện I/O nguy hiểm.
Đáp án đúng: B

Câu 19: Transformer sinh bytecode nhưng khi nạp lớp gặp VerifyError; nên kiểm tra gì?
A. Kiểm tra bytecode và metadata stack được tạo.
B. Chỉ cần --add-opens để JVM bỏ qua verification lỗi.
C. Chỉ cần đổi --release, không phải kiểm tra stack maps.
D. Chỉ cần tăng heap để bytecode vừa tạo được verifier.
Đáp án đúng: A

Câu 20: Multi-release JAR có thể chứa bản class riêng theo JDK; cần làm gì?
A. Chỉ dùng bản class ở thư mục gốc của JAR.
B. Để parser tự bỏ mọi class nằm ở thư mục versions.
C. Luôn lấy class file có major version thấp nhất.
D. Chọn đúng class variant cho runtime đích.
Đáp án đúng: D

Câu 21: Java 24 cải thiện điều gì ở virtual thread khi dùng synchronized?
A. Cấm virtual thread thực hiện synchronized method.
B. Bỏ cơ chế mutual exclusion của synchronized.
C. Giảm pinning do monitor trên các đường chờ.
D. Gắn một carrier cố định với mọi virtual thread.
Đáp án đúng: C

Câu 22: Có cần thay mọi synchronized bằng ReentrantLock chỉ để tránh pinning ở Java 24?
A. Có; synchronized vẫn giữ carrier mỗi lần chờ.
B. Có; synchronized không còn hỗ trợ virtual threads.
C. Không; Java 24 giảm pinning do monitor.
D. Không; ReentrantLock đã bị loại khỏi JDK.
Đáp án đúng: C

Câu 23: Virtual thread đang gọi hàm native bị blocking lâu; rủi ro nào còn có?
A. Chỉ monitor mới có thể pin virtual thread.
B. Native call đổi virtual thread thành platform thread.
C. Java 24 unmount ngay mọi native call đang chờ.
D. Native blocking vẫn có thể làm pin carrier thread.
Đáp án đúng: D

Câu 24: Nhiều request HTTP chủ yếu chờ I/O; virtual threads hữu ích nhất ở điểm nào?
A. Tự cache mọi phản hồi HTTP ở cấp carrier.
B. Làm phép tính CPU nhanh hơn theo số virtual threads.
C. Loại bỏ timeout của các socket thuộc hệ điều hành.
D. Duy trì nhiều tác vụ chờ I/O trên ít carriers.
Đáp án đúng: D

Câu 25: Tác vụ CPU-bound được chạy bằng hàng triệu virtual threads; kỳ vọng nào đúng?
A. JVM dành một core riêng cho mỗi virtual thread.
B. Vẫn bị giới hạn bởi core CPU và workload.
C. Mọi phép toán CPU tự chuyển sang non-blocking I/O.
D. Virtual thread không được phép chạy code thuần CPU.
Đáp án đúng: B

Câu 26: Khi nhiều virtual threads cùng chờ monitor, điều gì vẫn đúng?
A. Monitor không thể đồng thời dùng cho platform thread.
B. Monitor vẫn bảo đảm mutual exclusion.
C. Mỗi virtual thread tự có bản sao riêng của monitor.
D. Mọi virtual threads đều được vào vùng khóa song song.
Đáp án đúng: B

Câu 27: Service vẫn chậm sau khi giảm monitor pinning; nên điều tra gì?
A. Chỉ tăng carrier count mà không đo contention thực tế.
B. Kết luận mọi synchronized vẫn luôn pin carrier.
C. Chỉ tăng số virtual threads để bỏ hết thời gian chờ.
D. Xem native calls và contention còn tồn tại.
Đáp án đúng: D

Câu 28: ThreadLocal chứa bộ đệm lớn cho mỗi virtual thread; Java 24 có xóa chi phí này không?
A. Có; JVM tự gộp ThreadLocal thành buffer dùng chung.
B. Có; unmount sẽ tự động xóa mọi giá trị ThreadLocal.
C. Không; Java 24 cấm ThreadLocal với virtual threads.
D. Không; dữ liệu ThreadLocal vẫn được giữ.
Đáp án đúng: D

Câu 29: Đo hiệu quả virtual threads sau nâng JDK; nhóm metric nào phù hợp?
A. Đo carrier usage, throughput và latency.
B. Chỉ CPU lúc build mà không đo latency tại runtime.
C. Chỉ số thread tạo mới, bỏ qua mức độ chờ của task.
D. Chỉ tổng số virtual threads, không đo carrier blocking.
Đáp án đúng: A

Câu 30: Sau cải tiến monitor, virtual thread vẫn chờ khóa lâu; giải thích nào đúng?
A. Giảm pinning không đồng nghĩa xóa lock contention.
B. Platform thread không thể tranh chấp monitor.
C. Monitor không còn duy trì trạng thái khóa ở Java 24.
D. Mỗi virtual thread có lock riêng không chia sẻ.
Đáp án đúng: A

Câu 31: Service startup chậm do nạp nhiều class; tính năng Java 24 nào phù hợp?
A. CDS cache tự tối ưu mọi hot method trước khi chạy.
B. AOT cache tự tạo native executable từ mọi class.
C. JIT profile cache giữ mọi class của plugin chưa tải.
D. AOT Class Loading & Linking hỗ trợ cache việc nạp lớp.
Đáp án đúng: D

Câu 32: Khi training để tạo AOT cache, workload nào phù hợp?
A. Dùng workload khởi động đại diện thực tế.
B. Chỉ gọi một helper không thuộc startup flow chính.
C. Chỉ đo kích thước heap khi service chưa khởi động.
D. Chỉ chạy java -version để tải toàn bộ lớp ứng dụng.
Đáp án đúng: A

Câu 33: Dependency của ứng dụng thay đổi sau lúc tạo AOT cache; điều gì nên làm?
A. Chỉ đổi tên cache theo tên bản release là đủ.
B. JVM luôn tự thêm class mới vào cache lúc startup.
C. Xác minh cache có còn hợp với classpath mới.
D. AOT cache không phụ thuộc classpath và dependency.
Đáp án đúng: C

Câu 34: AOT Class Loading & Linking có tạo native executable độc lập không?
A. Không; ứng dụng vẫn cần JVM và có thể dùng cache.
B. Có; ứng dụng không còn cần Java runtime khi chạy.
C. Có; mọi method được dịch thành mã máy trong AOT.
D. Không; tính năng chỉ tồn tại trong compiler javac.
Đáp án đúng: A

Câu 35: Đánh giá lợi ích AOT class loading, metric nào trực tiếp nhất?
A. Đo cold startup đến khi service sẵn sàng.
B. Kích thước public key của crypto provider.
C. Số phần tử được Gatherer phát trong pipeline.
D. Số lần hashCode chạy sau nhiều giờ xử lý.
Đáp án đúng: A

Câu 36: Một plugin chưa từng được nạp khi training AOT cache; điều gì có thể xảy ra?
A. Plugin không thể hoạt động nếu không có trong cache.
B. Plugin chắc chắn đã được AOT cache nạp sẵn.
C. JVM tự sinh một cache riêng cho plugin khi chạy.
D. Đường nạp plugin không được cache bao phủ.
Đáp án đúng: D

Câu 37: Nếu không đóng gói AOT cache vào production image, hệ quả có thể là gì?
A. Ứng dụng không thể chạy nếu thiếu cache tùy chọn.
B. JVM tự tải cache từ vendor bằng HTTP khi cần.
C. Có thể mất lợi ích tăng tốc startup.
D. Mọi class chỉ có thể chạy bằng interpreter.
Đáp án đúng: C

Câu 38: Cache AOT được tạo với JDK khác môi trường production; cần kiểm tra gì?
A. Chỉ tên package của mỗi lớp trong cache AOT.
B. Chỉ CPU quota của máy được dùng làm training.
C. Chỉ tên file cache mà không so JDK và classpath.
D. Tính tương thích của cache với build và runtime.
Đáp án đúng: D

Câu 39: AOT Class Loading & Linking khác JIT ở điểm nào?
A. AOT tối ưu nạp lớp; JIT tối ưu mã chạy.
B. AOT tạo executable, JIT chỉ tạo tệp JAR.
C. AOT chỉ tối ưu hot methods, JIT chỉ quản lý modules.
D. AOT thay thế class loader, JIT chỉ xử lý JSON input.
Đáp án đúng: A

Câu 40: Service có p99 cao sau khi chạy nhiều giờ; có nên mặc định dùng AOT cache không?
A. Có; AOT luôn tăng tốc mọi phép tính CPU của ứng dụng.
B. Chưa; cần đo bottleneck tại steady state.
C. Có; cache lớn hơn sẽ loại mọi độ trễ network.
D. Không; AOT luôn làm throughput giảm trong mọi workload.
Đáp án đúng: B

Câu 41: ML-KEM trong Java 24 phục vụ mục đích mật mã nào?
A. Mã hóa đối xứng tập tin bằng AES-GCM.
B. Dẫn xuất password bằng hàm memory-hard.
C. Tạo chữ ký số bằng private signing key.
D. Key encapsulation dùng để trao đổi bí mật phiên.
Đáp án đúng: D

Câu 42: ML-DSA trong Java 24 hỗ trợ nhu cầu nào?
A. Dẫn xuất mật khẩu yếu thành private key.
B. Thỏa thuận shared secret qua key encapsulation.
C. Tạo và kiểm tra chữ ký số hậu lượng tử.
D. Mã hóa dữ liệu phiên bằng thuật toán AES-GCM.
Đáp án đúng: C

Câu 43: API mật mã Java nào dùng để thực hiện ML-KEM?
A. java.security.Signature cho key encapsulation.
B. java.security.MessageDigest cho encapsulation bytes.
C. javax.crypto.KEM cho encapsulate và decapsulate.
D. javax.crypto.Cipher để ký các message bằng ML-KEM.
Đáp án đúng: C

Câu 44: Để xác minh ML-DSA signature trong Java, dùng API nào?
A. java.security.MessageDigest để giải mã signature.
B. RandomGenerator có seed để đối chiếu dữ liệu.
C. javax.crypto.KEM cùng public key để verify chữ ký.
D. java.security.Signature cùng public key của bên ký.
Đáp án đúng: D

Câu 45: Bên nhận file cập nhật có ML-DSA signature cần những gì?
A. Nội dung đã ký, chữ ký và public key được tin cậy.
B. Seed dùng tạo dữ liệu demo trong CI của bản build.
C. Private key của mọi client đã tải artifact.
D. Shared secret ML-KEM dùng trong phiên hiện tại.
Đáp án đúng: A

Câu 46: Trong ML-KEM, bên gửi encapsulate bằng khóa nào của bên nhận?
A. Private key của bên nhận; phía nhận dùng public key.
B. Cùng public key cho cả encapsulation và decapsulation.
C. Public key của bên nhận; phía nhận decapsulate bằng private key.
D. Cùng private key được chia sẻ cho mọi bên tham gia.
Đáp án đúng: C

Câu 47: Sau khi ML-KEM tạo shared secret, ứng dụng cần làm gì tiếp?
A. Dùng secret trong một giao thức bảo vệ dữ liệu phù hợp.
B. ML-KEM tự xác minh danh tính server từ shared secret.
C. ML-KEM tự tạo chữ ký số cho mỗi HTTP message.
D. Mọi payload tự động được ML-KEM mã hóa ngay khi tạo secret.
Đáp án đúng: A

Câu 48: Encapsulation data ML-KEM được gửi cho phía nhận với vai trò gì?
A. Giúp phía nhận tái lập cùng shared secret.
B. Chứa ciphertext của toàn bộ payload ứng dụng.
C. Giúp xác minh signature mà không cần public key.
D. Là bản sao public key để thay cho private key.
Đáp án đúng: A

Câu 49: JDK có ML-KEM thì tất cả TLS tự động dùng hậu lượng tử không?
A. Có; JVM tự thay mọi TLS key exchange bằng ML-KEM.
B. Có; TLS provider cũ bị vô hiệu khi Java 24 khởi động.
C. Không; ML-KEM không thể dùng trong giao thức TLS.
D. Không; giao thức và đối tác phải hỗ trợ cùng thuật toán.
Đáp án đúng: D

Câu 50: Chữ ký ML-DSA hợp lệ có xác nhận luôn danh tính bên ký không?
A. Có; signature hợp lệ thay được cả chuỗi certificate.
B. Không; verifier bắt buộc biết private key của signer.
C. Không; public key cần được gắn với chủ thể tin cậy.
D. Có; public key ML-DSA luôn mang danh tính được xác thực.
Đáp án đúng: C

Câu 51: Benchmark hậu lượng tử cần đo những thông số nào?
A. Chỉ thời gian tải crypto provider lúc khởi động.
B. CPU và kích thước key, encapsulation, signature.
C. Chỉ throughput CPU mà bỏ kích thước key và chữ ký.
D. Chỉ kích thước của JAR cung cấp crypto provider.
Đáp án đúng: B

Câu 52: Dùng PRNG seed đoán được để sinh ML-DSA private key có rủi ro gì?
A. Signature tự trở thành hash không thể kiểm chứng.
B. JVM tự chuyển thuật toán từ ML-DSA sang RSA.
C. Khóa riêng có thể bị đoán do entropy không an toàn.
D. Key pair tự ghi vào mọi AOT cache của JVM.
Đáp án đúng: C

Câu 53: Hai JDK vendor dùng ML-KEM và cần giao tiếp; nên đối chiếu gì?
A. Provider, algorithm và encoding key/encapsulation.
B. Internal class name của provider luôn phải giống.
C. Chỉ cần so Object.hashCode giữa hai bên.
D. Các key pair phải giống nhau nếu JDK version trùng.
Đáp án đúng: A

Câu 54: ML-DSA có thay trực tiếp ML-KEM để thiết lập shared secret không?
A. Không; ML-KEM chỉ dùng để lưu key trong keystore.
B. Không; ML-DSA dùng chữ ký, ML-KEM dùng encapsulation.
C. Có; mọi chữ ký số đều tự sinh shared secret.
D. Có; signature có thể khôi phục private key đối tác.
Đáp án đúng: B

Câu 55: Service dùng ML-DSA ký artifact cần bảo vệ thành phần nào?
A. Public key xác minh phải được giữ bí mật.
B. Private signing key trong kho khóa với quyền hạn chế.
C. Signature phải được giấu để tránh bị sao chép.
D. Tên thuật toán phải bí mật để verifier tin cậy.
Đáp án đúng: B

Câu 56: Client cũ chưa hỗ trợ ML-KEM khi server nâng cấp; cần làm gì?
A. Giả định client cũ tự có ML-KEM khi server nâng.
B. Chia sẻ private key cho client cũ để decapsulate.
C. Thỏa thuận thuật toán và kiểm tra khả năng hỗ trợ hai bên.
D. Bỏ chứng thư vì ML-KEM đã thay mọi dạng xác thực.
Đáp án đúng: C

Câu 57: jlink trong Java 24 có cải tiến gì liên quan runtime image?
A. Có thể sinh class file trực tiếp từ JFR.
B. Có thể liên kết image mà không cần bộ JMOD riêng.
C. Có thể tạo native executable không phụ thuộc JVM.
D. Có thể dịch mọi thư viện C thành Java bytecode.
Đáp án đúng: B

Câu 58: Một runtime image tối giản thiếu module ứng dụng cần; nên kiểm tra gì?
A. Chỉ thứ tự imports trong mã Java nguồn.
B. Đồ thị module và API thực sự cần trong image.
C. Chỉ tên file README của bản release.
D. Chỉ collector được chọn trong IDE.
Đáp án đúng: B

Câu 59: Build trên Java 24 nhưng cần chạy ở Java 21; cần làm gì?
A. Dùng --release phù hợp và kiểm tra API trên runtime đích.
B. Thêm module import để JVM tự giảm class-file version.
C. Chỉ tắt JFR events để JVM cũ đọc được bytecode.
D. Đổi tên file JAR thành hậu tố Java 21 là đủ.
Đáp án đúng: A

Câu 60: Bytecode agent cũ không đọc class Java 24; cần rà soát gì?
A. Chỉ tên JAR, bỏ qua class-file version trong JAR.
B. Hỗ trợ class-file version và metadata mới của agent.
C. Chỉ tên class loader, bỏ qua major version.
D. Chỉ quyền reflective access của agent lúc chạy.
Đáp án đúng: B

Câu 61: Khi API mới còn ở preview trên Java 24, cách xử lý phù hợp là gì?
A. Coi preview là hợp đồng cố định cho mọi phiên bản JDK.
B. Xem bản chính thức và những thay đổi API trên JDK mới.
C. Bật preview cho mọi API đã chính thức trong Java 24.
D. Ghép preview nhiều bản JDK trong một JAR phát hành.
Đáp án đúng: B

Câu 62: Một service dùng Gatherers, Class-File API và ML-KEM; cần test nâng cấp gì?
A. Chỉ kết quả java -version ở máy developer.
B. Chỉ tạo AOT cache rồi coi mọi API tương thích.
C. Chỉ tổng số dòng source sau khi nâng cấp.
D. JDK tối thiểu, provider, tooling và hành vi runtime.
Đáp án đúng: D

Câu 63: Sau thay đổi virtual-thread pinning, điều gì vẫn cần test?
A. Chỉ số carrier mà bỏ thời gian lock contention.
B. Chỉ throughput mà bỏ kiểm tra tính đúng của lock.
C. Chỉ GC pause mà bỏ đường native blocking.
D. Thread safety và các đường native blocking còn lại.
Đáp án đúng: D

Câu 64: Ứng dụng nâng JDK và dependency cùng lúc, muốn xác định cải thiện từ đâu; nên làm gì?
A. Gộp các thay đổi rồi quy hết lợi ích cho JDK.
B. Chỉ so kích thước AOT cache sau hai phiên bản.
C. Tách các thay đổi khi đo để đánh giá riêng từng tác động.
D. Chỉ đo một lần startup rồi suy ra cả throughput.
Đáp án đúng: C
