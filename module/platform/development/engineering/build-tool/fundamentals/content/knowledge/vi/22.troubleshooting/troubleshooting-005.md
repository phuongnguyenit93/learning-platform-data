# ClassNotFoundException và NoClassDefFoundError trong ngữ cảnh build

Một ứng dụng Java có thể biên dịch thành công nhưng vẫn thất bại ngay khi chạy với lỗi không tìm thấy lớp. Hai lỗi thường gặp là **ClassNotFoundException** và **NoClassDefFoundError**. Cả hai đều liên quan tới việc JVM hoặc class loader không thể cung cấp một lớp cần thiết, nhưng chúng xuất hiện trong những tình huống khác nhau.

Trong ngữ cảnh build, nguyên nhân thường nằm ở sự khác biệt giữa compile classpath và runtime classpath, dependency scope, cách đóng gói artifact, cấu hình module hoặc class loader của môi trường triển khai. Một thư viện có thể có mặt khi biên dịch nhưng không được đưa vào gói chạy; một dependency bắc cầu có thể bị loại; hoặc một lớp có thể tồn tại nhưng không khởi tạo được do thiếu dependency khác.

Để xử lý đúng, cần đọc chính xác loại lỗi, xác định tên lớp mà JVM không tìm thấy, tìm artifact sở hữu lớp đó, rồi kiểm tra dependency graph và classpath ở đúng giai đoạn xảy ra lỗi. Chỉ thêm một JAR bất kỳ vào classpath có thể che triệu chứng nhưng không giải quyết được nguyên nhân gốc.

## 1. Hai lỗi này có điểm gì giống nhau?

Java dùng class loader để nạp định nghĩa lớp khi chương trình cần sử dụng. Lớp có thể được nạp khi:

- JVM khởi tạo lớp chứa phương thức main.
- Bytecode tham chiếu tới một kiểu cần được liên kết.
- Chương trình gọi Class.forName hoặc ClassLoader.loadClass.
- Framework quét component, plugin hoặc driver.
- Service loader hoặc dependency injection tìm implementation.
- JVM cần nạp một lớp cha, interface hoặc kiểu phụ thuộc của lớp khác.

Nếu lớp cần thiết không thể được tìm thấy hoặc liên kết, chương trình có thể thất bại trước hoặc trong khi thực hiện logic nghiệp vụ.

Hai lỗi có chung biểu hiện bề ngoài là thiếu lớp, nhưng loại exception/error cho biết cách lớp được yêu cầu:

| Loại | Phân cấp | Tình huống tiêu biểu |
| --- | --- | --- |
| **ClassNotFoundException** | Checked exception, kế thừa Exception | Mã nguồn yêu cầu nạp lớp theo tên, nhưng class loader không tìm thấy lớp đó. |
| **NoClassDefFoundError** | Error, thuộc nhóm LinkageError | JVM cần định nghĩa lớp đã được tham chiếu khi liên kết hoặc thực thi nhưng không thể cung cấp lớp đó; cũng có thể xảy ra sau khi khởi tạo lớp thất bại trước đó. |

Không nên xem hai loại là hai cách viết khác nhau của cùng một lỗi. Cách nạp lớp và thời điểm xảy ra rất quan trọng khi chẩn đoán.

## 2. ClassNotFoundException là gì?

**ClassNotFoundException** xảy ra khi chương trình yêu cầu một class loader tìm một lớp bằng tên, nhưng class loader không tìm thấy định nghĩa lớp tương ứng.

Ví dụ:

    public class PluginLoader {
        public static void main(String[] args) throws Exception {
            Class<?> type = Class.forName("com.example.plugins.CsvPlugin");
            System.out.println(type.getName());
        }
    }

Nếu lớp com.example.plugins.CsvPlugin không có trên classpath hoặc không thể truy cập bởi class loader được sử dụng, lời gọi Class.forName có thể ném ClassNotFoundException.

Một số API có thể ném lỗi này:

- Class.forName(String).
- ClassLoader.loadClass(String).
- Một số API framework hoặc plugin sử dụng class loading theo tên.

### Vì sao lỗi thường xuất hiện lúc chạy?

Compiler không nhất thiết biết mọi tên lớp được yêu cầu dưới dạng chuỗi. Trong ví dụ trên, tên com.example.plugins.CsvPlugin là một chuỗi. Nếu mã nguồn không trực tiếp tham chiếu kiểu CsvPlugin, compiler có thể không yêu cầu lớp đó trong compile classpath.

Chương trình vẫn có thể biên dịch, nhưng khi chạy, Class.forName mới yêu cầu class loader tìm lớp. Nếu artifact chứa lớp không có trên runtime classpath, lỗi xuất hiện.

### Tên lớp phải là tên đầy đủ

Class.forName thường nhận tên đầy đủ gồm package:

    Class.forName("com.example.plugins.CsvPlugin");

Không phải:

    Class.forName("CsvPlugin");

Trừ khi lớp thực sự nằm trong default package, chuỗi tên lớp thiếu package sẽ không khớp. Java cũng phân biệt chữ hoa và chữ thường trong tên lớp; điều này đặc biệt dễ gây lỗi khi build trên Windows rồi triển khai lên Linux.

