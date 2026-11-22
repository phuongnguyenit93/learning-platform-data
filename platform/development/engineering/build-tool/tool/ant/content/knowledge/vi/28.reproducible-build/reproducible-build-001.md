# Kiểm soát phiên bản Ant, JDK, thư viện và công cụ ngoài

Trong dự án sử dụng **Apache Ant**, cùng mã nguồn và cùng `build.xml` chưa bảo đảm hai máy build ra cùng kết quả. Bản Ant khác nhau có thể thực thi task khác nhau; JDK khác nhau có thể tạo bytecode, thông báo lỗi hoặc metadata khác nhau; thư viện và công cụ ngoài có thể thay đổi dù câu lệnh build không đổi.

Trong phạm vi **Build tái lập**, kiểm soát phiên bản là quá trình **khai báo, cố định, kiểm tra và ghi nhận tất cả thành phần ảnh hưởng tới build**. Cần cố định cả số phiên bản lẫn **nội dung binary**, vì tên file hay chuỗi version không phải bằng chứng rằng bytes giống nhau.

## 1. Những thành phần cần kiểm soát

| Thành phần | Nếu không khóa | Cơ chế kiểm soát |
|---|---|---|
| **Apache Ant** | Task, cách giải quyết classpath hoặc hành vi đóng gói có thể thay đổi | Chốt bản Ant cụ thể; phân phối từ nguồn tin cậy, đối chiếu checksum, kiểm tra lúc chạy |
| **JDK chạy Ant** | Khác JVM, compiler, thư viện chuẩn, encoding hoặc xử lý TLS | Chốt vendor, phiên bản đầy đủ, nền tảng và SHA-256; đặt `JAVA_HOME` tường minh |
| **Java release đầu ra** | Có thể dùng API quá mới hoặc bytecode không tương thích | Chọn `javac release="..."` và xác minh runtime đích |
| **JAR ứng dụng** | Dependency trực tiếp/transitive biến động, cùng tên nhưng khác bytes | Dùng phiên bản cố định, dependency lock/manifest và checksum từng JAR |
| **Thư viện dành cho Ant task** | Một máy có task bổ sung trong `~/.ant/lib`, máy khác không có | Khai báo `taskdef` với classpath riêng, pin JAR của task |
| **Công cụ ngoài** | `protoc`, `git`, `node`, `zip`… được lấy tùy ý từ `PATH` | Gọi binary bằng đường dẫn có quản lý; xác minh version và checksum |
| **Kho tải và môi trường** | Cùng build nhưng repository, OS, locale, timestamp hoặc biến môi trường khác | Pin nguồn và artifact, kiểm soát môi trường, lưu thông tin build |

Cần phân biệt ba mức kết quả:

1. **Có thể dựng lại:** lấy đúng những đầu vào đã sử dụng.
2. **Kết quả chức năng nhất quán:** cùng phiên bản công cụ, code và cấu hình cho kết quả kiểm thử/chạy tương đương.
3. **Tái lập từng byte:** hai lần build tạo artifact có cùng SHA-256.

Khóa phiên bản là nền tảng cho cả ba, nhưng mục tiêu thứ ba còn đòi hỏi kiểm soát timestamp, thứ tự file, ZIP/JAR metadata và nguồn bất định khác.

## 2. Tạo danh mục phiên bản của dự án

Ví dụ cấu trúc:

~~~text
project/
├── build.xml
├── versions.properties
├── scripts/
│   ├── antw.sh
│   └── antw.ps1
├── .toolchains/                # bootstrap tạo và xác minh
│   ├── apache-ant-1.10.14/
│   └── jdk-17.0.12+7/
├── vendor/lib/
│   ├── commons-lang3-3.14.0.jar
│   └── commons-lang3-3.14.0.jar.sha256
├── tools/
│   └── protoc/linux-x86_64/bin/protoc
├── src/main/java/
└── dist/
~~~

