# Dùng --patch-module trong tình huống có kiểm soát

`--patch-module` là một tùy chọn nâng cao của hệ thống mô-đun Java (JPMS), cho phép **bổ sung hoặc ghi đè nội dung lớp/tài nguyên của một named module đã tồn tại** trong một lần biên dịch hoặc một lần chạy cụ thể. Nó đặc biệt hữu ích khi viết **white-box tests** (kiểm thử bên trong một mô-đun), thử một bản thay thế tạm thời của lớp để chẩn đoán lỗi, hoặc kiểm chứng thay đổi trước khi xây dựng lại mô-đun chính thức.

Điểm mấu chốt: tùy chọn này làm thay đổi **cách công cụ tìm nội dung của mô-đun trong tiến trình đang được cấu hình**. Nó không sửa vĩnh viễn JAR/module gốc, không tự tạo một mô-đun mới và không biến một classpath bất kỳ thành hệ thống mô-đun đúng cấu trúc. Vì patch được ưu tiên khi tìm lớp, lạm dụng có thể che giấu lỗi phiên bản, phá tính tái lập và khiến chương trình chạy khác nhau giữa máy phát triển, CI và production.

Bài thuộc nhóm **Mô-đun Java** của Java Advance – compilation, dùng Java 17 trở lên. Phần thực hành được kiểm tra trên JDK có hỗ trợ `javac --release 17`, tập trung vào một named module do chính chúng ta tạo và một bản vá nằm trong thư mục đầu ra riêng.

## 1. Bối cảnh: mô-đun Java khác package và classpath

Một **named module** khai báo `module-info.java`, có tên mô-đun và những chỉ thị như `requires`, `exports`, `opens`, `uses`, `provides`. Ví dụ:

~~~java
module demo.library {
    exports demo.library.api;
}
~~~

Trong ví dụ này:

- `demo.library` là **tên mô-đun**.
- `demo.library.api` là **package** mà module cho phép module khác truy cập API công khai.
- Package nội bộ không được export vẫn có thể chứa lớp và phương thức, nhưng mã bên ngoài module không được tùy ý sử dụng chúng theo quy tắc JPMS.
- `requires demo.library;` trong một module ứng dụng khai báo quan hệ *readability* giữa hai module.
- `--module-path` chỉ vị trí các module artifact (modular JAR hoặc exploded module directory) để công cụ tìm và giải quyết mô-đun.

Một **classpath** thông thường dùng cho unnamed module, trong khi **module path** cho phép JPMS nhận diện các named modules và kiểm tra boundaries. `--patch-module` tác động vào **một module cụ thể đã có danh tính**, nên cần hiểu rõ module được patch và môi trường giải quyết module.

So sánh:

| Cấu hình | Ý nghĩa | Có thay đổi nội dung nhìn thấy của module? |
|---|---|---|
| `--class-path` hoặc `-cp` | Đường tìm lớp/tài nguyên kiểu classpath | Không phải cơ chế patch named module |
| `--module-path` | Đường tìm các module artifact | Xác định nơi tìm module, không ghi đè từng lớp theo cách patch |
| `--patch-module m=path` | Ghép nội dung từ `path` vào module `m`, ưu tiên nội dung patch | Có, trong quá trình biên dịch/chạy được cấu hình |
| `--add-reads` | Nới quan hệ module readability | Không thay thế bytecode |
| `--add-exports` | Nới khả năng truy cập package cho module khác | Không thay thế bytecode |
| `--add-opens` | Nới quyền truy cập reflection sâu ở runtime | Không thay thế bytecode |

Đây là những cơ chế khác nhau. Dùng `--patch-module` để **đưa nội dung vào module**, và chỉ dùng các tùy chọn bổ sung về `reads/exports/opens` khi chính các ràng buộc tương ứng cần điều chỉnh cho một môi trường kiểm thử có kiểm soát.

## 2. Cú pháp và đường dẫn patch

Cú pháp khái quát của `javac` và `java`:

~~~text
--patch-module <module-name>=<patch-path>
~~~

`<module-name>` là **tên module**, không phải package hay tên JAR. `<patch-path>` là một hoặc nhiều thư mục/JAR được tìm như gốc của cây package, có dấu phân cách đường dẫn theo hệ điều hành:

~~~text
Windows:      --patch-module demo.library="patch-classes;extra-patch.jar"
Linux/macOS:  --patch-module demo.library="patch-classes:extra-patch.jar"
~~~

Ví dụ hai dòng trên chỉ minh họa cú pháp nhiều phần tử; bài thực hành chính dùng một thư mục để giống nhau trên các hệ điều hành.

Quy tắc quan trọng:

1. Mỗi phần tử của patch path phải trỏ tới **gốc cây package**. Nếu tệp là `patch-classes/demo/library/api/Greeting.class`, truyền `patch-classes`, không truyền `patch-classes/demo/library/api`.
2. Patch có thể chứa lớp **mới**, lớp có **cùng tên nhị phân** với lớp gốc để thay thế nó, và tài nguyên. Kiểu khai báo phải phù hợp package/danh tính module và các quy tắc Java khác.
3. Nội dung tìm thấy ở patch path được ưu tiên so với nội dung cùng tên trong module gốc; khi có nhiều phần tử patch path, phần tử xuất hiện trước có thể che nội dung cùng tên ở phần tử sau.
4. Đối với `javac`, chỉ định `--patch-module` tối đa **một lần cho một module** trong một lượt biên dịch; gom nhiều phần tử vào giá trị đường dẫn tương ứng.
5. Vì các đường dẫn tương đối dựa vào working directory của tiến trình, cần chạy từ gốc dự án xác định hoặc truyền đường dẫn đã chuẩn hóa.
6. `--patch-module` không tự lấy nội dung từ mọi file JAR trong một thư mục; chỉ định đúng thư mục chứa cây package hoặc đúng JAR.

Khi patch một module từ nhiều nguồn khác nhau, cần kiểm soát thứ tự các phần tử đường dẫn để tránh lớp trùng tên được chọn ngoài ý muốn. Không dùng thứ tự một danh sách JAR không được quản lý làm cơ chế version selection.

## 3. Khác nhau giữa patch lúc biên dịch và patch lúc chạy

Có **hai tiến trình độc lập**:

- `javac --patch-module demo.library=...`: compiler phân tích nguồn/lớp patch như một phần của module được chỉ định, từ đó có thể biên dịch lớp thử nghiệm cùng package với lớp nội bộ module, hoặc biên dịch một phiên bản thay thế của lớp gốc.
- `java --patch-module demo.library=...`: JVM nạp lớp/tài nguyên patch vào module tương ứng trong tiến trình chạy cụ thể. Đây là thao tác ảnh hưởng đến thực thi.

Dùng patch ở một giai đoạn **không tự động kích hoạt patch ở giai đoạn kia**:

~~~text
              Giai đoạn biên dịch                    Giai đoạn chạy
  module gốc + patch-src --javac--> patch-classes
                                                  |
  module gốc + patch-classes ---------java--------> tiến trình có patch
  module gốc -------------------------java--------> tiến trình nguyên bản
~~~

Ví dụ, sau khi đã tạo bytecode patch, nếu chạy `java` mà **không** truyền `--patch-module`, JVM vẫn dùng nội dung gốc từ module artifact (trừ khi một cấu hình khác đã thay đổi nguồn nội dung).

Điều này giúp tạo các thử nghiệm có phạm vi rõ: cùng một bộ module gốc, chạy **baseline**, **patched run**, rồi **baseline lần nữa** để chứng minh rằng patch không sửa artifact gốc.

## 4. Dự án mẫu gồm hai named modules và một patch riêng

Chúng ta sẽ có:

- `demo.library`: module thư viện, chứa API được export và một lớp nội bộ package-private.
- `demo.app`: module ứng dụng, `requires demo.library` và gọi API công khai.
- `patch-src`: lớp `Greeting` thay thế và `WhiteBoxProbe` mới để quan sát nội bộ.
- `patch-classes`: bytecode riêng của patch, **không phải** bytecode của module gốc.

Cấu trúc thư mục cuối cùng:

~~~text
project/
├── src/
│   ├── demo.library/
│   │   ├── module-info.java
│   │   └── demo/library/
│   │       ├── api/Greeting.java
│   │       └── internal/Secret.java
│   └── demo.app/
│       ├── module-info.java
│       └── demo/app/Main.java
├── patch-src/
│   └── demo/library/
│       ├── api/Greeting.java
│       └── internal/WhiteBoxProbe.java
├── mods/                  # đầu ra biên dịch module gốc
└── patch-classes/         # đầu ra biên dịch patch
~~~

Các đường dẫn dùng dấu `/` tương thích với các lệnh `javac`/`java` được trình bày dưới đây. Cần tạo đúng thư mục nguồn trước khi lưu tệp. Mỗi tên lớp `public` phải trùng tên tệp Java tương ứng.

### 4.1. Module thư viện: module-info.java

Tệp `src/demo.library/module-info.java`:

~~~java
module demo.library {
    exports demo.library.api;
}
~~~

Package `demo.library.api` được export; package `demo.library.internal` không được export. Đó là một điểm mấu chốt để hiểu **white-box testing**.

### 4.2. Module thư viện: API gốc

Tệp `src/demo.library/demo/library/api/Greeting.java`:

~~~java
package demo.library.api;

public final class Greeting {
    public static String message() {
        return "original";
    }
}
~~~

