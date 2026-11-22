# Chọn clean build để phát hiện lớp cũ và tài nguyên còn sót

Apache Ant hỗ trợ build tăng dần để rút ngắn thời gian biên dịch: task `<javac>` có thể chỉ biên dịch những tệp nguồn cần cập nhật, còn các task sao chép tài nguyên thường chỉ xử lý những tệp phù hợp với cấu hình hiện tại. Cách làm này nhanh khi phát triển hằng ngày, nhưng có một rủi ro: đầu ra cũ có thể vẫn nằm trong thư mục build dù tệp nguồn tương ứng đã bị xóa, đổi tên hoặc không còn được chọn.

Một **clean build** bắt đầu bằng việc xóa các đầu ra được sinh từ lần build trước rồi tạo lại chúng từ nguồn hiện tại. Nhờ đó, build có thể phát hiện những lớp `.class`, tài nguyên, mã nguồn sinh tự động hoặc tệp đóng gói còn sót. Đây là bước quan trọng trước khi phát hành, khi thay đổi cấu trúc source set hoặc khi kết quả build tăng dần có dấu hiệu khác với một lần build sạch.

## 1. Build tăng dần và clean build

Build tăng dần tái sử dụng đầu ra đã có. Ví dụ, nếu chỉ sửa `Main.java`, Ant có thể biên dịch lại tệp đó thay vì biên dịch lại toàn bộ dự án. Clean build xóa đầu ra cũ trước, sau đó chạy lại các bước cần thiết.

| Đặc điểm | Build tăng dần | Clean build |
|---|---|---|
| Đầu ra cũ | Được giữ lại và tái sử dụng khi phù hợp | Được xóa trước khi tạo đầu ra mới |
| Thời gian chạy | Thường nhanh hơn | Thường lâu hơn vì phải tạo lại đầu ra |
| Lớp từ source đã xóa | Có thể còn trong thư mục classes | Không còn nếu thư mục classes được xóa và build lại đúng cách |
| Tài nguyên đã bị loại khỏi nguồn | Có thể còn trong thư mục tài nguyên đích | Được loại bỏ khi thư mục đầu ra được tạo lại |
| Phù hợp | Vòng lặp phát triển thường ngày | Kiểm tra tính nhất quán, CI, phát hành và điều tra đầu ra cũ |

Ant không tự động chạy một target tên `clean` trước mọi lần build. `clean` là target do buildfile định nghĩa. Nếu người dùng chạy `ant compile`, Ant chỉ thực hiện target `compile` và các dependency của nó; việc có xóa đầu ra hay không phụ thuộc vào cấu hình buildfile.

## 2. Vì sao lớp cũ có thể còn sau build tăng dần?

Giả sử dự án có hai lớp:

```text
src/main/java/
└── com/example/
    ├── Main.java
    └── LegacyExporter.java
```

Sau khi biên dịch, thư mục đầu ra có:

```text
build/classes/
└── com/example/
    ├── Main.class
    └── LegacyExporter.class
```

Sau đó nhóm phát triển xóa `LegacyExporter.java` khỏi source. Nếu chỉ chạy lại target compile mà target không xóa thư mục classes, `LegacyExporter.class` cũ có thể vẫn tồn tại. Tệp `.class` đó không còn được tạo từ nguồn hiện tại, nhưng vẫn có thể được classloader tìm thấy nếu thư mục `build/classes` nằm trên classpath.

Điều này có thể gây ra một số tình huống khó chẩn đoán:

- Một lớp đã xóa vẫn được chạy hoặc được một lớp khác nạp thành công trên máy developer.
- Một JAR mới vô tình chứa lớp đã bị loại khỏi source.
- Build trên máy sạch thất bại vì lớp cũ không tồn tại ở đó.
- Một package hoặc source root đã đổi tên nhưng bytecode theo cấu trúc cũ vẫn còn.

Không chỉ lớp top-level mới có nguy cơ tồn tại cũ. Một tệp Java có thể tạo ra nhiều class file, ví dụ lớp lồng nhau, anonymous class hoặc inner class. Khi mã nguồn thay đổi và một lớp lồng bị xóa, các file như `Main$LegacyHandler.class` từ lần biên dịch trước cũng có thể còn nếu thư mục output không được làm sạch.

## 3. Lớp cũ do thay đổi include/exclude

Ant `<javac>` có thể giới hạn nguồn bằng `includes` và `excludes`:

```xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       includeantruntime="false">
    <include name="**/*.java"/>
    <exclude name="**/experimental/**"/>
</javac>
```

Giả sử lần build trước đã biên dịch `src/main/java/com/example/experimental/Preview.java`. Sau đó buildfile thêm exclude `**/experimental/**`. Từ lần build mới, Ant không còn chọn `Preview.java`; tuy nhiên, việc không chọn một nguồn không đồng nghĩa với việc task tự xóa `Preview.class` đã có trong `destdir`.

Tương tự, nếu thay include từ `**/*.java` sang chỉ `com/example/api/**/*.java`, các class nằm ngoài package `api` có thể còn lại. Vì vậy, khi thay đổi source set hoặc pattern include/exclude, clean build là cách rõ ràng để bảo đảm thư mục classes chỉ chứa đầu ra của tập nguồn hiện tại.

## 4. Tài nguyên cũ cũng có thể còn trong thư mục output

Build thường sao chép resource như `.properties`, XML, JSON, template, ảnh hoặc file cấu hình từ `src/main/resources` sang thư mục output. Ví dụ:

```xml
<copy todir="build/resources">
    <fileset dir="src/main/resources"/>
</copy>
```

Task copy đưa các tệp nguồn phù hợp vào thư mục đích. Nếu một tệp nguồn bị xóa hoặc không còn khớp fileset, tệp đích đã được copy từ lần trước có thể vẫn tồn tại. Việc copy các tệp hiện có không tự động đồng nghĩa với việc đồng bộ chính xác toàn bộ nội dung thư mục đích.

Ví dụ:

```text
src/main/resources/
└── config/
    └── application.properties
```

Ở lần build trước, `src/main/resources/config/legacy.properties` cũng từng tồn tại và được copy. Sau khi xóa tệp nguồn đó, thư mục `build/resources/config/legacy.properties` có thể vẫn còn nếu không xóa hoặc đồng bộ thư mục đích.

Tài nguyên cũ có thể gây ra lỗi tương tự lớp cũ: ứng dụng nạp nhầm cấu hình, đọc template đã bị loại bỏ hoặc đóng gói một file không còn được quản lý trong source.

## 5. Target `clean` cơ bản

Một buildfile Ant thường định nghĩa target `clean` để xóa các thư mục đầu ra có thể tạo lại:

```xml
<project name="inventory-app" default="compile" basedir=".">

    <property name="build.dir" location="build"/>
    <property name="dist.dir" location="dist"/>

    <target name="clean" description="Remove generated build output">
        <delete dir="${build.dir}"/>
        <delete dir="${dist.dir}"/>
    </target>

    <target name="compile">
        <mkdir dir="${build.dir}/classes"/>
        <javac srcdir="src/main/java"
               destdir="${build.dir}/classes"
               includeantruntime="false"
               encoding="UTF-8"/>
    </target>

</project>
```

`<delete dir="..."/>` xóa thư mục được chỉ định cùng nội dung bên trong. Sau đó target compile tạo lại thư mục cần thiết bằng `<mkdir>`.

Chỉ xóa các thư mục đầu ra mà dự án sở hữu và có thể tạo lại, chẳng hạn `build/`, `dist/` hoặc thư mục generated output. Không đặt thư mục source, thư mục chứa dữ liệu đầu vào của người dùng hoặc thư mục cấu hình cần giữ vào danh sách clean.

Nếu dự án có nhiều output directory riêng, cần khai báo và xóa từng thư mục đó. Ví dụ `build/classes`, `build/resources`, `build/generated-sources`, `build/test-classes` và `build/reports` có thể được quản lý dưới một `build.dir` chung để target clean đơn giản hơn.

## 6. Tổ chức thư mục đầu ra để clean dễ dàng

Clean build sẽ an toàn và dễ dự đoán hơn nếu tất cả đầu ra được sinh nằm dưới một hoặc vài thư mục được quy ước rõ.

```text
project/
├── build.xml
├── src/
│   ├── main/java/
│   ├── main/resources/
│   └── test/java/
├── build/
│   ├── classes/
│   ├── resources/
│   ├── test-classes/
│   ├── generated-sources/
│   └── reports/
└── dist/
```

Một số nguyên tắc hữu ích:

- Không biên dịch `.class` trực tiếp vào thư mục source.
- Không ghi resource đã xử lý đè lên resource gốc.
- Đặt generated source và generated resource trong thư mục output riêng.
- Giữ test output tách khỏi main output nếu chúng có vòng đời khác nhau.
- Dùng property như `build.dir`, `classes.dir`, `resources.dir` để các target cùng tham chiếu một cấu trúc.
- Clean target chỉ xóa những thư mục đã xác định là đầu ra có thể tái tạo.

