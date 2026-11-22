# Đối chiếu cấu hình Maven trên máy cá nhân với máy build (CI)

## 1. Vấn đề: cùng mã nguồn nhưng build khác kết quả

Một dự án Java có thể **build thành công trên laptop nhưng thất bại trên CI**, dù cả hai checkout cùng commit và sử dụng một `pom.xml`. Maven không chỉ đọc POM: kết quả còn phụ thuộc phiên bản Maven/JDK, file `settings.xml` ở máy hoặc người dùng, repository và mirror, profile đang bật, lệnh CLI, Maven Wrapper, toolchain, môi trường mạng, cache artifact và quyền của tài khoản chạy build.

Một số tình huống điển hình:

- Máy cá nhân đã có dependency hoặc plugin trong `~/.m2/repository`, còn agent CI mới không tải được chúng từ remote repository.
- Máy cá nhân có `settings.xml` khai báo mirror và credential hợp lệ; CI thiếu `server id` hoặc không nhận được token.
- Maven trên local chạy JDK 21, CI chạy JDK 17 trong khi POM và plugin yêu cầu một Java release cụ thể.
- Local dùng một profile settings/POM không được bật trên CI; dependency hoặc property hiệu lực khác nhau.
- Local gõ `mvn package -DskipTests`, CI chạy `./mvnw -B clean verify`. Hai lệnh thực thi các bước khác nhau.

**Mục tiêu đối chiếu** không phải sao chép nguyên file settings cá nhân lên CI. Mục tiêu là tìm những khác biệt có ý nghĩa, cố định phần cấu hình cần giống nhau, cho phép khác nhau đúng những chỗ cần thiết (như credential và endpoint theo môi trường) và bảo vệ dữ liệu bí mật.

Ba lớp đầu vào cần phân biệt:

1. **Cấu hình dự án:** `pom.xml`, parent POM, BOM, plugin, profile, `.mvn/maven.config`, `.mvn/jvm.config` và Maven Wrapper.
2. **Cấu hình môi trường:** global/user `settings.xml`, toolchains, `JAVA_HOME`, Maven/JDK cài đặt, proxy, certificate, DNS và local repository.
3. **Cấu hình lần chạy:** lệnh Maven, `-s`, `-gs`, `-P`, `-D`, `-o`, tùy chọn module, các biến môi trường và secrets được cung cấp cho job.

Chỉ nhìn thấy cùng POM hoặc cùng commit **không chứng minh effective settings, effective POM, classpath và đầu ra build đã giống nhau**.

## 2. Kiểm kê đúng các nguồn cấu hình

### 2.1. User settings và global settings

Maven có hai lớp settings thường gặp:

| File | Vị trí mặc định | Vai trò | Ghi đè đường dẫn |
| --- | --- | --- | --- |
| Global settings | `${maven.home}/conf/settings.xml` | Thiết lập dùng cho bản Maven được cài | `-gs` / `--global-settings` |
| User settings | `${user.home}/.m2/settings.xml` | Thiết lập theo tài khoản thực thi Maven | `-s` / `--settings` |

Maven kết hợp hai lớp này thành **effective settings**; user settings được ưu tiên khi các phần tương ứng có quy tắc ghi đè. File settings trong thư mục home của tài khoản chạy CI có thể khác file của người mở terminal hoặc người quản trị agent.

Khi dùng:

```bash
mvn -s ci/settings.xml clean verify
```

Maven sử dụng file đã chỉ định làm **user settings** cho lần gọi đó thay cho vị trí user settings mặc định; global settings của bản Maven vẫn có thể đóng góp cấu hình. `-s` không có nghĩa “trộn thêm một file settings thứ ba”. Đường dẫn `ci/settings.xml` chỉ là ví dụ, không mặc định tồn tại trong mọi repository.

**Không lưu secrets trong POM hoặc commit settings cá nhân vào Git.** User settings thường chứa cấu hình hạ tầng hoặc thông tin đăng nhập riêng môi trường; POM nên chứa thông tin về mô hình build có thể chia sẻ.

### 2.2. Các trường cần đối chiếu trong settings.xml

