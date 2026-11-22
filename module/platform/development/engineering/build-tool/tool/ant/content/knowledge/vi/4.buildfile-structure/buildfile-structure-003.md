# Phân biệt target, task và khai báo kiểu dữ liệu trong `build.xml`

Trong Apache Ant, tệp `build.xml` mô tả cách một dự án được xây dựng bằng các phần tử XML. Khi đọc một buildfile, bạn sẽ thường gặp những tên như `<project>`, `<target>`, `<javac>`, `<copy>`, `<path>` và `<fileset>`. Chúng đều xuất hiện dưới dạng thẻ XML, nhưng không có cùng vai trò.

Ba khái niệm cần phân biệt là:

- **Target**: một mục tiêu hoặc một nhóm bước trong quy trình build. Target gom các công việc có liên quan và có thể phụ thuộc vào target khác.
- **Task**: một thao tác cụ thể mà Ant thực hiện, chẳng hạn tạo thư mục, biên dịch mã nguồn, sao chép tệp hoặc đóng gói JAR.
- **Datatype (kiểu dữ liệu của Ant)**: một cấu trúc dữ liệu mô tả thông tin để task sử dụng, chẳng hạn danh sách đường dẫn classpath hoặc tập hợp tệp cần xử lý.

Ví dụ, target `compile` có thể chứa task `<javac>`. Task này nhận một datatype `<path>` làm classpath để tìm các thư viện cần thiết. Target tổ chức công việc, task thực hiện công việc, còn datatype cung cấp dữ liệu cho công việc đó.

## 1. Cấu trúc cơ bản của một buildfile

Một buildfile thông thường bắt đầu bằng phần tử gốc `<project>`:

```xml
<project name="first-java" default="compile" basedir=".">
    <property name="src.dir" location="src" />
    <property name="build.dir" location="build" />

    <target name="compile">
        <mkdir dir="${build.dir}/classes" />
        <javac
            srcdir="${src.dir}"
            destdir="${build.dir}/classes"
            includeantruntime="false" />
    </target>
</project>
```

Trong ví dụ trên:

- `<project>` là phần tử gốc của buildfile. Thuộc tính `name` đặt tên dự án, `default` chỉ định target mặc định và `basedir` xác định thư mục cơ sở dùng để phân giải các đường dẫn tương đối.
- Hai phần tử `<property>` đặt các thuộc tính dùng lại trong buildfile. Giá trị của chúng có thể được tham chiếu bằng cú pháp `${tên-thuộc-tính}`.
- `<target name="compile">` khai báo một target tên `compile`.
- `<mkdir>` và `<javac>` là các task nằm bên trong target. Ant thực hiện chúng khi target được chạy.

Nếu chạy lệnh `ant compile` tại thư mục chứa `build.xml`, Ant sẽ thực hiện target `compile`. Nếu chỉ chạy `ant`, Ant sẽ chọn target được khai báo trong thuộc tính `default` của `<project>`.

## 2. Target: mục tiêu tổ chức các bước build

Target là đơn vị tổ chức quy trình trong buildfile. Một target thường đại diện cho một giai đoạn có ý nghĩa, ví dụ:

- `clean`: xóa kết quả build cũ.
- `init`: chuẩn bị các thư mục cần thiết.
- `compile`: biên dịch mã nguồn.
- `test`: chạy kiểm thử.
- `jar`: đóng gói các lớp đã biên dịch thành tệp JAR.
- `run`: chạy ứng dụng.

Khai báo target có dạng tổng quát:

```xml
<target
    name="tên-target"
    depends="target-phụ-thuộc"
    description="Mô tả ngắn"
    if="tên-property"
    unless="tên-property">
    <!-- Các task được thực hiện trong target -->
</target>
```

Các thuộc tính thường dùng:

| Thuộc tính | Ý nghĩa |
|---|---|
| `name` | Tên định danh của target. Đây là tên được dùng khi gọi target hoặc khai báo trong `depends`. |
| `depends` | Danh sách target cần chạy trước target hiện tại, phân cách bằng dấu phẩy. |
| `description` | Mô tả target, hữu ích khi liệt kê trợ giúp của dự án. |
| `if` | Chỉ chạy target khi property có tên được chỉ định đã tồn tại. |
| `unless` | Chỉ chạy target khi property có tên được chỉ định chưa tồn tại. |

