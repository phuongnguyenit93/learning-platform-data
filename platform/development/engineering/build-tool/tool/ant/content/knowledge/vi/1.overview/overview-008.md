# Lộ trình học Ant từ build đơn giản đến hệ thống nhiều dự án

Apache Ant là công cụ tự động hóa quá trình build, thường được dùng trong các dự án Java. Ant đọc file XML, thực thi các task như tạo thư mục, biên dịch mã nguồn, sao chép tài nguyên, chạy kiểm thử và đóng gói JAR. Điểm mạnh của Ant là mọi bước đều được mô tả rõ ràng và có thể tùy chỉnh theo nhu cầu của dự án.

Lộ trình dưới đây đi từ một file `build.xml` nhỏ đến cách tổ chức nhiều dự án dùng chung quy tắc build. Mỗi chặng bổ sung một nhóm khái niệm mới trên cùng một ví dụ, để người học hiểu được vì sao cấu hình cần thay đổi khi dự án lớn dần.

## 1. Hiểu Ant trước khi viết build script

Ant tổ chức công việc quanh ba thành phần chính:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| `project` | Đại diện cho một build script và xác định target mặc định, thư mục gốc | `<project name="sample" default="package">` |
| `target` | Một nhóm công việc có tên; có thể phụ thuộc vào target khác | `<target name="compile" depends="init">` |
| `task` | Một hành động cụ thể được thực hiện bên trong target | `<javac>`, `<copy>`, `<jar>`, `<delete>` |

Một build script thường là một đồ thị target. Khi gọi một target, Ant thực hiện các target mà nó phụ thuộc trước, sau đó mới chạy các task của target được gọi. Thuộc tính `depends` mô tả thứ tự phụ thuộc ở mức target.

```xml
<project name="sample" default="package" basedir=".">
    <target name="init">
        <mkdir dir="build"/>
    </target>

    <target name="compile" depends="init">
        <echo message="Compile source code here"/>
    </target>

    <target name="package" depends="compile">
        <echo message="Package the application here"/>
    </target>
</project>
```

Khi chạy `ant package`, thứ tự là `init` → `compile` → `package`. Nếu chạy `ant` mà không ghi tên target, Ant gọi target được khai báo trong thuộc tính `default` của `project`.

Ant không tự áp đặt một vòng đời build cố định cho mọi dự án. Người viết build script quyết định target nào tồn tại, chúng phụ thuộc nhau ra sao và task nào được chạy. Ant cũng không tự tải thư viện Maven từ repository; phần quản lý dependency cần được xử lý bằng classpath, thư viện được chuẩn bị sẵn hoặc công cụ tích hợp như Apache Ivy.

## 2. Chặng 0 — Chuẩn bị môi trường và công cụ

Trước khi học task, hãy bảo đảm máy có JDK và Apache Ant. Ant cần Java runtime để chạy; task `javac` cần compiler tương ứng với JDK được cấu hình trên máy. Phiên bản JDK dùng để build nên thống nhất với phiên bản mà dự án yêu cầu.

Kiểm tra môi trường:

```bash
java -version
javac -version
ant -version
```

Nếu lệnh `ant` không được nhận diện, kiểm tra Ant đã được cài đặt và thư mục `bin` của Ant đã nằm trong `PATH` hay chưa. Trên CI, nên chọn một image hoặc môi trường build có phiên bản JDK và Ant được kiểm soát, thay vì phụ thuộc vào cấu hình ngẫu nhiên của máy chạy.

Ở chặng này, người học cần biết cách chạy lệnh trong terminal, đọc XML cơ bản và hiểu sự khác nhau giữa đường dẫn tương đối với `basedir` của build script.

## 3. Chặng 1 — Tạo build script đầu tiên

Bắt đầu bằng một dự án không cần Java source. Mục tiêu là hiểu cách Ant đọc `build.xml`, tìm target và thực hiện task.

Tạo file `build.xml`:

```xml
<project name="hello-ant" default="hello" basedir=".">
    <target name="hello" description="Print a greeting">
        <echo message="Hello from Apache Ant"/>
    </target>
</project>
```

Chạy các lệnh sau trong thư mục chứa file:

```bash
ant
ant hello
ant -p
```

- `ant` chạy target mặc định `hello`.
- `ant hello` gọi trực tiếp target có tên `hello`.
- `ant -p` hiển thị các target có thông tin trợ giúp; thuộc tính `description` giúp danh sách dễ đọc hơn.

Tiếp theo, thử các task cơ bản:

```xml
<target name="prepare">
    <mkdir dir="build/output"/>
    <echo file="build/output/message.txt" message="Created by Ant"/>
    <copy file="build/output/message.txt" tofile="build/message-copy.txt"/>
    <delete file="build/message-copy.txt"/>
</target>
```

Các task này giúp làm quen với thao tác file và thư mục. Hãy quan sát file nào được tạo, sao chép hoặc xóa sau mỗi lần chạy. Khi đã hiểu luồng thực thi, chuyển sang build một ứng dụng Java thực tế.

**Kết quả cần đạt:** tự tạo được `build.xml`, khai báo target mặc định, gọi target theo tên và kết hợp nhiều task trong một target.

## 4. Chặng 2 — Biên dịch và đóng gói một ứng dụng Java

Tạo cấu trúc dự án nhỏ:

```text
hello-app/
├── build.xml
├── lib/
├── src/
│   └── main/
│       ├── java/
│       │   └── com/example/App.java
│       └── resources/
│           └── app.properties
├── build/
└── dist/
```

`src/main/java` chứa mã nguồn Java, `src/main/resources` chứa tài nguyên cần đặt cùng class đã biên dịch, `lib` là nơi chứa các JAR bên ngoài nếu dự án dùng dependency theo cách thủ công. `build` là thư mục trung gian và `dist` chứa artifact được đóng gói.

Một `build.xml` tối thiểu có thể viết như sau:

```xml
<project name="hello-app" default="jar" basedir=".">
    <property name="app.name" value="hello-app"/>
    <property name="main.class" value="com.example.App"/>

    <property name="src.main" location="${basedir}/src/main/java"/>
    <property name="src.resources" location="${basedir}/src/main/resources"/>
    <property name="build.dir" location="${basedir}/build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="dist.dir" location="${basedir}/dist"/>

    <path id="compile.classpath">
        <fileset dir="${basedir}/lib">
            <include name="**/*.jar"/>
        </fileset>
    </path>

    <target name="clean" description="Remove generated files">
        <delete dir="${build.dir}"/>
        <delete dir="${dist.dir}"/>
    </target>

    <target name="init">
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${dist.dir}"/>
    </target>

    <target name="compile" depends="init" description="Compile application sources">
        <javac srcdir="${src.main}"
               destdir="${classes.dir}"
               encoding="UTF-8"
               includeantruntime="false">
            <classpath refid="compile.classpath"/>
        </javac>

        <copy todir="${classes.dir}">
            <fileset dir="${src.resources}"/>
        </copy>
    </target>

    <target name="jar" depends="compile" description="Create the application JAR">
        <jar destfile="${dist.dir}/${app.name}.jar"
             basedir="${classes.dir}"/>
    </target>

    <target name="run" depends="compile" description="Run the application">
        <java classname="${main.class}" fork="true" failonerror="true">
            <classpath>
                <pathelement location="${classes.dir}"/>
                <path refid="compile.classpath"/>
            </classpath>
        </java>
    </target>
</project>
```

Ví dụ giả định các thư mục `src/main/java`, `src/main/resources` và `lib` đã tồn tại. Nếu dự án chưa dùng thư viện ngoài, có thể bỏ phần `compile.classpath` và các tham chiếu đến nó.

Các target tạo thành một chuỗi rõ ràng:

```text
ant jar
  └── compile
        └── init
```

