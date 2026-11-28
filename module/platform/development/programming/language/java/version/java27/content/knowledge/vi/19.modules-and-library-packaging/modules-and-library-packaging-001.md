# Classpath, module path và cách phân giải phụ thuộc

> **Phạm vi:** Java 27, chương **Module và đóng gói thư viện**. Bài học trình bày classpath, module path, Java Platform Module System (JPMS), cách phân giải phụ thuộc, khả năng truy cập qua `requires`/`exports`/`opens`, cùng quy trình biên dịch và đóng gói JAR. JPMS là cơ chế chính thức từ Java 9 (JEP 261) và vẫn có hiệu lực trong Java 27. Ví dụ sử dụng tính năng chính thức, không cần preview.

## 1. Vì sao cần phân biệt classpath và module path?

Một ứng dụng Java thường phụ thuộc nhiều package và thư viện. Khi biên dịch, `javac` phải tìm được khai báo các class được tham chiếu; khi chạy, JVM phải tải được bytecode và các tài nguyên cần thiết.

Java hỗ trợ hai cách tổ chức đường tìm kiếm phụ thuộc:

- **Classpath** là danh sách các thư mục và JAR chứa class/resource theo cơ chế truyền thống. Code ứng dụng trên classpath thuộc một **unnamed module**.
- **Module path** là những vị trí chứa **named modules** mà JPMS có thể quan sát và chọn vào module graph. Các module có descriptor, quan hệ phụ thuộc và ranh giới package rõ ràng.

Classpath **vẫn được Java 27 hỗ trợ**; nó không bị khai tử chỉ vì JPMS đã ra đời. Một chương trình nhỏ, code tương thích với thư viện chưa modular hóa hoặc một ứng dụng có build tool quản lý classpath vẫn có thể sử dụng classpath. Khi cần encapsulation rõ, modular JAR và custom runtime image, module path đem lại cơ chế phù hợp hơn.

| Nội dung | Classpath | Module path |
| --- | --- | --- |
| Cấu trúc tìm kiếm | Các class/JAR theo package hierarchy | Các module có tên trong module hierarchy |
| Hợp đồng phụ thuộc | Do build/loader tổ chức | Có `module-info` và `requires` |
| Giới hạn package công khai | Chủ yếu theo access modifier Java | Còn có `exports`, `opens` và readability |
| Tên thực thể để tìm | Tên class, package | Tên module và class trong module |
| JAR chưa có descriptor | Được tải như classpath JAR | Có thể trở thành automatic module |
| Chế độ launch | `java -cp ... MainClass` | `java -p ... -m module/MainClass` |
| Thư viện tải từ repository | Không tự động tải | Cũng không tự động tải |

**Không đánh đồng** việc đặt một JAR vào đường dẫn với việc dependency của nó đã có hiệu lực trong module graph.

## 2. Phân biệt package, JAR và module

- **Package**: namespace chứa các class/interface, ví dụ `com.acme.greetings`.
- **JAR**: tệp archive có thể chứa class/resource; một JAR có thể nằm trên classpath hoặc module path.
- **Module**: nhóm package có tên và quy tắc phụ thuộc/truy cập, được mô tả qua `module-info.java` khi là explicit module.
- **Module descriptor**: khai báo tên module, phụ thuộc, package được export/open và thông tin service.
- **Module graph**: tập resolved modules cùng các quan hệ readability.
- **Module layer**: một vùng cấu hình module trong runtime; ứng dụng cơ bản thường sử dụng boot layer do launcher tạo.

Một modular JAR chứa `module-info.class` ở gốc archive. Một JAR chưa có descriptor khi đặt trên **module path** có thể được JPMS nhận diện như **automatic module**, còn trên **classpath** nó vẫn thuộc unnamed module.

### 2.1. Ba câu hỏi để được truy cập class

Đối với code trong module A muốn dùng class từ module B:

1. B có được **tìm thấy và resolve** trong configuration không?
2. A có **đọc (read)** module B không?
3. B có **export package** chứa class đó cho A, và bản thân class/member có quyền truy cập Java phù hợp không?

Nếu thiếu bất kỳ điều kiện cần thiết nào, chỉ viết `public class` hoặc thêm `import` là chưa đủ. Việc `opens` phục vụ reflection là một điều kiện khác, sẽ đề cập riêng.

## 3. Classpath trong Java 27

Tùy chọn tương đương:

- `--class-path`
- `-classpath`
- `-cp`

Ví dụ:

~~~text
sample/
├── classes/com/acme/app/Main.class
└── lib/common-utils.jar
~~~

Chạy trên Windows PowerShell:

~~~powershell
java --class-path "classes;lib/common-utils.jar" com.acme.app.Main
~~~

Chạy trên Linux/macOS:

~~~bash
java --class-path "classes:lib/common-utils.jar" com.acme.app.Main
~~~

| Hệ điều hành | Phân tách các entry classpath |
| --- | --- |
| Windows | Dấu chấm phẩy `;` |
| Linux/macOS | Dấu hai chấm `:` |

