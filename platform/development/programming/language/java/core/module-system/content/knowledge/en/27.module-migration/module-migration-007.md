# Duy trì test và plugin build trong giai đoạn chuyển đổi

Khi chuyển một dự án Java từ **classpath** sang **Java Platform Module System (JPMS)**, mục tiêu không chỉ là biên dịch thành công `module-info.java`. Hệ thống còn phải giữ được các bài **unit test**, **integration test**, **plugin test**, tác vụ build bằng Maven/Gradle và cơ chế tìm plugin ở runtime.

Quá trình migration nên diễn ra theo từng bước, với một đường build đang hoạt động làm mốc đối chiếu. Nếu chuyển đồng thời toàn bộ dependency, test runner và plugin loader sang module path, khi xảy ra lỗi sẽ rất khó xác định nguyên nhân. Cách thực tế hơn là kiểm soát riêng ba luồng: **compile ứng dụng**, **chạy test** và **đóng gói/nạp plugin**.

## 1. Vì sao test và plugin dễ hỏng khi modularize?

Trên classpath, các class thường thuộc unnamed module của class loader. Một framework test hoặc plugin có thể dùng reflection để tìm constructor, gọi method không public và quét classpath hoặc file `META-INF/services`.

Trong named module, JPMS bổ sung các ràng buộc:

- Module muốn sử dụng API của module khác cần có **readability**, thường qua `requires`.
- Package muốn cho module khác truy cập kiểu public cần `exports`.
- Package muốn framework sử dụng **deep reflection** cần `opens` phù hợp.
- Provider trong named module phải được khai báo bằng `provides ... with ...` khi dùng cơ chế module service.
- Module trên module path phải được **resolve**; chỉ đặt JAR trong một thư mục chưa đảm bảo nó đã trở thành module tham gia cấu hình chạy.
- Một package không thể tùy tiện bị chia giữa nhiều named modules trong cùng cấu hình.

Vì vậy, cùng một test có thể chạy khi mọi JAR ở classpath nhưng thất bại sau khi chuyển thư viện chính sang module path.

## 2. Phân loại ba phạm vi cần giữ hoạt động

| Phạm vi | Ví dụ | Điều cần kiểm tra |
|---|---|---|
| Build ứng dụng | `javac`, Maven Compiler, Gradle Java plugin | Module path, descriptor, dependency, tên module |
| Chạy test | JUnit, Mockito, integration tests | Test classpath/module path, quyền reflection, test fixtures |
| Plugin build và plugin runtime | Maven/Gradle plugins, service providers, plugin JAR | Class loader của build tool, metadata đóng gói, `ServiceLoader` và module layer |

“Plugin build” có thể chỉ **plugin thực thi trong công cụ build** như Maven/Gradle plugin, hoặc **plugin artifact do ứng dụng xây dựng và nạp khi chạy**. Hai trường hợp có vòng đời khác nhau.

Plugin của Maven/Gradle thường thực thi trong môi trường riêng của build tool, không tự động trở thành module mà ứng dụng đọc. Ngược lại, plugin runtime dùng JPMS có thể cần `uses`, `provides`, module path, service binding hoặc module layer.

## 3. Đặt baseline trước khi chuyển đổi

Trước khi thêm `module-info.java`, nên xác định một trạng thái build ổn định:

1. Build ứng dụng từ clean workspace.
2. Chạy đầy đủ unit tests và integration tests đang có.
3. Đóng gói các JAR được ứng dụng phân phối.
4. Chạy một kịch bản tải plugin thực tế.
5. Ghi lại các module/JAR, JDK, dependency và công cụ build đang sử dụng.

Ví dụ với Maven:

    mvn clean verify

Ví dụ với Gradle:

    ./gradlew clean build

Nếu dự án có tác vụ kiểm thử riêng hoặc integration test không thuộc pipeline mặc định, bổ sung các tác vụ đó vào baseline. Không giả định `build` hoặc `verify` luôn bao gồm mọi test của mọi dự án.

