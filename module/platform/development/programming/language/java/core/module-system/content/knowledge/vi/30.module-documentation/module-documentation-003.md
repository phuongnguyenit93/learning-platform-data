# Ghi rõ requires, exports, uses và provides

## 1. Vì sao tài liệu module cần nói rõ bốn chỉ thị này?

Trong Java Platform Module System (JPMS), `module-info.java` là hợp đồng kỹ thuật giữa một named module và những module khác. Nó cho biết:

- `requires`: module này cần đọc module nào.
- `exports`: những package nào được công bố như API cho code của module khác.
- `uses`: module này tiêu thụ service contract nào bằng cơ chế service loading.
- `provides ... with ...`: module này đăng ký implementation nào cho một service contract.

Chỉ nhìn thấy những class `public` trong JAR hoặc danh sách dependency của Maven/Gradle không đủ để hiểu toàn bộ hợp đồng JPMS. Một module có thể nằm trên module path nhưng chưa được resolve; package chứa public class vẫn có thể không được export; provider class có thể tồn tại trong JAR nhưng không được đăng ký bằng `provides`.

Vì vậy, README của thư viện modular nên vừa chỉ ra **descriptor chính thức**, vừa giải thích **ý nghĩa với consumer và người triển khai provider**, đồng thời cung cấp cách xác minh artifact sau khi build.

Bốn câu hỏi mà tài liệu nên trả lời rõ ràng:

1. Người dùng thư viện cần khai báo `requires` module nào?
2. Package nào thực sự là public API và package nào là implementation detail?
3. Nếu thư viện dùng service, module consumer cần khai báo `uses` nào?
4. Nếu thư viện cung cấp service, provider class nào được đăng ký và nó được nạp bằng cách nào?

## 2. Một ví dụ có cả requires, exports, uses và provides

Giả sử hệ thống xử lý thanh toán gồm ba phần:

~~~text
com.acme.payment.api       # Service contract và dữ liệu trao đổi
com.acme.payment.card      # Module triển khai provider
com.acme.payment.checkout  # Ứng dụng tìm và sử dụng provider
~~~

Module API:

~~~java
module com.acme.payment.api {
    exports com.acme.payment.api;
}
~~~

Service interface:

~~~java
package com.acme.payment.api;

public interface PaymentProcessor {
    String providerId();
    boolean charge(long amountInCents);
}
~~~

Module provider:

~~~java
module com.acme.payment.card {
    requires com.acme.payment.api;

    provides com.acme.payment.api.PaymentProcessor
        with com.acme.payment.card.internal.CardPaymentProcessor;
}
~~~

Module ứng dụng:

~~~java
module com.acme.payment.checkout {
    requires com.acme.payment.api;

    uses com.acme.payment.api.PaymentProcessor;
}
~~~

Khi biên dịch, cả provider và consumer đều cần đọc module API. Ở runtime, consumer dùng `ServiceLoader` để tìm provider đã tham gia module configuration. Consumer không cần `requires com.acme.payment.card;` chỉ vì nó muốn sử dụng provider thông qua service contract.

Tài liệu của hệ thống nên giải thích từng quyết định này, không chỉ dán ba file descriptor rồi để người đọc tự suy luận.

## 3. Ghi rõ module name và yêu cầu môi trường

Đầu README nên có một đoạn thông tin cơ bản:

| Trường | Ví dụ | Vì sao cần ghi |
|---|---|---|
| Module name | `com.acme.payment.api` | Consumer dùng đúng tên trong `requires` |
| Artifact | `com.acme:payment-api:1.2.0` | Build tool tải đúng dependency |
| Java baseline | JDK 21 | Tránh chạy bằng runtime không phù hợp |
| Module type | Explicit named module | Phân biệt với automatic module |
| Exports | `com.acme.payment.api` | Xác định public API |
| Services | `PaymentProcessor` | Biết service contract và provider discovery |
| Optional integrations | Ví dụ module logging hoặc SQL | Biết dependency nào tùy chọn |

