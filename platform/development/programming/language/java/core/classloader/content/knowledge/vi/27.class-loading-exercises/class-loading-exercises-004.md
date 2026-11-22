# Thực hành: Cô lập hai phiên bản thư viện trong hai ClassLoader (Java 17+)

Một tình huống kinh điển của **Java ClassLoader** là hai plugin cùng cần một thư viện có **cùng fully qualified class name**, nhưng phiên bản hoặc hành vi khác nhau. Ví dụ:

- Plugin A cần `lib.Formula` phiên bản **v1**: `evaluate(x) = x + 1`.
- Plugin B cần `lib.Formula` phiên bản **v2**: `evaluate(x) = x * 10`.
- Cả hai đều triển khai interface `spi.Calculator` do ứng dụng chủ (host) cung cấp.

Nếu mọi JAR nằm trên **cùng application classpath/class loader**, hai class files đều mang tên `lib.Formula`; một defining loader không thể sở hữu **hai runtime classes cùng binary name**. Trong bài thực hành này, ta tạo **hai đối tượng `URLClassLoader` khác nhau** cùng parent. Mỗi loader đọc JAR riêng và định nghĩa bản `lib.Formula` của mình; đồng thời cả hai dùng **cùng runtime interface `spi.Calculator`** qua parent delegation.

**Kết quả mong đợi:** Hai plugin có cùng implementation binary name `plugins.CalculatorImpl` vẫn hoạt động song song với kết quả khác nhau, không gây `ClassCastException` khi host ép về `spi.Calculator`. Ta sẽ kiểm tra trực tiếp class identity, defining loader, static state và trường hợp đối chứng khi dùng một loader chung.

## 1. Mục tiêu học tập và điều kiện cần

Sau bài này, bạn có thể:

1. Giải thích vì sao **(binary name, defining class loader)** xác định runtime class identity.
2. Đóng hai phiên bản của thư viện có **cùng package/class name** thành hai JAR riêng.
3. Tạo **hai `URLClassLoader`**, mỗi loader chỉ có URL JAR của phiên bản nó cần.
4. Đặt **SPI/shared API ở parent** để instances từ hai plugin đều có thể cast thành một interface chung.
5. Chứng minh **`lib.Formula` của A khác `lib.Formula` của B** dù tên giống hệt.
6. Chứng minh static fields/caches của mỗi runtime class độc lập.
7. Chạy trường hợp đối chứng **một loader chứa cả hai JAR** để thấy xung đột namespace/chọn phiên bản theo thứ tự URL.
8. Nhận diện nguyên nhân khiến isolation thất bại: parent classpath bị “nhiễm” thư viện private, sai loader, trùng SPI, lệch resource discovery hoặc lỗi binary compatibility.
9. Biết cách quản lý lifecycle, đóng loader và tránh hiểu nhầm class loader là sandbox bảo mật.

**Yêu cầu:** JDK 17 trở lên với `javac`, `java` và `jar` trên PATH; terminal Bash/Linux/macOS/Git Bash hoặc Windows PowerShell. Code dùng cú pháp/API tương thích Java 17, không cần Maven/Gradle, thư viện bên ngoài hay IDE.

Đây là **thực hành classpath/JAR thông thường**, không dùng `module-info.java`. Cuối bài có phần đối chiếu với JPMS/module layers.

## 2. Kiến trúc: một host và hai namespace plugin

```text
                  HOST / APPLICATION CLASSLOADER
                    ├── host.TwoVersions
                    └── spi.Calculator
                              ^
                              | parent delegation
              +---------------+-----------------+
              |                                 |
       URLClassLoader A                  URLClassLoader B
       URLs: [plugin-v1.jar]             URLs: [plugin-v2.jar]
          |                                 |
          +-- plugins.CalculatorImpl        +-- plugins.CalculatorImpl
          |                                 |
          +-- lib.Formula (v1)              +-- lib.Formula (v2)
              evaluate(x)=x+1                  evaluate(x)=x*10
```

Hai bản `lib.Formula` có **cùng binary name**, nhưng runtime identity khác vì **defining loader A** khác **defining loader B**:

```text
("lib.Formula", Loader A) != ("lib.Formula", Loader B)
```

Tương tự, `plugins.CalculatorImpl` trong JAR A và JAR B là hai runtime classes khác nhau.

Trong khi đó:

```text
a.loadClass("spi.Calculator")
    == b.loadClass("spi.Calculator")
    == spi.Calculator.class
```

vì cả hai loader **delegate** việc nạp `spi.Calculator` cho parent, nơi chỉ có **một** định nghĩa interface. Host dùng interface này để giao tiếp với hai implementation instances.

### Lưu ý: hai loader riêng chưa đồng nghĩa cô lập mọi thứ

`URLClassLoader` mặc định dùng **parent-first delegation**. Nếu parent **đã có `lib.Formula`**, cả A và B có thể lấy ngay class của parent và **không dùng** class private trong JAR tương ứng. Vì vậy runtime classpath của host trong thực hành này **chỉ** chứa `out/host` — tuyệt đối không thêm `out/v1`, `out/v2` hoặc `plugin-v1.jar` / `plugin-v2.jar` vào `-cp` của host.

Trong hệ thống thực tế, cần tách rõ:

| Đặt ở đâu? | Class/package | Lý do |
|---|---|---|
| **Parent/host** | `spi.Calculator`, host APIs, shared DTO | Một runtime type identity cho cả host và hai plugin |
| **Loader A** | `lib.Formula` v1, `plugins.CalculatorImpl` cho A | Dependency và implementation riêng |
| **Loader B** | `lib.Formula` v2, `plugins.CalculatorImpl` cho B | Dependency và implementation riêng |
| **Không đặt ở parent** | Bất kỳ bản private `lib.Formula` nào | Tránh parent-first “đè” phiên bản của child |
| **Không đóng vào từng plugin JAR** | Bản copy `spi.Calculator` | Tránh lệch identity/SPI class duplication |

## 3. Tạo cấu trúc project

