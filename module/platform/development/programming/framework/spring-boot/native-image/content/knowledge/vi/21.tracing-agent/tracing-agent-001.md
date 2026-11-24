# Native Image Tracing Agent quan sát truy cập động khi ứng dụng chạy trên JVM

Khi biên dịch Spring Boot thành **GraalVM Native Image**, một số thao tác chỉ được thực hiện động lúc chạy có thể không được static analysis nhận diện đầy đủ. Ví dụ: reflection tìm constructor hoặc method theo tên, đọc file từ classpath, tạo dynamic proxy hoặc gọi JNI. Nếu thiếu metadata, ứng dụng có thể build thành công nhưng lỗi khi một request hoặc nhánh nghiệp vụ cụ thể chạy trên native executable.

**Native Image Tracing Agent** giúp điều tra vấn đề này bằng cách gắn agent vào một tiến trình chạy trên JVM. Agent quan sát các truy cập động thực sự xảy ra, sau đó sinh metadata để Native Image sử dụng khi build. Trong module **`SPRING_BOOT_NATIVE_IMAGE`** (biên dịch Spring Boot bằng Spring AOT, đánh giá startup/memory, kiểm thử tương thích và đóng gói container), bài học này hướng dẫn cách chạy agent, tạo độ phủ workload, đọc/lọc metadata, tích hợp Maven/Gradle và xác minh kết quả trên native executable.

> **Điểm quan trọng:** tracing agent ghi nhận những gì đã xảy ra trong lần chạy được quan sát. Nó không tự khám phá mọi đường code, không chứng minh ứng dụng đã tương thích hoàn toàn và không thay thế hints mà Spring AOT hoặc thư viện đã cung cấp.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao Native Image cần metadata cho reflection, resource, proxy và JNI.
- Gắn tracing agent vào ứng dụng Spring Boot chạy trên JVM.
- Chọn giữa chạy ứng dụng trực tiếp và chạy test suite với agent.
- Thiết kế workload để đi qua các nhánh nghiệp vụ có truy cập động.
- Hiểu `config-output-dir`, `config-merge-dir`, `trace-output` và cách lưu kết quả.
- Phân biệt caller filter với access filter.
- Review, hợp nhất và đưa metadata vào đúng vị trí trong source.
- Dùng agent với Maven Native Build Tools hoặc Gradle Native Build Tools.
- Kiểm tra metadata bằng native build và native integration test.

## 2. Vì sao cần Tracing Agent?

Native Image thực hiện reachability analysis ở build time. Builder có thể nhìn thấy nhiều lời gọi Java thông thường qua bytecode, nhưng không phải lúc nào cũng biết chính xác target của một thao tác động.

~~~java
String implementationName = settings.getImplementationClass();
Class<?> type = Class.forName(implementationName);
Object instance = type.getDeclaredConstructor().newInstance();
~~~

Tên class và constructor được chọn từ cấu hình lúc runtime. Static analysis không nhất thiết suy ra được mọi giá trị có thể xuất hiện trong `implementationName`.

| Nhóm | Ví dụ | Metadata có thể cần |
|---|---|---|
| Reflection | `Class.forName`, `getDeclaredMethod`, constructor invocation | Class, constructor, field, method và quyền truy cập |
| Resource | `Class.getResource`, `ClassLoader.getResource`, đọc file theo tên | Resource pattern hoặc resource bundle |
| Dynamic proxy | `Proxy.newProxyInstance` | Danh sách interface proxy |
| JNI | Java gọi native method hoặc native code gọi ngược vào Java | JNI classes/methods/fields |
| Serialization | Framework đọc/ghi object qua reflection | Reflection/serialization metadata phù hợp |

Spring AOT và các thư viện tương thích Native Image có thể tự đóng góp nhiều hints. Tracing Agent hữu ích khi một thư viện hoặc pattern không được Spring nhận diện, hoặc khi cần tìm member cụ thể bị thiếu.

