# Lập danh sách package và dependency hiện tại

Trước khi chuyển một ứng dụng Java từ classpath sang Java Platform Module System (JPMS), việc quan trọng nhất không phải viết ngay `module-info.java`, mà là **biết chính xác ứng dụng đang có những package, artifact và dependency nào**. Nếu thiếu bước kiểm kê này, quá trình migration dễ vướng split package, thư viện không tương thích với module path, dependency xuất hiện chỉ tại runtime hoặc truy cập API nội bộ JDK.

Bài học này hướng dẫn tạo một **baseline inventory** cho ứng dụng hiện tại: danh sách package, nguồn sở hữu package, dependency trực tiếp/bắc cầu, module name dự kiến, phạm vi sử dụng, dependency động và rủi ro cần xử lý. Sau khi kiểm kê, nhóm phát triển mới có đủ dữ liệu để quyết định ranh giới module và thứ tự chuyển đổi.

## 1. Mục tiêu của bước kiểm kê

Kết quả nên trả lời được các câu hỏi sau:

1. Ứng dụng hiện có những package Java nào?
2. Mỗi package thuộc source set, module logic, JAR hay dependency nào?
3. Những JAR nào đang nằm trên compile classpath, runtime classpath và test classpath?
4. Artifact nào là modular JAR, automatic module hay thư viện chỉ dành cho classpath?
5. Mã của ứng dụng đang phụ thuộc vào package/lớp của thư viện nào?
6. Có package cùng tên nằm trong nhiều artifact không?
7. Có dependency vào package nội bộ của JDK, ví dụ `sun.*` hoặc `jdk.internal.*`, không?
8. Có reflection, `ServiceLoader`, JNI, serialization hoặc class loading động không?
9. Dependency nào thuộc API công khai, dependency nào chỉ dùng trong implementation?
10. Nếu chia module, ranh giới package/module và quan hệ `requires` dự kiến là gì?

Không nên xem inventory chỉ là danh sách file `.jar`. Một JAR có thể chứa nhiều package, một package có thể bị chia giữa nhiều JAR và một dependency có thể chỉ xuất hiện qua cấu hình runtime, service provider hoặc reflection.

## 2. Xác định phạm vi dự án và phiên bản Java

Trước tiên, ghi nhận thông tin nền:

- Tên ứng dụng hoặc repository, nhánh/commit đang kiểm kê.
- JDK dùng để build và JDK dùng để chạy trong môi trường thực tế.
- Build tool và phiên bản, ví dụ Maven hoặc Gradle.
- Danh sách subproject/submodule của build.
- Các source set: main, test, integrationTest, generated sources.
- Các môi trường chạy: development, CI, container, server, desktop.
- Kiến trúc đóng gói: runnable JAR, WAR, EAR, thư mục `lib/`, fat/uber JAR hay native launcher.

Ví dụ ghi nhận:

```text
Project: inventory-service
Revision: <commit-hash>
Build tool: Gradle 8.x
Compile JDK: 21
Runtime JDK: 21
Artifacts: app.jar, catalog.jar, persistence.jar
Execution: java -cp ... com.example.Main
Target: migrate to named modules
```

Thông tin này giúp các lần chạy công cụ có thể lặp lại. Nếu một máy dùng JDK 17 nhưng CI dùng JDK 21, kết quả phân tích dependency vào JDK modules hoặc multi-release JAR có thể khác nhau.

**Chỉ kiểm kê trong đúng cấu hình đang sử dụng:** với một hệ thống phức tạp, có thể cần bản inventory riêng cho runtime production và test runtime.

## 3. Phân biệt artifact, package, class và module

Bốn khái niệm không đồng nghĩa:

| Đơn vị | Ví dụ | Cần ghi nhận |
|---|---|---|
| Artifact | `logging-core-2.0.jar` | File, tọa độ Maven, phiên bản, nơi lấy |
| Package | `com.example.logging.api` | Tập lớp cùng package, chủ sở hữu |
| Class | `com.example.logging.api.Logger` | Tham chiếu thực tế từ bytecode |
| Module | `com.example.logging` | Tên trong descriptor hoặc automatic module name |

