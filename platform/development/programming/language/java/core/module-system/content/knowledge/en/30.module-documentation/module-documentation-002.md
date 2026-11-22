# module-info.java với chú thích API

Trong Java Platform Module System (JPMS), file `module-info.java` là điểm khai báo hợp đồng của một named module: tên module, các dependency, package được công khai hoặc mở cho reflection, cùng các service mà module sử dụng hoặc cung cấp.

Khi xây dựng thư viện modular để người khác sử dụng, descriptor không nên chỉ “đủ để biên dịch”. Nó còn là nơi thích hợp để viết **Javadoc cấp module** — giải thích mục đích của module, API dành cho người dùng, dependency có ý nghĩa, cách sử dụng service và giới hạn tương thích. Những chú thích này giúp tài liệu API truyền đạt *vì sao* module tồn tại và *cách* dùng module, thay vì chỉ liệt kê cấu trúc kỹ thuật.

Điểm cốt lõi: **Javadoc đặt ngay trước khai báo `module` trong `module-info.java` sẽ được công cụ `javadoc` sử dụng để tạo trang mô tả module.** Các directive `requires`, `exports`, `opens`, `uses`, `provides` vẫn được compiler phân tích theo ngữ nghĩa JPMS; chú thích không làm thay đổi các quyền này.

## 1. Vai trò của module-info.java trong tài liệu công khai

Một module descriptor tối giản:

~~~java
module com.acme.catalog {
    requires java.logging;
    exports com.acme.catalog.api;
}
~~~

Từ descriptor này, công cụ có thể biết:

- Tên module là `com.acme.catalog`.
- Module có dependency tới `java.logging`.
- Package `com.acme.catalog.api` được export.

Nhưng compiler không thể suy ra những điều người dùng API cần biết:

- Module cung cấp chức năng gì?
- Consumer nên bắt đầu bằng kiểu nào?
- Những package nào là public API ổn định?
- Có service provider hoặc extension point không?
- Sử dụng API có yêu cầu cấu hình hoặc quy ước vòng đời nào?
- Những package implementation nào cố ý không công khai?

Javadoc cấp module là nơi trả lời các câu hỏi trên. Descriptor và tài liệu đóng vai trò bổ sung: descriptor ràng buộc khả năng truy cập, còn Javadoc trình bày ý nghĩa và hướng dẫn sử dụng.

## 2. Viết Javadoc ngay trước module declaration

Cách viết thông dụng:

~~~java
/**
 * Cung cấp API quản lý danh mục sản phẩm.
 *
 * <p>Consumer sử dụng {@link com.acme.catalog.api.Catalog}
 * để tra cứu thông tin sản phẩm. Module công khai package
 * {@code com.acme.catalog.api}; các class implementation
 * được giữ trong package không export.
 *
 * <p>Ví dụ descriptor của consumer:
 * <pre>{@code
 * module com.acme.shop {
 *     requires com.acme.catalog;
 * }
 * }</pre>
 *
 * @since 1.0
 */
module com.acme.catalog {
    requires java.logging;
    exports com.acme.catalog.api;
}
~~~

Những điểm cần chú ý:

- Mở đầu bằng `/**` và kết thúc bằng `*/` để tạo **Javadoc comment**, không phải comment thông thường.
- Đặt comment ngay trước `module com.acme.catalog { ... }`.
- Tóm tắt mục đích module bằng một câu đầu tiên rõ ràng.
- Dùng các đoạn HTML/Javadoc hợp lệ như `<p>`, `{@code ...}` và `{@link ...}`.
- Có thể thêm `@since` để ghi lại mốc API được giới thiệu.

Ví dụ chỉ dùng:

~~~java
// Module quan ly danh muc
module com.acme.catalog { ... }
~~~

thì comment này có ích cho người đọc source nhưng không được xem như Javadoc mô tả module trong trang tài liệu API được tạo ra.

Cũng không nên đặt Javadoc module ở một class bất kỳ rồi kỳ vọng `javadoc` tự gắn nó vào trang module summary.

## 3. Chọn nội dung nào để viết ở cấp module?

Javadoc cấp module nên tập trung vào thông tin có phạm vi toàn module.

Một cấu trúc thực tế:

1. **Một câu định nghĩa:** module cung cấp chức năng cốt lõi nào.
2. **Public API:** package và entry point người dùng cần gọi.
3. **Tích hợp:** service, dependency hoặc framework mà consumer cần biết.
4. **Ví dụ sử dụng:** descriptor tối giản và đoạn code khởi đầu.
5. **Giới hạn:** những phần chưa được hỗ trợ hoặc implementation detail không nên phụ thuộc.
6. **Tương thích:** mốc `@since`, ghi chú migration hoặc thay đổi contract quan trọng.

Không cần lặp lại toàn bộ danh sách class ở trang module. Các class, method và package đã có trang Javadoc riêng. Tài liệu cấp module nên đóng vai trò bản đồ dẫn người đọc đến đúng API.

Ví dụ mở đầu hữu ích:

~~~java
/**
 * API đọc và tìm kiếm danh mục sản phẩm cho ứng dụng bán hàng.
 *
 * <p>Bắt đầu với {@link com.acme.catalog.api.Catalog}.
 * Có thể mở rộng logic tìm kiếm bằng service
 * {@link com.acme.catalog.spi.CatalogPlugin}.
 *
 * <p>Module không công khai package
 * {@code com.acme.catalog.internal}; consumer không nên
 * tham chiếu vào implementation package.
 *
 * @since 1.0
 */
module com.acme.catalog {
    exports com.acme.catalog.api;
    exports com.acme.catalog.spi;
}
~~~

Ở đây, nội dung giải thích ranh giới sử dụng công khai, còn directive `exports` hiện thực hóa ranh giới đó.

## 4. Javadoc của module và Javadoc của package bổ sung cho nhau

Một project modular thường có cấu trúc:

~~~text
src/
└── com.acme.catalog/
    ├── module-info.java
    └── com/acme/catalog/
        ├── api/
        │   ├── package-info.java
        │   └── Catalog.java
        ├── spi/
        │   ├── package-info.java
        │   └── CatalogPlugin.java
        └── internal/
            └── DefaultCatalogPlugin.java
~~~

Các tài liệu nên được chia đúng cấp:

| Vị trí | Nội dung phù hợp |
| --- | --- |
| `module-info.java` | Mục đích module, public surface, mô hình tích hợp, ví dụ tổng thể |
| `package-info.java` | Vai trò và quy ước của package, phạm vi API trong package |
| Javadoc của class/interface | Trách nhiệm của kiểu, lifecycle, thread-safety, ví dụ tạo instance |
| Javadoc của method | Tham số, kết quả, exception, side effect, điều kiện tiền/hậu |
| README ngoài source | Hướng dẫn build, vận hành, setup và chi tiết không phù hợp với API reference |

Ví dụ package documentation:

~~~java
/**
 * Các entry point công khai cho việc truy vấn danh mục.
 *
 * <p>Ứng dụng bên ngoài chỉ nên phụ thuộc vào những
 * interface và kiểu được mô tả trong package này.
 *
 * @since 1.0
 */
package com.acme.catalog.api;
~~~

Và Javadoc của kiểu:

~~~java
package com.acme.catalog.api;

/**
 * Cổng truy vấn thông tin sản phẩm.
 *
 * <p>Implementation có thể đọc dữ liệu từ nhiều nguồn.
 *
 * @since 1.0
 */
public interface Catalog {

    /**
     * Tìm sản phẩm theo mã định danh.
     *
     * @param id mã sản phẩm, không được {@code null}
     * @return sản phẩm nếu tồn tại
     * @throws IllegalArgumentException nếu id không hợp lệ
     */
    java.util.Optional<Product> findById(String id);
}
~~~

Việc tách cấp tài liệu giúp module summary ngắn gọn nhưng vẫn dẫn người dùng tới những chi tiết cần thiết.

## 5. Mô tả requires: giải thích dependency, không chỉ liệt kê

Một module có thể có các directive:

~~~java
module com.acme.reporting {
    requires java.logging;
    requires com.acme.catalog;
}
~~~

Javadoc nên diễn giải các dependency đáng chú ý:

~~~java
/**
 * Tạo báo cáo tổng hợp từ dữ liệu danh mục.
 *
 * <p>Module sử dụng {@code com.acme.catalog} làm nguồn
 * dữ liệu và {@code java.logging} để ghi nhận sự kiện.
 *
 * <p>Consumer chỉ cần phụ thuộc vào
 * {@code com.acme.reporting} nếu không trực tiếp
 * sử dụng kiểu từ các module dependency.
 */
module com.acme.reporting {
    requires java.logging;
    requires com.acme.catalog;
    exports com.acme.reporting.api;
}
~~~

Cần phân biệt rõ:

- `requires x`: module hiện tại đọc module `x`.
- `requires transitive x`: readability tới `x` có thể được truyền tới consumer đọc module hiện tại theo quy tắc JPMS.
- `requires static x`: dependency bắt buộc ở compile-time nhưng không bắt buộc phải hiện diện lúc runtime.

Javadoc có thể giải thích lý do dùng `transitive` hoặc `static`, nhưng chỉ **directive thật trong descriptor** mới thay đổi module graph. Viết một câu “dependency này là optional” trong Javadoc không thay thế `requires static` hoặc logic xử lý optional dependency của ứng dụng.

Với public API trả về kiểu thuộc module khác, hãy cân nhắc `requires transitive` khi đó là một phần hợp đồng cần được consumer đọc. Đây là quyết định thiết kế module, không phải quyết định trình bày tài liệu.

## 6. Mô tả exports: đâu là public API?

Ví dụ:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;
    exports com.acme.catalog.spi;
}
~~~

Đây là những package được export không giới hạn tới các module có readability phù hợp. Trong tài liệu cấp module, nên nói rõ mục đích của từng package:

~~~java
/**
 * Cung cấp API và extension point cho catalog.
 *
 * <ul>
 *   <li>{@code com.acme.catalog.api}: API dùng bởi ứng dụng.</li>
 *   <li>{@code com.acme.catalog.spi}: service contract
 *       dành cho module provider.</li>
 * </ul>
 */
module com.acme.catalog {
    exports com.acme.catalog.api;
    exports com.acme.catalog.spi;
}
~~~

Nếu dùng qualified exports:

~~~java
exports com.acme.catalog.maintenance to com.acme.admin;
~~~

hãy ghi rõ đây là integration dành riêng cho module `com.acme.admin`, không phải API công khai cho mọi consumer. Nội dung và directive phải thống nhất: tài liệu không nên khuyên người dùng thông thường import package đã chỉ export cho một module cụ thể.

Một package có class `public` nhưng không được export vẫn không trở thành public API dành cho module khác. Javadoc không nới lỏng ranh giới đó.

## 7. Mô tả opens: quyền reflection có phạm vi

Framework như ORM hoặc serializer có thể cần deep reflection vào package implementation. Descriptor có thể khai báo:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;

    opens com.acme.catalog.internal
        to com.acme.serializer;
}
~~~

Trong Javadoc module, mô tả lý do quyền đó tồn tại:

~~~java
/**
 * API danh mục sản phẩm.
 *
 * <p>Package {@code com.acme.catalog.internal}
 * không phải API công khai. Nó chỉ được mở cho module
 * {@code com.acme.serializer} để đọc metadata của object
 * khi serialize.
 */
module com.acme.catalog {
    exports com.acme.catalog.api;
    opens com.acme.catalog.internal to com.acme.serializer;
}
~~~

Phân biệt:

- `exports p`: cho phép truy cập public type/member từ các module đọc module nguồn.
- `opens p`: cho phép deep reflection vào package từ các module khác.
- `opens p to m`: chỉ cấp deep reflection cho target module `m`.
- `open module`: mở toàn bộ package của module cho reflection.

Không nên viết trong tài liệu rằng `opens p to m` làm package thành API compile-time của `m`. `opens` không thay thế `exports`; nếu consumer cần import kiểu từ package, phải thiết kế public API và export tương ứng.

Nếu framework chưa có tên module và chạy trên classpath, cấu hình `--add-opens ...=ALL-UNNAMED` có thể được dùng làm bước migration. Đó là một lựa chọn vận hành cần ghi chú riêng, không phải tên module hợp lệ để viết sau `to` trong `module-info.java`.

## 8. Tài liệu cho uses và provides với @uses, @provides

ServiceLoader và service binding là phần quan trọng của JPMS. Javadoc có các block tag hỗ trợ documentation của service ở cấp module:

- `@uses service.type mô tả`: giải thích service mà module tiêu thụ.
- `@provides service.type mô tả`: giải thích service mà module cung cấp implementation.

Ví dụ:

~~~java
/**
 * Module mở rộng catalog thông qua service provider.
 *
 * <p>Ứng dụng có thể tích hợp plugin tùy biến qua
 * {@link com.acme.catalog.spi.CatalogPlugin}.
 *
 * @uses com.acme.catalog.spi.CatalogPlugin
 *       Tìm plugin dùng để bổ sung nguồn dữ liệu catalog.
 *
 * @provides com.acme.catalog.spi.CatalogPlugin
 *       Cung cấp implementation mặc định trong module.
 *
 * @since 1.0
 */
module com.acme.catalog {
    exports com.acme.catalog.api;
    exports com.acme.catalog.spi;

    uses com.acme.catalog.spi.CatalogPlugin;

    provides com.acme.catalog.spi.CatalogPlugin
        with com.acme.catalog.internal.DefaultCatalogPlugin;
}
~~~

Directive `uses` và `provides` là phần **máy đọc được** trong module descriptor. Hai Javadoc tag tương ứng chỉ cung cấp **mô tả cho con người**.

Nên giữ chúng đồng bộ:

- Đã khai báo `uses` thì mô tả mục đích tìm provider và thời điểm sử dụng.
- Đã khai báo `provides` thì mô tả loại implementation hoặc tính năng được cung cấp.
- Không viết tag cho service không còn tồn tại trong descriptor hoặc không còn là hợp đồng đã công bố.
- Không đưa chi tiết implementation bí mật vào tài liệu public nếu nó không thuộc API contract.

Đối với module tiêu thụ service nhưng không cung cấp provider, chỉ cần `uses` và `@uses`. Ngược lại, module chuyên cung cấp provider thường có `provides` và `@provides`.

## 9. Ví dụ module-info.java hoàn chỉnh có chú thích API

Một descriptor tham khảo:

~~~java
/**
 * Cung cấp API, SPI và implementation mặc định
 * cho danh mục sản phẩm.
 *
 * <p>Ứng dụng bắt đầu từ
 * {@link com.acme.catalog.api.Catalog}.
 * Package {@code com.acme.catalog.api} là bề mặt sử dụng
 * dành cho client. Package {@code com.acme.catalog.spi}
 * chứa contract mở rộng qua ServiceLoader.
 *
 * <p>Ví dụ module consumer:
 * <pre>{@code
 * module com.acme.shop {
 *     requires com.acme.catalog;
 * }
 * }</pre>
 *
 * <p>Không sử dụng class trong
 * {@code com.acme.catalog.internal} như API ổn định.
 *
 * @uses com.acme.catalog.spi.CatalogPlugin
 *       Tìm provider mở rộng dữ liệu danh mục.
 *
 * @provides com.acme.catalog.spi.CatalogPlugin
 *       Cung cấp provider mặc định để ứng dụng có thể chạy
 *       khi chưa cài plugin bên ngoài.
 *
 * @since 1.0
 */
module com.acme.catalog {
    requires java.logging;

    exports com.acme.catalog.api;
    exports com.acme.catalog.spi;

    uses com.acme.catalog.spi.CatalogPlugin;

    provides com.acme.catalog.spi.CatalogPlugin
        with com.acme.catalog.internal.DefaultCatalogPlugin;
}
~~~

Trong source tương ứng cần thực sự tồn tại:

~~~text
com.acme.catalog/
├── module-info.java
└── com/acme/catalog/
    ├── api/
    │   └── Catalog.java
    ├── spi/
    │   └── CatalogPlugin.java
    └── internal/
        └── DefaultCatalogPlugin.java
~~~

Implementation `DefaultCatalogPlugin` cần đáp ứng quy tắc của service provider, chẳng hạn triển khai interface `CatalogPlugin` và có constructor hoặc provider method hợp lệ theo cơ chế JPMS.

Đây là một ví dụ tài liệu hướng tới consumer: người đọc thấy mục đích module, điểm bắt đầu, API/SPI được export, service và phạm vi không được cam kết. Compiler chỉ sử dụng các directive để thực thi module semantics; `javadoc` sử dụng phần mô tả để tạo tài liệu.

