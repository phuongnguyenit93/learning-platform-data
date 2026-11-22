# Tạo runtime riêng bằng jlink trong Java 17

> **Chủ đề:** Java 17  
> **Chương:** Đóng gói và nền tảng  
> **Mục tiêu:** Hiểu cách `jlink` tạo một runtime image tùy chỉnh từ các module của JDK và ứng dụng; biết chuẩn bị module, xác định dependency, tạo launcher, kiểm tra image và phân phối ứng dụng cùng runtime riêng.

## 1. jlink giải quyết vấn đề gì?

Một ứng dụng Java thường cần có Java runtime để chạy. Nếu chỉ phân phối file JAR, người dùng phải cài một runtime tương thích hoặc tự chuẩn bị môi trường Java. Điều này có thể dẫn đến:

- Máy đích chưa cài Java.
- Máy đích dùng phiên bản Java không tương thích.
- Runtime có nhiều module và thành phần hơn ứng dụng thực sự cần.
- Việc cài đặt và cấu hình runtime trở thành trách nhiệm của người dùng.

`jlink` là công cụ trong JDK, được giới thiệu từ Java 9 cùng hệ thống module JPMS. Nó liên kết các module cần thiết để tạo một **runtime image** tùy chỉnh. Image chứa runtime có thể chạy ứng dụng mà không yêu cầu người dùng cài một JDK riêng.

Ví dụ, một ứng dụng chỉ cần `java.base` và `java.logging` có thể được đóng gói cùng runtime chứa các module cần thiết đó, thay vì yêu cầu người dùng cài một JDK đầy đủ.

### 1.1. Runtime image là gì?

Runtime image là một thư mục có cấu trúc chứa các thành phần cần để chạy ứng dụng trên một nền tảng cụ thể, thường gồm:

- Runtime launcher như `bin/java` và launcher do ứng dụng tạo.
- Các module runtime đã được liên kết.
- Native libraries và cấu hình cần thiết.
- Metadata và resource mà runtime cần.

Ví dụ cấu trúc khái quát:

```text
my-runtime/
  bin/
    java
    keytool
    orders
  conf/
  include/       (có thể không có nếu đã loại header files)
  legal/
  lib/
    modules
    server/
    security/
    ...
```

Danh sách thư mục/file thực tế phụ thuộc tùy chọn jlink và các module được liên kết. Không nên dựa vào cấu trúc nội bộ của image để tự sửa file runtime; hãy tạo lại image bằng lệnh jlink khi thay đổi cấu hình.

### 1.2. jlink không tạo native executable độc lập

Runtime image có launcher để khởi chạy ứng dụng Java, nhưng ứng dụng vẫn chạy trên JVM trong image. Đây không phải phép biên dịch Java thành một file native executable độc lập.

Image cũng không phải JDK đầy đủ: nó thường không có compiler `javac`, debugger hoặc toàn bộ công cụ phát triển. Mục tiêu là cung cấp runtime vừa đủ cho ứng dụng.

### 1.3. jlink chỉ làm việc với module

Đầu vào của jlink là các module có thể resolve được, chẳng hạn:

- Module của JDK, được cung cấp dưới dạng JMOD trong thư mục `$JAVA_HOME/jmods`.
- Modular JAR có `module-info.class`.
- Exploded module (thư mục module đã biên dịch, chứa `module-info.class`).
- JMOD do công cụ `jmod` tạo hoặc do JDK cung cấp.

Một JAR chỉ chạy trên classpath hoặc một automatic module không thể được jlink liên kết như một module tường minh. Các dependency đó cần được modular hóa hoặc xử lý bằng cách đóng gói phù hợp trước khi tạo image.

## 2. Điều kiện để tạo runtime image

### 2.1. Dùng JDK 17

`jlink` được phân phối cùng JDK. Kiểm tra:

```bash
java -version
jlink --version
javac -version
```

Nên dùng JDK 17 để biên dịch, phân tích và liên kết ứng dụng mục tiêu Java 17. Nếu dùng JDK khác, cần hiểu rõ khả năng tương thích của class file, module descriptor và các module runtime được liên kết.

### 2.2. Ứng dụng phải là named module tường minh

Một ứng dụng modular thường có file `module-info.java`. Ví dụ:

```java
module com.acme.orders {
    requires java.logging;
}
```

Trong ví dụ này, module ứng dụng có tên `com.acme.orders` và khai báo dependency đến `java.logging`.

Một module có thể khai báo thêm `exports` để công khai package, `opens` cho reflection hoặc `uses`/`provides` cho service. Các khai báo này có thể ảnh hưởng đến module graph mà jlink cần resolve.

### 2.3. Dependency cũng cần tương thích với module path

Nếu ứng dụng sử dụng thư viện bên thứ ba, cần xác định thư viện đó có module descriptor hay không:

| Loại dependency | Có thể đưa trực tiếp vào jlink? | Hướng xử lý |
|---|---|---|
| JDK module | Có | JDK cung cấp trong JMOD |
| Modular JAR có descriptor tường minh | Có | Đưa vào module path |
| Exploded module | Có | Đưa thư mục chứa module vào module path |
| JMOD hợp lệ | Có | Đưa vào module path |
| Automatic module | Không | Modular hóa dependency trước khi link |
| JAR chỉ dùng trên classpath | Không trực tiếp | Chuyển sang named module hoặc đóng gói theo kiến trúc khác |

Đừng nhầm việc một JAR có thể dùng trên module path khi chạy với việc JAR đó có thể được jlink liên kết. jlink cần module tường minh để xây runtime image.

## 3. Tạo ứng dụng modular đơn giản

Trước khi dùng jlink, hãy tạo một ứng dụng nhỏ có module descriptor để thấy rõ module path và module graph.

### 3.1. Cấu trúc source

Ví dụ:

```text
orders-app/
  src/
    com.acme.orders/
      module-info.java
      com/acme/orders/Main.java
```

Nội dung `module-info.java`:

```java
module com.acme.orders {
    requires java.logging;
}
```

Nội dung `Main.java`:

```java
package com.acme.orders;

import java.util.logging.Logger;

public class Main {
    private static final Logger LOGGER =
            Logger.getLogger(Main.class.getName());

    public static void main(String[] args) {
        LOGGER.info("Orders application is running on Java "
                + Runtime.version());
    }
}
```

Module `com.acme.orders` khai báo `requires java.logging` vì code dùng `Logger`. `java.base` luôn được đọc ngầm bởi mọi module, nên không cần ghi `requires java.base`.

### 3.2. Biên dịch thành exploded module

Từ thư mục gốc `orders-app`:

```bash
javac --module-source-path src -d mods -m com.acme.orders
```

Sau khi biên dịch, cấu trúc có dạng:

```text
mods/
  com.acme.orders/
    module-info.class
    com/acme/orders/Main.class
```

Thư mục `mods` là module path chứa exploded module `com.acme.orders`.

### 3.3. Chạy thử module trước khi link

Chạy module bằng JDK hiện tại:

```bash
java --module-path mods --module com.acme.orders/com.acme.orders.Main
```

Hoặc dùng cú pháp ngắn `-m`:

```bash
java --module-path mods -m com.acme.orders/com.acme.orders.Main
```

Kết quả log sẽ hiển thị thông báo ứng dụng đang chạy cùng phiên bản Java. Chạy thử trước giúp tách lỗi ứng dụng/module khỏi lỗi tạo runtime image.

## 4. Tạo runtime image bằng jlink

### 4.1. Cú pháp cơ bản

Lệnh tổng quát:

```bash
jlink --module-path <module-path> --add-modules <root-module>[,<root-module>...] --output <runtime-image>
```

Các tham số cốt lõi:

- `--module-path`: nơi jlink tìm module. Có thể chứa thư mục JMOD của JDK, modular JAR, JMOD và exploded module.
- `--add-modules`: các module gốc cần đưa vào image. jlink resolve dependency của chúng theo module descriptor.
- `--output`: thư mục output cho runtime image.

### 4.2. Tạo image trên Linux/macOS

Giả sử `JAVA_HOME` trỏ tới JDK 17 và source module đã được biên dịch vào `mods`:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.orders --output build/orders-runtime
```

Ở đây:

- `$JAVA_HOME/jmods` cung cấp các module của JDK.
- `mods` cung cấp exploded module của ứng dụng.
- `com.acme.orders` là root module.
- jlink tự resolve các dependency tường minh, gồm `java.logging` và các module mà module đó cần.

### 4.3. Tạo image trên Windows PowerShell

Trên Windows, dấu phân cách module path là dấu chấm phẩy:

```powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.acme.orders --output build\orders-runtime
```

Nếu chạy trong CMD, cú pháp biến môi trường và ký tự xuống dòng sẽ khác PowerShell. Hãy dùng đúng cú pháp của shell hiện tại.

### 4.4. Chạy ứng dụng từ runtime image

Image cơ bản đã có runtime launcher. Trên Linux/macOS:

```bash
build/orders-runtime/bin/java --module com.acme.orders/com.acme.orders.Main
```

Trên Windows PowerShell:

```powershell
build\orders-runtime\bin\java.exe --module com.acme.orders/com.acme.orders.Main
```

Lệnh này chạy module ứng dụng bằng runtime vừa tạo. Người dùng không cần trỏ đến JDK cài riêng trên máy nếu image được phân phối đầy đủ và tương thích với hệ thống đích.

## 5. Tạo launcher riêng cho ứng dụng

Nếu phân phối runtime cho người dùng cuối, không nên yêu cầu họ nhập tên module và main class mỗi lần. Tùy chọn `--launcher` tạo lệnh khởi chạy riêng trong image.

### 5.1. Cú pháp launcher

```text
--launcher <command-name>=<module>[/<main-class>]
```

Ví dụ:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.orders --launcher orders=com.acme.orders/com.acme.orders.Main --output build/orders-runtime
```