## 3. Agent quan sát điều gì và không quan sát điều gì?

Agent được gắn vào **JVM process**. Trong khi ứng dụng chạy, nó quan sát các dynamic access mà process thực hiện. Khi JVM kết thúc, agent ghi metadata ra thư mục cấu hình.

~~~mermaid
flowchart TD
    A["Ứng dụng Spring Boot + dependencies"] --> B["Chạy trên GraalVM JDK/JVM"]
    B --> C["Tracing Agent quan sát dynamic access"]
    C --> D["Reflection / resources / proxies / JNI"]
    D --> E["Metadata JSON"]
    E --> F["Review và lọc metadata"]
    F --> G["META-INF/native-image"]
    G --> H["Native Image build"]
    H --> I["Native executable"]
    I --> J["Native integration tests"]
~~~

Agent có thể quan sát các thao tác xảy ra trong lần chạy được gắn agent, nhưng có những giới hạn:

- Nếu một nhánh code không được thực thi, agent không thể ghi nhận truy cập chỉ có trong nhánh đó.
- Test có thể thực hiện truy cập của JUnit, Mockito, logging hoặc test framework mà production không cần.
- Một bộ dữ liệu thử nghiệm không đại diện cho mọi input, cấu hình, tenant hoặc trạng thái hệ thống.
- Agent ghi nhận hành vi runtime; nó không chứng minh thao tác đó đúng về nghiệp vụ hoặc an toàn.
- Metadata được tạo ra có thể rộng hơn cần thiết, trùng lặp hoặc chứa entry chỉ phục vụ test.

Hãy xem metadata agent sinh ra là **bằng chứng để review**, không phải file cấu hình được chấp nhận tự động.

## 4. Chuẩn bị môi trường

Trước khi chạy agent:

1. Cài GraalVM JDK tương thích với phiên bản Native Image sẽ dùng để build.
2. Kiểm tra `JAVA_HOME`, `java -version` và `native-image --version`.
3. Build ứng dụng JVM thành công trước.
4. Nếu dùng Spring AOT, tạo AOT output theo cấu hình của dự án.
5. Chuẩn bị dữ liệu/test account để gọi được các luồng nghiệp vụ cần quan sát.
6. Chọn một thư mục output mới, riêng cho lần chạy agent.

Agent thường được cung cấp cùng GraalVM JDK. Có thể gắn bằng `-agentlib:native-image-agent=...`. Nếu dùng JVM khác có hỗ trợ JVMTI, tài liệu GraalVM mô tả cách nạp thư viện agent bằng đường dẫn tuyệt đối qua `-agentpath`; trong thực hành Spring Boot, dùng GraalVM JDK giúp tránh sai khác về agent binary và phiên bản.

## 5. Chạy ứng dụng trực tiếp với agent

Đây là cách phù hợp khi muốn điều tra một thư viện hoặc một luồng request cụ thể mà test suite hiện chưa bao phủ.

Với ứng dụng Spring Boot đã được xử lý AOT và đóng gói thành JAR:

~~~bash
java -Dspring.aot.enabled=true -agentlib:native-image-agent=config-output-dir=build/native/agent-output -jar build/libs/orders-service.jar
~~~

Với Maven, JAR thường ở `target/`; với Gradle, thường ở `build/libs/`. Hãy thay bằng tên artifact thật của dự án.

Lưu ý:

- `-agentlib` phải xuất hiện trước `-jar`, tên main class hoặc tham số ứng dụng.
- `-Dspring.aot.enabled=true` bật sử dụng AOT optimizations khi chạy JAR đã có AOT assets; chỉ dùng khi ứng dụng đã được build với AOT.
- `config-output-dir` là thư mục agent ghi metadata. Nên dùng thư mục mới, không dùng nhầm thư mục source đang chứa metadata đã review.
- Agent ghi metadata khi JVM kết thúc. Hãy dừng ứng dụng bằng shutdown có kiểm soát để agent hoàn tất việc ghi file.

