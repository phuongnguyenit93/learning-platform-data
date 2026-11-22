# Phân biệt mô tả mô-đun với metadata của công cụ xây dựng

Trong Java Platform Module System (JPMS), **mô tả mô-đun** và **metadata của công cụ xây dựng** cùng tham gia tạo ra một ứng dụng, nhưng chúng trả lời hai nhóm câu hỏi khác nhau.

- Mô tả mô-đun xác định danh tính và ranh giới truy cập của mô-đun khi Java biên dịch và chạy: mô-đun tên gì, đọc mô-đun nào, xuất package nào, mở package nào cho reflection và tham gia Service Provider Interface ra sao.
- Metadata của công cụ xây dựng mô tả cách dự án được biên dịch, kiểm thử, đóng gói và phân phối: artifact có tọa độ nào, dùng JDK nào, lấy dependency từ đâu, source set nằm ở đâu, plugin và task nào được chạy.

Hiểu đúng hai lớp này giúp tránh nhầm tên project với tên mô-đun, nhầm dependency của Gradle/Maven với quan hệ `requires`, hoặc kỳ vọng một cấu hình build tự tạo ra ranh giới JPMS.

## 1. Ba thứ cần phân biệt

Trong một dự án Java có mô-đun tường minh, thường gặp ba thành phần:

1. **`module-info.java`** là module descriptor ở dạng mã nguồn. Nó khai báo tên mô-đun và các chỉ thị JPMS.
2. **`build.gradle`, `build.gradle.kts`, `pom.xml`, `settings.gradle`** là metadata/cấu hình của công cụ xây dựng. Chúng mô tả project, dependency artifact, toolchain, plugin, source set, task và cách tạo đầu ra.
3. **`module-info.class`** là descriptor đã được compiler tạo từ `module-info.java`. Nó được đặt ở gốc của mô-đun đã biên dịch và được đóng gói trong modular JAR.

Ví dụ cấu trúc dự án:

~~~text
billing-service/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            ├── module-info.java
            └── com/
                └── example/
                    └── billing/
                        └── api/
                            └── Invoice.java
~~~

Công cụ xây dựng đọc cấu hình của nó để biết cách biên dịch source set và xử lý dependency. Compiler đọc `module-info.java` để tạo descriptor. Khi JAR được đưa lên module path, Java dùng descriptor đã biên dịch để phân giải mô-đun và áp dụng quy tắc truy cập.

## 2. Module descriptor mô tả điều gì?

Một module descriptor được viết trong `module-info.java`:

~~~java
module com.example.billing {
    requires java.logging;
    exports com.example.billing.api;
    opens com.example.billing.model to com.example.json;
}
~~~

Các khai báo trên thuộc về JPMS:

- `module com.example.billing` đặt tên mô-đun là `com.example.billing`.
- `requires java.logging` khai báo mô-đun hiện tại đọc mô-đun `java.logging`.
- `exports com.example.billing.api` cho phép mã trong mô-đun khác đọc mô-đun này truy cập các kiểu `public` thuộc package API.
- `opens com.example.billing.model to com.example.json` mở package cho truy cập sâu bằng reflection từ mô-đun được nêu tên.

Module descriptor còn có thể khai báo `requires transitive`, `requires static`, `exports ... to`, `opens`, `uses` và `provides ... with`. Đây là các quy tắc về khả năng đọc mô-đun, khả năng truy cập package và cơ chế service của Java.

Descriptor **không phải** nơi khai báo:

- Maven coordinates như `groupId`, `artifactId`, `version`.
- Tên project Gradle, cấu trúc multi-project hoặc repository tải dependency.
- JDK/toolchain dùng để chạy compiler, test hoặc build.
- Phiên bản plugin, task, test framework hay cấu hình đóng gói.
- Thư mục source/resource tùy chỉnh hoặc quy tắc publish artifact.

Các thông tin đó thuộc cấu hình build. Module descriptor có thể tham chiếu tên mô-đun dependency, nhưng không chứa tọa độ Maven hay đường dẫn để tải JAR đó.

## 3. Metadata của công cụ xây dựng mô tả điều gì?

Với Gradle Groovy DSL, một phần `build.gradle` có thể trông như sau:

~~~groovy
plugins {
    id 'java-library'
}

