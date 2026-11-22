# ServiceLoader.load từ caller module

> Phạm vi: Java Platform Module System (JPMS, từ Java 9). Bài này giải thích module nào phải khai báo **uses** khi gọi **ServiceLoader.load**, và cách điều đó liên quan đến việc tìm provider lúc chạy.

## Mục tiêu

Sau bài này, bạn có thể:

- Xác định đúng **caller module** của lời gọi **ServiceLoader.load**.
- Đặt **uses**, **requires** và **provides** vào đúng module descriptor.
- Phân biệt module của caller, module chứa service API, module chứa provider và thread context class loader.
- Giải thích vì sao ứng dụng không cần phụ thuộc trực tiếp vào module provider.
- Chọn đúng overload của **ServiceLoader.load** và chẩn đoán lỗi **ServiceConfigurationError**.

## 1. Caller module là module nào?

**Caller module** là module chứa đoạn code trực tiếp gọi phương thức **ServiceLoader.load**. JVM xác định module này ngầm định khi phương thức được gọi; bạn không truyền module caller vào tham số.

Ví dụ:

~~~java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class);
~~~

Nếu đoạn code trên nằm trong module **com.acme.app**, thì **com.acme.app** là caller module. Caller module không phải mặc nhiên là:

- module khai báo interface **GreetingService**;
- module triển khai **GreetingService**;
- module của thread context class loader.

Ba khái niệm này có vai trò khác nhau:

| Thành phần | Vai trò |
|---|---|
| Caller module | Module phải được phép sử dụng service; đây là nơi khai báo **uses**. |
| Service module | Module chứa kiểu service; caller cần đọc được kiểu này, thường thông qua **requires** và **exports**. |
| Provider module | Module đăng ký implementation bằng **provides ... with ...**. |
| Thread context class loader (TCCL) | Điểm bắt đầu để **ServiceLoader.load(service)** tìm provider. |

Điểm quan trọng: **caller module quyết định kiểm tra uses; TCCL quyết định phạm vi class loader bắt đầu tìm provider.** Đừng gộp hai khái niệm này thành một.

## 2. ServiceLoader.load(Class<S>) hoạt động thế nào?

Lời gọi:

~~~java
ServiceLoader.load(GreetingService.class);
~~~

tương đương với:

~~~java
ServiceLoader.load(
        GreetingService.class,
        Thread.currentThread().getContextClassLoader()
);
~~~

Vì vậy, overload một tham số sử dụng TCCL của thread hiện tại. Overload nhận **ClassLoader** cho phép chỉ định loader rõ ràng:

~~~java
ClassLoader loader = Thread.currentThread().getContextClassLoader();

ServiceLoader<GreetingService> services =
        ServiceLoader.load(GreetingService.class, loader);
~~~

Cả hai overload đều thực hiện kiểm tra quyền sử dụng service dựa trên caller module. Nếu caller nằm trong một **explicit named module**, module descriptor của caller phải khai báo **uses** cho service. Nếu service type không truy cập được từ caller, hoặc caller là explicit module nhưng thiếu **uses**, lời gọi có thể ném **ServiceConfigurationError**.

**ServiceLoader.load** tạo đối tượng loader; provider được tìm và khởi tạo một cách lazy khi bạn duyệt **iterator()**, dùng **stream()** hoặc gọi thao tác tương ứng. Vì thế, lỗi provider có thể xuất hiện ở bước duyệt, sau khi lời gọi **load** đã trả về.

## 3. Đặt requires, uses và provides đúng chỗ

Giả sử có ba module:

- **com.acme.spi**: công bố service API.
- **com.acme.provider**: cung cấp implementation.
- **com.acme.app**: gọi **ServiceLoader.load** để sử dụng service.

### Module chứa service API

**module-info.java** của **com.acme.spi**:

~~~java
module com.acme.spi {
    exports com.acme.spi;
}
~~~

Interface service:

~~~java
package com.acme.spi;

public interface GreetingService {
    String greet(String name);
}
~~~

Package chứa interface cần được export để module ứng dụng có thể tham chiếu kiểu **GreetingService**.

### Module gọi ServiceLoader.load

**module-info.java** của **com.acme.app**:

~~~java
module com.acme.app {
    requires com.acme.spi;
    uses com.acme.spi.GreetingService;
}
~~~

Hai directive có mục đích riêng:

- **requires com.acme.spi** cho phép code trong app đọc và sử dụng service type được export từ module SPI.
- **uses com.acme.spi.GreetingService** khai báo rằng app tìm provider cho service này qua **ServiceLoader**.

**uses phải nằm trong module trực tiếp gọi ServiceLoader.load.** Nếu code gọi API nằm trong một module tiện ích, chẳng hạn **com.acme.bootstrap**, thì **uses** phải được khai báo trong **com.acme.bootstrap**. Việc module ứng dụng gọi một hàm wrapper không tự chuyển quyền khai báo **uses** sang ứng dụng.

