# CPU target và khả năng chạy binary trên những máy có tập lệnh khác nhau

Một native executable của Spring Boot không chỉ phụ thuộc vào hệ điều hành và kiến trúc CPU như Linux/AMD64 hay Linux/AArch64. Nó còn phụ thuộc vào **tập lệnh CPU (instruction set)** mà GraalVM đã cho phép compiler sử dụng khi tạo binary.

Hai máy cùng chạy Linux x86-64 vẫn có thể không chạy được cùng một native executable nếu CPU của máy đích thiếu một tập lệnh mà binary yêu cầu. Tình huống thường gặp là binary được build trên máy mới với AVX2, FMA hoặc một nhóm lệnh khác, sau đó triển khai lên máy cũ hơn hoặc VM/cloud instance có CPU features bị giới hạn.

GraalVM Native Image cung cấp tùy chọn `-march` để chọn mức CPU mục tiêu. Chọn đúng mức này giúp cân bằng hiệu năng với phạm vi máy có thể chạy binary. Bài học tập trung vào cách hiểu ISA target, chọn baseline, cấu hình Maven/Gradle/Buildpacks, xử lý lỗi không tương thích và kiểm thử trên các nhóm máy đích.

## 1. Hai trục tương thích cần phân biệt

Khi phát hành native executable, cần kiểm tra hai lớp tương thích độc lập:

1. **Platform target:** hệ điều hành và kiến trúc CPU mà executable được tạo cho, ví dụ Linux/AMD64 hoặc Linux/AArch64.
2. **CPU instruction-set target:** các lệnh CPU cụ thể mà compiler được phép phát ra trên kiến trúc đó, ví dụ x86-64-v2 hoặc x86-64-v3.

Native Image có hai tùy chọn tương ứng:

| Tùy chọn | Điều khiển | Ví dụ | Không có nghĩa là |
| --- | --- | --- | --- |
| `--target` | Platform gồm OS và CPU architecture | `linux-amd64`, `linux-aarch64` nếu toolchain hỗ trợ | Không chọn mức AVX/SSE hay CPU microarchitecture |
| `-march` | Mức tập lệnh CPU cho Graal compiler | `-march=x86-64-v3`, `-march=compatibility` | Không đổi Linux thành Windows hoặc AMD64 thành AArch64 |

Ví dụ, `linux-amd64` chỉ xác định executable dành cho Linux trên AMD64. Nó không nói binary cần baseline x86-64-v1, v2, v3 hay v4.

Một container image gắn nhãn `linux/amd64` cũng chưa mô tả đầy đủ CPU requirement. Hai node đều báo AMD64 nhưng một node có AVX2, node còn lại không có, vẫn có thể cho kết quả chạy khác nhau.

### Vị trí của CPU target trong pipeline Spring Boot

~~~mermaid
flowchart TD
    A["Java source và dependencies"] --> B["Spring AOT"]
    B --> C["Generated source, bytecode và hints"]
    C --> D["GraalVM Native Image build"]
    D --> E["Chọn OS/architecture target"]
    E --> F["Chọn CPU ISA bằng -march"]
    F --> G["Native executable"]
    G --> H["Kiểm tra CPU và OS của máy triển khai"]
    H --> I{"Đủ platform và CPU features?"}
    I -->|Có| J["Chạy ứng dụng"]
    I -->|Không| K["Build lại cho target phù hợp"]
~~~

Spring AOT chuẩn bị code và metadata cho ứng dụng. CPU target được quyết định ở bước GraalVM Native Image build, sau khi có đầu vào AOT.

## 2. Instruction set là gì?

Instruction set là tập các lệnh mà CPU có thể thực thi. Một số nhóm lệnh phổ biến:

- SSE và các phiên bản mở rộng trên x86.
- AVX, AVX2 và AVX-512 trên các CPU x86-64 tương ứng.
- BMI1, BMI2, FMA và F16C trên một số thế hệ x86.
- Các extension trên AArch64 như AES, SHA, CRC32, LSE hoặc SVE tùy CPU và toolchain.

Compiler có thể tối ưu một đoạn code bằng những lệnh mới hơn. Nếu binary chứa lệnh mà CPU đích không hỗ trợ, tiến trình có thể từ chối khởi chạy hoặc gặp lỗi illegal instruction khi đi tới đoạn code đó.

### Các mức x86-64

