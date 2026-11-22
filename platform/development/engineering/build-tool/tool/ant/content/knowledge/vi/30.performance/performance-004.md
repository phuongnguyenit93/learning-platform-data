# Cân bằng chi phí fork JVM với nhu cầu cô lập tiến trình

Trong **Apache Ant**, một tác vụ Java có thể chạy ngay bên trong máy ảo Java (JVM) đang chạy Ant hoặc chạy trong **JVM con** được tạo bằng cơ chế *fork*. Fork giúp tách lỗi và trạng thái của tác vụ khỏi tiến trình build, đồng thời cho phép cấu hình riêng bộ nhớ và tham số JVM. Đổi lại, mỗi lần tạo tiến trình phát sinh chi phí khởi động, nạp lớp, chuẩn bị môi trường và tài nguyên hệ điều hành.

Ở chủ đề **Hiệu năng**, lựa chọn phù hợp không đơn thuần là “fork hay không fork”, mà là trả lời ba câu hỏi:

1. Tác vụ có thực sự cần ranh giới tiến trình để bảo vệ build, giới hạn tài nguyên hoặc ngăn trạng thái rò rỉ không?
2. Chi phí khởi tạo một JVM mới chiếm bao nhiêu trong thời gian thực thi công việc?
3. Có thể **giảm số lần fork** bằng cách gộp công việc, tái sử dụng tiến trình một cách có kiểm soát hoặc đổi phạm vi cô lập không?

Bài này tập trung vào các tác vụ Ant như `<java>`, `<javac>` và `<junit>`, nơi lựa chọn tiến trình có ảnh hưởng trực tiếp tới tốc độ và độ tin cậy của build.

## 1. Fork JVM nghĩa là gì trong Ant?

Khi chạy `ant build`, một tiến trình JVM đã tồn tại để phân tích `build.xml` và điều phối các target. Một task Java có thể thực thi theo hai mô hình:

~~~mermaid
flowchart TB
    A["Tiến trình JVM của Ant"] --> T["Target trong build.xml"]
    T --> B{"Cách chạy Java?"}
    B -->|"fork=false"| C["Thực thi trong JVM của Ant"]
    B -->|"fork=true"| D["Tạo tiến trình JVM con"]
    D --> E["Thực thi công việc trong JVM con"]
    C --> F["Trả trạng thái về Ant"]
    E --> F
~~~

### Chạy trong cùng JVM — `fork="false"`

Ant gọi mã Java trong tiến trình của chính nó. Phương án này thường tránh được chi phí tạo tiến trình mới, nhưng tác vụ và Ant vẫn dùng chung những tài nguyên ở cấp JVM như heap, system properties, một số singleton/static state, thread và native library đã nạp. Classloader có thể tạo một mức phân tách tên lớp nhưng **không tạo ranh giới tiến trình**.

Một tác vụ có lỗi quản lý bộ nhớ, tạo thread không dừng hoặc thay đổi trạng thái toàn JVM có thể ảnh hưởng tới tác vụ khác. Tác vụ gọi `System.exit(...)` cũng không phù hợp với môi trường chạy bên trong Ant: nó có nguy cơ kết thúc luôn tiến trình build.

### Chạy trong JVM con — `fork="true"`

Ant tạo một hệ điều hành process mới để chạy Java. JVM con có heap, classloader, system properties và vòng đời riêng. Khi nó kết thúc, bộ nhớ cùng trạng thái trong process được giải phóng; Ant có thể tiếp tục hoặc báo lỗi dựa trên exit code.

Tuy nhiên, JVM con vẫn thường chạy với **cùng quyền của tài khoản hệ điều hành** như Ant, có thể đọc cùng file và truy cập cùng mạng nếu được phép. Fork **không phải cơ chế sandbox bảo mật** và không bảo đảm mọi subprocess do JVM con tạo ra đều được dọn sạch.

