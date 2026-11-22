# Mối quan hệ giữa project, target, task, property và kiểu dữ liệu trong Apache Ant

Trong Apache Ant, một file build mô tả một **project**, chia công việc thành các **target**. Mỗi target chứa các **task** để thực hiện công việc cụ thể. Task lấy cấu hình từ **property** và có thể nhận dữ liệu có cấu trúc như **path**, **fileset** hoặc **patternset**.

Năm khái niệm này kết hợp để tạo thành quy trình build có thể đọc, tái sử dụng và điều khiển từ dòng lệnh.

## 1. Bức tranh tổng thể

~~~text
Project (build.xml)
│
├── Properties: giá trị cấu hình
│   ├── src.dir = "src"
│   └── build.dir = "build"
│
├── Data types: dữ liệu có cấu trúc
│   ├── Path: danh sách đường dẫn
│   └── Fileset: tập file được chọn theo mẫu
│
├── Target: init
│   └── Tasks: mkdir, copy
│
├── Target: compile
│   └── Task: javac
│
└── Target: package
    └── Task: jar
~~~

- **Project** là phạm vi của toàn bộ cấu hình và các target trong một build file.
- **Target** là một bước công việc có tên. Target có thể phụ thuộc vào target khác.
- **Task** là thao tác thực tế được thực thi bên trong target.
- **Property** cung cấp giá trị cấu hình để target và task sử dụng.
- **Data type** biểu diễn dữ liệu có cấu trúc mà task cần, chẳng hạn danh sách đường dẫn hoặc tập file được chọn.

Property và data type thường được khai báo ở cấp project để nhiều target có thể dùng chung. Task thường được đặt trong target để Ant thực thi theo thứ tự của quy trình build.

## 2. Project: phạm vi của một build

Project là phần tử gốc của file Ant. Một build file thông thường có một phần tử project bao quanh các khai báo và target.

~~~xml
<project name="sample-app" default="package" basedir=".">
    <!-- Properties và data types -->

    <target name="init">
        <!-- Các task -->
    </target>
</project>
~~~

Ba thuộc tính thường gặp:

| Thuộc tính | Ý nghĩa |
|---|---|
| name | Tên dễ nhận biết của project. |
| default | Target được chọn khi gọi Ant mà không chỉ định target. |
| basedir | Thư mục gốc để phân giải các đường dẫn tương đối trong build file. |

### 2.1. basedir và đường dẫn

Nếu đặt basedir bằng dấu chấm, thư mục chứa build file thường được dùng làm thư mục cơ sở. Đường dẫn tương đối như src hoặc build/classes được hiểu dựa trên thư mục này.

~~~xml
<project name="sample-app" default="compile" basedir=".">
    <property name="src.dir" location="src"/>
    <property name="classes.dir" location="build/classes"/>
</project>
~~~

Thuộc tính location của task property diễn giải giá trị như một đường dẫn theo ngữ cảnh của project và chuẩn hóa đường dẫn đó. Vì vậy, src.dir và classes.dir có thể được dùng ở nhiều target mà không phải lặp lại cách ghép đường dẫn.

### 2.2. Target mặc định không phải target duy nhất

Với khai báo:

~~~xml
<project name="sample-app" default="package">
~~~

Lệnh **ant** chọn target package làm điểm bắt đầu. Nếu người dùng chỉ định **ant compile**, Ant bắt đầu từ target compile và thực hiện các dependency của target đó nếu có. Giá trị default không có nghĩa là mọi target khác sẽ tự động chạy sau target mặc định.

Project cũng cung cấp một số property dựng sẵn:

- **basedir**: thư mục cơ sở của project.
- **ant.file**: file build đang được Ant nạp.
- **ant.project.name**: tên project.
- **ant.version**: phiên bản Ant.

Có thể tham chiếu property bằng cú pháp **${tên-property}**.

## 3. Target: một bước trong quy trình build

