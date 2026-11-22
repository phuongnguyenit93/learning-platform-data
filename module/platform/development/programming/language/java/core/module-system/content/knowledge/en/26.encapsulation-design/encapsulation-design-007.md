# Đặt type public tại package phù hợp

Trong Java Platform Module System (JPMS), việc đặt một type có modifier public vào package nào là quyết định thiết kế API chứ không chỉ là cách tổ chức thư mục. Một class có thể public đối với mã Java trong cùng mô-đun, nhưng vẫn không thể được mô-đun khác import nếu package chứa nó không được exports. Ngược lại, khi một package được export, mọi top-level type public đủ điều kiện trong package đó có thể trở thành một phần của bề mặt API nhìn thấy từ bên ngoài.

Để duy trì strong encapsulation, hãy tách rõ **package dành cho hợp đồng công khai** và **package dành cho implementation**. Chỉ export package chứa những kiểu thực sự được cam kết cho người sử dụng; giữ class hỗ trợ, adapter, cache, mapper và thuật toán nội bộ trong package không export.

Bài học này giải thích cách chọn package cho public type, cách tránh lộ implementation qua chữ ký public, và cách sắp xếp module-info.java để API ổn định khi dự án phát triển.

## 1. Public trong Java chưa đủ để trở thành API của module

Java có hai tầng liên quan đến khả năng truy cập:

1. **Java language access:** public, protected, package-private và private kiểm soát quyền truy cập ở cấp class và member.
2. **JPMS module access:** requires quyết định readability, exports quyết định package được dùng như API thông thường, còn opens quyết định quyền deep reflection ở runtime.

Giả sử module có descriptor:

~~~java
module com.example.catalog {
    exports com.example.catalog.api;
}
~~~

Và chứa hai lớp:

~~~java
package com.example.catalog.api;

public interface CatalogService {
    String productName(String sku);
}
~~~

~~~java
package com.example.catalog.internal;

public final class DefaultCatalogService
        implements com.example.catalog.api.CatalogService {
    @Override
    public String productName(String sku) {
        return "Product " + sku;
    }
}
~~~

DefaultCatalogService là public, nhưng package com.example.catalog.internal không được export. Mã trong mô-đun khác không được phép import lớp này như API public thông thường, dù modifier của lớp là public.

Trong khi đó CatalogService nằm trong package được export, nên mô-đun có readability phù hợp có thể tham chiếu interface này.

Đây là điểm thiết yếu: **public type và exported package là hai điều kiện khác nhau**.

## 2. Package là ranh giới export, không phải từng class

Trong module-info.java, JPMS không có chỉ thị export riêng một class:

~~~java
module com.example.catalog {
    exports com.example.catalog.api;
}
~~~

Chỉ thị exports mở khả năng truy cập các kiểu public trong cả package api. Nó không chỉ export một interface mà bạn đang quan tâm.

Nếu đặt một public implementation helper vào cùng package:

~~~java
package com.example.catalog.api;

public final class CacheResetUtility {
    public static void resetAll() {
        // Internal operation
    }
}
~~~

thì một mô-đun khác có thể nhìn thấy CacheResetUtility cùng với những API công khai khác, miễn là thỏa các quy tắc truy cập. Điều này không nhất thiết đồng nghĩa nhà phát hành cam kết hỗ trợ nó, nhưng về mặt cơ chế JPMS nó đã được đưa ra bề mặt truy cập.

Nếu class không dành cho consumer, có hai lựa chọn thường hợp lý:

- Chuyển class sang package không export, ví dụ com.example.catalog.internal.
- Nếu class chỉ được dùng trong cùng package, cân nhắc bỏ modifier public để nó trở thành package-private.

Không nên sử dụng public chỉ vì thuận tiện, rồi hy vọng module-info.java có thể giấu từng type nằm trong package đã export.

## 3. Thiết kế package từ góc nhìn của consumer

