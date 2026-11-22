# Mô hình đồ thị phụ thuộc và thuộc tính `depends`

Trong Apache Ant, một dự án thường được chia thành nhiều target như `clean`, `init`, `compile`, `test` và `package`. Những target này có quan hệ với nhau: muốn kiểm thử thì cần biên dịch trước, muốn đóng gói thì cần có các lớp đã biên dịch và những tài nguyên cần thiết.

Thuộc tính `depends` mô tả quan hệ đó trong `build.xml`. Ant dựa vào các khai báo này để xác định target nào phải được thực hiện trước target đang được yêu cầu. Khi dự án có nhiều target và nhiều tầng phụ thuộc, ta có thể biểu diễn chúng thành **đồ thị phụ thuộc**.

Sau bài học, bạn có thể:

- Giải thích ý nghĩa và cú pháp của `depends`.
- Đọc đồ thị phụ thuộc và xác định thứ tự thực hiện các target.
- Phân biệt phụ thuộc trực tiếp, phụ thuộc bắc cầu và phụ thuộc dùng chung.
- Nhận biết lỗi phụ thuộc vòng hoặc tên target được khai báo sai.
- Thiết kế chuỗi target rõ ràng cho quy trình build Java.

## 1. Vì sao cần mô hình phụ thuộc?

Giả sử một dự án Java có quy trình như sau:

1. Tạo thư mục chứa kết quả build.
2. Biên dịch mã nguồn Java.
3. Chạy kiểm thử.
4. Đóng gói ứng dụng thành tệp JAR.

Các bước này có thứ tự logic. Không thể kiểm thử nếu chưa có lớp đã biên dịch; cũng không thể đóng gói các lớp nếu bước biên dịch chưa tạo ra chúng.

Ant không suy đoán thứ tự đó từ tên target hoặc vị trí target trong file. Người viết buildfile khai báo quan hệ bằng `depends`, để Ant biết target nào cần chạy trước.

Ví dụ:

```xml
<project name="demo" default="package">
    <property name="build.dir" location="build" />

    <target name="init">
        <mkdir dir="${build.dir}/classes" />
    </target>

    <target name="compile" depends="init">
        <echo message="Compile source code" />
    </target>

    <target name="test" depends="compile">
        <echo message="Run tests" />
    </target>

    <target name="package" depends="test">
        <echo message="Package application" />
    </target>
</project>
```

Khi chạy:

```bash
ant package
```

Ant thực hiện các target theo chuỗi phụ thuộc:

```text
init -> compile -> test -> package
```

Bạn chỉ yêu cầu `package`, nhưng Ant tự xác định và thực hiện các target cần thiết trước nó.

## 2. Cú pháp thuộc tính `depends`

`depends` là thuộc tính của phần tử `<target>`. Cú pháp cơ bản:

```xml
<target name="target-hien-tai" depends="target-phu-thuoc-1,target-phu-thuoc-2">
    <!-- Các task của target hiện tại -->
</target>
```

Ví dụ:

```xml
<target name="compile" depends="init">
    <javac srcdir="src" destdir="build/classes" />
</target>
```

Khai báo trên có nghĩa target `compile` phụ thuộc vào target `init`. Ant phải xử lý `init` trước khi thực hiện các task trong `compile`.

Nếu một target cần nhiều target khác chạy trước, liệt kê tên chúng bằng dấu phẩy:

```xml
<target name="package" depends="compile,test,copy-resources">
    <jar destfile="build/app.jar" basedir="build/classes" />
</target>
```

Trong ví dụ, `package` phụ thuộc trực tiếp vào ba target `compile`, `test` và `copy-resources`. Các tên trong `depends` phải là tên target đã được khai báo trong dự án hoặc được đưa vào qua cơ chế import phù hợp. Không ghi tên task như `javac` hoặc `copy` vào `depends`.

`depends` nhận danh sách tên target phân cách bằng dấu phẩy, không phải một câu lệnh hoặc biểu thức điều kiện. Có thể xuống dòng để buildfile dễ đọc nếu vẫn giữ nguyên giá trị thuộc tính:

```xml
<target name="package"
        depends="compile,test,copy-resources"
        description="Create the application archive">
    <jar destfile="build/app.jar" basedir="build/classes" />
</target>
```

## 3. Đọc đồ thị phụ thuộc

Đồ thị phụ thuộc gồm các **đỉnh** và **cạnh**:

- Mỗi đỉnh đại diện cho một target.
- Mỗi cạnh biểu diễn quan hệ phụ thuộc giữa hai target.