| Tiêu chí | Cùng JVM với Ant | JVM con |
|---|---|---|
| Khởi động | Không tạo process/JVM mới | Tạo process, khởi động JVM, nạp class |
| Heap và GC | Dùng chung với Ant | Heap và GC riêng |
| Static/singleton, system properties | Có nguy cơ tác động tới tiến trình build | Cách ly phần lớn trạng thái trong process con |
| `-Xmx`, JVM flags riêng | Không thể cấp một bộ cờ JVM độc lập cho riêng task | Có thể cấu hình bằng `<jvmarg>` và thuộc tính phù hợp |
| Lỗi làm JVM dừng | Có nguy cơ làm dừng Ant | Thông thường chỉ làm dừng process con |
| Timeout/working directory riêng | Khả năng hạn chế, tùy task | Có thể kiểm soát ở cấp process |
| Bộ nhớ đỉnh | Không thêm heap con nhưng có thể làm phình heap Ant | Ant và child JVM có thể cùng chiếm RAM |
| Phù hợp | Công việc ngắn, tin cậy, ít tác động trạng thái | Code không tin cậy về độ ổn định, tool cần bộ nhớ/cờ riêng, test cần cô lập |

## 2. Chi phí của mỗi lần fork đến từ đâu?

Một lần gọi JVM con thường trải qua các giai đoạn:

1. Hệ điều hành tạo process và chuẩn bị môi trường, file descriptor/handle, working directory.
2. JVM khởi động, đọc cấu hình, thiết lập heap, GC và runtime.
3. JVM nạp class, khởi tạo framework, dependency và dữ liệu cần thiết.
4. Tác vụ xử lý dữ liệu thực tế, có thể được JIT tối ưu khi chạy đủ lâu.
5. Process kết thúc, Ant nhận exit code và thu thập stdout/stderr.

Một mô hình gần đúng:

\[
T_{\text{tổng}} \approx N \times (T_{\text{tạo process}} + T_{\text{khởi động JVM}} + T_{\text{khởi tạo ứng dụng}}) + \sum_{i=1}^{N} T_{\text{xử lý},i} + T_{\text{I/O}}
\]

Trong đó `N` là **số lần fork**, không phải số file đầu vào. Con số thực tế phụ thuộc CPU, hệ điều hành, JDK, lượng class cần nạp, cache đĩa, framework và tải của máy; không có mức chi phí vài mili-giây hay vài giây cố định đúng cho mọi dự án.

Ví dụ giả định để thấy tác động về nguyên lý:

| Cách tổ chức | Số dữ liệu | Số JVM con | Chi phí khởi tạo nếu mỗi JVM tốn giả định 0,4 giây |
|---|---:|---:|---:|
| Mỗi file gọi một lần `<java fork="true">` | 200 file | 200 | 80 giây |
| Một lần fork xử lý 20 file | 200 file | 10 | 4 giây |
| Một lần fork xử lý toàn bộ batch | 200 file | 1 | 0,4 giây |

Các số trong bảng là **giả định để minh họa phép nhân**, không phải kết quả benchmark của Ant. Gộp tác vụ giảm chi phí khởi động nhưng làm tăng lượng công việc và trạng thái được giữ trong một child JVM. Để quyết định, cần đo tổng thời gian thật, CPU, bộ nhớ đỉnh và độ ổn định với khối lượng tương ứng.

### Bộ nhớ không đơn giản là “fork giúp tiết kiệm RAM”

Khi `fork="false"`, tác vụ dùng heap và metaspace trong JVM của Ant. Khi `fork="true"`, child JVM cần heap và runtime riêng, **đồng thời** Ant vẫn tồn tại.

Vì vậy, bộ nhớ đỉnh gần đúng của một child:

\[
M_{\text{đỉnh}} \approx M_{\text{Ant}} + M_{\text{JVM con}} + M_{\text{bộ nhớ native/OS}}
\]

Nếu chạy `P` child song song:

\[
M_{\text{đỉnh}} \approx M_{\text{Ant}} + \sum_{i=1}^{P} M_{\text{JVM con},i} + M_{\text{khác}}
\]

`-Xmx` chỉ giới hạn phần heap Java của JVM tương ứng; tổng RSS còn gồm metaspace, thread stacks, code cache, direct buffers và thư viện native. Do đó cấu hình bốn process với mỗi process `-Xmx1g` không có nghĩa tổng RAM tối đa chính xác là 4 GiB.

## 3. Chọn chạy cùng JVM cho tác vụ nhỏ, đã kiểm soát