Sau khi link, image có launcher `orders` trong thư mục `bin`. Trên Windows, launcher có phần mở rộng executable phù hợp với nền tảng.

### 5.2. Chạy launcher

Linux/macOS:

```bash
build/orders-runtime/bin/orders
```

Windows PowerShell:

```powershell
build\orders-runtime\bin\orders.exe
```

Launcher gọi main class của module đã chỉ định, sử dụng runtime đi kèm image. Đây là cách thuận tiện để phân phối ứng dụng mà không bắt người dùng biết module name hoặc classpath/module path.

### 5.3. Thêm launcher cho nhiều entry point

Một runtime image có thể có nhiều launcher nếu ứng dụng có nhiều main class/module cần khởi chạy:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.orders,com.acme.admin --launcher orders=com.acme.orders/com.acme.orders.Main --launcher admin=com.acme.admin/com.acme.admin.Main --output build/acme-runtime
```

Các root module phải có mặt trên module path và resolve được. Chỉ thêm launcher không tự đưa một module chưa được resolve vào image; cần đưa module đó vào `--add-modules` hoặc dependency graph phù hợp.

## 6. Cách jlink chọn module cho image

### 6.1. Root module và dependency closure

`--add-modules` chỉ định root modules. jlink xây module graph từ các root đó và resolve những dependency cần thiết theo các chỉ thị `requires` trong descriptor.

Ví dụ:

```java
module com.acme.orders {
    requires java.logging;
    requires com.acme.money;
}

module com.acme.money {
    requires java.base;
}
```

Khi liên kết `com.acme.orders`, jlink cần resolve `java.logging` và `com.acme.money` cùng các dependency của chúng. `java.base` là module nền tảng luôn có mặt.

Đó là lý do một runtime image có thể nhỏ hơn JDK đầy đủ: chỉ các module nằm trong module graph cần thiết mới được liên kết.

### 6.2. Thêm nhiều root module

Nếu ứng dụng có nhiều entry point độc lập hoặc cần service provider module không được kéo vào qua dependency thông thường, có thể chỉ định nhiều root:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.orders,com.acme.admin --output build/acme-runtime
```

Danh sách module phân cách bằng dấu phẩy. Module phải được tìm thấy trên module path và có descriptor phù hợp.

### 6.3. Giới hạn tập module có thể quan sát

`--limit-modules` giới hạn tập module được xem xét trong quá trình resolve:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.orders --limit-modules java.base,java.logging,com.acme.orders --output build/orders-runtime
```

Tùy chọn này có thể hữu ích khi muốn kiểm soát rõ module universe. Tuy nhiên, danh sách phải chứa toàn bộ module cần thiết để resolve graph. Nếu thiếu dependency, quá trình link sẽ thất bại.

Thông thường, bắt đầu với `--add-modules` và để jlink resolve dependency là đủ. Chỉ dùng `--limit-modules` khi có yêu cầu cụ thể và đã hiểu module graph.

## 7. Service binding và ServiceLoader

Một ứng dụng có thể dùng Java Service Provider Interface (SPI) để tìm implementation lúc chạy thông qua `ServiceLoader`. Trong JPMS, consumer khai báo `uses` và provider khai báo `provides ... with ...`.

Ví dụ module consumer:

```java
module com.acme.orders {
    requires java.base;
    uses com.acme.orders.spi.PaymentGateway;
}
```

Module provider:

```java
module com.acme.payments.card {
    requires com.acme.orders;
    provides com.acme.orders.spi.PaymentGateway
        with com.acme.payments.card.CardPaymentGateway;
}
```

Trong thực tế, `java.base` có thể bỏ khỏi descriptor vì luôn được đọc ngầm. Ví dụ giữ lại để nhấn mạnh module nền tảng, nhưng module descriptor thường không cần khai báo nó.

Nếu provider module không nằm trong dependency graph theo cách resolve thông thường, tùy chọn `--bind-services` yêu cầu jlink bind các service provider module cùng dependency của chúng:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.orders --bind-services --output build/orders-runtime
```

Khi ứng dụng dùng `ServiceLoader`, hãy kiểm tra:

- Consumer module có khai báo `uses` đúng service type không.
- Provider module có khai báo `provides` với implementation hợp lệ không.
- Provider module có nằm trên module path không.
- Có cần `--bind-services` để đưa provider vào runtime image không.
- Constructor hoặc phương thức khởi tạo provider đáp ứng yêu cầu của ServiceLoader không.

`--bind-services` có thể làm image lớn hơn vì nó kéo thêm provider và dependency. Chỉ bật khi ứng dụng cần service binding hoặc khi chính sách đóng gói yêu cầu.

## 8. Tối ưu kích thước runtime image

Sau khi module graph đúng, có thể dùng các tùy chọn jlink để giảm dung lượng image.

### 8.1. Bỏ debug information

