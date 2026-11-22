# Khi nào dùng --add-modules, --add-reads và --add-exports trong Java

Khi làm việc với Java Platform Module System (JPMS, từ Java 9), việc một class có mặt trên máy **chưa đủ** để một class khác sử dụng được nó. Module chứa class ấy phải được đưa vào **đồ thị module đã phân giải**; module đang gọi phải **đọc được** module chứa class; và package chứa kiểu cần dùng phải **được export** cho module gọi. Ba cờ `--add-modules`, `--add-reads` và `--add-exports` giải quyết **ba vấn đề khác nhau**.

Bài học này giải thích chính xác khi nào dùng từng cờ ở lệnh `javac` và `java`, cách kiểm tra lỗi thường gặp, cũng như vì sao một bản sửa chỉ ở lúc biên dịch có thể vẫn lỗi lúc chạy. Các ví dụ tối giản dùng cú pháp Java 17+ và được thiết kế để có thể tạo tệp, biên dịch, chạy độc lập. Các lệnh shell trong ví dụ dùng **Bash trên Linux/macOS** từ thư mục dự án; Windows PowerShell cần tạo thư mục bằng lệnh tương đương và dùng đúng dấu phân cách đường dẫn nếu có danh sách nhiều mục.

## 1. Ba điều kiện để sử dụng một kiểu thuộc named module khác

Hãy hình dung chương trình ở `demo.app` muốn dùng lớp public `Library` trong package `demo.lib.internal` của module `demo.lib`:

~~~text
Tập module quan sát được (JDK image, module path)
                    │
                    ▼
        Module resolution (root + requires)
                    │
          demo.lib đã resolved?
                    │
          ┌─────────┴──────────┐
          │                    │
        Chưa                  Rồi
          │                    │
     --add-modules            ▼
                     demo.app đọc demo.lib?
                                │
                      ┌─────────┴────────┐
                      │                  │
                     Chưa               Rồi
                      │                  │
                  --add-reads            ▼
                                 Package được export
                                 cho demo.app?
                                        │
                              ┌─────────┴─────────┐
                              │                   │
                             Chưa                 Rồi
                              │                   │
                         --add-exports       Kiểm tra tiếp
                                             public/access
~~~

Đây là sơ đồ để suy nghĩ khi chẩn đoán, **không phải công thức phải thêm cả ba cờ**. Thông thường `module-info.java` đã khai báo `requires` và `exports` đúng nên **không cần cờ nào**. Không phải mọi lỗi đòi đúng một cờ: thiếu dependency trên module path, package/private member hoặc split package còn có nguyên nhân riêng.

Các khái niệm nền tảng:

- **Observable module:** module mà compiler hoặc launcher có thể phát hiện từ JDK image/module path; *observable* không tự động có nghĩa *resolved*.
- **Root module:** điểm khởi đầu của giải thuật resolution; tập `requires` của các root và phụ thuộc tiếp theo quyết định những module nào vào graph.
- **Readability edge:** quan hệ có hướng `A → B` cho phép module `A` đọc các kiểu mà `B` export cho `A`.
- **Exports:** module `B` công bố một package cho mọi module (unqualified export) hoặc cho một tập module được chọn (qualified export). `public` trên class vẫn chưa đủ nếu package chưa được export.
- **Unnamed module:** mã trên classpath thuộc unnamed module, không có tên để dùng ở vị trí named target; ký hiệu đặc biệt `ALL-UNNAMED` được dùng ở một số option.

Ở named module chuẩn, `requires demo.lib;` trong `demo.app/module-info.java` thông thường vừa làm `demo.lib` được resolve theo dependency vừa tạo readability edge. Nếu `demo.lib` đã `exports demo.lib.api;`, mã `demo.app` có thể dùng các public type trong `demo.lib.api` mà không cần sửa dòng lệnh.

## 2. Bảng quyết định nhanh

| Cờ | Thay đổi gì? | Khi nào hữu ích? | Cờ không làm được gì? |
| --- | --- | --- | --- |
| `--add-modules M` | Thêm `M` vào các root module cần resolve | Code trên classpath cần module nằm trên module path; module tùy chọn chưa được resolve; tool/test harness | Không tự cấp `exports` cho package nội bộ; không tự tạo cạnh `A đọc B` cho mọi named module |
| `--add-reads A=B` | Thêm readability edge `A → B` | Named module `A` tạm cần dùng API mà descriptor chưa khai `requires B`; test và migration | Không export package của `B`; không thay một dependency/JAR không có mặt |
| `--add-exports B/p=A` | Cho `B` export package `p` tới `A` ở compile/runtime theo lệnh | White-box test, công cụ cũ cần public type thuộc package không export | Không cho quyền truy cập member `private`; không mở deep reflection; không tự thêm `requires` |
| `--add-opens B/p=A` | Mở package để deep reflection ở runtime | Framework reflection cần truy cập non-public members | Không phải giải pháp chung cho lệnh import kiểu không export trong mã Java |

