# Khai báo phía dùng bằng `uses` trong JPMS

Trong Java Platform Module System (JPMS), một mô-đun dùng dịch vụ cần khai báo nhu cầu đó bằng chỉ thị `uses` trong `module-info.java`. Chỉ thị này nói rằng mô-đun cần một implementation của service type đã nêu. Ứng dụng thường tìm implementation bằng `ServiceLoader`, trong khi mô-đun provider đăng ký implementation bằng `provides ... with ...`.

`uses` giúp consumer phụ thuộc vào hợp đồng dịch vụ. Consumer biết interface và hành vi cần gọi; nó không cần biết tên class triển khai hoặc package nội bộ của provider.

## 1. Vai trò của `uses`

Cú pháp:

```java
module com.example.greeter.app {
    requires com.example.greeter.api;
    uses com.example.greeter.api.Greeter;
}
```

`uses` nhận tên đầy đủ của service type. Service type thường là interface hoặc abstract class được mô-đun API export. Consumer cần `requires` mô-đun chứa service type để đọc và sử dụng kiểu đó; `uses` khai báo nhu cầu tìm provider cho kiểu ấy.

`uses` không tạo implementation, không chọn provider và cũng không thay thế `requires`. Nó là metadata trong module descriptor để JPMS và `ServiceLoader` biết mô-đun này có nhu cầu dùng dịch vụ.

## 2. Ba phía trong một dịch vụ mô-đun

Một thiết kế service thường có ba vai trò:

| Vai trò | Khai báo trong `module-info.java` | Trách nhiệm |
| --- | --- | --- |
| API / service type | `exports` package chứa interface | Công bố hợp đồng mà consumer và provider cùng sử dụng. |
| Consumer | `requires` API và `uses` service type | Tìm và gọi implementation thông qua hợp đồng. |
| Provider | `requires` API và `provides ... with ...` | Đăng ký class cung cấp implementation. |

Quan hệ tổng quát:

```text
com.example.greeter.app  --requires-->  com.example.greeter.api
          |                                  ^
          | uses Greeter                     | implements
          v                                  |
       ServiceLoader              com.example.greeter.english
                                             provides Greeter
```

Consumer không cần khai báo `requires com.example.greeter.english`. Nó chỉ phụ thuộc API. Provider cũng phụ thuộc API để triển khai đúng hợp đồng. Khi ứng dụng được resolve với service binding, provider phù hợp trên module path có thể được đưa vào module layer.

## 3. Ví dụ hoàn chỉnh với `ServiceLoader`

Ví dụ dưới đây có ba mô-đun: API định nghĩa `Greeter`, provider cung cấp lời chào tiếng Anh, còn ứng dụng chỉ khai báo `uses` và tìm provider lúc chạy.

```text
src/
├── com.example.greeter.api/
│   ├── module-info.java
│   └── com/example/greeter/api/Greeter.java
├── com.example.greeter.english/
│   ├── module-info.java
│   └── com/example/greeter/english/EnglishGreeter.java
└── com.example.greeter.app/
    ├── module-info.java
    └── com/example/greeter/app/Main.java
```

**`src/com.example.greeter.api/module-info.java`**

```java
module com.example.greeter.api {
    exports com.example.greeter.api;
}
```

**`src/com.example.greeter.api/com/example/greeter/api/Greeter.java`**

```java
package com.example.greeter.api;

public interface Greeter {
    String greet(String name);
}
```

Đây là hợp đồng công khai. Consumer chỉ cần biết phương thức `greet`; API không phụ thuộc vào class provider cụ thể.

**`src/com.example.greeter.english/module-info.java`**

```java
module com.example.greeter.english {
    requires com.example.greeter.api;

    provides com.example.greeter.api.Greeter
            with com.example.greeter.english.EnglishGreeter;
}
```

Provider khai báo nó cung cấp implementation cho service type `Greeter`.

**`src/com.example.greeter.english/com/example/greeter/english/EnglishGreeter.java`**

```java
package com.example.greeter.english;

import com.example.greeter.api.Greeter;

public final class EnglishGreeter implements Greeter {
    public EnglishGreeter() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

Với dạng provider class này, implementation phải là class public có public constructor không tham số. Package implementation không cần export cho consumer.

**`src/com.example.greeter.app/module-info.java`**

```java
module com.example.greeter.app {
    requires com.example.greeter.api;
    uses com.example.greeter.api.Greeter;
}
```

Đây là phần khai báo phía dùng. Consumer đọc được API và thông báo nó cần service `Greeter`; nó không khai báo dependency trực tiếp tới module English provider.

**`src/com.example.greeter.app/com/example/greeter/app/Main.java`**

```java
package com.example.greeter.app;

