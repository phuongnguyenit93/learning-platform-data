# Cách Ant mô tả công việc và phụ thuộc bằng XML

Apache Ant dùng một tệp XML để mô tả quy trình build của dự án. Tệp này khai báo dự án gồm những bước nào, mỗi bước thực hiện các thao tác gì và bước nào phải hoàn tất trước bước nào. Ant đọc các khai báo đó để xác định thứ tự chạy khi người dùng gọi một target.

Điểm cốt lõi là ba khái niệm **project**, **target** và **task**: project là toàn bộ quy trình build, target là một bước có tên trong quy trình, còn task là thao tác cụ thể được thực hiện bên trong target. Thuộc tính **depends** nối các target thành một đồ thị phụ thuộc.

## 1. Cấu trúc của một build file

Build file mặc định của Ant thường có tên `build.xml`. Cấu trúc cơ bản như sau:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="sample-app" default="package" basedir=".">

    <property name="src.dir" location="src/main/java"/>
    <property name="build.dir" location="build"/>

    <target name="init">
        <mkdir dir="${build.dir}"/>
    </target>

    <target name="compile" depends="init">
        <javac srcdir="${src.dir}"
               destdir="${build.dir}"
               includeantruntime="false"/>
    </target>

</project>
~~~

Các thành phần quan trọng:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| `project` | Phần tử gốc, đại diện cho một dự án Ant | `<project ...>` |
| `property` | Khai báo giá trị dùng lại trong build file | `<property name="build.dir" location="build"/>` |
| `target` | Khai báo một bước build có tên | `<target name="compile">` |
| task | Thực hiện một thao tác cụ thể | `<javac>`, `<mkdir>`, `<jar>` |
| phần tử lồng nhau | Cung cấp cấu hình chi tiết cho task | `<fileset>`, `<classpath>` |

Một build file là XML nên các phần tử phải được lồng đúng cấu trúc và đóng thẻ hợp lệ. Các target được khai báo trực tiếp bên trong project; các task thường được đặt bên trong target mà chúng phục vụ.

### Phần tử project

Phần tử project bao quanh toàn bộ khai báo:

~~~xml
<project name="sample-app" default="package" basedir=".">
    <!-- properties và targets được khai báo ở đây -->
</project>
~~~

Ba thuộc tính thường gặp:

- **name** đặt tên dễ nhận biết cho dự án Ant.
- **default** chỉ định target được chạy khi gọi Ant mà không ghi tên target.
- **basedir** xác định thư mục gốc để phân giải các đường dẫn tương đối trong build file. Giá trị `.` nghĩa là thư mục hiện tại của build project.

Ví dụ, với `default="package"`, lệnh `ant` tương đương với việc yêu cầu Ant chạy target `package` cùng các target phụ thuộc của nó.

### Property và biểu thức thay thế

Property giúp tập trung các giá trị cấu hình thay vì lặp lại đường dẫn hoặc tên môi trường ở nhiều nơi.

~~~xml
<property name="src.dir" location="src/main/java"/>
<property name="test.src.dir" location="src/test/java"/>
<property name="build.dir" location="build"/>
<property name="classes.dir" location="${build.dir}/classes"/>
~~~

Giá trị được tham chiếu bằng cú pháp `${ten-property}`, ví dụ `${classes.dir}`. Thuộc tính `location` phù hợp với đường dẫn trên hệ thống tệp; thuộc tính `value` thường dùng cho giá trị văn bản:

~~~xml
<property name="application.name" value="sample-app"/>
~~~

Property chuẩn của Ant có tính chất **chỉ thiết lập một lần**: khi một property đã có giá trị, khai báo sau không ghi đè giá trị đó. Property truyền từ dòng lệnh bằng `-D` được thiết lập trước khi build file xử lý các khai báo, vì vậy có thể dùng để cung cấp giá trị theo môi trường:

~~~bash
ant -Dbuild.dir=build-ci package
~~~

## 2. Target mô tả một bước công việc

Target là đơn vị tổ chức chính của quy trình build. Một target có tên để người dùng gọi trực tiếp hoặc để target khác tham chiếu trong thuộc tính `depends`.

