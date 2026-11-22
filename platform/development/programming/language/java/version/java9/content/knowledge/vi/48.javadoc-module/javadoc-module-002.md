# Lựa chọn mô-đun, package và kiểu cần xuất tài liệu bằng Javadoc (Java 9+)

## Mục tiêu

Sau bài này, bạn có thể chọn chính xác **mô-đun (module)**, **package** và **kiểu (type: class, interface, enum, record...)** để tạo tài liệu API; phân biệt **phạm vi nguồn cần đưa vào** với **mức truy cập được hiển thị**; sử dụng `javadoc` cho ứng dụng có `module-info.java`; tạo tài liệu công khai và tài liệu nội bộ theo hai chính sách riêng; và kiểm tra kết quả đầu ra để tránh công bố nhầm các thành phần triển khai.

Bài sử dụng **Javadoc của JDK hiện đại** cùng Java Platform Module System (JPMS), xuất hiện từ Java 9 và vẫn được áp dụng trong Java 17/21+. Các tùy chọn `--module`, `--module-source-path`, `--show-packages`, `--show-types`, `--show-members`, `--show-module-contents`, `--expand-requires`, `--source-path` và `-subpackages` là những cơ chế hiện hành của Javadoc. Không cần các chế độ HTML frames hoặc thủ thuật công cụ cũ.

## 1. Ba tầng chọn nội dung và một tầng hiển thị

Phần quan trọng nhất là hiểu **hai nhóm quyết định độc lập**:

1. **Chọn nguồn/phạm vi:** đưa mô-đun nào, package nào hoặc tệp `.java` nào vào lần chạy Javadoc. Những lựa chọn này đến từ đối số `--module`, tên package, `-subpackages` hoặc đường dẫn source file.
2. **Lọc thành phần được trình bày:** sau khi đã chọn nguồn, chỉ hiện các package được export hay cả package nội bộ; chỉ hiện type `public` hay cả package-private; và chỉ hiện member ở mức truy cập nào. Những lựa chọn này đến từ nhóm `--show-*`.

Sơ đồ:

```text
Các source root chứa module-info.java và *.java
                       |
            Chọn mô-đun / package / tệp
                       |
            Lọc package exported/all
                       |
            Lọc type public/protected/package/private
                       |
            Lọc member public/protected/package/private
                       |
              Javadoc standard doclet
                       |
      HTML: module-summary / package-summary / Type.html
```

Ví dụ, yêu cầu **“chỉ xuất tài liệu public của mô-đun thư viện”** khác yêu cầu **“chỉ xuất tài liệu một class public”**:

- Trường hợp đầu: chọn cả module bằng `--module`, lọc `--show-packages exported --show-types public --show-members public`.
- Trường hợp sau: truyền **đường dẫn đến một tệp nguồn Java cụ thể**. Việc chỉ thêm `--show-types public` **không** có nghĩa chỉ còn một class: nó vẫn chọn **mọi public type** thuộc phạm vi đã chọn.

Javadoc là công cụ **sinh tài liệu tĩnh**. Nó không sửa mã, không thay đổi câu lệnh `exports`, `opens` hoặc `requires` trong `module-info.java`, không biến package-private thành public, và không ngăn người dùng truy cập một API đã thật sự được công bố trong chương trình.

## 2. Cơ sở mô-đun: `module-info.java`, package và type

Một mô-đun có tên được khai báo bằng `module-info.java`:

```java
/** Provides a small calculator API for external callers. */
module com.example.catalog {
    exports com.example.catalog.api;
}
```

Trong đó:

- `com.example.catalog` là **tên module**, không phải tên package.
- `com.example.catalog.api` là package được **export**. Các public type trong package này có thể trở thành bề mặt API cho module khác có quyền đọc module, tùy quan hệ đọc và các điều kiện truy cập còn lại.
- Package `com.example.catalog.internal` không được export, dù có class khai báo `public`. Một class `public` nằm trong package không export **không tự trở thành public API cho module khác**.
- `opens` có ý nghĩa mở truy cập phản chiếu (*deep reflection*) theo quy tắc JPMS; nó **không tương đương** việc công khai package thành API biên dịch bằng `exports`.
- `requires` biểu diễn phụ thuộc module. Một module phụ thuộc có thể cần để Javadoc phân tích liên kết kiểu, nhưng **không mặc nhiên là module cần xuất tài liệu HTML**.