Giả sử một ứng dụng Ant có tác vụ Java kiểm tra cấu trúc dữ liệu đầu vào và trả về bình thường, không gọi `System.exit`, không sửa system properties toàn cục và không giữ thread sau khi kết thúc.

Một đoạn `build.xml` minh họa:

~~~xml
<project name="fork-demo" default="validate" basedir=".">
    <property name="classes.dir" location="build/classes"/>

    <path id="app.runtime.classpath">
        <pathelement location="${classes.dir}"/>
    </path>

    <target name="validate">
        <java classname="com.example.build.ValidateInputs"
              fork="false"
              failonerror="true">
            <classpath refid="app.runtime.classpath"/>
            <arg file="input/catalog.json"/>
        </java>
    </target>
</project>
~~~

Khi chạy `ant validate`, Ant không cần tạo thêm một JVM cho `ValidateInputs`. Lựa chọn này phù hợp khi chi phí thực thi chính rất nhỏ so với overhead của process mới, và code có hành vi rõ ràng với JVM của Ant.

Cần hiểu giới hạn:

- Classloader có thể cô lập một phần class của chương trình, nhưng không tách heap, GC hay trạng thái cấp process.
- Task không có môi trường JVM riêng để tùy ý thay đổi `-Xmx`, `-javaagent`, `--add-opens` và những cờ khởi động khác.
- Không nên trông chờ vào việc dùng `dir`, `timeout` hoặc `<jvmarg>` như khi chạy JVM con; với Ant `<java>`, các chức năng liên quan process có giới hạn hoặc chỉ có ý nghĩa khi fork.
- Mã không được viết cho môi trường nhúng, đặc biệt mã gọi `System.exit`, có thể khiến build khó kiểm soát.
- Tác vụ trước để lại static state, thread hoặc tài nguyên chưa đóng có thể ảnh hưởng tới tác vụ sau.

**Phân biệt “tin cậy” với “mã của đội mình”:** code tự viết vẫn có thể làm rò trạng thái hoặc giữ thread. Quyết định dựa trên hành vi quan sát được, không dựa trên tác giả.

## 4. Fork khi cần cô lập process, bộ nhớ hoặc vòng đời

Với công cụ tạo mã, xử lý dữ liệu lớn hoặc chạy chương trình có thể thay đổi trạng thái JVM, dùng `fork="true"`:

~~~xml
<project name="fork-demo" default="generate" basedir=".">
    <property name="classes.dir" location="build/classes"/>
    <property name="generated.dir" location="build/generated"/>

    <!-- Được bootstrap từ JDK đã khóa phiên bản -->
    <property name="jdk.java.executable"
              location=".toolchains/jdk/bin/java"/>

    <path id="app.runtime.classpath">
        <pathelement location="${classes.dir}"/>
        <!-- Bổ sung các JAR đã khóa phiên bản nếu công cụ cần. -->
    </path>

    <target name="generate">
        <mkdir dir="${generated.dir}"/>

        <java classname="com.example.tools.BatchGenerator"
              fork="true"
              jvm="${jdk.java.executable}"
              maxmemory="512m"
              timeout="120000"
              failonerror="true"
              dir="${basedir}">
            <classpath refid="app.runtime.classpath"/>
            <jvmarg value="-Dfile.encoding=UTF-8"/>
            <arg file="input/schemas"/>
            <arg file="${generated.dir}"/>
        </java>
    </target>
</project>
~~~

Ý nghĩa của các cấu hình:

| Thuộc tính | Tác dụng khi fork |
|---|---|
| `fork="true"` | Yêu cầu Ant khởi động JVM con |
| `jvm="..."` | Chỉ định chính xác executable Java, tránh phụ thuộc `PATH` |
| `maxmemory="512m"` | Thiết lập giới hạn heap tối đa cho JVM con (tương ứng cờ `-Xmx`) |
| `<jvmarg>` | Truyền cờ cho JVM con; ví dụ encoding, GC, module access |
| `timeout="120000"` | Đặt thời hạn chờ task theo mili-giây; quá hạn Ant xử lý kết thúc process theo hỗ trợ của task |
| `failonerror="true"` | Build thất bại khi tác vụ trả về mã lỗi thay vì im lặng tiếp tục |
| `dir="..."` | Xác định working directory của tiến trình con |
| `<classpath>` | Khai báo classpath của ứng dụng được khởi chạy |

