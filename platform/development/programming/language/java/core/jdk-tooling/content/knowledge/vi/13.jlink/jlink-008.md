# Include service binding với jlink

Tùy chọn **`--bind-services`** của công cụ `jlink` yêu cầu quá trình liên kết runtime image tìm và đưa vào image các module cung cấp dịch vụ (service provider modules) cho những service được các module đã chọn sử dụng, cùng các dependency cần thiết của provider.

Tùy chọn này đặc biệt hữu ích với ứng dụng dùng **`ServiceLoader`**. Ứng dụng có thể chỉ khai báo service interface và directive `uses`; module triển khai service được phát hiện qua directive `provides`. Khi tạo runtime image, `jlink --bind-services` liên kết các provider phù hợp mà không cần liệt kê từng provider trong `--add-modules`.

## 1. Service binding trong Java Module System là gì?

Java Platform Module System (JPMS) cho phép một module sử dụng dịch vụ thông qua interface mà không phụ thuộc trực tiếp vào module triển khai.

Có ba thành phần:

- **Service:** interface hoặc abstract class mô tả chức năng mà ứng dụng cần.
- **Service consumer:** module sử dụng dịch vụ. Trong `module-info.java`, module khai báo directive `uses`.
- **Service provider:** module triển khai dịch vụ. Trong `module-info.java`, module khai báo directive `provides ... with ...`.

Cách tổ chức này giúp tách phần định nghĩa API khỏi phần triển khai. Ứng dụng có thể sử dụng nhiều provider khác nhau mà không phải biên dịch lại để tham chiếu trực tiếp từng lớp triển khai.

Ví dụ về quan hệ:

```text
Application module
       |
       | uses GreetingService
       v
GreetingService interface
       ^
       | implements
       |
Provider module
       |
       | provides GreetingService with ...
       v
Concrete provider class
```

Khi liên kết runtime image, service binding giúp tìm những provider phù hợp trên module path và đưa chúng cùng dependency cần thiết vào image.

## 2. Phân biệt uses, provides và --bind-services

Ba khái niệm này có vai trò khác nhau:

| Thành phần | Khai báo ở đâu | Vai trò |
| --- | --- | --- |
| `uses` | `module-info.java` của consumer | Khai báo module cần sử dụng một service |
| `provides ... with ...` | `module-info.java` của provider | Đăng ký lớp triển khai service |
| `--bind-services` | Lệnh `jlink` | Tìm và liên kết các module provider cùng dependency của chúng vào runtime image |

Ví dụ khai báo consumer:

```java
module com.example.app {
    requires com.example.greeting.api;
    uses com.example.greeting.GreetingService;
}
```

Ví dụ khai báo provider:

```java
module com.example.greeting.provider {
    requires com.example.greeting.api;

    provides com.example.greeting.GreetingService
        with com.example.greeting.provider.EnglishGreetingService;
}
```

Directive `uses` và `provides` mô tả quan hệ service trong module descriptor. Tùy chọn `--bind-services` của `jlink` sử dụng những khai báo đó khi tạo image.

**Lưu ý:** `--bind-services` không tự viết directive `uses` hoặc `provides` vào module. Các module phải khai báo service đúng trong `module-info.java`.

## 3. Cú pháp của jlink --bind-services

Cú pháp cơ bản:

```bash
jlink --module-path <module-path> --add-modules <root-modules> --bind-services --output <directory>
```

Các thành phần:

- `--module-path`: nơi tìm các module đầu vào, chẳng hạn thư mục `jmods` của JDK và thư mục module đã biên dịch.
- `--add-modules`: các module gốc cần đưa vào runtime image.
- `--bind-services`: tìm và liên kết service provider modules cùng dependency cần thiết.
- `--output`: thư mục runtime image được tạo.

Ví dụ:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --bind-services --output image
```

Trên Windows PowerShell, dấu phân cách giữa các mục module path là dấu chấm phẩy:

```powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app --bind-services --output image
```

Trên macOS/Linux, dấu phân cách là dấu hai chấm:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --bind-services --output image
```

