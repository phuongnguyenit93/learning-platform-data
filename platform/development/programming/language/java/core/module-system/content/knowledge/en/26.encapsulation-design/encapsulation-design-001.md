# Chia package theo API và implementation

## 1. Mục tiêu của việc tách API và implementation

Java Platform Module System (JPMS) cho phép một module công bố chọn lọc các package qua chỉ thị `exports`. Nhờ vậy, tác giả module có thể phân biệt phần **contract công khai** mà ứng dụng bên ngoài được phép sử dụng với phần **implementation nội bộ** có thể thay đổi mà không phá vỡ code consumer.

Nếu đặt API và implementation vào cùng một package đã export, mọi public type trong package đều có thể được consumer tham chiếu theo các quy tắc truy cập Java và JPMS. Điều này khiến consumer dễ phụ thuộc trực tiếp vào các class mà nhà phát triển chỉ định dùng nội bộ.

Ví dụ cấu trúc dễ tạo coupling:

~~~text
com.acme.inventory/
├── InventoryService.java
├── JdbcInventoryService.java
├── ProductRepository.java
└── ConnectionFactory.java
~~~

Khi descriptor khai báo:

~~~java
module com.acme.inventory {
    exports com.acme.inventory;
}
~~~

cả `InventoryService` lẫn những implementation class `public` trong package này đều thuộc phạm vi export. JPMS không có lệnh `exports` theo từng class riêng lẻ.

Cách tổ chức phù hợp hơn:

~~~text
com.acme.inventory.api
com.acme.inventory.internal
~~~

Và:

~~~java
module com.acme.inventory {
    exports com.acme.inventory.api;
}
~~~

Consumer chỉ cần phụ thuộc vào contract. Implementation có thể được thay thế mà vẫn giữ nguyên API.

## 2. Phân loại package theo trách nhiệm

Có thể bắt đầu bằng những nhóm sau:

| Nhóm | Vai trò | Ví dụ |
|---|---|---|
| API | Contract cho code sử dụng module | `com.acme.inventory.api` |
| Implementation | Class triển khai contract, thuật toán nội bộ | `com.acme.inventory.internal` |
| Persistence | Repository, database mapping, JDBC adapter | `com.acme.inventory.internal.persistence` |
| SPI | Contract cho người viết provider/extension | `com.acme.inventory.spi` |
| Integration | Contract/adapter dùng cho tích hợp chuyên biệt | `com.acme.inventory.integration` |

Một API package có thể chứa interface, abstract class, record/DTO, enum, exception công khai và một facade hoặc factory. Không phải tất cả public API đều phải là interface.

Implementation package thường chứa class cụ thể, cache, mapper, connection factory, repository, adapter và helper mà consumer không cần biết.

Các tên `api`, `spi`, `internal` chỉ là quy ước đặt tên. **Ranh giới thật sự do module descriptor và các quy tắc access của Java quyết định.** Đặt package tên `internal` nhưng vẫn `exports` nó thì JPMS vẫn cho phép truy cập theo quyền export.

## 3. Một module chứa cả API và implementation

Với thư viện nhỏ, chưa nhất thiết phải tách thành hai module. Có thể tách package ngay trong một module:

~~~text
inventory/
└── src/main/java/
    ├── module-info.java
    └── com/acme/inventory/
        ├── api/
        │   ├── InventoryService.java
        │   └── InventoryServices.java
        └── internal/
            └── InMemoryInventoryService.java
~~~

Descriptor:

~~~java
module com.acme.inventory {
    exports com.acme.inventory.api;
}
~~~

Contract công khai:

~~~java
package com.acme.inventory.api;

public interface InventoryService {
    String findName(String sku);
}
~~~

Implementation nội bộ:

~~~java
package com.acme.inventory.internal;

import com.acme.inventory.api.InventoryService;
import java.util.Map;

public final class InMemoryInventoryService
        implements InventoryService {

    private final Map<String, String> products =
            Map.of("SKU-1", "Notebook", "SKU-2", "Keyboard");

    @Override
    public String findName(String sku) {
        return products.getOrDefault(sku, "Not found");
    }
}
~~~