Một artifact có thể chứa nhiều package. Một module có thể được đóng gói thành modular JAR, hoặc tồn tại dạng thư mục exploded module. Package Java không tự biến thành module; quá trình migration cần chủ động thiết kế đơn vị module chứa các package đó.

Ví dụ:

```text
src/main/java/
└── com/example/
    ├── app/
    ├── catalog/api/
    ├── catalog/internal/
    ├── persistence/
    └── util/
```

Không thể kết luận rằng `com.example.catalog` là module chỉ vì các package cùng prefix. Cần xác định dependency giữa các package, tính độc lập và API được công khai trước khi chọn ranh giới module.

## 4. Liệt kê package từ source code

Với source Java, có thể tìm khai báo package:

```java
package com.example.catalog.api;
```

Tùy hệ điều hành, dùng IDE, lệnh tìm kiếm hoặc script để thu thập các dòng `package` từ những file `.java`. Ví dụ trên hệ thống có `grep`:

```shell
grep -R "^package " src/main/java --include="*.java"
```

Nếu dùng PowerShell:

```powershell
Get-ChildItem src/main/java -Recurse -Filter *.java |
  Select-String -Pattern '^\s*package\s+'
```

Kết quả thô cần được chuẩn hóa: bỏ dấu chấm phẩy, bỏ trùng, tách package với đường dẫn file và source set.

Một bảng hữu ích:

| Package | Source set | Thư mục | Nhóm chức năng | API/implementation |
|---|---|---|---|---|
| `com.example.catalog.api` | main | `src/main/java` | Catalog contract | API |
| `com.example.catalog.internal` | main | `src/main/java` | Catalog implementation | Internal |
| `com.example.persistence` | main | `src/main/java` | Database adapter | Implementation |
| `com.example.catalog.test` | test | `src/test/java` | Unit tests | Test-only |

Không gộp package từ main và test mà không đánh dấu source set. Nhiều dự án có test class nằm trong cùng package với mã production để truy cập các thành viên package-private; khi chuyển sang JPMS, đây là một điểm thiết kế cần chú ý.

## 5. Liệt kê package từ JAR và bytecode

Đối với dependency bên thứ ba, package không nằm trong source repository mà nằm trong artifact đã biên dịch.

Xem nội dung JAR:

```shell
jar --list --file libs/catalog-library.jar
```

Đầu ra có thể chứa:

```text
META-INF/
META-INF/MANIFEST.MF
com/vendor/catalog/Api.class
com/vendor/catalog/internal/Impl.class
```

Từ đường dẫn class có thể suy ra:

```text
com.vendor.catalog
com.vendor.catalog.internal
```

Lưu ý khi kiểm kê:

- Không tính `module-info.class` là class thuộc package thông thường.
- Một JAR có thể có default-package classes (không có khai báo package), vốn không phù hợp với explicit named module.
- Các tệp trong `META-INF/services` thể hiện service configuration truyền thống, cần ghi riêng.
- Multi-release JAR có thể có lớp ở `META-INF/versions/<n>/`, nên cần xét phiên bản JDK mục tiêu.
- Fat JAR hoặc shaded JAR có thể chứa nhiều thư viện đã gộp; cần nhận diện package theo nội dung thực tế, không chỉ tên artifact.
- Resource folder không đồng nghĩa với package Java; danh sách package nên dựa chủ yếu trên class metadata và cấu trúc bytecode.

Nếu có thể, xuất một danh sách unique `package → artifact`, rồi đánh dấu package xuất hiện trong nhiều artifact để phát hiện split package sớm.

## 6. Lấy dependency graph từ Maven

Với dự án Maven, dependency được khai báo trong `pom.xml`, nhưng kết quả thực tế còn chịu dependency bắc cầu, scope và dependency management.

Xem dependency tree:

```shell
mvn dependency:tree
```

Xuất ra file để lưu cùng inventory:

```shell
mvn dependency:tree -DoutputFile=dependency-tree.txt
```

Cần ghi ít nhất:

- `groupId:artifactId:version`.
- Scope: `compile`, `runtime`, `provided`, `test` hoặc scope khác.
- Dependency trực tiếp hay bắc cầu.
- Đường dẫn parent dependency đã kéo artifact vào build.
- Có conflict/omission theo mediation hay không.
- Phiên bản thực sự được chọn.

