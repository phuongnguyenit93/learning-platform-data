# Liệt kê module có thể quan sát bằng java --list-modules

## 1. Mục tiêu

Java Platform Module System (JPMS) chia runtime và ứng dụng thành các module có tên, descriptor và quan hệ phụ thuộc rõ ràng. Khi làm việc với một modular application, đôi khi cần biết JDK hiện tại cung cấp những module nào hoặc một thư mục module path đang chứa những module nào.

Lệnh launcher:

~~~bash
java --list-modules
~~~

in danh sách các module mà runtime có thể quan sát được theo cấu hình tìm kiếm hiện tại, sau đó kết thúc. Đây là lệnh kiểm tra môi trường module; nó không khởi chạy main class của ứng dụng.

Bài này hướng dẫn cách đọc kết quả, bổ sung module path, lọc danh sách và phân biệt danh sách module observable với graph thực tế được resolve cho một ứng dụng.

Sau bài này, bạn có thể:

- Liệt kê các module có sẵn trong runtime đang dùng.
- Liệt kê thêm modular JAR hoặc exploded module trên module path.
- Hiểu ý nghĩa tên module và version hiển thị.
- Phân biệt module observable, module được resolve và service provider được khởi tạo.
- Dùng các tùy chọn chẩn đoán liên quan khi cần điều tra một modular application.

## 2. Liệt kê module của JDK hiện tại

Mở terminal và chạy:

~~~bash
java --list-modules
~~~

Kết quả trên một JDK có thể có dạng:

~~~text
java.base@21
java.compiler@21
java.datatransfer@21
java.desktop@21
java.instrument@21
java.logging@21
java.management@21
java.naming@21
java.net.http@21
java.prefs@21
java.rmi@21
java.scripting@21
java.security.jgss@21
java.sql@21
java.transaction.xa@21
java.xml@21
jdk.compiler@21
jdk.javadoc@21
jdk.jlink@21
jdk.unsupported@21
~~~

Danh sách thực tế phụ thuộc vào bản JDK, nhà cung cấp JDK, cách runtime được đóng gói và các tùy chọn launcher. Ví dụ trên chỉ minh họa định dạng; không phải danh sách cố định cho mọi máy.

Mỗi dòng thường có dạng:

~~~text
module.name@version
~~~

Trong đó:

- Phần trước dấu @ là tên module.
- Phần sau dấu @ là version được module cung cấp, nếu có.
- Module không khai báo version có thể được hiển thị mà không có phần version.

Một vài module quen thuộc:

| Module | Vai trò khái quát |
| --- | --- |
| java.base | Module nền tảng, chứa các API cốt lõi như java.lang và java.util. |
| java.logging | API và hạ tầng logging của Java. |
| java.sql | API JDBC và các kiểu dữ liệu SQL. |
| java.xml | API xử lý XML. |
| java.desktop | AWT, Swing và các API desktop liên quan. |
| jdk.compiler | Các công cụ compiler, bao gồm javac. |
| jdk.jlink | Công cụ tạo custom runtime image. |

Module java.base là module nền tảng mà các named module khác mặc định đọc được; các module khác có thể được ứng dụng yêu cầu trực tiếp hoặc gián tiếp.

## 3. Liệt kê module trên module path

Không có tham số bổ sung, launcher liệt kê các module observable từ runtime hiện tại. Để kiểm tra các module ứng dụng tự đóng gói, truyền module path:

~~~bash
java --module-path mods --list-modules
~~~

Giả sử thư mục mods chứa:

~~~text
project/
├── mods/
│   ├── com.example.greeting.api.jar
│   ├── com.example.greeting.provider.jar
│   └── com.example.tools/
│       ├── module-info.class
│       └── com/example/tools/Main.class
└── src/
~~~

Trong đó hai file JAR là modular JAR có module descriptor, còn thư mục com.example.tools là một exploded module. Khi các artifact có cấu trúc hợp lệ và nằm đúng vị trí mà module path chỉ định, chúng có thể xuất hiện trong danh sách module observable.

Kết quả minh họa:

~~~text
java.base@21
java.compiler@21
java.logging@21
...
com.example.greeting.api
com.example.greeting.provider
com.example.tools
~~~

Lưu ý:

- Thư mục mods trong ví dụ là module path entry chứa các module.
- Một modular JAR có module descriptor module-info.class.
- Exploded module là thư mục module đã có module-info.class và các class đã biên dịch theo package.
- Tên module được xác định bởi module descriptor, không nhất thiết giống tên file JAR.
- Một JAR không có module descriptor có thể được xem là automatic module khi đặt trên module path; tên automatic module được suy ra theo quy tắc đặt tên hoặc manifest. JAR trên classpath không trở thành một named module observable theo cách này.

Nếu dùng nhiều module path entry, truyền danh sách theo dấu phân tách của hệ điều hành. Trên Windows, path-list thường dùng dấu chấm phẩy; trên Linux và macOS, path-list thường dùng dấu hai chấm.

Ví dụ Windows:

~~~powershell
java --module-path "mods;plugins" --list-modules
~~~

Ví dụ Linux/macOS:

~~~bash
java --module-path "mods:plugins" --list-modules
~~~

## 4. Giới hạn danh sách bằng --limit-modules

Một runtime có thể quan sát nhiều module hơn số module mà ứng dụng thực sự cần. Tùy chọn --limit-modules giới hạn tập module observable theo các module được nêu và dependency closure cần thiết của chúng.

Ví dụ:

~~~bash
java --limit-modules java.base,java.logging --list-modules
~~~

Lệnh này yêu cầu launcher giới hạn tập module theo java.base và java.logging cùng các dependency cần thiết theo quy tắc module resolution. Kết quả giúp khảo sát một runtime/module universe nhỏ hơn.

Có thể kết hợp với module path:

~~~bash
java --module-path mods --limit-modules java.base,com.example.greeting.app --list-modules
~~~

Việc giới hạn có thể làm một số module không còn observable hoặc khiến ứng dụng không resolve được nếu chúng nằm ngoài tập được phép. Chỉ dùng tùy chọn này khi muốn chủ động kiểm soát tập module có thể dùng.

## 5. Lọc kết quả để tìm module cần thiết

Kết quả có thể dài, đặc biệt trên JDK đầy đủ. Có thể chuyển output qua công cụ lọc của hệ điều hành.

Trên Linux/macOS:

~~~bash
java --list-modules | grep java.sql
~~~

Trên Windows PowerShell:

~~~powershell
java --list-modules | Select-String "java.sql"
~~~

Hoặc dùng findstr trong Command Prompt:

~~~cmd
java --list-modules | findstr java.sql
~~~

Ví dụ, tìm module HTTP client:

~~~bash
java --list-modules | grep java.net.http
~~~

Các công cụ lọc chỉ xử lý văn bản được in ra. Chúng không thay đổi module graph hoặc cấu hình runtime.

## 6. Phân biệt observable modules và resolved modules

Đây là điểm rất dễ nhầm khi đọc kết quả.

**Observable modules** là những module mà hệ thống module có thể tìm thấy trong phạm vi cấu hình tìm kiếm hiện tại, ví dụ runtime image và module path. Lệnh --list-modules phục vụ việc liệt kê tập này.

**Resolved modules** là các module thực sự được đưa vào Configuration khi resolver giải quyết một tập root modules và dependency của chúng. Một module có thể observable nhưng không được resolve cho ứng dụng đang chạy.

Ví dụ, module path có thể chứa cả ba module:

~~~text
com.example.app
com.example.api
com.example.optional-plugin
~~~

Nếu app chỉ yêu cầu com.example.api và không dùng hoặc yêu cầu optional plugin, plugin có thể vẫn xuất hiện trong danh sách observable nhưng không nằm trong configuration được resolve cho app.

Vì vậy, không thể kết luận một module đã được ứng dụng nạp vào graph chỉ vì tên của nó xuất hiện trong kết quả --list-modules.

## 7. Các lệnh chẩn đoán liên quan

### Xem descriptor của một module

Dùng --describe-module để xem thông tin descriptor của một module cụ thể:

~~~bash
java --describe-module java.sql
~~~

Có thể mô tả module ứng dụng trên module path:

~~~bash
java --module-path mods --describe-module com.example.greeting.app
~~~

Thông tin có thể bao gồm module name, version, các package được export, các module được require, service được uses và service được provides. Đây là cách xem metadata của một module mà không cần chạy main class.

### Xem quá trình resolve khi khởi chạy ứng dụng

Dùng --show-module-resolution cùng lệnh chạy module:

~~~bash
java --show-module-resolution --module-path mods --module com.example.greeting.app/com.example.greeting.app.Main
~~~