Factory công khai:

~~~java
package com.acme.inventory.api;

import com.acme.inventory.internal.InMemoryInventoryService;

public final class InventoryServices {

    private InventoryServices() {
    }

    public static InventoryService createDefault() {
        return new InMemoryInventoryService();
    }
}
~~~

Trong cùng một named module, code ở các package khác nhau vẫn có thể dùng public class nội bộ theo quy tắc Java. Điều đó không có nghĩa các module consumer bên ngoài được phép truy cập package internal.

Factory ở ví dụ này làm nhiệm vụ wiring. Trong kiến trúc lớn, có thể đặt việc lựa chọn implementation ở một composition root riêng để API module không phụ thuộc ngược vào implementation.

## 4. Consumer chỉ nhìn thấy contract

Module consumer:

~~~java
module com.acme.checkout {
    requires com.acme.inventory;
}
~~~

Ứng dụng:

~~~java
package com.acme.checkout;

import com.acme.inventory.api.InventoryService;
import com.acme.inventory.api.InventoryServices;

public final class Main {

    public static void main(String[] args) {
        InventoryService service =
                InventoryServices.createDefault();

        System.out.println(service.findName("SKU-1"));
    }
}
~~~

Consumer không import implementation class. Nó chỉ sử dụng type có trong API package đã export.

Nếu consumer thử:

~~~java
import com.acme.inventory.internal.InMemoryInventoryService;
~~~

compiler có thể báo:

~~~text
package com.acme.inventory.internal is not visible
(package com.acme.inventory.internal is declared in module
 com.acme.inventory, which does not export it)
~~~

Thông báo này minh họa sự khác biệt giữa:

- `public`: khả năng truy cập type theo Java language rules.
- `requires`: khả năng đọc module dependency.
- `exports`: khả năng truy cập public types của một package qua module boundary.

Dù `InMemoryInventoryService` là `public`, một named module khác vẫn không thể dùng nó như public API khi package chứa class không được export.

## 5. exports không áp dụng đệ quy

Nếu descriptor khai báo:

~~~java
module com.acme.inventory {
    exports com.acme.inventory.api;
}
~~~

thì package `com.acme.inventory.api.internal` **không tự động được export**. Java không xem subpackage là một phần của package cha về quyền truy cập.

Tương tự, `exports com.acme.inventory` không làm mọi package có prefix `com.acme.inventory.*` được export.

Muốn export nhiều package, phải nêu từng package:

~~~java
module com.acme.inventory {
    exports com.acme.inventory.api;
    exports com.acme.inventory.events;
}
~~~

Không có cú pháp wildcard:

~~~java
// Sai cú pháp:
exports com.acme.inventory.*;
~~~

Vì JPMS export ở cấp package, hãy xác định ngay từ đầu package nào chứa những public type thật sự được hỗ trợ lâu dài. Không đặt implementation class vào package API rồi trông chờ một keyword khác để ẩn chúng.

## 6. Tránh làm rò rỉ implementation qua chữ ký công khai

Một lỗi thiết kế tinh vi là đặt interface trong API package nhưng để method trả về kiểu thuộc implementation package:

~~~java
package com.acme.inventory.api;

import com.acme.inventory.internal.SqlProductEntity;

public interface InventoryService {
    SqlProductEntity find(String sku);
}
~~~

Dù package API đã được export, consumer vẫn bị ràng buộc vào `SqlProductEntity`, một type nội bộ không export.

Cách phù hợp hơn là định nghĩa dữ liệu trao đổi trong API:

~~~java
package com.acme.inventory.api;

public record ProductView(String sku, String name) {
}
~~~

Sau đó:

~~~java
package com.acme.inventory.api;

import java.util.Optional;

public interface InventoryService {
    Optional<ProductView> find(String sku);
}
~~~

Implementation chuyển database entity sang `ProductView` trước khi trả kết quả.

Khi đánh giá một public API, kiểm tra:

1. Kiểu trả về và parameter types.
2. Generic arguments, ví dụ `List<ProductView>`.
3. Checked exception trong `throws`.
4. Superclass/interface mà public type kế thừa.
5. Annotation và những kiểu khác nằm trong contract mà consumer cần biên dịch cùng.

Nếu API trả về `List<SqlProductEntity>` trong khi entity chỉ dành cho persistence, việc thay ORM hoặc database có thể phá vỡ consumer. API ổn định nên tránh lộ những quyết định triển khai này.

## 7. Hướng phụ thuộc giữa API và implementation

Một thiết kế dễ bảo trì thường tuân theo:

~~~text
consumer  ----->  API contract  <-----  implementation
~~~

Ý nghĩa:

- Consumer biết contract, không cần biết implementation cụ thể.
- Implementation triển khai contract.
- Một composition root, factory hoặc service-discovery mechanism quyết định implementation nào được dùng.

Trong single-module design, factory nằm trong API package có thể sử dụng implementation ở cùng module. Với hệ thống cần nhiều implementation thay thế, mô hình nhiều module thường rõ ràng hơn.

Không nên để API module `requires` implementation module chỉ để khởi tạo một object cụ thể. Nếu cần wiring, đưa trách nhiệm chọn provider sang host/composition module hoặc dùng `ServiceLoader`.

## 8. Khi nào nên tách thành API module và implementation module?

Tách module là lựa chọn phù hợp khi:

- Nhiều team hoặc hệ thống khác nhau cùng sử dụng một contract.
- Có nhiều backend thay thế: file, database, cloud storage hoặc in-memory.
- Ứng dụng cần plugin hoặc extension động.
- Implementation có dependency nặng mà API không nên mang theo.
- Muốn phát hành API và implementation theo vòng đời/version riêng.

Ví dụ cấu trúc:

~~~text
src/
├── com.acme.inventory.api/
│   ├── module-info.java
│   └── com/acme/inventory/api/InventoryService.java
├── com.acme.inventory.provider/
│   ├── module-info.java
│   └── com/acme/inventory/provider/internal/FileInventoryService.java
└── com.acme.checkout/
    ├── module-info.java
    └── com/acme/checkout/Main.java
~~~

Điểm quan trọng là mỗi module sở hữu package riêng. Không sao chép API class vào từng provider JAR vì như vậy có thể tạo split package hoặc class identity khác nhau khi dùng class loader/layer riêng.

## 9. Public API module

Descriptor:

~~~java
module com.acme.inventory.api {
    exports com.acme.inventory.api;
}
~~~

Service contract:

~~~java
package com.acme.inventory.api;

public interface InventoryService {
    String findName(String sku);
}
~~~

Module API không biết provider nào sẽ được cài. Nơi dùng interface chỉ cần `requires com.acme.inventory.api;`.

API package nên giữ số lượng dependency càng nhỏ và ổn định càng tốt. Nếu một public signature bắt buộc chứa type từ module khác, cân nhắc `requires transitive` khi điều đó phản ánh đúng contract; không thêm `transitive` cho mọi dependency nội bộ.

## 10. Provider module và ServiceLoader

Một provider module có thể đăng ký implementation qua JPMS service binding:

~~~java
module com.acme.inventory.provider {
    requires com.acme.inventory.api;

    provides com.acme.inventory.api.InventoryService
        with com.acme.inventory.provider.internal.FileInventoryService;
}
~~~

Implementation:

~~~java
package com.acme.inventory.provider.internal;

import com.acme.inventory.api.InventoryService;

public final class FileInventoryService
        implements InventoryService {

    public FileInventoryService() {
    }

    @Override
    public String findName(String sku) {
        return "File-backed: " + sku;
    }
}
~~~

Lưu ý:

- Provider class nằm trong package không export.
- `provides ... with ...` đăng ký implementation với service type.
- Consumer không phải import hoặc `requires` provider module cụ thể.
- Provider module cần `requires` API module để triển khai đúng service type.
- Việc `ServiceLoader` tạo provider hợp lệ không đòi hỏi provider implementation package phải được export.

