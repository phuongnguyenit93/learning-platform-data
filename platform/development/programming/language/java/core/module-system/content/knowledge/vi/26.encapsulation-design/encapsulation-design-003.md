# Không export package nội bộ chỉ vì test

## 1. Vì sao không nên export package nội bộ cho test?

Trong Java Platform Module System (JPMS), module descriptor xác định package nào được công khai cho module khác. Directive **exports** là một phần của hợp đồng API: nó cho phép module tiêu thụ truy cập các kiểu public trong package được export, theo các quy tắc truy cập Java thông thường.

Ví dụ:

    module com.example.billing {
        exports com.example.billing.api;
    }

Package **com.example.billing.api** là bề mặt API mà module chủ động công khai. Các package như **com.example.billing.internal**, **com.example.billing.persistence** hoặc **com.example.billing.impl** vẫn được giữ bên trong module nếu không được export.

Một lớp có modifier public không tự động trở thành API truy cập được từ mọi module. Nếu package chứa lớp không được export, module khác không thể sử dụng lớp đó theo cách truy cập thông thường chỉ vì lớp được khai báo public.

Khi viết unit test, đôi khi ta muốn truy cập lớp hoặc phương thức nội bộ để kiểm tra thuật toán, trạng thái hoặc nhánh lỗi. Việc thêm:

    exports com.example.billing.internal;

chỉ để test biên dịch được sẽ làm package nội bộ trở thành bề mặt truy cập của module trong mọi môi trường sử dụng artifact đó. Người dùng thư viện có thể bắt đầu phụ thuộc vào implementation detail. Sau này đổi tên package, chuyển lớp hoặc thay đổi cấu trúc nội bộ sẽ khó hơn vì có thể phá vỡ code bên ngoài.

Nguyên tắc thiết kế là: **chỉ export package vì đó là API được hỗ trợ cho consumer, không export chỉ để làm cho test dễ truy cập.**

## 2. exports thực sự làm gì?

Directive **exports** công khai một package tới các module khác. Ví dụ:

    module com.example.billing {
        exports com.example.billing.api;
        exports com.example.billing.spi
            to com.example.integration;
    }

Có hai dạng:

- **Unqualified export:** package được export cho các module đọc được module hiện tại.
- **Qualified export:** package chỉ được export tới các module được liệt kê sau từ khóa **to**.

Qualified export có thể hữu ích cho một SPI hoặc API được chia sẻ có chủ đích với một nhóm module cụ thể. Tuy nhiên, dùng tên module test trong production descriptor chỉ để test truy cập nội bộ vẫn tạo một ngoại lệ trong hợp đồng module và thường không phải lựa chọn phù hợp.

Export không tự động export các subpackage. Nếu module export **com.example.billing.api**, package **com.example.billing.api.internal** vẫn là package riêng và không được export nếu không khai báo riêng.

Export cũng không bỏ qua các modifier Java. Một package được export không làm cho thành viên private trở thành public. Nó chỉ loại bỏ rào cản encapsulation ở cấp package của JPMS để các module khác có thể truy cập những kiểu và thành viên vốn được phép theo quy tắc ngôn ngữ.

## 3. Encapsulation là hợp đồng của module

Một module tốt thường có một bề mặt API nhỏ và một phần implementation lớn hơn được giữ kín.

Ví dụ:

    module com.example.billing {
        requires java.sql;

        exports com.example.billing.api;
        uses com.example.billing.spi.PaymentGateway;
    }

Cấu trúc package:

    com.example.billing.api
      InvoiceService.java
      Invoice.java

    com.example.billing.spi
      PaymentGateway.java

    com.example.billing.internal
      InvoiceServiceImpl.java
      InvoiceValidator.java

    com.example.billing.persistence
      JdbcInvoiceRepository.java

Consumer chỉ cần sử dụng **InvoiceService** và **Invoice**. Implementation, validator và repository có thể thay đổi mà không ảnh hưởng đến consumer nếu chúng không bị công khai.

Nếu export package nội bộ chỉ để test, module đã công bố nhiều chi tiết hơn mức consumer cần. Điều đó có thể dẫn đến:

- Consumer phụ thuộc vào lớp implementation thay vì API.
- Refactor package hoặc thay đổi cấu trúc nội bộ gây lỗi tương thích.
- Module mất khả năng kiểm soát các điểm mở rộng.
- Các kiểu nội bộ có thể bị sử dụng sai vòng đời hoặc sai thứ tự gọi.
- Việc thay thế implementation bằng cách khác trở nên khó khăn.
- API surface lớn hơn khiến tài liệu, versioning và kiểm thử tương thích phức tạp hơn.

