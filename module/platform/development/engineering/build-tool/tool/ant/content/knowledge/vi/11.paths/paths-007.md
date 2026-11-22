# Kiểm soát `CLASSPATH`, `-noclasspath` và `-nouserlib`

Khi khởi động Apache Ant, bộ nạp lớp của Ant có thể nhận thư viện từ nhiều nguồn, trong đó có biến môi trường `CLASSPATH` và thư mục thư viện riêng của người dùng `~/.ant/lib`. Những thư viện này có thể cung cấp custom task, datatype hoặc thư viện bổ trợ cho build. Tuy nhiên, chúng cũng có thể làm build phụ thuộc vào cấu hình riêng của từng máy và gây ra lỗi khó tái hiện.

Ant cung cấp hai tùy chọn dòng lệnh để kiểm soát hai nguồn đó:

- `-noclasspath`: yêu cầu Ant launcher bỏ qua biến môi trường `CLASSPATH` khi thiết lập classpath của Ant.
- `-nouserlib`: yêu cầu Ant không nạp các JAR trong thư mục thư viện riêng của người dùng, thường là `${user.home}/.ant/lib`.

Hai tùy chọn này hữu ích khi cần kiểm tra build trong môi trường sạch hơn, tìm dependency bị ẩn trên máy phát triển hoặc giảm ảnh hưởng từ thư viện cài đặt toàn cục. Chúng kiểm soát classpath dùng để khởi chạy Ant; chúng không xóa biến môi trường khỏi hệ điều hành và cũng không tự xóa classpath mà dự án khai báo riêng cho compiler hoặc ứng dụng.

## 1. Phân biệt các nguồn classpath

Classpath là danh sách các thư mục và tệp JAR mà Java dùng để tìm lớp và tài nguyên. Trong một dự án Ant, có nhiều classpath với phạm vi khác nhau.

| Nguồn | Mục đích | Ví dụ |
|---|---|---|
| `CLASSPATH` của môi trường | Cung cấp classpath qua môi trường cho tiến trình khởi chạy | `CLASSPATH=lib/tool.jar;lib/extra.jar` trên Windows |
| Thư viện người dùng của Ant | Cung cấp JAR dùng chung cho Ant của một người dùng | `~/.ant/lib/custom-task.jar` |
| Thư viện cài đặt Ant | Chứa thư viện lõi và thư viện bổ trợ được cài cùng Ant | `${ANT_HOME}/lib` |
| `-lib` trên dòng lệnh | Thêm đường dẫn thư viện tường minh cho Ant launcher | `ant -lib lib/ant-tasks.jar ...` |
| Classpath của task trong build file | Cung cấp lớp cho compiler, JVM ứng dụng hoặc custom task theo cấu hình task | `<javac><classpath>...</classpath></javac>` |

`-noclasspath` và `-nouserlib` chỉ tác động đến hai nguồn đầu tiên trong bảng. Chúng không có nghĩa là Ant khởi động mà không có bất kỳ thư viện nào. Ant vẫn cần thư viện lõi của chính nó và có thể sử dụng các đường dẫn được cấu hình tường minh ở những nơi khác.

### 1.1. Classpath của Ant launcher

Ant launcher cần tìm các lớp của Ant và những task hoặc thư viện được nạp ở cấp Ant. Các JAR trong thư viện cài đặt Ant, thư viện người dùng, biến `CLASSPATH` và các đường dẫn được thêm bằng `-lib` có thể tham gia vào quá trình này.

Nếu máy phát triển có cài một custom task trong thư viện dùng chung, build file có thể chạy thành công trên máy đó dù repository không khai báo dependency của task. Máy CI hoặc máy đồng nghiệp không có JAR ấy sẽ báo không tìm thấy task hoặc class.

Đây là dạng phụ thuộc môi trường ẩn. Chạy Ant với `-noclasspath` và `-nouserlib` giúp kiểm tra xem build có vô tình dựa vào hai nguồn cấu hình cá nhân này hay không.

### 1.2. Classpath của compiler và ứng dụng

Classpath của `<javac>` xác định thư viện mà compiler cần để biên dịch mã nguồn. Classpath của task `<java>` hoặc một chương trình Java được fork xác định lớp mà ứng dụng cần khi chạy.

Ví dụ classpath biên dịch được khai báo trực tiếp trong build file:

```xml
<path id="compile.classpath">
    <fileset dir="lib">
        <include name="*.jar"/>
    </fileset>
</path>

<target name="compile">
    <mkdir dir="build/classes"/>
    <javac srcdir="src/main/java"
           destdir="build/classes"
           includeantruntime="false">
        <classpath refid="compile.classpath"/>
    </javac>
</target>
```

