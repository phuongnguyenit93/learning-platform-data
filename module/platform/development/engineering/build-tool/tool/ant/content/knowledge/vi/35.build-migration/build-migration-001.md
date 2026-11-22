# Kiểm kê target, dependency, sản phẩm và công cụ trong build Ant hiện hữu

Chuyển một dự án từ **Apache Ant** sang công cụ build mới dễ gặp một lỗi tưởng như khó hiểu: mã vẫn biên dịch, nhưng bản phân phối không giống trước; bộ kiểm thử không chạy; một bước sinh mã bị bỏ qua; hoặc bản phát hành cần một script mà không ai nhớ Ant đang gọi. Những sai khác này xuất phát từ việc chuyển cấu hình mà chưa biết đầy đủ **hành vi của bản build hiện hữu**.

Trong module **Build Tool Ant**, chủ đề **Chuyển đổi build**, bài học này hướng dẫn tạo hồ sơ kiểm kê gồm bốn nhóm: **target**, **dependency**, **sản phẩm đầu ra** và **công cụ thực thi**. Mục tiêu là xây dựng một đường cơ sở (*baseline*) đủ rõ để sau này đối chiếu kết quả của hệ thống build mới với hành vi đang được dự án và CI sử dụng.

## 1. Kiểm kê build là gì?

Một bản kiểm kê tốt trả lời được các câu hỏi:

- Ai gọi Ant: developer, CI, script phát hành hay job bảo trì? Lệnh và profile nào được dùng?
- Target nào tồn tại, target nào chạy khi gọi một entry point, thứ tự chạy và điều kiện nào làm chúng bị bỏ qua?
- Mỗi target đọc nguồn dữ liệu gì, dùng thư viện gì và phụ thuộc vào sản phẩm nào của target khác?
- Nó tạo ra file, thư mục, báo cáo hay artifact nào? Nó có xóa dữ liệu hoặc thao tác với hệ thống bên ngoài không?
- Ant/JDK và các công cụ con, Antlib, task tùy biến đến từ đâu, chạy với phiên bản nào?
- Bằng chứng cho từng kết luận nằm ở dòng XML nào, script nào, log nào hoặc artifact nào?

Cần phân biệt **kiểm kê tĩnh** với **quan sát động**:

| Phương pháp | Thu thập | Điểm mạnh | Giới hạn |
|---|---|---|---|
| Đọc tĩnh | `build.xml`, tệp import, property, script, `ivy.xml`, CI | Phát hiện cả nhánh chưa chạy | Property và target động có thể làm kết quả khác thực tế |
| Quan sát chạy | Log Ant, trạng thái thư mục, báo cáo kiểm thử, archive sau build | Cho thấy đường chạy thực tế của một cấu hình | Chỉ bao phủ các điều kiện/profile được kích hoạt |

Hai nguồn này bổ trợ cho nhau. Một target không xuất hiện trong log lần gần nhất **chưa chắc là target không dùng nữa**. Nó có thể chỉ chạy trên CI phát hành, Windows, hoặc khi một property được bật.

## 2. Khóa phạm vi kiểm kê và chụp đường cơ sở

Trước khi phân tích XML, xác định các trường hợp sử dụng đã tồn tại:

| Phạm vi | Lệnh minh họa | Kết quả cần tìm |
|---|---|---|
| Developer | `ant compile` | Class, tài nguyên biên dịch |
| Kiểm thử CI | `ant -Dprofile=ci test` | Test report, coverage |
| Bản phân phối | `ant -Drelease=true dist` | JAR/WAR/ZIP và thư viện runtime |
| Phát hành | `ant publish` | Artifact được đưa đến kho hoặc môi trường ngoài |
| Bảo trì | `ant clean` | Những thư mục/file bị xóa |

Các lệnh này chỉ là ví dụ; phải lấy lệnh **thực sự được sử dụng** từ CI, script và hướng dẫn dự án.

Ghi lại một hồ sơ nền:

~~~text
Repository / commit  :
Build file entry      :
Ant version / path    :
JDK vendor / version  :
OS / shell / runner   :
Command line          :
Property/profile      :
Workspace clean?      :
Result / log path     :
Artifact locations    :
Build date            :
~~~

Không ghi mật khẩu hoặc token vào hồ sơ. Với property như `-Drepository.password=...`, chỉ ghi rằng build cần credential và nguồn cấp an toàn của nó.

Nên lập baseline riêng cho cấu hình quan trọng. Ví dụ, `ant dist` trên máy developer và `ant -Drelease=true dist` trên CI có thể tạo ra **hai bộ artifact khác nhau**. Nếu mục tiêu là chuyển toàn bộ quy trình, cả hai đường chạy đều thuộc phạm vi kiểm kê.

## 3. Phát hiện toàn bộ file Ant liên quan

Một dự án có thể có:

~~~text
project/
├── build.xml
├── build-ci.xml
├── build.properties
├── ant/
│   ├── common.xml
│   ├── release.xml
│   └── custom-tasks.xml
├── ivy.xml
├── ivysettings.xml
├── lib/
├── scripts/
├── src/
└── test/
~~~