Test nên giúp bảo vệ hợp đồng của module. Nó không nên vô tình mở rộng hợp đồng đó.

## 4. Ưu tiên kiểm thử qua public API

Cách kiểm thử đầu tiên nên là gọi module từ góc nhìn của consumer:

    InvoiceService service = BillingModule.createService();

    Invoice invoice = service.createInvoice(request);

    assertEquals(InvoiceStatus.CREATED, invoice.status());

Test này xác nhận hành vi mà consumer thực sự quan sát được. Nó vẫn có thể kiểm tra nhiều quy tắc nghiệp vụ, tính hợp lệ của dữ liệu, xử lý lỗi và tương tác giữa các thành phần nội bộ mà không cần truy cập trực tiếp implementation.

Một cách tổ chức tốt là tạo test consumer trong module riêng:

    module com.example.billing.tests {
        requires com.example.billing;
        requires org.junit.jupiter.api;
    }

Test chỉ import các kiểu được export từ **com.example.billing**. Nếu test không biên dịch được vì đang dùng một package nội bộ, hãy xem lại test có đang kiểm tra một hợp đồng được hỗ trợ hay đang phụ thuộc vào chi tiết triển khai.

Kiểm thử qua API công khai có các lợi ích:

- Xác nhận hành vi mà ứng dụng thực tế sử dụng.
- Giữ được quyền thay đổi implementation.
- Phát hiện lỗi tích hợp giữa API và các thành phần nội bộ.
- Không cần thêm export chỉ dành cho test.
- Giúp test ổn định hơn khi refactor.

Không phải mọi test đều phải là black-box. White-box test vẫn hữu ích cho thuật toán phức tạp, nhưng cần thiết lập ranh giới truy cập riêng cho môi trường test.

## 5. Khi cần white-box test, hãy mở quyền ở cấu hình test

JPMS cung cấp các option của compiler và launcher để điều chỉnh quyền truy cập trong một lần chạy cụ thể. Chúng hữu ích khi test cần truy cập package nội bộ mà không muốn biến package đó thành API của artifact production.

### Dùng --add-exports cho test

Nếu test cần tham chiếu các kiểu public trong package nội bộ của một named module, có thể dùng **--add-exports**.

Ví dụ module:

    module com.example.billing {
        exports com.example.billing.api;
    }

Test chạy trong unnamed module và cần truy cập một lớp public trong package nội bộ. Khi biên dịch test, có thể thêm:

    javac --module-path mods \
          --add-exports com.example.billing/com.example.billing.internal=ALL-UNNAMED \
          -cp junit-platform-console-standalone.jar \
          -d target/test-classes \
          src/test/java/com/example/billing/InvoiceValidatorTest.java

Khi chạy test, truyền quyền tương ứng cho JVM:

    java --module-path mods \
         --add-exports com.example.billing/com.example.billing.internal=ALL-UNNAMED \
         -jar junit-platform-console-standalone.jar \
         execute --class-path target/test-classes \
         --select-class com.example.billing.InvoiceValidatorTest

Ví dụ minh họa dùng JUnit Console và đường dẫn build phổ biến; tùy phiên bản JUnit hoặc build tool, cách truyền classpath và chọn test có thể khác.

Đích **ALL-UNNAMED** có nghĩa package được export tới các unnamed modules. Nếu test nằm trong một named module, hãy chỉ định đúng tên module test thay vì ALL-UNNAMED.

**--add-exports** cho phép truy cập các kiểu public trong package được chỉ định. Nó không cấp quyền deep reflection vào thành viên private hoặc package-private.

### Dùng --add-opens khi framework cần deep reflection

Một số framework test, dependency injection hoặc mocking framework dùng reflection để truy cập field, constructor hoặc method không public. Khi đó, **--add-exports** có thể chưa đủ.

Dùng **--add-opens** ở thời điểm chạy:

    java --module-path mods \
         --add-opens com.example.billing/com.example.billing.internal=ALL-UNNAMED \
         -jar junit-platform-console-standalone.jar \
         execute --class-path target/test-classes

Option này mở package cho deep reflection từ module đích được chỉ định. Nó không làm các kiểu nội bộ trở thành API compile-time cho test. Nếu test cần tham chiếu trực tiếp một kiểu public trong package chưa export, vẫn cần cơ chế export phù hợp khi biên dịch.

