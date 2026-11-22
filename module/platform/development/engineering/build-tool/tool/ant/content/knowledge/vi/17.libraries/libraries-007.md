# Cấu hình resolver, repository và cache bằng `ivysettings.xml`

Apache Ant có thể gọi Apache Ivy để giải quyết dependency Java. Ivy cần biết lấy metadata và tệp JAR từ đâu, thử những nguồn nào trước, xác thực với repository riêng ra sao và lưu các artifact đã tải ở đâu. Những quy tắc này được cấu hình trong tệp `ivysettings.xml`.

`ivysettings.xml` mô tả **cách tìm và lấy dependency**. Danh sách thư viện mà một module cần thường được khai báo trong `ivy.xml`. Hai tệp có vai trò khác nhau: một tệp mô tả dependency của dự án; tệp còn lại mô tả các resolver, repository và cache được dùng để tìm dependency đó.

## 1. Phân biệt `ivy.xml` và `ivysettings.xml`

Một dự án có thể dùng cấu trúc:

```text
inventory-app/
├── build.xml
├── ivy.xml
├── ivysettings.xml
├── src/
│   └── main/java/
└── build/
```

| Tệp | Trách nhiệm |
|---|---|
| `ivy.xml` | Khai báo module hiện tại, các configuration và dependency cần thiết |
| `ivysettings.xml` | Khai báo resolver, repository, thứ tự tìm kiếm, cache và thông tin truy cập nguồn riêng |
| `build.xml` | Gọi các task Ivy như `settings`, `resolve`, `cachepath` hoặc `retrieve`, rồi dùng kết quả trong các task Ant khác |

Ví dụ `ivy.xml` khai báo ứng dụng cần thư viện JSON và logging:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<ivy-module version="2.0">
    <info organisation="com.example" module="inventory-app"/>

    <configurations>
        <conf name="compile" description="Dependencies needed to compile"/>
        <conf name="runtime" extends="compile" description="Runtime dependencies"/>
        <conf name="test" extends="runtime" description="Test dependencies"/>
    </configurations>

    <dependencies>
        <dependency org="com.fasterxml.jackson.core"
                    name="jackson-databind"
                    rev="2.17.2"
                    conf="compile->default"/>
        <dependency org="org.slf4j"
                    name="slf4j-api"
                    rev="2.0.16"
                    conf="runtime->default"/>
    </dependencies>
</ivy-module>
```

Tệp này nêu rõ dependency và phiên bản mà module yêu cầu. Ivy sẽ dùng cấu hình resolver trong `ivysettings.xml` để tìm metadata và artifact tương ứng.

## 2. Các khái niệm chính trong `ivysettings.xml`

| Thành phần | Vai trò |
|---|---|
| Settings | Chọn resolver mặc định và các thiết lập chung |
| Resolver | Quy tắc tìm metadata và artifact của một dependency |
| Repository | Nơi lưu metadata và binary, ví dụ Maven repository hoặc thư mục nội bộ |
| Resolver chain | Thử nhiều resolver theo thứ tự được khai báo |
| Cache | Lưu metadata, kết quả phân giải và artifact tải về trên máy hoặc trong vùng cache được cấu hình |
| Credentials | Cung cấp thông tin xác thực khi truy cập repository yêu cầu đăng nhập |
| Module routing | Chọn resolver riêng cho một tổ chức hoặc module cụ thể |

Repository là nơi chứa dependency; resolver là cơ chế Ivy dùng để truy cập và tìm dependency trong nguồn đó. Cache là vùng lưu cục bộ giúp tránh tải lại dữ liệu không cần thiết trong các lần build tiếp theo.

## 3. Tệp settings tối thiểu dùng Maven repository

Ivy có resolver `ibiblio` để truy cập repository tương thích Maven. Ví dụ sau dùng Maven Central:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<ivysettings>
    <settings defaultResolver="central"/>

    <resolvers>
        <ibiblio name="central"
                 m2compatible="true"
                 root="https://repo.maven.apache.org/maven2/"/>
    </resolvers>

    <caches defaultCacheDir="${user.home}/.ivy2/cache"/>
</ivysettings>
```

Giải thích:

- `<settings defaultResolver="central"/>` chọn resolver tên `central` làm resolver mặc định.
- `<resolvers>` chứa các resolver được định nghĩa trong settings.
- `<ibiblio>` truy cập repository theo cấu trúc Maven.
- `m2compatible="true"` yêu cầu Ivy dùng quy ước đường dẫn Maven, trong đó group/artifact/version được ánh xạ theo cấu trúc repository.
- `root` là URL gốc của repository.
- `<caches>` đặt thư mục cache mặc định.

Nếu không chỉ định resolver mặc định, Ivy có thể dùng resolver mặc định nội bộ tùy cấu hình. Với dự án cần kiểm soát nguồn tải, nên khai báo rõ `defaultResolver` để người đọc biết dependency được tìm ở đâu.

## 4. Resolver cho repository Maven nội bộ

Doanh nghiệp thường có repository riêng để lưu artifact nội bộ hoặc proxy các repository bên ngoài. Có thể khai báo resolver `ibiblio` khác với Maven Central:

```xml
<ivysettings>
    <settings defaultResolver="company-repo"/>

    <resolvers>
        <ibiblio name="company-repo"
                 m2compatible="true"
                 root="https://artifacts.example.com/repository/maven-public/"/>
    </resolvers>

    <caches defaultCacheDir="${user.home}/.ivy2/cache"/>
</ivysettings>
```

Thay URL ví dụ bằng endpoint repository được quản trị viên cung cấp. Endpoint có thể là repository hosted, proxy hoặc group repository tùy sản phẩm quản lý artifact của tổ chức.

Khi dùng repository nội bộ, nên xác định rõ:

- Repository có chứa artifact nội bộ, artifact bên thứ ba hay cả hai.
- Có yêu cầu xác thực hay không.
- Repository có proxy Maven Central hay không.
- Có chính sách chặn phiên bản, artifact hoặc license nào không.
- Endpoint nào được dùng cho môi trường phát triển và môi trường build chính thức.

Không nên cấu hình build dựa vào một repository cá nhân hoặc endpoint chỉ truy cập được từ máy của một thành viên.

## 5. Resolver cho thư mục filesystem

Ngoài repository HTTP, Ivy có thể tìm dependency trong thư mục trên máy hoặc trên vùng lưu trữ dùng chung thông qua resolver `filesystem`.

```xml
<ivysettings>
    <settings defaultResolver="local-first"/>

    <resolvers>
        <filesystem name="local-libraries">
            <ivy pattern="${user.home}/.ivy2/local/[organisation]/[module]/[revision]/ivy.xml"/>
            <artifact pattern="${user.home}/.ivy2/local/[organisation]/[module]/[revision]/[artifact]-[revision].[ext]"/>
        </filesystem>

        <ibiblio name="central"
                 m2compatible="true"
                 root="https://repo.maven.apache.org/maven2/"/>

        <chain name="local-first" returnFirst="true">
            <resolver ref="local-libraries"/>
            <resolver ref="central"/>
        </chain>
    </resolvers>

    <caches defaultCacheDir="${user.home}/.ivy2/cache"/>
</ivysettings>
```

Resolver `filesystem` sử dụng các pattern để xác định nơi tìm metadata Ivy và artifact. Các token trong pattern có ý nghĩa:

| Token | Ý nghĩa |
|---|---|
| `[organisation]` | Tổ chức hoặc group của module |
| `[module]` | Tên module/artifact |
| `[revision]` | Phiên bản được yêu cầu |
| `[artifact]` | Tên artifact cụ thể |
| `[type]` | Loại artifact theo metadata Ivy |
| `[ext]` | Phần mở rộng tệp, ví dụ `jar` hoặc `pom` |

Các pattern phải khớp với cấu trúc thực tế của repository. Nếu repository nội bộ không lưu metadata theo định dạng Ivy, có thể cần resolver phù hợp với layout của nó hoặc dùng repository Maven tương thích.

## 6. Kết hợp nhiều nguồn bằng resolver chain

Resolver chain cho phép Ivy thử nhiều nguồn theo thứ tự. Điều này hữu ích khi dự án có artifact nội bộ trong repository riêng và thư viện bên thứ ba trong Maven Central.

```xml
<ivysettings>
    <settings defaultResolver="main-chain"/>

    <resolvers>
        <chain name="main-chain" returnFirst="true">
            <ibiblio name="company"
                     m2compatible="true"
                     root="https://artifacts.example.com/repository/maven-public/"/>
            <ibiblio name="central"
                     m2compatible="true"
                     root="https://repo.maven.apache.org/maven2/"/>
        </chain>
    </resolvers>

    <caches defaultCacheDir="${user.home}/.ivy2/cache"/>
</ivysettings>
```