~~~xml
<target name="compile" depends="init" description="Biên dịch mã nguồn Java">
    <javac srcdir="${src.dir}"
           destdir="${classes.dir}"
           includeantruntime="false"/>
</target>
~~~

Các thuộc tính thường dùng của target:

| Thuộc tính | Ý nghĩa |
|---|---|
| `name` | Tên target; cần duy nhất trong project để có thể tham chiếu rõ ràng |
| `depends` | Danh sách target phải được xử lý trước target hiện tại |
| `description` | Mô tả ngắn, có thể hiển thị trong phần trợ giúp của Ant |
| `if` | Chỉ thực hiện phần thân target khi property được chỉ định đã tồn tại |
| `unless` | Chỉ thực hiện phần thân target khi property được chỉ định chưa tồn tại |

Tên target nên thể hiện mục đích của bước, chẳng hạn `clean`, `init`, `compile`, `test` hoặc `package`. Khi target được chia theo từng trách nhiệm, người đọc dễ hiểu quy trình và có thể chạy riêng một bước để xử lý công việc cụ thể.

## 3. Task là thao tác thực tế

Task là lệnh mà Ant thực thi. Một target có thể chứa một hoặc nhiều task; trong trường hợp thông thường, các task trong cùng target được thực hiện theo thứ tự xuất hiện trong XML.

~~~xml
<target name="prepare">
    <mkdir dir="${classes.dir}"/>
    <mkdir dir="${dist.dir}"/>
    <copy todir="${build.dir}/config">
        <fileset dir="src/main/resources"/>
    </copy>
</target>
~~~

Trong ví dụ trên:

1. `mkdir` tạo thư mục chứa class đã biên dịch.
2. `mkdir` tạo thư mục chứa sản phẩm đóng gói.
3. `copy` sao chép tài nguyên; `fileset` mô tả tập tệp nguồn cần sao chép.

Một số task thường gặp:

| Task | Công việc |
|---|---|
| `mkdir` | Tạo thư mục |
| `delete` | Xóa tệp hoặc thư mục |
| `copy` | Sao chép tệp |
| `javac` | Biên dịch mã nguồn Java |
| `jar` | Đóng gói các tệp thành JAR |
| `echo` | In thông điệp |
| `java` | Chạy lớp Java |

Task có thể nhận cấu hình qua thuộc tính XML hoặc phần tử lồng nhau. Ví dụ, `javac` nhận `srcdir` và `destdir`; task xử lý tập tệp có thể nhận một phần tử `fileset`. Cách lồng này giúp cấu hình dữ liệu có cấu trúc mà không phải gom mọi thứ vào một chuỗi thuộc tính dài.

## 4. depends mô tả quan hệ phụ thuộc giữa các target

Thuộc tính `depends` cho biết target hiện tại cần những target nào hoàn thành trước khi chạy phần thân của nó.

~~~xml
<target name="init">
    <mkdir dir="${classes.dir}"/>
</target>

<target name="compile" depends="init">
    <javac srcdir="${src.dir}"
           destdir="${classes.dir}"
           includeantruntime="false"/>
</target>

<target name="package" depends="compile">
    <jar destfile="${dist.dir}/sample.jar"
         basedir="${classes.dir}"/>
</target>
~~~

Khi gọi target `package`, Ant xử lý chuỗi phụ thuộc theo hướng:

~~~text
init → compile → package
~~~

- `init` tạo thư mục cần thiết.
- `compile` chạy sau khi `init` hoàn tất.
- `package` chạy sau khi `compile` hoàn tất.

Vì vậy, người dùng chỉ cần yêu cầu target cuối cùng; Ant lần theo các quan hệ `depends` để thực hiện các bước chuẩn bị.

### Một target có thể phụ thuộc vào nhiều target

Các tên target trong `depends` được phân cách bằng dấu phẩy:

~~~xml
<target name="verify" depends="test,check-style">
    <echo message="Verification completed"/>
</target>
~~~

Ant xử lý các phụ thuộc theo thứ tự chúng xuất hiện trong danh sách. Nếu một target phụ thuộc lại vào target khác, Ant tiếp tục xử lý quan hệ đó trước khi quay về target đang xét.

Ví dụ:

~~~xml
<target name="init">
    <echo message="Prepare directories"/>
</target>

<target name="compile" depends="init">
    <echo message="Compile sources"/>
</target>

<target name="test" depends="compile">
    <echo message="Run tests"/>
</target>

<target name="check-style" depends="init">
    <echo message="Check source style"/>
</target>

<target name="verify" depends="test,check-style">
    <echo message="Verification completed"/>
</target>
~~~

Đồ thị phụ thuộc có thể hình dung như sau:

~~~mermaid
flowchart TD
    I["init"] --> C["compile"]
    C --> T["test"]
    I --> S["check-style"]
    T --> V["verify"]
    S --> V
~~~

Khi chạy `verify`, một thứ tự hợp lệ theo danh sách phụ thuộc là `init`, `compile`, `test`, `check-style`, rồi `verify`. Target `init` chỉ được thực hiện một lần trong cùng lượt build, dù có nhiều nhánh cùng phụ thuộc vào nó.

### Phụ thuộc không đồng nghĩa với thứ tự khai báo trong XML

Ant không mặc định chạy tất cả target từ trên xuống dưới theo thứ tự chúng xuất hiện trong file. Ant bắt đầu từ target được yêu cầu, hoặc target mặc định, rồi lần theo `depends`.

Ví dụ, target `package` có thể được khai báo trước target `compile` trong file và vẫn phụ thuộc vào `compile`:

~~~xml
<target name="package" depends="compile">
    <jar destfile="build/sample.jar" basedir="build/classes"/>
</target>

<target name="compile">
    <javac srcdir="src" destdir="build/classes"/>
</target>
~~~

Khi chạy `ant package`, Ant vẫn xử lý `compile` trước `package`. Thứ tự công việc đến từ quan hệ phụ thuộc, không phải vị trí dòng khai báo.

### Phụ thuộc vòng là cấu hình sai

Một đồ thị phụ thuộc phải cho phép Ant xác định thứ tự hoàn thành. Nếu A phụ thuộc B, đồng thời B phụ thuộc A, Ant không thể tìm được thứ tự hợp lệ:

~~~xml
<target name="A" depends="B"/>
<target name="B" depends="A"/>
~~~

Cấu hình này tạo thành chu trình và khiến quá trình build thất bại. Khi gặp lỗi liên quan đến vòng phụ thuộc, cần xem lại trách nhiệm của các target và tách bước chung thành target thứ ba nếu phù hợp.

## 5. Ví dụ build.xml hoàn chỉnh

Ví dụ sau mô tả một ứng dụng Java nhỏ với các bước chuẩn bị, biên dịch và đóng gói. Target `clean` được khai báo riêng để người dùng chủ động yêu cầu xóa sản phẩm build cũ.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="sample-app" default="package" basedir=".">

    <!-- Các đường dẫn dùng chung -->
    <property name="src.dir" location="src/main/java"/>
    <property name="build.dir" location="build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="dist.dir" location="${build.dir}/dist"/>

    <!-- Xóa kết quả build cũ khi được yêu cầu -->
    <target name="clean" description="Xóa thư mục build">
        <delete dir="${build.dir}"/>
    </target>

    <!-- Tạo thư mục đầu ra -->
    <target name="init" description="Chuẩn bị thư mục build">
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${dist.dir}"/>
    </target>

    <!-- Biên dịch mã nguồn; cần init hoàn tất trước -->
    <target name="compile" depends="init"
            description="Biên dịch mã nguồn Java">
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               includeantruntime="false"/>
    </target>

    <!-- Đóng gói class đã biên dịch; cần compile hoàn tất trước -->
    <target name="package" depends="compile"
            description="Tạo tệp JAR">
        <jar destfile="${dist.dir}/sample-app.jar"
             basedir="${classes.dir}"/>
    </target>

</project>
~~~

Trong build file này, `default="package"` khiến lệnh `ant` chạy target `package`. Ant nhận thấy `package` phụ thuộc vào `compile`, còn `compile` phụ thuộc vào `init`, nên thứ tự thực thi là:

1. `init`: tạo `build/classes` và `build/dist`.
2. `compile`: biên dịch mã nguồn trong `src/main/java` vào `build/classes`.
3. `package`: đóng gói nội dung `build/classes` thành `build/dist/sample-app.jar`.

