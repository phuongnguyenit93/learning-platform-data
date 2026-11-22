# Tách ứng dụng thành mô-đun API, triển khai và khởi chạy (Java 9+)

## 1. Bài toán và kết quả cần đạt

Giả sử một ứng dụng cần gửi lời chào nhưng không muốn phụ thuộc cứng vào lớp cung cấp lời chào. Ta chia thành **ba named modules** của Java Platform Module System (JPMS):

- **`academy.api`:** công bố hợp đồng `GreetingService`. Các thành phần khác biết phải gọi phương thức nào, không cần biết lớp triển khai cụ thể.
- **`academy.greeter`:** triển khai `GreetingService` bằng `VietnameseGreeter`. Module này đăng ký provider của service nhưng **không export** package chứa lớp triển khai.
- **`academy.app`:** phụ thuộc vào API và tìm provider bằng `ServiceLoader` lúc chạy. App không khai báo `requires academy.greeter;`.

Kết quả mong đợi: biên dịch cả ba module, chạy ứng dụng qua **module path**, in `Xin chào, Java!`; đóng gói thành modular JAR và vẫn chạy được.

```text
                 Compile-time readability
 academy.app ------------------------------> academy.api
     |                                           ^
     | uses academy.api.GreetingService          |
     |                                           | requires academy.api
     v                                           |
 ServiceLoader  --- tìm service provider ---> academy.greeter
                                                |
                                                | provides GreetingService
                                                | with VietnameseGreeter
                                                v
                                       Triển khai ở package riêng
                                       không cần exports package đó
```

Dấu mốc Java 9 là **`module-info.java`, module path, `requires`, `exports`, `uses`, `provides` và khả năng liên kết service với module graph**. Các cơ chế này vẫn áp dụng trên JDK hiện hành. Bài thực hành sử dụng JDK 17+ làm baseline để mã và lệnh biên dịch có thể sử dụng trong dự án hiện đại.

### Khi nào nên tách như vậy?

Cách chia này phù hợp cho plugin, backend có nhiều provider, ứng dụng thay đổi cơ chế triển khai theo môi trường hoặc thư viện cần công bố API ổn định. Nếu một chương trình rất nhỏ chỉ có vài class và không có nhu cầu boundary/service, việc tách thành nhiều module có thể làm build phức tạp thêm mà không mang lại lợi ích. Module là đơn vị **đọc phụ thuộc, đóng gói và encapsulation**, không phải đơn vị chạy một JVM riêng: cả ba module trong ví dụ chạy trên cùng một JVM.

## 2. Những từ khóa JPMS phải hiểu trước

Mỗi **named module** có một descriptor `module-info.java` ở gốc nguồn của module.

| Khai báo | Viết ở module nào? | Tác dụng |
| --- | --- | --- |
| `exports academy.api;` | `academy.api` | Công bố package API để các module đọc được nó có thể truy cập những kiểu `public` trong package |
| `requires academy.api;` | `academy.app` và `academy.greeter` | Khai báo module cần đọc `academy.api` để dùng interface `GreetingService` |
| `uses academy.api.GreetingService;` | `academy.app` | Khai báo module là **consumer** của service; hỗ trợ `ServiceLoader` và service binding |
| `provides academy.api.GreetingService with academy.greeter.VietnameseGreeter;` | `academy.greeter` | Đăng ký lớp cung cấp service ở module triển khai |
| `opens package.name;` | Chỉ khi thực sự cần reflection tới package | Cho phép truy cập phản chiếu theo quy tắc JPMS; **không cần** cho demo `ServiceLoader` này |
| `requires transitive academy.api;` | Module trung gian khi thiết kế muốn cho module đọc nó đọc tiếp API | Khác `requires` thông thường; **không cần** trong sơ đồ ba module hiện tại |

