# Preview feature và yêu cầu khớp phiên bản khi biên dịch, chạy

Trong nhóm **Biên dịch đa phiên bản** của chủ đề **Java Advance Compatibility Migration**, preview feature là một phần của quy trình thử nghiệm tính năng Java trước khi tính năng đó trở thành tiêu chuẩn ổn định. Khi sử dụng preview feature, nhóm phải quản lý đồng thời phiên bản JDK dùng để biên dịch, cờ bật preview của compiler, phiên bản JVM chạy ứng dụng và cờ bật preview của runtime.

Điểm đặc biệt cần nhớ là preview feature gắn với một phiên bản phát hành Java cụ thể. Bytecode phụ thuộc vào preview feature của một release chỉ được JVM tương ứng của release đó chấp nhận khi preview được bật. Vì vậy, chỉ thêm cờ vào lệnh biên dịch là chưa đủ; mọi tiến trình thực thi liên quan cũng phải được cấu hình phù hợp.

Bài học này trình bày vòng đời preview feature, cách compiler và JVM kiểm soát chúng, yêu cầu khớp phiên bản, cách cấu hình Gradle/Maven/CI, những lỗi thường gặp và cách lập kế hoạch khi feature được thay đổi hoặc trở thành tính năng chính thức.

## 1. Preview feature là gì?

Preview feature là một tính năng Java đã được triển khai để cộng đồng và nhà phát triển thử nghiệm trước khi được hoàn thiện và đưa vào trạng thái chính thức. Tùy từng release, preview có thể áp dụng cho:

- Ngôn ngữ Java, chẳng hạn cú pháp hoặc quy tắc ngôn ngữ mới.
- JVM hoặc định dạng class file, khi cần thay đổi cơ chế thực thi.
- Java SE API, khi một API mới được cung cấp dưới trạng thái preview.

Một preview feature đã có đặc tả và triển khai đủ để thử nghiệm, nhưng vẫn có thể được điều chỉnh hoặc loại bỏ trong release tiếp theo. Nhóm sử dụng cần chấp nhận khả năng phải sửa source code, cấu hình và cách triển khai khi nâng JDK.

Preview feature không có cùng cam kết ổn định như một tính năng Java đã được chuẩn hóa. Không nên xem việc một chương trình biên dịch và chạy thành công với preview là bằng chứng rằng mã nguồn đó sẽ tiếp tục hoạt động nguyên vẹn ở mọi phiên bản Java sau.

### 1.1. Vòng đời điển hình

~~~text
Đề xuất và thiết kế
        |
        v
Preview lần 1 trong một JDK release
        |
        v
Thu thập phản hồi và điều chỉnh
        |
        +--------------------+
        |                    |
        v                    v
Preview lần tiếp theo     Thay đổi lớn hoặc loại bỏ
        |
        v
Đưa vào trạng thái chính thức
        |
        v
API/ngôn ngữ ổn định theo chính sách tương thích Java
~~~

Không phải feature nào cũng đi hết chuỗi này. Một feature có thể chỉ xuất hiện trong một lần preview, được preview nhiều lần với thay đổi đáng kể, trở thành chính thức hoặc bị rút lại.

Khi chuẩn bị migration, hãy tra cứu trạng thái của đúng feature trong đúng JDK release. Không suy luận trạng thái chỉ từ tên feature hoặc từ một bài hướng dẫn được viết cho release khác.

### 1.2. Preview feature khác với tính năng đã chính thức

| Đặc điểm | Preview feature | Tính năng chính thức |
|---|---|---|
| Trạng thái | Đang được đánh giá | Đã được chuẩn hóa trong release |
| Cách bật | Thường cần cờ preview tương ứng | Dùng theo cấu hình Java thông thường |
| Khả năng thay đổi | Có thể đổi hoặc bị loại bỏ | Có cam kết tương thích theo chính sách Java |
| Bytecode | Có thể được đánh dấu là class file dùng preview | Class file thông thường |
| Runtime | Phải bật preview và khớp release tạo bytecode | Có thể chạy trên các JVM tương thích với class file/API |
| Phù hợp với thư viện công khai | Cần cân nhắc chặt vì ràng buộc runtime | Phù hợp hơn cho hợp đồng ổn định |