Trên AMD64, các mức microarchitecture thường được đặt tên x86-64-v1, v2, v3 và v4. Các mức này có tính tích lũy: mức cao hơn bao gồm các yêu cầu của mức thấp hơn.

| Mức | Khái quát | Hệ quả khi triển khai |
| --- | --- | --- |
| x86-64-v1 | Baseline x86-64 ban đầu, gồm các lệnh nền như SSE2 | Phạm vi CPU cũ rộng nhất trong các mức x86-64 phổ biến |
| x86-64-v2 | Bổ sung các extension như SSE3, SSSE3, SSE4.1, SSE4.2 và POPCNT | Cần CPU hỗ trợ nhóm lệnh bổ sung của v2 |
| x86-64-v3 | Bổ sung AVX, AVX2, BMI1, BMI2, FMA và một số extension khác | Không chạy trên CPU thiếu AVX2 hoặc các feature bắt buộc khác của v3 |
| x86-64-v4 | Bổ sung nhóm AVX-512 tương ứng | Chỉ triển khai trên CPU và môi trường hệ điều hành hỗ trợ đầy đủ các feature của v4 |

Đây là bảng khái quát, không phải danh sách CPUID đầy đủ. Một số extension còn yêu cầu hệ điều hành bật và lưu trạng thái thanh ghi phù hợp. Tên model CPU hoặc năm sản xuất chỉ là gợi ý; hãy kiểm tra feature flags thực tế của máy đích.

### AArch64

AArch64 có các mức kiến trúc như `armv8-a` và các phiên bản mở rộng sau đó. Không nên áp dụng tên mức x86-64 cho ARM. Một máy ARM có thể hỗ trợ AES hoặc LSE trong khi máy ARM khác cùng kiến trúc cơ bản không có cùng extension.

Danh sách target và feature được GraalVM hỗ trợ thay đổi theo phiên bản và platform. Dùng `native-image -march=list` và `native-image --list-cpu-features` trên đúng toolchain để biết các lựa chọn thực tế.

## 3. Tùy chọn -march của GraalVM

GraalVM Native Image cung cấp `-march` để điều khiển tập lệnh mà Graal compiler được phép sử dụng khi tạo native code.

Các lựa chọn thường gặp:

| Cấu hình | Hành vi | Khi nên dùng |
| --- | --- | --- |
| `-march=compatibility` | Chọn tập lệnh bảo thủ, giảm yêu cầu CPU để tăng khả năng chạy trên máy cũ | Phân phối binary cho nhiều máy hoặc fleet có CPU không đồng nhất |
| `-march=native` | Cho compiler sử dụng các CPU feature được nhận diện trên máy build | Build và chạy trên cùng máy hoặc fleet có cùng feature set |
| `-march=x86-64-v2` | Chọn rõ mức x86-64-v2 nếu toolchain liệt kê hỗ trợ | Khi đã xác định toàn bộ máy đích đáp ứng baseline v2 |
| `-march=x86-64-v3` | Chọn rõ mức x86-64-v3 nếu toolchain liệt kê hỗ trợ | Fleet có baseline v3 đã được kiểm chứng |
| `-march=list` | In các machine type mà Native Image có thể nhắm tới | Khảo sát target hợp lệ trước khi cấu hình |

`-march=native` có thể tận dụng AVX2, AES, LSE hoặc các feature mà máy build cung cấp. Đổi lại, binary có thể không chạy trên máy khác dù máy đó cùng kiến trúc CPU.

`-march=compatibility` giảm các yêu cầu ISA để mở rộng phạm vi máy chạy được. Điều đó có thể làm giảm một số cơ hội tối ưu, nhưng không có nghĩa mọi workload đều chậm đi đáng kể. Hãy benchmark bằng workload thật.

### Mặc định thay đổi theo GraalVM version

Không nên giả định mọi phiên bản GraalVM dùng cùng một mặc định:

- Trong GraalVM for JDK 17/20, thay đổi ở dòng 23.0 đặt mặc định AMD64 thành `x86-64-v3`; trước đó `compatibility` là mặc định.
- Tài liệu hiện hành mô tả mặc định x64 là `x86-64-v3`.
- Mặc định AArch64 đã thay đổi theo release và tài liệu phiên bản. Một số release notes ghi `armv8.1-a`, trong khi trang tối ưu hóa của một số release liệt kê `armv8-a`.

