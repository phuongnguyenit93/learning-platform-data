# Khả năng hỗ trợ Shenandoah theo bản phân phối JDK, hệ điều hành và kiến trúc

> **Chủ đề cha: Shenandoah · Ngữ cảnh Java 15.** Shenandoah là bộ thu gom rác HotSpot hướng tới **độ trễ dừng ngắn** bằng cách thực hiện nhiều công việc GC đồng thời với ứng dụng. **JEP 379 đưa Shenandoah thành tính năng production ở JDK 15**; nhưng việc một tính năng có trong mã nguồn OpenJDK **không có nghĩa nó có sẵn trong mọi bản nhị phân JDK, mọi JVM engine hoặc mọi tổ hợp OS/CPU**. Khi triển khai, câu hỏi chính xác là: **“Bản JDK đang chạy trong đúng container/máy này có khởi động được và thực sự chọn Shenandoah hay không?”**

**Ghi chú phiên bản:** Java 15 là mốc lịch sử của tính năng, không phải khuyến nghị triển khai một JDK 15 đã hết thời gian bảo trì. Bài ưu tiên Java 17+ và các bản LTS hiện đại, tách rõ khả năng Shenandoah cơ bản với **generational Shenandoah được chuẩn hóa ở JDK 25 (JEP 521)**. Không dựa vào các tùy chọn thử nghiệm cũ hoặc bảng platform đã lỗi thời.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **Java language/API version**, **JVM implementation**, **JDK distribution/vendor**, **OS**, **CPU architecture** và **native build configuration**.
2. Giải thích vì sao cùng lệnh `java -XX:+UseShenandoahGC` chạy trên một bản Temurin/Zulu/Corretto nhưng có thể thất bại trên một bản phân phối khác, dù đều báo `openjdk version "25..."`.
3. Biết các mốc: Shenandoah production **JDK 15**; mainstream OpenJDK trên JDK 17/21/25; generational Shenandoah **JDK 25**, còn có thể cần bật **tường minh**.
4. Đọc bảng hỗ trợ OS/architecture đúng mức: Linux, Windows, macOS và các cổng kiến trúc có **mức kiểm thử khác nhau**, không phải mọi artifact có cùng ma trận.
5. Biết rằng **x86_64/amd64** và **AArch64/arm64** là các kiến trúc thường gặp, còn PPC64/RISC-V tùy port và build; **OpenJDK 25 đã loại bỏ x86 32-bit port (JEP 503)**.
6. Dùng lệnh khởi động và GC logging để chứng minh Shenandoah thực sự hoạt động thay vì suy đoán từ OS name/vendor.
7. Chạy ba chương trình Java 17+ để kiểm tra hỗ trợ ở runtime hiện tại, kiểm thử workload, và rà nhiều JDK binaries với cùng thao tác.
8. Xử lý lỗi `Unrecognized VM option`, `Shenandoah GC is not supported on this platform`, JVM không có GC, mismatch giữa PATH và JAVA_HOME, container multi-arch, hoặc `jlink` custom runtime.
9. Thiết lập smoke tests trong CI/deployment để tránh âm thầm dùng GC khác với cấu hình đã được benchmark.
10. Đánh giá hiệu năng và hoạt động nền tảng thực tế, không suy “supported” thành “luôn nhanh nhất” hoặc “được vendor hỗ trợ thương mại”.

## 2. “Có hỗ trợ Shenandoah” là câu hỏi nhiều tầng

Một ứng dụng Java có thể chạy tốt nhưng Shenandoah không khả dụng. Hãy phân biệt các tầng sau:

| Tầng | Câu hỏi phải kiểm tra | Ví dụ |
| --- | --- | --- |
| **Java version** | Bản JDK có chứa mã nguồn tính năng/mode không? | JDK 15 có Shenandoah production; JDK 25 có generational mode |
| **JVM implementation** | Đây có phải HotSpot với Shenandoah hay một VM khác? | HotSpot, OpenJ9, GraalVM Native Image là các runtime khác nhau |
| **JDK vendor/distribution** | Vendor có build/đóng gói Shenandoah không? | Azul Zulu, Eclipse Temurin, Corretto, Oracle builds có chính sách khác |
| **OS** | Native OS port của runtime/GC có sẵn? | Linux, Windows, macOS; không suy từ chỉ `os.name` |
| **CPU architecture** | Kiến trúc có được triển khai/kiểm thử barrier và mã GC không? | x86_64, AArch64, PPC64, RISC-V |
| **Artifact thực tế** | Bản JDK/JRE/container image đang chạy đã bật GC ở lúc build? | Một image nhỏ hoặc build tùy chỉnh có thể khác package desktop |
| **Runtime flags** | Có bật đúng collector/mode mà không bị option khác ghi đè? | `-XX:+UseShenandoahGC` và mode tương ứng |
| **Operational support** | Thực tế GC có khởi động, chạy GC cycles và đáp ứng SLO? | Log `Using Shenandoah`, GC MXBeans/JFR, benchmark dưới tải |
| **Vendor support policy** | Có bản vá/bảo mật/SLA cho tổ hợp đó không? | Cần kiểm trang support lifecycle của từng vendor |

**Công thức thực tế:**

~~~text
Tên JDK hoặc version ──X──> Không đủ chứng minh có Shenandoah

Bản runtime chính xác
  + VM implementation
  + JDK build flags
  + OS + architecture
  + collector/mode options
  + startup thành công
  + log/management metrics xác nhận GC được chọn
        ↓
Kết luận: Shenandoah khả dụng trong MÔI TRƯỜNG CỤ THỂ ấy
~~~

Một checkbox “Supported” trên website có thể áp dụng cho dòng JDK/version/OS/architecture khác. Một số build có thể hỗ trợ mode Shenandoah thường nhưng chưa hỗ trợ **generational**. “Có thể khởi động” cũng **không đồng nghĩa đã benchmark và đạt SLO**.

## 3. Các mốc phiên bản còn giá trị khi đọc tài liệu hiện nay

| Mốc | Diễn giải đúng | Ứng dụng hiện nay |
| --- | --- | --- |
| **JDK 15 · JEP 379** | Shenandoah trở thành production feature trong OpenJDK/HotSpot | `-XX:+UseShenandoahGC` là cờ chọn collector production khi build có GC đó |
| **JDK 17 LTS** | Shenandoah tồn tại trên nhiều bản HotSpot LTS hiện đại | Kiểm artifact cụ thể, không phải mọi Java 17 binary |
| **JDK 21 LTS** | Tiếp tục được bảo trì trong các bản HotSpot có hỗ trợ | Thích hợp so sánh ứng dụng đã chạy JDK 21; giữ patch mới |
| **JDK 24** | Generational Shenandoah từng ở giai đoạn experimental theo lịch sử | **Không coi flag thử nghiệm lịch sử là hướng dẫn chung** |
| **JDK 25 · JEP 521** | Generational Shenandoah được hoàn thiện thành tính năng chuẩn của JDK | Có thể chọn `-XX:ShenandoahGCMode=generational` trên HotSpot build có hỗ trợ |
| **JDK 25 · JEP 503** | Port x86 32-bit của mainline OpenJDK bị loại bỏ | Không tuyên bố các JDK 25 mainline x86 32-bit vẫn có Shenandoah |
| **JDK 26/27 và bản sau** | Vendor có thể thay đổi hỗ trợ/default/options theo release | Đọc release notes và kiểm thực tế; **đừng đoán từ phiên bản trước** |

**Quan trọng:** JDK 25 có generational Shenandoah **không có nghĩa generational luôn là chế độ mặc định**. Theo tài liệu command-line JDK 25/27, chế độ mặc định Shenandoah thường là `satb` (single-generation), còn `generational` cần bật khi muốn dùng:

~~~bash
# JDK 25+ HotSpot build có hỗ trợ Shenandoah generational:
java -XX:+UseShenandoahGC \
     -XX:ShenandoahGCMode=generational \
     -Xlog:gc=info -version
~~~

Đây là lệnh để **kiểm tra mode được yêu cầu trên bản JDK 25+**, không phải lệnh dùng được trên mọi JDK 17/21/24. Với các bản cũ và vendor backport, hãy tham khảo tài liệu chính xác của build thay vì lấy flag của JDK 25 áp dụng bừa.

**Không cần `-XX:+UnlockExperimentalVMOptions` để bật Shenandoah production ở JDK 15+**, và không sử dụng hướng dẫn experimental-era như thể chúng vẫn là cài đặt chuẩn.

## 4. Phân phối JDK: cùng bytecode nhưng không cùng bộ GC

### 4.1. Vì sao vendor quyết định khả năng hỗ trợ?

OpenJDK là mã nguồn và dự án tham chiếu; mỗi nhà phát hành có thể:
- Xây một HotSpot VM có hoặc không có bộ phận Shenandoah theo build configuration.
- Phát hành runtime cho OS/CPU khác nhau, với mức kiểm thử và hỗ trợ khác nhau.
- Backport/sửa lỗi Shenandoah vào nhánh LTS theo chính sách riêng.
- Cung cấp VM engine khác HotSpot, hoặc một binary **native image** không dùng HotSpot GC.
- Đóng gói JRE tối giản/custom runtime với thành phần và policy vận hành khác JDK đầy đủ.

Do đó **`java --version` chỉ nói một phần**. Muốn biết có Shenandoah hãy **khởi chạy JVM với flag của Shenandoah và xem log/GC beans**.

### 4.2. Những tên phân phối thường gặp

Bảng mang tính **định hướng để hỏi đúng câu hỏi**, không phải cam kết mọi version/SKU/platform:

| Bản phân phối/VM | Tình hình Shenandoah đáng chú ý | Kiểm tra trước triển khai |
| --- | --- | --- |
| **Red Hat build of OpenJDK / Fedora OpenJDK** | Dự án Shenandoah do Red Hat đóng góp mạnh; nhiều bản build Red Hat/Fedora có hỗ trợ | Đúng package, patch level, OS/CPU và support contract |
| **Eclipse Temurin (HotSpot)** | Nhiều bản HotSpot OpenJDK hiện đại cung cấp Shenandoah | Kiểm đúng Temurin version/arch/JRE-vs-JDK, smoke test khi deploy |
| **Azul Zulu** | Tài liệu OpenJDK Shenandoah ghi Zulu có Shenandoah từ các bản 11u tương ứng; bản JDK hiện đại có thể chạy | Kiểm Zulu JVM cụ thể và OS/CPU; không đồng nhất Zulu với một JVM khác |
| **Amazon Corretto** | Theo OpenJDK Shenandoah wiki, các bản Corretto 11.0.9+ có hỗ trợ ở nhiều build | Kiểm image Corretto cụ thể, Amazon Linux/container architecture |
| **BellSoft Liberica** | Tài liệu Liberica mô tả Shenandoah là collector được cung cấp cho nhiều platform | Đúng Liberica edition/version, OS, arch, flags |
| **SapMachine** | Dự án Shenandoah ghi có hỗ trợ từ SapMachine 17 | Kiểm artifacts và lifecycle cụ thể |
| **Oracle JDK / Oracle-provided OpenJDK builds** | OpenJDK Shenandoah wiki ghi Oracle **không đóng gói Shenandoah** trong các build của họ, dù Java man pages mô tả flag chung của HotSpot | **Đừng suy từ docs chung rằng binary Oracle hiện tại có Shenandoah**; thử chính binary |
| **IBM Semeru / Eclipse OpenJ9** | OpenJ9 dùng bộ các GC policies riêng, không tương đương HotSpot Shenandoah | Đọc tài liệu GC của OpenJ9, không áp dụng `UseShenandoahGC` của HotSpot |
| **GraalVM Native Image** | Native executable có bộ quản lý bộ nhớ khác VM HotSpot; `-XX:+UseShenandoahGC` của java launcher không tự áp dụng cho native image | Chọn collector/runtime theo tài liệu Native Image, không dựa vào Java source version |
| **Build tùy chỉnh / jlink runtime / Docker image** | Quyền chọn GC phụ thuộc VM native binary thật sự đi kèm | Kiểm đúng image digest/binary sau khi đóng gói và trong container đang chạy |

Danh sách trên **không phải vendor ranking hoặc danh sách cấp phép**. Dòng “có Shenandoah” từ wiki có thể được cập nhật hoặc bị giới hạn theo bản build. Đối với quyết định sản xuất, dùng thông báo support của vendor và smoke test trong **môi trường triển khai cuối cùng**.

### 4.3. Bẫy “Oracle Java docs có option thì Oracle JDK chắc chắn có”

Tài liệu Java command-line mô tả khả năng và cú pháp của HotSpot nói chung, trong đó có `-XX:+UseShenandoahGC`. Nhưng Oracle-provided binaries có thể **không build kèm** Shenandoah. Các tài liệu/website về Java cũng có thể dùng từ “OpenJDK” cho cả dự án nguồn lẫn build từ một vendor.

Vì vậy, hai mệnh đề sau **không tương đương**:

~~~text
"OpenJDK source tree contains Shenandoah code."
"Exact /opt/java/bin/java binary includes and can run Shenandoah."
~~~

Chỉ lệnh thử khởi động, GC initialization log và chính sách vendor mới giúp kết luận cho binary thực tế.

### 4.4. HotSpot và OpenJ9 không có cùng dòng JVM flags

`-XX:+UseShenandoahGC` là option của HotSpot build tích hợp Shenandoah. OpenJ9 có các **GC policies** riêng (`gencon`, `balanced`, `optthruput`, v.v. tùy phiên bản).

Một ứng dụng Spring/Quarkus hoặc Java SE giống hệt có thể chạy trên cả HotSpot và OpenJ9, nhưng:
- Không có lý do để kỳ vọng `-XX:+UseShenandoahGC` hoạt động trên OpenJ9.
- Không được tự đổi `gencon` thành “Shenandoah” vì cùng nhắm tới giảm pause.
- Log/command-line monitoring và mặc định collector khác nhau.

Như vậy **VM implementation** là chiều độc lập với “vendor hỗ trợ Java 21” hoặc “OS hỗ trợ Java”.

## 5. Hệ điều hành: Linux, Windows, macOS và ranh giới portability

### 5.1. Cách đọc OpenJDK Shenandoah platform overview

Trang OpenJDK Shenandoah wiki mô tả **mức độ ưu tiên/kiểm thử** của các OS ports:
- **Linux:** Mục tiêu chính, được kiểm thử liên tục trong dự án.
- **Windows:** Mục tiêu thứ cấp, được kiểm thử liên tục.
- **macOS:** Port bổ sung, cộng đồng tham gia kiểm thử.

Đây là mô tả về **dự án/cổng OpenJDK Shenandoah**, **không** phải giấy bảo đảm rằng mọi binary trên OS ấy đều hỗ trợ. Ví dụ một vendor có thể phát hành Java 25 cho macOS ARM64, nhưng chưa tích hợp Shenandoah vào artifact đó; hoặc một image Linux tối giản có native JVM không chứa collector.

Với OS ít phổ biến, đừng trích danh sách historical ports rồi khẳng định là platform production hiện thời. Hỗ trợ mainline JDK có thể thay đổi theo JEP/OS lifecycle; cần xem **OS port + CPU port + build cụ thể**.

### 5.2. Linux

