# Module documentation với công cụ Javadoc

## 1. Module documentation là gì?

Module documentation là phần tài liệu HTML mô tả một named module trong Java Platform Module System (JPMS). Tài liệu giúp người dùng hiểu mục đích của module, API được công khai, các module mà nó yêu cầu, package được export, service mà module sử dụng hoặc cung cấp và các giới hạn tương thích.

Công cụ `javadoc` đọc documentation comment trong mã nguồn Java rồi tạo bộ trang HTML. Với dự án modular, tài liệu có thêm trang riêng cho từng module, thường là `module-summary.html`. Trang này mô tả module descriptor và liên kết tới package, type cùng các thành phần liên quan.

Module documentation có giá trị như một phần của hợp đồng phát hành:

- Người dùng biết module nào cần thêm vào module path.
- Người dùng biết package nào được hỗ trợ như API công khai.
- Người dùng biết service nào có thể được nạp bằng `ServiceLoader`.
- Người bảo trì biết module phụ thuộc vào những module nào và phiên bản nào.
- Nhóm phát triển có thể kiểm tra thay đổi API trước khi phát hành.

Javadoc không thay thế `module-info.java`. Các chỉ thị `requires`, `exports`, `opens`, `uses` và `provides` quyết định cấu trúc module; documentation comment giải thích ý nghĩa và cách sử dụng cấu trúc đó.

## 2. Các vị trí viết tài liệu cho một module

Tài liệu của module được hình thành từ nhiều loại documentation comment:

| Vị trí | Nội dung được mô tả | Trang HTML thường tạo |
|---|---|---|
| `module-info.java` | Mục đích module, dependency, package export, service use/provision và thông tin phát hành. | `module-summary.html` |
| `package-info.java` | Mục đích package, nhóm API và quy ước chung. | `package-summary.html` |
| Class/interface/enum/record | Vai trò, cách dùng, điều kiện và hành vi của type. | Trang type tương ứng. |
| Constructor/method/field | Tham số, giá trị trả về, exception và tác động phụ. | Phần summary/detail của trang type. |
| `overview.html` | Tổng quan cho toàn bộ bộ tài liệu, hướng dẫn và sơ đồ lớn. | `overview-summary.html` |

Đối với named module, comment đứng ngay trước khai báo `module` trong `module-info.java` là module description. Không đặt comment này ở trên một package declaration hoặc trong một class rồi mong Javadoc xem đó là mô tả module.

Ví dụ:

~~~java
/**
 * Provides the public API for creating greetings.
 *
 * <p>Applications can use the service interface to discover
 * a greeting provider at runtime.</p>
 *
 * @since 1.0
 */
module com.example.greeter.api {
    exports com.example.greeter.api;
}
~~~

Khi Javadoc xử lý module này, nội dung trên xuất hiện trong trang module summary.

## 3. Documentation comment trong module-info.java

Một documentation comment cho module nên giải thích những điều mà người dùng không thể hiểu đầy đủ chỉ từ tên module hoặc các directive:

- Module cung cấp chức năng gì và dành cho đối tượng nào.
- API nào được hỗ trợ và package nào được export.
- Dependency bắt buộc hoặc dependency tùy chọn có vai trò gì.
- Module có dùng hoặc cung cấp service nào.
- Những giới hạn về runtime, cấu hình hoặc phiên bản Java.
- Các thay đổi tương thích quan trọng giữa các phiên bản.

Ví dụ module API:

~~~java
/**
 * Provides the public API for greeting services.
 *
 * <p>Applications use {@link com.example.greeter.api.GreetingService}
 * to work with greeting providers without depending on an implementation.</p>
 *
 * @since 1.0
 */
module com.example.greeter.api {
    exports com.example.greeter.api;
}
~~~

Module description hỗ trợ HTML cơ bản trong Javadoc comment, có thể dùng paragraph, list và inline tags như `{@link ...}`, `{@code ...}`. Nên dùng link tới type quan trọng để người đọc đi thẳng tới API.