**Readability khác accessibility:** app có `requires academy.api` thì module app *đọc* module API. Nhưng loại `public` trong một package của API còn cần package ấy được `exports` thì app mới truy cập qua import. Lớp trong package không export của provider vẫn có thể được `ServiceLoader` tạo qua khai báo `provides` đúng chuẩn, không cần app import trực tiếp.

**Module path khác classpath:** `--module-path` tìm *named modules*, đọc descriptor và giải quyết graph. Đưa `module-info.java` hoặc JAR module vào classpath rồi chạy `java Main` là một mô hình khác; nó không thực hành các boundary JPMS theo cách đang học.

## 3. Cây thư mục hoàn chỉnh

Tạo dự án `jpms-greeting-demo` như sau. Tên folder trực tiếp dưới `src` trùng với **tên module**:

```text
jpms-greeting-demo/
└── src/
    ├── academy.api/
    │   ├── module-info.java
    │   └── academy/api/GreetingService.java
    ├── academy.greeter/
    │   ├── module-info.java
    │   └── academy/greeter/VietnameseGreeter.java
    └── academy.app/
        ├── module-info.java
        └── academy/app/Main.java
```

Các file `mods/` chứa bytecode và `dist/` chứa JAR sẽ được lệnh build tạo ra; ban đầu chưa cần tạo. **`academy.api` là tên module**, còn `academy/api` là đường dẫn package theo quy tắc `package academy.api;`. Đừng nhầm tên module với tên package hoặc tên tệp.

## 4. Viết module API: hợp đồng không biết implementation

Tệp **`src/academy.api/module-info.java`**:

```java
module academy.api {
    exports academy.api;
}
```

Tệp **`src/academy.api/academy/api/GreetingService.java`**:

```java
package academy.api;

public interface GreetingService {
    String greet(String name);
}
```

Interface chỉ định hành vi nhận `name`, trả kết quả `String`. Module API không import hay `requires` module app/provider nào; nhờ vậy module triển khai có thể được thay thế mà không tạo vòng phụ thuộc.

Điểm thiết kế: public API nên nhỏ và rõ ràng. Tránh đưa các kiểu nội bộ của implementation vào chữ ký `GreetingService`, vì như vậy client lại phải biết các chi tiết không thuộc hợp đồng. Khi thư viện lớn lên, thay đổi API cần xem xét khả năng tương thích nguồn/binary của các module tiêu thụ.

## 5. Viết module triển khai: requires + provides

Tệp **`src/academy.greeter/module-info.java`**:

```java
module academy.greeter {
    requires academy.api;

    provides academy.api.GreetingService
        with academy.greeter.VietnameseGreeter;
}
```

Tệp **`src/academy.greeter/academy/greeter/VietnameseGreeter.java`**:

```java
package academy.greeter;

import academy.api.GreetingService;

public final class VietnameseGreeter implements GreetingService {
    @Override
    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
```

**Vì sao có `requires`?** Provider phải đọc module chứa interface để `implements GreetingService`.

**Vì sao có `provides ... with ...`?** Module descriptor đăng ký quan hệ *service → provider* cho cơ chế discovery. Với module provider được khai báo bằng `provides`, `ServiceLoader` có thể tìm và khởi tạo provider nếu module được resolve vào layer thích hợp.

**Vì sao không `exports academy.greeter;`?** App chỉ cần nhìn thấy interface `GreetingService`. Nó không cần import, `new` hay biết tên `VietnameseGreeter`. Không export package này giúp giảm phần implementation trở thành API công khai, nhưng không tự biến module thành sandbox bảo mật.

Lớp provider trong ví dụ là `public`, có public no-argument constructor mặc định (vì lớp không khai báo constructor riêng) và implements interface. Đây là hình thức cung cấp service đơn giản, đúng hợp đồng `ServiceLoader` của JDK hiện hành. Nếu provider cần cấu hình ngoài, hãy thiết kế provider factory/khởi tạo rõ ràng; demo dùng constructor không tham số để dễ quan sát.

