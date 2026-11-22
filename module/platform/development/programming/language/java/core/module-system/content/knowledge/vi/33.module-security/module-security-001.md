# Encapsulation như một lớp giảm bề mặt truy cập

## 1. Encapsulation và attack surface

Trong Java, **encapsulation** là cách tổ chức trạng thái và hành vi sao cho người dùng một thành phần chỉ tiếp cận được những thao tác mà thành phần đó chủ động công khai. Lớp có thể giữ dữ liệu trong field private, cung cấp method có kiểm soát và che giấu các lớp triển khai phía sau một interface hoặc API ổn định.

Trong Java Platform Module System (JPMS), encapsulation được mở rộng từ phạm vi lớp và package lên phạm vi module. Module descriptor xác định package nào được export, package nào chỉ dùng nội bộ và package nào được mở cho deep reflection.

Một bề mặt truy cập nhỏ giúp giảm số điểm mà mã bên ngoài có thể gọi, cấu hình hoặc tác động trực tiếp. Trong ngữ cảnh security, điều đó có nghĩa là giảm số API, trạng thái và chi tiết triển khai mà ứng dụng phải bảo vệ trước đầu vào không tin cậy hoặc cách sử dụng sai.

Ví dụ, một module thanh toán có thể chỉ công khai API:

    module com.example.payment {
        exports com.example.payment.api;
    }

Các package triển khai như:

    com.example.payment.internal
    com.example.payment.persistence
    com.example.payment.crypto

được giữ kín nếu không export hoặc open. Consumer chỉ nhìn thấy những kiểu được thiết kế để sử dụng. Module có thể thay đổi cách xác thực, lưu trữ hoặc mã hóa nội bộ mà không biến các lớp đó thành hợp đồng công khai.

Encapsulation là một lớp giảm bề mặt truy cập, không phải một sandbox hoàn chỉnh. Nó hỗ trợ kiểm soát khả năng truy cập của mã Java trong module system; nó không tự bảo vệ ứng dụng khỏi mọi lỗi logic, dữ liệu đầu vào độc hại, lỗ hổng native code hoặc mã đã được cấp quyền thực thi bên trong tiến trình.

## 2. Từ access modifier đến ranh giới module

Java có nhiều lớp kiểm soát truy cập. Mỗi lớp giải quyết một phạm vi khác nhau:

| Cơ chế | Phạm vi | Ý nghĩa |
|---|---|---|
| private | Thành viên của lớp | Chỉ mã trong lớp khai báo được truy cập trực tiếp |
| package-private | Các lớp trong cùng package | Hỗ trợ cộng tác nội bộ giữa các lớp cùng package |
| protected | Package và lớp con theo quy tắc Java | Hỗ trợ mở rộng có kiểm soát |
| public | Mọi nơi có thể truy cập kiểu/package | Công khai ở cấp ngôn ngữ, nhưng vẫn chịu quy tắc module |
| exports | Package của một named module | Cho phép module khác đọc và truy cập các kiểu public trong package |
| opens | Package của một named module | Cho phép deep reflection vào package theo quy tắc JPMS |

Modifier public không có nghĩa là mọi module đều có thể dùng lớp. Một public class nằm trong package không được export vẫn được giữ ngoài bề mặt truy cập thông thường của module.

Ví dụ:

    module com.example.payment {
        exports com.example.payment.api;
    }

    package com.example.payment.internal;

    public final class PaymentTokenVerifier {
        public boolean verify(String token) {
            // Implementation details
            return true;
        }
    }

Dù PaymentTokenVerifier là public, module khác không thể sử dụng nó theo cách truy cập thông thường vì package com.example.payment.internal không được export.

Điều này giúp module giữ quyền kiểm soát nơi implementation được sử dụng. Nếu sau này thay lớp verifier bằng một service hoặc một implementation khác, consumer không bị phụ thuộc trực tiếp vào chi tiết đó.

## 3. Thiết kế API nhỏ để giảm điểm truy cập

Một module nên công khai những thao tác mà consumer cần, không công khai toàn bộ các lớp tạo nên implementation.

Ví dụ một API thanh toán:

    package com.example.payment.api;

    public interface PaymentService {
        PaymentResult charge(PaymentRequest request);
    }

    public record PaymentRequest(
            String accountId,
            long amountInCents) {
    }

    public record PaymentResult(
            String transactionId,
            boolean accepted) {
    }

Consumer chỉ cần gọi PaymentService:

    PaymentResult result = paymentService.charge(request);

