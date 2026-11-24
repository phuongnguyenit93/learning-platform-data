# Đánh giá thư viện bên thứ ba trước khi dùng trong Native Image

## 1. Vì sao cần đánh giá dependency riêng?

Một ứng dụng Spring Boot có thể chạy ổn định trên JVM nhưng thất bại khi biên dịch hoặc chạy bằng GraalVM Native Image. Nguyên nhân đôi khi không nằm trong mã nguồn của ứng dụng mà đến từ thư viện bên thứ ba: thư viện dùng reflection theo tên runtime, sinh bytecode động, đọc resource theo pattern, nạp JNI library, khởi tạo static state phụ thuộc môi trường hoặc dựa vào API JVM không được hỗ trợ theo cách đang dùng.

Vì vậy, việc đánh giá dependency là một bước riêng trong quá trình chuẩn bị Native Image. Không nên chỉ nhìn vào việc thư viện có trên Maven Central, có phiên bản mới hay ứng dụng đã chạy được trên JVM. Cần kiểm tra khả năng hỗ trợ Native Image của đúng phiên bản, các metadata mà thư viện cung cấp, giới hạn runtime và những luồng nghiệp vụ thực sự được sử dụng.

Trong module **SPRING_BOOT_NATIVE_IMAGE**, mục tiêu là biên dịch ứng dụng Spring Boot bằng Spring AOT và GraalVM Native Image, kiểm thử tương thích, đóng gói container và đánh giá startup/bộ nhớ. Mỗi dependency quan trọng cần được phân loại và xác minh trong chính application module cùng toolchain sẽ phát hành.

## 2. Những rủi ro phổ biến trong thư viện bên thứ ba

| Kỹ thuật hoặc hành vi | Rủi ro với Native Image | Bằng chứng cần tìm |
|---|---|---|
| Reflection theo tên class/member | Static analysis không suy ra được mục tiêu | Runtime hints, reachability metadata, tài liệu native |
| Runtime bytecode generation | Cần sinh class mới sau khi build | AOT integration, pre-generated proxy hoặc giới hạn được công bố |
| ClassLoader tùy biến | Có thể nạp class không nằm trong image | Mô tả class loading và test native |
| Resource lookup động | Resource không được đưa vào executable | Resource hints, metadata hoặc resource pattern |
| JDK dynamic proxy | Tập interface proxy có thể chưa được khai báo | Proxy hints hoặc AOT contribution |
| Java serialization | Thiếu metadata cho kiểu và object graph | Serialization hints và round-trip test |
| JNI/native library | Thiếu thư viện hoặc sai OS/CPU/ABI | JNI metadata, binary artifacts, run-image requirements |
| Static initializer có side effect | Trạng thái build-time bị đóng vào image | Initialization guidance và diagnostic log |
| Instrumentation/agent | Phụ thuộc khả năng JVM runtime | Tài liệu hỗ trợ GraalVM cụ thể |
| Process hoặc shell invocation | Executable ngoài không có trong container | Runtime package, path và permission |

Không phải cứ thấy một kỹ thuật trong bảng là thư viện chắc chắn không tương thích. Nhiều thư viện đã có tích hợp AOT, metadata hoặc fallback phù hợp. Bảng này dùng để xác định câu hỏi cần trả lời và test cần chạy.

## 3. Bắt đầu từ đúng dependency graph

Đánh giá phải dựa trên dependency thực tế của application module, không chỉ file build ở root. Trong Gradle multi-project, chọn đúng project chứa Spring Boot application.

Ví dụ:

```bash
./gradlew :api-app:dependencies --configuration runtimeClasspath
```

Truy nguyên dependency:

```bash
./gradlew :api-app:dependencyInsight --dependency example-library --configuration runtimeClasspath
```

Với Maven:

```bash
./mvnw dependency:tree
```

Cần xác định:

- Dependency trực tiếp và transitive.
- Version thực sự được resolve, kể cả khi version được quản lý bởi BOM.
- Exclusions và dependency constraints.
- Scope/configuration, đặc biệt runtime classpath.
- Dependency chỉ dùng trong test so với dependency nằm trong artifact production.
- Platform-specific artifacts hoặc optional native modules.

Một thư viện có thể hoạt động trên JVM do class chỉ được dùng ở một endpoint hiếm. Vì vậy, dependency graph là điểm bắt đầu để kiểm tra, chưa phải bằng chứng đầy đủ về runtime compatibility.

## 4. Tìm tuyên bố hỗ trợ Native Image của nhà cung cấp

