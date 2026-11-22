# Chi phí đánh đổi về tính khả chuyển, độ an toàn, hiệu năng và vận hành khi Java tương tác với mã native

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao một ứng dụng Java chạy trên JVM vẫn có thể phụ thuộc vào hệ điều hành, CPU và ABI khi gọi thư viện native.
2. Phân biệt những bảo đảm của Java với rủi ro phát sinh ở ranh giới Java–native: quản lý bộ nhớ, con trỏ, luồng, lỗi và bảo mật.
3. Đánh giá hiệu năng **toàn tuyến** thay vì mặc định rằng mã C/C++ hoặc lời gọi native nhanh hơn Java.
4. Lập kế hoạch đóng gói, giám sát, nâng cấp và xử lý sự cố native library trong môi trường phát triển, CI/CD và production.
5. Chọn phương án hợp lý giữa Java thuần, JNI, Foreign Function & Memory API (FFM), thư viện binding bên thứ ba và giao tiếp với tiến trình ngoài.

## 1. Vì sao cần cân nhắc chi phí đánh đổi?

**Native interoperability** là việc mã Java tương tác với mã hoặc dữ liệu nằm ngoài môi trường thực thi Java được quản lý, chẳng hạn thư viện C/C++, API hệ điều hành, bộ giải mã chuyên dụng hay driver. Các cách thường gặp gồm:

- **JNI (Java Native Interface):** định nghĩa phương thức Java có từ khóa native và cài đặt tương ứng trong thư viện native; hỗ trợ tương tác hai chiều với JVM nhưng cần tuân thủ hợp đồng JNI.
- **FFM API:** API chuẩn thuộc gói java.lang.foreign, được hoàn thiện trong **JDK 22**; cho phép gọi hàm native và truy cập vùng nhớ ngoài heap qua các đối tượng mô tả hàm, layout và vòng đời bộ nhớ. FFM giảm một số rủi ro của cách thao tác con trỏ thủ công, nhưng **không thể bảo đảm mã C/C++ bên ngoài là an toàn**.
- **Binding như JNA:** thư viện bên thứ ba giúp gọi nhiều API native mà không phải tự viết lớp cầu nối JNI cho từng hàm; đổi lại có phụ thuộc thư viện và chi phí chuyển đổi/gọi.
- **Tiến trình riêng + IPC/HTTP/gRPC:** Java giao tiếp với chương trình native qua ranh giới tiến trình. Chi phí truyền dữ liệu lớn hơn, nhưng lỗi crash của chương trình native thường không làm sập trực tiếp JVM.

Lợi ích có thể là truy cập khả năng hệ điều hành chưa được Java cung cấp, tái sử dụng thư viện trưởng thành, hoặc dùng thuật toán/phần cứng chuyên dụng. Tuy nhiên, **tiện ích của một hàm native phải được so với toàn bộ chi phí vòng đời của nó**, không chỉ số dòng code hay thời gian thực thi một hàm.

Ví dụ, thay một thao tác Java thuần bằng lời gọi native để nhanh hơn 5% trong phép đo vi mô có thể không đáng nếu ứng dụng phải phát hành nhiều binary, có thêm lỗ hổng bộ nhớ và khó gỡ lỗi trong production.

## 2. Bốn trục đánh đổi chính

| Trục | Lợi ích có thể đạt | Chi phí/rủi ro cần trả |
| --- | --- | --- |
| **Tính khả chuyển** | Dùng API thiết bị/OS, thư viện thuật toán tối ưu theo CPU | Phụ thuộc OS, kiến trúc CPU, ABI, bộ thư viện hệ thống, phiên bản binary |
| **Độ an toàn** | Tiếp cận tài nguyên native và bộ nhớ trực tiếp | Con trỏ sai, vượt biên, use-after-free, double-free, data race, crash toàn JVM hoặc lỗ hổng an ninh |
| **Hiệu năng** | Tận dụng thư viện đã tối ưu, vector hóa, phần cứng hoặc giảm một số bản sao dữ liệu | Chi phí crossing, marshalling, copy/pin dữ liệu, cấp phát ngoài heap, lock, callback, startup |
| **Vận hành** | Tận dụng hệ sinh thái native có sẵn | Build đa nền tảng, phân phối binary, cấp quyền native access, cập nhật CVE, giám sát, rollback, debug |

