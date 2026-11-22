# Tạo checksum và thông tin nguồn gốc sản phẩm

Khi phát hành một sản phẩm Java, cần cung cấp cách để người nhận kiểm tra tệp tải về có bị thay đổi hay không và hiểu artifact được tạo từ mã nguồn, dependency và quy trình build nào. Apache Ant có thể tính checksum cho artifact, ghi metadata build vào manifest hoặc tệp thông tin riêng, đồng thời gọi công cụ ký số hay công cụ tạo provenance của hệ thống CI.

Các loại thông tin này có mục đích khác nhau:

- **Checksum** là giá trị băm của nội dung tệp, dùng để phát hiện dữ liệu khác với bản đã tính.
- **Chữ ký số** xác nhận artifact được ký bằng khóa riêng tương ứng; người nhận cần xác minh chữ ký bằng khóa công khai đáng tin cậy.
- **Build metadata** mô tả phiên bản, commit, thời điểm và công cụ đã tạo artifact.
- **SBOM** liệt kê thành phần và dependency có trong sản phẩm.
- **Build provenance/attestation** ghi nhận nguồn đầu vào, builder và quy trình tạo ra artifact, thường được ký hoặc bảo vệ bởi nền tảng build.

Một giá trị SHA-256 không tự chứng minh ai đã tạo artifact hoặc artifact đến từ repository nào. Để có thông tin nguồn gốc đáng tin cậy, cần kết hợp checksum với metadata, chữ ký và provenance phù hợp.

## 1. Checksum và vai trò trong phát hành

Checksum là kết quả của một hàm băm mật mã được tính trên toàn bộ byte của tệp. Nếu nội dung tệp thay đổi, checksum gần như chắc chắn thay đổi theo. Người nhận có thể tính lại checksum sau khi tải artifact rồi so sánh với giá trị được nhà phát hành công bố.

Ví dụ một tệp JAR và checksum SHA-256:

```text
inventory-2.4.0.jar
inventory-2.4.0.jar.sha256
```

Tệp `.sha256` có thể chứa giá trị băm của JAR. Nếu giá trị tính lại trùng khớp, nội dung tệp đang kiểm tra giống với nội dung đã được dùng để tạo checksum.

### 1.1. Chọn thuật toán băm

Các thuật toán thường gặp:

| Thuật toán | Đặc điểm | Khuyến nghị |
|---|---|---|
| MD5 | Nhanh nhưng có lỗ hổng va chạm đã biết | Không dùng để bảo đảm an toàn cho artifact phát hành |
| SHA-1 | Có tấn công va chạm thực tế | Tránh dùng cho checksum bảo mật mới |
| SHA-256 | Thuộc SHA-2, được hỗ trợ rộng rãi trong JDK hiện đại và công cụ hệ điều hành | Lựa chọn mặc định phù hợp cho checksum phát hành |
| SHA-512 | Thuộc SHA-2, tạo digest dài hơn SHA-256 | Có thể dùng khi chính sách hoặc hệ thống phân phối yêu cầu |

Với artifact phát hành, hãy chỉ định rõ `SHA-256` hoặc thuật toán mạnh hơn thay vì dựa vào mặc định của task. Task `<checksum>` của Ant có thể mặc định dùng MD5 nếu không khai báo `algorithm`, vì vậy cần đặt `algorithm="SHA-256"` một cách tường minh.

### 1.2. Checksum chứng minh điều gì?

Checksum hữu ích khi người nhận đã có một giá trị băm đáng tin cậy để đối chiếu. Nó phát hiện lỗi truyền tải, tệp bị hỏng hoặc nội dung bị thay đổi so với digest tham chiếu.

Tuy nhiên, nếu kẻ tấn công thay cả JAR lẫn tệp checksum được tải từ cùng một nguồn không đáng tin, hai tệp có thể vẫn khớp nhau. Checksum không xác thực danh tính người phát hành. Để xác thực nguồn gốc, cần chữ ký số hoặc attestation được xác minh bằng khóa/tổ chức đáng tin cậy.

## 2. Tính checksum bằng task `<checksum>` của Ant

Ant cung cấp task `<checksum>` để tính digest cho một tệp hoặc một tập tệp. Có thể lưu kết quả vào Ant property, tạo tệp checksum cạnh artifact hoặc ghi vào thư mục riêng.

