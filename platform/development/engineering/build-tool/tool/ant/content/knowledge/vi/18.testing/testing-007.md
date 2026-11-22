# Chọn JVM, working directory và tham số cho tiến trình kiểm thử

Khi chạy kiểm thử bằng Apache Ant, đôi khi cần một tiến trình Java riêng với JDK, thư mục làm việc, tham số dòng lệnh và biến môi trường được kiểm soát. Ví dụ, bộ kiểm thử có thể cần chạy bằng JDK 17 trong khi Ant đang chạy bằng JDK 21, cần đọc fixture tương đối với một thư mục test riêng hoặc cần nhận các tùy chọn như `--profile integration`.

Task `<java>` của Ant có thể khởi chạy một lớp Java hoặc một JAR. Khi bật `fork="true"`, Ant tạo JVM con và cung cấp các thuộc tính để chọn executable, working directory, JVM arguments, application arguments, system properties và environment variables. Đây là cách phù hợp khi muốn kiểm soát tiến trình kiểm thử độc lập với JVM đang chạy Ant.

## 1. Phân biệt JVM của Ant và JVM chạy kiểm thử

Ant là một chương trình Java, nên bản thân tiến trình Ant đã chạy bên trong một JVM. Khi task `<java>` được cấu hình `fork="true"`, task khởi chạy một tiến trình Java khác để chạy test launcher hoặc chương trình kiểm thử.

```text
Terminal / CI job
      |
      v
   Ant process
   JVM A (JDK dùng để chạy Ant)
      |
      |  <java fork="true">
      v
   Test process
   JVM B (JDK dùng để chạy kiểm thử)
      |
      v
   Test runner / test suite
```

Hai JVM có thể dùng cùng một JDK hoặc hai JDK khác nhau. Chẳng hạn, Ant có thể chạy bằng JDK 21 nhưng test integration cần xác nhận ứng dụng tương thích với JDK 17. Khi đó, chọn executable Java 17 cho tiến trình kiểm thử.

Nếu không fork, task `<java>` chạy lớp được chỉ định trong JVM của Ant. Khi ấy không thể chọn một executable JVM khác cho lần chạy đó, và các thiết lập riêng của một tiến trình như working directory hay environment không có cùng ý nghĩa như khi fork.

### 1.1. Khi nào cần fork?

Nên dùng `fork="true"` khi:

- Cần chạy test bằng một JDK khác với JDK đang chạy Ant.
- Cần truyền JVM arguments như `-Xmx`, `-ea`, `-D...` hoặc tùy chọn module.
- Cần đặt working directory riêng cho test process.
- Cần kiểm soát environment variables của tiến trình con.
- Muốn cô lập lỗi hoặc trạng thái static của test khỏi JVM Ant.
- Cần timeout cho một tiến trình kiểm thử độc lập.

Không fork có thể tiết kiệm thời gian khởi động và phù hợp với một số task chạy nhanh, nhưng dùng chung JVM có thể làm trạng thái hệ thống hoặc classloader ảnh hưởng giữa các lần thực thi. Với kiểm thử cần xác nhận môi trường runtime thực tế, fork thường rõ ràng hơn.

## 2. Chọn executable JVM bằng thuộc tính `jvm`

Khi `fork="true"`, thuộc tính `jvm` của task `<java>` chỉ định đường dẫn đến chương trình Java dùng để khởi chạy tiến trình con. Nếu không chỉ định, Ant sử dụng Java executable tương ứng với môi trường Java đang chạy Ant.

Ví dụ:

```xml
<property name="test.java" value="/opt/jdk-17/bin/java"/>

<target name="test-integration">
    <java classname="com.example.tests.IntegrationTestLauncher"
          fork="true"
          jvm="${test.java}"
          failonerror="true">
        <classpath refid="test.classpath"/>
    </java>
</target>
```

Đường dẫn trong ví dụ là Linux. Trên Windows, executable thường có tên `java.exe`, ví dụ `C:\Program Files\Java\jdk-17\bin\java.exe`.

### 2.1. Đặt JVM theo môi trường

Có thể truyền đường dẫn JVM từ dòng lệnh để cùng một build file chạy trên nhiều máy:

```bash
ant -Dtest.java=/opt/jdk-17/bin/java test-integration
```