Thực hành sử dụng **năm Java source files**:

```text
two-version-lab/
├── src/
│   ├── host/
│   │   ├── spi/
│   │   │   └── Calculator.java
│   │   └── host/
│   │       └── TwoVersions.java
│   ├── v1/
│   │   └── lib/
│   │       └── Formula.java
│   ├── v2/
│   │   └── lib/
│   │       └── Formula.java
│   └── plugin/
│       └── plugins/
│           └── CalculatorImpl.java
├── out/
│   ├── host/
│   ├── v1/
│   └── v2/
└── dist/
    ├── plugin-v1.jar
    └── plugin-v2.jar
```

**Vì sao implementation chỉ có một file source?** Ta muốn chứng minh **cùng một code implementation** có thể liên kết với **hai class definitions của thư viện khác nhau** khi biên dịch/đóng gói riêng. Cùng file `src/plugin/plugins/CalculatorImpl.java` được biên dịch **hai lần**: lần đầu cùng thư viện v1 vào `out/v1`, lần thứ hai cùng thư viện v2 vào `out/v2`.

**Vì sao `lib.Formula` có hai source files trùng fully qualified name?** Để biểu diễn hai phiên bản thư viện thật — chúng phải được biên dịch **vào hai output folders riêng**, không được cùng đẩy vào một thư mục `-d`.

## 4. Viết SPI dùng chung ở host

Tệp **`src/host/spi/Calculator.java`**:

```java
package spi;

public interface Calculator {
    String version();
    int apply(int value);
}
```

Đây là **contract** mà host biết trước. `version()` phục vụ quan sát kết quả, còn `apply(int)` gọi chức năng được plugin cung cấp.

Một thiết kế plugin tốt chỉ cho host giao tiếp thông qua **các types do parent/shared loader định nghĩa**; không để public method signatures của SPI lộ một private type như `lib.Formula` (vì hai loader có hai types khác nhau).

Nếu cần truyền object phức tạp, sử dụng DTO/record hoặc interfaces chung được host định nghĩa, chứ không truyền object `lib.Formula` trực tiếp qua boundary.

## 5. Tạo thư viện phiên bản v1

Tệp **`src/v1/lib/Formula.java`**:

```java
package lib;

public final class Formula {
    private static int calls;

    private Formula() {}

    public static String version() {
        return "v1";
    }

    public static int evaluate(int value) {
        ++calls;
        return value + 1;
    }

    public static int calls() {
        return calls;
    }
}
```

Ở v1, `evaluate(3)` trả **4**. `calls` là **static state** của runtime class `lib.Formula` do loader tương ứng định nghĩa.

Tệp này chỉ dùng Java chuẩn, không phụ thuộc `spi.Calculator`.

## 6. Tạo thư viện phiên bản v2

Tệp **`src/v2/lib/Formula.java`**:

```java
package lib;

public final class Formula {
    private static int calls;

    private Formula() {}

    public static String version() {
        return "v2";
    }

    public static int evaluate(int value) {
        ++calls;
        return value * 10;
    }

    public static int calls() {
        return calls;
    }
}
```

Ở v2, `evaluate(3)` trả **30**.

Hai source files có **cùng package `lib`, cùng class `Formula` và cùng method signatures** nhưng implementation khác. Đây là tình huống tốt để kiểm thử isolation vì **không phải** chỉ dùng các class khác tên, mà thật sự có **binary-name collision**.

### Nếu hai phiên bản có API khác nhau thì sao?

Bài lab cố ý giữ signatures giống nhau để so sánh behavior rõ ràng. Trong sản phẩm thực, một version có thể thay `evaluate` thành method khác. Khi plugin được biên dịch dựa vào v2 nhưng runtime vô tình nạp v1, có thể có `NoSuchMethodError`, `NoSuchFieldError`, `AbstractMethodError` hoặc các lỗi linking khác tùy kiểu thay đổi. Isolation đúng giúp mỗi plugin nhìn đúng dependency version nó được build/test với.

## 7. Tạo plugin implementation (biên dịch hai lần)

Tệp **`src/plugin/plugins/CalculatorImpl.java`**:

```java
package plugins;

import lib.Formula;
import spi.Calculator;

public final class CalculatorImpl implements Calculator {
    @Override
    public String version() {
        return Formula.version();
    }

    @Override
    public int apply(int value) {
        return Formula.evaluate(value);
    }
}
```

Tệp này **không hard-code “v1” hay “v2”**. Nó gọi `lib.Formula` được tìm thấy trong namespace của class loader định nghĩa `plugins.CalculatorImpl`.

Lúc runtime, bytecode của `CalculatorImpl` có **symbolic reference** đến `lib.Formula`. Khi JVM cần resolve reference này, loader gắn với defining class `plugins.CalculatorImpl` tham gia việc tìm class liên quan. Với loader A, `lib.Formula` là v1; với loader B, `lib.Formula` là v2.

Trong lab cả `CalculatorImpl` lẫn `Formula` thuộc cùng plugin JAR và được cùng child loader định nghĩa; điều này giữ dependency graph của mỗi plugin nhất quán.

**Không thử cho plugin A trực tiếp import một implementation class của plugin B** trong thiết kế isolation này: chúng là namespaces riêng, và cross-plugin type references cần contract/delegation rõ.

## 8. Viết chương trình host: hai loader riêng và một loader đối chứng

Tệp **`src/host/host/TwoVersions.java`**:

```java
package host;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import spi.Calculator;

public final class TwoVersions {

    private static Calculator plugin(URLClassLoader loader)
            throws Exception {
        Class<?> type = loader.loadClass("plugins.CalculatorImpl");
        return (Calculator) type.getDeclaredConstructor()
                .newInstance();
    }

    public static void main(String[] args) throws Exception {
        ClassLoader parent = TwoVersions.class.getClassLoader();
        URL v1 = Path.of(args[0]).toUri().toURL();
        URL v2 = Path.of(args[1]).toUri().toURL();

        try {
            parent.loadClass("plugins.CalculatorImpl");
            System.out.println("Parent sees implementation: true");
        } catch (ClassNotFoundException expected) {
            System.out.println("Parent sees implementation: false");
        }

        try (URLClassLoader a =
                     new URLClassLoader(new URL[]{v1}, parent);
             URLClassLoader b =
                     new URLClassLoader(new URL[]{v2}, parent);
             URLClassLoader both =
                     new URLClassLoader(new URL[]{v1, v2}, parent)) {

            Calculator c1 = plugin(a);
            Calculator c2 = plugin(b);

            System.out.println("Version A: " + c1.version());
            System.out.println("Version B: " + c2.version());
            System.out.println("Result A(3): " + c1.apply(3));
            System.out.println("Result B(3): " + c2.apply(3));

            Class<?> aImpl = a.loadClass("plugins.CalculatorImpl");
            Class<?> bImpl = b.loadClass("plugins.CalculatorImpl");

            System.out.println("Different implementation classes: "
                    + (aImpl != bImpl));

            System.out.println("Different dependency classes: "
                    + (a.loadClass("lib.Formula")
                        != b.loadClass("lib.Formula")));

            System.out.println("Same shared SPI class: "
                    + (a.loadClass("spi.Calculator")
                        == b.loadClass("spi.Calculator")));

            System.out.println("Loader A owns plugin: "
                    + (aImpl.getClassLoader() == a));

            System.out.println("Loader B owns plugin: "
                    + (bImpl.getClassLoader() == b));

            System.out.println("Calls A: "
                    + a.loadClass("lib.Formula")
                       .getMethod("calls").invoke(null));

            System.out.println("Calls B: "
                    + b.loadClass("lib.Formula")
                       .getMethod("calls").invoke(null));

            Calculator shared = plugin(both);
            System.out.println("Shared loader version: "
                    + shared.version());
            System.out.println("Shared result (3): "
                    + shared.apply(3));
            System.out.println("Shared version remains: "
                    + plugin(both).version());
        }
    }
}
```

Chương trình dùng **ba** đối tượng loader để so sánh trực tiếp:

- `a`: **chỉ** có URL JAR v1.
- `b`: **chỉ** có URL JAR v2.
- `both`: **cả hai URLs**, v1 trước v2, đóng vai trò **trường hợp đối chứng** — không phải thiết kế đáp ứng yêu cầu dùng đồng thời hai versions.

Mỗi child loader nhận **cùng `parent`** là defining loader của `host.TwoVersions`. Do host cũng chứa `spi.Calculator`, cả A và B delegate SPI lên cùng parent.

### Phân tích đoạn plugin(URLClassLoader)

```java
Class<?> type = loader.loadClass("plugins.CalculatorImpl");
return (Calculator) type.getDeclaredConstructor().newInstance();
```

Đây là **trích đoạn** từ program hoàn chỉnh ở trên. `loadClass` nhận binary name `plugins.CalculatorImpl`. Reflection gọi public no-arg constructor và tạo object. Cuối cùng, ép kiểu qua **`spi.Calculator` của host**.

Cast thành công vì trong cả hai JAR chỉ có implementation `plugins.CalculatorImpl` và thư viện private `lib.Formula`. Không có file `spi/Calculator.class` riêng nằm trong hai plugin JARs; host interface đã được defining parent cung cấp.

### Vì sao dùng try-with-resources?

`URLClassLoader` implements `Closeable`. Sau khi kết thúc thực hành, `try-with-resources` gọi `close()` cho A, B và both để giải phóng JAR/file handles do loaders quản lý.

**`close()` không phải “unloadClass”**: classes đã được định nghĩa vẫn có thể tồn tại khi còn strong references. Trong sản phẩm thật, không đóng loader trước khi plugin dừng nhận công việc và hoàn tất lifecycle, vì loader đã đóng có thể không đọc được class/resource mới từ các URLs của nó.

## 9. Biên dịch và đóng gói trên Linux/macOS/Git Bash

Từ thư mục `two-version-lab`:

```bash
mkdir -p out/host out/v1 out/v2 dist

# Host chỉ chứa SPI và chương trình thử nghiệm.
javac --release 17 -d out/host \
  src/host/spi/Calculator.java \
  src/host/host/TwoVersions.java

# Plugin v1: biên dịch Formula v1 + cùng CalculatorImpl.
# Compile classpath chỉ có shared SPI trong out/host.
javac --release 17 -cp out/host -d out/v1 \
  src/v1/lib/Formula.java \
  src/plugin/plugins/CalculatorImpl.java

# Plugin v2: Formula v2 + CalculatorImpl được biên dịch riêng.
javac --release 17 -cp out/host -d out/v2 \
  src/v2/lib/Formula.java \
  src/plugin/plugins/CalculatorImpl.java

# Đóng hai JAR, không đưa spi.Calculator vào plugin JAR.
jar --create --file dist/plugin-v1.jar -C out/v1 .
jar --create --file dist/plugin-v2.jar -C out/v2 .

# Quan trọng: CHỈ out/host nằm trên runtime -cp.
java -cp out/host host.TwoVersions \
  dist/plugin-v1.jar dist/plugin-v2.jar
```

**Đường dẫn classpath trên Windows khác dấu phân tách** nếu có nhiều entries: Windows dùng `;`, Linux/macOS dùng `:`. Trong demo này runtime classpath chỉ có **một** directory `out/host` nên không cần delimiter; hai đường JAR là **program arguments**, không phải các phần tử của `-cp`.

### Kiểm tra hai JAR thật sự độc lập

Sau khi build:

```bash
jar --list --file dist/plugin-v1.jar
jar --list --file dist/plugin-v2.jar
```

Cả hai phải có các entries sau (có thể còn manifest và directory entries):

```text
lib/Formula.class
plugins/CalculatorImpl.class
```

**Không nên thấy**:

```text
spi/Calculator.class
host/TwoVersions.class
```

trong plugin JAR. Nếu có, build process đã đưa shared API/host code vào plugin artifact; cần xem lại packaging để tránh class identity/trùng contract về sau.