**--add-opens** là option của runtime launcher. Không dùng nó thay cho --add-exports khi compiler cần quyền truy cập package.

### Dùng cả hai khi test có cả hai nhu cầu

Một test có thể vừa import kiểu public nội bộ, vừa cần framework phản chiếu sâu. Khi đó có thể truyền cả hai option:

    java --module-path mods \
         --add-exports com.example.billing/com.example.billing.internal=ALL-UNNAMED \
         --add-opens com.example.billing/com.example.billing.internal=ALL-UNNAMED \
         -jar junit-platform-console-standalone.jar \
         execute --class-path target/test-classes

Chỉ cấp quyền cho package cụ thể và đúng đích test cần. Tránh mở toàn bộ module hoặc toàn bộ package cho tất cả module nếu không cần thiết.

## 6. Đưa test vào chính module bằng --patch-module

Một cách khác là biên dịch và chạy test như một phần của module đang được kiểm thử. Build tool có thể dùng **--patch-module** để bổ sung test classes vào module đích trong môi trường test.

Ví dụ khái niệm:

    javac --module-path mods \
          --patch-module com.example.billing=target/test-classes \
          -d target/test-classes \
          src/test/java/com/example/billing/internal/InvoiceValidatorTest.java

Khi chạy, build tool cấu hình JVM để patch test classes vào module:

    java --module-path mods \
         --patch-module com.example.billing=target/test-classes \
         --module com.example.billing/com.example.billing.test.TestLauncher

Khi test classes được đưa vào module đích, chúng thuộc cùng ranh giới module với implementation và có thể truy cập package-private theo các quy tắc Java thông thường. Cấu hình thực tế phụ thuộc cách build tool biên dịch test, vị trí output và cách test framework được đưa vào module graph.

Nếu test framework nằm ở module khác, module đang được patch có thể cần thêm readability tới framework. Build tool có thể cấu hình **--add-reads** cho test runtime. Không nên đưa các cấu hình test này vào descriptor production nếu chúng không phải dependency của ứng dụng thực tế.

**--patch-module** hữu ích cho white-box testing, nhưng nên được giới hạn trong test task. Nó không phải cách để đưa lớp test hoặc implementation nội bộ vào artifact phát hành.

## 7. Phân biệt exports và opens

Hai directive này thường bị nhầm khi cấu hình test:

| Cơ chế | Mục đích | Trường hợp test |
|---|---|---|
| **exports package** | Cho phép module khác truy cập các kiểu public trong package | Test import public type trong API |
| **opens package** | Cho phép deep reflection vào package | Framework cần truy cập field/method/constructor không public |
| **--add-exports** | Bổ sung export trong cấu hình compile/runtime cụ thể | Test tham chiếu kiểu public ở package nội bộ |
| **--add-opens** | Bổ sung open ở runtime | Test framework dùng reflection sâu |
| **--patch-module** | Bổ sung nội dung vào module đích | Đưa test classes vào cùng module để white-box test |

Ví dụ trong descriptor:

    module com.example.billing {
        exports com.example.billing.api;
        opens com.example.billing.persistence;
    }

Directive opens không làm package trở thành API compile-time. Nó chủ yếu phục vụ reflection sâu. Ngược lại, exports không tự cho phép framework truy cập mọi thành viên private.

Nếu chỉ test cần reflection, đừng thêm opens không giới hạn vào production module descriptor. Hãy cấu hình --add-opens trong test JVM để quyền mở chỉ tồn tại ở lần chạy test đó.

## 8. Qualified exports có phải giải pháp cho test?

JPMS hỗ trợ qualified export:

    module com.example.billing {
        exports com.example.billing.internal
            to com.example.billing.tests;
    }

Cách này giới hạn quyền truy cập package cho module có tên cụ thể. Nó có thể hợp lý nếu một package thực sự là SPI hoặc API nội bộ được chia sẻ có chủ đích với một module khác.

Tuy nhiên, nếu **com.example.billing.tests** chỉ là module kiểm thử, qualified export vẫn đưa tên module test vào production descriptor. Artifact phát hành sẽ mang một ngoại lệ truy cập dành riêng cho test, và việc đổi tên hoặc tách test module có thể ảnh hưởng descriptor.