Phương thức `message()` công khai, trả về chữ `original`.

### 4.3. Module thư viện: lớp nội bộ

Tệp `src/demo.library/demo/library/internal/Secret.java`:

~~~java
package demo.library.internal;

final class Secret {
    static String token() {
        return "inside-module";
    }
}
~~~

`Secret` là **top-level class package-private**, phương thức `token()` cũng package-private. Một lớp ở package khác, kể cả cùng module, không thể trực tiếp gọi `Secret.token()` theo quy tắc truy cập Java thông thường.

### 4.4. Module ứng dụng: module-info.java

Tệp `src/demo.app/module-info.java`:

~~~java
module demo.app {
    requires demo.library;
}
~~~

Dòng `requires` cho module ứng dụng quyền đọc `demo.library`; ứng dụng vẫn chỉ có quyền truy cập các package được export thích hợp.

### 4.5. Module ứng dụng: Main.java

Tệp `src/demo.app/demo/app/Main.java`:

~~~java
package demo.app;

import demo.library.api.Greeting;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message());
    }
}
~~~

Đây là chương trình có main đầy đủ. Ứng dụng chỉ sử dụng API công khai của thư viện.

## 5. Biên dịch module gốc và chạy baseline

Mở terminal tại thư mục `project`. Lệnh biên dịch:

~~~sh
javac --release 17 -encoding UTF-8 --module-source-path src -d mods -m demo.library,demo.app
~~~

Giải thích:

- `--module-source-path src` cho biết layout nguồn dạng `src/<module-name>/...`.
- `-m demo.library,demo.app` chọn các module cần biên dịch, không cần liệt kê thủ công từng tệp nguồn.
- `-d mods` lưu các module đã biên dịch dưới `mods/demo.library` và `mods/demo.app`; `javac` tạo đầu ra theo cấu trúc module.
- `--release 17` dùng quy tắc ngôn ngữ và API công khai của Java 17.
- `-encoding UTF-8` giữ mã hóa nguồn nhất quán.

Chạy baseline:

~~~sh
java --module-path mods -m demo.app/demo.app.Main
~~~

Stdout:

~~~text
original
~~~

Trong lệnh chạy, `--module-path mods` cung cấp hai exploded modules; `-m demo.app/demo.app.Main` yêu cầu chạy main class của module `demo.app`. JPMS giải quyết `demo.library` thông qua chỉ thị `requires` của `demo.app`.

**Đây là điểm đối chứng bắt buộc:** trước khi patch, ta cần biết module gốc chạy đúng và in `original`. Nếu baseline đã lỗi, phải sửa cấu trúc hoặc module graph trước khi thử patch.

## 6. Tạo patch ghi đè lớp API gốc

Tạo tệp **`patch-src/demo/library/api/Greeting.java`**:

~~~java
package demo.library.api;

public final class Greeting {
    public static String message() {
        return "patched";
    }
}
~~~

Nó có cùng tên package và cùng tên nhị phân `demo.library.api.Greeting` với lớp gốc; giao diện phương thức `message()` vẫn giữ nguyên, chỉ thay giá trị trả về. Đây là **thay thế hành vi có chủ đích**, không phải cách cập nhật module chính thức.

Compile tệp patch trong bối cảnh module gốc:

~~~sh
javac --release 17 -encoding UTF-8 --module-path mods --patch-module demo.library=patch-src -d patch-classes patch-src/demo/library/api/Greeting.java
~~~

Tạo thư mục `patch-classes` trước khi chạy nếu công cụ/thiết lập của bạn cần thư mục đích tồn tại. Tùy chọn `--module-path mods` giúp `javac` biết module `demo.library` đã biên dịch; `--patch-module demo.library=patch-src` đặt các nguồn patch vào **ngữ cảnh của module đó**; `-d patch-classes` đưa bytecode patch sang thư mục riêng.

Sau khi biên dịch, `patch-classes/demo/library/api/Greeting.class` tồn tại. Không đặt patch class vào `mods/demo.library`: mục tiêu của ví dụ là giữ module gốc nguyên vẹn để so sánh.

Chạy với patch:

~~~sh
java --module-path mods --patch-module demo.library=patch-classes -m demo.app/demo.app.Main
~~~

Stdout chính xác:

~~~text
patched
~~~

Đây là bằng chứng rằng runtime ưu tiên định nghĩa `Greeting` từ patch path. Nếu bỏ `--patch-module` khỏi lệnh chạy:

~~~sh
java --module-path mods -m demo.app/demo.app.Main
~~~

kết quả quay lại:

~~~text
original
~~~

Chạy thử theo thứ tự baseline → patched → baseline đã được kiểm chứng thực tế, với lần biên dịch dùng `javac --release 17`. Hành vi thay đổi chỉ tồn tại ở tiến trình được cấu hình có patch.

