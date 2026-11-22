# Thiết lập encoding, debug, deprecation và compilerarg

Trong Apache Ant, task `<javac>` điều khiển quá trình biên dịch mã nguồn Java. Ngoài thư mục source, thư mục output và classpath, task này còn cho phép cấu hình cách compiler đọc văn bản, lượng thông tin debug được ghi vào bytecode, cách báo việc sử dụng API đã deprecated và các tùy chọn compiler chuyên biệt.

Bốn nhóm cấu hình cần nắm là:

- `encoding`: chọn charset để đọc các tệp `.java`.
- `debug` và `debuglevel`: yêu cầu compiler ghi thông tin phục vụ debug vào tệp `.class`.
- `deprecation`: yêu cầu compiler thông báo khi mã sử dụng API đã deprecated.
- `<compilerarg>`: truyền trực tiếp các đối số mà compiler hỗ trợ, chẳng hạn `-Xlint`, `--release`, `-parameters` hoặc tùy chọn annotation processing.

Các tùy chọn này tác động đến những phần khác nhau của build. Encoding ảnh hưởng cách đọc source; debug ảnh hưởng metadata trong bytecode; deprecation và lint ảnh hưởng thông báo chẩn đoán; compilerarg mở rộng cấu hình theo khả năng của compiler đang dùng.

## 1. Cấu hình cơ bản của task `<javac>`

Một target compile thường xác định thư mục source, nơi ghi class và classpath:

~~~xml
<property name="src.main" location="src/main/java"/>
<property name="classes.dir" location="build/classes"/>

<target name="compile">
    <mkdir dir="${classes.dir}"/>
    <javac srcdir="${src.main}"
           destdir="${classes.dir}"
           includeantruntime="false"/>
</target>
~~~

Các thuộc tính trong ví dụ:

- `srcdir`: thư mục chứa mã nguồn Java.
- `destdir`: thư mục nhận các tệp `.class`.
- `includeantruntime="false"`: không tự đưa thư viện runtime của Ant vào classpath ứng dụng.

Có thể bổ sung encoding, debug, deprecation và compilerarg ngay trong task:

~~~xml
<target name="compile">
    <mkdir dir="${classes.dir}"/>
    <javac srcdir="${src.main}"
           destdir="${classes.dir}"
           includeantruntime="false"
           encoding="UTF-8"
           debug="true"
           debuglevel="source,lines,vars"
           deprecation="true">
        <compilerarg value="-Xlint:unchecked"/>
    </javac>
</target>
~~~

Đây là cấu hình minh họa cho compiler tương thích với các tùy chọn được truyền. Nếu dùng compiler khác như Eclipse compiler, cần kiểm tra adapter và tập tùy chọn mà compiler đó hỗ trợ.

## 2. Chọn encoding cho mã nguồn Java

### 2.1. Vì sao cần khai báo encoding?

Tệp `.java` là văn bản. Khi đọc source, compiler cần biết các byte trong file được mã hóa theo charset nào để chuyển chúng thành ký tự. Nếu không chỉ định encoding, compiler thường dùng charset mặc định của môi trường chạy. Charset đó có thể khác giữa máy phát triển, agent CI hoặc hệ điều hành.

Ví dụ source có ký tự tiếng Việt:

~~~java
public class Greeting {
    public static void main(String[] args) {
        System.out.println("Xin chào, lập trình Java!");
    }
}
~~~

Nếu file được lưu bằng UTF-8 nhưng compiler đọc theo một charset khác, ký tự có dấu có thể bị giải mã sai hoặc gây lỗi biên dịch. Build local có thể chạy trong môi trường dùng cùng charset với editor, trong khi CI lại thất bại.

### 2.2. Dùng thuộc tính `encoding`

Đặt `encoding` trên task `<javac>`:

~~~xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       encoding="UTF-8"
       includeantruntime="false"/>
~~~

`encoding="UTF-8"` yêu cầu compiler đọc các source được task biên dịch bằng UTF-8. Đây là lựa chọn phổ biến cho dự án mới và giúp kết quả nhất quán giữa các hệ điều hành.

