# Phân biệt thư viện ứng dụng với thư viện cần cho task tùy chọn

Khi build một dự án Java bằng Apache Ant, bạn có thể phải khai báo nhiều JAR ở những vị trí khác nhau. Một số JAR chứa các lớp mà ứng dụng của bạn sử dụng; một số JAR lại chứa chính task mở rộng mà Ant cần nạp để thực hiện build. Hai nhóm thư viện này có thể cùng xuất hiện trong một dự án, nhưng phục vụ hai môi trường thực thi khác nhau.

**Thư viện ứng dụng** là dependency của mã nguồn hoặc chương trình được build. Ant đưa chúng vào classpath của task như `javac` hoặc `java` để biên dịch và chạy ứng dụng.

**Thư viện cần cho task tùy chọn** là dependency của phần mở rộng build. Ant cần nạp chúng vào classpath của chính Ant hoặc classloader được tạo khi đăng ký task để có thể nhận diện và thực thi task đó.

Nếu đặt nhầm thư viện vào classpath, một lỗi thường gặp là Ant vẫn báo không tìm thấy task dù JAR đã có trong thư mục `lib` của ứng dụng; hoặc task chạy được nhưng chương trình cuối cùng lại thiếu dependency khi khởi chạy. Phân biệt hai nhóm này giúp build file rõ ràng và môi trường CI có thể tái tạo.

## 1. Hai nhóm thư viện phục vụ hai mục đích khác nhau

Giả sử dự án có cấu trúc:

```text
hello-ant/
├── build.xml
├── src/
│   └── com/example/Main.java
├── lib/
│   ├── domain-api.jar
│   └── json-library.jar
├── task-libs/
│   ├── report-ant-task.jar
│   └── report-engine.jar
└── build/
```

Trong ví dụ:

- `domain-api.jar` và `json-library.jar` là thư viện mà mã nguồn ứng dụng sử dụng.
- `report-ant-task.jar` chứa lớp triển khai một task mở rộng cho Ant.
- `report-engine.jar` là dependency mà chính task báo cáo cần khi thực thi.

Hai nhóm có thể được mô tả như sau:

| Tiêu chí | Thư viện ứng dụng | Thư viện của task tùy chọn |
|---|---|---|
| Ai cần nạp? | Compiler hoặc JVM chạy ứng dụng | Ant hoặc classloader của task |
| Mục đích | Cung cấp API/lớp cho mã nguồn ứng dụng | Cung cấp implementation và dependency cho task build |
| Vị trí cấu hình thường gặp | Nested `<classpath>` của `javac`, `java`, test task | `ANT_HOME/lib`, tùy chọn `-lib`, hoặc classpath của `taskdef` |
| Lỗi khi thiếu | Lỗi biên dịch, `ClassNotFoundException`, `NoClassDefFoundError` trong ứng dụng | Không nhận diện task, không nạp được task class hoặc thiếu dependency khi task chạy |
| Có tự động thay thế nhóm kia không? | Không | Không |

Tên thư mục `lib` hay `task-libs` chỉ là quy ước để người đọc dễ phân biệt. Điều quyết định là classpath nào thực sự được cấu hình cho từng thành phần.

## 2. Classpath của Ant và classpath của ứng dụng

Để hiểu rõ sự khác nhau, cần phân biệt ít nhất hai môi trường:

**Classpath của Ant** là nơi Ant tìm các lớp phục vụ chính quá trình build, bao gồm task tùy chọn và các dependency của chúng.

**Classpath của ứng dụng** là nơi compiler hoặc JVM tìm các lớp của ứng dụng và thư viện mà ứng dụng sử dụng.

Có thể hình dung:

```text
Tiến trình Ant
│
├── Ant classloader / task classloader
│   ├── report-ant-task.jar
│   └── report-engine.jar
│
└── Task đang được thực thi
    │
    ├── javac classpath
    │   ├── domain-api.jar
    │   └── json-library.jar
    │
    └── java runtime classpath
        ├── build/classes
        ├── domain-api.jar
        └── json-library.jar
```