| Thành phần | Tác dụng | Khác biệt có thể tạo lỗi |
| --- | --- | --- |
| `<localRepository>` | Nơi lưu artifact, plugin và metadata đã tải | Cache local có artifact mà CI thiếu |
| `<mirrors>` | Đổi endpoint tải từ repository sang mirror/repository manager | CI tải từ host khác hoặc mirror thiếu artifact |
| `<servers>` | Xác thực theo `id` cho repository/mirror | 401/403 do token, quyền hoặc id không khớp |
| `<proxies>` | Kết nối qua proxy được cấu hình | Một máy kết nối được, máy kia bị chặn mạng |
| `<profiles>` | Đặt settings properties, repositories và pluginRepositories | Profile bật trên local nhưng không bật CI |
| `<activeProfiles>` | Chỉ rõ các profile settings kích hoạt | Các property và repository hiệu lực khác nhau |
| `<pluginGroups>` | Nhóm được tìm khi gọi plugin theo prefix | `mvn custom:goal` lỗi chỉ trên CI |
| `<offline>` | Cấm tải artifact qua mạng | Agent sạch gặp lỗi thiếu artifact |

Không phải mọi nội dung POM đều hợp lệ trong `settings.xml`. Settings profile chỉ hỗ trợ tập cấu hình phù hợp như properties, repositories và pluginRepositories; không đặt nguyên `<build><plugins>` vào settings profile rồi mong Maven sử dụng như POM.

### 2.3. Các yếu tố nằm ngoài settings.xml

- **Maven version và launcher:** `mvn -version`, Maven Wrapper `./mvnw -version`, `mvnw.cmd`.
- **JDK:** runtime Maven đang chạy, Compiler Plugin Java release, JDK được Maven Toolchains chọn khi có.
- **POM hiệu lực:** parent, profile, BOM, dependency, pluginManagement và executions.
- **Lệnh thực tế:** `clean verify` và `package` không tương đương; `-DskipTests`/`-Dmaven.test.skip` thay đổi kiểm thử.
- **Biến môi trường:** `JAVA_HOME`, `MAVEN_OPTS`, `MAVEN_ARGS` trong bản Maven hỗ trợ, các biến app/test và biến dùng để cấp credential.
- **Cache:** local repo ấm có thể che lỗi tải dependency/plugin; snapshot metadata cũng có thể khác theo thời điểm.
- **Container/CI:** image, truststore/CA, proxy/DNS, filesystem case sensitivity, timezone, locale, UID và mức tài nguyên.
- **Các cấu hình project-level:** `.mvn/maven.config` chứa Maven CLI arguments; `.mvn/jvm.config` chứa JVM arguments cho tiến trình chạy Maven, không tự thay đổi JVM của ứng dụng Java chạy sau build.

## 3. Xác lập điều kiện so sánh công bằng

Trước khi so settings, hãy xác nhận hai môi trường sử dụng **cùng commit**, **cùng phiên bản Maven/JDK được yêu cầu**, **cùng module** và **cùng lệnh build**. Ví dụ trên Linux/macOS, từ root repository có Wrapper được nhóm tin cậy:

```bash
git rev-parse HEAD
git status --short
./mvnw -version
./mvnw -B clean verify
```

Nếu dự án không có Wrapper, thay bằng `mvn` và ghi nhận version. Trên Windows PowerShell, dùng `.\mvnw.cmd`. Trước khi chạy Wrapper từ nguồn mới chưa được tin cậy, phải review script và nguồn tải. Lệnh `verify` có thể kích hoạt plugin hoặc kiểm thử tích hợp riêng của dự án, nên thực hiện trong phạm vi build được nhóm cho phép.

- `git rev-parse HEAD`: kiểm tra commit.
- `git status --short`: xem thay đổi chưa commit có thể khiến laptop khác CI.
- `-version`: cho biết Maven và Java runtime mà Maven thực sự chạy.
- `-B clean verify`: build mới ở batch mode, đi qua các phase tới `verify` theo những plugin goal đã cấu hình.

