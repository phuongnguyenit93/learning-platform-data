# Biên dịch một hoặc nhiều mô-đun bằng `--module-source-path` trong Java

Java Platform Module System (JPMS), xuất hiện từ Java 9, cho phép một ứng dụng khai báo các **named modules** bằng `module-info.java`. Khi biên dịch một cây mã nguồn gồm nhiều module, `javac --module-source-path` chỉ cho compiler **vị trí mã nguồn của từng module** và cách xác định một file `.java` thuộc module nào. Kết hợp với `-m` / `--module`, ta có thể biên dịch một module hoặc nhiều module có quan hệ phụ thuộc bằng một lời gọi `javac`.

Điều quan trọng là phân biệt bốn việc: **khai báo module trong mã nguồn** (`module-info.java`), **tìm mã nguồn các module** (`--module-source-path`), **chọn module cần biên dịch** (`-m`) và **tìm module đã biên dịch khi chạy** (`java --module-path`). Chúng có nhiệm vụ khác nhau.

## 1. Module Java là gì?

Một named module có tên, chứa các package và có descriptor thường nằm trong file `module-info.java` ở gốc cây nguồn của module. Ví dụ:

~~~java
// module-info.java
module com.example.library {
    exports com.example.api;
}
~~~

- `module com.example.library` khai báo tên module.
- `exports com.example.api` cho phép các module đọc được module này truy cập các **public types** thuộc package `com.example.api` theo quy tắc JPMS.
- `requires com.example.library` trong module khác khai báo phụ thuộc đọc module này.
- `exports` không tương đương với `requires`: một cái chỉ định package nào được phơi ra, cái kia chỉ định module nào cần đọc.
- Cú pháp module descriptor còn có `requires transitive`, `requires static`, `opens`, `uses` và `provides ... with ...`. Trong bài này, cặp `requires`/`exports` đủ để minh họa quy trình biên dịch.

Khi được biên dịch, `module-info.java` tạo `module-info.class`; các class trong package tạo các `.class` khác. Named module thường được phân phối bằng **exploded module directory** hoặc **modular JAR** có descriptor.

Với code Java không đặt trong named module (unnamed module/classpath), cách bố trí và lệnh compile khác; **không bắt buộc sử dụng `--module-source-path` cho mọi chương trình Java**.

## 2. Bản đồ các tùy chọn thường đi cùng nhau

| Tùy chọn | Dùng tại đâu? | Chức năng |
| --- | --- | --- |
| `javac --module-source-path PATH` | Biên dịch | Chỉ cách tìm **source trees của các named modules** |
| `javac --module M1,M2` hoặc `javac -m M1,M2` | Biên dịch | Chọn module nguồn cần được compile |
| `javac -d OUT` | Biên dịch | Chọn nơi ghi `.class`; khi biên dịch nhiều module, output được chia theo module |
| `javac --module-path MODS` / `-p MODS` | Biên dịch | Tìm **module đã biên dịch** mà các module nguồn phụ thuộc |
| `javac --release 17` | Biên dịch | Kiểm tra source/API và sinh class tương thích Java 17 |
| `java --module-path MODS` / `-p MODS` | Chạy | Tìm các module có sẵn để phân giải và khởi chạy |
| `java --module M/pack.Main` / `java -m M/pack.Main` | Chạy | Chỉ định module và main class để thực thi |

**Chú ý hai nghĩa của `-m`:** trong lệnh `javac`, `-m` chọn **module để biên dịch**; trong lệnh `java`, `-m` chọn **module để khởi chạy**. Hai chương trình có option giống cách viết nhưng làm hai việc khác nhau.

`--module-source-path` không phải `--module-path`, cũng không phải `--source-path`. Dùng một đường dẫn source mà quên `-m` hoặc quên liệt kê file nguồn chưa chắc khiến compiler biên dịch toàn bộ cây nguồn; đường dẫn chỉ cho biết **tìm nguồn ở đâu**, còn danh sách `-m` hoặc các file `.java` chỉ ra **đầu vào cần biên dịch**.

