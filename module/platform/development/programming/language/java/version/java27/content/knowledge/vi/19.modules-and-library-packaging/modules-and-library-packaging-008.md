# Phân tích phụ thuộc bằng jdeps và kiểm soát split package trong Java 27

Khi một ứng dụng gồm nhiều JAR, việc biên dịch thành công chưa bảo đảm nó sẽ khởi chạy đúng trên **module path**. Một thư viện có thể tham chiếu module không khai báo, kéo theo JDK internal API, thiếu dependency lúc triển khai hoặc chia sẻ cùng một package với một thư viện khác. Các lỗi này liên quan tới **kiến trúc đóng gói**, không chỉ tới nội dung từng class.

Trong **Java SE 27**, hai chủ đề cần được xem xét cùng nhau:

- `jdeps` (*Java class dependency analyzer*) là công cụ đi kèm JDK để **phân tích phụ thuộc tĩnh** từ các class đã biên dịch, thư mục class, JAR và named module.
- **Split package** là trường hợp một package Java cùng tên xuất hiện trong nhiều nguồn đóng gói/module khác nhau. Trên module path, các package chồng lấn có thể làm **module resolution, biên dịch hoặc khởi tạo module layer thất bại**.

Bài thuộc chương **Module và đóng gói thư viện**. Mục tiêu là biết phân tích dependency bằng công cụ JDK 27, đọc được bản chất xung đột và áp dụng cách khắc phục bền vững. Không dùng API nội bộ đã không còn được hỗ trợ làm phương án thiết kế mới.

## 1. Phân biệt package, JAR và module

Ba khái niệm liên quan nhưng không đồng nghĩa:

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| Java package | Không gian tên của các class/interface | `com.acme.orders.api` |
| JAR | Artifact lưu class và tài nguyên | `orders.jar` |
| Named module | Đơn vị JPMS có tên, dependency và chính sách xuất/mở package | `com.acme.orders` |
| Modular JAR | JAR chứa `module-info.class` thích hợp | `orders.jar` đóng gói module thật |
| Automatic module | JAR thường được đặt trên module path, tên module được suy ra hoặc lấy từ manifest | Một dependency chưa có descriptor |
| Unnamed module | Code được nạp từ classpath theo cách tương thích | Một ứng dụng chưa modularize |

Ví dụ `module-info.java` của một named module:

```java
module com.acme.orders {
    requires java.sql;
    exports com.acme.orders.api;
}
```

Điểm cần hiểu:

1. `requires java.sql` cho phép module hiện tại **đọc** module `java.sql`.
2. `exports com.acme.orders.api` cho phép module khác truy cập các kiểu public đủ điều kiện của package API.
3. Một class có khai báo `public` trong package **không được export** vẫn không tự nhiên truy cập được từ module khác.
4. `java.base` được mọi module đọc ngầm định.
5. `com.acme.orders` và `com.acme.orders.internal` là **hai package độc lập**. Cùng tiền tố không đồng nghĩa là cùng package.

Khái niệm *module readability* và *package accessibility* phải được tách biệt. Một module có thể đọc module khác, nhưng chỉ sử dụng trực tiếp các package được module kia xuất phù hợp cho nó.

## 2. Classpath và module path ảnh hưởng đến xung đột như thế nào?

JDK 27 vẫn hỗ trợ cả classpath và module path:

| Đặc điểm | Classpath (`--class-path`) | Module path (`--module-path`) |
| --- | --- | --- |
| JAR không có `module-info.class` | Nằm trong unnamed module | Có thể trở thành automatic module |
| Kiểm soát truy cập package theo descriptor | Không hoạt động như named module | Có quy tắc `requires`, `exports`, `opens` |
| Hai JAR chứa class thuộc cùng package | Có thể cùng tồn tại, nhưng dễ xảy ra shadowing/xung đột phiên bản | Có thể phá vỡ tính nhất quán JPMS |
| Thứ tự duyệt/phân giải class | Phụ thuộc vào cơ chế class loader/classpath | Dựa trên module graph và class loader |
| Kiểm chứng cấu hình module | Không có descriptor cho code classpath | Có thể dùng `--validate-modules` và module resolution |

Không nên nói rằng “cứ hai JAR có cùng package thì JVM luôn lập tức báo lỗi”. Hệ quả phụ thuộc việc chúng thuộc **module nào, module nào được resolve, quan hệ đọc/xuất package và cách gán module vào class loader**.

Tuy vậy, khi thiết kế named modules trên module path, nguyên tắc an toàn là **mỗi package phải có chủ sở hữu rõ ràng**, không phân tán class của cùng package giữa nhiều module.

## 3. jdeps phân tích được gì và giới hạn ở đâu?

`jdeps` dựa trên thông tin tĩnh của class file. Nó hữu ích để:

- Xem class/package nào phụ thuộc class/package khác.
- Nhận diện module JDK được dùng như `java.sql` hoặc `java.xml`.
- Phân tích đường phụ thuộc ở mức class, package, archive và module.
- Tìm tham chiếu tới **JDK internal API** với `--jdk-internals`.
- Tìm **missing dependencies** với `--missing-deps`.
- Đánh giá module graph và descriptor với `--check`.
- Sinh danh sách module để hỗ trợ packaging/runtime image bằng `--print-module-deps`.
- Xuất sơ đồ dependency dạng DOT.

Nhưng `jdeps` **không thực thi mã** và không thể tự động phát hiện chính xác mọi phụ thuộc sinh động như:

- `Class.forName(...)` khi tên class lấy từ file cấu hình.
- Reflection, dependency injection, runtime proxy hoặc bytecode sinh động.
- Service provider chỉ được phát hiện lúc chạy nếu không được biểu diễn qua các tham chiếu/descriptor có thể phân tích tĩnh.
- Tài nguyên không phải class, file cấu hình và quy tắc nạp plugin bên ngoài.

**Không có cạnh trong kết quả jdeps không có nghĩa dependency runtime hoàn toàn không tồn tại.** Cũng không có nghĩa các JAR không có split package. Việc kiểm tra package chồng lấn cần thêm bước kiểm kê nội dung JAR và kiểm chứng module graph.

## 4. Những tùy chọn jdeps đáng nhớ trong Java 27

| Tùy chọn hoặc ví dụ | Ý nghĩa | Dùng khi |
| --- | --- | --- |
| `jdeps -s app.jar` | Tóm tắt dependency | Quan sát nhanh |
| `jdeps --verbose:package app.jar` | Phụ thuộc theo package | Kiểm tra coupling giữa package |
| `jdeps --verbose:class app.jar` | Phụ thuộc theo class | Xác định class gây ra dependency |
| `jdeps --api-only app.jar` | Phụ thuộc trong API public/protected liên quan | Review API thư viện |
| `jdeps --class-path lib/dependency.jar app.jar` | Bổ sung classpath để phân giải | Phân tích JAR chưa modular |
| `jdeps --module-path dist --module com.acme.app` | Phân tích một named module | Đánh giá JPMS |
| `jdeps --list-deps app.jar` | Danh sách module dependencies và package JDK internal được tham chiếu | Kiểm kê module |
| `jdeps --list-reduced-deps app.jar` | Bỏ các cạnh đọc được suy ra | Làm gọn đồ thị |
| `jdeps --print-module-deps app.jar` | Xuất module list ngăn bằng dấu phẩy | Đầu vào tham khảo cho `jlink` |
| `jdeps --module-path dist --check com.acme.app` | Review descriptor và đồ thị module | Đánh giá requires/exports |
| `jdeps --jdk-internals app.jar` | Tìm JDK internal API | Kiểm tra khả năng nâng cấp JDK |
| `jdeps --missing-deps app.jar` | Tìm những dependency chưa phân giải | Kiểm tra input phân tích |
| `jdeps --multi-release 27 library.jar` | Chọn lớp phù hợp mức Java 27 của multi-release JAR | Thư viện hỗ trợ nhiều release |
| `jdeps --dot-output graphs app.jar` | Xuất tệp đồ thị `.dot` | Trực quan hóa |
| `jdeps --generate-module-info generated library.jar` | Sinh gợi ý `module-info.java` | Lập kế hoạch modularize |

Một số tùy chọn **không kết hợp được** theo hướng dẫn công cụ. Ví dụ `--generate-module-info` không dùng cùng `--class-path` hoặc `--dot-output`. Chạy `jdeps --help` để kiểm tra trước khi ghép nhiều cờ.

`--ignore-missing-deps` chỉ cho phép bỏ qua những dependency chưa tìm thấy trong một số kiểu phân tích. **Nó không thêm dependency còn thiếu và không chứng minh application đã đóng gói đúng.**

## 5. Ví dụ có thể tái tạo: hai named modules hợp lệ

Xây hai module:

- `com.example.greetings` cung cấp lớp `Greeter`.
- `com.example.app` dùng `Greeter` từ package đã export.

Cấu trúc:

```text
example/
└── src/
    ├── com.example.greetings/
    │   ├── module-info.java
    │   └── com/example/greetings/api/Greeter.java
    └── com.example.app/
        ├── module-info.java
        └── com/example/app/Main.java
```

Tệp `src/com.example.greetings/module-info.java`:

```java
module com.example.greetings {
    exports com.example.greetings.api;
}
```

Tệp `src/com.example.greetings/com/example/greetings/api/Greeter.java`:

```java
package com.example.greetings.api;

public final class Greeter {
    private Greeter() {}

    public static String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
```

Tệp `src/com.example.app/module-info.java`:

```java
module com.example.app {
    requires com.example.greetings;
}
```

Tệp `src/com.example.app/com/example/app/Main.java`:

```java
package com.example.app;

import com.example.greetings.api.Greeter;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.greet("Java 27"));
    }
}
```

### 5.1. Biên dịch và đóng gói bằng lệnh JDK 27

