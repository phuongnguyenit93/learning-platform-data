# Quản lý version module và compatibility

## 1. Module name, module version và artifact version

Trong Java Platform Module System (JPMS), một named module được định danh bằng module name, ví dụ com.acme.orders. Module có thể mang metadata version, chẳng hạn 1.4.2, để công cụ build, người vận hành và hệ thống phân phối nhận biết phiên bản artifact.

Cần phân biệt ba khái niệm:

- **Module name:** tên định danh trong module-info.java, được dùng bởi requires, qualified exports/opens, uses, provides và module resolution.
- **Module version:** metadata version có thể được ghi vào module descriptor đã biên dịch.
- **Artifact version:** phiên bản của JAR/dependency theo hệ thống build như Maven hoặc Gradle.

Ví dụ artifact Maven com.acme:orders:1.4.2 có thể chứa named module com.acme.orders với module version 1.4.2. Module name nên ổn định qua các bản phát hành; không đưa version vào tên module.

JPMS không phải dependency version resolver như Maven hoặc Gradle. Module resolution chủ yếu làm việc với module name và dependency graph. Metadata version không tự khiến JVM chọn phiên bản mới nhất, áp dụng semantic versioning hoặc giải quyết xung đột dependency. Việc chọn artifact version thuộc trách nhiệm của build tool, package manager hoặc hệ thống triển khai.

## 2. Ghi version vào module descriptor

Source module-info.java khai báo module name và quan hệ module, nhưng không có cú pháp version trực tiếp trong khai báo module. Version thường được gắn vào descriptor khi đóng gói modular JAR.

Ví dụ module:

~~~java
module com.acme.orders {
    requires com.acme.customer;
    exports com.acme.orders.api;
}
~~~

Sau khi compile, đóng gói và gắn version:

~~~bash
jar --create \
    --file build/com.acme.orders.jar \
    --module-version 1.4.2 \
    -C build/classes/com.acme.orders .
~~~

Thư mục đầu vào phải chứa module-info.class cùng các class/resource của module. Điều chỉnh đường dẫn -C cho đúng output directory của dự án.

Kiểm tra descriptor:

~~~bash
jar --describe-module --file build/com.acme.orders.jar
~~~

Output có thể hiển thị tên module kèm version:

~~~text
com.acme.orders@1.4.2
requires com.acme.customer
exports com.acme.orders.api
~~~

Version được lưu trong module descriptor. Nó hữu ích cho tooling, báo cáo và kiểm tra artifact, nhưng không tự quyết định dependency nào được chọn khi runtime resolve module graph.

### 2.1. Đọc version bằng ModuleDescriptor

Có thể đọc version bằng API java.lang.module.ModuleDescriptor:

~~~java
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;

public class InspectModuleVersion {
    public static void main(String[] args) {
        ModuleReference reference = ModuleFinder
                .of(Path.of("build"))
                .find("com.acme.orders")
                .orElseThrow();

        ModuleDescriptor descriptor = reference.descriptor();

        System.out.println("Module: " + descriptor.name());

        descriptor.version().ifPresentOrElse(
                version -> System.out.println("Version: " + version),
                () -> System.out.println("Version metadata is absent"));
    }
}
~~~

ModuleDescriptor.version() trả về Optional<ModuleDescriptor.Version>. Module không có version metadata là tình huống hợp lệ; code không nên giả định mọi descriptor đều có version.

Nếu cần chuỗi version gốc, dùng rawVersion(), cũng trả về Optional<String>. version() cung cấp đối tượng version đã parse để so sánh, còn rawVersion() cho phép lấy chuỗi được ghi trong descriptor.

### 2.2. Tạo descriptor bằng Builder

Khi tạo descriptor trong bộ nhớ, API builder có thể gắn version:

~~~java
import java.lang.module.ModuleDescriptor;

public class BuildModuleDescriptor {
    public static void main(String[] args) {
        ModuleDescriptor descriptor = ModuleDescriptor
                .newModule("com.acme.tools")
                .version(ModuleDescriptor.Version.parse("2.1.0"))
                .exports("com.acme.tools.api")
                .build();

        System.out.println(descriptor.name());
        System.out.println(descriptor.version().orElseThrow());
    }
}
~~~

