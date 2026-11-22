# Quản lý phiên bản, tên tệp và định danh bản phát hành

Khi dùng Apache Ant để đóng gói ứng dụng, việc tạo được một tệp JAR hoặc ZIP mới chỉ là một phần của quy trình phát hành. Nhóm phát triển còn cần biết artifact đó thuộc phiên bản nào, được tạo từ lần build nào, lấy mã nguồn ở revision nào và có đúng là tệp đã được kiểm tra hay không.

Nếu mọi lần build đều ghi ra cùng một tên như `application.jar`, artifact mới có thể ghi đè artifact cũ. Nếu tên tệp và metadata bên trong JAR không thống nhất, người nhận cũng khó xác định bản đang sử dụng. Một quy ước phiên bản và tên tệp rõ ràng giúp lưu trữ, truy vết, so sánh và phát hành có kiểm soát.

Bài học này trình bày cách xây dựng định danh bản phát hành trong Ant, cách đặt tên artifact, ghi metadata vào manifest, phân biệt phiên bản sản phẩm với số build và revision mã nguồn, tạo checksum và tổ chức output để các bản phát hành có thể được truy xuất lâu dài.

## 1. Phân biệt các loại định danh

Một artifact thường có nhiều thông tin định danh. Không nên dùng một giá trị duy nhất để đại diện cho tất cả.

| Định danh | Ý nghĩa | Ví dụ |
|---|---|---|
| Product version | Phiên bản chức năng của sản phẩm | `2.4.0` |
| Pre-release identifier | Trạng thái phát hành trước bản ổn định | `2.5.0-rc.1` |
| Build number | Số thứ tự của lần build trong CI hoặc hệ thống phát hành | `1042` |
| Build ID | Mã định danh duy nhất của một lần chạy | `ci-1042` |
| SCM revision | Commit hoặc revision của mã nguồn dùng để build | `a1b2c3d4e5f6` |
| Build timestamp | Thời điểm tạo artifact | `20261112-163000` |
| Artifact filename | Tên file được phân phối hoặc lưu trữ | `sample-2.4.0-ci-1042.jar` |
| Checksum | Dấu kiểm tra nội dung file | SHA-256 digest |

Ví dụ, hai artifact có cùng product version `2.4.0` nhưng được tạo từ hai commit khác nhau có thể có build ID khác nhau. Ngược lại, cùng một build có thể tạo nhiều loại artifact như JAR ứng dụng, ZIP chứa tài liệu và gói kiểm thử; mỗi file có tên riêng nhưng cùng tham chiếu đến product version và SCM revision.

Hãy quyết định thông tin nào cần xuất hiện trong tên file, thông tin nào nằm trong manifest và thông tin nào được lưu trong metadata phát hành. Tên file nên ngắn, ổn định và dễ đọc; manifest hoặc metadata có thể chứa thông tin chi tiết hơn.

## 2. Chọn quy ước version cho sản phẩm

Một quy ước phổ biến là Semantic Versioning (SemVer):

```text
MAJOR.MINOR.PATCH[-PRERELEASE][+BUILD]
```

Ví dụ:

| Phiên bản | Ý nghĩa thường dùng |
|---|---|
| `1.0.0` | Bản phát hành ổn định đầu tiên |
| `1.1.0` | Thêm chức năng tương thích ngược |
| `1.1.1` | Sửa lỗi tương thích ngược |
| `2.0.0` | Thay đổi lớn có thể phá vỡ tương thích |
| `2.0.0-alpha.1` | Bản alpha trước phát hành |
| `2.0.0-beta.2` | Bản beta thứ hai |
| `2.0.0-rc.1` | Release candidate đầu tiên |
| `2.0.0+build.1042` | Metadata build của phiên bản `2.0.0` |

Theo SemVer, tăng `MAJOR` khi có thay đổi không tương thích API, tăng `MINOR` khi bổ sung chức năng tương thích ngược và tăng `PATCH` khi sửa lỗi tương thích ngược. Phần pre-release phân biệt bản chưa ổn định; build metadata bổ sung thông tin nhận diện nhưng không làm thay đổi thứ tự ưu tiên của phiên bản SemVer.

