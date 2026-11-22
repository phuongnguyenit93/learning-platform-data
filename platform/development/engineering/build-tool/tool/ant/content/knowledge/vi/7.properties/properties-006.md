# Phân biệt value và location khi khai báo đường dẫn

## Mục tiêu

Trong Apache Ant, task `property` dùng để khai báo các property có thể tái sử dụng trong buildfile. Khi property chứa đường dẫn đến thư mục hoặc tệp, ta thường gặp hai thuộc tính là `value` và `location`.

Cả hai đều có thể gán một chuỗi cho property, nhưng Ant diễn giải chúng theo cách khác nhau:

- **`value`** gán giá trị văn bản được cung cấp. Nếu chuỗi trông giống một đường dẫn tương đối, Ant vẫn giữ nó dưới dạng chuỗi tương đối.
- **`location`** coi giá trị được cung cấp là một đường dẫn tệp. Đường dẫn tương đối được giải quyết dựa trên `basedir` của project, sau đó được chuẩn hóa thành đường dẫn tuyệt đối.

Chọn đúng thuộc tính giúp buildfile hoạt động ổn định khi chạy từ các thư mục làm việc khác nhau, đồng thời giúp người đọc biết property đang lưu một đoạn đường dẫn hay một vị trí cụ thể trên hệ thống tệp.

## 1. Property trong Ant là gì?

Property là một cặp tên và giá trị. Sau khi khai báo, ta tham chiếu property bằng cú pháp `${property.name}`.

~~~xml
<project name="property-demo" default="show">
    <property name="app.name" value="Sample Application"/>
    <property name="build.dir" value="build"/>

    <target name="show">
        <echo message="Application: ${app.name}"/>
        <echo message="Build directory: ${build.dir}"/>
    </target>
</project>
~~~

Trong ví dụ trên, `app.name` và `build.dir` là hai property. Task echo sử dụng các giá trị đó khi chạy target `show`.

Property trong Ant thường có tính chất bất biến: sau khi một property đã được thiết lập, khai báo tiếp theo cùng tên không ghi đè giá trị ban đầu. Quy tắc này áp dụng cho cả property được khai báo bằng `value` và `location`.

~~~xml
<property name="output.dir" value="out"/>
<property name="output.dir" location="build/out"/>
~~~

Sau hai khai báo trên, `output.dir` vẫn giữ giá trị từ khai báo đầu tiên là `out`. Khai báo thứ hai không chuyển property thành đường dẫn tuyệt đối. Vì vậy, khi thử nghiệm `value` và `location`, hãy dùng tên property khác nhau hoặc bảo đảm property chưa được thiết lập trước đó.

## 2. Thuộc tính value: gán chuỗi như đã cung cấp

Thuộc tính `value` đặt giá trị văn bản cho property. Ant vẫn thực hiện property expansion đối với các tham chiếu `${...}` trong giá trị, nhưng không tự coi chuỗi đó là đường dẫn để chuyển thành tuyệt đối hoặc chuẩn hóa.

~~~xml
<project name="value-demo" default="show" basedir=".">
    <property name="source.dir" value="src/main/java"/>
    <property name="build.dir" value="build"/>

    <target name="show">
        <echo message="Source: ${source.dir}"/>
        <echo message="Build: ${build.dir}"/>
    </target>
</project>
~~~

Hai property trên lưu các chuỗi tương đối `src/main/java` và `build`. Chúng chưa được chuyển thành đường dẫn tuyệt đối ngay tại thời điểm khai báo property.

Điều đó hữu ích khi muốn giữ đường dẫn tương đối để tái sử dụng trong nhiều vị trí, hoặc khi task nhận giá trị và tự diễn giải đường dẫn theo ngữ cảnh của nó.

### 2.1. value không tự giải quyết dấu chấm và dấu chấm đôi

Xét khai báo:

~~~xml
<property name="source.path" value="src/../src/main/java"/>
~~~