PowerShell trên Windows:

```powershell
ant "-Dtest.java=C:\Program Files\Java\jdk-17\bin\java.exe" test-integration
```

Trong build file, nên có giá trị mặc định phù hợp với môi trường hoặc yêu cầu CI cung cấp `test.java` rõ ràng. Nếu dùng một đường dẫn mặc định, hãy đảm bảo nó tồn tại trên mọi máy chạy target đó.

Ví dụ khai báo theo biến môi trường `JAVA17_HOME`:

```xml
<property environment="env"/>
<property name="test.java" location="${env.JAVA17_HOME}/bin/java"/>

<target name="check-test-java">
    <fail unless="env.JAVA17_HOME"
          message="JAVA17_HOME must point to the JDK used for integration tests."/>
    <echo message="Test JVM: ${test.java}"/>
</target>
```

Trên Windows, cần cấu hình đường dẫn đến `java.exe` tương ứng, chẳng hạn dùng một property riêng theo môi trường. Không giả định rằng đường dẫn `/bin/java` trên mọi hệ điều hành đều trỏ đến executable hợp lệ.

### 2.2. Kiểm tra JVM đã chọn

Trước khi chạy test, có thể in cấu hình executable mà build định dùng:

```xml
<echo message="Test JVM: ${test.java}"/>
```

Để xác nhận runtime thực tế, có thể gọi một launcher nhỏ in `java.version`, `java.vendor` và `java.home`, hoặc chạy một target chẩn đoán riêng. Không nên chỉ dựa vào `java -version` trong terminal nếu target sử dụng một executable khác thông qua thuộc tính `jvm`. Đoạn `<echo>` ở trên cần nằm bên trong một target.

## 3. Working directory của tiến trình kiểm thử

Thuộc tính `dir` của task `<java>` chỉ định thư mục làm việc hiện tại cho tiến trình Java được fork. Đây là thư mục mà chương trình con nhìn thấy như working directory khi mở các đường dẫn tương đối.

Ví dụ:

```xml
<property name="test.work.dir" location="${basedir}/build/test-work"/>

<target name="prepare-test-work">
    <mkdir dir="${test.work.dir}"/>
</target>

<target name="test-integration" depends="prepare-test-work">
    <java classname="com.example.tests.IntegrationTestLauncher"
          fork="true"
          dir="${test.work.dir}"
          failonerror="true">
        <classpath refid="test.classpath"/>
    </java>
</target>
```

Nếu launcher đọc tệp `fixtures/request.json` bằng đường dẫn tương đối, chương trình sẽ tìm đường dẫn đó bên dưới `build/test-work`, không phải mặc nhiên bên dưới thư mục chứa `build.xml`.

### 3.1. Tách working directory khỏi thư mục dự án

Một cấu trúc thường dùng:

```text
sample-project/
├── build.xml
├── src/
│   └── test/java/
├── test-data/
│   └── integration/
└── build/
    └── test-work/
        ├── fixtures/
        ├── temp/
        └── reports/
```

Thư mục `test-work` có thể được tạo lại trước mỗi lần test. Test process có thể ghi file tạm và log vào đây mà không làm bẩn thư mục source.

Nếu test cần đọc dữ liệu gốc ở `test-data/integration`, hãy truyền đường dẫn tuyệt đối qua system property hoặc application argument thay vì giả định working directory luôn giống nhau:

```xml
<java classname="com.example.tests.IntegrationTestLauncher"
      fork="true"
      dir="${test.work.dir}"
      failonerror="true">
    <classpath refid="test.classpath"/>
    <sysproperty key="test.data.dir"
                 value="${basedir}/test-data/integration"/>
</java>
```

Trong mã Java, test có thể đọc `System.getProperty("test.data.dir")` để tìm fixture. Cách này giữ rõ hai vai trò: `dir` xác định nơi tiến trình bắt đầu làm việc; `test.data.dir` xác định vị trí dữ liệu đầu vào của test.

### 3.2. Phân biệt `dir` và `user.dir`

Khi tiến trình được fork với `dir`, Ant đặt working directory của tiến trình theo thư mục đã chỉ định. Không nên dùng `-Duser.dir=...` như cách thay thế cho `dir`: thay đổi property `user.dir` không tương đương với việc thay đổi current working directory của hệ điều hành cho tiến trình.

