# Khai báo property và tham chiếu bằng cú pháp ${...}

Trong một file `build.xml`, nhiều target và task thường dùng chung các giá trị như thư mục mã nguồn, thư mục chứa file biên dịch, tên file JAR, phiên bản ứng dụng hoặc classpath. Nếu viết trực tiếp từng giá trị ở mọi nơi, cấu hình sẽ khó đọc và dễ không nhất quán khi dự án thay đổi. Apache Ant cung cấp **property** để đặt tên cho những giá trị này và cho phép tham chiếu lại bằng cú pháp `${...}`.

Property là một khái niệm nền tảng trong Ant. Hiểu cách khai báo, mở rộng và xử lý property giúp ta tổ chức buildfile rõ ràng, truyền cấu hình từ dòng lệnh, đọc thiết lập từ file riêng và tránh những lỗi do thứ tự khai báo hoặc tính bất biến của property.

## 1. Property là gì?

Property là một cặp gồm **tên** và **giá trị** mà Ant lưu trong project trong lúc thực hiện build. Các task và target có thể dùng tên đó để lấy lại giá trị.

Ví dụ:

```xml
<property name="app.name" value="hello-ant"/>
<property name="build.dir" value="build"/>
```

Hai dòng trên khai báo:

| Tên property | Giá trị |
|---|---|
| `app.name` | `hello-ant` |
| `build.dir` | `build` |

Sau khi được khai báo, giá trị có thể được sử dụng ở nhiều vị trí trong buildfile. Thay vì lặp lại chuỗi `build`, ta tham chiếu property `build.dir`.

Property thường dùng để lưu:

- Tên ứng dụng, tên module hoặc phiên bản phát hành.
- Đường dẫn source, resource, thư mục build và thư mục phân phối.
- Tên file JAR hoặc WAR đầu ra.
- Cấu hình môi trường như `dev`, `test`, `staging` hoặc `production`.
- Giá trị bật/tắt một hành vi, ví dụ `skip.tests` hoặc `debug.enabled`.
- Classpath, tên công cụ hoặc tham số được dùng ở nhiều target.

Property của Ant có giá trị dạng chuỗi. Một giá trị trông giống số, đường dẫn hoặc Boolean vẫn được lưu dưới dạng văn bản; task nhận giá trị sẽ diễn giải nó theo yêu cầu riêng.

## 2. Khai báo property bằng name và value

Cách khai báo cơ bản nhất là dùng task `property` với hai thuộc tính `name` và `value`:

```xml
<property name="app.name" value="hello-ant"/>
<property name="app.version" value="1.0.0"/>
<property name="environment" value="development"/>
```

- `name` là tên dùng để tham chiếu property.
- `value` là giá trị dạng chuỗi được gán cho tên đó.

Tên property thường được đặt theo quy ước có dấu chấm để thể hiện nhóm cấu hình, ví dụ `app.name`, `src.dir`, `build.classes.dir`. Dấu chấm chỉ giúp tổ chức tên dễ đọc; nó không tạo ra một cấu trúc object hoặc namespace riêng trong Ant.

Tên property phân biệt chữ hoa và chữ thường. Ví dụ `app.name` và `APP.NAME` là hai tên khác nhau. Vì vậy, nên chọn một kiểu đặt tên nhất quán và dùng chính xác cùng cách viết ở nơi khai báo và nơi tham chiếu.

### 2.1. Khai báo property trong project

Task `property` thường được đặt ở cấp project, bên ngoài các target, để giá trị có sẵn cho những target trong file build:

```xml
<project name="hello-ant" default="compile" basedir=".">

    <property name="app.name" value="hello-ant"/>
    <property name="src.dir" value="src/main/java"/>
    <property name="build.dir" value="build"/>

    <target name="compile">
        <echo message="Building ${app.name}"/>
    </target>

</project>
```

Khi Ant nạp buildfile, các task cấu hình ở cấp project được xử lý trước khi chạy target. Vì vậy, target `compile` có thể tham chiếu `${app.name}`.

Property cũng có thể được khai báo bên trong target. Trong trường hợp đó, task `property` chỉ được thực hiện khi target chạy. Tuy nhiên, do property của Ant có tính bất biến, việc đặt property trong target không biến nó thành một biến cục bộ có thể thay đổi mỗi lần target chạy. Khi tổ chức cấu hình chung, đặt các property ở đầu project thường giúp người đọc dễ hiểu thứ tự và phạm vi sử dụng hơn.

