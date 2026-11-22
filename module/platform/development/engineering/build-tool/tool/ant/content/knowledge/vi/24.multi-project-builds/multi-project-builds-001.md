# Phân rã hệ thống thành dự án gốc và các dự án con

Khi một hệ thống Java có nhiều thành phần, một `build.xml` duy nhất có thể trở nên khó đọc và khó thay đổi. Các bước biên dịch thư viện dùng chung, xây dựng dịch vụ, đóng gói ứng dụng và chạy kiểm thử có thể có dependency, thư mục đầu ra và vòng đời khác nhau. Apache Ant cho phép chia hệ thống thành nhiều build project độc lập, mỗi dự án con có `build.xml` riêng, còn dự án gốc điều phối thứ tự thực hiện.

Trong cách tổ chức này, dự án gốc thường đóng vai trò aggregator: nó gọi các dự án con theo thứ tự cần thiết và cung cấp những target cấp cao như `build`, `test`, `package` hoặc `clean`. Mỗi dự án con chịu trách nhiệm xây dựng một module hoặc một thành phần cụ thể. Cách phân rã này giúp giới hạn phạm vi thay đổi, cho phép chạy riêng từng module và làm rõ quan hệ phụ thuộc giữa các phần của hệ thống.

## 1. Dự án gốc và dự án con trong Ant

Ant không có một loại project đặc biệt tên là “root project” hay “subproject”. Mỗi tệp build là một Ant project được khai báo bằng phần tử `<project>`. Khái niệm dự án gốc và dự án con là cách tổ chức kiến trúc build:

- **Dự án gốc (root/aggregator)** chứa build file ở cấp workspace, biết danh sách module và điều phối các bước trên toàn hệ thống.
- **Dự án con (child project/module)** có build file riêng, quản lý source, dependency, task và output của chính module đó.
- **Quan hệ phụ thuộc giữa module** mô tả module nào cần artifact do module khác tạo ra.
- **Điều phối build** bảo đảm các module được gọi theo thứ tự phù hợp với đồ thị phụ thuộc.

Ví dụ hệ thống có ba module:

```text
workspace/
├── build.xml                    # Dự án gốc: điều phối toàn hệ thống
├── build-common.properties      # Cấu hình dùng chung
├── build-common.xml             # Target dùng chung (nếu cần)
├── modules/
│   ├── core/
│   │   ├── build.xml             # Dự án con core
│   │   └── src/main/java/
│   ├── service/
│   │   ├── build.xml             # Dự án con service
│   │   └── src/main/java/
│   └── cli/
│       ├── build.xml             # Dự án con cli
│       └── src/main/java/
└── test-data/
```

Trong ví dụ, `service` sử dụng `core`, còn `cli` sử dụng `service`. Dự án gốc chịu trách nhiệm gọi `core` trước `service`, rồi mới đến `cli`.

Một dự án con có thể được gọi trực tiếp từ thư mục của nó:

```bash
cd modules/core
ant jar
```

Hoặc được gọi qua dự án gốc:

```bash
cd workspace
ant build
```

Hai cách gọi dùng cùng build file của module. Điều này cho phép lập trình viên làm việc riêng với module, trong khi CI có thể chạy toàn bộ hệ thống thông qua root build.

## 2. Xác định ranh giới module

Trước khi tạo nhiều `build.xml`, hãy xác định các thành phần có trách nhiệm và vòng đời tương đối độc lập. Một module nên có mục tiêu rõ ràng, chẳng hạn:

| Module | Trách nhiệm | Artifact đầu ra ví dụ |
|---|---|---|
| `core` | Kiểu dữ liệu, logic nghiệp vụ và API dùng chung | `core.jar` |
| `service` | Dịch vụ ứng dụng, tích hợp với core | `service.jar` |
| `cli` | Giao diện dòng lệnh và lớp khởi chạy | `cli.jar` |
| `web` | Ứng dụng web và tài nguyên web | WAR hoặc thư mục triển khai |
| `integration-tests` | Kiểm thử tích hợp nhiều module | Báo cáo test, không nhất thiết tạo JAR phát hành |

Không nên tách module chỉ vì một thư mục có nhiều tệp. Một ranh giới tốt thường có một hoặc nhiều đặc điểm:

- Có trách nhiệm nghiệp vụ hoặc kỹ thuật riêng.
- Có thể biên dịch, kiểm thử hoặc đóng gói độc lập.
- Có dependency đầu vào và artifact đầu ra xác định.
- Có thể được tái sử dụng bởi nhiều module khác.
- Có vòng đời hoặc điều kiện phát hành riêng.

Nếu hai nhóm source luôn được biên dịch, kiểm thử và phát hành cùng nhau, không có API hoặc artifact độc lập, việc tách chúng thành hai dự án con có thể làm tăng cấu hình mà không đem lại lợi ích tương ứng.

### 2.1. Phân biệt module với target

Target là đơn vị công việc bên trong một Ant project, còn module là một phần của hệ thống có build project riêng. Một module thường có nhiều target như `clean`, `compile`, `test` và `jar`.

| Thành phần | Phạm vi | Ví dụ |
|---|---|---|
| Target | Một build project | `modules/core/build.xml` có target `compile` |
| Module/dự án con | Một phần hệ thống với build file và output riêng | `core`, `service`, `cli` |
| Root project | Build project điều phối nhiều module | `workspace/build.xml` |
| Artifact | Kết quả được module tạo ra và module khác có thể sử dụng | `core.jar` |

