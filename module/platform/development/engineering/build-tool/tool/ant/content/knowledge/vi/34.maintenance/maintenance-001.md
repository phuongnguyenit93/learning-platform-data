# Quy ước đặt tên target, property, path ID và macro trong Apache Ant

## 1. Vì sao đặt tên là một phần của bảo trì build?

Với **Apache Ant**, một dự án nhỏ có thể bắt đầu bằng vài target trong một tệp `build.xml`. Khi dự án phát triển, nhiều người cùng sửa quy trình biên dịch, kiểm thử, đóng gói và chạy CI, các tên không nhất quán bắt đầu gây lỗi khó phát hiện:

- Target `make`, `build` và `compileAll` có tên khác nhau nhưng cùng thực hiện biên dịch.
- Property `dir`, `buildDir` và `output.path` cùng chỉ tới một thư mục.
- Một `<path>` có `id="cp"` khiến người đọc không biết đó là compile classpath hay runtime classpath.
- Macro `doStuff` không cho biết thao tác gì, trong khi người gọi nhầm nó với một target có thể chạy trực tiếp bằng `ant`.
- Một tệp Ant nhập (import) thêm target cùng tên, làm thay đổi đường đi build hoặc tạo xung đột.

Ant không bắt buộc dự án dùng một kiểu chữ đặt tên duy nhất. Tuy nhiên, **một quy ước nhất quán, có ý nghĩa và dễ tìm kiếm** giúp bảo trì an toàn hơn nhiều so với tên ngắn tùy hứng.

Trong bài này, ta chọn một quy ước thống nhất để minh họa. Đây là **quy ước khuyến nghị của dự án**, không phải quy tắc cú pháp bắt buộc của Ant:

| Thành phần | Vai trò | Quy ước đề xuất | Ví dụ |
| --- | --- | --- | --- |
| `target name` | Hành động hoặc mốc của quy trình | Động từ + đối tượng, `kebab-case` | `compile-main`, `run-tests`, `package-jar` |
| `property name` | Giá trị cấu hình hoặc đường dẫn | Danh từ theo nhóm, `dot.case` | `src.main.dir`, `java.release` |
| `path id` | Tham chiếu một tập đường dẫn | Loại path + mục đích, `dot.case` | `classpath.compile`, `classpath.runtime` |
| `macrodef name` | Tác vụ tái sử dụng tại nơi gọi | Động từ + đối tượng, `kebab-case` | `log-step`, `copy-resources` |
| `macrodef attribute name` | Tham số của macro | Tên ngắn có nghĩa, `kebab-case` | `step`, `destination-dir` |

Điểm cốt lõi là **đọc tên phải dự đoán được chức năng**, và nhìn tên phải biết đang tham chiếu **target, property, path ID hay macro**.

## 2. Hiểu đúng bốn loại tên trước khi tạo quy ước

Bốn loại tên này xuất hiện trong các thành phần XML khác nhau và có cách sử dụng khác nhau.

### 2.1. Target: bước được Ant điều phối

```xml
<target name="compile-main">
    <!-- Các task biên dịch -->
</target>
```

Một target có thể được gọi bằng:

```bash
ant compile-main
```

hoặc trở thành dependency của target khác:

```xml
<target name="package-jar" depends="compile-main">
    <!-- Đóng gói sau khi biên dịch -->
</target>
```

`name` của target vì vậy là **giao diện điều khiển build**. Khi người dùng hoặc CI thường xuyên gọi `ant verify`, tên `verify` là một phần của hợp đồng vận hành mà việc đổi tên có thể làm hỏng script bên ngoài.

### 2.2. Property: giá trị được thay thế trong cấu hình

```xml
<property name="build.classes.dir" location="build/classes"/>

<mkdir dir="${build.classes.dir}"/>
```

Property dùng cú pháp `${...}` khi tham chiếu. Thông thường, một property đã được đặt không thể bị ghi đè bằng một khai báo `<property>` sau đó; các giá trị `-Dname=value` truyền qua dòng lệnh có thể chiếm quyền ưu tiên. Do vậy **tên property phải thể hiện rõ giá trị mà người dùng được phép cấu hình**, tránh đặt nhiều tên khác nhau cho cùng một mục đích.

### 2.3. Path ID: tên của một reference chứa đường dẫn

```xml
<path id="classpath.compile">
    <fileset dir="lib" includes="**/*.jar"
             erroronmissingdir="false"/>
</path>

<javac srcdir="src" destdir="build/classes"
       includeantruntime="false">
    <classpath refid="classpath.compile"/>
</javac>
```

`id` tạo một **reference** trong Ant; `refid` lấy reference đó. Nó không phải property và không được sử dụng như `${classpath.compile}` để lấy danh sách JAR theo cách trên. Tên path nên cho biết đó là compile classpath, runtime classpath hay đường dẫn công cụ.

### 2.4. Macro: thao tác được tái sử dụng

```xml
<macrodef name="log-step">
    <attribute name="step"/>
    <attribute name="message"/>
    <sequential>
        <echo level="info" message="[@{step}] @{message}"/>
    </sequential>
</macrodef>
```

Sau khi định nghĩa, dùng:

```xml
<log-step step="compile-main" message="Bắt đầu biên dịch"/>
```

Tên `log-step` là tên **task được macrodef định nghĩa**, còn `step` và `message` là tham số macro, tham chiếu bằng `@{...}`. Macro **không phải target**: không thể mặc định gọi `ant log-step` chỉ vì đã khai báo `macrodef name="log-step"`. Macro thực thi khi một target hoặc tác vụ khác gọi nó.

