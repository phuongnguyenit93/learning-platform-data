# Đóng gói ứng dụng classpath với --input, --main-jar và --main-class

Với ứng dụng Java không dùng module descriptor, jpackage có thể đóng gói ứng dụng chạy trên classpath bằng ba tùy chọn cốt lõi: --input chỉ thư mục chứa file cần đóng gói, --main-jar chọn JAR chính và --main-class xác định lớp có phương thức main. Từ các đầu vào này, jpackage tạo application image hoặc native installer cùng Java runtime.

Ứng dụng classpath thường gồm một executable JAR và các JAR dependency. jpackage không biên dịch source code hay tải dependency; bạn cần build ứng dụng và chuẩn bị các file trước. Khi đóng gói, mọi file trong input được đưa vào application payload. Các JAR trong input tạo thành classpath mặc định của launcher.

Bài học thuộc chương jpackage cơ bản của module JAVA_VERSION_JAVA16. jpackage là công cụ chính thức từ Java 16 và các nguyên tắc dưới đây vẫn áp dụng trên JDK hiện đại. Trọng tâm là ứng dụng non-modular dùng classpath; ứng dụng modular có quy trình riêng qua --module-path và --module.

## 1. Ứng dụng classpath là gì?

Ứng dụng classpath chạy các lớp Java từ classpath thay vì khởi chạy một module có tên. Một ứng dụng đơn giản có thể được đóng gói trong JAR:

```java
package com.example.catalog;

public class Main {
    public static void main(String[] args) {
        System.out.println("Catalog application started");
        for (String arg : args) {
            System.out.println("Argument: " + arg);
        }
    }
}
```

Sau khi biên dịch, class và resource được đóng gói vào catalog.jar. Nếu ứng dụng dùng thư viện ngoài JDK, các JAR runtime dependency cũng phải sẵn sàng để launcher nạp.

## 2. Vai trò của --input

--input nhận đường dẫn tới thư mục chứa các file sẽ được đóng gói. Đường dẫn có thể tuyệt đối hoặc tương đối với thư mục làm việc hiện tại của lệnh:

```powershell
jpackage --type app-image --name Catalog --input build\jpackage-input --main-jar catalog.jar
```

Các quy tắc cần nhớ:

- Tất cả file trong thư mục input được đưa vào application image.
- --main-jar được tính theo đường dẫn tương đối từ thư mục input.
- JAR dependency trong input được đưa vào classpath mặc định của launcher.
- File resource ngoài JAR cũng được đóng gói, nhưng ứng dụng phải tự định vị và đọc chúng.
- jpackage không tự giải quyết dependency từ Maven hoặc Gradle.

Nên dùng một thư mục staging riêng chỉ chứa file cần ở runtime. Không trỏ --input vào toàn bộ repository hoặc thư mục build tổng hợp có source, test report, log, file tạm và secret.

## 3. Vai trò của --main-jar

--main-jar xác định JAR chính của ứng dụng. Giá trị là tên file hoặc đường dẫn tương đối từ thư mục --input tới JAR chứa lớp main.

Ví dụ, với:

```text
build/
  jpackage-input/
    catalog.jar
    jackson-core.jar
    jackson-databind.jar
```

giá trị phù hợp là:

```powershell
jpackage --input build\jpackage-input --main-jar catalog.jar
```

Nếu JAR chính nằm trong thư mục con, có thể chỉ rõ đường dẫn tương đối:

```powershell
jpackage --input build\jpackage-input --main-jar app\catalog.jar
```

Tuy nhiên, các JAR dependency phải được đưa vào classpath đúng cách. Cấu trúc đơn giản, dễ kiểm tra nhất là đặt JAR chính và các JAR dependency ở thư mục input, rồi để jpackage tạo classpath mặc định.

--main-jar chỉ chọn JAR chứa điểm vào; nó không có nghĩa là các JAR dependency khác được tự tải xuống. Hãy đưa dependency runtime vào input trước khi chạy lệnh.

## 4. Vai trò của --main-class

--main-class là tên đầy đủ (fully qualified name) của lớp chứa phương thức:

```java
public static void main(String[] args)
```

Ví dụ:

```powershell
jpackage --input build\jpackage-input --main-jar catalog.jar --main-class com.example.catalog.Main
```

