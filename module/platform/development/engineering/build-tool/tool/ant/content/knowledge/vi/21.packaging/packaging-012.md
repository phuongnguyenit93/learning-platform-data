# Kiểm tra sản phẩm đóng gói bằng một lần chạy thử độc lập

Sau khi Ant tạo JAR hoặc thư mục phân phối, cần kiểm tra chính sản phẩm đã đóng gói bằng cách chạy nó trong một tiến trình riêng. Mục tiêu là xác nhận artifact có thể khởi động và thực hiện được một chức năng đại diện khi được sử dụng theo cách gần với người dùng hoặc môi trường triển khai.

Một lần chạy thử độc lập khác với việc chạy test trên các lớp trong `build/classes`. Nó phải sử dụng JAR hoặc distribution đã tạo, cùng manifest và runtime dependency được phân phối. Nên chạy trong một working directory riêng, với dữ liệu đầu vào thử nghiệm được chuẩn bị rõ ràng, rồi kiểm tra exit code và kết quả đầu ra.

Luồng cơ bản:

~~~text
Compile + process resources
             |
             v
      Package JAR/distribution
             |
             v
       Chuẩn bị test workspace
             |
             v
  Khởi chạy artifact trong JVM riêng
             |
             v
  Ghi nhận exit code / stdout / stderr
             |
             v
  Kiểm tra kết quả chức năng đại diện
             |
       +-----+-----+
       |           |
      Đạt        Không đạt
       |           |
       v           v
  Cho phép bước  Dừng pipeline và giữ report
  tiếp theo
~~~

## 1. Vì sao cần chạy thử artifact đã đóng gói?

Unit test thường chạy trên classpath do build tạo ra. Chúng rất hữu ích để kiểm tra từng lớp và logic nội bộ, nhưng không tự chứng minh rằng JAR cuối cùng có đầy đủ nội dung và có thể chạy độc lập.

Một lần chạy thử sau đóng gói có thể phát hiện các lỗi mà unit test chưa bao phủ:

- Manifest thiếu `Main-Class` hoặc khai báo sai tên lớp.
- Resource không được đưa vào JAR hoặc nằm sai đường dẫn.
- Dependency runtime không được copy vào distribution.
- Manifest `Class-Path` tham chiếu sai tên hoặc sai vị trí JAR.
- Ứng dụng vô tình phụ thuộc vào file có trên máy phát triển nhưng không nằm trong artifact.
- Code sử dụng đường dẫn tương đối theo working directory nhưng hoạt động sai khi chạy từ thư mục khác.
- Bytecode hoặc thư viện không tương thích với JDK mục tiêu.
- Cấu hình khởi động, tham số dòng lệnh hoặc quyền truy cập file chưa đúng.

Vì vậy, một lần chạy thử độc lập là smoke test ở cấp artifact: nó kiểm tra đường đi tối thiểu từ file phân phối tới một kết quả có thể quan sát.

## 2. Thế nào là một lần chạy thử độc lập?

Một lần chạy thử có tính độc lập nên đáp ứng các điều kiện sau:

1. Artifact đã được tạo bởi target package.
2. Tiến trình kiểm thử chạy riêng, không dùng chung JVM với Ant.
3. Lệnh chạy trỏ tới JAR hoặc thư mục phân phối thực tế.
4. Runtime classpath đến từ artifact và dependency được phân phối, không lấy ngầm từ `build/classes`.
5. Working directory được chỉ định rõ và tách khỏi thư mục source.
6. Input thử nghiệm được chuẩn bị riêng, có kết quả mong đợi cụ thể.
7. Ant ghi nhận exit code, stdout/stderr và kiểm tra output.
8. Nếu kiểm tra không đạt, target smoke test làm build thất bại.

Ví dụ, với executable JAR, lệnh chạy nên tương đương:

~~~bash
java -jar dist/application.jar --input input.txt --output result.txt
~~~

Lệnh này sử dụng `Main-Class` và manifest `Class-Path` của JAR. Không thêm `build/classes` vào classpath vì điều đó có thể che giấu việc JAR thiếu class hoặc resource.

Nếu ứng dụng không phải executable JAR, có thể chạy entry point bằng classpath của distribution, nhưng classpath đó phải được tạo từ các file thực sự được phân phối. Mục đích vẫn là kiểm tra artifact như một sản phẩm hoàn chỉnh.

## 3. Chuẩn bị distribution trước khi chạy