`init` tạo thư mục đầu ra. `compile` gọi task `javac`, sau đó sao chép resource vào cùng thư mục class. `jar` gom nội dung đã biên dịch thành một file JAR. `run` chạy class chính với classpath gồm class đã biên dịch và các thư viện cần thiết.

Một số điểm cần chú ý:

- `location` phù hợp khi khai báo thuộc tính là đường dẫn; Ant chuẩn hóa đường dẫn dựa trên vị trí build.
- `includeantruntime="false"` tránh đưa thư viện nội bộ của Ant vào classpath biên dịch ứng dụng một cách vô tình.
- `fork="true"` chạy ứng dụng trong một tiến trình Java riêng. `failonerror="true"` khiến build thất bại nếu ứng dụng thoát với mã lỗi.
- JAR được tạo ở ví dụ trên chứa class và resource. Muốn chạy bằng `java -jar`, cần cấu hình manifest có `Main-Class` và bảo đảm các dependency runtime cũng được cung cấp đúng cách.
- Phiên bản source/bytecode Java nên được cấu hình phù hợp với JDK mục tiêu của dự án; không nên dựa vào mặc định khác nhau giữa các máy.

**Kết quả cần đạt:** có thể chạy `ant clean`, `ant compile`, `ant jar` và `ant run`; hiểu thư mục nguồn, thư mục đầu ra và quan hệ giữa các target.

## 5. Chặng 3 — Hoàn thiện vòng đời build: resource, test và artifact

Khi đã biên dịch được một ứng dụng, hãy tách các bước thành target có trách nhiệm rõ ràng. Một vòng đời thường gặp là:

```text
clean → init → compile → compile-test → test → package
```

Không nhất thiết mọi dự án phải có đúng các tên target này. Điều quan trọng là một target chỉ làm một nhóm công việc dễ hiểu và các phụ thuộc được khai báo rõ.

### 5.1. Xử lý resource

Resource có thể là file cấu hình, template, ảnh hoặc dữ liệu tĩnh. Chúng thường không được biên dịch như Java source nhưng cần xuất hiện trên runtime classpath. Vì vậy, bước copy resource phải chạy sau khi thư mục đầu ra được tạo và trước khi đóng gói JAR.

Nếu dự án có resource theo môi trường, hãy xác định rõ file nào được đóng gói cho từng môi trường. Tránh để các file cấu hình của máy cá nhân vô tình đi vào artifact phát hành.

### 5.2. Biên dịch và chạy test

Tách thư mục test khỏi thư mục source chính:

```text
src/
├── main/java/
├── main/resources/
├── test/java/
└── test/resources/
```

Target `compile-test` biên dịch test source vào `build/test-classes`. Classpath của test cần có class chính, test class và các thư viện test. Target `test` gọi test runner và phải làm build thất bại khi có test fail. Báo cáo test nên được lưu trong `build/reports` để CI có thể thu thập.

Ant có task tích hợp cho một số phiên bản JUnit thông qua gói task tùy chọn; với JUnit 5, cần chọn runner tương thích, chẳng hạn JUnit Platform Console, rồi gọi runner bằng task `java`. Hãy coi runner và dependency test là một phần của cấu hình test classpath, không trộn chúng vào runtime classpath của artifact phát hành.

### 5.3. Đóng gói artifact

Target `package` chỉ nên chạy sau khi compile và test thành công theo chính sách của dự án. Tùy mục tiêu, artifact có thể là JAR, WAR, ZIP hoặc một thư mục phân phối. Dùng tên file có ý nghĩa và lưu đầu ra ở một vị trí ổn định để CI hoặc bước triển khai tiếp theo có thể tìm thấy.

### 5.4. Hiểu giới hạn của `depends`

`depends` mô tả thứ tự target cần chạy. Nó không phải một hệ thống theo dõi toàn bộ quan hệ phụ thuộc giữa từng file nguồn và từng file đầu ra. Một số task như `javac` có cơ chế kiểm tra source đã thay đổi để quyết định biên dịch lại; với các bước khác, có thể cần dùng `uptodate`, `available`, `condition` hoặc cấu trúc target phù hợp.