Tên artifact Maven/Gradle **không nhất thiết trùng** với module name. Với explicit modular JAR, module name được định nghĩa bởi descriptor đã biên dịch. Nếu người dùng viết sai `requires`, việc có JAR đúng tên file cũng không giúp JPMS resolve được module.

Trong README, ưu tiên viết đầy đủ module name thay vì chỉ gọi mơ hồ là “module payment”.

## 4. requires: ghi rõ module cần đọc và lý do

Một đoạn descriptor:

~~~java
module com.acme.payment.checkout {
    requires com.acme.payment.api;
    requires java.logging;
}
~~~

cần được giải thích:

- `requires com.acme.payment.api`: ứng dụng dùng các kiểu contract của API thanh toán.
- `requires java.logging`: ứng dụng dùng logging API trong JDK.
- `java.base` được đọc ngầm định, nên thường không cần một dòng `requires java.base;`.

Ví dụ bảng trong tài liệu:

| Dependency module | Loại quan hệ | Được sử dụng để làm gì? |
|---|---|---|
| `com.acme.payment.api` | `requires` | Truy cập `PaymentProcessor` và DTO công khai |
| `java.logging` | `requires` | Ghi log qua `java.util.logging` |
| `java.base` | Mandated/implicit | Các kiểu cốt lõi của Java |

Nếu một module được build bằng Maven hoặc Gradle, nên bổ sung artifact tương ứng với dependency bên thứ ba. Một tên module có thể không cho biết trực tiếp groupId, artifactId và version trong repository.

**Đừng chỉ liệt kê dependency:** cho biết dependency nào thuộc public contract, dependency nào chỉ hỗ trợ implementation và dependency nào phải được cung cấp ở runtime.

## 5. requires transitive: tài liệu phải nêu ảnh hưởng đến consumer

`requires transitive` là một phần quan trọng của public module contract.

Giả sử public API của module report trả về một kiểu trong `java.sql`:

~~~java
module com.acme.report.api {
    requires transitive java.sql;
    exports com.acme.report.api;
}
~~~

Interface:

~~~java
package com.acme.report.api;

import java.sql.Connection;

public interface ReportService {
    void generate(Connection connection);
}
~~~

Dòng `requires transitive java.sql` cho phép những module đọc `com.acme.report.api` có readability tới `java.sql` theo quy tắc JPMS. Nó phù hợp khi kiểu thuộc dependency xuất hiện trong contract public của API.

README cần nói rõ:

- Consumer nào có thể sử dụng API mà không cần khai báo `requires java.sql` riêng?
- Vì sao dependency được chuyển tiếp?
- Những type nào trong public API khiến dependency đó trở thành một phần contract?
- Nếu thay đổi sang `requires` thông thường, consumer có thể phải sửa `module-info.java` như thế nào?

Không nên dùng `requires transitive` cho mọi module dependency chỉ để “đỡ lỗi biên dịch”. Việc mở rộng readability là quyết định thiết kế API và cần được ghi nhận như một phần tương thích của thư viện.

## 6. requires static: ghi rõ điều kiện runtime

Ví dụ một tích hợp tùy chọn:

~~~java
module com.acme.payment.integration {
    requires static com.acme.annotations;
}
~~~

`requires static` mô tả dependency cần được giải quyết khi compile, nhưng không bắt buộc phải có mặt trong runtime configuration theo cách của `requires` thông thường.

Tài liệu nên giải thích:

- Dependency được dùng ở compile-time cho mục đích gì?
- Có code path nào tại runtime thật sự cần nó không?
- Khi kích hoạt tính năng nào thì consumer phải bổ sung artifact/module?
- Hành vi fallback nếu dependency vắng mặt là gì?

Ví dụ mô tả:

> Module `com.acme.annotations` cần khi biên dịch những source dùng annotation hỗ trợ. Ở runtime, ứng dụng không cần module này cho luồng thanh toán cơ bản; nếu bật tính năng tích hợp cụ thể, hãy kiểm tra yêu cầu runtime riêng.

