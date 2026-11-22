# Tái sử dụng đường dẫn bằng refid và classpathref

Trong Apache Ant, nhiều task cần sử dụng cùng một danh sách đường dẫn. Khi biên dịch Java, task `javac` cần biết nơi tìm các class và thư viện phụ thuộc. Khi chạy ứng dụng, task `java` cũng cần một classpath phù hợp. Nếu khai báo lại danh sách JAR ở từng task, cấu hình dễ bị trùng lặp và có thể lệch nhau khi dependency thay đổi.

Ant giải quyết vấn đề này bằng data type `path` và cơ chế reference. Ta định nghĩa một path có tên bằng `id`, sau đó tái sử dụng nó bằng `refid` hoặc thuộc tính tiện dụng `classpathref` của task hỗ trợ classpath. Cách làm này giúp build script có một nơi quản lý đường dẫn và nhiều task cùng sử dụng một cấu hình nhất quán.

## 1. Khai báo path có id

`path` là data type mô tả một danh sách đường dẫn. Có thể khai báo nó ở cấp project, bên ngoài các target, rồi gán một tên duy nhất bằng thuộc tính `id`.

```xml
<project name="catalog-app" default="compile" basedir=".">
    <property name="lib.dir" location="${basedir}/lib"/>
    <property name="classes.dir" location="${basedir}/build/classes"/>

    <path id="application.classpath">
        <pathelement location="${classes.dir}"/>
        <fileset dir="${lib.dir}">
            <include name="**/*.jar"/>
        </fileset>
    </path>

    <target name="compile">
        <mkdir dir="${classes.dir}"/>
        <javac srcdir="src/main/java"
               destdir="${classes.dir}"
               includeantruntime="false"
               classpathref="application.classpath"/>
    </target>
</project>
```

Trong ví dụ:

- `<path>` tạo một cấu trúc đường dẫn.
- `id="application.classpath"` đặt tên reference cho cấu trúc đó.
- `<pathelement>` thêm một vị trí cụ thể vào path.
- `<fileset>` tìm các file JAR trong thư mục `lib`.
- `classpathref` yêu cầu task `javac` dùng path đã được định nghĩa.

`path` không phải task biên dịch. Nó chỉ mô tả dữ liệu. Task `javac` mới thực hiện việc biên dịch và sử dụng path làm classpath đầu vào.

## 2. Reference là gì?

Ant có cơ chế lưu các đối tượng được đặt tên trong project. Một data type có thể đăng ký đối tượng của nó bằng `id`; thành phần khác có thể lấy lại đối tượng đó bằng `refid` nếu nó hỗ trợ kiểu reference tương ứng.

Ví dụ đơn giản:

```xml
<path id="shared.libs">
    <pathelement location="lib/common.jar"/>
    <pathelement location="lib/logging.jar"/>
</path>

<path id="compile.path">
    <path refid="shared.libs"/>
    <pathelement location="build/classes"/>
</path>
```

Ở đây, `compile.path` kết hợp path đã khai báo trong `shared.libs` với thư mục class đã biên dịch. Phần tử `<path refid="shared.libs"/>` đưa các phần tử của reference có sẵn vào path mới.

Reference không phải là một property chuỗi. `id` định danh một đối tượng Ant, còn `refid` yêu cầu dùng lại đối tượng đó. Vì vậy, không thể tùy ý thay một reference kiểu `fileset` vào vị trí cần `path`, hoặc ngược lại. Kiểu của reference phải tương thích với phần tử đang nhận nó.

## 3. Dùng refid trong nested classpath

Nhiều task Ant hỗ trợ nested element có tên `classpath`. Bên trong phần tử đó, có thể dùng `refid` để tham chiếu path đã định nghĩa.

```xml
<path id="compile.classpath">
    <fileset dir="lib">
        <include name="**/*.jar"/>
    </fileset>
</path>

<target name="compile">
    <javac srcdir="src/main/java"
           destdir="build/classes"
           includeantruntime="false">
        <classpath refid="compile.classpath"/>
    </javac>
</target>
```

Trong trường hợp này, `<classpath>` là nested path-like element của task `javac`. `refid` liên kết nó với reference `compile.classpath`. Có thể dùng cách này khi muốn nhìn thấy rõ classpath ngay bên trong task hoặc khi task hỗ trợ nested classpath nhưng không có thuộc tính tham chiếu trực tiếp tương ứng.

Nested classpath cũng có thể tự khai báo phần tử đường dẫn thay vì tham chiếu:

```xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       includeantruntime="false">
    <classpath>
        <pathelement location="build/classes"/>
        <fileset dir="lib">
            <include name="**/*.jar"/>
        </fileset>
    </classpath>
</javac>
```

Hai cách đều mô tả classpath cho compiler. Khi nhiều task cần cùng danh sách, định nghĩa path có `id` rồi tham chiếu thường dễ bảo trì hơn.

## 4. Dùng classpathref trên task

Một số task cung cấp thuộc tính `classpathref` như cách viết ngắn để tham chiếu path có sẵn. Với `javac`, có thể viết:

```xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       includeantruntime="false"
       classpathref="compile.classpath"/>
```

Thay vì mở một nested element `<classpath>`, task nhận trực tiếp tên reference qua thuộc tính `classpathref`.

So sánh hai cách:

```xml
<!-- Cách 1: thuộc tính tiện dụng trên task -->
<javac srcdir="src/main/java"
       destdir="build/classes"
       classpathref="compile.classpath"/>

<!-- Cách 2: nested element dùng refid -->
<javac srcdir="src/main/java" destdir="build/classes">
    <classpath refid="compile.classpath"/>
</javac>
```

Với task `javac`, cả hai đều tham chiếu cùng một path. Hãy kiểm tra tài liệu task cụ thể để biết task đó hỗ trợ thuộc tính `classpathref`, nested `classpath` hay cả hai. Không phải mọi task đều có cùng bộ thuộc tính.

## 5. Tách compile classpath và runtime classpath

Classpath khi biên dịch và khi chạy ứng dụng có thể khác nhau. Compile classpath chứa thư viện cần để compiler phân giải các kiểu được tham chiếu trong source. Runtime classpath chứa class ứng dụng và các thư viện cần thiết khi JVM thực thi.

Ví dụ khai báo hai path riêng:

```xml
<property name="classes.dir" location="${basedir}/build/classes"/>
<property name="lib.dir" location="${basedir}/lib"/>

<path id="third-party.libs">
    <fileset dir="${lib.dir}">
        <include name="**/*.jar"/>
    </fileset>
</path>

<path id="compile.classpath">
    <path refid="third-party.libs"/>
</path>

<path id="runtime.classpath">
    <pathelement location="${classes.dir}"/>
    <path refid="third-party.libs"/>
</path>
```

Task compile sử dụng compile classpath:

```xml
<target name="compile">
    <mkdir dir="${classes.dir}"/>
    <javac srcdir="src/main/java"
           destdir="${classes.dir}"
           includeantruntime="false"
           classpathref="compile.classpath"/>
</target>
```

Task chạy ứng dụng sử dụng runtime classpath:

```xml
<target name="run" depends="compile">
    <java classname="com.example.App"
          fork="true"
          failonerror="true">
        <classpath refid="runtime.classpath"/>
    </java>
</target>
```

Không nên mặc định rằng một classpath dùng cho compile luôn đủ cho runtime. Một thư viện có thể cần ở thời điểm chạy dù source chỉ tham chiếu gián tiếp, hoặc một thư viện chỉ phục vụ compile/test không cần được phát hành cùng ứng dụng.

## 6. Mở rộng path dùng chung bằng path refid

Có thể xây dựng path từ các path nhỏ hơn. Cách này phù hợp khi dự án có nhiều nhóm dependency hoặc nhiều module dùng chung một tập thư viện nền.

```xml
<path id="logging.libs">
    <pathelement location="lib/slf4j-api.jar"/>
    <pathelement location="lib/logging-impl.jar"/>
</path>

<path id="database.libs">
    <pathelement location="lib/jdbc-driver.jar"/>
</path>

<path id="service.classpath">
    <path refid="logging.libs"/>
    <path refid="database.libs"/>
    <pathelement location="build/classes"/>
</path>
```

`service.classpath` kết hợp các phần tử của hai path dependency và thư mục class. Nếu cần thêm một thư viện logging hoặc driver, có thể sửa path con tương ứng mà không phải tìm và sửa mọi task tiêu thụ classpath.

Một path có thể được mở rộng thêm bằng các phần tử khác:

```xml
<path id="test.classpath">
    <path refid="service.classpath"/>
    <pathelement location="build/test-classes"/>
    <fileset dir="lib/test">
        <include name="**/*.jar"/>
    </fileset>
</path>
```

Ở đây, test classpath kế thừa các dependency runtime/compile của service, thêm test classes và thư viện chỉ dùng cho test. Task test có thể tham chiếu `test.classpath` bằng nested `<classpath refid="test.classpath"/>` nếu task runner hỗ trợ cấu trúc này.