Vì vậy, **build output của chính toolchain đang chạy là bằng chứng cuối cùng về machine type được chọn**. Khi nâng GraalVM, hãy xem lại dòng target machine trong build output và chạy lại test trên nhóm CPU thấp nhất được hỗ trợ.

## 4. Khảo sát machine type và CPU features trước khi build

Chạy các lệnh sau bằng đúng GraalVM JDK có Native Image:

~~~bash
# Phiên bản Native Image đang dùng.
native-image --version

# Các machine type có thể chọn.
native-image -march=list

# Các CPU feature mà target platform của toolchain nhận diện.
native-image --list-cpu-features
~~~

Hai lệnh cuối trả lời hai câu hỏi khác nhau:

- `-march=list` cho biết tên các mức machine type mà compiler nhận hỗ trợ.
- `--list-cpu-features` cho biết danh sách feature của target platform mà toolchain có thể sử dụng.

Nếu cần xem CPU của Linux host, có thể dùng:

~~~bash
lscpu
grep -m 1 '^flags' /proc/cpuinfo
~~~

Trong VM hoặc container, danh sách feature mà guest nhìn thấy có thể bị hypervisor hoặc cấu hình container giới hạn. Đừng chỉ dựa vào model CPU của máy vật lý bên dưới.

### Đọc build output

Native Image build output có phần thông tin Graal compiler, thường hiển thị optimization level và target machine. Ví dụ:

~~~text
Graal compiler: optimization level: 2, target machine: x86-64-v3
C compiler: gcc (linux, x86_64, ...)
~~~

Nếu build output cho thấy `x86-64-v3` thì binary được build theo mức đó, dù lệnh build không ghi rõ `-march`. Đây là lý do cần lưu build log hoặc machine-readable build report cùng artifact.

## 5. Chọn baseline theo môi trường triển khai

Chọn CPU target dựa trên tập máy thực sự chạy binary, không dựa trên máy của lập trình viên.

| Môi trường | Chiến lược đề xuất | Lý do |
| --- | --- | --- |
| Một máy chủ cố định, build và deploy cùng máy | Cân nhắc `-march=native` | Có thể dùng toàn bộ feature của CPU đã biết |
| Fleet cloud đồng nhất và có baseline được xác nhận | Chọn mức ISA cụ thể hoặc `native` nếu build host tương đương | Tận dụng tối ưu nhưng vẫn kiểm soát compatibility |
| Fleet có nhiều thế hệ CPU AMD64 | `-march=compatibility` hoặc baseline thấp nhất được fleet hỗ trợ | Tránh binary yêu cầu lệnh mà node cũ thiếu |
| Phần mềm phân phối cho khách hàng không kiểm soát phần cứng | `-march=compatibility` | Tăng xác suất chạy trên nhiều CPU |
| Hệ thống chỉ triển khai trên ARM | Build target AArch64 và chọn feature baseline phù hợp | AMD64 binary không thể chạy trực tiếp trên ARM64 |
| Hỗn hợp AMD64 và AArch64 | Tạo artifact riêng cho từng OS/architecture | Một native executable không phải binary đa kiến trúc |

### Ví dụ lựa chọn

Một hệ thống có 30 node AMD64, trong đó 10 node cũ chỉ đáp ứng baseline thấp hơn v3. Nếu build trên workstation mới bằng mặc định v3, một phần fleet có thể không chạy được binary.

Có hai cách thiết kế:

- Build một binary dùng baseline chung thấp nhất mà cả fleet đáp ứng.
- Tạo nhiều biến thể binary và điều phối artifact theo pool máy có CPU feature tương ứng.

Cách thứ hai có thể giữ tối ưu cho node mới nhưng làm tăng số lượng artifact, pipeline build và ma trận kiểm thử.

## 6. Phân biệt lỗi CPU ISA với lỗi OS/ABI

Một binary có thể dùng ISA tương thích nhưng vẫn không chạy được do khác biệt nền tảng.

| Vấn đề | Ví dụ | Cách xử lý |
| --- | --- | --- |
| CPU ISA không tương thích | Binary yêu cầu AVX2, CPU đích không có AVX2 | Build lại với `-march` thấp hơn |
| CPU architecture khác | Binary AMD64 chạy trên AArch64 | Build executable riêng cho AArch64 |
| OS khác | Binary Linux chạy trực tiếp trên Windows | Build cho OS đích |
| libc khác | Binary phụ thuộc glibc nhưng runtime image chỉ có musl | Chọn builder/runtime phù hợp và kiểm tra linkage |
| Native library không tương thích | JNI library được biên dịch với ISA cao hơn binary chính | Thay hoặc rebuild native dependency với baseline phù hợp |

