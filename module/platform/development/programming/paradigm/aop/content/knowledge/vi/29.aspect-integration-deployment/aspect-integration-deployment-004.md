# Quản lý phiên bản công cụ, định dạng mã và thư viện phụ thuộc trong AOP

Aspect-Oriented Programming (AOP) cho phép đưa các mối quan tâm xuyên suốt như đo thời gian, kiểm toán hay quan sát vào nhiều điểm thực thi (join point). Khi tích hợp vào một hệ thống Java, aspect có thể được đưa vào bytecode lúc biên dịch, sau biên dịch, trong quá trình nạp lớp hoặc được thực hiện qua cơ chế chặn lời gọi tại runtime. Mỗi cách triển khai tạo ra yêu cầu tương thích riêng giữa **mã nguồn, compiler, bộ dệt aspect (weaver), định dạng class/JAR, JVM và các thư viện phụ thuộc**.

Một bản nâng cấp compiler hoặc weaver có thể khiến bản build lỗi; một bản nâng cấp JDK có thể tạo bytecode runtime cũ không đọc được; một thư viện instrumentation có thể đổi cấu trúc lớp và ảnh hưởng tới class loader. Vì vậy, quản lý phiên bản AOP không chỉ là chọn phiên bản thư viện mới nhất. Cần xác định một **tập phiên bản đã kiểm chứng**, lưu rõ cấu hình tạo artifact, kiểm tra sản phẩm sau weaving và có cách quay lui khi triển khai.

Bài này trình bày kiến thức AOP độc lập với framework ứng dụng cụ thể. Các tên như AspectJ, ASM hoặc Byte Buddy được dùng như **ví dụ về công cụ trong hệ sinh thái Java**, không đồng nhất một công cụ với toàn bộ khái niệm AOP.

## 1. Những thành phần cần quản lý phiên bản

| Thành phần | Vai trò khi sử dụng AOP | Điều cần kiểm tra |
| --- | --- | --- |
| Mã nghiệp vụ | Định nghĩa lớp, phương thức, giao diện và hành vi gốc | Phiên bản nguồn, API/ABI, kiểu join point cần áp dụng |
| Định nghĩa aspect | Pointcut, advice, kiểu dữ liệu và quy tắc ưu tiên | Cú pháp có được compiler/weaver hiện tại hiểu không; thứ tự advice |
| Trình biên dịch Java | Sinh class file từ Java source | Ngôn ngữ được hỗ trợ, chế độ target/release, metadata debug |
| Compiler/weaver AOP | Kết hợp logic aspect vào điểm thực thi | Phiên bản Java/bytecode được hỗ trợ, chế độ weaving, thay đổi hành vi |
| Runtime AOP hoặc agent | Chặn lời gọi hoặc biến đổi lớp khi tải/chạy | Khả năng tương thích JVM, class loader, module, tham số khởi động |
| Thư viện bytecode | Đọc, phân tích, viết class file | Có hiểu class-file version và cấu trúc bytecode của JDK mục tiêu không |
| Runtime Java | Xác minh và chạy bytecode, quản lý lớp | Class-file version, module access, verifier, các hạn chế instrumentation |
| Thư viện nghiệp vụ | Kiểu dữ liệu, annotations, API mà advice tham chiếu | Binary compatibility, thay đổi tên lớp/phương thức, chuyển tiếp phụ thuộc |
| Build tool và plugin | Biên dịch, weaving, test, đóng gói và xuất bản artifact | Phiên bản wrapper, plugin API, task order, khóa dependency |
| Hạ tầng đóng gói/phát hành | Tạo JAR, agent JAR, container và file cấu hình | Đúng artifact, manifest, classpath/module path, tính toàn vẹn đầu ra |

Một bản ứng dụng hoạt động khi compile chưa chắc đã hoạt động lúc nạp lớp. Quy trình quản lý phiên bản cần phân biệt ít nhất bốn mức:

1. **Tương thích nguồn:** mã Java/aspect được công cụ hiện tại phân tích và biên dịch thành công.
2. **Tương thích binary:** class sau biên dịch có thể liên kết với các class/phụ thuộc khác, không vấp lỗi như NoSuchMethodError hay NoClassDefFoundError.
3. **Tương thích runtime:** JVM và công cụ áp dụng aspect có thể nạp, xác minh và thực thi class ở đúng môi trường triển khai.
4. **Tương thích hành vi:** pointcut vẫn bắt trúng tập join point mong muốn; advice giữ đúng thứ tự, kết quả, ngoại lệ, thread safety và side effect sau nâng cấp.