Hãy đọc **phần tên bên trái dấu `=`** thật kỹ:

- `--add-reads A=B`: **A đọc B**; chiều là từ consumer sang provider.
- `--add-exports B/p=A`: **B export p cho A**; chiều là từ provider sang consumer.
- `--add-modules B`: **B được thêm làm root để resolve**, không có tên package hay target consumer.

Một module có thể có mặt và được đọc, nhưng vẫn không truy cập được package internal. Ngược lại, một package đã được export cho `A` nhưng `A` chưa đọc module sở hữu thì khả năng truy cập vẫn chưa hoàn chỉnh. Đó là lý do không nên xem các cờ như những “mức độ mở khóa” có thể thay thế lẫn nhau.

## 3. Cú pháp chính xác của ba cờ

### 3.1. --add-modules

~~~text
--add-modules module1,module2
--add-modules=module1,module2
--add-modules ALL-MODULE-PATH
~~~

Danh sách tên module dùng dấu **phẩy**, không dùng dấu phân cách classpath. `ALL-MODULE-PATH` có nghĩa là thêm các module trên module path làm root. Ở launcher `java` còn có các giá trị đặc biệt `ALL-DEFAULT` và `ALL-SYSTEM` cho các tình huống khởi chạy/test chuyên biệt. Không nên dùng `ALL-SYSTEM` thường xuyên vì mở rộng graph quá mức cần thiết; và không suy đoán mọi giá trị đặc biệt của launcher đều có cùng ngữ nghĩa/khả dụng khi dùng `javac`.

### 3.2. --add-reads

~~~text
--add-reads consumer.module=provider.module
--add-reads=consumer.module=provider.module
--add-reads consumer.module=first.module,second.module
--add-reads consumer.module=ALL-UNNAMED
~~~

`consumer.module` là module cần bổ sung cạnh đọc. Danh sách bên phải là những module đích. `ALL-UNNAMED` cho phép named module đọc mã ở các unnamed modules, thường dùng trong thử nghiệm/migration khi thư viện vẫn còn trên classpath.

### 3.3. --add-exports

~~~text
--add-exports provider.module/provider.pkg=consumer.module
--add-exports=provider.module/provider.pkg=consumer.module
--add-exports provider.module/provider.pkg=first.module,second.module
--add-exports provider.module/provider.pkg=ALL-UNNAMED
~~~

`provider.pkg` là **package** bên trong `provider.module`, không phải một class. Dùng `/` giữa tên module và tên package; không đặt class name sau `/`. `ALL-UNNAMED` cho phép **mọi unnamed module** nhìn thấy những public type trong package được export, miễn các điều kiện khả năng truy cập khác đã thỏa.

Cả ba cờ cần được đặt **trước tên main class hoặc `-m` cùng tham số khởi chạy phù hợp** khi dùng `java`. Chúng là **option của công cụ**, không phải tham số `String[] args` truyền cho `main`. Các lệnh `javac` cũng đặt cờ cùng với source/module path và thư mục output theo cú pháp công cụ.

## 4. --add-modules: module có mặt nhưng chưa được đưa vào graph

Tình huống thường gặp: ứng dụng **classpath** sử dụng một **named module** trên module path. Đặt JAR hoặc thư mục module lên `--module-path` chỉ làm nó *observable*; với ứng dụng chạy bằng classpath, những module trên module path thường **chưa phải root**, nên cần `--add-modules`.

### Ví dụ đầy đủ: một library module và ứng dụng classpath

Tạo cấu trúc:

~~~text
project/
├── src/
│   ├── library/
│   │   ├── module-info.java
│   │   └── demo/greet/api/Greeter.java
│   └── classic/
│       └── Main.java
├── mods/               (sinh khi build)
└── out/                (sinh khi build)
~~~

**`src/library/module-info.java`**

~~~java
module demo.greeter {
    exports demo.greet.api;
}
~~~

**`src/library/demo/greet/api/Greeter.java`**

~~~java
package demo.greet.api;

public final class Greeter {
    private Greeter() {
    }

    public static String message() {
        return "Hello from module";
    }
}
~~~