Ant không tự biến target `compile` trong `core` thành dependency của target `compile` trong `service`. Dự án gốc phải gọi các build con theo thứ tự hoặc build con phải có cơ chế lấy artifact dependency rõ ràng.

## 3. Thiết kế cấu trúc thư mục

Một cấu trúc dễ quản lý là đặt mỗi module dưới một thư mục riêng và đặt `build.xml` ở gốc module:

```text
workspace/
├── build.xml
├── build-common.properties
├── modules/
│   ├── core/
│   │   ├── build.xml
│   │   ├── src/main/java/
│   │   ├── src/test/java/
│   │   └── build/                 # Output riêng của core
│   ├── service/
│   │   ├── build.xml
│   │   ├── src/main/java/
│   │   ├── src/test/java/
│   │   └── build/                 # Output riêng của service
│   └── cli/
│       ├── build.xml
│       ├── src/main/java/
│       └── build/                 # Output riêng của cli
└── dist/                          # Artifact tổng hợp nếu cần
```

Mỗi module có thư mục `build/` riêng để target `clean` của module không xóa nhầm output của module khác. Dự án gốc có thể có thư mục `dist/` riêng để tập hợp artifact cuối cùng.

### 3.1. Giữ output của module độc lập

Trong build file của `core`:

```xml
<project name="core" default="jar" basedir=".">
    <property name="build.dir" location="${basedir}/build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="dist.dir" location="${build.dir}/dist"/>

    <target name="clean">
        <delete dir="${build.dir}" quiet="true"/>
    </target>

    <target name="prepare">
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${dist.dir}"/>
    </target>
</project>
```

Vì `${basedir}` là thư mục của module khi chạy build file đó, các đường dẫn output được giới hạn trong `modules/core/build`. Khi chạy `clean` của `core`, Ant không xóa `modules/service/build` hoặc `modules/cli/build`.

Tránh đặt mọi module ghi vào cùng một thư mục `build/classes` ở cấp workspace. Cách đó dễ gây trùng tên lớp, ghi đè artifact và khiến việc dọn dẹp một module ảnh hưởng đến module khác.

### 3.2. Sử dụng `${basedir}` cho đường dẫn của module

`${basedir}` là thư mục gốc của Ant project hiện tại. Khi child build được gọi với `dir` là thư mục module, `${basedir}` trong child trỏ đến module đó.

Nên khai báo đường dẫn nội bộ dựa trên `${basedir}`:

```xml
<property name="src.main" location="${basedir}/src/main/java"/>
<property name="src.test" location="${basedir}/src/test/java"/>
<property name="build.dir" location="${basedir}/build"/>
```

Không giả định `${basedir}` luôn là thư mục workspace. Khi chạy target trực tiếp trong module, Ant dùng basedir của module; khi chạy qua `<ant>` hoặc `<subant>`, basedir của project con phụ thuộc vào thư mục/build file được gọi.

## 4. Tạo build file độc lập cho từng module

Một module nên cung cấp một giao diện target ổn định để người dùng và root project gọi. Các tên thường dùng:

| Target | Mục đích |
|---|---|
| `clean` | Xóa output do chính module tạo ra |
| `prepare` | Tạo thư mục và chuẩn bị đầu vào |
| `compile` | Biên dịch source chính |
| `test-compile` | Biên dịch source kiểm thử |
| `test` | Chạy kiểm thử của module |
| `jar` hoặc `package` | Tạo artifact của module |
| `all` | Điều phối các bước cần thiết trong phạm vi module |

Không bắt buộc mọi module phải có đủ các target này. Ví dụ module chỉ chứa tài nguyên có thể không cần `compile`; module kiểm thử tích hợp có thể chỉ có `test`.

Ví dụ build file tối giản cho module `core`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="core" default="jar" basedir=".">

    <property name="src.main" location="${basedir}/src/main/java"/>
    <property name="build.dir" location="${basedir}/build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="dist.dir" location="${build.dir}/dist"/>

    <target name="clean" description="Remove core build output">
        <delete dir="${build.dir}" quiet="true"/>
    </target>

    <target name="prepare">
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${dist.dir}"/>
    </target>

    <target name="compile" depends="prepare">
        <javac srcdir="${src.main}"
               destdir="${classes.dir}"
               includeantruntime="false"
               encoding="UTF-8"/>
    </target>

    <target name="jar" depends="compile">
        <jar destfile="${dist.dir}/core.jar"
             basedir="${classes.dir}"/>
    </target>

</project>
```

Module `core` có thể được xây dựng độc lập:

```bash
ant -f modules/core/build.xml jar
```

Lệnh này gọi build file của `core` từ workspace. Ant dùng thư mục chứa build file làm basedir mặc định nếu không có cấu hình khác; để tránh mơ hồ khi gọi từ script, có thể chuyển vào thư mục module rồi chạy `ant jar`.

## 5. Gọi một dự án con bằng task `<ant>`

Task `<ant>` chạy một Ant build khác từ target hiện tại. Nó phù hợp khi root project cần gọi một module cụ thể, truyền một số property và kiểm soát thứ tự thực hiện.

Cú pháp thường dùng:

```xml
<ant antfile="build.xml"
     dir="modules/core"
     target="jar"
     inheritAll="false"/>
