# Chọn mô-đun gốc và tính phụ thuộc bắc cầu

Khi JVM khởi chạy một ứng dụng modular, nó không nạp mọi mô-đun chỉ vì các JAR đang nằm trên module path. Java bắt đầu từ một tập **mô-đun gốc (root modules)**, sau đó phân giải các mô-đun mà chúng yêu cầu và tiếp tục lần theo các dependency cần thiết. Kết quả là một **module configuration** gồm các mô-đun đã được resolve cùng quan hệ đọc giữa chúng.

Hai việc cần phân biệt:

- **Resolution (phân giải)** quyết định mô-đun nào được đưa vào configuration.
- **Readability (khả năng đọc)** quyết định mã trong một mô-đun có thể đọc các mô-đun nào theo đồ thị JPMS.

Chỉ thị `requires` tạo dependency cần phân giải. `requires transitive` còn truyền khả năng đọc dependency đó tới các mô-đun phụ thuộc vào mô-đun khai báo nó. Việc chọn root module bằng launcher, chẳng hạn `-m` và `--add-modules`, quyết định điểm bắt đầu của quá trình.

## 1. Root module là gì?

Root module là mô-đun được chọn làm điểm bắt đầu khi tạo module configuration. Khi chạy một ứng dụng modular bằng:

~~~powershell
java --module-path mods -m com.example.app/com.example.app.Main
~~~

launcher chọn `com.example.app` làm mô-đun gốc. JVM đọc descriptor của mô-đun đó, tìm các dependency được khai báo bằng `requires`, rồi tiếp tục phân giải dependency của những mô-đun vừa tìm thấy.

Root module không có nghĩa là mô-đun duy nhất được nạp. Nó là điểm bắt đầu để tính tập mô-đun cần thiết.

Một mô-đun khác có thể được chọn làm root ngay cả khi không có mô-đun nào khai báo `requires` tới nó. Đây là cách đưa một plugin, adapter hoặc thành phần tùy chọn vào runtime configuration khi ứng dụng cần sử dụng nó theo cơ chế khác.

Phần ví dụ trong bài dùng cách khởi chạy named module với `-m`. Khi khởi chạy main class từ classpath, launcher áp dụng quy tắc root mặc định khác; có thể dùng `--show-module-resolution` để quan sát tập root thực tế.

## 2. Module path là nơi tìm kiếm, không phải danh sách module đã resolve

Ví dụ thư mục:

~~~text
mods/
├── com.example.app/
├── com.example.orders/
├── com.example.pricing/
├── com.example.shared/
└── com.example.audit/
~~~

Việc cả năm mô-đun có mặt trên module path chỉ có nghĩa module finder có thể tìm thấy chúng. Nó không bảo đảm cả năm đều được resolve vào configuration.

Nếu root là `com.example.app` và dependency graph không dẫn tới `com.example.audit`, mô-đun audit có thể không được resolve. Khi cần audit trong runtime configuration, hãy thêm nó làm root bằng `--add-modules`.

Điều này khác với classpath: class/JAR trên classpath được nạp vào unnamed module theo cơ chế class loading; module path tham gia quá trình tìm kiếm và phân giải named module theo descriptor và root set.

## 3. Cách Java tính dependency closure

Giả sử các mô-đun khai báo:

~~~java
// module-info.java của com.example.app
module com.example.app {
    requires com.example.orders;
}
~~~

~~~java
// module-info.java của com.example.orders
module com.example.orders {
    requires com.example.pricing;
    requires transitive com.example.shared;
}
~~~

~~~java
// module-info.java của com.example.pricing
module com.example.pricing {
    requires com.example.shared;
}
~~~

Khi `com.example.app` là root, Java thực hiện theo ý tưởng sau:

1. Bắt đầu với root `com.example.app`.
2. Đọc descriptor và thêm dependency bắt buộc `com.example.orders`.
3. Đọc descriptor của orders; thêm `com.example.pricing` và `com.example.shared`.
4. Đọc descriptor của pricing; dependency `com.example.shared` đã có trong tập nên không cần thêm lần nữa.
5. Tiếp tục cho đến khi không còn dependency bắt buộc mới.