Target là một nhóm thao tác có tên. Target giúp chia quy trình lớn thành các bước có mục đích rõ ràng:

- **clean**: xóa kết quả build cũ.
- **init**: tạo thư mục cần thiết.
- **compile**: biên dịch mã nguồn.
- **test**: chạy kiểm thử.
- **package**: đóng gói ứng dụng.
- **deploy**: triển khai sản phẩm.

Một target có thể chứa nhiều task. Ant thực thi các task trong target theo thứ tự chúng xuất hiện trong XML.

~~~xml
<target name="init">
    <mkdir dir="build"/>
    <mkdir dir="build/classes"/>
    <mkdir dir="build/dist"/>
</target>
~~~

Target init có ba task mkdir. Ant tạo thư mục build trước, sau đó tạo hai thư mục con.

### 3.1. Quan hệ phụ thuộc bằng depends

Thuộc tính depends khai báo những target phải hoàn thành trước target hiện tại.

~~~xml
<target name="init">
    <mkdir dir="build/classes"/>
</target>

<target name="compile" depends="init">
    <javac srcdir="src" destdir="build/classes"/>
</target>

<target name="package" depends="compile">
    <jar destfile="build/app.jar" basedir="build/classes"/>
</target>
~~~

Khi gọi **ant package**, Ant xử lý chuỗi phụ thuộc:

~~~text
init → compile → package
~~~

Target package không cần tự gọi target compile; dependency đã mô tả quan hệ đó. Nếu một target phụ thuộc vào nhiều target, có thể liệt kê tên bằng dấu phẩy:

~~~xml
<target name="package" depends="compile,copy-resources">
    <jar destfile="build/app.jar" basedir="build/classes"/>
</target>
~~~

Ant thực hiện dependency trước target phụ thuộc. Một target đã được thực hiện trong cùng một lần chạy build sẽ không bị chạy lặp lại chỉ vì nhiều nhánh dependency cùng tham chiếu đến nó.

Nên khai báo dependency theo quan hệ thực sự giữa các bước. Ví dụ, đóng gói cần biên dịch xong; kiểm thử tích hợp có thể cần ứng dụng đã được chuẩn bị. Dependency giúp người đọc hiểu tại sao một target cần những target khác.

### 3.2. Điều kiện chạy target: if và unless

Target có thể được điều khiển bằng if hoặc unless:

~~~xml
<target name="publish" if="publish.enabled">
    <echo message="Publishing artifact"/>
</target>

<target name="local-only" unless="publish.enabled">
    <echo message="Skipping publication"/>
</target>
~~~

- **if="publish.enabled"**: chạy target khi property publish.enabled đã được đặt.
- **unless="publish.enabled"**: chạy target khi property đó chưa được đặt.

Điểm cần nhớ: if và unless kiểm tra **sự tồn tại của property**, không diễn giải nội dung property như một biểu thức boolean. Nếu publish.enabled được đặt thành chuỗi false, property vẫn tồn tại và target có if="publish.enabled" vẫn đủ điều kiện chạy.

Có thể đặt property từ dòng lệnh:

~~~bash
ant -Dpublish.enabled=true publish
~~~

Nếu cần điều kiện phức tạp hơn, có thể dùng task condition để tạo property dựa trên điều kiện cụ thể rồi dùng property đó trong target.

### 3.3. Target không phải hàm

Target có tên và dependency, nhưng không hoạt động như một hàm thông thường:

- Target không có danh sách tham số riêng.
- Target không trả về giá trị.
- Target không tạo phạm vi biến cục bộ độc lập theo cách một lời gọi hàm thường làm.
- Các task trong target được thực thi theo thứ tự của build.

Khi cần thay đổi hành vi, thường dùng property, data type, dependency hoặc điều kiện của target để mô tả cấu hình.

## 4. Task: thao tác thực tế

Task là đơn vị thực thi công việc trong Ant. Tên phần tử XML tương ứng với tên task; thuộc tính và phần tử con cung cấp cấu hình cho nó.

