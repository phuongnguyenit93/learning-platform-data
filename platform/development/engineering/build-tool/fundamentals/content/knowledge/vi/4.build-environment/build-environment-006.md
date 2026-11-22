# Thư mục cấu hình người dùng, thư mục cache và cấu hình cấp dự án

Khi chạy Gradle hoặc Maven, build tool không chỉ đọc mã nguồn và tệp mô tả build. Nó còn đọc cấu hình từ dự án, từ tài khoản người dùng đang chạy lệnh và từ môi trường của máy. Đồng thời, nó lưu nhiều dữ liệu đã tải hoặc đã tính toán vào các thư mục cache để những lần build sau nhanh hơn.

Các vị trí này có phạm vi và mục đích khác nhau. Cấu hình cấp dự án thường được chia sẻ qua Git để cả nhóm cùng sử dụng. Cấu hình người dùng thường phục vụ riêng cho một máy hoặc tài khoản, chẳng hạn thông tin truy cập repository nội bộ. Cache chứa dữ liệu có thể tái tạo hoặc tải lại. Đầu ra build là sản phẩm được tạo ra từ mã nguồn và cấu hình, ví dụ thư mục `build/` của Gradle hoặc `target/` của Maven.

Hiểu sự khác nhau giữa các vị trí này giúp xử lý lỗi build, kiểm soát dependency, tránh commit dữ liệu nhạy cảm và biết nên xóa hoặc giữ lại thư mục nào khi dọn môi trường.

## 1. Bốn phạm vi dữ liệu thường gặp

Có thể bắt đầu bằng cách phân loại dữ liệu mà build tool sử dụng:

| Phạm vi | Mục đích | Ví dụ |
|---|---|---|
| Cấu hình cấp dự án | Mô tả cách dự án được build và các quy tắc chung của nhóm | `settings.gradle(.kts)`, `build.gradle(.kts)`, `gradle.properties`, `pom.xml`, `.mvn/` |
| Cấu hình người dùng | Tùy chỉnh build theo tài khoản hoặc máy đang chạy | `~/.gradle/gradle.properties`, `~/.m2/settings.xml`, Maven `toolchains.xml` |
| Cache và dữ liệu tải về | Lưu dependency, build tool distribution, metadata hoặc kết quả có thể tái sử dụng | `~/.gradle/caches/`, `~/.gradle/wrapper/dists/`, `~/.m2/repository/` |
| Đầu ra build | Lưu lớp đã biên dịch, tài nguyên đã xử lý, báo cáo và artifact của project | `build/` trong Gradle, `target/` trong Maven |

Ví dụ, nếu một dependency không tải được, nguyên nhân có thể nằm ở khai báo repository của dự án, mirror/proxy trong cấu hình người dùng, kết nối mạng hoặc dữ liệu cache. Nếu ứng dụng chạy với cấu hình sai, cần xem cấu hình runtime và tham số được truyền vào tiến trình; xóa cache dependency thường không giải quyết vấn đề đó.

Một nguyên tắc hữu ích là xác định **ai sở hữu dữ liệu** và **dữ liệu có thể tạo lại hay không**:

- Dự án sở hữu cấu hình build dùng chung.
- Người dùng hoặc môi trường CI sở hữu cấu hình riêng, credential và đường dẫn cục bộ.
- Build tool quản lý cache và có thể tạo lại phần lớn dữ liệu trong đó.
- Task build tạo đầu ra; đầu ra thường có thể tái tạo từ đầu vào.

## 2. Thư mục Gradle User Home

Gradle dùng một thư mục người dùng gọi là **Gradle User Home**. Đây là nơi lưu cấu hình, cache, distribution của Gradle Wrapper, log daemon và dữ liệu dùng chung giữa nhiều dự án của cùng người dùng.

Mặc định, Gradle User Home thường là thư mục `.gradle` bên trong thư mục home của tài khoản:

```text
Linux/macOS:  ~/.gradle/
Windows:     %USERPROFILE%\.gradle\
```

Đường dẫn có thể được thay đổi bằng biến môi trường `GRADLE_USER_HOME` hoặc tùy chọn dòng lệnh `--gradle-user-home` (`-g`). Ví dụ:

```bash
# Linux/macOS
export GRADLE_USER_HOME="$HOME/.gradle-company"
./gradlew build
```

```powershell
# Windows PowerShell
$env:GRADLE_USER_HOME = "$env:USERPROFILE\.gradle-company"
.\gradlew.bat build
```

Khi đổi Gradle User Home, Gradle sẽ tìm cấu hình và cache ở vị trí mới. Nếu vị trí đó chưa có distribution hoặc dependency đã tải, lần build đầu có thể phải tải lại dữ liệu.

