# Xcode Command Line Tools và kiến trúc CPU trên macOS

## 1. Vì sao môi trường macOS quan trọng khi build Spring Boot Native Image?

Trong module **SPRING_BOOT_NATIVE_IMAGE**, ứng dụng Spring Boot được xử lý qua **Spring AOT** và biên dịch bằng **GraalVM Native Image** thành chương trình native. Thay vì chạy bytecode trên JVM ở môi trường triển khai, bản native chạy dưới dạng executable dành cho một **hệ điều hành** và **kiến trúc CPU** cụ thể. Quy trình này giúp đánh giá thời gian khởi động, mức dùng bộ nhớ, nhưng cũng đặt thêm yêu cầu cho máy build.

Trên macOS, việc chạy `java -version` thành công **chưa đủ** chứng minh máy có thể build native. Native Image cần bộ công cụ biên dịch/link native của Apple. Đồng thời phải thống nhất kiến trúc của JDK/GraalVM, tiến trình build và thư viện liên quan: máy Apple Silicon thường dùng **arm64 (aarch64)**, còn Mac Intel dùng **x86_64 (amd64)**.

Hai câu hỏi nên giải quyết trước khi thực hành Maven/Gradle là:

1. **Máy có Xcode Command Line Tools, compiler, linker và macOS SDK dùng được không?**
2. **GraalVM và các công cụ đang chạy theo kiến trúc CPU nào, và executable được tạo ra sẽ chạy ở đâu?**

### Chuỗi công cụ ở thời điểm build

~~~mermaid
flowchart TB
    A["Mã nguồn và dependency Spring Boot"] --> B["Spring AOT tạo mã và runtime hints"]
    B --> C["JDK biên dịch bytecode Java"]
    C --> D["GraalVM Native Image phân tích và tạo mã native"]
    E["Xcode Command Line Tools: clang, linker, macOS SDK"] --> D
    D --> F["Mach-O executable: macOS arm64 hoặc x86_64"]
    G["Maven / Gradle + Native Build Tools"] -. "điều phối" .-> B
    G -. "điều phối" .-> D
~~~

Sơ đồ mô tả vai trò logic. Cách Native Image gọi compiler/linker và các thư mục trung gian phụ thuộc bộ công cụ và phiên bản đang dùng. **Spring AOT xử lý ngữ nghĩa của Spring**, còn **CLT cung cấp toolchain macOS ở mức hệ thống**; hai phần không thay thế được nhau.

## 2. Xcode Command Line Tools là gì?

**Xcode Command Line Tools (CLT)** là bộ công cụ phát triển dòng lệnh của Apple. Với tác vụ biên dịch native trên macOS, các thành phần quan trọng gồm:

| Thành phần | Vai trò khi build native |
| --- | --- |
| `clang` | Công cụ biên dịch native/C, tham gia xử lý mã và đối tượng native theo cách Native Image/toolchain yêu cầu |
| Linker của Apple | Liên kết mã đối tượng và thư viện thành executable phù hợp với macOS |
| macOS SDK và header | Khai báo API, kiểu dữ liệu và thông tin cần thiết khi biên dịch/liên kết với nền tảng |
| `xcrun` | Tìm công cụ/SDK thuộc active developer directory |
| `xcode-select` | Chọn hoặc kiểm tra vị trí bộ công cụ phát triển đang hoạt động |

CLT thường nằm tại:

~~~text
/Library/Developer/CommandLineTools
~~~

Nếu cài toàn bộ Xcode, thư mục developer thường ở:

~~~text
/Applications/Xcode.app/Contents/Developer
~~~

**Không nhất thiết phải cài toàn bộ ứng dụng Xcode** chỉ để tạo native executable Spring Boot. Trong nhiều trường hợp, CLT đủ cung cấp compiler, linker và SDK. Tuy nhiên, cần dùng bộ phiên bản **được hỗ trợ bởi phiên bản GraalVM và macOS cụ thể**.

### Cài đặt và kiểm tra CLT

Mở Terminal trên macOS và chạy:

~~~bash
# Yêu cầu macOS cài Command Line Tools nếu chưa có.
xcode-select --install
~~~

Lệnh thường mở giao diện cài đặt của Apple; nếu CLT đã có, macOS có thể thông báo không cần cài lại. Sau khi cài xong, kiểm tra:

~~~bash
# Developer directory được chọn.
xcode-select -p

# Đường dẫn clang và linker do xcrun phân giải.
xcrun --find clang
xcrun --find ld

# SDK macOS đang được công cụ build nhìn thấy.
xcrun --sdk macosx --show-sdk-path

# Kiểm tra compiler có chạy được.
clang --version
~~~

**Kỳ vọng:** `xcode-select -p` trả về một thư mục developer hợp lệ; `xcrun` tìm được compiler và SDK; `clang --version` hiển thị phiên bản Apple clang hoặc compiler đang cấu hình. Đường dẫn/phiên bản cụ thể thay đổi theo phiên bản macOS, Xcode/CLT và cấu hình máy.

Nếu đang dùng đầy đủ Xcode, kết quả `xcode-select -p` có thể trỏ tới thư mục developer của Xcode thay vì CLT; đây không tự động là lỗi. Điều cần xác minh là công cụ và SDK được chọn hoạt động đúng.

### CLT khác gì với JDK và Native Build Tools?

Một máy muốn build Spring Boot native bằng Maven/Gradle thường cần cả ba lớp:

1. **JDK/GraalVM có Native Image**: cung cấp Java compiler/runtime cần cho build và trình biên dịch `native-image`.
2. **Apple native toolchain**: cung cấp `clang`, linker và SDK cho macOS.
3. **Công cụ build Java**: Maven/Gradle cùng Spring Boot plugin và GraalVM Native Build Tools để đưa AOT, Java compilation, native compilation vào quy trình build.

Cài CLT **không** tự cài GraalVM Native Image. Ngược lại, có `native-image` nhưng thiếu linker/SDK thì native compilation vẫn có thể thất bại.

## 3. Apple Silicon và Intel: hiểu đúng arm64, aarch64, x86_64, amd64

Các tên kiến trúc thường gặp:

| Loại Mac | Tên kiến trúc thường gặp | Cách gọi trong artifact/toolchain | Ví dụ đặc điểm |
| --- | --- | --- | --- |
| Mac dùng chip Apple Silicon (dòng M) | `arm64` hoặc `aarch64` | macOS/aarch64, macOS/arm64 | CPU theo họ ARM 64-bit |
| Mac dùng CPU Intel 64-bit | `x86_64` hoặc `amd64` | macOS/amd64, macOS/x86_64 | CPU theo họ x86 64-bit |

Trong nhiều tài liệu, **arm64 và aarch64** chỉ cùng kiến trúc ở mức cần biết cho bài này; **x86_64 và amd64** cũng là các tên tương đương. Tuy nhiên, các công cụ có thể dùng cách đặt tên khác nhau cho file phát hành hoặc Docker platform.

### Kiểm tra kiến trúc từ Terminal

~~~bash
# Kiến trúc được phiên terminal/tiến trình hiện tại nhìn thấy.
uname -m
arch

# Một cách xem phần cứng thực, hữu ích khi nghi ngờ Rosetta.
system_profiler SPHardwareDataType
~~~

Trên máy Apple Silicon, môi trường chạy ứng dụng **qua Rosetta 2** có thể khiến một số lệnh trong tiến trình đã dịch báo `x86_64`. Vì vậy, chỉ nhìn `uname -m` trong một terminal đang chạy bằng Rosetta không nhất thiết phản ánh đúng kiến trúc phần cứng.

Trên macOS hỗ trợ cơ chế này, lệnh sau có thể giúp phát hiện tiến trình đang được Rosetta dịch:

~~~bash
# Giá trị 1 thường biểu thị tiến trình hiện tại đang chạy qua Rosetta.
sysctl -n sysctl.proc_translated
~~~

Nếu khóa sysctl không tồn tại hoặc trả lỗi, không kết luận máy hỏng; cơ chế/khóa này có thể không áp dụng cho môi trường hiện tại. Có thể đối chiếu với **About This Mac** để xem chip Apple hay bộ xử lý Intel.

### Kiểm tra JDK và GraalVM đang dùng

Đừng chỉ kiểm tra phần cứng. Maven, Gradle và Native Image có thể đang dùng **JDK khác phiên Terminal mong đợi**, đặc biệt nếu cài nhiều JDK hoặc dùng SDK manager.

~~~bash
java -version
native-image --version

