# Phân biệt mô-đun quan sát được với mô-đun được phân giải

## 1. Hai khái niệm mô tả hai giai đoạn khác nhau

Trong Java Platform Module System (JPMS), **mô-đun quan sát được (observable module)** và **mô-đun được phân giải (resolved module)** mô tả hai trạng thái khác nhau trong quá trình tìm và chọn mô-đun.

- **Observable module:** định nghĩa mô-đun có thể được tìm thấy bởi một `ModuleFinder` trong những vị trí tìm kiếm đang được cấu hình. Mô-đun đó là một ứng viên mà hệ thống có thể xem xét khi phân giải.
- **Resolved module:** mô-đun đã được chọn vào một `Configuration` sau khi thuật toán phân giải xử lý tập mô-đun gốc và các quan hệ phụ thuộc của chúng.

Một mô-đun có thể quan sát được nhưng chưa được phân giải. Việc đặt một mô-đun lên module path giúp hệ thống tìm thấy định nghĩa của nó; điều đó chưa có nghĩa mô-đun sẽ tự động tham gia vào cấu hình đang chạy.

Ví dụ, module path có ba mô-đun:

- `com.example.app`: ứng dụng chính.
- `com.example.lib`: thư viện mà ứng dụng khai báo `requires`.
- `com.example.metrics`: mô-đun độc lập, không được ứng dụng yêu cầu.

Cả ba mô-đun đều có thể quan sát được vì `ModuleFinder` tìm thấy chúng trên module path. Nếu `com.example.app` là mô-đun gốc duy nhất, cấu hình phân giải theo các directive `requires` sẽ chứa ứng dụng, thư viện và các phụ thuộc nền tảng cần thiết; `com.example.metrics` vẫn có thể chưa được phân giải.

**Điểm cốt lõi:** observable nói rằng hệ thống *có thể tìm thấy* mô-đun; resolved nói rằng mô-đun *đã được chọn vào cấu hình*.

## 2. Mô-đun nào có thể quan sát được?

Một mô-đun là observable khi một module finder trong ngữ cảnh tìm kiếm hiện tại có thể tìm thấy định nghĩa của nó. Các nguồn thường gặp gồm:

### 2.1. Mô-đun nền tảng trong runtime image

JDK cung cấp các mô-đun nền tảng trong runtime image. Có thể lấy module finder dành cho nguồn này bằng:

~~~java
ModuleFinder systemFinder = ModuleFinder.ofSystem();
~~~

Ví dụ: `java.base`, `java.logging`, `java.sql` và những mô-đun khác được cung cấp bởi runtime image của JDK đang sử dụng.

Không phải mọi mô-đun nền tảng đều được phân giải vào mọi ứng dụng. Chúng có thể quan sát được nhưng chỉ được chọn khi thuộc tập gốc, là phụ thuộc cần thiết hoặc được đưa vào qua cơ chế phân giải khác.

### 2.2. Mô-đun trên module path

Dùng `ModuleFinder.of(...)` để tìm các mô-đun trong một hoặc nhiều vị trí:

~~~java
ModuleFinder applicationFinder =
    ModuleFinder.of(Paths.get("mods"));
~~~

Module path có thể chứa:

- **Modular JAR:** JAR có descriptor `module-info.class`.
- **Exploded module:** thư mục chứa `module-info.class` ở gốc và các package đã biên dịch.
- **Automatic module:** JAR không có module descriptor nhưng được đặt trên module path. JDK tạo descriptor tự động cho JAR đó theo quy tắc đặt tên mô-đun.

Một JAR đặt trên classpath thuộc unnamed module của class loader tương ứng. JAR đó không tự trở thành một named module chỉ vì nó có mặt trong ứng dụng. Cùng một JAR không có descriptor có thể được xem là automatic module nếu đặt trên module path.

### 2.3. Module finder dùng để khám phá, không tự phân giải

Hai phương thức thường dùng:

~~~java
Optional<ModuleReference> reference =
    applicationFinder.find("com.example.metrics");

Set<ModuleReference> allReferences =
    applicationFinder.findAll();