## 3. Quy ước đặt tên target

### 3.1. Dùng động từ, đối tượng và phạm vi cụ thể

Tên nên mô tả việc target *làm*:

| Nên dùng | Hạn chế dùng | Lý do |
| --- | --- | --- |
| `clean` | `clearStuff` | Thuật ngữ quen thuộc cho việc xóa output build |
| `compile-main` | `compile1` | Rõ loại source được biên dịch |
| `compile-tests` | `testCompileThing` | Rõ bước biên dịch mã kiểm thử |
| `run-tests` | `doTest` | Rõ đây là bước thực thi test |
| `package-jar` | `jarThing` | Nói rõ loại artifact được tạo |
| `generate-docs` | `docsStep2` | Không phụ thuộc thứ tự đánh số |
| `verify` | `all2` | Mốc xác nhận build có thể gọi từ CI |
| `publish-artifact` | `uploadIt` | Rõ tác động ra hệ thống ngoài |

Tên `clean`, `compile`, `test`, `package`, `verify` có tính quen thuộc trong hệ sinh thái build. Một dự án có thể dùng các tên này cho **mốc công khai** và các tên chi tiết `compile-main`, `compile-tests` cho **bước nội bộ**.

Khi dự án có nhiều phần, thêm đối tượng rõ ràng: `compile-client`, `compile-server` hoặc `package-cli`. Không thêm tiền tố quá dài nếu toàn bộ file Ant đã nằm trong một module xác định và tên không mơ hồ.

### 3.2. Chọn một kiểu chữ và giữ nhất quán

Ví dụ dùng `kebab-case`:

```xml
<target name="prepare-build"/>
<target name="compile-main" depends="prepare-build"/>
<target name="package-jar" depends="compile-main"/>
<target name="verify" depends="package-jar"/>
```

Hạn chế cùng một file có kiểu lẫn lộn như:

```xml
<target name="PrepareBuild"/>
<target name="compile_main"/>
<target name="packageJar"/>
<target name="VERIFY"/>
```

Các kiểu trên không nhất thiết sai cú pháp, nhưng gây khó tìm kiếm và dễ viết nhầm trong `depends` hoặc script CI. Tên target có phân biệt chữ hoa/chữ thường; `compile-main` và `Compile-Main` không nên được xem là một.

### 3.3. Target công khai và target hỗ trợ

Ant có các target mà người dùng/CI gọi trực tiếp, và các target chỉ dùng để cấu tạo chuỗi dependency. Có thể phân biệt bằng tài liệu hoặc tiền tố nếu nhóm đã thống nhất.

Ví dụ:

```xml
<project name="shop-build" default="verify">
    <target name="prepare-directories"
            description="Tạo các thư mục đầu ra cần thiết"/>

    <target name="compile-main" depends="prepare-directories"/>

    <target name="verify" depends="compile-main"
            description="Thực hiện luồng xác nhận build chính"/>
</project>
```

`description` giúp một target xuất hiện trong danh sách target có mô tả khi chạy `ant -projecthelp`. Có thể dành `description` cho những target mà nhóm muốn người dùng biết và gọi trực tiếp.

Một số dự án đặt tên target hỗ trợ bằng tiền tố như `-prepare-internal`. Trong Ant, tiền tố dấu gạch ngang không phải cơ chế bảo mật, và việc bảo vệ target phụ thuộc vào cách công cụ xử lý tên/điểm vào. **Không nên coi một quy ước tên là kiểm soát truy cập**. Muốn phân biệt public/internal, hãy ghi rõ giao diện được hỗ trợ và cấu trúc dependency.

### 3.4. Đừng nhét thứ tự vào tên

Không nên tạo:

```xml
<target name="step1"/>
<target name="step2"/>
<target name="step3"/>
```

chỉ vì hiện tại ba bước diễn ra theo thứ tự đó. Khi thêm bước ở giữa, toàn bộ tên và chỗ gọi có thể phải đổi. Hãy đặt tên theo trách nhiệm và dùng `depends` cho thứ tự:

```xml
<target name="generate-sources"/>
<target name="compile-main" depends="generate-sources"/>
<target name="package-jar" depends="compile-main"/>
```

`depends` là quan hệ điều phối của Ant, còn tên target biểu đạt **ý nghĩa ổn định của thao tác**.

### 3.5. Tránh tên mơ hồ, quá rộng hoặc hứa hẹn vượt quá thực tế

Target `verify` nên thật sự chạy các bước xác nhận mà dự án cam kết. Nếu `verify` chỉ biên dịch, không chạy test dù nhóm hiểu “verify” là compile + test, tên này gây hiểu lầm. Có thể bắt đầu bằng `compile-main` và chỉ tạo `verify` khi quy trình hoàn chỉnh.

Ngược lại, target `build-everything-deploy-everywhere` vừa dài vừa trộn bước build với side effect triển khai. Tốt hơn nên có `package-jar` và `deploy-staging` tách biệt, với target tổng hợp rõ ràng nếu thực sự cần.

## 4. Quy ước đặt tên property

### 4.1. Dùng `dot.case` để nhóm theo ý nghĩa

Ví dụ một bộ property thống nhất:

```xml
<property name="src.main.dir" location="src/main/java"/>
<property name="src.test.dir" location="src/test/java"/>
<property name="src.resources.dir" location="src/main/resources"/>

<property name="build.dir" location="build"/>
<property name="build.classes.dir" location="${build.dir}/classes"/>
<property name="build.test-classes.dir" location="${build.dir}/test-classes"/>

<property name="dist.dir" location="dist"/>
<property name="artifact.name" value="shop-app"/>
<property name="artifact.version" value="1.0.0"/>

<property name="java.release" value="17"/>
<property name="build.profile" value="local"/>
```

Nhóm tên giúp người bảo trì tìm kiếm hiệu quả:

- `src.*`: nguồn đầu vào.
- `build.*`: file trung gian sinh ra khi build.
- `dist.*`: output dành cho phân phối.
- `artifact.*`: tên và phiên bản sản phẩm tạo ra.
- `java.*` trong ví dụ này chỉ dùng key cụ thể như `java.release` do dự án chủ động khai báo; cần tránh xung đột với **system property** có sẵn.
- `build.profile`: lựa chọn profile có ý nghĩa với build.

Trong dự án thực tế, hãy kiểm tra các property có sẵn của Ant và JVM trước khi đặt tên. Ví dụ `ant.home`, `ant.file`, `ant.project.name`, `ant.java.version` và `java.home` đã có ý nghĩa đặc biệt. Không đặt lại chúng làm property riêng của dự án.

### 4.2. Đặt tên theo *ý nghĩa*, không theo kiểu dữ liệu thuần túy

Các tên sau thiếu ngữ cảnh:

```xml
<property name="dir" value="build"/>
<property name="name" value="shop"/>
<property name="path" value="lib"/>
<property name="flag" value="true"/>
<property name="version" value="1.0"/>
```

Khi dùng từ nhiều target, người đọc phải tìm ngược từng khai báo. Nên dùng:

```xml
<property name="build.dir" location="build"/>
<property name="artifact.name" value="shop"/>
<property name="deps.dir" location="lib"/>
<property name="artifact.version" value="1.0"/>
```

Nếu một property là đường dẫn thư mục, đuôi `.dir` làm ý nghĩa rõ ràng. Nếu là đường dẫn file, dùng `.file` (ví dụ `report.summary.file`). Nếu là URL, dùng `.url` (ví dụ `repo.publish.url`), và tránh ghi giá trị bí mật của URL vào log.

### 4.3. Phân biệt `location` và `value`

Tên tốt chưa đủ; cách khai báo phải phản ánh loại giá trị:

```xml
<property name="src.main.dir" location="src/main/java"/>
<property name="artifact.name" value="shop-app"/>
```

Với `location`, Ant chuẩn hóa đường dẫn dựa trên `basedir`. Với `value`, Ant xử lý chuỗi theo giá trị được truyền. Khi đặt tên `*.dir` và `*.file`, dùng `location` giúp giảm phụ thuộc vào thư mục hiện tại của shell nếu đường dẫn được hiểu tương đối theo project.

### 4.4. Property bất biến: không dùng một tên cho nhiều giai đoạn

Mẫu không nên dùng:

```xml
<target name="compile-main">
    <property name="output.dir" location="build/classes"/>
</target>

<target name="package-jar">
    <property name="output.dir" location="dist"/>
</target>
```

Vì property thường không bị ghi đè sau khi được đặt, `output.dir` có thể vẫn là đường dẫn của target chạy trước. Cách đặt tên riêng:

```xml
<property name="build.classes.dir" location="build/classes"/>
<property name="dist.dir" location="dist"/>
```

Nếu cần giá trị cục bộ cho một macro/target, Ant có tác vụ `<local>` trên các phiên bản hỗ trợ, hoặc có thể truyền trực tiếp tham số macro để tránh dựa vào property toàn cục thay đổi theo thời gian. Không đặt lại property toàn cục rồi mong nó là biến mutable như trong ngôn ngữ lập trình.

### 4.5. Tên property thể hiện hợp đồng CLI/CI

Một property được CI truyền qua `-D` trở thành một phần của giao diện build:

```bash
ant -Dbuild.profile=ci -Djava.release=17 verify
```

Nếu đổi `java.release` thành `jdk.version` mà không cập nhật job CI, Ant có thể dùng giá trị mặc định thay vì giá trị từ CI. Đối với property được dùng bên ngoài, cần quản lý thay đổi tương tự đổi tên tham số dòng lệnh: cập nhật caller, tài liệu và giá trị mặc định.

Hạn chế tạo hai property đồng nghĩa `jdk.version` và `java.release` lâu dài; người dùng sẽ không rõ cái nào có quyền ưu tiên.

### 4.6. Property điều kiện không phải boolean tự động

Trong cấu hình target truyền thống:

```xml
<target name="run-tests" unless="skip.tests">
    <!-- Thực thi kiểm thử -->
</target>
```

`unless="skip.tests"` kiểm tra property có **tồn tại** hay không, không tự hiểu giá trị chuỗi `false` như boolean. Lệnh `ant -Dskip.tests=false run-tests` vẫn đặt property `skip.tests`, vì vậy target có thể bị bỏ qua.

Nếu dùng điều kiện theo sự tồn tại, tên nên diễn đạt “đã được bật/được yêu cầu” và phải tạo property đó chỉ khi điều kiện đúng. Nếu muốn xử lý giá trị true/false, dùng các task điều kiện thích hợp như `<condition>` để chuyển thành một property kết quả với quy tắc rõ ràng. Không nên dùng một tên property mơ hồ như `flag` hoặc `enable`.

