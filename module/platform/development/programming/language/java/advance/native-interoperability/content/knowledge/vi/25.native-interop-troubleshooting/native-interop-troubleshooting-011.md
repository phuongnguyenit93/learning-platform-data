# Tách ví dụ lỗi tối thiểu khỏi ứng dụng lớn trước khi kết luận lỗi JVM

## Mục tiêu

Khi một dịch vụ Java dùng JNI hoặc Foreign Function & Memory API (FFM) gặp `UnsatisfiedLinkError`, `IllegalCallerException`, kết quả native sai, hoặc tiến trình JVM dừng với `SIGSEGV` / `EXCEPTION_ACCESS_VIOLATION`, rất dễ quy lỗi cho JVM vì thông báo xuất hiện trong tiến trình `java`. Nhưng lỗi có thể nằm ở cấu hình JVM, thư viện native, ABI, vòng đời bộ nhớ, dữ liệu đầu vào, ứng dụng, hệ điều hành hoặc chính JVM.

Một **minimal reproducible example (MRE)** là bộ mã, dữ liệu và lệnh chạy nhỏ nhất có thể tạo lại **cùng hiện tượng cần điều tra** trong môi trường đã mô tả. Cần tối thiểu hóa từng phần nhưng vẫn giữ đúng điều kiện kích hoạt, thay vì tạo ra một lỗi “trông giống” lỗi ban đầu.

Sau bài này, người học có thể:

- Xác định **dấu vân tay lỗi** cần giữ nguyên khi rút gọn.
- Tách dần framework, database, HTTP, dependency và logic nghiệp vụ, nhưng giữ lại các điều kiện JNI/FFM thực sự liên quan.
- Chạy thử nghiệm có đối chứng để phân biệt lỗi cấu hình, thư viện native, ứng dụng và giả thuyết lỗi JVM.
- Chuẩn bị một gói tái hiện đủ thông tin để người khác chạy lại, xác minh hoặc báo cáo sự cố.

## 1. “Lỗi trong tiến trình Java” chưa có nghĩa là “bug của JVM”

| Dấu hiệu | Ý nghĩa ban đầu | Điều cần kiểm chứng |
| --- | --- | --- |
| `UnsatisfiedLinkError` | Không nạp, tìm thấy hoặc liên kết được thư viện/hàm native | Tên/path thư viện, binary đúng OS/CPU, dependency native, tên symbol, chữ ký JNI |
| Cảnh báo restricted native access / `IllegalCallerException` | Mã chạy vào thao tác native bị giới hạn nhưng module chưa có quyền theo chính sách JDK | Phiên bản JDK và các cờ `--enable-native-access`, `--illegal-native-access`; module thực hiện lời gọi |
| `WrongMethodTypeException` / `IllegalArgumentException` ở FFM | Java-side method handle, layout, argument hoặc điều kiện API có thể chưa phù hợp | `FunctionDescriptor`, `MethodType`, kích thước/alignment, lifetime và giá trị truyền |
| Exception Java bình thường | Luồng Java ném exception; thường tiến trình JVM vẫn hoạt động | Stack trace đầu tiên, input, logic và thư viện tạo exception |
| `SIGSEGV` hoặc `EXCEPTION_ACCESS_VIOLATION`, file `hs_err_pid*.log` | Fatal error làm tiến trình VM chết | Problematic frame, native stack, crash dump, thư viện C/C++/JNI/FFM, compiler/JIT, OS |
| Treo, kết quả sai, memory leak | Có thể liên quan race, deadlock, memory safety, logic hoặc runtime | Thread dump, mẫu tải, thời gian chạy, tài nguyên và khả năng lặp lại |

**Không đủ chứng cứ:** “Cứ gọi native là JVM crash”; “stack có `jvm.dll` nên lỗi chắc chắn ở JVM”; “thêm `-Xint` thì hết lỗi nên chắc chắn JIT bị bug”. Ví dụ, JNI code có thể làm hỏng bộ nhớ rồi crash ở một frame của JVM khá lâu sau đó. Một thay đổi cờ JVM cũng có thể thay đổi timing hoặc layout, chỉ giúp khoanh vùng chứ chưa chứng minh nguyên nhân.

