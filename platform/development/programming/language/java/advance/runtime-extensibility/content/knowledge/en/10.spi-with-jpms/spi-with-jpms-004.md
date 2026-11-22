# Khai báo provides ... with ... và giữ package triển khai được đóng gói trong JPMS

## 1. Bài toán: công bố khả năng mở rộng mà không công khai implementation

Trong ứng dụng Java dùng **Java Platform Module System (JPMS)**, host cần gọi một **Service Provider Interface (SPI)**, còn các module độc lập cung cấp implementation. Host phải khám phá và sử dụng provider mà không cần import class triển khai. Đồng thời, nhà phát triển provider muốn giữ các package nội bộ khỏi việc bị module khác phụ thuộc trực tiếp.

JPMS hỗ trợ mô hình này qua hai nhóm khai báo trong **module-info.java**:

- **provides <Service> with <Provider>**: module cung cấp khai báo nó triển khai service nào bằng những provider nào.
- **uses <Service>**: module tiêu thụ cho biết mã bên trong có thể khám phá service đó bằng **java.util.ServiceLoader**.

Chỉ **package chứa giao diện SPI hoặc các kiểu public trong hợp đồng** mới cần được export cho bên sử dụng. **Package chứa class triển khai có thể giữ nguyên không export, không open**, dù bản thân provider class cần đáp ứng điều kiện public của cơ chế ServiceLoader.

Điểm mấu chốt: **đăng ký provider không đồng nghĩa với export implementation package**. JPMS có đường truy cập riêng được kiểm soát cho việc tìm và khởi tạo service provider. Nhờ đó, module khác có thể nhận một đối tượng qua interface dùng chung mà không có quyền import hoặc tùy tiện reflection vào implementation.

## 2. Phân vai ba module và ranh giới phụ thuộc

Một cấu trúc cơ bản:

~~~text
ext.api
  └── exports ext.api
          ^
          | requires
          |
ext.app                 ext.provider
  ├── requires ext.api     ├── requires ext.api
  ├── uses ext.api.Greeting├── provides ext.api.Greeting
  └── ServiceLoader       │     with ext.provider.internal.GreetingImpl
                          └── KHÔNG exports/opens ext.provider.internal
~~~

Ba module có vai trò riêng:

| Module | Chứa gì? | Khai báo cốt lõi |
| --- | --- | --- |
| **ext.api** | Interface Greeting và các kiểu dữ liệu hợp đồng | **exports ext.api** |
| **ext.provider** | Lớp GreetingImpl và chi tiết xử lý | **requires ext.api**; **provides ... with ...**; không exports package implementation |
| **ext.app** | Host tiêu thụ SPI, chọn và gọi provider | **requires ext.api**; **uses ext.api.Greeting** |

Host **không cần requires ext.provider** và không cần biết tên class GreetingImpl tại compile time. Thay implementation hoặc thêm provider module khác không buộc host sửa import hay module descriptor, miễn cùng đáp ứng SPI đã công bố.

**requires** điều khiển khả năng đọc module (readability); **exports** điều khiển khả năng truy cập public type của một package; **uses/provides** điều khiển đăng ký và khám phá service. Các cơ chế này bổ sung nhau, không thay thế nhau.

## 3. Chính xác provides ... with ... khai báo điều gì?

Trong **module-info.java** của module provider:

~~~java
module ext.provider {
    requires ext.api;

    provides ext.api.Greeting
        with ext.provider.internal.GreetingImpl;
}
~~~

Đọc theo từng thành phần:

1. **module ext.provider**: đây là named module chứa provider.
2. **requires ext.api**: provider biên dịch được khi tham chiếu interface Greeting, nằm trong package **ext.api** đã export.
3. **provides ext.api.Greeting**: module thông báo mình cung cấp implementation cho đúng kiểu service này.
4. **with ext.provider.internal.GreetingImpl**: chỉ định lớp provider; tên này phải có thể được compiler nhận diện trong **chính module ext.provider**.
5. Không có **exports ext.provider.internal** và cũng không có **opens ext.provider.internal**: package triển khai giữ được tính đóng gói mạnh đối với module khác.

Không viết **provides** trong module giao diện để công bố một provider nằm trong một module khác. Provider type nêu sau **with** phải được khai báo trong chính module chứa chỉ thị provides. Một module có thể dùng nhiều provider cho cùng một service:

~~~java
// Mảnh module-info.java minh họa khi có đủ hai implementation trong cùng module.
provides ext.api.Greeting
    with ext.provider.internal.GreetingImpl,
         ext.provider.internal.AlternativeGreeting;
~~~

Ví dụ nhiều provider không phải chương trình độc lập; AlternativeGreeting cần được định nghĩa và hợp lệ trước khi biên dịch. Không được lặp lại cùng một service trong hai chỉ thị provides riêng của cùng module, hoặc lặp cùng một provider trong cùng danh sách.

**Chỉ thị provides không có nghĩa một object đã được khởi tạo ngay khi JVM khởi động.** Module descriptor mang thông tin để cơ chế service binding/discovery tìm provider; ServiceLoader thường tìm và tạo instance khi được duyệt đến.

## 4. Vì sao implementation class có thể public nhưng package vẫn ẩn?

Java có hai tầng truy cập cần phân biệt:

- **public class**: class có mức truy cập public trong ngôn ngữ Java. Đây là một điều kiện để một kiểu được ghi sau **with** làm provider của named module.
- **exports package**: module cho phép mã thuộc những module phù hợp truy cập các public type trong package đó, tùy quy tắc readability.

Vì vậy có thể khai báo:

~~~java
package ext.provider.internal;

import ext.api.Greeting;

