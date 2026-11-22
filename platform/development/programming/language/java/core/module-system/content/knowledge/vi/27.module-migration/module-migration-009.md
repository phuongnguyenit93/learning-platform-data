# Đo tác động tới đóng gói và triển khai

Khi chuyển ứng dụng Java từ classpath sang Java Platform Module System (JPMS), thay đổi không chỉ nằm trong file `module-info.java`. Cách biên dịch, module path, module graph, service provider, reflection, cấu trúc phân phối, runtime image và lệnh khởi động đều có thể thay đổi. Do đó, migration thành công phải được kiểm chứng bằng **phép đo đóng gói và triển khai trước/sau**, thay vì chỉ dựa vào việc ứng dụng biên dịch thành công.

Mục tiêu là trả lời những câu hỏi thực tế: tổng kích thước artifact thay đổi bao nhiêu; có thể tạo custom runtime image bằng `jlink` không; thời gian build và khởi động có thay đổi; module hoặc service nào bị thiếu khi deploy; và cơ chế rollback có còn hoạt động?

## 1. Định nghĩa phạm vi cần đo

Trước tiên, phân biệt những đối tượng sau:

- **JAR sản phẩm:** bytecode và resource của ứng dụng, có thể chứa `module-info.class`.
- **Dependency artifacts:** các JAR thư viện đi cùng ứng dụng, có thể là explicit, automatic hoặc classpath JAR.
- **Java runtime:** JDK/JRE đầy đủ hay custom runtime image do `jlink` tạo.
- **Distribution:** toàn bộ ZIP, TAR, thư mục cài đặt, installer hoặc container image phát hành cho người dùng.
- **Deployment:** quá trình tải/cài gói, cấu hình, khởi động và đưa ứng dụng vào trạng thái sẵn sàng.
- **Runtime behavior:** startup, bộ nhớ, service discovery, reflection, resource loading và các đường chạy nghiệp vụ.

Không được đánh đồng kích thước một file JAR với kích thước distribution. Nếu trước migration đóng gói một JAR nhỏ nhưng máy đích phải có JDK đầy đủ, còn sau migration đóng gói ứng dụng cùng runtime tùy biến, ranh giới đo đã thay đổi. Hãy chọn cùng một phạm vi trước và sau hoặc báo riêng từng phương án triển khai.

## 2. Chốt baseline trước khi modular hóa

Trước khi chỉnh code, lưu lại:

~~~text
Baseline:
- Commit/release:
- JDK vendor and version:
- OS / CPU architecture:
- Build tool and version:
- Build command:
- Packaging command:
- Actual launch command:
- JVM options:
- Dependency lock or resolved dependency list:
- Test workload:
- Distribution format:
- Deployment environment:
~~~

Baseline phải có thể tái tạo. Nếu hệ thống dùng container, lưu cả digest base image, architecture và biến cấu hình. Nếu sử dụng Maven hoặc Gradle, chốt dependency để tránh kết quả thay đổi chỉ do nâng phiên bản thư viện.

Bản sau migration nên dùng cùng phiên bản JDK, cấu hình GC, memory limits và workload nếu mục tiêu là tách riêng tác động của JPMS. Nếu đồng thời nâng JDK hoặc framework, phải ghi rõ vì những yếu tố đó cũng có thể ảnh hưởng tốc độ và dung lượng.

## 3. Bộ chỉ số tối thiểu

| Nhóm | Chỉ số | Đơn vị |
|---|---|---|
| Artifact | Kích thước JAR chính | byte, MiB |
| Dependency | Tổng dung lượng JAR phụ thuộc | byte, MiB |
| Runtime | Tổng dung lượng Java runtime đi kèm | MiB |
| Distribution | Tổng dung lượng ZIP/installer/thư mục | MiB |
| Container | Compressed size và uncompressed size | MB hoặc MiB, ghi rõ |
| Build | Thời gian clean build | giây |
| Packaging | Thời gian tạo image/installer | giây |
| Startup | Từ khởi chạy đến readiness | mili giây |
| Runtime | Peak RSS và heap usage khi chạy workload | MiB |
| Resolution | Số module có trong boot layer | module |
| Operations | Thời gian deploy, ready và rollback | giây/phút |
| Compatibility | Số lỗi module, reflection hoặc service discovery | số lỗi |