## 6. Viết module ứng dụng: requires + uses + ServiceLoader

Tệp **`src/academy.app/module-info.java`**:

```java
module academy.app {
    requires academy.api;

    uses academy.api.GreetingService;
}
```

Tệp **`src/academy.app/academy/app/Main.java`**:

```java
package academy.app;

import academy.api.GreetingService;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        GreetingService greeting = ServiceLoader.load(GreetingService.class)
                .findFirst()
                .orElseThrow(() -> new IllegalStateException(
                        "No GreetingService implementation found"));

        System.out.println(greeting.greet("Java"));
    }
}
```

Các ý quan trọng:

1. App **requires `academy.api`** vì import và sử dụng `GreetingService`.
2. App **uses `academy.api.GreetingService`** vì nó là named module gọi `ServiceLoader.load(...)` để tìm service; bỏ `uses` có thể gây `ServiceConfigurationError` theo hợp đồng API.
3. App **không requires `academy.greeter`**. Provider là lựa chọn triển khai tại runtime.
4. `ServiceLoader.load(GreetingService.class)` tìm providers trong phạm vi class loader/module layer tương ứng, theo cơ chế được định nghĩa trong `ServiceLoader`. `findFirst()` trả một provider nếu có; ví dụ **chỉ có một provider** nên kết quả xác định.
5. Trong hệ thống có nhiều providers, **không dựa vào thứ tự provider** để quyết định triển khai chính. Hãy định nghĩa cơ chế lựa chọn rõ ràng theo cấu hình hoặc metadata, kiểm tra provider được phép và xử lý trường hợp không có provider.

`ServiceLoader` không giống `Class.forName("...VietnameseGreeter")`: module app không cần hardcode tên lớp implementation hoặc dùng reflection mở tùy tiện package nội bộ. Không cần ghi file `META-INF/services/...` khi provider là **named module** khai báo `provides` như trong bài này.

## 7. Biên dịch ba module trong một lệnh

Mở terminal tại gốc `jpms-greeting-demo`. Kiểm tra công cụ `javac` và `java` đều dùng một JDK phù hợp:

```bash
javac -version
java -version
```

Để biên dịch tất cả source modules, dùng:

```bash
javac -encoding UTF-8 --release 17 --module-source-path src -d mods --module academy.api,academy.greeter,academy.app
```

Trong bài thực hành, lệnh này chạy được trên JDK 17+ có khả năng biên dịch target 17. Nếu đang dùng JDK 17 thì `--release 17` vẫn hợp lệ; nếu dùng JDK 24/25 thì nó giúp giới hạn API và class-file version tương ứng với Java 17.

Giải thích tùy chọn:

| Thành phần | Ý nghĩa |
| --- | --- |
| `-encoding UTF-8` | Đọc source chứa tiếng Việt bằng UTF-8 |
| `--release 17` | Biên dịch theo Java 17, gồm ngôn ngữ, class-file target và nền tảng API tương thích |
| `--module-source-path src` | `src` là root chứa các module nguồn `academy.api`, `academy.greeter`, `academy.app` |
| `-d mods` | Ghi `.class` vào output root `mods`, chia thành thư mục theo module |
| `--module academy.api,academy.greeter,academy.app` | Yêu cầu compiler biên dịch các module này từ source module path; đây là danh sách **module names** |

Sau khi hoàn tất, kiểm tra:

```text
mods/
├── academy.api/
│   ├── module-info.class
│   └── academy/api/GreetingService.class
├── academy.greeter/
│   ├── module-info.class
│   └── academy/greeter/VietnameseGreeter.class
└── academy.app/
    ├── module-info.class
    └── academy/app/Main.class
```

Mỗi thư mục `mods/<module>` là **exploded module** có descriptor biên dịch. Đây là bytecode của ba module, chưa phải ba JVM hay ba service tiến trình.

## 8. Khởi chạy ứng dụng theo JPMS