### 2.1. Tính checksum và lưu vào property

Ví dụ tính SHA-256 của một JAR:

```xml
<target name="calculate-checksum">
    <checksum file="build/dist/inventory.jar"
              algorithm="SHA-256"
              property="inventory.sha256"/>

    <echo message="SHA-256: ${inventory.sha256}"/>
</target>
```

Thuộc tính `property` nhận giá trị digest được tính. Cách này phù hợp khi cần dùng checksum ở bước tiếp theo, ghi vào manifest metadata hoặc tạo một tệp checksum tổng hợp.

Không dùng property để ghi đè checksum của nhiều artifact vào cùng một tên property. Ant property là bất biến theo quy tắc first definition wins; hãy dùng tên riêng cho từng artifact hoặc tạo tệp checksum tương ứng.

### 2.2. Tạo sidecar checksum cạnh artifact

Nếu không chỉ định `property`, task có thể ghi checksum ra tệp riêng. Dùng `fileext` để chỉ định phần mở rộng mong muốn:

```xml
<target name="checksum-jar">
    <checksum file="build/dist/inventory.jar"
              algorithm="SHA-256"
              fileext=".sha256"/>
</target>
```

Task tạo tệp checksum tương ứng với artifact, chẳng hạn `inventory.jar.sha256`. Có thể dùng `todir` để đặt các tệp checksum trong thư mục riêng thay vì để cạnh từng artifact.

### 2.3. Tạo checksum cho nhiều artifact bằng FileSet

Task `<checksum>` hỗ trợ nested `<fileset>`. Ví dụ tạo sidecar SHA-256 cho các JAR và ZIP trong thư mục phát hành:

```xml
<target name="checksum-release-artifacts">
    <mkdir dir="build/checksums"/>

    <checksum algorithm="SHA-256"
              fileext=".sha256"
              todir="build/checksums">
        <fileset dir="build/dist">
            <include name="*.jar"/>
            <include name="*.zip"/>
        </fileset>
    </checksum>
</target>
```

Ant tính checksum cho từng resource được chọn và ghi các tệp kết quả vào `todir` theo cấu trúc tương ứng. Chỉ chọn artifact cuối cùng cần phát hành; tránh đưa thư mục checksum vào chính FileSet đầu vào.

### 2.4. Một số thuộc tính quan trọng của `<checksum>`

| Thuộc tính | Ý nghĩa |
|---|---|
| `file` | Tệp đơn cần tính hoặc xác minh checksum |
| `todir` | Thư mục đích để ghi các tệp checksum khi xử lý tập tệp |
| `algorithm` | Tên thuật toán băm, ví dụ `SHA-256` |
| `provider` | Tên provider Java Cryptography Architecture nếu cần chọn provider cụ thể |
| `fileext` | Phần mở rộng của tệp checksum, ví dụ `.sha256` |
| `property` | Tên Ant property nhận digest được tính cho tệp |
| `verifyproperty` | Tên property nhận kết quả xác minh checksum với tệp sidecar hiện có |
| `totalproperty` | Property nhận checksum tổng hợp cho tập tệp, khi dùng với FileSet |
| `forceOverwrite` | Cho phép ghi lại checksum file ngay cả khi cơ chế kiểm tra thời gian sửa đổi cho rằng không cần cập nhật |
| `readbuffersize` | Kích thước buffer đọc dữ liệu để tính checksum |

Thuộc tính cụ thể và cách kết hợp chúng cần tuân theo tài liệu Ant của phiên bản đang dùng. Trong build phát hành, cách đơn giản nhất là chỉ định `algorithm`, `file` hoặc `fileset`, và `property` hoặc `todir` theo đúng mục tiêu.

## 3. Xác minh checksum bằng Ant

Task `<checksum>` có thể kiểm tra artifact với sidecar checksum đã tạo trước đó. Dùng `verifyproperty` để nhận kết quả xác minh:

```xml
<target name="verify-jar-checksum">
    <checksum file="build/dist/inventory.jar"
              algorithm="SHA-256"
              fileext=".sha256"
              verifyproperty="inventory.checksum.valid"/>

    <condition property="inventory.checksum.matches">
        <equals arg1="${inventory.checksum.valid}" arg2="true"/>
    </condition>

    <fail unless="inventory.checksum.matches"
          message="SHA-256 verification failed for inventory.jar"/>
</target>
```