Nếu dự án cũ lưu source bằng một charset khác, phải khai báo đúng charset thực tế của các file đó. Không thể chỉ đổi thuộc tính `encoding` để chuyển đổi nội dung file; muốn đổi charset lưu trữ, cần chuyển đổi file bằng editor hoặc công cụ chuyển mã trước.

### 2.3. Encoding của source khác encoding của resource

Thuộc tính `encoding` trên `<javac>` chỉ điều khiển cách compiler đọc mã nguồn Java. Nó không tự cấu hình cách task `<copy>`, `<filter>`, `<concat>` hoặc một công cụ khác đọc và ghi tài nguyên văn bản.

Ví dụ, nếu copy file `.properties` có lọc nội dung, cần cấu hình encoding của task xử lý tài nguyên theo thuộc tính mà task đó hỗ trợ. Không nên giả định rằng `javac encoding="UTF-8"` khiến toàn bộ build sử dụng UTF-8.

Cũng cần phân biệt encoding của source với encoding đầu ra mà chương trình sử dụng lúc chạy. Một ứng dụng có thể đọc source UTF-8, nhưng cách nó ghi ra console hoặc đọc file runtime còn phụ thuộc API, cấu hình JVM và encoding của dữ liệu.

## 3. Bật thông tin debug bằng `debug`

Compiler có thể ghi thêm metadata vào bytecode để debugger liên kết mã đang chạy với source. Thuộc tính `debug` của task `<javac>` bật hoặc tắt việc tạo thông tin debug.

~~~xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       encoding="UTF-8"
       debug="true"
       includeantruntime="false"/>
~~~

Khi `debug="true"`, compiler được yêu cầu tạo thông tin debug theo khả năng của nó. Với `javac`, thông tin này thường bao gồm tên source, số dòng và thông tin biến cục bộ. Giá trị mặc định của Ant cho `debug` là tắt; nên khai báo rõ trong build nếu cần kết quả nhất quán.

Thông tin debug giúp:

- Debugger hiển thị số dòng source khi dừng tại breakpoint.
- Stack trace có thể chỉ ra số dòng trong source khi metadata tương ứng có sẵn.
- Debugger hiển thị tên và giá trị biến cục bộ khi compiler đã ghi thông tin đó.
- IDE liên kết bytecode với source dễ hơn.

Bật debug không có nghĩa chương trình chạy chậm hơn một cách đáng kể trong mọi trường hợp; đây chủ yếu là metadata bổ sung trong class file. Tuy nhiên, thông tin biến cục bộ có thể làm tăng kích thước bytecode và tiết lộ tên biến nội bộ. Với artifact phát hành, nhóm dự án nên quyết định chính sách debug dựa trên nhu cầu vận hành và bảo mật.

### 3.1. Chọn mức thông tin bằng `debuglevel`

Thuộc tính `debuglevel` chọn nhóm metadata debug mà compiler ghi. Với `javac`, các mức thường dùng là:

| Mức | Thông tin được ghi |
|---|---|
| `source` | Tên file source được dùng để biên dịch |
| `lines` | Bảng ánh xạ vị trí bytecode với số dòng source |
| `vars` | Thông tin biến cục bộ và tham số theo khả năng compiler |

Có thể kết hợp nhiều mức bằng dấu phẩy:

~~~xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       debug="true"
       debuglevel="source,lines,vars"
       includeantruntime="false"/>
~~~

Nếu chỉ cần số dòng cho stack trace, có thể chọn:

~~~xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       debug="true"
       debuglevel="lines,source"
       includeantruntime="false"/>
~~~

`debuglevel` có ý nghĩa khi debug được bật. Nếu `debug="false"`, không nên kỳ vọng chỉ định `debuglevel` sẽ tự bật metadata debug. Cú pháp và mức được hỗ trợ còn phụ thuộc compiler adapter.

### 3.2. Debug metadata không phải source code