Property `source.path` giữ chuỗi `src/../src/main/java`. Ant không dùng thuộc tính `value` để tự loại bỏ phần `../` trong chuỗi này.

Nếu in property ra log, ta sẽ thấy giá trị văn bản đã khai báo, có thể kèm kết quả thay thế các property được tham chiếu:

~~~xml
<echo message="Source path: ${source.path}"/>
~~~

Việc đường dẫn tương đối đó cuối cùng trỏ đến đâu còn phụ thuộc vào task sử dụng nó và quy tắc phân giải đường dẫn của task.

### 2.2. value vẫn hỗ trợ property expansion

Dùng `value` không có nghĩa là Ant giữ nguyên mọi ký tự trong thuộc tính. Các biểu thức property hợp lệ vẫn được thay thế.

~~~xml
<project name="value-expansion-demo" default="show" basedir=".">
    <property name="module.dir" value="modules"/>
    <property name="source.dir" value="${module.dir}/sample/src"/>

    <target name="show">
        <echo message="Module: ${module.dir}"/>
        <echo message="Source: ${source.dir}"/>
    </target>
</project>
~~~

Property `source.dir` nhận chuỗi `modules/sample/src` sau khi Ant thay `${module.dir}`. Kết quả vẫn là một chuỗi đường dẫn tương đối; việc ghép property không tự biến nó thành đường dẫn tuyệt đối.

Có thể dùng cách này khi cấu trúc build được thiết kế xoay quanh các đường dẫn tương đối, chẳng hạn thư mục nguồn, thư mục tài nguyên hoặc tên thư mục đầu ra được dùng bên trong project.

## 3. Thuộc tính location: khai báo vị trí tệp hoặc thư mục

Thuộc tính `location` cho Ant biết giá trị property biểu diễn một vị trí trên hệ thống tệp. Ant xử lý đường dẫn theo `basedir` của project và chuẩn hóa kết quả.

~~~xml
<project name="location-demo" default="show" basedir=".">
    <property name="source.dir" location="src/main/java"/>
    <property name="build.dir" location="build"/>

    <target name="show">
        <echo message="Project base: ${basedir}"/>
        <echo message="Source: ${source.dir}"/>
        <echo message="Build: ${build.dir}"/>
    </target>
</project>
~~~

Nếu buildfile nằm trong thư mục `/work/sample` và project dùng thư mục đó làm `basedir`, property `source.dir` sẽ được chuyển thành đường dẫn tuyệt đối tương ứng với `/work/sample/src/main/java`. Trên Windows, kết quả sẽ theo dạng đường dẫn của hệ điều hành, ví dụ `C:\work\sample\src\main\java`.

Ví dụ đường dẫn chỉ nhằm minh họa. Giá trị thực tế phụ thuộc vào vị trí project và hệ điều hành đang chạy Ant.

### 3.1. Đường dẫn tương đối được tính từ basedir

Khi `location` nhận một đường dẫn tương đối, Ant giải quyết nó dựa trên thư mục cơ sở của project.

~~~xml
<project name="basedir-demo" default="show" basedir="project-root">
    <property name="config.file" location="config/app.properties"/>

    <target name="show">
        <echo message="Base: ${basedir}"/>
        <echo message="Config: ${config.file}"/>
    </target>
</project>
~~~

Trong ví dụ này, `basedir="project-root"` là thư mục cơ sở được chỉ định tương đối với vị trí buildfile. Property `config.file` sau đó được giải quyết từ thư mục cơ sở của project, không phải đơn giản từ thư mục hiện tại của terminal tại thời điểm gọi Ant.

Nếu không chỉ định `basedir` trong phần tử project, Ant thông thường dùng thư mục chứa buildfile làm thư mục cơ sở. Thuộc tính `basedir` cũng có thể được đặt rõ ràng để buildfile có một gốc phân giải đường dẫn dễ dự đoán.

