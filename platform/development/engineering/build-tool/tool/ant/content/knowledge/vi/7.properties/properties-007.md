# Property có sẵn: basedir, ant.file, ant.version và ant.java.version

Apache Ant tự thiết lập một số property để build file có thể biết project đang nằm ở đâu, build file nào đang được sử dụng, phiên bản Ant nào đang chạy và JVM của Ant thuộc phiên bản Java nào. Bốn property thường gặp là `basedir`, `ant.file`, `ant.version` và `ant.java.version`.

Các property này có thể được tham chiếu bằng cú pháp `${property.name}` trong `build.xml`, giống property do dự án khai báo. Tuy nhiên, chúng mô tả môi trường và project context do Ant xác định; không nên tự gán lại tùy tiện hoặc dùng chúng thay cho cấu hình phiên bản Java đích của ứng dụng.

## 1. Tổng quan bốn property có sẵn

| Property | Giá trị mô tả | Câu hỏi được trả lời |
|---|---|---|
| `basedir` | Thư mục cơ sở của Ant project | Các đường dẫn tương đối trong project được tính từ đâu? |
| `ant.file` | Vị trí build file mà project đang sử dụng | Ant đang đọc build file nào? |
| `ant.version` | Phiên bản Apache Ant đang chạy | Công cụ build hiện tại là phiên bản nào? |
| `ant.java.version` | Phiên bản Java mà Ant nhận diện cho JVM chạy Ant | Ant đang chạy trên thế hệ Java nào? |

Ví dụ, một project có thể in các giá trị này:

~~~xml
<project name="sample-app" default="show-environment">

    <target name="show-environment">
        <echo message="Project base directory: ${basedir}"/>
        <echo message="Build file: ${ant.file}"/>
        <echo message="Ant version: ${ant.version}"/>
        <echo message="Ant Java version: ${ant.java.version}"/>
    </target>

</project>
~~~

Chạy:

~~~bash
ant show-environment
~~~

Ant thay thế các biểu thức `${...}` bằng giá trị property trước khi thực hiện task. Giá trị thực tế phụ thuộc vào nơi đặt build file, cách gọi Ant và phiên bản công cụ trên máy.

## 2. `basedir`: thư mục cơ sở của project

`basedir` là thư mục gốc mà Ant dùng để phân giải các đường dẫn tương đối của project. Đây là property quan trọng nhất khi build file tham chiếu đến source, resource, thư viện hoặc thư mục đầu ra.

Có thể chỉ định thư mục cơ sở bằng thuộc tính `basedir` trên thẻ `<project>`:

~~~xml
<project name="sample-app"
         default="show-paths"
         basedir=".">

    <target name="show-paths">
        <echo message="Project base: ${basedir}"/>
        <echo message="Source: ${basedir}/src/main/java"/>
        <echo message="Build: ${basedir}/build"/>
    </target>

</project>
~~~

Với `basedir="."`, thư mục hiện tại của project build file là cơ sở. Nếu không khai báo thuộc tính `basedir` trên `<project>`, Ant mặc định dùng thư mục chứa build file làm thư mục cơ sở.

Nếu `basedir` là đường dẫn tương đối, Ant phân giải nó tương đối với thư mục chứa build file. Ví dụ cấu trúc:

~~~text
workspace/
├── project/
│   ├── build.xml
│   ├── src/
│   └── build/
└── shared/
~~~

Build file có thể chọn `workspace` làm base directory bằng cách khai báo:

~~~xml
<project name="sample-app" default="show-paths" basedir="..">
    <target name="show-paths">
        <echo message="Base=${basedir}"/>
        <echo message="Source=${basedir}/project/src"/>
        <echo message="Shared=${basedir}/shared"/>
    </target>
</project>
~~~

Trong trường hợp này, `basedir=".."` được tính từ thư mục chứa `project/build.xml`, nên base directory là `workspace`.

### 2.1. `basedir` ảnh hưởng đến đường dẫn tương đối

Các thuộc tính và task dùng đường dẫn tương đối thường được phân giải theo project base directory. Ví dụ:

~~~xml
<property name="src.dir" location="src/main/java"/>
<property name="classes.dir" location="build/classes"/>

