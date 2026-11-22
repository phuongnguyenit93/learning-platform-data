# Module nhỏ có thật sự giảm phụ thuộc không?

## 1. Module nhỏ không tự động có ít phụ thuộc

Chia một ứng dụng thành nhiều module nhỏ có thể làm ranh giới rõ ràng hơn, nhưng số lượng module tăng không đồng nghĩa mức độ phụ thuộc giảm. Một module nhỏ vẫn có thể phụ thuộc vào rất nhiều module khác; ngược lại, một module có phạm vi lớn nhưng cohesion tốt và API ổn định có thể tạo ra ít quan hệ phụ thuộc hơn.

Cần phân biệt ba yếu tố:

- **Kích thước module:** module chứa bao nhiêu package, lớp hoặc chức năng.
- **Cohesion:** các thành phần bên trong module có phục vụ cùng một trách nhiệm và thay đổi cùng nhau hay không.
- **Coupling:** module cần biết, gọi hoặc phụ thuộc vào bao nhiêu module khác để thực hiện trách nhiệm của mình.

Mục tiêu thiết kế không phải tạo module nhỏ nhất có thể. Mục tiêu là tạo các module có trách nhiệm rõ ràng, phụ thuộc có chủ đích và bề mặt API đủ nhỏ để thay đổi độc lập.

Ví dụ, tách một module billing thành các module rất nhỏ:

    com.example.billing.invoice
    com.example.billing.tax
    com.example.billing.discount
    com.example.billing.customer
    com.example.billing.persistence
    com.example.billing.validation

Nếu mỗi module phải gọi trực tiếp nhiều module còn lại, đồ thị phụ thuộc có thể trở nên dày đặc. Thay đổi một quy tắc nghiệp vụ có thể yêu cầu sửa nhiều module và cập nhật nhiều module-info.java.

Một thiết kế ít module hơn nhưng chia theo năng lực nghiệp vụ có thể dễ hiểu hơn:

    com.example.billing
    com.example.customer
    com.example.catalog
    com.example.infrastructure

Điều này không có nghĩa luôn phải gộp module. Cần xem trách nhiệm, hướng phụ thuộc và khả năng thay đổi độc lập của từng phần.

## 2. Đánh giá phụ thuộc bằng đồ thị module

Có thể mô hình hóa module như các đỉnh trong đồ thị có hướng. Một directive **requires** tạo quan hệ đọc từ module khai báo sang module được yêu cầu.

Ví dụ:

    module com.example.application {
        requires com.example.billing;
        requires com.example.customer;
    }

    module com.example.billing {
        requires com.example.customer;
        requires com.example.persistence;
    }

    module com.example.persistence {
        requires java.sql;
    }

Đồ thị này cho thấy application phụ thuộc vào billing và customer; billing lại phụ thuộc vào customer và persistence. Một thay đổi trong persistence có thể ảnh hưởng tới billing và gián tiếp tới application nếu API hoặc hành vi mà chúng sử dụng thay đổi.

Khi phân tích coupling, nên xem:

- **Fan-out:** một module phụ thuộc vào bao nhiêu module khác.
- **Fan-in:** có bao nhiêu module phụ thuộc vào module này.
- **Dependency depth:** cần đi qua bao nhiêu tầng dependency để đến một thành phần.
- **Cycles:** các module có tạo quan hệ phụ thuộc vòng hay không.
- **API surface:** module công khai bao nhiêu package và kiểu cho module khác.

JPMS yêu cầu đồ thị module hợp lệ, không cho phép chu trình trong quan hệ requires. Vì vậy, một chuỗi phụ thuộc vòng sẽ gây lỗi khi xây dựng hoặc resolve module graph. Tuy nhiên, không có chu trình không có nghĩa kiến trúc đã ít coupling; một module vẫn có thể phụ thuộc trực tiếp vào rất nhiều module.

Một module nhỏ nhưng có fan-out cao có thể là điểm điều phối quá tải. Một module API được nhiều module sử dụng có fan-in cao nhưng điều đó có thể hợp lý nếu API ổn định và có trách nhiệm rõ ràng.

## 3. Cohesion quan trọng hơn số lượng lớp

Một module nên nhóm những thành phần thay đổi cùng nhau vì cùng phục vụ một trách nhiệm. Đây là ý nghĩa thực tế của cohesion trong thiết kế module.

Ví dụ, các lớp sau thường có lý do để ở cùng một module billing:

    com.example.billing.api.InvoiceService
    com.example.billing.internal.InvoiceValidator
    com.example.billing.internal.InvoiceCalculator
    com.example.billing.internal.InvoiceRepository

