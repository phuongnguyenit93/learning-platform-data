# Vai trò của javac --release khi biên dịch cho phiên bản Java đích

Một dự án Java có thể được phát triển bằng JDK mới nhưng vẫn cần chạy trên một phiên bản Java cũ hơn. Ví dụ, nhóm dùng JDK 21 để build ứng dụng nhưng môi trường triển khai chỉ có Java 17. Khi đó, chỉ biên dịch thành công trên JDK 21 chưa đủ để bảo đảm ứng dụng chạy được trên Java 17. Mã bytecode phải tương thích với phiên bản đích, và mã nguồn không được sử dụng những API chỉ xuất hiện ở phiên bản mới hơn.

Tùy chọn **javac --release** giải quyết đồng thời hai phần quan trọng của vấn đề này: chọn mức ngôn ngữ và định dạng class file phù hợp với phiên bản Java đích, đồng thời giới hạn các API Java SE mà mã nguồn được phép sử dụng theo phiên bản đó. Đây là cách rõ ràng và đáng tin cậy hơn việc chỉ đặt riêng -source và -target khi biên dịch bằng JDK mới.

## 1. Vì sao cần chỉ định phiên bản Java đích?

JDK được dùng để biên dịch và JRE/JVM được dùng để chạy không nhất thiết có cùng phiên bản. Một dự án có thể:

- Được biên dịch trên JDK 21.
- Được đóng gói thành JAR.
- Được triển khai lên máy chủ chỉ cài Java 17.

Nếu bytecode yêu cầu phiên bản class file mới hơn JVM hỗ trợ, ứng dụng sẽ không thể nạp lớp. Nếu bytecode có định dạng tương thích nhưng mã nguồn gọi một API chỉ có từ Java 21, ứng dụng vẫn có thể lỗi khi chạy trên Java 17.

Do đó, khả năng tương thích với Java đích có ít nhất hai khía cạnh:

1. **Tương thích bytecode:** JVM đích phải hiểu phiên bản class file mà compiler tạo ra.
2. **Tương thích API:** những lớp và phương thức thuộc nền tảng Java mà chương trình sử dụng phải tồn tại trên runtime đích.

Ngoài ra còn có những yếu tố khác như dependency bên ngoài, module, hành vi runtime và môi trường hệ điều hành. Tùy chọn --release xử lý phần tương thích của ngôn ngữ, class file và API nền tảng Java SE; nó không thể tự bảo đảm mọi thành phần của ứng dụng tương thích với môi trường triển khai.

## 2. Ba khái niệm: source, target và release

Trước khi dùng --release, cần phân biệt ba khái niệm thường gặp trong javac.

### Source level

Source level xác định phiên bản cú pháp và quy tắc ngôn ngữ Java mà compiler chấp nhận. Ví dụ, nếu source level là 17, mã nguồn phải tuân theo các tính năng và quy tắc ngôn ngữ được hỗ trợ ở Java 17.

Tùy chọn tương ứng:

    javac -source 17 ...

### Target class-file version

Target xác định định dạng bytecode mà compiler tạo ra. JVM có thể từ chối một class file nếu phiên bản class file mới hơn phiên bản mà JVM hỗ trợ.

Tùy chọn tương ứng:

    javac -target 17 ...

### Platform API

Platform API là tập các lớp, interface, phương thức và trường do nền tảng Java cung cấp. Một mã nguồn có thể dùng cú pháp cũ nhưng gọi API mới.

Ví dụ, mã nguồn có thể dùng cú pháp Java 8 nhưng gọi một phương thức chỉ được thêm vào Java 11. Chỉ đặt -source 8 và -target 8 không tự động ngăn compiler mới nhìn thấy API của JDK hiện tại.

Đây là khoảng trống quan trọng của cách chỉ dùng -source và -target.

## 3. --release kết hợp những gì?

Tùy chọn:

    javac --release 17 ...

yêu cầu compiler biên dịch mã nguồn theo nền tảng Java 17. Về ý nghĩa, nó kết hợp:

- Quy tắc ngôn ngữ tương ứng với release 17.
- Định dạng class file dành cho release 17.
- Tập API Java SE công khai được hỗ trợ ở release 17.

Nhờ đó, nếu đang dùng JDK mới hơn để biên dịch, compiler vẫn kiểm tra mã nguồn dựa trên API của phiên bản đích. Mã nguồn không thể vô tình gọi một API Java SE chỉ có trong JDK mới hơn mà không tồn tại trong release đã chọn.

Ví dụ:

    javac --release 17 -d out src/com/example/Main.java

Lệnh này dùng compiler của JDK đang cài, nhưng đặt mục tiêu nền tảng Java 17. Nếu mã nguồn gọi API chỉ xuất hiện từ Java 21, compiler sẽ báo lỗi thay vì tạo bytecode có vẻ tương thích nhưng không chạy được trên Java 17.

--release được bổ sung từ JDK 9. Nó chỉ dùng được với javac thuộc JDK 9 trở lên và chỉ hỗ trợ các release mà phiên bản compiler hiện tại cho phép. Một JDK cũ không thể biên dịch cho release mới hơn nó hỗ trợ.

## 4. Ví dụ về lỗi khi chỉ dùng -source và -target

Giả sử nhóm biên dịch bằng JDK 21 nhưng cần chạy trên Java 17. Mã nguồn gọi một API được thêm sau Java 17:

    import java.util.List;

    public class Main {
        public static void main(String[] args) {
            List<String> names = List.of("An", "Binh");
            System.out.println(names.getFirst());
        }
    }

Phương thức getFirst() của List được bổ sung trong Java 21. Nếu chỉ dùng:

    javac -source 17 -target 17 Main.java

compiler mới có thể vẫn nhìn thấy API List của JDK 21. Tùy chọn source và target giới hạn ngôn ngữ và class file, nhưng không tự giới hạn API nền tảng theo Java 17. Mã có thể biên dịch trong một số trường hợp dù phương thức không có trên runtime Java 17.

Khi dùng:

    javac --release 17 Main.java

compiler kiểm tra API theo Java 17 và báo lỗi vì getFirst() không thuộc API List của phiên bản đích. Nhờ vậy, lỗi được phát hiện ở bước biên dịch thay vì xuất hiện khi ứng dụng chạy.

Nếu thay getFirst() bằng get(0), phương thức này đã tồn tại trong Java 17 và mã nguồn có thể biên dịch theo release 17.

## 5. API được giới hạn như thế nào?

JDK mới chứa các lớp và phương thức được bổ sung qua nhiều phiên bản. Khi dùng --release N, javac cần biết bề mặt API công khai của nền tảng Java ở release N, chứ không chỉ dùng toàn bộ API của JDK đang cài.

Trong các JDK hiện đại, compiler sử dụng dữ liệu chữ ký API được đóng gói trong JDK, thường được biết đến qua tệp ct.sym, để kiểm tra các API của release cũ. Nhờ dữ liệu này, compiler có thể chạy trên JDK mới nhưng vẫn xác định lớp và thành viên nào được phép dùng khi biên dịch cho một release được hỗ trợ.

Việc giới hạn áp dụng cho API nền tảng Java mà javac quản lý theo release. Nó không tự giới hạn mọi thư viện bên ngoài. Nếu dự án thêm dependency bên thứ ba chỉ hỗ trợ Java 21, --release 17 không thể tự biến thư viện đó thành thư viện tương thích Java 17.

Ví dụ, nếu classpath có một JAR biên dịch bằng Java 21 hoặc JAR gọi API không có trên Java 17, việc đặt --release 17 cho mã nguồn của ứng dụng không bảo đảm JAR đó chạy được trên Java 17. Cần kiểm tra bytecode và yêu cầu runtime của dependency riêng.

## 6. --release không phải là lựa chọn JDK để chạy build

Một nhầm lẫn phổ biến là nghĩ rằng:

    javac --release 17

