# Phân biệt JDK chạy Ant và JDK dùng để biên dịch dự án

Khi chạy một dự án Java bằng Apache Ant, có thể có hai JDK tham gia vào quá trình build: JDK cung cấp JVM để khởi động Ant và JDK cung cấp trình biên dịch `javac` để biên dịch mã nguồn của dự án. Hai vai trò này thường dùng chung một JDK, nhưng không bắt buộc phải như vậy.

Điểm cần xác định là Ant đang chạy trong JVM nào, task `javac` lấy compiler từ đâu, và bytecode được tạo ra dành cho phiên bản Java nào. Ba thông tin này có liên quan nhưng không đồng nghĩa. Nếu nhầm lẫn chúng, một build có thể chạy bằng JDK mới nhưng vẫn biên dịch bằng compiler cũ, hoặc biên dịch được mã nguồn nhưng tạo bytecode không tương thích với môi trường triển khai.

## 1. Ba phiên bản Java cần phân biệt

Trong một build Ant, hãy tách ba khái niệm sau:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| JDK chạy Ant (Ant runtime JDK) | JDK cung cấp JVM khởi động tiến trình Ant và chạy các Ant task trong tiến trình đó | Ant chạy bằng JDK 21 |
| JDK dùng để biên dịch (compiler JDK) | JDK cung cấp `javac` thực sự biên dịch mã nguồn | Mã nguồn được biên dịch bằng JDK 17 |
| Phiên bản Java đích (target/runtime Java) | Phiên bản Java mà bytecode và API được biên dịch để tương thích | Ứng dụng yêu cầu Java 17 khi chạy |

Một cấu hình có thể dùng JDK 21 để chạy Ant, JDK 17 để biên dịch, và tạo bytecode Java 17. Một cấu hình khác có thể dùng cùng JDK 17 cho cả Ant và compiler. Việc dùng JDK mới hơn để khởi động Ant không tự động có nghĩa dự án được biên dịch theo phiên bản Java mới hơn.

Cũng cần phân biệt JDK với JRE theo cách gọi truyền thống. JDK chứa các công cụ phát triển như `javac`; môi trường runtime chỉ đủ chạy ứng dụng có thể không có compiler. Ant vẫn có thể chạy những task không cần biên dịch trong một runtime phù hợp, nhưng task biên dịch in-process cần compiler của JDK. Trong các bản Java hiện đại, JDK là cách cài đặt tiêu chuẩn; không nên giả định mọi máy đều có một bộ JRE độc lập.

## 2. JDK nào khởi động tiến trình Ant?

Ant là một ứng dụng Java. Khi chạy lệnh `ant`, script khởi động Ant tìm Java executable và dùng nó để mở JVM chạy lớp khởi động của Ant. JDK được chọn ở bước này là JDK chạy Ant.

Trên nhiều môi trường, biến `JAVA_HOME` là đầu mối quan trọng:

- `JAVA_HOME` trỏ tới thư mục gốc của JDK, chẳng hạn `/opt/jdk-21` hoặc `C:\Program Files\Java\jdk-21`.
- Script `ant`/`ant.bat` thường ưu tiên Java dưới `JAVA_HOME` nếu biến này được thiết lập hợp lệ.
- Nếu `JAVA_HOME` không được thiết lập, script có thể tìm `java` từ `PATH`, tùy cách cài đặt Ant và môi trường shell.
- `ANT_HOME` xác định vị trí cài đặt Ant; nó không phải đường dẫn JDK.
- `ANT_OPTS` truyền các tùy chọn JVM cho tiến trình Ant, ví dụ giới hạn heap hoặc cấu hình hệ thống.

Ví dụ trên Linux/macOS:

~~~bash
export JAVA_HOME=/opt/jdk-21
export ANT_HOME=/opt/apache-ant
export PATH="$JAVA_HOME/bin:$ANT_HOME/bin:$PATH"

java -version
ant -version
ant -diagnostics
~~~

Ví dụ trên Windows PowerShell:

~~~powershell
$env:JAVA_HOME = 'C:\Program Files\Java\jdk-21'
$env:ANT_HOME = 'C:\tools\apache-ant'
$env:Path = "$env:JAVA_HOME\bin;$env:ANT_HOME\bin;$env:Path"