Với từng chỉ số, ghi cột `Before`, `After`, `Delta`, phương pháp đo và điều kiện thử. Một số chỉ số như lỗi dependency cần đạt 0; số module hoặc kích thước không nhất thiết càng nhỏ càng tốt.

Công thức phần trăm khi giá trị baseline khác 0:

~~~text
Delta tuyệt đối = After - Before
Delta (%)      = (After - Before) / Before * 100
~~~

Ví dụ giả định:

| Chỉ số | Before | After | Delta |
|---|---:|---:|---:|
| Tổng distribution | 320 MiB | 240 MiB | -80 MiB (-25%) |
| Clean build | 40 s | 46 s | +6 s (+15%) |
| Cold startup | 1.50 s | 1.42 s | -0.08 s (-5.3%) |

Đây là số minh họa công thức, không phải kết quả đo của một ứng dụng thực. Một lợi ích về kích thước có thể đi kèm chi phí build tăng. Cần đánh giá trade-off theo yêu cầu sản phẩm.

## 4. Phương pháp đo đáng tin cậy

Một phép thử nên có quy trình lặp lại:

1. Chạy trên cùng OS, JDK, CPU architecture và cấu hình JVM.
2. Định nghĩa workload và dữ liệu đầu vào cố định.
3. Thực hiện clean build khi so thời gian build toàn phần.
4. Đo nhiều lần thay vì chọn một lần chạy tốt nhất.
5. Ghi median, p90 hoặc độ phân tán cho startup và deploy.
6. Phân biệt cold startup với lần khởi động khi filesystem cache đã nóng.
7. Ghi rõ phụ thuộc mạng, database, DNS hoặc external service có nằm trong phép đo.
8. Sử dụng artifact **đúng như sẽ triển khai**, không chỉ class output trong IDE.

Nếu pipeline có build cache hoặc tải dependency qua network, nên tách thời gian download/cache khỏi công đoạn biên dịch khi cần phân tích nguyên nhân. Kết quả chỉ có ý nghĩa nếu mô tả đủ điều kiện để nhóm khác tái lập.

## 5. Phân tích dependency với jdeps

`jdeps` giúp phân tích quan hệ dependency tĩnh của bytecode để tìm module JDK và dependency khác.

Ví dụ JAR thông thường:

~~~bash
jdeps --print-module-deps app.jar
~~~

Với modular JAR nằm trên module path:

~~~bash
jdeps --module-path mods \
      --print-module-deps \
      mods/com.acme.app.jar
~~~

Để xem dependency chi tiết hơn:

~~~bash
jdeps --module-path mods \
      --list-deps \
      mods/com.acme.app.jar
~~~

Nên lưu lại những module cần thiết, dependency không tìm thấy và package nội bộ JDK mà code còn tham chiếu. Không nên tự động coi danh sách của `jdeps` là danh sách đầy đủ mọi module runtime.

**Giới hạn quan trọng:** `jdeps` chủ yếu nhìn dependency từ bytecode. Các class nạp bằng `Class.forName`, tên provider lấy từ cấu hình, reflection, service loading, JNI hoặc resource động có thể không được phát hiện đầy đủ. Phải xác nhận thêm bằng integration test và kiểm tra runtime thực tế.

## 6. Kiểm tra modular JAR và module descriptor

Một explicit modular JAR có descriptor `module-info.class`. Kiểm tra artifact sau build:

~~~bash
jar --describe-module --file mods/com.acme.app.jar
jar --list --file mods/com.acme.app.jar
~~~

Descriptor mẫu:

~~~java
module com.acme.app {
    requires java.logging;
    requires java.sql;
    requires java.net.http;
}
~~~

Khi migration, ghi nhận các thay đổi:

- JAR chính có `module-info.class` hay chưa.
- Tên module thực tế có ổn định không.
- Những package nào `exports` hoặc `opens`.
- Các dependency `requires`, `requires transitive` hoặc `requires static`.
- Service directives `uses` và `provides` có đúng không.
- Có JAR phụ thuộc nào chưa thể đưa lên module path không.

Modular JAR có thể lớn hơn JAR cũ một ít vì descriptor, nhưng điều đó không kết luận toàn bộ distribution lớn hơn. JPMS tập trung vào graph, encapsulation và khả năng tạo custom runtime.

## 7. Quan sát module graph lúc chạy

`--show-module-resolution` giúp quan sát những module được giải quyết:

~~~bash
java --show-module-resolution \
     --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

Trong mã Java có thể liệt kê module của boot layer:

~~~java
ModuleLayer.boot().modules().stream()
    .map(Module::getName)
    .sorted()
    .forEach(System.out::println);
~~~

Danh sách này là các module được định nghĩa trực tiếp trong boot layer, không phải toàn bộ JAR có trên disk. Lưu danh sách trước/sau để tìm module được thêm, module thiếu hoặc automatic module xuất hiện bất ngờ.

Nếu ứng dụng cần provider được đưa vào graph bởi service binding, kiểm tra riêng cấu hình có binding:

~~~bash
java --bind-services \
     --show-module-resolution \
     --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

Graph lớn hơn không nhất thiết là xấu: một JDBC driver, logging provider hay crypto module cần thiết vẫn phải có mặt. Mục tiêu là **đầy đủ dependency, không kéo theo module không có chủ đích**.

## 8. Tạo custom runtime image bằng jlink

Một hướng giảm kích thước phân phối là dùng `jlink` liên kết các module ứng dụng/JDK cần thiết thành runtime image.

Ví dụ với explicit modular JAR đã đóng gói trong thư mục `mods`:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" \
      --add-modules com.acme.app \
      --output runtime-image
~~~

Trên Windows PowerShell, dấu phân cách module path là dấu chấm phẩy:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.acme.app --output runtime-image
~~~

Kiểm tra image:

~~~bash
./runtime-image/bin/java --list-modules
./runtime-image/bin/java -m com.acme.app/com.acme.app.Main
~~~

`--add-modules com.acme.app` chọn root; resolver đưa vào dependency closure từ descriptor. Khi đo, lấy dung lượng **toàn thư mục `runtime-image`**, không chỉ một binary trong `bin` hay `lib`.

Một custom runtime image nhỏ hơn không tự chứng minh JVM dùng ít RAM hoặc khởi động nhanh hơn. Kích thước filesystem, RSS, heap và thời gian khởi động là những chỉ số khác nhau và phải đo độc lập.

## 9. Automatic module có thể cản trở linking

Trong quá trình chuyển đổi, một thư viện cũ không có `module-info.class` nhưng nằm trên module path có thể trở thành automatic module. Nó dùng tên từ `Automatic-Module-Name` hoặc tên JAR suy ra.

Automatic module hữu ích để ứng dụng named module tham chiếu thư viện cũ, nhưng **`jlink` không chấp nhận automatic module như đầu vào liên kết thông thường**. Vì vậy, một ứng dụng vẫn còn dependency automatic module có thể chạy với Java launcher nhưng chưa thể liên kết trực tiếp thành runtime image như kỳ vọng.

Cần ghi trong báo cáo:

| Loại thư viện | Trạng thái | Tác động đóng gói |
|---|---|---|
| JDK/Java SE module | Named module có descriptor | Có thể chọn làm root/dependency khi linking |
| Explicit modular JAR | Có `module-info.class` | Tham gia resolution và có thể dùng khi linking nếu hợp lệ |
| Automatic module | Chưa có descriptor tường minh | Hỗ trợ migration; có hạn chế với `jlink` |
| Classpath library | Thuộc unnamed module | Cần chiến lược compatibility/packaging riêng |

Nếu linking bị chặn, đừng giả định chỉ thêm manifest name là đủ. Có thể cần nâng cấp thư viện lên bản modular, đổi dependency hoặc chọn kiểu distribution khác trong giai đoạn chuyển tiếp.

