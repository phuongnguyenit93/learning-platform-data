# Manifest Automatic-Module-Name

> Phạm vi: Java Platform Module System (JPMS, từ Java 9). **Automatic-Module-Name** là thuộc tính trong manifest của JAR, dùng để đặt tên ổn định cho JAR khi nó được đưa lên module path nhưng chưa có module descriptor tường minh.

## Mục tiêu

Sau bài này, bạn có thể:

- Xác định đúng vị trí và cú pháp của thuộc tính **Automatic-Module-Name**.
- Phân biệt explicit module, automatic module và JAR chạy trên class path.
- Giải thích cách JVM đặt tên automatic module từ manifest hoặc tên file JAR.
- Thêm thuộc tính này bằng Maven hoặc Gradle.
- Kiểm tra tên module thực tế và dùng nó trong directive **requires**.
- Hiểu giới hạn của automatic module trong quá trình chuyển thư viện cũ sang JPMS.

## 1. Automatic-Module-Name là gì?

Một JAR chưa có file **module-info.class** có thể được dùng như một **automatic module** nếu đặt trên module path. Java cần một tên module để các module khác tham chiếu đến nó bằng directive **requires**.

Tên automatic module được xác định theo thứ tự:

1. Nếu manifest có thuộc tính **Automatic-Module-Name** hợp lệ, dùng giá trị đó.
2. Nếu không có thuộc tính này, Java suy ra tên module từ tên file JAR.

Thuộc tính này giúp thư viện công bố tên module ổn định, không phụ thuộc vào tên artifact hoặc phiên bản trong tên file. Ví dụ, các bản phát hành **acme-logging-2.4.0.jar** và **acme-logging-2.5.0.jar** có thể cùng mang tên module **com.acme.logging**.

**Automatic-Module-Name không tạo ra module descriptor tường minh.** Nó chỉ cung cấp tên cho automatic module khi JAR được xử lý trên module path.

## 2. Khai báo trong JAR manifest

Manifest nằm tại đường dẫn:

~~~text
META-INF/MANIFEST.MF
~~~

Thêm thuộc tính vào phần main attributes của manifest:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.acme.logging
~~~

Một số nguyên tắc khi đặt giá trị:

- Giá trị phải là tên module hợp lệ theo quy tắc định danh module của Java.
- Nên dùng tên dạng reverse-domain, chẳng hạn **com.acme.logging** hoặc **org.example.parser**.
- Các thành phần tên được phân cách bằng dấu chấm; tránh dấu gạch ngang, khoảng trắng và ký tự không hợp lệ.
- Không thêm đuôi **.jar**, đường dẫn, Maven group/artifact syntax hay phiên bản vào giá trị.
- Tên module có phân biệt chữ hoa và chữ thường; nên chọn một cách viết ổn định và giữ nguyên qua các bản phát hành.
- Thuộc tính phải nằm trong phần đầu của manifest, trước dòng trống phân cách các named sections.

Ví dụ đúng:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: org.example.image
~~~

Ví dụ không nên dùng:

~~~text
Automatic-Module-Name: org-example-image
~~~

Dấu gạch ngang trong ví dụ cuối không tạo thành một tên module Java hợp lệ. Hãy dùng **org.example.image**.

Nếu manifest được tạo bởi build tool, hãy cấu hình thuộc tính trong phần manifest của plugin đóng gói JAR. Không cần tự tạo một file manifest thủ công nếu công cụ build đã quản lý nó.

## 3. Java chọn tên module như thế nào?

Cần phân biệt ba trường hợp sau.

### Trường hợp A: JAR có module-info.class

Nếu JAR có module descriptor tường minh, tên module được lấy từ khai báo **module** trong file **module-info.class**.

~~~java
module com.acme.logging {
    exports com.acme.logging;
}
~~~

Trong trường hợp này, tên trong module descriptor là nguồn xác định tên module. Thuộc tính **Automatic-Module-Name** trong manifest không thay thế hoặc ghi đè tên đã khai báo trong **module-info.class**.