Không đưa thông tin bí mật, đường dẫn máy cá nhân, token hoặc cấu hình nội bộ vào tài liệu phát hành. Javadoc là tài liệu có thể được công bố cùng artifact.

## 4. Tài liệu cho uses và provides

JPMS hỗ trợ service provider thông qua hai directive:

- `uses service.Type;` khai báo module sử dụng một service.
- `provides service.Type with implementation.Type;` khai báo module cung cấp implementation của service.

Trong module documentation, có thể mô tả hai quan hệ này bằng block tags `@uses` và `@provides`.

### Mô tả module sử dụng service

~~~java
/**
 * Runs the greeting application.
 *
 * @uses com.example.greeter.api.GreetingService
 *       A service used to create the greeting shown to the user.
 */
module com.example.greeter.app {
    requires com.example.greeter.api;
    uses com.example.greeter.api.GreetingService;
}
~~~

Tag `@uses` giúp Javadoc hiển thị mục Uses trong phần Services của trang module. Tên service phải khớp với service type được khai báo trong directive `uses`.

### Mô tả module cung cấp service

~~~java
/**
 * Provides the default greeting implementation.
 *
 * @provides com.example.greeter.api.GreetingService with
 *           com.example.greeter.impl.DefaultGreetingService
 *           The built-in provider for the greeting service.
 *
 * @since 1.0
 */
module com.example.greeter.impl {
    requires com.example.greeter.api;

    provides com.example.greeter.api.GreetingService
        with com.example.greeter.impl.DefaultGreetingService;
}
~~~

Tag `@provides` mô tả service type, implementation được cung cấp và mục đích của provider. Directive `provides ... with ...` vẫn phải có trong module descriptor; documentation tag không tự tạo service provider.

Trang module summary có thể hiển thị phần Services với các nhóm Uses và Provides, giúp người đọc hiểu module tham gia vào service graph như thế nào.

## 5. Tài liệu package bằng package-info.java

Module documentation nên đi cùng package documentation. Package comment mô tả mục đích của package và các type công khai thuộc package đó.

Ví dụ `src/com.example.greeter.api/com/example/greeter/api/package-info.java`:

~~~java
/**
 * Defines the public service API for greeting providers.
 *
 * <p>Applications depend on these interfaces instead of depending
 * on a particular provider implementation.</p>
 *
 * @since 1.0
 */
package com.example.greeter.api;
~~~

Package documentation được gắn với package, không gắn với module. Một module có thể chứa nhiều package và mỗi package nên có mô tả rõ ràng nếu nó là một phần của API.

Đối với named module:

- Package được export thường là phần API người dùng cần xem trong tài liệu công khai.
- Package không export thường là implementation detail và có thể được loại khỏi tài liệu API.
- Khi cần tài liệu nội bộ cho nhóm phát triển, có thể yêu cầu Javadoc hiển thị tất cả package bằng `--show-packages all`.

`package-info.java` là cách tiêu chuẩn để viết package comment. Tệp `package.html` là cách cũ; nên ưu tiên `package-info.java` trong dự án hiện đại.

## 6. Ví dụ đầy đủ: tạo Javadoc cho ba module

Ví dụ gồm ba module:

- `com.example.greeter.api` khai báo interface service.
- `com.example.greeter.impl` cung cấp implementation.
- `com.example.greeter.app` sử dụng service qua `ServiceLoader`.

Cấu trúc nguồn:

~~~text
project/
└── src/
    ├── com.example.greeter.api/
    │   ├── module-info.java
    │   └── com/example/greeter/api/
    │       ├── package-info.java
    │       └── GreetingService.java
    ├── com.example.greeter.impl/
    │   ├── module-info.java
    │   └── com/example/greeter/impl/
    │       └── DefaultGreetingService.java
    └── com.example.greeter.app/
        ├── module-info.java
        └── com/example/greeter/app/
            └── Main.java