Đối với từng dependency quan trọng, kiểm tra tài liệu chính thức của đúng phiên bản:

1. Có mục Native Image/GraalVM/Spring AOT support không?
2. Hỗ trợ được cung cấp từ phiên bản nào?
3. Cần dùng artifact/classifier riêng hay dependency bổ sung không?
4. Có RuntimeHintsRegistrar, Spring AOT contribution hoặc reachability metadata không?
5. Có giới hạn về reflection, proxy, serialization, JNI, OS hoặc architecture không?
6. Có yêu cầu cấu hình build arguments hoặc initialization policy không?
7. Có test matrix cho GraalVM/Spring Boot/JDK version đang dùng không?

Tách rõ ba mức tuyên bố:

- **Có hỗ trợ chính thức**: tài liệu nêu rõ version và cách cấu hình.
- **Có metadata nhưng cần cấu hình**: thư viện cung cấp hints/metadata, ứng dụng phải kích hoạt hoặc bổ sung theo hướng dẫn.
- **Chưa xác minh**: không tìm thấy tuyên bố hoặc chỉ có báo cáo cộng đồng. Cần thử nghiệm trước khi đưa vào release.

Không suy ra rằng một thư viện hỗ trợ Native Image chỉ vì dependency của nó xuất hiện trong một ứng dụng native khác. Ứng dụng kia có thể dùng một code path nhỏ hơn hoặc tự bổ sung metadata riêng.

## 5. Kiểm tra metadata được đóng gói trong artifact

Một thư viện có thể cung cấp metadata cùng JAR để ứng dụng tiêu thụ không phải tự viết lại mọi hint. Các cơ chế thường gặp:

- Spring AOT contribution hoặc `RuntimeHintsRegistrar`.
- `META-INF/spring/aot.factories` để đăng ký registrar theo cơ chế Spring AOT phù hợp.
- GraalVM reachability metadata theo schema/định dạng được phiên bản Native Image hỗ trợ.
- Metadata service/provider hoặc resource cần thiết theo hướng dẫn của framework.

Kiểm tra nội dung JAR:

```bash
jar tf path/to/library.jar
```

Tìm các vị trí metadata thường gặp như `META-INF/spring/aot.factories`, metadata reachability của GraalVM, `META-INF/services`, resource và native binaries. Đường dẫn cụ thể thay đổi theo hệ sinh thái và phiên bản; không giả định mọi thư viện dùng cùng một cấu trúc.

Nếu metadata tồn tại, xác minh:

- File có nằm trong artifact version thực tế được resolve không?
- Class registrar được đóng gói và load được không?
- Key, schema và package có đúng với version framework/toolchain không?
- AOT log cho thấy registrar/contribution được phát hiện không?
- Metadata có bao phủ code path ứng dụng đang sử dụng không?

Có file metadata trong JAR không đồng nghĩa metadata đã được tiêu thụ thành công. Cần kiểm tra AOT/build output và test runtime.

## 6. Phân biệt Spring RuntimeHints với reachability metadata

Spring RuntimeHints là abstraction do Spring cung cấp để mô tả reflection, resource, proxy, serialization và các khả năng runtime khác. Spring AOT thu thập hints từ application và các integration được hỗ trợ.

GraalVM Native Image có reachability metadata riêng. Metadata này mô tả các phần cần giữ hoặc cách xử lý các hoạt động động theo schema của GraalVM. Spring và Native Image tích hợp với nhau theo phiên bản/toolchain.

| Cơ chế | Vai trò | Khi đánh giá thư viện |
|---|---|---|
| RuntimeHintsRegistrar | Thư viện đóng góp hints qua Spring AOT | Xác minh registrar được phát hiện |
| Spring AOT contribution | Thư viện can thiệp quá trình AOT theo API hỗ trợ | Kiểm tra version/API tương thích |
| GraalVM reachability metadata | Mô tả yêu cầu Native Image độc lập hoặc qua repository metadata | Kiểm tra schema và phân phối |
| Tracing Agent output | Gợi ý metadata từ code path đã quan sát trên JVM | Rà soát và kiểm thử bổ sung |

Không chuyển đổi thủ công tên API Spring thành JSON GraalVM nếu chưa đối chiếu schema. Không thêm cùng một metadata bằng nhiều cơ chế chỉ để tăng cơ hội build thành công; trước hết xác định nguồn nào được toolchain tiêu thụ.

## 7. Các nhóm tương thích cần kiểm tra riêng

### Reflection và class loading