Đừng mặc định mọi cấu hình đều nằm trong `build.xml`. Cần tìm các tệp được Ant nạp qua `<import>`, `<include>`, được gọi qua `<ant>`/`<subant>`, và các script CI dùng tham số `-f` để chọn file build khác.

Với ripgrep, có thể tìm các ứng viên theo tên:

~~~bash
rg --files \
  -g 'build*.xml' \
  -g '*ant*.xml' \
  -g 'ivy*.xml' \
  -g '*.properties' \
  -g '*.jar' \
  -g '*.sh' \
  -g '*.cmd' \
  -g '*.bat'
~~~

Trên PowerShell, cú pháp đơn giản:

~~~powershell
rg --files -g 'build*.xml' -g '*ant*.xml' -g 'ivy*.xml' -g '*.properties' -g '*.jar'
~~~

Tìm những khai báo có ý nghĩa:

~~~bash
rg -n '<(target|import|include|antcall|subant|ant|taskdef|typedef|macrodef|presetdef|scriptdef|property|path|fileset|javac|junit|jar|war|zip|tar|copy|exec|java)\b' -g '*.xml'
~~~

Các lệnh `rg` dùng để **định vị**. Tránh phân tích quan hệ bằng tìm chuỗi đơn thuần: XML có thể chứa comment, macro, namespace và property khiến tên target hoặc đường dẫn chỉ được xác định lúc chạy.

Một điểm đặc biệt quan trọng: `<import>` và `<include>` có cơ chế đặt tên, namespace và override khác nhau. Nếu có target trùng tên, cần đọc quy tắc của Ant và cấu hình thực tế để xác định định nghĩa nào được dùng. Tạo bảng liên kết:

| File | Được gọi/nạp từ | Vai trò | Target hoặc task đáng chú ý |
|---|---|---|---|
| `build.xml` | Entry chính | Điều phối | `compile`, `test`, `dist` |
| `ant/common.xml` | `import` | Cấu hình chung | `init`, `clean` |
| `ant/release.xml` | `import` | Phát hành | `package`, `publish` |
| `modules/api/build.xml` | `ant` | Project con | `compile`, `jar` |

Đây là các hàng minh họa, không phải tên file bắt buộc trong mọi dự án.

## 4. Kiểm kê target: điểm vào, điều kiện và quan hệ thực thi

### 4.1. Các trường phải có

| Trường | Cần ghi |
|---|---|
| Tên target | Giá trị `name` chính xác |
| File/vị trí | File XML và dòng khai báo |
| Mục đích | `description` hoặc công việc thực hiện |
| Entry point | Ant mặc định, lệnh CLI, script CI, target khác gọi |
| Depends | Danh sách `depends` theo thứ tự khai báo |
| Lệnh gọi bổ sung | `antcall`, `ant`, `subant`, macro điều phối |
| Điều kiện | `if`, `unless`, `condition`, `available`, profile |
| Task sử dụng | `javac`, `junit`, `jar`, `exec`, task tùy biến |
| Đầu vào | Source, classpath, config, generated files |
| Đầu ra/tác dụng phụ | File, báo cáo, gói, xóa file, upload |
| Bằng chứng | Dòng XML, log, file thực tế |
| Mức chắc chắn | Khai báo; quan sát được; chưa rõ |

Ant có lệnh hỗ trợ khám phá:

~~~bash
ant -version
ant -f build.xml -projecthelp
ant -f build.xml -projecthelp -verbose
~~~

`-projecthelp` (viết tắt `-p`) liệt kê thông tin trợ giúp và các target; chế độ `-verbose` có thể hiển thị thêm các target không có `description`. Kết quả này không thay thế việc đọc các file import hoặc project con, và không phải một lệnh chuẩn để xuất toàn bộ đồ thị thực thi.

### 4.2. Ví dụ phân tích một file `build.xml`

Giả sử dự án đã có source Java, thư viện trong `lib/` và class `com.example.Main`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="legacy-app" default="dist" basedir=".">

    <property file="build.properties"/>
    <property name="src.dir" location="src"/>
    <property name="classes.dir" location="build/classes"/>
    <property name="dist.dir" location="dist"/>

    <path id="compile.path">
        <fileset dir="lib" includes="*.jar"/>
    </path>

    <target name="prepare" description="Tao thu muc">
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${dist.dir}"/>
    </target>

    <target name="compile" depends="prepare">
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               includeantruntime="false">
            <classpath refid="compile.path"/>
        </javac>
    </target>

    <target name="package" depends="compile">
        <jar destfile="${dist.dir}/app.jar"
             basedir="${classes.dir}">
            <manifest>
                <attribute name="Main-Class"
                           value="com.example.Main"/>
            </manifest>
        </jar>
    </target>

    <target name="dist" depends="package"
            description="Tao ban phan phoi">
        <copy todir="${dist.dir}/lib">
            <fileset dir="lib" includes="*.jar"/>
        </copy>
    </target>

    <target name="clean">
        <delete dir="build"/>
        <delete dir="dist"/>
    </target>
