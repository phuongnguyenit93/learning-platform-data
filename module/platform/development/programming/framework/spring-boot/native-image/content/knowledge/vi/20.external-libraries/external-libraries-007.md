# Khi nào cần nâng cấp, thay thư viện hoặc thay cách tích hợp

## 1. Vì sao cần đánh giá lại thư viện khi chuyển sang Native Image?

Một ứng dụng Spring Boot có thể hoạt động ổn định trên JVM nhưng gặp lỗi khi build hoặc chạy bằng GraalVM Native Image. Nguyên nhân thường liên quan đến cách thư viện sử dụng reflection, proxy, resource, serialization, JNI, classloader hoặc khởi tạo class. Một số thư viện được thiết kế dựa trên khả năng khám phá và nạp mã động của JVM, trong khi Native Image phân tích tập mã có thể truy cập ở build time theo mô hình closed-world.

Khi gặp vấn đề, không nên lập tức thay toàn bộ thư viện hoặc thêm hàng loạt RuntimeHints. Cần xác định thư viện có hỗ trợ Native Image ở version đang dùng hay không, vấn đề có được giải quyết bằng metadata chính thức không, và chi phí duy trì workaround có hợp lý không.

Bài học này đưa ra quy trình quyết định **khi nào nâng cấp, thay thư viện hoặc thay cách tích hợp** trong module **SPRING_BOOT_NATIVE_IMAGE**. Mục tiêu là chọn phương án ít rủi ro, có thể kiểm thử và duy trì lâu dài, đồng thời bảo đảm chức năng ứng dụng, thời gian khởi động và mức sử dụng bộ nhớ.

## 2. Bắt đầu từ lỗi có thể tái hiện

Trước khi thay dependency, hãy tạo một trường hợp lỗi tối thiểu:

- Ghi lại phiên bản Spring Boot, Spring Framework, JDK/GraalVM và Native Build Tools.
- Xác định thư viện trực tiếp hoặc bắc cầu có liên quan.
- Ghi stack trace đầy đủ và pha xảy ra lỗi: AOT, Native Image compilation hay runtime.
- Xác định thao tác gây lỗi: reflection, resource loading, proxy, serialization, JNI, class initialization hay dynamic class loading.
- Tạo test nhỏ gọi đúng đường đi bị lỗi trên JVM và native.
- Xác nhận lỗi không phải do cấu hình build, ABI, thư viện hệ điều hành hoặc file runtime.

Ví dụ: `ClassNotFoundException` có thể do reflection target chưa được đăng ký, nhưng cũng có thể do tên class sai hoặc dependency không nằm trên classpath. `UnsatisfiedLinkError` thường cần kiểm tra native library, architecture và ABI; nâng Spring Boot có thể không liên quan.

Một lỗi chỉ xuất hiện trên native là bằng chứng cần điều tra, chưa phải bằng chứng thư viện hoàn toàn không tương thích.

## 3. Phân loại nguyên nhân trước khi chọn phương án

| Nhóm nguyên nhân | Dấu hiệu thường gặp | Hướng xử lý ban đầu |
|---|---|---|
| Version cũ chưa hỗ trợ Native Image | Release mới có native metadata hoặc AOT integration | Kiểm tra release notes và nâng cấp |
| Thiếu reachability metadata | Reflection/proxy/resource không được giữ | Kiểm tra metadata chính thức, bổ sung RuntimeHints |
| Cách dùng thư viện không phù hợp | Dynamic class loading, plugin JAR runtime, compiler | Thay cách tích hợp hoặc tách service |
| Cấu hình Spring AOT sai | Bean/condition/profile khác dự kiến | Kiểm tra AOT inputs và configuration |
| Mismatch nền tảng | Sai libc, loader, architecture hoặc shared library | Đồng bộ builder/runtime/toolchain |
| Bug của thư viện hoặc framework | Có thể tái hiện trên native với cấu hình hợp lệ | Kiểm tra issue/release, nâng cấp hoặc báo upstream |
| Bug trong ứng dụng | Sai reflection signature, resource path hoặc lifecycle | Sửa code và regression test |

Phân loại giúp tránh sửa sai tầng. Ví dụ, thêm reflection hints không thể làm một JAR mới xuất hiện trong native executable sau khi build; thay thư viện JSON cũng không sửa được file config bị mount sai.