Đối với named module sử dụng service, caller cần khai báo `uses` cho service type đó.

## 11. Consumer tìm implementation bằng service contract

Descriptor của consumer:

~~~java
module com.acme.checkout {
    requires com.acme.inventory.api;
    uses com.acme.inventory.api.InventoryService;
}
~~~

Code:

~~~java
package com.acme.checkout;

import com.acme.inventory.api.InventoryService;
import java.util.ServiceLoader;

public final class Main {

    public static void main(String[] args) {
        InventoryService service =
                ServiceLoader.load(InventoryService.class)
                        .findFirst()
                        .orElseThrow(() ->
                                new IllegalStateException(
                                        "No InventoryService provider"));

        System.out.println(service.findName("SKU-1"));
    }
}
~~~

Host thao tác qua `InventoryService`. Không cần thấy class `FileInventoryService`.

Khi chạy, provider cần được phân giải vào module configuration. Ví dụ, nếu muốn thêm provider như một root module rõ ràng:

~~~bash
java --module-path mods \
  --add-modules com.acme.inventory.provider \
  -m com.acme.checkout/com.acme.checkout.Main
~~~

Ví dụ này không áp đặt thứ tự provider khi có nhiều implementation. Nếu nghiệp vụ cần chọn backend theo tên hoặc priority, hãy định nghĩa cơ chế lựa chọn rõ ràng thay vì dựa vào thứ tự `ServiceLoader`.

## 12. Biên dịch ví dụ nhiều module

Với source layout `src/<module-name>/...` ở trên:

~~~bash
javac --module-source-path src \
  -d mods \
  -m com.acme.inventory.api,com.acme.inventory.provider,com.acme.checkout
~~~

Output:

~~~text
mods/
├── com.acme.inventory.api/
│   └── module-info.class
├── com.acme.inventory.provider/
│   └── module-info.class
└── com.acme.checkout/
    └── module-info.class
~~~

Các `.class` của API, provider và consumer được compiler đặt vào package path tương ứng dưới từng thư mục module.

Chạy:

~~~bash
java --module-path mods \
  --add-modules com.acme.inventory.provider \
  -m com.acme.checkout/com.acme.checkout.Main
~~~

Kết quả minh họa:

~~~text
File-backed: SKU-1
~~~

Lưu ý cách dùng `--module-source-path` phù hợp với source tree có một thư mục con mang tên mỗi module. Nếu dùng Maven/Gradle multi-project với `src/main/java` trong từng subproject, build tool thường quản lý output và module path thay vì dùng nguyên lệnh này.

## 13. SPI là contract cho provider, không phải implementation

Nếu hệ thống có một SPI rõ ràng, có thể phân chia:

~~~text
com.acme.payment.api
com.acme.payment.spi
com.acme.payment.provider.internal
~~~

Trong đó:

- `api` dành cho consumer gọi tính năng.
- `spi` dành cho provider hoặc extension triển khai chức năng.
- `provider.internal` chứa implementation mà consumer không nên import.

Một SPI được provider ở module khác triển khai cũng phải được export phù hợp:

~~~java
module com.acme.payment.api {
    exports com.acme.payment.api;
    exports com.acme.payment.spi;
}
~~~

Nếu SPI chỉ được sử dụng bởi những module cụ thể, có thể chọn qualified exports. Nhưng không nên giấu interface SPI trong package không export rồi mong module provider độc lập có thể implement nó bằng code thông thường.

Ngược lại, package chứa implementation class của provider thường không cần export. Phân biệt **provider contract** và **provider implementation** sẽ giúp service architecture có boundary rõ ràng.

## 14. Qualified exports cho package tích hợp chuyên biệt

Đôi khi một package chỉ cần được công bố cho một module adapter đã biết:

~~~java
module com.acme.inventory {
    exports com.acme.inventory.api;

    exports com.acme.inventory.integration
        to com.acme.inventory.adapter;
}
~~~

Khi đó, `com.acme.inventory.adapter` có thể truy cập các public type phù hợp trong package integration nếu cũng có readability. Những module khác không tự được cấp quyền đó.

