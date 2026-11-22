# Phân biệt nâng cấp runtime, biên dịch lại và hiện đại hóa mã nguồn

Trong một dự án Java, cụm từ “nâng cấp Java” thường chỉ nhiều công việc khác nhau: thay phiên bản JVM đang chạy ứng dụng, biên dịch lại ứng dụng bằng JDK mới, hoặc sửa mã nguồn để sử dụng API và cách viết hiện đại hơn. Ba việc này có liên quan nhưng không đồng nghĩa. Nếu gộp chúng thành một thay đổi duy nhất, nhóm phát triển sẽ khó xác định nguyên nhân khi có lỗi và khó biết chính xác phạm vi kiểm thử cần thực hiện.

Bài học này phân biệt ba loại thay đổi trong bối cảnh **Java Advance Compatibility Migration**, thuộc chương **Tổng quan chuyển đổi**. Mục tiêu là giúp xác định một kế hoạch chuyển đổi đang thay đổi lớp nào của hệ thống, mức tương thích nào cần giữ và bằng chứng nào cần thu thập trước khi triển khai.

## 1. Nhìn vào các lớp của một ứng dụng Java

Một ứng dụng Java đi qua chuỗi bước từ mã nguồn đến môi trường chạy:

~~~text
Mã nguồn Java
    |
    | JDK compiler + build tool + dependency
    v
Bytecode (.class) và gói ứng dụng (JAR/WAR)
    |
    | JVM + thư viện nền tảng + cấu hình + hệ điều hành
    v
Ứng dụng đang chạy
~~~

Mỗi lớp có thể được thay đổi độc lập ở một mức độ nhất định:

- **Mã nguồn** là các tệp .java, cấu trúc package, cách gọi API và logic nghiệp vụ.
- **Môi trường biên dịch** gồm JDK dùng để chạy compiler, compiler options, annotation processor, Gradle hoặc Maven và các plugin build.
- **Bytecode** là kết quả biên dịch trong các tệp .class; JAR/WAR đóng gói bytecode cùng tài nguyên và có thể chứa thư viện phụ thuộc.
- **Môi trường chạy** gồm JVM, các thư viện Java đi kèm runtime, tham số JVM, hệ điều hành, chứng thư, locale, timezone và các cấu hình triển khai.
- **Thư viện phụ thuộc** có thể có yêu cầu JDK hoặc runtime riêng, kể cả khi mã nguồn ứng dụng không trực tiếp dùng tính năng mới.

Vì vậy, cần phân biệt ít nhất ba phiên bản thường bị gọi chung là “version Java”:

1. **JDK dùng để chạy công cụ build**: phiên bản Java chạy Gradle hoặc Maven.
2. **JDK dùng để biên dịch**: phiên bản compiler thực sự được chọn cho task compile.
3. **Phiên bản đích của bytecode và API**: phiên bản Java mà sản phẩm được biên dịch để hỗ trợ.

Ngoài ra còn có **JVM dùng để chạy ứng dụng trong production**. Phiên bản này có thể giống hoặc khác JDK dùng để build. Một máy build chạy JDK 21 hoàn toàn có thể tạo bytecode hướng đến Java 17, rồi ứng dụng được chạy trên Java 17 nếu mã nguồn, API và toàn bộ dependency đều đáp ứng giới hạn đó.

Đây là nền tảng để phân biệt ba hoạt động dưới đây.

## 2. Ba hoạt động và định nghĩa chính xác

### 2.1. Nâng cấp runtime (runtime upgrade)

Nâng cấp runtime là thay đổi môi trường thực thi ứng dụng sang phiên bản JVM hoặc Java runtime mới hơn. Mục tiêu trực tiếp là chạy **artifact hiện có** trên môi trường mới.

Ví dụ:

- Ứng dụng đã được đóng gói thành **orders-service.jar** với bytecode Java 17.
- Nhóm vận hành thay image container từ một bản phân phối Java 17 sang Java 21.
- Nhóm triển khai chạy lại chính JAR đó trên JVM 21 mà không biên dịch lại mã nguồn.

Trong trường hợp này, thay đổi chính nằm ở môi trường chạy. Mã nguồn và artifact có thể được giữ nguyên.

Nâng cấp runtime có thể đem lại:

- Bản vá bảo mật và sửa lỗi của JVM.
- Garbage Collector, JIT compiler và hiệu năng runtime được cải thiện.
- Hỗ trợ TLS, cipher suite, thuật toán mã hóa và chứng thư mới.
- Hỗ trợ tốt hơn cho hệ điều hành, kiến trúc CPU hoặc nền tảng triển khai mới.
- Khả năng vận hành và giám sát phù hợp hơn với hạ tầng hiện tại.

