# Ảnh hưởng của inheritAll, inheritRefs và basedir

Trong Apache Ant, task `<ant>` cho phép một build file gọi build file khác để xây dựng các module hoặc dự án con. Mỗi lần gọi tạo một project context mới, có target, property, reference và thư mục cơ sở riêng. Tuy vậy, project con có thể nhận một phần cấu hình từ project cha.

Ba thuộc tính quyết định phần lớn hành vi này là:

- `inheritAll`: truyền property từ project gọi sang project được gọi.
- `inheritRefs`: truyền reference (đối tượng Ant có `id`) từ project gọi sang project được gọi.
- `dir` và `useNativeBasedir`: xác định thư mục cơ sở (`basedir`) mà project con sử dụng.

Các thuộc tính này độc lập về mục đích. `inheritAll` điều khiển property; `inheritRefs` điều khiển reference; `basedir` điều khiển cách phân giải đường dẫn tương đối. Tuy nhiên, Ant có một quy tắc tương thích lịch sử khiến giá trị `basedir` mặc định còn chịu ảnh hưởng của `inheritAll` và lịch sử gọi build lồng nhau. Vì vậy, khi build nhiều module, nên khai báo `dir` hoặc `useNativeBasedir` một cách tường minh nếu muốn tránh sự phụ thuộc ngầm.

## 1. Project cha gọi project con bằng `<ant>`

Một project có thể gọi build file của module khác bằng task `<ant>`:

~~~xml
<project name="workspace" default="build-all" basedir=".">

    <target name="build-all">
        <ant antfile="modules/core/build.xml" target="compile"/>
        <ant antfile="modules/web/build.xml" target="package"/>
    </target>

</project>
~~~

Mỗi task `<ant>` đọc build file được chỉ định, tạo project con và thực hiện target yêu cầu. Nếu không truyền `target`, Ant dùng default target của project con.

Ví dụ cấu trúc thư mục:

~~~text
workspace/
├── build.xml
└── modules/
    ├── core/
    │   └── build.xml
    └── web/
        └── build.xml
~~~

Project cha có thể gọi build file của `core` và `web`. Hai project con có thể khai báo property, target và reference riêng. Các tùy chọn kế thừa quyết định dữ liệu nào từ project cha được chuyển sang.

`<ant>` phải nằm trong một target khi nó gọi lại chính build file đang chứa task đó. Gọi cùng build file bên ngoài target có thể gây vòng lặp hoặc lỗi thực thi.

## 2. `inheritAll`: truyền property từ project cha

`inheritAll` quyết định các property của project gọi có được truyền sang project con hay không.

**Mặc định:** `true`.

Khi `inheritAll="true"`, Ant truyền tất cả property của project cha sang project con. Các property được truyền sẽ có ưu tiên hơn property cùng tên được khai báo trong build file con, do property thông thường của Ant không thể ghi đè sau khi đã được thiết lập.

Ví dụ, project cha khai báo:

~~~xml
<project name="parent" default="build-child">

    <property name="release.version" value="2.4.0"/>
    <property name="build.mode" value="release"/>

    <target name="build-child">
        <ant antfile="child/build.xml" target="show-config"/>
    </target>

</project>
~~~

Project con:

~~~xml
<project name="child" default="show-config">

    <property name="release.version" value="1.0.0-SNAPSHOT"/>
    <property name="build.mode" value="debug"/>

    <target name="show-config">
        <echo message="Version=${release.version}"/>
        <echo message="Mode=${build.mode}"/>
    </target>

</project>
~~~

Với `inheritAll` mặc định là `true`, project con nhận property từ cha. Kết quả hiển thị là:

~~~text
Version=2.4.0
Mode=release
~~~

Các giá trị `1.0.0-SNAPSHOT` và `debug` trong build file con không thay thế được property đã truyền từ cha.

