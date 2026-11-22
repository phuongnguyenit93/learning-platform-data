# Phân tích JAR, package và class bằng `jdeps`

`jdeps` (Java Dependency Analysis Tool) là công cụ dòng lệnh đi kèm JDK để phân tích các phụ thuộc được thể hiện trong bytecode Java. Công cụ có thể đọc một file `.class`, thư mục chứa class hoặc JAR, sau đó báo cáo phụ thuộc ở cấp module, package hoặc class. Đây là công cụ hữu ích khi kiểm tra thư viện, tìm dependency bị thiếu, chuẩn bị chuyển JAR cũ sang JPMS và xác định việc sử dụng JDK internal API.

`jdeps` thực hiện phân tích tĩnh, không chạy ứng dụng. Kết quả cho biết những tham chiếu mà công cụ tìm được trong bytecode và module descriptor; nó không chứng minh toàn bộ đường chạy runtime đều đã được kiểm tra. Các class được nạp qua tên chuỗi, reflection, cấu hình ngoài, plugin và thư viện native có thể cần kiểm tra bổ sung.

## 1. `jdeps` phân tích những gì?

Ở mức cơ bản, `jdeps` đọc class file và xác định các kiểu mà class tham chiếu. Từ những tham chiếu đó, công cụ tổng hợp các cạnh phụ thuộc:

- **Class-level:** class nào tham chiếu tới class nào, ví dụ `CatalogService -> Logger`.
- **Package-level:** package nguồn phụ thuộc vào package đích nào, ví dụ `com.acme.catalog.api -> java.util.logging`.
- **Module-level:** module cần đọc module nào, ví dụ `com.acme.catalog -> java.logging`.
- **API-only:** phụ thuộc xuất hiện trong public/protected API của public class, như kiểu tham số, kiểu trả về, field và checked exception.
- **JDK internal API:** tham chiếu tới API nội bộ của JDK có nguy cơ thay đổi hoặc bị loại bỏ.

`jdeps` không phải trình profiler hay công cụ đo hiệu năng. Nó không cho biết một class được gọi bao nhiêu lần, nhánh nào chạy hoặc dependency nào được sử dụng trong một lần chạy cụ thể.

## 2. Cài đặt và xác định phiên bản

`jdeps` nằm trong thư mục `bin` của JDK. Hãy dùng công cụ từ JDK tương ứng với phiên bản Java mà dự án biên dịch hoặc triển khai:

```shell
java -version
javac -version
jdeps --version
jdeps --help
```

`jdeps --help` liệt kê tùy chọn của đúng phiên bản đang cài. Cú pháp có cả dạng viết tắt và dạng dài; một số tùy chọn như `-summary`, `-verbose:package`, `-verbose:class` dùng một dấu gạch ngang theo tên được công bố trong help.

## 3. Đầu vào: JAR, thư mục class và một class cụ thể

`jdeps` nhận một hoặc nhiều đường dẫn:

```shell
jdeps library.jar
jdeps build/classes
jdeps build/classes/com/acme/catalog/CatalogService.class
```

- **JAR:** phân tích các class trong archive và descriptor nếu JAR là modular JAR.
- **Thư mục:** phân tích các class trong thư mục đã biên dịch, phù hợp với output của `javac`.
- **Một class:** khoanh vùng dependency của class cần điều tra; các dependency ngoài input cần được cung cấp qua class path hoặc module path để phân giải đầy đủ.

Phân biệt vị trí của thư viện:

| Vị trí | Cách Java nhìn nhận | Tùy chọn phân tích thường dùng |
|---|---|---|
| Classpath | Các class thuộc unnamed module. | `--class-path` / `-cp`. |
| Module path, JAR có `module-info.class` | Explicit named module. | `--module-path`, `--module`. |
| Module path, JAR không có descriptor | Automatic module. | `--module-path`, tên automatic module. |

Đường dẫn dependency cần được cung cấp đúng. Nếu thiếu dependency, `jdeps` có thể báo `not found`; đừng kết luận rằng dependency không tồn tại chỉ vì nó không có trong output.

## 4. Chọn cấp độ phân tích: summary, package và class

Đây là các chế độ cơ bản nhất:

| Tùy chọn | Kết quả | Khi nên dùng |
|---|---|---|
| `-summary` hoặc `-s` | Tóm tắt dependency theo archive/module. | Muốn xem nhanh một JAR phụ thuộc vào module nào. |
| `-verbose:package` | Quan hệ phụ thuộc giữa package. | Tìm package nội bộ hoặc package JDK mà một package đang dùng. |
| `-verbose:class` | Quan hệ phụ thuộc giữa class. | Truy nguyên một class cụ thể hoặc tìm nguồn tham chiếu. |
| `-v` hoặc `-verbose` | Phân tích class-level chi tiết, bao gồm cả phụ thuộc trong cùng package. | Cần xem toàn bộ class-level edge. |

Mặc định, các chế độ verbose lọc một số phụ thuộc nội bộ cùng package/archive. Dùng `-filter:none` khi cần xem cả các quan hệ đó.

### Ví dụ output

Giả sử JAR `com.acme.catalog` có class `CatalogService` sử dụng `java.util.logging.Logger`, `java.time.Instant` và class nội bộ `Store`.

Summary:

```shell
jdeps -summary mods/com.acme.catalog.jar
```

Output mẫu từ JDK 24:

```text
com.acme.catalog -> java.base
com.acme.catalog -> java.logging
```

Package-level:

```shell
jdeps -verbose:package mods/com.acme.catalog.jar
```

Đoạn output tiêu biểu:

```text
com.acme.catalog.api -> com.acme.catalog.internal  com.acme.catalog
com.acme.catalog.api -> java.time                 java.base
com.acme.catalog.api -> java.util.logging         java.logging
```

Class-level:

```shell
jdeps -verbose:class mods/com.acme.catalog.jar
```

Đoạn output tiêu biểu:

```text
com.acme.catalog.api.CatalogService -> com.acme.catalog.internal.Store  com.acme.catalog
com.acme.catalog.api.CatalogService -> java.time.Instant                java.base
com.acme.catalog.api.CatalogService -> java.util.logging.Logger         java.logging
```

Nhìn từ các mức này, có thể đi từ câu hỏi tổng quát “JAR cần module nào?” tới câu hỏi cụ thể “class nào kéo `java.logging` vào?”.

## 5. Chỉ phân tích dependency xuất hiện trong public API

`--api-only` giới hạn kết quả vào dependency được tham chiếu từ public/protected members của public classes, gồm kiểu field, kiểu tham số, kiểu trả về và checked exception trong chữ ký API.

```shell
jdeps --api-only mods/com.acme.catalog.jar
```

Trong ví dụ, `CatalogService` dùng `Logger` ở phần triển khai nhưng không đưa `Logger` ra chữ ký công khai. Vì vậy `java.logging` có thể xuất hiện trong phân tích tổng thể nhưng không xuất hiện trong phần API-only. Kiểu `Instant` là kiểu trả về công khai nên được giữ lại.

Đây là cách kiểm tra dependency bị lộ ra ngoài hợp đồng API. Nếu một thư viện định thay thế hoặc ẩn implementation, hãy xem API-only để biết kiểu nào từ dependency đang xuất hiện trong chữ ký công khai.

`--api-only` không thay thế phân tích đầy đủ: dependency nội bộ vẫn cần thiết để chương trình chạy.

## 6. Lọc dependency theo package, regex hoặc module

Ba tùy chọn lọc dependency thường dùng:

```shell
jdeps --package java.util.logging library.jar
jdeps --regex 'java[.]util[.].*' library.jar
jdeps --require java.logging library.jar
```

- `--package` tìm dependency khớp tên package; có thể chỉ định nhiều lần.
- `--regex` lọc theo biểu thức chính quy của dependency.
- `--require` lọc theo tên module đích.

`--package`, `--regex` và `--require` là các lựa chọn loại trừ lẫn nhau trong một lần chạy. Dùng một trong ba tùy chọn phù hợp với câu hỏi cần trả lời.

Để chỉ phân tích một nhóm class nguồn, dùng `-include` với regex class:

```shell
jdeps -include 'com[.]acme[.]catalog[.]api[.].*' -verbose:class library.jar
```

`-include` giới hạn các class được phân tích; `--package` hoặc `--regex` giới hạn các dependency được báo cáo. Hai nhóm tùy chọn này giải quyết hai câu hỏi khác nhau.

## 7. Phân tích đệ quy và dependency gián tiếp

Mặc định, `jdeps` phân tích dependency trực tiếp của input. Khi cần theo dõi sâu hơn:

```shell
jdeps --recursive library.jar
jdeps --no-recursive library.jar
jdeps --compile-time library.jar
```

- `--recursive` (hoặc `-R`) tiếp tục duyệt dependency runtime và ngầm dùng `-filter:none`.
- `--no-recursive` chỉ phân tích dependency trực tiếp.
- `--compile-time` hiển thị góc nhìn dependency compile-time theo quan hệ bắc cầu.