Một preview feature có thể hữu ích để thử nghiệm thiết kế, nhưng việc đưa nó vào thư viện dùng chung tạo thêm ràng buộc cho mọi consumer. Nếu consumer không thể kiểm soát phiên bản JDK và cách khởi chạy JVM, việc sử dụng preview trong public API có thể làm giảm khả năng phân phối thư viện.

## 2. Cờ bật preview khi biên dịch

Compiler không mặc định cho phép source code sử dụng preview feature. Với **javac**, cần truyền tùy chọn:

~~~bash
--enable-preview
~~~

Tùy chọn này cho phép compiler của JDK hiện tại chấp nhận các preview feature thuộc chính release đó.

Nên kết hợp nó với **--release** để xác định rõ release Java mà source và bytecode hướng đến.

Ví dụ với JDK 21:

~~~bash
javac --enable-preview --release 21 -d out src/com/example/Main.java
~~~

Trong ví dụ này:

- **--enable-preview** bật preview feature của JDK đang chạy compiler.
- **--release 21** đặt mức ngôn ngữ, phiên bản class file và tập API Java SE được phép sử dụng theo release 21.
- **-d out** chỉ định thư mục chứa class file được tạo.

**Điều kiện quan trọng:** compiler phải là JDK 21 khi bật preview của Java 21. Không thể dùng JDK 22 để yêu cầu **--enable-preview --release 21** nhằm biên dịch preview feature của Java 21. Preview được bật cho release hiện tại của compiler, không phải cho một release cũ tùy chọn.

### 2.1. Vì sao nên dùng --release?

Có thể gặp các tùy chọn source và target:

~~~bash
javac -source 21 -target 21 ...
~~~

Chúng điều khiển mức cú pháp và phiên bản bytecode, nhưng không tự giới hạn đầy đủ tập API của JDK mục tiêu. Khi biên dịch trên JDK mới hơn, source có thể vô tình gọi API chỉ tồn tại ở JDK mới dù bytecode được tạo cho một release cũ.

**--release** kết hợp các yêu cầu về source level, target bytecode và API Java SE của release được chọn. Khi cần preview, sử dụng JDK đúng release và kết hợp:

~~~bash
javac --enable-preview --release 21 ...
~~~

Không dùng **--release** như một cách để tạo preview bytecode cho một JDK cũ từ compiler mới hơn. Compiler chỉ bật preview cho release của chính nó.

### 2.2. Phân biệt compiler JDK và target runtime

Một dự án có thể có nhiều phiên bản Java tham gia vào quá trình build:

| Thành phần | Vai trò |
|---|---|
| JDK chạy Gradle/Maven | Khởi chạy build tool |
| JDK compiler/toolchain | Chạy javac để biên dịch source |
| Release target | Xác định mức API và class file |
| JDK chạy test | Khởi chạy test worker hoặc test process |
| JDK chạy ứng dụng | Nạp class và thực thi ứng dụng |

Khi dùng preview feature của Java 21, compiler cần là JDK 21 và JVM chạy các class phụ thuộc preview cũng cần là Java 21 với preview được bật. Việc Gradle chạy trên JDK khác không tự động bảo đảm compiler và test worker đã dùng đúng phiên bản.

## 3. Cờ bật preview khi chạy

Sau khi biên dịch thành công, JVM cũng phải được cho phép sử dụng preview feature.

Ví dụ:

~~~bash
java --enable-preview -cp out com.example.Main
~~~

Cờ runtime có vai trò riêng với cờ compiler:

| Giai đoạn | Cờ | Mục đích |
|---|---|---|
| Biên dịch | javac với **--enable-preview** | Cho phép source sử dụng preview feature của release compiler |
| Chạy | java với **--enable-preview** | Cho phép JVM thực thi class file phụ thuộc preview của release hiện tại |

Nếu chỉ bật preview lúc biên dịch nhưng bỏ cờ khi chạy, JVM có thể từ chối nạp class file dùng preview. Một lỗi thường gặp là **UnsupportedClassVersionError** với thông báo cho biết preview feature chưa được bật.

Cờ runtime phải có mặt trong đúng tiến trình JVM thực thi code. Đặt cờ cho Gradle daemon hoặc Maven process không có nghĩa mọi JVM con do test runner, application plugin hoặc script khởi chạy đều tự nhận được cờ đó.