Tìm các lời gọi như `Class.forName`, `getDeclaredMethod`, `getDeclaredConstructor`, `Field.get` và `setAccessible`. Hỏi thư viện có cung cấp hints cho class/member cụ thể không. Nếu class được chọn bằng dữ liệu runtime, cần xác định allowlist hoặc danh sách implementation có thể biết trước.

### Proxy và bytecode generation

Tìm JDK dynamic proxy, CGLIB, Byte Buddy, ASM hoặc instrumentation. Phân biệt proxy có thể được Spring AOT chuẩn bị với class được sinh tùy ý sau khi executable đã build. JDK proxy hints không thay thế khả năng sinh subclass/bytecode tùy biến.

### Resource và configuration

Kiểm tra template, schema, file SQL, message bundle và resource được đọc theo tên động. Xác minh resource có trong JAR và được đóng gói vào Native Image. File cấu hình/secret cần thay đổi theo môi trường nên được cấp ở runtime qua filesystem, environment hoặc secret manager.

### Serialization

Kiểm tra object graph, custom serialization hooks, proxy handler và metadata serialization. Ưu tiên DTO/snapshot có hợp đồng ổn định; tránh serialize Spring bean, connection hoặc proxy có infrastructure state.

### JNI và native library

Tìm native methods, `System.loadLibrary`, thư viện `.so`/`.dll`/`.dylib` và yêu cầu ABI. Xác minh binary đúng OS/CPU, thư viện bắc cầu và run image cuối cùng.

### Class initialization

Kiểm tra static initializer có đọc environment, thời gian, random state, file hoặc native library không. Dùng hướng dẫn chính thức về initialization policy; không áp dụng `--initialize-at-run-time` đại trà để che lỗi.

## 8. Phân biệt lỗi dependency với lỗi cấu hình ứng dụng

Khi native build hoặc runtime thất bại, xác định lớp lỗi trước:

| Triệu chứng | Nhóm cần kiểm tra |
|---|---|
| Class không tìm thấy | Runtime dependency graph, version, classloader |
| Constructor/method reflection lỗi | Reflection metadata và signature |
| Resource trả null | Resource path, JAR content và resource hints |
| Proxy không tạo được | Proxy strategy, AOT integration, interface/class constraints |
| Serialization lỗi | Object graph và serialization metadata |
| UnsatisfiedLinkError | JNI library, load path, ABI và JNI metadata |
| Giá trị static sai | Class initialization policy |
| AOT context thiếu bean | Profile, condition, classpath và build-time properties |
| Build OOM hoặc linker lỗi | Toolchain, builder resources và target platform |

Không khắc phục mọi lỗi bằng cách thêm reflection hints. Ví dụ, dependency không nằm trong runtime classpath không thể được sửa bằng RuntimeHints; class được tạo tùy ý bằng bytecode runtime cũng không được giải quyết chỉ bằng cách mở constructor.

## 9. Kiểm thử thư viện độc lập trước khi tích hợp sâu

Với dependency có rủi ro cao, tạo một ứng dụng mẫu nhỏ hoặc test module cô lập để kích hoạt đúng API đang dùng. Mục tiêu là phân biệt lỗi của thư viện với cấu hình phức tạp của ứng dụng lớn.

Một trình tự hữu ích:

1. Tạo một Spring Boot application tối giản với đúng version dependency.
2. Gọi API đại diện cho code path production.
3. Chạy test JVM và ghi nhận hành vi baseline.
4. Chạy Spring AOT với đúng JDK, profile và classpath.
5. Build Native Image.
6. Chạy executable và kích hoạt API đó.
7. Đóng gói container với run image production dự kiến.
8. Kiểm tra OS/architecture, resource, JNI library và permission.

Một smoke test chỉ khởi động context không đủ nếu dependency chỉ dùng khi xử lý request, chạy scheduled job hoặc thực hiện migration. Test phải kích hoạt chính tính năng mà ứng dụng sẽ dùng.

## 10. Kiểm tra version matrix

Khả năng tương thích phụ thuộc tổ hợp phiên bản, không chỉ riêng thư viện.

| Thành phần | Cần ghi nhận |
|---|---|
| Spring Boot | Version và plugin tương ứng |
| Spring Framework | Version được Boot quản lý |
| JDK | Vendor, version và toolchain |
| GraalVM Native Image | Distribution và version |
| Native Build Tools | Plugin version và cấu hình |
| Dependency | Artifact, resolved version và classifier |
| Builder/buildpack | Image digest và buildpack version nếu dùng CNB |
| Run image | Distribution, digest, libc và architecture |
| Target | OS, CPU architecture và ABI |