**`src/classic/Main.java`**

~~~java
import demo.greet.api.Greeter;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.message());
    }
}
~~~

Từ thư mục `project`, lệnh Bash:

~~~bash
mkdir -p mods/demo.greeter out
javac -d mods/demo.greeter src/library/module-info.java src/library/demo/greet/api/Greeter.java
javac --module-path mods --add-modules demo.greeter -d out src/classic/Main.java
java --module-path mods --add-modules demo.greeter -cp out Main
~~~

Stdout từ lệnh chạy cuối:

~~~text
Hello from module
~~~

Vì sao các lệnh có hiệu lực?

1. `javac -d mods/demo.greeter ...` tạo class files cho named module `demo.greeter`; module descriptor đặt ở output root của module.
2. `--module-path mods` làm module `demo.greeter` *observable* cho lời gọi compiler và runtime.
3. `--add-modules demo.greeter` thêm module này vào graph. Vì `Main` là code **unnamed module**, nó đọc các named modules đã resolved và có thể dùng public class trong package `demo.greet.api` được export không giới hạn.
4. Cờ có ở **cả lời gọi `javac` lẫn `java`** để compiler phân giải được kiểu và runtime có graph phù hợp.

Nếu chỉ đưa `--module-path mods` nhưng bỏ `--add-modules demo.greeter`, `Main` thông thường không thấy module tự tạo ấy trong graph khi biên dịch; lúc chạy cũng có thể gặp lỗi tìm lớp. Tên diagnostic khác nhau theo bối cảnh, nhưng nguyên nhân là **module chưa được resolve**, không phải thiếu `public`.

### Khi có thể không cần --add-modules

Nếu `Main` nằm trong named module `demo.app` có `requires demo.greeter;`, resolution từ root `demo.app` thường sẽ tự đưa `demo.greeter` vào graph. Khi đó thêm `--add-modules demo.greeter` thường không giải quyết vấn đề gì mới.

Lựa chọn tốt nhất là khai báo dependency cố định bằng `requires` trong `module-info.java` thay vì dùng cờ tạm. Chỉ dùng `--add-modules` có chủ đích khi muốn đưa thêm root vào graph mà descriptor hoặc chế độ khởi chạy mặc định chưa làm điều đó.

## 5. --add-reads: module cần đọc một module khác dù descriptor chưa requires

Với named modules, compiler kiểm tra readability. Một module `A` không tự động đọc mọi module khác chỉ vì tất cả nằm trên module path. `--add-reads A=B` thêm cạnh `A → B` trong module graph tại quá trình biên dịch hoặc chạy tùy nơi dùng cờ.

### Ví dụ đầy đủ với module java.sql

Ví dụ tránh phụ thuộc thư viện ngoài, dùng module chuẩn `java.sql` và một named module của ứng dụng không khai `requires java.sql`.

Cấu trúc:

~~~text
project/
└── src/
    └── read/
        ├── module-info.java
        └── demo/read/Main.java
~~~

**`src/read/module-info.java`**

~~~java
module demo.read {
}
~~~

**`src/read/demo/read/Main.java`**

~~~java
package demo.read;

import java.sql.DriverManager;

public class Main {
    public static void main(String[] args) {
        System.out.println(DriverManager.class.getModule().getName());
    }
}
~~~

Lệnh Bash:

~~~bash
mkdir -p mods/demo.read
javac --add-modules java.sql --add-reads demo.read=java.sql -d mods/demo.read src/read/module-info.java src/read/demo/read/Main.java
java --module-path mods --add-modules java.sql --add-reads demo.read=java.sql -m demo.read/demo.read.Main
~~~

Stdout từ lệnh cuối:

~~~text
java.sql
~~~

`--add-modules java.sql` đảm bảo `java.sql` được thêm làm root để resolve trong ví dụ khi `demo.read` không `requires` nó; `--add-reads demo.read=java.sql` cho phép `demo.read` đọc package public đã export của `java.sql`.

Nếu **bỏ riêng `--add-reads`** lúc biên dịch, compiler có thể báo rằng package `java.sql` không visible vì `demo.read` không đọc `java.sql`, ngay cả khi `java.sql` đã resolved. Nếu chỉ cung cấp cờ lúc compile nhưng bỏ lúc chạy, dependency còn chưa được thiết lập đúng theo graph runtime; khi truy cập kiểu liên quan sẽ có nguy cơ lỗi linkage/access.

Giải pháp bền vững là sửa descriptor thành:

~~~java
module demo.read {
    requires java.sql;
}
~~~

