# Kiểm tra dependency graph trước khi publish

## 1. Vì sao phải kiểm tra dependency graph trước khi phát hành?

Với Java Core Module System (JPMS), một thư viện có thể biên dịch thành công ở máy tác giả nhưng vẫn không sử dụng được khi người khác đưa JAR lên module path. Nguyên nhân thường nằm ở những dependency đã được resolve khác nhau, module name không ổn định, package bị che bởi `exports`, dependency thiếu ở runtime hoặc một provider chỉ được phát hiện trong môi trường phát triển.

Vì vậy, trước khi publish một modular JAR, không chỉ chạy build rồi upload artifact. Cần kiểm tra ít nhất hai góc nhìn:

1. **Dependency graph của build tool:** Maven hoặc Gradle đã chọn artifact và phiên bản dependency nào cho từng scope/configuration?
2. **Module graph của JPMS:** Khi biên dịch và chạy, module nào đọc module nào, module nào được resolve và package/service nào được công bố?

Một lần kiểm tra đầy đủ cần bổ sung góc nhìn thứ ba: **artifact thực tế được publish**. Dependency graph trong source project chưa chắc giống dependency graph mà consumer nhìn thấy khi tải artifact từ repository.

Mục tiêu không phải làm graph nhỏ bằng mọi giá. Mục tiêu là một graph có thể giải thích, lặp lại và sử dụng được trong môi trường consumer.

## 2. Phân biệt build dependency graph với JPMS module graph

Ví dụ một thư viện quản lý dữ liệu:

~~~text
com.acme.report.api
    |
    +-- com.acme.report.codec
    |        |
    |        +-- third-party JSON library
    |
    +-- java.sql
~~~

Cần phân biệt các quan hệ:

| Khía cạnh | Được mô tả bằng | Câu hỏi cần trả lời |
|---|---|---|
| Build dependencies | `pom.xml`, `build.gradle`, repository metadata | Artifact nào, version nào, scope nào? |
| JPMS dependencies | `module-info.java` và descriptor đã biên dịch | Module nào cần đọc module khác? |
| Runtime configuration | Module path, root modules, service binding | Module nào thực sự được resolve khi chạy? |
| Public API dependencies | Public method signatures, superclass/interface, exported packages | Consumer có cần dependency này để compile không? |
| Dynamic dependencies | Reflection, `ServiceLoader`, cấu hình, plugin discovery | Có dependency chỉ xuất hiện ở runtime không? |

Một Maven/Gradle dependency không đồng nghĩa một dòng `requires`. Ví dụ thư viện nằm trong classpath truyền thống, dependency thuộc runtimeOnly hoặc dependency chỉ phục vụ annotation processing có thể cần cách xử lý khác khi xây dựng module descriptor.

Ngược lại, `requires java.sql;` là quan hệ module với thành phần JDK; nó không nhất thiết xuất hiện như một dependency bên ngoài trong POM hoặc Gradle configuration.

**Điểm cần nhớ:** build graph giải thích cách artifact được chọn; JPMS graph giải thích cách các named module được liên kết và kiểm soát truy cập.

## 3. Ví dụ modular library và public API dependency

Giả sử module `com.acme.report.api` công bố một API báo cáo:

~~~java
module com.acme.report.api {
    requires transitive java.sql;
    requires com.acme.report.codec;

    exports com.acme.report.api;
}
~~~

Public interface:

~~~java
package com.acme.report.api;

import java.sql.Connection;

public interface ReportService {
    byte[] generate(Connection connection);
}
~~~

Từ descriptor trên:

- `java.sql` nằm trong public contract vì kiểu `Connection` xuất hiện trong method signature.
- `requires transitive java.sql` cho consumer của module này khả năng đọc `java.sql` qua dependency của API.
- `com.acme.report.codec` là dependency implementation trong ví dụ, nên chỉ khai báo `requires` nếu public API không phơi bày kiểu thuộc module codec.
- `com.acme.report.api` là package được export; package codec nội bộ không nhất thiết phải export cho consumer.

Nếu đổi `requires transitive java.sql` thành `requires java.sql`, một consumer chỉ khai báo `requires com.acme.report.api` có thể cần thêm `requires java.sql` khi sử dụng những kiểu SQL trong API.