### 2.1. Những thành phần thường có trong Gradle User Home

Cấu trúc cụ thể thay đổi theo phiên bản Gradle và các tính năng được sử dụng, nhưng thường có những thành phần sau:

```text
~/.gradle/
├── caches/                 # dependency, metadata và dữ liệu cache của Gradle
├── daemon/                 # log và dữ liệu liên quan đến Gradle daemon
├── jdks/                   # JDK được Gradle provision trong một số cấu hình/toolchain
├── wrapper/
│   └── dists/              # Gradle distributions được Wrapper tải về
├── gradle.properties       # cấu hình Gradle ở phạm vi người dùng
├── init.gradle(.kts)       # init script, nếu người dùng có cấu hình
└── init.d/                 # các init script bổ sung, nếu có
```

Không phải máy nào cũng có đủ các mục này. Gradle chỉ tạo những thư mục cần thiết khi tính năng tương ứng được sử dụng.

**`caches/`** lưu dữ liệu Gradle có thể tái sử dụng, chẳng hạn metadata dependency, artifact đã tải, kết quả transform và dữ liệu build cache tùy cấu hình. Các thư mục con thường gắn với phiên bản Gradle hoặc định dạng cache, vì vậy không nên dựa vào một tên thư mục nội bộ cố định khi viết hướng dẫn vận hành.

**`daemon/`** chứa log và dữ liệu của Gradle daemon. Khi build gặp lỗi liên quan đến daemon, log có thể giúp xác định JVM, tham số khởi chạy hoặc lỗi xảy ra trong quá trình daemon hoạt động.

**`wrapper/dists/`** lưu các Gradle distribution mà Wrapper đã tải. Nhờ đó, lần chạy sau không phải tải lại cùng distribution nếu dữ liệu còn hợp lệ.

**`gradle.properties`** trong Gradle User Home là cấu hình người dùng. Nó có thể chứa property áp dụng cho nhiều dự án chạy bằng tài khoản đó, chẳng hạn cấu hình proxy, JVM args cho daemon hoặc property phục vụ môi trường cá nhân. Cần lưu ý rằng property ở phạm vi người dùng có thể ảnh hưởng đến build của nhiều repository.

**`init.gradle` và `init.d/`** cho phép người dùng hoặc tổ chức bổ sung logic cấu hình áp dụng khi Gradle khởi tạo. Ví dụ, tổ chức có thể dùng init script để cấu hình repository nội bộ hoặc quy tắc chung. Vì init script có thể tác động rộng đến mọi build của người dùng, khi debug cần kiểm tra cả những script này.

### 2.2. Cấu hình người dùng trong `gradle.properties`

Một tệp `~/.gradle/gradle.properties` có thể chứa các thuộc tính như:

```properties
org.gradle.jvmargs=-Xmx2g -Dfile.encoding=UTF-8
org.gradle.parallel=true

# Property riêng cho môi trường người dùng
companyRepositoryUrl=https://repo.example.com/maven-public
```

Build script có thể đọc project property nếu dự án được thiết kế để sử dụng nó. Tuy nhiên, không phải mọi thuộc tính trong tệp đều là cấu hình hợp lệ của Gradle core; property tùy biến chỉ có tác dụng khi build script hoặc plugin đọc nó.

Một tệp `gradle.properties` cũng có thể nằm ở thư mục gốc của dự án. Hai tệp này có phạm vi khác nhau:

- `project-root/gradle.properties`: cấu hình đi cùng dự án và thường được chia sẻ qua Git.
- `GRADLE_USER_HOME/gradle.properties`: cấu hình cá nhân, áp dụng cho các build của người dùng theo quy tắc ưu tiên property của Gradle.

Với nhiều nguồn định nghĩa, Gradle có quy tắc ưu tiên. Nói chung, giá trị truyền trực tiếp qua dòng lệnh có thể ghi đè giá trị trong tệp; `gradle.properties` ở Gradle User Home có độ ưu tiên cao hơn tệp cùng tên ở root project, và tệp ở Gradle installation có độ ưu tiên thấp hơn. Khi cần kết luận chính xác, hãy kiểm tra loại property và nguồn truyền vào thay vì chỉ tìm một dòng trong một tệp.

Không đưa password, access token hoặc private key vào tệp `gradle.properties` được commit. Nếu cần thông tin xác thực cho repository, hãy lấy từ biến môi trường hoặc secret store và bảo đảm log build không in giá trị bí mật.

### 2.3. Thư mục cache của Gradle khác gì build cache?

Hai khái niệm dễ bị nhầm là **dependency/cache nội bộ của Gradle** và **build cache**.

