# `spring.modulith.runtime.verification-enabled`

`spring.modulith.runtime.verification-enabled` là thuộc tính Boolean điều khiển việc Spring Modulith kiểm tra application module arrangement khi ứng dụng Spring Boot khởi động. Khi thuộc tính có giá trị `true` và `spring-modulith-runtime` có mặt trên runtime classpath, Spring Boot auto-configuration đăng ký `RuntimeApplicationModuleVerifier`. Verifier kiểm tra module model; nếu phát hiện vi phạm kiến trúc, startup bị abort.

Thuộc tính này có giá trị mặc định là `false`. Vì vậy, chỉ thêm runtime artifact không tự động bật kiểm tra. Nhóm cần chủ động cấu hình property ở môi trường muốn áp dụng.

## 1. Ý nghĩa chính xác của property

Property có tên đầy đủ:

```text
spring.modulith.runtime.verification-enabled
```

Đây là cờ bật/tắt runtime module verification:

| Giá trị | Hành vi |
| --- | --- |
| `true` | Nếu `spring-modulith-runtime` có trên runtime classpath, runtime verifier được đăng ký để kiểm tra module arrangement khi startup |
| `false` | Runtime verifier không được đăng ký; ứng dụng vẫn có thể dùng các runtime support khác của Spring Modulith |
| Không khai báo | Dùng mặc định `false` |

Property chỉ điều khiển runtime verifier. Nó không bật module detection strategy, không tạo module, không sửa dependency graph và không tự chạy `ApplicationModules.verify()` trong JUnit. Nó quyết định có thực hiện bước kiểm tra module arrangement trong lần khởi động ứng dụng hay không.

## 2. Giá trị mặc định là `false`

Spring Modulith 2.2.0 công bố property trong bảng configuration properties với default value là `false`. Auto-configuration cũng dùng điều kiện Boolean với `matchIfMissing = false`, nghĩa là verifier chỉ được tạo khi property được đặt rõ ràng thành `true`.

Điều này giúp dự án lựa chọn thời điểm đưa runtime verification vào vận hành. Một codebase có thể đã dùng `ApplicationModules.verify()` trong architecture test nhưng chưa bật kiểm tra ở startup. Khi đó, CI vẫn kiểm tra kiến trúc theo test, còn ứng dụng runtime chưa có startup guard.

Không nên suy ra rằng property đang bật chỉ vì dependency runtime tồn tại. Hãy kiểm tra cả hai điều kiện: artifact có trên runtime classpath và property có effective value là `true`.

## 3. Điều kiện cần: runtime artifact phải có trên classpath

Property không tự cài đặt runtime support. Với Gradle, có thể thêm dependency:

```kotlin
dependencies {
    runtimeOnly("org.springframework.modulith:spring-modulith-runtime")
}
```

Với Maven:

```xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-runtime</artifactId>
    <scope>runtime</scope>
</dependency>
```

Nếu ứng dụng đã dùng `spring-modulith-starter-core`, starter này kéo `spring-modulith-runtime` vào runtime dependency graph. Hãy kiểm tra dependency graph trước khi khai báo trực tiếp để tránh thêm dependency không cần thiết.

Phạm vi `runtime` là phù hợp khi ứng dụng chỉ cần runtime support. Nếu artifact chỉ có trong test scope, property trong production configuration không thể kích hoạt auto-configuration ở production vì lớp runtime support không có trong classpath được triển khai.

## 4. Bật property bằng YAML

Trong `application.yml`:

```yaml
spring:
  modulith:
    runtime:
      verification-enabled: true
```

Cấu trúc lồng nhau tương ứng với key đầy đủ:

```text
spring.modulith.runtime.verification-enabled=true
```

Nếu muốn tắt rõ ràng:

```yaml
spring:
  modulith:
    runtime:
      verification-enabled: false
```

Khi không có cấu hình, Spring Modulith dùng `false`. Việc ghi rõ `false` có thể hữu ích trong profile cần thể hiện chủ ý, nhưng không bắt buộc nếu nhóm chấp nhận default.

## 5. Bật bằng `application.properties`

Nếu dự án dùng properties file, khai báo một dòng:

```properties
spring.modulith.runtime.verification-enabled=true
```

Để tắt:

```properties
spring.modulith.runtime.verification-enabled=false
```

