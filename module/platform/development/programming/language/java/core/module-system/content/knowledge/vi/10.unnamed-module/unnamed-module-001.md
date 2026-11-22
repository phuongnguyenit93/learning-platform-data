# Unnamed module của classpath

Trong Java Platform Module System (JPMS), các class được nạp từ classpath thuộc về một **unnamed module** gắn với class loader đã nạp chúng. Unnamed module là module không có tên và không có `module-info.java`. Nó cho phép các ứng dụng Java truyền thống tiếp tục chạy mà không cần chuyển ngay sang mô hình named module.

Khi chạy ứng dụng bằng `-cp` hoặc `--class-path`, Java không tạo một named module riêng cho từng JAR trên classpath. Những class do cùng một class loader nạp sẽ thuộc unnamed module của class loader đó. Vì vậy, các JAR trên classpath thường chia sẻ một vùng module không tên, dù chúng vẫn có thể nằm trong những file riêng biệt.

## 1. Unnamed module được tạo như thế nào?

Mỗi class loader có một unnamed module tương ứng. Với ứng dụng chạy thông thường, class loader ứng dụng nạp các class từ những thư mục và JAR được chỉ định trên classpath; các class đó thuộc unnamed module của class loader ứng dụng.

Ví dụ:

```shell
java -cp "app.jar;lib-a.jar;lib-b.jar" com.acme.app.Main
```

Trên Windows, dấu phân cách classpath là dấu chấm phẩy. Trên Linux và macOS, dùng dấu hai chấm:

```shell
java -cp "app.jar:lib-a.jar:lib-b.jar" com.acme.app.Main
```

Các class mà application class loader nạp từ `app.jar`, `lib-a.jar` và `lib-b.jar` đều thuộc unnamed module của class loader đó. Việc mỗi thư viện được đóng gói thành một JAR riêng không làm nó tự trở thành một named module.

Nếu một ứng dụng tạo class loader riêng, class do loader đó nạp sẽ thuộc unnamed module gắn với loader riêng. Do đó, trong một JVM có thể có nhiều unnamed module, mỗi module gắn với một class loader khác nhau.

## 2. Đặc điểm của unnamed module

Unnamed module có một số đặc điểm quan trọng:

- **Không có tên module:** không thể tham chiếu nó bằng tên trong directive `requires`.
- **Không có module descriptor:** không có `module-info.java` để khai báo `requires`, `exports`, `opens`, `uses` hay `provides`.
- **Đọc được các module khác:** unnamed module có khả năng đọc rộng tới các module trong cấu hình/layer liên quan, nên mã classpath có thể sử dụng API đã được export của named module.
- **Export các package của mình:** các package trong unnamed module được export, vì vậy named module có thể truy cập chúng nếu named module có readability tới unnamed module.
- **Là open module:** các package của unnamed module được mở cho deep reflection.
- **Không tạo ranh giới encapsulation theo package như explicit module:** mã classpath tiếp tục dựa vào access modifier Java và các quy tắc class loader.

Các đặc điểm này hỗ trợ tính tương thích với ứng dụng cũ. Tuy nhiên, unnamed module không cung cấp sự kiểm soát dependency và package boundary rõ ràng như explicit module.

## 3. module-info.class bị bỏ qua trên classpath

Một JAR có thể chứa `module-info.class` để trở thành explicit module khi đặt trên module path. Nhưng khi cùng JAR được đặt trên classpath, runtime không dùng descriptor đó để tạo named module. Các class được nạp vào unnamed module của class loader.

Ví dụ, JAR có descriptor:

```java
module com.acme.library {
    exports com.acme.library.api;
}
```

Nếu chạy:

```shell
java -cp "app.jar;library.jar" com.acme.app.Main
```

thì ranh giới module và directive `exports` của `com.acme.library` không được áp dụng như khi JAR nằm trên module path. Classpath sử dụng mô hình unnamed module.

Nếu chuyển sang:

```shell
java --module-path mods \
     --module com.acme.app/com.acme.app.Main
```

thì các JAR modular trên module path được phân giải thành named module và descriptor của chúng được áp dụng. Một package không export có thể khiến consumer không truy cập được, dù class bên trong có modifier `public`.

Vì vậy, một thư viện có thể hoạt động trên classpath nhưng phát sinh lỗi truy cập khi chuyển sang module path. Khi migration, cần kiểm tra descriptor, `requires`, `exports`, `opens` và vị trí thật của từng dependency.

## 4. Phân biệt unnamed module và automatic module