- Dependency cache lưu metadata và artifact dependency đã được phân giải/tải về. Nó giúp Gradle không phải tải lại mọi thư viện trong mỗi lần build.
- Build cache lưu đầu ra của những task được cấu hình và xác định là cacheable. Khi đầu vào giống nhau và điều kiện cache phù hợp, Gradle có thể khôi phục đầu ra mà không thực hiện lại task.

Build cache có thể dùng local cache hoặc remote cache nếu dự án cấu hình. Việc bật `org.gradle.caching=true` cho phép sử dụng build cache theo cấu hình hiện hành, nhưng không làm mọi task tự động trở thành cacheable. Task cần có mô hình input/output phù hợp và không được có hành vi phụ thuộc vào trạng thái bên ngoài không được khai báo.

Vì vậy, nếu dependency không tải được, cần xem dependency cache và repository. Nếu một task chạy lại dù đầu vào không đổi, cần xem build cache, khai báo task và lý do Gradle quyết định thực thi task.

## 3. Cấu hình cấp dự án của Gradle

Các tệp cấp dự án thường nằm ở root của Gradle build hoặc trong thư mục `gradle/`:

```text
project-root/
├── settings.gradle.kts
├── build.gradle.kts
├── gradle.properties
├── gradle/
│   ├── libs.versions.toml
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── gradlew
├── gradlew.bat
├── .gradle/                    # dữ liệu cục bộ của build, thường không commit
├── build/                      # đầu ra build, thường không commit
└── src/
```

**`settings.gradle(.kts)`** xác định cấu trúc build, root project, project con và một số chính sách phân giải plugin/dependency.

**`build.gradle(.kts)`** mô tả plugin, dependency, source set, toolchain, task và các quy tắc build của project tương ứng. Dự án nhiều module có thể có build file ở root và từng module.

**`gradle.properties`** ở root project chứa các Gradle property được chia sẻ cùng dự án. Chỉ nên đặt ở đây những giá trị phù hợp để mọi thành viên và CI cùng nhận.

**`gradle/libs.versions.toml`** là Version Catalog mặc định, dùng để khai báo alias và phiên bản plugin/dependency tập trung. Nó là tệp nguồn cấu hình được quản lý trong Git, không phải cache.

**`gradle/wrapper/gradle-wrapper.properties`** xác định Gradle distribution mà wrapper cần chạy. Script wrapper và tệp hỗ trợ đi cùng dự án giúp mọi người sử dụng đúng phiên bản.

### 3.1. Thư mục `.gradle/` ở root dự án

Thư mục `.gradle/` trong project root chứa dữ liệu trạng thái và cache cục bộ liên quan đến build của dự án. Nó có thể lưu metadata, trạng thái file, thông tin execution hoặc dữ liệu hỗ trợ tăng tốc. Đây là dữ liệu được Gradle tạo và quản lý, không phải nơi khai báo dependency hay cấu hình canonical của nhóm.

Không nhầm:

- `~/.gradle/`: Gradle User Home, được chia sẻ giữa nhiều dự án của người dùng.
- `project-root/.gradle/`: dữ liệu cục bộ gắn với một project/build cụ thể.
- `project-root/build/`: đầu ra task của project, ví dụ `.class`, tài nguyên đã xử lý, JAR và báo cáo.

Thư mục `.gradle/` ở root thường được bỏ qua trong Git. Nếu xóa, Gradle có thể cần tái tạo trạng thái hoặc thực hiện một số công việc lại trong lần build sau. Xóa nó không đồng nghĩa với xóa toàn bộ dependency cache dùng chung trong Gradle User Home.

## 4. Thư mục người dùng của Maven

Maven sử dụng thư mục cấu hình người dùng thường là `.m2` bên trong home directory:

```text
Linux/macOS:  ~/.m2/
Windows:     %USERPROFILE%\.m2\
```

Trong thư mục này, Maven thường tìm cấu hình người dùng và lưu local repository. Các vị trí phổ biến gồm:

```text
~/.m2/
├── repository/          # local repository: dependency/artifact đã tải hoặc cài đặt
├── settings.xml         # cấu hình Maven của người dùng
└── toolchains.xml       # khai báo các JDK/toolchain có thể sử dụng, nếu có
```

Tùy chọn cài đặt và cách tổ chức môi trường, có thể có thêm các tệp hoặc thư mục khác. `~/.m2` là thư mục mặc định theo home của người dùng, nhưng Maven cho phép thay đổi local repository và chỉ định tệp settings khác.

### 4.1. `settings.xml` ở cấp người dùng

Maven có hai phạm vi settings phổ biến:

- **Global settings**: nằm trong thư mục `conf/` của Maven installation.
- **User settings**: mặc định nằm tại `${user.home}/.m2/settings.xml`.