## 2. Chụp mốc ban đầu trước khi sửa hoặc cắt bớt

Mỗi lần rút gọn cần có **điểm so sánh đáng tin**. Trước hết chạy lại bản gốc, ghi nhận môi trường và dấu hiệu. Không đổi đồng thời JDK, cờ, native binary và input rồi dùng kết quả để kết luận.

### 2.1. Lưu dấu vân tay lỗi

Ghi ít nhất bốn nhóm:

1. **Trigger:** thao tác, request/input, đường gọi Java → JNI/FFM, thứ tự các bước, số luồng, số lần lặp, seed ngẫu nhiên và thời điểm phát sinh.
2. **Triệu chứng:** loại exception và stack trace gốc; nếu VM chết, lưu fatal error log (thường `hs_err_pid<process-id>.log`), problematic frame, signal, thread đang chạy, exit code và khoảng thời gian đến khi crash.
3. **Môi trường:** JDK vendor + **đầy đủ build/update**, tên VM, OS, CPU architecture, container/base image, CPU/memory limit; phiên bản native library, architecture/ABI và các thư viện native phụ thuộc.
4. **Lệnh chạy:** chính xác đường dẫn tới binary `java`, class path/module path, `-D` properties, `-X` / `-XX` flags, `--enable-native-access`, `--add-opens`, các biến môi trường có thể ảnh hưởng library search và toàn bộ input.

Lệnh tham khảo, chạy bằng **đúng JDK của ứng dụng gặp lỗi**:

```bash
java -version
javac -version
```

Nếu Java process vẫn chạy, HotSpot/JDK có thể cung cấp:

```bash
jcmd <pid> VM.command_line
jcmd <pid> VM.system_properties
```

Hai lệnh `jcmd` là **mẫu cú pháp**; thay `<pid>` bằng PID thực, cần quyền attach và có thể không khả dụng trong một số container. Thu thập có chọn lọc vì system properties và crash dumps có thể chứa đường dẫn, token, dữ liệu nhạy cảm. Với runtime chạy trong IDE, Docker hoặc Gradle, đừng giả định `java` trên `PATH` là đúng JVM của process; kiểm tra binary thực sự được gọi.

### 2.2. Phân biệt fatal crash với exception được bắt

- **Exception Java:** có stack trace và có thể bắt được (ví dụ `UnsatisfiedLinkError` là một `Error`). Chỉ thấy exception không đủ bằng chứng VM chết.
- **Fatal VM crash:** thường xuất hiện fatal error log của HotSpot và process chấm dứt bất thường; `SIGSEGV` trên hệ Unix hoặc `EXCEPTION_ACCESS_VIOLATION` trên Windows là những dấu hiệu cần điều tra native/runtime.
- **Process bị OS kill:** có thể không sinh `hs_err`, chẳng hạn hết memory của container hoặc tín hiệu từ bên ngoài. Đối chiếu exit status, container events, OS logs.
- **Lỗi kết quả hay treo:** không được tự biến thành crash chỉ vì khó tái hiện. Giữ đúng loại hiện tượng khi tạo MRE.

## 3. Quy trình rút gọn: giữ nguyên trigger, bỏ từng tầng

Giả sử ứng dụng lớn có luồng sau:

```text
HTTP request
  -> Spring Controller
  -> Service / business rules
  -> Database / queue / cache
  -> JNI hoặc FFM bridge
  -> libimage.so / image.dll / libimage.dylib
  -> native function đọc buffer
  -> JVM chết hoặc trả sai kết quả
```

Mục tiêu không nhất thiết là xóa mọi thành phần. Mục tiêu là tìm **tập điều kiện tối thiểu vẫn tạo được cùng lỗi**. Thực hiện tuần tự:

1. **Đóng băng baseline:** giữ một bản chạy và cấu hình gốc. Tạo bản thử độc lập để cắt giảm; lưu lại lệnh chạy và kết quả trước/sau mỗi thay đổi.
2. **Thay phần điều phối:** gọi trực tiếp bridge từ `public static void main(String[] args)`; bỏ HTTP, scheduler, DI hoặc framework nếu lỗi vẫn tồn tại.
3. **Thay dữ liệu nguồn:** nếu có thể, thay database/remote API bằng byte array, file fixture hoặc input cố định. Ghi đúng encoding, length, giá trị đặc biệt, endian và thứ tự dữ liệu mà native side nhận.
4. **Tách lớp tích hợp:** giảm xuống một wrapper Java cùng `System.load(...)` / `System.loadLibrary(...)` hoặc một FFM downcall, và đúng native library tương ứng. Không vội bỏ thư viện native vì đó có thể là thành phần gây lỗi.
5. **Cắt native side có kiểm soát:** nếu sở hữu source C/C++, giảm hàm native thành thao tác nhỏ hơn nhưng **giữ nguyên lỗi**. Với thư viện third-party không có source, giữ binary thực tế, version, checksum và hướng dẫn lấy lại.
6. **Thu nhỏ concurrency/resource:** chỉ bỏ thread hoặc tải nếu lỗi còn xuất hiện; với race/UAF, số luồng, interleaving, warm-up hoặc tần suất lặp có thể chính là trigger.
7. **Chạy lại bản gốc ở điểm kiểm:** khi bản tối thiểu mất lỗi, phục hồi thay đổi gần nhất, thử lại và xác định dependency/điều kiện đã bị loại bỏ quá tay.

Có thể dùng cách **delta debugging**: chia tập dependency/thao tác thành hai nhóm, tạm loại một nhóm, chạy test; nếu vẫn cùng lỗi, giữ phần đã rút; nếu mất lỗi, phục hồi rồi thử nhóm khác. Việc chia nửa chỉ là chiến lược tìm kiếm; các yếu tố phụ thuộc nhau (ví dụ native library + đúng layout) có thể phải được giữ như một nhóm. Với lỗi không ổn định, lặp lại đủ nhiều lần và so tỷ lệ xuất hiện trước/sau; **một lần chạy thành công không chứng minh lỗi đã biến mất**.

### Một MRE native thực sự cần giữ những gì?

| Thành phần | Chỉ giữ khi liên quan; ví dụ |
| --- | --- |
| Java source | Một class có `main()`, đoạn gọi JNI/FFM, kiểu dữ liệu và lỗi quan sát |
| Native source/binary | Hàm C/C++ tối thiểu hoặc file `.so`/`.dll`/`.dylib` đúng version, cách build và phụ thuộc |
| Định nghĩa giao tiếp | `JNIEXPORT` signature; FFM `FunctionDescriptor`, `MemoryLayout`, calling convention, pointer ownership |
| Dữ liệu | Byte sequence, charset, buffer size, offset, alignment, giá trị biên, số lần lặp |
| Runtime | JDK build và flags có ảnh hưởng, OS/CPU, kiến trúc binary, đường dẫn load library |
| Timing/tài nguyên | Nếu là race, thread count, scheduling, warm-up, workload, container limit |

Không thay một lệnh `downcallHandle` bằng mã tự `throw new RuntimeException(...)` để “tái hiện lỗi”: tuy cùng thấy exception trên console, điểm phát sinh và cơ chế đã khác. Tương tự, thay binary native bằng một file lỗi khiến `UnsatisfiedLinkError` xuất hiện chưa chứng minh đã tái hiện crash gốc.

## 4. Ví dụ Java chạy độc lập: tách lỗi nạp thư viện khỏi ứng dụng

