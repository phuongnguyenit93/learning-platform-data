# Chạy lớp có `main` bằng task `java`

Sau khi biên dịch mã nguồn Java, dự án cần một bước để khởi chạy ứng dụng. Apache Ant cung cấp task `<java>` để gọi phương thức `main` của một lớp Java, truyền đối số, thiết lập classpath và cấu hình môi trường chạy. Nhờ đó, việc chạy ứng dụng có thể được mô tả ngay trong `build.xml` và trở thành một phần của quy trình build.

Task `<java>` có thể chạy lớp trong JVM đang thực thi Ant hoặc khởi chạy một JVM riêng. Lựa chọn này ảnh hưởng tới cách ứng dụng nhận classpath, tham số JVM, thư mục làm việc và cách Ant xử lý mã thoát của chương trình.

## 1. Cấu trúc cơ bản của task `<java>`

Giả sử dự án có lớp sau:

```java
package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from Ant");
    }
}
```

Sau khi biên dịch lớp vào `build/classes`, có thể chạy bằng Ant:

```xml
<java classname="com.example.Main" fork="true"/>
```

Thuộc tính `classname` nhận tên đầy đủ của lớp (fully qualified class name), bao gồm package. Không thêm phần mở rộng `.java` hoặc `.class` vào giá trị này.

Một target tối thiểu có thể viết như sau:

```xml
<project name="java-run-demo" default="run" basedir=".">

    <property name="classes.dir" location="build/classes"/>

    <target name="run">
        <java classname="com.example.Main" fork="true">
            <classpath>
                <pathelement location="${classes.dir}"/>
            </classpath>
        </java>
    </target>

</project>
```

Phần tử `<classpath>` cho JVM biết nơi tìm lớp đã biên dịch. Nếu không có classpath phù hợp, Ant có thể không tìm thấy lớp `com.example.Main` hoặc các thư viện mà lớp đó sử dụng.

## 2. Kết hợp biên dịch và chạy ứng dụng

Thông thường, target chạy ứng dụng phụ thuộc vào target biên dịch để bảo đảm bytecode đã tồn tại trước khi khởi chạy.

```xml
<project name="inventory-app" default="run" basedir=".">

    <property name="src.dir" location="src/main/java"/>
    <property name="classes.dir" location="build/classes"/>

    <target name="compile">
        <mkdir dir="${classes.dir}"/>
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               includeantruntime="false"
               encoding="UTF-8"/>
    </target>

    <target name="run" depends="compile">
        <java classname="com.example.Main"
              fork="true"
              failonerror="true">
            <classpath>
                <pathelement location="${classes.dir}"/>
            </classpath>
        </java>
    </target>

</project>
```

Khi chạy:

```sh
ant run
```

Ant thực hiện target `compile` trước, sau đó gọi lớp `com.example.Main`. Nếu biên dịch thất bại, target `run` không được thực hiện vì prerequisite chưa hoàn thành.

## 3. Chọn chạy trong JVM của Ant hay JVM riêng

Thuộc tính `fork` quyết định cách task khởi chạy chương trình:

| Cấu hình | Hành vi |
|---|---|
| `fork="false"` (mặc định) | Chạy lớp trong JVM đang thực thi Ant thông qua cơ chế class loader của Ant |
| `fork="true"` | Khởi chạy một tiến trình JVM riêng cho ứng dụng |

### Chạy không fork

```xml
<java classname="com.example.Main" fork="false">
    <classpath>
        <pathelement location="build/classes"/>
    </classpath>
</java>
```

Chế độ không fork có thể tiện cho tác vụ Java ngắn, đơn giản và không cần tùy chỉnh JVM. Vì chương trình chạy trong cùng JVM với Ant, nó dùng chung tiến trình và một phần môi trường runtime với build tool. Những tùy chọn chỉ dành cho tiến trình JVM con như tham số khởi chạy JVM, giới hạn bộ nhớ hoặc thư mục làm việc riêng không có tác dụng theo cách giống chế độ fork.

### Chạy fork

```xml
<java classname="com.example.Main"
      fork="true"
      failonerror="true">
    <classpath>
        <pathelement location="build/classes"/>
    </classpath>
</java>
```

Chế độ fork phù hợp khi ứng dụng cần JVM riêng, cần truyền tùy chọn JVM, cần tách biệt vòng đời tiến trình hoặc cần kiểm soát thư mục làm việc và đầu vào/đầu ra. Nó cũng giúp tránh để trạng thái runtime của ứng dụng ảnh hưởng trực tiếp tới JVM chạy Ant.

## 4. Cấu hình classpath