Đường dẫn `compile.classpath` là cấu hình của task compiler trong build file. Chạy `ant -noclasspath` không xóa `lib/*.jar` khỏi path này. Nếu compiler cần thư viện trong `lib`, task vẫn có thể sử dụng chúng khi Ant được khởi chạy với `-noclasspath`.

Tương tự, các classpath được khai báo trong task `<java>`, `<junit>` hoặc task khác có phạm vi riêng không bị hai switch này tự động loại bỏ.

## 2. Biến môi trường `CLASSPATH`

`CLASSPATH` là biến môi trường có thể chứa một hoặc nhiều thư mục và JAR để Java tìm lớp. Ant launcher có thể sử dụng biến này khi khởi tạo classpath của Ant.

Ví dụ một biến môi trường có thể chứa:

```text
CLASSPATH=lib/custom-ant-task.jar;lib/legacy-helper.jar
```

Trên Windows, dấu phân cách các mục thường là dấu chấm phẩy (`;`). Trên Linux và macOS, dấu phân cách thường là dấu hai chấm (`:`):

```bash
CLASSPATH=lib/custom-ant-task.jar:lib/legacy-helper.jar
```

Nếu `CLASSPATH` được đặt toàn cục, mọi tiến trình được khởi chạy từ môi trường đó có thể kế thừa giá trị. Điều này có thể làm các công cụ dùng những phiên bản thư viện khác nhau hoặc vô tình tải một lớp từ vị trí không được dự án quản lý.

### 2.1. Kiểm tra giá trị `CLASSPATH`

Trên Windows PowerShell:

```powershell
$env:CLASSPATH
```

Trên Windows Command Prompt:

```bat
echo %CLASSPATH%
```

Trên Linux hoặc macOS:

```bash
printf '%s\n' "$CLASSPATH"
```

Nếu biến không được đặt, kết quả có thể rỗng. Điều đó không nhất thiết là lỗi: nhiều dự án Ant không cần biến môi trường `CLASSPATH` vì build file tự khai báo các thư viện cần thiết.

### 2.2. Bỏ qua `CLASSPATH` khi khởi chạy Ant

Dùng `-noclasspath` trước tên target:

```bash
ant -noclasspath compile
```

Ant launcher bỏ qua biến môi trường `CLASSPATH` khi xây dựng classpath của Ant. Tùy chọn này giúp xác định xem một custom task hoặc thư viện có đang được cung cấp ngầm từ biến môi trường hay không.

Có thể dùng với một build file cụ thể:

```bash
ant -noclasspath -f build.xml compile
```

Tùy chọn này không xóa `CLASSPATH` khỏi môi trường của tiến trình Ant và không ngăn các tiến trình con được khởi chạy sau đó kế thừa biến môi trường ấy. Nó chỉ yêu cầu Ant launcher không dùng biến đó làm nguồn classpath của Ant.

## 3. Thư viện người dùng của Ant và `-nouserlib`

Ant có thư mục thư viện riêng cho từng người dùng, mặc định là `.ant/lib` bên dưới thư mục home của người dùng:

| Hệ điều hành | Vị trí thường gặp |
|---|---|
| Windows | `%USERPROFILE%\.ant\lib` |
| Linux | `$HOME/.ant/lib` |
| macOS | `$HOME/.ant/lib` |

JAR đặt trong thư mục này có thể được Ant nạp để cung cấp custom task hoặc thư viện dùng chung cho nhiều dự án. Cách cài đặt đó thuận tiện cho một máy cá nhân, nhưng build có thể phụ thuộc vào JAR mà những máy khác không có.

### 3.1. Bỏ qua thư viện người dùng

Dùng tùy chọn `-nouserlib`:

```bash
ant -nouserlib compile
```

Ant không nạp các JAR trong thư mục thư viện người dùng mặc định. Nếu build cần custom task chỉ được cài trong thư mục này, Ant có thể báo không tìm thấy task hoặc class.

Tùy chọn này không xóa hoặc sửa các JAR trong `.ant/lib`. Nó chỉ thay đổi cách Ant khởi chạy trong lần gọi hiện tại. Các thư viện lõi trong `${ANT_HOME}/lib` vẫn thuộc bản cài đặt Ant và không bị `-nouserlib` loại bỏ.

### 3.2. Khi nào nên dùng thư viện người dùng?