Khi lựa chọn package, hãy bắt đầu bằng câu hỏi: **mô-đun khác được phép phụ thuộc lâu dài vào những gì?**

Một API tốt thường gồm:

- Interface hoặc class đại diện cho hành vi nghiệp vụ được công bố.
- Kiểu đầu vào, đầu ra và exception ổn định.
- Factory hoặc entry point để tạo đối tượng nếu consumer không nên biết implementation.
- Annotation hoặc extension point mà consumer được phép sử dụng.

Những phần thường nên ở package nội bộ:

- Repository implementation, cache, mapper và helper.
- Cấu trúc dữ liệu phục vụ thuật toán nội bộ.
- Adapter tích hợp thư viện cụ thể.
- Code sinh tự động không được thiết kế thành hợp đồng.
- Class chứa logic wiring và cấu hình riêng của module.

Ví dụ bố cục:

~~~text
src/com.example.catalog/
├── module-info.java
└── com/example/catalog/
    ├── api/
    │   ├── CatalogService.java
    │   ├── ProductView.java
    │   └── CatalogServices.java
    ├── internal/
    │   ├── DefaultCatalogService.java
    │   └── ProductCache.java
    └── persistence/
        └── FileProductStore.java
~~~

Descriptor:

~~~java
module com.example.catalog {
    exports com.example.catalog.api;
}
~~~

Nhờ vậy module bên ngoài chỉ phụ thuộc vào com.example.catalog.api. Module sở hữu có thể thay cache hoặc persistence implementation mà không bắt consumer sửa import.

## 4. Tình huống thiết kế sai: implementation nằm trong package API

Giả sử dự án ban đầu chỉ có:

~~~text
com/example/payment/
├── PaymentService.java
├── PaymentServiceImpl.java
├── DatabaseConnectionHelper.java
└── RetryPolicy.java
~~~

Cả bốn type được khai báo public và package được export:

~~~java
module com.example.payment {
    exports com.example.payment;
}
~~~

Mọi type public trong package này đều được mô-đun khác nhìn thấy. Một consumer có thể bắt đầu tạo trực tiếp PaymentServiceImpl hoặc gọi DatabaseConnectionHelper.

Về sau, đội phát triển muốn đổi database hoặc kiến trúc retry. Việc thay thế implementation có thể làm vỡ mã consumer đã phụ thuộc vào những type không đáng lẽ là API.

Một cấu trúc phù hợp hơn:

~~~text
com/example/payment/
├── api/
│   ├── PaymentService.java
│   ├── PaymentRequest.java
│   └── PaymentServices.java
├── internal/
│   ├── DefaultPaymentService.java
│   └── RetryPolicy.java
└── persistence/
    └── DatabaseConnectionHelper.java
~~~

~~~java
module com.example.payment {
    exports com.example.payment.api;
}
~~~

Mục tiêu không phải giảm số type public bằng mọi giá, mà là tách rõ **public đối với code nội bộ** và **public API dành cho module khác**.

## 5. Public implementation ở package không export vẫn có ích

Đôi khi implementation cần được sử dụng từ một package khác trong cùng module. Khi đó class có thể phải public theo quy tắc ngôn ngữ Java.

Ví dụ:

~~~java
package com.example.payment.internal;

import com.example.payment.api.PaymentService;

public final class DefaultPaymentService implements PaymentService {
    @Override
    public String pay(String reference) {
        return "OK:" + reference;
    }
}
~~~

Và factory trong package api:

~~~java
package com.example.payment.api;

import com.example.payment.internal.DefaultPaymentService;

public final class PaymentServices {
    private PaymentServices() {
    }

    public static PaymentService create() {
        return new DefaultPaymentService();
    }
}
~~~

Dù DefaultPaymentService là public, nó không trở thành một kiểu mà consumer bên ngoài có thể import qua JPMS vì package internal không export.

Module khác chỉ dùng:

~~~java
import com.example.payment.api.PaymentService;
import com.example.payment.api.PaymentServices;

