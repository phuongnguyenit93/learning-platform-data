# Container base image, thư viện hệ thống và kiến trúc đích

Khi nâng một ứng dụng Java, việc biên dịch lại bằng JDK mới chỉ giải quyết một phần tương thích. Một JAR vẫn có thể chạy ổn định trên máy lập trình nhưng gặp lỗi khi chuyển vào container: JVM không khởi động, JNI báo UnsatisfiedLinkError, kết nối TLS không tin cậy chứng chỉ, dữ liệu thời gian bị lệch, hoặc một thư viện native x86-64 không chạy trên node ARM64. Các vấn đề này thường bắt nguồn từ **container base image**, **thư viện hệ thống**, **ABI** và **kiến trúc triển khai**, chứ không trực tiếp từ Java source.

Bài học nằm trong chủ đề **Java Advance Compatibility Migration**, chương **Đóng gói và môi trường**. Trọng tâm là hiểu base image chứa những gì, lựa chọn JDK/JRE và hệ điều hành nền, phân biệt glibc với musl, xác định dependency native, đóng gói multi-architecture images, quản lý runtime resources, bảo mật supply chain và kiểm thử migration theo chính image sẽ được đưa lên production.

Nguyên tắc xuyên suốt: **tương thích container là tương thích của cả artifact Java, JVM, userland hệ điều hành, native libraries, container runtime và nền tảng CPU đích**. Một lần docker build thành công hoặc một Java unit test xanh không đủ chứng minh toàn bộ chuỗi này hoạt động.

## 1. Những tầng tham gia khi một Java container chạy

~~~text
Application request / message
             |
             v
+-----------------------------------------+
| Application bytecode                    |
| app.jar, classes, third-party JARs      |
+-----------------------------------------+
| Java runtime                            |
| JVM, JRE modules, GC, JSSE, JIT         |
+-----------------------------------------+
| Native libraries and agents             |
| JNI, JNA, JVMTI, libc, libstdc++        |
+-----------------------------------------+
| Container image userland                |
| OS packages, CA, timezone, fonts, user  |
+-----------------------------------------+
| Container runtime + Linux kernel        |
| namespaces, cgroups, seccomp, mounts    |
+-----------------------------------------+
| CPU architecture and instruction set    |
| x86-64, AArch64, CPU extensions         |
+-----------------------------------------+
~~~

Một chương trình Java thuần có thể ít phụ thuộc native code bên thứ ba, nhưng JVM vẫn cần các binary và system interfaces phù hợp. Một hệ thống xử lý ảnh, dùng database native client, GPU, JNI compression hoặc APM profiler có thể chứa thêm nhiều thư viện C/C++ và agents.

### 1.1. Ba câu hỏi cần trả lời trước khi chuyển image

1. **Java runtime nào cần thiết?** Major/update/build, vendor, modules, JVM flags, security policy và các Java APIs.
2. **Userland nào cần thiết?** Linux distribution, libc, shared libraries, CA certificates, timezone, locale, fonts và những tệp cấu hình OS.
3. **Platform đích nào được hỗ trợ?** OS, architecture, bitness, instruction set, cgroups, container runtime và chính sách deployment.

Không được đồng nhất Java version với toàn bộ runtime contract.

## 2. Base image là gì?

Base image là image nền được chọn trong chỉ thị FROM của Dockerfile, cung cấp filesystem và các runtime components cho layer tiếp theo.

~~~dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /app
COPY target/app.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Đây là ví dụ cho một executable JAR đã build sẵn ở target/app.jar. Trong dự án thực tế phải dùng đúng đường dẫn artifact và xác minh tag runtime có sẵn. Image không chỉ cung cấp java executable; nó còn có các thư viện JVM và những thành phần OS được người phát hành image chọn.

### 2.1. Base image không tạo kernel riêng

Container Linux thường dùng kernel của host hoặc Linux VM, trong khi image chứa userland như filesystem, shared libraries và application binaries. Chọn Debian-based image không làm kernel của máy host biến thành kernel Debian. Trên Docker Desktop macOS/Windows, Linux container thường chạy bên trong Linux VM.

### 2.2. Tag không phải nội dung bất biến

Một tag như 21-jre có thể được cập nhật để nhận security patches. Hai lần build ở các ngày khác nhau có thể lấy hai nội dung image khác nhau dù Dockerfile không đổi.

Để tạo artifact có thể truy xuất, có thể pin image theo digest:

~~~dockerfile
FROM registry.example.org/java/runtime:21@sha256:REPLACE_WITH_REAL_DIGEST
~~~

Chuỗi digest trên là placeholder, không phải một digest hợp lệ để triển khai. Digest thực phải lấy từ registry đáng tin và được xác minh theo đúng platform. Pin digest giúp reproducibility nhưng cần quy trình cập nhật thường xuyên; không nên pin rồi bỏ mặc bản vá.

### 2.3. Những thông tin cần lưu về image

| Thuộc tính | Ví dụ thông tin cần ghi |
|---|---|
| JDK/JRE | Java 21, bản update/build và vendor |
| OS userland | Debian-family, Ubuntu-family, Alpine, UBI… |
| libc | glibc hoặc musl, version |
| Platform | linux/amd64, linux/arm64 |
| Image identity | Registry, repository, tag, immutable digest |
| User | UID/GID, root hay non-root |
| Native dependencies | libstdc++, crypto, codec, database libraries |
| Runtime files | Truststore, CA, tzdata, fonts, locales |
| Container settings | CPU/memory limit, writable mounts, entrypoint |
| Patching | Source/vendor, policy quét CVE và cập nhật |

## 3. JDK, JRE, jlink và distroless: lựa chọn runtime

| Loại image | Ưu điểm | Cần chú ý |
|---|---|---|
| JDK đầy đủ | Có compiler và nhiều công cụ chẩn đoán | Nhiều thành phần không cần cho production |
| JRE | Tập trung vào chạy Java applications | Có thể thiếu jcmd, javac và công cụ phát triển |
| Custom jlink runtime | Chọn tập Java modules cần sử dụng | Có thể thiếu module hoặc provider được load động |
| Distroless runtime | Userland tối giản, ít công cụ thừa | Không có shell/package manager, khó debug trực tiếp |
| Linux distro + Java tự cài | Chủ động cài native dependencies | Phải quản lý patch cho cả OS và JDK |

Không có lựa chọn nào mặc nhiên tốt nhất. Hệ thống cần font rendering, thư viện HSM, JNI, machine-learning runtime hoặc native agent có thể cần nhiều OS packages hơn một REST service chỉ dùng Java thuần.

### 3.1. Build bằng JDK, chạy bằng JRE

Phần build cần javac và Maven/Gradle; production thường chỉ cần runtime.

