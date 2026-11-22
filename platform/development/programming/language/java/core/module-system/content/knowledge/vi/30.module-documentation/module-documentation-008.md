# Changelog khi thay đổi module boundary

Trong Java Platform Module System (JPMS), **module boundary** xác định module nào sở hữu package, module nào có thể đọc module khác, những package nào được truy cập như public API và những package nào được mở cho reflection. Vì vậy, thay đổi `module-info.java` có thể là một thay đổi ảnh hưởng đến người dùng thư viện ngay cả khi không sửa một phương thức Java public nào.

Một changelog tốt cần trả lời rõ: **đã thay đổi ranh giới nào, ai bị ảnh hưởng, hậu quả ở compile time hoặc runtime là gì, cần sửa code hoặc lệnh chạy ra sao và từ phiên bản nào thay đổi có hiệu lực**. Chỉ viết “refactor module structure” hoặc “cleanup module-info” thường không đủ cho những dự án phụ thuộc.

Bài này trình bày cách viết changelog và migration notes khi thay đổi module boundary trong thư viện hoặc ứng dụng modular Java.

## 1. Vì sao module boundary là một phần của hợp đồng tương thích?

Một named module có descriptor:

```java
module com.acme.catalog {
    requires java.logging;
    exports com.acme.catalog.api;
    opens com.acme.catalog.model to com.acme.json;
    uses com.acme.catalog.spi.Connector;
}
```

Descriptor này thể hiện nhiều quyết định kiến trúc:

- `requires java.logging`: module có dependency đọc module logging.
- `exports com.acme.catalog.api`: module khác có thể truy cập các kiểu public của package API nếu có readability phù hợp.
- `opens com.acme.catalog.model to com.acme.json`: module JSON được phép deep reflection vào package model ở runtime.
- `uses ... Connector`: module có nhu cầu khám phá một loại service qua `ServiceLoader`.

Giả sử release sau bỏ `exports com.acme.catalog.api`. Các class và phương thức trong JAR có thể vẫn còn, nhưng consumer đang import chúng có thể không biên dịch được; bytecode đã biên dịch cũng có thể gặp `IllegalAccessError` khi chạy trên module graph mới.

Nếu đổi một `opens` thành đóng package, framework serializer/ORM có thể gặp `InaccessibleObjectException` dù unit test không dùng reflection vẫn chạy bình thường.

Vì vậy, **diff của module descriptor phải được xem xét như diff của public API** khi chuẩn bị release notes.

## 2. Những thay đổi cần có trong changelog

| Thay đổi | Ảnh hưởng có thể xảy ra | Nội dung cần ghi |
|---|---|---|
| Thêm `exports P` | Mở public API mới cho consumer | Tên package, module, phạm vi hỗ trợ |
| Bỏ `exports P` | Consumer mất quyền truy cập package | API thay thế, cách migrate, release áp dụng |
| Đổi `exports P` thành `exports P to A` | Các module khác `A` bị giới hạn | Tập consumer được hỗ trợ, hướng chuyển đổi |
| Thêm/bỏ `opens P` | Thay đổi khả năng deep reflection | Framework bị ảnh hưởng và cấu hình thay thế |
| Thêm/bỏ `requires M` | Đổi dependency graph và khả năng phân giải | Module name và yêu cầu runtime |
| Đổi `requires` ↔ `requires transitive` | Đổi readability được truyền cho consumer | Consumer có cần khai báo `requires` trực tiếp hay không |
| Đổi `requires` ↔ `requires static` | Đổi yêu cầu dependency tại runtime resolution | Dependency còn cần khi code thực thi không |
| Thêm/bỏ `uses S` | Thay đổi nhu cầu khám phá service | Service contract và hành vi mặc định |
| Thêm/bỏ/đổi `provides S with I` | Tập provider và hành vi plugin đổi | Implementation được thêm/bỏ/thay và cách chọn |
| Đổi tên module | Các descriptor `requires` cũ không còn phù hợp | Tên cũ, tên mới, tọa độ artifact và migration |
| Chuyển package giữa các module | Thay đổi chủ sở hữu package và `requires` | Đường import, module path và tương thích |
| Tách hoặc hợp nhất module | Graph và artifact phân phối thay đổi | Mapping module cũ/mới, dependency và lệnh chạy |