`requires static` không tương đương trực tiếp với một Maven scope hay Gradle configuration. Cần ghi rõ cả dependency của build tool và quy tắc runtime JPMS, nhất là khi thư viện cung cấp optional feature.

## 7. exports: công bố package API, không phải từng class

Descriptor:

~~~java
module com.acme.payment.api {
    exports com.acme.payment.api;
}
~~~

Nghĩa là những public type thích hợp trong package `com.acme.payment.api` có thể được module khác truy cập khi consumer có readability. Các package khác không tự động được export.

Ví dụ:

~~~text
com.acme.payment.api
com.acme.payment.api.internal
com.acme.payment.internal
~~~

Chỉ export `com.acme.payment.api` **không export đệ quy** `com.acme.payment.api.internal` hoặc `com.acme.payment.internal`.

Trong README nên có danh sách rõ:

| Package | Trạng thái | Cam kết |
|---|---|---|
| `com.acme.payment.api` | Exported | Public API dành cho consumer |
| `com.acme.payment.card.internal` | Not exported | Chi tiết provider, không import trực tiếp |
| `com.acme.payment.api.internal` (nếu có) | Not exported | Helper nội bộ, không phải contract |

Nếu source chứa class `public` trong package internal, điều đó không tự biến class thành API có thể dùng từ named module khác. Ranh giới package được xác lập bằng `exports`.

## 8. Qualified exports: chỉ cấp API cho module cụ thể

JPMS hỗ trợ export có đích:

~~~java
module com.acme.payment.api {
    exports com.acme.payment.api;

    exports com.acme.payment.spi
        to com.acme.payment.card, com.acme.payment.wallet;
}
~~~

Đoạn README tương ứng cần nói:

- `com.acme.payment.api` được export vô điều kiện.
- `com.acme.payment.spi` chỉ được export cho `com.acme.payment.card` và `com.acme.payment.wallet`.
- Module khác không thể xem `spi` là public API chung nếu không có quyền bổ sung.
- Module đích vẫn cần có quan hệ readability phù hợp để import các type trong package.

Đừng mô tả qualified exports bằng câu chung “package này được public”. Cần ghi **public cho ai**, vì một module khác ngoài danh sách có thể compile fail dù package vẫn tồn tại trong JAR.

Qualified exports tạo coupling tới tên module đích, nên tài liệu cũng phải cập nhật khi đổi tên các module cộng tác.

## 9. Phân biệt exports với opens trong tài liệu

Dù đề bài tập trung bốn chỉ thị `requires`, `exports`, `uses` và `provides`, README cũng cần giải thích `opens` khi có framework reflection để tránh hiểu nhầm.

Ví dụ:

~~~java
module com.acme.payment.api {
    exports com.acme.payment.api;
    opens com.acme.payment.model
        to com.fasterxml.jackson.databind;
}
~~~

Giải thích:

- `exports` dùng cho truy cập Java thông thường tới public API.
- `opens` cấp quyền deep reflection vào package cho framework được chỉ định.
- Package được `opens` không vì thế trở thành package public API để import như một package đã export.
- `exports` cũng không tự cho phép framework đọc/ghi mọi private field.

Nếu framework chạy dưới unnamed module hoặc cấu hình runtime khác, tên module thực hiện reflection có thể khác; tài liệu triển khai phải dùng đúng module identity thực tế.

Tránh đưa `--add-opens` hoặc `--add-exports` vào hướng dẫn mặc định nếu descriptor có thể mô tả quan hệ đúng. Nếu phải dùng launcher flags khi migration, hãy ghi rõ lý do, module đích, phạm vi và kế hoạch loại bỏ.

## 10. uses: nói rõ module nào tiêu thụ service

`uses` là khai báo của module **tiêu thụ** service. Ví dụ:

~~~java
module com.acme.payment.checkout {
    requires com.acme.payment.api;

    uses com.acme.payment.api.PaymentProcessor;
}
~~~

Nó không chọn một provider cụ thể. Nó cho biết module checkout có nhu cầu tìm implementation của `PaymentProcessor`.