Linux là môi trường thường dùng để chạy Shenandoah trong cloud/containers. Tuy nhiên:
- Hỗ trợ khác nhau giữa Linux x86_64, aarch64, ppc64le, riscv64 và các kiến trúc khác.
- `glibc`/`musl`, kernel, native toolchain và vendor đóng gói là yếu tố ảnh hưởng artifact.
- Một container có thể dùng **Linux userspace** nhưng chạy trên host kiến trúc CPU không như môi trường build CI.
- cgroup CPU quota/memory limit có thể thay đổi khả năng đáp ứng latency ngay cả khi GC đã chạy.
- Docker image `openjdk:...`, `eclipse-temurin:...`, `amazoncorretto:...` khác nhau; **image tag không phải bằng chứng đã chọn Shenandoah**.

**Kiểm tra trực tiếp trong container**, không chỉ trên máy host:

~~~bash
# Bên trong container thực tế:
java -version
java -XX:+UseShenandoahGC -Xms64m -Xmx128m \
     -Xlog:gc=info -version

# Quan sát "Using Shenandoah" và exit code 0 nếu build hỗ trợ.
~~~

Cần kiểm image digest, base image, native architecture, startup flags cuối cùng và dependency trên container runtime.

### 5.3. Windows

Shenandoah có Windows port trong OpenJDK, và **đã được xác minh bằng chương trình Java 17+ trên Windows 11, Azul Zulu JDK 24 x64** trong bài này. Nhưng không thể suy:
- Mọi Oracle/HotSpot/JDK build cho Windows đều có Shenandoah.
- Windows x64 và Windows ARM64 dùng cùng native code.
- Một JRE embed trong ứng dụng là cùng binary với `java` người dùng chạy ngoài terminal.

Các path thường gặp trên Windows có khoảng trắng (`C:\Program Files\...`). Trong PowerShell hãy dùng **call operator `&`**:

~~~powershell
$java = "C:\Path\To\jdk\bin\java.exe"
& $java -version
& $java -XX:+UseShenandoahGC -Xms64m -Xmx128m -Xlog:gc=info -version
~~~

**`C:\Path\To\jdk\bin\java.exe` là path minh họa, phải thay bằng file hiện có.** Windows shell và process manager có thể đặt environment/GC flags riêng; kiểm command thật của service thay vì chỉ test PATH của người dùng.

### 5.4. macOS (Intel và Apple Silicon)

macOS có binary JDK trên **x86_64** và **aarch64/arm64 (Apple Silicon)** ở nhiều vendors, nhưng:
- Cùng nhãn `macOS` chưa nói kiến trúc.
- Một Terminal chạy dưới Rosetta có thể chọn x64 JDK, còn service runtime dùng ARM64 JDK (hoặc ngược lại).
- Sự hỗ trợ Shenandoah cần kiểm trên **JVM binary/arch thực tế**; không chỉ dựa vào việc hãng cung cấp Java cho Apple Silicon.
- VM được host/chip hỗ trợ không đồng nghĩa vendor đã kiểm thử Shenandoah với cùng SLA.

Chạy `java -version`, `uname -m`, rồi smoke test `-XX:+UseShenandoahGC` trong đúng shell/process context.

### 5.5. OS được JDK hỗ trợ nhưng GC chưa chắc được hỗ trợ

Một JVM phát hành cho một OS có thể chạy G1/Serial/Parallel nhưng không có Shenandoah vì collector cần các phần **native/architecture-specific barrier code**. Ngược lại, upstream có thể có port nhưng vendor không build/ship nó.

Tách riêng:
1. **Java hỗ trợ OS**.
2. **HotSpot hỗ trợ OS/CPU combination**.
3. **Shenandoah được build vào HotSpot**.
4. **Collector runtime/mode có thể hoạt động trong môi trường đích**.
5. **Vendor cam kết hỗ trợ sử dụng collector đó**.

## 6. Kiến trúc CPU: x86_64, AArch64, PPC64, RISC-V...

### 6.1. Vì sao Shenandoah cần code theo kiến trúc?

Shenandoah sử dụng **barrier mechanisms**, code generation/JIT/compiler và một số fast paths liên quan object references để duy trì tính đúng khi ứng dụng và GC cùng chạy. Một phần quan trọng phụ thuộc CPU architecture và HotSpot port:
- Instruction set/atomic operations và memory ordering.
- Read/write barriers ở interpreter/JIT.
- Các lệnh an toàn khi relocate/update references.
- Cách tạo code bởi C1/C2 và runtime stubs.
- Kiểm thử CPU/OS port, ABI và memory model.

Không thể chỉ recompile Java classes cho một kiến trúc mới để có Shenandoah đầy đủ. Thường phải có code native và kiểm thử cho CPU ấy.

### 6.2. Tình trạng kiến trúc theo OpenJDK Shenandoah wiki

| Kiến trúc | Định hướng upstream Shenandoah | Điều cần chú ý hiện nay |
| --- | --- | --- |
| **x86_64 / amd64** | Mục tiêu chính, continuously tested | Rất phổ biến trên Linux/Windows/macOS Intel, nhưng vendor build vẫn cần xác minh |
| **AArch64 / arm64** | Mục tiêu chính, continuously tested | Phổ biến trên Linux ARM servers và macOS Apple Silicon; phải đúng binary arch |
| **PPC64 (ví dụ ppc64le)** | Port thứ cấp/community tested | Tùy JDK vendor/version/OS artifact |
| **RISC-V 64 (riscv64)** | Port thứ cấp/community tested theo upstream | Tùy giai đoạn port và binary thực tế, cần smoke test |
| **x86 32-bit (i386/ia32)** | Được nhắc trong lịch sử port | **Không dùng bảng cũ để suy hỗ trợ JDK 25+: JEP 503 loại port x86 32-bit mainline** |
| **ARM32** | Wiki mô tả còn trong quá trình phát triển | Không xem là production-supported nếu chưa có bằng chứng artifact |
| **s390x** | Wiki Shenandoah ghi không hỗ trợ ở trang tổng quan | Một JDK có thể chạy trên IBM Z **không** nghĩa có Shenandoah |
| **SPARC và các port cũ** | Một số tài liệu quá khứ còn nhắc | Không đưa vào ma trận deployment hiện đại khi mainline/OS port đã ngừng |

**Chú ý:** Bảng phản ánh mô tả upstream cùng những thay đổi JEP gần đây, **không phải chứng chỉ tương thích cho mọi bản JDK 25/26/27**. Khi vendor cung cấp Linux s390x hoặc AIX ppc64 binaries chẳng hạn, điều đó **không trực tiếp** nói Shenandoah hoạt động. Cần test native GC implementation tương ứng.

### 6.3. `os.arch` không phải phép kiểm chứng hỗ trợ

Java có thể in:

~~~text
os.arch=amd64    (một số JVM Windows/x64)
os.arch=x86_64  (một số JVM Linux/x64)
os.arch=aarch64 (một số JVM ARM64)
~~~

Đây là tên kiến trúc theo runtime, không chứa thông tin:
- Shenandoah có được compile hay không.
- Native code cho architecture này có hoàn chỉnh hay không.
- CPU/OS có feature requirements được đáp ứng không.
- Nhà cung cấp có hỗ trợ trên architecture này không.

Dùng `System.getProperty("os.arch")` để **chẩn đoán môi trường**, không để kết luận support.

## 7. Phép kiểm tối thiểu: xác nhận collector thực sự hoạt động

**Quy trình chuẩn cho HotSpot hiện đại có hỗ trợ:**

~~~bash
# 1) Kiểm chính xác binary đang được gọi:
java -version

# 2) Yêu cầu tạo HotSpot với Shenandoah:
java -XX:+UseShenandoahGC -Xms64m -Xmx128m \
     -Xlog:gc=info -version
~~~

Khi thành công, GC log có thể chứa dòng kiểu:

~~~text
[...][info][gc] Using Shenandoah
~~~