Giả sử một Spring Boot service báo `UnsatisfiedLinkError` lúc khởi tạo JNI wrapper. Bước đầu tiên là **thử riêng thao tác nạp thư viện**, không cần controller, database hay server. Ví dụ sau minh họa cơ chế lỗi do thiếu file; **đây là lỗi môi trường được tạo có chủ đích, không phải bằng chứng JVM có bug**.

Tạo file **`MinimalNativeLoad.java`**:

```java
import java.nio.file.Path;

public final class MinimalNativeLoad {
    public static void main(String[] args) {
        Path missingFile =
                Path.of("__missing_native_repro_93cf6f91__.bin")
                    .toAbsolutePath();

        try {
            System.load(missingFile.toString());
            System.out.println("UNEXPECTED: library loaded");
        } catch (UnsatisfiedLinkError error) {
            System.out.println("REPRODUCED: UnsatisfiedLinkError");
        }
    }
}
```

Đoạn mã dùng cú pháp tương thích Java 17+, còn **lệnh chạy dưới đây dành cho JDK 24–25** vì kiểm soát native access của JNI được mở rộng từ JDK 24. Chạy trong thư mục **không có file** tên `__missing_native_repro_93cf6f91__.bin`:

```bash
javac MinimalNativeLoad.java
java --enable-native-access=ALL-UNNAMED --illegal-native-access=deny MinimalNativeLoad
```

Stdout dự kiến, nếu file không tồn tại:

```text
REPRODUCED: UnsatisfiedLinkError
```

**Vì sao cần hai cờ trong lệnh chạy?** Trên JDK 24–25, `System.load` là restricted native operation. `--enable-native-access=ALL-UNNAMED` cấp quyền cho class chạy trên class path; `--illegal-native-access=deny` làm thiếu quyền trở thành lỗi rõ ràng. Cấp quyền đầy đủ cho phép bước nạp thư viện diễn ra và thất bại đúng ở nguyên nhân **file không tồn tại**. Nếu thử thiếu cờ native access ở chế độ `deny`, lỗi có thể chuyển thành `IllegalCallerException` trước khi JVM kịp kiểm tra file; đó là **một trigger khác**.

Ví dụ này chỉ chứng minh rằng có thể tạo MRE cho **nhóm lỗi nạp thư viện**. Khi xử lý ứng dụng thật, hãy thay đường dẫn giả bằng đúng đường dẫn/binary đang gặp vấn đề và chỉ coi là tái hiện thành công khi **cùng giai đoạn, cùng dấu hiệu có ý nghĩa** xảy ra. Một `UnsatisfiedLinkError` vì “file not found” khác với `UnsatisfiedLinkError` vì “undefined symbol” hoặc vì dependency native thứ cấp bị thiếu, dù cùng tên loại exception.

### Đối chứng có giá trị hơn việc chỉ thấy exception

Nếu bản gốc lỗi khi nạp một thư viện có thật, kiểm tra tuần tự:

- File có thật ở đường dẫn ứng dụng dùng? `System.load` yêu cầu tên đường dẫn tuyệt đối; `System.loadLibrary` dùng tên logic để JVM tìm thư viện theo cấu hình.
- Binary đúng OS/architecture (x64, aarch64), đúng ABI, đúng phiên bản C runtime và phụ thuộc chưa?
- Symbol JNI có đúng tên, linkage và signature không? Với FFM, descriptor có khớp hàm native và ownership/lifetime vùng nhớ không?
- Lệnh thử trực tiếp dùng đúng JDK và tập flags tương đương bản gốc chưa?

Các công cụ kiểm tra dependency native tùy nền tảng gồm `ldd` (Linux), `otool -L` (macOS), `dumpbin /DEPENDENTS` (Windows, khi có công cụ phù hợp). Chúng hỗ trợ chẩn đoán binary; không phải bằng chứng tự động rằng JVM bị lỗi.

## 5. Thử nghiệm có đối chứng: thay một biến tại một thời điểm