~~~

- `find(name)` kiểm tra finder có tìm thấy một mô-đun theo tên hay không.
- `findAll()` trả về các định nghĩa mô-đun mà finder quan sát được.

Kết quả của `find` hoặc `findAll` là bằng chứng về khả năng tìm thấy mô-đun. Nó không cho biết mô-đun có nằm trong cấu hình phân giải của ứng dụng hay không.

## 3. Mô-đun được phân giải như thế nào?

JPMS phân giải mô-đun dựa trên một tập **mô-đun gốc (root modules)**. Tập gốc xác định điểm bắt đầu để xây dựng cấu hình.

Quy trình cơ bản:

1. Xác định các mô-đun gốc cần phân giải.
2. Tìm định nghĩa của từng mô-đun gốc trong các nguồn mô-đun có thể quan sát.
3. Đọc các directive `requires` trong descriptor.
4. Tiếp tục tìm và phân giải các phụ thuộc bắt buộc của những mô-đun đã chọn.
5. Kiểm tra tính hợp lệ của module graph, chẳng hạn tên mô-đun, phụ thuộc bắt buộc và xung đột package.
6. Tạo `Configuration` chứa các mô-đun đã được phân giải và quan hệ readability giữa chúng.

Nếu một phụ thuộc bắt buộc không thể tìm thấy trong các nguồn phù hợp hoặc cấu hình cha, quá trình phân giải thất bại. Một mô-đun không được chọn làm root và cũng không phải phụ thuộc của các root có thể vẫn observable nhưng không xuất hiện trong configuration.

### 3.1. Mô-đun gốc được xác định từ đâu?

Khi khởi chạy ứng dụng bằng tên mô-đun:

~~~bash
java --module-path mods -m com.example.app/com.example.app.Main
~~~

`com.example.app` là mô-đun gốc được yêu cầu khởi chạy. Các mô-đun mà nó khai báo `requires` sẽ được xem xét tiếp trong quá trình phân giải.

Có thể bổ sung root bằng tùy chọn `--add-modules`:

~~~bash
java --module-path mods --add-modules com.example.metrics -m com.example.app/com.example.app.Main
~~~

Lúc này `com.example.metrics` được thêm vào tập gốc. Nếu định nghĩa của nó và các phụ thuộc cần thiết đều hợp lệ, mô-đun sẽ được đưa vào cấu hình.

Một số giá trị đặc biệt thường dùng:

- `--add-modules ALL-MODULE-PATH`: thêm tất cả mô-đun observable trên module path làm root.
- `--add-modules ALL-SYSTEM`: thêm các mô-đun hệ thống observable làm root.

Tùy chọn `--limit-modules` có thể giới hạn tập mô-đun được xem xét trong môi trường chạy. Nó hữu ích khi cần giới hạn module universe của ứng dụng.

### 3.2. Vai trò của requires

Các directive `requires` tạo ra quan hệ phụ thuộc trong module graph. Ví dụ:

~~~java
module com.example.app {
    requires com.example.lib;
}
~~~

Khi `com.example.app` là root, hệ thống phải tìm và phân giải `com.example.lib` vì đây là phụ thuộc bắt buộc.

Modifier `transitive` truyền readability tới những mô-đun đọc mô-đun hiện tại. Nó ảnh hưởng tới đồ thị readability và tập phụ thuộc cần xử lý.

Modifier `static` biểu thị phụ thuộc bắt buộc khi biên dịch nhưng tùy chọn khi chạy. Vì vậy, khi phân giải ở runtime, phụ thuộc chỉ được khai báo bằng `requires static` không bắt buộc phải có mặt nếu không được yêu cầu bởi một quan hệ khác.

### 3.3. Service binding có thể bổ sung mô-đun

Khi phân giải có xét service binding, các mô-đun cung cấp service phù hợp với directive `uses` có thể được bổ sung vào cấu hình thông qua `provides`.

API có hai cách phân giải đáng chú ý:

- `Configuration.resolve(...)`: phân giải module graph dựa trên các root và quan hệ phụ thuộc.
- `Configuration.resolveAndBind(...)`: thực hiện phân giải kèm service binding, có thể bổ sung các mô-đun provider.

Vì vậy, danh sách mô-đun trong cấu hình thực tế có thể rộng hơn phần phụ thuộc `requires` trực tiếp. Khi đọc kết quả `--show-module-resolution`, cần phân biệt các dòng root/requires với các dòng binds được bổ sung do service binding.

## 4. Ví dụ hoàn chỉnh: observable nhưng chưa resolved

Ví dụ có ba mô-đun. Ứng dụng chỉ phụ thuộc vào thư viện; mô-đun metrics độc lập và chưa được yêu cầu.

### 4.1. Cấu trúc mã nguồn

~~~text
src/
├── com.example.app/
│   ├── module-info.java
│   └── com/example/app/Main.java
├── com.example.lib/
│   ├── module-info.java
│   └── com/example/lib/Message.java
└── com.example.metrics/
    ├── module-info.java
    └── com/example/metrics/Metrics.java
~~~

### 4.2. Module descriptor của ứng dụng

File `src/com.example.app/module-info.java`:

~~~java
module com.example.app {
    requires com.example.lib;
}
~~~

File `src/com.example.app/com/example/app/Main.java`:

~~~java
package com.example.app;

import com.example.lib.Message;

public class Main {
    public static void main(String[] args) {
        System.out.println("app uses " + Message.value());
    }
}
~~~

### 4.3. Module descriptor của thư viện

File `src/com.example.lib/module-info.java`:

~~~java
module com.example.lib {
    exports com.example.lib;
}
~~~

File `src/com.example.lib/com/example/lib/Message.java`:

~~~java
package com.example.lib;

public class Message {
    public static String value() {
        return "resolved dependency";
    }
}
~~~

### 4.4. Module descriptor của metrics

File `src/com.example.metrics/module-info.java`:

~~~java
module com.example.metrics {
    exports com.example.metrics;
}
~~~

File `src/com.example.metrics/com/example/metrics/Metrics.java`:

~~~java
package com.example.metrics;

public class Metrics {
}
~~~

Mô-đun metrics có descriptor hợp lệ nhưng không được `com.example.app` yêu cầu.

### 4.5. Biên dịch cả ba mô-đun

Chạy tại thư mục chứa `src`:

~~~bash
javac --module-source-path src -d mods -m com.example.app,com.example.lib,com.example.metrics
~~~

Sau khi biên dịch, thư mục `mods` chứa ba exploded module. Cả ba định nghĩa đều có thể được module finder tìm thấy.

### 4.6. Chạy ứng dụng với app là root duy nhất

~~~bash
java --module-path mods -m com.example.app/com.example.app.Main
~~~

Kết quả:

~~~text
app uses resolved dependency
~~~

Ứng dụng chạy được vì `com.example.app` và phụ thuộc `com.example.lib` được phân giải. `com.example.metrics` không cần thiết cho ứng dụng nên chưa được chọn vào cấu hình theo các quan hệ requires.

### 4.7. Kiểm tra bằng Java API

Tạo file `Probe.java` bên ngoài các module:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Paths;
import java.util.Set;
import java.util.TreeSet;
import java.util.stream.Collectors;

public class Probe {
    public static void main(String[] args) {
        ModuleFinder finder = ModuleFinder.of(Paths.get(args[0]));

        Set<String> observable = finder.findAll().stream()
            .map(ref -> ref.descriptor().name())
            .collect(Collectors.toCollection(TreeSet::new));

        Configuration appConfiguration =
            ModuleLayer.boot().configuration().resolve(
                ModuleFinder.ofSystem(),
                finder,
                Set.of("com.example.app")
            );

        Set<String> resolved = appConfiguration.modules().stream()
            .map(module -> module.name())
            .collect(Collectors.toCollection(TreeSet::new));

        System.out.println("Observable on module path: " + observable);
        System.out.println("Resolved from app root: " + resolved);
        System.out.println("metrics observable: "
            + finder.find("com.example.metrics").isPresent());
        System.out.println("metrics resolved from app root: "
            + appConfiguration.findModule("com.example.metrics").isPresent());

        Configuration withMetricsRoot =
            ModuleLayer.boot().configuration().resolve(
                ModuleFinder.ofSystem(),
                finder,
                Set.of("com.example.app", "com.example.metrics")
            );

        System.out.println("metrics resolved when added as root: "
            + withMetricsRoot.findModule("com.example.metrics").isPresent());
    }
}
~~~