Đừng nhầm việc target được gọi với việc mọi file bên trong chắc chắn đã được cập nhật. Khi cần xác nhận tính đúng đắn từ đầu, chạy một build sạch bằng `ant clean test package`.

**Kết quả cần đạt:** build có thể biên dịch source và test riêng, chạy test có kiểm soát lỗi, xử lý resource và tạo artifact sau khi các bước cần thiết hoàn tất.

## 6. Chặng 4 — Quản lý classpath và thư viện bên ngoài

Một ứng dụng thực tế thường dùng thư viện ngoài. Ant cung cấp `path` và các resource collection như `fileset` để mô tả classpath.

Ví dụ classpath lấy tất cả JAR trong thư mục `lib`:

```xml
<path id="application.classpath">
    <fileset dir="lib">
        <include name="**/*.jar"/>
        <exclude name="*-sources.jar"/>
        <exclude name="*-javadoc.jar"/>
    </fileset>
</path>
```

Sau đó tái sử dụng path bằng reference:

```xml
<javac srcdir="src/main/java" destdir="build/classes">
    <classpath refid="application.classpath"/>
</javac>
```

`fileset` chọn tập file theo mẫu. `path` kết hợp nhiều phần tử đường dẫn. `id` tạo một reference để nhiều task cùng dùng một cấu hình classpath, tránh lặp lại danh sách JAR ở từng target.

### 6.1. Bắt đầu với thư viện được quản lý thủ công

Với ví dụ nhỏ hoặc dự án cũ, có thể đặt JAR vào `lib`. Cần thống nhất phiên bản thư viện giữa các máy và ghi nhận nguồn gốc dependency. Không nên để mỗi lập trình viên tự tải một phiên bản khác nhau rồi chép vào thư mục cục bộ.

Nhược điểm của cách này là người quản lý build phải tự xử lý phiên bản, dependency bắc cầu, cập nhật và tính nhất quán. Khi số thư viện tăng, nên chuyển sang công cụ quản lý dependency.

### 6.2. Tích hợp Apache Ivy

Apache Ivy là công cụ quản lý dependency có thể tích hợp với Ant. Ivy đọc mô tả dependency, tải artifact từ repository và tạo classpath cho các task Ant. Ivy là thành phần riêng cần được cài đặt và nạp vào Ant; nó không tự có sẵn chỉ vì dự án dùng Ant.

Ví dụ `ivy.xml` khai báo dependency:

```xml
<ivy-module version="2.0">
    <info organisation="com.example" module="catalog-app"/>

    <configurations>
        <conf name="compile"/>
        <conf name="test" extends="compile"/>
    </configurations>

    <dependencies>
        <dependency org="org.example" name="example-library"
                    rev="1.2.3" conf="compile->default"/>
    </dependencies>
</ivy-module>
```

Trong `build.xml`, khai báo namespace Ivy và tạo target resolve:

```xml
<project name="catalog-app" default="package" basedir="."
         xmlns:ivy="antlib:org.apache.ivy.ant">

    <target name="resolve">
        <ivy:resolve/>
        <ivy:cachepath pathid="dependency.classpath" conf="compile"/>
    </target>

    <target name="compile" depends="resolve">
        <javac srcdir="src/main/java" destdir="build/classes">
            <classpath refid="dependency.classpath"/>
        </javac>
    </target>
</project>
```

Để ví dụ chạy được, cần nạp JAR của Ivy vào Ant, cấu hình repository phù hợp và bảo đảm tọa độ dependency tồn tại. Trong dự án thật, nên quản lý riêng cấu hình repository và các dependency theo mục đích `compile`, `test` hoặc runtime. Ưu tiên phiên bản cố định để build có thể tái lập; tránh dùng revision động nếu không có chính sách kiểm soát.

