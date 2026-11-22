# Phân biệt JVM của Ant và JVM ứng dụng với fork

Apache Ant là một ứng dụng Java. Khi chạy `ant build`, chính Ant đang hoạt động bên trong một JVM. Trong buildfile, task `<java>` có thể gọi phương thức `main()` của một lớp Java. Câu hỏi quan trọng là lớp ứng dụng đó chạy ngay trong JVM đang chạy Ant hay được khởi động trong một JVM riêng.

Thuộc tính `fork` của task `<java>` quyết định lựa chọn này. Mặc định `fork="false"`: Ant thực thi lớp Java trong cùng tiến trình JVM với Ant. Khi đặt `fork="true"`, Ant khởi chạy một tiến trình Java con, có JVM riêng cho ứng dụng. Hai chế độ ảnh hưởng đến bộ nhớ, system properties, classpath, tùy chọn JVM, khả năng cô lập lỗi và cách build chờ chương trình kết thúc.

## 1. Hai JVM trong một quy trình build

Khi Ant chạy, có một JVM điều khiển toàn bộ build:

```text
ant build
   |
   v
JVM của Ant
   |
   +-- đọc build.xml
   +-- chạy target
   +-- thực thi task javac, copy, jar, ...
   +-- thực thi task java
```

Task `<java>` có hai cách thực thi lớp ứng dụng:

**Không fork (`fork="false"`)**: mã `main()` được gọi trong tiến trình đang chạy Ant. Không có JVM ứng dụng thứ hai.

```text
Tiến trình Ant
└── JVM của Ant
    ├── Ant runtime và các task
    └── lớp ứng dụng được gọi bởi task <java>
```

**Có fork (`fork="true"`)**: Ant tạo một tiến trình Java con. Tiến trình con có heap, runtime và vòng đời riêng.

```text
Tiến trình Ant                         Tiến trình Java con
└── JVM của Ant  -- khởi chạy ------>  └── JVM ứng dụng
    ├── điều phối build                    └── gọi main()
    └── chờ kết quả (mặc định)                 └── thoát khi hoàn tất
```

Trong cả hai trường hợp, `<java>` vẫn là task do Ant điều khiển. Khác biệt nằm ở ranh giới tiến trình và JVM dùng để chạy lớp ứng dụng.

## 2. Chạy trong JVM của Ant với fork=false

Khi `fork` không được bật, Ant gọi lớp ứng dụng trong JVM hiện tại. Đây là giá trị mặc định, nhưng có thể ghi rõ `fork="false"` để người đọc buildfile hiểu chủ đích:

```xml
<target name="run-in-process" depends="compile">
    <java classname="com.example.app.Main" fork="false">
        <classpath>
            <pathelement location="build/classes" />
            <fileset dir="lib">
                <include name="*.jar" />
            </fileset>
        </classpath>
        <arg value="--profile" />
        <arg value="development" />
    </java>
</target>
```

Task gọi `com.example.app.Main.main()` với hai tham số ứng dụng `--profile` và `development`. Classpath lồng bên trong giúp Ant tìm lớp chính và các lớp mà ứng dụng cần.

Do chạy trong cùng tiến trình, ứng dụng không có heap JVM độc lập. Các trạng thái cấp tiến trình như system properties, default locale, default timezone, luồng, shutdown hooks và một số thiết lập toàn cục có thể ảnh hưởng tới Ant hoặc các task chạy sau đó. Việc nạp lớp có thể dùng classloader riêng của Ant, nhưng classloader riêng không tạo ra ranh giới tiến trình.

Chế độ này phù hợp với chương trình nhỏ, tác vụ kết thúc nhanh và mã ứng dụng được thiết kế để chạy an toàn bên trong JVM của công cụ build. Nó cũng tránh chi phí khởi động một tiến trình Java mới.

### Những giới hạn cần nhớ

- Không thể chọn một executable Java khác cho riêng ứng dụng vì ứng dụng đang dùng JVM đã khởi chạy Ant.
- Không thể cấp một heap riêng bằng `maxmemory` cho ứng dụng.
- Các tùy chọn khởi động JVM như `jvmarg` không có ý nghĩa như khi tạo JVM con.
- Lỗi làm thay đổi trạng thái toàn cục của tiến trình có thể ảnh hưởng đến các task tiếp theo.
- Một ứng dụng chạy vô hạn hoặc giữ các luồng không daemon có thể làm tiến trình Ant không kết thúc như mong đợi.

