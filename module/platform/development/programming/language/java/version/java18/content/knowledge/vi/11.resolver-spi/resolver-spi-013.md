# Đăng ký provider trong named module bằng `provides ... with` và kiểm tra module được resolve

## Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt **khai báo dịch vụ**, **đưa module provider vào đồ thị module** (resolution) và **chọn/kích hoạt provider** lúc chạy.
- Đăng ký `java.net.spi.InetAddressResolverProvider` trong một **named module** bằng chỉ thị `provides ... with` của JPMS.
- Biên dịch và chạy hai module độc lập, xác minh provider module đã được resolve bằng `--show-module-resolution` và `ModuleLayer.boot()`.
- Xác định các nguyên nhân phổ biến khiến khai báo provider đúng nhưng `InetAddress` vẫn không sử dụng provider mong đợi.

**Bối cảnh:** Java 18 giới thiệu SPI phân giải địa chỉ Internet qua JEP 418. API `java.net.spi.InetAddressResolverProvider` tiếp tục hữu ích trên các JDK hiện đại. Bài học tập trung vào cách đăng ký và kiểm chứng provider trong JPMS; phần triển khai sẽ ủy quyền cho bộ phân giải tích hợp để có một ví dụ an toàn, dễ quan sát. Khi xây dựng resolver thực tế, bạn có thể trả về một `InetAddressResolver` tự triển khai để xử lý phân giải tên và phân giải ngược.

## 1. Ba bước dễ bị nhầm lẫn

Khi ứng dụng gọi `InetAddress.getByName(...)`, JDK có thể sử dụng một `InetAddressResolverProvider` được đăng ký qua cơ chế dịch vụ. Với named module, có ba điều kiện khác nhau:

| Khái niệm | Ý nghĩa | Cách kiểm tra |
| --- | --- | --- |
| **Đăng ký (declaration)** | `module-info.java` của provider có `provides java.net.spi.InetAddressResolverProvider with ...;` | Xem khai báo module đã biên dịch bằng `jar --describe-module` nếu đóng gói JAR, hoặc xem `module-info.java` trong ví dụ. |
| **Resolution** | Module provider thực sự thuộc đồ thị module được phân giải cho lần chạy đó; chỉ đặt module trên `--module-path` chưa bảo đảm điều này. | `java --show-module-resolution` và `ModuleLayer.boot().findModule(...)`. |
| **Kích hoạt (selection/initialization)** | Khi `InetAddress` khởi tạo cơ chế phân giải, JDK tìm provider thích hợp và gọi `get(Configuration)` để lấy resolver. | Ghi thông báo trong `get(...)` và thực hiện tra cứu địa chỉ. |

Chỉ thị `provides ... with` mô tả **module nào cung cấp dịch vụ nào**, nhưng bản thân nó không tương đương với `requires` và cũng không tự chứng minh module đã được resolve. `requires` thiết lập quan hệ phụ thuộc đọc module; `provides` đăng ký một hoặc nhiều lớp triển khai dịch vụ. `uses` dành cho module trực tiếp sử dụng cơ chế tìm dịch vụ. Trong ví dụ này, ứng dụng chỉ gọi `InetAddress`, vì vậy không cần khai báo `uses InetAddressResolverProvider` trong module của ứng dụng; việc tra cứu provider do hạ tầng của JDK thực hiện.

## 2. Tạo hai named module

Giả sử có cây thư mục sau (đường dẫn tương đối so với thư mục dự án):

```text
src/
├── com.example.resolver/
│   ├── module-info.java
│   └── com/example/resolver/DelegatingResolverProvider.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
```

### 2.1. Khai báo provider module

File `src/com.example.resolver/module-info.java`:

```java
module com.example.resolver {
    provides java.net.spi.InetAddressResolverProvider
            with com.example.resolver.DelegatingResolverProvider;
}
```

Tên sau `with` là tên đầy đủ của lớp triển khai. Đây là một **service provider declaration** trong module descriptor. `InetAddressResolverProvider` thuộc `java.base`, module được mọi named module đọc ngầm định, nên không cần viết `requires java.base;`.

File `src/com.example.resolver/com/example/resolver/DelegatingResolverProvider.java`:

```java
package com.example.resolver;

import java.net.spi.InetAddressResolver;
import java.net.spi.InetAddressResolverProvider;

public final class DelegatingResolverProvider
        extends InetAddressResolverProvider {

    public DelegatingResolverProvider() {
        // Constructor công khai để cơ chế nạp service tạo instance.
    }

    @Override
    public String name() {
        return "delegating-resolver";
    }

    @Override
    public InetAddressResolver get(Configuration configuration) {
        System.err.println("[resolver-demo] provider da duoc kich hoat");
        // Trao lại việc tra cứu cho resolver tích hợp của JDK.
        return configuration.builtinResolver();
    }
}
```