Ví dụ code:

~~~java
package com.acme.payment.checkout;

import com.acme.payment.api.PaymentProcessor;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        PaymentProcessor processor =
                ServiceLoader.load(PaymentProcessor.class)
                        .findFirst()
                        .orElseThrow(() ->
                                new IllegalStateException(
                                        "No PaymentProcessor provider"));

        System.out.println(processor.providerId());
    }
}
~~~

README của consumer nên trả lời:

1. Service type chính xác là gì?
2. Module nào khai báo `uses`?
3. Có cần ít nhất một provider để khởi động không?
4. Nếu không có provider, consumer xử lý kết quả rỗng ra sao?
5. Nếu có nhiều provider, logic chọn provider dựa vào tiêu chí nào?

Nếu code chạy từ named module trực tiếp gọi `ServiceLoader`, descriptor của module caller cần `uses` tương ứng. Chỉ khai báo `requires` module API không thay thế được `uses`.

## 11. provides ... with ...: ghi rõ implementation được đăng ký

Module provider:

~~~java
module com.acme.payment.card {
    requires com.acme.payment.api;

    provides com.acme.payment.api.PaymentProcessor
        with com.acme.payment.card.internal.CardPaymentProcessor;
}
~~~

Implementation:

~~~java
package com.acme.payment.card.internal;

import com.acme.payment.api.PaymentProcessor;

public final class CardPaymentProcessor
        implements PaymentProcessor {

    public CardPaymentProcessor() {
    }

    @Override
    public String providerId() {
        return "card";
    }

    @Override
    public boolean charge(long amountInCents) {
        return amountInCents > 0;
    }
}
~~~

README của provider cần nêu:

| Mục | Giá trị |
|---|---|
| Provider module | `com.acme.payment.card` |
| Service type | `com.acme.payment.api.PaymentProcessor` |
| Implementation | `com.acme.payment.card.internal.CardPaymentProcessor` |
| Provider identifier | `card` |
| Dependency | `requires com.acme.payment.api` |
| Cách kích hoạt | Đưa provider module vào runtime configuration |
| Public package của provider | Không cần export implementation package chỉ để ServiceLoader tìm provider |

Provider class có thể được khai báo ở package không export. JPMS service binding sử dụng metadata `provides`, nên consumer không cần import implementation class.

`ServiceLoader` hỗ trợ provider constructor hoặc provider method hợp lệ theo quy tắc JPMS. Nếu thư viện dùng một phương án đặc biệt, nên mô tả cơ chế khởi tạo và yêu cầu constructor/`provider()` trong hướng dẫn dành cho người bảo trì provider.

## 12. Service API và provider không nên bị buộc phụ thuộc ngược

Một kiến trúc thường dùng:

~~~text
checkout module ------requires------> payment API module
                                        ^
                                        |
                                     requires
                                        |
                                    card provider module
~~~

Contract nằm trong module API. Provider triển khai contract và consumer sử dụng contract.

Không nên viết:

~~~java
// Thiết kế dễ gây coupling, không phải lựa chọn mặc định
module com.acme.payment.api {
    requires com.acme.payment.card;
}
~~~

chỉ để đưa provider vào runtime. Làm vậy khiến API phụ thuộc một implementation cụ thể, giảm khả năng thay thế provider.

Thay vào đó, tài liệu deployment có thể chỉ ra cách thêm provider như root module khi cần:

~~~bash
java --module-path mods \
  --add-modules com.acme.payment.card \
  -m com.acme.payment.checkout/com.acme.payment.checkout.Main
~~~

Hoặc sử dụng service binding trong cấu hình/module layer phù hợp. Việc tìm provider phụ thuộc vào module configuration thực tế, không chỉ vào sự có mặt của JAR trong thư mục.

## 13. Mô tả ServiceLoader theo module layer

Với plugin architecture, provider có thể nằm trong custom `ModuleLayer` thay vì boot layer.

Khi đó hướng dẫn sử dụng nên phân biệt:

~~~java
ServiceLoader.load(PaymentProcessor.class)
~~~

và:

~~~java
ServiceLoader.load(pluginLayer, PaymentProcessor.class)
~~~

Overload nhận `ModuleLayer` tìm provider trong layer được cung cấp và các ancestor layer liên quan. Vì vậy, nếu cần tìm riêng provider của custom layer, có thể kiểm tra module/layer của provider class:

~~~java
var providers =
        ServiceLoader.load(pluginLayer, PaymentProcessor.class)
                .stream()
                .filter(p ->
                        p.type().getModule().getLayer() == pluginLayer)
                .toList();
~~~

README nên nêu cách ứng dụng tạo hoặc nhận `pluginLayer`, module nào được đưa vào configuration và cách consumer xác định provider mong đợi.

Nếu có nhiều layer hoặc nhiều provider, không nên nói chung chung rằng “đặt JAR lên module path là tự động được sử dụng”. Cần chỉ rõ cơ chế resolution/service binding và cách khởi tạo.

## 14. Bảng contract: requires, exports, uses, provides

Trong README của một thư viện modular, một bảng tóm tắt thường giúp người đọc định vị nhanh:

| Chỉ thị | Nằm trong module nào | Ý nghĩa | Consumer/provider cần làm gì |
|---|---|---|---|
| `requires com.acme.payment.api` | Checkout | Consumer đọc API module | Đảm bảo API module có trên module path |
| `requires com.acme.payment.api` | Card provider | Provider triển khai API contract | Dùng đúng service class identity |
| `exports com.acme.payment.api` | Payment API | Public API có thể được module khác sử dụng | Chỉ import public type từ package được export |
| `uses PaymentProcessor` | Checkout | Consumer yêu cầu service | Gọi ServiceLoader và xử lý khi không có provider |
| `provides PaymentProcessor with CardPaymentProcessor` | Card provider | Đăng ký implementation | Đưa provider module vào runtime configuration |

Có thể thêm cột version/artifact nếu hệ thống có nhiều dependency bên thứ ba.

Bảng này nên được suy ra từ descriptor của **artifact phát hành**, không chỉ từ ý định trong source. Nếu build pipeline tạo multi-release JAR hoặc thay descriptor theo profile, cần ghi đúng cấu hình mà người dùng thực sự tải về.

## 15. Một README sử dụng được nên hướng dẫn consumer cụ thể

Ví dụ đoạn hướng dẫn ngắn:

### Thêm module vào project

Với consumer trên module path, thêm artifact `payment-api` và những dependency cần thiết vào build tool, sau đó khai báo:

~~~java
module com.acme.payment.checkout {
    requires com.acme.payment.api;
    uses com.acme.payment.api.PaymentProcessor;
}
~~~

### Thêm provider

Thêm artifact `payment-card` vào runtime module path. Đảm bảo module `com.acme.payment.card` được resolve, chẳng hạn bằng `--add-modules` nếu configuration khởi chạy không tự đưa provider vào.

### Tìm provider

~~~java
PaymentProcessor processor =
        ServiceLoader.load(PaymentProcessor.class)
                .findFirst()
                .orElseThrow();
~~~

### Xử lý lỗi

Nếu không tìm thấy provider:

- Kiểm tra module caller đã khai báo `uses`.
- Kiểm tra provider module có `provides`.
- Kiểm tra provider module đã được resolve.
- Kiểm tra service type của consumer/provider là cùng một class identity.
- Kiểm tra lỗi khởi tạo provider từ exception thực tế.

Các bước đủ cụ thể này có giá trị hơn một đoạn README chỉ nói “hỗ trợ ServiceLoader”.

## 16. Ghi rõ dependency bắt buộc, tùy chọn và chỉ dùng ở build/test

Một README modular nên tránh việc trộn các loại dependency.

Ví dụ:

| Thành phần | Khi compile | Khi chạy | Ghi chú |
|---|---|---|---|
| `com.acme.payment.api` | Bắt buộc cho consumer/provider | Bắt buộc khi consumer/provider dùng contract | Named module API |
| `com.acme.payment.card` | Consumer không cần compile trực tiếp với class provider | Cần khi chọn provider card | Service implementation |
| `java.logging` | Cần nếu module import logging API | Thường cần theo module graph | JDK module |
| Annotation helper `com.acme.annotations` | Có thể chỉ cần compile | Tùy thiết kế | Cân nhắc `requires static` |
| JUnit hoặc test fixtures | Dành cho test | Không phải dependency production | Không đưa vào hướng dẫn runtime thông thường |

Thông tin này cần đồng bộ với Maven/Gradle dependency scope/configuration. Ví dụ, trong Gradle `api` và `implementation` thể hiện cách dependency xuất hiện trên compile classpath của consumer; còn `requires` và `requires transitive` là quan hệ readability của JPMS. Hai hệ thống có liên quan nhưng không đồng nhất.

## 17. Kiểm tra descriptor sau khi build

File `module-info.java` trong source có thể khác nội dung artifact được publish do cách build, packaging hoặc profile. Vì vậy tài liệu release nên đi kèm một lệnh kiểm tra trực tiếp modular JAR:

~~~bash
jar --describe-module --file dist/com.acme.payment.api.jar
~~~

Với provider:

~~~bash
jar --describe-module --file dist/com.acme.payment.card.jar
~~~

Dòng `provides` phải thể hiện service type và implementation tương ứng. Kiểm tra `exports`, `requires` và các qualified exports/opens nếu có.

Có thể liệt kê nội dung JAR:

~~~bash
jar --list --file dist/com.acme.payment.api.jar
~~~

Với explicit modular JAR thông thường, cần có `module-info.class` ở root:

~~~text
module-info.class
com/acme/payment/api/PaymentProcessor.class
~~~

Nếu JAR không có descriptor tường minh, việc đặt nó trên module path có thể khiến nó trở thành automatic module. Khi ấy contract readability/export khác với explicit module; README phải mô tả đúng loại module đang phát hành.

## 18. Xem module từ góc nhìn Java launcher

Đối với các module đã build dưới thư mục `mods`, có thể chạy:

~~~bash
java --module-path mods \
  --describe-module com.acme.payment.api
~~~

Hoặc:

~~~bash
java --module-path mods \
  --describe-module com.acme.payment.card
~~~

Khi muốn biết những module nào đang có thể được launcher quan sát:

~~~bash
java --module-path mods --list-modules
~~~

Và để xem quá trình phân giải module lúc chạy ứng dụng:

~~~bash
java --show-module-resolution \
  --module-path mods \
  --add-modules com.acme.payment.card \
  -m com.acme.payment.checkout/com.acme.payment.checkout.Main
~~~

Phân biệt:

- `jar --describe-module`: mô tả một artifact JAR cụ thể.
- `java --describe-module`: mô tả một observable module theo module path/runtime hiện tại.
- `--show-module-resolution`: quan sát module graph được resolve khi khởi chạy ứng dụng.

README nên chỉ rõ lệnh nào dành cho mục đích nào. Mô tả thành công một module không tự chứng minh provider đã được chọn hoặc chương trình đã chạy đúng.

## 19. Tránh tài liệu gây hiểu nhầm về encapsulation

Một số phát biểu cần tránh:

| Phát biểu dễ gây sai | Diễn đạt phù hợp |
|---|---|
| “Có `requires` là dùng được mọi class của dependency” | `requires` tạo readability; package vẫn phải export thích hợp |
| “`exports` công khai cả module” | `exports` công bố package cụ thể, không đệ quy |
| “Class `public` trong package internal luôn dùng được” | Named module khác vẫn chịu ràng buộc exports |
| “`uses` bảo đảm có provider” | `uses` chỉ khai báo nhu cầu dùng service |
| “`provides` luôn khiến provider được chạy” | Provider phải nằm trong configuration/layer và được ServiceLoader khởi tạo khi cần |
| “Provider package phải `exports` cho consumer” | Với `provides` hợp lệ, không cần export implementation package chỉ để service loading |
| “`opens` giống `exports`” | `opens` phục vụ deep reflection, còn `exports` phục vụ truy cập Java thông thường |
| “Tên JAR chính là tên module” | Explicit module name lấy từ descriptor; automatic module có quy tắc đặt tên riêng |