## 3. NoClassDefFoundError là gì?

**NoClassDefFoundError** là một Error thuộc nhóm LinkageError. JVM phát sinh lỗi này khi cần một định nghĩa lớp mà không thể tìm hoặc sử dụng được định nghĩa đó trong quá trình liên kết hay thực thi.

Ví dụ:

    public class OrderService {
        private final PaymentClient client = new PaymentClient();

        public void pay() {
            client.charge();
        }
    }

Nếu OrderService đã được biên dịch với PaymentClient có mặt trên compile classpath, nhưng khi chạy JAR lại không có JAR chứa PaymentClient trên runtime classpath, JVM có thể ném NoClassDefFoundError khi cần nạp hoặc liên kết kiểu đó.

Lỗi cũng có thể xuất hiện khi một lớp phụ thuộc vào một lớp khác không có mặt. Ví dụ PaymentClient tồn tại nhưng một kiểu mà PaymentClient cần lại bị thiếu. Khi đọc stack trace, tên lớp trong thông báo có thể là lớp phụ thuộc bị thiếu chứ không phải lớp mà ứng dụng đang gọi trực tiếp.

### Trường hợp lớp đã khởi tạo thất bại

Một trường hợp quan trọng khác: lần đầu JVM khởi tạo lớp và static initializer thất bại. Lần khởi tạo đầu tiên có thể phát sinh ExceptionInInitializerError. Sau đó, nếu chương trình tiếp tục yêu cầu lớp đó, JVM có thể ném NoClassDefFoundError với thông báo tương tự:

    Could not initialize class com.example.Configuration

Ví dụ:

    public class Configuration {
        static {
            if (System.getProperty("config.path") == null) {
                throw new IllegalStateException("Missing config.path");
            }
        }
    }

Nếu static initializer ném exception, JVM đánh dấu lớp không khởi tạo thành công. Những lần sử dụng sau có thể báo NoClassDefFoundError dù file .class vẫn tồn tại trên classpath.

Vì vậy, không phải mọi NoClassDefFoundError đều có nghĩa JAR chứa lớp đó bị thiếu. Hãy tìm exception đầu tiên, đặc biệt là ExceptionInInitializerError hoặc nguyên nhân nằm trong static initializer.

## 4. So sánh ClassNotFoundException và NoClassDefFoundError

| Tiêu chí | ClassNotFoundException | NoClassDefFoundError |
| --- | --- | --- |
| Loại | Exception có kiểm tra | Error thuộc LinkageError |
| Tình huống thường gặp | Nạp lớp bằng tên qua class loader | JVM cần liên kết hoặc sử dụng lớp đã được tham chiếu |
| Ví dụ API | Class.forName, ClassLoader.loadClass | Liên kết bytecode, nạp kiểu phụ thuộc |
| Nguyên nhân phổ biến | Lớp không nằm trong phạm vi tìm kiếm của class loader | Lớp hoặc dependency bị thiếu trên runtime; lớp trước đó khởi tạo thất bại |
| Có thể xảy ra dù compile thành công? | Có, nhất là khi tên lớp được nạp động | Có, khi compile classpath khác runtime classpath |
| Cách điều tra đầu tiên | Tìm nơi gọi class loading và class loader được dùng | Tìm class bị thiếu, runtime classpath và lỗi khởi tạo trước đó |

Ví dụ dễ nhớ:

- Code gọi Class.forName("com.example.Driver") nhưng driver không được tìm thấy: thường là ClassNotFoundException.
- Bytecode cần com.example.Driver nhưng JAR chứa lớp đó không có khi chạy: thường là NoClassDefFoundError.
- Lớp Configuration đã có nhưng static initializer thất bại ở lần đầu: lần sử dụng sau có thể gặp NoClassDefFoundError với thông báo không thể khởi tạo lớp.

## 5. Compile classpath và runtime classpath khác nhau

Đây là nguyên nhân quan trọng nhất trong ngữ cảnh build.

Compile classpath là tập lớp mà compiler được phép nhìn thấy khi biên dịch mã nguồn. Runtime classpath là tập lớp và tài nguyên mà JVM có thể nạp khi chạy chương trình hoặc test.

Một dependency có thể có trên compile classpath nhưng vắng mặt trên runtime classpath. Khi đó, compiler không báo lỗi nhưng JVM có thể không tìm thấy lớp lúc chạy.

Sơ đồ:

    Mã nguồn Java
         |
         v
    Compile classpath
         |
         v
      javac
         |
         v
       .class
         |
         v
    Runtime classpath
         |
         v
        JVM

Nếu thư viện chỉ có ở compile classpath, bytecode vẫn có thể chứa tham chiếu tới các kiểu của thư viện đó. JVM cần thư viện khi nạp hoặc thực thi phần mã liên quan.

### Ví dụ

Giả sử mã nguồn sử dụng:

    import com.example.payment.PaymentClient;

Compiler tìm thấy PaymentClient vì dependency được khai báo cho compile. Nhưng khi chạy:

    java -cp app.jar com.example.Main