java -version
ant -version
ant -diagnostics
~~~

`java -version` hiển thị Java được shell tìm thấy theo `PATH`. Nếu script Ant ưu tiên một `JAVA_HOME` khác, kết quả `java -version` có thể không phản ánh đúng JVM Ant sử dụng. Vì vậy, khi điều tra cần xem cả `JAVA_HOME`, `PATH`, thông tin của `ant -diagnostics` và log khởi động Ant.

JDK chạy Ant còn quyết định môi trường thực thi của các custom Ant task, taskdef và plugin được nạp vào cùng JVM. Nếu một task mở rộng được biên dịch bằng Java mới hơn phiên bản runtime đang chạy Ant, task đó có thể không nạp được và báo lỗi phiên bản class file không được hỗ trợ. Đây là vấn đề tương thích của mã chạy trong Ant, khác với phiên bản Java đích của ứng dụng.

## 3. Task `javac` lấy compiler từ đâu?

Trong `build.xml`, dự án thường biên dịch mã nguồn bằng task `<javac>`. Task này có thể gọi compiler theo hai cách chính.

### 3.1. Biên dịch in-process: dùng compiler của JVM chạy Ant

Mặc định, task `javac` có `fork="false"`. Ant thực hiện biên dịch trong chính tiến trình Ant thông qua compiler adapter và Java compiler API. Với compiler `javac` chuẩn, compiler được lấy từ JDK đang chạy Ant.

~~~xml
<target name="compile">
    <mkdir dir="build/classes"/>
    <javac srcdir="src/main/java"
           destdir="build/classes"
           includeantruntime="false"
           fork="false"
           encoding="UTF-8"/>
</target>
~~~

Nếu Ant đang chạy bằng JDK 21, cấu hình in-process này sử dụng compiler của JDK 21. Chỉ đặt `source="17"` và `target="17"` không làm Ant chuyển sang chạy compiler của JDK 17; đó là các tùy chọn điều khiển mức ngôn ngữ và định dạng bytecode, không phải lựa chọn một JDK cài đặt khác.

Cách in-process có một số đặc điểm:

- Không cần tạo tiến trình `javac` bên ngoài cho mỗi lần biên dịch.
- Compiler dùng cùng môi trường Java với Ant.
- Dễ cấu hình khi dự án chỉ cần một JDK thống nhất.
- Không thể chọn một `javac` độc lập bằng cách chỉ đổi `source`, `target` hoặc `release`.
- Nếu compiler không có trong runtime đang chạy Ant, task không thể thực hiện biên dịch in-process bằng `javac`.

### 3.2. Biên dịch forked: gọi `javac` ở một tiến trình riêng

Khi đặt `fork="true"`, Ant tạo tiến trình ngoài để chạy compiler. Thuộc tính `executable` cho phép chỉ rõ đường dẫn tới chương trình `javac` muốn sử dụng.

~~~xml
<property name="compile.jdk.home" location="/opt/jdk-17"/>

<target name="compile">
    <mkdir dir="build/classes"/>
    <javac srcdir="src/main/java"
           destdir="build/classes"
           includeantruntime="false"
           fork="true"
           executable="${compile.jdk.home}/bin/javac"
           encoding="UTF-8"/>
</target>
~~~

Ở ví dụ này, Ant có thể chạy bằng JDK 21 nhưng task compile gọi `/opt/jdk-17/bin/javac`. JVM của Ant và JVM/compiler của tiến trình biên dịch được tách riêng. Trên Windows, đường dẫn thường trỏ tới `bin/javac.exe`, ví dụ:

~~~xml
<property name="compile.jdk.home" location="C:/Program Files/Java/jdk-17"/>

<javac srcdir="src/main/java"
       destdir="build/classes"
       fork="true"
       executable="${compile.jdk.home}/bin/javac.exe"
       includeantruntime="false"/>
~~~

Nếu dùng `fork="true"` mà không chỉ rõ `executable`, việc tìm compiler phụ thuộc vào cách Ant và môi trường hệ điều hành phân giải executable. Để build có thể tái lập, nên cấu hình đường dẫn compiler rõ ràng khi dự án yêu cầu một JDK riêng. Cũng cần bảo đảm đường dẫn đó tồn tại trên máy local và agent CI.