group = 'com.example'
version = '2.4.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
    modularity.inferModulePath = true
}

tasks.named('jar') {
    archiveBaseName = 'billing-service'
}
~~~

Đây là cấu hình build:

- `plugins` chọn plugin cung cấp các task và quy ước build Java.
- `group` và `version` xác định một phần tọa độ artifact.
- `toolchain` chọn JDK cho các task Java được cấu hình dùng toolchain.
- `modularity.inferModulePath` cho phép Gradle nhận diện cấu trúc dự án mô-đun để bố trí dependency phù hợp trên module path khi biên dịch/chạy task Java.
- `archiveBaseName` đặt tên cơ sở của JAR do task `jar` tạo ra.

Một project client có thể khai báo dependency build như sau:

~~~groovy
dependencies {
    implementation project(':billing-service')
}
~~~

Khai báo này nói với Gradle rằng project hiện tại cần đầu ra của project `:billing-service` trong cấu hình dependency `implementation`. Nó giúp Gradle xây dựng đồ thị task và đưa artifact cần thiết vào classpath/module path tương ứng.

Nếu mã nguồn client cũng là một named module, descriptor của client vẫn cần khai báo quan hệ JPMS tương ứng, ví dụ:

~~~java
module com.example.client {
    requires com.example.billing;
}
~~~

Tên project Gradle `:billing-service` và tên mô-đun JPMS `com.example.billing` là hai định danh riêng. Gradle project dependency không tự tạo câu lệnh `requires`; ngược lại, câu lệnh `requires` không tự cho Gradle biết artifact được tải hoặc build từ project nào.

Với Maven, vai trò tương tự được thể hiện qua `pom.xml`. Ví dụ tọa độ artifact:

~~~xml
<groupId>com.example</groupId>
<artifactId>billing-service</artifactId>
<version>2.4.0</version>
~~~

Các phần tử này định danh artifact trong hệ thống dependency/repository của Maven. Chúng không đặt tên JPMS module. Tên JPMS vẫn đến từ `module-info.java` hoặc cơ chế automatic module khi JAR chưa có descriptor tường minh.

## 4. So sánh trực tiếp

| Nội dung | Module descriptor | Build metadata |
|---|---|---|
| Định danh | Tên JPMS, ví dụ `com.example.billing` | Project name và tọa độ artifact, ví dụ `com.example:billing-service:2.4.0` |
| Phụ thuộc | `requires`, `requires transitive`, `requires static` | Dependency configuration, project dependency, version và repository |
| API công khai | `exports` package | Quy tắc publish và dependency exposure của công cụ build |
| Reflection | `opens` package | Có thể cấu hình plugin/task hỗ trợ framework, nhưng không tự mở package JPMS |
| Service | `uses` và `provides ... with` | Dependency và task để đóng gói provider artifact |
| Compiler | Mô tả module mà compiler phải kiểm tra | JDK/toolchain, release, compiler arguments và source set |
| Đóng gói | Descriptor được biên dịch thành `module-info.class` | Tên JAR, manifest, task đóng gói, publish và repository |
| Thời điểm sử dụng | Compiler và module system lúc phân giải/chạy | Build tool trong quá trình cấu hình, biên dịch, kiểm thử, đóng gói, phân phối |

Một quy tắc hữu ích: **JPMS quyết định mô-đun có thể đọc và truy cập gì; công cụ xây dựng quyết định lấy các đầu vào ở đâu và tạo artifact như thế nào.**

## 5. Ví dụ hoàn chỉnh: tên JAR khác tên JPMS module

Ví dụ này tạo một mô-đun thư viện và một mô-đun client. Tên mô-đun trong descriptor là `com.example.billing`, trong khi tên artifact có phần tên và phiên bản riêng.

Cấu trúc source:

~~~text
src/
├── com.example.billing/
│   ├── module-info.java
│   └── com/example/billing/api/Invoice.java
└── com.example.client/
    ├── module-info.java
    └── com/example/client/Main.java
~~~

**Descriptor của thư viện `src/com.example.billing/module-info.java`:**

~~~java
module com.example.billing {
    exports com.example.billing.api;
}
~~~

**API của thư viện `Invoice.java`:**

~~~java
package com.example.billing.api;