## 7. Tái sử dụng classpath ở nhiều task

Một lợi ích lớn của reference là các task có thể cùng sử dụng một path mà không phải khai báo lại danh sách JAR.

```xml
<project name="reuse-classpath" default="run" basedir=".">
    <property name="classes.dir" location="${basedir}/build/classes"/>

    <path id="app.classpath">
        <pathelement location="${classes.dir}"/>
        <fileset dir="${basedir}/lib">
            <include name="**/*.jar"/>
        </fileset>
    </path>

    <target name="compile">
        <mkdir dir="${classes.dir}"/>
        <javac srcdir="${basedir}/src/main/java"
               destdir="${classes.dir}"
               includeantruntime="false"
               classpathref="app.classpath"/>
    </target>

    <target name="run" depends="compile">
        <java classname="com.example.App"
              fork="true"
              failonerror="true">
            <classpath refid="app.classpath"/>
        </java>
    </target>
</project>
```

Trong ví dụ này, `javac` và `java` cùng dùng `app.classpath`. Nếu dự án có sự khác nhau giữa dependency compile và runtime, hãy tạo các path riêng thay vì cố ép mọi task dùng một path chung.

## 8. Hiểu thứ tự phần tử trong classpath

Classpath là danh sách vị trí được JVM hoặc compiler tìm kiếm theo thứ tự. Nếu cùng một class xuất hiện trong nhiều vị trí, thứ tự có thể ảnh hưởng đến class nào được nạp hoặc được dùng để biên dịch.

Ví dụ:

```xml
<path id="application.classpath">
    <pathelement location="build/classes"/>
    <pathelement location="lib/api-v2.jar"/>
    <pathelement location="lib/api-v1.jar"/>
</path>
```

Nếu hai JAR cùng chứa một class có tên đầy đủ giống nhau, việc để cả hai trong classpath có thể tạo ra kết quả khó dự đoán khi thay đổi thứ tự hoặc môi trường. Hãy loại dependency trùng phiên bản và giữ classpath tối thiểu cần thiết.

Khi dùng `fileset` để tìm JAR, thứ tự file có thể phụ thuộc vào quy tắc duyệt resource collection và hệ thống file. Nếu thứ tự là yếu tố quan trọng, hãy khai báo các phần tử cần ưu tiên một cách tường minh thay vì dựa vào thứ tự ngẫu nhiên của thư mục.

## 9. Đường dẫn tương đối và property

Khi định nghĩa path, nên dùng property cho các thư mục quan trọng để tránh lặp lại chuỗi đường dẫn:

```xml
<property name="basedir.root" location="${basedir}"/>
<property name="build.classes" location="${basedir.root}/build/classes"/>
<property name="dependency.dir" location="${basedir.root}/lib"/>

<path id="compile.classpath">
    <pathelement location="${build.classes}"/>
    <fileset dir="${dependency.dir}">
        <include name="**/*.jar"/>
    </fileset>
</path>
```

`location` giúp Ant chuẩn hóa giá trị đường dẫn. Đường dẫn tương đối trong path được hiểu theo base directory của project hoặc theo ngữ cảnh khai báo tương ứng. Dùng property có tên rõ ràng giúp giảm nhầm lẫn khi build được gọi từ thư mục khác hoặc khi nhiều build file được import.

Property của Ant có tính bất biến. Nếu `build.classes` đã được thiết lập trước đó, khai báo lại property cùng tên sẽ không thay thế giá trị cũ. Hãy chọn tên property có phạm vi rõ ràng và đặt giá trị mặc định trước khi tạo path tham chiếu đến chúng.

## 10. Khi nào dùng refid và khi nào dùng classpathref?

Hai cách này có quan hệ nhưng không thay thế nhau trong mọi vị trí:

| Cách viết | Vị trí | Ý nghĩa |
|---|---|---|
| `id="compile.classpath"` | Khi định nghĩa `<path>` | Đăng ký path với tên reference |
| `refid="compile.classpath"` | Trên nested path-like element hoặc data type hỗ trợ reference | Dùng lại đối tượng reference |
| `classpathref="compile.classpath"` | Thuộc tính của task có hỗ trợ classpathref | Gán trực tiếp reference làm classpath của task |
| `<classpath refid="compile.classpath"/>` | Nested element của task hỗ trợ nested classpath | Cung cấp path qua phần tử cấu hình bên trong task |

Ví dụ:

```xml
<path id="compile.classpath">
    <fileset dir="lib">
        <include name="**/*.jar"/>
    </fileset>
</path>

<!-- Task có thuộc tính classpathref -->
<javac srcdir="src" destdir="build/classes"
       classpathref="compile.classpath"/>

<!-- Task nhận nested classpath -->
<java classname="com.example.App" fork="true">
    <classpath refid="compile.classpath"/>
</java>
```

Điểm quan trọng là kiểm tra hợp đồng của task đang dùng. `refid` là cơ chế tham chiếu chung của các cấu trúc hỗ trợ reference; `classpathref` là tên thuộc tính riêng của một số task để nhận path làm classpath.

## 11. Lỗi thường gặp khi tái sử dụng path

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| `Reference ... not found` | Dùng `refid` hoặc `classpathref` trước khi reference được định nghĩa hoặc tên bị sai | Kiểm tra chính tả `id`, thứ tự khai báo và phạm vi project |
| `You must not specify both ...` | Cùng lúc cấu hình thuộc tính classpath và nested classpath theo cách task không cho phép | Chọn một cách cấu hình theo tài liệu task |
| Compiler không tìm thấy class | Path thiếu thư viện hoặc fileset không chọn được JAR | Kiểm tra thư mục, include pattern và path reference |
| Chạy ứng dụng bị `ClassNotFoundException` | Runtime classpath thiếu class ứng dụng hoặc dependency | Tạo runtime path có class output và thư viện cần thiết |
| Một phiên bản class không mong muốn được nạp | Có dependency trùng class hoặc classpath sai thứ tự | Kiểm tra các phần tử trong path và loại JAR trùng |
| Path không phản ánh thư mục mới | Property đường dẫn đã được đặt trước với giá trị khác | Kiểm tra thứ tự nạp property và tính bất biến của property |
| Nested reference sai kiểu | Dùng reference không tương thích với nested element | Kiểm tra data type mà task yêu cầu |

Để chẩn đoán, có thể dùng task `pathconvert` để chuyển một path reference thành chuỗi và in ra log:

```xml
<pathconvert property="compile.classpath.text"
             refid="compile.classpath"/>
<echo message="Compile classpath: ${compile.classpath.text}"/>
```

`pathconvert` hữu ích khi cần nhìn thấy các phần tử đường dẫn sau khi Ant giải quyết path. Không nên in classpath có chứa thông tin nhạy cảm hoặc đường dẫn nội bộ ra log công khai.

## 12. Bài tập thực hành

Tạo dự án có thư mục `src/main/java`, `src/test/java`, `lib`, `lib/test` và `build`.

1. Tạo path `third-party.libs` chứa tất cả JAR trong `lib`.
2. Tạo path `compile.classpath` tham chiếu `third-party.libs` bằng nested `<path refid="..."/>`.
3. Dùng `javac classpathref="compile.classpath"` để biên dịch source chính.
4. Tạo path `test.classpath` gồm compile classpath, thư mục test classes và các JAR trong `lib/test`.
5. Dùng nested `<classpath refid="test.classpath"/>` trong test runner phù hợp.
6. Tạo path `runtime.classpath` có class ứng dụng và các thư viện cần khi chạy.
7. Dùng cùng runtime path cho task `java` và xác nhận chương trình chạy được.
8. Dùng `pathconvert` in classpath ra log, sau đó thử loại một JAR cần thiết để quan sát lỗi và khôi phục lại.

Sau khi thực hành, người học cần tự giải thích được `id` đăng ký reference như thế nào, `refid` tái sử dụng path ở đâu, `classpathref` kết nối path với task ra sao và vì sao compile/test/runtime nên có thể cần các classpath khác nhau.

## 13. Nguyên tắc thiết kế đường dẫn có thể tái sử dụng

Hãy đặt tên path theo mục đích sử dụng như `compile.classpath`, `test.classpath` hoặc `runtime.classpath`. Tách các nhóm dependency có vòng đời khác nhau, sau đó kết hợp chúng bằng nested `<path refid="..."/>` khi cần. Dùng `classpathref` nếu task hỗ trợ thuộc tính đó; dùng nested `<classpath refid="..."/>` khi phù hợp với API của task.

Giữ classpath ngắn, rõ và không có dependency trùng phiên bản. Dùng property để quản lý thư mục, dùng `fileset` để chọn JAR theo quy tắc nhất quán, và dùng `pathconvert` khi cần quan sát đường dẫn đã được Ant giải quyết.

Khi làm theo các nguyên tắc này, build script có thể tái sử dụng cấu hình đường dẫn ở nhiều target mà vẫn thể hiện rõ thư viện nào phục vụ biên dịch, kiểm thử hoặc chạy ứng dụng.
