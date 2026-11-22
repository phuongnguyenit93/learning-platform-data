# Khả năng đọc và xuất package của mô-đun tự động

Trong Java Platform Module System (JPMS), **automatic module** là một mô-đun có tên được tạo ngầm từ một JAR chưa có module descriptor tường minh. Khi JAR như vậy được đặt trên **module path**, Java xem nó như một named module với một số quy tắc mặc định rộng để hỗ trợ thư viện chưa được modular hóa.

Automatic module có ba đặc điểm quan trọng:

- Nó **đọc mọi mô-đun đã được resolve trong module configuration**.
- Nó **xuất tất cả package** của chính nó cho các mô-đun đọc nó.
- Các package của nó cũng được mở cho deep reflection tại runtime.

Các quy tắc này giúp mô-đun cũ có thể được sử dụng từ ứng dụng JPMS mà chưa cần thêm `module-info.java`. Đổi lại, automatic module không có ranh giới package chặt chẽ như explicit module. Hiểu đúng chiều đọc, phạm vi export và cách đặt tên giúp tránh phụ thuộc nhầm hoặc vô tình mở rộng API.

## 1. Automatic module được hình thành khi nào?

Một JAR trở thành automatic module khi được đưa lên module path và không cung cấp module descriptor tường minh. Descriptor này có thể là `module-info.class` ở gốc JAR hoặc descriptor hợp lệ trong cấu trúc multi-release JAR.

Ví dụ:

~~~text
legacy-utils-2.4.0.jar
├── com/example/legacy/api/LegacyService.class
├── com/example/legacy/internal/Secret.class
└── META-INF/
    └── MANIFEST.MF
~~~

JAR trên không có `module-info.class`. Khi đặt trên module path, Java tạo một module descriptor ngầm cho nó. Có thể kiểm tra bằng công cụ JDK:

~~~powershell
jar --describe-module --file mods/legacy-utils-2.4.0.jar
~~~

Với JAR không khai báo `Automatic-Module-Name`, kết quả có dạng:

~~~text
No module descriptor found. Derived automatic module.

legacy.utils@2.4.0 automatic
requires java.base mandated
contains com.example.legacy.api
contains com.example.legacy.internal
~~~

Dòng `automatic` cho biết đây là automatic module. Các dòng `contains` liệt kê package được phát hiện trong JAR.

Cần phân biệt ba trường hợp:

- **Explicit module**: có descriptor `module-info.class`; các quan hệ đọc, export và opens được khai báo tường minh.
- **Automatic module**: JAR không có descriptor tường minh nhưng được đặt trên module path; Java tạo descriptor ngầm với quy tắc đọc/export/open rộng.
- **Unnamed module**: class/JAR nằm trên classpath. Nó không có tên JPMS để một named module dùng trong câu lệnh `requires`.

Cùng một JAR có thể được xử lý khác nhau tùy nơi đặt: trên module path nó có thể là automatic module; trên classpath nó thuộc unnamed module.

## 2. Tên của automatic module

Tên mô-đun được xác định theo thứ tự:

1. Nếu manifest có thuộc tính `Automatic-Module-Name`, Java dùng giá trị đó.
2. Nếu không có thuộc tính này, tên được suy ra từ tên file JAR.

Ví dụ manifest:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.example.legacy.utils
~~~

Khi đó, dù artifact có tên `legacy-utils-2.4.0.jar`, tên JPMS module là `com.example.legacy.utils`.

Nếu không khai báo thuộc tính, tên thường được suy ra bằng cách bỏ phần mở rộng `.jar`, loại bỏ hậu tố phiên bản nhận diện được và chuyển dấu phân cách trong tên file thành dấu chấm. Ví dụ:

~~~text
legacy-utils-2.4.0.jar  ->  legacy.utils
json-parser-3.1.jar     ->  json.parser
~~~

Quy tắc suy tên dựa vào tên file có thể khiến việc đổi tên artifact làm thay đổi module name. Khi một thư viện được nhiều ứng dụng modular sử dụng, nên cung cấp `Automatic-Module-Name` ổn định ngay cả trước khi thư viện có explicit descriptor.

Thuộc tính manifest này chỉ ổn định **tên** automatic module. Nó không tạo ra các chỉ thị `requires`, `exports`, `opens`, `uses` hoặc `provides` tùy chỉnh như `module-info.java`.

## 3. Khả năng đọc của automatic module

Automatic module có khả năng đọc tất cả mô-đun đã được resolve trong cấu hình chạy hiện tại. Điều này cho phép một thư viện chưa modular hóa tham chiếu tới các mô-đun khác mà không cần có descriptor khai báo từng quan hệ `requires`.