### 3.1. Yêu cầu khớp release

Giả sử một class sử dụng preview feature của Java 21:

~~~text
Compiler: JDK 21 + --enable-preview
                 |
                 v
          Class file preview 21
                 |
                 v
Runtime: JDK 21 + --enable-preview
                 |
                 v
             Có thể chạy
~~~

Các tổ hợp không hợp lệ thường gặp:

| Compiler tạo preview class | Runtime | Kết quả |
|---|---|---|
| JDK 21, preview bật | JDK 21, preview bật | Đúng release; có thể chạy nếu dependency và môi trường khác cũng phù hợp |
| JDK 21, preview bật | JDK 21, preview tắt | JVM từ chối class file phụ thuộc preview |
| JDK 21, preview bật | JDK 22, preview bật | Không tương thích; preview class của release 21 không được JVM 22 chấp nhận |
| JDK 21, preview bật | JDK 20 | Không tương thích phiên bản class file/runtime |
| JDK 22, preview bật | JDK 22, preview bật | Đúng release nếu class được biên dịch bằng JDK 22 |
| JDK 22, preview bật | JDK 21 | Runtime cũ không hiểu class file của release 22 |

Cùng có **--enable-preview** ở hai tiến trình không làm cho các release khác nhau tương thích. Cờ chỉ bật preview của JDK đang chạy; nó không biến JVM mới thành runtime cho preview class file của release cũ.

### 3.2. Phiên bản class file và minor version đặc biệt

Class file Java có major version và minor version. Khi class file sử dụng preview feature, JVM có thể nhận diện nó qua minor version đặc biệt **65535**, kết hợp với major version của release tương ứng.

Ví dụ, class file thông thường của Java 21 dùng major version 65. Class file preview của Java 21 có major version tương ứng và minor version đặc biệt cho preview.

Cơ chế này giúp JVM biết class file phụ thuộc vào preview feature. JVM kiểm tra release phù hợp và việc preview đã được bật trước khi cho phép thực thi. Đây là lý do class file preview không phải một artifact có thể tự do mang sang JDK feature release kế tiếp.

Không nên chỉ nhìn major version để kết luận tương thích. Khi điều tra lỗi, hãy xem cả minor version và thông báo JVM.

## 4. Ví dụ thực hành với Java 21

Ví dụ dưới đây minh họa quy trình biên dịch và chạy một chương trình có sử dụng preview feature của Java 21. Phần thân chương trình được giả định có cú pháp hoặc API thuộc preview của release này; thay bằng ví dụ cụ thể mà nhóm đang khảo sát.

### Bước 1: Xác nhận JDK đang dùng

~~~bash
java -version
javac -version
~~~

Cả compiler và runtime được chọn cho thử nghiệm phải thuộc JDK 21. Nếu build tool dùng toolchain riêng, cần xác nhận toolchain đó cũng trỏ đến JDK 21.

### Bước 2: Biên dịch với preview

~~~bash
javac --enable-preview --release 21 -d out src/com/example/Main.java
~~~

Nếu source dùng preview feature của release 21 nhưng thiếu **--enable-preview**, compiler sẽ báo lỗi. Nếu compiler không phải JDK 21, tổ hợp cờ và release có thể bị từ chối.

### Bước 3: Chạy với preview

~~~bash
java --enable-preview -cp out com.example.Main
~~~

Runtime cần là JDK 21. Khi chương trình chạy, JVM có thể hiển thị cảnh báo cho biết chương trình đang sử dụng preview feature của Java SE 21.

### Bước 4: Thử bỏ cờ runtime

~~~bash
java -cp out com.example.Main
~~~

Nếu class file thực sự phụ thuộc preview feature, JVM sẽ từ chối nạp hoặc thực thi class. Lỗi này minh họa rằng compile flag và runtime flag là hai điều kiện độc lập.

### Bước 5: Thử dùng JDK release kế tiếp

Nếu chạy class preview Java 21 bằng JDK 22, dù thêm **--enable-preview**, JVM vẫn không hỗ trợ preview class file được tạo cho release 21. Cần biên dịch lại source với JDK 22 sau khi kiểm tra feature đó còn tồn tại và cú pháp/API đã thay đổi ra sao.