Ngược lại, không nên dùng `requires transitive` cho mọi dependency. Nó đưa thêm quan hệ readability tới consumer và làm contract giữa module chặt hơn mức cần thiết.

## 4. Kiểm tra graph trên Maven

Với Maven, một bước nền tảng là xem **dependency tree đã resolve**, thay vì chỉ đọc từng dòng trong `pom.xml`.

Chạy tại module hoặc project cần phát hành:

~~~bash
mvn dependency:tree
~~~

Ví dụ output rút gọn:

~~~text
com.acme:report-api:jar:1.4.0
+- com.acme:report-codec:jar:2.2.0:compile
|  \- org.example:json-core:jar:3.0.0:compile
\- org.example:logging-adapter:jar:1.1.0:runtime
~~~

Các điểm cần kiểm tra:

- Artifact/group/version cuối cùng đã được chọn là gì?
- Dependency nào được kéo vào qua dependency bắc cầu?
- Dependency đó có scope `compile`, `runtime`, `test`, `provided` hoặc scope khác?
- Có phiên bản nào bị thay thế bởi dependency mediation hoặc dependency management không?
- Có dependency không cần thiết bị xuất hiện trong production artifact metadata không?

Maven có thể nhận version từ parent POM hoặc BOM qua `dependencyManagement`. Chỉ nhìn dependency declaration trong một module sẽ bỏ sót các quyết định version ở cấp build cha.

Khi cần xem POM đã hợp nhất với parent, profile và property:

~~~bash
mvn help:effective-pom
~~~

Lệnh này hữu ích khi dependency version không được khai báo trực tiếp trong POM hiện tại.

Một build phát hành nên dùng version được quản lý rõ ràng và tránh phụ thuộc vào các repository hay profile chỉ tồn tại trên máy tác giả.

## 5. Maven scope ảnh hưởng tới consumer

Không phải tất cả dependency khai báo trong POM đều cần xuất hiện trong runtime của consumer.

Các scope thường gặp:

| Scope | Ý định chính | Điều cần rà soát |
|---|---|---|
| `compile` | Cần cho biên dịch và thường tham gia dependency của consumer | Có thực sự là API/runtime dependency không? |
| `runtime` | Không cần để compile source hiện tại nhưng cần khi chạy | Runtime test đã bao phủ chưa? |
| `test` | Chỉ phục vụ kiểm thử | Không được vô tình đưa thành dependency chính thức |
| `provided` | Dự kiến môi trường cung cấp khi chạy | Consumer/host có thật sự cung cấp không? |
| `optional` | Không tự truyền thành dependency bắt buộc cho downstream consumer | Tài liệu đã hướng dẫn người dùng bổ sung khi cần chưa? |

Ví dụ một API thư viện cần JSON codec khi chạy. Nếu tác giả đánh dấu codec là optional trong POM nhưng không có cơ chế fallback, consumer có thể tải thư viện thành công rồi gặp lỗi khi gọi tính năng.

Tương tự, đặt driver JDBC trong `test` scope không có nghĩa driver sẽ có trong runtime của consumer. Hãy phân biệt **dependency được dùng để test** với **dependency cần triển khai thực tế**.

Maven scope và JPMS `requires static` không phải là hai cách viết đồng nghĩa. Một bên điều khiển build dependency resolution, bên kia điều khiển quan hệ module khi compile/runtime. Cần xem cả hai nếu có optional integration.

## 6. Kiểm tra dependency graph trên Gradle

Với Gradle, dependency graph được resolve theo từng **configuration**. Một cấu hình thường dùng:

~~~bash
./gradlew dependencies --configuration compileClasspath
~~~

Và configuration runtime:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Trên Windows có thể dùng:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
~~~

Hai graph có thể khác nhau, đặc biệt khi dự án sử dụng `implementation`, `api`, `compileOnly`, `runtimeOnly` hoặc các variant riêng.

Nếu một module có nhiều subproject, thực hiện trên đúng project:

~~~bash
./gradlew :report-api:dependencies --configuration runtimeClasspath
~~~

Khi cần biết tại sao một thư viện hoặc phiên bản xuất hiện:

~~~bash
./gradlew :report-api:dependencyInsight \
  --configuration runtimeClasspath \
  --dependency json-core