Với descriptor đúng và module `java.sql` hiện diện, có thể biên dịch và chạy bằng:

~~~bash
javac -d mods/demo.read src/read/module-info.java src/read/demo/read/Main.java
java --module-path mods -m demo.read/demo.read.Main
~~~

Không cần `--add-modules` hoặc `--add-reads` ở ví dụ này vì `requires` giải quyết cả dependency resolution và readability. **Đây là cách nên dùng khi thực sự phụ thuộc cố định vào `java.sql`.** Cờ `--add-reads` phù hợp hơn cho white-box testing, migration hoặc cấu hình thực nghiệm không thể/không nên sửa `module-info.java` ngay.

### Khi nào dùng =ALL-UNNAMED?

Một module đã được đặt trên module path nhưng vẫn cần dùng thư viện legacy **trên classpath** trong giai đoạn migration. Cờ:

~~~text
--add-reads demo.read=ALL-UNNAMED
~~~

bổ sung cạnh đọc tới các unnamed modules (phía classpath). Nó **không tự chuyển JAR classpath thành named module** và không giải quyết việc tìm class nếu `-cp` sai. Đây là cầu nối tạm khi modularization chưa hoàn tất; nếu library có thể trở thành named/automatic module phù hợp thì nên cải thiện cấu trúc phụ thuộc.

## 6. --add-exports: cho phép public type trong package chưa export

Named module có thể khai báo public class nhưng **không export** package chứa class. Mã ở module khác không được truy cập kiểu đó bằng lối truy cập thông thường. Cờ `--add-exports B/p=A` cho phép `B` coi package `p` là đã export bổ sung cho `A` tại lời gọi công cụ được chỉ định.

### Ví dụ đầy đủ: internal package được mở có giới hạn cho module thử nghiệm

Cấu trúc:

~~~text
project/
├── src/
│   ├── lib/
│   │   ├── module-info.java
│   │   └── demo/lib/internal/Secret.java
│   └── use/
│       ├── module-info.java
│       └── demo/use/Main.java
└── mods/                 (sinh khi build)
~~~

**`src/lib/module-info.java`**

~~~java
module demo.lib {
    // Không export demo.lib.internal
}
~~~

**`src/lib/demo/lib/internal/Secret.java`**

~~~java
package demo.lib.internal;

public final class Secret {
    private Secret() {
    }

    public static String message() {
        return "internal: allowed";
    }
}
~~~

**`src/use/module-info.java`**

~~~java
module demo.use {
    requires demo.lib;
}
~~~

**`src/use/demo/use/Main.java`**

~~~java
package demo.use;

import demo.lib.internal.Secret;

public class Main {
    public static void main(String[] args) {
        System.out.println(Secret.message());
    }
}
~~~

Lệnh Bash:

~~~bash
mkdir -p mods/demo.lib mods/demo.use
javac -d mods/demo.lib src/lib/module-info.java src/lib/demo/lib/internal/Secret.java
javac --module-path mods --add-exports demo.lib/demo.lib.internal=demo.use -d mods/demo.use src/use/module-info.java src/use/demo/use/Main.java
java --module-path mods --add-exports demo.lib/demo.lib.internal=demo.use -m demo.use/demo.use.Main
~~~

Stdout cuối:

~~~text
internal: allowed
~~~

Ở đây:

- `demo.use` **đã đọc** `demo.lib` vì descriptor có `requires demo.lib`.
- `demo.lib` **đã resolved** theo dependency đó.
- Phần thiếu là `demo.lib.internal` **không export**. Cờ `--add-exports` bổ sung đúng khả năng truy cập này cho `demo.use`.
- Nếu bỏ cờ khỏi lệnh `javac`, `import demo.lib.internal.Secret` bị từ chối vì package không được export.
- Nếu đã biên dịch bằng cờ mà bỏ cờ tương ứng lúc `java` chạy, JVM có thể ném `IllegalAccessError` khi truy cập class trong package chưa được export ở runtime.

Cờ này không làm `private` field/method truy cập được từ bên ngoài class: `Secret.message()` là `public` nên sau khi module access hợp lệ nó mới được phép gọi. `--add-exports` chỉ tác động **module-level package export**, không làm biến mất access modifiers của ngôn ngữ.

### Vì sao không luôn sửa module-info.java thành exports?

Nếu `demo.lib.internal` là API nội bộ, export vô điều kiện sẽ tăng bề mặt public API và có thể khiến mã ứng dụng lệ thuộc implementation detail. Với white-box tests, đôi khi chỉ cần tạm mở package cho module test. Với dependency production thực sự, giải pháp tốt hơn thường là chuyển tính năng cần dùng sang public API được export một cách chủ đích.