Nếu cần một thư mục làm việc cụ thể, hãy dùng `dir` của `<java fork="true">`. Nếu test chỉ cần một đường dẫn dữ liệu, truyền một system property hoặc argument chứa đường dẫn rõ ràng.

### 3.3. Working directory phải tồn tại

Hãy tạo thư mục làm việc trước khi khởi chạy tiến trình. Nếu thư mục chưa tồn tại, task có thể không khởi chạy được.

```xml
<target name="prepare-test-work">
    <delete dir="${test.work.dir}" quiet="true"/>
    <mkdir dir="${test.work.dir}"/>
</target>
```

Chỉ xóa thư mục mà build sở hữu, chẳng hạn một thư mục con riêng dưới `build/`. Không dùng một đường dẫn quá rộng như thư mục home hoặc thư mục dự án làm đích cho thao tác xóa.

Nếu cần giữ log hoặc dữ liệu sau test để điều tra lỗi, không xóa thư mục làm việc trước khi thu thập artifact. Có thể dọn nó trong target `clean` hoặc trong bước cleanup của CI sau khi đã lưu báo cáo.

## 4. Phân biệt JVM arguments và application arguments

Một tiến trình Java nhận hai nhóm tham số chính:

1. JVM arguments: được xử lý bởi chương trình `java` trước khi lớp main chạy.
2. Application arguments: được truyền cho phương thức `main(String[] args)` của chương trình.

Trong Ant, dùng `<jvmarg>` cho nhóm thứ nhất và `<arg>` cho nhóm thứ hai.

```xml
<java classname="com.example.tests.IntegrationTestLauncher"
      fork="true"
      failonerror="true">

    <jvmarg value="-Xms256m"/>
    <jvmarg value="-Xmx1g"/>
    <jvmarg value="-ea"/>
    <jvmarg value="-Duser.timezone=UTC"/>

    <arg value="--profile"/>
    <arg value="integration"/>
    <arg value="--config"/>
    <arg file="${basedir}/config/test-integration.yml"/>
</java>
```

JVM nhận `-Xms`, `-Xmx`, `-ea` và `-Duser.timezone=UTC`. Lớp main nhận bốn application arguments theo đúng thứ tự: `--profile`, `integration`, `--config` và đường dẫn file cấu hình.

### 4.1. Dùng một `<arg>` cho mỗi phần tử

Nên khai báo từng argument riêng để tránh lỗi phân tích dấu cách và dấu nháy:

```xml
<arg value="--output-dir"/>
<arg value="${test.work.dir}/reports with spaces"/>
```

Đối số thứ hai là một chuỗi duy nhất, kể cả khi đường dẫn có dấu cách. Tránh tự thêm dấu nháy vào giá trị:

```xml
<!-- Không nên: dấu nháy có thể trở thành một phần của argument. -->
<arg value="&quot;${test.work.dir}/reports with spaces&quot;"/>
```

Nếu dùng `line` để truyền một chuỗi nhiều argument, Ant phải phân tích lại chuỗi đó thành từng phần. Với đường dẫn chứa dấu cách hoặc ký tự đặc biệt, `value` hoặc `file` thường dễ kiểm soát hơn.

### 4.2. Truyền tham số dạng file hoặc path

Nested `<arg>` hỗ trợ các cách truyền giá trị khác nhau, trong đó `file` và `path` giúp Ant chuyển đổi đường dẫn theo hệ điều hành:

```xml
<arg file="${basedir}/test-data/input.json"/>
<arg value="${basedir}/test-data"/>
```

Với nhiều thành phần đường dẫn, có thể tạo một Ant Path rồi chuyển thành chuỗi theo quy ước hệ điều hành bằng `<pathconvert>`, sau đó truyền chuỗi đó bằng `<arg value="..."/>`. Không tự nối dấu phân cách classpath của Windows và Unix bằng chuỗi cố định nếu Ant có thể tạo Path cho bạn.

### 4.3. Không nhầm argument của JVM với argument của test

Ví dụ sai về ý nghĩa:

```xml
<java classname="com.example.tests.IntegrationTestLauncher" fork="true">
    <jvmarg value="--profile integration"/>
</java>
```