## 10. Tạo module documentation bằng javadoc CLI

Với source tree theo module:

~~~text
project/
└── src/
    ├── com.acme.catalog/
    │   ├── module-info.java
    │   └── com/acme/catalog/...
    └── com.acme.shop/
        ├── module-info.java
        └── com/acme/shop/...
~~~

Có thể sinh Javadoc cho một module:

~~~bash
javadoc \
  --module-source-path src \
  --module com.acme.catalog \
  -d docs
~~~

Hoặc cho nhiều module:

~~~bash
javadoc \
  --module-source-path src \
  --module com.acme.catalog,com.acme.shop \
  -d docs
~~~

Sau khi công cụ hoàn tất, thư mục `docs` chứa các trang HTML được tạo cho module, package và các API được công bố theo cấu hình Javadoc. Trong tài liệu được sinh, tìm trang **Module com.acme.catalog** (thường có trang `module-summary.html` thuộc thư mục module) để xem phần mô tả từ `module-info.java`.

Các điểm vận hành:

- Sử dụng JDK có công cụ `javadoc` và hỗ trợ JPMS.
- Tất cả type được tham chiếu trong `{@link ...}` cần có mặt trong phạm vi source/dependency mà Javadoc phân tích.
- Với dependency bên ngoài, cung cấp `--module-path` phù hợp nếu nguồn không tự đủ.
- Đường dẫn có dấu cách cần được quote theo shell.
- Những dự án không dùng layout `src/<moduleName>/...` cần điều chỉnh `--module-source-path` tương ứng.

Ví dụ có dependency ngoài source:

~~~bash
javadoc \
  --module-source-path src \
  --module-path libs \
  --module com.acme.catalog \
  -d docs
~~~

Lệnh tạo docs không thay thế bước build modular JAR. Javadoc giúp phát hành tài liệu API; `javac` và `jar` chịu trách nhiệm biên dịch và đóng gói artifact chạy được.

## 11. Tích hợp tạo Javadoc vào build tool

Trong dự án Maven có source đặt tại `src/main/java/module-info.java`, Javadoc thường được sinh bằng Maven Javadoc Plugin với cấu hình JDK/plugin phù hợp:

~~~bash
mvn javadoc:javadoc
~~~

Output mặc định thường nằm trong thư mục site do Maven quản lý, ví dụ `target/site/apidocs`, tùy plugin configuration.

Có thể phát hành Javadoc JAR để consumer tra cứu API:

~~~bash
mvn javadoc:jar
~~~

Trong Gradle Java Plugin, task `javadoc` tạo tài liệu API:

~~~bash
./gradlew javadoc
~~~

Tài liệu thường được sinh vào `build/docs/javadoc`. Khi project có `module-info.java`, cần đảm bảo toolchain và cấu hình module path được truyền đúng cho JavaDoc task. Tên task và hành vi có thể phụ thuộc version plugin/build logic.

Quy trình CI nên chạy docs trên cùng Java release đã dùng cho source. Nếu tài liệu gọi tới API chưa có ở Java target, Javadoc hoặc compiler có thể báo lỗi mặc dù mô tả bằng văn bản nhìn có vẻ hợp lệ.

## 12. Javadoc không thay thế module descriptor

Một số hiểu nhầm phổ biến:

| Giả định sai | Cách hiểu đúng |
| --- | --- |
| Viết `@uses` sẽ tự tạo service dependency | Cần directive `uses ServiceType;` trong descriptor |
| Viết `@provides` sẽ tự đăng ký provider | Cần `provides ServiceType with Impl;` |
| Ghi package là public trong Javadoc thì consumer import được | Cần `exports package.name;` phù hợp |
| Ghi “framework có thể phản chiếu” thì framework được quyền `setAccessible` | Cần `opens` hoặc runtime `--add-opens` phù hợp |
| Ghi dependency trong text Javadoc thì module đọc được dependency | Cần `requires` hoặc quan hệ readability đúng |
| `module-info.java` có comment là mọi class đều được document | Phải có source/type và cấu hình Javadoc để sinh trang API tương ứng |
| Javadoc hiển thị module nghĩa là JAR packaging hợp lệ | Phải kiểm tra `module-info.class` trong artifact thực tế |