```

Các thuộc tính chính:

| Thuộc tính | Ý nghĩa |
|---|---|
| `antfile` | Tệp build của dự án con; thường là `build.xml` |
| `dir` | Thư mục làm việc/basedir cho build con |
| `target` | Target cần chạy trong build con |
| `inheritAll` | Điều khiển việc kế thừa property thông thường từ project cha; mặc định là `true` |
| `inheritRefs` | Điều khiển việc kế thừa các reference; mặc định là `false` |
| `failonerror` | Quyết định build cha có thất bại khi build con lỗi hay không; nên giữ `true` cho quy trình phát hành |

Ví dụ target trong root build:

```xml
<project name="workspace" default="build" basedir=".">
    <property name="modules.dir" location="${basedir}/modules"/>

    <target name="build-core">
        <ant antfile="build.xml"
             dir="${modules.dir}/core"
             target="jar"
             inheritAll="false"
             failonerror="true"/>
    </target>
</project>
```

Khi chạy `ant build-core`, root project gọi target `jar` trong build file của module `core`. Thuộc tính `dir` giúp child build có basedir đúng với module, do đó các đường dẫn `${basedir}/src` và `${basedir}/build` trong child được giải quyết tương đối với thư mục `core`.

### 5.1. Truyền property tường minh

Nếu child cần một giá trị từ root, có thể truyền property bằng nested `<property>`:

```xml
<target name="build-core">
    <ant antfile="build.xml"
         dir="${modules.dir}/core"
         target="jar"
         inheritAll="false">
        <property name="release.version" value="${release.version}"/>
        <property name="build.profile" value="${build.profile}"/>
    </ant>
</target>
```

Trong ví dụ, root chỉ chuyển hai property mà module cần. Cách truyền tường minh giúp hợp đồng giữa hai build dễ hiểu và giảm phụ thuộc vào toàn bộ cấu hình của project cha.

Nếu child có thể chạy độc lập, nó cũng nên có giá trị mặc định phù hợp hoặc thông báo rõ property bắt buộc cần truyền. Không nên để child chỉ chạy được khi root vô tình truyền một property không được tài liệu hóa.

### 5.2. Hiểu `inheritAll` và `inheritRefs`

`inheritAll="true"` là mặc định của task `<ant>`: property thông thường của project cha được chuyển sang project con. `inheritAll="false"` giới hạn việc kế thừa property thông thường; user properties có quy tắc kế thừa riêng. Điều này hữu ích khi muốn child build độc lập và chỉ nhận các giá trị đã được chỉ định.

Reference như Ant `Path`, `FileSet` hoặc datatype được khai báo bằng `id` không giống property. Việc truyền reference được điều khiển riêng bằng `inheritRefs`. Mặc định reference không được kế thừa. Trong kiến trúc nhiều module, thường nên để mỗi child tự tạo path cần thiết từ artifact và dependency của nó thay vì phụ thuộc vào reference nội bộ của root.

Không nên dùng `inheritAll="false"` rồi kỳ vọng mọi property của root vẫn có sẵn trong child. Hãy truyền property cần thiết hoặc để child nạp cấu hình dùng chung bằng tệp properties.

## 6. Gọi nhiều dự án con bằng task `<subant>`

Khi cần chạy cùng một target trên nhiều module, task `<subant>` phù hợp hơn việc viết nhiều task `<ant>` giống nhau. `subant` duyệt một build path gồm các thư mục hoặc build file và gọi target được chỉ định cho từng dự án con.

Ví dụ chạy target `clean` cho mọi module có `build.xml` trực tiếp dưới `modules/`:

```xml
<target name="clean-modules">
    <subant target="clean"
            failonerror="true"
            inheritAll="false">
        <fileset dir="${modules.dir}">
            <include name="*/build.xml"/>
        </fileset>
    </subant>
</target>
```

Với cấu trúc thư mục:

```text
modules/
├── core/build.xml
├── service/build.xml
└── cli/build.xml
```

`subant` gọi target `clean` của cả ba build file. Mỗi child thực hiện thao tác dọn output riêng của mình.

### 6.1. Chọn danh sách module cụ thể

Không nhất thiết gọi tất cả thư mục con. Có thể liệt kê chính xác các build file:

```xml
<subant target="test" failonerror="true">
    <filelist dir="${basedir}"
              files="modules/core/build.xml,modules/service/build.xml"/>
</subant>
```

`files` trong `filelist` xác định danh sách build file cần chạy. Cách này hữu ích khi chỉ một nhóm module có target `test` hoặc khi muốn giới hạn phạm vi trong một target cụ thể.

### 6.2. Dùng `buildpath` hoặc `buildpathref`

Có thể khai báo build path bằng nested path:

```xml
<path id="module.buildpath">
    <pathelement location="${modules.dir}/core"/>
    <pathelement location="${modules.dir}/service"/>
    <pathelement location="${modules.dir}/cli"/>
</path>

<target name="clean-modules">
    <subant target="clean"
            buildpathref="module.buildpath"
            failonerror="true"/>
</target>
```

Khi các phần tử build path là thư mục, `subant` tìm build file theo tên mặc định `build.xml`, trừ khi được cấu hình khác. Khi dùng build file có tên khác nhau, hãy chỉ định danh sách file hoặc thuộc tính `antfile` phù hợp.

### 6.3. Khi nào dùng `<subant>`?

`<subant>` phù hợp với những target có thể chạy đồng nhất trên nhiều module, ví dụ `clean`, `test` hoặc `package` khi tất cả module đều có cùng quy ước target.

Không nên dùng một lần `subant target="build"` để xây dựng tất cả module nếu một số module phụ thuộc vào artifact của module khác và thứ tự chưa được đảm bảo. Trong trường hợp đó, root nên điều phối theo từng giai đoạn hoặc gọi từng child theo thứ tự dependency.

## 7. Mô hình hóa dependency giữa các dự án con

Giả sử hệ thống có quan hệ:

```text
core  →  service  →  cli
```

`service` cần JAR của `core`; `cli` cần JAR của `service`. Ant không tự phân tích quan hệ này giữa nhiều build file. Dự án gốc cần thể hiện thứ tự:

```xml
<target name="build-core">
    <ant antfile="build.xml" dir="${modules.dir}/core"
         target="jar" inheritAll="false"/>
