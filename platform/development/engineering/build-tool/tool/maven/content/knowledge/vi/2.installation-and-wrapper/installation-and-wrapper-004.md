# Maven Home, thư mục người dùng và các vị trí cấu hình

Khi một dự án Maven chạy được trên máy A nhưng không chạy được trên máy B, nguyên nhân thường nằm ở **Maven được khởi chạy từ đâu**, **Maven đang đọc cấu hình của người dùng nào** hoặc **cấu hình nào được áp dụng cho dự án**. Ba vị trí dễ nhầm nhất là thư mục cài Maven (Maven Home), thư mục riêng của người dùng (thường là `~/.m2`) và thư mục `.mvn` nằm trong dự án.

Bài này tập trung vào cách nhận diện từng vị trí, vai trò của các tệp cấu hình, cách Maven sử dụng chúng và cách kiểm tra đường dẫn thực tế. Ví dụ chủ yếu áp dụng cho Maven 3.9.x; những điểm khác ở Maven 4 được nêu riêng.

## 1. Ba phạm vi cấu hình cần phân biệt

| Phạm vi | Vị trí điển hình | Vai trò |
| --- | --- | --- |
| **Installation / Maven Home** | `/opt/apache-maven-3.9.x` hoặc `C:\tools\apache-maven-3.9.x` | Nơi chứa chương trình Maven, script `bin/mvn`, thư viện và cấu hình **global** trong `conf/settings.xml`. |
| **User / User Home** | `${user.home}/.m2`, thường là `~/.m2` | Cấu hình riêng của người chạy Maven, như `settings.xml`, `toolchains.xml`, và bộ nhớ đệm dependency trong `repository/`. |
| **Project** | `pom.xml` và `.mvn/` dưới thư mục gốc dự án | Khai báo dự án và các tùy chọn chạy Maven có thể chia sẻ trong Git; thư mục `.mvn/wrapper/` lưu cấu hình Maven Wrapper. |

Một máy có thể cài **nhiều bản Maven**, nhiều người dùng trên máy có **nhiều thư mục `.m2` khác nhau**, còn mỗi repository Git có thể có `.mvn` riêng. Đây là ba khái niệm độc lập.

Sơ đồ ví dụ:

```text
/opt/apache-maven-3.9.x/            <- Maven Home (bản Maven đã cài)
├── bin/mvn
├── conf/settings.xml               <- global settings
└── lib/

/home/lan/.m2/                       <- User Maven directory
├── settings.xml                    <- user settings (nếu có)
├── toolchains.xml                  <- mô tả JDK/toolchain (nếu có)
└── repository/                     <- local repository mặc định

/home/lan/work/demo-app/             <- Project
├── pom.xml
├── mvnw                            <- wrapper script cho Linux/macOS
├── mvnw.cmd                        <- wrapper script cho Windows
└── .mvn/
    ├── maven.config
    ├── jvm.config
    ├── extensions.xml
    └── wrapper/maven-wrapper.properties
```

Các tệp tùy chọn trong sơ đồ không nhất thiết xuất hiện ở mọi dự án. Maven vẫn chạy được nếu không có `~/.m2/settings.xml` hoặc thư mục `.mvn`.

## 2. Maven Home: thư mục cài đặt Maven

**Maven Home** là thư mục gốc của một bản phân phối Apache Maven. Ví dụ, nếu giải nén Maven vào `C:\tools\apache-maven-3.9.x` thì script khởi chạy thường nằm tại `C:\tools\apache-maven-3.9.x\bin\mvn.cmd`, còn cấu hình toàn cục ở `C:\tools\apache-maven-3.9.x\conf\settings.xml`.

Các thành phần thường gặp:

- `bin/`: chương trình/script `mvn`, `mvn.cmd` và các script hỗ trợ.
- `conf/settings.xml`: **global settings**, mặc định ở cấp bản cài Maven.
- `lib/`, `boot/`: các thư viện Maven cần để vận hành. Không chỉnh sửa tùy tiện.
- `maven.home`: thuộc tính hệ thống Maven dùng để chỉ thư mục cài thực sự trong phiên chạy.

### Xác định Maven thực sự đang chạy

Trên Linux/macOS:

```bash
command -v mvn
mvn -version
```

Trên Windows PowerShell:

```powershell
Get-Command mvn
mvn -version
```

Trên Windows Command Prompt:

```bat
where mvn
mvn -version
```