Không phải mọi thay đổi trong bảng đều luôn gây lỗi. Ảnh hưởng thực tế phụ thuộc vào consumer đang dùng package/service nào, artifact có được đặt trên module path hay classpath, và cách cấu hình build/runtime. Changelog phải **mô tả phạm vi ảnh hưởng có căn cứ**, không suy luận rằng bất cứ sửa đổi descriptor nào cũng là breaking change.

## 3. Phân biệt tên artifact với tên module trong release notes

Một ứng dụng có thể dùng Maven dependency:

```xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>catalog-client</artifactId>
    <version>2.0.0</version>
</dependency>
```

Nhưng JPMS module name có thể là `com.acme.catalog`. Hai tên không bắt buộc giống nhau. Nếu đổi artifact hoặc module, changelog cần ghi riêng:

```text
Artifact cũ: com.acme:catalog-client:1.x
Artifact mới: com.acme:catalog-client:2.x
JPMS module cũ: com.acme.catalog
JPMS module mới: com.acme.catalog.api
```

Ví dụ trên là thông tin minh họa. Điều quan trọng là tránh hướng dẫn consumer sửa `requires com.acme.catalog;` theo Maven `artifactId` thay vì theo **tên module thật** từ `module-info.class`.

Có thể kiểm tra module name của artifact bằng:

```shell
jar --describe-module --file catalog-client-2.0.0.jar
```

Nếu JAR là automatic module, tên có thể đến từ `Automatic-Module-Name` hoặc được suy ra từ filename. Việc thay đổi naming của automatic module cũng cần ghi chú nếu consumer đang khai báo `requires` tới tên đó.

## 4. Mẫu ghi changelog cho thay đổi exports

### Trước thay đổi

Thư viện phiên bản 1.x:

```java
module com.acme.catalog {
    exports com.acme.catalog.api;
    exports com.acme.catalog.legacy;
}
```

Consumer sử dụng:

```java
module com.acme.report {
    requires com.acme.catalog;
}
```

```java
import com.acme.catalog.legacy.LegacyCatalog;
```

### Sau thay đổi

Thư viện phiên bản 2.x:

```java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
```

Package `com.acme.catalog.legacy` không còn được export. Nếu class vẫn tồn tại nhưng không được công bố, consumer không còn quyền truy cập trực tiếp từ named module khác.

Một mục changelog có ích:

```markdown
### Changed — JPMS module boundary

- Module: `com.acme.catalog`
- Removed export: `com.acme.catalog.legacy`
- Supported public API: `com.acme.catalog.api`
- Affected consumers: named modules importing classes from
  `com.acme.catalog.legacy`
- Migration: replace `LegacyCatalog` with `CatalogClient`
  from `com.acme.catalog.api`
- Runtime impact: previously compiled consumers may encounter
  `IllegalAccessError` when accessing the non-exported package
```

Changelog cần có hướng migration cụ thể, không chỉ ghi “removed deprecated export”. Nếu API thay thế không hoàn toàn tương đương, hãy mô tả hành vi hoặc dữ liệu nào cần điều chỉnh.

**Lưu ý:** giữ `public` trên class bên trong package không export không làm class đó trở thành public API qua ranh giới named module.

## 5. Qualified exports: thu hẹp nhóm consumer được phép dùng API

Một thay đổi từ:

```java
exports com.acme.catalog.integration;
```

sang:

```java
exports com.acme.catalog.integration to com.acme.partner;
```

có nghĩa package đó chỉ còn được export cho module `com.acme.partner`. Consumer khác có thể bị ảnh hưởng.

Trong changelog, cần nêu:

1. Module sở hữu package và tên package được thu hẹp.
2. Những module được cấp qualified export sau thay đổi.
3. Những consumer trước đây dùng unqualified export sẽ không còn truy cập được.
4. API thay thế hoặc hướng tích hợp được hỗ trợ.

Nếu đổi tên consumer từ `com.acme.partner` sang `com.acme.partner.v2`, qualified export cũng phải được cập nhật khi cần. Không nên nói “qualified export vẫn tương thích” nếu tập module đích đã thay đổi.

Dạng ghi ngắn gọn:

```markdown
### Breaking — Qualified export

`com.acme.catalog.integration` is now exported only to
`com.acme.partner`. Other named modules must migrate to the
public `com.acme.catalog.api` package.
```