Các lớp xác thực, kiểm tra hạn mức, truy cập database, xử lý khóa và ghi audit log có thể nằm trong package nội bộ. Không cần export những lớp đó chỉ để consumer phối hợp trực tiếp.

Thiết kế API nhỏ có một số lợi ích bảo mật:

- Giảm số phương thức có thể bị gọi từ bên ngoài.
- Giảm số trạng thái nội bộ mà consumer có thể quan sát hoặc cố thay đổi.
- Tập trung kiểm tra đầu vào tại một số điểm vào được xác định.
- Giảm khả năng consumer gọi sai thứ tự các bước nội bộ.
- Hạn chế việc lộ thông tin nhạy cảm qua kiểu dữ liệu hoặc exception không cần thiết.
- Cho phép thay đổi implementation mà không mở rộng hợp đồng tương thích.

API nhỏ không thay thế validation. Một method public vẫn phải kiểm tra dữ liệu đầu vào, xác thực danh tính và quyền thực hiện thao tác. Encapsulation giúp định vị các điểm cần kiểm tra và tránh để consumer bỏ qua chúng bằng cách gọi thẳng lớp nội bộ.

## 4. Không export package nội bộ

Một package nên được export khi nó là phần API được hỗ trợ. Ví dụ:

    module com.example.identity {
        exports com.example.identity.api;
    }

Còn các package sau được giữ nội bộ:

    com.example.identity.internal
    com.example.identity.crypto
    com.example.identity.persistence
    com.example.identity.audit

Nếu export toàn bộ package chỉ để thuận tiện cho một ứng dụng khác, module có thể vô tình biến implementation detail thành API. Khi đó consumer có thể phụ thuộc vào lớp nội bộ, constructor, exception hoặc thứ tự xử lý mà module chưa từng cam kết duy trì.

Một số hệ quả:

- Việc refactor hoặc thay thế implementation trở nên khó khăn.
- Consumer có thể bỏ qua validation ở API chính và gọi trực tiếp lớp nội bộ.
- Các lớp có quyền truy cập dữ liệu hoặc tài nguyên nhạy cảm được lộ rộng hơn.
- Khó giới hạn quyền truy cập theo vai trò của từng module.
- Bề mặt cần kiểm tra tương thích và bảo mật tăng lên.

Không export package nội bộ không có nghĩa mã nội bộ tự động an toàn. Các lớp trong module vẫn cần tuân thủ access modifier, kiểm tra đầu vào, quản lý tài nguyên và nguyên tắc least privilege.

## 5. Qualified exports và quyền truy cập có chủ đích

JPMS hỗ trợ **qualified exports**, tức chỉ export package cho một nhóm module được nêu rõ.

    module com.example.payment {
        exports com.example.payment.api;

        exports com.example.payment.spi
            to com.example.payment.adapter;
    }

Trong ví dụ này, package API được công khai rộng rãi cho module đọc được module payment. Package SPI chỉ được export tới module adapter có tên cụ thể.

Qualified exports hữu ích khi một module có một extension point dành cho module khác đã biết. Nó giúp thu hẹp phạm vi consumer có thể truy cập package.

Tuy nhiên, qualified exports vẫn là một phần của module descriptor và hợp đồng kiến trúc. Nếu module đích có thể bị thay thế bởi mã không đáng tin cậy hoặc không được quản lý, việc cấp quyền truy cập package cần được xem xét cẩn thận.

Không nên dùng qualified exports như cách cấp quyền cho mọi test module hoặc mọi plugin mà không có lý do thiết kế rõ ràng. Nếu quyền chỉ cần trong test, cấu hình test launcher hoặc build tool thường phù hợp hơn.

## 6. opens và rủi ro từ deep reflection

Directive **opens** cho phép framework hoặc thư viện dùng reflection sâu vào package, bao gồm truy cập thành viên không public trong những điều kiện JPMS cho phép.

Ví dụ:

    module com.example.payment {
        exports com.example.payment.api;
        opens com.example.payment.persistence
            to com.example.orm;
    }

Module ORM có thể cần reflection để ánh xạ entity hoặc đọc metadata. Việc mở package được giới hạn cho module com.example.orm thay vì mở toàn bộ module.

Một khai báo rộng hơn:

    open module com.example.payment {
        exports com.example.payment.api;
    }

sẽ mở tất cả package của module cho deep reflection. Cách này có thể thuận tiện với framework cũ nhưng làm giảm encapsulation vì nhiều thành phần nội bộ trở nên có thể được truy cập qua reflection.