## 3. Tham chiếu property bằng cú pháp ${...}

Sau khi khai báo property tên `build.dir`, ta tham chiếu giá trị của nó bằng cú pháp:

```text
${build.dir}
```

Phần nằm giữa `${` và `}` là tên property. Ant thay biểu thức này bằng giá trị hiện tại của property khi xử lý nội dung buildfile có hỗ trợ property expansion.

Ví dụ:

```xml
<project name="hello-ant" default="prepare">
    <property name="app.name" value="hello-ant"/>
    <property name="build.dir" value="build"/>

    <target name="prepare">
        <mkdir dir="${build.dir}"/>
        <echo message="Preparing ${app.name} in ${build.dir}"/>
    </target>
</project>
```

Khi chạy target `prepare`, Ant xử lý các tham chiếu và thực hiện các thao tác tương ứng với những giá trị đã khai báo. Với cấu hình trên, thư mục `build` được tạo và thông báo có nội dung tương ứng với tên ứng dụng cùng thư mục build.

### 3.1. Tham chiếu trong thuộc tính XML

Property expansion thường được dùng trong giá trị thuộc tính của task:

```xml
<property name="src.dir" value="src/main/java"/>
<property name="classes.dir" value="build/classes"/>

<target name="compile">
    <javac srcdir="${src.dir}" destdir="${classes.dir}"/>
</target>
```

`javac` nhận giá trị từ property để biết thư mục source và thư mục đầu ra. Khi cần thay đổi đường dẫn, ta sửa khai báo property hoặc truyền giá trị từ bên ngoài thay vì sửa từng task.

### 3.2. Tham chiếu trong nội dung task

Property cũng có thể xuất hiện trong nội dung của một số task, ví dụ `echo`:

```xml
<property name="release.version" value="2.4.0"/>

<target name="show-version">
    <echo message="Release version: ${release.version}"/>
</target>
```

Khi target chạy, Ant in ra giá trị của property. Đây là cách đơn giản để quan sát cấu hình trong quá trình build.

### 3.3. Kết hợp nhiều property

Một property có thể tham chiếu các property khác:

```xml
<property name="build.dir" value="build"/>
<property name="classes.dir" value="${build.dir}/classes"/>
<property name="reports.dir" value="${build.dir}/reports"/>
<property name="jar.file" value="${build.dir}/dist/hello-ant.jar"/>
```

Các giá trị sau được xây dựng từ `build.dir`. Nếu `build.dir` đã có giá trị `build`, thì `classes.dir` nhận `build/classes`, `reports.dir` nhận `build/reports`, và `jar.file` nhận `build/dist/hello-ant.jar`.

Đây là cách tạo một cấu hình có quan hệ rõ ràng: thay đổi thư mục gốc có thể làm thay đổi nhiều đường dẫn phụ thuộc.

## 4. Khai báo property cho đường dẫn bằng location

Khi property biểu diễn đường dẫn file hoặc thư mục, Ant cung cấp thuộc tính `location`:

```xml
<property name="src.dir" location="src/main/java"/>
<property name="build.dir" location="build"/>
<property name="classes.dir" location="${build.dir}/classes"/>
```

`location` biểu diễn vị trí file hoặc thư mục. Đường dẫn tương đối được phân giải theo project basedir và giá trị được chuẩn hóa thành đường dẫn tuyệt đối. Điều này hữu ích khi task cần một vị trí file rõ ràng.

Ví dụ:

```xml
<project name="hello-ant" basedir=".">
    <property name="src.dir" location="src/main/java"/>
    <property name="build.dir" location="build"/>

    <target name="show-paths">
        <echo message="Source: ${src.dir}"/>
        <echo message="Build: ${build.dir}"/>
    </target>
</project>
```

Nếu project nằm tại `/workspace/hello-ant`, các property được khai báo bằng `location` sẽ biểu diễn các vị trí tương ứng dưới thư mục dự án đó. Trên Windows, Ant trả về đường dẫn theo dạng phù hợp với hệ điều hành.

### 4.1. Phân biệt value và location

Hai thuộc tính này đều có thể dùng để khai báo property nhưng ý nghĩa khác nhau:

| Cách khai báo | Cách hiểu |
|---|---|
| `<property name="build.dir" value="build"/>` | Giá trị chuỗi là `build` |
| `<property name="build.dir" location="build"/>` | Vị trí thư mục `build`, được phân giải thành đường dẫn tuyệt đối theo basedir |

Nếu task nhận một đường dẫn, `location` thường diễn đạt ý định rõ ràng hơn. Nếu property là tên môi trường, tên artifact hoặc một giá trị văn bản khác, dùng `value`.

Không khai báo cả `value` và `location` cho cùng một property với mong muốn hai giá trị được kết hợp. Property chỉ được thiết lập một lần; khai báo thành công đầu tiên sẽ quyết định giá trị.

## 5. Thứ tự khai báo và mở rộng property

Ant xử lý property theo thứ tự. Khi một property được đặt giá trị, các tham chiếu property trong giá trị đó được mở rộng dựa trên những property đã có tại thời điểm thiết lập.

Ví dụ đúng:

```xml
<property name="build.dir" value="build"/>
<property name="classes.dir" value="${build.dir}/classes"/>
```

`build.dir` được khai báo trước, vì vậy khi Ant thiết lập `classes.dir`, biểu thức `${build.dir}` đã có thể được thay bằng `build`.

Nếu đảo thứ tự:

```xml
<property name="classes.dir" value="${build.dir}/classes"/>
<property name="build.dir" value="build"/>
```

thì tại thời điểm thiết lập `classes.dir`, `build.dir` chưa có giá trị. Ant không tự động tính lại mọi property đã được thiết lập trước đó khi một property khác xuất hiện về sau. Tham chiếu chưa giải quyết có thể còn nguyên dưới dạng `${build.dir}` và dẫn đến đường dẫn hoặc tham số không như mong muốn.

Vì vậy, nên khai báo theo thứ tự từ giá trị gốc đến giá trị dẫn xuất:

```xml
<property name="project.name" value="hello-ant"/>
<property name="build.dir" location="build"/>
<property name="classes.dir" location="${build.dir}/classes"/>
<property name="jar.file" location="${build.dir}/dist/${project.name}.jar"/>
```

Trong ví dụ này, các giá trị cơ sở được thiết lập trước, sau đó mới dùng chúng để xây dựng các đường dẫn cụ thể.

## 6. Property có tính bất biến: giá trị đầu tiên được giữ lại

Một quy tắc rất quan trọng của Ant là **property bất biến (immutable)**: khi một property đã được thiết lập, các lần khai báo sau với cùng tên sẽ không ghi đè giá trị đó.

Ví dụ:

```xml
<property name="environment" value="development"/>
<property name="environment" value="production"/>

<echo message="Environment: ${environment}"/>
```

Trong trường hợp này, `environment` giữ giá trị `development`, vì đó là giá trị được thiết lập đầu tiên. Dòng khai báo thứ hai không thay thế nó bằng `production`.

Tính bất biến giúp build có cấu hình ổn định trong suốt một lượt chạy. Một target không thể vô tình thay đổi property chung rồi làm các target phía sau nhận một cấu hình khác.

### 6.1. Truyền giá trị từ dòng lệnh bằng -D

Ta có thể truyền property khi gọi Ant:

```bash
ant -Denvironment=production jar
```

Trong buildfile:

```xml
<property name="environment" value="development"/>

<target name="show-env">
    <echo message="Environment: ${environment}"/>
</target>
```

Giá trị do `-D` truyền vào được thiết lập trước khi buildfile xử lý các task property thông thường. Vì vậy, khai báo mặc định trong file không ghi đè được giá trị `production` từ dòng lệnh.

Đây là mẫu thường dùng để đặt giá trị mặc định nhưng vẫn cho phép người chạy build lựa chọn cấu hình:

```xml
<property name="environment" value="development"/>
<property name="build.dir" value="build/${environment}"/>
```

Chạy:

```bash
ant show-env
ant -Denvironment=staging show-env
ant -Denvironment=production show-env
```

Lần đầu dùng mặc định `development`. Hai lệnh sau dùng giá trị do người gọi truyền vào. Trong ví dụ này, property `environment` được quyết định trước khi các property phụ thuộc được thiết lập.

### 6.2. Vì sao khai báo mặc định nên đặt sau cấu hình có thể ghi đè?

Do property chỉ được thiết lập một lần, thứ tự nạp cấu hình ảnh hưởng đến khả năng cung cấp giá trị mặc định.