Task đọc sidecar `inventory.jar.sha256`, tính lại digest của JAR và đặt kết quả xác minh vào property `inventory.checksum.valid`. Condition tiếp theo kiểm tra giá trị đó; nếu không khớp, task `<fail>` làm build dừng.

Không viết `<fail unless="inventory.checksum.valid">` để kiểm tra kết quả true/false. `unless` của Ant kiểm tra property đã được thiết lập hay chưa; một property có giá trị chuỗi `false` vẫn tồn tại. Hãy so sánh giá trị rõ ràng như ví dụ trên.

### 3.1. Xác minh bằng công cụ của hệ điều hành

Người nhận artifact có thể tự tính SHA-256 bằng công cụ phổ biến.

Linux:

```bash
sha256sum inventory-2.4.0.jar
```

macOS:

```bash
shasum -a 256 inventory-2.4.0.jar
```

Windows PowerShell:

```powershell
Get-FileHash .\inventory-2.4.0.jar -Algorithm SHA256
```

So sánh toàn bộ chuỗi digest với giá trị do nhà phát hành cung cấp. Không chỉ so sánh vài ký tự đầu hoặc cuối.

### 3.2. Tạo tệp `SHA256SUMS` theo định dạng phổ biến

Một số công cụ như `sha256sum -c` mong đợi tệp checksum có dạng digest, hai dấu cách, rồi tên tệp. Có thể tạo tệp tổng hợp bằng cách lấy digest vào property và ghi tên artifact:

```xml
<target name="write-sha256sums">
    <checksum file="build/dist/inventory.jar"
              algorithm="SHA-256"
              property="inventory.sha256"/>
    <checksum file="build/dist/inventory-sources.zip"
              algorithm="SHA-256"
              property="sources.sha256"/>

    <echo file="build/dist/SHA256SUMS"
          message="${inventory.sha256}  inventory.jar"/>
    <echo file="build/dist/SHA256SUMS"
          append="true"
          message="${sources.sha256}  inventory-sources.zip"/>
</target>
```

Tệp kết quả có dạng:

```text
<sha256-of-inventory-jar>  inventory.jar
<sha256-of-sources-zip>  inventory-sources.zip
```

Các chuỗi trong dấu ngoặc nhọn ở trên chỉ minh họa; Ant ghi giá trị băm thực tế. Trên Linux, người nhận có thể đặt JAR, ZIP và `SHA256SUMS` trong cùng thư mục rồi chạy:

```bash
sha256sum -c SHA256SUMS
```

Trên macOS có thể dùng:

```bash
shasum -a 256 -c SHA256SUMS
```

Trên Windows, dùng `Get-FileHash` cho từng tệp rồi so sánh với digest trong danh sách, hoặc dùng công cụ tương thích với định dạng checksum này.

Tên file trong `SHA256SUMS` được tính tương đối với thư mục mà lệnh kiểm tra được chạy. Hãy phân phối tệp checksum cùng các artifact và hướng dẫn người nhận chạy lệnh từ đúng thư mục.

## 4. Tạo metadata nguồn gốc trong build

Checksum chỉ mô tả nội dung artifact. Để người nhận biết artifact đến từ đâu, build nên ghi lại thông tin nhận dạng phiên bản và nguồn đầu vào.

Thông tin hữu ích thường gồm:

| Trường | Ví dụ | Mục đích |
|---|---|---|
| Tên artifact | `inventory` | Nhận diện sản phẩm |
| Phiên bản | `2.4.0` | Nhận diện bản phát hành |
| Repository | `https://example.org/scm/inventory.git` | Cho biết nguồn mã nguồn |
| Commit | `8c12...` | Chỉ ra revision cụ thể được build |
| Build ID | `release-2026.11.12.4` | Liên kết artifact với một lần chạy CI |
| Build time | Thời điểm UTC | Hỗ trợ điều tra và đối chiếu lịch sử |
| Builder | Tên workflow/runner hoặc hệ thống build | Cho biết môi trường tạo artifact |
| Toolchain | Phiên bản JDK và Ant | Giúp tái lập môi trường |
| Dependency | Phiên bản dependency được resolve | Cho biết thành phần đầu vào của build |
| Artifact digest | SHA-256 | Liên kết metadata với đúng byte của artifact |