Hai cách gọi có thể so sánh như sau:

| Cấu hình | JVM chạy Ant | Compiler thực tế |
|---|---|---|
| `fork="false"` (mặc định) | JDK 21 | Compiler của JDK 21 đang chạy Ant |
| `fork="true"`, executable trỏ JDK 17 | JDK 21 | `javac` thuộc JDK 17 được chỉ định |
| `fork="true"`, executable trỏ JDK 21 | JDK 17 | `javac` thuộc JDK 21 được chỉ định |

Việc fork chỉ tách tiến trình compiler. Ant vẫn phải chạy được trên JDK runtime đã chọn, các task khác vẫn chạy theo JVM của Ant, và build file vẫn cần tương thích với phiên bản Ant đang cài.

## 4. Phiên bản Java đích không phải là phiên bản JDK đang chạy Ant

Một trong những nhầm lẫn phổ biến nhất là cho rằng `source` hoặc `target` quyết định JDK nào được dùng. Thực tế, chúng không chọn JDK cài đặt.

- `source` giới hạn cú pháp ngôn ngữ Java mà compiler chấp nhận.
- `target` yêu cầu compiler tạo bytecode theo định dạng class file của phiên bản Java tương ứng.
- Tùy chọn `--release` trên các JDK hỗ trợ nó vừa giới hạn mức ngôn ngữ, vừa chọn định dạng bytecode và tập API Java công khai của phiên bản đích.

Ví dụ, khi Ant chạy bằng JDK 21 và biên dịch in-process, có thể yêu cầu compiler JDK 21 tạo đầu ra tương thích Java 17:

~~~xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       includeantruntime="false"
       encoding="UTF-8">
    <compilerarg value="--release"/>
    <compilerarg value="17"/>
</javac>
~~~

Với compiler JDK 9 trở lên, `--release 17` giúp tránh việc vô tình gọi API chỉ có ở Java 21 trong mã nguồn cần chạy trên Java 17. Ví dụ, nếu chỉ dùng `source="17"` và `target="17"` với compiler mới, compiler có thể vẫn nhìn thấy API của JDK mới hơn; chương trình có thể biên dịch thành công nhưng gặp lỗi khi chạy trên Java 17 vì API đó không tồn tại ở runtime đích.

Không kết hợp `--release` với `source`/`target` trong cùng một lần gọi `javac`; chọn một cách cấu hình nhất quán. Nếu compiler là JDK 8 thì không có tùy chọn `--release`. Với yêu cầu tương thích Java 8, cần dùng compiler/JDK phù hợp và cấu hình `source`, `target` cùng API boot class path thích hợp, hoặc dùng một công cụ build/toolchain có hỗ trợ tương ứng.

Một giới hạn khác: JDK 17 không thể biên dịch cú pháp Java 21 chỉ bằng cách đặt `target` thành 21. Muốn dùng tính năng ngôn ngữ mới, compiler phải đủ mới. Nếu Ant chạy bằng JDK 17 nhưng cần biên dịch mã Java 21, có thể giữ Ant ở JDK 17 và fork compiler JDK 21, miễn là phiên bản Ant, task và môi trường hỗ trợ cấu hình đó.

## 5. Ba kịch bản cấu hình thường gặp

### Kịch bản A: Dùng một JDK cho cả Ant và compiler

Đây là lựa chọn đơn giản nhất. Ví dụ dự án yêu cầu Java 17:

~~~bash
export JAVA_HOME=/opt/jdk-17
export PATH="$JAVA_HOME/bin:$PATH"
ant clean compile
~~~

Với `<javac fork="false">`, Ant và compiler cùng lấy JDK 17. Cấu hình này dễ hiểu, dễ chẩn đoán và thường phù hợp khi không có yêu cầu giữ Ant ở một JDK khác.

### Kịch bản B: Ant chạy JDK mới, dự án biên dịch bằng JDK cũ hơn

Ví dụ máy build cần JDK 21 để chạy Ant và một số task hiện đại, nhưng sản phẩm phải được biên dịch bằng JDK 17:

~~~text
JAVA_HOME = /opt/jdk-21
        |
        v
  Ant JVM chạy JDK 21
        |
        | fork="true"
        v
 /opt/jdk-17/bin/javac
        |
        v
 bytecode Java 17
        |
        v
 chạy trên Java 17 trở lên