~~~

### Module API

Tệp `src/com.example.greeter.api/module-info.java`:

~~~java
/**
 * Provides the public API for greeting services.
 *
 * <p>Applications use the service interface without depending
 * on a concrete provider implementation.</p>
 *
 * @since 1.0
 */
module com.example.greeter.api {
    exports com.example.greeter.api;
}
~~~

Tệp `src/com.example.greeter.api/com/example/greeter/api/package-info.java`:

~~~java
/**
 * Defines the public service API for greeting providers.
 */
package com.example.greeter.api;
~~~

Tệp `src/com.example.greeter.api/com/example/greeter/api/GreetingService.java`:

~~~java
package com.example.greeter.api;

/**
 * Creates a greeting for a recipient.
 */
public interface GreetingService {

    /**
     * Returns a greeting for the given name.
     *
     * @param name recipient name
     * @return formatted greeting
     */
    String greet(String name);
}
~~~

### Module implementation

Tệp `src/com.example.greeter.impl/module-info.java`:

~~~java
/**
 * Provides the default implementation of the greeting service.
 *
 * @provides com.example.greeter.api.GreetingService with
 *           com.example.greeter.impl.DefaultGreetingService
 *           The built-in provider.
 *
 * @since 1.0
 */
module com.example.greeter.impl {
    requires com.example.greeter.api;

    provides com.example.greeter.api.GreetingService
        with com.example.greeter.impl.DefaultGreetingService;
}
~~~

Tệp `src/com.example.greeter.impl/com/example/greeter/impl/DefaultGreetingService.java`:

~~~java
package com.example.greeter.impl;

import com.example.greeter.api.GreetingService;

/**
 * Default provider that prefixes a name with {@code Hello}.
 */
public class DefaultGreetingService implements GreetingService {

    /** Creates the default provider. */
    public DefaultGreetingService() {
    }

    /**
     * {@inheritDoc}
     */
    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

### Module application

Tệp `src/com.example.greeter.app/module-info.java`:

~~~java
/**
 * Runs the greeting application using a discovered service provider.
 *
 * @uses com.example.greeter.api.GreetingService
 *       A service used to create the greeting shown to the user.
 *
 * @since 1.0
 */
module com.example.greeter.app {
    requires com.example.greeter.api;
    uses com.example.greeter.api.GreetingService;
}
~~~

Tệp `src/com.example.greeter.app/com/example/greeter/app/Main.java`:

~~~java
package com.example.greeter.app;

import com.example.greeter.api.GreetingService;
import java.util.ServiceLoader;

/**
 * Starts the greeting application.
 */
public class Main {

    /** Creates the application entry point. */
    public Main() {
    }