Điểm này rất quan trọng khi chạy buildfile từ một thư mục khác. Ví dụ, nếu gọi:

~~~text
ant -f /work/sample/build.xml show
~~~

thì đường dẫn tương đối trong `location` vẫn được tính theo `basedir` của project trong buildfile, thay vì mặc nhiên lấy thư mục hiện tại của terminal làm gốc.

### 3.2. Đường dẫn có dấu chấm và dấu chấm đôi được chuẩn hóa

Giả sử project có `basedir` là `/work/sample` và khai báo:

~~~xml
<property name="source.dir" location="src/../src/main/./java"/>
~~~

Ant giải quyết đường dẫn tương đối từ `basedir`, sau đó chuẩn hóa các thành phần như `.` và `..`. Kết quả minh họa là:

~~~text
/work/sample/src/main/java
~~~

Như vậy, `location` cung cấp một biểu diễn đường dẫn tuyệt đối đã chuẩn hóa, thuận tiện khi nhiều task cần dùng chung một vị trí.

Chuẩn hóa đường dẫn không đồng nghĩa với việc Ant tạo thư mục, tạo tệp hoặc xác nhận tệp chắc chắn tồn tại. `location` chỉ tính giá trị đường dẫn cho property. Nếu cần kiểm tra sự tồn tại, hãy dùng task hoặc điều kiện phù hợp như `available`.

### 3.3. Đường dẫn tuyệt đối được cung cấp trực tiếp

Nếu giá trị của `location` đã là đường dẫn tuyệt đối, Ant sử dụng vị trí đó và chuẩn hóa đường dẫn.

~~~xml
<property name="external.config" location="/opt/app/config/app.properties"/>
~~~

Đường dẫn này không được ghép thêm vào `basedir` như một đường dẫn tương đối. Trên Windows, có thể dùng đường dẫn tuyệt đối theo định dạng của hệ thống, chẳng hạn `C:/tools/app/config.properties`.

### 3.4. location cũng hỗ trợ property expansion

Có thể tham chiếu property đã khai báo trước trong thuộc tính `location`.

~~~xml
<project name="nested-location-demo" default="show" basedir=".">
    <property name="workspace.dir" location="../workspace"/>
    <property name="generated.dir" location="${workspace.dir}/generated"/>
    <property name="report.file" location="${generated.dir}/reports/build.html"/>

    <target name="show">
        <echo message="Workspace: ${workspace.dir}"/>
        <echo message="Generated: ${generated.dir}"/>
        <echo message="Report: ${report.file}"/>
    </target>
</project>
~~~

Ant thay các tham chiếu property trước khi xử lý đường dẫn. Vì vậy, khai báo `generated.dir` sử dụng giá trị của `workspace.dir`, rồi `report.file` sử dụng giá trị của `generated.dir`.

Các property được tham chiếu cần được khai báo trước khi sử dụng. Nếu một property đã được thiết lập từ nơi khác, quy tắc bất biến của property vẫn áp dụng.

## 4. So sánh trực tiếp value và location

Bảng sau cho thấy sự khác nhau khi cùng một chuỗi đường dẫn được đưa vào hai thuộc tính.

Giả sử project có `basedir` là `/work/sample`:

| Khai báo | Giá trị property minh họa | Cách Ant diễn giải |
|---|---|---|
| `value="src/main/java"` | `src/main/java` | Giữ chuỗi tương đối |
| `location="src/main/java"` | `/work/sample/src/main/java` | Giải quyết từ basedir và chuẩn hóa |
| `value="src/../lib"` | `src/../lib` | Giữ chuỗi như đã cung cấp |
| `location="src/../lib"` | `/work/sample/lib` | Giải quyết và chuẩn hóa |
| `value="/opt/app/config"` | `/opt/app/config` | Giữ chuỗi tuyệt đối như văn bản |
| `location="/opt/app/config"` | `/opt/app/config` | Nhận diện vị trí tuyệt đối và chuẩn hóa |