Điều này hữu ích khi nhiều module phải dùng chung version, build number, môi trường hoặc thư mục output. Tuy nhiên, nó cũng có thể làm project con phụ thuộc ngầm vào cấu hình của cha. Một module được chạy trực tiếp có thể cho kết quả khác khi được gọi từ build tổng.

### 2.1. Khi đặt `inheritAll="false"`

Nếu không muốn project con nhận toàn bộ property thông thường từ cha, đặt:

~~~xml
<ant antfile="child/build.xml"
     target="show-config"
     inheritAll="false"/>
~~~

Khi đó, Ant chỉ truyền các user property, chẳng hạn property được cung cấp trên command line bằng `-D`. Property thông thường được khai báo trong build file cha không tự động được truyền.

Ví dụ chạy build cha:

~~~bash
ant -Dci.build=true build-child
~~~

Ngay cả khi task `<ant>` đặt `inheritAll="false"`, user property `ci.build` vẫn được truyền sang project con. Trong khi đó, property thông thường như `release.version` được khai báo bằng `<property>` trong build file cha sẽ không được kế thừa tự động.

Project con có thể tự khai báo giá trị mặc định:

~~~xml
<project name="child" default="show-config">
    <property name="release.version" value="1.0.0-SNAPSHOT"/>

    <target name="show-config">
        <echo message="Version=${release.version}"/>
        <echo message="CI=${ci.build}"/>
    </target>
</project>
~~~

Nếu `ci.build` không được truyền, biểu thức có thể không có giá trị; build nên kiểm tra sự tồn tại của property trước khi dùng nếu nó là tùy chọn.

`inheritAll="false"` không có nghĩa là project con bị cô lập hoàn toàn. User property vẫn được truyền, và nested `<property>` trong task `<ant>` luôn được chuyển sang project con.

## 3. Truyền property tường minh bằng nested `<property>`

Khi muốn project con nhận một vài giá trị cụ thể mà không kế thừa toàn bộ property cha, dùng nested `<property>`:

~~~xml
<project name="parent" default="build-child">

    <property name="release.version" value="2.4.0"/>
    <property name="debug.enabled" value="false"/>

    <target name="build-child">
        <ant antfile="child/build.xml"
             target="package"
             inheritAll="false">
            <property name="module.version" value="${release.version}"/>
            <property name="debug.enabled" value="${debug.enabled}"/>
        </ant>
    </target>

</project>
~~~

Nested `<property>` được đánh giá trong project gọi. Ví dụ `${release.version}` lấy giá trị từ project cha, rồi Ant truyền giá trị đó cho project con dưới tên `module.version`.

Các nested property này luôn được truyền, kể cả khi `inheritAll="false"`. Chúng có ngữ nghĩa tương tự user property, vì vậy property cùng tên trong project con không thể ghi đè giá trị được truyền.

Có thể truyền file property hoặc các dạng cấu hình mà task `<property>` hỗ trợ:

~~~xml
<ant antfile="child/build.xml" target="package" inheritAll="false">
    <property name="environment" value="staging"/>
    <property file="config/child-build.properties"/>
</ant>
~~~

Đường dẫn file trong nested `<property file="...">` được xử lý theo project gọi. Hãy đặt rõ vị trí file cấu hình và tránh giả định nó được tính từ `basedir` của project con.

Nếu nhiều nested `<property>` cùng đặt một tên, phần tử được khai báo sau cùng sẽ thắng. Đây là quy tắc riêng của nested property trong `<ant>` để tương thích ngược; nó khác với cách các task `<property>` thông thường trong cùng build file xử lý giá trị đã được đặt.

### 3.1. Nested property tiếp tục được truyền qua các build sâu hơn

Từ Ant 1.8.0, property được truyền bằng nested `<property>` của một task `<ant>` sẽ tiếp tục được truyền xuống các project sâu hơn, kể cả khi build trung gian gọi `<ant>` khác với `inheritAll="false"`.

Ví dụ luồng:

~~~text
Build A
  |
  | <ant> nested property: release.channel=stable
  v