# Kiến trúc của JVM đang khởi chạy và Java home được chọn.
java -XshowSettings:properties -version 2>&1 | grep -E 'os.arch|java.home'

# Kiểm tra runtime mà Maven/Gradle đang thực sự gọi.
./mvnw --version
./gradlew --version
~~~

Hai lệnh wrapper cuối là **hai lựa chọn dành cho dự án Maven hoặc Gradle tương ứng**; chỉ chạy wrapper có mặt trong dự án. Nếu `native-image` không được tìm thấy, cần cài hoặc chọn bộ GraalVM có hỗ trợ Native Image và cấu hình `PATH` phù hợp theo hướng dẫn cho bản phân phối đó.

Để xem các kiến trúc mà một file executable JDK hỗ trợ, có thể dùng:

~~~bash
# Ví dụ với JDK 21; thay bằng phiên bản được dự án/GraalVM hỗ trợ.
JDK_FOR_CHECK="$(/usr/libexec/java_home -v 21)"
file "$JDK_FOR_CHECK/bin/java"
lipo -archs "$JDK_FOR_CHECK/bin/java"
~~~

`file` cho biết loại executable (ví dụ Mach-O) và có thể báo nhiều kiến trúc nếu file là **universal binary**. `lipo -archs` liệt kê các slice có trong binary. **Một file Java hỗ trợ hai kiến trúc không đồng nghĩa với tiến trình đang chạy cả hai**: khi chạy, hệ điều hành chọn một slice; kiểm tra thêm `os.arch` để biết chế độ JVM hiện tại.

## 4. Vì sao phải đồng bộ kiến trúc trong quá trình native compilation?

Giả sử bạn sử dụng Mac Apple Silicon. Bộ cài GraalVM có thể mang nhãn `macos-aarch64` cho ARM, hoặc một bản dành cho `macos-amd64`/`x86_64` cho Intel. Nếu lẫn lộn các thành phần, ví dụ chạy JDK x86_64 qua Rosetta rồi cố liên kết thư viện native arm64, quá trình build có thể lỗi kiến trúc đối tượng hoặc không tìm được binary phù hợp.

Luồng mong muốn khi build native **macOS/arm64**:

~~~text
Mac Apple Silicon
  ├─ Terminal / build process: arm64
  ├─ JDK / GraalVM Native Image: macOS arm64 (aarch64)
  ├─ Apple clang + linker + macOS SDK
  ├─ Native library/JNI có dùng: arm64 hoặc universal có arm64 slice
  └─ Kết quả: executable Mach-O arm64 cho macOS
~~~

Luồng tương tự cho **macOS/x86_64** sử dụng JDK/GraalVM và các thư viện native tương ứng x86_64. Chọn cùng kiến trúc giúp giảm lỗi link và tránh chi phí dịch mã do Rosetta.

### Rosetta 2 hữu ích khi nào?

Rosetta 2 cho phép chạy nhiều ứng dụng macOS x86_64 trên máy Apple Silicon. Trong môi trường phát triển, nó có thể hữu ích khi công cụ chỉ có bản Intel. Nhưng cần nắm rõ:

- **Rosetta là lớp dịch để chạy phần mềm x86_64**, không phải một công cụ tự động chuyển native image x86_64 thành arm64.
- Chạy Terminal, JDK hoặc trình build trong chế độ Rosetta có thể làm công cụ quan sát hệ thống báo kiến trúc của tiến trình đang dịch, khiến việc xác định toolchain khó hơn.
- Khi native compilation sử dụng thư viện C/JNI, tất cả binary và thư viện được liên kết phải tương thích với kiến trúc target; Rosetta không sửa được một liên kết Mach-O sai kiến trúc.

Khi có lựa chọn, hãy ưu tiên **GraalVM bản native đúng kiến trúc máy** và khởi chạy terminal/build tương ứng. Nếu bắt buộc duy trì luồng Intel dưới Rosetta, phải kiểm chứng toàn bộ JDK, Native Image, linker, thư viện native và executable đầu ra như một tổ hợp x86_64 nhất quán.

### Nhận diện executable sau build

Sau khi build, không đoán kiến trúc chỉ từ tên file. Dùng:

~~~bash
# Thay đường dẫn bằng executable thật do dự án sinh ra.
file target/ten-ung-dung