nếu app.jar không chứa PaymentClient và JAR của thư viện không được thêm vào classpath, JVM có thể ném NoClassDefFoundError.

Một build đúng cần bảo đảm dependency cần thiết cho runtime được đưa vào classpath khi chạy hoặc được đóng gói theo cách phù hợp.

## 6. Dependency scope trong Maven có thể tạo khoảng cách classpath

Maven scope quyết định dependency được dùng ở giai đoạn nào và có được truyền tiếp tới consumer hay không.

| Scope | Compile mã nguồn chính | Runtime ứng dụng | Test | Ý nghĩa thường gặp |
| --- | --- | --- | --- | --- |
| compile | Có | Có | Có | Dependency thông thường, được truyền tiếp |
| provided | Có | Thường do môi trường cung cấp | Có | API do container/runtime cung cấp |
| runtime | Không dùng để compile mã chính | Có | Có | Thư viện chỉ cần lúc chạy |
| test | Không | Không | Có | Chỉ dùng cho test |
| system | Có | Có theo cấu hình | Có | Đường dẫn JAR cục bộ; không khuyến khích |

### Dùng provided nhưng runtime không cung cấp

Ví dụ:

    <dependency>
        <groupId>jakarta.servlet</groupId>
        <artifactId>jakarta.servlet-api</artifactId>
        <version>6.0.0</version>
        <scope>provided</scope>
    </dependency>

Scope provided phù hợp khi ứng dụng được triển khai vào servlet container có sẵn Servlet API. Nếu chạy ứng dụng như một tiến trình độc lập mà không có container cung cấp API, lớp có thể bị thiếu lúc chạy.

### Dùng test scope cho dependency cần ở runtime

Nếu một thư viện được khai báo với scope test nhưng mã ứng dụng cần nó khi chạy, thư viện sẽ không nằm trong runtime classpath của ứng dụng. Test có thể chạy vì test classpath bao gồm test dependencies, nhưng ứng dụng triển khai có thể lỗi.

### Dependency bắc cầu bị loại

Một dependency có thể bị loại bằng exclusions hoặc optional. Nếu ứng dụng cần lớp nằm trong dependency bị loại, cần khai báo dependency thích hợp một cách rõ ràng.

Ví dụ:

    <dependency>
        <groupId>com.example</groupId>
        <artifactId>reporting-client</artifactId>
        <version>2.1.0</version>
        <exclusions>
            <exclusion>
                <groupId>com.example</groupId>
                <artifactId>shared-core</artifactId>
            </exclusion>
        </exclusions>
    </dependency>

Nếu reporting-client cần shared-core ở runtime và ứng dụng không cung cấp version khác, có thể gặp lỗi nạp lớp.

## 7. Dependency configuration trong Gradle

Gradle phân biệt các configuration dùng cho compile và runtime.

Một số configuration phổ biến với Java Plugin:

| Configuration | Vai trò |
| --- | --- |
| implementation | Dependency nội bộ của module, dùng cho compile và runtime |
| api | Dependency được công khai qua API của library module |
| compileOnly | Có khi biên dịch, không tự có trong runtime |
| runtimeOnly | Chỉ cần khi chạy |
| testImplementation | Dependency của mã test |
| testRuntimeOnly | Dependency chỉ cần khi chạy test |

### compileOnly có thể gây thiếu lớp lúc chạy

Ví dụ:

    dependencies {
        compileOnly 'com.example:payment-api:1.2.0'
    }

Nếu mã ứng dụng dùng PaymentClient từ dependency này nhưng runtime không cung cấp JAR tương ứng, JVM có thể ném NoClassDefFoundError.

compileOnly phù hợp cho annotation API hoặc API do môi trường chạy cung cấp, với điều kiện runtime thật sự có chúng.

### runtimeOnly cho implementation được nạp lúc chạy

Ví dụ JDBC driver:

    dependencies {
        runtimeOnly 'org.postgresql:postgresql:42.7.3'
    }

Driver có thể được nạp qua DriverManager hoặc service provider. Nó không nhất thiết cần cho compile nếu mã ứng dụng chỉ dùng JDBC API chuẩn do JDK cung cấp.

Nếu driver không có trong runtime classpath, ứng dụng có thể không tìm thấy driver phù hợp hoặc không tải được implementation.

### Kiểm tra configuration phù hợp

Để xem runtime classpath:

    ./gradlew dependencies --configuration runtimeClasspath

Để xem compile classpath:

    ./gradlew dependencies --configuration compileClasspath

Với test:

    ./gradlew dependencies --configuration testRuntimeClasspath

Nếu dependency có trong compileClasspath nhưng không có trong runtimeClasspath, hãy xem nó được khai báo bằng compileOnly, bị exclude hoặc không được truyền tiếp như mong muốn.

## 8. Vì sao test chạy được nhưng ứng dụng triển khai lại lỗi?

Test runtime classpath thường chứa nhiều dependency hơn runtime của artifact chính:

- Test framework và engine.
- Mock library.
- Test fixture.
- Dependency chỉ khai báo testImplementation hoặc test scope.
- Các cấu hình bổ sung do plugin test thêm vào.