Biên dịch và chạy chương trình kiểm tra:

~~~bash
javac -d probe Probe.java
java -cp probe Probe mods
~~~

Kết quả:

~~~text
Observable on module path: [com.example.app, com.example.lib, com.example.metrics]
Resolved from app root: [com.example.app, com.example.lib, java.base]
metrics observable: true
metrics resolved from app root: false
metrics resolved when added as root: true
~~~

Kết quả cho thấy:

- `finder.findAll()` tìm thấy cả ba mô-đun trên module path.
- `Configuration.modules()` chỉ liệt kê các mô-đun đã được phân giải trong cấu hình được tạo từ root `com.example.app`.
- `com.example.metrics` observable nhưng không resolved.
- Khi thêm metrics làm root, `Configuration.findModule(...)` xác nhận mô-đun đã được phân giải.

Ví dụ dùng `Configuration.resolve(...)` để minh họa rõ phần phụ thuộc `requires`. Nếu dùng `resolveAndBind(...)` hoặc quan sát quá trình khởi động JVM, service binding có thể bổ sung các provider module khác.

## 5. Công cụ kiểm tra observable và resolved

### 5.1. Liệt kê mô-đun observable

Dùng:

~~~bash
java --module-path mods --list-modules
~~~

Tùy chọn `--list-modules` liệt kê các mô-đun observable mà launcher nhìn thấy trong cấu hình tìm kiếm hiện tại, gồm các mô-đun hệ thống và mô-đun trên module path.

Lệnh này hữu ích khi cần xác nhận một mô-đun có được tìm thấy hay không. Nó không chứng minh rằng tất cả mô-đun được liệt kê đều tham gia vào cấu hình của ứng dụng.

### 5.2. Xem quá trình phân giải khi khởi chạy

Dùng:

~~~bash
java --show-module-resolution --module-path mods -m com.example.app/com.example.app.Main
~~~

Tùy chọn `--show-module-resolution` in thông tin về root, các quan hệ requires và service binding trong quá trình khởi động. Đây là cách thực tế để xem những mô-đun được đưa vào cấu hình lúc chạy.

Kết quả có thể khác nhau giữa các JDK do tập mô-đun hệ thống và service provider được cài đặt khác nhau. Vì vậy nên tập trung vào tên root, các dòng requires và các dòng binds liên quan đến ứng dụng.

### 5.3. Kiểm tra bằng API

| API | Câu hỏi được trả lời |
|---|---|
| `ModuleFinder.find(name)` | Finder có tìm thấy định nghĩa mô-đun theo tên không? |
| `ModuleFinder.findAll()` | Finder quan sát được những định nghĩa mô-đun nào? |
| `Configuration.modules()` | Những mô-đun nào nằm trong configuration? |
| `Configuration.findModule(name)` | Configuration có chứa mô-đun theo tên không? |
| `ModuleLayer.boot().configuration()` | Configuration của boot layer hiện tại là gì? |

Không nên dùng `ModuleFinder.findAll()` để kết luận một mô-đun đã được phân giải. Muốn kiểm tra trạng thái resolved, hãy xem `Configuration.modules()` hoặc `Configuration.findModule(name)` trên đúng configuration cần kiểm tra.

## 6. Phân biệt với readability, exports và class loading

Bốn khái niệm này liên quan nhưng không đồng nghĩa:

| Khái niệm | Ý nghĩa |
|---|---|
| Observable | Có thể tìm thấy định nghĩa mô-đun qua module finder |
| Resolved | Được đưa vào một configuration sau quá trình phân giải |
| Readable | Một mô-đun có quan hệ readability tới mô-đun khác |
| Exported | Package được công khai cho module khác theo directive exports |
| Loaded | Class đã được class loader nạp vào JVM |