~~~text
Build stage:
  JDK + Maven/Gradle + source -> JAR

Runtime stage:
  JRE + JAR + required native libraries -> image
~~~

Nếu compiler phát class file Java 17 nhưng runtime image chứa Java 21, ứng dụng có thể chạy, miễn các dependencies và runtime behaviors phù hợp. Ngược lại, class file Java 21 không chạy trên JRE 17 chỉ bằng cách thay tên image.

### 3.2. Khi production cần JDK tools

Một số môi trường sử dụng jcmd, jfr, jstack hoặc keytool trực tiếp trong container. JRE/distroless image có thể không chứa chúng. Có thể dùng diagnostic image hoặc cơ chế observability bên ngoài, nhưng phải thiết kế trước khi cần điều tra sự cố.

### 3.3. Kích thước image không quyết định tính đúng đắn

Giảm 100 MB không đáng nếu làm thiếu CA, font, native codec hoặc khiến không thể chẩn đoán memory leak. Hãy ưu tiên tính tương thích, bảo mật, khả năng cập nhật và vận hành trước, rồi mới tối ưu kích thước.

## 4. Java version khác hệ điều hành và libc

Hai images cùng ghi Java 21 có thể khác nhau đáng kể:

~~~text
Image A:
  JDK vendor A, Java 21
  Debian-family userland
  glibc
  linux/amd64

Image B:
  JDK vendor B, Java 21
  Alpine-family userland
  musl
  linux/arm64
~~~

Cả hai có thể chạy cùng Java bytecode phù hợp, nhưng không nhất thiết chạy cùng native library hoặc agent.

### 4.1. Chọn OS distribution theo dependency

| Nhóm image | Đặc điểm | Rủi ro migration |
|---|---|---|
| Debian/Ubuntu | glibc, apt/dpkg ecosystem | Phiên bản glibc, packages, CA/tzdata |
| RHEL/UBI | glibc, RPM ecosystem | Vendor support, native packages, FIPS |
| Alpine | musl, apk ecosystem | Native binary glibc không tự chạy trên musl |
| Distroless | Tối giản userland, ít tooling | Thiếu shell, CA/font/native libs tùy image |
| Scratch/custom | Tự cung cấp mọi file cần thiết | Dễ thiếu dynamic loader hoặc Java modules |

Nếu một thư viện native chỉ được vendor hỗ trợ trên glibc, đổi image sang Alpine/musl vì dung lượng nhỏ có thể tạo incompatibility nghiêm trọng.

### 4.2. Tránh gộp nhiều thay đổi một lúc

~~~text
Trước:
  JDK 11 + Ubuntu + glibc + amd64

Sau:
  JDK 21 + Alpine + musl + arm64
~~~

Khi lỗi xảy ra, khó tách nguyên nhân do JDK, libc, architecture hay thư viện native. Nếu có thể, hãy nâng JDK trước trong cùng OS family, sau đó tối giản image và cuối cùng mở rộng architecture.

## 5. glibc và musl: ranh giới ABI quan trọng

glibc và musl là hai C library implementations khác nhau. C/C++ binary được build cho glibc **không được bảo đảm** có thể nạp trong userland chỉ dùng musl.

~~~text
Java JAR
    |
    v
JNI/JNA wrapper
    |
    v
libimage.so build cho glibc
    |
    v
Alpine runtime chỉ có musl
    |
    v
Dynamic loader / symbol error
~~~

Một file .so tồn tại trên filesystem không đồng nghĩa OS loader có thể load nó.

### 5.1. Những lớp phải khớp

- ELF architecture và bitness.
- C dynamic loader.
- libc family và symbol versions.
- Native dependencies qua NEEDED entries.
- libstdc++/C++ ABI khi dùng C++.
- Calling convention và data structure layout.
- CPU instruction set.
- Quyền đọc/execute và filesystem policy.

### 5.2. Ngay cùng glibc cũng có giới hạn version

Binary build trên distribution mới có thể yêu cầu symbol version không có trên runtime cũ, tạo lỗi dạng:

~~~text
version 'GLIBC_2.xx' not found
~~~

xx là placeholder. Cần xác định symbol requirements thực tế và chọn baseline build/runtime phù hợp. Không nên copy một vài file libc từ image khác để sửa nhanh vì dynamic loader, NSS và các thư viện liên quan phải cùng một tập nhất quán.

### 5.3. Compatibility layer không phải câu trả lời chung

Có môi trường cung cấp gói tương thích hoặc cách chạy một số glibc binaries trên musl, nhưng không nên suy luận mọi JNI/JNA/OpenSSL/C++ library sẽ hoạt động. Với native package do vendor chỉ hỗ trợ glibc, chọn glibc-based base image thường ít rủi ro hơn.

## 6. Java application có thể cần những thư viện hệ thống nào?

Một ứng dụng Java không import C code trực tiếp vẫn có thể sử dụng native dependencies thông qua các JAR.

| Nhóm | Ví dụ | Lỗi có thể xuất hiện |
|---|---|---|
| C/C++ runtime | libc, libstdc++, libgcc | UnsatisfiedLinkError hoặc symbol mismatch |
| Mã hóa native | OpenSSL, PKCS#11/HSM | Không load provider, handshake/crypto failure |
| Networking | Native Netty transport, resolver | Lỗi transport/resolver hoặc fallback |
| Compression | zlib, zstd, lz4 JNI | Native codec không khả dụng |
| Database | ODBC/native clients, embedded engine | Không nạp shared library |
| Rendering | fontconfig, freetype, image codecs | PDF, ảnh và glyph lỗi |
| ML/GPU | CUDA, inference engine | Driver/runtime/ABI không khớp |
| Monitoring | JVMTI, profiler/APM agent | Crash hoặc không attach được |
| File/OS | Native watcher, serial/USB | Không truy cập device/syscall |
| Runtime data | CA, timezone, locale, fonts | Lỗi trust/time/formatting |

Không nên cài mọi thư viện ở bảng. Cần kiểm kê những thành phần thực sự được ứng dụng dùng.

### 6.1. Java TLS thường không cần system OpenSSL

Nhiều HTTP clients dùng JSSE của JDK. Không nên kết luận cứ có HTTPS là phải cài libssl từ OS. Ngược lại, native TLS engine, PKCS#11 provider hoặc thư viện C/C++ riêng có thể yêu cầu OpenSSL tương ứng.

### 6.2. Phụ thuộc native bắc cầu

~~~text
app.jar
   |
   v
third-party.jar
   |
   v
Extract libwrapper.so
   |
   +--> libstdc++.so
   +--> libcrypto.so
   +--> libc.so
~~~