SemVer là quy ước quản lý phiên bản sản phẩm, không phải chức năng tự động của Ant. Ant chỉ lưu và đưa chuỗi version vào tên file hoặc metadata theo cấu hình bạn viết.

### Chọn một quy ước phù hợp với dự án

Không phải dự án nào cũng cần đầy đủ SemVer. Một ứng dụng nội bộ có thể dùng `2026.11` hoặc `release-2026-q4`. Điều quan trọng là:

- Cùng một quy tắc được dùng nhất quán giữa các nhóm.
- Một version không bị tái sử dụng cho nội dung khác nhau.
- Có cách xác định artifact được tạo từ revision nào.
- Bản phát hành ổn định và bản thử nghiệm có thể phân biệt được.
- Version trong tên file khớp với version trong metadata.

Nếu đã công bố version `2.4.0`, không nên thay nội dung artifact rồi tiếp tục dùng cùng tên và version đó. Hãy phát hành version mới hoặc build identifier mới theo chính sách của dự án.

## 3. Khai báo version và build identifier trong Ant

Ant property phù hợp để lưu các giá trị cấu hình của bản phát hành. Ví dụ:

```xml
<project name="sample-app" default="package" basedir=".">

    <property file="release.properties"/>

    <property name="app.name" value="sample-app"/>
    <property name="release.version" value="0.1.0-SNAPSHOT"/>
    <property name="build.number" value="local"/>
    <property name="build.id" value="local"/>
    <property name="scm.revision" value="unknown"/>

    <property name="dist.dir" location="dist"/>
    <property name="classes.dir" location="build/classes"/>

    <property
        name="artifact.id"
        value="${release.version}-${build.id}"/>

</project>
```

Các property có ý nghĩa:

- `app.name`: tên sản phẩm hoặc module.
- `release.version`: version của sản phẩm.
- `build.number`: số thứ tự của build.
- `build.id`: mã riêng của lần chạy.
- `scm.revision`: revision mã nguồn.
- `artifact.id`: chuỗi dùng để tạo tên artifact.

File `release.properties` có thể chứa cấu hình mặc định được quản lý cùng dự án:

```properties
app.name=sample-app
release.version=2.4.0
build.number=1042
build.id=ci-1042
scm.revision=a1b2c3d4e5f6
```

Khi chạy:

```bash
ant package
```

Ant nạp các giá trị từ file rồi dùng chúng trong build. Người gọi có thể truyền user property để thay đổi một giá trị cho lần chạy:

```bash
ant -Drelease.version=2.5.0-rc.1 -Dbuild.id=ci-1088 package
```

User property từ dòng lệnh có độ ưu tiên cao hơn property thông thường được nạp trong build file. Property của Ant có tính bất biến: một lần khai báo `<property>` sau đó không ghi đè giá trị đã được thiết lập. Vì vậy, hãy nạp file cấu hình và thiết lập các giá trị mặc định theo thứ tự có chủ đích.

### Không dùng cùng một property cho nhiều ý nghĩa

Không nên gộp product version, build number và revision vào một property duy nhất rồi dùng chuỗi đó ở mọi nơi. Giữ chúng riêng biệt sẽ giúp:

- Thay build ID mà không thay product version.
- Ghi revision vào manifest mà không làm tên file quá dài.
- Dùng cùng product version cho nhiều loại artifact của một lần build.
- Tạo báo cáo hoặc metadata có thể truy vấn từng trường riêng.

## 4. Đặt tên artifact có version

Tên artifact nên chứa tên ứng dụng, version và khi cần một build identifier:

```text
<app-name>-<release-version>[-<build-id>].<extension>
```

Ví dụ:

```text
sample-app-2.4.0.jar
sample-app-2.4.0-ci-1042.jar
sample-app-2.5.0-rc.1-ci-1088.jar
sample-app-2.4.0-docs.zip
```

Một số nguyên tắc đặt tên:

- Dùng chữ thường và dấu gạch ngang để tên file dễ đọc trên nhiều hệ điều hành.
- Tránh khoảng trắng, ký tự điều khiển và ký tự không cần thiết.
- Giữ phần mở rộng phản ánh đúng định dạng artifact.
- Đặt version ở vị trí thống nhất để có thể sắp xếp hoặc tìm kiếm.
- Chỉ đưa build ID vào tên khi cần phân biệt các lần build của cùng product version.
- Không dùng `latest` làm định danh duy nhất của bản phát hành.

