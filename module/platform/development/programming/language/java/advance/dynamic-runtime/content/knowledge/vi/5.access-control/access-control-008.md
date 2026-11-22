# 5.8 Vai trò và phạm vi của `--add-exports`, `--add-opens` trong thực nghiệm

## 1. Mục tiêu và bối cảnh

Từ Java 9, **Java Platform Module System (JPMS)** cho phép một module kiểm soát package nào được công khai cho mã của module khác và package nào được phép truy cập sâu bằng Reflection. Hai tùy chọn dòng lệnh `--add-exports` và `--add-opens` là cách **bổ sung quyền truy cập có phạm vi xác định cho một lần biên dịch/chạy hoặc cho môi trường thực nghiệm**, khi không muốn hoặc không thể thay đổi ngay `module-info.java` của module sở hữu package.

Bài này tập trung vào cách chọn đúng tùy chọn, xác định chính xác **module nguồn / package / module đích**, chứng minh khác biệt qua chương trình chạy được trên Java 17+, đọc lỗi đúng bản chất và quản lý phạm vi tác động của một thực nghiệm.

Sau bài này, bạn có thể:

- Phân biệt **readability**, **exports**, **opens** và **Java access modifiers**.
- Giải thích `--add-exports` giúp mã module khác dùng **public API của một package không được export**, còn `--add-opens` cho phép **deep reflection tại runtime** trên package đó.
- Biết chỗ áp dụng cờ ở `javac` và ở **JVM thực sự chạy ứng dụng hoặc test**, cũng như khác biệt giữa `ALL-UNNAMED` và **named module**.
- Tự dựng module thử nghiệm, tái hiện lỗi biên dịch, `IllegalAccessError`, kết quả `trySetAccessible()` và tác dụng của từng cờ.
- Biết giới hạn của cờ: quyền cho **package và module đích cụ thể**, không biến private thành public ở cấp ngôn ngữ, không tự giải quyết mọi quan hệ đọc module và không sửa vĩnh viễn file module.

> **Nguyên tắc:** Hai cờ là công cụ khoanh vùng để khảo sát tương thích, test hoặc chẩn đoán một phụ thuộc đang truy cập package bị đóng. Một thí nghiệm thành công không chứng minh rằng việc phụ thuộc vào API nội bộ là ổn định cho ứng dụng lâu dài.

## 2. Mô hình quyền truy cập: phải phân biệt bốn lớp

Một lời gọi xuyên module có thể đi qua nhiều điều kiện khác nhau:

| Lớp | Câu hỏi | Công cụ/khái niệm |
| --- | --- | --- |
| **Module được đọc (readability)** | Module gọi có đọc được module cung cấp kiểu không? | `requires` trong `module-info.java`, module graph, `--add-reads` khi thật sự cần |
| **Package được export** | Mã thường được phép tham chiếu **public types** của package đó không? | `exports` hoặc `--add-exports` |
| **Package được open** | Framework có được dùng Reflection để truy cập sâu tới non-public members/types không? | `opens`, `open module` hoặc `--add-opens` |
| **Quy tắc Java/member** | Bản thân class/member có `public`, `protected`, package-private hay `private`? | Java access control, `setAccessible` / `trySetAccessible` khi thích hợp |

Những điều này liên quan nhưng **không thay thế nhau**.

Ví dụ, một package đã được `exports` vẫn có thể chứa `private` field. Mã từ module khác được gọi public API phù hợp, nhưng `Field.setAccessible(true)` để đọc private field có thể bị module system chặn nếu package chưa được `opens`.

Ngược lại, việc một package được `opens` phục vụ reflective access ở **runtime** không đồng nghĩa với việc mã nguồn ở module khác có quyền `import` public type của package ấy khi **biên dịch**. Trường hợp compile-time reference vẫn cần export phù hợp.

Nếu code dùng named module `app.module` để truy cập module `lib.module`, còn cần module `app.module` **đọc** `lib.module` (thông thường qua `requires lib.module;`). `--add-exports` không phải cách tự động thêm mọi `requires` bị thiếu. Với mã đặt trên **class path**, các class thường thuộc **unnamed module**, và target sẽ được chỉ định bằng `ALL-UNNAMED` trong các thí nghiệm bên dưới.

## 3. Cú pháp và ý nghĩa chính xác của từng tùy chọn