Ví dụ, file `build.properties`:

```properties
environment=staging
build.dir=out
```

Buildfile:

```xml
<project name="hello-ant" default="show-config">
    <property file="build.properties"/>

    <!-- Chỉ đặt mặc định nếu file chưa cung cấp giá trị. -->
    <property name="environment" value="development"/>
    <property name="build.dir" value="build"/>

    <target name="show-config">
        <echo message="Environment: ${environment}"/>
        <echo message="Build directory: ${build.dir}"/>
    </target>
</project>
```

Vì file `build.properties` được đọc trước, `environment` nhận `staging` và `build.dir` nhận `out`. Các dòng khai báo mặc định phía sau không ghi đè các giá trị đó. Nếu file không cung cấp một property, dòng mặc định tương ứng mới thiết lập nó.

## 7. Đọc property từ file cấu hình

Khi có nhiều giá trị cần thay đổi theo máy hoặc môi trường, có thể tách chúng khỏi `build.xml` và đặt trong file `.properties`.

Ví dụ cấu trúc:

```text
hello-ant/
├── build.xml
├── build.properties
└── src/
```

Nội dung `build.properties`:

```properties
app.name=hello-ant
app.version=1.2.0
environment=development
build.dir=build
```

Nạp file bằng task `property`:

```xml
<property file="build.properties"/>
```

Sau đó có thể tham chiếu:

```xml
<echo message="${app.name} version ${app.version}"/>
<mkdir dir="${build.dir}"/>
```

Đường dẫn file tương đối trong thuộc tính `file` được phân giải theo project basedir. Nếu file nằm ở vị trí khác, hãy chỉ rõ đường dẫn phù hợp.

### 7.1. Dùng file cấu hình làm giá trị mặc định

Một cách tổ chức thường gặp là:

1. Nạp file properties có thể chứa cấu hình của nhóm hoặc môi trường.
2. Đặt các property mặc định bằng task `property` sau đó.
3. Dùng các property đã có để khai báo đường dẫn dẫn xuất và cấu hình task.

Ví dụ:

```xml
<property file="build.properties"/>

<property name="environment" value="development"/>
<property name="build.dir" value="build"/>
<property name="classes.dir" location="${build.dir}/classes"/>
```

Thứ tự này tận dụng tính chất first-wins: file có thể cung cấp giá trị, còn buildfile bổ sung mặc định cho những giá trị chưa được cung cấp.

## 8. Lấy giá trị từ biến môi trường

Ant có thể đọc các biến môi trường của hệ điều hành bằng thuộc tính `environment`:

```xml
<property environment="env"/>
```

Với prefix `env`, các biến môi trường được đưa vào Ant property theo dạng `env.TEN_BIEN`. Ví dụ:

```xml
<echo message="Java home: ${env.JAVA_HOME}"/>
<echo message="User profile: ${env.USERPROFILE}"/>
```

Tên biến thực tế phụ thuộc hệ điều hành. Windows thường có các biến như `JAVA_HOME`, `USERPROFILE`; Linux và macOS thường có `JAVA_HOME`, `HOME`, `USER`. Hãy dùng đúng tên biến tồn tại trong môi trường đang chạy.

Lệnh kiểm tra biến môi trường ở shell:

```powershell
# PowerShell
$env:JAVA_HOME
$env:USERPROFILE
```

```bat
:: Command Prompt
echo %JAVA_HOME%
echo %USERPROFILE%
```

```bash
# Linux/macOS
printf '%s\n' "$JAVA_HOME"
printf '%s\n' "$HOME"
```

Đọc biến môi trường không có nghĩa Ant thay đổi biến của hệ điều hành. Task `property environment="env"` chỉ đưa các giá trị môi trường hiện có vào hệ thống property của project.

## 9. Một số property có sẵn của Ant và Java

Ant và JVM cung cấp một số property hệ thống hữu ích mà người viết build không cần tự khai báo.