`--strip-debug` loại bỏ debug information khỏi các class trong image:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.orders --strip-debug --output build/orders-runtime
```

Điều này có thể giảm dung lượng nhưng cũng làm giảm thông tin debug có sẵn. Nếu cần debug production runtime hoặc phân tích stack trace theo yêu cầu đặc biệt, hãy cân nhắc trước khi strip.

### 8.2. Nén resource

Tùy chọn `--compress` hỗ trợ các mức trong JDK 17:

| Giá trị | Ý nghĩa |
|---|---|
| `0` | Không nén |
| `1` | Constant string sharing |
| `2` | Nén ZIP cho resource trong image |

Ví dụ:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.orders --compress=2 --output build/orders-runtime
```

Nén có thể giảm dung lượng lưu trữ nhưng có thể thay đổi chi phí đọc/giải nén khi chạy. Hãy đo cả kích thước image và hiệu năng khởi động/hoạt động theo workload thực tế.

### 8.3. Bỏ header files và man pages

Runtime dành cho người dùng cuối thường không cần C/C++ header files hoặc man pages:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.orders --no-header-files --no-man-pages --output build/orders-runtime
```

Hai tùy chọn này loại bỏ:

- `--no-header-files`: header files dùng cho phát triển native/JNI.
- `--no-man-pages`: man pages.

Chúng phù hợp với runtime image triển khai nếu ứng dụng không cần các tài liệu/header này.

### 8.4. Kết hợp các tùy chọn phổ biến

Ví dụ image gọn hơn có launcher:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.orders --launcher orders=com.acme.orders/com.acme.orders.Main --strip-debug --compress=2 --no-header-files --no-man-pages --output build/orders-runtime
```

Không nên mặc định bật mọi plugin. Hãy xác định mục tiêu triển khai, khả năng debug và yêu cầu hiệu năng trước khi chọn.

### 8.5. Xem plugin khả dụng

Danh sách plugin phụ thuộc phiên bản JDK:

```bash
jlink --list-plugins
```

Lệnh này cho biết plugin và tùy chọn mà bản jlink hiện tại hỗ trợ. Đây là nguồn tham chiếu tốt khi cần kiểm tra cú pháp chính xác cho JDK 17.

## 9. Phân tích dependency trước khi link bằng jdeps

Trước khi tạo image, cần biết ứng dụng phụ thuộc vào những module nào. `jdeps` là công cụ phân tích dependency của class/JAR/module, được cung cấp cùng JDK.

### 9.1. In danh sách module dependency

Với modular JAR và dependency đã đặt trong module path:

```bash
jdeps --print-module-deps --module-path "$JAVA_HOME/jmods:mlib" --recursive mlib/com.acme.orders.jar
```

`--print-module-deps` in danh sách module dependency dạng phù hợp để dùng với `--add-modules`. `--recursive` yêu cầu phân tích dependency theo cách đệ quy.

Kết quả ví dụ:

```text
java.base,java.logging,com.acme.money
```

Đây là ví dụ minh họa; kết quả thực tế phụ thuộc class được tham chiếu và module descriptor của ứng dụng cùng dependency.

### 9.2. Tạo runtime image từ danh sách module

Sau khi xem danh sách dependency và bảo đảm tất cả module đều có mặt trên module path:

```bash
jlink --module-path "$JAVA_HOME/jmods:mlib" --add-modules com.acme.orders --output build/orders-runtime
```

Thông thường nên chọn module ứng dụng làm root. jlink sẽ resolve các module cần thiết theo descriptor. Kết quả của `jdeps` là thông tin để đối chiếu và phát hiện dependency bị thiếu, không phải lý do để bỏ qua việc hiểu module graph.

### 9.3. Phân tích JAR không có descriptor

`jdeps` cũng có thể giúp phân tích một JAR cũ và gợi ý module dependency. Với một JAR chưa modular hóa, có thể thử:

```bash
jdeps --print-module-deps legacy-library.jar
```

Tuy nhiên, kết quả phân tích dependency không tự biến JAR thành explicit named module và không làm nó linkable. Nếu muốn đưa thư viện vào runtime image, cần chuyển nó thành module tường minh, chẳng hạn tạo descriptor phù hợp rồi đóng gói thành modular JAR hoặc JMOD.

### 9.4. Hỗ trợ tạo module descriptor cho thư viện cũ

`jdeps` có tùy chọn `--generate-module-info` để tạo source `module-info.java` ban đầu cho JAR chưa modular hóa:

```bash
jdeps --generate-module-info generated-modules legacy-library.jar
```

Descriptor được sinh ra chỉ là điểm khởi đầu. Hãy đọc và chỉnh sửa để:

- Xác nhận tên module.
- Khai báo đúng dependency.
- Chỉ export package thực sự là API.
- Thêm `uses`/`provides` nếu thư viện có SPI.
- Bổ sung `opens` khi framework cần reflection và có lý do cụ thể.

Sau đó biên dịch lại thư viện thành modular JAR và thử trên module path trước khi dùng jlink. Không nên xem descriptor tự sinh là hợp đồng module đã hoàn thiện.