Không có phương án nào thắng trên cả bốn trục. Một thiết kế đúng phải nêu rõ **mục tiêu cần đạt, ngưỡng chấp nhận rủi ro và bằng chứng đo lường**.

## 3. Tính khả chuyển: “Write once, run anywhere” có giới hạn

Mã bytecode Java thường di chuyển được giữa các nền tảng có JVM phù hợp. Nhưng **mã máy native được biên dịch cho một tổ hợp môi trường cụ thể**. Cần phân biệt ít nhất sáu yếu tố:

1. **Hệ điều hành:** Windows, Linux và macOS có loader, đường dẫn và API khác nhau. Tên thư viện thường có dạng DLL, SO hoặc dylib, nhưng tên file chỉ là một phần vấn đề.
2. **Kiến trúc CPU:** x86-64, AArch64/ARM64... có tập lệnh, quy ước gọi hàm và định dạng binary khác nhau.
3. **ABI (Application Binary Interface):** quy định cách truyền tham số, căn chỉnh, layout cấu trúc, kiểu dữ liệu và symbol. Hai bản build cùng CPU vẫn có thể không tương thích nếu ABI khác.
4. **Runtime native:** phiên bản libc, C++ runtime, thư viện hệ thống, dependency bậc hai; ví dụ môi trường Linux dùng glibc và musl không thể mặc nhiên dùng chung một binary.
5. **Hợp đồng dữ liệu:** kích thước kiểu C, signedness, endianness, alignment, encoding, struct packing và quyền sở hữu buffer phải được thống nhất với Java.
6. **Phiên bản JDK và chính sách native access:** Java API, chế độ module, tùy chọn JVM hoặc các hạn chế truy cập native có thể khác giữa phiên bản.

**Phân biệt quan trọng:** chuyển từ JNI sang FFM không biến thư viện C được biên dịch cho Linux x86-64 thành thư viện chạy trên Windows ARM64. FFM cải thiện cách viết cầu nối Java, còn binary native vẫn chịu ràng buộc nền tảng.

### Ví dụ về một ma trận hỗ trợ

Nếu sản phẩm cam kết chạy trên Windows x86-64, Linux x86-64 và Linux ARM64, tối thiểu phải trả lời:

| Môi trường | Artifact native | Kiểm chứng bắt buộc |
| --- | --- | --- |
| Windows x86-64 | Binary được build cho Windows x86-64 | Loader, dependency DLL, runtime C/C++, quyền truy cập |
| Linux x86-64 | Binary Linux x86-64 đúng libc/ABI | Dependency SO, version symbol, image container |
| Linux ARM64 | Binary Linux AArch64 tương thích | ABI, tập lệnh CPU, chức năng, hiệu năng thực tế |

Không thể coi “test thành công trên máy developer” là bằng chứng rằng cả ma trận hoạt động. Nếu thiếu binary cho một nền tảng, hãy **chặn cấu hình không được hỗ trợ** hoặc chuyển sang đường Java thuần đã kiểm chứng tương đương; không để lỗi chỉ xuất hiện sau khi nhận request.

### Giảm chi phí khả chuyển

- Giữ API Java ở phía ngoài của một adapter nhỏ; chỉ adapter biết JNI/FFM và cách tìm thư viện.
- Chuẩn hóa dữ liệu ở ranh giới: độ rộng số nguyên, thứ tự byte, encoding, ownership, xử lý null và mã lỗi.
- Có danh sách OS/architecture/ABI được hỗ trợ cùng test tự động; tránh chọn binary chỉ dựa trên chuỗi tên OS.
- Phát hành và kiểm tra từng artifact native kèm phiên bản và checksum; ghi rõ khi nào không có hỗ trợ.
- Nếu yêu cầu đa nền tảng cao mà native chỉ phục vụ tối ưu hóa, giữ đường Java thuần làm baseline.

## 4. Độ an toàn: vùng ngoài JVM thay đổi mô hình rủi ro

