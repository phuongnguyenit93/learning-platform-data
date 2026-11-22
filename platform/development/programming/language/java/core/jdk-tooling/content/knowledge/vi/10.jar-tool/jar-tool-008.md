# Class-Path trong JAR Manifest

## 1. Manifest và thuộc tính Class-Path là gì?

Mỗi tệp JAR là một archive dựa trên định dạng ZIP. Ngoài class file và resource, JAR có thể chứa tệp manifest tại đường dẫn **META-INF/MANIFEST.MF**. Manifest lưu metadata dưới dạng các cặp tên thuộc tính và giá trị.

Hai thuộc tính quan trọng khi tạo JAR có thể chạy độc lập là:

- **Main-Class**: tên lớp chứa điểm vào ứng dụng, thường là lớp có phương thức main.
- **Class-Path**: danh sách URL đến các JAR hoặc thư mục bổ sung cần được thêm vào class path khi JAR được sử dụng để chạy ứng dụng.

Ví dụ manifest:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.Main
Class-Path: lib/common.jar lib/logging.jar

~~~

Khi chạy:

~~~bash
java -jar app.jar
~~~

Java launcher đọc Main-Class để tìm lớp chính và sử dụng Class-Path trong manifest để tìm các thư viện bên ngoài. Nhờ đó, người dùng có thể khởi chạy ứng dụng bằng một lệnh ngắn mà không phải tự gõ toàn bộ classpath trên command line.

**Class-Path trong manifest không nhúng các thư viện phụ thuộc vào JAR chính.** Nó chỉ tham chiếu đến vị trí các tệp hoặc thư mục khác. Khi phân phối ứng dụng, phải gửi kèm các dependency theo đúng cấu trúc đường dẫn đã khai báo.

## 2. Cấu trúc cơ bản của META-INF/MANIFEST.MF

Manifest là văn bản có cấu trúc theo từng section. Section đầu tiên là main section, chứa các thuộc tính áp dụng cho toàn bộ JAR. Các section tiếp theo có thể mô tả metadata của từng entry trong archive.

Một manifest đơn giản:

~~~text
Manifest-Version: 1.0
Main-Class: demo.app.Main
Class-Path: lib/helper.jar lib/logging.jar

~~~

Các quy tắc quan trọng:

1. Mỗi thuộc tính có dạng **Tên: Giá trị**.
2. Main section bắt đầu ngay từ đầu tệp và kết thúc bằng một dòng trống.
3. **Manifest-Version** nên xuất hiện đầu tiên trong main section.
4. **Main-Class** và **Class-Path** phải đặt trong main section để áp dụng cho toàn bộ JAR.
5. Tên lớp trong Main-Class là tên nhị phân đầy đủ, có package, không có phần mở rộng .class và không dùng dấu gạch chéo của đường dẫn tệp.
6. Manifest phải có dòng trống kết thúc section. Công cụ jar tự tạo manifest chuẩn khi dùng tùy chọn --manifest.

Ví dụ đúng:

~~~text
Manifest-Version: 1.0
Main-Class: com.acme.billing.Main
Class-Path: lib/common.jar lib/database.jar

~~~

Ví dụ tên Main-Class không đúng:

~~~text
Main-Class: com/acme/billing/Main.class
~~~

Giá trị đúng là **com.acme.billing.Main**. JVM dùng tên lớp để nạp class, không dùng đường dẫn file class.

## 3. Cách viết thuộc tính Class-Path

Class-Path chứa một danh sách URL được phân cách bằng một hoặc nhiều dấu cách. Mỗi URL có thể là đường dẫn tương đối được giải quyết từ vị trí JAR chứa manifest hoặc URL tuyệt đối.

Ví dụ:

~~~text
Class-Path: lib/common.jar lib/logging.jar config/

~~~

Các mục trên có ý nghĩa:

- **lib/common.jar**: JAR nằm trong thư mục lib cạnh JAR ứng dụng.
- **lib/logging.jar**: một JAR phụ thuộc khác trong cùng thư mục lib.
- **config/**: thư mục resource hoặc class bổ sung; URL thư mục kết thúc bằng dấu gạch chéo.

Không dùng dấu hai chấm hoặc dấu chấm phẩy để phân tách danh sách trong thuộc tính manifest. Dấu phân cách của Class-Path là dấu cách. Điều này khác với tùy chọn launcher -cp, vốn dùng dấu phân cách theo hệ điều hành: dấu chấm phẩy trên Windows và dấu hai chấm trên Linux/macOS.

Ví dụ so sánh:

~~~text
# Trong manifest: các URL cách nhau bằng dấu cách
Class-Path: lib/a.jar lib/b.jar

# Trong command line Windows:
java -cp "app.jar;lib/a.jar;lib/b.jar" com.example.Main

# Trong command line Linux/macOS:
java -cp "app.jar:lib/a.jar:lib/b.jar" com.example.Main
~~~

### Đường dẫn tương đối được tính từ đâu?

Đây là quy tắc quan trọng nhất của Class-Path manifest: URL tương đối được giải quyết dựa trên URL/vị trí của JAR chứa manifest, không dựa trên thư mục làm việc hiện tại của terminal.

Giả sử cấu trúc:

~~~text
deployment/
  app.jar
  lib/
    helper.jar
    logging.jar
~~~

Trong app.jar có:

~~~text
Class-Path: lib/helper.jar lib/logging.jar

~~~

Khi chạy app.jar từ thư mục deployment, các dependency được tìm trong deployment/lib. Nếu người dùng chuyển sang một thư mục khác rồi chạy JAR bằng đường dẫn đầy đủ, các URL tương đối vẫn được tính từ vị trí app.jar.

Đường dẫn phải trỏ đến đúng tệp hoặc thư mục đã được đóng gói. Trên hệ điều hành phân biệt chữ hoa/chữ thường, tên thư mục và tệp trong manifest cũng phải khớp chính xác.

### Đường dẫn có khoảng trắng

Class-Path dùng dấu cách làm dấu phân cách URL, vì vậy khoảng trắng nằm trong tên tệp cần được mã hóa theo quy tắc URL, thường là **%20**.

Ví dụ:

~~~text
Class-Path: lib/My%20Library.jar
~~~

Không đặt đường dẫn có khoảng trắng trong dấu nháy đơn hoặc nháy kép như cách viết shell command; manifest không áp dụng quy tắc trích dẫn của shell.

## 4. Quan hệ giữa Main-Class, Class-Path và java -jar

Một executable JAR thường khai báo cả Main-Class và Class-Path:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.Main
Class-Path: lib/common.jar lib/database.jar

~~~

Chạy bằng:

~~~bash
java -jar app.jar
~~~

Launcher thực hiện các bước chính:

1. Mở JAR được chỉ định.
2. Đọc manifest.
3. Tìm lớp được khai báo trong Main-Class.
4. Xây dựng class path ứng dụng từ JAR chính và các URL trong Class-Path.
5. Nạp lớp chính và gọi phương thức main.

Các đối số đặt sau tên JAR được truyền vào main(String[] args):

~~~bash
java -jar app.jar --port 8080 production
~~~

Trong ví dụ này, --port và production là đối số của ứng dụng. Chúng không phải VM option hay launcher option.

### Class-Path manifest và -cp khác nhau thế nào?

| Tiêu chí | Manifest Class-Path | Launcher -cp / --class-path |
|---|---|---|
| Nơi khai báo | META-INF/MANIFEST.MF | Command line hoặc script |
| Cách phân cách | Dấu cách giữa các URL | Dấu phân cách theo OS |
| Đường dẫn tương đối | Tính từ JAR chứa manifest | Tính từ thư mục làm việc hiện tại |
| Mục đích | Gắn dependency vào cấu hình của JAR | Chỉ định classpath cho một lần chạy |
| Khi dùng -jar | Được launcher sử dụng | Classpath ngoài do -cp cung cấp bị bỏ qua trong chế độ -jar |

Nếu cần chỉ định classpath trực tiếp, có thể chạy lớp chính thay vì dùng -jar:

~~~bash
java -cp "app.jar:lib/helper.jar" com.example.Main
~~~

Trên Windows, thay dấu hai chấm bằng dấu chấm phẩy. Trong chế độ -jar, hãy đặt dependency trong Class-Path của manifest và bảo đảm các đường dẫn đó tồn tại.

## 5. Thực hành: tạo ứng dụng gồm hai JAR

Ta tạo một ứng dụng nhỏ gồm:

- **app.jar**: chứa lớp chính demo.app.Main.
- **helper.jar**: chứa lớp demo.support.MessageProvider.
- Manifest của app.jar khai báo Main-Class và Class-Path.

Cấu trúc dự án:

~~~text
project/
  src/
    demo/
      app/
        Main.java
      support/
        MessageProvider.java
  build/
    classes/
    lib/
      helper.jar
    app.jar
  manifest.mf
~~~

### Bước 1: Tạo lớp thư viện

Tệp src/demo/support/MessageProvider.java:

~~~java
package demo.support;

public class MessageProvider {
    public String message() {
        return "Loaded from helper.jar";
    }
}
~~~

### Bước 2: Tạo lớp chính

Tệp src/demo/app/Main.java:

~~~java
package demo.app;

import demo.support.MessageProvider;

public class Main {
    public static void main(String[] args) {
        System.out.println(new MessageProvider().message());
        System.out.println("args=" + String.join(",", args));
    }
}
~~~

### Bước 3: Biên dịch các lớp

Tạo thư mục build/classes và build/lib, sau đó chạy:

~~~bash
javac --release 17 -d build/classes \
    src/demo/support/MessageProvider.java \
    src/demo/app/Main.java
~~~

Sau lệnh này, các file class nằm trong:

~~~text
build/classes/demo/support/MessageProvider.class
build/classes/demo/app/Main.class
~~~

### Bước 4: Đóng gói helper.jar

Chạy từ thư mục project:

~~~bash
jar --create --file build/lib/helper.jar \
    -C build/classes demo/support
~~~

Lệnh -C chuyển thư mục gốc đóng gói sang build/classes và chỉ thêm package demo/support. Vì vậy, trong helper.jar, đường dẫn lớp vẫn là demo/support/MessageProvider.class.

### Bước 5: Tạo manifest cho app.jar

Tệp manifest.mf:

~~~text
Manifest-Version: 1.0
Main-Class: demo.app.Main
Class-Path: lib/helper.jar

~~~

Class-Path được viết tương đối với build/app.jar. JAR chính nằm trong build, còn helper.jar nằm trong build/lib, vì vậy URL lib/helper.jar trỏ đúng dependency.

### Bước 6: Đóng gói app.jar

~~~bash
jar --create --file build/app.jar \
    --manifest manifest.mf \
    -C build/classes demo/app
~~~

JAR chính chỉ chứa package demo/app. Dependency vẫn ở ngoài trong build/lib/helper.jar và được manifest tham chiếu.

### Bước 7: Chạy ứng dụng

~~~bash
java -jar build/app.jar one two
~~~

Kết quả chính xác:

~~~text
Loaded from helper.jar
args=one,two
~~~

Nếu xóa hoặc đổi tên build/lib/helper.jar, ứng dụng có thể khởi động nhưng sẽ gặp lỗi khi JVM cần nạp MessageProvider. Điều đó chứng minh Class-Path chỉ tham chiếu dependency; nó không sao chép thư viện vào app.jar.

## 6. Kiểm tra manifest và dependency

Khi ứng dụng không tìm thấy lớp, hãy xác minh cả nội dung JAR và đường dẫn dependency.

### Xem nội dung JAR

~~~bash
jar --list --file build/app.jar
jar --list --file build/lib/helper.jar
~~~

Trong app.jar, kiểm tra có:

~~~text
META-INF/MANIFEST.MF
demo/app/Main.class
~~~

Trong helper.jar, kiểm tra có:

~~~text
META-INF/MANIFEST.MF
demo/support/MessageProvider.class
~~~

Manifest mặc định có thể được jar tự tạo. Nếu dùng manifest tùy chỉnh, kiểm tra tệp META-INF/MANIFEST.MF bên trong app.jar để xác nhận Main-Class và Class-Path đúng.

Có thể trích riêng manifest:

~~~bash
jar --extract --file build/app.jar META-INF/MANIFEST.MF
~~~

Sau đó mở tệp META-INF/MANIFEST.MF và kiểm tra:

~~~text
Manifest-Version: 1.0
Main-Class: demo.app.Main
Class-Path: lib/helper.jar
~~~

### Kiểm tra đường dẫn khi chạy từ thư mục khác

Giả sử app.jar và lib/helper.jar nằm trong deployment như ví dụ trước. Có thể chuyển sang thư mục làm việc khác rồi chạy JAR bằng đường dẫn tuyệt đối:

~~~bash
cd /tmp
java -jar /opt/myapp/deployment/app.jar
~~~

Nếu manifest khai báo Class-Path tương đối đúng, JVM vẫn tìm dependency theo vị trí deployment/app.jar. Đây là cách kiểm tra để tránh nhầm lẫn giữa đường dẫn manifest và thư mục làm việc hiện tại.

### Kiểm tra classpath và nguồn lớp

Có thể bật log nạp lớp để xem JVM tìm lớp từ đâu:

~~~bash
java -Xlog:class+load=info -jar build/app.jar
~~~

Log này hữu ích khi có nhiều bản sao của cùng một lớp hoặc khi ứng dụng nạp nhầm phiên bản dependency. Nội dung log có thể dài; hãy lọc theo tên lớp cần kiểm tra.

## 7. Nhiều dependency và thứ tự tìm kiếm

Class-Path có thể liệt kê nhiều JAR:

~~~text
Class-Path: lib/core.jar lib/json.jar lib/logging.jar

~~~

Các URL được xử lý theo danh sách trong thuộc tính. Khi có nhiều vị trí chứa cùng một tên lớp, thứ tự class path có thể quyết định lớp nào được nạp trước. Đây là nguyên nhân phổ biến của lỗi dùng nhầm phiên bản thư viện.

Một số lưu ý:

- Tránh đưa hai phiên bản khác nhau của cùng một thư viện vào class path.
- Giữ tên và vị trí JAR ổn định trong gói phát hành.
- Kiểm tra dependency transitively cần thiết của từng thư viện.
- Một JAR được tham chiếu có thể khai báo Class-Path riêng trong manifest của nó; vì vậy cần kiểm tra cả manifest của dependency khi chẩn đoán.
- Không dựa vào thứ tự ngẫu nhiên của quá trình copy file hoặc đóng gói để giải quyết xung đột class.

Class-Path manifest không phải công cụ quản lý dependency đầy đủ. Nó không quản lý version, scope, checksum, xung đột dependency hoặc tải thư viện theo module. Với dự án có nhiều thư viện, nên dùng Maven hoặc Gradle để giải quyết dependency và tạo gói phân phối có cấu trúc rõ ràng.

## 8. Class-Path trong manifest và module path

Class-Path manifest thuộc cơ chế class path truyền thống, thường dùng với JAR không modular và ứng dụng chạy trên class loader class path.

Java Platform Module System có cơ chế riêng:

- **--class-path / -cp**: tìm lớp trong thư mục và JAR thuộc class path.
- **--module-path / -p**: tìm các module có descriptor hoặc automatic module.
- **module-info.java**: khai báo requires, exports, opens và các quan hệ module.

Thuộc tính Class-Path không thay thế khai báo requires trong module-info.java. Nếu ứng dụng được thiết kế theo named module, hãy quản lý dependency bằng module path và module descriptor thay vì cố dùng manifest Class-Path như một hệ thống module.

Một modular JAR có thể được đóng gói với module-info.class. Khi chạy bằng module path, JVM giải quyết quan hệ module theo quy tắc JPMS. Không nên nhầm việc JAR có manifest với việc JAR tự động trở thành một module được khai báo đầy đủ.

## 9. Tạo manifest bằng công cụ jar và build tool

### Dùng jar

Công cụ jar có thể nhận manifest có sẵn:

~~~bash
jar --create --file app.jar --manifest manifest.mf -C classes .
~~~

Hoặc đặt Main-Class bằng tùy chọn:

~~~bash
jar --create --file app.jar --main-class com.example.Main -C classes .
~~~

Khi cần Class-Path, tạo manifest có thuộc tính đó rồi truyền bằng --manifest. Nếu vừa dùng manifest tùy chỉnh vừa dùng tùy chọn --main-class, hãy kiểm tra manifest cuối cùng để chắc chắn chỉ có một Main-Class đúng.

### Maven

Với Maven, có thể cấu hình Maven JAR Plugin để ghi Main-Class và Class-Path vào manifest. Ví dụ cấu hình cơ bản:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-jar-plugin</artifactId>
    <configuration>
        <archive>
            <manifest>
                <mainClass>demo.app.Main</mainClass>
                <addClasspath>true</addClasspath>
                <classpathPrefix>lib/</classpathPrefix>
            </manifest>
        </archive>
    </configuration>
</plugin>
~~~

Cấu hình addClasspath yêu cầu plugin ghi dependency classpath vào manifest. Cấu trúc phân phối vẫn phải đặt các JAR phụ thuộc trong đúng thư mục lib/ tương ứng với vị trí JAR ứng dụng. Chỉ ghi manifest không tự copy các dependency vào thư mục đó; hãy cấu hình thêm bước copy hoặc assembly/distribution phù hợp.

### Gradle

Gradle cho phép tùy chỉnh manifest khi tạo JAR:

~~~groovy
tasks.jar {
    manifest {
        attributes(
            'Main-Class': 'demo.app.Main',
            'Class-Path': configurations.runtimeClasspath.files
                .collect { file -> "lib/" + file.name }
                .join(' ')
        )
    }
}
~~~

Đây là ví dụ minh họa cách tạo danh sách từ runtimeClasspath. Nếu dùng cấu hình này, phải bảo đảm các file dependency thực sự được copy vào thư mục lib cạnh JAR khi phân phối. Cần xử lý thêm trường hợp tên file trùng nhau hoặc dependency có tên phiên bản khác nhau.

Với ứng dụng thực tế, Gradle Application Plugin, Maven Assembly Plugin hoặc công cụ đóng gói tương ứng thường giúp tạo thư mục phân phối hoàn chỉnh gồm JAR ứng dụng, dependency và script chạy.

## 10. Giới hạn và lỗi thường gặp

### ClassNotFoundException hoặc NoClassDefFoundError

Nguyên nhân thường gặp:

- JAR dependency không nằm tại vị trí Class-Path khai báo.
- Sai chữ hoa/chữ thường trong tên file hoặc thư mục.
- Manifest dùng đường dẫn tính từ thư mục làm việc thay vì vị trí JAR.
- Dependency chưa được copy vào gói phát hành.
- Một dependency khác bị thiếu ở phía sau chuỗi phụ thuộc.

Cách xử lý: kiểm tra META-INF/MANIFEST.MF trong JAR, kiểm tra file thực tế, chạy jar --list và bật log nạp lớp.

### Main method không được tìm thấy

Kiểm tra Main-Class có đúng tên lớp nhị phân đầy đủ không. Lớp đó cần có điểm vào phù hợp, ví dụ:

~~~java
public static void main(String[] args)
~~~

Không thêm .class, không dùng đường dẫn thư mục và không ghi sai package.

### Đường dẫn có dấu cách

Mã hóa dấu cách trong URL bằng %20. Không thêm dấu nháy shell vào giá trị manifest. Nếu có thể, dùng tên thư mục đơn giản, không có khoảng trắng để giảm lỗi khi triển khai.

### JAR chạy được trên máy phát triển nhưng không chạy trên máy khác

Có thể máy phát triển vô tình có dependency trong classpath, IDE hoặc biến môi trường. Máy triển khai chỉ có các tệp được đóng gói. Hãy thử chạy bằng java -jar từ một thư mục làm việc khác và trong một môi trường sạch để kiểm tra tính độc lập của gói.

### Dùng -cp cùng -jar nhưng dependency vẫn không được nạp

Trong chế độ java -jar, classpath ngoài do -cp hoặc CLASSPATH cung cấp không được dùng để thay thế classpath của ứng dụng. Đưa dependency vào Class-Path của manifest hoặc chạy lớp chính bằng java -cp ... com.example.Main.

### Manifest quá dài hoặc sai định dạng

Theo định dạng JAR, một dòng manifest không được dài quá **72 byte** trước ký tự xuống dòng. Dòng dài phải được ngắt và dòng tiếp theo bắt đầu bằng một dấu cách để tiếp tục giá trị trước đó. Độ dài được tính theo byte, không đơn giản là số ký tự Unicode. Nên để công cụ jar hoặc build tool sinh manifest thay vì tự nối chuỗi dài bằng tay.

Ví dụ dòng tiếp tục:

~~~text
Class-Path: lib/core.jar lib/json.jar lib/logging.jar
 lib/metrics.jar lib/database.jar

~~~

Dấu cách đầu dòng thứ hai là ký hiệu nối tiếp, không phải dấu phân cách mới.

## 11. Bảo mật và vận hành

Manifest Class-Path ảnh hưởng trực tiếp đến các thư viện mà ứng dụng nạp. Vì vậy:

- Chỉ phân phối dependency từ nguồn tin cậy.
- Không để người dùng không đáng tin có quyền thay thế JAR trong thư mục lib.
- Kiểm tra phiên bản và checksum dependency trong pipeline phát hành.
- Tránh đường dẫn tuyệt đối gắn với một máy cụ thể.
- Giữ thư mục triển khai có cấu trúc ổn định.
- Không để JAR không tin cậy xuất hiện trước thư viện đáng tin trong class path.
- Ghi lại danh sách dependency và phiên bản trong artifact hoặc metadata phát hành.

Class-Path chỉ khai báo nơi tìm thư viện; nó không xác minh tính an toàn, nguồn gốc hoặc tính tương thích của các JAR đó.

## 12. Checklist trước khi phát hành executable JAR

- [ ] Manifest có Manifest-Version và Main-Class đúng.
- [ ] Main-Class là tên lớp đầy đủ, không có .class.
- [ ] Class-Path nằm trong main section của manifest.
- [ ] Các mục Class-Path cách nhau bằng dấu cách.
- [ ] URL tương đối được tính từ vị trí JAR chứa manifest.
- [ ] JAR và thư mục dependency tồn tại trong gói phân phối.
- [ ] Đường dẫn có khoảng trắng được mã hóa đúng.
- [ ] Không có dependency trùng phiên bản hoặc class bị shadowing.
- [ ] Chạy thử bằng java -jar từ một thư mục làm việc khác.
- [ ] Kiểm tra output và log nạp lớp khi có lỗi.
- [ ] Dùng Maven/Gradle để quản lý dependency nếu ứng dụng có nhiều thư viện.
- [ ] Phân biệt class path truyền thống với module path của JPMS.