Ví dụ:

```text
com.example:inventory-service:1.0
+- com.vendor:json-codec:3.2:compile
|  \- com.vendor:core-api:3.0:compile
+- org.slf4j:slf4j-api:2.0:compile
\- org.junit.jupiter:junit-jupiter:5.10:test
```

Ví dụ chỉ minh họa. Tên và phiên bản thật phải lấy từ output của dự án.

Trong JPMS, không phải dependency Maven nào cũng trở thành một `requires`. Ví dụ dependency chỉ phục vụ test không nhất thiết thuộc module descriptor production. Vì vậy, scope phải được giữ trong bảng inventory.

## 7. Lấy dependency graph từ Gradle

Gradle có thể đưa dependency khác nhau vào từng configuration, ví dụ `compileClasspath`, `runtimeClasspath`, `testRuntimeClasspath`.

Các lệnh hữu ích:

```shell
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
```

Trên Windows, dùng `gradlew.bat` nếu dự án có Gradle Wrapper.

Khi cần giải thích một dependency xuất phát từ đâu:

```shell
./gradlew dependencyInsight --dependency json-codec --configuration runtimeClasspath
```

Lệnh `dependencyInsight` giúp hiểu phiên bản được chọn và nguyên nhân một artifact có mặt trong configuration.

Nên ghi inventory cho cả compile và runtime:

| Artifact | Compile | Runtime | Test | Direct/Transitive |
|---|---|---|---|---|
| `catalog-api.jar` | Có | Có | Có | Direct |
| `jdbc-driver.jar` | Không/tuỳ cấu hình | Có | Có | Runtime |
| `junit-jupiter.jar` | Không | Không | Có | Test |
| `legacy-core.jar` | Có | Có | Có | Transitive |

Một thư viện chỉ có ở runtime, ví dụ JDBC driver hoặc service provider, rất dễ bị bỏ sót nếu chỉ xem `compileClasspath`.

## 8. Dùng jdeps để phân tích dependency từ bytecode

`jdeps` là công cụ JDK đọc class/JAR và phân tích dependency tĩnh. Đây là nguồn dữ liệu khác với dependency tree của build tool:

- Build tool cho biết artifact được cấu hình hoặc phân giải vào build.
- `jdeps` cho biết bytecode thực sự tham chiếu tới các lớp/package/module nào mà công cụ có thể nhận diện.

Xem dependency theo package:

```shell
jdeps -verbose:package --class-path "libs/*" build/libs/inventory-service.jar
```

Trên Windows, các dấu quote và wildcard cần phù hợp với shell; `--class-path` nhận đường dẫn phù hợp cho các dependency dạng classpath.

Xem dependency ở mức module JDK:

```shell
jdeps --list-deps build/libs/inventory-service.jar
```

Ước lượng các module cần cho runtime image:

```shell
jdeps --print-module-deps build/libs/inventory-service.jar
```

Nếu ứng dụng đã có explicit module và các dependency trên module path:

```shell
jdeps --module-path mods --list-deps dist/com.example.app.jar
```

Đối với multi-release JAR:

```shell
jdeps --multi-release 21 --class-path "libs/*" --list-deps build/libs/inventory-service.jar
```

Phiên bản `21` chỉ là ví dụ; dùng phiên bản tương ứng với JDK mục tiêu.

**Không suy ra rằng jdeps phân tích đầy đủ runtime behavior.** Reflection, tên lớp lấy từ cấu hình, code generation, JNI và service loading có thể không để lại dependency tĩnh rõ ràng trong bytecode.

## 9. Kiểm tra dependency vào JDK internal API

Một bước migration quan trọng là phát hiện việc dùng API nội bộ JDK.

Lệnh:

```shell
jdeps --jdk-internals --class-path "libs/*" build/libs/inventory-service.jar
```

Kết quả giúp nhận diện một số tham chiếu tới `sun.*`, `jdk.internal.*` hoặc API JDK nội bộ khác.

Nên ghi lại:

- Class nào phụ thuộc API nội bộ.
- Internal class/package nào được tham chiếu.
- Mục đích sử dụng.
- API chuẩn hoặc API JDK được tài liệu hóa có thể thay thế.
- Thư viện hiện tại có phiên bản mới đã loại dependency nội bộ hay chưa.

Ví dụ một bảng:

| Thành phần | Internal API | Nguyên nhân | Hướng xử lý |
|---|---|---|---|
| Legacy serializer | `sun.misc.Unsafe` | Truy cập bộ nhớ cấp thấp | Nâng thư viện hoặc chuyển sang `VarHandle`/API phù hợp |
| Custom reflection | `java.lang` private fields | Cấu hình framework | Dùng public API, chỉnh framework hoặc `opens` có phạm vi |
| Legacy encoding | API nội bộ | Base64 | `java.util.Base64` |

Không nên chỉ thêm `--add-exports` hoặc `--add-opens` để bỏ qua vấn đề mà không ghi nhận dependency rủi ro.

## 10. Xác định module name của các dependency

Một thư viện có thể thuộc một trong ba nhóm chính:

1. **Explicit named module:** chứa `module-info.class` và khai báo tên module rõ ràng.
2. **Automatic module:** không có descriptor explicit nhưng được đặt trên module path, có tên từ `Automatic-Module-Name` hoặc từ tên JAR.
3. **Classpath library:** hiện được nạp vào unnamed module từ classpath; có thể cần chiến lược migration riêng.

Với từng JAR, dùng:

```shell
jar --describe-module --file libs/catalog-library.jar
```

Lệnh này giúp xem module name và thông tin descriptor mà công cụ JAR nhận diện được.

Ví dụ inventory:

| Artifact | Module name | Loại | Package chính | Ghi chú |
|---|---|---|---|---|
| `catalog-api.jar` | `com.example.catalog.api` | Explicit | `com.example.catalog.api` | Có `module-info.class` |
| `legacy-codec.jar` | `com.vendor.legacycodec` | Automatic | `com.vendor.codec` | Tên từ manifest |
| `old-orm.jar` | Cần xác định | Classpath | `org.example.orm` | Có thể chưa chuyển được |

Không đoán module name theo tọa độ Maven hoặc tên file. Với automatic module được suy ra từ filename, việc đổi tên JAR khi phát hành có thể làm tên module thay đổi; vì vậy cần kiểm tra cụ thể.

## 11. Phát hiện split package từ inventory

Split package là một tên package xuất hiện trong nhiều module/artifact. Ví dụ:

```text
first.jar:
    com/example/shared/First.class

second.jar:
    com/example/shared/Second.class
```

Dù hai JAR không chứa cùng class, cả hai đều chứa package `com.example.shared`.

Trên classpath, ứng dụng có thể vẫn chạy tùy cách class loader tìm class. Khi cả hai JAR trở thành named modules, module resolution hoặc layer definition có thể từ chối cấu hình.

Một bảng phát hiện:

| Package | Artifact A | Artifact B | Trạng thái |
|---|---|---|---|
| `com.example.shared` | `first.jar` | `second.jar` | Split package |
| `org.vendor.util` | `util-old.jar` | `util-new.jar` | Có thể là dependency trùng phiên bản |
| `com.example.api` | `api.jar` | `impl.jar` | Cần xác định ownership |

Sau khi tìm bằng danh sách package, có thể kiểm tra module path:

```shell
java --module-path mods --validate-modules
```

Và quan sát quá trình resolution của ứng dụng:

```shell
java --show-module-resolution --dry-run --module-path mods -m com.example.app/com.example.app.Main
```

Hai lệnh này hỗ trợ đánh giá module graph thực tế. Chúng không thay thế việc kiểm kê package trong mọi JAR vì một module có thể nằm trên path nhưng chưa được phân giải trong một lần chạy cụ thể.

## 12. Lập dependency matrix giữa các package

Artifact dependency tree và module descriptor chưa đủ để quyết định ranh giới module. Cần biết package nào đang dùng package nào.

Ví dụ:

| Package nguồn | Package đích | Mức sử dụng | Dự kiến |
|---|---|---|---|
| `com.example.app` | `com.example.catalog.api` | API công khai | `requires com.example.catalog` |
| `com.example.catalog.internal` | `com.example.persistence` | Implementation | Cân nhắc tái cấu trúc |
| `com.example.app` | `java.sql` | JDBC | `requires java.sql` |
| `com.example.app` | `org.slf4j` | Logging | Xác định module name chính xác |