Khi điều tra lỗi, có thể bắt đầu bằng `validate` và các goal Maven Help Plugin để xem cấu hình trước khi thực hiện toàn bộ build. Đừng kết luận “settings khác” nếu thực tế local đang chạy `mvn test` tại module `app` nhưng CI chạy `mvn -B verify` từ aggregator.

## 4. Đọc cấu hình hiệu lực, thay vì chỉ mở file thô

### 4.1. Effective settings

```bash
mvn -B help:effective-settings
```

Goal `help:effective-settings` tính cấu hình settings mà Maven sử dụng sau khi kết hợp global và user settings. Nó giúp quan sát mirror, localRepository, pluginGroups, active profiles, repositories của settings và tình trạng offline.

Nếu dùng file user settings cụ thể:

```bash
mvn -s ci/settings.xml -B help:effective-settings
```

Khi cần lưu kết quả trong môi trường được bảo vệ:

```bash
mvn -B help:effective-settings -Doutput=effective-settings.xml
```

**Cảnh báo:** Help Plugin che mật khẩu theo mặc định, nhưng đầu ra có thể vẫn chứa hostname, URL nội bộ, tên tài khoản và giá trị cấu hình nhạy cảm. Không bật `-DshowPasswords=true` khi chia sẻ log/ticket. Không đưa file effective settings lên Git hoặc đăng diff nguyên văn nếu chưa kiểm tra và ẩn thông tin cần bảo vệ.

### 4.2. Effective POM và profile đang bật

```bash
mvn -B help:effective-pom
mvn -B help:active-profiles
```

`help:effective-pom` cho biết mô hình dự án sau inheritance, profile và các quy tắc Maven; xem version plugin, repository từ POM, dependencyManagement, goal execution, encoding, compiler release. Với Help Plugin hỗ trợ, `-Dverbose` có thể thêm chú thích nguồn gốc các cấu hình:

```bash
mvn -B help:effective-pom -Dverbose
```

`help:active-profiles` cho biết profile nào hoạt động theo POM, settings và cơ chế kích hoạt liên quan. Profile có thể được bật qua `-P` hoặc điều kiện JDK, OS, property, file. **Cùng effective settings không tự chứng minh cùng effective POM** nếu người dùng gọi CLI hoặc chọn profile khác nhau.

Cần rà soát đầu ra trước khi chia sẻ vì effective POM cũng có thể chứa URL nội bộ hoặc property nhạy cảm.

### 4.3. Maven/JDK và Toolchains

```bash
mvn -version
java -version
javac -version
```

Nếu dự án dùng Wrapper, `./mvnw -version` là bằng chứng phù hợp hơn về Maven runtime của project. JDK Maven đang chạy có thể **khác JDK mà Compiler Plugin sử dụng** nếu đã bật Maven Toolchains. Trong trường hợp đó, so cả `toolchains.xml` trên máy, Toolchains Plugin và Compiler Plugin Java release. Thuộc tính `maven.compiler.release=17` không có chức năng tự cài JDK 17.

## 5. Bảng đối chiếu an toàn cho nhóm

Đừng chỉ chạy `diff ~/.m2/settings.xml ci-settings.xml` rồi dán kết quả vào ticket: settings có thể chứa token, username, URL proxy, key và nhiều dữ liệu nội bộ. So sánh **ý nghĩa cấu hình sau khi đã che dữ liệu nhạy cảm**.

```text
TRƯỜNG                     MÁY CÁ NHÂN                MÁY BUILD / CI
Git commit                  same-commit                same-commit
Maven / Wrapper             same-approved-version      same-approved-version
JDK Maven runtime           17                         17
Java compiler release       17                         17
User settings source        user home                  CI generated temporary file
Global settings             approved installation      approved build image
Mirror id                   corp-mirror                corp-mirror
Mirror host                 approved endpoint          approved endpoint
Server id                   corp-mirror                corp-mirror
Credential source           credential manager         CI secret manager
Active profile ids          standard-build             standard-build
Local repository            warm cache                  isolated/controlled cache
Command                     clean verify               -B clean verify
```

Bảng chỉ là mẫu, **không mô tả một hệ thống có thật**. Có thể ghi mirror/repository ID và trạng thái khớp; không cần đưa token hoặc mật khẩu vào báo cáo. Hạn chế công bố đường dẫn workspace, hostname hoặc account nếu không cần thiết.