### 3.1. `--add-exports`: bổ sung export cho package

Cú pháp:

```text
--add-exports=<source-module>/<package>=<target-module>[,<target-module>...]
```

Ví dụ:

```text
--add-exports=demo.lib/demo.lib.internal=ALL-UNNAMED
--add-exports=demo.lib/demo.lib.internal=demo.app
```

Trong đó:

- `demo.lib` là **module sở hữu package**.
- `demo.lib.internal` là **tên package chính xác** nằm trong module đó.
- `ALL-UNNAMED` là tất cả unnamed modules, gồm code class path; nó **rộng hơn một JAR cụ thể**.
- `demo.app` là tên một **named module**, dùng khi chỉ cần cấp thêm export cho module đó.

Cờ khiến package được xem là **export thêm** tới module đích trong ngữ cảnh phù hợp; mã đích có thể tham chiếu các **public types và public API** của package mà không bị rào cản export của JPMS ngăn lại, miễn các điều kiện về readability và access modifier cũng thỏa mãn.

`--add-exports` được dùng ở **compile-time với `javac`** khi mã nguồn cần import non-exported public type; cũng cần dùng ở **runtime với `java`** nếu chương trình đã biên dịch vẫn truy cập loại type đó qua liên kết thông thường. Chỉ cấp cờ cho `javac` không đảm bảo JVM chạy sẽ được cấp quyền tương tự.

Cờ **không mở quyền private reflection**. Khi `Field` hoặc `Method` non-public cần `setAccessible`, export một mình thường chưa đủ.

### 3.2. `--add-opens`: mở package cho deep reflection lúc chạy

Cú pháp:

```text
--add-opens=<source-module>/<package>=<target-module>[,<target-module>...]
```

Ví dụ:

```text
--add-opens=demo.lib/demo.lib.internal=ALL-UNNAMED
--add-opens=java.base/java.time=ALL-UNNAMED
--add-opens=demo.lib/demo.lib.internal=demo.app
```

Cờ này mở package ở **runtime** cho module đích thực hiện **deep reflection**, ví dụ:

- `Field.trySetAccessible()` hoặc `Field.setAccessible(true)` trên private field.
- `Method`/`Constructor` non-public được kích hoạt truy cập sâu khi quy định Reflection cho phép.
- Một framework như serializer, ORM, proxy/DI hoặc test tool có lý do hợp lệ để thao tác metadata non-public.

Mở package còn cho phép quyền truy cập public ở runtime trong phạm vi được mở, nhưng **không cấp compile-time export** để mã nguồn ở module khác có thể trực tiếp import public type. Vì vậy, `javac` có thể chấp nhận tùy chọn `--add-opens` chỉ để cảnh báo rằng nó **không có tác dụng ở compile time**.

Lưu ý: **được mở package** không có nghĩa mọi thao tác Reflection bất kỳ đều thành công. Vẫn có các quy tắc về cách gọi, đối tượng đích, kiểu dữ liệu, final fields và những giới hạn API riêng. Cờ chỉ giải quyết đúng rào cản package openness của JPMS.

### 3.3. So sánh ngắn

| Tiêu chí | `--add-exports` | `--add-opens` |
| --- | --- | --- |
| Mục tiêu chính | Cho mã đích sử dụng public API của package không export | Cho mã đích reflective access sâu tại runtime |
| `javac` | **Có hiệu lực** khi biên dịch access tới public type nội bộ | **Không mở package ở compile time** |
| `java` | Cấp thêm export trong runtime | Cấp thêm open trong runtime |
| Truy cập private field bằng `setAccessible` từ module khác | **Không đủ** | **Có thể cho phép** nếu các điều kiện khác phù hợp |
| Phạm vi | Một package trong một source module tới target module(s) | Một package trong một source module tới target module(s) |
| Thay đổi `module-info.java`? | Không | Không |
| Dùng để thay thế public API ổn định? | Không nên | Không nên |

Hai cú pháp `--add-exports=X/Y=Z` và `--add-exports X/Y=Z` thường đều dùng được ở launcher; cách dùng dấu `=` ngay sau tên cờ đặc biệt tiện khi cấu hình trong IDE/Gradle/Maven. Các ví dụ trong bài thống nhất một dạng để dễ đối chiếu.

## 4. Thực nghiệm kiểm chứng với module tự tạo