Ngoài `module-info.java`, hai nguồn mô tả thông dụng là:

- `package-info.java`: ghi mô tả tổng quan package; Javadoc sử dụng nó cho trang `package-summary.html`.
- Phần `/** ... */` đặt ngay trước class, interface, record, enum, constructor, field hoặc method: cung cấp phần mô tả cho từng API element.

**Nguyên tắc chọn loại tài liệu:** nếu trang dành cho người dùng thư viện, ưu tiên các module/API package được export và type cần thiết cho người dùng. Nếu trang dành cho đội phát triển, có thể cần cả package nội bộ và các type/member không public; khi ấy phải phát hành tài liệu qua kênh nội bộ.

## 3. Cấu trúc dự án ví dụ: hai module và hai loại package

Ta sẽ dùng một dự án Java nhỏ đủ để quan sát sự khác biệt giữa **public API** và **implementation**:

```text
project/
└── src/
    ├── com.example.catalog/
    │   ├── module-info.java
    │   └── com/example/catalog/
    │       ├── api/
    │       │   ├── package-info.java
    │       │   ├── Calculator.java
    │       │   └── PackageOnly.java
    │       └── internal/
    │           ├── package-info.java
    │           └── InternalCodec.java
    └── com.example.app/
        ├── module-info.java
        └── com/example/app/
            ├── package-info.java
            └── Launcher.java
```

Tất cả lệnh bên dưới chạy ở thư mục `project/`. Đây là layout **`src/<module-name>/<package-path>`**; đường dẫn `--module-source-path src` đúng với layout này. Với Maven/Gradle nhiều module và source root ở `src/main/java`, phải thay bằng đường dẫn hoặc pattern phù hợp, **không sao chép nguyên lệnh khi cấu trúc thư mục khác**.

### 3.1. Module thư viện và package API

Tệp `src/com.example.catalog/module-info.java`:

```java
/** Provides a small calculator API for external callers. */
module com.example.catalog {
    exports com.example.catalog.api;
}
```

Tệp `src/com.example.catalog/com/example/catalog/api/package-info.java`:

```java
/** Stable API for calculator operations. */
package com.example.catalog.api;
```

Tệp `src/com.example.catalog/com/example/catalog/api/Calculator.java`:

```java
package com.example.catalog.api;

/** Public calculator service. */
public class Calculator {
    /** Creates a calculator. */
    public Calculator() { }

    /**
     * Adds two numbers.
     *
     * @param a first operand
     * @param b second operand
     * @return sum of a and b
     */
    public int add(int a, int b) { return a + b; }

    /**
     * Operation intended for subclasses.
     *
     * @param number input
     * @return twice the input
     */
    protected int twice(int number) { return number * 2; }

    /**
     * Package implementation detail.
     *
     * @return offset
     */
    int packageOffset() { return 0; }

    /**
     * Private implementation detail.
     *
     * @return internal value
     */
    private int secret() { return 0; }
}
```

Type `Calculator` là `public` nhưng các member có bốn mức truy cập: constructor và `add` là `public`; `twice` là `protected`; `packageOffset` là package-private; `secret` là `private`. Vì vậy đây là mẫu tốt để phân biệt `--show-types` và `--show-members`.

Tệp `src/com.example.catalog/com/example/catalog/api/PackageOnly.java`:

```java
package com.example.catalog.api;

/** Package-private helper; intentionally excluded from public API. */
final class PackageOnly {
    /** Creates an internal helper. */
    PackageOnly() { }
}
```

Dù `PackageOnly` nằm trong **package đã export**, bản thân nó không có modifier `public`. Bởi vậy, khi chọn `--show-types public`, type này vẫn không được đưa vào tài liệu.

### 3.2. Package không export

Tệp `src/com.example.catalog/com/example/catalog/internal/package-info.java`:

```java
/** Internal implementation details, not exported by the module. */
package com.example.catalog.internal;
```

Tệp `src/com.example.catalog/com/example/catalog/internal/InternalCodec.java`:

```java
package com.example.catalog.internal;

/** Internal type in a package that the module does not export. */
public final class InternalCodec {
    private InternalCodec() { }

    /**
     * Encodes an integer.
     *
     * @param value number to encode
     * @return decimal form of the integer
     */
    public static String encode(int value) {
        return Integer.toString(value);
    }
}
```