Dấu phân tách entry khác với `/` hoặc `\\` phân chia thư mục bên trong một path.

### 3.1. Compile classpath và runtime classpath

Giả sử `Main.java` gọi API từ `common-utils.jar`. Biên dịch:

~~~bash
javac --class-path lib/common-utils.jar -d classes src/com/acme/app/Main.java
~~~

Chạy (ví dụ Linux/macOS):

~~~bash
java --class-path "classes:lib/common-utils.jar" com.acme.app.Main
~~~

Compiler cần tìm khai báo của kiểu khi biên dịch; runtime cần tải class khi thực thi. Trong dự án thực tế, build tool có thể cấu hình các tập dependencies khác nhau cho compile, runtime và test.

### 3.2. Classpath không tự quét tất cả JAR trong thư mục

Đường dẫn `lib` **không tự động** có nghĩa toàn bộ file JAR nằm trong đó được thêm vào classpath.

Có thể dùng entry wildcard `"lib/*"`, được Java launcher mở rộng tới các JAR trong thư mục đó. Wildcard này không có nghĩa quét đệ quy và thứ tự các JAR không được bảo đảm. Không thiết kế chương trình dựa vào việc một trong hai JAR chứa cùng binary class sẽ luôn được tìm thấy trước.

Đối với `java -jar app.jar`, launcher dùng quy tắc tìm main class và dependency theo JAR manifest; không coi `--class-path` bên ngoài như chế độ chạy main class thông thường. Kiểm tra manifest hoặc cấu hình công cụ đóng gói nếu chương trình dùng `-jar`.

## 4. Module path và named modules

`--module-path` (viết gọn `-p`) chỉ nơi tìm các application modules đã biên dịch.

Ví dụ:

~~~text
mods/
├── com.acme.greetings/
│   ├── module-info.class
│   └── com/acme/greetings/Greetings.class
└── com.acme.app/
    ├── module-info.class
    └── com/acme/app/Main.class
~~~

Chạy:

~~~bash
java --module-path mods --module com.acme.app/com.acme.app.Main
~~~

Viết ngắn:

~~~bash
java -p mods -m com.acme.app/com.acme.app.Main
~~~

`com.acme.app` đứng trước dấu `/` là **tên module**; `com.acme.app.Main` là tên class chạy. Có module trên module path **không** đồng nghĩa nó chắc chắn được resolve: graph bắt đầu từ root module(s) và các quy tắc chọn module.

### 4.1. Các đường dẫn dễ nhầm

| Tùy chọn | Mục đích |
| --- | --- |
| `--class-path` | Tìm class/resource của code chạy theo classpath |
| `--module-path` | Tìm named/automatic modules đã có để compile/run |
| `--module-source-path` | Giúp `javac` tìm nguồn `.java` của module theo source hierarchy |
| `-d` (trong `javac`) | Chỉ định thư mục output class đã biên dịch |

Đừng đưa các file `.java` thẳng vào module path rồi mong JVM biên dịch cả ứng dụng. Cũng đừng dùng `--module-source-path` để trỏ tới JAR đã biên dịch.

## 5. Module descriptor: module-info.java

Thư viện có public API:

~~~java
module com.acme.greetings {
    exports com.acme.greetings;
}
~~~

Ứng dụng gọi thư viện:

~~~java
module com.acme.app {
    requires com.acme.greetings;
}
~~~

Các directive phổ biến:

| Directive | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `requires` | Module phụ thuộc trực tiếp vào một named module | `requires java.sql;` |
| `requires transitive` | Truyền khả năng đọc dependency tới module đọc module hiện tại | `requires transitive com.acme.api;` |
| `requires static` | Cần khi biên dịch, có thể vắng mặt lúc chạy | `requires static com.acme.annotations;` |
| `exports` | Cho phép code bên ngoài truy cập public/protected API của package | `exports com.acme.api;` |
| `exports ... to` | Giới hạn export cho các named module cụ thể | `exports com.acme.testing to com.acme.tests;` |
| `opens` | Cho phép reflective access vào package lúc chạy | `opens com.acme.model;` |
| `opens ... to` | Chỉ mở package cho các named module được liệt kê | `opens com.acme.model to com.example.mapper;` |
| `uses` | Module tiêu thụ một service | `uses com.acme.spi.Converter;` |
| `provides ... with` | Module cung cấp implementation cho service | `provides com.acme.spi.Converter with com.acme.impl.CsvConverter;` |

Mọi named module (trừ `java.base`) có dependency ngầm đến `java.base`. Không cần lặp `requires java.base;` trong các descriptor thông thường.

### 5.1. requires và exports là hai chiều khác nhau

~~~java
module com.acme.library {
    requires java.logging;
    exports com.acme.library.api;
}
~~~

- Library **đọc** `java.logging`, nhưng client dùng library không tự đọc `java.logging`.
- `com.acme.library.api` được export để code khác có thể sử dụng public API khi đã có readability.
- `com.acme.library.internal` không tự export, ngay cả khi chứa `public class`.