Một số task phổ biến:

| Task | Công việc |
|---|---|
| mkdir | Tạo thư mục. |
| delete | Xóa file hoặc thư mục. |
| copy | Sao chép file. |
| move | Di chuyển file. |
| javac | Biên dịch mã nguồn Java. |
| jar | Tạo file JAR. |
| java | Chạy một lớp Java. |
| echo | In thông điệp ra log. |
| available | Kiểm tra sự tồn tại của file, class hoặc resource và có thể đặt property. |
| fail | Chủ động làm build thất bại khi điều kiện không được đáp ứng. |

Ví dụ:

~~~xml
<target name="prepare">
    <mkdir dir="build"/>
    <copy file="config/app.properties" todir="build"/>
    <echo message="Preparation completed"/>
</target>
~~~

Ant thực hiện lần lượt: tạo thư mục build, sao chép file cấu hình, rồi in thông điệp.

### 4.1. Task nhận cấu hình bằng thuộc tính XML

Các thuộc tính trên task thường nhận giá trị đơn giản:

~~~xml
<mkdir dir="${build.dir}"/>
~~~

Ở đây, mkdir là task, dir là thuộc tính cấu hình và ${build.dir} là tham chiếu đến property. Task không cần biết property được khai báo ở đâu; nó nhận giá trị sau khi Ant phân giải tham chiếu.

### 4.2. Task có thể chứa data type

Một số task nhận dữ liệu có cấu trúc thông qua phần tử con:

~~~xml
<copy todir="build/config">
    <fileset dir="config">
        <include name="*.properties"/>
    </fileset>
</copy>
~~~

copy là task thực hiện sao chép. fileset mô tả tập file nguồn, còn include chỉ định mẫu file được chọn. fileset và include ở đây đóng vai trò cấu hình dữ liệu cho task copy; chúng không phải thao tác độc lập cần Ant thực thi như một target riêng.

### 4.3. Thứ tự và lỗi khi task chạy

Trong một target, thứ tự khai báo task có ý nghĩa. Nếu task tạo thư mục đứng trước task ghi file vào thư mục đó, quy trình sẽ rõ ràng và có thể thực thi đúng.

Thông thường, nếu một task thất bại, Ant đánh dấu build thất bại và dừng các bước tiếp theo. Một số task có tùy chọn riêng như failonerror để thay đổi cách xử lý lỗi. Chỉ nên dùng tùy chọn này khi việc tiếp tục build sau lỗi là hành vi có chủ đích.

## 5. Property: giá trị cấu hình của build

Property là một cặp tên và giá trị. Nó đưa các giá trị thường dùng ra khỏi cấu hình task để có thể tái sử dụng và thay đổi theo môi trường.

~~~xml
<project name="sample-app" default="compile" basedir=".">
    <property name="src.dir" location="src"/>
    <property name="build.dir" location="build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>

    <target name="compile">
        <mkdir dir="${classes.dir}"/>
        <javac srcdir="${src.dir}" destdir="${classes.dir}"/>
    </target>
</project>
~~~

Thay vì lặp lại build/classes ở nhiều nơi, build file định nghĩa classes.dir một lần rồi tham chiếu bằng ${classes.dir}.

### 5.1. Property luôn có dạng tên và giá trị

Cú pháp tham chiếu:

~~~xml
<echo message="Source directory: ${src.dir}"/>
~~~

Cú pháp khai báo thường gặp:

~~~xml
<property name="app.version" value="1.0.0"/>
<property name="src.dir" location="src"/>
~~~

value gán một giá trị chuỗi. location diễn giải giá trị như một đường dẫn theo ngữ cảnh của project và chuẩn hóa đường dẫn đó.

Property của Ant là **giá trị dạng chuỗi**. Một giá trị trông giống số, boolean hoặc đường dẫn vẫn được lưu dưới dạng chuỗi; task sử dụng nó sẽ diễn giải theo mục đích của task.