`InternalCodec` là `public` ở **cấp type** nhưng package của nó **không export**. Nếu xuất tài liệu API công khai với `--show-packages exported`, trang của class này phải vắng mặt. Nếu xuất tài liệu nội bộ với `--show-packages all`, trang này có thể xuất hiện; việc có trang tài liệu **không làm class được export**.

### 3.3. Module ứng dụng dùng API công khai

Tệp `src/com.example.app/module-info.java`:

```java
/** Example module that consumes the calculator API. */
module com.example.app {
    requires com.example.catalog;
    exports com.example.app;
}
```

Tệp `src/com.example.app/com/example/app/package-info.java`:

```java
/** Demo client entry point. */
package com.example.app;
```

Tệp `src/com.example.app/com/example/app/Launcher.java`:

```java
package com.example.app;

import com.example.catalog.api.Calculator;

/** Simple public entry point. */
public final class Launcher {
    private Launcher() { }

    /**
     * Runs the demonstration.
     *
     * @param args unused command-line arguments
     */
    public static void main(String[] args) {
        System.out.println(new Calculator().add(1, 2));
    }
}
```

Lệnh biên dịch và chạy độc lập của mẫu (dùng JDK 17 trở lên):

```bash
javac --release 17 -encoding UTF-8 -d out --module-source-path src --module com.example.catalog,com.example.app
java --module-path out --module com.example.app/com.example.app.Launcher
```

Stdout:

```text
3
```

Ở đây `javac` biên dịch module, còn `java --module-path out --module module/name.of.MainClass` chạy ứng dụng. **Đây không phải lệnh xuất tài liệu**; nó chỉ xác nhận source hợp lệ, package đã export có thể được module khác sử dụng và cấu trúc nguồn đủ nhất quán trước khi dùng Javadoc.

## 4. Trường hợp A — xuất tài liệu public cho đúng một module

Lệnh:

```bash
javadoc -quiet -Werror -Xdoclint:all -encoding UTF-8 -d docs/public --module-source-path src --module com.example.catalog --show-packages exported --show-types public --show-members public --show-module-contents api
```

Giải thích các tham số:

| Tham số | Ý nghĩa |
| --- | --- |
| `--module-source-path src` | Cho Javadoc biết nơi tìm source của các named module. |
| `--module com.example.catalog` | Chọn **một module** để đưa vào bộ tài liệu. |
| `--show-packages exported` | Chỉ lấy package đã export của module được chọn. |
| `--show-types public` | Trong các package đã chọn, chỉ công bố các type `public`. |
| `--show-members public` | Trong các type được đưa vào, chỉ công bố member `public`. |
| `--show-module-contents api` | Ở trang module, trình bày thông tin ở mức API thay vì chi tiết đầy đủ tất cả directive của module. |
| `-d docs/public` | Ghi HTML vào thư mục đích riêng. |
| `-encoding UTF-8` | Giải mã source/comment theo UTF-8 để giữ dấu tiếng Việt đúng. |
| `-Xdoclint:all -Werror` | Kiểm tra chất lượng Javadoc comment và coi warning là lỗi trong lần xuất bản này. |
| `-quiet` | Bớt thông báo tiến trình; warning/error vẫn được báo. |

Sau khi chạy thành công, các tệp quan trọng gồm:

```text
docs/public/com.example.catalog/module-summary.html
docs/public/com.example.catalog/com/example/catalog/api/package-summary.html
docs/public/com.example.catalog/com/example/catalog/api/Calculator.html
```

Hai trang sau **không được sinh** trong cấu hình public:

```text
docs/public/com.example.catalog/com/example/catalog/api/PackageOnly.html
docs/public/com.example.catalog/com/example/catalog/internal/InternalCodec.html
```

Hai nguyên nhân khác nhau: `PackageOnly` bị lọc vì **không public**; `InternalCodec` bị lọc vì **package không export**. Đây chính là hai tầng bộ lọc mà bài học yêu cầu phân biệt.

Trong `Calculator.html`, phương thức `add` xuất hiện; `twice` (protected), `packageOffset` (package-private) và `secret` (private) không được mô tả như các member public được chọn.

Để công bố API ra bên ngoài, việc chọn module, package và access level phải khớp với **hợp đồng phiên bản API** của thư viện, không chỉ với cấu trúc thư mục hiện tại.

## 5. Trường hợp B — xuất tài liệu đầy đủ hơn cho nhóm bảo trì nội bộ

Lệnh:

```bash
javadoc -quiet -Werror -Xdoclint:all -encoding UTF-8 -d docs/internal --module-source-path src --module com.example.catalog --show-packages all --show-types package --show-members package --show-module-contents all
```

Lần này:

- `--show-packages all` lấy cả `com.example.catalog.internal`, dù package không export.
- `--show-types package` lấy các type ở mức package-private trở lên, bao gồm `PackageOnly`.
- `--show-members package` cho thấy public, protected và package-private members trong những type đã được chọn; riêng `secret()` là private nên vẫn bị loại.
- `--show-module-contents all` cho phép trang mô-đun trình bày chi tiết các directive của module, thay vì chỉ phần liên quan API được công bố.

Vì vậy, đầu ra nội bộ có thêm ít nhất:

```text
docs/internal/com.example.catalog/com/example/catalog/api/PackageOnly.html
docs/internal/com.example.catalog/com/example/catalog/internal/InternalCodec.html
```

Nếu nhóm bảo trì thực sự cần tài liệu cho cả private type và private member, dùng `--show-types private --show-members private` và cân nhắc mức độ nhạy cảm của tài liệu. **Không** sử dụng bộ cờ nội bộ để phát hành công khai một cách vô thức: tài liệu có thể tiết lộ thiết kế triển khai, điểm mở rộng hoặc các cấu trúc chưa có cam kết tương thích.

Tài liệu nội bộ mở rộng phạm vi mô tả **mã nguồn**, không thay đổi khả năng truy cập thực của module khác lúc biên dịch/chạy. `InternalCodec` vẫn ở trong package không export.

## 6. Trường hợp C — chọn nhiều module cụ thể

Khi tạo tài liệu chung cho thư viện và ứng dụng trong ví dụ:

```bash
javadoc -quiet -d docs/two --module-source-path src --module com.example.catalog,com.example.app
```

Cả hai trang module được tạo:

```text
docs/two/com.example.catalog/module-summary.html
docs/two/com.example.app/module-summary.html
```

Các module trong danh sách `--module` được phân cách bằng **dấu phẩy**. Mặc định Javadoc chỉ coi các module được nêu tường minh là module sẽ được viết tài liệu, **không** tự tạo tài liệu riêng cho mọi module trong đồ thị `requires`.

Một ví dụ khác khi thực sự muốn đưa dependency vào phạm vi tài liệu:

```bash
javadoc -d docs/with-dependencies --module-source-path src --module com.example.app --expand-requires all
```

`--expand-requires transitive` mở rộng phạm vi theo các phụ thuộc `requires transitive` (bao gồm bao đóng transitive); `--expand-requires all` còn thêm các phụ thuộc trực tiếp theo cơ chế được mô tả trong tài liệu Javadoc. Đây là **tùy chọn mở rộng các module được viết tài liệu**. Nó khác `--module-path`, vốn dùng để giúp công cụ tìm và phân giải module phụ thuộc đã có, chứ **không tự nói rằng các module đó cũng phải được xuất thành trang tài liệu**.

Nếu làm tài liệu cho SDK có API rõ ràng, thường nên liệt kê chính xác các module cần phát hành. Mở rộng dependency chỉ khi bạn có chủ đích và quyền phân phối tài liệu của những module liên quan.

## 7. Trường hợp D — chỉ xuất một package

Khi chỉ muốn tài liệu cho `com.example.catalog.api`, có thể trỏ `--source-path` đến **source root của đúng một module** rồi cung cấp tên package:

```bash
javadoc -quiet -d docs/package --source-path src/com.example.catalog --show-types package com.example.catalog.api
```

Kết quả có:

```text
docs/package/com.example.catalog/com/example/catalog/api/package-summary.html
docs/package/com.example.catalog/com/example/catalog/api/Calculator.html
docs/package/com.example.catalog/com/example/catalog/api/PackageOnly.html
```

Và **không** có `InternalCodec.html` vì package của nó không nằm trong danh sách được chọn. Ở đây `--show-types package` cho phép thấy `PackageOnly` trong package đã chọn. Nếu cần một package chỉ có public types, đổi thành `--show-types public`.

**Lưu ý cú pháp đã kiểm chứng:** đừng giả định có thể truyền một tên package trực tiếp sau `--module-source-path src` và Javadoc sẽ tự suy ra module chứa nó:

```bash
# Không phải lựa chọn ổn định cho cấu trúc src/<module>/... của ví dụ:
javadoc -d docs/problem --module-source-path src com.example.catalog.api
```