Ứng dụng thường phụ thuộc vào nhiều JAR ngoài các lớp của chính dự án. Có thể khai báo classpath ngay trong task:

```xml
<java classname="com.example.Main" fork="true">
    <classpath>
        <pathelement location="build/classes"/>
        <fileset dir="lib" includes="*.jar"/>
    </classpath>
</java>
```

Nếu nhiều target cùng dùng classpath, nên khai báo một `Path` có `id` và tham chiếu lại:

```xml
<path id="application.classpath">
    <pathelement location="build/classes"/>
    <fileset dir="lib" includes="**/*.jar"/>
</path>

<target name="run">
    <java classname="com.example.Main" fork="true">
        <classpath refid="application.classpath"/>
    </java>
</target>
```

`id` đặt tên cho path; `refid` yêu cầu task dùng lại danh sách vị trí đã khai báo. Cách này giảm lặp cấu hình và giúp classpath biên dịch/chạy được quản lý tập trung.

Hãy phân biệt classpath dùng để biên dịch và classpath dùng để chạy. Một thư viện có thể cần ở cả hai giai đoạn, nhưng một số dependency chỉ cần trong runtime hoặc chỉ cần cho compiler. Task `<java>` phải nhận đủ lớp ứng dụng và các dependency thực sự cần khi chương trình chạy.

## 5. Truyền đối số cho `main(String[] args)`

Đối số dòng lệnh được truyền bằng các phần tử lồng `<arg>`. Mỗi phần tử `<arg value="..."/>` tạo một đối số riêng trong mảng `args` của phương thức `main`.

```xml
<java classname="com.example.Main" fork="true">
    <classpath>
        <pathelement location="build/classes"/>
    </classpath>
    <arg value="--profile"/>
    <arg value="test"/>
    <arg value="--port"/>
    <arg value="8080"/>
</java>
```

Ứng dụng nhận được mảng đối số tương đương:

```java
args[0] = "--profile";
args[1] = "test";
args[2] = "--port";
args[3] = "8080";
```

Nếu một đối số chứa khoảng trắng, vẫn đặt toàn bộ giá trị trong cùng một phần tử `<arg>`:

```xml
<arg value="Inventory Service"/>
```

Khi đó `args` nhận một phần tử duy nhất là `Inventory Service`, không phải hai đối số riêng. Cách này giúp tránh vấn đề dấu nháy và phân tách chuỗi khi Ant gọi tiến trình.

Có thể dùng `line` để cung cấp một chuỗi đối số theo cú pháp dòng lệnh:

```xml
<arg line="--profile test --port 8080"/>
```

Với buildfile cần xử lý giá trị có khoảng trắng hoặc ký tự đặc biệt, các phần tử `<arg value="..."/>` riêng thường rõ ràng và ít gây nhầm lẫn hơn.

## 6. Thiết lập system property cho ứng dụng

Nếu ứng dụng đọc cấu hình qua `System.getProperty`, có thể truyền system property bằng phần tử `<sysproperty>`:

```xml
<java classname="com.example.Main" fork="true">
    <classpath>
        <pathelement location="build/classes"/>
    </classpath>
    <sysproperty key="app.profile" value="test"/>
    <sysproperty key="app.config" value="config/test.properties"/>
</java>
```

Trong mã Java:

```java
String profile = System.getProperty("app.profile");
String config = System.getProperty("app.config");
System.out.println("Profile: " + profile);
System.out.println("Config: " + config);
```

`<sysproperty>` đặt thuộc tính hệ thống cho tiến trình Java được khởi chạy. Nó khác với `<arg>`: đối số xuất hiện trong `String[] args`, còn system property được đọc qua `System.getProperty`.

Nếu giá trị được khai báo bằng property Ant, có thể tham chiếu bằng `${...}`:

```xml
<property name="run.profile" value="test"/>

<java classname="com.example.Main" fork="true">
    <classpath refid="application.classpath"/>
    <sysproperty key="app.profile" value="${run.profile}"/>
</java>
```

Không đặt thông tin bí mật như mật khẩu production trực tiếp trong `build.xml` hoặc dòng lệnh nếu chúng có thể bị lưu trong repository hoặc log. Hãy sử dụng cơ chế quản lý bí mật phù hợp với môi trường triển khai.

## 7. Truyền tham số cho chính JVM bằng `<jvmarg>`

Đối số ứng dụng và đối số JVM có mục đích khác nhau. Dùng `<arg>` để truyền dữ liệu cho `main`; dùng `<jvmarg>` để truyền tùy chọn lúc khởi chạy JVM.

Ví dụ:

```xml
<java classname="com.example.Main" fork="true">
    <classpath refid="application.classpath"/>
    <jvmarg value="-Xms128m"/>
    <jvmarg value="-Xmx512m"/>
    <jvmarg value="-Dfile.encoding=UTF-8"/>
    <arg value="--profile"/>
    <arg value="test"/>
</java>
```

Ở đây:

- `-Xms128m` đặt kích thước heap ban đầu.
- `-Xmx512m` giới hạn heap tối đa.
- `-Dfile.encoding=UTF-8` đặt system property cho JVM.
- `--profile` và `test` là đối số của ứng dụng.

Các phần tử `<jvmarg>` có ý nghĩa khi `fork="true"`, vì Ant cần truyền chúng cho tiến trình JVM con. Khi không fork, không có JVM mới để nhận các tùy chọn khởi chạy đó.

Ngoài `<jvmarg>`, task có thuộc tính `maxmemory` để cấu hình giới hạn bộ nhớ cho JVM được fork:

```xml
<java classname="com.example.Main" fork="true" maxmemory="512m">
    <classpath refid="application.classpath"/>
</java>
```

Nếu đã dùng `maxmemory`, tránh khai báo một giới hạn heap khác mâu thuẫn trong `jvmarg -Xmx...`. Nên chọn một cách cấu hình rõ ràng để người đọc biết giới hạn thực tế.

## 8. Chọn JVM thực thi

Khi chạy fork, Ant thường dùng Java executable của môi trường đang chạy Ant. Có thể chỉ định executable khác bằng thuộc tính `jvm`:

```xml
<java classname="com.example.Main"
      fork="true"
      jvm="C:/Java/jdk-21/bin/java.exe">
    <classpath refid="application.classpath"/>
</java>
```

Đường dẫn ví dụ cần được thay bằng vị trí Java thực tế. Nếu muốn build di động giữa nhiều máy, nên quản lý đường dẫn JDK qua property hoặc cấu hình môi trường thay vì cố định đường dẫn cá nhân trong buildfile.

Có thể xác định Java mà môi trường hiện tại đang dùng bằng các lệnh:

```sh
java -version
where java
```

Trên Linux/macOS, dùng `command -v java` để xem executable được tìm thấy qua `PATH`. Nếu Ant được khởi chạy bằng một JDK khác với JVM mà task `<java>` cần dùng, hãy cấu hình rõ executable và kiểm tra tương thích phiên bản.

## 9. Thư mục làm việc và biến môi trường

Khi ứng dụng đọc tệp bằng đường dẫn tương đối, thư mục làm việc ảnh hưởng tới vị trí tệp được tìm thấy. Với JVM được fork, có thể đặt thư mục làm việc bằng thuộc tính `dir`:

```xml
<java classname="com.example.Main"
      fork="true"
      dir="${basedir}"
      failonerror="true">
    <classpath refid="application.classpath"/>
    <arg value="config/test.properties"/>
</java>
```

Trong ví dụ, ứng dụng nhận đường dẫn tương đối `config/test.properties`; tiến trình được khởi chạy với thư mục làm việc là thư mục cơ sở của project. Nếu không đặt `dir`, tiến trình thường kế thừa thư mục làm việc hiện tại của Ant.

Task cũng hỗ trợ truyền biến môi trường qua nested `<env>` khi chạy fork:

```xml
<java classname="com.example.Main" fork="true">
    <classpath refid="application.classpath"/>
    <env key="APP_PROFILE" value="test"/>
</java>
```

Ứng dụng có thể đọc biến này qua `System.getenv("APP_PROFILE")`. Biến môi trường và system property là hai cơ chế khác nhau: biến môi trường đến từ tiến trình hệ điều hành, còn system property được thiết lập trong JVM.

## 10. Kiểm soát lỗi và mã thoát

Khi ứng dụng chạy trong JVM riêng, tiến trình có thể kết thúc với mã thoát khác 0 để báo lỗi. Task `<java>` có thuộc tính `failonerror` và `resultproperty` để điều khiển cách Ant phản ứng.

```xml
<java classname="com.example.Main"
      fork="true"
      failonerror="true">
    <classpath refid="application.classpath"/>
</java>
```

Với `failonerror="true"`, Ant đánh dấu task thất bại nếu tiến trình trả về mã thoát khác 0. Đây thường là lựa chọn phù hợp khi target chạy ứng dụng là một bước bắt buộc của build.

Nếu muốn ghi nhận mã thoát và để các bước tiếp theo tự quyết định, có thể dùng `resultproperty` cùng `failonerror="false"`:

```xml
<java classname="com.example.Main"
      fork="true"
      failonerror="false"
      resultproperty="application.exit.code">
    <classpath refid="application.classpath"/>
</java>

<echo message="Application exit code: ${application.exit.code}"/>
```