### Trường hợp B: JAR không có module-info.class và được đặt trên module path

Java xem JAR là automatic module.

- Có **Automatic-Module-Name** hợp lệ: dùng chính giá trị trong manifest.
- Không có thuộc tính: suy ra tên từ tên file JAR.

Ví dụ:

| Tên file | Manifest | Tên automatic module |
|---|---|---|
| **acme-logging-2.4.0.jar** | **com.acme.logging** | **com.acme.logging** |
| **acme-parser-1.3.jar** | Không có | Tên được suy ra từ tên file, thường là **acme.parser** |
| **image-tools.jar** | **org.example.image** | **org.example.image** |

Quy tắc suy tên từ file có xử lý phần mở rộng và phần phiên bản theo quy tắc đặt tên automatic module. Ký tự không phù hợp được chuẩn hóa thành dấu chấm; vì vậy tên suy ra có thể thay đổi khi tên file, classifier hoặc cách đóng gói thay đổi.

Không nên dựa vào tên suy ra cho một thư viện cần cung cấp module name ổn định. Hãy khai báo **Automatic-Module-Name** ngay cả khi hiện tại tên file đã tạo ra một tên có vẻ phù hợp.

### Trường hợp C: JAR được đặt trên class path

Thuộc tính **Automatic-Module-Name** không biến JAR thành named module khi chạy trên class path. Các lớp của JAR vẫn thuộc unnamed module theo cơ chế class path truyền thống.

Do đó, cùng một JAR có thể:

- được dùng như thư viện class path trong ứng dụng cũ;
- được nhận diện bằng tên automatic module khi đặt trên module path.

Đây là một lý do thuộc tính này hữu ích trong quá trình chuyển đổi thư viện sang JPMS.

## 4. Automatic module có đặc điểm gì?

Khi JAR chưa có module descriptor được đặt trên module path, Java tạo descriptor tự động cho nó. Automatic module là một named module, vì vậy module khác có thể tham chiếu đến nó bằng tên trong **requires**.

Automatic module có các đặc điểm đáng chú ý:

- Nó đọc được các module khác trong module configuration theo quy tắc của automatic module.
- Tất cả package của nó được export, nên module phụ thuộc có thể truy cập các public type trong những package đó.
- Nó không có danh sách **requires**, **exports**, **opens**, **uses** và **provides** do tác giả thư viện thiết kế trong một module descriptor tường minh.
- Tên module vẫn được quản lý trong module graph như tên của một named module.

Hệ quả là automatic module giúp thư viện cũ tham gia module graph nhanh chóng, nhưng không cung cấp mức đóng gói và khai báo phụ thuộc rõ ràng như explicit module.

Ví dụ, đặt JAR có tên module **com.acme.logging** trên module path cho phép module ứng dụng khai báo:

~~~java
module com.acme.app {
    requires com.acme.logging;
}
~~~

Ứng dụng có thể biên dịch và chạy với thư viện đó mà chưa cần thư viện có **module-info.java**.

## 5. Cấu hình bằng Maven

Với Maven, dùng **maven-jar-plugin** để thêm manifest entry vào JAR được đóng gói:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-jar-plugin</artifactId>
    <version>3.4.2</version>
    <configuration>
        <archive>
            <manifestEntries>
                <Automatic-Module-Name>com.acme.logging</Automatic-Module-Name>
            </manifestEntries>
        </archive>
    </configuration>
</plugin>
~~~

Đặt cấu hình này trong phần **build/plugins** của file **pom.xml**.

Sau khi chạy:

~~~bash
mvn clean package
~~~

JAR đầu ra sẽ chứa manifest entry **Automatic-Module-Name: com.acme.logging** nếu plugin này thực sự tạo artifact mà bạn định phát hành.

Nếu dự án có nhiều loại JAR hoặc dùng plugin shade/assembly để tạo JAR cuối cùng, hãy kiểm tra đúng artifact được phân phối. Plugin đóng gói cuối có thể tạo lại manifest và làm mất entry đã khai báo ở bước trước.