import com.example.greeter.api.Greeter;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        Greeter greeter = ServiceLoader.load(Greeter.class)
                .findFirst()
                .orElseThrow(() -> new IllegalStateException("No Greeter provider found"));

        System.out.println(greeter.greet("Lan"));
    }
}
```

Biên dịch từ thư mục chứa `src`:

```powershell
javac --release 17 --module-source-path src -d out -m com.example.greeter.api,com.example.greeter.english,com.example.greeter.app
```

Chạy ứng dụng:

```powershell
java --module-path out -m com.example.greeter.app/com.example.greeter.app.Main
```

STDOUT:

```text
Hello, Lan!
```

Consumer chỉ gọi phương thức trên interface `Greeter`. Khi cần thay đổi cách chào, có thể thêm provider khác mà không cần sửa mã consumer, miễn là provider tuân thủ cùng hợp đồng và được đưa vào module path/runtime layer.

## 4. Điều gì xảy ra nếu thiếu `uses`?

Với consumer là named module, `ServiceLoader.load(Greeter.class)` kiểm tra mô-đun gọi có khai báo sử dụng service type hay không. Nếu thiếu `uses`, thao tác tìm provider có thể ném `ServiceConfigurationError` với thông báo mô-đun consumer không khai báo `uses` cho service đó.

Vì vậy, chỉ có `requires com.example.greeter.api` là chưa đủ. `requires` cho phép consumer đọc service type; `uses` khai báo consumer có ý định tìm provider của service type đó.

Kiểm tra descriptor đã biên dịch bằng cách đóng gói ứng dụng thành JAR:

```powershell
New-Item -ItemType Directory -Force build | Out-Null
jar --create --file build/com.example.greeter.app.jar -C out/com.example.greeter.app .
jar --describe-module --file build/com.example.greeter.app.jar
```

Trong kết quả cần có các dòng tương ứng:

```text
requires com.example.greeter.api
uses com.example.greeter.api.Greeter
```

Đây là cách xác nhận chỉ thị `uses` thực sự nằm trong descriptor của artifact được đóng gói.

## 5. `uses` và `provides` phối hợp như thế nào?

`uses` nằm ở phía consumer; `provides` nằm ở phía provider. Cả hai phải chỉ cùng một service type. Service type cần được export từ mô-đun API để các mô-đun khác có thể đọc và sử dụng nó.

Ví dụ:

```java
// Consumer
module com.example.greeter.app {
    requires com.example.greeter.api;
    uses com.example.greeter.api.Greeter;
}
```

```java
// Provider
module com.example.greeter.english {
    requires com.example.greeter.api;
    provides com.example.greeter.api.Greeter
            with com.example.greeter.english.EnglishGreeter;
}
```

Provider class trong ví dụ dùng public no-argument constructor. JPMS cũng hỗ trợ provider method: class được nêu trong `provides` có thể khai báo phương thức `public static provider()` trả về service type hoặc subtype phù hợp. Cơ chế provider method hữu ích khi việc tạo đối tượng cần factory hoặc cấu hình riêng; class provider không nhất thiết phải tự triển khai service interface trong trường hợp này.

Không export package provider chỉ để `ServiceLoader` nhìn thấy implementation được khai báo bằng `provides` trong named module. Consumer dùng service type công khai; JPMS xử lý provider theo module descriptor.

## 6. Nhiều provider và lựa chọn implementation

Một service có thể có nhiều provider. `ServiceLoader` tìm các provider phù hợp và nạp chúng theo cơ chế lazy. `findFirst()` phù hợp với ví dụ có một provider hoặc khi ứng dụng chấp nhận provider đầu tiên; không nên dùng thứ tự phát hiện làm chính sách nghiệp vụ nếu ứng dụng cần chọn implementation xác định.

Khi có nhiều provider, có thể duyệt các kết quả và áp dụng tiêu chí lựa chọn của ứng dụng. API `ServiceLoader.stream()` cung cấp `Provider<S>` để xem kiểu provider trước khi gọi `get()` tạo instance:

```java
ServiceLoader<Greeter> loader = ServiceLoader.load(Greeter.class);