Sơ đồ này thể hiện hai mục đích nạp lớp. Classpath của task cung cấp mã thực thi cho Ant; classpath của ứng dụng cung cấp dependency cho mã Java đang được biên dịch hoặc chạy.

Một JAR có thể xuất hiện trong cả hai môi trường nếu nó thực sự được cả task và ứng dụng sử dụng. Tuy nhiên, việc đặt nó vào một classpath không có nghĩa nó tự động xuất hiện trong classpath còn lại.

Ví dụ:

- Đưa `json-library.jar` vào nested `<classpath>` của `javac` giúp compiler tìm được các lớp JSON mà mã nguồn tham chiếu.
- Đưa `report-ant-task.jar` vào classpath của `taskdef` giúp Ant nạp lớp task báo cáo.
- Đưa `report-ant-task.jar` vào classpath ứng dụng không tự đăng ký tên task XML với Ant.
- Đưa `json-library.jar` vào classpath của Ant không tự làm cho JVM chạy ứng dụng tìm thấy thư viện đó.

## 3. Thư viện ứng dụng được khai báo ở đâu?

Dependency của ứng dụng thường được đưa vào path datatype rồi tham chiếu từ các task cần nó.

Ví dụ:

```xml
<project name="application-build" default="compile" basedir=".">

    <property name="src.dir" location="src"/>
    <property name="classes.dir" location="build/classes"/>

    <path id="application.classpath">
        <pathelement location="lib/domain-api.jar"/>
        <pathelement location="lib/json-library.jar"/>
    </path>

    <target name="compile">
        <mkdir dir="${classes.dir}"/>

        <javac
            srcdir="${src.dir}"
            destdir="${classes.dir}"
            includeantruntime="false"
            encoding="UTF-8">
            <classpath refid="application.classpath"/>
        </javac>
    </target>

</project>
```

Trong ví dụ, nested `<classpath>` nằm bên trong `javac`. Các JAR trong `application.classpath` được dùng để phân giải kiểu dữ liệu và lớp mà mã nguồn tham chiếu trong lúc biên dịch.

Nếu ứng dụng cần các dependency đó khi chạy, chúng cũng phải được cung cấp cho JVM. Có thể tạo một path runtime riêng:

```xml
<path id="application.runtime.classpath">
    <pathelement location="build/classes"/>
    <pathelement location="lib/domain-api.jar"/>
    <pathelement location="lib/json-library.jar"/>
</path>

<target name="run" depends="compile">
    <java
        classname="com.example.Main"
        fork="true"
        failonerror="true">
        <classpath refid="application.runtime.classpath"/>
    </java>
</target>
```

`javac` và `java` dùng classpath ở hai giai đoạn khác nhau. Dependency có thể cần ở cả hai giai đoạn, nhưng danh sách không nhất thiết giống hệt nhau: một số thư viện chỉ cần khi biên dịch, trong khi một số thư viện khác chỉ được nạp động lúc chạy.

Nếu đóng gói thành JAR để phân phối, hãy bảo đảm người dùng cuối cũng có cách tìm các dependency runtime, chẳng hạn phân phối thư mục `lib/` cùng ứng dụng và khai báo `Class-Path` trong manifest, hoặc dùng cơ chế đóng gói dependency phù hợp.

## 4. Thư viện của task tùy chọn được khai báo ở đâu?

Task tùy chọn là phần mở rộng của Ant. Trước khi sử dụng thẻ task trong build file, Ant phải nạp được lớp triển khai task và các thư viện mà lớp đó cần.

Ví dụ, thư viện `report-ant-task.jar` chứa lớp:

```java
package com.example.ant;

import org.apache.tools.ant.Task;

public class ReportTask extends Task {
    @Override
    public void execute() {
        log("Generating report");
    }
}
```

Giả sử lớp này còn sử dụng một thư viện `report-engine.jar`. Có thể đăng ký task bằng `taskdef` và cung cấp cả hai JAR:

```xml
<taskdef
    name="generate-report"
    classname="com.example.ant.ReportTask">
    <classpath>
        <pathelement location="task-libs/report-ant-task.jar"/>
        <pathelement location="task-libs/report-engine.jar"/>
    </classpath>
</taskdef>

<target name="report">
    <generate-report/>
</target>
```

Nested `<classpath>` ở đây phục vụ việc nạp lớp task. Nó không phải classpath dành cho ứng dụng được build.

Nếu task tùy chọn đã được Ant nhận diện sẵn theo tên, thư viện triển khai vẫn phải có mặt theo hướng dẫn cài đặt của task. Tùy phiên bản Ant và cách phân phối, có thể cần JAR task cùng các dependency đặt trong `ANT_HOME/lib`, hoặc cung cấp qua tùy chọn `-lib` khi chạy Ant.

Ví dụ:

```bash
ant -lib task-libs report
```

Tùy chọn `-lib` bổ sung thư mục hoặc JAR vào classpath của Ant cho lần chạy đó. Nếu task cần nhiều JAR, bạn có thể đặt chúng trong một thư mục được quản lý cùng dự án và truyền thư mục đó. Với task đăng ký bằng `taskdef`, khai báo classpath tường minh giúp người đọc biết thư viện task đến từ đâu.

## 5. Ví dụ kết hợp cả hai nhóm thư viện

Một build file có thể cần cả thư viện ứng dụng và thư viện của task tùy chọn. Ví dụ:

```xml
<project name="combined-build" default="report" basedir=".">

    <property name="src.dir" location="src"/>
    <property name="classes.dir" location="build/classes"/>

    <!-- Classpath dành cho mã nguồn ứng dụng -->
    <path id="application.classpath">
        <pathelement location="lib/domain-api.jar"/>
        <pathelement location="lib/json-library.jar"/>
    </path>

    <!-- Nạp task mở rộng và dependency của chính task -->
    <taskdef
        name="generate-report"
        classname="com.example.ant.ReportTask">
        <classpath>
            <pathelement location="task-libs/report-ant-task.jar"/>
            <pathelement location="task-libs/report-engine.jar"/>
        </classpath>
    </taskdef>

    <target name="compile">
        <mkdir dir="${classes.dir}"/>
        <javac
            srcdir="${src.dir}"
            destdir="${classes.dir}"
            includeantruntime="false"
            encoding="UTF-8">
            <classpath refid="application.classpath"/>
        </javac>
    </target>

    <target name="report" depends="compile">
        <generate-report/>
    </target>

</project>
```

Trong cấu hình này:

1. `application.classpath` chứa các thư viện mà mã nguồn Java sử dụng.
2. Classpath lồng trong `taskdef` chứa lớp triển khai `ReportTask` và dependency của chính task.
3. Target `compile` dùng `application.classpath` cho `javac`.
4. Target `report` gọi task mở rộng sau khi compile hoàn tất.

Nếu chỉ khai báo `report-ant-task.jar` trong `application.classpath`, compiler có thể nhìn thấy lớp task nếu mã nguồn tham chiếu đến nó, nhưng Ant chưa chắc đã đăng ký được thẻ `<generate-report>`. Ngược lại, nếu chỉ đưa `domain-api.jar` vào classpath của `taskdef`, ứng dụng vẫn có thể không biên dịch được nếu `javac` không nhận được thư viện đó.

## 6. Dependency bắc cầu của task tùy chọn

Một task tùy chọn có thể phụ thuộc vào nhiều thư viện khác. Ví dụ:

```text
report-ant-task.jar
        |
        v
report-engine.jar
        |
        v
commons-io.jar
```

Nếu Ant nạp được lớp `ReportTask` nhưng khi thực thi lại thiếu `commons-io.jar`, build có thể gặp `NoClassDefFoundError`. Vì vậy, classpath của task phải chứa đầy đủ dependency cần thiết, không chỉ JAR có lớp task chính.

Khi bổ sung một task library:

- Đọc tài liệu cài đặt của đúng phiên bản task.
- Xác định JAR triển khai task.
- Xác định các dependency runtime mà task cần.
- Kiểm tra phiên bản Ant và JDK tương thích.
- Cung cấp toàn bộ JAR cần thiết cho classloader của Ant theo cách thư viện yêu cầu.
- Tránh đưa nhiều phiên bản khác nhau của cùng một dependency vào cùng classloader nếu chúng có thể xung đột.

Không nên đoán dependency chỉ từ tên file. Một số thư viện đóng gói dependency bên trong JAR, một số yêu cầu cung cấp riêng, và một số dùng cơ chế antlib hoặc service discovery. Hãy dùng tài liệu và metadata phát hành của thư viện làm nguồn xác định.

## 7. Ví dụ quen thuộc: task JUnit và thư viện JUnit

Kiểm thử là tình huống dễ thấy sự khác nhau giữa task library và application/test classpath.

Khi dùng task JUnit cổ điển của Ant, có hai phần cần phân biệt:

- Phần tích hợp task của Ant để Ant nhận diện và thực thi task JUnit.
- Thư viện JUnit và các lớp kiểm thử mà task cần để chạy test.

Một cấu hình minh họa:

```xml
<target name="test" depends="compile">
    <junit fork="true" printsummary="yes">
        <classpath>
            <pathelement location="build/classes"/>
            <pathelement location="build/test-classes"/>
            <pathelement location="lib/application-api.jar"/>
            <pathelement location="lib/junit.jar"/>
        </classpath>

        <formatter type="plain"/>

        <batchtest todir="build/test-reports">
            <fileset dir="build/test-classes">
                <include name="**/*Test.class"/>
            </fileset>
        </batchtest>
    </junit>
</target>
```

Nested `<classpath>` trong task là các lớp cần thiết cho tiến trình kiểm thử, bao gồm output của ứng dụng, output test và thư viện kiểm thử. Phần triển khai optional task JUnit của Ant cùng các dependency mà chính task cần vẫn phải được cài đặt theo hướng dẫn của phiên bản Ant đang sử dụng.

Với JUnit Platform, Ant có task `junitlauncher` ở các phiên bản hỗ trợ. Task này có cách cấu hình và dependency khác với task JUnit cổ điển; không nên sao chép nguyên classpath hoặc hướng dẫn cài đặt giữa hai task. Hãy đọc tài liệu đúng phiên bản Ant và JUnit.

Ví dụ này cho thấy cùng một target kiểm thử có thể cần cả thư viện của Ant task lẫn thư viện ứng dụng/test. Chúng giải quyết hai nhu cầu khác nhau.

## 8. Vì sao đưa JAR vào nhầm classpath không giải quyết được lỗi?

### Đưa task JAR vào classpath của javac

Nếu Ant báo:

```text
taskdef class com.example.ant.ReportTask cannot be found
```

thì việc thêm `report-ant-task.jar` vào nested `<classpath>` của `javac` không giải quyết đúng vấn đề. `javac` chỉ dùng classpath đó để biên dịch mã nguồn. Ant cần JAR trong classpath dùng để nạp task, ví dụ classpath của `taskdef` hoặc classpath Ant theo hướng dẫn cài đặt.

### Đưa application JAR vào classpath của Ant

Nếu ứng dụng báo:

```text
java.lang.NoClassDefFoundError: com/example/domain/Customer
```

thì thêm `domain-api.jar` vào `ANT_HOME/lib` có thể khiến một lớp xuất hiện trong môi trường Ant, nhưng đó không phải cách cấu hình classpath runtime rõ ràng cho ứng dụng. Hãy bổ sung nó vào classpath của task `java`, test runner hoặc cơ chế phân phối ứng dụng phù hợp.

### Đặt task JAR vào thư mục lib của dự án

Việc có file `task-libs/report-ant-task.jar` trên đĩa không khiến Ant tự động nhận diện task. JAR phải được đưa vào classpath của Ant và task phải được đăng ký hoặc được phát hiện theo cơ chế mà thư viện hỗ trợ.