Sau khi ứng dụng khởi động, gửi request hoặc thực hiện thao tác để đi qua các đường code cần điều tra:

- Đăng nhập và refresh token.
- Tạo, đọc, cập nhật và xóa dữ liệu.
- Upload/download file.
- Gọi API đối tác qua WebClient/RestClient.
- Chạy tác vụ nền hoặc message listener.
- Serialize/deserialize DTO, record, enum và subtype.
- Đọc template, schema, certificate hoặc resource theo tên.

Khi đã thực hiện đủ workload, dừng ứng dụng (ví dụ `Ctrl+C`), sau đó kiểm tra thư mục `build/native/agent-output`.

### Agent có thể ghi theo chu kỳ

Với process chạy lâu, có thể dùng:

~~~bash
java -agentlib:native-image-agent=config-output-dir=build/native/agent-output,config-write-period-secs=300,config-write-initial-delay-secs=5 -jar build/libs/orders-service.jar
~~~

Trong ví dụ, agent ghi metadata định kỳ mỗi 300 giây, bắt đầu sau 5 giây. Với một lần kiểm thử ngắn, output khi JVM kết thúc thường đơn giản hơn.

## 6. Chạy test suite với agent

Chạy test với agent tạo quy trình lặp lại được: mỗi lần thay đổi dependency hoặc hints, có thể chạy lại cùng nhóm test và so sánh metadata.

Tuy nhiên, agent sẽ quan sát cả hoạt động của test infrastructure. Output có thể chứa reflection/resource/proxy chỉ phục vụ JUnit, Mockito, assertion library hoặc test framework. Không đưa nguyên output của test vào production mà chưa lọc.

Một test suite hữu ích nên bao phủ:

- Happy path và các lỗi dự kiến.
- Các nhánh cấu hình bật/tắt.
- Các loại DTO và subtype.
- Các endpoint hoặc message handler ít được gọi.
- Các định dạng file và resource khác nhau.
- Các luồng tích hợp bên ngoài có dùng reflection/proxy.

Nếu test chỉ chạy smoke test khởi động context, metadata thu được có thể rất ít dù ứng dụng còn nhiều đường code động khác.

## 7. Chọn chế độ output

Agent có các tùy chọn output chính:

| Tùy chọn | Hành vi | Khi dùng |
|---|---|---|
| `config-output-dir=DIR` | Ghi một bộ metadata vào thư mục output | Bắt đầu lần thu thập mới, tách output theo scenario |
| `config-merge-dir=DIR` | Hợp nhất truy cập mới vào bộ metadata đã có | Thu thập bổ sung từ scenario khác |
| `trace-output=FILE` | Ghi trace chi tiết các access đã quan sát | Điều tra sâu từng dynamic access |

Ví dụ chạy hai scenario độc lập:

~~~bash
java -agentlib:native-image-agent=config-output-dir=build/native/agent-rest -jar app.jar
java -agentlib:native-image-agent=config-output-dir=build/native/agent-messaging -jar app.jar
~~~

Có thể hợp nhất hai thư mục sau khi review:

~~~bash
native-image-utils generate --input-dir=build/native/agent-rest --input-dir=build/native/agent-messaging --output-dir=build/native/agent-merged
~~~

Hoặc chạy lần tiếp theo với `config-merge-dir` để bổ sung vào output đã tồn tại:

~~~bash
java -agentlib:native-image-agent=config-merge-dir=build/native/agent-merged -jar app.jar
~~~

Không nên ghi nhiều process đồng thời vào cùng một `config-output-dir`. Nếu nhiều process cần chạy cùng lúc, mỗi process nên có thư mục output riêng, sau đó merge bằng `native-image-utils`.

### Ghi trace chi tiết

~~~bash
java -agentlib:native-image-agent=trace-output=build/native/trace.json -jar build/libs/orders-service.jar
~~~

Sau khi process kết thúc, chuyển trace thành metadata:

~~~bash
native-image-utils generate --trace-input=build/native/trace.json --output-dir=build/native/trace-config
~~~

Trace có thể rất lớn và chứa nhiều chi tiết hơn bộ cấu hình cuối. Chỉ dùng khi cần điều tra sâu.

## 8. Hiểu các file metadata được tạo

Tùy phiên bản GraalVM, Native Build Tools và định dạng metadata, agent có thể tạo `reachability-metadata.json` hoặc các file JSON theo từng loại cấu hình cũ.

| File/nhóm | Nội dung |
|---|---|
| `reachability-metadata.json` | Định dạng tổng hợp hiện đại cho nhiều loại reachability metadata |
| `reflect-config.json` | Class, constructor, method, field cần reflection |
| `resource-config.json` | Resource và resource bundle |
| `proxy-config.json` | Interface list dùng để tạo dynamic proxy |
| `jni-config.json` | Class/member được truy cập qua JNI |
| `serialization-config.json` | Kiểu dữ liệu cần hỗ trợ serialization theo metadata Native Image |

Không phải mọi phiên bản đều tạo tất cả file. Hãy đọc output thực tế của agent đang dùng, không tạo file rỗng chỉ để đủ danh sách.

Ví dụ metadata reflection dạng legacy:

~~~json
[
  {
    "name": "com.example.plugins.CsvExportPlugin",
    "allDeclaredConstructors": true,
    "methods": [
      {
        "name": "export",
        "parameterTypes": ["com.example.ExportRequest"]
      }
    ]
  }
]
~~~

Đoạn trên chỉ minh họa cấu trúc; file agent sinh ra có thể chứa thêm member flags, conditions hoặc định dạng khác. Không tự chép ví dụ này vào dự án nếu chưa xác minh class/member thực tế.

Metadata mới có thể chứa điều kiện như `typeReached`, nghĩa là một entry chỉ có hiệu lực khi một kiểu cụ thể được reach. Điều kiện giúp giảm metadata áp dụng toàn cục. Không xóa hoặc viết lại conditions do tool sinh ra chỉ vì muốn file ngắn hơn.

## 9. Tăng độ phủ workload

Agent chỉ biết hành vi đã chạy. Vì vậy, chất lượng metadata phụ thuộc trực tiếp vào chất lượng workload.

1. Lập danh sách endpoint, message handler, scheduled task và luồng tích hợp.
2. Liệt kê các kiểu dữ liệu hoặc resource được truy cập động trong từng luồng.
3. Chạy agent với dữ liệu đại diện cho mỗi nhóm.
4. Chạy lại với các nhánh cấu hình quan trọng.
5. So sánh metadata giữa các lần chạy.
6. Đối chiếu entry mới với source code hoặc thư viện tạo access.
7. Chạy native test sau khi đưa metadata vào build.

| Luồng | Dữ liệu cần đi qua | Dynamic access cần quan sát |
|---|---|---|
| REST order | DTO, nested record, enum | Jackson reflection/binding |
| Upload CSV | File mẫu, parser | Resource và reflection nếu parser dùng |
| OAuth callback | Provider, key/certificate | Resource, proxy hoặc reflection |
| Message consumer | Nhiều event subtype | Serialization/deserialization |
| Plugin nội bộ đã đóng gói | Provider class | Service discovery, reflection nếu cần |
| Scheduled report | Template và locale | Resource bundle, template access |

Độ phủ không chỉ là số lượng test. Cần bảo đảm test thực sự gọi các nhánh chứa dynamic access.

## 10. Lọc output: caller filter và access filter

Agent có hai loại filter chính:

- **Caller filter:** access được gọi từ class nào? Filter dựa trên class thực hiện lời gọi động.
- **Access filter:** access đang nhắm tới class hoặc member nào? Filter dựa trên target của truy cập và có thể loại class cùng các member của nó khỏi metadata.

### Caller filter

Caller filter hữu ích để loại các access phát sinh từ test infrastructure hoặc package không thuộc ứng dụng cần thu thập.