Giả sử ứng dụng có cấu trúc:

~~~text
project/
├── build.xml
├── src/
│   └── main/
│       ├── java/
│       │   └── com/example/Main.java
│       └── resources/
│           └── app.properties
├── src/smoke/
│   └── input.txt
├── lib/runtime/
│   └── runtime-library.jar
└── dist/
    ├── application.jar
    └── lib/
        └── runtime-library.jar
~~~

Target package cần tạo JAR, copy runtime dependency và đặt manifest phù hợp. Ví dụ:

~~~xml
<property name="classes.dir" location="build/classes"/>
<property name="dist.dir" location="dist"/>
<property name="runtime.lib.dir" location="lib/runtime"/>
<property name="app.version" value="1.0.0"/>

<target name="copy-runtime-libs">
    <mkdir dir="${dist.dir}/lib"/>
    <copy todir="${dist.dir}/lib">
        <fileset dir="${runtime.lib.dir}">
            <include name="*.jar"/>
        </fileset>
    </copy>
</target>

<target name="package" depends="compile,copy-runtime-libs">
    <jar destfile="${dist.dir}/application-${app.version}.jar"
         basedir="${classes.dir}">
        <manifest>
            <attribute name="Main-Class" value="com.example.Main"/>
            <attribute name="Implementation-Version" value="${app.version}"/>
            <attribute name="Class-Path" value="lib/runtime-library.jar"/>
        </manifest>
    </jar>
</target>
~~~

Ví dụ giả định `runtime-library.jar` là dependency duy nhất và đã được đặt trong `lib/runtime`. Nếu có nhiều dependency, manifest `Class-Path` phải liệt kê đúng các JAR được copy sang distribution. Với dự án có dependency resolver, nên tạo cả classpath compile và danh sách runtime từ cùng kết quả resolve để tránh hai danh sách bị lệch.

Nếu ứng dụng không có dependency ngoài, có thể bỏ target `copy-runtime-libs` và thuộc tính `Class-Path`. Nếu ứng dụng dùng một cấu trúc phân phối khác, smoke test phải chạy theo đúng cấu trúc mà người dùng sẽ nhận.

## 4. Tạo target smoke test bằng task `<java>`

Task `<java>` của Ant có thể khởi chạy một Java class hoặc executable JAR. Để kiểm tra artifact trong một JVM riêng, đặt `fork="true"`. Với JAR có `Main-Class`, dùng thuộc tính `jar`.

Ví dụ dưới đây giả định ứng dụng nhận `--input` và `--output`, đọc `input.txt`, ghi kết quả vào `result.txt` và trả exit code 0 khi thành công:

~~~xml
<property name="smoke.work.dir" location="build/smoke/work"/>
<property name="smoke.report.dir" location="build/reports/smoke"/>
<property name="app.jar" location="dist/application-1.0.0.jar"/>

<target name="smoke-test" depends="package">
    <!-- Mỗi lần chạy bắt đầu với workspace và report sạch. -->
    <delete dir="${smoke.work.dir}"/>
    <delete dir="${smoke.report.dir}"/>
    <mkdir dir="${smoke.work.dir}"/>
    <mkdir dir="${smoke.report.dir}"/>

    <!-- Chuẩn bị fixture đầu vào. -->
    <copy file="src/smoke/input.txt"
          tofile="${smoke.work.dir}/input.txt"/>

    <!-- Chạy chính JAR đã đóng gói trong JVM riêng. -->
    <java jar="${app.jar}"
          fork="true"
          dir="${smoke.work.dir}"
          failonerror="false"
          resultproperty="smoke.exit"
          output="${smoke.report.dir}/stdout.log"
          error="${smoke.report.dir}/stderr.log"
          timeout="30000">
        <arg value="--input"/>
        <arg value="input.txt"/>
        <arg value="--output"/>
        <arg value="result.txt"/>
    </java>

    <!-- Kiểm tra exit code của tiến trình. -->
    <condition property="smoke.exit.ok">
        <equals arg1="${smoke.exit}" arg2="0"/>
    </condition>
    <fail unless="smoke.exit.ok"
          message="Packaged application failed; exit code=${smoke.exit}. See smoke reports."/>

    <!-- Kiểm tra file kết quả mà ứng dụng phải tạo. -->
    <available file="${smoke.work.dir}/result.txt"
               type="file"
               property="smoke.result.exists"/>
    <fail unless="smoke.result.exists"
          message="Smoke test did not create result.txt"/>

    <!-- Kiểm tra nội dung đầu ra có dấu hiệu thành công mong đợi. -->
    <loadfile property="smoke.result"
              srcFile="${smoke.work.dir}/result.txt"/>
    <condition property="smoke.result.ok">
        <contains string="${smoke.result}"
                  substring="EXPECTED_RESULT"/>
    </condition>
    <fail unless="smoke.result.ok"
          message="Smoke test output does not contain the expected result"/>
