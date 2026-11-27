# Đưa strategy vào production khi runtime cần dùng

Một `ApplicationModuleDetectionStrategy` tùy chỉnh chỉ có tác dụng trong môi trường mà Spring Modulith tải được implementation đó. Nếu strategy chỉ nằm trong test source set, bài kiểm tra kiến trúc có thể chạy đúng nhưng ứng dụng triển khai vẫn phát hiện mô-đun theo cấu hình mặc định. Khi runtime cần dùng cùng mô hình mô-đun để xử lý sự kiện, quan sát hoặc cung cấp thông tin kiến trúc, strategy phải có mặt trên runtime classpath của artifact được triển khai.

Bài học này tập trung vào việc đóng gói và đăng ký strategy để môi trường production sử dụng cùng quy tắc phát hiện mô-đun với môi trường phát triển. Ví dụ dùng ứng dụng `com.acme.shop`, có các mô-đun `orders`, `catalog` và `customers`.

## 1. Phân biệt strategy trong test và strategy trong production

`ApplicationModuleDetectionStrategy` quyết định những package nào bên dưới package gốc của ứng dụng được xem là module base package. Spring Modulith dùng kết quả đó để xây dựng mô hình các mô-đun và kiểm tra quan hệ giữa chúng.

Trong một số dự án, quy ước mặc định như mỗi package con trực tiếp là một mô-đun không phù hợp với cấu trúc thực tế. Ví dụ, ứng dụng có thể gom các package nghiệp vụ dưới `com.acme.shop.contexts`, hoặc chỉ một tập package được chọn mới là mô-đun. Khi đó, strategy tùy chỉnh mô tả quy ước phát hiện riêng của ứng dụng.

Vị trí đăng ký quyết định phạm vi sử dụng:

| Vị trí implementation và cấu hình | Môi trường có thể tải strategy |
|---|---|
| `src/test/java` và `src/test/resources` | Chỉ test runtime |
| `src/main/java` và `src/main/resources` | Runtime ứng dụng và test runtime thông thường |
| Một thư viện nằm trên runtime classpath, có đóng gói cấu hình factory | Các ứng dụng sử dụng thư viện đó có thể tải strategy |

Nếu production cần strategy, implementation và tệp đăng ký phải được đóng gói trong artifact hoặc dependency thực sự có trên runtime classpath. Đặt cấu hình trong `src/test/resources` chỉ giúp kiểm tra ở test; cấu hình đó không đi vào JAR ứng dụng thông thường.

## 2. Viết strategy theo quy ước package của ứng dụng

Giả sử package gốc là `com.acme.shop` và chỉ ba package con `orders`, `catalog`, `customers` là mô-đun. Các package như `shared`, `configuration` hoặc package kỹ thuật khác không được xem là mô-đun độc lập.

Tạo implementation trong source set chính:

```java
package com.acme.shop.architecture;

import java.util.Collection;
import java.util.Set;
import java.util.stream.Collectors;

import com.tngtech.archunit.core.domain.JavaPackage;
import org.springframework.modulith.core.ApplicationModuleDetectionStrategy;

public class BusinessPackageDetectionStrategy implements ApplicationModuleDetectionStrategy {

    private static final Set<String> MODULE_NAMES = Set.of(
            "orders",
            "catalog",
            "customers"
    );

    @Override
    public Collection<JavaPackage> getModuleBasePackages(JavaPackage basePackage) {
        String modulePrefix = basePackage.getName() + ".";

        return basePackage.getSubPackages().stream()
                .filter(candidate -> MODULE_NAMES.stream()
                        .anyMatch(name -> candidate.getName().equals(modulePrefix + name)))
                .collect(Collectors.toSet());
    }
}
```

Strategy nhận package gốc do Spring Modulith cung cấp, sau đó chọn đúng các package có tên khớp với danh sách mô-đun. Việc so sánh tên đầy đủ với `modulePrefix` giúp tránh vô tình chọn một package lồng sâu như `com.acme.shop.orders.internal` làm mô-đun độc lập.

Ví dụ này cố ý dùng một allow-list nhỏ để quy tắc dễ kiểm soát. Nếu tổ chức dùng quy ước tên package hoặc cấu trúc nhiều bounded context, có thể thay phần lọc bằng quy tắc tương ứng. Dù chọn cách nào, strategy nên có kết quả xác định từ cấu trúc package và không phụ thuộc vào trạng thái runtime như dữ liệu cơ sở dữ liệu, biến môi trường hoặc dịch vụ mạng.