`name` là thuộc tính quan trọng nhất vì Ant cần tên target để xác định mục tiêu cần thực hiện. Nên đặt tên ngắn gọn và thể hiện hành động hoặc giai đoạn, ví dụ `compile`, `test`, `package`.

### 2.1. Quan hệ phụ thuộc giữa các target

Một target có thể cần kết quả từ target khác. Thuộc tính `depends` mô tả thứ tự phụ thuộc đó. Ví dụ:

```xml
<project name="demo" default="jar">
    <property name="build.dir" location="build" />

    <target name="init">
        <mkdir dir="${build.dir}/classes" />
    </target>

    <target name="compile" depends="init">
        <echo message="Biên dich ma nguon" />
    </target>

    <target name="jar" depends="compile">
        <echo message="Dong goi ung dung" />
    </target>
</project>
```

Khi gọi `ant jar`, Ant xử lý các target theo quan hệ phụ thuộc:

```text
jar
 |
 +-- cần compile trước
       |
       +-- cần init trước

Thứ tự thực hiện: init -> compile -> jar
```

`depends` nhận tên target, không nhận tên task. Trong ví dụ, `jar` phụ thuộc vào target `compile`, còn `compile` phụ thuộc vào target `init`.

Nếu một target phụ thuộc vào nhiều target, có thể liệt kê chúng bằng dấu phẩy:

```xml
<target name="package" depends="compile,test">
    <echo message="Chuan bi dong goi" />
</target>
```

Ant xử lý các target phụ thuộc theo thứ tự được khai báo, cùng với các phụ thuộc bắc cầu của chúng. Trong một lần gọi Ant, một target chỉ được thực hiện tối đa một lần, kể cả khi nhiều nhánh phụ thuộc cùng yêu cầu target đó.

### 2.2. Điều kiện `if` và `unless`

Target có thể được bật hoặc bỏ qua dựa trên sự tồn tại của property:

```xml
<target name="deploy" if="deploy.enabled">
    <echo message="Thuc hien deploy" />
</target>

<target name="local-report" unless="ci.build">
    <echo message="Day la build local" />
</target>
```

Trong ví dụ:

- `deploy` chỉ được thực hiện khi property `deploy.enabled` đã được đặt.
- `local-report` chỉ được thực hiện khi property `ci.build` chưa được đặt.

Điều kiện ở đây kiểm tra property có tồn tại hay không; nó không phải biểu thức so sánh giá trị như `deploy.enabled == true`. Có thể đặt property từ buildfile hoặc truyền từ dòng lệnh, ví dụ:

```bash
ant -Ddeploy.enabled=true deploy
```

Lưu ý rằng target bị bỏ qua do điều kiện không thỏa mãn vẫn có thể được xem là đã xử lý trong lần chạy đó; điều kiện không phải cơ chế lặp lại target cho đến khi đúng.

### 2.3. Target không phải task

Target không tự thực hiện một thao tác cụ thể. Nó tạo một phạm vi để nhóm các task và xác định khi nào nhóm đó được chạy. Chẳng hạn:

```xml
<target name="clean">
    <delete dir="build" />
</target>
```

`clean` là tên target; `<delete>` mới là task xóa thư mục. Khi gọi `ant clean`, Ant chọn target `clean`, rồi thực hiện task `<delete>` bên trong.

## 3. Task: thao tác mà Ant thực hiện

Task là đơn vị công việc cụ thể. Mỗi task thường được biểu diễn bằng một phần tử XML nằm trong target. Tên phần tử cho Ant biết cần gọi thao tác nào; thuộc tính và phần tử con cung cấp tham số cho thao tác đó.

Một số task thường gặp:

| Task | Công dụng | Ví dụ |
|---|---|---|
| `<echo>` | In thông báo ra màn hình build. | `<echo message="Building..." />` |
| `<mkdir>` | Tạo thư mục. | `<mkdir dir="build/classes" />` |
| `<delete>` | Xóa tệp hoặc thư mục. | `<delete dir="build" />` |
| `<copy>` | Sao chép tệp hoặc thư mục. | `<copy file="app.properties" todir="build" />` |
| `<javac>` | Biên dịch mã nguồn Java. | `<javac srcdir="src" destdir="build/classes" />` |
| `<jar>` | Tạo tệp JAR. | `<jar destfile="build/app.jar" basedir="build/classes" />` |
| `<java>` | Khởi chạy lớp Java hoặc chương trình Java. | `<java classname="com.example.Main" fork="true" />` |