Tuy nhiên, việc JVM mới có thể đọc bytecode cũ **không đồng nghĩa ứng dụng chắc chắn chạy đúng**. Runtime mới có thể thay đổi hành vi mặc định, loại bỏ tùy chọn JVM cũ, siết chặt truy cập nội bộ, cập nhật thư viện nền tảng hoặc thay đổi cách xử lý một số trường hợp biên.

Một số vùng cần kiểm tra khi nâng runtime:

| Vùng thay đổi | Rủi ro có thể gặp |
|---|---|
| API nền tảng | API đã bị loại bỏ hoặc không còn được hỗ trợ |
| Reflection và module | Truy cập sâu vào package nội bộ bị chặn hoặc cần cấu hình rõ ràng |
| JVM options | Cờ JVM cũ bị loại bỏ, đổi tên hoặc thay đổi ý nghĩa |
| TLS và bảo mật | Cipher, giao thức hoặc thuật toán cũ không còn được bật mặc định |
| Charset, locale, timezone | Kết quả đọc/ghi dữ liệu hoặc định dạng có thể khác |
| Garbage Collector và JIT | Độ trễ, mức sử dụng bộ nhớ hoặc thông lượng thay đổi |
| JNI và native library | Thư viện native không tương thích với kiến trúc hoặc runtime mới |
| Thư viện bên thứ ba | Dependency có thể không hỗ trợ JVM mục tiêu |

Một ví dụ đáng chú ý là thay đổi mặc định về charset. Từ Java 18, UTF-8 trở thành charset mặc định trong nhiều môi trường theo JEP 400. Một ứng dụng trước đó dựa vào charset mặc định của máy để đọc tệp có thể cho kết quả khác sau khi nâng runtime. Nếu định dạng dữ liệu yêu cầu một charset cụ thể, ứng dụng nên chỉ định charset đó tường minh thay vì dựa vào mặc định của máy.

**Kết luận của runtime upgrade:** artifact không nhất thiết phải được tạo lại, nhưng hành vi của ứng dụng vẫn có thể thay đổi vì JVM và thư viện nền tảng đã thay đổi. Do đó, kiểm thử trên runtime đích là bắt buộc.

### 2.2. Biên dịch lại (recompilation)

Biên dịch lại là chạy compiler trên mã nguồn để tạo bytecode và artifact mới. Hoạt động này có thể thực hiện mà không thay đổi logic hoặc cấu trúc mã nguồn.

Ví dụ:

- Mã nguồn vẫn được viết theo Java 17.
- Nhóm build chuyển sang dùng JDK 21 để chạy compiler.
- Compiler tạo artifact mới với phiên bản đích Java 17.
- Artifact mới tiếp tục được triển khai trên JVM 17.

Trong ví dụ này, **JDK compiler đã thay đổi nhưng runtime production và phiên bản đích của bytecode có thể không đổi**.

Biên dịch lại thường được thực hiện để:

- Chuyển toolchain build sang JDK được tổ chức hỗ trợ.
- Tạo artifact mới từ mã nguồn đã lưu trong repository.
- Cập nhật compiler, annotation processor hoặc plugin build.
- Kiểm tra mã nguồn có còn biên dịch được với compiler mới hay không.
- Tạo bytecode cho một phiên bản Java đích cụ thể.
- Tái tạo artifact để phục vụ quy trình phát hành có thể lặp lại.

Điểm quan trọng là phải phân biệt **JDK chạy compiler** với **release đích**. Ví dụ, JDK 21 có thể biên dịch mã nguồn cho Java 17 bằng tùy chọn **--release 17**. Khi đó compiler giới hạn cú pháp và API theo release 17, đồng thời tạo class file tương thích với Java 17.

~~~bash
javac --release 17 -d out src/com/example/Main.java
~~~

Nếu bỏ tùy chọn release và dùng compiler JDK 21 theo cấu hình mặc định, kết quả thường hướng đến Java 21. Artifact đó có thể không chạy được trên JVM 17.

Trong JDK 9 trở lên, nên ưu tiên **--release** thay vì chỉ kết hợp **-source** và **-target**. Hai tùy chọn -source và -target kiểm soát mức cú pháp và phiên bản class file, nhưng nếu cấu hình không giới hạn API nền tảng đúng cách, mã nguồn vẫn có thể vô tình gọi API chỉ tồn tại ở JDK mới hơn. --release giải quyết đồng thời giới hạn ngôn ngữ, bytecode và API nền tảng của release được chọn.

Biên dịch lại cũng có thể phát hiện hoặc tạo ra vấn đề:

- Mã nguồn cũ không còn biên dịch do compiler hoặc API thay đổi.
- Annotation processor sinh mã khác hoặc không tương thích với JDK mới.
- Plugin build chưa hỗ trợ JDK đang dùng để chạy Gradle/Maven.
- Dependency được nâng phiên bản gián tiếp hoặc được phân giải khác do cấu hình build thay đổi.
- Cảnh báo mới xuất hiện, chẳng hạn API deprecated hoặc thao tác không an toàn.
- Artifact mới có thể khác artifact cũ dù mã nguồn không đổi, do compiler, dependency hoặc quy trình đóng gói đã thay đổi.

Vì thế, “chỉ biên dịch lại” vẫn là một thay đổi có thể tác động đến sản phẩm. Cần cố định dependency, toolchain, compiler options và quy trình đóng gói để có thể giải thích sự khác biệt giữa hai artifact.

### 2.3. Hiện đại hóa mã nguồn (source modernization)

Hiện đại hóa mã nguồn là chủ động chỉnh sửa mã nguồn để cải thiện cách viết, API, cấu trúc, khả năng bảo trì, an toàn hoặc hiệu quả. Đây là thay đổi ở tầng mã nguồn và thường cần biên dịch lại để tạo artifact mới.

Hiện đại hóa có thể bao gồm:

- Thay API đã lỗi thời bằng API được khuyến nghị.
- Dùng **java.time** thay cho các API ngày giờ cũ khi phù hợp.
- Dùng try-with-resources để quản lý tài nguyên.
- Dùng generic, lambda, Stream API hoặc các cấu trúc ngôn ngữ phù hợp với phiên bản Java mục tiêu.
- Dùng record cho kiểu dữ liệu thuần dữ liệu khi ngữ nghĩa của record phù hợp.
- Dùng switch expression hoặc pattern matching khi giúp biểu đạt logic rõ ràng hơn.
- Cải thiện xử lý ngoại lệ, null, đồng thời và quản lý tài nguyên.
- Loại bỏ phụ thuộc vào API nội bộ của JDK.
- Tách trách nhiệm, giảm coupling và làm rõ ranh giới module.

Ví dụ, một đoạn mã cũ tự đóng tài nguyên:

~~~java
BufferedReader reader = null;
try {
    reader = new BufferedReader(new FileReader(path));
    return reader.readLine();
} finally {
    if (reader != null) {
        reader.close();
    }
}
~~~

Có thể được hiện đại hóa thành:

~~~java
try (BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    return reader.readLine();
}
~~~

Thay đổi này vừa dùng try-with-resources, vừa chỉ định charset rõ ràng. Tuy nhiên, cần xác nhận charset của dữ liệu thực tế trước khi thay đổi; không nên đổi cách giải mã dữ liệu chỉ vì muốn dùng API mới.

Một ví dụ khác là mô hình dữ liệu bất biến đơn giản. Nếu phiên bản Java mục tiêu hỗ trợ record và kiểu dữ liệu chỉ cần mang dữ liệu, có thể dùng:

~~~java
public record CustomerId(String value) {
    public CustomerId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("value must not be blank");
        }
    }
}
~~~

Record giúp giảm mã lặp cho constructor, accessor, equals, hashCode và toString. Nhưng record không phải lựa chọn phù hợp cho mọi class: nếu kiểu dữ liệu cần kế thừa từ một class khác, có trạng thái thay đổi, hoặc cần kiểm soát vòng đời phức tạp, class thông thường có thể thích hợp hơn.

Hiện đại hóa mã nguồn không có nghĩa là thay toàn bộ cú pháp cũ bằng cú pháp mới. Một thay đổi chỉ có giá trị khi nó cải thiện tính đúng đắn, an toàn, khả năng đọc, hiệu năng hoặc khả năng phát triển của hệ thống. Mỗi thay đổi cũng cần xét đến phiên bản Java mục tiêu và khả năng tương thích với consumer hiện tại.

Cần lưu ý rằng một số thay đổi thường được gọi chung là “modernize Java” thực chất là migration của framework hoặc hệ sinh thái. Ví dụ, chuyển package từ javax.* sang jakarta.* có thể làm thay đổi API và binary compatibility của ứng dụng. Đây không đơn thuần là đổi cú pháp Java; cần đánh giá phiên bản framework, dependency và contract của các thành phần liên quan.

**Kết luận của source modernization:** mã nguồn thay đổi có chủ đích, thường kéo theo biên dịch lại và kiểm thử hành vi. Việc có cần nâng runtime hay không phụ thuộc vào API và tính năng mới được sử dụng.

## 3. So sánh ba hoạt động theo phạm vi thay đổi