Không dùng tên rút gọn hoặc tự đặt alias. Property canonical dạng kebab-case giúp cấu hình nhất quán giữa YAML, properties, command line và environment variable.

## 6. Bật theo profile môi trường

Một lựa chọn thường gặp là cấu hình khác nhau giữa local development và môi trường triển khai. Ví dụ, `application.yml` giữ default tắt:

```yaml
spring:
  modulith:
    runtime:
      verification-enabled: false
```

Trong `application-staging.yml`:

```yaml
spring:
  modulith:
    runtime:
      verification-enabled: true
```

Trong `application-production.yml`:

```yaml
spring:
  modulith:
    runtime:
      verification-enabled: true
```

Khi profile `staging` hoặc `production` được kích hoạt, cấu hình profile-specific có thể ghi đè giá trị từ file cấu hình chung theo quy tắc externalized configuration của Spring Boot.

Nếu dùng một file YAML nhiều document, có thể gắn profile bằng `spring.config.activate.on-profile`:

```yaml
spring:
  modulith:
    runtime:
      verification-enabled: false
---
spring:
  config:
    activate:
      on-profile: staging
  modulith:
    runtime:
      verification-enabled: true
```

Hãy xác nhận profile thực sự được kích hoạt trong môi trường triển khai. Một file `application-production.yml` tồn tại không có nghĩa Spring Boot tự động nạp file đó khi profile `production` chưa active.

## 7. Ghi đè bằng command-line argument

Spring Boot cho phép truyền property trực tiếp khi chạy ứng dụng:

```bash
java -jar shop.jar --spring.modulith.runtime.verification-enabled=true
```

Để tắt trong một lần chạy:

```bash
java -jar shop.jar --spring.modulith.runtime.verification-enabled=false
```

Command-line property có độ ưu tiên cao hơn property lấy từ file cấu hình. Vì vậy, nếu file YAML đặt `true` nhưng lệnh khởi động truyền `false`, effective value sẽ là `false`.

Điều này hữu ích khi chẩn đoán cấu hình nhưng cũng có thể gây bất ngờ trong deployment script. Hãy kiểm tra command line của process và các tham số do container/orchestrator truyền vào khi property không có hành vi như dự kiến.

## 8. Dùng environment variable

Spring Boot hỗ trợ relaxed binding từ environment variable. Để chuyển canonical property sang tên biến môi trường:

1. Thay dấu chấm `.` bằng dấu gạch dưới `_`.
2. Bỏ dấu gạch ngang `-`.
3. Chuyển toàn bộ thành chữ hoa.

Vì vậy:

```text
spring.modulith.runtime.verification-enabled
```

được ánh xạ thành:

```text
SPRING_MODULITH_RUNTIME_VERIFICATIONENABLED=true
```

Lưu ý: dấu gạch ngang giữa `verification` và `enabled` bị loại bỏ; không thay nó bằng một dấu gạch dưới khác. Tên `SPRING_MODULITH_RUNTIME_VERIFICATION_ENABLED` không tuân theo quy tắc chuyển đổi canonical được Spring Boot mô tả.

Environment variable phù hợp với container và nền tảng deployment nơi cấu hình được truyền qua environment. Hãy kiểm tra đúng tên biến và giá trị Boolean (`true` hoặc `false`) nếu verifier không được kích hoạt.

## 9. Property kích hoạt verifier trong startup như thế nào?

Khi `spring-modulith-runtime` có mặt, Spring Boot auto-configuration đăng ký các runtime components của Spring Modulith. `RuntimeApplicationModuleVerifier` chỉ được đăng ký khi property có giá trị `true`.

Luồng tổng quát:

```text
Ứng dụng bắt đầu startup
        |
        v
Spring Boot nạp Environment
        |
        v
Kiểm tra spring.modulith.runtime.verification-enabled
        |
        +---- false / missing ----> Không đăng ký runtime verifier
        |
        +---- true ---------------> Đăng ký RuntimeApplicationModuleVerifier
                                      |
                                      v
                              Tạo application module model
                                      |
                                      v
                              Kiểm tra module arrangement
                                      |
                         +------------+------------+
                         |                         |
                     Violation                 Hợp lệ
                         |                         |
                         v                         v
                  Abort startup              Tiếp tục startup
```

