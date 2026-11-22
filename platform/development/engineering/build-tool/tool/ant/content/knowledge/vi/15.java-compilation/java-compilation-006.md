# Biên dịch trong JVM hiện tại hoặc tách tiến trình bằng fork

Task `<javac>` của Apache Ant có thể biên dịch mã nguồn Java ngay trong JVM đang chạy Ant hoặc khởi chạy trình biên dịch ở một tiến trình riêng. Hai cách này tạo ra cùng loại đầu ra là các tệp class, nhưng khác nhau về cách chọn compiler, cách sử dụng bộ nhớ, mức cô lập và yêu cầu môi trường.

Mặc định, task `javac` chạy compiler trong tiến trình Ant hiện tại. Khi đặt `fork="true"`, Ant gọi chương trình compiler bên ngoài, thường là executable `javac`, trong một tiến trình riêng. Chọn đúng chế độ giúp build phù hợp với JDK, tài nguyên máy và yêu cầu của CI.

## 1. Hai chế độ thực thi của task javac

### 1.1. Biên dịch trong JVM hiện tại: fork=false

Khi `fork` không được bật, Ant sử dụng compiler trong cùng JVM đang chạy Ant. Đây là chế độ mặc định của task `javac`.

Ví dụ:

~~~xml
<target name="compile">
    <mkdir dir="build/classes" />

    <javac srcdir="src/main/java"
           destdir="build/classes"
           fork="false"
           includeantruntime="false"
           encoding="UTF-8" />
</target>
~~~

Trong trường hợp này:

- Tiến trình Ant khởi động JVM.
- Task `javac` gọi compiler thông qua adapter mà Ant sử dụng.
- Compiler chạy trong cùng tiến trình và dùng chung không gian bộ nhớ của JVM đó.
- JVM và JDK cung cấp compiler cho Ant phải phù hợp với chế độ biên dịch được chọn.

Ưu điểm của chế độ này là không cần tạo một tiến trình compiler riêng cho mỗi lần gọi. Build thường có ít chi phí khởi chạy hơn và cấu hình đơn giản hơn. Đây là lựa chọn phù hợp cho dự án thông thường khi JDK chạy Ant đã cung cấp compiler mà dự án cần.

Hạn chế là compiler dùng chung tài nguyên JVM với Ant và các task khác. Bạn không thể cấp riêng heap cho compiler như khi chạy một tiến trình ngoài. Nếu compiler hoặc thư viện compiler gặp vấn đề về classloader, chúng cũng có thể ảnh hưởng đến tiến trình Ant.

### 1.2. Biên dịch trong tiến trình riêng: fork=true

Khi đặt `fork="true"`, Ant khởi chạy compiler bên ngoài thay vì chạy compiler trong JVM hiện tại:

~~~xml
<target name="compile">
    <mkdir dir="build/classes" />

    <javac srcdir="src/main/java"
           destdir="build/classes"
           fork="true"
           includeantruntime="false"
           encoding="UTF-8" />
</target>
~~~

Thông thường Ant sẽ tìm executable `javac` theo môi trường Java và `PATH`. Nếu cần chọn compiler cụ thể, có thể đặt thuộc tính `executable`:

~~~xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       fork="true"
       executable="/opt/jdk-17/bin/javac"
       includeantruntime="false" />
~~~

Đường dẫn trên là ví dụ cho Linux. Trên Windows, hãy dùng đường dẫn tới `javac.exe` của JDK đã chọn. Nếu không chỉ định `executable`, Ant sử dụng cách tìm compiler theo môi trường cài đặt.

Với chế độ fork:

- Ant vẫn chạy trong JVM ban đầu.
- Ant tạo tiến trình hệ điều hành mới để chạy compiler.
- Compiler sử dụng JVM và JDK tương ứng với executable được gọi.
- Tiến trình compiler có không gian bộ nhớ và vòng đời riêng.
- Ant chờ compiler kết thúc rồi xử lý mã thoát và kết quả.