Chạy từ **thư mục gốc dự án**:

```bash
java --module-path mods --module academy.app/academy.app.Main
```

Kết quả:

```text
Xin chào, Java!
```

Định dạng của `--module` (`-m`) là `module-name/fully.qualified.MainClass`. Ở đây app được launch như **named module**, Java đọc các descriptor từ `mods` và giải quyết module graph.

Điều đáng chú ý: app không `requires academy.greeter`; nó chỉ `uses GreetingService`. Khi chạy bằng launcher `java` chuẩn với provider module có mặt và được phát hiện trên module path, **service binding** có thể bổ sung module provider vào graph để `ServiceLoader` tìm thấy. Trong ví dụ, đây là hành vi thực tế đã kiểm thử: provider từ `academy.greeter` được nạp và in lời chào.

Có thể xem module resolution thay vì đoán nguyên nhân:

```bash
java --show-module-resolution --module-path mods --module academy.app/academy.app.Main
```

Lệnh này in thêm thông tin resolution/binding, nên stdout có **nhiều dòng phụ thuộc phiên bản JDK/module graph**; dòng ứng dụng ở cuối vẫn là `Xin chào, Java!`. Không coi thứ tự/định dạng chi tiết của các log là API ổn định.

### Điều gì xảy ra nếu thiếu provider?

Giả sử bản phân phối chỉ có `academy.api` và `academy.app`, **không có `academy.greeter`** và không có provider tương thích nào khác trên runtime module path/layer. Hai module app/API vẫn có thể resolve được vì app không yêu cầu implementation module trực tiếp, nhưng `ServiceLoader.findFirst()` không tìm thấy provider; ví dụ chủ động ném `IllegalStateException("No GreetingService implementation found")`.

Đây là dấu hiệu cho thấy dependency của API và dependency của **deployment** khác nhau. Một app có thể không phụ thuộc source vào provider, nhưng cấu hình phát hành vẫn phải mang đúng implementation. Trong thực tế, hãy kiểm tra trước lúc deploy rằng runtime image/module path có provider module đã phê duyệt.

## 9. Đóng gói thành modular JAR

Dùng `jar` có sẵn trong JDK. Các lệnh sau thực hiện sau bước `javac` và cần thư mục `mods` có đủ `.class`:

```bash
mkdir dist
jar --create --file dist/academy.api.jar -C mods/academy.api .
jar --create --file dist/academy.greeter.jar -C mods/academy.greeter .
jar --create --file dist/academy.app.jar --main-class academy.app.Main -C mods/academy.app .
```

`mkdir dist` hoạt động trong terminal POSIX; trên PowerShell cũng có lệnh `mkdir dist` tương đương. Nếu thư mục đã tồn tại, bỏ qua bước tạo hoặc dùng lệnh phù hợp để bảo đảm thư mục tồn tại. Sau đóng gói:

```text
dist/
├── academy.api.jar
├── academy.greeter.jar
└── academy.app.jar
```

`jar --create` đóng các module đã biên dịch vào JAR; vì mỗi JAR chứa `module-info.class`, chúng là **explicit modular JARs**, không phải automatic modules. `--main-class academy.app.Main` lưu entry point trong module descriptor của JAR app, cho phép chạy bằng **tên module**:

```bash
java --module-path dist --module academy.app
```

Stdout:

```text
Xin chào, Java!
```

Lệnh chạy này đã được kiểm thử với cả ba modular JAR. Nếu không dùng `--main-class` ở bước đóng gói, chạy với tên class đầy đủ: `java --module-path dist --module academy.app/academy.app.Main`.

Dùng `jar --describe-module` để xác minh descriptor được đóng gói thật sự:

```bash
jar --describe-module --file dist/academy.api.jar
jar --describe-module --file dist/academy.greeter.jar
jar --describe-module --file dist/academy.app.jar
```

Kết quả sẽ cho thấy:

- `academy.api`: `exports academy.api`;
- `academy.greeter`: `requires academy.api` và `provides academy.api.GreetingService with academy.greeter.VietnameseGreeter`;
- `academy.app`: `requires academy.api`, `uses academy.api.GreetingService` và `main-class academy.app.Main`.

Một vài dòng `requires java.base mandated` là quan hệ bắt buộc với module nền tảng, không phải lỗi. Đường dẫn tuyệt đối tới JAR và thứ tự một số dòng phụ thuộc môi trường; chỉ cần kiểm tra các khai báo thiết yếu.

## 10. Vì sao không cần yêu cầu module triển khai trong module app?

Nếu app viết:

```java
module academy.app {
    requires academy.api;
    requires academy.greeter;
}
```

thì ứng dụng đã nêu rõ tên module triển khai trong descriptor. Đó có thể là chủ đích khi app thật sự dùng implementation trực tiếp, nhưng sẽ **giảm khả năng đổi provider độc lập**. Trong ví dụ service-based, app dùng:

```java
module academy.app {
    requires academy.api;
    uses academy.api.GreetingService;
}
```

và provider tự công bố:

```java
module academy.greeter {
    requires academy.api;
    provides academy.api.GreetingService
            with academy.greeter.VietnameseGreeter;
}
```

Việc dùng `provides` không biến provider thành một thư viện mà app có thể import tùy ý. Interface `GreetingService` là hợp đồng tiêu chuẩn để giao tiếp. Sự phân tách này hữu ích khi thêm provider thứ hai hay thay bằng cách triển khai khác mà không sửa code trong app.

**Điểm cần kiểm soát:** vì provider được chọn tại runtime, phát hành ứng dụng phải xác thực được provider nào được phép và cách chọn provider nếu có nhiều kết quả. `ServiceLoader.findFirst()` tốt cho demo một provider; với nhiều provider không nên lấy phần tử đầu làm chính sách nghiệp vụ hoặc an ninh.

### Nếu không cần ServiceLoader

Trong trường hợp app **cố ý dùng một implementation đã biết** và không cần plugin/replaceability, cấu hình `requires academy.greeter` và export package cần dùng có thể là giải pháp đơn giản hơn, nhưng đó là mô hình phụ thuộc trực tiếp. Hai mô hình hợp lệ cho những nhu cầu khác nhau. Không thêm `uses/provides` chỉ vì dự án có `module-info.java`; chỉ thêm khi muốn *service-based discovery*.

## 11. Mở rộng: biên dịch từng module và phụ thuộc build

Với dự án nhiều module, build tool thường biên dịch API trước rồi implementation/app sau. Khi source từng module tách ở nhiều project, quy trình về nguyên tắc là:

1. Biên dịch `academy.api` trước để có bytecode/module descriptor của API.
2. Đặt module API đã biên dịch lên **compiler module path** khi build `academy.greeter` và `academy.app`.
3. Đóng gói các modular JAR độc lập và đưa chúng vào runtime module path theo phân phối thực tế.

Điểm quan trọng: `requires academy.api` ở descriptor và `--module-path` ở lệnh compile là hai phần bổ trợ. Một cái xác định **quan hệ module**, cái kia cung cấp **địa điểm tìm module**. Không giả định `requires` tự tải dependency từ Maven Central hoặc cấu hình thư viện; Gradle/Maven (nếu dùng) phải được khai báo dependency/build riêng.

Bài thực hành chọn **biên dịch nhiều source modules trong một lệnh** để không phụ thuộc công cụ build và để quan sát thẳng tác dụng của `--module-source-path`. Trong dự án thật, Gradle/Maven có thể làm nhiều bước compile, packaging và test giúp bạn, nhưng cần giữ đúng module descriptors, module path và service provider packaging.

## 12. Runtime image và service binding khi phát hành

