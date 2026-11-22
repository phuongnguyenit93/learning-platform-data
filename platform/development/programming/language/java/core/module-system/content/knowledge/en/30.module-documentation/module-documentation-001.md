# Module Javadoc và package Javadoc

Trong Java Platform Module System (JPMS), **module descriptor** mô tả ranh giới kỹ thuật của module, còn **Javadoc** giúp người đọc hiểu mục đích, cách sử dụng, giới hạn và hợp đồng API. Hai cấp tài liệu thường quan trọng nhất là **module Javadoc** trong `module-info.java` và **package Javadoc** trong `package-info.java`.

Module Javadoc trả lời: *Module này có trách nhiệm gì, cung cấp API nào, phụ thuộc vào đâu và cần được sử dụng như thế nào?* Package Javadoc trả lời: *Package này chứa nhóm kiểu nào, khái niệm chính là gì và người dùng nên bắt đầu ở đâu?*

Cả hai được viết dưới dạng Java documentation comment `/** ... */`, nhưng gắn với những phần tử khác nhau. Khi chạy công cụ `javadoc`, chúng được tổng hợp cùng tài liệu lớp, interface, constructor và phương thức thành một bộ API documentation có cấu trúc.

**Nguyên tắc:** tài liệu làm rõ hợp đồng API, nhưng không tự làm thay đổi `requires`, `exports`, `opens`, `uses` hoặc `provides`. Quyền truy cập giữa các module vẫn do module descriptor và quy tắc JPMS quyết định.

## 1. Module Javadoc nằm ở đâu?

Module Javadoc là documentation comment ngay phía trước khai báo `module` hoặc `open module` trong file `module-info.java`.

Ví dụ:

~~~java
/**
 * Cung cấp API quản lý danh mục sản phẩm cho ứng dụng.
 *
 * <p>Module này công bố package
 * {@link com.example.catalog.api} để client
 * tạo và truy vấn thông tin sản phẩm.
 *
 * <p>Các package implementation không được export;
 * client không nên phụ thuộc vào chi tiết lưu trữ nội bộ.
 *
 * @since 1.0
 */
module com.example.catalog {
    exports com.example.catalog.api;
}
~~~

Comment đứng **trước** từ khóa `module`. Công cụ Javadoc gắn phần mô tả này với trang tổng quan của module.

Nội dung phù hợp ở cấp module gồm:

- Vai trò và phạm vi trách nhiệm của module.
- Những package API chính được công bố.
- Cách sử dụng module và ví dụ luồng tích hợp.
- Các yêu cầu, giới hạn hoặc nguyên tắc kiến trúc cần biết.
- Hợp đồng service mà module sử dụng hoặc cung cấp.
- Thông tin phiên bản API, cảnh báo tương thích và quy ước vận hành.

Không nên biến module Javadoc thành bản sao liệt kê toàn bộ phương thức. Chi tiết của class và method nên nằm ở Javadoc ngay tại class hoặc method; trang module dùng để dẫn đường và giải thích thiết kế tổng thể.

## 2. Package Javadoc nằm ở đâu?

Tài liệu cấp package hiện đại được đặt trong file `package-info.java` của chính package đó.

Ví dụ package `com.example.catalog.api`:

~~~java
/**
 * API công khai để đọc và thao tác dữ liệu danh mục.
 *
 * <p>Điểm bắt đầu thông dụng là
 * {@link com.example.catalog.api.CatalogService}.
 *
 * <p>Package này chứa các contract ổn định dành
 * cho consumer. Implementation và persistence
 * được giữ trong các package nội bộ khác.
 *
 * @since 1.0
 */
package com.example.catalog.api;
~~~

File `package-info.java` không cần chứa public class. Nó thường gồm một Javadoc comment gắn với khai báo `package`, và có thể kèm package annotations nếu thiết kế cần.

Vị trí file thường như sau:

~~~text
src/
└── com.example.catalog/
    ├── module-info.java
    └── com/example/catalog/
        ├── api/
        │   ├── package-info.java
        │   ├── CatalogService.java
        │   └── CatalogItem.java
        └── internal/
            ├── package-info.java
            └── InMemoryCatalogStore.java
~~~