Một baseline hữu ích không chỉ ghi “BUILD SUCCESS”, mà còn ghi test nào đã chạy và plugin nào thực sự được phát hiện, khởi tạo.

## 4. Chuyển đổi theo tầng, không đổi toàn bộ một lần

Có thể chia migration thành các bước:

**Bước A — Chuẩn hóa dependency.** Xác định thư viện nào đã có explicit module, thư viện nào trở thành automatic module và thư viện nào còn ở classpath. Kiểm tra package trùng tên giữa các artifact.

**Bước B — Modularize phần lõi.** Thêm `module-info.java` cho module API hoặc module core có ranh giới rõ. Tránh export package internal chỉ để làm toàn bộ test chạy nhanh.

**Bước C — Giữ test hiện hữu.** Tạm dùng cấu hình test classpath hoặc thêm các tùy chọn runtime dành riêng cho test, rồi từng bước chuyển sang kiểm thử trong named module nếu cần.

**Bước D — Chuyển plugin.** Chuẩn hóa service API, service provider, cách đóng gói JAR và cách module được resolve. Có thể giữ plugin cũ ở classpath trong giai đoạn trung gian nếu kiến trúc hỗ trợ.

**Bước E — Thu hẹp ngoại lệ.** Khi test và plugin đã chạy ổn định, giảm `--add-opens`, `--add-exports` và `--add-reads` không còn cần thiết.

Mỗi bước nên có một lệnh build/test có thể lặp lại. Việc có hai cách khởi chạy trong thời gian chuyển tiếp là hợp lý nếu được kiểm soát và có mục tiêu kết thúc rõ ràng.

## 5. Ví dụ một ứng dụng modular tối thiểu

Giả sử ứng dụng có module core:

    src/
      com.example.core/
        module-info.java
        com/example/core/api/Calculator.java
        com/example/core/internal/DefaultCalculator.java
      com.example.app/
        module-info.java
        com/example/app/Main.java

Module core:

    module com.example.core {
        exports com.example.core.api;
    }

API của core:

    package com.example.core.api;

    public interface Calculator {
        int add(int a, int b);
    }

Module app:

    module com.example.app {
        requires com.example.core;
    }

Biên dịch theo module source path:

    javac --module-source-path src -d out -m com.example.core,com.example.app

Chạy:

    java --module-path out -m com.example.app/com.example.app.Main

Khi bước này hoạt động, mới cần đưa test runner và plugin vào cấu hình tương ứng. Đừng thay đổi tất cả đường dẫn build/test trước khi xác nhận module graph của ứng dụng.

## 6. Giữ unit test chạy khi test vẫn ở classpath

Nhiều dự án có test nằm dưới `src/test/java` và được framework test nạp qua classpath. Trong giai đoạn đầu, có thể giữ test ở unnamed module trong khi production code đã trở thành named module.

Đây là một phương án chuyển tiếp, không phải trạng thái tự động tương đương với chạy test đúng quy tắc JPMS.

Ví dụ, code test có thể gọi API public của core nếu package được export:

    module com.example.core {
        exports com.example.core.api;
    }

Nếu test cố truy cập field private trong package internal, việc `exports` API public không đủ để cho phép deep reflection. Cấu hình riêng cho JVM kiểm thử có thể cần:

    --add-opens=com.example.core/com.example.core.internal=ALL-UNNAMED

Lệnh trên mở package internal của `com.example.core` cho code trong unnamed modules, chẳng hạn một test framework đang chạy trên classpath.

Nếu framework test nằm trong **named module**, `ALL-UNNAMED` không cấp quyền cho nó. Khi đó target phải là module name thực tế của framework gọi reflection.

Chỉ thêm quyền vào JVM test đang cần, không nhất thiết thêm vào JVM production.

## 7. Khi nào dùng --patch-module cho test?

Một số test cần truy cập các thành viên package-private của code production. Khi code nằm trong named module, việc đặt test ở cùng tên package nhưng trong unnamed module không biến hai bên thành cùng runtime package.