Ưu điểm là có thể chọn JDK compiler khác với JDK đang chạy Ant, đặt giới hạn bộ nhớ riêng và cô lập một số vấn đề của compiler khỏi JVM Ant. Đổi lại, mỗi lần gọi phải khởi chạy tiến trình ngoài, cần executable compiler tồn tại và build phải xử lý khác biệt môi trường giữa các máy.

## 2. So sánh fork=false và fork=true

| Tiêu chí | fork=false | fork=true |
|---|---|---|
| Vị trí thực thi | Trong JVM đang chạy Ant | Trong tiến trình compiler riêng |
| Compiler | Được nạp và gọi trong JVM Ant | Được gọi qua executable bên ngoài |
| JDK compiler | Gắn với JDK/runtime cung cấp compiler cho Ant | Có thể chọn bằng executable hoặc môi trường PATH |
| Bộ nhớ | Dùng chung heap JVM Ant | Có thể cấu hình bộ nhớ cho compiler fork |
| Cách ly tiến trình | Compiler và Ant cùng tiến trình | Compiler có tiến trình riêng |
| Chi phí khởi chạy | Thấp hơn do không tạo compiler process riêng | Có thêm chi phí khởi chạy và kết thúc process |
| Tùy chỉnh executable | Không áp dụng theo cách fork | Có thể chỉ định executable |
| Phù hợp khi | Build thông thường, môi trường JDK thống nhất | Cần chọn JDK riêng, cấp bộ nhớ riêng hoặc cô lập compiler |

Không có chế độ nào luôn nhanh hơn trong mọi dự án. Thời gian thực tế phụ thuộc kích thước mã nguồn, số lần gọi javac, compiler, tốc độ ổ đĩa, cache và tài nguyên máy. Với build lớn, hãy đo trên cùng môi trường trước khi quyết định.

## 3. Quan hệ giữa JVM chạy Ant và JDK biên dịch

### 3.1. Khi không fork

Khi `fork=false`, compiler chạy trong JVM của Ant. Vì vậy, JDK dùng để khởi động Ant cũng quyết định compiler mà task có thể sử dụng.

Ví dụ:

~~~text
JAVA_HOME=/opt/jdk-17
ant compile
~~~

Nếu Ant được khởi động bằng JDK 17, task biên dịch trong JVM đó sử dụng compiler mà JDK 17 cung cấp. Bạn không thể chỉ đặt một đường dẫn `javac` khác ở `PATH` rồi mong chế độ in-process tự chuyển sang compiler của JDK đó.

Trên các hệ thống Java hiện đại, compiler được cung cấp bởi JDK, thường thông qua module compiler của JDK. Nếu Ant được chạy bằng một môi trường runtime không có compiler, task có thể không biên dịch được ở chế độ in-process. Cần bảo đảm Ant được khởi động bằng JDK đầy đủ phù hợp.

### 3.2. Khi fork

Khi `fork=true`, có thể chọn executable compiler khác với JDK chạy Ant:

~~~xml
<property name="javac.executable"
          value="/opt/jdk-21/bin/javac" />

<target name="compile">
    <javac srcdir="src/main/java"
           destdir="build/classes"
           fork="true"
           executable="${javac.executable}"
           includeantruntime="false" />
</target>
~~~

Ant có thể đang chạy bằng JDK 17, trong khi compiler bên ngoài là JDK 21. Khi đó, cần kiểm tra riêng:

- Phiên bản Java chạy Ant.
- Phiên bản executable compiler.
- Phiên bản Java mục tiêu mà ứng dụng cần hỗ trợ.
- Các tùy chọn compiler và API mà mã nguồn sử dụng.

Ví dụ kiểm tra executable đã chọn:

~~~text
/opt/jdk-21/bin/java -version
/opt/jdk-21/bin/javac -version
~~~

Trên Windows, có thể chạy:

~~~powershell
& "C:\Java\jdk-21\bin\java.exe" -version
& "C:\Java\jdk-21\bin\javac.exe" -version
~~~

Không nên chỉ nhìn kết quả `java -version` trong terminal để kết luận compiler fork đang dùng đúng JDK. Hãy kiểm tra trực tiếp executable mà task `javac` gọi.

### 3.3. Chọn phiên bản Java đầu ra

