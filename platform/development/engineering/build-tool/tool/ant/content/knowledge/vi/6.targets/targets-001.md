# Thiết kế target theo một trách nhiệm rõ ràng

Trong Apache Ant, target là một đơn vị công việc có tên trong build file. Một build file thường có nhiều target để thực hiện các giai đoạn như chuẩn bị thư mục, biên dịch mã nguồn, chạy kiểm thử, đóng gói và dọn kết quả cũ. Khi thiết kế target, hãy gom những task phục vụ cùng một mục tiêu vào một target và đặt tên thể hiện rõ mục tiêu đó.

Thiết kế mỗi target theo một trách nhiệm rõ ràng giúp build file dễ đọc, dễ gọi riêng từng công việc, dễ tìm lỗi và thuận tiện thay đổi quy trình khi dự án phát triển. Một target có thể chứa nhiều task; điều quan trọng là các task đó cùng phục vụ một kết quả có ý nghĩa.

## 1. Target là một đơn vị công việc

Target được khai báo bằng phần tử `<target>` trong `<project>`. Thuộc tính `name` đặt tên cho target, còn nội dung bên trong chứa các task mà Ant thực thi.

Ví dụ:

```xml
<target name="prepare">
    <mkdir dir="build"/>
    <mkdir dir="build/classes"/>
</target>
```

Target `prepare` có hai task `<mkdir>`, nhưng chúng cùng thực hiện một mục tiêu: chuẩn bị các thư mục cần thiết cho build. Đây vẫn là một trách nhiệm rõ ràng dù target chứa nhiều task.

Ngược lại, nếu một target vừa xóa dữ liệu cũ, biên dịch mã nguồn, chạy kiểm thử, đóng gói JAR, sao chép tài liệu và gửi thông báo, nó đang gom nhiều giai đoạn có mục đích khác nhau. Khi một bước thất bại hoặc cần chạy riêng một giai đoạn, người dùng khó xác định phần công việc cần gọi và khó biết target đang thay đổi những gì.

Có thể hiểu nguyên tắc thiết kế như sau:

- Một target đại diện cho một mục tiêu build có thể diễn đạt ngắn gọn bằng một động từ hoặc cụm động từ.
- Các task trong target cùng đóng góp vào mục tiêu đó.
- Những mục tiêu độc lập hoặc có thể được gọi riêng nên được tách thành các target riêng.
- Quan hệ giữa các giai đoạn được thể hiện bằng dependency thay vì sao chép task từ target này sang target khác.

## 2. Phân biệt trách nhiệm của target và task

Task là hành động cụ thể mà Ant thực thi, chẳng hạn `<mkdir>`, `<delete>`, `<javac>`, `<copy>` hoặc `<jar>`. Target là nhóm công việc được đặt tên để người dùng có thể yêu cầu Ant thực hiện.

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Task | Thực hiện một hành động cụ thể | `<mkdir dir="build"/>` tạo thư mục |
| Target | Gom các task cùng mục tiêu thành một đơn vị có tên | `prepare` chuẩn bị thư mục build |
| Dependency | Khai báo target cần hoàn thành trước target khác | `compile` phụ thuộc `prepare` |
| Orchestration target | Kết nối các giai đoạn thành quy trình cấp cao | `build` phụ thuộc `package` |

Không cần tạo một target riêng cho từng task. Ví dụ, hai lệnh tạo thư mục đầu ra và thư mục chứa class có thể nằm chung trong target `prepare`, vì cả hai cùng phục vụ việc chuẩn bị môi trường build.

```xml
<target name="prepare" description="Prepare build directories">
    <mkdir dir="build"/>
    <mkdir dir="build/classes"/>
    <mkdir dir="build/dist"/>
</target>
```

Tách target khi công việc có ý nghĩa độc lập. Ví dụ `clean` xóa kết quả cũ, `compile` biên dịch mã nguồn và `package` tạo gói phân phối. Người dùng có thể gọi từng target khi cần kiểm tra hoặc thực hiện riêng một giai đoạn.

## 3. Xác định ranh giới trách nhiệm

