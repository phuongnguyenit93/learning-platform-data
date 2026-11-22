# Xử lý reflection, service loader và resource lookup

## 1. Vì sao ba cơ chế này cần được xem lại khi modular hóa?

Khi chuyển một ứng dụng từ classpath sang Java Platform Module System (JPMS), mã nguồn có thể vẫn biên dịch được nhưng một số chức năng khám phá hoặc truy cập tài nguyên lại thay đổi hành vi. Những điểm dễ bị ảnh hưởng gồm:

- Framework dùng reflection để đọc field private, gọi constructor hoặc tạo proxy.
- Ứng dụng tìm plugin hoặc implementation bằng **ServiceLoader**.
- Mã nguồn đọc file cấu hình, template, schema hoặc metadata nằm bên trong JAR.
- Thư viện quét package bằng cách liệt kê tài nguyên qua classloader.
- Ứng dụng nạp class hoặc module theo tên lấy từ cấu hình.

Trên classpath truyền thống, nhiều thư viện giả định rằng mọi JAR đều nằm trong một không gian tìm kiếm tương đối phẳng. Với named module, JPMS bổ sung ranh giới readability, exports, opens và module layer. Vì vậy, việc một class hoặc resource tồn tại trong JAR không đảm bảo mọi module khác đều có thể tìm thấy hoặc truy cập nó.

Cần phân biệt ba việc:

1. **Discovery:** tìm implementation, class hoặc resource.
2. **Loading:** nạp class hoặc tạo instance.
3. **Access:** được phép gọi API, đọc thành viên hoặc mở nội dung resource.

Một lỗi ở bước này không nhất thiết được sửa bằng cách mở quyền ở bước khác. Ví dụ, **opens** có thể cho phép deep reflection nhưng không tự đăng ký provider cho ServiceLoader; **uses** giúp khai báo service consumer nhưng không làm package của provider trở thành API public.

## 2. Kiểm kê các điểm phụ thuộc trước khi chuyển đổi

Trước khi thêm module descriptor, hãy tìm các cơ chế động trong ứng dụng và thư viện:

- Các lệnh **Class.forName**, **getDeclaredField**, **getDeclaredMethod**, **setAccessible** hoặc **trySetAccessible**.
- Các lời gọi **ServiceLoader.load** và file **META-INF/services**.
- Các lời gọi **Class.getResource**, **getResourceAsStream**, **ClassLoader.getResource** hoặc **getResourceAsStream**.
- Framework có package scanning, annotation scanning, plugin registry hoặc cấu hình tên class.
- Tên class, tên module và đường dẫn resource được tạo từ chuỗi cấu hình.
- Plugin được nạp trong module layer riêng hoặc classloader tùy chỉnh.

Phân loại từng điểm theo mục đích. Nếu tìm implementation của một SPI, ServiceLoader thường là cơ chế phù hợp. Nếu framework cần truy cập field private, hãy xác định package cần mở. Nếu chỉ đọc file cấu hình, hãy dùng API resource đúng với module chứa file đó.

Công cụ phân tích bytecode như **jdeps** có thể hỗ trợ tìm phụ thuộc tĩnh và một số tham chiếu tới API nội bộ, nhưng không thể suy ra đầy đủ tên class được tạo động, resource path lấy từ cấu hình hoặc mọi hành vi reflection. Các điểm này cần được xác nhận qua mã nguồn, cấu hình và kiểm thử.

## 3. Reflection trong named module

Reflection vẫn hoạt động trong JPMS, nhưng quyền truy cập phụ thuộc vào ranh giới module.

### Truy cập API public

Nếu module thư viện muốn công khai kiểu cho module khác, nó cần export package:

~~~java
module com.example.model {
    exports com.example.model.api;
}
~~~

Module framework cần đọc module đó:

~~~java
module com.example.framework {
    requires com.example.model;
}
~~~

Framework có thể gọi các phương thức public được export. Đây là truy cập Java thông thường và không yêu cầu mở package cho deep reflection.

### Deep reflection vào thành viên private

Giả sử framework cần đọc field private trong entity:

~~~java
Field field = Customer.class.getDeclaredField("email");