</target>

<target name="build-service" depends="build-core">
    <ant antfile="build.xml" dir="${modules.dir}/service"
         target="jar" inheritAll="false"/>
</target>

<target name="build-cli" depends="build-service">
    <ant antfile="build.xml" dir="${modules.dir}/cli"
         target="jar" inheritAll="false"/>
</target>

<target name="build" depends="build-cli"/>
```

Khi chạy `ant build`, root hoàn thành `core` trước, tiếp đến `service`, cuối cùng là `cli`. Dependency giữa các target của root thể hiện thứ tự giữa các build con.

### 7.1. Child sử dụng artifact của module khác

Module `service` cần biết vị trí JAR mà `core` tạo ra. Có thể tính đường dẫn workspace từ vị trí module:

```xml
<project name="service" default="jar" basedir=".">
    <property name="workspace.dir" location="${basedir}/../.."/>
    <property name="core.jar"
              location="${workspace.dir}/modules/core/build/dist/core.jar"/>
    <property name="build.dir" location="${basedir}/build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>

    <path id="compile.classpath">
        <pathelement location="${core.jar}"/>
    </path>

    <target name="compile">
        <mkdir dir="${classes.dir}"/>
        <javac srcdir="${basedir}/src/main/java"
               destdir="${classes.dir}"
               includeantruntime="false">
            <classpath refid="compile.classpath"/>
        </javac>
    </target>
</project>
```

Ví dụ giả định `service` nằm trong `workspace/modules/service`, nên `${basedir}/../..` trỏ về workspace. Target `build-service` của root phải chạy sau `build-core`, để JAR đã tồn tại trước khi `service` compile.

Trong module lớn, nên đặt quy ước artifact ổn định, ví dụ `build/dist/<module>.jar`, hoặc tập hợp artifact vào một thư mục workspace dùng chung. Không để module phụ thuộc vào thư mục tạm nội bộ như `build/tmp` của module khác.

### 7.2. Kiểm tra artifact dependency trước khi dùng

Nếu module có thể được chạy độc lập, hãy kiểm tra artifact dependency tồn tại và hiển thị thông báo có ích:

```xml
<target name="check-core-artifact">
    <available file="${core.jar}" type="file"
               property="core.jar.exists"/>
    <fail unless="core.jar.exists"
          message="core.jar is missing. Build the core module before service."/>
</target>

<target name="compile" depends="check-core-artifact">
    <!-- javac sử dụng compile.classpath -->
</target>
```

Kiểm tra này giúp người chạy hiểu vì sao module không thể compile độc lập. Với build root, dependency ordering phải bảo đảm artifact được tạo trước; với build module trực tiếp, tài liệu cần hướng dẫn chạy module phụ thuộc trước hoặc tải artifact từ repository.

## 8. Chia sẻ cấu hình giữa root và child

Các module thường cần cùng phiên bản Java, encoding, thư mục phân phối hoặc quy ước tên artifact. Có thể chia sẻ cấu hình theo hai cách chính: truyền property từ root hoặc để mỗi child nạp một tệp cấu hình chung.

### 8.1. Dùng tệp properties chung

Tệp `build-common.properties` ở workspace:

```properties
java.source=17
java.target=17
build.encoding=UTF-8
release.version=2.4.0
```

Trong build file của module `core` hoặc `service`:

```xml
<property name="workspace.dir" location="${basedir}/../.."/>
<property file="${workspace.dir}/build-common.properties"/>
```

Mỗi module tự nạp cùng một tệp cấu hình nên vẫn có thể chạy độc lập, kể cả khi root gọi child với `inheritAll="false"`.

Sau đó dùng property trong task:

```xml
<javac srcdir="${basedir}/src/main/java"
       destdir="${basedir}/build/classes"
       source="${java.source}"
       target="${java.target}"
       encoding="${build.encoding}"
       includeantruntime="false"/>
```

### 8.2. Truyền property từ root

Nếu root quản lý một giá trị chỉ dùng cho lần build hiện tại, có thể truyền qua nested `<property>` của task `<ant>` hoặc `<subant>`. Ví dụ:

```xml
<target name="build-core">
    <ant antfile="build.xml"
         dir="${modules.dir}/core"
         target="jar"
         inheritAll="false">
        <property name="release.version" value="${release.version}"/>
    </ant>
