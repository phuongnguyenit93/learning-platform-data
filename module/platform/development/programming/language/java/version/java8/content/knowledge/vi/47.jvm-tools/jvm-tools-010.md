# Kiểm thử công cụ, agent và thư viện bytecode trên JDK hiện hành

**Chủ đề cha:** JVM và công cụ. **Đề bài:** Xây dựng cách kiểm thử có hệ thống cho công cụ JVM, Java agent, native/JVMTI agent và thư viện phân tích, tạo hoặc biến đổi bytecode khi JDK phát triển. Trọng tâm là khả năng đọc class file mới, tính đúng đắn của bytecode sau transform, tương thích runtime/API, module và class loader, cách agent được nạp, cùng các thay đổi mới của JDK ảnh hưởng đến profiler, coverage, mocking và công cụ chẩn đoán.

**Mốc phiên bản:** Ngày 06-11-2026, **JDK 27** là bản Java SE hiện hành đã phát hành GA ngày 15-09-2026. JDK 27 dùng class-file major version **71**. Class-File API trong gói java.lang.classfile là API chuẩn từ JDK 24; JDK 27 dùng API này để parse, verify, transform và generate class file. Các chương trình agent trong bài dùng Java 17+; ví dụ Class-File API cần JDK 24+.

> **Nguyên tắc:** Một thư viện bytecode có thể chạy được trên JDK mới nhưng vẫn không đọc được class file mới; một parser đọc được class file chưa chắc sinh bytecode verifier chấp nhận; một agent khởi động được chưa chắc hoạt động đúng khi retransformation, module hoặc class loader thay đổi. Phải kiểm thử **runtime của công cụ**, **phiên bản class file đầu vào**, **phiên bản class file đầu ra**, **cơ chế nạp agent** và **ngữ nghĩa bytecode sau transform**.

## 1. Vì sao phải kiểm thử riêng công cụ JVM?

Ứng dụng Java thông thường chủ yếu sử dụng API ở mức ngôn ngữ và thư viện. Công cụ bytecode đi sâu hơn: đọc cấu trúc class file, phân tích constant pool, method descriptor, stack map frame, exception table, module attribute, annotation, bootstrap method và các thành phần JVM khác. Một thay đổi ở compiler, JVM verifier, module system hoặc class-file format có thể làm công cụ cũ lỗi dù mã ứng dụng không thay đổi.

Những sản phẩm thường nằm trong nhóm này:

- **Java agent:** coverage, tracing, profiling, APM, logging, security monitoring, mock inline và công cụ đo thời gian thực thi.
- **Native/JVMTI agent:** profiler native, debugger, công cụ quan sát JVM và tích hợp với hệ điều hành.
- **Bytecode library:** ASM, Byte Buddy, Javassist và Class-File API của JDK.
- **Build/test tooling:** Maven Surefire/Failsafe, Gradle Test, test runner, compiler plugin, code coverage và instrumentation trong test.
- **JVM diagnostics:** javap, jdeps, jar, jcmd, JFR, jfr, Serviceability Agent và công cụ phân tích dump.

Một lỗi instrumentation có thể làm thay đổi hành vi ứng dụng, gây VerifyError, LinkageError, ClassCircularityError, rò rỉ class loader hoặc tăng latency. Vì vậy, kiểm thử công cụ phải kiểm tra **bytecode đầu ra và hành vi runtime**, không chỉ kiểm tra rằng API thư viện được gọi mà không ném exception.

### 1.1. Bốn trục tương thích cần tách riêng

| Trục | Câu hỏi | Ví dụ kiểm tra |
| --- | --- | --- |
| JDK chạy công cụ | Tool/agent có khởi động được trên JDK triển khai không? | Chạy agent và test runner trên các JDK trong support policy |
| Class file đầu vào | Parser có đọc được class file mà compiler/framework phát ra không? | Java 17 major 61, Java 27 major 71 |
| Class file đầu ra | Bytecode sau transform có đúng format và được JVM verifier chấp nhận không? | Parse lại, verify và chạy với -Xverify:all |
| Cách agent được nạp | Tool có dựa vào startup agent hay dynamic attach? | Chạy với -javaagent, thử dynamic attach và kiểm tra JEP 451 |

**Không dùng một trục để suy ra ba trục còn lại.** Ví dụ, javac --release 17 chỉ kiểm soát source/API/class file của chương trình được biên dịch. Nó không chứng minh parser hỗ trợ Java 27, cũng không chứng minh agent có thể retransformation class đang chạy trên JDK 27.

## 2. Những mốc class-file quan trọng

Class file bắt đầu bằng magic number 0xCAFEBABE, tiếp theo là minor version và major version. Major version giúp JVM và công cụ biết định dạng class file thuộc thế hệ nào.

| Java SE | Class-file major |
| --- | ---: |
| Java 8 | 52 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 24 | 68 |
| Java 25 | 69 |
| Java 26 | 70 |
| **Java 27** | **71** |

JVM của Java SE 27 hỗ trợ major version đến 71. Nếu tool sinh class file major 72 rồi đưa vào JVM 27, việc load class sẽ thất bại vì runtime chưa hỗ trợ định dạng đó. Ngược lại, parser chạy trên JDK cũ có thể từ chối class file mới dù class file đó hợp lệ trên JDK mới.

### 2.1. Preview class file có minor version đặc biệt

Từ Java 12, class file dùng preview features có minor version 65535. Ví dụ, class file preview của Java 27 có version 71.65535.

- Class file preview của **cùng release** chỉ được load khi bật preview cho đúng release, ví dụ --enable-preview trên JDK 27.
- Class file preview của release cũ không thể được load chỉ bằng cách bật preview trên release mới hơn. Ví dụ, class file 70.65535 của Java 26 không trở thành class file preview hợp lệ trên JDK 27.
- Class file không dùng preview thường có minor version 0 với các major version hiện đại.

Khi kiểm thử parser hoặc agent, hãy có cả fixture class file thường và preview. Không hạ minor version bằng cách sửa header rồi coi đó là phép chuyển đổi hợp lệ; nội dung class file có thể phụ thuộc vào feature preview và verifier của release tương ứng.

### 2.2. Compiler target và runtime target là hai lựa chọn khác nhau

javac --release 17 biên dịch mã với API và class-file target Java 17. Chạy class file đó trên JDK 27 là một bài test runtime. Nó không tạo fixture Java 27.

Để tạo fixture cho nhiều release:
- Dùng đúng compiler release tương ứng hoặc CI có JDK tương ứng.
- Lưu fixture class file theo release để parser/transformer kiểm thử.
- Ghi rõ class file được biên dịch từ source nào, với compiler version và preview flag nào.
- Không sửa major/minor thủ công để giả lập compiler mới.