có nghĩa compiler đang chạy bằng JDK 17. Thực tế, compiler vẫn là javac của JDK đang được gọi. --release chỉ đặt mục tiêu tương thích cho đầu ra và API nền tảng.

Ví dụ:

- Máy build cài JDK 21.
- PATH trỏ tới JDK 21.
- javac là compiler 21.
- Lệnh javac --release 17 tạo đầu ra cho nền tảng Java 17.

Nếu muốn bảo đảm build thực sự chạy bằng một JDK cụ thể, cần chọn JDK/toolchain tương ứng. Toolchain và --release giải quyết hai việc khác nhau:

| Cấu hình | Vai trò |
| --- | --- |
| JDK/compiler được chọn | Quyết định công cụ javac nào thực thi build. |
| --release N | Quyết định mức ngôn ngữ, class file và API Java SE mục tiêu. |
| Runtime triển khai | JVM thực tế sẽ nạp và chạy ứng dụng. |

Một dự án có thể dùng JDK 21 để biên dịch bằng --release 17, hoặc dùng toolchain JDK 17 để biên dịch trực tiếp bằng compiler 17. Lựa chọn nào phù hợp phụ thuộc chính sách build và khả năng hỗ trợ của plugin.

## 7. Giá trị release và phiên bản class file

Mỗi phiên bản Java tương ứng với một class-file major version. Một số giá trị thường gặp:

| Java release | Class-file major version |
| --- | ---: |
| Java 8 | 52 |
| Java 9 | 53 |
| Java 10 | 54 |
| Java 11 | 55 |
| Java 12 | 56 |
| Java 13 | 57 |
| Java 14 | 58 |
| Java 15 | 59 |
| Java 16 | 60 |
| Java 17 | 61 |
| Java 18 | 62 |
| Java 19 | 63 |
| Java 20 | 64 |
| Java 21 | 65 |
| Java 22 | 66 |
| Java 23 | 67 |
| Java 24 | 68 |
| Java 25 | 69 |

Ví dụ, Java 17 hỗ trợ class-file major version 61. Nếu ứng dụng chứa class file major version 65, đó là bytecode Java 21 và JVM Java 17 không thể nạp nó như class file thông thường.

Không cần ghi nhớ toàn bộ bảng. Khi cần chẩn đoán, có thể xem major version của lớp bằng javap hoặc công cụ phân tích bytecode.

## 8. Ví dụ đầy đủ với javac

Giả sử dự án có cấu trúc:

    project/
      src/
        com/example/
          Product.java
          Main.java
      out/

Từ thư mục gốc dự án, tạo thư mục đầu ra rồi biên dịch cho Java 17:

    mkdir out
    javac --release 17 -encoding UTF-8 -d out src/com/example/Product.java src/com/example/Main.java

Trong lệnh này:

- --release 17 đặt mục tiêu Java 17.
- -encoding UTF-8 chỉ định bảng mã nguồn.
- -d out đặt các tệp .class vào thư mục out theo cấu trúc package.
- Các đối số .java liệt kê mã nguồn cần biên dịch.

Có thể chạy chương trình trên JVM 17 hoặc mới hơn:

    java -cp out com.example.Main

Classpath cần trỏ tới thư mục gốc của cây package, ở đây là out. Tên lớp đầy đủ gồm package và tên lớp, không có phần mở rộng .class.

Nếu mã nguồn dùng cú pháp hoặc API chỉ có từ Java 21, javac --release 17 sẽ báo lỗi. Đây là hành vi mong muốn vì dự án đang yêu cầu tương thích Java 17.

## 9. Kiểm tra kết quả bằng javap

Sau khi biên dịch, có thể dùng javap để xem thông tin class file:

    javap -verbose -classpath out com.example.Main

Trong kết quả, tìm dòng:

    major version: 61

Giá trị 61 tương ứng với class file Java 17.

javap cũng có thể hiển thị constant pool, phương thức và bytecode. Khi chỉ cần xác nhận class-file version, phần major version là thông tin cần xem.