Hai khái niệm này thường bị nhầm lẫn vì đều có thể xuất hiện khi làm việc với thư viện cũ không có `module-info.class`.

| Đặc điểm | Unnamed module | Automatic module |
|---|---|---|
| Nguồn phổ biến | Class/JAR được nạp từ classpath | JAR không có descriptor đặt trên module path |
| Có tên module | Không | Có |
| Có module descriptor tường minh | Không | Không có descriptor do tác giả viết; tên và hành vi module được suy ra |
| Đọc module khác | Rộng, không khai báo `requires` | Có khả năng đọc rộng để hỗ trợ migration |
| Package được export | Tất cả package của unnamed module | Tất cả package của automatic module |
| Có thể được named module `requires` | Không thể dùng tên vì không có tên module | Có thể khai báo `requires` bằng tên automatic module |

Ví dụ một thư viện cũ không có `module-info.class`:

- Đặt trên classpath: các class thuộc unnamed module của class loader.
- Đặt trên module path: JAR được xem là automatic module, có tên lấy từ `Automatic-Module-Name` trong manifest nếu có, hoặc được suy ra từ tên JAR.

Automatic module vẫn là named module và có thể được tham chiếu trong `requires`. Unnamed module không có tên nên không thể xuất hiện trong directive `requires` của một module descriptor.

## 5. Named module có đọc được unnamed module không?

Chiều readability rất quan trọng khi kết hợp module path và classpath. Unnamed module đọc được các named module, nhưng named module không tự động đọc unnamed module. Vì vậy, một ứng dụng modular có thể không truy cập được thư viện chỉ nằm trên classpath.

Named module không thể viết:

```java
module com.acme.app {
    requires unnamed;
}
```

Không có tên `unnamed` để tham chiếu. Trong tình huống migration cần named module truy cập classpath, có thể bổ sung quan hệ readability ở thời điểm biên dịch/chạy bằng `--add-reads`:

```shell
java --module-path mods \
     --class-path legacy-library.jar \
     --add-reads com.acme.app=ALL-UNNAMED \
     --module com.acme.app/com.acme.app.Main
```

`ALL-UNNAMED` chỉ các unnamed module liên quan trong runtime. Sau khi bổ sung readability, module ứng dụng có thể tham chiếu các kiểu public trong package của unnamed module theo các quy tắc truy cập Java thông thường.

Đây là giải pháp chuyển tiếp hữu ích khi chưa thể modularize thư viện cũ. Về lâu dài, nên đưa thư viện lên module path dưới dạng explicit hoặc automatic module, hoặc đóng gói dependency theo kiến trúc modular rõ ràng.

## 6. Ví dụ kiểm tra class thuộc unnamed module

Có thể kiểm tra module của một class trong runtime bằng API `Class.getModule()`:

```java
public class ModuleInfoExample {
    public static void main(String[] args) {
        Module module = ModuleInfoExample.class.getModule();

        System.out.println("Named: " + module.isNamed());
        System.out.println("Name: " + module.getName());
        System.out.println("Class loader: "
            + ModuleInfoExample.class.getClassLoader());
    }
}
```

Khi class được nạp từ classpath bởi application class loader, kết quả thường cho biết:

- `isNamed()` trả về `false`.
- `getName()` trả về `null`.
- Class loader là application class loader.

Nếu class nằm trong named module trên module path, `isNamed()` trả về `true` và `getName()` trả về tên module, ví dụ `com.acme.app`.

Có thể kiểm tra module của một thư viện cụ thể:

```java
Module libraryModule = com.acme.legacy.LegacyClient.class.getModule();

System.out.println(libraryModule.isNamed());
System.out.println(libraryModule.getName());
```

Cách kiểm tra này đáng tin cậy hơn việc chỉ nhìn tên file JAR, bởi cùng một JAR có thể được đặt ở classpath hoặc module path và được xử lý theo hai chế độ khác nhau.

## 7. ServiceLoader với classpath

Cơ chế SPI truyền thống có thể hoạt động trên classpath bằng file cấu hình trong thư mục `META-INF/services`.

Giả sử service interface là:

```java
package com.acme.spi;

public interface GreetingService {
    String greet(String name);
}
```

Provider implementation:

```java
package com.acme.provider;

import com.acme.spi.GreetingService;

public class EnglishGreetingService implements GreetingService {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

Trong JAR provider, tạo file:

```text
META-INF/services/com.acme.spi.GreetingService
```

Nội dung file:

```text
com.acme.provider.EnglishGreetingService
```

Consumer có thể tìm provider bằng:

```java
ServiceLoader<GreetingService> loader =
    ServiceLoader.load(GreetingService.class);