Build B (inheritAll=false)
  |
  | <ant inheritAll=false>
  v
Build C
~~~

Build C vẫn nhận `release.channel=stable` do đây là property được truyền tường minh từ A. Điều này hữu ích khi build tổng truyền một tham số release xuyên suốt nhiều tầng module.

## 4. `inheritRefs`: truyền reference từ project cha

Property là giá trị cấu hình, thường được thay bằng `${...}`. Reference là đối tượng Ant có cấu trúc, ví dụ `Path`, `FileSet`, `PatternSet` hoặc một data type khác có `id`.

`inheritRefs` quyết định các reference của project cha có được copy sang project con hay không.

**Mặc định:** `false`.

Ví dụ project cha khai báo:

~~~xml
<project name="parent" default="build-child">

    <path id="shared.compile.path">
        <pathelement location="shared/classes"/>
        <fileset dir="shared/lib">
            <include name="*.jar"/>
        </fileset>
    </path>

    <target name="build-child">
        <ant antfile="child/build.xml"
             target="compile"
             inheritRefs="true"/>
    </target>

</project>
~~~

Project con có thể sử dụng reference được truyền:

~~~xml
<project name="child" default="compile">

    <target name="compile">
        <javac srcdir="src/main/java"
               destdir="build/classes"
               includeantruntime="false">
            <classpath refid="shared.compile.path"/>
        </javac>
    </target>

</project>
~~~

Với `inheritRefs="true"`, Ant copy các reference của project gọi sang project mới. Nếu project con chưa có reference `shared.compile.path`, nó có thể sử dụng reference được truyền từ cha.

### 4.1. Reference cùng tên trong project con không bị ghi đè

Một điểm quan trọng: khi dùng `inheritRefs="true"`, reference đã được định nghĩa trong project con không bị reference cùng tên từ project cha ghi đè.

Ví dụ project con có:

~~~xml
<path id="shared.compile.path">
    <pathelement location="child/lib/child-api.jar"/>
</path>
~~~

Nếu project cha cũng có reference `shared.compile.path` và gọi với `inheritRefs="true"`, định nghĩa của project con được giữ. Reference từ cha chỉ được copy nếu ID đó chưa có trong project con.

Điều này khác với property inheritance: property được truyền từ cha có thể chiếm tên trước và ngăn property cùng tên trong child thay thế nó; reference inheritance mặc định không ghi đè reference child đã khai báo.

## 5. Chỉ truyền reference cần thiết bằng nested `<reference>`

Nếu project con chỉ cần một hoặc một vài reference, có thể truyền tường minh bằng nested `<reference>` thay vì bật `inheritRefs="true"` cho tất cả.

~~~xml
<ant antfile="child/build.xml"
     target="compile"
     inheritRefs="false">
    <reference refid="shared.compile.path"/>
</ant>
~~~

`refid` là ID của reference trong project gọi. Nếu bỏ `torefid`, reference được đăng ký trong project con dưới cùng ID.

Có thể đổi ID khi truyền:

~~~xml
<ant antfile="child/build.xml"
     target="compile"
     inheritRefs="false">
    <reference refid="shared.compile.path"
               torefid="child.external.classpath"/>
</ant>
~~~

Project con sử dụng reference bằng ID mới:

~~~xml
<classpath refid="child.external.classpath"/>
~~~

Cách đổi ID giúp tránh đụng tên với reference nội bộ của project con và thể hiện rõ nguồn gốc của cấu hình được truyền.

Nested `<reference>` có quy tắc ưu tiên khác `inheritRefs="true"`: reference được truyền tường minh sẽ ghi đè reference đã khai báo ngoài target trong project con, nhưng không ghi đè reference được khai báo bên trong target. Do target được thực hiện sau giai đoạn khởi tạo project, cần phân biệt nơi reference được đăng ký khi dự đoán giá trị cuối cùng.

## 6. So sánh `inheritRefs` và nested `<reference>`

