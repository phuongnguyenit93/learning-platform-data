# Quan hệ `requires` và khả năng đọc trực tiếp trong JPMS

Trong Java Platform Module System (JPMS), `requires` khai báo một mô-đun phụ thuộc vào mô-đun khác. Khai báo này tạo quan hệ đọc (*readability*): mã trong mô-đun phụ thuộc có thể tham chiếu các kiểu public thuộc những package mà mô-đun được đọc đã `exports`. Khả năng đọc và quyền truy cập package là hai điều kiện riêng; có `requires` không đồng nghĩa với việc mọi package của mô-đun kia đều trở thành API công khai.

## 1. Readability là gì?

Một mô-đun có tên chỉ có thể dùng kiểu từ mô-đun khác khi mô-đun hiện tại đọc được mô-đun cung cấp kiểu đó và package chứa kiểu được export tới bên gọi. Quan hệ đọc được hình thành từ các chỉ thị `requires` trong `module-info.java` và được mở rộng theo quy tắc `requires transitive`.

Ví dụ, nếu `com.example.app` khai báo `requires com.example.service`, thì `com.example.app` đọc trực tiếp `com.example.service`. Quan hệ này không tự động hai chiều: `com.example.service` không vì thế mà đọc được `com.example.app`.

```text
com.example.app  --requires-->  com.example.service
       app đọc được service
       service không tự động đọc được app
```

Readability là một phần của đồ thị mô-đun được resolve khi biên dịch hoặc khởi tạo module layer. Nó không phải thao tác import class và cũng không tự động nạp mọi class trong dependency.

## 2. `requires` tạo khả năng đọc trực tiếp

Cú pháp cơ bản trong `module-info.java`:

```java
module com.example.app {
    requires com.example.service;
}
```

Khi biên dịch và chạy, module finder phải tìm được `com.example.service` trên module path hoặc trong các nguồn mô-đun mà runtime sử dụng. Nếu không tìm thấy một dependency bắt buộc, quá trình compile hoặc resolve sẽ báo lỗi, thường là `module not found` hoặc thông báo không resolve được mô-đun.

Mỗi mô-đun thông thường cũng đọc `java.base` theo quan hệ ngầm định. Vì vậy không cần viết `requires java.base;` trong module descriptor. Descriptor có thể hiển thị dependency này với modifier `MANDATED` khi đọc bằng API hoặc công cụ.

### Readability chưa đủ để truy cập kiểu

Giả sử `com.example.service` khai báo:

```java
module com.example.service {
    exports com.example.service.api;
}
```

Ứng dụng đọc được mô-đun service và có thể truy cập kiểu public trong `com.example.service.api`. Package `com.example.service.internal` vẫn được đóng gói nội bộ nếu không được export. Ngay cả khi ứng dụng biết tên class, `requires` không cấp quyền truy cập vào package chưa export.

Phân biệt các chỉ thị thường gặp:

| Chỉ thị | Vai trò |
| --- | --- |
| `requires` | Tạo khả năng đọc trực tiếp một mô-đun phụ thuộc. |
| `exports` | Cho phép mô-đun đọc package truy cập các kiểu public trong package đó. |
| `opens` | Cho phép reflection sâu trên package trong runtime theo quy tắc mở package. |

`exports` là hợp đồng truy cập ở mức mã nguồn/bytecode; `opens` phục vụ các framework hoặc thư viện cần reflection sâu. Không dùng `opens` để thay thế `exports` khi muốn công khai API Java thông thường.

## 3. `requires transitive` truyền khả năng đọc cho mô-đun phụ thuộc

`requires transitive` dùng khi API công khai của một mô-đun phụ thuộc làm lộ kiểu thuộc mô-đun khác. Mọi mô-đun đọc mô-đun trung gian cũng sẽ đọc được dependency được đánh dấu `transitive`.

Ví dụ đồ thị:

```text
com.example.app
       | requires
       v
com.example.geometry.core
       | requires transitive
       v
com.example.geometry.api
```