Khi chuyển sang named module, một import Java không đồng nghĩa một `requires` mới, vì `requires` là quan hệ module → module. Nhiều package cùng thuộc một module chỉ cần một dependency ở mức module.

Tuy nhiên, dependency lộ trong API public có thể cần `requires transitive` nếu consumer đọc module hiện tại cũng cần đọc module chứa kiểu đó.

Ví dụ:

```java
module com.example.catalog {
    requires transitive com.example.money;
    exports com.example.catalog.api;
}
```

Nếu API catalog công khai dùng kiểu của money module, quan hệ transitive có thể phù hợp. Nếu money chỉ dùng trong implementation nội bộ, `requires` thông thường thường là lựa chọn tốt hơn.

## 13. Kiểm kê dependency động và reflection

Phân tích dependency từ source hoặc bytecode không phát hiện hết mọi nhu cầu runtime. Cần tìm riêng các cơ chế nạp động:

- `Class.forName("...")` với tên class dạng chuỗi.
- `ClassLoader.loadClass(...)`.
- Reflection: `getDeclaredField`, `getDeclaredMethod`, `setAccessible`.
- `ServiceLoader.load(...)`.
- Java SPI cũ qua `META-INF/services`.
- JNI hoặc native library loading.
- ORM, JSON serializer, dependency injection framework.
- Dynamic proxy và bytecode generation.
- Plugin nạp từ thư mục ngoài.
- Resource lookup dựa trên class loader.
- Java serialization có tên class trong dữ liệu persisted.

Ví dụ:

```java
Class<?> type = Class.forName(
        "com.vendor.jdbc.DriverImpl"
);
```

Tên lớp dạng chuỗi có thể không được `jdeps` nhận diện là dependency tĩnh như import trực tiếp.

Một bảng nên có:

| Cơ chế | Vị trí | Dependency runtime | Rủi ro JPMS |
|---|---|---|---|
| Reflection | `JsonMapper` | Domain model private fields | Có thể cần `opens` |
| ServiceLoader | `CodecFactory` | Provider modules | `uses`/`provides` |
| JNI | `NativeBridge` | Native library | Packaging và môi trường |
| Class.forName | `DriverFactory` | JDBC driver | Dynamic discovery |

Điều này giúp team tránh tình huống app biên dịch thành công nhưng thất bại khi runtime framework cố truy cập private member hoặc load provider.

## 14. Phân biệt compile, runtime và test dependency

Một phần quan trọng của inventory là **scope**. Không phải dependency nào có trong test cũng cần được export hoặc đưa vào module graph production.

Ví dụ:

```text
compile:
  catalog-api.jar
  logging-api.jar

runtime:
  catalog-impl.jar
  logging-provider.jar
  jdbc-driver.jar

test:
  junit.jar
  mockito.jar
  testcontainers.jar
```

Khi tạo `module-info.java`, module production nên phản ánh dependency production. Các thư viện test có thể cần chiến lược riêng: module test riêng, test trên module path, `--patch-module` hoặc cấu hình `--add-opens` phù hợp.

Nếu không ghi scope, việc thêm tất cả dependency vào module descriptor có thể làm module graph phình to và tăng độ ghép nối.

## 15. Phân loại dependency theo mức rủi ro migration

Không phải mọi dependency đều khó chuyển sang JPMS như nhau. Có thể phân nhóm:

| Nhóm | Dấu hiệu | Độ ưu tiên |
|---|---|---|
| Thấp | Explicit named module, API export rõ | Dễ kiểm tra và chuyển |
| Trung bình | Automatic module, tên ổn định, không split package | Cần xác nhận module graph |
| Cao | Split package, classpath-only dependency | Cần thiết kế lại hoặc nâng thư viện |
| Cao | JDK internal API, deep reflection | Cần thay API hoặc cấu hình access |
| Cao | Plugin loading động, nhiều class loader | Cần thử nghiệm ModuleLayer/ServiceLoader |