## 10. Lệnh tương đương trên Windows PowerShell

```powershell
New-Item -ItemType Directory -Force -Path out/host, out/v1, out/v2, dist | Out-Null

javac --release 17 -d out/host src/host/spi/Calculator.java src/host/host/TwoVersions.java

javac --release 17 -cp out/host -d out/v1 src/v1/lib/Formula.java src/plugin/plugins/CalculatorImpl.java

javac --release 17 -cp out/host -d out/v2 src/v2/lib/Formula.java src/plugin/plugins/CalculatorImpl.java

jar --create --file dist/plugin-v1.jar -C out/v1 .
jar --create --file dist/plugin-v2.jar -C out/v2 .

java -cp out/host host.TwoVersions dist/plugin-v1.jar dist/plugin-v2.jar
```

Các lệnh này cũng làm việc khi các paths chứa khoảng trắng nếu được quote phù hợp khi tạo lệnh tương ứng. Để chắc chắn JDK đang sử dụng:

```powershell
java -version
javac -version
```

Nếu terminal không tìm được `javac` hay `jar`, hãy kiểm tra JDK (không chỉ JRE) và `JAVA_HOME`/PATH. Không tự động lấy các bản class đã biên dịch sẵn của IDE khi chưa biết IDE đang dùng compile target và output directories nào.

## 11. Kết quả thực nghiệm đã kiểm tra

Bộ **5 Java source files** và hai JAR trên được biên dịch với **`javac --release 17`** và chạy trên JDK 24 tương thích Java 17. Stdout chính xác cho thứ tự **v1 rồi v2**:

```text
Parent sees implementation: false
Version A: v1
Version B: v2
Result A(3): 4
Result B(3): 30
Different implementation classes: true
Different dependency classes: true
Same shared SPI class: true
Loader A owns plugin: true
Loader B owns plugin: true
Calls A: 1
Calls B: 1
Shared loader version: v1
Shared result (3): 4
Shared version remains: v1
```

Đây là **đầu ra của chính chương trình**, không phải JVM verbose class-loading log.

### Đọc hiểu từng kết quả

| Dòng kết quả | Ý nghĩa |
|---|---|
| `Parent sees implementation: false` | Host **không** nhìn thấy `plugins.CalculatorImpl`; implementation không vô tình nằm trên application classpath |
| `Version A: v1` | Loader A resolve `lib.Formula` từ JAR v1 |
| `Version B: v2` | Loader B resolve `lib.Formula` từ JAR v2 |
| `Result A(3): 4` | Bản v1 chạy phép `3 + 1` |
| `Result B(3): 30` | Bản v2 chạy phép `3 * 10` |
| `Different implementation classes: true` | `plugins.CalculatorImpl` của A và B là **hai `Class<?>` khác nhau** |
| `Different dependency classes: true` | `lib.Formula` của A và B là **hai runtime classes khác nhau** |
| `Same shared SPI class: true` | Cả hai dùng cùng runtime interface do parent định nghĩa |
| `Loader A/B owns plugin: true` | Đúng defining loader, không bị parent hoặc shared loader định nghĩa hộ |
| `Calls A/B: 1` | Mỗi bản `lib.Formula` có **static field `calls` riêng**; cùng chạy một lượt nên mỗi bên bằng 1 |
| `Shared loader version: v1` | Loader có URL v1 đứng trước v2 chọn một class implementation/Formula từ v1 |
| `Shared result (3): 4` | Loader chung thực thi behavior v1; không tự chọn “v2 cho request khác” |
| `Shared version remains: v1` | Gọi nạp implementation nhiều lần trên cùng loader vẫn được một runtime type, không chuyển sang v2 |

### Vì sao hai bản giữ static state riêng?

`static int calls` thuộc runtime class, không thuộc tên `"lib.Formula"` trên toàn JVM. Vì vậy:

```text
("lib.Formula", Loader A).calls = 1
("lib.Formula", Loader B).calls = 1

Đó là hai biến static riêng biệt của hai runtime classes.
```

Nếu có một shared library `lib.Formula` được parent định nghĩa, cả hai plugin có thể dùng **chung static state của bản parent**, trái yêu cầu isolation.

## 12. Đối chứng bổ sung: đảo thứ tự hai JAR

Không cần sửa mã nguồn. Đảo thứ tự arguments:

```bash
java -cp out/host host.TwoVersions \
  dist/plugin-v2.jar dist/plugin-v1.jar
```

PowerShell:

```powershell
java -cp out/host host.TwoVersions dist/plugin-v2.jar dist/plugin-v1.jar
```

Đầu ra xác minh:

```text
Parent sees implementation: false
Version A: v2
Version B: v1
Result A(3): 30
Result B(3): 4
Different implementation classes: true
Different dependency classes: true
Same shared SPI class: true
Loader A owns plugin: true
Loader B owns plugin: true
Calls A: 1
Calls B: 1
Shared loader version: v2
Shared result (3): 30
Shared version remains: v2
```

**Giải thích:**

- `a` nhận URL đầu tiên (lúc này v2), `b` nhận URL thứ hai (v1): **mỗi loader vẫn cô lập chính xác** phiên bản được cấp cho nó.
- `both` nhận URL array `[v2, v1]`: với `URLClassLoader` mặc định và parent không có class trùng tên, nó tìm trong URLs theo thứ tự và chọn bản v2.
- `both` **không thể định nghĩa thêm một bản `plugins.CalculatorImpl`/`lib.Formula` với cùng binary name** từ JAR còn lại sau khi đã chọn bản v2.

Đối chứng này cho thấy **thứ tự URL ảnh hưởng đến một loader chung**, chứ không tự cung cấp đa phiên bản. Thứ tự là nguyên tắc tra class/resource của `URLClassLoader` khi dùng một URL search path; với app server/container/custom loaders, lookup policy có thể khác.

## 13. Hai versions không tạo ra một kiểu chung cho implementation