if (!field.trySetAccessible()) {
    throw new IllegalStateException(
        "Package is not open for deep reflection"
    );
}

String email = (String) field.get(customer);
~~~

Nếu package chứa **Customer** chưa mở cho module framework, **trySetAccessible()** có thể trả về false. Nếu gọi **setAccessible(true)** trực tiếp, JVM có thể ném **InaccessibleObjectException**.

Module sở hữu entity có thể mở đúng package cho framework:

~~~java
module com.example.model {
    exports com.example.model.api;

    opens com.example.model.entity
        to com.example.framework;
}
~~~

**exports** cho phép truy cập các kiểu public; **opens** cho phép reflection sâu vào package. Mở package có mục tiêu giúp giữ các package implementation khác được đóng gói.

Nếu framework chạy từ classpath và thuộc unnamed module, có thể mở package khi khởi chạy:

~~~bash
java \
  --add-opens com.example.model/com.example.model.entity=ALL-UNNAMED \
  -jar app.jar
~~~

Nếu framework là named module, thay **ALL-UNNAMED** bằng tên module cụ thể. **--add-opens** là tùy chọn của Java launcher tại runtime; nó không thay thế khai báo API và không phải tùy chọn sửa lỗi cho javac.

### MethodHandles và proxy

Một số framework dùng **MethodHandles.privateLookupIn** để tạo quyền truy cập vào thành viên không public. Cơ chế này cũng chịu quy tắc đóng gói module. Package của class đích cần được mở phù hợp cho module chứa lookup caller.

Với proxy và reflection, hãy kiểm tra framework đang tạo proxy qua interface public, subclass hay truy cập implementation private. Không phải mọi lỗi proxy đều cần mở toàn bộ module. Có thể chỉ cần export API interface hoặc mở một package model cụ thể.

### Không dùng reflection để truy cập API nội bộ của JDK

Nếu thư viện truy cập package nội bộ như **sun.*** hoặc field private trong module JDK, ưu tiên nâng cấp thư viện và chuyển sang API công khai. Strong encapsulation của các module JDK bảo vệ implementation nội bộ khỏi việc phụ thuộc không ổn định.

Có thể dùng:

~~~bash
jdeps --jdk-internals path/to/library.jar
~~~

để tìm một số tham chiếu tĩnh tới API nội bộ. Kết quả không thay thế việc kiểm tra các đường gọi reflection động.

## 4. ServiceLoader trong JPMS

ServiceLoader cung cấp cơ chế tìm implementation theo một hợp đồng service đã khai báo. Cơ chế này phù hợp với SPI, plugin và các extension point mà consumer không muốn phụ thuộc trực tiếp vào từng implementation.

Giả sử module API cung cấp service interface:

~~~java
package com.example.spi;

public interface PaymentProvider {
    String name();
    void pay(int amount);
}
~~~

Module API export package chứa interface:

~~~java
module com.example.payment.api {
    exports com.example.spi;
}
~~~

Module consumer khai báo **uses**:

~~~java
module com.example.payment.app {
    requires com.example.payment.api;

    uses com.example.spi.PaymentProvider;
}
~~~

Module provider khai báo implementation:

~~~java
module com.example.payment.card {
    requires com.example.payment.api;

    provides com.example.spi.PaymentProvider
        with com.example.payment.card.CardPaymentProvider;
}
~~~

Sau đó consumer tìm provider:

~~~java
ServiceLoader<PaymentProvider> providers =
    ServiceLoader.load(PaymentProvider.class);

for (PaymentProvider provider : providers) {
    provider.pay(100);
}
~~~

Trong named module, module gọi ServiceLoader phải khai báo **uses** cho service. Module provider khai báo **provides ... with ...** trong module descriptor. Service interface cần được export để consumer có thể đọc và sử dụng kiểu đó.

Nếu ứng dụng sử dụng một **ModuleLayer** riêng để nạp plugin, có thể tìm provider trong layer đó:

~~~java
ServiceLoader<PaymentProvider> providers =
    ServiceLoader.load(pluginLayer, PaymentProvider.class);
~~~