Ví dụ target có nhiều task:

```xml
<target name="prepare">
    <echo message="Chuan bi thu muc build" />
    <mkdir dir="build" />
    <mkdir dir="build/classes" />
</target>
```

Khi target `prepare` được gọi, Ant thực hiện các task theo thứ tự chúng xuất hiện trong target: in thông báo, tạo thư mục `build`, rồi tạo thư mục `build/classes`.

### 3.1. Thuộc tính và phần tử con của task

Task nhận dữ liệu thông qua thuộc tính XML. Ví dụ:

```xml
<copy file="config/app.properties" todir="build" overwrite="true" />
```

Trong đó:

- `file` chỉ định tệp nguồn.
- `todir` chỉ định thư mục đích.
- `overwrite` yêu cầu ghi đè tệp đích nếu cần.

Một số task còn nhận cấu hình qua phần tử con. Ví dụ, task `<javac>` có thể nhận classpath qua phần tử `<classpath>`:

```xml
<javac srcdir="src" destdir="build/classes" includeantruntime="false">
    <classpath>
        <pathelement location="lib/example.jar" />
    </classpath>
</javac>
```

Ở đây `<javac>` là task. Phần tử `<classpath>` cung cấp cấu hình đường dẫn cho task, còn `<pathelement>` mô tả một mục trên đường dẫn. Các phần tử con này được diễn giải theo cấu trúc mà task hỗ trợ; không phải cứ là một thẻ XML bên trong target thì đều là task độc lập.

### 3.2. Task tích hợp sẵn và task tự định nghĩa

Ant cung cấp nhiều task tích hợp sẵn như `javac`, `copy`, `delete`, `jar` và `java`. Ngoài ra, Ant cho phép đăng ký task do dự án hoặc thư viện bên ngoài cung cấp bằng task `<taskdef>`.

Ví dụ về hình thức khai báo:

```xml
<taskdef name="mycheck" classname="com.example.ant.MyCheckTask" />

<target name="verify">
    <mycheck />
</target>
```

`<taskdef>` đăng ký tên task `mycheck` với lớp triển khai tương ứng. Sau khi được đăng ký và lớp triển khai có thể được nạp, `<mycheck>` có thể được sử dụng như một task trong target. Đây là cơ chế mở rộng Ant; bài thực hành cơ bản thường chỉ cần các task có sẵn.

## 4. Datatype: cấu trúc dữ liệu dùng để cấu hình task

Datatype trong Ant là cấu trúc mô tả dữ liệu mà task có thể sử dụng. Datatype không đại diện cho một mục tiêu build và cũng không trực tiếp thực hiện công việc như task.

Một số datatype thường gặp:

| Datatype | Dữ liệu được mô tả | Trường hợp sử dụng |
|---|---|---|
| `path` | Một danh sách đường dẫn gồm thư mục, tệp JAR hoặc các mục đường dẫn khác. | Cấu hình classpath cho trình biên dịch hoặc chương trình Java. |
| `fileset` | Tập hợp tệp được chọn từ một thư mục theo các mẫu include/exclude. | Chọn tệp nguồn, tài nguyên hoặc tệp cần sao chép. |
| `dirset` | Tập hợp thư mục được chọn theo mẫu. | Chọn các thư mục cần xử lý. |
| `patternset` | Các quy tắc chọn hoặc loại trừ tên tệp. | Dùng lại quy tắc include/exclude trong nhiều fileset. |
| `mapper` | Quy tắc ánh xạ tên hoặc đường dẫn đầu vào sang tên hoặc đường dẫn đầu ra. | Đổi tên tệp khi sao chép hoặc xử lý hàng loạt. |
| `filterset` | Các cặp bộ lọc thay thế nội dung văn bản. | Thay placeholder trong tệp cấu hình khi copy. |

Datatype thường xuất hiện dưới dạng phần tử con của task hoặc được khai báo riêng để nhiều task cùng tham chiếu. Các datatype phổ biến có thể có thuộc tính `id` để định danh và được tham chiếu lại bằng `refid`.

## 5. Khai báo và sử dụng datatype

### 5.1. Khai báo datatype lồng trong task

Nếu chỉ một task cần dữ liệu, bạn có thể khai báo datatype ngay bên trong task đó. Ví dụ:

```xml
<target name="compile">
    <javac srcdir="src" destdir="build/classes" includeantruntime="false">
        <classpath>
            <pathelement location="lib/example.jar" />
            <pathelement location="build/classes" />
        </classpath>
    </javac>
</target>
```

`<classpath>` là cấu trúc dữ liệu đường dẫn mà `<javac>` sử dụng. Hai phần tử `<pathelement>` mô tả hai mục trên đường dẫn: tệp thư viện và thư mục chứa các lớp đã biên dịch. Cấu trúc này chỉ được khai báo tại nơi task cần dùng.

### 5.2. Khai báo datatype có `id` để dùng lại

Nếu nhiều task cần cùng một dữ liệu, hãy khai báo datatype ở cấp project và gán `id`:

```xml
<project name="demo" default="compile">
    <path id="compile.classpath">
        <pathelement location="lib/example.jar" />
        <pathelement location="build/classes" />
    </path>

    <target name="compile">
        <javac srcdir="src" destdir="build/classes" includeantruntime="false">
            <classpath refid="compile.classpath" />
        </javac>
    </target>
</project>
```

Trong ví dụ:

- `<path>` khai báo một datatype đường dẫn.
- `id="compile.classpath"` đặt tên tham chiếu cho datatype đó.
- `<classpath refid="compile.classpath" />` yêu cầu task sử dụng cấu trúc đường dẫn đã khai báo.

`id` và `refid` giúp tránh lặp lại cùng một cấu hình ở nhiều vị trí. Khi classpath thay đổi, bạn chỉ cần cập nhật khai báo dùng chung.

### 5.3. Kết hợp `fileset` và `path`

Classpath thường cần chứa tất cả tệp JAR trong thư mục thư viện. Thay vì liệt kê từng JAR, bạn có thể dùng `fileset` bên trong `path`:

```xml
<path id="compile.classpath">
    <fileset dir="lib">
        <include name="**/*.jar" />
    </fileset>
</path>
```

Ý nghĩa:

- `path` là datatype đường dẫn tổng hợp.
- `fileset` chọn các tệp từ thư mục `lib`.
- `include` đưa các tệp có tên khớp mẫu `**/*.jar` vào tập hợp. Mẫu này chọn các tệp JAR trong thư mục `lib` và các thư mục con.

Sau đó task có thể tham chiếu đường dẫn bằng `refid`:

```xml
<javac srcdir="src" destdir="build/classes" includeantruntime="false">
    <classpath refid="compile.classpath" />
</javac>
```

Một `fileset` cũng có thể được dùng trực tiếp trong task như `<copy>` hoặc `<delete>` khi task hỗ trợ kiểu dữ liệu này:

```xml
<copy todir="build/resources">
    <fileset dir="resources">
        <include name="**/*.properties" />
        <exclude name="private/**" />
    </fileset>
</copy>
```

Trong ví dụ, `<copy>` là task sao chép; `<fileset>` mô tả các tệp nguồn; `<include>` và `<exclude>` là các quy tắc chọn tệp bên trong fileset. Các phần tử con này cấu hình dữ liệu đầu vào cho task copy.

## 6. Phân biệt `id`, `refid` và property

Khi đọc buildfile, bạn có thể thấy cả `id`, `refid` và property. Chúng đều giúp tái sử dụng thông tin nhưng có vai trò khác nhau.

| Thành phần | Vai trò | Cách sử dụng |
|---|---|---|
| `id` | Đặt định danh cho một đối tượng datatype để có thể tham chiếu. | `id="compile.classpath"` |
| `refid` | Tham chiếu đến datatype đã được định danh. | `refid="compile.classpath"` |
| Property | Lưu một giá trị dạng thuộc tính để thay thế trong buildfile. | `${src.dir}` |

Ví dụ kết hợp:

```xml
<property name="lib.dir" location="lib" />

<path id="compile.classpath">
    <fileset dir="${lib.dir}">
        <include name="*.jar" />
    </fileset>
</path>

<target name="compile">
    <javac srcdir="src" destdir="build/classes" includeantruntime="false">
        <classpath refid="compile.classpath" />
    </javac>
</target>
```

Ở đây, `${lib.dir}` thay bằng giá trị property `lib.dir`; `id` đặt tên cho datatype `path`; `refid` kết nối cấu hình path đó với task `javac`.

