# Truyền system property, biến môi trường và thư mục làm việc

Khi Apache Ant chạy một chương trình Java, build file thường cần truyền cấu hình vào JVM, cung cấp biến môi trường và chọn thư mục mà chương trình xem là thư mục hiện hành. Ba việc này liên quan đến ba cơ chế khác nhau: Java system property, operating-system environment variable và working directory.

Trong Ant, cách cấu hình phụ thuộc vào việc dùng task `<java>` để chạy lớp Java hay dùng `<exec>` để gọi lệnh `java` như một chương trình bên ngoài. Hiểu đúng ranh giới này giúp tránh trường hợp build file đã khai báo property nhưng ứng dụng không đọc được, hoặc đường dẫn tương đối trỏ đến sai nơi.

## 1. Phân biệt ba loại cấu hình

Trước khi viết task, hãy xác định giá trị cần truyền thuộc loại nào:

| Loại | Mục đích | Cách ứng dụng Java đọc |
|---|---|---|
| Ant property | Giá trị cấu hình được dùng trong build file, ví dụ `${app.profile}` | Không tự xuất hiện trong ứng dụng; phải chuyển tiếp rõ ràng |
| Java system property | Cấu hình thuộc JVM, ví dụ `app.profile=development` | `System.getProperty("app.profile")` |
| Environment variable | Cấu hình thuộc môi trường của tiến trình, ví dụ `APP_PROFILE` | `System.getenv("APP_PROFILE")` |
| Working directory | Thư mục hiện hành của tiến trình, dùng để phân giải đường dẫn tương đối | `Path.of(".").toAbsolutePath()` hoặc `user.dir` để quan sát |

Ant property và Java system property có tên gọi gần giống nhau nhưng không phải cùng một kho dữ liệu. Ví dụ, khai báo:

```xml
<property name="app.profile" value="development"/>
```

chỉ giúp Ant thay thế `${app.profile}` trong build file. Ứng dụng Java không tự nhìn thấy property đó. Muốn ứng dụng đọc được bằng `System.getProperty`, phải truyền nó vào JVM bằng `<sysproperty>` hoặc tham số `-D`.

Tương tự, environment variable không tự trở thành Java system property. Ứng dụng phải đọc đúng API `System.getenv`. Working directory lại là trạng thái của tiến trình ở cấp hệ điều hành, không phải một loại property có thể thay thế tùy ý.

## 2. Truyền Java system property bằng `<sysproperty>`

Khi dùng task `<java>`, phần tử lồng `<sysproperty>` truyền một cặp key/value vào JVM chạy chương trình. `key` là tên system property; `value` là giá trị được Ant thay thế từ build file.

```xml
<project name="run-with-system-properties" default="run">
    <property name="app.profile" value="development"/>
    <property name="app.config" location="${basedir}/config/app.properties"/>

    <target name="run">
        <java classname="com.example.Main"
              fork="true"
              failonerror="true">
            <classpath>
                <pathelement location="${basedir}/build/classes"/>
                <pathelement location="${basedir}/lib/application.jar"/>
            </classpath>

            <sysproperty key="app.profile" value="${app.profile}"/>
            <sysproperty key="app.config" value="${app.config}"/>
        </java>
    </target>
</project>
```

Trong ví dụ này, Ant thay `${app.profile}` và `${app.config}` trước khi khởi chạy chương trình. JVM con nhận được hai system property tương ứng. Ứng dụng đọc chúng như sau:

```java
public class Main {
    public static void main(String[] args) {
        String profile = System.getProperty("app.profile");
        String configFile = System.getProperty("app.config");

        System.out.println("Profile: " + profile);
        System.out.println("Config: " + configFile);
    }
}
```

Nếu property không được truyền vào JVM và cũng không có giá trị mặc định trong ứng dụng, `System.getProperty("app.profile")` trả về `null`. Có thể chỉ định giá trị mặc định ngay khi đọc:

```java
String profile = System.getProperty("app.profile", "local");
```

`fork="true"` tạo JVM riêng để chạy chương trình. Đây là lựa chọn phù hợp khi cần môi trường chạy tách biệt, truyền environment variable hoặc đặt working directory cho tiến trình Java. Task `<java>` mặc định chạy không fork; khi không fork, mã Java chạy trong JVM của Ant nên không có một tiến trình con riêng để cô lập cấu hình.

### Truyền nhiều property

Có thể khai báo nhiều `<sysproperty>` trong cùng một task. Mỗi phần tử tương ứng với một cặp tên và giá trị:

```xml
<java classname="com.example.Main" fork="true" failonerror="true">
    <sysproperty key="app.profile" value="${app.profile}"/>
    <sysproperty key="app.region" value="ap-southeast-1"/>
    <sysproperty key="app.feature.audit" value="true"/>
</java>
```