Bốn mức này phải được xác minh độc lập. “Build xanh” chỉ chứng minh một phần của hợp đồng tương thích.

## 2. Chọn và ghi lại cơ chế triển khai aspect

Trước khi bàn đến phiên bản, phải xác định **cơ chế áp dụng aspect**. Tên công cụ và cấu hình không thể hoán đổi tùy ý.

| Cơ chế | Thời điểm áp dụng | Thành phần có phiên bản cần kiểm soát | Rủi ro điển hình |
| --- | --- | --- | --- |
| Compile-time weaving | Khi biên dịch source thành class | Aspect compiler, Java source/target, phụ thuộc compile | Compiler chưa hỗ trợ cú pháp hoặc class-file mới |
| Post-compile/binary weaving | Sau biên dịch, trước khi đóng gói hoặc triển khai | Weaver, class đầu vào, classpath, bytecode writer | Dệt trùng, ghi đè metadata, thay đổi class không đúng |
| Load-time weaving | Khi class loader nạp class | Weaving agent/runtime, JVM, class loader, file cấu hình | Bỏ lỡ lớp đã load, xung đột transformer, module access |
| Runtime proxy/interception | Khi lời gọi đi qua đối tượng chặn | Proxy/interceptor library, quy tắc tạo proxy, API của đối tượng | Lời gọi nội bộ không đi qua proxy, hạn chế kiểu phương thức/lớp |

**Không suy ra khả năng tương thích từ tên chế độ.** Cùng một định nghĩa advice nhưng hai cơ chế có thể nhận diện tập join point khác nhau. Ví dụ JDK dynamic proxy chặn lời gọi đi qua giao diện được proxy hiện thực; nó không tự động áp dụng tới mọi constructor, field access hoặc lời gọi trực tiếp nội bộ của đối tượng đích. Các cơ chế weaving bytecode có thể hỗ trợ tập join point khác tùy ngôn ngữ pointcut và hiện thực.

Quy ước rõ **một đơn vị chịu trách nhiệm weaving** cho mỗi artifact ở mỗi giai đoạn. Nếu vừa weave sau biên dịch vừa weave tiếp ở runtime mà không kiểm soát, một join point có thể nhận advice hai lần hoặc bị xung đột biến đổi. Không được giả định thao tác weaving luôn idempotent; phải kiểm tra khả năng reweave theo tài liệu của đúng phiên bản công cụ.

Trong hồ sơ phát hành, nên ghi: cơ chế weaving, task/build stage dệt mã, tập classes/jars đầu vào, điểm áp dụng agent, phiên bản weaver, file cấu hình, tập pointcut và thứ tự transformer nếu có nhiều agent.

## 3. Quản lý phiên bản Java và định dạng bytecode

### 3.1 Source level, target và runtime là ba thứ khác nhau

Ví dụ compiler chạy trên JDK 21 vẫn có thể được cấu hình sinh bytecode cho Java 17. Với Java, tùy chọn **javac --release 17** vừa ràng buộc cú pháp ngôn ngữ, phiên bản bytecode, vừa giới hạn API nền tảng theo Java 17. Chỉ thay đổi target mà không kiểm soát API có thể gây lỗi khi chạy trên JVM cũ hơn.

Trong class file, bốn byte đầu là magic **CAFEBABE**, tiếp theo là minor và major version. Một vài mốc thường dùng:

| Java | Class-file major |
| --- | ---: |
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |

JVM cũ hơn mức class-file đã phát hành thường từ chối nạp với UnsupportedClassVersionError. Nhưng JVM hỗ trợ major version **không bảo đảm** weaver hoặc thư viện đọc bytecode cũng hỗ trợ; công cụ đó có parser, quy tắc xác minh và bộ ghi class riêng.

Mã sau weaving có thể khác mã đầu vào về cấu trúc phương thức, constant pool, stack map frames, exception table, generic signature và annotations. Một công cụ quá cũ có thể từ chối classfile mới hoặc ghi lại dữ liệu không hợp lệ. Vì vậy, cần kiểm tra **class-file major của cả lớp đầu vào và đầu ra** và thực sự nạp/chạy bytecode đầu ra trên JVM mục tiêu.

### 3.2 Preview features, multi-release JAR và metadata

Class file biên dịch bằng preview feature có yêu cầu runtime đặc biệt; không nên phát hành nhầm preview bytecode như một artifact tương thích Java thông thường. Nếu buộc dùng preview, cần ghi rõ phiên bản JDK và flags trong hợp đồng triển khai.