Nếu tool phải hỗ trợ class file từ nhiều release, fixture nên gồm baseline mà sản phẩm hỗ trợ, LTS đang hỗ trợ và release mới nhất mà tool công bố hỗ trợ.

## 3. Những thay đổi JDK 27 ảnh hưởng đến công cụ

JDK 27 không chỉ nâng major version lên 71. Các công cụ đọc cấu trúc JVM, quan sát object hoặc xử lý dữ liệu chẩn đoán cần kiểm thử các thay đổi runtime sau.

| Thay đổi trong JDK 27 | Ảnh hưởng đến tool/agent |
| --- | --- |
| Class file major 71 | Parser, writer, verifier và instrumentation library phải nhận dạng class file Java 27 |
| Compact Object Headers mặc định bật trên HotSpot | Profiler/native agent không được giả định kích thước hoặc offset object header nội bộ cố định |
| G1 trở thành garbage collector mặc định trong mọi môi trường HotSpot | Kiểm thử tool thu thập GC/JFR metrics với G1 mặc định và các collector mà sản phẩm hỗ trợ |
| JFR redaction mặc định đối với command-line arguments, giá trị ban đầu của environment variables và system properties | Tool phân tích recording không được mặc định rằng mọi giá trị nhạy cảm sẽ hiện nguyên văn |
| Serviceability Agent loại bỏ lệnh clhsdb printmdo | Script chẩn đoán dựa vào lệnh này phải được cập nhật |
| Có jcmd VM.security_properties | Có thể dùng để kiểm tra security properties đang hoạt động trong JVM |

**Compact Object Headers:** Tool dùng API được hỗ trợ như JVMTI, JFR và Management API thay vì đọc offset object header nội bộ bằng Unsafe hoặc giả định layout HotSpot. Nếu profiler có native code phụ thuộc layout, hãy chạy regression trên JDK 27 với mặc định và với tùy chọn tắt compact headers khi runtime còn hỗ trợ tùy chọn đó.

**JFR redaction:** Test nên xác nhận dữ liệu nhạy cảm được che theo cấu hình hiện hành. Không làm test pass bằng cách tắt toàn bộ redaction nếu sản phẩm không có yêu cầu nghiệp vụ rõ ràng. Nếu tool cần một trường cụ thể, thiết kế event hoặc cấu hình redaction theo allowlist và kiểm thử quyền truy cập recording.

**Serviceability Agent:** Nếu công cụ dùng clhsdb, kiểm tra command được hỗ trợ trên JDK mục tiêu. Đừng phụ thuộc vào output nội bộ không được cam kết ổn định giữa các release.

## 4. Java agent và vòng đời Instrumentation

Java agent dùng module java.instrument. Agent JAR chứa một class agent và manifest khai báo entry point. JVM truyền đối tượng Instrumentation cho agent để đăng ký transformer hoặc thực hiện các thao tác instrumentation được hỗ trợ.

Có ba cơ chế khởi động thường gặp:

| Cơ chế | Manifest | Entry point | Thời điểm |
| --- | --- | --- | --- |
| Startup agent | Premain-Class | premain(String, Instrumentation) | JVM khởi động, trước main của ứng dụng |
| Dynamic agent | Agent-Class | agentmain(String, Instrumentation) | Sau khi JVM đã chạy, nếu implementation cho phép attach |
| Agent nằm trong executable JAR | Launcher-Agent-Class | agentmain(String, Instrumentation) | Trước main của ứng dụng khi launcher hỗ trợ |

Với startup agent, lệnh thường dùng:

~~~bash
java -javaagent:trace-agent.jar=demo/ -jar application.jar
~~~

Có thể truyền nhiều -javaagent trên cùng command line. premain được gọi theo thứ tự agent được khai báo. Thứ tự này có ý nghĩa vì các transformer có thể xử lý nối tiếp cùng một class file.

### 4.1. Manifest của agent JAR

Ví dụ:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.TraceAgent
Can-Redefine-Classes: true
Can-Retransform-Classes: true

~~~

- Premain-Class là binary name của class chứa premain.
- Can-Redefine-Classes khai báo agent có cần khả năng redefine hay không.
- Can-Retransform-Classes khai báo agent có cần khả năng retransformation hay không.
- Những capability không khai báo mặc định là false.

Không bật capability chỉ để "phòng khi cần". Chỉ yêu cầu những gì agent thật sự sử dụng, sau đó kiểm tra Instrumentation.isRedefineClassesSupported() và isRetransformClassesSupported() trước khi gọi API tương ứng.

### 4.2. ClassFileTransformer

ClassFileTransformer nhận class file bytes trước khi JVM define class. Nó có thể được gọi khi:
- Class được load lần đầu.
- Class được redefine.
- Class được retransform nếu transformer có khả năng retransformation.

Ví dụ chữ ký hiện hành:

~~~java
byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer);
~~~

Các quy tắc cần nhớ:

1. className dùng internal form với dấu /, ví dụ demo/Greeter.
2. loader có thể là null với bootstrap class loader.
3. classBeingRedefined là null khi class được load lần đầu.
4. Không sửa trực tiếp classfileBuffer; coi đó là input chỉ đọc.
5. Trả null nếu không cần biến đổi.
6. Nếu có thay đổi, trả về một byte[] mới chứa class file hoàn chỉnh, hợp lệ.
7. Khi nhiều transformer cùng áp dụng, output của transformer trước là input của transformer tiếp theo.
8. Exception bị ném ra từ transformer không làm JVM tự động hủy toàn bộ class loading; theo contract, nó có hiệu ứng như không transform. Vì vậy phải tự ghi log/metric lỗi thay vì trông chờ exception làm test fail.

**Cẩn thận với class JDK cốt lõi:** Nếu transformer xử lý class C nhưng trong lúc transform lại load hoặc resolve chính C hay một dependency gây vòng lặp, có thể xảy ra LinkageError hoặc lỗi circularity. Transformer nên nhỏ, tránh reflection hoặc load class không cần thiết trong callback.

### 4.3. Redefine và retransform không phải công cụ thay schema tùy ý

HotSwap/Instrumentation hỗ trợ thay đổi nội dung method trong giới hạn của JVM. Không giả định có thể thêm/xóa field, method, đổi signature, superclass hoặc cấu trúc class tùy ý khi redefine một class đã được load.

Thiết kế instrumentation nên:
- Đưa helper field/method cần thiết vào class ngay từ lần load đầu nếu schema cho phép.
- Ưu tiên sửa method body khi có thể.
- Kiểm tra capability trước khi redefine/retransform.
- Test trên đúng JVM vendor/version.
- Test nhiều lần retransform để bảo đảm output ổn định và không chèn instrumentation trùng lặp.

Transformer có canRetransform=false không được gọi lại theo cùng cách trong mỗi lần retransform; JVM tái sử dụng kết quả trước đó của nhóm transformer không hỗ trợ retransform. Transformer có canRetransform=true được gọi lại. Hãy kiểm thử cả hai kiểu nếu agent hỗ trợ retransformation.