Verifier kiểm tra module arrangement và làm ứng dụng khởi động thất bại nếu phát hiện architectural violation. Đây là startup guard, không phải cơ chế theo dõi liên tục sau khi ứng dụng đã chạy.

## 10. Property này không thay thế architecture test

Architecture test thường gọi `ApplicationModules.verify()` trong JUnit. Runtime property kích hoạt kiểm tra ở lần khởi động ứng dụng. Hai cơ chế có thời điểm và mục đích khác nhau:

| Cơ chế | Khi chạy | Cách kích hoạt |
| --- | --- | --- |
| Architecture test | Local hoặc CI khi chạy test | Test gọi `ApplicationModules.verify()` |
| Runtime verification | Khi ứng dụng khởi động | Có runtime artifact và property bằng `true` |

Nên giữ architecture test trong CI để developer phát hiện vi phạm trước khi đóng gói. Runtime verification bổ sung một lớp bảo vệ cho artifact thực sự được khởi động trong môi trường triển khai.

Property không làm test tự động chạy và cũng không thay thế các assertion riêng của architecture test, ví dụ kiểm tra tập module dự kiến khi dùng explicit/custom detection strategy.

## 11. Phân biệt với các property runtime khác

Spring Modulith có những property cùng prefix `spring.modulith.runtime`, nhưng chúng điều khiển tính năng khác nhau:

| Property | Vai trò |
| --- | --- |
| `spring.modulith.runtime.verification-enabled` | Kiểm tra application module arrangement khi startup |
| `spring.modulith.runtime.flyway-enabled` | Bật tùy chỉnh Flyway để thực thi migration theo module và dependency order |

Bật `verification-enabled` không tự bật module-specific Flyway migration. Bật `flyway-enabled` cũng không tự bật runtime module verification. Nếu ứng dụng cần cả hai tính năng, hãy cấu hình từng property theo mục đích.

Property này cũng không thay thế `spring.modulith.detection-strategy`. Detection strategy quyết định package nào được nhận diện thành module; verification-enabled quyết định có kiểm tra arrangement đã phát hiện trong startup hay không.

## 12. Đồng bộ custom detection strategy giữa test và runtime

Nếu ứng dụng dùng `ApplicationModuleDetectionStrategy` tùy chỉnh, class strategy và marker liên quan phải có trong production sources để runtime support sử dụng được. Nếu strategy chỉ nằm trong `src/test/java`, architecture test có thể phát hiện module theo một cách nhưng runtime verifier lại không có cùng cấu hình.

Ví dụ property chọn custom strategy:

```properties
spring.modulith.detection-strategy=com.acme.shop.architecture.BusinessModuleDetectionStrategy
spring.modulith.runtime.verification-enabled=true
```

Hai property có nhiệm vụ riêng:

- `detection-strategy` chọn cách xây dựng module arrangement.
- `runtime.verification-enabled` yêu cầu xác minh arrangement đó khi startup.

Hãy đặt custom strategy và package annotation trong production source set, đồng thời duy trì completeness test để xác nhận module roots được phát hiện đúng như dự kiến.

## 13. Kiểm tra effective value khi cấu hình không có tác dụng

Nếu runtime verifier không chạy, hãy kiểm tra giá trị property mà Spring Environment thực sự nhìn thấy. Có thể đọc trực tiếp trong một bean chẩn đoán:

```java
package com.acme.shop.diagnostics;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
class ModulithConfigurationDiagnostics {

    private static final Logger log =
            LoggerFactory.getLogger(ModulithConfigurationDiagnostics.class);

    @Bean
    ApplicationRunner logRuntimeVerificationSetting(Environment environment) {
        return args -> {
            boolean enabled = environment.getProperty(
                    "spring.modulith.runtime.verification-enabled",
                    Boolean.class,
                    false
            );

            log.info("Spring Modulith runtime verification enabled: {}", enabled);
        };
    }
}
```

Đoạn code trên ghi lại effective value sau khi Spring Environment đã được tạo. Vì `ApplicationRunner` chỉ chạy khi ứng dụng đã đi qua các bước startup trước đó, nếu runtime verifier abort startup thì runner có thể không được gọi. Khi đó, kiểm tra nguồn cấu hình, profile, environment variable, command line hoặc Spring Boot condition report.

