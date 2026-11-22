# Service provider interface và consumer

## 1. SPI và consumer là gì?

Trong Java, **Service Provider Interface (SPI)** là một interface hoặc abstract contract mô tả một dịch vụ mà nhiều module có thể cung cấp cách triển khai khác nhau. **Consumer** là module cần sử dụng dịch vụ đó. **Provider** là module cung cấp một implementation cụ thể.

Ba vai trò được tách rời:

- **SPI module** định nghĩa kiểu dịch vụ mà consumer và provider cùng biết.
- **Consumer module** phụ thuộc vào kiểu dịch vụ, yêu cầu dịch vụ bằng `uses`, rồi tìm implementation bằng `ServiceLoader`.
- **Provider module** phụ thuộc vào SPI, triển khai dịch vụ và đăng ký implementation bằng `provides ... with ...`.

Consumer chỉ cần biết contract. Nó không cần biết tên class triển khai hoặc phụ thuộc trực tiếp vào module provider. Nhờ vậy có thể thêm, thay hoặc gỡ provider mà không phải sửa consumer, miễn là contract vẫn tương thích.

Ví dụ dưới đây dùng dịch vụ `GreetingService`: consumer yêu cầu lời chào, còn provider quyết định nội dung lời chào.

## 2. Cấu trúc các module

Ví dụ gồm ba named module:

```text
src/
├── com.acme.greeting.spi/
│   ├── module-info.java
│   └── com/acme/greeting/spi/GreetingService.java
├── com.acme.greeting.provider.en/
│   ├── module-info.java
│   └── com/acme/greeting/provider/en/EnglishGreeting.java
└── com.acme.greeting.consumer/
    ├── module-info.java
    └── com/acme/greeting/consumer/Main.java
```

Luồng phụ thuộc:

```text
com.acme.greeting.consumer
       | requires + uses
       v
com.acme.greeting.spi
       ^
       | requires + provides
com.acme.greeting.provider.en
```

Sơ đồ thể hiện cả hai module đều biết SPI. Consumer không khai báo `requires com.acme.greeting.provider.en`; việc tìm provider được giao cho cơ chế dịch vụ của JPMS và `ServiceLoader`.

## 3. Định nghĩa service contract trong SPI module

Tệp `src/com.acme.greeting.spi/module-info.java`:

```java
module com.acme.greeting.spi {
    exports com.acme.greeting.spi;
}
```

Tệp `src/com.acme.greeting.spi/com/acme/greeting/spi/GreetingService.java`:

```java
package com.acme.greeting.spi;

public interface GreetingService {
    String greet(String name);
}
```

Package chứa interface được `exports` để các module khác có thể tham chiếu kiểu `GreetingService`. Đây là phần contract công khai của hệ thống. SPI module không cần biết có bao nhiêu provider hoặc provider nằm ở đâu.

Một SPI tốt nên mô tả hành vi mà consumer cần, giữ API ổn định và tránh đưa chi tiết triển khai của từng provider vào contract.

## 4. Cài đặt và đăng ký provider

Tệp `src/com.acme.greeting.provider.en/module-info.java`:

```java
module com.acme.greeting.provider.en {
    requires com.acme.greeting.spi;

    provides com.acme.greeting.spi.GreetingService
        with com.acme.greeting.provider.en.EnglishGreeting;
}
```

Tệp `src/com.acme.greeting.provider.en/com/acme/greeting/provider/en/EnglishGreeting.java`:

```java
package com.acme.greeting.provider.en;

import com.acme.greeting.spi.GreetingService;

public final class EnglishGreeting implements GreetingService {
    public EnglishGreeting() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

Hai phần quan trọng trong module descriptor:

- `requires com.acme.greeting.spi` cho phép provider tham chiếu interface mà nó triển khai.
- `provides GreetingService with EnglishGreeting` đăng ký class provider cho service type `GreetingService`.

Với cách khai báo provider bằng class như ví dụ, provider class phải là `public` và có public constructor không tham số. JPMS không bắt buộc package chứa implementation phải được `exports`; consumer không gọi trực tiếp class này. Điều đó giúp provider giữ implementation ở package nội bộ.

Một provider module có thể cung cấp nhiều service type. Một service type cũng có thể có nhiều provider; trong một `provides` directive có thể liệt kê nhiều provider class, phân tách bằng dấu phẩy.

## 5. Khai báo consumer và tìm service

Tệp `src/com.acme.greeting.consumer/module-info.java`:

```java
module com.acme.greeting.consumer {
    requires com.acme.greeting.spi;

    uses com.acme.greeting.spi.GreetingService;
}
```

Consumer cần `requires` SPI để biên dịch và sử dụng interface. Directive `uses` khai báo rằng module này sẽ tìm service type đó ở runtime.

Tệp `src/com.acme.greeting.consumer/com/acme/greeting/consumer/Main.java`:

```java
package com.acme.greeting.consumer;

import com.acme.greeting.spi.GreetingService;

import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        String name = args.length > 0 ? args[0] : "Java";

        ServiceLoader<GreetingService> services =
                ServiceLoader.load(GreetingService.class);

        boolean found = false;
        for (GreetingService service : services) {
            found = true;
            System.out.println(service.greet(name));
        }

        if (!found) {
            System.out.println("No GreetingService provider was found.");
        }
    }
}
```

`ServiceLoader.load(GreetingService.class)` trả về một `ServiceLoader` có thể duyệt qua các implementation tìm được. Việc nạp và khởi tạo provider diễn ra khi duyệt, vì vậy có thể xử lý nhiều provider mà không cần liệt kê class cụ thể trong consumer.

Kết quả với provider tiếng Anh:

```text
Hello, Java!
```

Consumer không import `EnglishGreeting`, không gọi constructor của nó và không cần biết module provider có tên gì. Nó chỉ làm việc với `GreetingService`.

## 6. Biên dịch và chạy ví dụ

Đứng tại thư mục chứa thư mục `src`, chạy:

```bash
javac --module-source-path src -d out \
  -m com.acme.greeting.spi,com.acme.greeting.provider.en,com.acme.greeting.consumer
```

Sau khi biên dịch, chạy main class của consumer:

```bash
java --module-path out \
  -m com.acme.greeting.consumer/com.acme.greeting.consumer.Main
```

Có thể truyền tên làm đối số:

```bash
java --module-path out \
  -m com.acme.greeting.consumer/com.acme.greeting.consumer.Main "Ada"