Ví dụ giả định `BatchGenerator` là chương trình có `main(String[] args)` xử lý cả thư mục input. Tên lớp và đường dẫn cần thay bằng công cụ của dự án. Với Windows, executable có thể là `java.exe` trong bộ JDK tương ứng.

Một số điểm vận hành quan trọng:

- Thư mục JDK trong `jvm` phải tồn tại và được quản lý bằng manifest version/checksum. JVM chạy Ant và JVM con **có thể là hai bộ JDK khác nhau**, nên phải xác minh cả hai khi sự khác biệt có ý nghĩa.
- Cấu hình heap không làm tăng RAM có sẵn trên máy. Nếu vượt giới hạn, JVM con có thể ném `OutOfMemoryError`; Ant cần được cấu hình để thấy exit code thất bại.
- Việc đặt `timeout` giúp phát hiện task bị treo nhưng không bảo đảm dọn được mọi tiến trình con/cháu do công cụ tự spawn.
- Fork làm giảm tác động của crash ở cấp JVM, nhưng mọi tác động lên file, database, mạng hoặc môi trường bên ngoài vẫn có thể xảy ra.
- Không ghi credential vào `<jvmarg>` hoặc câu lệnh hiển thị công khai trong log; nếu cần bí mật, dùng cơ chế cấp phát an toàn của môi trường chạy.

### Không nhầm `fork` với `spawn`

Trong task `<java>`, `spawn="true"` yêu cầu chạy tiến trình theo kiểu tách khỏi luồng chờ thông thường. Đây **không phải** giải pháp cải thiện hiệu năng cho công việc mà build cần kết quả trước khi sang target tiếp theo: Ant không còn có thể điều phối kết thúc, thời gian chạy và exit status như một child được chờ bình thường. Khi build cần kiểm tra đầu ra hoặc fail nếu chương trình lỗi, dùng `fork="true"` với cơ chế chờ/kiểm soát exit code.

## 5. Giảm số lần fork trước khi tối ưu các cờ JVM

Trong nhiều dự án, chi phí lớn nhất không nằm ở việc một child JVM khởi động chậm, mà ở chỗ target chạy **một JVM cho mỗi file**.

Ví dụ cách tổ chức kém hiệu quả:

~~~text
200 schema
  ├── java -jar generator.jar schema-001.json
  ├── java -jar generator.jar schema-002.json
  ├── ...
  └── java -jar generator.jar schema-200.json
= 200 lần tạo JVM + 200 lần khởi tạo generator
~~~

Nếu generator hỗ trợ xử lý danh sách file hoặc cả thư mục:

~~~text
200 schema
  └── java -jar generator.jar --input-dir input/schemas
      = 1 lần tạo JVM + 1 lần khởi tạo generator + xử lý 200 schema
~~~

Đó là **amortization**: chi phí setup được phân bổ cho nhiều đơn vị công việc. Cách áp dụng trong Ant:

1. Ưu tiên API hoặc chế độ batch của công cụ nếu nó được hỗ trợ chính thức.
2. Truyền input theo file danh sách, thư mục hoặc response file khi CLI hỗ trợ, thay vì lặp `<java>` cho từng tệp.
3. Nếu công cụ nặng nhưng không có batch mode, cân nhắc viết wrapper Java có vòng lặp xử lý trong một process, với điều kiện API hỗ trợ tái sử dụng an toàn.
4. Giới hạn số tác vụ trong mỗi batch khi có rủi ro rò bộ nhớ hoặc giữ trạng thái giữa các input.
5. Không tự gộp các bài test hoặc tác vụ vốn yêu cầu ranh giới process riêng để bảo đảm đúng chức năng.

Một child JVM dùng lại lâu có thể giảm startup nhưng cũng tích lũy cache, static state và heap pressure. Vì thế điểm tối ưu có thể là **một JVM cho một nhóm công việc**, thay vì “một JVM cho tất cả” hoặc “một JVM cho từng file”.

## 6. Với `<javac>`, cân bằng tốc độ biên dịch và bộ nhớ riêng

Task `<javac>` là trường hợp đặc biệt: Ant có thể dùng compiler trong process hoặc gọi compiler ngoài. Nhiều build tận dụng cách biên dịch trong JVM hiện tại để tránh overhead; nhưng với project lớn hoặc compiler/tool/plugin có hành vi riêng, fork có thể giúp tách heap và vòng đời.