</target>
```

Cách truyền này phù hợp với build number, profile hoặc phiên bản release do CI cung cấp. Nếu property là cấu hình chung lâu dài cho mọi module, tệp properties dùng chung có thể dễ quản lý hơn.

### 8.3. Dùng `<import>` để chia sẻ target

Nếu nhiều build file cần dùng chung một số target hoặc macro, có thể đặt chúng trong tệp XML dùng chung và import vào child project:

```xml
<property name="workspace.dir" location="${basedir}/../.."/>
<import file="${workspace.dir}/build-common.xml"/>
```

`<import>` đưa target và định nghĩa từ tệp được import vào cùng Ant project hiện tại. Nó không khởi chạy một dự án con độc lập như `<ant>` hoặc `<subant>`. Vì vậy:

- Dùng `import` để tái sử dụng target, macrodef hoặc cấu hình trong cùng project.
- Dùng `<ant>` để gọi một build file khác một cách tường minh.
- Dùng `<subant>` để gọi cùng target trên một nhóm build file.

Không nên đưa toàn bộ logic của mọi module vào một tệp common rồi import khắp nơi. Tệp dùng chung nên chứa quy ước thực sự phổ biến; logic đặc thù của module vẫn nên nằm trong build file của module đó.

## 9. Điều phối các target toàn hệ thống

Root project thường cung cấp các target cấp cao như `clean`, `build`, `test`, `package` và `release`. Những target này gọi các module hoặc nhóm module theo thứ tự.

Ví dụ root build file:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="workspace" default="build" basedir=".">

    <property name="modules.dir" location="${basedir}/modules"/>
    <property name="dist.dir" location="${basedir}/dist"/>
    <property name="release.version" value="2.4.0"/>

    <target name="clean">
        <subant target="clean" failonerror="true" inheritAll="false">
            <fileset dir="${modules.dir}">
                <include name="*/build.xml"/>
            </fileset>
        </subant>
        <delete dir="${dist.dir}" quiet="true"/>
    </target>

    <target name="build-core">
        <ant antfile="build.xml" dir="${modules.dir}/core"
             target="jar" inheritAll="false" failonerror="true"/>
    </target>

    <target name="build-service" depends="build-core">
        <ant antfile="build.xml" dir="${modules.dir}/service"
             target="jar" inheritAll="false" failonerror="true">
            <property name="release.version" value="${release.version}"/>
        </ant>
    </target>

    <target name="build-cli" depends="build-service">
        <ant antfile="build.xml" dir="${modules.dir}/cli"
             target="jar" inheritAll="false" failonerror="true"/>
    </target>

    <target name="build" depends="build-cli"/>

    <target name="test-all" depends="build">
        <subant target="test" failonerror="true" inheritAll="false">
            <fileset dir="${modules.dir}">
                <include name="*/build.xml"/>
            </fileset>
        </subant>
    </target>

</project>
```

Đây là ví dụ minh họa. Nếu một module không có target `test`, không nên đưa build file đó vào fileset của `test-all`; hãy chọn danh sách module có kiểm thử hoặc thống nhất target `test` cho mọi module.

### 9.1. Build tất cả module độc lập

Nếu các module không phụ thuộc vào artifact của nhau, có thể dùng `subant` để gọi cùng target trên toàn bộ build file:

```xml
<target name="compile-independent-modules">
    <subant target="compile" failonerror="true">
        <fileset dir="${modules.dir}">
            <include name="*/build.xml"/>
        </fileset>
    </subant>
</target>
```

Đây là cách ngắn gọn cho những module độc lập hoặc chỉ sử dụng thư viện ngoài. Nếu có quan hệ dependency nội bộ, hãy chia thành các giai đoạn theo thứ tự hoặc dùng target root riêng cho từng nhóm.

### 9.2. Không để dependency order phụ thuộc vào thứ tự duyệt thư mục

Thứ tự các file được tìm thấy bởi một fileset không nên được dùng làm cơ chế mô hình hóa dependency. Nếu `service` cần `core`, hãy thể hiện rõ target `build-service` phụ thuộc `build-core` ở root. Không dựa vào việc thư mục `core` có tên đứng trước `service` theo thứ tự alphabet.

Khi thêm module mới, hãy cập nhật đồ thị dependency và target điều phối tương ứng. Nếu hai module độc lập, có thể đưa chúng vào cùng một giai đoạn; nếu một module tiêu thụ artifact của module khác, phải có thứ tự rõ ràng.

## 10. Quy ước target giữa các module

Root project dễ điều phối hơn khi các module có một hợp đồng target nhất quán. Ví dụ:

| Quy ước | Ý nghĩa trong mọi module |
|---|---|
| `clean` | Xóa output do module tạo |
| `compile` | Biên dịch source chính |
| `test` | Chạy test của module |
| `jar` | Tạo JAR nếu module là thư viện hoặc ứng dụng JAR |
| `package` | Tạo artifact phân phối của module |

Không ép module không có ý nghĩa đóng gói phải tạo một JAR rỗng chỉ để tuân theo quy ước. Có thể cung cấp target `package` phù hợp với loại artifact thực tế, hoặc giới hạn fileset ở root cho những module có target đó.

### 10.1. Target mặc định của child

Mỗi child project nên đặt target mặc định hợp lý:

```xml
<project name="core" default="jar" basedir=".">
```

Khi người dùng vào module và chạy `ant` không có target, Ant thực hiện `jar`. Tuy nhiên, root nên gọi target tường minh bằng thuộc tính `target` của `<ant>` để tránh phụ thuộc vào default target của child.

### 10.2. Target điều phối trong child

Child có thể có target `all` hoặc `build` để điều phối các bước trong phạm vi module:

```xml
<target name="build" depends="test,jar"/>
```

Chỉ dùng quan hệ này nếu `test` thực sự cần hoàn thành trước khi tạo artifact. Nếu quy trình test và package cần được điều khiển riêng ở root, hãy để root gọi các target tương ứng.

## 11. Quản lý dependency giữa module và repository

Trong một workspace, module tiêu thụ có thể tham chiếu artifact do module khác tạo ra bằng đường dẫn tương đối ổn định. Với hệ thống lớn hoặc nhiều repository, có thể publish artifact vào repository Maven/Ivy rồi resolve bằng tọa độ và phiên bản.