Từ thư mục `example`, các lệnh **PowerShell**:

```powershell
javac --module-source-path src -d out --module com.example.greetings,com.example.app

New-Item -ItemType Directory -Force dist | Out-Null

jar --create --file dist/com.example.greetings.jar -C out/com.example.greetings .
jar --create --file dist/com.example.app.jar -C out/com.example.app .

java --module-path dist --module com.example.app/com.example.app.Main
```

Kết quả:

```text
Xin chào, Java 27!
```

`--module-source-path src` cho `javac` biết thư mục gốc chứa mã nguồn module. `-d out` tạo output được phân theo module. Lệnh `jar` đưa `module-info.class` vào từng JAR để tạo **modular JAR**. Lệnh `java --module-path dist` phân giải dependency của `com.example.app` từ hai artifact.

Có thể chạy ứng dụng dưới dạng **exploded modules** từ thư mục `out` thay vì đóng JAR, nhưng cách dùng JAR ở đây gần với quy trình phát hành thư viện hơn.

### 5.2. Kiểm tra descriptor của từng JAR

```powershell
jar --describe-module --file dist/com.example.greetings.jar
jar --describe-module --file dist/com.example.app.jar
```

Ý nghĩa mong đợi:

- `com.example.greetings` export `com.example.greetings.api`.
- `com.example.app` requires `com.example.greetings`.
- `java.base` được đọc ngầm định.

Không nên suy ra module name chỉ từ tên file JAR. Với automatic module, tên có thể do `Automatic-Module-Name` trong manifest cung cấp hoặc do công cụ suy từ tên file.

## 6. Phân tích hai module bằng jdeps

Các lệnh sau dùng chính hai JAR đã đóng gói trong `dist`:

```powershell
jdeps --module-path dist --module com.example.app
jdeps --module-path dist --module com.example.app --list-deps
jdeps --module-path dist --module com.example.app --print-module-deps
jdeps --module-path dist --check com.example.app
```

Mỗi lệnh trả lời một câu hỏi khác nhau:

1. `--module-path` giúp công cụ tìm module và các dependency.
2. `--module com.example.app` chọn module cần phân tích.
3. `--list-deps` hiển thị danh sách module dependencies được phân tích.
4. `--print-module-deps` xuất danh sách module gọn, ngăn bằng dấu phẩy; không phải danh sách các package trùng.
5. `--check` phân tích descriptor, đồ thị dependencies sau khi giảm bớt cạnh suy ra và có thể nêu **unused qualified exports**.

Muốn thấy cạnh tham chiếu cụ thể, chuyển sang:

```powershell
jdeps --module-path dist --verbose:package --module com.example.app
jdeps --module-path dist --verbose:class --module com.example.app
```

Quan hệ trọng tâm cần tìm là class `com.example.app.Main` sử dụng `com.example.greetings.api.Greeter`. Định dạng đầu ra thực tế phụ thuộc cờ jdeps; không nên coi một đoạn kết quả rút gọn viết trong tài liệu là output cố định của mọi môi trường.

### 6.1. API dependency khác implementation dependency

```powershell
jdeps --api-only --verbose:package dist/com.example.greetings.jar
```

`--api-only` tập trung vào dependency xuất hiện trong chữ ký API công khai hoặc protected phù hợp (tham số, kiểu trả về, trường, checked exception), thay vì toàn bộ implementation.

Đây là góc nhìn hữu ích khi quyết định `requires transitive`: nếu API công khai của thư viện A dùng kiểu từ module B, module đọc A cũng có thể cần đọc B. **Không biến mọi requires thành requires transitive**; chỉ dùng khi đúng trách nhiệm API và mô hình module graph.

## 7. Phân tích JAR chưa modular và phụ thuộc thiếu

Một JAR thông thường có thể được kiểm tra cùng các dependency đã biết:

```powershell
jdeps --class-path "lib/support.jar" "dist/legacy-library.jar"
jdeps --class-path "lib/support.jar" --verbose:class "dist/legacy-library.jar"
jdeps --class-path "lib/support.jar" --missing-deps "dist/legacy-library.jar"
```

Các tên file này **chỉ minh họa cho một thư viện khác**, không phải file được tạo trong bài thực hành ở mục 5. Thay bằng đúng các artifact của dự án.

Nếu `jdeps` báo `not found` hoặc missing dependency, trước tiên kiểm tra:

- Input phân tích đã bao gồm đúng các JAR cần thiết chưa?
- Đã khai báo đường dẫn ở `--class-path` hay `--module-path` đúng vị trí chưa?
- Có nhiều phiên bản cùng tên hoặc artifact không tương thích không?
- Dependency có được nạp ở runtime theo cách mà jdeps không quan sát được không?

Cần phân biệt **thiếu khi phân tích** với **thiếu khi triển khai thực tế**. Cả hai đều đáng kiểm tra, nhưng không có nghĩa giống nhau.