`com.example.app` khai báo trực tiếp dependency tới `geometry.core`. Vì `geometry.core` công khai dependency `geometry.api` bằng `requires transitive`, ứng dụng cũng đọc được `geometry.api` mà không cần khai báo thêm một dòng `requires` riêng.

Điều này đặc biệt hữu ích khi API của `geometry.core` trả về hoặc nhận tham số thuộc `geometry.api`. Nếu không truyền readability, người dùng của `geometry.core` sẽ phải tự khai báo thêm dependency vào `geometry.api` chỉ để biên dịch với chữ ký public của thư viện.

Không nên đánh dấu mọi dependency là `transitive`. Việc đó làm dependency trở thành một phần của hợp đồng mô-đun mà người dùng phải quan tâm, tăng phạm vi phụ thuộc và khiến thay đổi kiến trúc khó hơn. Chỉ dùng khi kiểu của dependency thực sự xuất hiện trong API được export hoặc có lý do hợp đồng rõ ràng.

## 4. Ví dụ chạy được: truyền readability qua `requires transitive`

Ví dụ gồm ba mô-đun. `geometry.core` công khai API có sử dụng `Point` của `geometry.api`; ứng dụng chỉ khai báo `requires geometry.core` nhưng vẫn dùng được `Point` nhờ `requires transitive`.

```text
src/
├── com.example.geometry.api/
│   ├── module-info.java
│   └── com/example/geometry/api/Point.java
├── com.example.geometry.core/
│   ├── module-info.java
│   └── com/example/geometry/core/GeometryService.java
└── com.example.geometry.app/
    ├── module-info.java
    └── com/example/geometry/app/Main.java
```

**`src/com.example.geometry.api/module-info.java`**

```java
module com.example.geometry.api {
    exports com.example.geometry.api;
}
```

**`src/com.example.geometry.api/com/example/geometry/api/Point.java`**

```java
package com.example.geometry.api;

public record Point(int x, int y) {
}
```

**`src/com.example.geometry.core/module-info.java`**

```java
module com.example.geometry.core {
    requires transitive com.example.geometry.api;
    exports com.example.geometry.core;
}
```

**`src/com.example.geometry.core/com/example/geometry/core/GeometryService.java`**

```java
package com.example.geometry.core;

import com.example.geometry.api.Point;

public final class GeometryService {
    public Point origin() {
        return new Point(0, 0);
    }
}
```

**`src/com.example.geometry.app/module-info.java`**

```java
module com.example.geometry.app {
    requires com.example.geometry.core;
}
```

**`src/com.example.geometry.app/com/example/geometry/app/Main.java`**

```java
package com.example.geometry.app;

import com.example.geometry.api.Point;
import com.example.geometry.core.GeometryService;

public class Main {
    public static void main(String[] args) {
        Point origin = new GeometryService().origin();
        System.out.println("Origin: " + origin.x() + ", " + origin.y());
    }
}
```

Chạy từ thư mục chứa `src`:

```powershell
javac --release 17 --module-source-path src -d out -m com.example.geometry.api,com.example.geometry.core,com.example.geometry.app
java --module-path out -m com.example.geometry.app/com.example.geometry.app.Main
```

STDOUT:

```text
Origin: 0, 0
```

Điểm cần quan sát: `Main` import `Point`, nhưng `com.example.geometry.app` không khai báo `requires com.example.geometry.api`. Việc biên dịch vẫn hợp lệ vì `geometry.core` đã công khai quan hệ đọc tới `geometry.api` bằng `requires transitive`.

Nếu đổi dòng trong descriptor của `geometry.core` thành `requires com.example.geometry.api;`, `geometry.app` sẽ không còn readability tới `geometry.api`. Khi đó đoạn `Main` dùng `Point` sẽ không biên dịch cho đến khi ứng dụng khai báo dependency trực tiếp hoặc thư viện khôi phục hợp đồng transitive phù hợp.

## 5. `requires static`: cần khi biên dịch, có thể vắng mặt lúc chạy

