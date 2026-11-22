# Artifact bị ghi nhận not found và cách kiểm tra .lastUpdated trong Maven

## 1. Tình huống thường gặp

Một project Maven có dependency hợp lệ nhưng lần build hiện tại báo:

~~~text
Could not find artifact org.example:sample-lib:jar:1.0.0 in central
~~~

Hoặc:

~~~text
Failure to find ... was cached in the local repository.
Resolution will not be reattempted until the update interval
of the repository has elapsed or updates are forced.
~~~

Những dòng trên là **mẫu thông điệp được rút gọn**, không phải một lần build đã chạy trong bài. Khi Maven thử tải một artifact nhưng remote trả lời **không tìm thấy**, Maven có thể ghi lại kết quả âm tính vào **local repository**. Lần sau, để tiết kiệm network requests, Resolver có thể dùng lại trạng thái đó cho tới khi hết chu kỳ kiểm tra hoặc khi buộc cập nhật.

Vì vậy có thể xảy ra kịch bản: 09:00 Maven hỏi một version chưa publish và nhận 404; 09:05 nhóm khác mới publish version ấy; 09:06 Maven ở máy cũ vẫn báo “cached not found”. Tuy nhiên **không được mặc định mọi lỗi not found là do cache**. GAV sai, repository không chứa file, parent POM thiếu, snapshots disabled, mirror sai, auth bị từ chối và lỗi mạng đều cần được chẩn đoán riêng.

Bài này tập trung vào Maven **3.9.x / JDK 17+**: cách hoạt động của **negative resolution cache**, nơi tìm file `.lastUpdated`, đọc file một cách an toàn, lệnh `-U`, `-o`, cách kiểm repositories và khi nào mới cần xóa cache mục tiêu. Có demo Maven Java 17 có profile cố tình thêm một dependency giả để quan sát failure.

## 2. Tọa độ artifact và đường dẫn repository

Maven nhận diện dependency qua các thành phần như `groupId`, `artifactId`, `version`, `type/extension` và `classifier` khi có.

Ví dụ một dependency thực:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.14.0</version>
</dependency>
~~~

Trong layout Maven chuẩn, file chính thường nằm dưới:

~~~text
org/apache/commons/commons-lang3/3.14.0/
    commons-lang3-3.14.0.pom
    commons-lang3-3.14.0.jar
~~~

**POM là artifact descriptor**, JAR là compiled binary. Có thể POM không tải được dù JAR còn trong local repo; lỗi đó thường xuất hiện dưới dạng `Failed to read artifact descriptor`. Parent POM và BOM dùng `packaging=pom` không cần main JAR; không báo thiếu JAR khi artifact đúng là `pom`.

Classifier thay đổi filename: `sources` đi với `-sources.jar`, `javadoc` đi với `-javadoc.jar`. Vì vậy trước khi xử lý, copy chính xác **toàn bộ coordinates và extension/classifier** từ lỗi; đừng chỉ nhìn tên artifactId rồi xóa thư mục có tên gần giống.

## 3. Local repository và remote repository

Theo Apache Maven:

- **Local repository:** cache của Maven trên máy chạy build, thường là `~/.m2/repository` nhưng có thể được thay qua `settings.xml` hoặc `-Dmaven.repo.local=...`.
- **Remote repository:** kho qua `https://` hoặc `file://` theo Maven layout. Maven Central, private Nexus/Artifactory và corporate proxies đều là những ví dụ.
- **Mirror:** cấu hình ở settings có thể chuyển yêu cầu tới một repo manager khác với URL người viết POM dự kiến.
- **CI cache:** dịch vụ CI có thể lưu/khôi phục nguyên thư mục local repository giữa jobs. Đây là một lớp cache **khác** cache do Maven Resolver ghi.
- **Repository manager negative cache:** server proxy có thể tự cache 404; đây lại là một lớp nữa.

Một GAV có thể tồn tại trên Maven Central nhưng Maven build trong doanh nghiệp chỉ được đi qua proxy mirror, và mirror chưa có/không được phép phục vụ artifact đó. Trong trường hợp ấy `-U` buộc Maven client retry nhưng **không làm proxy tự có artifact**.