Đối tượng được tạo chỉ là metadata trong bộ nhớ. build() không tự tạo modular JAR, không ghi module-info.class và không đưa module vào module path. Muốn phát hành artifact, vẫn cần compile và đóng gói đúng quy trình.

## 3. Module version không phải cơ chế chọn dependency version

Giả sử module ứng dụng khai báo:

~~~java
module com.acme.app {
    requires com.acme.orders;
}
~~~

Dòng requires chỉ định module name com.acme.orders. Nó không thể hiện ràng buộc như “từ version 1.4 trở lên” hoặc “chỉ chấp nhận major version 1”.

Khi build, Gradle hoặc Maven chọn artifact version dựa trên dependency declaration, constraints, lockfile, repository metadata và các quy tắc resolution của build tool. Sau đó compiler/runtime dùng module name trong descriptor để thiết lập module graph.

Ví dụ Gradle:

~~~groovy
dependencies {
    implementation("com.acme:orders:1.4.2")
}
~~~

Ví dụ Maven:

~~~xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>orders</artifactId>
    <version>1.4.2</version>
</dependency>
~~~

Artifact được chọn cần chứa module name mà consumer yêu cầu. Nếu JAR khai báo tên module khác, dependency declaration có thể resolve thành công ở tầng repository nhưng module graph vẫn không resolve như mong đợi.

Không dựa vào tên file JAR orders-1.4.2.jar để suy ra module name hoặc version descriptor. Hãy kiểm tra module-info.class bằng jar --describe-module.

## 4. Giữ module name ổn định

Module name là một phần của contract giữa các module. Consumer tham chiếu tên này trong requires; module khác có thể dùng nó trong qualified exports, opens hoặc service configuration.

Không nên đổi module name chỉ vì artifact version thay đổi. Các bản phát hành 1.4.2, 1.5.0 và 2.0.0 vẫn nên giữ module name com.acme.orders nếu chúng là các bản phát hành của cùng một module và migration được quản lý theo version policy của dự án.

Đổi tên module có thể buộc mọi consumer cập nhật requires, module path, launcher, jlink configuration, service binding, test configuration và các qualified export target. Nếu thực sự cần đổi tên, hãy xem đó là migration có ảnh hưởng tới người dùng.

### 4.1. Automatic-Module-Name

Một thư viện chưa có module-info.class có thể được dùng như automatic module khi đặt trên module path. Để tên module ổn định, JAR có thể khai báo manifest entry:

~~~text
Automatic-Module-Name: com.acme.legacy
~~~

Nếu không có entry này, tên automatic module có thể được suy ra từ tên file JAR. Đổi tên artifact hoặc version suffix có thể làm tên suy ra thay đổi, ảnh hưởng đến requires của consumer.

Khi chuẩn bị modularize thư viện, nên cung cấp Automatic-Module-Name ổn định trong giai đoạn chuyển tiếp, sau đó phát hành module descriptor tường minh khi đã sẵn sàng.

## 5. Compatibility có nhiều lớp

Một phiên bản module mới có thể giữ nguyên module name nhưng vẫn phá vỡ consumer. Vì vậy, compatibility cần được đánh giá ở nhiều lớp.

| Loại compatibility | Câu hỏi cần trả lời | Ví dụ thay đổi gây ảnh hưởng |
| --- | --- | --- |
| Source compatibility | Source consumer có compile lại được không? | Xóa method public, đổi kiểu tham số hoặc đổi package. |
| Binary compatibility | Bytecode consumer đã compile có chạy với module mới không? | Xóa method/field mà bytecode cũ tham chiếu. |
| Module compatibility | Module graph có resolve và quyền truy cập có còn hợp lệ không? | Xóa export, đổi module name hoặc thêm dependency bắt buộc. |
| Behavioral compatibility | Hành vi có giữ đúng contract không? | Đổi exception, validation hoặc semantics của method. |
| Service compatibility | Consumer/provider SPI có tiếp tục tương thích không? | Đổi service interface hoặc xóa provider declaration. |
| Operational compatibility | Runtime image và môi trường triển khai có chạy được không? | Thêm module bắt buộc nhưng image cũ không chứa module đó. |

Một thay đổi có thể không phá source compilation nhưng vẫn phá binary compatibility hoặc behavior. Chỉ kiểm tra build của module mới là chưa đủ; cần kiểm tra các consumer đã compile với phiên bản cũ.