Với layout ví dụ, lệnh này báo `No source files for package com.example.catalog.api`. Lý do là `--module-source-path` mô tả **tổ chức nhiều module**, còn tên package đơn lẻ cần một context source path có thể tìm package trong một source root thích hợp. Lựa chọn đã kiểm thử là `--source-path src/com.example.catalog com.example.catalog.api`.

Cũng không nên trộn `--module com.example.catalog` vào một lệnh với kỳ vọng tên package phía sau sẽ tự thu hẹp toàn bộ module. `--module` là một **điều kiện chọn cả module**; nếu cần đúng một package, hãy dùng lệnh chọn package ở trên.

Khi cần nhiều package hoặc cả các package con trong cùng source root:

```bash
javadoc -d docs/subpackages --source-path src/com.example.catalog -subpackages com.example.catalog -exclude com.example.catalog.internal
```

`-subpackages` duyệt package được chỉ định và các package con; `-exclude` bỏ các package nằm trong danh sách (và các package con của chúng) khỏi danh sách do `-subpackages` hình thành. Đối với nhiều tên package, dấu phân cách trong hai tham số này là **dấu hai chấm** ngay cả trên Windows. `-exclude` không phải bộ lọc bảo mật tổng quát cho mọi cách chọn module; hãy dùng nó đúng với cơ chế `-subpackages` và kiểm tra danh sách trang HTML thực tế.

## 8. Trường hợp E — chỉ xuất một type cụ thể

Muốn tài liệu cho riêng `Calculator` mà không mở rộng ra cả module hoặc toàn bộ package, có thể truyền **đường dẫn đến một tệp `.java`**:

```bash
javadoc -quiet -d docs/one --module-source-path src src/com.example.catalog/com/example/catalog/api/Calculator.java
```

Kết quả có:

```text
docs/one/com.example.catalog/com/example/catalog/api/Calculator.html
```

Và không có trang `InternalCodec.html`. Trong thao tác này, `--module-source-path src` giúp Javadoc biết vị trí module, còn **source filename** ở cuối là phần tử nguồn được chọn tường minh.

Điều cần phân biệt:

- `--show-types public` nghĩa là **lọc visibility các type** trong phạm vi được chọn, không phải chọn một tên class.
- Source file `.../Calculator.java` là **cách chỉ định mục tiêu cụ thể** khi cần một type chính.
- Đối số `com.example.catalog.api.Calculator` không phải cách chọn type an toàn như đường dẫn tệp; cú pháp chuẩn của công cụ mô tả đối số vị trí là **tên package hoặc source file**, không phải danh sách tên class đầy đủ.
- Một tệp nguồn Java có thể chứa nhiều khai báo top-level không public hoặc nested types. Javadoc vẫn xét các filter `--show-types`/`--show-members`, và một số element liên quan có thể xuất hiện theo chính sách doclet. Do đó cần **kiểm tra HTML tạo ra**, không suy luận rằng “một tệp bằng đúng một trang”.
- Để chọn nhiều type, có thể cung cấp nhiều đường dẫn tệp cụ thể; cần bảo đảm module/source root nhất quán và các kiểu phụ thuộc được phân giải.

Nếu cần giấu **một thành phần cụ thể** không thể thiết kế lại API, Javadoc standard doclet còn hỗ trợ tag `@hidden` trong Javadoc comment của **type, method hoặc field**. Tag này làm element không xuất hiện trong API docs được tạo; chỉ sử dụng có chủ đích, vì nó không hề thay đổi Java visibility hoặc tạo ranh giới bảo mật. Đừng nhầm `@deprecated` với “ẩn khỏi tài liệu”: deprecated chỉ thông báo API không còn được khuyến nghị cho mã mới, không tự loại element.

## 9. Bảng các bộ lọc `--show-*`

| Bộ lọc | Giá trị | Phạm vi quyết định |
| --- | --- | --- |
| `--show-packages` | `exported` / `all` | Chọn package đã export hay tất cả package trong module. |
| `--show-types` | `public` / `protected` / `package` / `private` | Chọn mức visibility của class/interface/enum/record/annotation type. |
| `--show-members` | `public` / `protected` / `package` / `private` | Chọn visibility của field/method/constructor trong các type đã chọn. |
| `--show-module-contents` | `api` / `all` | Quyết định mức chi tiết khai báo module được trình bày. |

