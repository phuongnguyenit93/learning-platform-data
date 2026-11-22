# Tạo project Java 21 với classpath hoặc module path phù hợp

Khi tạo project Java 21, cần chọn cách phân giải thư viện phù hợp với cấu trúc ứng dụng. Với một ứng dụng nhỏ hoặc project chưa dùng Java Platform Module System (JPMS), **classpath** là lựa chọn đơn giản và tương thích rộng. Khi project được chia thành các module có tên, cần kiểm soát phụ thuộc và đóng gói API rõ ràng, hãy dùng **module path** cùng `module-info.java`.

Hai cách này đều được hỗ trợ trong Java 21. Việc chọn module path không phải yêu cầu bắt buộc chỉ vì project dùng JDK 21; hãy chọn theo kiến trúc và thư viện mà project thực sự cần.

## 1. Chuẩn bị JDK 21

Project cần JDK để biên dịch và runtime tương thích để chạy. Mở terminal tại bất kỳ thư mục nào và kiểm tra:

```shell
java --version
javac --version
```

Cả hai lệnh cần trỏ đến bộ JDK 21 mà project dự định sử dụng. `java` là trình chạy ứng dụng; `javac` là trình biên dịch. Nếu `java` báo phiên bản 21 nhưng `javac` không tồn tại hoặc báo phiên bản khác, hãy kiểm tra `JAVA_HOME` và thứ tự thư mục `bin` trong `PATH` để terminal sử dụng cùng một JDK.

Khi biên dịch, dùng `--release 21` để giới hạn cả cú pháp ngôn ngữ và API Java ở mức phát hành 21. Tùy chọn này đặc biệt hữu ích khi project được biên dịch bằng một JDK mới hơn nhưng vẫn phải chạy trên Java 21. Chỉ đặt phiên bản JDK trong IDE hoặc biến môi trường là chưa đủ để bảo đảm mã nguồn không vô tình gọi API mới hơn; `--release` giúp kiểm tra điều đó ngay lúc biên dịch.

## 2. Hiểu đúng classpath và module path

| Tiêu chí | Classpath | Module path |
|---|---|---|
| Cách khai báo | `--class-path` hoặc `-cp` | `--module-path` hoặc `-p` |
| Cấu trúc mã nguồn | Không bắt buộc có `module-info.java` | Mỗi module tường minh có `module-info.java` |
| Khai báo phụ thuộc | Đưa thư mục lớp hoặc JAR vào classpath | Khai báo `requires` trong module descriptor và đặt module phụ thuộc trên module path |
| Phạm vi đóng gói | Các lớp thường thuộc unnamed module | Module có tên, có thể khai báo package được export hoặc open |
| Phù hợp khi | Ứng dụng đơn giản, thư viện/framework chủ yếu dùng classpath, hoặc chưa cần ranh giới module | Ứng dụng nhiều module, thư viện có module descriptor, cần ranh giới phụ thuộc và đóng gói rõ ràng |

Classpath là danh sách thư mục chứa `.class` và các JAR mà trình biên dịch hoặc JVM cần tìm. Các lớp chạy theo cơ chế classpath thuộc unnamed module. Đây vẫn là cách tổ chức hợp lệ và phổ biến cho nhiều ứng dụng Java.

Module path chứa các module đã được đóng gói hoặc biên dịch. Một module tường minh có tên và mô tả phụ thuộc trong `module-info.java`. JPMS cho phép module chỉ công khai các package cần thiết bằng `exports`, đồng thời khai báo module cần dùng bằng `requires`.

Không trộn hai cơ chế một cách tùy tiện. Nếu chạy ứng dụng theo JPMS, hãy đặt các module cần thiết trên module path và khởi chạy module bằng tên module. Nếu ứng dụng dùng classpath, hãy bảo đảm các JAR cần thiết xuất hiện trên classpath ở cả lúc biên dịch lẫn lúc chạy.

## 3. Tạo project Java 21 dùng classpath

Đây là cấu trúc phù hợp cho một ứng dụng nhỏ, bài thực hành hoặc project chưa cần chia thành các module JPMS:

```text
java21-classpath/
├── src/
│   └── com/
│       └── example/
│           └── app/
│               └── Main.java
├── lib/
└── out/
```

