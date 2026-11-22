# Module path trong Java

## 1. Module path là gì?

**Module path** (đường dẫn module) là danh sách vị trí mà compiler hoặc JVM tìm kiếm các module Java. Đây là thành phần của Java Platform Module System (JPMS), được giới thiệu từ Java 9.

Trong hệ thống module, mỗi named module khai báo tên và quan hệ phụ thuộc trong tệp `module-info.java`. Module path giúp công cụ Java tìm các module, đọc module descriptor, giải quyết các khai báo `requires` và xác định package nào được công khai qua `exports`.

Module path thường chứa:

- **Modular JAR:** JAR có module descriptor `module-info.class`.
- **Automatic module JAR:** JAR chưa có module descriptor nhưng được đặt trên module path; tên module được lấy từ manifest hoặc tên tệp.
- **Exploded module:** thư mục module đã biên dịch, có `module-info.class` ở cấp gốc.
- **Thư mục chứa module:** thư mục có các modular JAR hoặc thư mục exploded module bên trong.

Ví dụ, một dự án có thể đặt module đã biên dịch trong `mods` hoặc modular JAR trong `lib`. Khi chạy, JVM nhận các vị trí đó qua tùy chọn `--module-path`.

## 2. Vì sao cần module path?

Module path giúp ứng dụng Java có cấu trúc rõ ràng khi dự án gồm nhiều module hoặc sử dụng thư viện modular.

Các lợi ích chính:

- **Giải quyết phụ thuộc:** JVM tìm module được khai báo qua `requires`.
- **Kiểm soát truy cập:** module chỉ công khai package được khai báo qua `exports`; reflection sâu có thể cần `opens`.
- **Phát hiện xung đột:** hệ thống module có thể phát hiện tên module trùng, package bị chia giữa các module hoặc phụ thuộc không hợp lệ.
- **Triển khai có chọn lọc:** `jlink` dùng module path để tạo runtime image chứa các module cần thiết.
- **Tách mã nguồn và thư viện:** source module, module đã biên dịch và thư viện modular có thể nằm ở các vị trí riêng.

Module path không chỉ là thư mục chứa JAR. JVM dùng nó để tìm module và xây dựng module graph dựa trên descriptor cùng các quan hệ phụ thuộc.

## 3. Phân biệt module path và classpath

Classpath là cơ chế tìm class truyền thống. Module path phục vụ việc tìm và giải quyết các module có tên.

| Tiêu chí | Classpath | Module path |
|---|---|---|
| Tùy chọn | `--class-path`, `-classpath` hoặc `-cp` | `--module-path` hoặc `-p` |
| Nội dung | Thư mục class, JAR thông thường | Modular JAR, automatic module JAR, exploded module hoặc thư mục chứa module |
| Cách tổ chức | Các class thuộc unnamed module | Các named module được tìm và resolve |
| Kiểm soát package | Không có ranh giới JPMS giữa các JAR | Descriptor điều khiển `requires`, `exports` và `opens` |
| Khởi chạy | Tên class chính hoặc `-jar` | Tên module qua `-m` hoặc `--module` |

Ví dụ classpath:

```bash
java -cp "out:lib/*" com.example.Main
```

Ví dụ module path:

```bash
java --module-path lib --module com.example.app/com.example.app.Main
```

Trên Windows, dấu phân cách path element là dấu chấm phẩy (`;`). Trên Linux và macOS, dấu phân cách là dấu hai chấm (`:`).

Không thể chỉ đổi `-cp` thành `-p` rồi mong một ứng dụng classpath tự động trở thành module. Ứng dụng named module cần module descriptor và cấu hình phụ thuộc phù hợp.

### 3.1. Named module và unnamed module

Class được nạp từ classpath thuộc unnamed module của class loader tương ứng. Class trong modular JAR hoặc exploded module có thể thuộc một named module.

Named module không thể khai báo `requires` trực tiếp tới unnamed module. Vì vậy, nếu ứng dụng modular cần một thư viện cũ chưa có module descriptor, có thể đưa JAR đó lên module path để Java xem nó như automatic module, nếu thư viện phù hợp với cơ chế này.

## 4. Cấu trúc của module path

Module path gồm một hoặc nhiều path element. Mỗi element có thể chỉ tới một module hoặc một thư mục chứa nhiều module.

Ví dụ với các module đã biên dịch:

```text
project/
├── mods/
│   ├── com.example.app/
│   │   ├── module-info.class
│   │   └── com/example/app/Main.class
│   └── com.example.greeter/
│       ├── module-info.class
│       └── com/example/greeter/Greeter.class
└── src/
```

Ở đây, `mods` là thư mục chứa các exploded module. Khi truyền `--module-path mods`, JVM tìm từng module trong thư mục đó.

Ví dụ với modular JAR:

```text
project/
├── lib/
│   ├── com.example.app.jar
│   └── com.example.greeter.jar
└── src/
```

`lib` là thư mục chứa các modular JAR. Có thể truyền chính thư mục `lib` cho module path.

Một path element cũng có thể là đường dẫn trực tiếp tới một modular JAR hoặc thư mục gốc của một exploded module. Tránh đặt nhiều phiên bản có cùng tên module trên các vị trí khác nhau, vì module được tìm thấy trước có thể che khuất phiên bản phía sau.

## 5. Khai báo module bằng module-info.java

Mỗi named module có module descriptor được khai báo trong `module-info.java`. Khi biên dịch, compiler tạo `module-info.class` ở cấp gốc của module.

Ví dụ module thư viện:

```java
module com.example.greeter {
    exports com.example.greeter;
}
```

Khai báo này có nghĩa:

- Tên module là `com.example.greeter`.
- Package `com.example.greeter` được công khai cho các module khác.
- Các package khác của module, nếu có, không tự động được export.

Module ứng dụng có thể khai báo phụ thuộc:

```java
module com.example.app {
    requires com.example.greeter;
}
```

`requires` cho biết module ứng dụng cần module thư viện. Khi compiler hoặc JVM giải quyết module graph, nó tìm `com.example.greeter` trên module path.

Một số directive thường gặp:

| Directive | Ý nghĩa |
|---|---|
| `requires` | Khai báo module phụ thuộc |
| `requires transitive` | Truyền khả năng đọc module phụ thuộc tới module đọc module hiện tại |
| `requires static` | Phụ thuộc cần khi biên dịch nhưng có thể không bắt buộc ở runtime |
| `exports` | Công khai package cho module khác |
| `exports ... to` | Chỉ công khai package cho các module được nêu tên |
| `opens` | Cho phép truy cập reflective sâu vào package |
| `uses` | Khai báo module sử dụng một service |
| `provides ... with` | Khai báo implementation cung cấp cho một service |

Tên module được xác định bởi descriptor hoặc quy tắc automatic module, không nhất thiết giống tên thư mục hay tên file JAR.

## 6. Tùy chọn --module-path và -p

Tùy chọn `--module-path` chỉ định nơi tìm application modules. Dạng viết tắt là `-p`.

Cú pháp:

```bash
java --module-path <module-path> ...
javac --module-path <module-path> ...
```

Ví dụ:

```bash
java --module-path mods --module com.example.app/com.example.app.Main
```

Các thành phần:

- `--module-path mods`: tìm module trong thư mục `mods`.
- `--module`: chọn module cần khởi chạy.
- `com.example.app/com.example.app.Main`: tên module, dấu gạch chéo và tên lớp chính.

Dạng rút gọn:

```bash
java -p mods -m com.example.app/com.example.app.Main
```

`-p` tương đương `--module-path`; `-m` tương đương `--module` trong lệnh launcher.

### 6.1. Nhiều vị trí trên module path

Có thể cung cấp nhiều path element để module nằm ở nhiều thư mục hoặc archive khác nhau.

Windows PowerShell:

```powershell
java --module-path "mods;lib" --module com.example.app/com.example.app.Main
```

Linux/macOS:

```bash
java --module-path "mods:lib" --module com.example.app/com.example.app.Main
```

Đường dẫn có dấu cách nên được đặt trong dấu nháy kép. Dùng đúng dấu phân cách theo hệ điều hành; nhầm `;` và `:` là lỗi cấu hình phổ biến.

### 6.2. Đường dẫn trực tiếp tới một module

Nếu chỉ có một modular JAR, có thể chỉ định trực tiếp file đó:

```bash
java --module-path lib/com.example.greeter.jar --describe-module com.example.greeter
```

Nếu có nhiều module phụ thuộc nhau, hãy đưa tất cả vị trí cần thiết vào module path, thường là một thư mục chứa các modular JAR hoặc một danh sách path element.