Nên ưu tiên mở package cụ thể và đúng module đích. Chỉ dùng open module khi framework thực sự cần quyền rộng và phạm vi đó đã được chấp nhận trong thiết kế.

Reflection không phải cách để bỏ qua mọi quy tắc truy cập. Các thao tác như setAccessible(true) có thể bị giới hạn bởi JPMS; truy cập sâu vào package chưa mở có thể dẫn đến InaccessibleObjectException. Mở package cũng không biến field private thành API ổn định, nó chỉ cấp quyền reflection trong phạm vi được phép.

## 7. Runtime options có thể làm yếu encapsulation

Java launcher có các option cho phép điều chỉnh ranh giới module khi chạy:

| Option | Tác dụng | Tác động đến encapsulation |
|---|---|---|
| --add-exports | Export thêm package tới module đích | Mở truy cập thông thường tới kiểu public trong package |
| --add-opens | Mở package cho deep reflection | Cho phép framework truy cập thành viên không public |
| --add-reads | Bổ sung quan hệ readability | Cho phép module đọc module khác |
| --patch-module | Bổ sung lớp hoặc tài nguyên vào module đích | Thay đổi nội dung module trong cấu hình chạy |

Ví dụ:

    java --add-exports com.example.payment/com.example.payment.internal=ALL-UNNAMED \
         --module-path mods \
         --module com.example.application/com.example.application.Main

Lệnh này export package internal tới các unnamed modules. Nó có thể giúp tương thích tạm thời với thư viện cũ, nhưng cũng làm tăng số mã có thể truy cập package đó.

Ví dụ mở package cho reflection:

    java --add-opens com.example.payment/com.example.payment.persistence=ALL-UNNAMED \
         --module-path mods \
         --module com.example.application/com.example.application.Main

Không nên thêm các option này vào production một cách mặc định. Hãy xác định framework nào cần quyền, package nào cần mở và module nào là đích. Sau đó ghi lại lý do, giới hạn phạm vi và có kế hoạch loại bỏ khi dependency được cập nhật.

## 8. Encapsulation và nguyên tắc least privilege

Nguyên tắc **least privilege** yêu cầu mỗi thành phần chỉ nhận quyền cần thiết để thực hiện nhiệm vụ.

Trong JPMS, có thể áp dụng bằng cách:

- Chỉ export package API thực sự cần cho consumer.
- Dùng qualified exports khi chỉ một số module cần package SPI.
- Chỉ mở package cho reflection khi framework có yêu cầu cụ thể.
- Tránh open module nếu chỉ một package cần được mở.
- Tránh dùng ALL-UNNAMED khi có thể chỉ định một module đích.
- Giữ dependency requires ở mức cần thiết.
- Không expose lớp nội bộ hoặc capability nhạy cảm qua API công khai.
- Tách module theo trách nhiệm để quyền truy cập dễ được hiểu và quản lý.

Ví dụ:

    module com.example.secrets {
        exports com.example.secrets.api;
        opens com.example.secrets.persistence
            to com.example.orm;
    }

Module consumer có thể sử dụng API công khai. ORM có thể reflection vào package persistence theo mục đích đã xác định. Package crypto và internal vẫn được giữ kín.

Tuy vậy, JPMS không phải hệ thống phân quyền người dùng hoặc sandbox cho mã độc. Một module khác có thể có quyền truy cập thông qua các directive hoặc runtime option đã cấp; mã cùng tiến trình còn có thể sử dụng các API khác như JNI hoặc native code. Encapsulation cần được kết hợp với xác thực, authorization, kiểm tra dữ liệu, quản lý secret, cập nhật dependency và cấu hình triển khai an toàn.

## 9. Service provider không nhất thiết phải export implementation

ServiceLoader cho phép module cung cấp implementation mà không cần export package chứa lớp provider.

Ví dụ:

    module com.example.payment.api {
        exports com.example.payment.api;
        exports com.example.payment.spi;
    }

    module com.example.payment.provider {
        requires com.example.payment.api;

        provides com.example.payment.spi.PaymentProvider
            with com.example.payment.internal.DefaultPaymentProvider;
    }

Package com.example.payment.internal có thể được giữ kín. Consumer tìm provider thông qua service type công khai, không cần import implementation class.

