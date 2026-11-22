# Giữ mô-đun triển khai độc lập với mã sử dụng dịch vụ

Java Platform Module System (JPMS) hỗ trợ kiến trúc dịch vụ thông qua hai directive trong `module-info.java`: `uses` và `provides`. Kết hợp với `ServiceLoader`, các directive này cho phép mô-đun ứng dụng phụ thuộc vào một hợp đồng dịch vụ ổn định, trong khi các mô-đun triển khai có thể được thêm, thay thế hoặc gỡ bỏ độc lập.

Ý tưởng cốt lõi là tách ba vai trò:

- **Service API** định nghĩa interface hoặc abstract class mà các bên cùng hiểu.
- **Consumer module** sử dụng dịch vụ thông qua Service API và khai báo `uses`.
- **Provider module** triển khai dịch vụ, phụ thuộc vào Service API và khai báo `provides ... with ...`.

Consumer không cần `requires` mô-đun provider và không import lớp triển khai. Khi chạy, JPMS có thể liên kết provider quan sát được vào module graph thông qua service binding.

## 1. Kiến trúc và chiều phụ thuộc

Ví dụ một ứng dụng cần định dạng thông điệp. Hợp đồng `MessageFormatter` nằm trong mô-đun API. Ứng dụng gọi `ServiceLoader` để tìm formatter. Mô-đun triển khai cung cấp `UppercaseFormatter`.

```text
com.example.app
    | requires + uses
    v
com.example.message.api
    ^
    | requires + provides
com.example.message.provider.upper
```

Các quan hệ cần giữ:

1. Consumer đọc Service API vì nó gọi các kiểu được định nghĩa trong API.
2. Provider đọc cùng Service API vì lớp triển khai phải thực hiện hợp đồng.
3. Consumer khai báo `uses` cho service type.
4. Provider khai báo `provides` và liệt kê implementation class.
5. Consumer không khai báo `requires` tới provider; provider cũng không cần biết mô-đun consumer.

Nhờ vậy, có thể thay `com.example.message.provider.upper` bằng một provider khác mà không phải sửa mã nguồn hoặc `module-info.java` của ứng dụng, miễn provider mới thực hiện cùng hợp đồng dịch vụ.

## 2. `uses` và `provides` trong JPMS

### `uses` — khai báo nhu cầu dịch vụ

Consumer module khai báo service type mà nó muốn tìm:

```java
module com.example.app {
    requires com.example.message.api;
    uses com.example.message.api.MessageFormatter;
}
```

`uses` không tạo dependency trực tiếp tới một implementation cụ thể. Nó khai báo một service dependence để module system biết rằng mô-đun này cần các provider của service type đó.

Với named module, khai báo `uses` là cần thiết khi gọi `ServiceLoader.load(...)` cho service type. Thiếu khai báo này có thể khiến `ServiceLoader` ném `ServiceConfigurationError` vì caller module chưa khai báo sử dụng dịch vụ.

### `provides ... with ...` — đăng ký implementation

Provider module khai báo lớp triển khai:

```java
module com.example.message.provider.upper {
    requires com.example.message.api;
    provides com.example.message.api.MessageFormatter
            with com.example.message.provider.upper.UppercaseFormatter;
}
```

`provides` ghi rõ service type và một hoặc nhiều provider class. Provider module phải đọc mô-đun chứa service type. Lớp provider trong ví dụ là lớp `public`, triển khai interface dịch vụ và có public no-argument constructor mặc định.

Package chứa provider class không cần export cho consumer chỉ để `ServiceLoader` tạo provider. Điều này giúp implementation tiếp tục được đóng gói bên trong provider module.

## 3. ServiceLoader tìm provider như thế nào?

`ServiceLoader` thuộc `java.util` trong `java.base`. Consumer tải các implementation thông qua service type:

```java
ServiceLoader<MessageFormatter> loader =
        ServiceLoader.load(MessageFormatter.class);

for (MessageFormatter formatter : loader) {
    // Sử dụng hợp đồng, không cần biết lớp triển khai cụ thể.
}
```

Với named module, quá trình hoạt động gồm các bước:

1. Ứng dụng được khởi chạy và module graph được resolve.
2. Consumer module khai báo `uses MessageFormatter`.
3. JPMS tìm các provider module quan sát được có `provides MessageFormatter with ...`.
4. Service binding đưa provider phù hợp vào module graph khi resolve.
5. `ServiceLoader` phát hiện và khởi tạo provider khi consumer duyệt kết quả.

Việc duyệt `ServiceLoader` có tính lazy: provider được phát hiện và khởi tạo khi kết quả được sử dụng. Có thể có nhiều provider cùng cung cấp một service; consumer nên xử lý từng kết quả thay vì phụ thuộc vào một implementation cụ thể.

