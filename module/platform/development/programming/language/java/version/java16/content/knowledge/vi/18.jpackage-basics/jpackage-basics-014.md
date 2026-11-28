# Tạo launcher bổ sung bằng --add-launcher và tệp properties

## 1. Vì sao một ứng dụng cần nhiều launcher?

Một ứng dụng desktop hoặc công cụ nội bộ có thể có nhiều cách khởi chạy. Chẳng hạn cùng một chương trình có thể chạy ở chế độ người dùng, chế độ quản trị, chế độ chẩn đoán hoặc mở một giao diện dành riêng cho tác vụ cụ thể.

Nếu mỗi chế độ cần một lệnh khởi chạy khác nhau, người dùng phải nhớ tham số hoặc tự tạo script. `jpackage` hỗ trợ tạo thêm launcher trong cùng application image bằng tùy chọn `--add-launcher`.

Mỗi launcher bổ sung có thể có:

- Tên launcher riêng.
- Main class hoặc main module riêng nếu ứng dụng cần.
- Bộ tham số mặc định truyền vào ứng dụng.
- JVM options riêng.
- Phiên bản và icon riêng.
- Cấu hình console trên Windows.

Các launcher dùng chung application image và runtime được đóng gói. Nhờ đó, một bộ cài có thể cung cấp nhiều entry point mà không phải đóng gói nhiều bản runtime giống nhau.

`jpackage` trở thành công cụ production-ready trong JDK 16 qua JEP 392. Đây là công cụ đóng gói ứng dụng Java vẫn được duy trì trong các JDK hiện đại. Nội dung bài tập trung vào thuộc tính launcher còn được hỗ trợ, không dựa vào cú pháp thử nghiệm hoặc tùy chọn cũ.

Mục tiêu bài học:

- Hiểu vai trò của launcher chính và launcher bổ sung.
- Tạo tệp properties cho từng launcher.
- Dùng `--add-launcher` nhiều lần trong một lệnh đóng gói.
- Phân biệt application arguments với JVM options.
- Chọn main JAR hoặc main module cho launcher.
- Tạo launcher có cấu hình khác nhau nhưng dùng chung runtime.
- Kiểm tra application image và gỡ lỗi cấu hình launcher.

## 2. Launcher chính và launcher bổ sung

Khi chạy `jpackage`, các tùy chọn trên dòng lệnh xác định launcher chính của ứng dụng. Tùy chọn `--add-launcher` tạo thêm một launcher thay thế dựa trên cấu hình launcher chính.

Ví dụ, một ứng dụng có launcher chính:

~~~text
AcmeDesk
~~~

và hai launcher bổ sung:

~~~text
AcmeDesk
AcmeDesk-Admin
AcmeDesk-Diagnostics
~~~

Cả ba launcher nằm trong cùng application image. Launcher bổ sung có thể ghi đè một số thông tin của launcher chính, chẳng hạn default arguments hoặc JVM options.

Một launcher bổ sung không tự tạo một ứng dụng độc lập với runtime riêng. Nó là một cách khởi chạy khác của ứng dụng đã được đóng gói.

Cấu trúc lệnh:

~~~bash
jpackage [các tùy chọn ứng dụng chính] \
    --add-launcher TenLauncherA=launcher-a.properties \
    --add-launcher TenLauncherB=launcher-b.properties
~~~

Mỗi launcher cần một tệp properties riêng và một lần gọi `--add-launcher` riêng. Có thể lặp lại tùy chọn này để tạo nhiều launcher trong cùng lần đóng gói.

## 3. Cú pháp --add-launcher

Cú pháp:

~~~text
--add-launcher launcher-name=properties-file
~~~

Trong đó:

| Thành phần | Ý nghĩa |
| --- | --- |
| `launcher-name` | Tên launcher bổ sung sẽ được tạo. |
| `properties-file` | Đường dẫn tới tệp properties chứa cấu hình launcher. |

Đường dẫn tệp có thể là đường dẫn tuyệt đối hoặc tương đối với thư mục làm việc hiện tại khi chạy `jpackage`.