### Module cung cấp implementation

**module-info.java** của **com.acme.provider**:

~~~java
module com.acme.provider {
    requires com.acme.spi;

    provides com.acme.spi.GreetingService
        with com.acme.provider.EnglishGreetingService;
}
~~~

Implementation:

~~~java
package com.acme.provider;

import com.acme.spi.GreetingService;

public final class EnglishGreetingService implements GreetingService {

    public EnglishGreetingService() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Provider module cần đọc được service API nên khai báo **requires com.acme.spi**. Directive **provides ... with ...** đăng ký implementation cho service. Trong ví dụ này, provider có constructor public không tham số.

Package **com.acme.provider** không cần export chỉ để **ServiceLoader** sử dụng provider đã được khai báo bằng **provides**. Package chứa service API mới là package cần export cho caller.

Một provider trong named module cũng có thể khai báo public static method không tham số tên **provider**, trả về kiểu tương thích với service. Khi dùng provider method đó, chính lớp provider không bắt buộc phải implement service interface; nếu không có provider method, provider class phải đáp ứng quy tắc constructor của ServiceLoader.

### Vì sao app không requires com.acme.provider?

App chỉ phụ thuộc vào abstraction **GreetingService**. Provider được tìm qua cơ chế service binding của module system và ServiceLoader. Khi module đã được resolve sử dụng một service, quá trình resolve có thể đưa các module provider tương ứng trên module path vào module graph.

Do đó, app thường chỉ cần **requires** module chứa service API và **uses** service. Nếu app khai báo **requires com.acme.provider**, app đã phụ thuộc trực tiếp vào implementation cụ thể và mất một phần lợi ích thay thế provider độc lập.

## 4. Ví dụ sử dụng hoàn chỉnh

Trong module **com.acme.app**, lớp **Main** có thể duyệt tất cả provider:

~~~java
package com.acme.app;

import com.acme.spi.GreetingService;
import java.util.ServiceLoader;

public final class Main {