## 7. Bổ sung lớp để kiểm thử bên trong module

Một tình huống có kiểm soát khác là **white-box test**: cần kiểm tra hành vi của các thành phần nội bộ nhưng không muốn mở public API hay sửa `exports` của module gốc chỉ để chạy test.

Tạo tệp **`patch-src/demo/library/internal/WhiteBoxProbe.java`**:

~~~java
package demo.library.internal;

public final class WhiteBoxProbe {
    public static void main(String[] args) {
        System.out.println(Secret.token());
    }
}
~~~

`WhiteBoxProbe` được đặt **cùng package** với `Secret`, nên có thể gọi `Secret.token()` nếu được biên dịch và chạy trong cùng module. Không có dòng `import` vì hai lớp cùng package; việc lớp mới có `public` không tự khiến package `demo.library.internal` được export.

Biên dịch patch đầy đủ gồm cả lớp thay thế lẫn lớp probe:

~~~sh
javac --release 17 -encoding UTF-8 --module-path mods --patch-module demo.library=patch-src -d patch-classes patch-src/demo/library/api/Greeting.java patch-src/demo/library/internal/WhiteBoxProbe.java
~~~

Chạy probe trong module đã patch:

~~~sh
java --module-path mods --patch-module demo.library=patch-classes -m demo.library/demo.library.internal.WhiteBoxProbe
~~~

Stdout chính xác:

~~~text
inside-module
~~~

Tại sao hợp lệ?

1. `Secret` và `WhiteBoxProbe` ở cùng package `demo.library.internal`.
2. `WhiteBoxProbe` được **đưa vào module `demo.library`** bằng `--patch-module` lúc compile và run.
3. Package-private access được kiểm tra theo quy tắc package và runtime module tương ứng.
4. Ta không cần thêm `exports demo.library.internal;` vào `module-info.java` gốc chỉ để chạy probe nội bộ.

Trong thực tế, một unit-test framework có thể cần thêm các tùy chọn `--add-reads`/`--add-opens` tùy cách runner, framework và reflection được tổ chức. Bài này dùng `main` trong module đã patch để cô lập cơ chế cơ bản, chưa liên quan tới framework.

### 7.1. Vì sao không chỉ đặt lớp thử nghiệm trên classpath?

Nếu biên dịch `WhiteBoxProbe` như lớp của **unnamed module** rồi cho nó tham chiếu lớp package-private trong named module, ta có các rào cản: package không được export, và kiểu không được khai báo công khai. Việc có cùng chuỗi `package demo.library.internal;` ở nguồn khác module **không đồng nghĩa** cùng runtime package để tự có quyền truy cập.

Với white-box test, patch là cách có chủ đích để test code được xem như một phần của module mục tiêu. Mục tiêu là **giữ tính đóng gói của module trong sản phẩm chính**, còn môi trường test có quyền truy cập cần thiết thông qua cấu hình riêng.

## 8. Đưa patch vào một JAR riêng

Thay vì truyền thư mục `patch-classes`, có thể tạo patch JAR **không có module-info.class riêng**. Tạo thư mục `patches` rồi đóng gói:

~~~sh
jar --create --file patches/library-patch.jar -C patch-classes .
~~~

Với PowerShell có thể tạo thư mục trước bằng:

~~~powershell
New-Item -ItemType Directory -Path patches -Force | Out-Null
~~~

Với Linux/macOS: `mkdir -p patches`.

Chạy:

~~~sh
java --module-path mods --patch-module demo.library=patches/library-patch.jar -m demo.app/demo.app.Main
~~~

Cơ chế tương tự dùng thư mục patch: JVM đọc các lớp ở patch JAR như nội dung của **demo.library**. Patch JAR không cần (và không nên cố) khai báo `module demo.library { ... }` mới; module descriptor của module gốc tiếp tục quyết định danh tính và các ràng buộc mô-đun.

Một JAR nằm trên `--module-path` **khác** với một JAR được đưa vào `--patch-module`. Trong ví dụ này, `library-patch.jar` là **vật chứa nội dung để patch**, không phải module độc lập để `requires`.

Nếu kết quả chạy với JAR khác thư mục patch, hãy kiểm tra đúng entry `demo/library/api/Greeting.class` bằng `jar --list --file patches/library-patch.jar`, cũng như đường dẫn/working directory. Không nên suy rằng việc tạo JAR tự thêm bản patch vào mọi lần chạy.

## 9. Thứ tự ưu tiên và vấn đề class trùng tên

Cơ chế patch ưu tiên nội dung của patch path trước nội dung tương ứng ở module gốc. Nếu có nhiều phần tử được chỉ định cho cùng module, nội dung đầu tiên tìm thấy có thể che các mục cùng tên ở phần tử sau. Ví dụ (chỉ minh họa cú pháp):