Qualified exports hữu ích khi:

- Một package là contract nội bộ giữa một nhóm module.
- Không muốn biến package thành API công khai cho mọi consumer.
- Tên module đích được quản lý và ổn định.

Nếu phải liệt kê quá nhiều target module, cân nhắc tạo API module dành riêng cho integration hoặc thiết kế lại contract. Qualified exports không thay thế việc quản trị compatibility của API mà nó công bố.

## 15. opens dành cho reflection, không thay thế exports

Framework có thể cần deep reflection vào model/entity package dù code consumer không được import implementation.

Ví dụ:

~~~java
module com.acme.inventory {
    exports com.acme.inventory.api;

    opens com.acme.inventory.internal.model
        to com.fasterxml.jackson.databind;
}
~~~

Trong trường hợp trên:

- API package được export để consumer sử dụng các public type.
- Model package được open cho một module framework cụ thể.
- Open package không tự trở thành package được export cho truy cập Java thông thường.

Chỉ mở đúng package và đúng module thực hiện reflection. Nếu dùng JPA/Hibernate hoặc framework khác, module đích có thể không phải Jackson; cần xem runtime configuration thực tế.

Tránh dùng `open module` cho toàn bộ module khi chỉ có một package cần reflection. Điều đó làm rộng phạm vi truy cập reflective hơn nhu cầu ban đầu.

## 16. Tránh split package giữa các named module

Một sai lầm khi tách module là đưa cùng package `com.acme.inventory.common` vào cả API module và provider module:

~~~text
com.acme.inventory.api module:
    com.acme.inventory.common

com.acme.inventory.provider module:
    com.acme.inventory.common
~~~

Các cấu hình JPMS có quy tắc nghiêm ngặt đối với package trùng tên giữa các module. Việc tách một package thành hai JAR có thể gây lỗi compile hoặc module resolution khi các module cùng tham gia module graph.

Hãy phân chia package rõ ràng:

~~~text
com.acme.inventory.api
com.acme.inventory.provider.internal
~~~

Hai package có chung prefix nhưng khác tên đầy đủ là hợp lệ. Không có yêu cầu mỗi module phải sở hữu một namespace prefix duy nhất, nhưng **một package có cùng tên đầy đủ không nên bị chia giữa nhiều named module**.

Nếu cần type dùng chung, đặt chúng ở module API và để provider/consumer dùng cùng class identity, thay vì copy class.

## 17. Kiểm tra package đã export bằng công cụ JDK

Sau khi build modular JAR:

~~~bash
jar --describe-module --file build/libs/inventory.jar
~~~

Ví dụ output minh họa:

~~~text
com.acme.inventory
requires java.base mandated
exports com.acme.inventory.api
contains com.acme.inventory.internal
~~~

`contains` nếu được công cụ hiển thị nghĩa là package có trong module, không có nghĩa package đã export.

Với module output trên module path:

~~~bash
java --module-path mods \
  --describe-module com.acme.inventory
~~~

Có thể kiểm tra runtime Module API:

~~~java
Module provider = InventoryService.class.getModule();
Module consumer = Checkout.class.getModule();

boolean readsProvider = consumer.canRead(provider);

boolean apiExported =
        provider.isExported("com.acme.inventory.api", consumer);

boolean internalExported =
        provider.isExported("com.acme.inventory.internal", consumer);
~~~

Với explicit named modules, descriptor chỉ export `api` và không có launcher flag mở quyền bổ sung, `apiExported` thường là `true` và `internalExported` là `false`. `readsProvider` phụ thuộc quan hệ readability.

Một phép thử kiến trúc hữu ích là viết consumer cố import implementation class và xác nhận compiler từ chối. Đó là dấu hiệu ranh giới module đang hoạt động như mong muốn, không phải lỗi cần chữa bằng `--add-exports`.

## 18. Những phản ví dụ cần tránh