</project>
~~~

Đây là **bản build minh họa** để kiểm kê, không phải project hoàn chỉnh khi chưa có source, thư viện và cấu hình cần thiết.

Đồ thị phụ thuộc của target mặc định `dist`:

~~~text
dist
  |
  v
package
  |
  v
compile
  |
  v
prepare

clean       (khong thuoc duong chay dist)
~~~

Dấu mũi tên đi đến **target phải thực hiện trước**. Thứ tự chạy thực tế là `prepare → compile → package → dist`. Target `clean` vẫn phải được kiểm kê vì nó ảnh hưởng cách chạy lại từ workspace sạch.

| Target | Depends | Thao tác | Đầu ra/tác dụng phụ |
|---|---|---|---|
| `prepare` | Không | Tạo thư mục | `build/classes/`, `dist/` |
| `compile` | `prepare` | Biên dịch với JAR từ `lib/` | `build/classes/**/*.class` |
| `package` | `compile` | Tạo JAR và manifest | `dist/app.jar` |
| `dist` | `package` | Sao chép dependency runtime | `dist/lib/*.jar` |
| `clean` | Không | Xóa sản phẩm | Xóa `build/` và `dist/` |

### 4.3. `depends` không bao quát mọi lời gọi

Hai ví dụ cần lập **cạnh gọi riêng**:

~~~xml
<target name="build-module">
    <ant antfile="modules/api/build.xml"
         target="package"/>
</target>

<target name="call-compile">
    <antcall target="compile"/>
</target>
~~~

`<ant>` có thể chạy target ở project khác. `<subant>` có thể gọi một tập build con. `<antcall>` gọi target theo cơ chế project mới của Ant và có thể làm cùng một công việc chạy lại, khác với việc thêm một tên vào `depends` trong cùng luồng build. Ghi rõ target gọi, file được gọi, property và reference được truyền, cùng tần suất gọi quan sát được.

Không nên suy ra rằng một target nằm ngoài `depends` là không dùng: nó có thể chỉ được kích hoạt từ script shell hoặc CI job riêng.

### 4.4. Điều kiện có thể che khuất dependency

~~~xml
<target name="integration-test"
        depends="compile"
        if="integration.enabled">
    <echo message="Run integration tests"/>
</target>
~~~

Nếu `integration.enabled` chưa được đặt, phần thân target bị bỏ qua, nhưng **Ant vẫn xử lý các target trong `depends` trước khi xét điều kiện** của `integration-test`. Cần ghi cả hành vi này để tránh migration tạo ra thứ tự thực thi khác.

Property cũng có thể đến từ CLI:

~~~bash
ant -Dprofile=dev compile
ant -Dprofile=release -Dintegration.enabled=true dist
~~~

Ant property thông thường có tính bất biến theo cơ chế “giá trị được đặt trước giữ nguyên”; giá trị `-D` có thể thay đổi kết quả so với mặc định trong file. Kiểm kê cần ghi nguồn giá trị (CLI, property file, environment, mặc định) và giá trị đã resolve cho **mỗi baseline**.

## 5. Kiểm kê dependency theo ba lớp

Trong Ant, “dependency” có thể chỉ:

1. **Target dependency:** cạnh `depends` hoặc quan hệ target sinh artifact rồi target khác tiêu thụ.
2. **Input dependency:** source, config, template, file schema, JAR local hoặc công cụ cần để chạy task.
3. **External dependency:** thư viện được tải qua Apache Ivy, repository, script download; bao gồm dependency bắc cầu.

| Nhóm | Ví dụ | Dữ liệu cần ghi |
|---|---|---|
| Source | `src/**/*.java`, `test/**/*.java` | Đường dẫn, include/exclude, bước sinh source |
| JAR local | `lib/*.jar` | Tên file thật, version, nguồn, hash, scope |
| Ivy/managed | `ivy.xml`, `ivysettings.xml` | Org/module/revision, resolver, dependency bắc cầu |
| Input đã sinh | `build/generated/**/*.java` | Target tạo, target dùng, điều kiện cập nhật |
| Cấu hình | `build.properties`, `filters.properties` | Profile, override, loại dữ liệu |
| Toolchain | JDK, Ant, `PATH` | Version, đường dẫn, cách cài |
| Dịch vụ ngoài | DB test, Maven proxy, API | Địa chỉ, credential, điều kiện truy cập |
| Project con | `modules/*/build.xml` | File build, target, artifact trao đổi |

### 5.1. Lấy classpath thực tế, không chỉ pattern

~~~xml
<path id="compile.classpath">
    <fileset dir="lib" includes="*.jar"/>
    <pathelement location="build/generated/classes"/>
</path>

<javac srcdir="src"
       destdir="build/classes"
       classpathref="compile.classpath"/>
~~~

Pattern `*.jar` phụ thuộc nội dung thư mục `lib` trên máy chạy. Để migration có thể tái lập, phải liệt kê **các JAR được resolve thực tế** trong baseline: file nào, version nào, xuất xứ và phạm vi sử dụng. Ghi cả đường dẫn `build/generated/classes` vì nó có thể là output của một target khác mà compile cần chờ.