<target name="show-paths">
    <echo message="src.dir=${src.dir}"/>
    <echo message="classes.dir=${classes.dir}"/>
</target>
~~~

Nếu base directory là `/workspace/project`, các đường dẫn trên được phân giải thành những vị trí nằm dưới `/workspace/project`, chẳng hạn `/workspace/project/src/main/java` và `/workspace/project/build/classes`.

Thuộc tính `location` của `<property>` phù hợp khi muốn biểu diễn một giá trị như đường dẫn đã được Ant phân giải. Khi dùng `value`, Ant lưu chuỗi giá trị theo cách khai báo; nếu giá trị đó là đường dẫn, việc chuẩn hóa và phân giải có thể không diễn ra như mong muốn. Vì vậy, hãy ưu tiên `location` cho property đại diện cho file hoặc directory.

### 2.2. Ghi đè base directory khi gọi Ant

Project có thể cho phép người chạy cung cấp `basedir` từ command line:

~~~bash
ant -Dbasedir=/workspace/checkout show-paths
~~~

Điều này hữu ích khi cùng một build file được chạy trong nhiều checkout hoặc workspace. Tuy nhiên, việc thay đổi base directory có thể làm mọi đường dẫn tương đối trong build trỏ sang vị trí khác. Chỉ ghi đè khi build file được thiết kế để hỗ trợ cách chạy đó; nếu không, có thể dẫn đến việc Ant đọc nhầm source, ghi output vào sai thư mục hoặc không tìm thấy tài nguyên.

Không nên đồng nhất `basedir` với thư mục shell đang đứng. Hai thư mục này có thể khác nhau khi gọi Ant bằng `-f` từ một vị trí khác hoặc khi build file khai báo base directory riêng.

## 3. `ant.file`: vị trí của build file

`ant.file` cho biết vị trí của build file được Ant sử dụng cho project hiện tại. Property này hữu ích khi build cần tìm tài nguyên nằm cạnh `build.xml`, in đường dẫn build file trong log hoặc xác định cấu hình theo vị trí của project.

Ví dụ:

~~~xml
<project name="sample-app" default="show-build-file">

    <target name="show-build-file">
        <echo message="Build file: ${ant.file}"/>
    </target>

</project>
~~~

Nếu build file nằm ở `/workspace/project/build.xml`, giá trị `ant.file` thường là đường dẫn đã được phân giải tới file đó.

### 3.1. `ant.file` khác `basedir`

Hai property có liên quan nhưng không giống nhau:

| Property | Ví dụ | Đại diện cho |
|---|---|---|
| `ant.file` | `/workspace/project/build.xml` | Một tệp build |
| `basedir` | `/workspace/project` | Thư mục cơ sở của project |

Một build file có thể nằm trong thư mục `build/` nhưng chọn thư mục cha làm `basedir`. Khi đó, `ant.file` trỏ tới tệp build còn `basedir` trỏ tới thư mục khác.

Ví dụ:

~~~text
workspace/
└── project/
    ├── build/
    │   └── build.xml
    ├── src/
    └── dist/
~~~

Build file:

~~~xml
<project name="sample-app" default="show-paths" basedir="..">
    <target name="show-paths">
        <echo message="Build file=${ant.file}"/>
        <echo message="Base directory=${basedir}"/>
    </target>
</project>
~~~

Khi đó, `ant.file` xác định `project/build/build.xml`, còn `basedir` xác định thư mục `project`.

### 3.2. Gọi build file bằng `-f`

Người dùng không cần đứng trong thư mục chứa build file để chạy Ant. Có thể chỉ định file trực tiếp:

~~~bash
cd /tmp
ant -f /workspace/project/build.xml show-build-file
~~~

Ant đọc build file tại đường dẫn được truyền bằng `-f`. Nếu project không khai báo `basedir`, thư mục chứa build file là cơ sở mặc định; thư mục shell `/tmp` không tự động trở thành project base directory chỉ vì lệnh được chạy tại đó.

`ant.file` giúp ghi nhận file nào đang được sử dụng, còn `basedir` quyết định cách phân giải đường dẫn tương đối. Khi debug lỗi “không tìm thấy file”, hãy in cả hai thay vì chỉ kiểm tra thư mục hiện tại của terminal.