Một lớp có thể tồn tại khi chạy test nhưng không có trong gói ứng dụng. Vì vậy, test pass không chứng minh gói triển khai có đầy đủ dependency.

Ví dụ:

    dependencies {
        testImplementation 'com.example:payment-sdk:3.0.0'
    }

Test sử dụng PaymentClient và chạy thành công. Nhưng mã ứng dụng cũng gọi PaymentClient lúc runtime, trong khi dependency chỉ thuộc testImplementation. Artifact production không có thư viện đó và có thể lỗi.

Nếu thư viện thực sự cần trong production, khai báo bằng implementation hoặc api phù hợp. Không nên dựa vào test classpath để bù dependency bị thiếu trong runtime.

## 9. Dependency có trong graph nhưng không có trong artifact

Một dependency được resolve thành công không có nghĩa JAR của nó đã được nhúng vào artifact chính.

Ví dụ, Gradle hoặc Maven thường tạo một JAR mỏng (thin JAR) chỉ chứa lớp và tài nguyên của chính project. Các dependency nằm riêng và phải được cung cấp qua classpath hoặc một cơ chế phân phối khác.

### Chạy JAR mỏng

Lệnh:

    java -jar app.jar

chỉ hoạt động nếu manifest và cách đóng gói cung cấp đủ thông tin classpath, hoặc JAR tự chứa mọi lớp cần thiết. Nếu JAR mỏng không khai báo dependency, JVM có thể không tìm thấy lớp bên ngoài.

Một cách chạy với dependency riêng:

    java -cp "app.jar;lib/*" com.example.Main

Trên Linux/macOS, dấu phân cách classpath thường là dấu hai chấm:

    java -cp "app.jar:lib/*" com.example.Main

Dấu phân cách classpath trên Windows là dấu chấm phẩy; trên Unix-like là dấu hai chấm.

### Fat JAR hoặc uber JAR

Fat JAR/uber JAR đóng gói ứng dụng cùng dependency theo một cấu trúc được plugin hỗ trợ. Ví dụ Spring Boot executable JAR thường chứa dependency trong BOOT-INF/lib và dùng launcher riêng để thiết lập class loader.

Nếu plugin đóng gói không chạy, cấu hình sai hoặc dependency bị exclude, JAR cuối cùng có thể thiếu lớp dù dependency graph ở giai đoạn build có đầy đủ.

Hãy kiểm tra nội dung artifact cuối, không chỉ kiểm tra dependency report.

## 10. Kiểm tra nội dung JAR và classpath

### Liệt kê nội dung JAR

Dùng lệnh:

    jar tf app.jar

Tìm lớp cần thiết, ví dụ:

    com/example/payment/PaymentClient.class

Nếu không có lớp đó trong JAR chính, hãy kiểm tra xem nó thuộc một dependency JAR riêng hay cần được đóng gói vào fat JAR.

### Xem manifest

Có thể xem manifest bằng:

    jar xf app.jar META-INF/MANIFEST.MF

Sau đó đọc:

    META-INF/MANIFEST.MF

Với executable JAR truyền thống, thuộc tính Main-Class xác định lớp entry point. Thuộc tính Class-Path có thể liệt kê các JAR phụ thuộc theo URL tương đối. Cơ chế đóng gói khác như Spring Boot có launcher và cấu trúc riêng.

### Kiểm tra classpath lúc chạy

Nếu chạy qua script, service hoặc container, hãy xem chính xác command line và biến môi trường:

- Đối số -cp hoặc -classpath.
- Biến CLASSPATH nếu được sử dụng.
- Working directory ảnh hưởng đường dẫn tương đối.
- Manifest Class-Path.
- Thư mục lib và các JAR thực sự có mặt.
- Class loader hoặc launcher do framework cung cấp.

Không nên chỉ kiểm tra classpath trong IDE. IDE có thể tự thêm dependency mà script triển khai hoặc lệnh java trực tiếp không có.

## 11. Dependency bắc cầu và xung đột version

Một lớp có thể bị thiếu vì dependency bắc cầu không được đưa vào runtime hoặc version được chọn không tương thích.

Ví dụ:

    application
       +----> reporting-client
       |          +----> shared-core:1.8
       |
       +----> http-adapter
                  +----> shared-core:2.0

Build tool chọn một version theo quy tắc resolution. Nếu version được chọn không chứa lớp hoặc phương thức mà thư viện khác cần, có thể xảy ra lỗi liên kết.

Lỗi NoClassDefFoundError có thể xuất hiện khi lớp phụ thuộc bị thiếu. Nếu lớp có tồn tại nhưng API không tương thích, lỗi khác như NoSuchMethodError hoặc AbstractMethodError có thể xuất hiện.

### Maven

Xem cây dependency:

    mvn dependency:tree

Chỉ xem dependency liên quan:

    mvn dependency:tree -Dincludes=com.example:shared-core

Kiểm tra scope runtime:

    mvn dependency:tree -Dscope=runtime

Kiểm tra version được chọn, exclusion và scope. Nếu dependency cần cho runtime nhưng bị loại, hãy khai báo trực tiếp version tương thích hoặc điều chỉnh exclusion.