`--profile integration` ở đây được đưa cho JVM executable, không phải cho chương trình kiểm thử. Nếu đây là tùy chọn của launcher, hãy dùng:

```xml
<arg value="--profile"/>
<arg value="integration"/>
```

Tương tự, `-Xmx1g` là tùy chọn JVM, không phải argument của phương thức `main`.

## 5. Truyền system properties cho test process

System property là cặp tên/giá trị mà mã Java đọc qua `System.getProperty`. Dùng nested `<sysproperty>` để truyền chúng cho tiến trình kiểm thử:

```xml
<java classname="com.example.tests.IntegrationTestLauncher"
      fork="true"
      failonerror="true">
    <sysproperty key="test.profile" value="integration"/>
    <sysproperty key="test.data.dir"
                 value="${basedir}/test-data/integration"/>
    <sysproperty key="user.timezone" value="UTC"/>
</java>
```

Trong Java:

```java
String profile = System.getProperty("test.profile");
String dataDir = System.getProperty("test.data.dir");
```

`<sysproperty>` khác `<jvmarg value="-Dkey=value"/>` ở cách biểu diễn. Cả hai có thể tạo system property cho JVM con; nested `<sysproperty>` thường dễ đọc, nhất là khi giá trị chứa đường dẫn hoặc được lấy từ Ant property.

### 5.1. Truyền property từ dòng lệnh Ant

Có thể đặt giá trị thay đổi theo môi trường bằng `-D`:

```bash
ant -Dtest.profile=staging -Dtest.timeout=120 test-integration
```

Sau đó dùng các property trong build file:

```xml
<sysproperty key="test.profile" value="${test.profile}"/>
<sysproperty key="test.timeout" value="${test.timeout}"/>
```

Hãy khai báo giá trị mặc định nếu target có thể chạy mà không truyền `-D`, hoặc kiểm tra property bắt buộc trước khi gọi test. Ant property có quy tắc first definition wins, nên cần chú ý thứ tự và nguồn khai báo.

## 6. Truyền environment variables cho tiến trình con

Environment variables được đọc qua `System.getenv` hoặc các API hệ điều hành. Dùng nested `<env>` để truyền biến cho tiến trình Java được fork:

```xml
<java classname="com.example.tests.IntegrationTestLauncher"
      fork="true"
      failonerror="true">
    <env key="APP_MODE" value="test"/>
    <env key="LANG" value="en_US.UTF-8"/>
    <env key="TEST_DATA_DIR" value="${basedir}/test-data"/>
</java>
```

Trong Java, có thể đọc:

```java
String mode = System.getenv("APP_MODE");
String dataDir = System.getenv("TEST_DATA_DIR");
```

Environment variable và system property là hai cơ chế khác nhau. `APP_MODE` được đọc bằng `System.getenv("APP_MODE")`; property `test.profile` được đọc bằng `System.getProperty("test.profile")`.

### 6.1. Không vô tình ghi đè `PATH`

Nếu cần thêm thư mục công cụ vào `PATH`, hãy giữ giá trị hiện tại và dùng cách nối đường dẫn phù hợp với hệ điều hành. Tránh thay toàn bộ `PATH` bằng một thư mục duy nhất, vì tiến trình test có thể không tìm được các chương trình hệ thống cần thiết.

Khi có thể, dùng `<env key="..." path="..."/>` cho biến dạng đường dẫn để Ant xử lý dấu phân cách theo nền tảng. Nếu cần giữ giá trị `PATH` hiện có, hãy nạp biến môi trường vào Ant và ghép thêm thư mục theo cách có kiểm soát, hoặc để CI chuẩn bị environment trước khi gọi Ant.

### 6.2. Không truyền secret qua log

Không in token, password hoặc khóa truy cập vào `<echo>`, application arguments hoặc lệnh có thể được ghi lại trong log CI. Nếu test cần secret, cấp qua cơ chế secret của CI hoặc môi trường được bảo vệ, giới hạn quyền truy cập và tránh echo giá trị đó.

## 7. Classpath của tiến trình kiểm thử

JVM có thể khởi động đúng nhưng test vẫn thất bại nếu classpath thiếu test runner, class của ứng dụng hoặc dependency. Với `<java>`, dùng nested `<classpath>`:

```xml
<path id="test.classpath">
    <pathelement location="build/test-classes"/>
    <pathelement location="build/classes"/>
    <fileset dir="lib/test">
        <include name="*.jar"/>
    </fileset>
</path>

<java classname="com.example.tests.IntegrationTestLauncher"
      fork="true"
      failonerror="true">
    <classpath refid="test.classpath"/>
</java>
```

Classpath thường cần test classes, application classes và các thư viện kiểm thử/runtime. Nếu dùng Ivy, có thể tạo Ant Path từ configuration `test` rồi kết hợp với output directories của dự án.

Classpath là đường dẫn tìm lớp; working directory là thư mục hiện tại của tiến trình. Thêm một thư mục vào classpath không làm nó trở thành working directory và đặt `dir` không tự thêm thư mục đó vào classpath.

## 8. Giới hạn thời gian và xử lý mã thoát

Một tiến trình kiểm thử có thể treo do deadlock, chờ mạng hoặc chờ tài nguyên. Thuộc tính `timeout` của `<java fork="true">` giới hạn thời gian chạy theo mili giây.

```xml
<java classname="com.example.tests.IntegrationTestLauncher"
      fork="true"
      timeout="300000"
      failonerror="true">
    <classpath refid="test.classpath"/>
</java>
```

Ví dụ giới hạn năm phút. Chọn timeout dựa trên thời lượng test bình thường và tài nguyên của CI; timeout quá thấp có thể làm test hợp lệ thất bại trên máy chậm.

`failonerror="true"` làm build thất bại nếu chương trình con kết thúc với mã thoát khác 0. Nếu cần tự xử lý mã thoát, có thể đặt `resultproperty` và để `failonerror="false"`:

```xml
<target name="run-integration-tests">
    <java classname="com.example.tests.IntegrationTestLauncher"
          fork="true"
          failonerror="false"
          resultproperty="test.exit.code">
        <classpath refid="test.classpath"/>
    </java>

    <condition property="tests.passed">
        <equals arg1="${test.exit.code}" arg2="0"/>
    </condition>

    <fail unless="tests.passed"
          message="Integration tests failed with exit code ${test.exit.code}."/>
</target>
```

Nếu không cần xử lý riêng mã thoát, dùng `failonerror="true"` đơn giản và dễ hiểu hơn. `resultproperty` hữu ích khi muốn phân biệt nhiều loại kết quả hoặc tạo thông báo lỗi tùy chỉnh.

## 9. Dùng task `<junit>` khi chạy JUnit

Nếu dự án sử dụng JUnit, Ant có task `<junit>` để khám phá và thực thi test theo cấu hình JUnit, đồng thời tạo formatter và báo cáo. Task này khác với việc dùng `<java>` để gọi một lớp launcher tự viết.

Ví dụ:

```xml
<junit fork="true"
       forkmode="once"
       haltonfailure="true"
       printsummary="yes"
       timeout="300000">

    <classpath>
        <pathelement location="build/classes"/>
        <pathelement location="build/test-classes"/>
        <fileset dir="lib/test">
            <include name="*.jar"/>
        </fileset>
    </classpath>

    <jvmarg value="-Xmx1g"/>
    <jvmarg value="-ea"/>
    <sysproperty key="test.profile" value="integration"/>
    <env key="APP_MODE" value="test"/>

    <formatter type="plain" usefile="true"/>
    <batchtest todir="build/test-reports">
        <fileset dir="build/test-classes">
            <include name="**/*Test.class"/>
        </fileset>
    </batchtest>
</junit>
```

Các điểm cần chú ý:

- `fork="true"` chạy test trong JVM con.
- `forkmode` điều khiển cách tái sử dụng JVM giữa các test; `once` dùng một tiến trình cho batch, còn các chế độ khác có thể tạo tiến trình theo test hoặc nhóm test.
- `jvm` có thể chỉ định executable JVM cho tiến trình fork.
- Nested `<jvmarg>`, `<sysproperty>` và `<env>` cấu hình JVM và môi trường test.
- `timeout` đặt giới hạn thời gian cho test process.
- `formatter` và `batchtest` cấu hình đầu ra báo cáo và tập test.