Bật `debug` không nhúng toàn bộ nội dung `.java` vào `.class`. Nó ghi metadata phục vụ công cụ debug. Nếu muốn phân phối source kèm thư viện, cần đóng gói source JAR hoặc artifact riêng bằng task phù hợp.

Tương tự, việc có `debug="true"` không bảo đảm debugger luôn hiển thị đầy đủ tên biến. Cần compiler hỗ trợ, metadata tương ứng được tạo và debugger có source phù hợp.

## 4. Báo việc sử dụng API deprecated bằng `deprecation`

Trong Java, một class, method, constructor hoặc field có thể được đánh dấu `@Deprecated` để thông báo rằng API đó không còn được khuyến nghị sử dụng. API có thể vẫn hoạt động, nhưng có thể bị thay thế hoặc loại bỏ trong phiên bản tương lai.

Ví dụ:

~~~java
class LegacyApi {
    /** @deprecated Use {@link #newMethod()} instead. */
    @Deprecated
    public void oldMethod() {
        // Legacy implementation
    }

    public void newMethod() {
        // Current implementation
    }
}
~~~

Nếu mã nguồn gọi `oldMethod()`, compiler có thể phát ra thông báo về API deprecated. Trong Ant, thuộc tính `deprecation` của `<javac>` điều khiển việc yêu cầu compiler phát thông tin deprecation:

~~~xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       encoding="UTF-8"
       deprecation="true"
       includeantruntime="false"/>
~~~

Khi bật, compiler cung cấp thông tin về việc sử dụng hoặc khai báo API deprecated theo cách compiler hỗ trợ. Thuộc tính này không tự sửa mã nguồn, không thay thế API cũ và cũng không mặc định làm build thất bại.

### 4.1. Dùng lint để có cảnh báo chi tiết hơn

Với `javac`, có thể yêu cầu cảnh báo deprecation chi tiết qua compiler option `-Xlint:deprecation`:

~~~xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       includeantruntime="false">
    <compilerarg value="-Xlint:deprecation"/>
</javac>
~~~

`deprecation="true"` và `-Xlint:deprecation` có liên quan nhưng không phải cùng một thuộc tính Ant. Thuộc tính `deprecation` bật chế độ thông báo deprecation của task; `-Xlint:deprecation` là tùy chọn cụ thể của `javac` để yêu cầu mức cảnh báo lint chi tiết hơn.

Nếu dự án muốn cảnh báo nhiều nhóm vấn đề, có thể dùng:

~~~xml
<compilerarg value="-Xlint:unchecked"/>
<compilerarg value="-Xlint:deprecation"/>
~~~

Hoặc:

~~~xml
<compilerarg value="-Xlint:all"/>
~~~

`-Xlint:all` có thể tạo nhiều cảnh báo hơn, bao gồm những cảnh báo trước đây chưa được hiển thị. Nên bật trong một thay đổi có kiểm soát, xem lại cảnh báo mới và thống nhất chính sách xử lý trước khi áp dụng `-Werror`.

## 5. Truyền tùy chọn compiler bằng `<compilerarg>`

Không phải mọi tùy chọn của `javac` đều có thuộc tính riêng trên Ant `<javac>`. Nested element `<compilerarg>` cho phép truyền đối số trực tiếp tới compiler adapter.

Ví dụ:

~~~xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       encoding="UTF-8"
       debug="true"
       deprecation="true"
       includeantruntime="false">
    <compilerarg value="-Xlint:unchecked"/>
    <compilerarg value="-Xlint:deprecation"/>
</javac>
~~~

Mỗi `<compilerarg value="..."/>` cung cấp một đối số. Dùng nhiều phần tử riêng giúp nhìn rõ ranh giới từng đối số, nhất là với option nhận thêm một giá trị.

Ví dụ truyền `--release` và số phiên bản thành hai đối số:

~~~xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       encoding="UTF-8"
       includeantruntime="false">
    <compilerarg value="--release"/>
    <compilerarg value="17"/>
</javac>
~~~