PaymentService service = PaymentServices.create();
System.out.println(service.pay("INV-001"));
~~~

Điều này giúp consumer phụ thuộc vào interface và factory, thay vì bị ràng buộc vào cách khởi tạo hoặc cách cài đặt hiện tại.

## 6. Chữ ký public phải dùng các kiểu consumer truy cập được

Một lỗi thiết kế phổ biến là đặt interface vào package đã export nhưng dùng một kiểu nội bộ trong public method signature.

Ví dụ:

~~~java
package com.example.order.api;

import com.example.order.internal.OrderData;

public interface OrderService {
    OrderData load(String id);
}
~~~

OrderData chỉ tồn tại trong package internal không export. Consumer có thể nhìn thấy interface OrderService nhưng gặp khó khăn hoặc lỗi compile khi muốn sử dụng kiểu trả về OrderData.

Cách cải thiện là đưa kiểu dữ liệu hợp đồng sang package API:

~~~java
package com.example.order.api;

public record OrderView(String id, String status) {
}
~~~

~~~java
package com.example.order.api;

public interface OrderService {
    OrderView load(String id);
}
~~~

Nếu implementation cần một cấu trúc OrderData riêng, hãy chuyển đổi sang OrderView tại ranh giới API.

Quy tắc này cũng áp dụng cho:

- Kiểu tham số của public method và public constructor.
- Kiểu trả về, generic type parameter và generic bound.
- Exception được công bố như một phần hợp đồng.
- Public field, superclass và interface mà consumer phải tham chiếu.
- Public nested type xuất hiện trong chữ ký dùng bên ngoài.

Không nên chỉ kiểm tra type được khai báo public; cần đọc cả **toàn bộ type graph xuất hiện trong API công khai**.

## 7. Thiết kế API DTO hoặc record

Kiểu dữ liệu xuất hiện trong hợp đồng nên được đặt ở package có tên và ý nghĩa rõ ràng, chẳng hạn api, model hoặc contract, tùy quy ước nhóm.

Ví dụ:

~~~java
package com.example.inventory.api;

public record ProductView(
        String sku,
        String displayName,
        int availableQuantity) {
}
~~~

~~~java
package com.example.inventory.api;

import java.util.Optional;

public interface InventoryService {
    Optional<ProductView> find(String sku);
}
~~~

Descriptor:

~~~java
module com.example.inventory {
    exports com.example.inventory.api;
}
~~~

Consumer có thể dùng ProductView mà không cần biết kiểu entity hoặc cache nội bộ.

Record thích hợp với dữ liệu bất biến và công khai theo giá trị khi nó đáp ứng yêu cầu nghiệp vụ. Tuy nhiên không phải mọi entity hoặc object phức tạp đều phải biến thành record. Mục tiêu là chọn kiểu hợp đồng ổn định, không lộ chi tiết persistence hoặc framework.

Khi thiết kế DTO, cần cân nhắc khả năng tương thích nếu thay đổi component hoặc constructor public. Đặt nó ở API package có nghĩa là những thay đổi sau này có thể ảnh hưởng đến consumer.

## 8. API package và internal package không nhất thiết có một tên cố định

Không có quy định bắt buộc mọi dự án đều phải dùng hậu tố .api hoặc .internal.

Các cách đặt tên đều có thể hợp lý:

~~~text
com.example.billing.api
com.example.billing.contract
com.example.billing.spi
com.example.billing.internal
com.example.billing.persistence
com.example.billing.adapter
~~~

Điều quan trọng là ngữ nghĩa rõ ràng:

- Package chứa type dành cho consumer cần được tài liệu hóa như hợp đồng.
- Package internal không nên export nếu module bên ngoài không cần dùng trực tiếp.
- Package spi dành cho Service Provider Interface nên được thiết kế cẩn thận vì provider bên ngoài có thể cần implement kiểu ở đó.
- Package model có thể là API hoặc nội bộ; không nên suy luận chỉ từ tên model.

