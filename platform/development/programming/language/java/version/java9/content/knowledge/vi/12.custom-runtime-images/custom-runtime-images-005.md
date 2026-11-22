# Đưa nhà cung cấp dịch vụ vào image với `--bind-services`

## 1. Vì sao cần `--bind-services`?

Khi tạo runtime image bằng `jlink`, công cụ chỉ đưa vào các module thuộc đồ thị module đã được phân giải, cùng những dependency cần thiết. Một module cung cấp dịch vụ thường không được module ứng dụng `requires` trực tiếp: ứng dụng chỉ phụ thuộc vào interface dịch vụ và tìm implementation bằng `ServiceLoader` lúc chạy.

Điều này tạo ra một khoảng cách giữa hai thời điểm:

- **Lúc chạy ứng dụng:** `ServiceLoader` tìm các implementation đã được đăng ký và có mặt trong runtime.
- **Lúc tạo image:** `jlink` phải biết module provider nào cần được đưa vào image. Chỉ có file JAR của provider trên module path chưa đủ để bảo đảm nó được liên kết.

Tùy chọn `--bind-services` yêu cầu `jlink` phân giải cả các module cung cấp những service mà các module trong đồ thị hiện tại khai báo sử dụng. Các module provider và dependency của chúng được đưa vào image. Cơ chế này dựa trên khai báo service của hệ module, nên ứng dụng không cần phụ thuộc trực tiếp vào từng implementation.

`--bind-services` được hỗ trợ từ Java 9 và vẫn là tùy chọn hợp lệ trong các JDK hiện hành. Ví dụ bên dưới dùng cú pháp module ổn định và có thể biên dịch bằng JDK 17 trở lên.

## 2. Bốn thành phần cần phân biệt

| Thành phần | Vai trò |
| --- | --- |
| `uses <Service>` | Module tiêu thụ khai báo loại service mà nó cần. |
| `provides <Service> with <Provider>` | Module provider đăng ký implementation cho service. |
| `ServiceLoader.load(Service.class)` | Mã ứng dụng tìm và khởi tạo các provider có trong runtime. |
| `jlink --bind-services` | Khi liên kết image, tìm provider cho các service được khai báo `uses` và đưa provider cùng dependency vào image. |

Module ứng dụng cần `requires` module chứa interface service. Nó khai báo `uses` cho interface đó, nhưng không cần `requires` module provider. Đây là điểm giúp thay implementation mà không phải sửa dependency trực tiếp của ứng dụng.

## 3. Ví dụ với ba module

Ta tạo một service `GreetingService`, một module ứng dụng tiêu thụ service và một module cung cấp implementation.

```text
src/
├── com.acme.spi/
│   ├── module-info.java
│   └── com/acme/spi/GreetingService.java
├── com.acme.app/
│   ├── module-info.java
│   └── com/acme/app/Main.java
└── com.acme.provider/
    ├── module-info.java
    └── com/acme/provider/EnglishGreetingService.java
```

**Module chứa interface — `com.acme.spi/module-info.java`:**

```java
module com.acme.spi {
    exports com.acme.spi;
}
```

**Interface — `GreetingService.java`:**

```java
package com.acme.spi;

public interface GreetingService {
    String greet(String name);
}
```

**Module ứng dụng — `com.acme.app/module-info.java`:**

```java
module com.acme.app {
    requires com.acme.spi;
    uses com.acme.spi.GreetingService;
}
```

Dòng `uses` là khai báo quan trọng đối với module ứng dụng. Nó cho hệ module biết ứng dụng cần các provider của `GreetingService`.

**Ứng dụng — `Main.java`:**

```java
package com.acme.app;

import com.acme.spi.GreetingService;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        GreetingService service = ServiceLoader.load(GreetingService.class)
            .findFirst()
            .orElseThrow(() -> new IllegalStateException("No provider found"));

        System.out.println(service.greet("Java 9"));
    }
}
```

Ứng dụng chỉ biết interface `GreetingService`. Nó không import `EnglishGreetingService` và không khai báo `requires com.acme.provider`.

**Module provider — `com.acme.provider/module-info.java`:**

```java
module com.acme.provider {
    requires com.acme.spi;
    provides com.acme.spi.GreetingService
        with com.acme.provider.EnglishGreetingService;
}
```

Khai báo `provides ... with ...` đăng ký implementation với hệ module. Package chứa lớp provider không cần `exports` chỉ để `ServiceLoader` sử dụng provider đã khai báo.

**Implementation — `EnglishGreetingService.java`:**

```java
package com.acme.provider;

import com.acme.spi.GreetingService;

public class EnglishGreetingService implements GreetingService {
    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

Lớp provider trong ví dụ là `public` và có constructor không tham số mặc định. Đây là dạng provider đơn giản mà `ServiceLoader` có thể khởi tạo.

## 4. Biên dịch module và tạo runtime image

Đứng tại thư mục chứa `src/`, chạy bằng PowerShell trên Windows với một JDK đầy đủ. Biến `JAVA_HOME` cần trỏ đến thư mục JDK để đường dẫn `jmods` tồn tại.

```powershell
New-Item -ItemType Directory -Force mods | Out-Null

javac -d mods --module-source-path src -m com.acme.spi,com.acme.app,com.acme.provider

jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.acme.app --bind-services --output runtime-image

