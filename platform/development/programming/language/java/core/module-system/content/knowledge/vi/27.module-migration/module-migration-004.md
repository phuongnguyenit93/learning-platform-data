# Chuyển thư viện sang module path từng phần

Khi một dự án Java lâu năm dùng classpath, các JAR thường được đặt chung vào một danh sách đường dẫn và ứng dụng có thể tham chiếu những class public của chúng mà không khai báo quan hệ module rõ ràng. Java Platform Module System (JPMS), được giới thiệu từ Java 9, bổ sung **module path**, **named module**, **module descriptor** và các quy tắc về readability, exports và service loading.

Trong thực tế, hiếm khi có thể chuyển tất cả thư viện sang JPMS trong một lần. Một số JAR đã có `module-info.class`, một số chỉ có `Automatic-Module-Name`, còn nhiều thư viện vẫn là JAR truyền thống. Cách tiếp cận thực dụng là **di chuyển từng phần**, giữ ứng dụng chạy được qua từng giai đoạn và biến các dependency thành named module khi đã đủ điều kiện.

Bài học này mô tả một lộ trình từng bước: **classpath → automatic module trên module path → ứng dụng có module-info.java → thư viện explicit module**, cùng phương pháp kiểm tra sau mỗi lần chuyển.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt classpath, unnamed module, module path, automatic module và explicit named module.
- Chuyển một JAR truyền thống sang module path mà chưa cần viết ngay `module-info.java`.
- Kiểm tra tên module thật của JAR và cố định tên bằng `Automatic-Module-Name`.
- Chạy ứng dụng classpath có sử dụng thư viện trên module path.
- Chuyển ứng dụng thành explicit named module với `requires`.
- Hiểu khi nào phải tiếp tục di chuyển dependency còn nằm trên classpath.
- Phát hiện split package, thiếu module, sai tên module và rắc rối về exports/services.
- Lập kế hoạch migration có bước kiểm chứng và đường quay lui rõ ràng.

## 1. Vì sao nên chuyển dần?

Một ứng dụng có thể có đồ thị dependency như sau:

~~~text
com.acme.app
  ├── acme-math.jar
  ├── acme-client.jar
  │     └── legacy-http.jar
  └── acme-report.jar
        └── thirdparty-util.jar
~~~

Trong mô hình classpath, các JAR có thể được cung cấp bằng một tham số `-cp`:

~~~bash
java -cp "app.jar:libs/*" com.acme.app.Main
~~~

Trên Windows, dấu phân cách classpath là dấu chấm phẩy:

~~~powershell
java -cp "app.jar;libs/*" com.acme.app.Main
~~~

Khi dùng JPMS, các module được resolve với tên và dependency. Nếu đồng thời yêu cầu mọi JAR chuyển thành explicit module, dự án có thể vướng:

- Thư viện chưa phát hành descriptor.
- Tên module chưa ổn định.
- Package trùng giữa các dependency.
- Dependency chỉ hoạt động qua reflection hoặc SPI.
- Framework trông đợi thread context class loader.
- Mã ứng dụng đang trực tiếp gọi class thuộc classpath mà named module không đọc được.

Chuyển từng phần giúp khoanh vùng lỗi: mỗi lần di chuyển một nhóm JAR, biên dịch, chạy smoke test và kiểm tra graph trước khi chuyển nhóm tiếp theo.

## 2. Năm khái niệm cần tách bạch

| Khái niệm | Ý nghĩa thực tế |
|---|---|
| Classpath | Tập thư mục/JAR truyền thống, thường được cung cấp bằng `-cp` hoặc `--class-path` |
| Unnamed module | Các class do một class loader nạp từ classpath thuộc unnamed module của loader đó |
| Module path | Nguồn tìm các named module, cung cấp bằng `-p` hoặc `--module-path` |
| Automatic module | JAR không có descriptor, được đặt trên module path và tự nhận danh tính named module |
| Explicit named module | Module có descriptor `module-info.class` xác định tên và các chỉ thị như `requires`, `exports` |

### 2.1. Automatic module là cầu nối migration

Một JAR truyền thống không có `module-info.class` có thể được đặt trên module path để Java coi nó là **automatic module**.

Automatic module:

- Có module name do manifest hoặc filename xác định.
- Được xem là export các package của nó.
- Có khả năng đọc các module đã được resolve và unnamed module, tạo thuận lợi cho migration.
- Không có các chỉ thị `requires`/`exports` được khai báo tường minh như explicit module.