Với compiler `javac` từ JDK 9 trở lên, `--release 17` yêu cầu compiler áp dụng mức ngôn ngữ, định dạng bytecode và tập API Java công khai tương ứng với Java 17. Đây thường là cách phù hợp hơn việc chỉ đặt `source` và `target` khi cần biên dịch trên JDK mới nhưng giữ khả năng chạy trên một phiên bản Java cũ hơn.

Không kết hợp `--release` với `source`/`target` trong cùng một lần gọi compiler. Hãy chọn một cách cấu hình nhất quán và bảo đảm compiler thực sự hỗ trợ option đó.

### 5.1. Một số compilerarg thường dùng

| Đối số | Mục đích | Lưu ý |
|---|---|---|
| `-Xlint:unchecked` | Cảnh báo thao tác generic không được kiểm tra đầy đủ | Hữu ích khi làm việc với raw type hoặc ép kiểu không an toàn |
| `-Xlint:deprecation` | Cảnh báo chi tiết khi dùng API deprecated | Có thể kết hợp với `deprecation="true"` |
| `-Xlint:all` | Bật nhiều nhóm cảnh báo lint | Có thể tạo nhiều cảnh báo cần xử lý |
| `-Werror` | Chuyển warning thành lỗi compiler | Chỉ bật khi nhóm đã kiểm soát được warning hiện có |
| `-parameters` | Ghi tên tham số method/constructor vào class file | Hữu ích cho reflection và framework đọc tên tham số; cần compiler Java hỗ trợ |
| `-proc:none` | Tắt annotation processing trong lượt compile | Chỉ dùng nếu dự án không cần annotation processor tạo mã hoặc kiểm tra |
| `--release 17` | Chọn API, cú pháp và bytecode tương thích Java 17 | Cần compiler JDK 9 trở lên |
| `-Akey=value` | Truyền option cho annotation processor | Tên option phụ thuộc processor |

Ví dụ kết hợp lint và giữ tên tham số:

~~~xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       encoding="UTF-8"
       includeantruntime="false">
    <compilerarg value="-Xlint:unchecked"/>
    <compilerarg value="-Xlint:deprecation"/>
    <compilerarg value="-parameters"/>
</javac>
~~~

Ví dụ cấu hình annotation processor:

~~~xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       includeantruntime="false">
    <compilerarg value="-Aconfig=src/main/resources/processor.properties"/>
</javac>
~~~

Compiler chuyển option `-A` cho annotation processor. Processor phải khai báo và hỗ trợ option đó; nếu không, compiler có thể báo option không được nhận diện hoặc không được sử dụng.

### 5.2. Truyền option gồm nhiều phần

Với option cần một giá trị riêng, hãy truyền mỗi phần như một đối số riêng:

~~~xml
<compilerarg value="--release"/>
<compilerarg value="17"/>
~~~

Không ghép hai phần thành một chuỗi duy nhất nếu compiler mong đợi hai đối số. Có thể dùng thuộc tính `line` để truyền một dòng đối số, nhưng các phần tử `value` riêng thường dễ đọc và tránh nhầm lẫn hơn.

Một số tùy chọn JVM bắt đầu bằng `-J`, ví dụ `-J-Xmx2g`, chỉ có ý nghĩa khi gọi executable `javac` theo cách forked. Chúng điều khiển JVM chạy compiler, không phải tùy chọn ngôn ngữ hay bytecode của source. Nếu Ant đang biên dịch in-process, không thể dùng `-J` theo cách như một tiến trình javac bên ngoài.

## 6. Kết hợp encoding, debug, deprecation và compilerarg

Một target compile có thể gom các lựa chọn phổ biến thành cấu hình dùng chung:

~~~xml
<property name="src.main" location="src/main/java"/>
<property name="classes.dir" location="build/classes"/>
<property name="java.release" value="17"/>

<target name="compile">
    <mkdir dir="${classes.dir}"/>
    <javac srcdir="${src.main}"
           destdir="${classes.dir}"
           encoding="UTF-8"
           debug="true"
           debuglevel="source,lines,vars"
           deprecation="true"
           includeantruntime="false">
        <compilerarg value="--release"/>
        <compilerarg value="${java.release}"/>
        <compilerarg value="-Xlint:unchecked"/>
        <compilerarg value="-Xlint:deprecation"/>
    </javac>