Trong Java thuần, cơ chế kiểm tra chỉ số mảng, an toàn kiểu, GC và quản lý đối tượng hạn chế nhiều lỗi bộ nhớ phổ biến. Khi đi vào native code, các bảo đảm này **không tự động bao phủ** con trỏ, buffer hoặc thread phía native.

### 4.1. Những lỗi cần thiết kế để phòng ngừa

| Rủi ro | Tình huống | Kiểm soát |
| --- | --- | --- |
| Vượt biên bộ nhớ | C ghi quá dung lượng buffer do Java truyền | Kiểm tra độ dài hai phía; dùng API có kiểm tra bounds; fuzz và sanitizer native |
| Use-after-free | Native giữ con trỏ sau khi vùng nhớ bị giải phóng | Quy định ai sở hữu và khi nào tài nguyên hết hạn; không lưu pointer vượt scope |
| Double-free / leak | Hai bên cùng giải phóng hoặc không bên nào giải phóng | Một chủ sở hữu rõ ràng; close/free theo hợp đồng; test leak |
| Data race / sai thread | Native callback trên thread không phù hợp hoặc chia sẻ buffer không đồng bộ | Ghi rõ quy tắc luồng, đồng bộ, thời gian sống và callback |
| Sai ABI / layout | Java hiểu struct khác C; sai alignment hoặc kiểu số | Đối chiếu header, layout, calling convention; test dữ liệu biên |
| Crash ngoài khả năng bắt exception | Native dereference pointer hỏng gây SIGSEGV/access violation | Test native bằng sanitizer; cô lập tiến trình nếu cần độ sẵn sàng cao |
| Library không đáng tin | Binary bị thay thế, lỗi thời hoặc chứa CVE | Kiểm chứng nguồn, hash/chữ ký, SBOM, cập nhật và hạn chế quyền |

**Bắt Exception không biến native code thành vùng an toàn.** Một lỗi link thư viện có thể sinh UnsatisfiedLinkError, nhưng lỗi ghi nhớ sai có thể làm crash toàn bộ process, âm thầm làm hỏng dữ liệu hoặc chỉ bộc lộ sau nhiều request.

### 4.2. Quyền sở hữu bộ nhớ và FFM

FFM có MemorySegment và Arena để mô tả vùng nhớ và vòng đời truy cập. Khi sử dụng đúng, các kiểm tra về phạm vi truy cập và vòng đời giúp tránh một số lỗi ở mã Java gọi API. Tuy nhiên:

- Vùng off-heap không trở thành đối tượng Java được GC quản lý như bình thường; phải hiểu khi nào tài nguyên được cấp phát/thu hồi.
- Mã native có thể ghi sai địa chỉ, giữ pointer quá lâu hoặc vi phạm hợp đồng đồng bộ dù Java dùng FFM.
- Cần phân biệt **sao chép**, **mượn buffer tạm thời** và **chuyển giao quyền sở hữu**. Nếu native giữ pointer sau khi lời gọi kết thúc, bộ nhớ và callback không được đóng/giải phóng quá sớm.
- Một Arena có phạm vi thread không thể dùng tùy tiện từ mọi thread; thiết kế callback và concurrency phải theo đúng quy tắc của API.

### 4.3. Native access là quyền cần quản trị

Từ **JDK 24**, các thao tác JNI như nạp thư viện và liên kết native method thuộc diện **restricted native access**, tương tự một số thao tác FFM. Các bản JDK hiện hành có cơ chế cảnh báo/chế độ xử lý truy cập không được khai báo; chính sách có thể siết chặt ở phiên bản sau.

Khi triển khai, xem xét bật quyền có chủ đích bằng tùy chọn **--enable-native-access** cho module cần dùng (hoặc **ALL-UNNAMED** khi chạy ứng dụng trên classpath). Có thể kiểm tra đường nâng cấp bằng chế độ **--illegal-native-access=deny** nếu JDK hỗ trợ. Không bật quyền rộng hơn mức cần thiết và không coi việc hết warning là bằng chứng thư viện an toàn.