public final class GreetingImpl implements Greeting {
    public GreetingImpl() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Dù GreetingImpl là **public**, mã trong ext.app **không được import trực tiếp ext.provider.internal.GreetingImpl** khi ext.provider không export package tương ứng. Nếu cố sửa host để dùng implementation, compiler sẽ từ chối theo ranh giới module, ngay cả khi thêm **requires ext.provider** nhưng vẫn không có exports phù hợp.

Ngược lại, ServiceLoader có cơ chế chuyên biệt để tạo provider được ghi trong module descriptor, ngay cả khi package của provider **không export** cho module gọi. Đây là tính năng có chủ đích của JPMS chứ không phải việc ServiceLoader tự ý vượt qua kiểm soát truy cập bằng reflection thông thường.

Có thể giữ các class trợ giúp trong package không export ở quyền truy cập package-private. Tuy nhiên lớp provider được khai báo trực tiếp trong **provides ... with ...** phải là public top-level hoặc public static nested type hợp lệ. Đừng biến provider class thành package-private rồi mong việc không export package sẽ thay thế điều kiện public.

## 5. Exports, opens, requires, uses và provides khác nhau ở đâu?

| Chỉ thị | Đặt trong module nào? | Công dụng | Có cần cho ví dụ này? |
| --- | --- | --- | --- |
| **exports ext.api** | ext.api | Cho module khác dùng public interface/DTO của API | Có |
| **requires ext.api** | ext.app và ext.provider | Cho phép mã trong module đọc module API | Có |
| **uses ext.api.Greeting** | ext.app | Công bố module chứa code gọi ServiceLoader cho Greeting | Có |
| **provides ext.api.Greeting with ...** | ext.provider | Đăng ký provider nằm trong module này | Có |
| **exports ext.provider.internal** | ext.provider | Công khai public type implementation cho module khác | Không; nên tránh |
| **opens ext.provider.internal** | ext.provider | Cho phép deep reflection vào package theo phạm vi khai báo | Không cần |
| **open module ext.provider** | ext.provider | Mở các package của toàn module cho deep reflection | Không cần; làm yếu encapsulation |

**Exports** chủ yếu phục vụ truy cập public type và member theo quy tắc module. **Opens** cho phép reflective access theo mức được cấp; không tương đương với export dùng cho import thông thường. Một package không exports vẫn có thể bị mở cho reflection nếu được khai báo opens, vì vậy giữ encapsulation thật sự thường có nghĩa là **không exports và không opens package implementation**.

Nếu một framework bên ngoài thực sự cần reflection, có thể cân nhắc **opens package to framework.module** chỉ cho module cụ thể, nhưng đó là quyết định riêng về quyền truy cập. **ServiceLoader không đòi hỏi opens package provider**. Tránh thêm opens theo phản xạ chỉ để xử lý lỗi khởi tạo provider: cần kiểm tra điều kiện provider, khai báo provides, việc resolve module và mã constructor/provider method trước.

**Qualified exports** như **exports ext.api to ext.app, ext.provider** giới hạn người dùng interface, nhưng phải bảo đảm tất cả module tiêu thụ thực sự được phép. Với SPI public dành cho nhiều nhà phát triển plugin, exports ext.api thường dễ phát triển hơn.

## 6. Ví dụ Java 17 hoàn chỉnh: ServiceLoader dùng provider từ package không export

Ví dụ gồm ba **explicit named modules**. Một module sở hữu interface, một module khai báo provider, một module host duyệt ServiceLoader. Mã có thể biên dịch với **javac --release 17** và chạy từ JDK 17 trở lên.

### 6.1. Cấu trúc tệp

~~~text
demo/
├── src/
│   ├── ext.api/
│   │   ├── module-info.java
│   │   └── ext/api/Greeting.java
│   ├── ext.provider/
│   │   ├── module-info.java
│   │   └── ext/provider/internal/GreetingImpl.java
│   └── ext.app/
│       ├── module-info.java
│       └── ext/app/Main.java
└── mods/                           # Sinh ra khi biên dịch
    ├── ext.api/
    ├── ext.provider/
    └── ext.app/
~~~

Các tên sau **src/** là tên module theo chuẩn **--module-source-path**. Package implementation cố ý đặt tên **ext.provider.internal** để nhắc rằng code của host không nên phụ thuộc trực tiếp vào nó; chữ "internal" chỉ mang ý nghĩa quy ước, còn tính đóng gói thực sự do **module-info.java** quyết định.

### 6.2. Module chứa SPI công khai

**src/ext.api/module-info.java**

~~~java
module ext.api {
    exports ext.api;
}
~~~

**src/ext.api/ext/api/Greeting.java**

~~~java
package ext.api;

public interface Greeting {
    String greet(String name);
}
~~~

ext.api chỉ export interface cần thiết. Các kiểu khác không thuộc hợp đồng có thể đặt vào package khác và không export.

### 6.3. Module provider đăng ký service nhưng giấu package triển khai

**src/ext.provider/module-info.java**

~~~java
module ext.provider {
    requires ext.api;

    provides ext.api.Greeting
        with ext.provider.internal.GreetingImpl;
}
~~~

**src/ext.provider/ext/provider/internal/GreetingImpl.java**

~~~java
package ext.provider.internal;

import ext.api.Greeting;

public final class GreetingImpl implements Greeting {
    public GreetingImpl() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Hãy để ý **không có** dòng exports hoặc opens cho ext.provider.internal. Lớp GreetingImpl vẫn public và có public constructor không tham số; điều này phục vụ cơ chế provider constructor của ServiceLoader, không biến package thành API cho host.

### 6.4. Module ứng dụng chỉ phụ thuộc SPI

**src/ext.app/module-info.java**

~~~java
module ext.app {
    requires ext.api;
    uses ext.api.Greeting;
}
~~~

**src/ext.app/ext/app/Main.java**

~~~java
package ext.app;

import ext.api.Greeting;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        int count = 0;

        for (Greeting service : ServiceLoader.load(Greeting.class)) {
            System.out.println("Service: " + service.greet("Java"));
            System.out.println("Provider module: " +
                    service.getClass().getModule().getName());
            System.out.println("Provider package exported: " +
                    service.getClass().getModule().isExported(
                            "ext.provider.internal", Main.class.getModule()));
            System.out.println("Provider package open: " +
                    service.getClass().getModule().isOpen(
                            "ext.provider.internal", Main.class.getModule()));
            count++;
        }

        System.out.println("Providers: " + count);
    }
}
~~~

Main không import GreetingImpl. Nó chỉ biết **Greeting** và ServiceLoader. Sau khi nhận object, Main có thể gọi các phương thức của giao diện Greeting. Việc **getClass()** và **getModule()** cho phép quan sát thông tin mô tả runtime; không trao quyền import hoặc truy cập trực tiếp thành viên riêng của implementation.

### 6.5. Biên dịch và chạy

Đứng tại thư mục **demo/** đã tạo theo cấu trúc trên. Lệnh sau biên dịch cả ba module trong một lần gọi; javac sẽ tạo thư mục **mods**:

~~~bash
javac --release 17 --module-source-path src -d mods -m ext.api,ext.provider,ext.app
~~~

Khởi chạy ứng dụng với **module path**. Trong ví dụ này, **--add-modules ext.provider** bảo đảm module provider được resolve ở runtime, còn **-m ext.app/ext.app.Main** chỉ rõ module và class main:

~~~bash
java --module-path mods --add-modules ext.provider -m ext.app/ext.app.Main
~~~

Hai lệnh trên dùng được với terminal Windows, Linux và macOS khi JDK nằm trên PATH; không có dấu phân cách classpath phụ thuộc hệ điều hành vì **mods** chỉ là một module-path entry.

**Standard output chính xác:**

~~~text
Service: Hello, Java!
Provider module: ext.provider
Provider package exported: false
Provider package open: false
Providers: 1
~~~

Giải thích kết quả:

1. **Service: Hello, Java!** cho thấy host đã nhận và sử dụng object thực thi Greeting, dù không import lớp triển khai.
2. **Provider module: ext.provider** xác nhận instance thực tế đến từ named module provider.
3. **Provider package exported: false** chứng minh ext.provider.internal không được export cho module ext.app.
4. **Provider package open: false** chứng minh package cũng không được mở cho deep reflection của ext.app.
5. **Providers: 1** vì ví dụ chỉ khai báo một provider cho Greeting.

Đây là sự kiểm chứng quan trọng: **ServiceLoader vẫn khởi tạo provider thành công trong khi package implementation không export và không open**.

Lệnh --add-modules trong ví dụ giúp việc resolve provider có kết quả rõ ràng. Trên cấu hình JPMS hỗ trợ service binding, provider có thể được đưa vào module graph qua việc resolve service mà không cần flag này; không nên phụ thuộc vào một giả định ngầm khi chuyển sang custom ModuleLayer, image đóng gói riêng hoặc môi trường launch khác.

## 7. Vì sao app cần uses nhưng không cần requires provider?

**uses ext.api.Greeting** thuộc **module chứa code gọi ServiceLoader**. Trong ví dụ, Main gọi trực tiếp ServiceLoader.load(Greeting.class), nên **ext.app** khai báo uses.

Nếu chuyển toàn bộ logic ServiceLoader sang một thư viện/module độc lập, chính module thực hiện lời gọi này cần có uses theo hợp đồng Java; không tự động suy ra uses của một module khác chỉ vì nó gọi thư viện.

**requires ext.api** vẫn cần thiết vì ext.app trực tiếp tham chiếu Greeting trong source. Nhưng **requires ext.provider** không cần để duyệt provider. Nếu thêm requires ext.provider, app tạo ra quan hệ phụ thuộc module không mong muốn; thậm chí khi đọc được module provider, app vẫn không thể import ext.provider.internal vì package đó không export.

Đây là ưu điểm của service binding: consumer phụ thuộc **hợp đồng**, không phụ thuộc tên implementation. Module provider có thể đổi hoặc có thêm nhiều provider. Số lượng và thứ tự provider không nên dùng làm hợp đồng nghiệp vụ nếu hệ thống không kiểm soát đầy đủ cấu hình/nguồn khám phá.

**Khi không tìm được provider**, ServiceLoader có thể duyệt ra không phần tử mà không ném lỗi. Cần phân biệt với provider được khai báo nhưng bị lỗi cấu hình hoặc lỗi khởi tạo, thường được báo bằng **ServiceConfigurationError** trong lúc duyệt. Tùy ứng dụng, host cần quyết định không có provider là lỗi bắt buộc hay tình huống có thể dùng fallback.

## 8. Provider constructor và provider method: hai đường tạo instance của named module

Với **explicit named module** ghi **provides ... with ...**, Java 17 hỗ trợ hai đường tạo provider:

| Cách tạo | Điều kiện | Kiểu được ghi sau with |
| --- | --- | --- |
| **Provider constructor** | Provider type public, cụ thể, gán được cho SPI và có constructor **public không tham số** | Chính lớp implementation hoặc subclass của SPI |
| **Provider method** | Provider type public và có **public static provider()** không tham số, kiểu trả về gán được cho SPI | Có thể là factory class không implements SPI |

Ví dụ phần 6 dùng đường **provider constructor**. Một thiết kế khác có thể dùng factory để kiểm soát quá trình tạo object và giữ concrete implementation ở quyền package-private.

**Ví dụ thay thế trong module ext.provider** (mã minh họa, không sử dụng đồng thời với cấu hình provider của phần 6):

**module-info.java** của module provider sẽ đổi thành:

~~~java
module ext.provider {
    requires ext.api;

    provides ext.api.Greeting
        with ext.provider.internal.GreetingFactory;
}
~~~

**ext/provider/internal/GreetingFactory.java** trong module provider:

~~~java
package ext.provider.internal;

import ext.api.Greeting;

public final class GreetingFactory {
    private GreetingFactory() {
    }

    public static Greeting provider() {
        return new InternalGreeting();
    }
}

final class InternalGreeting implements Greeting {
    @Override
    public String greet(String name) {
        return "Factory: " + name;
    }
}
~~~

Factory type **GreetingFactory** là public và ở đúng module provider, nhưng không phải subtype của Greeting và không cần public no-arg constructor. ServiceLoader của explicit named module gọi **public static provider()**, nhận object implement Greeting. **InternalGreeting** thậm chí là package-private, không cần xuất hiện trong provides clause. Package của cả hai vẫn có thể không export và không open.

Đây là **một lựa chọn thay thế**, không phải điều kiện bắt buộc cho mọi provider. Khi cùng một provider type có provider method hợp lệ, ServiceLoader ưu tiên đường method đó theo quy tắc named module. Nếu provider() trả null hoặc ném lỗi, việc duyệt provider có thể dẫn đến ServiceConfigurationError.

**Giới hạn quan trọng:** provider method không được dùng như cơ chế thay thế constructor cho provider được cấu hình qua **META-INF/services trên classpath** hoặc provider trong **automatic module**. Những trường hợp đó vẫn cần provider class gán được cho service và có provider constructor phù hợp. Không trộn lẫn quy tắc của hai mô hình triển khai.

## 9. Giữ package nội bộ đóng gói mang lại lợi ích gì?

Một module provider thường có các chi tiết thay đổi thường xuyên: thuật toán, cache, cấu hình, connection, adapter, factory và class hỗ trợ. Nếu export package implementation, module ngoài có thể import public types của nó và bắt đầu phụ thuộc vào cấu trúc không có ý định ổn định.

Giữ package chưa export có các tác dụng thực tế:

- **Giảm coupling:** host chỉ compile theo ext.api.Greeting, thay GreetingImpl không buộc sửa source của host.
- **Giữ freedom để refactor:** có thể đổi package/class implementation (đồng thời cập nhật provides), miễn hợp đồng và hành vi đã công bố còn tương thích.
- **Giảm bề mặt API:** người dùng module không vô tình chọn constructor hay helper class nội bộ làm API.
- **Tách hợp đồng khỏi chiến lược tạo instance:** factory có thể thay cách chọn implementation mà caller vẫn nhận một Greeting hợp lệ.
- **Giúp phát hiện phụ thuộc sai sớm:** compiler báo lỗi import package chưa export, thay vì đợi refactor implementation làm vỡ host.

Encapsulation không phải ẩn tuyệt đối **tên lớp**, **bytecode** hoặc **logic** khỏi người có quyền đọc artifact. Module descriptor có thông tin provides; runtime có thể cho biết tên class và module. Đây là cơ chế kiểm soát truy cập và duy trì ranh giới API, **không phải sandbox cho plugin không đáng tin**.

## 10. Phân biệt classpath SPI và JPMS named module

| Chủ đề | Provider JAR trên classpath | Explicit named module trên module path |
| --- | --- | --- |
| Nơi đăng ký service | Tệp **META-INF/services/<binary-service-name>** | **provides <Service> with <Provider>** trong module-info.java |
| Module tiêu thụ khai báo uses | Không có module-info.java trong unnamed module | Module chứa lời gọi ServiceLoader phải khai báo **uses** |
| Đường khởi tạo | Provider constructor public không tham số | Provider constructor hoặc public static provider() hợp lệ |
| Bảo vệ implementation package | Không có cơ chế exports/opens của named module | Có thể không export và không open package implementation |
| Phụ thuộc khi compile | Classpath và Java access rules | requires + readability + exports ở module API |
| Khám phá provider | ServiceLoader đọc service configuration resource | ServiceLoader dùng thông tin module descriptor/module graph |

Đối với **automatic module** (JAR thường được đặt trên module path để JPMS suy ra module), quy tắc khác explicit named module ở một số điểm. Không được lấy cơ chế static provider() của explicit named module rồi mặc định rằng nó hoạt động với automatic module. Nếu muốn encapsulation và khai báo provides rõ ràng, hãy sử dụng module-info.java thật và xác minh module descriptor của artifact đầu ra.

Với named module, bạn **không cần tạo META-INF/services** chỉ để đăng ký provider đã khai báo trong provides; tránh duy trì hai nguồn đăng ký không nhất quán. Nếu một provider class thuộc named module cũng xuất hiện trong service configuration file, cơ chế ServiceLoader có quy tắc riêng để không xử lý lặp theo cách classpath thông thường.

## 11. Quy tắc biên dịch và xử lý lỗi thường gặp

### 11.1. Điều kiện để provides hợp lệ

Trong explicit named module:

1. Service được chỉ định phải là kiểu phù hợp và có thể truy cập bởi module provider.
2. Mỗi provider type phải là **public top-level hoặc public static nested type** được khai báo trong **chính module chứa provides**.
3. Nếu không có provider method, provider phải là subtype của service và có public constructor không tham số.
4. Nếu có provider method, đó phải là public static method **provider()** không tham số với kiểu trả về gán được cho service.
5. Module chứa lời gọi ServiceLoader phải có uses cho service; module khác chỉ cần requires để dùng các kiểu public theo mức truy cập tương ứng.
6. Nếu provider cần class/library ngoài, những dependency đó vẫn phải có mặt và hợp lệ trên module path/runtime theo quan hệ module thực tế.

Sai phạm ở các ràng buộc về provides có thể được compiler phát hiện; các lỗi khác như constructor/provider() ném exception, dependency thiếu hoặc module chưa được resolve chỉ lộ ra lúc runtime.

### 11.2. Bảng chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Không có provider được tìm thấy | ext.provider chưa được resolve, không có provides, sai service/module layer | Kiểm tra module path, module graph và provides; với demo dùng --add-modules ext.provider |
| Compiler báo package implementation không visible | Host import provider từ package không exports | Đúng thiết kế: bỏ import implementation, dùng interface và ServiceLoader |
| Compiler báo service/provider không truy cập được | Thiếu requires/exports cho service, provider type sai hoặc không public | Kiểm tra API module và quy tắc provides |
| ServiceConfigurationError khi duyệt | Provider thiếu constructor/method hợp lệ, return sai, constructor/method ném lỗi, thiếu dependency | Xem cause, kiểm tra type/constructor/factory và runtime module graph |
| Host gọi ServiceLoader từ named module không có uses | Thiếu **uses <Service>** trong module gọi | Thêm uses vào đúng module của caller |
| Reflection tới implementation thất bại | Package không exports/opens cho caller | Dùng SPI; chỉ mở package khi có yêu cầu reflection được thiết kế rõ |
| Có class provider nhưng service không được phát hiện | Đường nạp hoặc module layer không đúng, khai báo provides ở sai module | Quan sát resolved modules và layer dùng trong ServiceLoader |
| Provider đã đổi artifact nhưng kết quả cũ | Loader/layer cũ hoặc ServiceLoader cache còn được dùng | Quản lý lifecycle, tạo layer/loader mới và reload phù hợp |

**ServiceLoader nạp provider lazily.** ServiceConfigurationError có thể phát sinh trong Iterator.hasNext(), Iterator.next(), Stream hoặc Provider.get() tùy thời điểm thực hiện việc tìm/tạo. Catch lỗi ở nơi quản lý discovery để gắn thêm provider/service context, không nhét catch(Throwable) khắp code nghiệp vụ.

Nếu muốn quan sát việc đăng ký từ artifact đã biên dịch, có thể sử dụng:

~~~bash
java --describe-module ext.provider --module-path mods
~~~

Lệnh trên minh họa khả năng xem module descriptor; tùy cách gọi JVM có thể dùng cách viết **java --module-path mods --describe-module ext.provider** để bảo đảm option được phân tích đúng. Kết quả module descriptor giúp kiểm tra provides có đúng service và provider type hay không. Không dùng sự tồn tại của .class đơn lẻ làm bằng chứng đã đăng ký SPI.

### 11.3. Runtime module graph và module layer

Việc đặt JAR/exploded module trên module path **chưa bảo đảm module đó đã được resolve và tham gia layer đang dùng**. Với ví dụ đơn giản, **--add-modules ext.provider** giải quyết rõ điều này. Trong cấu hình service binding, JPMS cũng có thể thêm provider module khi giải quyết dependency service; cách launch, module graph, custom ModuleLayer hay runtime image có thể ảnh hưởng kết quả.

Khi host nạp plugin ở một **ModuleLayer** riêng, cân nhắc **ServiceLoader.load(layer, Greeting.class)** để khám phá provider trong layer đó và các parent layer theo hợp đồng API, thay vì mặc định ServiceLoader.load(Greeting.class) đang tìm đúng nơi. Cách khởi tạo custom ModuleLayer là một thiết kế rộng hơn; bài này chỉ yêu cầu hiểu rằng **provides** phải đi cùng cấu hình layer/visibility thích hợp.

Không nên thêm **requires ext.provider** vào module ứng dụng chỉ vì provider có trên module path. Quan hệ trực tiếp đó đánh mất lợi ích thay thế provider mà service abstraction mang lại.

## 12. Kiểm thử tính đóng gói

Một bộ kiểm thử tối thiểu nên có cả kiểm tra **tích cực** (SPI vẫn chạy) và **tiêu cực** (không thể truy cập implementation như API):

| Thử nghiệm | Kết quả mong đợi |
| --- | --- |
| Compile ba module bằng --release 17 | Thành công; không cần export implementation |
| Chạy ext.app với ext.provider được resolve | ServiceLoader tạo provider và chạy Greeting.greet |
| Kiểm tra isExported cho ext.provider.internal từ ext.app | false |
| Kiểm tra isOpen cho ext.provider.internal từ ext.app | false |
| Thêm import ext.provider.internal.GreetingImpl vào host | Không hợp lệ qua ranh giới module nếu package không export |
| Bỏ uses trong ext.app nhưng vẫn gọi ServiceLoader | Caller module không có permission uses; lỗi service loading |
| Đổi provides sang tên provider sai hoặc kiểu không phù hợp | Compile-time error hoặc lỗi đăng ký phù hợp |
| Provider constructor/provider() ném exception | Quan sát ServiceConfigurationError khi khởi tạo |
| Thay provider module khác thực hiện cùng Greeting | Host giữ nguyên source code; discovery được cấu hình lại |
| Chạy qua custom ModuleLayer | Provider tìm thấy trong đúng layer theo cấu hình |

Trong CI, chạy ví dụ trên các **named modules thật** thay vì dồn mọi .class vào classpath. Nếu unit test chỉ chạy trên unnamed module, có thể không phát hiện được việc quên uses, export nhầm implementation package hay module resolution sai.

Nên kiểm tra danh sách exports/opens trong module descriptor sau khi build artifact: một thay đổi build hoặc module-info.java có thể vô tình làm lộ package nội bộ dù kiểm thử chức năng vẫn pass.

## 13. Checklist thiết kế trước khi công bố provider module

- API module export **đúng những package hợp đồng** cho consumer/provider.
- Provider module khai báo **requires API** và **provides Service with Provider** với đúng binary type.
- Provider class nằm **trong chính module provider**, public và có provider constructor hoặc provider method hợp lệ.
- Implementation package **không exports và không opens** nếu không có nhu cầu truy cập bên ngoài cụ thể.
- Consumer module **requires API**, **uses Service** tại nơi gọi ServiceLoader và không phụ thuộc compile-time vào implementation module.
- Runtime cấu hình module path, module resolution và module layer phù hợp; không coi "JAR có mặt" là "module đã được dùng".
- Kiểm thử **ServiceLoader hoạt động** đồng thời xác minh **isExported/isOpen false** đối với package triển khai.
- Xử lý trường hợp không có provider, nhiều provider hoặc provider lỗi với chính sách rõ ràng; không phụ thuộc thứ tự ngẫu nhiên.
- Đã phân biệt explicit named modules, automatic modules và classpath providers trước khi áp dụng quy tắc constructor/factory.

**Ghi nhớ:** **provides ... with ...** là cách module công bố provider cho **ServiceLoader**, không phải lệnh export class implementation. Giữ interface/DTO ở package API được export, còn class triển khai trong package **không export và không open**; host gọi qua SPI, và JPMS duy trì ranh giới đóng gói trong khi vẫn hỗ trợ mở rộng lúc chạy.

Tài liệu tham khảo chính thức cho Java 17:

- https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html
- https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html