## 3. Bố trí cây nguồn theo module

Cách dễ nhất cho một dự án nhỏ là có thư mục cha `src/`, bên dưới có **một thư mục tên đúng bằng module**. Bên trong từng module là `module-info.java` và cây package:

~~~text
project/
├── src/
│   ├── com.example.lib/
│   │   ├── module-info.java
│   │   └── com/
│   │       └── example/
│   │           └── lib/
│   │               └── Message.java
│   └── com.example.app/
│       ├── module-info.java
│       └── com/
│           └── example/
│               └── app/
│                   └── Main.java
└── out/                       # Được tạo trước khi javac chạy
~~~

Ở dạng cây này, `--module-source-path src` cho `javac` biết dưới `src` có các module source roots, mỗi thư mục con ứng với module cùng tên. Không cần viết tên tệp nguồn của mọi class nếu dùng `--module` để chọn module.

Một cách nhìn khác:

~~~text
--module-source-path src
             │
             ├── com.example.lib/ → nguồn module com.example.lib
             │                         └── module-info.java
             └── com.example.app/ → nguồn module com.example.app
                                       └── module-info.java

javac -d out
             │
             ├── com.example.lib/ → module-info.class và class của library
             └── com.example.app/ → module-info.class và class của app
~~~

**Tên package và tên module khác nhau.** Module có thể chứa nhiều package và không bắt buộc package chính trùng tên module. Trong ví dụ, chúng giống tiền tố chỉ để dễ quan sát.

Đặt `module-info.java` ở gốc module root. Các file khai báo `package com.example.lib;` nằm trong `com/example/lib/` bên dưới root đó. Code của **named module** cần có named package; không đặt application classes vào unnamed/default package.

## 4. Ví dụ đầy đủ: hai module phụ thuộc nhau

Tạo **bốn tệp** như cây thư mục ở phần 3.

### 4.1. Descriptor của thư viện

**File `src/com.example.lib/module-info.java`:**

~~~java
module com.example.lib {
    exports com.example.lib;
}
~~~

Descriptor cho phép code ở module khác đọc public types trong package `com.example.lib` nếu module kia khai báo quan hệ `requires` thích hợp.

### 4.2. Class công khai của thư viện

**File `src/com.example.lib/com/example/lib/Message.java`:**

~~~java
package com.example.lib;

public final class Message {
    private Message() {
    }

    public static String say() {
        return "hello modular Java";
    }
}
~~~

Method `say()` là public và static, đủ điều kiện để `com.example.app` gọi khi module dependency/export đều hợp lệ.

### 4.3. Descriptor của ứng dụng

**File `src/com.example.app/module-info.java`:**

~~~java
module com.example.app {
    requires com.example.lib;
}
~~~

Nếu bỏ `requires com.example.lib;`, `com.example.app` không có quan hệ đọc module `com.example.lib` được khai báo phù hợp. Dù module library có `exports` thì application cũng không tự có quyền dùng public API của nó theo mô hình JPMS.

### 4.4. Main class

**File `src/com.example.app/com/example/app/Main.java`:**

~~~java
package com.example.app;

import com.example.lib.Message;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Message.say());
    }
}
~~~

`import com.example.lib.Message;` chỉ giúp dùng tên ngắn `Message` trong source. Nó không thay `requires` và không tự thêm JAR dependency.

## 5. Biên dịch cả hai module trong một lệnh

Từ thư mục `project/` chứa `src/`, tạo thư mục output rỗng `out/`, rồi chạy:

~~~bash
mkdir out
javac --release 17 -d out --module-source-path src -m com.example.lib,com.example.app
~~~

Lệnh này được áp dụng cho **JDK 17+**. Nếu thư mục `out` đã tồn tại, bỏ qua bước `mkdir out`. Tên module trong `-m` được phân tách bằng dấu **phẩy**, không phải dấu phân tách filesystem classpath.