JPMS hỗ trợ tùy chọn `--patch-module` để bổ sung class/resource vào một module cho quá trình biên dịch hoặc chạy:

    --patch-module com.example.core=path/to/test-classes

Ý tưởng là cho test class trở thành một phần được patch của module `com.example.core` trong môi trường test. Điều này có thể giúp các test cùng package truy cập package-private member mà không phải export package cho toàn bộ ứng dụng.

Tuy nhiên, cần phân biệt:

- `--patch-module` tác động đến nội dung module được patch.
- `--add-reads` bổ sung quan hệ đọc giữa module.
- `--add-opens` mở package cho deep reflection.
- `--add-exports` bổ sung quyền truy cập kiểu public của package.

Nếu test class được patch vào named module nhưng JUnit hoặc test framework đang nằm trên classpath, test module có thể cần readability tới unnamed modules trong JVM test:

    --add-reads=com.example.core=ALL-UNNAMED

Các flag này chỉ áp dụng khi cấu trúc test thực sự yêu cầu. Nên để Maven Surefire, Gradle Test hoặc test runner quản lý chúng khi công cụ đã hỗ trợ mô hình modular test; tránh sao chép một bộ flag chung không xét module path và class loader thực tế.

## 8. Reflection trong test: exports không thay thế opens

Unit test và framework có thể dùng reflection để gọi constructor hoặc đọc field private:

    Field field = target.getClass()
            .getDeclaredField("id");

    field.setAccessible(true);

Nếu class thuộc package chưa được mở cho module của code reflection, chương trình có thể ném:

    java.lang.reflect.InaccessibleObjectException

Cách khắc phục là mở package phù hợp:

    --add-opens=com.example.core/com.example.core.internal=ALL-UNNAMED

Hoặc, nếu dự án chủ động cho phép framework ở named module `com.example.test.framework` truy cập:

    opens com.example.core.internal to com.example.test.framework;

trong `module-info.java` của module nguồn.

Nếu quyền này chỉ phục vụ kiểm thử, ưu tiên cấu hình tại JVM test thay vì mở rộng hợp đồng module production.

Không dùng `--add-opens` để sửa một lỗi compile-time `package ... is not visible` khi test import kiểu public: trường hợp đó phải kiểm tra readability và `exports`.

## 9. Cấu hình Maven trong giai đoạn chuyển tiếp

Với Maven, dự án có `module-info.java` thường được Maven Compiler Plugin và Maven Surefire Plugin xử lý theo cấu hình module phù hợp với phiên bản plugin và JDK.

Một số dự án chọn tạm chạy test trên classpath trong quá trình migration. Ví dụ cấu hình Surefire:

    <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <configuration>
            <useModulePath>false</useModulePath>
        </configuration>
    </plugin>

Đây chỉ là **một lựa chọn chuyển tiếp**: test có thể chạy trong môi trường classpath mà không kiểm tra đầy đủ các ràng buộc module path của production.

Khi cần chạy test với JPMS nghiêm ngặt hơn, có thể để Surefire dùng module path và thiết lập cấu hình patch/reads/opens thích hợp cho cấu trúc test. Các tùy chọn phụ thuộc vào cách test được biên dịch, việc test có `module-info.java` riêng hay không và phiên bản plugin.

Có thể truyền VM options dành riêng cho test qua cấu hình `argLine` trong những trường hợp phù hợp:

    <configuration>
        <argLine>
            --add-opens=com.example.core/com.example.core.internal=ALL-UNNAMED
        </argLine>
    </configuration>

Chỉ sử dụng ví dụ này nếu code reflection thực sự chạy trong unnamed module. Không nên thay `argLine` sẵn có chứa tùy chọn Java agent, JaCoCo hoặc cấu hình khác mà không hợp nhất chúng.

Khi vận hành Maven, hãy phân biệt:

- `maven-compiler-plugin`: biên dịch source/module.
- `maven-surefire-plugin`: thường chạy unit tests.
- `maven-failsafe-plugin`: thường chạy integration tests khi dự án đã cấu hình.
- Các plugin đóng gói: tạo JAR, distribution, image hoặc artifact plugin.

