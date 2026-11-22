# Directive provides trong Java Module System

## Mục tiêu

Sau bài này, bạn có thể giải thích directive \`provides\` trong Java Platform Module System (JPMS); khai báo một module cung cấp implementation cho service; kết hợp \`provides\` với \`uses\` và \`ServiceLoader\`; phân biệt service API, provider và consumer; chọn giữa provider constructor và provider factory method; đóng gói, chạy và kiểm tra các module trên module path; đồng thời chẩn đoán các lỗi discovery phổ biến.

## 1. \`provides\` là gì?

Từ Java 9, JPMS cho phép module mô tả những service mà nó cung cấp. Trong file \`module-info.java\`, directive:

~~~java
provides com.example.codec.spi.Codec
    with com.example.codec.provider.impl.Utf8Codec;
~~~

có nghĩa module hiện tại đăng ký class \`Utf8Codec\` làm service provider cho service type \`Codec\`.

Service thường là một interface hoặc abstract class mô tả một khả năng mà ứng dụng cần, ví dụ:

- Bộ mã hóa/giải mã dữ liệu.
- Driver kết nối cơ sở dữ liệu.
- Bộ phân tích định dạng file.
- Nhà cung cấp logging hoặc security.
- Plugin mở rộng một chức năng của ứng dụng.

Consumer biết service API và gọi nó thông qua \`ServiceLoader\`. Consumer không cần biết tên hoặc package của implementation cụ thể. Provider module tự đăng ký implementation bằng \`provides\`.

Mô hình này giúp tách ba vai trò:

| Thành phần | Trách nhiệm |
|---|---|
| Service API | Định nghĩa interface/abstract class và hợp đồng sử dụng |
| Provider module | Cung cấp một hoặc nhiều implementation của service |
| Consumer module | Khai báo service cần dùng và tìm provider lúc chạy |

\`provides\` không phải lời gọi method và không tự tạo object ngay khi JVM khởi động. Nó là metadata trong module descriptor để hệ thống module và \`ServiceLoader\` có thể tìm provider khi ứng dụng yêu cầu.

## 2. Cú pháp và vị trí trong module-info.java

Cú pháp tổng quát:

~~~java
provides ServiceType
    with ProviderType1, ProviderType2;
~~~

- \`ServiceType\` là kiểu service mà consumer biết.
- Sau \`with\` là một hoặc nhiều provider class thuộc module đang khai báo directive.
- Mỗi provider được phân tách bằng dấu phẩy.
- Directive kết thúc bằng dấu chấm phẩy.
- Tên type thường được viết đầy đủ theo package để descriptor rõ ràng.

Ví dụ:

~~~java
module com.example.image.provider {
    requires com.example.image.api;

    provides com.example.image.spi.ImageCodec
        with com.example.image.provider.PngCodec,
             com.example.image.provider.JpegCodec;
}
~~~

Một module có thể cung cấp nhiều service khác nhau bằng nhiều directive \`provides\`. Với cùng một service type, module chỉ được có một directive \`provides\`; nếu cần nhiều implementation, liệt kê chúng trong cùng mệnh đề \`with\`.

Provider class phải được khai báo trong chính module đang chứa directive \`provides\`. Không thể dùng directive của module A để đăng ký class provider thuộc module B.

## 3. Phân biệt provides, uses, requires và exports

Bốn directive thường xuất hiện cùng nhau nhưng có mục đích khác nhau:

| Directive | Câu hỏi mà nó trả lời |
|---|---|
| \`requires\` | Module này phụ thuộc vào module nào? |
| \`exports\` | Package nào được module khác truy cập? |
| \`uses\` | Module này cần tìm provider cho service nào? |
| \`provides ... with ...\` | Module này cung cấp provider nào cho service nào? |

Ví dụ một provider module:

~~~java
module com.example.codec.provider {
    requires com.example.codec.api;

    provides com.example.codec.spi.Codec
        with com.example.codec.provider.impl.Utf8Codec;
}
~~~

Module provider cần \`requires\` module chứa service API để tham chiếu interface \`Codec\`. Nó dùng \`provides\` để đăng ký implementation.

Ví dụ consumer module:

~~~java
module com.example.codec.app {
    requires com.example.codec.api;

    uses com.example.codec.spi.Codec;
}
~~~

Consumer cần \`requires\` API module vì source code gọi các method của interface \`Codec\`. Consumer khai báo \`uses\` để được phép tìm provider của service đó bằng \`ServiceLoader\`.

Thông thường consumer **không cần** \`requires com.example.codec.provider\`. Đây là lợi ích quan trọng của service abstraction: consumer phụ thuộc vào API, còn provider được phát hiện qua module resolution và service loading.

### Service API cần được export

Nếu service interface nằm trong module riêng, package chứa interface phải được export cho consumer và provider sử dụng:

~~~java
module com.example.codec.api {
    exports com.example.codec.spi;
}
~~~

Provider implementation package thường không cần export. Module descriptor \`provides\` cho phép đăng ký implementation mà không phải công khai package nội bộ cho mọi module. Đây là cách giữ encapsulation tốt hơn.

\`exports\` và \`opens\` cũng có ý nghĩa khác nhau: \`exports\` cho phép truy cập các public type theo quy tắc module; \`opens\` cho phép deep reflection. Việc đăng ký service bằng \`provides\` tự nó không có nghĩa package provider cần mở cho reflection.

## 4. Hai cách tạo service provider

JPMS hỗ trợ hai cách để \`ServiceLoader\` tạo một provider được khai báo bằng \`provides\`.

### Cách 1: Provider class triển khai service và có public no-arg constructor

Đây là cách trực tiếp, thường dùng nhất:

~~~java
package com.example.codec.provider.impl;

import com.example.codec.spi.Codec;

public class Utf8Codec implements Codec {

    public Utf8Codec() {
    }

    @Override
    public String encode(String input) {
        return "UTF-8:" + input;
    }
}
~~~

Module descriptor:

~~~java
module com.example.codec.provider {
    requires com.example.codec.api;

    provides com.example.codec.spi.Codec
        with com.example.codec.provider.impl.Utf8Codec;
}
~~~

Trong trường hợp này:

- Provider class phải là public.
- Provider class phải là top-level class hoặc static nested class.
- Provider phải implement service type (hoặc là subtype của service class).
- Provider phải có public constructor không tham số.
- \`ServiceLoader\` tạo instance thông qua constructor đó.

Nếu class không khai báo constructor nào, compiler có thể tạo default constructor; tuy nhiên provider cần thỏa yêu cầu public no-arg constructor. Khi đã khai báo constructor có tham số riêng, đừng giả định compiler vẫn tạo default constructor.

### Cách 2: Provider method tên provider()

Từ Java 9, provider class có thể khai báo một public static method tên chính xác là \`provider\`, không có tham số và trả về một subtype của service:

~~~java
package com.example.codec.provider.impl;

import com.example.codec.spi.Codec;

public final class Utf8CodecFactory {

    public static Codec provider() {
        return new Utf8Codec();
    }
}
~~~

Module descriptor đăng ký factory class:

~~~java
provides com.example.codec.spi.Codec
    with com.example.codec.provider.impl.Utf8CodecFactory;
~~~

Ở dạng này, class \`Utf8CodecFactory\` không cần tự implement \`Codec\`; \`ServiceLoader\` gọi method \`provider()\` để lấy object thực hiện service.

Provider method cần đáp ứng:

- Có modifier \`public static\`.
- Tên method là \`provider\`.
- Không nhận tham số.
- Kiểu trả về là service type hoặc subtype của service type.
- Chỉ có một provider method hợp lệ cho provider class.

Cách factory hữu ích khi việc tạo implementation cần cấu hình, chọn object cụ thể hoặc ẩn class implementation thật. Nếu provider method trả về null hoặc ném exception, quá trình tải provider có thể thất bại bằng \`ServiceConfigurationError\`.

### So sánh hai cách

| Tiêu chí | Provider constructor | Provider method |
|---|---|---|
| Provider class phải implement service? | Có | Không nhất thiết |
| Cách tạo instance | Public constructor không tham số | Public static \`provider()\` |
| Giá trị trả về | Chính instance provider | Object do factory trả về |
| Phù hợp khi | Implementation đơn giản | Cần factory hoặc che giấu implementation |
| Có cần public no-arg constructor? | Có | Không, nếu dùng provider method hợp lệ |

Nếu provider class có provider method hợp lệ, \`ServiceLoader\` sử dụng method đó để tạo provider. Nếu không có provider method, nó dùng provider constructor và provider class phải là subtype của service.

## 5. Ví dụ hoàn chỉnh: API, provider và consumer

Ví dụ dưới đây tạo ba module độc lập. Provider cung cấp một implementation của service \`Codec\`; consumer tìm và gọi implementation thông qua \`ServiceLoader\`.

### Cấu trúc thư mục

~~~text
project/
└── src/
    ├── com.example.codec.api/
    │   ├── module-info.java
    │   └── com/example/codec/spi/Codec.java
    ├── com.example.codec.provider/
    │   ├── module-info.java
    │   └── com/example/codec/provider/impl/Utf8Codec.java
    └── com.example.codec.app/
        ├── module-info.java
        └── com/example/codec/app/Main.java
~~~

### Module 1: service API

File \`src/com.example.codec.api/module-info.java\`:

~~~java
module com.example.codec.api {
    exports com.example.codec.spi;
}
~~~

File \`src/com.example.codec.api/com/example/codec/spi/Codec.java\`:

~~~java
package com.example.codec.spi;

public interface Codec {
    String encode(String input);
}
~~~

API module chỉ công khai package chứa service interface.

### Module 2: provider

File \`src/com.example.codec.provider/module-info.java\`:

~~~java
module com.example.codec.provider {
    requires com.example.codec.api;

    provides com.example.codec.spi.Codec
        with com.example.codec.provider.impl.Utf8Codec;
}
~~~

File \`src/com.example.codec.provider/com/example/codec/provider/impl/Utf8Codec.java\`:

~~~java
package com.example.codec.provider.impl;

import com.example.codec.spi.Codec;

public class Utf8Codec implements Codec {

    public Utf8Codec() {
    }

    @Override
    public String encode(String input) {
        return "UTF-8:" + input;
    }
}
~~~

Package \`com.example.codec.provider.impl\` không được export. Consumer không cần import hoặc gọi trực tiếp \`Utf8Codec\`.

### Module 3: consumer application

File \`src/com.example.codec.app/module-info.java\`:

~~~java
module com.example.codec.app {
    requires com.example.codec.api;

    uses com.example.codec.spi.Codec;
}
~~~

File \`src/com.example.codec.app/com/example/codec/app/Main.java\`:

~~~java
package com.example.codec.app;

import com.example.codec.spi.Codec;
import java.util.ServiceLoader;

public class Main {

    public static void main(String[] args) {
        ServiceLoader<Codec> loader =
                ServiceLoader.load(Codec.class);

        for (Codec codec : loader) {
            System.out.println(codec.encode("hello"));
        }
    }
}
~~~

Consumer chỉ import \`Codec\` và \`ServiceLoader\`. Nó không import \`Utf8Codec\` và không khai báo \`requires com.example.codec.provider\`.

### Biên dịch cả ba module

Mở terminal tại thư mục \`project\`:

~~~bash
javac --module-source-path src -d out -m com.example.codec.api,com.example.codec.provider,com.example.codec.app
~~~

Tùy chọn:

- \`--module-source-path src\` chỉ định thư mục gốc chứa source của các module.
- \`-d out\` đặt class file đã biên dịch vào thư mục out theo từng module.
- \`-m\` chọn các module cần biên dịch; compiler xử lý dependency giữa chúng.

Sau khi biên dịch, cấu trúc output có dạng:

~~~text
out/
├── com.example.codec.api/
│   ├── module-info.class
│   └── com/example/codec/spi/Codec.class
├── com.example.codec.provider/
│   ├── module-info.class
│   └── com/example/codec/provider/impl/Utf8Codec.class
└── com.example.codec.app/
    ├── module-info.class
    └── com/example/codec/app/Main.class
~~~

### Chạy consumer trên module path

~~~bash
java --module-path out -m com.example.codec.app/com.example.codec.app.Main
~~~

Output chính xác:

~~~text
UTF-8:hello
~~~

Khi khởi chạy module consumer, module resolution có thể bind provider module quan sát được trên module path vì consumer khai báo \`uses\` và provider module khai báo \`provides\`. \`ServiceLoader\` sau đó tìm và khởi tạo provider khi vòng lặp yêu cầu phần tử.

Để quan sát quá trình module resolution:

~~~bash
java --show-module-resolution --module-path out -m com.example.codec.app/com.example.codec.app.Main
~~~

Thông tin resolution được in thêm trên stderr; output ứng dụng vẫn là \`UTF-8:hello\`.

## 6. Đóng gói thành modular JAR

Các module đã biên dịch có thể được đóng gói thành ba JAR riêng:

~~~bash
mkdir dist
jar --create --file dist/com.example.codec.api.jar -C out/com.example.codec.api .
jar --create --file dist/com.example.codec.provider.jar -C out/com.example.codec.provider .
jar --create --file dist/com.example.codec.app.jar -C out/com.example.codec.app .
~~~

Mỗi JAR có \`module-info.class\` ở root nên là modular JAR với module name lấy từ descriptor, không phải suy luận từ tên file.

Kiểm tra descriptor của provider:

~~~bash
jar --describe-module --file dist/com.example.codec.provider.jar
~~~

Trong kết quả, tìm module name và directive cung cấp service, tương tự:

~~~text
com.example.codec.provider
requires com.example.codec.api
provides com.example.codec.spi.Codec with com.example.codec.provider.impl.Utf8Codec
~~~

Chạy ứng dụng từ thư mục chứa ba modular JAR:

~~~bash
java --module-path dist -m com.example.codec.app/com.example.codec.app.Main
~~~

Output:

~~~text
UTF-8:hello
~~~

Không cần đặt provider module vào \`requires\` của app module. Module resolution phát hiện provider qua service binding khi module consumer sử dụng service và provider module có mặt trong tập module quan sát được.

## 7. Vì sao provider package thường không export?

Một trong các lợi ích lớn nhất của JPMS service là provider có thể được tìm thấy mà không công khai package implementation.

Ví dụ:

~~~java
module com.example.codec.provider {
    requires com.example.codec.api;

    provides com.example.codec.spi.Codec
        with com.example.codec.provider.impl.Utf8Codec;
}
~~~

Module không có:

~~~java
exports com.example.codec.provider.impl;
~~~

Điều đó có nghĩa code của consumer không thể truy cập trực tiếp public class \`Utf8Codec\` chỉ bằng cách import nó như một API công khai. Nhưng service loader vẫn có thể tìm và khởi tạo provider theo metadata \`provides\`.

Cách thiết kế này giúp provider thay implementation mà không buộc consumer phụ thuộc vào class cụ thể. Ví dụ module provider có thể thay \`Utf8Codec\` bằng implementation mới, trong khi service contract \`Codec\` và code consumer vẫn giữ nguyên.

Chỉ export package provider nếu đó thực sự là API mà module khác cần gọi trực tiếp. Không export chỉ để làm cho \`ServiceLoader\` hoạt động.

## 8. Nhiều provider cho cùng một service

Một directive có thể đăng ký nhiều provider:

~~~java
provides com.example.codec.spi.Codec
    with com.example.codec.provider.impl.Utf8Codec,
         com.example.codec.provider.impl.Base64Codec,
         com.example.codec.provider.impl.HexCodec;
~~~

Consumer có thể lặp qua tất cả provider:

~~~java
for (Codec codec : ServiceLoader.load(Codec.class)) {
    System.out.println(codec.encode("hello"));
}
~~~

ServiceLoader có thể tìm provider từ nhiều module. Không nên dựa vào thứ tự giữa các module khác nhau nếu ứng dụng cần một provider cụ thể. Nếu ứng dụng cần lựa chọn, hãy bổ sung metadata hoặc method trong service contract để đánh giá capability/priority, hoặc để người dùng cấu hình provider mong muốn.

Không có provider nào cũng là tình huống hợp lệ về mặt API: iterator có thể rỗng. Consumer nên xác định rõ hành vi khi service không có implementation.

## 9. ServiceLoader hoạt động như thế nào?

\`ServiceLoader\` là API tiêu chuẩn để tìm và tải service provider.

~~~java
ServiceLoader<Codec> loader =
        ServiceLoader.load(Codec.class);
~~~

Khi code gọi \`iterator()\`, \`for-each\`, \`findFirst()\` hoặc thao tác trên stream, provider được tìm và khởi tạo theo nhu cầu. Việc discovery và instantiation là lazy; chỉ gọi \`load\` không đồng nghĩa mọi provider lập tức được tạo object.

Một số API quan trọng:

| API | Mục đích |
|---|---|
| \`ServiceLoader.load(Codec.class)\` | Tạo loader dùng thread context class loader |
| \`iterator()\` | Duyệt và khởi tạo provider theo nhu cầu |
| \`stream()\` | Duyệt các mô tả provider trước khi lấy instance |
| \`reload()\` | Xóa cache provider đã được loader tìm thấy |
| \`ServiceLoader.load(layer, Codec.class)\` | Tìm provider trong một ModuleLayer và các layer cha |

ServiceLoader cache các provider đã tải trong một loader. Khi môi trường provider thay đổi theo cách ứng dụng quản lý được, có thể gọi \`reload()\` để xóa cache. Không nên chia sẻ cùng một ServiceLoader instance giữa nhiều thread mà không có đồng bộ thích hợp.

### Kiểm tra provider trước khi tạo instance

\`stream()\` trả về các đối tượng \`ServiceLoader.Provider\`. Chúng cho phép xem provider type và lọc trước khi gọi \`get()\` để tạo instance:

~~~java
ServiceLoader<Codec> loader =
        ServiceLoader.load(Codec.class);

loader.stream()
      .map(ServiceLoader.Provider::type)
      .forEach(System.out::println);
~~~

Cách này hữu ích khi ứng dụng muốn xem metadata hoặc chọn provider trước khi khởi tạo. Với provider factory, \`type()\` có thể biểu diễn kiểu trả về của provider method; dùng \`get()\` để lấy instance service.

## 10. Quy tắc và giới hạn của directive provides

Theo Java Language Specification, các điều kiện quan trọng gồm:

- Service type phải là kiểu có thể truy cập từ module hiện tại; enum không được dùng làm service trong directive \`provides\`.
- Mỗi provider phải là public class hoặc interface, top-level hoặc static nested.
- Mỗi provider phải được khai báo trong chính module đang chứa directive.
- Provider có provider method thì method phải là public static, tên \`provider\`, không có tham số và trả về subtype của service.
- Nếu không có provider method, provider phải có public no-arg constructor và là subtype của service.
- Một module không được khai báo nhiều directive \`provides\` cho cùng service.
- Một provider không được liệt kê lặp lại trong cùng một directive.

Những điều kiện này được compiler kiểm tra ở thời điểm biên dịch khi có đủ thông tin module/type. Một số lỗi chỉ xuất hiện lúc chạy nếu provider không thể được nạp hoặc khởi tạo trong môi trường thực tế.

### Một số ví dụ không hợp lệ

Provider không public:

~~~java
class HiddenCodec implements Codec {
    public String encode(String input) {
        return input;
    }
}
~~~

Provider không có public no-arg constructor và không có provider method:

~~~java
public class ConfiguredCodec implements Codec {
    public ConfiguredCodec(String charset) {
    }

    public String encode(String input) {
        return input;
    }
}
~~~

Provider method trả về kiểu không tương thích với service:

~~~java
public class CodecFactory {
    public static String provider() {
        return "not a Codec";
    }
}
~~~

Các ví dụ này không đáp ứng điều kiện provider tương ứng. Hãy sửa class/provider method theo một trong hai cơ chế hợp lệ đã trình bày.

## 11. Khác biệt giữa named module và classpath provider

Java có thể tìm service provider trong cả named modules và classpath, nhưng cách đăng ký khác nhau.

| Môi trường | Cách đăng ký provider |
|---|---|
| Explicit named module | Directive \`provides Service with Provider;\` trong \`module-info.java\` |
| Classpath / unnamed module | File \`META-INF/services/<fully-qualified-service-name>\` |
| Automatic module trên module path | Provider configuration file theo quy tắc ServiceLoader; provider cần public no-arg constructor |

Ví dụ với classpath, JAR provider có file:

~~~text
META-INF/services/com.example.codec.spi.Codec
~~~

Nội dung file:

~~~text
com.example.codec.provider.impl.Utf8Codec
~~~

Mỗi dòng là một provider class name. Cách đăng ký này có lịch sử từ trước Java 9 và vẫn được hỗ trợ để tương thích.

Với explicit named module, nên khai báo \`provides\` trong module descriptor. Không cần đồng thời tạo provider configuration file cho cùng provider trong named module; ServiceLoader bỏ qua tên provider trong file cấu hình nếu provider đó đã được khai báo bởi named module.

Automatic module không có explicit \`module-info.java\`; do đó nó không thể khai báo directive \`provides\` của riêng mình. Quy tắc provider constructor áp dụng cho provider được phát hiện qua provider configuration file trong trường hợp này; provider method không được hỗ trợ như đối với explicit named module.

## 12. Lỗi thường gặp và cách xử lý

### Consumer quên directive uses

**Dấu hiệu:** gọi \`ServiceLoader.load(Service.class)\` từ explicit named module gây \`ServiceConfigurationError\`.

**Nguyên nhân:** module consumer chưa khai báo service trong \`uses\`.

**Cách xử lý:** thêm:

~~~java
uses com.example.codec.spi.Codec;
~~~

vào \`module-info.java\` của consumer, biên dịch lại và chạy lại.

### Provider không được tìm thấy

**Dấu hiệu:** ServiceLoader không trả về provider nào.

**Nguyên nhân có thể gặp:**

- Provider module không nằm trên module path.
- Provider module không được quan sát hoặc không được resolve vào module layer.
- Thiếu directive \`provides\` hoặc sai service/provider class name.
- Consumer không khai báo \`uses\`.
- Module path đang trỏ nhầm thư mục hoặc JAR.

**Cách xử lý:** kiểm tra \`jar --describe-module\`, module path, module resolution và module descriptor. Dùng \`--show-module-resolution\` để quan sát module graph lúc khởi động.

### Provider không có public no-arg constructor

**Dấu hiệu:** \`ServiceConfigurationError\` khi ServiceLoader khởi tạo provider.

**Nguyên nhân:** provider không khai báo provider method hợp lệ và cũng không có public constructor không tham số.

**Cách xử lý:** thêm public no-arg constructor hoặc dùng public static no-arg \`provider()\` method có return type phù hợp.

### Provider method không hợp lệ

**Dấu hiệu:** provider không được khởi tạo hoặc xuất hiện \`ServiceConfigurationError\`.

**Nguyên nhân:** method tên sai, không public/static, có tham số, return type không tương thích, trả null hoặc ném exception.

**Cách xử lý:** kiểm tra method phải là public static, tên chính xác \`provider\`, không có tham số và trả về service type/subtype; bảo đảm factory không trả null.

### Provider package bị export quá rộng

**Dấu hiệu:** module descriptor có nhiều package implementation public dù consumer chỉ cần service interface.

**Nguyên nhân:** nhầm lẫn giữa \`provides\` và \`exports\`.

**Cách xử lý:** giữ package service API được export; để provider implementation package encapsulated trừ khi có nhu cầu công khai thực sự.

### Lỗi khi lặp qua ServiceLoader

**Dấu hiệu:** \`ServiceConfigurationError\` xuất hiện khi gọi \`hasNext()\`, \`next()\` hoặc xử lý stream.

**Nguyên nhân:** provider class không thể nạp, constructor/factory thất bại, provider method trả null hoặc có lỗi cấu hình.

**Cách xử lý:** đọc cause của error, kiểm tra module descriptor, classpath/module path và provider initialization. Vì loading lazy, lỗi có thể xuất hiện ở bước lặp chứ không phải ngay tại \`ServiceLoader.load()\`.

### Dùng sai module path và classpath

**Dấu hiệu:** module API hoặc provider không tìm thấy, hoặc app chạy nhưng không phát hiện provider.

**Nguyên nhân:** modular JAR được đặt trên classpath thay vì module path, hoặc module path thiếu thư mục/JAR cần thiết.

**Cách xử lý:** dùng \`--module-path\` cho named modules và chạy app bằng \`-m module/class\`. Với ứng dụng classpath truyền thống, dùng \`-cp\` và provider configuration file.

## 13. Khi nào nên dùng provides?

Nên dùng JPMS service khi:

- Một API có nhiều implementation thay thế được.
- Consumer không nên phụ thuộc trực tiếp vào implementation module.
- Muốn đóng gói plugin/provider thành module độc lập.
- Muốn giữ package implementation không export.
- Muốn framework hoặc ứng dụng phát hiện provider lúc chạy.
- Muốn thay provider bằng module khác mà không thay đổi code consumer.

Không cần dùng service loader cho mọi lời gọi method. Nếu ứng dụng chỉ có một implementation cố định và không cần mở rộng, dependency injection trực tiếp hoặc constructor injection có thể đơn giản hơn.

Service abstraction nên phản ánh một extension point thực sự. Đừng tạo service interface chỉ để bọc một class duy nhất nếu không có nhu cầu thay thế hoặc khám phá implementation.

## 14. Checklist triển khai

- [ ] Service API nằm trong package được export bởi module API.
- [ ] Provider module có \`requires\` tới module chứa service type.
- [ ] Provider module khai báo \`provides Service with Provider;\`.
- [ ] Provider class là public và top-level hoặc static nested.
- [ ] Provider dùng public no-arg constructor hoặc provider method hợp lệ.
- [ ] Consumer module có \`requires\` service API.
- [ ] Consumer module khai báo \`uses Service;\`.
- [ ] Consumer không phụ thuộc trực tiếp vào provider module nếu không cần.
- [ ] Provider implementation package không export nếu không phải API công khai.
- [ ] Provider module có mặt trên module path/module layer được resolve.
- [ ] Đã kiểm tra descriptor bằng \`jar --describe-module\`.
- [ ] Đã chạy thử \`ServiceLoader\` và kiểm tra trường hợp không có provider.
- [ ] Đã xử lý \`ServiceConfigurationError\` phù hợp.
- [ ] Không phụ thuộc vào thứ tự provider giữa các module nếu chưa có hợp đồng rõ ràng.

## 15. Tài liệu tham khảo chính thức

- [Java Language Specification, Java SE 26 — §7.7.3 Service Consumption](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-7.html#jls-7.7.3) — directive \`uses\` và quy tắc service consumption.
- [Java Language Specification, Java SE 26 — §7.7.4 Service Provision](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-7.html#jls-7.7.4) — cú pháp và quy tắc provider của directive \`provides\`.
- [ServiceLoader — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html) — discovery, provider constructor, provider method, lazy loading, caching và lỗi cấu hình.
- [ServiceLoader.Provider — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.Provider.html) — xem provider type và lấy provider instance.
- [ModuleDescriptor.Builder — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/module/ModuleDescriptor.Builder.html) — API tạo module descriptor và khai báo service provider.

Directive \`provides\` là phần đăng ký service provider của JPMS. Khi kết hợp đúng với service API, \`uses\`, \`ServiceLoader\` và module path, ứng dụng có thể khám phá implementation mà vẫn giữ ranh giới module và tính đóng gói rõ ràng.