Các property này được truy cập riêng qua `System.getProperty`. Chúng không làm thay đổi các Ant property ban đầu và cũng không tự ghi ngược giá trị từ ứng dụng về build file.

## 3. Truyền environment variable bằng `<env>`

Environment variable thuộc môi trường của tiến trình. Trong task `<java>` chạy forked JVM, dùng phần tử lồng `<env>` để đặt biến mà chương trình con sẽ nhận được.

```xml
<project name="run-with-environment" default="run">
    <property name="app.profile" value="development"/>
    <property name="runtime.home" location="${basedir}/runtime"/>

    <target name="run">
        <java classname="com.example.Main"
              fork="true"
              failonerror="true">
            <classpath>
                <pathelement location="${basedir}/build/classes"/>
            </classpath>

            <env key="APP_PROFILE" value="${app.profile}"/>
            <env key="APP_HOME" value="${runtime.home}"/>
        </java>
    </target>
</project>
```

Ứng dụng Java đọc các biến này bằng `System.getenv`:

```java
String profile = System.getenv("APP_PROFILE");
String appHome = System.getenv("APP_HOME");
```

Nếu biến không tồn tại trong môi trường tiến trình, `System.getenv("APP_PROFILE")` trả về `null`. Tên environment variable thường được viết hoa và phân tách từ bằng dấu gạch dưới, nhưng tên biến và cách phân biệt chữ hoa/chữ thường phụ thuộc hệ điều hành.

### Đọc environment variable có sẵn trên máy chạy Ant

Nếu build file cần đọc biến môi trường hiện có để tạo cấu hình, có thể nhập chúng thành Ant property bằng thuộc tính `environment` của task `<property>`:

```xml
<property environment="env"/>

<target name="show-path">
    <echo message="PATH của máy chạy Ant: ${env.PATH}"/>
</target>
```

Với prefix `env`, Ant tạo các property như `${env.PATH}` hoặc `${env.HOME}` từ môi trường hiện tại. Việc nhập này chỉ giúp build file đọc được giá trị. Nếu muốn chuyển một giá trị sang tiến trình Java con, vẫn phải khai báo `<env>` trong task:

```xml
<property environment="env"/>

<java classname="com.example.Main" fork="true">
    <env key="ORIGINAL_PATH" value="${env.PATH}"/>
</java>
```

Không nhầm `<property environment="env"/>` với `<env .../>`: phần tử thứ nhất đọc môi trường của tiến trình Ant vào build property; phần tử thứ hai thiết lập môi trường cho tiến trình được task khởi chạy.

## 4. Đặt working directory bằng `dir`

Working directory là thư mục hiện hành của tiến trình. Khi ứng dụng mở một file bằng đường dẫn tương đối, đường dẫn đó được phân giải dựa trên working directory của tiến trình, không tự động dựa trên vị trí của file `build.xml`.

Với task `<java>`, đặt thuộc tính `dir` để chọn thư mục chạy cho JVM được fork:

```xml
<project name="run-from-runtime-directory" default="run">
    <property name="runtime.dir" location="${basedir}/runtime"/>

    <target name="run">
        <mkdir dir="${runtime.dir}"/>

        <java classname="com.example.Main"
              fork="true"
              failonerror="true"
              dir="${runtime.dir}">
            <classpath>
                <pathelement location="${basedir}/build/classes"/>
            </classpath>
        </java>
    </target>
</project>
```

Giả sử ứng dụng chạy đoạn mã:

```java
Path config = Path.of("config", "app.properties");
System.out.println(config.toAbsolutePath());
```

Với working directory là `${basedir}/runtime`, đường dẫn tương đối `config/app.properties` được hiểu là file bên dưới thư mục `runtime`. Nếu muốn tham chiếu file theo vị trí dự án, hãy truyền đường dẫn tuyệt đối bằng một property như `${basedir}` hoặc `${app.config}` thay vì phụ thuộc vào thư mục hiện hành.

### `dir` và `${basedir}` giải quyết hai việc khác nhau

- `${basedir}` là Ant property đại diện cho thư mục cơ sở của project build. Dùng nó để tạo đường dẫn ổn định tới file trong dự án.
- `dir` trên task chạy tiến trình con đặt working directory của tiến trình đó. Nó ảnh hưởng đến cách tiến trình con phân giải đường dẫn tương đối.

Ví dụ, dù task Java chạy từ thư mục `runtime`, Ant vẫn có thể dùng `${basedir}/config/app.properties` để tham chiếu file cấu hình tại thư mục gốc dự án. Đặt `dir` không thay đổi `basedir` của project Ant và cũng không đổi thư mục hiện hành của tiến trình Ant đang chạy build.