Chúng cùng thực hiện một năng lực nghiệp vụ và có thể cần thay đổi cùng nhau khi quy tắc hóa đơn thay đổi. Việc tách mỗi lớp thành một module sẽ làm tăng cấu hình và quan hệ phụ thuộc mà không tạo ra ranh giới kiến trúc có ý nghĩa.

Ngược lại, nếu module billing chứa cả chức năng gửi email, quản lý người dùng, truy cập catalog và kết nối thanh toán bên ngoài, module có thể đang gộp nhiều trách nhiệm không liên quan. Khi đó, tách theo năng lực nghiệp vụ có thể giảm coupling và cho phép từng phần thay đổi độc lập.

Một câu hỏi hữu ích khi quyết định tách là: **Nếu trách nhiệm này thay đổi, những phần nào thực sự cần thay đổi cùng nó?** Nếu hai nhóm luôn phải thay đổi cùng nhau và không có nhu cầu triển khai hoặc quản trị độc lập, tách thành hai module có thể chỉ tạo thêm đường biên nhân tạo.

## 4. JPMS giúp kiểm soát phụ thuộc như thế nào?

Module descriptor làm rõ quan hệ dependency:

    module com.example.billing {
        requires com.example.customer;
        requires java.sql;

        exports com.example.billing.api;
    }

Directive **requires** khai báo module mà module hiện tại cần đọc. **exports** xác định package nào được module khác truy cập theo quy tắc JPMS.

Điều này giúp phân biệt hai câu hỏi:

- Module cần phụ thuộc vào module nào?
- Module muốn công khai package nào cho consumer?

Một module có thể cần một module khác nhưng không cần export toàn bộ package của chính nó. Ngược lại, export package không tự tạo ra dependency requires; module consumer vẫn cần có readability phù hợp.

JPMS giúp biểu diễn ranh giới tĩnh, nhưng không tự quyết định ranh giới nghiệp vụ đúng. Nếu module A gọi trực tiếp nhiều lớp nội bộ của B, C và D, việc thêm module-info.java chỉ làm các quan hệ đó hiển thị rõ hơn. Nó không làm coupling biến mất.

Một thiết kế tốt thường có các module API nhỏ, ổn định và module implementation được giữ kín. Consumer phụ thuộc vào contract thay vì các lớp triển khai cụ thể.

## 5. requires, requires transitive và requires static

Ba dạng requires ảnh hưởng khác nhau đến dependency graph.

### requires

    module com.example.billing {
        requires com.example.customer;
    }

Module billing cần đọc module customer. Đây là quan hệ dependency thông thường và được thể hiện trực tiếp trong module descriptor.

### requires transitive

    module com.example.billing.api {
        requires transitive com.example.money;
        exports com.example.billing.api;
    }

Nếu module khác requires com.example.billing.api, quan hệ readability tới com.example.money được truyền tiếp theo quy tắc requires transitive. Điều này hữu ích khi kiểu public của API billing sử dụng kiểu từ money và consumer cũng cần đọc module money để làm việc với API đó.

Tuy nhiên, lạm dụng requires transitive có thể làm dependency lan rộng. Một module tiêu thụ API có thể phải đọc thêm nhiều module mà nó không chủ động chọn. Vì vậy, chỉ dùng transitive khi dependency thực sự là một phần của contract public.

### requires static

    module com.example.billing {
        requires static com.example.metrics;
    }

requires static biểu thị dependency cần có khi biên dịch nhưng có thể vắng mặt trong runtime configuration. Nó thường dùng cho annotation, công cụ hoặc tích hợp tùy chọn mà module không cần trong mọi môi trường chạy.

Nếu mã thực tế cần lớp từ module đó khi chạy mà module không có trong runtime configuration, ứng dụng vẫn có thể gặp lỗi liên kết hoặc nạp lớp. requires static không phải cách để bỏ qua một dependency runtime bắt buộc.

### Giữ dependency rõ ràng

Một module nhỏ không nên khai báo requires transitive cho mọi dependency chỉ để consumer dễ biên dịch. Hãy xác định dependency nào thật sự xuất hiện trong API public, dependency nào chỉ phục vụ implementation và dependency nào là tùy chọn.

## 6. Tách module theo hướng phụ thuộc ổn định

Một nguyên tắc hữu ích là để phần thay đổi thường xuyên phụ thuộc vào contract ổn định, thay vì để API lõi phụ thuộc trực tiếp vào implementation thay đổi thường xuyên.

Ví dụ, nếu billing cần gửi thông báo, có thể khai báo một interface:

    package com.example.notification.api;

    public interface NotificationService {
        void send(String recipient, String message);
    }