`ApplicationModuleDetectionStrategy` là cơ chế phát hiện mô-đun của Spring Modulith. Strategy không thay thế `@ApplicationModule`, `@NamedInterface` hay các quy tắc phụ thuộc. Nó xác định các package gốc được nhận diện là mô-đun; các khai báo boundary và API vẫn có vai trò riêng trong mô hình đó.

## 3. Đăng ký bằng `META-INF/spring.factories`

Spring Modulith tải strategy tùy chỉnh thông qua cơ chế Spring factories. Tạo tệp sau trong source set chính:

```text
src/main/resources/META-INF/spring.factories
```

Thêm mapping giữa interface và implementation:

```properties
org.springframework.modulith.core.ApplicationModuleDetectionStrategy=\
com.acme.shop.architecture.BusinessPackageDetectionStrategy
```

Tên bên trái là tên đầy đủ của interface `ApplicationModuleDetectionStrategy`; tên bên phải là implementation của ứng dụng. Khi tệp này nằm trong runtime classpath, Spring Modulith có thể tải strategy đã đăng ký khi xây dựng `ApplicationModules`.

Implementation cần có thể được khởi tạo bởi cơ chế Spring factories. Vì vậy, giữ lớp ở trạng thái `public`, không phải lớp trừu tượng và cung cấp constructor không tham số có thể truy cập. Strategy không được giả định rằng nó là Spring bean: không dựa vào `@Autowired`, constructor injection hoặc `ApplicationContext` để lấy dependency.

Không đăng ký cùng một implementation ở nhiều vị trí với các quy tắc khác nhau. Một ứng dụng nên có một chiến lược phát hiện mô-đun rõ ràng để kết quả không phụ thuộc vào thứ tự classpath hoặc cấu hình của từng môi trường.

## 4. Bảo đảm cấu hình đi vào artifact production

Kiểm tra cấu trúc source trước khi build:

```text
src
├── main
│   ├── java
│   │   └── com/acme/shop/architecture
│   │       └── BusinessPackageDetectionStrategy.java
│   └── resources
│       └── META-INF
│           └── spring.factories
└── test
    └── java
        └── com/acme/shop
            └── ModuleDetectionTests.java
```

Với Spring Boot executable JAR, tài nguyên của ứng dụng thường được đặt dưới `BOOT-INF/classes/`. Với JAR Java thông thường, tài nguyên nằm trực tiếp dưới `META-INF/`. Sau khi build, kiểm tra artifact để xác nhận `spring.factories` đã được đóng gói và nội dung mapping trỏ tới đúng implementation.

Ví dụ kiểm tra một JAR:

```bash
jar tf build/libs/shop-application.jar
```

Trong danh sách kết quả, tìm `META-INF/spring.factories` hoặc `BOOT-INF/classes/META-INF/spring.factories`, tùy loại JAR. Sau đó có thể mở tệp JAR để xác minh nội dung mapping. Nếu strategy được cung cấp từ một thư viện riêng, kiểm tra JAR của thư viện đó và bảo đảm thư viện được khai báo trong runtime dependency của ứng dụng.

Không dựa vào việc test chạy thành công để kết luận artifact production có cấu hình. Test runtime thường nhìn thấy cả tài nguyên của `src/test/resources`; đây chính là lý do một cấu hình đặt nhầm ở test có thể che giấu lỗi đóng gói.

## 5. Kiểm chứng mô hình mô-đun bằng cùng runtime classpath

Tạo bài kiểm tra kiến trúc sử dụng lớp ứng dụng thực tế:

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

import static org.assertj.core.api.Assertions.assertThat;

class ModuleDetectionTests {

    @Test
    void discoversTheExpectedBusinessModules() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        assertThat(modules.getModuleByName("orders")).isPresent();
        assertThat(modules.getModuleByName("catalog")).isPresent();
        assertThat(modules.getModuleByName("customers")).isPresent();