### 5.2. exports không giống opens

`exports` phục vụ truy cập thông thường khi biên dịch và thực thi. `opens` dùng chủ yếu cho reflection trong runtime (chẳng hạn framework cần truy cập private field/constructor).

- `opens com.acme.model;` **không** tự cho phép module khác `import com.acme.model.Customer;` khi compile.
- `exports com.acme.model;` **không** tự cho phép deep reflection tới private fields từ module khác.

Tốt nhất chỉ mở các package cần reflection bằng `opens ... to` nếu biết module của framework. Đừng khai báo `open module` cho toàn bộ thư viện chỉ để xử lý một lỗi reflection cục bộ.

## 6. Ví dụ hoàn chỉnh: hai module từ source tới ứng dụng

Ví dụ dùng hai explicit named modules. Các đường dẫn dưới đây là cấu trúc **minh họa để người học tự thực hành**; không phải file ngoài phạm vi bài đang được worker sửa.

### 6.1. Tổ chức source

~~~text
demo/
├── src/
│   ├── com.acme.greetings/
│   │   ├── module-info.java
│   │   └── com/acme/greetings/Greetings.java
│   └── com.acme.app/
│       ├── module-info.java
│       └── com/acme/app/Main.java
├── mods/                  # output khi compile
└── lib/                   # output JAR khi package
~~~

**File `src/com.acme.greetings/module-info.java`**

~~~java
module com.acme.greetings {
    exports com.acme.greetings;
}
~~~

**File `src/com.acme.greetings/com/acme/greetings/Greetings.java`**

~~~java
package com.acme.greetings;

import java.util.Objects;

public final class Greetings {
    private Greetings() {}

    public static String hello(String name) {
        return "Xin chào, " + Objects.requireNonNull(name, "name");
    }
}
~~~

**File `src/com.acme.app/module-info.java`**

~~~java
module com.acme.app {
    requires com.acme.greetings;
}
~~~

**File `src/com.acme.app/com/acme/app/Main.java`**

~~~java
package com.acme.app;

import com.acme.greetings.Greetings;

public final class Main {
    private Main() {}

    public static void main(String[] args) {
        System.out.println(Greetings.hello("Java 27"));
    }
}
~~~

### 6.2. Chuẩn bị thư mục output

Với PowerShell trên Windows:

~~~powershell
New-Item -ItemType Directory -Force -Path mods/com.acme.greetings,mods/com.acme.app,lib | Out-Null
~~~

Với Bash trên Linux/macOS:

~~~bash
mkdir -p mods/com.acme.greetings mods/com.acme.app lib
~~~

Chạy các lệnh kế tiếp từ thư mục `demo/`; đường dẫn nguồn cần khớp cây thư mục mô tả.

### 6.3. Biên dịch thư viện

~~~bash
javac -d mods/com.acme.greetings src/com.acme.greetings/module-info.java src/com.acme.greetings/com/acme/greetings/Greetings.java
~~~

Kết quả gồm `mods/com.acme.greetings/module-info.class` và class `Greetings`. Đây là **exploded module** trong thư mục, không cần đóng JAR mới có thể dùng qua module path.

### 6.4. Biên dịch ứng dụng với thư viện trên module path

~~~bash
javac --module-path mods -d mods/com.acme.app src/com.acme.app/module-info.java src/com.acme.app/com/acme/app/Main.java
~~~

Compiler tìm thấy module `com.acme.greetings` từ `mods` và kiểm tra `requires` trong descriptor của app. Nếu thiếu module path ở bước này, app không tìm được named module phụ thuộc theo ví dụ.

### 6.5. Chạy

~~~bash
java --module-path mods --module com.acme.app/com.acme.app.Main
~~~

Kết quả:

~~~text
Xin chào, Java 27
~~~

Diễn biến:

1. Launcher chọn `com.acme.app` làm **root module**.
2. Resolver đọc `requires com.acme.greetings;`.
3. JPMS tìm `com.acme.greetings` trong các nguồn module quan sát được.
4. Graph xác nhận app đọc greetings và greetings export package API.
5. JVM khởi động main class, lời gọi `Greetings.hello` hợp lệ.

### 6.6. Biên dịch nhiều module một lần

Khi source tree tuân theo module hierarchy như ở trên, có thể dùng:

~~~bash
javac --module-source-path src -d mods --module com.acme.greetings,com.acme.app
~~~

`--module-source-path` dành cho module-oriented source layout; output được phân chia theo module name. Trong dự án thực, chọn **một** chiến lược compile nhất quán để tránh class cũ còn lại từ cách build khác.

## 7. Đóng gói thành modular JAR

Modular JAR có `module-info.class` ở gốc archive. Sau khi hoàn tất bước compile:

~~~bash
jar --create --file lib/com.acme.greetings.jar -C mods/com.acme.greetings .
jar --create --file lib/com.acme.app.jar -C mods/com.acme.app .
~~~