Kết quả configuration chứa:

~~~text
com.example.app
    └── com.example.orders
          ├── com.example.pricing
          │     └── com.example.shared
          └── com.example.shared
~~~

Đây là dependency closure của root. Mỗi mô-đun chỉ được resolve một lần trong cùng configuration, dù nhiều đường dependency cùng dẫn tới nó.

Nếu một dependency bắt buộc không thể tìm thấy trên module path hoặc trong các module finder tương ứng, quá trình phân giải thất bại trước khi main method chạy. Lỗi thường gặp là `FindException` hoặc thông báo không tìm thấy mô-đun, tùy API và giai đoạn phát hiện lỗi.

## 4. requires và requires transitive có vai trò khác nhau

Cả hai chỉ thị đều khai báo dependency mô-đun và đều tham gia tính dependency closure. Khác biệt quan trọng nằm ở khả năng đọc được truyền tiếp:

| Chỉ thị | Dependency được resolve | Mô-đun client đọc dependency |
|---|---|---|
| `requires B;` | Có | Client trực tiếp yêu cầu A đọc B thì A đọc B; client của A không tự động nhận readability tới B |
| `requires transitive B;` | Có | Mô-đun đọc A cũng được đọc B qua quan hệ truyền tiếp |

Ví dụ, orders khai báo:

~~~java
module com.example.orders {
    requires transitive com.example.shared;
}
~~~

App chỉ cần:

~~~java
module com.example.app {
    requires com.example.orders;
}
~~~

Mã nguồn trong app có thể dùng API public được export bởi `com.example.shared`, vì orders truyền khả năng đọc shared tới các mô-đun đọc orders. App không cần thêm `requires com.example.shared` chỉ để có readability tới shared trong trường hợp này.

Nếu orders khai báo dependency tới pricing bằng `requires com.example.pricing;` thông thường, app vẫn không có readability tới pricing chỉ vì orders đọc pricing. Pricing vẫn được resolve trong configuration, nhưng app không thể mặc nhiên import API của pricing.

**Điểm cốt lõi:** dependency resolution đi theo các quan hệ `requires`; readability được mở rộng thêm bởi `requires transitive`. Một mô-đun có thể đã resolve nhưng mã của một mô-đun khác vẫn không được phép đọc nó.

`requires transitive` cũng không tự export package của dependency. Package vẫn phải được mô-đun sở hữu export theo quy tắc JPMS. Readability và package accessibility là hai điều kiện riêng.

## 5. requires static và dependency tùy chọn

`requires static` khai báo một dependency cần có khi biên dịch nhưng có thể vắng mặt khi chạy:

~~~java
module com.example.app {
    requires static com.example.optional.compiler;
}
~~~

Đây là lựa chọn cho dependency chỉ cần trong một số tình huống, ví dụ annotation hoặc API chỉ dùng ở compile time. Ở runtime, mô-đun được khai báo bằng `requires static` không bắt buộc phải có mặt để configuration được resolve.

Cần bảo đảm mã chạy không gọi class hoặc method của dependency đó khi dependency vắng mặt. Nếu code thực sự cần dependency ở runtime, hãy dùng `requires` thông thường.

So sánh nhanh:

- `requires B`: B là dependency bắt buộc khi resolve mô-đun ở runtime.
- `requires transitive B`: B là dependency bắt buộc và readability được truyền tới mô-đun đọc mô-đun hiện tại.
- `requires static B`: B cần khi biên dịch nhưng có thể không có trong runtime configuration.
- `requires static transitive B`: kết hợp tính tùy chọn ở runtime với khả năng truyền readability khi dependency hiện diện; chỉ dùng khi API công khai thực sự cần kiểu từ B.

## 6. Chọn thêm root bằng --add-modules

Tùy chọn `--add-modules` bổ sung root module cho quá trình phân giải:

~~~powershell
java --add-modules com.example.audit --module-path mods -m com.example.app/com.example.app.Main
~~~

Trong ví dụ này, app vẫn là main module. `com.example.audit` được thêm vào root set dù app không khai báo `requires com.example.audit`. JVM resolve audit cùng các dependency của audit.

Có thể dùng `--add-modules` khi:

- Cần đưa một plugin hoặc adapter vào configuration.
- Một module cung cấp provider/service cần được đưa vào tập module đã resolve.
- Muốn bật một tính năng tùy chọn mà ứng dụng phát hiện bằng tên module hoặc cơ chế registry.
- Cần chẩn đoán sự khác nhau giữa dependency closure mặc định và configuration có thêm root.

Launcher còn hỗ trợ các token đặc biệt:

| Giá trị | Ý nghĩa |
|---|---|
| `--add-modules com.example.audit` | Thêm mô-đun được chỉ định làm root |
| `--add-modules ALL-MODULE-PATH` | Thêm tất cả mô-đun quan sát được trên module path làm root |
| `--add-modules ALL-SYSTEM` | Thêm tất cả mô-đun hệ thống làm root |
| `--add-modules ALL-DEFAULT` | Thêm tập root mặc định của launcher |

Dùng tên mô-đun JPMS, không dùng tên project Gradle, Maven `artifactId` hoặc tên file JAR nếu chúng khác module name.

Không nên thêm `ALL-MODULE-PATH` theo thói quen. Việc resolve mọi mô-đun có thể đưa thêm dependency không cần thiết vào configuration và làm lộ xung đột như split package hoặc nhiều phiên bản module không tương thích.

## 7. --limit-modules khác --add-modules

Hai tùy chọn này phục vụ hai mục đích khác nhau:

- `--add-modules` bổ sung root module để chúng được resolve cùng dependency closure.
- `--limit-modules` giới hạn tập mô-đun mà module finder có thể quan sát trong quá trình phân giải.

Ví dụ giới hạn tập mô-đun có thể quan sát:

~~~powershell
java --limit-modules java.base,com.example.app --module-path mods -m com.example.app/com.example.app.Main
~~~

Tập khả dụng sẽ bị giới hạn theo các mô-đun được chỉ định và dependency cần thiết của chúng. Nếu một mô-đun bắt buộc nằm ngoài tập quan sát được, ứng dụng không thể resolve thành công.

Dùng `--limit-modules` để kiểm tra ứng dụng có vô tình phụ thuộc vào module hệ thống hoặc module bên ngoài không mong muốn hay không. Nó không phải cách thay thế cho `requires` và không có nghĩa là tự thêm các module tùy chọn vào root set.

## 8. Ví dụ hoàn chỉnh: dependency bắc cầu và root tùy chọn

Ví dụ dưới đây có năm named module:

- `com.example.app`: ứng dụng chính, root khi chạy bằng `-m`.
- `com.example.orders`: API đơn hàng, yêu cầu pricing và truyền readability tới shared.
- `com.example.pricing`: tính giá, yêu cầu shared.
- `com.example.shared`: API dùng chung.
- `com.example.audit`: mô-đun audit độc lập, không nằm trong dependency closure mặc định của app.

Cấu trúc source:

~~~text
src/
├── com.example.shared/
│   ├── module-info.java
│   └── com/example/shared/api/Shared.java
├── com.example.pricing/
│   ├── module-info.java
│   └── com/example/pricing/api/Pricing.java
├── com.example.orders/
│   ├── module-info.java
│   └── com/example/orders/api/Orders.java
├── com.example.audit/
│   ├── module-info.java
│   └── com/example/audit/api/Audit.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
~~~

**Shared module:**

~~~java
module com.example.shared {
    exports com.example.shared.api;
}
~~~

~~~java
package com.example.shared.api;

public final class Shared {
    private Shared() {
    }

    public static String version() {
        return "shared-v1";
    }
}
~~~

**Pricing module:**

~~~java
module com.example.pricing {
    requires com.example.shared;
    exports com.example.pricing.api;
}
~~~