## 5. Quy ước đặt tên path ID

### 5.1. `id` biểu thị mục đích của tập đường dẫn

Một dự án có thể có các classpath khác nhau:

| ID đề xuất | Vai trò |
| --- | --- |
| `classpath.compile` | JAR cần để biên dịch source chính |
| `classpath.test.compile` | JAR cần để biên dịch source kiểm thử |
| `classpath.runtime` | Classes và JAR cần khi chạy ứng dụng |
| `classpath.test.runtime` | Classes và JAR cần khi chạy test |
| `path.codegen.tools` | Đường dẫn các tool tạo source |
| `path.docs.tools` | Đường dẫn công cụ xây tài liệu |

Ant không ép dùng tiền tố `classpath.`. Điểm quan trọng là **tên reference đủ rõ để tránh nhầm giữa classpath phục vụ compile và classpath phục vụ runtime**.

Ví dụ:

```xml
<path id="classpath.compile">
    <fileset dir="lib" includes="**/*.jar"
             erroronmissingdir="false"/>
</path>

<path id="classpath.runtime">
    <pathelement location="build/classes"/>
    <path refid="classpath.compile"/>
</path>
```

Sau đó:

```xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       includeantruntime="false">
    <classpath refid="classpath.compile"/>
</javac>

<java classname="com.example.App"
      fork="true">
    <classpath refid="classpath.runtime"/>
</java>
```

Hai đoạn tác vụ trên minh họa cách dùng reference trong những target phù hợp; bản thân chúng không phải một `build.xml` hoàn chỉnh.

### 5.2. Reference và property là hai loại khác nhau

Đừng đánh đồng:

```xml
<path id="classpath.compile">
    <fileset dir="lib" includes="**/*.jar"
             erroronmissingdir="false"/>
</path>
```

với:

```xml
<property name="classpath.compile" value="lib/example.jar"/>
```

Cùng một chuỗi tên nhưng khác loại: `id` là reference Ant quản lý, còn `name` là property. Dù có thể đặt trùng chuỗi, việc đó tạo ra hai thực thể khó hiểu khi bảo trì. Hãy chọn quy ước để tránh trùng lặp có thể gây nhầm: ví dụ giữ `classpath.*` cho ID của `<path>` và dùng `deps.dir`, `tool.jar.file` cho property dữ liệu.

Khi cần in path để chẩn đoán, có thể dùng `pathconvert`:

```xml
<pathconvert property="diagnostic.compile-classpath"
             refid="classpath.compile"
             pathsep=" | "/>
<echo level="verbose"
      message="[environment] classpath: ${diagnostic.compile-classpath}"/>
```

Đây là property mới chứa **biểu diễn văn bản** của path, không biến path ID gốc thành property. Chỉ ghi đường dẫn an toàn cho log, tránh vô tình để lộ vị trí chứa secret.

### 5.3. Đừng dùng ID chung chung

Các ID như `cp`, `path1`, `allJars` có thể đủ trong ví dụ 10 dòng, nhưng khó hiểu khi có nhiều macro, file import và target. Một `classpath.compile` rõ hơn vì mọi người có thể tra cứu `refid="classpath.compile"` xuyên suốt dự án.

Một lỗi phổ biến khác là đưa tất cả JAR vào một `classpath.all` rồi sử dụng trong mọi giai đoạn. Điều này có thể che giấu thiếu dependency và làm kiểm thử vô tình thành công nhờ thư viện chỉ nên có mặt ở runtime. Nên chia theo **mục đích thực thi**.

### 5.4. Đặt ID nhất quán khi chia build thành nhiều tệp

Reference ID thường được quản lý trong phạm vi project Ant đang thực thi. Khi các đoạn build được kết hợp qua `<import>` hoặc `<include>`, tên trùng có thể gây khó khăn hoặc xung đột tùy cách định nghĩa và tham chiếu. Với các đoạn dùng chung, nên áp dụng prefix theo thành phần, ví dụ `classpath.codegen` hoặc `shared.classpath.codegen` nếu cần tránh trùng.

Đừng mặc định import tự tạo scope riêng như module trong Java. Trước khi đặt ID dùng chung, cần xem các ID đang tồn tại trong project đã kết hợp.

## 6. Quy ước đặt tên macro

### 6.1. Macro được gọi như một task có tên rõ ràng

`<macrodef>` thích hợp để gom một đoạn thao tác Ant thường được lặp lại. Ví dụ, dự án muốn mọi target ghi log thống nhất:

```xml
<macrodef name="log-step">
    <attribute name="step"/>
    <attribute name="message"/>
    <attribute name="level" default="info"/>
    <sequential>
        <echo level="@{level}"
              message="[@{step}] @{message}"/>
    </sequential>
</macrodef>
```

Sau đó trong target:

```xml
<target name="prepare-build">
    <log-step step="prepare-build"
              message="Bắt đầu tạo thư mục"/>
    <mkdir dir="build"/>
</target>
```

Quy ước đặt tên macro:

- Bắt đầu bằng động từ phù hợp với tác vụ: `log-`, `copy-`, `compile-`, `validate-`, `write-`.
- Phần sau chỉ rõ đối tượng hoặc kết quả: `log-step`, `copy-resources`, `validate-input`.
- Tránh `macro1`, `common`, `helper`, `execute` vì không thể biết nó làm gì.
- Nếu macro dành riêng cho công cụ hoặc module, có thể dùng tiền tố: `java-compile-sources`, `docs-copy-assets`.