Java dependency tree chỉ cho biết một phần. Dynamic linker dependencies không nhất thiết hiển thị trong Maven hoặc Gradle.

## 7. Kiểm tra thư viện native trên Linux

Những lệnh sau là ví dụ chẩn đoán, chạy trên hệ thống có tool tương ứng.

### 7.1. Architecture và binary format

~~~bash
file /opt/app/native/libexample.so
readelf -h /opt/app/native/libexample.so
~~~

Cần xem ELF class, Machine, file type, ABI và toolchain hints.

### 7.2. Dynamic dependency

~~~bash
readelf -d /opt/app/native/libexample.so
~~~

Các mục như NEEDED, RPATH hoặc RUNPATH giúp hiểu dynamic loader cần gì.

Một số môi trường cho phép:

~~~bash
ldd /opt/app/native/libexample.so
~~~

Tuy nhiên, **không chạy ldd tùy tiện với binary không tin cậy**. Tùy môi trường, công cụ có thể liên quan thực thi dynamic loader; với file không tin cậy nên ưu tiên phân tích tĩnh hoặc sandbox.

### 7.3. Exports và JNI symbols

~~~bash
nm -D /opt/app/native/libexample.so
objdump -T /opt/app/native/libexample.so
~~~

Nếu Java native method đổi package/tên/signature nhưng thư viện chưa được build lại, symbol JNI có thể không khớp. Với JNA, export C function/calling convention cũng phải khớp.

### 7.4. Image distroless không có các lệnh trên

Không nên cài thêm compiler/linker tools vào production image chỉ để chạy ldd. Có thể dùng diagnostic image chứa cùng binary, image test tương thích hoặc công cụ từ build pipeline.

## 8. Kiến trúc đích: amd64, arm64 và naming conventions

Nền tảng container thường được ghi:

~~~text
linux/amd64
linux/arm64
~~~

Các công cụ khác có thể dùng:

| Bối cảnh | x86-64 | ARM64 |
|---|---|---|
| Docker platform | linux/amd64 | linux/arm64 |
| uname -m thường gặp | x86_64 | aarch64 |
| Java os.arch thường gặp | amd64 | aarch64 |
| Native classifier | linux-x86_64 | linux-aarch64 |

Tên thực tế có thể khác theo vendor, framework và package. Code chọn native binary phải dùng mapping rõ ràng thay vì so sánh một chuỗi không kiểm soát.

### 8.1. Java bytecode không chứa toàn bộ application

Một base image multi-arch có JVM cho cả amd64 và arm64 nhưng app.jar có thể nhúng một file linux-x86_64/libcompress.so. Khi chạy trên ARM64, Java classes có thể load thành công rồi lỗi ở native call đầu tiên.

Phải kiểm tra:

- JNI/JNA artifacts.
- Native agents/JVMTI profiler.
- Database native clients.
- Compression, image, ML codecs.
- Công cụ hệ thống được copy vào image.
- CPU-specific binaries và kernel interfaces.

### 8.2. ARM 32-bit không phải ARM64

Nếu một library có classifier linux-armv7, không nên giả định nó tương thích linux/arm64. Bitness, ABI và instruction set có thể khác.

### 8.3. CPU instruction extensions

Ngay cả cùng x86-64, native binary được compile với instruction set quá mới có thể lỗi trên CPU cũ. Cần chọn minimum CPU baseline hoặc cơ chế runtime dispatch đã được kiểm thử.

## 9. Multi-architecture image và manifest list

Một image tag có thể đại diện cho nhiều platform-specific manifests:

~~~text
my-service:1.0
    |
    +--> linux/amd64 image
    |      +--> amd64 JVM
    |      +--> amd64 native libs
    |
    +--> linux/arm64 image
           +--> arm64 JVM
           +--> arm64 native libs
~~~

Container runtime thường chọn manifest phù hợp với node. Nhưng tag có cả hai variant **không chứng minh** mọi library bên trong đúng architecture.

### 9.1. Xem manifest

~~~bash
docker buildx imagetools inspect registry.example.org/team/my-service:1.0
~~~

Lệnh minh họa, thay bằng repository/tag thật. Cần kiểm tra platforms và digest, không chỉ một architecture đầu tiên.

### 9.2. Build đa nền tảng

~~~bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t registry.example.org/team/my-service:1.0 \
  --push .
~~~

Builder phải có native workers, cross-compilation hoặc emulation phù hợp. Buildx không tự chuyển đổi một thư viện x86-64 sang ARM64.

### 9.3. Image index digest khác per-platform digest

Cần phân biệt digest của manifest index với digest của từng variant. Khi điều tra sự cố riêng trên node ARM64, nên biết đúng ARM64 manifest/runtime image đã được kéo.

### 9.4. Emulation không thay kiểm thử trên node thật

QEMU có thể hữu ích cho thử nghiệm hoặc build nhưng hiệu năng/CPU features/runtime behavior khác native ARM64. Nếu production chạy ARM64, nên có integration tests trên ARM64 node thật.

## 10. BUILDPLATFORM và TARGETPLATFORM

BuildKit phân biệt:

- BUILDPLATFORM: máy đang thực hiện build.
- TARGETPLATFORM: platform của image output.

Ví dụ:

~~~dockerfile
FROM --platform=$BUILDPLATFORM eclipse-temurin:21-jdk AS build
ARG TARGETPLATFORM
ARG TARGETARCH

WORKDIR /workspace
# Compile Java artifact cho đúng Java release.
~~~

Đây chỉ là Dockerfile fragment để minh họa khái niệm. Có thể compile Java bytecode trên BUILDPLATFORM nếu code không nhúng artifact native theo kiến trúc build host.

Nhưng nếu Maven tự chọn classifier theo os.arch của JVM build, dùng JVM amd64 để tạo JAR rồi đưa JAR đó vào arm64 image có thể nhúng binary sai.

### 10.1. Phải biết native artifacts được tạo ở đâu

Có ba mô hình:

1. Native library được build trên builder native cho từng architecture.
2. Native library được cross-compile bằng toolchain/ABI phù hợp.
3. Native library được vendor phát hành riêng theo platform và packaging chọn đúng variant.

Chỉ đặt ARG TARGETARCH trong Dockerfile không bảo đảm compiler C/C++ hoặc Maven classifier tự sử dụng giá trị đó. Cần kết nối biến target với công cụ build và xác minh output.

## 11. Dockerfile multi-stage cơ bản

Một ví dụ build Maven rồi chạy bằng JRE:

~~~dockerfile
FROM eclipse-temurin:21-jdk AS build

WORKDIR /workspace
COPY .mvn .mvn
COPY mvnw pom.xml ./
RUN chmod +x ./mvnw