Thư mục `.ant/lib` có thể phù hợp cho công cụ phát triển cá nhân hoặc các task dùng chung trong một môi trường được quản lý. Tuy nhiên, với build cần chạy nhất quán trên máy của nhiều thành viên hoặc trên CI, dependency nên được khai báo và quản lý rõ trong dự án hoặc trong cấu hình môi trường build đã được chuẩn hóa.

Nếu một custom task chỉ tồn tại trong `.ant/lib`, hãy xem đó là dependency cần được tài liệu hóa và cung cấp theo cách có thể tái lập. Không nên yêu cầu mọi thành viên tự cài một JAR không được quản lý mà không ghi lại phiên bản và nguồn tải.

## 4. Dùng hai tùy chọn cùng nhau

`-noclasspath` và `-nouserlib` giải quyết hai nguồn classpath khác nhau. Có thể kết hợp chúng để kiểm tra build mà không dùng `CLASSPATH` của môi trường hoặc thư viện người dùng:

```bash
ant -noclasspath -nouserlib clean compile
```

Hoặc chỉ định build file:

```bash
ant -noclasspath -nouserlib -f build.xml compile
```

Lệnh này hữu ích khi kiểm tra xem build có phụ thuộc vào thư viện cài đặt cá nhân hay không. Nếu lệnh thông thường chạy được nhưng lệnh có hai switch thất bại, hãy tìm custom task hoặc dependency đang được cung cấp từ `CLASSPATH` hoặc `${user.home}/.ant/lib`.

### 4.1. Bảng hành vi của từng tùy chọn

| Lệnh | `CLASSPATH` môi trường | `${user.home}/.ant/lib` | Thư viện Ant trong `${ANT_HOME}/lib` |
|---|---|---|---|
| `ant compile` | Có thể được launcher sử dụng | Được nạp theo cấu hình mặc định | Được nạp |
| `ant -noclasspath compile` | Bị bỏ qua bởi launcher | Vẫn được nạp | Được nạp |
| `ant -nouserlib compile` | Vẫn có thể được launcher sử dụng | Bị bỏ qua | Được nạp |
| `ant -noclasspath -nouserlib compile` | Bị bỏ qua bởi launcher | Bị bỏ qua | Được nạp |

Các đường dẫn được thêm tường minh bằng `-lib` và classpath được khai báo riêng trong build file là các cơ chế khác. Không nên diễn giải hai switch này thành chế độ không có bất kỳ thư viện ngoài nào.

## 5. Kiểm tra build có phụ thuộc thư viện cá nhân hay không

Một cách thực tế để tìm dependency ẩn là so sánh kết quả chạy thông thường với kết quả chạy trong chế độ bỏ qua hai nguồn cá nhân.

Giả sử build thông thường chạy được:

```bash
ant clean compile
```

Sau đó chạy:

```bash
ant -noclasspath -nouserlib clean compile
```

Nếu cả hai lệnh đều thành công, build không cần hai nguồn classpath đó cho các target vừa chạy. Đây là dấu hiệu tốt, nhưng không chứng minh build hoàn toàn độc lập với mọi cấu hình bên ngoài: Ant vẫn sử dụng thư viện trong bản cài đặt, các đường dẫn `-lib`, classpath khai báo trong task và những công cụ có sẵn trên máy.

Nếu lệnh thứ hai thất bại, hãy đọc lỗi đầu tiên và xác định loại lớp hoặc task không được tìm thấy. Ví dụ:

| Thông báo lỗi | Khả năng cần kiểm tra |
|---|---|
| Không tìm thấy task custom | Task có thể đang được nạp từ `CLASSPATH` hoặc `.ant/lib` |
| `ClassNotFoundException` khi chạy task | Thư viện chứa class cần thiết có thể chỉ có trong một nguồn bị bỏ qua |
| `NoClassDefFoundError` | Một class mà task hoặc custom task phụ thuộc không có trong classloader thích hợp |
| Compiler không tìm thấy package của ứng dụng | Kiểm tra classpath riêng của `<javac>`, không kết luận ngay rằng `-noclasspath` đã xóa nó |

Để xác định nguồn, chạy Ant với thông tin chẩn đoán:

```bash
ant -diagnostics
```

Có thể dùng thêm `-verbose` hoặc `-debug` khi cần quan sát quá trình khởi động và nạp task:

```bash
ant -verbose -noclasspath -nouserlib compile
```

Thông tin chẩn đoán có thể chứa đường dẫn máy cá nhân. Hãy xem lại trước khi chia sẻ log công khai.

## 6. Khai báo dependency rõ ràng cho custom task

Nếu build sử dụng custom Ant task, hãy cung cấp thư viện của task theo cách có thể tái lập thay vì chỉ dựa vào thư mục `.ant/lib` hoặc biến `CLASSPATH` của từng máy.