Thay vì phụ thuộc vào class nội bộ có thể thay đổi giữa các JDK, ta tự tạo module `demo.lib` chứa một package cố ý **không export, không open**. Hai chương trình trên class path sẽ kiểm tra public access và private reflection.

**Yêu cầu:** JDK 17 trở lên, `javac` và `java` trên `PATH`. Các lệnh Java dưới đây chạy tại thư mục gốc `jpms-flags-lab`.

### 4.1. Tạo cấu trúc thư mục

```text
jpms-flags-lab/
├── src/
│   ├── demo.lib/
│   │   ├── module-info.java
│   │   └── demo/lib/internal/Helper.java
│   └── app/
│       ├── ExportDemo.java
│       └── OpenDemo.java
└── out/
    ├── mods/
    └── app/
```

Có thể tạo thư mục trước khi tạo file theo sơ đồ. Với Bash (Linux, macOS, Git Bash/WSL):

```bash
mkdir -p src/demo.lib/demo/lib/internal src/app out/mods out/app
```

Với Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path "src/demo.lib/demo/lib/internal","src/app","out/mods","out/app"
```

Hai khối lệnh tạo thư mục trên là **lựa chọn theo hệ điều hành**; sau đó tạo đúng bốn file bên dưới với nội dung tương ứng.

### 4.2. Module library: chưa export và chưa open

File **`src/demo.lib/module-info.java`**:

```java
module demo.lib {
    // Cố ý không exports và không opens package nội bộ.
}
```

File **`src/demo.lib/demo/lib/internal/Helper.java`**:

```java
package demo.lib.internal;

public class Helper {
    private static String secret = "SECRET";

    public static String hello() {
        return "HELLO";
    }
}
```

`Helper` là một **public class**, `hello()` cũng là public method. Tuy vậy, package `demo.lib.internal` chưa được export, nên mã từ module khác không thể tự động tham chiếu hai thành phần này theo kiểu truy cập tĩnh thông thường. `secret` là private field, giúp kiểm tra quyền truy cập sâu.

### 4.3. Chương trình thử truy cập public API

File **`src/app/ExportDemo.java`**:

```java
import demo.lib.internal.Helper;

public class ExportDemo {
    public static void main(String[] args) {
        System.out.println(Helper.hello());
    }
}
```

Đây là class ở **unnamed module** vì sẽ biên dịch/chạy trên class path.

Biên dịch module library:

```bash
javac --module-source-path src -d out/mods -m demo.lib
```

**Thử biên dịch `ExportDemo` không cấp export:**

```bash
javac --module-path out/mods --add-modules demo.lib -d out/app src/app/ExportDemo.java
```

Lệnh này **dự kiến thất bại** vì package `demo.lib.internal` không được `demo.lib` export. Trình biên dịch có thể báo lỗi tương đương:

```text
error: package demo.lib.internal is not visible
(package demo.lib.internal is declared in module demo.lib, which does not export it)
```

Cùng module source, chỉ thay điều kiện quyền truy cập khi biên dịch:

```bash
javac --module-path out/mods --add-modules demo.lib --add-exports=demo.lib/demo.lib.internal=ALL-UNNAMED -d out/app src/app/ExportDemo.java
```

**Kết quả:** biên dịch thành công. Lưu ý `--add-modules demo.lib` làm module được resolve ở ngữ cảnh class path, còn `--add-exports` bổ sung quyền export; hai tùy chọn có vai trò riêng.

**Thử chạy thiếu runtime export:**

```bash
java --module-path out/mods --add-modules demo.lib -cp out/app ExportDemo
```

Dù đã biên dịch thành công, runtime **dự kiến ném `IllegalAccessError`** khi mã cố truy cập `Helper`, vì JVM chạy chương trình chưa được cấp export bổ sung. Lỗi điển hình có ý nghĩa:

```text
java.lang.IllegalAccessError: class ExportDemo (in unnamed module ...)
cannot access class demo.lib.internal.Helper (in module demo.lib)
because module demo.lib does not export demo.lib.internal
```

Dấu `...` ở trên là **đoạn lược bỏ địa chỉ module/stack trace phụ thuộc runtime**, không phải toàn văn log cần so khớp.

**Cấp export khi chạy:**

```bash
java --module-path out/mods --add-modules demo.lib --add-exports=demo.lib/demo.lib.internal=ALL-UNNAMED -cp out/app ExportDemo
```

Stdout chính xác:

```text
HELLO
```

**Kết luận thực nghiệm 1:** `--add-exports` giải quyết quyền tham chiếu public type của package đang đóng, nhưng phải được đặt ở đúng **giai đoạn biên dịch** và **JVM runtime** khi cả hai giai đoạn đều kiểm tra quyền đó.

### 4.4. Chương trình thử Reflection vào private field

File **`src/app/OpenDemo.java`**:

```java
import java.lang.reflect.Field;