### Gradle

Xem runtime graph:

    ./gradlew dependencies --configuration runtimeClasspath

Giải thích một module:

    ./gradlew dependencyInsight --dependency shared-core --configuration runtimeClasspath

Lệnh dependencyInsight giúp xem version được yêu cầu, version được chọn và nguyên nhân chọn version. Nếu module không xuất hiện trong runtimeClasspath, hãy lần ngược configuration khai báo và các rule exclude.

## 12. Class loader có thể nhìn thấy những lớp nào?

Ngay cả khi JAR tồn tại trên máy, class loader đang thực hiện yêu cầu vẫn có thể không nhìn thấy nó.

Java có thể có nhiều class loader:

- Bootstrap class loader: nạp các lớp nền tảng cốt lõi.
- Platform class loader: nạp các module nền tảng bổ sung.
- Application class loader: thường nạp lớp từ application classpath.
- Custom class loader: framework, plugin system hoặc container có thể tạo loader riêng.

Một ứng dụng server có thể có class loader riêng cho từng web application. Plugin framework có thể dùng loader riêng để cô lập dependency. Một JAR nằm trên classpath của ứng dụng chính chưa chắc được nhìn thấy bởi class loader con hoặc loader của plugin theo mọi chiều.

### Context class loader

Một số framework dùng thread context class loader để tìm provider, tài nguyên hoặc implementation. Nếu code chạy trong thread có context class loader khác với loader dự kiến, Class.forName hoặc ServiceLoader có thể không tìm thấy lớp.

Ví dụ:

    ClassLoader loader = Thread.currentThread().getContextClassLoader();
    Class<?> type = loader.loadClass("com.example.plugins.CsvPlugin");

Nếu loader không có quyền nhìn thấy JAR chứa CsvPlugin, lệnh có thể ném ClassNotFoundException.

Khi điều tra plugin hoặc ứng dụng server, hãy xác định loader nào đang thực hiện việc nạp, thay vì chỉ kiểm tra xem JAR có tồn tại ở đâu đó.

## 13. JPMS và module path

Java Platform Module System bổ sung module path và các quy tắc readability/exports. Một lớp có thể tồn tại trong module nhưng module hiện tại không đọc được module đó hoặc package không được export theo cách cần thiết.

Lỗi do module access thường có thể là FindException, LayerInstantiationException, IllegalAccessError hoặc các lỗi liên quan module, không nhất thiết là ClassNotFoundException/NoClassDefFoundError. Tuy vậy, cấu hình module path sai cũng có thể khiến module hoặc lớp không được tìm thấy trong quá trình khởi động.

Khi ứng dụng dùng module-info.java, cần kiểm tra:

- Module path có chứa module cần thiết không.
- Module name có đúng với tên được yêu cầu không.
- Module có được resolve trong configuration hiện tại không.
- requires có khai báo module cần dùng không.
- Package có được export/open theo yêu cầu không.
- Có nhầm lẫn giữa classpath và module path không.

Không nên sửa mọi lỗi nạp lớp bằng cách chuyển tất cả dependency sang classpath. Hãy xác định dự án đang chạy theo classpath hay module path và đọc thông báo module cụ thể.

## 14. ClassNotFoundException do framework hoặc service loading

Một số thư viện không tham chiếu trực tiếp implementation trong bytecode mà tìm lớp theo tên hoặc qua service provider.

Ví dụ:

    Class.forName("org.postgresql.Driver");

Nếu JDBC driver không có trên runtime classpath, lệnh có thể ném ClassNotFoundException.

Một số thư viện hiện đại tự đăng ký JDBC driver qua Service Provider Interface. Khi đó, code ứng dụng có thể không gọi Class.forName trực tiếp. Nhưng driver JAR và file metadata service vẫn phải có trong runtime artifact/classpath.

Tương tự, ServiceLoader:

    ServiceLoader<MyPlugin> plugins = ServiceLoader.load(MyPlugin.class);

cần implementation và metadata provider phù hợp. Nếu provider không có hoặc class loader không nhìn thấy nó, framework có thể không tìm được implementation. Một số framework sẽ ném exception riêng thay vì ClassNotFoundException.

Khi framework báo không tìm thấy plugin, driver hoặc provider, hãy kiểm tra cả:

- JAR implementation.
- File META-INF/services.
- Class loader dùng để tìm provider.
- Cách đóng gói fat JAR/shaded JAR có giữ hoặc gộp service metadata không.

## 15. Annotation processor và dependency chỉ có lúc compile

Một số thư viện chỉ cần trong quá trình biên dịch, chẳng hạn annotation processor. Chúng có thể được khai báo trên annotation processor path thay vì runtime classpath.

Ví dụ Lombok:

    dependencies {
        compileOnly 'org.projectlombok:lombok:1.18.32'
        annotationProcessor 'org.projectlombok:lombok:1.18.32'
    }

Lombok xử lý annotation khi compile và thường không cần trong runtime. Nếu một thư viện annotation chỉ dùng để sinh mã, việc không có nó lúc chạy là bình thường.