Trước tiên hãy xác định build đang dùng local repo nào. Với CI, local repository không nhất thiết nằm dưới home thư mục mặc định; dùng đúng `-Dmaven.repo.local` của invocation và settings thật.

## 4. Maven Resolver tạo .lastUpdated như thế nào?

Luồng cơ bản:

~~~text
Project POM + settings + active profiles
            |
            v
Compute effective coordinates and repositories
            |
            v
Check local repository and update policy
            |
      +-----+------+
      |            |
  Available      Need remote request
      |            |
      v            v
  Use file    Remote repository
                   |
             +-----+-----+
             |           |
         Download OK   Not found
             |           |
             v           v
         Save POM/JAR  Record miss as applicable
                         in *.lastUpdated
~~~

`.lastUpdated` là **local marker file**, không phải dependency và không phải file publisher phải upload. Maven Resolver sử dụng nó để nhớ một kết quả kiểm tra / thất bại tương ứng với artifact và remote repository.

Ví dụ trong local cache:

~~~text
org/example/training/missing-demo-lib/999.0.0/
    missing-demo-lib-999.0.0.pom.lastUpdated
    missing-demo-lib-999.0.0.jar.lastUpdated
~~~

Cả hai tên là **file có thể xuất hiện**, không phải bảo đảm Maven luôn tạo cả đôi. Một invocation có thể dừng ở POM, ở JAR hoặc thậm chí trước khi gọi remote. **Không có marker không chứng minh rằng chưa từng lỗi**: có thể bạn đang xem sai local repo, file đã được dọn, offline mode không hỏi remote, hoặc Resolver/phiên bản xử lý khác.

## 5. .lastUpdated chứa gì?

Tài liệu Apache Maven Artifact Resolver mô tả marker là một **Java Properties file**. Nội dung có thể gắn với canonical remote URL, thời điểm kiểm tra và thông tin lỗi. Một key tương ứng `<remote-url>.error` được dùng để phân biệt trạng thái trong chính sách Resolver:

- Giá trị lỗi **rỗng** có thể biểu thị loại lỗi **not found**.
- Giá trị lỗi **không rỗng** biểu thị những lỗi truyền tải khác nếu chính sách Resolver đang lưu loại lỗi đó.
- Các keys/timestamps có thể được escape trong định dạng Java Properties, chẳng hạn dấu `:` trong URL.

**Chính sách mặc định Maven 3:** theo tài liệu Resolver, lỗi **not found (type 1) luôn được cache**, còn các lỗi khác như authentication/timeouts (type 2) **không được cache** bởi Maven 3 theo chính sách mặc định. Vì vậy không thể kết luận “HTTP 401 đang được cache” chỉ vì thấy một file có hậu tố `.lastUpdated`.

Không dựa vào **dạng chính xác của properties keys** để viết parser production, vì đây là trạng thái nội bộ của Resolver. Có thể dùng file làm bằng chứng hỗ trợ, nhưng **log Maven + tọa độ + remote URL** vẫn là cơ sở chẩn đoán chính.

**Bảo mật:** marker/log có thể tiết lộ URL private repo hoặc thông tin nhạy cảm nếu URL bị cấu hình sai. Không gửi nguyên file ra issue công khai khi chưa redact.

## 6. Cached miss khác remote 404 hiện tại

Khi một artifact chưa tồn tại trên remote, Maven có thể nhận 404 từ lần gọi thật. Sau đó, một lần chạy khác trong update interval có thể bị chặn ở local cache:

~~~text
Failure to find ... was cached in the local repository.
Resolution is not reattempted until the update interval ...
~~~

Thông báo “was cached” nói rằng **lần này Maven có thể đã không gửi lại request tới remote**. Nó không chứng minh artifact vẫn thiếu trên server tại thời điểm hiện tại.

Ngược lại, một lỗi 404 sau khi chạy `-U` có thể là remote thực sự tiếp tục không có artifact, hoặc proxy/permission policy vẫn trả 404. Nếu repository chưa publish, xóa marker không giúp; nếu kho mới publish nhưng Maven dùng mirror sai, cũng không giúp.