Thư mục `$JAVA_HOME/jmods` cung cấp các module nền tảng của JDK; `mods` chứa các module ứng dụng đã biên dịch. Dùng cùng một JDK tương thích cho `javac` và `jlink`.

## 4. Ví dụ hoàn chỉnh: ServiceLoader và ba module

Ví dụ sau tạo ba module:

1. `com.example.greeting.api`: định nghĩa service interface.
2. `com.example.greeting.app`: sử dụng service qua `ServiceLoader`.
3. `com.example.greeting.provider`: cung cấp một implementation.

Mục tiêu là liên kết runtime image chỉ với module ứng dụng làm root. `jlink --bind-services` sẽ tìm provider phù hợp trên module path và đưa provider vào image.

Cấu trúc thư mục:

```text
project/
  src/
    com.example.greeting.api/
      module-info.java
      com/example/greeting/GreetingService.java
    com.example.greeting.app/
      module-info.java
      com/example/greeting/app/Main.java
    com.example.greeting.provider/
      module-info.java
      com/example/greeting/provider/EnglishGreetingService.java
```

### Bước 1: Tạo module service API

Tệp **`src/com.example.greeting.api/module-info.java`**:

```java
module com.example.greeting.api {
    exports com.example.greeting;
}
```

Tệp **`src/com.example.greeting.api/com/example/greeting/GreetingService.java`**:

```java
package com.example.greeting;

public interface GreetingService {
    String greet();
}
```

Package được export để module consumer và provider có thể tham chiếu interface công khai.

### Bước 2: Tạo module provider

Tệp **`src/com.example.greeting.provider/module-info.java`**:

```java
module com.example.greeting.provider {
    requires com.example.greeting.api;

    provides com.example.greeting.GreetingService
        with com.example.greeting.provider.EnglishGreetingService;
}
```

Tệp **`src/com.example.greeting.provider/com/example/greeting/provider/EnglishGreetingService.java`**:

```java
package com.example.greeting.provider;

import com.example.greeting.GreetingService;

public final class EnglishGreetingService implements GreetingService {
    public EnglishGreetingService() {
    }

    @Override
    public String greet() {
        return "Hello from a linked service provider";
    }
}
```

Lớp provider triển khai interface và có public no-argument constructor. Package triển khai không cần export chỉ để đăng ký provider bằng directive `provides`.

### Bước 3: Tạo module ứng dụng sử dụng service

Tệp **`src/com.example.greeting.app/module-info.java`**:

```java
module com.example.greeting.app {
    requires com.example.greeting.api;
    uses com.example.greeting.GreetingService;
}
```

Directive `requires` cho phép ứng dụng đọc API module. Directive `uses` khai báo rằng ứng dụng cần service `GreetingService`.

Tệp **`src/com.example.greeting.app/com/example/greeting/app/Main.java`**:

```java
package com.example.greeting.app;

import com.example.greeting.GreetingService;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        GreetingService service = ServiceLoader
            .load(GreetingService.class)
            .findFirst()
            .orElseThrow(() ->
                new IllegalStateException("No GreetingService provider found")
            );

        System.out.println(service.greet());
    }
}
```

Ứng dụng chỉ phụ thuộc vào interface `GreetingService`; nó không import hoặc tạo trực tiếp `EnglishGreetingService`. `ServiceLoader` tìm implementation đã được module provider đăng ký.

### Bước 4: Biên dịch ba module

Chạy tại thư mục gốc `project`.

**Windows PowerShell:**

```powershell
New-Item -ItemType Directory -Force mods | Out-Null
javac -d mods --module-source-path src -m com.example.greeting.api,com.example.greeting.app,com.example.greeting.provider
```

**macOS/Linux:**

```bash
mkdir -p mods
javac -d mods --module-source-path src -m com.example.greeting.api,com.example.greeting.app,com.example.greeting.provider
```

Sau khi biên dịch, cấu trúc đầu ra có dạng:

```text
mods/
  com.example.greeting.api/
    module-info.class
    com/example/greeting/GreetingService.class
  com.example.greeting.app/
    module-info.class
    com/example/greeting/app/Main.class
  com.example.greeting.provider/
    module-info.class
    com/example/greeting/provider/EnglishGreetingService.class
```

Mỗi thư mục trong `mods` là một exploded module, có `module-info.class` và các class file tương ứng.

### Bước 5: Tạo runtime image với service binding

**Windows PowerShell:**

```powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.greeting.app --bind-services --output image
```

**macOS/Linux:**

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.greeting.app --bind-services --output image
```

Phân tích lệnh:

- Root module duy nhất được chỉ định là `com.example.greeting.app`.
- Module ứng dụng yêu cầu `com.example.greeting.api`, nên API module được phân giải như dependency.
- Ứng dụng khai báo `uses GreetingService`.
- Provider module khai báo `provides GreetingService with EnglishGreetingService`.
- `--bind-services` tìm provider phù hợp trong module path, đưa provider và các dependency cần thiết vào runtime image.

Không cần thêm `com.example.greeting.provider` vào `--add-modules` trong ví dụ này vì mục tiêu là minh họa việc service binding tự tìm provider. Provider phải có mặt và quan sát được trên module path đầu vào.

### Bước 6: Chạy ứng dụng từ runtime image

**Windows PowerShell:**

```powershell
.\image\bin\java.exe -m com.example.greeting.app/com.example.greeting.app.Main
```

**macOS/Linux:**

```bash
./image/bin/java -m com.example.greeting.app/com.example.greeting.app.Main
```

Kết quả chính xác:

```text
Hello from a linked service provider
```

Kết quả cho thấy provider module đã được liên kết vào runtime image và `ServiceLoader` tìm thấy implementation khi ứng dụng chạy.

## 5. Điều gì xảy ra nếu không dùng --bind-services?

Nếu chỉ chạy:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.greeting.app --output image-no-bind
```

và provider không phải dependency trực tiếp hoặc root module khác, provider có thể không được đưa vào image. Khi chạy ứng dụng, `ServiceLoader` không tìm thấy provider và ví dụ trên sẽ ném:

```text
java.lang.IllegalStateException: No GreetingService provider found
```

Đây là tình huống thường gặp khi ứng dụng sử dụng service interface và mong đợi provider được phát hiện tự động, nhưng image chỉ chứa các module được phân giải theo dependency thông thường.

Có hai cách giải quyết:

- Dùng `--bind-services` để liên kết provider cho service mà module đã chọn sử dụng.
- Khai báo provider module tường minh trong `--add-modules` nếu muốn tự quyết định module provider cần có.

Ví dụ liên kết provider tường minh:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.greeting.app,com.example.greeting.provider --output image-explicit
```

Lệnh này thêm provider như một root module. Vì vậy, service binding không còn cần thiết để đưa riêng provider này vào image.

Trên Windows, thay dấu hai chấm trong module path bằng dấu chấm phẩy:

```powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.greeting.app,com.example.greeting.provider --output image-explicit
```

## 6. Provider được tìm như thế nào?

Trong module system, service provider được khai báo trong module descriptor. Ví dụ:

```java
provides com.example.greeting.GreetingService
    with com.example.greeting.provider.EnglishGreetingService;