**Kết quả cần đạt:** hiểu cách tạo classpath dùng chung, phân biệt dependency biên dịch với dependency test/runtime và biết khi nào nên chuyển từ `lib` thủ công sang Ivy.

## 7. Chặng 5 — Quản lý cấu hình và tái sử dụng build logic

Khi build script lớn hơn, các giá trị như tên ứng dụng, thư mục đầu ra, môi trường, phiên bản thư viện và đường dẫn công cụ nên được đưa thành property.

### 7.1. Khai báo và nạp property

```xml
<property name="environment" value="dev"/>
<property name="config.file" location="config/${environment}.properties"/>
<property file="${config.file}"/>
```

Có thể truyền giá trị khi chạy Ant:

```bash
ant -Denvironment=ci clean test package
```

Property của Ant có tính bất biến: khi một property đã được đặt, lần khai báo tiếp theo thường không thay đổi giá trị đó. Property truyền từ dòng lệnh là user property và có độ ưu tiên cao. Vì vậy, hãy đặt giá trị mặc định trước, sau đó nạp file cấu hình theo quy tắc nhất quán; đừng kỳ vọng có thể ghi đè một property tùy ý ở target chạy sau.

Không commit mật khẩu, token hoặc thông tin bí mật vào file properties trong repository. CI nên cấp secret qua cơ chế quản lý secret của môi trường chạy và chỉ truyền vào bước cần sử dụng.

### 7.2. Tách phần cấu hình dùng chung

Khi nhiều build script cần cùng cách đặt thư mục, classpath hoặc target tiện ích, có thể đưa phần dùng chung vào file riêng rồi nhập bằng `import`:

```xml
<project name="module-a" default="package" basedir=".">
    <import file="../../build-support/common.xml"/>

    <!-- Targets riêng của module-a -->
</project>
```

File được import có thể chứa property, macro và target dùng chung. Cần đặt tên target có chủ đích để tránh xung đột; `import` cho phép dự án nhập tùy biến target được import. Khi cần giữ namespace cho target từ project được đưa vào, có thể tìm hiểu thêm task `include`.

### 7.3. Dùng macro cho chuỗi task lặp lại

`macrodef` đóng gói một chuỗi task thành macro có tham số:

```xml
<macrodef name="ensure-directory">
    <attribute name="path"/>
    <sequential>
        <mkdir dir="@{path}"/>
    </sequential>
</macrodef>

<target name="init">
    <ensure-directory path="build/classes"/>
    <ensure-directory path="build/reports"/>
</target>
```

Macro hữu ích khi nhiều module lặp lại cùng một thao tác có cấu trúc ổn định. Không nên tạo macro chỉ để che đi vài dòng task đơn giản; tên macro và tham số phải làm rõ hành động mà nó thực hiện.

### 7.4. Giữ target có trách nhiệm rõ ràng

Nên dùng `depends` để mô tả thứ tự trong vòng đời build. `antcall` có thể gọi một target khác trong cùng project, nhưng lạm dụng nó dễ làm luồng thực thi khó lần theo và tạo cảm giác target bị chạy lại ngoài dự kiến. Khi một bước là điều kiện bắt buộc của bước khác, quan hệ `depends` thường dễ đọc hơn.

**Kết quả cần đạt:** có thể cấu hình build bằng property, chọn môi trường qua dòng lệnh, tách phần dùng chung và tái sử dụng logic mà không nhân bản toàn bộ build script.

## 8. Chặng 6 — Tổ chức build cho nhiều dự án

Khi một repository có nhiều ứng dụng hoặc module, mỗi module nên có trách nhiệm build riêng. Một build ở thư mục gốc điều phối thứ tự thực hiện và kết nối artifact giữa các module.

Ví dụ cấu trúc:

```text
workspace/
├── build.xml
├── build-support/
│   └── common.xml
└── modules/
    ├── core/
    │   ├── build.xml
    │   └── src/
    ├── service/
    │   ├── build.xml
    │   └── src/
    └── cli/
        ├── build.xml
        └── src/
```