~~~java
package com.example.pricing.api;

import com.example.shared.api.Shared;

public final class Pricing {
    private Pricing() {
    }

    public static String label() {
        return "price-for-" + Shared.version();
    }
}
~~~

**Orders module:**

~~~java
module com.example.orders {
    requires transitive com.example.shared;
    requires com.example.pricing;
    exports com.example.orders.api;
}
~~~

~~~java
package com.example.orders.api;

import com.example.pricing.api.Pricing;
import com.example.shared.api.Shared;

public final class Orders {
    private Orders() {
    }

    public static String summary() {
        return "orders:" + Shared.version() + ":" + Pricing.label();
    }
}
~~~

**Audit module:**

~~~java
module com.example.audit {
    requires com.example.shared;
    exports com.example.audit.api;
}
~~~

~~~java
package com.example.audit.api;

public final class Audit {
    private Audit() {
    }

    public static String name() {
        return "audit";
    }
}
~~~

**App module:**

~~~java
module com.example.app {
    requires com.example.orders;
}
~~~

Main class:

~~~java
package com.example.app;

import com.example.orders.api.Orders;
import com.example.shared.api.Shared;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        Module app = Main.class.getModule();
        Module pricing = ModuleLayer.boot()
                .findModule("com.example.pricing")
                .orElseThrow();

        System.out.println(
                "orders-readable=" + app.canRead(Orders.class.getModule())
        );

        System.out.println(
                "shared-readable-via-transitive="
                        + app.canRead(Shared.class.getModule())
        );

        System.out.println(
                "pricing-resolved="
                        + ModuleLayer.boot().findModule("com.example.pricing").isPresent()
        );

        System.out.println("pricing-readable=" + app.canRead(pricing));

        System.out.println(
                "audit-resolved="
                        + ModuleLayer.boot().findModule("com.example.audit").isPresent()
        );

        System.out.println(Orders.summary());
    }
}
~~~

App import và dùng `Shared` dù module descriptor của app chỉ yêu cầu orders. Điều này hợp lệ vì orders khai báo `requires transitive com.example.shared`. App không import Pricing; orders chỉ khai báo `requires` thông thường tới pricing.

Biên dịch cả năm mô-đun bằng JDK 17 trở lên, từ thư mục gốc dự án:

~~~powershell
javac --release 17 --module-source-path src -d mods -m com.example.shared,com.example.pricing,com.example.orders,com.example.audit,com.example.app
~~~

Chạy app với root mặc định là `com.example.app`:

~~~powershell
java --module-path mods -m com.example.app/com.example.app.Main
~~~

Stdout:

~~~text
orders-readable=true
shared-readable-via-transitive=true
pricing-resolved=true
pricing-readable=false
audit-resolved=false
orders:shared-v1:price-for-shared-v1
~~~

Kết quả cho thấy orders, pricing và shared đã được resolve theo dependency closure. App đọc được shared nhờ `requires transitive`. Pricing cũng đã resolve nhưng app không đọc được pricing vì orders khai báo `requires` thường. Audit có trên module path nhưng không được resolve vì không thuộc dependency closure và chưa được chọn làm root.

Chạy lại và thêm audit làm root:

~~~powershell
java --add-modules com.example.audit --module-path mods -m com.example.app/com.example.app.Main
~~~

Stdout:

~~~text
orders-readable=true
shared-readable-via-transitive=true
pricing-resolved=true
pricing-readable=false
audit-resolved=true
orders:shared-v1:price-for-shared-v1
~~~

Chỉ trạng thái resolve của audit thay đổi. App không cần thêm `requires com.example.audit` nếu nó không trực tiếp đọc API của audit; việc chọn audit làm root và việc cấp readability cho app là hai quyết định riêng.

## 9. Quan sát module resolution

Khi cần xem JVM chọn root và lần theo dependency ra sao, dùng:

~~~powershell
java --show-module-resolution --module-path mods -m com.example.app/com.example.app.Main
~~~

Phần đầu kết quả có dạng:

~~~text
root com.example.app
com.example.app requires com.example.orders
com.example.orders requires com.example.pricing
com.example.orders requires com.example.shared
com.example.pricing requires com.example.shared
~~~

Nếu thêm `--add-modules com.example.audit`, log sẽ thể hiện audit là root bổ sung và liệt kê dependency của nó.

Có thể kiểm tra configuration đang chạy trong code bằng:

~~~java
ModuleLayer.boot().modules().stream()
        .map(Module::getName)
        .sorted()
        .forEach(System.out::println);
~~~

Hoặc kiểm tra riêng một module:

~~~java
boolean present =
        ModuleLayer.boot().findModule("com.example.audit").isPresent();
~~~

Các phương thức trên kiểm tra boot layer. Nếu ứng dụng tự tạo module layer riêng bằng API `ModuleLayer`, hãy kiểm tra layer đó thay vì giả định mọi module đều nằm trong boot layer.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Module có trên module path nhưng `FindException` khi chạy | Module không quan sát được hoặc dependency bắt buộc chưa được resolve | Kiểm tra module path, module name và các `requires` |
| Module tùy chọn không xuất hiện trong boot layer | Không nằm trong dependency closure và chưa được chọn làm root | Thêm bằng `--add-modules` hoặc thiết kế service binding phù hợp |
| App không import được API của dependency bắc cầu | Dependency trung gian dùng `requires` thường thay vì `requires transitive` | Khai báo transitive nếu API công khai của module trung gian thực sự phơi kiểu từ dependency |
| Dependency đã resolve nhưng app không đọc được | Có dependency closure nhưng không có readability edge tới module đó | Kiểm tra `requires` trực tiếp hoặc `requires transitive` trên đường phụ thuộc |
| Thêm `ALL-MODULE-PATH` làm runtime lỗi | Resolve thêm mô-đun không cần thiết, gây xung đột hoặc split package | Chỉ thêm root cụ thể mà ứng dụng cần |
| `--limit-modules` khiến app không khởi động | Một dependency bắt buộc nằm ngoài tập mô-đun được phép quan sát | Bổ sung đúng module vào tập giới hạn hoặc bỏ giới hạn không phù hợp |
| App chạy trong IDE nhưng lỗi khi dùng launcher | IDE tự thêm root module, module path hoặc VM option | So sánh lệnh chạy thực tế, đặc biệt `-m`, `--add-modules` và module path |

## 11. Checklist thiết kế runtime configuration

- Xác định main module được chọn làm root khi khởi chạy bằng `-m`.
- Liệt kê dependency trực tiếp trong `module-info.java` bằng `requires`.
- Tính dependency closure bằng cách lần theo các `requires` của từng module.
- Chỉ dùng `requires transitive` khi API công khai của module cần truyền readability tới dependency.
- Dùng `requires static` cho dependency cần ở compile time nhưng có thể vắng mặt khi runtime.
- Thêm module tùy chọn bằng `--add-modules` khi cần resolve nó dù không có đường `requires` từ root.
- Tránh thêm tất cả module path nếu chỉ cần một hoặc vài module tùy chọn.
- Dùng `--limit-modules` để giới hạn tập mô-đun có thể quan sát, không dùng nó như root selector.
- Dùng `--show-module-resolution` để kiểm tra root và dependency closure.
- Kiểm tra đúng module layer khi ứng dụng tạo layer riêng.
- Phân biệt module đã resolve, module mà mã có thể đọc và package mà module có thể truy cập; đây là các khái niệm liên quan nhưng không đồng nhất.

Chọn root modules xác định điểm bắt đầu của runtime configuration. Java lần theo dependency bắt buộc để resolve toàn bộ module graph cần thiết; `requires transitive` điều khiển cách readability được truyền qua API module, còn `--add-modules` cho phép đưa module tùy chọn vào configuration. Khi phân biệt rõ ba cơ chế này, ứng dụng modular có thể khởi chạy với tập module vừa đủ, dễ kiểm tra và ít phụ thuộc ngoài dự kiến.