### 3.3. Build nhiều project hoặc build lồng nhau

Một quy trình có thể gọi nhiều build file thông qua task `<ant>` hoặc `<subant>`. Mỗi project có project context và build file riêng. Ant cung cấp các property có định danh project, chẳng hạn `ant.file.<project-name>`, trong ngữ cảnh nhiều project, để phân biệt vị trí build file theo tên project.

Khi làm việc với build lồng nhau, không nên mặc định rằng một giá trị `ant.file` duy nhất luôn đại diện cho mọi build file trong toàn bộ quy trình. Hãy kiểm tra tên project, property có định danh project và log của từng invocation. Cũng cần phân biệt property được truyền từ project cha với property được Ant thiết lập trong project con.

## 4. `ant.version`: phiên bản Apache Ant

`ant.version` chứa thông tin phiên bản của Apache Ant đang chạy. Nó cho biết công cụ build được cài đặt là bản nào, giúp ghi log môi trường, đối chiếu yêu cầu tương thích của task hoặc plugin, và điều tra khác biệt giữa máy phát triển với CI.

Ví dụ:

~~~xml
<target name="show-tool-versions">
    <echo message="Ant=${ant.version}"/>
</target>
~~~

Giá trị cụ thể phụ thuộc bản Ant được cài trên máy. Có thể xem nhanh bằng:

~~~bash
ant -version
~~~

`ant.version` mô tả phiên bản Ant, không phải phiên bản Java, phiên bản build file hay phiên bản ứng dụng. Nếu máy local dùng một bản Ant mới hơn CI, một task hoặc thuộc tính chỉ có trong bản mới có thể chạy local nhưng thất bại trên agent CI cũ.

Khi dự án phụ thuộc vào một task được bổ sung ở một phiên bản Ant nhất định, cần quy định phiên bản Ant tối thiểu trong hướng dẫn phát triển và cấu hình CI. Không nên chỉ kiểm tra `ant.version` bằng so sánh chuỗi tùy tiện: so sánh từ điển có thể cho kết quả sai giữa các chuỗi số phiên bản. Nếu cần ràng buộc phiên bản, dùng cơ chế kiểm tra phiên bản phù hợp của Ant hoặc script kiểm tra version theo từng thành phần số.

## 5. `ant.java.version`: phiên bản Java chạy Ant

`ant.java.version` là property do Ant thiết lập để phản ánh phiên bản Java runtime mà Ant nhận diện cho JVM đang chạy chính nó. Nó hữu ích khi muốn ghi nhận hoặc kiểm tra môi trường Java thực thi Ant.

Ví dụ:

~~~xml
<target name="show-tool-versions">
    <echo message="Ant=${ant.version}"/>
    <echo message="Ant Java=${ant.java.version}"/>
    <echo message="Java runtime=${java.version}"/>
    <echo message="Java home=${java.home}"/>
</target>
~~~

Trong ví dụ, `ant.java.version` là phiên bản Java theo cách Ant chuẩn hóa/nhận diện. `java.version` là system property của JVM và thường cung cấp chuỗi phiên bản chi tiết hơn, ví dụ có thể bao gồm số bản cập nhật. `java.home` cho biết thư mục runtime được JVM sử dụng.

Cần hiểu rõ property này nói về JVM chạy Ant. Nó không trực tiếp cho biết:

- JDK nào được gọi nếu task `<javac fork="true">` dùng `executable` riêng.
- Phiên bản bytecode mà dự án tạo ra.
- Java runtime mà ứng dụng sẽ dùng khi triển khai.
- Phiên bản Java của mọi tiến trình con được Ant khởi chạy.

Ví dụ, Ant có thể chạy trên Java 21 (`ant.java.version` phản ánh Java 21), nhưng target compile fork `/opt/jdk-17/bin/javac`. Khi đó compiler là JDK 17, còn `ant.java.version` vẫn mô tả JVM của Ant. Nếu target test cũng fork một JVM khác, runtime test cần được kiểm tra riêng.

## 6. Phân biệt property của Ant với system property và environment variable