~~~text
Windows:
--patch-module demo.library="patch-a;patch-b"

Linux/macOS:
--patch-module demo.library="patch-a:patch-b"
~~~

Nếu cả `patch-a` và `patch-b` chứa `demo/library/api/Greeting.class`, bạn không nên coi chúng như hai bản được kết hợp thành một lớp. Một định nghĩa lớp trùng tên sẽ được tìm trước, còn định nghĩa sau bị che.

Cần lập danh sách rõ **từng lớp/tài nguyên được thêm hoặc thay thế**, tránh tình huống patch chứa một bản `.class` cũ không chủ ý. Có thể kiểm tra:

~~~sh
jar --list --file patches/library-patch.jar
javap -classpath patch-classes demo.library.api.Greeting
~~~

`javap` cho biết cấu trúc/chữ ký lớp trong patch, giúp xác minh bạn đã build đúng class. Muốn xem một phương thức làm gì ở mức bytecode, có thể dùng `javap -c -classpath patch-classes demo.library.api.Greeting`.

Tránh đặt cả nguồn và bytecode không nhất quán ở nhiều patch paths rồi phụ thuộc vào thứ tự ngầm. Hãy chỉ rõ một bản patch mục tiêu, giữ patch output riêng với output sản phẩm và lưu bằng chứng kiểm thử.

## 10. --patch-module không thay module-info hoặc tự thay module graph

Một trong những ranh giới quan trọng nhất là **patch content không đồng nghĩa sửa module descriptor**. Patch không phải API để định nghĩa lại một module bằng cách thay `module-info.class` trong JAR patch, và không tự thêm các chỉ thị `requires`, `exports`, `opens`, `uses`, `provides` vào descriptor của module gốc.

Ví dụ, `demo.library` chỉ export `demo.library.api`. Nếu một module khác muốn trực tiếp import một kiểu trong `demo.library.internal`, việc có `WhiteBoxProbe.class` trong patch **không tự export** package `demo.library.internal` ra ngoài.

### 10.1. Trường hợp cần điều chỉnh readability

Nếu một lớp patch thực sự cần gọi API từ module khác mà `demo.library` **không đọc** theo module graph hiện tại, compiler/runtime có thể từ chối dù bytecode/tệp đã xuất hiện trên module path. Trong kiểm thử chuyên biệt, có thể dùng `--add-reads` thích hợp để mở rộng quan hệ đọc cho module.

Ví dụ khái niệm (không phải lệnh chạy cho dự án ở phần 4 vì dự án này không cần module khác):

~~~text
--add-reads demo.library=some.module
~~~

Điều kiện: `some.module` phải thực sự tồn tại, được resolve phù hợp và các package cần dùng vẫn chịu quy tắc export. **`--add-reads` không tự tạo module hay cấp quyền truy cập mọi package.**

### 10.2. Trường hợp cần export hoặc opens

Nếu một module test **khác module được patch** phải dùng trực tiếp public type của một package chưa export, có thể cần `--add-exports` phù hợp trong cấu hình compile/run test. Nếu framework dùng reflection sâu vào thành viên không public, runtime có thể cần `--add-opens`.

Ví dụ khái niệm:

~~~text
--add-exports demo.library/demo.library.internal=demo.tests
--add-opens demo.library/demo.library.internal=demo.tests
~~~

Trong trường hợp trên, `demo.tests` là một module test giả định đã tồn tại, không có trong dự án mẫu. `--add-exports` không cho phép truy cập trực tiếp một **class package-private** từ package khác bằng cú pháp Java thông thường; nó chỉ thay đổi ranh giới export của package, các quy tắc truy cập thành viên vẫn áp dụng.

`--add-opens` liên quan tới truy cập reflection sâu ở runtime, không tương đương cấp quyền compile-time để import một kiểu bất kỳ.

### 10.3. Patch không biến module chưa tồn tại thành module hợp lệ

Để dùng:

~~~text
--patch-module demo.library=patch-classes
~~~

công cụ phải nhận diện được **module `demo.library`** trong môi trường cấu hình. Đưa một thư mục lớp lên patch path mà không có module mục tiêu không phải cách khai báo named module mới. Hãy kiểm tra module nằm trong `mods`, trên module path phù hợp, hoặc là system module có thật; khi chạy, kiểm tra module có được resolved trong module graph không.

Đối với ứng dụng ví dụ, `demo.app` đã `requires demo.library`, nên module được resolve tự nhiên khi chạy `-m demo.app/...`.

## 11. Rủi ro khi thay lớp có chữ ký không tương thích

Trong bài mẫu, bản patch giữ nguyên:

~~~java
public static String message()
~~~

và chỉ đổi giá trị trả về. Đây là thay đổi có khả năng tương thích với bytecode `demo.app` đã biên dịch.

Nếu patch loại bỏ phương thức, đổi tham số, đổi kiểu trả về trong chữ ký bytecode, chuyển từ `static` sang instance hoặc làm thay đổi các điều kiện truy cập, mã ứng dụng đã biên dịch có thể lỗi khi JVM link/gọi, ví dụ:

- `NoSuchMethodError`: bytecode cần một phương thức mà class thực tế được nạp không còn khai báo/thừa kế phù hợp.
- `NoSuchFieldError`: trường được tham chiếu không còn phù hợp.
- `IncompatibleClassChangeError`: một quan hệ cấu trúc binary bị thay đổi không tương thích.
- `IllegalAccessError`: truy cập bị từ chối khi liên kết.
- `ExceptionInInitializerError` hoặc các lỗi khởi tạo: patch thay đổi hành vi khởi tạo lớp.

Vì vậy patch để thay một implementation phải được kiểm tra **cả API compatibility lẫn runtime behavior**. Đừng chỉ chứng minh lớp patch đã nạp bằng cách nhìn một dòng stdout rồi suy ra mọi consumer đều an toàn.

Ngay cả khi chữ ký không thay đổi, thay đổi semantics (ví dụ phương thức luôn trả `null` thay vì chuỗi) vẫn có thể gây lỗi nghiệp vụ. White-box patch chỉ thích hợp khi thử nghiệm có mục tiêu, đầu ra và điều kiện rollback rõ ràng.

## 12. Patching system modules và giới hạn cần giữ

Cơ chế `--patch-module` cũng có thể xuất hiện trong các bài kiểm thử chuyên biệt về system module, ví dụ một thư viện nền tảng trong môi trường JDK thử nghiệm. Tuy nhiên, **patch system modules như `java.base` có tác động rất rộng**: lớp của JDK được nhiều thành phần khác dùng; thay sai bytecode hoặc xâm phạm giả định của runtime có thể gây lỗi khởi động, lỗi liên kết hoặc hành vi khó dự đoán.

Đối với thực hành và hầu hết ứng dụng:

1. Patch **module do mình sở hữu**, trong một project thử nghiệm có thể tái lập.
2. Không dùng patch để lén thay API nội bộ của JDK trong production.
3. Không coi `--patch-module` là cách chính thức để sửa lỗi thư viện bên thứ ba đã phát hành.
4. Không lấy việc patch chạy được làm bằng chứng rằng một package đã được export hoặc một API nội bộ đã thành hợp đồng public được hỗ trợ.
5. Với library/module thật sự cần sửa lâu dài, thay mã nguồn rồi build và phát hành module/JAR hợp lệ; để dependency management quản lý phiên bản.

Một số cơ chế đặc biệt có giới hạn về định dạng class, quyền truy cập, module resolution và class loading. Hãy dùng tài liệu tương ứng phiên bản JDK đang chạy; không suy luận từ một bài thử đơn giản rằng mọi module, mọi class loader và mọi JDK đều chấp nhận cùng patch.

## 13. Áp dụng cho kiểm thử trong Gradle/Maven/IDE

Trong dự án thực tế, công cụ build có thể tự quản lý cách compile và run các module/test sources. Có nhiều cấu trúc kiểm thử:

- **Black-box tests:** chỉ dùng public API được export của module. Thường không cần `--patch-module`.
- **White-box tests:** test nằm trong package của module mục tiêu, cần nhìn class/member package-private. Có thể dùng `--patch-module` để compiler và JVM coi test code như nội dung của module đích.
- **Reflection-heavy tests:** framework cần truy cập thành viên nội bộ; có thể cần `--add-opens` phù hợp ngoài việc patch.
- **Integration tests:** nên xác minh artifact được đóng gói thực tế **không có test patch** và cấu hình test không bị vô tình áp dụng cho production.

Với Gradle, nhiệm vụ `JavaCompile` và `Test` thường cần cấu hình **riêng** cho compiler arguments và JVM arguments. Chỉ thêm `--patch-module` vào `options.compilerArgs` không đủ để một tiến trình `Test` hay `JavaExec` tự sử dụng patch khi chạy. Ngược lại, runtime JVM arguments không làm `javac` biên dịch nguồn kiểm thử theo ngữ cảnh patch.

Với Maven/IDE, hãy kiểm tra cách plugin hoặc IDE xây dựng module path, classpath, test output, JVM args và cách chọn module launcher; các phiên bản plugin có thể khác nhau. Không nên sao chép một đoạn cấu hình cho mọi dự án rồi bỏ qua output thực tế. Quy trình đáng tin là **in/log đúng lệnh javac và java mà build tool tạo ra**, so sánh chúng với ví dụ thủ công, và chạy test trong CI.