## 10. JAR, exploded module và JMOD

jlink có thể nhận các dạng module khác nhau. Hiểu sự khác nhau giúp chọn cách đóng gói phù hợp.

| Dạng | Nội dung | Trường hợp thường dùng |
|---|---|---|
| Exploded module | Thư mục chứa `module-info.class` và package đã biên dịch | Phát triển, thử nghiệm và build nội bộ |
| Modular JAR | JAR có `module-info.class` ở gốc hoặc multi-release module descriptor hợp lệ | Phân phối thư viện/ứng dụng module |
| JMOD | Định dạng module riêng của JDK, có thể chứa class, native library, command, config và header | Xây dựng JDK/runtime và module cần thành phần native đặc thù |

### 10.1. Dùng modular JAR

Có thể đóng gói exploded module thành JAR:

```bash
jar --create --file mlib/com.acme.orders.jar --main-class com.acme.orders.Main -C mods/com.acme.orders .
```

JAR vẫn chứa `module-info.class` nên module descriptor được giữ lại. Sau đó có thể dùng thư mục `mlib` làm module path:

```bash
jlink --module-path "$JAVA_HOME/jmods:mlib" --add-modules com.acme.orders --launcher orders=com.acme.orders/com.acme.orders.Main --output build/orders-runtime
```

### 10.2. Khi nào cần JMOD?

JMOD hữu ích khi một module cần mang theo thành phần native hoặc tài nguyên build/runtime mà modular JAR không đóng gói theo cùng cách. Các module JDK trong `$JAVA_HOME/jmods` là ví dụ quen thuộc.

Đối với ứng dụng Java thuần chỉ có class và resource, modular JAR hoặc exploded module thường đủ. Không cần tạo JMOD chỉ để dùng jlink.

### 10.3. Không đưa JDK/JRE cài sẵn lên module path như một thư mục tùy ý

Module path cần trỏ tới thư mục chứa các module hợp lệ, chẳng hạn `$JAVA_HOME/jmods` hoặc thư mục chứa modular JAR. Trỏ tới thư mục cài JDK chung chung không thay thế được module path đúng.

Hãy kiểm tra module path và module name bằng công cụ của JDK:

```bash
java --list-modules
jmod describe "$JAVA_HOME/jmods/java.base.jmod"
```

Lệnh `java --list-modules` liệt kê module mà runtime hiện tại quan sát được. `jmod describe` mô tả module trong JMOD.

## 11. Ứng dụng chưa modular hóa: chỉ link runtime, phân phối JAR riêng

Không phải mọi ứng dụng đều có thể chuyển ngay sang JPMS. Có thể dùng jlink để tạo runtime nhỏ chứa các module JDK mà ứng dụng classpath cần, rồi phân phối JAR ứng dụng riêng.

Trong cách này:

- jlink chỉ tạo runtime image từ module JDK được chọn.
- JAR ứng dụng và thư viện classpath vẫn được phân phối bên cạnh image.
- jlink không đóng gói hoặc phân tích đầy đủ object/classpath dependency thành module trong image.
- Người chạy dùng launcher `java` trong image với `-cp`.

### 11.1. Phân tích module JDK cần thiết

Ví dụ:

```bash
jdeps --print-module-deps --class-path "lib/*" app.jar
```

Kết quả có thể là:

```text
java.base,java.logging,java.sql
```

Đây là kết quả minh họa. Nếu ứng dụng dùng reflection, service loader, tên class được tạo động hoặc dependency không thể phân tích tĩnh, có thể phải bổ sung module thủ công và kiểm tra khi chạy.

### 11.2. Link runtime chứa các module JDK

```bash
jlink --module-path "$JAVA_HOME/jmods" --add-modules java.base,java.logging,java.sql --output build/legacy-runtime
```

### 11.3. Phân phối JAR bên cạnh runtime

Ví dụ cấu trúc:

```text
distribution/
  runtime/
    bin/java
    lib/modules
    ...
  app/
    app.jar
    lib/
      dependency-a.jar
      dependency-b.jar
```

Chạy trên Linux/macOS:

```bash
distribution/runtime/bin/java -cp "distribution/app/app.jar:distribution/app/lib/*" com.acme.Main
```

Trên Windows, dùng dấu chấm phẩy trong classpath:

```powershell
distribution\runtime\bin\java.exe -cp "distribution\app\app.jar;distribution\app\lib\*" com.acme.Main
```

Đây là phương án chuyển tiếp hữu ích. Nếu cần jlink đóng gói cả ứng dụng vào image, hãy modular hóa ứng dụng và dependency thành named module tường minh.

## 12. Kiểm tra runtime image sau khi tạo

Đừng chỉ dựa vào việc lệnh jlink kết thúc không lỗi. Hãy kiểm tra image có đủ module và chạy được ứng dụng.

### 12.1. Kiểm tra phiên bản runtime

Linux/macOS:

```bash
build/orders-runtime/bin/java -version
```

Windows PowerShell:

```powershell
build\orders-runtime\bin\java.exe -version
```