Một cách phân loại:

- **Có thể ghi trong báo cáo nội bộ đã duyệt:** Maven/JDK version, lệnh build, id profile, id plugin, các option không nhạy cảm.
- **Cần kiểm tra quyền chia sẻ:** URL/hệ thống nội bộ, username, local cache path, đường dẫn CA/truststore, tên service.
- **Không đưa vào diff và log:** password, token, private key, passphrase, biến môi trường chứa secrets.

## 6. Mirror, repository và xác thực: nguồn sai khác phổ biến

### 6.1. Mirror chọn lại đích tải

Maven có thể nhận repository từ settings profile, POM, parent/Super POM. Trước khi tải artifact, quy tắc `<mirrors>` được áp dụng để ánh xạ sang endpoint khác. Ví dụ minh họa dùng **tên miền .invalid không tồn tại thực tế**:

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <mirrors>
        <mirror>
            <id>corp-mirror</id>
            <url>https://artifacts.example.invalid/maven-public</url>
            <mirrorOf>external:*</mirrorOf>
        </mirror>
    </mirrors>
</settings>
```

`external:*` chọn các repository bên ngoài, ngoại trừ localhost và nguồn file theo ngữ nghĩa Maven. `*` chọn mọi repository id. CI có mirror rộng trong khi máy cá nhân không có có thể **truy cập những máy chủ hoàn toàn khác nhau** dù cùng POM.

Một mirror không tự hợp nhất nhiều repository. Nếu muốn một endpoint cung cấp nhiều upstream, cần repository manager được cấu hình proxy/group phù hợp. Với nhiều mirror có rule chồng lấn, Maven ưu tiên match chính xác id rồi áp dụng quy tắc chọn mirror; đừng dựa vào việc trùng rule để tự cân bằng tải.

### 6.2. Dependency và plugin dùng những đường cấu hình khác nhau

- `<repositories>`: nơi Maven phân giải dependency ứng dụng.
- `<pluginRepositories>`: nơi phân giải Maven plugin và các artifact phục vụ plugin.
- `<mirrors>`: thay endpoint tải cho repository được match.
- `<pluginGroups>`: chỉ định group để tìm khi gọi plugin theo prefix, không tự cấp thêm quyền truy cập mạng.

Một lỗi `Plugin ... could not be resolved` không nhất thiết do repository dependency khai báo sai. Cần kiểm tra pluginRepository, mirror, proxy, certificate và metadata liên quan plugin.

### 6.3. Credential và server id

Trong settings, cấu hình `<servers>` được ánh xạ bằng `<id>`. Nếu Maven tải qua mirror `corp-mirror`, credential thường phải được cấu hình với **id khớp endpoint được dùng**, chứ không đơn thuần là id gốc `central`.

Ví dụ **đoạn cấu hình** dùng biến môi trường CI, không chứa giá trị bí mật:

```xml
<servers>
    <server>
        <id>corp-mirror</id>
        <username>${env.MAVEN_REPO_USER}</username>
        <password>${env.MAVEN_REPO_PASSWORD}</password>
    </server>