JDK dùng để biên dịch và phiên bản Java mục tiêu của ứng dụng là hai khái niệm khác nhau. Ví dụ, JDK 21 có thể tạo đầu ra tương thích với Java 17 nếu compiler và cấu hình hỗ trợ.

Với Ant và compiler hỗ trợ thuộc tính `release`, có thể dùng:

~~~xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       release="17"
       includeantruntime="false" />
~~~

Tùy chọn release giúp compiler kiểm soát mức ngôn ngữ, bytecode và API nền tảng theo phiên bản mục tiêu. Nếu dùng JDK 8, tùy chọn `--release` không có; khi đó phải dùng cấu hình source/target phù hợp và có biện pháp bảo đảm mã nguồn không gọi API chỉ xuất hiện ở JDK mới hơn.

Khi fork compiler sang một JDK khác, hãy kiểm tra phiên bản Ant có hỗ trợ thuộc tính compiler mà bạn muốn dùng và compiler executable thực tế có nhận tùy chọn đó hay không.

## 4. Điều khiển bộ nhớ cho compiler fork

### 4.1. Vì sao cần bộ nhớ riêng?

Khi compiler chạy trong JVM Ant, nó sử dụng heap của chính JVM đó. Nếu build có nhiều task và compiler cùng tiêu thụ nhiều bộ nhớ, có thể xảy ra lỗi thiếu heap trong tiến trình Ant.

Khi compiler được fork, Ant có thể truyền cấu hình bộ nhớ cho tiến trình compiler. Hai thuộc tính thường dùng là:

- `memoryInitialSize`: kích thước heap ban đầu của compiler fork.
- `memoryMaximumSize`: giới hạn heap tối đa của compiler fork.

Ví dụ:

~~~xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       fork="true"
       memoryInitialSize="128m"
       memoryMaximumSize="1024m"
       includeantruntime="false" />
~~~

Các giá trị trên là ví dụ. Hãy điều chỉnh theo kích thước dự án, bộ nhớ máy và số compiler process có thể chạy đồng thời. Các thuộc tính bộ nhớ này chỉ có ý nghĩa khi compiler được fork; chúng không đặt heap riêng cho compiler khi `fork=false`.

### 4.2. Không tăng heap một cách tùy tiện

Tăng memoryMaximumSize có thể giúp dự án lớn tránh lỗi OutOfMemoryError trong compiler process, nhưng cũng làm tăng lượng bộ nhớ tối đa mà tiến trình có thể sử dụng.

Nếu CI chạy nhiều job song song, mỗi job lại fork compiler với heap tối đa lớn, tổng nhu cầu bộ nhớ có thể vượt giới hạn máy hoặc container. Hãy tính cả số tiến trình đồng thời, bộ nhớ dành cho Ant, test runner và các service khác.

Khi gặp lỗi thiếu bộ nhớ, cần xác định lỗi xảy ra trong JVM Ant hay trong compiler fork:

- Nếu stack trace thuộc tiến trình Ant khi `fork=false`, xem cấu hình heap của JVM khởi chạy Ant.
- Nếu compiler process fork bị lỗi, xem memoryInitialSize/memoryMaximumSize và log của javac.
- Nếu CI bị kill vì vượt giới hạn container, kiểm tra giới hạn bộ nhớ thực tế và mức song song của pipeline.

## 5. Truyền tùy chọn cho compiler

### 5.1. Dùng compilerarg

Task javac cho phép truyền thêm tham số trực tiếp cho compiler bằng phần tử compilerarg:

~~~xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       fork="true"
       includeantruntime="false">
    <compilerarg value="-Xlint:deprecation" />
    <compilerarg value="-Xlint:unchecked" />
</javac>
~~~

Ví dụ này yêu cầu compiler hiển thị cảnh báo về API deprecated và thao tác generic không an toàn. Các tùy chọn được compiler hỗ trợ phụ thuộc phiên bản JDK.

Có thể truyền một chuỗi đối số hoặc nhiều phần tử compilerarg. Với giá trị chứa khoảng trắng, hãy dùng thuộc tính và cách quote phù hợp theo cú pháp Ant. Không ghép một chuỗi lệnh shell hoàn chỉnh vào compilerarg; Ant truyền các đối số cho compiler theo cấu trúc riêng.