~~~

`dependencyInsight` giúp tìm đường phụ thuộc hoặc lý do chọn phiên bản cho một dependency cụ thể, hữu ích khi có conflict resolution.

Không nên kết luận version đã publish bằng cách chỉ đọc dòng `implementation 'group:artifact:version'`. Resolution strategy, dependency constraints, platform/BOM và các variant có thể tác động đến kết quả cuối cùng.

## 7. Gradle api và implementation có ý nghĩa riêng

Với plugin `java-library`, Gradle phân biệt:

~~~groovy
dependencies {
    api 'com.acme:report-contract:1.0.0'
    implementation 'com.acme:report-codec:2.2.0'
    runtimeOnly 'com.acme:report-runtime-adapter:1.1.0'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.0'
}
~~~

Theo ý định của Java Library plugin:

- `api` dành cho dependency cần được phơi bày tới compile classpath của consumer.
- `implementation` dành cho dependency triển khai không cần được phơi bày như compile-time API của consumer.
- `runtimeOnly` là dependency chỉ cần tại runtime.
- `testImplementation` không phải dependency production.

Với JPMS, việc chọn `api` hay `implementation` **không tự viết** `requires transitive` hoặc `requires` vào `module-info.java`. Cần bảo đảm build metadata và descriptor nhất quán với contract thực tế.

Nếu một public signature dùng type từ module khác nhưng build dependency lại bị giấu ở implementation scope, consumer có thể gặp khó khăn khi biên dịch. Ngược lại, đưa mọi dependency vào `api` sẽ phơi bày graph lớn không cần thiết.

## 8. Kiểm tra module descriptor đã đóng gói

Source descriptor chưa phải bằng chứng cuối cùng. Sau khi build, hãy kiểm tra artifact được dự định publish:

~~~bash
jar --describe-module --file build/libs/report-api-1.4.0.jar
~~~

Hoặc với Maven:

~~~bash
jar --describe-module --file target/report-api-1.4.0.jar
~~~

Kết quả của explicit modular JAR cần xác nhận:

- Tên module đúng với tên mà consumer sẽ viết trong `requires`.
- Những `requires` phù hợp với dependency thực tế.
- Package API được `exports` đúng phạm vi.
- Qualified exports/opens và service declarations được đóng gói đúng.
- `module-info.class` thực sự nằm trong artifact.

Có thể xem file trong JAR:

~~~bash
jar --list --file build/libs/report-api-1.4.0.jar
~~~

Với modular JAR thông thường, cần thấy:

~~~text
module-info.class
com/acme/report/api/ReportService.class
~~~

Nếu JAR không có descriptor tường minh, khi đặt trên module path nó có thể trở thành automatic module. Khi đó tên module có thể bắt nguồn từ `Automatic-Module-Name` hoặc tên file; đừng mặc định tên JAR tương đương tên module.

## 9. Kiểm tra module graph bằng jdeps

`jdeps` là công cụ của JDK dùng để phân tích dependency từ bytecode. Sau khi build, có thể chạy:

~~~bash
jdeps --print-module-deps --module-path libs \
  build/libs/report-api-1.4.0.jar
~~~

Hoặc:

~~~bash
jdeps --list-deps --module-path libs \
  build/libs/report-api-1.4.0.jar
~~~

Trong đó:

- `--module-path libs` chỉ nơi tìm các modular dependency cần thiết cho phân tích.
- `--print-module-deps` cho biết danh sách module dependency dạng rút gọn phục vụ các trường hợp như chuẩn bị `jlink`.
- `--list-deps` báo cáo các dependency module/package được phát hiện.

Nếu các dependency được đặt trong những thư mục khác nhau, hãy tạo module path tương ứng. Không nên đoán rằng `jdeps` tự tải các thư viện từ Maven Central hoặc Gradle cache như một build tool.

Với JAR dạng multi-release, cần dùng tùy chọn `--multi-release` phù hợp để phân tích biến thể class dành cho phiên bản Java đích.

Lưu ý quan trọng: `jdeps` chủ yếu dựa trên dependency bytecode tĩnh. Reflection, `ServiceLoader`, class name được đọc từ cấu hình và plugin được nạp động có thể không được phản ánh đầy đủ. Vì thế `jdeps` là công cụ kiểm tra graph, không phải lời cam kết rằng runtime sẽ không cần thêm dependency.