Điều này quan trọng với ứng dụng có plugin module được nạp động. Gọi **ServiceLoader.load(PaymentProvider.class)** và tìm provider trong một layer riêng là hai phạm vi khác nhau; hãy dùng layer đúng với nơi plugin được định nghĩa.

### Provider trên classpath

Ứng dụng chưa modular vẫn có thể dùng ServiceLoader. Provider trên classpath được đăng ký trong file:

~~~text
META-INF/services/com.example.spi.PaymentProvider
~~~

File chứa tên đầy đủ của từng provider, mỗi dòng một class:

~~~text
com.example.payment.card.CardPaymentProvider
com.example.payment.wallet.WalletPaymentProvider
~~~

Khi chuyển provider thành named module, metadata này thường được chuyển thành khai báo **provides** trong **module-info.java**. Không nên vừa duy trì hai cách đăng ký cho cùng một provider nếu không có nhu cầu tương thích rõ ràng.

### Kiểm tra provider không được tìm thấy

Nếu ServiceLoader không trả về provider, kiểm tra lần lượt:

1. Consumer có khai báo **uses** đúng service type không?
2. Provider module có khai báo **provides** đúng interface không?
3. Provider module có nằm trong module path hoặc module layer đang được tìm kiếm không?
4. Service interface có cùng tên module và package mà consumer/provider cùng tham chiếu không?
5. Nếu provider nằm trên classpath, file **META-INF/services** có đúng đường dẫn và tên class không?
6. Nếu dùng layer tùy chỉnh, lời gọi ServiceLoader có sử dụng đúng layer không?

ServiceLoader không quét mọi class có annotation hoặc mọi class implement một interface. Nó sử dụng metadata service đã đăng ký. Nếu ứng dụng đang dùng package scanning để tìm plugin, hãy quyết định rõ có thể chuyển sang SPI/ServiceLoader hay framework vẫn cần scanner riêng.

## 5. Resource lookup trong named module

Resource có thể là file properties, XML, JSON, template, schema, ảnh hoặc metadata nằm trong JAR. Khi chuyển sang module, cần xác định resource thuộc package nào và module nào sẽ đọc nó.

### Dùng Class.getResourceAsStream

Nếu resource nằm cùng package với class, dùng đường dẫn tương đối:

~~~java
InputStream input =
    ConfigReader.class.getResourceAsStream("config.properties");
~~~