Điều đó **không có nghĩa JAR đã được modular hóa hoàn chỉnh**. Automatic module vẫn thiếu hợp đồng module rõ ràng, và tên module suy ra từ filename có thể thay đổi khi nhà phát hành đổi cách đặt tên artifact.

### 2.2. Explicit named module có ranh giới chặt hơn

Ví dụ một thư viện explicit module:

~~~java
module com.acme.math {
    exports com.acme.math;
}
~~~

Ứng dụng modular sử dụng nó:

~~~java
module com.acme.app {
    requires com.acme.math;
}
~~~

Named module không thể khai báo `requires` tới unnamed module thông thường. Vì thế, khi chuyển **ứng dụng** thành explicit named module, phải đảm bảo các thư viện mà ứng dụng trực tiếp dùng có thể được nhìn thấy dưới dạng named module (explicit hoặc automatic), hoặc có giải pháp chuyển tiếp được kiểm soát.

## 3. Nguyên tắc chọn thứ tự chuyển thư viện

Nên bắt đầu từ **dependency nằm thấp trong graph**, thường là các utility hoặc library ít phụ thuộc module khác. Sau khi chúng ổn định trên module path, mới chuyển các thư viện cấp cao hơn và cuối cùng là ứng dụng chính.

Ví dụ:

~~~text
                 com.acme.app
                  /        \
                 v          v
           acme-client    acme-report
                 |          |
                 v          v
            legacy-http  thirdparty-util
~~~

Thứ tự hợp lý có thể là:

1. Kiểm kê tên module và package của `legacy-http`, `thirdparty-util`.
2. Chuyển các dependency thấp tầng lên module path nếu không xung đột.
3. Chuyển `acme-client` và `acme-report` thành automatic/explicit module.
4. Chuyển `com.acme.app` thành explicit module khi các kiểu app dùng trực tiếp đã nằm trong named modules.
5. Thay thế automatic module bằng explicit module theo từng thư viện khi có descriptor phù hợp.

Đây là **chiến lược gợi ý**, không phải quy tắc buộc mọi dự án phải chuyển chính xác theo thứ tự trên. Một library có split package hoặc framework đặc biệt có thể phải xử lý trước.

## 4. Kiểm kê trước khi migration

Trước khi thay đổi lệnh chạy, lập bảng cho mỗi dependency:

| Thông tin | Cách xác định |
|---|---|
| JAR đang ở classpath hay module path? | Lệnh chạy thật, cấu hình IDE và build |
| Có `module-info.class` không? | `jar --describe-module` |
| Tên module thực tế là gì? | `jar --describe-module --file ...` |
| Có `Automatic-Module-Name` không? | Manifest của JAR |
| Các package được chứa? | `jar tf ...` |
| Có service provider/resource/reflection không? | Mã nguồn và runtime configuration |
| Dependency phụ thuộc library nào? | `jdeps`, Maven/Gradle dependency graph |

Kiểm tra descriptor hoặc tên automatic module:

~~~bash
jar --describe-module --file libs/acme-math.jar
~~~

Liệt kê class trong JAR:

~~~bash
jar tf libs/acme-math.jar
~~~

Phân tích dependency tĩnh của ứng dụng classpath:

~~~bash
jdeps --print-module-deps --class-path "libs/*" app.jar
~~~

`jdeps` không phát hiện mọi dependency được nạp bằng tên class, reflection hoặc plugin; cần kết hợp với cấu hình runtime và test thực tế.

Với Maven:

~~~bash
mvn dependency:tree
~~~

Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Trên Windows có thể dùng `gradlew.bat`. Mục tiêu của bước này là xác định rõ artifact nào đang được dùng, tránh giữ hai bản cùng thư viện trên các path khác nhau.

## 5. Ví dụ thực hành: thư viện math cũ

Ta sẽ tạo một thư viện JAR truyền thống, sau đó lần lượt chuyển nó và ứng dụng sang JPMS. Ví dụ dùng Java 17 trở lên và chạy từ thư mục dự án.

Ban đầu:

~~~text
project/
├── legacy-src/
│   └── com/acme/math/TaxCalculator.java
├── app-src/
│   └── com/acme/app/Main.java
├── libs/
└── out/
~~~

Thư viện:

~~~java
// legacy-src/com/acme/math/TaxCalculator.java
package com.acme.math;

public final class TaxCalculator {
    private TaxCalculator() {}

    public static int totalWithTax(int amount, int taxPercent) {
        return amount + amount * taxPercent / 100;
    }
}
~~~

Ứng dụng:

~~~java
// app-src/com/acme/app/Main.java
package com.acme.app;

import com.acme.math.TaxCalculator;

public class Main {
    public static void main(String[] args) {
        System.out.println(TaxCalculator.totalWithTax(100, 10));
    }
}
~~~

### 5.1. Biên dịch JAR theo cách classpath

Biên dịch thư viện:

~~~bash
javac -d out/math legacy-src/com/acme/math/TaxCalculator.java
~~~

Đóng gói JAR truyền thống:

~~~bash
jar --create --file libs/acme-math.jar -C out/math .
~~~

Biên dịch ứng dụng:

~~~bash
javac -cp libs/acme-math.jar -d out/app app-src/com/acme/app/Main.java
~~~

Chạy trên Linux/macOS:

~~~bash
java -cp "out/app:libs/acme-math.jar" com.acme.app.Main
~~~

Chạy trên Windows:

~~~powershell
java -cp "out/app;libs/acme-math.jar" com.acme.app.Main
~~~

Kết quả:

~~~text
110
~~~

Đây là trạng thái khởi đầu để so sánh khi chuyển sang module path.

## 6. Bước 1: gán tên module ổn định cho thư viện

Nếu đưa `acme-math.jar` không có descriptor vào module path, Java có thể suy tên automatic module từ filename. Tên suy ra có thể gây bất ngờ hoặc thay đổi theo cách đặt tên file.

Để kiểm soát migration, nhà phát hành thư viện có thể thêm manifest:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.acme.math

~~~

Lưu nội dung vào file `math.mf` (có dòng kết thúc phù hợp), sau đó tạo lại JAR:

~~~bash
jar --create --file libs/acme-math.jar \
    --manifest math.mf \
    -C out/math .
~~~

Trên Windows PowerShell:

~~~powershell
jar --create --file libs/acme-math.jar --manifest math.mf -C out/math .
~~~

Xác minh:

~~~bash
jar --describe-module --file libs/acme-math.jar
~~~

JAR chưa có `module-info.class` nhưng giờ có tên automatic module ổn định là `com.acme.math`.

**Lưu ý:** `Automatic-Module-Name` chỉ cung cấp tên module. Nó không khai báo `requires` hoặc `exports` thực sự, cũng không tự sửa split package.

## 7. Bước 2: chuyển JAR sang module path, app vẫn ở classpath

Giữ mã và class của ứng dụng trong classpath, nhưng đặt JAR `acme-math.jar` trên module path.

Lệnh chạy trên Linux/macOS:

~~~bash
java --module-path libs/acme-math.jar \
     --add-modules com.acme.math \
     --class-path out/app \
     com.acme.app.Main
~~~

Lệnh tương đương một dòng (dùng được trên Windows):

~~~powershell
java --module-path libs/acme-math.jar --add-modules com.acme.math --class-path out/app com.acme.app.Main
~~~

Kết quả mong đợi vẫn là:

~~~text
110
~~~

### 7.1. Vì sao cần --add-modules?

Khi chạy main class từ classpath, ứng dụng nằm trong unnamed module. Một application module đặt trên module path **không nhất thiết tự được resolve** chỉ vì JAR xuất hiện trên path.

`--add-modules com.acme.math` bổ sung automatic module đó làm root cần resolve, cho phép classpath application sử dụng các class mà module đã công bố.

Nếu thư viện không nằm trong tập module được resolve, lệnh chạy có thể không tìm được class dù JAR có mặt trên module path. Bởi vậy cần kiểm tra cả **module path** và **root modules**.

### 7.2. Có cần đổi import không?

Không. Tên Java class vẫn là:

~~~java
import com.acme.math.TaxCalculator;
~~~

Việc chuyển JAR từ classpath sang module path không tự đổi tên package hoặc class.

### 7.3. Những gì đã thay đổi?

Trước:

~~~text
Unnamed module (app + acme-math)
~~~

Sau:

~~~text
Unnamed module (app)
        |
        | sử dụng public API
        v
Automatic named module: com.acme.math
~~~