Không phải mọi thông tin đều cần đặt trong manifest. Có thể lưu một phần trong manifest để dễ xem nhanh, còn thông tin chi tiết hơn trong `build-info.properties`, SBOM hoặc provenance attestation.

### 4.1. Nhận commit và build ID từ CI

Một cách đơn giản là yêu cầu pipeline truyền các giá trị nhận dạng vào Ant:

```bash
ant -Dapp.version=2.4.0 \
    -Dsource.repository=https://example.org/scm/inventory.git \
    -Dsource.revision=8c12f4a... \
    -Dbuild.id=release-2026.11.12.4 \
    package
```

Trên Windows PowerShell, có thể viết cùng lệnh trên một dòng hoặc dùng dấu backtick để xuống dòng. Giá trị commit cần là commit đầy đủ mà pipeline checkout, không nên dùng nhãn nhánh như `main` làm định danh nguồn bất biến.

Nếu build được chạy cục bộ, có thể đặt các property mặc định phù hợp hoặc yêu cầu người chạy truyền chúng. Với phát hành chính thức, nên để CI cung cấp revision và build ID từ chính lần checkout/build đó để tránh ghi nhầm nguồn.

### 4.2. Ghi `build-info.properties`

Có thể tạo tệp thông tin build bên cạnh artifact:

```xml
<target name="write-build-info">
    <fail unless="app.version"
          message="app.version is required for a release."/>
    <fail unless="source.revision"
          message="source.revision must identify the source commit."/>
    <fail unless="build.id"
          message="build.id must identify this build run."/>

    <echo file="build/dist/build-info.properties">
artifact.name=inventory
artifact.version=${app.version}
source.repository=${source.repository}
source.revision=${source.revision}
build.id=${build.id}
build.time=${build.timestamp}
build.ant.version=${ant.version}
build.java.version=${java.version}
    </echo>
</target>
```

Property `build.timestamp` cần được cung cấp bởi pipeline hoặc khai báo trước trong build. Có thể dùng timestamp do CI cấp theo UTC để bảo đảm các hệ thống dùng cùng một chuẩn thời gian. Không nên dùng thời gian local không kèm múi giờ nếu metadata cần đối chiếu giữa các khu vực.

Nếu `source.repository` không bắt buộc trong mọi môi trường, có thể kiểm tra nó tương tự hoặc ghi rõ `unknown` theo chính sách. Tránh ghi thông tin nhạy cảm như URL repository chứa token, password hoặc thông tin xác thực.

### 4.3. Ghi metadata vào JAR manifest

Manifest có thể chứa một số trường nhận dạng nhanh:

```xml
<jar destfile="build/dist/inventory.jar"
     basedir="build/classes">
    <manifest>
        <attribute name="Main-Class" value="com.example.app.Main"/>
        <attribute name="Implementation-Title" value="inventory"/>
        <attribute name="Implementation-Version" value="${app.version}"/>
        <attribute name="Build-Revision" value="${source.revision}"/>
        <attribute name="Build-Id" value="${build.id}"/>
        <attribute name="Build-Jdk" value="${java.version}"/>
        <attribute name="Build-Ant" value="${ant.version}"/>
    </manifest>
</jar>
```

Các header `Build-Revision`, `Build-Id`, `Build-Jdk` và `Build-Ant` là metadata tùy chỉnh do dự án định nghĩa. Người nhận có thể đọc chúng bằng `jar` hoặc API `java.util.jar.Manifest`.

Manifest không phải bằng chứng mật mã về nguồn gốc: bất kỳ ai có thể sửa JAR cũng có thể sửa manifest. Hãy dùng nó để nhận diện và hỗ trợ điều tra, không dùng nó thay cho chữ ký hoặc provenance attestation.

## 5. Thu thập thông tin commit và toolchain

Một build có thể ghi nhận revision Git và phiên bản công cụ, nhưng cần bảo đảm các giá trị được lấy từ đúng lần checkout.

### 5.1. Truyền revision từ pipeline