Task `<junit>` có các thuộc tính và nested element riêng theo phiên bản Ant/JUnit. Không nhầm `tempdir` của task với working directory của tiến trình. Khi cần đặt working directory một cách tường minh cho một launcher Java, task `<java fork="true" dir="...">` cung cấp thuộc tính `dir`. Nếu dùng `<junit>`, hãy kiểm tra tài liệu phiên bản đang cài về working directory và cách task khởi chạy fork; có thể dùng đường dẫn fixture tuyệt đối để tránh phụ thuộc vào thư mục hiện tại.

## 10. Ví dụ hoàn chỉnh: chạy test launcher trong JVM riêng

Build file sau kết hợp lựa chọn JVM, working directory, classpath, JVM arguments, application arguments, system properties, environment variables và timeout:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="test-process-demo" default="test-integration" basedir=".">

    <property name="build.dir" location="${basedir}/build"/>
    <property name="test.work.dir" location="${build.dir}/test-work"/>
    <property name="test.report.dir" location="${build.dir}/test-reports"/>
    <property name="test.data.dir" location="${basedir}/test-data/integration"/>

    <!-- CI có thể truyền -Dtest.java=/absolute/path/to/java -->
    <property name="test.java" value="${java.home}/bin/java"/>

    <path id="test.classpath">
        <pathelement location="${build.dir}/test-classes"/>
        <pathelement location="${build.dir}/classes"/>
        <fileset dir="lib/test">
            <include name="*.jar"/>
        </fileset>
    </path>

    <target name="prepare-test-process">
        <mkdir dir="${test.work.dir}"/>
        <mkdir dir="${test.report.dir}"/>
    </target>

    <target name="test-integration" depends="prepare-test-process">
        <java classname="com.example.tests.IntegrationTestLauncher"
              fork="true"
              jvm="${test.java}"
              dir="${test.work.dir}"
              timeout="300000"
              failonerror="true">

            <classpath refid="test.classpath"/>

            <jvmarg value="-Xms256m"/>
            <jvmarg value="-Xmx1g"/>
            <jvmarg value="-ea"/>

            <sysproperty key="test.profile" value="integration"/>
            <sysproperty key="test.data.dir" value="${test.data.dir}"/>
            <sysproperty key="test.report.dir" value="${test.report.dir}"/>

            <env key="APP_MODE" value="test"/>

            <arg value="--suite"/>
            <arg value="integration"/>
            <arg value="--fail-fast"/>
        </java>
    </target>

    <target name="clean">
        <delete dir="${build.dir}" quiet="true"/>
    </target>