`-march=compatibility` chỉ giải quyết phạm vi instruction set của code mà Native Image compiler tạo ra. Nó không biến Linux binary thành Windows binary, không thay libc và không sửa một thư viện JNI đã được biên dịch với CPU requirement cao hơn.

## 7. Vì sao Spring AOT không quyết định CPU target?

Spring AOT phân tích ApplicationContext và sinh code/hints để Native Image xử lý. Các file AOT này vẫn là đầu vào có thể đóng gói trong executable JAR.

GraalVM Native Image mới là bước tạo machine code cho một OS/architecture và CPU target cụ thể.

Spring Boot hỗ trợ giữ một pipeline tạo executable JAR đã có AOT assets, sau đó chuyển JAR đó thành native image ở bước CI/CD phù hợp. Cách này giúp dùng lại artifact Java trung gian cho nhiều build target, nhưng mỗi native executable vẫn phải được tạo riêng cho platform cần triển khai.

### Native Image không phải cross-compiler tổng quát

Tùy chọn `--target` có thể chọn OS/architecture target theo dạng mà toolchain hỗ trợ, nhưng không nên hiểu rằng chỉ cần đặt `--target` là có thể cross-compile từ bất kỳ máy build nào sang bất kỳ OS/CPU nào.

Tài liệu Spring Boot nêu rõ Native Image không hỗ trợ cross-compilation theo mô hình build tổng quát. Khi cần nhiều platform, hãy dùng build worker hoặc buildpack chạy trên platform tương ứng. Một JAR có AOT assets có thể là đầu vào dùng lại; executable native cần được tạo trong môi trường build phù hợp.

## 8. Cấu hình Maven Native Build Tools

Với dự án Spring Boot dùng `native-maven-plugin`, truyền `-march` qua `buildArgs`.

Ví dụ chọn baseline tương thích:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>-march=compatibility</buildArg>
        </buildArgs>
    </configuration>
</plugin>
~~~

Nếu dự án đã có cấu hình plugin trong parent POM hoặc profile `native`, thêm argument vào cấu hình hiện tại thay vì tạo một khai báo plugin thứ hai.

Build executable:

~~~bash
./mvnw -Pnative native:compile
~~~

Nếu cần baseline v2 đã được kiểm tra trên fleet:

~~~xml
<buildArgs>
    <buildArg>-march=x86-64-v2</buildArg>
</buildArgs>
~~~

Chỉ dùng machine type cụ thể nếu `native-image -march=list` của đúng GraalVM toolchain liệt kê nó và mọi máy đích đáp ứng các feature tương ứng.

Native Build Tools nhận mỗi `buildArg` như một option expression riêng. Không đặt cả chuỗi lệnh shell vào một thẻ buildArg.

## 9. Cấu hình Gradle Native Build Tools

Với Groovy DSL:

~~~groovy
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add("-march=compatibility")
        }
    }
}
~~~

Nếu chỉ build cho fleet đã xác nhận x86-64-v3:

~~~groovy
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add("-march=x86-64-v3")
        }
    }
}
~~~

Build executable:

~~~bash
./gradlew nativeCompile
~~~

Nếu project có nhiều binary như `main` và `test`, hãy quyết định option áp dụng cho từng binary. Dùng cấu hình chung cho mọi binary chỉ khi tất cả đều nhắm cùng platform và CPU baseline.

### Kotlin DSL

Với `build.gradle.kts`, cấu hình cùng Native Build Tools extension:

~~~kotlin
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add("-march=compatibility")
        }
    }
}
~~~

Cú pháp API cụ thể có thể khác theo phiên bản plugin. Kiểm tra Native Build Tools version đang được quản lý trong build và dùng `buildArgs` của binary tương ứng.

## 10. Truyền CPU target khi dùng Cloud Native Buildpacks

Spring Boot có thể dùng Paketo Buildpacks để tạo container image chứa native executable. Native Image buildpack cung cấp biến môi trường:

`BP_NATIVE_IMAGE_BUILD_ARGUMENTS`

Biến này truyền argument trực tiếp tới lệnh `native-image`. Ví dụ dùng `pack` với AOT-processed executable JAR:

~~~bash
pack build orders-api:0.1.0 \
  --path target/orders-api.jar \
  --env BP_NATIVE_IMAGE=true \
  --env BP_NATIVE_IMAGE_BUILD_ARGUMENTS=-march=compatibility