## 5. Dynamic attach và JEP 451

Dynamic attach cho phép một công cụ kết nối tới JVM đang chạy rồi yêu cầu JVM nạp agent. API Java thường dùng là com.sun.tools.attach.VirtualMachine trong module JDK jdk.attach. Đây là API của JDK, không phải API Java SE portable có mặt trong mọi runtime image.

JEP 451 được triển khai từ JDK 21:
- JVM cảnh báo khi Java agent hoặc JVM TI agent được nạp vào một JVM đang chạy.
- Startup agent qua -javaagent hoặc -agentlib không tạo cảnh báo dynamic-load này.
- Với HotSpot, -XX:+EnableDynamicAgentLoading là opt-in rõ ràng cho dynamic loading và có thể tắt cảnh báo.
- -XX:-EnableDynamicAgentLoading giúp kiểm thử xem ứng dụng/test framework có phụ thuộc vào dynamic attach hay không.
- Mục tiêu của JEP là chuẩn bị cho việc không cho dynamic loading mặc định trong một release tương lai. Khi hỗ trợ JDK mới, cần kiểm tra trạng thái thực tế thay vì giả định cơ chế này sẽ luôn được bật mặc định.

**Khuyến nghị cho test framework:** Nếu thư viện mocking, coverage hoặc profiling tự attach agent vào JVM đang chạy, hãy kiểm tra xem có thể nạp agent lúc JVM khởi động bằng -javaagent hay không. Điều này giúp hành vi test rõ ràng, tránh phụ thuộc vào Attach API và cảnh báo dynamic loading.

Một runtime image tạo bằng jlink có thể không chứa module jdk.attach. Nếu sản phẩm cần attach API, kiểm tra module trong image triển khai. Dynamic attach cũng phụ thuộc OS permission, process ownership, provider và cấu hình JVM đích. Không coi việc attach thành công trên máy phát triển là bảo đảm sẽ thành công trong container hoặc môi trường production.

### 5.1. Java agent và native JVMTI agent

Java agent và native JVMTI agent có cùng mục tiêu quan sát/biến đổi JVM nhưng khác cơ chế:

- Java agent dùng java.lang.instrument, class file transformer và Java bytecode library.
- Native agent dùng JVM Tool Interface (JVMTI), native library và ABI của hệ điều hành/CPU.
- Native agent thường được nạp bằng -agentlib:name hoặc -agentpath:/path/to/lib.
- Dynamic attach có thể nạp Java agent hoặc native agent nếu implementation hỗ trợ.

Với native agent, ma trận test phải thêm OS, CPU architecture, native compiler/runtime và ABI. Không hard-code layout nội bộ HotSpot hoặc giả định compact object headers luôn tắt.

## 6. Module system và class loader trong instrumentation

### 6.1. Cùng tên class nhưng khác class loader là hai kiểu khác nhau

Trong JVM, identity của một class được xác định bởi **binary name và defining class loader**. Hai class có cùng tên com.example.Plugin nhưng được hai loader khác nhau định nghĩa có thể không assignable cho nhau.

Transformer nên xem xét đồng thời:
- className
- loader
- module
- protectionDomain

Đừng chỉ dùng Map theo class name để lưu trạng thái cho tất cả class loader. Cách đó dễ gộp nhầm hai class khác nhau và có thể giữ class loader lâu hơn vòng đời ứng dụng. Cân nhắc ClassValue, weak-key map hoặc lifecycle cleanup phù hợp.

### 6.2. Bootstrap, platform và system class loader

Agent class thường được load bởi system class loader và thuộc unnamed module của loader đó. Nếu agent cần helper class ở bootstrap loader, có API như appendToBootstrapClassLoaderSearch, nhưng chỉ nên dùng khi thật sự cần. Helper đặt vào bootstrap search phải phụ thuộc vào các class mà bootstrap loader có thể nhìn thấy; không mặc định toàn bộ thư viện application sẽ có mặt ở đó.

Một số transformer có thể nhận loader == null. Đây không phải dữ liệu thiếu hay bug; nó biểu thị bootstrap loader.

### 6.3. Module access khác với bytecode transformation

Java Platform Module System kiểm soát readability, exports và opens. Một agent có thể cần:
- --add-opens ở startup để hỗ trợ reflection trên một package cụ thể.
- Instrumentation.redefineModule(...) để thêm reads/exports/opens theo khả năng API.
- --add-modules để bảo đảm module cần thiết được resolve vào boot layer.

Mở package cho reflection không tự sửa lỗi verifier, linkage hoặc thiếu class. Tương tự, transform bytecode thành công không tự cấp quyền truy cập vào package không được export/open. Test riêng classpath, module path và runtime image đã rút gọn.

## 7. Class-File API chuẩn trong JDK

Từ JDK 24, Java có API chuẩn java.lang.classfile trong module java.base. API này được phát triển qua các giai đoạn preview trước khi final hóa. Nó hỗ trợ:
- Parse class file thành ClassModel.
- Truy cập class, method, field, constant pool và attribute.
- Verify class file.
- Transform class file qua ClassTransform.
- Generate class file qua ClassBuilder.
- Chọn options ảnh hưởng parsing, writing và stack map generation.

Một điểm hữu ích là ClassFile.latestMajorVersion() trả major version mới nhất mà runtime hiện tại hỗ trợ. Trên JDK 27, giá trị này là 71; trên JDK 24 là 68.

**Class-File API không thay thế Java agent API.** ClassFileTransformer vẫn nhận/trả byte[]. Agent có thể dùng Class-File API bên trong callback để parse và transform bytes. API chuẩn giúp giảm phụ thuộc vào parser bên thứ ba nếu tool chỉ cần xử lý các cấu trúc class file theo API của JDK đang chạy.

### 7.1. Khi nào vẫn cần thư viện bên thứ ba?

| Công cụ | Điểm mạnh | Phù hợp khi |
| --- | --- | --- |
| Class-File API | API chuẩn JDK, parse/verify/transform/generate | Muốn giảm dependency và target JDK 24+ |
| ASM | Visitor/tree API mức thấp, kiểm soát bytecode chi tiết | Cần transform phức tạp, hỗ trợ nhiều class-file versions |
| Byte Buddy | API mức cao để tạo type, method và agent | Cần instrumentation/Advice hoặc code generation mà không tự thao tác từng instruction |
| Javassist | API thao tác bytecode với abstraction mức cao | Dự án đã dùng và version hiện tại hỗ trợ class file mục tiêu |

Không chọn library chỉ dựa vào việc nó có thể compile trên JDK mới. Hãy xem version matrix, changelog, release note và test thực tế trên class file mới nhất mà sản phẩm nhận vào. Với parser/transformer chạy trên JDK cũ nhưng phải đọc class file mới, khả năng hỗ trợ class-file format của chính library quan trọng hơn phiên bản Java mà library dùng để compile.