Đối với hai bộ lọc có bốn mức, một giá trị bao gồm các mức truy cập rộng hơn:

```text
public    => chỉ public
protected => public và protected
package   => public, protected và package-private
private   => mọi mức (kể cả private)
```

**Mặc định quan trọng:** mức `--show-types` và `--show-members` thông thường là `protected`; `--show-packages` mặc định là `exported` và `--show-module-contents` là `api` theo standard doclet hiện hành. Vì vậy, “không truyền gì” **không đồng nghĩa** với “chỉ public members”, cũng không đồng nghĩa với “bao gồm mọi package nội bộ”.

Một số cờ ngắn vẫn được công cụ hỗ trợ, nhưng phải hiểu chúng **đồng thời** quy định bốn bộ lọc thay vì chỉ một:

| Cờ | `show-types` | `show-members` | `show-packages` | `show-module-contents` |
| --- | --- | --- | --- | --- |
| `-public` | public | public | exported | api |
| `-protected` | protected | protected | exported | api |
| `-package` | package | package | all | all |
| `-private` | private | private | all | all |

Vì thế, chỉ đổi từ `-protected` sang `-package` có thể làm phạm vi tài liệu **mở rộng cả sang các package không export**, ngoài việc hiện thêm package-private types/members. Với pipeline xuất bản nghiêm ngặt, ghi tường minh các tùy chọn `--show-*` giúp người review đọc được chính sách và tránh tăng phạm vi ngoài ý muốn.

## 10. Source path, module path và release khác nhau thế nào?

Nhầm đường dẫn là một nguyên nhân rất thường gặp khi xuất Javadoc cho code có module:

| Tham số | Cần cung cấp | Khi sử dụng |
| --- | --- | --- |
| `--module-source-path src` | Cấu trúc nguồn chứa **nhiều named modules** theo layout `src/<module>/...` hoặc pattern hợp lệ. | Muốn Javadoc tìm mã nguồn của module được chọn qua `--module`, hoặc tệp Java trong module source tree. |
| `--source-path src/com.example.catalog` | **Một source root** chứa các package của một module. | Muốn chọn trực tiếp một package bằng tên package hoặc dùng `-subpackages`. |
| `--module-path path` | Thư mục/JAR chứa **module đã biên dịch** mà source phụ thuộc vào. | Giúp compiler/doclet phân giải dependency; không tự chọn module để viết tài liệu. |
| `--class-path path` | Classpath cho thư viện không modular hoặc những dependency dùng qua classpath. | Khi phân giải kiểu phụ thuộc từ classpath trong cấu hình phù hợp. |
| `--release 17` | Mốc API/ngôn ngữ Java cho việc phân tích source theo một Java release. | Khi CI yêu cầu tránh dùng API/ngôn ngữ sau mốc hỗ trợ của dự án. |
| `-d docs/...` | Thư mục đầu ra HTML. | Tách tài liệu public, internal, từng module hoặc từng package; tránh ghi đè nhầm. |

**Đừng nhầm `--release` của `javadoc` với việc tự động biên dịch và chạy toàn bộ ứng dụng:** để xác minh runtime, dùng `javac`/test như riêng trong ví dụ. Dùng đúng phiên bản JDK/toolchain trong CI để tránh đầu ra khác nhau giữa developer machine và build server.

Nếu dự án có module phụ thuộc nằm trong JAR bên ngoài, đặt dependency trên `--module-path` hoặc cấu hình build tương ứng để Javadoc phân giải được các kiểu trong signature. Không nên thêm dependency không cần thiết vào `--module` chỉ để hết lỗi “symbol not found”, vì như vậy cũng mở rộng phạm vi tài liệu sẽ xuất.

Với Gradle/Maven, nên tạo một task Javadoc có **nguồn và classpath/modulepath lấy từ build thực tế**, rồi truyền các tùy chọn chọn module/package/type và visibility tương đương. Không hard-code `src` nếu dự án thực tế có `moduleA/src/main/java`, generated sources hoặc nhiều source sets. Khi dùng nhiều module trong một lần xuất, đặc biệt phải kiểm tra root và pattern của `--module-source-path`.

## 11. Kiểm tra kết quả trước khi phát hành

Javadoc tạo thành công chưa có nghĩa là **chọn đúng phạm vi**. Nên kiểm thử cả “có” lẫn “không có”:

| Nhóm tài liệu | Kiểm tra dương tính | Kiểm tra âm tính |
| --- | --- | --- |
| Public module | `module-summary.html` của module đích tồn tại. | Không sinh trang cho module khác chưa được chọn. |
| Exported packages | Có `.../api/package-summary.html`. | Không có `.../internal/package-summary.html`. |
| Public types | Có `Calculator.html`. | Không có `PackageOnly.html`. |
| Internal docs | Có `InternalCodec.html` và `PackageOnly.html`. | Không vô tình trộn bộ docs nội bộ vào site public. |
| Một type | Có `Calculator.html`. | Không sinh type ngoài phạm vi, ví dụ `InternalCodec.html`. |
| Quality | Tool trả exit code 0; liên kết/tags hợp lệ. | `-Werror` phải khiến build thất bại khi có warning cần xử lý. |

Trên CI có thể chạy Javadoc với:

```bash
javadoc -Werror -Xdoclint:all -encoding UTF-8 -d docs/api --module-source-path src --module com.example.catalog --show-packages exported --show-types public --show-members public --show-module-contents api
```

Sau đó kiểm tra các trang “được phép” và “không được phép” trước khi publish. Với nhiều module, cần thống kê các trang `module-summary.html`, `package-summary.html` và trang class, hoặc kiểm tra danh mục module/package do doclet xuất ra. Kết quả trang HTML ở các JDK khác nhau có thể đổi bố cục; nên kiểm tra **sự tồn tại/không tồn tại của nội dung và phần tử mục tiêu** thay vì phụ thuộc hoàn toàn vào chi tiết CSS/HTML.

Thực hành tốt:

1. **Tách đầu ra:** `docs/public` và `docs/internal` là hai thư mục khác nhau, với quyền phát hành khác nhau.
2. **Ghi chính sách trong build:** danh sách module, package và mức visibility được review như code thay vì phụ thuộc mặc định.
3. **Kiểm tra DocLint:** mô tả class, constructor và phương thức public đầy đủ; `@param`/`@return` đúng chữ ký; không tắt `-Xdoclint` bừa bãi để che lỗi.
4. **Kiểm tra doc thật:** mở `index.html`, `module-summary.html`, `package-summary.html` và một số trang type tiêu biểu; xem navigation, liên kết và dấu tiếng Việt.
5. **Xác thực phạm vi trước upload:** mọi `internal`, `implementation`, `debug` hoặc package bí mật phải vắng mặt trong output công khai nếu hợp đồng không cho phép.
6. **Kiểm tra từng bản phát hành:** khi thêm `exports` hoặc thay source set, danh sách tài liệu có thể thay đổi. Snapshot danh mục API hữu ích để phát hiện public surface mới.

### Một cảnh báo quan trọng về “ẩn khỏi docs”

Javadoc **không phải cơ chế kiểm soát truy cập**. Giấu một class bằng `@hidden` hoặc `--show-types public` không khiến class không thể bị truy cập bởi mã Java có đủ quyền; ngược lại, xuất HTML cho `internal` không tự làm module khác có thể import package đó. Bảo mật và ranh giới module phải được áp dụng bằng thiết kế API, `exports/opens`, quyền publish và chính sách hệ thống.

## 12. Lỗi thường gặp khi chọn phạm vi