### 4.4. Khi nào phải cô lập tiến trình?

Nếu native library có nguồn gốc khó kiểm soát, xử lý file đầu vào không đáng tin hoặc crash là rủi ro không chấp nhận được, cân nhắc chạy trong **tiến trình riêng** với timeout, giới hạn bộ nhớ/CPU, quyền hệ điều hành tối thiểu và giao thức trao đổi có kiểm tra. Giao tiếp IPC sẽ tốn serialization và context switch, nhưng một crash của worker native có thể được phát hiện và khởi động lại độc lập. Cô lập tiến trình giúp giảm phạm vi ảnh hưởng; nó không thay thế vá lỗi hoặc kiểm tra đầu vào.

## 5. Hiệu năng: đo đường đi đầy đủ, không đo một hàm đơn lẻ

Native không đồng nghĩa nhanh hơn. JVM có JIT, tối ưu nội tuyến, vector hóa, intrinsic và thư viện chuẩn được tối ưu. Một lời gọi native có thể thắng ở phần tính toán nhưng thua khi tính cả chuyển đổi dữ liệu.

Mô hình tư duy đơn giản:

~~~text
T_end_to_end =
    T_khoi_tao_va_nap_thu_vien
  + N * (T_qua_ranh_gioi + T_chuyen_du_lieu)
  + T_xu_ly_native
  + T_dong_bo_va_callback
  + T_giai_phong_tai_nguyen
~~~

Đây là mô hình để phân tích, **không phải công thức dự báo chính xác**; các phần có thể chồng lấn và phụ thuộc caching, JIT, tải hệ thống.

### Các nguồn chi phí dễ bị bỏ sót

- **Rất nhiều lời gọi nhỏ:** một triệu lần gọi native để xử lý từng số có thể chậm hơn một lời gọi xử lý mảng lớn.
- **Marshalling/copy:** đổi String, object graph hoặc mảng Java sang bố cục C; chuyển từ heap sang native buffer và ngược lại.
- **GC interaction:** giữ hoặc pin vùng dữ liệu trong thời gian dài có thể ảnh hưởng hoạt động GC; cấp phát off-heap cũng tăng áp lực bộ nhớ process dù không hiện rõ trên Java heap.
- **Threading:** native library tự tạo thread, khóa nội bộ hoặc gọi ngược JVM có thể gây contention và latency bất thường.
- **Khởi động:** load thư viện, resolve symbol và khởi tạo thiết bị có thể gây độ trễ lần đầu.
- **Tài nguyên ngoài heap:** throughput tăng nhưng RSS cao hơn, memory leak hoặc fragmentation có thể làm hệ thống kém ổn định.

### Khi native có thể đáng giá

Một thư viện xử lý ảnh thực hiện phép biến đổi lớn trên block dữ liệu liên tục, hoặc một SDK thiết bị có phần cứng chuyên dụng, có thể đem lại lợi ích thực sự. Ngược lại, thay thao tác chuỗi đơn giản bằng một lời gọi C riêng cho từng phần tử thường là thiết kế cần xem lại.

Trước khi chọn native:

1. Lấy **baseline Java thuần** bằng workload đại diện và đo sau warm-up phù hợp.
2. Đo **end-to-end** gồm startup, crossing, copy, thao tác native, kết quả và giải phóng; bổ sung benchmark vi mô khi cần chẩn đoán.
3. So cùng input/output, mức độ chính xác, concurrency, batch size và cấu hình máy.
4. Theo dõi throughput, p50/p95/p99 latency, CPU, native RSS, GC và tỷ lệ lỗi; không chỉ chọn một phép đo tốt nhất.
5. Dùng công cụ phù hợp: JMH cho phép đo vi mô Java, Java Flight Recorder cho quan sát JVM, profiler/sanitizer phía native và kiểm thử tải hệ thống.
6. Chạy trên **tất cả môi trường mục tiêu**: tối ưu cho một CPU hoặc một libc không đảm bảo lợi ích trên nền tảng khác.