Một bản build có thể biên dịch thành công nhưng test runner hoặc bản JAR xuất ra vẫn cần sửa riêng.

## 10. Cấu hình Gradle trong giai đoạn chuyển tiếp

Với Gradle và Java plugin, có thể bật cơ chế suy luận module path cho code có module descriptor:

    plugins {
        id 'java'
    }

    java {
        modularity.inferModulePath = true
    }

Cấu hình kiểm thử dùng JUnit Platform, nếu dự án đang dùng JUnit Jupiter:

    tasks.withType(Test).configureEach {
        useJUnitPlatform()
    }

Nếu test framework chạy trên classpath và cần deep reflection, có thể thêm flag chỉ cho test:

    tasks.withType(Test).configureEach {
        useJUnitPlatform()
        jvmArgs(
            '--add-opens=com.example.core/com.example.core.internal=ALL-UNNAMED'
        )
    }

Tùy vào Gradle, JDK, source set và cách module được biên dịch, test có thể cần cấu hình patch module hoặc module path bổ sung. Không nên giả định riêng `inferModulePath = true` tự cấu hình chính xác mọi test framework và plugin.

Các Gradle plugins thực thi trong quá trình build có class loader và dependencies riêng do Gradle quản lý. Đừng nhầm plugin classpath của Gradle với module path của ứng dụng mà task Java đang biên dịch/chạy.

## 11. Tách build plugin của công cụ và runtime plugin

Có hai loại “plugin” thường bị gộp chung khi migration:

**Build-tool plugin** chạy trong Maven hoặc Gradle để làm việc như compile, generate source, test, package, publish. Ví dụ Maven Compiler/Surefire hoặc Gradle Java/Application plugin. Chúng phụ thuộc vào API và runtime của công cụ build.

**Runtime plugin** là một thành phần ứng dụng tìm và nạp lúc chạy, ví dụ qua `ServiceLoader` hoặc `ModuleLayer`.

Chuyển ứng dụng sang JPMS không yêu cầu mọi build-tool plugin đều có module-info riêng trong dự án. Nhưng plugin phải hỗ trợ JDK/build tool đang sử dụng và truyền đúng compiler/test VM options nếu có task modular.

Đối với runtime plugin, cần quản lý service API, cách đăng ký provider, module path hoặc plugin class loader. Hai công việc này có thể được thực hiện theo hai nhánh riêng trong kế hoạch migration.

## 12. Ví dụ ServiceLoader để giữ cơ chế plugin

Giả sử ứng dụng hỗ trợ plugin xuất báo cáo.

Service interface trong module API:

    package com.example.spi;

    public interface ReportExporter {
        String format();
        byte[] export(String content);
    }

Descriptor API:

    module com.example.spi {
        exports com.example.spi;
    }

Một provider plugin triển khai service:

    package com.example.csv;

    import com.example.spi.ReportExporter;
    import java.nio.charset.StandardCharsets;

    public final class CsvExporter implements ReportExporter {
        public CsvExporter() {}

        @Override
        public String format() {
            return "csv";
        }

        @Override
        public byte[] export(String content) {
            return content.getBytes(StandardCharsets.UTF_8);
        }
    }

Descriptor provider:

    module com.example.csv.provider {
        requires com.example.spi;
        provides com.example.spi.ReportExporter
            with com.example.csv.CsvExporter;
    }

Descriptor ứng dụng:

    module com.example.app {
        requires com.example.spi;
        uses com.example.spi.ReportExporter;
    }

Ứng dụng tìm plugin:

    ServiceLoader<ReportExporter> exporters =
            ServiceLoader.load(ReportExporter.class);

    for (ReportExporter exporter : exporters) {
        System.out.println(exporter.format());
    }

Ở cách này, app không cần `requires com.example.csv.provider;` chỉ để gọi service theo `ServiceLoader`. Tuy nhiên, provider module phải có mặt trong module graph mà ServiceLoader đang xét.

