# Biên dịch lại với --release và kiểm chứng trên JDK tối thiểu

Trong một đợt **Java Advance Compatibility Migration**, tổ chức có thể dùng JDK mới trên máy phát triển và CI nhưng vẫn cam kết phần mềm chạy được trên một JDK thấp hơn. Ví dụ build bằng **JDK 21**, đặt mục tiêu **Java 17**, sau đó kiểm tra artifact bằng **runtime JDK 17** thực tế.

Nếu chỉ chạy compiler với JDK 21, output có thể mang classfile Java 21 và không chạy trên Java 17. Nếu chỉ dùng `-source 17 -target 17`, compiler có thể vẫn cho phép gọi Java 21 API. Nếu dùng đúng `--release 17` nhưng không thử chạy trên Java 17, ứng dụng vẫn có thể lỗi vì thư viện bên thứ ba, plugin, reflection, JNI hoặc startup flags.

Bài thực hành này đi từ source Java tối giản đến JAR phát hành, kết hợp **thử nghiệm thành công**, **thử nghiệm thất bại có chủ đích**, kiểm tra phiên bản bytecode và kiểm thử runtime tối thiểu. Sau đó chuyển cùng nguyên tắc sang Maven, Gradle và CI.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt JDK chạy build, JDK compiler, Java release target và JDK tối thiểu ở runtime.
2. Biên dịch source bằng `javac --release` và hiểu các hạn chế về ngôn ngữ, API và bytecode.
3. Dùng `javap` xác định major version của classfile.
4. Đóng gói executable JAR và chạy nó bằng đúng JVM tối thiểu.
5. Quan sát cách `--release` chặn API chỉ tồn tại ở JDK mới.
6. Chứng minh `-source`/`-target` không thay thế được `--release`.
7. Phát hiện giới hạn khi third-party dependencies, dynamic loading và plugin không phù hợp JDK tối thiểu.
8. Đưa một minimum-runtime gate có thể kiểm chứng vào pipeline.

Trong toàn bộ ví dụ, chúng ta chọn:

| Thành phần | Phiên bản |
|---|---|
| Máy build và compiler | JDK 21 |
| Target cho Java source và Java SE API | `--release 17` |
| JDK tối thiểu được cam kết | JDK 17 |
| JDK bổ sung để so sánh | JDK 21 |
| Application | Java SE CLI nhỏ, không cần framework |

Đây là **tổ hợp minh họa**, không phải tuyên bố mọi framework/dependency đều chạy được trên JDK 17. Với dự án thật, phải đối chiếu support matrix trước.

## 2. Bốn giá trị không được đánh đồng

Một quy trình có thể trông như sau:

~~~text
CI runner
   |
   +-- Maven/Gradle chạy bằng JDK 21
   |
   +-- javac từ JDK 21, với --release 17
   |       |
   |       v
   |    Application classfile target 17
   |       |
   |       v
   |    Package JAR
   |
   +-- Smoke/integration job dùng JDK 17
   |       |
   |       v
   |    Chạy chính JAR vừa build
   |
   +-- Runtime test bổ sung trên JDK 21
~~~

**Build JDK** là JVM chạy Maven/Gradle. **Compiler JDK** là bộ `javac` thực sự tạo bytecode, có thể được chọn qua Java toolchains. **Release target** là ngôn ngữ, Java SE API và classfile level mà compiler được yêu cầu hỗ trợ. **Runtime JDK** là JVM nạp và thực thi artifact.

Mặc dù trong ví dụ compiler và build tool đều dùng JDK 21, các giá trị này có thể tách biệt trong Maven/Gradle toolchains.

### 2.1. Vì sao cần kiểm thử runtime?

`--release` giúp bắt lỗi tại thời điểm compile nhưng không tự chạy phần mềm. Nó không kiểm tra đầy đủ các lỗi có thể phát sinh ở runtime như `ServiceLoader`, `Class.forName`, nạp JDBC driver, SSL handshake, native library hoặc Java agent.

Do đó cần tối thiểu hai lớp bằng chứng:

- **Compile gate:** tạo output có Java release target đúng.
- **Minimum-runtime gate:** chạy chính artifact cuối trên JVM tối thiểu và thực hiện các kịch bản quan trọng.

## 3. --release làm được gì?

Lệnh:

~~~bash
javac --release 17 ...
~~~

yêu cầu compiler hỗ trợ target Java 17 về:

- **Source language level:** không chấp nhận cú pháp chỉ có ở Java release mới hơn.
- **Classfile target:** tạo classfile tương ứng Java 17.
- **Platform API exposure:** khi source được biên dịch, chỉ nhìn thấy Java SE APIs phù hợp release 17 theo dữ liệu API target mà compiler cung cấp.

Ví dụ Java 21 thêm API `List.getFirst()`; source gọi method này phải bị từ chối khi compile `--release 17`.

### 3.1. --release không giải quyết mọi vấn đề tương thích

Nó không tự:

- Chuyển bytecode của JAR dependencies từ target 21 về target 17.
- Kiểm tra API gọi qua reflection.
- Đảm bảo mọi framework/plugin hỗ trợ Java 17.
- Chọn đúng Java executable trong Docker/systemd/Windows service.
- Cung cấp file resources hoặc native libraries.
- Đảm bảo TLS, timezone, locale và security providers giống nhau.
- Xác minh behavioral contracts hoặc persistence compatibility.
- Tạo bộ runtime Java 17 đi kèm artifact.

Điều này sẽ được chứng minh trong các phần thử nghiệm bên dưới.

## 4. Chuẩn bị hai JDK

Giả sử đã cài JDK 21 và JDK 17, với biến môi trường:

~~~text
JAVA21_HOME = thư mục cài JDK 21
JAVA17_HOME = thư mục cài JDK 17
~~~

Trên Bash:

~~~bash
"$JAVA21_HOME/bin/java" -version
"$JAVA21_HOME/bin/javac" -version
"$JAVA17_HOME/bin/java" -version
~~~