## 4. Khi nào nên nâng cấp thư viện?

Nâng cấp là lựa chọn đầu tiên nên đánh giá khi phiên bản mới có một trong các cải thiện sau:

- Hỗ trợ Spring AOT hoặc GraalVM Native Image chính thức.
- Bổ sung reachability metadata cho reflection, proxy, resource hoặc serialization.
- Sửa bug class initialization, JNI hoặc dynamic access.
- Loại bỏ API đã deprecated hoặc cơ chế không tương thích.
- Tương thích với JDK, Spring Boot và Native Build Tools version đang dùng.
- Có test native trong CI hoặc tài liệu xác nhận phạm vi hỗ trợ.

Không chỉ nhìn số version. Đọc release notes, migration guide, issue liên quan và dependency graph. Một bản nâng cấp lớn có thể thay đổi API, default behavior, serialization format hoặc transitive dependencies.

Ví dụ, nếu một thư viện serializer ở version cũ yêu cầu reflection hints thủ công nhưng version mới cung cấp metadata Native Image đã kiểm thử, nâng cấp có thể giảm cấu hình riêng của ứng dụng. Tuy nhiên cần xác minh metadata đó bao phủ đúng module/tính năng đang dùng, không chỉ happy path.

## 5. Kiểm tra tương thích theo toàn bộ dependency chain

Thư viện trực tiếp có thể hỗ trợ Native Image nhưng dependency bắc cầu của nó lại dùng reflection hoặc JNI không được hỗ trợ. Vì vậy, kiểm tra dependency graph:

Maven:

```bash
./mvnw dependency:tree
```

Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Ghi lại:

- Dependency trực tiếp và transitive.
- Version được resolve thực tế.
- Dependency bị conflict hoặc override.
- Optional module được bật trong runtime.
- Native library/resource đi kèm.
- Metadata reachability được đóng gói trong artifact nào.

Không nên nâng riêng một transitive dependency bằng cách ép version nếu thư viện cha chưa hỗ trợ version đó. Kiểm tra BOM, dependency management và compatibility matrix của framework trước khi override.

## 6. Tìm metadata Native Image có sẵn

Trước khi tự viết hints, kiểm tra thư viện có cung cấp metadata chính thức hay không. Nhiều thư viện hiện đại đóng gói reachability metadata hoặc tích hợp Spring RuntimeHints để khai báo reflection, resource, proxy và serialization.

Các nguồn nên xem:

- Tài liệu chính thức của thư viện về GraalVM Native Image.
- Release notes và migration guide.
- Repository metadata của thư viện.
- GraalVM Reachability Metadata Repository nếu thư viện có đóng góp.
- Spring Boot/Spring Framework support documentation.
- Native integration tests của upstream.

Metadata có thể được phân phối trong JAR theo cơ chế và định dạng phụ thuộc GraalVM version. Không tự sao chép file metadata từ version khác hoặc đặt vào thư mục tùy ý rồi giả định compiler sẽ đọc.

Nếu thư viện đã có metadata, xác minh build tool và GraalVM version đang dùng nhận diện nó. Kiểm tra native image build log, test thư viện và đường đi ứng dụng thật.

## 7. Khi nào nên bổ sung RuntimeHints của ứng dụng?

Tự bổ sung hints phù hợp khi:

- Thư viện có API reflection nhưng không thể cung cấp metadata cho đúng class ứng dụng.
- Ứng dụng chọn class/member trong một tập hữu hạn đã biết.
- Resource classpath được chọn theo tên động nhưng tập file cố định.
- Ứng dụng tự tạo JDK proxy từ interface đã biết.
- Native code gọi callback vào type Java được xác định trước.

Ví dụ registrar:

```java
final class PartnerSdkHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.reflection().registerType(
                PartnerPayload.class,
                MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS,
                MemberCategory.INVOKE_PUBLIC_METHODS
        );

        hints.resources().registerPattern(
                "partner/templates/*.json");
    }
}
```

Gắn registrar:

```java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(PartnerSdkHints.class)
class PartnerSdkConfiguration {
}
```

Ví dụ minh họa; hãy đăng ký đúng constructor/method/resource mà SDK thực sự dùng và kiểm tra API của Spring Framework version. Không đăng ký mọi member hoặc toàn bộ resource package chỉ để làm build pass.