| Cách truyền | Phạm vi | Hành vi khi project con có ID trùng |
|---|---|---|
| `inheritRefs="false"` | Không tự copy reference cha | Reference child giữ nguyên |
| `inheritRefs="true"` | Copy tất cả reference cha | Không ghi đè reference đã có trong child |
| Nested `<reference refid="x"/>` | Chỉ copy reference `x` | Ghi đè reference child được khai báo ngoài target; không ghi đè reference tạo bên trong target |
| Nested `<reference refid="x" torefid="y"/>` | Copy `x` của cha dưới ID `y` trong child | Áp dụng quy tắc ưu tiên của nested reference đối với ID `y` |

Nên dùng `inheritRefs="true"` khi project con được thiết kế để dùng chung phần lớn reference của project cha. Dùng nested `<reference>` khi chỉ muốn truyền một cấu trúc cụ thể như classpath, FileSet hoặc path chứa công cụ.

Không nên truyền tất cả reference chỉ vì tiện. Reference có thể phụ thuộc đường dẫn hoặc cấu trúc thư mục của project cha; khi project con chạy độc lập, reference đó có thể không còn phù hợp. Một giao diện project con rõ ràng thường chỉ nhận những reference thật sự cần thiết.

## 7. `basedir` của project con và thuộc tính `dir`

`basedir` là thư mục cơ sở để Ant phân giải các đường dẫn tương đối trong một project. Project con có thể khai báo `basedir` trên `<project>`:

~~~xml
<project name="core" default="compile" basedir=".">
    <target name="compile">
        <echo message="Child basedir=${basedir}"/>
        <javac srcdir="src/main/java" destdir="build/classes"/>
    </target>
</project>
~~~

Khi chạy trực tiếp build file, `basedir="."` được tính tương đối với thư mục chứa build file. Nếu không khai báo `basedir`, Ant mặc định dùng thư mục chứa build file làm base directory.

Khi project cha gọi build con, thuộc tính `dir` của task `<ant>` có thể chỉ định base directory cho project mới:

~~~xml
<ant dir="modules/core"
     antfile="build.xml"
     target="compile"/>
~~~

Trong trường hợp thông thường, project con dùng `modules/core` làm `basedir`. Thuộc tính `dir` cũng là thư mục để phân giải đường dẫn `antfile` và `output` của task `<ant>`.

Nếu bỏ `antfile`, Ant tìm `build.xml` trong thư mục được chỉ định bởi `dir` (hoặc thư mục mặc định nếu `dir` không được đặt). Nếu `antfile` là đường dẫn tương đối, nó được tính tương đối với `dir`.

### 7.1. `dir` được chỉ định thì ưu tiên hơn `basedir` của child

Nếu đặt `dir`, giá trị này sẽ thay thế `basedir` mà build file con khai báo, trừ khi `useNativeBasedir="true"` được bật.

Ví dụ child khai báo:

~~~xml
<project name="core" default="compile" basedir="../shared">
    <target name="compile">
        <echo message="basedir=${basedir}"/>
    </target>
</project>
~~~

Nếu parent gọi:

~~~xml
<ant dir="modules/core" antfile="build.xml" target="compile"/>
~~~

thì `basedir` của child là `modules/core`, không phải `../shared` như khai báo trong child. `dir` được dùng để đặt base directory cho lần gọi này.

### 7.2. Nếu bỏ `dir`, kết quả phụ thuộc `inheritAll`

Đối với task `<ant>` nằm trong một build được gọi trực tiếp từ command line (không phải chính nó là build con của một `<ant>` hoặc `<antcall>` khác), quy tắc mặc định như sau:

| `dir` | `inheritAll` | `basedir` của project con |
|---|---|---|
| Có giá trị | `true` hoặc `false` | Giá trị `dir` |
| Bỏ qua | `true` | `basedir` của project gọi |
| Bỏ qua | `false` | `basedir` được khai báo trong `<project>` của build con; nếu không có thì là thư mục chứa build file con |

