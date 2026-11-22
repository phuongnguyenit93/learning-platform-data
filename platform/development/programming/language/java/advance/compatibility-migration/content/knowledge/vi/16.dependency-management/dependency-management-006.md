# Kiểm tra dependency bị bỏ duy trì và lựa chọn thay thế

Trong **Java Advance Compatibility Migration**, thay đổi JDK không chỉ ảnh hưởng mã nguồn do lập trình viên viết. Mỗi ứng dụng còn phụ thuộc vào framework, thư viện runtime, plugin build, annotation processor, agent, thư viện native và những JAR bắc cầu mà nhóm phát triển có thể không trực tiếp khai báo. Một thành phần **không còn được duy trì** có thể ngăn việc lên Java mới, tạo lỗ hổng bảo mật không được vá hoặc làm hệ thống phụ thuộc vĩnh viễn vào API nội bộ của JDK.

Tuy nhiên, “bị bỏ duy trì” không thể xác định chỉ bằng việc repository ít commit hoặc đã lâu chưa tăng phiên bản. Một library nhỏ, ổn định, ít thay đổi vẫn có thể đáp ứng yêu cầu; một dự án nhiều commit nhưng không sửa lỗi bảo mật cũng có thể có rủi ro cao. Vì vậy, cần kết hợp **bằng chứng về trạng thái bảo trì**, **đường phụ thuộc thực tế**, **mức phơi nhiễm**, **hợp đồng kỹ thuật** và **khả năng vận hành trên JDK mục tiêu** để chọn giải pháp.

Bài này trình bày cách kiểm kê direct/transitive dependencies, xác định những dấu hiệu bị bỏ duy trì, đánh giá các phương án nâng cấp, thay thế, loại bỏ, fork hoặc cô lập; sau đó xác minh chức năng, dữ liệu, tương thích nhị phân, bảo mật và hiệu năng trước khi kết luận migration thành công.

## 1. Phạm vi dependency trong một ứng dụng Java

Dependency không chỉ là các mục `implementation` trong Gradle hoặc `<dependency>` trong Maven. Cần xem toàn bộ chuỗi tạo ra và vận hành ứng dụng.

| Nhóm | Ví dụ | Rủi ro khi nâng JDK |
|---|---|---|
| Thư viện compile | API module, annotations, utility classes | Cú pháp/API không phù hợp JDK đích |
| Thư viện runtime | JSON, ORM, HTTP, database driver | Lỗi class loading, serialization, network |
| Dependency bắc cầu | JAR được framework/client kéo vào | Version cũ ẩn trong dependency graph |
| Build plugin | Compiler, packaging, shading, code generation | Plugin không chạy với Gradle/Maven/JDK mới |
| Annotation processor | Mapper, metamodel, generator | Phụ thuộc AST hoặc javac internals |
| Test dependency | Test runner, mocking, coverage | Test không phát hiện hoặc instrumentation lỗi |
| Java agent | APM, profiler, tracing | Bytecode transform không hỗ trợ class-file mới |
| Native dependency | JNI/JNA, native crypto, compression | ABI/architecture hoặc platform mismatch |
| Framework/container | Web runtime, DI, ORM | Java baseline, namespace hoặc cấu hình thay đổi |
| Thư viện nội bộ | Shared SDK, client, common-core | Không có owner, CI, release hoặc support policy |
| Runtime bổ sung | JAR của application server, injected library | Artifact chạy khác graph build |
| Image và tooling | JDK container image, Gradle/Maven wrapper | Toolchain lỗi hoặc runtime đã EOL |

Một dependency có thể xuất hiện trong nhiều nhóm. Ví dụ, ORM framework dùng bytecode library cho runtime proxy; cùng library này có thể được test runner dùng khi mocking. Nâng một trong các thành phần mà bỏ qua thành phần còn lại có thể tạo xung đột.

**Nguyên tắc:** kiểm kê theo đường đi **source → build → resolved graph → packaged artifact → runtime/deployment**, không chỉ dựa vào một file khai báo.

## 2. Phân biệt deprecated, EOL, abandoned và vulnerable

### 2.1. Deprecated

Một API hoặc package được đánh dấu deprecated nghĩa là nhà phát hành không còn khuyến khích sử dụng hoặc đang hướng người dùng tới API khác. Deprecation có thể kéo dài nhiều release. Nó không tự chứng minh component đã hết bảo trì.

### 2.2. End-of-life (EOL)

EOL thường áp dụng cho **một nhánh hoặc phiên bản cụ thể** theo chính sách nhà phát hành. Dự án có thể vẫn duy trì các nhánh mới hơn nhưng không cấp security fixes cho nhánh cũ.

Ví dụ giả định: framework 1.x hết hỗ trợ, còn 2.x được bảo trì. Khi đó ghi “framework X bị bỏ duy trì” là không chính xác; rủi ro nằm ở **branch 1.x** mà ứng dụng đang dùng.

### 2.3. Abandoned/unmaintained

Một dự án có thể ngừng có maintainer, repository bị archive, release process ngừng hoặc không còn người phản hồi lỗ hổng và incompatibility mới. Đây là trạng thái cần được xác minh từ nguồn phù hợp, không nên chỉ suy ra từ thời điểm commit cuối.

### 2.4. Vulnerable

Một component có thể có security advisory hoặc CVE dù vẫn đang được duy trì. Ngược lại, một thư viện không còn duy trì chưa chắc có lỗ hổng đã công bố. Cần đánh giá **artifact và version đang dùng**, khả năng khai thác, đường code thực tế và bản vá hiện có.

| Trạng thái | Câu hỏi trọng tâm |
|---|---|
| Deprecated | Có hướng migration chính thức hoặc ngày loại bỏ không? |
| EOL | Version/branch hiện tại còn được vendor bảo trì không? |
| Unmaintained | Khi có lỗi JDK/security, ai có thể sửa và phát hành? |
| Vulnerable | Có advisory ảnh hưởng version, code path và cấu hình của ứng dụng không? |
| Unsupported JDK | Library có hỗ trợ JDK mục tiêu hoặc có bằng chứng kiểm thử không? |

Một thư viện có thể nằm ở nhiều trạng thái cùng lúc. Việc xử lý cần ưu tiên dựa trên rủi ro tổng thể.

## 3. Vì sao Java migration làm rủi ro dependency lộ rõ?

Những vấn đề thường gặp khi nâng JDK:

1. **Strong encapsulation:** thư viện cũ truy cập `sun.*`, `jdk.internal.*` hoặc deep reflection có thể bị chặn.
2. **JDK API bị loại bỏ:** code có thể phụ thuộc component từng đi kèm JDK nhưng không còn trên runtime mới.
3. **Class-file version:** bytecode parser hoặc instrumentation library cũ không hiểu major version mới.
4. **Source/AST compatibility:** annotation processor dùng cấu trúc `com.sun.tools.javac.*` nội bộ có thể lỗi.
5. **Framework baseline:** bản framework cũ không hỗ trợ runtime, còn bản mới đòi JDK tối thiểu cao hơn.
6. **Namespace migration:** một số hệ sinh thái chuyển từ `javax.*` sang `jakarta.*` theo version framework.
7. **TLS policy:** thư viện HTTP hoặc crypto cũ giả định giao thức và thuật toán không còn được bật mặc định.
8. **Serialization behavior:** thay framework/codec có thể đổi dữ liệu hoặc kết quả mapping.
9. **Build/test tool:** test runner và plugin cũ có thể không khởi động hoặc tự vô hiệu hóa test.
10. **Runtime packaging:** dependency được đưa vào fat JAR hoặc container khác với graph CI.

Vì thế, “mã nguồn đã biên dịch” chỉ là một bằng chứng nhỏ. Phải biết thư viện đang dùng có khả năng thực thi và được sửa lỗi trong chu kỳ JDK mới hay không.

## 4. Xác định phạm vi kiểm kê

Trước khi đánh giá trạng thái bảo trì, cần xác định **những gì phải được kiểm tra**.

Với mỗi ứng dụng hoặc module, ghi:

- Tên service/module và chủ sở hữu.
- JDK hiện tại, JDK mục tiêu, JDK của CI và runtime container.
- Phiên bản Gradle/Maven wrapper, compiler plugin và các plugin chủ chốt.
- Direct dependencies và transitive dependencies.
- Compile/runtime/test/annotation-processor classpaths.
- Libraries do application server hoặc runtime platform cung cấp.
- Java agents, native dependencies và các JAR được nạp động.
- Cấu trúc artifact cuối: plain JAR, fat JAR, WAR/EAR, image.
- Các chức năng, dữ liệu và giao thức phụ thuộc library đang xét.

Một hệ thống có thể chạy bằng dependency khác build: một driver được cài vào application server, một agent gắn qua `JAVA_TOOL_OPTIONS` hoặc một plugin được tải từ thư mục ngoài. Nếu không kiểm kê, các phần này có thể gây lỗi sau deploy dù local build xanh.

### 4.1. Version khai báo chưa chắc là version thực tế

Một khai báo dependency có thể dùng BOM, constraint, version range hoặc dynamic version. Ví dụ minh họa:

~~~groovy
dependencies {
    implementation 'org.example:protocol-client:2.+'
}
~~~

Đây **không phải cấu hình khuyến nghị** cho migration cần tái lập. Version được resolve có thể thay đổi theo thời điểm, cache và repository. Khi lập inventory cần ghi tọa độ artifact thực tế đã chọn, không chỉ `2.+`.

Một định danh thường gặp:

~~~text
groupId:artifactId:version
~~~

Tùy build tool còn có classifier, type, variant và capabilities. Nếu thiếu thông tin này, có thể nhận nhầm artifact hoặc không tái hiện được dependency graph.

## 5. Kiểm kê bằng Gradle

Với Gradle Java plugin, các lệnh tham khảo:

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
~~~

Trong dự án multi-module:

~~~bash
./gradlew :orders-service:dependencies \
  --configuration runtimeClasspath
~~~

Khi cần tìm lý do một version được chọn:

~~~bash
./gradlew :orders-service:dependencyInsight \
  --dependency jackson-databind \
  --configuration runtimeClasspath
~~~

`jackson-databind` chỉ là tên dùng để minh họa lệnh điều tra; không hàm ý version cụ thể nào bị bỏ duy trì.

### 5.1. Các configuration cần phân biệt

| Configuration hoặc classpath | Mục đích |
|---|---|
| `compileClasspath` | API compiler thấy |
| `runtimeClasspath` | Các JAR ứng dụng cần khi chạy |
| `testRuntimeClasspath` | Thư viện cần khi test |
| `annotationProcessor` | Processor chạy lúc biên dịch |
| Buildscript/plugin classpath | Plugin do build tool chạy |
| Custom integration-test configurations | Libraries cho integration/functional tests |

Không được bỏ qua test dependencies. Một mock framework hoặc coverage agent cũ có thể không hiểu class-file version của JDK mới, khiến build/test pipeline hỏng dù production library tương thích.

### 5.2. Build plugins

Lệnh tham khảo:

~~~bash
./gradlew buildEnvironment
~~~

Lệnh giúp quan sát buildscript dependencies trong những dự án phù hợp. Plugin resolution qua `plugins {}` và `pluginManagement` có thể có cơ chế riêng; cần ghi plugin ID/version và kiểm tra compatibility với JDK/Gradle wrapper chứ không suy rằng một báo cáo hiển thị đủ tất cả.

### 5.3. Kiểm soát graph tái lập

Gradle có dependency locking, version catalogs, dependency constraints và dependency verification. Những cơ chế này có thể giúp ổn định version đã resolve và kiểm tra tính toàn vẹn artifact. Chúng **không tự chứng minh library được duy trì**, nhưng giúp đối chiếu chính xác trước/sau khi nâng JDK.

## 6. Kiểm kê bằng Maven

Các lệnh cơ bản:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.example:legacy-codec
mvn help:effective-pom
~~~

`dependency:tree` hiển thị graph theo Maven resolution. `help:effective-pom` hữu ích để thấy cấu hình thừa kế qua parent, BOM và `dependencyManagement`.

Một số version của Maven Dependency Plugin hỗ trợ:

~~~bash
mvn dependency:tree -Dverbose
~~~

Thông tin omitted/conflict nodes có thể khác tùy plugin version. Khi đánh giá, hãy dựa vào output thật và tọa độ được resolve.

### 6.1. BOM và dependencyManagement

Nếu bản `pom.xml` chỉ khai báo group/artifact mà không có version, cần kiểm tra version đến từ parent hoặc imported BOM. Không nên nhìn một dòng dependency rồi kết luận nó đang dùng version mới.

### 6.2. Plugin dependencies

Ngoài application dependencies còn có compiler, surefire, failsafe, shade, assembly, code generator và các plugin Maven khác. Một plugin không hỗ trợ Java mục tiêu có thể làm quá trình build lỗi trước khi code ứng dụng được compile.