## 8. Phiên bản thư viện bytecode cần kiểm tra

Tại thời điểm 06-11-2026, các mốc công khai đáng chú ý gồm:

| Thành phần | Mốc phiên bản hiện hành được công bố | Ý nghĩa cho kiểm thử |
| --- | --- | --- |
| ASM | 9.11.1; ASM 9.11 thêm Opcodes.V27 | Dùng version có hỗ trợ class file Java 27; kiểm tra bug fix của 9.11.1 |
| Byte Buddy | 1.18.16; 1.18.15 công bố hỗ trợ Java 28 | 1.18.16 cập nhật ASM 9.11.1; test Advice, constructors, frames và dynamic attach |
| JaCoCo | 0.8.16 hỗ trợ Java 27 chính thức | Không dùng bản cũ chỉ có hỗ trợ experimental nếu production đã phát JDK 27 |
| JDK Class-File API | Có từ JDK 24; JDK 27 nhận major 71 | Không cần dependency ngoài cho các thao tác class file cơ bản trên JDK 24+ |

Đây là **ảnh chụp phiên bản tại ngày viết**, không phải cam kết rằng version number sẽ giữ nguyên. Khi nâng JDK hoặc library, hãy kiểm tra release notes mới nhất, security fixes, compatibility matrix và dependency tree.

### 8.1. Kiểm tra dependency graph

Một dự án có thể kéo nhiều phiên bản ASM qua Byte Buddy, JaCoCo, framework mocking hoặc plugin build. Nếu các module asm, asm-tree, asm-commons, asm-util bị lệch phiên bản, lỗi có thể xuất hiện ở runtime dù compile thành công.

Maven:

~~~bash
mvn dependency:tree -Dincludes=org.ow2.asm,net.bytebuddy,org.jacoco
~~~

Gradle:

~~~bash
./gradlew dependencyInsight --dependency asm --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency byte-buddy --configuration testRuntimeClasspath
~~~

Kiểm tra cả dependency của test runtime, agent runtime và plugin build. Một version mới ở compile classpath không đảm bảo test worker hoặc agent JAR cũng dùng version đó.

## 9. Những cấu trúc bytecode phải có trong fixture

Một test suite chỉ dùng class đơn giản có constructor và một method sẽ bỏ sót nhiều lỗi. Khi library parse/transform class file, hãy có fixture chứa:

- Class, interface, enum, annotation, generic signature.
- StackMapTable, exception table, line/local-variable tables.
- Runtime visible/invisible annotations và type annotations.
- invokedynamic, lambda, method handle và bootstrap methods.
- CONSTANT_Dynamic (dynamic constants) khi target release hỗ trợ.
- Nest host/member, inner class và synthetic/bridge method.
- Record components và sealed classes/permitted subclasses.
- module-info.class, module attributes, service metadata.
- Multi-release JAR với base entry và META-INF/versions/N.
- Class được compiler tạo từ preview features, nếu sản phẩm hỗ trợ preview.
- Class được generate từ framework hoặc Kotlin/Scala/Groovy nếu các ngôn ngữ đó nằm trong phạm vi hỗ trợ.

Với ASM, cần chú ý ClassReader, ClassWriter, ClassVisitor, MethodVisitor, Frame và các visitor cho attribute. Nếu dùng ClassWriter.COMPUTE_FRAMES, test resolver của superclass/common supertype; class loader của test có thể không nhìn thấy mọi dependency. Đừng chỉ assert rằng ClassWriter.toByteArray() không ném exception.

## 10. Kiểm tra bytecode trước và sau khi biến đổi

Một pipeline kiểm thử tốt có nhiều lớp xác nhận:

1. **Parse:** parser nhận được class file, đọc được class name, version, methods và attributes.
2. **Structural verification:** Class-File API hoặc verifier của library không phát hiện lỗi cấu trúc.
3. **JVM verification:** load/execute class đã transform trên JVM mục tiêu với -Xverify:all.
4. **Behavioral test:** gọi method sau transform và so sánh kết quả với expected behavior.
5. **Repeatability:** chạy transform hai lần, kiểm tra không nhân đôi instrumentation ngoài ý muốn.
6. **Retransformation:** kiểm tra class đã load có thể retransform theo capability và schema rules.
7. **Compatibility:** chạy cùng output trên các JDK nằm trong support matrix.

Một transform có thể tạo byte array hợp lệ ở mức parser nhưng vẫn sai stack map frame hoặc tham chiếu method. Chỉ chạy ClassFile.verify hay CheckClassAdapter chưa đủ để chứng minh JVM sẽ load class thành công. Hãy load/execute output trong forked JVM thật.

### 10.1. Stack map frames và verifier

Với class file hiện đại, stack map frames là phần quan trọng của bytecode verification. Khi chèn instruction, thay control flow hoặc sửa exception handler, tool phải bảo đảm:
- max_stack và max_locals phù hợp.
- Branch target và exception handler hợp lệ.
- Frame state tại mỗi basic block đúng.
- Uninitialized object/constructor state không bị làm sai.
- Method descriptor, return type và operand stack khớp.
- Bootstrap method/constant pool entry còn tham chiếu đúng.

Một số thay đổi chỉ thêm instruction tuyến tính có vẻ đơn giản nhưng vẫn làm sai frame tại branch hoặc exception handler. Luôn chạy verifier và test behavior sau transform.

### 10.2. Transform phải ổn định khi được gọi lại

Một agent có thể bị gọi lại trong quá trình retransformation. Nếu mỗi lần callback lại chèn thêm cùng một logging call, class có thể bị instrument lặp. Thiết kế transform theo hướng:
- Xác định class/method đã có marker hoặc trạng thái phù hợp.
- Không mutate input byte array.
- Trả null khi không cần thay đổi.
- Xử lý class đã được agent khác biến đổi.
- Không giả định transformer là duy nhất hoặc luôn chạy đầu tiên.
- Test thứ tự nhiều agent trên cùng một JVM.

## 11. Java 17+: Ví dụ agent quan sát class được load

Ví dụ này tạo một startup agent đăng ký ClassFileTransformer. Agent chỉ ghi tên class trong package demo và trả null, tức không thay đổi bytecode. Mục tiêu là kiểm tra manifest, entry point premain, transformer callback và thứ tự load class.

Cấu trúc thư mục:

~~~text
src-agent/
  demo/
    TraceAgent.java
src-app/
  demo/
    Main.java
    Greeter.java
out/
  MANIFEST.MF
~~~

File **TraceAgent.java**:

~~~java
package demo;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class TraceAgent {
    public static void premain(String args, Instrumentation inst) {
        String prefix = args == null || args.isBlank()
                ? "demo/"
                : args;

        inst.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    Module module,
                    ClassLoader loader,
                    String className,
                    Class<?> classBeingRedefined,
                    ProtectionDomain protectionDomain,
                    byte[] classfileBuffer) {

                if (className != null
                        && className.startsWith(prefix)) {
                    System.out.println("SEEN " + className);
                }

                return null;
            }
        }, false);
    }
}
~~~

File **Main.java**:

~~~java
package demo;

public final class Main {
    public static void main(String[] args) {
        System.out.println(new Greeter().message());
    }
}
~~~

File **Greeter.java**:

~~~java
package demo;

public final class Greeter {
    public String message() {
        return "Hello from instrumented app";
    }
}
~~~

Manifest **MANIFEST.MF**:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.TraceAgent

~~~

Biên dịch và đóng gói (lệnh Bash):

~~~bash
mkdir -p out/agent-classes out/app-classes

javac --release 17 -d out/agent-classes \
  src-agent/demo/TraceAgent.java

jar cfm out/trace-agent.jar out/MANIFEST.MF \
  -C out/agent-classes demo

javac --release 17 -d out/app-classes \
  src-app/demo/Main.java src-app/demo/Greeter.java

java -Xverify:all \
  -javaagent:out/trace-agent.jar=demo/ \
  -cp out/app-classes demo.Main
~~~

**Stdout xác định:**

~~~text
SEEN demo/Main
SEEN demo/Greeter
Hello from instrumented app
~~~

Giải thích:
- premain chạy trước main của ứng dụng.
- Agent đăng ký transformer trước khi ứng dụng bắt đầu load class demo/Main.
- className dùng dấu /, nên prefix demo/ khớp.
- classfileBuffer được giữ nguyên; callback trả null để báo không transform.
- -Xverify:all yêu cầu JVM thực hiện verification đầy đủ khi load class.
- Agent này **chỉ quan sát**, không chứng minh một bytecode transform thực tế đã đúng. Khi chuyển sang chèn instruction, cần tạo byte array mới, verify và chạy behavioral test riêng.

Mẫu đã được biên dịch và chạy trong workspace trên JDK 24.0.2; output cho thấy startup agent và callback hoạt động. Nên chạy lại cùng test trên JDK 27 trong CI.

## 12. Java 24+: Dùng Class-File API để parse và verify

Ví dụ sau đọc một class file, lấy internal class name, major version và số lỗi verifier.

Tạo file **ClassFileApiDemo.java**:

~~~java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.nio.file.Path;

public class ClassFileApiDemo {
    public static void main(String[] args) throws Exception {
        ClassFile classFile = ClassFile.of();
        ClassModel model = classFile.parse(Path.of(args[0]));

        System.out.println("Class: "
                + model.thisClass().asInternalName());
        System.out.println("Major: " + model.majorVersion());
        System.out.println("Verify errors: "
                + classFile.verify(model).size());
        System.out.println("Runtime max major: "
                + ClassFile.latestMajorVersion());
    }
}
~~~

Biên dịch và chạy trên JDK 24+:

~~~bash
javac --release 24 -d out/tools ClassFileApiDemo.java

java -cp out/tools ClassFileApiDemo \
  out/app-classes/demo/Main.class
~~~

Ví dụ input Main.class được biên dịch với --release 17:

**Stdout trên JDK 24:**

~~~text
Class: demo/Main
Major: 61
Verify errors: 0
Runtime max major: 68
~~~

Trên JDK 27, cùng class input major 61 vẫn được parse; dòng Runtime max major dự kiến là **71**. API này được final từ JDK 24; không thể biên dịch chương trình trên bằng --release 17 vì package java.lang.classfile chưa có ở Java 17.

**Giới hạn:** ClassFile.verify là một bước kiểm tra class file. Để kiểm chứng hành vi trong JVM, vẫn cần chạy class đã tạo/biến đổi trên runtime mục tiêu, có thể dùng -Xverify:all. Parser có thể phát hiện malformed/unsupported class file; accessor của ClassModel cũng có thể phát sinh lỗi khi parse theo cơ chế on-demand.

## 13. Công cụ JDK để chẩn đoán class file và dependency

Các công cụ đi kèm JDK giúp tìm nguyên nhân trước khi viết thêm code debug.

### 13.1. javap

javap disassemble class file. Một số lệnh hữu ích:

~~~bash
javap -verbose -classpath out/app-classes demo.Main
javap -c -s -p -classpath out/app-classes demo.Greeter
javap -verify -classpath out/app-classes demo.Main
~~~

- -verbose: constant pool, class version, flags, attributes.
- -c: bytecode instruction.
- -s: descriptor.
- -p: hiển thị cả member private.
- -verify: thông tin verification bổ sung.
- --multi-release 27: chọn version entry khi kiểm tra multi-release JAR.

**Lưu ý:** javap không tự chọn version entry của multi-release JAR nếu chỉ truyền classpath như JAR thông thường. Dùng --multi-release hoặc URL trỏ tới entry version cụ thể để kiểm tra đúng class file.

### 13.2. jdeps

Tìm dependency và tham chiếu JDK internal APIs:

~~~bash
jdeps --jdk-internals --recursive out/trace-agent.jar
jdeps --multi-release 27 --jdk-internals library.jar
~~~

jdeps --jdk-internals giúp phát hiện dependency compile-time tới internal APIs. Nó không tìm hết mọi truy cập reflection được tạo động; cần kết hợp runtime test, log và kiểm tra dependency.

### 13.3. jar

Kiểm tra cấu trúc JAR và module:

~~~bash
jar --list --file library.jar
jar --describe-module --file library.jar
~~~

Với agent JAR, kiểm tra manifest thực tế:

~~~bash
jar --list --file trace-agent.jar
unzip -p trace-agent.jar META-INF/MANIFEST.MF
~~~

Không chỉ nhìn file source manifest; xác minh nội dung manifest nằm trong JAR sau bước packaging.

### 13.4. jcmd, JFR và diagnostics

Trên JVM đang chạy:

~~~bash
jcmd <pid> help
jcmd <pid> VM.command_line
jcmd <pid> VM.system_properties
jcmd <pid> VM.classloaders
jcmd <pid> VM.security_properties
~~~

Command cụ thể phụ thuộc JDK/provider. JDK 27 có thêm VM.security_properties, hữu ích khi kiểm tra security properties thực tế.

Với recording:

~~~bash
jfr summary recording.jfr
jfr print --events jdk.ExecutionSample recording.jfr
~~~

Khi test JFR trên JDK 27, nhớ các trường command-line/environment/property có thể đã bị redaction theo mặc định. Test parser/report của bạn với recording có redaction, không giả định mọi trường luôn tồn tại.

## 14. Multi-release JAR và các class file theo phiên bản

