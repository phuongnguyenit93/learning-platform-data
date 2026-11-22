# Phiên bản module cung cấp thông tin gì và vì sao cần chính sách phiên bản riêng

## 1. Vấn đề: có version trong module chưa đủ để quản lý tương thích

Java Platform Module System (JPMS) hỗ trợ gắn **phiên bản tùy chọn** cho một module. Ví dụ module \`com.example.plugin.api\` có thể mang phiên bản \`2.1.0\`, và chương trình có thể đọc thông tin đó qua \`ModuleDescriptor.version()\`.

Nhưng **module version chỉ là metadata**, không phải một cơ chế quản lý dependency đầy đủ như Maven hoặc Gradle. Bộ phân giải JPMS không tự diễn giải một version range như \`[2.0,3.0)\` để tìm bản phát hành phù hợp, không tự tải bản mới nhất từ repository và không tự quyết định việc nâng cấp module là an toàn về tương thích API.

Trong kiến trúc plugin, cần phân biệt:

- **Module name**: định danh module JPMS dùng cho \`requires\` và resolution, ví dụ \`com.example.plugin.api\`.
- **Module version**: thông tin phiên bản tùy chọn trong descriptor, ví dụ \`2.1.0\`.
- **API compatibility policy**: các quy tắc do host và plugin framework đặt ra để quyết định plugin nào được phép kết nối với API nào.
- **Artifact/dependency version**: phiên bản phát hành JAR hay thư viện do build/deployment system quản lý.
- **Runtime requirement**: phiên bản Java tối thiểu, đặc tính module, class-file version và khả năng thực thi.

Một host đáng tin cậy **đọc version, nhưng không chỉ tin version**: nó phải kiểm tra hợp đồng được hỗ trợ, binary compatibility, dependency graph, tính năng cần thiết và hành vi runtime.

## 2. Module version được khai báo ở đâu?

Trong JPMS, một explicit module có \`module-info.java\`:

\`\`\`java
module com.example.plugin.api {
    exports com.example.plugin.api;
}
\`\`\`

Cú pháp Java \`module-info.java\` **không có** mệnh đề \`version\`. Phiên bản được gắn khi biên dịch/đóng gói hoặc thông qua các công cụ hỗ trợ. Ví dụ:

\`\`\`bash
javac -d out/api src/api/module-info.java src/api/com/example/plugin/api/Plugin.java
jar --create --file plugin-api.jar --module-version 2.1.0 -C out/api .
\`\`\`

Đoạn lệnh giả định các file nguồn tồn tại ở đường dẫn đã nêu. \`--module-version\` thêm phiên bản vào module descriptor của JAR được tạo. Đây là thông tin của module, **không phải** một chỉ thị source \`requires com.example.plugin.api >= 2.0\`; JPMS không hỗ trợ cú pháp version-range đó trong \`module-info.java\`.

Các module trên module path có thể là **explicit**, **automatic** hoặc **exploded**. Cách xác định phiên bản khả dụng phụ thuộc descriptor/artifact và công cụ tạo nó. Không nên suy luận chắc chắn version chỉ từ tên file \`foo-2.1.jar\`; \`ModuleDescriptor.version()\` mới là dữ liệu do JPMS trình bày và nó có thể trống.

## 3. Đọc ModuleDescriptor.version()

API quan trọng:

\`\`\`java
ModuleDescriptor descriptor = reference.descriptor();
Optional<ModuleDescriptor.Version> version = descriptor.version();
\`\`\`

\`ModuleDescriptor.Version\` là kiểu biểu diễn và so sánh phiên bản của JPMS; nó không đồng nghĩa hoàn toàn với Semantic Versioning. Một số chuỗi phiên bản được parse theo quy tắc JPMS, và định dạng/so sánh có thể khác chính sách phát hành riêng của hệ plugin. Nếu ứng dụng tuân theo SemVer, phải dùng quy tắc parser và range riêng phù hợp SemVer.

Module version là tùy chọn: \`version()\` có thể trả \`Optional.empty()\`. Ứng dụng không nên tự gán mặc định \`0.0.0\` hoặc coi missing version là bản mới nhất khi chưa có policy.

Các trường metadata khác thường cần xem cùng version:

| Metadata | Ý nghĩa | Điều không tự bảo đảm |
|---|---|---|
| \`descriptor.name()\` | Tên JPMS module | Nhà phát hành đáng tin |
| \`descriptor.version()\` | Phiên bản được khai báo | Tương thích với host |
| \`descriptor.requires()\` | Những module cần để liên kết | Phiên bản dependency phù hợp |
| \`descriptor.exports()\` | Package có thể truy cập | API semantic stability |
| \`descriptor.uses()\` | Service mà module sử dụng | Service được cài sẵn |
| \`descriptor.provides()\` | Service provider được công bố | Provider an toàn/khởi tạo thành công |

## 4. Ví dụ Java 17+: đọc version của module đã đóng gói

Ví dụ này tạo một module nhỏ rồi dùng \`ModuleFinder\` để đọc descriptor trước khi kích hoạt bất kỳ mã plugin nào.

Cấu trúc:

\`\`\`text
project/
├── src/
│   └── demo.plugin/
│       ├── module-info.java
│       └── demo/plugin/Greeter.java
└── InspectModuleVersion.java
\`\`\`

Nội dung **\`src/demo.plugin/module-info.java\`**:

\`\`\`java
module demo.plugin {
    exports demo.plugin;
}
\`\`\`

Nội dung **\`src/demo.plugin/demo/plugin/Greeter.java\`**:

\`\`\`java
package demo.plugin;

public final class Greeter {
    public static String greet() {
        return "hello";
    }
}
\`\`\`

Nội dung **\`InspectModuleVersion.java\`**:

\`\`\`java
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;
import java.util.Comparator;

public class InspectModuleVersion {
    public static void main(String[] args) {
        if (args.length != 1) {
            System.err.println("Usage: java InspectModuleVersion <jar-or-directory>");
            System.exit(2);
        }

        ModuleFinder finder = ModuleFinder.of(Path.of(args[0]));
        finder.findAll().stream()
                .sorted(Comparator.comparing(r -> r.descriptor().name()))
                .forEach(InspectModuleVersion::print);
    }

    private static void print(ModuleReference reference) {
        ModuleDescriptor d = reference.descriptor();
        System.out.println("module=" + d.name());
        System.out.println("version=" +
                d.version().map(Object::toString).orElse("<none>"));
        System.out.println("automatic=" + d.isAutomatic());
        System.out.println("requires=" +
                d.requires().stream()
                        .map(ModuleDescriptor.Requires::name)
                        .sorted()
                        .toList());
    }
}
\`\`\`

Tại thư mục \`project\`, chạy trên JDK 17+ (shell POSIX):

\`\`\`bash
javac -d mods/demo.plugin \
  src/demo.plugin/module-info.java \
  src/demo.plugin/demo/plugin/Greeter.java

jar --create --file demo.plugin.jar \
  --module-version 2.1.0 \
  -C mods/demo.plugin .

javac InspectModuleVersion.java
java InspectModuleVersion demo.plugin.jar
\`\`\`

Stdout:

\`\`\`text
module=demo.plugin
version=2.1.0
automatic=false
requires=[java.base]
\`\`\`

\`java.base\` là dependency ngầm định. Nếu đóng gói module mà không đặt \`--module-version\`, trường \`version\` có thể là \`<none>\`.

Lệnh \`ModuleFinder.of(Path.of(args[0]))\` chỉ đọc thông tin về module từ đường dẫn; chương trình không gọi class \`Greeter\`, không tạo \`ModuleLayer\` và không kích hoạt plugin. Trường hợp đường dẫn lỗi, artifact không hợp lệ hoặc module trùng/xung đột có thể dẫn tới \`FindException\`/lỗi I/O tương ứng, cần phân loại khi triển khai production.

## 5. JPMS resolution dùng version như thế nào?

Hãy xem:

\`\`\`java
module com.example.report.plugin {
    requires com.example.plugin.api;
}
\`\`\`

Lệnh \`requires\` nêu **tên module**, không khai báo version tối thiểu/tối đa. Bộ phân giải JPMS dùng \`ModuleFinder\` và parent configuration để tìm module theo tên và thỏa các quy tắc dependency/readability. Nó **không thương lượng version range** như dependency resolver của build tool.

Điều này dẫn đến ba hệ quả:

1. Nếu có \`com.example.plugin.api\` version \`1.0.0\` trên module path, cú pháp \`requires com.example.plugin.api;\` không tự từ chối chỉ vì plugin cần một API mới hơn.
2. Nếu có nhiều phiên bản JAR cùng tên module trong cùng phạm vi tìm kiếm, không được kỳ vọng JPMS chọn phiên bản cao nhất theo SemVer.
3. Khi thiếu dependency phiên bản cần thiết, JPMS không tự tải bản mới từ Maven Central hay một plugin repository.

Module version là metadata hữu ích cho diagnostics và policy ở tầng host, **không phải phép thay thế cho kiểm tra tương thích nhị phân, semantic hoặc khả năng của provider**.

## 6. Vì sao cần chính sách phiên bản riêng?

Một hệ plugin cần trả lời những câu hỏi mà JPMS không tự giải quyết:

- Plugin \`csv-exporter 3.2.0\` có tương thích với host API \`2.4.0\` không?
- Có cho phép plugin yêu cầu API \`2.x\` chạy trên API \`3.0.0\` không?
- Khi phát hiện hai plugin cùng ID nhưng khác version, sẽ chọn bản nào?
- Một module không có version có được cho chạy không?
- Khi host cập nhật API, những provider nào phải build lại hoặc chạy integration test?
- Tính năng nào thực sự có mặt trong runtime, bất kể module version khai báo?
- Khi rollback, host có cần giữ nhiều phiên bản plugin song song hay không?

JPMS không thể tự suy ra compatibility từ số phiên bản. Host phải xây một **policy** tường minh và áp dụng trước khi nạp/kích hoạt plugin.

Ví dụ một policy đơn giản:

\`\`\`text
Host API version: 2.4.0
Supported plugin API major: 2
Plugin requires API major: 2 -> allowed candidate
Plugin requires API major: 3 -> rejected
Unknown API major -> rejected until reviewed
\`\`\`

Đây chỉ là **bộ lọc compatibility ban đầu**. Cùng major vẫn không bảo đảm mọi phương thức/behavior tương thích nếu nhà phát triển phá vỡ hợp đồng hoặc dùng API đã bị loại bỏ. Cần thêm contract tests, kiểm tra method/class có mặt, feature negotiation và kiểm thử runtime.

## 7. Phân biệt các loại phiên bản trong plugin ecosystem

| Loại | Ví dụ | Chủ thể quyết định |
|---|---|---|
| JPMS module version | \`com.example.plugin.api@2.4.0\` | Build/packaging metadata |
| Plugin implementation version | \`csv-exporter 1.7.0\` | Nhà phát hành plugin |
| Host API version | \`2.4.0\` | Chủ sở hữu hợp đồng extension |
| Plugin API requirement | \`>=2.2,<3.0\` | Metadata/descriptor của plugin + policy host |
| JVM/runtime requirement | Java 17+ | Bản build, bytecode và tính năng sử dụng |
| Artifact dependency version | \`library-x:4.1.2\` | Build/deployment resolution |
| Capability version | \`export.csv.v2\` | Protocol/feature negotiation |

Không nên dùng một chuỗi version duy nhất cho tất cả. Một plugin phiên bản \`5.0.0\` vẫn có thể sử dụng API host \`2.x\`; ngược lại, plugin version \`1.0.0\` có thể yêu cầu API host \`3.x\`.

Nếu module descriptor chỉ chứa \`version=1.7.0\`, host vẫn chưa biết plugin cần API nào. Có thể dùng metadata riêng trong manifest hoặc descriptor plugin:

\`\`\`text
Plugin-Id: csv-exporter
Plugin-Version: 1.7.0
Plugin-Api-Range: [2.2.0,3.0.0)
Required-Java-Version: 17
\`\`\`

Các trường \`Plugin-*\` ở đây là quy ước ứng dụng, **không phải thuộc tính JPMS chuẩn**; range chỉ được phép dùng khi host tự định nghĩa và hiện thực parser/chính sách.

## 8. Semantic Versioning và tương thích thực tế

Semantic Versioning thường biểu diễn \`MAJOR.MINOR.PATCH\` với ý nghĩa:

- **MAJOR** khi có thay đổi API không tương thích.
- **MINOR** khi thêm chức năng tương thích ngược.
- **PATCH** khi sửa lỗi không phá compatibility theo contract.

Tuy nhiên, SemVer **chỉ đáng tin khi dự án tuân thủ kỷ luật phát hành và định nghĩa rõ public API**. Đặc biệt, thay đổi hành vi, serialization format, threading hoặc security policy có thể phá tương thích dù method signature vẫn tồn tại.

Những lỗi so sánh version phổ biến:

- So sánh bằng \`String.compareTo\`: \`"2.10.0"\` có thứ tự từ điển khác kỳ vọng khi so với \`"2.9.0"\`.
- Chỉ tách dấu chấm rồi so \`int\`: bỏ qua prerelease như \`2.0.0-rc.1\`, build metadata và quy tắc SemVer.
- Tin rằng \`ModuleDescriptor.Version\` luôn chính là một parser/comparator SemVer đầy đủ.
- Dùng rule “cùng major là an toàn tuyệt đối” mà không kiểm thử contract.

Nên dùng một thư viện version-range đáng tin hoặc tự hiện thực một parser được kiểm thử nghiêm ngặt theo specification mà hệ plugin đã chọn. Đặt policy cho prerelease, snapshot, phiên bản thiếu hoặc không hợp lệ.

## 9. Quy trình kiểm tra compatibility trước kích hoạt

Một quy trình pre-activation thực tế:

\`\`\`text
Plugin artifact chưa tin cậy
        |
        v
Kiểm tra nguồn, hash/signature, metadata/schema
        |
        v
Đọc module descriptor + plugin descriptor
        |
        v
Xác định plugin ID/version, API requirement, Java requirement
        |
        v
Kiểm tra version policy và feature/capability requirements
        |
        v
Kiểm tra module/dependency graph, duplicate module names
        |
        v
Resolution + layer/class loader
        |
        v
Kiểm tra service provider contract + khởi tạo/health check
        |
        v
Công bố plugin active
\`\`\`

**Từ chối trước khi khởi tạo** nếu policy không được thỏa. Không nên dùng \`Class.forName\` để “kiểm tra metadata” của plugin chưa được phê duyệt vì class loading/initialization có thể chạy code hoặc gây tác dụng phụ.

Trường hợp cần hỗ trợ nhiều API major cùng lúc, có thể phát hành adapter hoặc nhiều module API riêng, nhưng phải thiết kế cẩn thận class identity và compatibility. Không thể chỉ đặt hai JAR trùng tên module khác version cùng một module graph rồi kỳ vọng JPMS tự chọn đúng cho từng plugin.

## 10. Binary compatibility khác với module version

Hai bản API có thể cùng module name nhưng khác class/method. Ví dụ:

\`\`\`java
// API v1
public interface Exporter {
    byte[] export(String input);
}
\`\`\`

\`\`\`java
// API v2 - thay đổi chữ ký, có khả năng phá tương thích
public interface Exporter {
    byte[] export(String input, String format);
}
\`\`\`

Nếu plugin build theo API v1 nhưng runtime host dùng API v2, có thể phát sinh \`NoSuchMethodError\`, \`AbstractMethodError\` hoặc lỗi linkage khác tùy call site và cách plugin được biên dịch/triển khai. Chỉ nhìn module version không chứng minh compatibility.

Ngay cả việc thêm abstract method vào interface có thể làm các implementation cũ thất bại khi method mới được gọi. Thêm \`default\` method có thể thân thiện hơn trong một số trường hợp nhưng vẫn cần đánh giá xung đột method và semantics.

Các công cụ so sánh API, kiểm thử binary compatibility và integration tests giúp bổ sung policy dựa trên version. Với plugin interface, nên thiết kế hợp đồng có khả năng mở rộng, phân nhóm capability và quy tắc deprecation rõ ràng.

## 11. Versioning trong ModuleLayer và hot reload

Một \`ModuleLayer\` là cấu hình runtime được tạo từ graph module đã resolve. Sau khi layer tồn tại, thay một JAR bằng bản version mới trên filesystem **không tự cập nhật module đang chạy**.

Khi nâng cấp plugin:

1. Chọn artifact phiên bản mới theo policy, kiểm tra integrity và compatibility.
2. Tạo finder/configuration/layer mới theo thiết kế class loader.
3. Nạp và kiểm tra provider mới.
4. Công bố snapshot registry mới để request tiếp theo dùng phiên bản mới.
5. Drain request cũ, đóng tài nguyên và gỡ reference tới loader/layer cũ.
6. Theo dõi class unloading/Metaspace, không giả định GC sẽ thu hồi ngay.

Với rollback, “quay lại version trước” có thể yêu cầu khởi tạo lại từ artifact được lưu trữ, vì loader/layer cũ có thể đã đóng hoặc object state không thể dùng lại.

Đừng nhầm version pinning với class loading isolation: pin một artifact đúng version vẫn chưa đủ nếu hai plugin cùng dùng các dependency không tương thích và buộc chạy trong một loader chung.

## 12. Chính sách ví dụ cho host/plugin

Một policy đơn giản nhưng rõ ràng:

\`\`\`text
Host:
  apiModule: com.example.plugin.api
  apiVersion: 2.4.1
  supportedApiRange: >=2.2.0 <3.0.0
  javaRuntime: 17
  allowPrereleasePlugins: false

Plugin:
  id: csv-exporter
  pluginVersion: 1.7.0
  requiredApiRange: >=2.3.0 <3.0.0
  minJava: 17
  requiredCapabilities: [export.csv.v2]
\`\`\`

Đây là cấu hình khái niệm, không phải cú pháp chuẩn của \`module-info.java\` hoặc \`ModuleDescriptor\`. Host phải kiểm tra cả hai điều kiện: API hiện hành nằm trong range plugin yêu cầu, và policy host cho phép plugin/capability này. Tính đúng đắn còn tùy các capability hiện có và kết quả contract test.

Một bảng quyết định minh họa:

| Plugin yêu cầu | Host API hiện hành | Kết quả policy |
|---|---|---|
| \`>=2.3,<3.0\` | \`2.4.1\` | Có thể chấp nhận nếu contract/capability đạt |
| \`>=3.0,<4.0\` | \`2.4.1\` | Từ chối vì không nằm trong range |
| \`>=2.0,<2.4\` | \`2.4.1\` | Từ chối theo range plugin khai báo |
| Không khai báo | \`2.4.1\` | Từ chối hoặc yêu cầu migration theo policy |

Không nên âm thầm “nới” range do plugin đã khai báo hoặc bỏ qua phiên bản thiếu mà không ghi lý do. Khi kiểm tra bằng máy, mọi quyết định nên được log với \`pluginId\`, version, API requirement, selected API và policy revision.

## 13. Lỗi phổ biến

- Đọc \`ModuleDescriptor.version()\` rồi nghĩ JPMS sẽ tự kiểm tra version range.
- Đặt version trực tiếp trong \`requires\` của \`module-info.java\` như syntax Maven.
- Cho rằng tên JAR đủ để xác định module version đáng tin.
- Dùng \`ModuleDescriptor.Version\` thay hẳn một chính sách SemVer mà không kiểm tra khác biệt.
- Coi số version “cao hơn” luôn tương thích với plugin cũ.
- Chỉ nhìn source compatibility mà bỏ qua binary/behavior compatibility.
- Không định nghĩa cách xử lý bản không có version hoặc prerelease.
- Để module trùng tên với version khác nhau và kỳ vọng JPMS tự chọn mới nhất.
- Đánh đồng version plugin, version API, version JDK và version dependency.
- Không kiểm tra artifact, capabilities và service contract trước khi kích hoạt.

## 14. Checklist thực hành

Trước khi đưa module/plugin vào runtime:

1. Đã đọc đúng \`ModuleDescriptor.name()\` và \`version()\`, xử lý version thiếu?
2. Đã phân biệt module version và plugin/API/runtime requirement?
3. Đã định nghĩa parser/range policy, prerelease và cơ chế compatibility?
4. Đã kiểm tra API hiện hành nằm trong range mà plugin hỗ trợ?
5. Đã kiểm tra Java version, dependency graph và capability bắt buộc?
6. Đã so sánh binary compatibility/contract và test behavior quan trọng?
7. Đã loại duplicate module names và xung đột dependency?
8. Đã xác minh nguồn gốc/integrity trước khi load code?
9. Đã có policy rollback, hot reload, drain và cleanup?
10. Đã log quyết định accept/reject có nguyên nhân rõ ràng?

**Ghi nhớ:** **JPMS module version trả lời “module tự khai báo phiên bản nào?”**, nhưng không trả lời “plugin này chạy an toàn và tương thích với host hiện tại không?”. Câu hỏi thứ hai đòi hỏi **chính sách phiên bản, kiểm tra dependency, capability và contract** do ứng dụng chủ động thiết kế.