Trong kết quả `mvn -version`, tìm dòng **Maven home:** để biết thư mục của phiên Maven đang chạy; đồng thời xem các dòng **Java version** và **Java home** để biết JVM được sử dụng. Đường dẫn và phiên bản hiển thị phụ thuộc máy, vì vậy không nên ghi nhớ một kết quả mẫu cố định.

Biến môi trường `MAVEN_HOME` thường được các script hoặc IDE dùng để tham chiếu nơi cài Maven. `M2_HOME` có thể xuất hiện trong hướng dẫn cũ, nhưng không nên xem nó là điều kiện bắt buộc cho mọi bản Maven hiện đại. `PATH` quyết định lệnh `mvn` nào được shell tìm thấy trước; vì thế việc đặt `MAVEN_HOME` đúng **chưa bảo đảm** đang thực thi bản Maven mong muốn. Luôn kiểm tra bằng `mvn -version`.

**Phân biệt với JDK:** `JAVA_HOME` trỏ tới JDK, trong khi Maven Home trỏ tới bản cài Maven. Chúng phục vụ hai mục đích khác nhau. Nếu sử dụng Maven Wrapper (`./mvnw` hoặc `mvnw.cmd`), dự án có thể khởi chạy một bản Maven riêng do Wrapper tải về, không nhất thiết là bản được tìm thấy bằng `mvn` trên `PATH`.

## 3. Thư mục người dùng: `${user.home}/.m2`

`user.home` là thuộc tính hệ thống Java chỉ thư mục home của tài khoản đang chạy Maven. Giá trị này thường tương ứng với:

| Hệ điều hành | Vị trí thường gặp |
| --- | --- |
| Linux | `/home/ten-nguoi-dung/.m2` |
| macOS | `/Users/ten-nguoi-dung/.m2` |
| Windows | `C:\Users\ten-nguoi-dung\.m2`, thường tương đương `%USERPROFILE%\.m2` |

Đây là **giá trị mặc định**, không phải đường dẫn cứng cho mọi máy. Máy CI, container, tiến trình chạy bằng tài khoản dịch vụ hoặc cấu hình JVM đặc biệt có thể dùng home khác tài khoản bạn đang đăng nhập. Ký hiệu `~` là cách shell biểu diễn home; trong cấu hình Maven/XML nên dùng đúng cú pháp thuộc tính `${user.home}` hoặc đường dẫn tuyệt đối khi cần.

Bên trong `.m2`, những mục quan trọng nhất là:

- `settings.xml`: cấu hình riêng của người dùng, ví dụ mirror, proxy, repository, profile, thông tin xác thực.
- `repository/`: **local repository** mặc định, nơi Maven lưu artifact đã tải và artifact được cài bằng các goal như `install`; đây không phải thư mục mã nguồn dự án.
- `toolchains.xml`: mô tả các JDK/công cụ được plugin chọn khi build, để có thể dùng JDK biên dịch khác với JDK đang chạy Maven.
- `wrapper/dists/`: vị trí Maven Wrapper thường lưu các bản phân phối Maven đã tải về (có thể thay đổi theo cấu hình Wrapper).

Không phải tất cả các tệp/thư mục đều tồn tại ngay sau khi cài Maven. `settings.xml` là tệp **tùy chọn**; nếu vắng mặt, Maven dùng cấu hình mặc định và các nguồn cấu hình khác.

### Local repository không phải Maven Home

Mặc định local repository ở:

```text
${user.home}/.m2/repository
```

Ví dụ dependency `org.slf4j:slf4j-api:2.0.17` có thể được lưu theo cấu trúc nhóm/tên/phiên bản:

```text
.m2/repository/org/slf4j/slf4j-api/2.0.17/
    slf4j-api-2.0.17.jar
    slf4j-api-2.0.17.pom
    ...
```

Maven dùng thư mục này làm cache và nơi lưu artifact cục bộ; các repository từ xa như Maven Central hoặc repository manager của doanh nghiệp là nguồn cung cấp artifact khác. Đổi `MAVEN_HOME` **không đồng nghĩa** đổi local repository. Cũng không nên đưa cả `.m2/repository` vào Git của dự án.