Kết quả ở mục 11 chứng minh `a.loadClass("lib.Formula") != b.loadClass("lib.Formula")`, dù tên nhị phân giống nhau: **defining loader khác tạo runtime type khác**. Tương tự, hai bản `plugins.CalculatorImpl` không tự cast được sang nhau. Nhưng cả hai vẫn cast được sang **một `spi.Calculator` do parent định nghĩa**.

| Type | Defining loader | Có dùng xuyên hai plugin? |
| --- | --- | --- |
| `lib.Formula` v1/v2 | Lần lượt A và B | Không, mỗi bên là private dependency |
| `plugins.CalculatorImpl` v1/v2 | Lần lượt A và B | Không cast chéo implementation |
| `spi.Calculator` | Host/parent | Có, là shared contract |

Trong scope `main`, có thể kiểm tra thêm:

```java
Class<?> aType = a.loadClass("plugins.CalculatorImpl");
Class<?> bType = b.loadClass("plugins.CalculatorImpl");
System.out.println(aType.getName().equals(bType.getName())); // true
System.out.println(aType == bType); // false
System.out.println(bType.isInstance(c1)); // false
```

**Reflection không hợp nhất class identity.** Nó có thể gọi method của object thuộc loader cụ thể, nhưng type checks, access và các constraints của JVM vẫn áp dụng. Không đưa private `lib.Formula` vào chữ ký public của `spi.Calculator`; giao tiếp qua API/DTO do host định nghĩa.

## 14. Trường hợp isolation thất bại: parent classpath bị nhiễm thư viện

Hãy hình dung host bị cấu hình sai:

```bash
# KHÔNG phải cách chạy đúng cho bài này:
java -cp "out/host:dist/plugin-v1.jar" \
  host.TwoVersions dist/plugin-v1.jar dist/plugin-v2.jar
```

Trên Windows, dùng `";"` thay dấu `":"` trong `-cp` nếu muốn tái hiện, nhưng **không dùng lệnh sai làm production configuration**.

Lúc này parent/application class loader có thể tìm:

```text
plugins.CalculatorImpl
lib.Formula
```

trong `plugin-v1.jar`. Vì `URLClassLoader` mặc định **delegate parent first**, cả A và B có thể nhận class của parent (thay vì class từ JAR riêng):

```text
a.loadClass("plugins.CalculatorImpl") -> Parent class
b.loadClass("plugins.CalculatorImpl") -> Parent class
a.loadClass("lib.Formula")            -> Parent v1
b.loadClass("lib.Formula")            -> Parent v1
```

Điều này có thể khiến output phiên bản B không còn là v2, `Different implementation classes` không còn đúng và `getClassLoader() == b` là `false`.

**Cách khắc phục:** Đặt implementation/dependencies private chỉ trong URL list của plugin loader. Ở parent, giữ **shared SPI/contracts** và các thư viện thật sự cần được chia sẻ giữa host và plugins.

### Nếu parent cần chính thư viện đó?

Khi một framework host buộc mang `lib.Formula` ở parent, có thể cần **custom child-first loader có giới hạn namespace** để cho plugin dùng private copy, hoặc relocation/shading tại build time, hoặc cách ly plugin bằng process. Không nên tự override `loadClass` child-first cho **mọi** package: sẽ gây lỗi với `java.*`, API dùng chung, logging/reflective integration và type identity.

Nếu thật sự triển khai custom policy, thường:

```text
java.* / platform.*       -> always parent/platform
spi.* / shared.api.*      -> parent first
plugin private namespaces -> child first, controlled fallback
others                    -> defined policy (usually parent first)
```

Đây là **pseudocode chính sách**, không phải implementation Java hoàn chỉnh. Cần xử lý `getClassLoadingLock`, `findLoadedClass`, `resolveClass`, class loading errors và policy resources tương ứng.

## 15. Các lỗi thường gặp trong quá trình làm bài

### Lỗi 1 — ClassNotFoundException khi host thử nhìn thấy plugin

Trong demo có đoạn cố ý:

```java
parent.loadClass("plugins.CalculatorImpl");
```

và bắt `ClassNotFoundException` để in `Parent sees implementation: false`. Đây là **kết quả mong muốn**, vì host không được chứa class implementation.

Nếu `a.loadClass("plugins.CalculatorImpl")` mới ném `ClassNotFoundException` thì không phải như vậy. Hãy kiểm tra:

- `plugin-v1.jar` đã chứa entry `plugins/CalculatorImpl.class` chưa?
- `Path.of(args[0]).toUri().toURL()` có trỏ đúng file JAR không?
- Tên binary `plugins.CalculatorImpl` có viết đúng package/class không?
- Có vô tình dùng URL thư mục thiếu dấu `/` hoặc URL protocol không được hỗ trợ không?

### Lỗi 2 — NoClassDefFoundError: spi/Calculator

Plugin implementation cần giải quyết shared interface `spi.Calculator`. Nếu host không có interface này hoặc child parent không nhìn thấy host SPI, JVM có thể thất bại khi định nghĩa/liên kết implementation.

**Cách sửa:** Bảo đảm `spi.Calculator` nằm trong `out/host` và child loaders dùng đúng parent chứa SPI. Không giải quyết bằng cách lén đóng một bản interface độc lập trong mỗi plugin mà không kiểm tra type identity.

### Lỗi 3 — ClassCastException với hai bản spi.Calculator

Nếu custom child-first policy tự định nghĩa `spi.Calculator` riêng trong A và B, object A/B có thể không cast được về interface `spi.Calculator` mà host đang dùng, **mặc dù tên giống nhau**.

**Cách sửa:** Bảo đảm một defining loader chung cho SPI. In:

```java
System.out.println(
    a.loadClass("spi.Calculator") == Calculator.class);
```

Đây là snippet trong method có biến `a` và import `spi.Calculator`. Kết quả kỳ vọng là `true`.

### Lỗi 4 — NoSuchMethodError hoặc IncompatibleClassChangeError