`versions.properties`:

~~~properties
# Giá trị chỉ để minh họa một bộ đã được chọn, không phải khuyến nghị bản mới nhất.
ant.required=1.10.14

jdk.vendor=Eclipse Adoptium
jdk.version=17.0.12+7
jdk.release=17

commons.lang3.version=3.14.0
protoc.version=25.3
~~~

Ngoài phiên bản, nên có manifest bootstrap ghi **tên artifact, URL/kho nguồn, OS/architecture, SHA-256** của Ant, JDK, các thư viện và công cụ. SHA-256 là dữ liệu kiểm tra toàn vẹn; không dùng chuỗi hash giả trong cấu hình thật. Mỗi binary khác hệ điều hành/kiến trúc có digest riêng.

**Điểm cần chú ý:** Ant cho phép truyền `-Dten.thuoc.tinh=gia-tri` trên CLI, và user property có thể ưu tiên hơn giá trị trong `<property file="versions.properties"/>`. Vì vậy `versions.properties` chỉ là khai báo; CI chính thức phải kiểm soát tham số đầu vào và xác minh toolchain thực tế.

## 3. Cố định bản Ant thực thi

Lệnh `ant` trong terminal thường lấy từ `PATH`. Một máy có Ant của IDE, máy khác có Ant cài qua package manager hoặc bản được thêm vào `PATH` trước. Cùng một lệnh nhưng khác executable.

Quy trình nên dùng:

1. Chọn phiên bản **chính xác**, chẳng hạn Apache Ant 1.10.14.
2. Tải bản phân phối ở nguồn đã phê duyệt, xác minh checksum **trước khi giải nén**.
3. Đặt tại thư mục chuẩn, chẳng hạn `.toolchains/apache-ant-1.10.14/`, hoặc dùng image đã pin digest.
4. Gọi bằng wrapper của dự án: `scripts/antw.sh` hoặc `scripts/antw.ps1`.
5. Có bước kiểm tra runtime bên trong `build.xml` để fail sớm nếu phiên bản khác.

Ant cung cấp `<antversion>`:

~~~xml
<project name="version-demo" default="verify-ant" basedir=".">
    <property file="versions.properties"/>

    <target name="verify-ant">
        <antversion property="ant.version.ok"
                    exactly="${ant.required}"/>
        <fail unless="ant.version.ok"
              message="Sai phien ban Apache Ant; hay chay qua wrapper cua du an."/>
    </target>
</project>
~~~

Kiểm tra phiên bản phát hiện lệch cấu hình, còn **checksum bản phân phối Ant** giúp xác nhận nội dung binary. Không dùng kết quả `ant -version` làm thay thế cho kiểm tra checksum.

### Ngăn thư viện Ant ngầm từ máy cá nhân

Ant có thể nạp task hoặc thư viện từ các vị trí cài đặt và thư viện người dùng. Lệnh chính thức có thể dùng:

~~~bash
"$ANT_HOME/bin/ant" -nouserlib -noclasspath -noinput -f build.xml clean package
~~~

`-nouserlib` ngăn dùng thư viện riêng trong thư mục Ant của người dùng; `-noclasspath` ngăn nạp classpath từ môi trường. Những task bổ sung phải được khai báo với classpath tường minh và kiểm tra binary giống các dependency khác.

Ví dụ khi dự án thật sự có một task tùy biến:

~~~xml
<path id="build.tasks.classpath">
    <pathelement location="tools/antlib/project-ant-task-2.1.0.jar"/>
</path>

<taskdef name="projectTask"
         classname="com.example.build.ProjectTask"
         classpathref="build.tasks.classpath"/>
~~~

Tên class/JAR trong ví dụ là minh họa; khi triển khai phải thay bằng task thực và đưa file JAR của nó vào manifest checksum. Việc dùng classpath tường minh làm rõ task đến từ đâu và giảm phụ thuộc vào cấu hình IDE.