</target>
~~~

Cấu hình này có ý nghĩa:

1. Source được đọc bằng UTF-8.
2. Bytecode có metadata debug gồm source, line number và local variable theo compiler hỗ trợ.
3. Compiler báo việc sử dụng API deprecated.
4. Compiler nhận các cảnh báo lint về unchecked operation và deprecation.
5. Compiler JDK 9+ tạo đầu ra theo Java release được đặt trong property `java.release`.

Nếu dùng `-Werror`, mọi warning được compiler xem là warning và có thể bị nâng thành lỗi. Chỉ thêm option này khi dự án đã xử lý các cảnh báo hiện hữu hoặc có quy trình quản lý warning rõ ràng.

## 7. Phân biệt tùy chọn Ant với tùy chọn riêng của javac

Một số cấu hình có thuộc tính riêng trong task `<javac>`, trong khi một số khác phải truyền qua `<compilerarg>`.

| Mục tiêu | Cấu hình Ant | Tùy chọn compiler liên quan |
|---|---|---|
| Đọc source theo UTF-8 | `encoding="UTF-8"` | `-encoding UTF-8` |
| Tạo debug metadata | `debug="true"` | `-g` |
| Chọn nhóm debug metadata | `debuglevel="lines,vars,source"` | `-g:lines,vars,source` |
| Báo deprecation | `deprecation="true"` | `-deprecation` hoặc lint tương ứng tùy compiler |
| Cảnh báo unchecked | Nested `<compilerarg>` | `-Xlint:unchecked` |
| Giới hạn Java API/bytecode đích | `release` nếu phiên bản Ant hỗ trợ, hoặc `<compilerarg>` | `--release 17` |
| Giữ tên tham số | Nested `<compilerarg>` | `-parameters` |

Khi một thuộc tính Ant đã cung cấp cách cấu hình trực tiếp, nên dùng thuộc tính đó để build file thể hiện rõ ý định. Dùng compilerarg cho tùy chọn không có thuộc tính riêng hoặc khi cần tính năng đặc thù của compiler.

Không nên truyền lặp lại cùng một option qua cả thuộc tính Ant và `<compilerarg>` nếu chưa hiểu cách adapter tạo command line. Ví dụ, không cần vừa dùng `encoding="UTF-8"` vừa tự truyền `-encoding UTF-8`; hai cấu hình trùng nhau làm build khó đọc và có thể tạo xung đột nếu giá trị khác nhau.

## 8. Compiler chạy in-process và fork ảnh hưởng thế nào?

Task `<javac>` có thể biên dịch trong tiến trình Ant hoặc gọi compiler ở một tiến trình riêng.

~~~xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       fork="false"
       encoding="UTF-8"
       includeantruntime="false"/>
~~~

Với `fork="false"` (mặc định), Ant thường dùng compiler trong JVM đang chạy Ant thông qua compiler adapter. Các compilerarg được adapter hỗ trợ sẽ được truyền tới compiler đó.

Nếu cần gọi một executable `javac` riêng:

~~~xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       fork="true"
       executable="/opt/jdk-17/bin/javac"
       encoding="UTF-8"
       includeantruntime="false">
    <compilerarg value="--release"/>
    <compilerarg value="17"/>
    <compilerarg value="-Xlint:deprecation"/>
</javac>
~~~

Trên Windows, `executable` thường trỏ tới `bin/javac.exe`. Khi fork, Ant khởi chạy compiler bên ngoài; các tùy chọn phải phù hợp với executable và phiên bản JDK đó. Cấu hình `fork` không làm thay đổi JVM đang chạy Ant.

Tùy chọn compilerarg không phải lúc nào cũng dùng được với mọi compiler. Ví dụ `-Xlint` và `--release` là tùy chọn của `javac`; nếu chuyển sang compiler adapter khác, hãy kiểm tra cú pháp tương đương. Các tùy chọn `-J...` yêu cầu gọi executable forked và không được hiểu như compiler option thông thường khi biên dịch in-process.