**Biên dịch trong process Ant**:

~~~xml
<target name="compile" depends="init">
    <javac srcdir="src/main/java"
           destdir="build/classes"
           includeantruntime="false"
           encoding="UTF-8"
           release="17"
           fork="false"/>
</target>
~~~

**Gọi compiler ngoài process**:

~~~xml
<target name="compile-isolated" depends="init">
    <javac srcdir="src/main/java"
           destdir="build/classes"
           includeantruntime="false"
           encoding="UTF-8"
           release="17"
           fork="true"
           executable="${pinned.jdk.home}/bin/javac"
           memoryMaximumSize="1g"/>
</target>
~~~

Đây là hai phương án thay thế trong cùng một dự án, không phải hai bước bắt buộc chạy liên tiếp. Target `init` và property `pinned.jdk.home` do dự án định nghĩa; target không tự chứa để minh họa trọng tâm cấu hình compiler. Trên Windows, thay `javac` bằng executable thực tế của bộ JDK.

Điểm cần nhớ:

- `fork="false"` thường giảm chi phí tạo process và có thể phù hợp với biên dịch gia tăng nhỏ.
- `fork="true"` cho compiler process riêng và cấu hình bộ nhớ riêng; thuộc tính như `memoryMaximumSize` có ý nghĩa trong mô hình compiler được fork.
- Biên dịch nhiều file trong **một lần gọi `<javac>`** thường tốt hơn tạo nhiều target mỗi target compile một file.
- Nếu compiler/JDK fork khác compiler của Ant, cần cố định đường dẫn và phiên bản, đồng thời dùng release/source/target nhất quán.
- Fork compiler không bảo đảm build incremental tối ưu; phạm vi file biên dịch, timestamp và dependency vẫn chi phối số lượng công việc.

Không thay `fork="false"` bằng `fork="true"` cho mọi dự án chỉ vì muốn tránh memory pressure: khi cả Ant và compiler chạy đồng thời, tổng RAM có thể tăng. Quyết định cần dựa vào số lượng source, bộ nhớ và phép đo build sạch/build gia tăng.

## 7. Với kiểm thử, cô lập đúng cấp độ

Bài test thường dùng static state, system properties, locale/timezone, thread, file tạm hoặc thư viện native. Những trạng thái này có thể ảnh hưởng tới bài test chạy sau. Fork ở cấp test giúp tránh tác động lên tiến trình Ant, nhưng **mức độ cô lập giữa các test** phụ thuộc cách cấu hình.

Với task `<junit>` cổ điển của Ant (dành cho bài test JUnit tương thích với task này), thuộc tính `fork="yes"` yêu cầu chạy test trong JVM con. Thuộc tính `forkmode` điều khiển mức độ tái sử dụng JVM:

| Chế độ `forkmode` | Ý tưởng | Cân bằng |
|---|---|---|
| `perTest` | Có thể fork riêng theo mỗi lớp test | Cô lập tốt hơn giữa các test, nhưng chi phí startup lớn |
| `perBatch` | Fork theo mỗi batch của `<batchtest>` | Giảm số process, cô lập theo nhóm |
| `once` | Cố gắng dùng một JVM con cho các test tương thích | Ít startup nhất, nhưng test cùng process có thể rò trạng thái sang nhau |

Ví dụ chạy batch test trong child JVM, sử dụng task `<junit>` cổ điển:

~~~xml
<target name="test" depends="compile-tests">
    <mkdir dir="build/test-reports"/>

    <junit fork="yes"
           forkmode="once"
           haltonfailure="yes"
           printsummary="yes">
        <classpath>
            <pathelement location="build/classes"/>
            <pathelement location="build/test-classes"/>
            <fileset dir="vendor/test-lib" includes="*.jar"/>
        </classpath>

        <formatter type="xml"/>

        <batchtest todir="build/test-reports">
            <fileset dir="build/test-classes">
                <include name="**/*Test.class"/>
            </fileset>
        </batchtest>
    </junit>
</target>
~~~