## 6. Thay đổi module descriptor có thể phá compatibility

### 6.1. Xóa hoặc thu hẹp exports

Nếu phiên bản cũ khai báo:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
}
~~~

nhưng phiên bản mới xóa export:

~~~java
module com.acme.orders {
}
~~~

consumer không còn được phép truy cập public types trong package đó qua module boundary. Source có thể không compile và bytecode đã compile có thể gặp lỗi truy cập lúc runtime.

Đổi từ unqualified export sang qualified export cũng có thể phá các consumer không nằm trong danh sách target.

### 6.2. Thay đổi requires

Thêm dependency mới:

~~~java
module com.acme.orders {
    requires com.acme.customer;
}
~~~

có thể làm module graph không resolve được nếu module com.acme.customer không có trong module path/runtime image. Dependency mới cũng có thể tạo xung đột package hoặc module name với dependency hiện hữu.

Phân biệt các dạng requires:

- requires M: dependency cần có khi resolve module.
- requires transitive M: các module đọc module hiện tại cũng có thể đọc M thông qua readability propagation.
- requires static M: dependency cần khi compile nhưng có thể không bắt buộc ở runtime nếu module không được yêu cầu bởi đường đi runtime khác.
- requires static transitive M: kết hợp ý nghĩa static và transitive.

Thay requires transitive thành requires có thể ảnh hưởng consumer vốn dựa vào dependency được truyền tiếp để truy cập API của module khác.

### 6.3. Thay đổi opens

Xóa hoặc thu hẹp opens có thể khiến framework không còn deep reflection vào package. Application có thể compile bình thường nhưng lỗi ở runtime khi ORM, serializer hoặc dependency injection framework truy cập private members.

Ngược lại, mở thêm package có thể không phá compatibility chức năng nhưng làm tăng phạm vi reflection access. Đánh giá đây là thay đổi về security/access contract.

### 6.4. Thay đổi uses/provides

Nếu consumer xóa uses hoặc provider xóa provides, service discovery có thể không còn tìm thấy implementation cần thiết.

Một thay đổi trong service interface cũng có thể làm provider cũ không còn implement được service mới hoặc consumer mới không còn tương thích với provider cũ. Hãy kiểm tra cả descriptor và hành vi ServiceLoader.

## 7. Quản lý version theo semantic policy

JPMS không áp đặt một quy tắc semantic versioning cụ thể. Dự án có thể áp dụng SemVer hoặc một policy riêng, nhưng cần định nghĩa rõ cách phân loại thay đổi.

Một policy phổ biến:

- **PATCH:** sửa lỗi không thay đổi public contract và giữ behavior tương thích theo policy.
- **MINOR:** bổ sung API hoặc capability theo hướng tương thích ngược.
- **MAJOR:** thay đổi có thể phá source, binary, module hoặc behavioral compatibility.

Ví dụ:

~~~text
1.4.2 -> 1.4.3   sửa lỗi tương thích
1.4.3 -> 1.5.0   thêm API mới
1.5.0 -> 2.0.0   loại bỏ API cũ hoặc đổi contract
~~~

Đây là quy ước phát hành của dự án, không phải quy tắc được JVM thực thi. ModuleDescriptor.Version có khả năng parse và so sánh version metadata, nhưng không tự áp dụng SemVer policy, không kiểm tra API compatibility và không ngăn một module có version thấp hơn được đặt trên module path.

Không dùng version number làm bằng chứng duy nhất rằng hai module tương thích. Cần kết hợp release notes, API review, module descriptor comparison và test với consumer.

## 8. Phân tích module version và compatibility bằng công cụ

### 8.1. Kiểm tra module descriptor

Với mỗi artifact:

~~~bash
jar --describe-module --file libs/com.acme.orders-1.4.2.jar
~~~

Đối chiếu:

- Module name có ổn định không?
- Version metadata có được ghi không?
- Requires có thay đổi không?
- Exports/qualified exports có thay đổi không?
- Opens, uses và provides có thay đổi không?
- Automatic module name có bị suy ra khác trước không?

Nên lưu descriptor output của mỗi release để reviewer so sánh thay đổi module contract.

### 8.2. Kiểm tra API và dependency

Dùng javap để xem public signature của class:

~~~bash
javap -classpath libs/com.acme.orders-1.4.2.jar \
  com.acme.orders.api.OrderService