JAR đa phiên bản (multi-release JAR) có thể chứa các bản class khác nhau dưới META-INF/versions/. JVM chọn nội dung tùy phiên bản runtime. Một công cụ dệt mã phải xác định nó xử lý base classes, các phiên bản phụ, hay cả hai. Việc chỉ weave base classes có thể khiến aspect xuất hiện trên JDK này nhưng mất trên JDK khác.

Khi weave, cần bảo toàn hoặc tái tạo metadata hợp lệ: annotations, signatures, parameter names khi cần, exception attributes, stack map frames, nest/module attributes và thông tin line number để debug. Không được khẳng định metadata luôn giữ nguyên chỉ vì API public trông giống nhau.

### 3.3 Định dạng mã nguồn aspect không phải chuẩn chung của mọi công cụ

AOP mô tả các khái niệm join point, pointcut và advice. **Cú pháp cụ thể** là hợp đồng riêng của một công cụ/ngôn ngữ mở rộng. Một công cụ có thể dùng file aspect độc lập, một công cụ dùng annotations trên class Java, một công cụ dùng cấu hình bên ngoài, một công cụ khác dùng interceptor API. Các cú pháp không nhất thiết tương thích chéo.

Chẳng hạn, trong hệ sinh thái AspectJ có kiểu source aspect dưới dạng file .aj và các pointcut expression của chính ngôn ngữ đó. Việc đổi trình biên dịch sang javac thuần mà vẫn giữ source .aj không làm javac tự hiểu cú pháp aspect. Với định nghĩa aspect bằng Java annotations, compile thành công cũng chưa chứng minh aspect sẽ được dệt vào join point: còn cần đúng weaver và cấu hình ở build hoặc runtime.

Vì thế, khi nâng cấp phải ghi cả **phiên bản cú pháp/DSL, cách định nghĩa aspect, cách kích hoạt và cấu hình loader**. Không chỉ ghi “AOP enabled”.

## 4. Quy tắc quản lý phiên bản công cụ

Một hệ thống AOP nên dùng một **bộ phiên bản thử nghiệm chung (toolchain contract)**. Phần sau là mẫu thông tin cần quản lý, không phải cú pháp cấu hình bắt buộc của mọi công cụ:

```yaml
toolchain:
  language: Java
  javaRelease: 17
  targetRuntime: Java 17+
  build: Gradle wrapper pinned in repository
aop:
  mode: compile-time weaving
  sourceRepresentation: tool-specific aspect source
  aspects:
    - timing
    - auditing
  pointcutContract:
    - method executions in selected application packages
verification:
  - compile and weave from clean checkout
  - inspect emitted class-file major version
  - run integration tests against woven classes
  - verify advice invocation count and order
  - compare runtime behavior with controlled baseline
```

Các trường trên phải được hoàn thiện bằng **tọa độ artifact và phiên bản cụ thể đã kiểm thử** trong lockfile/bản kê phát hành thực tế; bản mẫu chỉ diễn đạt cấu trúc hợp đồng. Không thể suy ra một phiên bản weaver hỗ trợ Java 17 hoặc Java 21 chỉ vì tên artifact tồn tại trong kho phụ thuộc. Luôn dùng compatibility matrix, release notes và thử nghiệm của nhà cung cấp đúng cho phiên bản được chọn.

Để giữ build tái hiện được:

1. **Khóa phiên bản build tool:** commit Gradle wrapper hoặc Maven wrapper, cấu hình plugin và repository, tránh phụ thuộc môi trường máy của lập trình viên.
2. **Khai báo cụ thể compiler/weaver và runtime AOP:** ghi phiên bản trực tiếp, đừng tự động lấy bản mới nhất khi CI chạy.
3. **Kiểm soát transitive dependencies:** sử dụng dependency locking/verification hoặc lockfile tương ứng, để một thư viện bên dưới không tự đổi major version ngoài ý muốn.
4. **Lưu phiên bản JDK dùng để build và chạy:** có thể dùng Java toolchain, image digest/container hoặc mô tả môi trường CI; kiểm tra artifact trên runtime thấp nhất được hỗ trợ.
5. **Lưu checksum và nguồn tải:** dependency verification, kho artifact đã kiểm duyệt và quyền truy cập phù hợp giúp bảo vệ reproducibility và chuỗi cung ứng.
6. **Phân loại nâng cấp:** thay đổi patch/minor vẫn có thể ảnh hưởng weaver và bytecode; mọi nâng cấp công cụ biến đổi lớp cần chạy lại ma trận kiểm tra tương thích.
7. **Không ghi bản phát hành bằng nhãn nổi:** các cú pháp phụ thuộc kiểu latest, dấu cộng chọn phiên bản động hoặc khoảng version không được kiểm soát làm cùng một commit có thể cho artifact khác nhau.