`dir` có ý nghĩa khi task chạy forked process. Nếu `<java>` chạy không fork, mã ứng dụng dùng chung JVM với Ant và không thể có working directory riêng được thiết lập bởi task. Hãy dùng `fork="true"` nếu ứng dụng cần một thư mục làm việc độc lập.

## 5. Kết hợp system property, environment variable và working directory

Trong thực tế, một ứng dụng có thể dùng system property để chọn profile, environment variable để xác định thư mục dữ liệu và working directory để đọc file tương đối. Có thể cấu hình cả ba trong một task:

```xml
<project name="configured-java-application" default="run">
    <property name="app.profile" value="development"/>
    <property name="runtime.dir" location="${basedir}/runtime"/>
    <property name="app.config" location="${basedir}/config/app.properties"/>

    <target name="run">
        <mkdir dir="${runtime.dir}"/>

        <java classname="com.example.Main"
              fork="true"
              failonerror="true"
              dir="${runtime.dir}">
            <classpath>
                <pathelement location="${basedir}/build/classes"/>
                <pathelement location="${basedir}/lib/application.jar"/>
            </classpath>

            <!-- Cấu hình thuộc JVM. -->
            <sysproperty key="app.profile" value="${app.profile}"/>
            <sysproperty key="app.config" value="${app.config}"/>

            <!-- Cấu hình thuộc môi trường tiến trình. -->
            <env key="APP_PROFILE" value="${app.profile}"/>
            <env key="APP_DATA_DIR" value="${runtime.dir}/data"/>

            <arg value="--check-configuration"/>
        </java>
    </target>
</project>
```

Trong ứng dụng:

```java
String profileProperty = System.getProperty("app.profile");
String configProperty = System.getProperty("app.config");

String profileEnvironment = System.getenv("APP_PROFILE");
String dataDirectory = System.getenv("APP_DATA_DIR");

Path relativeLog = Path.of("logs", "application.log");
Path absoluteLog = relativeLog.toAbsolutePath();
```

Ở ví dụ này, `app.profile` và `app.config` là system property; `APP_PROFILE` và `APP_DATA_DIR` là environment variable; còn `relativeLog` được phân giải từ working directory `${basedir}/runtime`. Việc truyền cùng một profile qua cả system property lẫn environment variable chỉ cần thiết nếu ứng dụng hoặc thư viện sử dụng cả hai cơ chế. Nếu ứng dụng chỉ đọc một loại, chỉ cấu hình loại đó để tránh có hai nguồn giá trị dễ lệch nhau.

## 6. Khi gọi Java thông qua task `<exec>`

Task `<exec>` chạy một chương trình bên ngoài. Nếu executable là `java`, Ant không xử lý lệnh này như task `<java>`. Vì vậy, system property phải được truyền dưới dạng đối số JVM `-Dkey=value`, environment variable dùng phần tử `<env>`, còn working directory dùng thuộc tính `dir` của `<exec>`.

```xml
<project name="execute-java-command" default="run">
    <property name="runtime.dir" location="${basedir}/runtime"/>
    <property name="app.profile" value="development"/>

    <target name="run">
        <mkdir dir="${runtime.dir}"/>

        <exec executable="java"
              dir="${runtime.dir}"
              failonerror="true">
            <!-- Các đối số JVM phải đứng trước tên class hoặc -jar. -->
            <arg value="-Dapp.profile=${app.profile}"/>
            <arg value="-Dapp.config=${basedir}/config/app.properties"/>
            <arg value="-cp"/>
            <arg path="${basedir}/build/classes"/>
            <arg value="com.example.Main"/>
            <arg value="--check-configuration"/>

            <env key="APP_PROFILE" value="${app.profile}"/>
        </exec>
    </target>
</project>
```

Nếu chạy file JAR, thứ tự lệnh tương ứng là `java -Dapp.profile=development -jar application.jar`. Các tùy chọn `-D` phải nằm trước `-jar` hoặc tên lớp chính; đặt chúng sau tên lớp sẽ biến chúng thành tham số của ứng dụng, không còn là tùy chọn JVM.

| Nhu cầu | Task `<java>` | Task `<exec>` gọi `java` |
|---|---|---|
| System property | `<sysproperty key="..." value="..."/>` | `<arg value="-Dkey=value"/>` |
| Environment variable | `<env key="..." value="..."/>` | `<env key="..." value="..."/>` |
| Working directory | `dir="..."` | `dir="..."` |
| Tham số ứng dụng | `<arg value="..."/>` | `<arg value="..."/>` |
| Báo build thất bại khi chương trình trả mã lỗi | `failonerror="true"` | `failonerror="true"` |