Nhưng nếu mã ứng dụng trực tiếp sử dụng một lớp runtime của thư viện được khai báo compileOnly, thì runtime có thể thiếu lớp đó. Cần phân biệt dependency chỉ phục vụ compiler với dependency được bytecode hoặc framework cần lúc chạy.

## 16. Lỗi do đóng gói hoặc shading

Các plugin tạo fat JAR, shaded JAR hoặc executable archive có thể:

- Không đưa dependency vào gói.
- Loại dependency theo filter.
- Đổi tên package bằng relocation.
- Không gộp metadata service đúng cách.
- Ghi đè tài nguyên hoặc manifest.
- Tạo artifact khác với artifact mà pipeline triển khai.

Ví dụ Maven Shade Plugin có thể relocate:

    <relocations>
        <relocation>
            <pattern>com.example.internal</pattern>
            <shadedPattern>com.example.app.internal</shadedPattern>
        </relocation>
    </relocations>

Nếu code hoặc metadata vẫn tham chiếu tên lớp cũ nhưng lớp đã được relocate, class loading có thể thất bại. Relocation cần xử lý cả các tham chiếu trong bytecode và một số metadata/tệp cấu hình chứa tên lớp.

Với Spring Boot executable JAR, dependency thường nằm trong BOOT-INF/lib và được launcher xử lý. Không thể giả định mọi lớp dependency phải nằm ở root của JAR.

Hãy kiểm tra artifact được tạo sau cùng bằng jar tf, đọc manifest và xác nhận đúng file được triển khai. Artifact ở target/, build/libs/ và artifact đã upload có thể không giống nhau nếu pipeline có bước repackage hoặc copy riêng.

## 17. Đọc stack trace theo đúng thứ tự

Khi gặp lỗi, hãy tìm:

1. Loại exception/error ở dòng đầu.
2. Tên lớp đầy đủ bị thiếu.
3. Dòng code đầu tiên trong ứng dụng hoặc framework yêu cầu lớp đó.
4. Cause lồng bên trong.
5. Có ExceptionInInitializerError trước đó hay không.
6. Lỗi xuất hiện trong test, khi khởi động ứng dụng, khi gọi một chức năng hay khi nạp plugin.

Ví dụ:

    Exception in thread "main" java.lang.NoClassDefFoundError: com/example/PaymentClient
        at com.example.app.Main.main(Main.java:12)
    Caused by: java.lang.ClassNotFoundException: com.example.PaymentClient
        at java.base/jdk.internal.loader.BuiltinClassLoader.loadClass(...)

Stack trace cho thấy JVM không thể tìm PaymentClient. Cause cho thấy class loader đã không tìm thấy lớp. Tiếp theo cần xác định artifact nào cung cấp lớp và tại sao artifact đó không có trong runtime classpath.

Một số thông báo có thể chứa dấu gạch chéo thay cho dấu chấm trong tên lớp, ví dụ com/example/PaymentClient. Đây là cách JVM biểu diễn internal name trong một số lỗi liên kết.

## 18. Các lệnh chẩn đoán hữu ích

### Maven

Xem cây dependency:

    mvn dependency:tree

Chỉ xem runtime dependency:

    mvn dependency:tree -Dscope=runtime

Lọc một artifact:

    mvn dependency:tree -Dincludes=com.example:payment-client

Xem classpath runtime có thể được tạo:

    mvn dependency:build-classpath -Dmdep.outputFile=runtime-classpath.txt

Xem POM hiệu lực:

    mvn help:effective-pom

Chạy với log chi tiết:

    mvn -X test

Lưu ý: dependency:build-classpath chỉ tạo danh sách classpath từ dependency theo cấu hình plugin; hãy kiểm tra đúng scope và module. Nó không chứng minh artifact đóng gói cuối cùng có đầy đủ thư viện.

### Gradle

Xem runtime dependency:

    ./gradlew dependencies --configuration runtimeClasspath

Xem test runtime dependency:

    ./gradlew dependencies --configuration testRuntimeClasspath

Giải thích module:

    ./gradlew dependencyInsight --dependency payment-client --configuration runtimeClasspath

Chạy task với log:

    ./gradlew run --info

Xem các task của project:

    ./gradlew tasks

Nếu project dùng application plugin, task run thường thiết lập runtime classpath theo cấu hình application. Nếu chạy main class thủ công bằng java -cp, cần bảo đảm classpath được dựng giống cấu hình đó.

### Kiểm tra JAR

    jar tf payment-client.jar

Tìm lớp cụ thể:

    jar tf payment-client.jar | findstr PaymentClient

Trên Linux/macOS có thể dùng grep thay findstr.

### Theo dõi class loading

Với JDK 9 trở lên:

    java -Xlog:class+load=info -cp "app.jar;lib/*" com.example.Main

Với JDK cũ:

    java -verbose:class -cp "app.jar;lib/*" com.example.Main

Log class loading giúp xác định lớp được nạp từ đâu và liệu JVM có thử tìm lớp hay không. Output có thể rất dài; hãy lọc theo tên package hoặc lớp cần điều tra.

## 19. Ví dụ: Maven compile thành công nhưng runtime thiếu dependency