Ví dụ, một automatic module tên `legacy.bridge` có thể chứa class gọi API của explicit module `com.example.provider`. Nếu `com.example.provider` đã được resolve vào module configuration, automatic module có thể đọc nó.

Tuy nhiên, cần phân biệt **module path** với **module configuration**:

- Đặt một JAR trên module path làm cho module finder có thể tìm thấy mô-đun đó.
- Việc mô-đun được resolve hay không còn phụ thuộc vào tập mô-đun gốc và các quan hệ phụ thuộc.
- Automatic module chỉ đọc những mô-đun nằm trong configuration đã resolve. Nó không tự động buộc mọi JAR đang có trên module path đều được resolve.

Nếu một explicit module cần dùng automatic module, nó vẫn phải khai báo `requires` bằng tên automatic module:

~~~java
module com.example.client {
    requires legacy.utils;
}
~~~

Chiều đọc không đối xứng: automatic module đọc các mô-đun đã resolve, nhưng explicit module tiêu thụ không tự động đọc mọi dependency mà automatic module có thể đọc. Nếu mã của client trực tiếp dùng API từ một explicit module khác, client vẫn cần quan hệ `requires` tương ứng.

### Bổ sung mô-đun vào configuration

Khi một automatic module gọi class thuộc một explicit module không nằm trong đồ thị phụ thuộc thông thường, có thể cần đưa explicit module đó vào làm root khi khởi chạy:

~~~powershell
java --add-modules com.example.provider --module-path "provider-out;mods;client-out" -m com.example.client/com.example.client.Main
~~~

`--add-modules` yêu cầu launcher resolve mô-đun được nêu tên cùng configuration. Sau khi `com.example.provider` có mặt trong configuration, automatic module có thể đọc nó.

Nếu bỏ `--add-modules` và không có dependency nào khác khiến provider được resolve, class của provider có thể không được tìm thấy lúc chạy. Vì vậy, không nên coi mọi JAR có mặt trên module path là tự động sẵn sàng cho mọi automatic module.

## 4. Automatic module xuất tất cả package

Với explicit module, package chỉ được công khai khi descriptor có `exports` tương ứng. Automatic module áp dụng quy tắc rộng hơn: tất cả package của nó được export.

Ví dụ JAR có hai package:

~~~text
com.example.legacy.api
com.example.legacy.internal
~~~

Một explicit module khai báo:

~~~java
module com.example.client {
    requires legacy.utils;
}
~~~

Mã trong client có thể import kiểu public từ cả hai package:

~~~java
import com.example.legacy.api.LegacyService;
import com.example.legacy.internal.Secret;
~~~

Ngay cả package có tên `internal` cũng được export theo quy tắc automatic module. Tên package không tự tạo ra ranh giới đóng gói; chỉ thị `exports` trong explicit descriptor mới kiểm soát package nào được truy cập qua JPMS.

Điều này có nghĩa là automatic module không bảo vệ được implementation detail bằng cách chỉ đặt class vào package nội bộ. Nếu một kiểu public nằm trong package đó, mô-đun đọc automatic module có thể truy cập nó.

## 5. Package của automatic module cũng mở cho reflection

Automatic module còn cho phép deep reflection vào các package của nó. Framework hoặc mô-đun khác có thể dùng reflection để truy cập private field, constructor hoặc method khi các quy tắc truy cập Java cho phép và đối tượng reflection thuộc đúng module context.

Ví dụ:

~~~java
Field field = Secret.class.getDeclaredField("value");
boolean accessible = field.trySetAccessible();
~~~

Với class `Secret` nằm trong automatic module, `trySetAccessible()` có thể trả về `true` mà không cần khai báo `opens` trong `module-info.java`, vì automatic module không có danh sách package đóng/mở tường minh.

Điều này thuận tiện cho các thư viện cũ được sử dụng với framework dựa trên reflection. Tuy nhiên, nó làm giảm khả năng đóng gói: mọi package đều được mở cho deep reflection, không chỉ package mà framework thực sự cần.

## 6. Ví dụ hoàn chỉnh: explicit client sử dụng automatic module

Ví dụ sau tạo một thư viện không có `module-info.java`, sau đó dùng nó từ một explicit module. Client truy cập được cả package API và package internal, đồng thời đọc private field bằng reflection.

Cấu trúc thư mục:

~~~text
legacy-src/
└── com/example/legacy/
    ├── api/
    │   └── LegacyService.java
    └── internal/
        └── Secret.java

client-src/
└── com.example.client/
    ├── module-info.java
    └── com/example/client/
        └── Main.java
~~~

**Thư viện cũ `LegacyService.java`:**

~~~java
package com.example.legacy.api;

public final class LegacyService {
    private LegacyService() {
    }

    public static String message() {
        return "automatic-module-readable";
    }
}
~~~

