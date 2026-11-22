# Phân biệt package, classpath và module ở mức định hướng — Java 17+

## 1. Ba khái niệm giải quyết ba câu hỏi khác nhau

Một dự án Java có nhiều lớp và thư viện cần tổ chức tên, tìm được mã đã biên dịch, đồng thời có thể xác định những phần nào được phép phụ thuộc vào nhau. Ba khái niệm thường gặp là:

| Khái niệm | Câu hỏi được giải quyết | Minh họa |
|---|---|---|
| **Package** | Kiểu này **mang tên gì**, thuộc nhóm tên nào? | `package com.example.library;`, kiểu `com.example.library.Greeter` |
| **Classpath** | JVM/trình biên dịch tìm các lớp và JAR kiểu truyền thống **ở đâu**? | `java -cp out-cp com.example.app.Main` |
| **Module** | Một đơn vị mã được đặt tên **phụ thuộc vào module nào và công khai package nào**? | `module com.example.app { requires com.example.library; }` |

**Tóm lại:** package là **không gian tên**; classpath là **đường dẫn tìm lớp/thư viện**; module là **đơn vị tổ chức phụ thuộc và ranh giới API** trong Java Platform Module System (JPMS, có từ Java 9).

Chúng không thay thế nhau: một chương trình dùng classpath vẫn có package; một named module cũng chứa các package; và file `.class` của module vẫn phải được JVM tìm thấy qua cơ chế thích hợp (thường là **module path**).

## 2. Package: tổ chức tên kiểu

~~~java
package com.example.library;

public final class Greeter {
    private Greeter() {}

    public static String hello(String name) {
        return "Hello, " + name;
    }
}
~~~

- `Greeter` là tên đơn giản của lớp.
- `com.example.library` là package.
- `com.example.library.Greeter` là **tên đầy đủ** của top-level class.
- Một lớp khác trong package `com.example.other` vẫn có thể có tên đơn giản `Greeter` mà không cùng tên đầy đủ.

Trong một file ở package khác, có thể dùng:

~~~java
import com.example.library.Greeter;

// Sau đó:
String message = Greeter.hello("Lan");
~~~

Hoặc không import mà viết `com.example.library.Greeter.hello("Lan")`.

**Import chỉ giúp tra cứu tên trong mã nguồn**. Dòng `import` không nói JVM phải tìm thư viện ở ổ đĩa nào, không làm classpath xuất hiện và không tự tạo object. Trình biên dịch vẫn cần tìm được lớp bằng những đường dẫn và cấu hình build phù hợp.

Package cũng liên quan đến quyền truy cập `package-private`: hai tên `com.example` và `com.example.library` **không phải cùng một package**, dù nhìn như quan hệ cha/con. `import com.example.*;` không tự import kiểu của `com.example.library`.

## 3. Classpath: chỉ nơi tìm lớp và JAR

Sau khi biên dịch, Java tạo ra file `.class`. Khi sử dụng cách chạy **không modular**, classpath mô tả các **thư mục gốc** và/hoặc **JAR** để công cụ tìm những lớp đó.

Ví dụ bố cục kết quả biên dịch:

~~~text
out-cp/
└── com/
    └── example/
        ├── library/
        │   └── Greeter.class
        └── app/
            └── Main.class
~~~

Lệnh:

~~~bash
java -cp out-cp com.example.app.Main
~~~

được hiểu là:

1. Tìm lớp chính có tên đầy đủ `com.example.app.Main`.
2. Tra từ **classpath root `out-cp`**, ghép các thành phần package thành đường dẫn `com/example/app/Main.class`.
3. Khi cần `Greeter`, tìm lớp `com/example/library/Greeter.class` từ classpath thích hợp.

**Không** chọn `-cp out-cp/com/example/app` cho một main class có package `com.example.app`: đó không phải root tương ứng với tên lớp đầy đủ.

Classpath có thể gồm nhiều mục. Dấu phân tách giữa các mục khác nhau theo hệ điều hành:

| Môi trường | Ví dụ classpath gồm thư mục và JAR | Dấu phân tách |
|---|---|---|
| Linux/macOS | `out-cp:lib/tools.jar` | `:` |
| Windows | `out-cp;lib\\tools.jar` | `;` |

Các mục trên chỉ minh họa cú pháp: `lib/tools.jar` không phải thư viện bắt buộc hay file được tạo trong bài này. Đối với ví dụ thực hành chỉ dùng `-cp out-cp`.

**Phân biệt:** `classpath` không phải tên package, và đặt một JAR vào classpath không tự khai báo một named module trong mã ứng dụng.

## 4. Classpath và unnamed module

Trong hệ thống module Java 9+, các lớp được nạp bằng application class loader từ classpath theo kiểu truyền thống thuộc **unnamed module** của class loader đó.

Đối với một class như `Main` chạy bằng `java -cp out-cp ...`, biểu thức:

~~~java
Main.class.getModule().getName()
~~~

trả về `null` (tên module của unnamed module không có giá trị). Điều này **không có nghĩa lớp không có package**: `Main.class.getPackageName()` vẫn có thể là `com.example.app`.

| Biểu thức | Trong bản chạy classpath của ví dụ |
|---|---|
| `Main.class.getName()` | `com.example.app.Main` |
| `Main.class.getPackageName()` | `com.example.app` |
| `Main.class.getModule().getName()` | `null` |

Một chương trình đơn giản **không bắt buộc tạo module-info.java**. Package và classpath vẫn hoạt động với Java 17+ mà không cần biến toàn bộ dự án thành named modules.

## 5. Module: đơn vị có tên, phụ thuộc và ranh giới API

Java Platform Module System (JPMS) cho phép tạo một **named module**, mô tả trong file `module-info.java`.

~~~java
module com.example.library {
    exports com.example.library;
}
~~~

và module sử dụng:

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

Ý nghĩa:

- `module com.example.library` đặt **tên module** là `com.example.library`. Tên module có thể giống tiền tố package, nhưng **module name và package name là hai khái niệm riêng**.
- `exports com.example.library;` cho các module đọc được module thư viện **truy cập những public types và public members được phép** trong package API đó.
- `requires com.example.library;` khai báo module ứng dụng **phụ thuộc vào/đọc được** module thư viện.
- `module-info.java` là **module declaration**, không phải class `Main` và cũng không thay cho khai báo `package` trong các file lớp.

Một module có thể chứa **nhiều package**. Mỗi package không buộc phải trở thành một module riêng. Một module chỉ công khai các package đã `exports` (hoặc công khai có điều kiện bằng cú pháp khác), nên **`public class` trong package không được export chưa đủ để module khác truy cập theo quy tắc JPMS**.

**Lưu ý:** `exports` là công khai API ở mức Java; `opens` phục vụ truy cập phản chiếu sâu trong các trường hợp thích hợp, không tương đương `exports`. Bài nhập môn này chỉ dùng `requires` và `exports`.

## 6. Module path khác classpath ra sao?

**Module path** chứa các vị trí để hệ thống module tìm **named modules**, ví dụ các thư mục module đã biên dịch hoặc modular JAR.

~~~bash
java --module-path out-mod --module com.example.app/com.example.app.Main
~~~

- `out-mod`: vị trí các named modules được biên dịch.
- `com.example.app` trước dấu `/`: **tên module** chứa điểm vào.
- `com.example.app.Main` sau dấu `/`: **tên lớp main**, vẫn có package riêng.
- JPMS dùng các module descriptors để kiểm tra quan hệ `requires` và `exports`.

Bảng so sánh:

| Khía cạnh | Classpath | Module path |
|---|---|---|
| Mục đích cơ bản | Tìm class/JAR của ứng dụng kiểu truyền thống | Tìm named modules |
| Lệnh chạy | `java -cp out-cp com.example.app.Main` | `java --module-path out-mod --module com.example.app/com.example.app.Main` |
| File mô tả module bắt buộc trong ví dụ? | Không; bỏ qua `module-info.java` khi biên dịch các lớp | Có `module-info.java` cho hai named modules |
| Kiểm tra `requires`/`exports` | Không dùng ranh giới named module cho các lớp trên classpath | Có, trong JPMS |
| Package tồn tại không? | Có | Có |