Trước khi viết target, hãy xác định đầu vào, hành động chính và kết quả mà target chịu trách nhiệm tạo ra. Một cách thực tế là diễn đạt mục tiêu bằng câu: “Target này chuẩn bị ...”, “Target này biên dịch ...” hoặc “Target này đóng gói ...”. Nếu phải dùng nhiều câu mô tả những kết quả không liên quan, có thể target đang chứa quá nhiều trách nhiệm.

### 3.1. Các target thường gặp

| Target | Trách nhiệm chính | Công việc thường nằm bên trong |
|---|---|---|
| `clean` | Xóa kết quả build được tạo ra trước đó | Xóa thư mục `build` hoặc thư mục đầu ra đã cấu hình |
| `prepare` | Chuẩn bị cấu trúc thư mục hoặc tài nguyên đầu vào | Tạo thư mục class, thư mục phân phối, sao chép cấu hình cần thiết |
| `compile` | Biên dịch mã nguồn | Gọi `<javac>` với source directory, destination và classpath |
| `test` | Chạy kiểm thử tự động | Gọi test runner hoặc task kiểm thử đã được cấu hình |
| `package` | Tạo gói có thể phân phối | Tạo JAR, ZIP hoặc gói đầu ra khác |
| `verify` | Kiểm tra kết quả hoặc điều kiện phát hành | Chạy kiểm tra chất lượng, xác minh tệp hoặc điều kiện cần thiết |
| `build` | Điều phối quy trình build thông thường | Phụ thuộc vào các giai đoạn cần hoàn thành để có sản phẩm build |

Tên target ở trên là quy ước dễ hiểu, không phải danh sách tên bắt buộc của Ant. Dự án có thể dùng tên khác, nhưng cần nhất quán và thể hiện đúng trách nhiệm.

### 3.2. Một target có thể có nhiều task

Ví dụ target `clean` có thể xóa nhiều thư mục đầu ra nếu chúng đều là sản phẩm do build tạo ra:

```xml
<target name="clean" description="Remove generated build output">
    <delete dir="build"/>
    <delete dir="reports/generated"/>
</target>
```

Hai task có cùng mục tiêu là loại bỏ kết quả sinh ra. Nếu một thao tác xóa dữ liệu người dùng hoặc tài nguyên nguồn không thuộc phạm vi build, không nên thêm nó vào `clean` chỉ vì muốn gom các lệnh xóa vào cùng một nơi.

Tương tự, target `package` có thể tạo thư mục đích rồi đóng gói JAR. Cả hai task đều phục vụ việc tạo sản phẩm phân phối:

```xml
<target name="package" depends="compile" description="Create application JAR">
    <mkdir dir="build/dist"/>
    <jar destfile="build/dist/application.jar" basedir="build/classes"/>
</target>
```

Trong ví dụ này, dependency `compile` bảo đảm class đã được biên dịch trước khi task `<jar>` đóng gói chúng. Việc tạo thư mục phân phối thuộc cùng mục tiêu tạo gói nên có thể đặt ngay trong target `package`.

### 3.3. Tránh target quá lớn

Một target quá lớn thường có nhiều nhóm công việc khác nhau và không thể gọi riêng từng giai đoạn. Ví dụ:

```xml
<!-- Ví dụ thiết kế khó bảo trì -->
<target name="everything">
    <delete dir="build"/>
    <mkdir dir="build/classes"/>
    <javac srcdir="src/main/java" destdir="build/classes"/>
    <!-- Chạy kiểm thử -->
    <!-- Sao chép tài nguyên -->
    <!-- Đóng gói JAR -->
    <!-- Tạo báo cáo -->
</target>
```

Tên `everything` không cho biết người dùng sẽ nhận được kết quả gì. Target cũng trộn thao tác dọn dẹp, chuẩn bị, biên dịch, kiểm thử, đóng gói và báo cáo. Nếu chỉ muốn biên dịch lại, người dùng vẫn phải gọi toàn bộ chuỗi công việc.

Hãy tách thành các target có mục tiêu riêng và kết nối chúng bằng `depends`. Khi đó, mỗi giai đoạn có thể được gọi độc lập, còn target cấp cao vẫn cung cấp một lệnh thuận tiện cho toàn bộ quy trình.

### 3.4. Tránh chia target quá nhỏ