Các ký tự hợp lệ của filename có khác biệt giữa hệ điều hành. Nếu artifact được chuyển giữa Windows, Linux và hệ thống lưu trữ khác, hãy giới hạn version và build ID ở một tập ký tự đơn giản, chẳng hạn chữ cái ASCII, chữ số, dấu chấm, dấu gạch ngang và dấu gạch dưới.

### Tạo tên file bằng property

Ví dụ hoàn chỉnh:

```xml
<property name="app.name" value="sample-app"/>
<property name="release.version" value="2.4.0"/>
<property name="build.id" value="ci-1042"/>

<property
    name="artifact.file"
    value="${app.name}-${release.version}-${build.id}.jar"/>

<echo message="Artifact: ${artifact.file}"/>
```

Giá trị `artifact.file` được tạo từ các property đã khai báo trước. Hãy đặt property thành phần trước property kết hợp để Ant có thể thay thế đúng giá trị.

## 5. Đưa version vào tên JAR và ZIP

Task `jar` và `zip` nhận đường dẫn output qua thuộc tính `destfile`. Bạn có thể xây dựng đường dẫn đó bằng property:

```xml
<property name="app.name" value="sample-app"/>
<property name="release.version" value="2.4.0"/>
<property name="build.id" value="ci-1042"/>
<property name="dist.dir" location="dist"/>
<property
    name="jar.file"
    location="${dist.dir}/${app.name}-${release.version}-${build.id}.jar"/>

<target name="package">
    <mkdir dir="${dist.dir}"/>
    <jar
        destfile="${jar.file}"
        basedir="build/classes"/>
</target>
```

Sau khi chạy `ant package`, artifact có tên:

```text
dist/sample-app-2.4.0-ci-1042.jar
```

Nếu cần tạo thêm gói ZIP:

```xml
<property
    name="source.zip"
    location="${dist.dir}/${app.name}-${release.version}-${build.id}-sources.zip"/>

<target name="package-sources">
    <zip destfile="${source.zip}">
        <fileset dir="src">
            <include name="**/*"/>
        </fileset>
    </zip>
</target>
```

Các artifact cùng lần phát hành có thể dùng chung version và build ID nhưng có hậu tố mô tả loại gói, ví dụ `-sources`, `-docs` hoặc `-tests`.

## 6. Ghi thông tin phát hành vào manifest

Tên file có thể bị đổi khi upload hoặc lưu trữ. Vì vậy, JAR ứng dụng nên có metadata bên trong manifest để người nhận xác định version ngay cả khi file được đổi tên.

Manifest nằm ở:

```text
META-INF/MANIFEST.MF
```

Task `jar` cho phép thêm thuộc tính bằng nested element `<manifest>`:

```xml
<jar
    destfile="${jar.file}"
    basedir="build/classes">
    <manifest>
        <attribute
            name="Implementation-Title"
            value="${app.name}"/>
        <attribute
            name="Implementation-Version"
            value="${release.version}"/>
        <attribute
            name="Implementation-Vendor"
            value="Example Engineering"/>
        <attribute
            name="Build-Number"
            value="${build.number}"/>
        <attribute
            name="Build-Id"
            value="${build.id}"/>
        <attribute
            name="SCM-Revision"
            value="${scm.revision}"/>
    </manifest>
</jar>
```

Các trường thường dùng:

| Manifest attribute | Mục đích |
|---|---|
| `Implementation-Title` | Tên sản phẩm hoặc module |
| `Implementation-Version` | Version của implementation |
| `Implementation-Vendor` | Tổ chức phát hành hoặc sở hữu |
| `Specification-Version` | Version của specification/API nếu dự án có định nghĩa |
| `Build-Number` | Số build |
| `Build-Id` | Mã lần build |
| `SCM-Revision` | Revision mã nguồn |

Các trường như `Build-Number`, `Build-Id` và `SCM-Revision` là metadata tùy chỉnh của dự án. Java không tự quy định ý nghĩa của chúng; ứng dụng hoặc công cụ phát hành phải đọc theo quy ước đã thống nhất.