Xác nhận runtime image dùng phiên bản Java mong muốn.

### 12.2. Liệt kê module có trong image

Linux/macOS:

```bash
build/orders-runtime/bin/java --list-modules
```

Windows:

```powershell
build\orders-runtime\bin\java.exe --list-modules
```

Danh sách module giúp xác nhận image không vô tình thiếu module cần thiết hoặc chứa nhiều module hơn dự kiến.

### 12.3. Chạy launcher của ứng dụng

Linux/macOS:

```bash
build/orders-runtime/bin/orders
```

Windows:

```powershell
build\orders-runtime\bin\orders.exe
```

Chạy smoke test với cấu hình và dữ liệu đại diện. Nếu ứng dụng dùng file cấu hình, certificate, timezone, locale, native library hoặc service provider, cần kiểm tra các thành phần đó trong môi trường image.

### 12.4. Kiểm tra dung lượng

So sánh kích thước:

- JDK đầy đủ được dùng làm nguồn.
- Runtime image vừa tạo.
- Toàn bộ distribution sau khi thêm ứng dụng, config và thư viện cần thiết.

Mục tiêu là tối ưu gói phân phối tổng thể, không chỉ giảm thư mục runtime trong khi quên các file cần thiết bên cạnh.

## 13. Phân phối runtime image

### 13.1. Đóng gói thư mục image

Sau khi kiểm thử, có thể nén toàn bộ thư mục runtime image cùng launcher, config và tài nguyên cần thiết thành gói phân phối. Giữ nguyên cấu trúc thư mục vì launcher và runtime sử dụng đường dẫn tương đối/nội bộ.

Ví dụ:

```text
orders-distribution/
  runtime/
  config/
  data/
  README.txt
```

Nếu launcher đã được tạo trong runtime image, người dùng chỉ cần chạy file trong `runtime/bin`.

### 13.2. Runtime image phụ thuộc nền tảng

Runtime image chứa native library và launcher phù hợp với nền tảng mà JDK/JMOD nguồn hỗ trợ. Vì vậy:

- Image cho Windows không phải gói chạy chung cho Linux/macOS.
- Khác biệt kiến trúc CPU (x64, AArch64, ...) cũng cần được xem xét.
- Native library bên thứ ba phải đúng OS/architecture và tương thích ABI.
- Hãy tạo và kiểm thử image riêng cho từng target platform.

Không thể lấy một runtime image rồi giả định nó chạy trên mọi hệ điều hành chỉ vì bytecode Java có tính portable.

### 13.3. Cập nhật bảo mật runtime đi kèm

Khi phân phối runtime image riêng, ứng dụng mang theo runtime được link tại thời điểm build. Cập nhật Java trên máy người dùng không tự cập nhật runtime nằm trong gói ứng dụng.

Khi có bản cập nhật JDK 17 chứa bản vá bảo mật hoặc sửa lỗi, cần:

1. Cập nhật JDK build lên bản vá được hỗ trợ.
2. Tạo lại runtime image bằng jlink.
3. Chạy kiểm thử hồi quy và kiểm tra tương thích.
4. Phát hành lại gói ứng dụng/runtime.
5. Có chính sách theo dõi phiên bản runtime đang được triển khai.

Đây là trách nhiệm quan trọng của đơn vị phân phối ứng dụng tự chứa runtime.

## 14. Các lỗi thường gặp khi dùng jlink

| Lỗi/hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `Module ... not found` | Module path thiếu JMOD, modular JAR hoặc exploded module | Kiểm tra `--module-path`, tên module và đường dẫn |
| `Module ... not found, required by ...` | Dependency được khai báo bằng `requires` nhưng không có trên module path | Bổ sung dependency dạng module tường minh và kiểm tra module graph |
| `Automatic modules are not supported` | Đang đưa JAR automatic lên module path để jlink liên kết | Modular hóa thư viện thành explicit named module |
| `Invalid module name` | Tên module trong descriptor hoặc tên suy ra không hợp lệ | Sửa module descriptor/manifest và kiểm tra tên module |
| Không tìm thấy main class khi chạy launcher | Sai tên module, package hoặc main class trong `--launcher` | Xác nhận module name, class name và class có phương thức main phù hợp |
| Ứng dụng chạy trên JDK đầy đủ nhưng lỗi trong image | Image thiếu module được nạp động, service provider, resource hoặc native library | Phân tích dependency, dùng `--bind-services` khi cần và kiểm tra runtime trên image |
| ServiceLoader không tìm thấy provider | Provider module không có trong image hoặc descriptor thiếu `provides` | Kiểm tra `uses`/`provides` và thử `--bind-services` |
| Reflection thất bại trong runtime image | Package không mở cho framework cần reflection | Khai báo `opens` có phạm vi phù hợp và kiểm thử framework |
| Image không chạy trên máy khác | Khác OS, CPU architecture hoặc native dependency | Build và kiểm thử image cho từng target platform |
| Image không giảm nhiều dung lượng | Module graph lớn, resource nhiều hoặc plugin chưa phù hợp | Xem module list, kiểm tra dependency và thử compression/strip có đo lường |
| Lệnh jlink báo output path đã tồn tại/không rỗng | Thư mục output chứa dữ liệu từ lần build trước | Chọn thư mục output mới hoặc dọn output build do quy trình sở hữu |
| Runtime image thiếu cập nhật bảo mật | Gói ứng dụng đang mang runtime cũ | Rebuild image bằng bản JDK đã cập nhật và phát hành lại |