Đừng sử dụng cờ mở package chỉ để che giấu việc project định nghĩa sai ranh giới module.

## 7. Khi cần dùng đồng thời nhiều cờ

Một lỗi JPMS có thể chứa **nhiều điều kiện độc lập chưa thỏa**. Ví dụ trong bối cảnh `demo.app` chưa khai `requires demo.lib`, còn class cần dùng nằm trong `demo.lib.internal` không được export:

~~~text
--add-modules demo.lib
--add-reads demo.app=demo.lib
--add-exports demo.lib/demo.lib.internal=demo.app
~~~

Khi phải cấu hình tạm bằng CLI, ba option trên lần lượt:

1. Đảm bảo `demo.lib` có mặt trong graph.
2. Tạo cạnh `demo.app → demo.lib`.
3. Cho `demo.lib` export package `demo.lib.internal` riêng tới `demo.app`.

Đoạn trên là **mẫu tổ hợp theo tình huống**, không phải một chương trình riêng có thể chạy. Chỉ cần hai hoặc một cờ nếu phần còn lại đã được descriptor/module graph đáp ứng. Tránh “bắn cả ba option” với các tên module mơ hồ: điều đó làm cấu hình khó kiểm toán và dễ quên khi triển khai.

Một nguyên tắc hữu ích để debug:

~~~text
Không tìm thấy module?
  └── Kiểm tra --module-path và module resolution/--add-modules.

Module có trong graph nhưng 'does not read'?
  └── Kiểm tra requires hoặc --add-reads theo đúng chiều.

Đã đọc module nhưng 'package ... is not visible/does not export'?
  └── Kiểm tra exports hoặc --add-exports.

Accessing private member / reflective access?
  └── Kiểm tra access modifier hoặc --add-opens cho deep reflection.
~~~

Nếu lỗi do JAR không có trên module path, các cờ graph không thể tự tạo ra JAR. Nếu hai module có package trùng nhau trong những cấu hình không hợp lệ, thêm export/reads cũng không phải cách sửa split-package problem.

## 8. Phân biệt tác dụng ở lúc biên dịch và lúc chạy

Có **hai tiến trình và hai cấu hình** quan trọng:

| Giai đoạn | Công cụ | Cần kiểm tra |
| --- | --- | --- |
| Biên dịch source | `javac` | Tên module được resolve, readability, exports đối với các kiểu trong mã nguồn |
| Chạy class đã biên dịch | `java` launcher / JVM | Runtime graph, module path, readability, exports của class được nạp |

Mở package bằng `--add-exports` khi biên dịch chỉ đảm bảo compiler **được phép tạo class file tham chiếu** tới class đó. Runtime vẫn phải có quyền tương ứng nếu descriptor chưa export. Tương tự, một cạnh `--add-reads` lúc biên dịch không tự được lưu vào `module-info.class` như một `requires` mới để mọi lệnh `java` lần sau áp dụng.

Điều này giải thích tình huống hay gặp: build thành công vì IDE/Gradle tự thêm flags ở compiler, nhưng chạy `java` từ terminal gặp `IllegalAccessError` hoặc lỗi module. Cần kiểm tra **lệnh `java` thực tế** do build, test runner, IDE hoặc container khởi động.

Có một số trường hợp compiler/launcher tự truyền các cấu hình đặc biệt (như source-file mode), nhưng không nên dựa vào đó để suy luận chung rằng các cờ compile-time luôn di chuyển sang runtime.

**Lưu ý với `--release`:** nếu dùng `javac --release`, nhất là khi cố export package nội bộ của *system module* như `java.base`, các hạn chế tương thích release có thể khiến tổ hợp option bị từ chối. Không mặc định một lệnh khai thác JDK internals sẽ chạy được với mọi `--release`. Hãy xem `javac --help`, `javac --help-extra` của JDK đang dùng và chọn public APIs thay thế nếu có.

## 9. Ba cờ khác những khái niệm dễ nhầm

### 9.1. --module-path khác --class-path

`--module-path` (`-p`) cho công cụ biết nơi tìm **named modules/automatic modules**. `--class-path` (`-cp`) là nơi tìm mã thuộc unnamed module. Đặt một plain JAR không có `module-info.class` lên module path có thể biến nó thành **automatic module** với tên và quy tắc đặc biệt. Cùng JAR trên classpath thuộc unnamed module, không có module name để dùng với `--add-modules my.jar`.