Ngôn ngữ trong tài liệu cần phân biệt hành vi compiler, module resolver và ServiceLoader. Đây là những giai đoạn khác nhau.

## 20. Ghi rõ thay đổi phá vỡ compatibility của module contract

Không phải mọi thay đổi `module-info.java` đều vô hại.

Ví dụ các thay đổi có thể ảnh hưởng consumer:

- Đổi tên module được dùng trong `requires`.
- Xóa một `exports` hoặc chuyển export vô điều kiện sang qualified exports.
- Đổi tên package API được export.
- Thay `requires transitive` thành `requires` khi consumer đang dựa vào readability truyền tiếp.
- Xóa hoặc đổi service contract được công bố.
- Xóa provider mà consumer đang kỳ vọng sẽ có tại runtime.
- Thay đổi constructor/provider method khiến service instantiation không còn tương thích.

README và release notes nên ghi:

1. Module name cũ và mới, nếu có.
2. Những package đã thêm/bỏ export.
3. Những dependency thêm/bỏ hoặc thay đổi modifier.
4. Những service `uses`/`provides` mới hoặc bị loại bỏ.
5. Hành động migration mà consumer hoặc provider author cần thực hiện.

Một release có cùng tên artifact nhưng đổi module name có thể buộc mọi consumer named module sửa descriptor; không nên chỉ ghi “internal refactor”.

## 21. Tổ chức tài liệu cho multi-module repository

Nếu repository có nhiều module:

~~~text
payment/
├── payment-api/
├── payment-card/
├── payment-wallet/
└── checkout-example/
~~~

Nên chia tài liệu thành hai cấp:

**README cấp repository:** trình bày module graph tổng quan, phiên bản Java, dependency quản lý chung, cách build và cách chạy ví dụ.

**README cấp module:** mô tả cụ thể `module-info.java`, exported packages, service contract, implementation, dependency module và hướng dẫn cho consumer/provider.

Ví dụ bảng tổng quan:

| Module | Vai trò | Requires | Exports | Uses | Provides |
|---|---|---|---|---|---|
| `com.acme.payment.api` | Contract | `java.base` ngầm định | `com.acme.payment.api` | Không | Không |
| `com.acme.payment.card` | Provider | `com.acme.payment.api` | Không cần export implementation | Không | `PaymentProcessor` |
| `com.acme.payment.checkout` | Consumer | `com.acme.payment.api` | Không bắt buộc | `PaymentProcessor` | Không |

Có thể tạo sơ đồ phụ thuộc, nhưng sơ đồ phải thống nhất với descriptor được build. Nếu có custom `ModuleLayer`, nên bổ sung hình minh họa layer cha/con và nơi provider được nạp.

## 22. Mẫu mục README dành cho một named module

Dưới đây là cấu trúc có thể dùng lại:

~~~markdown
# com.acme.payment.card

## Thông tin module
- Module name: com.acme.payment.card
- Artifact: com.acme:payment-card:1.2.0
- Java baseline: 21
- Loại: explicit named module

## Module descriptor
~~~java
module com.acme.payment.card {
    requires com.acme.payment.api;
    provides com.acme.payment.api.PaymentProcessor
        with com.acme.payment.card.internal.CardPaymentProcessor;
}
~~~

## Requires
- com.acme.payment.api: service contract bắt buộc.

## Exports
- Không export implementation package.

## Uses
- Module này không gọi ServiceLoader cho contract khác.

## Provides
- Service: com.acme.payment.api.PaymentProcessor
- Implementation: com.acme.payment.card.internal.CardPaymentProcessor