COPY src src
RUN ./mvnw -B -DskipTests package

FROM eclipse-temurin:21-jre

WORKDIR /app
COPY --from=build /workspace/target/app.jar /app/app.jar

USER 10001:10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Giả định:

- Maven Wrapper đã có trong repository.
- Project là module đơn giản, không cần copy thêm reactor modules.
- Build output đúng tên target/app.jar.
- Artifact có launcher/Main-Class.
- Runtime image hỗ trợ Java version và platform tương ứng.
- Ứng dụng có thể chạy mà không cần ghi vào /app.
- Không có native dependencies cần copy thêm.

Trong production, điều chỉnh Dockerfile theo project, chạy tests/validation ở pipeline phù hợp và pin base image version/digest có quản lý. Cờ -DskipTests ở đây **không phải hướng dẫn bỏ kiểm thử khi phát hành**.

### 11.1. Lợi ích của multi-stage

- Không mang Maven/compiler vào runtime.
- Tách dependencies build-time và runtime.
- Thu gọn bề mặt công cụ production.
- Dễ kiểm soát artifact được đưa vào final image.

### 11.2. Cạm bẫy thường gặp

- Native libraries chỉ được cài ở build stage.
- Build JDK và runtime JRE khác release ngoài ý muốn.
- Copy nhầm JAR không phải executable.
- Container chạy non-root nhưng không đọc được config.
- Runtime thiếu font/CA/timezone.
- Classifier native được build theo architecture của builder.
- CI không test final image vì chỉ test JAR trên host.

## 12. Tối giản runtime với jlink

jlink tạo runtime chứa một tập modules của Java Platform. Ví dụ:

~~~bash
jlink \
  --add-modules java.base,java.logging,java.naming,java.sql,java.management,java.xml \
  --strip-debug \
  --no-man-pages \
  --no-header-files \
  --output custom-runtime
~~~

Danh sách modules chỉ minh họa, **không đủ cho mọi application**. Một framework có thể dùng ServiceLoader, reflection hoặc dependency động khiến phân tích tĩnh bỏ sót modules.

### 12.1. Xác định modules

~~~bash
jdeps --print-module-deps --multi-release 21 app.jar
~~~

Với ứng dụng có third-party JARs, phải cung cấp classpath/modulepath phù hợp và kiểm tra các dependency mà jdeps không tự suy ra khi chỉ đọc app.jar.

### 12.2. Lỗi thường gặp sau jlink

- ClassNotFoundException hoặc NoClassDefFoundError do thiếu module.
- Missing Java services/crypto providers.
- JDBC/JNDI/XML module không có.
- Logging/management/instrumentation thiếu.
- Charset, timezone hoặc locale handling khác.
- Framework/agent dùng reflection vào package không còn sẵn.
- Native dependency hoặc JSSE configuration không phù hợp.

Phải kiểm thử runtime đã cắt giảm bằng **integration tests thực tế**, không chỉ chạy java -version.

### 12.3. jlink runtime có architecture

Custom runtime chứa JVM native binaries theo platform của JDK được sử dụng. Không thể lấy runtime được build cho Linux amd64 rồi copy trực tiếp sang Linux arm64 mà mong nó tự hoạt động.

### 12.4. jlink không giải quyết JNI/JNA

Nếu ứng dụng cần libdatabase.so hoặc libimage.so, jlink chỉ chọn Java modules; native library bên thứ ba vẫn phải được đóng gói và kiểm tra ABI riêng.

## 13. Distroless và images không có shell

Distroless thường giữ một số runtime dependencies tối thiểu, bỏ nhiều command-line tools/package manager không cần thiết.

Ưu điểm có thể là bề mặt filesystem nhỏ hơn và ít công cụ thừa. Tuy nhiên:

- Không có /bin/sh hoặc /bin/bash theo cách script giả định.
- Không có apt, apk, curl, ps, top hoặc ldd.
- Không thể cài package khi container đang chạy.
- Native libraries phải được đưa vào image từ trước.
- Cần phương án debug bên ngoài.
- Phải kiểm tra CA, timezone, fonts và thư mục ghi.

### 13.1. Chọn exec-form ENTRYPOINT

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Shell-form:

~~~dockerfile
ENTRYPOINT java -jar /app/app.jar
~~~

có thể cần shell và tạo process trung gian. Với distroless, nên sử dụng exec form và truyền JVM options qua cơ chế launcher/container configuration phù hợp.

### 13.2. Không tối giản trước khi biết dependency closure

Nếu một service dùng Java2D render PDF, JNI compression, PKCS#11 hoặc native profiler, cần kiểm kê và đóng gói đầy đủ trước khi giảm image xuống distroless.

## 14. Non-root user và filesystem permissions

Production containers thường nên chạy với quyền tối thiểu.

~~~dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /app
COPY target/app.jar /app/app.jar

USER 10001:10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Cần xác nhận:

- UID/GID có quyền đọc artifact và configuration.
- Secrets/truststore có quyền đọc được kiểm soát.
- Native libraries có thể được load.
- /tmp, /logs, cache và heap dump paths có quyền ghi.
- Mounted volumes không bị owner mismatch.
- Không cần capability đặc biệt để bind port.
- Nếu user không có home directory, code có phụ thuộc user.home không?

### 14.1. Read-only root filesystem

Một service có thể chạy với root filesystem read-only nếu tất cả dữ liệu cần ghi nằm ở writable mounts/tmpfs. Nhưng JNA/JNI library có thể extract .so vào java.io.tmpdir, framework có thể ghi file tạm, và JFR/heap dumps cần output destination.

### 14.2. noexec trên thư mục tạm

Nếu thư viện extract native code vào /tmp rồi load, mount noexec có thể làm loader từ chối. Nên dùng đường extraction được thư viện hỗ trợ với quyền thích hợp và chính sách bảo mật rõ, không bỏ tất cả protections để sửa lỗi nhanh.

## 15. CA certificates và Java truststore

Thay base image có thể thay đổi CA trust configuration. Cần phân biệt:

- OS CA store do distribution quản lý.
- JDK truststore, ví dụ cacerts.
- Custom truststore được application chỉ định.
- Keystore chứa private key/client certificate nếu mTLS.

Một số distributions tích hợp cập nhật OS CA với Java truststore; một số môi trường giữ chúng tách biệt. Không nên giả định cài package ca-certificates luôn làm mọi Java TLS client tin đúng CA.

### 15.1. Dấu hiệu thường gặp

~~~text
javax.net.ssl.SSLHandshakeException:
PKIX path building failed
~~~

Có thể do:

- Image thiếu CA nội bộ.
- Custom truststore không được mount.
- Non-root UID không đọc được keystore.
- JDK security policy từ chối certificate/algorithm yếu.
- Server không gửi đầy đủ chain.
- Proxy/load balancer thay certificate.
- Client đang dùng truststore khác dự kiến.