`[...]` là timestamp/decorations phụ thuộc JVM, **không phải stdout cố định**. Đọc cả **exit code**: quá trình khởi động có thể in thông báo lỗi và trả exit code khác 0.

### 7.1. Ý nghĩa của các flags

| Flag | Ý nghĩa |
| --- | --- |
| `-XX:+UseShenandoahGC` | Yêu cầu chọn Shenandoah khi VM build hỗ trợ |
| `-Xms64m` | Initial/min heap setting trong smoke test |
| `-Xmx128m` | Max heap trong smoke test; chỉ là giá trị thử nghiệm |
| `-Xlog:gc=info` | Hiện log GC startup để kiểm collector |
| `-version` | In thông tin phiên bản rồi thoát; kiểm tra startup nhưng không benchmark |
| `-XX:ShenandoahGCMode=generational` | Yêu cầu generational mode trên **JDK 25+ build hỗ trợ** |

**Không dùng `-XX:+IgnoreUnrecognizedVMOptions` để “đảm bảo start được”**. Nó có thể che dấu flag không có trong JVM; chương trình tưởng đã bật Shenandoah nhưng thực tế không đúng, gây sai benchmark và thay đổi latency behavior.

### 7.2. Lỗi có thể quan sát

| Hiện tượng | Nguyên nhân khả dĩ | Cách khắc phục |
| --- | --- | --- |
| `Unrecognized VM option 'UseShenandoahGC'` | Binary/VM không biết flag này | Kiểm JVM implementation và vendor/build; không đổi đại tên flag |
| `Shenandoah GC is not supported on this platform` | CPU/OS architecture path bị từ chối | Chọn build hỗ trợ đúng architecture hoặc collector khác |
| Lỗi “GC not included/available” | Vendor build không đóng gói collector | Thay artifact bằng build HotSpot có Shenandoah |
| Exit code 0 nhưng không thấy Shenandoah trong log | Sai đối tượng Java đang chạy/flag bị xử lý khác hoặc không bật logging phù hợp | Kiểm `Using Shenandoah`, MXBeans, startup config |
| `Unrecognized VM option ShenandoahGCMode=generational` | JDK quá cũ, không có mode, hoặc vendor build khác | Chỉ dùng JDK25+ hỗ trợ; xem docs release |
| `Could not reserve enough space ... heap` | Thiếu memory/virtual address/container restriction | Kiểm memory limit, heap flags, OS/cgroup |
| Lỗi VM options conflicts | Nhiều collector flags được bật | Chỉ chọn một GC; xem scripts/`JAVA_TOOL_OPTIONS`/`JDK_JAVA_OPTIONS` |
| Build hoạt động trên host nhưng fail trong container | Base image/JDK/arch khác hoặc quota/security khác | Thử trực tiếp trong image đã deploy và pin digest |
| Local `java` và service `java` khác | PATH/JAVA_HOME/IDE/runtime launcher trỏ binary khác | Ghi absolute java path và startup command của service |

Bắt đầu bằng **lỗi thật do JVM báo**; không tự quy mọi lỗi thành thiếu Shenandoah. `-Xmx` quá lớn, permission, unsupported OS/JDK options, lỗi cấu hình môi trường đều là nguyên nhân riêng.

## 8. Ví dụ 1 — Java 17+ tự kiểm hỗ trợ trên runtime hiện tại

Chương trình kiểm:
1. JDK feature version, tên VM/vendor, OS và CPU architecture.
2. Đường dẫn **`java` của chính runtime đang chạy** qua `java.home/bin/java`.
3. Khởi chạy **một JVM con** với `-XX:+UseShenandoahGC`.
4. JVM con dùng `GarbageCollectorMXBean` để xác nhận collector đang hoạt động có tên Shenandoah.
5. Bố mẹ chỉ trả `SUPPORTED` khi **JVM con exit code 0** và collector thật được chọn.

Điều này mạnh hơn việc chỉ kiểm `System.getProperty("java.vm.name").contains("HotSpot")`. Kết quả hỗ trợ vẫn chỉ áp dụng cho đúng binary/JVM đang được test, không phải tất cả binaries của vendor ấy.

### 8.1. Mã đầy đủ — `ShenandoahSupportProbe.java`

~~~java
import java.io.IOException;
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;

public class ShenandoahSupportProbe {
    static boolean selected() {
        return ManagementFactory.getGarbageCollectorMXBeans().stream()
                .map(GarbageCollectorMXBean::getName)
                .anyMatch(name -> name.toLowerCase(Locale.ROOT)
                        .contains("shenandoah"));
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 1 && "--child".equals(args[0])) {
            System.out.println("childSelectedShenandoah=" + selected());
            return;
        }
        boolean windows = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT).contains("windows");
        Path java = Path.of(System.getProperty("java.home"), "bin",
                windows ? "java.exe" : "java");
        String classPath = System.getProperty("java.class.path");

        System.out.println("feature=" + Runtime.version().feature());
        System.out.println("vmName=" + System.getProperty("java.vm.name"));
        System.out.println("vmVendor=" + System.getProperty("java.vm.vendor"));
        System.out.println("os=" + System.getProperty("os.name"));
        System.out.println("arch=" + System.getProperty("os.arch"));

        List<String> command = List.of(java.toString(),
                "-XX:+UseShenandoahGC",
                "-Xms64m", "-Xmx128m",
                "-cp", classPath,
                ShenandoahSupportProbe.class.getName(), "--child");
        Process process = new ProcessBuilder(command)
                .redirectErrorStream(true).start();
        String output;
        try (var input = process.getInputStream()) {
            output = new String(input.readAllBytes(),
                    StandardCharsets.UTF_8);
        }
        int exitCode = process.waitFor();
        boolean supported = exitCode == 0
                && output.contains("childSelectedShenandoah=true");
        System.out.println("probeExitCode=" + exitCode);
        System.out.println("shenandoahActuallySelected=" + supported);
        System.out.println("supportStatus=" +
                (supported ? "SUPPORTED" : "UNAVAILABLE"));
    }
}
~~~

**Biên dịch và chạy (Java 17+ có `java.management`):**

~~~bash
javac --release 17 -encoding UTF-8 ShenandoahSupportProbe.java
java ShenandoahSupportProbe
~~~

**Stdout quan sát trên Windows 11 x64 / Azul Zulu OpenJDK 24.0.2 HotSpot:**

~~~text
feature=24
vmName=OpenJDK 64-Bit Server VM
vmVendor=Azul Systems, Inc.
os=Windows 11
arch=amd64
probeExitCode=0
shenandoahActuallySelected=true
supportStatus=SUPPORTED
~~~

Giá trị `feature`, `vmName`, `vmVendor`, `os`, `arch` có thể khác trên máy khác. Quan trọng nhất là:
- `probeExitCode=0`: JVM con đã khởi động và kết thúc thành công.
- `shenandoahActuallySelected=true`: GC MXBean ở JVM con báo Shenandoah.
- `supportStatus=SUPPORTED`: chương trình kết hợp **exit status** và **đúng collector**; không chỉ dùng tên vendor.

Nếu không hỗ trợ, kết quả thường có `probeExitCode` khác 0, `shenandoahActuallySelected=false` và `supportStatus=UNAVAILABLE`. Giá trị exit code **không cố định giữa JVM/OS**.

### 8.2. Giới hạn của probe và cải tiến production