~~~

JAR đầu vào cần có các AOT generated assets. Buildpack thực hiện Native Image build trong builder container và đưa executable vào application image.

Một số điểm cần kiểm tra:

- Builder image và buildpack phải hỗ trợ OS/architecture cần tạo.
- Builder chạy trên kiến trúc nào và CPU feature nào có thể ảnh hưởng việc phát hiện `-march=native`.
- Khi dùng builder qua giả lập CPU, không nên giả định feature được báo giống máy triển khai thật.
- Hãy lưu lại buildpack/builder version, GraalVM version và build output.
- Runtime image phải tương thích với OS, architecture và libc của executable.

Với Maven/Gradle Spring Boot plugin, có thể cấu hình environment cho image build theo API của plugin đang dùng. Khi cần kiểm soát rõ, kiểm tra buildpack environment đã được truyền tới build phase và xác minh log `native-image` có nhận argument.

## 11. Tạo artifact cho nhiều OS và architecture

Nếu dịch vụ cần chạy trên Linux AMD64 và Linux AArch64, pipeline nên tạo hai native artifacts riêng:

~~~mermaid
flowchart TD
    A["Source code"] --> B["Spring AOT"]
    B --> C["Executable JAR có AOT assets"]
    C --> D["Build worker Linux AMD64"]
    C --> E["Build worker Linux AArch64"]
    D --> F["Native binary AMD64"]
    E --> G["Native binary AArch64"]
    F --> H["Container image linux/amd64"]
    G --> I["Container image linux/arm64"]
    H --> J["Multi-platform manifest"]
    I --> J
~~~

Có thể lưu executable JAR đã AOT như artifact trung gian. Mỗi build worker dùng GraalVM Native Image và native toolchain phù hợp để tạo executable cho target của nó.

### Container manifest không thay thế CPU baseline

Multi-platform OCI image có thể chứa manifest cho `linux/amd64` và `linux/arm64`. Khi pull, container runtime chọn image theo OS/architecture.

Tuy nhiên, manifest không tự kiểm tra đầy đủ x86-64-v2/v3/v4. Nếu binary AMD64 được build theo v3, image vẫn có thể mang nhãn `linux/amd64` nhưng không chạy trên node AMD64 thiếu feature v3.

Với fleet AMD64 không đồng nhất, cần thống nhất baseline ISA ở build pipeline hoặc điều phối deployment theo capability của node.

## 12. Lỗi CPU feature mismatch và cách chẩn đoán

Một lỗi thường gặp khi chạy binary trên CPU cũ có dạng:

~~~text
The current machine does not support all of the following CPU features
that are required by the image: [ ... ]
Please rebuild the executable with an appropriate setting
of the -march option.
~~~

Danh sách feature trong thông báo cho biết binary cần những lệnh nào mà CPU hiện tại không cung cấp.

Quy trình xử lý:

1. Ghi lại GraalVM version và target machine type trong build output.
2. Kiểm tra CPU features của máy build và máy đích.
3. Xác định binary được build với `-march=native`, mặc định version hay mức ISA được chỉ định.
4. Chọn `-march=compatibility` hoặc mức cụ thể thấp hơn mà toàn bộ máy đích hỗ trợ.
5. Build lại binary và triển khai thử trên máy có baseline thấp nhất.
6. Nếu lỗi vẫn là illegal instruction, kiểm tra thêm JNI/C/C++ native libraries và thư viện hệ thống.

### Phân biệt lỗi feature với lỗi kiến trúc

| Triệu chứng | Khả năng cao | Hướng kiểm tra |
| --- | --- | --- |
| Thông báo thiếu AVX2, BMI2, FMA hoặc feature tương tự | CPU target quá cao | Giảm `-march` |
| Binary báo sai executable format | Sai OS hoặc CPU architecture | Kiểm tra `file`, platform và build target |
| `Exec format error` trên ARM | Đang chạy binary AMD64 trên ARM hoặc ngược lại | Build binary đúng architecture |
| `Illegal instruction`/`SIGILL` | CPU thiếu instruction hoặc native dependency có ISA cao | Kiểm tra binary và các JNI/shared libraries |
| Lỗi thiếu `libc.so` hoặc shared library | Runtime image thiếu ABI/library cần thiết | Kiểm tra dynamic dependencies và runtime base image |

