# Chẩn đoán “Could not resolve dependencies” hoặc Maven plugin không tải được

## 1. Nhận diện đúng lỗi trước khi sửa

Khi Maven báo **`Could not resolve dependencies`**, **`Could not resolve plugin`**, **`PluginResolutionException`**, **`Plugin ... or one of its dependencies could not be resolved`** hoặc **`No plugin found for prefix`**, ứng dụng Java có thể chưa được biên dịch một dòng nào. Maven cần tìm đúng POM/JAR/metadata của thư viện hoặc plugin, nhưng một hoặc nhiều artifacts chưa được resolve thành công.

Hai câu hỏi đầu tiên:

1. **Artifact nào không resolve được?** Ghi chính xác `groupId:artifactId:version:type:classifier` nếu có, và xem đó là project dependency, parent/BOM, Maven plugin hay plugin dependency.
2. **Từ repository nào, với lỗi gốc nào?** Phân biệt `404 / artifact not found`, `401/403`, `407`, `PKIX`, DNS/proxy/timeout, offline mode, negative cache hoặc địa chỉ repository sai.

Điều không nên làm ngay: xóa toàn bộ `~/.m2/repository`, đổi ngẫu nhiên version, thêm repository lạ hoặc tắt TLS validation. Các biện pháp này dễ làm hỏng khả năng tái lập, gây lỗi khác hoặc che lấp nguyên nhân.

Bài thuộc nhóm **Chẩn đoán lỗi** của Maven và sẽ giúp bạn:

- Hiểu Maven Resolver, dependency graph, plugin class realm và parent/BOM resolution.
- Chỉ rõ khác biệt `repositories`, `pluginRepositories`, `distributionManagement` và mirror.
- Phân biệt plugin không tải được với plugin đã tải nhưng goal chạy lỗi.
- Dùng `-e`, `-X`, `-U`, `-o`, `-s`, `-ntp`, `dependency:tree`, `dependency:resolve` và `dependency:resolve-plugins` có mục đích.
- Xử lý private repository, credentials, network proxy, DNS, TLS truststore, cache và CI/offline.
- Chạy một project **Java 17 + JUnit 5** hoàn chỉnh có dependency từ Maven Central, rồi thực hành các lỗi cố ý được gắn nhãn riêng.
- Tạo checklist chẩn đoán và quy tắc sửa an toàn có thể áp dụng trong team.

Các phiên bản trong ví dụ được **ghim để tái hiện**: Java 17, Commons Lang 3.14.0, JUnit Jupiter 5.11.4 và một số Maven plugins. Đây không phải khẳng định chúng là phiên bản mới nhất.

## 2. Maven phải resolve những loại artifact nào?

Maven không chỉ tải JAR của code bạn viết. Trong một lệnh `mvn clean verify`, nó có thể cần các loại artifacts:

| Nhóm | Ví dụ | Được dùng ở đâu |
| --- | --- | --- |
| Parent POM | `org.example:build-parent:1.0.0:pom` | Tạo effective project model |
| Imported BOM | `org.example:platform-bom:1.0.0:pom` | Quản lý versions qua dependencyManagement |
| Project dependency | `org.apache.commons:commons-lang3:3.14.0:jar` | Compile/runtime classpath |
| Test dependency | `org.junit.jupiter:junit-jupiter:5.11.4:jar` | Test compilation/execution |
| Maven plugin | `org.apache.maven.plugins:maven-compiler-plugin:3.13.0:maven-plugin` | Thực hiện compiler goal |
| Plugin dependency | Các JAR plugin cần bên trong plugin realm | Plugin execution classpath |
| Plugin prefix metadata | Mapping prefix `dependency`, `compiler`… | Khi gọi short goal như `dependency:tree` |
| Extensions/transport | Build extensions hoặc provider riêng | Khởi tạo hoặc thao tác với repository transport |
| Classifier-specific artifact | `sources`, `tests`, native classifier | Khi POM/goal yêu cầu cụ thể |

Một project **không khai báo external dependency** vẫn cần Maven plugins để copy resources, compile, test và tạo JAR theo lifecycle. Vì vậy lỗi không tải được Compiler Plugin **khác** với lỗi không tải được Commons Lang.

## 3. Bản đồ luồng resolve

~~~text
./mvnw -B -ntp clean verify
           |
           v
Wrapper tìm Maven distribution (có thể tải lần đầu)
           |
           v
Maven chạy, đọc settings.xml và POM
           |
           v
Resolve parent POM, import BOM, active profiles
           |
           v
Dựng effective model và reactor
           |
           v
Tìm Maven plugins + plugin dependencies
           |
           v
Resolve project dependency graph theo scope/goal
           |
           v
Thực thi resources / compiler / surefire / jar ...
           |
           v
BUILD SUCCESS hoặc một lỗi cụ thể
~~~

Sơ đồ là cách nhìn để học, không phải Maven luôn hoàn thành từng tầng theo trình tự tuyến tính tuyệt đối. Có các resolution được thực hiện sớm khi dựng model, có resolution xảy ra ngay trước plugin goal, và plugin riêng có thể tự yêu cầu thêm artifacts trong lúc chạy.

**Thời điểm lỗi phát sinh** cho biết loại chẩn đoán cần ưu tiên. Nếu Maven chưa tải được parent POM, bạn không thể sửa bằng cách điều chỉnh Java source; compiler chưa được chạy.

## 4. Đọc dòng nguyên nhân đầu tiên, không chỉ BUILD FAILURE

Một log thu gọn dạng project dependency failure:

~~~text
[ERROR] Failed to execute goal on project resolution-lab:
Could not resolve dependencies for project
dev.learning.resolve:resolution-lab:jar:1.0.0:
Could not find artifact ...
~~~

Một log dạng plugin resolution failure:

~~~text
[ERROR] Plugin org.apache.maven.plugins:maven-compiler-plugin:...
or one of its dependencies could not be resolved
~~~

Hai đoạn trên là **mẫu cấu trúc log**, không phải kết quả chạy thực tế. Maven version, repository và artifact được báo trong log thật mới là dữ liệu cần ghi.

Khi nhận incident, lưu tối thiểu:

- Full CLI command.
- Maven và JDK versions.
- Project/module/revision.
- First meaningful error message, kèm `Caused by` nếu có.
- Exact failed GAV/type/classifier và repository ID/URL.
- HTTP status/TLS/DNS/timeout nếu được ghi.
- Offline mode, active profile, settings file và Maven local repository path.
- Lỗi xảy ra trên máy cá nhân hay CI runner.

Không cần đăng public toàn bộ log có token, URL nội bộ nhạy cảm, username hoặc secrets.

## 5. Lệnh chẩn đoán đầu tiên

Từ Maven project root:

~~~bash
mvn -version
java -version
mvn -B -ntp -e clean verify
~~~

- `mvn -version` cho biết Maven/Java đang chạy.
- `-B` là batch mode, thích hợp cho log CI dễ lặp.
- `-ntp` chỉ ẩn progress truyền tải, **không tắt download**.
- `-e` in stack trace để tìm exception gốc.

Nếu lỗi vẫn khó phân loại, chạy **một lượt diagnostic riêng**:

~~~bash
mvn -B -ntp -X clean verify
~~~

`-X` hiển thị debug information về repositories, resolutions, plugin execution và model details, nhưng **có thể chứa đường dẫn nội bộ, URLs hoặc thông tin nhạy cảm**. Không dùng `-X` làm benchmark hiệu năng, cũng không dán nguyên log vào nơi công khai.

Nếu project dùng Maven Wrapper, thay `mvn` bằng `./mvnw` trên Unix-like hoặc `.\mvnw.cmd` trên Windows, để kiểm tra đúng Maven version đã pin.

## 6. Cấu trúc một Maven repository

Artifact coordinate:

~~~text
org.apache.commons:commons-lang3:3.14.0
~~~

tương ứng đường dẫn repository layout:

~~~text
org/apache/commons/commons-lang3/3.14.0/
├── commons-lang3-3.14.0.pom
└── commons-lang3-3.14.0.jar
~~~

Maven đọc POM để hiểu metadata/transitive dependencies, rồi tải artifact files theo nhu cầu. Một vài files metadata/checksum khác có thể xuất hiện.

Repository Maven Central mặc định thường có root:

~~~text
https://repo.maven.apache.org/maven2/
~~~

Một Maven URL trong log thường được hình thành bằng cách kết hợp repository base URL và đường dẫn GAV. Hãy kiểm tra **artifact có tồn tại ở đúng repository đó** thay vì đoán chỉ theo tên thư viện.

### Không phải mọi artifact ở Maven Central

Artifact private, internal SNAPSHOT, release trong repository riêng hoặc vendor SDK có thể **không bao giờ** được publish lên Central. Nếu POM yêu cầu private artifact nhưng effective repository chỉ có Central, `Could not find artifact` là kết quả đúng của cấu hình sai, không phải lỗi máy Maven.

