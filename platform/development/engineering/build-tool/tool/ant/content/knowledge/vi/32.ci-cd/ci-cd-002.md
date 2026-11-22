# Chuẩn bị agent với Ant, JDK và công cụ ngoài đã xác định phiên bản

Khi đưa dự án **Apache Ant** lên hệ thống **CI/CD**, việc checkout cùng mã nguồn và chạy cùng `build.xml` chưa đủ để tạo kết quả đáng tin cậy. Một agent có thể cài Ant khác phiên bản, dùng nhầm JDK từ `PATH`, tự tải thư viện build ngoài danh mục hoặc gọi `protoc` và `node` với những phiên bản khác máy lập trình viên. Hậu quả là lỗi biên dịch khó tái hiện, kết quả test không ổn định, artifact khác nhau hoặc job phát hành thành công trong một môi trường nhưng thất bại ở môi trường khác.

Để **chuẩn bị agent có thể tái tạo**, nhóm cần coi bộ công cụ build là một tập đầu vào được quản lý: **phiên bản đã duyệt, binary tương ứng, nguồn tải, checksum, đường dẫn thực thi, cấu hình môi trường và dấu vết sau build**. Bài học này tập trung vào cách thực hiện hợp đồng đó cho Ant, JDK và công cụ ngoài trong CI/CD.

## 1. Agent CI/CD là một phần của môi trường build

*Agent* hay *runner* là máy ảo, máy vật lý hoặc container thực thi job: checkout, khởi tạo toolchain, biên dịch, kiểm thử, đóng gói và xuất bản artifact.

| Loại agent | Ưu điểm | Rủi ro |
|---|---|---|
| Hosted runner dùng một lần | Môi trường tương đối sạch giữa các job | Image mặc định và các công cụ có sẵn có thể được nhà cung cấp thay đổi |
| Self-hosted runner dùng lâu dài | Cài sẵn toolchain lớn, cache nhanh và truy cập mạng nội bộ | Phiên bản, cache, biến môi trường và quyền ghi có thể thay đổi sau từng job |
| Runner dùng container image | Đóng gói toolchain thành một image để phân phối thống nhất | Tag động có thể trỏ đến image mới; nội dung image phải được khóa bằng digest |
| Runner khởi tạo bằng script bootstrap | Có thể dựng lại từ manifest và artifact đã xác minh | Tải về và giải nén mất thời gian, script phải xử lý checksum/OS/architecture đúng |

Mỗi job cần trả lời được ba câu hỏi:

1. **Dùng phiên bản nào?** Không chỉ “JDK 21”, mà là vendor và phiên bản đầy đủ, ví dụ một bản vá JDK xác định.
2. **Có đúng binary không?** File được lấy từ nguồn nào, checksum SHA-256 có khớp bản đã duyệt không?
3. **Đã chạy đúng binary chưa?** Ant, Java, compiler và công cụ gọi bởi `<exec>` có sử dụng đường dẫn đã xác minh không?

Việc chỉ in `ant -version` hoặc `java -version` ra log không trả lời đủ cả ba câu hỏi. Hai binary khác nhau có thể cùng báo một phiên bản, và một JDK được cài đúng chưa chắc là JDK được Ant thực sự dùng.

## 2. Lập danh mục những đầu vào phải khóa

Một build Ant có thể chứa nhiều lớp công cụ:

| Đầu vào | Thông tin nên lưu | Vì sao cần |
|---|---|---|
| **Apache Ant** | Phiên bản cụ thể, URL/artifact ID, SHA-256 | Đảm bảo task chạy trên bản Ant dự kiến |
| **JDK chạy Ant** | Vendor, bản phát hành đầy đủ, OS/CPU architecture và SHA-256 | Ảnh hưởng trực tiếp JVM của Ant và các Java task in-process |
| **Compiler JDK** | Executable và phiên bản riêng nếu `<javac fork="true">` | Có thể khác JDK chạy Ant |
| **Java release đầu ra** | `javac release="17"` hoặc giá trị phù hợp | Quy định API Java chuẩn và class file target |
| **Ant task JAR** | Tên artifact, phiên bản và checksum | Task bổ sung có thể đến từ `ANT_HOME/lib` hoặc `taskdef` |
| **Thư viện ứng dụng** | Direct/transitive dependency, phiên bản, checksum | Tránh classpath và bytecode khác nhau |
| **Công cụ ngoài** | Version, binary, digest, OS/arch | Bao gồm `protoc`, `node`, `python`, `zip`, generator khác |
| **Image/môi trường** | Image digest, OS, arch, locale, timezone quan trọng | Giảm sai lệch do runner update |
| **Nguồn build** | Git commit SHA và tham số build | Cùng branch name vẫn có thể trỏ tới commit khác |