Các pattern `includes`, `excludes`, `fileset`, `dirset` và các phần tử `refid` là một phần của hợp đồng đầu vào. Nếu chuyển thành “đọc cả thư mục”, có nguy cơ thêm file dev-only vào artifact hoặc bỏ sót tài nguyên cần thiết.

### 5.2. Dependency bắc cầu và kho tải

Một project dùng Apache Ivy có thể định nghĩa:

~~~xml
<ivy-module version="2.0">
    <info organisation="com.example"
          module="legacy-app"/>
    <dependencies>
        <dependency org="org.apache.commons"
                    name="commons-lang3"
                    rev="3.14.0"/>
    </dependencies>
</ivy-module>
~~~

Cấu hình này mô tả một dependency trực tiếp; resolver có thể lấy thêm dependency bắc cầu từ metadata của thư viện. Hồ sơ phải ghi **danh sách artifact thực sự được chọn**, version, repository và cache, không chỉ trích `ivy.xml`. Nếu có revision động hoặc lấy từ nhiều repository, ghi rõ trường hợp cần ổn định lại khi chuyển đổi.

Một số dự án không dùng Ivy mà chạy:

~~~xml
<get src="https://example.org/artifacts/tool.jar"
     dest="lib/tool.jar"/>

<exec executable="curl">
    <arg value="-o"/>
    <arg value="lib/another.jar"/>
    <arg value="https://example.org/artifacts/another.jar"/>
</exec>
~~~

Các URL trên chỉ minh họa; trong project thật, cần ghi nguồn đã được duyệt, phiên bản, checksum và cơ chế cập nhật. Dependency tải trực tiếp cũng phải có trong inventory, dù không được khai báo là “dependency” bằng một DSL chuyên dụng.

### 5.3. Producer và consumer

Với một file `build/generated/Version.java`, bảng cần chỉ rõ:

| Artifact | Sinh từ target | Được target nào dùng | Điều kiện |
|---|---|---|---|
| `build/generated/Version.java` | `generate-version` | `compile` | Version/property |
| `build/classes/` | `compile` | `test`, `package` | JDK/classpath |
| `build/reports/tests/` | `test` | CI report publisher | Test runner |
| `dist/app.jar` | `package` | `dist`, `publish` | Release profile |

Nếu chỉ sao chép lệnh `javac` sang hệ thống mới mà quên tạo `Version.java`, bản build có thể lỗi ngẫu nhiên khi chạy từ checkout sạch hoặc khi build song song.

## 6. Kiểm kê mọi sản phẩm đầu ra

Đầu ra có thể là file trung gian, artifact phát hành, báo cáo hoặc thay đổi bên ngoài workspace.

| Task/nhóm task | Sản phẩm hoặc tác dụng phụ cần khảo sát |
|---|---|
| `javac` | Class, generated metadata |
| `jar`, `war`, `zip`, `tar` | Archive, manifest, file và metadata bên trong |
| `copy`, `move` | File được sao chép/chuyển, filter được áp dụng |
| `junit`, `junitlauncher` | Báo cáo XML, text, HTML, log |
| `javadoc` | Tài liệu API |
| `replaceregexp`, `fixcrlf`, `filterset` | Nội dung file sau biến đổi |
| `tstamp`, `propertyfile`, `touch` | Version hoặc timestamp |
| `delete` | Xóa file/thư mục |
| `exec`, `java`, custom task | Output do chương trình con tạo, network hoặc side effect |

### 6.1. Phiếu sản phẩm

| Trường | Ví dụ |
|---|---|
| Artifact | `dist/app.jar` |
| Producer | Target `package` |
| Input | `build/classes/`, manifest, resource |
| Consumer | `dist` hoặc pipeline release |
| Hợp đồng | Tên, cấu trúc, `Main-Class`, thư viện/runtime |
| Profile | Dev, release, OS |
| Dọn dẹp | Target `clean` có xóa không |
| Bằng chứng | XML khai báo, archive trong baseline |

Không chỉ ghi “JAR tồn tại”. Hãy mở cấu trúc archive và xác định những file, resource, manifest hoặc quyền thực thi mà hệ thống khác đang phụ thuộc:

~~~bash
jar tf dist/app.jar
sha256sum dist/app.jar
~~~

Trên PowerShell:

~~~powershell
jar tf .\dist\app.jar
Get-FileHash .\dist\app.jar -Algorithm SHA256
~~~

Hash giúp xác định byte của artifact, nhưng archive có thể thay đổi timestamp hoặc thứ tự entry giữa các lần build. Khi so sánh migration, cần xác định tiêu chí thực sự: toàn bộ byte phải giống, hay nội dung file và metadata quan trọng phải tương đương.

### 6.2. Các output có thể thay đổi khi chuyển công cụ