### 6.3. Dependency mediation

Maven giải quyết xung đột version theo quan hệ dependency và các ràng buộc cấu hình; version cuối cùng có thể không phải version mới nhất. Nếu cần override, phải hiểu graph và compatibility của dependency cấp trên, không sửa JAR thủ công trong local Maven cache.

## 7. Kiểm tra artifact thực sự được đóng gói

Sau khi lấy graph build, cần kiểm tra artifact mà runtime sẽ dùng.

Ví dụ:

~~~bash
jar tf application.jar
~~~

Trong fat JAR, thư viện có thể được lồng hoặc bị shade. Với WAR, classpath cũng có thể bao gồm các JAR do servlet container cung cấp. Với container image, entrypoint có thể bổ sung Java agents hoặc external libraries.

Các câu hỏi cần trả lời:

- JAR cũ có còn nằm trong artifact không?
- Cùng một thư viện có nhiều version qua các thư mục khác nhau không?
- Có bytecode đã được shade mà tên artifact không còn xuất hiện không?
- Có native library được tải ở runtime ngoài dependency graph không?
- Plugin hoặc application server có thay thế driver bản khác không?

**Xóa dependency khỏi build file chưa đủ để chứng minh nó đã biến mất khỏi deployment**. Phải kiểm tra toàn bộ runtime composition.

## 8. SBOM và inventory có cấu trúc

**Software Bill of Materials (SBOM)** giúp ghi các component và quan hệ phụ thuộc ở định dạng máy đọc, thường dùng CycloneDX hoặc SPDX.

Một bản ghi minh họa:

~~~yaml
component:
  name: legacy-codec
  group: org.example
  version: 1.4.2
  purl: pkg:maven/org.example/legacy-codec@1.4.2
  direct: false
  scope: runtime
  introducedBy: org.example:protocol-client:3.0
  usedBy:
    - orders-service
  owner: integration-team
  reviewStatus: pending
~~~

Tọa độ trên là **giả định**, không phải khẳng định một package thật có trạng thái bảo trì nào.

SBOM nên được đối chiếu với artifact và deployment vì một số component có thể được inject bởi runtime, nhúng trong image hoặc tải động. Với mỗi thành phần cần ghi version, nguồn repository, quan hệ dependency, owner và ngày rà soát.

SBOM hỗ trợ kiểm tra nhưng không tự cho biết component có được bảo trì tốt không. Trạng thái đó vẫn phải dựa trên nguồn chính thức và bằng chứng.

## 9. Những tín hiệu cho thấy thư viện có thể đã bỏ duy trì

| Tín hiệu | Ý nghĩa cần điều tra | Cảnh báo khi diễn giải |
|---|---|---|
| Repository chính thức đã archived | Có thể ngừng nhận thay đổi | Có thể đã chuyển sang repository kế nhiệm |
| Maintainer thông báo dừng phát triển | Bằng chứng mạnh về trạng thái dự án | Cần xem phạm vi branch/version |
| Không có release trong thời gian dài | Có thể chưa hỗ trợ JDK mới | Thư viện ổn định có thể không cần nhiều release |
| Issue/PR nghiêm trọng không phản hồi | Khả năng xử lý lỗi có vấn đề | Cần xem tác động và nguồn chính thức |
| Security advisory không có bản vá | Rủi ro bảo mật cao | Cần xác định exposure/version chính xác |
| Build CI dùng JDK quá cũ | Thiếu bằng chứng tương thích runtime mới | Có thể library vẫn chạy nếu API rất ổn định |
| Tài liệu không nhắc JDK mục tiêu | Chưa rõ support matrix | Không tự kết luận bị bỏ duy trì |
| Không còn người phát hành | Không có đường phát hành fix | Cần kiểm tra dự án kế nhiệm/fork |
| Dependency vào API đã bị gỡ | Migration có thể bị chặn | Cần kiểm tra khả năng thay API và workaround |
| License/provenance không rõ | Rủi ro pháp lý và supply chain | Không phải bằng chứng trực tiếp về maintenance |

### 9.1. Nguồn bằng chứng đáng ưu tiên

Ưu tiên: thông báo maintainer/vendor, chính sách support/EOL, release notes chính thức, security advisories, changelog, documentation về JDK compatibility, artifact publication và repository chính thức.

Không nên dựa vào một trang thống kê cộng đồng mà không đối chiếu nguồn gốc. Fork không có quan hệ rõ với upstream có thể tạo thông tin nhầm.

### 9.2. Ghi mức độ chắc chắn

Một phương pháp:

- **Confirmed EOL:** nhà phát hành đã thông báo version/branch hết hỗ trợ.
- **Confirmed archived:** repository chính thức đã archive và không có kế hoạch phát triển tại đó.
- **Likely unmaintained:** nhiều tín hiệu mạnh nhưng chưa có xác nhận trực tiếp.
- **Maintained with caveats:** có hỗ trợ nhưng có giới hạn JDK, feature hoặc security policy.
- **Unknown:** thiếu bằng chứng, cần người phụ trách tìm hiểu.

Không biến `Unknown` thành `Maintained` chỉ vì scanner không tìm ra CVE.

## 10. Không đồng nhất ít commit với rủi ro cao

Ba tình huống giả định:

**Thư viện A** làm một phép biến đổi dữ liệu đơn giản, ít phát hành, có tests và maintainer vẫn phản hồi sự cố. Thay nó ngay có thể không có lợi ích đáng kể.

**Thư viện B** có nhiều commit gần đây nhưng một advisory quan trọng ảnh hưởng production chưa được xử lý. Nó có thể cần ưu tiên cao dù cộng đồng sôi động.

**Thư viện C** dùng compiler internals, không có bản tương thích JDK đích và làm build thất bại. Nó là blocker của Java migration dù không có CVE.

Đánh giá nên dựa vào **tác động tới ứng dụng trên JDK mục tiêu** và khả năng ứng phó với lỗi mới, không dùng một số liệu duy nhất.

## 11. Kiểm tra JDK compatibility độc lập với maintenance

Một thư viện được duy trì vẫn có thể đòi Java release cao hơn runtime mà ứng dụng hỗ trợ.

Cần xác định:

1. Java baseline được upstream công bố.
2. JDK dùng để build library.
3. Class-file major version.
4. Tập Java SE API mà library yêu cầu.
5. Phụ thuộc vào internal APIs, reflection và module access.
6. Framework và container version tương thích.
7. Native/OS architecture được hỗ trợ.
8. JDK versions mà CI của upstream có kiểm thử.