Tùy chọn này chỉ được dùng khi đã chỉ định --main-jar. Nếu manifest của JAR chính có thuộc tính Main-Class hợp lệ, bạn có thể bỏ qua --main-class:

```text
Manifest-Version: 1.0
Main-Class: com.example.catalog.Main
```

Nếu manifest không khai báo Main-Class, hãy truyền --main-class khi đóng gói. Nếu tên lớp sai hoặc lớp không có phương thức main phù hợp, launcher được tạo có thể không khởi động được ứng dụng.

Để kiểm tra manifest của JAR, có thể liệt kê nội dung archive:

```powershell
jar --list --file build\jpackage-input\catalog.jar
```

Sau đó mở META-INF/MANIFEST.MF từ JAR để kiểm tra Main-Class. jar --describe-module hữu ích để xem metadata module, nhưng không phải lệnh kiểm tra thuộc tính main class trong manifest của executable JAR.

## 5. Classpath mặc định của launcher

Theo mặc định, jpackage tạo classpath chứa đường dẫn tới từng JAR được cung cấp trong thư mục --input. Các JAR chính và dependency trong input có thể được nạp mà không cần tự viết -cp. File khác như properties hoặc template vẫn được đóng gói, nhưng không tự động trở thành classpath.

Nếu resource đã nằm bên trong JAR, có thể đọc qua API resource:

```java
try (var input = Main.class.getResourceAsStream("/config/defaults.properties")) {
    if (input == null) {
        throw new IllegalStateException("Missing default configuration");
    }
    // Đọc properties từ input stream.
}
```

Nếu resource nằm ngoài JAR, ứng dụng cần dùng đường dẫn file phù hợp. Token $APPDIR của launcher có thể dùng để tham chiếu thư mục chứa application payload; khi truyền token qua shell, phải giữ nguyên ký tự $ để launcher mở rộng token lúc chạy.

## 6. Đóng gói application image tối thiểu

Giả sử thư mục staging đã có catalog.jar và dependency runtime. Trên Windows PowerShell:

```powershell
jpackage --type app-image --name Catalog --input build\jpackage-input --main-jar catalog.jar --main-class com.example.catalog.Main --dest build\packages
```

Giải thích:

| Tùy chọn | Ý nghĩa |
| --- | --- |
| --type app-image | Tạo application image để kiểm thử launcher và runtime |
| --name Catalog | Tên ứng dụng và launcher |
| --input build\jpackage-input | Thư mục chứa JAR và resource |
| --main-jar catalog.jar | JAR chính, đường dẫn tương đối từ input |
| --main-class com.example.catalog.Main | Lớp main của ứng dụng |
| --dest build\packages | Thư mục nhận application image |

Nếu JAR đã có Main-Class trong manifest, lệnh có thể rút gọn bằng cách bỏ --main-class:

```powershell
jpackage --type app-image --name Catalog --input build\jpackage-input --main-jar catalog.jar --dest build\packages
```

Application image tạo ra có launcher và runtime riêng. Hãy chạy launcher của image để kiểm thử thay vì chỉ chạy java -jar catalog.jar trên máy build.

## 7. Build JAR trước khi đóng gói

jpackage cần JAR đã được build. Với ví dụ nhỏ không có dependency ngoài JDK, có thể dùng javac và jar:

```powershell
New-Item -ItemType Directory -Force build\classes, build\jpackage-input | Out-Null
javac -d build\classes src\com\example\catalog\Main.java
jar --create --file build\jpackage-input\catalog.jar --main-class com.example.catalog.Main -C build\classes .
```

Lệnh jar --main-class ghi thuộc tính main class vào manifest. Khi đó jpackage có thể suy ra điểm vào từ JAR và không cần lặp lại --main-class:

```powershell
jpackage --type app-image --name Catalog --input build\jpackage-input --main-jar catalog.jar --dest build\packages
```

Với dự án Maven hoặc Gradle, hãy chạy build task tương ứng và chuẩn bị một staging directory chỉ chứa JAR chính, runtime dependency và resource. jpackage không thay thế bước compile, test hay dependency resolution.

## 8. Thêm dependency vào input

Ví dụ ứng dụng dùng các thư viện bên ngoài:

```text
build\jpackage-input\
  catalog.jar
  jackson-core.jar
  jackson-databind.jar
  slf4j-api.jar
```

Đóng gói bằng cùng một lệnh:

```powershell
jpackage --type app-image --name Catalog --input build\jpackage-input --main-jar catalog.jar --main-class com.example.catalog.Main --dest build\packages
```

Classpath mặc định bao gồm các JAR từ input. Chỉ đưa dependency cần khi chạy; không đưa JUnit, test fixture, source JAR, Javadoc JAR hoặc plugin build vào package.

Không để nhiều phiên bản của cùng thư viện trong input. Nếu cả jackson-databind-2.15.jar và jackson-databind-2.17.jar cùng có mặt, cùng một class có thể xuất hiện ở nhiều vị trí và gây lỗi nạp class khó đoán. Hãy dùng dependency graph đã được Maven/Gradle giải quyết để chọn một phiên bản.

## 9. Khi nào cần tự cấu hình classpath?

Phần lớn ứng dụng classpath đơn giản có thể dùng classpath mặc định do jpackage tạo. Chỉ tự cấu hình khi ứng dụng cần thêm thư mục class, JAR ở vị trí riêng hoặc một cấu trúc classpath cụ thể.

Có thể truyền -cp, -classpath hoặc -Djava.class.path qua --java-options. Khi làm vậy, classpath do bạn chỉ định **ghi đè classpath mặc định** của jpackage. Bạn phải đưa lại tất cả JAR cần thiết vào classpath mới.

Ví dụ trên Windows, muốn nạp JAR chính và các lớp rời trong thư mục classes:

```powershell
jpackage --type app-image --name Catalog --input build\jpackage-input --main-jar catalog.jar --main-class com.example.catalog.Main --java-options '-cp $APPDIR\catalog.jar;$APPDIR\classes' --dest build\packages
```

Trong ví dụ:

- $APPDIR được launcher mở rộng thành thư mục application payload khi chạy.
- Dấu chấm phẩy là dấu phân cách classpath trên Windows.
- PowerShell dùng dấu nháy đơn để giữ nguyên $APPDIR khi truyền cho jpackage.
- Vì classpath mặc định đã bị ghi đè, phải liệt kê cả JAR chính và các thư mục/JAR cần thiết khác.

Trên Linux và macOS, dấu phân cách classpath là dấu hai chấm. Cần điều chỉnh đường dẫn và cách escape token theo shell tương ứng. Không sao chép nguyên ví dụ Windows sang Unix.

## 10. Phân biệt --java-options và --arguments

Hai tùy chọn này phục vụ hai lớp khác nhau:

| Tùy chọn | Dữ liệu được truyền tới | Ví dụ |
| --- | --- | --- |
| --java-options | JVM | -Xms128m, -Xmx512m, -Dapp.mode=desktop |
| --arguments | Phương thức main(String[] args) của ứng dụng | --mode offline, config defaults.properties |

Ví dụ:

```powershell
jpackage --type app-image --name Catalog --input build\jpackage-input --main-jar catalog.jar --main-class com.example.catalog.Main --java-options "-Xms128m" --java-options "-Xmx512m" --arguments "--mode offline" --dest build\packages
```

--arguments đặt đối số mặc định cho ứng dụng khi người dùng mở launcher mà không truyền đối số riêng. Người dùng có thể truyền đối số lúc chạy để thay thế các giá trị mặc định. --java-options cấu hình JVM được launcher sử dụng.

Không dùng --arguments để truyền -Xmx hoặc -D... cho JVM; đó là các tùy chọn dành cho --java-options.

## 11. Tạo native installer sau khi kiểm thử image

Sau khi application image chạy đúng, có thể tạo installer trên hệ điều hành đích. Ví dụ tạo MSI trên Windows:

```powershell
jpackage --type msi --name Catalog --app-image build\packages\Catalog --dest build\installers --app-version 1.0.0
```

Quy trình hai bước giúp kiểm tra launcher và runtime trước khi tạo installer. Nếu muốn tạo installer trực tiếp từ JAR, có thể dùng --type msi cùng --input, --main-jar và --main-class trong một lệnh. Installer native phải được tạo trên đúng nền tảng đích.