Đừng suy luận module name từ tên JAR mà chưa kiểm chứng. Có thể dùng `jar --describe-module --file library.jar` hoặc công cụ liệt kê module phù hợp. Một automatic module có thể lấy tên từ manifest `Automatic-Module-Name` hoặc suy ra từ tên tệp JAR.

### 9.2. --add-exports khác --add-opens

- `--add-exports B/p=A` mở quyền truy cập **compile/link-time** tới các kiểu/members public trong package `p` của `B` cho `A` (khi các điều kiện đọc, public/access khác hợp lệ).
- `--add-opens B/p=A` mở package của `B` để mã ở `A` có thể thực hiện **deep reflection** ở runtime, chẳng hạn truy cập non-public members bằng `setAccessible` khi có quyền phù hợp.
- `opens` không thay `exports` như một cờ compiler thông thường để import và gọi public internal API. Ngược lại, `exports` không tự cho phép reflection vào trường `private`.

Khi chương trình gặp `InaccessibleObjectException` từ reflection, kiểm tra `opens`/`--add-opens`, phiên bản JDK và quyền reflection. Khi compiler báo package chưa export, kiểm tra `exports`/`--add-exports`. Hai lỗi khác tầng không nên sửa bằng cùng một cờ.

### 9.3. --add-reads khác --patch-module

`--patch-module module=path` dùng để bổ sung/thay thế các class/resource thuộc một module tại build/runtime theo cơ chế patch, thường gặp ở white-box tests. Nó không đồng nghĩa với việc cho module đọc thêm module khác. Đối với test cần truy cập internal package, có thể phải phối hợp `--patch-module`, `--add-reads` và `--add-exports` tùy cách test được đặt trong module.

### 9.4. --add-modules khác --limit-modules

`--add-modules` bổ sung root modules; `--limit-modules` thu hẹp tập module có thể quan sát trong một cấu hình. Nếu module bị loại khỏi universe bởi `--limit-modules` hoặc runtime image thiếu nó, chỉ thêm tên qua `--add-modules` không thể bảo đảm resolution thành công.

## 10. Các giá trị đặc biệt và khi nên tránh mở quá rộng

| Giá trị | Dùng cùng | Ý nghĩa |
| --- | --- | --- |
| `ALL-MODULE-PATH` | `--add-modules` | Làm root mọi module quan sát được từ module path, hữu ích trong build tools/automatic modules |
| `ALL-DEFAULT` | `--add-modules` của launcher `java` | Root set mặc định cho ứng dụng classpath trong cấu hình runtime đó |
| `ALL-SYSTEM` | `--add-modules` của launcher `java` | Root toàn bộ system modules; thường cho test harness/trường hợp đặc biệt |
| `ALL-UNNAMED` | Phía phải `--add-reads` hoặc `--add-exports` | Nhắm tới các unnamed modules, thường gắn với classpath |

Ví dụ một công cụ cần nạp nhiều plugin đặt dưới module path:

~~~bash
java --module-path plugins --add-modules ALL-MODULE-PATH -cp out Host
~~~

Đây là **mẫu lệnh**, chỉ hoạt động khi các module trong `plugins` hợp lệ và `Host`/dependencies hiện diện. Không nên dùng `ALL-MODULE-PATH` vô điều kiện vì có thể kéo vào graph các module không mong muốn và phơi bày xung đột phiên bản/package. Nếu biết rõ module cần thiết, nêu tên cụ thể thường minh bạch hơn.

`ALL-UNNAMED` trong `--add-exports java.base/sun.nio.ch=ALL-UNNAMED` là ví dụ cú pháp cho legacy code classpath cần một package JDK nội bộ. Việc dựa vào các package nội bộ có thể không tương thích các bản Java mới; đây **không phải cấu hình khuyến nghị cho code production**. Đừng đưa cờ này vào mọi ứng dụng chỉ để “chắc ăn”.