Nếu không có provider phù hợp, vòng lặp không có phần tử. Ứng dụng có thể dùng fallback hoặc thông báo rằng dịch vụ chưa được cấu hình.

## 4. Ví dụ hoàn chỉnh với ba mô-đun

Ví dụ dưới đây dùng ba mô-đun độc lập. Consumer chỉ biết interface `MessageFormatter`; provider có thể thay thế mà không cần chỉnh mã consumer.

### Cấu trúc thư mục

```text
src/
├── com.example.message.api/
│   ├── module-info.java
│   └── com/example/message/api/MessageFormatter.java
├── com.example.message.provider.upper/
│   ├── module-info.java
│   └── com/example/message/provider/upper/UppercaseFormatter.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
```

### Mô-đun Service API

`src/com.example.message.api/module-info.java`:

```java
module com.example.message.api {
    exports com.example.message.api;
}
```

Package API được export vì cả consumer và provider cần truy cập service type.

`src/com.example.message.api/com/example/message/api/MessageFormatter.java`:

```java
package com.example.message.api;

public interface MessageFormatter {
    String format(String message);
}
```

Interface là hợp đồng chung. Nó không tham chiếu tới bất kỳ provider class nào.

### Mô-đun provider

`src/com.example.message.provider.upper/module-info.java`:

```java
module com.example.message.provider.upper {
    requires com.example.message.api;
    provides com.example.message.api.MessageFormatter
            with com.example.message.provider.upper.UppercaseFormatter;
}
```

`src/com.example.message.provider.upper/com/example/message/provider/upper/UppercaseFormatter.java`:

```java
package com.example.message.provider.upper;

import com.example.message.api.MessageFormatter;
import java.util.Locale;

public final class UppercaseFormatter implements MessageFormatter {
    public String format(String message) {
        return "UPPER: " + message.toUpperCase(Locale.ROOT);
    }
}
```

Provider class không được export từ `module-info.java`. Consumer không cần import hoặc biết tên lớp này.

### Mô-đun consumer

`src/com.example.app/module-info.java`:

```java
module com.example.app {
    requires com.example.message.api;
    uses com.example.message.api.MessageFormatter;
}
```

Chú ý descriptor không có `requires com.example.message.provider.upper`.

`src/com.example.app/com/example/app/Main.java`:

```java
package com.example.app;

import com.example.message.api.MessageFormatter;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        int count = 0;
        for (MessageFormatter formatter : ServiceLoader.load(MessageFormatter.class)) {
            count++;
            System.out.println(formatter.format("Java modules"));
        }
        if (count == 0) {
            System.out.println("No provider found");
        }
    }
}
```

Mã consumer chỉ import `MessageFormatter` và `ServiceLoader`. Nó không chứa tên `UppercaseFormatter` và không gọi constructor của implementation.

## 5. Biên dịch và chạy

Chạy từ thư mục gốc chứa `src/` bằng JDK 9 trở lên. Tạo thư mục output:

```bash
mkdir -p out
```

Biên dịch cả ba mô-đun:

```bash
javac --module-source-path src -d out -m com.example.message.api,com.example.message.provider.upper,com.example.app
```

`--module-source-path src` xác định nơi chứa các cây mã nguồn mô-đun; `-m` chọn các mô-đun cần biên dịch. Sau khi biên dịch, `out` chứa ba thư mục mô-đun đã giải nén.

Chạy consumer trên module path:

```bash
java --module-path out --module com.example.app/com.example.app.Main
```

Kết quả chính xác:

```text
UPPER: JAVA MODULES
```

Ứng dụng tìm thấy provider và gọi nó qua interface. Không có dependency biên dịch trực tiếp từ `com.example.app` tới `com.example.message.provider.upper`.

### Quan sát service binding

Thêm `--show-module-resolution` để xem module graph khi khởi chạy:

```bash
java --show-module-resolution --module-path out --module com.example.app/com.example.app.Main
```

Trong phần đầu của kết quả sẽ có các dòng tương tự:

```text
root com.example.app ...
com.example.app requires com.example.message.api ...
com.example.app binds com.example.message.provider.upper ...
com.example.message.provider.upper requires com.example.message.api ...
```

Các đường dẫn và những dòng `binds` khác phụ thuộc JDK. Dòng `com.example.app binds com.example.message.provider.upper` cho thấy provider được đưa vào module graph nhờ service binding.

### Kiểm tra descriptor của consumer và provider

```bash
java --module-path out --describe-module com.example.app
java --module-path out --describe-module com.example.message.provider.upper
```

Descriptor consumer có `requires com.example.message.api` và `uses com.example.message.api.MessageFormatter`. Descriptor provider có `requires com.example.message.api` và `provides ... with ...`. Provider package được hiển thị là package chứa trong mô-đun; nó không có directive `exports`.