### 5.2. Dùng compilerclasspath cho compiler adapter

Ant hỗ trợ các adapter để làm việc với những compiler khác nhau. Thuộc tính `compilerclasspath` liên quan tới classpath dùng để nạp triển khai compiler adapter trong môi trường Ant. Nó khác với phần tử `classpath` bên trong javac dùng cho mã nguồn ứng dụng.

Phân biệt:

| Cấu hình | Mục đích |
|---|---|
| `<classpath>` bên trong `<javac>` | Dependency mà mã nguồn đang biên dịch cần tham chiếu |
| `compilerclasspath` | Lớp và thư viện cần để Ant nạp compiler adapter trong chế độ phù hợp |
| `executable` | Chương trình compiler bên ngoài khi fork |
| `<compilerarg>` | Tham số bổ sung truyền cho compiler |

Không đưa thư viện ứng dụng vào compilerclasspath chỉ vì mã nguồn cần nó; hãy dùng phần tử classpath dành cho javac. Tương tự, compilerclasspath không phải là classpath của ứng dụng khi chạy.

## 6. Ví dụ build.xml hỗ trợ chọn chế độ fork

Có thể dùng một property để chọn chế độ biên dịch theo môi trường:

~~~xml
<project name="compile-modes" default="compile" basedir=".">

    <property name="src.dir" location="${basedir}/src/main/java" />
    <property name="classes.dir" location="${basedir}/build/classes" />

    <!-- Mặc định dùng compiler trong JVM Ant. -->
    <property name="compile.fork" value="false" />

    <path id="compile.classpath">
        <fileset dir="${basedir}/lib" includes="*.jar" />
    </path>

    <target name="prepare">
        <mkdir dir="${classes.dir}" />
    </target>

    <target name="compile" depends="prepare">
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               fork="${compile.fork}"
               includeantruntime="false"
               encoding="UTF-8">
            <classpath refid="compile.classpath" />
            <compilerarg value="-Xlint:deprecation" />
        </javac>
    </target>

</project>
~~~

Mặc định, chạy:

~~~text
ant compile
~~~

sẽ dùng chế độ in-process vì compile.fork có giá trị false.

Muốn fork compiler:

~~~text
ant -Dcompile.fork=true compile
~~~

Nếu cần chọn compiler cụ thể, có thể thêm property executable vào build file hoặc cấu hình riêng theo môi trường:

~~~xml
<property name="javac.executable" value="javac" />

<target name="compile-forked" depends="prepare">
    <javac srcdir="${src.dir}"
           destdir="${classes.dir}"
           fork="true"
           executable="${javac.executable}"
           memoryMaximumSize="1024m"
           includeantruntime="false">
        <classpath refid="compile.classpath" />
    </javac>
</target>
~~~

Có thể gọi target forked bằng:

~~~text
ant -Djavac.executable=/opt/jdk-21/bin/javac compile-forked
~~~

Trên Windows, truyền đường dẫn tới `javac.exe` theo cú pháp shell đang sử dụng. Nếu executable chỉ là `javac`, tiến trình cần tìm được nó qua `PATH`.

Ví dụ build file này giả định thư mục lib và mã nguồn tồn tại. Nếu thư mục lib có thể không tồn tại, hãy điều chỉnh fileset hoặc tạo thư mục đó trước khi chạy build.

## 7. Khi nào nên chọn fork=false?

Chọn in-process khi:

- Ant được khởi chạy bằng JDK đầy đủ và compiler tương ứng đáp ứng yêu cầu dự án.
- Build không cần chọn một executable javac khác.
- Kích thước mã nguồn và mức sử dụng bộ nhớ phù hợp với JVM Ant.
- Muốn giảm chi phí tạo tiến trình compiler riêng.
- Không gặp xung đột giữa compiler, compiler adapter và các thư viện được nạp trong JVM Ant.

Đây là lựa chọn hợp lý cho phần lớn build Java đơn giản. Nó giữ cấu hình ngắn gọn và giúp JDK chạy Ant cũng là JDK biên dịch, giảm nguy cơ vô tình dùng hai phiên bản Java khác nhau.

