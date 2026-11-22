# Class file compatibility trong Java

Class file là định dạng bytecode mà Java compiler tạo ra từ mã nguồn. JVM đọc class file để nạp class, kiểm tra bytecode và thực thi chương trình. **Class file compatibility** mô tả khả năng một JVM hiểu và nạp được class file được tạo bởi compiler của một phiên bản Java nhất định.

Khi ứng dụng chạy trên nhiều phiên bản JDK, cần kiểm soát phiên bản class file của ứng dụng và toàn bộ dependency. Một chương trình có thể biên dịch thành công trên máy phát triển nhưng thất bại trên máy chủ nếu class file được tạo cho JVM mới hơn. Ngược lại, class file có phiên bản cũ vẫn có thể chạy trên JVM mới hơn, miễn là các API, thư viện và hành vi mà chương trình sử dụng tương thích.

## 1. Bốn lớp tương thích cần phân biệt

Cụm từ “tương thích Java” có thể nói đến nhiều vấn đề khác nhau:

| Loại tương thích | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Source compatibility | Compiler có chấp nhận cú pháp và tính năng ngôn ngữ này không? | Java 8 không có cú pháp var của Java 10 |
| Class file / bytecode compatibility | JVM có hiểu định dạng và bytecode trong file .class không? | JVM 11 không nạp class file major version 61 của Java 17 |
| Platform API compatibility | Runtime có cung cấp class, method và field mà chương trình tham chiếu không? | Java 8 không có List.of() được thêm từ Java 9 |
| Behavioral compatibility | Chương trình có giữ hành vi mong đợi trên runtime đích không? | Thay đổi hành vi API, timezone, charset hoặc thuật toán giữa các bản Java |

Một class file có thể có phiên bản mà JVM chấp nhận nhưng vẫn lỗi khi liên kết hoặc chạy do thiếu method, thiếu dependency, khác biệt module hoặc thay đổi hành vi. Vì vậy, kiểm tra major version là bước quan trọng nhưng chưa đủ để chứng minh toàn bộ ứng dụng tương thích.

## 2. Cấu trúc phiên bản của class file

Mỗi tệp .class bắt đầu bằng header nhận diện định dạng và thông tin phiên bản. Các trường quan trọng gồm:

- **magic number**: bốn byte **CA FE BA BE**, dùng nhận diện class file.
- **minor_version**: phiên bản phụ, là số nguyên không dấu 16-bit.
- **major_version**: phiên bản chính, là số nguyên không dấu 16-bit.
- Sau header là constant pool, access flags, thông tin class, interfaces, fields, methods và attributes.

Hai trường minor và major được lưu theo thứ tự byte lớn trước (big-endian). JVM dùng chúng để xác định class file có thuộc định dạng mà runtime hỗ trợ hay không.

Ví dụ, class file được biên dịch theo Java 17 thông thường có:

~~~text
minor version: 0
major version: 61
~~~

Trong ví dụ này, **61** là major version tương ứng Java 17. Khi xem phiên bản class file, thường chỉ cần kiểm tra hai dòng minor version và major version trong kết quả javap.

Phiên bản class file là thông tin của từng tệp .class, không phải một con số chung duy nhất cho cả JAR. Một JAR có thể chứa class được biên dịch từ nhiều phiên bản Java khác nhau; JVM chỉ gặp lỗi khi nạp một class cụ thể mà nó không hỗ trợ.

## 3. Bảng ánh xạ Java release và class file major version

Bảng dưới đây liệt kê major version phổ biến của các bản Java từ Java 1.1 đến Java 26:

| Java release | Class file major version |
|---|---:|
| Java 1.1 | 45 |
| Java 1.2 | 46 |
| Java 1.3 | 47 |
| Java 1.4 | 48 |
| Java 5 | 49 |
| Java 6 | 50 |
| Java 7 | 51 |
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
| Java 26 | 70 |

Với các phiên bản hiện đại, có thể ghi nhớ quy luật:

**major version = Java release + 44**

Ví dụ: Java 17 tương ứng 17 + 44 = 61; Java 21 tương ứng 21 + 44 = 65. Quy luật này áp dụng cho các release hiện đại trong bảng, không dùng để suy ra minor version của class file đời cũ.

## 4. Chiều tương thích giữa compiler và JVM