Những file `package-info.java` thuộc các package khác nhau có nội dung và ý nghĩa khác nhau. File trong `api` có thể mô tả hợp đồng công khai; file trong `internal` có thể hướng dẫn người bảo trì, dù package đó không được export cho consumer.

## 3. So sánh tài liệu module và package

| Tiêu chí | Module Javadoc | Package Javadoc |
|---|---|---|
| File thường dùng | `module-info.java` | `package-info.java` |
| Phạm vi | Một named module | Một Java package |
| Vị trí comment | Trước khai báo `module` | Trước khai báo `package` |
| Nội dung chính | Mục đích module, nhóm API, tích hợp, service | Vai trò package, kiểu chủ đạo, quy tắc sử dụng |
| Trang tài liệu | Module summary | Package summary |
| Liên quan encapsulation | Diễn giải `exports` và thiết kế module | Diễn giải package API hoặc nội bộ |
| Có thay đổi access control? | Không | Không |

Ví dụ ba cấp tài liệu:

~~~text
Module: com.example.catalog
  └─ Tại sao tồn tại và công bố API gì?

Package: com.example.catalog.api
  └─ Những loại API nào thuộc nhóm này?

Class: CatalogService
  └─ Một type dùng thế nào và các phương thức có contract gì?
~~~

Mỗi cấp nên bổ sung thông tin cho cấp còn lại. Tránh lặp nguyên văn các đoạn dài ở module, package và class, vì nội dung trùng lặp dễ trở nên không nhất quán khi thiết kế API thay đổi.

## 4. Một ví dụ modular hoàn chỉnh

Giả sử có hai module: một module cung cấp API và một module ứng dụng sử dụng API đó.

~~~text
project/
└── src/
    ├── com.example.catalog/
    │   ├── module-info.java
    │   └── com/example/catalog/api/
    │       ├── package-info.java
    │       ├── CatalogItem.java
    │       └── CatalogService.java
    └── com.example.app/
        ├── module-info.java
        └── com/example/app/Main.java
~~~

Module library:

~~~java
/**
 * API danh mục được chia sẻ cho các ứng dụng.
 *
 * <p>Client nên bắt đầu ở package
 * {@link com.example.catalog.api}.
 */
module com.example.catalog {
    exports com.example.catalog.api;
}
~~~

Package API:

~~~java
/**
 * Các kiểu dùng để mô tả và tra cứu mục danh mục.
 *
 * <p>Gồm {@link com.example.catalog.api.CatalogItem}
 * và {@link com.example.catalog.api.CatalogService}.
 */
package com.example.catalog.api;
~~~

Một record công khai:

~~~java
package com.example.catalog.api;

/**
 * Đại diện cho một mục danh mục bất biến.
 *
 * @param id mã định danh không rỗng
 * @param name tên hiển thị của mục
 */
public record CatalogItem(String id, String name) {
    public CatalogItem {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id is required");
        }
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name is required");
        }
    }
}
~~~

Interface:

~~~java
package com.example.catalog.api;

import java.util.Optional;

/**
 * Hợp đồng tra cứu mục danh mục.
 */
public interface CatalogService {

    /**
     * Tìm một mục theo mã định danh.
     *
     * @param id mã định danh cần tìm
     * @return mục tương ứng hoặc Optional rỗng
     * @throws IllegalArgumentException nếu id không hợp lệ
     */
    Optional<CatalogItem> findById(String id);
}
~~~

Ứng dụng consumer:

~~~java
module com.example.app {
    requires com.example.catalog;
}
~~~

Ví dụ cho thấy `exports` và `requires` là cấu hình module, còn Javadoc mô tả cách dùng. Package comment giúp kết nối hai kiểu `CatalogItem` và `CatalogService` thành một bức tranh API có ý nghĩa.

## 5. Javadoc không thay thế module descriptor

Có thể viết một comment nói rằng module cung cấp package `com.example.catalog.api`, nhưng nếu descriptor không có directive `exports`, module khác vẫn không thể import các public type của package đó theo quy tắc JPMS thông thường.

Ví dụ:

~~~java
/**
 * Có API tại com.example.catalog.api.
 */
module com.example.catalog {
    // Không có exports!
}
~~~