### 7.1. Tìm JDK internal API

```powershell
jdeps --jdk-internals dist/legacy-library.jar
```

Công cụ có thể chỉ ra class phụ thuộc API nội bộ JDK. Thiết kế thư viện mới nên ưu tiên **API Java SE được hỗ trợ công khai**, thay vì dựa trên những kiểu nội bộ có khả năng thay đổi hoặc bị hạn chế truy cập.

Nếu phát hiện:

1. Xác định class của thư viện gây ra dependency.
2. Tìm API Java SE công khai thay thế.
3. Sửa mã nguồn hoặc nâng phiên bản dependency.
4. Kiểm thử và chạy lại jdeps.

`--add-exports` hoặc `--add-opens` có thể phục vụ một số tình huống tương thích có chủ đích, nhưng không nên được xem như cách sửa chuẩn cho thư viện mới phụ thuộc JDK internals.

### 7.2. Multi-release JAR

Multi-release JAR có thể mang class phiên bản khác nhau trong `META-INF/versions/<version>`. Một phân tích chỉ nhìn phần gốc có thể bỏ sót dependency của lớp mà JDK 27 sẽ chọn:

```powershell
jdeps --multi-release base dist/example-mr.jar
jdeps --multi-release 27 dist/example-mr.jar
```

Hai lệnh là ví dụ cho **JAR multi-release đã tồn tại** tên `example-mr.jar`, không phải JAR được tạo ở mục 5. Khi phân phối thư viện cho nhiều phiên bản Java, phân tích theo đúng các runtime được hỗ trợ; không nên lấy kết quả Java 27 làm bảo đảm rằng thư viện chạy đúng trên JDK thấp hơn.

## 8. Split package: tên package bị chia giữa nhiều JAR/module

**Split package** xảy ra khi hai hoặc nhiều artifact chứa class thuộc **chính cùng một package Java**.

Ví dụ:

```text
alpha.jar
└── com/acme/shared/Alpha.class

beta.jar
└── com/acme/shared/Beta.class
```

Giả sử hai class có cùng khai báo:

```java
package com.acme.shared;
```

Dù class tên `Alpha` và `Beta` **khác nhau**, hai JAR vẫn cùng đóng góp vào package `com.acme.shared`. Không cần trùng tên class mới là split package.

Ngược lại:

```text
com/acme/shared/Alpha.class
com/acme/shared/internal/Beta.class
```

không thuộc cùng package: `com.acme.shared` và `com.acme.shared.internal` là hai package riêng. Java không cho rằng một package là thành viên của package cha chỉ vì có tiền tố giống nhau.

### 8.1. Hai dạng xung đột đáng phân biệt

**Xung đột khi module resolution:** JPMS không chấp nhận cấu hình mà một module **đọc hai module export cùng package** cho nó. Một module vừa chứa package `p`, vừa đọc module khác export `p` cho nó cũng có thể vi phạm quy tắc resolution.

**Xung đột khi tạo module layer:** dù không xảy ra điều kiện export nêu trên, việc **nhiều module có package chồng nhau được ánh xạ vào cùng class loader** vẫn có thể làm việc tạo layer thất bại.

Vì thế lỗi có thể được báo tại những giai đoạn khác nhau:

- `javac` báo package được đọc từ nhiều module.
- Module resolution báo `java.lang.module.ResolutionException`.
- Module layer báo `java.lang.LayerInstantiationException`, có thể kèm tên package và hai module.

Không nên viết quy tắc cực đoan “mọi split package ở mọi hoàn cảnh đều gây đúng một exception”. Quan hệ readable, exported package, loader, module nào thực sự được resolve và cách chạy khác nhau đều quan trọng.

### 8.2. Minh họa module graph không hợp lệ

Giả sử có hai modular JAR độc lập:

```text
com.acme.alpha.jar
    module com.acme.alpha
    exports com.acme.shared
    contains com.acme.shared.Alpha

com.acme.beta.jar
    module com.acme.beta
    exports com.acme.shared
    contains com.acme.shared.Beta
```

Module ứng dụng khai báo:

```java
module com.acme.app {
    requires com.acme.alpha;
    requires com.acme.beta;
}
```

Sơ đồ:

```text
                         ┌─ com.acme.alpha ─ exports com.acme.shared
com.acme.app ─ requires ─┤
                         └─ com.acme.beta  ─ exports com.acme.shared
                                                    ↑
                                  cùng tên package với alpha
```

Ứng dụng cần đọc hai module đều export `com.acme.shared`, nên đồ thị không hợp lệ. **Đổi tên class `Alpha` thành `FirstAlpha` không sửa được vấn đề**, vì package vẫn bị chia giữa hai module.

Đây là minh họa về cấu hình sai; không phải hướng dẫn để lắp hai module đó thành ứng dụng chạy được.

## 9. Vì sao jdeps một mình không kiểm soát hết split package?