### 14.1. Chẩn đoán module không tìm thấy

Kiểm tra tên module và module path:

```bash
java --list-modules
jmod describe "$JAVA_HOME/jmods/java.logging.jmod"
```

Với modular JAR, có thể dùng:

```bash
jar --describe-module --file mlib/com.acme.orders.jar
```

Lệnh này giúp xem module descriptor và tên module của JAR. Đừng đoán tên module từ tên package.

### 14.2. Chẩn đoán dependency thiếu

Chạy jdeps trên ứng dụng và dependency:

```bash
jdeps --print-module-deps --module-path "$JAVA_HOME/jmods:mlib" --recursive mlib/com.acme.orders.jar
```

Đối chiếu output với module path. Nếu dependency không có descriptor, hãy modular hóa trước khi đưa vào jlink.

### 14.3. Chẩn đoán service provider

`jlink` hỗ trợ:

```bash
jlink --module-path "$JAVA_HOME/jmods:mlib" --suggest-providers java.sql.Driver
```

Tùy chọn này gợi ý các module cung cấp implementation cho service type. Dùng nó cùng descriptor của consumer/provider để xác định module cần đưa vào image.

## 15. Các giới hạn và lưu ý thiết kế

### 15.1. jlink không tự phát hiện mọi dependency động

Phân tích module graph dựa nhiều vào descriptor và bytecode có thể phân tích. Những trường hợp sau có thể cần cấu hình bổ sung:

- Nạp class theo tên từ file cấu hình.
- Plugin được phát hiện lúc runtime.
- Reflection hoặc framework tự tìm implementation.
- Service provider cần được bind.
- JNI/native library được nạp theo cấu hình.
- Resource được đọc bằng đường dẫn động.

Hãy chạy ứng dụng trên runtime image với các tính năng thực tế, không chỉ kiểm tra một đường đi main đơn giản.

### 15.2. jlink không thay thế hệ thống build

jlink tạo runtime image, nhưng ứng dụng vẫn cần quy trình build để:

- Biên dịch source.
- Kiểm thử.
- Đóng gói modular JAR.
- Quản lý dependency.
- Tạo launcher/runtime image.
- Đóng gói config và tài nguyên.

Có thể tích hợp lệnh jlink vào Maven, Gradle hoặc script build, nhưng cần giữ module path, JDK version và tùy chọn link nhất quán.

### 15.3. Không nên tối ưu kích thước bằng cách xóa module tùy tiện

Nếu ứng dụng cần module để chạy một tính năng, xóa module đó có thể khiến lỗi chỉ xuất hiện khi tính năng được gọi. Bắt đầu bằng module graph được resolve, sau đó dùng jdeps, JMC/log và test thực tế để xác định phần có thể loại bỏ.

### 15.4. Giữ lại khả năng chẩn đoán phù hợp

`--strip-debug` có thể làm image nhỏ hơn nhưng giảm debug information. Với ứng dụng cần hỗ trợ production, cân nhắc giữ symbol/debug metadata ở artifact riêng hoặc tạo các loại image theo môi trường. Không nên đánh đổi khả năng điều tra sự cố mà không có kế hoạch.

### 15.5. Runtime image không phải installer

jlink tạo thư mục runtime image. Việc cài đặt, tạo shortcut, đăng ký service, cấu hình biến môi trường, cập nhật và gỡ bỏ ứng dụng là phần của hệ thống đóng gói/installer riêng.

## 16. Quy trình build runtime image có thể lặp lại

Một quy trình release thường gồm:

1. Chọn bản JDK 17 cụ thể và ghi nhận vendor/build version.
2. Biên dịch ứng dụng thành explicit named module.
3. Đóng gói dependency thành modular JAR hoặc JMOD.
4. Dùng `jdeps` để phân tích module dependency.
5. Chạy ứng dụng trên module path trước khi link.
6. Chọn root modules bằng `--add-modules`.
7. Thêm `--bind-services` nếu cần service provider binding.
8. Chọn launcher và plugin tối ưu phù hợp.
9. Tạo image vào output directory mới.
10. Kiểm tra version, module list, launcher và chức năng ứng dụng.
11. Chạy test trên từng OS/architecture mục tiêu.
12. Đóng gói runtime cùng config/resource cần thiết.
13. Ghi nhận JDK build và tùy chọn jlink để tái tạo image.
14. Cập nhật và phát hành lại image khi JDK có bản vá.

Ví dụ lệnh tổng hợp:

```bash
jlink --module-path "$JAVA_HOME/jmods:mlib" --add-modules com.acme.orders --bind-services --launcher orders=com.acme.orders/com.acme.orders.Main --strip-debug --compress=2 --no-header-files --no-man-pages --output build/orders-runtime
```

Đây là cấu hình ví dụ cho ứng dụng modular. Nếu ứng dụng không dùng service provider, có thể bỏ `--bind-services`. Nếu cần debug, cân nhắc bỏ `--strip-debug`.

## 17. Bài tập thực hành

### Bài 1 — Tạo runtime image cho ứng dụng modular

Tạo module `com.acme.hello` có `module-info.java` và class `Main` in ra thông báo. Thực hiện:

1. Biên dịch module vào thư mục `mods`.
2. Chạy module bằng JDK hiện tại.
3. Dùng jlink tạo image chỉ chứa module cần thiết.
4. Chạy ứng dụng bằng `bin/java` trong image.
5. Kiểm tra `--list-modules` và ghi lại các module có trong image.

### Bài 2 — Tạo launcher riêng

Từ ứng dụng ở Bài 1, dùng `--launcher hello=com.acme.hello/com.acme.hello.Main`. Chạy launcher từ image mà không nhập lại module name và main class.

### Bài 3 — Phân tích dependency bằng jdeps

Thêm một dependency modular vào ứng dụng. Dùng:

```bash
jdeps --print-module-deps --module-path "$JAVA_HOME/jmods:mlib" --recursive mlib/com.acme.hello.jar
```

Đối chiếu kết quả với các chỉ thị `requires` trong descriptor. Sau đó tạo image và giải thích vì sao module dependency được đưa vào.

### Bài 4 — Xử lý thư viện chưa modular hóa

Cho một JAR không có `module-info.class`:

1. Đặt JAR trên module path và thử dùng jlink.
2. Ghi nhận lỗi automatic module không được hỗ trợ.
3. Dùng `jdeps --generate-module-info` để tạo descriptor khởi đầu.
4. Chỉnh descriptor, biên dịch và đóng gói thành modular JAR.
5. Thử link lại.

Giải thích vì sao JAR chạy được trên classpath hoặc automatic module không có nghĩa nó link được trực tiếp bằng jlink.

### Bài 5 — Dùng service provider

Tạo một service interface, một consumer module khai báo `uses` và một provider module khai báo `provides ... with ...`. Tạo image:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.consumer --bind-services --output build/service-runtime
```

Chạy ứng dụng và xác nhận provider được tìm thấy. Thử bỏ `--bind-services` rồi quan sát khác biệt trong image.

### Bài 6 — So sánh kích thước image

Tạo các image với:

- Không nén.
- `--compress=2`.
- `--strip-debug --no-header-files --no-man-pages`.

So sánh dung lượng và kiểm tra ứng dụng vẫn chạy đúng. Ghi nhận lựa chọn nào phù hợp với yêu cầu triển khai.

### Bài 7 — Phân phối ứng dụng classpath

Với một ứng dụng chưa modular hóa, dùng `jdeps` để tìm các module JDK cần thiết, tạo runtime image chỉ từ JMOD của JDK và chạy JAR bằng `-cp`. Giải thích phần nào được jlink đưa vào image và phần nào vẫn phải phân phối riêng.

### Bài 8 — Tạo image cho nhiều nền tảng

Tạo runtime image cho hai môi trường khác nhau (ví dụ Windows x64 và Linux x64) bằng JDK/JMOD đúng nền tảng. Kiểm tra launcher, native dependency và cách đóng gói cho từng môi trường.

## 18. Tài liệu chính thức của Java 17

- [Java 17 jlink command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jlink.html): cú pháp, module path, root modules, launcher và các tùy chọn liên kết.
- [Java 17 jdeps command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html): phân tích dependency và tạo module descriptor ban đầu.
- [Java 17 jmod command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jmod.html): mô tả và tạo JMOD.
- [Java 17 jar command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html): tạo và kiểm tra modular JAR.
- [Java Language Specification 17 — Modules](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html): module declaration, requires, exports, uses và provides.
- [JEP 282 — jlink: The Java Linker](https://openjdk.org/jeps/282): mục tiêu thiết kế và chức năng của công cụ jlink.
- [Java Platform Module System — Module Resolution](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html): quy tắc module declaration và phụ thuộc module.

**Ghi nhớ:** jlink tạo runtime image tùy chỉnh từ các module tường minh và dependency được resolve. Bắt đầu bằng module descriptor đúng, phân tích dependency bằng jdeps, chỉ định root modules với `--add-modules`, thêm `--bind-services` khi cần provider, rồi tạo launcher và chọn plugin tối ưu phù hợp. Runtime image là gói chạy theo nền tảng, không phải native executable độc lập hay JDK đầy đủ. Hãy kiểm tra module list, chạy ứng dụng trên image, phân phối đúng OS/architecture và rebuild runtime khi JDK 17 có bản cập nhật bảo mật.