## Tích hợp
- Consumer cần requires com.acme.payment.api và uses PaymentProcessor.
- Provider module cần được đưa vào runtime configuration.

## Kiểm tra
- jar --describe-module --file payment-card.jar
- java --module-path mods --describe-module com.acme.payment.card
~~~

Trong Markdown thực tế, nếu viết code fence lồng nhau, dùng fence ngoài dài hơn fence trong hoặc tách các khối code độc lập để nội dung hiển thị đúng.

Mẫu này giúp người đọc không phải tự tìm hiểu service contract trong source, đồng thời giảm nguy cơ tài liệu chỉ mô tả class mà bỏ qua module boundary.

## 23. Các bước kiểm tra trước khi phát hành tài liệu

Một quy trình đồng bộ tài liệu với artifact:

1. Build sạch các module với JDK mục tiêu.
2. Xác nhận tên module và descriptor của từng JAR cuối.
3. Liệt kê các `requires`, bao gồm `transitive` và `static` nếu có.
4. Đối chiếu danh sách `exports` với các public API được hứa hỗ trợ.
5. Kiểm tra qualified exports/opens và các module đích.
6. Liệt kê service `uses` của consumer.
7. Liệt kê service `provides` và provider implementation.
8. Chạy consumer example trên module path thay vì chỉ classpath.
9. Nếu có provider, chạy ví dụ ServiceLoader với provider module đã resolve.
10. Đối chiếu Maven/Gradle metadata với tên module và dependency thực tế.
11. Cập nhật README và migration notes khi descriptor thay đổi.
12. Publish artifact và tài liệu theo cùng phiên bản.

Khi phải hỗ trợ nhiều phiên bản JDK, ghi rõ khác biệt nếu module graph hoặc các dependency JDK thay đổi. Đừng sao chép cứng kết quả của một JDK rồi khẳng định nó đúng cho mọi runtime.

## 24. Checklist ngắn cho người viết README

- [ ] Ghi đúng **module name** chứ không chỉ tên artifact/JAR.
- [ ] Cung cấp ví dụ `module-info.java` dùng được.
- [ ] Giải thích từng `requires` và phân biệt `transitive`/`static` khi có.
- [ ] Liệt kê rõ package nào `exports`, package nào là internal.
- [ ] Nếu có qualified exports, ghi rõ module đích.
- [ ] Nếu có `opens`, ghi rõ mục đích reflection và module được cấp quyền.
- [ ] Nếu có `uses`, ghi service type và cách consumer xử lý thiếu provider.
- [ ] Nếu có `provides`, ghi service interface và implementation type.
- [ ] Chỉ dẫn cách đưa provider module vào module configuration.
- [ ] Không yêu cầu consumer import provider implementation package nếu thiết kế dựa trên ServiceLoader.
- [ ] Ghi Java baseline, dependency artifact và lệnh chạy mẫu.
- [ ] Có lệnh `jar --describe-module` để kiểm tra artifact cuối.
- [ ] Có ví dụ consumer độc lập để xác nhận contract.
- [ ] Ghi rõ các thay đổi module contract trong release notes.

## 25. Ghi nhớ

Đối với một modular library, tài liệu tốt phải phản ánh **module contract**, không chỉ liệt kê class trong JAR.

- **`requires`:** module đọc những module nào, dependency nào truyền tiếp tới consumer, dependency nào chỉ cần ở compile.
- **`exports`:** package nào được hỗ trợ như public API và package nào bị giữ nội bộ.
- **`uses`:** module cần tìm service contract nào và xử lý provider discovery ra sao.
- **`provides`:** module đăng ký implementation nào, provider được đưa vào runtime như thế nào.

Hãy viết README từ góc nhìn người dùng: **cần thêm artifact nào, khai báo module-info.java ra sao, import package nào, tìm provider bằng cách nào và kiểm tra lỗi ở đâu**. Khi những thông tin này khớp với `module-info.class` đã phát hành, người dùng có thể tích hợp module ổn định hơn, đồng thời ranh giới API/implementation được giữ rõ ràng.