Trên Windows PowerShell:

~~~powershell
& "$env:JAVA21_HOME\bin\java.exe" -version
& "$env:JAVA21_HOME\bin\javac.exe" -version
& "$env:JAVA17_HOME\bin\java.exe" -version
~~~

Bạn cần xác nhận compiler thật là JDK 21 và JVM runtime tối thiểu thật là JDK 17. Nếu chỉ gọi `java -version` từ `PATH`, bạn chưa biết `javac` hoặc process Java khác đang dùng JDK nào.

Không có Java 17 trên máy local? Có thể chạy runtime gate trên CI runner hoặc container JDK 17 được quản lý. Nhưng **không đánh dấu kiểm thử PASS khi chưa thực sự chạy artifact trên Java 17**.

## 5. Cấu trúc project thực hành

Tạo project:

~~~text
compat-release-lab/
├── src/
│   ├── main/
│   │   └── java/com/acme/compat/CompatDemo.java
│   ├── test/
│   │   └── java/com/acme/compat/CompatSmoke.java
│   └── negative/
│       └── java/com/acme/compat/TooNewApi.java
└── build/
    ├── classes/
    └── test-classes/
~~~

Bash:

~~~bash
mkdir -p src/main/java/com/acme/compat
mkdir -p src/test/java/com/acme/compat
mkdir -p src/negative/java/com/acme/compat
mkdir -p build/classes build/test-classes
~~~

Trong PowerShell, có thể tạo các thư mục tương đương bằng IDE hoặc `New-Item -ItemType Directory -Force`. Các ví dụ file và lệnh được chạy từ thư mục root `compat-release-lab`.

## 6. Viết ứng dụng dùng Java 17 API

Tạo `src/main/java/com/acme/compat/CompatDemo.java`:

~~~java
package com.acme.compat;

import java.nio.charset.StandardCharsets;
import java.util.HexFormat;
import java.util.Objects;

public final class CompatDemo {

    private CompatDemo() {
    }

    public static String encode(String value) {
        Objects.requireNonNull(value, "value");
        return HexFormat.of().formatHex(
                value.getBytes(StandardCharsets.UTF_8));
    }

    public static void main(String[] args) {
        String text = args.length == 0 ? "Java" : args[0];

        System.out.println("input=" + text);
        System.out.println("hex=" + encode(text));
        System.out.println(
                "runtime=" + System.getProperty("java.version"));
    }
}
~~~

`java.util.HexFormat` là Java SE API có từ Java 17. Vì vậy nó phù hợp với release target 17 nhưng không thể dùng trong source targeting Java 11 nếu không có phương án thay thế.

Với input `Java`, hai dòng đầu phải là:

~~~text
input=Java
hex=4a617661
~~~

Dòng `runtime` giúp thấy JVM thực sự chạy ứng dụng. Nó không thay thế việc ghi đầy đủ vendor/version của Java executable trong log CI.

## 7. Biên dịch bằng JDK 21 với --release 17

Trên Bash:

~~~bash
"$JAVA21_HOME/bin/javac" \
  --release 17 \
  -encoding UTF-8 \
  -d build/classes \
  src/main/java/com/acme/compat/CompatDemo.java
~~~

Trên PowerShell:

~~~powershell
& "$env:JAVA21_HOME\bin\javac.exe" --release 17 -encoding UTF-8 -d build\classes src\main\java\com\acme\compat\CompatDemo.java
~~~

Giải thích:

| Tham số | Ý nghĩa |
|---|---|
| `$JAVA21_HOME/bin/javac` | Compiler JDK 21 |
| `--release 17` | Target Java 17 |
| `-encoding UTF-8` | Source encoding |
| `-d build/classes` | Output directory |
| Tên file `.java` | Source cần compile |

Kết quả mong đợi:

~~~text
build/classes/com/acme/compat/CompatDemo.class
~~~

Đây là bước **biên dịch**, chưa chứng minh runtime compatibility.

### 7.1. Nếu báo release version not supported

Ví dụ:

~~~text
error: release version 17 not supported
~~~

Nguyên nhân thường là `javac` được chọn không hỗ trợ target đó. Kiểm tra:

~~~bash
"$JAVA21_HOME/bin/javac" -version
"$JAVA21_HOME/bin/javac" --help
~~~

Không nên chỉ xóa `--release` để build xanh, vì khi đó compiler có thể dùng target mặc định khác minimum JDK của sản phẩm.

## 8. Kiểm tra classfile bằng javap

Sau compile:

~~~bash
"$JAVA21_HOME/bin/javap" \
  -verbose \
  -classpath build/classes \
  com.acme.compat.CompatDemo
~~~

Tìm dòng:

~~~text
major version: 61
~~~

Bảng mốc:

| Java release | Classfile major |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Dù compiler chạy ở JDK 21, `--release 17` tạo classfile target Java 17 (major version 61).

Lọc nhanh trên Bash:

~~~bash
"$JAVA21_HOME/bin/javap" -verbose \
  -classpath build/classes \
  com.acme.compat.CompatDemo | grep "major version"
~~~

Trên PowerShell:

~~~powershell
& "$env:JAVA21_HOME\bin\javap.exe" -verbose -classpath build\classes com.acme.compat.CompatDemo | Select-String "major version"
~~~

**Major version đúng là điều kiện cần, không phải bằng chứng toàn bộ app chạy được.** Một dependency ở runtime có thể vẫn chứa classfile major 65 hoặc một plugin gọi API không có trên Java 17.

## 9. Thử chạy class bằng JDK 17

Bash:

~~~bash
"$JAVA17_HOME/bin/java" \
  -cp build/classes \
  com.acme.compat.CompatDemo Java
~~~

Kỳ vọng:

~~~text
input=Java
hex=4a617661
runtime=17...
~~~

Chuỗi `runtime=17...` phụ thuộc phiên bản Java 17 update được cài.