RuntimeHints là metadata cho type/resource đã biết. Nó không làm Native Image có thể nạp class plugin mới từ JAR tùy ý sau khi executable được phát hành.

## 8. Khi nào nên thay cách tích hợp nhưng giữ nguyên thư viện?

Đôi khi thư viện tương thích native nếu dùng theo một đường đi tĩnh, nhưng cách tích hợp hiện tại lại phụ thuộc dynamic discovery. Có thể giữ dependency và thay cách gọi:

| Cách tích hợp hiện tại | Cách tích hợp nên xem xét |
|---|---|
| Tìm implementation bằng quét package lúc runtime | Đăng ký implementation tường minh |
| Chọn class bằng tên chuỗi bất kỳ | Registry hữu hạn gồm các class đã biết |
| Tạo proxy tùy ý | Dùng interface/proxy combination ổn định và proxy hints |
| Tìm resource theo tên ghép động | Đăng ký resource pattern hoặc tập file cố định |
| Tự tạo object bằng reflection | Dùng constructor/factory injection khi có thể |
| Nạp plugin JAR sau deploy | Đưa plugin vào build inputs hoặc tách plugin host |
| Compile rule thành Java class lúc runtime | Dùng DSL/interpreter hoặc build-time generation |

Thay cách tích hợp thường ít tốn kém hơn thay thư viện nếu phần lớn chức năng vẫn phù hợp. Tuy nhiên cần giữ nguyên behavior public contract, xử lý lỗi và hiệu năng của nghiệp vụ.

## 9. Khi nào nên thay thư viện?

Nên đánh giá thay thư viện khi có nhiều điều kiện cùng xuất hiện:

- Upstream không có kế hoạch hoặc cam kết hỗ trợ Native Image.
- Lỗi nằm trong thiết kế cốt lõi như dynamic class definition hoặc runtime compiler.
- Workaround yêu cầu metadata rộng, khó kiểm thử và dễ vỡ mỗi lần nâng version.
- Thư viện không còn được duy trì hoặc có rủi ro bảo mật.
- Có thư viện thay thế đáp ứng chức năng, license, hiệu năng và native support tốt hơn.
- Chi phí migration có thể kiểm soát bằng adapter và contract tests.

Không thay chỉ vì một stack trace khó hiểu. Trước tiên xác định tính năng thực tế đang sử dụng; nhiều thư viện có module optional hoặc mode tĩnh có thể đáp ứng use case mà không cần thay toàn bộ.

## 10. Tiêu chí chọn thư viện thay thế

Đánh giá ứng viên theo các tiêu chí có thể kiểm chứng:

| Tiêu chí | Câu hỏi |
|---|---|
| Native support | Có tài liệu/metadata và test Native Image không? |
| Spring integration | Có Spring AOT/RuntimeHints phù hợp không? |
| API fit | Có đáp ứng use case hiện tại mà không viết nhiều adapter không? |
| Maintenance | Release gần đây, issue được xử lý, có chính sách support không? |
| Compatibility | Hợp JDK, Spring Boot, GraalVM và license của dự án không? |
| Security | Có lịch sử CVE, quy trình vá và dependency an toàn không? |
| Performance | Latency, throughput, allocation và RSS có phù hợp không? |
| Migration | Có thể chuyển dần và rollback không? |
| Operations | Logging, metrics, tracing và cấu hình có phù hợp không? |

Chạy benchmark bằng workload thực tế. Không chọn thư viện chỉ vì trang chủ tuyên bố “GraalVM compatible”; cần test đúng API, module và phiên bản đang sử dụng.

## 11. Dùng adapter để giảm ảnh hưởng khi thay thư viện

Đặt interface nội bộ giữa nghiệp vụ và thư viện ngoài:

```java
public interface DocumentRenderer {
    byte[] render(RenderRequest request);
}
```

Implementation hiện tại:

```java
@Component
class LegacyDocumentRenderer implements DocumentRenderer {
    @Override
    public byte[] render(RenderRequest request) {
        // Gọi thư viện hiện tại
        return new byte[0];
    }
}
```

Implementation thay thế:

```java
@Component
class NativeFriendlyDocumentRenderer implements DocumentRenderer {
    @Override
    public byte[] render(RenderRequest request) {
        // Gọi thư viện tương thích Native Image
        return new byte[0];
    }
}
```