Ví dụ `caller-filter.json`:

~~~json
{
  "rules": [
    {"includeClasses": "com.example.orders.**"},
    {"excludeClasses": "com.example.orders.test.**"}
  ]
}
~~~

~~~bash
java -agentlib:native-image-agent=caller-filter-file=caller-filter.json,config-output-dir=build/native/agent-filtered -jar build/libs/orders-service.jar
~~~

Các rule được xét theo thứ tự; rule sau có thể ghi đè quyết định trước. Mẫu `.*` khớp class trực tiếp trong package; `.**` bao gồm cả subpackage ở mọi cấp.

### Access filter

Access filter dùng để loại target không muốn xuất hiện trong metadata. Ví dụ loại package nội bộ của test framework:

~~~json
{
  "rules": [
    {"excludeClasses": "org.example.testinfra.**"}
  ]
}
~~~

~~~bash
java -agentlib:native-image-agent=access-filter-file=access-filter.json,config-output-dir=build/native/agent-filtered -jar build/libs/orders-service.jar
~~~

Có thể kết hợp caller filter và access filter:

~~~bash
java -agentlib:native-image-agent=caller-filter-file=caller-filter.json,access-filter-file=access-filter.json,config-output-dir=build/native/agent-filtered -jar build/libs/orders-service.jar
~~~

### Giữ built-in filters

Agent có built-in filters để bỏ qua nhiều access do JVM và một số phần JDK thực hiện mà Native Image hỗ trợ sẵn. Tắt `no-builtin-caller-filter` hoặc `no-builtin-heuristic-filter` có thể tạo output rất lớn và ít hữu ích. Chỉ dùng trong điều tra thử nghiệm khi có lý do rõ ràng; không dùng output đó làm metadata production mặc định.

Filter quá rộng cũng có thể loại nhầm access của ứng dụng. Sau khi thêm filter, phải so sánh output trước/sau và chạy native tests bao phủ các luồng liên quan.

## 11. Tích hợp với Spring Boot

Spring Boot AOT thường tự tạo phần lớn hints cần thiết. Vì vậy, agent nên được dùng để **tìm phần còn thiếu** hoặc xác nhận một thư viện/pattern cụ thể, không phải để thay thế Spring AOT.

Chạy JAR đã có AOT assets cùng agent:

~~~bash
java -Dspring.aot.enabled=true -agentlib:native-image-agent=config-output-dir=build/native/agent-output -jar target/orders-service.jar
~~~

Sau khi app khởi động, gọi các luồng cần kiểm tra rồi dừng process bình thường. Review metadata và chỉ giữ các entry còn cần thiết.

Nếu chạy test suite, output có thể chứa metadata cho test engine, mocking, assertion hoặc server test. Có thể:

- Chạy ứng dụng trực tiếp để tập trung vào behavior production.
- Dùng caller/access filters để loại target/caller không mong muốn.
- Dùng chế độ conditional của Native Build Tools nếu plugin đã được cấu hình.
- Copy output test vào `src/test/resources/META-INF/native-image` khi metadata chỉ phục vụ native tests.
- Chỉ đưa metadata vào `src/main/resources/META-INF/native-image` sau khi xác định nó cần cho production.

## 12. Maven Native Build Tools

Native Build Tools Maven plugin hỗ trợ gắn tracing agent vào test hoặc application run. Agent bị tắt mặc định; có thể bật qua command line bằng `-Dagent=true` nếu project đã cấu hình native profile/plugin.

### Thu thập từ test suite

~~~bash
./mvnw -Pnative -Dagent=true test
~~~

Agent được gắn vào Maven Surefire test execution; output mặc định thường ở:

~~~text
target/native/agent-output/test/
~~~

Nếu đã cấu hình `metadataCopy` trong plugin, có thể copy output sau khi test:

~~~bash
./mvnw -Pnative -Dagent=true test native:metadata-copy
~~~