Ví dụ:

~~~bash
jpackage \
    --name AcmeDesk \
    --input input \
    --main-jar acme-desk.jar \
    --main-class com.acme.desktop.Main \
    --add-launcher Admin=launchers/admin.properties
~~~

Lệnh trên:

- Tạo ứng dụng có tên `AcmeDesk`.
- Dùng `acme-desk.jar` làm main JAR.
- Chạy class `com.acme.desktop.Main`.
- Tạo thêm launcher tên `Admin` theo cấu hình trong `launchers/admin.properties`.

Tên launcher có khoảng trắng nên được đặt trong dấu nháy kép ở dòng lệnh. Nên dùng tên đơn giản, dễ nhận biết và không trùng tên launcher khác.

## 4. Cấu trúc tệp properties

Tệp properties là danh sách cặp key-value, mỗi thuộc tính nằm trên một dòng:

~~~properties
arguments=--mode admin --read-only
java-options=-Xms256m -Xmx1g
app-version=2.1.0
~~~

Không cần khai báo section như INI. Tên key và dấu bằng phân tách tên thuộc tính với giá trị.

Các thuộc tính launcher phổ biến được hỗ trợ trong JDK hiện đại gồm:

| Key | Ý nghĩa |
| --- | --- |
| `module` | Module chứa main class; có thể ghi module name hoặc module name kèm main class. |
| `main-jar` | JAR chứa main class của launcher. |
| `main-class` | Tên đầy đủ của main class, dùng cùng main JAR. |
| `arguments` | Tham số mặc định truyền cho main class. |
| `java-options` | Tùy chọn truyền cho JVM khi launcher chạy. |
| `app-version` | Phiên bản ứng dụng hoặc launcher. |
| `icon` | Icon dùng cho launcher bổ sung. |
| `win-console` | Trên Windows, yêu cầu mở console cùng ứng dụng khi đặt thành `true`. |

Một tệp launcher phải đặt ít nhất một thuộc tính. Các giá trị được cung cấp trong tệp có thể bổ sung hoặc ghi đè những tùy chọn tương ứng từ lệnh tạo launcher chính.

Tập thuộc tính khả dụng có thể phụ thuộc phiên bản JDK và nền tảng. Khi xây dựng sản phẩm, kiểm tra `jpackage --help` và tài liệu của chính JDK dùng để đóng gói. Bài này chỉ sử dụng các thuộc tính launcher phổ biến còn được hỗ trợ.

## 5. Phân biệt arguments và java-options

Hai thuộc tính dễ nhầm nhất là `arguments` và `java-options`.

- `arguments` là tham số ứng dụng được truyền vào `main(String[] args)`.
- `java-options` là tùy chọn cấu hình JVM trước khi ứng dụng bắt đầu chạy.

Ví dụ:

~~~properties
arguments=--mode admin --config conf/admin.properties
java-options=-Xms256m -Xmx1g -Dapp.profile=admin
~~~

Trong ứng dụng Java:

~~~java
public class Main {
    public static void main(String[] args) {
        for (String arg : args) {
            System.out.println(arg);
        }

        System.out.println(
            System.getProperty("app.profile")
        );
    }
}
~~~

Các giá trị trong `arguments` xuất hiện trong mảng `args`. Thuộc tính `app.profile` được đọc qua `System.getProperty` vì nó được truyền bằng `-D` trong JVM options.

Không đặt tham số nghiệp vụ của ứng dụng vào `java-options`. Ngược lại, không đặt `-Xmx` hoặc `-D...` vào `arguments` rồi mong JVM xử lý chúng.

### Tham số mặc định

`arguments` xác định tham số mặc định cho launcher khi người dùng không truyền tham số ứng dụng trên dòng lệnh. Nếu người dùng khởi chạy với tham số riêng, launcher sử dụng tham số được cung cấp theo hợp đồng của launcher.