## 9. Tương thích phiên bản Java và compiler

Các option compiler có vòng đời riêng. JDK cũ có thể không hiểu option được thêm ở JDK mới; ngược lại, compiler mới có thể chấp nhận option nhưng tạo đầu ra không tương thích với runtime mục tiêu nếu cấu hình sai.

Một số nguyên tắc:

- `encoding`, `debug`, `debuglevel` và `deprecation` là cấu hình phổ biến của task Ant `<javac>`.
- `-Xlint` là nhóm tùy chọn riêng của `javac`; nhóm lint và cảnh báo có thể thay đổi giữa các phiên bản JDK.
- `--release` có từ JDK 9. Compiler JDK 8 không hỗ trợ option này.
- `-parameters` có từ Java 8 và cần compiler hỗ trợ.
- `-Werror` có thể làm build bắt đầu thất bại khi JDK mới bổ sung warning hoặc thay đổi mức cảnh báo.
- Compiler khác `javac` có thể có cú pháp option và mức hỗ trợ khác.

Nếu dự án cần chạy trên Java 17 nhưng build agent dùng JDK 21, có thể dùng compiler JDK 21 cùng `--release 17`. Điều này giới hạn API Java công khai và bytecode theo release 17, nhưng không tự động bảo đảm các thư viện bên thứ ba cũng tương thích Java 17. Dependency và runtime vẫn cần được kiểm tra.

## 10. Ví dụ target compile riêng cho main và test

Có thể dùng chung encoding, debug và compilerarg cho mã chính và mã test thông qua property hoặc macro/taskdef phù hợp. Một ví dụ trực tiếp:

~~~xml
<property name="main.src" location="src/main/java"/>
<property name="test.src" location="src/test/java"/>
<property name="main.classes" location="build/classes"/>
<property name="test.classes" location="build/test-classes"/>

<path id="compile.classpath">
    <fileset dir="lib">
        <include name="*.jar"/>
    </fileset>
</path>

<target name="compile">
    <mkdir dir="${main.classes}"/>
    <javac srcdir="${main.src}"
           destdir="${main.classes}"
           encoding="UTF-8"
           debug="true"
           debuglevel="source,lines,vars"
           deprecation="true"
           includeantruntime="false">
        <classpath refid="compile.classpath"/>
        <compilerarg value="-Xlint:unchecked"/>
    </javac>
</target>

<target name="test-compile" depends="compile">
    <mkdir dir="${test.classes}"/>
    <javac srcdir="${test.src}"
           destdir="${test.classes}"
           encoding="UTF-8"
           debug="true"
           debuglevel="source,lines,vars"
           deprecation="true"
           includeantruntime="false">
        <classpath>
            <pathelement location="${main.classes}"/>
            <path refid="compile.classpath"/>
        </classpath>
        <compilerarg value="-Xlint:unchecked"/>
    </javac>
</target>
~~~

Mã test nhìn thấy class chính thông qua classpath bổ sung `${main.classes}`. Cả hai lượt compile dùng cùng encoding và mức debug để kết quả nhất quán. Dự án có thể bổ sung thư viện test riêng vào classpath của target `test-compile`.