</target>
~~~

Trong ví dụ:

- `fork="true"` khởi chạy ứng dụng trong tiến trình JVM riêng.
- `jar` trỏ thẳng tới artifact đã đóng gói.
- `dir` đặt working directory của ứng dụng thành `build/smoke/work`.
- `resultproperty` nhận exit code của tiến trình.
- `failonerror="false"` cho phép Ant tiếp tục tới bước kiểm tra exit code và đưa ra thông báo riêng.
- `output` và `error` lưu stdout/stderr để điều tra khi thất bại.
- `timeout` giới hạn thời gian chạy để smoke test không treo vô hạn.
- `<available>` xác nhận file kết quả tồn tại.
- `<loadfile>` và `<contains>` xác nhận nội dung đầu ra có dấu hiệu mong đợi.

Hãy thay `EXPECTED_RESULT` bằng một chuỗi ổn định mà ứng dụng thực sự tạo ra. Smoke test nên kiểm tra một kết quả có ý nghĩa, không chỉ kiểm tra tiến trình đã khởi động.

Task `<java>` fork sẽ sử dụng Java executable phù hợp với môi trường Ant. Nếu cần kiểm tra bằng một JDK khác với JVM đang chạy Ant, có thể chỉ định executable qua thuộc tính `jvm` của task và bảo đảm JDK đó được cài trên agent.

## 5. Vì sao phải dùng working directory riêng?

Một ứng dụng có thể đọc hoặc ghi file theo đường dẫn tương đối. Nếu smoke test chạy từ thư mục gốc repository, nó có thể vô tình đọc file cấu hình hoặc dữ liệu có sẵn trên máy phát triển. Điều này làm kết quả khác với khi người dùng chạy distribution.

Đặt `dir` cho task `<java>` giúp mô phỏng môi trường chạy tách biệt:

~~~text
project/
├── src/
├── build/
│   ├── classes/
│   ├── reports/
│   └── smoke/
│       └── work/
│           ├── input.txt
│           └── result.txt
└── dist/
    ├── application.jar
    └── lib/
~~~

Trong ví dụ, ứng dụng chỉ nhìn thấy working directory smoke và distribution theo các đường dẫn được cung cấp. Nó không được chạy từ `build/classes` và không dựa vào thư mục source.

Nên xóa workspace smoke cũ trước mỗi lượt chạy. Nếu không, file kết quả còn sót từ lần trước có thể làm test mới tưởng rằng ứng dụng đã tạo output thành công. Dữ liệu fixture đầu vào cũng nên được copy từ một vị trí cố định để mỗi lần chạy có cùng nội dung.

## 6. Kiểm tra resource bên trong artifact

Một lần chạy độc lập nên thực sự sử dụng resource được đóng gói. Ví dụ, ứng dụng có thể đọc `/app.properties` từ classpath để lấy cấu hình mặc định.

Mã Java:

~~~java
import java.io.InputStream;
import java.util.Properties;

public final class Main {
    public static void main(String[] args) throws Exception {
        Properties properties = new Properties();
        try (InputStream input = Main.class.getResourceAsStream("/app.properties")) {
            if (input == null) {
                throw new IllegalStateException("app.properties is missing from the JAR");
            }
            properties.load(input);
        }

        System.out.println("APP_NAME=" + properties.getProperty("app.name"));
        // Continue with the application's command-line operation.
    }
}
~~~

Nếu resource không có trong JAR hoặc nằm sai đường dẫn, ứng dụng sẽ thất bại khi chạy. Đây chính là loại lỗi mà chạy class từ `build/classes` có thể che giấu nếu resource vẫn còn trong thư mục output nhưng bị bỏ quên khi đóng gói.

Có thể bổ sung assertion kiểm tra stdout:

~~~xml
<loadfile property="smoke.stdout"
          srcFile="${smoke.report.dir}/stdout.log"/>
<condition property="smoke.stdout.ok">
    <contains string="${smoke.stdout}"
              substring="APP_NAME=Sample"/>