**Nguyên tắc kiến trúc:** giảm số lần crossing, truyền dữ liệu theo lô và giữ hợp đồng dữ liệu rõ ràng thường có tác động lớn hơn việc đổi cơ chế JNI sang FFM chỉ vì kỳ vọng “nhanh hơn”. JNI, FFM và binding bên thứ ba phải được đo theo workload thực tế.

## 6. Vận hành: chi phí kéo dài sau khi code đã chạy

Một Java JAR thuần có thể được triển khai khá thống nhất trên nhiều JVM tương thích. Có native library, quy trình phát hành phải quản lý thêm binary và dependency:

### 6.1. Build và phân phối

- Tạo artifact theo tổ hợp **OS × architecture × ABI/libc**, cùng phiên bản có kiểm soát; lưu checksum và nguồn build có thể truy vết.
- Kiểm tra dependency bậc hai, phiên bản C/C++ runtime, CPU instruction set, chế độ 32/64-bit, cấu trúc image container.
- Tránh giả định rằng binary build trên máy mới nhất sẽ chạy trên máy hoặc image cũ hơn.
- Quy định rõ vị trí nạp thư viện. **System.loadLibrary** tìm theo cơ chế nạp library của JVM/hệ điều hành; **System.load** nhận đường dẫn tuyệt đối. Không dựa vào thư mục ghi được bởi người dùng hoặc đường dẫn khó kiểm soát trong production.
- Nếu bundle và giải nén native library, quản lý quyền file, tính toàn vẹn, chống đua ghi file và dọn tài nguyên.
- CI chạy kiểm tra chức năng và load smoke test trên từng môi trường được hỗ trợ; không chỉ cross-compile rồi tin rằng chạy được.

### 6.2. Khả năng quan sát và xử lý lỗi

Ghi lại **phiên bản adapter và native library**, OS/architecture, biến thể binary được chọn, lỗi load/link, kết quả health check và độ trễ ranh giới. Không log dữ liệu nhạy cảm hoặc pointer tùy tiện. Khi điều tra:

- **UnsatisfiedLinkError:** kiểm tra thiếu binary, tên library, đường dẫn tìm kiếm, dependency không load được, symbol không khớp và ABI.
- **Lỗi sau khi load thành công:** kiểm tra hợp đồng dữ liệu, signature của phương thức, lifecycle memory, callback và thread.
- **JVM crash:** thu thập crash log của JVM và core dump theo chính sách, symbol/debug info tương ứng với build; phân tích native stack cùng Java stack khi có.
- **Tăng RSS không tương ứng Java heap:** kiểm tra cấp phát native, arena, cache và leak; Java heap dump có thể không phản ánh toàn bộ bộ nhớ process.
- **Latency tăng đột biến:** đo thời gian ở từng đoạn, kiểm tra batch size, lock, GC, native thread và hoạt động I/O.

Trên JDK hỗ trợ, các sự kiện JFR như **jdk.NativeLibraryLoad** và **jdk.NativeLibraryUnload** giúp quan sát thao tác nạp/gỡ thư viện. Thông tin này bổ sung cho log và metric của ứng dụng.

### 6.3. Nâng cấp và rollback

Cập nhật thư viện native đồng thời có thể thay đổi ABI, symbol, hành vi lỗi hoặc yêu cầu libc. Cần kiểm tra tương thích giữa **bản Java adapter ↔ native binary ↔ môi trường runtime**; thực hiện canary, xác minh bằng test tích hợp và có khả năng rollback cả cặp phiên bản. Không chỉ rollback JAR trong khi thư viện native đã bị thay bằng bản không tương thích.

Native library trong cùng process đôi khi không thể unload/reload an toàn theo cách ứng dụng mong muốn; kế hoạch rollout nên tính đến việc **restart tiến trình**.

## 7. Chọn cách tích hợp theo yêu cầu thực tế