- Trình thử yêu cầu **`java` executable** tại `java.home/bin/java`. Một custom runtime image có thể dùng layout khác hoặc bị giới hạn quyền spawn process.
- Với JDK có GC mode riêng, probe trên kiểm **Shenandoah cơ bản**, **không** kiểm generational mode JDK25. Muốn kiểm mode, thêm flag tương ứng và xác minh log/startup thực tế.
- `getGarbageCollectorMXBeans().getName()` là tên do implementation cung cấp; với vendor/custom VM, nên dùng **GC initialization log** làm bằng chứng bổ sung.
- Chương trình đọc toàn bộ output subprocess cho dễ hiểu; trong production test harness nên đặt timeout và giới hạn output để tránh treo/hết bộ nhớ nếu child bất thường.
- JVM con có thể bị ảnh hưởng bởi `JAVA_TOOL_OPTIONS`, container policy hoặc flags từ environment; cần chạy đúng môi trường production.
- Một startup thành công không có nghĩa mọi phase GC đã được kiểm thử hoặc đủ heap/headroom cho workload thật. Kết hợp **workload smoke test** và SLO testing.

## 9. Ví dụ 2 — Smoke test hoạt động của Shenandoah với cấp phát bộ nhớ

Sau khi xác minh startup, cần xem GC thực sự xử lý allocation dưới tải. Ví dụ tạo **8,192 arrays, mỗi array 64 KiB**, tổng cấp phát **512 MiB** nhưng chỉ giữ các mảng gần nhất trong ring 256 phần tử (**16 MiB payload**). Nó không yêu cầu mạng, file đầu vào hoặc thư viện bên ngoài.

### 9.1. Mã độc lập — `ShenandoahGcWorkloadDemo.java`

~~~java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.List;
import java.util.Locale;

public class ShenandoahGcWorkloadDemo {
    static boolean shenandoahActive(
            List<GarbageCollectorMXBean> collectors) {
        return collectors.stream()
                .map(GarbageCollectorMXBean::getName)
                .anyMatch(name -> name.toLowerCase(Locale.ROOT)
                        .contains("shenandoah"));
    }

    public static void main(String[] args) {
        List<GarbageCollectorMXBean> collectors =
                ManagementFactory.getGarbageCollectorMXBeans();
        byte[][] live = new byte[256][];
        int blockBytes = 64 * 1024;
        int iterations = 8_192;
        long checksum = 0;

        for (int i = 0; i < iterations; i++) {
            byte[] block = new byte[blockBytes];
            block[0] = (byte) i;
            block[blockBytes - 1] = (byte) (i >>> 8);
            live[i % live.length] = block;
            checksum += block[0];
        }
        for (byte[] block : live) {
            checksum += block[block.length - 1];
        }

        System.out.println("shenandoahActive=" +
                shenandoahActive(collectors));
        System.out.println("allocatedMiB=" +
                ((long) blockBytes * iterations / (1024 * 1024)));
        System.out.println("retainedPayloadMiB=" +
                ((long) live.length * blockBytes / (1024 * 1024)));
        System.out.println("checksum=" + checksum);
        System.out.println("collectors=" + collectors.stream()
                .map(GarbageCollectorMXBean::getName).toList());
    }
}
~~~

Chạy trên JDK 17+ HotSpot có Shenandoah:

~~~bash
javac --release 17 -encoding UTF-8 ShenandoahGcWorkloadDemo.java

java -XX:+UseShenandoahGC -Xms64m -Xmx128m \
     -Xlog:gc=info:file=shenandoah.log:uptime,level,tags \
     ShenandoahGcWorkloadDemo
~~~

**Stdout xác minh trên Azul Zulu JDK24/Windows x64:**

~~~text
shenandoahActive=true
allocatedMiB=512
retainedPayloadMiB=16
checksum=3840
collectors=[Shenandoah Pauses, Shenandoah Cycles]
~~~

Dòng logging của same run chứa:

~~~text
[...][info][gc] Using Shenandoah
[...][info][gc] GC(0) Pause Init Mark (...)
[...][info][gc] GC(0) Concurrent marking ...
~~~

Đây là các mẫu log **đã rút gọn**; số GC, thời lượng và tên phase phụ thuộc version/mode/collector. Không yêu cầu chúng xuất hiện y hệt mọi runtime.

### 9.2. Chạy cùng workload với G1 để đối chứng lựa chọn GC

~~~bash
java -XX:+UseG1GC -Xms64m -Xmx128m \
     -Xlog:gc=info:file=g1.log:uptime,level,tags \
     ShenandoahGcWorkloadDemo
~~~

**Stdout quan sát dưới G1 trên cùng JDK24:**

~~~text
shenandoahActive=false
allocatedMiB=512
retainedPayloadMiB=16
checksum=3840
collectors=[G1 Young Generation, G1 Concurrent GC, G1 Old Generation]
~~~

Điều này cho thấy code chạy **cùng bytecode**, nhưng loại collector đã chọn khác nhau. Nếu bạn so performance thì cần warmup, nhiều lần chạy, p99/p99.9 request latency, throughput, memory/CPU budget và các chỉ số GC, không thể quyết định collector tốt hơn từ kết quả microbenchmark này.

### 9.3. Tại sao 512 MiB cấp phát mà heap chỉ 128 MiB vẫn chạy?

Ứng dụng không giữ cả 512 MiB cùng lúc. Các blocks trong ring bị ghi đè và có thể được GC thu hồi. Con số `retainedPayloadMiB=16` là bytes **payload tối đa của 256 arrays**, chưa bao gồm headers/JVM metadata. Đó là ví dụ để **kích hoạt GC cycles** trong heap nhỏ, **không phải** workload đại diện cho service thật.

Nếu chương trình hết memory, hãy xét live set, heap options và process environment; đừng tự kết luận Shenandoah không hỗ trợ OS. Hỗ trợ tính năng và đủ tài nguyên để chạy workload là hai câu hỏi khác nhau.

## 10. Ví dụ 3 — Kiểm cùng một lệnh trên nhiều JDK binaries

Khi cần chọn vendor/runtime, cách chắc chắn hơn tra bảng là **chạy một phép thử tương đương trên từng binary**. Chương trình sau nhận danh sách đường dẫn `java` và với mỗi binary:
1. Mở process con bằng đường dẫn được truyền vào.
2. Thử `-XX:+UseShenandoahGC` với heap thử nghiệm.
3. Bật `-Xlog:gc=info` và in `-version`.
4. Đọc exit code và tìm mẫu `Using Shenandoah` trong output.
5. Kết luận **chỉ cho candidate binary ấy**.

**Tệp `ShenandoahMultiJdkProbe.java` — độc lập, Java 17+:**

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public class ShenandoahMultiJdkProbe {
    public static void main(String[] args) throws Exception {
        boolean windows = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT).contains("windows");
        String currentJava = Path.of(System.getProperty("java.home"),
                "bin", windows ? "java.exe" : "java").toString();
        List<String> binaries = args.length == 0
                ? List.of(currentJava) : Arrays.asList(args);

        for (int index = 0; index < binaries.size(); index++) {
            String binary = binaries.get(index);
            List<String> command = new ArrayList<>();
            command.add(binary);
            command.add("-XX:+UseShenandoahGC");
            command.add("-Xms64m");
            command.add("-Xmx128m");
            command.add("-Xlog:gc=info");
            command.add("-version");

            System.out.println("candidate=" + (index + 1));
            try {
                Process process = new ProcessBuilder(command)
                        .redirectErrorStream(true).start();
                String output;
                try (var input = process.getInputStream()) {
                    output = new String(input.readAllBytes(),
                            StandardCharsets.UTF_8);
                }
                int exitCode = process.waitFor();
                boolean active = exitCode == 0
                        && output.contains("Using Shenandoah");
                System.out.println("exitCode=" + exitCode);
                System.out.println("shenandoahConfirmed=" + active);
            } catch (IOException ex) {
                System.out.println("launchFailed=" +
                        ex.getClass().getSimpleName());
            }
        }
    }
}
~~~

Chạy thử chính JDK hiện tại:

~~~bash
javac --release 17 -encoding UTF-8 ShenandoahMultiJdkProbe.java
java ShenandoahMultiJdkProbe
~~~