</condition>
<fail unless="smoke.stdout.ok"
      message="Packaged resource was not loaded as expected"/>
~~~

Nếu stdout lớn hoặc có dữ liệu biến đổi, hãy kiểm tra một marker ổn định hoặc để ứng dụng ghi một kết quả có cấu trúc vào file riêng. Không nên so sánh toàn bộ log nếu timestamp, đường dẫn hoặc thông tin môi trường thay đổi giữa các lần chạy.

## 7. Kiểm tra dependency runtime của distribution

Một JAR có thể có `Main-Class` nhưng vẫn không chạy được nếu dependency bên ngoài không có mặt. Có hai cách phân phối phổ biến:

1. Copy các JAR runtime vào thư mục bên cạnh application JAR và khai báo manifest `Class-Path`.
2. Tạo một archive gộp dependency (fat/uber JAR) bằng quy trình đóng gói được thiết kế cho mục tiêu đó.

Với cách thứ nhất:

~~~text
dist/
├── application.jar
└── lib/
    ├── logging-api.jar
    └── json-core.jar
~~~

Manifest của application JAR phải tham chiếu đúng các file, ví dụ:

~~~text
Class-Path: lib/logging-api.jar lib/json-core.jar
~~~

Smoke test chạy bằng `java -jar dist/application.jar` sẽ kiểm tra việc launcher đọc manifest và tìm các dependency. Nếu thiếu một JAR hoặc tên trong `Class-Path` sai, ứng dụng có thể thất bại khi tải class.

Nếu test dùng `classpath` của Ant gồm `build/classes` và toàn bộ thư viện trong `lib`, nó có thể chạy thành công dù distribution bị thiếu JAR. Vì vậy, khi mục tiêu là kiểm tra sản phẩm đóng gói, hãy chạy JAR theo manifest hoặc classpath distribution đã cài đặt, không mượn classpath nội bộ của build.

## 8. Kiểm tra cấu trúc JAR trước hoặc sau lần chạy

Có thể dùng công cụ `jar` của JDK để liệt kê entry:

~~~bash
jar tf dist/application.jar
~~~

Kiểm tra tối thiểu:

- Lớp entry point có mặt ở đường dẫn đúng, ví dụ `com/example/Main.class`.
- Resource cần thiết có mặt ở đúng đường dẫn.
- Manifest tồn tại tại `META-INF/MANIFEST.MF`.
- Không có class test, log, file tạm hoặc secret ngoài ý muốn.

Để xem manifest, có thể dùng:

~~~bash
jar xf dist/application.jar META-INF/MANIFEST.MF
cat META-INF/MANIFEST.MF
~~~

Kiểm tra archive là bước hỗ trợ. Lần chạy thử vẫn cần thiết vì chỉ chạy mới xác nhận launcher, class loading, resource loading và hành vi tối thiểu của chương trình trong runtime.

## 9. Kiểm tra JAR thư viện không có `Main-Class`

Không phải mọi JAR đều là ứng dụng có thể chạy bằng `java -jar`. Một JAR thư viện thường không có `Main-Class`; mục tiêu của nó là được một ứng dụng khác sử dụng.

Với thư viện, có thể tạo một smoke-test consumer nhỏ trong source test hoặc một thư mục riêng. Consumer được biên dịch với classpath chỉ gồm JAR đã đóng gói và dependency phân phối:

~~~text
build/smoke/
├── consumer-src/
│   └── LibrarySmoke.java
├── consumer-classes/
└── lib/
    └── library-under-test.jar
~~~

Ví dụ consumer:

~~~java
import com.example.library.PublicApi;

public class LibrarySmoke {
    public static void main(String[] args) {
        String result = new PublicApi().greet("Ant");
        if (!"Hello, Ant".equals(result)) {
            throw new AssertionError("Unexpected library result: " + result);
        }
        System.out.println("LIBRARY_SMOKE_OK");
    }
}
~~~

Target Ant có thể compile consumer và chạy nó bằng classpath gồm JAR trong distribution:

~~~xml
<target name="smoke-library" depends="package">
    <mkdir dir="build/smoke/consumer-classes"/>
    <javac srcdir="build/smoke/consumer-src"
           destdir="build/smoke/consumer-classes"
           includeantruntime="false">
        <classpath>
            <pathelement location="dist/library-under-test.jar"/>
            <fileset dir="dist/lib">
                <include name="*.jar"/>
            </fileset>
        </classpath>
    </javac>

    <java classname="LibrarySmoke"
          fork="true"
          failonerror="true">
        <classpath>
            <pathelement location="build/smoke/consumer-classes"/>
            <pathelement location="dist/library-under-test.jar"/>
            <fileset dir="dist/lib">
                <include name="*.jar"/>
            </fileset>
        </classpath>
    </java>