`src` chứa mã nguồn, `lib` là nơi có thể đặt các thư viện JAR bên ngoài, còn `out` chứa bytecode sau khi biên dịch. Tạo các thư mục này trước khi chạy lệnh biên dịch.

Nội dung `src/com/example/app/Main.java`:

```java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from Java 21");
    }
}
```

Tên package phải khớp với cấu trúc thư mục bên dưới `src`. Từ thư mục gốc `java21-classpath`, biên dịch bằng:

```shell
javac --release 21 --source-path src -d out src/com/example/app/Main.java
```

Ý nghĩa các tùy chọn:

- `--release 21`: biên dịch theo ngôn ngữ và API của Java 21.
- `--source-path src`: nơi `javac` tìm thêm mã nguồn được tham chiếu khi cần.
- `-d out`: ghi các file `.class` vào `out`, giữ cấu trúc package.
- `src/com/example/app/Main.java`: file nguồn đầu vào.

Sau khi biên dịch thành công, chạy lớp chính bằng tên đầy đủ của nó:

```shell
java --class-path out com.example.app.Main
```

JVM tìm `com.example.app.Main` bên trong thư mục gốc classpath `out`, sau đó gọi phương thức `main`. Kết quả mong đợi:

```text
Hello from Java 21
```

### Thêm thư viện JAR vào classpath

Giả sử project có các JAR nằm trực tiếp trong `lib`. Đưa chúng vào classpath khi biên dịch:

```shell
javac --release 21 --class-path "lib/*" --source-path src -d out src/com/example/app/Main.java
```

Khi chạy, classpath phải chứa cả bytecode của project và thư viện:

```shell
# Windows PowerShell
java --class-path "out;lib/*" com.example.app.Main

# Linux hoặc macOS
java --class-path "out:lib/*" com.example.app.Main
```

Dấu phân cách giữa các phần tử classpath là `;` trên Windows và `:` trên Linux/macOS. Ký hiệu `lib/*` bao gồm các JAR nằm trực tiếp trong thư mục `lib`; nó không quét đệ quy các thư mục con. Mỗi thư viện cần thiết phải có mặt ở cả thời điểm biên dịch và thời điểm chạy. JVM cũng không tự động tìm JAR được lồng bên trong một JAR khác.

Với project có nhiều file nguồn, có thể truyền tất cả file `.java` vào `javac` hoặc chỉ định lớp đầu vào và để `--source-path` tìm các file nguồn phụ thuộc. Khi project lớn dần, nên để Maven hoặc Gradle quản lý source set, thư viện và classpath thay vì tự duy trì danh sách lệnh dài.

## 4. Tạo project Java 21 dùng module path

Chọn JPMS khi project có ranh giới module thực sự, chẳng hạn một ứng dụng gồm nhiều module hoặc một thư viện muốn công bố API theo từng package. Mỗi module tường minh có một file `module-info.java` ở thư mục gốc mã nguồn của module.

Ví dụ project có một module ứng dụng:

```text
java21-modules/
├── src/
│   └── com.example.app/
│       ├── module-info.java
│       └── com/
│           └── example/
│               └── app/
│                   └── Main.java
└── out/
```

Tên thư mục `com.example.app` là tên module trong ví dụ này. Nội dung `src/com.example.app/module-info.java`:

```java
module com.example.app {
}
```

Nội dung `src/com.example.app/com/example/app/Main.java`:

```java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from the com.example.app module");
    }
}
```

Từ thư mục gốc `java21-modules`, biên dịch module:

```shell
javac --release 21 --module-source-path src -d out --module com.example.app
```

`--module-source-path src` cho `javac` biết cấu trúc thư mục nguồn theo tên module. `--module com.example.app` yêu cầu biên dịch module đó; `-d out` ghi kết quả vào thư mục đầu ra theo cấu trúc module. Sau khi biên dịch, `out` chứa module đã biên dịch và có thể được dùng làm module path.

Chạy lớp chính bằng tên module kết hợp tên lớp đầy đủ:

```shell
java --module-path out --module com.example.app/com.example.app.Main
```