Đừng biến tên package thành cơ chế kiểm soát truy cập duy nhất. Chính module-info.java mới xác định package nào được export ở cấp JPMS.

## 9. Khi API cần kiểu từ mô-đun khác

Public API có thể phụ thuộc vào một kiểu nằm trong một named module khác. Ví dụ thư viện catalog trả về kiểu Result từ mô-đun contract dùng chung.

Module contract:

~~~java
module com.example.contract {
    exports com.example.contract;
}
~~~

~~~java
package com.example.contract;

public record Result<T>(T value, boolean success) {
}
~~~

Module catalog:

~~~java
module com.example.catalog {
    requires transitive com.example.contract;
    exports com.example.catalog.api;
}
~~~

API:

~~~java
package com.example.catalog.api;

import com.example.contract.Result;

public interface CatalogService {
    Result<String> lookup(String sku);
}
~~~

requires transitive giúp module nào đọc com.example.catalog cũng có thể đọc com.example.contract theo quy tắc JPMS. Điều này phù hợp khi public API của catalog cần type từ contract.

Nếu catalog chỉ sử dụng một dependency trong implementation nội bộ và không lộ kiểu dependency ra hợp đồng công khai, requires thông thường thường phù hợp hơn requires transitive.

Không lạm dụng transitive cho mọi dependency. Nó làm tăng các quan hệ readability mà consumer nhận được và khiến dependency trở nên gắn chặt hơn với API module.

## 10. Qualified exports cho đối tác được chỉ định

Có những type không phải API chung cho tất cả consumer nhưng cần được một mô-đun tích hợp cụ thể sử dụng.

Ví dụ:

~~~java
module com.example.billing {
    exports com.example.billing.api;

    exports com.example.billing.integration
        to com.example.billing.bridge;
}
~~~

Package integration được export riêng cho com.example.billing.bridge, không phải cho mọi named module khác.

Qualified exports có thể hữu ích cho:

- Mô-đun adapter được quản lý cùng một sản phẩm.
- API giao tiếp giữa hai mô-đun trong một hệ thống lớn.
- Tích hợp đặc thù chưa muốn công bố rộng.

Tuy nhiên đây không phải ranh giới bảo mật chống lại mọi loại mã hoặc mọi cấu hình JVM. Nó là cơ chế điều khiển khả năng truy cập trong JPMS. Với API dành cho bên thứ ba, cần cân nhắc khả năng mở rộng danh sách module đích và tính ổn định của hợp đồng.

Không nên dùng qualified exports như cách che giấu một thiết kế package hỗn tạp, nơi hàng chục implementation helper đang nằm cùng API type. Tổ chức package tốt vẫn là nền tảng.

## 11. Opens không thay thế exports

Một framework serialization hoặc ORM có thể cần deep reflection vào field private của entity. Khi đó package chứa entity có thể cần opens:

~~~java
module com.example.billing {
    exports com.example.billing.api;

    opens com.example.billing.entity
        to com.example.persistence.framework;
}
~~~

Cách này cho phép framework thực hiện reflection sâu vào entity theo phạm vi module được chỉ định. Nó **không** làm package entity trở thành một package API thông thường để mọi client import.

Phân biệt:

| Chỉ thị | Mục đích |
| --- | --- |
| exports p | Cho phép sử dụng kiểu public của package p qua Java access thông thường. |
| exports p to m | Chỉ export package p cho module m. |
| opens p | Mở package p cho deep reflection tại runtime. |
| opens p to m | Mở package p cho deep reflection từ module m. |

Nếu client cần biên dịch mã gọi một public type, hãy xem requires và exports. Nếu framework cần đọc private state qua reflection, hãy xem opens.

Không export một package implementation chỉ vì serializer không truy cập được private field; cũng không open package API một cách không cần thiết chỉ để sửa lỗi import trong mã nguồn.