        modules.verify();
    }
}
```

Bài kiểm tra xác nhận các mô-đun dự kiến được phát hiện và các quy tắc kiến trúc có thể được xác minh trên mô hình vừa tạo. Vì implementation và `spring.factories` nằm trong `src/main`, test runtime thông thường sẽ dùng cùng cấu hình được đóng gói cho ứng dụng.

Để kiểm chứng gần với production hơn, chạy ứng dụng từ artifact đã build trong một môi trường kiểm thử triển khai. Quan sát log khởi động và các thành phần runtime có sử dụng mô hình mô-đun; đồng thời xác nhận các mô-đun được phát hiện đúng theo quy ước package. Kiểm tra artifact và kiểm tra runtime bổ sung cho nhau: một bên xác nhận tài nguyên được đóng gói, bên còn lại xác nhận ứng dụng thực sự tải và sử dụng nó.

## 6. Những lỗi thường gặp khi đưa strategy lên production

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Test nhận diện đúng mô-đun nhưng ứng dụng triển khai dùng kết quả khác | `spring.factories` chỉ nằm trong `src/test/resources` | Chuyển implementation và cấu hình cần thiết sang source set chính |
| Không tìm thấy implementation khi khởi chạy | Sai tên lớp, sai key hoặc tài nguyên không có trong runtime classpath | Kiểm tra fully qualified class name và nội dung JAR |
| Strategy được tải nhưng không phát hiện mô-đun mong muốn | Quy tắc lọc package không khớp package gốc thực tế | Kiểm tra package của lớp ứng dụng và các package con được trả về |
| Package `internal` bị coi là mô-đun riêng | Strategy chọn mọi package lồng sâu | Chỉ trả về package gốc theo quy ước, không chọn package triển khai con |
| Mỗi môi trường phát hiện một tập mô-đun khác nhau | Strategy phụ thuộc biến môi trường hoặc dữ liệu runtime | Dùng quy tắc ổn định, được kiểm soát bằng mã nguồn và cấu hình đóng gói |
| Ứng dụng có nhiều strategy cạnh tranh | Nhiều dependency đăng ký cùng factory interface | Hợp nhất quy tắc và giữ một strategy có chủ đích cho ứng dụng |

Nếu strategy nằm trong một thư viện dùng chung, cần cân nhắc rằng cấu hình factories của dependency cũng có thể được phát hiện cùng cấu hình của ứng dụng. Không nên thêm một strategy dùng chung chỉ để thuận tiện nếu mỗi ứng dụng cần quy tắc phát hiện khác nhau. Khi quy tắc là đặc thù của một ứng dụng, giữ implementation và đăng ký ở ứng dụng đó sẽ giúp quyền sở hữu rõ ràng hơn.

## 7. Quy trình triển khai an toàn

Khi chuẩn bị đưa strategy tùy chỉnh vào production, thực hiện lần lượt:

1. Chốt package gốc của ứng dụng và danh sách package nào được xem là mô-đun.
2. Viết strategy có kết quả xác định, chỉ trả về các module base package dự kiến.
3. Đặt implementation trong source set chính và đăng ký bằng `META-INF/spring.factories`.
4. Viết test xác nhận các mô-đun quan trọng được phát hiện, sau đó gọi `verify()` để kiểm tra boundary.
5. Build artifact và kiểm tra tệp `spring.factories` đã xuất hiện trong JAR hoặc dependency runtime.
6. Chạy artifact trong môi trường kiểm thử triển khai để xác nhận runtime sử dụng đúng mô hình mô-đun.
7. Đưa cùng artifact đã kiểm chứng qua các môi trường triển khai để tránh sai khác giữa build được test và build được phát hành.

Strategy phát hiện mô-đun là một phần của cấu hình kiến trúc. Thay đổi quy tắc này có thể làm thay đổi tập mô-đun, các quan hệ phụ thuộc được kiểm tra và cách thành phần runtime hiểu cấu trúc ứng dụng. Vì vậy, hãy xem thay đổi strategy như thay đổi boundary: cần review, kiểm thử và đóng gói cùng ứng dụng.

## 8. Bài tập tự kiểm tra

Với ứng dụng `com.acme.shop`, hãy trả lời các câu hỏi sau:

1. Nếu `BusinessPackageDetectionStrategy` chỉ được đặt trong `src/test/java`, production có tải được implementation đó không? Vì sao?
2. Nếu `spring.factories` nằm trong `src/test/resources`, tại sao test vẫn có thể pass trong khi artifact triển khai thiếu strategy?
3. Vì sao strategy nên chọn `com.acme.shop.orders` thay vì chọn thêm `com.acme.shop.orders.internal`?
4. Nếu strategy phụ thuộc vào một biến môi trường để quyết định package nào là mô-đun, điều gì có thể xảy ra khi chạy cùng artifact ở hai môi trường khác nhau?
5. Ngoài kiểm tra `ApplicationModules.verify()`, cần kiểm tra điều gì trong JAR và khi chạy ứng dụng để xác nhận cấu hình đã tới production?

Một câu trả lời tốt phải chỉ ra được cả ba điểm: implementation nằm trên runtime classpath, factory mapping được đóng gói trong artifact, và mô hình được tạo ở runtime chứa đúng các mô-đun dự kiến. Khi ba điều kiện này được kiểm chứng, strategy tùy chỉnh mới thực sự sẵn sàng cho ứng dụng production.