| Cách cung cấp dependency | Phù hợp khi | Lưu ý |
|---|---|---|
| Đường dẫn đến JAR trong workspace | Các module được build trong cùng checkout | Root phải bảo đảm module cung cấp được build trước |
| Thư mục artifact chung | Nhiều module cần dùng output đã được tập hợp | Cần quy ước tên và dọn output rõ ràng |
| Ivy/Maven repository | Module có thể được build và phát hành độc lập | Cần quản lý version, resolver và dependency metadata |
| JAR được tải từ bên ngoài | Dependency không thuộc workspace | Cần cố định version và checksum theo chính sách dự án |

Không nên để module `service` đọc trực tiếp source code bên trong `core/src/main/java`. Hãy tiêu thụ API qua artifact hoặc cơ chế module đã được định nghĩa. Điều đó giữ ranh giới và cho phép `core` thay đổi nội bộ mà không làm module khác phụ thuộc vào cấu trúc source.

## 12. Xử lý lỗi và trạng thái trong build nhiều dự án

Khi child build thất bại, root thường cần dừng ngay để tránh tiếp tục đóng gói một hệ thống chỉ được build một phần. Hãy giữ `failonerror="true"` cho các bước bắt buộc:

```xml
<ant antfile="build.xml"
     dir="${modules.dir}/core"
     target="jar"
     failonerror="true"/>
```

Tương tự với `<subant>`, đặt `failonerror="true"` khi một module lỗi phải làm toàn bộ target thất bại. Nếu muốn thu thập kết quả từ nhiều module dù một module lỗi, cần thiết kế cơ chế báo lỗi và tổng hợp riêng, không nên âm thầm bỏ qua lỗi.

### 12.1. Phân biệt lỗi của module với lỗi điều phối

Khi root build thất bại, xác định build file con nào đang chạy và target nào thất bại. Có thể đặt `<echo>` trước mỗi lời gọi hoặc dùng log output riêng cho từng module nếu cần lưu trữ.

Ví dụ:

```xml
<target name="build-service" depends="build-core">
    <echo message="Building module: service"/>
    <ant antfile="build.xml"
         dir="${modules.dir}/service"
         target="jar"
         failonerror="true"/>
</target>
```

Khi log có tên module và target, việc xác định phạm vi lỗi nhanh hơn. Không nên chỉ in một thông báo chung như `Build failed` mà không ghi rõ module đang được gọi.

### 12.2. Không dùng chung output directory cho nhiều module

Nếu mọi child ghi vào cùng một thư mục, lỗi của module này có thể bị che bởi artifact của module khác. Hãy đặt output dưới `${basedir}/build` của từng child, hoặc tạo thư mục riêng theo tên module trong vùng output chung.

Target root `clean` có thể gọi `clean` cho từng module bằng `subant`, sau đó xóa thư mục tổng hợp riêng của root. Mỗi module chỉ xóa vùng mà nó sở hữu.

## 13. Chạy độc lập và chạy từ root

Một module tốt nên hỗ trợ cả hai cách chạy:

**Chạy trực tiếp trong module:**

```bash
cd modules/core
ant clean jar
```

**Chạy từ workspace:**

```bash
ant -f build.xml build-core
```

Khi chạy độc lập, child cần biết cách lấy cấu hình dùng chung và dependency của nó. Nếu module phụ thuộc vào artifact của `core`, người chạy cần build `core` trước hoặc cấu hình module lấy artifact từ repository.

Khi chạy từ root, root chịu trách nhiệm điều phối dependency nội bộ. Không nên làm cho child chỉ chạy được trong một trạng thái đặc biệt của root mà không có thông báo rõ ràng.

### 13.1. Kiểm tra target của module

Vào thư mục module và chạy:

```bash
ant -p
```

Lệnh liệt kê các target có mô tả. Có thể dùng `ant -diagnostics` để xem thông tin môi trường Ant khi module phụ thuộc vào công cụ hoặc cấu hình ngoài.

Ở cấp workspace, kiểm tra các target điều phối:

```bash
ant -p
```

Người dùng cần nhìn thấy các thao tác cấp cao như `build`, `test-all`, `clean` hoặc `release` mà không phải nhớ tên mọi target nội bộ của từng module.

## 14. Ví dụ hoàn chỉnh với ba dự án con

Giả sử hệ thống có ba module theo dependency:

```text
core → service → cli
```

### 14.1. Build file của `core`

`modules/core/build.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="core" default="jar" basedir=".">
    <property name="build.dir" location="${basedir}/build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="dist.dir" location="${build.dir}/dist"/>

    <target name="clean">
        <delete dir="${build.dir}" quiet="true"/>
    </target>

    <target name="compile">
        <mkdir dir="${classes.dir}"/>
        <javac srcdir="${basedir}/src/main/java"
               destdir="${classes.dir}"
               includeantruntime="false"
               encoding="UTF-8"/>
    </target>

    <target name="jar" depends="compile">
        <mkdir dir="${dist.dir}"/>
        <jar destfile="${dist.dir}/core.jar"
             basedir="${classes.dir}"/>
    </target>
</project>
```

### 14.2. Build file của `service`