## 4. Phân biệt JDK chạy Ant với phiên bản Java được sinh ra

Cần kiểm soát đồng thời:

- **JVM chạy Ant:** được chọn qua script khởi động và thường gắn với `JAVA_HOME`. Nó ảnh hưởng đến các task chạy trong cùng JVM và Java system properties.
- **JDK của compiler:** `<javac>` có thể dùng compiler của JVM chạy Ant, hoặc một compiler riêng khi dùng `fork`/`executable`.
- **Release của mã biên dịch:** phiên bản bytecode và API chuẩn mà chương trình được phép dùng.

Ví dụ khóa runtime JDK và Java 17 đích:

~~~xml
<target name="verify-jdk">
    <condition property="jdk.runtime.ok">
        <and>
            <equals arg1="${java.vendor}"
                    arg2="${jdk.vendor}"/>
            <equals arg1="${java.runtime.version}"
                    arg2="${jdk.version}"/>
            <equals arg1="${java.specification.version}"
                    arg2="${jdk.release}"/>
        </and>
    </condition>
    <fail unless="jdk.runtime.ok"
          message="JDK runtime khac ban da khoa; kiem tra JAVA_HOME."/>
</target>

<target name="compile" depends="verify-jdk">
    <mkdir dir="build/classes"/>
    <javac srcdir="src/main/java"
           destdir="build/classes"
           release="${jdk.release}"
           encoding="UTF-8"
           includeantruntime="false"
           fork="false"/>
</target>
~~~

Các system property trên phản ánh **JVM đang chạy Ant**. Chuỗi `java.runtime.version` và `java.vendor` có thể khác tùy vendor/phân phối; phải điền giá trị thực của JDK đã chọn, xem bằng `java -XshowSettings:properties -version` từ đúng `JAVA_HOME`. Khóa đến bản vá yêu cầu xác minh binary của JDK, không chỉ so chuỗi.

`release="17"` giúp compiler giới hạn API chuẩn và bytecode cho Java 17. Nó không khóa JDK và cũng không kiểm soát thư viện bên ngoài. Không kết hợp tùy tiện `release` với `source`/`target`; khi dùng compiler hỗ trợ `--release`, ưu tiên một chính sách rõ ràng.

Nếu dùng compiler tách riêng khỏi JVM Ant, cần kiểm tra cả hai:

~~~xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       fork="true"
       executable="${pinned.jdk.home}/bin/javac"
       release="${jdk.release}"
       encoding="UTF-8"
       includeantruntime="false"/>
~~~

Đường dẫn executable trên dành cho hệ Unix; Windows cần đúng binary và phần mở rộng. Khi cấu hình `fork="true"`, kiểm tra `JAVA_HOME` của Ant **không đủ** để khẳng định compiler được gọi có đúng phiên bản.

### Khóa hệ điều hành và bản JDK ở cấp binary

Hai JDK cùng nhãn “17” có thể đến từ hai vendor khác nhau hoặc bản cập nhật khác nhau. Một directory tên `jdk-17` cũng có thể bị thay binary bên trong. Cần ghi nhận vendor, bản phát hành/bản vá, OS/architecture và digest gói JDK.

Trong CI dùng container, nên khóa image bằng digest, chẳng hạn `registry.example/build-jdk@sha256:<digest>`, thay vì chỉ dùng tag động `jdk:17`. Image cũng cần có Ant và công cụ ngoài đúng phiên bản; khóa image không thay thế việc kiểm tra manifest đầu vào.

## 5. Khóa các thư viện và dependency transitive

Một thư viện được mô tả bằng `group:artifact:version`, nhưng **tọa độ không chứng minh bytes**. Kho artifact cho phép overwrite, proxy, cache lỗi hoặc mirror sai có thể trả về JAR khác dù tên không đổi.

Manifest cho một dependency nên có tối thiểu:

~~~text
Artifact: org.apache.commons:commons-lang3:3.14.0
Filename: commons-lang3-3.14.0.jar
Source: <kho artifact được phê duyệt>
SHA-256: <64 ký tự hex của đúng JAR đã phê duyệt>
Scope: compile/runtime
~~~

Với ví dụ vendoring, lưu `vendor/lib/commons-lang3-3.14.0.jar` và file checksum tương ứng `vendor/lib/commons-lang3-3.14.0.jar.sha256`. File checksum chứa giá trị thực theo định dạng mà Ant đọc; không được tự động “chấp nhận” binary mới bằng cách ghi đè checksum khi verify thất bại.

Ant hỗ trợ điều kiện `<checksum>`:

~~~xml
<property name="lib.dir" location="vendor/lib"/>

<target name="verify-library">
    <available file="${lib.dir}/commons-lang3-${commons.lang3.version}.jar"
               property="commons.jar.exists"/>
    <fail unless="commons.jar.exists"
          message="Thieu commons-lang3 da khoa."/>

    <condition property="commons.jar.sha256.ok">
        <checksum file="${lib.dir}/commons-lang3-${commons.lang3.version}.jar"
                  algorithm="SHA-256"
                  fileext=".sha256"/>
    </condition>
    <fail unless="commons.jar.sha256.ok"
          message="Checksum cua commons-lang3 khong khop."/>
</target>
~~~

File `.sha256` phải tồn tại trước bước verify và chứa digest chính xác (thông thường một dòng hex theo pattern mặc định của Ant). Nên khai báo classpath từ tập dependency đã khóa:

~~~xml
<path id="compile.classpath">
    <pathelement
        location="${lib.dir}/commons-lang3-${commons.lang3.version}.jar"/>
</path>

<javac srcdir="src/main/java"
       destdir="build/classes"
       release="${jdk.release}"
       encoding="UTF-8"
       includeantruntime="false"
       classpathref="compile.classpath"/>
~~~

Cẩn thận với `<fileset dir="lib" includes="**/*.jar"/>`: nó có thể hút thêm JAR không nằm trong manifest. Nếu phải dùng fileset, cần đối chiếu **cả tập tên file lẫn digest** với lock file và fail khi có JAR ngoài danh mục.

### Dùng Apache Ivy hoặc cơ chế resolve động

Nếu Ant dùng Ivy để tải dependency, khóa danh sách khai báo trực tiếp vẫn chưa đủ. Build phát hành nên:

1. Tránh `latest.integration`, dải phiên bản mở và `SNAPSHOT` có thể thay đổi.
2. Khóa cả **dependency transitive** đã chọn, classifier, artifact đặc biệt và checksum từng file.
3. Ghi rõ repository/resolver được phép, chính sách cache và mirror.
4. Xác minh tập artifact sau resolve với lock/manifest được duyệt; khi drift thì dừng build.
5. Thử khả năng dựng lại từ cache sạch hoặc môi trường offline đã chuẩn bị để phát hiện đầu vào ngầm.

Nếu công cụ resolve chưa hỗ trợ lock bất biến theo yêu cầu, có thể tạo manifest từ lần resolve đã phê duyệt và viết bước kiểm tra danh sách/digest; không giả định việc khai báo một version trong `ivy.xml` tự động khóa toàn bộ đồ thị dependency.

**Thư viện của Ant task**, code generator và plugin build cũng phải được pin như thư viện ứng dụng. Chúng ảnh hưởng tới kết quả build dù không được đóng gói vào artifact cuối.

## 6. Khóa các công cụ ngoài gọi qua `<exec>`

Một lệnh như sau lấy binary `protoc` từ `PATH` và phụ thuộc vào máy đang chạy:

~~~xml
<exec executable="protoc" failonerror="true">
    <arg value="--version"/>
</exec>
~~~