## 7. Module path khi biên dịch bằng javac

`javac` cũng hỗ trợ module path. Trong lúc biên dịch, compiler cần tìm module được mã nguồn khai báo qua `requires` để kiểm tra kiểu và quyền truy cập.

Ví dụ khi module thư viện đã được đóng gói trong `lib`:

```bash
javac --module-path lib -d out --module-source-path src --module com.example.app
```

Trong lệnh trên:

- `--module-path lib` tìm các module đã biên dịch hoặc đóng gói, ví dụ `com.example.greeter`.
- `--module-source-path src` chỉ định nơi tìm mã nguồn của các module đang biên dịch.
- `-d out` chỉ định thư mục đầu ra.
- `--module com.example.app` chọn module nguồn cần biên dịch.

Cần phân biệt hai tùy chọn:

| Tùy chọn | Dùng để tìm |
|---|---|
| `--module-path` | Module dependency đã biên dịch hoặc đóng gói |
| `--module-source-path` | Mã nguồn của các module đang biên dịch |

`--module-source-path` hữu ích khi biên dịch nhiều module cùng lúc. Nó không thay thế module path dùng để tìm dependency đã biên dịch.

## 8. Ví dụ hoàn chỉnh: hai module dùng chung module path

Ví dụ sau tạo một module thư viện và một module ứng dụng. Đây là chương trình Java 17+ có thể biên dịch và chạy bằng JDK đầy đủ.

### 8.1. Tạo cấu trúc source

```text
module-path-demo/
└── src/
    ├── com.example.greeter/
    │   ├── module-info.java
    │   └── com/example/greeter/Greeter.java
    └── com.example.app/
        ├── module-info.java
        └── com/example/app/Main.java
```

Tệp `src/com.example.greeter/module-info.java`:

```java
module com.example.greeter {
    exports com.example.greeter;
}
```

Tệp `src/com.example.greeter/com/example/greeter/Greeter.java`:

```java
package com.example.greeter;

public final class Greeter {
    private Greeter() {
    }

    public static String message() {
        return "Hello from module path";
    }
}
```

Tệp `src/com.example.app/module-info.java`:

```java
module com.example.app {
    requires com.example.greeter;
}
```

Tệp `src/com.example.app/com/example/app/Main.java`:

```java
package com.example.app;

import com.example.greeter.Greeter;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.message());
    }
}
```

Ứng dụng khai báo `requires com.example.greeter`. Module thư viện khai báo `exports com.example.greeter` để ứng dụng được truy cập package chứa class `Greeter`.

### 8.2. Biên dịch cả hai module thành exploded modules

Từ thư mục gốc `module-path-demo`, tạo thư mục output.

Linux/macOS:

```bash
mkdir -p mods
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force mods
```

Biên dịch cả hai module:

```bash
javac --module-source-path src -d mods --module com.example.greeter,com.example.app
```

Sau khi biên dịch, cấu trúc output có dạng:

```text
mods/
├── com.example.greeter/
│   ├── module-info.class
│   └── com/example/greeter/Greeter.class
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
```

Mỗi thư mục con là một exploded module. `mods` là thư mục chứa các module, nên có thể được sử dụng làm module path.

### 8.3. Chạy ứng dụng từ module path

Chạy:

```bash
java --module-path mods --module com.example.app/com.example.app.Main
```

Stdout chính xác:

```text
Hello from module path
```

JVM tìm module `com.example.app` trong `mods`, đọc descriptor, giải quyết `requires com.example.greeter` rồi khởi chạy lớp `com.example.app.Main`.

Có thể viết ngắn hơn:

```bash
java -p mods -m com.example.app/com.example.app.Main
```

Hai lệnh có cùng ý nghĩa.

### 8.4. Đóng gói các module thành modular JAR

Từ thư mục gốc dự án, tạo thư mục `lib`:

```bash
mkdir -p lib
```

Tạo modular JAR cho thư viện và ứng dụng:

```bash
jar --create --file lib/com.example.greeter.jar -C mods/com.example.greeter .
jar --create --file lib/com.example.app.jar -C mods/com.example.app .
```

Mỗi JAR giữ `module-info.class` ở cấp gốc. Vì vậy, chúng vẫn là modular JAR.

Kiểm tra descriptor của module thư viện:

```bash
jar --describe-module --file lib/com.example.greeter.jar
```