## 11. Lỗi thường gặp và cách sửa đúng vấn đề

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| `module not found: demo.lib` | Sai `--module-path`, module name hoặc module artifact không tồn tại | Kiểm tra output `module-info.class`, `jar --describe-module`, đường dẫn |
| `package ... is not visible (not in the module graph)` | Named module trên module path nhưng chưa được resolve | Kiểm tra `requires` hoặc `--add-modules` |
| `module demo.app does not read demo.lib` | Thiếu readability edge | `requires demo.lib` hoặc tạm `--add-reads demo.app=demo.lib` |
| `package ... is not visible (does not export ...)` | Module provider không export package | Dùng public API/`exports` hoặc cờ tạm `--add-exports` |
| `IllegalAccessError` khi chạy sau compile thành công | Runtime graph/export khác compiler graph/export | Đưa đúng flags vào JVM launcher hoặc sửa descriptors |
| `InaccessibleObjectException` khi reflection | Package chưa open cho deep reflection | Kiểm tra `opens` / `--add-opens` ở runtime |
| `NoClassDefFoundError`/`ClassNotFoundException` | Thiếu class/runtime dependency hoặc module chưa resolve | Kiểm tra `-cp`, `--module-path`, root module, runtime image |
| Cờ `--add-exports` “không mở private” | Module export không thay Java access modifiers | Sửa API/kiểm soát reflection đúng cơ chế |
| Cờ không có tác dụng khi chạy IDE/test | Flags chỉ đặt cho compiler, chưa đặt cho test JVM/launcher | Kiểm tra cả compile và test runtime configuration |

Đừng đọc thông báo lỗi theo một từ khóa duy nhất: cùng kiểu “package not visible” có thể do thiếu resolution, readability hoặc export. Xem toàn bộ diagnostic, tên module được nhắc đến và cách tool build cung cấp module path.

## 12. Quy trình chẩn đoán từng bước

1. **Xác định nơi chứa class cần dùng**: classpath (unnamed module), JDK system module, named module JAR hay automatic module trên module path?
2. **Xác nhận module name** bằng `java --list-modules` cho runtime image khi phù hợp, hoặc `jar --describe-module --file path/to/library.jar` cho JAR. Lệnh `java --list-modules` mặc định liệt kê các module runtime image; đừng coi nó là danh sách đầy đủ mọi plugin JAR đặt ngoài image.
3. **Kiểm tra observability**: `--module-path` có trỏ đúng module artifact không? Artifact có `module-info.class` hoặc tên automatic module như dự đoán không?
4. **Kiểm tra resolution**: module provider có vào graph từ root/`requires` hay cần `--add-modules`?
5. **Kiểm tra readability**: module consumer có `requires`/readability edge tới provider không, hay chỉ có trên module path?
6. **Kiểm tra exports**: package provider có `exports p` hoặc `exports p to A` không? Nếu không, có thực sự cần public internal class cho test/migration không?
7. **Kiểm tra runtime tương ứng**: chạy lại với module path, module flags và JVM đúng như môi trường cuối, không chỉ chứng minh `javac` chạy qua.
8. **Rút cờ khi có thể**: sau khi sửa module descriptor hoặc chuyển sang public API, bỏ cờ tạm và chạy kiểm thử hồi quy.

Có thể dùng `java --describe-module demo.lib` cho module tìm được bởi runtime, hoặc `jar --describe-module --file ...` đối với modular/automatic JAR. Những lệnh này giúp xác minh name, `requires`, exports và main class metadata khi có; không phải mọi câu hỏi về runtime graph đều giải quyết được chỉ bằng một lệnh liệt kê.

## 13. Những điều không nên kết luận

**“Đã có --add-modules thì import được mọi class của module.”** Sai. Module có thể resolved nhưng chưa đọc được từ một named consumer hoặc package chưa export.

**“Đã thêm --add-reads là có thể gọi package private của dependency.”** Sai. Readability chỉ giải quyết cạnh đọc; package vẫn cần export, type/member vẫn cần accessibility theo Java.

**“--add-exports cho phép reflection vào bất kỳ field nào.”** Sai. Để deep reflection vào non-public members, thường cần `--add-opens` và điều kiện reflection phù hợp.

**“Chạy javac thành công thì java sẽ tự nhận cờ tương tự.”** Sai. Cấu hình compiler và launcher cần được kiểm chứng độc lập, dù có thể được cùng build tool tổ chức.

**“Nên thêm cả ba cờ vào mọi dự án JPMS.”** Sai. Lộ trình đúng là mô tả module dependencies bằng `requires` và public API bằng `exports` trong descriptors; dùng CLI adjustment ở những trường hợp cụ thể.

**“Tên artifact là library-1.0.jar thì module name chắc chắn là library.”** Sai. Module descriptor, manifest và luật suy tên automatic module có thể cho kết quả khác.

## 14. Bài tập tự kiểm tra

**Câu 1.** Ứng dụng classpath muốn dùng API public trong named module `org.tools` nằm trên module path, nhưng compiler báo module chưa trong graph. Cờ nào liên quan trực tiếp?  
**Đáp án:** `--add-modules org.tools`, đồng thời kiểm tra module path. Không cần `--add-exports` nếu package đã export public.

