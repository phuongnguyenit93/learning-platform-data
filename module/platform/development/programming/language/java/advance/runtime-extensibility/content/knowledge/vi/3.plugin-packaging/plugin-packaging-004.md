# Đọc manifest, phiên bản và mô tả plugin trước khi kích hoạt

## 1. Vì sao phải đọc metadata trước khi chạy plugin?

Trong kiến trúc mở rộng lúc chạy, **plugin** thường được đóng gói dưới dạng JAR hoặc một thư mục phân phối chứa JAR và các tài nguyên. Trước khi gọi bất kỳ mã nào của plugin, host cần biết gói đó là gì, dùng phiên bản API nào, có tương thích với host không, thành phần khởi tạo nằm ở đâu và nhà phát hành có đáng tin cậy không. Bước **kiểm tra trước kích hoạt (pre-activation validation)** giúp host từ chối gói không hợp lệ trước khi tạo class loader riêng, instantiate plugin, đăng ký service hoặc phân phát request cho plugin.

Có ba khái niệm dễ nhầm:

- **JAR manifest**: tệp chuẩn \`META-INF/MANIFEST.MF\` trong archive JAR, gồm các thuộc tính như \`Manifest-Version\`, \`Main-Class\` hoặc thuộc tính tự định nghĩa \`Plugin-Id\`, \`Plugin-Version\`. Java có API \`java.util.jar.Manifest\` và \`JarFile.getManifest()\` để đọc.
- **Plugin descriptor**: dữ liệu mô tả theo quy ước của hệ thống plugin, chẳng hạn \`plugin.properties\`, JSON hoặc YAML trong JAR. Một host có thể dùng manifest, descriptor riêng hoặc kết hợp cả hai.
- **Metadata đáng tin**: thông tin đã được kiểm tra cú pháp, chính sách, tương thích và nguồn gốc. Chỉ đọc được một giá trị từ manifest **không chứng minh giá trị ấy đúng hoặc an toàn**.

Ví dụ, một JAR có thể khai báo \`Plugin-Id: report-csv\`, \`Plugin-Version: 1.4.0\`, \`Plugin-Api-Version: 2\`, \`Plugin-Class: com.example.CsvPlugin\`. Đây là cam kết từ bên cung cấp; host phải tự đối chiếu chính sách trước khi kích hoạt.

## 2. Ví dụ cấu trúc gói plugin

Một file JAR hợp lệ có thể có cấu trúc:

\`\`\`text
report-csv-plugin.jar
├── META-INF/
│   └── MANIFEST.MF
└── com/example/plugins/
    └── CsvPlugin.class
\`\`\`

Nội dung manifest minh họa:

\`\`\`text
Manifest-Version: 1.0
Plugin-Id: report-csv
Plugin-Version: 1.4.0
Plugin-Api-Version: 2
Plugin-Class: com.example.plugins.CsvPlugin
Plugin-Description: Exports reports as CSV
\`\`\`

Các trường \`Plugin-*\` **không phải thuộc tính bắt buộc của chuẩn JAR**. Chúng là hợp đồng riêng giữa host và nhà phát triển plugin. Chuẩn JAR không tự xác nhận rằng class trong \`Plugin-Class\` tồn tại, triển khai interface phù hợp, hoặc có thể chạy an toàn.

Các lựa chọn thiết kế metadata cần trả lời rõ:

| Trường | Mục đích | Quy tắc kiểm tra ví dụ |
|---|---|---|
| \`Plugin-Id\` | Định danh ổn định để đăng ký | Bắt buộc, duy nhất, dùng chữ thường/số/dấu nối |
| \`Plugin-Version\` | Phiên bản của chính plugin | Bắt buộc, theo quy ước phiên bản được công bố |
| \`Plugin-Api-Version\` | Phiên bản hợp đồng host mà plugin cần | Phải thuộc tập phiên bản host hỗ trợ |
| \`Plugin-Class\` | Entry point dự kiến | Không trống; chỉ nạp sau khi đạt các kiểm tra ban đầu |
| \`Plugin-Description\` | Hiển thị và hỗ trợ vận hành | Có thể tùy chọn; giới hạn độ dài/kiểm soát hiển thị |
| \`Plugin-Requires\` | Phụ thuộc plugin khác (nếu có) | Parse, kiểm tra phiên bản phụ thuộc và chu kỳ phụ thuộc |

Với Java manifest, tên attribute phải theo quy tắc định dạng manifest và độ dài dòng được giới hạn theo số byte. Công cụ build/JAR thường xử lý việc xuống dòng và continuation. Không nên tự ghép chuỗi manifest thô tùy tiện cho các giá trị dài. Mô tả giàu cấu trúc, phụ thuộc phức tạp hay nhiều ngôn ngữ thường phù hợp hơn với descriptor JSON/YAML có schema và giới hạn kích thước rõ ràng.

## 3. Phân biệt phiên bản plugin, API và Java

Ba loại phiên bản có mục đích khác nhau:

1. **Phiên bản plugin**, ví dụ \`1.4.0\`, dùng để quản lý phát hành, cập nhật và rollback. Không thể tự suy ra tính tương thích với host chỉ từ số này.
2. **Phiên bản API plugin**, ví dụ \`2\`, diễn tả hợp đồng mà host và plugin dùng để giao tiếp. Host cần một chính sách tương thích tường minh, ví dụ chỉ hỗ trợ API \`2\`.
3. **Phiên bản Java/runtime**, ví dụ class được biên dịch cho Java 21 trong khi host chạy Java 17, có thể dẫn đến \`UnsupportedClassVersionError\` khi JVM định nghĩa class. Khả năng hỗ trợ JVM phải được kiểm tra bằng metadata đáng tin hoặc bằng cách phân tích bytecode trước bước nạp.

**Semantic Versioning** (\`MAJOR.MINOR.PATCH\`) là một quy ước hữu ích nhưng Java không có bộ so sánh SemVer chuẩn trong \`java.util.jar\`. Nếu host dùng SemVer, hãy định nghĩa rõ chính sách prerelease, build metadata và range; dùng thư viện đã kiểm chứng hoặc một parser đầy đủ. Không so sánh các phiên bản bằng chuỗi từ điển: \`"2.10.0"\` không thể được so sánh đúng với \`"2.9.0"\` bằng \`String.compareTo\`.

Để tránh lẫn lộn, ví dụ runnable dưới đây dùng \`Plugin-Api-Version\` dạng số nguyên và kiểm tra chính xác một phiên bản API. Đây là chính sách minh họa; trong sản phẩm thật có thể hỗ trợ nhiều phiên bản hoặc một dải tương thích.

## 4. Quy trình kiểm tra trước kích hoạt

Một pipeline có kiểm soát nên tiến hành theo thứ tự:

\`\`\`text
JAR chưa tin cậy
    |
    v
Kiểm tra nguồn, quyền truy cập và kích thước tệp
    |
    v
Mở JAR, đọc manifest/descriptor (chưa nạp entry-point class)
    |
    v
Parse + kiểm tra trường bắt buộc, định dạng, giới hạn
    |
    v
Kiểm tra ID trùng, phiên bản, API, JVM, phụ thuộc, chính sách tin cậy
    |
    +-- Không đạt --> TỪ CHỐI + ghi log nguyên nhân
    |
    v
Chuẩn bị class loader và môi trường plugin
    |
    v
Kiểm tra entry point, khởi tạo, health check, đăng ký
    |
    v
KÍCH HOẠT để nhận công việc
\`\`\`

Không coi \`new JarFile(...)\` hoặc \`getManifest()\` là hành động chạy entry point. Chúng phục vụ đọc archive/metadata. Tuy vậy dữ liệu bên trong vẫn là đầu vào không tin cậy và có thể chứa archive gây tốn tài nguyên; cần giới hạn kích thước, số entry, chi phí xử lý và tài nguyên đọc. Tránh giải nén nội dung tùy ý ra filesystem nếu không cần thiết.

Nên kiểm tra các điều kiện sau trước bước load class:

- Tệp có nguồn gốc từ vị trí được cho phép; đường dẫn đã chuẩn hóa, tránh thay thế tệp giữa kiểm tra và kích hoạt.
- Manifest tồn tại, đọc được, mỗi trường bắt buộc có đúng kiểu dữ liệu và giới hạn kích thước.
- ID plugin chưa được một plugin khác chiếm; chính sách nâng cấp/đổi phiên bản rõ ràng.
- API version và phiên bản Java cần thiết tương thích với host.
- Phụ thuộc bắt buộc đã sẵn sàng, không có vòng phụ thuộc và không xung đột.
- Artifact qua bước xác minh integrity, publisher/signature theo chính sách hệ thống.
- Quyền hoặc capability được khai báo không vượt quá giới hạn host cho phép.

**Lưu ý:** kiểm tra metadata chỉ là lớp đầu tiên. Class loading có thể gặp \`ClassNotFoundException\`, \`NoClassDefFoundError\`, \`LinkageError\`; constructor hoặc static initializer có thể chạy mã và gây tác dụng phụ. Việc quyết định có cho phép thực thi plugin cần dựa trên chính sách bảo mật và mô hình cô lập phù hợp.

## 5. Ví dụ Java 17+: đọc và xác thực manifest mà không kích hoạt plugin

Chương trình sau đọc JAR được chỉ định trên dòng lệnh, kiểm tra bốn trường bắt buộc và in thông tin đã chuẩn hóa. Nó không gọi \`Class.forName\`, không khởi tạo plugin, không thêm JAR vào classpath.

Tạo file **\`PluginManifestInspector.java\`**:

\`\`\`java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.jar.Attributes;
import java.util.jar.JarFile;
import java.util.jar.Manifest;
import java.util.regex.Pattern;

public final class PluginManifestInspector {
    private static final Pattern ID = Pattern.compile("[a-z][a-z0-9-]{0,63}");
    private static final Pattern VERSION =
            Pattern.compile("(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)");
    private static final Pattern CLASS_NAME =
            Pattern.compile("[A-Za-z_$][A-Za-z0-9_$]*(\\.[A-Za-z_$][A-Za-z0-9_$]*)+");
    private static final int SUPPORTED_API_VERSION = 2;
    private static final long MAX_JAR_BYTES = 20L * 1024 * 1024;

    record PluginMetadata(String id, String version, int apiVersion,
                          String entryClass, String description) {}

    private static String required(Attributes attrs, String name) {
        String value = attrs.getValue(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing " + name);
        }
        return value.trim();
    }

    private static PluginMetadata inspect(Path path) throws IOException {
        if (!Files.isRegularFile(path)) {
            throw new IllegalArgumentException("Not a regular file");
        }
        long size = Files.size(path);
        if (size > MAX_JAR_BYTES) {
            throw new IllegalArgumentException("JAR exceeds size limit");
        }

        try (JarFile jar = new JarFile(path.toFile())) {
            Manifest manifest = jar.getManifest();
            if (manifest == null) {
                throw new IllegalArgumentException("Missing manifest");
            }
            Attributes a = manifest.getMainAttributes();

            String id = required(a, "Plugin-Id");
            if (!ID.matcher(id).matches()) {
                throw new IllegalArgumentException("Invalid Plugin-Id");
            }

            String version = required(a, "Plugin-Version");
            if (!VERSION.matcher(version).matches()) {
                throw new IllegalArgumentException("Invalid Plugin-Version");
            }

            String apiText = required(a, "Plugin-Api-Version");
            int api;
            try {
                api = Integer.parseInt(apiText);
            } catch (NumberFormatException e) {
                throw new IllegalArgumentException("Invalid Plugin-Api-Version", e);
            }
            if (api != SUPPORTED_API_VERSION) {
                throw new IllegalArgumentException("Unsupported plugin API: " + api);
            }

            String entry = required(a, "Plugin-Class");
            if (!CLASS_NAME.matcher(entry).matches()) {
                throw new IllegalArgumentException("Invalid Plugin-Class");
            }

            String description = a.getValue("Plugin-Description");
            if (description == null) description = "";
            if (description.length() > 500) {
                throw new IllegalArgumentException("Description too long");
            }

            return new PluginMetadata(id, version, api, entry, description);
        }
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.err.println("Usage: java PluginManifestInspector <plugin.jar>");
            System.exit(2);
        }
        try {
            PluginMetadata m = inspect(Path.of(args[0]));
            System.out.println("VALID: " + m.id() + "@" + m.version());
            System.out.println("API: " + m.apiVersion());
            System.out.println("Entry: " + m.entryClass());
            System.out.println("Description: " + m.description());
        } catch (IllegalArgumentException e) {
            System.err.println("REJECTED: " + e.getMessage());
            System.exit(1);
        }
    }
}
\`\`\`

Để tạo JAR mẫu không cần code plugin thực sự, trước tiên tạo file **\`plugin.mf\`** với nội dung sau; kết thúc bằng một dòng trống:

\`\`\`text
Manifest-Version: 1.0
Plugin-Id: report-csv
Plugin-Version: 1.4.0
Plugin-Api-Version: 2
Plugin-Class: com.example.plugins.CsvPlugin
Plugin-Description: Exports reports as CSV

\`\`\`

Chạy trên môi trường có JDK 17+:

\`\`\`bash
javac PluginManifestInspector.java
jar --create --file sample-plugin.jar --manifest plugin.mf
java PluginManifestInspector sample-plugin.jar
\`\`\`

Kết quả kỳ vọng:

\`\`\`text
VALID: report-csv@1.4.0
API: 2
Entry: com.example.plugins.CsvPlugin
Description: Exports reports as CSV
\`\`\`

JAR mẫu chỉ phục vụ kiểm tra metadata: **nó không chứa \`CsvPlugin.class\`**, nên sẽ thất bại nếu host tiếp tục thực sự nạp lớp đó. Đây là chủ ý để minh họa việc **validation metadata** và **validation entry point** là hai cổng khác nhau.

Đổi \`Plugin-Api-Version: 2\` thành \`Plugin-Api-Version: 3\`, tạo lại JAR và chạy lại sẽ trả lỗi:

\`\`\`text
REJECTED: Unsupported plugin API: 3
\`\`\`

Thông báo này được ghi ra stderr và quá trình thoát với mã lỗi 1. Chương trình chỉ bắt lỗi validation loại \`IllegalArgumentException\`; lỗi I/O hoặc archive không đọc được đi theo đường lỗi riêng. Trong hệ thống thật nên chuyển tất cả lỗi thành kết quả kiểm tra có mã phân loại mà không để request xử lý plugin sập ứng dụng.

### Giới hạn cố ý của ví dụ

Biểu thức regex cho version chỉ chấp nhận \`MAJOR.MINOR.PATCH\` không có prerelease/build metadata; đó là subset của SemVer, không phải parser SemVer đầy đủ. Regex tên class mang tính kiểm tra sơ bộ kiểu tên nhị phân phổ biến, không bảo đảm class tồn tại hoặc triển khai đúng interface. Ví dụ cũng chưa kiểm tra chữ ký, dependency, module, min-Java-version, trạng thái registry, số entry JAR, race do tệp bị thay đổi hoặc cấu hình runtime. Vì vậy chương trình là **bộ lọc metadata ban đầu**, không phải plugin manager sản xuất.

## 6. Manifest chuẩn và descriptor riêng: nên chọn gì?

**Dùng JAR manifest** khi metadata ít, dạng key-value và liên quan trực tiếp tới gói JAR. Ưu điểm: có sẵn \`JarFile.getManifest()\`, không cần parser ngoài; phù hợp plugin id, phiên bản, tên entry point và vài cờ đơn giản.

**Dùng descriptor riêng** khi metadata gồm danh sách dependency, ranges, capabilities, cấu hình, ràng buộc quyền, nhiều entry point hoặc mô tả có cấu trúc. Với JSON/YAML cần định nghĩa schema, version schema, giới hạn kích thước, chính sách trùng key, trường bắt buộc/tùy chọn, encoding, xử lý giá trị không nhận biết. Không nên tải parser cấu hình từ chính plugin chưa được kiểm tra để đọc descriptor.

**Dùng cả hai** khi manifest chứa khóa bootstrap tối thiểu và chỉ tới descriptor có cấu trúc. Khi đó phải định nghĩa nguồn nào là chuẩn nếu hai bên khai báo mâu thuẫn. Ví dụ: \`Plugin-Id\` và \`Plugin-Version\` chỉ lấy từ manifest; descriptor chỉ cung cấp dependencies/configuration. Không cho phép hai nguồn tự ý ghi đè lẫn nhau.

## 7. Kiểm tra publisher, tính toàn vẹn và rủi ro TOCTOU

Một manifest tự khai báo ID, phiên bản hay tên publisher **không tạo ra danh tính đáng tin**. Các mức bảo đảm khác nhau:

- **Checksum/SHA-256** giúp biết byte của artifact có trùng checksum được chấp nhận hay không; checksum lấy từ cùng nguồn không tin cậy thì không xác thực nhà phát hành.
- **Chữ ký số** giúp kiểm tra artifact có được ký bởi khóa được tin cậy và nội dung được bảo vệ bởi chữ ký còn nguyên vẹn hay không, với điều kiện quy trình xác minh bao phủ toàn bộ payload liên quan và chính sách trust/key rotation đúng.
- **JAR signing** có các quy tắc về signed entry và cơ chế xác minh khi nội dung entry được đọc. Chỉ mở manifest bằng \`JarFile\` không có nghĩa đã kiểm tra chữ ký toàn bộ JAR; phải có bước xác minh chữ ký phù hợp và chính sách kiểm tra mọi entry quan trọng.
- **Allowlist** theo publisher, nguồn artifact và capability kiểm soát plugin nào được phép chạy ngay cả khi thông tin mô tả hợp lệ.

Rủi ro **time-of-check to time-of-use (TOCTOU)** xuất hiện khi host kiểm tra tệp tại đường dẫn A, nhưng trước lúc nạp thì tệp A đã bị thay thế. Một phương án là sao chép artifact vào vùng staging chỉ đọc/không cho bên ngoài sửa, tính hash và xác minh trên đúng bản sao; sau đó class loader chỉ nạp từ bản sao đã được phê duyệt. Cần áp dụng đồng bộ cho các dependency đi kèm.

## 8. Kích hoạt sau khi qua kiểm tra

Sau khi metadata đạt yêu cầu, host mới chuẩn bị bước có khả năng chạy code:

1. Chốt chính sách tương thích và trạng thái registry theo ID/version.
2. Cấu hình class loader hoặc \`ModuleLayer\` theo mô hình cô lập và dependency.
3. Nạp/kiểm tra entry point theo hợp đồng, ví dụ interface \`Plugin\`; bắt và phân loại lỗi nạp hoặc liên kết class.
4. Khởi tạo trong môi trường được phép, cung cấp cấu hình/capability, gọi lifecycle \`initialize\`/health check.
5. Chỉ sau khi khởi tạo thành công mới công bố plugin trong registry cho request mới.
6. Khi lỗi, rollback đăng ký tạm và đóng tài nguyên đã mở; lưu kết quả kiểm tra để vận hành truy vết.

Đối với plugin không tin cậy, chạy cùng JVM là rủi ro lớn: class loader riêng **không phải sandbox an toàn**. Có thể cần tách plugin ra tiến trình/container với hạn chế quyền và giao thức giao tiếp rõ ràng.

Nếu host hỗ trợ cập nhật nóng, cần thêm quy tắc chuyển tiếp giữa plugin cũ/mới: in-flight requests, version pinning, drain, shutdown và rollback. Kiểm tra manifest không thay thế phần quản lý vòng đời này.

## 9. Lỗi thường gặp và checklist kiểm tra

Các lỗi phổ biến:

- Chỉ kiểm tra manifest tồn tại rồi lập tức gọi \`Class.forName\` trên giá trị \`Plugin-Class\`.
- Tin vào \`Plugin-Version\` mà không đối chiếu API version và khả năng tương thích runtime.
- Dùng \`String.compareTo\` cho SemVer.
- Giả định trường \`Plugin-Class\` là chuẩn của Java/JAR, hoặc có class thật vì manifest khai báo như vậy.
- Đồng nhất checksum với chữ ký nhà phát hành, hoặc coi \`JarFile.getManifest()\` là đã xác thực chữ ký toàn bộ archive.
- Để tệp JAR bị thay thế trong khoảng giữa validation và loading.
- Không giới hạn đầu vào hoặc không chặn duplicate ID/version.
- Ghi nguyên \`Plugin-Description\` từ nguồn ngoài vào HTML/log mà không xử lý ngữ cảnh hiển thị và ký tự điều khiển.
- Khởi tạo plugin để “đọc metadata” khiến mã chưa được duyệt có cơ hội thực thi.

Checklist trước lúc **activate**: đã đọc đúng artifact; metadata parse được; các trường bắt buộc và schema hợp lệ; API/JVM/dependency phù hợp; ID/version không xung đột; nguồn và integrity đạt chính sách; entry point/lifecycle có thể kiểm tra trong môi trường phù hợp; registry chỉ công bố sau khởi tạo thành công; có log từ chối và khả năng rollback.

**Kết luận:** manifest và descriptor cho phép host ra quyết định **trước khi chạy plugin**. Phần cốt lõi là tách ba thời điểm rõ ràng: **đọc metadata → kiểm tra/cho phép → nạp và kích hoạt**, đồng thời xác thực nguồn gốc và kiểm soát vòng đời theo yêu cầu thực tế.