Cách được kiểm soát là provision `protoc` đúng OS/architecture từ một artifact có checksum, rồi dùng đường dẫn cụ thể:

~~~xml
<property name="protoc.executable"
          location="tools/protoc/linux-x86_64/bin/protoc"/>

<target name="verify-protoc">
    <available file="${protoc.executable}"
               property="protoc.exists"/>
    <fail unless="protoc.exists"
          message="Thieu protoc theo manifest."/>

    <exec executable="${protoc.executable}"
          failonerror="true"
          outputproperty="protoc.actual">
        <arg value="--version"/>
    </exec>

    <condition property="protoc.version.ok">
        <equals arg1="${protoc.actual}"
                arg2="libprotoc ${protoc.version}"
                trim="true"/>
    </condition>
    <fail unless="protoc.version.ok"
          message="protoc khac phien ban da khoa."/>
</target>
~~~

Đây là ví dụ cho Linux x86_64. Trên Windows hoặc macOS, bootstrap phải chọn artifact đúng nền tảng. Kiểm tra `--version` phát hiện sai phiên bản khi chạy, còn SHA-256 xác minh đúng binary **trước khi chạy**. Hai binary khác nhau có thể in cùng một chuỗi version.

Nguyên tắc tương tự áp dụng cho `node`, `npm`, `git`, công cụ ký, generator và trình nén. Công cụ có plugin riêng thì cần khóa cả plugin, không chỉ executable chính.

## 7. Wrapper của dự án để loại bỏ sự phụ thuộc vào `PATH`

Ant không có wrapper tiêu chuẩn tích hợp như Gradle Wrapper. Có thể viết script mỏng dùng toolchain đã được bootstrap và kiểm tra checksum.

Ví dụ `scripts/antw.sh`:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export JAVA_HOME="$repo_dir/.toolchains/jdk-17.0.12+7"
export ANT_HOME="$repo_dir/.toolchains/apache-ant-1.10.14"
unset CLASSPATH

exec "$ANT_HOME/bin/ant" \
  -nouserlib -noclasspath -noinput \
  -f "$repo_dir/build.xml" "$@"
~~~

Ví dụ `scripts/antw.ps1` cho Windows:

~~~powershell
$repoDir = Split-Path -Parent $PSScriptRoot
$env:JAVA_HOME = Join-Path $repoDir '.toolchains\jdk-17.0.12+7'
$env:ANT_HOME = Join-Path $repoDir '.toolchains\apache-ant-1.10.14'

Remove-Item Env:CLASSPATH -ErrorAction SilentlyContinue

& (Join-Path $env:ANT_HOME 'bin\ant.bat') `
    -nouserlib -noclasspath -noinput `
    -f (Join-Path $repoDir 'build.xml') @args

exit $LASTEXITCODE
~~~

Đường dẫn trong hai ví dụ là minh họa. Thực tế phải dùng các bản phân phối phù hợp hệ điều hành và đặt checksum pinning trong bước bootstrap. Cũng cần thống nhất version trong wrapper với manifest, tránh sửa một nơi mà bỏ sót nơi khác.

Có thể kiểm tra SHA-256 của gói tải về bằng:

~~~bash
sha256sum apache-ant-1.10.14-bin.tar.gz
~~~

hoặc PowerShell:

~~~powershell
(Get-FileHash -LiteralPath '.\apache-ant-1.10.14-bin.zip' -Algorithm SHA256).Hash
~~~

**Phải so sánh tự động với digest được phê duyệt và dừng khi khác**. Chỉ in digest ra console chưa bảo vệ được build.

## 8. Tạo cổng xác minh trước mọi công việc biên dịch

Các target chính cần phụ thuộc vào một cổng xác minh, để không có nhánh phát hành nào vượt qua kiểm tra môi trường.

Ví dụ sau cho thấy cách nối các target **đã định nghĩa tại các phần trước**; khi dùng phải hợp nhất vào một `build.xml` hoàn chỉnh, không khai báo lặp project hoặc target:

~~~xml
<target name="verify"
        depends="verify-ant,verify-jdk,verify-library,verify-protoc"/>

<target name="compile" depends="verify">
    <mkdir dir="build/classes"/>
    <javac srcdir="src/main/java"
           destdir="build/classes"
           release="${jdk.release}"
           encoding="UTF-8"
           includeantruntime="false"
           classpathref="compile.classpath"/>
</target>

<target name="package" depends="compile">
    <mkdir dir="dist"/>
    <jar destfile="dist/app.jar" basedir="build/classes"/>
</target>
~~~

Luồng xử lý:

~~~mermaid
flowchart TD
    A["Nạp manifest phiên bản và checksum"] --> B["Bootstrap Ant, JDK, JAR và công cụ đã khóa"]
    B --> C{"Bytes và môi trường hợp lệ?"}
    C -->|Không| X["Dừng: báo đầu vào lệch"]
    C -->|Có| D["Chạy Ant verify-*"]
    D --> E{"Version và classpath đúng?"}
    E -->|Không| X
    E -->|Có| F["Sinh mã, biên dịch, kiểm thử, đóng gói"]
    F --> G["Lưu SHA-256 artifact và thông tin build"]
~~~

Đối với build phát hành, không cho phép target tạo artifact bỏ qua `verify`. Tránh cơ chế tự tải “phiên bản mới nhất” ngay trong target build; nếu buộc tải dữ liệu, phải dùng artifact ID và hash đã khóa.

## 9. Những yếu tố còn có thể phá tính tái lập

Khóa Ant/JDK/JAR/tool là chưa đủ khi các đầu vào khác vẫn thay đổi:

| Yếu tố | Ví dụ ảnh hưởng | Hướng kiểm soát |
|---|---|---|
| `ANT_OPTS`, `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS` | Truyền JVM flags, encoding hoặc agent ngoài ý muốn | Quy định chính sách biến môi trường và chỉ log thông tin không nhạy cảm |
| `CLASSPATH`, `ANT_HOME`, `PATH` | Chọn task, JDK hoặc executable khác | Wrapper và classpath tường minh |
| Locale, timezone, charset | Sinh text, ngày giờ, sắp xếp khác nhau | Quy định locale/timezone; đặt encoding cho mọi task đọc/ghi text |
| Workspace bẩn | File đã build từ lần trước lọt vào output | Tạo workspace sạch, xác định đúng thư mục input/output |
| Repository và cache | Đọc binary khác cùng version hoặc phụ thuộc cache cũ | Pin digest và thử bootstrap từ cache sạch |
| ZIP/JAR timestamp, file order | Class giống nhau nhưng SHA-256 JAR khác | Chuẩn hóa metadata, mốc thời gian và thứ tự entry |
| OS và kiến trúc | Thư viện native và tool khác bytes | Khóa build platform hoặc chuẩn hóa được các đầu ra |
| Mã sinh tự động | Generator chèn thời gian, path hoặc version động | Cố định input của generator và làm cho output ổn định |

Đối với tái lập từng byte, có thể dùng `SOURCE_DATE_EPOCH` như mốc thời gian thống nhất **nếu từng task/tool thực sự hỗ trợ hoặc được cấu hình dùng giá trị đó**. Chỉ đặt biến này không tự động loại bỏ timestamp trong JAR/ZIP. Manifest, chữ ký, thứ tự entry và compiler output cũng cần kiểm soát.

Một chương trình có hành vi giống nhau chưa chắc có JAR cùng hash. Nên đánh giá chức năng và tính đồng nhất byte bằng hai phép kiểm tra riêng khi chính sách phát hành yêu cầu.

## 10. Quy trình nâng phiên bản có kiểm soát