## 6. Thay hoặc gỡ provider mà không sửa consumer

Có thể thay mô-đun `com.example.message.provider.upper` bằng một provider khác, ví dụ provider định dạng chữ thường. Provider mới:

- Đọc `com.example.message.api`.
- Cung cấp cùng service type `MessageFormatter` bằng `provides`.
- Được đặt trên module path lúc chạy.

Consumer vẫn biên dịch và chạy với cùng `module-info.java` và cùng mã `Main`. Nếu module path chỉ chứa consumer và Service API mà không có provider, ứng dụng vẫn khởi chạy và in:

```text
No provider found
```

Điều này cho thấy provider là thành phần triển khai có thể thay đổi độc lập. Consumer quyết định cách xử lý khi dịch vụ không được cài đặt.

## 7. Những lỗi thường gặp

| Lỗi hoặc biểu hiện | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `ServiceConfigurationError` báo consumer không khai báo `uses` | Named module gọi `ServiceLoader` nhưng thiếu service dependence | Thêm `uses` đúng service type vào `module-info.java` của consumer |
| Không tìm thấy provider | Provider module không nằm trên module path hoặc không khai báo `provides` đúng service type | Kiểm tra module path và descriptor bằng `--describe-module` |
| Provider không biên dịch | Provider module chưa `requires` mô-đun Service API hoặc implementation không thực hiện đúng interface | Thêm dependency API và sửa chữ ký implementation |
| Consumer không biên dịch khi import service type | Consumer chưa `requires` mô-đun API hoặc package API chưa export | Kiểm tra `requires` và `exports` |
| Consumer phải import implementation class | Thiết kế đã làm lộ chi tiết provider vào consumer | Chuyển kiểu phụ thuộc sang Service API và dùng `ServiceLoader` |
| Provider class không thể được tạo | Provider không đáp ứng quy tắc provider class, ví dụ thiếu public no-argument constructor trong kiểu provider class thông thường | Cung cấp constructor phù hợp hoặc dùng provider method theo ServiceLoader API |
| Provider được tìm thấy nhưng khởi tạo thất bại | Lỗi trong constructor/provider method hoặc dependency lúc chạy | Đọc nguyên nhân gốc của `ServiceConfigurationError` và kiểm tra dependency provider |

## 8. Nguyên tắc thiết kế dịch vụ

1. **Thiết kế Service API trước.** Đặt interface và kiểu trao đổi dữ liệu trong mô-đun API nhỏ, ổn định; tránh để API tham chiếu ngược tới provider.
2. **Consumer chỉ phụ thuộc vào hợp đồng.** Dùng `requires` cho mô-đun API và `uses` cho service type; không thêm `requires` tới implementation.
3. **Provider chỉ phụ thuộc vào hợp đồng.** Provider dùng `requires` tới API và đăng ký bằng `provides`.
4. **Giữ package triển khai đóng.** Không export package provider nếu consumer không cần truy cập trực tiếp implementation.
5. **Đưa provider vào module path lúc triển khai.** Service binding chỉ có thể chọn provider mà module system quan sát được và có thể resolve.
6. **Xử lý trường hợp không có provider.** Dùng fallback, cấu hình bắt buộc hoặc thông báo lỗi phù hợp với yêu cầu nghiệp vụ.
7. **Không ép thứ tự provider.** Nếu ứng dụng cần chọn một implementation cụ thể, hãy thiết kế thuộc tính/metadata hoặc quy tắc lựa chọn rõ ràng thay vì dựa vào thứ tự phát hiện.
8. **Giữ hợp đồng tương thích.** Khi thay provider, implementation mới phải tiếp tục đáp ứng service API mà consumer sử dụng.

## 9. Ghi nhớ

- `uses` khai báo consumer cần một service type.
- `provides ... with ...` đăng ký implementation trong provider module.
- `ServiceLoader.load(ServiceType.class)` tìm provider qua service contract.
- Consumer cần đọc Service API nhưng không cần đọc provider module.
- Provider cần đọc Service API nhưng không cần biết consumer module.
- JPMS service binding có thể resolve provider quan sát được vào module graph lúc khởi chạy.
- Provider package có thể giữ kín; consumer chỉ làm việc với interface công khai.

## Tài liệu tham khảo

- [Java SE 24 API — `ServiceLoader`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/ServiceLoader.html)
- [Java Language Specification — Service Dependences, §7.7.4](https://docs.oracle.com/en/java/javase/24/docs/specs/jls/jls-7.html#jls-7.7.4)
- [Java Launcher — Module path and module resolution options](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html)
- [JEP 261 — Module System](https://openjdk.org/jeps/261)