Khi chạy demo, có thể đưa provider vào root set:

    java --module-path mods --add-modules com.example.csv.provider -m com.example.app/com.example.app.Main

Nếu provider chỉ được đặt trên module path nhưng không được resolve, việc phát hiện provider có thể khác kỳ vọng. Đối với plugin được đặt trong module layer riêng, có thể dùng overload theo layer như phần tiếp theo.

## 13. Plugin trên classpath và module path khác nhau

Trong hệ thống cũ, provider trên classpath thường đăng ký bằng file:

    META-INF/services/com.example.spi.ReportExporter

Nội dung:

    com.example.csv.CsvExporter

Khi đóng gói thành named module, cơ chế khai báo provider thường chuyển sang `provides ... with ...` trong `module-info.java`.

Không xóa file `META-INF/services` khỏi bản artifact legacy nếu ứng dụng classpath cũ vẫn cần đọc nó trong giai đoạn chuyển tiếp. Đồng thời, phải tránh đăng ký sai kiểu provider hoặc chứa nhiều bản service API làm class identity không còn tương thích.

Named-module provider có thể dùng public no-arg constructor hoặc provider method theo quy tắc của `ServiceLoader`. Provider kiểu classpath được liệt kê trong `META-INF/services` phải đáp ứng hợp đồng constructor tương ứng.

Trong một giai đoạn migration, có thể cần duy trì hai cách đóng gói hoặc hai biến thể artifact, miễn là phạm vi, dependency và test tương ứng được quản lý rõ ràng.

## 14. ModuleLayer cho plugin động

Nếu ứng dụng tự phát hiện JAR plugin từ thư mục và nạp động, việc chỉ gọi `ServiceLoader.load(service)` trên class loader hiện tại không phải lúc nào cũng nhìn thấy plugin nằm trong module layer mới.

Với named-module plugins, có thể tạo module configuration và module layer riêng, rồi tìm provider qua overload nhận layer:

    ServiceLoader<ReportExporter> exporters =
            ServiceLoader.load(pluginLayer, ReportExporter.class);

Overload này tìm provider trong layer được chỉ định và các layer tổ tiên. Nó phù hợp với plugin system tự quản lý vòng đời module layer.

Plugin cần có module descriptor và khai báo `provides` phù hợp. Module layer phải được định nghĩa dựa trên một configuration đã resolve, cùng class loader strategy phù hợp.

Nếu plugin vẫn là JAR legacy ở classpath hoặc URLClassLoader riêng, có thể dùng overload nhận class loader:

    ServiceLoader<ReportExporter> exporters =
            ServiceLoader.load(
                ReportExporter.class,
                pluginClassLoader
            );

Chọn overload theo kiến trúc plugin thực tế; không đổi bừa sang `ModuleLayer` chỉ vì ứng dụng đã bắt đầu modularize.

## 15. Kiểm thử plugin theo hợp đồng

Một test plugin hiệu quả không chỉ xác nhận JAR được build. Nó cần kiểm tra cả hợp đồng runtime:

1. **API compatibility:** provider có triển khai đúng service interface của ứng dụng không?
2. **Provider discovery:** `ServiceLoader` có tìm thấy provider trong cấu hình triển khai thực tế không?
3. **Construction:** provider có khởi tạo được, không ném `ServiceConfigurationError` không?
4. **Behavior:** provider trả về kết quả đúng với dữ liệu thử không?
5. **Isolation:** nhiều plugin có tên package và service giống nhau không gây class-loader conflict không?
6. **Cleanup:** URLClassLoader, resource và các đối tượng plugin có được giải phóng phù hợp không?

Ví dụ kiểm tra tối thiểu:

    ServiceLoader<ReportExporter> loader =
            ServiceLoader.load(ReportExporter.class);

    boolean csvFound = loader.stream()
            .map(ServiceLoader.Provider::get)
            .anyMatch(exporter -> "csv".equals(exporter.format()));

    if (!csvFound) {
        throw new AssertionError("CSV plugin not discovered");
    }