**Stdout chính xác trong lần kiểm thử JDK24/Zulu Windows:**

~~~text
candidate=1
exitCode=0
shenandoahConfirmed=true
~~~

Để so hai JDK trên Linux/macOS, truyền **absolute paths thực**:

~~~bash
java ShenandoahMultiJdkProbe /path/to/vendorA/bin/java /path/to/vendorB/bin/java
~~~

Trên Windows PowerShell, quote đường dẫn có khoảng trắng:

~~~powershell
java ShenandoahMultiJdkProbe "C:\Path\To\JdkA\bin\java.exe" "C:\Path\To\JdkB\bin\java.exe"
~~~

**Lưu ý:**
- Hai đường dẫn `/path/to/...` và `C:\Path\To\...` chỉ là **ví dụ**, không phải file thật.
- `shenandoahConfirmed=false` nghĩa phép thử **chưa xác nhận được Shenandoah**, có thể do JVM không hỗ trợ, lỗi flags, path, hoặc log khác định dạng. Cần đọc stderr chi tiết và tự phân loại, đừng mặc định vendor có lỗi.
- Kiểm dựa trên chuỗi `Using Shenandoah` phụ thuộc HotSpot Unified Logging; chương trình 1 dùng thêm MXBeans để xác nhận. Một bộ smoke test enterprise có thể kết hợp **cả hai phương pháp**.
- Với nhiều JDK thật, cần lưu **binary path, `java -version`, vendor/build hash, OS/arch, exit code và GC initialization log** vào báo cáo.
- Nếu muốn process builder an toàn cho input không tin cậy, giới hạn số binaries, đặt timeout và giới hạn log; ví dụ ở đây dành cho danh sách cục bộ do người vận hành chỉ định.

## 11. Kiểm tra mode: Shenandoah thường và generational khác nhau

### 11.1. Mục tiêu của generational Shenandoah

Generational Shenandoah phân biệt object **young/old** để thu gom các đối tượng chết nhanh hiệu quả hơn ở nhiều workload, giúp giảm lượng tracing/CPU overhead trong một số trường hợp. Tuy nhiên:
- Không phải workload nào cũng nhanh hơn.
- Chính sách/heuristics có thể khác nhau giữa mode.
- Mode không thay thế việc tính heap headroom, GC CPU, allocation rate và SLO.
- Cần JDK/build hỗ trợ đúng mode.

JDK 25 hoàn thiện generational Shenandoah theo **JEP 521**. Trong các bản JDK 25/27 có option được ghi ở manual:

~~~bash
# Đổi mode có chủ đích trên runtime có hỗ trợ:
java -XX:+UseShenandoahGC \
     -XX:ShenandoahGCMode=generational \
     -Xms256m -Xmx1g -Xlog:gc=info -version
~~~

**Không gán cờ này cho JDK 17/21 một cách mù quáng**; một số vendor có thể backport nhưng phải có tài liệu chính thức cho build đó.

### 11.2. Đừng suy từ tên option rằng mode đã kích hoạt

Với một binary đã compile Shenandoah nhưng không có generational code hoặc không hỗ trợ mode trên kiến trúc:
- JVM có thể từ chối flag.
- Có thể thất bại khi khởi tạo GC.
- Có thể có cách xử lý khác tùy vendor build.

Vì vậy cần xem **exit code + GC initialization logs + JVM flags**. Nếu làm test có ý nghĩa về performance, dùng workload thật và đối chiếu GC mode thay vì chỉ xét startup.

### 11.3. Đừng dùng hướng dẫn lịch sử không còn phù hợp

- Shenandoah production **không** cần `UnlockExperimentalVMOptions` từ JDK 15.
- Generational Shenandoah trên **JDK 25** đã trở thành feature final, không cần bật option experimental cho mode này.
- Những tài liệu JDK 12–14 nói Shenandoah experimental chỉ phản ánh thời điểm cũ.
- Một bài blog nói JDK 24 generational Shenandoah là experimental **không có nghĩa** JDK 25/26 cũng vậy.
- Đừng khẳng định Shenandoah generational là **default của JDK 25**; cần mode flag khi muốn đảm bảo rõ ràng.

## 12. Điều kiện build/VM và các tình huống đặc biệt

### 12.1. Build từ mã nguồn OpenJDK

Việc Shenandoah có trong source tree không tự đảm bảo nó nằm trong output VM. Các build cấu hình tính năng VM ở thời điểm compile; một image có thể được build với các thành phần GC bị vô hiệu hóa. Port có thể cần native code theo OS/CPU.

Nếu tự build:
- Xem hướng dẫn xây JDK của **đúng branch**.
- Kiểm danh sách VM features khi configure/build, không copy cờ build từ phiên bản khác.
- Chạy JVM smoke test trên **đúng binary build ra**, không chỉ tìm source directory `gc/shenandoah`.
- Kiểm JDK tests liên quan collector/architecture trước khi đưa vào production.
- Nếu có patchset/vendor port, document rõ build provenance, commit hash, architecture, compilation flags và CI coverage.

### 12.2. `jlink` custom runtime images

`jlink` tạo runtime image từ các module JDK. Shenandoah thuộc phần **native HotSpot VM** chứ không phải một module Java tên `jdk.shenandoah` mà bạn thêm bằng `--add-modules`. Một jlink image có thể dùng cùng VM features của JDK nguồn, nhưng phụ thuộc image đã chứa launcher/VM runtime phù hợp.

Với ví dụ `ManagementFactory.getGarbageCollectorMXBeans()`, custom runtime cần có module **`java.management`** (hoặc dependency kéo theo), còn app sử dụng JFR cần module **`jdk.jfr`** khi có sử dụng.

**Nên:** Chạy smoke test trên `/path/to/runtime-image/bin/java`; không kiểm build JDK trước khi jlink rồi mặc định artifact sau packaging chắc chắn giống hệt.

### 12.3. Container multi-architecture

Một tag image có thể là **manifest list** chứa binaries riêng cho `linux/amd64` và `linux/arm64`. CI có thể chạy x86_64 trong khi production là ARM64. Thực hành:
- Pin tag/digest được kiểm soát, xem image architecture thực tế.
- Thực hiện smoke test trong từng image architecture (native hoặc CI runner tương thích).
- Đảm bảo Java binary bên trong image đúng arch và kernel ABI.
- Không coi `docker run --platform linux/arm64` dưới emulation là benchmark hiệu năng ARM64 đại diện cho host native.
- Đối chiếu CPU quota, memory limit và GC worker ergonomics theo runtime cuối cùng.

**Rủi ro:** Chạy trên emulation có thể thành công về tính năng nhưng sai về throughput/latency. Phân tách **capability smoke test** và **benchmark performance**.

### 12.4. Android, Native Image và JVM khác

Ứng dụng viết bằng Java không đồng nghĩa sử dụng HotSpot:
- Android runtime có garbage collector riêng; đừng áp dụng HotSpot Shenandoah flags.
- GraalVM Native Image sinh binary native với runtime/GC riêng; `java -XX:+UseShenandoahGC` không phải lựa chọn GC cho native executable.
- OpenJ9 có GC policies riêng.

Luôn xác định runtime implementation trước khi quyết định option hoặc kỳ vọng sự kiện `gc,shenandoah` trong log.

## 13. Triển khai an toàn trong CI/CD và vận hành

### 13.1. Gate khả năng hỗ trợ ở deployment