Javadoc là giao diện **mô tả**. JPMS áp dụng quyền theo **descriptor đã biên dịch** và cấu hình runtime. Hai lớp cần thống nhất nhưng không có quan hệ tự động thay thế cho nhau.

## 13. Dùng liên kết Javadoc đúng phạm vi

Một trang module tốt nên liên kết đến entry point thay vì viết toàn bộ chi tiết ngay trong phần giới thiệu.

Ví dụ:

~~~java
/**
 * Module xử lý báo cáo.
 *
 * <p>Để tạo báo cáo, dùng
 * {@link com.acme.reporting.api.ReportGenerator}.
 *
 * <p>Tham khảo
 * {@link com.acme.reporting.api.ReportOptions}
 * để biết các tùy chọn cấu hình.
 */
module com.acme.reporting {
    exports com.acme.reporting.api;
}
~~~

`{@link ...}` tạo hyperlink tới type được Javadoc nhận diện. `{@code ...}` hiển thị đoạn code nhưng không tạo hyperlink. Nên chọn theo mục đích:

- Dùng `{@link Type}` cho type/method mà người đọc nên bấm vào.
- Dùng `{@code identifier}` cho module name, package name và cú pháp cần hiển thị đơn thuần.
- Dùng `<pre>{@code ...}</pre>` cho ví dụ đa dòng.
- Dùng `@see` khi muốn tạo mục tham khảo bổ sung.
- Dùng `@since` để ghi mốc API xuất hiện.

Nếu tài liệu phụ thuộc Java SE API, có thể liên kết tới Javadoc nền tảng bằng cấu hình liên kết ngoài của công cụ `javadoc`. Với module của thư viện bên ngoài, cần đảm bảo tài liệu đích tồn tại và cấu hình liên kết đúng version để tránh link hỏng.

## 14. Ghi chú compatibility và evolution trong module docs

Khi thay đổi module descriptor, hãy cập nhật Javadoc nếu thay đổi có ý nghĩa với consumer.

Ví dụ thay đổi:

~~~java
// Version cũ:
module com.acme.catalog {
    exports com.acme.catalog.api;
}
~~~

Sang:

~~~java
// Version mới:
module com.acme.catalog {
    exports com.acme.catalog.api;
    exports com.acme.catalog.spi;
    uses com.acme.catalog.spi.CatalogPlugin;
}
~~~

Tài liệu cấp module nên nói rõ SPI mới, thời điểm consumer có thể dùng và cách cài provider. `@since` trên SPI type có thể ghi đúng version API xuất hiện.

Nếu chuyển public API từ package này sang package khác, tài liệu nên chỉ ra package thay thế, deprecation policy và hướng migration. Chỉ viết `@deprecated` trong source không tự tạo khả năng tương thích nhị phân với code đã build trên descriptor cũ.

Những thay đổi cần đặc biệt chú ý trong public contract:

- Bỏ hoặc thu hẹp `exports`.
- Đổi module name.
- Đổi service interface trong `uses`/`provides`.
- Chuyển package từ export sang chỉ open.
- Đưa một kiểu của module khác vào public method signature, làm xuất hiện dependency mới.
- Đổi yêu cầu Java release hoặc runtime module.

Tài liệu có thể cảnh báo người dùng; còn migration thực tế vẫn cần release notes, build compatibility test và chiến lược versioning.

## 15. Kiểm tra nội dung tài liệu được sinh

Khi hoàn tất build tài liệu, nên kiểm tra bằng công cụ và bằng cách đọc đầu ra:

~~~bash
javadoc \
  --module-source-path src \
  --module com.acme.catalog \
  -d docs
~~~

Sau đó mở trang module summary trong `docs` để xem:

- Câu mô tả đầu tiên có giúp nhận diện mục đích module không?
- Liên kết tới public entry point có được tạo không?
- Phần service usages/providers có đúng với descriptor thực tế không?
- Package công khai có mô tả và package-info phù hợp không?
- Ví dụ `requires` có sử dụng đúng module name không?
- Tài liệu không vô tình giới thiệu package internal như API ổn định chứ?
- Nội dung Javadoc có được cập nhật khi dependency hoặc service contract thay đổi không?