| Output | Nhóm | Cách xử lý khi migration |
|---|---|---|
| `build/classes/` | Trung gian | Đường dẫn có thể đổi nếu producer/consumer được nối đúng |
| `build/generated-sources/` | Sinh mã | Phải giữ quan hệ generate trước compile |
| `build/reports/tests/` | Báo cáo | Giữ định dạng và nơi CI đọc, hoặc cập nhật CI đồng bộ |
| `dist/app.jar` | Artifact phát hành | Giữ hợp đồng tên/nội dung nếu consumer yêu cầu |
| `dist/lib/` | Runtime dependency | Giữ đủ thư viện/version cần để chạy |
| `logs/` | Nhật ký | Xác định retention và nơi lưu |
| `cache/` | Cache | Có thể thay đổi nhưng cần hiểu nguồn và cách xóa |

Nếu một target tạo file cấu hình bằng cách thay token, phải ghi cả **nội dung sinh ra**, property ảnh hưởng và encoding/line ending nếu có script đa nền tảng.

### 6.3. Tác dụng phụ ngoài file

Ví dụ:

~~~xml
<target name="publish" depends="dist">
    <exec executable="sh" failonerror="true">
        <arg value="scripts/upload-release.sh"/>
    </exec>
</target>
~~~

Dòng XML chỉ nói Ant gọi script; để kiểm kê đầy đủ cần đọc `scripts/upload-release.sh` xem script upload đến đâu, có ghi đè bản phát hành không, lấy credential từ đâu và có gọi công cụ khác không.

Không nên chạy một target `publish`, `deploy`, `db-reset` hoặc `clean-remote` chỉ để “quan sát” khi chưa hiểu tác dụng phụ. Có thể thu thập log CI và đọc script trước; nếu cần chạy, thực hiện trên môi trường được chuẩn bị cho mục đích đó.

## 7. Kiểm kê công cụ, task mở rộng và môi trường

Ant không hoạt động độc lập với máy build. Cùng một XML nhưng JDK khác, JAR task khác hoặc shell khác có thể cho kết quả không giống nhau.

| Nhóm | Ví dụ | Dấu vết |
|---|---|---|
| Ant | Phiên bản, launcher, `ANT_HOME` | `ant -version`, CI, `-f`, `-lib` |
| JDK | Vendor, version, compiler | `java -version`, `javac -version`, `fork`, `executable` |
| Kiểm thử | JUnit, test runner, coverage | `junit`, `junitlauncher`, `taskdef` |
| Dependency manager | Ivy, Maven CLI | `ivy.xml`, `ivy:resolve`, `exec` |
| Task tùy chỉnh | Antlib/JAR, macro, scriptdef | `taskdef`, `typedef`, `macrodef` |
| Công cụ ngoài | Git, shell, Node, protoc, Docker | `exec`, script bao quanh |
| Phát hành | jarsigner, zip, GPG, upload CLI | Target package/publish |
| Hệ thống CI | Agent, image, biến môi trường | Job definition, runner config |

Các lệnh hữu ích trên Linux/macOS:

~~~bash
ant -version
java -version
javac -version
command -v ant
command -v java
printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
printf 'ANT_HOME=%s\n' "$ANT_HOME"
~~~

Trên PowerShell:

~~~powershell
ant -version
java -version
javac -version
Get-Command ant,java,javac | Select-Object Name,Source
$env:JAVA_HOME
$env:ANT_HOME
~~~

Lệnh `ant -diagnostics` có thể giúp quan sát classpath và cấu hình cài đặt. Đầu ra chẩn đoán đôi khi chứa đường dẫn hoặc dữ liệu nội bộ, nên chỉ lưu/chia sẻ trong phạm vi phù hợp.

### 7.1. Nhận diện custom task

~~~xml
<taskdef name="generateApi"
         classname="com.example.ant.ApiGeneratorTask">
    <classpath>
        <pathelement location="tools/api-generator-task.jar"/>
    </classpath>
</taskdef>

<target name="generate">
    <generateApi input="schemas/api.yaml"
                 output="build/generated"/>
</target>
~~~

Nếu chỉ đọc tên `generateApi` mà bỏ qua JAR task, bạn chưa biết code nào tạo output. Phải ghi JAR, class, nguồn cung cấp, version, classpath, input/output và hành vi trong task.

`macrodef`, `presetdef` và `scriptdef` cũng có thể che phần logic thật bên dưới một tên task ngắn. Đối với macro cần đọc nội dung `<sequential>`. Đối với custom task phải tra class/JAR hoặc tài liệu đi kèm thay vì đoán hành vi chỉ từ tên.

### 7.2. Thư viện và công cụ nạp ngầm

Một số vị trí cần thống kê:

~~~text
ANT_HOME/lib/
~/.ant/lib/
ant -lib ...
CLASSPATH
ANT_OPTS
project/lib/
Ivy cache
CI tool cache
~~~

Thư viện có thể được nạp từ môi trường dù không khai báo trong `build.xml`. Khi di chuyển sang môi trường mới, điều kiện “trên máy cũ đã có sẵn” thường là nguyên nhân gây thiếu task hoặc class. Ghi rõ dependency theo môi trường và cách cài đặt.

## 8. Mẫu hồ sơ kiểm kê sẵn dùng

Có thể lưu thành một tài liệu Markdown hoặc spreadsheet với năm bảng liên kết bằng ID.