## 12. Public top-level type và Java language rules

Trong Java, một top-level type có thể public hoặc package-private. Với source file thông thường, tên file của public top-level class/interface phải phù hợp với tên type public.

Ví dụ:

~~~java
package com.example.catalog.internal;

final class CacheKey {
    private final String value;

    CacheKey(String value) {
        this.value = value;
    }
}
~~~

CacheKey không public nên chỉ các lớp trong cùng package có thể trực tiếp truy cập nó theo quy tắc package-private của Java.

Một class khác trong cùng module nhưng khác package sẽ không thể import CacheKey chỉ nhờ việc chúng nằm cùng module. **JPMS không loại bỏ các modifier truy cập của Java**.

Nếu implementation cần được nhiều package trong cùng module sử dụng, có thể tạo type public trong package không export, hoặc thiết kế một điểm truy cập nội bộ có kiểm soát. Cũng cần cân nhắc giữ API nội bộ nhỏ thay vì làm public mọi helper cho tiện.

## 13. Public nested type và enclosing type

Một nested class hoặc nested interface có thể public, nhưng quyền truy cập bên ngoài còn phụ thuộc vào enclosing type, package và module.

Ví dụ:

~~~java
package com.example.catalog.api;

public final class CatalogOptions {
    public enum Mode {
        STRICT,
        LENIENT
    }

    private CatalogOptions() {
    }
}
~~~

Nếu package api được export và các điều kiện readability phù hợp, consumer có thể dùng CatalogOptions.Mode.

Ngược lại, một public nested type nằm trong top-level type không truy cập được từ module khác cũng không tự trở thành API công khai hữu ích cho consumer.

Khi thiết kế nested type công khai, cần xem xét cách consumer đặt import và gọi API. Đừng xuất hiện một nested type nội bộ trong signature của API chỉ vì nó có modifier public.

## 14. Tránh split package giữa các named module

JPMS không phù hợp với việc nhiều named module cùng cung cấp cùng một package trong cùng module graph và môi trường nạp lớp liên quan. Việc chia một package giữa nhiều module có thể gây lỗi phân giải hoặc lỗi cấu hình.

Ví dụ thiết kế không nên:

~~~text
module com.example.catalog.api
└── package com.example.catalog.shared

module com.example.catalog.impl
└── package com.example.catalog.shared
~~~

Cần tổ chức thành các package riêng theo trách nhiệm:

~~~text
com.example.catalog.api
com.example.catalog.internal
com.example.catalog.persistence
~~~

Mỗi package thuộc một module thích hợp trong cấu hình. Nếu hai module cần cùng kiểu hợp đồng, cân nhắc đưa kiểu đó vào một module API dùng chung thay vì sao chép cùng một package giữa nhiều module.

Cách này còn giảm rủi ro class identity và xung đột dependency khi thêm plugin hoặc module layer.

## 15. Tránh API lộ class của framework

Một lỗi thiết kế khác là đặt class API ở package phù hợp nhưng để chữ ký phụ thuộc vào framework-specific type:

~~~java
package com.example.payment.api;

public interface PaymentService {
    FrameworkSession beginPayment();
}
~~~

Nếu FrameworkSession là chi tiết implementation của ORM hoặc HTTP framework, consumer có thể bị buộc phụ thuộc vào framework chỉ để gọi API nghiệp vụ.

Một hợp đồng độc lập hơn:

~~~java
package com.example.payment.api;

public record PaymentTicket(String reference, String status) {
}
~~~

~~~java
package com.example.payment.api;

public interface PaymentService {
    PaymentTicket beginPayment();
}
~~~

Implementation có thể chuyển đổi giữa PaymentTicket và đối tượng framework bên trong package internal.

Không phải lúc nào lộ kiểu bên ngoài cũng sai: thư viện chuyên cung cấp integration có thể cố ý công khai kiểu framework. Nhưng đây phải là lựa chọn thiết kế có chủ đích, được tài liệu hóa và quản lý compatibility.