</servers>
```

Cần bảo đảm CI thực sự cấp hai biến đó qua secret manager, id đúng, token chưa hết hạn và tài khoản có quyền với repository. **Không in biến môi trường hoặc bật log debug chứa credential để “kiểm chứng”.**

Lỗi **401** thường gợi ý xác thực không hợp lệ/thiếu; **403** thường gợi ý quyền truy cập hoặc chính sách từ chối. Mã HTTP đơn lẻ chưa đủ chốt nguyên nhân: vẫn cần kiểm tra endpoint, rule mirror, token và thông báo từ repository manager.

### 6.4. Proxy, TLS và chính sách mạng

CI có thể chạy bên trong container thiếu CA nội bộ, DNS khác, firewall khác hoặc proxy chưa khai báo. Maven mới hơn có chính sách mặc định hạn chế repository HTTP bên ngoài. Khi tải được trên laptop nhưng lỗi TLS ở CI, hãy cập nhật truststore/certificate đáng tin và cấu hình mạng đúng thay vì tắt xác minh TLS.

## 7. Profile và biến môi trường

Maven settings profile có thể khai báo **properties, repositories, pluginRepositories** và được kích hoạt bằng `activeProfiles` hoặc CLI `-P` phù hợp. Profile POM còn có thể tác động cấu hình plugin, dependency và build theo quy tắc riêng.

Ví dụ local có profile `developer` được kích hoạt trong settings và khai báo property `build.mode=dev`; CI bật `release` hoặc không bật profile nào. Nếu POM dùng property đó để filter tài nguyên, cùng source code vẫn tạo ra artifact khác nhau.

Một property có thể đến từ Maven CLI `-D...`, từ POM/settings profile hoặc được plugin đọc từ biến môi trường. Vì vậy phải ghi lại **lệnh thực tế + active profiles + effective POM/settings**. Không nên dùng settings cá nhân để quyết định tùy tiện các giá trị phát hành ảnh hưởng đến artifact nếu nhóm chưa thống nhất.

## 8. Cache và snapshot: vì sao “máy tôi chạy được” không đủ?

Local repository thường nằm dưới `~/.m2/repository` và có thể bị thay bằng `<localRepository>` hoặc `-Dmaven.repo.local`. Nó là cache artifact/metadata; một lần build thành công có thể chỉ vì artifact đã có sẵn.

Có thể kiểm tra tải lại trong một local repository mới, **chỉ khi được phép dùng repository/network và đủ dung lượng**:

```bash
mvn -B -Dmaven.repo.local=.mvn-local-check clean verify
```

Thư mục `.mvn-local-check` chứa cache vừa tải về; nên đưa vào ignore phù hợp, không commit artifact hoặc cache vào Git. Không xóa cache chính của cả máy chỉ để kiểm tra: việc đó tốn tài nguyên, có thể ảnh hưởng các dự án khác.

Với `SNAPSHOT`, version range hoặc artifact thay đổi theo metadata, hai lần build ở thời điểm khác nhau có thể lấy byte không giống nhau. Khi yêu cầu tái lập, kiểm soát chính sách phát hành và phiên bản dependency/plugin, xác minh nguồn artifact và không dựa vào việc cache máy cá nhân tình cờ còn artifact cũ.

## 9. Ví dụ Java 17: hai settings khác nhau tạo tài nguyên build khác nhau

Ví dụ dùng **hai file settings không có credential** để chứng minh rằng cùng POM và code Java có thể cho đầu ra khác khi settings profile khác. Đây là bài thực hành về phạm vi cấu hình, không phải khuyến nghị đóng gói artifact production khác nhau theo máy.

### 9.1. Cây thư mục

```text
settings-compare/
├── pom.xml
├── examples/
│   ├── local-settings.xml
│   └── ci-settings.xml
└── src/
    └── main/
        ├── java/demo/settings/App.java
        └── resources/build-origin.properties
```

Tệp `examples/local-settings.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <profiles>
        <profile>
            <id>local-env</id>
            <properties>
                <build.origin>LOCAL</build.origin>
            </properties>
        </profile>
    </profiles>
    <activeProfiles>
        <activeProfile>local-env</activeProfile>
    </activeProfiles>
</settings>
```

Tệp `examples/ci-settings.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <profiles>
        <profile>
            <id>ci-env</id>
            <properties>
                <build.origin>CI</build.origin>
            </properties>
        </profile>
    </profiles>
    <activeProfiles>
        <activeProfile>ci-env</activeProfile>
    </activeProfiles>
</settings>
```

Cả hai file chỉ khác profile id và giá trị property, không có mirror hay auth; không cần repository nội bộ để chạy ví dụ.

### 9.2. POM đầy đủ

Tệp `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>settings-compare</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <build>
        <resources>
            <resource>
                <directory>src/main/resources</directory>
                <filtering>true</filtering>
                <includes>
                    <include>build-origin.properties</include>
                </includes>
            </resource>
        </resources>
        <plugins>
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
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Maven Compiler Plugin dùng Java release 17, Resources Plugin xử lý file resource được filter. Tệp `src/main/resources/build-origin.properties`:

```properties
origin=${build.origin}
```

Giá trị `${build.origin}` được Maven thay trong phase xử lý resources; **nó không phải Java runtime expression**.

Tệp `src/main/java/demo/settings/App.java`:

```java
package demo.settings;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class App {
    private App() {
    }

    public static void main(String[] args) throws IOException {
        Properties props = new Properties();
        try (InputStream input =
                App.class.getResourceAsStream("/build-origin.properties")) {
            if (input == null) {
                throw new IllegalStateException("Missing build-origin.properties");
            }
            props.load(input);
        }
        System.out.println("Build origin: " + props.getProperty("origin"));
    }
}
```

### 9.3. Build với settings local

Từ thư mục `settings-compare/`, chạy với Maven/JDK phù hợp:

```bash
mvn -s examples/local-settings.xml -B clean package
java -cp target/classes demo.settings.App
```

Stdout **của lệnh `java` thứ hai** là:

```text
Build origin: LOCAL
```

Dùng goal sau để kiểm tra profile được bật:

```bash
mvn -s examples/local-settings.xml -B help:active-profiles
```

Ở lần này, profile có id `local-env` được kích hoạt và cung cấp `build.origin=LOCAL` cho resource filtering.

### 9.4. Build với settings CI

```bash
mvn -s examples/ci-settings.xml -B clean package
java -cp target/classes demo.settings.App
```

Stdout của **lệnh `java` thứ hai** là:

```text
Build origin: CI
```

Source code, POM, resource đầu vào không đổi. `-s` chọn settings khác, khiến giá trị property được filter vào `target/classes/build-origin.properties` khác; khi Java đọc file từ classpath, kết quả khác tương ứng.

`clean` xóa đầu ra cũ trước khi build để không lẫn resource của lần trước. Có thể kiểm tra `target/classes/build-origin.properties` sau mỗi lần chạy và `jar tf target/settings-compare-1.0.0.jar` để chắc chắn JAR chứa file này. `jar tf` chỉ liệt kê entry, không in nội dung file; muốn kiểm tra byte/nội dung artifact cần công cụ phù hợp.

**Ý nghĩa:** nếu mục tiêu của doanh nghiệp là artifact phải giống nhau trên mọi máy, hãy quản lý property ảnh hưởng tới artifact tại một nguồn thống nhất và kiểm thử tính tái lập. Settings cá nhân nên chứa những khác biệt môi trường được phê duyệt, không trở thành nguồn định nghĩa bí mật của hành vi sản phẩm.

## 10. Quy trình chẩn đoán có thứ tự khi CI đỏ và máy cá nhân xanh

1. **Xác nhận cùng commit, working tree sạch, cùng build goals và module selection.** Không so hai phiên chạy khác mục tiêu rồi kết luận settings là nguyên nhân.
2. **So Maven version và JDK.** Kiểm tra Wrapper, `mvn -version`, `JAVA_HOME`, Toolchains và compiler release.
3. **So effective settings sau khi đã bảo vệ secrets.** Đối chiếu mirror, server id, profile, proxy, offline, localRepository và nơi file settings được nạp.
4. **So effective POM/profile.** Kiểm tra phiên bản dependency/plugin, nguồn POM parent, Java release và property thực tế.
5. **Đối chiếu repository dependency và plugin riêng.** Nhận diện endpoint tải thực tế sau khi mirror, authentication và HTTP/TLS.
6. **Kiểm tra tác động cache.** Khi được phép, thử local repo tách biệt hoặc CI agent sạch thay vì dựa vào cache ấm.
7. **Phân loại lỗi theo giai đoạn.** Lỗi model/parent POM, plugin resolution, compilation, test discovery, runtime, hay artifact publishing có cách xử lý khác nhau.
8. **Sửa đúng lớp cấu hình.** Chính sách build → POM; Maven runtime → Wrapper; JDK → image/toolchain; mirror/token → settings và secret manager; lệnh → pipeline; môi trường test → setup fixture/service.
9. **Xác minh trong môi trường sạch.** Chạy lại cùng phiên bản/cùng commit, ghi các bằng chứng không nhạy cảm và bổ sung quy tắc kiểm chứng vào tài liệu dự án.