Đây là điểm dễ gây nhầm lẫn. Với mặc định `inheritAll="true"`, nếu bỏ `dir`, child có thể kế thừa base directory của parent thay vì dùng thư mục chứa build file con. Điều đó có nghĩa đường dẫn tương đối trong child có thể được tính từ thư mục cha.

Ví dụ:

~~~text
workspace/
├── build.xml
└── modules/
    └── core/
        ├── build.xml
        └── src/
~~~

Nếu parent ở `workspace` gọi:

~~~xml
<ant antfile="modules/core/build.xml" target="compile"/>
~~~

và dùng mặc định `inheritAll="true"`, child có thể nhận `workspace` làm basedir. Khi đó `src/main/java` trong child sẽ được phân giải thành `workspace/src/main/java`, không phải `workspace/modules/core/src/main/java`.

Để tránh nhầm lẫn, có thể chỉ định:

~~~xml
<ant dir="modules/core" antfile="build.xml" target="compile"/>
~~~

Hoặc dùng `useNativeBasedir="true"` nếu muốn child sử dụng base directory như khi chạy trực tiếp.

## 8. `useNativeBasedir`: dùng base directory tự nhiên của build con

Từ Ant 1.8.0, task `<ant>` hỗ trợ `useNativeBasedir`:

~~~xml
<ant antfile="modules/core/build.xml"
     target="compile"
     useNativeBasedir="true"/>
~~~

Khi đặt `useNativeBasedir="true"`, project con sử dụng `basedir` mà nó sẽ nhận được nếu được chạy trực tiếp từ command line:

- Nếu `<project>` của child có thuộc tính `basedir`, giá trị đó được dùng và đường dẫn tương đối được tính từ thư mục chứa build file child.
- Nếu child không khai báo `basedir`, thư mục chứa build file child là base directory.

Cơ chế này độc lập với `dir` và `inheritAll` trong việc xác định `basedir` của project con. Tuy nhiên, `dir` vẫn có vai trò trong việc phân giải đường dẫn `antfile` và `output` của task `<ant>`.

Ví dụ:

~~~xml
<ant antfile="modules/core/build.xml"
     target="compile"
     dir="."
     useNativeBasedir="true"/>
~~~

Ở đây `dir="."` giúp Ant tìm `modules/core/build.xml` từ thư mục hiện tại của project gọi; `useNativeBasedir="true"` khiến project con dùng base directory tự nhiên của chính build file `modules/core/build.xml`.

Dùng `useNativeBasedir` khi mỗi module được thiết kế để chạy độc lập và các đường dẫn tương đối trong build file luôn phải tính từ thư mục module đó, dù được gọi từ build tổng.

## 9. Ảnh hưởng của các lần gọi Ant lồng nhau

Quy tắc `basedir` trở nên phức tạp hơn nếu một project con lại gọi project cháu. Khi `useNativeBasedir` không bật, Ant duy trì hành vi tương thích lịch sử: `basedir` của lần gọi hiện tại có thể phụ thuộc `dir` và `inheritAll` của các lần gọi trước đó.

Một số quy tắc quan trọng:

- Nếu task `<ant>` hiện tại có `dir`, giá trị `dir` hiện tại luôn thắng.
- Nếu task hiện tại bỏ `dir` và lần gọi cha đã chỉ định `dir`, project sâu hơn sẽ tiếp tục dùng giá trị `dir` của lần gọi cha.
- Nếu lần gọi cha không có `dir` và `inheritAll="true"`, project được gọi tiếp theo có thể dùng basedir của project cha ở tầng trước.
- Nếu lần gọi cha không có `dir` và `inheritAll="false"`, kết quả còn phụ thuộc `inheritAll` của task hiện tại.

Với một cấp gọi lồng nhau, khi task hiện tại bỏ `dir` và parent invocation cũng không có `dir`, bảng sau mô tả kết quả:

| `inheritAll` của lần gọi cha | `inheritAll` của lần gọi hiện tại | `basedir` của project mới |
|---|---|---|
| `true` | `true` | `basedir` của project ở tầng cha (project đã gọi build chứa task hiện tại) |
| `true` | `false` | `basedir` của project ở tầng cha |
| `false` | `true` | `basedir` của project đang chứa task `<ant>` hiện tại |
| `false` | `false` | `basedir` khai báo trong `<project>` của build mới; nếu không có thì thư mục chứa build file mới |

Nếu có nhiều tầng lồng nhau, cần áp dụng quy tắc này đệ quy từ lần gọi ngoài cùng. Đây là một trong những lý do nên chỉ định `dir` rõ ràng hoặc dùng `useNativeBasedir="true"` để làm cho đường dẫn của từng module dễ dự đoán.

### 9.1. Property `basedir` truyền từ command line

Nếu `basedir` của build ngoài cùng được truyền trên command line, ví dụ:

~~~bash
ant -Dbasedir=D:/agent/workspace build-all
~~~

hoặc được cung cấp qua property file, giá trị đó có ưu tiên đặc biệt. Với các task `<ant>` không chỉ định `dir`, các project sâu hơn có thể tiếp tục nhận giá trị `basedir` được truyền từ ngoài, bất kể số tầng lồng nhau.

Một nested `<property name="basedir" .../>` trong task `<ant>` cũng có thể tạo ảnh hưởng tương tự tới các build sâu hơn, trừ khi task tương ứng đặt `dir` tường minh.

Không nên dùng `basedir` như một property cấu hình thông thường để truyền đường dẫn tùy tiện giữa nhiều module nếu không hiểu tác động này. Khi cần truyền một thư mục dữ liệu riêng, dùng property có tên riêng như `shared.output.dir` hoặc `module.root`, và dùng `dir`/`useNativeBasedir` để kiểm soát project base directory.

## 10. Bảng so sánh tổng hợp

| Thuộc tính | Điều khiển | Mặc định | Hành vi chính |
|---|---|---|---|
| `inheritAll` | Property | `true` | Truyền property của cha; giá trị được truyền có ưu tiên trong child |
| `inheritRefs` | Reference | `false` | Copy reference của cha; không ghi đè reference child đã tồn tại |
| Nested `<property>` | Property cụ thể | Không có | Luôn truyền, kể cả khi `inheritAll="false"`; có thể truyền tiếp qua build sâu hơn |
| Nested `<reference>` | Reference cụ thể | Không có | Chọn reference cha, có thể đổi ID; có quy tắc ưu tiên riêng |
| `dir` | Base directory và phân giải antfile/output | Phụ thuộc `inheritAll` nếu bỏ qua | Khi được đặt, thường trở thành basedir của child |
| `useNativeBasedir` | Base directory của child | `false` | Từ Ant 1.8.0, dùng basedir như khi chạy build con trực tiếp |

Hãy nhớ rằng `inheritAll` và `inheritRefs` không thay thế nhau. Một Path reference không được truyền chỉ vì property được kế thừa; một property cũng không được truyền chỉ vì `inheritRefs="true"`.

## 11. Ví dụ kết hợp: module nhận property và classpath tường minh

Một cách tổ chức rõ ràng là tắt kế thừa toàn bộ, truyền đúng property cần thiết và chỉ truyền reference mà module sử dụng:

Project cha:

~~~xml
<project name="workspace" default="build-core" basedir=".">

    <property name="release.version" value="3.1.0"/>

    <path id="shared.compile.path">
        <fileset dir="shared/lib">
            <include name="*.jar"/>
        </fileset>
    </path>

    <target name="build-core">
        <ant dir="modules/core"
             antfile="build.xml"
             target="package"
             inheritAll="false"
             inheritRefs="false">
            <property name="module.version" value="${release.version}"/>
            <reference refid="shared.compile.path"
                       torefid="external.classpath"/>
        </ant>
    </target>

</project>
~~~

