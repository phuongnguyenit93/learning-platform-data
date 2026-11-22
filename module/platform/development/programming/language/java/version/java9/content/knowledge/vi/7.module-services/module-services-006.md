# ServiceLoader.Provider, stream và thời điểm khởi tạo

JPMS cho phép một mô-đun sử dụng dịch vụ thông qua interface hoặc abstraction mà không cần phụ thuộc trực tiếp vào từng lớp triển khai. **ServiceLoader** tìm các provider đã đăng ký; từ Java 9, API này có thêm **ServiceLoader.Provider<S>** và **ServiceLoader.stream()** để ứng dụng xem thông tin kiểu provider, lọc hoặc sắp xếp lựa chọn trước khi tạo đối tượng.

Điểm quan trọng của bài học là phân biệt ba thời điểm:

1. Tạo đối tượng **ServiceLoader**.
2. Khám phá provider và nhận các handle **Provider<S>**.
3. Tạo instance dịch vụ bằng **Provider.get()** hoặc lấy instance qua **Iterator.next()**.

Hiểu đúng thứ tự này giúp tránh khởi tạo những provider không được chọn, giảm side effect và kiểm soát thời điểm framework hoặc ứng dụng thực thi constructor/provider method.

## 1. ServiceLoader và cơ chế provider

Một service thường được định nghĩa bằng interface hoặc kiểu cha mà ứng dụng sử dụng. Provider là thành phần cung cấp implementation của service đó.

Ví dụ, mô-đun SPI khai báo:

~~~java
package com.example.spi;

public interface GreetingService {
    String greet(String name);
}
~~~

Mô-đun ứng dụng chỉ cần biết **GreetingService**. Các implementation có thể được cung cấp bởi những mô-đun độc lập và được tìm thấy trong lúc chạy.

Trong JPMS, mô-đun tiêu thụ khai báo **uses**:

~~~java
module com.example.app {
    requires com.example.spi;
    uses com.example.spi.GreetingService;
}
~~~

Mô-đun cung cấp khai báo **provides ... with ...**:

~~~java
module com.example.provider {
    requires com.example.spi;
    provides com.example.spi.GreetingService
        with com.example.provider.EnglishGreetingService;
}
~~~

Với ứng dụng chạy trên classpath, ServiceLoader cũng hỗ trợ cấu hình provider qua tệp **META-INF/services/<tên-service-đầy-đủ>**. Với named module, nên khai báo quan hệ dịch vụ trong **module-info.java** để module system quản lý việc tìm provider.

ServiceLoader có thể tìm nhiều provider cho cùng một service. Ứng dụng không cần tạo trực tiếp implementation bằng cách gọi constructor cụ thể; nó yêu cầu ServiceLoader tìm provider theo service type.

## 2. ServiceLoader.Provider<S> là gì?

Từ Java 9, **ServiceLoader.Provider<S>** biểu diễn một provider dưới dạng handle có thể xem kiểu trước khi lấy instance.

API chính:

~~~java
public interface ServiceLoader.Provider<S>
        extends Supplier<S> {

    Class<? extends S> type();

    S get();
}
~~~

- **type()** trả về Class của kiểu provider. Nếu provider là lớp triển khai trực tiếp, đây là lớp triển khai. Nếu provider dùng provider method, đây là kiểu trả về của phương thức **provider()**.
- **get()** lấy một instance của service từ provider. Với provider lớp, ServiceLoader khởi tạo lớp provider. Với provider method, ServiceLoader gọi phương thức factory đã khai báo.
- Vì **Provider<S>** kế thừa **Supplier<S>**, handle cũng có phương thức **get()** theo hợp đồng Supplier.

Điểm khác nhau giữa service type và provider type:

- **GreetingService.class** là kiểu dịch vụ mà ứng dụng yêu cầu.
- **EnglishGreetingService.class** hoặc **VietnameseGreetingService.class** là kiểu provider cụ thể mà ServiceLoader tìm được.