Trong ví dụ này, `core` tạo thư viện dùng bởi `service`, còn `cli` phụ thuộc vào `service`. Mỗi module tự biên dịch và đóng gói source của mình. Build gốc chỉ điều phối thứ tự.

### 8.1. Thống nhất hợp đồng giữa các module

Các module nên có một nhóm target chung, chẳng hạn:

| Target | Hợp đồng |
|---|---|
| `clean` | Xóa output do module tạo ra |
| `resolve` | Chuẩn bị dependency cần thiết |
| `compile` | Biên dịch source chính |
| `test` | Chạy test và trả lỗi khi test thất bại |
| `package` | Tạo artifact đầu ra |

Không phải module nào cũng cần mọi target. Ví dụ module chỉ chứa tài nguyên có thể không cần `compile`. Tuy vậy, tên và ý nghĩa target nên nhất quán để build gốc có thể điều phối dễ dàng.

### 8.2. Tạo build gốc để điều phối thứ tự

File `workspace/build.xml` có thể gọi build của từng module bằng task `ant`:

```xml
<project name="workspace" default="package-all" basedir=".">
    <target name="clean-all">
        <ant antfile="build.xml" dir="modules/core" target="clean"/>
        <ant antfile="build.xml" dir="modules/service" target="clean"/>
        <ant antfile="build.xml" dir="modules/cli" target="clean"/>
    </target>

    <target name="package-core">
        <ant antfile="build.xml" dir="modules/core" target="package"/>
    </target>

    <target name="package-service" depends="package-core">
        <ant antfile="build.xml" dir="modules/service" target="package"/>
    </target>

    <target name="package-cli" depends="package-service">
        <ant antfile="build.xml" dir="modules/cli" target="package"/>
    </target>

    <target name="package-all" depends="package-cli"/>
</project>
```

Khi chạy `ant package-all` ở thư mục gốc, Ant build `core`, sau đó `service`, rồi `cli`. Mỗi lệnh `<ant>` chạy build script con trong thư mục module tương ứng. Theo mặc định, task `ant` truyền các property của build cha sang build con; nếu cần cô lập cấu hình, có thể điều chỉnh `inheritall` và truyền tường minh những property mà module cần.

Trong `modules/service/build.xml`, classpath có thể tham chiếu artifact của `core` bằng đường dẫn tương đối đến `../core/dist/core.jar`. Vì target `package-service` phụ thuộc `package-core`, artifact đó đã được tạo trước khi service biên dịch. Tương tự, `cli` có thể dùng artifact do service tạo ra.

Điều quan trọng là dependency giữa module phải được thể hiện bằng target dependency ở build gốc và bằng artifact/classpath ở module tiêu thụ. Không nên dựa vào thứ tự alphabet của thư mục để suy ra module nào phải build trước.

### 8.3. Dùng `subant` khi cần gọi cùng target trên nhiều build

Nếu nhiều module có cùng một thao tác độc lập, `subant` có thể gọi một target trên tập hợp build file:

```xml
<target name="clean-modules">
    <subant target="clean" failonerror="true">
        <fileset dir="modules">
            <include name="*/build.xml"/>
        </fileset>
    </subant>
</target>
```

`subant` phù hợp với tác vụ đồng nhất như `clean` hoặc một bước kiểm tra chung. Với quá trình build có quan hệ phụ thuộc giữa module, hãy khai báo thứ tự bằng target và task `ant` rõ ràng; danh sách file được quét không thay thế cho mô hình dependency.

### 8.4. Chia sẻ logic mà vẫn giữ quyền sở hữu của module

`build-support/common.xml` nên chứa quy tắc thực sự dùng chung như macro, cấu hình công cụ hoặc target tiện ích. Mỗi module vẫn sở hữu source, test, dependency riêng và artifact riêng. Tránh đưa mọi logic vào build gốc, vì khi đó build từng module độc lập sẽ khó khăn và thay đổi nhỏ có thể ảnh hưởng toàn repository.

