# Named module, unnamed module và automatic module

Từ Java 9, **Java Platform Module System (JPMS)** bổ sung khái niệm *module* trên nền package và JAR. Module giúp hệ thống biểu diễn phụ thuộc có tên, kiểm soát package được truy cập từ bên ngoài, và giải quyết tập module cần thiết khi biên dịch/chạy. Tuy nhiên, dự án Java có thể đồng thời chứa code dùng cơ chế classpath cũ và các module mới.

Vì vậy, cần phân biệt chính xác:

- **Explicit named module:** module có tên được khai báo trong `module-info.java` (sau biên dịch là `module-info.class`).
- **Unnamed module:** module **không có tên**, chứa các lớp được tải theo mô hình classpath truyền thống của một class loader.
- **Automatic module:** JAR **không có module descriptor** nhưng được đặt trên module path và được hệ thống cho một tên module tự động.

Điều quan trọng nhất: **automatic module cũng là named module**. Về phân loại, named module bao gồm module đặt tên tường minh và automatic module. Ba nhãn trên là ba trường hợp cần thực hành, không phải ba tập rời nhau.

Bài học triển khai bằng Java 17+, không dùng thư viện ngoài JDK. Bạn sẽ tạo hai named modules, chạy JAR đó trên classpath để thấy unnamed module, rồi biến một JAR cũ thành automatic module để ứng dụng modular có thể tham chiếu bằng `requires`.

## 1. Tại sao JPMS xuất hiện?

Trước JPMS, lập trình viên thường chọn các vị trí trên **classpath** để `javac` và `java` tìm thấy các lớp. Cách này hữu ích nhưng một JAR không bắt buộc khai báo đầy đủ tập dependency và không có ranh giới `exports` ở cấp module.

Xét một thư viện có package `org.example.greetings.api` và package `org.example.greetings.internal`. Trên classpath, một lớp `public` thuộc package nội bộ có thể bị code bên ngoài tham chiếu nếu đáp ứng các quy tắc truy cập Java khác. Với explicit named module, tác giả có thể chủ động chỉ export package API và giữ package nội bộ không export.

Tệp descriptor:

~~~java
module org.example.greetings {
    exports org.example.greetings.api;
}
~~~

Dòng `module org.example.greetings` công bố tên module. Dòng `exports` công bố package mà các module khác có thể sử dụng các kiểu `public` phù hợp. Mỗi package có thể chứa nhiều lớp; module cũng có thể chứa nhiều package.

Module khác muốn dùng API này thường khai báo:

~~~java
module org.example.app {
    requires org.example.greetings;
}
~~~

`requires` diễn đạt quan hệ **readability**: module ứng dụng đọc module phụ thuộc. Quyền truy cập cụ thể tới một kiểu còn cần package được export và kiểu/thành viên có modifier phù hợp. `java.base` được mọi module đọc ngầm, nên không cần viết `requires java.base;`.

Tóm tắt:

~~~text
org.example.app (named)
       |
       | requires org.example.greetings
       v
org.example.greetings (named)
       |
       | exports org.example.greetings.api
       v
public API Greeter
~~~

Đây là lý do `public` và `exports` không có nghĩa giống nhau: `public` thuộc hệ thống truy cập kiểu/thành viên, còn `exports` là ranh giới ở cấp module.

## 2. Ba kiểu module ở cạnh nhau

| Thuộc tính | Explicit named | Unnamed | Automatic |
| --- | --- | --- | --- |
| Có tên module | Có, khai báo tường minh | Không | Có, được cấp tự động |
| `module-info.class` | Có | Không cần | Không có descriptor tường minh |
| Vị trí điển hình | Module path | Classpath | Module path |
| Có thể được module khác `requires` | Có | **Không** | Có |
| `exports` | Theo descriptor | Được coi là export mọi package | Tự export mọi package |
| `opens` | Theo descriptor/cơ chế JPMS | Được coi là open mọi package | Tự open mọi package |
| Công dụng | Thiết kế module có ranh giới rõ | Chạy code truyền thống | Chuyển tiếp JAR cũ sang JPMS |

