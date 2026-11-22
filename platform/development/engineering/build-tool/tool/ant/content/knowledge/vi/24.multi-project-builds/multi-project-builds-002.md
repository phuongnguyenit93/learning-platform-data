# Gọi build file khác bằng task `<ant>`

Khi một hệ thống có nhiều module hoặc nhiều dự án con, mỗi dự án thường có build file riêng để quản lý source, dependency và artifact của nó. Build file cấp cao có thể điều phối toàn bộ quy trình bằng cách gọi build file của từng module. Apache Ant cung cấp task `<ant>` cho mục đích này.

Task `<ant>` tạo một Ant project con, nạp build file được chỉ định và thực thi target trong project đó. Nhờ vậy, build file gốc có thể gọi target `clean`, `compile`, `jar` hoặc `test` của một dự án con mà không phải sao chép các task bên trong dự án đó.

Ví dụ cấu trúc workspace:

```text
workspace/
├── build.xml
├── common/
│   └── build.xml
├── customer-service/
│   └── build.xml
└── invoice-service/
    └── build.xml
```

Build file ở thư mục gốc có thể gọi lần lượt các build file con. Mỗi module vẫn quản lý các target và cấu hình riêng; build file gốc chỉ điều phối thứ tự và truyền những giá trị cần thiết.

## 1. Cú pháp cơ bản của task `<ant>`

Task `<ant>` thường dùng ba thuộc tính chính:

| Thuộc tính | Ý nghĩa |
|---|---|
| `antfile` | Đường dẫn đến build file cần gọi; mặc định là `build.xml` |
| `dir` | Thư mục làm việc và base directory của project con; mặc định là basedir của project hiện tại |
| `target` | Target cần chạy trong project con; nếu bỏ qua, Ant chạy default target của project con |

Ví dụ build file gốc:

```xml
<project name="workspace" default="build-all" basedir=".">
    <target name="build-common">
        <ant antfile="common/build.xml"
             dir="common"
             target="jar"/>
    </target>

    <target name="build-customer">
        <ant antfile="customer-service/build.xml"
             dir="customer-service"
             target="jar"/>
    </target>

    <target name="build-all" depends="build-common,build-customer"/>
</project>
```

Khi chạy `ant build-all` ở thư mục `workspace`, Ant thực hiện target `build-common`, sau đó `build-customer`. Mỗi task `<ant>` tạo project con từ file tương ứng và gọi target `jar` của project đó.

Trong ví dụ, `antfile` chỉ tới file build, còn `dir` chỉ tới thư mục dự án con. Nên khai báo cả hai khi build file nằm trong một module riêng để đường dẫn tương đối bên trong build file con được phân giải từ thư mục module.

Nếu `antfile` là đường dẫn tương đối, đường dẫn được phân giải theo thư mục làm việc được chọn cho lời gọi `<ant>`. Có thể dùng đường dẫn tuyệt đối bằng Ant property `location` khi workspace có cấu trúc phức tạp:

```xml
<property name="workspace.root" location="."/>
<property name="customer.dir"
          location="${workspace.root}/customer-service"/>

<target name="build-customer">
    <ant antfile="${customer.dir}/build.xml"
         dir="${customer.dir}"
         target="jar"/>
</target>
```

## 2. `dir`, basedir và `useNativeBasedir`

`dir` quyết định base directory mà project con sử dụng khi phân giải đường dẫn tương đối. Ví dụ, nếu build file con có:

```xml
<property name="src.dir" location="src"/>
<property name="classes.dir" location="build/classes"/>
```

và được gọi với `dir="customer-service"`, các đường dẫn này được hiểu tương ứng là `customer-service/src` và `customer-service/build/classes`.

Điều này quan trọng vì `${basedir}` trong build file con là base directory của project con, không phải lúc nào cũng là thư mục chứa build file. Task `<ant>` mặc định dùng `dir` làm base directory. Nếu muốn project con tự dùng giá trị `basedir` được khai báo trong phần tử `<project>` của chính nó, có thể đặt `useNativeBasedir="true"` (Ant 1.8.0 trở lên):