`requires static` khai báo dependency cần thiết lúc biên dịch nhưng không bắt buộc phải hiện diện khi chạy. Nếu dependency có mặt trên module path, điều đó tự nó chưa bảo đảm mô-đun đã được resolve vào runtime layer. Khi cần bật tính năng tùy chọn, dependency phải có mặt trong đồ thị đã resolve, ví dụ được thêm làm root bằng `--add-modules` hoặc được kéo vào bởi một root module khác.

```java
module com.example.report {
    requires static com.example.metrics.api;
}
```

Trường hợp thường gặp là thư viện annotation hoặc integration tùy chọn. `requires static` không tự biến class sử dụng dependency thành an toàn khi dependency bị thiếu. Nếu bytecode đi vào nhánh cần class đó, ứng dụng vẫn có thể gặp `NoClassDefFoundError` hoặc lỗi liên kết tương ứng.

Ví dụ dưới đây cô lập tham chiếu tới API metrics trong `MetricsBridge`. Lớp khởi động kiểm tra module layer trước khi gọi cầu nối; nếu module không được resolve, class cầu nối không được gọi.

**`src/com.example.metrics.api/module-info.java`**

```java
module com.example.metrics.api {
    exports com.example.metrics.api;
}
```

**`src/com.example.metrics.api/com/example/metrics/api/Metrics.java`**

```java
package com.example.metrics.api;

public final class Metrics {
    private Metrics() {
    }

    public static String status() {
        return "Metrics enabled";
    }
}
```

**`src/com.example.report/module-info.java`**

```java
module com.example.report {
    requires static com.example.metrics.api;
}
```

**`src/com.example.report/com/example/report/Main.java`**

```java
package com.example.report;

public class Main {
    public static void main(String[] args) {
        ModuleLayer layer = Main.class.getModule().getLayer();
        boolean available = layer != null
                && layer.findModule("com.example.metrics.api").isPresent();

        if (available) {
            System.out.println(MetricsBridge.status());
        } else {
            System.out.println("Metrics module is absent.");
        }
    }
}
```

**`src/com.example.report/com/example/report/MetricsBridge.java`**

```java
package com.example.report;

import com.example.metrics.api.Metrics;

final class MetricsBridge {
    static String status() {
        return Metrics.status();
    }
}
```

Biên dịch cả hai mô-đun từ thư mục chứa `src`:

```powershell
javac --release 17 --module-source-path src -d out -m com.example.metrics.api,com.example.report
```

Khi muốn bật metrics, thêm mô-đun tùy chọn vào đồ thị runtime:

```powershell
java --module-path out --add-modules com.example.metrics.api -m com.example.report/com.example.report.Main
```

STDOUT:

```text
Metrics enabled
```

Khi kiểm tra trường hợp không có metrics, chỉ đặt mô-đun ứng dụng lên module path:

```powershell
java --module-path out/com.example.report -m com.example.report/com.example.report.Main
```

STDOUT:

```text
Metrics module is absent.
```

Ở lần chạy thứ hai, `com.example.metrics.api` không có trong runtime graph; ứng dụng vẫn khởi động vì dependency là `static` và nhánh sử dụng `MetricsBridge` không được gọi. Nếu tính năng tùy chọn thực sự được dùng, phải bảo đảm mô-đun tương ứng đã được resolve và có mặt khi chạy.

`requires static transitive` kết hợp hai ý nghĩa: dependency cần ở compile time, tùy chọn ở runtime, và readability được truyền cho các mô-đun phụ thuộc. Chỉ dùng tổ hợp này khi hợp đồng API thực sự cần; việc truyền một dependency tùy chọn sang người dùng có thể khiến họ phải xử lý các kiểu mà runtime không đảm bảo luôn có.

## 6. Đồ thị đọc được và quá trình resolve

Runtime không chỉ đọc từng dòng `requires` riêng lẻ. Khi resolve một tập root modules, JPMS tìm các dependency bắt buộc và tính closure của đồ thị. Các quan hệ transitive tiếp tục được theo dõi qua nhiều lớp dependency.

Ví dụ nếu `app` đọc `service`, `service` đọc `repository`, và `repository` đọc transitive `domain`, readability của `app` có thể bao gồm các mô-đun được đưa vào closure theo các cạnh bắt buộc và transitive tương ứng. Không nên suy ra readability chỉ từ một descriptor riêng lẻ mà bỏ qua cấu hình runtime thực tế.