**Named là một đặc tính, không đồng nghĩa phải có `module-info.java` do người viết tạo.** Automatic module có tên nhưng descriptor được hệ thống tổng hợp. Unnamed module không có tên nên không thể được trỏ đến qua một `requires some.name;`.

Một ứng dụng có thể dùng nhiều module và JAR, song **nơi đặt JAR** quan trọng: JAR không modular ở classpath thuộc unnamed module; JAR đó ở module path có thể trở thành automatic module.

## 3. Explicit named modules: ví dụ đầy đủ

Tạo cây sau, đặt `module-demo` làm thư mục làm việc:

~~~text
module-demo/
├── src/
│   ├── org.example.greetings/
│   │   ├── module-info.java
│   │   └── org/example/greetings/api/Greeter.java
│   ├── org.example.app/
│   │   ├── module-info.java
│   │   └── org/example/app/Main.java
│   └── ...
├── out/
│   ├── greetings/
│   └── app/
└── mods/
~~~

**`src/org.example.greetings/module-info.java`:**

~~~java
module org.example.greetings {
    exports org.example.greetings.api;
}
~~~

**`src/org.example.greetings/org/example/greetings/api/Greeter.java`:**

~~~java
package org.example.greetings.api;

public final class Greeter {
    private Greeter() {
    }

    public static String hello(String name) {
        return "Hello, " + name;
    }
}
~~~

**`src/org.example.app/module-info.java`:**

~~~java
module org.example.app {
    requires org.example.greetings;
}
~~~

**`src/org.example.app/org/example/app/Main.java`:**

~~~java
package org.example.app;

import org.example.greetings.api.Greeter;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.hello("Lan"));
    }
}
~~~

Trên Linux/macOS, từ gốc dự án tạo thư mục đích:

~~~sh
mkdir -p out/greetings out/app mods
~~~

Trên Windows PowerShell, có thể tạo bằng:

~~~powershell
New-Item -ItemType Directory -Force out/greetings, out/app, mods | Out-Null
~~~

Chỉ cần chạy một cách tạo thư mục phù hợp. Sau đó biên dịch/đóng gói thư viện trước:

~~~sh
javac -encoding UTF-8 -d out/greetings src/org.example.greetings/module-info.java src/org.example.greetings/org/example/greetings/api/Greeter.java
jar --create --file mods/org.example.greetings.jar -C out/greetings .
~~~

`-d out/greetings` tạo đầu ra theo cấu trúc package; `jar -C out/greetings .` đóng gói từ **gốc module output**. JAR kết quả có `module-info.class` và `org/example/greetings/api/Greeter.class`.

Biên dịch/đóng gói module tiêu thụ:

~~~sh
javac -encoding UTF-8 --module-path mods -d out/app src/org.example.app/module-info.java src/org.example.app/org/example/app/Main.java
jar --create --file mods/org.example.app.jar -C out/app .
~~~

`--module-path mods` chỉ nơi tìm module dependency. `javac` có thể tìm `org.example.greetings` và kiểm tra `requires`, `exports`. Chạy:

~~~sh
java --module-path mods --module org.example.app/org.example.app.Main
~~~

Stdout:

~~~text
Hello, Lan
~~~

Phần trước dấu `/` của `--module` là **tên module**, sau nó là **tên lớp main đầy đủ**. Đó là cú pháp lựa chọn module/lớp, không phải đường dẫn tệp.

Kiểm tra JAR:

~~~sh
jar --describe-module --file mods/org.example.greetings.jar
jar --describe-module --file mods/org.example.app.jar
~~~

Hai JAR có descriptor module tường minh. Lệnh in chi tiết metadata có thể khác theo JDK, nhưng phần cần kiểm tra là các tên module và quan hệ `requires`/`exports`.

### Kiểm tra ý nghĩa `exports`

Nếu đổi descriptor thư viện thành:

~~~java
module org.example.greetings {
}
~~~

