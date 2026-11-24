# Liên kết động, liên kết tĩnh và điều kiện dùng glibc hoặc musl

## 1. Vì sao cần chọn chế độ liên kết?

Trong module **SPRING_BOOT_NATIVE_IMAGE**, Spring AOT phân tích cấu trúc ứng dụng rồi GraalVM Native Image biên dịch phần code có thể truy cập thành executable dành cho hệ điều hành và kiến trúc đích. Executable này vẫn có thể phụ thuộc vào thư viện native của hệ thống như C library, zlib, libgcc hoặc thư viện do SDK bên thứ ba cung cấp.

Khi triển khai Linux container, cần quyết định các thư viện native đó được nạp từ hệ điều hành lúc chạy hay được liên kết vào binary lúc build. Quyết định này ảnh hưởng đến:

- các thư viện và dynamic loader phải có trong runtime image;
- khả năng chạy trên Debian/Ubuntu, Red Hat, Alpine, distroless hoặc scratch;
- tương thích ABI giữa môi trường build và runtime;
- kích thước executable và container;
- cách cập nhật thư viện hệ thống và xử lý lỗ hổng bảo mật;
- khả năng dùng JNI hoặc thư viện native của bên thứ ba.

GraalVM Native Image hỗ trợ ba cách triển khai Linux thường gặp:

| Cách liên kết | C library | Thư viện native khác | Runtime phù hợp |
| --- | --- | --- | --- |
| Dynamic | Nạp động, thường là glibc | Có thể nạp động | Linux image cung cấp đúng glibc và shared libraries |
| Mostly static | glibc vẫn nạp động | Liên kết tĩnh các thư viện mà toolchain hỗ trợ | Image có glibc, ví dụ Debian-based distroless |
| Fully static | Đã link tĩnh với musl | Liên kết tĩnh các thư viện cần thiết | Có thể chạy trong scratch nếu ứng dụng không cần file/runtime resource ngoài |

Điểm quan trọng: **Native Image mặc định tạo binary liên kết động**. Nếu cần binary fully static trên Linux, GraalVM hỗ trợ cách đó với musl. Liên kết tĩnh glibc bằng `--static` không được Native Image hỗ trợ.

## 2. Dynamic linking trong ELF hoạt động thế nào?

Trên Linux, executable thường dùng định dạng ELF (Executable and Linkable Format). Một binary liên kết động chứa thông tin để kernel gọi dynamic loader, sau đó loader tìm và nạp các shared objects (`.so`) cần thiết.

Luồng khởi động tổng quát:

~~~mermaid
flowchart TB
    A["Container starts native executable"] --> B["Kernel reads ELF header"]
    B --> C{"ELF has PT_INTERP?"}
    C -->|Yes| D["Start dynamic loader"]
    D --> E["Resolve DT_NEEDED shared libraries"]
    E --> F["Map libraries and resolve symbols"]
    F --> G["Enter native application"]
    C -->|No| H["Start statically linked executable"]
    H --> G
~~~

Hai mục ELF thường cần kiểm tra:

- `PT_INTERP`: đường dẫn dynamic loader, ví dụ `/lib64/ld-linux-x86-64.so.2`.
- `DT_NEEDED`: danh sách shared libraries mà binary cần nạp.

Với binary liên kết động, việc copy riêng executable sang một container không có dynamic loader hoặc thiếu `.so` phụ thuộc sẽ khiến process không khởi động được. Thông báo lỗi đôi khi nói không tìm thấy file executable dù file đó thực sự tồn tại; nguyên nhân có thể là interpreter trong `PT_INTERP` không có.

## 3. Phân biệt linking của Java với linking native

Trước khi chọn libc, cần phân biệt hai khái niệm:

| Khái niệm | Xảy ra khi nào? | Thành phần liên quan |
| --- | --- | --- |
| Spring AOT | Build time | ApplicationContext, bean definitions, generated code và runtime hints |
| Native Image analysis/compilation | Build time | Java bytecode, reachability và native code |
| Native dynamic linking | Khi executable khởi động | ELF loader, libc và shared libraries |
| Native static linking | Khi executable được tạo | Object files và static archives (`.a`) được ghép vào binary |

Static linking không có nghĩa Java class được nạp động. Native Image đã xử lý code Java theo closed-world analysis trước đó. Lựa chọn glibc/musl chỉ quyết định ABI và cách executable liên kết với C library cùng các native dependencies.

Tương tự, thêm runtime hints cho reflection không giải quyết được lỗi thiếu `libc.so`, và chuyển sang musl không tự sửa được lỗi reflection/resource của Spring AOT.

## 4. glibc là gì?

**glibc** (GNU C Library) là C library phổ biến trên nhiều Linux distribution như Debian, Ubuntu, Fedora, Red Hat Enterprise Linux, Oracle Linux và Amazon Linux.

glibc cung cấp các API nền tảng mà native code thường dùng:

- xử lý process, thread và synchronization;
- cấp phát bộ nhớ;
- file, socket và system-call wrappers;
- DNS/name service integration;
- locale và một số chức năng runtime của hệ thống.

Native Image trên Linux thường tạo executable liên kết động với glibc theo mặc định. Đây là lựa chọn phù hợp khi runtime container đã dùng glibc và các JNI/native dependencies của ứng dụng cũng được build cho glibc.

### 4.1. Tương thích phiên bản glibc

Binary liên kết động có thể yêu cầu một phiên bản symbol cụ thể của glibc. Nếu build trên hệ thống mới rồi chạy trong runtime image cũ hơn, executable có thể báo:

~~~text
version 'GLIBC_2.xx' not found
~~~

Nguyên nhân là runtime glibc không cung cấp symbol version mà binary cần. Một cách triển khai an toàn là build trên baseline glibc bằng hoặc cũ hơn môi trường runtime thấp nhất được hỗ trợ, sau đó kiểm tra symbol requirements của executable.

Không nên chỉ dựa vào tên distribution. Hai image cùng họ Debian có thể dùng phiên bản glibc khác nhau do release khác nhau.

### 4.2. Ưu điểm và giới hạn

| Ưu điểm của glibc | Điều cần kiểm soát |
| --- | --- |
| Tương thích với phần lớn Linux server image phổ biến | Phiên bản glibc tối thiểu mà binary yêu cầu |
| Nhiều SDK/JNI vendor cung cấp binary build cho glibc | ABI và shared-library dependencies của vendor |
| Có hệ sinh thái locale, NSS và công cụ hệ thống quen thuộc | Cần runtime image có loader, libc và các `.so` cần thiết |
| Có thể cập nhật libc qua package của OS | Cần kiểm thử lại ứng dụng sau khi cập nhật thư viện hệ thống |

Nếu vendor chỉ phát hành native library cho glibc, hãy chọn runtime glibc. Không thể lấy shared library glibc rồi giả định nó sẽ nạp được trong môi trường musl chỉ vì cả hai đều là libc.

## 5. musl là gì?

**musl** là một implementation của C standard library dành cho Linux, có thiết kế gọn và tập trung vào tính đơn giản, tiêu chuẩn. Alpine Linux dùng musl làm libc mặc định.

musl thường được cân nhắc khi:

- muốn tạo fully static native executable;
- muốn dùng runtime container rất nhỏ hoặc `scratch`;
- toàn bộ native dependencies có thể build/link phù hợp với musl;
- đã kiểm tra các khác biệt hành vi mà ứng dụng phụ thuộc.

### 5.1. musl không phải glibc được đổi tên

Hai libc có nhiều API tương tự nhưng ABI và một số hành vi khác nhau. Một `.so` build cho glibc không tự động tương thích với musl. Native library cần được build lại cho musl hoặc thay bằng implementation tương thích.

Các khu vực cần kiểm thử:

- JNI/native SDK và dependency C/C++;
- DNS resolver, hostname lookup và cấu hình mạng;
- locale, collation và định dạng dữ liệu phụ thuộc locale;
- timezone và dữ liệu zoneinfo;
- hành vi thread, signal và system call mà native dependency sử dụng;
- thư viện sử dụng API riêng của glibc hoặc `dlopen`.

Không nên kết luận ứng dụng tương thích musl chỉ vì một smoke test HTTP thành công. Cần chạy các luồng thực sự sử dụng database driver, compression, crypto, image processing hoặc JNI nếu ứng dụng có những thành phần này.

### 5.2. Điều kiện hỗ trợ theo nền tảng

Static musl build phụ thuộc vào GraalVM distribution và native toolchain của target. Hướng dẫn GraalVM hiện hành về static executable nêu các điều kiện như Linux x64, GraalVM JDK 17 trở lên, musl toolchain 64-bit và zlib phù hợp.

Hỗ trợ cũng có thể khác theo kiến trúc và version. Compatibility Guide hiện hành của GraalVM ghi rõ musl chưa được hỗ trợ cho Native Image trên Linux AArch64. Nếu target là ARM64, kiểm tra ma trận hỗ trợ của đúng GraalVM release trước khi chọn musl.

## 6. Ba chế độ liên kết trên GraalVM Native Image

### 6.1. Dynamic linking mặc định

Build thông thường:

~~~bash
native-image -jar target/billing-service.jar billing-service
~~~

Native Image tạo binary liên kết động với các thư viện cần thiết của hệ thống. Trên Linux, cấu hình mặc định thường dùng glibc.

Có thể chọn rõ libc nếu muốn làm cấu hình build dễ đọc:

~~~bash
native-image --libc=glibc \
  -jar target/billing-service.jar \
  billing-service
~~~

Runtime image cần dynamic loader, glibc và mọi shared library được liệt kê trong ELF. `ldd` giúp kiểm tra danh sách dependency thực tế.

### 6.2. Mostly-static với --static-nolibc

Mostly-static liên kết tĩnh các native libraries mà Native Image có thể link, ngoại trừ `libc`. Với cấu hình Linux glibc mặc định, glibc vẫn được nạp động lúc runtime; các thư viện khác như zlib và một số JDK native libraries được liên kết tĩnh.

Build:

~~~bash
native-image --static-nolibc \
  -jar target/billing-service.jar \
  billing-service
~~~

Binary này vẫn cần runtime cung cấp glibc và dynamic loader. Nó phù hợp với glibc-based image, kể cả một số distroless image, khi muốn giảm các shared-library dependencies còn lại.

Tùy code và toolchain, executable vẫn có thể cần `libstdc++` hoặc `libgcc` động. Vì vậy, không suy luận chỉ từ tên `--static-nolibc`; hãy kiểm tra `ldd` trên binary thực tế.

### 6.3. Fully static với musl

Để tạo executable liên kết tĩnh với musl:

~~~bash
native-image --static --libc=musl \
  -jar target/billing-service.jar \
  billing-service
~~~

Điều kiện:

- chạy build trên Linux target được hỗ trợ;
- GraalVM Native Image version có hỗ trợ musl cho kiến trúc đó;
- musl toolchain và compiler wrapper có trong `PATH`;
- có các static libraries cần thiết, gồm zlib theo hướng dẫn toolchain;
- mọi native dependencies mà ứng dụng sử dụng có thể liên kết tĩnh tương thích.

Static glibc không được Native Image hỗ trợ bằng `--static`. Nếu mục tiêu là glibc runtime nhưng muốn giảm shared libraries khác, dùng `--static-nolibc`.

## 7. So sánh ba chế độ