Nhờ **type()**, ứng dụng có thể xem tên lớp, annotation hoặc metadata của implementation trước khi gọi **get()**.

## 3. ServiceLoader.stream()

**stream()** trả về:

~~~java
Stream<ServiceLoader.Provider<S>>
~~~

Nó trả về stream các provider handle, không phải stream các instance service. Đây là khác biệt quan trọng so với việc lặp trực tiếp qua **ServiceLoader<S>**.

Ví dụ:

~~~java
ServiceLoader<GreetingService> loader =
    ServiceLoader.load(GreetingService.class);

loader.stream()
    .map(provider -> provider.type().getName())
    .forEach(System.out::println);
~~~

Đoạn code trên xem tên kiểu provider. Việc duyệt stream và gọi **type()** không yêu cầu ứng dụng gọi constructor của implementation hoặc provider method để lấy service instance.

### 3.1. Lọc provider trước khi khởi tạo

Giả sử có nhiều implementation và chỉ muốn dùng provider có kiểu **VietnameseGreetingService**:

~~~java
ServiceLoader.Provider<GreetingService> selectedProvider =
    loader.stream()
        .filter(provider ->
            provider.type().getSimpleName()
                .equals("VietnameseGreetingService"))
        .findFirst()
        .orElseThrow(() ->
            new IllegalStateException("No matching provider"));

GreetingService service = selectedProvider.get();
~~~

Luồng xử lý:

1. ServiceLoader tìm các provider handle.
2. **type()** cung cấp kiểu để điều kiện lọc kiểm tra.
3. **findFirst()** chọn handle phù hợp.
4. **get()** mới yêu cầu instance của provider được chọn.

Các provider bị loại bởi điều kiện lọc không cần được khởi tạo chỉ để kiểm tra kiểu.

Có thể xem toàn bộ kiểu provider trước khi lựa chọn:

~~~java
List<ServiceLoader.Provider<GreetingService>> providers =
    loader.stream().toList();

providers.forEach(provider ->
    System.out.println(provider.type().getName()));
~~~

**toList()** ở đây thu thập các handle. Nó không biến chúng thành các **GreetingService** instance. Muốn có instance, phải gọi **get()** trên handle tương ứng.

## 4. Thời điểm khám phá và khởi tạo provider

Cần tách biệt việc tìm provider với việc tạo đối tượng provider.

| Thao tác | Việc xảy ra | Có tạo service instance? |
|---|---|---|
| **ServiceLoader.load(Service.class)** | Tạo loader và thiết lập ngữ cảnh tìm provider | Không |
| **loader.stream()** | Tạo stream provider handle | Không |
| **stream.filter(...)** | Xây dựng bước lọc của stream | Không; chưa duyệt stream |
| Terminal operation như **toList()**, **findFirst()** | Duyệt provider handle cần thiết và khám phá kiểu provider | Không tự gọi get() |
| **provider.type()** | Trả về kiểu provider | Không |
| **provider.get()** | Khởi tạo provider hoặc gọi provider method | Có |
| **iterator.hasNext()** | Kiểm tra và có thể tìm provider tiếp theo | Không tự khởi tạo instance mới |
| **iterator.next()** | Trả về provider instance tiếp theo | Có nếu instance chưa nằm trong cache |

### 4.1. Tạo ServiceLoader chưa tạo provider

~~~java
ServiceLoader<GreetingService> loader =
    ServiceLoader.load(GreetingService.class);

System.out.println("loader ready");
~~~

Lệnh **load()** không tạo tất cả các implementation. Việc tìm và nạp thông tin provider được thực hiện khi loader được duyệt.

Vì vậy, nếu provider có constructor ghi log hoặc thực hiện công việc tốn thời gian, chỉ tạo loader không làm các constructor đó chạy.

### 4.2. Duyệt Provider stream chưa gọi get()

~~~java
List<ServiceLoader.Provider<GreetingService>> handles =
    loader.stream().toList();
~~~