Consumer:

~~~java
module com.example.app {
    requires com.example.catalog;
}
~~~

Dù comment nói API tồn tại, compiler vẫn không cho app sử dụng package không export. Muốn công bố API, phải có directive thật:

~~~java
module com.example.catalog {
    exports com.example.catalog.api;
}
~~~

Ngược lại, chỉ thêm `exports` cũng không làm tài liệu xuất hiện rõ ràng nếu thiếu module và package Javadoc. Người đọc sẽ thấy các kiểu, nhưng khó hiểu cách tích hợp, contract và những phần không nên phụ thuộc.

**Documentation mô tả ý định; descriptor thực thi ranh giới kỹ thuật.** Hai nguồn cần nhất quán, nhưng không nên coi cái này là thay thế cho cái kia.

## 6. Module Javadoc và strong encapsulation

Named module có thể chứa nhiều package nhưng chỉ export một số package nhất định:

~~~java
/**
 * Module thư viện chuẩn hóa dữ liệu.
 *
 * <p>API công khai nằm tại
 * {@link com.example.normalize.api}.
 *
 * <p>Các package internal chứa thuật toán và adapter;
 * chúng không được bảo đảm ổn định cho consumer.
 */
module com.example.normalize {
    exports com.example.normalize.api;
}
~~~

Package `com.example.normalize.internal` có thể có documentation comment riêng cho người bảo trì:

~~~java
/**
 * Thành phần implementation nội bộ của module.
 *
 * <p>Không phải public API dành cho module khác.
 * Các class có thể thay đổi mà không thông báo
 * tương thích API cho consumer bên ngoài.
 */
package com.example.normalize.internal;
~~~

Một package có Javadoc **không có nghĩa** package đó được export. Tương tự, class được ghi tài liệu và khai báo `public` vẫn không trở thành API khả dụng đối với các module khác nếu package chưa export.

Khi xuất bản API documentation, có thể cấu hình công cụ để chỉ hiển thị nội dung API công khai hoặc thêm nội dung internal theo nhu cầu. Không nên dùng việc hiển thị Javadoc để suy ra quyền truy cập runtime.

## 7. Qualified exports và nội dung tài liệu

JPMS có thể chỉ export một package cho danh sách module cụ thể:

~~~java
/**
 * Module tích hợp hệ thống thanh toán.
 *
 * <p>Package com.example.payment.bridge là contract
 * nội bộ chỉ dành cho những adapter được chỉ định.
 */
module com.example.payment {
    exports com.example.payment.api;

    exports com.example.payment.bridge
        to com.example.checkout, com.example.admin;
}
~~~

Package Javadoc của `com.example.payment.bridge` nên nói rõ:

- Đối tượng sử dụng dự kiến là các module nào.
- Phần nào của package là contract ổn định.
- Những điều kiện tích hợp hoặc giới hạn tương thích.
- Lý do package không export vô điều kiện.

Tài liệu này giúp người đọc hiểu kiến trúc, nhưng qualified exports vẫn phải khai báo chính xác trong module descriptor. Nếu module đích đổi tên, việc chỉ sửa Javadoc không tự sửa directive `exports ... to`.

## 8. Module Javadoc với uses và provides

JPMS hỗ trợ service-oriented architecture bằng các directive `uses` và `provides`. Javadoc cung cấp các block tag chuyên biệt `@uses` và `@provides` để mô tả ý nghĩa service trong tài liệu module.

Ví dụ module consumer:

~~~java
/**
 * Ứng dụng mở rộng bằng các bộ định dạng tài liệu.
 *
 * @uses com.example.spi.Formatter
 *       Tìm các bộ định dạng do plugin cung cấp.
 */
module com.example.app {
    requires com.example.spi;

    uses com.example.spi.Formatter;
}
~~~

Ví dụ module provider:

~~~java
/**
 * Cung cấp implementation định dạng văn bản thuần.
 *
 * @provides com.example.spi.Formatter
 *           Bộ định dạng văn bản thuần mặc định.
 */
module com.example.formatter.text {
    requires com.example.spi;

    provides com.example.spi.Formatter
        with com.example.formatter.text.TextFormatter;
}
~~~