Muốn đổi local repository cho **một người dùng**, chỉnh `${user.home}/.m2/settings.xml`:

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <localRepository>/data/maven-cache</localRepository>
</settings>
```

Thay `/data/maven-cache` bằng đường dẫn tuyệt đối phù hợp và có quyền ghi; trên Windows có thể dùng `D:/maven-cache`. Muốn thay tạm thời cho **một lệnh** mà không sửa `settings.xml`:

```bash
mvn -Dmaven.repo.local=/data/maven-cache clean verify
```

Lệnh trên chỉ là ví dụ cho hệ thống có thư mục `/data/maven-cache`; người dùng Windows thay bằng đường dẫn trên máy mình. Không nhầm `-Dmaven.repo.local` với `MAVEN_HOME`.

## 4. Hai tệp `settings.xml`: global và user

Trong Maven 3, có hai vị trí chuẩn:

1. **Global settings:** `${maven.home}/conf/settings.xml`, dùng làm cấu hình cấp bản cài.
2. **User settings:** `${user.home}/.m2/settings.xml`, dùng làm cấu hình cấp tài khoản.

Maven kết hợp cấu hình hai nơi; khi có thuộc tính xung đột, **user settings được ưu tiên** theo quy tắc ghép settings. Đây không phải phép ghi đè toàn bộ tệp: các phần được hợp nhất theo ngữ nghĩa của chúng. Bởi vậy, không nên đoán kết quả chỉ bằng cách nhìn một tệp; hãy kiểm tra **effective settings**.

`settings.xml` phù hợp để chứa:

- `<localRepository>`: nơi lưu artifact cục bộ.
- `<mirrors>`: chuyển yêu cầu repository tới mirror/repository manager.
- `<proxies>`: cấu hình proxy cho mạng.
- `<servers>`: dữ liệu truy cập repository/server theo `id`, không đưa mật khẩu thật vào `pom.xml`.
- `<profiles>` và `<activeProfiles>`: một số tùy chọn repository và property phụ thuộc môi trường.

Những khai báo mang tính **bản chất dự án** như coordinates, dependencies, plugin, lifecycle, thông tin phát hành nên ở `pom.xml` hoặc POM cha được dùng chung, thay vì giấu trong settings chỉ có trên một máy.

### Ví dụ: người phát triển truy cập repository nội bộ

Ví dụ cấu hình trong `~/.m2/settings.xml`, với URL và tên biến môi trường mang tính minh họa:

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <mirrors>
        <mirror>
            <id>company-mirror</id>
            <name>Company Maven mirror</name>
            <url>https://repo.example.com/repository/maven-public/</url>
            <mirrorOf>central</mirrorOf>
        </mirror>
    </mirrors>
    <servers>
        <server>
            <id>company-mirror</id>
            <username>${env.COMPANY_MAVEN_USER}</username>
            <password>${env.COMPANY_MAVEN_TOKEN}</password>
        </server>
    </servers>
</settings>
```

Ý nghĩa:

- `mirrorOf=central` yêu cầu Maven dùng mirror này thay cho repository có id `central`. Muốn thay các repository khác cần cân nhắc lại mẫu `mirrorOf`.
- `servers/server/id` phải khớp với id repository/mirror cần xác thực; ở ví dụ là `company-mirror`.
- `${env.COMPANY_MAVEN_USER}` và `${env.COMPANY_MAVEN_TOKEN}` lấy giá trị từ môi trường tại thời điểm chạy. URL `repo.example.com` chỉ là ví dụ, phải thay bằng endpoint thực tế.
- Không commit `settings.xml` chứa credential vào repository. Với CI, dùng cơ chế quản lý bí mật của nền tảng CI.

Nếu không có mirror nội bộ, proxy hay nhu cầu riêng, phần cấu hình trên **không cần thiết**.

### Chỉ định tệp settings khác khi chạy

```bash
# Thay user settings cho lần chạy này
mvn -s /path/to/custom-settings.xml validate

# Thay global settings cho lần chạy này (tùy CLI Maven)
mvn -gs /path/to/global-settings.xml validate
```

`-s` (`--settings`) và `-gs` (`--global-settings` trong Maven 3) giúp chọn tệp cụ thể. Maven cần dự án/POM phù hợp để chạy goal `validate`; các đường dẫn trong ví dụ cần thay bằng tệp có thật.

**Ghi chú phiên bản:** Maven 4 có thể đọc thêm `.mvn/settings.xml` ở gốc dự án. Tệp settings chia sẻ theo dự án này chỉ chấp nhận những mục phù hợp phạm vi dự án; Maven bỏ qua các cấu hình gắn với cá nhân như `localRepository` và thông tin xác thực. Với Maven 3, không mặc định cho rằng `.mvn/settings.xml` thay được `~/.m2/settings.xml`.