Chạy ứng dụng bằng thư mục chứa hai JAR:

```bash
java --module-path lib --module com.example.app/com.example.app.Main
```

Stdout vẫn là:

```text
Hello from module path
```

Ví dụ cho thấy module path có thể trỏ tới thư mục chứa modular JAR hoặc thư mục chứa exploded module.

## 9. Modular JAR và automatic module

Không phải JAR nào cũng có `module-info.class`. Khi một JAR không có descriptor được đặt trên module path, Java có thể xem nó là **automatic module**.

Tên automatic module được xác định theo thứ tự:

1. Dùng thuộc tính `Automatic-Module-Name` trong manifest nếu có.
2. Nếu không có, suy ra tên từ tên file JAR theo quy tắc của JPMS.

Ví dụ:

```text
lib/
└── legacy-utils-2.4.jar
```

Nếu JAR không có `module-info.class` và không khai báo `Automatic-Module-Name`, tên module được suy ra từ tên file. Tên chính xác cần xác minh bằng công cụ JDK thay vì tự đoán.

Automatic module có hành vi tương thích rộng để hỗ trợ thư viện cũ, chẳng hạn export các package của nó và đọc các module quan sát được. Tuy nhiên, không nên coi automatic module là thiết kế module hoàn chỉnh.

Khi cần tên module ổn định, nhà cung cấp thư viện nên khai báo `Automatic-Module-Name` trong manifest hoặc phát hành modular JAR có module descriptor chính thức.

## 10. Quy tắc phân giải module trên module path

Khi khởi chạy một named module, JVM thực hiện module resolution để xác định module graph.

Ở mức khái niệm:

1. Module chính được chọn làm root module.
2. JVM đọc module descriptor của root.
3. Các module được khai báo qua `requires` được tìm trên module path hoặc trong runtime image.
4. Quá trình tiếp tục theo các dependency được yêu cầu.
5. JVM kiểm tra tính hợp lệ của graph, bao gồm tên module và package export.
6. Các module đã được resolve trở thành một phần của cấu hình runtime.

Một số quy tắc quan trọng:

- Tên module phải duy nhất trong module graph.
- Hai module không được tạo split package gây xung đột trong graph.
- Module phải export package để module khác truy cập kiểu public trong package đó.
- `requires transitive` ảnh hưởng đến khả năng đọc module theo chuỗi phụ thuộc.
- Thứ tự module path có thể ảnh hưởng module nào được tìm thấy trước nếu có bản trùng tên; tránh để nhiều bản cùng tên trên path.

Module path không tự động đưa mọi module tìm thấy vào graph. Các module được resolve phụ thuộc root module, directive `requires` và các tùy chọn bổ sung như `--add-modules`.

## 11. Các tùy chọn module liên quan

Ngoài `--module-path`, Java launcher có các tùy chọn giúp điều khiển module graph.

| Tùy chọn | Mục đích |
|---|---|
| `--module` hoặc `-m` | Chạy lớp chính trong một module |
| `--add-modules` | Thêm module root vào quá trình resolution |
| `--limit-modules` | Giới hạn tập module có thể quan sát |
| `--upgrade-module-path` | Cung cấp bản thay thế cho system module có thể nâng cấp |
| `--patch-module` | Bổ sung hoặc thay thế class/resource trong một module cụ thể |
| `--show-module-resolution` | In thông tin quá trình resolve module |
| `--validate-modules` | Kiểm tra tính hợp lệ của các module quan sát được |
| `--list-modules` | Liệt kê các module quan sát được rồi kết thúc |
| `--describe-module` | Hiển thị descriptor của module được chỉ định |

Ví dụ thêm module root:

```bash
java --module-path lib --add-modules com.example.greeter --list-modules
```

`--add-modules` hữu ích khi module không được kéo vào graph chỉ bởi các dependency hiện có nhưng vẫn cần được resolve, ví dụ module cung cấp service.

Xem module resolution khi chạy ứng dụng:

```bash
java --show-module-resolution --module-path lib --module com.example.app/com.example.app.Main
```

Tùy chọn `--show-module-resolution` in thông tin module được resolve. Chương trình vẫn thực thi và in kết quả của nó.

Kiểm tra các module trên module path:

```bash
java --validate-modules --module-path lib
```