Ví dụ property:

```xml
<property name="build.dir" location="build"/>
<property name="classes.dir" location="${build.dir}/classes"/>
<property name="resources.out" location="${build.dir}/resources"/>
<property name="test.classes.dir" location="${build.dir}/test-classes"/>
<property name="generated.dir" location="${build.dir}/generated-sources"/>
<property name="reports.dir" location="${build.dir}/reports"/>
<property name="dist.dir" location="dist"/>
```

Khi mọi output được gom theo quy ước, một lệnh xóa `build.dir` có thể loại bỏ phần lớn trạng thái cũ của quá trình build.

## 7. Tạo target `clean-build`

Có thể định nghĩa target chuyên dùng để chạy clean trước một build hoàn chỉnh:

```xml
<target name="clean-build"
        depends="clean,compile,process-resources,package"
        description="Run a complete build from clean output"/>
```

Ant thực hiện các dependency theo thứ tự được liệt kê, đồng thời tôn trọng dependency của từng target. Vì `clean` đứng trước `compile`, `process-resources` và `package`, các bước tạo output chạy sau khi thư mục cũ đã bị xóa.

Có thể gọi target:

```sh
ant clean-build
```

Hoặc chạy các target theo thứ tự từ command line:

```sh
ant clean compile process-resources package
```

Target `clean-build` giúp nhóm và CI có một tên target rõ ràng cho build sạch. Không nên thêm `clean` làm dependency của mọi target compile nếu muốn giữ lợi ích build tăng dần trong quá trình phát triển.

## 8. Ví dụ buildfile có compile, process resources và package

Ví dụ sau tách lớp, tài nguyên và JAR thành các bước riêng. Target `clean-build` xóa đầu ra rồi tạo lại toàn bộ:

```xml
<project name="inventory-app" default="compile" basedir=".">

    <property name="build.dir" location="build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="resources.out" location="${build.dir}/resources"/>
    <property name="dist.dir" location="dist"/>
    <property name="app.jar" location="${dist.dir}/inventory-app.jar"/>

    <path id="compile.classpath">
        <fileset dir="lib" includes="*.jar"/>
    </path>

    <target name="clean" description="Delete generated output">
        <delete dir="${build.dir}"/>
        <delete dir="${dist.dir}"/>
    </target>

    <target name="compile">
        <mkdir dir="${classes.dir}"/>
        <javac srcdir="src/main/java"
               destdir="${classes.dir}"
               includeantruntime="false"
               encoding="UTF-8">
            <classpath refid="compile.classpath"/>
        </javac>
    </target>

    <target name="process-resources">
        <delete dir="${resources.out}"/>
        <mkdir dir="${resources.out}"/>
        <copy todir="${resources.out}">
            <fileset dir="src/main/resources"/>
        </copy>
    </target>

    <target name="package" depends="compile,process-resources">
        <mkdir dir="${dist.dir}"/>
        <delete file="${app.jar}" quiet="true"/>
        <jar destfile="${app.jar}">
            <fileset dir="${classes.dir}"/>
            <fileset dir="${resources.out}"/>
            <manifest>
                <attribute name="Main-Class" value="com.example.Main"/>
            </manifest>
        </jar>
    </target>

    <target name="clean-build"
            depends="clean,package"
            description="Create the application from clean output"/>

</project>
```

Ở ví dụ này:

- `clean` xóa toàn bộ thư mục build và dist.
- `compile` biên dịch mã Java vào `build/classes`.
- `process-resources` xóa resource output cũ rồi copy lại từ source hiện tại.
- `package` tạo lại JAR từ lớp và resource vừa tạo.
- `clean-build` chạy clean trước package; dependency của package tiếp tục chạy compile và process-resources.

Việc xóa riêng `resources.out` trong `process-resources` còn bảo đảm target này có thể chạy độc lập sau khi source resource thay đổi. Nếu muốn giữ incremental copy, có thể dùng chiến lược đồng bộ phù hợp, nhưng cần có cách loại bỏ file đích đã không còn nguồn tương ứng.

## 9. Vì sao clean build quan trọng khi xóa hoặc đổi tên lớp?

Một ví dụ cụ thể:

Lần đầu dự án có:

```text
src/main/java/com/example/
├── Main.java
└── OldService.java
```