Một implementation được build với thư viện v2 nhưng runtime lỡ resolve `lib.Formula` v1 có API khác. JVM có thể ném `NoSuchMethodError` hoặc một `LinkageError` phù hợp khi cần resolve method/class.

**Cách sửa:** Xác định runtime `lib.Formula` do loader nào định nghĩa và JAR nào cung cấp class. Build/test đúng cặp implementation + dependency, không chỉ dựa vào Maven dependency declaration.

### Lỗi 5 — Static state không tách

Nếu `Calls A` và `Calls B` không độc lập sau khi chạy hai plugin, có thể bạn đang:

- dùng một `lib.Formula` class do parent định nghĩa;
- dùng một shared loader chứa cả hai JARs;
- đặt counter/state ở một **shared class** do parent định nghĩa;
- vô tình giữ một singleton toàn host chứa state của cả plugin.

**Cách sửa:** Xem `Class.getClassLoader()` của private dependency và chỗ khai báo static fields. Class identity mới là yếu tố quyết định static storage.

### Lỗi 6 — Package sealing hoặc signer mismatch

Hai JAR có package trùng tên trong **cùng loader** đôi khi còn gặp `SecurityException` do JAR manifest `Sealed: true` hoặc signer certificate sets khác nhau. Hai plugin loaders riêng tạo runtime packages riêng, nhưng không biến signed JAR thành trusted hay loại bỏ mọi classloading checks.

**Cách sửa:** Kiểm tra packaging/manifest/signing policy; không catch lỗi rồi silently fallback sang nguồn class khác.

### Lỗi 7 — Resource của phiên bản khác

`ClassLoader.getResource` và `getResources` có lookup policy riêng. Nếu bạn viết custom child-first class loading nhưng để resource parent-first, code v2 có thể đọc config/schema của v1. Đặt resource namespaces theo plugin, dùng đúng loader hoặc `SomePluginClass.class.getResourceAsStream` khi phù hợp. Với `META-INF/services` cần bảo toàn nhiều provider descriptors thay vì chọn duy nhất một resource.

### Lỗi 8 — Đóng loader quá sớm

`URLClassLoader.close()` ngăn nạp những classes/resources **mới** do loader ấy cung cấp theo contract. Đóng ngay sau khi tạo instance rồi chạy long-lived plugin có thể gây lỗi khi code dùng một dependency hoặc resource lần đầu sau đó.

**Cách sửa:** Gắn loader với plugin lifecycle; dừng request/tasks, unregister services, đóng resources rồi cuối cùng mới đóng loader.

## 16. Quan sát nguồn lớp bằng JVM logs và Java API

### 16.1. In defining loader

Trong method `main` của demo đã có:

```java
System.out.println(aImpl.getClassLoader() == a);
System.out.println(bImpl.getClassLoader() == b);
```

Đây là cách xác nhận **defining loader object identity**. Đừng chỉ in tên class `lib.Formula` rồi kết luận nó thuộc version nào, vì hai tên giống hệt.

Có thể bổ sung thông tin code source:

```java
Class<?> formulaA = a.loadClass("lib.Formula");
var pd = formulaA.getProtectionDomain();
var source = pd == null ? null : pd.getCodeSource();
System.out.println(source == null
        ? "(unknown)"
        : source.getLocation());
```

Đây là **snippet minh họa** bên trong method. Code source là một chỉ báo về nguồn, **không phải bằng chứng toàn bộ code an toàn/được tin cậy**, và trong custom loader có thể là `null`.

### 16.2. Bật class loading log (HotSpot/OpenJDK)

```bash
java '-Xlog:class+load=info' -cp out/host \
  host.TwoVersions dist/plugin-v1.jar dist/plugin-v2.jar
```

PowerShell:

```powershell
java "-Xlog:class+load=info" -cp out/host host.TwoVersions dist/plugin-v1.jar dist/plugin-v2.jar
```

Log có thể cho thấy nhiều sự kiện `plugins.CalculatorImpl` / `lib.Formula` từ hai JARs khác nhau. Tùy JVM, logging verbosity và thời điểm class loading, định dạng source URL, thời gian và thứ tự dòng khác nhau. **Không viết exact stdout assertion** cho VM diagnostic log; hãy dùng nó để quan sát class origin và đối chiếu `getClassLoader()`.

### 16.3. API tra class theo loader tường minh

```java
Class<?> v1Type = Class.forName("lib.Formula", false, a);
Class<?> v2Type = Class.forName("lib.Formula", false, b);
System.out.println(v1Type == v2Type); // false
```

Đây là snippet có biến `a`, `b`. Overload `Class.forName(name, initialize, loader)` cho phép chỉ rõ loader; `false` không yêu cầu initialization. **`Class.forName("lib.Formula")` một tham số** không tự động dùng plugin loader hay thread context class loader: nó dùng defining loader của calling class. Từ host, nếu `lib.Formula` không có ở parent, lời gọi một tham số có thể thất bại.

## 17. Cần thêm plugin thứ ba thì tổ chức thế nào?

Mỗi plugin có thể gắn với một **generation/loader scope**:

```text
Host + shared SPI
    |
    +-- Plugin A / Loader A / lib.Formula v1
    +-- Plugin B / Loader B / lib.Formula v2
    +-- Plugin C / Loader C / lib.Formula v3
```

Plugin manager nên giữ metadata:

- Plugin ID và version.
- Đường JAR/URL nguồn.
- Loader instance và parent.
- Implementation class name.
- Shared SPI type/version tương thích.
- Instance/start/stop state.
- Service/resource registrations.
- Thread pool/TCCL policy và cleanup hooks.

Không để implementation class hoặc private dependency object từ loader A đi vào API của B nếu không có contract phù hợp. Nếu cần tương tác giữa plugins, nên dùng shared interfaces/DTOs do host định nghĩa, message bus hoặc adapters.

### Hot-reload không phải redefine cùng loader

Nếu `plugin-v1.jar` được thay bằng bản mới trên disk, runtime class `("lib.Formula", A)` đã định nghĩa **không tự thay đổi**. Một loader cũng không thể gọi `defineClass` lần thứ hai cùng binary name để tạo một runtime type mới trong cùng loader.