Đây là bước trung gian quan trọng: ứng dụng chưa cần `module-info.java` nhưng đã kiểm chứng rằng thư viện có thể tham gia module graph.

## 8. Bước 3: chuyển ứng dụng thành explicit named module

Khi các thư viện app sử dụng trực tiếp đã có tên module ổn định, có thể bổ sung `module-info.java` cho ứng dụng.

Chuyển mã app sang cấu trúc module source path:

~~~text
project/
└── src/
    └── com.acme.app/
        ├── module-info.java
        └── com/acme/app/Main.java
~~~

`module-info.java`:

~~~java
module com.acme.app {
    requires com.acme.math;
}
~~~

`Main.java` vẫn như trước:

~~~java
package com.acme.app;

import com.acme.math.TaxCalculator;

public class Main {
    public static void main(String[] args) {
        System.out.println(TaxCalculator.totalWithTax(100, 10));
    }
}
~~~

Biên dịch app với thư viện automatic module:

~~~bash
javac --module-path libs/acme-math.jar \
      --module-source-path src \
      -d out/mods \
      -m com.acme.app
~~~

Lệnh một dòng:

~~~bash
javac --module-path libs/acme-math.jar --module-source-path src -d out/mods -m com.acme.app
~~~

Chạy trên Linux/macOS:

~~~bash
java --module-path "out/mods:libs/acme-math.jar" \
     -m com.acme.app/com.acme.app.Main
~~~

Chạy trên Windows:

~~~powershell
java --module-path "out/mods;libs/acme-math.jar" -m com.acme.app/com.acme.app.Main
~~~

Kết quả:

~~~text
110
~~~

Ở giai đoạn này:

- Ứng dụng đã là explicit named module `com.acme.app`.
- Thư viện vẫn là automatic named module `com.acme.math`.
- App có quan hệ đọc rõ ràng nhờ `requires com.acme.math;`.
- Package của thư viện automatic được export theo quy tắc automatic module.

### 8.1. Tại sao không giữ mọi dependency trên classpath?

Named module `com.acme.app` không thể khai báo một dòng `requires` hợp lệ tới unnamed module. Nếu app trực tiếp dùng class ở JAR còn nằm trên classpath, compiler có thể báo package không hiển thị hoặc module không đọc được unnamed module.

Do đó trước khi chuyển app, phải xử lý ít nhất các dependency mà mã app truy cập trực tiếp: di chuyển chúng lên module path dưới dạng explicit/automatic module hoặc thay đổi kiến trúc để chúng nằm sau một abstraction phù hợp.

Có thể tồn tại workaround như `--add-reads com.acme.app=ALL-UNNAMED` trong một số tình huống legacy, nhưng không nên xem đây là thiết kế cuối cùng vì nó bỏ qua lợi ích của dependency được khai báo rõ ràng.

## 9. Bước 4: đổi thư viện automatic thành explicit module

Sau khi app hoạt động ổn định với automatic module, ta có thể modular hóa chính thư viện. Ví dụ, chuyển source thư viện về:

~~~text
lib-src/
└── com.acme.math/
    ├── module-info.java
    └── com/acme/math/TaxCalculator.java
~~~

Descriptor của thư viện:

~~~java
module com.acme.math {
    exports com.acme.math;
}
~~~

`TaxCalculator.java` giữ nguyên package và public API.

Biên dịch thư viện:

~~~bash
javac --module-source-path lib-src \
      -d out/libs \
      -m com.acme.math
~~~

Đóng gói modular JAR:

~~~bash
jar --create --file libs/acme-math-modular.jar \
    -C out/libs/com.acme.math .
~~~

Xác minh descriptor:

~~~bash
jar --describe-module --file libs/acme-math-modular.jar
~~~

Biên dịch lại app bằng modular JAR mới:

~~~bash
javac --module-path libs/acme-math-modular.jar \
      --module-source-path src \
      -d out/mods \
      -m com.acme.app
~~~

Chạy trên Linux/macOS:

~~~bash
java --module-path "out/mods:libs/acme-math-modular.jar" \
     -m com.acme.app/com.acme.app.Main
~~~

Trên Windows:

~~~powershell
java --module-path "out/mods;libs/acme-math-modular.jar" -m com.acme.app/com.acme.app.Main
~~~

Kết quả vẫn là:

~~~text
110
~~~

