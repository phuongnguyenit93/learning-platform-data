# Cấu hình mã nguồn, tài nguyên và encoding nhất quán

Một dự án Java 21 cần đọc và ghi văn bản giống nhau trên máy lập trình viên, máy build và môi trường chạy. Nếu IDE lưu mã nguồn theo UTF-8 nhưng compiler đọc theo charset khác, hoặc build xử lý tài nguyên theo một encoding còn ứng dụng đọc theo encoding khác, chữ có dấu có thể bị lỗi dù logic chương trình hoàn toàn đúng.

Quy ước nên dùng cho dự án mới là **UTF-8 cho mã nguồn và tài nguyên văn bản**. Hãy khai báo quy ước này ở editor, compiler, build tool và các điểm đọc/ghi dữ liệu. Mỗi lớp cấu hình giải quyết một phần khác nhau; cấu hình charset cho compiler không tự động cấu hình cách ứng dụng đọc file lúc chạy.

## 1. Phân biệt các vị trí cần cấu hình

Encoding là quy tắc chuyển đổi giữa chuỗi byte được lưu trữ và ký tự Unicode mà chương trình xử lý. Trong một dự án Java, cần phân biệt ít nhất ba luồng:

| Luồng dữ liệu | Thành phần xử lý | Điều cần thống nhất |
|---|---|---|
| Mã nguồn (.java) | Editor và Java compiler | Editor lưu UTF-8; compiler giải mã source bằng UTF-8 |
| Tài nguyên văn bản như .properties, .json, .xml, .sql, .txt | Build tool và ứng dụng | Build filtering và mã đọc tài nguyên phải dùng đúng encoding của file |
| Dữ liệu bên ngoài như file người dùng, HTTP hoặc message | API I/O và giao thức | Chọn charset theo hợp đồng dữ liệu; không đoán từ máy đang chạy |

Tệp nhị phân như ảnh, PDF hoặc file nén không phải tài nguyên văn bản. Không áp dụng bộ lọc thay thế chuỗi hoặc xử lý encoding văn bản lên các tệp này.

## 2. Chọn UTF-8 làm quy ước chung

UTF-8 biểu diễn đầy đủ Unicode và phù hợp với mã nguồn có tiếng Việt, tên, thông báo và dữ liệu đa ngôn ngữ. Lưu các tệp văn bản bằng UTF-8 ngay từ editor để tránh việc chuyển đổi qua lại giữa nhiều bảng mã.

Từ JDK 18, UTF-8 là charset mặc định của các Java SE API trên các hệ điều hành; vì vậy Java 21 cũng mặc định UTF-8 khi gọi các API sử dụng default charset. Có thể kiểm tra giá trị runtime bằng:

~~~java
import java.nio.charset.Charset;

public class CharsetInfo {
    public static void main(String[] args) {
        System.out.println(Charset.defaultCharset());
    }
}
~~~

Default charset giúp hành vi của Java 21 nhất quán hơn giữa các máy, nhưng không thay thế việc khai báo encoding tại ranh giới dữ liệu. Một file do hệ thống khác tạo ra vẫn có thể dùng charset riêng; giao thức hoặc định dạng file mới là căn cứ để giải mã. Luồng **System.out** và **System.err** cũng có quy tắc encoding của console riêng, vì vậy lỗi hiển thị ở terminal không nhất thiết có nghĩa file nguồn bị sai.

Không dùng thay đổi thuộc tính hệ thống **file.encoding** như cách sửa encoding cho từng dự án. Hãy cấu hình compiler và API I/O ngay tại nơi sử dụng để quy ước được thể hiện rõ trong mã nguồn và build.

## 3. Cấu hình editor và mã nguồn

Trong IDE, đặt encoding của project và các tệp văn bản là UTF-8. Khi làm việc nhóm, nên lưu quy ước này trong **.editorconfig** để các editor hỗ trợ EditorConfig áp dụng cùng thiết lập:

~~~ini
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
~~~

**charset** xác định encoding; **end_of_line** chỉ quy định ký tự kết thúc dòng. Hai thiết lập giải quyết hai vấn đề khác nhau. Quy tắc line ending giúp diff ổn định giữa Windows, macOS và Linux, nhưng không chuyển một file từ bảng mã này sang bảng mã khác.

### Biên dịch trực tiếp bằng javac

Tùy chọn **-encoding** chỉ định charset để compiler đọc các file .java. Tùy chọn **--release** xác định phiên bản ngôn ngữ, bytecode và API Java mục tiêu. Với dự án Java 21, có thể cấu hình cả hai:

~~~bash
javac --release 21 -encoding UTF-8 -d out src/main/java/com/example/Main.java
~~~

Nếu bỏ **-encoding**, **javac** dùng default charset của môi trường compiler. Khai báo UTF-8 trực tiếp giúp lệnh build diễn đạt rõ quy ước của repository và tránh phụ thuộc vào cấu hình máy.

## 4. Cấu hình Maven

Với Maven, khai báo **project.build.sourceEncoding** là UTF-8. Maven Compiler Plugin dùng thuộc tính này làm encoding mặc định cho compiler; Maven Resources Plugin cũng dùng nó khi xử lý tài nguyên được filtering. Đồng thời đặt **maven.compiler.release** để build nhắm đúng Java 21.

~~~xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.16.0</version>
            <configuration>
                <encoding>UTF-8</encoding>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Việc khai báo rõ **encoding** trong compiler plugin làm cho cấu hình source dễ đọc khi xem riêng phần plugin. Thuộc tính **project.build.sourceEncoding** vẫn cần thiết vì nó là quy ước chung mà các plugin xử lý văn bản của Maven có thể sử dụng.

Nếu dự án bật resource filtering để thay placeholder trong file cấu hình, hãy giữ encoding của tài nguyên đồng nhất với UTF-8. Với trường hợp một nhóm tài nguyên thực sự có encoding riêng, cấu hình riêng cho nhóm đó và ghi lại lý do; không đổi encoding toàn dự án để xử lý một file ngoại lệ.

## 5. Cấu hình Gradle

Gradle Java Toolchain chọn JDK dùng cho các tác vụ compile, test và Javadoc. **options.release** giới hạn việc biên dịch theo Java 21, còn **options.encoding** xác định cách đọc source file. Có thể cấu hình trong **build.gradle.kts**:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release = 21
}

tasks.processResources {
    filteringCharset = "UTF-8"
}
~~~

**filteringCharset** quy định charset Gradle dùng khi đọc và ghi file có áp dụng filtering. Nếu tài nguyên chỉ được sao chép nguyên trạng và không qua bộ lọc, thao tác copy không cần giải mã rồi mã hóa lại nội dung. Khi dùng **filter**, **expand** hoặc một phép biến đổi văn bản, hãy đặt **filteringCharset** rõ ràng để kết quả không phụ thuộc default charset của JVM đang chạy Gradle.

Với dự án dùng Groovy DSL (**build.gradle**), các thuộc tính tương ứng cũng có thể đặt trong **java**, **tasks.withType(JavaCompile)** và **tasks.processResources**; tên cấu hình vẫn là **languageVersion**, **options.encoding**, **options.release** và **filteringCharset**.

## 6. Đọc và ghi văn bản rõ charset trong Java 21

Khi ứng dụng làm việc với file hoặc byte stream, chỉ định charset tại API I/O. Ví dụ dưới đây đọc và ghi file UTF-8:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class TextFileExample {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("message.txt");

        Files.writeString(
                path,
                "Xin chào, Java 21!",
                StandardCharsets.UTF_8
        );

        String content = Files.readString(path, StandardCharsets.UTF_8);
        System.out.println(content);
    }
}
~~~

**StandardCharsets.UTF_8** là hằng số có sẵn trong JDK, tránh lỗi gõ sai tên charset và không cần tra cứu charset bằng chuỗi. Với **InputStream**, dùng **InputStreamReader** có truyền charset; với **OutputStream**, dùng **OutputStreamWriter** có truyền charset. Không nên để việc chuyển đổi byte sang ký tự phụ thuộc ngầm vào default charset khi đọc dữ liệu từ hệ thống khác.

### Lưu ý riêng với java.util.Properties

Hai overload của **Properties.load** có hợp đồng encoding khác nhau:

- **load(InputStream)** diễn giải byte theo ISO-8859-1.
- **load(Reader)** nhận ký tự đã được giải mã; ứng dụng kiểm soát charset khi tạo **Reader**.

Nếu file .properties được lưu bằng UTF-8 và được đọc trực tiếp bằng **Properties**, hãy dùng **Reader**:

~~~java
import java.io.IOException;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

public class PropertiesExample {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("config", "app.properties");
        Properties properties = new Properties();

        try (Reader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
            properties.load(reader);
        }

        System.out.println(properties.getProperty("welcome"));
    }
}
~~~