```

Khi phân giải module cho runtime image:

1. `jlink` bắt đầu từ các root module trong `--add-modules`.
2. Các dependency được yêu cầu qua `requires` được phân giải.
3. Khi có `--bind-services`, service binding tìm các module provider cho service mà các module đã phân giải khai báo sử dụng.
4. Provider module và dependency của nó được thêm vào tập module liên kết.
5. Quá trình có thể tiếp tục với các service mà provider module sử dụng.

Do đó, một provider có thể kéo theo các module khác. Image cuối cùng không chỉ bao gồm provider class mà còn có các module cần thiết để provider hoạt động.

`--bind-services` chỉ tìm các provider có thể quan sát được trong module path và được khai báo hợp lệ. Nó không tải mọi JAR trong thư mục một cách tùy ý và không tự biến classpath library thành named module.

## 7. --bind-services và --add-modules khác nhau thế nào?

| Tiêu chí | `--add-modules` | `--bind-services` |
| --- | --- | --- |
| Vai trò | Chọn module gốc cần đưa vào image | Tìm và thêm module provider cho service được sử dụng |
| Đầu vào | Danh sách tên module | Quan hệ `uses` và `provides` trong module descriptor |
| Cách chọn | Người build chỉ định rõ | Module system phân giải provider phù hợp |
| Dependency | Dependency của module gốc được phân giải | Dependency của provider cũng được liên kết |
| Khi phù hợp | Ứng dụng biết chính xác các module cần có | Ứng dụng dùng service và muốn tự động liên kết provider |

Hai tùy chọn có thể dùng cùng nhau:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.greeting.app,com.example.metrics --bind-services --output image
```

Trong ví dụ, `com.example.greeting.app` và `com.example.metrics` là các root module được chọn trực tiếp. Service binding tiếp tục tìm provider cho các service mà các module đã phân giải sử dụng.

## 8. Tìm provider bằng --suggest-providers

`jlink` có tùy chọn `--suggest-providers` để gợi ý các module cung cấp một hoặc nhiều service type có thể tìm thấy trên module path.