Ý nghĩa từng phần:

1. `--release 17`: source/API/bytecode có mục tiêu Java 17.
2. `-d out`: vị trí output. Với nhiều named modules, `javac` tự tạo thư mục output theo module.
3. `--module-source-path src`: đường dẫn đến **module source hierarchy**, từ đó compiler tìm `src/com.example.lib/` và `src/com.example.app/`.
4. `-m com.example.lib,com.example.app`: yêu cầu compile mã nguồn các module đã chọn.
5. Từ `requires com.example.lib`, `javac` biết app phụ thuộc thư viện; có thể giải quyết tham chiếu qua các module nguồn trong cùng compilation.

**Kết quả:** `javac` thành công thường **không in stdout**. Các file được sinh:

~~~text
out/
├── com.example.lib/
│   ├── module-info.class
│   └── com/example/lib/Message.class
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
~~~

Đây là hai **exploded named modules**. Một thư mục `out/com.example.lib` không phải một file JAR, nhưng có thể được dùng làm module trên module path, vì chứa `module-info.class` và cây package tương ứng.

### Chạy chương trình vừa biên dịch

~~~bash
java --module-path out --module com.example.app/com.example.app.Main
~~~

Cách viết rút gọn:

~~~bash
java -p out -m com.example.app/com.example.app.Main
~~~

**Stdout chính xác:**

~~~text
hello modular Java
~~~

`java` nhận `out` là nơi tìm compiled modules; chọn module `com.example.app` rồi class `com.example.app.Main`. JVM phân giải dependency `com.example.lib` và gọi `main`. Dòng `--module-source-path src` dùng trong **compile**, không cần ở lúc chạy.

Ví dụ này không cần thêm JAR hoặc thư viện bên ngoài vì chỉ sử dụng API chuẩn JDK và hai module nguồn đã cho.

## 6. Biên dịch một module bằng cùng module source path

Khi chỉ muốn biên dịch module thư viện:

~~~bash
mkdir lib-out
javac --release 17 -d lib-out --module-source-path src -m com.example.lib
~~~

Output:

~~~text
lib-out/
└── com.example.lib/
    ├── module-info.class
    └── com/example/lib/Message.class
~~~

Chỉ định `-m com.example.lib` để chọn nguồn module thư viện. Nếu chọn một **module có dependency nguồn** như `com.example.app`, compiler có thể biên dịch thêm những source modules mà nó cần để hoàn thành compilation. Với layout ví dụ và một output rỗng, lệnh sau có thể cho ra cả app và lib:

~~~bash
mkdir app-out
javac --release 17 -d app-out --module-source-path src -m com.example.app
~~~

Không nên hiểu `-m com.example.app` là cam kết output sẽ chứa **duy nhất** module đó. Compiler xác định source dependencies theo module graph; khi cần một bản build chủ động, rõ ràng của cả hai module, chỉ định `-m com.example.lib,com.example.app` như phần 5.

### Biên dịch tuần tự với module đã có

Có thể biên dịch library trước, rồi cho app nhìn thấy **compiled library** qua module path. Dùng một output `out` đã tồn tại:

~~~bash
javac --release 17 -d out --module-source-path src -m com.example.lib
javac --release 17 -d out --module-source-path src --module-path out -m com.example.app
java --module-path out -m com.example.app/com.example.app.Main
~~~

`--module-path out` ở lần `javac` thứ hai hướng compiler tìm compiled module library nếu có; `--module-source-path src` vẫn chỉ các nguồn module. Khi đang tổ chức build thực tế, tránh nhầm source path và module path nếu có thể có nhiều phiên bản cùng tên module; hãy xác định module nào compiler ưu tiên theo cấu hình và artifact thực tế.

Một lựa chọn khác cho **một module riêng lẻ** là chỉ định các file `.java` cần biên dịch cùng `module-info.java`, và dùng `--module-path` khi phụ thuộc vào module đã compiled. `--module-source-path` đặc biệt hữu ích khi muốn compiler tìm đúng nhiều source module trong một cây chung.