rồi biên dịch lại thư viện, đóng gói JAR mới và biên dịch lại ứng dụng, mã `import org.example.greetings.api.Greeter;` bị từ chối do package không được export cho module ứng dụng. **Greeter là `public` vẫn chưa đủ.** Đây là lỗi truy cập ở cấp module, không phải do thiếu tệp lớp.

Mã descriptor trên là **phiên bản thử nghiệm** để gây lỗi, không dùng đồng thời với bản có `exports` nếu muốn chạy chương trình thành công.

## 4. Unnamed module: ứng dụng dùng classpath

**Classpath** là cơ chế truyền thống liệt kê thư mục class hoặc JAR cho công cụ tìm kiếm lớp. Những lớp được nạp theo cơ chế đó thuộc **unnamed module của class loader tương ứng**. Một JVM có thể có nhiều class loader và do đó không nhất thiết chỉ có một unnamed module toàn cục.

Đặc trưng:

- Không có tên module và không có `module-info.java` để khai báo `requires`.
- Duy trì khả năng tương thích với mã Java trước JPMS.
- Các package thuộc unnamed module được xem như export/open cho mục đích tương thích.
- Mã unnamed có khả năng đọc những named modules đã được resolve theo quy tắc JPMS, nhưng package đích vẫn phải export đúng; không phải mọi JAR đặt trên module path tự được resolve vào graph.

### Dùng modular JAR trên classpath

Cùng JAR `mods/org.example.greetings.jar` ở phần 3, nếu đưa vào **classpath**, sẽ được xử lý theo mô hình classpath; descriptor bên trong không làm JAR tự hoạt động như explicit named module trong cấu hình này.

Tạo file **`src/classapp/LegacyMain.java`** không khai báo package:

~~~java
import org.example.greetings.api.Greeter;

public class LegacyMain {
    public static void main(String[] args) {
        System.out.println(Greeter.hello("Linh"));
    }
}
~~~

Tạo trước `out/classapp`. Biên dịch bằng thư viện trên classpath:

~~~sh
javac -encoding UTF-8 -cp mods/org.example.greetings.jar -d out/classapp src/classapp/LegacyMain.java
~~~

Chạy trên Linux/macOS:

~~~sh
java -cp "out/classapp:mods/org.example.greetings.jar" LegacyMain
~~~

Trên Windows (PowerShell/CMD):

~~~powershell
java -cp "out/classapp;mods/org.example.greetings.jar" LegacyMain
~~~

Chạy một lệnh phù hợp sẽ in:

~~~text
Hello, Linh
~~~

Điểm đáng chú ý: **một JAR có `module-info.class` có thể nằm trên classpath và được sử dụng như thư viện truyền thống**, không phải named module được resolve theo descriptor. Bối cảnh tải lớp quyết định, không phải đuôi `.jar`.

### Named module có thể `requires` unnamed module không?

**Không.** Vì unnamed module không có tên, descriptor không thể viết một mệnh đề `requires` tham chiếu tới nó. Ví dụ sau không phải giải pháp cho thư viện nằm ở classpath:

~~~java
module org.example.app {
    requires some.unnamed.module;
}
~~~

Đây là **mẫu cố ý không hợp lệ khi dependency thực tế chỉ ở classpath**. Tên `some.unnamed.module` không được tự tạo từ classpath.

Nếu module ứng dụng cần thư viện cũ, một hướng thường dùng là đặt JAR đó trên **module path** dưới dạng automatic module, hoặc tìm phiên bản thư viện explicit modular. Các tùy chọn tương thích `--add-reads` có thể hỗ trợ một số tình huống, nhưng là giải pháp có kiểm soát chứ không làm unnamed module biến thành named module.

## 5. Automatic module: JAR cũ xuất hiện trên module path

Đây là cơ chế chuyển tiếp quan trọng nhất khi hệ sinh thái Java chưa modular hóa đồng loạt.

Một **JAR thông thường không chứa `module-info.class`**, khi dùng làm module trên **module path**, có thể được nhận diện thành **automatic module**. Công cụ tổng hợp descriptor và cấp tên, nhờ đó một explicit named module có thể ghi `requires tên.automatic;`.