Kiểm tra descriptor:

~~~bash
jar --describe-module --file lib/com.acme.greetings.jar
jar --describe-module --file lib/com.acme.app.jar
~~~

Chạy từ hai JAR:

~~~bash
java --module-path lib --module com.acme.app/com.acme.app.Main
~~~

Tên module trong `module-info.java` là nguồn xác định tên của **explicit module**, không phải tên file archive. Ví dụ file `greetings-2.0.jar` vẫn có thể chứa module `com.acme.greetings`.

Một modular JAR đặt trên `--class-path` vẫn có thể được sử dụng như một classpath JAR trong ứng dụng không dùng JPMS; khi đó descriptor không được dùng để áp các named-module boundary tương ứng. Điều này hữu ích cho thư viện muốn hỗ trợ cả hai cách triển khai.

## 8. Cách JPMS phân giải phụ thuộc

Module resolution xây một cấu hình các named modules, chứ không chỉ nạp toàn bộ JAR mà nó nhìn thấy.

~~~text
System modules + user module path
              │
              ▼
       Observable modules
              │
              ▼
       Root module(s)
              │
              ▼
     Theo các requires cần thiết
              │
              ▼
        Resolved modules
              │
              ▼
       Readability graph
              │
              ▼
  Kiểm tra conflicts/access rules
              │
              ▼
   Hợp lệ → compile hoặc launch
   Không hợp lệ → lỗi resolution
~~~

### 8.1. Observable không đồng nghĩa resolved

Một module có thể **observable** (tìm thấy trên module path hoặc system module path) nhưng không được đưa vào **resolved configuration** nếu nó không nằm trong tập root hoặc closure phụ thuộc được resolution chọn.

Đây là lý do có file JAR trên module path vẫn chưa đủ để `Class.forName` hoặc mã nguồn ở module bất kỳ có thể tự truy cập được nó.

### 8.2. Root modules

Với:

~~~bash
java --module-path lib --module com.acme.app/com.acme.app.Main
~~~

`com.acme.app` là root module, và các dependency bắt buộc của nó được đưa vào graph theo thuật toán resolution.

Với một chương trình ở classpath, có thể thêm một module trên module path vào tập root rõ ràng:

~~~bash
java --module-path lib --add-modules com.acme.greetings --class-path client/classes com.acme.client.Main
~~~

`--add-modules` không biến `client/classes` thành named module; nó yêu cầu JPMS resolve thêm named module `com.acme.greetings`.

### 8.3. Readability khác việc module có mặt trong graph

Giả sử:

~~~text
com.acme.app ──requires──▶ com.acme.catalog
                                │
                             requires
                                ▼
                           com.acme.model
~~~

App đọc catalog, nhưng **không tự đọc model** chỉ vì catalog cần model. Nếu app cần trực tiếp import class từ model, app cần khai báo `requires com.acme.model;` hoặc catalog có `requires transitive com.acme.model;`.

Ví dụ:

~~~java
module com.acme.catalog {
    requires transitive com.acme.model;
    exports com.acme.catalog;
}
~~~

Khi app đọc catalog, dependency có `transitive` làm cho app có readability tới model. Nhưng model vẫn phải **export** package mà app muốn import: readability không thay cho exports.

### 8.4. requires static

~~~java
module com.acme.app {
    requires static com.acme.annotations;
}
~~~

Một dependency `requires static` phải khả dụng **khi compile**, nhưng có thể vắng mặt lúc chạy. Phù hợp khi annotation hoặc API chỉ dùng ở giai đoạn build hoặc một tính năng optional được thiết kế rõ.

Không hiểu điều này như “JVM sẽ cho phép mọi lời gọi tới thư viện vắng mặt”. Nếu code runtime thực sự tải class từ module không có, vẫn có thể gặp lỗi liên kết hoặc tải class.

## 9. Unnamed module: code trên classpath

Code được tải từ classpath thuộc **unnamed module**, thay vì module có tên khai báo bằng `module-info.java`.

Một unnamed module có thể đọc các named modules **đã được resolve** và truy cập public API của các package được export tới nó. Tuy nhiên, unnamed module không làm cho tất cả JAR trên module path tự động được resolve.

Ví dụ client chạy theo classpath nhưng cần dùng thư viện named module:

~~~bash
java --module-path lib --add-modules com.acme.greetings --class-path client/classes com.acme.client.Main
~~~

Điều kiện là client thực sự có `com.acme.client.Main` trong `client/classes` và thư viện modular JAR đã xuất hiện trong `lib`. Tùy cách biên dịch client, cũng cần cấu hình module path và `--add-modules` tương ứng ở compile time.

**Chiều ngược lại có giới hạn quan trọng:** một explicit named module không thể khai báo `requires` tới unnamed module, vì unnamed module không có tên. Đặt JAR phụ thuộc trên classpath rồi viết `requires my.jar;` là sai nếu `my.jar` không phải tên module có thể resolve.