CI thường đã biết commit đang checkout và có thể truyền giá trị đó qua `-Dsource.revision`. Cách này tránh để build file tự đoán branch hoặc lấy commit từ một repository khác nằm trong thư mục làm việc.

Nếu muốn lấy revision trực tiếp bằng Git, có thể gọi lệnh từ Ant:

```xml
<target name="read-source-revision">
    <exec executable="git"
          dir="${basedir}"
          failonerror="true"
          outputproperty="source.revision">
        <arg value="rev-parse"/>
        <arg value="HEAD"/>
    </exec>
</target>
```

Target này giả định Git đã được cài đặt và `${basedir}` là working tree đúng. Với build phát hành, revision do CI truyền thường rõ ràng hơn và có thể đối chiếu với thông tin checkout của pipeline.

### 5.2. Ghi nhận toolchain

Ant cung cấp một số property hệ thống như `ant.version`, `ant.java.version` và `java.version`. Có thể ghi chúng vào build info để người nhận biết môi trường thực thi.

```xml
<echo message="Ant version: ${ant.version}"/>
<echo message="Ant Java version: ${ant.java.version}"/>
<echo message="Runtime Java version: ${java.version}"/>
```

Các property này mô tả JVM đang chạy Ant. Nếu dự án fork một JVM khác để biên dịch hoặc chạy test, cần ghi nhận riêng phiên bản JDK đó; `java.version` của Ant không nhất thiết là phiên bản JVM con.

## 6. SBOM và provenance attestation

Build metadata, SBOM và provenance thường được phân phối cùng nhau nhưng trả lời các câu hỏi khác nhau.

| Tài liệu | Câu hỏi được trả lời |
|---|---|
| `build-info.properties` | Artifact này được tạo từ phiên bản/commit/build ID nào? |
| Checksum | Nội dung tệp có khớp với digest đã công bố không? |
| Chữ ký số | Artifact có được ký bởi khóa mà người nhận tin cậy không? |
| SBOM | Artifact chứa hoặc phụ thuộc vào những thành phần nào? |
| Provenance attestation | Builder nào đã tạo artifact, từ source/materials nào và theo quy trình nào? |

### 6.1. SBOM

SBOM (Software Bill of Materials) là danh mục thành phần phần mềm trong sản phẩm. Các định dạng phổ biến gồm CycloneDX và SPDX. SBOM có thể ghi tên package, phiên bản, nhà cung cấp, license, quan hệ dependency và các định danh như PURL.

Ant không tự động tạo SBOM đầy đủ chỉ bằng task `<checksum>` hoặc `<jar>`. Có thể tích hợp công cụ tạo SBOM phù hợp với hệ sinh thái dependency của dự án, sau đó lưu kết quả cạnh artifact:

```text
dist/
├── inventory.jar
├── inventory.jar.sha256
├── inventory.cdx.json
└── build-info.properties
```

Nếu SBOM được tạo trước khi đóng gói, hãy bảo đảm nó mô tả đúng tập dependency thực sự có trong artifact. Với dependency được resolve bằng Ivy, có thể dùng báo cáo dependency làm một nguồn dữ liệu đầu vào, nhưng báo cáo Ivy không mặc nhiên là SBOM theo chuẩn CycloneDX hoặc SPDX.

### 6.2. Provenance attestation

Provenance mô tả mối liên hệ giữa artifact, nguồn đầu vào và quy trình build. Một bản provenance hữu ích thường có:

- Artifact digest để xác định chính xác sản phẩm.
- Source repository và commit bất biến.
- Builder identity hoặc workflow đã thực hiện build.
- Build type và các tham số quan trọng.
- Materials/dependencies được sử dụng.
- Thời gian và thông tin môi trường thực thi.

Các định dạng và mô hình như SLSA provenance cung cấp cấu trúc để máy có thể xác minh thông tin này. Ant có thể tạo metadata hoặc gọi công cụ tạo attestation, nhưng một tệp properties tự ghi không tự trở thành provenance được xác thực. Nên để nền tảng CI hoặc công cụ chuyên dụng tạo và ký attestation dựa trên thông tin thực tế của pipeline.

## 7. Ký artifact bằng chữ ký detached

Để xác thực nguồn phát hành, có thể ký JAR bằng OpenPGP hoặc hệ thống ký artifact của tổ chức. Với GnuPG, chữ ký detached thường được tạo thành tệp riêng:

```bash
gpg --armor --detach-sign --output inventory.jar.asc inventory.jar
```

Người nhận xác minh bằng:

```bash
gpg --verify inventory.jar.asc inventory.jar
```

Kết quả chữ ký hợp lệ chỉ có ý nghĩa xác thực danh tính khi người nhận đã kiểm tra fingerprint của khóa công khai và tin cậy khóa đó. Không chỉ dựa vào dòng `Good signature` nếu chưa xác nhận khóa thuộc nhà phát hành mong đợi.

### 7.1. Gọi công cụ ký từ Ant

Có thể tích hợp GnuPG vào target phát hành bằng task `<exec>`:

```xml
<target name="sign-artifact" depends="package">
    <exec executable="gpg" failonerror="true">
        <arg value="--batch"/>
        <arg value="--armor"/>
        <arg value="--detach-sign"/>
        <arg value="--output"/>
        <arg file="${dist.dir}/inventory.jar.asc"/>
        <arg file="${dist.dir}/inventory.jar"/>
    </exec>
</target>
```

Ví dụ giả định GnuPG đã được cài đặt, khóa ký đã được cấu hình an toàn trong keyring hoặc signing agent và tiến trình có quyền sử dụng khóa. Không lưu private key hoặc passphrase trong `build.xml`, repository, manifest hay log. Trong CI, ưu tiên secret store, signing service hoặc cơ chế ký được quản trị bởi nền tảng.

### 7.2. Thứ tự ký và tính checksum

Một quy trình thường dùng:

1. Hoàn tất JAR, ZIP và SBOM.
2. Ký các artifact cần xác thực.
3. Tính checksum cho các tệp cuối cùng được phân phối, bao gồm chữ ký detached nếu muốn kiểm tra truyền tải của chữ ký.
4. Tạo provenance attestation gắn với digest của artifact và thông tin build.
5. Kiểm tra lại chữ ký và checksum trước khi đưa vào kho phát hành.

Không sửa artifact sau khi ký. Nếu JAR thay đổi dù chỉ một byte sau khi ký, chữ ký detached cũ sẽ không còn xác minh được. Nếu thay đổi artifact, hãy ký lại và tạo lại checksum.

## 8. Ví dụ quy trình phát hành bằng Ant

Ví dụ sau kết hợp tạo JAR, ghi build info, tạo checksum và gọi GnuPG để ký artifact. Các property nhận dạng nguồn được truyền từ CI.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="inventory-release" default="release" basedir=".">

    <property name="app.name" value="inventory"/>
    <property name="app.version" value="2.4.0"/>
    <property name="build.dir" location="${basedir}/build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="dist.dir" location="${build.dir}/dist"/>

    <target name="check-release-metadata">
        <fail unless="source.repository"
              message="source.repository is required for a release."/>
        <fail unless="source.revision"
              message="source.revision is required for a release."/>
        <fail unless="build.id"
              message="build.id is required for a release."/>
        <fail unless="build.timestamp"
              message="build.timestamp is required for a release."/>
    </target>

    <target name="prepare-dist" depends="check-release-metadata">
        <mkdir dir="${dist.dir}"/>
    </target>

    <target name="package" depends="prepare-dist">
        <jar destfile="${dist.dir}/${app.name}-${app.version}.jar"
             basedir="${classes.dir}">
            <manifest>
                <attribute name="Main-Class" value="com.example.app.Main"/>
                <attribute name="Implementation-Title" value="${app.name}"/>
                <attribute name="Implementation-Version" value="${app.version}"/>
                <attribute name="Build-Revision" value="${source.revision}"/>
                <attribute name="Build-Id" value="${build.id}"/>
                <attribute name="Build-Jdk" value="${java.version}"/>
                <attribute name="Build-Ant" value="${ant.version}"/>
            </manifest>
        </jar>
    </target>

    <target name="write-build-info" depends="package">
        <echo file="${dist.dir}/build-info.properties">