## 5. `pom.xml` và `.mvn/`: cấu hình theo dự án

`pom.xml` là **Project Object Model**. Nó mô tả dự án cần build: `groupId`, `artifactId`, `version`, dependencies, plugins, modules, repositories, build profiles… Tệp này thuộc mã nguồn dự án và thường được commit vào Git.

Thư mục **`.mvn/`** nằm ở gốc dự án hoặc gốc dự án nhiều module, chứa các tệp tác động đến *cách khởi chạy Maven* cho dự án:

| Tệp | Tác dụng | Ví dụ |
| --- | --- | --- |
| `.mvn/maven.config` | Các **tham số dòng lệnh Maven** dùng chung. | `-B` (batch mode), `--fail-at-end`. |
| `.mvn/jvm.config` | Các **tùy chọn JVM chạy Maven**, không phải goal Maven. | `-Xmx1g`, `-Dfile.encoding=UTF-8`. |
| `.mvn/extensions.xml` | Khai báo core extensions cần tải và khởi tạo Maven. | Extension được cấu hình bằng Maven coordinates. |
| `.mvn/wrapper/maven-wrapper.properties` | Chọn bản phân phối Maven mà **Wrapper** tải/sử dụng. | `distributionUrl`. |

Ví dụ `.mvn/maven.config` trong Maven 3.9+:

```text
-B
--fail-at-end
```

Mỗi tham số nằm trên một dòng. Lưu ý: bắt đầu từ Maven 3.9.0, các đối số trong `maven.config` phải được đặt riêng từng dòng; việc viết nhiều đối số trên cùng một dòng như ở một số ví dụ Maven cũ dễ gây lỗi.

Ví dụ `.mvn/jvm.config`:

```text
-Xmx1g
-Dfile.encoding=UTF-8
```

`-Xmx1g` giới hạn heap tối đa cho JVM chạy Maven; nó **không tự động** đặt heap cho mọi tiến trình test hoặc ứng dụng Java được plugin khởi tạo riêng. Các lựa chọn JVM trong `MAVEN_OPTS` và `.mvn/jvm.config` có thể tác động cùng một phiên; khi trùng tùy chọn, thứ tự ưu tiên phụ thuộc phiên bản Maven, nên kiểm tra phiên bản và tài liệu tương ứng thay vì suy đoán.

**Không nhầm `.mvn` với `.m2`**: `.mvn` thuộc **repository dự án**, thường chia sẻ qua Git; `.m2` thuộc **tài khoản người dùng**, thường không chia sẻ.

## 6. Maven Wrapper và quan hệ với các thư mục

Maven Wrapper gồm script ở gốc dự án (`mvnw`, `mvnw.cmd`) và cấu hình trong `.mvn/wrapper/maven-wrapper.properties`. Khi chạy:

```bash
./mvnw -version
./mvnw clean verify
```

trên Linux/macOS, hoặc trong PowerShell ở Windows:

```powershell
.\mvnw.cmd -version
.\mvnw.cmd clean verify
```

Wrapper dùng phiên bản Maven được mô tả bởi `distributionUrl`; nếu cần, nó tải bản phân phối đó trước khi thực thi. Bản tải về thường được lưu dưới `~/.m2/wrapper/dists`, chứ không tự thay đổi bản `mvn` cài sẵn trên `PATH`. Với các loại Wrapper mới như `only-script`, dự án có thể **không có** `maven-wrapper.jar`; thiếu JAR không mặc nhiên là lỗi.

Wrapper giúp đồng nhất **phiên bản Maven** giữa máy phát triển và CI, nhưng vẫn cần JDK phù hợp. Nó cũng không biến user settings của người A thành user settings của người B. Hai người chạy cùng `mvnw` có thể vẫn dùng mirror, credential hoặc local repository khác nhau vì có `~/.m2/settings.xml` khác nhau.

Khi cần đối chiếu, chạy lần lượt `mvn -version` và `./mvnw -version` (hoặc `.\mvnw.cmd -version`) **trong cùng dự án**. Hai lệnh có thể in phiên bản và Maven Home khác nhau; đó là dữ liệu xác định bản thực thi, không phải bằng chứng lỗi.

## 7. Biến môi trường liên quan và vị trí của chúng