Property trong Ant thường được đặt theo nguyên tắc chỉ thiết lập một lần: khi một property đã có giá trị, một lần khai báo thông thường sau đó không ghi đè giá trị cũ. Property có thể được đặt từ dòng lệnh bằng `-D`, vì vậy người chạy build có thể truyền giá trị tùy môi trường. Property không phải datatype `path` hay `fileset`; nó lưu giá trị để dùng trong biểu thức `${...}`.

## 7. Phân biệt các phần tử khi đọc `build.xml`

Vì target, task và datatype đều được viết dưới dạng phần tử XML, người mới học dễ nhầm chúng với nhau. Hãy xem một ví dụ tổng hợp:

```xml
<project name="sample" default="compile">
    <property name="src.dir" location="src" />
    <property name="classes.dir" location="build/classes" />

    <path id="app.classpath">
        <pathelement location="lib/example.jar" />
    </path>

    <target name="init">
        <mkdir dir="${classes.dir}" />
    </target>

    <target name="compile" depends="init">
        <javac srcdir="${src.dir}" destdir="${classes.dir}" includeantruntime="false">
            <classpath refid="app.classpath" />
        </javac>
        <echo message="Compile completed" />
    </target>
</project>
```

| Phần tử hoặc thuộc tính | Phân loại | Giải thích |
|---|---|---|
| `<project>` | Phần tử gốc | Chứa cấu hình của toàn bộ buildfile. |
| `<property>` | Task | Đặt giá trị property để dùng trong buildfile. |
| `<path>` | Datatype | Khai báo danh sách đường dẫn. |
| `<pathelement>` | Thành phần datatype | Thêm một mục vào path. |
| `<target>` | Target | Nhóm các task thành mục tiêu build có tên. |
| `depends` | Thuộc tính của target | Khai báo target cần chạy trước. |
| `<mkdir>` | Task | Tạo thư mục. |
| `<javac>` | Task | Biên dịch mã nguồn Java. |
| `<classpath>` | Phần tử cấu hình datatype của task | Cung cấp classpath cho task javac. |
| `refid` | Thuộc tính tham chiếu | Trỏ đến datatype có `id` tương ứng. |
| `<echo>` | Task | In thông báo. |

Trong ví dụ, khi chạy `ant compile`, Ant cần chạy `init` trước do target `compile` khai báo `depends="init"`. Target `init` thực hiện task `mkdir`; target `compile` thực hiện task `javac` rồi task `echo`. Task `javac` lấy classpath từ datatype có `id="app.classpath"`.

Một cách nhận biết nhanh là xem phần tử đang trả lời câu hỏi nào:

- **Khi nào hoặc mục tiêu nào cần chạy?** Hãy tìm `<target>` và các thuộc tính như `name`, `depends`, `if`, `unless`.
- **Ant cần thực hiện thao tác gì?** Hãy tìm task như `<javac>`, `<copy>`, `<mkdir>`, `<delete>`.
- **Task cần nhận tập dữ liệu hoặc đường dẫn nào?** Hãy tìm datatype như `<path>`, `<fileset>`, `<patternset>` và cách tham chiếu `id`/`refid`.

Không nên phân loại một phần tử chỉ dựa trên việc nó nằm trong hay ngoài target. Hãy xét vai trò và ngữ cảnh mà Ant định nghĩa cho phần tử đó. Ví dụ, property task và datatype `path` có thể được khai báo ở cấp project, còn các task thực thi thông thường được đặt trong target.

## 8. Một số nhầm lẫn thường gặp

### Nhầm `depends` với `refid`

`depends` nối các target theo thứ tự thực hiện. `refid` nối một nơi sử dụng với datatype đã được khai báo bằng `id`.

```xml
<target name="compile" depends="init">
    <javac srcdir="src" destdir="build/classes">
        <classpath refid="compile.classpath" />
    </javac>
</target>
```

Ở đây, `init` là tên target phụ thuộc; `compile.classpath` là định danh của datatype. Hai giá trị này không thể thay thế cho nhau.

### Nhầm datatype với task

`<path>` mô tả một tập hợp đường dẫn. Nó không tự biên dịch, sao chép hay chạy chương trình. `<javac>` mới là task thực hiện biên dịch và nhận path làm dữ liệu đầu vào.

### Nghĩ rằng mọi thẻ con đều là task

Trong đoạn sau, chỉ `<javac>` là task thực hiện biên dịch:

```xml
<javac srcdir="src" destdir="build/classes">
    <classpath>
        <pathelement location="lib/example.jar" />
    </classpath>
</javac>
```