Không nên chỉ đổi runtime trong môi trường production để thử giải quyết lỗi. Hãy tạo một build mới theo đúng release mục tiêu và chạy test trên artifact mới.

## 5. Cấu hình trong Gradle

Với Gradle, cần cấu hình cả compiler và các JVM thực thi code. Ví dụ Groovy DSL cho Java 21:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 21
    options.compilerArgs += ['--enable-preview']
}

tasks.withType(Test).configureEach {
    jvmArgs '--enable-preview'
}

tasks.withType(JavaExec).configureEach {
    jvmArgs '--enable-preview'
}
~~~

Ý nghĩa:

- Java toolchain chọn JDK 21 cho các task Java tương ứng.
- **options.release = 21** giới hạn mức API và class file mục tiêu.
- **options.compilerArgs** bật preview trong quá trình compile.
- Test task truyền cờ cho JVM chạy test worker.
- JavaExec truyền cờ cho JVM chạy ứng dụng hoặc main class.

Cần xác nhận phiên bản Gradle hỗ trợ JDK 21 và cách cấu hình toolchain đang dùng. Nếu dự án có task tự tạo, fork compiler hoặc fork JVM riêng, task đó cũng phải được cấu hình.

### 5.1. Cẩn thận với test và task tùy chỉnh

Một dự án có thể có nhiều loại task:

- Compile source chính.
- Compile test source.
- Unit test.
- Integration test.
- JavaExec chạy ứng dụng.
- Task chạy migration tool hoặc code generator.
- Task khởi chạy process con.
- Task tạo smoke test hoặc compatibility fixture.

Không giả định cấu hình một task sẽ tự áp dụng cho tất cả process. Kiểm tra command line thực tế của task khi cần, đặc biệt với test worker và tiến trình được fork.

Nếu chỉ thêm **--enable-preview** vào JavaCompile, source có thể compile nhưng test JVM vẫn từ chối class file. Nếu chỉ thêm vào Test task, compiler lại không chấp nhận cú pháp preview.

### 5.2. Toolchain và JVM thực thi

Toolchain giúp chọn JDK cho task, nhưng cần xem từng loại task có sử dụng launcher đó hay không. Test task và JavaExec thường có thể dùng launcher từ Java toolchain; task tự tạo hoặc process được khởi chạy qua shell có thể dùng JAVA_HOME hoặc PATH của môi trường.

Nên xác nhận:

~~~bash
./gradlew -version
./gradlew compileJava --info
./gradlew test --info
~~~

Trên Windows dùng **gradlew.bat** tương ứng. Đọc log để xác định JDK compiler và JVM thực thi thực tế, không chỉ dựa vào java version của terminal.

## 6. Cấu hình trong Maven

Với Maven, cấu hình compiler plugin và các test runner riêng. Đoạn dưới đây là các phần cấu hình minh họa trong pom.xml; cần chọn phiên bản plugin tương thích với JDK và Maven đang dùng.

### 6.1. Compiler

~~~xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>

<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <compilerArgs>
            <arg>--enable-preview</arg>
        </compilerArgs>
    </configuration>
</plugin>
~~~

Compiler process phải chạy bằng JDK 21 để bật preview của Java 21. **maven.compiler.release** giới hạn API và class file mục tiêu.

### 6.2. Unit test với Surefire

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <argLine>--enable-preview</argLine>
    </configuration>
</plugin>
~~~

Nếu dùng integration test với Maven Failsafe, cấu hình JVM arguments tương tự cho Failsafe. Nếu dự án kết hợp JaCoCo hoặc agent khác, cần hợp nhất **argLine** để không vô tình ghi đè các tham số agent hiện có.

Khi test chạy trong forked JVM, **argLine** được dùng để cấu hình process đó. Nếu tắt fork và test chạy ngay trong Maven JVM, cờ phải được truyền cho JVM khởi chạy Maven; cấu hình cho process con không có tác dụng với process hiện tại.

### 6.3. Kiểm tra JDK của Maven

~~~bash
mvn -version
mvn clean test
~~~

**mvn -version** cho biết Java runtime mà Maven đang dùng. Nếu compiler được fork hoặc toolchain được khai báo riêng, cần kiểm tra thêm JDK compiler thực tế. CI phải dùng cùng feature release mà dự án đã chọn cho preview.

