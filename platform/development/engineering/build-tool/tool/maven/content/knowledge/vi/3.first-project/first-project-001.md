# Tạo dự án Java tối thiểu bằng `pom.xml`

## 1. Mục tiêu và điều kiện chuẩn bị

Một dự án Maven Java tối thiểu có thể chỉ gồm **một tệp `pom.xml`** và **một lớp Java có phương thức `main`**. Maven đọc `pom.xml` để biết dự án là gì, dùng Java phiên bản nào để biên dịch, tải plugin cần thiết và tạo sản phẩm build. Không cần Spring Boot, IDE, thư viện bên ngoài hoặc cấu hình nhiều module để bắt đầu.

Sau bài này, bạn có thể:

- Tạo thủ công dự án Java thuần theo cấu trúc chuẩn của Maven.
- Hiểu các thành phần thiết yếu trong `pom.xml`: `modelVersion`, `groupId`, `artifactId`, `version`, `properties` và plugin biên dịch.
- Chạy `mvn clean package` và giải thích vì sao thư mục `target/` cùng tệp JAR được tạo ra.
- Chạy lớp Java đã đóng gói, kiểm tra kết quả và chẩn đoán những lỗi cấu hình đầu tiên.

**Yêu cầu:** Có JDK 17 trở lên, Maven tương thích với JDK đang dùng và terminal có thể gọi lệnh `mvn`. Kiểm tra từ đúng terminal dùng để thực hành:

~~~bash
mvn --version
java -version
javac -version
~~~

Trong kết quả `mvn --version`, hãy xác nhận **Java version** phù hợp. `javac -version` giúp xác nhận công cụ biên dịch Java có sẵn trong môi trường shell. Nếu Maven chưa được cài toàn cục, có thể dùng Maven Wrapper của một dự án đã cấu hình wrapper; bài này giả định lệnh `mvn` hoạt động. Lần build đầu thường cần kết nối Internet để Maven lấy các plugin chưa được lưu trong cache.

## 2. Cấu trúc thư mục chuẩn

Tạo dự án có tên `hello-maven` với cây thư mục sau:

~~~text
hello-maven/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── HelloMaven.java
~~~

Ý nghĩa của từng phần:

| Vị trí | Vai trò |
| --- | --- |
| `hello-maven/pom.xml` | Project Object Model: mô tả tọa độ, cấu hình build, plugin và dependency của dự án. |
| `src/main/java/` | Thư mục mã nguồn Java chính theo quy ước Maven. |
| `com/example/` | Đường dẫn tương ứng với khai báo `package com.example;` trong lớp Java. |
| `HelloMaven.java` | Mã nguồn có `main(String[] args)` để chạy thử. |
| `target/` | Thư mục sản phẩm build do Maven tạo sau khi chạy; chưa cần tự tạo. |

Maven còn có các thư mục theo quy ước như `src/main/resources/`, `src/test/java/` và `src/test/resources/`. Chúng chưa cần thiết đối với ví dụ chỉ in một dòng ra màn hình.

Có thể tạo trước thư mục mã nguồn bằng terminal:

**Linux/macOS, Bash:**

~~~bash
mkdir -p hello-maven/src/main/java/com/example
cd hello-maven
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force -Path "hello-maven\src\main\java\com\example" | Out-Null
Set-Location hello-maven
~~~

Sau đó tạo hai tệp `pom.xml` ở thư mục gốc và `src/main/java/com/example/HelloMaven.java` bằng trình soạn thảo bất kỳ. Có thể dùng IDE, nhưng cấu trúc và nội dung tệp vẫn là phần quyết định Maven build ra sao.

## 3. Viết `pom.xml` hoàn chỉnh

Tạo tệp `hello-maven/pom.xml` với **nguyên văn** nội dung sau:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>hello-maven</artifactId>
    <version>1.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Đây là POM của một dự án Java độc lập, không có thẻ `parent` hay `dependencies`. Ta khai báo rõ plugin compiler để ví dụ có hành vi ổn định với Java 17. Phiên bản plugin `3.13.0` là một phiên bản cụ thể có hỗ trợ cấu hình `release`; không phải yêu cầu sử dụng bản mới nhất.