1. **Lập thay đổi:** ghi thành phần được nâng, phiên bản cũ/mới và lý do; xem tương thích giữa Ant, JDK, Ant tasks và compiler.
2. **Nhận và xác minh binary:** ghi URL hoặc artifact ID, SHA-256, vendor, OS/architecture của mọi gói được thay.
3. **Cập nhật đồng bộ:** sửa `versions.properties`, manifest bootstrap, sidecar checksum, lock dependency, wrapper và các đường dẫn cần thiết trong một thay đổi có thể review.
4. **Build từ môi trường sạch:** dùng đúng wrapper, xóa ảnh hưởng của thư viện cục bộ, restore dependency từ nguồn được duyệt.
5. **Kiểm tra kết quả:** chạy compiler, test, code generator và đóng gói; nếu yêu cầu tái lập byte, so SHA-256 artifact từ hai build sạch.
6. **Lưu dấu vết:** commit các file khóa cùng nhau, giữ log và hash artifact có thể truy nguyên.

Không chấp nhận thao tác chỉ đổi tên folder từ `jdk-17.0.11` sang `jdk-17.0.12` mà không xác minh binary, hoặc tải lại JAR mới rồi tự ghi checksum mới không qua review. Khi đổi JDK major, phiên bản Ant và task hiện tại có thể cần nâng tương ứng; không được suy luận chỉ từ Java release của ứng dụng.

### Các tình huống chẩn đoán thường gặp

| Hiện tượng | Nguyên nhân nên kiểm tra |
|---|---|
| Máy cá nhân chạy được, CI báo `taskdef not found` | Task JAR đang lấy từ thư viện Ant cục bộ |
| Lỗi `Unsupported class file major version` | JVM Ant hoặc compiler không tương thích bytecode của task/thư viện |
| Code dùng nhầm API Java mới | `release` chưa được chỉ định, hoặc compiler không phải bản đã khóa |
| Lỗi `ClassNotFoundException` không nhất quán | Classpath bị thay đổi, thiếu transitive JAR hoặc JAR không đúng digest |
| `protoc` tạo file khác ở CI | Executable được tìm từ `PATH` hoặc toolchain khác OS/version |
| Hai JAR giống chức năng nhưng khác SHA-256 | Timestamp, metadata ZIP, thứ tự file, manifest hoặc compiler khác |
| Chỉ build được khi cache đã ấm | Dependency chưa pin hoặc nguồn tải/cấu hình resolver thiếu rõ ràng |

## 11. Lưu bằng chứng cho mỗi bản build chính thức

Một build có thể tái hiện cần có thông tin để người khác khôi phục **đúng đầu vào**:

~~~text
Source commit: <Git commit cụ thể>
Build: <target, tham số được phép, trạng thái>
Ant: <version, checksum bản phân phối>
JDK: <vendor, runtime version, OS/architecture, checksum>
Java release: <giá trị biên dịch>
Libraries: <danh sách resolved dependency và SHA-256 từng artifact>
Ant tasks: <phiên bản, SHA-256 JAR task>
External tools: <binary, version, OS/architecture, SHA-256>
Environment: <image digest hoặc toolchain manifest>
Output: <tên artifact, SHA-256>
~~~

Nếu lưu bản ghi tự động, loại bỏ token, mật khẩu và dữ liệu nhạy cảm khỏi log. Có thể đóng gói manifest máy đọc được cùng artifact hoặc lưu trong hệ thống phát hành để tra cứu sau này.

Khi kiểm soát tốt, nhóm phát triển trả lời được năm câu hỏi: **Ant nào đã chạy? JDK nào đã biên dịch? Những JAR và binary nào thực sự được dùng? Chúng có đúng checksum được duyệt không? Có thể dựng lại cùng đầu vào trên một máy sạch như thế nào?** Cổng xác minh tự động khiến những câu trả lời đó trở thành bằng chứng kiểm chứng được, thay vì phụ thuộc vào cấu hình của từng máy.