## 7. Phân biệt “not found” với “transfer failed”

| Triệu chứng | Ý nghĩa cần kiểm tra | Không nên kết luận vội |
| --- | --- | --- |
| `Could not find artifact` / HTTP 404 | Artifact/metadata không tồn tại ở repository đã hỏi, hoặc endpoint đang che quyền | Không chắc project artifact hoàn toàn không tồn tại |
| HTTP 401 | Credentials thiếu, sai hoặc hết hạn | Không phải Java compiler bug |
| HTTP 403 | Có xác thực nhưng bị từ chối, policy hoặc endpoint restrictions | Không chắc URL sai |
| HTTP 407 | Proxy yêu cầu authentication | Không phải Maven Central đang thiếu artifact |
| HTTP 500/502/503/504 | Repository manager/proxy/server upstream bất ổn | Không vội thay GAV |
| Connect timeout | DNS, route, proxy, firewall, service reachability | Không phải dependency version lỗi ngay lập tức |
| Read timeout | Kết nối có nhưng response chậm/gián đoạn | Không nên tăng timeout vô hạn trước khi đo |
| `PKIX path building failed` | Java TLS trust chain không được xác minh | Không được tắt TLS validation |
| `Unsupported protocol / blocked HTTP` | URL hoặc policy transport không cho HTTP | Không bật unsafe HTTP để né chính sách |
| `cached in local repository` | Resolver lưu lần thất bại trước theo update policy | Không nhất thiết cần xóa toàn cache |

Các repository managers có thể trả status khác cho cùng nguyên nhân; ví dụ private artifact bị che bằng 404 thay vì 403. Phải đọc server/repository policy và xác minh quyền thực tế.

## 8. Lỗi project dependency resolution

POM ví dụ:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.14.0</version>
</dependency>
~~~

Nếu Maven báo không resolve được dependency này, kiểm tra:

1. Có đánh đúng `groupId`/`artifactId`/`version` không?
2. Packaging/classifier có bị yêu cầu sai không? Ví dụ yêu cầu `tests` JAR khi upstream không publish?
3. Đã có hiệu lực một `dependencyManagement`/BOM version override chưa?
4. Dependency được đưa vào từ một transitive path nào?
5. Repository/mirror thực tế có artifact đó không?
6. Máy/CI có quyền đọc repository không?
7. Local cache có artifact hỏng hoặc negative cache không?
8. `-o` có bị bật và artifact chưa cached không?
9. Repository có chính sách snapshots/releases phù hợp không?
10. CI có sử dụng settings/active profile khác laptop không?

**Không đổi dependency version hàng loạt** trước khi biết Maven đang hỏi URL nào và lỗi gốc là gì.

## 9. Lỗi plugin resolution là nhóm khác

POM plugin:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
</plugin>
~~~

Khi Maven cần compile, nó phải resolve plugin JAR và những dependency của plugin. Nếu lỗi:

~~~text
Plugin ... maven-compiler-plugin ... or one of its dependencies
could not be resolved
~~~

đừng sửa Commons Lang hoặc code `App.java` trước; kiểm tra:

- Plugin coordinates/version đúng không?
- Plugin repo hoặc mirror có đáp ứng không?
- Plugin dependencies có bị chặn bởi repository policy không?
- Credentials/proxy/TLS có áp dụng với plugin repositories không?
- Maven local repository có file/plugin metadata hỏng không?
- Plugin có yêu cầu Maven/JDK version khác không, **sau khi resolve thành công**?

Một plugin có thể đã tải được nhưng goal **thực thi lỗi** do compiler/source/JDK configuration. Khi đó message thường có dạng `Failed to execute goal ...:compile` kèm `Compilation failure`. Không phải “plugin không tải được”.

## 10. Plugin prefix resolution: một lỗi riêng

Lệnh rút gọn:

~~~bash
mvn dependency:tree
~~~

dùng prefix `dependency`. Maven phải map prefix sang plugin tương ứng bằng cơ chế plugin prefix resolution (plugins khai báo trong POM, plugin groups và repository metadata).

Khi log báo:

~~~text
No plugin found for prefix 'dependency'
~~~

không nhất thiết Maven Dependency Plugin artifact không tồn tại. Có thể prefix metadata/repository settings/pluginGroups hoặc offline cache gây lỗi.

Để giảm mơ hồ về prefix/version, thử **fully-qualified goal** có version đã duyệt:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
~~~

Cách này bỏ bước chọn prefix/version tự động, **không bỏ** tải plugin và its dependencies nếu cache trống.

Nếu lệnh fully-qualified hoạt động nhưng short prefix không hoạt động, ưu tiên kiểm tra prefix resolution/effective plugin settings. Nếu cả hai fail vì transfer, tập trung vào artifact repository/network/auth.

## 11. repositories, pluginRepositories và distributionManagement

Một trong các lỗi phổ biến nhất là cấu hình nhầm ba mục POM:

| Thành phần POM | Ý nghĩa |
| --- | --- |
| `<repositories>` | Remote repositories phục vụ download/resolve **project dependencies** |
| `<pluginRepositories>` | Remote repositories phục vụ download/resolve **Maven plugins** và plugin dependencies |
| `<distributionManagement>` | Điểm **publish** artifact của project khi chạy Maven deploy |

Ví dụ một private plugin repository (URL minh họa, không phải endpoint có thể chạy):

~~~xml
<pluginRepositories>
    <pluginRepository>
        <id>company-plugin-repo</id>
        <url>https://repo.example.org/repository/maven-plugins/</url>
        <releases>
            <enabled>true</enabled>
        </releases>
    </pluginRepository>
</pluginRepositories>
~~~

Nếu thêm repository chỉ dưới `<repositories>` nhưng custom plugin lại nằm **chỉ** ở private plugin repository, Maven có thể không tìm thấy plugin. Cần đúng `<pluginRepositories>` hoặc trusted mirror/repository manager có proxy đúng artifact source.

**Ghi chú:** parent POM, imported BOM và dependency POMs có thể ảnh hưởng effective repository configuration theo Maven rules; hãy xem cấu hình hiệu lực, không đọc mỗi local `pom.xml`.

## 12. Settings và mirrors có thể đổi toàn bộ repository thực

Một dự án chỉ khai Maven Central nhưng CI có:

~~~xml
<mirrors>
    <mirror>
        <id>corporate-mirror</id>
        <mirrorOf>*</mirrorOf>
        <url>https://repo.example.org/repository/maven-public/</url>
    </mirror>
</mirrors>
~~~

Đây là **fragment minh họa trong Maven settings**, không phải URL thật. Với `mirrorOf=*`, Maven sẽ định tuyến các yêu cầu repository tới mirror được chọn theo matching rules.

Hệ quả:

- Khi mirror khỏe và proxy đủ repositories, downloads có thể ổn định/nhanh hơn.
- Nếu mirror thiếu private artifacts hoặc bị downtime, cả project dependencies **và plugins** có thể bị ảnh hưởng.
- Chỉ sửa POM thêm Central có thể **không giải quyết** nếu settings vẫn mirror mọi request về repository lỗi.
- Một mirror không có cơ chế tự tổng hợp “tất cả repo khớp”; Maven chọn một mirror phù hợp, tổ chức cần một repository manager tổng hợp/proxy nếu muốn hợp nhất nguồn.
- `mirrorOf=external:*` không trỏ localhost/file repositories như `*`; khác biệt này quan trọng với integration tests.

Không sửa global/user settings của máy chung mà chưa xác định người sở hữu. Trong lab, chỉ xem file effective settings đã được phép sử dụng và tạo settings riêng nếu bạn có quyền.

## 13. Repository IDs và authentication binding

Nếu mirror là repository thực sự được Maven dùng, credentials thường được chọn theo **effective repository ID**. Ví dụ minh họa trong user settings:

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <mirrors>
        <mirror>
            <id>corporate-mirror</id>
            <mirrorOf>*</mirrorOf>
            <url>https://repo.example.org/repository/maven-public/</url>
        </mirror>
    </mirrors>

    <servers>
        <server>
            <id>corporate-mirror</id>
            <username>ci-reader</username>
            <password>${env.MAVEN_REPO_TOKEN}</password>
        </server>
    </servers>
</settings>
~~~

**Không copy ví dụ này như cấu hình production hoàn chỉnh.** URL là giả lập, biến môi trường cần được CI secret manager cung cấp, và cấu hình thật phải theo chính sách repository của tổ chức.

Điểm kiểm tra:

- `<server><id>` phải khớp ID của repository/mirror thực tế cần xác thực.
- Nếu POM dùng `private-repo` nhưng mirror thành `corporate-mirror`, credential map cần được kiểm tra theo endpoint/ID thực tế.
- Token có thể hết hạn, thiếu read scope hoặc chỉ có quyền publish chứ không có quyền download.
- CI và máy cá nhân có thể đọc settings khác nhau.
- Không lưu token plaintext trong POM, public logs hoặc repository.