| Tiêu chí | Nâng cấp runtime | Biên dịch lại | Hiện đại hóa mã nguồn |
|---|---|---|---|
| Lớp thay đổi chính | Môi trường thực thi | Compiler và artifact | Mã nguồn |
| Có sửa .java không? | Không bắt buộc | Không bắt buộc | Có |
| Có tạo artifact mới không? | Không bắt buộc | Có | Có, sau khi biên dịch |
| JVM production có đổi không? | Có | Không bắt buộc | Không bắt buộc |
| Phiên bản bytecode có đổi không? | Không | Có thể đổi hoặc giữ nguyên | Phụ thuộc release đích |
| Có thể dùng API mới không? | Chỉ API có trong runtime và dependency hiện tại của artifact | Có nếu mã nguồn dùng được và release đích hỗ trợ | Có nếu runtime, compiler và release đích hỗ trợ |
| Rủi ro chính | Khác biệt hành vi runtime | Khác biệt compiler, dependency và artifact | Lỗi logic, API, contract và hành vi |
| Bằng chứng cần chú trọng | Kiểm thử trên JVM mới | Build tái lập, kiểm tra bytecode và test | Review thay đổi, test nghiệp vụ và tương thích |

Ba hoạt động không loại trừ nhau. Một kế hoạch chuyển Java có thể thực hiện cả ba, nhưng nên nhận diện từng hoạt động riêng để biết thay đổi nào gây ra vấn đề.

## 4. Hiểu đúng về source compatibility, binary compatibility và runtime compatibility

Từ “tương thích” không chỉ có một nghĩa. Khi đánh giá migration, cần chỉ rõ loại tương thích đang được yêu cầu.

### 4.1. Source compatibility

Source compatibility trả lời câu hỏi: **mã nguồn hiện tại có thể được compiler mục tiêu biên dịch mà không cần sửa hoặc chỉ cần sửa trong phạm vi cho phép hay không?**

Ví dụ, một dự án viết theo Java 17 có thể tiếp tục biên dịch bằng JDK 21 nếu mã nguồn, annotation processor, compiler options và dependency hỗ trợ cấu hình đó.

Source compatibility không đảm bảo artifact chạy được trên runtime mục tiêu. Mã nguồn có thể biên dịch thành công nhưng lại gọi API không tồn tại trong runtime cũ nếu giới hạn API không được cấu hình đúng.

### 4.2. Binary compatibility

Binary compatibility liên quan đến việc các class đã biên dịch có thể liên kết và sử dụng class hoặc thư viện khác mà không gặp lỗi liên kết hay không.

Một thư viện có thể giữ nguyên tên class nhưng thay đổi chữ ký method, xóa constructor hoặc thay đổi kiểu trả về. Ứng dụng đã biên dịch trước đó có thể gặp lỗi như NoSuchMethodError hoặc NoClassDefFoundError khi chạy với thư viện mới.

Binary compatibility đặc biệt quan trọng khi nâng phiên bản dependency, thay đổi API public của thư viện dùng chung hoặc thay đổi cách đóng gói module.

### 4.3. Runtime và behavioral compatibility

Runtime compatibility trả lời câu hỏi: **artifact có khởi động và thực thi được trên môi trường mục tiêu hay không?**

Behavioral compatibility đi xa hơn: **ứng dụng có tiếp tục cho kết quả và tác động nghiệp vụ như mong đợi hay không?**

Một ứng dụng có thể khởi động thành công nhưng vẫn sai hành vi vì:

- Cách parse ngày giờ hoặc số thập phân thay đổi.
- Charset mặc định khác.
- TLS không còn chấp nhận cấu hình cũ.
- Thứ tự xử lý hoặc timing trong ứng dụng đồng thời thay đổi.
- Garbage Collector làm thay đổi đặc tính độ trễ.
- Thư viện thay đổi giá trị mặc định hoặc cách xử lý dữ liệu biên.

Vì vậy, kiểm tra “ứng dụng start được” chỉ chứng minh một phần nhỏ của tính tương thích.

### 4.4. Platform và operational compatibility

Platform compatibility xét đến API Java, module system, hệ điều hành, kiến trúc CPU, native library, container image và các dịch vụ ngoài ứng dụng.

Operational compatibility xét đến khả năng vận hành: health check, logging, metrics, tracing, memory limit, startup time, shutdown, cấu hình JVM và quy trình rollback.

Một migration có thể đúng ở mức source và binary nhưng vẫn thất bại trong production nếu container thiếu chứng thư, native library không đúng kiến trúc hoặc cấu hình memory không phù hợp với JVM mới.

## 5. Quan hệ giữa phiên bản JDK, bytecode và runtime

### 5.1. JDK mới thường chạy được bytecode cũ, nhưng không bảo đảm toàn bộ ứng dụng tương thích

JVM thường hỗ trợ các phiên bản class file cũ hơn. Vì vậy, một JAR được biên dịch cho Java 17 thường có thể được chạy trên Java 21. Nhưng ứng dụng còn phụ thuộc vào API nền tảng, dependency, reflection, native code và hành vi runtime.