Với `returnFirst="true"`, chain dừng khi resolver đầu tiên tìm thấy dependency phù hợp. Nếu resolver đầu tiên không có module được yêu cầu, Ivy thử resolver tiếp theo.

Thứ tự resolver có ý nghĩa. Nếu repository nội bộ là nguồn có thẩm quyền cho artifact công ty, nên đặt nó trước nguồn công khai. Tránh để một artifact cùng tọa độ có thể được lấy từ nguồn không mong muốn trước khi Ivy kiểm tra nguồn nội bộ.

Resolver chain giúp cấu hình nhiều nguồn, nhưng không tự xác định chính sách ưu tiên phiên bản giữa các nguồn một cách tùy ý. Kết quả còn phụ thuộc revision được yêu cầu, metadata và resolver strategy.

## 7. Chọn resolver theo module

Một số dự án cần dùng resolver khác nhau cho các nhóm module. Ví dụ, module nội bộ phải lấy từ repository công ty, trong khi dependency bên thứ ba được lấy từ Maven Central.

Ivy hỗ trợ phần tử `<modules>` để định tuyến theo tổ chức hoặc tên module:

```xml
<ivysettings>
    <settings defaultResolver="central"/>

    <resolvers>
        <ibiblio name="company"
                 m2compatible="true"
                 root="https://artifacts.example.com/repository/internal/"/>
        <ibiblio name="central"
                 m2compatible="true"
                 root="https://repo.maven.apache.org/maven2/"/>
    </resolvers>

    <modules>
        <module organisation="com.example.internal.*" resolver="company"/>
    </modules>

    <caches defaultCacheDir="${user.home}/.ivy2/cache"/>
</ivysettings>
```

Trong ví dụ, các module có organization khớp mẫu `com.example.internal.*` được chuyển tới resolver `company`; các module còn lại dùng resolver mặc định `central`.

Quy tắc định tuyến nên dựa trên namespace ổn định của tổ chức. Tránh pattern quá rộng khiến thư viện bên thứ ba bị gửi nhầm tới repository nội bộ hoặc ngược lại.

## 8. Hiểu cấu trúc cache của Ivy

Cache là vùng lưu cục bộ để Ivy giữ metadata đã phân giải và artifact đã tải. Khi một dependency được yêu cầu ở lần build sau, Ivy có thể dùng thông tin cache thay vì tải lại mọi thứ.

Có thể cấu hình thư mục cache mặc định:

```xml
<ivysettings>
    <settings defaultResolver="central"/>
    <resolvers>
        <ibiblio name="central"
                 m2compatible="true"
                 root="https://repo.maven.apache.org/maven2/"/>
    </resolvers>
    <caches defaultCacheDir="${user.home}/.ivy2/cache"/>
</ivysettings>
```

Trong đó `${user.home}` là thư mục home của người dùng đang chạy Ant/Ivy. Trên các máy khác nhau, đường dẫn thực tế có thể khác nhau.

Không nên nhầm cache với repository:

| Thành phần | Vị trí | Vai trò |
|---|---|---|
| Repository từ xa | Máy chủ Maven hoặc Ivy | Nguồn phân phối metadata và artifact |
| Repository filesystem | Thư mục do dự án hoặc tổ chức quản lý | Nguồn artifact trên đĩa |
| Ivy cache | Thư mục cục bộ trên máy build | Lưu kết quả resolve và các artifact đã tải |
| `lib/` của dự án | Thư mục dự án nếu dùng `retrieve` | Bản dependency được lấy ra theo pattern để task khác sử dụng |

Cache thường không nên được commit vào Git. Cache là dữ liệu có thể tái tạo từ repository và có thể chứa trạng thái riêng của máy. Thay vào đó, hãy commit `ivy.xml`, `ivysettings.xml` và các cấu hình cần thiết để mọi máy có thể resolve cùng dependency.

## 9. Điều khiển cache và cập nhật dependency

Ivy lưu cache nhằm giảm thời gian truy cập repository. Khi dependency được pin bằng revision cố định, các lần resolve sau thường có thể tái sử dụng metadata và artifact đã tải. Khi dùng revision động như `latest.integration` hoặc `1.+`, Ivy cần kiểm tra metadata mới để xác định phiên bản phù hợp; điều này làm kết quả build phụ thuộc trạng thái repository và thời điểm chạy.