</target>
~~~

Trong trường hợp này, consumer class là chương trình kiểm tra; thư viện được nạp từ JAR đóng gói trong `dist`, không lấy class production trực tiếp từ `build/classes`. Nếu mục tiêu là kiểm tra API công khai và dependency runtime, hãy giữ classpath consumer đúng với cách người dùng sẽ sử dụng thư viện.

## 10. Kiểm soát kết quả bằng exit code và output

Một smoke test đáng tin cậy nên có nhiều tín hiệu kết quả:

| Tín hiệu | Điều cần xác nhận |
|---|---|
| Tiến trình khởi chạy | JVM tìm được executable JAR hoặc entry point |
| Exit code | 0 nếu thao tác thử nghiệm thành công theo hợp đồng CLI |
| Stdout/stderr | Có log phục vụ điều tra, không chứa lỗi bất ngờ |
| File hoặc response đầu ra | Chức năng đại diện tạo kết quả thực tế |
| Nội dung kết quả | Output khớp marker hoặc giá trị mong đợi |
| Thời gian chạy | Hoàn thành trong giới hạn timeout |

Không nên chỉ kiểm tra rằng process không bị crash ngay lập tức. Ứng dụng có thể trả exit code 0 nhưng không thực hiện chức năng mong đợi; do đó cần kiểm tra thêm output. Ngược lại, nếu CLI được thiết kế để trả mã khác 0 cho một trường hợp nghiệp vụ hợp lệ, smoke test phải dùng tình huống có hợp đồng exit code rõ ràng.

Với ứng dụng server, một lần chạy thử có thể cần khởi động server trong tiến trình riêng, chờ cổng hoặc endpoint sẵn sàng, gửi một request và kiểm tra response trước khi dừng server. Không nên chỉ dựa vào việc process vẫn đang chạy vì server có thể bị treo hoặc không bind được cổng. Hãy dùng một cổng thử nghiệm được cấp riêng và cơ chế dọn tiến trình sau test để tránh làm rò rỉ process trên CI agent.

## 11. Gắn smoke test vào luồng build

Sau khi target `smoke-test` hoạt động độc lập, có thể nối nó vào target verify/package validation:

~~~xml
<target name="verify-package" depends="smoke-test"/>

<target name="release-ready" depends="verify-package">
    <echo message="Packaged application passed the smoke test"/>
</target>
~~~

Pipeline CI có thể gọi:

~~~bash
ant clean release-ready
~~~

Dependency graph đảm bảo compile, package và smoke test hoàn tất trước khi target `release-ready` được thực hiện. Nếu smoke test thất bại, Ant dừng target phụ thuộc và CI nhận trạng thái lỗi.

Có thể tách target `package` khỏi `smoke-test` để người phát triển vẫn tạo được JAR nhanh khi cần. Target phát hành hoặc CI chính thức nên gọi target tổng hợp có smoke test để artifact được kiểm tra trước khi publish.

Một nguyên tắc hữu ích là tạo artifact một lần, kiểm tra chính artifact đó, rồi chuyển cùng artifact sang bước publish/deploy. Tránh build lại một JAR khác sau khi smoke test thành công vì kết quả mới chưa được kiểm tra.

## 12. Chạy thử trong môi trường gần với production

Một lần chạy độc lập sẽ có giá trị hơn khi môi trường thử nghiệm gần với môi trường đích:

- Dùng JDK/runtime được hỗ trợ.
- Dùng đúng cấu trúc thư mục phân phối.
- Cung cấp biến môi trường và system property cần thiết.
- Dùng cấu hình thử nghiệm thay vì cấu hình production có secret.
- Cấp quyền file/network tối thiểu cần thiết.
- Không dựa vào file nằm ngoài distribution trừ những dependency môi trường đã được quy định.
- Ghi lại phiên bản artifact, JDK và cấu hình test trong log.

Nếu ứng dụng hỗ trợ nhiều phiên bản Java, có thể chạy cùng artifact trên từng runtime được hỗ trợ. Điều này khác với biên dịch lại cho từng JDK: mục tiêu là xác nhận một artifact cụ thể hoạt động trên các runtime tương ứng với chính sách phát hành.