Module path **không chỉ là cách viết khác của classpath**: đặt mã trên module path với descriptor hợp lệ có thể làm thay đổi khả năng đọc và truy cập giữa các module.

## 7. Cấu trúc nguồn dùng chung cho hai cách chạy

Để phân biệt chính xác, ta sử dụng **cùng một bộ file nguồn**, rồi biên dịch theo hai chế độ. Cấu trúc:

~~~text
project/
└── src/
    ├── com.example.library/
    │   ├── module-info.java
    │   └── com/
    │       └── example/
    │           └── library/
    │               └── Greeter.java
    └── com.example.app/
        ├── module-info.java
        └── com/
            └── example/
                └── app/
                    └── Main.java
~~~

Trong ví dụ:

- Có **hai named modules** để thử chế độ module.
- Có **hai packages** chứa class: `com.example.library` và `com.example.app`.
- Khi chạy chế độ classpath, ta chỉ biên dịch hai file `Greeter.java` và `Main.java`, **không biên dịch hai file `module-info.java`**.
- Khi chạy chế độ module path, ta biên dịch cả descriptors theo `--module-source-path src`.

Điều này giúp thấy rõ package vẫn tồn tại trong cả hai trường hợp; sự khác nhau thể hiện ở **cách khai báo/giải quyết module** và **cách gọi chương trình**.

## 8. Cú pháp mã nguồn Java 17+ đầy đủ

Tạo đúng **bốn file** theo cấu trúc tại mục 7.

**File 1 — `src/com.example.library/module-info.java`:**

~~~java
module com.example.library {
    exports com.example.library;
}
~~~

**File 2 — `src/com.example.library/com/example/library/Greeter.java`:**

~~~java
package com.example.library;

public final class Greeter {
    private Greeter() {}

    public static String hello(String name) {
        return "Hello, " + name;
    }
}
~~~

**File 3 — `src/com.example.app/module-info.java`:**

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

**File 4 — `src/com.example.app/com/example/app/Main.java`:**

~~~java
package com.example.app;

import com.example.library.Greeter;

public final class Main {
    private Main() {}

    public static void main(String[] args) {
        System.out.println("main class=" + Main.class.getName());
        System.out.println("library class=" + Greeter.class.getName());
        System.out.println("message=" + Greeter.hello("Lan"));
        System.out.println("app module=" + Main.class.getModule().getName());
        System.out.println("library module=" + Greeter.class.getModule().getName());
    }
}
~~~

Ở cả hai chế độ chạy, hai dòng tên class vẫn giữ package như nhau. Hai dòng `module=...` giúp nhận diện sự khác biệt: **unnamed module** khi chạy classpath và **named modules** khi chạy module path.

## 9. Cách 1 — biên dịch/chạy theo classpath

Đứng trong thư mục `project` có chứa `src`. Dùng **JDK 17 trở lên**, không cần Maven/Gradle, thư viện ngoài hoặc preview features.

**Bash (Linux/macOS):**

~~~bash
mkdir -p out-cp
javac --release 17 -encoding UTF-8 -d out-cp src/com.example.library/com/example/library/Greeter.java src/com.example.app/com/example/app/Main.java
java -cp out-cp com.example.app.Main
~~~

**PowerShell (Windows):**

~~~powershell
New-Item -ItemType Directory -Force -Path out-cp | Out-Null
javac --release 17 -encoding UTF-8 -d out-cp .\src\com.example.library\com\example\library\Greeter.java .\src\com.example.app\com\example\app\Main.java
java -cp out-cp com.example.app.Main
~~~

Lệnh `javac` chỉ nêu **hai source files có class**, không nêu bất kỳ `module-info.java` nào. `out-cp` là thư mục đích chứa các class theo tên package và là **classpath root** lúc chạy.

### Exact expected stdout — classpath