`modules/service/build.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="service" default="jar" basedir=".">
    <property name="workspace.dir" location="${basedir}/../.."/>
    <property name="core.jar"
              location="${workspace.dir}/modules/core/build/dist/core.jar"/>
    <property name="build.dir" location="${basedir}/build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="dist.dir" location="${build.dir}/dist"/>

    <path id="compile.classpath">
        <pathelement location="${core.jar}"/>
    </path>

    <target name="clean">
        <delete dir="${build.dir}" quiet="true"/>
    </target>

    <target name="check-core">
        <available file="${core.jar}" type="file"
                   property="core.jar.exists"/>
        <fail unless="core.jar.exists"
              message="Build core before compiling service."/>
    </target>

    <target name="compile" depends="check-core">
        <mkdir dir="${classes.dir}"/>
        <javac srcdir="${basedir}/src/main/java"
               destdir="${classes.dir}"
               includeantruntime="false"
               encoding="UTF-8">
            <classpath refid="compile.classpath"/>
        </javac>
    </target>

    <target name="jar" depends="compile">
        <mkdir dir="${dist.dir}"/>
        <jar destfile="${dist.dir}/service.jar"
             basedir="${classes.dir}"/>
    </target>
</project>
```

### 14.3. Build file của `cli`

`modules/cli/build.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="cli" default="jar" basedir=".">
    <property name="workspace.dir" location="${basedir}/../.."/>
    <property name="service.jar"
              location="${workspace.dir}/modules/service/build/dist/service.jar"/>
    <property name="build.dir" location="${basedir}/build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="dist.dir" location="${build.dir}/dist"/>

    <path id="compile.classpath">
        <pathelement location="${service.jar}"/>
    </path>

    <target name="clean">
        <delete dir="${build.dir}" quiet="true"/>
    </target>

    <target name="check-service">
        <available file="${service.jar}" type="file"
                   property="service.jar.exists"/>
        <fail unless="service.jar.exists"
              message="Build service before compiling cli."/>
    </target>

    <target name="compile" depends="check-service">
        <mkdir dir="${classes.dir}"/>
        <javac srcdir="${basedir}/src/main/java"
               destdir="${classes.dir}"
               includeantruntime="false"
               encoding="UTF-8">
            <classpath refid="compile.classpath"/>
        </javac>
    </target>

    <target name="jar" depends="compile">
        <mkdir dir="${dist.dir}"/>
        <jar destfile="${dist.dir}/cli.jar"
             basedir="${classes.dir}">
            <manifest>
                <attribute name="Main-Class" value="com.example.cli.Main"/>
            </manifest>
        </jar>
    </target>
</project>
```

Ví dụ `cli` chỉ minh họa compile classpath và tạo executable JAR. Nếu ứng dụng cần `core.jar` trực tiếp ở runtime, cần thêm nó vào runtime distribution hoặc manifest `Class-Path` theo cấu trúc phát hành thực tế.

### 14.4. Root build file điều phối

`workspace/build.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="workspace" default="build" basedir=".">
    <property name="modules.dir" location="${basedir}/modules"/>
    <property name="dist.dir" location="${basedir}/dist"/>

    <target name="clean">
        <subant target="clean" failonerror="true" inheritAll="false">
            <fileset dir="${modules.dir}">
                <include name="*/build.xml"/>
            </fileset>
        </subant>
        <delete dir="${dist.dir}" quiet="true"/>
    </target>

    <target name="build-core">
        <echo message="Building module core"/>
        <ant antfile="build.xml" dir="${modules.dir}/core"
             target="jar" inheritAll="false" failonerror="true"/>
    </target>

    <target name="build-service" depends="build-core">
        <echo message="Building module service"/>
        <ant antfile="build.xml" dir="${modules.dir}/service"
             target="jar" inheritAll="false" failonerror="true"/>
    </target>

    <target name="build-cli" depends="build-service">
        <echo message="Building module cli"/>
        <ant antfile="build.xml" dir="${modules.dir}/cli"
             target="jar" inheritAll="false" failonerror="true"/>
    </target>

    <target name="build" depends="build-cli"/>

    <target name="test-all" depends="build">
        <subant target="test" failonerror="true" inheritAll="false">
            <filelist dir="${modules.dir}"
                      files="core/build.xml,service/build.xml,cli/build.xml"/>
        </subant>
    </target>

</project>
```

Root gọi từng module theo thứ tự dependency. `build-service` phụ thuộc `build-core`; `build-cli` phụ thuộc `build-service`. Target `clean` có thể dùng `subant` vì thao tác clean của các module độc lập về thư mục output. Target `test-all` chỉ hợp lệ nếu cả ba child đều cung cấp target `test`; nếu một module không có test, hãy bỏ nó khỏi danh sách hoặc cung cấp target test phù hợp.

Chạy toàn bộ build từ workspace:

```bash
ant build
```

Chạy riêng một module:

```bash
ant -f modules/core/build.xml jar
```

Hoặc chạy clean toàn hệ thống:

```bash
ant clean
```

## 15. Các lựa chọn tổ chức và đánh đổi

| Cách tổ chức | Ưu điểm | Điều cần quản lý |
|---|---|---|
| Một `build.xml` lớn | Bắt đầu đơn giản, ít cơ chế điều phối | Dễ phình to, target và property có thể gắn chặt giữa các phần |
| Root + child build files | Mỗi module có build và output riêng, chạy độc lập được | Phải định nghĩa hợp đồng target và dependency giữa module |
| Root + `<subant>` cho mọi module | Gọi cùng target trên nhiều build file gọn | Không tự mô hình hóa thứ tự dependency phức tạp |
| Root + `<ant>` cho từng module | Kiểm soát chính xác target, thứ tự và property truyền vào | Root có nhiều target điều phối hơn |
| Child dùng artifact repository | Module có thể build độc lập và version hóa dependency | Cần quản lý publish, resolve, repository và version |
| Dùng `<import>` cho cấu hình chung | Tái sử dụng target/macro mà không tạo tiến trình build mới | Các định nghĩa được đưa vào cùng project, cần tránh xung đột tên target/property |