Đừng chỉ đổi `<id>` để “thử cho chạy”: tránh gửi credentials của private repo tới host không tin cậy. Luôn xác nhận URL, certificate và chính sách kết nối trước.

## 14. Cấu hình proxy trong Maven settings

Ở môi trường doanh nghiệp, mạng có thể yêu cầu HTTP/HTTPS proxy:

~~~xml
<proxies>
    <proxy>
        <id>corp-proxy</id>
        <active>true</active>
        <protocol>https</protocol>
        <host>proxy.example.org</host>
        <port>8443</port>
        <nonProxyHosts>localhost|127.0.0.1|*.example.org</nonProxyHosts>
    </proxy>
</proxies>
~~~

Đây là **fragment minh họa**, host/port không có thật. Cần xác định proxy hỗ trợ loại protocol nào và authentication có cần thiết hay không.

Nếu lỗi:

~~~text
UnknownHostException
Connection timed out
Proxy Authentication Required (407)
~~~

hãy kiểm tra DNS, proxy, VPN, firewall, allowlist và host cụ thể. Nếu `curl` của OS thành công nhưng Maven fail, Java/Maven có thể dùng proxy/truststore khác. `curl` **không chứng minh** Java TLS/HTTP client sẽ có cùng kết quả.

### Không tắt proxy/TLS kiểm tra để “thử vận may”

Không sử dụng các cờ SSL insecure, bỏ kiểm tra certificate hoặc thêm arbitrary public mirror làm giải pháp production. Nếu corporate TLS inspection thực sự cần, Java truststore phải tin đúng CA theo chính sách bảo mật của tổ chức.

## 15. Lỗi SSL/TLS: PKIX path building failed

Ví dụ lỗi thường thấy:

~~~text
PKIX path building failed:
sun.security.provider.certpath.SunCertPathBuilderException:
unable to find valid certification path to requested target
~~~

Điều này thường nghĩa là JVM không xây được trust chain hợp lệ tới certificate được server/proxy cung cấp.

Quy trình:

1. Xác định URL/hostname trong log Maven.
2. Kiểm tra thời gian hệ thống, cert expiry và hostname.
3. Xác định máy đang dùng JDK nào bằng `mvn -version` và `java -version`.
4. Xem có corporate TLS interception proxy hay không.
5. Kiểm tra chain do endpoint cung cấp với người vận hành repository/network.
6. Nếu chính sách cho phép, cài **đúng CA đáng tin** vào truststore được chỉ định cho JDK/Maven process.
7. Chạy lại bằng cùng JDK/settings.
8. Không dùng `-Dmaven.wagon.http.ssl.insecure=true` hay bỏ validation để che vấn đề.

**Maven có thể dùng JDK khác với Java trong terminal** nếu `JAVA_HOME`/wrapper/IDE configuration khác. Vì vậy `curl` hoặc browser truy cập được repository không chứng minh Maven JVM tin certificate đó.

## 16. 401, 403 và 407: tập trung vào quyền

| Status | Kiểm tra |
| --- | --- |
| 401 Unauthorized | Token/username/password thiếu, sai, hết hạn; server ID không match |
| 403 Forbidden | Token có tồn tại nhưng không có read permission, policy repo/role/block; đôi khi IP/network restriction |
| 407 Proxy Authentication Required | Credentials cho proxy, không phải artifact repository |
| 404 Not Found | GAV/repository path không tồn tại; ở private repo có thể che quyền hoặc proxy không route đúng |

**Điều quan trọng:** lỗi `401` tải dependency không giống lỗi `401` publish artifact tại `mvn deploy`. Download dùng `repositories/pluginRepositories`; publication dùng `distributionManagement` và quyền write riêng. Luôn đọc URL và goal bị lỗi.

Không paste full `settings.xml` chứa token vào issue hoặc chat. Nếu cần debug, chỉ cung cấp repository IDs/hostname đã được phép chia sẻ và lỗi đã redacted.

## 17. 404: kiểm tra chính xác GAV, classifier và repository

Ví dụ lỗi phổ biến:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang33</artifactId>
    <version>3.14.0</version>
</dependency>
~~~

Đây là **POM fragment cố ý sai**, không thuộc lab runnable. Tên artifact đúng phải là `commons-lang3`; Maven có thể tìm 404 vì `commons-lang33` không phải coordinates phát hành trong Maven Central.

Những chỗ dễ nhầm:

- `groupId` và `artifactId` không trùng tên Java package.
- Artifact đã chuyển groupId giữa các major versions.
- Version POM bị property interpolation sai hoặc chưa được khai báo.
- Classifier `tests`, `sources`, OS/architecture-specific classifier không được publish.
- Packaging/type `pom` vs `jar` không khớp.
- SNAPSHOT nằm ở snapshot repository, không phải release-only repository.
- Artifact private không nằm trong Central.
- Parent/BOM version không tồn tại theo coordinates được khai báo.

Mỗi lỗi cần sửa **đúng tọa độ hoặc repository**, không xóa cache hay tắt TLS một cách ngẫu nhiên.

## 18. Version range, SNAPSHOT và metadata

Maven có thể dùng phiên bản cụ thể:

~~~xml
<version>3.14.0</version>
~~~

hoặc version range:

~~~xml
<version>[3.0,4.0)</version>
~~~

Range phụ thuộc metadata phiên bản trong repository. SNAPSHOT có thể được publish nhiều lần với cùng logical version, thông qua metadata để chọn timestamped artifacts.

Khi metadata stale/missing:

- Maven có thể resolve version khác kỳ vọng hoặc không có version phù hợp.
- Repository manager có thể chưa proxy metadata mới.
- Local cache có metadata/failed resolution records.
- SNAPSHOT policy có thể tắt hoặc giới hạn update.
- Artifact đã bị xóa/GC khỏi repository nhưng POM vẫn trỏ tới.

**Đừng dùng ranges/SNAPSHOT như “version lock”** cho release reproducibility. Ghim release versions và đảm bảo repository immutability; với snapshots phải hiểu retention/update policy.

## 19. Negative cache và đuôi .lastUpdated

Maven Resolver có cơ chế cache những lần không tìm thấy hoặc transfer artifact lỗi, theo update policy. Bạn có thể gặp thông báo:

~~~text
This failure was cached in the local repository
and resolution is not reattempted until the update interval
has elapsed or updates are forced
~~~

Đây là một dạng thông báo có thật của Maven Resolver; text chi tiết thay đổi theo version và artifact.

Các file liên quan trong local repository có thể gồm:

~~~text
commons-lang3-3.14.0.jar.lastUpdated
commons-lang3-3.14.0.pom.lastUpdated
_remote.repositories
maven-metadata-<repository-id>.xml
~~~

Những filename này minh họa các loại metadata, không phải mọi lần tải đều sinh đúng bộ file ấy. `_remote.repositories` giúp Maven biết provenance của artifact cached; không nên xóa tùy tiện.

**Ưu tiên:** sửa lỗi gốc (đúng GAV, repo URL, credentials, TLS, network) trước. Sau đó mới xem `-U` hoặc kiểm tra cache trên đúng artifact. Nếu credentials vẫn sai, retry chỉ tạo ra một lần 401/403 nữa.

## 20. -U có ý nghĩa gì và không làm được gì?

Lệnh:

~~~bash
mvn -B -ntp -U clean verify
~~~

Theo Maven CLI, `-U` buộc kiểm tra missing releases và updated snapshots ở remote repositories. Nó hữu ích khi:

- Một artifact vừa được publish sau lần not-found trước.
- Repository/metadata đã được sửa và local negative cache chặn attempt mới.
- SNAPSHOT update policy khiến bạn cần kiểm tra bản remote mới theo chủ đích.

Nhưng `-U` **không**:

- Tạo artifact không có trên remote.
- Sửa GAV hoặc classifier sai.
- Sinh ra credentials không được cấp.
- Chữa lỗi certificate PKIX.
- Chữa firewall/DNS/timeout.
- Bỏ qua policy repository manager.
- Xác nhận bản Maven đang dùng sẽ luôn tìm thấy artifact nếu mirror bị cấu hình sai.

Không nên thêm `-U` vĩnh viễn vào mọi CI build chỉ vì một lần download fail; tăng remote metadata checks và có thể gây drift ở SNAPSHOT builds.

## 21. -o: Maven offline mode là một phép thử khác

Lệnh:

~~~bash
mvn -B -ntp -o clean verify
~~~

`-o` yêu cầu Maven không sử dụng remote repository để lấy artifacts còn thiếu.

Kết quả có thể giúp chẩn đoán:

- **Offline PASS:** các artifacts Maven cần cho workflow đó đã đủ trong local repo; vẫn có thể có plugin/test code tự dùng network ngoài Maven Resolver.
- **Offline FAIL:** thiếu artifact/plugin/metadata cần thiết trong cache hoặc repository provenance/policy không khớp.
- **Online FAIL nhưng Offline PASS:** có thể do remote update/metadata/network hoặc profiles khác, nhưng phải so đúng commands.
- **Offline FAIL ngay ở Clean Plugin:** Maven cần plugin mà cache chưa có; không suy ra ứng dụng source lỗi.

Không dùng `-o` làm “cách sửa download lỗi” khi local repository chưa có đầy đủ artifacts. Đối với CI, nên quản lý trusted caches và repository proxy thay vì dựa vào cache laptop tình cờ.

## 22. Kiểm tra cache an toàn bằng local repository riêng

Để phân biệt lỗi cache hiện tại với lỗi remote, dùng một repository thí nghiệm cô lập, **không xóa repo người dùng**.

Linux/macOS:

~~~bash
mkdir -p /tmp/maven-resolve-lab-repo
mvn -B -ntp -Dmaven.repo.local=/tmp/maven-resolve-lab-repo clean verify
~~~

Windows PowerShell:

~~~powershell
$repo = Join-Path $env:TEMP "maven-resolve-lab-repo"
New-Item -ItemType Directory -Force -Path $repo | Out-Null
mvn -B -ntp "-Dmaven.repo.local=$repo" clean verify
~~~

Nếu lần chạy với repo mới thành công nhưng lần chạy với repo cũ thất bại, có bằng chứng để kiểm tra stale/corrupt local cache hoặc repository provenance/update policy. **Nhưng** hai lần chạy cần cùng settings/profiles/network/Maven/JDK; isolated cache có thể kích hoạt downloads mới nên chậm hơn hoặc fail do mạng.

Nếu cả hai fail cùng một 403/PKIX/404, giải quyết remote/configuration trước; không tiếp tục xóa local files.

## 23. Có nên xóa cache artifact bị lỗi?

Có thể cần làm sạch **đúng folder artifact version** sau khi xác định cache hỏng, nhưng không nên dùng “xóa toàn `~/.m2`” làm bước đầu.

Quy trình được kiểm soát:

1. Xác định exact GAV và local Maven repository path đang dùng.
2. Sao lưu/ghi lại error và metadata liên quan nếu cần điều tra.
3. Xác nhận remote artifact/repository/trust đã ổn.
4. Ưu tiên thử isolated local repo hoặc `-U` trước.
5. Chỉ khi đã có lý do, dùng cơ chế targeted purge hoặc xóa **đúng artifact/version directory** trong local repo do bạn kiểm soát.
6. Chạy lại một lần, đối chiếu resolved artifact digest và logs.
7. Không xóa caches dùng chung bởi CI workers khác khi chưa có quyền.

Maven Dependency Plugin có goal `purge-local-repository` nhưng goal này **cũng cần tải plugin** nếu chưa cached; đọc tài liệu đúng version và kiểm soát include scope trước khi áp dụng. Bài không cung cấp lệnh xóa đệ quy tự động vì dễ tác động nhầm.

**Nguyên nhân gốc vẫn quan trọng:** xóa cache không giải quyết artifact sai coordinates hoặc repository 403.

## 24. Tìm effective repository cấu hình từ settings/POM

Một developer nói “POM chỉ khai Maven Central”, nhưng máy có thể dùng mirror trong user/global settings hoặc active profiles.

Để xem cấu hình hiệu lực bằng Help Plugin đã ghim version:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.1:effective-settings
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.1:effective-pom
~~~

Các goal trên có thể **cũng fail khi Maven không tải được Help Plugin hoặc parent POM**. Đó là giới hạn của chẩn đoán dùng Maven plugins khi chính resolution đang lỗi.

Kiểm tra:

- `~/.m2/settings.xml` và Maven installation global settings, nếu có quyền.
- Option `-s path/to/settings.xml` của lệnh Maven.
- `<mirrors>`, `<servers>`, `<proxies>` và active settings profiles.
- `<repositories>`/`<pluginRepositories>` trong effective POM.
- Parent POM/repositories được kế thừa.
- Maven Wrapper distribution config nếu lỗi xuất hiện **trước** khi Maven chạy.

**Bảo mật:** Effective Settings/POM và debug logs có thể chứa đường dẫn, hostname hoặc metadata nội bộ; không đưa vào public issue nguyên xi.

## 25. -s để dùng settings riêng một cách kiểm soát

Bạn có thể tạo settings file thử nghiệm **trong thư mục được phép**, rồi chạy:

~~~bash
mvn -B -ntp -s path/to/approved-settings.xml clean verify
~~~

Đây là cú pháp minh họa: thay `path/to/approved-settings.xml` bằng file thật do bạn quản lý.

Cách này giúp xác định có phải settings/mirror hiện tại gây lỗi hay không. Nhưng:

- Settings mới có thể làm private dependencies không còn accessible.
- Cẩn thận credentials, không copy secrets sang repo công khai.
- Giữ Maven/JDK/POM và command giống nhau để so kết quả.
- Nếu CI vốn bắt buộc dùng corporate mirror, không bypass mirror để publish/release production.

Vấn đề phải được giải quyết trong cấu hình được tổ chức chấp thuận, không chỉ bằng workaround trên laptop.

## 26. Parent POM lỗi: không phải dependency JAR bình thường

Một log kiểu:

~~~text
Non-resolvable parent POM for dev.example:my-app:1.0.0
~~~

cho biết Maven chưa dựng được project model hoàn chỉnh. Kiểm tra phần `<parent>`:

~~~xml
<parent>
    <groupId>dev.example</groupId>
    <artifactId>company-build-parent</artifactId>
    <version>1.0.0</version>
    <relativePath>../pom.xml</relativePath>
</parent>
~~~

Đoạn này **chỉ minh họa**, `dev.example` không phải repository artifact thật.

Các điểm quan trọng:

- Relative path có chỉ tới parent POM đúng với GAV/version đó không?
- Parent có thật trong source tree/reactor?
- Nếu parent nằm ở remote repository, Maven settings có đọc đúng repo không?
- Nếu dùng `<relativePath/>`, Maven không dựa vào local relative parent path theo cùng cách default; hãy biết chủ đích cấu hình.
- CI checkout có đầy đủ parent files/modules không?
- GAV parent có bị đổi mà child POM chưa update không?

Đừng thêm `-DskipTests` để xử lý lỗi parent; tests chưa chạy.

## 27. Imported BOM lỗi: xác định scope import POM

Một project dùng BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>dev.example</groupId>
            <artifactId>company-bom</artifactId>
            <version>2.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đây là ví dụ tọa độ giả lập, **không thuộc lab runnable**.

Nếu Maven báo `Non-resolvable import POM`:

- Kiểm tra BOM GAV/version.
- Xác nhận repository chứa file `company-bom-2.0.0.pom`.
- Kiểm tra BOM nằm trong release hay snapshot repo.
- Kiểm tra private repo/mirror/credentials.
- Kiểm tra parent/dependencyManagement properties có resolve đúng không.

**Không dùng `mvn dependency:tree` làm bước đầu nếu Maven chưa tạo được effective POM.** Sửa parent/BOM model resolution trước.

## 28. Multi-module Maven và dependency chưa install

Một multi-module repository:

~~~text
platform/
├── pom.xml             packaging pom
├── common/pom.xml      module library
└── service/pom.xml     module ứng dụng phụ thuộc common
~~~

Nếu chạy riêng từ thư mục `service` và `common` chưa nằm trong local/remote Maven repository, bạn có thể gặp:

~~~text
Could not find artifact dev.example:common:jar:1.0.0
~~~

Maven có thể build cả module phụ thuộc trong cùng reactor khi chạy đúng từ aggregator root:

~~~bash
mvn -B -ntp -pl :service -am clean verify
~~~

- `-pl :service` chọn module service.
- `-am` thêm các reactor projects mà service phụ thuộc để build cùng, nếu chúng là modules trong reactor.
- `clean verify` build theo reactor order phù hợp.

Nếu module không thuộc reactor hoặc coordinates trong service khác common, `-am` không tự tìm một module không có. Hãy so đúng GAV/version và aggregator modules.

**Không dùng `mvn install` mọi nơi như một workaround vĩnh viễn** khi CI cần build reactor đồng nhất: local install có thể khiến consumer dùng stale binary thay vì source cùng commit.

## 29. Plugin prefix group và pluginRepositories

Một custom plugin:

~~~text
dev.example.tools:quality-maven-plugin:1.0.0
~~~

được gọi bằng:

~~~bash
mvn quality:check
~~~

có thể cần plugin group/prefix metadata phù hợp; `pluginGroups` trong Maven settings giúp prefix lookup cho nhóm plugin ngoài hai default groups.