Không nên chỉ thay `-march` khi lỗi thực chất do sai OS, architecture hoặc libc.

## 13. Native libraries và JNI cũng cần cùng baseline

`-march` của Native Image điều khiển instruction set mà Graal compiler sử dụng cho native code do nó sinh ra. Ứng dụng Spring Boot có thể còn phụ thuộc vào native code bên ngoài:

- JNI libraries.
- Thư viện C/C++ đóng gói trong JAR.
- Database driver có native component.
- Compression, cryptography hoặc image processing libraries.
- Shared libraries được nạp qua `System.loadLibrary`.

Một thư viện C/C++ có thể đã được build riêng với AVX2 hoặc AVX-512. Khi đó, dù application binary dùng `-march=compatibility`, tiến trình vẫn có thể gặp `SIGILL` khi gọi thư viện đó trên CPU cũ.

Khi nghi ngờ:

1. Liệt kê shared libraries được đóng gói hoặc được nạp runtime.
2. Kiểm tra tài liệu CPU requirement của nhà cung cấp.
3. Dùng công cụ hệ điều hành để kiểm tra dependency, ví dụ `ldd` trên Linux.
4. Nếu có quyền build native library, chọn baseline tương thích hoặc dùng runtime dispatch có kiểm thử.
5. Chạy integration test trên máy có feature thấp nhất trong fleet.

Không phải mọi thư viện đều cần build với baseline thấp nhất. Một số thư viện có thể chọn implementation bằng runtime CPU dispatch. Hãy xác minh cơ chế dispatch thực tế thay vì giả định.

## 14. Đo hiệu năng trước khi chọn baseline

Chọn `-march=native` có thể giúp compiler dùng thêm instruction set và cải thiện một số workload. Mức tăng phụ thuộc code path, tỷ lệ CPU-bound, thư viện native, memory access và tải thực tế.

Để so sánh có ý nghĩa, tạo hai binary từ cùng source và cùng GraalVM version:

- Binary A: `-march=compatibility`.
- Binary B: `-march=native` hoặc mức ISA cụ thể của fleet.

Giữ nguyên các điều kiện khác:

- Cùng optimization level, GC, heap limit và dependency versions.
- Cùng container base image và OS.
- Cùng CPU/VM để đo performance nếu cả hai binary đều chạy được.
- Cùng request mix, dataset, concurrency và thời gian warm-up.
- Đo throughput, p50/p95/p99 latency, CPU, memory và error rate.

Không benchmark binary A trên máy cũ rồi binary B trên máy mới và quy toàn bộ chênh lệch cho `-march`. CPU model, memory, kernel, virtualization và network đều có thể ảnh hưởng kết quả.

### Chỉ số nên ghi lại

| Chỉ số | Mục đích |
| --- | --- |
| Build target machine | Xác nhận ISA đã chọn |
| Startup/ready time | Xem có khác biệt khởi động |
| Throughput | Đo số request xử lý mỗi giây |
| p95/p99 latency | Đánh giá đuôi độ trễ |
| CPU utilization | Xem hiệu quả sử dụng CPU |
| Peak RSS/container memory | Theo dõi chi phí bộ nhớ |
| Error rate | Xác nhận binary hoạt động đúng |
| CPU model và feature flags | Ghi lại môi trường benchmark |

`-march` chỉ là một biến trong tối ưu native. Không thay đổi GC, PGO, optimization level và CPU target cùng lúc nếu mục tiêu là hiểu tác động của từng lựa chọn.

## 15. Checklist trước khi phát hành native executable

- [ ] Đã ghi rõ OS và architecture đích.
- [ ] Đã xác định CPU baseline thấp nhất trong fleet.
- [ ] Đã kiểm tra mặc định `-march` của GraalVM version đang dùng.
- [ ] Đã kiểm tra `native-image -march=list`.
- [ ] Đã kiểm tra CPU features của máy build và máy triển khai.
- [ ] Không dùng `-march=native` trên CI runner không đại diện cho máy đích.
- [ ] Đã cấu hình `-march` qua Maven, Gradle hoặc Buildpacks.
- [ ] Đã kiểm tra builder image và runtime image tương thích.
- [ ] Đã kiểm tra JNI/shared libraries có yêu cầu ISA riêng hay không.
- [ ] Đã test binary trên CPU thấp nhất được hỗ trợ.
- [ ] Đã lưu GraalVM version, build output và machine type cùng artifact.
- [ ] Nếu hỗ trợ nhiều OS/architecture, đã tạo và test binary riêng cho từng target.