artifact.name=${app.name}
artifact.version=${app.version}
source.repository=${source.repository}
source.revision=${source.revision}
build.id=${build.id}
build.timestamp=${build.timestamp}
build.ant.version=${ant.version}
build.java.version=${java.version}
        </echo>
    </target>

    <target name="sign" depends="write-build-info">
        <exec executable="gpg" failonerror="true">
            <arg value="--batch"/>
            <arg value="--armor"/>
            <arg value="--detach-sign"/>
            <arg value="--output"/>
            <arg file="${dist.dir}/${app.name}-${app.version}.jar.asc"/>
            <arg file="${dist.dir}/${app.name}-${app.version}.jar"/>
        </exec>
    </target>

    <target name="checksums" depends="sign">
        <checksum file="${dist.dir}/${app.name}-${app.version}.jar"
                  algorithm="SHA-256"
                  property="artifact.sha256"/>
        <checksum file="${dist.dir}/${app.name}-${app.version}.jar.asc"
                  algorithm="SHA-256"
                  property="signature.sha256"/>
        <checksum file="${dist.dir}/build-info.properties"
                  algorithm="SHA-256"
                  property="buildinfo.sha256"/>

        <echo file="${dist.dir}/SHA256SUMS"
              message="${artifact.sha256}  ${app.name}-${app.version}.jar"/>
        <echo file="${dist.dir}/SHA256SUMS"
              append="true"
              message="${signature.sha256}  ${app.name}-${app.version}.jar.asc"/>
        <echo file="${dist.dir}/SHA256SUMS"
              append="true"
              message="${buildinfo.sha256}  build-info.properties"/>
    </target>

    <target name="release" depends="checksums">
        <echo message="Release artifacts prepared in ${dist.dir}"/>
    </target>

</project>
```

Các property `source.repository`, `source.revision`, `build.id` và `build.timestamp` cần được truyền từ pipeline, ví dụ:

```bash
ant \
  -Dsource.repository=https://example.org/scm/inventory.git \
  -Dsource.revision=8c12f4a... \
  -Dbuild.id=release-2026.11.12.4 \
  -Dbuild.timestamp=2026-11-12T09:30:00Z \
  release