## 16. API và SPI là hai bề mặt khác nhau

API phục vụ consumer; SPI phục vụ người cung cấp implementation hoặc plugin.

Ví dụ:

~~~text
com.example.report.api
com.example.report.spi
com.example.report.internal
~~~

Một interface SPI có thể được export để các module plugin implement:

~~~java
module com.example.report {
    exports com.example.report.api;
    exports com.example.report.spi;
    uses com.example.report.spi.ReportProvider;
}
~~~

Mô-đun provider có thể khai báo:

~~~java
module com.example.report.pdf {
    requires com.example.report;

    provides com.example.report.spi.ReportProvider
        with com.example.report.pdf.PdfReportProvider;
}
~~~

Mô-đun API có thể sử dụng ServiceLoader để khám phá provider. Lưu ý package chứa implementation PdfReportProvider không nhất thiết phải export chỉ để cung cấp provider qua provides.

Việc đặt SPI ở package riêng giúp giải thích đây là hợp đồng dành cho người mở rộng hệ thống, không phải mọi consumer đều cần dùng. Quy ước này cũng hỗ trợ tài liệu hóa và tiến hóa API rõ ràng hơn.

## 17. Thiết kế package cho thư viện dùng cả JPMS và classpath

Khi cùng một JAR có thể được sử dụng trên module path hoặc classpath, cần nhớ:

- Trên module path, JPMS áp dụng ranh giới exports/opens của named module.
- Trên classpath, các lớp thuộc unnamed module và ranh giới exports của modular descriptor không hoạt động theo cùng cơ chế như khi JAR là named module.
- Java modifier public/package-private vẫn được áp dụng trong cả hai mô hình.

Vì vậy, không nên xem một package không export là bí mật tuyệt đối trước mọi môi trường chạy. Mục tiêu của encapsulation design là **hợp đồng phụ thuộc rõ ràng và khả năng bảo trì**, không phải cô lập bảo mật đối với mã không đáng tin cậy trong cùng tiến trình.

Nếu thư viện được phát hành cho cả ứng dụng modular và non-modular, vẫn nên giữ thiết kế package API/internal rõ ràng. Tài liệu public API cần nhất quán, ngay cả khi classpath có khả năng truy cập rộng hơn.

## 18. Quy trình chuyển type public sang package phù hợp

Giả sử trước đây client dùng:

~~~java
import com.example.catalog.DefaultCatalogService;
~~~

Sau khi thiết kế lại, đội phát triển muốn consumer phụ thuộc vào CatalogService trong package api.

Đây có thể là thay đổi không tương thích đối với code client hiện hữu. Vì tên đầy đủ của type bao gồm package, việc di chuyển type sang package mới làm thay đổi binary name của nó.

Một quy trình an toàn:

1. Xác định type nào là API thực sự và type nào là implementation.
2. Kiểm tra tất cả public method, constructor, generic type và exception trong hợp đồng.
3. Thiết kế package api hoặc contract và module exports tương ứng.
4. Đưa interface, DTO và factory công khai sang package mới.
5. Giữ implementation trong package internal không export.
6. Cập nhật client dùng API mới.
7. Nếu thư viện đã có người dùng, cân nhắc adapter hoặc type chuyển tiếp có deprecated để quản lý compatibility.
8. Biên dịch và chạy consumer ở module riêng để xác nhận hợp đồng sử dụng được.

Với thư viện đã phát hành, không nên chuyển package một cách âm thầm. Source compatibility và binary compatibility đều cần được cân nhắc.

Không phải type nào cũng nên đổi package ngay. Có thể duy trì public facade cũ trong thời gian chuyển tiếp rồi gỡ bỏ theo chính sách versioning của dự án.

## 19. Ví dụ hoàn chỉnh: tách API và implementation

Bố cục dự án:

~~~text
src/
├── com.example.inventory/
│   ├── module-info.java
│   └── com/example/inventory/
│       ├── api/
│       │   ├── InventoryService.java
│       │   ├── ProductView.java
│       │   └── InventoryServices.java
│       └── internal/
│           └── InMemoryInventoryService.java
└── com.example.cli/
    ├── module-info.java
    └── com/example/cli/Main.java
~~~

Descriptor của inventory:

~~~java
module com.example.inventory {
    exports com.example.inventory.api;
}
~~~

DTO public:

~~~java
package com.example.inventory.api;

public record ProductView(String sku, String name) {
}
~~~

Service interface:

~~~java
package com.example.inventory.api;

import java.util.Optional;

public interface InventoryService {
    Optional<ProductView> find(String sku);
}
~~~

Implementation ở package internal:

~~~java
package com.example.inventory.internal;

import com.example.inventory.api.InventoryService;
import com.example.inventory.api.ProductView;
import java.util.Optional;

public final class InMemoryInventoryService
        implements InventoryService {

    @Override
    public Optional<ProductView> find(String sku) {
        if ("P-100".equals(sku)) {
            return Optional.of(new ProductView("P-100", "Notebook"));
        }
        return Optional.empty();
    }
}
~~~

Factory ở package API:

~~~java
package com.example.inventory.api;

import com.example.inventory.internal.InMemoryInventoryService;

public final class InventoryServices {
    private InventoryServices() {
    }

    public static InventoryService inMemory() {
        return new InMemoryInventoryService();
    }
}
~~~

Descriptor client:

~~~java
module com.example.cli {
    requires com.example.inventory;
}
~~~

Client:

~~~java
package com.example.cli;

import com.example.inventory.api.InventoryService;
import com.example.inventory.api.InventoryServices;

public class Main {
    public static void main(String[] args) {
        InventoryService inventory = InventoryServices.inMemory();
        System.out.println(inventory.find("P-100"));
    }
}
~~~

Client chỉ import kiểu từ package api. Việc implementation là public không làm nó trở thành API xuất bản vì package internal không được export.

## 20. Biên dịch ví dụ modular

Với cấu trúc module-source-path như trên, có thể biên dịch:

~~~bash
javac --module-source-path src \
    -d out \
    -m com.example.inventory,com.example.cli
~~~

Chạy ứng dụng:

~~~bash
java --module-path out \
    -m com.example.cli/com.example.cli.Main
~~~

Trên Windows, có thể dùng lệnh một dòng:

~~~powershell
javac --module-source-path src -d out -m com.example.inventory,com.example.cli
java --module-path out -m com.example.cli/com.example.cli.Main
~~~

Nếu client thử import trực tiếp com.example.inventory.internal.InMemoryInventoryService, compiler của ứng dụng modular sẽ từ chối truy cập package internal vì package này không được export cho com.example.cli.

Đây là cách kiểm tra thực tế xem ranh giới API có tương ứng với module descriptor hay không.

## 21. Công cụ hỗ trợ kiểm tra API module

Một số công cụ trong JDK:

~~~bash
jar --describe-module --file libs/inventory.jar
~~~

Lệnh cho biết module descriptor của JAR, gồm tên module và các exports tương ứng.

~~~bash
java --describe-module java.sql
~~~

Lệnh mô tả module hệ thống java.sql, hữu ích để quan sát cách một module công bố package.

~~~bash
jdeps --module-path libs --check com.example.inventory
~~~

jdeps hỗ trợ phân tích requires và dependency liên quan đến module descriptor. Tùy cách đóng gói, cần truyền đúng đường dẫn module hoặc JAR.

Các công cụ này giúp tìm tên mô-đun và những package được export. Tuy nhiên, quyết định type nào nên trở thành public API vẫn phải dựa trên hợp đồng sử dụng và yêu cầu kiến trúc.