public class OpenDemo {
    public static void main(String[] args) throws Exception {
        Class<?> type = Class.forName("demo.lib.internal.Helper");
        Field field = type.getDeclaredField("secret");
        boolean opened = field.trySetAccessible();

        System.out.println("opened=" + opened);
        if (opened) {
            System.out.println("secret=" + field.get(null));
        }
    }
}
```

Chương trình chỉ sử dụng tên class ở dạng chuỗi, không import `Helper`. `Class.forName` và `getDeclaredField` có thể tìm metadata ngay cả khi package chưa export; **bước xin mở quyền `trySetAccessible()`** mới kiểm tra liệu deep reflection từ module gọi có được phép hay không. `field.get(null)` hợp lệ vì `secret` là **static field**; nó chỉ được chạy sau khi cấp quyền thành công.

Biên dịch chương trình:

```bash
javac -d out/app src/app/OpenDemo.java
```

**Lần 1 — chưa cấp cờ:**

```bash
java --module-path out/mods --add-modules demo.lib -cp out/app OpenDemo
```

Stdout:

```text
opened=false
```

**Lần 2 — chỉ cấp `--add-exports`:**

```bash
java --module-path out/mods --add-modules demo.lib --add-exports=demo.lib/demo.lib.internal=ALL-UNNAMED -cp out/app OpenDemo
```

Stdout **vẫn** là:

```text
opened=false
```

Public export không đủ mở private field. Nếu thay `trySetAccessible()` bằng `setAccessible(true)` trong trạng thái package chưa open, Java có thể ném `java.lang.reflect.InaccessibleObjectException` thay vì trả `false`.

**Lần 3 — cấp đúng `--add-opens`:**

```bash
java --module-path out/mods --add-modules demo.lib --add-opens=demo.lib/demo.lib.internal=ALL-UNNAMED -cp out/app OpenDemo
```

Stdout:

```text
opened=true
secret=SECRET
```

**Kết luận thực nghiệm 2:** `--add-opens` mở package cho deep reflection từ unnamed module. Thử nghiệm này **không cần** `--add-exports` vì `OpenDemo` không có static import tới `Helper`; việc tra cứu là qua Reflection. Nếu mã nguồn **có** static import tới package đóng, quyền compile-time export vẫn là bài toán riêng.

### 4.5. Ma trận kết quả đã quan sát

| Chương trình / giai đoạn | Cờ áp dụng | Kết quả |
| --- | --- | --- |
| `javac ExportDemo.java` | Không export | Lỗi compile: package không visible |
| `javac ExportDemo.java` | `--add-exports` | Thành công |
| `java ExportDemo` sau khi compile có export | Runtime không export | `IllegalAccessError` |
| `java ExportDemo` | Runtime có `--add-exports` | `HELLO` |
| `java OpenDemo` | Không cờ | `opened=false` |
| `java OpenDemo` | Chỉ `--add-exports` | `opened=false` |
| `java OpenDemo` | `--add-opens` | `opened=true`, `secret=SECRET` |

Bảy trường hợp trên dùng **cùng các file Java**, chỉ thay đúng tham số JVM ở mỗi lần thử; khác biệt phản ánh ranh giới package export/open của JPMS.

## 5. Thực nghiệm ngắn với chính JDK: package đã export nhưng chưa open

`java.time` là package public API của module `java.base`. Ta có thể gọi `LocalDate.of(...)` bình thường, nhưng truy cập sâu vào private field bên trong `LocalDate` lại là chuyện khác.

Tạo file **`JdkOpenExperiment.java`** (độc lập với thư mục dự án ở mục 4):

```java
import java.lang.reflect.Field;
import java.time.LocalDate;