Trước khi chạy production, nên có bước kiểm tra rõ:
1. Resolve **absolute `java` executable path** mà service sẽ dùng.
2. In `java -version`, VM vendor, `os.name`, `os.arch`.
3. Chạy `java -XX:+UseShenandoahGC -Xlog:gc=info -version` **trên binary đó**.
4. Kiểm **exit 0** và log/beans xác nhận GC Shenandoah.
5. Nếu yêu cầu generational, kiểm thêm đúng `ShenandoahGCMode=generational` trên JDK25+ có hỗ trợ.
6. Khởi động workload smoke test (allocation pressure vừa phải) để đảm bảo GC thực sự hoạt động.
7. Ghi lại image digest / binary hash / JDK vendor+version / OS+arch.
8. Nếu support bắt buộc mà fail, **chặn deployment**, không âm thầm bỏ GC flag rồi chấp nhận collector khác.
9. Theo dõi GC logs/JFR và request SLO trong staging/canary trước rollout.
10. Giữ rollback và metric để truy nguyên khi nâng JDK/vendor/OS.

**Điểm về bảo mật:** Không lấy flag hỗ trợ từ input người dùng và không cho phép bật `IgnoreUnrecognizedVMOptions` làm bước “fallback” mặc định; nó có thể làm mất bằng chứng collector đã được chọn.

### 13.2. CI matrix nên gồm những gì?

Ví dụ bảng kiểm tối thiểu:

| Matrix dimension | Các trường cần có |
| --- | --- |
| JDK distribution | Temurin, Zulu, Corretto, Red Hat, Liberica, v.v. đúng nhu cầu |
| Version | JDK 17 LTS / 21 LTS / 25 LTS và bản patch hiện đang sử dụng |
| VM | HotSpot hay OpenJ9; Native Image test riêng |
| OS | Linux, Windows, macOS **nếu sản phẩm thực sự hỗ trợ** |
| CPU arch | x86_64/amd64, AArch64/arm64 và arch khác khi triển khai |
| Artifact | JDK/JRE, container image digest, jlink custom runtime |
| Collector | `-XX:+UseShenandoahGC`, G1 baseline, generational mode nếu đủ điều kiện |
| Capability test | Startup, selected collector, workload smoke test |
| Performance test | p99/p99.9, CPU cost, throughput, heap/RSS, GC pauses/stalls |
| Support policy | Vendor lifecycle, security patches và nơi báo lỗi |

Không cần thử **mọi tổ hợp của thế giới** nếu sản phẩm không chạy ở đó; hãy thử **mọi tổ hợp mà bạn thật sự triển khai** và cập nhật matrix khi nâng bản JDK/image.

### 13.3. Khi không có Shenandoah, nên làm gì?

Thứ tự ra quyết định:
1. **Kiểm đúng binary và architecture trước**: có thể chỉ do PATH hoặc JDK vendor khác.
2. **Kiểm vendor/build hỗ trợ**: có thể chọn một bản HotSpot phân phối có Shenandoah với security updates và SLA phù hợp.
3. **Kiểm nhu cầu thực**: nếu GC pause SLO đã đạt với G1/ZGC, không nhất thiết phải đổi JDK chỉ vì muốn Shenandoah.
4. **Benchmark lựa chọn thay thế**: G1 là lựa chọn phổ biến; ZGC cũng là low-latency collector trên các JDK HotSpot hỗ trợ, có trade-off riêng.
5. **Không tự hạ cấp**: nếu hệ thống bắt buộc dùng Shenandoah theo profile đã test, phải fail deployment khi thiếu collector.
6. **Ghi nợ kỹ thuật có kiểm soát** nếu một OS/arch chưa có Shenandoah, thay vì coi mọi platform tương đương.

Bản chất “supported” là **một thuộc tính của release artifact + môi trường**, không phải một thuộc tính cố định của chương trình Java.

## 14. Lỗi thường gặp và cách sửa

| Sai lầm | Vì sao sai? | Cách làm đúng |
| --- | --- | --- |
| “Java 15 có Shenandoah, nên mọi Java 15+ đều có” | Vendor/build/VM/OS/arch khác nhau | Test đúng binary, xem logs và policy |
| “Có trong OpenJDK source thì có ở Oracle JDK” | Oracle-provided binaries có thể omit GC theo wiki dự án | Kiểm artifact thực và vendor documentation |
| “Temurin/Zulu hỗ trợ trên Linux nên chắc hỗ trợ mọi Mac/Windows/ARM build” | Ma trận packaging và ports thay đổi | Kiểm từng OS/arch/release |
| “JDK 25 generational Shenandoah là default” | JEP 521 hoàn thiện mode không tự làm default | Dùng mode flag tường minh và xác nhận logs |
| Dùng `UnlockExperimentalVMOptions` cho Shenandoah production | Hướng dẫn cũ thời experimental | JDK15+ không cần để bật collector thường |
| Dùng `ShenandoahGCMode=generational` trên JDK17 | Mode hiện đại chưa chắc có | Chỉ dùng JDK25+ hỗ trợ hoặc vendor backport có tài liệu |
| “Linux/amd64 và Linux/arm64 image cùng tag nên như nhau” | Image có binaries native riêng | Kiểm digest/arch và chạy smoke test cho từng |
| Tin `System.getProperty("os.arch")` đủ | Chỉ nhận dạng arch, không chứng minh GC đã build | Khởi động JVM với flag và kiểm GC thật |
| “JDK có thể chạy s390x nên Shenandoah cũng chạy” | OS/JVM support khác GC architecture port | Đọc wiki/port và smoke test |
| Trích bảng 32-bit cũ cho JDK25 | JEP503 loại 32-bit x86 port của JDK25 | Theo JDK release và vendor lifecycle |
| Dùng VM OpenJ9 nhưng truyền HotSpot GC flag | VM implementations không đồng nhất | Dùng đúng GC policies của JVM engine |
| `-XX:+IgnoreUnrecognizedVMOptions` để không fail | Che mất việc GC không có/flag không hiệu lực | Fail closed và cảnh báo |
| Dựa vào GC log của máy dev cho prod | Binary/container/CPU khác | Kiểm chính image và service command production |
| Lỗi heap thiếu memory bị báo “GC không hỗ trợ” | Hai nguyên nhân khác nhau | Phân loại startup error và memory budget |
| Có `Using Shenandoah` rồi khẳng định latency tốt | Startup support không là performance proof | Benchmark p99/throughput/CPU/RSS |
| Tưởng `jlink --add-modules` tự cài thêm GC | GC nằm trong HotSpot native runtime | Dùng VM build có GC, test image tạo ra |
| Chỉ chọn vendor theo bảng public không kiểm patch | Vendor hỗ trợ và QA policy có thể đổi | Pin patch, đọc release notes/SLA |
| Tự fallback sang collector khác khi thiếu Shenandoah | Vi phạm SLO/cấu hình production đã kiểm thử | Chỉ fallback khi policy cho phép và đã benchmark |

## 15. Bài tập có đáp án

**Câu 1.** JDK 21 trên Linux hiển thị `OpenJDK 64-Bit Server VM`. Có thể kết luận Shenandoah hoạt động không?

**Đáp án:** Không. Cần biết vendor/build/architecture và thử `java -XX:+UseShenandoahGC -Xlog:gc=info -version`; kiểm exit code và GC thật.

**Câu 2.** Hai máy dùng cùng source code và Java 25 nhưng một máy chạy Shenandoah, máy khác báo `Unrecognized VM option`. Vì sao?

**Đáp án:** Hai binaries/VM engines có thể khác nhau về build features. Kiểm absolute `java` path, vendor, VM implementation, OS/arch, artifact và error output.

**Câu 3.** Một doanh nghiệp dùng Oracle-provided JDK nhưng một bài hướng dẫn chung nói Java 25 có `-XX:+UseShenandoahGC`. Có nên giả định chạy được không?

**Đáp án:** Không. Dự án Shenandoah nêu Oracle builds không đóng gói collector; docs chung mô tả khả năng cú pháp HotSpot. Chỉ runtime binary test và vendor policy có thể kết luận.

**Câu 4.** JDK 25 có generational Shenandoah. Nếu chỉ bật `-XX:+UseShenandoahGC` thì chắc chắn đang dùng generational mode chứ?