Tách target không có nghĩa mỗi task đều cần một target riêng. Nếu một target chỉ bọc một task đơn giản và không tạo ra một công việc có ý nghĩa độc lập, việc tách có thể làm build file dài hơn mà không tăng khả năng tái sử dụng hoặc khả năng đọc.

Ví dụ, nếu `prepare` chỉ tạo hai thư mục phục vụ cùng một giai đoạn, hãy giữ các task trong một target. Chỉ tách thành `create-classes-dir` và `create-dist-dir` khi hai việc đó thực sự được gọi, cấu hình hoặc quản lý độc lập trong dự án.

Ranh giới tốt phụ thuộc vào mục đích build, không phụ thuộc số lượng dòng XML hay số lượng task.

## 4. Kết nối target bằng dependency

Thuộc tính `depends` khai báo các target cần chạy trước target hiện tại. Đây là cơ chế để mô hình hóa trình tự giữa những giai đoạn có trách nhiệm riêng.

Ví dụ:

```xml
<project name="sample-app" default="build" basedir=".">

    <target name="prepare">
        <mkdir dir="build/classes"/>
    </target>

    <target name="compile" depends="prepare">
        <javac srcdir="src/main/java"
               destdir="build/classes"
               includeantruntime="false"/>
    </target>

    <target name="package" depends="compile">
        <mkdir dir="build/dist"/>
        <jar destfile="build/dist/application.jar"
             basedir="build/classes"/>
    </target>

    <target name="build" depends="package"/>

</project>
```

Luồng phụ thuộc:

```text
prepare  →  compile  →  package  →  build
```

Khi chạy `ant build`, Ant thực hiện `prepare`, sau đó `compile`, tiếp đến `package` và cuối cùng hoàn thành target `build`. Target `build` không cần chứa task vì vai trò của nó là cung cấp một điểm gọi cấp cao cho quy trình đã được các dependency mô tả.

Ví dụ giả định dự án có mã nguồn trong `src/main/java`. Thư mục này cần tồn tại và có mã nguồn phù hợp để `<javac>` biên dịch. Tùy dự án, bạn cũng cần khai báo classpath, thư viện và cấu hình compiler tương ứng.

### 4.1. Dependency thay cho việc sao chép task

Giả sử cả `package` và `test` đều cần mã nguồn được biên dịch. Hãy để cả hai phụ thuộc vào `compile`:

```xml
<target name="compile" depends="prepare">
    <javac srcdir="src/main/java"
           destdir="build/classes"
           includeantruntime="false"/>
</target>

<target name="test" depends="compile">
    <!-- Đặt task test runner của dự án tại đây. -->
</target>

<target name="package" depends="compile">
    <jar destfile="build/dist/application.jar"
         basedir="build/classes"/>
</target>
```

Khi chạy `ant test`, Ant thực hiện `compile` trước `test`. Khi chạy `ant package`, Ant cũng thực hiện `compile` trước `package`. Không cần sao chép task `<javac>` vào cả hai target.

Đoạn `test` trên chỉ minh họa ranh giới target và dependency. Để thực sự kiểm thử ứng dụng, hãy thêm task hoặc tích hợp test runner mà dự án đang sử dụng. Một target có tên `test` nhưng chỉ chứa comment không tự chạy kiểm thử.

### 4.2. Nhiều dependency

Một target có thể phụ thuộc vào nhiều target. Danh sách trong `depends` có thể được phân tách bằng dấu phẩy hoặc khoảng trắng. Ant xử lý các dependency theo thứ tự được khai báo, sau đó mới thực hiện nội dung của target phụ thuộc.

Ví dụ:

```xml
<target name="release" depends="verify,package">
    <echo message="Release inputs are ready"/>
</target>
```

Trong ví dụ này, `verify` và `package` được hoàn thành trước khi task `<echo>` của `release` chạy. Hãy chọn thứ tự dependency phù hợp với yêu cầu thực tế của dự án.

Nếu một target được yêu cầu qua nhiều nhánh dependency trong cùng một lần chạy, Ant chỉ thực hiện target đó một lần trong lần chạy ấy. Vì vậy, có thể dùng chung target `compile` mà không phải lặp lại các task biên dịch ở mọi nhánh.