`Implementation-Version` là trường quen thuộc trong manifest Java. Ứng dụng có thể đọc thông tin package bằng `Package.getImplementationVersion()` khi manifest và cách đóng gói cung cấp metadata phù hợp. Không nên giả định mọi classloader hoặc mọi cách chạy đều trả về giá trị này; hãy kiểm tra trên artifact thực tế.

### Executable JAR

Nếu JAR cần chạy trực tiếp bằng `java -jar`, hãy thêm `Main-Class`:

```xml
<manifest>
    <attribute name="Main-Class" value="com.example.Main"/>
    <attribute name="Implementation-Title" value="${app.name}"/>
    <attribute name="Implementation-Version" value="${release.version}"/>
    <attribute name="Build-Id" value="${build.id}"/>
</manifest>
```

`Main-Class` xác định lớp có phương thức `main`; các trường version và build metadata phục vụ nhận diện artifact. Chúng có mục đích khác nhau nhưng có thể cùng tồn tại trong manifest.

## 7. Ghi revision mã nguồn vào artifact

Product version cho biết phiên bản sản phẩm, nhưng không nhất thiết chỉ ra chính xác commit đã tạo ra artifact. Trong quy trình CI, việc lưu SCM revision giúp truy ngược mã nguồn.

Ant Core không tự quản lý Git commit. Nếu môi trường build có Git, có thể gọi lệnh `git` bằng task `exec`:

```xml
<target name="read-scm-revision">
    <exec
        executable="git"
        failonerror="true"
        outputproperty="scm.revision">
        <arg value="rev-parse"/>
        <arg value="--short=12"/>
        <arg value="HEAD"/>
    </exec>
</target>
```

Target này đặt output của lệnh Git vào property `scm.revision`. Sau đó, target đóng gói có thể phụ thuộc vào nó:

```xml
<target name="package" depends="read-scm-revision">
    <jar destfile="${jar.file}" basedir="build/classes">
        <manifest>
            <attribute name="Implementation-Version" value="${release.version}"/>
            <attribute name="SCM-Revision" value="${scm.revision}"/>
        </manifest>
    </jar>
</target>
```

Ví dụ giả định build đang chạy trong một Git working tree và Git executable có trong `PATH`. Nếu build có thể chạy từ source archive không chứa metadata Git, hãy cung cấp revision từ CI qua `-Dscm.revision=...` hoặc dùng giá trị có kiểm soát như `unknown`; đừng để target gọi Git làm hỏng quy trình đóng gói hợp lệ trong môi trường không có repository metadata.

Nếu cần xác định cả trạng thái working tree, có thể lấy thêm thông tin từ Git và ghi vào metadata. Artifact phát hành chính thức thường nên được tạo từ một commit hoặc tag đã được xác định, với source tree sạch theo chính sách của dự án.

## 8. Build number và timestamp

Build number thường do CI cấp để phân biệt các lần chạy. Ví dụ:

```bash
ant -Drelease.version=2.4.0 -Dbuild.number=1042 -Dbuild.id=ci-1042 package
```

Build number không thay thế product version. Nhiều lần build có thể cùng version sản phẩm nhưng khác build ID; điều này hữu ích cho snapshot hoặc kiểm thử nội bộ.

Nếu cần timestamp để hỗ trợ chẩn đoán, Ant có task `tstamp`:

```xml
<target name="set-build-time">
    <tstamp>
        <format
            property="build.timestamp"
            pattern="yyyyMMdd-HHmmss"/>
    </tstamp>
</target>
```

Sau đó có thể ghi timestamp vào manifest:

```xml
<attribute name="Build-Time" value="${build.timestamp}"/>
```

Timestamp hữu ích khi điều tra nhưng không nên luôn là thành phần duy nhất của version. Nó làm tên file thay đổi theo từng giây và có thể khiến hai artifact được tạo từ cùng source không còn so sánh dễ dàng. Với build tái lập, hãy lưu thời điểm trong metadata bên ngoài hoặc manifest khi chính sách cho phép; tránh đưa dữ liệu thời gian không cần thiết vào nội dung artifact nếu cần byte-for-byte reproducibility.