Một mô-đun đã resolved không có nghĩa mọi mô-đun khác đều đọc được nó. Readability được xác định bởi quan hệ module graph, đặc biệt là các directive `requires` và `requires transitive`.

Một mô-đun readable cũng không có nghĩa mọi package của nó đều truy cập được. Package cần được export phù hợp; quyền reflection sâu chịu sự điều khiển của `opens`.

Một mô-đun resolved cũng không có nghĩa mọi class trong mô-đun đã được tải hoặc khởi tạo. Class loading diễn ra theo nhu cầu của chương trình.

## 7. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Mô-đun không xuất hiện trong `ModuleFinder.findAll()` | Sai module path, sai tên hoặc vị trí chứa mô-đun không được finder tìm kiếm | Kiểm tra đường dẫn, tên module descriptor và finder đang dùng |
| Mô-đun có trong `--list-modules` nhưng không có trong configuration | Mô-đun observable nhưng không phải root hoặc phụ thuộc cần thiết | Dùng `--add-modules` nếu muốn chọn mô-đun đó làm root |
| Khởi chạy báo không tìm thấy module gốc | Tên root không đúng hoặc mô-đun không observable trong module path hiện tại | Kiểm tra tên sau `-m`, module path và kết quả `--list-modules` |
| Phân giải thất bại vì thiếu dependency | Một directive requires trỏ tới mô-đun không thể tìm thấy | Đưa dependency lên module path hoặc sửa descriptor theo dependency thực tế |
| Configuration chứa nhiều module hơn dự kiến | Có root bổ sung, phụ thuộc bắc cầu hoặc service binding | Đọc các dòng root, requires và binds trong `--show-module-resolution` |
| `Configuration.findModule()` trả về empty | Mô-đun không thuộc configuration đang kiểm tra | Kiểm tra đúng configuration, tập root và các dependency |
| Nhầm JAR trên classpath với mô-đun observable | JAR trên classpath thuộc unnamed module | Đặt modular JAR hoặc automatic module lên module path khi muốn dùng JPMS |
| Xung đột package khi phân giải | Hai named module cùng chứa package gây split package không hợp lệ trong cấu hình | Tổ chức package sao cho mỗi package thuộc một named module phù hợp |

## 8. Quy tắc thực hành

- Xem module path là nơi cung cấp các định nghĩa mô-đun có thể được tìm thấy.
- Xác định rõ root modules trước khi phân tích module graph.
- Dùng `ModuleFinder` để kiểm tra khả năng quan sát và `Configuration` để kiểm tra kết quả phân giải.
- Khi ứng dụng cần một mô-đun dù không khai báo qua requires, cân nhắc `--add-modules` hoặc cấu hình root phù hợp.
- Kiểm tra service binding nếu runtime đưa thêm provider module vào cấu hình.
- Phân biệt resolved với readable, exported và loaded khi phân tích lỗi.
- Dùng `--list-modules` để xem tập observable và `--show-module-resolution` để xem quá trình phân giải lúc chạy.

## 9. Ghi nhớ

Một mô-đun có thể tồn tại trên module path và được JVM tìm thấy nhưng không tham gia vào ứng dụng đang chạy. Nó chỉ trở thành resolved khi được chọn làm root, được yêu cầu bởi một mô-đun đã chọn hoặc được bổ sung qua cơ chế phân giải như service binding.

Vì vậy, khi điều tra lỗi module:

1. Kiểm tra mô-đun có observable hay không.
2. Kiểm tra tập root của cấu hình.
3. Kiểm tra các directive requires và service binding.
4. Kiểm tra mô-đun có thực sự nằm trong configuration hay không.
5. Sau đó mới kiểm tra readability, exports và class loading.

Cách phân tích theo thứ tự này giúp xác định rõ lỗi nằm ở bước tìm thấy định nghĩa mô-đun hay ở bước xây dựng module graph.