### 4.3. Tránh dependency vòng

Dependency cần tạo thành một đồ thị có hướng không chu trình. Nếu `compile` phụ thuộc `prepare`, nhưng `prepare` lại phụ thuộc `compile`, Ant không thể xác định thứ tự thực thi hợp lệ.

Ví dụ không hợp lệ về thiết kế:

```xml
<target name="prepare" depends="compile">
    <mkdir dir="build/classes"/>
</target>

<target name="compile" depends="prepare">
    <echo message="Compile source"/>
</target>
```

Hãy xác định chiều phụ thuộc theo dữ liệu và công việc: bước chuẩn bị tạo đầu vào cho bước biên dịch, do đó `compile` phụ thuộc `prepare`. Không để bước chuẩn bị phụ thuộc ngược vào kết quả của bước biên dịch.

## 5. Thiết kế target điều phối và target độc lập

Build file thường cần cả target thực hiện một giai đoạn cụ thể và target điều phối quy trình. Target điều phối có thể không chứa task; nó tập hợp các dependency để người dùng gọi một lệnh duy nhất.

Ví dụ, `compile` và `package` có thể chạy riêng, còn `build` đại diện cho quy trình build thông thường:

```xml
<project name="sample-app" default="build">

    <target name="prepare">
        <mkdir dir="build/classes"/>
    </target>

    <target name="compile" depends="prepare">
        <javac srcdir="src/main/java"
               destdir="build/classes"
               includeantruntime="false"/>
    </target>

    <target name="package" depends="compile">
        <mkdir dir="build/dist"/>
        <jar destfile="build/dist/application.jar"
             basedir="build/classes"/>
    </target>

    <target name="build" depends="package"
            description="Compile and package the application"/>

</project>
```

Các lệnh sau có mục đích khác nhau:

```bash
# Chạy toàn bộ quy trình build mặc định
ant

# Chỉ yêu cầu giai đoạn biên dịch và dependency của nó
ant compile

# Yêu cầu tạo gói, bao gồm các dependency cần thiết
ant package
```

Target độc lập cho phép người dùng thao tác ở mức chi tiết khi cần. Target điều phối cung cấp giao diện đơn giản cho quy trình phổ biến.

### 5.1. Đặt `clean` riêng

Target `clean` thường được thiết kế độc lập để người dùng quyết định khi nào cần xóa đầu ra cũ:

```xml
<target name="clean" description="Remove generated build files">
    <delete dir="build"/>
</target>
```

Không nên mặc định cho mọi lần `build` đều phụ thuộc `clean` nếu dự án muốn tận dụng biên dịch tăng dần theo thời gian sửa đổi tệp. Nếu `clean` nằm trong chuỗi dependency của `build`, đầu ra sẽ bị xóa trước mỗi lần build và các bước cần thiết phải chạy lại.

Nếu muốn cung cấp một lệnh build lại từ đầu, tạo target điều phối riêng:

```xml
<target name="rebuild" depends="clean,build"
        description="Clean and build from scratch"/>
```

Vì thứ tự dependency được khai báo là `clean` rồi `build`, Ant dọn đầu ra trước, sau đó chạy quy trình build. Người dùng có thể lựa chọn giữa `ant build` và `ant rebuild` theo nhu cầu.

## 6. Quy tắc đặt tên target

Tên target là giao diện mà người dùng và các target khác sử dụng. Tên tốt giúp người đọc hiểu công việc mà không cần mở nội dung target.

Nên dùng tên ngắn, rõ mục đích và nhất quán:

| Tên rõ nghĩa | Tên khó hiểu | Lý do |
|---|---|---|
| `prepare` | `step1` | Thể hiện mục tiêu chuẩn bị thay vì vị trí trong chuỗi |
| `compile` | `run2` | Nêu rõ công việc biên dịch |
| `package` | `doJar` | Thể hiện giai đoạn tạo gói, không gắn tên vào một cách triển khai cụ thể |
| `clean` | `removeStuff` | Xác định rõ phạm vi dọn dẹp build |
| `verify` | `checkAll` | Diễn đạt mục tiêu kiểm tra có chủ đích |
| `rebuild` | `again` | Cho biết đây là quy trình build lại từ đầu |