Hãy chọn `<java>` khi mục đích chính là chạy một Java class hoặc JAR và muốn Ant cung cấp cấu hình JVM trực tiếp. Dùng `<exec>` khi cần gọi một executable bên ngoài theo cách tổng quát, hoặc muốn mô tả đầy đủ command line như khi chạy từ terminal.

## 7. Quan sát giá trị trong ứng dụng và chẩn đoán lỗi

Khi ứng dụng đọc sai cấu hình, hãy in riêng từng nguồn để biết giá trị được truyền tới đâu:

```java
System.out.println("app.profile property = "
        + System.getProperty("app.profile"));
System.out.println("APP_PROFILE environment = "
        + System.getenv("APP_PROFILE"));
System.out.println("user.dir = " + System.getProperty("user.dir"));
System.out.println("current path = " + Path.of(".").toAbsolutePath());
```

Một số lỗi thường gặp:

1. **Khai báo Ant property nhưng ứng dụng nhận `null`.** Ant property chỉ được dùng trong build file. Hãy truyền nó qua `<sysproperty>` hoặc `<env>` tùy API mà ứng dụng đọc.
2. **Dùng `System.getProperty` để đọc environment variable.** Dùng `System.getenv("NAME")` cho biến môi trường; dùng `System.getProperty("name")` cho Java system property.
3. **Đặt `<env>` nhưng không fork JVM.** Environment variable thuộc môi trường tiến trình. Hãy dùng `fork="true"` khi chạy bằng `<java>` và cần thiết lập môi trường cho tiến trình Java con.
4. **Đặt `dir` nhưng đường dẫn vẫn không đổi.** Kiểm tra task có chạy fork hay không, và kiểm tra chính xác tiến trình nào đang thực hiện thao tác file. `dir` của task con không thay đổi thư mục hiện hành của Ant.
5. **Dùng đường dẫn tương đối với giả định sai.** Đường dẫn tương đối được phân giải theo working directory của tiến trình. Dùng `${basedir}` hoặc property được tạo bằng `location` khi cần đường dẫn ổn định trong dự án.
6. **Cố đổi working directory bằng `-Duser.dir`.** `user.dir` là system property thường phản ánh thư mục làm việc khi JVM khởi động; đặt giá trị này không phải cách đáng tin cậy để đổi working directory ở cấp hệ điều hành. Hãy dùng `dir` trên task tạo tiến trình.
7. **Đặt `-D` sai vị trí khi dùng `<exec>`.** Các tùy chọn JVM phải đứng trước tên class hoặc `-jar`. Sau tên class, chúng được chuyển thành tham số ứng dụng.
8. **Thư mục làm việc chưa tồn tại.** Thuộc tính `dir` chọn thư mục cho tiến trình; nó không thay thế bước tạo thư mục. Dùng `<mkdir>` trước khi chạy nếu build cần tạo thư mục đó.

## 8. Quy trình lựa chọn

Khi cấu hình một lần chạy Java, có thể đi theo trình tự sau:

1. Xác định ứng dụng đọc giá trị bằng `System.getProperty` hay `System.getenv`.
2. Khai báo giá trị nguồn trong Ant property nếu cần tái sử dụng trong build file.
3. Chọn `<java>` hoặc `<exec>` theo cách chạy chương trình; truyền system property bằng `<sysproperty>` hoặc `-D` tương ứng.
4. Truyền environment variable bằng `<env>` nếu ứng dụng cần đọc từ môi trường tiến trình.
5. Chọn working directory bằng `dir` khi ứng dụng dùng đường dẫn tương đối; dùng `${basedir}` hoặc `location` cho các file cần tham chiếu ổn định.
6. Dùng `fork="true"` với `<java>` khi cần tiến trình JVM riêng, environment variable riêng hoặc working directory riêng.
7. In các giá trị quan sát được từ ứng dụng trong lúc chẩn đoán để xác nhận từng cơ chế đã nhận đúng dữ liệu.

## Tài liệu tham khảo

- [Apache Ant Manual — Java Task](https://ant.apache.org/manual/Tasks/java.html): thuộc tính `fork`, `dir`, phần tử `sysproperty`, `env`, `arg` và cách chạy Java class/JAR.
- [Apache Ant Manual — Exec Task](https://ant.apache.org/manual/Tasks/exec.html): cách gọi chương trình ngoài, thiết lập working directory và environment variable.
- [Apache Ant Manual — Properties](https://ant.apache.org/manual/properties.html): Ant property và cách nhập environment variable bằng thuộc tính `environment`.
- [Java API — System](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html): `getProperty`, `getenv` và thông tin hệ thống của JVM.