Mỗi module cũng nên có thư mục output riêng. Nếu nhiều module cùng ghi vào một `build/classes`, file của module này có thể ghi đè hoặc làm nhiễu kết quả của module khác.

### 8.5. Kiểm soát lỗi và khả năng chạy độc lập

Build gốc cần dừng khi một module bắt buộc thất bại. Với `subant`, thuộc tính `failonerror="true"` thể hiện rõ yêu cầu đó. Với task `ant`, không nên bắt lỗi rồi tiếp tục đóng gói module phụ thuộc khi artifact đầu vào chưa được tạo.

Hãy kiểm tra cả hai cách chạy:

- Chạy build từ thư mục gốc để xác nhận thứ tự giữa các module.
- Chạy build của một module riêng để xác nhận module có thể tự giải quyết cấu hình và dependency của nó trong phạm vi đã thiết kế.

**Kết quả cần đạt:** có thể tổ chức repository nhiều module, thống nhất target contract, điều phối dependency theo thứ tự và chia sẻ build logic mà không làm mất tính độc lập của từng module.

## 9. Chặng 7 — Đưa Ant vào CI và làm build đáng tin cậy

Khi build chạy được trên máy cá nhân, bước tiếp theo là bảo đảm cùng một quy trình có thể chạy tự động trên CI.

Một lệnh CI thường có dạng:

```bash
ant -Denvironment=ci clean test package
```

Lệnh này chọn cấu hình CI, xóa output cũ, chạy test và tạo artifact. Tùy dự án, có thể gọi target tổng hợp như `verify` hoặc `build-all` để gom các bước thành một giao diện duy nhất.

Các nguyên tắc nên áp dụng:

1. **Môi trường có kiểm soát:** thống nhất JDK, Ant và các công cụ phụ trợ giữa máy cá nhân với CI.
2. **Dependency có phiên bản rõ ràng:** khóa phiên bản thư viện và repository; tránh để build phụ thuộc vào JAR không được quản lý.
3. **Build sạch có thể tái lập:** định kỳ chạy từ output rỗng để phát hiện file thừa hoặc kết quả phụ thuộc lần build trước.
4. **Lỗi được truyền đúng:** test fail, compile fail hoặc thiếu dependency phải làm job thất bại. Không dùng cấu hình nuốt lỗi để pipeline vẫn báo thành công.
5. **Artifact có vị trí ổn định:** CI biết chính xác file nào cần lưu, kiểm tra hoặc chuyển sang bước triển khai.
6. **Log đủ thông tin:** khi có lỗi, giữ log của lệnh Ant và báo cáo test để có thể tìm nguyên nhân.
7. **Secret được quản lý riêng:** token và mật khẩu được cấp qua secret store của CI, không lưu trong source hoặc file properties công khai.

Một số lệnh hỗ trợ chẩn đoán:

```bash
ant -p
ant -verbose package
ant -debug package
ant -diagnostics
```

`-verbose` hiển thị thêm chi tiết trong quá trình chạy; `-debug` cung cấp thông tin sâu hơn khi cần truy vết; `-diagnostics` hiển thị thông tin môi trường Ant. Khi gặp lỗi, hãy xác định target và task đầu tiên thất bại rồi kiểm tra input, property, classpath và đường dẫn của chính bước đó.