| Phương án | Thường phù hợp khi | Chi phí/rủi ro nổi bật |
| --- | --- | --- |
| **Java thuần / JDK API** | Đã có API đáp ứng chức năng và hiệu năng | Ít nhất về packaging native; vẫn phải đo và kiểm tra tính đúng |
| **JNI** | Có binding JNI trưởng thành hoặc cần cơ chế tương tác JVM đặc thù | Cầu nối native phức tạp, quản lý reference/exception/thread, crash trong process |
| **FFM (JDK 22+)** | Cần gọi thư viện C hay thao tác dữ liệu native với API chuẩn và mô hình layout/lifetime rõ hơn | Vẫn phụ thuộc binary và ABI; native access và mã C sai vẫn nguy hiểm |
| **JNA/binding bên thứ ba** | Ưu tiên tốc độ tích hợp, API nhỏ, dependency chấp nhận được | Phụ thuộc thêm runtime/binding và chi phí marshalling; vẫn cần test ABI |
| **Tiến trình native riêng qua IPC** | Cần cô lập crash, áp giới hạn quyền hoặc nâng cấp độc lập | Serialization, copy, latency, quản lý lifecycle và version giao thức |

Không nên chọn chỉ theo một hàng trong bảng. Chẳng hạn, nếu JDK mục tiêu là 17 nhưng FFM ổn định chỉ từ JDK 22, chi phí nâng JDK hoặc dùng cơ chế tương thích phải được đưa vào quyết định. Với C++ ABI phức tạp, một **C ABI wrapper** đơn giản và được version hóa thường giúp giảm rủi ro binding, dù vẫn cần kiểm chứng.

### Một quy trình quyết định có thể kiểm tra

**Câu hỏi 1 — Có thật sự cần native?** Nếu JDK hoặc thư viện Java đã đáp ứng chức năng và SLO, bắt đầu với Java thuần. Native cần một lý do cụ thể: API bắt buộc, SDK chỉ có native, tăng tốc đã đo được hoặc yêu cầu phần cứng.

**Câu hỏi 2 — Ranh giới tin cậy ở đâu?** Nếu mã native xử lý dữ liệu không tin cậy hay độ sẵn sàng rất cao, cân nhắc tách tiến trình sớm. Không coi try/catch là cơ chế chống crash.

**Câu hỏi 3 — Ai sở hữu dữ liệu và tài nguyên?** Viết hợp đồng cho input/output, encoding, layout, length, null, lifetime, thread, callback, lỗi và giải phóng. Mỗi buffer phải có một quy tắc ownership có thể test.

**Câu hỏi 4 — Chạy được ở đâu?** Lập ma trận OS/architecture/ABI/JDK/container, gắn mỗi cấu hình với artifact và pipeline kiểm thử. Nếu chỉ hỗ trợ một tập con, công bố rõ điều kiện đó.

**Câu hỏi 5 — Có bằng chứng lợi ích vượt chi phí?** So benchmark end-to-end với baseline, cộng thêm effort build, incident, CVE, support, rollback. Chốt thiết kế bằng số liệu của workload thực tế và mức rủi ro chấp nhận được.

## 8. Ví dụ Java 17+: cô lập native adapter và fallback rõ ràng

Giả sử muốn tính CRC32 cho một payload. JDK đã có **java.util.zip.CRC32**, nên **không cần native chỉ để tính CRC32**. Ví dụ sau cố ý dùng CRC32 làm chức năng nhỏ, xác định được kết quả để minh họa cách một ứng dụng **không phụ thuộc vào sự hiện diện của native binary** ở đường chạy mặc định.

File **NativeTradeoffDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.zip.CRC32;

public final class NativeTradeoffDemo {
    private NativeTradeoffDemo() {
    }

    // Chỉ là khai báo JNI. Ví dụ KHÔNG cung cấp thư viện demo_crc32.
    private static native long nativeCrc32(byte[] data);

    private static long javaCrc32(byte[] data) {
        CRC32 crc = new CRC32();
        crc.update(data, 0, data.length);
        return crc.getValue();
    }

    private static long checksum(byte[] data) {
        if (Boolean.getBoolean("demo.useNative")) {
            try {
                System.loadLibrary("demo_crc32");
                return nativeCrc32(data);
            } catch (UnsatisfiedLinkError
                     | SecurityException
                     | IllegalCallerException error) {
                System.err.println(
                    "Native unavailable: " + error.getClass().getSimpleName()
                );
            }
        }
        return javaCrc32(data);
    }