</project>
```

Trong môi trường Linux, nếu muốn dùng JDK 17:

```bash
ant -Dtest.java=/opt/jdk-17/bin/java test-integration
```

Trong PowerShell:

```powershell
ant "-Dtest.java=C:\Program Files\Java\jdk-17\bin\java.exe" test-integration
```

Giá trị mặc định `${java.home}/bin/java` phù hợp với nhiều môi trường Unix-like, nhưng trên Windows cần cấu hình đường dẫn `java.exe` phù hợp. Build CI nên truyền `test.java` rõ ràng nếu cần kiểm thử trên JDK khác với JDK đang chạy Ant.

## 11. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Test vẫn chạy bằng JDK của Ant | `fork` chưa bật hoặc `jvm` chưa được chỉ định đúng | Dùng `fork="true"`, đặt `jvm` đến executable Java cần dùng và in thông tin runtime từ test process |
| Không tìm thấy executable Java | Đường dẫn `jvm` sai hoặc không có quyền thực thi | Kiểm tra file `java`/`java.exe`, quyền truy cập và cấu hình JDK |
| Test không tìm thấy fixture | Working directory khác với giả định của test | Đặt `dir` rõ ràng hoặc truyền đường dẫn tuyệt đối qua system property/argument |
| Test nhận thiếu tham số | Dùng nhầm `<jvmarg>` thay cho `<arg>` hoặc ngược lại | Đặt JVM option trong `jvmarg`, application option trong `arg` |
| Đường dẫn có dấu cách bị tách thành nhiều argument | Ghép tham số bằng chuỗi `line` hoặc tự thêm dấu nháy sai | Dùng một `<arg value="..."/>` hoặc `<arg file="..."/>` cho mỗi argument |
| JVM hết bộ nhớ | Heap mặc định không đủ cho test | Tăng `-Xmx` bằng `<jvmarg>` sau khi xem mức tiêu thụ thực tế |
| Test không nhận system property | Đặt biến bằng `<env>` nhưng code đọc `System.getProperty`, hoặc ngược lại | Dùng `<sysproperty>` cho `System.getProperty`; `<env>` cho `System.getenv` |
| Test bị treo làm CI chờ vô hạn | Không đặt timeout hoặc timeout quá dài | Đặt `timeout` phù hợp và điều tra thread dump/log khi hết thời gian |
| Build vẫn thành công dù test trả mã lỗi | Không bật `failonerror` và không kiểm tra `resultproperty` | Dùng `failonerror="true"` hoặc kiểm tra mã thoát tường minh |
| Test phụ thuộc trạng thái của lần chạy trước | Dùng chung working directory hoặc không dọn dữ liệu tạm | Tạo thư mục làm việc riêng, chuẩn bị fixture và cleanup có kiểm soát |
| Máy local chạy được nhưng CI thất bại | JVM, environment, working directory hoặc classpath khác nhau | In thông tin runtime không nhạy cảm, cố định cấu hình và dùng đường dẫn tường minh |

## 12. Nguyên tắc tổ chức test process

Khi thiết kế target kiểm thử, nên tách các nhóm cấu hình để dễ đọc và thay đổi:

- JVM: executable, heap, assertion và system properties của runtime.
- Working directory: thư mục riêng để test đọc/ghi đường dẫn tương đối.
- Application arguments: tham số điều khiển test launcher hoặc suite.
- Environment: biến môi trường mà tiến trình con cần nhận.
- Classpath: test classes, application classes và dependency test/runtime.
- Kết quả: timeout, mã thoát, log và report.

Đặt các giá trị thay đổi theo máy hoặc CI thành Ant property, chẳng hạn `test.java`, `test.work.dir` và `test.data.dir`. Tránh ghi cứng đường dẫn máy cá nhân trong build file. Dùng `location` để tạo đường dẫn tuyệt đối từ `${basedir}` khi cần đường dẫn ổn định.

Không dùng working directory để thay thế classpath, không dùng system property thay cho environment variable nếu ứng dụng đọc một cơ chế cụ thể, và không đặt application argument thành JVM argument. Mỗi cấu hình điều khiển một phần khác nhau của tiến trình.

## 13. Checklist cấu hình tiến trình kiểm thử

- [ ] Đã quyết định test chạy trong JVM Ant hay JVM con.
- [ ] Nếu cần chọn JDK riêng, đã bật `fork="true"` và chỉ định `jvm` chính xác.
- [ ] Đường dẫn `java`/`java.exe` tồn tại và tương thích với ứng dụng.
- [ ] Đã tạo working directory trước khi khởi chạy test process.
- [ ] `dir` trỏ đến thư mục riêng mà build có quyền quản lý.
- [ ] Fixture và report có đường dẫn rõ ràng, không phụ thuộc ngầm vào current directory.
- [ ] JVM options được khai báo bằng `<jvmarg>`.
- [ ] Application arguments được khai báo bằng `<arg>` và giữ đúng ranh giới từng tham số.
- [ ] System properties được truyền bằng `<sysproperty>` khi test đọc `System.getProperty`.
- [ ] Environment variables được truyền bằng `<env>` khi test đọc `System.getenv`.
- [ ] Classpath có test classes, application classes và dependency cần thiết.
- [ ] Đã đặt timeout phù hợp và xác định cách xử lý mã thoát.
- [ ] Log không làm lộ secret hoặc thông tin xác thực.
- [ ] Working directory và dữ liệu tạm được dọn sau khi đã lưu artifact cần thiết.

Khi chọn đúng JVM, đặt working directory rõ ràng và phân biệt JVM arguments với application arguments, tiến trình kiểm thử của Ant sẽ có môi trường chạy nhất quán hơn giữa máy phát triển và CI. Task `<java fork="true">` cung cấp quyền kiểm soát trực tiếp cho một test launcher; task `<junit>` phù hợp khi cần tích hợp quy trình chạy và báo cáo JUnit.

Tài liệu tham khảo: [Apache Ant Manual — Java Task](https://ant.apache.org/manual/Tasks/java.html) và [Apache Ant Manual — JUnit Task](https://ant.apache.org/manual/Tasks/junit.html).