Ví dụ, đặt JAR custom task trong thư mục `lib/ant-tasks` của dự án:

```text
sample-project/
├── build.xml
├── lib/
│   └── ant-tasks/
│       └── company-ant-tasks.jar
└── src/
```

Khai báo path và task definition trong build file:

```xml
<path id="custom.tasks.classpath">
    <fileset dir="lib/ant-tasks">
        <include name="*.jar"/>
    </fileset>
</path>

<taskdef name="companyTask"
         classname="com.example.ant.CompanyTask"
         classpathref="custom.tasks.classpath"/>

<target name="run-company-task">
    <companyTask/>
</target>
```

`taskdef` dùng classpath được khai báo tường minh để nạp lớp thực thi task. Tên class và JAR ở ví dụ là minh họa; thay bằng API và thư viện thực tế của dự án.

Với cách khai báo này, dependency của custom task được lưu cùng dự án và có thể được kiểm soát phiên bản. Khi chạy:

```bash
ant -noclasspath -nouserlib run-company-task
```

Ant vẫn có thể nạp task qua classpath được khai báo trong build file, miễn là JAR và các dependency cần thiết được cung cấp đầy đủ, tương thích với phiên bản Ant và Java đang sử dụng.

Nếu chọn cung cấp thư viện qua `-lib`, hãy ghi rõ đường dẫn và phiên bản cần thiết trong tài liệu chạy build hoặc script CI. Không nên để một build chỉ hoạt động vì người dùng đã cài JAR thủ công mà không ai biết.

## 7. Phân biệt với `-lib` và classpath của task

Ngoài hai switch đang học, Ant còn có tùy chọn `-lib` để thêm đường dẫn thư viện cho Ant launcher. Ví dụ:

```bash
ant -lib lib/ant-tasks run-company-task
```

`-lib` là cách cung cấp đường dẫn một cách tường minh ở lần gọi Ant. Nó khác với việc dựa vào biến môi trường `CLASSPATH` hoặc thư mục `.ant/lib`.

| Cơ chế | Phạm vi ảnh hưởng |
|---|---|
| `-noclasspath` | Bỏ qua biến `CLASSPATH` khi launcher thiết lập classpath của Ant |
| `-nouserlib` | Bỏ qua JAR trong thư viện người dùng `${user.home}/.ant/lib` |
| `-lib` | Thêm đường dẫn thư viện cho Ant launcher |
| `<javac><classpath>` | Cung cấp dependency cho compiler trong target |
| `<java><classpath>` | Cung cấp lớp cho chương trình Java do task quản lý |
| `<taskdef classpathref="...">` | Cung cấp lớp triển khai custom task |

Không dùng `-noclasspath` để thay thế cấu hình `<javac><classpath>`, và không dùng `-nouserlib` để loại bỏ thư viện ứng dụng. Hai tùy chọn này chỉ kiểm soát nguồn thư viện khi Ant được khởi chạy.

## 8. Ảnh hưởng đến tiến trình con

`-noclasspath` yêu cầu Ant launcher không dùng biến `CLASSPATH` để tạo classpath của chính Ant. Nó không xóa biến `CLASSPATH` khỏi môi trường của tiến trình Ant.

Do đó, nếu build chạy một chương trình bên ngoài bằng task `<exec>`, chương trình con vẫn có thể kế thừa biến môi trường `CLASSPATH` từ Ant, tùy cách task và hệ điều hành tạo tiến trình. Nếu muốn kiểm soát môi trường của tiến trình con, hãy cấu hình rõ ràng phần tử `<env>` của task tương ứng.

Ví dụ:

```xml
<target name="run-external-tool">
    <exec executable="my-tool" failonerror="true">
        <env key="CLASSPATH" value="lib/tool-runtime.jar"/>
    </exec>
</target>
```

Đoạn cấu hình này đặt `CLASSPATH` cho tiến trình con được gọi bởi `<exec>`. Nó không thay đổi classpath dùng để tải Ant hoặc custom task trong tiến trình Ant hiện tại.

## 9. Ví dụ thực hành: kiểm tra build trong môi trường sạch hơn

Giả sử dự án có cấu trúc:

```text
sample-project/
├── build.xml
├── lib/
│   ├── app-api.jar
│   └── ant-tasks/
│       └── company-ant-tasks.jar
└── src/
    └── main/java/
```