**Kiểu trong package internal `Secret.java`:**

~~~java
package com.example.legacy.internal;

public final class Secret {
    private final String value;

    public Secret(String value) {
        this.value = value;
    }
}
~~~

Thư viện không có `module-info.java` và không khai báo `exports` hay `opens`.

**Descriptor của client `module-info.java`:**

~~~java
module com.example.client {
    requires legacy.utils;
}
~~~

Tên `legacy.utils` được suy ra từ file `legacy-utils-2.4.0.jar`. Nếu JAR khai báo `Automatic-Module-Name`, phải dùng đúng tên trong manifest thay cho tên suy ra.

**Mã client `Main.java`:**

~~~java
package com.example.client;

import com.example.legacy.api.LegacyService;
import com.example.legacy.internal.Secret;

import java.lang.reflect.Field;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        System.out.println(LegacyService.message());

        Secret secret = new Secret("automatic-module-data");
        System.out.println(
                "internal-package-exported=" + secret.getClass().getPackageName()
        );

        Field value = Secret.class.getDeclaredField("value");
        System.out.println("deepReflection=" + value.trySetAccessible());
    }
}
~~~

Biên dịch thư viện cũ thành class/JAR. Các lệnh dưới đây dùng PowerShell và giả định đang đứng ở thư mục gốc dự án:

~~~powershell
New-Item -ItemType Directory -Force legacy-classes, mods, out | Out-Null

javac -d legacy-classes legacy-src/com/example/legacy/api/LegacyService.java legacy-src/com/example/legacy/internal/Secret.java

jar --create --file mods/legacy-utils-2.4.0.jar -C legacy-classes .
~~~

Sau đó biên dịch explicit client trên module path:

~~~powershell
javac --module-path mods --module-source-path client-src -d out -m com.example.client
~~~

Chạy ứng dụng:

~~~powershell
java --module-path "mods;out" -m com.example.client/com.example.client.Main
~~~

Stdout chính xác:

~~~text
automatic-module-readable
internal-package-exported=com.example.legacy.internal
deepReflection=true
~~~

Kết quả xác nhận:

- Client đọc được automatic module thông qua `requires legacy.utils`.
- Package `com.example.legacy.internal` cũng được export dù thư viện không có `exports`.
- Reflection có thể bật quyền truy cập private field vì package của automatic module được mở cho deep reflection.

Nếu đưa cùng JAR lên classpath thay vì module path, nó thuộc unnamed module. Khi đó explicit module không thể khai báo `requires legacy.utils` để đọc nó; cần dùng cách tổ chức dependency phù hợp với classpath hoặc chuyển JAR lên module path.

## 7. Ví dụ về chiều đọc từ automatic module sang explicit module

Khả năng đọc rộng của automatic module có thể hữu ích trong giai đoạn chuyển đổi. Giả sử có:

- Explicit module `com.example.provider` xuất package `com.example.provider.api`.
- Automatic module `legacy.bridge` có class gọi `Provider.message()`.
- Explicit client `com.example.client` chỉ khai báo `requires legacy.bridge`.

Descriptor của provider:

~~~java
module com.example.provider {
    exports com.example.provider.api;
}
~~~

Class API:

~~~java
package com.example.provider.api;

public final class Provider {
    private Provider() {
    }

    public static String message() {
        return "named-module-readable";
    }
}
~~~

Class `Bridge` được biên dịch và đóng gói thành JAR không có `module-info.java`:

~~~java
package com.example.bridge.api;

import com.example.provider.api.Provider;

public final class Bridge {
    private Bridge() {
    }

    public static String message() {
        return Provider.message();
    }
}
~~~

Client chỉ cần khai báo:

~~~java
module com.example.client {
    requires legacy.bridge;
}
~~~

Khi chạy, thêm provider vào configuration:

~~~powershell
java --add-modules com.example.provider --module-path "provider-out;mods;client-out" -m com.example.client/com.example.client.Main
~~~

Stdout:

~~~text
named-module-readable
~~~

Automatic module `legacy.bridge` đọc được provider vì `com.example.provider` đã được resolve. Nếu provider không được resolve và không có dependency nào khác đưa nó vào configuration, class của provider sẽ không sẵn sàng lúc runtime. Ví dụ này cho thấy khả năng đọc rộng của automatic module vẫn phụ thuộc vào quá trình phân giải mô-đun.

## 8. So sánh explicit module, automatic module và unnamed module