Các động từ như `prepare`, `compile`, `test`, `package`, `verify`, `clean` thường phù hợp với target. Nếu cần nhiều biến thể, thêm từ mô tả phạm vi như `compile-main`, `compile-test` hoặc `package-dist`.

Tránh tên quá chung như `task1`, `process`, `execute` hoặc `everything`, vì chúng không cho biết tác động của target. Cũng tránh đặt tên theo chi tiết triển khai tạm thời nếu tên đó không phản ánh mục tiêu của công việc.

## 7. Dùng description để mô tả target

Thuộc tính `description` cung cấp mô tả ngắn cho target. Nó giúp người dùng hiểu mục tiêu khi liệt kê target bằng `ant -p`:

```xml
<target name="clean" description="Remove generated build output">
    <delete dir="build"/>
</target>

<target name="compile" depends="prepare"
        description="Compile main Java sources">
    <javac srcdir="src/main/java"
           destdir="build/classes"
           includeantruntime="false"/>
</target>
```

Description nên mô tả kết quả hoặc mục đích, không cần lặp lại nguyên tên target. Ví dụ, `Compile main Java sources` giải thích rõ phạm vi của `compile`.

Với target điều phối không có task, description đặc biệt hữu ích vì nó giúp người dùng hiểu vì sao target tồn tại và những giai đoạn mà nó kết nối.

## 8. Kiểm tra cách thiết kế target

Sau khi viết build file, bạn có thể liệt kê các target và mô tả bằng:

```bash
ant -p
```

Để xem thông tin chẩn đoán của Ant khi cần tìm hiểu môi trường thực thi:

```bash
ant -diagnostics
```

Thử gọi từng target độc lập để xác nhận ranh giới trách nhiệm có hữu ích:

```bash
ant prepare
ant compile
ant package
ant build
ant clean
```

Các lệnh trên là ví dụ theo build file đã khai báo. Không phải dự án nào cũng có đủ các target đó. Nếu một target được thiết kế là giai đoạn độc lập, hãy kiểm tra nó có thể được gọi trực tiếp và các dependency của nó có chuẩn bị đủ đầu vào hay không.

Khi xem log, chú ý thứ tự target được thực hiện. Nếu một target làm nhiều việc không liên quan hoặc cần chạy một target khác bằng cách sao chép các task, hãy xem xét tách trách nhiệm và dùng `depends`.

## 9. Các lỗi thiết kế target thường gặp

| Vấn đề | Hệ quả | Cách cải thiện |
|---|---|---|
| Một target làm tất cả | Khó gọi riêng giai đoạn, log dài và khó xác định lỗi | Tách các giai đoạn độc lập thành target riêng rồi kết nối bằng dependency |
| Mỗi task đều có một target | Build file có quá nhiều target nhỏ, tên và dependency gây nhiễu | Gom các task cùng mục tiêu vào một target |
| Sao chép task giữa các target | Cùng một công việc phải sửa ở nhiều nơi, dễ phát sinh khác biệt | Đưa công việc dùng chung vào target riêng và khai báo dependency |
| Target tên chung chung | Người dùng không đoán được target sẽ làm gì | Dùng động từ thể hiện mục tiêu như `compile`, `package`, `clean` |
| Dependency vòng | Ant không thể tạo thứ tự thực thi hợp lệ | Vẽ lại luồng đầu vào và đầu ra để dependency chỉ đi theo một chiều |
| `clean` luôn nằm trong `build` | Mỗi lần build đều xóa kết quả trước đó, mất lợi ích incremental | Giữ `clean` riêng và tạo `rebuild` khi cần dọn rồi build lại |
| Target điều phối chứa nhiều chi tiết triển khai | Quy trình cấp cao khó đọc và khó thay đổi | Để target điều phối chủ yếu kết nối các target giai đoạn |
| Target không mô tả rõ kết quả | Người dùng không biết khi nào nên gọi | Bổ sung `description` và đặt tên đúng trách nhiệm |

Không phải target nào cũng cần được tách hoặc điều phối. Hãy dựa vào nhu cầu gọi riêng, khả năng tái sử dụng, sự độc lập của đầu ra và mức độ dễ hiểu của build file để quyết định.