Target `clean` không nằm trong chuỗi phụ thuộc của `package`. Vì thế, chạy `ant` không tự động xóa thư mục build. Người dùng có thể yêu cầu rõ ràng `clean` trước khi đóng gói bằng lệnh `ant clean package`.

## 6. Chạy và quan sát các target

Ant cho phép gọi target mặc định hoặc chỉ định tên target:

| Lệnh | Kết quả |
|---|---|
| `ant` | Chạy target được khai báo trong thuộc tính `default` |
| `ant compile` | Chạy target `compile` cùng các phụ thuộc của nó |
| `ant clean` | Chỉ yêu cầu target `clean` và các phụ thuộc của nó, nếu có |
| `ant clean package` | Chạy lần lượt các target được yêu cầu theo thứ tự trên dòng lệnh; `package` vẫn xử lý các phụ thuộc của nó |
| `ant -p` | Hiển thị trợ giúp và các target có mô tả |
| `ant -f build-ci.xml package` | Dùng build file có tên khác `build.xml` |
| `ant -verbose package` | Hiển thị thông tin chi tiết hơn trong lúc xử lý build |

Có thể truyền property từ dòng lệnh để thay đổi cấu hình của một lượt build:

~~~bash
ant -Denv=ci package
~~~

Build file có thể khai báo property `env` để sử dụng giá trị đó trong các cấu hình hoặc điều kiện phù hợp. Việc truyền tham số không tự tạo ra target mới; target vẫn được chọn bằng tên như bình thường.

Khi cần hiểu vì sao một task chạy trước task khác, hãy lần từ target được gọi, xem thuộc tính `depends` của target đó, sau đó lần tiếp các target phụ thuộc. Khi cần biết một thao tác cụ thể làm gì, hãy đọc các task bên trong target theo thứ tự XML.

## 7. Điều kiện chạy target với if và unless

Ant hỗ trợ điều kiện ở cấp target thông qua `if` và `unless`. Hai thuộc tính này kiểm tra **property có tồn tại hay không**, chứ không diễn giải nội dung của property thành giá trị boolean.

~~~xml
<target name="integration-test" depends="compile" if="run.integration">
    <echo message="Integration test target is enabled"/>
</target>

<target name="publish" depends="package" unless="skip.publish">
    <echo message="Publish step is enabled"/>
</target>
~~~

Với ví dụ trên:

- `integration-test` thực hiện phần thân khi property `run.integration` đã được thiết lập.
- `publish` thực hiện phần thân khi property `skip.publish` chưa được thiết lập.
- Nếu property được đặt thành chuỗi `false`, nó vẫn được xem là đã tồn tại. Vì vậy, `if="run.integration"` vẫn cho phép target chạy khi property có giá trị văn bản là `false`.

Có thể thiết lập property từ dòng lệnh:

~~~bash
ant -Drun.integration=true integration-test
~~~

**Lưu ý về depends:** điều kiện chỉ quyết định phần thân target có được thực hiện hay không. Các target được liệt kê trong `depends` vẫn được xử lý trước. Do đó, nếu `run.integration` chưa được thiết lập thì phần thân của `integration-test` được bỏ qua, nhưng target `compile` vẫn chạy vì nó là phụ thuộc của target này.

Nếu cần điều kiện dựa trên một biểu thức hoặc kết quả kiểm tra phức tạp, hãy tạo property bằng task điều kiện thích hợp rồi dùng property đó trong `if` hoặc `unless`.

## 8. Phân biệt phụ thuộc target với phụ thuộc tệp

`depends` mô tả quan hệ thứ tự giữa **các target**. Nó không phải là khai báo đường dẫn đến một tệp và cũng không phải cơ chế tự động phân tích mọi thay đổi trong dự án để tạo đồ thị build.

Ví dụ:

~~~xml
<target name="package" depends="compile">
    <jar destfile="build/app.jar" basedir="build/classes"/>
</target>
~~~

Khai báo này có nghĩa target `compile` phải được xử lý trước target `package`. Nó không có nghĩa Ant chỉ chạy `package` khi một tệp nguồn thay đổi.