Trong bài này, sơ đồ dùng mũi tên theo chiều **target tiên quyết → target cần nó**. Vì vậy, nếu `package` khai báo `depends="compile"`, cạnh được vẽ là `compile → package`.

Ví dụ:

```xml
<target name="init">
    <mkdir dir="build/classes" />
</target>

<target name="compile" depends="init">
    <javac srcdir="src" destdir="build/classes" />
</target>

<target name="test" depends="compile">
    <echo message="Testing" />
</target>

<target name="package" depends="test">
    <jar destfile="build/app.jar" basedir="build/classes" />
</target>
```

Đồ thị:

```text
init  --->  compile  --->  test  --->  package
```

Khi đọc từ trái sang phải, mỗi target được thực hiện trước target ở bên phải. `init` là target tiên quyết của `compile`; `compile` là target tiên quyết của `test`; `test` là target tiên quyết của `package`.

### 3.1. Phụ thuộc trực tiếp

Nếu target `A` khai báo `depends="B"`, thì `B` là phụ thuộc trực tiếp của `A`.

```xml
<target name="compile" depends="init">
    <echo message="Compile" />
</target>
```

Ở đây:

- Target đang xét: `compile`.
- Phụ thuộc trực tiếp: `init`.
- Quan hệ theo chiều mũi tên của sơ đồ: `init → compile`.

Phụ thuộc trực tiếp được ghi ngay trong thuộc tính `depends` của target.

### 3.2. Phụ thuộc bắc cầu

Một target có thể phụ thuộc vào target khác thông qua nhiều tầng. Ví dụ:

```xml
<target name="init">
    <mkdir dir="build" />
</target>

<target name="compile" depends="init">
    <echo message="Compile" />
</target>

<target name="test" depends="compile">
    <echo message="Test" />
</target>

<target name="package" depends="test">
    <echo message="Package" />
</target>
```

Target `package` phụ thuộc trực tiếp vào `test`. Tuy nhiên, để thực hiện `test`, Ant cần `compile`; để thực hiện `compile`, Ant cần `init`. Do đó, `init` và `compile` cũng nằm trong tập phụ thuộc cần thiết để chạy `package`, dù chúng không xuất hiện trực tiếp trong `depends` của `package`.

Đây là **phụ thuộc bắc cầu**. Khi yêu cầu một target, Ant xét toàn bộ chuỗi phụ thuộc của target đó, không chỉ danh sách được ghi ngay trên target.

### 3.3. Nhiều phụ thuộc trực tiếp và nhánh dùng chung

Một target có thể cần nhiều nhánh công việc trước khi chạy. Ví dụ, bước đóng gói cần cả lớp đã biên dịch và tài nguyên đã được sao chép:

```xml
<target name="init">
    <mkdir dir="build/classes" />
</target>

<target name="compile" depends="init">
    <javac srcdir="src" destdir="build/classes" />
</target>

<target name="copy-resources" depends="init">
    <copy todir="build/classes">
        <fileset dir="resources" />
    </copy>
</target>

<target name="package" depends="compile,copy-resources">
    <jar destfile="build/app.jar" basedir="build/classes" />
</target>
```

Đồ thị phụ thuộc:

```text
                  +--> compile --------+
                  |                    |
init -------------+                    +--> package
                  |                    |
                  +--> copy-resources -+
```

`package` cần cả `compile` và `copy-resources`. Cả hai target này đều cần `init`. Khi gọi `ant package`, Ant xử lý `init` trước, rồi lần lượt xử lý các nhánh phụ thuộc theo thứ tự được khai báo, sau đó mới thực hiện `package`.

Trong cùng một lần gọi Ant, một target chỉ được thực hiện tối đa một lần. Vì vậy, `init` không chạy hai lần chỉ vì nó được yêu cầu qua cả nhánh `compile` và nhánh `copy-resources`.

## 4. Thứ tự thực hiện các target

Ant xử lý target theo nguyên tắc:

1. Xác định target mà người dùng yêu cầu (hoặc target mặc định nếu chạy `ant` không ghi tên target).
2. Xét các target được liệt kê trong `depends` của target đó.
3. Xử lý phụ thuộc của từng target trước khi thực hiện target đang xét.
4. Khi các phụ thuộc đã được xử lý, thực hiện các task bên trong target.

### 4.1. Thứ tự các mục trong `depends`

Khi có nhiều phụ thuộc, Ant xử lý chúng theo thứ tự được liệt kê trong `depends`, sau khi xử lý các phụ thuộc bắc cầu của từng mục.