    public static void main(String[] args) {
        ServiceLoader<GreetingService> services =
                ServiceLoader.load(GreetingService.class);

        for (GreetingService service : services) {
            System.out.println(service.greet("Lan"));
        }
    }
}
~~~

Một cấu trúc source đơn giản:

~~~text
src/
├── com.acme.spi/
│   ├── module-info.java
│   └── com/acme/spi/GreetingService.java
├── com.acme.provider/
│   ├── module-info.java
│   └── com/acme/provider/EnglishGreetingService.java
└── com.acme.app/
    ├── module-info.java
    └── com/acme/app/Main.java
~~~

Biên dịch các module:

~~~bash
javac --module-source-path src -d out \
  -m com.acme.spi,com.acme.provider,com.acme.app
~~~

Chạy ứng dụng:

~~~bash
java --module-path out \
  -m com.acme.app/com.acme.app.Main
~~~

Khi service binding được thực hiện trong quá trình resolve module, provider module khai báo **provides** cho service mà app khai báo **uses** có thể được đưa vào module graph mà app không cần **requires** trực tiếp provider đó.

Kết quả với provider ở trên:

~~~text
Hello, Lan!
~~~

## 5. Phạm vi tìm provider: class loader và module layer

Caller module và nơi tìm provider là hai trục riêng biệt.

### load(service)

~~~java
ServiceLoader.load(GreetingService.class);
~~~

Dùng TCCL của thread hiện tại làm class loader bắt đầu tìm kiếm. Cơ chế tìm provider có thể xét provider trong named module và unnamed module mà loader có thể nhìn thấy, bao gồm quan hệ parent delegation.

Nếu ứng dụng chạy trong container, application server hoặc môi trường plugin, TCCL có thể khác class loader của lớp đang gọi. Khi provider không được tìm thấy, hãy kiểm tra TCCL tại đúng thread thực hiện lời gọi.

### load(service, classLoader)

~~~java
ServiceLoader.load(GreetingService.class, pluginClassLoader);
~~~

Dùng class loader được truyền vào làm điểm bắt đầu tìm provider. Kiểm tra **uses** vẫn dựa trên caller module.

### load(moduleLayer, service)

~~~java
ServiceLoader<GreetingService> services =
        ServiceLoader.load(pluginLayer, GreetingService.class);
~~~

Dùng khi provider nằm trong một module layer cụ thể, ví dụ layer được tạo riêng cho plugin. Phương thức này tìm provider trong layer được chỉ định và các parent layer của nó; nó không tìm provider trong unnamed module.

Overload nhận **ModuleLayer** cũng áp dụng kiểm tra service accessibility và **uses** đối với caller module. Nếu dùng plugin layer, cần bảo đảm provider module thực sự thuộc layer đó hoặc một parent layer phù hợp.

### loadInstalled(service)

~~~java
ServiceLoader.loadInstalled(GreetingService.class);
~~~

Dùng platform class loader. Phương thức này hướng đến provider được cài đặt trong runtime; provider chỉ nằm trên application module path hoặc class path sẽ không được tìm theo cách thông thường của **load(service)**.

## 6. Nếu provider nằm trên class path

ServiceLoader vẫn hỗ trợ provider theo cơ chế class path truyền thống. JAR của provider chứa file:

~~~text
META-INF/services/com.acme.spi.GreetingService
~~~

Nội dung file liệt kê tên đầy đủ của các provider class, mỗi tên trên một dòng:

~~~text
com.acme.provider.EnglishGreetingService
~~~

Khi ứng dụng chạy trên class path, code thường thuộc unnamed module nên không có **module-info.java** để khai báo **uses**. Với ứng dụng chạy trong explicit named module, hãy dùng **uses** như các phần trước.

Không nhầm hai cơ chế đăng ký:

- Named module: khai báo **provides ... with ...** trong **module-info.java**.
- Class path: khai báo provider class trong **META-INF/services/<tên-đầy-đủ-của-service>**.

## 7. Lỗi thường gặp và cách tìm nguyên nhân

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| **ServiceConfigurationError** ngay tại **load** | Caller là explicit module nhưng thiếu **uses**, hoặc service type không truy cập được | Xác định module trực tiếp gọi **load**; thêm **uses**; kiểm tra **requires** và **exports** của service API |
| Không tìm thấy provider | Provider module không được resolve, provider không nằm trong phạm vi loader/layer, hoặc thiếu **provides** | Kiểm tra module path, module graph, **provides** và TCCL/layer |
| Lỗi khi duyệt **ServiceLoader** | Provider class không load được, khai báo provider sai, constructor/provider method không hợp lệ hoặc khởi tạo provider thất bại | Đọc đầy đủ nguyên nhân của **ServiceConfigurationError**; kiểm tra class và khai báo provider |
| App có **uses** nhưng vẫn lỗi | **uses** nằm trong module app, trong khi module khác mới là nơi trực tiếp gọi **ServiceLoader.load** | Chuyển **uses** vào module chứa lời gọi trực tiếp |
| App phải phụ thuộc vào implementation cụ thể | App đang **requires** provider module | Để app phụ thuộc service API; đăng ký implementation bằng **provides** ở provider module |
| Chạy được ở thread này nhưng không tìm thấy provider ở thread khác | TCCL khác nhau giữa các thread | Kiểm tra **Thread.currentThread().getContextClassLoader()** tại nơi gọi; cân nhắc truyền loader rõ ràng |

Một trình tự debug thực tế:

1. Tìm chính xác dòng gọi **ServiceLoader.load**.
2. Xác định module chứa lớp thực hiện lời gọi đó.
3. Nếu đó là explicit named module, xác nhận module descriptor có **uses** đúng service type.
4. Xác nhận caller đọc được service type: module chứa service export package và caller có **requires** phù hợp.
5. Kiểm tra provider module có **provides ... with ...**, có mặt trong module path và được resolve vào module layer cần tìm.
6. Kiểm tra TCCL nếu đang dùng overload **load(service)** hoặc **load(service, loader)**.
7. Duyệt loader để quan sát lỗi phát sinh trong quá trình tìm, load và khởi tạo provider.

## 8. Các điểm cần nhớ

- **uses** thuộc caller module — module trực tiếp gọi **ServiceLoader.load**.
- **requires** cho phép caller sử dụng service API; **exports** công bố package chứa service API.
- **provides ... with ...** thuộc provider module và đăng ký implementation.
- Caller module không đồng nghĩa với service module, provider module hoặc module của TCCL.
- **ServiceLoader.load(service)** dùng TCCL; **ServiceLoader.load(layer, service)** tìm trong module layer và các parent layer.
- **load** trả về loader; provider được xử lý lazy khi duyệt.
- Không cần để consumer **requires** từng provider module nếu muốn giữ kiến trúc service provider có thể thay thế.

Một lưu ý về vòng đời: ServiceLoader không được thiết kế để dùng chung đồng thời giữa nhiều thread. Cũng không nên cache loader này trên toàn JVM một cách tùy tiện, vì các ứng dụng khác nhau có thể có TCCL khác nhau và cache toàn cục có thể giữ lại class loader lâu hơn dự kiến.

## Tài liệu tham khảo

- [ServiceLoader — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html)
- [Java Language Specification — Module Declarations, Service Consumption và Service Provision](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.7)
- [Decoupling Modules with Services — Dev.java](https://dev.java/learn/organizing/modules/services/)