### 15.2. Hướng xử lý

Xác nhận provider/truststore thực tế, chain và hostname; cập nhật CA qua quy trình kiểm soát và giữ certificate validation. **Không tắt TrustManager/HostnameVerifier** để “làm cho image mới chạy được”.

### 15.3. mTLS

Với mutual TLS, phải kiểm tra cả client key, certificate chain, filesystem permissions và secret rotation. Đừng bake production private key vào image layers hoặc ghi password qua log build.

## 16. Timezone, locale và charset

Runtime image có thể thay timezone default hoặc không có đầy đủ timezone/locale resources. Điều này có thể làm:

- Batch jobs chạy lệch lịch.
- Timestamp log khác kỳ vọng.
- Date/time serialization sai offset.
- Chuỗi Unicode hoặc file encoding khác.
- Number/date formatting đổi.
- Replay dữ liệu lịch sử tạo kết quả khác.

### 16.1. Dùng timezone rõ ràng khi có contract

~~~java
import java.time.ZoneId;
import java.time.ZonedDateTime;

ZonedDateTime now = ZonedDateTime.now(
    ZoneId.of("Asia/Ho_Chi_Minh")
);
~~~

Đây chỉ là ví dụ về ZoneId tường minh; phải chọn timezone đúng với nghiệp vụ. Event timestamp xuyên hệ thống thường nên có representation UTC/offset rõ ràng thay vì dựa vào timezone mặc định của container.

### 16.2. ENV TZ và JVM timezone

~~~dockerfile
ENV TZ=UTC
~~~

và:

~~~text
-Duser.timezone=UTC
~~~

là hai cơ chế khác nhau. Behavior phụ thuộc JDK, OS configuration và code. Nên kiểm tra ZoneId.systemDefault() cùng kết quả business logic thay vì tin một biến môi trường.

### 16.3. Charset

Khi nâng JDK, default charset có thể thay đổi. Từ Java 18, UTF-8 được chuẩn hóa làm default charset theo JEP 400 trong phạm vi quy định.

Nên chỉ định encoding rõ tại ranh giới dữ liệu:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

String text = Files.readString(
    Path.of("/app/data/message.txt"),
    StandardCharsets.UTF_8
);
~~~

Đừng dùng default locale/charset của base image như một API contract cho dữ liệu nghiệp vụ.

## 17. Fonts, Java2D và headless mode

Một backend không có GUI vẫn có thể dùng fonts khi tạo PDF, Excel, ảnh, barcode, template hoặc đo kích thước văn bản. Image tối giản có thể thiếu fontconfig, freetype hoặc font families.

Triệu chứng:

- PDF có chữ mất dấu tiếng Việt.
- Text bị thay glyph.
- Layout/table bị lệch.
- Lỗi native font subsystem.
- Render ảnh khác giữa staging và production.

### 17.1. Headless mode không tạo fonts

~~~text
-Djava.awt.headless=true
~~~

không tự cài fonts hoặc mọi thư viện native hỗ trợ text rendering. Phải đưa đúng font/resource được phép vào image và kiểm thử với tiếng Việt, emoji, currency symbols và các ngôn ngữ mà sản phẩm thực tế hỗ trợ.

## 18. DNS, networking và proxy

Image và native resolver configuration có thể ảnh hưởng DNS behavior. Trong Kubernetes, còn có CoreDNS, network policy, service discovery và proxy.

Triệu chứng:

- UnknownHostException chỉ ở container mới.
- DNS lookup chậm.
- IPv4/IPv6 preference khác.
- TLS route thay đổi do proxy.
- Native DNS resolver library thiếu.

Phân loại lỗi theo tầng:

~~~text
Hostname
   |
   v
DNS resolution
   |
   v
TCP connection
   |
   v
TLS handshake
   |
   v
HTTP/JDBC/application protocol
~~~

Đừng giải quyết mọi lỗi network bằng cách thêm native packages hoặc tắt TLS validation. Cần xác định tầng gây lỗi qua logs, trace và test từ **cùng network path** với production.

## 19. Cgroups và JVM container awareness

Container runtime thường giới hạn CPU/memory qua cgroups. JDK hiện đại có cơ chế container awareness, nhưng cách tính có thể phụ thuộc JDK vendor/version và cgroup v1/v2.

### 19.1. Heap không phải toàn bộ bộ nhớ container

~~~text
Container memory limit
    |
    +--> Java heap (-Xmx)
    +--> Metaspace
    +--> Thread stacks
    +--> Code cache
    +--> DirectByteBuffer/off-heap
    +--> JNI/JNA allocations
    +--> Mapped files
    +--> Native agents
    +--> JVM native runtime
~~~

Nếu memory limit là 1 GiB và -Xmx=1g, RSS của process có thể vượt giới hạn do non-heap/native memory. Container có thể bị OOM kill dù Java heap chưa hết.

### 19.2. MaxRAMPercentage

Với JDK/HotSpot hỗ trợ:

~~~text
-XX:MaxRAMPercentage=65.0
~~~

là một ví dụ tỷ lệ, không phải cấu hình tối ưu cho mọi dịch vụ. Phải tính headroom cho threads, metaspace, direct memory và native allocations.

### 19.3. CPU quota và số processors

JVM có thể điều chỉnh GC/JIT threads và runtime scheduling theo số CPU nó nhìn thấy trong cgroups.

~~~java
System.out.println(
    Runtime.getRuntime().availableProcessors()
);
~~~

Cần kiểm tra CPU quota, request/limit, thread pools và workload. Một service chuyển node từ amd64 sang arm64 với cùng số vCPU danh nghĩa chưa chắc có cùng throughput.

### 19.4. Phân biệt OOMKilled với OutOfMemoryError

Một container bị kernel/cgroup kill có thể không ghi Java heap dump. Exit code 137 thường đi cùng SIGKILL nhưng cần xem reason của container/runtime để kết luận. OutOfMemoryError của Java heap và OOM kill do tổng memory có cơ chế khác nhau.

## 20. PID 1, tín hiệu và graceful shutdown

Container production cần xử lý SIGTERM, grace period và lifecycle.

### 20.1. Exec-form ENTRYPOINT

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

thường giúp JVM process nhận tín hiệu trực tiếp. Shell-form có thể tạo shell trung gian và ảnh hưởng signal forwarding; nếu dùng script, cần xem cơ chế exec và init process.

### 20.2. Dừng đúng nghĩa

Khi container nhận yêu cầu terminate, ứng dụng nên:

1. Ngừng nhận công việc mới.
2. Drain request/message đang chạy theo giới hạn.
3. Đóng connections, pools, thread executors.
4. Giải phóng JNI/JNA/native callbacks có ownership rõ.
5. Flush logs/traces nếu còn thời gian.
6. Thoát trước khi container grace period hết.

Shutdown hook không thể bảo đảm cleanup sẽ hoàn tất nếu process bị SIGKILL. Cần test khi có in-flight work và native resources đang hoạt động.

### 20.3. Readiness khác liveness

Java process có thể đang chạy nhưng chưa sẵn sàng nhận traffic vì đang load models hoặc khởi tạo database. Không chỉ dùng “process sống” để kết luận service ready.

## 21. Bảo mật và software supply chain của image

Base image, OS packages, JDK vendor, native binaries và ứng dụng đều tham gia vào supply chain.

Những nguyên tắc cần áp dụng:

- Chọn nguồn image đáng tin và có support policy.
- Ghi tag và digest.
- Pin/kiểm soát dependency versions.
- Quét security vulnerabilities, kể cả native libraries.
- Tạo SBOM/provenance khi quy trình yêu cầu.
- Bảo đảm build không để lộ secrets trong layers.
- Không cài package động khi container khởi động.
- Chạy non-root và giảm capabilities.
- Cập nhật base image có kiểm thử, không pin digest mãi mãi.
- Theo dõi cả security advisories của JDK vendor và OS distribution.

### 21.1. CVE scanner cũng có giới hạn

Scanner có thể báo package không thực sự được dùng hoặc bỏ sót một .so được copy thủ công mà không có package metadata. Phải triage với vendor advisory, exposure và runtime usage.

Image có ít packages không tự động có nghĩa không có vulnerabilities. Java runtime và application dependencies vẫn cần được quản lý.

### 21.2. Reproducible build

Cần lưu source commit, Dockerfile version, base digest, JDK version, dependency graph, native compiler versions, target platform và output image digest. Nếu chỉ dùng mutable latest tag, việc tái hiện sự cố sau một tháng có thể rất khó.

## 22. Debug production image tối giản

Distroless image có thể không có bash, curl, ldd, ps hoặc keytool. Giải pháp không nhất thiết là thêm mọi công cụ vào production.

Có thể dùng:

- Diagnostic image chứa cùng artifact/native libraries.
- Ephemeral debug container.
- JFR/JMX/metrics/logging.
- Build-stage static inspection.
- Core dump/heap dump pipeline có giới hạn quyền.
- Staging image variant có tool để phân tích.
- Cơ chế inspect filesystem/digest từ CI.

Tuy nhiên, **ít nhất một vòng integration test phải chạy bằng chính final production image**, không chỉ bằng JDK builder image, vì builder có thể chứa nhiều thư viện mà runtime stage thiếu.

## 23. Quy trình chẩn đoán khi app chỉ lỗi trong container

~~~text
Image platform phù hợp?
       |
       +-- Không --> Sai manifest/native binary
       |
       v
JVM khởi động?
       |
       +-- Không --> JDK/loader/libc/permissions
       |
       v
Ứng dụng nạp classes?
       |
       +-- Không --> Bytecode release/modules/classpath
       |
       v
Native libraries hoạt động?
       |
       +-- Không --> ABI/symbol/dependency/path
       |
       v
TLS/DNS/config hoạt động?
       |
       +-- Không --> Truststore/proxy/network
       |
       v
Business flow và graceful shutdown?
       |
       +-- Không --> Application lifecycle/runtime behavior
       |
       v
Performance/observability đạt yêu cầu?
~~~

### 23.1. Xác nhận image thực sự chạy

Không chỉ xem Dockerfile trong Git. Cần biết:

- Image digest mà node đã pull.
- Platform-specific manifest.
- Java version/vendor thực tế.
- Entrypoint và JVM options.
- Mounted secrets/volumes.
- User ID và filesystem permissions.
- Container memory/CPU limits.
- Application artifact version.

Một staging container và production container cùng tag chưa chắc có content giống nhau nếu tag mutable.

### 23.2. Runtime diagnostics

~~~bash
java -version
java -XshowSettings:properties -version
~~~

Trên những JDK hỗ trợ:

~~~bash
java -XshowSettings:system -version
~~~

có thể cho thông tin container/cgroup. Cần đọc output theo đúng JVM version. Java os.arch, uname và manifest platform nên được đối chiếu vì chúng không luôn dùng cùng tên architecture.

## 24. Tình huống: glibc library chuyển sang Alpine

Trước migration:

~~~text
JDK 11 + Debian base + libimage.so (glibc)
~~~

Sau migration:

~~~text
JDK 21 + Alpine base + libimage.so (vẫn glibc)
~~~

Ứng dụng có thể báo UnsatisfiedLinkError hoặc thông báo thiếu loader/symbol.

**Hướng xử lý:** xác nhận ABI bằng readelf, kiểm tra support matrix của native library, ưu tiên bản build musl chính thức nếu cần Alpine, hoặc trở về glibc-based runtime. Đừng coi chỉnh java.library.path là cách sửa ABI.

## 25. Tình huống: multi-arch base nhưng JNI chỉ có x86-64

Trước: ứng dụng chạy linux/amd64. Sau: deploy thêm linux/arm64.

Base image có cả hai manifests, nhưng dependency chứa native/linux-x86_64/libcodec.so.

Hướng xử lý:

1. Liệt kê những JNI/JNA/classifier packages.
2. Xác nhận bản ARM64 của thư viện.
3. Build/package theo đúng TARGETARCH.
4. Inspect per-platform image.
5. Chạy native integration tests trên ARM64 thật.
6. So sánh CPU/GC performance và error rate.
7. Rollout theo node architecture có quan sát.

Không có bản ARM64 thì phải thay thư viện hoặc không tuyên bố support ARM64.

## 26. Tình huống: CA hoặc mTLS lỗi trên runtime tối giản

Image JDK cũ có custom CA, nhưng JRE/distroless mới không mang truststore đó theo. HTTPS hoặc database TLS báo PKIX path building failed.

Hướng xử lý:

- Xác định truststore thực tế.
- Xác thực certificate chain và hostname.
- Mount/cấu hình CA nội bộ theo quy trình phê duyệt.
- Kiểm tra UID đọc được truststore/keystore.
- Đối chiếu JDK security policies.
- Test lại cùng endpoint/network path.

Không vô hiệu hóa certificate validation để “khôi phục tương thích”.

## 27. Tình huống: image thiếu font và timezone

Service tạo PDF hóa đơn và chạy scheduler theo giờ địa phương. Image tối giản khởi động thành công nhưng PDF mất dấu tiếng Việt, còn job chạy sai giờ.