**Câu 2.** `demo.app` và `demo.lib` đều resolved; `demo.lib` đã export `demo.lib.api`, nhưng `demo.app` không có `requires demo.lib`. Thiếu gì?  
**Đáp án:** Readability edge, tốt nhất là khai `requires demo.lib`; khi không sửa được descriptor có thể tạm `--add-reads demo.app=demo.lib`.

**Câu 3.** `demo.app` đã `requires demo.lib` nhưng muốn gọi public `Secret` trong `demo.lib.internal` chưa export. Cần gì?  
**Đáp án:** Public API mới/exports có chủ đích hoặc tạm `--add-exports demo.lib/demo.lib.internal=demo.app` ở compile và runtime khi cần.

**Câu 4.** Mã `Main` trên classpath muốn dùng một package được export có điều kiện cho unnamed modules. Giá trị đặc biệt nào liên quan?  
**Đáp án:** `ALL-UNNAMED` ở target của `--add-exports`, ví dụ `--add-exports demo.lib/demo.lib.internal=ALL-UNNAMED`.

**Câu 5.** Vì sao `--add-exports demo.lib/internal=demo.app` là cú pháp sai khi package thực tế tên `demo.lib.internal`?  
**Đáp án:** Sau dấu `/` phải là **tên package đầy đủ**, ở đây `demo.lib.internal`, không phải tên thư mục hay phần cuối rút gọn tùy ý.

**Câu 6.** `--add-reads demo.app=ALL-UNNAMED` có đưa `legacy.jar` từ classpath sang module path không?  
**Đáp án:** Không. Nó chỉ tạo readability edge tới unnamed modules; cách tìm thư viện vẫn theo classpath.

**Câu 7.** Đã thêm `--add-exports` khi `javac` và biên dịch qua, nhưng `java` ném `IllegalAccessError` khi truy cập internal class. Cần kiểm tra gì?  
**Đáp án:** Có export tương ứng lúc runtime chưa, module path và tên module đúng không, các điều kiện module/readability khác đã thỏa chưa.

**Câu 8.** Với dự án có thể thay `module-info.java`, nên dùng `--add-reads` cho phụ thuộc cố định hay thêm `requires`?  
**Đáp án:** Thêm `requires` để metadata module tự mô tả dependency và compiler/runtime có cùng graph theo thiết kế.

## 15. Checklist áp dụng trong dự án Java 17+

- Đọc `module-info.java` và xác định **root → resolution → reads → exports** theo đúng thứ tự câu hỏi.
- Khi thiếu *module trong graph*, kiểm tra đường dẫn và `--add-modules`.
- Khi thiếu *readability edge*, ưu tiên `requires` hoặc dùng `--add-reads` khi có lý do tạm thời.
- Khi thiếu *quyền dùng public types của package*, ưu tiên exported public API hoặc `--add-exports` cho mục tiêu được chọn.
- Phân biệt `--add-exports` với `--add-opens` của deep reflection.
- Nếu dùng flags để vượt ranh giới module, áp dụng đầy đủ vào cả **javac** và **java/test launcher** theo nhu cầu thực tế.
- Không dùng `ALL-MODULE-PATH`, `ALL-SYSTEM` hoặc `ALL-UNNAMED` vô điều kiện; càng mở rộng graph và quyền truy cập càng khó kiểm soát.
- Kiểm tra đúng bản JDK, hỗ trợ option và các giới hạn khi dùng `--release` hoặc custom runtime image.
- Khi hoàn tất migration, chuyển sang `requires`/`exports` bền vững và xóa các CLI overrides không còn cần.

**Ghi nhớ:** `--add-modules` giải quyết **module nào được resolve**; `--add-reads` giải quyết **module A đọc module B hay không**; `--add-exports` giải quyết **package P của B có được xuất cho A hay không**. Ba cờ bổ sung những mảnh khác nhau của JPMS và không thay thế `public`, classpath đúng, dependency thật hay cách thiết kế module rõ ràng.

### Tài liệu chính thức và thực hành

- [Oracle Java SE 17: javac Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html).
- [Oracle Java SE 17: java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html).
- [Dev.java: Extending the Module Graph with --add-modules and --add-reads](https://dev.java/learn/modules/add-modules-reads/).
- [Dev.java: Circumventing Strong Encapsulation](https://dev.java/learn/modules/strong-encapsulation/).
- [JEP 261: Module System](https://openjdk.org/jeps/261).