Dùng dependency management/BOM và Gradle dependency locking khi phù hợp để giảm khác biệt giữa developer và CI. Khi nâng một dependency, chạy lại các test native liên quan; không giả định metadata của version cũ áp dụng nguyên vẹn cho version mới.

## 11. Tạo báo cáo đánh giá dependency

Có thể duy trì một bảng trong pull request hoặc release record:

| Dependency | Resolved version | Kỹ thuật động | Metadata/support | Native test | Kết luận |
|---|---|---|---|---|---|
| Library A | … | Reflection | Registrar | Pass/Fail | Verified/Needs work |
| Library B | … | JNI | Vendor metadata | Pass/Fail | Verified/Needs work |
| Library C | … | Runtime proxy | Chưa rõ | Pass/Fail | Investigate |
| Library D | … | Resource lookup | Resource hints | Pass/Fail | Verified/Needs work |

Ghi rõ commit, build ID, JDK/GraalVM, OS/architecture, container digest và test report. Tránh chỉ ghi “native compatible” mà không nói version và code path nào đã được xác minh.

Có thể dùng trạng thái nội bộ:

- **Verified**: test native và container của code path cần thiết đã pass.
- **Verified with configuration**: pass sau khi thêm metadata/cấu hình đã ghi lại.
- **Limited**: chỉ một số feature/OS/architecture được hỗ trợ.
- **Unverified**: chưa có bằng chứng native đủ tin cậy.
- **Incompatible for current design**: phụ thuộc vào hành vi động không thể đáp ứng bằng cấu hình hiện tại.

Đây là cách phân loại quản lý dự án, không phải nhãn chính thức của GraalVM.

## 12. Cách xử lý khi thư viện chưa hỗ trợ đầy đủ

Ưu tiên các bước theo thứ tự:

1. Nâng lên phiên bản có hỗ trợ Native Image chính thức nếu tương thích chức năng.
2. Dùng artifact/classifier hoặc module native được nhà cung cấp hướng dẫn.
3. Kích hoạt Spring AOT contribution hoặc reachability metadata đã được cung cấp.
4. Bổ sung RuntimeHints cho phần ứng dụng tự kiểm soát và đã xác định rõ.
5. Chuyển từ reflection tùy ý sang registry/allowlist hoặc factory tĩnh.
6. Chuyển runtime proxy generation sang proxy/AOT artifacts có thể chuẩn bị trước.
7. Thay thư viện nếu code path bắt buộc không tương thích.
8. Nếu tính năng cần JVM dynamic loading/runtime compilation, tách tính năng đó sang process/service chạy JVM khi kiến trúc cho phép.

Không duy trì một tập hints rộng và khó hiểu chỉ để làm build qua được. Mỗi hint nên có lý do, test chứng minh và chủ sở hữu khi nâng version dependency.

## 13. Checklist trước khi chấp nhận dependency

- Đã xác định đúng runtime dependency graph và resolved version.
- Đã đọc tài liệu native support của đúng version.
- Đã kiểm tra reflection, proxy, resource, serialization, JNI và class initialization liên quan.
- Metadata có trong artifact và được Spring AOT/GraalVM thực sự tiêu thụ.
- Không phụ thuộc runtime bytecode generation hoặc class loading ngoài khả năng hỗ trợ.
- Native test kích hoạt code path production.
- Container test dùng đúng OS/architecture/run image.
- Có báo cáo version matrix, test result và artifact digest.
- Các hạn chế còn lại được ghi rõ trước khi release.

## 14. Câu hỏi tự kiểm tra

1. Vì sao một dependency chạy tốt trên JVM chưa đủ chứng minh tương thích Native Image?
2. Cần kiểm tra những nguồn metadata nào trong JAR của thư viện?
3. Khác nhau giữa RuntimeHintsRegistrar và GraalVM reachability metadata là gì?
4. Vì sao dependency phải được kiểm tra trên runtime classpath của đúng application module?
5. Khi nào reflection hints không thể giải quyết vấn đề runtime bytecode generation?
6. Vì sao JNI compatibility phụ thuộc OS, CPU architecture và ABI?
7. Một native smoke test cần kích hoạt những code path nào ngoài startup?
8. Những thông tin nào phải ghi lại để kết luận một phiên bản dependency đã được xác minh?

**Ghi nhớ:** đánh giá thư viện bên thứ ba theo đúng version, dependency graph và code path thực tế. Xác minh metadata AOT/reachability, reflection, proxy, resource, serialization, JNI và class initialization; sau đó build và chạy test trên native executable/container đích trước khi xem dependency là tương thích.