## 10. Service provider và tác động tới runtime image

Ứng dụng sử dụng `ServiceLoader` có dependency động không thể suy ra chỉ từ các câu `requires`.

Consumer:

~~~java
module com.acme.app {
    requires com.acme.spi;
    uses com.acme.spi.Formatter;
}
~~~

Provider:

~~~java
module com.acme.formatter.json {
    requires com.acme.spi;
    provides com.acme.spi.Formatter
        with com.acme.formatter.json.JsonFormatter;
}
~~~

`jlink` có tùy chọn liên kết các service provider khả dụng:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" \
      --add-modules com.acme.app \
      --bind-services \
      --output runtime-with-providers
~~~

Service binding có thể thêm nhiều module/provider và dependency vào image; dung lượng có thể **tăng** so với cấu hình không binding. Nếu chỉ cần một provider cụ thể, cần xem xét chọn root/chế độ triển khai có kiểm soát.

Sau khi tạo image, chạy đúng đường chức năng để xác nhận `ServiceLoader` tìm và khởi tạo được provider. Lưu ý provider được resolve chưa có nghĩa đã được khởi tạo; service loading thường diễn ra khi ứng dụng duyệt loader.

## 11. Reflection, opens và tài nguyên runtime

JPMS áp dụng strong encapsulation với package của named module. Một chương trình có thể biên dịch nhưng lỗi khi framework cần deep reflection:

~~~text
java.lang.reflect.InaccessibleObjectException
~~~

Module có thể mở đúng package cho framework:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.model to com.acme.serializer;
}
~~~

Khi cần workaround tạm thời, có thể dùng `--add-opens` với đúng module/package/đích. Nhưng phải ghi những JVM flags này trong launch configuration thực tế của image, container hoặc installer.

Các trường hợp dễ bị bỏ sót:

- ORM và entity construction.
- JSON/XML serializer truy cập field/constructor.
- Dependency injection và component scanning.
- Resource được tìm theo đường dẫn module.
- JDBC driver và service provider.
- TLS, certificate, security provider, locale và charset.

Hãy kiểm thử chúng trên **artifact phát hành**. Một smoke test chỉ gọi main hoặc health endpoint có thể không đi qua các đường code nạp động.

## 12. jpackage: đo app image và installer

`jpackage` có thể tạo app image hoặc installer để phân phối ứng dụng theo từng hệ điều hành.

Ví dụ minh họa với modular application:

~~~bash
jpackage --type app-image \
         --name AcmeApp \
         --module-path mods \
         --module com.acme.app/com.acme.app.Main \
         --dest dist
~~~

Nếu cung cấp custom runtime phù hợp:

~~~bash
jpackage --type app-image \
         --name AcmeApp \
         --runtime-image runtime-image \
         --module-path mods \
         --module com.acme.app/com.acme.app.Main \
         --dest dist
~~~

Tùy phiên bản JDK, OS và công cụ đóng gói được cài đặt, cú pháp/khả năng tạo installer có thể khác nhau. Hãy chạy thử trên đúng môi trường build thực tế.

Ngoài dung lượng installer, đo thời gian tạo gói, cài đặt, cập nhật và gỡ cài đặt; kiểm tra khả năng chạy trên máy sạch không có JDK hệ thống. Gói có thể nhỏ nhưng quá trình cập nhật hoặc rollback phức tạp hơn, nên cần đánh giá cả vòng đời phân phối.

## 13. Đo startup và memory

Để đo startup, xác định mốc rõ ràng:

~~~text
Start: thời điểm tạo Java process
Ready: thời điểm ứng dụng trả readiness/health thành công
Startup duration = Ready - Start
~~~

Chạy nhiều lần và phân biệt cold/warm startup. Nếu readiness còn chờ database/network, thời gian đó là một phần của phép đo end-to-end; cần ghi rõ.

Các chỉ số runtime khác:

- RSS và peak RSS.
- Heap used/committed.
- Metaspace.
- Số class và class loader.
- CPU khi startup và steady state.

Ví dụ công cụ chẩn đoán JDK:

~~~bash
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> GC.heap_info
~~~

Các dấu `<pid>` là placeholder cần thay bằng process id. RSS phải được đo từ OS/container monitoring phù hợp; heap used không bằng toàn bộ RSS.

Giữ nguyên `-Xms`, `-Xmx`, GC, workload và giới hạn container khi so sánh. Không suy luận một runtime image nhỏ hơn sẽ tự làm startup hoặc memory tốt hơn.

## 14. Đo build, pipeline và triển khai

Migration có thể thêm công đoạn:

~~~text
Before:
compile (classpath)
  -> package application
  -> copy dependencies
  -> deploy

After:
compile (module-path)
  -> package modular JAR
  -> inspect module descriptor
  -> dependency analysis
  -> optional jlink / jpackage
  -> test actual distribution
  -> deploy
~~~

Nên đo riêng:

1. Clean compile và incremental compile.
2. Unit/integration test.
3. Đóng gói JAR.
4. Tạo runtime image/installer.
5. Upload/push artifact.
6. Download/pull artifact ở môi trường đích.
7. Khởi động đến readiness.
8. Tổng thời gian pipeline commit-to-ready.
9. Thời gian rollback về bản trước.

Nếu custom runtime cần build riêng cho Linux x86_64, Linux arm64, Windows và macOS, chi phí CI và vận hành có thể tăng. Một báo cáo chỉ ghi gói nhỏ hơn mà bỏ qua ma trận build sẽ không phản ánh đầy đủ tác động.

## 15. Container image và hệ điều hành đích

Với container, cần đo **compressed registry size** và **uncompressed filesystem size**, vì hai giá trị không giống nhau. So sánh cùng architecture và base image khi có thể.

Một bản triển khai có custom runtime cần đủ thành phần nền:

- Thư viện native mà Java và dependency dùng.
- Certificate/trust store cho kết nối TLS.
- Time zone, locale, charset cần thiết.
- User quyền thấp, filesystem permissions và thư mục tạm.
- Health check, signal handling và logging.

Custom image không nhất thiết tự chứa mọi dependency OS. Một image ít byte hơn nhưng không có CA certificates hay thư viện hệ thống vẫn là gói không đạt yêu cầu.

Nên ghi image digest để khôi phục chính xác bản phát hành thay vì chỉ dùng tag có thể bị ghi đè.

## 16. Ma trận kiểm thử tương thích khi deploy

| Kiểm thử | Mục tiêu |
|---|---|
| Startup smoke test | Launcher chạy được với module graph mới |
| Module resolution | Không thiếu root/dependency, không có graph conflict |
| ServiceLoader | Các provider cần thiết xuất hiện và khởi tạo đúng |
| Database/JDBC | Driver và connection pool hoạt động |
| Reflection/serialization | Package cần mở được mở đúng phạm vi |
| HTTP/TLS | Kết nối mạng, certificate và provider phù hợp |
| Resource loading | Template, config, classpath/module resources tồn tại |
| Background tasks | Scheduler, batch, plugin được khởi tạo |
| Health/readiness | Deploy chỉ đánh dấu ready khi ứng dụng hoạt động |
| Rollback | Bản trước có thể phục hồi với dữ liệu và cấu hình phù hợp |

Các kiểm thử cần dùng đúng JAR, runtime image, biến môi trường và JVM options của production. IDE có thể chạy với classpath hoặc flags khác nên không đủ để chứng minh gói triển khai thành công.

## 17. Các lỗi phổ biến và nguyên nhân

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `FindException: Module ... not found` | Root/dependency không có trong image/module path | `--show-module-resolution`, `--list-modules` |
| `LayerInstantiationException` | Module graph/package conflict khi định nghĩa layer | Descriptor, split package, loader strategy |
| `IllegalAccessError` | Readability hoặc exports không đáp ứng | `requires`, `exports`, runtime flags |
| `InaccessibleObjectException` | Framework cần deep reflection | `opens`, `--add-opens` |
| `ServiceConfigurationError` | Provider thiếu/sai hoặc không khởi tạo được | `uses`, `provides`, service binding |
| `No suitable driver` | JDBC driver không được đưa vào runtime | Driver JAR/provider, module graph |
| Runtime nhỏ nhưng TLS lỗi | Thiếu crypto/certificate/provider/OS capability | Image contents, security, network |
| Local pass, container fail | Environment và JVM arguments khác nhau | Reproduce exact container startup |
| jlink không nhận dependency | Có automatic/nonmodular module không thể link | Kiểm tra dependency, nâng cấp bản modular |