`jdeps` trả lời chủ yếu câu hỏi **“class/module nào tham chiếu tới class/module nào?”**. Nhưng để phát hiện split package, cần hỏi **“artifact nào đang sở hữu package này?”**.

Hai câu hỏi khác nhau:

- Nếu một JAR chứa package `com.acme.shared` nhưng chưa có class nào của ứng dụng tham chiếu nó, `jdeps` có thể không hiển thị một cạnh từ ứng dụng tới package đó.
- Nếu module graph đã không thể resolve vì split package, `jdeps` có thể thất bại trước khi sinh báo cáo dependency chi tiết.
- `--print-module-deps` sinh danh sách module, không phải bảng package trùng.
- `--check` đánh giá module descriptor/graph, nhưng không thay thế việc rà soát **mọi artifact** trong dependency set.

Do đó, cần ba lớp kiểm chứng bổ sung cho nhau:

1. **Kiểm kê artifact/package:** xem chính xác những class nằm trong mỗi JAR.
2. **Phân tích dependency:** jdeps giúp giải thích vì sao module/library được dùng.
3. **Validation trên module path thật:** xác nhận module graph có thể được phân giải và khởi tạo.

## 10. Kiểm kê split package theo artifact

### 10.1. Xác định module name

Với hai JAR có dấu hiệu chồng package:

```powershell
jar --describe-module --file lib/alpha.jar
jar --describe-module --file lib/beta.jar
```

Đọc kỹ:

- Đây là **explicit modular JAR** hay JAR đang được xem như **automatic module**?
- Module name thực tế là gì?
- Package nào được export/opened?
- Module nào cần đọc các JAR này?

Tên module là thông tin từ descriptor hoặc cơ chế automatic module, **không đơn thuần là tên file JAR**.

### 10.2. Liệt kê các class để tìm package thật

```powershell
jar --list --file lib/alpha.jar
jar --list --file lib/beta.jar
```

Ví dụ các entry:

```text
com/acme/shared/Alpha.class
com/acme/shared/Beta.class
```

Đường dẫn package ở cả hai là `com/acme/shared`. Khi kiểm kê nhiều JAR, có thể xây dựng bảng:

| Package | Artifact chứa class | Cần xử lý? |
| --- | --- | --- |
| `com.acme.shared` | `alpha.jar`, `beta.jar` | Có, cùng một package ở hai nơi |
| `com.acme.alpha.api` | `alpha.jar` | Không có dấu hiệu split trong bảng này |
| `com.acme.beta.api` | `beta.jar` | Không có dấu hiệu split trong bảng này |

Quy trình quét tự động nên dựa trên **entry `.class`**, chuyển đường dẫn thư mục thành tên package. Có một số ngoại lệ phải xử lý đúng:

- `module-info.class` ở gốc JAR không phải một type thuộc package ứng dụng.
- Các thư mục `META-INF/versions/<n>` trong multi-release JAR cần được diễn giải theo package **sau phần tiền tố phiên bản**.
- Tài nguyên không phải class không mặc nhiên là một package Java.
- Class trong unnamed/default package cần được xem xét riêng; thư viện phân phối nên khai báo package có tên rõ ràng.
- Nếu tìm cùng tên class fully qualified ở hai JAR, đây còn là **duplicate class**, không chỉ split package.

Không nên xác định split package bằng cách so chuỗi tiền tố `com.acme`: như vậy sẽ báo nhầm cho nhiều package khác nhau có cùng miền tên.

### 10.3. Dùng Java launcher kiểm chứng module path

Khi đã có artifact dự kiến chạy:

```powershell
java --module-path lib --validate-modules
```

`--validate-modules` hỗ trợ phát hiện xung đột và lỗi trong các module quan sát được trên module path. Đây là bước kiểm tra hữu ích trong quy trình build/release.

Tiếp theo kiểm tra **root module thật** mà ứng dụng sẽ sử dụng:

```powershell
java --module-path lib --dry-run --module com.acme.app/com.acme.app.Main
```

`--dry-run` kiểm tra cấu hình khởi chạy mà không thực thi `main`. Lệnh chỉ mang tính minh họa: thay module và class bằng tên thật, đồng thời bảo đảm chúng có trong đường dẫn module.

Không dùng hai lệnh trên để khẳng định “mọi runtime configuration đều an toàn” nếu ứng dụng có **plugin/module layer do chương trình tự tạo**, class loader đặc biệt hoặc dependency runtime không hiện diện khi phân tích.

### 10.4. Quay lại jdeps để xác định nguyên nhân phụ thuộc

```powershell
jdeps --module-path lib --module com.acme.app --verbose:class
jdeps --module-path lib --check com.acme.app
```

Khi phân tích thành công, các cạnh phụ thuộc và module descriptor giúp tìm **vì sao các thư viện này nằm cùng một module graph**.

Nếu module không resolve được nên `jdeps` báo lỗi, hãy đọc **lỗi đầu tiên** và kết hợp kết quả kiểm kê JAR. Không thêm `--ignore-missing-deps` hay bỏ một JAR khỏi module path chỉ để làm cho lệnh jdeps “chạy xanh” nếu cấu hình đó khác môi trường phát hành thật.