| Tiêu chí | Dynamic glibc | Mostly-static glibc | Fully-static musl |
| --- | --- | --- | --- |
| Cách chọn | Mặc định hoặc `--libc=glibc` | `--static-nolibc` | `--static --libc=musl` |
| C library ở runtime | glibc động | glibc động | Đã link tĩnh musl |
| Các native library khác | Có thể cần `.so` | Phần lớn link tĩnh nếu toolchain có archive | Link tĩnh nếu có archive tương thích |
| Runtime image | Có loader, glibc và `.so` phụ thuộc | Có loader và glibc | Có thể dùng `scratch` |
| Native dependency chỉ có bản glibc | Thường phù hợp | Thường phù hợp nếu dependency được link | Không tương thích trực tiếp |
| Kích thước executable | Thường nhỏ hơn static hoàn toàn | Có thể lớn hơn dynamic | Có thể lớn do mang theo thư viện |
| Cập nhật libc | Cập nhật ở runtime image | Cập nhật glibc ở runtime image | Cần build lại binary để nhận bản musl mới |
| Độ linh hoạt runtime | Phụ thuộc thư viện hệ thống | Phụ thuộc glibc | Ít phụ thuộc thư viện native hệ thống |

Không có chế độ nào luôn nhanh nhất hoặc nhỏ nhất. Static linking có thể làm executable lớn hơn; dynamic linking có thể tận dụng shared libraries đã có trong OS. Hãy đo startup, RSS, image size và hiệu năng dưới workload thực tế.

## 8. Chọn glibc hay musl theo yêu cầu triển khai

### 8.1. Chọn dynamic glibc khi

- runtime image là Debian, Ubuntu, Red Hat, Oracle Linux hoặc distribution dùng glibc;
- SDK/JNI vendor cung cấp `.so` cho glibc;
- ứng dụng cần native dependency dùng API đặc thù glibc;
- muốn cập nhật libc qua OS package mà không rebuild ứng dụng;
- team đã có chuẩn runtime image glibc và công cụ chẩn đoán tương ứng.

Đây thường là lựa chọn dễ tích hợp nhất cho ứng dụng Spring Boot có nhiều driver và thư viện ngoài đã được kiểm thử trên Linux glibc.

### 8.2. Chọn mostly-static glibc khi

- muốn giảm số lượng shared libraries ngoài libc;
- runtime là Debian-based distroless hoặc image glibc tối giản;
- không cần dùng một số `.so` tùy chọn có thể được link tĩnh;
- vẫn muốn dùng ABI glibc và các JNI libraries tương thích glibc.

Hãy kiểm tra `ldd` để xác nhận runtime còn cần những gì. `--static-nolibc` không biến executable thành binary có thể chạy trong `scratch`, vì nó vẫn cần glibc và dynamic loader.

### 8.3. Chọn fully-static musl khi

- cần executable có thể chạy trong `scratch`;
- không muốn phụ thuộc vào glibc trong runtime image;
- toàn bộ JNI/native dependencies có thể build cho musl hoặc link tĩnh;
- đã kiểm thử DNS, locale, timezone, TLS và native libraries trên môi trường target;
- target OS/architecture được GraalVM version hỗ trợ.

Nếu ứng dụng phụ thuộc vào một vendor `.so` chỉ phát hành cho glibc, không chọn musl static trước khi có bản vendor tương thích.

## 9. Chuẩn bị musl toolchain

Native Image không tự mang theo toàn bộ compiler và static system libraries cần thiết cho musl. Máy build cần toolchain tương thích.

Theo hướng dẫn GraalVM, static build cần:

- Linux x64 trong cấu hình được hướng dẫn;
- GraalVM distribution có Native Image;
- musl toolchain 64-bit;
- `make` và `configure`;
- zlib tương thích, bao gồm static archive cần thiết.

Sau khi cài toolchain theo tài liệu của GraalVM, kiểm tra compiler wrapper:

~~~bash
which x86_64-linux-musl-gcc
x86_64-linux-musl-gcc --version
~~~

Tên executable phụ thuộc toolchain. Một số bộ toolchain cung cấp `musl-gcc`; toolchain được GraalVM hướng dẫn có thể cung cấp tên target-prefixed như `x86_64-linux-musl-gcc`.