### Bảng A — Entry point

| ID | Nguồn | Lệnh/job | Property/profile | Vai trò |
|---|---|---|---|---|
| E01 | Developer | `ant compile` | Mặc định | Compile |
| E02 | CI | `ant -Dprofile=ci test` | CI | Test |
| E03 | Release CI | `ant -Drelease=true dist` | Release | Artifact |
| E04 | Script phát hành | `ant publish` | Credential từ runner | Upload |

### Bảng B — Target

| ID | Target | File | Phụ thuộc/gọi | Điều kiện | Task và output |
|---|---|---|---|---|---|
| T01 | `prepare` | `build.xml` | Không | Không | `mkdir` |
| T02 | `compile` | `build.xml` | `prepare` | Không | `javac`, class |
| T03 | `package` | `build.xml` | `compile` | Không | JAR |
| T04 | `dist` | `build.xml` | `package` | Không | Copy libs |
| T05 | `clean` | `build.xml` | Không | Không | Xóa output |

### Bảng C — Dependency

| ID | Loại | Tên/đường dẫn | Producer/nguồn | Consumer | Chưa rõ |
|---|---|---|---|---|---|
| D01 | Source | `src/**/*.java` | Repository | Compile | Exclude? |
| D02 | JAR | `lib/*.jar` | Vendor/repository | Compile | Version/hash |
| D03 | Intermediate | `build/classes/` | Compile | Package | Profile |
| D04 | Config | `build.properties` | Repository/CI | Nhiều task | Override |
| D05 | Tool | JDK | Runner | Compile | Fork? |

### Bảng D — Sản phẩm

| ID | Artifact | Tạo bởi | Được dùng bởi | Điều kiện/hợp đồng |
|---|---|---|---|---|
| O01 | `build/classes/` | Compile | Test/package | Class đúng |
| O02 | `dist/app.jar` | Package | Runtime/CI | Manifest, resource |
| O03 | `dist/lib/` | Dist | Runtime | JAR đủ và đúng version |
| O04 | `build/reports/tests/` | Test | CI | XML/report path |

### Bảng E — Công cụ

| ID | Công cụ | Target dùng | Version/nguồn | Môi trường |
|---|---|---|---|---|
| K01 | Ant | Toàn project | Bản cài CI | `ANT_HOME` |
| K02 | JDK | Compile/test | Vendor/version | `JAVA_HOME` |
| K03 | Custom task | Generate | `tools/*.jar` | Ant classpath |
| K04 | CLI upload | Publish | Vendor/version | `PATH`, credential |

Bổ sung cột **Bằng chứng** cho cả năm bảng (ví dụ `ant/release.xml:42`, log CI job số N, đường dẫn artifact); thêm cột **Trạng thái** với các giá trị như `Đã quan sát`, `Chỉ thấy khai báo`, `Chưa xác minh`. Điều này phân biệt tri thức đã kiểm tra với những điểm còn cần khảo sát.

## 9. Tạo danh sách target thô bằng một script chỉ đọc

Với project tương đối đơn giản, có thể dùng Python để lập **bảng nháp** từ một file XML:

~~~python
# inventory_ant.py
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

if len(sys.argv) != 2:
    raise SystemExit("Usage: python inventory_ant.py build.xml")

file = Path(sys.argv[1])
project = ET.parse(file).getroot()

print("Project:", project.get("name", "(unknown)"))
print("Default:", project.get("default", "(none)"))
print("TARGET | DEPENDS | IF | UNLESS | DIRECT TASKS")

for target in project.findall("target"):
    tasks = ",".join(
        child.tag for child in target
        if isinstance(child.tag, str)
    )
    print(
        f'{target.get("name", "")} | '
        f'{target.get("depends", "")} | '
        f'{target.get("if", "")} | '
        f'{target.get("unless", "")} | {tasks}'
    )
~~~

Chạy trên file build được tin cậy:

~~~bash
python inventory_ant.py build.xml
~~~

Script này chỉ đọc **một file XML**, không giải quyết import, property, target override, macro, project con hoặc classpath. Do đó đầu ra chỉ là điểm bắt đầu để điền bảng target. Không sử dụng nó như bằng chứng duy nhất rằng đã kiểm kê toàn bộ build.

## 10. Quan sát hành vi bằng log và artifact

Sau khi xác định một target có thể chạy an toàn trong môi trường kiểm kê, ghi lại lần chạy:

~~~bash
ant -f build.xml -verbose dist > inventory-dist.log 2>&1
~~~

Trên PowerShell:

~~~powershell
ant -f build.xml -verbose dist *> inventory-dist.log
~~~

Đối chiếu log với bảng tĩnh:

| Dấu hiệu | Điều cần rút ra |
|---|---|
| Tên target trong log | Thứ tự thực hiện của đường chạy |
| `[javac]` | Nguồn biên dịch, classpath, compiler, nơi đặt class |
| `[junit]` hoặc test report | Suite đã chạy, số test, report path |
| `[jar]`/`[zip]` | Artifact được tạo, file đưa vào archive |
| `[copy]`/`[delete]` | Những file được thêm/xóa |
| `[exec]`/`[java]` | Chương trình ngoài, exit code, log riêng |
| Custom task | Hành vi cần truy ngược sang JAR hoặc macro |