```

Ví dụ tập trung vào bước phát hành; target `package` giả định `build/classes` đã được biên dịch. Cần bổ sung dependency compile/test và tạo SBOM theo công cụ của dự án trước khi ký nếu các bước đó thuộc quy trình release.

## 9. Kiểm tra kết quả phát hành

Sau khi target hoàn thành, thư mục phân phối có thể có dạng:

```text
build/dist/
├── inventory-2.4.0.jar
├── inventory-2.4.0.jar.asc
├── build-info.properties
└── SHA256SUMS
```

Kiểm tra checksum:

```bash
sha256sum -c SHA256SUMS
```

Kiểm tra chữ ký:

```bash
gpg --verify inventory-2.4.0.jar.asc inventory-2.4.0.jar
```

Sau đó kiểm tra fingerprint của khóa ký bằng nguồn công bố đáng tin cậy. Đọc metadata trong JAR:

```bash
unzip -p inventory-2.4.0.jar META-INF/MANIFEST.MF
```

Kiểm tra `build-info.properties` để đối chiếu commit, build ID, phiên bản và thời gian với lần chạy CI. Nếu có SBOM và provenance attestation, xác minh chúng theo định dạng và công cụ tương ứng.

## 10. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Digest khác với giá trị công bố | Artifact bị hỏng, bị thay đổi hoặc checksum thuộc phiên bản khác | Tải lại từ nguồn chính thức, kiểm tra tên/version và tính lại digest |
| Task dùng MD5 dù cần SHA-256 | Không chỉ định `algorithm` | Đặt `algorithm="SHA-256"` tường minh |
| `verifyproperty` trả về false | Sidecar cũ, sai thuật toán hoặc artifact đã thay đổi | Tạo lại checksum từ artifact cuối cùng và kiểm tra đúng `fileext` |
| Property checksum không có giá trị | Sai tên property, task không chạy hoặc tệp đầu vào không tồn tại | Kiểm tra target dependency, đường dẫn và log Ant |
| Tệp checksum không được ghi | Thư mục đích chưa tồn tại hoặc không có quyền ghi | Tạo `todir` bằng `<mkdir>` và kiểm tra quyền filesystem |
| Checksum list không xác minh được bằng `sha256sum -c` | Định dạng hoặc đường dẫn file không đúng với quy ước công cụ | Dùng định dạng `digest  filename` và chạy lệnh từ thư mục chứa artifact |
| Build info ghi commit không đúng | Pipeline truyền nhầm revision hoặc build file lấy từ working tree khác | Lấy revision từ checkout thực tế và liên kết với build ID |
| Manifest có metadata nhưng không xác thực được nguồn gốc | Manifest chỉ là dữ liệu có thể sửa, không phải chữ ký | Ký artifact và xác minh khóa công khai hoặc dùng provenance attestation |
| Chữ ký không hợp lệ sau khi đóng gói | Artifact bị sửa sau khi ký hoặc dùng nhầm chữ ký | Hoàn tất artifact trước, ký lại sau mọi thay đổi |
| `gpg` không thể ký trong CI | Keyring/agent không được cấu hình hoặc runner không có quyền dùng khóa | Cấu hình signing service hoặc secret store; không đưa private key vào repository |
| SBOM không khớp artifact | SBOM được tạo từ dependency graph khác hoặc trước khi thay đổi package | Sinh SBOM từ đúng dependency/artifact của lần release và ghi nhận phiên bản công cụ |

## 11. Nguyên tắc bảo vệ thông tin nguồn gốc

- Không ghi private key, passphrase, token hoặc password vào manifest, build info hay checksum file.
- Không dùng `user.name` hoặc đường dẫn home làm bằng chứng danh tính builder; đây chỉ là thông tin môi trường có thể thay đổi.
- Dùng commit đầy đủ, repository URI và build ID bất biến để nhận diện nguồn đầu vào.
- Ghi nhận dependency đã resolve và phiên bản toolchain dùng để tạo artifact.
- Tạo checksum sau khi artifact đã hoàn tất mọi bước sửa đổi.
- Ký artifact cuối cùng và xác minh fingerprint của khóa bằng kênh đáng tin cậy.
- Lưu SBOM và provenance cạnh artifact hoặc trong hệ thống phát hành có thể truy xuất.
- Giữ log build và attestation liên kết với cùng build ID.
- Không coi tệp metadata tự ghi là bằng chứng mật mã nếu chưa được ký hoặc xác thực bởi builder tin cậy.

## 12. Checklist phát hành

- [ ] Đã xác định artifact cuối cùng cần phân phối.
- [ ] Đã chọn SHA-256 hoặc thuật toán mạnh hơn và khai báo rõ trong `<checksum>`.
- [ ] Đã tạo sidecar hoặc `SHA256SUMS` cho đúng các artifact cuối cùng.
- [ ] Đã xác minh checksum bằng Ant hoặc công cụ độc lập.
- [ ] Build info ghi đúng phiên bản, repository, commit và build ID.
- [ ] Toolchain và thời điểm build được ghi nhận theo quy ước nhất quán.
- [ ] Manifest chỉ chứa metadata phù hợp, không chứa secret.
- [ ] SBOM mô tả đúng dependency của artifact phát hành.
- [ ] Provenance attestation liên kết digest với source và builder thực tế.
- [ ] Artifact được ký sau khi hoàn tất mọi thay đổi nội dung.
- [ ] Chữ ký được xác minh bằng khóa công khai và fingerprint đáng tin cậy.
- [ ] Checksum được tính lại sau khi ký nếu danh sách checksum bao gồm chữ ký.
- [ ] Artifact, checksum, chữ ký, SBOM và provenance được lưu cùng build ID hoặc release record.

Tạo checksum và thông tin nguồn gốc là bước quan trọng trong quy trình phát hành có thể kiểm chứng. Ant đảm nhiệm tốt việc tính digest, tạo manifest và ghi metadata build; chữ ký số, SBOM và provenance attestation bổ sung bằng chứng về người phát hành, thành phần và quy trình tạo artifact. Khi kết hợp các lớp này và xác minh chúng trước khi phân phối, người nhận có thể kiểm tra cả tính toàn vẹn lẫn nguồn gốc của sản phẩm.

Tài liệu tham khảo: [Apache Ant Manual — Checksum Task](https://ant.apache.org/manual/Tasks/checksum.html), [Apache Ant Manual — Manifest Task](https://ant.apache.org/manual/Tasks/manifest.html), [SLSA — Provenance](https://slsa.dev/spec/v1.0/provenance) và [CycloneDX Specification](https://cyclonedx.org/specification/).