Một số hệ thống tạo **custom runtime image** bằng `jlink` hoặc trình đóng gói ứng dụng `jpackage`. Đây là bước khác với việc tạo JAR:

- `javac` tạo class files.
- `jar` tạo modular JARs.
- `java --module-path ... --module ...` khởi chạy module từ JDK hiện tại.
- `jlink` tạo runtime image chứa một tập module.
- `jpackage` đóng gói ứng dụng thành bản phân phối cài đặt/chạy được, có thể tạo runtime image.

Với hệ thống dùng service như ví dụ, cần chú ý **provider module có thể không nằm trong closure `requires` thông thường**. Theo hướng dẫn hiện hành, `jlink` không tự làm service binding nếu không yêu cầu; `--bind-services` sẽ bổ sung các provider được tìm thấy cho những service đã khai báo. Hoặc cấu hình `--add-modules` để chỉ rõ provider cần đóng gói. Đừng giả định service hoạt động trên đầy đủ JDK thì custom runtime image chắc chắn chứa provider.

Một điểm cập nhật cần biết: **từ JDK 25, `jpackage` không mặc định đưa service binding vào runtime image**; khi cần có thể truyền tùy chọn `jlink` thông qua `--jlink-options --bind-services` (đồng thời giữ các jlink options khác mong muốn). Đây là thay đổi **đang áp dụng**, nên kiểm thử nội dung image thực tế trên đúng JDK phát hành. Không bật hết provider theo thói quen nếu sản phẩm cần phân phối chỉ một số implementation được phê duyệt.

Khi deploy, cần kiểm thử ít nhất: app khởi chạy bằng module path/runtime image thực tế; provider có thể tìm thấy; tất cả thư viện và module dependencies phù hợp; quyền hệ thống tệp/cấu hình runtime; và lỗi provider thiếu được báo rõ ràng.

## 13. Lỗi phổ biến và cách chẩn đoán

| Biểu hiện | Nguyên nhân có thể | Cách sửa |
| --- | --- | --- |
| `module not found: academy.api` | Compile/run module app nhưng không cung cấp API module trên module path/source path | Kiểm tra `mods`/`dist`, `module-info.class` và `--module-path` đúng thư mục |
| `package academy.api is not visible` | Thiếu `requires academy.api` hoặc thiếu `exports academy.api` | Sửa descriptor đúng module; kiểm tra `public` của interface |
| Compiler báo `module not found on module source path` | Sai `src/<module-name>/module-info.java` hoặc tên module không khớp thư mục | Đối chiếu tên thư mục, descriptor và `--module-source-path src` |
| `ServiceConfigurationError` khi load service | App named module thiếu `uses` hoặc cấu hình provider không hợp lệ | Khai báo `uses` ở app; `provides ... with ...` và class provider hợp lệ ở implementation |
| `No GreetingService implementation found` | Provider JAR/module không ở runtime path hoặc chưa được resolve/bind; không có provider | Kiểm tra đóng gói provider, module resolution và runtime image |
| `ClassNotFoundException` / `Could not find or load main class` | Chạy bằng classpath thay vì đúng module entry point, sai package/class | Dùng `java --module-path ... --module academy.app/academy.app.Main` |
| Provider compile được nhưng không tìm thấy khi chạy image đóng gói | Image không bao gồm module provider | Cấu hình `jlink --bind-services` hoặc `--add-modules` rõ ràng; kiểm tra nội dung image |
| Có hai providers mà lời chào thay đổi ngoài ý muốn | Dùng `findFirst()` và dựa vào thứ tự discovery | Thiết kế cách chọn provider tường minh, xử lý nhiều/không có provider |
| `jar --describe-module` không có `provides`/`uses` | Không đóng gói `module-info.class` đúng cách | Dùng bytecode từ source module build, kiểm tra descriptor trước phát hành |
| Gộp tất cả class vào một JAR và chỉ đổi tên thành “modular” | Mất ranh giới module, descriptor và dependency graph riêng | Giữ đúng module boundaries hoặc thiết kế lại module graph có chủ đích |