public final class Invoice {
    private Invoice() {
    }

    public static String status() {
        return "ready";
    }
}
~~~

**Descriptor của client `src/com.example.client/module-info.java`:**

~~~java
module com.example.client {
    requires com.example.billing;
}
~~~

**Điểm chạy của client `Main.java`:**

~~~java
package com.example.client;

import com.example.billing.api.Invoice;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Invoice.status());
    }
}
~~~

Có thể biên dịch và đóng gói bằng JDK 17 trở lên. Các lệnh sau dùng PowerShell và giả định đang đứng tại thư mục gốc dự án:

~~~powershell
New-Item -ItemType Directory -Force mods, build | Out-Null

javac --module-source-path src -d mods -m com.example.billing,com.example.client

jar --create --file build/billing-service-2.4.0.jar -C mods/com.example.billing .
jar --create --file build/client-app-1.0.jar -C mods/com.example.client .

jar --describe-module --file build/billing-service-2.4.0.jar

java --module-path build -m com.example.client/com.example.client.Main
~~~

Lệnh `javac` biên dịch hai named module theo source path và ghi đầu ra vào `mods`. Hai lệnh `jar` tạo artifact với tên file có thể do build metadata quy định. Tên file `billing-service-2.4.0.jar` không làm thay đổi tên JPMS trong descriptor.

Lệnh `jar --describe-module` kiểm tra descriptor đã được đóng gói. Với thư viện ở ví dụ này, các dòng quan trọng có dạng:

~~~text
com.example.billing
exports com.example.billing.api
requires java.base mandated
~~~

Dòng `com.example.billing` xác nhận tên mô-đun lấy từ descriptor. Tên artifact vẫn là `billing-service-2.4.0.jar`.

Lệnh chạy client có stdout chính xác:

~~~text
ready
~~~

Ví dụ chứng minh ba việc độc lập nhưng phối hợp với nhau:

1. `module-info.java` đặt tên mô-đun và xuất package API.
2. `module-info.java` của client khai báo `requires com.example.billing`.
3. Tên artifact và cách đặt JAR trong thư mục `build` do lệnh đóng gói hoặc build metadata quyết định.

## 6. Quan hệ giữa dependency của build và requires của JPMS

Đây là điểm dễ nhầm nhất khi làm dự án modular.

Giả sử client cần dùng thư viện billing. Trong build metadata, Gradle phải có dependency để tìm hoặc build artifact:

~~~groovy
dependencies {
    implementation project(':billing-service')
}
~~~

Trong module descriptor, client phải khai báo khả năng đọc mô-đun:

~~~java
module com.example.client {
    requires com.example.billing;
}
~~~

Hai khai báo có liên quan nhưng không thay thế nhau:

- Chỉ có dependency Gradle/Maven thì công cụ build có thể tìm được JAR, nhưng module descriptor của client vẫn có thể thiếu quan hệ `requires`.
- Chỉ có `requires` thì compiler biết client cần đọc mô-đun nào, nhưng build vẫn phải cung cấp artifact chứa mô-đun đó trên môi trường biên dịch và runtime.
- Tên project, tọa độ artifact và tên JPMS module phải được đối chiếu đúng. Không suy ra tên module từ tên project hoặc artifact nếu chưa kiểm tra descriptor.
- Nếu dependency là modular JAR, tên module mà `requires` tham chiếu phải khớp tên module trong descriptor của JAR.

Cũng cần phân biệt `exports` với dependency configuration của Gradle. `exports` công khai package theo quy tắc JPMS. Cấu hình `api` trong Gradle Java Library điều khiển dependency được phơi ra trên compile classpath của consumer theo mô hình Gradle. Hai cơ chế không có quan hệ thay thế một-một.

Tương tự, `requires transitive` điều khiển khả năng đọc mô-đun được truyền tiếp trong JPMS; nó không đơn giản là tên khác của `api` hoặc `implementation`. Khi thiết kế thư viện modular, cần xem cả module descriptor lẫn dependency metadata của build.

## 7. Tên module khi JAR chưa có module-info.class

Một JAR chưa có `module-info.class` vẫn có thể được dùng trên module path dưới dạng automatic module. Manifest có thể khai báo thuộc tính `Automatic-Module-Name` để đặt tên ổn định cho automatic module thay vì phụ thuộc vào cách suy ra tên từ tên file.