| Cách làm | Hậu quả |
|---|---|
| Đặt public implementation trong cùng package API | Consumer có thể tạo coupling trực tiếp với class cụ thể |
| Export package tên `internal` | Tên package không còn giúp thực thi encapsulation |
| Public API trả về persistence entity nội bộ | Contract bị ràng buộc với công nghệ lưu trữ |
| API module `requires` provider implementation module | Đảo ngược hướng dependency mong muốn |
| Sao chép API class vào từng plugin/provider JAR | Dễ gây split package hoặc class identity mismatch |
| Export implementation package chỉ để ServiceLoader phát hiện provider | Không cần khi khai báo `provides` phù hợp |
| Thêm `--add-exports` mọi nơi để consumer import internal | Làm suy yếu ranh giới và khó bảo trì |
| Dùng `open module` chỉ vì framework cần một model package | Mở quá rộng phạm vi deep reflection |

JPMS cung cấp công cụ thực thi boundary, nhưng việc lựa chọn đâu là contract lâu dài vẫn là trách nhiệm thiết kế của nhóm phát triển.

## 19. Quy trình chuyển từ thư viện legacy sang thiết kế có encapsulation

Khi modular hóa một thư viện Java cũ:

1. Liệt kê những package đang được các project bên ngoài import.
2. Xác định public contract cần được tiếp tục hỗ trợ.
3. Chuyển interface, DTO/record, enum và public exception vào package API.
4. Chuyển repository, database mapper, cache và adapter sang implementation package.
5. Kiểm tra chữ ký API để loại bỏ implementation type bị lộ.
6. Tạo `module-info.java` và chỉ export package được hỗ trợ.
7. Thêm qualified exports nếu có integration contract đặc biệt.
8. Mở package bằng `opens` khi framework thực sự cần deep reflection.
9. Nếu có nhiều implementation, cân nhắc API module + provider modules + `ServiceLoader`.
10. Biên dịch consumer trên module path để phát hiện import package nội bộ.
11. Dùng `jar --describe-module` xác nhận descriptor đã đóng gói.
12. Kiểm thử service discovery, reflection và những luồng nghiệp vụ sử dụng API.

Có thể dùng `jdeps` hỗ trợ phân tích dependency:

~~~bash
jdeps --list-deps build/libs/inventory.jar
~~~

Phân tích tĩnh chỉ là một phần. Các dependency dùng qua reflection, ServiceLoader hoặc class name trong configuration cần được kiểm tra bằng runtime test phù hợp.

## 20. Checklist trước khi phát hành

- [ ] API package chứa contract ổn định mà consumer cần.
- [ ] Implementation và helper nằm ngoài package được export.
- [ ] Descriptor chỉ export package thật sự được hỗ trợ.
- [ ] Public type không lộ kiểu internal trong method signature.
- [ ] Consumer chỉ `requires` module API cần thiết, không phụ thuộc implementation vô cớ.
- [ ] Provider module dùng chung service type của API module.
- [ ] `uses` và `provides` đúng khi dùng ServiceLoader.
- [ ] Không export provider implementation package chỉ vì service loading.
- [ ] Reflection chỉ được mở bằng `opens` đúng phạm vi.
- [ ] Không split package giữa các named module.
- [ ] Đã kiểm tra descriptor của modular JAR và module path.
- [ ] Đã thử biên dịch một consumer chỉ sử dụng contract công khai.

## 21. Ghi nhớ

**Chia package theo API và implementation là bước thực tế nhất để tận dụng strong encapsulation của JPMS.** Package API chứa những kiểu mà consumer được phép phụ thuộc; implementation package chứa chi tiết có thể thay đổi độc lập.

Với thư viện nhỏ, một module có thể chứa cả `api` và `internal` nhưng chỉ export `api`. Với plugin hoặc nhiều implementation thay thế nhau, có thể tách module API và provider, rồi dùng ServiceLoader để khám phá implementation mà không công bố class nội bộ.

Nguyên tắc chung: **consumer phụ thuộc contract, implementation triển khai contract, còn module descriptor công bố đúng các package cần thiết**. Tên package truyền đạt ý định, còn `requires`, `exports`, `opens` và quan hệ module graph thực thi ranh giới đó.