~~~

Khai báo đường dẫn compiler riêng trong build file hoặc nhận từ property của CI:

~~~xml
<property environment="env"/>
<property name="compile.jdk.home" value="${env.COMPILE_JDK_HOME}"/>

<target name="compile">
    <javac srcdir="src/main/java"
           destdir="build/classes"
           fork="true"
           executable="${compile.jdk.home}/bin/javac"
           includeantruntime="false"
           encoding="UTF-8"/>
</target>
~~~

Trên Windows, property cần trỏ đến `bin/javac.exe`. Cần kiểm tra biến `COMPILE_JDK_HOME` đã được CI cung cấp; không nên để property rỗng rồi âm thầm dùng compiler khác.

### Kịch bản C: Ant chạy JDK cũ, compiler được fork từ JDK mới

Trường hợp này có thể hữu ích khi một build hiện có phải giữ runtime của Ant ổn định, nhưng mã nguồn đã chuyển lên phiên bản Java mới hơn:

~~~text
JAVA_HOME = /opt/jdk-17
        |
        v
  Ant JVM chạy JDK 17
        |
        | fork="true"
        v
 /opt/jdk-21/bin/javac
        |
        v
 bytecode Java 21
        |
        v
 yêu cầu runtime Java 21 trở lên
~~~

Cấu hình fork cho phép compiler riêng thực hiện công việc. Tuy nhiên, điều này không làm cho mọi task trong Ant tự động dùng Java 21. Custom task, script Java, công cụ kiểm tra hoặc test chạy trong JVM Ant vẫn chịu giới hạn của JDK 17, trừ khi chính chúng cũng được cấu hình chạy ở tiến trình riêng.

## 6. Tách compiler JDK khỏi Java dùng để chạy test

Sau khi biên dịch, dự án có thể chạy test bằng JVM khác. Ví dụ, mã nguồn được biên dịch bằng JDK 17 nhưng integration test cần chạy trên Java 21 để kiểm tra môi trường triển khai.

Vì vậy, trong pipeline phức tạp có thể có ba lựa chọn độc lập:

1. JDK chạy Ant và các task in-process.
2. JDK chạy compiler `javac`.
3. JDK chạy test hoặc ứng dụng trong giai đoạn kiểm thử.

Một số task kiểm thử hỗ trợ fork JVM riêng và cho phép chỉ định executable Java. Khi cần kiểm tra nhiều runtime, có thể chạy cùng một artifact trên nhiều JDK khác nhau. Hãy phân biệt việc biên dịch artifact một lần với việc chạy test nhiều lần trên các JVM: chạy test trên Java 21 không chứng minh artifact tương thích Java 17, trừ khi có kiểm thử riêng trên Java 17.

Sơ đồ tổng quát:

~~~text
                   CI agent
                      |
                      v
             JDK chạy tiến trình Ant
                      |
          +-----------+------------+
          |                        |
          v                        v
     Ant tasks                 fork javac
     in-process                JDK compiler
          |                        |
          +-----------+------------+
                      |
                      v
                 JAR / WAR
                      |
             +--------+--------+
             |                 |
             v                 v
        Test trên JDK 17  Test trên JDK 21
             |                 |
             +--------+--------+
                      |
                      v
             Đánh giá tương thích runtime
~~~

Không phải mọi dự án đều cần ba JDK khác nhau. Chỉ tách chúng khi có yêu cầu tương thích, kiểm thử đa phiên bản hoặc ràng buộc công cụ cụ thể. Nếu không, một JDK thống nhất giúp giảm cấu hình và rủi ro môi trường.

## 7. Kiểm tra chính xác Ant và compiler đang dùng JDK nào

Không nên chỉ chạy `java -version` rồi kết luận compiler của Ant cũng dùng phiên bản đó. Hãy kiểm tra từng lớp.

### 7.1. Kiểm tra môi trường shell

Linux/macOS:

~~~bash
printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
command -v java
command -v javac
java -version
javac -version
ant -version
~~~

Windows PowerShell:

~~~powershell
$env:JAVA_HOME
Get-Command java
Get-Command javac
java -version
javac -version
ant -version
~~~