Tên resource không có dấu **/** ở đầu nên được hiểu tương đối với package của class.

Có thể dùng đường dẫn tuyệt đối từ gốc module:

~~~java
InputStream input =
    ConfigReader.class.getResourceAsStream(
        "/com/example/config/config.properties"
    );
~~~

Cách này gắn việc tìm resource với class cụ thể, hữu ích khi resource thuộc cùng module với code sử dụng nó.

### Dùng Module.getResourceAsStream

Có thể truy cập trực tiếp module chứa class:

~~~java
Module module = ConfigReader.class.getModule();

try (InputStream input =
         module.getResourceAsStream(
             "com/example/config/config.properties")) {
    if (input == null) {
        throw new IllegalStateException("Resource not found");
    }
    // Read the resource
}
~~~

Tên resource được truyền theo dạng đường dẫn từ gốc module, phân tách bằng dấu gạch chéo. API module giúp code xác định rõ resource được tìm trong module nào.

Trong named module, resource nằm trong package không được mở có thể bị đóng gói đối với module khác. Nếu một module framework cần đọc resource nội bộ của module ứng dụng, hãy mở package chứa resource cho caller phù hợp:

~~~java
module com.example.app {
    opens com.example.app.config
        to com.example.framework;
}
~~~

Mở package cũng ảnh hưởng đến quyền deep reflection vào package đó. Vì vậy, hãy đặt resource trong package phù hợp và chỉ mở cho module cần đọc.

### Dùng ClassLoader

Ứng dụng trên classpath thường dùng:

~~~java
InputStream input =
    Thread.currentThread()
          .getContextClassLoader()
          .getResourceAsStream("config/app.properties");
~~~

Cách này vẫn hữu ích với thư viện cần tôn trọng context classloader của ứng dụng hoặc container. Tuy nhiên, không nên giả định rằng classloader lookup sẽ liệt kê được mọi resource được đóng gói trong named module. Resource trong named module chịu quy tắc đóng gói của JPMS; hành vi tìm kiếm còn phụ thuộc vị trí resource và module.

Nếu resource thuộc module cụ thể, ưu tiên **Class.getResourceAsStream** hoặc **Module.getResourceAsStream** để xác định rõ module sở hữu resource.

### Resource không nên được đóng gói như cấu hình triển khai

File cấu hình có thể cần thay đổi giữa development, staging và production. Nếu file phải được vận hành viên chỉnh sửa sau khi build, hãy cân nhắc đọc từ filesystem, biến môi trường hoặc hệ thống cấu hình triển khai thay vì đóng gói cố định bên trong module.

Resource nội bộ phù hợp với dữ liệu mặc định, template hoặc schema được phân phối cùng ứng dụng. Cấu hình bí mật và thông tin môi trường không nên được nhúng trong JAR.

## 6. Package scanning và giới hạn của classloader

Một số framework tìm class bằng cách gọi **ClassLoader.getResources("com/example/plugins")**, duyệt URL trả về rồi liệt kê file class trong thư mục hoặc JAR. Cách này thường hoạt động trên classpath nhưng không phải là mô hình discovery tổng quát cho named module.

Trên module path:

- Module có thể không được biểu diễn như một thư mục/JAR có thể duyệt theo cách scanner classpath giả định.
- Resource và package trong named module có thể bị đóng gói.
- Một classloader có thể không đại diện cho tất cả module layer.
- Plugin có thể được nạp từ layer riêng hoặc ModuleFinder riêng.
- Tên class được tạo từ cấu hình có thể không xuất hiện trong kết quả quét tĩnh.

Nếu framework cần package scanning, hãy chọn phiên bản có hỗ trợ JPMS và kiểm tra cách framework duyệt module. Framework có thể dùng API module, module layer hoặc **ModuleReader** để đọc nội dung module. Không nên tự giả định rằng liệt kê URL của system classloader là đủ.

Khi xây dựng một hệ thống plugin mới, ServiceLoader thường dễ tích hợp với JPMS hơn nếu mỗi plugin cung cấp một SPI rõ ràng. Nếu framework cần quét annotation cho nhiều loại component, hãy kiểm tra tài liệu framework về module path, opens và resource scanning.

## 7. Kết hợp reflection, ServiceLoader và resource lookup

Một plugin modular có thể dùng cả ba cơ chế theo một quy trình rõ ràng:

1. Module consumer khai báo **uses** cho SPI.
2. Module provider khai báo **provides** với implementation.
3. ServiceLoader tìm provider trong module layer thích hợp.
4. Framework đọc metadata hoặc resource của provider bằng API module-aware.
5. Nếu cần deep reflection vào implementation, provider module mở đúng package cho framework.
6. Các resource cần truy cập từ bên ngoài được mở có mục tiêu hoặc được cung cấp qua API public.

Ví dụ consumer:

~~~java
module com.example.host {
    requires com.example.plugin.api;

    uses com.example.plugin.api.Plugin;
}
~~~

Provider:

~~~java
module com.example.plugin.csv {
    requires com.example.plugin.api;

    provides com.example.plugin.api.Plugin
        with com.example.plugin.csv.CsvPlugin;

    opens com.example.plugin.csv.config
        to com.example.framework;
}
~~~

Trong ví dụ này, ServiceLoader tìm **CsvPlugin** theo khai báo provider. Framework có thể đọc cấu hình trong package **com.example.plugin.csv.config** nếu resource được đặt ở đó và quyền mở package phù hợp. Nếu framework chỉ gọi các phương thức public của Plugin, không cần mở package implementation cho deep reflection.

Không nên dùng reflection scan thay cho ServiceLoader nếu chỉ cần tìm provider đã đăng ký. Cũng không nên thêm **opens** cho toàn bộ module nếu framework chỉ cần đọc một package cấu hình.

## 8. Quy trình chuyển đổi từ classpath sang JPMS

Có thể thực hiện theo các bước:

1. **Kiểm kê:** tìm mọi điểm reflection, ServiceLoader, resource lookup, package scan và dynamic class loading.
2. **Phân loại:** xác định điểm nào là SPI, điểm nào cần deep reflection và điểm nào chỉ đọc resource.
3. **Tách API:** đưa service interface vào module API có package được export.
4. **Đăng ký provider:** thêm **uses** vào consumer và **provides ... with ...** vào provider module.
5. **Giới hạn reflection:** dùng API public khi có thể; nếu cần deep reflection, mở đúng package cho đúng framework module.
6. **Chuyển resource:** dùng Class hoặc Module API cho resource nội bộ; dùng filesystem/configuration service cho cấu hình triển khai.
7. **Kiểm tra framework:** xác nhận scanner và classloader có hỗ trợ named module và module layer.
8. **Kiểm tra module graph:** xác nhận tất cả module và service provider có mặt trên module path hoặc layer cần thiết.
9. **Kiểm thử artifact đã đóng gói:** chạy từ modular JAR hoặc runtime image, không chỉ chạy từ IDE.
10. **Kiểm thử đường chạy động:** thử plugin, reflection, resource, cấu hình và các tính năng chỉ được kích hoạt trong môi trường triển khai.

Có thể giữ một số thư viện cũ trên classpath trong giai đoạn chuyển đổi, nhưng cần xác định rõ module nào thuộc unnamed module và module nào là named module. Khi đã chuyển thư viện sang module path, hãy kiểm tra lại resource scanning và quyền truy cập vì hành vi có thể thay đổi.

## 9. Các lỗi thường gặp

**Class được tìm thấy nhưng setAccessible thất bại**

Kiểm tra module sở hữu class và package đang chứa thành viên private. Dùng **opens package to framework.module** hoặc **--add-opens** ở runtime nếu cần deep reflection.

**ServiceLoader không tìm thấy provider**

Kiểm tra **uses**, **provides**, module path và module layer. Nếu provider ở classpath, kiểm tra file **META-INF/services**.

**Resource tồn tại trong JAR nhưng getResourceAsStream trả về null**

Kiểm tra tên resource, đường dẫn tương đối hay tuyệt đối, module sở hữu resource và package encapsulation. Nếu caller ở module khác, package có thể cần được mở cho caller.

**Package scanner không thấy class trong named module**

Kiểm tra framework có hỗ trợ JPMS/module layer hay chỉ quét URL của classpath. Có thể chuyển extension point sang ServiceLoader hoặc dùng scanner module-aware.

**Hoạt động trong IDE nhưng thất bại khi chạy JAR**

IDE có thể chạy ứng dụng bằng classpath hoặc thêm các quyền truy cập riêng. Hãy kiểm thử bằng đúng lệnh module path và module descriptor sẽ dùng khi triển khai.

**Plugin chạy trên module path nhưng không chạy trong runtime image**

Module provider có thể chưa được đưa vào image, hoặc provider được tìm bằng cấu hình/reflection thay vì metadata service. Kiểm tra **jlink --bind-services**, **--add-modules** và module layer khi khởi chạy.

## 10. Ghi nhớ

- **Reflection** cần phân biệt truy cập public với deep reflection; **exports** và **opens** có mục đích khác nhau.
- **ServiceLoader** dựa trên **uses** và **provides** trong named module, hoặc **META-INF/services** trên classpath.
- **ModuleLayer** quan trọng khi plugin được nạp động trong layer riêng.
- **Class.getResourceAsStream** và **Module.getResourceAsStream** giúp xác định rõ module chứa resource.
- Resource trong package của named module có thể bị đóng gói; mở package có mục tiêu khi module khác cần đọc.
- Classpath package scanning không tự động tương đương với scanning trên module path.
- Kiểm thử phải bao gồm artifact modular và các đường chạy động thực tế.

Khi chuyển sang JPMS, hãy mô tả rõ provider bằng service metadata, cấp quyền reflection theo package và chọn API resource phù hợp với module sở hữu file. Ba thay đổi này giúp ứng dụng giữ được chức năng plugin, framework và cấu hình mà vẫn tôn trọng ranh giới đóng gói của module.