Lớp provider kế thừa `InetAddressResolverProvider` và cung cấp hai phương thức quan trọng:

- `name()` trả về tên provider để nhận diện.
- `get(Configuration)` cung cấp một `InetAddressResolver`. Trong ví dụ, `configuration.builtinResolver()` lấy resolver tích hợp sẵn, tránh tự viết quy tắc DNS không cần thiết. Khi cần tùy biến, có thể thay đối tượng trả về bằng implementation của `InetAddressResolver` với `lookupByName(...)` và `lookupByAddress(...)`.

Lớp provider có constructor `public` không tham số để dễ hiểu và đáp ứng cách khởi tạo thông thường. Package `com.example.resolver` **không cần `exports`** chỉ để JDK nạp provider đã khai báo bằng `provides`; `exports` là cơ chế công khai API của package cho module khác, không phải cách đăng ký dịch vụ.

### 2.2. Tạo module ứng dụng

File `src/com.example.app/module-info.java`:

```java
module com.example.app {
    // Ứng dụng chỉ dùng API trong java.base.
}
```

File `src/com.example.app/com/example/app/Main.java`:

```java
package com.example.app;

import java.net.InetAddress;
import java.net.UnknownHostException;

public final class Main {
    public static void main(String[] args) throws UnknownHostException {
        boolean resolved = ModuleLayer.boot()
                .findModule("com.example.resolver")
                .isPresent();
        System.out.println("Provider module resolved: " + resolved);

        InetAddress address = InetAddress.getByName("localhost");
        System.out.println("localhost -> " + address.getHostAddress());
    }
}
```

`ModuleLayer.boot()` phản ánh các module đã được resolve trong lớp module khởi động. Dòng `InetAddress.getByName("localhost")` tạo một lần tra cứu để quan sát thời điểm SPI được sử dụng. Địa chỉ trả về có thể là IPv4 hoặc IPv6 tùy cấu hình hệ thống; không nên kiểm thử bằng cách cố định `127.0.0.1`.

## 3. Biên dịch và chạy với module provider được resolve rõ ràng

Ví dụ dùng JDK 18 hoặc JDK hiện đại có API `java.net.spi.InetAddressResolverProvider`. Chạy các lệnh tại thư mục chứa `src`:

```shell
javac --module-source-path src -d mods -m com.example.resolver,com.example.app
```

Sau đó chạy:

```shell
java --module-path mods \
  --add-modules com.example.resolver \
  --show-module-resolution \
  --module com.example.app/com.example.app.Main
```