Automatic module:

1. **Có tên** và tham gia module graph như named module.
2. Tự **export tất cả package** trong JAR.
3. Tự **open tất cả package** để hỗ trợ nhiều cách dùng reflection của thư viện cũ.
4. Có quan hệ đọc rộng nhằm tương thích thư viện cũ, bao gồm các named modules khác và unnamed module theo quy tắc JPMS.
5. Không chứa descriptor explicit từ tác giả, nên **chưa thiết kế ranh giới API/module chặt** như một explicit module.

Đừng đồng nhất “automatic module” với “JAR tự tải dependency trên mạng”. JPMS không phải trình tải thư viện; Maven/Gradle và công cụ quản lý dependency phụ trách tải artifact. Automatic module là cách **JAR được nhìn nhận trong module graph**.

### Tên automatic module có thể đến từ hai nguồn

Nếu manifest có:

~~~text
Automatic-Module-Name: legacy.math
~~~

thì JAR được nhận diện bằng tên `legacy.math` khi đóng vai trò automatic module. Nếu không có thuộc tính, tên có thể **suy ra từ tên tệp JAR** theo quy tắc chuẩn hóa (bao gồm xử lý phiên bản ở cuối tên).

Chẳng hạn `legacy-math-1.0.jar` thường được suy thành `legacy.math`, nhưng dựa vào tên suy ra khiến hợp đồng `requires` dễ bị tác động khi đổi tên file. Manifest `Automatic-Module-Name` là cách hữu ích để **ổn định tên trong giai đoạn chuyển tiếp**.

Thuộc tính này **không tự tạo `module-info.class`** và không biến JAR thành explicit named module. Khi thư viện được modular hóa hoàn chỉnh, cần descriptor tường minh để xác định dependency, exports/opens thích hợp.

## 6. Ví dụ: JAR thường thành automatic module

Chúng ta dùng một JAR chứa `legacy.math.LegacyMath`. JAR không có module descriptor, nhưng manifest chỉ định tên module `legacy.math`. Ứng dụng tiêu thụ là explicit named module `org.example.consumer`.

Cây bổ sung vào `module-demo`:

~~~text
src/
├── legacy/legacy/math/LegacyMath.java
└── org.example.consumer/
    ├── module-info.java
    └── org/example/consumer/Main.java

automatic.mf
out/
├── legacy/
└── consumer/
mods/
└── legacy-math-1.0.jar  (sẽ được tạo)
~~~

**`src/legacy/legacy/math/LegacyMath.java`:**

~~~java
package legacy.math;

public final class LegacyMath {
    private LegacyMath() {
    }

    public static int triple(int value) {
        return value * 3;
    }
}
~~~

Không tạo `module-info.java` cho thư viện này.

**`automatic.mf`** là tệp manifest văn bản, có newline ở cuối và một dòng trống kết thúc:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: legacy.math

~~~

**`src/org.example.consumer/module-info.java`:**

~~~java
module org.example.consumer {
    requires legacy.math;
}
~~~

**`src/org.example.consumer/org/example/consumer/Main.java`:**

~~~java
package org.example.consumer;

import legacy.math.LegacyMath;

public class Main {
    public static void main(String[] args) {
        System.out.println("Triple = " + LegacyMath.triple(7));
    }
}
~~~

Tạo trước thư mục `out/legacy` và `out/consumer`, và bảo đảm `mods` đã tồn tại. Biên dịch thư viện như JAR thường rồi đóng gói:

~~~sh
javac -encoding UTF-8 -d out/legacy src/legacy/legacy/math/LegacyMath.java
jar --create --file mods/legacy-math-1.0.jar --manifest automatic.mf -C out/legacy .
~~~

Kiểm tra:

~~~sh
jar --list --file mods/legacy-math-1.0.jar
jar --describe-module --file mods/legacy-math-1.0.jar
~~~

JAR phải có entry `legacy/math/LegacyMath.class`, **không có `module-info.class`**, và được công cụ mô tả là automatic module có tên `legacy.math`. Chi tiết cách in `jar --describe-module` thay đổi theo JDK, nên không giả định một bản stdout cố định.