## 9. Tạo checksum để xác minh artifact

Sau khi đóng gói, có thể tạo checksum để người nhận xác minh file tải về có cùng nội dung với file được phát hành.

Ví dụ dùng SHA-256:

```xml
<target name="checksum" depends="package">
    <checksum
        file="${jar.file}"
        algorithm="SHA-256"
        fileext=".sha256"/>
</target>
```

Task `checksum` tạo file checksum cạnh JAR, ví dụ:

```text
dist/
├── sample-app-2.4.0-ci-1042.jar
└── sample-app-2.4.0-ci-1042.jar.sha256
```

Checksum giúp phát hiện nội dung bị thay đổi hoặc hỏng trong quá trình truyền tải. Nó không chứng minh ai đã phát hành file và không thay thế chữ ký số. Nếu cần xác thực nguồn gốc, hãy dùng quy trình ký artifact và quản lý khóa riêng biệt.

Bạn cũng có thể lấy digest vào property để ghi vào log hoặc metadata:

```xml
<checksum
    file="${jar.file}"
    algorithm="SHA-256"
    property="artifact.sha256"/>
<echo message="SHA-256: ${artifact.sha256}"/>
```

Khi dùng `fileext`, task ghi digest ra file. Khi dùng `property`, task lưu digest vào property. Chọn cách phù hợp với quy trình phân phối và lưu trữ của dự án.

## 10. Tổ chức thư mục phát hành

Một cấu trúc output có thể giữ các artifact theo version:

```text
dist/
└── 2.4.0/
    ├── sample-app-2.4.0-ci-1042.jar
    ├── sample-app-2.4.0-ci-1042.jar.sha256
    ├── sample-app-2.4.0-ci-1042-sources.zip
    └── release-info.properties
```

Tệp `release-info.properties` có thể lưu thông tin máy đọc được:

```properties
app.name=sample-app
release.version=2.4.0
build.number=1042
build.id=ci-1042
scm.revision=a1b2c3d4e5f6
artifact=sample-app-2.4.0-ci-1042.jar
```

Lợi ích:

- Các artifact cùng version nằm trong một khu vực dễ tìm.
- Nhiều định dạng gói có thể được phát hành cùng nhau.
- Checksum được lưu cạnh artifact.
- Metadata có thể được dùng bởi script triển khai hoặc hệ thống quản lý phát hành.

Nếu lưu nhiều lần build của cùng version, hãy tạo thư mục theo build ID hoặc đưa build ID vào tên file để tránh ghi đè. Một kho artifact chính thức thường nên giữ artifact theo định danh bất biến thay vì cập nhật nội dung dưới cùng một đường dẫn.

## 11. Tránh ghi đè artifact đã phát hành

Trong quá trình phát triển, ghi đè `dist/application.jar` có thể tiện lợi. Nhưng với artifact phát hành, việc ghi đè cùng tên khiến khó xác định file nào đã được kiểm thử hoặc phân phối.

Có thể kiểm tra output đã tồn tại trước khi tạo artifact:

```xml
<target name="check-artifact-name">
    <available file="${jar.file}" property="artifact.already.exists"/>
    <fail
        if="artifact.already.exists"
        message="Artifact đã tồn tại: ${jar.file}. Hãy dùng build ID khác hoặc version mới."/>
</target>

<target name="package" depends="check-artifact-name">
    <mkdir dir="${dist.dir}"/>
    <jar destfile="${jar.file}" basedir="${classes.dir}"/>
</target>
```

Target `check-artifact-name` giúp tránh ghi đè một file đã tồn tại trong workspace hiện tại. Đây không phải cơ chế khóa phân tán: nếu hai build đồng thời cùng kiểm tra và ghi vào một thư mục chia sẻ, vẫn có thể xảy ra race condition. CI nên dùng workspace hoặc thư mục output riêng cho mỗi job, hoặc để kho artifact thực hiện kiểm soát tính duy nhất khi publish.

### Không dùng alias làm định danh chính

Tên như `latest.jar`, `stable.jar` hoặc `current.zip` có thể hữu ích cho liên kết tiện lợi, nhưng chúng có thể trỏ đến nội dung khác theo thời gian. Hãy giữ tên có version và build ID làm định danh chính. Nếu tạo alias, hãy xem nó là con trỏ phụ có thể cập nhật.