Hướng xử lý:

- Xác định font/glyph coverage phải hỗ trợ.
- Kiểm tra fontconfig/freetype và native rendering needs.
- Đưa fonts có bản quyền phù hợp vào image.
- Chọn ZoneId rõ ràng trong nghiệp vụ.
- Kiểm tra tzdata/runtime timezone settings.
- Dùng regression fixtures cho PDF và lịch.

Không có lỗi JVM startup không có nghĩa business behavior đúng.

## 28. Tình huống: heap còn trống nhưng pod bị OOMKilled

GC metrics báo heap after-GC thấp, nhưng Kubernetes ghi OOMKilled. Ứng dụng có thể có direct buffers, JNI allocations, thread stacks hoặc agent memory vượt headroom.

Cần điều tra cgroup memory, RSS/native memory, JVM heap settings và native library usage. Không tự tăng -Xmx theo container limit vì làm non-heap càng thiếu chỗ.

## 29. Tình huống: restart treo khi SIGTERM

Container dùng shell-form entrypoint, Java service có native background thread và connection pool. SIGTERM có thể không được forward đúng hoặc cleanup kéo dài hơn grace period.

Hướng xử lý:

- Dùng exec-form entrypoint hoặc script exec.
- Thiết kế drain/cancel theo thời hạn.
- Đóng native resources rõ ràng.
- Test shutdown có in-flight work.
- Đối chiếu termination grace period.
- Không mặc định mọi shutdown hook luôn hoàn tất.

## 30. Test matrix khi chuyển base image

| Java | OS/libc | Platform | Nội dung kiểm thử |
|---|---|---|---|
| JDK cũ | Base cũ/glibc | linux/amd64 | Baseline |
| JDK mới | Cùng OS family | linux/amd64 | Tách tác động JDK |
| JDK mới | Runtime tối giản | linux/amd64 | Thiếu OS/runtime dependencies |
| JDK mới | glibc image mới | linux/arm64 | Native architecture compatibility |
| JDK mới | musl image nếu hỗ trợ | linux/amd64 | libc compatibility |
| JDK mới | Final production image | Target thật | Integration/end-to-end |
| JDK mới | Final image + agents | Target thật | JVMTI/JNI/observability |

Không nhất thiết hỗ trợ mọi tổ hợp. Chỉ chọn các tổ hợp theo support policy và migration path, nhưng phải kiểm thử những nền tảng được cam kết.

### 30.1. Kiểm thử artifact

- Image index chứa đúng platforms.
- JDK major/update/vendor đúng.
- App classes và runtime Java release tương thích.
- Native binaries khớp OS/CPU/libc.
- Dependencies resolve và symbols tồn tại.
- Không có build-host native binaries lọt vào target image.
- Entrypoint/user/permissions đúng.
- Base image digest đã được ghi nhận.

### 30.2. Kiểm thử nghiệp vụ

- Startup, readiness, liveness.
- TLS/mTLS, DNS/proxy.
- Database/message broker.
- Charset/timezone/locale.
- Fonts/PDF/image rendering khi cần.
- JNI/JNA/JVMTI native calls.
- CPU/heap/off-heap under load.
- Graceful shutdown.
- Crash log/JFR/metrics.
- Rollback.

### 30.3. Negative tests

Thử đúng các trường hợp cần từ chối hoặc báo lỗi:

- Native binary sai architecture.
- Certificate không đáng tin.
- Thiếu secret hoặc truststore.
- Read-only filesystem không cho write.
- Không có required native dependency.
- Requested platform không có manifest.
- CPU/memory limit dưới mức tối thiểu.

Negative tests giúp nhận diện fallback âm thầm hoặc error handling không an toàn.

## 31. Quy trình migration theo pha

### Bước 1 — Kiểm kê trước khi đổi

Ghi lại base image cũ, JDK version, libc/OS, architecture, JAR/dependencies, JNI/JNA/JVMTI artifacts, CA, fonts, timezone, native clients, logging và resource limits.

### Bước 2 — Chọn target có support rõ ràng

Xác định runtime JDK, distro family, libc, target architectures và vendor support. Không chọn một image chỉ vì nhỏ hoặc được nhiều người dùng.

### Bước 3 — Nâng JDK trong cùng OS family nếu có thể

Giữ architecture và libc tương đối ổn định để kiểm tra Java/framework/agent compatibility trước.

### Bước 4 — Tối giản build/runtime

Tách JDK build và JRE runtime; nếu dùng jlink/distroless phải kiểm tra modules, native libraries, CA, timezone, fonts, temp dirs và diagnostic process.

### Bước 5 — Đổi libc hoặc thêm architecture khi có lý do

Đây là bước native compatibility riêng. Build đúng platform, chọn classifiers và kiểm tra exported symbols/ABI.

### Bước 6 — Đóng gói và ghi provenance

Pin digest, lưu SBOM, native artifacts/toolchain và output image index/per-platform digests. Không mang secrets vào layers.

### Bước 7 — Kiểm thử final image

Chạy integration tests trên image cuối cùng, trong môi trường có cùng permissions, mounted resources, CPU/memory limits và network dependencies.

### Bước 8 — Canary

Theo dõi startup errors, native crashes, TLS, DNS, latency, RSS/off-heap, CPU, GC, container restarts và shutdown. Rollout theo nhóm node/architecture nếu cần.

### Bước 9 — Rollback đồng bộ

Chuẩn bị image digest cũ, runtime/config/secret policy và khả năng đọc dữ liệu mà bản mới đã ghi. Rollback không đơn thuần là đổi JDK nếu image mới đã ghi format dữ liệu không tương thích.

### Bước 10 — Thu gọn legacy exceptions

Gỡ compatibility packages, native binaries cũ và flags tạm khi không còn cần. Cập nhật runbook và patch cadence cho base image mới.

## 32. CI/CD pipeline tham khảo

~~~text
Source commit + dependency lock
          |
          v
Compile JAR + unit tests
          |
          v
Build per-platform image
          |
          v
Inspect image manifests / native symbols
          |
          v
Security scan / SBOM / provenance
          |
          v
Integration tests on target platforms
          |
          v
Publish immutable image digest
          |
          v
Canary deployment
          |
          v
Measure + rollout or rollback
~~~

Buildx push thành công không có nghĩa mỗi architecture variant đều đã vượt integration tests. Cần có kết quả rõ cho các platform được hỗ trợ.

## 33. Những hiểu lầm thường gặp

### “Java write once, run anywhere nên architecture không quan trọng”

Java bytecode có thể portable, nhưng JVM, JNI/JNA libraries và native agents phải khớp OS/CPU/ABI.

### “Base image multi-arch là ứng dụng multi-arch”