~~~xml
<property name="debug.enabled" value="true"/>
<property name="retry.count" value="3"/>
~~~

Không nên hiểu debug.enabled là một biến boolean có thể thay đổi hoặc retry.count là một biến số nguyên mà Ant tự động cập nhật. Đây là các giá trị chuỗi được truyền cho task hoặc điều kiện phù hợp.

### 5.2. Property có tính bất biến

Một đặc điểm quan trọng của Ant là **property đã được đặt thì không thể bị ghi đè bằng một lần khai báo property thông thường tiếp theo**. Ant áp dụng nguyên tắc first definition wins: giá trị được đặt đầu tiên sẽ được giữ lại.

~~~xml
<property name="app.version" value="1.0"/>
<property name="app.version" value="2.0"/>

<target name="show-version">
    <echo message="${app.version}"/>
</target>
~~~

Khi chạy target show-version, giá trị được dùng vẫn là 1.0.

Quy tắc này hữu ích khi cho phép người dùng cung cấp giá trị từ bên ngoài và đặt giá trị mặc định trong build file:

~~~bash
ant -Dapp.version=2.5 package
~~~

Nếu property app.version đã được thiết lập từ dòng lệnh trước khi build file khai báo giá trị mặc định, khai báo mặc định trong file sẽ không thay thế giá trị đó.

Vì property không phải biến có thể gán lại, không nên thiết kế quy trình theo giả định rằng một task có thể thay đổi property đã được đặt. Khi cần nhiều giá trị cho nhiều giai đoạn, hãy dùng tên property khác nhau hoặc mô hình cấu hình phù hợp.

### 5.3. Các nguồn khai báo property

Property có thể đến từ nhiều nguồn.

**Khai báo trực tiếp trong build file**

~~~xml
<property name="build.dir" location="build"/>
~~~

**Truyền từ dòng lệnh**

~~~bash
ant -Denv=staging -Dapp.version=2.5 package
~~~

**Đọc từ file cấu hình**

~~~xml
<property file="build.properties"/>
~~~

File build.properties có thể chứa:

~~~properties
env=staging
app.version=2.5
~~~

**Đọc biến môi trường**

~~~xml
<property environment="env"/>
<echo message="User home: ${env.USERPROFILE}"/>
~~~

Tên property được tạo từ tiền tố env và tên biến môi trường. Trên hệ điều hành khác nhau, tên biến môi trường có thể khác nhau.

Do tính bất biến, thứ tự thiết lập property ảnh hưởng đến giá trị cuối cùng. Khi một giá trị cần được người chạy build tùy chỉnh, nên chọn cách khai báo và thứ tự nạp cấu hình có chủ đích.

### 5.4. Property và điều kiện

Property thường được dùng để bật hoặc tắt một phần quy trình:

~~~xml
<target name="integration-test" if="integration.enabled">
    <echo message="Running integration tests"/>
</target>
~~~

Gọi:

~~~bash
ant -Dintegration.enabled=true integration-test
~~~

sẽ đặt property trước khi Ant đánh giá điều kiện target. if chỉ quan tâm property có tồn tại hay không. Nếu cần tính toán điều kiện, hãy dùng các điều kiện Ant như isset, equals, available hoặc task condition thay vì xem chuỗi true/false là phép kiểm tra tự động.

## 6. Data type: dữ liệu có cấu trúc

Property phù hợp với một giá trị đơn giản. Tuy nhiên, nhiều task cần một tập hợp dữ liệu, chẳng hạn:

- Danh sách thư mục và file JAR tạo thành classpath.
- Tập file được chọn theo mẫu.
- Danh sách các thư mục cần xử lý.
- Bộ quy tắc chọn hoặc đổi tên file.

Ant cung cấp các **data type** để biểu diễn những cấu trúc này. Data type thường được khai báo bằng phần tử XML và có thể lồng trong task hoặc data type khác.