Tên macro nên giống tên **hành động nhỏ có thể tái sử dụng**, nhưng khác target ở chỗ macro không định nghĩa một bước lịch trình độc lập.

### 6.2. Tham số macro cũng cần quy ước

Tham số macro được khai báo bằng `<attribute name="...">` và dùng cú pháp `@{...}` trong nội dung macro:

```xml
<macrodef name="copy-resources">
    <attribute name="source-dir"/>
    <attribute name="destination-dir"/>
    <sequential>
        <mkdir dir="@{destination-dir}"/>
        <copy todir="@{destination-dir}">
            <fileset dir="@{source-dir}"/>
        </copy>
    </sequential>
</macrodef>
```

Người gọi:

```xml
<copy-resources
    source-dir="src/main/resources"
    destination-dir="build/classes"/>
```

Các tên `source-dir` và `destination-dir` mang nghĩa cụ thể. So với `from`/`to`, chúng dài hơn nhưng giúp người mới đọc thấy đang truyền **đường dẫn thư mục**, tránh nhầm với file hoặc pattern.

Đừng nhầm:

- `@{source-dir}`: tham số của `macrodef`.
- `${src.resources.dir}`: property Ant.

Hai cơ chế thay thế giá trị khác nhau. Trong lệnh gọi, người dùng có thể truyền property vào macro:

```xml
<copy-resources
    source-dir="${src.resources.dir}"
    destination-dir="${build.classes.dir}"/>
```

### 6.3. Tên macro và tên target nên tránh trùng ý nghĩa

Ví dụ sau khó bảo trì:

```xml
<macrodef name="build">
    <!-- Nhiều tác vụ -->
</macrodef>

<target name="build">
    <build/>
</target>
```

Dù tên target và task macro thuộc cơ chế khác nhau, người đọc dễ nhầm `ant build` với `<build/>`. Nên dùng:

```xml
<macrodef name="compile-sources">
    <!-- Thao tác lặp lại theo tham số -->
</macrodef>

<target name="compile-main">
    <compile-sources/>
</target>
```

Đoạn trên chỉ minh họa cách đặt tên, không phải định nghĩa macro đầy đủ. Target đặt tên cho **một mốc build cụ thể**; macro đặt tên cho **hành động dùng chung** mà target triển khai.

### 6.4. Tránh tạo macro quá tổng quát

Macro có hơn chục thuộc tính như `do-task` hoặc `common-operation` thường khó hiểu hơn một vài tác vụ Ant trực tiếp. Chỉ nên gom thành macro khi:

- Có đoạn thao tác được lặp lại ở nhiều nơi.
- Có hợp đồng tham số rõ.
- Tên macro có thể diễn tả hành động và phạm vi.
- Việc dùng macro khiến người bảo trì dễ hiểu hơn.

Đặt tên tốt không sửa được macro mang quá nhiều trách nhiệm. Với quy trình có nhiều dependency và điều kiện, target hoặc phần build riêng có thể phù hợp hơn.

## 7. Một bộ quy ước áp dụng xuyên suốt dự án

Giả sử một đội thống nhất:

1. **Target:** `kebab-case`, động từ trước, mốc giao diện ổn định là `clean`, `verify`; bước cụ thể như `compile-main`, `package-jar`.
2. **Property:** `dot.case`, nhóm theo chức năng; đường dẫn thư mục kết thúc bằng `.dir`, file bằng `.file`.
3. **Path ID:** tiền tố `classpath.` hoặc `path.`, tiếp theo là mục đích; tuyệt đối tránh tên `cp` trong file build lớn.
4. **Macro:** `kebab-case`, tên hành động; attribute là từ có nghĩa như `step`, `source-dir`.
5. **Không đổi tên tùy tiện:** target/`-D` public phải có kế hoạch cập nhật caller CI, script và tài liệu.

Đây là một file `build.xml` đầy đủ minh họa bộ quy ước. Dự án cần JDK 17 hoặc JDK mới hơn hỗ trợ tạo bytecode Java 17.

Cấu trúc:

```text
ant-naming-demo/
├── build.xml
├── src/
│   └── main/
│       └── java/
│           └── com/
│               └── example/
│                   └── App.java
├── lib/                  # JAR phụ thuộc nếu có
├── build/                # Output trung gian được tạo
└── dist/                 # Artifact được tạo
```

Mã `src/main/java/com/example/App.java`:

```java
package com.example;

public class App {
    public static void main(String[] args) {
        System.out.println("Ant naming conventions");
    }
}
```