Không dùng `--add-exports` như giải pháp dài hạn thay cho public API ổn định. Nếu cần workaround có thời hạn, ghi rõ bản release nào hỗ trợ và thời điểm dự kiến loại bỏ.

## 6. opens và reflection phải có release note riêng

`exports` và `opens` không thay thế nhau:

- `exports P`: cho phép truy cập các kiểu public trong package khi module có readability phù hợp.
- `opens P`: cho phép deep reflection vào package ở runtime.
- `opens P to M`: cho phép deep reflection chỉ từ module `M`.
- `open module`: mở các package trong module cho deep reflection, thường rộng hơn mức cần thiết.

Ví dụ trước thay đổi:

```java
module com.acme.catalog {
    exports com.acme.catalog.api;
    opens com.acme.catalog.model;
}
```

Sau thay đổi:

```java
module com.acme.catalog {
    exports com.acme.catalog.api;
    opens com.acme.catalog.model to com.acme.json;
}
```

Đây là thay đổi từ mở reflection rộng sang mở cho một module cụ thể. Khi viết changelog, không chỉ ghi “security hardening”. Cần nêu module framework nào vẫn được hỗ trợ, framework hoặc test nào phải điều chỉnh và lỗi dự kiến nếu chưa migrate:

```text
java.lang.reflect.InaccessibleObjectException
```

Một mục release note ví dụ:

```markdown
### Changed — Reflection access

The package `com.acme.catalog.model` is now opened only to
`com.acme.json`. Custom serializers running in other named
modules must use the supported mapping API or request a
documented integration path.
```

Với framework chạy trong unnamed module, cần kiểm tra quyền mở package cho `ALL-UNNAMED` nếu áp dụng workaround. Hãy ghi rõ môi trường chạy thay vì đưa một cờ JVM chung chung vào release notes.

## 7. requires và dependency graph: thay đổi nào cần công bố?

Nếu phiên bản 1.x có:

```java
module com.acme.catalog {
    requires java.logging;
    exports com.acme.catalog.api;
}
```

và phiên bản 2.x thêm:

```java
requires java.net.http;
```

thì graph runtime của thư viện có thêm dependency `java.net.http`. Người dùng chạy bằng JDK đầy đủ thường có module này, nhưng custom runtime image được tạo bằng `jlink` hoặc module path tùy chỉnh có thể cần xây dựng lại.

Trong changelog, nêu rõ:

```text
Added JPMS dependency: java.net.http
Affected environments: custom jlink images and constrained runtimes
Action: rebuild the runtime image and verify module resolution
```

Nếu dependency là một module thư viện bên thứ ba, cần ghi cả **artifact dependency** và **JPMS module name**, vì consumer hoặc build tool phải cung cấp artifact tương ứng.

Khi bỏ một `requires`, changelog cũng có thể ghi rõ module nào không còn bắt buộc, đặc biệt nếu thay đổi giúp giảm kích thước runtime image. Tuy nhiên, không cam kết image tự nhỏ đi nếu còn dependency khác giữ module đó trong graph.

## 8. requires transitive có ảnh hưởng tới API consumer

Giả sử thư viện export một interface có kiểu trả về từ module khác:

```java
package com.acme.catalog.api;

import com.acme.model.Product;

public interface Catalog {
    Product find(String id);
}
```

Descriptor ban đầu:

```java
module com.acme.catalog {
    requires transitive com.acme.model;
    exports com.acme.catalog.api;
}
```

Nhờ `requires transitive`, consumer đọc `com.acme.catalog` cũng được hưởng readability tới `com.acme.model`.

Nếu đổi thành:

```java
module com.acme.catalog {
    requires com.acme.model;
    exports com.acme.catalog.api;
}
```

thì consumer không còn nhận readability tới model theo đường transitive đó. Một số source consumer có thể phải khai báo thêm:

```java
module com.acme.report {
    requires com.acme.catalog;
    requires com.acme.model;
}
```

Changelog cần mô tả cụ thể:

```markdown
### Changed — Transitive readability

`com.acme.model` is no longer a transitive dependency of
`com.acme.catalog`. Consumer modules using types from
`com.acme.model` must declare `requires com.acme.model;`
directly.
```

Không đánh đồng điều này với Maven/Gradle transitive artifact dependency: build tool có thể vẫn tải model JAR, nhưng JPMS readability của named module được quyết định bằng descriptor và module graph.