Test phải chạy trong cùng kiểu cấu hình service discovery mà production dùng. Một provider được phát hiện trong classpath test có thể không được phát hiện trong named-module runtime nếu module provider chưa được resolve.

## 16. Cấu trúc bộ test trong migration

Có thể phân nhóm test theo mục đích:

| Nhóm test | Cấu hình gợi ý | Mục tiêu |
|---|---|---|
| Unit tests nhanh | Classpath hoặc modular test, tùy giai đoạn | Giữ hành vi nghiệp vụ cũ |
| Module boundary tests | Chạy với module path thật | Xác minh `requires`, `exports`, `opens` và package ownership |
| Service/Plugin tests | Khởi chạy với đúng provider module hoặc layer | Xác minh discovery và tạo provider |
| Integration tests | Runtime packaging gần production | Phát hiện khác biệt test/production |
| Packaging checks | Kiểm tra modular JAR và descriptor | Xác minh `module-info.class`, service metadata, main class |

Không nên thay thế toàn bộ integration tests bằng unit tests chỉ vì bước compile đã thành công. Lỗi module resolution, service discovery hoặc reflection thường chỉ xuất hiện khi JVM thực sự khởi chạy cấu hình module cuối cùng.

## 17. CI: giữ đường build cũ và đường build mới

Trong migration, có thể chạy hai lane trong CI:

**Legacy lane:** build/test theo cấu hình classpath hiện tại, bảo đảm hành vi cũ không bị hỏng.

**JPMS lane:** biên dịch và chạy ứng dụng/test hoặc plugin bằng module path, xác minh ranh giới module và service discovery.

Ví dụ với một dự án có profile Maven `jpms` được định nghĩa trước:

    mvn clean verify

    mvn -Pjpms clean verify

Lưu ý: `-Pjpms` chỉ có ý nghĩa nếu project thực sự khai báo profile `jpms` trong POM hoặc cấu hình Maven. Đây là minh họa mô hình hai lane, không phải profile mặc định do Maven cung cấp.

Với Gradle, có thể tạo task hoặc property để lựa chọn cấu hình phù hợp, sau đó đưa cả hai vào CI. Dù dùng build tool nào, hai lane cần chạy trên JDK/version tương ứng với mục tiêu triển khai.

Sau mỗi bước migration, hãy cập nhật checklist theo lỗi thực tế thay vì tắt hàng loạt test đang thất bại. Tắt test hoặc bỏ qua test suite có thể làm mất bằng chứng rằng migration vẫn giữ được hành vi.

## 18. Chẩn đoán lỗi thường gặp

| Lỗi/triệu chứng | Nguyên nhân thường thấy | Hướng xử lý |
|---|---|---|
| `module not found` hoặc `FindException` | Module path thiếu JAR, tên module sai | Kiểm tra artifact, descriptor, module path |
| `package ... is not visible` | Thiếu readability hoặc package chưa export | Kiểm tra `requires`, `exports` |
| `InaccessibleObjectException` | Test/framework truy cập private member trong package chưa open | Kiểm tra module gọi reflection, dùng `opens` hoặc `--add-opens` phù hợp |
| `ServiceConfigurationError` | Provider khai báo sai hoặc không khởi tạo được | Kiểm tra `provides`, `META-INF/services`, constructor/provider method |
| Test không được phát hiện | Test runner/source set/module path chưa khớp | Kiểm tra plugin test, test runtime, test engine |
| Plugin JAR build thành công nhưng không được nạp | Provider module chưa resolve hoặc layer không đúng | Kiểm tra root modules, `ServiceLoader` overload, plugin layer |
| `ClassCastException` khi dùng plugin | Service API bị nạp bởi nhiều class loader | Chia sẻ API qua loader cha hoặc cấu hình loader thống nhất |
| Split package / resolution conflict | Nhiều named modules chứa cùng package | Gộp package về một module hoặc đổi package theo trách nhiệm |