Ngoài bốn property trên, Ant còn có thể truy cập system property của JVM và biến môi trường khi nạp chúng. Không nên nhầm các nhóm này.

| Nhóm | Ví dụ | Nguồn giá trị |
|---|---|---|
| Property Ant tự cung cấp | `basedir`, `ant.file`, `ant.version`, `ant.java.version` | Ant và project context |
| System property của JVM | `java.version`, `java.home`, `os.name`, `user.dir` | JVM chạy Ant |
| Environment variable | `JAVA_HOME`, `PATH`, `ANT_HOME` | Môi trường tiến trình của hệ điều hành |
| Property dự án | `build.dir`, `release.version`, `src.dir` | `build.xml`, property file hoặc command line |

Có thể nạp biến môi trường thành property bằng task:

~~~xml
<property environment="env"/>
~~~

Sau đó truy cập như `${env.JAVA_HOME}` hoặc `${env.PATH}`. Nếu không nạp environment vào prefix `env`, không nên mặc định rằng mọi biến môi trường đều có thể được tham chiếu dưới đúng tên biến trong build file.

System properties của JVM được Ant cung cấp như property, ví dụ `${java.version}`. Tuy vậy, `java.version` và `ant.java.version` có mục đích khác nhau: một bên là system property nguyên bản, bên kia là phiên bản Java mà Ant nhận diện.

## 7. Property có sẵn được dùng ở thời điểm nào?

Ant thiết lập project context và các property môi trường trong quá trình khởi tạo project, trước khi thực hiện các top-level tasks và target. Vì vậy, có thể tham chiếu các property này ngay trong task `<echo>` ở cấp project hoặc bên trong target.

Ví dụ:

~~~xml
<project name="sample-app" default="compile">

    <echo message="Loading ${ant.file}"/>
    <echo message="Base directory: ${basedir}"/>
    <echo message="Ant ${ant.version}; Java ${ant.java.version}"/>

    <target name="compile">
        <echo message="Compiling from ${basedir}/src/main/java"/>
    </target>

</project>
~~~

Task cấp project trong ví dụ chạy trước target. Những giá trị này đã sẵn sàng để mở rộng khi Ant thực hiện task. Cách dùng này phù hợp để log thông tin môi trường ngay đầu build, giúp CI lưu dấu vết về công cụ và đường dẫn đang sử dụng.

## 8. Quy tắc property của Ant và việc ghi đè

Property của Ant có tính chất immutable theo cơ chế thông thường: sau khi một property đã được đặt, task `<property>` tiếp theo không ghi đè giá trị đó. Điều này giúp cấu hình có tính dự đoán, nhưng cũng khiến thứ tự nạp property quan trọng.

Ví dụ:

~~~xml
<property file="build.properties"/>
<property name="build.dir" location="build"/>
~~~

Property file được nạp trước; `build.dir` trong file có thể cung cấp giá trị. Giá trị khai báo sau chỉ đóng vai trò mặc định nếu property chưa tồn tại.

Các property hệ thống do Ant/JVM cung cấp cũng không nên bị thay thế bằng một khai báo trùng tên. Đặc biệt, tránh khai báo property dự án có tên `ant.version`, `ant.file` hoặc `ant.java.version` để biểu diễn một ý nghĩa khác. Điều đó làm log và điều kiện build trở nên khó hiểu.

`basedir` có cơ chế đặc biệt gắn với thuộc tính của `<project>` và có thể được truyền từ command line trong cấu hình Ant. Nếu muốn thay đổi base directory, hãy dùng cơ chế được hỗ trợ một cách tường minh và kiểm tra các đường dẫn được phân giải; không cố gắng ghi đè nó bằng một `<property>` thông thường ở giữa build.

## 9. Ví dụ ghi nhận môi trường build

Một target `environment-info` có thể tổng hợp các property quan trọng:

~~~xml
<project name="sample-app" default="environment-info">

    <property environment="env"/>

    <target name="environment-info">
        <echo message="========== BUILD ENVIRONMENT =========="/>
        <echo message="Project       : ${ant.project.name}"/>
        <echo message="Build file    : ${ant.file}"/>
        <echo message="Base directory: ${basedir}"/>
        <echo message="Ant version   : ${ant.version}"/>
        <echo message="Ant Java      : ${ant.java.version}"/>
        <echo message="Java version  : ${java.version}"/>
        <echo message="Java home     : ${java.home}"/>
        <echo message="JAVA_HOME     : ${env.JAVA_HOME}"/>
        <echo message="ANT_HOME      : ${env.ANT_HOME}"/>
        <echo message="======================================"/>
    </target>

</project>
~~~

`ant.project.name` là một property có sẵn khác của Ant, được đưa vào ví dụ để log nhận diện project. Nếu môi trường không có `JAVA_HOME` hoặc `ANT_HOME`, giá trị tương ứng có thể rỗng; log cần được diễn giải theo cấu hình thực tế.

Có thể gọi target này trong CI trước compile để log môi trường:

~~~bash
ant environment-info
ant clean compile
~~~

Khi so sánh log giữa local và CI, hãy chú ý cả vị trí build file, base directory, phiên bản Ant và Java runtime. Hai agent có thể cùng dùng Ant version nhưng khác JDK, hoặc cùng dùng JDK nhưng build file được gọi từ workspace khác.

## 10. Các lỗi thường gặp khi dùng property có sẵn

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Đường dẫn source bị lệch | Hiểu nhầm `basedir` là thư mục terminal hiện tại | In `${basedir}` và `${ant.file}`, kiểm tra `basedir` trên `<project>` |
| Không tìm thấy build file phụ | Dựa vào `basedir` để tìm chính build file | Dùng `${ant.file}` để xác định file build, sau đó tính đường dẫn liên quan |
| Local chạy nhưng CI báo thiếu task | Ant version khác nhau | In `${ant.version}` và thống nhất phiên bản Ant |
| Điều kiện Java cho kết quả ngoài dự kiến | Dùng `ant.java.version` như chuỗi phiên bản đầy đủ hoặc nhầm với compiler JDK | In thêm `${java.version}` và xác định compiler riêng nếu có fork |
| Compiler fork dùng JDK khác với Ant | `ant.java.version` chỉ mô tả JVM của Ant | Kiểm tra thuộc tính `executable` và chạy `javac -version` ở đúng đường dẫn |
| Property không đổi dù khai báo lại | Property đã được thiết lập trước đó | Kiểm tra thứ tự nạp file, command line và quy tắc first value wins |
| Build con tham chiếu nhầm build file | Giả định `ant.file` luôn là file của project mong muốn | Kiểm tra project context và property `ant.file.<project-name>` khi có nhiều project |

## 11. Cách kiểm tra nhanh khi debug

Khi gặp lỗi liên quan đến đường dẫn hoặc phiên bản công cụ, có thể thực hiện theo thứ tự:

1. In `${basedir}` để xác nhận base directory.
2. In `${ant.file}` để xác nhận build file đang chạy.
3. In `${ant.version}` để xác nhận phiên bản Ant.
4. In `${ant.java.version}`, `${java.version}` và `${java.home}` để nhận diện JVM chạy Ant.
5. Nếu có compiler fork, in property chứa đường dẫn `executable` và kiểm tra `javac -version` bằng chính executable đó.
6. Nếu cần biết Ant nhận các property nào, chạy `ant -diagnostics` và xem log `-verbose` khi target thực thi.

Lệnh thường dùng:

~~~bash
ant -diagnostics
ant -verbose environment-info
~~~

Các giá trị được in ra nên được xem là bằng chứng về project/runtime hiện tại. Không suy luận phiên bản compiler từ `ant.java.version` nếu build có fork compiler, và không suy luận base directory từ vị trí terminal.

## Kết luận

`basedir` xác định thư mục cơ sở để Ant phân giải đường dẫn tương đối; `ant.file` xác định build file đang được sử dụng; `ant.version` nhận diện phiên bản Apache Ant; `ant.java.version` phản ánh phiên bản Java của JVM chạy Ant. Bốn property này giúp build file tự mô tả project và môi trường thực thi. Khi debug, hãy in chúng cùng `java.version` và `java.home`; nếu compiler được fork riêng, kiểm tra thêm executable của `javac` vì property runtime của Ant không đại diện cho mọi tiến trình Java trong build.