# Kiểm thử launch argument, tài nguyên và thư viện phụ thuộc trong image

Application image chỉ thực sự sẵn sàng khi launcher truyền đúng đối số, ứng dụng đọc được tài nguyên và tất cả thư viện cần lúc chạy đều được nạp từ image. Lệnh jpackage tạo thành công chưa chứng minh các điều kiện này. Cần kiểm thử launcher thực tế, bao gồm cả trường hợp người dùng truyền đối số, trường hợp dùng đối số mặc định, resource nằm trong JAR, file bên ngoài JAR và dependency được nạp động.

jpackage có ba nhóm cấu hình cần phân biệt: --arguments đặt đối số mặc định cho ứng dụng, --java-options đặt tùy chọn cho JVM, còn --input và --app-content đưa file vào application payload. JAR trong --input còn được đưa vào classpath mặc định của launcher; file resource thông thường trong payload không tự động trở thành classpath.

Bài học thuộc chương **jpackage cơ bản** của module **JAVA_VERSION_JAVA16**. Các tùy chọn và cách kiểm thử dưới đây dựa trên tài liệu Oracle Java SE 26 và vẫn áp dụng cho JDK hiện đại. Trọng tâm là kiểm tra hành vi của image đã tạo, không phụ thuộc vào JDK cài trên máy build.

## 1. Những gì cần kiểm thử trong application image

Kiểm thử nên bao phủ bốn nhóm:

| Nhóm | Điều cần xác nhận |
| --- | --- |
| Launch arguments | Đối số mặc định, đối số người dùng truyền, chuỗi có dấu cách và thứ tự đối số |
| JVM options | System property, heap và các tùy chọn JVM được áp dụng đúng |
| Tài nguyên | Resource trong JAR đọc được; file ngoài JAR có đường dẫn đúng |
| Dependency | JAR runtime, service provider và native library có thể nạp trên máy đích |

Nên chạy launcher từ application image. Khi gọi java -jar bằng JDK trên máy phát triển, bạn đang kiểm tra một runtime và classpath khác với môi trường mà người dùng sẽ nhận.

## 2. Phân biệt --arguments và --java-options

Hai tùy chọn này đưa dữ liệu tới hai nơi khác nhau:

| Tùy chọn | Được truyền tới | Ví dụ |
| --- | --- | --- |
| --arguments | main(String[] args) của ứng dụng | --profile production, --config $APPDIR/config/app.properties |
| --java-options | JVM khởi chạy ứng dụng | -Xmx512m, -Dapp.mode=desktop, -Dapp.config=... |

Ví dụ:

~~~powershell
jpackage --type app-image --name Orders --input build\input --main-jar orders.jar --main-class com.example.orders.Main --arguments "--profile production" --java-options "-Xmx512m" --java-options "-Dapp.mode=desktop" --dest build\image
~~~

Trong lệnh trên:

- Ứng dụng nhận --profile và production trong mảng args.
- JVM nhận -Xmx512m.
- Ứng dụng đọc system property app.mode bằng System.getProperty("app.mode").

Không truyền -Xmx, -D... hoặc -XX:... qua --arguments; đó là tham số dành cho JVM. Ngược lại, không đưa tham số nghiệp vụ như --profile vào --java-options.

## 3. Đối số mặc định chỉ dùng khi người dùng không truyền đối số

--arguments đặt các đối số launcher mặc định. Nếu người dùng mở launcher mà không truyền đối số dòng lệnh, launcher chuyển các giá trị mặc định đó cho main class. Nếu người dùng đã truyền đối số khi mở launcher, các đối số dòng lệnh được dùng thay cho nhóm mặc định.

Ví dụ image được tạo với:

~~~powershell
jpackage --type app-image --name Orders --input build\input --main-jar orders.jar --main-class com.example.orders.Main --arguments "--profile production" --dest build\image
~~~

Hai lần chạy sau có kết quả khác nhau:

~~~powershell
# Không truyền đối số: ứng dụng nhận --profile production
& "build\image\Orders\Orders.exe"

# Có đối số riêng: ứng dụng nhận --profile staging
& "build\image\Orders\Orders.exe" --profile staging
~~~

Không nên giả định launcher sẽ nối --profile staging vào sau --profile production. Khi có đối số lúc chạy, nhóm mặc định được cấu hình bằng --arguments không được truyền vào. Hãy kiểm thử cả hai trường hợp để tránh bỏ sót cấu hình mặc định.

## 4. Kiểm tra đối số có dấu cách và nhiều giá trị

Giá trị --arguments có thể chứa nhiều đối số và có thể được dùng nhiều lần. Khi một đối số chứa dấu cách, cần đặt dấu nháy để launcher giữ nó thành một phần tử duy nhất.

Ví dụ:

~~~powershell
jpackage --type app-image --name Orders --input build\input --main-jar orders.jar --main-class com.example.orders.Main --arguments '--report "monthly summary.csv"' --dest build\image
~~~

Ứng dụng mong đợi ba phần tử:

~~~text
args[0] = --report
args[1] = monthly summary.csv
~~~

Hãy ghi lại đối số theo cách không làm lộ thông tin nhạy cảm. Không đưa password, access token, private key hoặc thông tin đăng nhập vào đối số mặc định vì người dùng có thể quan sát command line và cấu hình launcher.

## 5. Dùng APPDIR để truyền đường dẫn tài nguyên

Đối số hoặc JVM option có thể chứa token được launcher mở rộng lúc chạy:

| Token | Ý nghĩa sử dụng |
| --- | --- |
| $APPDIR | Thư mục chứa payload ứng dụng |
| $BINDIR | Thư mục chứa launcher |
| $ROOTDIR | Thư mục gốc của application image |

Các token này được launcher tính toán. Có thể dùng cú pháp $APPDIR/... hoặc `${APPDIR}`/... . Token phân biệt hoa thường trên Unix; trên Windows, việc mở rộng không phân biệt hoa thường. Nếu biến môi trường được tham chiếu không tồn tại, chuỗi đó không được mở rộng. Có thể thêm dấu gạch chéo ngược trước $ để ngăn mở rộng.

Ví dụ truyền đường dẫn file cấu hình ngoài JAR qua JVM property:

~~~powershell
jpackage --type app-image --name Orders --input build\input --main-jar orders.jar --main-class com.example.orders.Main --java-options '-Dapp.config=$APPDIR/config/app.properties' --dest build\image
~~~

PowerShell dùng dấu nháy đơn để giữ nguyên $APPDIR lúc tạo image. Với shell Unix, cũng cần escape hoặc quote $ để shell không mở rộng biến trước khi jpackage nhận giá trị. Token sẽ được launcher mở rộng khi chạy ứng dụng.

## 6. Resource bên trong JAR và file bên ngoài JAR

Hai loại tài nguyên cần được đọc theo hai cách khác nhau:

| Vị trí | Cách truy cập thường dùng |
| --- | --- |
| Resource đóng gói bên trong JAR | Class.getResourceAsStream() hoặc ClassLoader.getResourceAsStream() |
| File được đóng gói bên ngoài JAR | Path/Files với đường dẫn được xác định, ví dụ từ $APPDIR |

Resource trong JAR:

~~~java
try (var input = Main.class.getResourceAsStream("/defaults.properties")) {
    if (input == null) {
        throw new IllegalStateException("Missing defaults.properties");
    }

    var properties = new java.util.Properties();
    properties.load(input);
}
~~~

File cấu hình bên ngoài JAR:

~~~java
String configLocation = System.getProperty("app.config");
if (configLocation == null || configLocation.isBlank()) {
    throw new IllegalStateException("Missing app.config system property");
}

Path configPath = Path.of(configLocation);
if (!Files.isRegularFile(configPath)) {
    throw new IOException("Configuration file not found: " + configPath);
}

String configText = Files.readString(configPath);
~~~

Không dùng working directory làm gốc ngầm định cho file cấu hình. Launcher có thể được mở từ shortcut, menu hoặc terminal đang đứng ở một thư mục khác. Dùng resource API cho nội dung bất biến trong JAR và đường dẫn rõ ràng cho file ngoài JAR.

## 7. Đưa file ngoài JAR vào payload bằng --app-content

Với ứng dụng classpath, --input đưa toàn bộ file trong thư mục đầu vào vào application image. Nếu tài nguyên nằm ngoài thư mục input hoặc cần thêm một thư mục khác, có thể dùng --app-content.

Ví dụ cấu trúc:

~~~text
build/
  input/
    orders.jar
    jackson-core.jar
    jackson-databind.jar
    config/
      app.properties
  deploy/
    templates/
      invoice.html
~~~

Tạo image:

~~~powershell
jpackage --type app-image --name Orders --input build\input --main-jar orders.jar --main-class com.example.orders.Main --app-content build\deploy\templates --java-options '-Dapp.config=$APPDIR/config/app.properties' --dest build\image
~~~

--app-content nhận danh sách đường dẫn file hoặc thư mục, phân cách bằng dấu phẩy và có thể dùng nhiều lần. Hãy kiểm tra cấu trúc payload thực tế sau khi đóng gói để xác nhận file được đặt đúng nơi mà ứng dụng mong đợi.

Lưu ý riêng trên macOS: giá trị --app-content nên là một thư mục có thư mục con Resources, hoặc một thư mục hợp lệ khác trong Contents của application bundle. Cấu trúc không hợp lệ có thể làm bundle không hợp lệ và ảnh hưởng code signing hoặc notarization.