Đừng dùng `--add-opens` để sửa một class thực sự bị thiếu, và đừng dùng `--add-exports` để thay thế `provides` trong ServiceLoader. Mỗi cơ chế của JPMS giải quyết một loại vấn đề riêng.

## 19. Giảm phụ thuộc vào workaround theo thời gian

Các tùy chọn như `--add-reads`, `--add-exports`, `--add-opens` và `--patch-module` có thể hữu ích trong quá trình chuyển đổi. Nhưng chúng nên được ghi lại cùng lý do sử dụng và nơi áp dụng.

Một cách quản lý là lưu thông tin:

- Module/package được mở hoặc bổ sung quyền đọc.
- Test framework hoặc plugin cần quyền đó.
- Chỉ sử dụng ở test JVM hay cả production JVM.
- Phần code hoặc dependency nào sẽ được sửa để loại bỏ workaround.
- Test nào xác nhận có thể bỏ flag trong tương lai.

Khi nâng version build tool, test framework hoặc plugin, hãy thử loại bỏ các flag không còn cần thiết theo từng bước. Không mở tất cả package của module chỉ để giải quyết một test.

## 20. Các nhầm lẫn thường gặp

- **Tưởng thêm `module-info.java` là migration hoàn tất.** Runtime packaging, test runner và plugin discovery vẫn cần kiểm tra.
- **Tưởng test chạy trên classpath chứng minh module boundaries đúng.** Classpath test không nhất thiết áp dụng cùng cơ chế truy cập như production module path.
- **Tưởng `--add-opens` và `--add-exports` giống nhau.** Một tùy chọn phục vụ deep reflection, tùy chọn còn lại phục vụ truy cập kiểu public.
- **Tưởng build-tool plugin và runtime plugin là một.** Maven/Gradle plugin chạy trong build tool, còn plugin runtime do ứng dụng nạp.
- **Tưởng plugin JAR nằm trên module path sẽ tự được ServiceLoader phát hiện.** Provider module cần được resolve vào cấu hình có hiệu lực hoặc nạp qua layer phù hợp.
- **Tưởng API service cùng tên ở hai loader là cùng kiểu.** Class identity còn phụ thuộc vào class loader định nghĩa class.
- **Tưởng chỉ cần `--patch-module` cho mọi test.** Cấu hình test còn phụ thuộc readability, classpath/module path của framework và mức truy cập cần thiết.
- **Tưởng cấu hình JVM của ứng dụng áp dụng cho JVM test.** Mỗi JVM có VM options riêng.
- **Tưởng có thể bỏ toàn bộ test thất bại để đẩy nhanh migration.** Điều đó làm mất cơ chế phát hiện regression khi chuyển sang JPMS.

## Ghi nhớ

- Duy trì **compile, test, plugin build và runtime discovery** như các luồng cần kiểm chứng riêng trong migration.
- Có thể giữ một lane classpath ổn định bên cạnh một lane JPMS, rồi giảm dần sự phụ thuộc vào cấu hình legacy.
- Test dùng reflection có thể cần `--add-opens`; test cùng package với production có thể cần `--patch-module` tùy kiến trúc.
- Với Maven/Gradle, hãy phân biệt các plugin chạy build với module path của ứng dụng.
- Plugin runtime qua `ServiceLoader` phải có metadata provider phù hợp, class identity thống nhất và module/layer được resolve đúng.
- Đừng coi build thành công là đủ: test discovery, plugin discovery và packaging phải được chạy trong cấu hình gần production.
- Những flag mở rộng quyền nên có phạm vi nhỏ, lý do rõ và được loại bỏ khi kiến trúc đã hoàn tất migration.

Khi từng bước chuyển sang JPMS, mục tiêu là giữ các kiểm thử và plugin hoạt động liên tục trong lúc dần thu hẹp ranh giới phụ thuộc cũ. Thiết kế hai lane build, quản lý rõ module path/classpath và test trực tiếp các luồng ServiceLoader sẽ giúp quá trình chuyển đổi có thể kiểm soát, phục hồi và hoàn tất mà không đánh mất hành vi của hệ thống.