Ví dụ:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --suggest-providers com.example.greeting.GreetingService
```

Trên Windows PowerShell:

```powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --suggest-providers com.example.greeting.GreetingService
```

Tùy chọn này hữu ích khi:

- Không biết module nào cung cấp một service.
- Muốn kiểm tra module path có provider mong đợi hay không.
- Điều tra vì sao service binding không đưa provider vào image.
- Xác định provider trước khi quyết định liên kết tự động hoặc thêm module tường minh.

Kết quả phụ thuộc vào các module có mặt trên module path và khai báo `provides` của chúng.

## 9. Ảnh hưởng của service binding đến kích thước runtime image

`--bind-services` có thể làm runtime image lớn hơn vì nó bổ sung provider modules và các dependency của chúng.

Kích thước tăng hay giảm phụ thuộc vào:

- Số lượng service được các module đã chọn sử dụng.
- Số provider tìm được cho mỗi service.
- Các dependency mà provider yêu cầu.
- Những module nền tảng hoặc module ứng dụng đã có sẵn trong image.

Nếu một service có nhiều provider quan sát được, quá trình binding có thể liên kết nhiều provider phù hợp. Không nên giả định chỉ provider đầu tiên được đưa vào image vì `ServiceLoader.findFirst()` chỉ chọn một provider khi ứng dụng chạy; thao tác đó không phải quy tắc chọn module của `jlink`.

Để tạo image nhỏ nhất, hãy cân nhắc:

- Chỉ đưa vào module gốc thực sự cần thiết.
- Giới hạn module path ở các module đầu vào được quản lý.
- Kiểm tra provider nào thực sự cần thiết.
- So sánh image có và không có `--bind-services`.
- Nếu chỉ cần một provider cụ thể, cân nhắc thêm module đó tường minh và thiết kế module path phù hợp.

Không bỏ `--bind-services` chỉ để giảm kích thước nếu ứng dụng cần provider để hoạt động đúng.

## 10. Những điều kiện cần để service binding hoạt động

Kiểm tra các điều kiện sau:

- Module consumer khai báo `uses service.Interface`.
- Module provider khai báo `provides service.Interface with ProviderClass`.
- Provider class triển khai đúng service type.
- Provider module có thể đọc service API module thông qua `requires`.
- Module provider có mặt và quan sát được trên module path mà `jlink` sử dụng.
- Module path chứa cả module ứng dụng, module API và provider cần thiết.
- Dùng JDK có hỗ trợ JPMS và công cụ `jlink` tương thích.
- Ứng dụng thực sự gọi `ServiceLoader` hoặc cơ chế service tương ứng.

Với provider class thông thường được khai báo trong `provides`, provider cần đáp ứng yêu cầu của ServiceLoader, chẳng hạn lớp public và public no-argument constructor. Java cũng hỗ trợ dạng provider method theo quy tắc của service provider module; khi dùng dạng đó, hãy tuân thủ yêu cầu trong tài liệu ServiceLoader của JDK tương ứng.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| ServiceLoader không tìm thấy provider trong image | Provider module không được liên kết | Kiểm tra `uses`, `provides`, module path và dùng `--bind-services` hoặc thêm provider vào `--add-modules` |
| `ServiceConfigurationError` báo module không khai báo uses | Consumer thiếu directive `uses` | Thêm `uses` vào module descriptor của consumer rồi biên dịch lại |
| Provider module không được nhận diện | Thiếu provider trên module path hoặc descriptor không có `provides` đúng | Kiểm tra `jmod describe`, `jar --describe-module` hoặc cấu trúc module đã biên dịch |
| Provider không khởi tạo được | Provider class hoặc constructor không đáp ứng yêu cầu ServiceLoader | Kiểm tra class triển khai và constructor/provider method |
| `jlink` báo không tìm thấy module | Module path thiếu thư mục `mods` hoặc JDK `jmods` | Kiểm tra đường dẫn và dấu phân cách theo hệ điều hành |
| Image lớn hơn dự kiến | Binding bổ sung nhiều provider và dependency | Dùng `--suggest-providers`, kiểm tra module path và so sánh danh sách module |
| Chạy ứng dụng trực tiếp được nhưng image thiếu provider | Provider có trên module path khi chạy nhưng không được link vào image | Dùng `--bind-services` hoặc thêm provider module tường minh |
| Dùng provider trên classpath nhưng jlink không tìm thấy | `jlink` liên kết module, không đóng gói classpath tùy ý | Đóng gói provider thành module phù hợp và đưa vào module path |

## 12. Quy trình kiểm tra khi dùng --bind-services

Khi tạo runtime image cho ứng dụng dùng ServiceLoader:

1. Xác định service interface và module sở hữu interface.
2. Kiểm tra consumer đã khai báo `uses`.
3. Kiểm tra provider đã khai báo `provides ... with ...`.
4. Biên dịch tất cả module và xác nhận cấu trúc module output.
5. Đưa module ứng dụng, API, provider và JDK `jmods` vào module path.
6. Chạy `jlink --suggest-providers` nếu cần xác nhận provider có thể được tìm thấy.
7. Dùng `jlink --add-modules <root> --bind-services` để tạo image.
8. Kiểm tra danh sách module trong image bằng `image/bin/java --list-modules`.
9. Chạy ứng dụng từ chính Java executable trong image.
10. Kiểm tra log và kết quả ServiceLoader trong môi trường triển khai.

Khi cần so sánh, tạo thêm image không có `--bind-services` hoặc image có provider được chỉ định tường minh. Dùng các image ở thư mục đầu ra riêng để tránh ghi đè hoặc nhầm kết quả.

## 13. Ghi nhớ

- `uses` khai báo service mà module consumer cần.
- `provides ... with ...` đăng ký implementation trong module provider.
- `jlink --bind-services` liên kết các provider module phù hợp và dependency của chúng vào runtime image.
- Provider phải có mặt và quan sát được trên module path đầu vào.
- `--bind-services` không thay thế `--add-modules`; root module vẫn phải được chỉ định.
- Nếu không dùng service binding, có thể thêm provider module tường minh bằng `--add-modules`.
- `--suggest-providers` giúp tìm module cung cấp một service.
- Service binding có thể làm image lớn hơn vì bổ sung provider và dependency.
- `jlink` liên kết module; nó không đóng gói tùy ý dependency chỉ có trên classpath.

Khi hiểu `--bind-services`, bạn có thể tạo runtime image gọn nhưng vẫn giữ đầy đủ provider mà ứng dụng cần, đồng thời kiểm soát rõ ràng quan hệ giữa service API, consumer và implementation trong Java Module System.