## 12. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể gặp | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy main JAR | --main-jar sai tên hoặc đường dẫn không tương đối với input | Kiểm tra file trong input và sửa đường dẫn |
| Launcher không tìm thấy main class | Manifest thiếu Main-Class và không truyền --main-class, hoặc tên lớp sai | Kiểm tra manifest và fully qualified class name |
| ClassNotFoundException | Thiếu dependency JAR hoặc classpath bị ghi đè | Bổ sung JAR runtime và kiểm tra --java-options |
| NoClassDefFoundError | Dependency có khi test nhưng không có trong input | Thu thập runtime dependency vào staging |
| Không đọc được properties/template | File được đóng gói nhưng ứng dụng tìm trong classpath hoặc working directory sai | Đặt resource trong JAR hoặc dùng đường dẫn $APPDIR rõ ràng |
| Lỗi sau khi tự đặt -cp | Classpath tùy chỉnh bỏ sót JAR mặc định | Liệt kê lại tất cả JAR và thư mục cần thiết |
| Chạy được bằng java -jar nhưng launcher lỗi | Runtime, classpath hoặc JVM options của application image khác môi trường phát triển | Chạy launcher image và kiểm tra dependency thực tế |

## 13. Phân biệt ứng dụng classpath và modular

--main-jar và --main-class dành cho ứng dụng non-modular chạy trên classpath. Với ứng dụng modular, chỉ định module path và module chính:

```powershell
jpackage --type app-image --name ModularCatalog --module-path build\mods --module com.example.catalog/com.example.catalog.Main --dest build\packages
```

Không truyền đồng thời --main-jar và --module. Hãy chọn một mô hình khởi chạy đúng với cách ứng dụng đã được build. Việc có một file JAR không tự động làm ứng dụng trở thành modular; modular JAR cần có module-info.class và được xử lý trên module path.

## 14. Bài tập tự kiểm tra

Cho thư mục:

```text
release-input/
  orders.jar
  postgresql.jar
  slf4j-api.jar
  config/
    app.properties
```

JAR orders.jar có lớp main com.example.orders.Main và manifest chưa khai báo Main-Class.

Hãy trả lời:

1. Giá trị --input cần chỉ tới đâu?
2. Giá trị --main-jar là gì?
3. Giá trị --main-class là gì?
4. Hai JAR dependency nào được đưa vào classpath mặc định?
5. File config/app.properties có tự động trở thành classpath không?
6. Nếu truyền --java-options "-cp $APPDIR/orders.jar" thì chuyện gì xảy ra với classpath mặc định?

**Đáp án:**

1. release-input.
2. orders.jar, vì nó nằm trực tiếp trong input directory.
3. com.example.orders.Main.
4. postgresql.jar và slf4j-api.jar; JAR chính cũng nằm trong classpath mặc định.
5. Không. File được đóng gói vào payload nhưng ứng dụng cần đọc qua đường dẫn file hoặc đặt resource bên trong JAR.
6. Classpath mặc định bị thay thế. Phải liệt kê cả orders.jar và mọi JAR dependency cần thiết trong classpath mới.

## Ghi nhớ

**Đóng gói ứng dụng classpath bằng jpackage bắt đầu từ một thư mục input đã chuẩn bị: --input chọn thư mục, --main-jar chọn JAR chứa ứng dụng và --main-class chỉ rõ lớp main khi manifest chưa khai báo.** Classpath mặc định gồm các JAR được đưa vào input; file resource khác vẫn được đóng gói nhưng không tự động trở thành classpath. Nếu truyền -cp/-classpath qua --java-options, bạn thay thế classpath mặc định và phải liệt kê lại mọi JAR cần thiết. Hãy tạo app-image, chạy launcher thực tế rồi mới tạo installer.

## Tài liệu tham khảo

- [Oracle Java SE 26 — The jpackage Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html)
- [Oracle Java SE 26 — Packaging Tool User's Guide: Basic Packaging](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-tool-user-guide.pdf)
- [Oracle Java SE 26 — Set Class and Module Paths](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-tool-user-guide.pdf)
- [Oracle Java SE 16 — The jpackage Command](https://docs.oracle.com/en/java/javase/16/docs/specs/man/jpackage.html)
- [JEP 392 — Packaging Tool](https://openjdk.org/jeps/392)