## 6. Cấu hình bằng Gradle

### Kotlin DSL — build.gradle.kts

~~~kotlin
tasks.jar {
    manifest {
        attributes(
            mapOf("Automatic-Module-Name" to "com.acme.logging")
        )
    }
}
~~~

### Groovy DSL — build.gradle

~~~groovy
tasks.named('jar') {
    manifest {
        attributes(
            'Automatic-Module-Name': 'com.acme.logging'
        )
    }
}
~~~

Sau đó đóng gói:

~~~bash
./gradlew clean jar
~~~

Trên Windows có thể dùng **gradlew.bat clean jar**.

Tương tự Maven, hãy kiểm tra JAR cuối cùng được publish. Nếu task khác tạo shaded JAR, fat JAR hoặc artifact phân phối riêng, cần bảo đảm manifest của artifact cuối vẫn có thuộc tính này.

## 7. Kiểm tra tên module trong JAR đã đóng gói

Không nên chỉ nhìn vào cấu hình build. Hãy kiểm tra artifact thực tế sau khi đóng gói.

Dùng lệnh **jar --describe-module**:

~~~bash
jar --describe-module --file build/libs/acme-logging-2.4.0.jar
~~~

Với JAR không có **module-info.class** nhưng có **Automatic-Module-Name**, kết quả sẽ nhận diện tên module **com.acme.logging** là một automatic module. Nếu kết quả cho thấy tên được suy ra từ tên file, hãy kiểm tra manifest của artifact.

Có thể trích manifest để đọc trực tiếp:

~~~bash
jar --extract --file build/libs/acme-logging-2.4.0.jar META-INF/MANIFEST.MF
~~~

Sau đó mở file **META-INF/MANIFEST.MF** và tìm dòng:

~~~text
Automatic-Module-Name: com.acme.logging
~~~

Lệnh trích xuất ghi file vào thư mục hiện tại, vì vậy nên chạy trong một thư mục kiểm tra tạm thời.

Nếu JAR có **module-info.class**, **jar --describe-module** sẽ hiển thị descriptor tường minh. Khi đó, hãy kiểm tra tên module trong descriptor thay vì kỳ vọng thuộc tính manifest quyết định tên.

## 8. Dùng automatic module trong ứng dụng modular

Giả sử thư viện có file:

~~~text
libs/
└── acme-logging-2.4.0.jar
~~~

Manifest của JAR chứa:

~~~text
Automatic-Module-Name: com.acme.logging
~~~

Module ứng dụng khai báo:

~~~java
module com.acme.app {
    requires com.acme.logging;
}
~~~

Ví dụ cấu trúc source:

~~~text
src/
└── com.acme.app/
    ├── module-info.java
    └── com/acme/app/Main.java
~~~

Biên dịch ứng dụng với thư viện trên module path:

~~~bash
javac --module-path libs \
      --module-source-path src \
      -d out \
      -m com.acme.app
~~~

Chạy ứng dụng:

~~~bash
java --module-path out:libs \
     -m com.acme.app/com.acme.app.Main
~~~

Trong ví dụ trên, **com.acme.logging** là tên module mà ứng dụng dùng trong **requires**. Nó không cần trùng với tên file **acme-logging-2.4.0.jar**.

Trên Windows, dấu phân cách nhiều phần tử của module path là dấu chấm phẩy (**;**); trên macOS và Linux là dấu hai chấm (**:**).