Nếu plugin đã khai trong `build/plugins` cùng version/execution, Maven có thể xác định goal rõ hơn. Nhưng nếu bạn gọi short prefix với metadata thiếu, có thể thấy:

~~~text
No plugin found for prefix 'quality'
~~~

Trong chẩn đoán, thử fully-qualified plugin goal **được xác minh từ upstream**:

~~~text
mvn dev.example.tools:quality-maven-plugin:1.0.0:check
~~~

Đây là **chuỗi cú pháp minh họa**, không phải lệnh chạy được: `dev.example.tools` và goal `check` là giả lập. Nó giúp phân biệt prefix lookup với việc artifact/plugin realm thực sự không resolve được.

Đừng thêm plugin group lạ vào settings để “thử”, đặc biệt nếu yêu cầu tải code/plugin từ repository không được tin cậy.

## 30. Plugin dependencies có thể lỗi dù plugin JAR đã cached

Một plugin artifact có thể đã có:

~~~text
maven-compiler-plugin-3.13.0.jar
~~~

nhưng một artifact dependency của plugin chưa tải được. Maven vẫn báo:

~~~text
Plugin ... or one of its dependencies could not be resolved
~~~

Nguyên nhân có thể ở dependency **của plugin**, không phải phiên bản plugin chính. Trong debug logs, tìm artifact coordinate cuối cùng không tải được và repository tương ứng.

Các trường hợp:

- Plugin POM được resolve nhưng transitive plugin dependency bị 404.
- Private plugin phụ thuộc internal library chưa publish.
- Plugin dependency yêu cầu version mà repository manager đã chặn.
- Mirror áp dụng sai cho pluginDependencies.
- Local cache có file artifact hỏng hoặc metadata không nhất quán.

Không loại một project dependency không liên quan chỉ để “sửa plugin”. Có thể cần thay plugin version đã được duyệt, sửa plugin POM/repository hoặc đưa đúng artifact vào repository quản trị.

## 31. Lệnh riêng để phân giải project dependencies

Trong project có effective POM hợp lệ và Dependency Plugin sẵn sàng:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:resolve
~~~

Goal này thử resolve project dependencies và báo resolved versions. Nếu nó FAIL với chính GAV, đó là dấu hiệu rõ hơn về dependency resolution.

Để xem graph:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
~~~

**Lưu ý:** hai lệnh này cũng phải resolve Maven Dependency Plugin và its dependencies trước. Nếu Maven đang bị lỗi plugin repositories toàn cục, chúng có thể fail **trước** khi kiểm tra project dependencies. Không diễn giải một lần `dependency:resolve` thất bại như bằng chứng chắc chắn project GAV sai mà chưa đọc artifact gây lỗi.

## 32. Lệnh riêng để phân giải plugin artifacts

Dùng goal:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:resolve-plugins
~~~

Goal cố gắng resolve project plugins/report plugins và những dependencies của chúng, giúp thấy lỗi ở plugin side. Một goal gần liên quan là:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:go-offline
~~~

`go-offline` cố giải quyết project dependencies, plugins, report plugins và dependencies tương ứng để chuẩn bị offline build.

**Giới hạn cả hai:** không bảo đảm tất cả artifact được một custom goal/plugin tải động đã có trước; và bản thân Dependency Plugin phải tải được. Nếu Maven không dựng được parent/BOM, các goal cũng không giúp vượt qua lỗi model.

## 33. Verify chính xác artifact URL khi được phép

Ví dụ public POM của Commons Lang 3.14.0:

~~~text
https://repo.maven.apache.org/maven2/org/apache/commons/commons-lang3/3.14.0/commons-lang3-3.14.0.pom
~~~

Và public POM của Maven Compiler Plugin 3.13.0:

~~~text
https://repo.maven.apache.org/maven2/org/apache/maven/plugins/maven-compiler-plugin/3.13.0/maven-compiler-plugin-3.13.0.pom
~~~

Nếu mạng cho phép, có thể kiểm tra reachability tới đúng public endpoint:

~~~bash
curl --fail --head --location "https://repo.maven.apache.org/maven2/org/apache/commons/commons-lang3/3.14.0/commons-lang3-3.14.0.pom"
~~~

**Kết quả của HTTP HEAD có giới hạn:** proxy/server có thể xử lý HEAD khác GET. Một HTTP 200 cho public URL chỉ chứng minh endpoint đó trả lời, **không chứng minh Maven đang dùng endpoint này** (có thể bị mirror sang private repo), hoặc JVM TLS truststore giống system curl.

Không gửi credentials từ Maven settings lên public endpoint. Với private URL, phải theo công cụ mạng và policy được tổ chức cấp phép.

## 34. Windows: kiểm tra mạng và Maven mà không cần xóa cache

Windows PowerShell:

~~~powershell
mvn -version
java -version

Test-NetConnection repo.maven.apache.org -Port 443

mvn -B -ntp -e clean verify
~~~

- `Test-NetConnection` kiểm tra DNS/TCP tới host/port, không tự xác nhận HTTP auth/TLS trust của Java.
- `-e` giúp hiển thị nguyên nhân.
- Nếu dự án dùng Wrapper, thay `mvn` bằng `.\mvnw.cmd`.

Với repo riêng:

~~~powershell
$repo = Join-Path $env:TEMP "maven-resolution-check"
New-Item -ItemType Directory -Force -Path $repo | Out-Null

mvn -B -ntp "-Dmaven.repo.local=$repo" clean verify
~~~

Chỉ sử dụng test repo riêng để điều tra, không xóa local repository chung của người dùng.

## 35. Linux/macOS: kiểm tra tên miền, TCP và Maven logs

Unix-like shell:

~~~bash
mvn -version
java -version
curl --fail --head --location "https://repo.maven.apache.org/maven2/org/apache/commons/commons-lang3/3.14.0/commons-lang3-3.14.0.pom"
mvn -B -ntp -e clean verify
~~~

Để dùng repo riêng:

~~~bash
mkdir -p /tmp/maven-resolution-check
mvn -B -ntp -Dmaven.repo.local=/tmp/maven-resolution-check clean verify
~~~

**Đọc đúng terminal output**: nếu curl truy cập Central được nhưng Maven vẫn lỗi ở `corporate-mirror`, hãy xem effective mirror và credentials. Đừng đổi JDK/Compiler Plugin nếu gốc lỗi là mirror không có quyền đọc.

## 36. Lab Java 17: project chạy được khi resolution đúng

Dựng cấu trúc:

~~~text
resolution-lab/
├── pom.xml
└── src/
    ├── main/java/dev/learning/resolve/App.java
    └── test/java/dev/learning/resolve/AppTest.java
~~~

Lab có dependency **thực sự tồn tại** trên Maven Central và các plugin version được pin. Mục đích là có baseline hợp lệ trước khi đọc các kịch bản lỗi cố ý.

### 36.1. pom.xml đầy đủ

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.learning.resolve</groupId>
    <artifactId>resolution-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>

        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.3.2</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-dependency-plugin</artifactId>
                <version>3.8.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Giải thích:**

- `<maven.compiler.release>17</maven.compiler.release>` target Java 17 classfile/API, cần JDK hỗ trợ.
- `commons-lang3` mặc định `compile`; Maven phải resolve POM/JAR và put on compile/runtime classpath.
- `junit-jupiter` ở `test` scope; Surefire dùng để chạy unit test.
- Clean/Resources/Compiler/Surefire/JAR/Dependency Plugin versions đều ghim cụ thể.
- Không có private repository, SNAPSHOT, dynamic ranges hoặc credentials trong lab baseline.
- Không có Maven Wrapper scripts mặc định; có thể gọi Maven cài sẵn hoặc thêm Wrapper riêng.
- Không có Java application server; lab phục vụ dependency resolution và build.
- `outputTimestamp` giúp archive timestamps ổn định khi plugin hỗ trợ, không sửa network errors.

### 36.2. App.java

File `src/main/java/dev/learning/resolve/App.java`:

~~~java
package dev.learning.resolve;

import org.apache.commons.lang3.StringUtils;

public final class App {

    private App() {
    }