Ví dụ giả định các test tương thích với `<junit>` và JAR cần thiết đã có ở `vendor/test-lib`. Các thuộc tính và cơ chế fork của Ant `<junit>` không tự động áp dụng cho mọi engine của JUnit Platform hoặc plugin bên ngoài; nếu dự án dùng `<junitlauncher>`, cần cấu hình cách fork theo API của task đó.

Lưu ý quan trọng: `forkmode="once"` **không có nghĩa mỗi test được cô lập riêng**. Test cùng child JVM vẫn chia sẻ system properties, static state, thread và một số tài nguyên. Ant cũng có thể cần chia nhóm process nếu test có cấu hình JVM khác nhau. Khi cần độ độc lập tuyệt đối giữa các lớp test có side effect, xem xét `perTest` hoặc nhóm nhỏ thích hợp, dù chi phí sẽ tăng.

### Chọn theo đặc tính kiểm thử

- **Unit test ngắn, ít side effect:** ít process hoặc chia nhóm có thể giảm đáng kể startup.
- **Integration test chạm tới static global, native code hoặc thread phức tạp:** ưu tiên child JVM với phạm vi cô lập phù hợp.
- **Test có thể gọi `System.exit` hoặc làm JVM crash:** cần process riêng để bảo vệ Ant.
- **Test thay đổi dữ liệu ngoài process** (database, filesystem dùng chung, dịch vụ mạng): fork JVM **không tự cô lập** dữ liệu đó; cần môi trường test riêng, setup/teardown hoặc cơ chế đồng bộ.

Việc dùng nhiều child JVM đồng thời có thể làm tổng thời gian ngắn hơn nếu máy đủ tài nguyên, nhưng có nguy cơ tranh chấp CPU, RAM, ổ đĩa hoặc cổng mạng. Vì vậy số process chạy song song là một tham số hiệu năng cần đo, không nên mở vô hạn.

## 8. Chọn phạm vi fork theo rủi ro và chi phí

Một bảng quyết định thực hành:

| Loại công việc | Nhu cầu cô lập | Lựa chọn thường bắt đầu thử |
|---|---|---|
| Kiểm tra dữ liệu nhỏ bằng code tin cậy, không sửa global state | Thấp | Chạy trong JVM Ant nếu task hỗ trợ |
| Công cụ Java chạy vài giây/phút và phải có `-Xmx` riêng | Trung bình/cao | Fork một process cho một batch |
| Generator xử lý hàng trăm file, API hỗ trợ batch | Trung bình | Một child JVM cho nhóm file hợp lý |
| Compiler Java thông thường cho dự án nhỏ | Thấp/trung bình | Thử `<javac fork="false">` |
| Compiler rất nặng hoặc plugin compiler gây vấn đề với Ant JVM | Cao | Thử `<javac fork="true">` với JDK/memory được khóa |
| Unit test nhiều, ít side effect | Thấp/trung bình | Tái sử dụng JVM test theo batch/chế độ phù hợp |
| Test có trạng thái toàn JVM, native crash hoặc `System.exit` | Cao | Mỗi test hoặc mỗi nhóm rủi ro một JVM con |
| Công cụ không phải Java được gọi bằng `<exec>` | Theo đặc tính tool | Đã chạy process ngoài; quản lý version, timeout và exit status |

Bảng là gợi ý **để hình thành giả thuyết benchmark**, không phải quy tắc rằng mọi task thuộc một loại phải cấu hình giống nhau.

### Cây quyết định

~~~mermaid
flowchart TD
    A["Task dùng Java trong build Ant"] --> B{"Cần JVM flags/heap riêng, bảo vệ khỏi exit/crash, hoặc cô lập state?"}
    B -->|Không| C["Thử chạy trong JVM Ant"]
    B -->|Có| D["Fork JVM con"]
    D --> E{"Task có nhiều đơn vị công việc ngắn?"}
    E -->|Có| F{"Có thể batch mà không sai hành vi?"}
    F -->|Có| G["Gộp nhiều input vào mỗi JVM con"]
    F -->|Không| H["Dùng process riêng theo ranh giới cần thiết"]
    E -->|Không| H
    C --> I["Đo thời gian, RAM và độ tin cậy"]
    G --> I
    H --> I
    I --> J{"Đạt mục tiêu build?"}
    J -->|Không| K["Điều chỉnh batch size, mức fork hoặc giới hạn song song"]
    K --> I
    J -->|Có| L["Chốt cấu hình và giám sát"]