Mức rủi ro còn phụ thuộc ứng dụng sử dụng thư viện như thế nào. Một thư viện automatic module có thể hoạt động ổn định trong môi trường cụ thể; một explicit module vẫn có thể gây vấn đề nếu dependency/API không phù hợp.

Đây là bảng để hoạch định công việc, không phải kết luận tương thích chỉ dựa vào tên hoặc định dạng artifact.

## 16. Mẫu bảng inventory tổng hợp

Một bảng tối thiểu có thể gồm các cột:

| Cột | Mục đích |
|---|---|
| `artifact` | Tên file hoặc tọa độ Maven/Gradle |
| `version` | Phiên bản thực tế được resolve |
| `scope` | Compile, runtime, test... |
| `module_name` | Tên module xác minh từ descriptor |
| `module_type` | Explicit, automatic, classpath-only |
| `packages` | Danh sách package artifact sở hữu |
| `depends_on` | Artifact/module khác được tham chiếu |
| `exports_needed` | Package cần công khai cho module khác |
| `reflection` | Có truy cập reflection hay không |
| `services` | `uses`, `provides`, SPI file |
| `jdk_internals` | Có phụ thuộc nội bộ JDK hay không |
| `split_package` | Package trùng với artifact khác |
| `migration_action` | Giữ, nâng version, tách/gộp, relocate |
| `owner` | Nhóm hoặc người chịu trách nhiệm |
| `evidence` | Lệnh/file đã xác nhận thông tin |

Ví dụ vài dòng dữ liệu:

```text
artifact,scope,module_name,module_type,migration_action
catalog-api.jar,compile,com.example.catalog,explicit,keep
legacy-codec.jar,runtime,com.vendor.codec,automatic,verify
legacy-orm.jar,runtime,unknown,classpath-only,upgrade
```

Đây là dữ liệu minh họa, không phải kết quả của một dự án cụ thể.

Tài liệu inventory nên lưu cả bằng chứng: command line dùng để tạo dữ liệu, đầu ra `jdeps`, dependency tree và JDK version. Khi dependency thay đổi, team có thể chạy lại và so sánh với baseline cũ.

## 17. Từ package inventory sang module boundaries

Sau khi có inventory, có thể thiết kế module theo từng bước:

1. Nhóm các package thuộc cùng chức năng và có ownership rõ.
2. Xác định package API sẽ được `exports`.
3. Giữ implementation package không export trừ khi có lý do hợp lệ.
4. Xác định dependency giữa các nhóm package để chuyển thành `requires`.
5. Phát hiện dependency vòng giữa các module dự kiến.
6. Đánh dấu dependency xuất hiện trong public API có thể cần `requires transitive`.
7. Thiết kế service interface và `uses`/`provides` cho implementation thay thế được.
8. Ghi lại các package cần `opens` cho framework reflection.
9. Xử lý split package trước khi phân chia thành các named modules.
10. Chuyển đổi theo từng module, kiểm tra compile, runtime và test sau mỗi bước.

Không cần module hóa mọi package thành một module riêng. Module boundary nên phản ánh hợp đồng và khả năng tiến hóa độc lập của các thành phần, không chỉ cấu trúc thư mục.

## 18. Ví dụ phân tích từ hệ thống classpath

Giả sử một ứng dụng hiện chạy bằng:

```shell
java -cp "app.jar:lib/*" com.example.app.Main
```

Các thư viện gồm:

```text
app.jar
lib/catalog-api.jar
lib/catalog-impl.jar
lib/json-codec.jar
lib/jdbc-driver.jar
```

Bước kiểm kê cho thấy:

- `app.jar` chứa `com.example.app`.
- `catalog-api.jar` chứa `com.example.catalog.api`.
- `catalog-impl.jar` chứa `com.example.catalog.internal`.
- `json-codec.jar` chứa JSON provider và metadata SPI.
- `jdbc-driver.jar` chỉ cần ở runtime.
- Một số domain model bị framework truy cập qua reflection.

Từ đó, kế hoạch module hóa ban đầu có thể là:

```java
module com.example.catalog {
    exports com.example.catalog.api;
}
```

```java
module com.example.app {
    requires com.example.catalog;
    requires java.sql;

    // Các service dependency cần được xem xét riêng.
}
```