## 7. Cấu hình IDE và CI/CD

Cờ preview phải được đồng bộ giữa môi trường phát triển và pipeline. Nếu IDE compile bằng JDK 21 nhưng test runner dùng JDK khác, kết quả có thể khác với CI.

### 7.1. IDE

Kiểm tra các cấu hình sau:

- Project SDK hoặc JDK của workspace.
- Language level của module.
- Compiler options có **--enable-preview**.
- Run configuration có **--enable-preview**.
- Test run configuration có **--enable-preview**.
- Gradle/Maven JVM và Java toolchain.
- JDK được dùng bởi application server hoặc plugin chạy trong IDE.

IDE có thể cung cấp tùy chọn bật preview theo module. Tuy nhiên, cấu hình IDE chỉ phục vụ máy phát triển; cần đưa yêu cầu tương ứng vào build file và hướng dẫn dự án để CI và các máy khác dùng cùng thiết lập.

### 7.2. CI pipeline

Pipeline cần cố định JDK feature release và bật preview ở cả compile lẫn runtime.

~~~text
Chọn JDK feature release
          |
          v
Xác nhận compiler và runtime
          |
          v
Compile với --enable-preview
          |
          v
Chạy unit/integration test với --enable-preview
          |
          v
Kiểm tra artifact và class file
          |
          v
Chạy smoke test bằng runtime mục tiêu
          |
          v
Lưu JDK version, command line và test report
~~~

Các bước nên có bằng chứng:

- Phiên bản JDK và vendor của runner.
- Phiên bản Gradle/Maven.
- Compiler arguments thực tế.
- JVM arguments của test worker và application process.
- Kết quả test.
- Artifact checksum và thông tin build.
- JDK feature release được yêu cầu khi triển khai.

Nếu pipeline chia thành nhiều job hoặc stage, mỗi job có thể chạy trên runner khác. Cần cấu hình rõ JDK và cờ cho từng job, không giả định thiết lập của job compile tự động truyền sang job test hoặc deploy.

## 8. Preview feature trong multi-module và thư viện dùng chung

Một module có thể sử dụng preview feature trong khi các module khác không sử dụng. Cần xác định preview dependency có lan qua ranh giới module hay không.

~~~text
application
    |
    +---- core-library
    |         |
    |         +---- sử dụng preview API Java 21
    |
    +---- adapter
              |
              +---- không dùng preview
~~~

Nếu **core-library** chứa class file phụ thuộc preview Java 21, ứng dụng nạp class đó phải chạy trên JDK 21 với preview được bật. Việc module application không trực tiếp viết cú pháp preview không loại bỏ yêu cầu runtime của dependency.

Cần kiểm tra:

- Module nào thật sự sử dụng preview feature.
- Module nào compile hoặc test phụ thuộc vào class preview.
- Task nào tạo class file preview.
- Application nào nạp module đó.
- Có plugin hoặc consumer bên ngoài nào nhận artifact không.
- Cờ runtime có được truyền đến mọi process tiêu thụ hay không.

### 8.1. Giới hạn lan truyền của cấu hình

Compiler flag là cấu hình của task biên dịch. Runtime flag là cấu hình của process JVM. Chúng không tự động trở thành metadata có thể truyền xuyên suốt dependency graph.

Một JAR có thể được đóng gói thành công nhưng consumer vẫn không biết rằng cần:

- Dùng đúng JDK feature release.
- Bật preview khi chạy.
- Đồng bộ phiên bản các dependency có liên quan.

Vì vậy, nếu phát hành artifact có preview dependency, hãy công bố rõ yêu cầu JDK và runtime flag. Nếu consumer không thể đáp ứng yêu cầu đó, hãy cân nhắc tách phần thử nghiệm thành module tùy chọn hoặc giữ preview code bên ngoài public API.

### 8.2. Hạn chế preview trong public library

Một thư viện công khai thường cần hỗ trợ nhiều ứng dụng với lịch nâng cấp khác nhau. Khi public API hoặc class implementation phụ thuộc preview feature, consumer phải đáp ứng đúng release và runtime flag.

Rủi ro gồm:

- Consumer chạy JDK khác không thể nạp class preview.
- Consumer không kiểm soát được JVM startup arguments.
- Feature thay đổi ở release tiếp theo làm source hoặc API không còn tương thích.
- Artifact cũ phải được biên dịch lại để chạy trên release mới.
- Một module preview làm tăng yêu cầu runtime cho toàn bộ ứng dụng.

Nếu mục tiêu là thử nghiệm, có thể cô lập preview code trong module riêng, chỉ dùng trong môi trường kiểm thử hoặc phát hành artifact thử nghiệm có giới hạn hỗ trợ. Nếu bắt buộc sử dụng trong sản phẩm, phải ghi rõ release lock, runtime flag, thời gian hỗ trợ và kế hoạch loại bỏ hoặc thay thế.

## 9. Preview feature và incubator module không giống nhau

Java có các cơ chế thử nghiệm khác nhau. Không nên nhầm preview feature với incubator module.

| Đặc điểm | Preview feature | Incubator module |
|---|---|---|
| Mục đích | Thử nghiệm tính năng ngôn ngữ, JVM hoặc API theo release | Thử nghiệm API/module trước khi ổn định |
| Cơ chế bật thường gặp | **--enable-preview** | **--add-modules** và có thể cần tùy chọn module liên quan |
| Gắn với release | Preview class file phụ thuộc release tạo ra nó | Phụ thuộc trạng thái và module của JDK cụ thể |
| Phạm vi | Có thể ảnh hưởng cú pháp, class file hoặc API | Thường là API được cung cấp qua module incubator |
| Cách kiểm tra | Compiler/runtime preview flag và release khớp nhau | Kiểm tra module tồn tại, cách resolve và cấu hình module path |

Ví dụ với một incubator module:

~~~bash
java --add-modules jdk.incubator.vector -cp out com.example.Main
~~~

Đây là ví dụ về cách yêu cầu module được đưa vào module graph. Nó không thay thế **--enable-preview** và không có nghĩa mọi incubator module đều dùng cùng một cờ.

Một dự án có thể cần cả hai cơ chế nếu đồng thời sử dụng preview feature và incubator API. Hãy đọc hướng dẫn của đúng JDK release và từng module để xác định tùy chọn cần thiết.

## 10. Các lỗi thường gặp và cách điều tra

### 10.1. Compiler báo preview feature chưa được bật

Nguyên nhân thường gặp:

- Thiếu **--enable-preview** trong compiler arguments.
- Một module hoặc source set chưa nhận cấu hình.
- Compiler thực tế khác JDK dự kiến.
- Task code generation hoặc test compilation không dùng cùng compiler options.

Cách kiểm tra:

1. Xem command line của javac.
2. Xác nhận phiên bản javac.
3. Kiểm tra compiler task của từng module.
4. Kiểm tra test source set và task tùy chỉnh.

### 10.2. JVM báo preview feature chưa được bật

Nguyên nhân thường gặp:

- Đã bật preview khi compile nhưng không bật khi run.
- Test worker hoặc process con không nhận JVM argument.
- IDE run configuration thiếu cờ.
- Container entrypoint hoặc service script không truyền cờ.

Cách xử lý là thêm **--enable-preview** vào đúng JVM process thực thi class. Sau đó chạy lại cùng artifact để xác nhận.

### 10.3. JVM báo class file version không tương thích

Nguyên nhân thường gặp:

- Runtime cũ hơn release dùng để biên dịch.
- Preview class được biên dịch bằng một release nhưng chạy trên release khác.
- Dependency transitively chứa class file mới hơn runtime hỗ trợ.
- CI và production dùng JDK khác nhau.

Kiểm tra **java -version**, **javap -verbose** và dependency thực tế được nạp. Không chỉ kiểm tra JDK trong build container; phải kiểm tra cả runtime image và process production.

### 10.4. Dùng compiler mới với release cũ

Ví dụ, chạy JDK 22 nhưng yêu cầu:

~~~bash
javac --enable-preview --release 21 ...
~~~

Compiler không bật preview feature của Java 21 theo cách này. **--enable-preview** áp dụng cho release hiện tại của compiler. Hãy chọn JDK 21 toolchain nếu cần preview của Java 21.

### 10.5. Chỉ một số test thất bại