~~~

## 9. Đo hiệu năng đúng cách trước khi quyết định

Có thể so sánh các cấu hình trên cùng workload:

- **Phương án A:** chạy trong JVM của Ant nếu an toàn và được task hỗ trợ.
- **Phương án B:** fork từng đơn vị công việc hoặc từng test.
- **Phương án C:** fork theo batch hoặc tái sử dụng JVM con với ranh giới phù hợp.

Đo ít nhất các số liệu sau:

| Chỉ số | Cách hiểu |
|---|---|
| Thời gian build tổng | Tác động thật tới vòng phản hồi lập trình viên và CI |
| Thời gian target chính | Xác định target nào tiêu tốn nhiều nhất |
| Số JVM/process được tạo | Phân biệt overhead fork và thời gian xử lý |
| CPU sử dụng, thời gian chờ I/O | Phát hiện chi phí khởi động và nghẽn đĩa |
| Peak RSS của Ant và các child | Tránh đổi tốc độ lấy OOM trên CI |
| GC pause/heap behavior | Phát hiện tác vụ khiến JVM dùng chung chịu áp lực |
| Tỷ lệ timeout, flaky test hoặc crash | Cân nhắc độ tin cậy bên cạnh tốc độ |
| Kết quả artifact và kiểm thử | Bảo đảm hai phương án làm cùng công việc |

Để phép đo có ý nghĩa:

1. Cố định JDK/Ant phiên bản, cùng máy/CI runner, số core và giới hạn bộ nhớ.
2. So sánh cùng bộ input và cùng trạng thái cache phù hợp: **clean build** với clean build, incremental build với incremental build.
3. Chạy lặp nhiều lần; tách lần đầu cold start/cache lạnh với những lần sau.
4. Thu thập thời gian target bằng log/profiling thích hợp; có thể dùng công cụ hệ điều hành hoặc JDK như `jcmd` cho process đang chạy nếu cần điều tra bộ nhớ.
5. Chỉ thay đổi một yếu tố chính giữa các phương án, đồng thời kiểm tra exit code và output để tránh “nhanh hơn” do bỏ sót công việc.

Ví dụ bảng ghi kết quả theo mẫu (để điền số đo thật):

| Phương án | Lượt đo | Tổng thời gian | Số fork | Peak RSS | Kết quả test |
|---|---:|---:|---:|---:|---|
| A — in-process | 1…N | … | 0 | … | … |
| B — mỗi test/file một JVM | 1…N | … | … | … | … |
| C — batch/reuse | 1…N | … | … | … | … |

Không lấy một lần build trên máy cá nhân làm tiêu chuẩn cho mọi môi trường. Một cấu hình có thể tốt trên laptop nhiều RAM nhưng vượt giới hạn memory của CI container, hoặc hiệu quả với 100 file nhưng kém khi dữ liệu tăng gấp mười.

## 10. Khả năng tái lập, an toàn vận hành và xử lý lỗi

Trong thực tế, việc thay `fork` có thể làm thay đổi hành vi ngoài hiệu năng. Cần hiểu rõ các ranh giới sau:

### JVM con không đồng nghĩa dữ liệu được cô lập

Hai child JVM vẫn có thể cùng đọc và ghi một thư mục, cùng kết nối database, dùng chung port hoặc sử dụng chung cache. Nếu hai công việc không độc lập, việc chạy song song có thể gây race condition. Fork chỉ tạo ranh giới process; muốn cô lập side effect bên ngoài cần thư mục, tài khoản, database/schema hoặc tài nguyên riêng.

### Không bỏ qua mã lỗi và timeout

Ant nên fail nếu child JVM trả về mã lỗi, đặc biệt ở các bước bắt buộc trước đóng gói. Với `<java>`, `failonerror="true"` là cấu hình quan trọng. Nếu task cho phép thời hạn xử lý, đặt timeout phù hợp với khối lượng thực tế; quá thấp dễ biến một job chậm thành lỗi giả.

Một task bị kill bởi timeout có thể để lại file đầu ra dở dang hoặc subprocess cháu. Bước chạy sau phải kiểm soát việc dùng lại output đó. Một cách tổ chức thường gặp là ghi ra thư mục tạm riêng rồi chỉ chuyển vào vị trí kết quả chính sau khi tác vụ thành công.