Nếu CI hoặc IDE khởi chạy Ant bằng JDK riêng, cần bảo đảm JDK đó đúng với yêu cầu compiler. Không nên giả định JDK của dự án được chọn trong IDE luôn là JDK chạy Ant.

## 8. Khi nào nên chọn fork=true?

Chọn fork khi có một lý do kỹ thuật rõ ràng:

- Cần biên dịch bằng JDK khác với JDK chạy Ant.
- Cần chỉ định chính xác executable compiler.
- Cần cấp heap riêng cho compiler.
- Compiler hoặc adapter gây xung đột classloader trong JVM Ant.
- Muốn cô lập lỗi hoặc trạng thái nội bộ của compiler khỏi tiến trình Ant.
- Cần thử nghiệm nhiều phiên bản compiler trên cùng một máy build.

Ví dụ dự án cần chạy Ant bằng JDK 17 nhưng kiểm chứng khả năng biên dịch với JDK 21. Có thể dùng fork và executable chỉ tới JDK 21. Tuy nhiên, phải kiểm tra cả phiên bản Java mục tiêu và các dependency của dự án để kết quả có ý nghĩa.

Không nên bật fork chỉ vì thấy đây là lựa chọn “mạnh hơn”. Fork thêm chi phí process và có thể làm cấu hình CI phức tạp hơn. Nếu không cần JDK riêng, bộ nhớ riêng hoặc cô lập compiler, chế độ mặc định thường đã đủ.

## 9. Những khác biệt cần chú ý trong CI và IDE

### 9.1. JAVA_HOME và PATH

Khi fork, Ant cần tìm đúng executable compiler. Nếu `JAVA_HOME` và `PATH` trỏ tới hai JDK khác nhau, kết quả có thể không giống dự kiến.

Kiểm tra môi trường trên Linux/macOS:

~~~bash
echo "$JAVA_HOME"
command -v java
command -v javac
java -version
javac -version
~~~

Trên PowerShell:

~~~powershell
$env:JAVA_HOME
Get-Command java
Get-Command javac
java -version
javac -version
~~~

Nếu build dùng thuộc tính executable, hãy kiểm tra chính đường dẫn đó. Kết quả của `command -v javac` hoặc `Get-Command javac` chỉ cho biết lệnh được shell tìm thấy, không chứng minh task Ant đang dùng cùng executable nếu nó được cấu hình riêng.

### 9.2. IDE có thể chạy Ant bằng JDK khác

Một IDE có thể có nhiều lựa chọn Java:

- JDK dùng để chạy chính IDE.
- JDK dùng cho project.
- JDK dùng cho Ant runner.
- JDK compiler được chỉ định qua executable khi fork.

Khi build trong terminal thành công nhưng trong IDE thất bại, hãy kiểm tra JDK của Ant runner và cấu hình fork. Khi build trong IDE thành công nhưng CI thất bại, kiểm tra môi trường JDK của runner CI và PATH.

### 9.3. CI chạy song song

Nếu nhiều target hoặc job cùng fork compiler, mỗi tiến trình có thể tiêu thụ thêm bộ nhớ và tài nguyên CPU. Cần cân nhắc số lượng tiến trình đồng thời, heap mỗi tiến trình và giới hạn container. Không đặt memoryMaximumSize quá cao nếu nhiều job có thể chạy đồng thời trên một runner.

## 10. Các lỗi thường gặp và cách xử lý