## 7. Hai dạng cú pháp của `--module-source-path`

Theo tài liệu `javac`, module source path có **module-pattern form** và **module-specific form**. Chúng giúp xử lý cấu trúc thư mục khác nhau.

### 7.1. Dạng mẫu: một cây có quy luật

Với cây mẫu đơn giản ở trên:

~~~bash
javac --release 17 -d out --module-source-path src -m com.example.lib,com.example.app
~~~

Nếu không có `*` trong path pattern, `javac` hiểu ngầm vị trí module ngay dưới đường dẫn (tương đương logic ghép `/*` cho mỗi segment thích hợp). Có thể viết mẫu rõ ràng:

~~~bash
javac --release 17 -d out --module-source-path "src/*" -m com.example.lib,com.example.app
~~~

Trong **module-pattern form**, dấu `*` là **placeholder cho tên module**, không đơn giản là wildcard để shell tự liệt kê file. Nên đặt pattern trong dấu nháy để PowerShell, Bash hoặc công cụ gọi lệnh không can thiệp vào cách `javac` nhận argument.

Với layout thường thấy khi mỗi module có thêm `src/main/java`:

~~~text
workspace/
├── com.example.lib/
│   └── src/main/java/
│       ├── module-info.java
│       └── com/example/lib/Message.java
└── com.example.app/
    └── src/main/java/
        ├── module-info.java
        └── com/example/app/Main.java
~~~

Bạn có thể dùng:

~~~bash
javac --release 17 -d out --module-source-path "*/src/main/java" -m com.example.lib,com.example.app
~~~

Chạy lệnh từ thư mục `workspace`. Tên module được thay vào `*`, nên compiler tìm `com.example.lib/src/main/java` và `com.example.app/src/main/java`. Nếu các thư mục module đều nằm dưới `modules/`, pattern tương ứng là `"modules/*/src/main/java"`.

**Lưu ý:** đây là pattern của **đường dẫn module source**, không phải glob để liệt kê tất cả `.java`. Không viết `"src/**/*.java"` như một cách thay thế `--module-source-path`.

### 7.2. Dạng chỉ định từng module: `module-name=path`

Nếu nguồn các module không được bố trí cùng quy luật, hoặc muốn cấu hình chính xác:

~~~bash
javac --release 17 -d out ^
  --module-source-path com.example.lib=src/com.example.lib ^
  --module-source-path com.example.app=src/com.example.app ^
  -m com.example.lib,com.example.app
~~~

**Ở khối lệnh trên, dấu `^` là ký tự tiếp dòng chỉ dành cho Windows CMD**, không sử dụng nguyên văn trong PowerShell hoặc Bash. Để tránh khác biệt hệ điều hành, có thể viết **một dòng duy nhất**:

~~~bash
javac --release 17 -d out --module-source-path com.example.lib=src/com.example.lib --module-source-path com.example.app=src/com.example.app -m com.example.lib,com.example.app
~~~

Cú pháp này cho `javac` biết module `com.example.lib` ở `src/com.example.lib` và module `com.example.app` ở `src/com.example.app`. Đường dẫn có thể được đặt trong dấu nháy nếu chứa khoảng trắng (đặt toàn bộ argument `"com.example.lib=path có khoảng trắng"` để truyền thành một tham số cho `javac`).

Có thể kết hợp **một** pattern với các module-specific overrides. Khi cùng module được khai báo cả hai cách, vị trí **module-specific** có ưu tiên. Không dùng hai module-pattern forms khác nhau trong cùng lời gọi và không chỉ định lặp module-specific form cho **cùng một module**.

### 7.3. Nhiều vị trí nguồn cho cùng module