## 11. Cách sửa split package có thể duy trì lâu dài

### 11.1. Tạo một chủ sở hữu cho mỗi package

Phương án ưu tiên là bảo đảm một package Java có **một module sở hữu rõ ràng** trong cấu hình ứng dụng:

Trước:

```text
com.acme.alpha  -> com.acme.shared.Alpha
com.acme.beta   -> com.acme.shared.Beta
```

Sau:

```text
com.acme.alpha  -> com.acme.alpha.api.Alpha
com.acme.beta   -> com.acme.beta.api.Beta
```

Hoặc đưa các kiểu **thật sự dùng chung** vào một module:

```text
com.acme.common   exports com.acme.common.api
com.acme.alpha    requires com.acme.common
com.acme.beta     requires com.acme.common
```

Khi đó chỉ `com.acme.common` chứa bytecode của package chung. Hai module sử dụng nó qua dependency chứ **không đóng gói lại bản sao class**.

Một lần đổi package cần cập nhật:

- Lệnh `package`, import và các định nghĩa `exports`/`opens`.
- Các API có chữ ký tham chiếu tên class/package cũ.
- Cấu hình reflection, service descriptor, serialization, manifest và tài nguyên.
- Mã người dùng thư viện, kiểm thử và phiên bản artifact.

Đổi package công khai là một **thay đổi tương thích** cần kế hoạch migration, không phải chỉ là thay đường dẫn tệp.

### 11.2. Loại artifact trùng do dependency hoặc “fat JAR”

Đôi khi một thư viện đã **nhúng sẵn bytecode của thư viện khác** nhưng dự án vẫn kéo cả JAR gốc:

```text
vendor-bundle.jar  -> com/vendor/api/Client.class
vendor-api.jar     -> com/vendor/api/Client.class
```

Cách xử lý:

1. Xác định bản nào phải là nguồn sở hữu class.
2. Kiểm tra dependency graph trong công cụ build để hiểu dependency nào kéo bản còn lại vào.
3. Loại bản sao hoặc chọn đúng biến thể artifact (bundle **hoặc** thư viện rời, tùy cách phân phối).
4. Đóng gói lại và quét JAR cuối cùng; không chỉ sửa dependency ở source.
5. Kiểm thử trên module path thật để chắc các class cần thiết vẫn tồn tại.

Loại trừ một dependency mà không xác minh nội dung JAR có thể làm mất class cần ở runtime. Vì vậy mục tiêu là **một nguồn bytecode đúng**, không phải cắt bỏ ngẫu nhiên.

### 11.3. Shading/relocation khi không kiểm soát được mã nguồn

Một số bộ công cụ đóng gói hỗ trợ đổi tên package trong JAR (relocation). Đây là phương án có điều kiện, cần đánh giá:

- Tên class trong reflection và configuration.
- File `META-INF/services/...`, service provider lookup và annotation metadata.
- Resource path, serialization, chữ ký JAR và license.
- Ảnh hưởng tới API công khai và các ứng dụng tiêu thụ thư viện.

Relocation phải được áp dụng có chủ đích vào **artifact kết quả**, có kiểm thử và kiểm kê lại. Không coi đó là phép biến đổi miễn phí.

### 11.4. Không lấy cờ runtime để thay thế thiết kế

`--patch-module` có thể được dùng trong các tình huống kiểm thử, debug hoặc tương thích đặc biệt để bổ sung/thay class trong module. Nhưng không nên dùng nó như giải pháp kiến trúc mặc định cho hai thư viện đang sở hữu cùng package.

`--add-exports` và `--add-opens` giải quyết **quyền truy cập**, không phải quyền sở hữu package. Chúng không thay thế công việc bỏ split package.

Chuyển toàn bộ JAR về classpath có thể tránh một số kiểm tra JPMS, nhưng **không xóa được duplicate classes hoặc shadowing**. Đây là lựa chọn mô hình triển khai, không phải sửa tận gốc.

## 12. Automatic module và tên module ổn định

Một JAR chưa có descriptor trên module path có thể được xử lý như **automatic module**. Đây là cơ chế chuyển đổi được hỗ trợ trong Java 27, không phải tính năng đã bị gỡ bỏ.

Nhưng cần hiểu những điểm sau:

- Tên module có thể lấy từ `Automatic-Module-Name` trong manifest hoặc được suy ra từ tên file JAR.
- Automatic module xuất các package của nó theo quy tắc JPMS.
- Automatic module có chính sách readability rộng hơn explicit module, nhằm giúp phối hợp dependency trong thời kỳ chuyển đổi.
- Hai automatic/named modules cùng mang một package có thể tạo xung đột khi được resolve/khởi tạo.