Ví dụ class-file versions:

| Java | Major version |
|---|---:|
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |
| 25 | 69 |

Một JAR có class file major 65 không chạy được trên JVM Java 17 theo quy tắc class-file version thông thường. Nhưng major 52 cũng chưa đủ chứng minh nó chỉ dùng Java 8 API; compiler có thể đã tạo bytecode Java 8 với `-source`/`-target` mà không giới hạn API đích.

### 11.1. Dùng javap

~~~bash
javap -verbose -classpath lib/example.jar \
  org.example.Sample
~~~

Tìm:

~~~text
major version: 61
~~~

Với multi-release JAR, cần quan tâm những class variant tương ứng với runtime. Không kiểm tra một class rồi suy ra toàn bộ artifact đều cùng class-file version.

### 11.2. Dùng jdeps

~~~bash
jdeps --jdk-internals lib/example.jar
~~~

Công cụ hỗ trợ tìm một số tham chiếu tới JDK internal APIs; nó không phát hiện đầy đủ reflection dùng chuỗi, native code hoặc resource/config. Cần runtime test bổ sung.

## 12. Dependency bắc cầu: nguồn rủi ro khó nhìn thấy

Ví dụ:

~~~text
orders-service
   |
   +-- protocol-client:3.0
          |
          +-- legacy-codec:1.4
          |
          +-- transport-api:2.1
~~~

Nếu `legacy-codec` không còn duy trì, có những lựa chọn:

- Nâng `protocol-client` lên version không còn kéo codec cũ.
- Thay cả `protocol-client` bằng thư viện khác.
- Nếu API cho phép, thay version của codec bằng bản tương thích được hỗ trợ.
- Cô lập chức năng sử dụng codec và thay theo từng bước.
- Loại bỏ chức năng nếu không còn được dùng.

**Không nên chỉ exclude `legacy-codec`** nếu `protocol-client` vẫn gọi lớp trong đó. Build có thể pass nhưng một luồng runtime hiếm mới gặp `NoClassDefFoundError`.

Trong các framework có BOM hoặc compatibility matrix, nên ưu tiên tổ hợp dependency được kiểm chứng thay vì override một phiên bản transitive ngẫu nhiên.

## 13. Đánh giá lỗ hổng bảo mật thực tế

Với mỗi dependency có advisory:

- Advisory áp dụng cho artifact/version nào?
- Có fix version hoặc vendor backport không?
- Điều kiện khai thác liên quan feature/config nào?
- Có untrusted input đi tới code path đó không?
- Ứng dụng có quyền truy cập nhạy cảm không?
- Có compensating controls hoặc cách cô lập tạm thời không?
- Thời gian còn lại để thay thế có chấp nhận được không?
- Nếu thư viện bỏ duy trì, ai sẽ sửa khi có lỗ hổng tiếp theo?

Một scanner chỉ đối chiếu tọa độ/version có thể false positive hoặc false negative. Cần kiểm tra advisory nguồn và reachability theo kiến trúc thực tế.

Ngược lại, **không có CVE không chứng minh một thư viện không có lỗ hổng**. Nếu nó không được duy trì và xử lý input không tin cậy, rủi ro tương lai vẫn đáng xem xét.

## 14. License, provenance và an toàn chuỗi cung ứng

Một thư viện thay thế phải phù hợp không chỉ về API.

Kiểm tra:

- License của upstream và candidate; nghĩa vụ notice/attribution/disclosure nếu áp dụng.
- Quyền fork, sửa, đóng gói và phân phối theo mục đích tổ chức.
- Source repository chính thức và identity nhà phát hành artifact.
- Artifact coordinates, checksum/signature và repository phân phối.
- Chính sách phát hành, security response và cách kiểm soát quyền publish.
- Rủi ro dependency confusion, artifact hijack và fork giả danh.
- Component được shade/repackage có còn metadata license/provenance không.

Không chọn một repository có tên gần giống và coi đó là successor chính thức khi chưa có bằng chứng. Tình trạng bảo trì tốt không bù được license không phù hợp hoặc nguồn artifact thiếu tin cậy.

## 15. Ưu tiên theo rủi ro và tác động nghiệp vụ

Một ma trận hỗ trợ quyết định:

| Chiều đánh giá | Thấp | Trung bình | Cao |
|---|---|---|---|
| Phơi nhiễm bảo mật | Không nhận untrusted input | Dữ liệu nội bộ | Input public, secret hoặc quyền cao |
| JDK compatibility | Đã có evidence pass | Chưa có test đáng tin | Không compile/chạy trên JDK đích |
| Độ quan trọng | Tool phụ trợ | Một số workflow | Luồng cốt lõi hoặc nhiều service |
| Tình trạng duy trì | Có người chịu trách nhiệm | Duy trì hạn chế | EOL/abandoned/không có đường vá |
| Phạm vi ảnh hưởng | Một module | Vài service | Dùng chung nhiều hệ thống |
| Khả năng thay thế | API nhỏ, ít dữ liệu | Cần adapter | Thay đổi protocol/schema/phức tạp |

Nhóm có thể phân loại:

- **Blocker:** component khiến ứng dụng không thể chạy với JDK mục tiêu hoặc API cần thiết không tồn tại.
- **High priority:** lỗ hổng có exposure, không có bản vá hoặc không thể phục hồi khi gặp sự cố.
- **Medium priority:** maintenance status xấu nhưng đang hoạt động và có phương án thay thế.
- **Monitor:** ít thay đổi nhưng có owner, kiểm thử tốt và rủi ro hiện tại được chấp nhận.

Mỗi mức phải có lý do, evidence, owner và thời hạn. Không dùng tuổi đời JAR làm tiêu chí duy nhất.

## 16. Những lựa chọn xử lý

| Phương án | Khi phù hợp | Chi phí/rủi ro |
|---|---|---|
| Nâng version cùng dự án | Upstream có bản hỗ trợ và fix | Breaking changes, JDK baseline tăng |
| Chuyển sang successor project | Có dự án kế nhiệm được xác minh | Đổi API, package, license, behavior |
| Thay thư viện khác | Chức năng tương đương, library cũ hết đường duy trì | Contract/data/performance migration |
| Dùng Java SE/JDK documented API | Chức năng hiện đã có API chuẩn đáp ứng | Semantics phải đối chiếu |
| Loại bỏ dependency | Chức năng không còn sử dụng | Kiểm tra dead code/transitive references |
| Adapter + thay dần | Nhiều call sites, cần rollout từng bước | Chi phí chuyển tiếp |
| Fork hoặc vendor nội bộ | Không có alternative, có năng lực maintain | Nhận nghĩa vụ security/release |
| Cô lập service legacy | Phải giữ một giai đoạn chuyển tiếp | Security exposure, vận hành và latency |
| Chấp nhận rủi ro tạm thời | Hạn chế kỹ thuật chưa thể khắc phục ngay | Cần owner, mitigation, deadline |