Đây là lý do chuyển ứng dụng sang JPMS khi vẫn còn nhiều thư viện chỉ hoạt động trên classpath cần được lập kế hoạch. Không cần “mở tất cả” bằng các flag vượt quyền nếu có thể giữ một phần ứng dụng trên classpath trong giai đoạn chuyển tiếp.

## 10. Automatic modules: dùng JAR chưa có descriptor trên module path

Một JAR chưa có `module-info.class` có thể trở thành **automatic module** nếu đặt trên module path và được module finder nhận diện.

Giả sử:

~~~text
lib/
└── vendor-json-2.3.jar    # JAR chưa có module-info.class
~~~

JPMS gán tên automatic module dựa trên thông tin JAR. Có hai trường hợp:

1. JAR có manifest attribute `Automatic-Module-Name`: dùng tên được công bố.
2. JAR không có attribute này: tên được suy từ tên file theo quy tắc của JDK.

Ví dụ manifest:

~~~text
Automatic-Module-Name: com.vendor.json
~~~

Một module sử dụng có thể khai báo:

~~~java
module com.acme.app {
    requires com.vendor.json;
}
~~~

Điều này chỉ đúng khi JAR trên module path được nhận diện có đúng **module name `com.vendor.json`**, và cấu hình resolution phù hợp. Trước khi sử dụng tên suy đoán, xác minh bằng:

~~~bash
jar --describe-module --file lib/vendor-json-2.3.jar
~~~

### 10.1. Quyền truy cập của automatic module

Automatic module được thiết kế để hỗ trợ di chuyển dần sang JPMS:

- Export các package trong JAR để các named modules khác có thể dùng API public.
- Mở các package theo ngữ nghĩa automatic module cho reflective access.
- Có khả năng đọc rộng các module đã được resolve khác và cả unnamed module.
- Không yêu cầu bạn biên dịch lại JAR nguồn để thêm `module-info.java`.

Tuy nhiên, automatic module có **đường biên public API rộng hơn** explicit module. Nó là công cụ tương thích, không nên được xem như bằng chứng thư viện đã thiết kế module boundary hoàn chỉnh.

### 10.2. Những rủi ro khi dùng automatic module

| Rủi ro | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Module name không ổn định | Đổi tên `vendor-json-2.3.jar` có thể đổi tên được suy ra | Ưu tiên JAR có `Automatic-Module-Name` hoặc explicit descriptor |
| Split package | Hai JAR chứa cùng package | Kiểm tra dependency/package ownership |
| Truy cập API nội bộ | JAR cũ dùng `sun.*` hoặc JDK internals | Dùng `jdeps --jdk-internals` để kiểm tra |
| Reflection không tương thích | Framework cần deep reflection vào named module khác | Chỉnh `opens` có phạm vi đúng |
| Phụ thuộc khó xác định | JAR dùng reflection/ServiceLoader nhiều | Test runtime theo hình thức phát hành |

Không dùng tên package `com.vendor.json` để tự suy ra tên automatic module; kiểm tra artifact thật vì hai tên này không bắt buộc trùng nhau.

## 11. Split packages: cùng một package trong nhiều module

**Split package** là tình huống một tên package tồn tại ở nhiều module.

Ví dụ:

~~~text
alpha.jar (module alpha)
└── com/acme/shared/Parser.class

beta.jar (module beta)
└── com/acme/shared/Formatter.class
~~~

Dù `Parser` và `Formatter` là hai class khác nhau, package `com.acme.shared` bị chia giữa hai module. Nếu một module client đọc cả `alpha` và `beta` và cả hai export package đó đến client, JPMS có thể từ chối graph vì không có nguồn package duy nhất.

Giải pháp:

1. Đổi tên package để mỗi module có quyền sở hữu riêng, nếu bạn kiểm soát mã nguồn.
2. Hợp nhất package vào một module khi hợp lý.
3. Loại bỏ phiên bản JAR trùng lặp hoặc dependency chứa class được đóng gói lại.
4. Kiểm tra lại các thư viện shaded/relocated, multi-release JAR hoặc module tự động.
5. Không cố giải quyết split-package bằng `--add-opens`, vì vấn đề là package ownership/readability, không phải thiếu reflective access.

Classpath có thể từng “vượt qua” tình huống class trùng nhau nhờ một thứ tự tìm kiếm cụ thể, nhưng điều đó không phải thiết kế phụ thuộc an toàn. JPMS giúp lỗi tổ chức module lộ rõ.

## 12. Readability, exports và reflection là ba trục khác nhau

Xét ứng dụng `com.acme.app` dùng library `com.acme.library`:

| Câu hỏi | Cơ chế trả lời | Thiếu sẽ dẫn đến |
| --- | --- | --- |
| App có đọc library không? | `requires` hoặc readability graph | App không nhìn thấy module/type mong muốn |
| Library có export package API cho app không? | `exports`/qualified exports | Package không visible từ bên ngoài |
| Một framework có được truy cập private field bằng reflection? | `opens`/qualified opens | Runtime từ chối deep reflection |