| Biến/thuộc tính | Điều khiển điều gì? | Cần nhớ |
| --- | --- | --- |
| `PATH` | Cách shell tìm lệnh `mvn`. | Có nhiều bản Maven thì thứ tự thư mục trên `PATH` rất quan trọng. |
| `MAVEN_HOME` | Tham chiếu bản cài Maven trong một số script/công cụ. | Không phải tên của `~/.m2`; luôn xác nhận bằng `mvn -version`. |
| `JAVA_HOME` | JDK mà Maven launcher sử dụng khi được cấu hình theo JDK này. | Khác Maven Home; kiểm tra `Java home` ở `mvn -version`. |
| `MAVEN_OPTS` | Tùy chọn JVM chạy Maven. | Ví dụ `-Xmx1g`; không đặt goal `verify` ở đây. |
| `MAVEN_ARGS` | Tham số cho Maven CLI từ Maven 3.9.0+. | Ví dụ `-B`; khác với JVM option. |
| `maven.repo.local` | Thuộc tính xác định local repository cho phiên build. | Có thể truyền bằng `-Dmaven.repo.local=...`. |
| `user.home` | Home do JVM xác định. | Là cơ sở cho `${user.home}/.m2` mặc định. |

Nếu IDE dùng Maven đi kèm hoặc Maven Wrapper trong khi terminal dùng bản cài toàn hệ thống, cấu hình “Maven Home” trong IDE có thể khác `command -v mvn`. Khi chẩn đoán, kiểm tra **công cụ thực thi đang được IDE/CI chọn**, thay vì chỉ nhìn một biến môi trường.

## 8. Kiểm tra cấu hình hiệu lực theo thứ tự

Giả sử bạn vừa thay mirror hoặc thư mục local repository nhưng Maven vẫn tải artifact từ vị trí cũ. Thực hiện quy trình sau trong thư mục dự án:

**Bước 1 — Xác định Maven và JDK được dùng.**

```bash
mvn -version
```

Nếu dự án có Wrapper, thử thêm `./mvnw -version` (Linux/macOS) hoặc `.\mvnw.cmd -version` (Windows PowerShell). Xác nhận đúng Maven Home, phiên bản Maven và Java home.

**Bước 2 — Xác định home của tài khoản chạy Maven.**

- Linux/macOS: `echo "$HOME"` thường cho biết home của shell hiện tại.
- Windows PowerShell: `$env:USERPROFILE` thường cho biết thư mục hồ sơ người dùng.
- Nếu chạy bằng CI, container hoặc JVM có thiết lập riêng, hai giá trị trên có thể không trùng với thuộc tính Java `user.home`. Khi đó cần xem môi trường/tiến trình chạy Maven thực tế.

**Bước 3 — Xác định tệp settings có hiệu lực.**

```bash
mvn help:effective-settings
```

Goal này hiển thị cấu hình sau khi Maven tổng hợp các nguồn settings tương ứng. Maven Help Plugin có thể cần được tải ở lần chạy đầu nếu chưa có trong local repository. Mật khẩu được ẩn theo mặc định, nhưng vẫn nên rà soát thông tin nhạy cảm trước khi chia sẻ log.

Đối chiếu `localRepository`, `mirrors`, `servers` và `activeProfiles` với kỳ vọng. Nếu lệnh build có thêm `-s` hoặc `-gs`, nhớ dùng **cùng các tham số đó** khi kiểm tra; nếu không, bạn đang so sánh hai phiên cấu hình khác nhau.

**Bước 4 — Phân biệt cấu hình dự án với cấu hình người dùng.**

- Kiểm tra `pom.xml` khi dependency/plugin/repository khai báo ở mức dự án có vấn đề.
- Kiểm tra `.mvn/maven.config` khi Maven luôn nhận thêm flag.
- Kiểm tra `.mvn/jvm.config`/`MAVEN_OPTS` khi JVM báo thiếu heap hoặc có lỗi khởi động.
- Kiểm tra `.mvn/wrapper/maven-wrapper.properties` khi Wrapper chọn sai bản Maven.
- Kiểm tra `~/.m2/settings.xml` và global `conf/settings.xml` khi mirror, proxy, credential hoặc local repository không đúng.

**Bước 5 — Chỉ sửa đúng cấp cấu hình.** Thay user settings nếu vấn đề chỉ xảy ra ở một người; thay dự án khi quy tắc build cần được chia sẻ; thay global settings khi quản trị viên thực sự muốn áp dụng cho bản Maven cài đó. Chạy lại lệnh build và đối chiếu kết quả.