Ví dụ manifest:

~~~text
Automatic-Module-Name: com.example.legacy.billing
~~~

Đây là cơ chế hỗ trợ chuyển đổi thư viện sang JPMS. Nó chỉ cung cấp tên cho automatic module; không khai báo đầy đủ `requires`, `exports`, `opens`, `uses` và `provides` như một module descriptor tường minh. Khi thư viện đã sẵn sàng modular hóa đầy đủ, `module-info.java` là nơi mô tả ranh giới mô-đun.

Không dùng `Automatic-Module-Name` để kết luận rằng JAR đã có descriptor tường minh. Có thể kiểm tra artifact bằng:

~~~powershell
jar --describe-module --file path/to/library.jar
jar --list --file path/to/library.jar
~~~

## 8. Cách kiểm tra khi có lỗi

| Triệu chứng | Kiểm tra ở đâu | Hướng xử lý |
|---|---|---|
| Compiler báo module không đọc được | `module-info.java` và dependency/module path | Kiểm tra tên trong `requires`, descriptor của dependency và việc build đã cung cấp artifact |
| Gradle/Maven không tìm thấy dependency | `build.gradle` hoặc `pom.xml` | Kiểm tra tọa độ, version, repository và project path |
| Tên module khác tên JAR | Descriptor và artifact name | Dùng `jar --describe-module` để xác nhận tên module; kiểm tra build metadata cho tên file |
| Client import được artifact trên classpath nhưng lỗi khi chạy module path | Descriptor và cách cấu hình compile/runtime path | Kiểm tra module descriptor, package exports và dependency có mặt trên module path |
| Package public nhưng client vẫn không truy cập được | `exports` trong descriptor của thư viện | Xuất đúng package; từ khóa `public` của class không tự xuất package qua ranh giới JPMS |
| Framework reflection bị chặn | `opens` trong descriptor | Chỉ mở package cần thiết cho đúng mô-đun framework |
| Đổi artifactId nhưng `requires` không đổi | Build metadata và descriptor | Xác nhận tên JPMS độc lập với Maven artifactId; cập nhật từng lớp khi có chủ đích |
| Build chạy với JDK khác mong muốn | Toolchain và compiler task | Cấu hình toolchain/release phù hợp; descriptor vẫn phải tuân theo cú pháp và phiên bản Java mục tiêu |

Khi điều tra, hãy kiểm tra theo thứ tự: artifact có được build và resolve đúng không; JAR có chứa `module-info.class` không; tên module bên trong JAR là gì; descriptor của client có `requires` đúng không; package API đã được `exports` chưa. Trình tự này tách được lỗi phân phối artifact khỏi lỗi phân giải và truy cập của JPMS.

## 9. Checklist thiết kế và bảo trì

- Đặt tên JPMS rõ ràng trong `module-info.java`; không lấy tên file JAR làm nguồn suy luận.
- Khai báo `requires`, `exports`, `opens`, `uses`, `provides` theo nhu cầu thực tế của mô-đun.
- Dùng Gradle/Maven metadata cho tọa độ artifact, dependency resolution, toolchain, plugin, source set, test, đóng gói và publish.
- Bảo đảm dependency của build cung cấp đúng artifact mà module descriptor tham chiếu.
- Không coi Gradle `api`/`implementation` là thay thế trực tiếp cho JPMS `exports`/`requires`.
- Kiểm tra descriptor trong artifact bằng `jar --describe-module`.
- Khi dùng automatic module, xác nhận tên từ manifest hoặc công cụ JDK và có kế hoạch chuyển sang descriptor tường minh nếu cần kiểm soát ranh giới JPMS đầy đủ.
- Khi thay đổi tên project, artifact hoặc module, kiểm tra riêng từng lớp định danh và các consumer liên quan.

Mô tả mô-đun và metadata build là hai hợp đồng phối hợp: một hợp đồng với Java module system về khả năng đọc và truy cập; hợp đồng còn lại với công cụ xây dựng về cách tạo và phân phối artifact. Giữ chúng tách bạch nhưng nhất quán giúp modular JAR dễ biên dịch, chạy, kiểm tra và phát hành.