Trong cú pháp `--module`, phần trước dấu `/` là tên module và phần sau là tên lớp chính. Cách khởi chạy này yêu cầu JVM phân giải module `com.example.app` từ module path.

### Khai báo phụ thuộc module

Nếu mã nguồn sử dụng một module khác thuộc JDK, khai báo phụ thuộc bằng `requires`. Ví dụ, khi dùng API trong module `java.sql`:

```java
module com.example.app {
    requires java.sql;
}
```

Tên sau `requires` là tên module, không phải tên package hay tên file JAR. Chỉ khai báo những module mà mã nguồn thực sự cần.

Với một thư viện bên ngoài đã được đóng gói thành module, đặt JAR của thư viện trong `lib`, thêm `requires <ten.module>` vào `module-info.java`, rồi đưa `lib` vào module path khi biên dịch:

```shell
javac --release 21 --module-path lib --module-source-path src -d out --module com.example.app
```

Khi chạy, module path phải chứa cả module ứng dụng và các module phụ thuộc. Dùng đúng dấu phân cách theo hệ điều hành:

```shell
# Windows PowerShell
java --module-path "out;lib" --module com.example.app/com.example.app.Main

# Linux hoặc macOS
java --module-path "out:lib" --module com.example.app/com.example.app.Main
```

Nếu chưa biết tên module mà một JAR công bố, kiểm tra metadata của JAR thay vì tự đoán từ tên file:

```shell
jar --describe-module --file lib/example-library.jar
```

Tên module cần dùng trong `requires` phải khớp với tên module mà JAR công bố. Một JAR không có module descriptor có thể được xử lý như automatic module khi đặt trên module path, nhưng tên module suy ra có thể phụ thuộc metadata hoặc tên file. Với project JPMS cần cấu hình ổn định, ưu tiên thư viện công bố module name rõ ràng và xác minh bằng công cụ `jar`.

### `exports` và `opens` dùng để làm gì?

Module descriptor còn có thể kiểm soát khả năng truy cập package:

```java
module com.example.library {
    exports com.example.library.api;
}
```

`exports` cho phép module khác truy cập các kiểu `public` trong package được công bố. Những package không được export vẫn được giữ bên trong module theo quy tắc đóng gói của JPMS.

`opens` phục vụ truy cập phản chiếu sâu (deep reflection), thường cần trong một số framework hoặc thư viện ánh xạ dữ liệu. Chỉ mở đúng package cần thiết và cho đúng module khi có thể; không thêm `opens` đại trà nếu project không có yêu cầu đó. `exports` và `opens` giải quyết hai mục đích khác nhau, vì vậy không thay thế lẫn nhau.

## 5. Chọn cách tổ chức cho project

| Tình huống | Lựa chọn nên bắt đầu | Lý do |
|---|---|---|
| Bài tập, ứng dụng nhỏ hoặc công cụ nội bộ | Classpath | Ít cấu hình, dễ chạy trực tiếp bằng JDK |
| Project dùng thư viện/framework chủ yếu hướng tới classpath | Classpath | Phù hợp với cách đóng gói và hướng dẫn của các thư viện đó |
| Ứng dụng được chia thành nhiều module có tên | Module path | Khai báo phụ thuộc tường minh và phân định package được công bố |
| Thư viện muốn định nghĩa API công khai và che giấu phần triển khai | Module path | Dùng `exports` và quy tắc đóng gói của JPMS |
| Project hiện tại chạy ổn trên classpath, chưa cần ranh giới module | Tiếp tục classpath | Không cần thêm module descriptor nếu chưa có lợi ích kiến trúc cụ thể |

Một project có thể dùng thư viện JAR trên classpath mà không cần tự tạo module. Ngược lại, khi đã chọn JPMS, cần hiểu tên module, quan hệ `requires` và vị trí các module trên module path. Không quyết định chỉ dựa trên việc project có bao nhiêu file Java; hãy dựa trên cách project cần quản lý phụ thuộc và công khai API.

## 6. Dùng Maven hoặc Gradle để quản lý project