Đối với cấu hình production, không dùng credential hoặc endpoint thật trong smoke test. Hãy dùng fixture, sandbox hoặc dịch vụ thử nghiệm có kiểm soát để test không gây tác động tới hệ thống đang vận hành.

## 13. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `no main manifest attribute` | JAR không có `Main-Class` | Kiểm tra nested `<manifest>` hoặc file manifest đầu vào |
| `Could not find or load main class` | Sai tên Main-Class hoặc thiếu entry class | So sánh manifest với entry trong `jar tf` |
| `NoClassDefFoundError` | Dependency runtime thiếu hoặc manifest Class-Path sai | Kiểm tra `dist/lib` và đường dẫn trong manifest |
| Resource không tìm thấy | Resource không được đóng gói hoặc sai đường dẫn | Kiểm tra entry trong JAR và cách gọi resource API |
| Chạy local được nhưng smoke test thất bại | Local đang dùng file/classpath ngoài distribution | Chạy đúng JAR trong working directory riêng và kiểm tra dependency |
| Exit code khác 0 | Ứng dụng trả lỗi hoặc thiếu cấu hình/input | Đọc stderr/stdout và kiểm tra fixture, tham số, môi trường |
| Exit code 0 nhưng output sai | Chỉ kiểm tra process status, chưa kiểm tra kết quả nghiệp vụ | Thêm assertion trên file/response/marker đầu ra |
| Test đọc nhầm file cũ | Workspace không được dọn trước lần chạy | Xóa và tạo lại smoke workspace trước khi copy fixture |
| Test treo | Ứng dụng chờ input hoặc server không dừng | Đặt timeout và xác định điều kiện kết thúc rõ ràng |
| Build agent giữ process sau test | Ứng dụng được khởi chạy kiểu background/spawn | Dùng tiến trình đồng bộ hoặc cơ chế cleanup process rõ ràng |
| Artifact chạy sai phiên bản Java | Runtime smoke test khác Java target | Chạy bằng JDK/runtime mục tiêu và ghi nhận version |
| Report không có khi thất bại | Thư mục report chưa tồn tại hoặc tiến trình không ghi output | Tạo thư mục trước, lưu stdout/stderr và giữ artifact CI |

Khi thất bại, kiểm tra theo thứ tự: file JAR có tồn tại, manifest có đúng, dependency có đủ, process có khởi chạy, exit code là gì, log báo lỗi nào và output có được tạo đúng không. Không nên bỏ qua failure chỉ để pipeline tiếp tục.

## 14. Quy trình thực hiện một lần chạy thử độc lập

Một quy trình thực tế có thể gồm:

1. Chạy clean build và tạo JAR/distribution.
2. Kiểm tra nhanh archive và manifest.
3. Tạo working directory riêng cho smoke test.
4. Copy input fixture và cấu hình thử nghiệm vào workspace.
5. Khởi chạy artifact bằng JVM riêng theo cách người dùng sẽ chạy.
6. Đặt timeout và lưu stdout/stderr.
7. Kiểm tra exit code.
8. Kiểm tra output tồn tại và có nội dung mong đợi.
9. Lưu log/report làm artifact của CI.
10. Chỉ cho phép publish/deploy khi smoke test đạt.

Smoke test nên nhỏ, ổn định và chạy nhanh. Chọn một đường đi đại diện quan trọng của sản phẩm, ví dụ đọc cấu hình, xử lý một input mẫu và tạo output. Những kiểm tra sâu hơn thuộc về unit test, integration test hoặc acceptance test; không cần biến smoke test thành một bộ kiểm thử dài và khó duy trì.

## Kết luận

Kiểm tra sản phẩm đóng gói bằng một lần chạy thử độc lập nghĩa là chạy JAR hoặc distribution đã tạo trong một tiến trình JVM riêng, với working directory và input được kiểm soát, rồi xác nhận exit code cùng kết quả thực tế. Với executable JAR, Ant `<java jar="..." fork="true">` có thể mô phỏng lệnh `java -jar`; với JAR thư viện, có thể biên dịch và chạy một consumer nhỏ chỉ sử dụng artifact trong distribution. Hãy tránh dùng `build/classes` làm runtime classpath, kiểm tra dependency và resource từ chính gói phân phối, lưu log/report, đặt timeout và nối smoke test vào cổng trước publish/deploy để phát hiện lỗi đóng gói sớm.