Chẩn đoán theo tầng: artifact có đủ file không, module có được resolve không, caller có quyền đọc/truy cập không, provider có được tìm không và chức năng runtime có hoạt động không.

## 18. Quy trình A/B đo tác động

Một quy trình khả thi:

1. **Chốt baseline** gồm commit, JDK, OS, dependency, command, artifact và workload.
2. **Modular hóa có kiểm soát** bằng `module-info.java` và giải quyết dependency thật.
3. **Kiểm tra descriptor** bằng `jar --describe-module`.
4. **Phân tích dependency tĩnh** với `jdeps`.
5. **Tạo các distribution tương đương** và đo tổng byte artifact/runtime/package.
6. **Chạy integration test trên gói thực**; đặc biệt service provider, reflection, JDBC và TLS.
7. **Đo performance lặp lại**: cold startup, median/p90, peak RSS, readiness.
8. **Đo pipeline**: clean build, packaging, upload, deploy, rollback.
9. **Báo trade-off** bằng bảng before/after/delta, kèm môi trường thử.
10. **Đưa ra quyết định** có điều kiện chấp nhận hoặc blocker cụ thể.

Không nên thay đổi đồng thời framework, database driver và JDK khi muốn kết luận chính xác tác động của JPMS. Nếu không thể cô lập thay đổi, ghi rõ giới hạn của dữ liệu.

## 19. Mẫu báo cáo tác động migration

~~~text
JPMS Migration Impact

Scope:
- Application/release:
- Baseline revision:
- Modular revision:
- JDK, OS, architecture:
- Packaging modes:

Artifact & Distribution:
- App JAR bytes: before / after / delta
- Dependency bytes: before / after / delta
- Runtime bytes: before / after / delta
- Full distribution bytes: before / after / delta
- Container compressed/uncompressed size:

Build & Runtime:
- Clean build median:
- Linking/installer time:
- Cold startup median/p90:
- Peak RSS:
- Boot module count:

Compatibility:
- Module resolution:
- Service providers:
- Reflection/serialization:
- JDBC/HTTP/TLS:
- Smoke/integration tests:
- Remaining runtime workarounds:

Operations:
- Deploy duration:
- Rollback duration:
- Readiness:
- Artifact/image digest:

Decision:
- Accept / Block / Further investigation
- Risks and owner:
- Evidence:
~~~

Nếu một hạng mục chưa được đo, ghi “chưa đo”; không thay bằng con số đoán hoặc số minh họa. Gắn kết quả với build artifact/digest để có thể tra cứu đúng bản đã kiểm thử.

## 20. Ghi nhớ

**Đo tác động JPMS migration theo toàn bộ vòng đời phân phối.** Modular JAR có thể không nhỏ hơn JAR cũ, nhưng `jlink` có thể giúp tạo runtime image chỉ chứa module cần thiết khi đầu vào đáp ứng yêu cầu. `jdeps` giúp phân tích dependency tĩnh; `jar --describe-module` xác nhận descriptor; `--show-module-resolution` giúp quan sát graph; `jpackage` có thể tạo app image hoặc installer.

Chỉ so sánh kích thước, build time, startup và memory khi điều kiện đo tương đương. Phải kiểm chứng những dependency động như `ServiceLoader`, JDBC, reflection, TLS và resource loading trên chính artifact sẽ triển khai. Một báo cáo tốt có baseline rõ ràng, phép đo lặp lại, delta, giới hạn, khả năng rollback và quyết định triển khai có bằng chứng — không chỉ một con số “giảm dung lượng” thiếu ngữ cảnh.