~~~

So sánh với bản trước để phát hiện method, constructor, field và kiểu dữ liệu đã thay đổi. Với module path, dùng tùy chọn phù hợp của javap để chỉ rõ module.

Dùng jdeps để kiểm tra dependency/module graph:

~~~bash
jdeps --check com.acme.orders --module-path mods
~~~

jdeps giúp phát hiện dependency, split package và một số vấn đề liên quan module. Nó không chứng minh behavioral compatibility và không thay thế API compatibility checker hoặc test suite.

### 8.3. Kiểm tra internal JDK API

Nếu module dựa vào JDK internal API, dùng:

~~~bash
jdeps --jdk-internals libs/com.acme.orders-1.4.2.jar
~~~

Kết quả giúp phát hiện các tham chiếu có nguy cơ bị thay đổi hoặc encapsulate chặt hơn trong JDK mới. Ưu tiên thay bằng API công khai thay vì duy trì dependency vào implementation detail.

## 9. Kiểm tra consumer trước khi phát hành

Compatibility không chỉ là thuộc tính của provider module; nó còn phụ thuộc vào cách consumer sử dụng API và module descriptor.

Một release pipeline nên kiểm tra:

1. Build module mới từ source sạch.
2. So sánh descriptor mới với descriptor của release trước.
3. Compile các consumer đại diện với artifact mới.
4. Chạy binary compatibility test bằng bytecode đã compile với phiên bản cũ nếu dự án cần hỗ trợ nâng cấp tại chỗ.
5. Chạy integration test với service provider, reflection và module layer.
6. Kiểm tra jlink/runtime image có đủ dependency module mới.
7. Chạy test trên JDK baseline và các JDK được hỗ trợ.
8. Kiểm tra dependency locking/verification để bảo đảm consumer đang dùng đúng artifact.
9. Công bố release notes về thay đổi API, module graph và yêu cầu runtime.

Nếu module là thư viện công khai, nên có một tập consumer compatibility tests hoặc một compatibility checker tự động. Những test này nên đại diện cho cách module được dùng thật, bao gồm cả service registration và module access.

## 10. Chiến lược migration an toàn

Khi cần loại bỏ API hoặc thay đổi module descriptor, có thể thực hiện theo nhiều release:

**Giai đoạn 1 — Bổ sung:** thêm API mới hoặc module mới mà không xóa API cũ. Cập nhật documentation và ví dụ.

**Giai đoạn 2 — Deprecation:** đánh dấu API cũ deprecated, cung cấp hướng chuyển đổi và cảnh báo consumer. Không thu hẹp export hoặc opens khi consumer vẫn cần chúng.

**Giai đoạn 3 — Chuyển consumer:** cập nhật ứng dụng, plugin và module phụ thuộc sang API mới. Dùng dependency constraints/locks để xác định rõ phiên bản được kiểm thử.

**Giai đoạn 4 — Breaking release:** chỉ xóa API hoặc thay đổi module contract trong major release theo policy. Cập nhật module descriptor, module version metadata và release notes.

**Giai đoạn 5 — Runtime verification:** tạo lại runtime image, kiểm tra module list, service binding và test trong môi trường triển khai. Một dependency mới có thể khiến image cũ không còn đủ module.

Không nên phát hành một module có cùng version metadata nhưng descriptor/API thay đổi không được ghi nhận. Version và release notes cần phản ánh thay đổi thực tế để người dùng có thể điều tra và rollback.

## 11. Module version trong runtime image và plugin system

Runtime image tạo bằng jlink chứa tập module được linker chọn. Version metadata trong descriptor có thể được kiểm tra bằng tooling, nhưng image không tự chọn module version mới nhất khi chạy.

Ví dụ:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.acme.app \
  --bind-services \
  --output build/runtime-image
~~~

Nếu module com.acme.orders được nâng version, phải build lại image từ artifact mới và kiểm thử module graph. Không chỉ thay JAR ở một thư mục bên ngoài image rồi giả định image đã cập nhật.

Với plugin system dùng ModuleLayer, các plugin có thể được resolve trong layer riêng. Việc cô lập module version cần được thiết kế cẩn thận:

- Module cùng tên không thể được coi như hai version có thể cùng tồn tại trong một module configuration thông thường.
- Các layer riêng có thể giúp cô lập graph/plugin khác nhau, nhưng class identity phụ thuộc class loader/layer.
- Hai interface có cùng tên đầy đủ nhưng được nạp bởi class loader khác nhau có thể là hai kiểu Java khác nhau.
- Service API nên được chia sẻ từ một module/layer chung nếu host và plugin cần trao đổi object qua interface đó.

Nếu cần chạy đồng thời hai version không tương thích của một thư viện, có thể phải dùng layer/class loader riêng hoặc đổi package/module identity. Đây là quyết định kiến trúc, không thể giải quyết chỉ bằng cách đặt hai JAR version khác nhau trên cùng module path.

## 12. Dependency locking và phát hành có thể tái lập

Để consumer dùng đúng module version đã kiểm thử, hãy quản lý artifact version ở build system.

Với Gradle:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}

dependencies {
    implementation("com.acme:orders:1.4.2")
}
~~~

Sinh/cập nhật lock state có chủ đích và commit lockfiles. Có thể dùng dependency verification để kiểm tra checksum artifact tải về.

Với Maven, dùng version cụ thể và dependencyManagement/BOM để quản lý phiên bản thống nhất giữa các module. Tránh version range hoặc dependency version động trong artifact production nếu không có cơ chế kiểm soát rõ.

Cùng một module name có thể được đóng gói trong nhiều artifact version qua các release khác nhau. Build tool phải chọn một artifact cụ thể; sau đó module resolution kiểm tra module name và dependency graph. Ghi lại cả artifact coordinate/version lẫn module name/version metadata để tránh nhầm lẫn khi điều tra.

## 13. Các lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| requires com.acme.orders không resolve | JAR không có module name đó hoặc module không nằm trên module path | Dùng jar --describe-module và kiểm tra module path. |
| Version metadata bị trống | Modular JAR được đóng gói mà không gắn module version | Dùng jar --module-version khi tạo artifact nếu policy yêu cầu. |
| Đã có version metadata nhưng JVM vẫn chọn artifact không mong muốn | Nhầm version metadata với dependency version resolution | Khóa artifact bằng Gradle/Maven và kiểm tra JAR thực tế được dùng. |
| Consumer compile lỗi sau khi nâng module | API bị xóa/đổi hoặc package không còn export | So sánh API và module descriptor; cập nhật consumer hoặc phát hành migration. |
| Compile thành công nhưng runtime lỗi | Binary/module compatibility hoặc dependency runtime khác compile path | Chạy integration test với đúng runtime module path/image. |
| ServiceLoader không tìm thấy provider | uses/provides hoặc module provider thay đổi | Kiểm tra descriptor, service binding và provider artifact. |
| Framework không còn reflection được | Package opens bị thu hẹp hoặc bị xóa | Xem lại reflection contract; mở đúng package/target nếu cần. |
| Plugin không tương thích sau khi nâng version | Host và plugin dùng API/module contract khác nhau | Chạy plugin compatibility tests và quản lý version API chung. |
| Runtime image thiếu module mới | Image chưa được tạo lại hoặc module set không bao gồm dependency mới | Re-link bằng đúng module path và kiểm tra --list-modules. |

## 14. Quy trình quản lý version module

1. Giữ module name ổn định và tách biệt với artifact version.
2. Chọn policy versioning rõ ràng, ví dụ SemVer, và ghi nhận trong release process.
3. Gắn version metadata vào modular JAR bằng jar --module-version nếu tooling cần.
4. Kiểm tra module descriptor của artifact bằng jar --describe-module.
5. So sánh requires, exports, opens, uses, provides và public API với release trước.
6. Dùng Gradle/Maven để chọn artifact version cụ thể, lock dependency và xác minh checksum.
7. Compile và test consumer với artifact mới, bao gồm binary, service và reflection scenarios.
8. Tạo lại runtime image và kiểm thử trên đúng JDK/OS/architecture.
9. Ghi lại artifact coordinates, module name/version metadata, JDK/toolchain và hash trong release evidence.
10. Công bố breaking changes, migration notes và rollback path nếu module contract thay đổi.

Module version giúp mô tả artifact, còn compatibility được quyết định bởi API, module descriptor, dependency graph và hành vi thực tế. Quản lý tốt cả hai lớp giúp nâng cấp module có thể dự đoán, kiểm thử và rollback được.