`resultproperty` nhận mã thoát của tiến trình fork. Ant property có tính bất biến: nếu property cùng tên đã được đặt trước đó, lần chạy sau không thể thay đổi giá trị đã có. Vì vậy, hãy chọn tên property phù hợp hoặc thiết kế target để không dựa vào việc cùng một property được cập nhật qua nhiều lần chạy trong cùng một build.

`failonerror="false"` không biến lỗi của ứng dụng thành thành công về mặt nghiệp vụ; nó chỉ cho phép task không làm build dừng ngay vì mã thoát khác 0. Buildfile cần kiểm tra kết quả và xử lý tiếp theo một cách có chủ đích.

## 11. Giới hạn thời gian và chuyển hướng đầu ra

Với tiến trình fork, có thể đặt timeout để Ant không chờ ứng dụng vô thời hạn:

```xml
<java classname="com.example.BatchJob"
      fork="true"
      timeout="60000"
      failonerror="true">
    <classpath refid="application.classpath"/>
</java>
```

`timeout` tính bằng mili giây; ví dụ `60000` là 60 giây. Nếu chương trình chạy lâu hơn giới hạn, Ant dừng tiến trình theo cơ chế timeout và đánh dấu lần thực thi thất bại.

Có thể chuyển hướng stdout và stderr của tiến trình sang tệp:

```xml
<java classname="com.example.Main"
      fork="true"
      output="build/logs/application.out"
      error="build/logs/application.err"
      append="false">
    <classpath refid="application.classpath"/>
</java>
```

Trước khi chạy, hãy tạo thư mục log:

```xml
<mkdir dir="build/logs"/>
```

`output` chỉ định tệp nhận đầu ra chuẩn; `error` chỉ định tệp nhận đầu ra lỗi. `append` điều khiển việc nối vào tệp đã tồn tại hay ghi mới theo cấu hình task. Việc lưu log giúp phân tích lỗi sau khi target kết thúc.

Task còn hỗ trợ `input` hoặc `inputstring` để cung cấp dữ liệu chuẩn đầu vào cho chương trình trong các trường hợp cần thiết. Ví dụ:

```xml
<java classname="com.example.ConfirmJob" fork="true">
    <classpath refid="application.classpath"/>
    <inputstring>yes</inputstring>
</java>
```

Chỉ dùng đầu vào dạng này khi chương trình thực sự đọc stdin. Một chương trình chờ tương tác phức tạp có thể phù hợp hơn với một quy trình chạy riêng hoặc công cụ điều phối khác.

## 12. Chạy một JAR có manifest Main-Class

Nếu ứng dụng được đóng gói thành executable JAR và manifest khai báo `Main-Class`, task `<java>` có thể chạy JAR bằng thuộc tính `jar`:

```xml
<java jar="dist/inventory-app.jar" fork="true" failonerror="true">
    <arg value="--profile"/>
    <arg value="test"/>
</java>
```

Đây là cách chạy JAR tương đương với lệnh `java -jar` ở mức ý tưởng. Với chế độ chạy JAR, JVM dùng cấu hình classpath theo quy tắc executable JAR và manifest; không nên giả định nested classpath hoạt động giống khi gọi trực tiếp `classname`. Nếu JAR cần thư viện ngoài, phải đóng gói hoặc khai báo chúng theo cơ chế manifest/deployment phù hợp.

Nếu mục tiêu là gọi một lớp cụ thể trên classpath của dự án, dùng `classname`. Nếu mục tiêu là chạy gói JAR đã phát hành, dùng `jar` khi manifest được cấu hình đúng.

## 13. Một ví dụ hoàn chỉnh với tham số và log

Ví dụ sau biên dịch ứng dụng, chuẩn bị thư mục log, truyền đối số và system property, sau đó ghi stdout/stderr ra tệp:

```xml
<project name="inventory-runner" default="run" basedir=".">

    <property name="src.dir" location="src/main/java"/>
    <property name="classes.dir" location="build/classes"/>
    <property name="lib.dir" location="lib"/>
    <property name="logs.dir" location="build/logs"/>
    <property name="profile" value="test"/>

    <path id="application.classpath">
        <pathelement location="${classes.dir}"/>
        <fileset dir="${lib.dir}" includes="**/*.jar"/>
    </path>

    <target name="compile">
        <mkdir dir="${classes.dir}"/>
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               includeantruntime="false"
               encoding="UTF-8"/>
    </target>

    <target name="run" depends="compile">
        <mkdir dir="${logs.dir}"/>
        <java classname="com.example.inventory.Main"
              fork="true"
              failonerror="true"
              dir="${basedir}"
              output="${logs.dir}/application.out"
              error="${logs.dir}/application.err"
              timeout="120000">
            <classpath refid="application.classpath"/>
            <sysproperty key="app.profile" value="${profile}"/>
            <jvmarg value="-Xmx512m"/>
            <arg value="--mode"/>
            <arg value="batch"/>
        </java>
    </target>

</project>
```