JVM có một major version tối đa mà nó hiểu. Một JVM mới thường có thể nạp class file được tạo cho các phiên bản Java cũ hơn, trong phạm vi định dạng mà JVM hỗ trợ. JVM cũ không hiểu class file có major version mới hơn mức nó hỗ trợ.

Ví dụ:

| Class file | Runtime | Kết quả về định dạng |
|---|---|---|
| Java 8 / major 52 | Java 17 / major tối đa 61 | JVM 17 hiểu định dạng |
| Java 17 / major 61 | Java 21 / major tối đa 65 | JVM 21 hiểu định dạng |
| Java 21 / major 65 | Java 17 / major tối đa 61 | Không tương thích định dạng |
| Java 26 / major 70 | Java 21 / major tối đa 65 | Không tương thích định dạng |
| Java 17 / major 61 | Java 11 / major tối đa 55 | Không tương thích định dạng |

Ví dụ một ứng dụng được biên dịch mặc định bằng JDK 21 thường sinh class file major version 65. Nếu đưa file đó lên máy chỉ có Java 17, JVM 17 không thể nạp class file này.

Chiều ngược lại, nếu ứng dụng được biên dịch thành class file Java 17, JVM 21 có thể hiểu định dạng đó. Tuy nhiên, điều này không bảo đảm mọi API hoặc hành vi đều giống nhau; cần kiểm tra dependency và runtime behavior.

## 5. UnsupportedClassVersionError

Khi JVM cố nạp class file có phiên bản không được hỗ trợ, thường gặp lỗi:

~~~text
java.lang.UnsupportedClassVersionError:
  Hello has been compiled by a more recent version of the Java Runtime
  (class file version 65.0), this version of the Java Runtime only
  recognizes class file versions up to 61.0
~~~

Thông báo cho biết:

- **65.0** là phiên bản class file của class đang được nạp, tương ứng Java 21.
- **61.0** là major/minor tối đa mà runtime đang chạy hỗ trợ, tương ứng Java 17.
- Runtime hiện tại quá cũ so với class file.

UnsupportedClassVersionError là một dạng LinkageError. Nó thường xảy ra trong lúc JVM nạp class, trước khi chương trình có thể thực thi phần code liên quan.

Cách xử lý có hai hướng:

1. Chạy ứng dụng bằng JRE/JDK mới hơn, đủ khả năng nạp class file đã được phát hành.
2. Biên dịch lại ứng dụng và dependency từ source với target release phù hợp runtime đích, nếu dự án cần hỗ trợ runtime cũ.

Không nên chỉ đổi tên file hoặc sửa byte major version bằng hex editor. Thay đổi header không chuyển đổi bytecode, API hoặc cấu trúc class file về phiên bản cũ; kết quả có thể vẫn lỗi verifier, linkage hoặc gây hành vi không xác định.

## 6. javac: -source, -target và --release

Ba tùy chọn này có mục đích liên quan nhưng khác nhau.

| Tùy chọn | Tác dụng |
|---|---|
| -source N | Chọn phiên bản cú pháp và quy tắc ngôn ngữ Java được chấp nhận |
| -target N | Chọn phiên bản class file/bytecode mà compiler sinh ra |
| --release N | Chọn release mục tiêu, bao gồm source level, target class file và tập API Java SE tương ứng release đó |

### Vì sao -source và -target chưa đủ?

Giả sử dùng JDK 17 để biên dịch nhưng cần ứng dụng chạy trên Java 8. Lệnh:

~~~bash
javac -source 8 -target 8 ApiDemo.java
~~~

yêu cầu compiler chấp nhận cú pháp Java 8 và sinh class file major version 52. Tuy nhiên, compiler vẫn có thể nhìn thấy API của JDK 17 đang cài trên máy. Nếu source gọi một method chỉ có từ Java 9, compiler có thể chấp nhận lời gọi đó và tạo class file version 52, nhưng Java 8 runtime không có method tương ứng.

Ví dụ:

~~~java
import java.util.List;

public class ApiDemo {
    public static void main(String[] args) {
        List<String> names = List.of("Ada", "Grace");
        System.out.println(names);
    }
}
~~~

List.of() được bổ sung từ Java 9. Nếu biên dịch code này bằng compiler mới chỉ với -source 8 -target 8, class file có thể mang major version 52 nhưng vẫn tham chiếu method không tồn tại trong Java 8. Khi chạy trên Java 8, ứng dụng có thể gặp NoSuchMethodError.