Project con:

~~~xml
<project name="core" default="package" basedir=".">

    <property name="module.version" value="0.0.0-LOCAL"/>

    <target name="compile">
        <mkdir dir="build/classes"/>
        <javac srcdir="src/main/java"
               destdir="build/classes"
               includeantruntime="false">
            <classpath refid="external.classpath"/>
        </javac>
    </target>

    <target name="package" depends="compile">
        <jar destfile="dist/core-${module.version}.jar"
             basedir="build/classes"/>
    </target>

</project>
~~~

Trong ví dụ:

1. `inheritAll="false"` ngăn project con nhận mọi property thông thường từ cha.
2. Nested `<property>` truyền `module.version` với giá trị `3.1.0`.
3. Property được truyền có ưu tiên hơn default `0.0.0-LOCAL` trong child.
4. `inheritRefs="false"` giữ việc truyền reference ở chế độ chọn lọc.
5. Nested `<reference>` chuyển `shared.compile.path` thành ID `external.classpath` trong child.
6. `dir="modules/core"` đặt base directory cho child và làm đường dẫn tương đối trong module được tính từ thư mục đó.

Đây là một giao diện module tường minh: module biết nó cần property nào và reference nào. Khi chạy build file con trực tiếp, cần cung cấp cấu hình tương ứng hoặc định nghĩa default hợp lý để module vẫn có thể hoạt động độc lập.

## 12. Phân biệt `<ant>`, `<antcall>` và `<subant>`

Ba task có mục đích gần nhau nhưng phạm vi khác nhau:

| Task | Dùng để | Điểm cần nhớ |
|---|---|---|
| `<ant>` | Gọi một build file/project khác | Có `antfile`, `dir`, `inheritAll`, `inheritRefs`, `useNativeBasedir` |
| `<antcall>` | Gọi target khác trong cùng build file/project | Tạo một lượt target invocation mới; có `inheritAll` và `inheritRefs`, nhưng không phải cách điều phối dependency thông thường |
| `<subant>` | Gọi cùng một target trên nhiều subproject được tìm qua buildpath/resource collection | Phù hợp với build nhiều module; `inheritAll` mặc định là `false` trong task này |

Nếu chỉ cần target `package` chạy sau target `compile` trong cùng project, dùng `depends`. Không nên dùng `<antcall>` để thay thế dependency graph vì target có thể được thực hiện lại trong invocation riêng.

Nếu cần duyệt nhiều thư mục module và gọi cùng một build file cho từng module, `<subant>` có thể phù hợp hơn việc viết nhiều task `<ant>` lặp lại. Hãy kiểm tra default khác nhau của `inheritAll` giữa `<ant>` và `<subant>` trước khi chuyển cấu hình.

## 13. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Property trong child có giá trị của parent ngoài dự kiến | `inheritAll` mặc định là `true` | Đặt `inheritAll="false"` hoặc đổi tên property dùng chung |
| Child không nhận property cần thiết | `inheritAll="false"` và chưa truyền nested property | Thêm nested `<property>` hoặc truyền user property |
| Child không thấy Path/FileSet của parent | `inheritRefs` mặc định là `false` | Bật `inheritRefs` hoặc truyền nested `<reference>` |
| Reference của parent không thay reference child | `inheritRefs="true"` không ghi đè ID đã tồn tại | Dùng ID khác hoặc nested `<reference>` nếu cần override reference ngoài target |
| Reference được truyền nhưng task vẫn dùng giá trị khác | Child tạo reference cùng ID bên trong target | Kiểm tra vị trí khởi tạo và đổi `torefid` để tránh xung đột |
| Source trong child không tìm thấy khi gọi từ parent | Child nhận basedir của parent | Đặt `dir` hoặc `useNativeBasedir="true"` |
| `antfile` không tìm thấy | Đường dẫn được tính tương đối với `dir` hoặc base directory mặc định | Kiểm tra `dir`, `antfile` và working directory |
| Build con chạy đúng khi gọi trực tiếp nhưng sai khi gọi lồng | Quy tắc basedir phụ thuộc lịch sử invocation | Dùng `useNativeBasedir` hoặc chỉ định `dir` ở mỗi tầng |
| `inheritAll=false` nhưng một property vẫn xuất hiện | Property là user property hoặc được truyền bằng nested `<property>` | Kiểm tra nguồn tạo property và nested elements |
| Module con không độc lập | Phụ thuộc property/reference ngầm từ cha | Khai báo default hoặc giao diện tham số tường minh |