Đối với build có yêu cầu tái lập, nên ưu tiên revision cụ thể trong `ivy.xml` và kiểm soát thời điểm cập nhật cache. Ví dụ:

```xml
<dependency org="org.slf4j"
            name="slf4j-api"
            rev="2.0.16"
            conf="compile->default"/>
```

Nếu cần kiểm tra phiên bản mới, hãy thực hiện như một hoạt động cập nhật dependency có chủ đích, sau đó ghi revision đã chọn vào `ivy.xml`. Không dùng revision động trong build phát hành nếu dự án cần đầu ra ổn định.

Ivy có tùy chọn refresh ở task resolve để yêu cầu kiểm tra lại metadata của dependency. Ví dụ:

```xml
<ivy:resolve refresh="true"/>
```

`refresh` hữu ích khi repository vừa được cập nhật hoặc khi cần kiểm tra lại revision động. Nó không phải lệnh xóa toàn bộ cache. Xóa cache nên là thao tác xử lý có mục tiêu, vì xóa toàn bộ cache có thể khiến lần build sau phải tải lại nhiều dependency và làm tăng tải cho repository.

## 10. Resolver cho repository URL tùy chỉnh

Nếu repository không theo layout Maven hoặc Ivy mặc định, có thể dùng resolver `url` với các pattern cụ thể:

```xml
<ivysettings>
    <settings defaultResolver="vendor-url"/>

    <resolvers>
        <url name="vendor-url">
            <ivy pattern="https://downloads.example.com/ivy/[organisation]/[module]/[revision]/ivy.xml"/>
            <artifact pattern="https://downloads.example.com/artifacts/[organisation]/[module]/[revision]/[artifact]-[revision].[ext]"/>
        </url>
    </resolvers>

    <caches defaultCacheDir="${user.home}/.ivy2/cache"/>
</ivysettings>
```

Resolver `url` cho phép mô tả vị trí metadata và artifact theo pattern. Điều này phù hợp khi nhà cung cấp hoặc tổ chức có layout lưu trữ riêng. Pattern phải phản ánh đúng cấu trúc URL thực tế; nếu không, Ivy sẽ không tìm thấy file dù repository vẫn truy cập được.

Nếu nguồn chỉ cung cấp artifact mà không có metadata Ivy tương ứng, cần chọn resolver và cấu hình metadata phù hợp với định dạng repository. Không giả định mọi máy chủ HTTP chứa JAR đều tự động hoạt động như Maven repository.

## 11. Repository riêng có xác thực

Repository nội bộ có thể yêu cầu username/password. Ivy hỗ trợ khai báo credentials trong settings:

```xml
<ivysettings>
    <settings defaultResolver="company"/>

    <credentials host="artifacts.example.com"
                 realm="Company Artifact Repository"
                 username="${repo.user}"
                 passwd="${repo.password}"/>

    <resolvers>
        <ibiblio name="company"
                 m2compatible="true"
                 root="https://artifacts.example.com/repository/maven-public/"/>
    </resolvers>

    <caches defaultCacheDir="${user.home}/.ivy2/cache"/>
</ivysettings>
```

`host` phải khớp host của repository; `realm` cần khớp realm mà máy chủ yêu cầu nếu có. Giá trị `repo.user` và `repo.password` chỉ là placeholder: hãy cung cấp chúng từ cơ chế cấu hình bí mật của môi trường build hoặc tệp riêng không được commit.

Không ghi mật khẩu thật vào `ivysettings.xml` được lưu trong repository. Tránh in credentials ra log hoặc truyền chúng qua tham số có thể bị lưu trong lịch sử shell. Với CI, dùng secret variables hoặc secret store của nền tảng để cấp thông tin xác thực cho tiến trình build.

## 12. Tích hợp `ivysettings.xml` với Ant

Để sử dụng task Ivy, cần có Ivy jar trong classpath của Ant. Có thể đặt JAR phù hợp vào thư mục `lib` của Ant hoặc khởi chạy Ant với tùy chọn `-lib` trỏ tới vị trí Ivy jar. Phiên bản Ivy cần tương thích với phiên bản Ant và JDK của môi trường build.

Buildfile có thể khai báo namespace Antlib của Ivy:

```xml
<project name="ivy-ant-demo"
         default="resolve"
         xmlns:ivy="antlib:org.apache.ivy.ant">

    <target name="resolve">
        <ivy:settings file="ivysettings.xml"/>
        <ivy:resolve file="ivy.xml"/>
        <ivy:retrieve pattern="lib/[artifact]-[revision].[ext]"/>
    </target>

</project>
```

Trong ví dụ:

- `<ivy:settings>` nạp resolver và cache từ `ivysettings.xml`.
- `<ivy:resolve>` đọc `ivy.xml`, tìm dependency và phân giải phiên bản.
- `<ivy:retrieve>` sao chép artifact đã resolve ra thư mục dự án theo pattern.

Pattern `lib/[artifact]-[revision].[ext]` tạo tên file có tên artifact và revision. Nếu dự án muốn giữ cấu trúc Maven-like, có thể dùng pattern chứa `[organisation]`, `[module]` và `[revision]` để tránh trùng tên giữa các tổ chức.

## 13. Dùng cachepath để tạo classpath cho `javac`

Không nhất thiết phải retrieve JAR ra thư mục `lib`. Task `<ivy:cachepath>` có thể tạo Ant Path trỏ trực tiếp tới các artifact trong cache:

```xml
<project name="ivy-compile-demo"
         default="compile"
         xmlns:ivy="antlib:org.apache.ivy.ant">

    <property name="src.dir" location="src/main/java"/>
    <property name="classes.dir" location="build/classes"/>

    <target name="resolve-dependencies">
        <ivy:settings file="ivysettings.xml"/>
        <ivy:resolve file="ivy.xml" conf="compile"/>
        <ivy:cachepath pathid="compile.classpath" conf="compile"/>
    </target>

    <target name="compile" depends="resolve-dependencies">
        <mkdir dir="${classes.dir}"/>
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               includeantruntime="false"
               encoding="UTF-8">
            <classpath refid="compile.classpath"/>
        </javac>
    </target>

</project>
```

`ivy:cachepath` tạo một Path có `id` để task `javac` tham chiếu. Cấu hình `conf="compile"` yêu cầu Ivy lấy dependency thuộc configuration compile đã khai báo trong `ivy.xml`.

Để chạy ứng dụng, có thể tạo path riêng từ configuration runtime:

```xml
<target name="run" depends="compile">
    <ivy:cachepath pathid="runtime.classpath" conf="runtime"/>
    <java classname="com.example.Main" fork="true" failonerror="true">
        <classpath>
            <pathelement location="build/classes"/>
            <path refid="runtime.classpath"/>
        </classpath>
    </java>
</target>
```

Nếu dự án có dependency khác nhau giữa compile và runtime, hãy khai báo configuration trong `ivy.xml` và tạo path tương ứng cho từng task.

## 14. Chọn settings file theo môi trường

Một tổ chức có thể có repository khác nhau cho phát triển, kiểm thử và build phát hành. Có thể duy trì nhiều tệp settings:

```text
config/
├── ivysettings-dev.xml
├── ivysettings-ci.xml
└── ivysettings-release.xml
```

Mỗi tệp có thể định nghĩa resolver chain và cache phù hợp với môi trường. Buildfile nhận đường dẫn settings bằng property:

```xml
<project name="environment-aware-build"
         default="resolve"
         xmlns:ivy="antlib:org.apache.ivy.ant">

    <property name="ivy.settings.file" location="config/ivysettings-dev.xml"/>

    <target name="resolve">
        <ivy:settings file="${ivy.settings.file}"/>
        <ivy:resolve file="ivy.xml"/>
    </target>

</project>
```

Có thể truyền settings khác khi chạy Ant bằng property dòng lệnh nếu buildfile chưa đặt property đó bằng một giá trị không thể ghi đè:

```sh
ant -Divy.settings.file=config/ivysettings-ci.xml resolve
```

Ant property được truyền bằng `-D` có sẵn trước khi buildfile đặt giá trị mặc định, nên `<property>` trong buildfile không ghi đè giá trị đã được truyền. Cần bảo đảm mỗi settings file dùng đúng repository và credentials của môi trường tương ứng.

## 15. Cách kiểm tra cấu hình resolver và cache

Khi dependency không được tìm thấy, hãy kiểm tra lần lượt:

1. Buildfile có nạp đúng `ivysettings.xml` hay không.
2. `defaultResolver` có trỏ tới resolver đã khai báo hay không.
3. Resolver có đúng root URL hoặc filesystem pattern hay không.
4. Repository có metadata và artifact đúng tọa độ, revision hay không.
5. Dependency có bị định tuyến sang resolver khác qua `<modules>` hay không.
6. Credentials có đúng host/realm và quyền truy cập hay không.
7. Cache có metadata cũ hoặc trạng thái không phù hợp hay không.

Có thể bật log chi tiết của Ant/Ivy để xem resolver được gọi và vị trí Ivy tìm kiếm. Ví dụ:

```sh
ant -verbose resolve
```

Nếu nghi ngờ metadata cache đã cũ, có thể dùng `refresh="true"` trong `ivy:resolve` để yêu cầu kiểm tra lại. Chỉ xóa thư mục cache cụ thể khi đã xác định được vấn đề và hiểu rằng Ivy sẽ phải tải lại artifact liên quan.

## 16. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Ivy báo không có resolver mặc định | `defaultResolver` không khớp tên resolver hoặc resolver chưa được khai báo | Kiểm tra tên trong `<settings>` và phần `<resolvers>` |
| Không tìm thấy dependency trên Maven repository | Sai group/module/revision hoặc resolver root/layout không đúng | Kiểm tra tọa độ trong `ivy.xml`, URL root và `m2compatible` |
| Repository nội bộ không được thử | Resolver không nằm trong chain hoặc module routing trỏ sang resolver khác | Kiểm tra chain, thứ tự resolver và `<modules>` |
| JAR tải được nhưng metadata không tìm thấy | Repository layout hoặc pattern không khớp vị trí metadata | Kiểm tra cấu trúc repository và pattern `[organisation]`, `[module]`, `[revision]` |
| HTTP 401 hoặc 403 | Thiếu credentials, sai host/realm hoặc tài khoản không đủ quyền | Cấp credentials từ secret store và xác nhận quyền truy cập |
| Máy này resolve được, máy khác không | Phụ thuộc cache cục bộ hoặc repository chỉ truy cập từ một mạng | Kiểm tra cấu hình resolver và cung cấp repository dùng chung ổn định |
| Thay đổi repository nhưng Ivy vẫn dùng thông tin cũ | Metadata cache chưa được refresh hoặc revision động | Dùng refresh có chủ đích và kiểm tra cache liên quan |
| Hai phiên bản dependency xuất hiện ngoài dự kiến | Revision động, conflict hoặc metadata từ nhiều resolver | Pin revision, xem log resolve và kiểm tra conflict strategy |
| Ant báo không nhận diện `ivy:` task | Ivy jar chưa có trong classpath của Ant hoặc namespace chưa được khai báo | Cài/cấu hình Ivy jar, kiểm tra phiên bản và `xmlns:ivy` |
| Task `javac` không nhận được dependency đã resolve | Path ID sai hoặc configuration resolve không đúng | Kiểm tra `pathid`, `conf` và thứ tự target `resolve` trước `compile` |

## 17. Checklist cấu hình `ivysettings.xml`

- [ ] `ivy.xml` khai báo dependency và revision cần thiết.
- [ ] `ivysettings.xml` có `<settings>` và `defaultResolver` hợp lệ.
- [ ] Resolver được khai báo với đúng loại và đúng repository root/layout.
- [ ] Resolver chain có thứ tự phù hợp với nguồn artifact nội bộ và bên ngoài.
- [ ] Module routing chỉ áp dụng cho đúng organization/module.
- [ ] Cache directory được cấu hình phù hợp với môi trường build.
- [ ] Credentials không bị ghi trực tiếp vào file được commit.
- [ ] Ivy jar và Ant task namespace được cấu hình đúng.
- [ ] `ivy:resolve` chạy trước `ivy:cachepath` hoặc `ivy:retrieve`.
- [ ] Compile/runtime configurations được dùng đúng với task tương ứng.
- [ ] Phiên bản dependency được pin khi build cần tái lập.
- [ ] Đã kiểm tra log khi resolver không tìm được artifact.

`ivysettings.xml` giúp tách chính sách truy cập dependency khỏi danh sách dependency của module. Khi resolver, repository, thứ tự tìm kiếm và cache được cấu hình rõ ràng, Ant có thể dùng Ivy để resolve và cung cấp thư viện nhất quán cho các bước biên dịch, kiểm thử và chạy ứng dụng.