**Quan trọng:** Khi chuyển sang explicit module, các package không khai báo `exports` sẽ không còn tự được export như automatic module. Vì thế, cần thiết kế public API cẩn thận và cập nhật descriptor phù hợp.

Không đặt **cả** `acme-math.jar` và `acme-math-modular.jar` trên cùng module path khi chúng cùng cung cấp module `com.acme.math`. Loại bỏ bản cũ khỏi cấu hình trước khi kiểm tra phiên bản mới.

## 10. Khi còn nhiều thư viện chưa modular hóa

Trong ứng dụng thực tế, cấu trúc trung gian có thể là:

~~~text
                Explicit named module: com.acme.app
                        |
                  requires
                        v
                Automatic module: com.acme.client
                        |
               legacy implementation
                        v
                 Unnamed module
                    (classpath)
~~~

Automatic module được thiết kế để hỗ trợ một số dependency legacy từ unnamed module, nên có thể đóng vai trò cầu nối trong giai đoạn chuyển đổi. Tuy nhiên, explicit named module của app không nên trực tiếp dựa vào class trong unnamed module nếu muốn có graph bền vững.

Hãy phân biệt:

- **App trực tiếp import class trong JAR còn ở classpath:** cần chuyển JAR hoặc thiết kế lại dependency trước khi modular hóa app.
- **App chỉ gọi API của automatic module, còn implementation của module này dùng classpath dependency:** có thể là trạng thái migration tạm thời, nhưng cần kiểm thử thật.
- **Library chuyển từ automatic sang explicit:** thư viện không còn tự nhận quyền đọc unnamed module như trước; các dependency thực tế phải được khai báo và di chuyển phù hợp.

Một lộ trình an toàn là lập danh sách các dependency trực tiếp và gián tiếp, rồi chuyển dần cho đến khi graph chính không còn phụ thuộc vào cơ chế truy cập từ automatic module đến classpath.

## 11. Những lỗi thường gặp khi chuyển từng phần

### 11.1. Module not found

Ví dụ:

~~~text
error: module not found: com.acme.math
~~~

Nguyên nhân có thể là:

- JAR không nằm trên `--module-path` trong lệnh biên dịch/chạy.
- Tên module khác với tên được viết trong `requires`.
- Build đang dùng JAR khác hoặc phiên bản khác.
- Dependency chỉ xuất hiện trong cấu hình IDE, không có trong lệnh chạy thực tế.

Kiểm tra:

~~~bash
jar --describe-module --file libs/acme-math.jar
~~~

Và kiểm tra lại toàn bộ `--module-path`.

### 11.2. NoClassDefFoundError hoặc ClassNotFoundException

Trường hợp một JAR đã lên module path nhưng chưa được resolve có thể khiến class không được tìm thấy từ ứng dụng classpath.

Nếu app vẫn chạy từ classpath, xem xét root modules qua `--add-modules`:

~~~bash
java --module-path libs/acme-math.jar \
     --add-modules com.acme.math \
     --class-path out/app com.acme.app.Main
~~~

Nếu module đã được resolve, tiếp tục kiểm tra class có nằm trong JAR không, class loader nào đang nạp class và dependency bắc cầu có đầy đủ không.

### 11.3. Package is not visible

Với explicit module, một package phải được export từ module cung cấp và module sử dụng phải đọc module đó.

Ví dụ:

~~~java
module com.acme.math {
    exports com.acme.math.api;
}
~~~

~~~java
module com.acme.app {
    requires com.acme.math;
}
~~~

Nếu app import package `com.acme.math.internal` mà thư viện không export, compiler có thể từ chối. Đây là ranh giới đóng gói của JPMS, không phải dấu hiệu JAR hỏng.

### 11.4. Split package

Hai JAR có thể chứa cùng một package, ví dụ:

~~~text
acme-core.jar
└── com/acme/shared/Util.class

acme-extra.jar
└── com/acme/shared/Helper.class
~~~

Khi cùng trở thành named module và tham gia graph, split package có thể gây lỗi resolution hoặc truy cập. Hãy xác định module nào sở hữu package, sau đó đổi package, hợp nhất module hoặc nâng cấp dependency phù hợp.

`--add-exports` không tự giải quyết split package, vì nó thay đổi quyền export chứ không đổi ownership của package.

### 11.5. Duplicate module name