Khi debug, nên in các giá trị sau trong cả parent và child:

~~~xml
<echo message="Project=${ant.project.name}"/>
<echo message="Build file=${ant.file}"/>
<echo message="Basedir=${basedir}"/>
<echo message="Release version=${release.version}"/>
~~~

Có thể chạy Ant với `-verbose` để xem task gọi build con và target nào được thực hiện. Khi cần xác nhận property hoặc reference, tạo target chẩn đoán nhỏ trong child thay vì suy luận chỉ từ vị trí terminal.

## 14. Quy tắc thiết kế build nhiều dự án

- Dùng `inheritAll="false"` nếu muốn module có cấu hình riêng và chỉ nhận những property được truyền rõ ràng.
- Dùng nested `<property>` để truyền version, build number, môi trường hoặc đường dẫn chia sẻ cụ thể.
- Dùng `inheritRefs="true"` chỉ khi module thực sự cần phần lớn reference của parent.
- Ưu tiên nested `<reference>` khi chỉ cần chia sẻ một Path/FileSet và muốn kiểm soát ID trong child.
- Đặt `dir` rõ ràng khi parent muốn ép child dùng một module root cụ thể.
- Dùng `useNativeBasedir="true"` khi child cần hoạt động như lúc chạy trực tiếp, độc lập với base directory của parent.
- Tránh truyền property tên `basedir` như một tham số thông thường nếu không chủ động muốn ảnh hưởng đến mọi build sâu hơn.
- Giữ tên property và reference có namespace theo module để tránh trùng ID.
- Đảm bảo module có thể chạy độc lập hoặc ghi rõ các tham số mà build tổng phải cung cấp.
- Pin phiên bản Ant tối thiểu nếu dùng `useNativeBasedir` (Ant 1.8.0 trở lên).

Một build nhiều module dễ bảo trì khi mỗi project có ranh giới rõ: property nào là cấu hình chung, reference nào được chia sẻ, và thư mục nào là gốc của module. Những quyết định này nên thể hiện ngay trong task `<ant>` thay vì dựa vào hành vi kế thừa mặc định mà người đọc khó nhìn thấy.

## Kết luận

`inheritAll` truyền property (mặc định `true`), còn `inheritRefs` truyền reference (mặc định `false`). Nested `<property>` và `<reference>` cho phép chọn lọc dữ liệu gửi sang project con; nested property luôn được truyền ngay cả khi `inheritAll="false"`, còn nested reference có thể đổi ID và có quy tắc ưu tiên riêng. `dir` đặt base directory cho child và cũng là cơ sở phân giải `antfile`/`output`. Nếu bỏ `dir`, `basedir` có thể phụ thuộc `inheritAll` và lịch sử các lần gọi lồng nhau. Từ Ant 1.8.0, `useNativeBasedir="true"` giúp project con dùng base directory như khi chạy trực tiếp. Khi build nhiều module, hãy quyết định rõ property, reference và basedir nào được chia sẻ để tránh khác biệt giữa chạy module độc lập và chạy từ build tổng.

## Tài liệu tham khảo

- [Apache Ant – Ant Task](https://ant.apache.org/manual/Tasks/ant.html)
- [Apache Ant – SubAnt Task](https://ant.apache.org/manual/Tasks/subant.html)
- [Apache Ant – Writing a Simple Buildfile](https://ant.apache.org/manual/using.html)