loader.stream()
        .forEach(provider -> System.out.println(provider.type().getName()));
```

Đoạn này chỉ liệt kê tên class provider đã được phát hiện; nó không gọi `provider.get()` để tạo instance. Nếu cần lựa chọn theo cấu hình, hãy dùng tên/metadata do ứng dụng định nghĩa và kiểm tra trường hợp không có provider phù hợp.

`ServiceLoader` nạp provider một cách lazy và cache các provider đã được tìm thấy trong instance loader. Gọi `reload()` sẽ xóa cache để lần duyệt tiếp theo nạp lại provider. Một instance `ServiceLoader` không được thiết kế để chia sẻ đồng thời giữa nhiều thread; tạo instance phù hợp cho từng luồng hoặc quản lý truy cập đồng bộ nếu cần chia sẻ.

## 7. Khi dùng module layer riêng

Trong ứng dụng dùng module layer do chính ứng dụng tạo, provider cần được resolve vào layer đó. `ServiceLoader.load(Greeter.class)` phù hợp với luồng thông thường của ứng dụng; khi muốn truy vấn một layer cụ thể, API hiện hành có overload `ServiceLoader.load(ModuleLayer layer, Class<S> service)`.

Việc tìm provider chỉ thành công nếu provider đã được đưa vào layer và descriptor đăng ký đúng service. Đưa JAR lên một thư mục bất kỳ hoặc chỉ có file JAR trên đĩa chưa tự động làm provider xuất hiện trong layer đang chạy.

## 8. Ứng dụng classpath và ứng dụng named module

Ứng dụng chạy trên classpath thuộc unnamed module nên không khai báo `uses` trong `module-info.java`. Cơ chế `ServiceLoader` vẫn hỗ trợ provider được đăng ký bằng tệp `META-INF/services/<tên-service>` trên classpath.

Với ứng dụng modular dùng named module, hãy khai báo `uses` ở consumer và `provides ... with ...` ở provider trong module descriptor. Hai cách đăng ký provider phục vụ các kiểu triển khai khác nhau; không cần thêm tệp `META-INF/services` cho provider đã khai báo bằng `provides` trong named module.

## 9. Lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `ServiceConfigurationError` báo consumer không khai báo `uses` | Named module gọi `ServiceLoader` nhưng descriptor thiếu chỉ thị `uses`. | Thêm `uses` đúng service type vào `module-info.java` và biên dịch lại. |
| Không tìm thấy provider | Provider không nằm trong module path/layer, thiếu `provides`, sai service type hoặc provider không được resolve. | Kiểm tra module descriptor, tên module và cấu hình module path/layer. |
| `package ... is not visible` | Consumer chưa `requires` module API hoặc package service chưa được export. | Kiểm tra `requires` ở consumer và `exports` ở module API. |
| Provider không thể khởi tạo | Provider class không public, thiếu public constructor không tham số, hoặc provider method sai chữ ký. | Kiểm tra khai báo provider theo dạng constructor hay provider method. |
| Consumer phụ thuộc class provider cụ thể | Mã consumer import implementation thay vì dùng service type. | Chỉ phụ thuộc API và gọi provider qua `ServiceLoader`. |

Không giải quyết lỗi bằng cách export toàn bộ package implementation hoặc thêm dependency trực tiếp từ consumer tới từng provider. Hãy kiểm tra đúng ba phần: API export service type, consumer khai báo `requires` + `uses`, provider khai báo `requires` + `provides`.

## 10. Checklist khi khai báo phía dùng

1. Service type có package công khai và được export từ mô-đun API.
2. Consumer có `requires` mô-đun chứa service type.
3. Consumer có `uses` với đúng tên đầy đủ của service type.
4. Provider có `requires` API và `provides ... with ...` khớp chính xác service type.
5. Provider được đưa vào module path hoặc module layer khi chạy.
6. Consumer xử lý trường hợp không tìm thấy provider và có chính sách lựa chọn rõ ràng nếu tồn tại nhiều provider.
7. Package chứa implementation được giữ kín nếu consumer không cần truy cập trực tiếp.

Khai báo `uses` làm rõ nhu cầu dịch vụ của mô-đun tiêu thụ. Kết hợp `requires` để đọc API, `provides` để đăng ký implementation và `ServiceLoader` để tìm provider, ứng dụng có thể thay thế hoặc mở rộng implementation mà không gắn consumer với class nội bộ.