Module billing phụ thuộc vào contract:

    module com.example.billing {
        requires com.example.notification.api;
    }

Module triển khai email hoặc SMS có thể phụ thuộc vào API đó:

    module com.example.notification.email {
        requires com.example.notification.api;
    }

Billing không cần biết chi tiết của SMTP client, HTTP client hay nhà cung cấp gửi tin. Khi thay đổi implementation, module billing không nhất thiết phải thay đổi.

Có thể đi xa hơn bằng ServiceLoader:

    module com.example.notification.api {
        exports com.example.notification.api;
    }

    module com.example.billing {
        requires com.example.notification.api;
        uses com.example.notification.api.NotificationService;
    }

    module com.example.notification.email {
        requires com.example.notification.api;

        provides com.example.notification.api.NotificationService
            with com.example.notification.email.EmailNotificationService;
    }

Consumer biết service type và provider module đăng ký implementation. Cách này giảm dependency trực tiếp giữa module sử dụng và module triển khai, nhưng vẫn cần quản lý provider, module resolution và cấu hình runtime.

Không nên tạo service abstraction cho mọi method. Interface và service layer chỉ hữu ích khi có một ranh giới thay đổi, khả năng thay thế implementation hoặc nhu cầu mở rộng thực sự.

## 7. Khi nào nên tách một module?

Tách module thường có ích khi một nhóm chức năng có một hoặc nhiều đặc điểm sau:

- Có trách nhiệm nghiệp vụ riêng và API có thể mô tả độc lập.
- Có thể thay đổi hoặc phát hành độc lập với phần còn lại.
- Có dependency khác biệt rõ ràng, chẳng hạn chỉ module persistence cần java.sql.
- Cần giữ package implementation kín với consumer.
- Có nhiều consumer cần dùng chung một contract ổn định.
- Có thể kiểm thử, triển khai hoặc quản trị vòng đời riêng.
- Cần cô lập một dependency tùy chọn hoặc một tích hợp bên ngoài.
- Có thể thiết lập hướng phụ thuộc một chiều rõ ràng.

Ví dụ, một ứng dụng có thể tách:

    com.example.order.api
    com.example.order.core
    com.example.order.persistence
    com.example.order.integration

Nhưng nếu order.core phải gọi trực tiếp hàng chục kiểu public từ persistence và integration, ranh giới có thể chưa đúng. Có thể cần đưa interface repository hoặc gateway vào core và để implementation phụ thuộc ngược vào contract đó.

## 8. Khi nào không nên tách quá nhỏ?

Tách quá nhỏ có thể tạo ra chi phí lớn hơn lợi ích:

- Nhiều module-info.java phải duy trì.
- Nhiều requires và exports làm graph khó đọc.
- API giữa các module dễ trở thành giao tiếp nội bộ quá chi tiết.
- Một thay đổi đơn giản có thể buộc build và version nhiều artifact.
- Khó điều phối thứ tự khởi động, service discovery và module layer.
- Nhiều package nhỏ bị export chỉ để các module khác truy cập.
- Các module bị khóa vào cùng một chu kỳ release, dù được tách trên danh nghĩa.

Nếu hai module luôn được build, test, version và triển khai cùng nhau, đồng thời liên tục gọi API chi tiết của nhau, có thể chúng chưa phải hai đơn vị độc lập tốt.

Mặt khác, không nên giữ mọi thứ trong một module lớn chỉ vì muốn giảm số lượng. Nếu một module có nhiều trách nhiệm không liên quan, API phình to và thay đổi ở một phần liên tục ảnh hưởng phần khác, việc tách có thể đem lại giá trị thực.

## 9. Module JPMS không đồng nghĩa với Maven/Gradle subproject

Cần phân biệt module của JPMS với module/subproject của build tool.

- **JPMS module** là đơn vị module system được mô tả bằng module-info.java hoặc được suy ra như automatic module.
- **Maven module** thường là một project con trong multi-module build.
- **Gradle subproject** là một project trong cấu trúc build.

Một Maven module hoặc Gradle subproject có thể tạo ra một JAR không phải JPMS module tường minh. Ngược lại, một project có thể chứa nhiều source set hoặc artifact theo cách build riêng.

Việc chia repository thành nhiều subproject không tự động tạo ra kiến trúc JPMS tốt. Cần xác định rõ mỗi artifact sẽ trở thành module nào, package nào được export và dependency graph thực tế ra sao.

## 10. Đo và kiểm tra dependency graph

Có thể bắt đầu bằng cách đọc module descriptor:

    jar --describe-module --file billing.jar