### Dùng --release

Từ JDK 9, nên dùng **--release** khi cần biên dịch cho một Java release cũ hơn:

~~~bash
javac --release 8 ApiDemo.java
~~~

Lệnh này sẽ báo lỗi biên dịch vì List.of() không thuộc API Java 8. Compiler không cho source tham chiếu API mới hơn release đã chọn.

Ví dụ cho dự án Java 17:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/Hello.java
~~~

--release 17 giúp compiler:

- Áp dụng quy tắc ngôn ngữ của Java 17.
- Sinh class file tương ứng Java 17, major version 61.
- Kiểm tra code dựa trên API Java SE có trong release 17.

--release có từ JDK 9 và chỉ hỗ trợ các release mà JDK compiler hiện tại cung cấp. Không kết hợp --release với -source hoặc -target trong cùng một lệnh. Nếu dùng JDK 8, tùy chọn này chưa có; cần dùng compiler/toolchain phù hợp và cấu hình boot class path tương ứng khi phải target Java cũ.

## 7. Ví dụ thực hành: kiểm tra class file version

Tạo source file **Hello.java**:

~~~java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Class file compatibility");
    }
}
~~~

Giả sử máy đang dùng JDK 21 trở lên nhưng ứng dụng cần chạy trên Java 17. Tạo thư mục output rồi biên dịch với release 17.

Linux/macOS:

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 -d out src/Hello.java
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -d out src/Hello.java
~~~

Dùng javap để đọc thông tin class file:

~~~bash
javap -verbose -classpath out Hello
~~~

Trong output, tìm hai dòng:

~~~text
minor version: 0
major version: 61
~~~

Kết quả major version: 61 xác nhận compiler đã tạo class file theo định dạng Java 17. Có thể lọc nhanh trên PowerShell:

~~~powershell
javap -verbose -classpath out Hello | Select-String "minor version|major version"
~~~

Chạy chương trình:

~~~bash
java -cp out Hello
~~~

Stdout:

~~~text
Class file compatibility
~~~

Để kiểm tra runtime thực tế, dùng java -version. Nếu runtime là Java 17 hoặc mới hơn, JVM hiểu class file version 61. Nếu runtime là Java 11, class file này không thể được nạp.

## 8. Minor version và preview features

Ngoài major version, class file còn có minor version. Với class file Java hiện đại thông thường, minor version thường là 0.

Từ Java 12, class file sử dụng **minor version 65535** để đánh dấu việc sử dụng preview features của một Java release. Đây là dấu hiệu đặc biệt; JVM chỉ cho chạy class file preview khi bật preview và runtime thuộc đúng Java release đã tạo class đó.

Ví dụ, trên JDK 26 nếu source dùng preview feature của Java 26:

~~~bash
javac --enable-preview --release 26 PreviewDemo.java
java --enable-preview PreviewDemo
~~~

Khi kiểm tra bằng javap, class file preview có thể hiển thị:

~~~text
minor version: 65535
major version: 70
~~~

Các lưu ý:

- Cần bật --enable-preview khi biên dịch và khi chạy.
- Class file preview gắn với đúng Java release có preview feature đó.
- Không xem preview class file như bytecode phát hành ổn định có thể chuyển tự do giữa các release.
- Không dùng preview feature trong sản phẩm cần tương thích dài hạn nếu chưa chấp nhận rủi ro thay đổi hoặc loại bỏ feature.

## 9. Class file version trong JAR và dependency

Một JAR là container chứa nhiều entry. Mỗi class bên trong có thể có major/minor version riêng. Vì vậy, ứng dụng chính có thể target Java 17 nhưng vẫn lỗi trên Java 17 nếu một thư viện phụ thuộc được biên dịch cho Java 21.

Ví dụ:

~~~text
application.jar
  com/example/Main.class       major 61
  com/example/Service.class    major 61
  dependency/
    library-class.class        major 65
~~~

Nếu library-class.class được JVM nạp trong quá trình chạy, Java 17 sẽ không hiểu major version 65. Lỗi có thể xuất hiện sau khi ứng dụng khởi động, khi code lần đầu truy cập class trong dependency đó.

Khi điều tra:

1. Xác định class xuất hiện trong UnsupportedClassVersionError.
2. Xác định class thuộc artifact/JAR nào.
3. Kiểm tra major version của chính class đó.
4. Kiểm tra phiên bản thư viện có hỗ trợ Java runtime mục tiêu hay không.
5. Chọn bản dependency tương thích hoặc nâng runtime theo chính sách triển khai.

Dùng javap với class trên classpath hoặc trong JAR:

~~~bash
javap -verbose -classpath library.jar com.example.LibraryClass
~~~

Có thể liệt kê nội dung JAR:

~~~bash
jar --list --file library.jar
~~~

Không chỉ kiểm tra class chính. Cần rà soát dependency bắc cầu, plugin build, agent, thư viện test và các module được nạp động.

## 10. Multi-release JAR

Multi-release JAR cho phép một artifact chứa nhiều phiên bản triển khai của cùng class, phù hợp với các Java runtime khác nhau. JAR cần có manifest:

~~~text
Multi-Release: true
~~~

Cấu trúc ví dụ:

~~~text
library.jar
  META-INF/
    MANIFEST.MF
    versions/
      11/
        com/example/Feature.class
      17/
        com/example/Feature.class
  com/
    example/
      Feature.class
~~~

Khi chạy trên runtime Java 17, class loader có thể chọn entry trong META-INF/versions/17 nếu có; trên Java 11 có thể chọn bản trong versions/11; nếu không có entry phù hợp, dùng class ở vị trí gốc. Runtime cũ hơn Java 9 không áp dụng cơ chế multi-release và sử dụng các entry gốc.

Các bản class theo phiên bản phải được biên dịch cho runtime tương ứng và phải giữ hợp đồng API mà thư viện công bố. Multi-release JAR giúp một thư viện tận dụng API mới trên runtime mới mà vẫn giữ implementation nền cho runtime cũ; nó không tự làm cho một class file mới chạy được trên JVM cũ.

## 11. Cấu hình target compatibility trong build tool

Cần cấu hình release mục tiêu ngay trong build script để máy local và CI dùng cùng một quy tắc.

### Maven

Có thể đặt release và source encoding trong properties:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Hoặc khai báo trong Maven Compiler Plugin:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>17</release>
        <encoding>UTF-8</encoding>
    </configuration>
</plugin>
~~~

Build:

~~~bash
mvn clean package
~~~

Cấu hình release giúp compiler kiểm tra source và API theo Java 17. Nếu dự án dùng nhiều module, hãy kiểm tra cấu hình ở parent POM và các module con để tránh module ghi đè release ngoài ý muốn.

### Gradle Groovy DSL

Trong **build.gradle**:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}
~~~

### Gradle Kotlin DSL

Trong **build.gradle.kts**:

~~~kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 17
    options.encoding = "UTF-8"
}
~~~

Toolchain chọn JDK dùng để build; options.release đặt API và class file release mục tiêu. Hai cấu hình giải quyết hai câu hỏi khác nhau: dùng compiler nào và tạo output tương thích với release nào.

## 12. Quy trình chẩn đoán lỗi tương thích

### Bước 1: Xác định Java runtime đang chạy

~~~bash
java -version
~~~

Đây là phiên bản JVM thực sự được gọi trong terminal hoặc môi trường triển khai. Trên máy có nhiều JDK, lệnh java và javac có thể trỏ đến các bản khác nhau.

Windows PowerShell:

~~~powershell
Get-Command java
Get-Command javac
~~~

Linux/macOS:

~~~bash
which java
which javac
~~~

### Bước 2: Xác định compiler đang dùng

~~~bash
javac -version
~~~

Đừng giả định compiler và runtime có cùng phiên bản. Build tool, IDE, container hoặc CI có thể dùng JDK riêng.

### Bước 3: Đọc class file version

~~~bash
javap -verbose -classpath out com.example.Main
~~~

Đọc major version rồi đối chiếu bảng ở phần 3. Nếu lỗi xảy ra ở dependency, chạy javap trên class của dependency đó.

### Bước 4: Kiểm tra cấu hình build

Tìm các tùy chọn --release, -source, -target, toolchain và compiler configuration. Xác nhận build thực sự truyền cấu hình đó đến javac, đặc biệt khi build được điều khiển bởi IDE hoặc daemon.

### Bước 5: Kiểm tra dependency