Ví dụ cấu hình rút gọn để copy metadata test vào source test:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <agent>
            <enabled>true</enabled>
            <metadataCopy>
                <disabledStages>
                    <stage>main</stage>
                </disabledStages>
                <merge>true</merge>
                <outputDirectory>src/test/resources/META-INF/native-image</outputDirectory>
            </metadataCopy>
        </agent>
    </configuration>
</plugin>
~~~

`disabledStages` trong ví dụ bỏ qua metadata của main stage và chỉ copy output test. Nếu metadata được xác nhận cần cho ứng dụng production, hãy chọn output directory trong `src/main/resources/META-INF/native-image` và không loại main stage một cách vô ý.

### Thu thập khi chạy ứng dụng

Thu thập từ main application cần một process Java được fork riêng. Native Build Tools Maven plugin có thể phối hợp với `exec-maven-plugin`; cấu hình execution ID phải khớp với `agentExecutionId`.

Ví dụ khi project đã khai báo execution `java-agent`:

~~~bash
./mvnw -Pnative -Dagent=true -DskipTests -DskipNativeBuild=true package exec:exec@java-agent
~~~

Output main thường nằm trong:

~~~text
target/native/agent-output/main/
~~~

Chi tiết cấu hình fork phụ thuộc main class và classpath của dự án. Dùng ví dụ từ tài liệu Native Build Tools làm mẫu rồi điều chỉnh execution ID, main class và working directory.

Khi đã có metadata production, build lại native executable và chạy integration test:

~~~bash
./mvnw -Pnative -DskipTests package
~~~

## 13. Gradle Native Build Tools

Với Gradle, tracing agent được cấu hình trong block `graalvmNative.agent` khi plugin `org.graalvm.buildtools.native` đã được áp dụng.

Ví dụ cấu hình tối giản:

~~~groovy
graalvmNative {
    agent {
        enabled = true
        defaultMode = "standard"
        metadataCopy {
            inputTaskNames.add("test")
            outputDirectories.add("src/test/resources/META-INF/native-image")
            mergeWithExisting = true
        }
    }
}
~~~

Thu thập metadata trong test:

~~~bash
./gradlew -Pagent=standard nativeTest
~~~

Copy metadata từ task test:

~~~bash
./gradlew metadataCopy --task test
~~~

Nếu dùng `nativeRun` hoặc `run` để thu thập metadata từ ứng dụng:

~~~bash
./gradlew metadataCopy --task run
~~~

Output directory trong `metadataCopy` nên được chọn theo mục đích:

- `src/test/resources/META-INF/native-image`: metadata chỉ phục vụ native tests.
- `src/main/resources/META-INF/native-image`: metadata đã review và cần cho production native build.

Tên task và DSL có thể thay đổi theo phiên bản Native Build Tools. Kiểm tra version plugin đang resolve và tài liệu cùng version; đừng chép cấu hình của một plugin version khác mà chưa xác nhận.

## 14. Đưa metadata vào native build

Với metadata đã review, vị trí resource tiêu chuẩn trong ứng dụng thường là:

~~~text
src/main/resources/
└── META-INF/
    └── native-image/
        └── com.example/
            └── orders-service/
                └── reachability-metadata.json
~~~

Thư mục `META-INF/native-image` (hoặc subdirectory bên dưới) được Native Image tìm kiếm trên classpath/module path. Các file metadata cũ theo loại riêng cũng có thể được nhận diện theo quy tắc của GraalVM version tương ứng.

Nếu metadata nằm ngoài classpath, có thể truyền thư mục trực tiếp cho Native Image bằng:

~~~bash
native-image -H:ConfigurationFileDirectories=build/native/agent-output -jar target/orders-service.jar
~~~

Khi dùng Maven/Gradle plugin, metadata trong classpath thường được phát hiện tự động; metadata ngoài classpath cần cấu hình build argument tương ứng. Không thêm cùng một bộ metadata qua nhiều nguồn khác nhau nếu không cần thiết, vì có thể gây khó khăn khi truy vết.