```xml
<ant antfile="customer-service/build.xml"
     dir="${workspace.root}"
     target="jar"
     useNativeBasedir="true"/>
```

Với `useNativeBasedir="true"`, Ant tôn trọng basedir tự khai báo của build file con. Nếu bỏ qua thuộc tính này hoặc đặt `false`, `dir` của task điều khiển basedir của project con. Chỉ bật native basedir khi build file con thực sự cần dựa vào vị trí gốc của chính nó; nếu không, việc truyền `dir` tường minh thường dễ hiểu hơn.

Không nên nhầm `dir` của `<ant>` với việc đổi working directory của tiến trình Ant cha. Task tạo project con với base directory riêng; nó không thay đổi thư mục hiện hành của shell hay của build file cha.

## 3. Gọi default target, một target hoặc nhiều target

Nếu chỉ định `target`, Ant chạy target đó trong project con:

```xml
<ant antfile="common/build.xml"
     dir="common"
     target="test"/>
```

Nếu không chỉ định `target`, Ant chạy default target được khai báo trong `<project>` của build file con:

```xml
<!-- Gọi default target của common/build.xml. -->
<ant antfile="common/build.xml" dir="common"/>
```

Task `<ant>` cũng hỗ trợ các phần tử `<target>` lồng nhau để gọi nhiều target trong cùng project con:

```xml
<ant antfile="customer-service/build.xml" dir="customer-service">
    <target name="clean"/>
    <target name="test"/>
    <target name="jar"/>
</ant>
```

Các target được yêu cầu theo thứ tự khai báo; dependency của từng target vẫn được Ant xử lý theo quy tắc thông thường. Nếu target `test` đã phụ thuộc vào `compile`, Ant sẽ thực hiện dependency đó trước khi chạy `test`.

Với các target độc lập trong cùng một project con, có thể dùng `depends` ở build file cha để điều phối các lời gọi `<ant>`:

```xml
<target name="clean-customer">
    <ant antfile="customer-service/build.xml"
         dir="customer-service"
         target="clean"/>
</target>

<target name="test-customer" depends="clean-customer">
    <ant antfile="customer-service/build.xml"
         dir="customer-service"
         target="test"/>
</target>
```

Chọn cách viết theo mức độ phụ thuộc. Các target có quan hệ rõ ràng có thể dùng `depends`; các target được gọi chung trong một lần chạy project con có thể khai báo bằng các nested `<target>`.

## 4. Truyền Ant property sang project con

Project con có thể cần version, môi trường build, thư mục output hoặc thông tin cấu hình từ project cha. Task `<ant>` có thuộc tính `inheritAll` để điều khiển việc truyền property:

- Mặc định `inheritAll="true"`: tất cả property của project cha được truyền sang project con.
- Với `inheritAll="false"`: chỉ user property được truyền tự động. Các property thông thường của project cha không được truyền; có thể truyền riêng những giá trị cần thiết bằng nested `<property>` hoặc `<propertyset>`.

Ví dụ mặc định kế thừa property:

```xml
<project name="workspace" default="build-module">
    <property name="release.version" value="2.4.0"/>
    <property name="build.profile" value="staging"/>

    <target name="build-module">
        <ant antfile="customer-service/build.xml"
             dir="customer-service"
             target="jar"
             inheritAll="true"/>
    </target>
</project>
```

Trong build file con, có thể sử dụng `${release.version}` và `${build.profile}` nếu các property đó được kế thừa. Vì Ant property là bất biến, property được truyền vào project con có thể ngăn build file con đặt lại cùng tên với giá trị khác.

### Chỉ truyền những property cần thiết

Đối với build nhiều module, truyền tất cả property của project cha có thể làm các build file con phụ thuộc ngầm vào cấu hình bên ngoài. Có thể đặt `inheritAll="false"` rồi khai báo rõ các giá trị cần dùng:

```xml
<project name="workspace" default="build-module">
    <property name="release.version" value="2.4.0"/>
    <property name="build.profile" value="staging"/>
    <property name="workspace.root" location="."/>
    <property name="internal.debug" value="true"/>

    <target name="build-module">
        <ant antfile="customer-service/build.xml"
             dir="customer-service"
             target="jar"
             inheritAll="false">
            <property name="release.version" value="${release.version}"/>
            <property name="build.profile" value="${build.profile}"/>
            <property name="workspace.root" location="${workspace.root}"/>
        </ant>
    </target>
</project>
```

Project con nhận `release.version`, `build.profile` và `workspace.root`; property `internal.debug` không được truyền tự động vì `inheritAll` đã tắt và không có nested property tương ứng.

Có thể dùng `<propertyset>` để chọn một nhóm property theo tên hoặc prefix:

```xml
<ant antfile="customer-service/build.xml"
     dir="customer-service"
     target="jar"
     inheritAll="false">
    <propertyset>
        <propertyref prefix="release."/>
        <propertyref name="build.profile"/>
    </propertyset>
</ant>
```

Propertyset hữu ích khi có nhiều property cùng nhóm như `release.version`, `release.channel` và `release.revision`. Chỉ chọn prefix đủ hẹp để không vô tình truyền cấu hình nội bộ không liên quan.

Lưu ý: property được truyền từ cha có tính chất user property trong project con và không dễ bị ghi đè bằng `<property>` thông thường. Nếu child build cần tự quyết định một giá trị, hãy thống nhất tên property đầu vào riêng, hoặc chỉ truyền những giá trị mà cha thực sự sở hữu.

## 5. Truyền reference sang project con

Ngoài property, Ant còn có các reference như `path`, `fileset`, `mapper` hoặc đối tượng được tạo bởi task khác. Theo mặc định, reference không được kế thừa (`inheritRefs="false"`). Nếu muốn chuyển reference, có thể bật `inheritRefs="true"` hoặc dùng phần tử `<reference>` để truyền rõ ràng.

Ví dụ build file cha định nghĩa một classpath:

```xml
<path id="shared.compile.classpath">
    <pathelement location="lib/common-api.jar"/>
    <pathelement location="lib/logging-api.jar"/>
</path>

<target name="compile-customer">
    <ant antfile="customer-service/build.xml"
         dir="customer-service"
         target="compile"
         inheritAll="false">
        <reference refid="shared.compile.classpath"
                   torefid="shared.compile.classpath"/>
    </ant>
</target>
```

Trong project con, reference có thể được sử dụng bằng `refid`:

```xml
<target name="compile">
    <javac srcdir="src"
           destdir="build/classes"
           includeantruntime="false">
        <classpath refid="shared.compile.classpath"/>
    </javac>
</target>
```

`refid` chỉ định reference ở project cha; `torefid` là tên reference được đăng ký trong project con. Có thể bỏ `torefid` khi muốn dùng cùng tên theo quy tắc mặc định của task. Truyền reference rõ ràng giúp project con khai báo được dependency build mà nó cần thay vì phụ thuộc vào mọi reference của project cha.

Nếu bật `inheritRefs="true"`, tất cả reference đủ điều kiện từ project cha sẽ được chuyển sang project con. Cách này tiện cho một build nội bộ có cấu trúc thống nhất, nhưng có thể làm child build phụ thuộc vào nhiều reference không được thể hiện trong chính lời gọi. Với build nhiều module, nested `<reference>` thường giúp quan hệ phụ thuộc rõ hơn.

## 6. Ghi output của project con ra file

Thuộc tính `output` của task `<ant>` cho phép ghi output của lần gọi project con vào một file:

```xml
<target name="build-customer">
    <mkdir dir="build/logs"/>

    <ant antfile="customer-service/build.xml"
         dir="customer-service"
         target="jar"
         output="build/logs/customer-build.log"/>
</target>
```

Đường dẫn tương đối của `output` được phân giải theo project hiện tại. Việc ghi log riêng giúp phân tích lỗi của từng module trong một build lớn. Nếu cần log đầy đủ từ toàn bộ workspace, có thể cấu hình logger của Ant ở cấp tiến trình thay vì tạo một file riêng cho mỗi lời gọi.

## 7. Ví dụ điều phối nhiều module

Ví dụ sau ghép property truyền tường minh, target con và log riêng thành một build file gốc:

```xml
<project name="workspace" default="build-all" basedir=".">
    <property name="release.version" value="2.4.0"/>
    <property name="build.profile" value="production"/>
    <property name="workspace.root" location="."/>
    <property name="logs.dir" location="build/logs"/>

    <target name="clean-all">
        <ant antfile="common/build.xml"
             dir="common"
             target="clean"
             inheritAll="false"/>
        <ant antfile="customer-service/build.xml"
             dir="customer-service"
             target="clean"
             inheritAll="false"/>
        <ant antfile="invoice-service/build.xml"
             dir="invoice-service"
             target="clean"
             inheritAll="false"/>
    </target>

    <target name="build-common" depends="clean-all">
        <ant antfile="common/build.xml"
             dir="common"
             target="jar"
             inheritAll="false"
             output="${logs.dir}/common.log">
            <property name="release.version" value="${release.version}"/>
        </ant>
    </target>

    <target name="build-customer" depends="build-common">
        <ant antfile="customer-service/build.xml"
             dir="customer-service"
             target="jar"
             inheritAll="false"
             output="${logs.dir}/customer.log">
            <property name="release.version" value="${release.version}"/>
            <property name="build.profile" value="${build.profile}"/>
        </ant>
    </target>

    <target name="build-invoice" depends="build-common">
        <ant antfile="invoice-service/build.xml"
             dir="invoice-service"
             target="jar"
             inheritAll="false"
             output="${logs.dir}/invoice.log">
            <property name="release.version" value="${release.version}"/>
            <property name="build.profile" value="${build.profile}"/>
        </ant>
    </target>

    <target name="build-all" depends="build-customer,build-invoice"/>
</project>
```

Trong ví dụ này, `clean-all` dọn ba module. `build-common` tạo thư viện dùng chung. Hai module ứng dụng phụ thuộc vào `build-common`, nên Ant chỉ cần thực hiện target đó một lần trong lượt build này trước khi build từng ứng dụng. Các property được truyền rõ ràng cho child project, còn log của mỗi module được ghi riêng.

Đây là một mẫu điều phối; tên target và đường dẫn phải khớp với build file con thực tế. Mỗi build file con cần tự khai báo target `clean` hoặc `jar` tương ứng và biết cách dùng các property đầu vào được truyền.

## 8. Phân biệt `<ant>`, `depends`, `<antcall>` và `<subant>`

Các cơ chế này đều có thể tổ chức thứ tự build, nhưng phạm vi khác nhau:

| Cơ chế | Phạm vi | Dùng khi |
|---|---|---|
| `depends` | Target khác trong cùng Ant project | Các bước thuộc cùng một build file và cần quan hệ phụ thuộc rõ ràng |
| `<ant>` | Một Ant project/build file khác | Cần gọi build file của module hoặc dự án con cụ thể |
| `<antcall>` | Target khác trong cùng build file, chạy trong project context mới | Cần gọi lại một target của cùng build file với tham số riêng |
| `<subant>` | Nhiều build file trong một nhóm thư mục hoặc fileset | Cần chạy cùng target trên nhiều subproject được chọn |

Ví dụ `depends`:

```xml
<target name="jar" depends="compile">
    <!-- Tạo JAR sau khi compile hoàn tất. -->
</target>
```

Ví dụ `<antcall>`:

```xml
<target name="build-release">
    <antcall target="package">
        <param name="release.version" value="2.4.0"/>
    </antcall>
</target>
```

Ví dụ `<subant>` để chạy target `clean` trên nhiều dự án con:

```xml
<subant target="clean" genericantfile="build.xml">
    <fileset dir="modules">
        <include name="*/build.xml"/>
    </fileset>
</subant>
```

`<ant>` thích hợp khi cần chỉ rõ một build file con và truyền cấu hình/reference cho nó. Nếu cùng một target cần chạy trên nhiều thư mục module, `<subant>` có thể giảm số lời gọi lặp lại. Không nên dùng `<ant>` chỉ để thay thế `depends` trong cùng project vì nó tạo một project con mới và làm luồng build khó theo dõi hơn.