Xác định class lỗi thuộc thư viện nào, kiểm tra phiên bản dependency và Java baseline do thư viện công bố. Cập nhật dependency tương thích hoặc nâng runtime nếu đó là lựa chọn phù hợp.

### Bước 6: Clean build và thử trên runtime đích

Xóa output build cũ theo quy trình dự án, build lại bằng cấu hình release đã chọn và chạy test trên đúng Java runtime tối thiểu cần hỗ trợ. Chỉ xem build thành công trên JDK mới là chưa đủ.

## 13. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Chỉ cần đặt -target 8 là chạy được trên Java 8 | Bytecode có thể là major 52 nhưng vẫn tham chiếu API chỉ có ở Java mới hơn |
| -source 8 làm compiler chỉ thấy API Java 8 | -source chọn ngôn ngữ; không giới hạn đầy đủ API runtime |
| Class file version cũ bảo đảm chương trình chạy trên JVM mới | JVM có thể hiểu định dạng, nhưng dependency, API và hành vi vẫn có thể không tương thích |
| Chỉ cần kiểm tra class chính trong JAR | Dependency hoặc class được nạp động cũng có thể có major version cao hơn |
| Sửa major version bằng hex editor sẽ hạ bytecode | Thay header không chuyển đổi bytecode hay API |
| --release 17 có nghĩa chương trình sẽ chạy trên mọi Java từ 17 trở lên | Đây là cấu hình biên dịch theo Java 17; vẫn cần kiểm thử dependency và hành vi trên runtime triển khai |
| Toolchain 17 tự động bảo đảm mọi dependency target 17 | Toolchain chọn JDK build; dependency bên ngoài vẫn có thể được biên dịch bằng release mới hơn |
| Preview class file chỉ cần đúng major version | Preview còn dùng minor version 65535 và cần runtime cùng release với --enable-preview |

## 14. Checklist phát hành ứng dụng tương thích nhiều Java version

- [ ] Xác định runtime tối thiểu mà sản phẩm cần hỗ trợ.
- [ ] Dùng JDK/compiler phù hợp và cấu hình --release rõ ràng.
- [ ] Không chỉ dựa vào -source và -target khi cần kiểm soát API.
- [ ] Kiểm tra major/minor version của class chính và các dependency quan trọng.
- [ ] Xác nhận dependency bắc cầu, plugin và agent hỗ trợ runtime mục tiêu.
- [ ] Kiểm tra multi-release JAR nếu thư viện có nhiều implementation theo Java release.
- [ ] Chỉ bật preview feature khi sản phẩm chấp nhận ràng buộc runtime cùng release.
- [ ] Chạy clean build trong CI và test trên runtime tối thiểu được hỗ trợ.
- [ ] Kiểm tra cả lỗi linkage như NoSuchMethodError, NoClassDefFoundError và UnsupportedClassVersionError.
- [ ] Ghi Java baseline trong tài liệu build và hướng dẫn triển khai.

## 15. Ghi nhớ

- Class file chứa bytecode cùng major/minor version mà JVM dùng để xác định định dạng có được hỗ trợ hay không.
- Major version tăng theo Java release; ví dụ Java 8 là 52, Java 17 là 61, Java 21 là 65 và Java 26 là 70.
- JVM mới thường nạp được class file cũ; JVM cũ không nạp được class file mới hơn mức nó hỗ trợ.
- UnsupportedClassVersionError thường báo class file được tạo bằng Java mới hơn runtime hiện tại.
- --release là lựa chọn phù hợp từ JDK 9 khi cần đồng thời kiểm soát ngôn ngữ, bytecode và API mục tiêu.
- -source và -target riêng lẻ không giới hạn đầy đủ API của platform.
- Kiểm tra dependency và class file bên trong JAR, không chỉ class chính của ứng dụng.
- Preview class file dùng minor version 65535 và cần bật preview trên đúng Java release.
- Chỉ có clean build và test trên runtime mục tiêu mới xác nhận được mức tương thích thực tế.

## Tài liệu tham khảo chính thức

- [Java Virtual Machine Specification — Class File Format](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-4.html)
- [javac Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html)
- [javap Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javap.html)
- [JEP 247: Compile for Older Platform Versions](https://openjdk.org/jeps/247)
- [JEP 12: Preview Language and VM Features](https://openjdk.org/jeps/12)
- [JAR File Specification — Multi-Release JAR Files](https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html)