Chiều ngược lại có giới hạn rõ hơn: JVM cũ không thể thực thi class file có phiên bản mới hơn mức nó hỗ trợ. Trường hợp này thường gây UnsupportedClassVersionError.

Một số phiên bản class file thường gặp:

| Phiên bản Java | Major class file |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

Ví dụ, nếu một class được biên dịch với major version 65 thì runtime cần hỗ trợ class file Java 21. Chạy class đó trên Java 17 có thể gây lỗi UnsupportedClassVersionError.

### 5.2. Kiểm tra phiên bản bytecode

Có thể dùng javap để xem thông tin class file:

~~~bash
javap -verbose -classpath app.jar com.example.Main
~~~

Tìm dòng major version trong kết quả. Lưu ý rằng với JAR nhiều phiên bản (multi-release JAR), một JAR có thể chứa nhiều biến thể class cho các runtime khác nhau; cần kiểm tra đúng class entry được JVM chọn.

Lệnh kiểm tra phiên bản Java đang được shell sử dụng:

~~~bash
java -version
javac -version
~~~

Hai lệnh có thể trỏ đến hai cài đặt khác nhau nếu PATH, JAVA_HOME hoặc cấu hình toolchain không thống nhất. Kết quả của javac -version cũng không chứng minh Gradle hoặc Maven đang dùng chính compiler đó.

### 5.3. Dùng --release để xác định mục tiêu biên dịch

Ví dụ muốn build bằng JDK 21 nhưng vẫn hỗ trợ Java 17:

~~~bash
javac --release 17 -d out src/com/example/Main.java
~~~

Với Maven Compiler Plugin, có thể khai báo release trong properties:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Với Gradle, có thể tách toolchain và release đích:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Trong ví dụ Gradle:

- Toolchain chọn JDK 21 để chạy compiler.
- options.release = 17 giới hạn API và bytecode theo Java 17.
- JVM chạy ứng dụng vẫn phải được xác định riêng trong môi trường test và production.
- Gradle daemon cũng có thể chạy trên một JDK khác, miễn phiên bản Gradle hỗ trợ môi trường đó.

Không nên chỉ đọc một giá trị “Java version” trong cấu hình rồi kết luận toàn bộ pipeline đang dùng cùng một phiên bản.

## 6. Các tổ hợp migration thường gặp

### Trường hợp A — Chỉ nâng runtime

~~~text
Source:       giữ nguyên
Build:        giữ nguyên
Artifact:     giữ nguyên
Runtime:      Java 17 -> Java 21
~~~

Mục tiêu là kiểm tra artifact hiện tại trên JVM mới. Đây là cách khoanh vùng tác động của runtime upgrade. Nếu ứng dụng lỗi, có thể tập trung điều tra API bị thay đổi, JVM options, dependency, TLS, reflection, charset hoặc môi trường triển khai.

### Trường hợp B — Chỉ biên dịch lại, giữ release đích

~~~text
Source:       giữ nguyên
Compiler:     JDK 17 -> JDK 21
Release đích: Java 17 -> Java 17
Artifact:     tạo lại
Runtime:      vẫn Java 17
~~~

Mục tiêu là chuyển toolchain hoặc tái tạo artifact nhưng giữ khả năng chạy trên Java 17. Cần kiểm tra build tool, annotation processor, dependency và tính tái lập của artifact.

### Trường hợp C — Biên dịch lại với release mới và nâng runtime

~~~text
Source:       có thể giữ nguyên
Compiler:     JDK 21
Release đích: Java 21
Artifact:     tạo lại với bytecode Java 21
Runtime:      Java 17 -> Java 21
~~~

Mục tiêu là chuyển nền tảng build và runtime sang Java 21. Nếu dependency hoặc mã nguồn không hỗ trợ Java 21, có thể cần thêm thay đổi. Đây là migration có phạm vi rộng hơn hai trường hợp trước.

### Trường hợp D — Hiện đại hóa mã nguồn, giữ release cũ

~~~text
Source:       chỉnh sửa
Compiler:     có thể thay đổi
Release đích: giữ nguyên
Runtime:      giữ nguyên
~~~

Mục tiêu là cải thiện chất lượng mã nguồn mà vẫn giữ nền tảng tương thích cũ. Cách này phù hợp khi có thể dùng API và cú pháp trong release hiện tại. Không phải mọi tính năng mới đều có thể dùng nếu release đích không hỗ trợ.

### Trường hợp E — Hiện đại hóa mã nguồn và chuyển nền tảng

~~~text
Source:       chỉnh sửa
Compiler:     JDK mới
Release đích: tăng
Artifact:     tạo lại
Runtime:      nâng lên phiên bản hỗ trợ
~~~