Đặc biệt, tránh viết chương trình chạy in-process có hành vi kết thúc cả tiến trình như `System.exit()` hoặc thay đổi các thiết lập toàn cục mà không khôi phục. Đây là JVM đang phục vụ cả Ant, không phải một runtime riêng chỉ thuộc ứng dụng.

## 3. Chạy trong JVM riêng với fork=true

Khi bật `fork="true"`, Ant khởi chạy một tiến trình Java mới để thực thi lớp ứng dụng:

```xml
<target name="run-forked" depends="compile">
    <java classname="com.example.app.Main"
          fork="true"
          failonerror="true"
          timeout="60000"
          maxmemory="512m">

        <jvmarg value="-Xms128m" />
        <sysproperty key="app.profile" value="production" />

        <classpath>
            <pathelement location="build/classes" />
            <fileset dir="lib">
                <include name="*.jar" />
            </fileset>
        </classpath>

        <arg value="--port" />
        <arg value="8081" />
    </java>
</target>
```

Trong ví dụ:

- `fork="true"` yêu cầu Ant tạo JVM ứng dụng riêng.
- `maxmemory="512m"` đặt giới hạn heap tối đa cho JVM con.
- `<jvmarg>` truyền tùy chọn khởi động cho executable Java, ở đây đặt heap ban đầu.
- `<sysproperty>` thiết lập system property cho tiến trình ứng dụng.
- `<classpath>` cung cấp lớp đã biên dịch và thư viện cần thiết.
- `<arg>` truyền đối số cho phương thức `main()`.
- `timeout="60000"` đặt thời gian chờ tối đa là 60.000 mili giây cho tiến trình được fork.
- `failonerror="true"` yêu cầu build thất bại nếu chương trình kết thúc với mã thoát khác 0.

Ant thường chờ tiến trình con kết thúc rồi mới tiếp tục target. Sau khi chương trình hoàn tất, Ant có thể xử lý mã thoát và quyết định build tiếp tục hay thất bại theo cấu hình.

## 4. Phân biệt đối số ứng dụng, JVM argument và system property

Trong task `<java>`, các phần tử lồng nhau có ý nghĩa khác nhau. Đặt nhầm giá trị vào sai phần tử là lỗi cấu hình phổ biến.

| Thành phần | Nơi nhận giá trị | Ví dụ |
|---|---|---|
| `<arg>` | Đối số của `main(String[] args)` | `--port`, `8081` |
| `<jvmarg>` | Tùy chọn khởi động JVM con | `-Xms128m`, `-Xmx512m` |
| `<sysproperty>` | System property của ứng dụng | `app.profile=production` |
| `<env>` | Biến môi trường của tiến trình con | `APP_REGION=ap-southeast-1` |
| `<classpath>` | Lớp và thư viện ứng dụng cần nạp | `build/classes`, `lib/*.jar` |

Ví dụ truyền đủ các loại giá trị:

```xml
<java classname="com.example.app.Main" fork="true">
    <jvmarg value="-Xmx768m" />
    <sysproperty key="app.mode" value="batch" />
    <env key="APP_REGION" value="ap-southeast-1" />
    <classpath>
        <pathelement location="build/classes" />
        <pathelement location="lib/application-api.jar" />
    </classpath>
    <arg value="--input" />
    <arg file="data/input.csv" />
</java>
```

Trong lớp Java, có thể đọc dữ liệu theo cách tương ứng:

```java
public class Main {
    public static void main(String[] args) {
        String mode = System.getProperty("app.mode");
        String region = System.getenv("APP_REGION");

        System.out.println("Mode: " + mode);
        System.out.println("Region: " + region);
        System.out.println("First argument: " + args[0]);
    }
}
```

`System.getProperty()` đọc system property được truyền bằng `<sysproperty>`; `System.getenv()` đọc biến môi trường được truyền bằng `<env>`; còn `args` nhận các giá trị từ `<arg>`. Những giá trị này không thể thay thế lẫn nhau.

## 5. Classpath trong hai chế độ

Ứng dụng cần classpath để tìm lớp chính và các dependency. Task `<java>` cho phép khai báo classpath bằng thuộc tính `classpath`, `classpathref` hoặc nested element `<classpath>`.