Không giả định mọi API đọc .properties đều có cùng quy tắc. Hãy kiểm tra overload đang dùng và định dạng đầu vào; nếu gọi **load(InputStream)** với nội dung UTF-8 có ký tự ngoài ISO-8859-1, giá trị đọc được có thể bị sai.

## 7. Kiểm tra tính nhất quán trong nhóm và CI

Một cấu hình chỉ thực sự hữu ích khi được áp dụng trong cả môi trường phát triển và pipeline:

1. Lưu file .java và tài nguyên văn bản bằng UTF-8 trong editor.
2. Đưa **.editorconfig** vào repository và kiểm tra encoding của project trong IDE.
3. Đặt encoding cho compiler và resource filtering trong build file.
4. Dùng JDK 21 toolchain hoặc cấu hình JDK 21 tương ứng trong CI; không để mỗi máy tự chọn compiler khác nhau.
5. Thêm một chuỗi kiểm thử có tiếng Việt, ví dụ **Xin chào, thế giới!**, vào test đọc/ghi tài nguyên để phát hiện lỗi giải mã.
6. Kiểm tra nội dung tài nguyên sau bước filtering hoặc đóng gói khi dự án có biến đổi tài nguyên.

Có thể xem các thuộc tính JVM trong lúc chạy bằng:

~~~bash
java -XshowSettings:properties -version
~~~

Tìm thuộc tính **file.encoding** trong kết quả để kiểm tra default charset. Đây là thông tin chẩn đoán runtime; cấu hình build vẫn cần thể hiện rõ UTF-8 để compiler và bước xử lý tài nguyên có hợp đồng riêng.

## 8. Nhận diện lỗi encoding thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
|---|---|---|
| Compiler báo ký tự không hợp lệ hoặc không thể ánh xạ | Source file lưu bằng charset khác với charset compiler đang dùng | Lưu source thành UTF-8 và đặt **-encoding UTF-8** hoặc **options.encoding = "UTF-8"** |
| Tiếng Việt trong resource bị biến thành ký tự lạ sau build | Resource filtering dùng charset khác với encoding file gốc | Cấu hình **project.build.sourceEncoding** hoặc **filteringCharset** là UTF-8 |
| File đọc bằng Java bị sai dấu | Charset ở API đọc không khớp encoding thực của file | Chọn charset theo hợp đồng của file và truyền rõ vào API |
| **Properties** đọc sai giá trị tiếng Việt | Dùng **load(InputStream)** cho file UTF-8 | Dùng **load(Reader)** với Reader UTF-8, hoặc bảo đảm đầu vào đúng hợp đồng ISO-8859-1 |
| Terminal hiển thị sai nhưng nội dung file vẫn đúng | Charset của console không trùng với encoding của dữ liệu | Kiểm tra cấu hình terminal và console; không vội chuyển mã source file |

Không sửa lỗi bằng cách chuyển đổi encoding lặp đi lặp lại trên cùng một file. Trước tiên xác định byte của file đang được tạo ra theo encoding nào, thành phần nào giải mã byte đó và cấu hình hiện tại của thành phần ấy.

## 9. Checklist cấu hình

- [ ] Source .java được lưu bằng UTF-8.
- [ ] Editor và IDE dùng UTF-8 cho project.
- [ ] Compiler được cấu hình **-encoding UTF-8** hoặc tùy chọn tương đương.
- [ ] Build nhắm Java 21 bằng toolchain và/hoặc **--release 21**.
- [ ] Resource filtering dùng UTF-8.
- [ ] API đọc/ghi dữ liệu bên ngoài chỉ định charset theo định dạng hoặc giao thức.
- [ ] Các file .properties được đọc bằng overload phù hợp với encoding thực tế.
- [ ] CI kiểm tra build trên JDK 21 và có test với nội dung tiếng Việt.

## Tài liệu tham khảo

- [Java SE 21: Charset](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/Charset.html)
- [Java SE 21: javac command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
- [Java SE 21: Properties](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Properties.html)
- [Oracle: Preparing for Migration to JDK 21 — Default Charset](https://docs.oracle.com/en/java/javase/21/migrate/preparing-migration.html)
- [Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/)
- [Maven Resources Plugin: Encoding](https://maven.apache.org/plugins/maven-resources-plugin/examples/encoding.html)
- [Gradle: Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html)
- [Gradle: Working with Files](https://docs.gradle.org/current/userguide/working_with_files.html)