## 10. So sánh requires trong descriptor với dependency thực tế

Ví dụ:

~~~java
module com.acme.report.api {
    requires java.sql;
    requires com.acme.report.codec;

    exports com.acme.report.api;
}
~~~

Một số câu hỏi cần đặt ra:

1. `com.acme.report.codec` có thật trên module path của consumer không?
2. Module name thực tế của codec có đúng như descriptor nêu không?
3. Dependency codec là explicit module hay automatic module?
4. Public API có sử dụng kiểu từ codec không?
5. Nếu có, consumer có cần `requires transitive` thay cho `requires`?
6. Nếu codec là optional feature, liệu module descriptor có đang yêu cầu nó bắt buộc khi chạy không?
7. Nếu codec chỉ được nạp động qua service/provider, liệu thiết kế có cần trực tiếp `requires` implementation module không?

Không xóa `requires` chỉ vì một báo cáo static analysis không nhìn thấy bytecode sử dụng dependency. Một dependency có thể cần cho reflection, service discovery hoặc code chỉ hoạt động theo configuration.

Ngược lại, một dependency còn ở POM nhưng không còn được sử dụng có thể làm tăng graph và tăng rủi ro không cần thiết.

## 11. Kiểm tra module graph tại runtime

Nếu thư viện có ứng dụng mẫu hoặc consumer smoke test, dùng module path và khả năng quan sát resolution của Java launcher:

~~~bash
java --show-module-resolution \
  --module-path mods \
  -m com.acme.report.demo/com.acme.report.demo.Main
~~~

Lệnh hiển thị thông tin về các module được resolve khi JVM chuẩn bị chạy ứng dụng.

Chú ý:

- Root module và dependency theo `requires`.
- Những module được đưa vào do service binding, nếu có.
- Dependency từ runtime image như `java.base`, `java.sql` và các module JDK khác.
- Những module bên thứ ba thực sự được tìm thấy trên module path.

Có thể kiểm tra module có thể quan sát bằng:

~~~bash
java --module-path mods --list-modules
~~~

Và xem descriptor của module cụ thể:

~~~bash
java --module-path mods \
  --describe-module com.acme.report.api
~~~

`--list-modules` và `--describe-module` là công cụ khám phá module; một module có thể observable mà chưa chắc đã được resolve trong graph của lần chạy cụ thể. `--show-module-resolution` trả lời câu hỏi về lần chạy cụ thể tốt hơn.

## 12. Không để build thành công che giấu lỗi runtime

Một build có thể thành công vì IDE hoặc test classpath vô tình chứa thêm dependency, trong khi consumer chạy trên module path bị thiếu module.

Một ví dụ thường gặp:

~~~java
module com.acme.report.app {
    requires com.acme.report.api;
}
~~~

Nhưng `com.acme.report.api` lại có:

~~~java
requires com.acme.report.codec;
~~~

Nếu publisher không công bố hoặc không cung cấp đúng codec artifact, consumer có thể nhận lỗi:

~~~text
java.lang.module.FindException:
Module com.acme.report.codec not found, required by com.acme.report.api
~~~

Đây không phải lỗi của `exports`. Đây là lỗi module dependency chưa thể được phân giải.

Do đó, trước khi publish, cần thử **tải các artifact dự định phát hành** bằng một project consumer độc lập, sử dụng module path tương tự môi trường downstream. Không chỉ chạy test trên source tree nơi mọi output module đã được IDE làm sẵn.

## 13. Duplicate module name và split package

Hai vấn đề thường gây lỗi khi chuyển dependency từ classpath sang module path:

### 13.1. Duplicate module name

Hai JAR có thể được nhận diện bằng cùng module name dù file name khác nhau, chẳng hạn:

~~~text
libs/report-codec-1.0.jar
libs/report-codec-2.0.jar
~~~

Nếu cả hai công bố module name `com.acme.report.codec`, module finder/module path có thể gặp xung đột hoặc một artifact không được chọn như người dùng mong đợi, tùy vị trí và cách cấu hình.

Hãy bảo đảm module path của consumer không chứa nhiều bản artifact cạnh tranh cho cùng một module. Rà soát những dependency transitive dẫn tới việc trộn version cũ và mới.