Điểm cần ghi nhớ:

- `value` tập trung vào **giá trị chuỗi**.
- `location` tập trung vào **vị trí trên hệ thống tệp**.
- Cả hai đều có thể thay thế tham chiếu property.
- Chỉ `location` tự giải quyết đường dẫn tương đối theo `basedir` và chuẩn hóa nó.

## 5. Chọn thuộc tính nào khi khai báo đường dẫn?

Hãy dựa vào ý nghĩa của property trong buildfile.

### 5.1. Dùng value khi cần giữ đường dẫn tương đối

Ví dụ, project muốn lưu tên các thư mục con và kết hợp chúng với nhau:

~~~xml
<project name="relative-paths" default="show" basedir=".">
    <property name="source.root" value="src"/>
    <property name="source.java" value="${source.root}/main/java"/>
    <property name="source.test" value="${source.root}/test/java"/>
    <property name="build.root" value="build"/>
    <property name="build.classes" value="${build.root}/classes"/>

    <target name="show">
        <echo message="Java source: ${source.java}"/>
        <echo message="Test source: ${source.test}"/>
        <echo message="Classes: ${build.classes}"/>
    </target>
</project>
~~~

Cách viết này giữ các property ở dạng tương đối, dễ đọc và dễ ghép thành các đường dẫn con. Task sử dụng property sẽ nhận chuỗi tương đối và diễn giải nó theo quy tắc của task đó.

Dùng `value` phù hợp khi:

- Muốn lưu đường dẫn tương đối.
- Muốn lưu một đoạn đường dẫn để ghép với thư mục khác.
- Muốn giữ nguyên cách viết của chuỗi, kể cả các thành phần `.` hoặc `..`.
- Property không thực sự đại diện cho một vị trí tệp, dù tên của nó có thể chứa hậu tố `.dir` hoặc `.file`.

### 5.2. Dùng location khi cần một đường dẫn tuyệt đối ổn định theo project

Ví dụ, các task cần dùng chung thư mục đầu ra:

~~~xml
<project name="absolute-paths" default="show" basedir=".">
    <property name="build.dir" location="build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="reports.dir" location="${build.dir}/reports"/>
    <property name="config.file" location="config/build.properties"/>

    <target name="show">
        <echo message="Build: ${build.dir}"/>
        <echo message="Classes: ${classes.dir}"/>
        <echo message="Reports: ${reports.dir}"/>
        <echo message="Config: ${config.file}"/>
    </target>
</project>
~~~

Các property này biểu diễn vị trí cụ thể trong cây thư mục của project. Vì chúng được chuyển thành đường dẫn tuyệt đối, các task có thể nhận cùng một vị trí ngay cả khi build được gọi từ thư mục làm việc khác, miễn là cấu hình `basedir` của project không thay đổi.

Dùng `location` phù hợp khi:

- Property đại diện cho một tệp hoặc thư mục cụ thể.
- Muốn đường dẫn tương đối được tính theo `basedir` của project.
- Muốn loại bỏ các thành phần đường dẫn dư thừa như `.` và `..`.
- Muốn truyền một đường dẫn tuyệt đối đã chuẩn hóa cho nhiều task.

## 6. Những nhầm lẫn thường gặp

### 6.1. Nghĩ rằng value tự biến đường dẫn tương đối thành tuyệt đối

~~~xml
<property name="output.dir" value="build/output"/>
~~~

Khai báo này chỉ lưu chuỗi `build/output`. Tên property có hậu tố `.dir` không làm Ant tự chuyển nó thành đường dẫn tuyệt đối.

Nếu cần một vị trí tuyệt đối theo project, hãy dùng:

~~~xml
<property name="output.dir" location="build/output"/>
~~~

### 6.2. Nghĩ rằng location kiểm tra tệp có tồn tại

~~~xml
<property name="report.file" location="build/reports/index.html"/>
~~~