Chạy:

```sh
ant run
```

Target `run` chỉ bắt đầu sau khi `compile` hoàn tất. JVM con nhận classpath gồm lớp ứng dụng và các JAR trong `lib`; ứng dụng nhận system property `app.profile=test` và hai đối số `--mode`, `batch`. stdout và stderr được ghi vào hai tệp log. Nếu chương trình trả mã thoát khác 0 hoặc vượt timeout, task thất bại và target `run` được đánh dấu lỗi.

Có thể thay profile mặc định bằng property dòng lệnh:

```sh
ant -Dprofile=production run
```

## 14. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Ant báo không tìm thấy lớp main | Sai `classname` hoặc classpath thiếu thư mục chứa `.class` | Kiểm tra package, tên lớp và thêm đúng thư mục đầu ra vào classpath |
| Lớp main chạy nhưng không tìm thấy dependency | Runtime classpath thiếu JAR cần thiết | Bổ sung JAR vào path của task `<java>` |
| Ứng dụng không nhận đúng đối số | Dùng `arg line` không phù hợp hoặc ghép nhiều giá trị thành một arg | Dùng từng `<arg value="..."/>` và kiểm tra mảng `args` |
| `System.getProperty` trả về `null` | Chưa khai báo `<sysproperty>` hoặc dùng nhầm `<arg>` | Dùng `<sysproperty key="..." value="..."/>` cho system property |
| Tùy chọn `-Xmx` không có tác dụng | Chương trình chạy không fork | Đặt `fork="true"` để truyền tùy chọn khởi chạy JVM |
| Build vẫn thành công dù ứng dụng trả mã lỗi | `failonerror` đang là `false` hoặc chưa xử lý result property | Đặt `failonerror="true"` hoặc kiểm tra `resultproperty` một cách tường minh |
| Ứng dụng không tìm thấy tệp cấu hình tương đối | Thư mục làm việc không như dự kiến | Đặt `dir` khi fork và dùng đường dẫn tương đối với thư mục đó |
| Log không xuất hiện | Chưa tạo thư mục log hoặc chuyển hướng sai thuộc tính | Tạo thư mục trước bằng `<mkdir>` và kiểm tra `output`/`error` |
| Tiến trình chạy quá lâu | Ứng dụng bị treo hoặc đang chờ I/O | Xác định thời gian chạy hợp lệ và đặt `timeout` khi phù hợp |
| Chạy executable JAR nhưng thiếu thư viện | JAR chưa khai báo dependency runtime trong manifest hoặc gói phát hành | Kiểm tra manifest và cách đóng gói thư viện; không giả định classpath lồng sẽ bổ sung cho `java -jar` |

## 15. Checklist khi dùng task `<java>`

- [ ] `classname` là tên đầy đủ của lớp có `public static void main(String[] args)`.
- [ ] Target chạy phụ thuộc target biên dịch khi cần bytecode mới.
- [ ] Classpath chứa thư mục lớp và dependency runtime cần thiết.
- [ ] Đã chọn `fork` dựa trên nhu cầu về JVM riêng, JVM arguments và vòng đời tiến trình.
- [ ] Đối số ứng dụng được truyền bằng `<arg>`; system property bằng `<sysproperty>`; tùy chọn JVM bằng `<jvmarg>`.
- [ ] Thư mục làm việc được xác định nếu ứng dụng đọc đường dẫn tương đối.
- [ ] `failonerror` và `resultproperty` được cấu hình phù hợp với chính sách build.
- [ ] Có timeout và chuyển hướng log khi ứng dụng chạy lâu hoặc cần lưu kết quả chẩn đoán.
- [ ] Nếu chạy JAR, manifest có `Main-Class` và dependency runtime được cấu hình đúng.
- [ ] Đã kiểm tra lệnh chạy trong target Ant trên môi trường mục tiêu.

Task `<java>` giúp đưa việc khởi chạy chương trình Java vào buildfile. Dùng `classname` để chạy lớp có `main`, cung cấp classpath đúng, truyền từng loại tham số qua đúng phần tử và quyết định rõ cách xử lý tiến trình sẽ giúp target chạy ứng dụng dễ tái lập và dễ chẩn đoán khi có lỗi.