Giả sử project dùng PaymentClient:

    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>payment-sdk</artifactId>
            <version>3.0.0</version>
            <scope>provided</scope>
        </dependency>
    </dependencies>

Mã nguồn:

    import com.example.payment.PaymentClient;

    public class Main {
        public static void main(String[] args) {
            new PaymentClient().charge();
        }
    }

Maven compile có thể thành công vì provided dependency có trên compile classpath. Nhưng khi chạy:

    java -cp target/app.jar com.example.Main

nếu môi trường không cung cấp payment-sdk, JVM có thể ném NoClassDefFoundError.

Quy trình điều tra:

1. Xác nhận scope của payment-sdk trong POM.
2. Xem mvn dependency:tree -Dscope=runtime.
3. Kiểm tra artifact triển khai có chứa hoặc tham chiếu payment-sdk không.
4. Xác định runtime có cung cấp thư viện này không.
5. Nếu ứng dụng phải tự mang dependency, đổi scope sang compile hoặc dùng cấu hình đóng gói phù hợp.
6. Chạy lại test và kiểm tra artifact cuối.

Không đổi provided thành compile một cách máy móc nếu môi trường triển khai thực sự cung cấp thư viện. Khi đó, cần kiểm tra version của thư viện trên container/server có tương thích hay không.

## 20. Ví dụ: Gradle compileOnly gây lỗi lúc chạy

Giả sử build.gradle:

    plugins {
        id 'application'
    }

    dependencies {
        compileOnly 'com.example:payment-sdk:3.0.0'
    }

Mã nguồn sử dụng PaymentClient. Compile thành công vì dependency có trong compileClasspath. Nhưng application runtimeClasspath không có payment-sdk.

Kiểm tra:

    ./gradlew dependencies --configuration compileClasspath
    ./gradlew dependencies --configuration runtimeClasspath

Nếu thư viện phải có khi chạy, khai báo:

    dependencies {
        implementation 'com.example:payment-sdk:3.0.0'
    }

Nếu chỉ cần lúc runtime và không cần compile, có thể dùng runtimeOnly. Chọn configuration dựa trên cách mã nguồn và ứng dụng sử dụng thư viện.

## 21. Ví dụ: ClassNotFoundException do nạp plugin theo tên

Giả sử ứng dụng có cấu hình:

    plugin.class=com.example.plugins.CsvPlugin

Và code:

    String pluginName = properties.getProperty("plugin.class");
    Class<?> pluginType = Class.forName(pluginName);

Nếu JAR plugin không được đặt trong thư mục plugins hoặc không được thêm vào class loader, ứng dụng có thể ném ClassNotFoundException.

Trong trường hợp plugin được tải từ thư mục riêng, việc thêm JAR vào application classpath có thể chưa đủ nếu plugin loader sử dụng URLClassLoader riêng. Hãy kiểm tra:

- Đường dẫn thư mục plugin.
- JAR có tồn tại và đọc được không.
- Package và tên lớp có chính xác không.
- Class loader nào thực hiện loadClass.
- Plugin có dependency bắc cầu riêng không.
- Plugin API mà ứng dụng cung cấp có tương thích không.

Nếu dùng URLClassLoader, hãy kiểm tra URL thực tế và quyền truy cập file. Tránh giả định working directory luôn là thư mục chứa ứng dụng.

## 22. Ví dụ: NoClassDefFoundError do static initialization

Giả sử:

    public class Settings {
        static final String ENDPOINT = loadEndpoint();

        private static String loadEndpoint() {
            String value = System.getenv("PAYMENT_ENDPOINT");
            if (value == null) {
                throw new IllegalStateException("PAYMENT_ENDPOINT is required");
            }
            return value;
        }
    }

Nếu biến môi trường không tồn tại, lần đầu JVM khởi tạo Settings có thể phát sinh ExceptionInInitializerError với nguyên nhân là IllegalStateException. Nếu code tiếp tục tham chiếu Settings sau đó, có thể thấy:

    NoClassDefFoundError: Could not initialize class com.example.Settings

Trong trường hợp này, file Settings.class không bị thiếu. Nguyên nhân là static initialization thất bại. Hãy tìm lỗi đầu tiên trong log và sửa cấu hình môi trường hoặc logic khởi tạo.

Không nên chỉ thêm JAR hoặc thay classpath khi thông báo có cụm Could not initialize class.

## 23. Những nguyên nhân phổ biến và cách xử lý