Cách này giúp giữ ranh giới giữa contract và implementation. Consumer chỉ phụ thuộc vào interface được hỗ trợ, còn module provider có thể thay đổi lớp triển khai mà không buộc consumer biết tên lớp nội bộ.

Không cần export package implementation chỉ để ServiceLoader phát hiện provider được khai báo bằng provides trong module descriptor. Nếu provider được đóng gói theo cơ chế classpath cũ, cấu hình META-INF/services có các quy tắc riêng; dù vậy, việc công khai API vẫn nên tách khỏi chi tiết triển khai.

## 10. Kiểm thử mà không mở rộng API production

Test có thể cần kiểm tra nội bộ, nhưng không nên vì thế mà export package trong module descriptor phát hành.

Ưu tiên test qua public API:

    PaymentResult result = paymentService.charge(request);
    assertTrue(result.accepted());

Nếu cần truy cập public class trong package nội bộ ở test, có thể dùng --add-exports trong cấu hình test. Nếu framework cần deep reflection, có thể dùng --add-opens trong test runtime. Nếu test cần package-private access, build tool có thể cấu hình --patch-module để đưa test classes vào module đang kiểm thử.

Ví dụ runtime test:

    java --add-opens com.example.payment/com.example.payment.internal=ALL-UNNAMED \
         -jar junit-platform-console-standalone.jar

Cấu hình cụ thể phụ thuộc cách test framework và build tool tổ chức module path, classpath và test classes. Những option test-only nên nằm trong task test, không nên bị đưa vào script khởi chạy production.

Nếu test chạy trong một named module riêng, hãy chỉ định tên module đó thay cho ALL-UNNAMED khi có thể. Cấp quyền hẹp hơn giúp test phản ánh chính xác ranh giới dự kiến.

## 11. Cách đánh giá bề mặt truy cập của một module

Có thể bắt đầu bằng việc đọc module descriptor:

    jar --describe-module --file payment.jar

Kiểm tra:

1. Module export những package nào?
2. Có qualified exports không và các module đích có thực sự cần chúng không?
3. Module có directive opens hoặc được khai báo open module không?
4. Các directive requires có phản ánh dependency thực sự không?
5. Có package nội bộ nào đang bị export chỉ vì framework hoặc test không?
6. Có runtime option --add-exports hoặc --add-opens nào được thêm trong script deploy không?
7. Service provider có thể được khai báo bằng provides để giữ implementation package kín không?

Có thể dùng:

    java --show-module-resolution \
         --module-path mods \
         --module com.example.application/com.example.application.Main

để xem module graph được resolve lúc chạy. Kiểm tra cả lệnh launcher thực tế vì option command line có thể làm thay đổi ranh giới truy cập so với module descriptor.

Việc đọc descriptor không chứng minh module an toàn. Nó chỉ giúp hiểu một phần bề mặt truy cập do JPMS công khai và những ngoại lệ runtime đang được áp dụng.

## 12. Ghi nhớ

- Encapsulation thu hẹp những kiểu, trạng thái và thao tác mà mã bên ngoài có thể truy cập.
- Một module nên export API được hỗ trợ, giữ package implementation ở phạm vi nội bộ.
- Modifier public không tự vượt qua ranh giới package export của JPMS.
- Qualified exports giới hạn package cho module đích cụ thể nhưng vẫn là một phần của hợp đồng module.
- opens phục vụ deep reflection; open module mở rộng phạm vi reflection tới tất cả package.
- --add-exports và --add-opens có thể làm yếu encapsulation trong runtime; chỉ cấp đúng package và đúng module cần thiết.
- ServiceLoader cho phép đăng ký provider mà không cần export package implementation.
- Test-only access nên được cấu hình trong build/test runtime, không thêm vào production API chỉ vì tiện.
- Encapsulation không phải sandbox hoàn chỉnh; cần kết hợp với authentication, authorization, validation, secret management và cập nhật dependency.
- Đọc module descriptor và launcher options để hiểu bề mặt truy cập thực tế.

**Encapsulation là một lớp phòng vệ bằng cách giới hạn những điểm mã bên ngoài có thể tiếp cận.** Giữ API nhỏ, package nội bộ kín và quyền reflection có phạm vi giúp giảm bề mặt cần bảo vệ, đồng thời giữ cho module dễ thay đổi và dễ kiểm soát hơn.

## Tài liệu tham khảo

- Java Platform Module System — JEP 261: https://openjdk.org/jeps/261
- Java SE 21 API — Module: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html
- Java SE 21 Tool Specifications — java launcher: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html