Xem dependency của các lớp và package bằng jdeps:

    jdeps --module-path mods --check com.example.billing

Phân tích package dependency:

    jdeps --module-path mods --summary mods/com.example.billing.jar

Tùy mục tiêu, có thể sử dụng thêm:

    jdeps --module-path mods --list-deps mods/com.example.application.jar

Đầu ra của jdeps giúp nhận diện dependency trực tiếp và các module cần thiết theo phân tích bytecode. Nó không đo được toàn bộ coupling về nghiệp vụ, thay đổi source, dữ liệu hoặc hành vi runtime.

Khi đánh giá một module, nên xem:

1. Số module mà nó requires.
2. Các requires có phải dependency trực tiếp thực sự không.
3. Có requires transitive không cần thiết không.
4. Bao nhiêu package được export.
5. Bao nhiêu module khác phụ thuộc vào API của nó.
6. Có chu trình hoặc dependency vòng ở cấp source/build dù module graph không cho phép hay không.
7. Một thay đổi trong module này thường kéo theo bao nhiêu module khác phải sửa hoặc release.

Đừng dùng số lượng module hoặc số dòng requires làm thước đo duy nhất. Các con số chỉ giúp đặt câu hỏi; cần kết hợp hiểu biết về trách nhiệm và luồng thay đổi.

## 11. Ví dụ so sánh hai cách chia module

### Chia theo lớp kỹ thuật quá chi tiết

    module com.example.invoice.entity { }
    module com.example.invoice.validation { }
    module com.example.invoice.calculation { }
    module com.example.invoice.repository { }
    module com.example.invoice.service { }

Nếu mỗi module phải requires nhiều module còn lại, hệ thống có thể tạo nhiều cạnh dependency. Các phần nghiệp vụ liên quan chặt chẽ bị phân tán và thay đổi nhỏ cũng cần phối hợp nhiều module.

### Chia theo trách nhiệm và contract

    module com.example.invoice.api {
        exports com.example.invoice.api;
    }

    module com.example.invoice.core {
        requires com.example.invoice.api;
    }

    module com.example.invoice.persistence {
        requires com.example.invoice.api;
    }

    module com.example.application {
        requires com.example.invoice.api;
    }

Trong thiết kế này, core và persistence có thể cùng triển khai contract theo một kiến trúc dependency được lựa chọn. Ví dụ đơn giản trên chưa thể hiện toàn bộ cách inject repository hoặc wiring runtime, nhưng cho thấy API được tách thành một contract dùng chung.

Một lựa chọn khác là gộp core và persistence nếu chúng luôn thay đổi và triển khai cùng nhau. Quyết định cuối phụ thuộc vào việc persistence có cần thay thế độc lập, có consumer khác hay có yêu cầu cô lập dependency hay không.

## 12. Ghi nhớ

- Module nhỏ không tự động giảm coupling; số module ít cũng không tự động tạo kiến trúc tốt.
- Cohesion và hướng phụ thuộc quan trọng hơn kích thước hoặc số lớp.
- Đánh giá fan-in, fan-out, dependency depth, API surface và các chu trình ở cấp kiến trúc.
- requires tạo dependency trực tiếp; requires transitive lan truyền readability và cần được dùng có chủ đích.
- requires static phù hợp với dependency compile-time tùy chọn ở runtime, không thay thế dependency runtime bắt buộc.
- Module API ổn định có thể giúp implementation thay đổi độc lập.
- ServiceLoader có thể giảm dependency trực tiếp giữa consumer và provider khi có nhu cầu thay thế implementation.
- Chỉ tách module khi ranh giới trách nhiệm, thay đổi, phát hành hoặc quản trị thực sự độc lập.
- Không nhầm JPMS module với Maven module hoặc Gradle subproject.
- Dùng jar --describe-module và jdeps để quan sát dependency, nhưng kết hợp với phân tích thay đổi và trách nhiệm nghiệp vụ.

**Module nhỏ chỉ giảm phụ thuộc khi ranh giới của nó phản ánh một trách nhiệm độc lập và các module giao tiếp qua contract ổn định.** Nếu việc chia nhỏ chỉ làm tăng số requires, exports và điểm phối hợp, kiến trúc có thể trở nên phức tạp hơn dù mỗi module ít lớp hơn.

## Tài liệu tham khảo

- Java Platform Module System — JEP 261: https://openjdk.org/jeps/261
- Java SE 21 API — Module: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html
- Java SE 21 Tool Specifications — jdeps: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeps.html
- Java SE 21 Tool Specifications — java launcher: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html