## 12. Ví dụ build file phát hành tổng hợp

Ví dụ sau kết hợp version, build ID, manifest, SCM revision tùy chọn và checksum:

```xml
<project name="sample-app" default="release" basedir=".">

    <property file="release.properties"/>

    <property name="app.name" value="sample-app"/>
    <property name="release.version" value="0.1.0-SNAPSHOT"/>
    <property name="build.number" value="local"/>
    <property name="build.id" value="local"/>
    <property name="scm.revision" value="unknown"/>

    <property name="classes.dir" location="build/classes"/>
    <property name="dist.dir" location="dist"/>
    <property
        name="artifact.file"
        location="${dist.dir}/${app.name}-${release.version}-${build.id}.jar"/>

    <target name="compile">
        <mkdir dir="${classes.dir}"/>
        <javac
            srcdir="src"
            destdir="${classes.dir}"
            includeantruntime="false"
            encoding="UTF-8"/>
    </target>

    <target name="check-artifact-name">
        <available file="${artifact.file}" property="artifact.already.exists"/>
        <fail
            if="artifact.already.exists"
            message="Artifact already exists: ${artifact.file}"/>
    </target>

    <target name="package" depends="compile,check-artifact-name">
        <mkdir dir="${dist.dir}"/>
        <jar destfile="${artifact.file}" basedir="${classes.dir}">
            <manifest>
                <attribute name="Implementation-Title" value="${app.name}"/>
                <attribute name="Implementation-Version" value="${release.version}"/>
                <attribute name="Build-Number" value="${build.number}"/>
                <attribute name="Build-Id" value="${build.id}"/>
                <attribute name="SCM-Revision" value="${scm.revision}"/>
            </manifest>
        </jar>
    </target>

    <target name="checksum" depends="package">
        <checksum
            file="${artifact.file}"
            algorithm="SHA-256"
            fileext=".sha256"/>
    </target>

    <target name="release" depends="checksum">
        <echo message="Release version: ${release.version}"/>
        <echo message="Build ID: ${build.id}"/>
        <echo message="SCM revision: ${scm.revision}"/>
        <echo message="Artifact: ${artifact.file}"/>
    </target>

</project>
```

Chạy build với cấu hình release:

```bash
ant -Drelease.version=2.4.0 -Dbuild.number=1042 -Dbuild.id=ci-1042 release
```

Kết quả dự kiến:

```text
dist/
├── sample-app-2.4.0-ci-1042.jar
└── sample-app-2.4.0-ci-1042.jar.sha256
```

Ví dụ này đặt `scm.revision` mặc định là `unknown`. Trong CI, nên truyền revision thật:

```bash
ant -Drelease.version=2.4.0 -Dbuild.number=1042 -Dbuild.id=ci-1042 -Dscm.revision=a1b2c3d4e5f6 release
```

Nếu dự án muốn lấy revision trực tiếp từ Git, có thể thêm target `read-scm-revision` như phần trước và đặt `package` phụ thuộc vào target đó. Hãy chọn một nguồn revision duy nhất cho mỗi build để manifest, metadata và log không bị lệch nhau.

## 13. Kiểm tra artifact sau khi đóng gói

Sau khi build, hãy kiểm tra ít nhất:

1. Tên file chứa đúng app name, release version và build ID.
2. Manifest có `Implementation-Version` đúng với version đã chọn.
3. Revision và build number được ghi đúng nếu dự án yêu cầu.
4. Artifact không ghi đè một bản phát hành đã tồn tại.
5. Checksum được tạo từ đúng file cuối cùng.
6. Lệnh chạy hoặc kiểm thử artifact hoạt động trên môi trường phù hợp.

Có thể xem manifest bằng:

```bash
jar xf dist/sample-app-2.4.0-ci-1042.jar META-INF/MANIFEST.MF
```

Hoặc liệt kê nội dung archive:

```bash
jar tf dist/sample-app-2.4.0-ci-1042.jar
```

Khi giải nén manifest để kiểm tra, chú ý thư mục hiện tại vì lệnh `jar xf` tạo tệp trong workspace. Có thể dùng thư mục tạm để không làm lẫn metadata kiểm tra vào source tree.