Tiếp tục biên dịch explicit named module tiêu thụ:

~~~sh
javac -encoding UTF-8 --module-path mods -d out/consumer src/org.example.consumer/module-info.java src/org.example.consumer/org/example/consumer/Main.java
jar --create --file mods/org.example.consumer.jar -C out/consumer .
java --module-path mods --module org.example.consumer/org.example.consumer.Main
~~~

Kết quả:

~~~text
Triple = 21
~~~

Vậy một named module tường minh có thể sử dụng một thư viện cũ **chưa có `module-info.java`**, miễn JAR đó được nhận diện là automatic module trên module path và có tên mà `requires` dùng được.

**Phân biệt hai tình huống:** Nếu để `legacy-math-1.0.jar` chỉ trên classpath, nó không cung cấp named module `legacy.math` cho mệnh đề `requires legacy.math;`. Khi đó lệnh biên dịch module consumer có thể báo không tìm được module. Không thể chỉ thay `--module-path` bằng `-cp` mà giữ nguyên descriptor.

## 7. Readability, exports và opens

Ba khái niệm hay bị gộp nhầm:

**Readability:** Có đường đọc giữa hai module không? Descriptor explicit dùng `requires` để khai báo dependency. Nếu thiếu `requires` (hoặc cơ chế thiết lập quan hệ tương đương), module không nhất thiết được phép tham chiếu module khác dù JAR có nằm trên module path.

**Exports:** Package có được lộ ra cho truy cập thông thường từ module khác không? Trong explicit module, `exports org.example.greetings.api;` cho phép các kiểu public hợp lệ trong package đó xuất hiện trong API tiêu thụ. Một package không export vẫn bị che khỏi việc truy cập thông thường từ module khác.

**Opens:** Package có được mở cho reflection sâu không? Trong explicit module có thể dùng `opens some.package;` hoặc các biến thể có phạm vi phù hợp. `exports` không đồng nghĩa code bên ngoài được reflection truy cập mọi field private.

Ví dụ descriptor minh họa:

~~~java
module org.example.greetings {
    exports org.example.greetings.api;
    opens org.example.greetings.internal;
}
~~~

**Đây chỉ là đoạn minh họa**, không phải file chạy độc lập của bài thực hành: cần có package `org.example.greetings.internal` thật khi dùng cấu hình đó.

Unnamed module và automatic module có các ranh giới export/open rộng để tương thích code truyền thống. Khi nâng một JAR từ automatic thành explicit module, framework dùng reflection có thể cần thêm `opens` đúng chỗ; không thể giả định ứng dụng tiếp tục chạy y nguyên dù compile thành công.

Một lưu ý nữa: **named module không tự động thấy mọi JAR trên module path**. Hệ thống trước hết phải resolve những module cần thiết vào đồ thị; `--add-modules` có thể được dùng trong một số tình huống để thêm module gốc.

## 8. Classpath, module path và cách khởi chạy

| Công cụ/cú pháp | Mục đích |
| --- | --- |
| `javac -cp path ...` | Cho compiler tìm các lớp/JAR trên classpath |
| `java -cp path MainClass` | Chạy lớp main theo cơ chế classpath truyền thống |
| `javac --module-path path ...` | Cho compiler tìm các modules để resolve |
| `java --module-path path --module name/pkg.Main` | Chạy điểm vào ở named module |
| `java -p path -m name/pkg.Main` | Viết ngắn của hai tùy chọn liên quan module |
| `jar --describe-module --file file.jar` | Xem module descriptor/nội dung module được công cụ nhận dạng |

Ví dụ hai lệnh tương đương:

~~~sh
java --module-path mods --module org.example.app/org.example.app.Main
java -p mods -m org.example.app/org.example.app.Main
~~~

Khi classpath hoặc module path gồm **nhiều phần tử**, Linux/macOS dùng dấu `:` phân tách, Windows dùng `;`. Nhưng trong ví dụ module path chỉ gồm một thư mục `mods`, nên không cần dấu phân tách.