Module-specific form có thể chỉ một danh sách search roots cho một module khi thiết kế project cần nhiều thư mục nguồn. Dấu phân tách path list phụ thuộc hệ điều hành: `;` trên Windows, `:` trên Linux/macOS. Ví dụ minh họa:

~~~text
Windows:  --module-source-path "com.example.lib=src/lib-main;src/lib-generated"
Unix:     --module-source-path "com.example.lib=src/lib-main:src/lib-generated"
~~~

Đây là cấu hình đường dẫn, **chỉ dùng khi các thư mục thực sự tồn tại và chứa cây package phù hợp**; không phải hai lệnh có thể chạy độc lập từ ví dụ `src` ở trên. Với module-pattern form cũng có quy tắc phân tách nhiều path segments và mở rộng dấu ngoặc nhọn. Tránh rải tùy chọn trùng nhau khi một pattern đơn giản đã mô tả đủ source layout.

## 8. Phân biệt `--module-source-path` với các đường dẫn khác

### `--source-path`: tìm source theo package

Trong compilation **không phải nhiều module cùng lúc**, `--source-path` hoặc `-sourcepath` mô tả vị trí source files theo cây package. Nó không biểu diễn đầy đủ quy tắc tìm **nhiều module nguồn độc lập** như `--module-source-path`.

Ví dụ project truyền thống không JPMS:

~~~text
src/com/example/Main.java
~~~

Có thể compile với:

~~~bash
javac --release 17 -d out -sourcepath src src/com/example/Main.java
~~~

Đây là ví dụ về phân biệt options, **không chạy trực tiếp với bốn file modular** ở phần 4.

### `--class-path`: tìm classpath entries

Classpath là thế giới **unnamed module**. Một library có thể được dùng qua `-cp` trong code truyền thống, nhưng nó không tự tạo named module cho thư viện và không thay yêu cầu `requires` của named module. Việc trộn classpath, automatic modules và named modules có quy tắc đọc/export riêng; không giả định thêm `-cp` có thể sửa mọi lỗi module graph.

### `--module-path`: tìm module đã biên dịch

`javac --module-path out` cho compiler thấy compiled named modules; `java --module-path out` cho launcher/runtime tìm modules. Nó không thay việc chỉ định source roots khi muốn biên dịch đồng thời nhiều source modules.

Nếu chỉ có JAR của library, chẳng hạn `lib/com.example.lib.jar`, và nguồn app ở một module root, cách build tuần tự có thể chỉ định JAR đó qua `--module-path lib` thay vì đưa nguồn thư viện vào `--module-source-path`. Đừng nhầm **module path** với **module source path** vì chúng trỏ tới hai loại đầu vào khác nhau.

## 9. Biên dịch bằng danh sách source files thay vì `-m`

`--module-source-path` chỉ đường tìm nguồn; muốn biên dịch, bạn có thể chỉ định **module names** bằng `-m` hoặc **file paths** cụ thể.

Ví dụ để chỉ đích danh hai tệp nguồn thuộc library:

~~~bash
javac --release 17 -d out --module-source-path src src/com.example.lib/module-info.java src/com.example.lib/com/example/lib/Message.java
~~~

Ở chế độ biên dịch nhiều module, mọi source file nêu trực tiếp phải nằm trong các module roots hợp lệ của module source path. Lệnh trên là minh họa đầu vào source files **thuộc module**; nếu biên dịch thêm app đồng thời, cần liệt kê file của app hoặc dùng `-m` để compiler chọn module.

Khi nhiều module có hàng chục/hàng trăm file, `-m` thường dễ đọc hơn việc ghi danh sách các file `.java`. `-m` cho phép compiler xác định những source files trong modules được chọn và những dependencies cần thiết. Trong build tool, plugin/task có thể điều phối compilation theo module mà không cần bạn tự liệt kê chúng trên command line.

## 10. Kiểm tra kết quả `.class` và mô-đun sau biên dịch

Sau khi chạy lệnh ở phần 5:

~~~bash
javap --module-path out --module com.example.lib -p com.example.lib.Message
javap --module-path out --module com.example.app -p com.example.app.Main
~~~

`javap` có thể inspect classes trong các named modules với module path tương ứng. Nếu toolchain của bạn không hỗ trợ đúng cặp option như trên, dùng trực tiếp class file path trong `out` để xem descriptor/bytecode:

~~~bash
javap -p out/com.example.lib/com/example/lib/Message.class
javap -p out/com.example.app/com/example/app/Main.class
~~~

`javap` dùng để kiểm tra bytecode/method signatures của artifact đã sinh, **không tự sửa lỗi `requires`/package exports**.

Có thể dùng:

~~~bash
java --show-module-resolution --module-path out -m com.example.app/com.example.app.Main
~~~

để quan sát module resolution khi chạy. Tùy JVM và config, thông tin resolution thường được in ra stderr bên cạnh stdout `hello modular Java`, nên khi dùng để đối chiếu **stdout thuần** hãy chạy lệnh bình thường ở phần 5.

## 11. Đóng gói thành modular JAR (bước sau compilation)

`--module-source-path` phục vụ **biên dịch**. Đóng gói là bước riêng; khi các exploded modules tồn tại trong `out`, có thể đóng từng module thành modular JAR.

Tạo thư mục `dist` rồi chạy từ `project/`:

~~~bash
mkdir dist
jar --create --file dist/com.example.lib.jar -C out/com.example.lib .
jar --create --file dist/com.example.app.jar --main-class com.example.app.Main -C out/com.example.app .
~~~

Mỗi JAR chứa `module-info.class` của module tương ứng. Cách đặt `--main-class` trong lệnh `jar` lưu entry point cho module app để có thể dùng dạng chạy module không ghi `/MainClass` khi thích hợp.

Có thể chạy tường minh:

~~~bash
java --module-path dist -m com.example.app/com.example.app.Main
~~~

Stdout vẫn là:

~~~text
hello modular Java
~~~

Điểm khác với `java -jar` truyền thống: đây là **named module launch** qua module path, sử dụng `requires`/exports và module resolution. Không mặc định hai modular JAR cần ghép thành một fat JAR; JPMS được thiết kế để các module có thể phân phối và phân giải riêng.

Không đóng nguyên thư mục `out` (có nhiều module) thành một JAR như thể đó là một module duy nhất. Mỗi modular JAR phải có module descriptor và cây class của **chính module đó** tại gốc JAR.

## 12. Lỗi phổ biến và cách chẩn đoán

| Lỗi/hiện tượng | Cần kiểm tra |
| --- | --- |
| `module not found on module source path` | Tên trong `-m`, tên thư mục module, `module-info.java`, pattern và working directory |
| `module name ... does not match expected name ...` | Tên sau `module` trong descriptor có khớp tên module do pattern suy ra không |
| `not in a module on the module source path` | File `.java` nêu trực tiếp có nằm dưới module root hợp lệ không |
| `package ... is not visible` | Module consumer có `requires` không; module provider có `exports` đúng package không; kiểu có public không |
| `module not found: com.example.lib` | Source module/path hoặc compiled module/path chưa có module được yêu cầu; kiểm tra tên và nội dung |
| `class not found` / `Could not find or load main class` | Output path, module path, tên class đầy đủ, class có main hợp lệ |
| Compile thành công nhưng runtime không resolve được module | `java --module-path` trỏ nhầm nơi; thiếu modular JAR, thiếu dependency hoặc class file không tương thích |
| Có thư mục output nhưng thiếu `module-info.class` | Đã compile đúng named module chưa; output có bị xóa/ghi nhầm hay không |
| `invalid flag` / `invalid target release` | Đang chạy JDK/compiler nào (`javac -version`), cú pháp option và mức `--release` |
| `java: Error occurred during initialization of boot layer` | Module graph lúc chạy: descriptor, duplicate modules, missing module, split packages hay lỗi cấu hình liên quan |