## 16. Bài thực hành: build hai CPU target và kiểm tra khả năng chạy

Giả sử dịch vụ `orders-api` được triển khai trên một fleet Linux AMD64 có nhiều thế hệ CPU. Mục tiêu là tạo một binary chạy được trên baseline chung và so sánh với binary tối ưu cho máy build.

### Phần A — khảo sát toolchain

Chạy:

~~~bash
native-image --version
native-image -march=list
native-image --list-cpu-features
~~~

Ghi lại GraalVM version, các machine type có thể chọn và CPU features.

### Phần B — build binary tương thích

Với Maven, cấu hình plugin để truyền:

~~~xml
<buildArgs>
    <buildArg>-march=compatibility</buildArg>
</buildArgs>
~~~

Sau đó build:

~~~bash
./mvnw -Pnative native:compile -DskipTests
~~~

Với Gradle, cấu hình:

~~~groovy
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add("-march=compatibility")
        }
    }
}
~~~

Sau đó chạy:

~~~bash
./gradlew nativeCompile
~~~

### Phần C — build binary theo máy build

Tạo một build variant riêng và truyền:

~~~text
-march=native
~~~

Chạy cả hai binary trên máy build. So sánh build output để xác nhận target machine khác nhau. Đo throughput và latency bằng cùng một workload.

### Phần D — kiểm thử máy đích

1. Chọn một máy/VM có CPU feature set thấp nhất trong fleet.
2. Chạy binary compatibility và gửi request tới endpoint health/business.
3. Chạy binary native-target trên cùng máy để xác định có thiếu feature hay không.
4. Nếu có lỗi, ghi lại feature được báo và chọn baseline thấp hơn.
5. Chạy thêm test trên các node AMD64 mới hơn.
6. Nếu hệ thống có ARM64, tạo build riêng trên worker AArch64 và kiểm tra container image `linux/arm64`.

### Câu hỏi tự kiểm tra

1. Vì sao hai máy cùng AMD64 vẫn có thể không chạy cùng một native executable?
2. `-march` khác `--target` ở điểm nào?
3. Vì sao `-march=native` có thể gây lỗi khi build trên CI rồi deploy lên máy cũ?
4. `-march=compatibility` tác động đến khả năng tối ưu như thế nào?
5. Vì sao cần kiểm tra CPU features trong VM/container thay vì chỉ xem model CPU vật lý?
6. Vì sao nhãn OCI `linux/amd64` không thể hiện đầy đủ x86-64-v2/v3/v4?
7. Tại sao Spring AOT JAR có thể dùng lại nhưng native executable vẫn cần build riêng theo platform?
8. Vì sao `--target` không nên được xem là giải pháp cross-compilation tổng quát?
9. Một JNI library có thể làm ứng dụng gặp `SIGILL` dù Graal compiler dùng `-march=compatibility` không?
10. Cần giữ những điều kiện nào cố định để benchmark hai CPU target công bằng?

**Tiêu chí đạt:** giải thích được khác biệt giữa OS/architecture target và CPU instruction-set target; chọn được `-march` dựa trên fleet thực tế; cấu hình thành công qua Maven, Gradle hoặc Buildpacks; phân tích được lỗi thiếu CPU feature; kiểm thử binary trên máy có baseline thấp nhất; đồng thời tạo artifact riêng khi triển khai nhiều OS/architecture.

## Tài liệu chính thức

- GraalVM — Optimizations and Performance: https://www.graalvm.org/jdk25.5/reference-manual/native-image/optimizations-and-performance/
- GraalVM — Command-line Options: https://www.graalvm.org/jdk25.5/reference-manual/native-image/overview/Options/
- GraalVM — Native Image Build Output: https://www.graalvm.org/latest/reference-manual/native-image/overview/BuildOutput/
- GraalVM — Native Image Changelog: https://github.com/oracle/graal/blob/master/substratevm/CHANGELOG.md
- GraalVM Native Build Tools — Maven Plugin: https://graalvm.github.io/native-build-tools/latest/maven-plugin.html
- GraalVM Native Build Tools — Gradle Plugin: https://graalvm.github.io/native-build-tools/latest/gradle-plugin
- Spring Boot — Advanced Native Images Topics: https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html
- Paketo — Native Image Buildpack: https://github.com/paketo-buildpacks/native-image