Property được gán đường dẫn đã giải quyết và chuẩn hóa. Việc khai báo không tự tạo thư mục `build/reports`, cũng không bảo đảm `index.html` đã tồn tại.

Nếu muốn kiểm tra sự tồn tại của tệp, có thể dùng task `available`:

~~~xml
<available file="${report.file}" property="report.exists"/>

<target name="check-report">
    <echo message="Report exists: ${report.exists}"/>
</target>
~~~

Nếu tệp chưa tồn tại, property kiểm tra sẽ không được thiết lập. Cần xử lý trường hợp property đó chưa có trong logic build.

### 6.3. Nhầm basedir với thư mục hiện tại của terminal

`basedir` là thư mục cơ sở của project Ant. Thư mục hiện tại của terminal là nơi lệnh Ant được gọi. Hai thư mục có thể trùng nhau, nhưng không bắt buộc.

Ví dụ, buildfile có thể nằm trong `/work/sample`, trong khi terminal đang ở `/tmp`:

~~~text
cd /tmp
ant -f /work/sample/build.xml show
~~~

Nếu project sử dụng thư mục chứa buildfile làm `basedir`, thì:

~~~xml
<property name="config.dir" location="config"/>
~~~

sẽ được giải quyết từ thư mục cơ sở của project, không phải từ `/tmp`.

Đây là một lý do quan trọng để dùng `location` khi muốn diễn tả vị trí gắn với project.

### 6.4. Nghĩ rằng ghép property bằng value sẽ tự chuẩn hóa

~~~xml
<property name="root.dir" value="project/.."/>
<property name="output.dir" value="${root.dir}/build"/>
~~~

Property `output.dir` giữ chuỗi được ghép từ hai giá trị. Phần `..` vẫn còn trong chuỗi.

Nếu muốn Ant xử lý chuỗi ghép đó như một vị trí tệp, có thể khai báo:

~~~xml
<property name="root.dir" location="project/.."/>
<property name="output.dir" location="${root.dir}/build"/>
~~~

Khi đó, mỗi property được xử lý theo ngữ nghĩa đường dẫn của `location`.

### 6.5. Khai báo lại property với location để mong ghi đè value

~~~xml
<property name="logs.dir" value="logs"/>
<property name="logs.dir" location="build/logs"/>
~~~

Khai báo thứ hai không ghi đè khai báo đầu tiên. Ant property thông thường chỉ nhận giá trị lần đầu. Nếu muốn thử một cách khai báo khác, hãy đổi tên property hoặc loại bỏ nguyên nhân khiến property đã được thiết lập trước đó.

### 6.6. Dùng location để ghép danh sách classpath

`location` của task `property` dành cho một vị trí tệp hoặc thư mục. Nó không phải công cụ để ghép danh sách nhiều thư viện thành classpath.

Nếu cần quản lý classpath, hãy dùng kiểu dữ liệu `path` của Ant:

~~~xml
<path id="compile.classpath">
    <pathelement location="lib/alpha.jar"/>
    <pathelement location="lib/beta.jar"/>
    <pathelement location="${external.lib}/gamma.jar"/>
</path>
~~~

Ở đây, `path` biểu diễn một tập hợp các phần tử đường dẫn. Mỗi `pathelement` có thể dùng thuộc tính `location` để chỉ một vị trí cụ thể. Đây là cơ chế phù hợp hơn khi cần thêm, ghép hoặc tái sử dụng nhiều mục classpath.

## 7. Ví dụ tổng hợp: buildfile dùng cả value và location

Ví dụ sau cho thấy hai cách khai báo có thể cùng tồn tại trong một project. Property dạng tương đối được giữ bằng `value`, còn các vị trí đầu ra được chuẩn hóa bằng `location`.