Sau compile:

```text
build/classes/com/example/
├── Main.class
└── OldService.class
```

Sau refactor, `OldService.java` bị xóa và chức năng được chuyển sang `NewService.java`. Nếu chỉ chạy compile tăng dần, output có thể trở thành:

```text
build/classes/com/example/
├── Main.class
├── OldService.class
└── NewService.class
```

Khi chạy `ant clean-build`, thư mục classes cũ bị xóa. Compiler chỉ tạo các lớp từ source còn lại:

```text
build/classes/com/example/
├── Main.class
└── NewService.class
```

Kết quả sạch cho thấy `OldService.class` không còn được tạo ra. Điều này đặc biệt quan trọng khi target package lấy toàn bộ nội dung `build/classes` để đưa vào JAR.

## 10. Phát hiện tài nguyên cũ sau khi thay đổi source set

Tương tự lớp Java, resource output có thể còn file đã bị xóa khỏi source hoặc bị loại bởi pattern.

Ví dụ source resource:

```text
src/main/resources/
├── application.properties
└── templates/
    └── legacy-email.html
```

Sau khi xóa `legacy-email.html`, một lần copy thông thường không nhất thiết xóa bản đích cũ. Nếu package dùng toàn bộ `build/resources`, JAR mới có thể vẫn chứa template đã bỏ.

Một cách xử lý là xóa resource output trước khi copy:

```xml
<target name="process-resources">
    <delete dir="build/resources"/>
    <mkdir dir="build/resources"/>
    <copy todir="build/resources">
        <fileset dir="src/main/resources">
            <include name="**/*"/>
            <exclude name="**/local/**"/>
        </fileset>
    </copy>
</target>
```

Khi source resource hoặc include/exclude thay đổi, output mới sẽ chỉ gồm những file còn được chọn. Nếu thư mục đích chứa dữ liệu do người dùng tạo hoặc file không được tái tạo từ source, không xóa cả thư mục đó; hãy tách dữ liệu cần giữ khỏi thư mục output có thể tái tạo.

## 11. Lớp và resource sinh tự động

Một số build tạo mã Java hoặc resource từ schema, WSDL, OpenAPI, database model, template hoặc file cấu hình. Đầu ra sinh tự động cũng có thể bị cũ khi nguồn generator thay đổi.

Ví dụ target tạo source:

```xml
<property name="generated.src.dir" location="build/generated-sources"/>

<target name="generate-sources">
    <delete dir="${generated.src.dir}"/>
    <mkdir dir="${generated.src.dir}"/>
    <!-- Gọi generator để ghi các tệp .java mới vào generated.src.dir. -->
</target>

<target name="compile" depends="generate-sources">
    <mkdir dir="build/classes"/>
    <javac destdir="build/classes"
           includeantruntime="false">
        <src path="src/main/java"/>
        <src path="${generated.src.dir}"/>
    </javac>
</target>
```

Xóa generated output trước khi chạy generator giúp loại bỏ các tệp được sinh ở phiên bản trước nhưng không còn được tạo trong lần hiện tại. Nếu không làm sạch, source sinh cũ có thể tiếp tục được biên dịch dù schema hoặc cấu hình generator đã thay đổi.

Không xóa thư mục chứa schema, file OpenAPI hoặc input generator. Chỉ xóa thư mục output dành riêng cho kết quả được sinh.

## 12. Thay đổi classpath hoặc compiler có thể cần clean build

Build tăng dần thường dựa trên thông tin về tệp nguồn và thời điểm sửa đổi để quyết định biên dịch lại. Một số thay đổi của môi trường build không thể hiện như một thay đổi nội dung trong từng file `.java`, ví dụ:

- Nâng hoặc thay phiên bản JDK/compiler.
- Thay đổi `source`, `target` hoặc `release`.
- Thay đổi annotation processor hoặc generator.
- Thay JAR trên compile classpath bằng một phiên bản khác.
- Thay đổi compiler arguments hoặc encoding.
- Thay đổi source root, include/exclude hoặc cấu hình module.

Tùy compiler và cấu hình Ant, các thay đổi này không phải lúc nào cũng khiến mọi lớp liên quan được biên dịch lại theo cách mong muốn. Clean build tạo lại bytecode dưới cấu hình hiện tại và là cách đơn giản để loại trừ ảnh hưởng của output được tạo bởi môi trường trước.

Ví dụ, nếu thay đổi JDK release:

```xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       release="21"
       includeantruntime="false"/>
```