**Đáp án:** Không. Theo manual, mode mặc định vẫn có thể là SATB. Muốn dùng generational, bật `-XX:ShenandoahGCMode=generational` trên build hỗ trợ và kiểm logs.

**Câu 5.** Ứng dụng chạy trong Linux container arm64, còn CI smoke test được chạy trên Linux amd64. Kết quả CI có chứng minh Shenandoah được hỗ trợ ở production không?

**Đáp án:** Không. Hai image/binaries/CPU architecture khác nhau; phải kiểm trên image và architecture thực tế.

**Câu 6.** `os.arch=aarch64` có chứng minh JVM chứa implementation Shenandoah không?

**Đáp án:** Không. Nó chỉ nói về architecture mà JVM báo. Cần test collector startup và selected GC.

**Câu 7.** Vì sao JDK 25 x86 32-bit không được liệt kê như một mục tiêu mainstream hiện đại?

**Đáp án:** JEP 503 loại port x86 32-bit khỏi mainline JDK 25. Không dùng bảng port đã cũ làm bảo đảm.

**Câu 8.** IBM Semeru dùng OpenJ9, ứng dụng muốn low-pause GC. Có thể dùng `UseShenandoahGC` như với HotSpot không?

**Đáp án:** Không mặc định. OpenJ9 có bộ GC policies riêng; chọn theo docs và benchmark của OpenJ9.

**Câu 9.** Smoke test JDK vendor báo `Using Shenandoah`, nhưng p99 của service kém hơn G1. Có phải runtime không hỗ trợ Shenandoah?

**Đáp án:** Không. Tính năng đang có thể hoạt động, còn SLO phụ thuộc allocation/live set, heap headroom, CPU quota, barriers, GC configuration và workload. Cần benchmark tách khỏi capability test.

**Câu 10.** Vì sao cần chọn absolute `java` path cho production?

**Đáp án:** PATH/JAVA_HOME/IDE/service wrapper/container có thể chọn JDK khác. Testing binary khác không chứng minh kết quả của service.

**Câu 11.** Một vendor công bố JDK cho Windows ARM64. Có thể suy Shenandoah trên Windows ARM64 được hỗ trợ thương mại không?

**Đáp án:** Không. Cần xác minh collector được build và vendor hỗ trợ chính tổ hợp Windows ARM64/JDK release/GC.

**Câu 12.** Nếu bắt buộc dùng generational Shenandoah nhưng JDK 21 không có mode, có nên thêm `-XX:+IgnoreUnrecognizedVMOptions` rồi triển khai?

**Đáp án:** Không. Flag có thể bị bỏ qua làm runtime chạy collector/mode khác yêu cầu. Chọn JDK/build có mode hoặc đổi yêu cầu theo quy trình đánh giá; không che lỗi cấu hình.

**Câu 13.** OpenJDK Shenandoah wiki ghi “x86_64 primary target” có nghĩa chỉ Linux x64 mới dùng được?

**Đáp án:** Không. Kiến trúc và OS là các chiều riêng; có Windows/macOS ports, nhưng từng artifact cần hỗ trợ đúng tổ hợp.

**Câu 14.** `ShenandoahSupportProbe` in `SUPPORTED`. Có phải GC đã được đánh giá cho heap vài trăm GB và p99 2 ms chưa?

**Đáp án:** Chưa. Probe chỉ xác nhận tính năng chạy được trong child JVM. Cần workload thực tế và kiểm performance/reliability theo SLO.

## 16. Checklist quyết định trước production

- [ ] Ghi lại JDK **vendor, version, update/build number**, JVM engine, license/support lifecycle.
- [ ] Ghi đúng OS/kernel và CPU architecture của process, không chỉ host.
- [ ] Chạy smoke test trên **exact java executable** của app/container/runtime image.
- [ ] `-XX:+UseShenandoahGC` khởi động thành công với exit code `0`.
- [ ] GC initialization log hoặc MXBeans/JFR xác nhận collector được chọn là Shenandoah.
- [ ] Nếu cần **generational**, phiên bản/mode đã có và được xác nhận đúng.
- [ ] Không dùng flags legacy/experimental khi JDK hiện đại không yêu cầu.
- [ ] Không dùng `IgnoreUnrecognizedVMOptions` làm cách “ép” tính tương thích.
- [ ] Native OS/CPU port tương ứng được vendor/support policy chấp nhận.
- [ ] Workload smoke test có GC activity thật, không chỉ `java -version`.
- [ ] Đã kiểm CPU quota, heap headroom, memory limit và pause/throughput behavior.
- [ ] Benchmark p95/p99/p99.9 latency với cùng workload để chọn GC, không chỉ dựa vào “supported”.
- [ ] CI/CD kiểm từng OS/arch/JDK artifact được deploy, kể cả multiarch containers.
- [ ] Có rollback/fallback **được phê duyệt và đã benchmark**, không tự im lặng đổi collector.

## 17. Tóm tắt

- **Có Shenandoah hay không là thuộc tính của JVM binary và môi trường**, không chỉ Java source version.
- **Java 15 / JEP 379:** Shenandoah trở thành production trong OpenJDK HotSpot; nhưng bản Java 15 không còn là khuyến nghị LTS hiện nay.
- **HotSpot vendor khác nhau:** Temurin, Corretto, Zulu, Liberica, SapMachine, Red Hat thường có các builds Shenandoah; Oracle-provided builds được wiki dự án ghi là không đóng gói; **luôn kiểm artifact thật**.
- **OS/CPU:** Linux/Windows/macOS và x86_64/AArch64/PPC64/RISC-V có mức port khác nhau. **Đừng suy từ Java chạy được trên arch đó rằng Shenandoah cũng có.**
- **JDK 25 / JEP 521:** Generational Shenandoah hoàn thiện; yêu cầu mode rõ ràng, không giả định mặc định. **JEP 503** loại x86 32-bit port khỏi mainstream.
- **Kiểm định:** `java -XX:+UseShenandoahGC -Xlog:gc=info -version` + exit code + `Using Shenandoah`/GC beans + workload smoke test trong environment thật.
- **Capability không phải performance:** Collector hoạt động là bước một; SLO phải được benchmark riêng.

## 18. Tài liệu tham khảo hiện hành

- [OpenJDK Shenandoah Wiki — Support Overview, OS/Hardware/JDK support và vendor build availability](https://wiki.openjdk.org/display/shenandoah/Main)
- [OpenJDK JEP 379 — Shenandoah: A Low-Pause-Time Garbage Collector (Production, JDK 15)](https://openjdk.org/jeps/379)
- [OpenJDK JEP 521 — Generational Shenandoah (JDK 25)](https://openjdk.org/jeps/521)
- [OpenJDK JEP 503 — Remove the 32-bit x86 Port (JDK 25)](https://openjdk.org/jeps/503)
- [OpenJDK — HotSpot/VM Shenandoah implementation và architecture guards](https://github.com/openjdk/shenandoah/blob/master/src/hotspot/share/gc/shenandoah/shenandoahArguments.cpp)
- [Oracle Java SE 25 — java Command-Line Options: `UseShenandoahGC` và `ShenandoahGCMode`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html)
- [Oracle Java SE 25 — `GarbageCollectorMXBean`](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html)
- [BellSoft Liberica — JVM Memory Configuration, Shenandoah section](https://docs.bell-sw.com/liberica-jdk-documentation/)
- [Eclipse Temurin — Supported platforms và release availability](https://adoptium.net/temurin/releases/)
- [Microsoft Build of OpenJDK — Supported versions và OS/CPU distributions](https://learn.microsoft.com/en-us/java/openjdk/download)
- [Eclipse OpenJ9 — GC policies khác HotSpot Shenandoah](https://eclipse.dev/openj9/docs/gc/)