Không phải lúc nào “thay thư viện” cũng tốt hơn “nâng bản chính thức”. Nếu successor có migration guide và compatibility matrix rõ, nó có thể giúp giảm rủi ro hơn một library khác chỉ có tên tính năng tương tự.

## 17. Cách đánh giá candidate thay thế

Hai thư viện cùng được gọi là “JSON serializer”, “HTTP client” hoặc “connection pool” chưa chắc tương thích.

Danh sách so sánh nên bao gồm:

1. Public API, method signatures, checked exceptions.
2. Thread safety, ordering và concurrency semantics.
3. Null handling, defaults, immutable/mutable behavior.
4. Data format, field naming, enum, number precision, Unicode.
5. Protocol compatibility, timeouts, retries, redirects.
6. TLS verification và security defaults.
7. Runtime JDK baseline, framework và OS/platform support.
8. Memory usage, latency, throughput và resource ownership.
9. Logging, tracing và metrics.
10. Licensing và artifact provenance.
11. Release cadence, maintainer response và security policy.
12. Tính dễ dàng rollout/rollback.

Cần đánh giá bằng use cases mà ứng dụng **thật sự dùng**, không chỉ so sánh danh sách tính năng marketing hoặc số stars.

### 17.1. Dùng Java SE API thay thư viện nhỏ

Nếu thư viện cũ chỉ mã hóa Base64, Java 8+ cung cấp `java.util.Base64`:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public final class PayloadEncoding {
    private PayloadEncoding() {
    }

    public static String encode(String raw) {
        return Base64.getEncoder()
                .encodeToString(raw.getBytes(StandardCharsets.UTF_8));
    }

    public static String decode(String encoded) {
        byte[] bytes = Base64.getDecoder().decode(encoded);
        return new String(bytes, StandardCharsets.UTF_8);
    }
}
~~~

Tuy nhiên, nếu output cũ dùng MIME line breaks, URL-safe alphabet hoặc padding đặc thù, phải chọn API tương ứng và test dữ liệu đã lưu. “Có lớp tên giống” không đồng nghĩa output giống nhau.

## 18. Adapter pattern để thay dependency theo giai đoạn

Khi nhiều module trực tiếp sử dụng thư viện cũ, nên cân nhắc interface nội bộ phản ánh nhu cầu nghiệp vụ.

~~~java
package com.example.orders.spi;

public interface OrderCodec {
    byte[] encode(OrderPayload value);

    OrderPayload decode(byte[] data);
}
~~~

Một adapter cũ có thể được mô tả:

~~~java
public final class LegacyOrderCodec implements OrderCodec {

    private final LegacySerializer serializer;

    public LegacyOrderCodec(LegacySerializer serializer) {
        this.serializer = serializer;
    }

    @Override
    public byte[] encode(OrderPayload value) {
        return serializer.write(value);
    }

    @Override
    public OrderPayload decode(byte[] data) {
        return serializer.read(data, OrderPayload.class);
    }
}
~~~

`OrderPayload` và `LegacySerializer` là các kiểu minh họa do ứng dụng/thư viện giả định cung cấp. Không coi đoạn code là ví dụ chạy độc lập nếu chưa định nghĩa chúng.

Sau đó có thể tạo `ModernOrderCodec`, so sánh output bằng golden tests, đổi implementation qua dependency injection hoặc feature flag có kiểm soát, rồi xóa adapter cũ khi không còn consumer.

**Adapter chỉ cô lập API, không tự bảo đảm semantics.** Một serializer mới có thể đổi field naming, binary format hoặc default values dù interface Java giống hệt. Các khác biệt dữ liệu phải được kiểm thử.

## 19. Thay dependency trong Gradle

Ví dụ khai báo cũ:

~~~groovy
dependencies {
    implementation 'org.example:legacy-http-client:1.0'
}
~~~

Sau khi chọn candidate và sửa source:

~~~groovy
dependencies {
    implementation 'org.example:modern-http-client:2.0'
}
~~~

Tất cả tọa độ ở đây đều là **ví dụ giả định**, không phải package được khuyến nghị cài thật.

### 19.1. Exclude transitive dependency

~~~groovy
dependencies {
    implementation('org.example:protocol-client:3.0') {
        exclude group: 'org.example', module: 'legacy-codec'
    }
}
~~~

Chỉ exclude khi đã xác minh `protocol-client` không còn cần `legacy-codec` hoặc có implementation thay thế phù hợp. Nếu code cấp trên vẫn gọi class bị exclude, runtime có thể lỗi `ClassNotFoundException`, `NoClassDefFoundError` hoặc `NoSuchMethodError`.

### 19.2. Dùng constraints/BOM khi phù hợp

Dependency constraints hoặc platform/BOM có thể đồng bộ versions của cả hệ sinh thái. Tuy nhiên, forcing phiên bản mới không chứng minh ABI tương thích. Cần theo compatibility matrix của framework nếu có.

### 19.3. Kiểm tra graph sau thay đổi

~~~bash
./gradlew :orders-service:dependencies \
  --configuration runtimeClasspath

./gradlew :orders-service:dependencyInsight \
  --dependency legacy-codec \
  --configuration runtimeClasspath
~~~

Sau khi graph phù hợp, tiếp tục xác minh JAR/fat JAR và runtime image. Một component bị shade có thể không còn xuất hiện dưới tọa độ dễ nhận biết.

## 20. Thay dependency trong Maven

Khai báo cũ:

~~~xml
<dependency>
    <groupId>org.example</groupId>
    <artifactId>legacy-codec</artifactId>
    <version>1.4.2</version>
</dependency>
~~~

Khai báo mới:

~~~xml
<dependency>
    <groupId>org.example</groupId>
    <artifactId>modern-codec</artifactId>
    <version>2.0.0</version>
</dependency>
~~~

Các tọa độ chỉ dùng minh họa. Nếu library cũ bị kéo theo bởi một thư viện khác, có thể dùng exclusion:

~~~xml
<dependency>
    <groupId>org.example</groupId>
    <artifactId>protocol-client</artifactId>
    <version>3.0.0</version>
    <exclusions>
        <exclusion>
            <groupId>org.example</groupId>
            <artifactId>legacy-codec</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

Kiểm tra:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.example:legacy-codec
~~~

Maven `dependencyManagement` có thể áp version được chọn nhưng không sửa các call sites hoặc bảo đảm compatibility. Cần chạy test và kiểm tra runtime graph sau thay đổi.

## 21. Breaking changes khi nâng major version

Những thay đổi có thể xuất hiện dù library vẫn được bảo trì:

- Package/class đổi tên.
- Method signature, return type hoặc exceptions thay.
- Constructor được thay bằng builder/factory.
- Default timeout/retry/redirect policy khác.
- JSON/XML field name hoặc date/time format khác.
- Immutable/mutable hoặc thread safety semantics thay đổi.
- Resource close, connection pooling và lifecycle thay.
- TLS algorithms và hostname verification mặc định thay.
- Logging APIs hoặc tracing integration đổi.
- Native library và platform requirements thay.
- Java baseline tăng.
- Dependency bắc cầu, license hoặc artifact coordinates thay.

Với thư viện xử lý dữ liệu bền vững, migration guide phải bao gồm **data compatibility**, không chỉ “sửa compiler warnings”.

### 21.1. Binary compatibility

Một module có thể biên dịch lại với library mới, nhưng module khác giữ bytecode cũ gọi method chữ ký không còn tồn tại. Khi deploy trộn phiên bản, có thể gặp `NoSuchMethodError`, `NoSuchFieldError` hoặc `AbstractMethodError`. Kiểm tra các consumer modules và classpath runtime, không chỉ module vừa sửa.

### 21.2. Data compatibility

Dữ liệu trong database/message queue có thể do thư viện cũ tạo. Nếu thay codec, parser hoặc cryptography provider, cần thử đọc dữ liệu cũ, ghi dữ liệu mới và rollback theo các hướng tương thích mà hệ thống yêu cầu. Không mặc định bản mới đọc được mọi output lịch sử.

## 22. Khi nào nên fork hoặc vendor thư viện?

Fork là giải pháp có thể chấp nhận trong một số trường hợp nhưng nhóm phải trở thành **maintainer thực sự**.

Các điều kiện cần xem:

- License cho phép sửa và phân phối theo mô hình tổ chức.
- Có source, test suite và CI chạy trên JDK mục tiêu.
- Có owner hiểu lĩnh vực và xử lý security advisories.
- Có release/publish pipeline với provenance và artifact coordinates rõ.
- Có khả năng cập nhật transitive dependencies.
- Có tiêu chí dừng fork để chuyển sang upstream/successor.
- Có nguồn lực duy trì trên những JDK về sau.
- Rủi ro kỹ thuật thấp hơn thay đổi kiến trúc vào thời điểm đó.

Fork không chỉ là copy repository rồi đổi version number. Nếu không có owner, quy trình phát hành và security response, dự án nội bộ có thể rơi lại vào trạng thái không được duy trì.

Với thư viện xử lý cryptography, authentication hoặc untrusted parsing phức tạp, team thiếu chuyên môn nên cân nhắc kỹ việc tự fork dài hạn.

## 23. Cô lập dependency legacy như giải pháp chuyển tiếp

Nếu component không thể thay ngay nhưng JDK migration của hệ thống lớn có thời hạn, có thể tạm:

- Đóng chức năng sau adapter/service boundary.
- Giới hạn traffic hoặc nguồn input không đáng tin.
- Áp security controls và monitoring phù hợp.
- Giữ runtime cũ trong một vùng được kiểm soát, nếu còn được hỗ trợ và được phê duyệt.
- Dùng quy trình xử lý lỗi và rollback rõ ràng.
- Đặt thời hạn loại bỏ, owner và tiêu chí hoàn tất.

Đây không phải chứng nhận hệ thống đã an toàn. Giữ một JDK hoặc library đã EOL có thể làm tăng rủi ro, nhất là nếu không còn security fixes. Việc tách một dependency cũ thành microservice cũng không xóa lỗ hổng của code đó; nó chỉ thay đổi ranh giới vận hành.

## 24. Kiểm thử replacement theo nhiều lớp

### 24.1. Unit và contract tests

Bao gồm:

- Null, empty và malformed input.
- Unicode, encoding, escape, large payload.
- Timezone, locale, số lớn và rounding.
- Exceptions, timeout, retry, cancellation.
- Thread safety, ordering và concurrency.
- Close/cleanup semantics và resource leak.
- Edge cases từng có bug trong production.

### 24.2. Golden-file và serialization tests

Nếu library ghi dữ liệu, lưu mẫu định dạng cũ và thử đọc bằng bản mới. Với giai đoạn chạy nhiều version, thử cả chiều client/server cũ đọc dữ liệu mới khi đó là một yêu cầu chính thức.

### 24.3. Integration tests

Kiểm tra kết hợp với database, HTTP/TLS, messaging, cache, framework DI/ORM, application server và deployment topology. Một library pass unit tests vẫn có thể bị framework dùng sai cách hoặc dependency injection cấu hình khác.

### 24.4. API/binary tests

Xác nhận các modules và plugins dùng public API của library; không để JAR bản cũ bị nạp cùng bản mới gây xung đột.

### 24.5. Performance và vận hành

Với library nằm trên hot path, đo throughput, p50/p95/p99, CPU, allocation, heap, GC, connection count, startup time và behavior khi tải cao. Không mặc định replacement luôn nhanh hơn.

### 24.6. Security tests

Xác minh TLS verification, deserialization filters, input size limits, logging sensitive data, dependency advisories và cấu hình default mới. Một thư viện an toàn hơn nhưng bị cấu hình sai vẫn có thể tạo lỗ hổng.

## 25. Ma trận hỗ trợ nhiều JDK

Ví dụ sản phẩm cam kết hỗ trợ Java 17 và Java 21:

| Bước kiểm chứng | Java 17 | Java 21 | Bằng chứng |
|---|---|---|---|
| Build với compiler/toolchain phù hợp | PASS/FAIL | PASS/FAIL | Build log |
| Dependency graph | Reviewed | Reviewed | Lockfile/SBOM |
| Class-file/API baseline | Verified | Verified | javap/compile flags |
| Application startup | PASS/FAIL | PASS/FAIL | Startup log |
| Unit tests | PASS/FAIL | PASS/FAIL | Test reports |
| Integration tests | PASS/FAIL | PASS/FAIL | Test artifacts |
| Reflection/bytecode tool compatibility | PASS/FAIL | PASS/FAIL | Runtime logs |
| Serialization/data compatibility | PASS/FAIL | PASS/FAIL | Golden samples |
| Security triage | Reviewed | Reviewed | Advisory/evidence |
| Performance regression | Compared | Compared | Metrics |
| Deployment artifact | Verified | Verified | Checksums/image digests |

Các ô là placeholder, không phải kết quả đã chạy. Chỉ dùng PASS khi có bằng chứng thực tế. Nếu phát hành một artifact Java 17 và chạy nó trên Java 21, phải test đúng artifact đó trong cả hai runtime nếu đó là phạm vi hỗ trợ.

## 26. Quy trình chuyển đổi dependency theo từng bước

### Bước 1: Cố định baseline

Lưu commit, JDK, build tool, dependency graph, BOM, lockfile, artifact checksum, runtime image, test results và metrics.

### Bước 2: Lập inventory

Thu thập direct/transitive/tooling/runtime-injected components. Ghi owner và hệ thống tiêu thụ.

### Bước 3: Xác minh maintenance status

Kiểm tra tuyên bố chính thức, release notes, support policy, advisories và JDK compatibility docs. Ghi ngày kiểm tra, nguồn và mức độ chắc chắn.

### Bước 4: Phân loại rủi ro

Tách blocker JDK, security exposure, operational risk và maintenance uncertainty. Đánh giá mức độ quan trọng nghiệp vụ và khả năng xử lý.

### Bước 5: Chọn phương án

So sánh upgrade, successor, replacement, remove, adapter, fork hoặc temporary isolation. Giải thích trade-off và người chịu trách nhiệm.

### Bước 6: Thử nghiệm trên JDK mục tiêu

Tạo proof of concept với dependency candidate, chạy compile/runtime/serialization/security tests. Nếu được, tránh nâng JDK, framework và hàng chục libraries trong cùng một bước không thể quy nguyên nhân.

### Bước 7: Sửa build và code

Thay declarations, imports, adapters, configuration và transitive exclusions đúng phạm vi. Kiểm tra graph đã resolve.

### Bước 8: Xác minh artifact và behavior

Chạy unit, integration, contract và performance tests. Kiểm tra JAR/fat JAR/container để bảo đảm library cũ thực sự đã bị loại khỏi deployment khi đó là mục tiêu.

### Bước 9: Rollout có thể rollback

Dùng deployment strategy phù hợp. Quan sát logs, metrics, errors và data compatibility. Nếu format/schema thay đổi, rollback phải được thiết kế trước.

### Bước 10: Hoàn tất vòng đời

Dọn workaround và adapters không còn dùng, cập nhật SBOM/lockfile, runbooks, alerts và owner. Các rủi ro chưa xử lý phải có ngoại lệ chính thức với thời hạn.

## 27. Ví dụ tình huống quyết định

Giả sử một service dùng `org.example:legacy-protocol:1.2` (tên giả định). Kết quả kiểm kê:

- Dependency chạy trong luồng nhận message từ đối tác.
- Nhánh version hiện tại đã bị maintainer thông báo ngừng hỗ trợ.
- Library dùng parser cũ không hỗ trợ JDK mục tiêu.
- Có successor library nhưng khác API và serialization format.
- Một số client cũ vẫn dùng protocol phiên bản trước.

Bảng lựa chọn:

| Lựa chọn | Lợi ích | Rủi ro |
|---|---|---|
| Giữ legacy với JVM flags | Sửa code ít | Không giải quyết hết JDK/security risk |
| Override parser transitive | Dễ thử nghiệm | ABI hoặc behavior mismatch |
| Chuyển successor | Có đường support | Cần adapter và data tests |
| Fork nội bộ | Kiểm soát fix | Trở thành maintainer |
| Thay protocol | Có thể cải thiện kiến trúc | Chi phí client migration cao |

Một phương án có thể là tạo `ProtocolCodec` interface, giữ golden payloads, triển khai adapter successor, so sánh dữ liệu, chạy trên JDK đích, chuyển traffic theo giai đoạn và xóa dependency cũ khi không còn consumer.

Đây là **kịch bản giả định**, không phải kết luận trạng thái của một artifact có thật.

## 28. Dấu hiệu lỗi sau khi thay dependency

| Triệu chứng | Nguyên nhân thường gặp | Hướng điều tra |
|---|---|---|
| `UnsupportedClassVersionError` | Replacement JAR biên dịch cho JVM mới hơn | Major version/JDK target |
| `NoSuchMethodError` | ABI conflict hoặc runtime version khác compile | Dependency graph và packaging |
| `NoClassDefFoundError` | Excluded một JAR vẫn được code gọi | Runtime classpath và stack trace |
| `InaccessibleObjectException` | Thư viện cũ phản chiếu vào JDK internals | Upgrade library, JDK module access |
| Test runner không tìm test | Build/test plugin không hỗ trợ JDK | Plugin compatibility, test discovery |
| Serialization sai dữ liệu | Defaults hoặc schema đổi | Golden datasets và contract tests |
| Performance giảm | Library mới đổi resource/concurrency behavior | Baseline, profiler, metrics |
| Local pass, production fail | Artifact hoặc injected dependency khác | Container, application server, startup |
| Scanner vẫn thấy thư viện cũ | Vẫn có transitive/shaded/nested JAR | Artifact inspection và SBOM |
| License review fail | Candidate không phù hợp chính sách | Legal/provenance assessment |

Không nên dùng `--add-opens` như câu trả lời mặc định cho mọi lỗi khi đổi library. Các lỗi package/module access, API removed và ABI mismatch là những vấn đề khác nhau.

## 29. Những sai lầm thường gặp

### 29.1. Kết luận bỏ duy trì chỉ vì “lâu không commit”

Một thư viện nhỏ ổn định có thể không cần nhiều thay đổi. Cần bằng chứng từ maintainer, support policy và khả năng xử lý sự cố.

### 29.2. Chỉ xem direct dependencies

Rủi ro có thể đến từ transitive libraries, plugins, processors, agents và injected runtime JARs.

### 29.3. Chỉ chọn alternative có nhiều stars

Popularity không bảo đảm Java compatibility, security practice, data format, support, license hoặc hiệu năng.