Thường tạo **loader generation mới**, nạp/cấu hình plugin mới, chuyển request sang generation đó rồi dừng generation cũ. Khi không còn references từ host/threads/caches, loader cũ có thể đủ điều kiện cho JVM/GC thu hồi; **không có API yêu cầu unload class tùy ý, tức thì**.

### Unload và close

`URLClassLoader.close()` đóng resources/JAR handles do loader quản lý; class unloading do JVM/GC quyết định và phụ thuộc loader reachability. `close()` không làm `Class<?>` đã load hoặc các instances biến thành vô hiệu ngay.

Các nguồn giữ loader cũ sống lâu: plugin instances trong registries, `ServiceLoader` caches, event listeners, TCCL của thread pools, `ThreadLocal`, scheduled tasks, reflection handles, logging/JDBC/MBeans và other host references.

## 18. Khi nào nên dùng custom ClassLoader hoặc JPMS thay URLClassLoader?

### Chọn URLClassLoader khi

- Mỗi plugin là một hoặc vài JARs/directories thông thường.
- Parent chỉ chứa shared API/JDK dependencies phù hợp.
- Parent-first delegation đủ để bảo đảm private library từ child được dùng.
- Không cần custom resource policy hoặc bytecode transformations.

Bài lab thuộc chính trường hợp này. **Không cần override `loadClass` hoặc viết `defineClass` trực tiếp** để hoàn thành isolation.

### Cân nhắc custom ClassLoader khi

- Có dependency cùng binary name **đã nằm trên parent** nhưng plugin bắt buộc dùng bản private, cần child-first **chỉ cho namespace cụ thể**.
- Classes đến từ memory/remote storage/container đặc thù.
- Cần resource lookup/`getResources` priority policy riêng, có test để tránh mismatch.
- Có codegen/transformation hoặc plugin framework điều phối namespace phức tạp.

Khi tự override `loadClass`, phải kiểm tra locking/`findLoadedClass`/`resolveClass` và không bắt/nuốt `LinkageError` như thể là `ClassNotFoundException`. Với `java.*` và shared API, phải giữ các nền tảng/type identities đúng.

### Cân nhắc JPMS ModuleLayer khi

- Plugin JARs là **named modules** có `module-info.java`, `requires`, `exports`, `opens` và `provides ... with ...`.
- Bạn cần module configuration/readability/service discovery và module boundaries rõ.
- Có yêu cầu mapping modules vào một hoặc nhiều class loaders.

`ModuleLayer.defineModulesWithOneLoader` và `defineModulesWithManyLoaders` là những chiến lược khác nhau. **Module không đồng nghĩa class loader**, và việc tách named modules chưa chắc tạo isolation tương tự mỗi plugin/JAR một loader. Nên thiết kế module graph, loader mappings và package conflicts rõ ràng trước khi đổi kiến trúc.

## 19. Bảo mật: hai loader riêng không phải hai sandbox

**Class loader isolation không giới hạn độc lập quyền truy cập file, network, CPU hoặc hệ điều hành của code plugin**. Nó chủ yếu cách ly **runtime type identity, versioned dependencies, static state** và hỗ trợ vòng đời.

Một plugin từ nguồn không đáng tin chạy trong cùng JVM vẫn có thể gây side effects qua nhiều APIs mà process được quyền dùng. `SecurityManager` là cơ chế lịch sử đã bị deprecated for removal ở JDK 17 và **permanently disabled từ JDK 24**; không lấy nó làm sandbox mặc định cho một kiến trúc Java hiện đại.

Đối với plugin không đáng tin, cân nhắc **worker process/container** riêng, OS permissions, network egress controls, resource quotas, chặn/kiểm soát native access và một RPC/IPC contract nhỏ. Không suy luận “có hai `URLClassLoader` thì plugin A không thể ảnh hưởng B” ngoài phạm vi class identity.

## 20. Kiểm thử tự động cần có nếu triển khai production

Có thể chuyển các quan sát trong lab thành assertions:

1. Parent không tìm thấy `plugins.CalculatorImpl`.
2. Loader A thực sự là defining loader của implementation A, loader B của implementation B.
3. `a.loadClass("lib.Formula") != b.loadClass("lib.Formula")`.
4. `a.loadClass("spi.Calculator") == b.loadClass("spi.Calculator") == Calculator.class`.
5. `c1.version()` trả `v1`, `c2.version()` trả `v2` khi A=v1, B=v2.
6. `c1.apply(3) == 4`, `c2.apply(3) == 30`.
7. Calls static counters độc lập ở hai versions.
8. Loader chung chứa cả JARs chọn một version theo URL policy; đảo thứ tự URL làm đối chứng.
9. Sau khi kích hoạt plugin, shared API calls hoạt động không cần private type từ loader khác.
10. Plugin lifecycle đóng resources/threads và không lưu references sang plugin loader đã retire.

Đừng viết test phụ thuộc tuyệt đối vào **thời điểm class unload** sau `System.gc()`; GC không phải cơ chế unload theo yêu cầu, và workload/collector có thể khác nhau. Kiểm thử hành vi do ứng dụng kiểm soát và dùng profiling/heap retaining paths để khảo sát memory.

### Một thử thách nhỏ: kiểm tra chéo identity

Trong `main`, sau khi có `aImpl`, `bImpl` và `c1`, thêm:

```java
System.out.println("Same binary name: "
        + aImpl.getName().equals(bImpl.getName()));
System.out.println("A object is B instance: "
        + bImpl.isInstance(c1));
```

Đây là **đoạn chèn minh họa**, không thuộc stdout kiểm chứng nguyên bản. Dự kiến:

```text
Same binary name: true
A object is B instance: false
```

Đó là minh chứng ngắn gọn cho khác biệt giữa **tên** và **runtime type**.

### Thử thách 2: một dependency mới chỉ ở v2