## 9. Những lỗi thường gặp

1. **Đặt `settings.xml` vào sai chỗ.** Với Maven 3, `project/.mvn/settings.xml` không phải đường dẫn user settings mặc định; dùng `~/.m2/settings.xml` hoặc chỉ định `-s`. Maven 4 có hỗ trợ project settings nhưng giới hạn loại cấu hình.
2. **Chỉ đổi `MAVEN_HOME` rồi tưởng `mvn` tự đổi phiên bản.** Shell vẫn có thể lấy script từ bản Maven khác trên `PATH` hoặc IDE/Wrapper dùng bản riêng.
3. **Lẫn `JAVA_HOME` và Maven Home.** JDK dùng để chạy Maven là sản phẩm khác với bản phân phối Maven.
4. **Sửa `conf/settings.xml` rồi chuyển máy.** Đây là cấu hình của bản cài cụ thể; khi nâng cấp/giải nén Maven sang thư mục mới, chỉnh sửa cũ không tự đi theo.
5. **Cho rằng `.m2/repository` chứa cấu hình Maven.** Nó chủ yếu là nơi lưu artifact; mirror, proxy và credential được cấu hình qua settings.
6. **Dùng `~` hoặc đường dẫn tương đối trong `localRepository`.** Hãy dùng đường dẫn tuyệt đối hoặc biểu thức thuộc tính Maven được hỗ trợ như `${user.home}`; tránh giả định XML tự mở rộng ký hiệu shell.
7. **Sai id ở `servers`.** Thông tin xác thực gắn theo id của repository/mirror; id không khớp thường gây lỗi xác thực dù đã nhập tài khoản.
8. **Đưa secret vào `pom.xml` hoặc Git.** Thông tin theo tài khoản nên nằm trong user settings/secret của CI; không đưa token vào cấu hình dự án công khai.
9. **Xóa toàn bộ `~/.m2` để sửa mọi lỗi.** Việc này có thể xóa cấu hình, toolchains và cache, khiến các bản build phải tải lại rất nhiều artifact. Chỉ xử lý artifact/cache cụ thể khi đã xác định vấn đề.
10. **So sánh kết quả ở hai môi trường khác nhau.** Terminal, IDE, container và CI có thể chạy bằng người dùng, JDK hoặc bản Maven khác nhau.

## 10. Tự kiểm tra kiến thức

**Tình huống A:** Hai lập trình viên clone cùng một dự án có `pom.xml` và `mvnw` giống nhau; một người tải dependency qua repository nội bộ, người kia tải trực tiếp từ Maven Central. Hãy kiểm tra `~/.m2/settings.xml`, mirror và tài khoản chạy Maven trên từng máy trước khi kết luận `pom.xml` khác nhau.

**Tình huống B:** Muốn tất cả thành viên cùng dùng `-B` khi build dự án, đặt cờ này trong `.mvn/maven.config`. Muốn đặt heap cho JVM chạy Maven, sử dụng `.mvn/jvm.config` hoặc cấu hình JVM tương ứng, không đặt `-Xmx` thành Maven goal.

**Tình huống C:** Khi chạy `mvn` thấy Maven Home tại `C:\tools\apache-maven-A`, còn `.\mvnw.cmd` cho Maven Home khác. Đây có thể là hành vi bình thường: `mvn` dùng bản trên `PATH`, Wrapper dùng bản phân phối được cấu hình trong dự án.

## Tài liệu tham khảo chính thức

- [Apache Maven – Configuring Maven](https://maven.apache.org/configure.html): `MAVEN_OPTS`, `MAVEN_ARGS`, `.mvn/maven.config`, `.mvn/jvm.config`, extensions.
- [Apache Maven – Settings Reference](https://maven.apache.org/settings.html): global/user settings, mirror, proxy, server, profile, local repository.
- [Apache Maven – Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains.html): `toolchains.xml` và JDK toolchains.
- [Apache Maven Wrapper](https://maven.apache.org/tools/wrapper/): Wrapper, `distributionUrl` và bộ nhớ đệm bản phân phối.
- [Apache Maven Help Plugin – effective-settings](https://maven.apache.org/plugins/maven-help-plugin/effective-settings-mojo.html): xem cấu hình settings thực sự được tổng hợp.