### 29.4. Exclude thư viện rồi coi là xong

Nếu dependency cha vẫn gọi lớp đã loại bỏ, lỗi có thể chỉ xuất hiện ở runtime hiếm.

### 29.5. Override phiên bản transitive lên mới nhất hàng loạt

BOM/compatibility matrix có lý do tồn tại. Ép version tùy ý có thể tạo xung đột nhị phân.

### 29.6. Chỉ sửa compile errors

Một dependency thay thế có thể compile nhưng đổi retry, timeout, serialization, TLS và semantics.

### 29.7. Fork không có owner

Một fork không có CI, security response và release plan có thể lại bị bỏ duy trì.

### 29.8. Nhầm “không thấy CVE” thành “an toàn”

Vulnerability databases có độ bao phủ và mapping hữu hạn. Cần đánh giá trust boundary và maintainer responsiveness.

### 29.9. Không kiểm tra rollback dữ liệu

Thay serializer/protocol có thể làm binary rollback không đọc được data mới. Cần compatibility window và migration plan.

### 29.10. Không ghi nhận bằng chứng

Một nhận định “dependency hiện đã maintained” mà thiếu version, nguồn và ngày kiểm tra sẽ nhanh chóng mất giá trị khi hệ sinh thái thay đổi.

## 30. Mẫu báo cáo đánh giá một dependency

~~~yaml
dependencyReview:
  coordinate: "org.example:legacy-codec:1.4.2"
  scope: "runtime-transitive"
  introducedBy: "org.example:protocol-client:3.0"
  usedBy:
    - "orders-service"
  owner: "integration-team"
  currentJdk: "11"
  targetJdk: "17"
  maintenance:
    status: "under-review"
    evidence: "official support policy or maintainer announcement"
    checkedAt: "YYYY-MM-DD"
    confidence: "unknown"
  security:
    advisoriesReviewed: false
    runtimeExposure: "unknown"
  compatibility:
    source: "unknown"
    binary: "unknown"
    behavior: "not-tested"
  recommendation:
    action: "evaluate-replacement"
    candidate: "to-be-selected"
    deadline: "to-be-agreed"
  validation:
    graphReviewed: false
    buildPassed: false
    integrationPassed: false
    performanceCompared: false
  residualRisk:
    accepted: false
    mitigation: "pending"
~~~

Mẫu trên chứa tọa độ và trạng thái giả định. Không điền `PASSED` hoặc `maintained` chỉ để hoàn thành biểu mẫu. Mỗi quyết định cần owner, nguồn, thời điểm, phạm vi version và test evidence.

## 31. Checklist trước khi đóng việc migration dependency

- [ ] Đã xác định component ở resolved direct/transitive graph.
- [ ] Đã kiểm tra build plugins, annotation processors, agents và runtime-injected JARs.
- [ ] Đã ghi chính xác artifact, version, source repository và owner.
- [ ] Đã xác minh maintenance/EOL/deprecation từ nguồn đủ tin cậy.
- [ ] Đã rà advisory, license, provenance và mức phơi nhiễm.
- [ ] Đã xem Java baseline, class-file target và API nội bộ.
- [ ] Đã mô tả API, data format và nghiệp vụ thực sự sử dụng.
- [ ] Đã chọn upgrade/replacement/remove/fork/isolation có lý do.
- [ ] Đã kiểm soát graph bằng pin/lock/version policy khi phù hợp.
- [ ] Đã sửa code, build và configuration đúng phạm vi.
- [ ] Đã chứng minh thư viện cũ biến mất khỏi runtime nếu mục tiêu là loại bỏ.
- [ ] Đã chạy unit, contract, integration và security tests cần thiết.
- [ ] Đã kiểm tra serialization/protocol compatibility và performance nếu liên quan.
- [ ] Đã thử deployment/rollback trong môi trường phù hợp.
- [ ] Đã cập nhật SBOM, lockfiles, runbooks và owner.
- [ ] Ngoại lệ còn lại có deadline, mitigation và kế hoạch loại bỏ.

Checklist là công cụ hướng dẫn triển khai, **không phải kết quả QA đã được thực hiện** cho một ứng dụng cụ thể.

## 32. Nguyên tắc kết luận

- **Unmaintained, deprecated, EOL và vulnerable không đồng nghĩa.** Đánh giá đúng trạng thái và version bằng chứng thực tế.
- **Inventory phải bao trùm direct, transitive, build, test và runtime dependencies.** Bỏ sót một agent hoặc processor cũ có thể làm migration thất bại.
- **Dependency graph được resolve quan trọng hơn khai báo đơn lẻ.** Cần lưu BOM, lockfile và artifact thực tế.
- **Một thư viện được duy trì chưa chắc hỗ trợ Java release mà ứng dụng cần.** Xem JDK baseline, class-file version, API, reflection và native dependencies.
- **Không chọn library mới chỉ vì version hoặc popularity cao.** So sánh hợp đồng dữ liệu, API, bảo mật và hành vi.
- **Không exclude/override transitive dependencies một cách máy móc.** Chúng có thể vẫn được framework gọi.
- **Ưu tiên nâng/successor chính thức khi phù hợp**, nhưng vẫn phải kiểm thử breaking changes.
- **Thay thế bằng Java SE API có thể giảm dependency**, miễn là semantics tương đương.
- **Fork là trách nhiệm bảo trì lâu dài**, không phải workaround không chi phí.
- **Adapter, contract tests và phased rollout** giúp thay thư viện có kiểm soát.
- **SBOM, provenance và security scans là bằng chứng hỗ trợ**, không tự thay thế đánh giá chuyên môn và runtime tests.
- **Ngoại lệ phải có owner, thời hạn và kế hoạch dọn dẹp** để không biến rủi ro tạm thời thành nợ kỹ thuật vĩnh viễn.

Trong Java Advance Compatibility Migration, mục tiêu của quản lý dependency không phải “nâng mọi JAR lên mới nhất” mà là bảo đảm **mỗi thành phần còn sử dụng có đường hỗ trợ, hợp đồng kỹ thuật phù hợp và rủi ro được kiểm soát trên JDK mục tiêu**. Bằng cách kiểm kê chính xác, xác minh trạng thái bảo trì, chọn phương án thay thế dựa trên nhu cầu thật, kiểm tra artifact/runtime và thiết kế rollback, hệ thống có thể nâng Java mà không tiếp tục phụ thuộc vào các mắt xích không còn ai có thể khắc phục khi sự cố xuất hiện.