--app-content chỉ thêm file vào payload. Nó không tự động biến một JAR được thêm theo cách này thành classpath mặc định.

## 8. Kiểm thử dependency JAR trong classpath mặc định

Với ứng dụng non-modular, classpath mặc định do jpackage tạo chứa đường dẫn tới từng JAR trong thư mục --input. Vì vậy, staging directory cần có JAR chính và tất cả JAR runtime dependency:

~~~text
input/
  orders.jar
  postgresql.jar
  jackson-core.jar
  jackson-databind.jar
  slf4j-api.jar
~~~

Kiểm thử:

1. Xác nhận từng dependency runtime có mặt trong input.
2. Loại source JAR, Javadoc JAR, test JAR và thư viện chỉ dùng khi build.
3. Kiểm tra không có nhiều phiên bản của cùng thư viện.
4. Chạy launcher và gọi các chức năng thực sự sử dụng dependency.
5. Thử trên máy sạch để phát hiện dependency tình cờ có sẵn trên máy build.

Không đưa -cp hoặc -classpath vào --java-options nếu không cần. Classpath tự chỉ định qua --java-options sẽ ghi đè classpath mặc định của launcher. Nếu phải tự cấu hình classpath, hãy liệt kê lại JAR chính và tất cả JAR dependency. Dấu phân cách classpath là dấu chấm phẩy trên Windows và dấu hai chấm trên Linux/macOS.

## 9. Kiểm tra dependency được nạp động

Một số dependency không được sử dụng bằng lệnh new trực tiếp mà được nạp thông qua service provider, JDBC, reflection hoặc tên class trong cấu hình. Vì vậy, kiểm tra compile thành công chưa đủ.

Ví dụ kiểm tra JDBC driver đã được đưa vào image và được phát hiện qua cơ chế service provider:

~~~java
Driver driver = DriverManager.getDriver(
        "jdbc:postgresql://localhost:5432/orders");
System.out.println("JDBC driver: " + driver.getClass().getName());
~~~

Lệnh này xác nhận driver được đăng ký và nhận diện URL; nó chưa kiểm tra kết nối database. Hãy thực hiện thêm smoke test kết nối với database test trong môi trường phù hợp.

Với ứng dụng modular dùng ServiceLoader, kiểm tra khai báo uses/provides và runtime image. Từ JDK 25, jpackage không còn tự động đưa service bindings vào runtime image như các bản trước. Nếu ứng dụng cần service binding, cân nhắc --bind-services qua --jlink-options và kiểm tra provider trong image thực tế.

## 10. Kiểm tra native library và thành phần hệ thống

JAR dependency không bao gồm mọi thành phần mà ứng dụng cần. Nếu thư viện sử dụng JNI hoặc native access, kiểm tra:

- File native đúng nền tảng: .dll, .so hoặc .dylib.
- Kiến trúc CPU và ABI tương thích.
- Thư viện hệ thống mà native binary liên kết đã có trên máy đích.
- Đường dẫn nạp native library không phụ thuộc máy build.
- Chức năng có dùng native library chạy được trong application image.

Application image được tạo cho từng nền tảng đích. Không sao chép nguyên image Windows sang Linux hoặc macOS rồi kỳ vọng launcher và native dependency hoạt động.

## 11. Tạo launcher phụ với bộ arguments riêng

Nếu cùng một ứng dụng có nhiều chế độ chạy, --add-launcher tạo thêm launcher từ file properties. Mỗi launcher có thể dùng arguments hoặc JVM options riêng trong khi dùng chung payload ứng dụng.

Ví dụ file admin.properties:

~~~properties
arguments=--profile admin
java-options=-Xmx768m
~~~

Tạo launcher bổ sung:

~~~powershell
jpackage --type app-image --name Orders --input build\input --main-jar orders.jar --main-class com.example.orders.Main --add-launcher Admin=admin.properties --dest build\image
~~~

Kiểm thử cả launcher chính lẫn launcher Admin: xác nhận mỗi launcher truyền đúng đối số mặc định, JVM options và cùng tìm thấy resource/dependency cần thiết. Đối số dòng lệnh do người dùng truyền vẫn cần được kiểm tra riêng theo quy tắc fallback của --arguments.

## 12. Ma trận kiểm thử trước khi phát hành

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Mở launcher không truyền đối số | Ứng dụng nhận đúng --arguments mặc định |
| Mở launcher với đối số riêng | Ứng dụng nhận đúng nhóm đối số người dùng truyền |
| Đối số chứa dấu cách | Một giá trị được giữ nguyên thành một phần tử trong args |
| Đọc resource trong JAR | Resource được tìm thấy qua API resource |
| Đọc file ngoài JAR | File được tìm thấy qua đường dẫn dựa trên application directory |
| Gọi code dùng dependency JAR | Không có ClassNotFoundException hoặc NoClassDefFoundError |
| Nạp JDBC/service provider | Provider được phát hiện và smoke test thành công |
| Dùng native library | Library nạp được trên OS/CPU đích |
| Chạy trên máy sạch | Không phụ thuộc JDK hoặc thư viện tình cờ có trên máy build |
| Chạy launcher phụ | Arguments và JVM options đúng với properties riêng |