### 6.1. Phân biệt property, data type và task

| Khái niệm | Mục đích | Ví dụ |
|---|---|---|
| Property | Lưu một giá trị cấu hình dạng chuỗi. | build.dir, app.version |
| Data type | Mô tả dữ liệu có cấu trúc để task sử dụng. | path, fileset, patternset |
| Task | Thực hiện một thao tác. | javac, copy, jar |

Ví dụ:

~~~xml
<property name="build.dir" location="build"/>

<path id="compile.classpath">
    <pathelement location="lib/example.jar"/>
</path>

<target name="compile">
    <mkdir dir="${build.dir}/classes"/>
    <javac srcdir="src" destdir="${build.dir}/classes">
        <classpath refid="compile.classpath"/>
    </javac>
</target>
~~~

Trong đoạn này:

- build.dir là property chứa một đường dẫn.
- compile.classpath là data type path, mô tả danh sách đường dẫn.
- javac là task thực hiện biên dịch và nhận classpath đã khai báo.

### 6.2. Các data type thường gặp

| Data type | Dùng để mô tả | Ví dụ sử dụng |
|---|---|---|
| path | Một chuỗi đường dẫn gồm file hoặc thư mục. | Classpath, source path. |
| pathelement | Một phần tử đường dẫn bên trong path. | Một thư mục hoặc file JAR. |
| fileset | Tập file được chọn từ một thư mục theo include/exclude. | Sao chép file cấu hình hoặc resource. |
| dirset | Tập thư mục được chọn theo mẫu. | Xử lý các thư mục con phù hợp. |
| filelist | Danh sách file được chỉ định rõ ràng. | Xử lý một nhóm file đã biết tên. |
| patternset | Tập mẫu include/exclude có thể tái sử dụng. | Dùng chung quy tắc lọc file. |
| filterset | Tập quy tắc thay thế token trong quá trình xử lý file. | Thay token cấu hình khi copy. |
| mapper | Quy tắc ánh xạ tên hoặc đường dẫn nguồn sang đích. | Đổi tên file khi copy. |

Tên data type không có nghĩa là mọi task đều hỗ trợ nó. Mỗi task quy định loại dữ liệu nào có thể được nhận qua thuộc tính hoặc phần tử con.

### 6.3. Path: mô tả danh sách đường dẫn

path thường được dùng để mô tả classpath hoặc danh sách thư mục mà task cần tìm kiếm.

~~~xml
<path id="compile.classpath">
    <pathelement location="lib/core.jar"/>
    <pathelement location="lib/logging.jar"/>
    <pathelement location="build/classes"/>
</path>
~~~

Path trên chứa ba phần tử. Một task có thể sử dụng nó bằng refid:

~~~xml
<javac srcdir="src"
       destdir="build/classes"
       includeantruntime="false">
    <classpath refid="compile.classpath"/>
</javac>
~~~

Cách khai báo này giúp nhiều task dùng cùng classpath mà không phải lặp lại từng đường dẫn.

### 6.4. Fileset: chọn file theo quy tắc

fileset biểu diễn một tập file lấy từ một thư mục. Nó thường kết hợp:

- **dir**: thư mục gốc.
- **include**: mẫu file cần chọn.
- **exclude**: mẫu file cần loại bỏ.

~~~xml
<fileset id="config.files" dir="config">
    <include name="**/*.properties"/>
    <exclude name="**/secret/**"/>
</fileset>
~~~

Trong mẫu Ant:

- * khớp với một phần tên trong một cấp thư mục.
- ** cho phép khớp qua nhiều cấp thư mục.
- **/*.properties chọn các file có đuôi .properties trong cây thư mục.
- **/secret/** loại các file nằm trong nhánh thư mục secret.

Có thể đưa fileset vào task copy:

~~~xml
<copy todir="build/config">
    <fileset refid="config.files"/>
</copy>
~~~

Hoặc khai báo trực tiếp bên trong task:

~~~xml
<copy todir="build/config">
    <fileset dir="config">
        <include name="**/*.properties"/>
        <exclude name="**/secret/**"/>
    </fileset>