Nếu một framework hoặc plugin đã cung cấp giải pháp white-box testing theo JPMS, hãy dùng đúng tài liệu của công cụ đó. Không thêm `--patch-module` một cách rộng rãi vào mọi task, vì nó có thể che lỗi module boundaries đáng lẽ cần được phát hiện.

## 14. Chẩn đoán các lỗi phổ biến

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| `module not found: demo.library` | Module mục tiêu không có trên module path của giai đoạn tương ứng | Kiểm tra `mods/demo.library/module-info.class`, `--module-path` và tên module |
| Có patch nhưng vẫn in `original` | Chỉ patch lúc compile, quên patch lúc run; sai thư mục gốc hoặc module không được resolve | Kiểm tra lệnh `java --patch-module ...`, class thực có trong patch path |
| `package ... is not visible` | Module chưa đọc module khác hoặc package chưa được export thích hợp | Kiểm tra `requires`, `exports`, chỉ thêm `--add-reads`/`--add-exports` nếu thật sự có lý do |
| `cannot find symbol` khi compile probe | `javac` không nhìn thấy lớp nội bộ gốc hoặc patch source path sai | Kiểm tra `--module-path mods`, `--patch-module demo.library=patch-src`, đường package |
| `IllegalAccessError` lúc chạy | Bytecode được tạo trong bối cảnh quyền khác với runtime; sai class/module hoặc thay API | Dùng cùng cấu hình patch và module access ở compile/run khi cần, đọc stack trace |
| `ClassNotFoundException`/`NoClassDefFoundError` | Lớp patch hoặc dependency không thể tìm/nạp trong runtime graph/class loader | Kiểm tra patch output, module path và dependency runtime |
| `NoSuchMethodError` | Lớp patch thay chữ ký so với consumer đã compile | So binary signature bằng `javap`, tái biên dịch hoặc sửa patch tương thích |
| Chạy từ IDE khác terminal | IDE chọn JDK, module graph hoặc working directory khác | Kiểm tra JVM args, compiler args, toolchain và module output trong IDE |
| Chạy có patch thành công nhưng JAR release sai | Test patch bị đưa vào artifact thật hoặc build dùng output lẫn nhau | Giữ thư mục test/patch riêng; kiểm tra nội dung artifact trước release |

### 14.1. Checklist xác minh bằng lệnh

Sau khi biên dịch dự án mẫu:

~~~sh
java --module-path mods -m demo.app/demo.app.Main
java --module-path mods --patch-module demo.library=patch-classes -m demo.app/demo.app.Main
java --module-path mods -m demo.app/demo.app.Main
~~~

Dự đoán ba dòng từ ba lần chạy riêng biệt:

~~~text
original
patched
original
~~~

Nếu không khớp:

1. `javac -version` và `java -version`: cùng phiên bản JDK mục tiêu phù hợp chưa?
2. `mods/demo.library/module-info.class` và `mods/demo.library/demo/library/api/Greeting.class` tồn tại chứ?
3. `patch-classes/demo/library/api/Greeting.class` có phiên bản patch mới không?
4. `--patch-module` được truyền cho **lệnh java ở lần chạy thứ hai** chưa?
5. Working directory có đúng nơi chứa `mods` và `patch-classes`?
6. Có một patch JAR/thư mục khác che lớp đang thử không?
7. Test được chạy bằng `-m demo.app/demo.app.Main` để chọn named module mong muốn chưa?

Tách từng thay đổi bằng **một điều kiện thử nghiệm** giúp phân biệt lỗi do mã patch với lỗi do module graph, đường dẫn hoặc cache.

## 15. Những hiểu nhầm cần tránh

**“Patch có nghĩa sửa trực tiếp file JAR gốc.”** Không. Cơ chế patch thay đổi nội dung được nhìn thấy trong quá trình tìm lớp của môi trường được cấu hình; nếu lệnh chạy bỏ patch, bản gốc vẫn được dùng.

**“Có patch class trên ổ đĩa thì java tự dùng.”** Không. Phải truyền đúng `--patch-module module=path` cho runtime (hoặc một cơ chế cấu hình tương đương của môi trường chạy).

**“Chỉ patch lúc chạy là đủ để compile test truy cập package-private.”** Không. Compile test cũng phải được cấu hình đúng để `javac` hiểu test thuộc module nào.

**“Patch tự thay requires và exports.”** Không. Module descriptor của module chính vẫn quyết định module graph/public surface; có thể cần các tùy chọn nới quyền riêng theo từng tình huống kiểm thử.

**“--patch-module có thể tạo một module tên bất kỳ.”** Không. Module mục tiêu phải có danh tính và được tìm/resolve trong môi trường phù hợp.