## 9. Những giới hạn và lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không tìm thấy module khi biên dịch | JAR không nằm trên module path hoặc tên trong **requires** không khớp tên module thực tế | Kiểm tra đường dẫn và chạy **jar --describe-module** |
| Tên module thay đổi theo phiên bản JAR | Manifest thiếu **Automatic-Module-Name**, Java phải suy tên từ filename | Thêm một tên module ổn định vào manifest |
| Vẫn dùng tên cũ dù đã thêm manifest entry | JAR đang có **module-info.class**, nên tên lấy từ descriptor tường minh | Kiểm tra và cập nhật khai báo **module** trong descriptor |
| Hai JAR có cùng tên module | Manifest của hai artifact khai báo cùng tên hoặc có nhiều phiên bản cùng xuất hiện trên module path | Chọn tên duy nhất và loại bỏ artifact trùng khỏi module path |
| Không truy cập được package mong muốn như kỳ vọng | Đang nhầm automatic module với explicit module hoặc nhầm tên module với tên package | Kiểm tra package thực tế, public type và trạng thái module; nhớ rằng automatic module export toàn bộ package |
| Ứng dụng vẫn chạy trên class path nhưng không resolve được bằng module path | Thuộc tính manifest chỉ đặt tên automatic module, không tự tạo module descriptor hoặc cấu hình phụ thuộc tường minh | Đưa JAR lên module path, dùng đúng tên trong **requires** và kiểm tra module graph |

Một rủi ro khác là **split package**: cùng một package xuất hiện trong nhiều module khác nhau trên module path. Automatic module export tất cả package của nó, nên việc đưa nhiều JAR cũ có cấu trúc package chồng lấn vào module graph có thể gây lỗi resolve hoặc làm kiến trúc khó quản lý. Hãy kiểm tra package của các JAR trước khi ghép chúng vào cùng một ứng dụng modular.

Cũng cần phân biệt:

- **Tên module**: định danh trong module graph, ví dụ **com.acme.logging**.
- **Tên artifact**: tên sản phẩm/thư viện trong hệ thống build, ví dụ **acme-logging**.
- **Phiên bản artifact**: ví dụ **2.4.0**.
- **Tên package**: ví dụ **com.acme.logging.api**.

Chúng có thể có quan hệ quy ước với nhau nhưng không phải cùng một khái niệm.

## 10. Lộ trình chuyển thư viện cũ sang explicit module

**Automatic-Module-Name** là bước chuyển tiếp hữu ích khi thư viện chưa sẵn sàng có **module-info.class**.

Một lộ trình thường dùng:

1. Giữ thư viện tương thích với class path như hiện tại.
2. Thêm **Automatic-Module-Name** ổn định vào manifest và phát hành artifact.
3. Cho ứng dụng modular dùng thư viện qua **requires** với tên đã công bố.
4. Phân tích package công khai, phụ thuộc và service của thư viện.
5. Khi sẵn sàng, bổ sung **module-info.java** với các directive **requires**, **exports**, **opens**, **uses** và **provides** thực sự cần thiết.
6. Kiểm tra module descriptor của JAR phát hành. Khi có descriptor tường minh, tên module trong descriptor là tên được sử dụng; manifest attribute không còn quyết định tên module.

Khi chuyển sang explicit module, hãy xem đây là thay đổi thiết kế API/module boundary: chỉ export package cần công bố, khai báo dependency rõ ràng và kiểm tra khả năng tương thích của người dùng thư viện. Việc chỉ thêm manifest attribute chưa tạo ra các ranh giới đóng gói đó.

## 11. Ghi nhớ

- **Automatic-Module-Name** là main attribute trong **META-INF/MANIFEST.MF**.
- Nó đặt tên ổn định cho JAR chưa có **module-info.class** khi JAR nằm trên module path.
- Nếu manifest không có thuộc tính, tên automatic module được suy ra từ tên file JAR.
- Nếu JAR có module descriptor tường minh, tên trong descriptor được ưu tiên.
- Đặt JAR trên class path vẫn dùng unnamed module; manifest attribute không thay đổi cơ chế class path.
- Automatic module export tất cả package và đọc các module khác trong module configuration; nó là cầu nối tương thích, không thay thế một module descriptor được thiết kế đầy đủ.
- Kiểm tra artifact cuối bằng **jar --describe-module** trước khi phát hành.

## Tài liệu tham khảo

- [JEP 261 — Module System](https://openjdk.org/jeps/261)
- [JAR File Specification — Manifest](https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html)
- [ModuleFinder — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/ModuleFinder.html)
- [ModuleDescriptor — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/ModuleDescriptor.html)