### 12.1. Tên module phải khớp đường dẫn pattern

Nếu `src/com.example.lib/module-info.java` khai báo:

~~~java
module com.example.other {
}
~~~

thì không khớp logic module root `com.example.lib` của pattern `--module-source-path src`. Đây là **mẫu cố ý sai**, không phải file thay thế cho ví dụ chính. Hãy sửa descriptor hoặc bố trí source sao cho tên module trong `module-info.java` và tên module trong `-m`/source hierarchy nhất quán.

### 12.2. Thiếu `exports` không sửa bằng `import`

Nếu `com.example.lib` không export `com.example.lib`, app dù viết:

~~~java
import com.example.lib.Message;
~~~

vẫn không được phép sử dụng public type đó theo JPMS. Import chỉ rút gọn tên, **không vượt ranh giới module exports**.

### 12.3. Thiếu `requires` không sửa bằng `--module-source-path`

Nếu module app không khai báo `requires com.example.lib;` (hoặc cơ chế đọc module thích hợp trong một ngữ cảnh đặc biệt), chỉ đặt source của lib bên cạnh source app không cấp quyền truy cập theo module graph. `--module-source-path` giúp compiler **tìm module**, không biến mỗi module thành dependency của tất cả module còn lại.

### 12.4. Cây thư mục nhiều cấp nhưng pattern quá ngắn

Với source thực tế ở `modules/com.example.lib/src/main/java/`, pattern `--module-source-path modules` sẽ tìm sai root. Dùng:

~~~bash
javac --release 17 -d out --module-source-path "modules/*/src/main/java" -m com.example.lib,com.example.app
~~~

Đây là lệnh cho layout **modules/** khác với `src/` trong ví dụ chính; chỉ dùng khi đã đặt đúng các file tại vị trí đó.

### 12.5. Một package xuất hiện trong nhiều module

JPMS có các giới hạn về split packages, đặc biệt khi module graph cần đọc các module khác nhau chứa package trùng tên. Không giải quyết bằng cách đổi thứ tự `-m`, gộp class files vào một module root hoặc dùng classpath tùy tiện. Sắp xếp **package ownership** rõ ràng để tránh nhập nhằng và cấu hình trái module model.

### 12.6. Lệnh đã thành công nhưng bạn chỉ thấy class của một module

Kiểm tra chính xác argument của `-m`, những source files đã được chọn và các module dependencies. `javac -m com.example.lib` không có nghĩa buộc compiler tạo cả app nếu app không được yêu cầu hoặc không là dependency của lib.

## 13. Cách làm việc ổn định trong dự án

1. **Chọn layout rõ ràng:** mỗi named module có root và `module-info.java`; package files nằm đúng cây package. Với layout chung, dùng `--module-source-path src` hoặc pattern khớp đường dẫn.
2. **Xác định module graph:** module phụ thuộc phải có `requires`, module cung cấp public API phải `exports` đúng package. Không sửa module graph chỉ bằng Java imports.
3. **Biên dịch đến output sạch khi kiểm chứng:** `javac --release 17 -d out --module-source-path src -m ...`; dùng output rỗng để không nhầm stale class files.
4. **Xem kết quả theo module:** `out/<module-name>/module-info.class` và các tệp class theo cây package. Nếu dùng annotation processors, còn có thể có output generated riêng.
5. **Chạy bằng module path:** `java -p out -m M/package.Main`, kiểm tra module resolution và stdout thực tế.
6. **Đóng gói từng module khi cần:** modular JAR là bước riêng, không nằm trong tác dụng của `--module-source-path`.
7. **Trong build hệ thống lớn:** Gradle/Maven có thể cung cấp compile tasks, dependency resolution, annotation processing và packaging phù hợp. Hiểu `javac` trực tiếp giúp debug cấu hình build, không nhất thiết thay toàn bộ cơ chế build bằng một lệnh thủ công.

### Bảng ghi nhớ nhanh

| Bạn muốn... | Lệnh/tùy chọn cốt lõi |
| --- | --- |
| Biên dịch library duy nhất từ cùng cây nguồn | `javac -d out --module-source-path src -m com.example.lib` |
| Biên dịch cả library và app cùng một lần | `javac -d out --module-source-path src -m com.example.lib,com.example.app` |
| Dùng cấu trúc `module/src/main/java` | `javac -d out --module-source-path "*/src/main/java" -m ...` |
| Chỉ định source root riêng cho từng module | `--module-source-path moduleName=path` (lặp theo module) |
| Biên dịch app với library đã có ở dạng module | `javac --module-path compiledLibs ...` |
| Chạy app sau compile | `java -p out -m com.example.app/com.example.app.Main` |
| Đưa module thành modular JAR | `jar --create --file ... -C out/moduleName .` |