Các lệnh `java` và `javac` ở đây phản ánh cách shell tìm executable. Chúng hữu ích để phát hiện nhiều bản JDK trong `PATH`, nhưng chưa đủ để xác nhận Ant đã chọn đúng Java.

### 7.2. Kiểm tra JVM chạy Ant

Chạy:

~~~bash
ant -diagnostics
~~~

Thông tin diagnostics giúp xem phiên bản Ant, Java runtime, thuộc tính hệ thống và môi trường mà Ant nhận được. Có thể thêm một target nhỏ vào `build.xml` để in các thuộc tính của JVM hiện tại:

~~~xml
<target name="show-ant-java">
    <echo message="java.version=${java.version}"/>
    <echo message="java.home=${java.home}"/>
    <echo message="ant.java.version=${ant.java.version}"/>
    <echo message="JAVA_HOME=${env.JAVA_HOME}"/>
</target>
~~~

Các thuộc tính `java.version` và `java.home` là thuộc tính hệ thống của JVM chạy Ant. Chúng cho biết runtime thực tế của tiến trình Ant, hữu ích hơn việc chỉ nhìn kết quả `java -version` trong một shell có nhiều cấu hình Java.

### 7.3. Kiểm tra compiler được task `javac` sử dụng

Nếu `fork="false"`, compiler chuẩn lấy từ JDK chạy Ant. Có thể đối chiếu `java.home` và thông tin Java trong diagnostics.

Nếu `fork="true"`, hãy kiểm tra giá trị `executable` trong build file hoặc property được truyền vào. Đường dẫn đó là đầu mối xác định compiler. Có thể kiểm tra trực tiếp:

~~~bash
/opt/jdk-17/bin/javac -version
~~~

Trên Windows:

~~~powershell
& 'C:\Program Files\Java\jdk-17\bin\javac.exe' -version
~~~

Có thể chạy Ant với `-verbose` hoặc `-debug` để xem thêm thông tin về task và lệnh compiler được gọi:

~~~bash
ant -verbose compile
ant -debug compile
~~~

Log chi tiết có thể rất dài. Hãy tìm phần liên quan tới `javac`, compiler adapter, executable và tham số biên dịch. Nếu dùng compiler khác thông qua adapter hoặc công cụ tùy chỉnh, cần kiểm tra adapter đó thay vì mặc định coi mọi task `javac` đều gọi cùng một executable.

## 8. Những nhầm lẫn và lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `java -version` là 21 nhưng Ant báo Java 17 | `JAVA_HOME` của script Ant khác Java đầu tiên trong `PATH` | Kiểm tra `JAVA_HOME`, script Ant và `ant -diagnostics` |
| Đặt `source="17"` nhưng compiler vẫn là JDK 21 | `source` chỉ giới hạn cú pháp, không chọn compiler JDK | Dùng `fork="true"` và `executable` nếu cần JDK 17 thực sự |
| Build báo không tìm thấy compiler | Ant chạy bằng runtime không có compiler hoặc compiler executable sai | Dùng JDK cho Ant hoặc cấu hình fork tới `javac` hợp lệ |
| Mã biên dịch được nhưng chạy lỗi do API không tồn tại | Chỉ đặt `source`/`target`, compiler vẫn nhìn thấy API của JDK mới | Dùng `--release` trên compiler phù hợp hoặc biên dịch bằng JDK đích |
| Mã Java mới không biên dịch được | Compiler JDK quá cũ, dù máy có cài JDK mới | Kiểm tra `fork`, `executable` và compiler thực tế |
| Ant task tùy chỉnh không nạp được | Task được biên dịch bằng Java mới hơn JDK chạy Ant | Nâng JDK chạy Ant hoặc biên dịch lại task tương thích |
| Local build thành công, CI thất bại | Agent CI chọn JDK khác hoặc thiếu đường dẫn compiler riêng | Khai báo và kiểm tra JDK rõ ràng trong pipeline |
| Build lúc dùng JDK này, lúc dùng JDK khác | Dựa vào `PATH` hoặc `JAVA_HOME` không nhất quán | Pin phiên bản JDK và chỉ rõ `executable` cho compiler forked |