Một số tool chuyển stdout/stderr sang tệp riêng, vì vậy Ant log có thể không chứa toàn bộ sự kiện. Xem cả log mà task tạo và artifact sau build.

Đối với đường build phát hành, nên ghi nhận trạng thái **sạch** và **tăng dần** nếu incremental build là yêu cầu:

~~~bash
ant clean dist
ant dist
~~~

Trước khi chạy `clean` phải đọc phạm vi mà target xóa; một dự án cũ có thể định nghĩa đường dẫn xóa vượt ngoài `build/`. Cần dùng workspace dự định cho khảo sát. Hai lệnh trên được minh họa như trường hợp thông thường, không bắt buộc cho mọi dự án.

Một lần chạy không thể bao phủ mọi profile. Nếu có `if="release.enabled"`, hãy đánh dấu nhánh đó chưa xác minh khi mới chạy profile phát triển. Đừng lấy sự tồn tại của artifact cũ làm bằng chứng một target vừa chạy thành công.

## 11. Các trường hợp dễ bị bỏ sót

### 11.1. Macro gọi project con

~~~xml
<macrodef name="compile-module">
    <attribute name="module"/>
    <sequential>
        <ant antfile="modules/@{module}/build.xml"
             target="compile"/>
    </sequential>
</macrodef>

<target name="compile-all">
    <compile-module module="api"/>
    <compile-module module="worker"/>
</target>
~~~

Nếu chỉ xem `depends` của `compile-all`, ta sẽ không thấy hai project con. Cần mở định nghĩa macro và kiểm kê các file `modules/api/build.xml`, `modules/worker/build.xml`.

### 11.2. Điều kiện hệ điều hành

~~~xml
<exec executable="sh" osfamily="unix">
    <arg value="scripts/build-native.sh"/>
</exec>
~~~

Một build trên Linux không xác nhận được nhánh Windows. Nếu dự án có `.cmd`/`.bat` hoặc target riêng theo nền tảng, đưa cả hai vào inventory và ghi môi trường cần thiết.

### 11.3. Output tính từ property

~~~xml
<property name="release.version" value="1.0.0"/>
<property name="release.dir" location="dist/${release.version}"/>
~~~

Ghi cả biểu thức đường dẫn **và giá trị được resolve** ở baseline. Nếu CI truyền `-Drelease.version=2.0.0`, output khác với mặc định. Dự án mới phải giữ đúng quy tắc version, hoặc cập nhật mọi consumer khi đổi.

### 11.4. Artifact tồn tại từ lần chạy trước

Nếu `package` không chạy nhưng `dist/app.jar` vẫn còn, việc liệt kê file sau build có thể dẫn đến kết luận sai. Cần kết hợp log, timestamp, workspace sạch và quan hệ target để xác định output nào thực sự được tạo trong lần khảo sát.

### 11.5. Build thành công phụ thuộc state của máy

Một máy có `~/.ant/lib` hoặc cache Ivy đã được chuẩn bị trước; máy khác thiếu JAR và lỗi ngay. Hãy coi phiên bản JAR trong cache và vị trí thư viện Ant là input thực sự cho đến khi dự án có bước cài đặt rõ ràng. Cũng cần ghi các dịch vụ ngoài như database test hoặc artifact repository.

### 11.6. Publish/deploy không giống package

Target `package` có thể chỉ tạo file, còn `publish` upload hoặc ghi đè bản phát hành. Khi chuyển công cụ, không nên vô tình gộp thao tác phát hành vào build mặc định. Inventory phải ghi điểm đến, điều kiện kích hoạt và quyền cần thiết của mỗi tác dụng phụ.

## 12. Từ inventory sang bản đồ đối chiếu migration

Khi đã biết hành vi, tạo bảng mô tả **hợp đồng cần bảo toàn**:

| Hành vi Ant | Hợp đồng hiện có | Cần xác nhận ở công cụ mới |
|---|---|---|
| `compile` đọc source đặc biệt | Class sinh từ đúng tập source và classpath | Source set, compiler options |
| `generate` trước `compile` | Generated source sẵn sàng trước compiler | Quan hệ task và output tracking |
| `test` tạo XML report | CI đọc kết quả test đúng định dạng | Framework, filter, report path |
| `package` tạo JAR | Đúng manifest, class, resource | Task archive và cấu hình |
| `dist` copy runtime libs | Tập thư viện phù hợp để chạy | Runtime dependency/distribution |
| `publish` gọi script | Đúng artifact, đích và điều kiện | Tách bước phát hành |
| `clean` dọn output | Không còn file cũ ảnh hưởng build | Cách quản lý output/cache |

Phân loại từng hành vi: **bắt buộc tương đương**, **có thể thay đổi có kiểm soát**, hoặc **chưa đủ thông tin**. Không nhất thiết target Ant nào cũng cần một task trùng tên trong hệ thống mới; quan trọng là người dùng và CI nhận được đúng kết quả và điều kiện thất bại được bảo toàn.