### Chỉ có JAR chính nhưng thiếu dependency

Ant có thể nạp được lớp task chính nhưng lỗi khi task gọi đến một lớp phụ thuộc chưa có. Khi đó, hãy xem class name trong stack trace để xác định JAR nào còn thiếu và bổ sung nó vào classpath task.

## 9. Chọn cách cung cấp task library

Có một số cách phổ biến để đưa thư viện task vào môi trường Ant:

| Cách | Phạm vi | Khi phù hợp |
|---|---|---|
| `ANT_HOME/lib` | Bản cài Ant trên máy | Môi trường dùng chung, được quản trị và kiểm soát phiên bản |
| Truyền `-lib` | Một lần chạy Ant | Script CI hoặc lệnh build muốn chỉ rõ thư mục task library |
| Khai báo classpath trong `taskdef` | Task được đăng ký trong build file | Muốn build file thể hiện rõ JAR triển khai và dependency của task |
| Cơ chế antlib do thư viện cung cấp | Nhóm task/data type theo namespace | Thư viện hỗ trợ đóng gói định nghĩa qua antlib |

### Dùng ANT_HOME/lib

Đặt JAR vào thư mục thư viện của Ant là cách đơn giản, nhưng có thể tạo dependency ẩn: build file không cho biết task library đến từ đâu và hai máy có thể dùng hai phiên bản khác nhau.

Nếu dùng cách này, nhóm nên ghi rõ phiên bản Ant, danh sách JAR bổ sung và cách cài đặt trong tài liệu môi trường.

### Dùng -lib

Ví dụ:

```bash
ant -lib task-libs report
```

Cách này làm rõ thư mục task library trong lệnh chạy. Nó phù hợp với CI hoặc script khởi chạy có thể kiểm soát đường dẫn. Tuy nhiên, lệnh vẫn cần cung cấp đầy đủ dependency của task và build phải đăng ký task nếu thư viện không tự được phát hiện.

### Dùng classpath trong taskdef

Ví dụ:

```xml
<taskdef
    resource="com/example/ant/antlib.xml"
    uri="antlib:com.example.ant">
    <classpath>
        <pathelement location="task-libs/example-ant-tasks.jar"/>
        <pathelement location="task-libs/example-engine.jar"/>
    </classpath>
</taskdef>
```

Ví dụ này giả định JAR cung cấp resource antlib ở đường dẫn đã nêu. Hãy dùng đúng resource và URI do thư viện tài liệu hóa; không phải mọi task library đều cung cấp antlib.

## 10. Quản lý dependency để build tái lập

Một build file chỉ chạy được trên máy tác giả vì máy đó đã cài task library toàn cục là dấu hiệu của dependency chưa được mô tả đầy đủ.

Để thành viên khác và CI có thể tái tạo:

- Ghi rõ phiên bản Ant và JDK được hỗ trợ.
- Ghi rõ các optional task cần dùng và nguồn phát hành của chúng.
- Quản lý phiên bản task JAR và dependency bắc cầu.
- Phân biệt thư mục task library với thư mục dependency ứng dụng.
- Khai báo application classpath rõ ràng cho compile, test và runtime.
- Dùng một script hoặc tài liệu thống nhất để truyền `-lib` nếu dự án chọn cách đó.
- Không phụ thuộc ngầm vào `ANT_HOME/lib` của từng máy.
- Tránh commit thông tin xác thực hoặc thư viện không rõ nguồn gốc vào repository.

Ví dụ cấu trúc có thể giúp phân biệt:

```text
project/
├── build.xml
├── src/
├── lib/
│   ├── application-api.jar
│   └── json-library.jar
├── task-libs/
│   ├── custom-ant-task.jar
│   └── custom-task-engine.jar
└── build/
```