**Khóa phiên bản không đồng nghĩa đóng băng vĩnh viễn.** Cần có lịch rà soát CVE, JDK end-of-support, compatibility matrix, ghi chép quyết định nâng cấp và kiểm thử theo từng bước nhỏ. Nên thử nâng cấp JDK và weaver ở hai nhánh/thí nghiệm riêng trước, sau đó mới kiểm tra tổ hợp.

## 5. Quản lý thư viện phụ thuộc và ranh giới classpath

### 5.1 Nhận diện đúng loại phụ thuộc

- **Build-only:** trình biên dịch aspect, bộ weaving, plugin kiểm tra bytecode; chỉ cần trong giai đoạn build nếu sản phẩm là class đã dệt hoàn chỉnh.
- **Compile-time:** API annotation, kiểu dữ liệu và class mà source aspect hoặc nghiệp vụ tham chiếu khi biên dịch.
- **Runtime:** runtime library cho các lời gọi do code đã weave sinh ra, interceptor library hoặc weaver chạy lúc tải lớp; không tự động coi tất cả là build-only.
- **Test-only:** thư viện kiểm thử, agent kiểm tra instrumentation, profiler hoặc công cụ giả lập tải; thông thường không đưa vào runtime production.

Việc đặt nhầm dependency có thể tạo hai kiểu sự cố đối nghịch. Nếu phụ thuộc **cần ở runtime** nhưng chỉ có khi compile, ứng dụng có thể nổ NoClassDefFoundError hoặc NoSuchMethodError sau khi triển khai. Nếu thư viện compiler/weaver không cần thiết lại đóng gói vào runtime, artifact lớn hơn, tăng khả năng xung đột và bề mặt cập nhật bảo mật.

Đối với Java agent, xem cả manifest và quy tắc JVM: một Java agent tải bằng tùy chọn **-javaagent** cần JAR có manifest khai báo Premain-Class và class chứa phương thức premain hợp lệ. Một số agent hỗ trợ attach sau khởi động bằng Agent-Class/agentmain, nhưng quyền attach và hành vi instrument phụ thuộc chính sách và phiên bản runtime. Không tự thay cách nạp agent khi chưa có kiểm thử tương đương.

### 5.2 Phân tích graph, không chỉ dependency trực tiếp

Một lỗi thường gặp: ứng dụng sử dụng weaver A, thư viện đo đạc dùng ASM/Byte Buddy phiên bản B và một agent khác mang thư viện bytecode phiên bản C. Nếu các thành phần cùng chia sẻ class loader, các bản không tương thích có thể gây linkage error. Cũng có trường hợp mỗi agent cách ly classpath riêng, nhưng vẫn xung đột do cùng biến đổi một lớp.

Đọc dependency graph ở **compile, runtime và test scopes**; lưu ý khác biệt giữa compileClasspath và runtimeClasspath, các excludes, shading/relocation và quy tắc resolution. Một kết quả dependency tree “không có hai version trùng tên” vẫn chưa chứng minh tương thích nếu hai agent tác động cùng bytecode. Ngược lại, hai thư viện có bản sao được relocation/cách ly có thể cùng tồn tại nếu được kiểm chứng.

Không tùy tiện ép toàn bộ graph lên một bản ASM/Byte Buddy mới mà chưa kiểm tra các công cụ phụ thuộc có hỗ trợ API đó. Việc ép version có thể giải quyết một xung đột tên nhưng gây lỗi bytecode parser hoặc method linkage ở chỗ khác.

### 5.3 Shading, fat JAR, module path và class loader

Khi đóng gói executable JAR hoặc shaded JAR, kiểm tra:

- **Class trùng tên:** bản nào thắng khi nhiều JAR chứa cùng FQCN? Nếu sử dụng relocation, tài nguyên và mã phản chiếu tham chiếu tên lớp có còn đúng không?
- **ServiceLoader và metadata:** các file META-INF/services, module descriptors và resources cần được merge/copy đúng; mất chúng có thể làm weaver/extension không được tìm thấy.
- **Manifest:** giữ thông tin Main-Class, Premain-Class, Multi-Release nếu cần, nhưng chỉ giữ các trường thực sự phù hợp sau đóng gói.
- **Chữ ký JAR:** sửa bytecode trong JAR đã ký làm chữ ký cũ không còn hợp lệ. Nếu cần chữ ký hợp lệ, ký lại artifact **sau** bước biến đổi, với quy trình phát hành phù hợp.
- **Class loader:** plugin/container có loader tách biệt; cùng một tên class nhưng hai loader tạo hai kiểu khác nhau. Advice có thể gặp ClassCastException nếu truyền đối tượng qua ranh giới loader sai.
- **JPMS:** module exports/opens và quyền truy cập reflection/instrumentation có thể giới hạn tác vụ. Chỉ thêm opens/exports có phạm vi cần thiết sau khi hiểu lớp và module nào cần được truy cập.
- **Native image/AOT:** runtime không có cùng hành vi class loading/instrumentation như JVM thông thường; cần thiết kế riêng theo khả năng của nền tảng và công cụ. Không mặc định một agent load-time sẽ hoạt động y hệt.

Một bản build chứa đủ JAR nhưng thiếu file cấu hình pointcut vẫn có thể **chạy mà không áp dụng advice**, nguy hiểm vì không ném lỗi rõ ràng. Bước kiểm tra phát hành nên khẳng định số join point và advice thật sự chạy.

## 6. Bảo vệ tính ổn định của định nghĩa aspect và định dạng mã

Khi nhiều nhóm cùng viết aspect, đặt quy ước nhằm giảm thay đổi âm thầm trong quá trình nâng cấp:

1. **Quy ước tên:** tên aspect, advice và pointcut nêu rõ mục đích; tránh biểu thức quá rộng áp dụng lên toàn bộ thư viện.
2. **Một nguồn cho phạm vi pointcut:** đặt biểu thức/config ở vị trí kiểm soát version, có code review và test chọn join point.
3. **Tách hành vi khỏi cơ chế:** logic ghi metric/kiểm toán nên có API nội bộ rõ ràng; syntax pointcut và weaver adapter là phần có thể thay thế có kiểm thử.
4. **Điều kiện thực thi và thứ tự advice:** ghi lại thứ tự tương tác giữa logging, đo thời gian, xác thực, retry; thay order có thể đổi ngữ nghĩa và thời lượng đo.
5. **Xử lý ngoại lệ:** around advice phải giữ nguyên kết quả trả về hoặc ngoại lệ gốc trừ khi hành vi thay đổi đã được thiết kế. Dùng finally cho cleanup/đo thời gian cần kết thúc kể cả khi lỗi.
6. **Tính reentrant và concurrent:** advice thường được gọi đồng thời. Mutable shared state, counter, cache và context phải an toàn cho luồng; không dựa vào thứ tự yêu cầu.
7. **Giới hạn tự áp dụng:** ngăn pointcut bắt vào mã hạ tầng của chính advice nếu điều đó gây recursion, double counting hoặc bão hòa logging.
8. **Format source nhất quán:** cùng charset UTF-8, quy tắc newline/indent, formatter hỗ trợ cú pháp ngôn ngữ aspect tương ứng; không dùng formatter Java thuần trên file chứa cú pháp mà nó không hiểu.
9. **Tài liệu hóa metadata:** nếu logic dựa vào tên tham số, annotations hoặc line number, test các thuộc tính đó còn sau build và weaving.

Một bản thay đổi cách đặt tên package có thể vô tình làm pointcut dạng wildcard bắt quá nhiều hoặc quá ít join point. Do đó, ngoài test chức năng, phải có **kiểm thử hợp đồng pointcut**: ở đầu vào biết trước, advice X phải chạy đúng một lần cho trường hợp A và không chạy ở trường hợp B.

## 7. Ví dụ Java 17: kiểm tra class-file format bằng chương trình chạy độc lập

Trước và sau weaving, việc kiểm tra header của class file giúp phát hiện sớm bytecode vượt phiên bản runtime mục tiêu. Ví dụ dưới đây không cần thư viện AOP; nó kiểm tra một phần của **hợp đồng artifact** và là công cụ bổ trợ, không thay thế verifier hoặc test thực thi.

Lưu toàn bộ chương trình dưới tên **ClassVersionAudit.java**:

```java
import java.io.DataInputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ClassVersionAudit {
    private ClassVersionAudit() {}

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.err.println("Usage: java ClassVersionAudit <file.class>");
            System.exit(2);
        }

        Path file = Path.of(args[0]);
        try (DataInputStream in =
                     new DataInputStream(Files.newInputStream(file))) {
            if (in.readInt() != 0xCAFEBABE) {
                throw new IOException("Not a class file: " + file);
            }

            int minor = in.readUnsignedShort();
            int major = in.readUnsignedShort();
            String target = major >= 49
                    ? "Java " + (major - 44)
                    : "legacy JVM class version " + major;

            System.out.printf(
                    "%s: major=%d, minor=%d (%s)%n",
                    file, major, minor, target);
        }
    }
}
```

Dùng JDK 17 trở lên, biên dịch rõ mục tiêu Java 17:

```bash
javac --release 17 ClassVersionAudit.java
java ClassVersionAudit ClassVersionAudit.class
```

Kết quả xác định khi nguồn được biên dịch đúng bằng lệnh trên:

```text
ClassVersionAudit.class: major=61, minor=0 (Java 17)
```

Nếu cần kiểm tra file sau weaving, chạy chương trình với **đường dẫn đến .class đã dệt** (không đưa trực tiếp đường dẫn JAR vào, vì JAR không có header classfile). Muốn đọc class nằm trong JAR, trước tiên phải lấy đúng entry ra bằng công cụ ZIP/JAR hoặc viết trình đọc archive. Với multi-release JAR, kiểm tra cả các entry ứng với runtime cần hỗ trợ.

**Giới hạn của chương trình:** nó chỉ xác nhận magic, major và minor trong header; nó không chứng minh constant pool, bytecode, stack map frames, references hoặc lời gọi advice hợp lệ. Một file major 61 vẫn có thể bị VerifyError, ClassFormatError hoặc linkage error. Do đó, luôn nối bước này với việc nạp lớp, chạy test thực tế trên runtime mục tiêu và, khi cần, dùng công cụ phân tích classfile/bytecode tương thích đúng phiên bản.

## 8. Ma trận kiểm thử nâng cấp và triển khai

Một bộ test tốt xác minh cả hành vi và sản phẩm đã weave. Ví dụ quy trình cho một lần nâng phiên bản công cụ:

| Cổng kiểm tra | Thao tác | Tín hiệu PASS |
| --- | --- | --- |
| G1 — Resolve | Build từ clean checkout với wrapper và dependency lock đã commit | Cùng tập tọa độ/version/checksum; không còn version động |
| G2 — Compile | Compile source Java và định nghĩa aspect theo target release | Không lỗi syntax, classpath hoặc warning tương thích nghiêm trọng |
| G3 — Weave | Chạy bước weaving duy nhất được thiết kế; lưu danh sách class được biến đổi | Đúng lớp và join point dự kiến; không dệt trùng hoặc bỏ sót |
| G4 — Binary audit | Kiểm tra class major/minor, manifest, service resources và chữ ký | Tương thích runtime tối thiểu, artifact hợp lệ và đủ resource |
| G5 — Functional test | Gọi đường chạy bình thường, ngoại lệ và nested calls | Kết quả, ngoại lệ, side effect đúng; advice count/order khớp |
| G6 — Runtime test | Chạy sản phẩm đóng gói trong JVM/container thật | Không ClassNotFound, NoClassDefFound, VerifyError, module access hoặc agent startup error |
| G7 — Performance | So baseline và bản nâng cấp bằng tải đại diện | Độ trễ, CPU, allocation, GC và throughput nằm trong ngưỡng chấp nhận |
| G8 — Release | Phát hành artifact bất biến cùng manifest nguồn/phiên bản | Có đường quay lui tới artifact và cấu hình tương ứng |

Ma trận phiên bản tối thiểu nên bao gồm JVM **thấp nhất được hỗ trợ**, JVM triển khai chính và JVM mục tiêu của đợt nâng cấp. Nếu có nhiều class loader, nhiều chế độ weaving hoặc nhiều loại archive, bổ sung đúng các tổ hợp được vận hành; tránh kiểm thử toàn bộ tích Descartes tốn kém mà thiếu rủi ro thực tế.

Đối với agent/runtime interception, bổ sung kiểm tra thứ tự nhiều agent, thời điểm nạp class, khả năng retransform/redefine khi được sử dụng và chính sách module/attach của runtime mục tiêu. Khi đổi phiên bản thư viện bytecode, cần kiểm tra cả lớp dùng đặc trưng ngôn ngữ mới như records, sealed classes, invokedynamic hoặc nestmates nếu dự án có sử dụng.

### Kiểm tra tương đương hành vi khi thay đổi version