Lưu ý rằng class-file version đúng chưa chứng minh toàn bộ chương trình tương thích. Một class file có major version 61 vẫn có thể gọi một thư viện ngoài không tồn tại trên runtime, hoặc phụ thuộc vào một API nội bộ không được bảo đảm.

## 10. Vì sao -source và -target riêng lẻ chưa đủ?

Trước khi có --release, một cấu hình phổ biến là:

    javac -source 17 -target 17 ...

Hai tùy chọn này có vai trò:

- -source 17 giới hạn cú pháp và quy tắc ngôn ngữ.
- -target 17 tạo class file theo định dạng Java 17.

Nhưng compiler vẫn có thể sử dụng API của JDK hiện tại để kiểm tra mã nguồn. Vì vậy, nếu JDK hiện tại là 21, mã có thể gọi một API mới hơn Java 17.

Để giải quyết, trước đây người phát triển thường phải cung cấp thêm boot class path phù hợp với JDK đích, nhằm buộc compiler nhìn thấy thư viện nền tảng cũ. Cách này phức tạp, phụ thuộc cấu trúc JDK và không thuận tiện trong các JDK có hệ thống module.

--release gom yêu cầu về source, target và API platform vào một tùy chọn. Với JDK 9 trở lên, đây thường là lựa chọn nên dùng khi cần biên dịch cho release cũ hơn hoặc release cụ thể.

## 11. Các tùy chọn không được kết hợp với --release

Không thể dùng --release cùng -source hoặc -target trong cùng một lần gọi javac. --release đã xác định cả hai mức này.

Ví dụ không hợp lệ:

    javac --release 17 -source 17 -target 17 Main.java

Hãy dùng:

    javac --release 17 Main.java

Tương tự, --release không thể kết hợp với tùy chọn dùng để thay thế API nền tảng theo cách cũ như --system hoặc -bootclasspath. Nếu cần một platform image tùy chỉnh, phải xem các tùy chọn compiler và cách cấu hình tương ứng thay vì trộn chúng với --release.

Nếu gặp lỗi do truyền các tùy chọn xung đột, hãy kiểm tra cấu hình build xem plugin hoặc script có đang tự thêm source/target cùng với release hay không.

## 12. --release hỗ trợ những phiên bản nào?

Không phải compiler nào cũng có thể tạo đầu ra cho mọi phiên bản Java trong lịch sử. JDK hiện tại chỉ hỗ trợ một tập release nhất định, thường gồm chính release của JDK và một số release cũ được duy trì.

Ví dụ, javac của JDK 21 có thể hỗ trợ các release cũ như 8 đến 21, nhưng không thể tạo đầu ra cho một release rất cũ đã bị loại khỏi danh sách hỗ trợ của compiler.

Nếu chạy:

    javac --release 6 Main.java

trên một JDK hiện đại không còn hỗ trợ release 6, compiler sẽ báo release không được hỗ trợ.

Lỗi này không có nghĩa mã nguồn chắc chắn sai. Nó cho biết compiler hiện tại không cung cấp chế độ --release cho phiên bản đó. Có thể cần dùng một JDK cũ hơn phù hợp, hoặc đánh giá lại yêu cầu tương thích.

Ngược lại, nếu chọn release lớn hơn JDK đang dùng, compiler cũng không thể tạo đầu ra cho một nền tảng mà nó chưa biết.

## 13. Cấu hình --release trong Maven

Với Maven Compiler Plugin, có thể cấu hình release bằng property:

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

Hoặc khai báo trực tiếp trong plugin:

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
        </plugins>
    </build>

Property maven.compiler.release được Maven Compiler Plugin hỗ trợ để truyền giá trị release cho compiler. Cần dùng phiên bản plugin phù hợp và kiểm tra tài liệu của plugin mà dự án đang quản lý.

Sau khi cấu hình, chạy:

    mvn clean compile

Để kiểm tra compiler thực sự nhận tùy chọn nào, có thể bật log:

    mvn -X compile

Log debug có thể hiển thị command line hoặc tham số compiler plugin đã xây dựng. Nếu build dùng compiler fork hoặc toolchain, cần xác định đúng JDK được plugin gọi.