Maven hợp nhất global settings và user settings; cấu hình user có thể ghi đè cấu hình global tương ứng. Có thể chỉ định tệp settings khác khi chạy Maven bằng `-s` (user settings) hoặc `-gs` (global settings).

`settings.xml` có thể chứa:

- Mirror để chuyển các yêu cầu repository qua một máy chủ nội bộ.
- Server credentials để truy cập repository yêu cầu xác thực.
- Proxy cho kết nối mạng.
- Đường dẫn local repository.
- Profile và cơ chế kích hoạt profile ở phạm vi settings.

Ví dụ cấu hình local repository riêng:

```xml
<settings>
    <localRepository>D:/maven-cache/repository</localRepository>
</settings>
```

Ví dụ cấu hình mirror:

```xml
<settings>
    <mirrors>
        <mirror>
            <id>internal-mirror</id>
            <mirrorOf>*</mirrorOf>
            <url>https://repo.example.com/maven-public</url>
        </mirror>
    </mirrors>
</settings>
```

Nếu cấu hình server credentials, `<id>` của phần `<server>` cần khớp với id repository hoặc mirror mà Maven sử dụng. Không nên commit mật khẩu hoặc token thật trong settings được chia sẻ; hãy cung cấp chúng bằng secret store hoặc cơ chế an toàn của máy/CI.

### 4.2. `toolchains.xml`

Maven Toolchains cho phép project yêu cầu một loại công cụ cụ thể, thường là JDK, mà không phụ thuộc trực tiếp vào JDK đang dùng để khởi chạy Maven. Tệp `toolchains.xml` thường nằm trong thư mục cấu hình người dùng `.m2` và khai báo các toolchain đã cài trên máy.

Ví dụ rút gọn:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>21</version>
            <vendor>any</vendor>
        </provides>
        <configuration>
            <jdkHome>C:/Program Files/Java/jdk-21</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
```

Project có thể cấu hình Maven Toolchains Plugin hoặc plugin tương ứng để yêu cầu JDK phù hợp. Đường dẫn `jdkHome` phải tồn tại trên máy đang chạy build; vì vậy, `toolchains.xml` thường là cấu hình theo máy/người dùng, còn yêu cầu phiên bản toolchain nên được mô tả trong cấu hình dự án.

Điều này giúp phân biệt JDK chạy Maven và JDK dùng để compile/test. Nếu Maven được khởi chạy bằng JDK 21 nhưng project yêu cầu toolchain khác, build có thể dùng JDK được chọn qua toolchain cho các plugin hỗ trợ cơ chế này.

### 4.3. Local repository `~/.m2/repository`

Maven local repository là nơi lưu các artifact Maven đã tải từ remote repository và các artifact được cài đặt vào local repository, ví dụ bằng lệnh `mvn install`.

Một cấu trúc minh họa:

```text
~/.m2/repository/
└── org/
    └── junit/
        └── jupiter/
            └── junit-jupiter/
                └── 5.11.0/
                    ├── junit-jupiter-5.11.0.pom
                    └── junit-jupiter-5.11.0.jar