Hai JAR trên module path có thể có tên module trùng nhau, ví dụ cả hai khai báo `Automatic-Module-Name: com.acme.math`. Kết quả phụ thuộc nguồn tìm và thứ tự cấu hình, nhưng có thể dẫn đến module bị che khuất hoặc lỗi cấu hình.

Không nên giữ đồng thời hai version của cùng một module. Kiểm tra artifact và loại bỏ bản trùng để graph rõ ràng.

### 11.6. Reflection thất bại

Framework dùng reflection có thể gặp `InaccessibleObjectException` sau khi một thư viện trở thành explicit module.

Khi đó, xem xét package nào cần được mở cho framework:

~~~java
module com.acme.app {
    requires com.acme.framework;

    opens com.acme.app.model to com.acme.framework;
}
~~~

`exports` dành cho quyền truy cập public API thông thường; `opens` phục vụ deep reflection vào thành viên không public theo điều kiện thích hợp.

Dùng qualified opens nếu chỉ một framework module cần truy cập, tránh mở toàn bộ implementation.

### 11.7. ServiceLoader không tìm thấy provider

Các hệ thống plugin thường dùng `ServiceLoader`. Khi chuyển sang explicit named module, service contract nên được mô tả rõ:

Module sử dụng service:

~~~java
module com.acme.app {
    requires com.acme.spi;
    uses com.acme.spi.PaymentProvider;
}
~~~

Module cung cấp implementation:

~~~java
module com.acme.payment.impl {
    requires com.acme.spi;
    provides com.acme.spi.PaymentProvider
        with com.acme.payment.internal.DefaultPaymentProvider;
}
~~~

Để provider được tìm thấy, provider module phải có mặt trong configuration/layer phù hợp và được giải quyết theo cách tương thích với cơ chế service loading.

Đừng chỉ chuyển JAR giữa các path mà không kiểm tra lại `META-INF/services`, descriptor và cơ chế khởi tạo provider.

## 12. Các công cụ theo dõi migration

### 12.1. jar --describe-module

~~~bash
jar --describe-module --file libs/acme-math.jar
~~~

Dùng để biết JAR là explicit hay automatic module và tên module thực tế.

### 12.2. java --list-modules

~~~bash
java --module-path libs --list-modules
~~~

Liệt kê các module observable từ runtime/module path của lệnh gọi. Một module có tên trong danh sách không nhất thiết đã được resolve vào boot layer của ứng dụng.

### 12.3. --show-module-resolution

~~~bash
java --module-path "out/mods:libs" \
     --show-module-resolution \
     -m com.acme.app/com.acme.app.Main
~~~

Trên Windows, thay `:` bằng `;`. Dùng log để xác định module root, dependency và module nào thực sự tham gia graph khởi động.

### 12.4. java --validate-modules

~~~bash
java --module-path libs --validate-modules
~~~

Hữu ích để phát hiện một số vấn đề module path, chẳng hạn các module gây xung đột hoặc che khuất nhau.

### 12.5. jdeps

Với application JAR truyền thống:

~~~bash
jdeps --class-path "libs/*" --print-module-deps app.jar
~~~

Với named module:

~~~bash
jdeps --module-path "out/mods:libs" --check com.acme.app
~~~

Trên Windows, dùng `;` thay vì `:` trong danh sách nhiều vị trí module path. Kết quả `jdeps` giúp phân tích dependency tĩnh nhưng không thay thế runtime smoke test.

### 12.6. Kiểm tra nội dung JAR

~~~bash
jar tf libs/acme-math.jar
~~~

Tìm package và class được đóng gói thật. Nếu JAR rỗng, class sai package hoặc còn bytecode cũ, việc thay module path không giải quyết được vấn đề.

## 13. Migration trong Maven và Gradle

### 13.1. Maven

Kiểm tra dependencies:

~~~bash
mvn dependency:tree
~~~

Biên dịch và kiểm thử sau mỗi giai đoạn:

~~~bash
mvn clean verify
~~~

Trong dự án Maven, compiler plugin cần dùng cấu hình module path phù hợp với phiên bản JDK và cấu trúc module hiện tại. Đừng giả định mọi plugin hoặc profile của dự án sẽ tự chuyển toàn bộ dependency sang module path đúng như ý muốn.

Nếu có nhiều module Maven tương ứng nhiều JPMS module, hãy phân biệt:

- Maven module: một đơn vị build thuộc reactor.
- JPMS module: một named module được xác định bằng module descriptor hoặc automatic module name.