Tuy nhiên, hai JAR catalog có thực sự hợp thành một module hay không cần quyết định theo package ownership, cách build và dependency. Không nên viết descriptor trên chỉ vì hai artifact có tên giống nhau.

Nếu JSON provider nằm trong automatic module, tên module thực tế phải được kiểm tra trước khi khai báo dependency hoặc tổ chức service binding.

## 19. Những sai lầm thường gặp

**Chỉ đọc pom.xml hoặc build.gradle mà không xem dependency được resolve.**

Build tool có dependency bắc cầu, dependency management và version mediation. Dùng `mvn dependency:tree` hoặc Gradle dependency reports để xác nhận bản thực tế.

**Chỉ xem import trong source code.**

Code động, reflection, `ServiceLoader` hoặc thư viện runtime có thể không xuất hiện dưới dạng import. Cần ghi riêng dependency động.

**Dựa hoàn toàn vào jdeps.**

`jdeps` phân tích bytecode và không phát hiện đầy đủ reflection/dynamic loading. Cần đối chiếu dữ liệu build, runtime và kiểm thử.

**Không kiểm kê package nội bộ của JAR.**

Hai JAR có tên khác nhau vẫn có thể chứa cùng package. Split package chỉ lộ ra khi đếm package theo artifact.

**Nhầm tên package với module name.**

Tên module có thể khác package, tên JAR và tọa độ Maven. Hãy kiểm tra descriptor.

**Gộp test dependency vào production.**

Khi chuyển sang JPMS, test setup có thể cần cấu hình riêng; không nên biến mọi dependency của test thành `requires` production.

**Bỏ qua JDK version.**

Multi-release JAR, module JDK có sẵn và API nội bộ có thể thay đổi giữa các phiên bản Java. Inventory phải có JDK target.

## 20. Quy trình kiểm kê đề xuất

Có thể thực hiện theo checklist:

1. **Chốt baseline:** commit, toolchain, JDK, môi trường và tập artifact.
2. **Trích xuất build graph:** Maven dependency tree hoặc Gradle configurations.
3. **Kiểm kê source packages:** tìm package declaration theo từng source set.
4. **Kiểm kê JAR packages:** dùng `jar --list`, tính package → artifact.
5. **Xác định module name:** dùng `jar --describe-module` cho từng JAR.
6. **Phân tích bytecode:** chạy `jdeps` để lấy package/module dependencies.
7. **Quét JDK internals:** chạy `jdeps --jdk-internals`.
8. **Tìm dependency động:** reflection, JNI, service files, plugin registry, generated code.
9. **Tìm split package:** so sánh danh sách package và kiểm tra module path.
10. **Tách scope:** compile, runtime, test và những môi trường đặc biệt.
11. **Lập migration matrix:** module dự kiến, dependency, exports, opens, services và rủi ro.
12. **Lưu bằng chứng:** command line, output công cụ, phiên bản toolchain và ngày kiểm kê.

Sau bước này, nhóm phát triển có thể xem xét module boundaries và chuyển từng phần sang `module-info.java` trên dữ liệu thực tế thay vì phỏng đoán.

## Kết luận

Lập danh sách package và dependency hiện tại là bước nền tảng khi migration sang JPMS. Cần kiểm kê ở nhiều cấp độ: source package, JAR package, dependency graph của build tool, dependency từ bytecode, module name và các cơ chế runtime động.

`mvn dependency:tree`, Gradle dependency reports, `jar --list`, `jar --describe-module`, `jdeps`, `java --validate-modules` và `--show-module-resolution` là những công cụ bổ trợ cho nhau. Không công cụ nào đơn lẻ cho thấy đầy đủ cấu trúc runtime của một ứng dụng lớn.

Một inventory tốt phải cho biết package thuộc artifact nào, dependency đến từ đâu, scope nào sử dụng nó, module name có thật là gì, rủi ro split package/JDK internal API ra sao và lựa chọn migration tiếp theo. Khi có baseline đáng tin cậy, việc thiết kế `requires`, `exports`, `opens` và service binding sẽ có cơ sở rõ ràng, giảm rủi ro khi chuyển từ classpath sang module path.