Để cô lập nguyên nhân, kiểm tra theo thứ tự **source descriptor → compiler output → modular JAR descriptor → runtime module resolution → service lookup**. Không sửa bằng cách mở toàn bộ module `open module ...` hoặc tự thêm `--add-opens` hàng loạt khi lỗi là module path/`requires`/`uses`.

## 14. Luyện tập và câu hỏi tự kiểm tra

1. Vì sao `academy.app` cần `requires academy.api` nhưng không cần `requires academy.greeter` trong ví dụ `ServiceLoader`?
2. Bỏ `exports academy.api` ở API module sẽ tạo ra lỗi thuộc loại readability hay accessibility?
3. Nếu bỏ `uses academy.api.GreetingService` ở app, chuyện gì có thể xảy ra khi gọi `ServiceLoader.load`?
4. Nếu bỏ `provides ... with ...` ở implementation, `ServiceLoader` có thể tìm provider nhờ module descriptor nữa không?
5. Vì sao `academy.greeter` cần `requires academy.api` dù app không cần `requires academy.greeter`?
6. `mods/academy.greeter/module-info.class` và `dist/academy.greeter.jar` giữ thông tin service provider ở đâu?
7. Hãy bỏ `academy.greeter.jar` khỏi runtime module path và dự đoán đầu ra/lỗi, rồi đưa lại và so sánh.
8. Hãy thay `VietnameseGreeter` bằng một provider khác trong module implementation; cần thay đổi API/app hay chỉ implementation và cách phân phối?
9. Khi có nhiều provider, vì sao `findFirst()` không nên là quy tắc kinh doanh chọn nhà cung cấp?
10. Vì sao custom runtime image có thể thiếu provider dù bản chạy trên JDK đầy đủ hoạt động tốt?

### Bài tập mở rộng

Thêm một module triển khai khác, ví dụ `academy.greeter.english`, với `provides academy.api.GreetingService with ...EnglishGreeter;`. Giữ API và app không đổi. Để kiểm soát kết quả, thay `findFirst()` bằng lựa chọn provider có **metadata hoặc định danh được thiết kế trong API** và xử lý trường hợp không tìm thấy hoặc trùng định danh; không dùng thứ tự trả về của `ServiceLoader` làm tiêu chí. Kiểm tra bản phân phối chỉ chứa một provider và bản chứa nhiều providers.

**Ghi nhớ:** module API định nghĩa *hợp đồng* bằng `exports`; module implementation đăng ký *cách làm* bằng `provides`; module app tuyên bố *cần service* bằng `uses` và tìm nó qua `ServiceLoader`. `javac --module-source-path` tạo các named modules, `jar` đóng gói descriptors và `java --module-path --module` khởi chạy theo module graph. Muốn thay implementation độc lập, phải thiết kế cả **module boundary** và **runtime distribution** cho đúng.

## Tài liệu tham khảo chính thức còn áp dụng

- [Java SE 25 — ServiceLoader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceLoader.html): `uses`, `provides`, module providers, discovery và cách nạp service.
- [Java SE 25 — ModuleDescriptor](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/module/ModuleDescriptor.html): module directives và descriptor.
- [Java SE 25 — javac](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): `--module-source-path`, `--module`, `--release`, `-d`.
- [Java SE 25 — java launcher](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `--module-path`, `--module`, `--show-module-resolution`.
- [Java SE 25 — jar](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jar.html): modular JAR, `--main-class`, `--describe-module`.
- [Dev.java — Creating Runtime and Application Images with jlink](https://dev.java/learn/jlink/): service binding trong custom runtime image.
- [Java SE 25 — Packaging Overview](https://docs.oracle.com/en/java/javase/25/jpackage/packaging-overview.html): ảnh hưởng của `jpackage` với service binding từ JDK 25.