Kiểm tra zlib static archive và header có sẵn trong sysroot của toolchain. Đừng chỉ kiểm tra `gcc --version`: compiler mặc định của máy có thể vẫn trỏ tới glibc.

Giữ toolchain, GraalVM và target architecture được pin trong CI để các lần build có thể tái lập. Không trộn header của glibc với static libraries của musl trong cùng một native build.

## 10. Cấu hình Maven Native Build Tools

Có thể truyền linker options qua `native-maven-plugin`. Ví dụ mostly-static glibc:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>--static-nolibc</buildArg>
        </buildArgs>
    </configuration>
</plugin>
~~~

Ví dụ fully static musl:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>--static</buildArg>
            <buildArg>--libc=musl</buildArg>
        </buildArgs>
    </configuration>
</plugin>
~~~

Chỉ dùng một chế độ phù hợp với runtime target trong một build profile. Nếu POM đã có cấu hình `buildArgs`, gộp options vào cấu hình hiện tại thay vì tạo plugin execution trùng lặp.

Build theo profile/plugin của dự án:

~~~bash
./mvnw -Pnative native:compile
~~~

Profile `native` là quy ước thường gặp nhưng cần tồn tại trong POM thực tế. Kiểm tra effective POM và version Native Build Tools; option được hỗ trợ phụ thuộc GraalVM release.

## 11. Cấu hình Gradle Native Build Tools

Ví dụ Kotlin DSL cho mostly-static glibc:

~~~kotlin
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add("--static-nolibc")
        }
    }
}
~~~

Ví dụ Kotlin DSL cho fully static musl:

~~~kotlin
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add("--static")
            buildArgs.add("--libc=musl")
        }
    }
}
~~~

Sau đó chạy:

~~~bash
./gradlew nativeCompile
~~~

Với Groovy DSL hoặc plugin version khác, cách truy cập binary/task có thể khác. Kiểm tra plugin version và task list của dự án. Build musl phải chạy trong môi trường có musl toolchain và static libraries phù hợp.

## 12. Chọn runtime container

### 12.1. Dynamic glibc

Dùng runtime image có glibc và dynamic loader tương thích. Ví dụ Debian slim:

~~~dockerfile
FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY billing-service /app/billing-service

USER 65532:65532
ENTRYPOINT ["/app/billing-service"]
~~~

Base image cần chứa mọi `.so` mà `ldd` báo thiếu. Nếu binary được build trên glibc mới hơn bản trong Debian release này, vẫn có thể gặp lỗi symbol version; phải xác nhận baseline.

### 12.2. Mostly-static glibc

Có thể dùng image glibc tối giản hoặc Debian-based distroless. Ví dụ khung runtime:

~~~dockerfile
FROM gcr.io/distroless/base-debian12:nonroot

COPY billing-service /app/billing-service

ENTRYPOINT ["/app/billing-service"]
~~~

Image distroless không cung cấp shell và package manager. Hãy xác nhận binary cần đúng glibc version và mọi thư viện còn lại đã được link tĩnh. Nếu binary còn cần `libstdc++`, `libgcc` hoặc thư viện khác, runtime image phải cung cấp chúng hoặc build cần điều chỉnh.

### 12.3. Fully static musl

Binary fully static có thể chạy trong `scratch`:

~~~dockerfile
FROM scratch

COPY billing-service /app/billing-service
COPY ca-certificates.crt /etc/ssl/certs/ca-certificates.crt

USER 65532:65532
ENTRYPOINT ["/app/billing-service"]
~~~

Đường dẫn CA bundle cần được copy từ một stage có cài `ca-certificates`, hoặc từ artifact đã chuẩn bị. `scratch` không chứa CA certificates, timezone files, shell, user database hay tiện ích chẩn đoán.

Static binary vẫn có thể cần tài nguyên ngoài executable:

- CA bundle cho HTTPS/TLS;
- cấu hình mount và secret runtime;
- file timezone hoặc dữ liệu locale nếu ứng dụng cần;
- thư mục ghi tạm, nếu ứng dụng sử dụng;
- file cấu hình, template hoặc native resources được thiết kế để mount.

Fully static chỉ loại bỏ phụ thuộc shared library native; nó không tự nhúng mọi file hệ thống hoặc dữ liệu ứng dụng.

Static linking cũng không loại bỏ yêu cầu tương thích với kernel và CPU đích. Executable vẫn gọi Linux system calls và được build cho một kiến trúc cụ thể. Hãy kiểm tra kernel baseline, architecture và CPU features của node/container runtime; một binary fully static x86-64 vẫn không chạy trên ARM64.

## 13. Kiểm tra binary sau khi build

Không nên chọn runtime image dựa vào tên build flag. Hãy kiểm tra ELF artifact thực tế.

### 13.1. Xem định dạng và kiến trúc

~~~bash
file billing-service
~~~

Xác nhận binary là ELF executable và đúng architecture, ví dụ x86-64 hoặc AArch64. Static linking không làm binary x86-64 chạy được trên ARM64.

### 13.2. Kiểm tra dynamic loader

~~~bash
readelf -l billing-service | grep -i interpreter
~~~

Nếu có dòng `Requesting program interpreter`, executable yêu cầu dynamic loader. Nếu fully static, thường không có `PT_INTERP`.

### 13.3. Kiểm tra shared-library dependencies

~~~bash
readelf -d billing-service | grep NEEDED
ldd billing-service
~~~

Chỉ dùng `ldd` với executable do chính bạn build hoặc artifact đã được tin cậy. `ldd` trên binary không tin cậy có thể gọi dynamic loader theo cách không an toàn.

Kết quả thường thấy:

- Dynamic glibc: nhiều `NEEDED` entries, có libc và các `.so` khác.
- Mostly-static glibc: vẫn có dynamic loader/libc; có thể còn `libstdc++` hoặc `libgcc` tùy code.
- Fully-static musl: `ldd` thường báo `not a dynamic executable`; ELF không có dynamic interpreter và không có dynamic `NEEDED` libraries.

### 13.4. Kiểm tra glibc symbol version

Với binary glibc liên kết động:

~~~bash
readelf --version-info billing-service | grep GLIBC_
~~~

Danh sách symbol version giúp xác định yêu cầu glibc tối thiểu. So sánh với runtime image thực tế, không chỉ với máy build.

## 14. Các tài nguyên vẫn cần ở runtime

Chọn static linking không thay thế resource configuration của Native Image hoặc cấu hình hệ điều hành.

Ví dụ ứng dụng gọi HTTPS:

- binary không cần `libc.so` khi fully static musl;
- nhưng vẫn cần CA certificates để xác thực server;
- vẫn cần DNS resolver và network config của container;
- vẫn cần hostname và certificate chain hợp lệ.

Ứng dụng dùng timezone:

- cần xác định dữ liệu timezone đến từ JDK image hay hệ điều hành;
- kiểm thử zone ID và daylight-saving transitions;
- không giả định `scratch` có `/usr/share/zoneinfo`.

Ứng dụng dùng font, template hoặc file cấu hình:

- đưa resource vào Native Image nếu phù hợp và có metadata;
- hoặc copy/mount file theo deployment contract;
- kiểm tra đường dẫn và quyền truy cập trong runtime container.

Đây là lý do một fully static binary có thể chạy thành công trong container test đơn giản nhưng thất bại khi thực hiện nghiệp vụ thật.

## 15. Kiểm thử tương thích glibc và musl

Một ma trận kiểm thử hữu ích:

| Build mode | Runtime | Điều cần xác nhận |
| --- | --- | --- |
| Dynamic glibc | Cùng baseline glibc | Loader, `.so`, symbol version và TLS |
| Dynamic glibc | glibc mới hơn | ABI tương thích và native dependencies |
| Dynamic glibc | glibc cũ hơn | Không thiếu `GLIBC_x.y` symbols |
| Mostly-static glibc | Debian-based distroless | glibc/loader có mặt; không thiếu `.so` còn lại |
| Fully-static musl | `scratch` | Không có dynamic dependency; CA/config/resource được cung cấp |
| Fully-static musl | Alpine | Chạy đúng architecture; kiểm tra DNS, locale và native integration |

Với mỗi runtime, test:

- process startup và readiness;
- health endpoint;
- HTTPS handshake và certificate validation;
- DNS lookup;
- database connection và reconnect;
- message broker/client nếu có;
- compression, crypto và JNI;
- graceful shutdown;
- chạy dưới non-root user và filesystem read-only nếu deployment yêu cầu.

Không chỉ chạy `--version` hoặc health check. Gọi các API nghiệp vụ có sử dụng native dependencies.

## 16. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `No such file or directory` dù executable tồn tại | Thiếu dynamic loader được ghi trong `PT_INTERP` | Kiểm tra `readelf -l`; dùng runtime image có loader phù hợp |
| `error while loading shared libraries` | Thiếu `.so` dependency | Chạy `ldd` trên binary tin cậy và bổ sung thư viện đúng version |
| `GLIBC_2.xx not found` | Runtime glibc cũ hơn symbol version binary yêu cầu | Build trên baseline glibc cũ hơn hoặc nâng runtime |
| `--static` báo không hỗ trợ glibc | Native Image không hỗ trợ static glibc | Dùng `--static-nolibc` cho mostly-static glibc hoặc `--static --libc=musl` |
| Không tìm thấy musl compiler | Toolchain không có trong `PATH` hoặc sai target prefix | Kiểm tra musl toolchain và compiler wrapper |
| Không tìm thấy `libz.a` hoặc static archive | Thiếu zlib/toolchain static libraries | Cài đúng archive trong musl sysroot và build lại |
| glibc JNI `.so` không nạp trong Alpine | Native library dùng ABI glibc | Dùng glibc runtime hoặc build dependency cho musl |
| Static binary không gọi được HTTPS | Thiếu CA bundle hoặc cấu hình trust | Copy/mount CA certificates và kiểm tra hostname/chain |
| DNS khác giữa glibc và musl | Resolver/configuration behavior khác | Kiểm tra `/etc/resolv.conf`, DNS và behavior của client |
| Native build chạy trên x86-64 nhưng runtime là ARM64 | Sai target architecture | Build artifact riêng cho target architecture |
| Binary chạy nhưng thiếu timezone/config | Static linking không nhúng các file này | Cung cấp resource hoặc mount đúng vị trí |

## 17. Quy trình lựa chọn và phát hành

Giả sử dịch vụ billing cần chạy trong Kubernetes với image nhỏ, kết nối HTTPS tới payment provider và dùng một SDK JNI.

**Bước 1 — kiểm tra native dependencies**

- Liệt kê mọi JNI/shared library.
- Xác định vendor cung cấp bản glibc hay musl.
- Kiểm tra các thư viện có static archive không.
- Xác nhận SDK có dùng `dlopen` hoặc load plugin động không.

**Bước 2 — chọn runtime contract**

Nếu SDK chỉ có glibc `.so`, chọn dynamic hoặc mostly-static glibc và dùng runtime glibc. Nếu toàn bộ dependencies hỗ trợ musl, cân nhắc fully-static musl để dùng `scratch`.

**Bước 3 — build hai biến thể nếu cần đánh giá**

Dynamic:

~~~bash
native-image --libc=glibc \
  -jar target/billing-service.jar \
  billing-service-glibc
~~~

Mostly-static:

~~~bash
native-image --static-nolibc \
  -jar target/billing-service.jar \
  billing-service-mostly-static
~~~

Fully static musl (chỉ trên target được hỗ trợ):

~~~bash
native-image --static --libc=musl \
  -jar target/billing-service.jar \
  billing-service-musl