Phân tích đệ quy có thể làm output lớn hơn vì bao gồm các dependency gián tiếp. Hãy bắt đầu từ summary/direct dependency rồi mở rộng khi cần xác định dependency được kéo vào qua chuỗi nào.

`--inverse` có thể dùng cùng `--package`, `--regex` hoặc `--require` để tìm những artifact/module phụ thuộc trực tiếp hoặc gián tiếp vào node khớp. Tùy chọn này hữu ích khi muốn biết “ai đang dùng package/module này?” thay vì “artifact này đang dùng gì?”.

## 8. Tìm dependency bị thiếu bằng `--missing-deps`

Khi phân tích JAR cũ hoặc output class, một class có thể tham chiếu tới dependency không còn trong class path/module path hiện tại. Dùng:

```shell
jdeps --missing-deps application.jar
```

Ví dụ output:

```text
app.jar -> not found
   com.acme.app.App -> com.acme.helper.Helper  not found
```

Trong trường hợp này, `App` tham chiếu `Helper`, nhưng JAR chứa `Helper` chưa được cung cấp cho lần phân tích.

Thêm dependency vào class path:

```shell
jdeps --missing-deps --class-path lib/helper.jar application.jar
```

Nếu không còn dependency bị thiếu, lệnh không in danh sách missing dependency. Với named module, dùng `--module-path` để cung cấp module dependencies.

`--missing-deps` giúp phát hiện tham chiếu không phân giải được trong bytecode. Nó không xác minh các class được nạp bằng `Class.forName` từ chuỗi runtime, plugin được tìm qua cấu hình hay tài nguyên được mở theo tên động.

## 9. Tìm JDK internal API bằng `--jdk-internals`

Thư viện có thể tham chiếu các API nội bộ của JDK, ví dụ `sun.misc.Unsafe`. Các API này không phải hợp đồng Java SE ổn định và có thể thay đổi hoặc bị loại bỏ.

```shell
jdeps --jdk-internals legacy-library.jar
```

Output mẫu:

```text
legacy-library.jar -> jdk.unsupported
   com.acme.legacy.UnsafeUse -> sun.misc.Unsafe  JDK internal API (jdk.unsupported)
```

Tool cũng in cảnh báo và gợi ý thay thế nếu có thông tin. Khi thấy kết quả, xác định class và API cụ thể rồi tìm API công khai được hỗ trợ hoặc thiết kế lại phần phụ thuộc.

`--jdk-internals` không phải bộ lọc thông thường; theo help của JDK, không kết hợp nó với `--package`, `--regex` hoặc `-summary` trong cùng lần chạy.

## 10. Phân tích module và kiểm tra module descriptor

Với explicit modular JAR, chỉ định module path và tên module:

```shell
jdeps --module-path mods --module com.acme.catalog -summary
```

Phân tích module cụ thể giúp làm việc theo module graph thay vì chỉ dựa vào một đường dẫn archive.

### Kiểm tra descriptor

```shell
jdeps --module-path mods --check com.acme.catalog
```

`--check` in descriptor, các dependency sau phân tích và đồ thị sau khi rút gọn quan hệ đọc được bắc cầu. Nó cũng có thể nhận diện qualified export không được dùng.

### Liệt kê dependency module

```shell
jdeps --module-path mods --module com.acme.catalog --list-deps
jdeps --module-path mods --module com.acme.catalog --list-reduced-deps
jdeps --module-path mods --module com.acme.catalog --print-module-deps
```

- `--list-deps` liệt kê module dependencies và có thể phân tích bắc cầu.
- `--list-reduced-deps` loại các cạnh đọc được suy ra từ `requires transitive`.
- `--print-module-deps` in danh sách tên module phân cách bằng dấu phẩy; kết quả có thể dùng làm đầu vào `jlink --add-modules` khi tạo runtime image.

Ví dụ output của `--print-module-deps`:

```text
java.base,java.logging
```

Không lấy output này làm danh sách module hoàn chỉnh cho mọi môi trường triển khai nếu ứng dụng còn dùng reflection, service binding, plugin hoặc dependency runtime không thể suy ra từ bytecode. Kiểm tra thêm cấu hình triển khai và chạy thử runtime image.

## 11. Xuất đồ thị phụ thuộc

`--dot-output` tạo file DOT để quan sát đồ thị dependency:

```shell
jdeps --dot-output build/jdeps-graph mods/com.acme.catalog.jar
```