Ví dụ một thư viện chỉ công bố API cần thiết:

~~~java
module com.acme.library {
    exports com.acme.library.api;
    exports com.acme.library.testing to com.acme.tests;
    opens com.acme.library.model to com.example.mapper;
}
~~~

- Các module đọc library có thể sử dụng public API thuộc `com.acme.library.api`.
- Chỉ `com.acme.tests` được hưởng qualified export của `testing`.
- `com.example.mapper` được cấp reflective access vào package `model`, nhưng `opens` không tự cấp compile-time access thông thường.

Những tên module `com.acme.tests` và `com.example.mapper` chỉ là ví dụ. Trong ứng dụng thực tế, phải dùng đúng module name mà runtime tìm được.

### 12.1. Các flag tương thích và giới hạn sử dụng

| Flag | Tác dụng | Ví dụ |
| --- | --- | --- |
| `--add-modules` | Bổ sung root module cần resolve | `--add-modules com.acme.library` |
| `--add-reads` | Thêm quan hệ đọc module | `--add-reads com.acme.app=ALL-UNNAMED` |
| `--add-exports` | Cho phép truy cập API public trong package | `--add-exports com.acme.library/com.acme.library.internal=ALL-UNNAMED` |
| `--add-opens` | Mở package cho deep reflection runtime | `--add-opens com.acme.library/com.acme.library.model=ALL-UNNAMED` |

`ALL-UNNAMED` đề cập những unnamed modules như code trên classpath. `--add-opens` và `--add-exports` được dùng cho các trường hợp migrate, test hoặc tương thích, không phải lời khuyên mặc định mở các package nội bộ của JDK.

Nếu ứng dụng sở hữu cả hai phía dependency, ưu tiên sửa descriptor và cấu trúc API. Dùng flag tương thích cần lý do, phạm vi và kiểm thử được ghi nhận; một lỗi compile-time `import` không được giải quyết chỉ bằng `--add-opens`.

## 13. Class loading không đồng nhất với module resolution

Có hai giai đoạn liên quan nhưng khác nhau:

- **Module resolution** chọn named modules và thiết lập module configuration/readability graph.
- **Class loading/linking** tải các class cụ thể, xác minh bytecode và liên kết tham chiếu khi runtime cần.

Một module đã resolved vẫn có thể không cho code khác truy cập package chưa được export. Một module có thể export package nhưng app không đọc nó. Ngoài ra, reflection có thể bị chặn dù class public và package đã được export, nếu yêu cầu truy cập non-public member mà package chưa được mở.

Bởi vậy, không suy luận “lỗi `ClassNotFoundException` có nghĩa JAR chưa ở đâu đó trên máy”. Cần xác định **class loader**, **module graph** và **visibility**.

## 14. Các lệnh kiểm tra module trong Java 27

### 14.1. Liệt kê các system modules

~~~bash
java --list-modules
~~~

Đây là các module có trong **runtime image đang dùng**, thường có `java.base`, `java.logging`, `java.sql`. Nếu dùng custom runtime image, danh sách thực tế có thể nhỏ hơn JDK đầy đủ.

### 14.2. Xem descriptor của module

~~~bash
java --describe-module java.sql
~~~

Với user module, cung cấp module path thích hợp:

~~~bash
java --module-path lib --describe-module com.acme.greetings
~~~

### 14.3. Quan sát graph khi khởi động

~~~bash
java --show-module-resolution --module-path lib --module com.acme.app/com.acme.app.Main
~~~

`--show-module-resolution` hiển thị thông tin resolution trong startup, giúp xác định module nào trở thành root và các dependency nào được chọn. Đây là công cụ debug, không phải định dạng xuất dữ liệu ổn định để parser lâu dài.

### 14.4. Kiểm tra module trong JAR

~~~bash
jar --describe-module --file lib/com.acme.greetings.jar
~~~

Dùng để xác minh JAR có descriptor và tên module thực tế.

### 14.5. jdeps: phân tích phụ thuộc bytecode

~~~bash
jdeps --module-path lib --summary lib/com.acme.app.jar
jdeps --module-path lib --print-module-deps lib/com.acme.app.jar
~~~

Công cụ `jdeps` giúp nhìn dependencies ở mức class/package/module. Với JAR chưa modular hóa, rất hữu ích khi kiểm kê trước migration.

Kiểm tra phụ thuộc JDK internals:

~~~bash
jdeps --jdk-internals lib/legacy-helper.jar
~~~

**Giới hạn:** `jdeps` phân tích các tham chiếu bytecode có thể nhìn thấy. Nó không đảm bảo liệt kê đầy đủ class được tải bằng tên string qua reflection, provider của service hoặc plugin cấu hình động. Vì vậy phân tích tĩnh phải được bổ sung bằng integration tests.

### 14.6. jlink và jpackage ở giai đoạn phát hành

- `jar` đóng gói và kiểm tra modular JAR.
- `jlink` có thể tạo custom runtime image từ module graph tương thích.
- `jpackage` tạo các gói ứng dụng/bộ cài theo nền tảng.