Đây là migration toàn diện. Có thể bao gồm thay API cũ, cập nhật dependency, chuyển framework, điều chỉnh cấu hình và khai thác tính năng Java mới. Vì nhiều lớp cùng thay đổi, cần chia thành các bước có thể kiểm chứng và rollback.

## 7. Chọn chiến lược theo mục tiêu

Không phải dự án nào cũng cần hiện đại hóa mã nguồn khi nâng runtime. Cũng không phải dự án nào cần nâng runtime đều phải đổi release đích của bytecode.

| Mục tiêu | Hướng xử lý thường phù hợp |
|---|---|
| Cần bản vá bảo mật hoặc runtime được hỗ trợ | Đánh giá nâng runtime; giữ artifact nếu tương thích |
| Muốn chuẩn hóa JDK của CI/build | Chuyển toolchain và biên dịch lại; giữ release đích nếu cần hỗ trợ runtime cũ |
| Muốn chạy trên runtime mới nhưng chưa muốn dùng tính năng mới | Nâng runtime trước, giữ source và bytecode nếu có thể |
| Muốn hỗ trợ đồng thời runtime cũ và build bằng JDK mới | Dùng toolchain mới cùng --release phù hợp |
| Muốn loại bỏ API lỗi thời hoặc cải thiện khả năng bảo trì | Hiện đại hóa mã nguồn theo từng nhóm thay đổi |
| Muốn dùng API hoặc tính năng chỉ có ở Java mới | Nâng release đích, runtime và dependency tương ứng |
| Framework hoặc thư viện đã bỏ hỗ trợ nền tảng cũ | Lập kế hoạch migration dependency/framework cùng kiểm thử contract |

Một chiến lược thận trọng thường tách migration thành các chặng:

1. Ghi nhận trạng thái hiện tại: JDK build, compiler, release đích, JVM production, Gradle/Maven, dependency và cấu hình triển khai.
2. Kiểm tra khả năng chạy artifact hiện tại trên runtime mục tiêu nếu mục tiêu trước mắt là nâng runtime.
3. Chuyển toolchain build và biên dịch lại với release đích được xác định rõ.
4. Nâng dependency hoặc framework theo yêu cầu tương thích.
5. Hiện đại hóa mã nguồn theo nhóm nhỏ, mỗi nhóm có mục tiêu và kiểm thử cụ thể.
6. Nâng release đích của bytecode khi hệ thống đã sẵn sàng.
7. Triển khai theo từng môi trường, quan sát chỉ số và giữ khả năng rollback.

Không nhất thiết phải tuân thủ đúng thứ tự này trong mọi dự án. Điều quan trọng là mỗi chặng phải có đầu vào, thay đổi và bằng chứng đầu ra rõ ràng.

## 8. Quy trình phân tích một yêu cầu “nâng cấp Java”

Khi nhận yêu cầu nâng cấp Java, hãy làm rõ các câu hỏi sau trước khi thay đổi hệ thống.

### Bước 1 — Xác định điều gì đang cần thay đổi

Hỏi rõ yêu cầu thuộc trường hợp nào:

- Thay JVM/runtime đang chạy ứng dụng?
- Chuyển JDK dùng để build?
- Đổi phiên bản bytecode mà sản phẩm hỗ trợ?
- Sửa mã nguồn để dùng API hoặc tính năng mới?
- Nâng framework và dependency do phiên bản cũ hết hỗ trợ?

Một yêu cầu như “nâng từ Java 17 lên Java 21” chưa đủ cụ thể. Nó có thể chỉ nói về JVM production, JDK compiler, release đích hoặc cả ba.

### Bước 2 — Lập bản đồ phiên bản hiện tại

Ghi nhận ít nhất:

| Thành phần | Câu hỏi cần trả lời |
|---|---|
| JDK chạy build tool | Gradle/Maven đang chạy bằng JDK nào? |
| Compiler toolchain | Task compile dùng compiler từ JDK nào? |
| Source/release | Mã nguồn và API đích được giới hạn ở release nào? |
| Bytecode | Artifact hiện tại có major version nào? |
| Test runtime | Unit/integration test chạy trên JVM nào? |
| Production runtime | Container hoặc máy chủ production chạy JVM nào? |
| Dependencies | Thư viện và plugin hỗ trợ những phiên bản Java nào? |
| Native components | Có JNI, agent hoặc native library nào không? |

Không nên suy luận phiên bản production từ máy developer hoặc từ JDK chạy CI.

### Bước 3 — Xác định hợp đồng tương thích cần giữ

Ví dụ:

- Artifact mới vẫn phải chạy trên Java 17.
- Chỉ production được nâng lên Java 21 trong đợt đầu.
- Các module dùng chung phải giữ binary compatibility với consumer cũ.
- API public và định dạng dữ liệu không được thay đổi.
- Ứng dụng phải chạy trên cả Linux container hiện tại và môi trường staging.

Hợp đồng tương thích càng rõ thì phạm vi migration càng dễ kiểm soát.

### Bước 4 — Kiểm tra dependency và build tool

Một ứng dụng có thể không dùng tính năng mới của Java nhưng vẫn không build được nếu Gradle/Maven plugin, annotation processor hoặc dependency chưa hỗ trợ JDK mới.

Cần kiểm tra:

- Phiên bản Gradle/Maven có hỗ trợ JDK dùng để chạy build không.
- Compiler plugin có hỗ trợ release đích không.
- Annotation processor và bytecode instrumentation có tương thích không.
- Dependency có class file hoặc API yêu cầu runtime mới hơn không.
- Thư viện có dùng reflection sâu hoặc API nội bộ JDK không.
- Các plugin kiểm thử, đóng gói, coverage, static analysis có hỗ trợ không.

### Bước 5 — Chọn một lát cắt kiểm chứng

Trước khi chuyển toàn bộ hệ thống, chọn một module hoặc dịch vụ đại diện có đủ dependency và cách triển khai tương tự production. Xác nhận build, test, startup, kết nối dịch vụ ngoài và quan sát runtime trên nền tảng mục tiêu.

Một module quá đơn giản có thể không bộc lộ vấn đề ở dependency, reflection hoặc cấu hình. Hãy chọn lát cắt có khả năng đại diện cho rủi ro thực tế.

### Bước 6 — Định nghĩa tiêu chí hoàn thành

Tiêu chí nên bao gồm:

- Build thành công bằng toolchain đã chọn.
- Artifact có đúng bytecode release đã công bố.
- Unit test và integration test chạy trên runtime đích.
- Kiểm tra API contract và định dạng dữ liệu quan trọng.
- Kiểm tra startup, shutdown, health check, logging và metrics.
- Kiểm tra TLS, chứng thư, database driver, message broker và dịch vụ ngoài.
- Đo memory, CPU, throughput và latency khi có yêu cầu hiệu năng.
- Quy trình rollback đã được thử hoặc có thể thực hiện rõ ràng.

## 9. Những nhầm lẫn thường gặp

### “Dùng JDK 21 để build nghĩa là ứng dụng đã chạy trên Java 21”

Không đúng. JDK dùng để build và JVM dùng để chạy ứng dụng là hai cấu hình khác nhau. Hơn nữa, JDK 21 có thể biên dịch với --release 17, tạo bytecode hướng đến Java 17.

### “Bytecode cũ chạy được trên JVM mới nên không cần kiểm thử”

Không đúng. Khả năng đọc class file chỉ là một điều kiện. API bị loại bỏ, reflection, JVM options, TLS, charset, timezone, native library và hành vi mặc định vẫn có thể làm ứng dụng lỗi hoặc đổi kết quả.

### “Chỉ cần đặt sourceCompatibility và targetCompatibility là đủ”

Không phải lúc nào cũng đủ. Cần giới hạn API nền tảng tương ứng với release đích. Với JDK 9 trở lên, --release thường là lựa chọn rõ ràng hơn. Đồng thời phải kiểm tra dependency và compiler plugin.

### “Biên dịch lại không thay đổi mã nguồn thì không có rủi ro”

Biên dịch lại có thể thay compiler, annotation processor, plugin, dependency graph hoặc quy trình đóng gói. Artifact mới vì thế vẫn cần được kiểm tra.

### “Hiện đại hóa nghĩa là thay tất cả cú pháp cũ”

Không. Cú pháp mới chỉ nên được dùng khi giúp mã dễ hiểu, an toàn hoặc dễ bảo trì hơn. Một đoạn code cũ ổn định, rõ ràng và phù hợp với release mục tiêu không nhất thiết cần viết lại.

### “Nâng runtime và nâng release bytecode là cùng một việc”

Không. Runtime là môi trường thực thi; release bytecode là mục tiêu khi biên dịch. Có thể nâng runtime mà giữ nguyên artifact, hoặc build bằng JDK mới nhưng vẫn tạo bytecode cho runtime cũ.

### “Ứng dụng khởi động được là migration thành công”

Chưa đủ. Khởi động thành công không chứng minh nghiệp vụ, dữ liệu, tích hợp, bảo mật, hiệu năng và khả năng vận hành vẫn đúng. Cần kiểm thử theo hợp đồng tương thích đã xác định.

## 10. Ví dụ tổng hợp: chuyển một dịch vụ từ Java 17 sang Java 21

Giả sử một dịch vụ đang có cấu hình:

~~~text
JDK chạy Gradle:       17
Compiler:              17
Release đích:          17
Bytecode:              Java 17
Test runtime:          17
Production runtime:    17
~~~

Nhóm muốn chuyển production sang Java 21 nhưng chưa muốn sử dụng tính năng ngôn ngữ mới.

Có thể chia công việc thành hai chặng.

**Chặng 1: nâng runtime, giữ artifact**

~~~text
JDK chạy Gradle:       17
Compiler:              17
Release đích:          17
Artifact:              giữ nguyên
Test runtime:          21
Production runtime:    21
~~~

Chạy artifact hiện tại trên Java 21 ở môi trường thử nghiệm. Kiểm tra startup, luồng nghiệp vụ, tích hợp, TLS, charset, log, metrics và hiệu năng. Nếu phát hiện lỗi, điều tra khác biệt runtime trước khi mở rộng phạm vi thay đổi.

**Chặng 2: chuẩn hóa build toolchain**

~~~text
JDK chạy Gradle:       phiên bản được Gradle hỗ trợ
Compiler toolchain:    21
Release đích:          17
Bytecode:              Java 17
Test runtime:          17 và/hoặc 21 theo mục tiêu hỗ trợ
Production runtime:    21
~~~

Chuyển compiler toolchain sang JDK 21 nhưng giữ release 17. Build lại artifact và chạy kiểm thử. Nếu sản phẩm cần tiếp tục hỗ trợ Java 17, phải kiểm tra trên Java 17; nếu Java 21 là runtime tối thiểu mới, vẫn nên chạy test trên Java 21 và cập nhật rõ yêu cầu triển khai.

Sau khi hai chặng ổn định, nhóm có thể lập một thay đổi riêng để hiện đại hóa mã nguồn hoặc nâng release đích lên 21. Như vậy, khi có lỗi, nhóm có thể phân biệt lỗi do runtime, compiler/artifact hay thay đổi mã nguồn.

## 11. Cách ghi nhận phạm vi migration trong tài liệu kỹ thuật

Một bản kế hoạch migration nên tránh chỉ ghi “Upgrade Java 17 to 21”. Hãy ghi cụ thể:

~~~text
Runtime:
  Current: Java 17
  Target: Java 21

Build JDK:
  Current: JDK 17
  Target: JDK 21

Compiler release:
  Current: 17
  Target: 17

Source changes:
  None in this phase

Dependency changes:
  List exact libraries and versions, or state none

Compatibility contract:
  Artifact must remain runnable on Java 17
  Production deployment target is Java 21

Validation:
  Build, unit tests, integration tests, runtime smoke tests,
  security/TLS checks and operational metrics

Rollback:
  Previous artifact and Java 17 runtime remain deployable
~~~

Khi có thay đổi ở nhiều lớp, hãy ghi từng lớp và lý do. Ví dụ, nâng runtime để nhận bản vá bảo mật là một mục tiêu; nâng release đích để sử dụng API mới là mục tiêu khác; chuyển framework vì framework cũ hết hỗ trợ là một mục tiêu thứ ba. Mỗi mục tiêu có thể cần thời điểm triển khai, tiêu chí hoàn thành và phương án rollback riêng.

## 12. Ghi nhớ khi đánh giá một đề xuất chuyển đổi

Trước khi chấp thuận một đề xuất, hãy có thể trả lời rõ:

1. Thay đổi chính nằm ở runtime, compiler/artifact hay mã nguồn?
2. JDK chạy build, JDK compiler, release đích và JVM production hiện tại là những phiên bản nào?
3. Phiên bản Java thấp nhất mà artifact mới phải hỗ trợ là bao nhiêu?
4. Dependency, framework, annotation processor và native library có đáp ứng mục tiêu không?
5. Tương thích cần giữ là source, binary, runtime, behavioral hay operational?
6. Bằng chứng nào chứng minh ứng dụng hoạt động đúng trên môi trường mục tiêu?
7. Nếu thay đổi thất bại, có thể quay lại artifact và runtime trước đó bằng cách nào?

Có thể dùng ba câu hỏi ngắn để phân loại nhanh:

- **Runtime upgrade:** “Artifact đang có có chạy đúng trên JVM mới không?”
- **Recompilation:** “Mã nguồn hiện tại có thể được build lại bằng toolchain mới và tạo artifact đúng release không?”
- **Source modernization:** “Những thay đổi mã nguồn nào đem lại giá trị và vẫn giữ các hợp đồng tương thích cần thiết?”

Khi trả lời được ba câu hỏi này, phạm vi của một Java migration sẽ rõ ràng hơn. Nhóm có thể lập kế hoạch theo từng lớp, lựa chọn kiểm thử đúng trọng tâm và xác định nguyên nhân khi một bước chuyển đổi không đạt yêu cầu.