~~~text
main class=com.example.app.Main
library class=com.example.library.Greeter
message=Hello, Lan
app module=null
library module=null
~~~

`Main.class.getModule()` và `Greeter.class.getModule()` đều trả module descriptor runtime của **unnamed module** tương ứng; `getName()` trả `null`. Hai class vẫn có package và tên đầy đủ như in ở hai dòng đầu.

## 10. Cách 2 — biên dịch/chạy theo named modules

Vẫn đứng trong thư mục `project`, dùng nguyên bốn file nguồn phía trên.

**Bash (Linux/macOS):**

~~~bash
mkdir -p out-mod
javac --release 17 -encoding UTF-8 --module-source-path src -d out-mod -m com.example.library,com.example.app
java --module-path out-mod --module com.example.app/com.example.app.Main
~~~

**PowerShell (Windows):**

~~~powershell
New-Item -ItemType Directory -Force -Path out-mod | Out-Null
javac --release 17 -encoding UTF-8 --module-source-path src -d out-mod -m com.example.library,com.example.app
java --module-path out-mod --module com.example.app/com.example.app.Main
~~~

`--module-source-path src` chỉ đường dẫn nguồn chứa các thư mục tên module; `-m` chọn những module cần biên dịch; `-d out-mod` xuất các class đã biên dịch theo các module.

Kết quả có dạng:

~~~text
out-mod/
├── com.example.library/
│   ├── module-info.class
│   └── com/example/library/Greeter.class
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
~~~

JPMS giải quyết `requires com.example.library` từ app và kiểm tra `exports com.example.library` từ thư viện.

### Exact expected stdout — module path

~~~text
main class=com.example.app.Main
library class=com.example.library.Greeter
message=Hello, Lan
app module=com.example.app
library module=com.example.library
~~~

So với cách 1, **ba dòng đầu giữ nguyên**, chỉ khác thông tin module của các class. Điều này minh họa rằng cùng source code với package có thể biên dịch và chạy theo hai mô hình triển khai khác nhau.

## 11. Những hiểu lầm thường gặp

| Nhầm lẫn | Hiểu đúng |
|---|---|
| Package chính là thư mục | Package là namespace; thư mục là cách tổ chức file thường khớp tên package |
| Chỉ khai báo `package` là JVM tự tìm được class | Phải biên dịch và cung cấp vị trí class/JAR thích hợp |
| `import` thay thế classpath | Import giải quyết tên tại compile time, không cung cấp file thư viện |
| `-cp out-cp/com/example/app` với `com.example.app.Main` | Classpath phải là root chứa đường dẫn `com/example/app`, tức `out-cp` |
| Module là một class | Module là đơn vị có tên bao gồm các package và descriptor |
| Module bắt buộc có đúng một package | Một module có thể chứa nhiều package |
| Package tên `com.example.app` thì module cũng phải tên ấy | Hai tên là hai khái niệm độc lập; ví dụ trùng nhau chỉ để dễ hiểu |
| `public class` ở một package trong named module là luôn nhìn thấy từ mọi module | Module còn cần export package và điều kiện readability |
| `requires` tự import class vào mã nguồn | Vẫn cần import hoặc tên đầy đủ khi dùng kiểu trong package khác |
| `exports` biến package thành classpath directory | Exports khai báo API của module, không thay thế đường dẫn tìm module |
| Chạy classpath nhưng vẫn mong `getModule().getName()` in tên module khai báo trong các file `module-info.java` bị bỏ qua | Các class được biên dịch/đặt trên classpath trong ví dụ thuộc unnamed module |
| Nhầm `--module-path` với `--module-source-path` | Module path dùng tìm named modules đã có; module source path định vị mã nguồn modules cho compiler |

## 12. Chọn cách nào khi bắt đầu học Java?