# Hoặc với Gradle:
file build/native/nativeCompile/ten-ung-dung

# Xem các thư viện động liên kết ở môi trường macOS.
otool -L target/ten-ung-dung
~~~

Output của `file` thường cho biết `Mach-O 64-bit executable arm64` hoặc `Mach-O 64-bit executable x86_64`. Với đường dẫn Gradle, thay vào `otool -L` tương tự. Thư mục và tên executable phụ thuộc cấu hình Maven/Gradle; ví dụ chỉ minh họa vị trí thường gặp.

## 5. Quy trình kiểm tra môi trường trước khi build

Đây là checklist chạy **trên macOS**, trước khi dành thời gian cho native compilation vốn có thể tốn CPU/RAM:

~~~bash
# 1. Kiểm tra macOS, kiến trúc phiên Terminal.
sw_vers
uname -m

# 2. Kiểm tra bộ công cụ biên dịch hệ thống.
xcode-select -p
xcrun --find clang
xcrun --sdk macosx --show-sdk-path
clang --version

# 3. Kiểm tra JDK và Native Image.
java -version
native-image --version
java -XshowSettings:properties -version 2>&1 | grep -E 'os.arch|java.home'

# 4. Kiểm tra hệ build của dự án, chọn một trong hai.
./mvnw --version
./gradlew --version
~~~

Khi mọi điều kiện đã sẵn sàng, dùng cơ chế build native của Spring Boot:

**Dự án Maven** đã khai báo `spring-boot-maven-plugin`, `native-maven-plugin` và profile phù hợp:

~~~bash
./mvnw test
./mvnw -Pnative native:compile
~~~

**Dự án Gradle** đã áp dụng plugin Spring Boot và `org.graalvm.buildtools.native`:

~~~bash
./gradlew test
./gradlew nativeCompile
~~~

Trong dự án dùng `spring-boot-starter-parent`, profile Maven `native` thường có cấu hình tích hợp phù hợp; nếu không dùng parent, phải cấu hình tương đương thay vì mặc định profile luôn tồn tại. Bên Gradle, cần sử dụng các plugin có phiên bản tương thích. Các lệnh build trên không tự cài CLT và cũng không tự chọn lại kiến trúc JDK nếu môi trường đang cấu hình sai.

Quy trình được điều phối sẽ bao gồm xử lý Spring AOT, biên dịch Java và tạo executable GraalVM Native Image. Thử chạy executable sau khi build và kiểm tra những chức năng cần reflection, resource, proxy hoặc JNI. Khả năng build thành công không bảo đảm tất cả nhánh runtime đã tương thích.

## 6. Native executable macOS không phải Linux container image

Một khác biệt rất quan trọng khi vận hành:

| Môi trường build | Đích thường nhận được | Chạy trực tiếp ở đâu? |
| --- | --- | --- |
| macOS arm64, Native Image local | Mach-O arm64 | macOS arm64 tương thích |
| macOS x86_64, Native Image local | Mach-O x86_64 | macOS x86_64, hoặc trong một số trường hợp dưới Rosetta trên Apple Silicon |
| Linux arm64, Native Image | ELF arm64 | Linux arm64 với thư viện/runtime tương thích |
| Linux amd64, Native Image | ELF x86_64 | Linux amd64 với thư viện/runtime tương thích |

**Container Linux không chạy được executable Mach-O macOS** chỉ bằng cách chép file vào image. Máy Mac có thể chạy Docker Desktop, nhưng các container thông thường vẫn sử dụng môi trường Linux trong VM. Muốn triển khai Spring Boot native trong Linux container, cần **build executable Linux** bằng một môi trường build Linux phù hợp, ví dụ builder container/VM hoặc CI runner Linux.

Với Spring Boot và Cloud Native Buildpacks, một cách tiếp cận thường dùng:

~~~bash
# Dự án Maven đã cấu hình Spring Boot plugin / buildpacks thích hợp.
./mvnw -Pnative spring-boot:build-image
~~~

Quy trình này có thể thực hiện build native trong môi trường builder Linux do container engine cung cấp. Cần kiểm tra kiến trúc của builder/run image: trên máy Apple Silicon, nền tảng container có thể là `linux/arm64`, trong khi môi trường triển khai mục tiêu có thể yêu cầu `linux/amd64`. Không nên giả định rằng chạy trên Mac arm64 sẽ tạo ra executable Linux amd64.