| Property | Thông tin |
|---|---|
| `basedir` | Thư mục gốc của project Ant |
| `ant.file` | Đường dẫn buildfile đang được Ant sử dụng |
| `ant.project.name` | Tên project được khai báo trong buildfile |
| `ant.version` | Phiên bản Ant |
| `ant.home` | Thư mục cài đặt Ant khi xác định được |
| `ant.java.version` | Phiên bản Java theo cách Ant nhận diện |
| `java.version` | Phiên bản Java runtime |
| `java.home` | Thư mục Java home của JVM |
| `os.name` | Tên hệ điều hành |
| `os.arch` | Kiến trúc hệ điều hành |
| `user.name` | Tên người dùng của tiến trình |
| `user.home` | Thư mục home của người dùng |
| `user.dir` | Thư mục làm việc hiện tại của JVM |
| `file.separator` | Ký tự phân cách thư mục của hệ điều hành |
| `path.separator` | Ký tự phân cách các phần tử trong path |

Ví dụ:

```xml
<target name="show-runtime">
    <echo message="Ant: ${ant.version}"/>
    <echo message="Project: ${ant.project.name}"/>
    <echo message="Java: ${java.version}"/>
    <echo message="OS: ${os.name} (${os.arch})"/>
    <echo message="Basedir: ${basedir}"/>
</target>
```

Các property này giúp buildfile điều chỉnh hành vi hoặc ghi log theo môi trường. Không nên khai báo lại chúng chỉ để thay đổi giá trị; một số property được Ant hoặc JVM thiết lập sẵn và property của Ant tuân theo quy tắc first-wins.

## 10. Property trong một ví dụ buildfile hoàn chỉnh

Ví dụ sau kết hợp property trong file, property mặc định, đường dẫn `location`, property từ dòng lệnh và tham chiếu `${...}`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="hello-ant" default="jar" basedir=".">

    <!-- Nạp cấu hình nếu file tồn tại. -->
    <property file="build.properties"/>

    <!-- Giá trị mặc định: chỉ có tác dụng nếu chưa được thiết lập. -->
    <property name="app.name" value="hello-ant"/>
    <property name="app.version" value="1.0.0"/>
    <property name="build.dir" value="build"/>

    <!-- Giá trị dẫn xuất được khai báo sau các giá trị gốc. -->
    <property name="src.dir" location="src/main/java"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="dist.dir" location="${build.dir}/dist"/>
    <property name="jar.file" location="${dist.dir}/${app.name}-${app.version}.jar"/>

    <target name="show-config">
        <echo message="Application: ${app.name}"/>
        <echo message="Version: ${app.version}"/>
        <echo message="Source: ${src.dir}"/>
        <echo message="Classes: ${classes.dir}"/>
        <echo message="JAR: ${jar.file}"/>
    </target>

    <target name="prepare">
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${dist.dir}"/>
    </target>

    <target name="compile" depends="prepare">
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               encoding="UTF-8"
               includeantruntime="false"/>
    </target>

    <target name="jar" depends="compile">
        <jar destfile="${jar.file}" basedir="${classes.dir}"/>
    </target>