Khi thấy `Failed to read artifact descriptor`, hãy tìm **POM/parent/BOM liên quan**, không chỉ JAR. Khi thấy `PluginResolutionException`, kiểm `pluginRepositories` và repositories mà Maven dùng để tải plugin.

## 7. updatePolicy quyết định nhịp kiểm lại

Maven có `updatePolicy` cho `releases` và `snapshots` trong repository configuration:

| Giá trị | Ý nghĩa phổ biến |
| --- | --- |
| `always` | Kiểm theo nhu cầu mỗi khi policy yêu cầu cập nhật. |
| `daily` | Kiểm theo nhịp hàng ngày, default thông dụng. |
| `interval:30` | Kiểm theo khoảng 30 phút (giá trị ví dụ). |
| `never` | Không chủ động kiểm thường xuyên những file đã có theo policy. |

Một mảnh POM minh họa:

~~~xml
<repositories>
    <repository>
        <id>corp-snapshot</id>
        <url>https://repo.example.invalid/maven/snapshots/</url>
        <releases><enabled>false</enabled></releases>
        <snapshots>
            <enabled>true</enabled>
            <updatePolicy>daily</updatePolicy>
        </snapshots>
    </repository>
</repositories>
~~~

`example.invalid` là miền giả, không phải kho Maven dùng được. Nếu repository policy đang chờ tới lần kiểm tra tiếp theo, một miss cũ có thể được sử dụng lại. **Không đổi tất cả repos thành `always`** chỉ để sửa một artifact: việc đó làm tăng network traffic và không chữa GAV/permission sai.

## 8. -U: buộc kiểm tra lại, không phải lệnh sửa mọi lỗi

Apache Maven 3.x Compatibility Notes mô tả cách dùng `-U` để invalidating cached resolution error và force update check sau khi remote repository mới được sửa.

~~~bash
mvn -B -ntp -U clean verify
~~~

Dùng khi:

1. Đã xác nhận version/GAV đúng.
2. Artifact vừa được publish hoặc repository manager vừa đổi nguồn proxy.
3. Log nói kết quả miss được cache, hoặc có cơ sở nghi ngờ local negative cache.
4. Maven có quyền/kết nối để tải artifact từ remote đúng.

**Không kỳ vọng `-U`:** tự publish file còn thiếu, sửa tọa độ sai, vượt quyền 401/403, vô hiệu hóa TLS, sửa proxy server negative cache hay ép tải lại mọi JAR release đã hiện diện và hợp lệ.

Nếu `-U` vẫn báo không tìm thấy, chuyển sang kiểm **remote repository actual contents, repo ID, mirror, visibility, credentials và SNAPSHOT policies**. Không retry liên tục làm nhiễu logs/quota.

## 9. -o: offline mode không tải artifact mới

Lệnh:

~~~bash
mvn -B -ntp -o verify
~~~

chỉ dùng local repository. Nếu chỉ còn marker `.lastUpdated` mà không có POM/JAR tương ứng, build offline vẫn không có bytes cần thiết.

Không coi `-o -U` là “vừa offline vừa download bản mới”: hai mục tiêu mâu thuẫn. `-U` chỉ có tác dụng recheck remote khi Maven được phép kết nối.

Nếu offline build fail ở Maven Compiler Plugin, có thể **plugin** chưa cache, không liên quan một project dependency. Cần kiểm chính xác artifact đầu tiên báo thiếu.

## 10. Release, SNAPSHOT và maven-metadata.xml

Release GAV `org.example:lib:1.0.0` có file names dạng:

~~~text
org/example/lib/1.0.0/lib-1.0.0.pom
org/example/lib/1.0.0/lib-1.0.0.jar
~~~

Các kho release tốt nên immutable; không nên thay bytes dưới cùng version đã phát hành.

SNAPSHOT `1.0.1-SNAPSHOT` có thể được resolve dựa trên version-level metadata:

~~~text
org/example/lib/1.0.1-SNAPSHOT/
    maven-metadata.xml
    lib-1.0.1-20261110.101112-1.pom
    lib-1.0.1-20261110.101112-1.jar
~~~