Các công cụ này **không thay thế việc xác định phụ thuộc đúng**. Một custom image được tạo thành công không chứng minh chắc rằng mọi dependency chỉ tải qua reflection/dynamic configuration đều đã có mặt.

## 15. Các lỗi thường gặp khi phân giải

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `module not found` | Tên module sai; module path không bao gồm dependency | `jar --describe-module`, `--module-path` |
| `package ... is not visible` | Thiếu readability hoặc package không export | `requires`, `exports` |
| `ClassNotFoundException` | Class loader không thấy class được yêu cầu | Classpath, module graph, binary class name |
| `NoClassDefFoundError` | Thiếu class tại runtime hoặc lỗi tải/khởi tạo | Runtime dependencies, nguyên nhân gây lỗi |
| `InaccessibleObjectException` | Deep reflection vào module/package chưa mở | `opens` / qualified opens; cập nhật framework |
| Split-package/readability conflict | Hai module có package trùng được đọc trong cùng graph | Duyệt JAR và sửa package/module |
| `ServiceConfigurationError` | Khai báo provider/service không phù hợp hoặc không khởi tạo được | `uses`/`provides`, JAR descriptor, provider |
| Module có trên path nhưng không dùng được | Chưa được resolve, hoặc package chưa export | Root modules, `--add-modules`, graph, `exports` |
| Thư viện chạy trên classpath nhưng không chạy modular | Code phụ thuộc API không export hoặc reflection bị chặn | Test đúng chế độ `java -m`, xem boundary |

Một số lỗi xảy ra khi compile, một số khi launcher xây graph và một số chỉ phát sinh khi runtime tải class. Để điều tra, giữ **stack trace và cause**, không biến mọi lỗi thành “thiếu JAR”.

## 16. Dependency manager khác JPMS resolver

Maven hoặc Gradle có nhiệm vụ lựa chọn, tải và sắp đặt artifact dependencies. JPMS resolver xử lý **những module đã observable trong môi trường hiện tại**.

~~~text
Maven / Gradle
    ├─ Khai báo dependency + phạm vi
    ├─ Chọn phiên bản và tải artifacts
    └─ Cấu hình compile/runtime/test paths
                       │
                       ▼
JPMS trong javac/java
    ├─ Quan sát system/user modules
    ├─ Chọn root modules
    ├─ Resolve requires graph
    └─ Kiểm tra readability và package boundaries
~~~

`requires com.acme.greetings;` **không tự tải** thư viện từ một repository. Ngược lại, chỉ khai báo dependency trong build script không đồng nghĩa mã nguồn modular đã có `requires`/`exports` phù hợp.

Đối với dự án lớn, nên để build tool quản lý phiên bản artifact, scope và classpath/module path, còn descriptor định nghĩa named module boundary. Tránh trộn các tập `compileOnly`/`runtimeOnly` với `requires static` mà không kiểm tra kết quả packaging; cách cấu hình cụ thể tùy plugin/build tool đang sử dụng.

## 17. Kế hoạch di chuyển dần từ classpath sang JPMS

Không cần modular hóa toàn bộ ứng dụng lớn trong một lần.

**Bước 1 — Kiểm kê:** xác định các JAR, phiên bản, package trùng, API nội bộ JDK, reflection và service loader. Dùng `jar --describe-module`, `jdeps` và dependency reports.

**Bước 2 — Thiết kế module boundary:** nhóm package theo trách nhiệm, quyết định package API và internal, tránh chia package qua nhiều module.

**Bước 3 — Thêm descriptor cho code thuộc quyền sở hữu:**

~~~java
module com.acme.catalog {
    requires java.logging;
    exports com.acme.catalog.api;
}
~~~

**Bước 4 — Giải quyết thư viện bên thứ ba:** ưu tiên explicit modules, cân nhắc automatic modules với JAR chưa modular hóa, giữ một số thành phần trên classpath nếu cần trong quá trình chuyển tiếp. Kiểm tra automatic module name và split packages.

**Bước 5 — Test theo cách phân phối thực:** chạy đúng chế độ modular:

~~~bash
java --module-path lib --module com.acme.app/com.acme.app.Main
~~~

Nếu test chỉ sử dụng classpath, bạn có thể bỏ sót các lỗi module boundary tại runtime. Kiểm tra service loading, reflection và cấu hình môi trường.

**Bước 6 — Hoàn thiện phát hành:** khi sử dụng `jlink`/`jpackage`, xác minh module JDK cần thiết, provider classes và native resources trong runtime image. Không giả định phân tích tĩnh nhìn thấy mọi dependency động.

## 18. Sai lầm phổ biến và hướng xử lý