.\runtime-image\bin\java -m com.acme.app/com.acme.app.Main
```

`javac` biên dịch ba module vào `mods/`. Khi chạy `jlink`: 

1. `--module-path` chỉ ra module hệ thống của JDK và các module ứng dụng vừa biên dịch.
2. `--add-modules com.acme.app` chọn module ứng dụng làm root của đồ thị cần liên kết.
3. `--bind-services` tìm module provider phù hợp với các khai báo `uses` trong đồ thị đã phân giải.
4. `--output runtime-image` tạo runtime image riêng chứa ứng dụng, service API, provider được tìm thấy và các dependency cần thiết.

Kết quả chạy chương trình:

```text
Hello, Java 9!
```

Thư mục `runtime-image` phải chưa tồn tại hoặc đang rỗng khi chạy `jlink`. Trên Linux/macOS, dấu phân cách các phần tử của `--module-path` là `:`, ví dụ `"$JAVA_HOME/jmods:mods"`; trên Windows là `;` như lệnh PowerShell ở trên.

## 5. Điều gì xảy ra nếu bỏ `--bind-services`?

Nếu chỉ chạy:

```powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.acme.app --output runtime-without-binding
```

thì `com.acme.app` và dependency `com.acme.spi` được liên kết, nhưng `com.acme.provider` không tự trở thành dependency chỉ vì module đó đang có mặt trong `mods/`. Khi chạy image này, `ServiceLoader` không tìm thấy provider; ví dụ trên sẽ ném `IllegalStateException` với thông báo `No provider found`.

Có thể yêu cầu đưa provider vào một cách tường minh:

```powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.acme.app,com.acme.provider --output runtime-with-explicit-provider
```

Hai cách giải quyết hai nhu cầu khác nhau:

- Dùng `--bind-services` khi muốn liên kết các provider theo khai báo service, đặc biệt khi có nhiều implementation hoặc provider có dependency riêng.
- Dùng `--add-modules` khi đã biết chính xác module nào phải có trong image và muốn chỉ định chúng trực tiếp.

`--bind-services` không đưa mọi module trên module path vào image. Nó chỉ bổ sung các module provider phù hợp với service được các module trong đồ thị phân giải khai báo sử dụng, cùng dependency của các provider đó.

## 6. Những điều kiện để service được tìm thấy

- **Module tiêu thụ phải khai báo `uses`.** Với module có tên, gọi `ServiceLoader.load(...)` mà thiếu khai báo `uses` tương ứng có thể dẫn đến `ServiceConfigurationError` vì module không khai báo quyền sử dụng service đó.
- **Module provider phải khai báo `provides`.** Tên service và implementation phải khớp với interface mà ứng dụng sử dụng.
- **Provider phải nằm trên module path khi chạy `jlink`.** `--bind-services` không thể tìm một module không có trong các nguồn module được cung cấp.
- **Provider phải là module có thể liên kết.** `jlink` tạo image từ các module; một JAR chỉ chạy trên classpath hoặc automatic module không trở thành module có thể liên kết chỉ nhờ có file `META-INF/services`.
- **Phải kiểm tra dependency của provider.** Nếu một provider cần module khác, module đó cũng phải có trên module path để `jlink` phân giải thành công.
- **Không dựa vào thứ tự provider.** Nếu có nhiều implementation, `ServiceLoader` có thể trả về nhiều provider. Ví dụ dùng `findFirst()` chỉ để minh họa trường hợp có một provider; không nên xem thứ tự tìm thấy là quy tắc chọn provider ổn định.

Việc thêm `--bind-services` có thể làm image lớn hơn vì các provider và dependency của chúng được đưa vào runtime. Nếu muốn image nhỏ, hãy kiểm tra service nào thực sự được khai báo `uses`, provider nào có mặt trên module path và liệu có thể chọn một tập provider hẹp hơn hay không.

## 7. Cách xử lý lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
| --- | --- |
| `ServiceLoader` không tìm thấy provider | Kiểm tra `uses`, `provides`, service type, module path và việc dùng `--bind-services` hoặc `--add-modules`. |
| `ServiceConfigurationError` báo module không khai báo `uses` | Bổ sung `uses <Service>` vào `module-info.java` của module gọi `ServiceLoader`. |
| `jlink` báo không tìm thấy module provider | Kiểm tra module đã biên dịch, tên module trong `module-info.java` và đường dẫn `mods/` trong `--module-path`. |
| `jlink` báo lỗi khi liên kết một JAR thư viện | Kiểm tra JAR đó có phải explicit module hay không; `jlink` không đóng gói trực tiếp thư viện chỉ nằm trên classpath. |
| Image chạy được nhưng provider không xuất hiện | Xác nhận provider khai báo đúng `provides`, service được module ứng dụng khai báo `uses`, rồi tạo lại image với `--bind-services` hoặc chỉ định provider bằng `--add-modules`. |

## 8. Checklist trước khi phát hành image

1. Module ứng dụng `requires` module chứa service interface và khai báo `uses` cho interface đó.
2. Mỗi module provider khai báo đúng `provides <Service> with <Provider>`.
3. Các module provider và dependency của chúng có trong module path của lệnh `jlink`.
4. Chọn `--bind-services` để tự động liên kết provider theo service, hoặc dùng `--add-modules` để chỉ định provider cụ thể.
5. Chạy ứng dụng bằng Java nằm trong runtime image vừa tạo và kiểm tra kết quả service thực tế.

`--bind-services` giải quyết việc lựa chọn module provider trong lúc tạo runtime image. `ServiceLoader` vẫn chịu trách nhiệm tìm và sử dụng implementation khi ứng dụng chạy; hai cơ chế phối hợp với nhau nhưng hoạt động ở hai giai đoạn khác nhau.