Trong đó:

- Directive `uses` hoặc `provides` là thông tin module có tác dụng trong JPMS.
- Tag `@uses` hoặc `@provides` cung cấp **mô tả Javadoc** cho service tương ứng.
- Thêm tag tài liệu nhưng thiếu directive tương ứng không đăng ký consumer hay provider cho ServiceLoader.
- Tag tài liệu không tự tạo instance và không thay đổi hành vi của `Configuration.resolveAndBind(...)`.

Với hệ thống plugin, module Javadoc là nơi phù hợp để nêu contract SPI, mục đích service, điều kiện provider và nơi tìm hướng dẫn triển khai. Tài liệu chi tiết của interface service vẫn nên nằm tại Javadoc của interface đó.

## 9. Liên kết giữa module, package và class

Javadoc có thể tạo liên kết tới những phần tử Java có trong tập tài liệu.

Ví dụ trong module-info.java:

~~~java
/**
 * Cung cấp các thao tác danh mục.
 *
 * <p>Điểm bắt đầu là
 * {@link com.example.catalog.api.CatalogService}.
 */
module com.example.catalog {
    exports com.example.catalog.api;
}
~~~

Trong package-info.java:

~~~java
/**
 * Public API của danh mục.
 *
 * <p>Để tìm mục, dùng
 * {@link com.example.catalog.api.CatalogService#findById(String)}.
 *
 * @see com.example.catalog.api.CatalogItem
 */
package com.example.catalog.api;
~~~

Một số cú pháp hữu ích:

- `{@link Type}`: chèn liên kết inline tới type.
- `{@link Type#method(Type)}`: liên kết tới method.
- `{@linkplain Type nhãn hiển thị}`: liên kết với nhãn văn bản thông thường.
- `{@code ...}`: hiển thị đoạn code ngắn bằng phông code, tránh diễn giải như markup.
- `{@literal ...}`: hiển thị ký tự đặc biệt dưới dạng literal.
- `@see`: thêm tham chiếu ở khu vực “See Also”.
- `@since`: ghi mốc phiên bản mà API hoặc module được giới thiệu.
- `@deprecated`: giải thích lý do không nên tiếp tục sử dụng và hướng thay thế nếu có.

Khi tạo liên kết, cần dùng tên đầy đủ hoặc đặt import/context phù hợp để công cụ có thể giải quyết tham chiếu. Nếu Javadoc báo lỗi `reference not found`, hãy kiểm tra tên package/class và các module nằm trong phạm vi tài liệu.

Không thay toàn bộ lời giải thích bằng danh sách link. Javadoc tốt vẫn cần mô tả bằng ngôn ngữ tự nhiên trước khi dẫn sang chi tiết.

## 10. package-info.java và package annotations

Ngoài package Javadoc, file `package-info.java` có thể chứa annotation áp dụng ở cấp package.

Ví dụ giả định có annotation `@NonNullByDefault` được khai báo để có thể dùng trên package:

~~~java
/**
 * API quản lý giá trị và quy tắc kiểm tra đầu vào.
 *
 * <p>Package này dùng quy ước không-null mặc định
 * theo annotation của thư viện kiểm tra tĩnh.
 */
@NonNullByDefault
package com.example.validation.api;

import com.example.annotations.NonNullByDefault;
~~~

Đây là ví dụ về cú pháp; annotation `NonNullByDefault` là **giả định** do thư viện hoặc dự án cung cấp, không phải annotation sẵn có trong Java SE. Nó phải có `@Target(ElementType.PACKAGE)` phù hợp và module chứa annotation phải có thể đọc được ở thời điểm compile.

Cấu trúc file thường gồm:

1. Javadoc comment trước khai báo package.
2. Các package annotations nếu có.
3. Dòng `package qualified.name;`.
4. Các import cần thiết cho annotations.

Không dùng package-info.java như một nơi để khai báo class chính hoặc tạo dependency module ngầm. Quan hệ giữa các named module vẫn được điều khiển qua `module-info.java`.

## 11. Công cụ javadoc cho nhiều module source

JDK cung cấp công cụ `javadoc` để tạo tài liệu HTML từ source. Với source tree kiểu multi-module:

~~~text
src/
├── com.example.catalog/
│   ├── module-info.java
│   └── com/example/catalog/api/
│       ├── package-info.java
│       ├── CatalogItem.java
│       └── CatalogService.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
~~~

Có thể tạo tài liệu bằng lệnh:

~~~bash
javadoc --module-source-path src \
        --module com.example.catalog,com.example.app \
        -d docs
~~~

Ý nghĩa:

- `--module-source-path src`: nơi tìm source của các module.
- `--module ...`: danh sách source module cần đưa vào tài liệu.
- `-d docs`: thư mục ghi HTML được sinh ra.

Sau khi chạy, bộ tài liệu thường có trang tổng quan module, trang package và trang class hoặc interface. Các trang **module-summary.html** và **package-summary.html** giúp người đọc đi từ phạm vi module tới package cụ thể.

Nếu chỉ muốn tài liệu cho một module:

~~~bash
javadoc --module-source-path src \
        --module com.example.catalog \
        -d docs/catalog
~~~

Khi module phụ thuộc vào JAR đã biên dịch bên ngoài, thêm module path thích hợp để Javadoc giải quyết kiểu và dependency:

~~~bash
javadoc --module-source-path src \
        --module-path lib \
        --module com.example.catalog \
        -d docs/catalog
~~~

Nếu tài liệu hiển thị tiếng Việt, có thể cấu hình mã hóa nguồn/output thống nhất theo JDK:

~~~bash
javadoc -encoding UTF-8 \
        -docencoding UTF-8 \
        -charset UTF-8 \
        --module-source-path src \
        --module com.example.catalog \
        -d docs/catalog
~~~

Trên Windows PowerShell hoặc Command Prompt, có thể đặt toàn bộ lệnh trên một dòng thay vì dùng dấu `` của shell Unix để nối dòng. Với nhiều module path trên Windows, dùng dấu chấm phẩy `;` giữa các đường dẫn; Linux/macOS thường dùng dấu hai chấm `:`.

## 12. Phân biệt javadoc, javac và jar

Ba công cụ liên quan tới cùng dự án modular nhưng có nhiệm vụ khác nhau:

| Công cụ | Kết quả chính | Liên quan Javadoc |
|---|---|---|
| `javac` | Biên dịch .java thành .class và module-info.class | Đọc/kiểm tra source nhưng không tạo website tài liệu API |
| `jar` | Đóng gói class/resource thành JAR | Có thể đóng gói module descriptor đã biên dịch |
| `javadoc` | Tạo API documentation, thường là HTML | Đọc module/package/class documentation comments |

Ví dụ biên dịch:

~~~bash
javac --module-source-path src \
      -d mods \
      -m com.example.catalog,com.example.app
~~~

Sau đó tạo docs:

~~~bash
javadoc --module-source-path src \
        --module com.example.catalog,com.example.app \
        -d docs
~~~

Đây là **hai bước độc lập**. Biên dịch thành công không chứng minh Javadoc references đúng; và tạo Javadoc thành công không tự tạo executable application.

Các trang Javadoc nên được sinh từ đúng phiên bản source/descriptor đang phát hành, tránh trường hợp website tài liệu nói module đã export một package nhưng artifact thực tế lại chưa export package đó.

## 13. Javadoc trang module hiển thị gì?

Tùy phiên bản JDK và tùy chọn `javadoc`, trang tổng quan module có thể bao gồm:

- Mô tả module từ comment trước khai báo module.
- Các package của module trong phạm vi tài liệu.
- Thông tin về dependencies và quan hệ module.
- Các package được export hoặc mở theo module descriptor.
- Thông tin services từ `uses` hoặc `provides` và phần giải thích đi kèm nếu có.

Đây là cách nhìn hữu ích khi muốn giới thiệu module cho người mới tham gia codebase. Tuy nhiên, nội dung được hiển thị còn tùy mức hiển thị của công cụ và chính sách tài liệu, chẳng hạn API-only hay có thêm implementation.

Không nên dựa vào việc một trang tài liệu có hoặc không hiển thị package để suy ra tuyệt đối rằng module đó được phép truy cập ở runtime. Khi chẩn đoán thực tế, kiểm tra `module-info.java`, `ModuleDescriptor` hoặc thông tin module đã resolve.