- Bài Java nhỏ và ứng dụng chưa chia module: **dùng package rõ ràng và classpath**, học `javac -d out`, `java -cp out package.Main` trước.
- Khi đọc dự án có `module-info.java`: nhận diện **tên module**, những `requires` và `exports` cơ bản; biết cách tìm module path và điểm vào.
- Khi dùng IDE/Maven/Gradle: build tool có thể cấu hình classpath/module path tự động, nhưng ba khái niệm vẫn **khác nhau**.
- Khi gặp lỗi “cannot find symbol”, “ClassNotFoundException”, “NoClassDefFoundError” hoặc lỗi truy cập module: kiểm tra lần lượt **tên package/import**, việc biên dịch/tìm class, và nếu có JPMS thì **module descriptor/readability/exports**. Không kết luận chỉ từ một thông báo lỗi rằng package, classpath và module là cùng một thứ.

**Hạn chế của bài:** JPMS còn có `opens`, `uses`, `provides ... with`, automatic modules, strong encapsulation và nhiều tình huống kết hợp classpath/module path. Ở mức định hướng, cần hiểu vai trò chính của `requires` và `exports`, chưa cần tự xây hệ thống module phức tạp.

## 13. Bài tập có đáp án

**A.** `com.example.data.User` gồm simple name và package gì?  
**Đáp án:** simple name `User`, package `com.example.data`.

**B.** Có `Greeter.class` ở `out-cp/com/example/library/Greeter.class`, classpath root nên là gì?  
**Đáp án:** `out-cp`, không phải `out-cp/com/example/library`.

**C.** Hai package `com.example.app` và `com.example.library` nhất thiết phải nằm trong hai module riêng không?  
**Đáp án:** **Không**; một module có thể chứa nhiều package. Ví dụ này chọn hai module để minh họa `requires` và `exports`.

**D.** File `module-info.java` nào khai báo module ứng dụng phụ thuộc thư viện?

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

**E.** Nếu thư viện bỏ dòng `exports com.example.library;` mà app vẫn cần tham chiếu công khai `Greeter` theo mô hình named modules, có vấn đề gì?  
**Đáp án:** **Có**. App không được truy cập trực tiếp API thuộc package không được export theo quy tắc JPMS, dù lớp `Greeter` có khai báo `public`.

**F.** Trong cách chạy classpath của ví dụ, `Main.class.getModule().getName()` trả gì?  
**Đáp án:** `null`, vì class thuộc unnamed module.

**G.** Vì sao `import com.example.library.Greeter;` không tự thay thế `requires com.example.library;` trong named module `com.example.app`?  
**Đáp án:** `import` giúp viết tên ngắn trong mã nguồn; `requires` khai báo quan hệ đọc/phụ thuộc ở mức module. Hai nhiệm vụ khác nhau.

## 14. Checklist và kết luận

- [ ] Phân biệt `package`, `classpath` và `module` theo chức năng.
- [ ] Hiểu tên kiểu đầy đủ gồm package + simple name.
- [ ] Biết classpath root của class đã biên dịch theo cấu trúc package.
- [ ] Biết `import` không tự cung cấp class/JAR còn thiếu.
- [ ] Nhận diện `module-info.java`, `module`, `requires` và `exports`.
- [ ] Hiểu named module có thể bao gồm nhiều package.
- [ ] Phân biệt unnamed module của classpath với named module chạy qua module path.
- [ ] Biết công dụng của `--module-source-path` khi biên dịch nguồn module.
- [ ] Biết điểm vào `java --module-path ... --module name/package.Main`.
- [ ] Chạy được cùng hai source classes ở chế độ classpath và bộ bốn file ở chế độ module path, đối chiếu stdout.
- [ ] Không coi package, classpath và module là ba từ gọi cho một tính năng duy nhất.

**Kết luận:** **Package đặt tên và nhóm kiểu**, **classpath chỉ nơi tìm lớp/JAR**, còn **module khai báo đơn vị phụ thuộc và các package API được công khai**. Trong Java 17+, có thể bắt đầu từ package + classpath rồi học `module-info.java` khi gặp ứng dụng modular; hiểu đúng trách nhiệm từng khái niệm giúp đọc lỗi biên dịch/khởi chạy và tổ chức dự án rõ ràng.