Build file có thể khai báo classpath ứng dụng và custom task một cách rõ ràng:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="classpath-demo" default="compile" basedir=".">

    <path id="compile.classpath">
        <pathelement location="lib/app-api.jar"/>
    </path>

    <path id="custom.tasks.classpath">
        <fileset dir="lib/ant-tasks">
            <include name="*.jar"/>
        </fileset>
    </path>

    <taskdef name="companyTask"
             classname="com.example.ant.CompanyTask"
             classpathref="custom.tasks.classpath"/>

    <target name="compile">
        <mkdir dir="build/classes"/>
        <javac srcdir="src/main/java"
               destdir="build/classes"
               includeantruntime="false">
            <classpath refid="compile.classpath"/>
        </javac>
    </target>

    <target name="run-company-task" depends="compile">
        <companyTask/>
    </target>

</project>
```

Chạy build thông thường:

```bash
ant run-company-task
```

Sau đó thử bỏ qua hai nguồn thư viện cá nhân:

```bash
ant -noclasspath -nouserlib run-company-task
```

Nếu lệnh thứ hai thành công, Ant vẫn tìm thấy custom task qua `custom.tasks.classpath` và compiler vẫn tìm thấy API qua `compile.classpath`. Kết quả này cho thấy hai bước không cần dựa vào biến `CLASSPATH` hoặc JAR trong `.ant/lib`.

Ví dụ giả định JAR custom task chứa cả những dependency mà task cần, hoặc các dependency đó được khai báo bổ sung. Tên class `com.example.ant.CompanyTask` cũng phải khớp với lớp thật trong JAR. Build file thực tế cần cấu hình đủ mọi thư viện mà task và mã nguồn sử dụng.

## 10. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Build chạy bình thường nhưng thất bại với `-noclasspath` | Một task hoặc thư viện đang được cung cấp từ biến `CLASSPATH` | Xác định JAR cần thiết và khai báo rõ qua `taskdef`, path hoặc cấu hình Ant được quản lý |
| Build thất bại với `-nouserlib` | Custom task chỉ có trong `${user.home}/.ant/lib` | Đưa dependency vào dự án hoặc cung cấp qua cấu hình `-lib` được quản lý |
| Cả hai switch đều bật nhưng vẫn nạp thư viện lạ | Thư viện có thể đến từ `${ANT_HOME}/lib`, `-lib` hoặc classpath tường minh trong build | Kiểm tra nguồn nạp còn lại và chuẩn hóa bản cài đặt Ant |
| `<javac>` không tìm thấy package | Classpath của compiler thiếu thư viện | Khai báo nested `<classpath>` hoặc `classpathref` cho `<javac>` |
| Tiến trình ngoài vẫn nhìn thấy `CLASSPATH` | `-noclasspath` không xóa biến khỏi môi trường tiến trình | Kiểm soát môi trường con bằng cấu hình `<env>` hoặc cấu hình hệ điều hành phù hợp |
| Máy cá nhân chạy được, CI không chạy được | Máy cá nhân có JAR toàn cục mà CI không có | Khai báo dependency và phiên bản rõ ràng, chạy kiểm tra với hai switch trên CI |
| Không biết JAR đến từ đâu | Nhiều nguồn classpath cùng tham gia | Dùng `ant -diagnostics`, xem cấu hình launcher và kiểm tra từng nguồn thư viện |

## 11. Quy trình kiểm soát classpath đề xuất

Khi muốn build có thể tái lập trên nhiều máy, hãy thực hiện theo trình tự:

1. Xác định custom task và thư viện mà Ant cần để đọc build file hoặc thực thi task.
2. Xác định thư viện mà mã nguồn Java cần khi biên dịch và khi chạy ứng dụng.
3. Đưa dependency của dự án vào vị trí được quản lý hoặc khai báo đường dẫn rõ ràng bằng path và classpath của task.
4. Không dựa vào `CLASSPATH` toàn cục nếu dependency có thể được mô tả ngay trong dự án.
5. Chạy build với `-noclasspath -nouserlib` để phát hiện dependency cá nhân bị bỏ sót.
6. Kiểm tra log và `ant -diagnostics` nếu build thất bại, sau đó bổ sung đúng dependency còn thiếu.
7. Lặp lại lệnh kiểm tra trên môi trường CI hoặc máy sạch có cùng phiên bản Ant và JDK mục tiêu.

Hai switch này là công cụ chẩn đoán và kiểm soát nguồn classpath của Ant launcher. Chúng giúp làm rõ dependency nào đến từ môi trường cá nhân, còn dependency nào đã được dự án khai báo. Khi kết hợp với classpath tường minh cho compiler, ứng dụng và custom task, build file trở nên dễ chia sẻ và dễ tái lập hơn.