    /**
     * Loads a greeting provider and prints a greeting.
     *
     * @param args optional recipient name
     */
    public static void main(String[] args) {
        GreetingService service = ServiceLoader
                .load(GreetingService.class)
                .findFirst()
                .orElseThrow();

        String name = args.length == 0 ? "Java" : args[0];
        System.out.println(service.greet(name));
    }
}
~~~

### Biên dịch và chạy để kiểm tra ví dụ

Từ thư mục `project`:

~~~bash
mkdir -p mods

javac --release 17 \
  --module-source-path src \
  -d mods \
  --module com.example.greeter.api,com.example.greeter.impl,com.example.greeter.app
~~~

Chạy ứng dụng:

~~~bash
java --module-path mods \
  -m com.example.greeter.app/com.example.greeter.app.Main Ada
~~~

Stdout:

~~~text
Hello, Ada
~~~

Module app phải khai báo `uses com.example.greeter.api.GreetingService;` vì chính app gọi `ServiceLoader.load`. Module impl phải khai báo `provides ... with ...`. Chỉ viết `@uses` hoặc `@provides` trong Javadoc comment mà thiếu directive tương ứng sẽ không tạo quan hệ service lúc runtime.

## 7. Tạo tài liệu cho nhiều module bằng --module-source-path

Với source tree chứa nhiều module, dùng `--module-source-path` để chỉ định thư mục gốc chứa các thư mục module. Tùy chọn `--module` chọn module cần tạo tài liệu.

Lệnh tạo tài liệu API cho ba module trong ví dụ:

~~~bash
javadoc --release 17 \
  -encoding UTF-8 \
  -docencoding UTF-8 \
  -charset UTF-8 \
  --module-source-path src \
  --module com.example.greeter.api,com.example.greeter.impl,com.example.greeter.app \
  -d docs \
  --show-module-contents api \
  --show-packages exported \
  -Xdoclint:all \
  -Werror
~~~

Ý nghĩa:

- `--release 17` đặt mức tương thích source/API theo Java 17.
- `-encoding UTF-8` đọc mã nguồn theo UTF-8.
- `-docencoding UTF-8` đặt encoding của file HTML được tạo.
- `-charset UTF-8` khai báo charset trong tài liệu HTML.
- `--module-source-path src` tìm source của các module.
- `--module ...` chọn các module cần tạo tài liệu.
- `-d docs` đặt thư mục đầu ra.
- `--show-module-contents api` chọn mức hiển thị module declaration cho tài liệu API.
- `--show-packages exported` chỉ đưa các package được export vào phần package documentation.
- `-Xdoclint:all` bật các nhóm kiểm tra documentation.
- `-Werror` khiến cảnh báo Javadoc làm build thất bại.

Dùng cùng một lệnh cho các module giúp tài liệu có cấu trúc và mức kiểm tra nhất quán. Với dự án lớn, có thể đưa các tùy chọn vào file argument rồi truyền tên file bằng `@options.txt`.

## 8. --module-path và --module-source-path khác nhau thế nào?

Hai tùy chọn này giải quyết hai nguồn module khác nhau:

| Tùy chọn | Nguồn dữ liệu | Khi sử dụng |
|---|---|---|
| `--module-source-path` | Cây mã nguồn của nhiều named module. | Khi Javadoc phải đọc `module-info.java` và source của các module trong dự án. |
| `--module-path` hoặc `-p` | Modular JAR hoặc exploded module đã có. | Khi source đang được tài liệu hóa tham chiếu tới module phụ thuộc đã build sẵn. |
| `--class-path` hoặc `-cp` | Class file và JAR trên classpath. | Khi tài liệu hóa mã nguồn có dependency ở unnamed module hoặc thư viện cũ. |

Ví dụ khi module app tham chiếu tới một module thư viện đã đóng gói:

~~~bash
javadoc --release 17 \
  --module-source-path src \
  --module-path lib \
  --module com.example.greeter.app \
  -d docs
~~~

`lib` chứa modular JAR hoặc module đã biên dịch mà Javadoc cần phân giải khi đọc source. Không dùng `--module-path` thay cho `--module-source-path` khi mục tiêu là tìm mã nguồn của các module đang cần tạo tài liệu.

Nếu một dependency không thể phân giải, kiểm tra module name trong `requires`, vị trí JAR và module path. Tên file JAR không nhất thiết giống tên module khai báo bên trong.

## 9. Mở rộng tập module được tài liệu hóa

Mặc định, Javadoc chỉ tạo tài liệu cho các module được chỉ định tường minh trên command line. Có thể mở rộng tập module bằng `--expand-requires`:

~~~bash
# Bao gồm các dependency được khai báo bằng requires transitive
javadoc --module-source-path src \
  --module com.example.greeter.app \
  --expand-requires transitive \
  -d docs

# Bao gồm toàn bộ dependency của các module được chọn
javadoc --module-source-path src \
  --module com.example.greeter.app \
  --expand-requires all \
  -d docs
~~~

Giá trị:

- `transitive` bổ sung các module được yêu cầu qua quan hệ `requires transitive`.
- `all` bổ sung tất cả module dependency của module đã chọn.
- Không dùng `--expand-requires` thì chỉ các module được chọn tường minh được tài liệu hóa.

Tùy chọn này có thể làm bộ tài liệu lớn hơn đáng kể. Chỉ mở rộng khi người đọc cần xem cả tài liệu dependency trong cùng bộ HTML; nếu không, dùng `--link` để dẫn tới tài liệu đã phát hành của dependency.

## 10. Chọn mức độ chi tiết của module và package

Javadoc cung cấp các tùy chọn để điều khiển phạm vi tài liệu.

| Tùy chọn | Giá trị | Tác dụng |
|---|---|---|
| `--show-module-contents` | `api` hoặc `all` | Chọn mức chi tiết của module declaration được hiển thị. |
| `--show-packages` | `exported` hoặc `all` | Chỉ hiển thị package được export hoặc mọi package trong module. |
| `--show-types` | `public`, `protected`, `package`, `private` | Chọn mức truy cập của class, interface, enum, record và các type. |
| `--show-members` | `public`, `protected`, `package`, `private` | Chọn mức truy cập của field, constructor và method được hiển thị. |

Tài liệu API công khai thường dùng:

~~~bash
javadoc --module-source-path src \
  --module com.example.greeter.api,com.example.greeter.app \
  --show-module-contents api \
  --show-packages exported \
  --show-types protected \
  --show-members protected \
  -d docs-api
~~~

Tài liệu nội bộ có thể dùng:

~~~bash
javadoc --module-source-path src \
  --module com.example.greeter.api,com.example.greeter.impl,com.example.greeter.app \
  --show-module-contents all \
  --show-packages all \
  --show-types private \
  --show-members private \
  -d docs-internal
~~~

Có thể dùng các mức truy cập shorthand `-public`, `-protected`, `-package` và `-private`. Với named module, `-private` bao gồm mọi package và chi tiết module. Các tùy chọn `--show-*` giúp mô tả rõ mục tiêu hơn khi build tài liệu API và tài liệu nội bộ thành hai bộ riêng.

Không nên đưa package implementation vào tài liệu API công khai nếu package đó không được export và không phải contract hỗ trợ cho người dùng module.

## 11. Đọc cấu trúc HTML do Javadoc tạo ra

Khi chạy Javadoc cho nhiều named module, thư mục output có dạng:

~~~text
docs/
├── index.html
├── overview-summary.html
├── index-all.html
├── com.example.greeter.api/
│   ├── module-summary.html
│   └── com/example/greeter/api/
│       ├── package-summary.html
│       └── GreetingService.html
├── com.example.greeter.impl/
│   └── module-summary.html
└── com.example.greeter.app/
    └── module-summary.html
~~~

Các trang quan trọng:

- `index.html`: trang điều hướng chính.
- `overview-summary.html`: phần tổng quan cho toàn bộ bộ tài liệu.
- `module-summary.html`: mô tả module, directive, service và package liên quan.
- `package-summary.html`: mô tả package.
- Trang class/interface: mô tả type, method, constructor và field.
- `index-all.html`: chỉ mục tra cứu các thành phần.

Mỗi module có thư mục riêng được đặt theo module name. Khi có nhiều module cùng package name, đường dẫn theo module giúp phân biệt tài liệu của từng module.

Với module có `@uses` hoặc `@provides`, trang module summary có thể có phần Services chia thành Uses và Provides. Mục này giúp người đọc nhìn thấy vai trò của module trong service graph.

## 12. Viết documentation comment và liên kết API

Documentation comment nên mô tả hợp đồng quan sát được từ phía người dùng, không chỉ lặp lại tên method.

Ví dụ method có tài liệu đầy đủ:

~~~java
/**
 * Returns a greeting for the given recipient.
 *
 * <p>The result is suitable for display and is never {@code null}.</p>
 *
 * @param name recipient name; must not be {@code null}
 * @return formatted greeting
 * @throws IllegalArgumentException if {@code name} is blank
 * @see GreetingService
 * @since 1.0
 */
String greet(String name);
~~~

Các tags thường dùng:

- `@param` mô tả tham số.
- `@return` mô tả giá trị trả về.
- `@throws` hoặc `@exception` mô tả exception có thể được ném.
- `@see` tạo tham chiếu tới API liên quan.
- `@since` ghi phiên bản API được giới thiệu.
- `@deprecated` giải thích API đã lỗi thời và gợi ý thay thế.
- `{@link ...}` tạo liên kết tới type hoặc member.
- `{@code ...}` định dạng tên code trong văn bản.
- `{@inheritDoc}` kế thừa nội dung documentation từ method được override.

Câu đầu tiên của documentation comment thường được dùng làm phần summary trong trang index và danh sách method. Viết câu đầu rõ ràng, có chủ ngữ và mô tả tác dụng. Phần còn lại có thể giải thích chi tiết, ví dụ và điều kiện sử dụng.

Với API công khai, nên mô tả nullability, thread safety, thứ tự xử lý, side effect, giới hạn tài nguyên và exception khi những yếu tố này là một phần của contract.

## 13. Liên kết tới tài liệu của module khác

Khi module dùng API của JDK hoặc thư viện khác, Javadoc có thể tạo liên kết tới bộ tài liệu HTML đã phát hành của dependency.

Dùng `-link` khi máy build có thể truy cập URL tài liệu:

~~~bash
javadoc --module-source-path src \
  --module com.example.greeter.api \
  --link https://docs.oracle.com/en/java/javase/17/docs/api/ \
  -d docs
~~~

Dùng `-linkoffline` khi muốn liên kết tới URL tài liệu nhưng package list được lưu cục bộ:

~~~bash
javadoc --module-source-path src \
  --module com.example.greeter.api \
  -linkoffline https://docs.example.com/library/ ./offline-library-docs \
  -d docs
~~~

`-linkoffline` nhận hai giá trị: URL mà tài liệu sẽ liên kết tới và thư mục cục bộ chứa danh sách package/module của bộ tài liệu đích. Điều này hữu ích trong CI không có internet hoặc khi build từ tài liệu dependency đã tải trước.

Nếu dependency có module documentation riêng, liên kết tới đúng phiên bản docs để tránh link tới API không tồn tại trong artifact đang dùng. Không dùng `--expand-requires all` chỉ để giải quyết liên kết chéo nếu dependency đã có bộ tài liệu được phát hành.

## 14. Overview, tài nguyên và stylesheet

Có thể tạo trang overview cho toàn bộ bộ tài liệu bằng file HTML:

~~~html
<!-- overview.html -->
<h1>Greeter Platform</h1>
<p>Documentation for the public greeting modules.</p>
~~~

Truyền file vào Javadoc:

~~~bash
javadoc --module-source-path src \
  --module com.example.greeter.api,com.example.greeter.impl,com.example.greeter.app \
  -overview overview.html \
  -d docs
~~~

Các tùy chọn bổ sung:

- `-overview file` dùng nội dung HTML làm phần tổng quan.
- `-docfilessubdirs` sao chép đệ quy thư mục `doc-files` trong package.
- `--main-stylesheet file` thay stylesheet chính của tài liệu.
- `--add-stylesheet file` thêm stylesheet bổ sung.
- `-windowtitle text` đặt tiêu đề cửa sổ trình duyệt.
- `-doctitle html` đặt tiêu đề trang overview.
- `-taglet` và `-tag` hỗ trợ taglet hoặc custom tag khi dự án có quy ước tài liệu riêng.

Dùng thư mục `doc-files` cho hình minh họa, sơ đồ hoặc ví dụ tĩnh gắn với package/type. Kiểm tra các file được copy đúng đường dẫn trong output HTML và không tham chiếu tới file chỉ tồn tại trên máy build.

## 15. Kiểm tra tài liệu bằng DocLint

Javadoc có DocLint để kiểm tra chất lượng documentation comment. Các nhóm kiểm tra gồm:

| Nhóm | Nội dung |
|---|---|
| `accessibility` | Các vấn đề liên quan khả năng truy cập của HTML. |
| `html` | Cấu trúc và cú pháp HTML trong comment. |
| `missing` | Tài liệu hoặc tag bắt buộc còn thiếu theo mức kiểm tra. |
| `reference` | Tham chiếu tới type/member không hợp lệ hoặc không tìm thấy. |
| `syntax` | Cú pháp documentation comment và inline/block tag. |

Bật tất cả nhóm:

~~~bash
javadoc --module-source-path src \
  --module com.example.greeter.api,com.example.greeter.impl,com.example.greeter.app \
  -Xdoclint:all \
  -Werror \
  -d docs
~~~

`-Werror` khiến warning làm lệnh thất bại. Đây là lựa chọn hữu ích cho CI vì tài liệu thiếu hoặc liên kết sai được phát hiện trước khi phát hành.

Nếu dự án cũ có nhiều warning về tài liệu còn thiếu, có thể tạm tắt riêng nhóm missing trong giai đoạn chuyển đổi:

~~~bash
javadoc --module-source-path src \
  --module com.example.greeter.api \
  -Xdoclint:all,-missing \
  -d docs
~~~

Không nên tắt toàn bộ DocLint để che lỗi HTML hoặc liên kết. Hãy đặt mục tiêu bổ sung comment còn thiếu rồi bật lại `-Xdoclint:all -Werror`.

Có thể giới hạn DocLint cho package bằng `-Xdoclint/package:...` khi cần xử lý dần một codebase lớn. Sau mỗi lần thay đổi, kiểm tra warning thực tế và giữ cấu hình thống nhất giữa local build và CI.

## 16. Tích hợp Javadoc vào quy trình build

Javadoc nên được tạo từ cùng source revision và cùng module graph với artifact phát hành.

Một quy trình CI điển hình:

~~~bash
# Biên dịch tất cả module
javac --release 17 \
  --module-source-path src \
  -d mods \
  --module com.example.greeter.api,com.example.greeter.impl,com.example.greeter.app

# Chạy Javadoc cho các module
javadoc --release 17 \
  -encoding UTF-8 \
  -docencoding UTF-8 \
  -charset UTF-8 \
  --module-source-path src \
  --module com.example.greeter.api,com.example.greeter.impl,com.example.greeter.app \
  --show-module-contents api \
  --show-packages exported \
  -Xdoclint:all \
  -Werror \
  -d build/javadoc

# Kiểm tra ứng dụng sau khi build
java --module-path mods \
  -m com.example.greeter.app/com.example.greeter.app.Main Ada
~~~

Nên:

- Cố định JDK/toolchain và `--release`.
- Dùng UTF-8 nhất quán cho source và output.
- Chọn module API công khai rõ ràng; tạo bộ tài liệu nội bộ riêng nếu cần.
- Bật DocLint và xử lý warning trước khi phát hành.
- Lưu thư mục Javadoc như một build artifact có version.
- Kiểm tra các external link trong môi trường CI.
- Kiểm tra HTML output sau khi đổi module name hoặc package name.
- Không tạo tài liệu từ class file cũ hoặc source revision khác với artifact.

Với Maven hoặc Gradle, cấu hình task Javadoc để nhận đúng source set/module source path và module path mà compile task đang sử dụng. Không giả định task Javadoc tự động dùng đúng module path chỉ vì compile task thành công; kiểm tra lệnh thực tế trong build log khi gặp lỗi phân giải.

## 17. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không tạo trang `module-summary.html` | Không chọn named module hoặc source path không chứa module descriptor. | Kiểm tra `--module`, `--module-source-path` và vị trí `module-info.java`. |
| Module description trống | Thiếu documentation comment ngay trước khai báo `module`. | Thêm `/** ... */` trong `module-info.java`. |
| Trang module không có phần Uses/Provides mong đợi | Thiếu directive hoặc module comment thiếu `@uses`/`@provides`. | Kiểm tra cả module descriptor và documentation tags. |
| Không tìm thấy type trong module phụ thuộc | Module dependency không nằm trên module path hoặc source path. | Đặt dependency đã build vào `--module-path`; dùng `--module-source-path` cho source modules. |
| Package nội bộ không xuất hiện | Chỉ tạo tài liệu cho package được export. | Dùng `--show-packages all` cho tài liệu nội bộ. |
| Type/member không xuất hiện | Mức truy cập đang giới hạn phạm vi tài liệu. | Điều chỉnh `--show-types` và `--show-members`. |
| Link tới dependency bị hỏng | URL docs sai phiên bản hoặc bộ tài liệu đích không có element list. | Kiểm tra `-link` hoặc `-linkoffline` và đúng phiên bản docs. |
| Javadoc thất bại vì warning | Thiếu `@param`, `@return`, comment constructor hoặc HTML sai. | Sửa comment và chạy lại `-Xdoclint:all -Werror`. |
| HTML hiển thị sai tiếng Việt | Encoding đầu vào hoặc output không thống nhất. | Dùng `-encoding UTF-8`, `-docencoding UTF-8` và `-charset UTF-8`. |
| `@uses`/`@provides` hiển thị nhưng runtime không tìm thấy service | Chỉ viết documentation tag mà thiếu directive trong descriptor, hoặc provider không nằm trong module path. | Khai báo đúng `uses`/`provides` và kiểm tra service provider module. |
| Javadoc tạo tài liệu cho quá nhiều module | Dùng `--expand-requires all` hoặc chọn quá nhiều root modules. | Chỉ định module cần tài liệu và chọn mức expand phù hợp. |
| Tài liệu nội bộ bị đưa vào site công khai | Dùng `--show-packages all` hoặc visibility quá rộng cho bộ public docs. | Tạo hai bộ docs riêng: API public và internal. |

## 18. Checklist trước khi phát hành module documentation

- Mỗi named module có module description trong `module-info.java`.
- Module comment mô tả rõ mục đích, phạm vi API và dependency quan trọng.
- Các directive `requires`, `exports`, `opens`, `uses` và `provides` khớp với mô tả.
- Module dùng service có `@uses` và module cung cấp service có `@provides` khi cần giải thích service contract.
- Mỗi package được export có package documentation phù hợp.
- Các type và member công khai có comment mô tả hành vi, tham số, return value và exception.
- Các liên kết `{@link ...}` và external links hoạt động.
- Đã chọn đúng module bằng `--module` và đúng nguồn bằng `--module-source-path`.
- Đã chọn đúng mức hiển thị bằng `--show-module-contents`, `--show-packages`, `--show-types` và `--show-members`.
- Đã chạy `-Xdoclint:all -Werror` hoặc có kế hoạch xử lý warning rõ ràng.
- HTML output có trang `module-summary.html` cho từng module dự kiến.
- Đã kiểm tra trang module, package, type, service summary và tài nguyên tĩnh.
- Bộ tài liệu được tạo từ cùng revision và JDK release với artifact phát hành.

## 19. Tài liệu tham khảo

- [The javadoc Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javadoc.html)
- [Java Documentation Comments Specification](https://docs.oracle.com/en/java/javase/24/docs/specs/javadoc/doc-comment-spec.html)

Module documentation giúp người dùng hiểu module như một đơn vị API và dependency độc lập. Hãy viết module description trong `module-info.java`, mô tả package bằng `package-info.java`, ghi rõ service tags, rồi tạo tài liệu nhiều module bằng `--module-source-path` và `--module`. Bật DocLint trong CI và kiểm tra trang `module-summary.html` của từng module trước khi phát hành.