## 9. Những lỗi thường gặp và cách xử lý

1. **Không tìm thấy build file con.** Kiểm tra `antfile`, `dir` và working directory của project cha. Dùng Ant `location` để tạo đường dẫn tuyệt đối nếu cần.
2. **Không tìm thấy target.** Kiểm tra tên target trong build file con, bao gồm cả chữ hoa/chữ thường. Nếu bỏ `target`, Ant chạy default target của project con.
3. **Đường dẫn trong project con trỏ sai.** Xem giá trị basedir thực tế. Kiểm tra `dir` và `useNativeBasedir`; `${basedir}` trong child project phụ thuộc cách task `<ant>` tạo project con.
4. **Project con không nhận property.** Kiểm tra `inheritAll`. Khi đặt `false`, truyền các property cần thiết bằng nested `<property>` hoặc `<propertyset>`.
5. **Project con không thấy path/reference.** Reference mặc định không được kế thừa. Dùng nested `<reference>` hoặc bật `inheritRefs="true"` nếu thật sự muốn truyền toàn bộ reference.
6. **Property con không thể ghi đè giá trị từ cha.** Ant property là immutable; property truyền vào project con có thể được xem như user property. Chọn tên property đầu vào rõ ràng và quyết định giá trị nào do cha quản lý.
7. **Build file gọi lẫn nhau tạo vòng lặp.** Tránh để project A gọi B rồi B lại gọi A theo đường đi không kết thúc. Xác định một build file điều phối cấp cao và giữ dependency một chiều.
8. **Gọi target con nhiều lần làm build chậm.** Rà soát dependency giữa target cha và các lời gọi `<ant>`. Nếu nhiều module cùng cần một artifact, tạo target chung ở cấp điều phối và cho các target module phụ thuộc vào nó.
9. **Không tìm thấy log output.** Kiểm tra đường dẫn `output`, quyền ghi và thư mục cha đã tồn tại. Dùng đường dẫn rõ ràng từ project cha.
10. **Nhầm `<ant>` với một tiến trình Ant độc lập.** Task tạo project Ant con trong lần chạy Ant hiện tại; nó không phải cách cô lập một JVM mới. Nếu cần một tiến trình hoặc JDK riêng, hãy cân nhắc gọi executable bằng `<exec>`.

## 10. Quy trình thiết kế build nhiều dự án

Khi tổ chức một workspace có nhiều build file, có thể thực hiện theo các bước:

1. Đặt mỗi module trong thư mục riêng và xác định target công khai như `clean`, `compile`, `test`, `jar`.
2. Tạo một build file gốc để điều phối các module theo thứ tự phụ thuộc.
3. Dùng `antfile` và `dir` để chỉ rõ build file và base directory của từng module.
4. Chọn target cần gọi; nếu cần default target, bỏ thuộc tính `target`.
5. Quyết định property nào được kế thừa tự động và property nào phải truyền tường minh qua `inheritAll`.
6. Truyền reference bằng nested `<reference>` hoặc `inheritRefs` nếu project con cần dùng path/reference của project cha.
7. Dùng `depends` để mô tả thứ tự giữa các target điều phối trong project gốc.
8. Ghi log riêng khi build nhiều module để dễ tìm lỗi.
9. Giữ quan hệ gọi giữa các build file một chiều để tránh vòng lặp.
10. Chỉ chuyển sang `<subant>` khi cần chạy cùng target trên nhiều build file theo một fileset hoặc danh sách thư mục.

## Tài liệu tham khảo

- [Apache Ant Manual — Ant Task](https://ant.apache.org/manual/Tasks/ant.html): gọi build file khác, target, basedir, property và reference inheritance.
- [Apache Ant Manual — AntCall Task](https://ant.apache.org/manual/Tasks/antcall.html): gọi target khác trong cùng build file.
- [Apache Ant Manual — SubAnt Task](https://ant.apache.org/manual/Tasks/subant.html): gọi target trên nhiều subproject.
- [Apache Ant Manual — Property Task](https://ant.apache.org/manual/Tasks/property.html): khai báo property và các cơ chế truyền giá trị cấu hình.