Một bảng đối chiếu có giá trị hơn danh sách “có 20 target, 50 JAR” vì nó cho thấy target nào là entry point, dependency nào bị ẩn và output nào là hợp đồng thực tế.

## 13. Quy trình kiểm kê từng bước

1. **Thu thập entry point.** Tìm lệnh Ant trong CI, script và tài liệu dự án. Ghi commit, hệ điều hành, property/profile.
2. **Vẽ sơ đồ file build.** Tìm `build.xml`, các import/include, project con và file cấu hình.
3. **Lập bảng target.** Từ `name`/`depends`/`if`/`unless`, bổ sung `antcall`/`ant`/`subant` và macro.
4. **Lập bảng dependency.** Đọc classpath, fileset, Ivy, JAR local, generated source, property và nguồn bên ngoài.
5. **Lập bảng sản phẩm.** Đánh dấu producer/consumer, archive, report, output tạm, các bước xóa và tác dụng phụ.
6. **Lập bảng toolchain.** Ghi Ant/JDK, Antlib, custom task, CLI, shell và môi trường CI.
7. **Đối chiếu baseline.** Quan sát log và artifact ở các cấu hình quan trọng; đánh dấu nhánh chưa chạy được.
8. **Ghi lỗ hổng thông tin.** Với mục chưa biết, nêu bằng chứng đang thiếu và nơi có thể tìm, không tự điền theo suy đoán.
9. **Chuẩn bị migration.** Dùng bảng hợp đồng để xác nhận hành vi tương đương sau chuyển đổi.

Thứ tự này ưu tiên hiểu đúng bản build trước khi chỉnh sửa cấu hình. Với hệ thống lớn, có thể bắt đầu từ đường build phát hành quan trọng nhất rồi mở rộng sang nhánh ít dùng, miễn phạm vi còn thiếu được ghi rõ.

## 14. Bài tập thực hành

Cho một repository Ant chưa từng khảo sát, hãy tạo tài liệu `build-inventory.md` với các phần:

- **Entry points:** lệnh mặc định và ít nhất một lệnh CI/release.
- **Targets:** bảng tên, điều kiện, phụ thuộc và đồ thị từ entry point phát hành.
- **Dependencies:** source, JAR, Ivy, file cấu hình, đầu vào do target khác sinh.
- **Outputs:** class, report, JAR/WAR/ZIP, manifest, lib runtime và tác dụng phụ.
- **Tools:** Ant/JDK, custom tasks và công cụ ngoài.
- **Evidence:** XML file:dòng, log, artifact thực tế và các điểm còn chưa xác minh.

Một phát hiện có chất lượng có thể được ghi như sau:

> Target `package` phụ thuộc `compile` và tạo `dist/app.jar` từ `build/classes`. Target `dist` sao chép JAR runtime từ `lib/`. Trên CI, entry `ant -Drelease=true dist` thực hiện thêm một nhánh phát hành. Hai JAR local hiện chưa rõ nguồn gốc và version; cần xác minh trước khi thay bằng dependency được quản lý.

Ghi chép này cho biết **quan hệ, bằng chứng và việc còn thiếu**, hỗ trợ trực tiếp cho migration.

## 15. Tổng kết

Kiểm kê một build Apache Ant là xây dựng **bản đồ hành vi có căn cứ**. Hãy bắt đầu từ các entry point và profile; phân tích target cùng đồ thị gọi/phụ thuộc; truy dấu dependency, producer và consumer; liệt kê output và tác dụng phụ; cuối cùng xác định toolchain, JAR tùy biến và môi trường. Kết hợp khai báo tĩnh với log và artifact thực tế giúp phát hiện nhánh có điều kiện và dependency ẩn.

Bản kiểm kê là đường cơ sở để hệ thống build mới có thể được đối chiếu một cách cụ thể: điều gì phải chạy, theo điều kiện nào, tiêu thụ gì, tạo gì và ai đang sử dụng kết quả đó.

### Tài liệu tham khảo

- [Apache Ant Manual — Using Ant](https://ant.apache.org/manual/using.html)
- [Apache Ant Manual — Running Ant](https://ant.apache.org/manual/running.html)
- [Apache Ant Manual — Import task](https://ant.apache.org/manual/Tasks/import.html)
- [Apache Ant Manual — Include task](https://ant.apache.org/manual/Tasks/include.html)
- [Apache Ant Manual — Ant task](https://ant.apache.org/manual/Tasks/ant.html)
- [Apache Ant Manual — AntCall task](https://ant.apache.org/manual/Tasks/antcall.html)
- [Apache Ant Manual — SubAnt task](https://ant.apache.org/manual/Tasks/subant.html)
- [Apache Ant Manual — Property task](https://ant.apache.org/manual/Tasks/property.html)
- [Apache Ant Manual — FileSet](https://ant.apache.org/manual/Types/fileset.html)
- [Apache Ivy — Documentation](https://ant.apache.org/ivy/)