| Nguyên nhân | Dấu hiệu | Hướng xử lý |
| --- | --- | --- |
| Dependency chỉ có trên compile classpath | Compile pass, runtime thiếu lớp | Kiểm tra Maven scope hoặc Gradle compileOnly; khai báo runtime phù hợp |
| Dependency test-only | Test pass nhưng ứng dụng triển khai lỗi | Đưa dependency cần cho production vào configuration chính |
| Dependency bắc cầu bị exclude/optional | Một lớp của thư viện con bị thiếu | Xem dependency tree và khai báo dependency cần thiết |
| Artifact đóng gói thiếu JAR | Dependency graph có nhưng gói chạy không có | Kiểm tra thin/fat JAR, manifest, plugin repackage và thư mục lib |
| Chạy sai classpath | IDE chạy được, command line lỗi | So sánh lệnh chạy và runtimeClasspath thực tế |
| Sai tên/package/chữ hoa | Class.forName không tìm thấy lớp | Dùng tên đầy đủ và kiểm tra case-sensitive |
| Plugin/class loader riêng | JAR tồn tại nhưng loader không nhìn thấy | Kiểm tra loader, URL, thư mục plugin và context class loader |
| Thiếu dependency của dependency | Lớp chính có nhưng kiểu phụ thuộc bị thiếu | Xem stack trace và runtime dependency graph |
| Static initializer thất bại | NoClassDefFoundError: Could not initialize class | Tìm ExceptionInInitializerError đầu tiên và sửa nguyên nhân |
| Shading/relocation sai | Lớp hoặc service metadata không còn đúng tên | Kiểm tra cấu hình shade, relocation và META-INF/services |
| Module path/readability | Lỗi resolve hoặc truy cập module | Kiểm tra module path, requires, exports và module name |
| JAR sai phiên bản | Có lớp nhưng binary không tương thích | Kiểm tra version được chọn và các lỗi LinkageError khác |

## 24. Quy trình điều tra có hệ thống

Khi gặp ClassNotFoundException hoặc NoClassDefFoundError, hãy thực hiện theo thứ tự:

1. **Ghi nhận lỗi chính xác:** exception/error, tên lớp, cause và stack trace đầu tiên.
2. **Xác định thời điểm:** compile, test, khởi động ứng dụng, gọi chức năng hay tải plugin.
3. **Xác định artifact sở hữu lớp:** tìm JAR nào chứa package/class.
4. **Kiểm tra compile classpath:** dependency có được compiler nhìn thấy không?
5. **Kiểm tra runtime classpath:** dependency có được cung cấp lúc chạy không?
6. **Kiểm tra dependency graph:** scope, configuration, version, exclusion và dependency bắc cầu.
7. **Kiểm tra artifact cuối:** JAR/WAR/container có chứa hoặc tham chiếu đúng dependency không?
8. **Kiểm tra class loader/module:** loader nào đang tìm lớp, classpath hay module path?
9. **Kiểm tra khởi tạo lớp:** có ExceptionInInitializerError hoặc lỗi cấu hình trước đó không?
10. **Chạy lại đúng môi trường:** dùng command line và runtime giống môi trường triển khai, không chỉ IDE.

Một cách tiếp cận hữu ích là bắt đầu từ tên lớp trong lỗi, tìm artifact chứa lớp, rồi đi ngược về dependency khai báo artifact đó. Không nên bắt đầu bằng cách thêm tất cả JAR vào classpath vì điều đó có thể che mất dependency graph sai hoặc xung đột version.

## 25. Phòng tránh lỗi trong CI và quy trình phát hành

Để giảm lỗi thiếu lớp chỉ xuất hiện sau khi build:

- Dùng scope/configuration đúng với thời điểm dependency được cần.
- Kiểm tra runtimeClasspath thay vì chỉ compileClasspath.
- Chạy test và smoke test từ artifact đã đóng gói, không chỉ từ IDE.
- Kiểm tra JAR/WAR/container cuối cùng trong CI.
- Dùng dependency tree để phát hiện exclusion và conflict.
- Cố định version dependency và plugin.
- Không dựa vào dependency vô tình có trên máy developer.
- Kiểm tra classpath và environment variables trong script triển khai.
- Với plugin, kiểm tra class loader và metadata service.
- Với ứng dụng dùng JPMS, xác minh module path và module descriptors.

Một pipeline có thể có các bước:

    Compile
       |
       v
    Unit tests
       |
       v
    Package artifact
       |
       v
    Inspect package/runtime dependencies
       |
       v
    Launch smoke test from packaged artifact
       |
       v
    Publish/deploy

Smoke test nên chạy bằng đúng cách khởi động mà môi trường triển khai sử dụng. Nếu production chạy java -jar hoặc container image, hãy kiểm tra chính artifact hoặc image đó thay vì chỉ chạy main class với classpath do IDE tạo.

## 26. Kết luận

ClassNotFoundException thường xuất hiện khi một class loader được yêu cầu nạp lớp theo tên nhưng không tìm thấy lớp. NoClassDefFoundError thường xuất hiện khi JVM cần một định nghĩa lớp để liên kết hoặc thực thi nhưng không thể cung cấp nó; nó cũng có thể xuất hiện sau khi static initialization của lớp thất bại.

Trong build Java, nguyên nhân thường gặp là compile classpath khác runtime classpath, dependency scope không phù hợp, dependency bắc cầu bị loại, artifact đóng gói thiếu thư viện hoặc class loader không nhìn thấy JAR. Hãy đọc stack trace, xác định lớp và artifact, so sánh compile/runtime dependency graph, kiểm tra nội dung gói cuối và chạy smoke test từ đúng artifact triển khai. Cách lần theo chuỗi đó giúp sửa nguyên nhân gốc thay vì chỉ thêm JAR một cách thử-và-sai.