Lưu ý với classpath app dùng named module: **unnamed module có thể đọc các named modules đã được resolve**, nhưng chỉ đưa một JAR lên module path chưa chắc module đó đã được resolve theo cấu hình chạy. Trong một số trường hợp, thêm module đích vào root set bằng `--add-modules`:

~~~sh
java --module-path mods --add-modules org.example.greetings -cp out/classapp LegacyMain
~~~

Lệnh minh họa này dựa trên `LegacyMain.class` và JAR named module đã tạo ở phần trước. Nếu compile code classpath tham chiếu tới named module, cấu hình `javac` cũng cần được thiết lập nhất quán; đừng tưởng cờ runtime tự sửa được vấn đề compile-time.

## 9. Các lỗi phổ biến khi phối hợp module và JAR

| Triệu chứng | Cần xem lại |
| --- | --- |
| `module not found: legacy.math` | JAR automatic có trên module path không, tên thực tế là gì? |
| `package ... is not visible` | Module đọc được dependency chưa và package có được export không? |
| `Could not find or load main class` | Đang dùng `-cp` hay `-m`; tên class và classpath root đúng không? |
| `NoClassDefFoundError` | Thiếu class runtime hoặc có lỗi tải/khởi tạo dependency |
| `Error occurred during initialization of boot layer` | Module resolution, module trùng, split package, cấu hình path |
| Reflection bị từ chối truy cập | Kiểm tra `opens`/quy tắc module, không chỉ `exports` |

**Split package:** Một package xuất hiện trong hai named modules được resolve có thể làm quá trình resolution không hợp lệ. Ví dụ nếu hai JAR khác nhau cùng chứa `com/example/shared/...` rồi đều trở thành named modules, sự chia package có thể gây xung đột. Điều này ít được phát hiện khi chỉ thử chúng trên classpath kiểu cũ; trước khi chuyển hàng loạt JAR vào module path, cần kiểm tra package trùng.

**Trùng tên automatic modules:** Hai JAR có thể suy ra cùng tên module từ tên file hoặc manifest; đây là vấn đề khác với trùng package. Hãy xem `jar --describe-module` từng artifact và tránh vô tình đưa hai phiên bản dependency vào cùng đường dẫn.

**Không có `module-info.class` không có nghĩa chắc chắn unnamed module.** JAR thường có thể là unnamed khi đặt ở classpath hoặc automatic khi đặt ở module path. Vị trí và cách module được resolve quyết định.

**Không phải mọi lỗi class loading đều do JPMS.** Các lỗi phiên bản `.class`, tương thích API, khởi tạo static hoặc missing dependencies vẫn có thể xảy ra ngay cả khi module graph hợp lệ.

### Các câu hỏi kiểm tra khi build không thành công

1. Tôi đang biên dịch **explicit named module** hay mã trên classpath?
2. JAR cần dùng nằm ở **classpath** hay **module path**?
3. JAR có descriptor module tường minh chưa? Nếu không, tên automatic được xác định thế nào?
4. Descriptor của module tiêu thụ có `requires` đúng tên không?
5. Module thư viện có export đúng package API không?
6. Nếu reflection lỗi, package có cần `opens` không?
7. Có duplicate module name hoặc split package trên module path không?
8. Tại runtime, tôi có dùng **đúng JAR và module path** như khi compile không?

Việc kiểm tra đúng thứ tự giúp tránh cách sửa mò như thêm mọi JAR vào cả `-cp` lẫn `--module-path` hoặc mở toàn bộ package không cần thiết.

## 10. Cách tiếp cận khi chuyển dự án cũ sang JPMS

Không cần chuyển toàn bộ dự án lên module path ngay lập tức. Có thể làm từng bước:

1. **Lập danh sách dependency** và phiên bản thật được build/runtime sử dụng.
2. **Xem descriptor/tên tự động** từng JAR bằng `jar --describe-module`; ưu tiên thư viện có tên ổn định.
3. **Tách API và implementation** để biết package nào cần export, reflection nào cần open.
4. **Modular hóa code mình kiểm soát** bằng `module-info.java` và `requires`, `exports` phù hợp.
5. **Dùng automatic modules có chủ đích** cho JAR thư viện chưa hỗ trợ module tường minh.
6. **Kiểm tra split packages, service loading và reflection**, không chỉ xem build xanh.
7. **Chạy thử artifact thật** trên môi trường đích; compile classpath/module path phải nhất quán với runtime.
8. **Giảm biện pháp tạm** như `--add-opens` nếu có thể thay bằng thiết kế module hoặc nâng phiên bản thư viện.

Automatic module là **cây cầu chuyển tiếp**, không phải trạng thái tối ưu bắt buộc. Việc thay thế bằng explicit named module đòi hỏi định nghĩa hợp đồng API và truy cập rõ ràng.

## 11. Bài tập thực hành

**Bài 1 — Hai explicit named modules.** Tạo `Greeter` và `Main` trong phần 3. Chạy `jar --describe-module` và xác nhận dependency `requires`. Chạy để lấy stdout `Hello, Lan`.

**Bài 2 — Bỏ export.** Xóa `exports` từ descriptor thư viện, build lại thư viện và app. Giải thích tại sao `public class Greeter` vẫn không truy cập được qua module boundary.

**Bài 3 — Cùng JAR, hai cơ chế.** Đưa `org.example.greetings.jar` vào `-cp` rồi chạy `LegacyMain`. Chứng minh việc có `module-info.class` trong JAR chưa đủ để nó trở thành named module khi được dùng trên classpath.

**Bài 4 — Automatic module.** Tạo `legacy-math-1.0.jar` có `Automatic-Module-Name: legacy.math` nhưng không có `module-info.class`; dùng `jar --describe-module` rồi compile/run `org.example.consumer` với `requires legacy.math;`.

**Bài 5 — Đổi path.** Thử đưa JAR automatic khỏi `mods` rồi chạy module tiêu thụ. Dự đoán lúc nào báo thiếu module; sửa lại module path, không sửa logic của `LegacyMath`.

**Bài 6 — Ranh giới API.** Giả sử thư viện cũ có `api` và `internal`, đồng thời framework cần reflection vào `internal`. Khi tạo explicit descriptor, nêu những package cần `exports`, những package cần `opens` và vì sao không nên mở tất cả vô điều kiện.

### Tự đánh giá

1. **Automatic module có phải named module không?** — Có; tên và descriptor tổng hợp được cung cấp theo cơ chế automatic module.
2. **Unnamed module được tạo từ đâu?** — Từ mã được nạp theo classpath bởi class loader tương ứng.
3. **Một named module có `requires` unnamed module được không?** — Không; unnamed module không có tên để ghi trong descriptor.
4. **`module-info.java` dùng để làm gì?** — Khai báo module explicit, dependency và ranh giới export/open.
5. **`Automatic-Module-Name` có làm JAR thành explicit module không?** — Không; nó chỉ giúp đặt tên ổn định cho automatic module.
6. **Vì sao `public` chưa đủ để truy cập lớp khác module?** — Cần quan hệ đọc và package được export theo JPMS.
7. **`-cp` với `--module-path` có tương đương không?** — Không; mô hình nạp lớp/giải quyết module khác nhau.
8. **Automatic module export/open những gì?** — Mọi package theo quy tắc tương thích của automatic module.
9. **Làm sao biết tên module thực tế của một JAR?** — Kiểm tra `jar --describe-module --file ...` và manifest khi cần.
10. **Rủi ro chính khi đưa JAR cũ lên module path?** — Tên module suy ra thiếu ổn định, module/package trùng, dependency và reflection không tương thích.

**Kết luận:** Explicit named module mô tả ranh giới và phụ thuộc một cách chủ động; unnamed module duy trì mô hình classpath truyền thống; automatic module giúp JAR cũ có tên trong module graph mà chưa phải viết descriptor. Phân biệt ba trường hợp giúp bạn hiểu đúng lỗi tìm module, lỗi export/package và cách tổ chức biên dịch/triển khai Java hiện đại.