## 14. Câu hỏi tự kiểm tra

**1. Vì sao `--module-source-path src` tự tìm được `com.example.lib`?**  
Vì layout có `src/<module-name>/module-info.java`, và module-pattern form suy ra source root của từng module từ tên module. Descriptor phải khớp.

**2. Chỉ định `--module-source-path` có tự compile mọi module không?**  
Không. Cần chọn modules qua `-m` hoặc chỉ định source files; compiler cũng có thể compile module nguồn phụ thuộc cần thiết.

**3. `-m` của `javac` và `java` có giống chức năng không?**  
Không. Một cái chọn module nguồn compile; cái kia chọn module launch.

**4. Nếu app import đúng `Message` nhưng thiếu `requires`, chuyện gì xảy ra?**  
Import không tạo module read edge. Compiler có thể từ chối truy cập API của module kia; cần descriptor phù hợp.

**5. Thư viện có `exports` nhưng app vẫn báo package không visible, kiểm tra gì?**  
Kiểm tra app có `requires` đúng module, package export đúng tên, kiểu public và không có module khác trùng gây resolution bất thường.

**6. Biên dịch hai module xong, `out` có cấu trúc thế nào?**  
Mỗi module có thư mục `out/<module-name>/` chứa `module-info.class` và cây package/class files.

**7. Vì sao lệnh `java -cp out com.example.app.Main` không tương đương `java -p out -m com.example.app/com.example.app.Main`?**  
`-cp` dùng classpath/unnamed-module lookup; `-p` và `-m` dùng named modules, descriptor và module resolution. Trong ví dụ này, phải dùng module launch.

**8. Có thể dùng `--module-source-path "modules/*/src/main/java"` không?**  
Có khi cây nguồn thực tế nằm tại `modules/<module-name>/src/main/java`. Dấu `*` là placeholder module name.

**9. Module đã compiled được đặt ở `--module-path` có giúp compiler đọc source của module đó không?**  
Không. Module path trỏ tới compiled modules; module source path trỏ tới module sources.

**10. `--release 17` có tác động gì?**  
Đặt mức ngôn ngữ, API Java platform và class-file target tương ứng Java 17 theo hỗ trợ của JDK đang dùng, giúp phát hiện dùng sai tính năng/API mới hơn.

## 15. Tài liệu chính thức

- [Oracle JDK 17: The javac Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html) — mục *The Module Source Path Option*, cấu hình compilation và cách tìm module.
- [Oracle JDK 17: The java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html) — cú pháp khởi chạy named module, `-p` và `-m`.
- [Java Language Specification 17, Chapter 7 — Packages and Modules](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html) — module declarations, `requires`, `exports` và các ràng buộc ngôn ngữ.

**Kết luận:** `--module-source-path` nói cho `javac` **nơi tìm nguồn của từng named module**; `-m` nói **module nào cần compile**; `-d` chứa class files theo module; còn `java --module-path ... -m ...` dùng kết quả đã biên dịch để chạy. Nắm rõ từng vai trò giúp xử lý được cả dự án một module lẫn nhiều module phụ thuộc nhau.