Nếu unit test chạy được nhưng integration test thất bại, có thể integration test dùng một JVM khác. Các trường hợp cần kiểm tra:

- Surefire và Failsafe có cấu hình khác nhau.
- Test worker forked riêng.
- Gradle Test task có nhiều task type.
- Test khởi chạy ứng dụng qua JavaExec hoặc shell.
- Docker Compose hoặc Testcontainers dùng image JRE khác.
- Test chạy trên CI runner khác với compile stage.

Hãy xác định process nào thực sự nạp class preview và cấu hình cờ cho process đó.

### 10.6. Source chạy được trên release này nhưng không compile ở release kế tiếp

Preview feature có thể thay đổi cú pháp, kiểu, API hoặc quy tắc ngôn ngữ. Khi chuyển JDK, cần đọc JEP và migration note của feature, cập nhật source, sau đó compile/test lại.

Không dùng class file preview cũ làm artifact để triển khai trên release mới. Hãy tạo artifact mới từ source đã được điều chỉnh bằng compiler của release mục tiêu.

## 11. Theo dõi trạng thái feature qua các release

Với mỗi preview feature đang dùng, nên có một mục inventory:

| Trường | Nội dung |
|---|---|
| Feature name | Tên feature |
| JEP / tài liệu | Mã JEP hoặc tài liệu chính thức |
| First preview release | Release preview đầu tiên |
| Current status | Preview, second preview, final hoặc withdrawn |
| Source usage | Module, package và file đang dùng |
| Runtime dependency | Class nào cần preview khi nạp |
| Build flag | Compiler flag và release |
| Runtime flag | JVM argument cần thiết |
| Consumer | Ứng dụng, plugin hoặc module phụ thuộc |
| Owner | Nhóm chịu trách nhiệm |
| Next action | Re-evaluate, update source, remove hoặc finalize |

Ở mỗi lần nâng JDK:

1. Tra cứu trạng thái feature trong release mục tiêu.
2. Xác định feature còn preview, đã final hay bị rút lại.
3. Đọc thay đổi về cú pháp, API, class file và runtime.
4. Cập nhật compiler và runtime configuration.
5. Recompile toàn bộ module phụ thuộc.
6. Chạy test với JDK mục tiêu.
7. Xác nhận consumer và artifact đã chuyển đổi.
8. Cập nhật inventory và tài liệu.

Nếu feature trở thành chính thức, code thường cần được biên dịch lại theo release mới. Sau khi không còn phụ thuộc preview, có thể loại bỏ cờ preview và xác nhận build/run thành công mà không cần cờ đó.

Nếu feature bị rút lại, nhóm cần thiết kế lại phần code sử dụng nó. Không giả định rằng một feature bị rút lại sẽ luôn có API thay thế tương đương.

## 12. Chiến lược migration khi preview được final hoặc thay đổi

### 12.1. Khi feature trở thành chính thức

Ví dụ, một feature preview trong release N được chuẩn hóa trong release N+1.

Quy trình:

1. Đọc tài liệu chính thức của release N+1.
2. Xác định cú pháp và API cuối có thay đổi so với preview N không.
3. Chuyển compiler toolchain sang JDK N+1.
4. Sửa source theo đặc tả chính thức.
5. Loại bỏ **--enable-preview** nếu không còn feature preview khác.
6. Build lại tất cả module và artifact.
7. Chạy test trên JDK N+1.
8. Chạy consumer test và kiểm tra runtime.
9. Phát hành artifact mới, ghi rõ thay đổi yêu cầu nâng cấp.

Không giữ artifact preview N rồi chỉ thay JVM thành N+1. Artifact cần được biên dịch lại bằng compiler của release mới.

### 12.2. Khi feature vẫn tiếp tục preview

Nếu feature được preview lại ở release N+1, không mặc định cú pháp và API giữ nguyên. So sánh các lần preview, cập nhật code theo release mới, bật cờ tương ứng ở compile và runtime, rồi kiểm thử toàn bộ consumer.

Class file preview N không phải artifact dùng cho N+1. Mỗi release preview cần build riêng và runtime cùng release.

### 12.3. Khi feature bị rút lại

Nếu feature bị withdrawn hoặc không còn xuất hiện:

- Xác định các module và API đang phụ thuộc.
- Đọc lý do và hướng đi được công bố.
- Tìm API hoặc thiết kế thay thế.
- Đánh giá ảnh hưởng tới public API và consumer.
- Thực hiện refactor trong branch migration.
- Thêm regression test cho hành vi thay thế.
- Phát hành artifact mới sau khi xác nhận.

Nếu chưa có giải pháp thay thế, ghi rõ quyết định tạm hoãn nâng cấp hoặc loại bỏ phần sử dụng preview. Không xóa code mà chưa xác định hành vi nghiệp vụ cần giữ.

## 13. Preview feature trong production: cân nhắc và kiểm soát

Preview feature chủ yếu phục vụ phản hồi và đánh giá trước khi chuẩn hóa. Có thể có tình huống tổ chức muốn thử nghiệm nó trong môi trường gần production hoặc một workload có kiểm soát, nhưng phải chấp nhận ràng buộc phiên bản và rủi ro thay đổi.

Trước khi dùng, hãy xác định:

- Feature có thực sự đem lại giá trị cần thiết không?
- Có thể giữ JDK feature release cố định trong thời gian hỗ trợ không?
- Tất cả runtime instance có thể nhận **--enable-preview** không?
- Có consumer ngoài tổ chức hoặc plugin độc lập không?
- Có cách quay lại artifact không dùng preview không?
- Feature có làm lộ preview API qua public contract không?
- Có đủ test, logging, monitoring và owner xử lý khi feature thay đổi không?

Nếu dùng trong production, ghi rõ release lock, thời hạn, phạm vi, owner, rollback và kế hoạch chuyển sang feature chính thức hoặc giải pháp ổn định. Đối với thư viện công khai, nên tránh buộc mọi consumer phải sử dụng một preview feature nếu không thể kiểm soát runtime của họ.

## 14. Checklist trước khi bật preview feature

### Xác định feature

- [ ] Đã xác định tên feature và JEP/tài liệu của đúng release.
- [ ] Đã xác nhận trạng thái preview trong JDK mục tiêu.
- [ ] Đã hiểu feature áp dụng cho language, JVM hay API.
- [ ] Đã kiểm tra thay đổi giữa các lần preview.

### Compiler

- [ ] Compiler chạy bằng đúng JDK feature release.
- [ ] Có **--enable-preview** cho compiler.
- [ ] Có **--release** đúng release khi phù hợp.
- [ ] Mọi source set và module sử dụng feature đều nhận cấu hình.
- [ ] Build log ghi nhận compiler/toolchain thực tế.

### Runtime

- [ ] Runtime dùng cùng JDK feature release với preview class.
- [ ] JVM process có **--enable-preview**.
- [ ] Test worker, integration test và process con có cờ.
- [ ] Container, service script và production launcher có cờ.
- [ ] Không dùng preview class file cũ trên release khác.

### Consumer và phát hành

- [ ] Đã kiểm kê module, plugin và consumer phụ thuộc.
- [ ] Đã đánh giá ảnh hưởng tới public API.
- [ ] Đã lưu artifact và checksum của mỗi release preview.
- [ ] Đã ghi yêu cầu JDK/runtime cho consumer.
- [ ] Có kế hoạch khi feature final, thay đổi hoặc bị rút lại.
- [ ] Có artifact fallback và rollback đã kiểm chứng.

### CI/CD

- [ ] CI dùng đúng JDK cho compile và test.
- [ ] Compiler và JVM test nhận đúng cờ.
- [ ] Smoke test chạy trên runtime mục tiêu.
- [ ] Báo cáo lưu JDK, command line và artifact checksum.
- [ ] Pipeline có kiểm tra để phát hiện JDK lệch giữa các stage.

Preview feature giúp nhóm thử nghiệm khả năng mới của Java trước khi chúng trở thành tiêu chuẩn. Đổi lại, preview class file gắn với release đã tạo ra nó và cần được chạy bằng JVM cùng release với preview được bật. Vì vậy, hãy xem phiên bản compiler, runtime, build task và consumer là một hợp đồng thống nhất. Khi feature thay đổi hoặc trở thành chính thức, biên dịch lại source theo release mới, kiểm tra hành vi và phát hành artifact mới thay vì tái sử dụng bytecode preview cũ.