### Giải nghĩa từng thành phần

- **`<project>` và namespace:** xác định đây là POM Maven theo mô hình XML. `xsi:schemaLocation` giúp công cụ nhận diện schema; không phải URL dependency mà Maven phải tải để chạy ứng dụng.
- **`<modelVersion>4.0.0</modelVersion>`:** phiên bản *mô hình POM*. Không phải phiên bản Apache Maven được cài trên máy. Vì vậy không đổi giá trị này thành `3.9.x` khi Maven CLI báo phiên bản `3.9.x`.
- **`groupId` = `com.example`:** định danh nhóm/tổ chức sở hữu artifact. Thường chọn theo tên miền đảo ngược; không bắt buộc luôn giống Java package, dù dùng giống nhau ở ví dụ này.
- **`artifactId` = `hello-maven`:** tên artifact. Với cấu hình mặc định, tên này góp phần tạo tệp JAR đầu ra.
- **`version` = `1.0-SNAPSHOT`:** phiên bản đang phát triển. `SNAPSHOT` mang ngữ nghĩa phiên bản phát triển; nó không làm tệp JAR tự động chạy.
- **`packaging` = `jar`:** yêu cầu đóng gói dạng JAR. `jar` vốn là giá trị packaging mặc định của dự án Maven khi không khai báo, nhưng viết ra để người học thấy rõ ý định.
- **`maven.compiler.release` = `17`:** yêu cầu Maven Compiler Plugin biên dịch nhắm tới nền tảng Java 17 (bytecode và API khả dụng của bản release đó) khi thực thi với JDK hỗ trợ `--release 17`. Java dùng để chạy Maven và Java release của artifact là hai khái niệm khác nhau.
- **`project.build.sourceEncoding` = `UTF-8`:** quy định encoding mã nguồn cho plugin hỗ trợ thuộc tính này, tránh phụ thuộc mặc định môi trường.
- **`maven-compiler-plugin`:** plugin chịu trách nhiệm biên dịch nguồn Java. Khóa phiên bản plugin bằng `3.13.0` giúp tránh sự khác biệt do phiên bản plugin mặc định của các môi trường Maven khác nhau.

Tọa độ **`com.example:hello-maven:1.0-SNAPSHOT`** gồm `groupId:artifactId:version`. Đây là danh tính artifact Maven. Với dự án JAR mặc định, tệp được tạo có tên dự kiến:

~~~text
target/hello-maven-1.0-SNAPSHOT.jar
~~~

Không có thẻ `dependencies` vì chương trình chỉ sử dụng `java.lang.System` từ Java SE. Không cần khai báo dependency để dùng lớp thuộc thư viện chuẩn JDK. Khi thêm thư viện bên ngoài trong bài sau, Maven sẽ quản lý chúng qua `dependencies`.

## 4. Viết lớp Java đầu tiên

Tạo tệp đúng đường dẫn **`src/main/java/com/example/HelloMaven.java`**:

~~~java
package com.example;

public class HelloMaven {
    public static void main(String[] args) {
        System.out.println("Hello from Maven!");
    }
}
~~~

Lưu ý ba điểm:

1. Dòng `package com.example;` tương ứng với đường dẫn `com/example/` bên dưới `src/main/java`. Khớp package và cấu trúc thư mục là quy ước cần duy trì để Maven và IDE cùng nhận diện nguồn rõ ràng.
2. Tên tệp `HelloMaven.java` phải khớp tên `public class HelloMaven` (Java phân biệt chữ hoa/chữ thường).
3. `public static void main(String[] args)` là điểm vào để chạy lớp như một chương trình Java. Maven có thể biên dịch và đóng gói các lớp mà không cần `main`, nhưng ta dùng `main` để xác nhận chương trình chạy được.

Mã này là một chương trình độc lập, không cần thư viện ngoài hoặc tham số dòng lệnh. Kết quả chuẩn khi thực thi là một dòng:

~~~text
Hello from Maven!
~~~

## 5. Build dự án bằng Maven