Khi build nhiều nền tảng, hãy dùng builder/runner phù hợp với từng OS và architecture; mô phỏng kiến trúc khác (nếu được hỗ trợ) có thể chậm và không tương thích với một số native dependency. Đặt đúng Docker platform **không tự biến một native binary đã build cho macOS thành Linux binary**, và Native Image thông thường không phải cross-compiler tổng quát chỉ cần đổi một cờ là đổi đích.

Với CI/CD, cách dễ kiểm chứng là ghi rõ:

- Hệ điều hành và kiến trúc của máy/builder native.
- Phiên bản JDK/GraalVM, Spring Boot, Native Build Tools và CLT nếu chạy macOS.
- Nền tảng của executable cuối cùng, kiểm chứng bằng `file` (macOS/Linux) và kiểm thử trên runtime tương ứng.
- Tài nguyên CPU/RAM khi so sánh thời gian build, startup và mức dùng bộ nhớ giữa JVM và native.

## 7. Các lỗi thường gặp trên macOS và cách xử lý

| Triệu chứng | Nguyên nhân nên kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `xcrun: error: invalid active developer path` | CLT bị thiếu, di chuyển hoặc developer directory trỏ sai | Cài/khôi phục CLT; kiểm tra `xcode-select -p`, `xcrun --find clang` |
| `clang` hoặc linker không được tìm thấy | CLT chưa cài hoặc không được chọn | Cài CLT, kiểm tra SDK và active developer directory |
| Không tìm thấy `native-image` | JDK/GraalVM chưa có Native Image hoặc `PATH`/`JAVA_HOME` đang trỏ sai | Chọn bản GraalVM phù hợp, kiểm tra `java -version`, `native-image --version` |
| `wrong architecture`, `incompatible architecture` hoặc lỗi link thư viện native | JDK/GraalVM, object file, JNI library không thống nhất arm64/x86_64 | Kiểm tra `file`, `lipo -archs`, `os.arch`; chọn lại các binary đúng target |
| Lệnh báo x86_64 trên máy Apple Silicon | Terminal/JDK có thể chạy dưới Rosetta | Kiểm tra chip máy và chế độ tiến trình, khởi chạy công cụ arm64 nếu muốn build arm64 |
| Build native trên Mac thành công nhưng container Linux không chạy | Artifact Mach-O được đưa vào Linux image | Dùng builder Linux và biên dịch native cho Linux/kiến trúc triển khai |
| macOS SDK không được tìm thấy | Active developer directory hoặc cài đặt CLT/Xcode không hợp lệ | Kiểm tra `xcrun --sdk macosx --show-sdk-path`; sửa cài đặt và lựa chọn toolchain |
| Native build hết RAM, thời gian quá lâu | Chi phí phân tích/biên dịch của Native Image; có thể thêm chi phí dịch kiến trúc | Đảm bảo tài nguyên build, dùng JDK native đúng kiến trúc và giảm dependency không cần |

Nếu developer directory thật sự bị chọn sai, có thể chọn lại **đúng thư mục đã được cài**:

~~~bash
# Chỉ chạy nếu thư mục CLT này thực sự tồn tại và cần chọn nó.
sudo xcode-select --switch /Library/Developer/CommandLineTools

# Kiểm tra lại sau thay đổi.
xcode-select -p
xcrun --find clang
~~~

Lệnh `sudo xcode-select --switch` thay đổi lựa chọn developer directory trên máy; chỉ dùng khi đã xác nhận đường dẫn đúng. Nếu đang cần bộ công cụ của Xcode đầy đủ cho tác vụ khác, lựa chọn phù hợp có thể là developer directory của Xcode thay vì CLT.

Không phải mọi lỗi Native Image đều liên quan CLT. Nếu build đã qua bước linker nhưng ứng dụng lỗi khi reflection, resource hoặc serialization lúc chạy, nên kiểm tra **Spring AOT runtime hints và khả năng hỗ trợ của dependency**, không cài đi cài lại CLT.

## 8. Bài thực hành: xác nhận đúng môi trường macOS

**Tình huống:** một ứng dụng Spring Boot có endpoint HTTP chạy được bằng JAR; bạn muốn tạo native executable trên Mac, thử startup/memory và sau đó đóng gói chạy trên Linux container.