~~~xml
<project name="path-properties" default="show" basedir=".">
    <!-- Các thành phần đường dẫn tương đối -->
    <property name="source.root" value="src"/>
    <property name="source.main" value="${source.root}/main/java"/>
    <property name="source.test" value="${source.root}/test/java"/>

    <!-- Các vị trí cụ thể trong hệ thống tệp -->
    <property name="build.dir" location="build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="test.classes.dir" location="${build.dir}/test-classes"/>
    <property name="report.file" location="${build.dir}/reports/test.html"/>

    <target name="show">
        <echo message="Project base: ${basedir}"/>
        <echo message="Main source (relative): ${source.main}"/>
        <echo message="Test source (relative): ${source.test}"/>
        <echo message="Build directory (absolute): ${build.dir}"/>
        <echo message="Classes (absolute): ${classes.dir}"/>
        <echo message="Test classes (absolute): ${test.classes.dir}"/>
        <echo message="Report (absolute): ${report.file}"/>
    </target>

    <target name="prepare">
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${test.classes.dir}"/>
        <mkdir dir="${build.dir}/reports"/>
    </target>
</project>
~~~

Trong ví dụ:

1. `source.root`, `source.main` và `source.test` giữ các đoạn đường dẫn tương đối. Chúng hữu ích khi muốn mô tả cấu trúc nguồn theo dạng ngắn gọn.
2. `build.dir` được khai báo bằng `location`, vì vậy Ant giải quyết nó theo `basedir` và chuẩn hóa thành đường dẫn tuyệt đối.
3. `classes.dir`, `test.classes.dir` và `report.file` tiếp tục dựa trên property đã có. Mỗi giá trị được xử lý như một vị trí tệp.
4. Target `prepare` dùng các vị trí đó để tạo thư mục. Việc tạo thư mục diễn ra bởi task `mkdir`, không phải bởi khai báo property.

Có thể gọi target từ một thư mục terminal khác mà các vị trí được tạo bởi `location` vẫn gắn với `basedir` của project.

## 8. Bảng chọn nhanh

| Nhu cầu | Nên dùng | Ví dụ |
|---|---|---|
| Lưu đường dẫn tương đối | `value` | `value="src/main/java"` |
| Lưu tên hoặc đoạn đường dẫn để ghép tiếp | `value` | `value="${source.root}/main"` |
| Tạo vị trí tuyệt đối từ đường dẫn tương đối | `location` | `location="build/classes"` |
| Chuẩn hóa đường dẫn có `.` hoặc `..` | `location` | `location="src/../build"` |
| Dùng đường dẫn tuyệt đối đã có | `location` nếu muốn xử lý như vị trí tệp | `location="/opt/app/config"` |
| Quản lý nhiều thư viện trong classpath | Kiểu dữ liệu `path` | `<path id="...">...</path>` |

## 9. Tự kiểm tra khi khai báo property chứa đường dẫn

Trước khi chọn `value` hoặc `location`, hãy tự hỏi:

1. Property này cần giữ một chuỗi tương đối hay đại diện cho một vị trí cụ thể trên hệ thống tệp?
2. Nếu đường dẫn tương đối, nó cần được giải quyết từ `basedir` của project hay do task sử dụng tự xử lý?
3. Có cần loại bỏ các thành phần `.` và `..` để tạo đường dẫn chuẩn hóa không?
4. Property có tham chiếu property khác chưa được khai báo không?
5. Tên property có thể đã được thiết lập ở một file hoặc target khác không?
6. Có đang nhầm một vị trí đơn lẻ với danh sách nhiều phần tử classpath không?
7. Có đang kỳ vọng việc khai báo property sẽ tự tạo hoặc kiểm tra tệp, thư mục không?

Nếu cần giữ nguyên đường dẫn tương đối, dùng `value`. Nếu cần một vị trí tệp được giải quyết theo `basedir` và chuẩn hóa, dùng `location`. Việc lựa chọn theo mục đích này làm cho property dễ hiểu và giúp buildfile ít phụ thuộc vào thư mục mà người dùng đang đứng khi gọi Ant.