## 10. Các lỗi thường gặp khi build lớn dần

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Không tìm thấy task | Task thuộc gói tùy chọn hoặc thư viện ngoài chưa được nạp | Kiểm tra phiên bản Ant, `-lib`, `taskdef` hoặc cấu hình antlib |
| Không tìm thấy class khi compile | Classpath thiếu JAR hoặc path reference chưa được tạo | Kiểm tra `path`, `fileset`, dependency resolve và vị trí JAR |
| Chạy được trên máy cá nhân nhưng lỗi trên CI | JDK, Ant, biến môi trường hoặc dependency khác nhau | In phiên bản công cụ và so sánh property môi trường |
| Target chạy sai thứ tự | `depends` chưa khai báo đúng hoặc gọi target khác với dự kiến | Dùng `ant -verbose` và lần theo đồ thị target |
| Thay đổi source nhưng output cũ vẫn còn | Target không xử lý file cũ hoặc bước copy không đồng bộ | Chạy build sạch, kiểm tra điều kiện cập nhật và thư mục output |
| Module phụ thuộc không tìm thấy JAR | Build gốc chưa tạo artifact trước hoặc đường dẫn tương đối sai | Kiểm tra dependency giữa target module và classpath tiêu thụ |
| Build báo thành công dù test lỗi | Test runner không truyền exit code hoặc cấu hình task cho phép tiếp tục | Cấu hình runner/task để lỗi được truyền về Ant và CI |

Khi debug, nên kiểm tra theo thứ tự: target nào được gọi, property nào đang có giá trị, thư mục làm việc là gì, task nhận input nào, classpath gồm những gì và task kết thúc với trạng thái nào. Cách này thường khoanh vùng được lỗi nhanh hơn việc đọc toàn bộ build script cùng lúc.

## 11. Bài tập thực hành theo từng chặng

| Bài tập | Việc cần làm | Tiêu chí hoàn thành |
|---|---|---|
| 1. Hello Ant | Tạo target `hello`, `prepare` và `clean` | Gọi được target mặc định và target theo tên |
| 2. Java JAR | Tạo `App.java`, compile, copy resource và đóng gói JAR | Build sạch tạo được JAR chứa class và resource |
| 3. Test | Thêm test source và test runner | Test pass thì build thành công; test fail thì build thất bại |
| 4. Dependency | Thêm một thư viện ngoài vào classpath | Compile và chạy ứng dụng với đúng phiên bản dependency |
| 5. Cấu hình | Tạo cấu hình `dev` và `ci` bằng property | Có thể chọn môi trường bằng `-D` mà không sửa build script |
| 6. Nhiều module | Tạo `core`, `service`, `cli` và build gốc | Build gốc tạo artifact theo đúng thứ tự phụ thuộc |
| 7. CI | Chạy clean, test và package trên môi trường tự động | Job thất bại khi compile/test lỗi và lưu được artifact khi thành công |

Không nên chuyển sang bài nhiều module khi target, classpath và thư mục output của một module vẫn chưa rõ. Mỗi chặng cần để lại một build script có thể chạy lại và giải thích được.

## 12. Khi nào có thể xem là đã nắm được Ant?

Người học đã có nền tảng vững khi có thể tự thiết kế build cho một dự án Java mà không phải sao chép nguyên một `build.xml` có sẵn. Cụ thể, cần giải thích được:

- Target nào là entry point, target nào là bước trung gian và vì sao chúng phụ thuộc nhau.
- Source, resource, test, output trung gian và artifact phát hành nằm ở đâu.
- Classpath được tạo từ đâu và dependency nào thuộc compile, test hoặc runtime.
- Property được nạp theo thứ tự nào, giá trị dòng lệnh tác động ra sao và cấu hình môi trường được chọn thế nào.
- Phần build logic nào dùng chung, phần nào thuộc riêng từng module.
- Build gốc điều phối module theo quan hệ dependency nào và xử lý lỗi ra sao.
- Một build sạch trên CI tạo ra artifact nào và làm thế nào để truy vết khi build thất bại.

Ant phù hợp khi dự án cần một quy trình build tùy biến, khi phải duy trì hệ thống build cũ hoặc khi muốn mô tả rõ từng thao tác. Khi dự án cần quy ước dependency, vòng đời chuẩn và mô hình multi-module được tích hợp sẵn, hãy đánh giá thêm công cụ build cấp cao hơn. Dù chọn công cụ nào, các kiến thức về source set, classpath, dependency, artifact, tính tái lập và thứ tự build vẫn là nền tảng quan trọng.