Viết test với danh sách trường hợp cố định:

- Lời gọi phù hợp pointcut đi qua advice đúng số lần; lời gọi không phù hợp không bị tác động.
- Advice chạy đúng thứ tự khi có nhiều aspect.
- Giá trị trả về và ngoại lệ của phương thức gốc được giữ nguyên theo hợp đồng.
- Context theo luồng/yêu cầu được tạo và dọn dẹp đúng khi chạy đồng thời.
- Không có vòng lặp instrumentation hoặc log/telemetry trùng lặp.
- Startup, class loading và chi phí advice nằm trong giới hạn đã định.

Nếu kết quả khác sau nâng cấp, phân loại nguyên nhân theo **thay đổi syntax/pointcut, bytecode generation, dependency linkage, JVM behavior hay deployment configuration** trước khi sửa.

## 9. Phát hành tái hiện được và kế hoạch quay lui

Một chiến lược triển khai an toàn cho AOP cần quản lý **cả bản đã weave lẫn cấu hình runtime**. Quy trình tham khảo:

1. Tạo artifact trong CI bằng toolchain đã khóa; chạy lại sạch từ cùng commit để phát hiện phụ thuộc version động hoặc trạng thái build sót.
2. Gắn metadata phát hành: commit, JDK release, wrapper/plugin, aspect/weaver/runtime versions, dependency lock fingerprint, loại weaving, checksum JAR và cấu hình agent nếu có.
3. Lưu artifact đã weave như sản phẩm bất biến. Không để môi trường sản xuất tự weave lại khác với bản kiểm thử nếu mục tiêu là dùng compile/post-compile weaving. Nếu dùng load-time weaving, phải quản lý version agent và config runtime tương ứng.
4. Kiểm tra gói cuối cùng sau shading, signing, containerization; đảm bảo đúng lớp được thực thi, không chỉ đúng lớp trong thư mục build tạm.
5. Triển khai theo các giai đoạn được kiểm soát, đo join point count, startup failure, latency đuôi, CPU, GC và lỗi/timeout. Một aspect không chạy mà hệ thống vẫn phục vụ yêu cầu cũng có thể là regression nghiêm trọng.
6. Khi cần rollback, quay lui **đồng bộ** artifact, weaver/agent, JVM image hoặc cấu hình liên quan. Quay lui mỗi dependency nhưng giữ class đã weave cho bản mới có thể không tương thích.

Với load-time weaving, artifact ứng dụng có thể giống nhau nhưng thay version agent hoặc cấu hình pointcut sẽ tạo bytecode trong bộ nhớ khác; do đó version của **môi trường khởi động** cũng thuộc định danh phát hành. Với compile-time weaving, artifact đã được dệt là sản phẩm kiểm thử và không nên bị công cụ khác thay đổi âm thầm về sau.

## 10. Dấu hiệu lỗi phiên bản và cách truy nguyên

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| UnsupportedClassVersionError | Class được compile/weave cho Java mới hơn JVM chạy | Kiểm tra major và target; build lại với release phù hợp nếu công cụ hỗ trợ |
| Unsupported bytecode/class file version trong weaver | Thư viện parse bytecode quá cũ với class input | Kiểm tra support matrix và cập nhật weaver/parser đồng bộ |
| VerifyError hoặc ClassFormatError | Stack frames, bytecode, constant pool, metadata bị tạo sai | Giữ artifact trước/sau weaving; xác định transformer tạo lỗi; dùng phiên bản hỗ trợ |
| NoSuchMethodError, NoClassDefFoundError | Dependency runtime lệch với class được compile hoặc weave | So dependency graph compile/runtime và các thư viện do advice tham chiếu |
| ClassCastException với class cùng tên | Class được nạp bởi các class loader khác nhau | Xác định loader identity, cách ly hoặc thống nhất ranh giới type |
| InaccessibleObjectException, IllegalAccessError | JPMS/module/package access không phù hợp | Kiểm tra exports/opens và quyền truy cập theo tài liệu runtime |
| Agent startup failure | Sai manifest, agent JAR, quyền attach hoặc flags | Xác nhận đúng Premain-Class, thứ tự tham số và runtime hỗ trợ |
| Build thành công nhưng advice không chạy | Pointcut không còn khớp, thiếu config hoặc weaving phase | Test join point count, xem log chẩn đoán của weaver, kiểm tra package/class loader |
| Advice chạy hai lần | Weaving lặp, proxy lồng hoặc nhiều interceptor cùng bắt | Trace đường gọi, ghi nhận cấu hình và lần áp dụng transformer |
| Chỉ một phiên bản JDK bị lỗi | Multi-release entries, metadata hoặc module behavior khác | Kiểm tra đúng class thực nạp trên từng JVM, không chỉ base JAR |
| JAR đã ký không xác thực | Bytes của class/JAR bị biến đổi sau khi ký | Sắp lại pipeline để biến đổi trước rồi ký theo chính sách phát hành |
| p99 hoặc memory tăng sau cập nhật | Weaving đổi code path, advice tạo thêm allocation/IO hoặc xung đột | So baseline, profile, kiểm tra advice count và tải đại diện |