`classpath` và `pathelement` là cấu hình dữ liệu cho task `javac`. Chúng không phải các thao tác độc lập được chạy như `mkdir` hay `copy`.

### Nghĩ rằng target tự chạy theo thứ tự xuất hiện trong file

Ant không đơn giản chạy tất cả target từ trên xuống dưới. Khi gọi một target, Ant xét target được yêu cầu và các target trong quan hệ phụ thuộc `depends`. Bên trong từng target, các task được thực hiện theo thứ tự khai báo. Do đó, hãy mô tả quan hệ phụ thuộc rõ ràng thay vì dựa vào vị trí của target trong file.

### Nhầm tên target với tên task

Lệnh `ant compile` chọn target có `name="compile"`. Nó không có nghĩa Ant tìm một task tên `compile`. Một target có thể chứa task `<javac>`, nhưng tên target và tên task là hai định danh riêng.

## 9. Bài thực hành

Hãy tạo một buildfile nhỏ để vận dụng cả ba khái niệm.

### Yêu cầu

Tạo cấu trúc dự án:

```text
ant-sample/
├── build.xml
├── src/
│   └── Hello.java
└── lib/
    └── (các thư viện JAR nếu có)
```

Tệp `src/Hello.java`:

```java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello from Ant!");
    }
}
```

Tạo `build.xml`:

```xml
<project name="ant-sample" default="compile" basedir=".">
    <property name="src.dir" location="src" />
    <property name="build.dir" location="build" />
    <property name="classes.dir" location="${build.dir}/classes" />

    <path id="compile.classpath">
        <fileset dir="lib" includes="*.jar" />
    </path>

    <target name="clean" description="Remove generated files">
        <delete dir="${build.dir}" />
    </target>

    <target name="init">
        <mkdir dir="${classes.dir}" />
    </target>

    <target name="compile" depends="init" description="Compile Java sources">
        <javac
            srcdir="${src.dir}"
            destdir="${classes.dir}"
            includeantruntime="false"
            encoding="UTF-8">
            <classpath refid="compile.classpath" />
        </javac>
    </target>
</project>
```

Trong buildfile này:

- `clean`, `init` và `compile` là ba target.
- `delete`, `mkdir` và `javac` là các task.
- `compile.classpath` là datatype `path`; `fileset` mô tả các tệp JAR trong thư mục `lib`.
- `compile` phụ thuộc vào `init`, nên thư mục đầu ra được tạo trước khi biên dịch.
- Các property giúp quản lý đường dẫn ở một nơi và tái sử dụng chúng.

Mở Terminal tại thư mục `ant-sample` và chạy:

```bash
ant compile
```

Sau khi chạy thành công, lớp đã biên dịch nằm trong `build/classes`. Có thể chạy ứng dụng bằng:

```bash
java -cp build/classes Hello
```

Nếu muốn xóa kết quả build, chạy:

```bash
ant clean
```

Thử thay đổi `default="compile"` thành `default="clean"`, sau đó chạy `ant` để quan sát target mặc định được chọn. Tiếp theo, thêm một target `package` phụ thuộc vào `compile` và sử dụng task `<jar>` để đóng gói lớp đã biên dịch.

### Câu hỏi tự kiểm tra

1. Trong `build.xml`, phần tử nào khai báo một target và thuộc tính nào đặt tên cho target?
2. Vì sao `<javac>` được xem là task còn `<target>` không phải task?
3. Khi chạy `ant compile`, `depends="init"` có tác dụng gì?
4. Datatype `path` dùng để mô tả loại dữ liệu nào?
5. `id="compile.classpath"` và `refid="compile.classpath"` liên hệ với nhau như thế nào?
6. Vì sao `<fileset>` có thể xuất hiện bên trong `<path>` hoặc bên trong task `<copy>`?
7. Property `${classes.dir}` khác datatype có `id` ở điểm nào?

## Kết luận

Khi đọc hoặc viết `build.xml`, hãy phân biệt rõ ba vai trò. Target xác định mục tiêu và quan hệ phụ thuộc của quy trình build. Task thực hiện thao tác cụ thể như biên dịch, sao chép, tạo thư mục hoặc đóng gói. Datatype mô tả dữ liệu mà task cần, ví dụ classpath hoặc tập hợp tệp. Các thuộc tính `depends`, `id`, `refid` và property giúp kết nối những phần này để buildfile dễ đọc, tái sử dụng và bảo trì hơn.