### 13.2. Split package

Giả sử hai named module cùng chứa:

~~~text
com.acme.report.common
~~~

Khi các module này cùng tham gia cấu hình, JPMS có thể phát hiện xung đột package ownership hoặc làm consumer không thể đọc đồng thời những module chứa cùng package đó.

Đừng giải quyết split package bằng cách thay `requires` một cách tùy tiện. Thường cần chỉnh layout source/module để một package thuộc một module xác định, hoặc chuyển contract dùng chung vào module API rõ ràng.

Để hỗ trợ phát hiện vấn đề ở cấu hình module path, có thể chạy:

~~~bash
java --module-path mods --validate-modules
~~~

Lệnh này kiểm tra module path ở mức module metadata và báo một số vấn đề như xung đột module/package. Nó không thay thế smoke test runtime và không bao phủ mọi xung đột khi các module được nạp theo cách động khác.

## 14. Kiểm tra automatic module và tên module ổn định

Một JAR chưa có `module-info.class` khi đặt trên module path có thể được coi là automatic module.

Tên automatic module có thể được xác định bởi:

- Manifest attribute `Automatic-Module-Name`, nếu có.
- Tên file JAR được suy ra thành module name khi không có thuộc tính trên.

Ví dụ dependency:

~~~text
legacy-serializer-2.4.jar
~~~

có thể được suy ra tên module từ file. Khi nhà cung cấp đổi tên artifact, module name suy ra có thể thay đổi, làm dòng `requires` của consumer bị ảnh hưởng.

Trước khi publish thư viện phụ thuộc một automatic module:

~~~bash
jar --describe-module --file libs/legacy-serializer-2.4.jar
~~~

Hãy xác nhận module name đúng như đã dùng trong `module-info.java`.

Nếu tự publish một JAR chưa thể chuyển thành explicit module, có thể cân nhắc khai báo `Automatic-Module-Name` ổn định trong manifest để giảm rủi ro tên suy ra từ file. Đây là bước chuyển tiếp; nó không thay thế việc thiết kế descriptor tường minh cho module.

## 15. Kiểm tra dependency lộ qua public API

Không chỉ đọc POM/Gradle graph, hãy kiểm tra public signatures nằm trong những package được export.

Ví dụ:

~~~java
package com.acme.report.api;

import com.thirdparty.json.JsonNode;

public interface ReportParser {
    JsonNode parse(String text);
}
~~~

Nếu `JsonNode` thuộc một dependency bên ngoài, consumer dùng interface sẽ cần nhìn thấy kiểu đó. Trong JPMS, đây có thể là dấu hiệu cần module readability được truyền tiếp bằng `requires transitive`.

Một giải pháp kiến trúc khác là giữ dependency bên ngoài ở implementation layer và chỉ công bố kiểu do API module sở hữu:

~~~java
package com.acme.report.api;

public record ReportDocument(String title, String content) {
}
~~~

Nếu API trả về `ReportDocument`, consumer không cần biết thư viện JSON cụ thể được dùng để parse.

Checklist API leak:

- Public return/parameter type có nằm ngoài module API không?
- Checked exception có thuộc dependency private không?
- Generic arguments có chứa kiểu implementation không?
- Exported interfaces có kế thừa API thuộc module mà consumer không thể đọc không?
- Gradle `api` và Maven dependency metadata có phản ánh đúng những dependency được công bố không?

Public API và dependency graph cần tương thích; nếu không, consumer có thể gặp lỗi compile dù publisher vẫn build thành công.

## 16. ServiceLoader, reflection và dependency động

Một graph tĩnh thường không thể giải thích toàn bộ hành vi runtime.

### 16.1. ServiceLoader

Consumer có thể khai báo:

~~~java
module com.acme.report.app {
    requires com.acme.report.api;
    uses com.acme.report.spi.ReportProvider;
}
~~~

Provider module:

~~~java
module com.acme.report.csv {
    requires com.acme.report.api;

    provides com.acme.report.spi.ReportProvider
        with com.acme.report.csv.CsvReportProvider;
}
~~~

Provider module cần được đưa vào configuration/layer mà `ServiceLoader` sử dụng. Nếu thư viện công bố service API nhưng không tự cung cấp provider, phải hướng dẫn consumer thêm provider artifact phù hợp.