Ví dụ:

```xml
<target name="prepare-db">
    <echo message="Prepare database" />
</target>

<target name="prepare-ui">
    <echo message="Prepare UI" />
</target>

<target name="build" depends="prepare-db,prepare-ui">
    <echo message="Build application" />
</target>
```

Khi gọi `ant build`, thứ tự giữa hai phụ thuộc trực tiếp theo khai báo là `prepare-db`, rồi `prepare-ui`, sau đó mới đến `build`.

Nếu đổi thành:

```xml
<target name="build" depends="prepare-ui,prepare-db">
    <echo message="Build application" />
</target>
```

thì thứ tự hai target phụ thuộc được đảo lại. Chỉ nên dựa vào thứ tự này khi các bước thật sự độc lập hoặc khi bạn chủ động muốn một thứ tự cụ thể. Nếu target `prepare-ui` cần kết quả của `prepare-db`, hãy khai báo quan hệ phụ thuộc trực tiếp bằng `depends`, thay vì chỉ dựa vào vị trí trong danh sách.

### 4.2. Thứ tự task bên trong một target

`depends` xác định thứ tự giữa các target. Còn bên trong một target, các task được thực hiện theo thứ tự xuất hiện trong nội dung target.

```xml
<target name="prepare">
    <echo message="Step 1" />
    <mkdir dir="build" />
    <mkdir dir="build/classes" />
    <echo message="Step 4" />
</target>
```

Khi target `prepare` chạy, Ant thực hiện lần lượt bốn task theo thứ tự trong file. Không cần khai báo `depends` giữa các task này.

Hãy phân biệt hai cấp độ:

```text
Đồ thị target:
init -> compile -> package

Các task trong target compile:
echo -> javac -> copy
```

Đồ thị target điều phối các nhóm công việc; thứ tự task điều phối thao tác bên trong từng nhóm.

## 5. Target được yêu cầu và target mặc định

Thuộc tính `default` của `<project>` chỉ định target mặc định khi người dùng chạy Ant mà không ghi tên target.

```xml
<project name="demo" default="package">
    <target name="compile">
        <echo message="Compile" />
    </target>

    <target name="package" depends="compile">
        <echo message="Package" />
    </target>
</project>
```

Với buildfile trên:

| Lệnh | Target được yêu cầu | Kết quả |
|---|---|---|
| `ant` | `package` | Ant chạy `compile` trước rồi chạy `package`. |
| `ant compile` | `compile` | Ant chỉ chạy target `compile` và phụ thuộc của nó (nếu có). |
| `ant package` | `package` | Ant chạy `compile` rồi `package`. |

Ant không tự động chạy mọi target chỉ vì chúng được khai báo trong `build.xml`. Chỉ target được yêu cầu và các target phụ thuộc của nó mới tham gia lần chạy đó.

Bạn cũng có thể yêu cầu nhiều target từ dòng lệnh:

```bash
ant clean package
```

Ant xử lý các target được yêu cầu theo thứ tự liệt kê, đồng thời giải quyết phụ thuộc của từng target. Nếu một target đã được thực hiện trong cùng lần gọi, Ant không chạy lại target đó chỉ vì nó được yêu cầu thêm lần nữa qua một nhánh khác.

## 6. Đồ thị phụ thuộc phải không có chu trình

Quan hệ phụ thuộc của target cần tạo thành một đồ thị có hướng không chu trình (Directed Acyclic Graph — DAG). Điều đó có nghĩa không được tồn tại một chuỗi phụ thuộc quay trở lại chính target ban đầu.

Ví dụ khai báo sai:

```xml
<target name="compile" depends="test">
    <echo message="Compile" />
</target>

<target name="test" depends="package">
    <echo message="Test" />
</target>

<target name="package" depends="compile">
    <echo message="Package" />
</target>
```

Đồ thị tương ứng:

```text
compile -> test -> package
   ^                  |
   +------------------+
```

`compile` cần `test`, `test` cần `package`, còn `package` lại cần `compile`. Ant không thể tìm ra target nào có thể bắt đầu mà vẫn tôn trọng toàn bộ quan hệ đó. Khi phát hiện phụ thuộc vòng, Ant báo lỗi circular dependency và dừng xử lý build.

Để sửa, hãy xác định thứ tự nghiệp vụ đúng. Một quy trình thường hợp lý là:

```text
init -> compile -> test -> package
```

Sau đó khai báo:

```xml
<target name="compile" depends="init">...</target>
<target name="test" depends="compile">...</target>
<target name="package" depends="test">...</target>
```