## 14. Javadoc trang package nên mô tả gì?

Một package Javadoc tốt nên trả lời các câu hỏi:

- Package có vai trò gì trong module?
- Những public type quan trọng nào là điểm bắt đầu?
- Quy ước input, output hoặc lỗi chung của package là gì?
- Consumer cần đọc module nào và có giới hạn sử dụng nào?
- Có pattern hoặc workflow điển hình khi dùng các type?
- Package có ổn định như public API hay chỉ là implementation detail?
- Có chính sách versioning và deprecation nào cần biết?

Ví dụ cho package tích hợp:

~~~java
/**
 * Contract tích hợp nguồn dữ liệu sản phẩm.
 *
 * <p>Consumer nên triển khai
 * {@link com.example.catalog.spi.CatalogReader}.
 * Ứng dụng tìm implementation qua ServiceLoader.
 *
 * <p>Không phụ thuộc vào package implementation
 * của từng provider module.
 *
 * @since 2.0
 */
package com.example.catalog.spi;
~~~

Javadoc của `CatalogReader` sau đó giải thích chi tiết phương thức, exception và điều kiện triển khai. Trang package không cần lặp các `@param` và `@return` của từng method.

## 15. API documentation và internal documentation

Một tổ chức module rõ ràng có thể dùng ba lớp tài liệu:

**Tài liệu công khai.** Dành cho package export và public API. Tập trung vào contract, tính tương thích, cách sử dụng và các giới hạn được bảo đảm.

**Tài liệu tích hợp hạn chế.** Dành cho qualified exported package hoặc SPI. Nêu rõ module tiêu thụ dự kiến, điều kiện tích hợp và chính sách backward compatibility.

**Tài liệu nội bộ.** Dành cho package không export. Tập trung vào thuật toán, kiến trúc, invariants, cấu hình và quyết định implementation để phục vụ bảo trì.

Ví dụ:

~~~java
module com.example.catalog {
    exports com.example.catalog.api;

    exports com.example.catalog.spi
        to com.example.catalog.runtime;
}
~~~

Package `com.example.catalog.internal` có thể vẫn có package-info.java để người phát triển hiểu code. Việc viết Javadoc nội bộ không buộc module phải export nó.

Không nên thay đổi descriptor chỉ vì một số package hoặc class không xuất hiện trên bộ HTML public API docs. Nhu cầu hiển thị documentation và nhu cầu cấp quyền truy cập runtime là hai vấn đề độc lập.

## 16. Documentation cho service trong module

Với service contract, có ít nhất ba nơi đáng viết tài liệu:

1. **Module consumer** — vì sao module cần service, mô tả ở `@uses`.
2. **Module provider** — module cung cấp capability gì, mô tả ở `@provides`.
3. **Service interface** — contract bắt buộc, exceptions, vòng đời và các quy tắc implement.

Ví dụ service interface:

~~~java
package com.example.spi;

/**
 * Bộ chuyển đổi dữ liệu có thể được cung cấp bởi plugin.
 */
public interface Converter {

    /**
     * Chuyển đổi văn bản đầu vào.
     *
     * @param input văn bản cần xử lý
     * @return văn bản sau chuyển đổi
     * @throws IllegalArgumentException nếu input không hợp lệ
     */
    String convert(String input);
}
~~~

Descriptor provider:

~~~java
/**
 * Provider cho định dạng chuẩn hóa chữ hoa.
 *
 * @provides com.example.spi.Converter
 *           Cung cấp bộ chuyển đổi chữ hoa cho text.
 */
module com.example.converter.upper {
    requires com.example.spi;

    provides com.example.spi.Converter
        with com.example.converter.upper.UpperConverter;
}
~~~

Tài liệu module giải thích vai trò provider, còn Javadoc interface mô tả những gì mọi provider phải tuân thủ. Module service docs không thay thế khai báo `provides` hoặc việc triển khai contract của class provider.

## 17. Chính sách phiên bản và tính ổn định

Một module có thể thay đổi implementation mà không làm thay đổi API. Vì vậy, Javadoc nên phân biệt những cam kết ổn định với chi tiết nội bộ.