Một thông báo như `Unsupported class file major version` cũng cần xác định nó xuất hiện ở đâu: Ant JVM không đọc được bytecode của custom task, compiler không hỗ trợ class file đầu vào, hay runtime ứng dụng không chạy được artifact. Cùng một nhóm thông báo về class file có thể xuất hiện ở các giai đoạn khác nhau; hãy dựa vào stack trace và task đang thực hiện để tìm đúng JDK liên quan.

## 9. Cấu hình JDK rõ ràng trong CI/CD

Trong CI, nên xem JDK là một phần của cấu hình build được kiểm soát. Một pipeline có thể khai báo riêng:

~~~text
ANT_JDK_HOME      = JDK dùng khởi động Ant
COMPILE_JDK_HOME  = JDK cung cấp javac khi fork
TEST_JDK_HOME     = JDK dùng chạy test forked (nếu cần)
JAVA_RELEASE      = phiên bản Java đích của artifact
~~~

Trước khi gọi Ant, pipeline nên:

1. Chọn đúng JDK và đặt `JAVA_HOME` cho tiến trình Ant.
2. Kiểm tra `java -version` và `ant -diagnostics`.
3. Kiểm tra compiler path nếu build dùng forked `javac`.
4. Xác nhận phiên bản đích của artifact được cấu hình nhất quán.
5. Lưu log build để có thể xác định JDK và compiler đã dùng khi xảy ra lỗi.

Nếu dự án chỉ dùng một JDK, không cần tạo ba biến riêng. Có thể dùng một biến `JAVA_HOME`, để Ant chạy và biên dịch in-process bằng cùng JDK. Điều quan trọng là lựa chọn đó được ghi rõ và CI sử dụng cùng cấu hình với máy phát triển.

Không nên hard-code đường dẫn JDK của một máy cá nhân vào `build.xml` dùng chung cho cả nhóm. Hãy truyền đường dẫn qua property hoặc biến môi trường, cung cấp giá trị theo từng agent CI, rồi kiểm tra đường dẫn trước khi chạy compile. Nếu đường dẫn không hợp lệ, build nên dừng với thông báo rõ ràng thay vì âm thầm chọn một compiler khác.

## 10. Quy tắc lựa chọn thực tế

Có thể dùng các câu hỏi sau để chọn cấu hình:

- Nếu Ant và dự án đều hỗ trợ cùng một JDK, và không cần compiler riêng, dùng một JDK cho cả hai với `fork="false"`.
- Nếu cần giữ Ant ở JDK hiện tại nhưng biên dịch bằng một JDK khác, dùng `fork="true"` và chỉ rõ `executable`.
- Nếu cần giới hạn API và bytecode cho một phiên bản Java cũ hơn compiler đang dùng, ưu tiên `--release` khi JDK compiler hỗ trợ.
- Nếu cần chạy test trên nhiều phiên bản Java, cấu hình JVM test riêng cho từng lượt và ghi nhận runtime thực tế.
- Nếu custom Ant task hoặc plugin không tương thích với JDK chạy Ant, giải quyết tương thích của task/runtime trước; đổi `target` của ứng dụng không xử lý được vấn đề đó.

Khi điều tra một lỗi build, hãy trả lời theo thứ tự: JVM nào đang chạy Ant? Task `javac` chạy in-process hay fork? Nếu fork, executable nào được gọi? Compiler đó hỗ trợ phiên bản ngôn ngữ nào? Artifact được tạo cho Java đích nào? Cuối cùng, test và môi trường triển khai chạy bằng JDK nào? Trả lời riêng từng câu sẽ giúp xác định đúng lớp cấu hình cần sửa.

## Kết luận

JDK chạy Ant quyết định JVM thực thi Ant và các task chạy cùng tiến trình. JDK dùng để biên dịch quyết định compiler thực sự xử lý mã nguồn; với `<javac>` mặc định `fork="false"`, đó thường là compiler của JDK đang chạy Ant, còn `fork="true"` cùng `executable` cho phép gọi một JDK khác. Phiên bản Java đích lại là lựa chọn riêng, được kiểm soát bằng tùy chọn compiler như `--release` khi có hỗ trợ. Khi cấu hình hoặc chẩn đoán build, cần xác định rõ cả ba vai trò thay vì suy luận compiler từ `JAVA_HOME` hoặc từ `source`/`target` đơn lẻ.