Thực hiện theo trình tự:

1. **Xác định chip và OS**: xem About This Mac, sau đó chạy `uname -m` và `sw_vers`. Nếu máy Apple Silicon nhưng lệnh báo x86_64, kiểm tra terminal/Rosetta.
2. **Xác định Apple toolchain**: chạy `xcode-select -p`, `xcrun --find clang`, `xcrun --sdk macosx --show-sdk-path`. Đảm bảo compiler/linker/SDK được tìm thấy.
3. **Xác định Java toolchain**: chạy `java -version`, `native-image --version` và xem `os.arch`. Với Maven/Gradle, kiểm tra wrapper có chạy bằng JDK dự kiến.
4. **Build bằng hệ công cụ của dự án**: chọn `./mvnw -Pnative native:compile` hoặc `./gradlew nativeCompile` khi plugin/profile đã cấu hình đúng. Theo dõi log phân biệt lỗi Java/AOT, Native Image hay compiler/linker.
5. **Kiểm tra artifact**: dùng `file` để biết executable là Mach-O arm64 hay x86_64. Chạy thử trên macOS tương thích và kiểm thử các luồng quan trọng.
6. **So sánh bản JVM với bản native**: cùng request, dữ liệu và giới hạn CPU/RAM; đo thời gian tới khi sẵn sàng, RSS và độ trễ. Ghi cả chi phí build, không suy từ kích thước file ra mức dùng bộ nhớ.
7. **Triển khai container Linux**: thực hiện build bằng builder Linux phù hợp với `linux/amd64` hoặc `linux/arm64` đích, không sao chép Mach-O của Mac vào container Linux. Kiểm tra và chạy image trên môi trường tương thích.

### Mẫu bảng ghi kết quả

| Mục đo | JVM JAR trên macOS | Native macOS | Native Linux container |
| --- | --- | --- | --- |
| OS/CPU kiến trúc | macOS / … | macOS / … | Linux / … |
| Java/GraalVM version | … | … | … |
| Toolchain/linker/SDK | Không dùng cho việc chạy JAR | CLT / … | Linux builder / … |
| Thời gian build | … | … | … |
| Thời gian sẵn sàng | … | … | … |
| RSS khi ổn định | … | … | … |
| Kiểm thử chức năng | Pass/Fail | Pass/Fail | Pass/Fail |

Không điền số giả định vào bảng: giá trị phụ thuộc ứng dụng, tải, công cụ và phần cứng thực tế. Cũng không so sánh trực tiếp Mac arm64 với container Linux amd64 như thể chỉ có JVM/native thay đổi; hãy kiểm soát biến số hoặc ghi rõ giới hạn so sánh.

## 9. Câu hỏi tự kiểm tra

**1. Đã cài GraalVM nhưng `native:compile` báo thiếu linker. Cần kiểm tra gì trước?**

Kiểm tra CLT, active developer directory và macOS SDK bằng `xcode-select -p`, `xcrun --find clang`, `xcrun --sdk macosx --show-sdk-path`. Native Image cần toolchain nền tảng ngoài JDK.

**2. Máy dùng Apple Silicon nhưng `java` chạy ở `x86_64`. Có chắc Native Image sẽ ra arm64 không?**

Không. Cần kiểm tra binary JDK/GraalVM thực dùng, chế độ Rosetta, dependency native và kết quả `file` sau build. Hãy chọn bộ công cụ đồng nhất với kiến trúc muốn biên dịch.

**3. Có thể chép trực tiếp executable build trên macOS vào Docker image Linux rồi chạy không?**

Không. Mach-O macOS và ELF Linux là định dạng/thực thi nền tảng khác nhau. Cần build trong môi trường Linux cho kiến trúc triển khai thích hợp.

**4. Xcode CLT giúp Spring AOT biết thêm bean hoặc thêm reflection hints không?**

Không. CLT cung cấp compiler, linker và SDK. Spring AOT cùng runtime hints xử lý khía cạnh Spring và truy cập động; GraalVM Native Image dùng kết quả đó để biên dịch.

Nắm vững **CLT + kiến trúc CPU + JDK/GraalVM + nền tảng triển khai** giúp tránh nhiều lỗi build môi trường trước khi đi sâu vào tương thích reflection/resource, kiểm thử native và benchmark Spring Boot Native Image.