for (GreetingService service : loader) {
    System.out.println(service.greet("Java"));
}
```

Khi chạy trên classpath, `ServiceLoader` tìm provider thông qua file `META-INF/services` và class loader. Khi dùng named module, consumer khai báo `uses` và provider khai báo `provides ... with ...` trong `module-info.java`. Đây là hai hình thức đăng ký tương ứng với hai cách đóng gói.

## 8. Classpath và các giới hạn khi chuyển sang module path

Classpath có tính linh hoạt và tương thích cao, nhưng không cung cấp các ranh giới module tường minh:

- Dependency không được khai báo bằng `requires`; JVM tìm class dựa trên class loader và thứ tự classpath.
- Package có thể được đóng góp bởi nhiều JAR; việc nạp class phụ thuộc vào thứ tự và cơ chế class loader.
- Không có `exports` để giới hạn package nào được module khác sử dụng.
- Không có `opens` tường minh theo module; unnamed module mở package cho deep reflection.
- Một JAR có `module-info.class` vẫn không áp dụng descriptor khi chạy trên classpath.

Khi chuyển từ classpath sang module path, cần kiểm tra split package, duplicate class, service provider, resource lookup và framework dựa trên classpath scanning. Một số thư viện cũ giả định mọi dependency đều có thể tìm qua `java.class.path`; giả định đó có thể không đúng với module path.

## 9. Chẩn đoán và kiểm tra

Để xác định một JAR đang được sử dụng như unnamed module hay named module, trước hết kiểm tra lệnh chạy:

```shell
# Classpath: các class được nạp trong unnamed module của class loader
java -cp "app.jar;legacy.jar" com.acme.app.Main

# Module path: phân giải các named/automatic modules
java --show-module-resolution --module-path mods \
     --module com.acme.app/com.acme.app.Main
```

Có thể xem module descriptor của JAR:

```shell
jar --describe-module --file legacy.jar
```

Nếu JAR không có descriptor nhưng đặt trên module path, công cụ có thể hiển thị tên automatic module được suy ra. Nếu chạy trên classpath, hãy dùng `Class.getModule()` để xác định class thực tế thuộc unnamed module nào.

Khi một classpath library không truy cập được từ named module, hãy xác nhận module gọi có readability tới unnamed module chưa. Trong trường hợp chuyển tiếp, xem xét `--add-reads <module>=ALL-UNNAMED`. Khi một named module không truy cập được package của named module khác, kiểm tra `exports` hoặc qualified exports; nếu cần deep reflection, kiểm tra `opens`.

## 10. Khi nào nên giữ classpath và khi nào nên modularize?

Classpath phù hợp với ứng dụng legacy, thư viện chưa hỗ trợ JPMS hoặc dự án chưa có nhu cầu đóng gói theo module. Nó cho phép tích hợp nhanh nhưng dependency và package boundary ít rõ ràng.

Named module phù hợp khi muốn khai báo dependency rõ ràng, kiểm soát package API, phát hiện thiếu dependency sớm và hỗ trợ runtime image tối giản. Với thư viện chưa có `module-info.java`, automatic module có thể là bước chuyển tiếp trên module path. Khi đã sẵn sàng, tác giả có thể bổ sung explicit module descriptor.

Không nên chuyển module path chỉ bằng cách đổi cờ JVM. Hãy kiểm tra toàn bộ dependency graph, tên module, package export, reflection, service registration và cách framework khám phá resource.

## 11. Nguyên tắc ghi nhớ

- `public` không đồng nghĩa với package được công khai qua module boundary.
- Classpath đưa class vào unnamed module của class loader; module descriptor trong JAR không được áp dụng ở chế độ này.
- Unnamed module không có tên nên named module không thể `requires` nó.
- Unnamed module đọc các named module và export các package của mình; chiều ngược lại cần readability phù hợp.
- Automatic module có tên và xuất hiện trên module path; nó khác unnamed module.
- `requires` tạo readability, `exports` công bố package, `opens` cấp quyền deep reflection.
- Khi migration, kiểm tra artifact và lệnh chạy thực tế thay vì chỉ dựa vào mã nguồn.

Unnamed module là cầu nối để các ứng dụng classpath tiếp tục chạy trong nền tảng có JPMS. Hiểu đúng ranh giới của nó giúp giải thích vì sao một class public có thể truy cập được trong ứng dụng truyền thống nhưng bị giới hạn khi thư viện được đưa vào named module, đồng thời giúp chọn hướng migration phù hợp.