## 10. Ví dụ hoàn chỉnh theo trách nhiệm

Ví dụ sau minh họa cách phân chia trách nhiệm trong một build file nhỏ:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="sample-app" default="build" basedir=".">

    <property name="src.dir" value="src/main/java"/>
    <property name="build.dir" value="build"/>
    <property name="classes.dir" value="${build.dir}/classes"/>
    <property name="dist.dir" value="${build.dir}/dist"/>

    <target name="clean" description="Remove generated output">
        <delete dir="${build.dir}"/>
    </target>

    <target name="prepare" description="Create build directories">
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${dist.dir}"/>
    </target>

    <target name="compile" depends="prepare"
            description="Compile main Java sources">
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               includeantruntime="false"/>
    </target>

    <target name="package" depends="compile"
            description="Create the application JAR">
        <jar destfile="${dist.dir}/${ant.project.name}.jar"
             basedir="${classes.dir}"/>
    </target>

    <target name="build" depends="package"
            description="Compile and package the application"/>

    <target name="rebuild" depends="clean,build"
            description="Clean and build from scratch"/>

</project>
```

Trách nhiệm của từng target:

| Target | Trách nhiệm | Kết quả chính |
|---|---|---|
| `clean` | Xóa đầu ra do build tạo | Thư mục `build` được loại bỏ |
| `prepare` | Tạo thư mục cần cho các bước sau | Có thư mục class và thư mục phân phối |
| `compile` | Biên dịch mã nguồn Java | Các tệp `.class` trong `build/classes` |
| `package` | Đóng gói class thành JAR | JAR trong `build/dist` |
| `build` | Điều phối quy trình thông thường | Hoàn thành compile và package |
| `rebuild` | Dọn đầu ra rồi chạy build | Sản phẩm được tạo lại từ đầu |

Luồng phụ thuộc:

```text
                    ┌──────────────┐
                    │    clean     │
                    └──────┬───────┘
                           │
                           v
                    ┌──────────────┐
                    │    rebuild   │
                    └──────┬───────┘
                           │ depends on clean, build
                           v
┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐
│ prepare │ → │ compile │ → │ package │ → │  build  │
└─────────┘   └─────────┘   └─────────┘   └─────────┘
```

Sơ đồ nhấn mạnh rằng `clean` không phải dependency của `build`. Target `rebuild` là lựa chọn riêng cho trường hợp cần xóa đầu ra trước khi thực hiện quy trình build. Nếu chạy `ant build`, Ant không tự gọi `clean`.

Ví dụ cần thư mục `src/main/java` có mã nguồn Java để compile. Tùy ứng dụng, hãy bổ sung classpath, tài nguyên, cấu hình compiler và các bước kiểm thử tương ứng. Các target vẫn nên giữ mục tiêu riêng khi mở rộng build file.

## 11. Checklist thiết kế target

- [ ] Mỗi target có tên mô tả được một mục tiêu hoặc giai đoạn cụ thể.
- [ ] Các task trong một target cùng phục vụ mục tiêu đó.
- [ ] Những giai đoạn cần gọi riêng đã được tách thành target riêng.
- [ ] Công việc dùng chung được tái sử dụng thông qua dependency thay vì sao chép task.
- [ ] Target điều phối thể hiện quy trình cấp cao bằng các dependency rõ ràng.
- [ ] Dependency đi theo chiều đầu vào đến đầu ra và không tạo chu trình.
- [ ] `clean` được tách khỏi quy trình build thông thường nếu cần giữ khả năng build tăng dần.
- [ ] Target có `description` khi mô tả giúp người dùng hiểu mục đích.
- [ ] Có thể gọi trực tiếp các target giai đoạn và quan sát thứ tự thực thi trong log.

Thiết kế target theo một trách nhiệm rõ ràng giúp build file Ant trở thành mô tả quy trình có cấu trúc. Người dùng có thể gọi một giai đoạn khi cần, còn target điều phối kết nối các giai đoạn thành một quy trình thống nhất. Khi dự án lớn lên, cách tổ chức này giúp thay đổi từng bước mà không phải viết lại hoặc sao chép toàn bộ build logic.