Ví dụ một danh mục phiên bản đọc được trong `versions.properties`:

~~~properties
# Giá trị chỉ minh họa, không phải các phiên bản mới nhất.
ant.required=1.10.14
jdk.release=21
protoc.required=25.3
~~~

File này phù hợp cho target Ant xác minh phiên bản chạy. Tuy nhiên, nó **chưa đủ** để bootstrap agent: còn thiếu URL cụ thể, checksum, vendor, bản vá JDK và nền tảng. Cần thêm manifest được quản lý trong cùng repository, chẳng hạn:

~~~yaml
# Ví dụ cấu trúc. Thay mọi placeholder bằng dữ liệu thật đã xác minh.
platform: linux-x86_64
ant:
  version: "1.10.14"
  artifact: "apache-ant-1.10.14-bin.tar.gz"
  source: "https://artifacts.example.org/ant/apache-ant-1.10.14-bin.tar.gz"
  sha256: "<SHA-256 thật>"
jdk:
  vendor: "Eclipse Adoptium"
  runtimeVersion: "21.0.5+11"
  source: "<URL artifact JDK cố định cho Linux x86_64>"
  sha256: "<SHA-256 thật>"
externalTools:
  protoc:
    version: "25.3"
    source: "<URL binary protoc cố định cho Linux x86_64>"
    sha256: "<SHA-256 thật>"
~~~

Không sử dụng placeholder trong CI thật. Một bước parse/validate manifest phải từ chối phiên bản rỗng, URL không được duyệt hoặc checksum không hợp lệ. Khi dự án hỗ trợ nhiều nền tảng, mỗi bộ `OS + architecture` cần URL và SHA-256 tương ứng; không suy diễn rằng file Linux và Windows có cùng digest.

**Version và checksum có vai trò khác nhau:** version mô tả release mong muốn; checksum xác nhận bytes thực tế. Khi kho trung gian, cache hoặc mirror trả về nhầm file, kiểm tra version qua tên tệp có thể không phát hiện lỗi nhưng đối chiếu SHA-256 sẽ phát hiện.

## 3. Hai chiến lược chính để cung cấp toolchain

### A. Dựng toolchain bằng bootstrap ở đầu job

Luồng thao tác:

1. Checkout đúng commit, gồm cả manifest và checksum.
2. Xác định nền tảng agent và chọn artifact trong danh mục.
3. Tải JDK, Ant và các công cụ cần thiết từ URL đã duyệt.
4. Đối chiếu SHA-256 của từng gói **trước khi giải nén hoặc thực thi**.
5. Cài vào thư mục riêng của job hoặc vị trí chỉ đọc, có version/digest rõ ràng.
6. Cấu hình `JAVA_HOME`, `ANT_HOME` và đường dẫn của các công cụ ngoài.
7. Chạy bước xác minh lại runtime trước mọi target sinh artifact.

Ưu điểm là agent mới có thể dựng môi trường từ nguồn xác định, không phụ thuộc vào các package đã cài sẵn. Đổi lại, chi phí tải và giải nén JDK/SDK lớn có thể đáng kể, nên thường kết hợp cache có khóa bằng digest.

### B. Sử dụng image chứa sẵn toolchain

Một image CI có thể chứa Ant, JDK và công cụ ngoài đúng phiên bản. Cần tham chiếu image bằng digest bất biến thay vì chỉ một tag động:

~~~text
registry.example.org/ci/ant-jdk:ant-1.10.14-jdk21@sha256:<DIGEST_THỰC_TẾ>
~~~

Đây là dạng định danh minh họa; phải thay bằng digest image thật. Image cần được xây từ các artifact đã kiểm tra checksum và cập nhật qua một thay đổi được review. Job vẫn nên chạy xác minh runtime bởi một image có tên hợp lệ không chứng minh script đã sử dụng đúng executable.

Một tag như `jdk:21` hoặc `ant:latest` có thể thay đổi khi nhà cung cấp phát hành bản mới. Khóa digest sẽ cố định image đã chọn, nhưng cần nhớ rằng **nguồn build, dependency và các tài nguyên tải trong lúc chạy** cũng phải được kiểm soát.

### Self-hosted agent cần một hợp đồng tương tự

Khi agent là máy dùng lâu dài, không nên xem folder `/opt/java` hoặc `C:\Java` là bằng chứng về bản JDK. Một người quản trị có thể cập nhật binary, job khác có thể làm biến đổi cache hoặc thêm task JAR. Cần quy định quyền sửa toolchain, kiểm tra trước mỗi job và tránh cho hai job đồng thời cùng ghi vào một thư mục đang được dùng để build.

## 4. Bootstrap Apache Ant có xác minh SHA-256

Một cấu trúc dự án tham khảo:

~~~text
project/
├── build.xml
├── versions.properties
├── ci/
│   ├── toolchains.lock
│   ├── checksums/
│   │   └── apache-ant-1.10.14-bin.tar.gz.sha256
│   ├── bootstrap-toolchain.sh
│   ├── verify-toolchain.sh
│   └── antw.sh
├── .toolchains/              # được tạo sau bootstrap
├── tools/antlib/             # các task JAR bổ sung đã khóa
└── src/
~~~

File `ci/checksums/apache-ant-1.10.14-bin.tar.gz.sha256` chứa một dòng theo chuẩn `sha256sum -c`:

~~~text
<64 ký tự hex SHA-256 thực tế>  apache-ant-1.10.14-bin.tar.gz
~~~

Dòng trên là **mẫu định dạng**, không phải digest sử dụng được. Phải điền SHA-256 đã được phê duyệt theo đúng gói tải về.

Đoạn `ci/bootstrap-toolchain.sh` sau dành cho Linux, minh họa riêng khâu cài Ant:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ant_version="1.10.14"
ant_archive="apache-ant-${ant_version}-bin.tar.gz"
artifact_base="https://artifacts.example.org/ant"

download_dir="${repo_dir}/.toolchains/downloads"
install_dir="${repo_dir}/.toolchains"

mkdir -p "$download_dir" "$install_dir"

curl --fail --location --show-error --silent --retry 3 \
    "${artifact_base}/${ant_archive}" \
    --output "${download_dir}/${ant_archive}"

(
    cd "$download_dir"
    sha256sum --check \
        "${repo_dir}/ci/checksums/apache-ant-1.10.14-bin.tar.gz.sha256"
)

tar -xzf "${download_dir}/${ant_archive}" -C "$install_dir"

test -x "${install_dir}/apache-ant-${ant_version}/bin/ant"
"${install_dir}/apache-ant-${ant_version}/bin/ant" -version
~~~

Ví dụ yêu cầu URL và checksum hợp lệ được cấu hình từ nguồn tin cậy. Bước `sha256sum --check` sẽ dừng script khi digest khác vì `set -e` đang bật. Không đặt lệnh `curl | sh` chạy script tải động nếu không xác minh nội dung. Việc chỉ in checksum ra console mà không so sánh cũng chưa phải kiểm tra toàn vẹn.

Với môi trường có job chạy song song, nên tải/giải nén vào thư mục tạm riêng, kiểm tra xong mới chuyển sang vị trí chính, hoặc dùng thư mục theo digest không thể bị ghi đè. Với JDK và công cụ ngoài, trình tự kiểm tra tương tự nhưng phải xử lý riêng cấu trúc archive và binary cho từng OS/architecture.

## 5. Gọi Ant qua wrapper sử dụng toolchain đã duyệt

Apache Ant không có wrapper tiêu chuẩn tích hợp tương tự Gradle Wrapper. Nếu pipeline đơn giản gọi `ant`, hệ điều hành sẽ tìm executable theo `PATH` và có thể chọn một bản cài đặt không thuộc dự án. Giải pháp là một script ngắn chọn JDK và Ant đã được bootstrap, rồi gọi chúng bằng đường dẫn cụ thể.

Ví dụ `ci/antw.sh` trên Linux:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export JAVA_HOME="${repo_dir}/.toolchains/temurin-21.0.5+11"
export ANT_HOME="${repo_dir}/.toolchains/apache-ant-1.10.14"

test -x "${JAVA_HOME}/bin/java"
test -x "${JAVA_HOME}/bin/javac"
test -x "${ANT_HOME}/bin/ant"

export PATH="${JAVA_HOME}/bin:${ANT_HOME}/bin:/usr/bin:/bin"
unset CLASSPATH ANT_OPTS JAVA_TOOL_OPTIONS JDK_JAVA_OPTIONS

exec "${ANT_HOME}/bin/ant" \
    -nouserlib -noclasspath -noinput \
    -f "${repo_dir}/build.xml" "$@"
~~~

Các tên thư mục chỉ là quy ước minh họa; bootstrap phải tạo đúng cấu trúc và đã xác minh digest của binary. Nếu dự án cần JVM options riêng, khai báo chúng từ cấu hình được quản lý thay vì nhận các giá trị không biết có sẵn trên agent.

Hai tùy chọn giúp giảm ảnh hưởng từ agent: `-nouserlib` ngăn nạp JAR từ thư viện Ant riêng của tài khoản; `-noclasspath` tránh lấy classpath ngầm từ môi trường. Chúng không loại bỏ JAR nằm sẵn trong `ANT_HOME/lib`, nên toàn bộ nội dung bản phân phối Ant và các task bổ sung vẫn phải được kiểm soát.

Ví dụ PowerShell trên Windows:

~~~powershell
$repoDir = Split-Path -Parent $PSScriptRoot

$env:JAVA_HOME = Join-Path $repoDir '.toolchains\temurin-21.0.5+11'
$env:ANT_HOME = Join-Path $repoDir '.toolchains\apache-ant-1.10.14'

$java = Join-Path $env:JAVA_HOME 'bin\java.exe'
$ant = Join-Path $env:ANT_HOME 'bin\ant.bat'

if (-not (Test-Path -LiteralPath $java)) {
    throw 'JDK da khoa khong ton tai'
}
if (-not (Test-Path -LiteralPath $ant)) {
    throw 'Ant da khoa khong ton tai'
}

Remove-Item Env:CLASSPATH -ErrorAction SilentlyContinue

& $ant -nouserlib -noclasspath -noinput `
    -f (Join-Path $repoDir 'build.xml') @args

exit $LASTEXITCODE
~~~

Wrapper Windows cũng phải đi cùng bootstrap và kiểm tra SHA-256 dành riêng cho Windows. Việc file tồn tại và chạy được không thay thế kiểm tra toàn vẹn.

## 6. Xác minh Ant và JDK trước target build

Agent nên có hai tầng kiểm tra:

1. **Integrity:** gói Ant, JDK và executable có digest chính xác với manifest.
2. **Effective runtime:** Ant, JVM và compiler thực tế là các phiên bản, vendor và đường dẫn đã được duyệt.

Các lệnh chẩn đoán dùng đường dẫn tuyệt đối:

~~~bash
"$JAVA_HOME/bin/java" -version
"$JAVA_HOME/bin/javac" -version
"$ANT_HOME/bin/ant" -version
"$PROTOC_HOME/bin/protoc" --version
~~~

Chỉ ghi log chưa đủ: `ci/verify-toolchain.sh` cần so sánh version/runtime thực tế với giá trị đã khóa và thoát với mã lỗi khác 0 nếu lệch.

Một cổng xác minh bên trong `build.xml`:

~~~xml
<project name="ant-ci-demo" default="package" basedir=".">
    <property file="versions.properties"/>

    <target name="verify-ant">
        <antversion property="ant.version.ok"
                    exactly="${ant.required}"/>
        <fail unless="ant.version.ok"
              message="Sai phien ban Ant; hay dung wrapper cua du an"/>
    </target>

    <target name="verify-java-release">
        <condition property="java.release.ok">
            <equals arg1="${java.specification.version}"
                    arg2="${jdk.release}"/>
        </condition>
        <fail unless="java.release.ok"
              message="Java chay Ant khac release du kien"/>
    </target>

    <target name="verify-environment"
            depends="verify-ant,verify-java-release"/>

    <target name="compile" depends="verify-environment">
        <mkdir dir="build/classes"/>
        <javac srcdir="src/main/java"
               destdir="build/classes"
               includeantruntime="false"
               encoding="UTF-8"
               release="${jdk.release}"/>
    </target>

    <target name="package" depends="compile">
        <mkdir dir="dist"/>
        <jar destfile="dist/app.jar" basedir="build/classes"/>
    </target>
</project>
~~~

Đoạn ví dụ xác minh `java.specification.version` ở cấp major release. Nó **chưa** xác minh bản vá JDK 21.0.5+11 hoặc vendor; cần bổ sung đối chiếu `java.vendor`, `java.runtime.version` và/hoặc checksum binary trong script verify độc lập. Định dạng chuỗi version có thể khác nhau giữa các vendor.

Ba khái niệm cần tách riêng:

- **JVM chạy Ant:** do launcher và `JAVA_HOME` quyết định.
- **Compiler được gọi:** `<javac>` có thể dùng compiler trong process Ant hoặc binary chỉ định qua `fork="true" executable="..."`.
- **Release đích:** `release="..."` quy định API Java chuẩn và bytecode, không khóa binary compiler.

Khi dùng compiler fork riêng, script CI phải kiểm tra **cả hai bộ JDK** nếu chúng khác nhau. Ngoài ra, tham số Ant dạng `-Dten=giatri` có thể ưu tiên hơn giá trị trong `versions.properties`; đừng để job tùy tiện ghi đè property dùng làm cổng xác minh. Bước verify độc lập ở mức script/image giúp phát hiện sai lệch sớm.

## 7. Khóa JAR của Ant task và dependency ứng dụng

Một project có thể dùng Ant task bổ sung từ `~/.ant/lib`, `ANT_HOME/lib` hoặc `<taskdef>`. Nếu task JAR chỉ tồn tại trên máy cá nhân, build trên agent sạch có thể báo thiếu class hoặc chạy bản khác.

Dùng classpath riêng có khóa checksum:

~~~xml
<path id="team.task.classpath">
    <pathelement location="tools/antlib/team-task-2.0.0.jar"/>
</path>

<taskdef name="teamTask"
         classname="org.example.build.TeamTask"
         classpathref="team.task.classpath"/>
~~~

Tên class/JAR chỉ để minh họa; dự án phải thay bằng JAR thực và lưu SHA-256 đã duyệt. Ant có thể dùng `<checksum>` để xác minh một JAR khi file checksum sidecar đã tồn tại:

~~~xml
<target name="verify-team-task-jar">
    <available file="tools/antlib/team-task-2.0.0.jar"
               property="team.task.exists"/>
    <fail unless="team.task.exists"
          message="Thieu Ant task JAR da khoa"/>

    <condition property="team.task.sha256.ok">
        <checksum file="tools/antlib/team-task-2.0.0.jar"
                  algorithm="SHA-256"
                  fileext=".sha256"/>
    </condition>
    <fail unless="team.task.sha256.ok"
          message="Checksum Ant task JAR khong khop"/>
</target>
~~~

Sidecar `tools/antlib/team-task-2.0.0.jar.sha256` phải chứa digest thật theo định dạng Ant đọc. Không tự ghi lại digest khi phát hiện JAR khác, vì như thế bước verify mất ý nghĩa.

Thư viện ứng dụng cũng cần danh sách artifact trực tiếp **và transitive**. Nếu Ant sử dụng Ivy hoặc resolver tương tự, tránh các version động như `latest.integration`, dải version mở và snapshot có thể ghi đè trong pipeline phát hành. Cần kiểm tra kết quả resolve so với lock/manifest đã duyệt, gồm repository, artifact ID, version và checksum của từng binary.

Cần cẩn thận với classpath dùng `<fileset includes="**/*.jar">`: file JAR ngoài manifest có thể được thêm vào bởi cache hoặc job khác. Với yêu cầu tái lập, nên xác minh cả **tập tên file** và digest, thay vì chỉ kiểm tra vài JAR quen thuộc.

## 8. Khóa công cụ ngoài được Ant gọi qua <exec>

Một build có thể gọi `protoc`, `node`, `npm`, `git`, `python`, chương trình tạo mã, trình nén hay công cụ ký. Câu lệnh sau phụ thuộc vào binary được tìm từ `PATH`:

~~~xml
<exec executable="protoc" failonerror="true">
    <arg value="--version"/>
</exec>
~~~

Sau khi bootstrap binary đúng OS/architecture và xác minh SHA-256, khai báo executable tường minh:

~~~xml
<property name="protoc.executable"
          location=".toolchains/protoc-25.3/bin/protoc"/>

<target name="verify-protoc">
    <available file="${protoc.executable}"
               property="protoc.exists"/>
    <fail unless="protoc.exists"
          message="Thieu protoc da khoa"/>

    <exec executable="${protoc.executable}"
          failonerror="true"
          outputproperty="protoc.actual">
        <arg value="--version"/>
    </exec>

    <condition property="protoc.version.ok">
        <equals arg1="${protoc.actual}"
                arg2="libprotoc ${protoc.required}"
                trim="true"/>
    </condition>
    <fail unless="protoc.version.ok"
          message="Sai phien ban protoc"/>
</target>
~~~

Đường dẫn trên dành cho bố cục Linux ví dụ; Windows thường cần executable `protoc.exe`. **Chuỗi version** giúp phát hiện đang chạy sai tool, còn **checksum** chứng minh binary đúng bytes đã duyệt. Khi công cụ có plugin hoặc package kèm theo, manifest phải khóa cả các thành phần ấy chứ không chỉ executable chính.

## 9. Đưa chuẩn bị toolchain thành một giai đoạn bắt buộc của CI/CD

Các bước nên chạy theo một thứ tự rõ ràng:

~~~mermaid
flowchart TD
    A["Checkout đúng commit"] --> B["Đọc lock/manifest trong commit"]
    B --> C["Chọn artifact theo OS/architecture"]
    C --> D["Tải hoặc lấy từ cache theo digest"]
    D --> E{"Checksum/digest hợp lệ?"}
    E -->|Không| X["Fail job, báo đầu vào sai"]
    E -->|Có| F["Thiết lập JAVA_HOME, ANT_HOME và tool paths"]
    F --> G{"Runtime/version thực tế khớp?"}
    G -->|Không| X
    G -->|Có| H["Ant clean, compile, test, package"]
    H --> I{"Build/test thành công?"}
    I -->|Không| Y["Dừng publish và lưu log lỗi"]
    I -->|Có| J["Lưu artifact, checksum và provenance"]
    J --> K["Bước phát hành theo chính sách CI/CD"]
~~~

Bước verify phải diễn ra **trước bất cứ target nào sinh mã, biên dịch hoặc đóng gói**. Nếu chỉ kiểm tra version ở bước deploy, artifact đã có thể được tạo từ môi trường sai.

### Ví dụ pipeline GitHub Actions

Đây là cấu trúc để tham khảo, giả định repository đã triển khai các script bootstrap và verify cho **tất cả** toolchain trong manifest:

~~~yaml
name: Apache Ant CI

on:
  push:
  pull_request:

jobs:
  build:
    runs-on: ubuntu-24.04
    steps:
      - name: Checkout source
        uses: actions/checkout@v4

      - name: Install pinned Ant, JDK and external tools
        shell: bash
        run: ./ci/bootstrap-toolchain.sh

      - name: Verify toolchain version and checksums
        shell: bash
        run: ./ci/verify-toolchain.sh

      - name: Build and test with project wrapper
        shell: bash
        run: ./ci/antw.sh clean test package

      - name: Record artifact checksum
        shell: bash
        run: sha256sum dist/app.jar
~~~

**Đây là skeleton về thứ tự công việc**, chưa phải file có thể chạy nguyên xi ở mọi dự án: cần có script thật, file lock thật và các target `clean`, `test`, `package` đúng với `build.xml`. Ví dụ `bootstrap-toolchain.sh` ở phần trước mới minh họa việc tải Ant; khi triển khai job này phải bổ sung bootstrap/verify cho JDK, `protoc` và các công cụ khác đang dùng.

`ubuntu-24.04` chọn dòng runner OS nhưng không cố định mọi binary sẵn có bên trong runner image. `actions/checkout@v4` là major tag có thể được cập nhật; với yêu cầu chuỗi cung ứng nghiêm ngặt, khóa action bằng **commit SHA đầy đủ được phê duyệt** và cập nhật theo review. Nếu dùng container CI đã dựng sẵn, ghi image digest trong cấu hình job và vẫn xác minh công cụ bên trong.

Cách tổ chức trên cũng áp dụng về nguyên lý với Jenkins, GitLab CI, TeamCity hay Azure Pipelines. Công cụ CI chịu trách nhiệm chọn agent, cấp secret, quản lý cache và luồng artifact; script của dự án chịu trách nhiệm xác minh toolchain, còn Ant điều phối compile/test/package.

### Ai chịu trách nhiệm việc gì?

| Thành phần | Nhiệm vụ |
|---|---|
| CI agent/image | Cung cấp OS, CPU, filesystem và môi trường chạy được kiểm soát |
| Manifest phiên bản | Xác định artifact ID/URL, version, digest và nền tảng hợp lệ |
| Bootstrap script | Tải đúng binary, đối chiếu checksum và cài vào vị trí xác định |
| Verify script | Kiểm tra binary và runtime được chọn, thất bại khi lệch |
| Wrapper Ant | Thiết lập đường dẫn và gọi đúng Ant/JDK |
| `build.xml` | Điều phối target và kiểm tra điều kiện build bổ sung |
| CI/CD pipeline | Chạy đúng thứ tự, thu thập log, lưu artifact và cho phép phát hành khi đạt điều kiện |

Đừng phân tán nhiều định nghĩa version trái nhau trong Dockerfile, workflow và `build.xml` mà không có quy tắc đồng bộ. Nên dùng một manifest gốc, từ đó tạo ra hoặc đối chiếu các thuộc tính còn lại.

## 10. Cache để build nhanh mà vẫn tái tạo được

Tải và giải nén JDK, Ant hay code generator trong từng job có thể làm CI chậm. Cache được phép cải thiện tốc độ nhưng phải **lưu bản sao của artifact đã khóa**, không tự trở thành nguồn quyết định version.

Một khóa cache nên thể hiện:

~~~text
OS + architecture + SHA-256(toolchain manifest)
~~~

Ví dụ ý tưởng:

~~~text
toolchain-linux-x86_64-sha256_<hash-manifest>
~~~

Khi có cache hit, không được bỏ qua điều kiện toàn vẹn. Có thể tái kiểm tra checksum hoặc sử dụng cache content-addressed chỉ đọc đã được xác thực. Khi miss cache, bootstrap từ URL bất biến rồi đối chiếu digest như bình thường.

Những lỗi thiết kế cache thường gặp:

- Dùng key `ant-latest` hoặc `jdk21` nhưng không thể hiện bản vá, vendor, binary.
- Cài toolchain vào thư mục dùng chung cho nhiều job có thể ghi đè lẫn nhau.
- Dùng `~/.ant/lib` từ các job cũ nhưng không kiểm tra tập JAR.
- Chấp nhận file có sẵn trong cache dù SHA-256 khác bản đã duyệt.
- Thay checksum trong lock file tự động mỗi khi cache/download đổi bytes.

Các dependency được Ivy hoặc resolver khác tải về cũng cần manifest/lock. Một pipeline nên có khả năng dựng lại từ cache sạch. Nếu chỉ build thành công khi cache đã được làm ấm từ trước, danh mục đầu vào đang thiếu dữ liệu cần thiết.

## 11. Môi trường agent có thể làm thay đổi output

Khóa toolchain là điều kiện nền tảng, nhưng còn các nguồn sai lệch khác:

| Yếu tố | Có thể gây ra | Cách kiểm soát |
|---|---|---|
| `JAVA_HOME` | Ant chạy sai JDK | Wrapper chọn JDK đã xác minh và gọi executable tường minh |
| `PATH` | Tool ngoài lấy nhầm binary | Dùng đường dẫn tuyệt đối hoặc PATH được quản lý |
| `ANT_HOME` | Khác bản Ant/thư viện Ant | Chọn bản phân phối đã khóa và kiểm tra SHA-256 |
| `CLASSPATH` | JAR ngoài manifest ảnh hưởng task | Giảm classpath ngầm và khai báo path riêng |
| `ANT_OPTS`, `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS` | Thêm JVM flags, agent hoặc system property không mong muốn | Khai báo rõ JVM options; loại bỏ ảnh hưởng lạ |
| `LANG`, `LC_ALL`, `TZ` | Encoding, format ngày, thứ tự sắp xếp thay đổi | Cố định locale/timezone phù hợp; đặt encoding tường minh |
| Workspace bẩn | File sinh từ lần build trước lọt vào artifact | Chạy trên workspace sạch, tách input/output và cleanup đúng phạm vi |
| OS/CPU architecture | Công cụ native và đường dẫn khác | Khóa nền tảng hoặc dùng manifest theo nền tảng |
| Trạng thái kho artifact | Tải dependency khác dù tên giống nhau | Kiểm tra resolved artifact và SHA-256 |
| Đồng hồ hệ thống, thứ tự ZIP/JAR entry | Artifact khác hash dù class tương đương | Chuẩn hóa metadata và timestamp khi yêu cầu tái lập từng byte |

Một build chức năng giống nhau **không nhất thiết** tạo ra JAR cùng SHA-256. Timestamp trong archive, manifest động, thứ tự file và generator chèn thời gian có thể tạo khác biệt. Nếu mục tiêu là build tái lập ở mức byte, cần cấu hình từng task/tool có liên quan để kiểm soát những đầu vào này; chỉ đặt biến môi trường như `SOURCE_DATE_EPOCH` sẽ không tự động làm mọi task Ant chuẩn hóa output.

Nếu build chứa bước ký artifact, thông tin chữ ký và metadata ký cũng cần chính sách riêng. Việc chuẩn bị agent được khóa không tự giải quyết mọi yếu tố không xác định của quy trình phát hành.

## 12. Ghi thông tin toolchain cùng artifact phát hành

Sau khi build/test thành công, pipeline nên lưu một bản ghi có thể tra cứu:

~~~text
source.commit: <Git commit SHA chính xác>
agent.os: <tên/version OS>
agent.arch: <kiến trúc CPU>
agent.imageDigest: <digest của image nếu có>
toolchain.manifestSha256: <SHA-256 manifest>
ant.version: <phiên bản thực tế>
ant.binarySha256: <digest binary/gói đã duyệt>
jdk.vendor: <vendor thực tế>
jdk.runtimeVersion: <phiên bản đầy đủ>
jdk.binarySha256: <digest binary/gói đã duyệt>
java.targetRelease: <release biên dịch>
externalTools: <tên, version, OS/architecture, digest>
dependencies.lockSha256: <digest lock dependency>
build.command: <target và tham số đã được phép>
build.result: <success/failure>
artifact.name: dist/app.jar
artifact.sha256: <digest thực tế của artifact>
~~~

Bản ghi có thể là JSON, YAML hoặc metadata phát hành. Nó cho biết artifact được tạo từ **bộ đầu vào nào**, giúp đối chiếu giữa hai lần chạy và điều tra nguyên nhân drift.

Lấy hash artifact sau khi đóng gói:

~~~bash
sha256sum dist/app.jar
~~~

Hoặc Windows PowerShell:

~~~powershell
(Get-FileHash -LiteralPath 'dist\app.jar' -Algorithm SHA256).Hash
~~~

Không ghi token, mật khẩu hoặc bí mật môi trường vào log. Bước deploy nên sử dụng **chính artifact đã build và test** cùng thông tin checksum, thay vì âm thầm build lại dưới một agent có thể khác phiên bản. Nếu quy trình buộc rebuild, cần áp dụng cùng chính sách toolchain và xác minh đầu ra theo yêu cầu của dự án.

## 13. Chẩn đoán lỗi agent và xử lý lệch phiên bản

| Dấu hiệu | Nguyên nhân nên kiểm tra | Hướng xử lý |
|---|---|---|
| `ant -version` khác ở CI | Runner chọn Ant cài sẵn trên `PATH` | Gọi đúng wrapper hoặc executable tuyệt đối |
| `Unsupported release version` hoặc lỗi compiler | Compiler JDK khác release mong đợi | Kiểm tra `JAVA_HOME`, `javac -version` và thuộc tính `executable` |
| `taskdef class not found` | JAR chỉ có trên máy cá nhân trong `~/.ant/lib` | Khai báo classpath task riêng và pin checksum |
| `ClassNotFoundException` chỉ xảy ra trên CI | Classpath hoặc dependency transitive khác | Đối chiếu danh sách resolved JAR và SHA-256 |
| Generator sinh code khác | `protoc` hoặc công cụ ngoài khác version/platform | Kiểm tra đường dẫn, version và binary digest |
| Cache hit nhưng digest sai | Cache key quá rộng hoặc dữ liệu bị thay | Từ chối cache, tải lại từ artifact đã khóa |
| Lỗi xuất hiện sau khi hosted runner cập nhật | Pipeline phụ thuộc tool có sẵn ngoài manifest | Bootstrap đầy đủ hoặc pin image digest |
| Chỉ build được trên một self-hosted runner | Có trạng thái ngầm, package cũ hoặc cấu hình riêng | Thử agent sạch, xác minh mọi đầu vào |
| JAR chạy tương đương nhưng hash khác | Timestamp, thứ tự entry, manifest hoặc file sinh tự động | Kiểm tra quy trình chuẩn hóa archive |
| Artifact deploy khác artifact đã test | Deploy chạy build lại hoặc lấy file cache sai | Chuyển đúng artifact và kiểm tra checksum trước publish |

Một lỗi xác minh tốt cần nêu: **công cụ nào sai, đường dẫn đang dùng, version hoặc checksum mong đợi, giá trị thực tế**. Khi mismatch, pipeline phải dừng trước compile/package hoặc ít nhất trước publish. Không nên tự thay checksum trong manifest theo binary vừa tải để “sửa” lỗi: như vậy không còn sự phê duyệt nguồn công cụ.

## 14. Quy trình nâng cấp phiên bản có kiểm soát

Khi cần nâng Ant, JDK hoặc công cụ ngoài, thực hiện thành một thay đổi có thể review:

1. **Xác định phạm vi:** thành phần, phiên bản hiện tại, phiên bản đích, lý do và rủi ro tương thích.
2. **Chọn artifact xác định:** xác minh nhà cung cấp, URL/ID nguồn, nền tảng và SHA-256 thật.
3. **Cập nhật hợp đồng:** sửa manifest, sidecar checksum, wrapper, image digest, script verify và `versions.properties` theo cùng một chính sách.
4. **Chạy thử trên agent sạch:** bootstrap bằng bộ tool mới và fail nếu mismatch trước khi build.
5. **Đánh giá kết quả:** compile, test, codegen, đóng gói, kiểm tra artifact; nếu yêu cầu tái lập byte, so hash từ hai lần build sạch.
6. **Review và phát hành:** cập nhật cache key hoặc image được sử dụng chính thức, giữ khả năng quay về toolchain cũ.
7. **Ghi provenance:** gắn version/digest mới với các artifact sinh ra từ bản cập nhật.

Một workflow riêng có thể theo dõi bản mới và tạo đề xuất nâng cấp, nhưng pipeline phát hành không nên tự tải bản `latest` trong mỗi lần chạy. Mục tiêu là mọi lần build cùng commit và cùng manifest đều chọn **đúng cùng một bộ công cụ đã duyệt**.

## 15. Tóm lại: hợp đồng chuẩn bị agent

Một agent CI/CD được chuẩn bị đúng cho Apache Ant phải đáp ứng những điều kiện nối tiếp nhau: **manifest xác định được phiên bản và checksum → bootstrap lấy đúng binary theo nền tảng → verify kiểm tra bytes và runtime thực tế → wrapper gọi đúng Ant/JDK → build chỉ bắt đầu sau khi xác minh thành công → artifact đi kèm checksum và thông tin toolchain**.

Khi áp dụng hợp đồng đó, nhóm không cần suy đoán dựa vào máy build: có thể trả lời chính xác **Ant nào đã chạy, JDK nào đã biên dịch, công cụ ngoài nào đã sinh mã, binary của chúng có đúng bản được duyệt không, và làm sao dựng lại cùng môi trường trên một agent sạch**. Đây là nền tảng cho pipeline Ant ổn định, có thể tái tạo và đáng tin cậy khi phát hành.