| Hiện tượng | Nguyên nhân hay gặp | Cách sửa |
| --- | --- | --- |
| `No source files for package ...` | Truyền package name với `--module-source-path src` nhưng không chỉ đúng single-module source root. | Dùng `--source-path src/<module> package.name` khi muốn chọn package theo tên. |
| Cả module xuất tài liệu thay vì một package | Dùng `--module moduleName` khi mục tiêu thực sự là một package duy nhất. | Chọn tên package qua `--source-path` hoặc chỉ định danh sách source file cụ thể. |
| Tất cả public classes của nhiều package xuất hiện | Dùng `--show-types public` để cố “chọn một class”. | Chọn đúng đường dẫn `.java` của type cần xuất. |
| Không thấy public class của package `internal` | Module không export package và `--show-packages` đang là `exported`. | Chỉ với tài liệu nội bộ: đổi `--show-packages all` và xác nhận phạm vi công bố. |
| Không thấy package-private class trong exported package | `--show-types` là `public` hoặc `protected`. | Dùng `--show-types package` trong bộ tài liệu nội bộ. |
| Không thấy private method | `--show-members` không phải `private`. | Chỉ nếu thực sự cần: `--show-members private` trong docs nội bộ. |
| Dùng `-package` và vô tình lộ package nội bộ | Cờ ngắn đó đặt cả `--show-packages all`. | Ghi tường minh bốn tùy chọn `--show-*` phù hợp. |
| Thêm `--module-path` nhưng không có HTML của dependency | Module path giúp phân giải, không nhất thiết chọn module để viết docs. | Thêm module đó vào `--module` nếu thật sự muốn xuất tài liệu. |
| Không thấy source khi dự án dùng Maven/Gradle | Layout nguồn không phải `src/<module>/...`. | Đặt `--module-source-path`/`--source-path` đúng source root hoặc module-specific path. |
| Javadoc chạy thành công nhưng thiếu tài liệu API | Có thể thiếu Javadoc comment, thiếu source file trong phạm vi, `@hidden`, hoặc sai filter. | Dùng DocLint và xác minh trang module/package/type cùng element quan trọng. |
| Doc public chứa trang nội bộ | Dùng `--show-packages all` hoặc nguồn quá rộng và publish cùng thư mục. | Dùng build public riêng, loại internal và kiểm tra HTML trước phát hành. |
| Tên module và tên package bị nhầm | Module là định danh JPMS, package là namespace Java. | Đối chiếu `module-info.java`, đường dẫn source root và tên package khai báo ở đầu file. |

## 13. Tự luyện

1. Trong ví dụ trên, vì sao `PackageOnly` và `InternalCodec` đều **không** có trong tài liệu public nhưng vì hai lý do khác nhau? Trả lời dựa trên `exports` và `public`.
2. Đổi lệnh xuất public từ `--show-members public` sang `--show-members protected`. Phương thức nào của `Calculator` xuất hiện thêm? Phạm vi type và package có đổi không?
3. Chọn **chỉ một package** `com.example.catalog.api` và chỉ các type public. Viết lệnh Javadoc dựa trên `--source-path` và `--show-types`, rồi kiểm tra file HTML của `PackageOnly`.
4. Chọn **chỉ một type** `Calculator` mà không đưa `Launcher` vào tài liệu. Vì sao chỉ ghi `--show-types public` không giải quyết được bài toán?
5. Tạo hai output riêng cho public và internal, rồi thiết lập bước CI thất bại nếu đường dẫn `InternalCodec.html` xuất hiện ở output public.
6. Giải thích vì sao `--module-path`, `--module` và `--expand-requires` không thể dùng thay thế cho nhau.
7. Một module đổi từ `exports com.example.catalog.api;` sang không export package đó. Những file HTML nào trong lần xuất public sẽ bị ảnh hưởng? Nhóm bảo trì nên cập nhật hợp đồng API và kiểm thử ra sao?

## Ghi nhớ

- **Chọn module:** `--module moduleA,moduleB` với `--module-source-path` đúng layout.
- **Chọn package:** dùng tên package kết hợp `--source-path`; dùng `-subpackages`/`-exclude` khi cần duyệt cây package.
- **Chọn type:** truyền đường dẫn tệp `.java` cụ thể; `--show-types` là filter visibility, không phải danh sách tên type.
- **Kiểm soát tài liệu công khai:** `--show-packages exported --show-types public --show-members public --show-module-contents api`.
- **Tài liệu nội bộ:** mở rộng `all/package/private` một cách có chủ đích và không publish chung với public docs.
- **Luôn kiểm tra đầu ra:** nội dung đúng phải **có**, implementation ngoài hợp đồng phải **không có**, và DocLint phải vượt qua.

### Tài liệu tham khảo hiện hành

- [Oracle JDK 24 — The javadoc Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javadoc.html): cú pháp chọn module, package, source file, `--module-source-path`, `--source-path`, `-subpackages`, `-exclude`, `--expand-requires`, `-Werror`.
- [Oracle JDK 24 — jdk.javadoc.doclet](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.javadoc/jdk/javadoc/doclet/package-summary.html): mô hình chọn element, bốn bộ lọc `--show-*` và ánh xạ các cờ `-public/-protected/-package/-private`.
- [Oracle JDK 25 — Documentation Comment Specification for the Standard Doclet](https://docs.oracle.com/en/java/javase/25/docs/specs/javadoc/doc-comment-spec.html): comment `/** ... */`, `@param`, `@return` và `@hidden`.
- [Oracle JDK 24 — The javac Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html): biên dịch nhiều named modules, `--module-source-path` và `--release`.