Do đó, qualified export chỉ nên dùng khi mối quan hệ giữa hai module là một phần có chủ đích của kiến trúc. Với test-only access, ưu tiên cấu hình compiler/launcher hoặc patch module trong test task.

## 9. Tổ chức package và test để tránh split package

Một lỗi khác xuất hiện khi test được đặt trong cùng package name nhưng lại được biên dịch thành một named module riêng. Ví dụ production module chứa:

    com.example.billing.internal.InvoiceValidator

và test module riêng cũng chứa:

    com.example.billing.internal.InvoiceValidatorTest

Nếu cả hai module cùng sở hữu package **com.example.billing.internal**, cấu hình có thể gặp vấn đề split package. Cùng tên package không làm hai package thuộc hai module khác nhau trở thành một.

Các cách tổ chức thường dùng:

- Đặt test classes trong package test riêng và kiểm thử qua public API.
- Nếu cần package-private access, cấu hình test classes như phần được patch vào module production trong test runtime.
- Dùng build tool hỗ trợ JPMS để tạo module test và cấu hình reads/opens/patch phù hợp.
- Không tạo một module test chỉ để export toàn bộ package nội bộ của module production.

Package name giống nhau chỉ có ý nghĩa khi lớp thực sự được nạp trong cùng ranh giới runtime phù hợp. Tách test thành module độc lập không tự động cho phép test truy cập package-private của module production.

## 10. Ví dụ thiết kế hoàn chỉnh

Giả sử module billing có API và implementation:

    module com.example.billing {
        requires java.sql;
        exports com.example.billing.api;
    }

    package com.example.billing.api;

    public interface InvoiceService {
        Invoice create(InvoiceRequest request);
    }

Implementation được giữ trong package không export:

    package com.example.billing.internal;

    final class InvoiceValidator {
        boolean isValid(InvoiceRequest request) {
            return request != null;
        }
    }

Consumer module chỉ sử dụng API:

    module com.example.application {
        requires com.example.billing;
    }

Test black-box gọi InvoiceService và xác nhận kết quả, không cần biết InvoiceValidator tồn tại.

Nếu thuật toán trong InvoiceValidator có nhiều nhánh phức tạp và cần white-box test, cấu hình test task có thể patch test class vào com.example.billing hoặc dùng --add-exports cho test module nếu lớp cần tham chiếu là public. Nếu framework cần truy cập private members, thêm --add-opens chỉ trong JVM test.

Production module-info.java vẫn giữ đúng hợp đồng:

    module com.example.billing {
        requires java.sql;
        exports com.example.billing.api;
    }

Nhờ đó, consumer chỉ nhìn thấy API được hỗ trợ, còn test vẫn có thể dùng các cơ chế chuyên biệt trong môi trường kiểm thử.

## 11. Ghi nhớ

- **exports** là hợp đồng API của module; chỉ export package mà consumer thực sự cần.
- Không export package nội bộ chỉ để test truy cập được implementation.
- Package không export vẫn có thể chứa các lớp public, nhưng module khác không thể dùng chúng theo truy cập thông thường.
- Ưu tiên test qua public API để bảo vệ hành vi mà consumer quan sát được.
- Dùng **--add-exports** trong test khi cần tham chiếu public types ở package nội bộ.
- Dùng **--add-opens** trong test runtime khi framework cần deep reflection.
- **--add-opens** không thay thế quyền truy cập compile-time của --add-exports.
- Dùng **--patch-module** khi cần đưa test classes vào cùng module để kiểm thử package-private hoặc implementation detail.
- Qualified exports chỉ phù hợp khi quan hệ truy cập là một phần có chủ đích của kiến trúc, không phải lối tắt cho test.
- Không mở toàn bộ module cho ALL-UNNAMED trong production chỉ để làm test framework hoạt động.
- Giữ test-only options trong cấu hình test của Maven, Gradle hoặc test launcher.
- Kiểm tra ranh giới package và module để tránh split package khi tách test thành module riêng.

**Một module nên công khai đúng những gì consumer cần sử dụng.** Test có thể cần quyền truy cập sâu hơn, nhưng quyền đó nên được cấp trong cấu hình kiểm thử và chỉ cho package, module, thời điểm cần thiết.

## Tài liệu tham khảo

- Java Platform Module System — JEP 261: https://openjdk.org/jeps/261
- Java SE 21 Tool Specifications — javac: https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html
- Java SE 21 Tool Specifications — java launcher: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- Java SE 21 API — Module: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html