Nội dung phù hợp ở public package docs:

- Ý nghĩa các kiểu công khai.
- Hành vi có thể quan sát được từ consumer.
- Các loại exception được contract bảo đảm.
- Quy ước nullability hoặc thread safety nếu API có quy định.
- Mốc bắt đầu hỗ trợ qua `@since`.
- Hướng migration cho API đã deprecated.

Nội dung không nên coi là public contract:

- Tên thuật toán nội bộ có thể thay đổi.
- Cách sắp xếp collection implementation.
- Tên class nằm trong package không export.
- Những chi tiết chỉ đúng với một phiên bản triển khai.

Ví dụ khi thay API cũ:

~~~java
/**
 * API cũ dùng cho catalog legacy.
 *
 * @deprecated Sử dụng
 * {@link com.example.catalog.api.CatalogService}
 * thay thế kể từ phiên bản 2.0.
 */
@Deprecated(since = "2.0")
public interface LegacyCatalog {
}
~~~

Với public API, documentation cần đồng nhất với annotation hoặc thay đổi code thực tế. Gắn `@deprecated` trong Javadoc nhưng không dùng `@Deprecated` cho code có thể làm công cụ và người sử dụng nhận tín hiệu không nhất quán.

## 18. Dùng Javadoc để dẫn người đọc qua module graph

Trong dự án nhiều module, tài liệu nên cho biết cách điều hướng từ module-level overview tới các package và type liên quan.

Ví dụ cấu trúc:

~~~text
com.example.catalog.api
   exports com.example.catalog.api
             |
             v
       CatalogService
             |
             v
com.example.catalog.runtime
   requires com.example.catalog.api
             |
             v
    runtime implementation
~~~

Module Javadoc của `com.example.catalog.api` có thể giải thích rằng nó chỉ chứa contract dùng chung; module runtime triển khai các contract đó. Package Javadoc dẫn tới interface `CatalogService`. Javadoc interface mô tả hành vi bắt buộc.

Tài liệu tốt không cần liệt kê mọi cạnh trong module graph. Chỉ nêu những dependency và điểm tích hợp thực sự quan trọng đối với người sử dụng API. Nếu một dependency là implementation detail, không nên khuyến khích consumer phụ thuộc trực tiếp vào nó.

Khi sử dụng liên kết sang module hoặc type của module khác, tạo docs với module path hoặc source module phù hợp để công cụ có thể giải quyết tham chiếu. Với tài liệu external API, xem xét tùy chọn linking của Javadoc tương ứng môi trường build và hosting.

## 19. Tối ưu tài liệu theo đối tượng đọc

Một README hoặc package Javadoc có thể phục vụ nhiều nhóm:

- **Người dùng API:** cần biết entry point, dependency và ví dụ sử dụng.
- **Người tích hợp service:** cần biết SPI interface, quy tắc provider và vòng đời.
- **Người bảo trì:** cần biết thiết kế module, package internal và giới hạn implementation.
- **Người review:** cần đối chiếu public surface của descriptor với lời mô tả tài liệu.

Nên phân cấp thông tin:

- Module comment: bức tranh tổng thể.
- Package comment: một nhóm khái niệm liên quan.
- Type comment: ý nghĩa class/interface.
- Method comment: contract cụ thể và edge cases.
- README bên ngoài: quy trình build, cài đặt, vận hành hoặc ví dụ dài.

Không nên nhét lệnh deploy, thông tin máy cá nhân, cấu hình bí mật hoặc nội dung chỉ đúng một môi trường vào Javadoc API công khai.

## 20. Chẩn đoán lỗi khi tạo Javadoc

**Không thấy trang module summary.** Kiểm tra source có `module-info.java`, dùng `--module-source-path` và `--module` đúng tên module hay chưa.

**Không thấy mô tả package.** Kiểm tra có `package-info.java` với documentation comment trước khai báo package không, file có nằm đúng đường dẫn package và có được tool xử lý hay không.

**Tham chiếu link không được giải quyết.** Kiểm tra tên đầy đủ của type/method, source path, module path và việc phần tử cần link có nằm trong tập tài liệu hay không.