### Cố định cả JVM Ant và JVM con

Khi `fork="true"`, sử dụng executable JDK được quản lý cụ thể. JVM Ant chạy bởi `JAVA_HOME` còn child được chỉ định bằng `jvm` hoàn toàn có thể khác phiên bản. Việc thay compiler, runtime flags hoặc encoding có thể đổi artifact. Với môi trường build tái lập, ghi nhận và xác minh **cả hai**.

### Cân bằng song song với tài nguyên thật

Fork có thể tạo điều kiện song song hóa, nhưng số fork lớn không bảo đảm throughput cao. Nếu mỗi child cần heap lớn, nạp cùng một framework và đọc cùng một đĩa, thêm process có thể làm hệ thống bị swapping hoặc GC nhiều hơn. Hãy đặt giới hạn đồng thời dựa trên CPU và memory runner, theo dõi process tree và thu hẹp khi phát hiện contention.

## 11. Những lỗi thường gặp và cách nhìn nguyên nhân

| Hiện tượng | Khả năng cần xem xét | Hướng xử lý |
|---|---|---|
| Build mất thời gian dù mỗi file xử lý rất nhanh | Một JVM con được tạo cho từng file | Gom input thành batch, giảm số lần gọi `<java>` |
| Ant chậm dần hoặc thiếu heap sau nhiều task | Tác vụ chạy in-process giữ trạng thái, class hoặc thread | Xác định nguồn giữ tài nguyên; fork task rủi ro hoặc sửa lifecycle |
| Sau khi chuyển sang fork, build lại OOM trên CI | Ant và JVM con cùng chiếm RAM, hoặc có nhiều child đồng thời | Tính lại tổng RAM, giảm concurrency/batch, đặt heap hợp lý |
| Một test làm toàn bộ Ant dừng | Test chạy cùng JVM và gọi exit/crash native | Chạy test trong process riêng |
| Test vẫn flaky dù đã fork | Nhiều test tái sử dụng **cùng** JVM con, hoặc chia sẻ DB/file | Giảm nhóm test, cô lập state ngoài process |
| Child chạy đúng ở máy A nhưng sai máy B | JVM executable/classpath/env khác nhau | Pin binary và flags; ghi log thông tin môi trường |
| Timeout nhưng process phụ còn tồn tại | Tool sinh process cháu hoặc không xử lý shutdown | Thiết kế cleanup/process-tree management ở môi trường chạy |
| Chạy `fork="true"` nhanh hơn rất ít | Công việc chính dài, overhead fork chỉ chiếm phần nhỏ | Ưu tiên tối ưu thuật toán, I/O, cache hoặc tăng batch nếu an toàn |
| `-Xmx` task không đổi | Task vẫn chạy trong JVM Ant hoặc flag đặt không đúng vị trí | Kiểm tra thuộc tính fork và cách Ant truyền tham số JVM |

## 12. Kết luận thực hành

Một build Ant có hiệu năng tốt và vận hành ổn định thường áp dụng **nhiều mức cô lập khác nhau**:

- Chạy **trong JVM của Ant** với task Java nhỏ, ổn định và không có tác động trạng thái.
- Chạy **JVM con** khi cần bảo vệ process Ant, đặt heap/flags riêng, kiểm soát vòng đời hoặc cô lập test.
- **Gộp công việc** khi chi phí khởi động JVM lặp lại lớn và việc tái sử dụng không làm sai hành vi.
- **Giới hạn số JVM chạy đồng thời** theo tổng CPU và RAM thực tế.
- **Đo tổng thời gian, bộ nhớ và độ tin cậy** trên cùng workload trước khi cố định cấu hình.

Câu hỏi cốt lõi không phải “có nên bật `fork` cho tất cả task không?”, mà là **ranh giới cô lập nhỏ nhất nào vẫn bảo đảm độ đúng và độ tin cậy, với số lần khởi động JVM ít nhất có thể chấp nhận**. Khi xác định đúng ranh giới đó, nhóm vừa giảm thời gian build vừa tránh những lỗi khó truy nguyên do dùng chung trạng thái hoặc lạm dụng tiến trình con.