Vì vậy trước khi chuyển thư viện từ classpath sang module path, **kiểm kê tên module, package và dependencies của toàn bộ tập JAR**. Đừng để một automatic module bị đổi tên chỉ do cập nhật file JAR dẫn tới việc ứng dụng không thể khai báo `requires` đúng như trước.

Khi có quyền bảo trì thư viện, một explicit module descriptor được thiết kế cẩn thận giúp ranh giới API và dependency có thể kiểm chứng rõ hơn.

## 13. Rà soát module descriptor với jdeps --check

Lệnh:

```powershell
jdeps --module-path dist --check com.example.app
```

theo tài liệu JDK 27 sẽ in descriptor, các dependency sau phân tích, đồ thị sau khi giảm các cạnh đọc suy ra, và phát hiện **unused qualified exports**. Nó phù hợp để review module graph, nhưng không đảm bảo mọi vấn đề runtime hoặc split package ở JAR không tham gia phân tích đều được tìm thấy.

### 13.1. Phân biệt requires, requires transitive và requires static

```java
module com.acme.report {
    requires java.sql;
    requires transitive com.acme.api;
    requires static com.acme.compiletools;
}
```

- `requires M`: module hiện tại đọc `M`.
- `requires transitive M`: các module đọc module hiện tại cũng đọc `M` theo quan hệ readability được suy ra; phù hợp khi API của module hiện tại lộ kiểu thuộc `M`.
- `requires static M`: dependency được yêu cầu tại thời điểm biên dịch nhưng có thể vắng trong quá trình chạy theo hợp đồng module; không dùng tùy tiện để bỏ qua dependency thực sự bắt buộc.

`--list-reduced-deps` lược đi những cạnh đọc module có thể suy ra bởi `requires transitive`. **Không** diễn giải việc một cạnh bị lược bỏ trong báo cáo thành “module có thể được xóa khỏi runtime mà không ảnh hưởng gì”.

Các directive `opens`, `uses`, `provides` và dependency của reflection/service loading cũng cần được xem xét; không thể thay chúng bằng một danh sách static bytecode references.

## 14. Phân biệt các công cụ phát hiện vấn đề đóng gói

| Vấn đề | Công cụ/góc nhìn đúng | Điều không nên suy diễn |
| --- | --- | --- |
| Hai JAR cùng một package | `jar --list` cho **tất cả** artifact liên quan; so tên package | Chỉ nhìn danh sách module jdeps là đủ |
| Hai JAR chứa cùng tên class | So đường dẫn `.class` giữa các JAR | Hai class tên khác nhau thì không có split |
| Entry trùng **bên trong một JAR** | `jar --validate --file file.jar` | `jar --validate` tự tìm split giữa mọi JAR |
| Two modules export same package to a reader | Module resolution, compiler, `java --validate-modules` | Chỉ cần đổi tên một class là hết xung đột |
| Module layer có package chồng nhau trong cùng loader | Thực thi/layer validation, đọc `LayerInstantiationException` | Mọi lỗi layer giống lỗi compile-time |
| Missing class dependency | `jdeps --missing-deps` và kiểm tra paths | Tự động coi là lỗi runtime dù input thiếu |
| Dùng JDK internal API | `jdeps --jdk-internals` | Dùng `--add-exports` sẽ sửa kiến trúc vĩnh viễn |
| Dependency sinh động qua reflection/SPI | Cấu hình framework, module descriptor, integration tests | jdeps không thấy nghĩa là không tồn tại |
| Trùng module name | `jar --describe-module` và validate module path | Tên file đủ để biết tên module |

`jar --validate` là kiểm tra **tính toàn vẹn từng JAR**, gồm duplicate entry path và một số quy tắc đối với multi-release JAR. Nó không phải công cụ so sánh tên package giữa mọi JAR trong hệ thống.

## 15. Quy trình kiểm soát split package trong CI

Một pipeline build có thể kiểm tra theo thứ tự sau:

1. **Chốt tập artifact cuối cùng** để phân tích: những JAR thực sự được dùng trong deployment, không chỉ những JAR nằm trong source.
2. **Khóa JDK và phiên bản công cụ**: ghi `java --version` và `jdeps --version` để có khả năng tái lập kết quả.
3. **Đọc module name/descriptor**: `jar --describe-module`, phát hiện named/automatic module và trùng tên.
4. **Quét package ownership**: liệt kê class trong mỗi JAR, xử lý multi-release đúng, tổng hợp `package -> các artifacts`.
5. **Chặn overlap có rủi ro**: package cùng tên ở nhiều named/automatic modules dự kiến cùng chạy cần được giải quyết trước phát hành.
6. **Chạy phân tích jdeps**: `--list-deps`, `--verbose:class` khi cần, `--missing-deps`, `--jdk-internals`.
7. **Xác thực module graph**: `java --validate-modules` và `--dry-run --module` với root module thật.
8. **Chạy integration tests**: đặc biệt những đường đi dùng reflection, service loading, serialization và framework plugin.
9. **So sánh kết quả sau mỗi thay đổi dependency**: một phiên bản JAR mới có thể thêm package, thay module name hoặc thay API dependency.
10. **Ghi nhận quyết định kiến trúc**: nếu chấp nhận ngoại lệ classpath/relocation, cần lý do, phạm vi và kế hoạch kiểm soát.