Không nên thêm `requires com.acme.report.csv` vào API module chỉ để ép một provider cụ thể tồn tại. Điều đó tạo coupling ngược giữa contract và implementation.

### 16.2. Reflection

Framework có thể cần `opens` hoặc qualified opens để truy cập model class.

~~~java
module com.acme.report.api {
    exports com.acme.report.api;
    opens com.acme.report.model to com.fasterxml.jackson.databind;
}
~~~

Cấu hình build có thể chứa Jackson dependency nhưng runtime vẫn lỗi reflection nếu module graph/opens không đúng. Graph kiểm tra trước publish nên được kết hợp với integration test thực tế.

### 16.3. Dependency chỉ dùng trong configuration

Tên class do plugin system đọc từ file cấu hình có thể không xuất hiện trong `jdeps`. Khi publish, cần tài liệu và test cho tình huống đó thay vì dùng static analysis để loại bỏ dependency động.

## 17. Quản lý version và tính lặp lại của dependency graph

Trước khi publish, cần biết graph sẽ được resolve ra sao ở máy khác và ở lần build khác.

Với Maven:

- Sử dụng version rõ ràng và dependency management nhất quán.
- Không phụ thuộc vào SNAPSHOT hoặc version thay đổi ngoài ý muốn trong release ổn định.
- Kiểm tra các active profiles có ảnh hưởng tới dependency.
- Xem effective POM và dependency tree của đúng release configuration.

Với Gradle:

- Kiểm tra resolved graph của `compileClasspath` và `runtimeClasspath`.
- Cân nhắc dependency locking/verification theo chính sách dự án.
- Kiểm tra constraints, platforms/BOM và resolution strategy.
- Tránh để dynamic/changing versions làm thay đổi graph giữa các lần publish.

Version conflict có thể không gây compile error ngay nhưng thay đổi behavior hoặc public ABI khi consumer resolve dependency qua những constraint khác.

Khi cần phát hành ổn định, lưu lại phiên bản plugin, JDK/toolchain và các dependency quan trọng trong CI build log hoặc release metadata để có thể tái tạo vấn đề.

## 18. Dependency graph và rủi ro chuỗi cung ứng

Việc kiểm tra graph cũng giúp phát hiện những dependency không cần thiết, phiên bản đã lỗi thời hoặc artifact không rõ nguồn gốc.

Các bước có ích:

1. Xác định dependency trực tiếp và transitive thực tế.
2. Loại dependency test/dev khỏi production graph khi không cần.
3. Kiểm tra license policy và provenance của artifact theo quy định tổ chức.
4. Chạy quét lỗ hổng trên graph đã resolve bằng công cụ được dự án chấp nhận.
5. Nếu quy trình release yêu cầu, tạo SBOM cho tập dependency thực sự sử dụng.
6. Ghi nhận các ngoại lệ tạm thời và owner có trách nhiệm xử lý.

Cần phân biệt quét vulnerability với JPMS resolution. Module graph hợp lệ không chứng minh dependency an toàn; vulnerability scan sạch cũng không chứng minh module name, exports hoặc runtime service binding đúng.

Đây là những cổng kiểm tra bổ sung, không phải thay thế cho việc chạy ứng dụng trên module path.

## 19. Kiểm tra artifact publish thay vì chỉ kiểm tra source

Sau khi build, cần xác nhận nội dung JAR cuối cùng khớp với những gì consumer sẽ tải.

Ví dụ với Maven:

~~~bash
mvn -B -ntp clean verify
~~~

Với Gradle:

~~~bash
./gradlew clean build
~~~

Tiếp theo:

~~~bash
jar --describe-module --file path/to/published-artifact.jar
jar --list --file path/to/published-artifact.jar
~~~

Nếu release dùng một bản copy/staging artifact, kiểm tra **chính file staging** trước khi publish. Tránh tình huống test trên artifact A nhưng upload artifact B do task hoặc profile khác tạo ra.

Cũng cần kiểm tra metadata xuất bản:

- Maven POM có đúng group/artifact/version không?
- Dependency scope và optional flags có phản ánh nhu cầu consumer không?
- Gradle Module Metadata (nếu có) có đúng các variant và dependency không?
- Artifact và metadata đã được publish cùng version chưa?
- Có dependency nội bộ chỉ tồn tại trong repository công ty khiến consumer bên ngoài không thể tải không?

Một modular JAR đúng descriptor nhưng POM thiếu dependency bắt buộc vẫn có thể gây lỗi downstream.

## 20. Consumer smoke test trước publish

Một phép thử rất có giá trị là tạo **consumer project nhỏ nằm ngoài module nguồn**.

Ví dụ:

~~~text
consumer-smoke/
└── src/
    ├── module-info.java
    └── com/acme/smoke/Main.java
~~~

Descriptor:

~~~java
module com.acme.smoke {
    requires com.acme.report.api;
}
~~~

Main:

~~~java
package com.acme.smoke;

import com.acme.report.api.ReportService;

public final class Main {
    public static void main(String[] args) {
        System.out.println("API visible: "
                + ReportService.class.getModule().getName());
    }
}
~~~

Biên dịch với artifact staging và dependency modules:

~~~bash
javac --module-path dist/modules \
  -d out/consumer \
  consumer-smoke/src/module-info.java \
  consumer-smoke/src/com/acme/smoke/Main.java
~~~

Để chạy từ exploded module output, đặt `out/consumer` vào một module path entry thích hợp hoặc đóng gói consumer thành modular JAR. Chẳng hạn:

~~~bash
jar --create --file dist/modules/com.acme.smoke.jar \
  -C out/consumer .

java --module-path dist/modules \
  -m com.acme.smoke/com.acme.smoke.Main
~~~

Thư mục `dist/modules` trong ví dụ phải tồn tại và chứa JAR hoặc exploded modules thực sự cần thiết, bao gồm module API và dependency bắt buộc.

Smoke test cần làm rõ:

- Consumer có compile với public API không?
- Tên module đúng như tài liệu không?
- Các module dependency có được resolve không?
- Có lỗi split package/duplicate module name không?
- Public signature có tham chiếu type mà consumer không đọc được không?
- Nếu service/reflection là một phần contract, có thể thực thi luồng đó không?

Ưu tiên dùng artifact đã staging thay vì output trong project nguồn, vì consumer phải đại diện cho cách người dùng thật tải thư viện.

## 21. Checklist CI dành cho modular library

Một pipeline phát hành có thể gồm các cổng kiểm tra sau:

| Giai đoạn | Kiểm tra | Bằng chứng mong muốn |
|---|---|---|
| Build | Compile/package bằng JDK mục tiêu | Build thành công, artifact ổn định |
| Unit/integration tests | Kiểm thử API và implementation | Test results |
| Maven/Gradle graph | Resolve compile/runtime dependencies | Dependency tree hoặc configuration report |
| Artifact descriptor | `jar --describe-module` | Tên module và requires/exports đúng |
| Module analysis | `jdeps` với module path đã chuẩn bị | Dependency module có thể giải thích |
| Module validation | `java --validate-modules` | Không có lỗi module path được công cụ phát hiện |
| Runtime resolution | `--show-module-resolution` với demo app | Module graph khởi động được |
| Consumer smoke | Compile/run dùng staging artifact | Public API dùng được qua module path |
| Dynamic behavior | ServiceLoader/reflection/plugin scenarios | Provider và reflection hoạt động nếu được hỗ trợ |
| Publication metadata | POM/Gradle metadata/version | Downstream có thể tải đúng artifact/dependency |

Không nhất thiết mọi project đều cần một công cụ CI riêng cho từng hàng. Nhưng các rủi ro chính phải được kiểm tra trước publish bằng test hoặc command có thể chạy lại.

Ví dụ pipeline đơn giản nên tối thiểu build, chạy test, xem dependency graph, kiểm tra descriptor của artifact và thực hiện consumer smoke test. Các phần như security scanning hoặc SBOM tùy chính sách release.