Nếu lệnh chạy thành công, bạn đã có bằng chứng một số hành vi của class hiện tại chạy trên Java 17. Nhưng chúng ta vẫn cần đóng JAR và chạy artifact thật.

## 10. Đóng executable JAR từ các class đã biên dịch

Dùng JDK 21:

~~~bash
"$JAVA21_HOME/bin/jar" \
  --create \
  --file build/compat-demo.jar \
  --main-class com.acme.compat.CompatDemo \
  -C build/classes .
~~~

Liệt kê nội dung:

~~~bash
"$JAVA21_HOME/bin/jar" \
  --list --file build/compat-demo.jar
~~~

JAR cần chứa:

~~~text
META-INF/MANIFEST.MF
com/acme/compat/CompatDemo.class
~~~

Bây giờ chạy **chính file JAR** bằng Java 17:

~~~bash
"$JAVA17_HOME/bin/java" \
  -jar build/compat-demo.jar Java
~~~

Kỳ vọng vẫn có `hex=4a617661` và dòng runtime Java 17.

### 10.1. Vì sao đóng JAR rồi thử lại?

Trong project thật, packaging có thể làm mất resource, thiếu dependency, sai manifest, dùng loader riêng hoặc chứa classfile không mong đợi. Kiểm chứng chỉ bằng output directory của compiler không thay thế kiểm chứng **distribution cuối**.

`Main-Class` chỉ chỉ định entrypoint. Nó không tự hạ classfile version hay đóng gói runtime dependencies.

## 11. Thêm smoke test Java thuần

Tạo `src/test/java/com/acme/compat/CompatSmoke.java`:

~~~java
package com.acme.compat;

public final class CompatSmoke {

    public static void main(String[] args) {
        expect("4a617661", CompatDemo.encode("Java"));
        expect("", CompatDemo.encode(""));

        boolean rejectedNull = false;
        try {
            CompatDemo.encode(null);
        } catch (NullPointerException expected) {
            rejectedNull = true;
        }

        if (!rejectedNull) {
            throw new AssertionError(
                    "Null input should be rejected");
        }

        System.out.println("SMOKE_OK");
    }

    private static void expect(String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    "Expected " + expected + ", got " + actual);
        }
    }
}
~~~

Bài test không cần JUnit nên tập trung vào compiler/runtime. Nó xác minh output hex, xử lý chuỗi rỗng và lỗi khi input `null`.

Compile test bằng JDK 21 target 17:

~~~bash
"$JAVA21_HOME/bin/javac" \
  --release 17 \
  -encoding UTF-8 \
  -classpath build/classes \
  -d build/test-classes \
  src/test/java/com/acme/compat/CompatSmoke.java
~~~

Chạy test bằng Java 17:

~~~bash
"$JAVA17_HOME/bin/java" \
  -cp "build/classes:build/test-classes" \
  com.acme.compat.CompatSmoke
~~~

Windows PowerShell:

~~~powershell
& "$env:JAVA17_HOME\bin\java.exe" -cp "build\classes;build\test-classes" com.acme.compat.CompatSmoke
~~~

Kỳ vọng:

~~~text
SMOKE_OK
~~~

**Lưu ý:** classpath separator trên Unix-like thường là `:`, trên Windows là `;`.

### 11.1. Tại sao compile test target 17 chưa đủ?

Vì nếu test runner vẫn chạy bằng JDK 21, bạn chưa thực thi các method trên runtime Java 17. Hãy ghi lại Java executable mà process test thật sự dùng.

## 12. Thử âm tính: gọi API Java 21

Tạo `src/negative/java/com/acme/compat/TooNewApi.java`:

~~~java
package com.acme.compat;

import java.util.List;

public final class TooNewApi {

    public static void main(String[] args) {
        String first = List.of("A", "B").getFirst();
        System.out.println(first);
    }
}
~~~

`List.getFirst()` được bổ sung trong Java 21 thông qua các API sequenced collections; nó không có trong Java 17.

Thử biên dịch bằng JDK 21 nhưng target 17:

~~~bash
"$JAVA21_HOME/bin/javac" \
  --release 17 \
  -d build/negative17 \
  src/negative/java/com/acme/compat/TooNewApi.java
~~~

**Kết quả mong đợi là compile thất bại**, thông báo có thể là:

~~~text
error: cannot find symbol
  symbol:   method getFirst()
~~~

Đây là lỗi tốt: `--release 17` đang ngăn source tham chiếu Java 21 API.

### 12.1. Không đưa negative fixture vào main source set

File `TooNewApi.java` nằm trong thư mục `src/negative` riêng để dùng cho bài thực hành. Nếu đưa nó vào source set production, build sẽ fail như dự kiến. Với CI, có thể chạy bước negative-test có xử lý exit code riêng.

## 13. Thử compile file đó với --release 21

~~~bash
"$JAVA21_HOME/bin/javac" \
  --release 21 \
  -d build/negative21 \
  src/negative/java/com/acme/compat/TooNewApi.java
~~~

Trên JDK 21, ví dụ này có thể compile thành công vì API được hỗ trợ.

Dùng `javap` trên class mới:

~~~bash
"$JAVA21_HOME/bin/javap" \
  -verbose \
  -classpath build/negative21 \
  com.acme.compat.TooNewApi
~~~

Kỳ vọng classfile:

~~~text
major version: 65
~~~

Chạy bằng Java 17:

~~~bash
"$JAVA17_HOME/bin/java" \
  -cp build/negative21 \
  com.acme.compat.TooNewApi
~~~

Kết quả dự kiến là lỗi `UnsupportedClassVersionError` vì runtime Java 17 không hỗ trợ classfile target Java 21. Đây là lỗi khác với `cannot find symbol` lúc compile.

## 14. Phân biệt --release và -source/-target

Một project cũ có thể dùng:

~~~bash
javac -source 17 -target 17 ...
~~~

Tuy nhiên, hai cờ này **không bảo vệ Java SE API availability của target giống `--release`** khi compiler là JDK mới hơn.

Thử cùng file `TooNewApi.java`:

~~~bash
"$JAVA21_HOME/bin/javac" \
  -source 17 \
  -target 17 \
  -d build/unsafe \
  src/negative/java/com/acme/compat/TooNewApi.java
~~~

Ví dụ có thể compile được bằng JDK 21: classfile mang major version 61 nhưng bytecode vẫn gọi `List.getFirst()`.

Chạy:

~~~bash
"$JAVA17_HOME/bin/java" \
  -cp build/unsafe \
  com.acme.compat.TooNewApi
~~~

Java 17 đọc được classfile major 61, nhưng không có method `List.getFirst()`. Một lỗi điển hình là:

~~~text
java.lang.NoSuchMethodError
~~~

### 14.1. Bảng so sánh

| Cấu hình | Bytecode target | Java SE API bị giới hạn theo target? | Kết quả quan trọng |
|---|---|---|---|
| JDK 21, không cờ target | 21 | Theo platform JDK 21 | Không cam kết Java 17 |
| JDK 21, `-source 17 -target 17` | 17 | Không tương đương `--release 17` | Có thể gọi API Java 21 |
| JDK 21, `--release 17` | 17 | Có | Giảm rủi ro tham chiếu API mới |
| JDK 17, target mặc định | 17 | Theo platform JDK 17 | Vẫn cần test runtime |

Nếu dự án muốn hỗ trợ Java 17, ưu tiên `--release 17` hoặc cấu hình build tool truyền option tương đương. Đừng dùng `-target` làm bằng chứng đầy đủ cho Java SE API compatibility.

## 15. Thử dùng HexFormat với --release 11

Ứng dụng chính dùng `HexFormat` (API Java 17). Thử:

~~~bash
"$JAVA21_HOME/bin/javac" \
  --release 11 \
  -d build/negative11 \
  src/main/java/com/acme/compat/CompatDemo.java
~~~

Kỳ vọng compiler không tìm thấy `java.util.HexFormat` vì API đó chưa có trên Java 11.

Điều này giúp kiểm tra tính nhất quán của target policy:

- Nếu minimum JDK là 17, `HexFormat` hợp lệ.
- Nếu minimum JDK là 11, phải thay implementation encode hoặc thay yêu cầu minimum runtime.
- Không nên chỉnh con số target chỉ để build xanh mà chưa xem consumers còn chạy Java nào.

## 16. Vì sao classfile major đúng vẫn chưa đủ?

Ứng dụng có thể compile target 17 nhưng mang một third-party library được compile target 21.

~~~text
app.jar
  com/acme/app/Main.class        -> major 61

vendor-library.jar
  com/vendor/Feature.class       -> major 65

Java 17 runtime
  -> Main load được
  -> Feature được nạp khi request chạy
  -> UnsupportedClassVersionError
~~~

`--release 17` chỉ áp dụng cho source đang được compiler biên dịch theo target. Nó không rewrite class files của dependencies.

### 16.1. Ví dụ thư viện Java 21

Tạo một file riêng:

~~~java
package com.acme.lib;

public final class Only21 {
    public static String answer() {
        return "Library built with Java 21";
    }
}
~~~

Giả sử nằm tại `src/lib21/java/com/acme/lib/Only21.java`. Compile:

~~~bash
"$JAVA21_HOME/bin/javac" \
  --release 21 \
  -d build/lib21-classes \
  src/lib21/java/com/acme/lib/Only21.java
~~~

Đóng JAR:

~~~bash
"$JAVA21_HOME/bin/jar" \
  --create \
  --file build/lib21.jar \
  -C build/lib21-classes .
~~~

Một application compile bằng JDK 21 với `--release 17` có thể dùng `lib21.jar` làm compile dependency. Compiler JDK 21 có khả năng đọc classfile của thư viện, nhưng **Java 17 runtime sẽ không thể nạp classfile major 65** khi code cần tới nó.

Bài tập: thêm một ứng dụng nhỏ gọi `Only21.answer()`, compile ứng dụng với `--release 17 -classpath build/lib21.jar`, rồi chạy trên Java 17. Quan sát lỗi và xem major version của `Only21.class`. Đừng trộn fixture này vào main app đã kiểm thử xanh.

### 16.2. Kết luận cho dependencies

Cần kiểm tra:

- Runtime dependencies và transitive versions thực tế.
- Minimum Java requirement của framework, JDBC driver, JSON library, logging và agents.
- Classfile version của các thư viện nghi ngờ.
- Những class chỉ được load ở chức năng ít dùng.
- Native libraries và operating system requirements.

Một `jdeps` report hoặc classfile scan hữu ích nhưng **không thay thế runtime integration tests**.

## 17. Reflection và dynamic invocation vượt ngoài API guard

Xét code:

~~~java
try {
    java.lang.reflect.Method method =
        java.util.List.class.getMethod("getFirst");

    System.out.println("Method present: " + method);
} catch (NoSuchMethodException expectedOnOldJdk) {
    System.out.println("Method not available");
}
~~~

Đoạn code này có thể compile với `--release 17` vì tên method `"getFirst"` nằm trong string; compiler không coi nó là lời gọi tĩnh đến `List.getFirst()`.

Ở runtime:

- Java 17: reflection không tìm thấy method.
- Java 21: method có thể tồn tại.

Tương tự với `Class.forName`, `MethodHandle`, Java SPI, plugin discovery và frameworks dùng tên class từ configuration.

Nếu ứng dụng có optional feature theo JDK version, cần fallback được test trên **JDK thấp nhất**, không chỉ code path chạy trên JDK mới.

## 18. ServiceLoader và plugin còn có rủi ro riêng

Một ứng dụng có thể gọi:

~~~java
ServiceLoader<MyService> providers =
    ServiceLoader.load(MyService.class);
~~~

Code compile được với `--release 17` nhưng provider JAR có thể:

- Không nằm trên runtime classpath/module path.
- Có classfile version cao hơn 17.
- Sử dụng Java 21 APIs trong một callback hiếm.
- Có `META-INF/services` hoặc JPMS `provides` metadata sai.
- Bundle bản SPI API khác gây classloader identity mismatch.