**“Có thể dùng patch thay hẳn dependency management.”** Không. Patch chỉ là cơ chế ghi đè/bổ sung có kiểm soát; dependency versions, API compatibility và artifact publishing vẫn phải được quản lý.

**“Lớp nằm cùng package chữ viết thì chắc chắn có quyền package-private.”** Không. Trong ứng dụng JPMS, runtime package/module identity và cách lớp được nạp rất quan trọng. Đặt test code vào chính module qua patch là khác với tạo một package trùng tên trong unnamed module.

## 16. Bài tập thực hành

### Bài 1 — Phân biệt compile patch và runtime patch

Biên dịch `Greeting` patch bằng `javac --patch-module`. Chạy `demo.app` hai lần, lần đầu không patch runtime, lần sau có patch runtime. Giải thích vì sao chỉ có lần sau in `patched`.

### Bài 2 — White-box test và ranh giới module

Biên dịch/chạy `WhiteBoxProbe` như phần 7 để truy cập `Secret.token()`. Sau đó thử viết một module khác có `import demo.library.internal.Secret;` mà không sửa module descriptor. Dự đoán vì sao `Secret` vẫn không trở thành API công khai: package chưa export, class còn package-private.

### Bài 3 — Patch JAR

Đóng gói `patch-classes` thành `patches/library-patch.jar`; kiểm tra nội dung bằng `jar --list --file`. Dùng JAR đó làm patch path thay cho thư mục. Chứng minh ứng dụng vẫn in `patched`, trong khi lệnh không patch lại in `original`.

### Bài 4 — Binary compatibility

Đổi signature của `Greeting.message()` trong patch thành `Greeting.message(String value)` mà không giữ overload cũ. Biên dịch patch nhưng **không** biên dịch lại module ứng dụng. Dự đoán khả năng xảy ra `NoSuchMethodError` khi ứng dụng chạy với patch, rồi khôi phục signature phù hợp. Bài tập nên làm trong project thử nghiệm vì bytecode consumer được tạo theo API gốc.

### Bài 5 — Quy trình thử nghiệm an toàn

Giả sử một unit test cần nhìn package-private method của module thư viện. Hãy mô tả các bước: tạo patch source riêng, compile đúng module, chạy test với patch, kiểm tra output và loại patch khỏi artifact production. Giải thích khi nào thêm `--add-reads` hoặc `--add-opens` là có lý do thực tế và khi nào không cần.

## 17. Checklist quyết định có dùng --patch-module hay không

Trước khi dùng, cần xác nhận:

- **Mục đích**: white-box test, chẩn đoán một lớp, hoặc thử nghiệm tương thích trong môi trường có kiểm soát.
- **Module mục tiêu**: named module nào, tìm ở đâu, có được resolve khi chạy không?
- **Phạm vi patch**: lớp/tài nguyên nào được thêm hoặc thay thế? Có tên trùng hoặc dữ liệu lỗi thời không?
- **Đường dẫn**: patch path có trỏ tới gốc cây package, đúng hệ điều hành và working directory không?
- **Hai giai đoạn**: có cần cấu hình cả `javac` và `java` không? Build tool/IDE có truyền đúng cho từng tiến trình không?
- **Quyền truy cập**: `requires`, `exports`, `opens` hiện tại có đủ cho test không? Có đang vô tình làm rộng quyền của môi trường sản phẩm không?
- **Tương thích**: chữ ký bytecode/behavior có phù hợp với consumer đã compile không?
- **Kiểm chứng**: baseline → patched → baseline có chứng minh được tác động đúng phạm vi không?
- **Cô lập**: patch classes/JAR có nằm ngoài output và bản phát hành chính không?
- **Gỡ bỏ**: bỏ JVM/compiler patch option có khôi phục được hành vi nguyên bản không?

Với ứng dụng JPMS, **`--patch-module` là công cụ can thiệp có chọn lọc vào nội dung của một module đã tồn tại**. Hãy xem nó là khả năng phục vụ thử nghiệm và chẩn đoán có bằng chứng cụ thể, không phải phương án thay thế việc thiết kế public API, cấu hình dependency hoặc phát hành module đúng chuẩn.

## 18. Tài liệu chính thức để tự đối chiếu

- Oracle Java SE 17, *The javac Command*, mục **Patching Modules**: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- Oracle Java SE 17, *The java Command*, mô tả `--patch-module`, `--add-reads`, `--add-exports`, `--add-opens`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Java Platform Module System, JEP 261: https://openjdk.org/jeps/261

Khi có khác biệt giữa IDE, phiên bản JDK hoặc cách gọi module launcher, hãy kiểm tra **lệnh compiler/runtime thực tế** và tài liệu tương ứng với JDK đang dùng.