Khi báo lỗi, đính kèm tối thiểu: stack trace đầy đủ, JVM version và flags, toolchain/weaver versions, danh sách dependency ở runtime, checksum JAR, mode weaving, thông tin class loader và class trước/sau weaving. Thiếu các thông tin đó dễ dẫn tới thay phiên bản ngẫu nhiên và tạo thêm biến trong quá trình chẩn đoán.

## 11. Ví dụ quyết định nâng cấp có kiểm soát

Giả sử ứng dụng đang chạy Java 17, có aspect đo thời gian được weave lúc build. Nhóm muốn nâng compiler/weaver lên một bản mới để xử lý cú pháp Java mới và giảm lỗi phân tích class. Các bước hợp lý:

1. Chụp **baseline** của bản đang vận hành: mã nguồn, lockfile, checksum artifact, danh sách class được weave, advice count, test và số liệu hiệu năng.
2. Chỉ nâng compiler/weaver ở nhánh thử nghiệm; tạm giữ Java release 17, runtime và dependency khác trong mức cho phép.
3. Đọc release notes và xác nhận support matrix của chính phiên bản được chọn; chạy G1–G7. Nếu compiler mới tạo metadata khác nhưng class major vẫn 61, vẫn cần test verifier và advice.
4. Nếu cần nâng Java runtime, tách thành phép thử thứ hai: dùng artifact đã kiểm tra trên JVM mới, rồi kiểm tra tổ hợp toolchain mới + JVM mới. Không suy ra tương thích từ từng thay đổi độc lập khi chúng có thể tương tác.
5. Chỉ phát hành khi pointcut contract, hành vi nghiệp vụ và ngưỡng vận hành đạt yêu cầu; nếu không, giữ artifact cũ và lưu kết quả thử nghiệm để phân tích.

Nếu chuyển từ compile-time weaving sang load-time weaving, đây là **thay đổi kiến trúc triển khai**: đường nạp lớp, thứ tự transformer, agent manifest, module access và artifact đầu ra đều có thể khác. Nó cần hồ sơ tương thích và kiểm thử riêng, không chỉ đổi một dependency rồi xem build thành công.

## 12. Checklist bảo trì cho mỗi release

- [ ] Đã ghi rõ cơ chế AOP và toàn bộ công cụ thực sự tham gia tạo/chạy aspect.
- [ ] Compiler, weaver, runtime/agent và thư viện bytecode đã được kiểm tra tương thích với JDK mục tiêu.
- [ ] Build wrapper, dependency versions, transitive graph và checksum được quản lý tái hiện được.
- [ ] Mã nguồn aspect, cú pháp pointcut, cấu hình weaving và thứ tự advice nằm trong version control.
- [ ] Không có bước weave ngoài dự kiến hoặc cùng một join point bị áp dụng trùng.
- [ ] Đã kiểm tra class-file major/minor, metadata, multi-release entries khi có, manifest, chữ ký và classpath/module path.
- [ ] Đã xác nhận API và hành vi: join point đúng phạm vi, kết quả/ngoại lệ/side effect không bị sai.
- [ ] Đã chạy artifact đóng gói thật trên JVM và môi trường tối thiểu được hỗ trợ.
- [ ] Đã so sánh startup, tải đại diện, độ trễ, CPU, bộ nhớ/GC trước khi triển khai.
- [ ] Đã lưu đủ metadata và artifact để rollback theo một tập phiên bản nhất quán.

Quản lý phiên bản AOP thành công nghĩa là **mỗi artifact có thể truy ngược được đã dùng compiler, weaver, thư viện, class-file format và runtime nào**, đồng thời có bằng chứng rằng advice chạy đúng chỗ, đúng hành vi và đúng mức chi phí. Khi những điều kiện đó được kiểm soát, việc nâng cấp và triển khai aspect trở nên có thể dự đoán, kiểm chứng và khôi phục.