public class JdkOpenExperiment {
    public static void main(String[] args) throws Exception {
        Field field = LocalDate.class.getDeclaredField("year");
        boolean opened = field.trySetAccessible();
        System.out.println("opened=" + opened);

        if (opened) {
            System.out.println("year="
                    + field.getInt(LocalDate.of(2025, 3, 5)));
        }
    }
}
```

Biên dịch bằng Java 17+:

```bash
javac JdkOpenExperiment.java
```

Không có cờ:

```bash
java JdkOpenExperiment
```

Stdout trên JDK có trường `LocalDate.year` như JDK 17:

```text
opened=false
```

Cấp cờ **chỉ cho JVM chạy ví dụ**:

```bash
java --add-opens=java.base/java.time=ALL-UNNAMED JdkOpenExperiment
```

Stdout:

```text
opened=true
year=2025
```

Điểm cần phân biệt:

- `java.base/java.time` nghĩa là **package `java.time` bên trong module `java.base`**, không phải tên một class.
- Package `java.time` đã export public API; `--add-exports=java.base/java.time=ALL-UNNAMED` trong trường hợp này **không giải quyết private reflection**.
- `year` là **chi tiết triển khai** của `LocalDate` ở JDK đang kiểm tra, không phải public API được bảo đảm tồn tại hoặc giữ nguyên hình dạng qua mọi JDK. Vì thế đây chỉ là thí nghiệm; code sản phẩm nên dùng `LocalDate.getYear()`.
- Cờ có hiệu lực khi khởi động **JVM mới**; bật cờ trong một JVM khác sau đó không làm thay đổi JVM đang chạy.

## 6. Phạm vi thật sự của các cờ

### 6.1. Một package, một module nguồn, tập module đích

Không có wildcard “mở hết mọi package của mọi module” trong cú pháp của từng cờ. Với:

```text
--add-opens=java.base/java.time=ALL-UNNAMED
```

ta đang mở package `java.time` thuộc `java.base` cho **mọi unnamed module**; không tự mở `java.lang`, `java.util`, package thuộc module khác, hoặc các named modules. Cũng không có nghĩa rằng chỉ **một JAR** cụ thể trên class path nhận quyền: `ALL-UNNAMED` áp dụng cho mọi unnamed modules phù hợp.

Với một ứng dụng modular có module `my.test.runner`, phạm vi có thể thu hẹp:

```text
--add-opens=demo.lib/demo.lib.internal=my.test.runner
--add-exports=demo.lib/demo.lib.internal=my.test.runner
```

Đó là hai quyền khác nhau, và tên module đích phải thực sự đúng với module đang thực thi mã truy cập. Nếu framework/thư viện được nạp trên class path, module của nó thường là unnamed; ghi tên một named module khác sẽ không cấp quyền cho nó.

### 6.2. Một lần biên dịch hoặc một JVM chạy cụ thể

- Cờ truyền cho `javac` chỉ ảnh hưởng cách **lần biên dịch đó** kiểm tra accessibility (trong đó `--add-exports` có tác dụng).
- Cờ truyền cho `java` chỉ ảnh hưởng **JVM được launcher đó khởi động**.
- Không tự động lan sang JVM con được tạo bằng `ProcessBuilder`, JVM của plugin test fork, IDE run configuration khác, Gradle `Test` / `JavaExec` khác, hoặc tiến trình server đã chạy từ trước.
- Đặt cờ vào lệnh chạy một unit test nhưng thực tế lỗi đến từ JVM worker/integration test khác sẽ không giải quyết được lỗi.

Trong IDE hay build tool, hãy xác định **process đang ném lỗi**. Với test do Gradle chạy, cờ runtime cần đi vào cấu hình `jvmArgs` của đúng task `Test`, không chỉ vào command line khởi động Gradle daemon. Nếu source code cần `--add-exports` để compile, phải cấu hình riêng compiler arguments của đúng task `JavaCompile`. Trong Maven hoặc IDE cũng theo nguyên tắc **compiler option** và **runtime VM option** là hai chỗ khác nhau.

Một cấu hình minh họa tối thiểu cho **task Test** trong Gradle Groovy DSL:

```groovy
tasks.named('test', Test) {
    jvmArgs '--add-opens=java.base/java.time=ALL-UNNAMED'
}
```

Đây chỉ là cấu hình **runtime của JVM chạy task `test`**, không phải cờ cho mọi quy trình build hoặc một lệnh Java độc lập. Chỉ thêm vào thí nghiệm thực sự cần reflective access.

### 6.3. `--add-exports` không giải quyết readability, module resolution hoặc Java modifier

Nếu named module `app.module` không có quan hệ đọc tới `lib.module`, cần xem `requires lib.module;` hay khi có lý do rõ ràng mới xem `--add-reads`. Nếu `lib.module` chưa được resolve trên module path trong mô hình thí nghiệm, có thể cần `--add-modules lib.module`. `--add-exports` không thay thế cả hai việc đó.

Ngay khi package được export:

- Một **private** class/member không tự biến thành `public` theo ngôn ngữ Java.
- `protected` và package-private vẫn có các quy tắc riêng của Java.
- Code gọi method phải dùng đúng tham số, đối tượng đích, kiểu trả về.
- `--add-exports` không tự bật `setAccessible(true)` và không bảo đảm deep reflection thành công.

### 6.4. `--add-opens` là quyền runtime, không phải “làm mọi thứ được phép”

Package được open khiến nhiều thao tác Reflection sâu có thể hoạt động, nhưng không thay đổi chữ ký Java hoặc phá bỏ mọi quy tắc của Reflection. Ví dụ, field `final` có những giới hạn cập nhật riêng; module openness không bảo đảm viết được vào mọi final field. Các vấn đề class loading, module chưa resolve, missing dependency, gọi method không đúng tham số vẫn là các lỗi khác.

Một package nằm trong **open module** (khai báo `open module ...`) hoặc đã có `opens` phù hợp trong `module-info.java` có thể **không cần** cờ bổ sung. Trước khi thêm cờ, kiểm tra ranh giới thật sự trong module descriptor.

### 6.5. Java 17+ và tùy chọn cũ `--illegal-access`

Từ JDK 17, JEP 403 đưa hầu hết JDK internals vào cơ chế strong encapsulation. Tùy chọn cũ `--illegal-access` từng phục vụ chuyển tiếp trong Java 9–16 **không còn cấp quyền reflective access** trên Java 17: sử dụng nó có thể chỉ tạo cảnh báo về tùy chọn đã lỗi thời. Khi thực nghiệm cần mở package, phải chỉ định **đúng package** bằng `--add-opens`, thay vì trông đợi `--illegal-access=permit`.

Một số internal/critical API có ngoại lệ lịch sử (ví dụ `sun.misc.Unsafe` trong module `jdk.unsupported`), nhưng điều đó không làm các package nội bộ tùy ý trở thành public API ổn định.

Khi compile dựa vào JDK internal APIs, tùy chọn `javac --release` còn hạn chế việc vượt module export của system modules; không coi việc thêm `--add-exports` là cách chắc chắn vượt qua mọi ràng buộc của `--release`. Thực nghiệm cần nêu rõ JDK dùng để compile và mục tiêu compatibility của build.

## 7. Chẩn đoán lỗi theo đúng rào cản

| Hiện tượng | Khả năng cần kiểm tra | Hướng xử lý thực nghiệm |
| --- | --- | --- |
| `package ... is not visible` khi `javac` | Package của named module không export cho mã biên dịch, hoặc module chưa đọc/resolve | Kiểm tra module graph; thêm đúng compile-time `--add-exports` nếu vấn đề là export |
| `IllegalAccessError` khi chạy dù compile được | JVM runtime thiếu quyền export tương ứng | Đặt `--add-exports` ở **JVM thực sự chạy code**; xác nhận module, package, target |
| `InaccessibleObjectException` khi `setAccessible(true)` | Package chưa open cho module thực hiện deep reflection | Dùng `--add-opens` đúng package/module và đúng runtime |
| `trySetAccessible()` trả `false` | Runtime chưa cho phép bật sâu vào member | Kiểm tra `opens`, module của caller, module/package khai báo member |
| `ClassNotFoundException` / `NoClassDefFoundError` | Không tìm thấy class/dependency hoặc module chưa được resolve | Sửa class path/module path/module resolution; hai cờ trên không tạo class bị thiếu |
| Lỗi chỉ xảy ra trong test fork/IDE, không tái hiện ở shell | Cờ được truyền cho tiến trình khác | Kiểm tra VM options của **đúng process**, test runner và test workers |
| Vẫn lỗi khi thêm cờ | Sai tên module/package, sai module đích, member non-public dùng trực tiếp, readability chưa đủ, hoặc nguyên nhân khác | Xác nhận `Class.getModule()`, `getPackageName()`, module graph và stack trace |

Có thể kiểm tra module và package của class một cách có hệ thống:

```java
// Trích đoạn minh họa; giả sử Class<?> type đã được xác định.
Module owner = type.getModule();
String packageName = type.getPackageName();
Module caller = OpenDemo.class.getModule();