## 11. Tra cứu nhanh lỗi phổ biến

| Triệu chứng | Kiểm tra trước | Hướng khắc phục |
| --- | --- | --- |
| `Could not resolve dependencies` trên CI | Mirror, repositories, offline, cache, artifact version | Xác định endpoint và artifact có tồn tại, kiểm tra quyền/mạng |
| `Plugin ... could not be resolved` | PluginRepositories, mirror, local cache, repository manager | Sửa nguồn plugin/metadata; không chỉ thêm repository dependency |
| 401/403 trên CI | Server id, token, secret availability, quyền truy cập | Đồng bộ id và quyền với mirror/repository đang được sử dụng |
| Lỗi proxy/TLS | Proxy, certificate truststore, DNS, image, firewall | Cấu hình mạng/CA đáng tin; không tắt TLS tùy tiện |
| Lỗi Java release/bytecode | Maven JDK, Toolchains, Compiler Plugin, runtime JDK | Dùng đúng JDK và release/target |
| Khác số test | CLI `skipTests`, Surefire version, test discovery, profile | Xem lệnh và Surefire reports; không chỉ đọc BUILD SUCCESS |
| Chỉ máy cá nhân chạy được | Artifact chưa publish, cache cũ, settings riêng | Kiểm tra với cache sạch và repository chuẩn |
| Test fail theo timezone/locale | CI environment, encoding, file path, clock | Làm test độc lập hoặc kiểm soát môi trường |
| Plugin prefix chỉ nhận trên local | pluginGroups/metadata, Maven version | Dùng plugin group đúng hoặc tọa độ đầy đủ có version |
| Effective settings giống nhau nhưng artifact khác | Effective POM, CLI, JDK, plugin inputs, snapshots | Mở rộng đối chiếu, không quy lỗi chỉ vào settings |

## 12. Chính sách cấu hình và bàn giao

Một tổ chức nên phân định rõ:

- **Git:** POM, version plugin/dependency, Maven Wrapper đã kiểm chứng, cấu hình project-level không chứa bí mật.
- **CI image/pipeline:** JDK, lệnh build, module selection, môi trường test, proxy/CA, cache policy và các thông số cần tái lập.
- **Settings môi trường:** mirror, repositories, server id, proxy và những khác biệt được phê duyệt giữa máy cá nhân với CI.
- **Secret manager:** password, access token, private key, credential CI; không commit chúng vào file settings trong repository.
- **Báo cáo build:** Maven/JDK version, profile id, command, artifact/test summary, checksum nếu cần; các trường nhạy cảm phải được ẩn.

Mẫu kiểm chứng ngắn có thể lưu cho từng môi trường:

```text
Git commit:
Build command:
Maven / Wrapper version:
JDK running Maven:
Compiler release / toolchain:
User/global settings source:
Mirror and repository IDs (sanitized):
Active profile IDs:
Effective dependency/plugin versions:
Local repository and cache policy:
Network, proxy and CA policy:
Test summary:
Artifact checksum:
Approved differences:
```

Mục tiêu không phải làm hai máy giống hệt cấu trúc vật lý, mà là **đầu vào quan trọng được thống nhất hoặc mọi khác biệt đều được giải thích và quản lý**.

### Tài liệu chính thức

- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html)
- [Apache Maven — Settings Model](https://maven.apache.org/ref/3-LATEST/maven-settings/settings.html)
- [Apache Maven — Help Plugin: effective-settings](https://maven.apache.org/plugins/maven-help-plugin/effective-settings-mojo.html)
- [Apache Maven — Help Plugin: effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
- [Apache Maven — Help Plugin: active-profiles](https://maven.apache.org/plugins/maven-help-plugin/active-profiles-mojo.html)
- [Apache Maven — Using Mirrors for Repositories](https://maven.apache.org/guides/mini/guide-mirror-settings.html)
- [Apache Maven — Multiple Repositories](https://maven.apache.org/guides/mini/guide-multiple-repositories.html)
- [Apache Maven — Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains.html)