Không có một cấu trúc duy nhất phù hợp cho mọi hệ thống. Với workspace nhỏ, root có thể gọi trực tiếp từng child bằng `<ant>`. Với nhiều module có cùng target, `<subant>` giảm lặp. Với hệ thống cần phát hành module độc lập, repository artifact và version rõ ràng có thể phù hợp hơn việc tham chiếu đường dẫn build cục bộ.

## 16. Lỗi thường gặp khi phân rã nhiều dự án

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Child không tìm thấy source hoặc output | Dùng đường dẫn tương đối dựa trên thư mục gọi thay vì basedir của child | Dùng `${basedir}` và truyền `dir` chính xác trong `<ant>` |
| Child không nhận property của root | Đặt `inheritAll="false"` nhưng không truyền property cần thiết | Truyền nested `<property>` hoặc để child nạp tệp properties chung |
| Reference như Path không có trong child | `inheritRefs` mặc định không kế thừa reference | Khai báo path riêng trong child hoặc truyền reference có chủ đích |
| Module phụ thuộc được build quá muộn | Dựa vào thứ tự alphabet/fileset thay vì dependency graph | Tạo target root có `depends` theo thứ tự module |
| `subant` báo không tìm thấy target | Một child không cung cấp target được gọi | Chuẩn hóa target contract hoặc giới hạn fileset/filelist |
| Một module clean làm mất output module khác | Các module dùng chung output directory | Đặt output riêng dưới `${basedir}/build` của mỗi child |
| Module chạy được qua root nhưng không chạy riêng | Child phụ thuộc property hoặc artifact chỉ có trong trạng thái root | Cung cấp default/configuration rõ ràng và kiểm tra dependency trước khi compile |
| Build tiếp tục dù child lỗi | Cấu hình `failonerror="false"` hoặc bỏ qua lỗi | Dùng `failonerror="true"` cho bước bắt buộc |
| Root build tạo artifact cũ | Dependency target không được gọi hoặc child output không được cập nhật | Kiểm tra target child, dependency ordering và đường dẫn artifact |
| Tệp common gây xung đột target | Import nhiều định nghĩa cùng tên hoặc logic module bị đưa vào common | Giới hạn tệp dùng chung ở quy ước thực sự phổ biến và dùng tên target có namespace khi cần |
| Test chạy trên module không có test target | `subant` quét mọi build file nhưng target không đồng nhất | Dùng danh sách module test cụ thể hoặc chuẩn hóa target `test` |

## 17. Nguyên tắc thiết kế build nhiều dự án

- Mỗi child sở hữu source, target và output của chính nó.
- Root điều phối module, không nên chứa chi tiết biên dịch nội bộ của mọi module.
- Dùng tên target nhất quán để root gọi child dễ dàng.
- Thể hiện dependency giữa module bằng target root hoặc dependency artifact rõ ràng.
- Không dựa vào thứ tự duyệt thư mục để quyết định thứ tự build.
- Dùng `${basedir}` cho đường dẫn nội bộ của từng project.
- Chỉ truyền property và reference mà child thực sự cần.
- Giữ child có thể chạy độc lập khi điều đó là mục tiêu của module.
- Tách output directory để clean và build không ảnh hưởng lẫn nhau.
- Dùng `failonerror="true"` cho các bước bắt buộc trong quy trình phát hành.
- Chỉ dùng `<subant>` cho nhóm build file có target chung và có thể chạy theo cách đó.
- Dùng `<import>` để chia sẻ target trong cùng project, không nhầm với việc gọi build con.
- Quản lý artifact dependency qua đường dẫn ổn định hoặc repository có version.

## 18. Checklist phân rã hệ thống

- [ ] Đã xác định module theo trách nhiệm và ranh giới có thể build/kiểm thử riêng.
- [ ] Root build file có các target cấp cao để điều phối toàn hệ thống.
- [ ] Mỗi child có `build.xml` riêng và target contract phù hợp.
- [ ] Mỗi child dùng `${basedir}` cho source, build và dist directory của mình.
- [ ] Output của các module không ghi đè lẫn nhau.
- [ ] Dependency giữa module được mô tả rõ bằng artifact và thứ tự build.
- [ ] Root gọi module theo dependency graph, không dựa vào thứ tự fileset.
- [ ] Đã chọn `<ant>` cho lời gọi cụ thể hoặc `<subant>` cho nhóm module phù hợp.
- [ ] Đã quyết định cách truyền property và reference.
- [ ] Cấu hình chung được chia sẻ qua properties hoặc target import có kiểm soát.
- [ ] Child có thể chạy độc lập hoặc thông báo rõ dependency cần chuẩn bị.
- [ ] Lỗi child được truyền lên root cho các bước bắt buộc.
- [ ] Target `clean` chỉ xóa output thuộc sở hữu của module tương ứng.
- [ ] Các target root như `build`, `test-all` và `clean` được kiểm tra từ workspace.

Phân rã hệ thống thành dự án gốc và các dự án con giúp build Ant phản ánh cấu trúc thực tế của phần mềm. Root project quản lý quy trình tổng thể, còn từng child project giữ quyền sở hữu đối với source, dependency và artifact của module. Khi ranh giới module rõ ràng, target contract nhất quán và dependency được điều phối theo đúng thứ tự, hệ thống có thể phát triển thêm module mà không biến một `build.xml` duy nhất thành điểm phụ thuộc của toàn bộ dự án.