**Một package internal không xuất hiện trong public API docs.** Kiểm tra mức hiển thị của Javadoc và exports trong descriptor. Không tự động export package internal chỉ để đưa nó lên trang public.

**Javadoc báo lỗi HTML hoặc ký tự đặc biệt.** Dùng `{@code ...}` hoặc `{@literal ...}` khi muốn hiển thị dấu đặc biệt, kiểm tra cấu trúc HTML trong documentation comment và mã hóa UTF-8.

**Biên dịch được nhưng javadoc fail.** Compiler và Javadoc tool có mục đích khác nhau; lỗi doc comment, thiếu liên kết hoặc cấu hình source/module path có thể chỉ lộ khi tạo documentation.

**Module Javadoc và descriptor không nhất quán.** Comment nói module công bố package/service nhưng descriptor chưa khai báo đúng. Kiểm tra source descriptor; đừng coi lời mô tả là cơ chế cấp quyền.

**Tài liệu vẫn hiển thị API đã bị loại bỏ.** Kiểm tra phiên bản source được dùng để generate, cache CI và thư mục output. Nên sinh docs từ artifact/source cùng version với bản phát hành.

## 21. Quy trình viết tài liệu module/package

Khi một module mới được tạo, có thể làm theo trình tự sau:

1. Xác định trách nhiệm module và package API thực sự cần export.
2. Viết module-info.java với `requires`, `exports`, `uses`, `provides` thích hợp.
3. Viết documentation comment phía trước khai báo module.
4. Tạo package-info.java cho các package API quan trọng.
5. Ở package docs, chỉ rõ entry point và liên kết tới type chính.
6. Viết Javadoc cho public class/interface và các method tạo nên contract.
7. Nếu có SPI, thêm `@uses` / `@provides` mô tả service ở cấp module.
8. Dùng `javadoc` để sinh trang docs; xem module summary và package summary.
9. Sửa lỗi cấu trúc Javadoc, tham chiếu, mã hóa nếu công cụ báo.
10. Đảm bảo bộ docs phát hành đến từ đúng version source và module descriptor.

Một lệnh tham khảo:

~~~bash
javadoc --module-source-path src \
        --module com.example.catalog \
        -encoding UTF-8 \
        -docencoding UTF-8 \
        -charset UTF-8 \
        -d docs
~~~

Có thể thêm lint hoặc strict verification trong CI theo chính sách dự án. Khi cần kiểm tra tùy chọn cụ thể của JDK đang dùng, chạy `javadoc --help` và `javadoc -X`.

## 22. Tự kiểm tra kiến thức

1. Module Javadoc được đặt ở đâu trong `module-info.java`?
2. Package Javadoc được đặt ở đâu trong `package-info.java`?
3. Một module comment có thể tự export package bằng cách mô tả nó trong văn bản không?
4. Module Javadoc khác package Javadoc ở phạm vi và mục đích nào?
5. Package không export có thể có package-info.java không?
6. `@uses` và `@provides` là tag tài liệu hay JPMS directive?
7. Directive nào thực sự đăng ký service consumer/provider trong module system?
8. `{@link ...}` giúp người đọc điều hướng ra sao?
9. Công cụ nào tạo HTML API docs từ source modular?
10. Trong `javadoc`, `--module-source-path` và `--module` có vai trò gì?
11. Vì sao documentation của package internal không có nghĩa package đó được public?
12. Khi API bị deprecated, nên đồng bộ Javadoc và annotation Java thế nào?
13. Vì sao docs phải được sinh từ đúng source version đang phát hành?
14. Nên đặt ví dụ vận hành dài trong module Javadoc, package Javadoc hay README riêng?

**Kết luận:** `module-info.java` và `package-info.java` tạo ra hai tầng documentation bổ trợ cho JPMS. Module Javadoc giải thích trách nhiệm và bề mặt API của module; package Javadoc giải thích nhóm kiểu và điểm bắt đầu của từng package. Viết đúng vị trí, liên kết tới type phù hợp, dùng `@uses`/`@provides` khi có service và tạo HTML bằng `javadoc` giúp kiến trúc module dễ hiểu hơn mà không làm suy yếu strong encapsulation.