Khi `fork="false"`, Ant sử dụng cơ chế classloader trong tiến trình hiện tại để nạp lớp ứng dụng và các lớp phụ thuộc. Khi `fork="true"`, classpath được truyền cho tiến trình Java con. Trong cả hai chế độ, classpath phải chứa lớp chính và các thư viện mà chương trình cần.

Ví dụ dùng một Path có thể tái sử dụng:

```xml
<path id="application.classpath">
    <pathelement location="build/classes" />
    <fileset dir="lib">
        <include name="*.jar" />
    </fileset>
</path>

<target name="run-in-process">
    <java classname="com.example.app.Main"
          classpathref="application.classpath">
    </java>
</target>

<target name="run-forked">
    <java classname="com.example.app.Main"
          fork="true"
          classpathref="application.classpath"
          failonerror="true" />
</target>
```

Việc dùng chung Path giúp hai target sử dụng cùng một tập thư viện, trong khi vẫn có thể chọn ranh giới JVM theo nhu cầu. Nếu ứng dụng cần dependency khác với Ant hoặc thư viện task của Ant, nên khai báo rõ classpath ứng dụng thay vì dựa vào classpath nội bộ của công cụ build.

## 6. Chọn executable và cấu hình JVM con

Khi fork, có thể chỉ định executable Java bằng thuộc tính `jvm`. Nếu không chỉ định, Ant sử dụng Java executable phù hợp với runtime đang chạy Ant theo cơ chế mặc định của nó.

```xml
<property environment="env" />

<target name="run-with-selected-jvm">
    <java classname="com.example.app.Main"
          fork="true"
          jvm="${env.JAVA_HOME}/bin/java"
          maxmemory="1g"
          failonerror="true">
        <jvmarg value="-Xms256m" />
        <classpath location="build/classes" />
    </java>
</target>
```

Đường dẫn executable trong ví dụ minh họa môi trường Unix-like. Trên Windows, Java executable thường là `java.exe` trong thư mục `bin`; nên cấu hình đường dẫn phù hợp với hệ điều hành hoặc dùng mặc định khi không cần chọn runtime riêng.

Một số thuộc tính và phần tử có ý nghĩa khi tạo tiến trình mới:

| Cấu hình | Mục đích |
|---|---|
| `jvm` | Chọn executable Java được gọi |
| `maxmemory` | Đặt giới hạn heap tối đa |
| `<jvmarg>` | Truyền tùy chọn JVM như heap, GC hoặc system property dạng JVM option |
| `clonevm` | Yêu cầu JVM con kế thừa các thiết lập VM phù hợp từ JVM đang chạy Ant |
| `timeout` | Giới hạn thời gian chờ tiến trình con |
| `newenvironment` và `<env>` | Kiểm soát môi trường biến của tiến trình con |

`clonevm` không có nghĩa là chia sẻ cùng một heap hay biến static với Ant. Nó sao chép một số thiết lập khởi chạy sang JVM mới; tiến trình con vẫn có bộ nhớ và vòng đời độc lập. Khi cần kiểm soát rõ ràng, khai báo trực tiếp các `jvmarg`, `sysproperty` và biến môi trường cần thiết.

## 7. System properties và trạng thái toàn cục

System properties là các cặp khóa-giá trị trong đối tượng `System`, ví dụ `user.timezone`, `file.encoding` hoặc property do ứng dụng tự định nghĩa.

Khi ứng dụng chạy in-process, nó dùng cùng tiến trình JVM với Ant. Những thay đổi vào trạng thái toàn cục của JVM có thể tác động đến các task khác chạy sau đó. Khi ứng dụng chạy forked, các system properties của tiến trình con tách biệt với tiến trình Ant; thay đổi trong JVM con không làm thay đổi trực tiếp `System.getProperties()` của JVM cha.

Ví dụ đặt property riêng cho ứng dụng forked:

```xml
<java classname="com.example.app.Main" fork="true">
    <sysproperty key="app.config" value="config/production.yml" />
    <sysproperty key="user.timezone" value="UTC" />
    <classpath location="build/classes" />
</java>
```

Điều này giúp ứng dụng chạy với cấu hình timezone riêng mà không cần thay đổi timezone mặc định của tiến trình Ant. Tuy nhiên, process isolation không cô lập các tài nguyên bên ngoài như file, database, socket hoặc dịch vụ mạng; hai tiến trình vẫn có thể cùng truy cập và thay đổi chúng.

## 8. Mã thoát, timeout và vòng đời tiến trình