```

Đường dẫn bên trong repository được tổ chức theo tọa độ Maven như `groupId`, `artifactId` và `version`. Khi một project khai báo dependency, Maven tìm artifact phù hợp trong local repository trước; nếu chưa có hoặc cần cập nhật theo chính sách, Maven có thể truy cập remote repository để tải về.

Local repository không chỉ là cache tạm thời: nó còn chứa các artifact mà lập trình viên cài từ project khác trên máy bằng `mvn install`. Nếu xóa toàn bộ `repository/`, các artifact đã tải sẽ cần được tải lại và các artifact chỉ tồn tại ở local có thể không còn sẵn để project khác sử dụng.

Có thể thay local repository bằng phần tử `<localRepository>` trong `settings.xml`, hoặc truyền thuộc tính hệ thống `-Dmaven.repo.local=...` khi chạy Maven. Điều này hữu ích khi muốn dùng cache riêng cho CI job, ổ đĩa khác hoặc một môi trường thử nghiệm.

## 5. Cấu hình cấp dự án của Maven

Một Maven project thường có cấu trúc như sau:

```text
project-root/
├── pom.xml
├── .mvn/
│   ├── maven.config             # tùy chọn mặc định cho lệnh Maven của dự án
│   ├── jvm.config               # tùy chọn JVM chạy Maven
│   ├── extensions.xml           # extension cấp core, nếu có
│   └── wrapper/
│       └── maven-wrapper.properties
├── mvnw
├── mvnw.cmd
├── .mvn/wrapper/                # có thể có thêm tệp wrapper theo kiểu phân phối
├── .gitignore
├── src/
└── target/                      # đầu ra build, thường không commit
```

**`pom.xml`** mô tả project, dependency, plugin, properties, profile và quan hệ module/parent.

**`.mvn/maven.config`** chứa các tùy chọn dòng lệnh Maven mặc định áp dụng cho dự án theo cơ chế Maven hỗ trợ. Ví dụ, nhóm có thể cấu hình một số cờ chung để mọi lần gọi Maven từ root dự án đều sử dụng.

**`.mvn/jvm.config`** chứa các tham số JVM dùng khi Maven khởi chạy, chẳng hạn heap hoặc system property. Đây là cấu hình cho tiến trình Maven.

**`.mvn/extensions.xml`** khai báo Maven core extensions nếu dự án cần mở rộng hành vi của Maven ở cấp core. Extension có phạm vi ảnh hưởng rộng hơn một plugin thông thường, vì vậy cần được quản lý và xem xét cẩn thận.

**`.mvn/wrapper/`**, `mvnw` và `mvnw.cmd` thuộc Maven Wrapper, giúp chọn phiên bản Maven đã khai báo.

**`target/`** là thư mục đầu ra thường chứa bytecode, tài nguyên đã xử lý, báo cáo test và artifact. Nó không phải thư mục cấu hình.

### 5.1. Profile trong POM và profile trong settings

Maven hỗ trợ profile để điều chỉnh cấu hình theo điều kiện hoặc môi trường. Profile có thể được khai báo trong `pom.xml` hoặc trong `settings.xml`, nhưng phạm vi và cách chia sẻ khác nhau:

- Profile trong POM là một phần cấu hình dự án, có thể được chia sẻ qua Git.
- Profile trong settings thuộc môi trường người dùng hoặc Maven installation, thường dùng cho mirror, repository hoặc giá trị đặc thù của máy.

Có thể kích hoạt profile bằng `-P` khi chạy Maven, hoặc bằng điều kiện activation mà Maven hỗ trợ. Không nên đặt mọi cấu hình môi trường vào POM nếu nó chứa thông tin riêng tư hoặc chỉ đúng với một máy.

## 6. Thư mục cache và đầu ra build của từng công cụ

Cache và output đều có thể chiếm dung lượng, nhưng ý nghĩa khác nhau.

| Nội dung | Gradle | Maven |
|---|---|---|
| Dữ liệu người dùng | Gradle User Home, mặc định `~/.gradle/` | Maven user home, mặc định `~/.m2/` |
| Dependency đã tải | Cache trong Gradle User Home | Local repository, mặc định `~/.m2/repository/` |
| Build tool distribution của wrapper | `~/.gradle/wrapper/dists/` | Thường được lưu dưới `.m2/wrapper/dists/` theo cấu hình wrapper |
| Trạng thái/cache riêng của project | `project-root/.gradle/` | Maven chủ yếu dùng local repository chung và dữ liệu trong `target/`; plugin có thể có cache riêng |
| Đầu ra build | `project-root/build/` | `project-root/target/` |
| Cấu hình người dùng | `~/.gradle/gradle.properties`, init scripts | `~/.m2/settings.xml`, `toolchains.xml` |
| Cấu hình project | Settings/build scripts, `gradle.properties`, wrapper files | `pom.xml`, `.mvn/`, wrapper files |

Vị trí cụ thể có thể được thay đổi bằng tùy chọn hoặc cấu hình của công cụ. Bảng trên mô tả mặc định phổ biến để định hướng khi tìm file.

### 6.1. Cache dependency

Khi build lần đầu, Gradle hoặc Maven có thể phải tải plugin, dependency và metadata từ repository từ xa. Những dữ liệu này được lưu ở cache/local repository để các lần build tiếp theo có thể sử dụng lại.

Nếu build không truy cập được mạng, dữ liệu đã cache có thể giúp tiếp tục build trong một số trường hợp. Tuy nhiên, offline chỉ hoạt động khi tất cả plugin, dependency và metadata cần thiết đã có sẵn. Nếu thiếu một artifact, build sẽ thất bại thay vì tự tìm một nguồn khác.

Với Gradle, có thể yêu cầu chế độ offline:

```bash
./gradlew --offline build
```

Với Maven:

```bash
./mvnw -o verify
```

Các lệnh này không tải dependency mới. Chúng hữu ích khi kiểm tra xem cache hiện tại đã đủ hay chưa, nhưng không thay thế việc cấu hình repository hoặc chuẩn bị dependency cho môi trường build.

### 6.2. Build output

Gradle thường đặt đầu ra của project trong `build/`; Maven thường đặt đầu ra trong `target/`. Các thư mục này có thể chứa:

- Bytecode đã biên dịch.
- Tài nguyên đã copy hoặc filter.
- Kết quả kiểm thử và báo cáo.
- JAR/WAR hoặc artifact khác.
- File trung gian do plugin tạo.

Đầu ra build gắn với một project và có thể tái tạo bằng task/lifecycle tương ứng. Vì vậy, `build/` và `target/` thường được đưa vào `.gitignore`. Nếu dự án có yêu cầu lưu một artifact đặc biệt, hãy làm theo quy ước phát hành riêng thay vì commit toàn bộ output mặc định.

## 7. Cấu hình được đọc từ đâu và ưu tiên như thế nào?

Một build có thể nhận cùng một giá trị từ nhiều nguồn: tệp trong repository, tệp người dùng, biến môi trường, system property hoặc đối số dòng lệnh. Khi giá trị cuối cùng khác mong đợi, cần xác định nguồn nào đang thắng.

### 7.1. Với Gradle

Gradle có nhiều nguồn cấu hình:

- Tệp `settings.gradle(.kts)` và `build.gradle(.kts)` xác định cấu trúc và hành vi build.
- `gradle.properties` có thể nằm trong Gradle User Home, root project hoặc Gradle installation.
- Project property có thể truyền bằng `-Pname=value`.
- System property có thể truyền bằng `-Dname=value` hoặc qua cơ chế project property được Gradle hỗ trợ.
- Environment variable có thể được build script hoặc plugin đọc.

Với Gradle properties, các nguồn có thứ tự ưu tiên. Trong các trường hợp thông dụng, tham số project property từ dòng lệnh được ưu tiên hơn giá trị trong tệp; `gradle.properties` ở Gradle User Home được ưu tiên hơn tệp ở root project, và tệp trong Gradle installation có độ ưu tiên thấp hơn. Cần phân biệt project property với system property vì cú pháp và quy tắc ánh xạ khác nhau.

Ví dụ truyền một giá trị khi chạy:

```bash
./gradlew -PappVersion=2.0.0 build
```

Nếu build script đọc `appVersion`, giá trị `2.0.0` có thể được sử dụng cho lần build này mà không cần sửa file trong repository. Đây là cách phù hợp cho một số giá trị CI như version hoặc endpoint môi trường, miễn là dự án định nghĩa rõ property và giá trị không phải secret.

### 7.2. Với Maven

Maven kết hợp nhiều nguồn cấu hình:

- `pom.xml` và parent POM cung cấp mô tả dự án.
- Global `settings.xml` cung cấp cấu hình ở phạm vi Maven installation.
- User `settings.xml` cung cấp cấu hình ở phạm vi người dùng và có thể ghi đè phần tương ứng của global settings.
- Profile có thể được kích hoạt theo cấu hình hoặc bằng `-P`.
- System property có thể truyền bằng `-Dname=value`.
- Biến môi trường có thể được tham chiếu trong một số biểu thức và plugin.

Ví dụ truyền local repository khác cho một lần chạy:

```bash
./mvnw -Dmaven.repo.local=/tmp/maven-repository verify
```

Ví dụ dùng settings file riêng:

```bash
./mvnw -s ci-settings.xml verify
```

Tệp settings được chỉ định phải tồn tại trên máy/agent chạy build. Nếu CI tạo file này từ secret store, cần bảo đảm file không bị in nội dung vào log hoặc lưu trong artifact công khai.

Không nên suy luận rằng mọi cấu hình Maven đều được ghi trong POM. Mirror, proxy, credential và local repository thường đến từ settings hoặc môi trường; đây là lý do cùng một commit có thể hoạt động trên máy này nhưng thất bại trên máy khác.

## 8. Cách điều tra lỗi liên quan đến cấu hình và cache

Khi build có hành vi khác nhau giữa máy cá nhân và CI, hãy xác định vị trí dữ liệu trước khi xóa cache hoặc thay đổi build script.

### Trường hợp 1: Gradle dùng sai repository hoặc proxy

Kiểm tra lần lượt:

1. Repository được khai báo ở settings hoặc build script.
2. `~/.gradle/gradle.properties` có property proxy hoặc repository dành cho người dùng hay không.
3. Gradle init script trong `~/.gradle/init.gradle` hoặc `~/.gradle/init.d/` có thay đổi repository hay không.
4. Biến môi trường proxy và cấu hình mạng của máy/CI.
5. Log build để xác định URL repository thực tế đang được truy cập.

Nếu chỉ một người gặp lỗi, cấu hình trong Gradle User Home hoặc môi trường của người đó là một hướng kiểm tra quan trọng.

### Trường hợp 2: Maven tải dependency từ máy chủ không mong muốn

Kiểm tra:

1. `repositories` trong POM và parent POM.
2. Global và user `settings.xml`, đặc biệt phần `mirrors`.
3. Id của mirror/server và thông tin xác thực tương ứng.
4. Proxy hoặc biến môi trường trong môi trường chạy Maven.
5. Local repository có artifact cũ hoặc metadata cần cập nhật hay không.

Có thể dùng `-U` để yêu cầu Maven kiểm tra cập nhật cho các dependency SNAPSHOT và metadata liên quan theo quy tắc cập nhật. Không nên dùng tùy chọn này như cách sửa mọi lỗi dependency; trước hết cần xác nhận repository và quyền truy cập đúng.

### Trường hợp 3: Build lỗi sau khi đổi JDK hoặc build tool

Kiểm tra cả hai phiên bản:

- JDK chạy Gradle/Maven.
- Phiên bản Gradle/Maven được wrapper chọn.
- JDK toolchain hoặc compiler target mà project yêu cầu.
- Phiên bản plugin và dependency có tương thích hay không.

Với Gradle, có thể xem phiên bản Gradle và JVM đang dùng bằng:

```bash
./gradlew --version
```

Với Maven:

```bash
./mvnw --version
```

Các lệnh này giúp xác định build tool đang chạy trên Java nào và phiên bản tool nào được sử dụng. Nếu cần biết compiler toolchain cụ thể, hãy xem cấu hình và log của task/plugin tương ứng.

### Trường hợp 4: Build lỗi do cache hỏng hoặc metadata cũ

Chỉ xem xét làm mới cache sau khi đã xác định lỗi có liên quan đến dữ liệu cache. Ví dụ, artifact tải dở hoặc metadata bị hỏng có thể khiến build tiếp tục thất bại dù repository và credential đã đúng.

Các bước ít ảnh hưởng nên thử trước:

- Chạy lại build và xem lỗi có tái hiện hay không.
- Yêu cầu refresh dependency theo cơ chế của build tool khi nghi ngờ metadata cũ.
- Xóa đúng artifact hoặc cache con có vấn đề nếu đã xác định được vị trí.
- Chỉ làm sạch cache lớn hoặc toàn bộ thư mục người dùng khi hiểu dữ liệu nào sẽ phải tải/tạo lại.

Không xóa toàn bộ `~/.gradle` hoặc `~/.m2` như phản xạ đầu tiên. Việc đó có thể làm mất nhiều dependency đã tải, distribution wrapper, cấu hình người dùng và artifact chỉ tồn tại ở local, khiến build sau đó chậm hơn hoặc thất bại vì không còn dữ liệu cần thiết.

## 9. Quản lý dữ liệu trong Git và CI

Khi quyết định một tệp có nên commit hay không, hãy dựa vào vai trò của nó:

| Vị trí/tệp | Thường commit? | Lý do |
|---|---|---|
| Gradle settings/build scripts | Có | Là mô tả build được chia sẻ |
| Gradle wrapper scripts, JAR và properties | Có | Giúp mọi người dùng cùng phiên bản Gradle |
| Gradle Version Catalog | Có | Quản lý dependency/plugin của dự án |
| Gradle `gradle.properties` ở root | Thường có nếu chỉ chứa cấu hình chung, không có secret | Chia sẻ thuộc tính build |
| `~/.gradle/gradle.properties` và init scripts cá nhân | Không | Thuộc cấu hình người dùng/máy |
| `~/.gradle/caches/`, `~/.gradle/daemon/` | Không | Dữ liệu cục bộ do Gradle quản lý |
| Project `.gradle/` và `build/` | Thường không | Trạng thái cục bộ và đầu ra có thể tái tạo |
| Maven `pom.xml` | Có | Mô tả project và dependency |
| Maven Wrapper scripts và tệp wrapper cần thiết | Có | Thống nhất phiên bản Maven |
| `.mvn/maven.config`, `.mvn/jvm.config` dùng chung | Có nếu phù hợp với mọi môi trường | Cấu hình lệnh/JVM ở phạm vi dự án |
| `~/.m2/settings.xml`, `toolchains.xml` | Không | Cấu hình riêng của người dùng/máy, có thể chứa credential và đường dẫn cục bộ |
| `~/.m2/repository/` | Không | Local repository và cache artifact |
| Maven `target/` | Thường không | Đầu ra build có thể tái tạo |

Một số dự án có thể chọn cách khác, nhưng cần có lý do và quy ước rõ ràng. Đặc biệt, tệp dùng chung không nên chứa đường dẫn ổ đĩa chỉ tồn tại trên máy một thành viên hoặc token truy cập repository.

Trong CI, nên tách rõ:

- Cấu hình build được lấy từ repository.
- Credential được cấp qua secret store hoặc biến môi trường.
- Cache được lưu/khôi phục theo cơ chế CI, có khóa phù hợp với hệ điều hành, JDK, build tool và lock/config cần thiết.
- Output được tạo trong workspace và được publish như artifact ở bước phù hợp.

Cache CI giúp giảm thời gian tải dependency và build, nhưng không phải nguồn chân lý của dự án. Nếu cache bị thiếu, build đúng cấu hình vẫn phải có khả năng tạo lại dữ liệu từ repository và các đầu vào hợp lệ.

## 10. Ví dụ: cùng một dự án chạy trên máy cá nhân và CI

Giả sử nhóm có một dự án Gradle cần tải dependency từ repository công ty. Cách tổ chức hợp lý có thể là:

```text
Repository (được commit)
├── settings.gradle.kts       # cấu trúc build và repository policy
├── build.gradle.kts          # plugin, dependency, task
├── gradle.properties         # giá trị chung, không chứa secret
└── gradle/wrapper/           # phiên bản Gradle