Terminal operation **toList()** buộc stream duyệt các provider cần thiết để tạo danh sách handle. ServiceLoader có thể cần nạp hoặc kiểm tra kiểu provider trong quá trình này, nhưng việc tạo handle không đồng nghĩa với tạo service instance.

Nếu constructor hoặc provider factory có side effect, chúng chưa được gọi chỉ vì ứng dụng đã thu thập các handle.

### 4.3. get() là điểm yêu cầu instance

~~~java
GreetingService service = handles.get(0).get();
~~~

Đây là thời điểm ứng dụng yêu cầu instance. Với provider lớp, constructor public không tham số được gọi. Với provider method, phương thức factory **provider()** được gọi để lấy đối tượng dịch vụ.

Không nên giả định mọi provider sẽ được tạo sẵn khi **load()** hoặc **stream()** được gọi. Hãy gọi **get()** ở đúng thời điểm ứng dụng thật sự cần implementation.

## 5. Provider lớp và provider method

JPMS hỗ trợ hai cách khai báo provider phổ biến.

### 5.1. Provider là lớp triển khai service

~~~java
package com.example.provider;

import com.example.spi.GreetingService;

public final class EnglishGreetingService
        implements GreetingService {

    public EnglishGreetingService() {
        System.out.println("construct:English");
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Module descriptor:

~~~java
module com.example.provider {
    requires com.example.spi;

    provides com.example.spi.GreetingService
        with com.example.provider.EnglishGreetingService;
}
~~~

Với provider lớp, lớp provider phải đáp ứng yêu cầu của ServiceLoader, gồm khả năng truy cập và constructor public không tham số. Khi **Provider.get()** được gọi, ServiceLoader tạo implementation bằng constructor đó.

### 5.2. Provider method

Named module cũng có thể cung cấp một lớp factory có phương thức public static tên **provider()**. Phương thức không nhận tham số và trả về một kiểu triển khai service.

~~~java
package com.example.provider;

public final class VietnameseGreetingFactory {
    private VietnameseGreetingFactory() { }

    public static VietnameseGreetingService provider() {
        System.out.println("factory:Vietnamese");
        return new VietnameseGreetingService();
    }
}
~~~

Implementation:

~~~java
package com.example.provider;

import com.example.spi.GreetingService;

public final class VietnameseGreetingService
        implements GreetingService {

    VietnameseGreetingService() {
        System.out.println("construct:Vietnamese");
    }

    @Override
    public String greet(String name) {
        return "Xin chao, " + name + "!";
    }
}
~~~

Module descriptor:

~~~java
module com.example.provider {
    requires com.example.spi;

    provides com.example.spi.GreetingService
        with com.example.provider.VietnameseGreetingFactory;
}
~~~

Trong trường hợp này, lớp được liệt kê sau **with** là lớp factory. Khi ServiceLoader gọi **Provider.type()**, kiểu được trả về là kiểu trả về của provider method, ở đây là **VietnameseGreetingService**. Khi gọi **Provider.get()**, ServiceLoader gọi **VietnameseGreetingFactory.provider()** để lấy service instance.

Cách này hữu ích khi provider cần tạo đối tượng thông qua factory, cần lựa chọn cấu hình hoặc không thể dùng constructor public không tham số của implementation.

## 6. Ví dụ hoàn chỉnh: lọc provider và khởi tạo đúng lúc

Ví dụ có ba mô-đun:

- **com.example.spi** định nghĩa **GreetingService**.
- **com.example.provider** cung cấp một provider lớp và một provider method.
- **com.example.app** duyệt Provider stream, xem kiểu và chỉ lấy instance của provider được chọn.

Cấu trúc thư mục:

~~~text
src/
├── com.example.spi/
│   ├── module-info.java
│   └── com/example/spi/GreetingService.java
├── com.example.provider/
│   ├── module-info.java
│   └── com/example/provider/
│       ├── EnglishGreetingService.java
│       ├── VietnameseGreetingFactory.java
│       └── VietnameseGreetingService.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
~~~

### 6.1. Mô-đun SPI

Tệp **src/com.example.spi/module-info.java**:

~~~java
module com.example.spi {
    exports com.example.spi;
}
~~~

Tệp **src/com.example.spi/com/example/spi/GreetingService.java**:

~~~java
package com.example.spi;

public interface GreetingService {
    String greet(String name);
}
~~~

### 6.2. Mô-đun provider

Tệp **src/com.example.provider/module-info.java**:

~~~java
module com.example.provider {
    requires com.example.spi;

    provides com.example.spi.GreetingService
        with com.example.provider.EnglishGreetingService,
             com.example.provider.VietnameseGreetingFactory;
}
~~~

Tệp **src/com.example.provider/com/example/provider/EnglishGreetingService.java**:

~~~java
package com.example.provider;

import com.example.spi.GreetingService;

public final class EnglishGreetingService
        implements GreetingService {

    public EnglishGreetingService() {
        System.out.println("construct:English");
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Tệp **src/com.example.provider/com/example/provider/VietnameseGreetingService.java**:

~~~java
package com.example.provider;

import com.example.spi.GreetingService;

public final class VietnameseGreetingService
        implements GreetingService {

    VietnameseGreetingService() {
        System.out.println("construct:Vietnamese");
    }

    @Override
    public String greet(String name) {
        return "Xin chao, " + name + "!";
    }
}
~~~

Tệp **src/com.example.provider/com/example/provider/VietnameseGreetingFactory.java**:

~~~java
package com.example.provider;

public final class VietnameseGreetingFactory {
    private VietnameseGreetingFactory() { }

    public static VietnameseGreetingService provider() {
        System.out.println("factory:Vietnamese");
        return new VietnameseGreetingService();
    }
}
~~~

### 6.3. Mô-đun ứng dụng

Tệp **src/com.example.app/module-info.java**:

~~~java
module com.example.app {
    requires com.example.spi;
    uses com.example.spi.GreetingService;
}
~~~

Ứng dụng chỉ yêu cầu mô-đun SPI. Nó không cần khai báo phụ thuộc trực tiếp tới mô-đun provider để tham chiếu implementation, vì việc tìm provider được thực hiện qua cơ chế dịch vụ.

Tệp **src/com.example.app/com/example/app/Main.java**:

~~~java
package com.example.app;

import java.util.List;
import java.util.ServiceLoader;
import com.example.spi.GreetingService;

public final class Main {
    public static void main(String[] args) {
        ServiceLoader<GreetingService> loader =
            ServiceLoader.load(GreetingService.class);

        System.out.println("loader-created");

        List<ServiceLoader.Provider<GreetingService>> providers =
            loader.stream().toList();

        System.out.println("provider-handles=" + providers.size());

        providers.stream()
            .map(provider -> provider.type().getName())
            .sorted()
            .forEach(type -> System.out.println("provider-type=" + type));

        System.out.println("before-get");

        GreetingService selected = providers.stream()
            .filter(provider -> provider.type().getSimpleName()
                .equals("VietnameseGreetingService"))
            .findFirst()
            .orElseThrow(() ->
                new IllegalStateException("No matching provider"))
            .get();

        System.out.println(selected.greet("JPMS"));
    }
}
~~~

### 6.4. Biên dịch và chạy

Yêu cầu JDK 17 trở lên. Chạy từ thư mục chứa **src**:

~~~bash
javac -d out --module-source-path src -m com.example.spi,com.example.provider,com.example.app
java --module-path out --add-modules com.example.provider -m com.example.app/com.example.app.Main
~~~

**--add-modules com.example.provider** đưa mô-đun provider vào cấu hình chạy, trong khi ứng dụng chỉ khai báo **requires com.example.spi**.

Kết quả stdout:

~~~text
loader-created
provider-handles=2
provider-type=com.example.provider.EnglishGreetingService
provider-type=com.example.provider.VietnameseGreetingService
before-get
factory:Vietnamese
construct:Vietnamese
Xin chao, JPMS!
~~~

Hãy chú ý thứ tự:

- Sau **loader-created**, chưa có constructor nào chạy.
- Sau khi thu thập hai provider handle và in kiểu, vẫn chưa có constructor hoặc factory nào chạy.
- Sau **before-get**, ứng dụng mới gọi **get()** trên provider được chọn.
- Factory tiếng Việt được gọi, sau đó implementation được tạo và trả lời.

Provider tiếng Anh không được khởi tạo trong luồng lựa chọn này vì ứng dụng chỉ gọi **get()** trên handle tiếng Việt. Ví dụ minh họa cách dùng metadata để chọn implementation trước khi tạo đối tượng.

## 7. So sánh stream() với iterator()

ServiceLoader cũng triển khai **Iterable<S>**, nên có thể duyệt provider trực tiếp bằng iterator:

~~~java
ServiceLoader<GreetingService> loader =
    ServiceLoader.load(GreetingService.class);

Iterator<GreetingService> iterator = loader.iterator();

if (iterator.hasNext()) {
    GreetingService service = iterator.next();
    System.out.println(service.greet("JPMS"));
}
~~~

Hai cách duyệt có mục tiêu khác nhau:

- **iterator()** trả về service instance. **hasNext()** kiểm tra provider tiếp theo và có thể thực hiện việc tìm/nạp metadata; **next()** trả về instance và khởi tạo provider khi cần.
- **stream()** trả về **Provider<S>**. Ứng dụng có thể gọi **type()** để kiểm tra implementation trước, sau đó mới gọi **get()** cho provider được chọn.

Iterator có thể trả các instance đã nằm trong cache của ServiceLoader trước khi tìm và khởi tạo provider tiếp theo. Vì vậy, khi kiểm tra thời điểm khởi tạo, cần phân biệt instance đã được tạo từ trước với provider mới được khám phá.

Dùng **iterator()** khi ứng dụng muốn lấy các service instance theo lượt. Dùng **stream()** khi cần lọc, sắp xếp hoặc kiểm tra kiểu provider trước khi khởi tạo.

## 8. Những cách dùng dễ làm khởi tạo quá sớm

### 8.1. Gọi get() trước khi lọc

Cách sau có thể tạo nhiều provider hơn mức cần thiết:

~~~java
GreetingService selected = loader.stream()
    .map(ServiceLoader.Provider::get)
    .filter(service ->
        service.getClass().getSimpleName()
            .equals("VietnameseGreetingService"))
    .findFirst()
    .orElseThrow();
~~~

**map(Provider::get)** gọi **get()** trước khi điều kiện **filter** kiểm tra service instance. Vì vậy, mỗi provider được stream duyệt qua trước khi tìm thấy kết quả đều có thể bị khởi tạo.

Cách phù hợp khi cần lọc theo kiểu là lọc trên Provider handle trước:

~~~java
GreetingService selected = loader.stream()
    .filter(provider ->
        provider.type().getSimpleName()
            .equals("VietnameseGreetingService"))
    .findFirst()
    .orElseThrow()
    .get();
~~~

### 8.2. Duyệt trực tiếp ServiceLoader khi chỉ cần metadata

~~~java
for (GreetingService service : loader) {
    System.out.println(service.getClass().getName());
}
~~~

Vòng lặp trên lấy service instance. Nó phù hợp khi ứng dụng thực sự cần dùng từng service, nhưng không phù hợp nếu chỉ muốn xem kiểu provider hoặc lọc implementation trước khi tạo đối tượng.

Khi chỉ cần metadata, dùng **loader.stream()** và **Provider.type()**.

### 8.3. Nghĩ rằng stream() luôn không có chi phí

Stream không tạo service instance chỉ vì ứng dụng lấy provider handle, nhưng việc khám phá provider vẫn có chi phí. ServiceLoader có thể phải đọc cấu hình, tìm provider trong module layer hoặc class loader, và nạp kiểu provider để cung cấp **Class** cho **type()**.

Do đó, stream trì hoãn việc tạo service instance, không có nghĩa là mọi hoạt động khám phá đều miễn phí hoặc bị trì hoãn cho tới **get()**.

### 8.4. Không xử lý lỗi khi khám phá provider

ServiceLoader thường phát hiện lỗi trong lúc duyệt thay vì ngay tại lời gọi **load()**. Các tình huống như provider không tồn tại, cấu hình sai, kiểu không tương thích hoặc constructor/provider method lỗi có thể dẫn đến **ServiceConfigurationError** khi provider được tìm hoặc khởi tạo.

Đặt xử lý lỗi ở nơi thực sự duyệt stream hoặc gọi **get()**. Nếu việc tìm provider là một phần của quá trình khởi động ứng dụng, hãy ghi log service type, provider type và nguyên nhân để việc chẩn đoán rõ ràng.

## 9. Một số lưu ý khi dùng trong ứng dụng thực tế

- **Lọc theo metadata ổn định:** nếu cần lựa chọn theo tính năng, phiên bản hoặc loại triển khai, nên định nghĩa metadata/annotation rõ ràng thay vì phụ thuộc vào thứ tự provider.
- **Không dựa vào thứ tự khám phá:** khi nhiều provider cùng tồn tại, hãy sắp xếp hoặc áp dụng chính sách lựa chọn rõ ràng nếu thứ tự ảnh hưởng kết quả.
- **Chọn ModuleLayer khi cần:** nếu provider nằm trong một module layer tùy chỉnh, dùng overload **ServiceLoader.load(layer, service)** để tìm provider trong layer được chỉ định.
- **Chú ý cache của iterator:** iterator có thể trả instance đã được ServiceLoader tạo trước đó. **reload()** xóa cache của loader để các lần duyệt sau tải lại provider.
- **Không chia sẻ ServiceLoader tùy tiện giữa nhiều thread:** các instance ServiceLoader không được thiết kế để dùng đồng thời an toàn từ nhiều thread. Hãy quản lý vòng đời và đồng bộ phù hợp.
- **Quản lý lifecycle riêng:** ServiceLoader tìm và tạo provider; nó không tự định nghĩa quy tắc đóng tài nguyên của service. Nếu implementation giữ file, socket, thread hoặc connection, ứng dụng cần có hợp đồng lifecycle rõ ràng, chẳng hạn interface mở rộng **AutoCloseable**.

## 10. Checklist lựa chọn và khởi tạo provider

- Service type được định nghĩa bằng interface hoặc abstraction mà ứng dụng cần.
- Mô-đun tiêu thụ khai báo **uses** cho service type.
- Mô-đun provider khai báo **provides ... with ...** và provider hợp lệ.
- Dùng **ServiceLoader.load()** để tạo loader.
- Dùng **stream()** khi cần xem hoặc lọc provider trước khi có instance.
- Dùng **Provider.type()** để kiểm tra kiểu provider.
- Chỉ gọi **Provider.get()** sau khi đã chọn provider.
- Dùng **iterator()** khi cần lấy service instance trực tiếp; nhớ rằng **next()** có thể khởi tạo provider.
- Không gọi **map(Provider::get)** trước khi lọc nếu không muốn khởi tạo các provider bị loại.
- Xử lý lỗi khám phá và khởi tạo tại nơi stream được duyệt hoặc **get()** được gọi.
- Quản lý lifecycle và tính an toàn đa luồng của service theo nhu cầu ứng dụng.

**Nguyên tắc sử dụng:** **ServiceLoader.stream()** cho phép ứng dụng quyết định provider nào cần được khởi tạo. **Provider.type()** dùng để xem kiểu; **Provider.get()** là thao tác lấy instance. Khi lọc trước rồi mới gọi **get()**, ứng dụng có thể tránh khởi tạo các implementation không được chọn và giữ thời điểm tạo đối tượng trong tầm kiểm soát.