Điều này hữu ích khi mỗi launcher đại diện cho một chế độ mặc định, còn người dùng hoặc script vẫn có thể truyền tham số để điều khiển lần chạy cụ thể.

## 6. Tạo launcher cho chế độ quản trị

Giả sử ứng dụng `AcmeDesk` hỗ trợ chế độ người dùng và quản trị. Launcher chính chạy chế độ thông thường, launcher bổ sung chạy chế độ quản trị.

Tệp `launchers/admin.properties`:

~~~properties
arguments=--mode admin --config conf/admin.properties
java-options=-Xms256m -Xmx1g -Dapp.profile=admin
app-version=2.1.0
~~~

Lệnh đóng gói:

~~~bash
jpackage \
    --type app-image \
    --name AcmeDesk \
    --input input \
    --main-jar acme-desk.jar \
    --main-class com.acme.desktop.Main \
    --app-version 2.1.0 \
    --dest dist \
    --add-launcher Admin=launchers/admin.properties
~~~

Application image sẽ có launcher chính và launcher `Admin`. Launcher Admin truyền tham số chế độ quản trị và JVM options riêng.

Trong ứng dụng, có thể xử lý tham số:

~~~java
public class Main {
    public static void main(String[] args) {
        String mode = "user";

        for (int i = 0; i < args.length - 1; i++) {
            if ("--mode".equals(args[i])) {
                mode = args[i + 1];
            }
        }

        System.out.println("Starting in mode: " + mode);
    }
}
~~~

Ví dụ chỉ minh họa cách nhận biết chế độ. Ứng dụng thực tế vẫn phải kiểm tra quyền người dùng trước khi thực hiện chức năng quản trị. Tên launcher hoặc tham số `--mode admin` không phải cơ chế xác thực hay phân quyền bảo mật.
## 7. Tạo nhiều launcher trong một lần đóng gói

Có thể tạo nhiều launcher với cấu hình khác nhau.

Tệp `launchers/admin.properties`:

~~~properties
arguments=--mode admin
java-options=-Xms256m -Xmx1g -Dapp.profile=admin
~~~

Tệp `launchers/diagnostics.properties`:

~~~properties
arguments=--mode diagnostics --log-level debug
java-options=-Xms128m -Xmx768m -Dapp.profile=diagnostics
~~~

Tệp `launchers/import.properties`:

~~~properties
arguments=--mode import --batch-size 500
java-options=-Xms512m -Xmx2g -Dapp.profile=import
~~~

Lệnh:

~~~bash
jpackage \
    --type app-image \
    --name AcmeDesk \
    --input input \
    --main-jar acme-desk.jar \
    --main-class com.acme.desktop.Main \
    --dest dist \
    --add-launcher Admin=launchers/admin.properties \
    --add-launcher Diagnostics=launchers/diagnostics.properties \
    --add-launcher Import=launchers/import.properties
~~~

Kết quả có bốn entry point:

| Launcher | Default arguments | JVM profile |
| --- | --- | --- |
| AcmeDesk | Theo cấu hình launcher chính | Theo cấu hình launcher chính |
| AcmeDesk-Admin | `--mode admin` | `admin` |
| AcmeDesk-Diagnostics | `--mode diagnostics --log-level debug` | `diagnostics` |
| AcmeDesk-Import | `--mode import --batch-size 500` | `import` |

Mỗi launcher có tệp properties riêng, giúp cấu hình dễ đọc và dễ kiểm soát trong source control.

## 8. Cấu hình launcher theo module

`jpackage` hỗ trợ ứng dụng modular và non-modular. Với ứng dụng modular, launcher có thể dùng thuộc tính `module`.

Giả sử ứng dụng có module `com.acme.desktop` và main class `com.acme.desktop.Main`.

Tệp properties:

~~~properties
module=com.acme.desktop/com.acme.desktop.Main
arguments=--mode admin
java-options=-Xmx1g -Dapp.profile=admin
~~~

Lệnh đóng gói ứng dụng modular:

~~~bash
jpackage \
    --type app-image \
    --name AcmeDesk \
    --module-path mods \
    --module com.acme.desktop/com.acme.desktop.Main \
    --dest dist \
    --add-launcher Admin=launchers/admin.properties
~~~

Giá trị `module` có thể là tên module nếu main class đã được xác định trong module descriptor; nếu cần chỉ rõ main class, dùng dạng `module-name/main-class`.

Với ứng dụng non-modular, dùng `main-jar` và `main-class`:

~~~properties
main-jar=acme-desk.jar
main-class=com.acme.desktop.Main
arguments=--mode admin
~~~

Không cấu hình `module` cùng `main-jar` cho cùng một launcher. Chọn mô hình khởi chạy phù hợp với ứng dụng.

## 9. Dùng icon và Windows console cho launcher

Một launcher bổ sung có thể dùng icon riêng:

~~~properties
arguments=--mode admin
icon=icons/admin.ico
~~~

Icon giúp người dùng phân biệt các entry point trong môi trường desktop. Định dạng và kích thước icon cần phù hợp với nền tảng đóng gói.

Trên Windows, thuộc tính `win-console` điều khiển việc mở console cùng launcher:

~~~properties
arguments=--mode diagnostics
win-console=true
~~~

Điều này phù hợp với launcher chẩn đoán hoặc công cụ dòng lệnh cần hiển thị output. Với launcher desktop thông thường, có thể để cấu hình mặc định phù hợp với ứng dụng.

`win-console` là thuộc tính nền tảng Windows. Không giả định nó có cùng tác dụng trên Linux hoặc macOS.

## 10. Xử lý giá trị có khoảng trắng

Giá trị `arguments` có thể chứa nhiều tham số. Nếu một tham số có khoảng trắng, đặt riêng tham số đó trong dấu nháy kép.

Ví dụ:

~~~properties
arguments=--mode import --input "D:/Acme Data/Orders"
~~~

Theo cách này, đường dẫn có khoảng trắng được truyền như một đối số. Nếu bỏ dấu nháy, đường dẫn có thể bị tách thành nhiều đối số.

Tương tự, `java-options` có thể chứa nhiều JVM options:

~~~properties
java-options=-Xms256m -Xmx1g -Dapp.name=AcmeDesk
~~~

Nếu giá trị JVM option chứa khoảng trắng, cần tuân theo quy tắc quoting của properties launcher và shell/platform tương ứng. Nên thử trực tiếp launcher đã tạo và kiểm tra giá trị nhận được trong ứng dụng.

Không dùng cú pháp escape của shell để suy đoán cách parser properties xử lý. Tệp properties được đọc bởi `jpackage` và sau đó launcher diễn giải danh sách đối số theo quy tắc riêng của công cụ.

## 11. Launcher bổ sung ghi đè cấu hình nào?

Các tùy chọn trong tệp properties được dùng để bổ sung hoặc ghi đè những tùy chọn tương ứng trên dòng lệnh tạo launcher chính.

Ví dụ, launcher chính có:

~~~bash
jpackage \
    --name AcmeDesk \
    --input input \
    --main-jar acme-desk.jar \
    --main-class com.acme.desktop.Main \
    --arguments "--mode user" \
    --java-options "-Xmx512m"
~~~

Launcher bổ sung có:

~~~properties
arguments=--mode admin
java-options=-Xmx1g -Dapp.profile=admin
~~~

Khi chạy launcher Admin, cấu hình riêng của nó được áp dụng cho launcher đó. Launcher chính vẫn giữ cấu hình của nó.

Nên ghi rõ các thuộc tính cần thay đổi trong mỗi tệp. Đừng sao chép toàn bộ cấu hình chính vào tất cả tệp properties nếu launcher chỉ khác một vài giá trị; cấu hình dư thừa làm tăng nguy cơ các launcher lệch nhau khi ứng dụng được cập nhật.

## 12. Kiểm tra application image sau khi đóng gói

Nên tạo application image trước khi tạo installer để kiểm tra launcher.

Ví dụ:

~~~bash
jpackage \
    --type app-image \
    --name AcmeDesk \
    --input input \
    --main-jar acme-desk.jar \
    --main-class com.acme.desktop.Main \
    --dest dist \
    --add-launcher Admin=launchers/admin.properties \
    --add-launcher Diagnostics=launchers/diagnostics.properties
~~~

Sau khi tạo thành công:

1. Kiểm tra thư mục application image.
2. Xác nhận launcher chính tồn tại.
3. Xác nhận các launcher bổ sung có mặt.
4. Khởi chạy từng launcher.
5. Kiểm tra ứng dụng nhận đúng default arguments.
6. Kiểm tra JVM options thông qua system properties hoặc log chẩn đoán.
7. Kiểm tra icon và console trên nền tảng tương ứng.
8. Kiểm tra tài nguyên cấu hình mà launcher tham chiếu có được đóng gói đúng vị trí.

Application image chứa launcher, runtime và các file ứng dụng cần thiết. Cấu trúc thư mục cụ thể phụ thuộc hệ điều hành. Không giả định tên file thực thi hoặc vị trí file cấu hình là giống nhau trên mọi nền tảng.

Có thể xem file cấu hình launcher do `jpackage` tạo trong application image để xác minh các giá trị mặc định đã được ghi. Sau đó vẫn cần chạy launcher thực tế vì cấu hình đúng về mặt file chưa bảo đảm ứng dụng xử lý tham số đúng.

## 13. Tạo installer sau khi kiểm tra launcher

Khi application image đã được kiểm tra, có thể tạo installer cho nền tảng đích. Có thể yêu cầu `jpackage` tạo installer trực tiếp hoặc dùng application image có sẵn làm đầu vào.

Ví dụ tạo installer từ application image:

~~~bash
jpackage \
    --type msi \
    --name AcmeDesk \
    --app-image dist/AcmeDesk
~~~

`msi` là định dạng Windows. Linux và macOS có định dạng gói riêng. `jpackage` không hỗ trợ cross-platform packaging: gói native phải được tạo trên nền tảng đích tương ứng.

Vì vậy, quy trình phát hành đa nền tảng thường có một bước build/package riêng trên Windows, Linux và macOS. Các launcher bổ sung được tạo trong application image và đi cùng gói cài đặt của nền tảng đó.

## 14. Quản lý properties file trong dự án

Nên lưu các tệp properties cùng mã nguồn đóng gói, ví dụ:

~~~text
project/
├── input/
│   └── acme-desk.jar
├── launchers/
│   ├── admin.properties
│   ├── diagnostics.properties
│   └── import.properties
└── packaging/
    └── package-app.sh
~~~

Lợi ích:

- Cấu hình launcher được quản lý bằng version control.
- Có thể review thay đổi default arguments và JVM options.
- Có thể tạo lại application image một cách nhất quán.
- Mỗi launcher có một mục đích rõ ràng.
- Có thể kiểm tra khác biệt giữa các môi trường phát hành.

Không đặt mật khẩu, token hoặc secret trong `arguments` hay `java-options`. Những giá trị này có thể xuất hiện trong file cấu hình đóng gói, script hoặc thông tin process. Hãy lấy secret từ cơ chế quản lý bí mật phù hợp tại runtime.

## 15. Lỗi thường gặp và cách khắc phục