Các lệnh `javac` và `java` ở trên giúp hiểu trực tiếp compiler, output directory và cơ chế nạp lớp/module. Với ứng dụng thực tế có nhiều thư viện, Maven hoặc Gradle giúp quản lý dependency, source set và quy trình build lặp lại được. Build tool vẫn sử dụng compiler của JDK; hãy cấu hình rõ mức Java mà project hỗ trợ.

Với Maven, đặt release trong `pom.xml`:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```

Đảm bảo phiên bản Maven Compiler Plugin của project hỗ trợ thuộc tính `maven.compiler.release`, và Maven đang chạy bằng JDK phù hợp. Nếu project có `module-info.java`, cấu hình compiler và dependency theo mô hình JPMS của project.

Với Gradle Groovy DSL, có thể yêu cầu JDK 21 bằng Java toolchain:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Toolchain giúp Gradle chọn JDK dùng cho các tác vụ Java. Có thể đặt thêm mức API/ngôn ngữ đích rõ ràng cho tác vụ biên dịch:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 21
}
```

Khi dùng build tool, thêm thư viện qua cơ chế dependency của Maven/Gradle. Build tool sẽ chuẩn bị classpath cho project thông thường; với project JPMS, hãy giữ `module-info.java` và cấu hình dependency để compiler có thể phân giải các module cần thiết. Tránh duy trì đồng thời một danh sách JAR thủ công và một danh sách dependency của build tool vì hai nguồn cấu hình dễ lệch nhau.

## 7. Lỗi thường gặp và cách kiểm tra

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `invalid source release: 21` | `javac` đang chạy từ JDK thấp hơn 21 | Kiểm tra `javac --version`, `JAVA_HOME` và `PATH`; chọn đúng JDK 21 |
| `package ... does not exist` | Thiếu JAR phụ thuộc, sai classpath hoặc sai source path/package | Kiểm tra `--class-path`, `--source-path` và dòng `package` so với cấu trúc thư mục |
| `Could not find or load main class` | Chỉ định sai tên lớp hoặc classpath không trỏ đến thư mục gốc chứa package | Đưa `out` vào classpath và chạy bằng tên lớp đầy đủ, ví dụ `com.example.app.Main` |
| `Module ... not found` | Thiếu module trên module path hoặc dùng sai tên module | Kiểm tra thư mục/JAR trên `--module-path` và dùng `jar --describe-module` để xác nhận tên |
| `module ... does not read ...` hoặc không truy cập được package | Quan hệ `requires` hoặc quyền `exports` chưa phù hợp | Kiểm tra module descriptor của module sử dụng và module cung cấp API |
| Chạy được lúc biên dịch nhưng lỗi thiếu lớp khi chạy | Thư viện có trong classpath lúc biên dịch nhưng thiếu khi chạy | Đưa cùng dependency cần thiết vào classpath lúc chạy; với JPMS, thêm module vào module path |

Khi debug, kiểm tra theo thứ tự: phiên bản JDK, lệnh biên dịch thực tế, thư mục output, tên package/module, rồi danh sách dependency ở cả compile time và runtime. Lỗi classpath thường liên quan đến vị trí lớp/JAR; lỗi JPMS thường liên quan thêm đến tên module và quan hệ đọc module.

## 8. Checklist trước khi bàn giao project

- `java --version` và `javac --version` đều trỏ đến JDK 21 mong muốn.
- Project đã chọn classpath hoặc module path dựa trên nhu cầu kiến trúc.
- Lệnh biên dịch đặt `--release 21` khi cần bảo đảm tương thích API Java 21.
- Tất cả dependency cần thiết đều có mặt ở thời điểm biên dịch và chạy.
- Nếu dùng JPMS, mỗi module tường minh có `module-info.java`, các quan hệ `requires` hợp lệ và module path chứa đủ module phụ thuộc.
- Lệnh chạy dùng đúng tên lớp đầy đủ với classpath, hoặc đúng tên module/lớp với module path.

Sau khi hoàn tất các bước này, project có thể được biên dịch và chạy nhất quán bằng JDK 21. Khi chuyển từ project đơn giản sang kiến trúc nhiều module, có thể bắt đầu bằng cách xác định ranh giới API và dependency, sau đó bổ sung module descriptor theo từng module thay vì thêm `module-info.java` mà chưa có mục đích rõ ràng.