    public static void main(String[] args) {
        byte[] input = "123456789".getBytes(StandardCharsets.US_ASCII);
        System.out.printf("CRC32: %08X%n", checksum(input));
    }
}
~~~

Biên dịch và chạy **đường Java mặc định**, không yêu cầu thư viện native:

~~~bash
javac NativeTradeoffDemo.java
java NativeTradeoffDemo
~~~

Kết quả **stdout chính xác**:

~~~text
CRC32: CBF43926
~~~

Đặt cờ **-Ddemo.useNative=true** mới yêu cầu thử nạp thư viện tên **demo_crc32** và gọi JNI. Do ví dụ **không có bản cài đặt C/JNI**, môi trường thông thường sẽ báo lỗi load/link trên stderr rồi dùng Java fallback; stdout vẫn biểu diễn kết quả của CRC32 Java. Trên JDK 24+ có thể xuất hiện cảnh báo native access tùy cấu hình. Không dùng nhánh native của ví dụ để suy ra tốc độ JNI/FFM.

**Giới hạn cố ý của ví dụ:**

- Fallback chỉ phù hợp khi kết quả và ngữ nghĩa hai implementation **đã được kiểm chứng tương đương**. Với thao tác bảo mật hoặc dữ liệu cần tính chính xác đặc biệt, không tự ý fallback làm thay đổi hợp đồng.
- Catch UnsatisfiedLinkError xử lý lỗi load/link, **không cứu được JVM nếu native code làm hỏng bộ nhớ hoặc crash process**.
- Code minh họa thử load ngay khi gọi; sản phẩm thật nên có **adapter được khởi tạo và kiểm tra sức khỏe có kiểm soát**, không nạp thư viện lặp trong đường nóng, và nên kiểm tra bằng một lời gọi smoke test an toàn.
- Nếu phát triển nativeCrc32 thật, phải cung cấp header/signature JNI tương ứng, bảo đảm thuật toán trả kết quả CRC32 không dấu biểu diễn bằng long, hỗ trợ binary theo nền tảng và test chéo với Java.

## 9. Ba tình huống ứng dụng

**Tình huống A — Tối ưu xử lý từng bản ghi nhỏ.** Ứng dụng xử lý hàng triệu item và muốn gọi thư viện C cho từng item. Vì crossing/marshalling lặp lại, hãy benchmark Java thuần trước, sau đó thử batch API; nếu lợi ích toàn tuyến không đáng kể, không đưa native vào production.

**Tình huống B — Tích hợp SDK của thiết bị chỉ cung cấp C API.** Native gần như bắt buộc vì thiếu API Java tương đương. Xây adapter hẹp, kiểm soát pointer/buffer và callback, đóng gói binary từng nền tảng, bổ sung simulator hoặc contract test khi CI không có thiết bị thật.

**Tình huống C — Giải mã file đầu vào không đáng tin bằng thư viện C/C++.** Dù native có thể rất nhanh, một lỗi parsing có thể làm crash JVM hoặc lộ bộ nhớ. Cân nhắc worker process với quyền tối thiểu, timeout và giới hạn tài nguyên, giao thức được version hóa, circuit breaker và kiểm tra file lỗi/fuzzing.

Trong mỗi trường hợp, câu trả lời tốt phụ thuộc vào ràng buộc **chức năng, vận hành và SLO**, không chỉ vào ngôn ngữ cài đặt.

## 10. Sai lầm phổ biến và cách tránh

| Sai lầm | Vì sao sai | Cách làm tốt hơn |
| --- | --- | --- |
| “Native luôn nhanh hơn Java” | Bỏ qua JIT, crossing và copy | Đo toàn tuyến, so cùng workload và semantics |
| “FFM làm C library an toàn” | FFM không kiểm soát mọi hành vi C/C++ bên ngoài | Quy định ownership, kiểm tra biên, dùng sanitizer và isolation khi cần |
| “Một file SO chạy trên mọi Linux” | ABI/libc/CPU và dependencies có thể khác | Build/test ma trận mục tiêu, gắn binary với runtime |
| “Bắt Throwable sẽ không làm JVM chết” | Crash process và memory corruption nằm ngoài bảo đảm try/catch | Test native, giới hạn quyền, tách process nếu cần |
| “Chỉ cần có DLL/SO trong JAR” | Loader, dependency, quyền và đường dẫn vẫn có thể lỗi | Smoke test load/link trên đúng OS/container |
| “Chỉ cần kiểm tra heap” | Off-heap/native allocation cũng tiêu thụ RAM | Quan sát RSS, native allocation, GC và leak |
| “Đổi Java binding là đủ khi nâng library” | ABI/version, native access và binary có thể đổi | Version hóa cặp adapter–binary, canary và rollback |