## 13. Khoanh vùng lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể gặp | Cách kiểm tra và xử lý |
| --- | --- | --- |
| Ứng dụng không nhận arguments mặc định | Người dùng đã truyền đối số khi mở launcher | Kiểm tra quy tắc fallback; ghi log args trong môi trường test |
| Một chuỗi có dấu cách bị tách thành nhiều phần tử | Thiếu quoting trong --arguments hoặc properties | Đặt quote cho đúng giá trị và kiểm tra mảng args |
| System property bị thiếu | JVM option đặt nhầm trong --arguments | Chuyển sang --java-options và đọc bằng System.getProperty() |
| Không tìm thấy file cấu hình | Đường dẫn dựa trên working directory | Dùng $APPDIR và xác nhận file có trong payload |
| ClassNotFoundException | Thiếu dependency hoặc classpath bị ghi đè | Bổ sung JAR vào --input hoặc khai báo lại đầy đủ classpath |
| NoClassDefFoundError | Dependency chỉ có trong môi trường build/test | Chạy chức năng thực tế trên image và máy sạch |
| Không tìm thấy JDBC/service provider | Provider hoặc service binding không có trong runtime | Kiểm tra dependency và module/service configuration |
| Native library không nạp | Sai OS/CPU, thiếu ABI hoặc thư viện hệ thống | Tạo image đúng target và kiểm tra native dependencies |
| Image macOS lỗi signing/notarization | Nội dung --app-content đặt sai cấu trúc bundle | Đặt tài nguyên vào thư mục hợp lệ trong Contents, ví dụ Resources |

## 14. Bài tập tự kiểm tra

Ứng dụng Orders được đóng gói với:

~~~text
input/
  orders.jar
  postgresql.jar
  jackson-databind.jar
  config/
    app.properties
deploy/
  templates/
~~~

Lệnh tạo image có --arguments "--profile production", --java-options "-Dapp.config=$APPDIR/config/app.properties" và --app-content deploy\templates. File app.properties nằm trong input/config; thư mục templates được thêm bằng --app-content.

Hãy trả lời:

1. Khi mở launcher không truyền đối số, main class nhận những giá trị nào?
2. Khi người dùng mở launcher với --profile staging, đối số mặc định có còn được truyền không?
3. app.config được đọc từ args hay system property?
4. app.properties có tự động trở thành classpath không?
5. postgresql.jar và jackson-databind.jar có vai trò gì trong classpath mặc định?
6. Nếu thêm -cp qua --java-options, cần làm gì với classpath mặc định?

**Đáp án:**

1. args nhận --profile và production.
2. Không. Đối số người dùng truyền được dùng thay cho nhóm đối số mặc định.
3. Đây là system property; ứng dụng đọc bằng System.getProperty("app.config").
4. Không. File được đưa vào payload bằng --app-content; ứng dụng đọc nó qua đường dẫn file.
5. Đây là JAR dependency nằm trong --input, được đưa vào classpath mặc định.
6. Phải liệt kê lại orders.jar, postgresql.jar, jackson-databind.jar và mọi JAR cần thiết trong classpath tùy chỉnh.

## Ghi nhớ

**Kiểm thử launch argument, tài nguyên và dependency phải thực hiện trên launcher của application image.** --arguments chỉ cung cấp đối số mặc định khi người dùng không truyền đối số lúc chạy; --java-options cấu hình JVM. Resource trong JAR được đọc bằng API resource, file ngoài JAR được đóng gói bằng --input hoặc --app-content và truy cập qua đường dẫn rõ ràng như $APPDIR. JAR runtime dependency cần có trong --input để nằm trong classpath mặc định; nếu tự đặt classpath, phải liệt kê lại đầy đủ. Hãy thử các chức năng nạp dependency và resource trên máy sạch trước khi phát hành.

## Tài liệu tham khảo

- [Oracle Java SE 26 — The jpackage Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html)
- [Oracle Java SE 26 — Packaging Overview](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-overview.html)
- [Oracle Java SE 26 — Packaging Tool User's Guide: Set Class and Module Paths](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-tool-user-guide.pdf)
- [Oracle Java SE 26 — Packaging Tool User's Guide: Add Launchers](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-tool-user-guide.pdf)
- [JEP 392 — Packaging Tool](https://openjdk.org/jeps/392)