~~~

**Bước 4 — kiểm tra ELF**

Chạy `file`, `readelf -l`, `readelf -d` và `ldd` trên từng artifact. Ghi lại dynamic loader, `NEEDED` libraries và GLIBC symbol version nếu có.

**Bước 5 — kiểm thử trong runtime image cuối**

Chạy cùng test suite với HTTPS, DNS, database, SDK/JNI, resource và non-root user. Đảm bảo CA bundle và cấu hình được cung cấp đúng.

**Bước 6 — so sánh chi phí**

Đo executable size, container image size, startup-to-ready, RSS và throughput. Static linking có thể làm binary lớn hơn; không kết luận chỉ từ dung lượng base image.

**Bước 7 — pin toolchain và runtime**

Ghi lại GraalVM version, JDK, compiler, musl/glibc baseline, target OS/architecture và digest runtime image. Rebuild và kiểm thử lại khi cập nhật libc hoặc native dependencies.

## 18. Checklist trước khi chọn linking mode

- [ ] Đã liệt kê JNI/shared-library dependencies của ứng dụng.
- [ ] Đã xác định runtime image dùng glibc hay musl.
- [ ] Đã phân biệt dynamic, mostly-static và fully-static.
- [ ] Không dùng `--static` với glibc.
- [ ] Nếu dùng `--static-nolibc`, runtime vẫn có glibc và loader.
- [ ] Nếu dùng `--static --libc=musl`, target và GraalVM version hỗ trợ musl.
- [ ] Musl toolchain và static zlib libraries đã được cài đúng.
- [ ] Native dependencies có ABI phù hợp với libc được chọn.
- [ ] Đã kiểm tra ELF interpreter và `DT_NEEDED`.
- [ ] Đã kiểm tra GLIBC symbol version với dynamic glibc binary.
- [ ] Đã cung cấp CA bundle, timezone/config/resource cần thiết.
- [ ] Đã test DNS, TLS, database, JNI và các luồng nghiệp vụ quan trọng.
- [ ] Đã chạy trong đúng runtime container cuối, bằng non-root user.
- [ ] Đã đo image size, startup, RSS và throughput dưới cùng workload.
- [ ] Đã pin GraalVM, toolchain, architecture và runtime image digest.

**Ghi nhớ:** dynamic glibc phù hợp với phần lớn runtime Linux và JNI dependencies phổ biến; `--static-nolibc` giảm các shared-library dependencies nhưng vẫn cần glibc; `--static --libc=musl` tạo fully static executable và có thể chạy trong `scratch` khi target được hỗ trợ. Hãy chọn theo ABI của native dependencies, runtime container và các resource mà ứng dụng cần, rồi xác minh bằng ELF inspection và test trong image cuối.

## Tài liệu tham khảo

- [GraalVM Native Image — Build a Statically Linked or Mostly-Statically Linked Native Executable](https://www.graalvm.org/latest/reference-manual/native-image/guides/build-static-executables/): điều kiện toolchain, `--static --libc=musl`, `--static-nolibc` và lựa chọn container.
- [GraalVM Native Image — Compatibility Guide](https://www.graalvm.org/latest/reference-manual/native-image/metadata/Compatibility/): giới hạn hỗ trợ theo tính năng và kiến trúc, bao gồm musl trên Linux AArch64.
- [GraalVM Native Image — Command-line Options](https://www.graalvm.org/latest/reference-manual/native-image/overview/Options/): kiểm tra các option được hỗ trợ trong phiên bản đang cài.
- [musl libc](https://musl.libc.org/): tài liệu và thông tin về musl C library.
- [Linux man-pages — ld.so](https://man7.org/linux/man-pages/man8/ld.so.8.html): dynamic linker/loader và cơ chế tìm shared libraries.
- [Linux man-pages — elf](https://man7.org/linux/man-pages/man5/elf.5.html): cấu trúc ELF, program headers và dynamic section.