Máy lập trình viên
└── ~/.gradle/
    ├── gradle.properties     # credential/proxy cá nhân nếu cần
    ├── caches/               # dependency và cache
    └── wrapper/dists/        # Gradle distribution đã tải

CI agent
└── GRADLE_USER_HOME/
    ├── gradle.properties     # được cấp an toàn từ secret/env nếu cần
    ├── caches/               # cache riêng hoặc được khôi phục từ CI cache
    └── wrapper/dists/        # distribution đã tải
```

Máy cá nhân và CI cùng lấy build script và wrapper từ một commit, nên dùng cùng phiên bản Gradle và cùng quy tắc build. Credential được cấp riêng theo môi trường. Cache có thể khác nhau nhưng chỉ ảnh hưởng hiệu năng và khả năng chạy offline; nó không nên làm thay đổi dependency hoặc artifact mà build được yêu cầu tạo ra.

Với Maven, mô hình tương tự: POM và Maven Wrapper được commit; `settings.xml` và toolchains được cấp cho người dùng/CI; local repository được lưu trong cache của từng môi trường; `target/` là đầu ra build.

## 11. Những câu hỏi nên đặt ra khi tìm một thư mục

Khi gặp một thư mục có tên `.gradle`, `.m2`, `caches`, `repository`, `build` hoặc `target`, hãy tự hỏi:

1. Thư mục này thuộc repository hay nằm trong home của người dùng?
2. Nó chứa cấu hình do con người quản lý hay dữ liệu build tool tự tạo?
3. Dữ liệu có được chia sẻ giữa nhiều dự án hay chỉ thuộc một project?
4. Nếu xóa, dữ liệu có thể được tải/tạo lại không? Có mất artifact cục bộ hoặc credential không?
5. CI có cần cache thư mục này không, hay chỉ cần publish đầu ra build?

Trả lời được các câu hỏi đó sẽ giúp chọn đúng nơi cấu hình, biết cách chia sẻ giữa nhóm và tránh thao tác dọn dẹp quá rộng.

## 12. Những điều cần ghi nhớ

- Cấu hình cấp dự án mô tả cách build chung và thường được commit cùng mã nguồn.
- Cấu hình người dùng phục vụ môi trường của một tài khoản/máy, có thể chứa proxy, credential hoặc đường dẫn cục bộ.
- Gradle User Home mặc định là `~/.gradle`; có thể thay đổi bằng `GRADLE_USER_HOME` hoặc `--gradle-user-home`.
- Maven user settings mặc định nằm trong `~/.m2/settings.xml`; local repository mặc định nằm trong `~/.m2/repository/`.
- Gradle dependency cache và build cache có mục đích khác nhau; Maven local repository chứa artifact đã tải và artifact cài đặt ở local.
- `project-root/.gradle/`, `build/` và `target/` là dữ liệu cục bộ/đầu ra build, thường không cần commit.
- Cache có thể tăng tốc build, nhưng cấu hình và dependency của dự án vẫn phải được mô tả rõ ràng để có thể tái tạo.
- Không xóa toàn bộ thư mục người dùng khi chưa xác định dữ liệu cần thiết; không commit secret hoặc cấu hình cá nhân vào repository.

Khi điều tra một build không ổn định, hãy phân biệt cấu hình của dự án, cấu hình của người dùng, cache và đầu ra. Sau đó kiểm tra nguồn giá trị thực tế mà Gradle hoặc Maven đang đọc. Cách tiếp cận này giúp tìm đúng nguyên nhân và giữ cho môi trường build có thể tái tạo giữa máy cá nhân, máy CI và các thành viên trong nhóm.