</copy>
~~~

Cách khai báo trực tiếp phù hợp khi tập file chỉ dùng một lần. Dùng id và refid phù hợp khi nhiều task cần cùng một quy tắc chọn file.

### 6.5. Patternset: tái sử dụng quy tắc lọc

patternset gom các mẫu include/exclude thành một cấu hình có thể dùng lại:

~~~xml
<patternset id="java.source.patterns">
    <include name="**/*.java"/>
    <exclude name="**/generated/**"/>
</patternset>

<fileset id="main.sources" dir="src">
    <patternset refid="java.source.patterns"/>
</fileset>
~~~

Ở đây, patternset chỉ mô tả quy tắc. fileset kết hợp quy tắc đó với thư mục gốc để tạo tập file cụ thể.

### 6.6. Dùng id và refid để chia sẻ data type

Data type có thể được đặt tên bằng id rồi tham chiếu lại bằng refid, nếu task hoặc data type nhận nó hỗ trợ cách dùng này.

~~~xml
<path id="shared.path">
    <pathelement location="lib/common.jar"/>
</path>

<target name="compile">
    <javac srcdir="src/main" destdir="build/classes">
        <classpath refid="shared.path"/>
    </javac>
</target>

<target name="compile-test" depends="compile">
    <javac srcdir="src/test" destdir="build/test-classes">
        <classpath refid="shared.path"/>
    </javac>
</target>
~~~

id là định danh của đối tượng dữ liệu trong project. refid yêu cầu Ant sử dụng lại đối tượng đã được định nghĩa. Nó không tạo bản sao độc lập của cấu hình.

Khi đặt id, cần bảo đảm định danh không bị trùng trong phạm vi mà Ant quản lý. Khi dùng refid, data type được tham chiếu phải được khai báo và có loại tương thích với vị trí sử dụng.

## 7. Các khái niệm phối hợp trong một build

Năm khái niệm không tồn tại độc lập. Chúng liên kết với nhau thành một quy trình:

~~~mermaid
flowchart TD
    P["Project<br/>build.xml"] --> CFG["Cấu hình project"]
    CFG --> PROP["Properties<br/>giá trị cấu hình"]
    CFG --> DATA["Data types<br/>path, fileset, patternset"]
    P --> T1["Target: init"]
    T1 --> T2["Target: compile"]
    T2 --> T3["Target: package"]
    T1 --> A1["Tasks: mkdir, copy"]
    T2 --> A2["Task: javac"]
    T3 --> A3["Task: jar"]
    PROP -. "cung cấp giá trị" .-> A1
    PROP -. "cung cấp giá trị" .-> A2
    PROP -. "cung cấp giá trị" .-> A3
    DATA -. "cung cấp dữ liệu" .-> A2
~~~

Một cách đọc sơ đồ:

1. Project xác định phạm vi của build file.
2. Property cung cấp giá trị cấu hình như thư mục nguồn, thư mục đầu ra và phiên bản ứng dụng.
3. Data type mô tả tập hợp đường dẫn hoặc file cần xử lý.
4. Target tổ chức các bước công việc và quan hệ phụ thuộc.
5. Task thực hiện thao tác, sử dụng property và data type làm đầu vào.

### 7.1. Luồng xử lý khi gọi Ant

Giả sử người dùng chạy:

~~~bash
ant -Dapp.version=2.0 package
~~~

Có thể theo dõi quá trình ở mức khái niệm:

1. Ant nạp build file và xác định project.
2. Các cấu hình project như property và data type được khởi tạo.
3. Property app.version đã được cung cấp từ dòng lệnh, nên khai báo mặc định cùng tên trong build file sẽ không ghi đè nó.
4. Ant xác định target được yêu cầu là package.
5. Ant giải quyết các dependency của package trước khi chạy target này.
6. Trong từng target, Ant thực hiện các task theo thứ tự khai báo.
7. Khi task cần giá trị như ${build.dir}, Ant sử dụng property tương ứng.
8. Khi task cần danh sách file hoặc đường dẫn, Ant sử dụng data type được truyền vào.
9. Nếu các bước hoàn tất, build kết thúc thành công; nếu task phát sinh lỗi không được xử lý theo cách cho phép tiếp tục, build kết thúc với trạng thái thất bại.

## 8. Ví dụ hoàn chỉnh: biên dịch và đóng gói ứng dụng Java

Ví dụ sau kết hợp project, target, task, property và data type trong một build file.

~~~xml
<project name="sample-app" default="package" basedir=".">

    <!-- Properties: các giá trị cấu hình dùng chung -->
    <property name="src.dir" location="src"/>
    <property name="build.dir" location="build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="dist.dir" location="${build.dir}/dist"/>
    <property name="jar.name" value="sample-app.jar"/>

    <!-- Data type: classpath dùng khi biên dịch -->
    <path id="compile.classpath">
        <fileset dir="lib">
            <include name="*.jar"/>
        </fileset>
    </path>

    <!-- Target: chuẩn bị thư mục -->
    <target name="init">
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${dist.dir}"/>
    </target>

    <!-- Target: biên dịch, phụ thuộc vào init -->
    <target name="compile" depends="init">
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               includeantruntime="false">
            <classpath refid="compile.classpath"/>
        </javac>
    </target>

    <!-- Target: sao chép resource sau khi biên dịch -->
    <target name="resources" depends="compile">
        <copy todir="${classes.dir}">
            <fileset dir="${src.dir}">
                <include name="**/*.properties"/>
                <exclude name="**/test/**"/>
            </fileset>
        </copy>
    </target>

    <!-- Target mặc định: đóng gói -->
    <target name="package" depends="resources">
        <jar destfile="${dist.dir}/${jar.name}"
             basedir="${classes.dir}"/>
    </target>

    <!-- Target độc lập: dọn kết quả build -->
    <target name="clean">
        <delete dir="${build.dir}"/>
    </target>

</project>
~~~

Phân tích các thành phần:

| Thành phần | Vai trò trong ví dụ |
|---|---|
| Project sample-app | Bao bọc cấu hình và toàn bộ target. |
| default="package" | Chọn package khi gọi ant không kèm tên target. |
| src.dir, build.dir, classes.dir, dist.dir, jar.name | Property chứa đường dẫn và tên file đầu ra. |
| compile.classpath | Data type path, chứa các JAR trong thư mục lib. |
| init | Target tạo thư mục đầu ra. |
| compile | Target chạy task javac, phụ thuộc init. |
| resources | Target dùng task copy và data type fileset để sao chép resource. |
| package | Target dùng task jar để đóng gói, phụ thuộc resources. |
| clean | Target dùng task delete để xóa thư mục build. |

Các lệnh có thể dùng:

~~~bash
# Chạy target mặc định: package
ant

# Chạy riêng target compile và các dependency của nó
ant compile

# Chạy target clean
ant clean

# Truyền thêm property từ dòng lệnh
ant -Djar.name=sample-app-2.0.jar package
~~~

Khi chạy ant, luồng dependency là:

~~~text
init → compile → resources → package
~~~

Target clean không nằm trong chuỗi dependency đó, vì vậy nó chỉ chạy khi được yêu cầu trực tiếp. Đây là cách thường dùng: dọn dẹp là thao tác riêng, không nên tự động xóa kết quả trước khi đóng gói.

Ví dụ giả định project có mã nguồn Java trong src, thư mục lib chứa các JAR phụ thuộc và Ant có thể tìm thấy task javac cùng công cụ biên dịch phù hợp. Nếu project không có thư mục lib, hãy điều chỉnh hoặc bỏ phần classpath tương ứng theo cấu trúc thực tế.