Gợi ý mức xử lý:

- **Fail build** khi các module sẽ dùng cùng nhau không thể resolve/khởi chạy, có duplicate class nguy hiểm hoặc split package được xác nhận ở ranh giới named modules.
- **Yêu cầu review** khi phát sinh JDK internal dependency, automatic module mới, hoặc thay đổi package/API của thư viện.
- **Thông tin** khi dependency module hợp lệ thay đổi mà không gây xung đột; đánh giá impact nếu cần.

Không nên chặn build chỉ vì hai package chia sẻ tiền tố `com.acme`; phải so sánh tên **package chính xác**.

## 16. Checklist khắc phục lỗi “Package ... in both module ...”

Khi gặp lỗi có nội dung tương tự:

```text
Package com.acme.shared in both module com.acme.alpha
and module com.acme.beta
```

hãy thực hiện tuần tự:

1. **Ghi nhận lỗi đầy đủ**: lệnh `java`/`javac`, module path, root module, tên package và hai module được nêu.
2. **Tìm artifact thật**: xác nhận JAR nào định nghĩa hai module bằng `jar --describe-module`.
3. **Kiểm tra class trong package**: dùng `jar --list` ở cả hai JAR; tránh nhầm “trùng class” với “trùng package”.
4. **Đọc dependency graph**: tìm vì sao cả hai artifact được kéo vào ứng dụng, kể cả từ dependency transitively.
5. **Sửa đúng chủ sở hữu**: bỏ bản sao, tách package theo module, trích module chung hoặc relocation có kiểm thử.
6. **Build lại artifact cuối**: bảo đảm module descriptor, service/resource metadata và API của consumer đã cập nhật.
7. **Kiểm chứng**: quét package lại, `java --validate-modules`, jdeps, rồi thực hiện integration tests.
8. **Ngăn tái diễn**: bổ sung bước kiểm kê package ownership ở CI và thống nhất chính sách packaging.

Quan trọng nhất là **xác định package thuộc về module nào**. Một lần chạy không còn báo lỗi sau khi tùy chỉnh module/classpath tạm thời chưa chứng minh kiến trúc đã được sửa.

## 17. Checklist khi thiết kế một thư viện Java 27

Trước khi phát hành hoặc thêm JAR lên module path, nên hỏi:

- JAR có `module-info.class` không; tên module thực tế là gì?
- Những package nào được JAR định nghĩa, và có artifact khác định nghĩa **đúng cùng tên package** không?
- Module nào cần `requires`; trường hợp nào đúng nghĩa cần `requires transitive`?
- API có để lộ kiểu từ dependency không; kết quả `jdeps --api-only` cho thấy gì?
- Có `opens`/`uses`/`provides` hay runtime reflection mà jdeps tĩnh không thể thấy đầy đủ không?
- Có missing dependencies hoặc JDK internal API không?
- Artifact có là multi-release JAR không, và kết quả trên runtime cần hỗ trợ có khác nhau không?
- `java --validate-modules` và ứng dụng với root module thật có khởi chạy được không?
- Đổi package có phá vỡ khả năng tương thích của consumer/serialization/service metadata không?
- CI đã có kiểm tra split package giữa **artifacts cuối**, không chỉ kiểm tra một JAR riêng lẻ, chưa?

**Ghi nhớ:** `jdeps` cho biết **mã đã biên dịch phụ thuộc vào đâu**; kiểm kê JAR cho biết **package do artifact nào sở hữu**; validation JPMS cho biết **module graph có phù hợp để sử dụng không**. Cần phối hợp cả ba góc nhìn khi đóng gói thư viện hiện đại.

## 18. Nguồn tham khảo chính thức Java SE 27

- [The `jdeps` Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jdeps.html): các chế độ phân tích và giới hạn của `--check`, `--list-deps`, `--print-module-deps`, `--jdk-internals`, `--missing-deps`, `--generate-module-info`.
- [The `java` Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): `--module-path`, `--module`, `--validate-modules`, `--dry-run`.
- [The `javac` Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html): `--module-source-path`, `--module` và biên dịch đa module.
- [The `jar` Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jar.html): modular JAR, `--describe-module`, `--list`, `--validate` và multi-release JAR.
- [Java Language Specification 27 — Chapter 7: Packages and Modules](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-7.html): quy tắc `requires`/`exports`, package và module.
- [`java.lang.module` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/module/package-summary.html): resolution/readability và các điều kiện hợp lệ của module graph.
- [`java.lang.module.Configuration` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/module/Configuration.html): lý do resolution thất bại, bao gồm xung đột exported package.
- [`java.lang.ModuleLayer` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ModuleLayer.html): các vấn đề khi module có package chồng nhau được nạp bằng cùng class loader.