Thư mục đích chứa file `.dot` cho archive và summary. Có thể dùng Graphviz hoặc công cụ đọc DOT để chuyển thành hình. Với JAR lớn, đồ thị giúp nhìn ra dependency trung tâm, package liên kết rộng và nhóm module cần tách.

Không chỉnh sửa file DOT rồi coi đó là kết quả gốc của `jdeps`; nếu thay đổi input hoặc tùy chọn, chạy lại lệnh để tạo đồ thị mới.

## 12. Tạo module descriptor gợi ý cho JAR cũ

Đối với JAR chưa có `module-info.class`, `jdeps` có thể tạo module descriptor mẫu:

```shell
jdeps --generate-module-info generated-modules legacy-library.jar
```

Ví dụ descriptor được tạo:

```java
module legacy.lib {
    exports com.acme.legacy;
}
```

Đây là điểm khởi đầu để modularize thư viện, không phải descriptor đã được xác nhận đúng cho mọi tình huống. Cần kiểm tra lại:

- Module name và tính ổn định của tên.
- Tất cả dependency thật sự cần thiết và phạm vi `requires`.
- Package nào là API cần `exports`, package nào nên giữ nội bộ.
- Reflection cần `opens` hay không.
- Service consumer/provider có cần `uses` và `provides` hay không.
- Class được nạp động, resource, native library và cấu hình runtime.

`--generate-module-info` làm việc trên các JAR được chỉ định và không nhận `--class-path` hoặc `--dot-output` cùng lần chạy. Nếu thư viện thực sự cần mở toàn bộ package cho deep reflection, có tùy chọn `--generate-open-module`; chỉ dùng khi thiết kế yêu cầu điều đó, vì open module mở rộng quyền reflection ở runtime.

## 13. Multi-release JAR

Multi-release JAR có thể chứa các class khác nhau theo phiên bản Java trong `META-INF/versions/`. Khi cần phân tích một phiên bản cụ thể, chỉ định:

```shell
jdeps --multi-release 17 library.jar
```

Giá trị có thể là một số nguyên từ 9 trở lên hoặc `base`. Chọn đúng phiên bản mục tiêu để kết quả phản ánh class variant mà runtime tương ứng sẽ sử dụng. Không dùng tùy chọn này cho JAR thông thường không phải multi-release nếu không có nhu cầu cụ thể.

## 14. Ví dụ xuyên suốt: phân tích JAR có API và implementation package

Ví dụ gồm một explicit module `com.acme.catalog` có package API và package nội bộ:

```text
src/
└── com.acme.catalog/
    ├── module-info.java
    ├── com/acme/catalog/api/CatalogService.java
    └── com/acme/catalog/internal/Store.java
```

**`src/com.acme.catalog/module-info.java`:**

```java
module com.acme.catalog {
    requires java.logging;
    exports com.acme.catalog.api;
}
```

**`src/com.acme.catalog/com/acme/catalog/api/CatalogService.java`:**

```java
package com.acme.catalog.api;

import com.acme.catalog.internal.Store;
import java.time.Instant;
import java.util.logging.Logger;

public final class CatalogService {
    private static final Logger LOG = Logger.getLogger(CatalogService.class.getName());
    private final Store store = new Store();

    public String findName(String id) {
        LOG.info("Looking up " + id);
        return store.findName(id);
    }

    public Instant generatedAt() {
        return Instant.now();
    }
}
```

**`src/com.acme.catalog/com/acme/catalog/internal/Store.java`:**

```java
package com.acme.catalog.internal;

public final class Store {
    public String findName(String id) {
        return "Item-" + id;
    }
}
```

### Biên dịch và đóng gói

Chạy từ thư mục dự án bằng JDK 17 trở lên:

```shell
javac --module-source-path src -d out -m com.acme.catalog
mkdir mods
jar --create --file mods/com.acme.catalog.jar -C out/com.acme.catalog .
```

### Xem dependency theo từng mức

```shell
jdeps -summary mods/com.acme.catalog.jar
jdeps -verbose:package mods/com.acme.catalog.jar
jdeps -verbose:class mods/com.acme.catalog.jar
jdeps --api-only mods/com.acme.catalog.jar
```

Với JDK 24.0.2, summary của ví dụ cho thấy `java.base` và `java.logging`. Package-level cho thấy `com.acme.catalog.api` tham chiếu `com.acme.catalog.internal`, `java.time` và `java.util.logging`. Class-level chỉ ra `CatalogService` là class sử dụng `Store`, `Instant` và `Logger`.