## 15. Review metadata trước khi commit

Trước khi đưa metadata vào source:

1. **Xác định nguồn:** entry đến từ application, framework, test hoặc thư viện nào?
2. **Kiểm tra target:** class/member/resource có tồn tại trong phiên bản dependency hiện tại không?
3. **Kiểm tra phạm vi:** có thể đăng ký một constructor/method cụ thể thay vì toàn bộ member không?
4. **Kiểm tra conditions:** có điều kiện `typeReached` hoặc condition khác cần giữ nguyên không?
5. **Loại trùng:** hợp nhất entry trùng theo đúng semantics, không chỉ xóa dòng lặp bằng text.
6. **Kiểm tra môi trường:** đường dẫn resource và tên class có phụ thuộc OS/profile không?
7. **Kiểm tra test-only:** metadata nào chỉ phục vụ test nên nằm trong test resources.
8. **Kiểm tra dependency version:** nâng phiên bản thư viện có thể làm metadata cũ không còn đúng.

Metadata càng hẹp và có nguồn gốc rõ ràng thì càng dễ bảo trì. Tránh bật toàn bộ reflection cho mọi class chỉ để làm một test pass.

## 16. Agent không thay thế reachability metadata repository

Một số thư viện bên thứ ba đã cung cấp reachability metadata trong GraalVM Reachability Metadata Repository. Native Build Tools có thể tự tải metadata tương ứng với dependency version khi build.

Nên kiểm tra theo thứ tự:

1. Spring AOT hoặc framework integration đã cung cấp hints chưa?
2. Thư viện có metadata chính thức hoặc metadata trong repository chưa?
3. Có thể nâng dependency lên phiên bản đã hỗ trợ Native Image không?
4. Nếu còn thiếu, dùng tracing agent để quan sát behavior.
5. Nếu agent không bao phủ đủ hoặc cần metadata có điều kiện, viết `RuntimeHintsRegistrar`/metadata thủ công có kiểm thử.

Không nên giữ một lượng lớn metadata agent sinh ra nếu dependency đã cung cấp metadata chính thức và entry đó không cần cho application code.

## 17. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Thư mục output rỗng | Không chạy dynamic path, agent không được attach hoặc JVM chưa thoát | Kiểm tra command line, workload và shutdown |
| Chỉ có metadata cho startup | Chưa gọi endpoint/job cần thiết | Tăng độ phủ workload |
| Metadata có nhiều class JUnit/Mockito | Chạy test suite và thu cả test infrastructure | Dùng app trực tiếp, filter hoặc tách test metadata |
| Native vẫn lỗi dù có metadata | Nhánh lỗi chưa được chạy, metadata target sai hoặc loại hint không phù hợp | Đọc native error, tái hiện path, bổ sung đúng hint |
| Metadata không được build sử dụng | Đặt sai thư mục hoặc không nằm trên classpath | Đặt dưới `META-INF/native-image` hoặc cấu hình directory argument |
| Nhiều process ghi đè output | Dùng chung `config-output-dir` | Mỗi process một thư mục rồi merge |
| Output quá lớn | Filter rộng hoặc built-in filter bị tắt | Khôi phục built-in filters, review caller/access filters |
| Build pass nhưng production lỗi | Test chưa bao phủ config/input/branch thực tế | Thêm integration scenario và chạy native executable |

## 18. Quy trình hoàn chỉnh từ JVM đến Native Image

~~~mermaid
flowchart TD
    A["Build JAR có Spring AOT"] --> B["Chạy JVM với tracing agent"]
    B --> C["Gọi API/job/message theo workload"]
    C --> D["Agent ghi metadata"]
    D --> E["Review, filter, merge"]
    E --> F["Commit metadata cần thiết"]
    F --> G["Build Native Image"]
    G --> H["Chạy native integration tests"]
    H --> I{"Tất cả luồng đã kiểm tra pass?"}
    I -->|Chưa| B
    I -->|Rồi| J["Đóng gói và kiểm thử container"]