## 22. Lỗi thường gặp trong encapsulation design

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Public type không import được từ module khác | Package chứa type không được export hoặc thiếu readability | Kiểm tra requires và exports; chỉ export nếu type thực sự là API. |
| Consumer import được implementation helper | Helper public nằm trong package đã export | Chuyển helper sang package không export hoặc giảm visibility. |
| API method dùng kiểu internal trong signature | Hợp đồng lộ kiểu consumer không truy cập được | Dùng DTO/interface công khai trong package API. |
| Package conflict khi ghép module | Split package hoặc trùng package trong cấu hình không phù hợp | Tách package theo mô-đun và dùng một module contract chung. |
| Framework reflection lỗi | Package cần deep reflection nhưng chưa được opens | Cấp qualified opens đúng package cho framework nếu thật sự cần. |
| Thay package làm code client không biên dịch | Binary name/import của public type đã đổi | Quản lý migration và compatibility có chủ đích. |
| Chỉ đặt tên package internal nhưng vẫn bị consumer dùng trên classpath | Tên package không tự tạo quyền truy cập | Tách hợp đồng rõ ràng, kiểm soát qua modifier và exports khi chạy modular. |

## 23. Nguyên tắc chốt khi đặt public type

- Đặt interface, DTO, factory và exception công khai vào package phù hợp với hợp đồng của module.
- Chỉ export package dành cho consumer, không export toàn bộ module vì thuận tiện.
- Không để public signature cần đến các type trong package không export.
- Kiểm tra dependency xuất hiện trong public signature và cân nhắc requires transitive nếu API cần chuyển tiếp readability.
- Giữ implementation, cache, mapper và persistence helper trong package không export.
- Có thể dùng public implementation trong package internal nếu nhiều package trong cùng module thực sự cần.
- Dùng qualified exports cho API tích hợp có phạm vi đích rõ ràng.
- Dùng opens cho deep reflection; không coi opens là cách công bố API thông thường.
- Tránh split package giữa các named module trong cùng cấu hình.
- Xem di chuyển public type giữa package là một thay đổi hợp đồng cần quản lý tương thích.

## 24. Câu hỏi tự kiểm tra

**Câu 1:** Một class public nằm trong com.example.billing.internal, nhưng module chỉ exports com.example.billing.api. Mô-đun khác có được import class internal đó không?

Không theo truy cập JPMS thông thường. Modifier public của class không thay thế việc package được export.

**Câu 2:** Nếu một package đã export có ba class public, JPMS có chỉ định export riêng đúng một class trong đó không?

Không. exports áp dụng cho package. Cần tổ chức lại package hoặc thay visibility nếu chỉ muốn công bố một phần.

**Câu 3:** Một interface API trả về kiểu InternalOrder không được export. Thiết kế có vấn đề gì?

Consumer có thể không sử dụng được kiểu trong chữ ký. Nên công bố một interface hoặc DTO hợp đồng ở package API và chuyển đổi từ internal type bên trong module.

**Câu 4:** Package chứa entity cần ORM đọc private field. Nên thêm exports hay opens?

Khi chỉ cần deep reflection, opens có phạm vi cho module ORM thường phù hợp; exports dành cho truy cập API public thông thường.

**Câu 5:** Khi nào dùng requires transitive?

Khi module công khai API phụ thuộc vào kiểu từ mô-đun khác và muốn consumer đọc được dependency đó qua hợp đồng module. Nếu dependency chỉ là chi tiết implementation, requires thông thường thường phù hợp hơn.

**Câu 6:** Một class public trong package internal có phải luôn là lỗi thiết kế không?

Không. Nó có thể cần được gọi từ package khác trong cùng module. Điều quan trọng là package internal không được export cho consumer bên ngoài nếu class không thuộc hợp đồng API.

**Câu 7:** Tại sao đổi package của public type có thể phá tương thích?

Vì tên đầy đủ của type bao gồm tên package. Đổi package làm thay đổi tên mà source code và bytecode client tham chiếu, nên cần chiến lược migration.
