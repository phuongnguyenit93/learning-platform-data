# Thiết lập `javac --release 21` để kiểm soát ngôn ngữ, bytecode và API

Khi một dự án cần chạy trên Java 21, cấu hình trình biên dịch phải giữ đồng bộ ba giới hạn: cú pháp và quy tắc ngôn ngữ Java 21, định dạng bytecode mà JVM Java 21 hiểu được, và tập API nền tảng có trong Java 21. Tùy chọn `javac --release 21` gom cả ba giới hạn đó vào một cấu hình rõ ràng.

Đây là cách nên dùng khi biên dịch mã Java hướng tới Java 21, kể cả khi máy build cài JDK mới hơn. Chẳng hạn, một JDK mới có thể cung cấp thêm API và tính năng ngôn ngữ; `--release 21` vẫn giữ dự án trong phạm vi Java SE 21.

## 1. Ba giới hạn mà bản build cần kiểm soát

Một dự án Java có thể biên dịch thành công nhưng vẫn không chạy được trên phiên bản Java dự kiến nếu chỉ kiểm soát một phần cấu hình.

| Giới hạn | Điều cần bảo đảm với Java 21 | Cách kiểm soát |
|---|---|---|
| Ngôn ngữ nguồn | Chỉ dùng cú pháp và quy tắc ngôn ngữ thuộc Java 21 | Mức source 21 |
| Bytecode | Tạo class file có định dạng Java 21 | Mức target 21; class file Java 21 có major version 65 |
| API nền tảng | Chỉ tham chiếu API Java SE đã có trong Java 21 | Biên dịch dựa trên API của release 21 |

Ba giới hạn này có liên quan nhưng không thể thay thế cho nhau. Ví dụ, đặt mức source và target 21 khi dùng một JDK mới hơn vẫn có thể cho phép mã tham chiếu API được bổ sung sau Java 21. Mã đó có thể biên dịch thành công nhưng thất bại khi chạy trên Java 21 vì API không tồn tại ở runtime.

## 2. `--release 21` giải quyết điều gì?

Với JDK 9 trở lên, `javac --release N` yêu cầu trình biên dịch:

1. Áp dụng quy tắc ngôn ngữ của phiên bản Java SE được chọn.
2. Sinh class file tương thích với định dạng của phiên bản đó.
3. Biên dịch dựa trên các API Java SE công khai, được hỗ trợ và được tài liệu hóa trong phiên bản đó.

Vì vậy, `javac --release 21` tương đương về mục tiêu với việc đặt source và target ở mức 21, đồng thời giới hạn API nền tảng theo Java 21. Đây là điểm quan trọng khiến `--release` phù hợp hơn việc chỉ đặt riêng `-source` và `-target`.

Không truyền thêm `-source` hoặc `-target` cùng với `--release`; nếu cần, có thể kết hợp các tùy chọn độc lập như `-encoding` hoặc `-Xlint`.

Ví dụ, mã sau sử dụng virtual thread, một API ổn định được đưa vào Java 21:

~~~java
public class VirtualThreadExample {
    public static void main(String[] args) throws InterruptedException {
        Thread thread = Thread.ofVirtual().start(
            () -> System.out.println("Hello from a virtual thread")
        );
        thread.join();
    }
}
~~~

Mã này thuộc phạm vi API Java 21 nên có thể biên dịch với `--release 21`. Ngược lại, khi một dự án được đặt `--release 21`, trình biên dịch sẽ từ chối tham chiếu đến API Java SE chỉ xuất hiện sau Java 21, dù JDK đang chạy `javac` có cung cấp API mới đó.

### Yêu cầu đối với JDK

Muốn biên dịch cho release 21, cần dùng JDK có trình biên dịch hỗ trợ release 21 — thông thường là JDK 21 hoặc JDK mới hơn còn hỗ trợ đích này. JDK 20 trở xuống không thể biên dịch mã Java 21 vì trình biên dịch của chúng không hiểu release 21.

JDK được dùng để chạy `javac` là môi trường biên dịch. Nó có thể khác phiên bản Java mà dự án nhắm tới. Ví dụ, một JDK mới hơn có thể biên dịch dự án Java 21 bằng `--release 21`; kết quả vẫn mang định dạng class file Java 21 và bị giới hạn theo API Java 21.

## 3. Biên dịch trực tiếp bằng javac

Trước tiên, xác định trình biên dịch và runtime đang được tìm thấy qua `PATH`:

~~~shell
javac --version
java --version
~~~

Hai lệnh này giúp nhận diện phiên bản công cụ, nhưng trong môi trường có nhiều JDK, cần kiểm tra thêm đường dẫn thực tế để chắc chắn `javac` và `java` đến từ bộ JDK mong muốn. Trên Windows có thể dùng `where.exe javac`; trên Linux hoặc macOS có thể dùng `which javac`.