Để kiểm tra checksum, dùng công cụ phù hợp với hệ điều hành, chẳng hạn `sha256sum` trên nhiều bản Linux hoặc `Get-FileHash` trong PowerShell:

```powershell
Get-FileHash .\dist\sample-app-2.4.0-ci-1042.jar -Algorithm SHA256
```

Giá trị digest phải khớp với nội dung file checksum do Ant tạo.

## 14. Một số lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Tên JAR vẫn là tên cũ | `destfile` không dùng property version hoặc property được ghép sai thứ tự | Kiểm tra property trước khi khai báo `artifact.file` |
| Filename và manifest khác version | Hai giá trị được khai báo riêng và không cùng lấy từ một property | Dùng chung `release.version` cho tên file và `Implementation-Version` |
| Build ID không xuất hiện | Lệnh CI không truyền property hoặc tên property sai | Kiểm tra `-Dbuild.id=...` và log giá trị trước khi đóng gói |
| Revision là `unknown` | Build không nhận revision từ CI hoặc Git | Truyền `scm.revision` hoặc chạy target lấy revision trong Git working tree |
| Artifact cũ bị ghi đè | Các lần build dùng cùng tên và cùng thư mục output | Thêm build ID hoặc kiểm tra file tồn tại trước khi tạo |
| Checksum không khớp | Checksum được tạo trước khi artifact thay đổi hoặc đang kiểm tra nhầm file | Tạo checksum sau bước đóng gói cuối cùng và xác minh đúng đường dẫn |
| Tên file không tương thích hệ điều hành | Build ID hoặc version chứa ký tự đặc biệt | Chuẩn hóa chuỗi dùng trong filename |
| Manifest không có version | Task `jar` không khai báo thuộc tính manifest | Thêm nested `<manifest>` và `Implementation-Version` |
| Hai build đồng thời xung đột | Cùng ghi vào một output directory | Dùng workspace riêng hoặc cơ chế publish có kiểm soát tính duy nhất |

## 15. Nguyên tắc quản lý bản phát hành

- Dùng một quy ước version có ý nghĩa và áp dụng nhất quán.
- Tách product version, build number, build ID, SCM revision và timestamp.
- Dùng property chung cho filename và manifest để tránh lệch thông tin.
- Đặt tên artifact có version; không dùng tên alias thay cho định danh chính.
- Lưu metadata đủ để truy vết artifact về source revision và lần build.
- Tạo checksum sau khi artifact đã hoàn tất.
- Không ghi đè artifact đã công bố; mỗi lần phát hành nên có định danh bất biến.
- Dùng workspace hoặc thư mục output riêng khi chạy nhiều build song song.
- Giữ thông tin thời gian ở vai trò metadata khi cần build tái lập.
- Kiểm tra artifact thực tế trước khi phân phối.

## 16. Ghi nhớ

- Version sản phẩm cho biết mức phát triển của ứng dụng; build ID phân biệt từng lần tạo artifact.
- SCM revision xác định commit hoặc revision mã nguồn đã được dùng.
- Ant property giúp ghép các thành phần thành tên file và metadata phát hành.
- `destfile` của task `jar` hoặc `zip` có thể dùng property để tạo tên artifact có version.
- Manifest có thể lưu `Implementation-Title`, `Implementation-Version`, build number, build ID và revision.
- Task `exec` có thể gọi Git để lấy revision nếu môi trường build có Git.
- Task `tstamp` tạo timestamp; timestamp nên là metadata bổ sung thay vì định danh duy nhất.
- Task `checksum` có thể tạo SHA-256 file để xác minh nội dung artifact.
- Tên versioned và build ID giúp tránh ghi đè; alias như `latest` chỉ nên là tham chiếu tiện lợi.

Một quy trình phát hành rõ ràng phải trả lời được ba câu hỏi: artifact thuộc version sản phẩm nào, được tạo từ revision nào và là kết quả của lần build nào. Khi các thông tin đó được quản lý nhất quán trong property, tên file, manifest và checksum, việc lưu trữ, phân phối và truy vết artifact sẽ đáng tin cậy hơn.