| Sai lầm | Hệ quả | Hướng xử lý |
| --- | --- | --- |
| Cho rằng mọi JAR trong `lib` tự nằm trên classpath | Runtime không tìm được class | Chỉ định chính xác entry hoặc wildcard |
| Cho rằng mọi JAR trên module path tự resolved | Module cần dùng có thể không có trong graph | Kiểm tra root modules và `--add-modules` |
| Dùng `public` rồi nghĩ mọi module import được | Lỗi visibility | Bổ sung readability và export phù hợp |
| Hiểu `requires` là transitive mặc định | Client không đọc dependency gián tiếp | Khai báo trực tiếp hoặc `requires transitive` nếu API cần |
| Đặt JAR chỉ trên classpath rồi khai `requires` | Named module không tồn tại | Dùng modular/automatic JAR trên module path |
| Đoán automatic module name theo package | Tên module không đúng | Xem `jar --describe-module` |
| Dùng `opens` thay vì `exports` để fix import | Compile vẫn lỗi | Export public API; opens chỉ cho reflection |
| Mở toàn bộ module khi framework cần một package | Mất encapsulation không cần thiết | Qualified opens cho đúng framework/package |
| Có hai module export cùng package cho client | Split-package conflict | Tổ chức lại package ownership |
| Test theo classpath nhưng phát hành theo module path | Lỗi JPMS chỉ xuất hiện lúc chạy | Integration test đúng mô hình launch |
| Nghĩ `jdeps` phát hiện mọi phụ thuộc runtime | Bỏ sót reflection/plugin | Test integration và cấu hình động |
| Dùng `--add-exports/--add-opens` làm giải pháp mặc định | Khó bảo trì, mở quyền quá rộng | Sửa API/module descriptor khi có thể |
| Nhầm JPMS với dependency manager | Không kiểm soát phiên bản artifact | Tách build-time dependency resolution và JPMS module resolution |

## 19. Checklist review classpath và module path

- [ ] Đã xác định ứng dụng dùng classpath hay module path khi phát hành.
- [ ] Cả compile và runtime đều được cấu hình đủ dependency theo từng scope.
- [ ] `--class-path`, `--module-path`, `--module-source-path` được dùng đúng ngữ cảnh.
- [ ] Mỗi explicit module có `module-info.java` hợp lệ.
- [ ] Các `requires` khớp đúng tên module thật của dependency.
- [ ] Public API package được export; internal package không bị mở không cần thiết.
- [ ] Chỉ dùng `requires transitive` khi muốn cho client đọc dependency thông qua API library.
- [ ] Chỉ dùng `requires static` khi runtime vắng module là trường hợp hợp lệ.
- [ ] Reflection framework chỉ được cấp `opens` phù hợp.
- [ ] Automatic module name đã được kiểm tra trên artifact thật.
- [ ] Không có split packages xung đột trong resolved graph.
- [ ] Không dựa vào thứ tự classpath/wildcard để xử lý nhiều phiên bản JAR.
- [ ] Đã test startup, class loading, service loading và reflective access theo đúng mode.
- [ ] Có thể dùng `--show-module-resolution` và `jdeps` để tìm vấn đề.
- [ ] Dữ liệu/ngữ nghĩa của module graph được hiểu khác dependency resolution của build tool.
- [ ] Mọi flag tương thích vượt quyền JPMS có lý do và phạm vi rõ ràng.
- [ ] Nếu tạo runtime image tùy biến, đã kiểm tra đủ module JDK và dependency động.

## 20. Nguồn tài liệu chính thức

- [JLS Java SE 27 — Chapter 7: Packages and Modules](https://docs.oracle.com/javase/specs/jls/se27/html/jls-7.html) — module descriptor, `requires`, `exports`, `opens` và unnamed modules.
- [Java SE 27 — java Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html) — `--module-path`, `--module`, `--add-modules`, `--show-module-resolution` và launch.
- [Java SE 27 — javac Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html) — `--class-path`, `--module-path`, `--module-source-path` và compile-time dependency search.
- [Java SE 27 — jar Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jar.html) — modular JAR và `--describe-module`.
- [Java SE 27 — jdeps Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jdeps.html) — phân tích bytecode/module dependencies và JDK internals.
- [Java SE 27 API — java.lang.module](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/module/package-summary.html) — resolution và readability graph.
- [Java SE 27 API — ModuleDescriptor](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/module/ModuleDescriptor.html) — descriptor của named/automatic module.
- [JEP 261 — Module System](https://openjdk.org/jeps/261) — thiết kế và triển khai JPMS.
- [JEP 200 — The Modular JDK](https://openjdk.org/jeps/200) — tổ chức JDK thành các module.

**Kết luận:** Cả classpath và module path đều có chỗ đứng trong Java 27. Classpath tổ chức tìm class theo đường dẫn; module path cùng JPMS giải quyết bài toán **named modules, root selection, requires graph và quyền truy cập qua exports/opens**. Khi sửa lỗi phụ thuộc, hãy lần lượt hỏi: artifact đang ở đâu, module có được resolve chưa, caller có đọc module đó không, package có export đúng đối tượng không và có cần reflection hay không. Tách bạch các câu hỏi này giúp build, đóng gói thư viện và vận hành ứng dụng ổn định hơn.