Tệp `build.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="ant-naming-demo" default="verify" basedir=".">

    <!-- Property: danh từ theo nhóm, dot.case. -->
    <property name="java.release" value="17"/>
    <property name="src.main.dir" location="src/main/java"/>
    <property name="build.dir" location="build"/>
    <property name="build.classes.dir" location="${build.dir}/classes"/>
    <property name="dist.dir" location="dist"/>
    <property name="artifact.name" value="demo"/>
    <property name="artifact.jar.file"
              location="${dist.dir}/${artifact.name}.jar"/>

    <!-- Path ID: mục đích được nói rõ trong tên. -->
    <path id="classpath.compile">
        <fileset dir="lib"
                 includes="**/*.jar"
                 erroronmissingdir="false"/>
    </path>

    <path id="classpath.runtime">
        <pathelement location="${build.classes.dir}"/>
        <path refid="classpath.compile"/>
    </path>

    <!-- Macro: tên động từ, tham số ngắn nhưng rõ. -->
    <macrodef name="log-step">
        <attribute name="step"/>
        <attribute name="message"/>
        <sequential>
            <echo level="info"
                  message="[@{step}] @{message}"/>
        </sequential>
    </macrodef>

    <target name="prepare-build">
        <available file="${src.main.dir}"
                   type="dir"
                   property="src.main.exists"/>
        <fail unless="src.main.exists"
              message="[prepare-build] Thiếu thư mục ${src.main.dir}"/>

        <log-step step="prepare-build"
                  message="Tạo thư mục output"/>
        <mkdir dir="${build.classes.dir}"/>
        <mkdir dir="${dist.dir}"/>
    </target>

    <target name="compile-main" depends="prepare-build">
        <log-step step="compile-main"
                  message="Biên dịch source Java"/>
        <javac srcdir="${src.main.dir}"
               destdir="${build.classes.dir}"
               release="${java.release}"
               encoding="UTF-8"
               includeantruntime="false">
            <classpath refid="classpath.compile"/>
        </javac>
        <log-step step="compile-main"
                  message="Biên dịch hoàn tất"/>
    </target>

    <target name="package-jar" depends="compile-main">
        <log-step step="package-jar"
                  message="Đóng gói JAR"/>
        <jar destfile="${artifact.jar.file}"
             basedir="${build.classes.dir}"/>
        <log-step step="package-jar"
                  message="Đã tạo ${artifact.jar.file}"/>
    </target>

    <target name="verify" depends="package-jar"
            description="Build và kiểm tra artifact JAR">
        <available file="${artifact.jar.file}"
                   type="file"
                   property="artifact.jar.exists"/>
        <fail unless="artifact.jar.exists"
              message="[verify] Không tìm thấy JAR đầu ra"/>
        <log-step step="verify"
                  message="Artifact JAR đã được tạo"/>
    </target>

    <target name="run-app" depends="compile-main"
            description="Chạy chương trình demo">
        <java classname="com.example.App"
              fork="true"
              failonerror="true">
            <classpath refid="classpath.runtime"/>
        </java>
    </target>

    <target name="clean"
            description="Xóa thư mục output của build">
        <delete dir="${build.dir}"/>
        <delete dir="${dist.dir}"/>
    </target>

</project>
```

Thực thi:

```bash
ant -projecthelp
ant verify
ant run-app
ant clean
ant verify
```

Những gì tên trong ví dụ cho biết:

| Tên | Loại | Ý nghĩa |
| --- | --- | --- |
| `verify` | Target | Điểm vào kiểm tra artifact |
| `prepare-build` | Target | Chuẩn bị trước khi compile |
| `compile-main` | Target | Biên dịch source chính |
| `package-jar` | Target | Tạo JAR |
| `java.release` | Property | Mức tương thích Java yêu cầu |
| `build.classes.dir` | Property | Thư mục chứa `.class` |
| `artifact.jar.file` | Property | Đường dẫn JAR đầu ra |
| `classpath.compile` | Path ID | Thư viện compiler cần đọc |
| `classpath.runtime` | Path ID | Classpath khi thực thi |
| `log-step` | Macro | Ghi log theo target |

Điểm chú ý: `verify` trong ví dụ chỉ xác nhận **artifact JAR tồn tại** sau khi build; nó **chưa có bộ test tự động**. Khi thêm test thật, hãy mở rộng dependency của `verify` theo đúng cam kết của dự án, thay vì giả định tên `verify` tự động chạy mọi bước kiểm thử.

## 8. Quy ước khi nhiều tệp Ant được import/include

Trong dự án lớn, team có thể chia định nghĩa build thành nhiều tệp để bảo trì:

```text
build.xml
build/
  targets-java.xml
  targets-tests.xml
  macros-common.xml
```

Ant có `<import>` và `<include>` để kết hợp logic từ các file. Hai cơ chế này có quy tắc xử lý tên và target khác nhau; vì vậy không nên giả định mỗi file tạo một phạm vi tên cô lập như Java package.

Trong Ant, các target được import có thể được tham chiếu bằng tên mang tiền tố project, và quy tắc xử lý trùng tên phụ thuộc cách import/include. Do đó tên riêng của từng module có ý nghĩa:

- `java-compile-main` hoặc `compile-main` khi phạm vi đã rõ.
- `tests-run-unit` và `tests-run-integration` khi nhiều tập test.
- `docs-generate-site` cho tác vụ tạo tài liệu.

Ví dụ ở mức quy ước (không phải bộ file import hoàn chỉnh):

```text
build.xml               → verify, clean, package-jar
build/targets-java.xml  → java-compile-main
build/targets-tests.xml → tests-run-unit
build/macros-common.xml → log-step, validate-directory
```

Đặt tên không giải quyết hết vấn đề import. Khi gom file, cần kiểm tra chính xác tên target/reference đã được khai báo, đường dẫn tương đối và hành vi trùng tên của cơ chế import/include đang sử dụng. Không nên đổi tên ồ ạt mà chưa kiểm tra các chỗ gọi trong `depends` và CI.

### 8.1. Tránh va chạm với custom task và macro khác

Một macro đặt `name="copy"` sẽ dễ nhầm với task Ant có sẵn `<copy>`. Tương tự, `delete`, `jar` và `javac` là các tên task thông dụng. Hãy chọn tên macro mang ý nghĩa cụ thể như `copy-resources`, `package-extra-files` hoặc `compile-generated-sources`.