## 9. requires static và dependency tùy chọn

`requires static M` biểu thị dependency cần tại compile time nhưng không bắt buộc phải hiện diện khi phân giải module ở runtime.

Ví dụ:

```java
module com.acme.catalog {
    requires static com.acme.annotations;
}
```

Nếu release đổi `requires com.acme.annotations;` thành `requires static com.acme.annotations;`, changelog có thể nói rõ dependency không còn bắt buộc khi runtime resolution. Nhưng **không có nghĩa** mọi đường chạy dùng API của module đó sẽ tự hoạt động khi thiếu JAR.

Ngược lại, nếu đổi `requires static` thành `requires`, deployment phải bảo đảm module mới luôn có mặt tại runtime.

Một thông báo tốt nên tách:

- Điều kiện cần khi compile.
- Điều kiện cần khi runtime resolution.
- Điều kiện thực tế của những tính năng sử dụng class thuộc module phụ thuộc.
- Thay đổi cần thiết trong Maven/Gradle scope hoặc dependency configuration.

Không nên viết “module dependency removed” khi module vẫn xuất hiện với `requires static` và source vẫn cần nó để biên dịch.

## 10. Service boundary: uses và provides

Service contract là một phần module boundary dù consumer không import trực tiếp implementation class.

Consumer:

```java
module com.acme.catalog.app {
    requires com.acme.catalog.spi;
    uses com.acme.catalog.spi.ExportService;
}
```

Provider:

```java
module com.acme.catalog.csv {
    requires com.acme.catalog.spi;
    provides com.acme.catalog.spi.ExportService
        with com.acme.catalog.csv.CsvExporter;
}
```

Những thay đổi cần công bố gồm:

- Module provider mới hoặc module provider bị loại bỏ.
- Service interface được đổi tên hoặc chuyển sang module khác.
- Provider implementation hoặc hành vi mặc định thay đổi.
- Module consumer bắt đầu hoặc ngừng sử dụng service.
- Thay đổi cách đưa provider vào runtime image hoặc `ModuleLayer`.
- Service bị thay bằng API khác hoặc cần cấu hình provider tường minh.

Ví dụ changelog:

```markdown
### Changed — Service provider

The CSV exporter is now provided by module
`com.acme.catalog.csv` instead of `com.acme.catalog`.
Deployments must include the provider module and ensure it is
resolved (for example, through an explicit root or service binding).
```

Cần phân biệt “JAR có trên module path” và “module provider đã được resolve”. Một provider có thể nằm trong thư mục deployment nhưng chưa được đưa vào graph. Release notes nên chỉ ra yêu cầu khởi chạy hoặc linking nếu thay đổi service boundary làm khác cách khám phá provider.

## 11. Đổi tên module hoặc tách module là thay đổi migration rõ rệt

Giả sử trước đây consumer có:

```java
module com.acme.report {
    requires com.acme.catalog;
}
```

Phiên bản mới tách:

```text
com.acme.catalog.api
com.acme.catalog.impl
```

Nếu API chuyển sang module `com.acme.catalog.api`, consumer thường cần sửa:

```java
module com.acme.report {
    requires com.acme.catalog.api;
}
```

Changelog phải bao gồm cả mapping tên:

| Trước | Sau | Hành động consumer |
|---|---|---|
| `com.acme.catalog` | `com.acme.catalog.api` | Sửa `requires` và dependency artifact nếu thay đổi |
| `com.acme.catalog.internal` | `com.acme.catalog.impl.internal` | Không import trực tiếp; dùng API public thay thế |
| Provider nằm trong module gốc | Provider trong `com.acme.catalog.impl` | Đảm bảo provider module có trong runtime graph |

Nếu thay đổi package name, cung cấp ví dụ import trước/sau, không chỉ ví dụ `module-info.java`.

Đổi tên module có thể yêu cầu rebuild toàn bộ consumer modular JAR. Một số runtime configuration, launcher scripts, `--add-opens`, `--add-exports`, `--add-modules`, `--module-path` và file cấu hình plugin cũng cần cập nhật.

## 12. Binary compatibility, source compatibility và runtime compatibility

Changelog nên phân loại tác động theo giai đoạn thay vì chỉ một nhãn “breaking”:

| Loại tương thích | Cần xem xét |
|---|---|
| Source compatibility | Source consumer biên dịch lại có cần đổi `requires`, import hoặc API không? |
| Binary/runtime linkage | Bytecode consumer cũ có còn truy cập class/member qua graph runtime mới không? |
| Runtime behavior | `ServiceLoader`, reflection, provider discovery và tính năng runtime có còn hoạt động? |
| Deployment compatibility | Custom image, module path, launcher hoặc JDK version có phải thay đổi? |
| Build tooling compatibility | Maven/Gradle module path, compiler options, test runner hoặc processor path có thay đổi? |

Ví dụ, bỏ export một package có thể gây lỗi compile ở dự án consumer mới, nhưng bytecode đã biên dịch cũng có thể gặp `IllegalAccessError` nếu vẫn tham chiếu public class trong package không export.

Đổi một `opens` có thể không thay đổi khả năng compile code thông thường, nhưng làm reflection thất bại ở runtime.

Đổi `provides` có thể không tác động vào API source hay linkage nhưng làm `ServiceLoader` tìm được implementation khác hoặc không tìm thấy implementation nào.

Những khác biệt này nên xuất hiện trong phần “Impact” của changelog để người dùng biết cần chạy loại kiểm thử nào.

## 13. Mẫu changelog có cấu trúc

Có thể dùng một cấu trúc thống nhất cho mọi thay đổi module boundary:

```markdown
## [2.0.0] - YYYY-MM-DD

### Breaking changes

**JPMS boundary: <module-name>**

- Change: <exports / opens / requires / uses / provides / rename>
- Before: <old module descriptor behavior>
- After: <new module descriptor behavior>
- Affected consumers: <module names / packages / frameworks>
- Compile-time impact: <what compilation may reject>
- Runtime impact: <linkage, reflection, services, resolution>
- Migration: <concrete code / module-info / command changes>
- Workaround (if any): <temporary action and removal plan>

### Added

- <new public export, module or provider>

### Changed

- <behavioral or dependency changes>

### Removed

- <module, package export or service removed>

### Verification

- <supported JDK/runtime configurations and verification commands>
```

Dấu `<...>` trong template là placeholder cần thay bằng dữ liệu phát hành thực tế. Không cần lặp lại cùng thay đổi dưới nhiều mục nếu việc đó gây khó đọc; ưu tiên một mục có đủ thông tin và dẫn tới migration guide chi tiết.

Nếu project sử dụng định dạng Keep a Changelog, có thể đặt các entry vào các nhóm `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security` theo quy ước của project. Điều cốt lõi là người dùng nhìn thấy tác động JPMS, không phải tiêu đề nhóm cụ thể.

## 14. Ví dụ release note đầy đủ cho một lần thay đổi boundary

Giả sử release 2.0.0 của thư viện giả định `com.acme.catalog` thu hẹp API, tách provider và bổ sung dependency. Changelog có thể viết:

```markdown
## [2.0.0] - 2026-11-11

### Breaking changes

**JPMS module `com.acme.catalog`**

- Removed export `com.acme.catalog.legacy`.
  Consumers must switch to `com.acme.catalog.api`.
- Changed `com.acme.catalog.model` from unqualified
  `opens` to `opens ... to com.acme.json`.
  Other reflection frameworks need a supported integration.
- Module `com.acme.catalog.csv` now supplies
  `com.acme.catalog.spi.ExportService`.

### Changed

- Added dependency `requires java.net.http;`.
  Rebuild custom runtime images.
- `com.acme.model` is no longer a transitive
  readability dependency. Consumers that use its types
  must declare `requires com.acme.model;` directly.

### Migration

1. Replace legacy imports with the public API package.
2. Update any qualified reflection configuration.
3. Include and resolve the CSV provider module when needed.
4. Review module descriptors and runtime images.
5. Recompile and run modular integration tests.
```

Đây là ví dụ minh họa cách trình bày, không phải lịch sử phát hành của một thư viện có thật.

Khi phát hành chính thức, bổ sung link tới commit/PR, issue, migration guide hoặc API reference nếu project có những tài liệu đó. Người dùng cần một đường dẫn rõ từ việc phát hiện thay đổi đến các bước nâng cấp.

## 15. Migration guide nên có ví dụ trước/sau

Nếu có breaking change, changelog ngắn gọn nên dẫn sang hướng dẫn nâng cấp có code trước/sau. Ví dụ đổi module name:

Trước:

```java
module com.acme.report {
    requires com.acme.catalog;
}
```

Sau:

```java
module com.acme.report {
    requires com.acme.catalog.api;
}
```

Trước:

```java
import com.acme.catalog.legacy.LegacyCatalog;
```

Sau:

```java
import com.acme.catalog.api.CatalogClient;
```

Nếu một API thay đổi cả semantics, nên chỉ ra cách chuyển tham số, exception, lifecycle hoặc cấu hình provider tương ứng. Chỉ đổi tên import không đủ khi implementation có hành vi khác.

Với runtime image, hướng dẫn có thể bao gồm việc tạo lại image:

```shell
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.acme.report \
  --output runtime
```

Đường dẫn và root module trong ví dụ phải được thay theo build thực tế. Với Windows, phần tử module path được phân tách bằng dấu chấm phẩy thay vì dấu hai chấm.

Nếu provider cần được liên kết vào image thông qua service binding, có thể cần `--bind-services` hoặc một root module được chỉ định tường minh. Hướng dẫn nên nêu lựa chọn đúng cho kiến trúc triển khai.

## 16. Changelog cho các tình huống classpath và module path

Một JAR có thể được dùng ở hai chế độ:

1. **Classpath:** class được đưa vào unnamed module; descriptor trong JAR không được áp dụng như named module boundary.
2. **Module path:** module system nhận diện module name, áp dụng readability, exports và opens.

Vì vậy, một thay đổi chỉ liên quan `exports` có thể ảnh hưởng mạnh đến named-module consumers nhưng không có cùng tác động trực tiếp trên classpath consumers.

Changelog nên ghi tách:

```text
Affected: consumers running the library on the JPMS module path.
Classpath usage: no direct export-boundary change; verify API and
runtime behavior separately.
```

Không suy ra rằng classpath hoàn toàn không bị ảnh hưởng: class, method hoặc dependency vẫn có thể thay đổi độc lập với descriptor.

Nếu thư viện chuyển từ automatic module sang explicit module, hãy ghi tên module cũ/mới và các package không còn được export rộng. Một module explicit thường có boundary chặt hơn automatic module; nhiều import trước đây có thể cần sửa.

## 17. Dùng công cụ để thu thập thông tin release notes

Khi xây dựng changelog, cần so sánh **artifact trước và sau release**, không chỉ đọc diff của source descriptor.

### Xem descriptor của từng JAR

```shell
jar --describe-module --file catalog-client-1.9.0.jar
jar --describe-module --file catalog-client-2.0.0.jar
```

Đầu ra cho thấy module name, các `requires`, `exports`, `opens`, `uses` và `provides` được đóng gói. Với multi-release JAR, cần kiểm tra descriptor tương ứng với release Java mục tiêu.

### Xem module trong runtime hiện tại

```shell
java --list-modules
```

Đối với module nằm trên module path:

```shell
java --module-path mods --describe-module com.acme.catalog
```

Với custom runtime image, sử dụng executable bên trong image thay vì một lệnh `java` có thể trỏ tới JDK khác.

### Theo dõi resolution

```shell
java --show-module-resolution \
  --module-path mods \
  -m com.acme.report/com.acme.report.Main
```

Công cụ này giúp xác định module nào được resolve trong lần chạy cụ thể. Nó không tự chứng minh các nhánh chức năng dùng reflection hoặc service đã hoạt động, nên vẫn cần integration tests phù hợp.

### Phân tích dependency

```shell
jdeps --summary --module-path mods catalog-client-2.0.0.jar
```

`jdeps` hữu ích để tìm dependency tĩnh, không thay thế kiểm tra service provider, reflection hay artifact packing. Khi ghi “removed dependency”, hãy đối chiếu với descriptor và dependency graph build/runtime thực tế.

## 18. Đánh giá mức độ thay đổi phiên bản

Không có quy tắc JPMS nào bắt buộc một thay đổi `exports` phải tăng major version. Mức tăng phiên bản do chính sách tương thích của project quyết định, thường kết hợp với SemVer hoặc quy ước release khác.

Một cách cân nhắc:

- **Breaking boundary change:** xóa export được công bố, đổi module name đang được consumer dùng, bỏ provider nằm trong hợp đồng hỗ trợ, thay đổi reflection contract cần thiết. Với dự án áp dụng SemVer nghiêm ngặt, những thay đổi này thường được cân nhắc cho major release.
- **Backward-compatible API addition:** thêm package API mới được export hoặc thêm service tùy chọn mà không đổi hành vi hiện tại. Có thể phù hợp với minor release tùy chính sách.
- **Bug fix / maintenance:** sửa descriptor cho đúng hợp đồng đã tài liệu hóa mà không làm consumer hợp lệ bị ảnh hưởng. Có thể phù hợp với patch release, nhưng vẫn cần mô tả nếu hành vi thực tế thay đổi.

Điểm quan trọng là **hợp đồng đã được công bố và phạm vi consumer được hỗ trợ**, không chỉ số dòng thay đổi trong `module-info.java`. Nếu một package internal chưa bao giờ được hỗ trợ công khai nhưng từng bị export nhầm, việc đóng package có thể làm hỏng consumer đã phụ thuộc vào nó; changelog vẫn nên cảnh báo tác động thực tế.

## 19. Liên hệ giữa changelog và tài liệu API

Changelog trả lời “điều gì thay đổi ở release này”, còn các tài liệu khác trả lời “trạng thái hiện tại là gì”:

- **Module descriptor:** hợp đồng máy đọc được về readability, exports, opens và service bindings.
- **Javadoc/API reference:** các kiểu, phương thức và package được hỗ trợ.
- **Architecture documentation:** lý do tách module và hướng dependency.
- **Migration guide:** các bước nâng cấp giữa hai release.
- **Changelog:** lịch sử thay đổi, mức ảnh hưởng và điểm bắt đầu migration.

Không nên thay thế changelog bằng một snapshot của descriptor mới. Người dùng cần biết sự khác biệt **so với release trước**, đặc biệt khi dependency và cấu hình của họ được viết cho module name hoặc package cũ.

Trong tài liệu kiến trúc, có thể bổ sung sơ đồ:

```text
Before:
  com.acme.report --> com.acme.catalog
                           |
                           +--> com.acme.model

After:
  com.acme.report --> com.acme.catalog.api
                           |
                           +--> com.acme.model

Provider:
  com.acme.catalog.csv --> com.acme.catalog.spi
```

Sơ đồ này chỉ minh họa; cách hiển thị dependency cần phù hợp với descriptor thực tế. Changelog có thể liên kết tới sơ đồ hoặc migration guide thay vì lặp lại chi tiết quá dài.

## 20. Checklist cho maintainer khi phát hành thay đổi boundary

Trước khi công bố một release có thay đổi JPMS:

1. Xác định module names và package exports của cả bản cũ và mới từ artifact được đóng gói.
2. Liệt kê những directive `requires`, `requires transitive`, `requires static`, `exports`, `opens`, `uses`, `provides` đã thay đổi.
3. Phân loại consumer bị ảnh hưởng: compile-time imports, binary runtime access, deep reflection, service discovery hoặc deployment.
4. Ghi chính xác module/package/service name, tránh chỉ ghi Maven artifact coordinates.
5. Nếu có thay đổi tương thích ngược không đầy đủ, cung cấp migration steps với `module-info.java` và code trước/sau.
6. Ghi chú các cờ launcher, module path hoặc cấu hình `jlink` cần thay đổi.
7. Nếu đề xuất workaround như `--add-exports` hoặc `--add-opens`, mô tả đây là biện pháp tạm thời, phạm vi áp dụng và rủi ro phụ thuộc vào implementation nội bộ.
8. Phân biệt tác động với consumer trên classpath và trên module path.
9. Kiểm tra mô tả release bằng đúng phiên bản JDK và artifact mục tiêu.
10. Đặt mục breaking change ở vị trí dễ thấy; liên kết tới tài liệu migration khi nội dung vượt phạm vi changelog ngắn.

**Kết luận:** Mỗi thay đổi module boundary có thể thay đổi cách mã consumer được biên dịch, liên kết, nạp provider hoặc hoạt động với reflection. Changelog cần làm rõ **trước/sau, phạm vi ảnh hưởng và hành động nâng cấp** cho từng thay đổi quan trọng. Khi coi `module-info.java` là một phần của hợp đồng API và ghi chép có cấu trúc, nhóm phát triển sẽ giảm những lỗi khó hiểu khi người dùng nâng phiên bản thư viện hoặc tái tạo runtime image.