Hai khái niệm có thể liên hệ nhưng không đồng nghĩa.

### 13.2. Gradle

Kiểm tra dependency graph:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Kiểm thử:

~~~bash
./gradlew clean test
~~~

Một số phiên bản Gradle có khả năng suy luận module path từ `module-info.java` và dependency metadata, nhưng cách xử lý chính xác còn phụ thuộc plugin/cấu hình build. Vì vậy, cần quan sát lệnh compiler và launcher thực tế, không chỉ dựa vào danh sách dependency của build tool.

### 13.3. Giữ một nguồn sự thật cho dependency

Khi chuyển từng phần, tránh cùng một JAR xuất hiện cả trên classpath và module path trong một lần chạy. Tình huống này dễ tạo class identity khác nhau, nhầm version hoặc khiến việc chẩn đoán khó hơn.

Nên ghi nhận rõ dependency nào ở classpath, dependency nào ở module path và bước migration tiếp theo của từng artifact.

## 14. Khi nào nên dùng requires transitive?

Sau khi chuyển một library thành explicit module, nếu public API của library bộc lộ kiểu từ một module khác, cân nhắc `requires transitive`.

Ví dụ:

~~~java
module com.acme.client {
    requires transitive com.acme.model;
    exports com.acme.client.api;
}
~~~

Nếu class trong `com.acme.client.api` có method trả về kiểu public từ `com.acme.model`, các client đọc `com.acme.client` cũng cần nhìn thấy các kiểu model trong API.

`requires transitive` truyền readability; nó không tự export các package không được công bố từ module model.

Không khai báo mọi dependency là transitive một cách máy móc. Chỉ dùng khi module dependency thực sự thuộc hợp đồng API công khai.

## 15. Những điều không nên làm

**Chuyển tất cả JAR lên module path ngay lập tức.**

Một thao tác hàng loạt có thể làm lộ nhiều xung đột cùng lúc. Chuyển từng nhóm dependency nhỏ giúp tìm nguyên nhân rõ ràng hơn.

**Tự suy tên module từ filename.**

Tên automatic module có thể được quyết định bởi manifest. Dùng `jar --describe-module` để xác nhận trước khi viết `requires`.

**Dùng --add-exports thay cho thiết kế module.**

Flag này chỉ thay đổi quyền export ở một số ngữ cảnh. Nó không sửa thiếu JAR, duplicate module name hoặc split package.

**Cho rằng automatic module đã có encapsulation tốt.**

Automatic module được xem là export mọi package. Khi chuyển thành explicit module, hãy xác định package API thật sự và chỉ export những package cần công bố.

**Quên kiểm tra service provider và reflection.**

Một dự án có thể biên dịch thành công nhưng chỉ gặp lỗi lúc framework quét annotation, nạp plugin hoặc service provider. Cần có runtime/integration tests.

**Quên clean build và phân biệt compile/runtime path.**

Class cũ còn trong output hoặc dependency chỉ có ở compile classpath có thể khiến lỗi xuất hiện sau khi triển khai. Dùng đúng runtime artifact để kiểm tra.

**Xem workaround như kiến trúc cuối cùng.**

`--add-reads` hoặc `--add-exports` có thể hữu ích cho migration khó nhưng nên giới hạn phạm vi và có kế hoạch loại bỏ.

## 16. Kế hoạch chuyển đổi theo các mốc kiểm chứng

Một kế hoạch triển khai thực tế có thể chia thành các mốc sau:

| Mốc | Trạng thái | Điều kiện chuyển tiếp |
|---|---|---|
| M0 | Toàn bộ app và dependency chạy trên classpath | Build và smoke test hiện tại chạy ổn định |
| M1 | Một thư viện thấp tầng là automatic module trên module path | App classpath chạy được với `--add-modules` phù hợp |
| M2 | Nhiều dependency đã lên module path | Không có split package/duplicate module trong graph cần dùng |
| M3 | App là explicit named module | `requires` đầy đủ; không phụ thuộc trực tiếp vào unnamed module |
| M4 | Thư viện quan trọng có explicit descriptor | API package được export đúng; reflection/services hoạt động |
| M5 | Build và deployment ổn định trên JPMS | CI và runtime production sử dụng module graph đã kiểm chứng |

### 16.1. Kiểm chứng sau mỗi mốc

Sau mỗi lần chuyển JAR:

1. Ghi lại tên và version artifact mới.
2. Dùng `jar --describe-module` xác nhận module name.
3. Chạy compile theo đúng JDK và module path.
4. Chạy `--show-module-resolution` để xem graph.
5. Chạy test liên quan và smoke test ứng dụng.
6. Kiểm tra class/service loading nếu thư viện có plugin hoặc reflection.
7. Chỉ tiếp tục chuyển dependency tiếp theo khi bước hiện tại chạy ổn định.

Nếu gặp lỗi, quay lại cấu hình classpath/module path của mốc gần nhất đã kiểm chứng, thay vì thêm nhiều flag vá lỗi cùng lúc.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Một JAR chưa có `module-info.class` nhưng được đặt trên module path. Java có thể coi nó là module không?

**Trả lời:** Có. JAR có thể trở thành automatic module; tên module được lấy từ manifest `Automatic-Module-Name` hoặc suy ra theo quy tắc của JDK.

**Câu 2.** App còn chạy từ classpath. Sau khi chuyển `acme-math.jar` lên module path, vì sao có thể cần `--add-modules com.acme.math`?

**Trả lời:** Vì việc JAR nằm trên module path không đảm bảo module đó là root đã được resolve. `--add-modules` yêu cầu Java resolve module được nêu.

**Câu 3.** Có thể viết `requires unnamed;` trong `module-info.java` của ứng dụng không?

**Trả lời:** Không. Unnamed module không có tên để khai báo `requires` như named module.

**Câu 4.** Thư viện automatic module đã hoạt động. Khi chuyển thành explicit module, điều gì có thể khiến app không biên dịch?

**Trả lời:** Các package trước đây được export tự động có thể không còn được export. Cần thiết kế `exports` cho API cần công bố và cập nhật dependency tương ứng.

**Câu 5.** Hai JAR trên module path cùng chứa package `com.acme.common`. Có thể chỉ thêm `--add-exports` để giải quyết không?

**Trả lời:** Không. Cần xử lý split package, xác định package thuộc module nào hoặc đổi package/phiên bản dependency thích hợp.

**Câu 6.** Tại sao nên di chuyển thư viện ít phụ thuộc trước?

**Trả lời:** Vì có thể kiểm chứng lớp dependency thấp trước, sau đó chuyển các thư viện phụ thuộc ở tầng cao hơn, giúp khoanh vùng lỗi dễ hơn.

**Câu 7.** Lệnh nào giúp xem tên module thực tế của một JAR?

**Trả lời:** `jar --describe-module --file path/to/library.jar`.

**Câu 8.** Ứng dụng đã chuyển thành named module nhưng vẫn trực tiếp import class của JAR chỉ có trên classpath. Đây có phải trạng thái bền vững không?

**Trả lời:** Thường không. App không thể khai báo `requires` tới unnamed module; nên chuyển dependency trực tiếp lên module path hoặc điều chỉnh thiết kế cho phù hợp.

**Câu 9.** Automatic module có phải là sandbox an toàn cho code không tin cậy?

**Trả lời:** Không. JPMS là cơ chế tổ chức và đóng gói module; không nên coi module path hoặc class loader là cơ chế cách ly bảo mật.

**Câu 10.** Sau khi di chuyển một thư viện, build thành công nhưng `ServiceLoader` không tìm thấy provider. Nên kiểm tra gì?

**Trả lời:** Kiểm tra `uses`/`provides`, service descriptor, provider module có được resolve trong layer phù hợp không và runtime configuration có đầy đủ module không.

## Tổng kết

**Chuyển thư viện sang module path từng phần** là quá trình đưa một ứng dụng classpath truyền thống sang JPMS mà không buộc toàn bộ dependency phải có `module-info.java` ngay lập tức.

Lộ trình phổ biến là: kiểm kê dependency → đưa một số JAR lên module path dưới dạng automatic module → chạy app classpath với root module phù hợp → chuyển app sang explicit named module → lần lượt chuyển thư viện thành explicit module và thu hẹp API exports.

Trong mỗi giai đoạn, hãy xác minh **tên module thực tế, nguồn JAR, các module đã resolve, quyền truy cập package và runtime behavior**. Điều này giúp tránh nhầm lẫn giữa lỗi classpath, lỗi tìm module, split package và lỗi encapsulation, đồng thời giảm rủi ro khi triển khai migration trong hệ thống lớn.