Khi fork, task `<java>` có thể quan sát việc chương trình kết thúc và mã thoát của tiến trình con. `failonerror="true"` yêu cầu Ant đánh dấu build thất bại nếu ứng dụng trả về mã thoát khác 0.

```xml
<java classname="com.example.batch.ImportMain"
      fork="true"
      failonerror="true"
      timeout="300000">
    <classpath location="build/classes" />
    <arg value="data/import.csv" />
</java>
```

Ở đây Ant chờ tối đa 300.000 mili giây (5 phút). Nếu chương trình không kết thúc trong khoảng thời gian đó, task xử lý timeout theo cơ chế của Ant và build không thể coi bước chạy là thành công bình thường.

Nếu cần ghi lại mã thoát để xử lý tiếp, task hỗ trợ thuộc tính `resultproperty` trong những chế độ thực thi phù hợp:

```xml
<target name="run-check">
    <java classname="com.example.batch.CheckMain"
          fork="true"
          failonerror="false"
          resultproperty="check.exit.code">
        <classpath location="build/classes" />
    </java>
</target>

<target name="inspect-result" depends="run-check">
    <echo message="Application exit code: ${check.exit.code}" />
</target>
```

Khi dùng `resultproperty`, hãy thiết kế target dựa trên mã thoát và kiểm tra trường hợp property chưa được thiết lập. Nếu muốn build dừng ngay khi chương trình trả về lỗi, `failonerror="true"` thường rõ ràng hơn.

## 9. Khi nào chọn fork=false và fork=true?

Việc chọn chế độ phụ thuộc vào mức độ độc lập mà chương trình cần so với Ant.

| Tiêu chí | `fork="false"` | `fork="true"` |
|---|---|---|
| JVM thực thi | JVM đang chạy Ant | JVM mới của tiến trình con |
| Heap | Dùng chung heap với Ant | Heap riêng, có thể cấu hình `maxmemory` |
| System properties | Cùng phạm vi tiến trình | Riêng tiến trình con |
| JVM executable | Không chọn riêng | Có thể chỉ định bằng `jvm` |
| JVM arguments | Không khởi động JVM mới | Có thể truyền bằng `<jvmarg>` |
| Cách ly lỗi và trạng thái runtime | Thấp hơn, có thể ảnh hưởng Ant | Tốt hơn ở cấp tiến trình |
| Chi phí khởi chạy | Thấp hơn | Có chi phí tạo tiến trình/JVM |
| Phù hợp với | Công việc nhỏ, nhanh, an toàn trong JVM hiện tại | Ứng dụng cần runtime, bộ nhớ hoặc trạng thái độc lập |

Nên cân nhắc `fork="true"` khi:

- Ứng dụng cần heap riêng hoặc tùy chọn GC riêng.
- Cần chạy bằng một JDK/JRE khác với JVM của Ant.
- Chương trình thay đổi system properties, locale, timezone hoặc trạng thái toàn cục.
- Muốn kiểm soát mã thoát và timeout của một tiến trình ứng dụng.
- Ứng dụng có vòng đời hoặc dependency dễ xung đột với runtime Ant.

`fork="false"` phù hợp khi chương trình là tác vụ ngắn, không thay đổi trạng thái toàn cục và không cần JVM option riêng. Không nên bật fork chỉ theo thói quen nếu không cần ranh giới tiến trình, vì việc tạo JVM mới có chi phí thời gian và tài nguyên.

## 10. Ví dụ buildfile với hai chế độ chạy

Một dự án có thể định nghĩa hai target chạy cùng lớp chính theo hai chế độ. Target đầu chạy trong JVM của Ant; target thứ hai chạy trong tiến trình riêng:

```xml
<project name="java-fork-example" default="run-forked">

    <property name="classes.dir" value="build/classes" />

    <path id="app.classpath">
        <pathelement location="${classes.dir}" />
        <fileset dir="lib">
            <include name="*.jar" />
        </fileset>
    </path>

    <target name="compile">
        <mkdir dir="${classes.dir}" />
        <javac srcdir="src"
               destdir="${classes.dir}"
               encoding="UTF-8"
               includeantruntime="false" />
    </target>

    <target name="run-in-process" depends="compile">
        <java classname="com.example.app.Main"
              classpathref="app.classpath"
              fork="false">
            <arg value="--mode" />
            <arg value="local" />
        </java>
    </target>

    <target name="run-forked" depends="compile">
        <java classname="com.example.app.Main"
              classpathref="app.classpath"
              fork="true"
              maxmemory="512m"
              timeout="120000"
              failonerror="true">
            <jvmarg value="-Xms128m" />
            <sysproperty key="app.mode" value="isolated" />
            <arg value="--mode" />
            <arg value="batch" />
        </java>
    </target>

</project>
```