Trong migration thật, phải test **provider binaries đang được dùng**, không chỉ source code nội bộ được compile lại.

Một unit test không dùng ServiceLoader có thể pass nhưng ứng dụng fail khi bắt đầu load plugin. Cần đưa đường discovery và callback vào runtime gate.

## 19. Compiler target không kiểm soát Java agent

Java agent có thể được gắn khi launch:

~~~bash
"$JAVA17_HOME/bin/java" \
  -javaagent:/opt/agent/monitoring.jar \
  -jar build/compat-demo.jar
~~~

Đây là ví dụ cấu hình: không có nghĩa file agent đã tồn tại trong lab.

Agent có thể cần runtime target riêng, bytecode library phù hợp, quyền reflection và JDK flags khác. Nâng app compiler lên JDK 21 không tự cập nhật agent; hạ `--release` cũng không giúp agent cũ hỗ trợ JDK mới.

Đối với sản phẩm có APM/profiler/tracing/security agent, minimum-runtime test nên chạy với **cấu hình agent thực tế** và test các class được instrument.

## 20. Maven: đặt maven.compiler.release

Một Maven project có thể định nghĩa:

~~~xml
<properties>
  <maven.compiler.release>17</maven.compiler.release>
  <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Hoặc khai báo trực tiếp:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-compiler-plugin</artifactId>
  <version>3.13.0</version>
  <configuration>
    <release>17</release>
  </configuration>
</plugin>
~~~

Đây là một phiên bản plugin có thật dùng để minh họa cú pháp, không phải khuyến nghị luôn dùng bản này cho mọi Maven/JDK hoặc khẳng định đây là bản mới nhất. Dự án phải chọn theo policy và support matrix.

Kiểm tra Maven process:

~~~bash
./mvnw --version
~~~

Biên dịch:

~~~bash
./mvnw -B clean package
~~~

Nhưng **Maven test không tự chạy bằng Java 17 chỉ vì compiler target 17**. Nếu Maven process dùng JDK 21, các tests được fork bởi Surefire/Failsafe có thể cũng dùng JDK 21 khi chưa cấu hình Java toolchain/test JVM riêng.

### 20.1. Minimum runtime job riêng

Có thể tổ chức:

~~~text
Job Build:
  Maven JVM JDK 21
  maven.compiler.release = 17
  Package app.jar
  Publish checksum + artifact

Job Runtime:
  Java executable từ JDK 17
  Download chính app.jar ở job Build
  Chạy smoke/integration tests
  Ghi runtime vendor/build
~~~

Cách này giúp phân biệt compile pass với runtime pass.

### 20.2. Maven Jar Plugin

Nếu muốn tạo runnable JAR cho `CompatDemo`:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-jar-plugin</artifactId>
  <version>3.4.2</version>
  <configuration>
    <archive>
      <manifest>
        <mainClass>com.acme.compat.CompatDemo</mainClass>
      </manifest>
    </archive>
  </configuration>
</plugin>
~~~

Maven Jar Plugin thông thường chỉ đóng class/resource của module. Nếu app dùng external runtime libraries, phải cung cấp chúng qua distribution/launcher hoặc packaging plugin phù hợp. Đừng dùng `java -jar` trên thin JAR thiếu dependencies rồi quy kết do `--release`.

## 21. Maven Toolchains và test plugins

Maven Toolchains có thể chọn JDK cho những plugins hỗ trợ toolchain. Tuy nhiên:

- JDK chạy Maven process có yêu cầu riêng.
- Compiler JDK có thể khác Maven runtime JDK.
- `<release>17</release>` không tự đặt test JVM thành Java 17.
- Surefire/Failsafe cần configuration riêng nếu mục tiêu là fork test bằng minimum JDK.

Một cách kiểm chứng độc lập là chạy artifact bằng executable Java 17 ở CI job riêng. Nếu dùng toolchains, phải log toolchain được chọn và xác nhận test JVM thực tế chứ không chỉ nhìn POM.

## 22. Gradle: Java toolchain và options.release

Trong `build.gradle` (Groovy DSL):

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Cấu hình diễn đạt rõ:

- Compile dùng JDK 21 toolchain.
- Source, Java SE API và classfile target là 17.
- Gradle daemon có JVM support constraints riêng.
- Test/JavaExec tasks không nhất thiết cùng JVM với compiler.

### 22.1. Chạy Gradle Test bằng Java 17

Với Gradle versions hỗ trợ APIs tương ứng, có thể khai báo:

~~~groovy
tasks.withType(Test).configureEach {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Cấu hình này cần JDK 17 toolchain được cung cấp/tìm thấy theo policy. Không nên ngầm kết luận Gradle đã chọn đúng JDK nếu test setup chưa được quan sát.

Ví dụ lệnh:

~~~bash
./gradlew --version
./gradlew clean test
~~~

`./gradlew --version` thường phản ánh JVM Gradle đang chạy, không đủ bằng chứng cho mỗi Test JVM. Khi cần, log Java version ngay trong process test hoặc chạy smoke trực tiếp bằng JDK 17.

## 23. Gradle Application Plugin và artifact cuối

Một ứng dụng có thể dùng:

~~~groovy
plugins {
    id 'application'
}

application {
    mainClass = 'com.acme.compat.CompatDemo'
}
~~~

Application Plugin có thể tạo distribution qua:

~~~bash
./gradlew installDist
~~~

Distribution thường gồm JAR, runtime libraries và startup scripts. Cần kiểm tra startup script dùng runtime nào khi triển khai, kể cả `JAVA_HOME` và `PATH`.

Một project có thể compile target 17 nhưng generated script hoặc framework loader chỉ được test trên 21. Vì vậy minimum-runtime test phải chạy **đúng distribution có thể phát hành**, không chỉ class ở `build/classes`.

## 24. --release và JPMS

Nếu application có `module-info.java`, module descriptor cũng được biên dịch theo target release tương ứng.

Ví dụ:

~~~java
module com.acme.compat {
    requires java.logging;
    exports com.acme.compat.api;
}
~~~

Cần chú ý:

- JPMS bắt đầu từ Java 9; không thể coi một descriptor Java 9+ là phần bình thường của source target Java 8.
- Third-party JAR có thể là explicit module, automatic module hoặc nằm trên classpath.
- Module names và `requires` phải khớp.
- `exports`/`opens` ảnh hưởng accessibility/reflection.
- Java runtime image được tạo bằng `jlink` có thể thiếu system modules.
- Module path ở CI có thể khác production.

`--release 17` không thay thế kiểm thử module resolution khi launch bằng `java --module ...`. Một app compile target 17 vẫn có thể gặp `FindException: Module ... not found` do runtime module path thiếu artifact.

## 25. Multi-release JAR không được đánh giá qua một classfile

Một multi-release JAR có thể chứa:

~~~text
com/acme/codec/Parser.class
META-INF/versions/11/com/acme/codec/Parser.class
META-INF/versions/17/com/acme/codec/Parser.class
META-INF/versions/21/com/acme/codec/Parser.class
~~~

và manifest:

~~~text
Multi-Release: true
~~~

Một runtime có hỗ trợ sẽ chọn versioned entries theo quy tắc tương ứng. Điều này cho phép một thư viện có baseline cũ nhưng implementation tối ưu cho JDK mới.

Vì thế:

- Classfile 65 dưới `META-INF/versions/21` không nhất thiết làm Java 17 không chạy được JAR.
- Nếu classfile 65 được đặt ở base path và Java 17 cần nạp, đó là vấn đề.
- Shading/repackaging phải bảo toàn structure và manifest metadata.
- Test trên Java 17 thật mới chứng minh version selection đi đúng đường.

## 26. Tương thích API không đồng nghĩa tương thích hành vi

Ngay cả khi bytecode và APIs phù hợp, runtime vẫn có thể khác do:

- Default locale/timezone/charset.
- TLS algorithms, keystore, CA certificates.
- GC/JIT và container memory ergonomics.
- Filesystem path/permissions.
- Native libraries, OS/architecture.
- Runtime flags hoặc Java agent.
- Reflection behavior hoặc module encapsulation.
- Behavior thay đổi giữa framework/library versions.

Để giảm phụ thuộc vào defaults, có thể dùng charset tường minh:

~~~java
String text = new String(bytes, StandardCharsets.UTF_8);
~~~

Tuy nhiên việc chọn charset/timezone phải nhất quán với contract dữ liệu cũ. Không tự đổi mặc định trong migration khi chưa xác định semantic hiện tại.

## 27. JVM options và startup command cũng cần kiểm chứng

Ví dụ khởi chạy bằng Java 17:

~~~bash
"$JAVA17_HOME/bin/java" \
  -Xms256m \
  -Xmx512m \
  -Duser.timezone=UTC \
  -jar build/compat-demo.jar Java
~~~

JVM options ở trước `-jar`. Những arguments nằm sau tên JAR được truyền cho application, trừ khi framework tự diễn giải theo cách riêng.

Sai mục đích:

~~~bash
"$JAVA17_HOME/bin/java" -jar build/compat-demo.jar -Xmx512m
~~~

`-Xmx512m` ở đây chỉ là application argument. Một option JVM không được JDK 17 hỗ trợ có thể khiến launcher thất bại trước khi main chạy, dù classes compile `--release 17` đúng.

## 28. Kiểm thử runtime bằng đúng production artifact

Một minimum-runtime smoke test cần:

1. Lấy artifact cuối do CI build, không rebuild một bản khác trong bước test.
2. Ghi SHA-256 hoặc checksum của artifact đó.
3. Chọn Java executable từ JDK 17 cụ thể.
4. Chạy startup/health/CLI hoặc API kịch bản tối thiểu.
5. Kiểm tra stdout/stderr và exit code.
6. Kiểm tra resources/dependencies thực sự được nạp.
7. Chạy critical integration paths: DB, HTTP, broker, TLS, plugins.
8. Thử graceful shutdown nếu là service.
9. Ghi version JDK và runtime environment vào report.

Nếu bài lab chỉ chạy `CompatDemo` mà không có external integrations, PASS chỉ chứng minh luồng CLI đơn giản. Nó không có nghĩa một enterprise service với Hibernate, Spring, Kafka và JDBC cũng đã được kiểm tra.

### 28.1. Biên dịch một lần, test nhiều runtime

~~~text
Commit X
   |
   v
Build with JDK 21, --release 17
   |
   v
Artifact SHA-256 = H
   |
   +--> Java 17 runtime test (artifact H)
   |
   +--> Java 21 runtime test (artifact H)
   |
   v
Release only after required gates
~~~

Nếu mỗi runtime job tự biên dịch artifact bằng JDK riêng, nhóm không còn so sánh chính xác cùng binary distribution.

## 29. Ma trận kiểm thử gợi ý

| Compiler | Target | Runtime | Kết quả mong đợi |
|---|---|---|---|
| JDK 21 | `--release 17` | Java 17 | **Phải pass** với kịch bản được hỗ trợ |
| JDK 21 | `--release 17` | Java 21 | Pass nếu sản phẩm hỗ trợ runtime 21 |
| JDK 17 | Release mặc định 17 | Java 17 | Baseline tùy chọn |
| JDK 21 | `--release 21` | Java 17 | Dự kiến fail do classfile 65 |
| JDK 21 | `--release 17`, gọi `List.getFirst()` | Chưa chạy | Compile fail có chủ đích |
| JDK 21 | `-source 17 -target 17`, gọi API21 | Java 17 | Có thể compile nhưng fail runtime |

Các tình huống thất bại có chủ đích là những **negative tests**, không phải dấu hiệu pipeline sản xuất nên chấp nhận lỗi.

## 30. CI pipeline tối thiểu

Một pipeline có thể chia:

~~~text
STAGE A — Verify toolchains
  - Build compiler thật là JDK 21
  - Runtime test thật là JDK 17

STAGE B — Build immutable artifact
  - Compile --release 17
  - Package
  - Save artifact SHA-256

STAGE C — Static checks
  - Inspect classfile target
  - Inspect dependency versions/minimum Java
  - Report suspicious classes and APIs

STAGE D — Minimum runtime test
  - Run artifact trên Java 17
  - Run smoke, contract, integration tests
  - Verify startup/shutdown and exit status

STAGE E — Additional runtime test
  - Run exact same artifact trên Java 21

STAGE F — Release decision
  - Save evidence and unresolved risks
  - Block release if mandatory Java 17 gate fails
~~~

Một Bash script nhỏ cho lab:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

mkdir -p build/classes

"$JAVA21_HOME/bin/javac" --release 17 \
  -encoding UTF-8 \
  -d build/classes \
  src/main/java/com/acme/compat/CompatDemo.java

"$JAVA21_HOME/bin/jar" --create \
  --file build/compat-demo.jar \
  --main-class com.acme.compat.CompatDemo \
  -C build/classes .

"$JAVA17_HOME/bin/java" \
  -jar build/compat-demo.jar Java
~~~

Đây là skeleton, chưa assert toàn bộ output hoặc chạy integration scenarios. Pipeline thật cần kiểm tra exit code, kỳ vọng dữ liệu và dependencies.

## 31. Dependency graph và minimum supported Java

Maven:

~~~bash
./mvnw dependency:tree
~~~

Gradle:

~~~bash
./gradlew dependencies
./gradlew dependencyInsight \
  --dependency example-library \
  --configuration runtimeClasspath
~~~

Các lệnh trên giúp biết resolved versions, nhưng không tự kết luận thư viện hỗ trợ Java 17.

Cần thêm:

- Vendor/framework support matrix.
- Minimum-Java requirement ghi trong documentation/release notes.
- Classfile inspection khi nghi có mismatch.
- Test các dynamic paths.
- Test packaged runtime classpath/module path.
- Native/JNI compatibility khi có.
- Agent/plugin compatibility với JDK tối thiểu.

Một thư viện compile target 21 không trở thành Java 17 compatible chỉ vì application dùng `--release 17`.

## 32. Bảng xử lý lỗi

| Triệu chứng | Nguyên nhân thường gặp | Cần kiểm tra |
|---|---|---|
| `release version 17 not supported` | Compiler sai/quá cũ | `javac -version` |
| `cannot find symbol: getFirst` với release 17 | Java 21 API bị chặn đúng | API target và source |
| `cannot find symbol: HexFormat` với release 11 | API chỉ có từ Java 17 | Minimum Java policy |
| `UnsupportedClassVersionError` | Bytecode lớn hơn JVM hỗ trợ | `javap` trên app/dependency |
| `NoSuchMethodError` | API không tồn tại ở runtime hoặc binary mismatch | Source/target/API/versions |
| `NoClassDefFoundError` | Runtime dependency thiếu hoặc init lỗi | Classpath và root cause |
| `ClassNotFoundException` | Dynamic class loading không thấy class | Loader/plugin/resource |
| `ServiceConfigurationError` | Provider SPI/ServiceLoader lỗi | Service descriptors/JPMS |
| `InaccessibleObjectException` | Reflection/module boundaries | Library version, opens |
| CI pass nhưng Java 17 fail | Tests chạy JDK 21 hoặc thiếu coverage | Test JVM thực tế |
| Container fail nhưng local pass | Image JDK/native/config khác | Dockerfile, launch flags |
| Main pass, batch job fail | Dependency chỉ load ở luồng hiếm | Integration coverage |

Không đọc exception một cách tách rời. Cần xác nhận JVM version, artifact checksum, runtime dependencies và bước kịch bản thực hiện khi lỗi xảy ra.

## 33. Bài tập mở rộng A: hạ minimum xuống Java 11

Dùng cùng `CompatDemo.java`, thử:

~~~bash
"$JAVA21_HOME/bin/javac" \
  --release 11 \
  -d build/release11 \
  src/main/java/com/acme/compat/CompatDemo.java
~~~

Kỳ vọng: fail vì `HexFormat` không có ở Java 11.

Yêu cầu:

1. Thay implementation encode bằng Java 11 APIs hoặc code thuần tương thích.
2. Giữ output hex `4a617661`.
3. Biên dịch `--release 11`.
4. Chạy bằng Java 11 thực nếu đó là target được yêu cầu.
5. Không tự đổi business behavior khi hạ platform API.

## 34. Bài tập mở rộng B: thử thư viện Java 21 với app Java 17

Tạo thư viện `Only21` như ví dụ, rồi một application gọi `Only21.answer()`. Compile application bằng JDK 21 với `--release 17`, nhưng để thư viện target21 trên compiler classpath.

Khi chạy trên Java17, xác định classfile nào thực sự gây lỗi và chứng minh library không được tự hạ target. Sau đó đề xuất một trong các phương án:

- Chọn bản library hỗ trợ Java 17.
- Thay API/library bằng implementation phù hợp.
- Nâng minimum runtime qua quy trình phê duyệt, thông báo breaking change.
- Tách component phụ thuộc Java 21 thành service khác khi kiến trúc cho phép.

Không giải quyết bằng cách xóa runtime test Java 17.

## 35. Bài tập mở rộng C: thêm gate vào CI

Thiết kế hai job:

**Build job** sử dụng JDK 21, compile `--release 17`, package một immutable artifact và publish checksum.

**Minimum-runtime job** sử dụng JDK 17, tải đúng artifact đó, xác nhận Java executable, chạy smoke/integration tests và lưu output.

Yêu cầu bổ sung: nếu JDK 17 không có sẵn hoặc test không thực thi được, kết quả phải là **BLOCKED/FAILED**, không phải PASS. Nếu chỉ có classfile check, ghi rõ `Runtime NOT EXECUTED`.

## 36. Bài tập mở rộng D: phân tích dynamic dependency

Chọn một plugin, JDBC driver hoặc framework extension của project đang làm và trả lời:

- Artifact/version nào thực sự được deploy?
- Nó có minimum JDK requirement gì?
- Nó được nạp khi startup hay khi gọi feature?
- `ServiceLoader`/reflection/module path có tham gia không?
- Có Java agent hoặc bytecode transformer nào?
- Test nào phải chạy trên JDK tối thiểu để buộc class đó được nạp?
- Có cách log class source và Java runtime khi lỗi không?

Bài tập này giúp mở rộng hiểu biết từ demo Java SE sang enterprise migration.

## 37. Bảng chứng cứ hoàn thành lab

Sau thực hành, một báo cáo có thể ghi:

~~~text
Project: compat-release-lab
Build JDK: 21 (vendor/update thực tế)
Compiler command: javac --release 17
Application classfile major: 61
Artifact: build/compat-demo.jar
Artifact SHA-256: <ghi từ công cụ checksum>
Minimum runtime: Java 17 (vendor/update)
Java 17 smoke result: SMOKE_OK
Java 21 API negative test: compile failed as expected
Java 21 bytecode on Java 17: failed as expected
Dependency scan: <kết quả thực tế>
Integration scenarios: <đã thử hoặc NOT TESTED>
Remaining risks: <ghi cụ thể>
~~~

Những ô trong dấu ngoặc nhọn cần được điền bằng dữ liệu đo **thực tế**. Bài học không tự nhận các lệnh trên đã được chạy trong môi trường của người học.

### 37.1. Vì sao nên lưu checksum?

Nếu job Build và job Runtime dùng hai artifact khác nhau dù tên file giống nhau, việc test pass không chứng minh artifact được phát hành đúng. Checksum/digest giúp gắn kết quả test với một binary cụ thể.

## 38. Checklist áp dụng cho dự án sản xuất

- [ ] Đã xác định JDK tối thiểu theo chính sách sản phẩm.
- [ ] Đã xác định JDK chạy Maven/Gradle và JDK compiler thật.
- [ ] Đã kiểm tra compiler hỗ trợ target `--release` được chọn.
- [ ] Đã đặt release target nhất quán trong Maven/Gradle.
- [ ] Đã kiểm tra major version của application classes.
- [ ] Đã tránh tham chiếu tĩnh đến Java SE API vượt minimum target.
- [ ] Đã kiểm tra third-party/runtime/transitive dependencies.
- [ ] Đã kiểm tra bytecode tooling, agents và plugins.
- [ ] Đã kiểm tra ServiceLoader/reflective/dynamic loading.
- [ ] Đã kiểm tra resources, classpath/module path và packaging.
- [ ] Đã chạy artifact cuối bằng runtime JDK tối thiểu.
- [ ] Đã chạy smoke và critical integration tests trên JVM tối thiểu.
- [ ] Đã kiểm tra database, TLS, serialization và external contracts.
- [ ] Đã kiểm tra JVM flags, environment và native libraries.
- [ ] Đã dùng cùng artifact khi test các Java runtime khác nhau.
- [ ] Đã lưu checksum, JDK vendor/update, dependency versions và test results.
- [ ] Đã đánh dấu chính xác những scenario chưa test.
- [ ] Đã chuẩn bị rollback artifact/runtime nếu regression xảy ra.

## 39. Những hiểu lầm dễ gặp

**“Build bằng JDK 21 thì artifact bắt buộc cần Java 21.”** Không nhất thiết: `--release 17` cho phép compiler tạo output target Java 17.

**“`-source 17 -target 17` đã chặn Java 21 APIs.”** Không đầy đủ. Đây là lý do cần `--release`.

**“Major version 61 nghĩa là mọi dependency đều chạy được trên Java 17.”** Không. Phải kiểm tra runtime libraries và dynamically loaded classes.

**“`--release 17` nghĩa là không cần cài Java 17 để test.”** Sai nếu sản phẩm cam kết support runtime Java 17.

**“Maven/Gradle chạy trên Java 21 nghĩa là test đã chạy Java 17.”** Không. Test JVM cần được chọn và xác minh riêng.

**“Compiler sẽ tự recompile third-party JAR xuống Java 17.”** Không.

**“Reflection cũng được kiểm tra như lời gọi method trực tiếp.”** Không. Tên class/method trong strings có thể chỉ được resolve khi runtime.

**“Chạy được main là đủ.”** Không, một API/plugin có thể chỉ được nạp khi người dùng gọi một feature cụ thể.

**“Một bản JAR chạy Java 21 chứng minh nó chạy Java 17.”** Không, dù application classfile target 17.

## 40. Kết luận

Trong Java Advance Compatibility Migration, **`--release` là công cụ compile-time để giới hạn ngôn ngữ, Java SE API và bytecode theo JDK mục tiêu**, mạnh hơn chỉ dùng `-source`/`-target` khi compiler chạy trên JDK mới.

Nhưng **minimum supported JDK** là một cam kết về hành vi chạy thực tế. Vì vậy, cần đóng gói artifact hoàn chỉnh, kiểm tra dependencies, rồi chạy chính artifact đó trên JVM thấp nhất được hỗ trợ, kèm smoke, integration, plugin và contract tests.

Quy trình khuyến nghị:

~~~text
Xác định JDK tối thiểu
         |
         v
Build bằng JDK mới + --release <minimum>
         |
         v
Package một artifact và lưu checksum
         |
         v
Kiểm tra classfile và dependencies
         |
         v
Chạy artifact đó trên minimum JDK thật
         |
         v
Smoke + integration + contract tests
         |
         v
Lưu bằng chứng, phát hành có rollback
~~~

**Biên dịch đúng target là bước đầu; chỉ khi artifact thật được chạy và kiểm chứng trên JDK tối thiểu thì cam kết tương thích mới có cơ sở.**