## 9. Những nhầm lẫn thường gặp

### 9.1. Nhầm project với target

Project là phạm vi của toàn bộ build file. Target chỉ là một bước trong project. Một project thường có nhiều target, nhưng không vì thế mà mỗi target trở thành một project riêng.

### 9.2. Nhầm target với task

Target tổ chức công việc và dependency. Task thực hiện thao tác. Ví dụ, compile thường là tên target do người viết build file đặt; javac là task Ant dùng để biên dịch Java.

### 9.3. Nghĩ rằng gọi target sẽ tự chạy mọi target khác

Ant chỉ chạy target được yêu cầu cùng các dependency cần thiết. Target không nằm trong chuỗi dependency sẽ không tự động chạy. Target mặc định chỉ được chọn khi lệnh gọi không chỉ định target.

### 9.4. Nghĩ rằng property có thể ghi đè như biến thông thường

Property theo nguyên tắc first definition wins. Khai báo lại cùng tên không thay thế giá trị đã được đặt. Hãy thiết kế thứ tự nạp cấu hình và giá trị mặc định phù hợp.

### 9.5. Nghĩ rằng if="flag" kiểm tra chuỗi có giá trị true

if và unless kiểm tra sự tồn tại của property. Property có giá trị chuỗi false vẫn là property đã được đặt.

### 9.6. Nhầm data type với task

fileset mô tả tập file; copy thực hiện sao chép. path mô tả danh sách đường dẫn; javac sử dụng classpath đó khi biên dịch. Data type thường cung cấp dữ liệu cho task thay vì tự thực hiện một thao tác build.

### 9.7. Lặp cấu hình thay vì dùng id và refid

Nếu nhiều task cần cùng classpath hoặc cùng quy tắc lọc file, có thể khai báo data type một lần bằng id rồi tham chiếu bằng refid. Điều này giảm trùng lặp và giúp cấu hình nhất quán.

## 10. Cách tự phân tích một build file

Khi đọc một file Ant mới, có thể đi theo thứ tự sau:

1. Tìm phần tử project để biết tên project, target mặc định và thư mục cơ sở.
2. Tìm các khai báo property để hiểu những giá trị cấu hình quan trọng.
3. Tìm các data type như path, fileset và patternset; ghi nhận id và nơi chúng được tham chiếu.
4. Liệt kê các target và đọc thuộc tính depends, if, unless để hiểu luồng điều khiển.
5. Đọc task trong từng target theo đúng thứ tự XML để biết thao tác thực tế.
6. Lần theo các tham chiếu ${...} và refid để xác định đầu vào của mỗi task.
7. Từ target được gọi trên dòng lệnh, lần ngược dependency để xác định những bước thực sự được chạy.

Khi cần kiểm tra target có sẵn trong build file, có thể dùng:

~~~bash
ant -projecthelp
~~~

Lệnh này hiển thị trợ giúp và các target có mô tả phù hợp trong project.

## 11. Ghi nhớ

- **Project** là gốc của build file, chứa cấu hình và các target.
- **Target** đặt tên cho một bước công việc và liên kết các bước bằng depends.
- **Task** thực hiện thao tác cụ thể theo thứ tự khai báo trong target.
- **Property** lưu giá trị cấu hình dạng chuỗi; property đã đặt thường không bị ghi đè.
- **Data type** mô tả dữ liệu có cấu trúc như đường dẫn, tập file và quy tắc lọc.
- **id/refid** cho phép đặt tên và tái sử dụng data type.
- Khi Ant chạy, target quyết định các task nào được thực hiện; property và data type cung cấp cấu hình, dữ liệu cho những task đó.

Nếu phân biệt rõ năm khái niệm này, bạn có thể đọc một build file Ant từ cấu hình project, lần theo dependency giữa các target, hiểu thao tác của từng task và xác định chính xác dữ liệu đầu vào mà task sử dụng.