Tạo `lib.Extra` chỉ trong plugin v2 JAR và cho implementation v2 gọi class này. Khi giữ hai loaders riêng, v2 nhìn thấy `lib.Extra`, v1 không cần nhìn thấy. Nếu thay đổi app classpath/JAR URLs thiếu nhất quán, thử nghiệm có thể xuất hiện `NoClassDefFoundError`.

Đây là bài mở rộng **tự thực hiện**; cần thêm file/class và biên dịch lại. Không nên trình bày một output cố định khi chưa chạy đúng mã mở rộng.

### Thử thách 3: quan sát tài nguyên trùng tên

Thêm `plugin.properties` vào cả hai JARs với nội dung `version=v1` và `version=v2`. So sánh `a.getResourceAsStream("plugin.properties")` và `b.getResourceAsStream("plugin.properties")`, rồi `both.getResources("plugin.properties")`. Bạn sẽ thấy bài toán **resource lookup** khác class identity: một loader có thể liệt kê **nhiều tài nguyên cùng tên** nhưng chỉ có một runtime class cho mỗi binary name.

Khi thiết kế loader child-first cho classes, phải kiểm soát resource lookup priority tương ứng nếu resources gắn chặt với version.

## 21. Checklist trước khi hoàn tất bài

- [ ] Biên dịch **hai `lib.Formula` riêng**, không chung output directory.
- [ ] Hai plugin JAR chứa `lib/Formula.class` và `plugins/CalculatorImpl.class`.
- [ ] Host output chỉ có `spi/Calculator.class` và `host/TwoVersions.class`.
- [ ] Runtime command dùng `-cp out/host` — **không** đưa plugin JARs lên parent classpath.
- [ ] Hai loader `a`, `b` dùng cùng parent và **khác URL lists**.
- [ ] A trả version v1 / số 4; B trả version v2 / số 30.
- [ ] Hai implementation `Class<?>` và hai dependency `Class<?>` khác nhau.
- [ ] Shared SPI `Class<?>` giống nhau giữa A/B và host.
- [ ] Static counters độc lập.
- [ ] Một loader chung có cả JARs chọn version đầu theo URL order, không chạy song song hai definitions cùng tên.
- [ ] Đã đối chiếu khi đảo URL order và khi parent bị đưa nhầm implementation private.
- [ ] Biết cách đóng loader và không nhầm `close` với unload.
- [ ] Hiểu vì sao runtime type isolation **không phải security sandbox**.

## 22. Câu hỏi tự kiểm tra

**1. Hai file `lib/Formula.class` có tên giống nhau trong hai JARs. Chúng có thể cùng tồn tại trong JVM không?** Có, nếu chúng được **hai defining loaders khác nhau** định nghĩa.

**2. Vì sao không cho cả hai versions vào cùng một defining loader?** Một defining loader chỉ sở hữu một runtime class cho mỗi binary name; một version có thể shadow version còn lại.

**3. Trong lab, tại sao host có thể cast cả hai CalculatorImpl objects sang `spi.Calculator`?** Vì interface chỉ do parent định nghĩa và cả hai child delegate cho parent.

**4. Dùng hai URLClassLoader nhưng thêm `plugin-v1.jar` vào host `-cp` sẽ ra sao?** Parent-first có thể khiến child trả bản class v1 do parent định nghĩa, phá private-version isolation.

**5. Hai `static int calls` của `lib.Formula` có dùng chung không?** Không; đó là hai static fields trong hai runtime classes khác defining loaders.

**6. Tại sao kết quả loader chung đổi từ v1 sang v2 khi đảo URL order?** `URLClassLoader` tìm URLs theo thứ tự khi parent không cung cấp class, rồi chỉ giữ một definition cùng binary name trong loader đó.

**7. `Class.forName("lib.Formula")` trong host có tự chọn plugin loader theo thread context không?** Không; overload một tham số sử dụng defining loader của calling class. Dùng overload có loader argument nếu cần chỉ rõ.

**8. Hai implementation classes cùng tên có ép kiểu sang nhau được không?** Không chỉ vì tên giống; runtime class identity phụ thuộc defining loader.

**9. `URLClassLoader.close()` có xóa runtime classes ngay không?** Không; nó giải phóng nguồn/handles theo API, class unloading do JVM/GC quyết định.

**10. Hai class loaders riêng có bảo đảm chạy mã plugin không đáng tin an toàn không?** Không; cần process/OS isolation và quyền thực thi được kiểm soát.

**11. Khi nào chọn custom child-first loader?** Khi namespace private cần thắng bản trùng tên trên parent và đã có policy package, locking, resource lookup và shared API rõ ràng.

**12. Bài tập này chứng minh isolation ở mức nào?** **Class identity, dependency version và static state** của private classes; không tự chứng minh process-security isolation hoặc hot unload.

## 23. Nguồn tham khảo

- **Java SE 17 `ClassLoader`** — binary names, defining loader, parent delegation, `loadClass`, `findClass`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- **Java SE 17 `URLClassLoader`** — tra class/resources theo thứ tự URLs sau parent, `close()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- **JVMS Java SE 17 §5.3 — Creation and Loading** — runtime class identity gắn với binary name + defining loader: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- **Java SE 17 `Class.forName`** — overload có tên, `initialize` và loader tường minh: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- **Java SE 17 `ServiceLoader`** — dùng shared service type, discovery providers, TCCL/module variants: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- **Java SE 17 `ModuleLayer`** — alternatives cho named-module plugins và loader mappings: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html
- **JLS Java SE 17 §§12.2–12.4** — loading, linking và initialization: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html

**Ghi nhớ:** **Hai versions của cùng `lib.Formula` có thể chạy song song vì được hai class loaders khác nhau định nghĩa.** Hãy để **SPI/shared contracts ở parent**, còn implementation và dependencies private nằm trong các JAR/loader riêng. Luôn xác minh `getClassLoader()`, class identity, static state và thứ tự URL; đừng nhầm “hai JARs” với “hai namespaces” nếu chúng đang được nạp bởi **một loader**.