</project>
```

Giả sử `build.properties` có nội dung:

```properties
app.version=2.3.0
build.dir=out
```

Khi chạy:

```bash
ant show-config
```

Ant nạp các giá trị từ file, bổ sung mặc định cho property chưa được thiết lập và in cấu hình. Khi chạy:

```bash
ant -Dapp.version=3.0.0 -Dbuild.dir=release jar
```

Các user property từ dòng lệnh đã có trước khi buildfile xử lý, nên chúng được giữ lại thay cho giá trị cùng tên trong file properties. Những property dẫn xuất được thiết lập sau đó sẽ dùng các giá trị đã được quyết định này.

Ví dụ trên minh họa cách tổ chức cấu hình. Để build thành công, dự án phải có source Java hợp lệ; nếu cần dependency ngoài, classpath của task `javac` cũng phải được cấu hình.

## 11. Lỗi thường gặp khi dùng property

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
|---|---|---|
| Log vẫn in `${app.name}` | Property chưa được khai báo, khai báo sai tên hoặc được đặt sau thời điểm tham chiếu | Kiểm tra chính tả và thứ tự khai báo |
| Đã khai báo giá trị mới nhưng property không đổi | Property đã được thiết lập trước đó | Tìm nơi thiết lập đầu tiên, kiểm tra `-D` và thứ tự nạp file |
| Đường dẫn bị lặp hoặc sai thư mục | Dùng `value` như chuỗi đường dẫn hoặc tính sai basedir | Kiểm tra `location`, `basedir` và cách ghép đường dẫn |
| File properties không được nạp | Đường dẫn `file` tương đối không tính từ thư mục dự kiến hoặc file không tồn tại | Kiểm tra basedir và đường dẫn file |
| Biến môi trường không có giá trị | Chưa khai báo `environment` prefix hoặc tên biến không đúng | Dùng `<property environment="env"/>` và kiểm tra tên biến của OS |
| Property từ `-D` không có tác dụng như mong muốn | Property đã được dẫn xuất trước khi tham số được áp dụng ở một cơ chế gọi khác hoặc script không truyền tham số đến Ant | Kiểm tra lệnh Ant thực tế và thứ tự thiết lập |
| Hai tên gần giống nhưng kết quả khác nhau | Property phân biệt hoa thường | Chuẩn hóa tên property và tham chiếu |

### 11.1. Tham chiếu chưa được định nghĩa

Ví dụ:

```xml
<property name="classes.dir" value="${build.dir}/classes"/>
<property name="build.dir" value="build"/>
```

`build.dir` chưa có giá trị khi Ant xử lý khai báo đầu tiên. Kết quả dẫn xuất vì vậy không như mong muốn. Hãy đảo thứ tự:

```xml
<property name="build.dir" value="build"/>
<property name="classes.dir" value="${build.dir}/classes"/>
```

### 11.2. Muốn ghi đè property đã được thiết lập

Ví dụ:

```xml
<property name="environment" value="development"/>
<property name="environment" value="production"/>
```

Giá trị đầu tiên vẫn được giữ. Nếu cần chọn môi trường theo lần chạy, hãy để property mặc định trong buildfile và truyền giá trị bằng `-D`:

```bash
ant -Denvironment=production jar
```

Đây là cách cấu hình rõ ràng, dễ ghi lại trong script và CI.

### 11.3. Nhầm property Ant với biến môi trường

Khai báo:

```xml
<property name="JAVA_HOME" value="C:/tools/jdk"/>
```

chỉ tạo property tên `JAVA_HOME` bên trong Ant project. Nó không thay đổi biến môi trường `JAVA_HOME` của hệ điều hành và cũng không cập nhật `PATH` cho terminal. Nếu cần đọc biến môi trường, dùng `environment`; nếu cần cấu hình launcher Java, hãy thiết lập môi trường bên ngoài theo đúng cách của hệ điều hành.

## 12. Nguyên tắc tổ chức property dễ bảo trì

- Đặt các property cấu hình ở đầu buildfile, trước những target cần sử dụng chúng.
- Đặt tên có ý nghĩa và nhất quán, ví dụ `src.dir`, `build.dir`, `dist.dir`, `app.version`.
- Khai báo giá trị gốc trước, giá trị dẫn xuất sau.
- Dùng `location` cho đường dẫn file/thư mục và `value` cho giá trị văn bản.
- Tách cấu hình có thể thay đổi theo môi trường vào file `.properties` khi phù hợp.
- Đặt giá trị mặc định sau khi nạp cấu hình có thể ghi đè.
- Dùng `-Dname=value` để truyền cấu hình theo từng lần gọi Ant.
- Nhớ rằng property là bất biến; không thiết kế target dựa trên giả định rằng khai báo sau sẽ thay thế giá trị trước.
- Tránh đưa mật khẩu, token hoặc bí mật vào buildfile và file properties được commit. Nếu cần bí mật, dùng cơ chế secret của môi trường chạy CI và giới hạn việc in giá trị ra log.

## 13. Kết luận

Task `property` cho phép đặt tên cho giá trị cấu hình trong Ant. Cú pháp `${property.name}` tham chiếu giá trị đó ở những thuộc tính hoặc nội dung task có hỗ trợ property expansion. Với đường dẫn, `location` giúp phân giải vị trí theo project basedir; với giá trị văn bản, `value` là lựa chọn trực tiếp. Property cũng có thể được nạp từ file, đọc từ biến môi trường hoặc truyền qua dòng lệnh bằng `-D`.

Quy tắc cần nhớ nhất là property của Ant bất biến: giá trị được thiết lập đầu tiên sẽ được giữ lại. Vì thế, hãy tổ chức thứ tự khai báo từ giá trị gốc đến giá trị dẫn xuất, nạp cấu hình trước khi đặt mặc định và truyền tham số từ dòng lệnh khi cần thay đổi môi trường. Cách tổ chức này làm buildfile dễ đọc, dễ tái sử dụng và ít phát sinh lỗi cấu hình.