    public static String message() {
        return "Resolved: " + StringUtils.capitalize("maven") + " + Java 17";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

`StringUtils.capitalize("maven")` trả `Maven`. Vì thế **dòng do chương trình in chính xác**:

~~~text
Resolved: Maven + Java 17
~~~

### 36.3. AppTest.java

File `src/test/java/dev/learning/resolve/AppTest.java`:

~~~java
package dev.learning.resolve;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class AppTest {

    @Test
    void returnsExpectedMessage() {
        assertEquals("Resolved: Maven + Java 17", App.message());
    }
}
~~~

Test xác minh code và classpath của project. Nó **không chứng minh remote repository sẽ luôn sẵn sàng** trong tương lai; chỉ thể hiện run hiện tại đã có đủ artifacts cần thiết.

## 37. Build baseline và chạy ứng dụng

Từ thư mục `resolution-lab`:

~~~bash
mvn -version
java -version
mvn -B -ntp clean verify
~~~

Khi Maven/JDK 17+, repository và source code hoạt động:

- Maven resolve plugins và project dependencies khi cần.
- Compiler Plugin biên dịch `App.java`.
- Surefire chạy JUnit test.
- JAR Plugin tạo `target/resolution-lab-1.0.0.jar`.
- Log có `BUILD SUCCESS`.

Để chạy main bằng Java launcher với JAR dependency trong local Maven repo mặc định:

Linux/macOS:

~~~bash
java -cp "target/classes:$HOME/.m2/repository/org/apache/commons/commons-lang3/3.14.0/commons-lang3-3.14.0.jar" dev.learning.resolve.App
~~~

Windows PowerShell:

~~~powershell
java -cp "target\classes;$HOME\.m2\repository\org\apache\commons\commons-lang3\3.14.0\commons-lang3-3.14.0.jar" dev.learning.resolve.App
~~~

Stdout:

~~~text
Resolved: Maven + Java 17
~~~

Các lệnh trên **giả định Maven local repository mặc định** và Commons Lang JAR đã tải vào đó. Nếu dùng `-Dmaven.repo.local` hoặc Maven settings override, thay JAR path tương ứng. `target/classes` có application class nhưng không tự chứa Commons Lang.

Không dùng:

~~~bash
java -jar target/resolution-lab-1.0.0.jar
~~~

làm cách chạy baseline, vì POM **không đặt Main-Class trong manifest** và không đóng gói Commons Lang thành fat JAR.

## 38. Thí nghiệm 1: lỗi dependency GAV sai có chủ đích

Chỉ trong **bản sao lab** hoặc nhánh thử nghiệm được phép, sửa artifactId trong Commons Lang dependency:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang33</artifactId>
    <version>3.14.0</version>
</dependency>
~~~

Đây là **đoạn cố ý sai**: thay `commons-lang3` thành `commons-lang33`.

Sau đó chạy:

~~~bash
mvn -B -ntp clean verify
~~~

Kết quả dự kiến: Maven không resolve được artifact không tồn tại ở Maven Central; log sẽ nêu GAV `org.apache.commons:commons-lang33:3.14.0`, có thể có `Could not find artifact`/not found và `BUILD FAILURE`.

**Cách sửa:** khôi phục artifactId đúng, không xóa repository cache hoặc tắt SSL. Nếu trước đó not-found đã được cached, có thể thử `-U` **sau khi** sửa GAV/repository, nhưng bản mới GAV đúng thường đi đường lookup khác.

Không bao giờ commit đoạn POM cố ý lỗi vào project thực.

## 39. Thí nghiệm 2: cache trống và offline mode

Tạo một local repository riêng **chưa có artifact Maven**.

Linux/macOS:

~~~bash
mkdir -p /tmp/resolution-empty-repo
mvn -B -ntp -o -Dmaven.repo.local=/tmp/resolution-empty-repo clean verify
~~~

Windows PowerShell:

~~~powershell
$repo = Join-Path $env:TEMP "resolution-empty-repo"
New-Item -ItemType Directory -Force -Path $repo | Out-Null
mvn -B -ntp -o "-Dmaven.repo.local=$repo" clean verify
~~~

Nếu directory thực sự trống và không có artifact/plugin cached theo resolver configuration, Maven sẽ FAIL vì không thể lấy plugin/dependency cần thiết trong offline mode. Nó có thể fail **ngay ở Maven Clean Plugin** chứ chưa đến Commons Lang.

Sau đó có thể chạy cùng repository **online**:

~~~bash
mvn -B -ntp -Dmaven.repo.local=/tmp/resolution-empty-repo clean verify
~~~

Rồi thử lại `-o` khi cache đủ.

**Thí nghiệm chỉ an toàn nếu path nằm trong directory do bạn quản lý.** Không chạy lệnh xóa Maven cache chung để tạo “empty repo”. Nếu môi trường có mirror bị lỗi, online run cũng có thể FAIL; đó là dữ liệu chẩn đoán.

## 40. Thí nghiệm 3: plugin version không tồn tại

Chỉ dùng trong **bản sao lab**, nếu bạn gọi một plugin version không được publish:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-compiler-plugin:0.0.0:compile
~~~

Mục tiêu là thấy plugin resolution failure thay vì project dependency resolution. `0.0.0` là version cố ý không hợp lệ đối với release được dùng trong lab.

Dòng lỗi dự kiến sẽ nhắc tới Maven Compiler Plugin version `0.0.0` hoặc plugin artifact không được tìm thấy; bạn **không nên** gán cho source code Java.

Sau thí nghiệm, quay về lệnh chuẩn:

~~~bash
mvn -B -ntp clean verify
~~~

Vì POM baseline ghim Maven Compiler Plugin `3.13.0`, nó sẽ không dùng version `0.0.0` trong lifecycle chuẩn.

## 41. Thí nghiệm 4: short prefix vs fully-qualified goal

Để so:

~~~bash
mvn -B -ntp dependency:tree
~~~

và:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
~~~

Trong điều kiện plugin/repository bình thường, cả hai có thể cho tree tương ứng. Nếu chỉ short prefix fail, hãy tìm vấn đề plugin prefix/metadata/group matching.

Nếu cả hai fail vì `PluginResolutionException`, Maven chưa có plugin/dependencies hoặc không truy cập được repository; kiểm tra mirror/credentials/cache.

Đừng ép một kết luận khi chưa đọc actual GAV và repository của run.

## 42. Khi lỗi chỉ xuất hiện trên CI

| Khác biệt CI vs laptop | Dấu hiệu | Hướng điều tra |
| --- | --- | --- |
| CI settings khác | Repo/mirror URL trong logs khác | So effective settings, secret binding |
| CI token thiếu/hết hạn | 401/403 | CI secret store và permission scope |
| CI behind corporate proxy | DNS/timeout/407 | Proxy settings, noProxyHosts, firewall |
| CI JDK truststore khác | PKIX | JDK vendor/patch, enterprise CA |
| CI local repo trống | Downloads nhiều, offline fail | Trusted repository proxy/cache |
| CI chạy Maven version khác | Plugin behavior/version resolution khác | Maven Wrapper, Enforcer |
| CI active profiles khác | Dependency/private repo chỉ xuất hiện trong profile | So `-P`, active profiles, settings profiles |
| CI checkout thiếu parent | Non-resolvable parent POM | Correct checkout/reactor |
| CI thiếu internal module | Failed project dependency resolution | Build reactor đúng `-pl/-am` |
| CI network restricted | HTTPS endpoint unreachable | Allowlist/proxy/policy |
| CI local repo shared improperly | Corrupt/stale artifact metadata | Isolated repos/locking/caches |

CI troubleshooting cần biết **runner image**, Java version, Maven settings, local cache path và job permission. Một POM chạy trên laptop không chứng minh CI có quyền đọc mọi private repository.

## 43. Maven Wrapper distribution download lỗi không phải plugin resolution

Nếu log xuất hiện **trước khi Maven Core khởi động**, ví dụ Wrapper không tải được Maven distribution từ `distributionUrl`, đây là lỗi **Wrapper bootstrap**. Cần kiểm tra:

- `.mvn/wrapper/maven-wrapper.properties`, distribution URL và checksum nếu có.
- Network/proxy/TLS của Wrapper implementation.
- Wrapper scripts có đúng platform/permissions không.
- Distribution file có bị mirror/proxy cấm không.
- CI có cache Maven Wrapper distribution được phép không.

Khi Wrapper chưa khởi động được Maven, chỉnh `<repositories>` trong POM **có thể không có tác dụng**. Phải tách stage này với Maven plugin artifact resolution.

## 44. Plugin đã tải nhưng không tương thích JDK/Maven

Một case khác:

~~~text
The plugin ... requires Maven version ...
UnsupportedClassVersionError
NoSuchMethodError
ClassNotFoundException
~~~

Những lỗi như trên có thể xảy ra khi plugin đã được tải và Maven bắt đầu load/thực thi plugin, nhưng bytecode/API/Maven Core hoặc transitive plugin dependency không tương thích.

**Đây không phải lỗi “không tải được plugin”**, dù biểu hiện cuối có thể là `Failed to execute goal`.

Cần kiểm tra:

- Plugin minimum Maven version theo docs.
- JDK runtime của Maven, không chỉ compiler release target.
- Plugin version có phù hợp Maven core không.
- Plugin/extension dependencies và xung đột library classloaders.
- Source bytecode của plugin so với JVM.
- Pin plugin version và upgrade theo compatibility matrix thay vì đoán.

Không cố gắng sửa `UnsupportedClassVersionError` bằng `-U`: Maven đã có artifact, vấn đề là runtime compatibility.

## 45. Kiểm tra update policy và snapshots

Repository POM có thể chứa policy:

~~~xml
<repositories>
    <repository>
        <id>company-snapshots</id>
        <url>https://repo.example.org/repository/maven-snapshots/</url>
        <releases>
            <enabled>false</enabled>
        </releases>
        <snapshots>
            <enabled>true</enabled>
            <updatePolicy>daily</updatePolicy>
        </snapshots>
    </repository>
</repositories>
~~~

Đây là **fragment minh họa**, URL không có thật.

Maven dùng release/snapshot policies và update intervals để quyết định lúc nào kiểm tra remote. Nếu SNAPSHOT artifact mới vừa được publish nhưng local metadata còn cached, bạn có thể cần chờ policy hoặc dùng `-U` có chủ đích.

Nếu remote SNAPSHOT đã bị cleanup theo retention, metadata/POM cũ có thể trỏ tới timestamped artifact không còn. Điều này không được sửa bằng cách xóa sạch cache rồi hy vọng artifact tự xuất hiện; cần repository manager restore/re-publish theo release policy hoặc pin artifact còn tồn tại.

## 46. Cẩn thận với HTTP repositories và insecure protocols

Trong Maven hiện đại, external HTTP repository access thường chịu các default blocking policies (đặc biệt từ Maven 3.8.x). Nếu POM/private settings vẫn dùng:

~~~xml
<url>http://repo.example.org/repository/maven-public/</url>
~~~

đây là **URL cấu hình không an toàn minh họa**, không nên được copy vào production. Cách khắc phục đúng thường là chuyển repository manager sang **HTTPS/TLS hợp lệ** hoặc dùng endpoint do tổ chức phê duyệt.

Không override HTTP blocker chỉ để “cho build xanh” khi chưa có đánh giá security. Việc tải dependencies/plugins là chạy/sử dụng code bên thứ ba; integrity của transport là quan trọng.

## 47. Khi repository báo 500/502/503

Lỗi thuộc repository manager/proxy/remote infrastructure có thể do:

- Upstream registry đang lỗi.
- Proxy cache corrupt hoặc đang reindex.
- Backend storage quota/full.
- Rate limit/connection pool.
- TLS gateway/load balancer gặp sự cố.
- CI egress bị thay đổi.

Cách xử lý:

1. Ghi URL/repository ID và HTTP status.
2. Kiểm tra repository service status với nhóm vận hành.
3. Thử một known-good artifact POM ở cùng endpoint nếu được phép.
4. Kiểm tra error xảy ra trên một artifact hay mọi artifacts.
5. Ghi thời điểm, scope users/jobs và correlation ID (nếu có).
6. Escalate repository admin, không tự đưa token vào URL.
7. Sau khi service hồi phục, retry theo update policy có kiểm soát.

**Không** chữa lỗi 503 bằng việc thay toàn bộ dependency versions hoặc tắt security checks.

## 48. Bảng quyết định nhanh theo thông điệp lỗi

| Thông điệp chính | Nên kiểm tra đầu tiên | Không ưu tiên |
| --- | --- | --- |
| `Could not resolve dependencies for project` | Failed project artifact GAV, repo, auth | Sửa Java method |
| `PluginResolutionException` | Plugin GAV, pluginRepositories/mirror | Đổi `junit-jupiter` tùy tiện |
| `No plugin found for prefix` | Prefix mapping, pluginGroups, plugin metadata | Xóa source code |
| `Non-resolvable parent POM` | Parent coords, relativePath, repo | Chạy `-DskipTests` |
| `Non-resolvable import POM` | BOM GAV, repo/policy | Chỉnh Compiler flags |
| `401/403` | Settings server ID/token/read permission | Xóa repo cache toàn bộ |
| `407` | Maven proxy credentials/settings | Đổi artifact version |
| `PKIX path building failed` | Java truststore/server cert/proxy | Bật SSL insecure |
| `UnknownHostException` | DNS/proxy/VPN/hostname | Nâng Surefire |
| `Read timed out` | Remote latency/proxy/backend | Tắt test |
| `This failure was cached` | Sửa root cause rồi `-U` hoặc targeted test | Xóa ~/.m2 vô điều kiện |
| `Offline mode and ... not been downloaded` | Artifact chưa cached | Sửa code App.java |
| `UnsupportedClassVersionError` | JDK/Maven/plugin bytecode compatibility | Retry download mãi |
| `Compilation failure` | Source/compiler/JDK/Classpath | Mirror nếu không có transfer error |
| `There are test failures` | Test reports/fixtures | Thay repository nếu đã resolve xong |

## 49. Quy trình chẩn đoán chuẩn cho một incident thật

1. **Dừng giả định** rằng mọi lỗi Maven là do code Java.
2. Lưu full command, POM revision, Maven/JDK versions và machine/CI context.
3. Tìm **first root-cause message**, không chỉ báo cáo BUILD FAILURE cuối cùng.
4. Phân loại: Wrapper, parent/BOM, project dependency, Maven plugin, plugin prefix, plugin execution hay test.
5. Ghi failed GAV/version/type/classifier và repository ID/URL.
6. Xác minh artifact coordinate chính xác từ nguồn tin cậy.
7. Kiểm tra repository đó có cung cấp artifact đúng version/packaging không.
8. Kiểm tra effective repositories, mirrors, pluginRepositories, settings và active profiles.
9. Nếu private repository, xác minh read access/token và server ID đúng endpoint.
10. Nếu network, kiểm tra DNS/proxy/TLS/HTTP status với người vận hành.
11. Nếu lỗi cached, **sau khi sửa root cause**, dùng `-U` hoặc thử isolated repo để xác nhận.
12. Nếu multi-module, xem reactor selection và `-am`.
13. Nếu chỉ short goal prefix fail, thử fully-qualified goal có version.
14. Nếu plugin đã resolve mà execution fail, chuyển sang kiểm tra compatibility/config/code.
15. Chạy lại **chính command gốc**, không chỉ một lệnh đã bỏ test hoặc đổi profile.
16. Lưu bằng chứng trước/sau, giải thích root cause và remediation bền vững.
17. Không sửa config/code ngoài thẩm quyền hoặc đưa credentials vào logs.
18. Với CI, kiểm tra môi trường sạch mới vẫn thành công; laptop cache không là bằng chứng đủ.

Một RCA tốt nêu “private BOM không tồn tại ở corporate mirror do proxy group thiếu upstream repository, sau khi sửa group thì `mvn clean verify` PASS” thay vì chỉ ghi “Maven lỗi mạng, đã xóa cache”.

## 50. Checklist trước khi kết luận đã sửa xong

- [ ] Đã xác định đúng loại lỗi: wrapper, dependency, parent/BOM, plugin, prefix hoặc execution.
- [ ] Ghi Maven/JDK version và full CLI command.
- [ ] Ghi exact GAV/version/type/classifier bị lỗi.
- [ ] Xác minh repository URL/ID thực Maven chọn.
- [ ] Xem mirrorOf trong settings, không đọc riêng POM.
- [ ] So `repositories` với `pluginRepositories` theo loại artifact.
- [ ] Không nhầm `distributionManagement` là nơi download dependencies.
- [ ] Với private repo, server ID/credentials/read role đã được kiểm tra đúng host.
- [ ] Không để token/password trong POM hoặc logs.
- [ ] HTTP 401/403/407 đã được xử lý đúng nguyên nhân.
- [ ] DNS/proxy/VPN/firewall có đường kết nối hợp lệ.
- [ ] Java truststore tin đúng certificate chain; không bypass TLS.
- [ ] Không sử dụng HTTP insecure endpoint tùy tiện.
- [ ] Parent/BOM coordinates và relativePath đúng.
- [ ] GAV/case/classifier/package type đúng.
- [ ] Snapshot/release policies và repository retention phù hợp.
- [ ] Lỗi cached đã được hiểu trước khi dùng `-U`.
- [ ] Không xóa toàn bộ shared local Maven repository.
- [ ] Khi cần đã thử isolated local repo với cùng settings/profiles.
- [ ] Nếu plugin prefix fail, đã thử goal fully-qualified có version.
- [ ] Nếu plugin realm fail, đã xem plugin transitive dependencies.
- [ ] Nếu source compilation fail, không đổ lỗi cho repository khi artifacts đã đủ.
- [ ] Nếu multi-module, đã build đúng reactor modules.
- [ ] Nếu offline mode fail, đã xác minh cache có đủ artifacts.
- [ ] Nếu CI-only, so JDK/Wrapper/settings/secret/runner/repository cache.
- [ ] Chạy lại đúng lệnh gốc; không “giải quyết” bằng cách skip tests.
- [ ] Lưu phiên bản source và logs đã redacted.
- [ ] Tạo RCA và ngăn tái phát (pin versions, mirror health, CI secrets).
- [ ] Tôn trọng quyền truy cập và chính sách artifact provenance.

## 51. Bài tập tự kiểm tra có đáp án

1. **`Could not resolve dependencies` chắc chắn là lỗi Compiler Plugin?**  
   Không. Đây thường là project dependency artifact resolution, cần đọc GAV cụ thể.

2. **`PluginResolutionException` có thể xảy ra khi project không có external dependency?**  
   Có, vì Maven lifecycle vẫn cần plugin artifacts.

3. **Parent POM được resolve lúc nào?**  
   Khi Maven dựng project model, có thể trước mọi compiler goal.

4. **BOM được dùng để làm gì?**  
   Quản lý versions, thường qua `dependencyManagement` với type `pom`/scope `import`.

5. **Thư viện private có chắc tồn tại trên Maven Central?**  
   Không, cần repository nội bộ phù hợp.

6. **`<repositories>` phục vụ chủ yếu nhóm nào?**  
   Project dependencies.

7. **`<pluginRepositories>` phục vụ nhóm nào?**  
   Maven plugins và plugin dependencies.

8. **`<distributionManagement>` là nơi Maven download dependencies?**  
   Không; chủ yếu là đích publish project artifacts.

9. **Mirror `mirrorOf=*` có thể ảnh hưởng plugin download?**  
   Có, theo repository mirroring rules.

10. **Maven có tự hợp nhất tất cả mirror cùng match?**  
    Không; nó chọn mirror theo matching rules; repository manager mới tổng hợp/proxy sources.

11. **Server ID trong settings dùng để làm gì?**  
    Match credentials tới effective repository/mirror ID.

12. **401 thường gợi ý gì?**  
    Thiếu/sai/hết hạn credentials.

13. **403 có chắc artifact không tồn tại?**  
    Không; có thể thiếu quyền/policy.

14. **407 nói về ai?**  
    Proxy authentication.

15. **404 có thể do lỗi nào?**  
    Sai GAV/version/classifier hoặc repository không có artifact.

16. **PKIX path building failed thường liên quan gì?**  
    JVM TLS trust chain/certificate.

17. **Có nên tắt SSL validation để Maven download được?**  
    Không.

18. **Có nên xóa `~/.m2/repository` ngay?**  
    Không; ưu tiên xác định lỗi và dùng repo riêng.

19. **`-U` có tạo ra artifact không tồn tại không?**  
    Không.

20. **`-U` có thể hữu ích khi nào?**  
    Sau khi remote artifact/metadata đã sửa hoặc cached failure cần được kiểm tra lại.

21. **`-o` nghĩa là gì?**  
    Maven offline resolution; artifacts cần thiết phải có trong cache.

22. **Offline FAIL khi cache trống chứng minh code Java sai?**  
    Không; plugin/dependency chưa cached.

23. **`-ntp` có chặn network transfer không?**  
    Không; chỉ ẩn transfer progress.

24. **`-X` có cần dùng cho mọi build thường ngày?**  
    Không; debug khi cần, logs phải được redacted.

25. **`-e` có ích gì?**  
    Hiển thị stack traces để tìm nguyên nhân.

26. **Lệnh full-coordinate cho Maven Dependency Plugin tree?**  
    `mvn org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree`.

27. **Tại sao short prefix có thể fail dù plugin artifact tồn tại?**  
    Prefix mapping/plugin metadata hoặc pluginGroups chưa resolve đúng.

28. **Một plugin có tải xong JAR chính nhưng vẫn lỗi resolve?**  
    Có; transitive plugin dependency có thể thiếu.

29. **Goal nào kiểm tra plugin artifacts?**  
    `dependency:resolve-plugins`, nhưng chính Dependency Plugin cần resolve trước.

30. **Goal nào prefetch project/plugin dependencies?**  
    `dependency:go-offline`; không bảo đảm mọi custom external download.

31. **Non-resolvable parent POM xử lý trước hay sau Java source compilation?**  
    Trước; Maven chưa dựng được model.

32. **Muốn build service cùng reactor dependency common thì dùng gì?**  
    Từ root: `mvn -pl :service -am clean verify` khi các modules cùng reactor.

33. **`-am` có thể tìm module không thuộc reactor không?**  
    Không.

34. **Version `0.0.0` trong plugin negative test dùng để làm gì?**  
    Cố ý yêu cầu plugin không có, quan sát plugin resolution failure.

35. **Stdout chính xác của Java 17 lab?**  
    `Resolved: Maven + Java 17`.

36. **Dependency compile chính của lab là gì?**  
    `org.apache.commons:commons-lang3:3.14.0`.

37. **Dependency test chính của lab là gì?**  
    `org.junit.jupiter:junit-jupiter:5.11.4`.

38. **Plain JAR lab có tự chứa Commons Lang không?**  
    Không, phải có runtime classpath.

39. **`curl` trả 200 có chắc Maven dùng cùng URL và truststore không?**  
    Không; có mirror/proxy/JVM khác.

40. **Có nên sửa settings production chỉ để demo không?**  
    Không; dùng môi trường thử nghiệm được phép.

41. **Nếu Maven báo UnsupportedClassVersionError sau khi đã tải plugin, đó là gì?**  
    Lỗi compatibility/runtime/plugin loading, không phải download missing artifact.

42. **Khi repo trả 503, bước đầu là gì?**  
    Xác minh repository service/gateway/upstream health, ghi URL/status.

43. **Cách xác nhận đã sửa đúng?**  
    Chạy lại chính command/profiles/CI workflow ban đầu và lưu evidence.

44. **Thông điệp quan trọng nhất?**  
    Phân loại đúng artifact/lỗi/đích repository trước khi thay config hay cache; sửa **nguyên nhân gốc** thay vì xóa toàn bộ Maven repository.

## 52. Tài liệu chính thức

- [Apache Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html): local/remote repository, resolving dependencies.
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): transitive dependency rules, scopes, mediation.
- [Apache Maven — Guide to Multiple Repositories](https://maven.apache.org/guides/mini/guide-multiple-repositories.html): repository precedence và mirror application.
- [Apache Maven — Using Mirrors for Repositories](https://maven.apache.org/guides/mini/guide-mirror-settings.html): `mirrorOf`, external matching và mirror selection.
- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html): servers, mirrors, proxies, profiles, localRepository.
- [Apache Maven — Maven POM Reference](https://maven.apache.org/pom.html): repositories, pluginRepositories, distributionManagement.
- [Apache Maven — Maven CLI Options 3.9.9](https://maven.apache.org/ref/3.9.9/maven-embedder/cli.html): `-U`, `-o`, `-X`, `-e`, `-s`, `-ntp`.
- [Apache Maven — Guide to Configuring Maven](https://maven.apache.org/guides/mini/guide-configuring-maven.html): settings, proxy, authentication.
- [Apache Maven Dependency Plugin — dependency:resolve](https://maven.apache.org/plugins/maven-dependency-plugin/resolve-mojo.html): resolve project dependencies.
- [Apache Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): inspect dependency paths.
- [Apache Maven Dependency Plugin — dependency:resolve-plugins](https://maven.apache.org/plugins/maven-dependency-plugin/resolve-plugins-mojo.html): resolve project plugins and their dependencies.
- [Apache Maven Dependency Plugin — dependency:go-offline](https://maven.apache.org/plugins/maven-dependency-plugin/go-offline-mojo.html): prefetch dependencies/plugins.
- [Apache Maven Dependency Plugin — dependency:purge-local-repository](https://maven.apache.org/plugins/maven-dependency-plugin/purge-local-repository-mojo.html): targeted cache purge semantics.
- [Apache Maven — Guide to Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html): Maven reactor và module selection.
- [Apache Maven Wrapper](https://maven.apache.org/tools/wrapper/): wrapper distribution bootstrap.
- [Maven Resolver — DefaultUpdateCheckManager](https://maven.apache.org/resolver/xref/org/eclipse/aether/internal/impl/DefaultUpdateCheckManager.html): failed resolution cache/update policy.
- [Oracle Java 17 — java launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): JVM classpath và chạy Java class.

**Kết luận:** `Could not resolve dependencies`, plugin artifact không tải được, parent/BOM không resolve và plugin prefix không tìm thấy đều trông giống “Maven không build”, nhưng **không cùng nguyên nhân**. Hãy tìm exact GAV, repository URL/ID và error gốc; kiểm tra effective settings/mirrors, credentials, network, TLS, update/cache policy rồi mới chỉnh sửa. `-U`, `-o`, `-X` và local repository cô lập là **công cụ chẩn đoán**, không phải thuốc chữa mọi lỗi. Luôn xác minh bằng lệnh build gốc sau khi sửa, không xóa cache toàn máy hoặc bỏ kiểm tra bảo mật chỉ để có `BUILD SUCCESS`.