Một số task, chẳng hạn `javac`, có thể tự kiểm tra trạng thái đầu vào và đầu ra để tránh biên dịch lại những tệp không cần thiết. Đó là hành vi của task. Quan hệ `depends` vẫn có nhiệm vụ xác định thứ tự giữa các target trong lượt build.

Vì vậy, khi thiết kế build file, cần khai báo đầy đủ các quan hệ công việc: target nào cần chuẩn bị trước, target nào sử dụng kết quả của bước nào, và bước nào là điểm kết thúc của quy trình.

## 9. Quy tắc XML và lỗi thường gặp

Build file phải là XML hợp lệ trước khi Ant có thể diễn giải các khai báo. Một số quy tắc cần nhớ:

- Mỗi tài liệu XML có một phần tử gốc, ở đây là `project`.
- Phần tử phải được đóng đúng và lồng đúng thứ tự.
- Giá trị thuộc tính đặt trong dấu nháy đơn hoặc nháy kép.
- Tên phần tử và thuộc tính phân biệt chữ hoa, chữ thường.
- Ký tự đặc biệt trong nội dung thuộc tính cần được escape theo XML. Ví dụ dùng `&amp;` cho dấu `&`, `&lt;` cho dấu `<` và `&gt;` cho dấu `>`.

Ví dụ, nếu thông điệp cần chứa dấu `&`, hãy viết:

~~~xml
<echo message="Compile &amp; package"/>
~~~

Một số lỗi cấu hình phổ biến:

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Ant báo không tìm thấy target phụ thuộc | Tên trong `depends` sai hoặc target chưa được khai báo trong phạm vi build | Kiểm tra chính tả và tên target |
| Build báo lỗi phụ thuộc vòng | Các target tham chiếu lẫn nhau thành chu trình | Vẽ lại đồ thị và tách phần công việc chung |
| Task chạy trước khi có thư mục đầu ra | Thiếu target chuẩn bị trong chuỗi phụ thuộc | Thêm target chuẩn bị vào `depends` |
| Target không chạy khi gọi `ant` | Target đó không phải target mặc định hoặc không thuộc chuỗi phụ thuộc | Gọi target trực tiếp hoặc sửa thuộc tính `default`/ `depends` |
| Target có `if` vẫn chạy dù property mang giá trị `false` | Ant kiểm tra sự tồn tại của property | Chỉ thiết lập property khi thực sự muốn bật điều kiện |
| Ant không đọc được build file | XML sai cú pháp hoặc đóng/mở thẻ không khớp | Kiểm tra cấu trúc XML và ký tự đặc biệt |

## 10. Cách thiết kế quy trình build dễ hiểu

Khi viết build file, nên tổ chức target theo các bước công việc mà người phát triển có thể gọi và hiểu được:

- Đặt tên theo mục đích: `clean`, `init`, `compile`, `test`, `package`, `publish`.
- Mỗi target nên tập trung vào một nhóm thao tác có cùng mục tiêu.
- Khai báo `depends` theo yêu cầu thực sự của công việc. Nếu đóng gói cần class đã biên dịch, `package` phụ thuộc vào `compile`.
- Tách cấu hình dùng chung thành property để dễ thay đổi thư mục nguồn, thư mục đầu ra hoặc tên sản phẩm.
- Dùng `description` để người khác có thể hiểu target từ lệnh trợ giúp.
- Giữ đồ thị phụ thuộc không có chu trình và tránh tạo quan hệ chỉ để dựa vào thứ tự dòng trong XML.
- Chỉ đưa bước dọn dẹp vào chuỗi khi quy trình thực sự yêu cầu; target `clean` thường được gọi chủ động.

Một build file tốt cho phép người đọc trả lời nhanh ba câu hỏi: **có thể chạy những bước nào, mỗi bước làm gì, và cần hoàn tất bước nào trước khi chạy bước tiếp theo**. XML cung cấp cấu trúc để khai báo các bước; target và task tổ chức công việc; `depends` mô tả thứ tự giữa các bước. Khi kết hợp đúng ba thành phần này, Ant có thể điều phối một quy trình build Java rõ ràng và có thể gọi lại theo từng mục đích.