## 22. Triệu chứng thường gặp khi graph không đúng

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| `module not found: X` | Dependency bắt buộc thiếu trên module path hoặc module name sai | Xem descriptor, dependency tree và module path |
| Consumer compile fail dù publisher compile pass | Public API lộ type không đọc được hoặc thiếu metadata dependency | Kiểm tra exported API, `requires transitive`, POM/Gradle variants |
| `package ... is not visible` | Package không export hoặc consumer chưa đọc module | `requires`, `exports`, qualified exports |
| Provider không được tìm thấy | Provider module chưa được resolve hoặc thiếu `provides` | `uses`/`provides`, `--show-module-resolution`, `ServiceLoader` |
| Reflection báo `InaccessibleObjectException` | Package chưa `opens` cho module framework | Xem `opens` và runtime flags |
| Lỗi split package | Hai named module có package trùng tên | Rà soát package contents và module path |
| Bị chọn sai phiên bản thư viện | Maven mediation, Gradle resolution hoặc metadata sai | `dependency:tree`, `dependencyInsight` |
| Works locally, fails after publish | Dependency chỉ có trong IDE/test/source tree hoặc metadata không đầy đủ | Test consumer từ staging artifact |
| Automatic module name thay đổi | Tên được suy ra từ JAR filename | `jar --describe-module`, manifest, lock module names |
| Jdeps không thấy dependency động | Reflection, service provider, config-driven class | Runtime/integration tests |

Đừng sửa mọi lỗi bằng cách thêm tất cả JAR lên classpath hoặc cấp `--add-reads`/`--add-exports` đại trà. Cần xác định graph bị thiếu dependency, sai module name, sai public contract hay bị giới hạn truy cập package.

## 23. Quy trình thực hành trước khi nhấn publish

Một quy trình có thể áp dụng cho cả Maven và Gradle:

1. **Build sạch bằng JDK dự định hỗ trợ.** Bảo đảm `module-info.class` được tạo.
2. **Resolve dependency graph.** Xem compile và runtime dependencies của đúng project/version.
3. **Xác định dependency bắc cầu.** Giải thích nguồn gốc các thư viện quan trọng, nhất là thư viện có nhiều phiên bản.
4. **Kiểm tra public API.** Những type trong exported packages phải sử dụng được từ consumer.
5. **Đọc descriptor của artifact cuối.** Xác nhận module name, `requires`, `exports`, `opens`, `uses`, `provides`.
6. **Dùng `jdeps` phân tích dependency tĩnh.** Cung cấp module path đầy đủ để tránh kết luận sai.
7. **Kiểm tra module path.** Phát hiện duplicate module name hoặc split package.
8. **Chạy runtime demo có `--show-module-resolution`.** Xác nhận module graph được phân giải như dự kiến.
9. **Kiểm thử dependency động.** Provider, reflection và plugin loading nếu sản phẩm có hỗ trợ.
10. **Chạy consumer smoke test từ staging artifact.** Không dựa vào classpath tiện lợi của IDE.
11. **Kiểm tra metadata xuất bản.** POM/Gradle variants phải cung cấp dependency phù hợp.
12. **Lưu bằng chứng release.** Ghi lại JDK/toolchain, resolved graph và các ngoại lệ được chấp nhận.

Nếu một bước phát hiện thiếu dependency, sửa từ đúng nguồn: descriptor, build configuration, published metadata, service registration hoặc thiết kế API. Sau đó chạy lại quy trình trước khi publish.

## 24. Ghi nhớ

Kiểm tra dependency graph trước khi publish không chỉ là xem thư viện nào xuất hiện trong `pom.xml` hoặc `build.gradle`. Với JPMS cần đối chiếu đồng thời:

- **Build graph:** Maven/Gradle đã chọn artifact, version và scope nào?
- **Module graph:** `module-info.class` khai báo quan hệ `requires` và quyền truy cập gì?
- **Runtime graph:** JVM thực sự resolve những module nào qua module path?
- **Published artifact:** Consumer có thể tải, compile và chạy được bằng artifact/metadata được phát hành không?

Dùng `mvn dependency:tree` hoặc Gradle `dependencies`/`dependencyInsight` để hiểu build graph; dùng `jar --describe-module`, `jdeps` và `java --show-module-resolution` để hiểu JPMS; cuối cùng dùng consumer smoke test để xác nhận contract và dependency thực sự dùng được.

**Chỉ nên publish khi dependency graph đã có thể giải thích, module graph có thể resolve, public API không rò rỉ dependency ngoài ý muốn và artifact cuối đã được thử từ góc nhìn consumer.**