Đặt một tiêu chí pass/fail dựa trên **signature của lỗi gốc**, không chỉ dựa trên “process kết thúc khác 0”. Ví dụ, nếu vấn đề là SIGSEGV trong hàm native sau 100 lượt gọi, kiểm tra có cùng kiểu crash/stack và điều kiện lời gọi; một `IllegalCallerException` xảy ra sớm hơn không được tính là tái hiện.

Bảng sau là **kế hoạch thử nghiệm**; cột kết quả để người thực hiện ghi từ môi trường thật, không giả định trước:

| Lượt | Giữ nguyên | Thay đúng một yếu tố | Câu hỏi |
| --- | --- | --- | --- |
| A | App gốc, JDK, input, native binary | Không thay đổi (baseline) | Lỗi hiện với tỷ lệ nào, signature gì? |
| B | JDK, flags, native binary, input | Thay HTTP/service bằng `main()` gọi bridge | Framework có bắt buộc để lỗi xảy ra? |
| C | JDK, flags, bridge, native binary | Thay database bằng input cố định | Có giữ đúng byte buffer gây lỗi không? |
| D | Bản MRE và input | Dùng build native khác, vẫn cùng ABI | Lỗi đi theo native binary hay không? |
| E | Bản MRE và cùng native binary | Đổi một JDK build/update trên môi trường tương đương | Có khác biệt liên quan phiên bản JVM không? |
| F | Bản MRE và JDK | Thêm `-Xcheck:jni`, nếu là JNI | JNI checker có phát hiện vi phạm thao tác nào không? |

Trong các phép so sánh, tránh thay đổi hai yếu tố cùng lúc. Nếu cần thử `-Xint` để xem khác biệt khi tắt JIT, hãy ghi nó là **thí nghiệm khoanh vùng**: mất lỗi có thể do JIT, do timing hoặc do bố cục bộ nhớ thay đổi. Không khẳng định JIT bug chỉ từ quan sát ấy.

### Khi lỗi có tính ngẫu nhiên

Bản MRE nhỏ có thể làm thay đổi lịch chạy thread, tốc độ hoặc memory layout và khiến race hiếm xuất hiện hơn. Hãy:

1. Giữ input/seed và dữ liệu binary có thể đối chiếu; nếu quan hệ timing là điều kiện, ghi đủ threads và sequence.
2. Cố định warm-up, số lần lặp và tài nguyên trong từng lượt so sánh.
3. Ghi **số lần lỗi / tổng số lần chạy**, ví dụ trong báo cáo thử nghiệm có thể ghi dạng “7/50”; đây chỉ là ví dụ định dạng, không phải kết quả quan sát của bài.
4. Tăng hoặc giảm concurrency từng mức để tìm ngưỡng; khi thay môi trường, giữ nguyên bài thử để tránh nhiễu.
5. Nếu chưa rút gọn được hơn mà vẫn giữ cùng lỗi, **dừng tại MRE nhỏ nhất hiện có**. Không cần ép thành một file Java bằng cách hy sinh trigger.

## 6. Đọc bằng chứng crash trong ngữ cảnh JNI/FFM

Với HotSpot fatal error, trước tiên xem `hs_err_pid*.log` hoặc file được cấu hình bằng `-XX:ErrorFile=...`. Chú ý phần đầu (signal, JDK build, problematic frame), thread hiện hành, native frames, loaded libraries, JVM flags và OS. Crash dump/core file có thể cần thiết khi stack bị hỏng.

- **`C [libcustom.so+offset]`:** điểm crash hiện nằm trong native library. Điều tra C/C++, dependency, pointer, ABI, JNI contract trước; vẫn chưa loại trừ dữ liệu bị hỏng ở nơi khác.
- **`V [libjvm.so+offset]` / `V [jvm.dll+offset]`:** crash được ghi ở mã VM. Không đủ để khẳng định bug JVM; lỗi native trước đó có thể gây memory corruption và làm JVM chết khi truy cập tiếp.
- **`J ...`:** frame mã Java đã JIT compile, đáng xem xét compiler/optimization nhưng vẫn phải loại trừ dữ liệu và native corruption.
- **Không có `hs_err`:** kiểm tra process có thật sự bị HotSpot fatal error hay bị OS kill, launcher/container chặn, thiếu quyền ghi log, hoặc JVM chết trước khi ghi được thông tin.