## 11. Checklist trước khi đưa vào production

- [ ] Đã ghi rõ lý do native là cần thiết hoặc lợi ích đo được; baseline Java thuần được lưu lại.
- [ ] Mỗi API có hợp đồng dữ liệu: kiểu, độ dài, encoding, layout, ownership, lifetime, thread, lỗi và callback.
- [ ] Đã kiểm tra input không tin cậy, memory safety và độ ổn định dưới tải; có test lỗi native và crash strategy.
- [ ] Có artifact và test cho **từng** OS/architecture/ABI/libc/JDK được cam kết hỗ trợ.
- [ ] Binary có nguồn gốc, checksum/chữ ký, dependency và quy trình cập nhật lỗ hổng.
- [ ] Startup kiểm tra load/link/capability; thiếu hỗ trợ thì báo lỗi rõ hoặc fallback tương đương đã được test.
- [ ] Đã đo throughput, p95/p99 latency, CPU, Java heap, native RSS và hiệu quả batch trên workload thật.
- [ ] Đã xác định native access flags theo phiên bản JDK/module và thử kịch bản siết chặt quyền.
- [ ] Có metric, log phiên bản native, crash dump/symbol, health check, canary và rollback nhất quán.
- [ ] Có chủ sở hữu bảo trì thư viện native và kế hoạch nâng cấp phụ thuộc.

## 12. Câu hỏi tự kiểm tra

1. **Vì sao FFM không tự giải quyết tính khả chuyển?** Vì nó cung cấp API phía Java; binary và hợp đồng ABI của thư viện native vẫn phụ thuộc OS/CPU/runtime.
2. **Khi một thao tác native nhanh gấp đôi nhưng service chậm hơn, kiểm tra gì trước?** Số lần crossing, copy/marshalling, startup, lock/callback, RSS/GC và hiệu năng toàn tuyến dưới tải thực.
3. **Khi nào fallback là nguy hiểm?** Khi hai implementation khác ngữ nghĩa, độ chính xác, bảo mật, trạng thái hoặc tác động phụ; trường hợp này phải fail rõ ràng hoặc kiểm chứng tương đương trước.
4. **Vì sao nên tách tiến trình cho một bộ giải mã native không đáng tin?** Để giảm phạm vi ảnh hưởng của crash và áp giới hạn quyền/tài nguyên, đổi lại chịu chi phí IPC và quản lý tiến trình.
5. **Lỗi UnsatisfiedLinkError đã được bắt thì có đảm bảo native an toàn không?** Không. Nó chủ yếu liên quan nạp/liên kết, không bảo vệ khỏi memory corruption hoặc crash trong thư viện native.

## Tài liệu tham khảo chính thức

- [JEP 454 — Foreign Function & Memory API (JDK 22)](https://openjdk.org/jeps/454).
- [Oracle Java 22 — Foreign Function and Memory API](https://docs.oracle.com/en/java/javase/22/core/foreign-function-and-memory-api.html).
- [JEP 472 — Prepare to Restrict the Use of JNI](https://openjdk.org/jeps/472).
- [Oracle JDK 26 Migration Guide — Native Access Restrictions](https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html).

**Điểm cần nhớ:** Quyết định dùng native chỉ thực sự hợp lý khi lợi ích chức năng hoặc hiệu năng vượt qua **tổng chi phí khả chuyển, an toàn, hiệu năng toàn tuyến và vận hành** được xác minh bằng kiểm thử, số liệu và quy trình triển khai cụ thể.