Không nên cấu hình đồng thời maven.compiler.release với source và target có giá trị mâu thuẫn. Hãy chọn một cách quản lý thống nhất để tránh plugin truyền các tham số xung đột.

## 14. Cấu hình --release trong Gradle

Trong Gradle, task JavaCompile có thuộc tính options.release. Ví dụ với Groovy DSL:

    tasks.withType(JavaCompile).configureEach {
        options.release = 17
    }

Với Kotlin DSL:

    tasks.withType<JavaCompile>().configureEach {
        options.release.set(17)
    }

Thiết lập này yêu cầu javac biên dịch các source set Java theo release 17.

Có thể kết hợp với Java toolchain:

    java {
        toolchain {
            languageVersion = JavaLanguageVersion.of(21)
        }
    }

    tasks.withType(JavaCompile).configureEach {
        options.release = 17
    }

Trong ví dụ, Gradle chọn toolchain JDK 21 để thực thi compiler, nhưng compiler tạo đầu ra theo Java 17. Điều này giúp tách phiên bản JDK chạy build khỏi phiên bản Java đích.

Nếu dự án cần compiler JDK 17 thay vì JDK 21, có thể đặt toolchain languageVersion là 17 và vẫn dùng release 17 hoặc cấu hình phù hợp với chính sách build. Toolchain xác định JDK được dùng; options.release xác định nền tảng đích mà javac kiểm tra.

Lưu ý rằng tùy chọn release dành cho task JavaCompile. Các compiler khác như Kotlin hoặc Scala có cơ chế target riêng; cần cấu hình chúng để tạo bytecode tương thích và dùng API phù hợp với cùng nền tảng đích.

## 15. Dùng --release cùng với module system

Java 9 giới thiệu module system. Khi biên dịch dự án có module-info.java, javac vẫn cần biết release đích để kiểm tra các API và module thuộc nền tảng đó.

Ví dụ:

    javac --release 17 -d out src/module-info.java src/com/example/Main.java

Module descriptor cũng là một phần của đầu ra và cần tương thích với phiên bản Java đích. Nếu module descriptor khai báo yêu cầu một module chỉ xuất hiện ở Java mới hơn, compiler theo release cũ có thể báo lỗi.

Không phải mọi dự án đều cần module-info.java. Với ứng dụng classpath truyền thống, --release vẫn hữu ích để kiểm soát bytecode và API mà không cần chuyển dự án sang module system.

## 16. --release không kiểm soát dependency bên ngoài

Một dự án có thể biên dịch mã nguồn của mình bằng --release 17 nhưng kéo một thư viện ngoài chỉ chạy trên Java 21. Compiler có thể không phát hiện hết vấn đề nếu thư viện đó đã được biên dịch và API của nó có thể được đọc từ classpath.

Ví dụ:

    dependencies {
        implementation 'com.example:modern-client:5.0.0'
    }

Nếu modern-client yêu cầu Java 21, việc đặt options.release = 17 cho task JavaCompile không làm thư viện đó tương thích với Java 17.

Do đó, cần kiểm tra:

- Phiên bản Java tối thiểu mà từng dependency hỗ trợ.
- Class-file version của các JAR bên ngoài.
- API nền tảng mà dependency sử dụng.
- Yêu cầu runtime được công bố trong metadata hoặc tài liệu.
- Khả năng tương thích của plugin và thư viện native.

Các công cụ phân tích dependency và bytecode có thể giúp phát hiện một số vấn đề, nhưng kiểm thử trên runtime đích vẫn rất quan trọng.

## 17. Kiểm thử trên phiên bản Java đích

Biên dịch bằng --release là một lớp bảo vệ ở compile time. Nó không thay thế kiểm thử trên JVM thực tế mà ứng dụng sẽ sử dụng.

Một quy trình đáng tin cậy nên:

1. Chọn JDK/toolchain để thực thi build.
2. Cấu hình --release theo phiên bản Java thấp nhất mà sản phẩm hỗ trợ.
3. Biên dịch toàn bộ source set.
4. Chạy unit test và integration test.
5. Chạy test trên runtime Java đích hoặc ma trận các phiên bản được hỗ trợ.
6. Kiểm tra dependency bên ngoài và native library.
7. Tạo artifact và xác nhận nó chạy được trong môi trường triển khai.

Nếu sản phẩm hỗ trợ Java 17 và Java 21, có thể biên dịch theo release 17 để bảo đảm không sử dụng API nền tảng mới hơn Java 17, sau đó chạy kiểm thử trên cả runtime 17 và 21.

## 18. Các lỗi thường gặp

### error: release version 17 not supported

Compiler hiện tại không hỗ trợ release đã chọn. Kiểm tra phiên bản javac bằng:

    javac -version

Nếu compiler quá cũ, dùng JDK mới hơn có hỗ trợ release đó hoặc chọn toolchain phù hợp.

### API không tồn tại khi dùng --release

Mã nguồn đang gọi API không thuộc Java SE của release đích. Hãy thay bằng API có sẵn ở phiên bản mục tiêu, hoặc nâng phiên bản Java tối thiểu mà sản phẩm hỗ trợ.

### class file has wrong version

Một class file được biên dịch cho Java mới hơn runtime đang dùng. Xác định class nào có major version quá cao, sau đó cấu hình compiler hoặc dependency tương ứng về mức tương thích.

### Build dùng JDK khác với JDK mong muốn

PATH, JAVA_HOME, Maven toolchain hoặc Gradle toolchain có thể khiến build gọi một compiler khác. Kiểm tra:

    java -version
    javac -version
    mvn -version
    ./gradlew -version

Các lệnh cho biết phiên bản Java mà từng công cụ đang sử dụng hoặc nhận diện. Với Gradle toolchain, cần kiểm tra cấu hình toolchain và log task compile.

### Mã biên dịch được nhưng lỗi lúc chạy

Nguyên nhân có thể là dependency không tương thích, API nội bộ, phản chiếu, native library, cấu hình module hoặc khác biệt môi trường. --release không thể phát hiện mọi lỗi runtime.

## 19. Quy tắc lựa chọn thực tế

Khi cần biên dịch cho phiên bản Java đích, có thể áp dụng các nguyên tắc:

- Dùng --release N với JDK 9 trở lên khi cần đồng thời giới hạn source, class file và API Java SE.
- Chọn N là phiên bản Java thấp nhất mà sản phẩm cam kết hỗ trợ.
- Dùng toolchain để cố định JDK thực thi compiler và các công cụ build.
- Không trộn --release với -source hoặc -target trong cùng lệnh javac.
- Không cho rằng --release kiểm soát yêu cầu Java của dependency bên ngoài.
- Kiểm tra class-file version khi điều tra lỗi không tương thích bytecode.
- Chạy kiểm thử trên runtime đích, đặc biệt với ứng dụng có dependency phức tạp.
- Giữ cấu hình Maven/Gradle nhất quán giữa local, CI và môi trường phát hành.

## 20. Kết luận

--release là tùy chọn quan trọng khi dùng javac mới để biên dịch ứng dụng cho một phiên bản Java đích. Nó kết hợp mức ngôn ngữ, định dạng class file và tập API Java SE được hỗ trợ của release đó. Nhờ vậy, compiler có thể phát hiện sớm việc mã nguồn sử dụng cú pháp hoặc API quá mới.

Chỉ dùng -source và -target có thể tạo class file cũ nhưng vẫn cho phép mã nguồn tham chiếu API mới của JDK đang cài. --release giải quyết điểm này cho các release mà compiler hỗ trợ. Tuy nhiên, nó không chọn JDK chạy build, không kiểm tra toàn bộ dependency bên ngoài và không thay thế kiểm thử trên runtime thực tế. Kết hợp --release, toolchain, quản lý dependency và kiểm thử trên phiên bản Java đích giúp build có khả năng tương thích rõ ràng và đáng tin cậy hơn.