| Biểu hiện | Nguyên nhân có thể xảy ra | Hướng xử lý |
|---|---|---|
| In-process không tìm thấy compiler | Ant chạy bằng runtime không có compiler hoặc JDK không phù hợp | Khởi chạy Ant bằng JDK đầy đủ; kiểm tra JDK đang chạy Ant |
| Fork báo không tìm thấy javac | Executable không có trong PATH hoặc đường dẫn executable sai | Đặt PATH đúng hoặc chỉ định executable tới javac của JDK |
| Terminal và CI dùng phiên bản javac khác nhau | JAVA_HOME/PATH hoặc cấu hình executable không thống nhất | In phiên bản compiler và kiểm tra đường dẫn thực tế trong mỗi môi trường |
| In-process bị OutOfMemoryError | Compiler và Ant dùng chung heap JVM | Điều chỉnh heap của JVM chạy Ant hoặc cân nhắc fork |
| Compiler fork bị thiếu bộ nhớ | Heap cấp cho compiler fork quá thấp hoặc có nhiều tiến trình đồng thời | Điều chỉnh memoryInitialSize/memoryMaximumSize và mức song song |
| Tham số compiler không được nhận | Tùy chọn không được JDK hiện tại hỗ trợ hoặc truyền sai | Kiểm tra javac -version và cú pháp compilerarg |
| Mã nguồn biên dịch bằng JDK mới nhưng chạy trên JDK cũ bị lỗi | Phiên bản bytecode hoặc API vượt quá runtime mục tiêu | Dùng release phù hợp và kiểm tra trên đúng runtime |
| Classpath có thư viện Ant ngoài dự kiến | includeantruntime đang bật | Đặt includeantruntime="false" và khai báo dependency ứng dụng riêng |
| Fork chậm hơn dự kiến | Chi phí khởi chạy process, nhiều lần gọi javac hoặc I/O lớn | Đo thời gian, gom compile target hợp lý và chỉ fork khi cần |
| Máy local build được nhưng IDE không build được | IDE chạy Ant với JDK khác | Kiểm tra cấu hình Ant runner và JDK project |

Khi điều tra, hãy thu thập cả phiên bản Ant, JDK chạy Ant và compiler executable. Đừng chỉ thay đổi fork rồi kết luận lỗi đã được giải quyết; xác định đúng tiến trình nào đang thiếu compiler, thiếu bộ nhớ hoặc dùng sai phiên bản Java.

## 11. Checklist chọn chế độ biên dịch

Trước khi cấu hình task javac, hãy xác định:

- JDK nào đang chạy Ant?
- JDK đó có compiler cần thiết cho chế độ in-process không?
- Dự án có cần một compiler executable khác không?
- Nếu fork, executable nào sẽ được gọi?
- Phiên bản Java mục tiêu của ứng dụng là bao nhiêu?
- Có cần cấp bộ nhớ riêng cho compiler fork không?
- Compiler có cần tham số bổ sung qua compilerarg không?
- Classpath ứng dụng đã được tách khỏi thư viện Ant chưa?
- IDE và CI có dùng cùng cấu hình JDK/compiler không?
- Khi fork nhiều job, giới hạn bộ nhớ và CPU có đủ không?

Nếu mọi câu trả lời đều phù hợp với JDK đang chạy Ant, dùng mặc định `fork=false` thường là đủ. Nếu cần chọn compiler riêng, heap riêng hoặc cách ly tiến trình, cấu hình `fork=true` và xác định executable một cách rõ ràng.

## 12. Nguyên tắc duy trì

- Hiểu rằng `fork=false` là chế độ mặc định và compiler chạy trong JVM Ant.
- Dùng `fork=true` khi cần compiler process riêng.
- Dùng `executable` để chỉ định compiler cụ thể khi fork.
- Chỉ dùng `memoryInitialSize` và `memoryMaximumSize` cho compiler fork.
- Dùng `compilerarg` cho tham số của javac, không nhầm với classpath dependency của mã nguồn.
- Giữ `includeantruntime="false"` cho ứng dụng thông thường và khai báo dependency rõ ràng.
- Kiểm tra phiên bản JDK thực tế, đặc biệt trong IDE và CI.
- Chọn `release` hoặc cấu hình source/target phù hợp với runtime mục tiêu.
- Đo hiệu năng và bộ nhớ trên môi trường thực tế trước khi đổi chế độ cho toàn dự án.

Việc chọn giữa biên dịch trong JVM hiện tại và fork compiler là quyết định về môi trường thực thi, tài nguyên và khả năng kiểm soát JDK. Khi hiểu rõ tiến trình nào chạy compiler, executable nào được sử dụng và classpath nào phục vụ mã nguồn, build Ant sẽ dễ dự đoán hơn trên máy phát triển lẫn CI.