Mở terminal tại thư mục **`hello-maven/`** — nơi chứa `pom.xml` — rồi chạy:

~~~bash
mvn validate
~~~

Lệnh này cho Maven đọc cấu hình dự án và thực hiện pha `validate`. Nếu cấu hình POM có lỗi cú pháp XML hoặc thiếu phần tử bắt buộc, đây là bước đầu phù hợp để phát hiện. Tuy nhiên, `validate` thành công **không có nghĩa** lớp Java đã biên dịch thành công.

Tiếp theo, biên dịch và đóng gói:

~~~bash
mvn clean package
~~~

Lệnh gồm hai phần:

- **`clean`:** chạy pha dọn dẹp theo *clean lifecycle*, thường xóa thư mục `target/` của bản build trước.
- **`package`:** đưa dự án qua các pha cần thiết của *default lifecycle* cho đến `package`, bao gồm biên dịch `src/main/java`, xử lý tài nguyên, biên dịch/chạy test nếu có và tạo artifact JAR.

Một đoạn log build thành công thường kết thúc bằng:

~~~text
[INFO] BUILD SUCCESS
~~~

Các dòng về plugin, thời gian và bước build có thể khác theo phiên bản Maven, cache và hệ điều hành; không dùng một bản log cố định để khẳng định tất cả môi trường phải giống nhau. Vì ví dụ chưa có test, Maven không có bài test người học tự viết để thực thi.

Sau khi thành công, cây thư mục chứa thêm các sản phẩm tương tự:

~~~text
hello-maven/
├── pom.xml
├── src/
│   └── main/
│       └── java/
│           └── com/
│               └── example/
│                   └── HelloMaven.java
└── target/
    ├── classes/
    │   └── com/
    │       └── example/
    │           └── HelloMaven.class
    └── hello-maven-1.0-SNAPSHOT.jar
~~~

*Minh họa chỉ hiển thị các mục quan trọng; `target/` thực tế có thể chứa thêm thư mục metadata, trạng thái plugin, tài nguyên và báo cáo.*

`HelloMaven.java` là **mã nguồn**; `HelloMaven.class` là **bytecode** sau biên dịch; `hello-maven-1.0-SNAPSHOT.jar` là **gói JAR** chứa lớp đã biên dịch và metadata đóng gói do plugin tạo. Mặc định Maven không biến JAR thư viện này thành một chương trình khởi chạy bằng `java -jar`.

## 6. Chạy chương trình đã build

Cách dễ nhất là chạy trực tiếp lớp được biên dịch:

~~~bash
java -cp target/classes com.example.HelloMaven
~~~

**Kết quả chính xác:**

~~~text
Hello from Maven!
~~~

`-cp` (viết dài `-classpath`) chỉ định nơi Java tìm các lớp. Ở lệnh trên, `target/classes` là classpath và `com.example.HelloMaven` là tên lớp đầy đủ gồm package.

Cũng có thể chạy lớp nằm trong JAR vừa tạo:

~~~bash
java -cp target/hello-maven-1.0-SNAPSHOT.jar com.example.HelloMaven
~~~

**Kết quả chính xác:**

~~~text
Hello from Maven!
~~~

Vì chương trình chỉ dùng thư viện chuẩn Java, chạy với classpath duy nhất là JAR này là đủ. Với ứng dụng có dependency ngoài, classpath có thể cần thêm các thư viện hoặc một cách đóng gói khác.

**Tại sao không gõ ngay `java -jar target/hello-maven-1.0-SNAPSHOT.jar`?** `java -jar` cần thuộc tính `Main-Class` thích hợp trong manifest của JAR. POM hiện tại **chưa cấu hình** thuộc tính đó; `main` trong nguồn Java không tự khiến JAR có manifest chứa `Main-Class`. Lệnh `java -cp ... com.example.HelloMaven` là cách chạy phù hợp với ví dụ tối thiểu. Khi muốn có executable JAR, có thể cấu hình `maven-jar-plugin` với manifest `mainClass` hoặc dùng chiến lược đóng gói tương ứng ở bài nâng cao.