Timestamp ở trên **chỉ minh họa**, không phải kết quả đã tải. Local repo có thể lưu metadata dưới tên `maven-metadata-<repo-id>.xml`. **`maven-metadata.xml` và `.lastUpdated` không giống nhau**: metadata cho version discovery/snapshot timestamps, marker cho update check/failure state.

Khi SNAPSHOT missing, kiểm `snapshotRepository` thực sự được deploy, `snapshots.enabled` trong consumer repository, metadata và timestamped files. `-U` có thể buộc metadata update nhưng không sửa publishing thiếu POM/JAR.

## 11. Demo Java 17: một project chạy bình thường và một profile tạo miss

Cấu trúc:

~~~text
maven-miss-demo/
├── pom.xml
└── src/main/java/org/example/diagnostics/Main.java
~~~

Dự án mặc định chỉ dùng JDK 17. Profile `simulate-missing` thêm tọa độ giả, để bài học có thể quan sát negative caching **trong local repository riêng**, không ảnh hưởng project production.

**Yêu cầu:** JDK 17+, Maven 3.9.x, kết nối tới approved Maven plugin repository. Nếu repository plugin bị chặn, Maven có thể fail trước khi nó thử dependency giả; lúc đó phải sửa plugin repo trước.

## 12. pom.xml đầy đủ