Trên Windows PowerShell, có thể viết lệnh `java` trên **một dòng** (dấu `\` ở trên chỉ là ký hiệu nối dòng cho shell kiểu Unix):

```powershell
java --module-path mods --add-modules com.example.resolver --show-module-resolution --module com.example.app/com.example.app.Main
```

Hãy tìm các dấu hiệu sau trong đầu ra:

```text
root com.example.app ...
root com.example.resolver ...
Provider module resolved: true
[resolver-demo] provider da duoc kich hoat
localhost -> 127.0.0.1
```

Đây là **đầu ra minh họa**, không phải chuỗi bắt buộc phải giống hoàn toàn: `--show-module-resolution` in thêm nhiều module và quan hệ phụ thuộc; thứ tự giữa `System.out` và `System.err` có thể khác; địa chỉ `localhost` có thể là IPv6.

Giải thích từng bằng chứng:

1. `--module-path mods` làm cho cả hai module có thể được tìm thấy (observable).
2. `--add-modules com.example.resolver` đặt provider module vào tập root module để nó được resolve chắc chắn cho lần chạy này, dù ứng dụng không có `requires com.example.resolver`.
3. `--show-module-resolution` cho biết quá trình phân giải đã nhận module provider. Dòng `Provider module resolved: true` xác nhận điều đó trực tiếp từ boot layer.
4. Thông báo trong `get(Configuration)` cho thấy JDK đã khởi tạo provider và lấy resolver của nó khi xử lý việc phân giải địa chỉ.

**Điểm cần nhớ:** `--show-module-resolution` và `findModule(...)` chỉ kiểm chứng **resolution**. Để kiểm chứng **kích hoạt**, cần thêm bằng chứng từ `get(...)` hoặc hành vi riêng có thể quan sát của resolver. Việc có tên module trong đồ thị không đủ chứng minh provider đã được chọn, nhất là khi môi trường có nhiều provider.

## 4. Vì sao chỉ đặt JAR/module trên module path là chưa đủ?

JPMS phân biệt **module có thể tìm thấy** và **module nằm trong đồ thị đã phân giải**. Nếu chỉ chạy:

```shell
java --module-path mods --module com.example.app/com.example.app.Main
```

thì không được suy ra provider luôn được resolve chỉ vì thư mục `mods` chứa `com.example.resolver`. Tập module thực tế được resolve còn phụ thuộc vào root module, các quan hệ `requires`, cơ chế liên kết dịch vụ và cách tạo runtime image. Hãy dựa vào `--show-module-resolution` hoặc `ModuleLayer.boot()` để kết luận trên **lần chạy cụ thể**.

Để chủ động kiểm soát bản demo, dùng `--add-modules com.example.resolver`. Khi đóng gói runtime image bằng `jlink`, cần bảo đảm provider module được đưa vào image thông qua danh sách module phù hợp hoặc cơ chế service binding như `--bind-services`, rồi kiểm tra lại trong môi trường đích. Không coi một bản build thành công là bằng chứng provider sẽ xuất hiện trong mọi runtime.

## 5. Kiểm tra và khắc phục lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `ModuleLayer.boot().findModule(...)` trả `false` | Module provider chưa được resolve. | Kiểm tra `--module-path`, thêm `--add-modules com.example.resolver` và xem `--show-module-resolution`. |
| Báo `Module ... not found` | Sai tên module, sai vị trí output hoặc không có module hợp lệ trên module path. | Đối chiếu tên trong `module-info.java`, cấu trúc `mods` và lệnh `javac`. |
| Provider module được resolve nhưng không có thông báo trong `get(...)` | Việc tra cứu chưa khởi tạo provider, provider khác được chọn hoặc resolver đã được khởi tạo trước đó. | Chạy trong JVM mới, gọi `InetAddress.getByName(...)` và kiểm tra các provider đang cùng tham gia runtime. |
| Có thông báo từ provider nhưng kết quả phân giải không khác bình thường | Ví dụ đang ủy quyền qua `configuration.builtinResolver()`. | Đây là kết quả mong đợi; để thử hành vi tùy biến cần viết `InetAddressResolver` riêng và kiểm thử đầy đủ. |
| Module biên dịch không thấy provider | Khai báo sai tên lớp hoặc lớp chưa kế thừa đúng `InetAddressResolverProvider`. | Đối chiếu `provides ... with` với package, class và chữ ký API chính xác. |

Trong ứng dụng thực tế, các lệnh chẩn đoán có thể được dùng kết hợp với test tích hợp khởi chạy một tiến trình JVM mới. Hãy tránh phụ thuộc vào thứ tự chọn provider khi có nhiều provider khả dụng, vì không nên giả định một thứ tự mà hợp đồng API không bảo đảm. Đồng thời, kết quả phân giải địa chỉ có thể chịu ảnh hưởng của cache; đừng dùng nhiều lần gọi `getByName(...)` trong cùng JVM để kết luận về việc thay đổi provider giữa chừng.

## 6. Bài tập kiểm chứng

1. Chạy đúng ví dụ với `--add-modules` và chụp lại hai bằng chứng: module đã resolve (`true`) và thông báo trong `get(...)`.
2. Chạy lại trong một JVM mới mà bỏ `--add-modules`, quan sát `--show-module-resolution` và giá trị `findModule(...)`. Ghi nhận kết quả thực tế thay vì dự đoán mặc định của mọi JDK/cách đóng gói.
3. Đổi tên module provider trong `module-info.java`, cập nhật `--add-modules`, biên dịch lại và giải thích vì sao **tên module** khác với tên của **lớp provider** sau `with`.
4. Giải thích bằng lời vì sao `module com.example.app {}` hợp lệ dù ứng dụng gọi `InetAddress`, và vì sao không cần `exports com.example.resolver` để đăng ký provider này.

### Tự kiểm tra

**Hỏi:** `provides ... with` có khiến mọi module trên module path được nạp ngay lập tức không?

**Đáp:** Không. Khai báo đăng ký triển khai dịch vụ trong module descriptor; module còn phải tham gia đồ thị phân giải phù hợp, và việc chọn/khởi tạo provider xảy ra theo cơ chế SPI lúc chạy.

**Hỏi:** Có thể dùng `findModule(...) == true` để khẳng định `get(Configuration)` đã được gọi không?

**Đáp:** Không. `findModule(...)` xác nhận module có trong boot layer. Thông báo hoặc hành vi thực tế của provider mới cung cấp bằng chứng nó được kích hoạt.

**Hỏi:** Tại sao ví dụ trả về `configuration.builtinResolver()`?

**Đáp:** Để tập trung vào đăng ký và resolution của named module trên JDK hiện đại, đồng thời giữ nguyên cơ chế phân giải địa chỉ của JDK trong ví dụ. Đây là điểm xuất phát trước khi tự triển khai `lookupByName(...)` và `lookupByAddress(...)`.

## Tài liệu tham khảo

- JEP 418 — *Internet-Address Resolution SPI* (Java 18): https://openjdk.org/jeps/418
- Java SE API — `java.net.spi.InetAddressResolverProvider`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/spi/InetAddressResolverProvider.html
- Java Platform Module System — chỉ thị `provides`, `uses` và module resolution: https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.7