1. **Quên tạo properties file:** đường dẫn trong `--add-launcher` phải trỏ đến tệp thực tế.
2. **Dùng một properties file cho nhiều launcher với cấu hình khác nhau:** tạo một tệp riêng cho mỗi launcher để tránh nhầm lẫn.
3. **Nhầm `arguments` với `java-options`:** arguments vào `main(String[] args)`; java-options cấu hình JVM.
4. **Đặt main class không đi cùng main JAR:** `main-class` chỉ dùng cùng `main-jar`; với ứng dụng modular, dùng `module`.
5. **Khai báo cả `module` và `main-jar`:** chọn một mô hình khởi chạy cho mỗi launcher.
6. **Dùng sai tên module:** kiểm tra tên module thật và main class trong module descriptor.
7. **Quên quote tham số có khoảng trắng:** một đường dẫn có khoảng trắng có thể bị tách thành nhiều đối số.
8. **Ghi đè cấu hình launcher chính ngoài ý muốn:** chỉ đặt key cần thay đổi trong properties file.
9. **Tạo installer trước khi thử launcher:** tạo `app-image` và kiểm tra từng launcher trước khi phát hành.
10. **Đưa tùy chọn Windows vào kỳ vọng chung mọi nền tảng:** `win-console` chỉ dành cho Windows.
11. **Dùng một application image cho mọi hệ điều hành:** native package phải được tạo trên nền tảng đích.
12. **Đặt secret vào properties file:** không lưu thông tin xác thực trong cấu hình launcher.
13. **Cho rằng launcher admin tự cấp quyền quản trị:** quyền thực tế phải được kiểm tra ở tầng ứng dụng và hệ điều hành.
14. **Không kiểm tra sau khi nâng cấp JDK:** xác minh các key properties vẫn được hỗ trợ bằng tài liệu và `jpackage --help` của JDK đóng gói.

## 16. Bài tập thực hành

1. Tạo launcher chính chạy ứng dụng ở chế độ user.
2. Tạo `admin.properties` với default arguments `--mode admin`.
3. Tạo `diagnostics.properties` với `--mode diagnostics` và JVM option bật log.
4. Gọi `--add-launcher` hai lần trong cùng lệnh `jpackage`.
5. Chạy từng launcher và in ra `args` để xác nhận default arguments.
6. Dùng `java-options` đặt system property rồi đọc bằng `System.getProperty`.
7. Tạo launcher modular bằng thuộc tính `module`.
8. Tạo launcher non-modular bằng `main-jar` và `main-class`.
9. Thêm icon riêng cho launcher Admin và kiểm tra trên desktop tương ứng.
10. Tạo launcher Windows có console để quan sát log chẩn đoán.
11. Thử một argument chứa đường dẫn có khoảng trắng và kiểm tra mảng args.
12. Tạo application image, kiểm tra các launcher, rồi mới tạo installer.
13. Thiết kế ba launcher cho một ứng dụng quản lý dữ liệu: User, Import và Diagnostics; mô tả default arguments và JVM options của từng launcher.
14. Giải thích vì sao tên launcher hoặc tham số `--mode admin` không thay thế xác thực quyền người dùng.

## Ghi nhớ

`--add-launcher name=properties-file` tạo một launcher bổ sung trong application image của `jpackage`. Mỗi launcher cần một properties file riêng; các thuộc tính trong file có thể bổ sung hoặc ghi đè cấu hình tương ứng từ launcher chính. `arguments` truyền tham số mặc định vào ứng dụng khi launcher được chạy mà không có tham số riêng; `java-options` truyền tùy chọn cho JVM. Chọn `main-jar` cùng `main-class` cho ứng dụng non-modular hoặc `module` cho ứng dụng modular. Có thể tạo nhiều launcher trong một lần đóng gói và dùng chung runtime. Hãy tạo `app-image` trước để kiểm tra launcher, xác nhận tham số và JVM options, sau đó mới tạo installer trên nền tảng đích. Các launcher chỉ cung cấp entry point và cấu hình chạy; chúng không thay thế xác thực hoặc phân quyền của ứng dụng.

**Tài liệu tham khảo chính thức:**

- [JEP 392 – Packaging Tool](https://openjdk.org/jeps/392)
- [JDK 16 – The jpackage Command](https://docs.oracle.com/en/java/javase/16/docs/specs/man/jpackage.html)
- [JDK 16 – Packaging Tool User's Guide](https://docs.oracle.com/en/java/javase/16/jpackage/)
- [JDK 16 – Support Application Requirements](https://docs.oracle.com/en/java/javase/16/jpackage/support-application-features.html)
- [Current jpackage Command Reference](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html)