`--upgrade-module-path` và `--patch-module` là các tùy chọn chuyên biệt. Chúng không phải cách thông thường để thêm thư viện ứng dụng; dependency của ứng dụng nên được đặt trên module path và khai báo bằng `requires`.

## 12. Module path khi dùng jlink

`jlink` tạo runtime image tùy chỉnh từ các module đã được resolve. Công cụ này cũng nhận module path qua `--module-path` hoặc `-p`.

Ví dụ tạo runtime image có ứng dụng modular trong `lib`.

Linux/macOS:

```bash
jlink --module-path "$JAVA_HOME/jmods:lib" --add-modules com.example.app --output app-runtime
```

Windows PowerShell:

```powershell
jlink --module-path "$env:JAVA_HOME\jmods;lib" --add-modules com.example.app --output app-runtime
```

Ở đây:

- `$JAVA_HOME/jmods` cung cấp các JMOD của JDK.
- `lib` cung cấp modular JAR của ứng dụng.
- `--add-modules com.example.app` chọn module ứng dụng làm root; dependency được resolve theo descriptor.
- `--output app-runtime` chỉ định thư mục runtime image được tạo.

`jlink` có thể dùng JMOD ở link-time. Khi chạy ứng dụng bằng lệnh `java` thông thường, hãy dùng modular JAR hoặc exploded module trên module path theo định dạng launcher hỗ trợ; không mặc định rằng JMOD có thể dùng như modular JAR ở runtime.

## 13. Module path trong IDE và build tool

Trong dự án thực tế, module path có thể được cấu hình trong IDE hoặc build tool thay vì gõ trực tiếp lệnh launcher.

### 13.1. IntelliJ IDEA

Với dự án modular:

- Đảm bảo thư mục chứa `module-info.java` được nhận diện là source root phù hợp.
- Chọn JDK có hỗ trợ JPMS.
- Kiểm tra module dependencies và module descriptor.
- Kiểm tra Run Configuration có chọn đúng module hoặc module path.
- Xác nhận thư viện modular nằm trên module path nếu dự án cần JPMS.

Nếu chạy từ terminal được nhưng IDE báo không tìm thấy module, kiểm tra cấu hình module của Run Configuration và các thư viện được gắn với module.

### 13.2. Eclipse

Eclipse hỗ trợ module Java trong project sử dụng JDK tương thích. Kiểm tra:

- JRE System Library trỏ tới JDK phù hợp.
- Tệp `module-info.java` được nhận diện trong source folder.
- Module dependencies được khai báo đúng.
- Run Configuration sử dụng module path khi khởi chạy named module.

### 13.3. Maven và Gradle

Maven và Gradle có thể biên dịch, kiểm thử và đóng gói dự án modular. Cấu hình cụ thể phụ thuộc plugin và phiên bản build tool.

Các điểm cần xác nhận:

- Mã nguồn có `module-info.java` và package đúng cấu trúc.
- Dependency được đưa vào module path nếu là modular dependency.
- Compiler release và JDK chạy build tool tương thích.
- Test runner dùng đúng module path hoặc cấu hình mở module cần thiết.
- Artifact JAR sau đóng gói giữ module descriptor.

Không nên chỉ nhìn vào cấu hình dependency của Maven/Gradle rồi kết luận module path lúc runtime đã đúng. Hãy kiểm tra lệnh build, test và lệnh khởi chạy thực tế.

## 14. Chẩn đoán và kiểm tra module path

Khi JVM không tìm được module hoặc resolve không thành công, hãy kiểm tra từng lớp cấu hình.

Một số lệnh hữu ích:

```bash
java --list-modules
java --module-path lib --list-modules
java --module-path lib --describe-module com.example.greeter
jar --describe-module --file lib/com.example.greeter.jar
```

Có thể dùng `jdeps` để phân tích dependency module của ứng dụng:

```bash
jdeps --module-path lib --check com.example.app
```

Khi kiểm tra, xác nhận:

1. Đường dẫn tồn tại và shell đã truyền đúng giá trị cho Java.
2. Module path trỏ đúng thư mục chứa module hoặc đúng file module.
3. Modular JAR có `module-info.class` ở vị trí hợp lệ.
4. Automatic module có tên module hợp lệ.
5. Tên trong `requires` khớp tên module thực tế.
6. Package cần dùng được export.
7. Không có hai phiên bản module cùng tên gây che khuất hoặc xung đột.
8. Module nguồn được biên dịch đúng bằng `--module-source-path`.
9. JDK dùng để biên dịch và chạy hỗ trợ phiên bản module/class file của dự án.