Multi-release JAR cho phép một thư viện cung cấp implementation khác nhau theo release Java. JAR có manifest:

~~~text
Multi-Release: true
~~~

Các entry có thể nằm tại:
- Root JAR: implementation baseline.
- META-INF/versions/17/...
- META-INF/versions/21/...
- META-INF/versions/25/...

Khi runtime Java 27 load multi-release JAR, nó chọn versioned entry cao nhất không vượt quá release đang chạy, sau đó fallback về entry thấp hơn hoặc root.

Tool transform JAR phải:
- Giữ nguyên META-INF/MANIFEST.MF.
- Không xóa các entry META-INF/versions/N.
- Xử lý từng class file theo version tương ứng.
- Không đưa class file có major version cao hơn mức được phép vào versioned directory.
- Giữ public/protected API nhất quán theo yêu cầu của multi-release JAR specification.
- Kiểm tra module descriptor ở root và các versioned directory nếu có.

Dùng javap --multi-release 27 và jdeps --multi-release 27 để kiểm tra đúng view của release. Đừng chỉ parse root entry rồi kết luận toàn bộ JAR tương thích Java 27.

## 15. Ma trận kiểm thử CI cho agent và bytecode library

Một ma trận thực tế nên phân biệt JDK chạy tool và class file mà tool phải xử lý.

| Nhóm test | Dữ liệu/Runtime | Kết quả cần xác nhận |
| --- | --- | --- |
| Baseline runtime | JDK thấp nhất sản phẩm còn hỗ trợ | Agent/tool khởi động và xử lý class cơ bản |
| LTS runtime | JDK LTS mà sản phẩm cam kết hỗ trợ | Không lỗi module, attach hoặc verifier |
| Current runtime | JDK 27 | Hỗ trợ class major 71 và thay đổi runtime mới |
| Class file fixtures | Class major 52, 61, 65, 68, 69, 70, 71 nếu có | Parser nhận diện đúng, transform không làm hỏng |
| Preview fixtures | Minor version 65535 của đúng release | Xử lý theo đúng preview policy |
| Agent startup | -javaagent/-agentlib | Agent được nạp trước ứng dụng, manifest đúng |
| Dynamic attach | agentmain/Attach API | Cảnh báo, quyền truy cập và flag được kiểm thử |
| Retransformation | Class đã load, retransform nhiều lần | Không duplicate instrumentation, đúng schema rules |
| Module/class loader | Classpath, module path, custom loader | Không nhầm type identity hoặc access |
| Packaging | JAR thường và multi-release JAR | Không mất versioned entries, manifest hoặc module info |
| Runtime verification | -Xverify:all | Không có VerifyError/ClassFormatError |
| Behavioral | Chạy method đã transform | Kết quả và exception đúng yêu cầu |
| Native agent | OS/CPU support matrix | ABI, native library và JVMTI tương thích |

Ví dụ matrix release nếu sản phẩm hỗ trợ các runtime này: JDK 17, 21, 25 và 27. Nếu support policy còn bao gồm JDK khác, thêm vào matrix. Không cần test mọi JDK đã từng phát hành; cần test baseline cam kết, LTS quan trọng và release hiện hành.

### 15.1. Dùng --release để khóa API baseline

Nếu tool cần chạy từ JDK 17 trở lên, compile phần core agent:

~~~bash
javac --release 17 -d out/classes src/main/java/demo/*.java
~~~

Phần dùng Class-File API phải được tách thành module/source set chỉ build trên JDK 24+ hoặc có implementation khác cho JDK cũ. Không tham chiếu trực tiếp java.lang.classfile trong code cần compile --release 17.

### 15.2. Kiểm thử dynamic attach như một dependency thật

Thử chạy test worker với:

~~~bash
java -XX:-EnableDynamicAgentLoading -jar test-runner.jar
~~~

Nếu một framework cố attach agent vào JVM đang chạy, test có thể thất bại hoặc báo không được phép. Khi đó:
- Xác định agent nào được attach và vì sao.
- Kiểm tra test runner có hỗ trợ cấu hình -javaagent từ startup không.
- Pin đúng version của framework và agent.
- Tránh thêm -XX:+EnableDynamicAgentLoading vào mọi môi trường chỉ để ẩn cảnh báo.
- Chỉ bật dynamic loading khi deployment thực sự cần và policy cho phép.

### 15.3. Kiểm thử nhiều agent

Nếu test runtime có JaCoCo, Byte Buddy, Mockito inline và agent nội bộ, ghi nhận thứ tự -javaagent. Test riêng:
- Từng agent một.
- Tổ hợp agent theo thứ tự production.
- Retransform sau khi nhiều transformer đã chạy.
- Class do custom class loader định nghĩa.
- Test forked JVM khác với IDE runner nếu sản phẩm dùng cả hai.

Thứ tự transformer có thể thay đổi bytecode đầu vào của transformer tiếp theo. Không dùng một kết quả đơn lẻ từ môi trường IDE để kết luận Maven/Gradle forked test cũng hoạt động như vậy.

## 16. JDK 27: Các test bổ sung cho profiler và diagnostic agent

Ngoài class major 71, nên thêm các test sau:

1. **Compact Object Headers:** chạy profiler/JVMTI agent trên cấu hình mặc định JDK 27; kiểm tra không giả định object header layout nội bộ.
2. **G1 mặc định:** xác nhận event/metric GC được thu thập đúng khi không truyền collector flag.
3. **JFR redaction:** test báo cáo với recording đã che command-line arguments, environment và initial system properties.
4. **Serviceability Agent:** xóa dependency vào clhsdb printmdo, dùng API/command còn được hỗ trợ.
5. **Security properties:** dùng jcmd VM.security_properties khi cần chẩn đoán cấu hình security runtime.
6. **Class-file API:** xác nhận ClassFile.latestMajorVersion() là 71 trên JDK 27 và parser xử lý class file major 71.
7. **Preview:** kiểm tra class file preview Java 27 trên JDK 27 với --enable-preview; không dùng class file preview Java 26 làm fixture tương đương.

Nếu agent sử dụng HotSpot internal structures hoặc native access, hãy test trên đúng vendor/architecture production. Java SE API có thể ổn định trong khi internal implementation details của HotSpot thay đổi giữa các release.

## 17. Bảo đảm chất lượng khi viết transformer

Một transformer tốt cần tuân thủ các nguyên tắc:

- **Nhanh:** callback có thể chạy trong đường class loading; tránh network I/O, chờ lock lâu hoặc scan toàn bộ classpath.
- **Không re-enter chính class đang transform:** tránh load dependency khiến class circularity.
- **Có filter:** giới hạn package/class cần xử lý, tránh instrument JDK và framework không cần thiết.
- **Không mutate input:** luôn tạo output bytes mới khi có thay đổi.
- **Có kiểm soát lỗi:** ghi log có giới hạn, không để một lỗi parser làm mất dấu lỗi transform.
- **Idempotent:** retransform không chèn lặp cùng một instrumentation.
- **Loader-aware:** không lưu trạng thái chỉ theo tên class.
- **Module-aware:** phân biệt module readability với bytecode validity.
- **Không sửa schema trái phép:** tôn trọng redefine/retransform restrictions.
- **Có kill switch:** cho phép tắt một nhóm instrumentation nếu gặp lỗi production.

Nếu dùng ASM, ClassWriter.COMPUTE_FRAMES có thể cần resolve hierarchy để tính common superclass. Với custom class loader hoặc dependency không có trong tool classpath, việc resolve có thể sai hoặc thất bại. Hãy override resolver phù hợp hoặc dùng Class-File API/strategy tương thích với môi trường đó.

## 18. Security và độ tin cậy của agent

Agent chạy trong process của ứng dụng và có quyền thay đổi bytecode. Một agent không đáng tin có thể:
- Thay đổi logic xác thực hoặc authorization.
- Đọc dữ liệu nhạy cảm.
- Chèn network call hoặc ghi dữ liệu ra ngoài.
- Làm hỏng class file và gây crash.
- Can thiệp vào profiler/monitoring khác.

Vì vậy:
- Chỉ nạp agent từ nguồn đã xác minh.
- Pin version, checksum và chữ ký artifact.
- Theo dõi dependency transitive và cập nhật security fix.
- Không cho client bên ngoài tùy ý chỉ định agent path.
- Giới hạn agent có quyền truy cập file/network theo deployment policy.
- Test malformed class file, file lớn bất thường, nested attribute và dữ liệu đầu vào không tin cậy.
- Không bật debug chi tiết chứa dữ liệu production nhạy cảm ngoài thời gian chẩn đoán.

Các công cụ parse class file nhận input từ plugin, build artifact hoặc người dùng cũng cần bảo vệ khỏi malformed input và resource exhaustion. Cập nhật library parser và giới hạn kích thước/độ sâu xử lý là một phần của kiểm thử bảo mật.

## 19. Lỗi phổ biến và hướng tìm nguyên nhân

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| UnsupportedClassVersionError | Runtime không hỗ trợ class major/minor | javap -verbose, kiểm tra JDK target |
| Parser báo unsupported class version | Bytecode library quá cũ | Kiểm tra release notes/version matrix |
| VerifyError | Stack map frame, operand stack hoặc type flow sai | -Xverify:all, javap -c -v, verifier API |
| ClassFormatError | Class file output malformed | Parse lại output, kiểm tra constant pool/attributes |
| NoClassDefFoundError | Agent helper không visible với class loader đích | Kiểm tra loader, bootstrap search, module graph |
| ClassCastException dù tên class giống nhau | Hai defining class loader khác nhau | Log class loader và module của hai class |
| IllegalAccessError/InaccessibleObjectException | Module/package chưa export/open | Kiểm tra module graph và quyền reflection |
| Transformer không được gọi lại | canRetransform false hoặc capability không hỗ trợ | Manifest và isRetransformClassesSupported() |
| UnsupportedOperationException khi retransform | Capability chưa bật/không hỗ trợ | Manifest, provider và instrumentation flags |
| Cảnh báo dynamic agent loading | Test/framework đang attach sau startup | Tìm agent JAR và chuyển sang -javaagent nếu phù hợp |
| Agent không attach trong runtime image | Thiếu module jdk.attach, provider hoặc quyền OS | Kiểm tra image modules và process permissions |
| ClassCircularityError/LinkageError | Transformer load class đang transform hoặc dependency vòng | Giảm logic trong callback, kiểm tra loader |
| Instrumentation bị chèn lặp | Transformer không idempotent | Test retransform nhiều lần |
| Chỉ lỗi trên JDK 27 | Class major 71 hoặc runtime change mới | Chạy fixture JDK 27, kiểm tra release notes |
| Lỗi chỉ xảy ra trong multi-release JAR | Tool chỉ xử lý root entries | javap --multi-release, kiểm tra META-INF/versions |
| JFR thiếu command line/environment | JDK 27 redaction mặc định | Kiểm tra redaction policy và event schema |
| Profiler sai object size | Phụ thuộc object layout HotSpot cũ | Test compact object headers, dùng API được hỗ trợ |
| Lỗi chỉ trên Gradle/Maven test | Forked JVM khác agent/dependency order | In test JVM args và dependency tree |

## 20. Checklist review một thư viện bytecode/agent

- [ ] Đã xác định baseline JDK và JDK hiện hành được hỗ trợ?
- [ ] Đã xác nhận major/minor class file đầu vào và đầu ra?
- [ ] Có test class file Java 27 major 71?
- [ ] Có test preview class file theo đúng release?
- [ ] Library parser/writer có version matrix bao phủ class file mục tiêu?
- [ ] Có kiểm tra release notes và security fixes của ASM/Byte Buddy/Javassist/JaCoCo?
- [ ] Các module ASM cùng version?
- [ ] Đã kiểm tra dependency tree của cả compile và test runtime?
- [ ] Agent có manifest và entry point đúng?
- [ ] Startup agent chạy bằng -javaagent?
- [ ] Dynamic attach được phát hiện bằng test -XX:-EnableDynamicAgentLoading?
- [ ] Transformer không mutate input bytes?
- [ ] Transformer trả null khi không thay đổi?
- [ ] Transformer xử lý exception/logging rõ?
- [ ] Có test nhiều transformer cùng đăng ký?
- [ ] Có test redefine/retransform và schema restrictions?
- [ ] Có test custom class loader, bootstrap loader và module path?
- [ ] Có test multi-release JAR?
- [ ] Có kiểm tra javap, jdeps --jdk-internals, jar --describe-module?
- [ ] Class file output được parse/verify lại?
- [ ] Class file output được load với -Xverify:all?
- [ ] Có behavioral test sau transform?
- [ ] Có test JDK 27 compact object headers, G1 và JFR redaction nếu tool liên quan?
- [ ] Không phụ thuộc lệnh diagnostic hoặc HotSpot internal đã bị loại bỏ?
- [ ] Agent artifact được xác minh nguồn gốc và version?
- [ ] CI ghi lại JDK vendor/version, JVM flags và agent order?

## 21. Bộ kiểm thử thực hành

Một pipeline nhỏ có thể tổ chức như sau:

~~~text
Source / test fixture
       |
       v
Compile on each supported release
       |
       v
Inspect class version and dependencies
       |
       v
Parse with bytecode library / Class-File API
       |
       v
Transform through agent or build-time tool
       |
       v
Parse and verify transformed bytes
       |
       v
Run on target JDK with -Xverify:all
       |
       v
Behavioral + retransformation + module/loader tests
       |
       v
Record JDK, library versions, JVM flags and results
~~~

Một pipeline CI tốt cần lưu lại:
- JDK vendor, full version string và architecture.
- Compiler release và preview flags.
- Phiên bản ASM/Byte Buddy/Javassist/JaCoCo.
- Agent startup arguments và thứ tự agent.
- Class-file major/minor của fixture và output.
- Verifier result, test result và JFR/diagnostic artifacts khi có lỗi.

Không chỉ test một build xanh. Khi nâng JDK hoặc bytecode library, hãy chạy lại fixture cũ và fixture mới để phát hiện regression tương thích ngược và hỗ trợ class file mới.

## 22. Câu hỏi ôn tập

1. Vì sao tool runtime JDK và class-file version đầu vào là hai trục tương thích khác nhau?
2. JDK 27 dùng class-file major version bao nhiêu?
3. Minor version 65535 biểu thị điều gì với class file hiện đại?
4. Vì sao class file preview Java 26 không thể load bằng JDK 27 chỉ nhờ --enable-preview?
5. Class-File API chuẩn được final từ JDK nào?
6. ClassFile.latestMajorVersion() trả về điều gì?
7. ClassFileTransformer phải làm gì với classfileBuffer?
8. Khi nào transformer nên trả null?
9. premain và agentmain khác nhau ở thời điểm khởi động nào?
10. -javaagent khác dynamic attach thế nào?
11. JEP 451 thay đổi điều gì với dynamic agent loading?
12. Vì sao nên thử test suite với -XX:-EnableDynamicAgentLoading?
13. Can-Retransform-Classes có vai trò gì trong agent manifest?
14. Vì sao retransform nhiều lần cần kiểm tra idempotence?
15. Vì sao cùng binary class name nhưng khác class loader có thể là hai kiểu khác nhau?
16. Module opens có thay thế bytecode verifier không?
17. Vì sao javap -verbose hữu ích khi điều tra UnsupportedClassVersionError?
18. jdeps --jdk-internals phát hiện loại dependency nào?
19. Multi-release JAR lưu class file theo release ở thư mục nào?
20. Vì sao phải chạy class file output bằng JVM thật sau khi parser verify?
21. Compact Object Headers mặc định trong JDK 27 có thể ảnh hưởng profiler nào?
22. JFR redaction trong JDK 27 cần được đưa vào test nào?
23. Vì sao không nên chỉ dùng class file Java 17 để kiểm thử tool hỗ trợ JDK 27?
24. Khi nào nên dùng Class-File API thay cho ASM/Byte Buddy?
25. Khi nào native/JVMTI agent cần thêm ma trận OS/CPU architecture?

**Gợi ý đáp án:** (1) Runtime API và parser input format có thể hỗ trợ khác nhau. (2) 71. (3) Class file dùng preview features. (4) Preview class file gắn với release cụ thể. (5) JDK 24. (6) Major version mới nhất runtime hỗ trợ. (7) Coi input là chỉ đọc, không mutate. (8) Khi không transform. (9) premain trước application main; agentmain sau startup hoặc theo Launcher-Agent-Class. (10) Startup agent được nạp bằng JVM option; dynamic attach kết nối JVM đang chạy. (11) Cảnh báo dynamic loading và chuẩn bị cho default denial trong tương lai. (12) Để phát hiện dependency ẩn vào dynamic attach. (13) Khai báo capability retransformation. (14) Tránh chèn instrumentation lặp. (15) Class identity gồm binary name và defining loader. (16) Không. (17) Hiển thị class version và bytecode. (18) Tham chiếu static tới JDK internal APIs. (19) META-INF/versions/N. (20) Runtime verifier/linker có thể phát hiện lỗi khác parser. (21) Profiler đọc layout object nội bộ. (22) Kiểm tra event/report khi argument và environment đã bị che. (23) Không có class file major 71 hay cấu trúc mới. (24) Khi target JDK 24+ và cần API chuẩn. (25) Vì native agent phụ thuộc ABI, OS và architecture.

**Kết luận:** Kiểm thử công cụ JVM trên JDK hiện hành cần kiểm tra đồng thời class-file format, verifier, transformer lifecycle, agent loading, module/class loader, multi-release packaging và thay đổi runtime. JDK 27 đưa class-file major lên 71 và có những thay đổi liên quan trực tiếp tới công cụ như compact object headers, G1 mặc định, JFR redaction và thay đổi Serviceability Agent. Dùng Class-File API chuẩn từ JDK 24 khi phù hợp; với ASM, Byte Buddy, Javassist và JaCoCo, chọn version có hỗ trợ release mục tiêu và test trên đúng runtime production. Chỉ kết luận một tool tương thích khi class file sau biến đổi được JVM xác minh, chạy đúng hành vi và vượt qua ma trận CI đã công bố.

## Tài liệu tham khảo hiện hành

- **JDK 27 Release Notes** — các thay đổi runtime, JFR, G1, Compact Object Headers và Serviceability Agent: https://www.oracle.com/java/technologies/javase/27-relnote-issues.html
- **Java SE 27 API Specification**: https://docs.oracle.com/en/java/javase/27/docs/api/
- **Java SE 27 JVM Specification, Class File Format** — major/minor version, preview class file và verifier: https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-4.html
- **ClassFile API, Java SE 27** — parse, verify, transform, generate và latestMajorVersion: https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/ClassFile.html
- **Class-File API (JEP 484)** — API chuẩn từ JDK 24: https://openjdk.org/jeps/484
- **java.lang.instrument, Java SE 27** — startup/dynamic agent, manifest và instrumentation: https://docs.oracle.com/en/java/javase/27/docs/api/java.instrument/java/lang/instrument/package-summary.html
- **ClassFileTransformer, Java SE 27** — transform contract, transformer order và retransform behavior: https://docs.oracle.com/en/java/javase/27/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
- **Attach API, Java SE 27** — jdk.attach và VirtualMachine: https://docs.oracle.com/en/java/javase/27/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html
- **JEP 451** — Prepare to Disallow the Dynamic Loading of Agents: https://openjdk.org/jeps/451
- **JEP 484** — Class-File API: https://openjdk.org/jeps/484
- **JDK 27 javap command**: https://docs.oracle.com/en/java/javase/27/docs/specs/man/javap.html
- **JDK 27 jdeps command**: https://docs.oracle.com/en/java/javase/27/docs/specs/man/jdeps.html
- **JAR File Specification** — multi-release JAR và META-INF/versions: https://docs.oracle.com/en/java/javase/27/docs/specs/jar/jar.html
- **ASM Versions** — release notes và class-file support: https://asm.ow2.io/versions.html
- **Byte Buddy Release Notes** — version compatibility và ASM integration: https://github.com/raphw/byte-buddy/blob/master/release-notes.md
- **JaCoCo Change History** — Java 27 support: https://www.jacoco.org/jacoco/trunk/doc/changes.html