Cách gọi:

```shell
# Chạy lớp trong JVM của Ant
ant run-in-process

# Chạy lớp trong JVM riêng
ant run-forked
```

Hai target dùng cùng classpath và cùng lớp chính, nhưng truyền tham số và thiết lập runtime khác nhau. Đây là cách hữu ích để so sánh hành vi của ứng dụng khi chạy trong cùng tiến trình và khi chạy độc lập.

## 11. Lỗi thường gặp khi dùng fork

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Ứng dụng không nhận được `-Xmx` | Đang chạy với `fork="false"`; không có JVM mới để nhận JVM argument | Bật `fork="true"` rồi đặt `maxmemory` hoặc `<jvmarg>` |
| Không tìm thấy lớp chính trong JVM con | Classpath không được khai báo hoặc đường dẫn không đúng | Kiểm tra `classpath`, `classpathref` và vị trí class output |
| Ứng dụng chạy bằng JDK khác với dự kiến | Ant đang dùng executable mặc định | Chỉ định `jvm` tới Java executable cần dùng khi fork |
| Thay đổi system property ảnh hưởng task sau | Ứng dụng chạy in-process trong JVM của Ant | Dùng fork để cô lập system properties hoặc khôi phục trạng thái sau khi chạy |
| Build vẫn tiếp tục dù ứng dụng trả mã lỗi | `failonerror` đang tắt hoặc mã thoát được xử lý qua `resultproperty` | Bật `failonerror="true"` hoặc kiểm tra mã thoát rõ ràng |
| Task chờ mãi không kết thúc | Ứng dụng không thoát hoặc có luồng giữ tiến trình sống | Dùng `timeout` khi fork và kiểm tra vòng đời luồng của ứng dụng |
| Ứng dụng cần biến môi trường nhưng không thấy | Chưa khai báo `<env>` hoặc tiến trình con được cấu hình môi trường riêng | Kiểm tra `newenvironment` và khai báo các biến cần thiết |
| Dùng fork nhưng kỳ vọng cô lập file hoặc database | Fork chỉ tạo ranh giới tiến trình/JVM | Quản lý riêng tài nguyên bên ngoài như file, cổng, database và dữ liệu dùng chung |

Khi debug, hãy xác định trước ứng dụng đang chạy in-process hay forked. Sau đó kiểm tra executable, classpath, JVM arguments, system properties, biến môi trường và mã thoát. Việc phân biệt rõ hai JVM giúp tránh tìm lỗi ở classpath khi nguyên nhân thực tế là tùy chọn JVM không được áp dụng.

## 12. Quy trình chọn và cấu hình fork

Khi thêm task `<java>` vào buildfile, có thể tiến hành theo trình tự sau:

1. Xác định ứng dụng có cần JVM riêng, heap riêng hoặc tùy chọn JVM riêng hay không.
2. Nếu không cần, dùng `fork="false"` hoặc giữ mặc định và bảo đảm ứng dụng không can thiệp trạng thái toàn cục của Ant.
3. Nếu cần cô lập tiến trình, đặt `fork="true"` và chọn executable qua `jvm` nếu runtime mặc định không phù hợp.
4. Khai báo classpath ứng dụng rõ ràng, độc lập với classpath nội bộ của Ant.
5. Đặt JVM option bằng `<jvmarg>`, system property bằng `<sysproperty>`, biến môi trường bằng `<env>` và đối số `main()` bằng `<arg>`.
6. Với tiến trình forked, đặt timeout và chính sách mã thoát phù hợp với yêu cầu build.
7. Chạy thử cả trường hợp thành công và thất bại để xác nhận Ant xử lý vòng đời ứng dụng đúng như mong đợi.

`fork` xác định ứng dụng có dùng chung JVM với Ant hay chạy trong một JVM riêng. Khi chạy in-process, ứng dụng dùng chung trạng thái cấp tiến trình với công cụ build; khi fork, ứng dụng có heap, system properties và vòng đời riêng. Chọn đúng chế độ giúp build kiểm soát tài nguyên, cấu hình runtime và lỗi thực thi rõ ràng hơn.