## 15. Lỗi thường gặp khi cấu hình module path

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `Module ... not found` | Module path sai hoặc thiếu module dependency | Kiểm tra thư mục, tên module và file JAR |
| `Module ... does not read ...` | Module graph không có quan hệ đọc cần thiết | Khai báo `requires` đúng trong module descriptor |
| `package ... is not visible` | Package không được module sở hữu export | Thêm `exports` phù hợp hoặc dùng API công khai |
| `FindException` khi khởi động | Module archive hỏng, descriptor sai hoặc trùng tên | Kiểm tra JAR bằng `jar --describe-module` và loại bỏ bản trùng |
| `ResolutionException` | Module graph có dependency hoặc package conflict | Kiểm tra `requires`, split package và các module cùng tên |
| Chạy được với `-cp` nhưng lỗi với `-p` | Thư viện cũ nằm trên classpath và chưa được chuyển thành module phù hợp | Đưa JAR phù hợp lên module path hoặc thiết kế lại ranh giới module |
| `java -jar` không chạy như named module | `-jar` là chế độ khởi chạy JAR theo classpath | Dùng `--module-path` và `--module` cho modular application |
| Không tìm thấy source module | Dùng nhầm `--module-path` thay cho `--module-source-path` | Đặt source root đúng và dùng tùy chọn dành cho source |
| Module path có nhiều phiên bản cùng tên | Nhiều artifact cùng module name nằm trên các path element | Giữ một phiên bản được chọn và kiểm tra thứ tự path |

Một lỗi phổ biến là nhầm tên module với tên JAR. Hãy dùng `jar --describe-module` hoặc `java --describe-module` để xác định tên module thay vì suy luận chỉ từ tên file.

## 16. Quy trình chuẩn khi cấu hình module path

Khi thêm dependency hoặc chạy một ứng dụng modular:

1. Xác định module ứng dụng và đọc `module-info.java`.
2. Liệt kê các module được khai báo trong `requires`.
3. Xác định mỗi dependency là modular JAR, automatic module hay exploded module.
4. Đặt module vào một thư mục hoặc path element rõ ràng.
5. Cấu hình `--module-path` khi biên dịch và chạy.
6. Khi biên dịch nhiều source module, dùng thêm `--module-source-path`.
7. Khởi chạy named module bằng `--module` hoặc `-m`.
8. Kiểm tra module descriptor, module graph và package export nếu gặp lỗi.
9. Loại bỏ các bản module trùng tên khỏi module path.
10. Nếu tạo runtime image, cung cấp module path phù hợp cho `jlink`.
11. Ghi lại phiên bản JDK, vị trí module và lệnh build/run để các thành viên có thể tái lập môi trường.

Nên chuẩn hóa tên module và cách tổ chức thư mục dependency trong nhóm. Việc này giảm lỗi do mỗi máy dùng một đường dẫn hoặc một phiên bản thư viện khác nhau.

## 17. Tổng kết

Module path là cơ chế tìm kiếm và phân giải named module trong hệ thống module Java. Nó giúp compiler, JVM và `jlink` tìm đúng module, kiểm tra phụ thuộc và xây dựng module graph.

Những điểm cần nhớ:

- `--module-path` hoặc `-p` chỉ định nơi tìm module.
- Module path có thể chứa modular JAR, automatic module JAR, exploded module hoặc thư mục chứa module.
- `module-info.java` khai báo tên module, `requires`, `exports` và các directive liên quan.
- `--module-source-path` tìm mã nguồn module; `--module-path` tìm module dependency.
- `--module` hoặc `-m` dùng để khởi chạy named module.
- Windows dùng dấu `;` để phân tách path element; Linux và macOS dùng dấu `:`.
- Classpath và module path phục vụ hai mô hình tổ chức khác nhau; named module không thể khai báo phụ thuộc trực tiếp tới unnamed module.
- `jlink` sử dụng module path để tạo runtime image; JMOD chủ yếu phục vụ link-time.
- Khi gặp lỗi, kiểm tra tên module, descriptor, dependency, exports và các phiên bản trùng lặp trên path.

**Tài liệu tham khảo chính thức:**

- [The java Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [The javac Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
- [ModuleFinder API — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/module/ModuleFinder.html)