Tạo `maven-miss-demo/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example.diagnostics</groupId>
    <artifactId>maven-miss-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>

    <profiles>
        <profile>
            <id>simulate-missing</id>
            <dependencies>
                <dependency>
                    <groupId>org.example.training</groupId>
                    <artifactId>missing-demo-lib</artifactId>
                    <version>999.0.0</version>
                </dependency>
            </dependencies>
        </profile>
    </profiles>
</project>
~~~

Tọa độ `org.example.training:missing-demo-lib:999.0.0` là **artifact giả định không có trong các repositories dùng cho demo**. Nếu một môi trường test tình cờ publish artifact trùng tên, chọn một tọa độ giả khác trong **kho test**, không dùng product thật.

Profile không active mặc định, vì thế build bình thường không bị cố ý làm lỗi. Không commit profile “simulate-missing” vào project production như một cấu hình vận hành.

## 13. Main.java và một build bình thường

Tạo `src/main/java/org/example/diagnostics/Main.java`:

~~~java
package org.example.diagnostics;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("Maven resolver demo OK");
    }
}
~~~

Chạy từ thư mục `maven-miss-demo`:

~~~bash
mvn -B -ntp clean package
java -cp target/classes org.example.diagnostics.Main
~~~

**Stdout chính xác của lệnh Java:**

~~~text
Maven resolver demo OK
~~~

Maven logs không phải stdout Java và có thể thay đổi theo Maven/plugins. Nếu lệnh package fail trước khi profile được bật, kiểm JDK/compiler plugin/repositories; không kết luận đó là lỗi của dependency giả.

## 14. Tạo negative cache có kiểm soát

Từ project root, chạy:

~~~bash
mvn -B -ntp -Dmaven.repo.local=./resolver-demo-repo -Psimulate-missing compile
~~~

Dùng `-Dmaven.repo.local=./resolver-demo-repo` để chọn **cache riêng**, không can thiệp `~/.m2/repository`. Maven có thể tải các plugins vào cache mới trước khi thử dependency giả.

Vì GAV giả dự kiến không có ở remote, `compile` có thể **BUILD FAILURE**. Đây là **kết quả chủ đích**. Một thư mục local có thể được tạo:

~~~text
resolver-demo-repo/
└── org/example/training/missing-demo-lib/999.0.0/
    ├── missing-demo-lib-999.0.0.pom.lastUpdated
    └── missing-demo-lib-999.0.0.jar.lastUpdated   # có thể xuất hiện
~~~

Không yêu cầu cả hai marker phải có. Tùy Resolver, phase và error, chỉ POM marker có thể được ghi. Nếu toàn bộ plugin resolve fail trước, không có marker dependency giả cũng là điều có thể hiểu được.

Chạy lại cùng lệnh trong một update interval:

~~~bash
mvn -B -ntp -Dmaven.repo.local=./resolver-demo-repo -Psimulate-missing compile
~~~

Log có thể chuyển từ “remote not found” sang “cached ... until update interval”. Không bịa số request hoặc timestamp cụ thể: behavior thực phụ thuộc settings và state.

## 15. Đọc marker trên Linux/macOS

Từ thư mục project:

~~~bash
find ./resolver-demo-repo/org/example/training/missing-demo-lib/999.0.0 \
  -type f -name '*.lastUpdated' -print
~~~

Nếu file POM marker có thật, đọc:

~~~bash
cat ./resolver-demo-repo/org/example/training/missing-demo-lib/999.0.0/missing-demo-lib-999.0.0.pom.lastUpdated
~~~

Nếu `find` không thấy directory, xác nhận Maven thật sự dùng `-Dmaven.repo.local=...`, plugin không fail sớm và một remote request đã được thử. Đừng tự tạo file `.lastUpdated` để “bổ sung cache”.

**Điều cần quan sát:** filename đúng artifact và extension, remote URL trong properties nếu có, trạng thái lỗi, file last-modified time và lời thông báo trong Maven log. Không upload nguyên file ra public issue nếu chứa private repo URL.

## 16. Đọc marker trên Windows PowerShell

Trong thư mục `maven-miss-demo`:

~~~powershell
$dir = ".\resolver-demo-repo\org\example\training\missing-demo-lib\999.0.0"
if (Test-Path -LiteralPath $dir) {
    Get-ChildItem -LiteralPath $dir -Filter "*.lastUpdated" -File |
        Select-Object Name, Length, LastWriteTime
}
~~~

Đọc POM marker nếu tồn tại:

~~~powershell
$marker = Join-Path $dir "missing-demo-lib-999.0.0.pom.lastUpdated"
if (Test-Path -LiteralPath $marker) {
    Get-Content -LiteralPath $marker
}
~~~

PowerShell trên Windows thường có default local repo `$HOME\.m2\repository`, nhưng **demo dùng ./resolver-demo-repo**. Đường dẫn theo shell phải trùng với file path Maven thực sử dụng. Nếu file không có, đừng suy ngay rằng không có cached miss ở nơi khác.

## 17. Thử -U trên demo và hiểu kết quả

Chạy:

~~~bash
mvn -B -ntp -U -Dmaven.repo.local=./resolver-demo-repo -Psimulate-missing compile
~~~

Cờ `-U` yêu cầu Maven **retry/update checks** cho cached status. Do dependency giả chưa publish, build vẫn có thể fail 404 — đó **không phải** dấu hiệu `-U` vô dụng. Nó chỉ chứng minh hiện tại chưa có artifact resolve được qua repositories hiệu lực.

Với một thư viện **đã được publish sau lần miss**, `-U` có thể giúp Maven tải thành công. Nhưng phải kiểm artifact POM/JAR thực trên kho, quyền đọc, và URL Maven dùng. Nếu proxy phía server giữ 404, một local `-U` vẫn có thể nhận 404.

## 18. Dùng dependency:get để kiểm artifact biết là có

Có thể dùng Maven Dependency Plugin `3.8.1`, goal `get`, để kiểm riêng một GAV công khai:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:get \
  -Dartifact=org.apache.commons:commons-lang3:3.14.0 \
  -Dtransitive=false
~~~

Đây là một version **đã được phát hành**, không có nghĩa bản mới nhất. Goal có thể gọi Maven Central theo Super POM/mirror config và vẫn phải tải chính Dependency Plugin trước khi tải artifact.

Cú pháp `-Dartifact` ở plugin `3.8.1` là:

~~~text
groupId:artifactId:version[:packaging[:classifier]]
~~~

Nếu muốn type JAR minh bạch:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:get \
  -Dartifact=org.apache.commons:commons-lang3:3.14.0:jar \
  -Dtransitive=false
~~~

**Không đảo version và packaging**. Nếu public known-good artifact resolve được nhưng internal artifact không, kiểm repo profile/mirror/auth của internal. Nếu cả hai không resolve, có thể vấn đề nằm ở network, corporate proxy, pluginRepositories hoặc TLS.

Lưu ý `-Dtransitive=false` giảm graph dependency mà goal lấy, **không** có nghĩa Maven plugin resolution cần 0 dependencies.

## 19. Kiểm effective repositories và credentials

Một checklist cho `pom.xml` và `settings.xml`:

- `<repositories>` cho project dependencies; `<pluginRepositories>` cho Maven build plugins.
- Active settings profiles và `activeProfiles` có thực sự bật kho private cần thiết?
- `<mirrors>` `mirrorOf` có chuyển request sang server khác? Repository ID sau mirror là ID nào?
- `<servers><server><id>...` có khớp repository hoặc mirror ID thực được chọn?
- Token có quyền **read** artifact? Một số repo private trả 404 để không tiết lộ package khi user không được phép.
- Repo có `<releases><enabled>...` và `<snapshots><enabled>...` đúng với version?
- Proxy/TLS/corporate CA/firewall/DNS có cho phép kết nối?
- Artifact đã **published** thực sự hay vẫn đang staging/đang cài local trên máy publisher?

Mảnh mirror minh họa:

~~~xml
<mirrors>
    <mirror>
        <id>corp-mirror</id>
        <mirrorOf>external:*</mirrorOf>
        <url>https://repo.example.invalid/maven/proxy/</url>
    </mirror>
</mirrors>
~~~

`example.invalid` chỉ là ví dụ, không được dùng như URL production. Một server entry cho `corp-mirror` cần match mirror ID, không nhất thiết ID `central` gốc.

**Không in** settings passwords/API keys/token vào logs. `401` thường chỉ auth thiếu hoặc sai; `403` có thể thiếu quyền hay policy. Đừng sửa bằng cách tắt TLS verification hoặc cấp admin token bừa bãi.

## 20. Help Plugin giúp kiểm cấu hình, nhưng có giới hạn

Goal của Maven Help Plugin:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.1:effective-settings
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.1:effective-pom
~~~

Nó giúp hiểu settings và effective POM sau merge. Nhưng nếu **parent POM thiếu**, goal `effective-pom` cũng có thể fail trước khi in output. Nếu Help Plugin chưa được tải và plugin repo lỗi, chính công cụ chẩn đoán cũng fail.

Không bật tùy chọn hiện passwords trong log. Effective settings dù ẩn password vẫn có thể chứa private repo URLs, proxy metadata; chỉ lưu/chia sẻ bản đã redact.

Khi nhiều profiles/BOMs dùng version management, tìm chính GAV/version **được resolve**, không chỉ version ở dòng dependency trực tiếp.

## 21. Dọn .lastUpdated: không xóa cả ~/.m2

Thứ tự xử lý nên là:

1. Kiểm **GAV/version/type/classifier** và artifact có trên remote thật không.
2. Kiểm mirror/credentials/snapshot enable và local repository path.
3. Dùng **một lượt `-U`** sau khi biết request cần retry.
4. Chỉ khi có bằng chứng cache cục bộ lỗi/miss vẫn cản trở, mới cân nhắc **xóa đúng các marker của artifact/version** hoặc dùng local repo cô lập.
5. Xác minh Maven tải được POM/JAR và project build pass.

**Không chạy lệnh xóa toàn bộ** `~/.m2/repository` hay mọi `*.lastUpdated` theo wildcard toàn hệ thống. Điều đó làm mất hàng nghìn artifacts, làm CI chậm, có thể xóa những local-only artifacts chưa deploy, và chưa chắc sửa đúng nguyên nhân.

Việc xóa file marker không làm artifact tự xuất hiện trên remote. Không chỉnh tay contents/timestamps của Java Properties để ép Resolver như một API được hỗ trợ.

## 22. Dependency Plugin: purge có giới hạn

Goal `purge-local-repository` có thể xóa cached project dependencies và tùy chọn resolve lại. **Nếu chạy không filter, phạm vi có thể rất rộng**. Với Plugin `3.8.1`, có option `manualInclude`:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:purge-local-repository \
  -DmanualInclude=org.example.training:missing-demo-lib \
  -DreResolve=false
~~~

Đây là **lệnh có tác dụng xóa** trong local repository, không nên chạy máy/runner dùng cache chung nếu chưa review. `manualInclude` nhắm groupId:artifactId; `resolutionFuzziness` ảnh hưởng mức chi tiết file/version bị loại. `-DreResolve=false` giúp không ngay lập tức tải lại.

Vì đây là bài chẩn đoán, **không cần purge để học marker**. Dùng `-U` trước; khi cần isolate, repo riêng qua `-Dmaven.repo.local=...` có thể an toàn hơn động vào cache mặc định.

Đừng chọn `manualInclude` quá rộng rồi tình cờ xóa cả các versions không liên quan.

## 23. Parent POM, BOM và plugin có thể là artifact bị missing

Không chỉ project JAR mới gặp lỗi. Ví dụ:

~~~text
Non-resolvable parent POM for org.example:my-service:1.0.0
~~~

Trong trường hợp đó, Maven cần **parent POM artifact**, và marker có thể là `parent-version.pom.lastUpdated`. Source checkout của tác giả có thể có parent qua `relativePath`, nhưng CI tách source tree không có parent hoặc remote chưa publish.

Một BOM import là POM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.example.platform</groupId>
            <artifactId>company-bom</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đây chỉ là POM fragment minh họa. Nếu BOM thiếu, kiểm đường dẫn `company-bom-1.0.0.pom` và marker của BOM, không tìm JAR không tồn tại.

Maven plugins và plugin dependencies dùng `pluginRepositories` hoặc plugin mirror; `dependency:tree` của ứng dụng không nhất thiết bao gồm plugin classpath. Một lỗi Maven Compiler Plugin missing có hướng điều tra khác với dependency compile của ứng dụng.

## 24. CI cache có thể duy trì miss cũ qua nhiều jobs

Một CI cache restore chứa cả `.lastUpdated` từ lần trước có thể giữ dấu miss lâu hơn điều developer dự kiến. Trong khi đó còn có proxy registry cache và HTTP CDN/proxy cache phía server.

Phân biệt các lớp:

| Lớp | Vị trí | Cách kiểm |
| --- | --- | --- |
| Maven local repository | Runner/home hoặc `-Dmaven.repo.local` | Marker và artifact files theo GAV. |
| CI cache service | Cache store/restore giữa jobs | Cache key, timestamp, trust domain. |
| Maven repository manager | Nexus/Artifactory/proxy | Upstream availability, negative cache policy, repository routing. |
| Proxy/CDN | Hệ thống mạng | Response status/headers, incident/provider logs. |

`-U` buộc **client Maven** kiểm lại theo chính sách, **không xóa server-side negative cache**. Nếu dependency mới publish vẫn chưa nhìn thấy qua proxy, phải kiểm proxy upstream/registry manager theo quy trình quản trị.

Không cache Maven `settings.xml` chứa credentials, không dùng shared caches giữa untrusted PR và privileged release jobs nếu có nguy cơ cache poisoning/disclosure.

## 25. Checklist chẩn đoán theo thứ tự

1. Đọc đầy đủ error và chép **GAV, version, extension, classifier, repo ID/URL**.
2. Xác nhận artifact **đã publish thật**, POM/JAR (hoặc POM-only) tồn tại ở kho được phép.
3. Kiểm release vs SNAPSHOT, staging/publication state và credentials.
4. Kiểm settings profiles, mirrors, repository ID, `pluginRepositories` nếu plugin fail.
5. Xác định local repo path của **chính invocation lỗi**.
6. Tìm đúng `*.lastUpdated` trong folder GAV/version, đọc thông tin hỗ trợ đã redact.
7. Thử `mvn -U` một lần sau khi kiểm các điều kiện trên.
8. Nếu còn fail, xác định đây là local negative cache, remote 404, 401/403, TLS/network hay proxy cache.
9. Chỉ khi cần và đã review mới targeted purge hoặc cache cô lập.
10. Xác minh downloaded artifact/POM và project tests/runtime pass.
11. Ghi root cause để sửa workflow: publish dependency trước consumer, repository config, snapshot policy hoặc CI cache timing.

**Không giải quyết sự cố bằng cách xóa tất cả cache và tuyên bố đã khắc phục**, vì lỗi có thể tái diễn với GAV/repo sai.

## 26. Câu hỏi tự kiểm tra

**Q: `-U` có buộc Maven hỏi lại artifact release từng not found không?**  
Theo Apache Maven 3.x notes, nó giúp bypass cached resolution error và force check; không đồng nghĩa download lại mọi release JAR hợp lệ.

**Q: Xóa `.lastUpdated` có publish artifact vào repository không?**  
Không, nó chỉ thay local cache state.

**Q: `.lastUpdated` có luôn nghĩa là HTTP 404 ở thời điểm hiện tại không?**  
Không. Nó có thể phản ánh lần miss trước đó; xem remote và log hiện tại.

**Q: Vì sao có JAR local mà vẫn lỗi artifact descriptor?**  
POM hoặc parent/BOM cần thiết có thể không resolve được.

**Q: Vì sao public dependency chạy được còn internal artifact báo missing?**  
Có thể khác repository/profile/mirror/auth, không nhất thiết Maven bị hỏng.

**Q: Có nên chạy offline để bỏ qua miss?**  
Không; offline không tải được POM/JAR mới.

**Q: `_remote.repositories` có phải .lastUpdated không?**  
Không; nó là local repository tracking của nguồn artifact, không phải marker negative-cache cùng chức năng.

**Q: `maven-metadata.xml` khác .lastUpdated thế nào?**  
Metadata giúp version discovery/snapshot mapping; marker ghi trạng thái check/failure trong local resolver.

**Q: Maven 4 giống hoàn toàn Maven 3 không?**  
Không. Tài liệu Resolver có sự khác nhau về chính sách cache lỗi not found và khả năng điều chỉnh bằng CLI; không dùng cờ Maven 4 vào Maven 3.9.

## 27. Tài liệu chính thức

- [Apache Maven 3.x Compatibility Notes — Caching of Artifact Resolution Errors](https://cwiki.apache.org/confluence/spaces/MAVEN/pages/2852668/Maven+3.x+Compatibility+Notes): giải thích marker và `-U` sau lỗi cached.
- [Apache Maven Artifact Resolver — Local Repository](https://maven.apache.org/resolver/local-repository.html): `.lastUpdated`, classification of errors và default Maven 3 caching policy.
- [Apache Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html): local/remote repo và dependency download.
- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html): mirrors, profiles, server IDs và localRepository.
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html): repositories, dependency types, policies và plugins.
- [Apache Maven — Repository Layout](https://maven.apache.org/repositories/layout.html): GAV thành paths.
- [Apache Maven — Maven Metadata](https://maven.apache.org/repositories/metadata.html): snapshot metadata/version-level entries.
- [Apache Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): resolved versions/transitive graph.
- [Maven Dependency Plugin 3.8.1 — dependency:get](https://maven.apache.org/plugins-archives/maven-dependency-plugin-3.8.1/get-mojo.html): `artifact`/`transitive` parameters.
- [Maven Dependency Plugin 3.8.1 — purge-local-repository](https://maven.apache.org/components/plugins-archives/maven-dependency-plugin-3.8.1/purge-local-repository-mojo.html): `manualInclude`, `reResolve`, `resolutionFuzziness`.
- [Apache Maven — Purging Local Repository](https://maven.apache.org/components/plugins/maven-dependency-plugin/examples/purging-local-repository.html): phạm vi/xử lý purge.
- [Apache Maven — Guide to Using Mirrors](https://maven.apache.org/guides/mini/guide-mirror-settings.html): mirror IDs/patterns.
- [Apache Maven Help Plugin](https://maven.apache.org/plugins/maven-help-plugin/): effective-pom/effective-settings và diagnostic.

**Kết luận:** Khi Maven ghi “not found”, hãy **xác nhận artifact thật sự tồn tại ở remote đúng và có quyền tải**, rồi xem log/`.lastUpdated` trong **local repo chính xác**. `mvn -U` giúp retry cached miss đã lỗi thời nhưng không sửa sai GAV, auth, TLS, proxy server hoặc artifact chưa publish. Trước khi xóa cache, phân biệt POM/JAR, SNAPSHOT metadata, parent/BOM/plugins và các lớp cache client/CI/server. **Targeted diagnosis trước, targeted cleanup sau** là cách xử lý an toàn và có thể kiểm chứng.