Tùy chọn này in thông tin về quá trình module resolution khi launcher khởi chạy ứng dụng. Nó hữu ích khi cần biết module nào được resolve và dependency nào dẫn tới chúng.

Nếu cần quan sát service provider được thêm qua service binding, hãy bảo đảm cách khởi chạy thực hiện service binding phù hợp. Chỉ nhìn danh sách --list-modules không thể thay thế việc xem resolution của ứng dụng cụ thể.

### So sánh ba lệnh

| Lệnh | Câu hỏi được trả lời |
| --- | --- |
| java --list-modules | Runtime có thể quan sát những module nào? |
| java --describe-module module.name | Descriptor của module này khai báo điều gì? |
| java --show-module-resolution ... | Launcher resolve những module nào khi khởi chạy ứng dụng? |

## 8. Quan hệ với ServiceLoader

Một provider module có thể xuất hiện trong kết quả --list-modules nếu module đó observable trên module path hoặc trong runtime image. Tuy nhiên, điều đó không có nghĩa provider đã được chọn hoặc service instance đã được tạo.

Cần tách các bước:

1. Provider module được đặt trong phạm vi module finder có thể quan sát.
2. Module resolver đưa provider vào configuration nếu service binding hoặc dependency resolution yêu cầu.
3. Ứng dụng gọi ServiceLoader để khám phá provider.
4. Ứng dụng yêu cầu instance bằng Provider.get() hoặc duyệt instance qua iterator.

Ví dụ, module descriptor của provider có thể khai báo:

~~~java
module com.example.greeting.provider {
    requires com.example.greeting.api;

    provides com.example.greeting.api.GreetingService
        with com.example.greeting.provider.FormalGreetingService;
}
~~~

Module consumer khai báo:

~~~java
module com.example.greeting.app {
    requires com.example.greeting.api;

    uses com.example.greeting.api.GreetingService;
}
~~~

Lệnh --list-modules có thể giúp xác nhận provider module có thể được tìm thấy qua module path. Khi cần xác nhận provider được đưa vào graph cho ứng dụng, hãy kiểm tra resolution bằng cách khởi chạy với --show-module-resolution hoặc kiểm tra Configuration trong code. Khi cần xác nhận implementation được khởi tạo, quan sát vị trí ứng dụng gọi ServiceLoader và Provider.get().

## 9. Một số tình huống thực tế

**Kiểm tra máy có module java.sql không**

~~~bash
java --list-modules
~~~

Tìm dòng java.sql trong kết quả. Nếu cần lọc nhanh, dùng grep hoặc Select-String theo hệ điều hành.

**Kiểm tra một modular JAR có được tìm thấy không**

~~~bash
java --module-path mods --list-modules
~~~

Đối chiếu tên module hiển thị với module name trong module-info.java. Nếu không xuất hiện, kiểm tra file JAR có modular descriptor không, vị trí file có nằm trực tiếp trong module path entry phù hợp không và tên module có đúng không.

**Kiểm tra descriptor của module provider**

~~~bash
java --module-path mods --describe-module com.example.greeting.provider
~~~

Tìm directive provides và service type tương ứng.

**Điều tra vì sao ứng dụng không tìm thấy một dependency**

~~~bash
java --show-module-resolution --module-path mods --module com.example.greeting.app/com.example.greeting.app.Main
~~~

Kiểm tra root module, các dependency được resolve và module path thực tế. Đồng thời xem module descriptor của consumer có requires hoặc uses phù hợp hay không.

## 10. Ghi nhớ

- java --list-modules liệt kê module observable trong cấu hình tìm kiếm hiện tại rồi kết thúc.
- Dùng --module-path để thêm modular JAR hoặc exploded module cần khảo sát.
- Dòng kết quả thường có dạng module.name@version; version có thể không xuất hiện nếu module không khai báo.
- Observable không đồng nghĩa với resolved; resolved cũng không đồng nghĩa với service instance đã được khởi tạo.
- Dùng --describe-module để xem descriptor của một module.
- Dùng --show-module-resolution khi cần chẩn đoán graph được resolve cho một lần chạy cụ thể.
- Với ServiceLoader, cần phân biệt provider có mặt trên module path, provider được bind vào graph và implementation được khởi tạo.

Khi bắt đầu điều tra một modular application, hãy dùng --list-modules để kiểm tra nguồn module có thể quan sát, --describe-module để đọc contract của module và --show-module-resolution để hiểu graph mà launcher thực sự xây dựng.