API-only giữ `java.time.Instant` vì đây là kiểu trả về công khai, nhưng không giữ `Logger` chỉ được dùng trong implementation. Kết quả này giúp phân biệt dependency của hợp đồng API với dependency triển khai.

### Kiểm tra module graph và tạo DOT

```shell
jdeps --module-path mods --check com.acme.catalog
jdeps --module-path mods --module com.acme.catalog --print-module-deps
jdeps --dot-output build/jdeps-graph mods/com.acme.catalog.jar
```

Với JAR này, danh sách module tối thiểu do phân tích trả về là `java.base,java.logging`. File DOT cho phép xem trực quan cạnh từ `com.acme.catalog` tới các module nền tảng.

## 15. Quy trình phân tích một thư viện trong dự án thực tế

1. Xác định đúng artifact và phiên bản JAR; lưu lại checksum nếu cần so sánh kết quả giữa các lần build.
2. Chạy `jdeps -summary` để xem dependency tổng quan.
3. Chạy `-verbose:package` để xác định package nội bộ và dependency ngoài.
4. Chạy `-verbose:class` để truy về class tạo ra dependency cần điều tra.
5. Dùng `--api-only` để kiểm tra kiểu dependency bị lộ trong public API.
6. Bổ sung đúng `--class-path` hoặc `--module-path`, rồi chạy `--missing-deps` để phát hiện dependency chưa phân giải.
7. Chạy `--jdk-internals` để tìm API nội bộ JDK.
8. Với modular JAR, dùng `--check`, `--list-deps` hoặc `--print-module-deps` để xem module graph.
9. Xuất `--dot-output` khi cần trình bày hoặc phân tích cấu trúc dependency.
10. Nếu đang modularize JAR cũ, dùng `--generate-module-info` làm bản nháp rồi review thủ công và kiểm thử runtime.
11. Chạy test tích hợp trên đúng JDK, classpath/module path và cấu hình triển khai thực tế.

## 16. Giới hạn cần nhớ

- `jdeps` phân tích bytecode tĩnh; nó không chạy ứng dụng và không đo tần suất sử dụng dependency.
- `Class.forName("...")`, reflection, service discovery, plugin registry, tên class trong file cấu hình và JNI có thể không tạo dependency edge thông thường trong bytecode.
- Một dependency có thể được nạp trong runtime nhưng không hiện đầy đủ trong báo cáo tĩnh; cần kiểm tra cấu hình và integration test.
- `--api-only` chỉ xem public/protected API của public classes, không đại diện cho toàn bộ dependency runtime.
- `--print-module-deps` hỗ trợ tạo runtime image nhưng không tự bảo đảm image có mọi tài nguyên, provider hoặc plugin mà ứng dụng cần.
- Descriptor được sinh tự động là gợi ý. Cần review `requires`, `exports`, `opens`, `uses` và `provides` trước khi phát hành explicit modular JAR.

## 17. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `not found` trong output. | Thiếu dependency trên class path/module path hoặc khai báo sai đường dẫn. | Bổ sung đúng dependency bằng `--class-path` hoặc `--module-path`. |
| Không thấy dependency của một class. | Đang dùng summary/package filter hoặc class không thuộc tập được phân tích. | Chạy `-verbose:class`, kiểm tra input và dùng `-include` đúng cách. |
| Output quá lớn. | Dùng recursive hoặc class-level trên toàn bộ dependency graph. | Bắt đầu với `-summary`, `-verbose:package`, `--no-recursive`, rồi mở rộng. |
| `--module` báo không tìm thấy module. | Module path thiếu JAR hoặc tên module không khớp descriptor. | Kiểm tra `jar --describe-module` và `--module-path`. |
| `--jdk-internals` phát hiện API nội bộ. | Bytecode phụ thuộc API không phải Java SE ổn định. | Tìm API thay thế và cập nhật thư viện. |
| Descriptor được sinh ra nhưng module không chạy. | Thiếu service declaration, opens, dependency động hoặc cấu hình runtime. | Review descriptor và chạy integration tests; không phát hành bản sinh tự động ngay. |
| `--multi-release` cho kết quả khác mong đợi. | Phân tích sai class variant hoặc sai target release. | Chọn đúng phiên bản bằng `--multi-release`. |

## Tài liệu tham khảo

- [The `jdeps` Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html)
- [The `jar` Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jar.html)
- [The `javac` Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html)
- [Java Platform Module System — Module Dependencies (JLS, Java SE 26)](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-7.html)