Sau khi thay từ release cũ sang `21`, nên chạy clean build ít nhất một lần để chắc chắn toàn bộ output được tạo theo cấu hình mới. Điều này cũng áp dụng khi thay dependency có ảnh hưởng tới API mà mã nguồn biên dịch dựa vào.

## 13. Clean build trước khi đóng gói và phát hành

JAR thường được tạo từ thư mục classes hoặc từ một staging directory. Nếu những thư mục đó còn file cũ, artifact phát hành có thể chứa nội dung không còn tồn tại trong source.

Ví dụ package:

```xml
<jar destfile="dist/application.jar" basedir="build/classes"/>
```

Nếu `build/classes` còn `LegacyService.class`, task JAR có thể đưa lớp đó vào archive. Clean build trước package giúp giảm nguy cơ phát hành class cũ.

Một quy trình phát hành có thể chạy:

```sh
ant clean-build
```

Sau đó kiểm tra archive:

```sh
jar tf dist/application.jar
```

Nếu artifact chứa nhiều loại đầu ra như classes, resource, generated metadata và thư viện, hãy bảo đảm từng thư mục staging cũng được tái tạo hoặc đồng bộ đúng cách trước khi đóng gói.

## 14. Dùng clean build trong CI

CI thường chạy trên workspace mới hoặc workspace được tái sử dụng tùy cấu hình agent. Nếu agent tái sử dụng workspace, output của build trước có thể còn lại. Vì vậy, pipeline cần quy định rõ việc clean.

Ví dụ:

```sh
ant clean-build test package
```

Hoặc nếu `clean-build` đã bao gồm package:

```sh
ant clean-build test
```

Không chạy lặp cả hai cách nếu target `clean-build` đã tạo artifact và target `package` lại thực hiện công việc tương tự mà không có lý do. Hãy định nghĩa dependency giữa target rõ ràng để CI không vô tình chạy package trước clean hoặc chạy lại bước tốn thời gian không cần thiết.

Một số pipeline có thể dùng workspace mới cho mỗi job; trong trường hợp đó, rủi ro stale output thấp hơn. Tuy nhiên, target clean vẫn hữu ích vì nó làm rõ quy trình và cho phép chạy cùng cách trên máy developer, CI và môi trường phát hành.

## 15. Không nên clean mọi lần build

Clean build có chi phí vì phải biên dịch lại và tái tạo toàn bộ output. Nếu dự án lớn, chạy clean trước mọi target compile sẽ làm mất lợi ích của build tăng dần.

Một cách tổ chức hợp lý là cung cấp cả hai đường đi:

```xml
<target name="compile">
    <!-- Incremental compile -->
</target>

<target name="clean-build" depends="clean,package"/>
```

Trong vòng lặp phát triển, developer có thể chạy:

```sh
ant compile
```

Khi cần xác minh output sạch hoặc chuẩn bị phát hành:

```sh
ant clean-build
```

Khi nghi ngờ một lớp hoặc resource cũ, có thể chạy clean rồi build lại để xác định vấn đề có đến từ output cũ hay không. Nếu lỗi biến mất sau clean, cần xem lại target incremental và cách quản lý output thay vì chỉ coi clean là cách sửa lâu dài.

## 16. Kiểm tra output để nhận diện lớp cũ và resource cũ

Clean build là một cách loại bỏ stale output; việc kiểm tra thư mục và archive cũng giúp xác định file nào đang được tạo.

### Liệt kê lớp trong JAR

```sh
jar tf dist/application.jar
```

Tìm những class không còn trong source hoặc package đã được đổi tên. Có thể so sánh danh sách entry với source set hiện tại nếu dự án có script hỗ trợ.

### Liệt kê output trên Windows PowerShell

```powershell
Get-ChildItem -Recurse -File build\classes
Get-ChildItem -Recurse -File build\resources
```

### Liệt kê output trên Linux/macOS

```sh
find build/classes -type f
find build/resources -type f
```

Nếu output được tạo trong một workspace cũ, hãy xem thời gian sửa đổi và đường dẫn tương đối của file. Một class có tên tương ứng với source đã xóa là dấu hiệu cần kiểm tra, nhưng không phải mọi class file đều có tên trùng trực tiếp với một tệp `.java`: inner class và generated class có thể có tên riêng.

## 17. Clean target cho nhiều module

Trong dự án nhiều module, mỗi module có thể có thư mục output riêng:

```text
project/
├── build.xml
├── core/
│   ├── build.xml
│   └── build/
├── web/
│   ├── build.xml
│   └── build/
└── integration-tests/
    ├── build.xml
    └── build/
```

Project cha có thể gọi target clean của từng sub-build:

```xml
<target name="clean-all">
    <ant antfile="build.xml" dir="core" target="clean" inheritAll="false"/>
    <ant antfile="build.xml" dir="web" target="clean" inheritAll="false"/>
    <ant antfile="build.xml" dir="integration-tests" target="clean" inheritAll="false"/>
</target>
```

Mỗi module chịu trách nhiệm xóa output của chính nó. Điều này giúp project cha không phải biết mọi thư mục trung gian bên trong từng module. Nếu dùng `<import>` thay cho sub-build, hãy nhớ các target được nhập chạy trong project chính và chịu ảnh hưởng bởi `basedir` của project chính.

Khi clean nhiều module, cần xác định rõ output dùng chung. Không để hai module cùng ghi vào một thư mục rồi một module xóa thư mục đó trong khi module kia vẫn cần dùng.

## 18. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Class đã xóa khỏi source vẫn nằm trong JAR | `.class` cũ còn trong `destdir` và package lấy toàn bộ thư mục classes | Chạy clean build hoặc quản lý output theo source set được tái tạo |
| Lớp inner cũ vẫn được nạp | File `Outer$OldInner.class` còn từ lần biên dịch trước | Xóa thư mục classes trước khi biên dịch lại |
| Resource đã xóa vẫn có trong JAR | Task copy không xóa file đích không còn nguồn | Xóa resource output trước khi copy hoặc dùng cơ chế đồng bộ có kiểm soát |
| Class thuộc package đã exclude vẫn xuất hiện | Exclude chỉ ngừng chọn source, không xóa output cũ | Clean `destdir` khi source selection thay đổi |
| Máy developer build được nhưng CI thất bại | Developer có stale class hỗ trợ vô tình, CI bắt đầu từ output sạch | Chạy clean build và sửa dependency/source thực sự còn thiếu |
| Thay JDK nhưng bytecode không đồng nhất | Output cũ được tạo bằng compiler/options trước | Clean rồi biên dịch bằng JDK và tùy chọn mới |
| Generated source cũ vẫn được biên dịch | Generator không xóa file output đã bỏ | Xóa generated output trước khi chạy generator |
| Target clean xóa nhầm dữ liệu | Output và input được đặt chung thư mục hoặc property sai | Tách thư mục output khỏi source/data và chỉ xóa path đã xác định |
| Clean build chạy quá lâu | Target clean bị thêm vào mọi lần compile hoặc package | Tách target incremental và clean-build; chỉ clean khi cần |
| JAR vẫn chứa entry cũ dù classes đã sạch | Archive hoặc staging resource còn sót, hoặc package không tạo lại archive | Xóa JAR đích và tái tạo staging/output trước khi đóng gói |

## 19. Checklist lựa chọn clean build

- [ ] Có thay đổi source root, package, include hoặc exclude không?
- [ ] Có xóa hoặc đổi tên lớp, inner class hay generated source không?
- [ ] Có xóa hoặc đổi tên resource, template hay file cấu hình không?
- [ ] Có thay đổi JDK, compiler option, classpath hoặc annotation processor không?
- [ ] Có dấu hiệu class/resource cũ vẫn nằm trong output hoặc JAR không?
- [ ] Các thư mục output đã được tách khỏi source và dữ liệu cần giữ chưa?
- [ ] Target `clean` chỉ xóa output có thể tái tạo chưa?
- [ ] Target `clean-build` bảo đảm clean chạy trước compile, resource processing và package chưa?
- [ ] CI hoặc quy trình phát hành có một đường chạy từ output sạch chưa?
- [ ] Đã kiểm tra nội dung JAR và thư mục resource sau clean build khi cần chưa?

Clean build là cách tạo lại đầu ra từ source hiện tại thay vì tiếp tục dùng những gì còn sót từ lần trước. Trong Ant, hãy định nghĩa target `clean` để xóa output có thể tái tạo, tổ chức các thư mục classes/resources/generated riêng và tạo target `clean-build` chạy clean trước khi biên dịch, xử lý tài nguyên và đóng gói. Dùng build tăng dần cho vòng lặp nhanh; dùng clean build khi thay đổi source set, môi trường compiler, chuẩn bị phát hành hoặc cần xác nhận rằng artifact không chứa lớp và tài nguyên cũ.