System.out.println("owner=" + owner.getName());
System.out.println("package=" + packageName);
System.out.println("caller=" + caller.getName()); // null: unnamed module
System.out.println("exported=" + owner.isExported(packageName, caller));
System.out.println("open=" + owner.isOpen(packageName, caller));
```

**Lưu ý:** Đoạn code trên là **trích đoạn**, dùng để hỗ trợ đọc metadata trong ngữ cảnh có `type`, `OpenDemo`; không phải chương trình độc lập. `Module.isExported(packageName, caller)` và `Module.isOpen(packageName, caller)` giúp kiểm tra **quyền có hiệu lực với đúng caller module**, thay vì chỉ suy đoán từ tên JAR. Với unnamed module, `getName()` trả `null`.

Trong ví dụ `OpenDemo`, ta cũng có thể dùng `Class.forName(...)` để tìm chủ sở hữu package, rồi xem `type.getModule()`. Không nên nhầm package `demo.lib.internal` với tên module `demo.lib` khi điền cờ.

## 8. Cách tổ chức một thí nghiệm có thể kiểm chứng

Để kết luận một cờ thật sự giải quyết đúng vấn đề, hãy ghi lại:

1. **JDK + phiên bản** của `javac` và `java` (ví dụ `java -version`, `javac -version`); bảo đảm chương trình đang dùng đúng JDK dự kiến.
2. **Chương trình tối thiểu** thể hiện chính xác lỗi và module source/target; tránh thêm nhiều thư viện cùng lúc.
3. **Baseline không cờ**: compile error, runtime error hoặc `trySetAccessible() == false` là gì?
4. **Chỉ thêm một cờ đúng package/target**; chạy lại cùng chương trình để chứng minh thay đổi. Khi cần, thử cả compile và runtime như mục 4.3.
5. **Xác nhận JVM nhận cờ** bằng command line hoặc configuration của chính process đó; không dựa vào cấu hình của process cha.
6. **Gỡ cờ để thử lại baseline** nếu cần kiểm tra tính nhân quả; không ghi nhận một thay đổi do code/library version bị đổi cùng lúc.
7. **Ghi kết quả và đường hướng thay thế**: public API được hỗ trợ, cấu hình thư viện đúng cách, update thư viện hoặc thay đổi `module-info.java` trong module do mình sở hữu.

Một bản ghi ngắn phù hợp:

| Thuộc tính | Ví dụ |
| --- | --- |
| Java runtime | JDK 17+ |
| Module nguồn | `demo.lib` |
| Package cần truy cập | `demo.lib.internal` |
| Module đích | `ALL-UNNAMED` |
| Hành vi trước | `opened=false` |
| Thay đổi duy nhất | `--add-opens=demo.lib/demo.lib.internal=ALL-UNNAMED` |
| Hành vi sau | `opened=true`, `secret=SECRET` |
| Kết luận có thể khẳng định | Package chưa open cho unnamed module, cờ runtime đã cấp quyền deep reflection cho thí nghiệm này |
| Kết luận **không** được suy diễn | Private reflection là public API ổn định hoặc mọi JDK/package khác đều hoạt động như vậy |

## 9. Quyết định chọn cờ trong một phút

- **Mã nguồn `import` public class từ package không export và `javac` báo package invisible?** Kiểm tra module graph, rồi thử **`--add-exports` lúc compile**. Nếu binary chạy vẫn truy cập class đó, thường còn cần **`--add-exports` ở runtime**.
- **Public API đã truy cập được nhưng `setAccessible(true)` bị chặn khi đọc private field/constructor?** Kiểm tra package owner và thử **`--add-opens` ở đúng runtime**.
- **Chỉ biết tên class qua `Class.forName`, cần Reflection vào member non-public?** Có thể chỉ cần **`--add-opens`**, không cần compile-time export nếu không có static reference.
- **Không tìm thấy class hoặc module chưa resolve?** Xác định class path/module path, `--add-modules` hoặc quan hệ `requires` trước.
- **Ứng dụng ở named module?** Dùng **tên module đích cụ thể** khi có thể, thay vì cấp `ALL-UNNAMED` rộng hơn nhu cầu.

Về lâu dài, ưu tiên sửa mã để dùng API được export chính thức; nếu sở hữu thư viện, cân nhắc thiết kế `exports`/`opens ... to ...` trong `module-info.java` với phạm vi thật cần thiết. Cờ là một **quyền bổ sung theo cách khởi chạy**, hữu ích để phân lập nguyên nhân tương thích, nhưng cần được giữ ở nơi cấu hình rõ ràng và có lý do kỹ thuật.

## 10. Bài tập tự kiểm tra

**Câu 1.** `java --add-exports=demo.lib/demo.lib.internal=ALL-UNNAMED` làm `Field.trySetAccessible()` trên private field trong `Helper` trả `true` không?  
**Đáp án:** Trong ví dụ mục 4, **không**. Export hỗ trợ public access, deep reflection cần mở package phù hợp bằng `--add-opens`.

**Câu 2.** Vì sao `ExportDemo` biên dịch được với `--add-exports` ở `javac` nhưng vẫn ném `IllegalAccessError` khi chạy thiếu cờ?  
**Đáp án:** Compile và runtime là hai ngữ cảnh kiểm tra riêng. Quyền export bổ sung ở compiler không tự được “đóng gói” trong file `.class` để JVM khác nhận theo.

**Câu 3.** Với một test JUnit chạy trên class path, phần `=ALL-UNNAMED` chỉ cấp quyền cho riêng test class đó?  
**Đáp án:** Không. Nó cấp cho **mọi unnamed module**, gồm các class/JAR class path phù hợp trong JVM đó. Nếu cần quyền hẹp hơn, cân nhắc test trong named module.

**Câu 4.** Chỉ thêm `--add-opens` vào lệnh `javac` có giúp mã nguồn `import` class public thuộc package không export được biên dịch không?  
**Đáp án:** Không. `--add-opens` dùng cho runtime reflective access, không phải compile-time export.

**Câu 5.** Một named module không đọc được module nguồn. Chỉ thêm `--add-exports` đã giải quyết xong toàn bộ hay chưa?  
**Đáp án:** Chưa chắc. Còn cần quan hệ readability thích hợp (`requires` hoặc cấu hình đọc có chủ đích), và module nguồn phải được resolve.

**Câu 6.** Vì sao nên thử `java.base/java.time` với `--add-opens` nhưng không giữ code đọc private field `LocalDate.year` trong sản phẩm?  
**Đáp án:** Field đó là chi tiết triển khai. Public API `LocalDate.getYear()` ổn định hơn; cờ thực nghiệm không biến chi tiết nội bộ thành giao diện được bảo đảm.

**Câu 7.** Nếu thêm `--add-opens` vào Gradle daemon nhưng unit test chạy trong JVM test fork vẫn lỗi, nên làm gì?  
**Đáp án:** Cấu hình runtime arguments cho **đúng task/process chạy test**, xác nhận cờ có mặt trong JVM phát sinh `InaccessibleObjectException`.

## 11. Tài liệu tham khảo chính thức

- [Dev.java — Circumventing Strong Encapsulation with `--add-exports` and `--add-opens`](https://dev.java/learn/modules/add-exports-opens/): ví dụ compile-time export, runtime export, deep reflection và phạm vi mở package.
- [Oracle Java SE 17 — `java` launcher options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): các tùy chọn module system khi khởi chạy JVM.
- [Oracle Java SE 17 — `javac` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): quy tắc `--add-exports` lúc compile, module graph và giới hạn của `--release`.
- [OpenJDK JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): vì sao JDK 17 mạnh tay hơn với reflective access vào nội bộ JDK.
- [Oracle Java SE 17 — `AccessibleObject`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): `trySetAccessible()`, `setAccessible(true)` và điều kiện quyền truy cập khi module khác nhau.
- [Oracle Java SE 17 — `Module`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): `isExported()`, `isOpen()` và khái niệm module openness.