Nếu muốn kiểm tra các mục nằm trong JAR bằng JDK:

~~~bash
jar tf target/hello-maven-1.0-SNAPSHOT.jar
~~~

Trong danh sách trả về, tìm `com/example/HelloMaven.class`. Lệnh `jar tf` chỉ liệt kê nội dung JAR; nó không chạy phương thức `main`.

## 7. Hiểu những lệnh Maven thường dùng ngay từ dự án đầu tiên

| Lệnh | Tác dụng | Khi nào dùng? |
| --- | --- | --- |
| `mvn validate` | Kiểm tra giai đoạn xác nhận cấu hình dự án. | Vừa tạo/sửa `pom.xml` và muốn kiểm tra bước đầu. |
| `mvn compile` | Chạy các pha cần thiết đến `compile`; tạo lớp trong `target/classes`. | Muốn phát hiện lỗi biên dịch mà chưa cần JAR. |
| `mvn test` | Chạy các pha đến `test`, gồm test nếu đã khai báo đúng và có nguồn test. | Khi dự án bắt đầu có unit test. |
| `mvn package` | Biên dịch, kiểm thử nếu có rồi tạo artifact theo packaging. | Cần JAR của dự án. |
| `mvn clean` | Xóa kết quả build trước theo clean lifecycle. | Muốn loại bỏ artifact cũ. |
| `mvn clean package` | Dọn đầu ra cũ và tạo lại artifact. | Cần xác nhận một bản build mới rõ ràng. |
| `mvn install` | Chạy đến pha `install`, đưa artifact vào kho Maven cục bộ để dự án khác có thể dùng. | Chỉ khi cần sử dụng artifact cục bộ từ dự án khác; không cần cho ví dụ này. |

Một khác biệt quan trọng: `mvn package` **không tự xóa** `target/` cũ, trong khi `mvn clean package` yêu cầu dọn trước. Maven xử lý thứ tự pha của lifecycle; người dùng không cần gọi từng pha `validate`, `compile` rồi `package` riêng khi chạy `mvn package`.

## 8. Kiểm tra sự nhất quán giữa POM, mã nguồn và đầu ra

Ba thông tin cần đồng bộ khi tự đổi tên dự án:

| Nơi khai báo | Ví dụ hiện tại | Ý nghĩa |
| --- | --- | --- |
| `<artifactId>` | `hello-maven` | Thành phần tên artifact/JAR mặc định. |
| `<version>` | `1.0-SNAPSHOT` | Thành phần phiên bản trong tên JAR mặc định. |
| `package` + tên class | `com.example.HelloMaven` | Tên lớp phải dùng trong câu lệnh `java -cp`. |

Ví dụ, nếu đổi `artifactId` thành `welcome-app` và giữ `version` là `1.0-SNAPSHOT`, đường dẫn JAR mặc định sẽ đổi thành `target/welcome-app-1.0-SNAPSHOT.jar`. Nếu đổi package Java thành `org.example.demo`, hãy chuyển tệp tới `src/main/java/org/example/demo/HelloMaven.java` và chạy tên lớp `org.example.demo.HelloMaven`. Việc đổi `groupId` không tự đổi khai báo Java `package`; đây là hai khái niệm liên quan theo quy ước nhưng độc lập về cơ chế.

Các thay đổi thử nghiệm nên được kiểm tra bằng `mvn clean package`, sau đó dùng tên JAR và tên class **thực tế**. Không dựa vào tệp `target/` của lần build cũ sau khi đổi tọa độ hoặc cấu trúc nguồn.

## 9. Lỗi thường gặp và cách xử lý