Giả sử mã nguồn nằm tại `src/main/java/com/example/Main.java`, thư mục đích `out` đã tồn tại, và lớp chính khai báo package `com.example`. Có thể biên dịch như sau:

~~~shell
javac --release 21 -encoding UTF-8 -d out src/main/java/com/example/Main.java
java -cp out com.example.Main
~~~

Ý nghĩa các tùy chọn:

- `--release 21`: cố định ngôn ngữ, bytecode và API nền tảng theo Java 21.
- `-encoding UTF-8`: xác định bảng mã đọc file nguồn. Tùy chọn này độc lập với `--release`.
- `-d out`: đặt nơi ghi class file; trình biên dịch tạo cấu trúc thư mục package bên dưới thư mục đích.
- `-cp out`: đưa thư mục chứa class file vào classpath khi chạy chương trình.

Nếu dự án có nhiều file nguồn, truyền tất cả file cần biên dịch hoặc dùng argument file của javac. Với dự án thực tế, nên để Maven hoặc Gradle quản lý danh sách nguồn, dependency và thứ tự các bước build.

### Xác minh bytecode đầu ra

Có thể dùng `javap` đi kèm JDK để xem phiên bản class file:

~~~shell
javap -verbose -classpath out com.example.Main
~~~

Trong kết quả, tìm dòng `major version: 65`. Major version 65 là định dạng class file của Java 21. Đây là cách kiểm tra đầu ra hữu ích khi cần xác nhận cấu hình compiler thực sự được áp dụng.

Việc thấy major version 65 xác nhận mức bytecode, nhưng không tự chứng minh mọi dependency đều chạy được trên Java 21. Các thư viện bên ngoài cũng cần có class file và yêu cầu runtime tương thích.

## 4. Cấu hình trong Maven

Với Maven, đặt thuộc tính `maven.compiler.release` để các lần biên dịch mã chính và mã kiểm thử dùng cùng release:

~~~xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Đảm bảo dự án khai báo một phiên bản Maven Compiler Plugin được duy trì và hỗ trợ tham số `release` (tham số này được hỗ trợ từ phiên bản 3.6.0). Ví dụ cấu hình plugin:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
        </plugin>
    </plugins>
</build>
~~~

Phiên bản plugin trong ví dụ là một phiên bản cụ thể có hỗ trợ `release`; dự án mới nên chọn và khóa một phiên bản plugin còn được duy trì phù hợp với phiên bản Maven và JDK đang sử dụng. Không nên giả định Maven tự chọn compiler plugin mới nhất.

Thuộc tính `maven.compiler.release` xác định release đích, nhưng không tự chọn JDK cài trên máy. Nếu cần kiểm soát chính xác JDK mà Maven dùng khi có nhiều JDK, hãy cấu hình Maven Toolchains và xác minh bằng `mvn -version`. Kết quả này cho biết Maven đang chạy bằng Java nào; cấu hình toolchain quyết định JDK được dùng cho compiler khi dự án khai báo toolchain tương ứng.

## 5. Cấu hình trong Gradle

Với Gradle Groovy DSL, dùng Java toolchain để chọn JDK và đặt `options.release` để khóa phạm vi biên dịch:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 21
    options.encoding = 'UTF-8'
}
~~~

Java toolchain chọn JDK 21 cho các tác vụ Java được cấu hình sử dụng toolchain. `options.release = 21` thể hiện rõ mức ngôn ngữ, bytecode và API mà compiler phải tuân theo. `options.encoding` đặt bảng mã file nguồn.

Trong dự án nhiều module, đặt cấu hình dùng chung ở cấp phù hợp để mọi module Java đều nhận cùng toolchain và release. Kiểm tra các tác vụ biên dịch riêng của module, mã kiểm thử và tác vụ tạo mã nếu chúng có cấu hình compiler độc lập.

Toolchain và release giải quyết hai phần khác nhau: toolchain chọn bộ JDK thực thi compiler; release chọn nền tảng Java mà mã nguồn được phép nhắm tới. Cấu hình cả hai giúp build ổn định hơn giữa máy phát triển và CI.

## 6. Phân biệt release đích với JDK chạy compiler

Hai khái niệm thường bị nhầm lẫn:

| Khái niệm | Vai trò |
|---|---|
| JDK chạy compiler | Cung cấp `javac`, phiên bản compiler, công cụ và môi trường chạy các plugin xử lý annotation |
| `--release 21` | Giới hạn mã nguồn, class file và API Java SE mà compiler sử dụng cho sản phẩm |
| JDK chạy ứng dụng | JVM thực thi class file và cung cấp API tại thời điểm chạy |

Ví dụ, nếu dùng JDK 25 để chạy compiler với `--release 21`, mã nguồn vẫn được biên dịch theo Java 21. Tuy nhiên, compiler vẫn là compiler thuộc JDK 25; cảnh báo, sửa lỗi compiler và một số hành vi công cụ có thể khác so với JDK 21. Khi cần build có thể tái lập chặt chẽ, hãy cố định cả phiên bản JDK, Maven hoặc Gradle, plugin và dependency trong quy trình build.