Ví dụ phần thân chỉ là placeholder; trong ứng dụng thật cần triển khai và xử lý exception cụ thể. Business service chỉ phụ thuộc `DocumentRenderer`, không phụ thuộc SDK trực tiếp.

Adapter giúp:
- Giới hạn thay đổi vào một module.
- Viết contract test độc lập với thư viện.
- Chạy hai implementation song song trong giai đoạn migration nếu an toàn.
- Chuẩn hóa error model và logging.
- Rollback bằng cấu hình/bean selection nếu cả hai implementation đã được đóng gói.

Nếu dùng `@ConditionalOnProperty` để chọn adapter, nhớ rằng condition có thể ảnh hưởng bean graph trong Spring AOT. Nếu muốn chọn lúc runtime trong cùng native binary, đăng ký các implementation cần thiết và dùng selector runtime thay vì loại bean ở build time.

## 12. So sánh ba phương án: nâng cấp, thay thư viện, thay cách tích hợp

| Phương án | Chọn khi | Lợi ích | Chi phí/rủi ro |
|---|---|---|---|
| Nâng cấp thư viện | Upstream đã sửa lỗi/thêm native metadata | Giữ API quen thuộc, ít thay đổi nghiệp vụ | Breaking changes, transitive dependency |
| Thay cách tích hợp | Thư viện dùng được nếu bỏ đường dynamic không cần thiết | Giữ dependency, giảm phạm vi migration | Adapter/registry code, cần kiểm thử đường đi mới |
| Thay thư viện | Thiết kế cốt lõi không phù hợp hoặc maintenance kém | Loại bỏ giới hạn dài hạn | Migration, behavior/performance khác, license |

Có thể kết hợp các phương án. Ví dụ nâng SDK lên version mới, đồng thời thay plugin discovery bằng registry tĩnh. Nếu không có version nào hỗ trợ use case dynamic, tách năng lực đó sang JVM service có thể hợp lý hơn thay bằng thư viện khác nhưng vẫn cùng giới hạn.

## 13. Đánh giá tác động tới Spring AOT và Native Image

Mỗi thay đổi dependency hoặc cách tích hợp cần kiểm tra lại:

- Bean registration và conditional configuration.
- Proxy/interface combination.
- Reflection, JNI và serialization hints.
- Classpath resource patterns.
- Class initialization policy.
- Native library architecture/ABI.
- Script engine, classloader và dynamic compilation.
- Buildpack/runtime image và shared libraries.

Không giả định metadata cũ vẫn đúng sau nâng version. Một version mới có thể thêm hints, đổi package/class hoặc thay behavior. Ngược lại, bỏ một thư viện có thể khiến RuntimeHints tự viết trước đó trở nên thừa; cần loại bỏ metadata không còn dùng sau khi test xác nhận.

## 14. Quy trình migration có thể rollback

Một quy trình an toàn:

1. **Baseline:** lưu test results, dependency tree, native build log, startup/RSS và behavior hiện tại.
2. **Tái hiện:** tạo test nhỏ cho tính năng lỗi trên JVM và native.
3. **Research:** kiểm tra upstream release, metadata, issue và compatibility.
4. **Chọn phương án:** nâng version, thay cách tích hợp, thay thư viện hoặc tách service.
5. **Adapter/contract:** giữ API nội bộ ổn định và viết contract tests.
6. **Thử nghiệm cô lập:** thay một dependency hoặc một đường gọi mỗi lần.
7. **Native validation:** chạy Spring AOT, build executable và test trong runtime container.
8. **Regression:** chạy toàn bộ test suite và so sánh output.
9. **Benchmark:** đo startup, RSS, throughput và latency bằng cùng workload.
10. **Rollout:** phát hành canary, theo dõi metrics/log và giữ phương án rollback.

Không thay nhiều thư viện cùng lúc nếu chưa có lý do. Thay từng phần giúp xác định tác động và giảm thời gian truy tìm regression.

## 15. Kiểm thử tương thích cho thư viện ngoài

Một compatibility suite nên bao phủ đúng tính năng mà ứng dụng dùng:

| Nhóm test | Ví dụ |
|---|---|
| API behavior | Kết quả nghiệp vụ và exception contract |
| Reflection | Constructor/method/field được truy cập động |
| Resource | Template/schema/message bundle |
| Proxy/AOP | Interface list, transaction/advice |
| Serialization | JSON, polymorphic type, custom serializer |
| Class initialization | Environment/file/network side effects |
| JNI | Library load, callback và architecture |
| Container | User, filesystem, shared library, config mount |
| Version compatibility | JDK/Spring/GraalVM/plugin versions |
| Performance | Startup, RSS, throughput và latency |

Chạy test JVM trước để xác nhận chức năng cơ bản, rồi native build/test. Nếu chỉ native fail, giữ fixture tối thiểu để điều tra. Nếu cả hai fail sau migration, có thể là breaking behavior của thư viện chứ không phải Native Image.

## 16. Các dấu hiệu không nên cố thêm hints

Nên dừng việc mở rộng hints và đánh giá thay đổi kiến trúc khi:

- Ứng dụng cần compile source Java tùy ý sau khi native executable đã phát hành.
- Cần nạp class/plugin không biết trước lúc build.
- Engine phụ thuộc runtime bytecode generation không có Native Image support.
- Metadata phải đăng ký không giới hạn theo dữ liệu người dùng.
- Hints rộng khiến image giữ một lượng lớn class/member và khó kiểm soát.
- Upstream xác nhận tính năng không được hỗ trợ trong Native Image.
- Workaround đụng sâu vào implementation nội bộ và dễ hỏng theo version.

Trong những trường hợp này, cân nhắc DSL/interpreter, build-time code generation, JVM worker/service hoặc process chuyên biệt. Chọn phương án theo yêu cầu cập nhật logic, bảo mật, latency và khả năng vận hành.

## 17. Bài thực hành: quyết định nâng cấp hay thay cách tích hợp

**Bối cảnh:** một SDK đối tác dùng reflection để tạo payload, đọc template từ classpath và có plugin discovery. JVM hoạt động, native build báo thiếu reflection/resource metadata; plugin mới được tải từ thư mục sau deploy.

**Bước 1 — Chia nhỏ tính năng.** Tạo ba test riêng: payload reflection, template loading và plugin discovery.

**Bước 2 — Kiểm tra version hiện tại.** Xem dependency tree, release notes và tài liệu Native Image của SDK.

**Bước 3 — Thử version mới.** Kiểm tra xem SDK có metadata reflection/resource chính thức và native tests không; chạy lại ba test.

**Bước 4 — Đánh giá plugin.** Xác định plugin có thể cố định trong build hay thực sự phải thêm sau deploy. Nếu tập plugin cố định, đưa vào build inputs và đăng ký type/hints.

**Bước 5 — Thử thay cách tích hợp.** Thay discovery bằng registry tĩnh cho các plugin đã biết; giữ SDK nếu các tính năng còn lại tương thích.

**Bước 6 — Đánh giá giới hạn còn lại.** Nếu yêu cầu nạp plugin mới sau phát hành vẫn bắt buộc, thử tách plugin host sang JVM service và xác định contract.

**Bước 7 — So sánh phương án.** Ghi chi phí migration, native build, image size, startup, RSS, latency, bảo mật và vận hành.

**Bước 8 — Chọn rollout.** Dùng adapter/contract test, canary và rollback để xác nhận behavior production.

Tiêu chí hoàn thành: có bằng chứng cho từng nguyên nhân, quyết định được giải thích bằng compatibility và chi phí, test JVM/native pass cho tính năng được hỗ trợ, giới hạn còn lại có phương án kiến trúc rõ ràng.

## 18. Kết luận

Khi một thư viện ngoài gặp vấn đề với Spring Boot Native Image, hãy phân loại nguyên nhân và xác minh phạm vi tính năng trước khi quyết định. **Nâng cấp** khi upstream đã cải thiện hỗ trợ native; **thay cách tích hợp** khi thư viện hoạt động tốt với tập type/resource/proxy biết trước; **thay thư viện** khi thiết kế, bảo trì hoặc hỗ trợ native không đáp ứng yêu cầu. Với nhu cầu compile/nạp mã tùy ý sau deploy, cân nhắc tách sang JVM service hoặc môi trường chuyên biệt.

Dùng adapter, contract tests, dependency analysis, native integration tests và benchmark để kiểm soát migration. Một quyết định tốt cần bảo đảm chức năng, khả năng bảo trì, bảo mật và chi phí vận hành, chứ không chỉ làm cho một lần native build thành công.