Đồ thị dependency của các named modules phải không có chu trình. Nếu A cần B và B cần A theo các khai báo `requires`, quá trình biên dịch hoặc resolve sẽ báo lỗi chu trình mô-đun. Hãy tách hợp đồng chung thành mô-đun thứ ba hoặc đảo chiều dependency qua abstraction/service khi cần phá vòng phụ thuộc.

`requires` cũng không đảm bảo module được tìm thấy ở mọi môi trường. Module path dùng khi biên dịch và runtime phải cung cấp đúng module cần thiết. Dependency có trên compile module path nhưng bị thiếu trên runtime module path có thể khiến ứng dụng không resolve hoặc không liên kết được.

## 7. Kiểm tra readability tại runtime

Đối với chẩn đoán runtime, `Module.canRead(Module other)` cho biết một module hiện tại có đọc được module khác trong cấu hình đã chạy hay không. `Module.isExported(String packageName, Module other)` có thể giúp kiểm tra package có được export tới module đích hay không.

```java
Module app = Main.class.getModule();
Module api = Point.class.getModule();

System.out.println("Reads API: " + app.canRead(api));
System.out.println("API package exported: "
        + api.isExported("com.example.geometry.api", app));
```

Đoạn trên là mã chẩn đoán, giả định `Main` và `Point` đã được biên dịch và nạp thành công. Nó không thay thế khai báo module descriptor và không nên được dùng để che giấu dependency thiết kế sai.

## 8. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `module not found` | Module cần thiết không có trên module path hoặc tên module sai. | Kiểm tra tên trong `module-info.java`, vị trí JAR và `--module-path`. |
| `module X does not read module Y` | Không có quan hệ readability trực tiếp hoặc transitive phù hợp. | Kiểm tra chuỗi `requires` từ module hiện tại đến Y. |
| Package không được export | Module được đọc nhưng package không nằm trong `exports` hoặc qualified export không nhắm tới caller. | Kiểm tra `exports` và danh sách target module. |
| `NoClassDefFoundError` khi chạy | Dependency tùy chọn hoặc dependency runtime bị thiếu khi code cần class đó. | Kiểm tra `requires static`, module path runtime và đường thực thi gọi class tùy chọn. |
| Circular dependence | Đồ thị `requires` có chu trình. | Tách abstraction dùng chung hoặc điều chỉnh hướng phụ thuộc. |

Không giải quyết lỗi readability bằng cách export toàn bộ package hoặc mở module một cách rộng rãi. Hãy sửa đúng quan hệ dependency và chỉ công khai package cần thiết.

## 9. Nguyên tắc thiết kế

1. Dùng `requires` cho dependency mà module cần trực tiếp trong implementation hoặc API nội bộ.
2. Dùng `requires transitive` khi dependency là một phần của hợp đồng public mà người dùng module trung gian cần đọc để biên dịch và sử dụng API.
3. Dùng `requires static` cho dependency compile-time tùy chọn, đồng thời cô lập các đường thực thi cần dependency đó và bảo đảm module được resolve khi bật tính năng.
4. Giữ dependency một chiều và đồ thị không chu trình. Đưa abstraction dùng chung vào module riêng nếu nhiều module cần cùng một hợp đồng.
5. Phân biệt readability với exports/opens. Mỗi mô-đun nên export package công khai tối thiểu và chỉ mở reflection khi có nhu cầu rõ ràng.
6. Kiểm tra module path ở cả compile time và runtime. Build thành công không chứng minh runtime có đủ các module cần thiết.

Hiểu đúng `requires` giúp xác định mô-đun nào được phép tham chiếu kiểu của mô-đun khác, kiểm soát dependency được truyền qua API và tránh công khai quá mức. `requires transitive` là một phần của hợp đồng mô-đun; `requires static` dành cho dependency chỉ bắt buộc khi biên dịch. Chọn đúng loại quan hệ sẽ giữ đồ thị JPMS rõ ràng và giúp ứng dụng chạy ổn định trong các môi trường module path khác nhau.