Có thể bật cơ chế kiểm tra Javadoc tùy toolchain, ví dụ `-Xdoclint:all`, để phát hiện một số vấn đề tài liệu và markup:

~~~bash
javadoc -Xdoclint:all \
  --module-source-path src \
  --module com.acme.catalog \
  -d docs
~~~

Đây là kiểm tra chất lượng của quy trình build tài liệu tại dự án mẫu; nó không thay đổi module graph hoặc descriptor mà runtime sử dụng.

## 16. Những lỗi thường gặp khi viết Javadoc module

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không thấy phần giới thiệu trong trang Module | Dùng `//` hoặc `/* ... */` thay vì Javadoc `/** ... */`, hoặc comment đặt sai vị trí | Đặt Javadoc ngay trước `module` declaration |
| `javadoc` báo không tìm thấy type trong `{@link}` | Source/module path chưa chứa type tương ứng hoặc tên type sai | Kiểm tra fully qualified name và dependency khi sinh docs |
| API class có trang nhưng module summary không có mô tả | Chỉ viết Javadoc ở class, chưa viết ở `module-info.java` | Thêm Javadoc cấp module |
| Service được document nhưng không hoạt động | Có `@uses`/`@provides` mà thiếu directive tương ứng | Đồng bộ tag và descriptor |
| Module docs khuyên import package nhưng `javac` từ chối | Package không export cho consumer | Sửa public API boundary hoặc tài liệu hướng dẫn |
| Framework reflection thất bại dù module docs ghi “open” | Directive `opens` thiếu hoặc target module name sai | Kiểm tra descriptor, module thực thi reflection và runtime flags |
| Docs có ví dụ compile nhưng không chạy đúng | Ví dụ dùng module name/dependency khác artifact thực tế | Kiểm tra ví dụ trên module path phù hợp |
| Một module biến thành automatic module sau đóng gói | `module-info.class` không ở đúng vị trí hoặc bị build plugin bỏ sót | Dùng `jar --describe-module --file artifact.jar` kiểm tra |

## 17. Quy trình viết module documentation đề xuất

Một quy trình nhất quán khi phát hành thư viện modular:

1. **Chọn ranh giới module.** Xác định tên module, public packages, implementation packages và service contracts.
2. **Viết descriptor.** Khai báo đúng `requires`, `exports`, `opens`, `uses`, `provides`.
3. **Thêm Javadoc cấp module.** Mô tả purpose, entry point, public packages và integration.
4. **Thêm package-info.java.** Giải thích contract của các package public, nhất là API và SPI.
5. **Viết Javadoc cho public type.** Giải thích method contract, exception, nullability, lifecycle và thread-safety khi cần.
6. **Liên kết giữa các cấp.** Dùng `{@link}` để điều hướng từ module đến class/method.
7. **Tạo tài liệu.** Dùng `javadoc`, Maven Javadoc Plugin hoặc Gradle task tương ứng.
8. **Kiểm tra artifact.** Đảm bảo modular JAR vẫn chứa `module-info.class` hợp lệ.
9. **Cập nhật cùng thay đổi API.** Khi descriptor thay đổi, chỉnh module docs và release notes tương ứng.

Một nguyên tắc hữu ích: **mỗi directive quan trọng trong descriptor nên có lý do thiết kế mà người bảo trì hiểu được; mỗi lời hứa trong Javadoc cần được descriptor và public API hiện thực hóa.**

## Kết luận

`module-info.java` là hợp đồng kỹ thuật của named module; Javadoc ngay trước khai báo `module` là nơi giải thích hợp đồng đó cho người sử dụng. Nội dung tốt nên trình bày mục đích module, public API entry point, package export, giới hạn reflection, dependency đáng chú ý và service integration.

Hãy kết hợp Javadoc cấp module với `package-info.java` và Javadoc class/method để cung cấp tài liệu theo đúng cấp độ. Sử dụng `@uses` và `@provides` để giải thích service, nhưng nhớ rằng các tag chỉ mô tả; directive thật mới quyết định service metadata. Khi phát hành, sinh trang module bằng `javadoc` và kiểm tra artifact modular JAR để bảo đảm tài liệu và ranh giới JPMS nhất quán.