Nếu dùng `-lib task-libs`, hãy bảo đảm thư mục đó được tạo và có đúng dependency trước khi gọi Ant. Nếu dùng `taskdef` với classpath cục bộ, build file cần tham chiếu các JAR ở vị trí ổn định.

Không phải lúc nào cũng cần duy trì hai thư mục vật lý riêng. Một dự án nhỏ có thể lưu chung các JAR trong một nơi, nhưng vẫn nên khai báo riêng hai path theo mục đích để không vô tình đưa task library vào sản phẩm ứng dụng hoặc bỏ quên application dependency ở runtime.

## 11. Chẩn đoán lỗi theo classloader

| Lỗi | Nơi cần kiểm tra trước | Hướng xử lý |
|---|---|---|
| `task ... not found` | Đăng ký task và classpath của Ant | Kiểm tra `taskdef`, antlib, `-lib` và tên task |
| `taskdef class ... cannot be found` | JAR triển khai task | Bổ sung đúng JAR vào classpath của `taskdef` hoặc Ant |
| `NoClassDefFoundError` khi task bắt đầu chạy | Dependency của task tùy chọn | Xác định lớp thiếu và thêm JAR tương ứng vào task classpath |
| `package ... does not exist` khi javac chạy | Application compile classpath | Thêm thư viện ứng dụng vào nested `<classpath>` của `javac` |
| `ClassNotFoundException` khi ứng dụng chạy | Application runtime classpath | Bổ sung dependency cho task `java`, test runner hoặc gói phát hành |
| Task chạy được trên máy cá nhân nhưng lỗi trên CI | Cấu hình Ant toàn cục hoặc JAR task thiếu trong CI | So sánh `ANT_HOME`, phiên bản Ant, tùy chọn `-lib` và task classpath |
| `NoSuchMethodError` hoặc lỗi liên kết | Phiên bản JAR không tương thích hoặc trùng lặp | Kiểm tra dependency graph và loại bỏ phiên bản xung đột |

Khi đọc stack trace, hãy xác định lỗi xảy ra trong lúc Ant nạp task, lúc task thực thi, lúc compiler biên dịch ứng dụng hay trong JVM của ứng dụng. Vị trí phát sinh lỗi thường chỉ ra classpath cần kiểm tra.

Các lệnh hữu ích:

```bash
ant -version
ant -diagnostics
ant -verbose report
```

`ant -version` xác nhận bản Ant đang chạy. `ant -diagnostics` cung cấp thông tin môi trường và thư viện Ant nhận diện được. `-verbose` giúp theo dõi quá trình nạp và thực thi task chi tiết hơn.

## 12. Ghi nhớ

- Thư viện ứng dụng cung cấp lớp cho mã nguồn hoặc chương trình; khai báo chúng trong classpath của `javac`, `java` hoặc test task.
- Thư viện của task tùy chọn cung cấp implementation và dependency cho Ant; đưa chúng vào classpath Ant hoặc classpath của `taskdef` theo tài liệu task.
- Classpath của Ant và classpath của ứng dụng là hai cấu hình khác nhau; đặt JAR vào một nơi không tự động đưa nó vào nơi còn lại.
- Một task tùy chọn có thể có dependency bắc cầu; phải cung cấp đầy đủ các JAR cần thiết.
- Task library có thể được cung cấp qua `ANT_HOME/lib`, `-lib`, `taskdef` hoặc antlib, tùy cơ chế mà thư viện hỗ trợ.
- Với task kiểm thử, thường phải phân biệt thư viện triển khai task của Ant với thư viện framework và classpath của các lớp test.
- Muốn build chạy ổn định trên máy khác, hãy ghi rõ phiên bản và quản lý cả hai nhóm dependency.

Khi gặp lỗi thiếu lớp, trước tiên hãy xác định lớp đó thuộc về Ant task hay ứng dụng đang được build. Sau đó đặt JAR vào đúng classpath: task implementation cho môi trường Ant, application dependency cho compiler hoặc JVM chạy chương trình. Cách phân chia này giúp tránh các dependency ẩn và làm build dễ tái lập hơn.