Trong môi trường có Actuator, endpoint `env` và `conditions` có thể hỗ trợ chẩn đoán property source và auto-configuration condition. Chỉ expose các endpoint cần thiết và bảo vệ chúng theo chính sách vận hành; không công khai toàn bộ environment ra bên ngoài.

## 14. Các nguyên nhân phổ biến khiến verifier không được kích hoạt

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Đã đặt `true` nhưng không có runtime verification | Thiếu `spring-modulith-runtime` trên runtime classpath | Kiểm tra dependency graph của artifact được đóng gói |
| Có runtime artifact nhưng verifier không được đăng ký | Property không có hoặc effective value là `false` | Kiểm tra default, YAML nesting, profile và property source ghi đè |
| Local chạy nhưng staging không chạy | Profile hoặc environment variable khác nhau | Kiểm tra profile active và tên environment variable |
| YAML nhìn đúng nhưng property không được bind | Sai cấp thụt lề hoặc key viết sai | Đối chiếu với `spring.modulith.runtime.verification-enabled` |
| Biến môi trường không có tác dụng | Dùng dấu gạch dưới thay cho dấu gạch ngang trong tên biến | Dùng `SPRING_MODULITH_RUNTIME_VERIFICATIONENABLED` |
| Architecture test pass nhưng startup fail | Runtime và test phát hiện module model khác nhau hoặc artifact runtime có cấu hình khác | Đồng bộ detection strategy, production sources và configuration |
| Startup fail sau khi bật property | Module arrangement có architectural violation | Đọc diagnostic để sửa dependency, package boundary hoặc allowlist |

## 15. Những nhầm lẫn thường gặp

| Nhận định | Cách hiểu chính xác |
| --- | --- |
| Property mặc định là `true` | Default trong Spring Modulith 2.2.0 là `false` |
| Thêm runtime artifact là đủ | Cần thêm property bằng `true` để đăng ký verifier |
| Property tạo module model | Module detection tạo arrangement; property chỉ bật bước verification lúc startup |
| Property bật `ApplicationModules.verify()` trong mọi test | Nó điều khiển runtime verifier, không điều khiển JUnit architecture test |
| `verification-enabled` và `flyway-enabled` là một | Một property kiểm tra module arrangement, property kia tùy chỉnh Flyway migration |
| Property chỉ tạo warning | Violation khiến runtime verifier abort startup |
| Biến môi trường là `SPRING_MODULITH_RUNTIME_VERIFICATION_ENABLED` | Spring Boot bỏ dấu gạch ngang khi chuyển canonical property thành environment variable |
| Tắt runtime verification đồng nghĩa module không còn được kiểm tra | Architecture test vẫn có thể gọi `ApplicationModules.verify()` độc lập |

## 16. Ghi nhớ

`spring.modulith.runtime.verification-enabled` là Boolean property bật runtime module verification. Giá trị mặc định là `false`. Để verifier hoạt động, ứng dụng cần có `spring-modulith-runtime` trên runtime classpath và cấu hình property thành `true` bằng YAML, properties, profile, command line hoặc environment variable. Khi bật, Spring Boot auto-configuration đăng ký `RuntimeApplicationModuleVerifier`; nếu module arrangement có violation, startup bị abort.

Property này chỉ điều khiển việc xác minh lúc startup. Nó không quyết định cách phát hiện module, không bật module-specific Flyway và không thay thế architecture test trong CI. Khi dùng custom detection strategy, hãy đưa strategy vào production sources để test và runtime xây dựng cùng module model. Nếu verifier không chạy, kiểm tra runtime dependency, effective property value, profile đang active và nguồn cấu hình có thể ghi đè.

## Tài liệu tham khảo

- [Spring Modulith 2.2 — Runtime Support](https://docs.spring.io/spring-modulith/reference/runtime.html)
- [Spring Modulith 2.2 — Configuration Properties](https://docs.spring.io/spring-modulith/reference/appendix.html)
- [Spring Modulith API — `SpringModulithRuntimeAutoConfiguration`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/runtime/autoconfigure/SpringModulithRuntimeAutoConfiguration.html)
- [Spring Boot — Externalized Configuration and Environment Variables](https://docs.spring.io/spring-boot/reference/features/external-config.html)