Để chạy ứng dụng dùng class file Java 21, runtime cần là Java 21 hoặc mới hơn. `--release 21` không làm cho bytecode Java 21 chạy được trên JVM cũ hơn.

## 7. Những giới hạn `--release 21` không xử lý

`--release` kiểm soát biên dịch đối với nền tảng Java SE. Nó không thay thế toàn bộ quản lý tương thích của dự án:

- **Dependency bên ngoài:** compiler vẫn cần đọc được class file của thư viện. Một thư viện yêu cầu Java mới hơn có thể không biên dịch hoặc không chạy được trên Java 21.
- **Runtime và môi trường triển khai:** cấu hình release không cài đặt JVM, không chọn container image và không ép lệnh chạy ứng dụng dùng Java 21. Cần kiểm soát runtime trong môi trường test, CI và production.
- **API nội bộ hoặc không được hỗ trợ:** không nên dựa vào API nội bộ của JDK. `--release` hướng tới API Java SE công khai, được hỗ trợ và được tài liệu hóa.
- **Công cụ build và annotation processor:** plugin, compiler plugin, annotation processor và công cụ tạo mã có yêu cầu JDK riêng. Chúng có thể chạy trong môi trường JDK dùng để build, nên cần kiểm tra tương thích độc lập.
- **Các yếu tố tái lập khác:** encoding, phiên bản dependency, plugin, biến môi trường và cấu hình CI vẫn cần được khóa hoặc quản lý rõ ràng.

Nếu ứng dụng biên dịch thành công nhưng lỗi khi chạy, hãy kiểm tra cả runtime thực tế và dependency, thay vì chỉ nhìn vào giá trị release.

## 8. Lỗi thường gặp và cách xử lý

| Biểu hiện | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `release version 21 not supported` | `javac` đang chạy từ JDK cũ chưa hỗ trợ release 21 | Chọn JDK 21 hoặc JDK mới hơn có hỗ trợ release 21; kiểm tra lại đường dẫn compiler và toolchain |
| `UnsupportedClassVersionError` | JVM chạy ứng dụng cũ hơn mức bytecode của class file | Chạy bằng Java 21 hoặc mới hơn, hoặc build lại cho release thấp hơn nếu mã nguồn và dependency cho phép |
| Không tìm thấy một API khi biên dịch | API không thuộc Java SE 21 hoặc dependency chưa có trong compile classpath | Xác minh API xuất hiện từ phiên bản Java nào; kiểm tra dependency và cấu hình release |
| Biên dịch được nhưng gặp `NoSuchMethodError` hoặc `NoClassDefFoundError` khi chạy | Runtime đang nạp phiên bản thư viện khác với lúc biên dịch, hoặc thư viện yêu cầu API không có ở runtime | Đồng bộ dependency giữa compile và runtime; kiểm tra classpath/module path và phiên bản Java thực tế |
| Máy cá nhân build được nhưng CI thất bại | JDK, toolchain, plugin hoặc dependency giữa hai môi trường khác nhau | In phiên bản JDK và build tool trong CI; khóa toolchain, plugin và dependency |

Khi chẩn đoán, kiểm tra theo thứ tự: JDK thực thi compiler, release được truyền vào tác vụ compile, class file đầu ra, runtime chạy ứng dụng và dependency được nạp tại runtime. Cách này giúp xác định đúng tầng gây lỗi.

## 9. Checklist cấu hình cho dự án Java 21

- [ ] Máy build hoặc CI có JDK với `javac` hỗ trợ release 21.
- [ ] Tác vụ biên dịch dùng `--release 21` hoặc cấu hình tương đương của Maven/Gradle.
- [ ] Encoding nguồn được đặt rõ ràng, thường là UTF-8.
- [ ] Toolchain chọn JDK dự kiến; phiên bản Maven/Gradle và compiler plugin được khóa.
- [ ] Mã kiểm thử và mọi module Java dùng cùng release đích.
- [ ] Runtime trong test, CI và production là Java 21 hoặc mới hơn.
- [ ] Dependency và annotation processor được xác nhận tương thích với JDK build và runtime Java 21.
- [ ] Khi cần xác minh đầu ra, dùng `javap -verbose` để kiểm tra major version 65.

Với dự án Java 21, cấu hình cốt lõi là chọn một JDK phù hợp, đặt `--release 21` cho mọi tác vụ biên dịch và chạy ứng dụng trên Java 21 trở lên. Cấu hình đó giúp giới hạn ngôn ngữ, bytecode và API nền tảng một cách nhất quán; việc kiểm soát dependency, plugin và runtime hoàn thiện phần tương thích còn lại.