~~~

Checklist:

- [ ] Build ứng dụng JVM và Spring AOT thành công.
- [ ] Chạy agent trên đúng GraalVM JDK/version.
- [ ] Chọn output directory mới, riêng cho lần thu thập.
- [ ] Bao phủ REST, messaging, scheduled jobs, serialization và resource access.
- [ ] Chạy nhiều input/configuration để đi qua các nhánh động.
- [ ] Dừng JVM có kiểm soát để agent ghi output.
- [ ] Review từng metadata entry và nguồn phát sinh.
- [ ] Loại metadata chỉ phục vụ test nếu không cần cho production.
- [ ] Đặt metadata đã duyệt trong `META-INF/native-image`.
- [ ] Build lại native executable.
- [ ] Chạy native integration tests trên các luồng đã quan sát.
- [ ] Chạy thử container cuối cùng với cấu hình/resource tương đương deployment.

## 19. Bài tập tự kiểm tra

**Câu 1.** Tracing Agent chạy ở giai đoạn nào?

**Gợi ý:** agent gắn vào JVM process để quan sát dynamic access khi ứng dụng chạy; nó không quan sát trực tiếp một native executable.

**Câu 2.** Vì sao metadata agent sinh ra không bảo đảm ứng dụng tương thích hoàn toàn?

**Gợi ý:** agent chỉ ghi nhận code path đã thực thi. Những nhánh chưa chạy sẽ không có trong output.

**Câu 3.** `config-output-dir` và `config-merge-dir` khác nhau thế nào?

**Gợi ý:** một tùy chọn tạo output mới; tùy chọn kia bổ sung/merge access vào bộ metadata hiện có.

**Câu 4.** Vì sao chạy test suite có thể tạo metadata thừa?

**Gợi ý:** agent quan sát cả test framework, mock, assertion và các dependency chỉ phục vụ test.

**Câu 5.** Caller filter khác access filter ở đâu?

**Gợi ý:** caller filter lọc nơi phát sinh access; access filter lọc target của access.

**Câu 6.** Vì sao phải chạy native integration test sau khi copy metadata?

**Gợi ý:** cần xác nhận Native Image thực sự nạp metadata và đường code cuối cùng hoạt động trên executable, không chỉ trên JVM.

**Câu 7.** Khi nhiều JVM process chạy agent cùng lúc, nên dùng chung output directory không?

**Gợi ý:** không. Mỗi process nên ghi một thư mục riêng rồi merge các bộ output.

## 20. Tài liệu tham khảo

- [GraalVM — Collect Metadata with the Tracing Agent](https://www.graalvm.org/reference-manual/native-image/Agent/): cách gắn agent, output/merge, filters, trace file và native-image-utils.
- [GraalVM — Configure Native Image with the Tracing Agent](https://www.graalvm.org/latest/reference-manual/native-image/guides/configure-with-tracing-agent/): quy trình tạo metadata và build executable.
- [Spring Boot Reference — Advanced Native Images Topics](https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html): cách dùng tracing agent với Spring AOT, chạy ứng dụng hoặc test, review và access filters.
- [GraalVM Native Build Tools — Maven Plugin](https://graalvm.github.io/native-build-tools/latest/maven-plugin): cấu hình agent, chạy test/application và metadata copy.
- [GraalVM Native Build Tools — Gradle Plugin](https://graalvm.github.io/native-build-tools/latest/gradle-plugin): agent modes, filter files và metadataCopy task.

**Ghi nhớ:** Tracing Agent là công cụ quan sát dynamic access trong một JVM run để hỗ trợ tạo reachability metadata cho Native Image. Chất lượng output phụ thuộc workload, filter và review. Hãy dùng Spring AOT cùng metadata chính thức của dependency trước, chạy agent để tìm phần còn thiếu, lưu metadata đã duyệt dưới `META-INF/native-image`, rồi xác minh bằng native integration tests và container thực tế.