## 11. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Ký tự tiếng Việt bị lỗi hoặc báo ký tự không hợp lệ | Encoding của source khác encoding compiler đang dùng | Kiểm tra charset thực tế của file và đặt `encoding` đúng |
| Local compile được nhưng CI lỗi ký tự | Dựa vào charset mặc định khác nhau giữa môi trường | Khai báo encoding tường minh, thường là UTF-8 |
| Debugger không hiện số dòng | Debug metadata không được tạo hoặc thiếu `lines` | Bật `debug="true"` và kiểm tra `debuglevel` |
| Debugger không hiển thị biến local | Metadata `vars` không có hoặc compiler không hỗ trợ | Bật `debuglevel` có `vars`, kiểm tra compiler và class file |
| Có API deprecated nhưng không thấy cảnh báo chi tiết | Chưa bật deprecation/lint phù hợp | Bật `deprecation="true"` và/hoặc `-Xlint:deprecation` |
| Build thất bại sau khi thêm `-Werror` | Warning hiện có bị nâng thành lỗi | Xử lý warning trước hoặc bỏ `-Werror` trong giai đoạn chuyển tiếp |
| `invalid flag: --release` | Compiler đang dùng quá cũ hoặc không phải javac tương thích | Kiểm tra JDK/compiler thực tế; `--release` yêu cầu JDK 9+ |
| `compilerarg` không được nhận diện | Option không thuộc compiler hoặc adapter hiện tại | Đối chiếu tài liệu compiler, kiểm tra adapter và fork mode |
| `-J-Xmx...` không có tác dụng | Compiler đang chạy in-process | Dùng `fork="true"` và executable javac nếu cần tùy chọn JVM compiler |
| Tên tham số không có khi reflection | Chưa tạo metadata parameter | Thêm `-parameters` và biên dịch lại |

Khi điều tra, hãy xác định compiler thực tế trước. Với `fork="false"`, compiler thường thuộc JDK chạy Ant. Với `fork="true"`, kiểm tra `executable`. Sau đó xem log chi tiết để biết option đã được truyền hay chưa.

Có thể chạy:

~~~bash
ant -verbose compile
ant -debug compile
javac -version
~~~

Nếu Ant dùng executable riêng, chạy chính đường dẫn `javac` đó với `-version`; lệnh `javac -version` từ PATH có thể trỏ tới JDK khác.

## 12. Quy ước cấu hình nên dùng trong dự án

Một build dễ bảo trì nên thống nhất các lựa chọn sau:

- Lưu source Java bằng một charset thống nhất và khai báo `encoding` rõ ràng.
- Chọn `debug`/`debuglevel` theo nhu cầu phát triển, kiểm thử và vận hành.
- Bật deprecation/lint để phát hiện API cũ trước khi nâng cấp JDK hoặc thư viện.
- Chỉ dùng `-Werror` khi warning baseline đã được kiểm soát.
- Dùng `<compilerarg>` cho tùy chọn thực sự cần thiết và được compiler hỗ trợ.
- Ghi rõ phiên bản Java đích bằng `--release` khi compiler hỗ trợ, tránh chỉ dựa vào JDK đang chạy Ant.
- Cố định JDK/compiler và phiên bản Ant trong CI để tránh khác biệt giữa máy.
- Tránh truyền trùng một option qua thuộc tính Ant và compilerarg.
- Ghi log phiên bản Java/compiler khi cần chẩn đoán build.

Có thể tách cấu hình theo mục tiêu:

| Mục tiêu | Encoding | Debug | Deprecation/lint | Compilerarg khác |
|---|---|---|---|---|
| Compile khi phát triển | UTF-8 | Bật đầy đủ | Bật cảnh báo | `-Xlint:unchecked` |
| CI kiểm tra chất lượng | UTF-8 | Theo chính sách dự án | Bật lint | Có thể bật `-Werror` sau khi warning sạch |
| Artifact release | UTF-8 | Theo chính sách phát hành | Bật kiểm tra trước release | `--release` để cố định Java target, nếu hỗ trợ |

Các cấu hình trên là gợi ý tổ chức. Một số nhóm vẫn giữ debug metadata trong artifact release để hỗ trợ điều tra production; nhóm khác tắt hoặc giảm metadata. Hãy thống nhất theo nhu cầu vận hành và chính sách bảo mật của sản phẩm.

## Kết luận

Trong Ant `<javac>`, `encoding` quyết định cách đọc source, `debug` và `debuglevel` quyết định metadata hỗ trợ debugger, còn `deprecation` bật thông báo về API đã deprecated. Nested `<compilerarg>` mở rộng cấu hình bằng các tùy chọn của compiler như `-Xlint`, `-Werror`, `-parameters` hoặc `--release`. Hãy chọn option theo compiler thực tế, cố định encoding và Java release của dự án, rồi xác minh cấu hình trên cùng môi trường JDK/Ant mà CI sử dụng.