Không nên cố khắc phục lỗi bằng cách xóa tùy tiện một phụ thuộc. Hãy kiểm tra xem target nào thật sự cần kết quả của target nào và chỉ giữ các quan hệ cần thiết.

## 7. Các lỗi thường gặp khi dùng `depends`

| Lỗi | Vì sao xảy ra | Cách xử lý |
|---|---|---|
| Ghi tên task trong `depends` | `depends` chỉ nhận tên target. | Tạo target bao quanh task rồi tham chiếu tên target đó. |
| Gõ sai tên target | Tên trong `depends` không khớp target đã khai báo. | Kiểm tra chính tả và tên target, kể cả các buildfile được import. |
| Quên khai báo phụ thuộc | Target cần dữ liệu từ target khác nhưng không có quan hệ `depends`. | Khai báo phụ thuộc trực tiếp để Ant có thể tự xác định thứ tự. |
| Tạo chu trình phụ thuộc | Một target quay lại phụ thuộc chính nó qua một hoặc nhiều target trung gian. | Vẽ đồ thị và loại bỏ quan hệ phụ thuộc sai theo đúng thứ tự nghiệp vụ. |
| Cho rằng Ant chạy mọi target | Chỉ target được yêu cầu và các phụ thuộc của nó được xử lý. | Chọn target cụ thể hoặc cấu hình `default` phù hợp. |
| Dựa vào thứ tự target trong file | Vị trí khai báo target không thay thế quan hệ phụ thuộc. | Dùng `depends` để biểu diễn rõ quan hệ cần thiết. |
| Lặp lại nhiều công việc trong các target | Nhiều target có cùng bước chuẩn bị nhưng không được tổ chức hợp lý. | Tách bước dùng chung thành target riêng và cho các target cần nó cùng phụ thuộc. |

### 7.1. Phụ thuộc vào target không tồn tại

Ví dụ:

```xml
<target name="compile" depends="init-build">
    <javac srcdir="src" destdir="build/classes" />
</target>
```

Nếu buildfile không có target `init-build` và cũng không có target tương ứng được đưa vào từ buildfile khác, Ant không thể giải quyết phụ thuộc này. Hãy kiểm tra tên target trong `depends` và tên trong khai báo `<target name="...">`.

### 7.2. Target phụ thuộc nhưng không tạo dữ liệu cần thiết

Khai báo `depends` đúng cú pháp chưa đảm bảo quy trình đúng. Ví dụ `package` phụ thuộc `compile`, nhưng task trong `compile` lại ghi kết quả vào thư mục khác với thư mục mà task `jar` sử dụng. Khi đó thứ tự target hợp lệ nhưng dữ liệu đầu ra không khớp.

Khi thiết kế buildfile, hãy kiểm tra cả hai điều:

- Quan hệ target có thể hiện đúng thứ tự công việc không?
- Đầu ra của target trước có đúng là đầu vào mà target sau cần không?

## 8. Cách thiết kế đồ thị phụ thuộc dễ bảo trì

Một buildfile dễ hiểu thường chia quy trình thành các target có trách nhiệm rõ ràng. Ví dụ:

```xml
<project name="sample-app" default="package" basedir=".">
    <property name="src.dir" location="src" />
    <property name="build.dir" location="build" />
    <property name="classes.dir" location="${build.dir}/classes" />

    <target name="clean" description="Remove generated files">
        <delete dir="${build.dir}" />
    </target>

    <target name="init" description="Create build directories">
        <mkdir dir="${classes.dir}" />
    </target>

    <target name="compile" depends="init" description="Compile Java sources">
        <javac
            srcdir="${src.dir}"
            destdir="${classes.dir}"
            encoding="UTF-8"
            includeantruntime="false" />
    </target>

    <target name="test" depends="compile" description="Run tests">
        <echo message="Run test suite here" />
    </target>

    <target name="package" depends="test" description="Create application JAR">
        <jar destfile="${build.dir}/sample-app.jar" basedir="${classes.dir}" />
    </target>
</project>
```

Đồ thị chính:

```text
clean       (được gọi riêng khi cần xóa kết quả)

init -> compile -> test -> package
```

Một số nguyên tắc hữu ích:

1. **Mỗi target có một nhiệm vụ rõ ràng.** Ví dụ `compile` chỉ tập trung biên dịch; `package` tập trung đóng gói.
2. **Khai báo phụ thuộc ở nơi cần thiết.** Nếu `test` cần lớp đã biên dịch, `test` nên phụ thuộc `compile`.
3. **Tách bước dùng chung.** Nếu `compile` và `copy-resources` đều cần thư mục đầu ra, hãy tạo target `init` dùng chung.
4. **Tránh phụ thuộc vòng.** Xác định luồng công việc theo một chiều từ bước chuẩn bị đến bước tạo sản phẩm.
5. **Không dùng target để gom mọi thao tác không liên quan.** Các target nhỏ, có ý nghĩa giúp người khác hiểu và gọi từng giai đoạn dễ dàng.
6. **Đặt tên nhất quán.** Những tên như `clean`, `init`, `compile`, `test`, `package` thường dễ hiểu trong dự án Java.

Target `clean` trong ví dụ không nằm trên chuỗi phụ thuộc của `package`, vì đóng gói không nhất thiết phải xóa toàn bộ kết quả build trước. Người dùng có thể chủ động gọi `ant clean` khi muốn dọn dẹp. Nếu quy trình yêu cầu xóa trước khi build, có thể thiết kế target riêng như `clean-build` phụ thuộc `clean` và `package`, nhưng cần cân nhắc việc build lại toàn bộ có phải hành vi mặc định mong muốn hay không.

## 9. Bài thực hành

### Bài 1: Đọc một đồ thị tuyến tính

Cho các target:

```xml
<target name="init">
    <echo message="Init" />
</target>

<target name="compile" depends="init">
    <echo message="Compile" />
</target>

<target name="test" depends="compile">
    <echo message="Test" />
</target>

<target name="package" depends="test">
    <echo message="Package" />
</target>
```

Hãy vẽ đồ thị phụ thuộc, sau đó xác định thứ tự target khi chạy `ant package` và `ant compile`.

### Bài 2: Đọc đồ thị có nhánh dùng chung

```xml
<target name="init">
    <mkdir dir="build" />
</target>

<target name="compile" depends="init">
    <echo message="Compile" />
</target>

<target name="resources" depends="init">
    <echo message="Copy resources" />
</target>

<target name="package" depends="compile,resources">
    <echo message="Package" />
</target>
```

Hãy trả lời:

1. `package` có những phụ thuộc trực tiếp nào?
2. `init` có phải phụ thuộc trực tiếp của `package` không?
3. Khi chạy `ant package`, target `init` có chạy hai lần vì xuất hiện ở hai nhánh không?
4. Nếu đổi `depends="compile,resources"` thành `depends="resources,compile"`, thứ tự hai nhánh thay đổi thế nào?

### Bài 3: Tìm và sửa chu trình

```xml
<target name="compile" depends="test">
    <echo message="Compile" />
</target>

<target name="test" depends="package">
    <echo message="Test" />
</target>

<target name="package" depends="compile">
    <echo message="Package" />
</target>
```

Hãy vẽ chu trình, giải thích vì sao Ant không thể thực hiện build và sửa các quan hệ để có thứ tự hợp lý `compile`, `test`, `package`.

### Đáp án gợi ý

- Bài 1: đồ thị `init → compile → test → package`. Chạy `ant package` thực hiện cả bốn target theo thứ tự đó; chạy `ant compile` chỉ cần `init` rồi `compile`.
- Bài 2: `package` phụ thuộc trực tiếp vào `compile` và `resources`; `init` là phụ thuộc bắc cầu. `init` chỉ chạy một lần trong cùng lần gọi Ant. Thay thứ tự danh sách sẽ đổi thứ tự xử lý hai nhánh trực tiếp nếu không có thêm quan hệ phụ thuộc ràng buộc thứ tự đó.
- Bài 3: chu trình là `compile → test → package → compile` theo chiều quan hệ phụ thuộc đã khai báo. Có thể sửa thành `test depends="compile"` và `package depends="test"`, đồng thời bỏ phụ thuộc ngược từ `compile` đến `test`.

## Kết luận

Thuộc tính `depends` cho Ant biết các target cần được thực hiện trước target đang xét. Khi biểu diễn các target thành đồ thị, mỗi target là một đỉnh và mỗi quan hệ tiên quyết là một cạnh. Ant giải quyết cả phụ thuộc trực tiếp lẫn phụ thuộc bắc cầu, xử lý các phụ thuộc theo thứ tự khai báo và chỉ thực hiện một target tối đa một lần trong một lần gọi build. Hãy bảo đảm đồ thị không có chu trình, tên target hợp lệ và quan hệ phụ thuộc phản ánh đúng dữ liệu mà từng bước cần.