Với **JNI**, thử bật `-Xcheck:jni` trên cùng MRE:

```bash
java -Xcheck:jni --enable-native-access=ALL-UNNAMED MyJniRepro
```

`MyJniRepro` là tên minh họa, lệnh chỉ chạy khi có class và native library tương ứng. `-Xcheck:jni` có thể phát hiện sai cách dùng JNI và đôi khi dừng VM khi phát hiện vi phạm nghiêm trọng, nhưng **không chứng minh tất cả native code đều an toàn nếu không báo lỗi**. Với FFM, xem lại scope/lifetime của `Arena` / `MemorySegment`, pointer hợp lệ, alignment và chữ ký downcall/upcall; những lỗi bên native không được JVM bảo đảm bắt đầy đủ.

Nếu native code từ bên thứ ba gây crash, cần có phiên bản binary và cách lấy lại nó để tái hiện. Nếu sở hữu code C/C++, có thể thêm build với symbol/debug information và dùng native debugger phù hợp, nhưng ghi rõ rằng debug build có thể thay đổi timing/layout so với bản lỗi gốc.

## 7. Khi nào giả thuyết “lỗi JVM” đủ mạnh để báo?

Chỉ xem là **giả thuyết được củng cố**, chưa phải kết luận, khi đồng thời có nhiều bằng chứng:

1. Có **tái hiện ổn định** cùng lỗi gốc trên một MRE nhỏ, với lệnh chạy chính xác và dữ liệu cần thiết.
2. Đã loại trừ hoặc ghi nhận các yếu tố bên ngoài: thiếu native library, sai ABI, lỗi JNI/FFM contract, gọi API ngoài lifetime, data race, resource exhaustion và khác biệt OS/container.
3. Kiểm tra trên JDK update phù hợp và một vài cấu hình đối chứng có kiểm soát; nếu lỗi chỉ xuất hiện trên một build, ghi chính xác build đó thay vì khẳng định mọi JVM đều lỗi.
4. Đối chiếu các issue đã biết trong [OpenJDK JBS](https://bugs.openjdk.org/) hoặc kênh báo lỗi tương ứng, nhưng tránh kết luận chỉ dựa trên tên exception tương tự.
5. Đưa đủ chứng cứ để người khác độc lập chạy: file nguồn, native code/binary cần thiết, compiler/SDK, lệnh build/run, expected/actual, tỷ lệ lặp lại, logs và kết quả từng lần thử.

Một crash Java process **không tự khẳng định JVM có bug**; và việc một MRE chạy ổn trên JDK khác **không tự chứng minh lỗi nằm trong JDK ban đầu** nếu cùng lúc đã đổi native binary, OS, workload hoặc timing.

### Gói tái hiện chuẩn để trao đổi hoặc báo cáo

Một bug report tốt nên có các mục sau, với dữ liệu thật thay vì đoán:

- **Tóm tắt:** hiện tượng đúng nghĩa (exception, fatal crash, hang, wrong output) và bước xảy ra.
- **Môi trường tái hiện:** Java vendor/build, OS/CPU, container, native library và ABI.
- **Điều kiện chạy:** cấu trúc file nhỏ, cách build Java/native, lệnh `javac`/`java` đầy đủ, mọi flag liên quan.
- **Input và trigger:** dữ liệu tối thiểu, thứ tự gọi, số luồng/lặp, seed, cách kiểm tra kết quả.
- **Expected vs actual:** hành vi mong đợi và hành vi đã quan sát; ghi cả exit code và loại log.
- **Bằng chứng:** stack trace hoặc `hs_err`, core dump nếu có, trace JNI/FFM, output của các phép thử đối chứng.
- **Giới hạn hiện biết:** phần chưa rút gọn được hoặc điều kiện môi trường chưa kiểm soát.

Trước khi chia sẻ, loại dữ liệu cá nhân, secret, đường dẫn nội bộ, thông tin nhạy cảm; nhưng đừng sửa byte input, alignment, checksum hoặc tham số kích hoạt đến mức lỗi biến mất. Khi dữ liệu thật không thể chia sẻ, nêu rõ giới hạn và cố tạo synthetic fixture có hành vi tương đương.

## 8. Những lỗi thường gặp khi tối thiểu hóa

1. **Giữ cùng tên exception nhưng không giữ cùng nguyên nhân.** Hai `UnsatisfiedLinkError` có thể phát sinh ở giai đoạn hoàn toàn khác nhau: không tìm thấy file, thiếu dependency, hay thiếu native symbol.
2. **Xóa thư viện native quá sớm.** Nếu lỗi xảy ra vì pointer UAF hoặc ABI, MRE Java thuần không còn tái hiện điều cần chẩn đoán.
3. **Vừa đổi JDK vừa đổi binary native.** Mất lỗi sau đó không chỉ ra yếu tố nào quyết định.
4. **Bật/tắt nhiều JVM flags cùng lúc.** Đặc biệt `-Xint`, `-Xcheck:jni`, GC flags, access flags có thể làm thay đổi thời gian và đường chạy.
5. **Cắt concurrency rồi tuyên bố đã sửa.** Một race có thể chỉ xuất hiện với hai thread, warm-up hoặc áp lực bộ nhớ cụ thể.
6. **Bỏ mất bằng chứng khi `catch`.** Chỉ in “native error” mà không lưu exception message/stack trong hồ sơ điều tra sẽ làm mất signature quan trọng.
7. **Kết luận từ một lần chạy.** Lỗi hiếm cần biểu diễn xác suất/tỷ lệ và số lần kiểm tra.
8. **Đưa source nhưng thiếu lệnh build và environment.** Với native interoperability, compiler, architecture, library lookup và ABI thường là một phần của repro.

## Kết luận thực hành

Một lộ trình đáng tin là: **đóng băng lỗi gốc → chụp môi trường và signature → loại từng tầng không cần thiết → giữ lại Java/native boundary nhỏ nhất vẫn gây lỗi → chạy đối chứng có kiểm soát → đánh giá bằng chứng JVM bug**. Rút gọn thành công làm cuộc điều tra nhanh hơn; điều quan trọng hơn số dòng code là bảo toàn nguyên nhân và khả năng người khác tái hiện đúng hiện tượng.

## Tài liệu tham khảo

- [Oracle JDK 25 — Troubleshoot System Crashes](https://docs.oracle.com/en/java/javase/25/troubleshoot/troubleshoot-system-crashes.html): cách đọc fatal error log, problematic frame, lỗi native và lỗi JVM.
- [Oracle JDK 25 — Troubleshooting `-Xcheck:jni`](https://docs.oracle.com/en/java/javase/25/troubleshoot/command-line-options1.html): phạm vi kiểm tra JNI và giới hạn chẩn đoán.
- [Oracle — Submit a Bug Report](https://docs.oracle.com/en/java/javase/17/troubleshoot/submit-bug-report.html): thu thập mốc môi trường, rút gọn test và ghi lệnh tái hiện.
- [OpenJDK JEP 472 — Prepare to Restrict the Use of JNI](https://openjdk.org/jeps/472): ảnh hưởng `--enable-native-access` và `--illegal-native-access` trên JDK 24.
- [Oracle JDK 25 — Migrating from JDK 8 and Later](https://docs.oracle.com/en/java/javase/25/migrate/migrating-jdk-8-later-jdk-releases.html): JNI/FFM native access và diagnostic tools.