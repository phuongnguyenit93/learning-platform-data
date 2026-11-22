# Phát hành plugin theo phiên bản, kiểm tra gói và giữ đường quay lại bản trước

## 1. Mục tiêu của quy trình phát hành plugin

Trong hệ thống Java hỗ trợ mở rộng lúc chạy, phát hành plugin không đơn giản là biên dịch một JAR rồi chép vào thư mục \`plugins/\`. Plugin là mã thực thi bên trong (hoặc bên cạnh) host, thường có hợp đồng API, dependency, cấu hình, quyền truy cập và vòng đời độc lập. Một bản phát hành chỉ nên được kích hoạt khi **artifact đúng phiên bản, hợp lệ, tương thích và có thể phục hồi** nếu gặp sự cố.

Ba mục tiêu cần đạt đồng thời:

1. **Phát hành có thể nhận diện và tái lập**: mỗi phiên bản có định danh, source revision, build settings, checksum/signature và artifact bất biến.
2. **Kiểm tra gói trước khi chạy**: kiểm tra manifest/descriptor, nội dung JAR, dependency, contract, class-file version, cấu hình và tính toàn vẹn.
3. **Có đường rollback được kiểm chứng**: bản trước được giữ sẵn cùng cấu hình tương thích; chuyển hướng request và dọn vòng đời không làm mất trạng thái hoặc đóng plugin đang xử lý.

\`\`\`text
Source + tests
      |
      v
Build artifact bất biến (pluginId, version)
      |
      v
Validate: hash/signature, descriptor, API/JVM, dependencies
      |
      v
Stage + smoke test + health check
      |
      v
Publish active registry (atomic switch)
      |
      +-- OK --> observe + drain old version
      |
      +-- FAILURE --> rollback sang release an toàn
                           |
                           v
                    observe + incident report
\`\`\`

Chú ý hai khái niệm: **deploy** là chuẩn bị bản phát hành có thể chạy; **activate** là cho request sử dụng bản đó. Tách hai bước giúp có chỗ kiểm tra và rollback trước khi ảnh hưởng người dùng.

## 2. Định danh và chính sách phiên bản

Một plugin nên có metadata tường minh, tối thiểu:

| Trường | Ví dụ | Mục đích |
|---|---|---|
| \`pluginId\` | \`csv-exporter\` | Định danh ổn định của plugin |
| \`pluginVersion\` | \`1.8.2\` | Định danh bản phát hành |
| \`requiredApiRange\` | \`[2.2.0,3.0.0)\` | Phạm vi API host được hỗ trợ |
| \`minimumJava\` | \`17\` | Runtime Java tối thiểu |
| \`entryPoint\` / \`service\` | \`com.example.spi.Exporter\` | Điểm mở rộng cần tìm |
| \`artifactSha256\` | SHA-256 xác thực riêng | Xác định đúng nội dung artifact |
| \`dependencies\` | Module/JAR + version | Xác định runtime closure |
| \`permissions\` | Capability được phép | Kiểm soát quyền truy cập |
| \`buildRevision\` | Commit/build ID | Truy vết nguồn phát hành |

Những trường này có thể nằm trong JAR manifest, descriptor JSON/YAML hoặc bản release metadata được bảo vệ. Đây là **quy ước của hệ thống plugin**, không phải các trường chuẩn bắt buộc của JPMS.

Với Semantic Versioning (\`MAJOR.MINOR.PATCH\`), tăng \`MAJOR\` khi phá hợp đồng tương thích, \`MINOR\` cho tính năng tương thích ngược và \`PATCH\` cho thay đổi sửa lỗi theo hợp đồng dự án. Tuy nhiên, chỉ dựa vào chữ số phiên bản không đủ chứng minh compatibility: một thay đổi hành vi, concurrency, serialization hoặc permission có thể phá chức năng dù method signature giữ nguyên.

**Không ghi đè một artifact đang mang cùng plugin ID + version bằng byte khác.** Việc dùng lại version khiến rollback, cache và truy vết trở nên không đáng tin. Nếu cần sửa bản \`1.8.2\`, phát hành \`1.8.3\` hoặc một định danh release mới theo policy.

## 3. Đóng gói artifact bất biến

Một layout phát hành minh họa:

\`\`\`text
releases/
└── csv-exporter/
    ├── 1.8.1/
    │   ├── csv-exporter.jar
    │   ├── release.json
    │   └── SHA256SUMS
    └── 1.8.2/
        ├── csv-exporter.jar
        ├── release.json
        └── SHA256SUMS
\`\`\`

Thư mục phiên bản là **immutable** sau khi được duyệt. Nếu repository/artifact storage hỗ trợ content-addressable storage thì khóa theo digest còn làm việc xác minh rõ hơn.

Ví dụ JAR manifest do host quy ước:

\`\`\`text
Manifest-Version: 1.0
Plugin-Id: csv-exporter
Plugin-Version: 1.8.2
Plugin-Api-Version: 2
Plugin-Class: com.example.csv.CsvExportPlugin
\`\`\`

Các thuộc tính \`Plugin-*\` không phải chuẩn JAR bắt buộc. Host tự định nghĩa cách parse và so sánh. Với JPMS, \`module-info.class\` và \`ModuleDescriptor.version()\` có thể mang metadata module version, nhưng JPMS không tự giải quyết semantic version ranges hay chọn bản mới nhất.

Khi build, nên cố định toolchain, dependencies và cấu hình; tạo SBOM/provenance khi quy trình tổ chức yêu cầu. **Reproducible build** giúp so sánh artifact từ cùng input, nhưng digest khác nhau chưa đủ chứng minh có xâm nhập và digest giống nhau không thay thế việc xác minh nhà phát hành.

## 4. Những gì phải kiểm tra trong gói plugin

Tách kiểm tra thành các cổng rõ ràng.

### Cổng A — Artifact và nguồn gốc

- Tệp có tồn tại, kích thước nằm trong giới hạn, định dạng JAR/ZIP có thể đọc?
- Đường dẫn đã chuẩn hóa, không trỏ ra ngoài vùng cho phép qua symlink/traversal?
- SHA-256 có khớp với digest lấy từ **nguồn đáng tin**?
- Chữ ký số/publisher identity có thỏa policy và danh sách tin cậy?
- Có biện pháp chống **TOCTOU**: artifact đã kiểm tra có phải chính byte sẽ được nạp?
- Archive có số entry, kích thước giải nén và tài nguyên xử lý phù hợp?

Đọc metadata chưa phải chạy code plugin, nhưng JAR vẫn là đầu vào không tin cậy. Để an toàn hơn, đưa artifact vào staging không cho sửa sau validation và chỉ nạp từ bản sao được phê duyệt.

### Cổng B — Metadata và compatibility

- \`pluginId\`, version, entry point, API range, Java minimum có hợp lệ?
- ID có trùng với plugin khác hoặc phiên bản không phù hợp chính sách?
- Host API nằm trong range plugin hỗ trợ và các capability cần thiết hiện có?
- Class-file major có được runtime hỗ trợ? Java 17 dùng major 61, Java 21 dùng major 65.
- Dependency closure có đầy đủ, version conflict và split-package/duplicate module name được xử lý?
- Shared API có cùng class identity qua parent loader/layer?
- Provider có đúng service contract, \`provides\` / \`META-INF/services\` đã cấu hình?

**Module version không phải compatibility policy.** Có module \`2.1.0\` không tự chứng minh plugin dùng được API v2.1 hoặc mọi binary method vẫn hợp lệ.

### Cổng C — Thử trong môi trường staging

- Tạo class loader hoặc \`ModuleLayer\` theo đúng kiến trúc host.
- Khám phá provider; phân biệt không có/một/nhiều/provider lỗi.
- Khởi tạo và gọi lifecycle \`start\` hoặc \`initialize\`.
- Thực hiện smoke test và các contract methods bắt buộc.
- Kiểm tra health, config, resource quota, timeout và security policy.
- Nếu lỗi, không publish plugin; cleanup mọi resource đã khởi tạo.

**Lưu ý:** chạy constructor, static initializer hoặc \`ServiceLoader.Provider.get()\` có thể thực thi mã plugin. Không đưa mã thiếu tin cậy vào cùng JVM để “kiểm tra thử” khi chính sách bảo mật yêu cầu isolation mạnh.

## 5. Ví dụ Java 17+: kiểm tra manifest và digest mà chưa kích hoạt

Tạo file **\`PluginPackageInspector.java\`**. Chương trình kiểm tra các trường manifest cơ bản, cấu trúc version minh họa và SHA-256 của chính JAR; nó không nạp entry-point class. Digest được **in để đối chiếu** với nguồn phân phối đáng tin, không tự chứng minh artifact an toàn.

\`\`\`java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.jar.Attributes;
import java.util.jar.JarFile;
import java.util.jar.Manifest;
import java.util.regex.Pattern;

public final class PluginPackageInspector {
    private static final Pattern ID =
            Pattern.compile("[a-z][a-z0-9-]{0,63}");
    private static final Pattern VERSION =
            Pattern.compile("(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)");
    private static final int SUPPORTED_API = 2;

    private static String require(Attributes attributes, String key) {
        String value = attributes.getValue(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing " + key);
        }
        return value.trim();
    }

    private static void inspect(Path file) throws Exception {
        if (!Files.isRegularFile(file)) {
            throw new IllegalArgumentException("Not a regular file");
        }
        try (JarFile jar = new JarFile(file.toFile())) {
            Manifest manifest = jar.getManifest();
            if (manifest == null) {
                throw new IllegalArgumentException("Missing JAR manifest");
            }
            Attributes a = manifest.getMainAttributes();
            String id = require(a, "Plugin-Id");
            String version = require(a, "Plugin-Version");
            String apiText = require(a, "Plugin-Api-Version");

            if (!ID.matcher(id).matches()) {
                throw new IllegalArgumentException("Invalid Plugin-Id");
            }
            if (!VERSION.matcher(version).matches()) {
                throw new IllegalArgumentException("Invalid Plugin-Version");
            }
            int api;
            try {
                api = Integer.parseInt(apiText);
            } catch (NumberFormatException e) {
                throw new IllegalArgumentException("Invalid API version", e);
            }
            if (api != SUPPORTED_API) {
                throw new IllegalArgumentException("Unsupported API " + api);
            }

            MessageDigest sha256 = MessageDigest.getInstance("SHA-256");
            try (InputStream input = Files.newInputStream(file)) {
                byte[] buffer = new byte[8192];
                int count;
                while ((count = input.read(buffer)) >= 0) {
                    if (count > 0) sha256.update(buffer, 0, count);
                }
            }
            System.out.println("VALID " + id + "@" + version);
            System.out.println("API " + api);
            System.out.println("SHA-256 " +
                    HexFormat.of().formatHex(sha256.digest()));
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java PluginPackageInspector <jar>");
            System.exit(2);
        }
        try {
            inspect(Path.of(args[0]));
        } catch (IllegalArgumentException e) {
            System.err.println("REJECTED: " + e.getMessage());
            System.exit(1);
        }
    }
}
\`\`\`

Tạo một JAR mẫu metadata-only để kiểm tra. Lưu manifest **\`plugin.mf\`** và kết thúc bằng một dòng trống:

\`\`\`text
Manifest-Version: 1.0
Plugin-Id: csv-exporter
Plugin-Version: 1.8.2
Plugin-Api-Version: 2

\`\`\`

Chạy trên JDK 17+:

\`\`\`bash
javac PluginPackageInspector.java
jar --create --file sample-plugin.jar --manifest plugin.mf
java PluginPackageInspector sample-plugin.jar
\`\`\`

Stdout có dạng:

\`\`\`text
VALID csv-exporter@1.8.2
API 2
SHA-256 <64 ký tự hex của artifact thực tế>
\`\`\`

Dòng SHA-256 được biểu diễn theo mẫu vì nội dung bytes của JAR thay đổi theo metadata và môi trường build. **Không được hard-code digest này làm giá trị bảo mật**. Chương trình minh họa chưa kiểm tra publisher signature, giới hạn archive, toàn bộ class files, dependency, service declaration hay race giữa hai lần mở file. Ở production, hãy áp dụng allowlist và xác minh bản sao immutable được nạp sau đó.

Để kiểm thử nhánh từ chối, đổi \`Plugin-Api-Version: 2\` thành \`3\`, tạo lại JAR; chương trình in stderr:

\`\`\`text
REJECTED: Unsupported API 3
\`\`\`

## 6. Quy trình release có kiểm soát

Một pipeline CI/CD thực dụng:

\`\`\`text
Commit / release tag
    |
    v
Build bằng toolchain & dependency lock
    |
    v
Unit tests + compatibility tests
    |
    v
Package JAR + descriptor + checksum + provenance
    |
    v
Artifact validation / signature verification
    |
    v
Publish release immutable (không ghi đè version)
    |
    v
Stage trong host, resolve dependency và run smoke tests
    |
    v
Canary hoặc rollout theo nhóm request/tenant
    |
    v
Atomic activate + monitoring
    |
    v
Stable / rollback
\`\`\`

Những điều phải được ghi lại ở mỗi release: \`pluginId\`, version, exact digest, release ID, API requirement, Java requirement, publisher/signature status, dependency list, host deployment ID, timestamp và người/phê duyệt tự động theo policy.

**Phê duyệt deploy và phê duyệt activate có thể khác nhau.** Tách hai bước tránh trường hợp artifact được tải lên repository thì lập tức chạy ở production chưa qua compatibility check.

## 7. Tách staged, active và previous

Một quản lý plugin nên có trạng thái rõ ràng:

| State | Ý nghĩa | Có nhận request mới? |
|---|---|---|
| \`DISCOVERED\` | Gói mới xuất hiện, chưa duyệt | Không |
| \`VALIDATED\` | Artifact và metadata hợp lệ | Không |
| \`STAGED\` | Đã resolve, khởi tạo trong môi trường kiểm tra | Không |
| \`ACTIVE\` | Được registry hiện hành chọn | Có |
| \`DRAINING\` | Ngừng cấp request mới, đợi request cũ | Không |
| \`STOPPED\` | Đã đóng resource theo lifecycle | Không |
| \`FAILED\` / \`QUARANTINED\` | Không đáp ứng policy hoặc startup thất bại | Không |

Có thể giữ một **release manifest** của bản được phép rollback:

\`\`\`text
active  -> csv-exporter@1.8.2 (sha256:...)
previous-> csv-exporter@1.8.1 (sha256:...)
\`\`\`

Nhưng “previous” không nhất thiết là object đang còn chạy. Có thể chỉ giữ artifact đã kiểm chứng, dependency closure và cấu hình tương thích. Nếu plugin V1 đã bị đóng hoặc class loader đã giải phóng, rollback đòi hỏi **khởi tạo lại V1**, không đơn giản là sửa một con trỏ tới instance cũ.

Nếu plugin có state persistent, phải xác định schema migration và backward compatibility từ đầu. Nếu V2 đã ghi dữ liệu theo schema V2 không đọc được bởi V1, việc chuyển JAR về V1 **không bảo đảm rollback nghiệp vụ thành công**.

## 8. Atomic publication và không đóng phiên bản cũ quá sớm

Trong hệ đọc nhiều, writer có thể chuẩn bị một immutable registry mới và công bố qua \`AtomicReference\`:

\`\`\`java
// Đoạn tích hợp, không phải chương trình độc lập.
record Registry(long revision, Map<String, Plugin> plugins) {
    Registry {
        plugins = Map.copyOf(plugins);
    }
}

AtomicReference<Registry> active =
        new AtomicReference<>(new Registry(0, Map.of()));
\`\`\`

Sau khi V2 đạt kiểm tra, writer xây snapshot mới và \`active.set(newRegistry)\`. Reader lấy một snapshot và giữ cho toàn bộ tác vụ logic để tránh chọn lẫn hai phiên bản.

Tuy nhiên, atomic swap **không cho phép đóng V1 ngay**: request đã lấy snapshot cũ vẫn có thể đang gọi V1.

\`\`\`text
Reader A đã giữ V1
      |
Writer publish V2
      |
Request mới dùng V2
      |
Reader A tiếp tục dùng V1
      |
Drain V1 / đợi lease kết thúc
      |
Close V1
\`\`\`

Có thể dùng lease/reference counting với protocol acquire không race với draining, hoặc read/write lock bảo vệ lifetime. Chỉ tăng ref-count sau khi đọc snapshot mà không đồng bộ với thao tác close là chưa đủ; có race acquire-after-close.

Nếu nhiều writer cùng cập nhật registry, dùng single-writer executor, lock hoặc CAS đúng cách để tránh lost update. Không đặt \`plugin.start()\` trong hàm CAS có thể chạy lại.

## 9. Rollback: chuyển phiên bản không giống hoàn tác dữ liệu

Rollback cần định nghĩa phạm vi:

- **Traffic rollback:** định tuyến request mới trở lại bản ổn định.
- **Code/artifact rollback:** nạp lại binary và dependency của release trước.
- **Config rollback:** phục hồi đúng cấu hình/feature flags tương thích.
- **Data rollback:** xử lý dữ liệu/schema do release lỗi đã thay đổi.
- **Operational rollback:** dừng canary, thu hồi quyền, đóng callback/task và cleanup resource.

Không phải mọi thứ đều hoàn tác tự động. Nếu V2 đã gửi email, ghi thanh toán hoặc thay schema dữ liệu, chuyển lại V1 không đảo ngược những side effect đó. Cần idempotency, compensation hoặc migration ngược đã được kiểm chứng.

### Playbook rollback tối thiểu

1. **Xác định trigger:** error rate, latency, health check, compatibility failures hoặc sự cố bảo mật vượt ngưỡng chính sách.
2. **Đóng băng rollout:** ngừng kích hoạt V2 thêm trên node/tenant khác.
3. **Xác nhận release rollback target:** artifact digest, dependency và config trước đó vẫn có và hợp lệ.
4. **Khởi tạo phiên bản trước trong staging** nếu instance cũ đã dừng.
5. **Chuyển traffic/registry nguyên tử** theo chính sách; request đang chạy phải được drain/cancel an toàn.
6. **Kiểm tra hậu rollback:** health, error rate, dữ liệu và các capability thiết yếu.
7. **Cleanup V2:** dừng task/listener, đóng resource và gỡ references/class loader theo lifecycle.
8. **Ghi incident:** version, digest, lý do, thời điểm, kết quả và các bước xử lý dữ liệu còn lại.

**Không rollback tự động vô hạn** nếu bản trước cũng lỗi hoặc state schema đã không còn tương thích. Có thể cần đưa feature vào degraded mode và chặn tác vụ gây side effect.

## 10. Canary và rollout tăng dần

Đối với plugin thay đổi hành vi quan trọng, nên đưa vào môi trường staging rồi rollout theo cohort/tenant hoặc phần trăm traffic có kiểm soát. Cần chú ý **routing ổn định** khi một request có nhiều bước: một luồng công việc không nên bắt đầu ở V1 rồi vô tình kết thúc ở V2 nếu contract yêu cầu pin phiên bản.

Những tín hiệu cần theo dõi:

| Tín hiệu | Gợi ý phát hiện |
|---|---|
| Startup/health failure | Plugin không thể activate |
| LinkageError | Binary/API mismatch hoặc class loader conflict |
| Request error rate | Hành vi plugin thay đổi/hỏng |
| Latency p95/p99 | Chậm do dependency, cache hoặc tài nguyên |
| Resource/Metaspace | Loader, thread, callback hoặc resource leak |
| Duplicate side effects | Retry/rollback làm lặp nghiệp vụ |
| Plugin-specific metrics | Kết quả xuất dữ liệu, tỷ lệ lỗi định dạng |

Canary phải đủ dài và có khối lượng phù hợp để lộ lỗi representative. Nếu chỉ có một request demo, không thể kết luận an toàn cho toàn bộ traffic.

## 11. Test release và rollback trước production

Bộ test nên có:

1. Không có provider: host trả lỗi có ngữ nghĩa.
2. Có một provider hợp lệ: gọi đúng implementation.
3. Có nhiều provider: áp dụng selection policy và xử lý trùng.
4. Provider cấu hình lỗi: bị reject trước activation.
5. Artifact sai digest hoặc signature: không được nạp.
6. Module/API requirement không thỏa: từ chối có nguyên nhân.
7. Factory/constructor hoặc health check thất bại: không publish snapshot lỗi.
8. V2 hoạt động, V1 còn in-flight: V1 không bị close sớm.
9. Rollback sau publish V2: traffic mới chọn V1 đã được kiểm chứng.
10. Persistent data đã được V2 ghi: V1 có đọc/xử lý được theo migration policy?
11. Nhiều lần reload: class loader, callback, thread, Metaspace không tăng không giới hạn.
12. Shutdown giữa rollout hoặc rollback: tài nguyên được dọn và trạng thái không mơ hồ.

Có thể sử dụng test fixture JAR nhiều version, integration tests với class loader/module layer thực và giả lập failure có kiểm soát. Khi kiểm thử concurrent publication, dùng latch/barrier thay vì \`Thread.sleep\` làm bằng chứng thứ tự.

## 12. Những lỗi phát hành phổ biến

- Ghi đè artifact cùng version khiến checksum và rollback target không đáng tin.
- Chỉ kiểm tra JAR tồn tại, không kiểm tra signature, dependency và compatibility.
- Tin \`ModuleDescriptor.version()\` sẽ tự kiểm tra API version ranges.
- Dùng JAR đang thay đổi trên filesystem làm nguồn class loading sau validation.
- Activate plugin trước khi kiểm tra constructor/provider và health.
- Công bố từng provider dở dang thay vì một registry snapshot hoàn chỉnh.
- Đóng V1 ngay sau V2 publish dù request V1 còn chạy.
- Giữ chỉ tên version mà không giữ exact artifact + digest + config cũ.
- Nghĩ rollback JAR sẽ đảo ngược schema migration và side effect.
- Không chuẩn bị cách xử lý khi rollback target đã bị xóa hoặc không còn chạy trên JDK mới.
- Không quan sát loader leak, thread leak và resource leak sau nhiều lần deploy.
- Để plugin không tin cậy chạy cùng JVM mà không có ranh giới bảo mật phù hợp.

## 13. Checklist phát hành và đường quay lại

Trước khi bật plugin version mới:

- Artifact có ID/version **bất biến**, digest và provenance phù hợp?
- Manifest/descriptor có schema, API requirement, Java requirement và service entry đúng?
- Artifact đã được kiểm tra integrity/signature theo nguồn tin cậy?
- Dependencies/JAR/modules đúng, không trùng module/class gây conflict?
- Plugin đã qua unit, contract, integration, smoke và health checks?
- Registry chỉ được công bố sau khi toàn bộ provider cần thiết sẵn sàng?
- Có lease/drain protocol để tránh đóng plugin in-flight?
- Có lưu exact release trước cùng config, dependency và rollback guide?
- Có kiểm tra migration/schema có tương thích rollback không?
- Có canary, metrics, ngưỡng dừng, timeout và người chịu trách nhiệm vận hành?
- Có quy trình cleanup resource/class loader và log quyết định release?

**Ghi nhớ:** phát hành plugin an toàn là **đóng gói bất biến theo phiên bản → xác minh artifact và hợp đồng → staging → công bố có kiểm soát → quan sát → rollback đã được thử trước**. Một bản JAR cũ được giữ lại chỉ là điều kiện cần; **đường quay lại thực sự** đòi hỏi cả dependency, cấu hình, dữ liệu, lifecycle và traffic routing đều hỗ trợ.