Không đúng nếu JAR chứa native artifacts chỉ dành cho một CPU architecture.

### “JRE luôn có đủ thứ mà JDK image có”

Không chắc. JRE/custom runtime có thể thiếu tools, modules và OS dependencies.

### “Alpine luôn là lựa chọn tốt nhất vì nhỏ”

Không có kết luận chung. Musl có thể không hỗ trợ binary glibc của ứng dụng.

### “Chỉ cần sửa java.library.path để hết UnsatisfiedLinkError”

Không đúng khi binary sai architecture, thiếu dependency hoặc khác ABI.

### “Dockerfile không đổi thì image không đổi”

Không đúng với mutable tags và dependency resolution chưa được cố định.

### “Distroless không có shell nghĩa là không thể debug”

Có thể dùng diagnostic image, JFR/metrics, ephemeral debug container và phương án ngoài image, nhưng phải chuẩn bị trước.

### “Non-root chỉ cần thêm USER”

Không đủ. Cần kiểm tra quyền secrets, volumes, temp directories và native extraction.

### “Memory limit chính là giới hạn heap”

Sai. Native/off-heap/thread stacks/JVM overhead cũng dùng bộ nhớ container.

### “Có CA của OS thì Java chắc chắn trust được”

Không đúng ở mọi distro/JDK. Phải kiểm tra Java truststore thực tế.

### “QEMU test đủ để cam kết ARM64 production”

Không luôn. Cần kiểm thử native/performance trên ARM64 thật nếu đó là nền tảng đích.

### “docker build thành công là migration xong”

Không đúng. TLS, DNS, native loader, timezone, font, resource limits và shutdown có thể chỉ lỗi khi chạy.

## 34. Mẫu hồ sơ đánh giá container compatibility

~~~text
APPLICATION
  Service:
  Owner:
  Java compiler release:
  Current JDK/vendor/build:
  Target JDK/vendor/build:
  App artifact hash:
  Main/JVM flags:

IMAGE
  Current tag/digest:
  Target tag/digest:
  Distro/version:
  libc/version:
  JDK/JRE/jlink/distroless:
  Support/patch policy:

PLATFORM
  linux/amd64:
  linux/arm64:
  Other target OS:
  CPU instruction baseline:
  Kernel/cgroup assumptions:

NATIVE DEPENDENCIES
  JNI/JNA:
  JVMTI/APM agent:
  Native codec/database/HSM:
  libstdc++/libgcc:
  OpenSSL/crypto:
  ABI and dynamic dependencies:
  Per-platform artifacts:

RUNTIME DATA
  CA/truststore:
  mTLS keys:
  DNS/proxy:
  Timezone/locale:
  Fonts:
  Temporary directories:
  File permissions:

SECURITY
  Non-root UID/GID:
  Read-only root:
  Secrets mount:
  Capabilities:
  Vulnerability scan:
  SBOM/provenance:

RESOURCES
  Memory limit:
  Heap max:
  Direct/native memory:
  CPU quota:
  Thread settings:
  GC/metrics:

VALIDATION
  Startup:
  Native loading:
  TLS/DNS:
  Database/message broker:
  Data/time/encoding:
  Font/rendering:
  Load/stress tests:
  SIGTERM/shutdown:
  Per-platform tests:
  Canary/rollback:

DECISION
  Approved image digest:
  Owner:
  Risks/exceptions:
  Rollback digest:
  Next patch milestone:
~~~

Hồ sơ này nên được lưu cùng image digest và build provenance để một sự cố production có thể được tái hiện chính xác.

## 35. Checklist phát hành

- [ ] Xác nhận JDK vendor/version/build và Java release của artifact.
- [ ] Xác nhận base image distribution, libc và immutable digest.
- [ ] Xác nhận manifest cho tất cả target architectures.
- [ ] Kiểm tra từng JNI/JNA/JVMTI library đúng platform.
- [ ] Kiểm tra native loader, symbols và dependencies.
- [ ] Không có glibc/musl mismatch ngoài ý muốn.
- [ ] Kiểm soát CPU instruction baseline.
- [ ] Runtime modules đủ nếu dùng jlink.
- [ ] CA/truststore/mTLS đúng và có quyền đọc.
- [ ] Timezone, locale, charset và fonts đúng theo nghiệp vụ.
- [ ] DNS/proxy/TLS/network paths hoạt động.
- [ ] Container non-root và file permissions đúng.
- [ ] Temp/native extraction tương thích noexec/read-only policy.
- [ ] ENTRYPOINT nhận tín hiệu và shutdown kịp thời.
- [ ] Heap/off-heap/native memory có headroom trong cgroup.
- [ ] Observability/JFR/GC logging có cấu hình phù hợp.
- [ ] Integration tests chạy trên final production image.
- [ ] Test ARM64 trên node thật nếu hỗ trợ arm64.
- [ ] Security scan/SBOM/provenance hoàn tất theo chính sách.
- [ ] Có canary và rollback theo đúng image digests.

## 36. Tổng kết

Container base image là một phần thiết yếu của hợp đồng tương thích khi nâng Java. Đổi từ JDK image sang JRE/distroless, từ Debian sang Alpine, hoặc từ amd64 sang arm64 có thể làm hỏng ứng dụng dù Java source không đổi và build vẫn thành công.

Những nguyên tắc cần nhớ:

1. **Tách Java compatibility với native/OS compatibility.** Class file đúng không chứng minh .so/.dll, libc hoặc JNI ABI đúng.
2. **Chọn image theo dependency thực tế.** JDK/JRE, CA, timezone, fonts, system packages và native agents đều có thể quan trọng.
3. **Kiểm tra kiến trúc đích đến từng native binary.** Multi-arch manifest không tự bảo đảm application multi-arch.
4. **Quản lý bằng digest và provenance.** Mutable tags không thay thế immutable artifact identity.
5. **Hiểu giới hạn container.** Heap chỉ là một phần memory; cgroups và CPU quota tác động tới JVM.
6. **Tối giản có chủ đích.** Non-root, read-only filesystem, jlink và distroless cần đi cùng test và phương án chẩn đoán.
7. **Giảm số biến trong một lần migration.** Nâng JDK, đổi distro/libc, thu gọn image và thêm ARM64 là những rủi ro riêng.
8. **Kiểm thử final image trên target platform.** Startup, native calls, TLS, dữ liệu, hiệu năng và graceful shutdown đều phải được xác minh.

Một migration đáng tin không chỉ tạo ra image có nhãn Java mới. Nó phải tạo được artifact đúng hệ điều hành và kiến trúc CPU đã cam kết, mang đủ thư viện hệ thống, có thể vá bảo mật, vận hành ổn định và rollback an toàn khi cần.