Khi xây thư viện Antlib dùng chung cho nhiều dự án, namespace XML có thể giúp phân biệt custom task; nhưng quy ước đặt tên dễ hiểu vẫn cần thiết. Các macro không nên chiếm tên task chuẩn nếu mục đích là bọc thêm hành vi riêng.

## 9. Đổi tên trong một dự án đang vận hành

Một quy ước mới chỉ hữu ích nếu không phá vỡ những lời gọi hiện có. Cần phân biệt **tên hoàn toàn nội bộ** và **giao diện mà caller bên ngoài sử dụng**.

### 9.1. Trước khi đổi tên target

Giả sử CI hiện gọi:

```bash
ant buildAll
```

Dự án muốn tên chuẩn là `verify`. Nếu sửa trực tiếp thành `verify`, các pipeline cũ sẽ báo target không tồn tại. Có thể tạm duy trì wrapper:

```xml
<target name="verify" depends="package-jar"
        description="Điểm vào build chuẩn"/>

<target name="buildAll" depends="verify"
        description="Tương thích tạm thời với script cũ"/>
```

Wrapper `buildAll` không cần lặp lại logic. Trong giai đoạn chuyển tiếp, cập nhật caller CI/scripts sang `ant verify`; sau khi xác nhận không còn nơi gọi tên cũ, mới cân nhắc xóa wrapper theo quy trình thay đổi của dự án.

Tên target là một phần của command API; việc đổi tên cần đi cùng thay đổi ở bên ngoài `build.xml`.

### 9.2. Đổi property thường cần thận trọng hơn

Giả sử trước đây có:

```xml
<property name="outputDir" location="build/classes"/>
```

và team muốn dùng `build.classes.dir`. Nếu CI vẫn truyền `-DoutputDir=...`, một khai báo property mới không tự chuyển giá trị đó. Việc giữ đồng thời hai tên và chờ Ant cập nhật một trong hai có thể phát sinh thứ tự ưu tiên khó hiểu vì property bất biến.

Đối với property công khai, nên:

1. Xác định tất cả caller đang truyền `-DoutputDir` hoặc dùng `${outputDir}`.
2. Quyết định tên chuẩn mới và nguồn giá trị của nó.
3. Cập nhật các caller và `build.xml` đồng bộ.
4. Nếu phải có giai đoạn tương thích, mô tả rõ tên nào được ưu tiên và tạo cơ chế chuyển tiếp có kiểm soát.
5. Loại bỏ alias sau khi không còn người dùng để tránh hai nguồn cấu hình.

Hạn chế đổi tên chỉ vì sở thích chữ hoa/chữ thường nếu chi phí ảnh hưởng lớn hơn lợi ích bảo trì.

### 9.3. Đổi path ID và macro

Đổi `classpath.compile` hoặc `log-step` tác động đến những chỗ tham chiếu `refid` hoặc những lời gọi element macro. Khi sửa, cần tìm đầy đủ nơi dùng trong project; với build đã chia file, kiểm tra cả những file được `import`/`include`.

Macro mới có thể giữ wrapper gọi tới macro cũ trong thời gian chuyển tiếp nếu cấu trúc phù hợp, nhưng không nên tạo một mạng alias khó theo dõi. Nếu thay đổi chỉ nằm trong một file và không có caller bên ngoài, thường có thể đổi đồng bộ trong một lần.

## 10. Phân biệt quy ước tên và cấu trúc thật của build

Tên chỉ có giá trị khi đúng với hành vi. Một số hiểu lầm cần tránh:

**`compile-tests` không có nghĩa tự chạy test.** Nó chỉ nên biên dịch mã kiểm thử; việc thực thi nên có target như `run-tests` hoặc `test`.

**`classpath.runtime` không tự tính mọi dependency.** Nó chỉ chứa các đường dẫn được khai báo hoặc bổ sung qua reference. Ant không tự tải transitive dependency chỉ vì đặt tên path là runtime.

**`java.release` không tự đổi JDK.** Đây là property thông thường do dự án khai báo. Nó chỉ ảnh hưởng compiler khi được gán vào `release`, `source` hoặc thiết lập tương ứng.

**`verify` không tự động bảo đảm chất lượng.** Nó chỉ chạy các dependency và tác vụ mà build thực sự khai báo. Nếu pipeline cần test, cần đưa test vào luồng `verify`.

**`log-step` không tự biết target hiện hành.** Trong macro ví dụ, caller truyền `step` để thông báo có ngữ cảnh. Đừng kỳ vọng Ant tự chèn tên target vào `@{step}` nếu không truyền tham số.

**`.dir` trong property name không tạo kiểu dữ liệu directory.** Quy ước đặt tên giúp người đọc hiểu mục đích; chính giá trị và task tiêu thụ quyết định cách xử lý.

## 11. Mẫu checklist đặt tên cho code review

Khi thêm target, property, path ID hoặc macro, nhóm có thể dùng bảng sau để rà soát:

| Câu hỏi | Ví dụ đạt | Dấu hiệu cần xem lại |
| --- | --- | --- |
| Target mô tả hành động cụ thể chưa? | `package-jar` | `step3` |
| Target công khai có tên ổn định không? | `verify` | Đổi tên mỗi lần sửa CI |
| Có đúng một kiểu chữ trong cùng nhóm tên không? | `compile-main`, `compile-tests` | `compileMain`, `compile_tests` |
| Property có chỉ rõ ý nghĩa và đơn vị/loại giá trị không? | `build.classes.dir` | `path`, `dir1` |
| Property có tránh tên hệ thống của Ant/JVM không? | `artifact.version` | Đặt lại `ant.home` |
| ID có chỉ rõ loại classpath/path không? | `classpath.test.runtime` | `cp2` |
| `refid` có tên trùng chính xác với ID khai báo không? | `refid="classpath.compile"` | `refid="classpath.compiles"` |
| Macro có tên là thao tác không? | `validate-input` | `helper` |
| Macro attribute có mô tả đầu vào không? | `source-dir`, `destination-dir` | `x`, `y` |
| Có vô tình dùng lại tên task chuẩn không? | `copy-resources` | Định nghĩa macro `copy` |
| Thay đổi tên có ảnh hưởng caller ngoài không? | Đã cập nhật CI/scripts | Target cũ bị xóa nhưng CI còn gọi |
| Tên có phản ánh hành vi thật không? | `run-tests` thực sự chạy test | `verify` chỉ làm `echo` |

Đây là bảng hỗ trợ đánh giá thay đổi, không phải yêu cầu mọi dự án phải dùng đúng tiền tố như ví dụ. Quan trọng nhất là sự nhất quán giữa tên và hành vi đã được nhóm thống nhất.

## 12. Bài thực hành bảo trì

### Bài 1: Đặt tên lại một build khó đọc

Giả sử bạn gặp file:

```xml
<project name="old-demo" default="all">
    <property name="d" value="out"/>
    <property name="n" value="app"/>

    <target name="one">
        <mkdir dir="${d}"/>
    </target>

    <target name="two" depends="one">
        <javac srcdir="src" destdir="${d}"
               includeantruntime="false"/>
    </target>

    <target name="all" depends="two">
        <jar destfile="${n}.jar" basedir="${d}"/>
    </target>
</project>
```

Hãy đề xuất một ánh xạ tên giữ nguyên ý nghĩa:

| Tên cũ | Tên mới gợi ý |
| --- | --- |
| `one` | `prepare-build` |
| `two` | `compile-main` |
| `all` | `package-jar` hoặc wrapper `verify` khi phù hợp |
| `d` | `build.classes.dir` |
| `n` | `artifact.name` |

Sau đó cập nhật `default`, `depends` và các biểu thức `${...}` cùng lúc. Nếu CI đang gọi `ant all`, cần cập nhật caller hoặc giữ wrapper tương thích trong thời gian chuyển đổi.

### Bài 2: Phân biệt path ID và property

Tạo một path ID tên `classpath.compile` chứa các JAR ở `lib/`, rồi đưa vào `<javac>` bằng `refid`. Dùng `pathconvert` để tạo property riêng `diagnostic.compile-classpath` và in ở mức `verbose`. Quan sát sự khác nhau giữa:

- Path ID được truyền cho tác vụ cần đường dẫn.
- Property chứa chuỗi để in log.
- Tên property chỉ tới một thư mục cụ thể như `deps.dir`.

### Bài 3: Tái sử dụng macro log

Dùng `macrodef name="log-step"` ở mục 7 và thêm target `generate-docs`. Gọi macro hai lần để báo bắt đầu/kết thúc, luôn truyền `step="generate-docs"`. Sau đó thử đổi tên attribute `message` thành `text` trong khai báo macro mà không đổi lời gọi; đọc thông báo lỗi và rút ra vì sao tên tham số macro cũng là một hợp đồng với caller.

### Bài 4: Chuẩn hóa một build lớn

Với dự án có nhiều file Ant, lập danh sách:

```text
Target public:
  clean
  verify
  package-jar

Target hỗ trợ:
  prepare-build
  compile-main
  compile-tests
  run-tests

Property:
  src.main.dir
  src.test.dir
  build.classes.dir
  artifact.jar.file
  java.release

Path ID:
  classpath.compile
  classpath.test.compile
  classpath.runtime

Macro:
  log-step
  copy-resources
  validate-input
```

So sánh tên hiện có với danh sách này, đánh dấu các tên trùng nghĩa hoặc khó hiểu, rồi lập thứ tự đổi tên dựa trên phạm vi ảnh hưởng. Tên nào CI hoặc người dùng đang gọi nên được xem là giao diện công khai, cần xử lý tương thích trước.

## 13. Tổng kết

Quy ước đặt tên có tác dụng khi nó giúp người bảo trì hiểu build mà không cần mở từng dòng XML:

- **Target** biểu đạt một bước hoặc mốc thực thi: `compile-main`, `package-jar`, `verify`.
- **Property** biểu đạt một giá trị cấu hình, theo nhóm rõ nghĩa: `build.classes.dir`, `java.release`.
- **Path ID** biểu đạt tập đường dẫn dùng lại, có mục đích xác định: `classpath.compile`, `classpath.runtime`.
- **Macro** biểu đạt hành động lặp lại và tham số có nghĩa: `log-step`, `copy-resources`.

Đặc biệt khi bảo trì dự án đã có CI, hãy xem các tên target và property được gọi từ bên ngoài như một giao diện cần được giữ ổn định. Một bộ tên rõ ràng, nhất quán và gắn đúng hành vi sẽ làm sơ đồ dependency, log và các thay đổi của `build.xml` dễ đọc hơn, giảm rủi ro khi nhiều người cùng sửa hệ thống build.