```

Khi chạy trên module path, cơ chế service binding của JPMS có thể đưa module provider phù hợp vào module graph dựa trên các service mà module đã resolve khai báo `uses`. Đây là lý do consumer không cần khai báo `requires` tới từng provider. Có thể thêm `--show-module-resolution` vào lệnh `java` để quan sát quá trình resolve module khi cần tìm lỗi.

## 7. ServiceLoader hoạt động như thế nào?

Ở mức sử dụng thông thường, quy trình gồm các bước:

1. Consumer khai báo `uses` cho service type trong `module-info.java`.
2. Provider module khai báo `provides` và class triển khai tương ứng.
3. Module system tìm các provider phù hợp trong module graph; với named module, service binding tham gia vào quá trình resolve.
4. Consumer gọi `ServiceLoader.load(ServiceType.class)`.
5. Khi duyệt kết quả, `ServiceLoader` nạp và tạo các provider rồi trả về dưới kiểu service interface.

Một số điểm cần nhớ:

- Nếu không tìm thấy provider, vòng lặp không chạy lần nào. Hãy quyết định rõ consumer sẽ báo lỗi, dùng giá trị mặc định hay bỏ qua dịch vụ.
- Có thể có nhiều provider. Không nên dựa vào thứ tự duyệt để quyết định provider nào có độ ưu tiên cao nhất; nếu cần lựa chọn, hãy dùng cấu hình hoặc một quy tắc lựa chọn rõ ràng.
- Quá trình nạp provider có thể phát sinh `ServiceConfigurationError` nếu khai báo hoặc provider không hợp lệ. Ứng dụng có thể bắt lỗi này ở ranh giới phù hợp để ghi log hoặc báo lỗi cấu hình.
- `ServiceLoader` lưu cache các provider đã nạp trong instance của nó. Gọi `reload()` sẽ xóa cache để lần duyệt sau nạp lại provider.
- Nếu ứng dụng tự tạo `ModuleLayer`, có thể dùng `ServiceLoader.load(layer, GreetingService.class)` để tìm provider trong layer được chỉ định.

## 8. Named module và classpath

Với named module trên module path, đăng ký service nằm trong `module-info.java` bằng `uses` và `provides`.

Với ứng dụng chạy trên classpath hoặc thư viện theo cơ chế classpath truyền thống, provider thường được đăng ký bằng tệp:

```text
META-INF/services/com.acme.greeting.spi.GreetingService
```

Tệp này chứa tên đầy đủ của từng provider class, mỗi tên trên một dòng, ví dụ:

```text
com.acme.greeting.provider.en.EnglishGreeting
```

Đây là hai cơ chế đăng ký khác nhau. Khi làm việc với named module, hãy khai báo service trong module descriptor; khi làm việc với classpath, kiểm tra tệp `META-INF/services` có nằm trong artifact được đóng gói hay không.

## 9. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Consumer không biên dịch được khi tham chiếu service type | SPI module chưa `exports` package chứa interface hoặc consumer chưa `requires` SPI |
| Consumer báo module không khai báo sử dụng service | Thiếu directive `uses` trong `module-info.java` của consumer |
| Provider không được tìm thấy | Thiếu `provides ... with ...`, sai service type/provider class, provider module không có trên module path hoặc không được resolve |
| Provider không thể được khởi tạo | Class provider không public, thiếu public constructor không tham số, hoặc constructor ném lỗi |
| Provider không triển khai đúng contract | Class provider không assignable với service type hoặc chữ ký method không khớp |
| Consumer phải sửa mỗi khi thêm provider | Consumer đang phụ thuộc trực tiếp vào implementation thay vì chỉ phụ thuộc vào SPI |

Khi debug, kiểm tra đồng thời ba nơi: service interface có được export đúng không, consumer có khai báo `uses` không, và provider có khai báo `provides` đúng service type cùng implementation không.

## 10. Khi nào nên dùng mô hình SPI?

SPI phù hợp khi một ứng dụng cần cho phép nhiều implementation cùng tuân theo một contract, chẳng hạn:

- Nhiều database driver cùng cung cấp một interface truy cập dữ liệu.
- Nhiều định dạng parser cùng triển khai một interface đọc dữ liệu.
- Nhiều thuật toán mã hóa, bộ chuyển đổi hoặc plugin có thể được bổ sung độc lập.
- Ứng dụng lõi cần mở rộng bằng module do nhóm khác hoặc bên thứ ba phát triển.

Nếu ứng dụng chỉ có một implementation cố định và không cần cơ chế mở rộng, gọi trực tiếp implementation có thể đơn giản hơn. SPI hữu ích khi việc tách contract khỏi implementation đem lại khả năng thay thế, mở rộng hoặc triển khai provider độc lập.

## Ghi nhớ

- **SPI** định nghĩa contract chung.
- **Consumer** khai báo `requires` SPI và `uses` service type.
- **Provider** khai báo `requires` SPI và `provides` implementation.
- **ServiceLoader** tìm và nạp provider theo service type; consumer không cần phụ thuộc trực tiếp vào provider module.
- Trên JPMS, package chứa service interface cần được export; package implementation có thể được giữ kín.