| Đặc điểm | Explicit module | Automatic module | Unnamed module |
|---|---|---|---|
| Vị trí thường dùng | Module path | Module path | Classpath |
| Tên mô-đun | Khai báo trong `module-info.java` | Manifest hoặc suy từ tên JAR | Không có tên JPMS ổn định |
| Descriptor | `module-info.class` | Descriptor được tạo ngầm | Không có |
| Khả năng đọc | Theo `requires` | Đọc mọi mô-đun trong configuration | Đọc các mô-đun trong configuration theo quy tắc unnamed module |
| Package export | Theo `exports` | Tất cả package | Không áp dụng ranh giới export như named module |
| Deep reflection | Theo `opens` hoặc quyền runtime | Tất cả package được mở | Không áp dụng ranh giới đóng gói của named module |
| Kiểm soát API | Tường minh | Rộng, ít khả năng đóng gói | Không có module descriptor để kiểm soát |

Một automatic module là named module, nên explicit module có thể tham chiếu nó bằng `requires`. Unnamed module không có tên để khai báo như vậy.

## 9. Hạn chế và lưu ý khi sử dụng

Automatic module chủ yếu là cầu nối để chuyển thư viện cũ sang JPMS. Các đặc điểm rộng của nó tạo ra một số rủi ro:

- **Đọc quá rộng**: automatic module đọc mọi mô-đun đã resolve trong configuration, nên phụ thuộc của thư viện khó được nhìn thấy từ descriptor.
- **Export quá rộng**: mọi package đều được công khai qua JPMS. Package `internal` không còn là ranh giới bảo vệ.
- **Mở reflection quá rộng**: framework có thể truy cập sâu vào package mà thư viện chưa chủ động chọn mở.
- **Tên module có thể thay đổi**: nếu tên được suy từ file JAR, đổi tên artifact có thể làm hỏng `requires` ở consumer.
- **Split package**: hai mô-đun cùng chứa package name có thể gây lỗi khi phân giải cấu hình. Không nên dùng automatic module để hợp nhất các JAR có package trùng nhau.
- **Dependency không được resolve**: JAR nằm trên module path nhưng không thuộc module configuration thì automatic module không thể dùng class của nó lúc chạy.

Nếu cần API ổn định, dependency rõ ràng và đóng gói chặt, nên chuyển thư viện sang explicit module. Khi làm việc đó, hãy xác định package API cần `exports`, package cần mở cho framework bằng qualified `opens`, và các dependency thực sự cần `requires`.

## 10. Lộ trình chuyển từ automatic sang explicit module

Có thể chuyển đổi theo từng bước:

1. **Ổn định tên mô-đun** bằng manifest `Automatic-Module-Name` khi thư viện chưa có descriptor.
2. **Kiểm tra package** và xác định API public thực sự cần cung cấp.
3. **Xử lý split package** giữa các JAR trước khi tạo explicit descriptor.
4. **Thêm `module-info.java`** với các quan hệ `requires`, `exports`, `opens`, `uses` và `provides` cần thiết.
5. **Kiểm thử trên module path** để phát hiện package chưa export hoặc dependency chưa khai báo.
6. **Kiểm thử framework reflection** và chỉ mở các package cần thiết cho đúng mô-đun.
7. **Cập nhật consumer** nếu tên module hoặc ranh giới API thay đổi có chủ đích.

Sau khi JAR có explicit descriptor, tên module và quy tắc truy cập được điều khiển bởi descriptor. Manifest `Automatic-Module-Name` không còn quyết định tên mô-đun trong trường hợp đó.

## 11. Checklist khi sử dụng automatic module

- Xác nhận JAR thực sự không có module descriptor tường minh.
- Đặt JAR trên module path nếu muốn sử dụng nó như automatic module.
- Kiểm tra tên module bằng `jar --describe-module`.
- Ưu tiên manifest `Automatic-Module-Name` để tên không phụ thuộc tên file artifact.
- Khai báo `requires` đúng tên automatic module ở explicit consumer.
- Nhớ rằng automatic module đọc các mô-đun đã resolve, không tự resolve mọi JAR trên module path.
- Dùng `--add-modules` khi một dependency cần được đưa vào configuration nhưng không được kéo vào bởi quan hệ phụ thuộc khác.
- Giả định mọi package đều được export và mở cho reflection; không dựa vào tên `internal` để bảo vệ implementation detail.
- Tránh split package giữa các mô-đun.
- Lập kế hoạch chuyển sang explicit module khi cần kiểm soát dependency, API và quyền reflection.

Automatic module giúp thư viện chưa modular hóa tham gia vào ứng dụng JPMS với thay đổi tối thiểu. Quy tắc đọc rộng, export toàn bộ package và mở reflection giúp khả năng tương thích cao, nhưng cũng làm ranh giới mô-đun lỏng hơn. Khi cần kiểm soát rõ API và dependency, explicit module với descriptor được thiết kế có chủ đích là hướng phù hợp cho trạng thái lâu dài.