| Thông báo/hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `mvn: command not found` hoặc `'mvn' is not recognized` | Shell chưa tìm được Maven trên `PATH`. | Xác minh cài đặt Maven; mở terminal mới sau khi sửa `PATH`, chạy `mvn --version`. |
| Maven báo không có POM trong thư mục hiện tại | Bạn chạy lệnh ngoài thư mục `hello-maven` hoặc đặt sai tên/vị trí `pom.xml`. | Chuyển vào thư mục chứa `pom.xml`; kiểm tra đúng tên, không phải `pom.xml.txt`. |
| `release version 17 not supported` | Trình biên dịch được chọn không hỗ trợ `--release 17`, thường do JDK quá cũ. | Đối chiếu `mvn --version`, `javac -version`, JDK/toolchains; chạy Maven/compiler bằng JDK hỗ trợ Java 17. |
| `JAVA_HOME` không hợp lệ hoặc Maven chạy trên Java không mong muốn | `JAVA_HOME`/launcher/`PATH` đang chỉ đến Java khác. | Kiểm tra đường dẫn runtime trong `mvn --version`; chỉnh biến môi trường và mở lại terminal. |
| `Non-parseable POM` | XML sai cú pháp, thiếu thẻ đóng, ký tự `&` chưa escape hoặc thẻ đặt sai. | Kiểm tra nội dung `pom.xml` và vị trí Maven chỉ ra; so lại với POM mẫu. |
| `cannot find symbol` | Tên lớp, method, biến hoặc kiểu dữ liệu trong Java không hợp lệ/không được import. | Đọc dòng lỗi compiler, sửa Java source rồi chạy lại `mvn compile`. |
| `Could not find or load main class` | Classpath hoặc tên class đầy đủ sai; bản build chưa có class. | Kiểm tra `target/classes`, package và tên class; dùng `com.example.HelloMaven`. |
| `no main manifest attribute` khi chạy `java -jar` | JAR chưa cấu hình `Main-Class`. | Dùng lệnh `java -cp ... com.example.HelloMaven` trong bài này hoặc cấu hình manifest cho JAR chạy trực tiếp. |
| Lỗi tải Maven plugin/dependency | Mạng, proxy, mirror, kho lưu trữ hoặc cache chưa đáp ứng. | Kiểm tra kết nối, cấu hình `settings.xml`/repository/mirror và thông báo lỗi cụ thể; không sửa mã Java khi lỗi chỉ xảy ra ở bước tải plugin. |
| `UnsupportedClassVersionError` khi chạy class | JVM lúc chạy thấp hơn phiên bản bytecode đã biên dịch. | Chạy bằng Java 17 trở lên với ví dụ này, hoặc điều chỉnh mục tiêu biên dịch phù hợp yêu cầu thực tế. |

Ngoài ra, hãy kiểm tra việc lưu tệp Java với đúng đuôi `.java` và POM ở thư mục gốc. Một IDE có thể hiển thị dự án hợp lệ nhờ cấu hình riêng, nhưng lệnh Maven vẫn chỉ đọc `pom.xml` cùng cấu trúc nguồn mà Maven nhận diện.

## 10. Bài thực hành tự kiểm chứng

Thực hiện tuần tự từ thư mục `hello-maven`:

1. Kiểm tra `mvn --version` để xác nhận JVM đang chạy Maven.
2. Tạo `pom.xml` và lớp `HelloMaven.java` đúng như mẫu.
3. Chạy `mvn clean package` và xác nhận có `BUILD SUCCESS`.
4. Kiểm tra `target/classes/com/example/HelloMaven.class` và `target/hello-maven-1.0-SNAPSHOT.jar`.
5. Chạy `java -cp target/hello-maven-1.0-SNAPSHOT.jar com.example.HelloMaven` và đối chiếu một dòng `Hello from Maven!`.
6. Đổi nội dung chuỗi in ra thành `My first Maven project`, build lại rồi chạy lại để chứng minh JAR mới chứa mã mới.

Để tự đánh giá, thử trả lời: `modelVersion` có phải phiên bản lệnh `mvn` không? Vì sao project không có `dependencies` mà vẫn in được ra console? `mvn compile` và `mvn package` khác nhau ở sản phẩm nào? Vì sao `java -cp` chạy được nhưng `java -jar` chưa chắc chạy được? Nếu bạn giải thích được từ chính POM, cây thư mục và kết quả thực thi, bạn đã hoàn thành vòng đầu tiên **viết mã Java → biên dịch bằng Maven → tạo JAR → chạy chương trình**.
