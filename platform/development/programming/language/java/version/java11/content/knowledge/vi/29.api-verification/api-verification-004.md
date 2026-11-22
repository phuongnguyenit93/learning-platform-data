# Kiểm chứng API — Đóng gói tài nguyên, service provider và metadata cần thiết (Java 11)

## 1. Vì sao API biên dịch thành công vẫn có thể thất bại khi phát hành?

Một thư viện có thể vượt qua `javac` nhưng vẫn lỗi khi triển khai thành `.jar` hoặc custom runtime image: class công khai không được `exports` khỏi module; file `.properties`/template bị bỏ quên; `ServiceLoader` không tìm được provider; file `META-INF/services` bị ghi đè khi build fat JAR; hoặc metadata module/version khác với bản đã kiểm thử.

Vì vậy, **kiểm chứng API** phải kiểm cả **hợp đồng tĩnh** lẫn **bản phân phối thực tế**:

- **API contract:** tên module, exported packages, interface/class public, method signatures, exception/behavioral contract và dependency modules.
- **Service Provider Interface (SPI):** một interface được công bố, các implementation có thể thay thế, cơ chế đăng ký provider và cách `ServiceLoader` tìm provider.
- **Resources:** config mặc định, template, schema, resource bundle, text hoặc binary files mà runtime phải đọc từ artifact.
- **Metadata:** `module-info.class`, `META-INF/MANIFEST.MF`, service configuration files, phiên bản và các mục cần cho đóng gói/phân phối.
- **Runtime resolution:** những module/provider có mặt trong layer và custom runtime; khả năng đọc resource không bị sai path/encapsulation.
- **Integration smoke test:** consumer thực thi một API operation **từ đúng JAR đã phát hành**, không chỉ test class trên IDE classpath.

Bài này dùng **Java 11** và các công cụ **`javac`, `jar`, `java`, `jdeps`, `jlink`**. Các API JPMS và `ServiceLoader` vẫn được sử dụng trong JDK hiện đại; tránh hướng dẫn Applet/Java Web Start đã lỗi thời. `--release 11` xác nhận source/platform API của Java 11, nhưng **vẫn cần chạy trên runtime đích** nếu sản phẩm cam kết hỗ trợ một bản JDK/vendor cụ thể.

**Kết quả học tập:** tự xây và kiểm chứng ứng dụng có ba named modules, hai resource files, một service provider; nhận diện classpath vs module path; chạy ứng dụng từ JAR và từ image `jlink`; đưa các phép kiểm tra phù hợp vào CI.

## 2. Danh sách thành phần cần giữ khi đóng gói

| Thành phần | File/vị trí điển hình | Cần kiểm chứng | Triệu chứng nếu thiếu |
| --- | --- | --- | --- |
| API interface/class | `com/example/contract/FormatService.class` | Signature, modifier, package đúng | `ClassNotFoundException`, lỗi compile/link |
| Explicit module descriptor | `module-info.class` ở **gốc modular JAR** | `requires`, `exports`, `uses`, `provides` | Graph/module visibility không đúng |
| Module dependencies | `requires com.example.contract` | Có module phù hợp tại runtime | `Module not found` |
| Resource nội bộ | `META-INF/demo/prefix.txt` | Có đúng đường dẫn và nội dung | `getResourceAsStream` trả null |
| Metadata resource | `META-INF/demo/api.properties` | Version key và encoding | Thiếu metadata lúc khởi động |
| Provider declaration trên module path | `provides Service with Implementation` | Có trong `module-info.class` | `ServiceLoader` không thấy provider |
| Provider descriptor trên classpath | `META-INF/services/<service-FQCN>` | File UTF-8, class names đúng | Provider không được đăng ký |
| JAR manifest | `META-INF/MANIFEST.MF` | Main-Class/version/Automatic-Module-Name nếu dùng | Thiếu entry point hoặc metadata |
| Resource bundles/schema | `*.properties`, `*.json`/`*.xml` | Parser, charset, locale, path | Runtime chỉ lỗi ở một locale/feature |
| License/notice nếu cần | `LICENSE`, `NOTICE`, `META-INF/*` | Theo chính sách phân phối | Vi phạm điều kiện release |
| Tùy chọn native libraries | `.so`, `.dll`, `.dylib` | Đúng OS/ABI/arch | `UnsatisfiedLinkError` |

Không phải API nào cũng cần tất cả file. **Tránh thêm service descriptor hoặc metadata “cho đủ danh sách”** nếu thư viện không cung cấp SPI hoặc không phân phối theo mô hình đó. Mục tiêu là artifact chứa **đúng và đủ thứ runtime thực sự cần**.

Ba tầng kiểm chứng cần tách rời:

1. **Source tree** có file là chưa đủ.
2. **Compiled output** có `.class` là chưa đủ.
3. **Final JAR / linked image** phải có file và chạy đúng như consumer sẽ dùng.

Đặc biệt, `javac` không tự copy các resource `.properties`/`.txt` tùy ý. Build tool có thể copy từ `src/main/resources` hoặc `assets`, nhưng chỉ **mở JAR cuối và chạy thử** mới xác nhận chuỗi đóng gói hoàn chỉnh.

## 3. Kiểm chứng API theo JPMS: public không thay thế `exports`

Java Platform Module System (JPMS, Java 9+) bổ sung ranh giới module:

| Directive | Chức năng | Ví dụ |
| --- | --- | --- |
| `requires M` | Module này đọc M | `requires com.example.contract;` |
| `requires transitive M` | Phụ thuộc được lan truyền theo graph readability | Khi signature API phơi bày type từ M |
| `exports package` | Package trở thành API cho những module đọc module này | `exports com.example.contract;` |
| `exports package to M` | Chỉ export tới module được chỉ định | API bạn bè, không phải public chung |
| `opens package` | Cho phép deep reflection/resource lookup theo JPMS | Framework cần reflective access |
| `uses Service` | Module có code gọi `ServiceLoader` cho service | `uses com.example.contract.FormatService;` |
| `provides Service with Impl` | Module đăng ký implementation của service | `provides FormatService with PrefixFormatter;` |

Một interface dù mang `public` vẫn có thể **không truy cập được từ module khác** nếu package chứa nó không `exports`. Ngược lại, `opens` không phải cách thay thế `exports` khi consumer cần compile code gọi interface bình thường.

**Phân biệt ABI với module visibility:** consumer có thể không đọc được một class do thiếu `exports` dù method signatures hoàn toàn đúng. Khi bỏ `exports`, bạn thay **hợp đồng public API**, không chỉ thay cấu hình runtime.

**Phân biệt service consumer/provider:** consumer nên `requires` module chứa **service interface**, đồng thời `uses` interface. Nó **không cần phụ thuộc tĩnh vào module implementation** nếu mục tiêu là plugin có thể thay. Provider module mới `provides` implementation. Một provider có thể tồn tại trên disk mà **chưa được resolve vào module graph**, do đó cũng cần kiểm tra cách chạy/link image.

## 4. Bài thực hành: API contract, provider và consumer

Xây ứng dụng có ba module:

```text
com.example.contract
  exports com.example.contract
  public interface FormatService
          ^
          |
com.example.impl
  requires com.example.contract
  provides FormatService with PrefixFormatter
  file META-INF/demo/prefix.txt
          ^
          |
com.example.app
  requires com.example.contract
  uses FormatService
  file META-INF/demo/api.properties
```

Service được gọi `FormatService.format(String)`. Provider đọc prefix **trong JAR của chính nó**; app đọc version metadata **trong app JAR**. Thành công khi cả bốn dòng output của app xuất hiện chính xác, nghĩa là API visibility, SPI discovery, resource packaging và runtime execution đều hoạt động.

Cấu trúc file:

```text
project/
├── src/
│   ├── com.example.contract/
│   │   ├── module-info.java
│   │   └── com/example/contract/FormatService.java
│   ├── com.example.impl/
│   │   ├── module-info.java
│   │   └── com/example/impl/PrefixFormatter.java
│   └── com.example.app/
│       ├── module-info.java
│       └── com/example/app/App.java
├── assets/
│   ├── impl/META-INF/demo/prefix.txt
│   └── app/META-INF/demo/api.properties
├── mods/      (được tạo khi biên dịch)
└── mlib/      (chứa JAR sau đóng gói)
```

### 4.1. Module contract

**`src/com.example.contract/module-info.java`**

```java
module com.example.contract {
    exports com.example.contract;
}
```

**`src/com.example.contract/com/example/contract/FormatService.java`**

```java
package com.example.contract;

public interface FormatService {
    String format(String value);
}
```

Chỉ export **API package**. Một phương thức thêm/thay kiểu tham số có thể gây source/binary incompatibility cho consumer; module descriptor và Java API signature đều cần được kiểm tra khi nâng phiên bản.

### 4.2. Module provider

**`src/com.example.impl/module-info.java`**

```java
module com.example.impl {
    requires com.example.contract;

    provides com.example.contract.FormatService
            with com.example.impl.PrefixFormatter;
}
```

**`src/com.example.impl/com/example/impl/PrefixFormatter.java`**

```java
package com.example.impl;

import com.example.contract.FormatService;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;

public final class PrefixFormatter implements FormatService {
    public PrefixFormatter() {}

    @Override
    public String format(String value) {
        try (InputStream in = PrefixFormatter.class.getResourceAsStream(
                "/META-INF/demo/prefix.txt")) {
            if (in == null) {
                throw new IllegalStateException("prefix resource missing");
            }

            String prefix = new String(
                    in.readAllBytes(), StandardCharsets.UTF_8).trim();
            return prefix + " " + value;
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }
}
```

**`assets/impl/META-INF/demo/prefix.txt`**

```text
Hello,
```

Bốn điểm cần kiểm tra:

1. `PrefixFormatter` là class public, implement `FormatService` và có **public no-arg constructor**, thuận tiện cho `ServiceLoader`.
2. Descriptor `provides ... with ...` trỏ đúng tên class. **Không bắt buộc export implementation package `com.example.impl`** chỉ để `ServiceLoader` trong một named module tìm provider.
3. Prefix được đọc qua `getResourceAsStream`, không phải `Files.readString("src/...")`. Trong production, thư mục `src` thường không tồn tại.
4. Resource đặt trong `META-INF/demo`, không phải package Java bị JPMS encapsulation. Đây là lựa chọn có chủ đích cho bài test, **không** phải nơi chứa secrets.

### 4.3. Consumer module

**`src/com.example.app/module-info.java`**

```java
module com.example.app {
    requires com.example.contract;
    uses com.example.contract.FormatService;
}
```

**`src/com.example.app/com/example/app/App.java`**

```java
package com.example.app;

import com.example.contract.FormatService;
import java.io.InputStream;
import java.util.Iterator;
import java.util.Properties;
import java.util.ServiceLoader;

public final class App {
    public static void main(String[] args) throws Exception {
        Properties p = new Properties();
        try (InputStream in = App.class.getResourceAsStream(
                "/META-INF/demo/api.properties")) {
            if (in == null) {
                throw new IllegalStateException("api metadata missing");
            }
            p.load(in);
        }

        String version = p.getProperty("api.version");
        if (!"1.0".equals(version)) {
            throw new IllegalStateException("bad API metadata");
        }
        System.out.println("api.version=" + version);

        Iterator<FormatService> it =
                ServiceLoader.load(FormatService.class).iterator();
        if (!it.hasNext()) {
            throw new IllegalStateException("provider not resolved");
        }

        FormatService service = it.next();
        if (it.hasNext()) {
            throw new IllegalStateException(
                    "expected exactly one provider");
        }

        System.out.println("provider=" + service.getClass().getName());
        System.out.println("message=" + service.format("Java 11"));
        System.out.println("verified=true");
    }
}
```

**`assets/app/META-INF/demo/api.properties`**

```properties
api.version=1.0
```

**Quan sát về consumer:**

- `requires com.example.contract` bảo đảm mã consumer sử dụng được API type.
- `uses com.example.contract.FormatService` công bố nhu cầu dùng SPI theo JPMS.
- `ServiceLoader.load(...)` phát hiện providers lazily. Lỗi provider có thể xuất hiện khi duyệt `hasNext()/next()`, không chỉ lúc `load()`.
- Demo chủ động yêu cầu **đúng một provider** để kết quả xác định. Hệ plugin thật có thể có nhiều providers; thứ tự khám phá không được coi là hợp đồng ổn định.
- `Properties.load(InputStream)` ở đây đọc ASCII. Với giá trị Unicode, hãy kiểm tra định dạng Java properties và chọn `Reader`/UTF-8 hay escapes phù hợp.
- Có assertion lỗi rõ cho thiếu metadata, provider chưa resolve và lỗi tài nguyên provider. Một test chỉ thấy provider class có mặt nhưng không gọi `format(...)` sẽ bỏ sót lỗi thiếu resource.

## 5. Biên dịch mã Java với `--release 11`

Đặt terminal ở thư mục `project`. Trên POSIX shell:

```bash
mkdir -p mods mlib

javac --release 11 \
  --module-source-path src \
  -d mods \
  -m com.example.contract,com.example.impl,com.example.app
```

Trong Windows PowerShell, sau khi tạo hai thư mục `mods` và `mlib`, lệnh `javac` cũng có thể viết một dòng:

```powershell
javac --release 11 --module-source-path src -d mods -m com.example.contract,com.example.impl,com.example.app
```

Các thành phần:

- `--release 11` yêu cầu compiler dùng public platform API của Java 11 và sinh classfile target 11.
- `--module-source-path src` dùng thư mục con theo **tên module** như `src/com.example.impl`.
- `-d mods` lưu classes thành `mods/com.example.*`.
- `-m` liệt kê module cần compile.

**Cảnh báo:** compile thành công mới chứng minh `.java` và `module-info.java` hợp lệ. `javac` **không tự copy** `assets/.../prefix.txt` hay `api.properties` vào output. Bước packaging phải ghi rõ tài nguyên nào cần đi cùng artifact.

**Một build tốt cần điều kiện sạch:** tránh `mods` cũ chứa class bị xóa khỏi source nhưng vẫn sót từ lần compile trước. Trong CI, tạo thư mục build mới cho mỗi job hoặc clean đúng thư mục build đích; không xóa tùy tiện filesystem khác.

## 6. Tạo modular JAR chứa cả classes và resources

Tạo ba JAR (POSIX shell):

```bash
jar --create --file mlib/com.example.contract.jar \
  -C mods/com.example.contract .

jar --create --file mlib/com.example.impl.jar \
  -C mods/com.example.impl . \
  -C assets/impl META-INF/demo/prefix.txt

jar --create --file mlib/com.example.app.jar \
  -C mods/com.example.app . \
  -C assets/app META-INF/demo/api.properties
```

Trên PowerShell, dùng cú pháp **mỗi lệnh một dòng**, không sao chép dấu `\` nối dòng của POSIX:

```powershell
jar --create --file mlib/com.example.contract.jar -C mods/com.example.contract .
jar --create --file mlib/com.example.impl.jar -C mods/com.example.impl . -C assets/impl META-INF/demo/prefix.txt
jar --create --file mlib/com.example.app.jar -C mods/com.example.app . -C assets/app META-INF/demo/api.properties
```

**`-C DIR entry`** đổi directory gốc của những entry được thêm. Trong provider JAR, resource path cuối cùng phải là **`META-INF/demo/prefix.txt`**, không phải `assets/impl/META-INF/demo/prefix.txt`. Tương tự, `module-info.class` phải xuất hiện ở gốc JAR, không nằm trong `mods/com.example.impl/module-info.class` bên trong artifact.

Vì các source modules được compile bằng javac, JAR chứa `module-info.class` sẽ trở thành **explicit modular JAR**. Đây là cơ chế Java 9+ còn dùng trên Java 11/17/21+.

### 6.1. Kiểm tra nội dung của chính JAR

```bash
jar --list --file mlib/com.example.contract.jar
jar --list --file mlib/com.example.impl.jar
jar --list --file mlib/com.example.app.jar
```

Các entry cần hiện diện:

| Artifact | Các entry quan trọng |
| --- | --- |
| `com.example.contract.jar` | `module-info.class` và `com/example/contract/FormatService.class` |
| `com.example.impl.jar` | `module-info.class`, `com/example/impl/PrefixFormatter.class` và `META-INF/demo/prefix.txt` |
| `com.example.app.jar` | `module-info.class`, `com/example/app/App.class` và `META-INF/demo/api.properties` |

`jar` thường thêm `META-INF/MANIFEST.MF`. Việc có manifest không bù được việc thiếu provider declaration trong module descriptor, và manifest **không tự nạp resource file**.

Đừng assert byte-for-byte thứ tự ZIP entries: thứ tự có thể khác theo tool/build. Đúng hơn là kiểm tra **file có, đúng path, kích thước/nội dung/encoding phù hợp**, và không xuất hiện secrets. Một resource entry tồn tại nhưng chứa giá trị sai cũng vẫn gây lỗi runtime.

### 6.2. Vì sao phải có smoke test sau packaging?

Một JAR có thể chứa resource nhưng code gọi sai path; một provider module có class nhưng không có `provides`; hoặc implementation ném lỗi trong constructor. `jar --list` không thể chứng minh điều ấy. Bài test phải đi đến **`service.format("Java 11")`** và kiểm giá trị trả về.

Đây là lý do unit test trực tiếp `new PrefixFormatter()` chưa đủ: nó **bỏ qua ServiceLoader discovery và module resolution**. Tương tự, chạy từ IDE có thêm source resource folders có thể tạo cảm giác đúng, trong khi release JAR bị mất file.

## 7. Kiểm tra module descriptor và API exports

Dùng `jar --describe-module`:

```bash
jar --describe-module --file mlib/com.example.contract.jar
jar --describe-module --file mlib/com.example.impl.jar
jar --describe-module --file mlib/com.example.app.jar
```

Với provider module, các dòng quan trọng tương tự:

```text
requires com.example.contract
requires java.base mandated
provides com.example.contract.FormatService with com.example.impl.PrefixFormatter
contains com.example.impl
```

Tool có thể in thêm file URL, module version hoặc các field khác. **Không nên hardcode một đường dẫn tuyệt đối của máy build** vào assertion.

Các câu hỏi code review:

1. Contract module thực sự **`exports com.example.contract`**?
2. Provider module **`requires` contract** và **`provides` service** với class implementation đúng?
3. App module **`requires` contract** và **`uses` service**?
4. Có export nhầm package implementation không?
5. Có hai module định nghĩa cùng package hoặc một dependency không mong muốn không?
6. Có module name không ổn định do JAR được đóng gói thành **automatic module** thay vì explicit module không?

**Module metadata là một phần API contract.** Thay đổi từ `exports com.example.contract` sang bỏ export khiến consumer bị lỗi, dù không đổi một byte source của `FormatService`.

### 7.1. Nhãn version module không bảo đảm semantic compatibility

Có thể đặt module version khi tạo JAR:

```bash
jar --create --file mlib/com.example.contract.jar \
  --module-version 1.0 \
  -C mods/com.example.contract .
```

Đây là **lựa chọn thay thế** lệnh tạo contract JAR trước đó, không phải bước bắt buộc phải chạy lại trên cùng file. `--module-version 1.0` ghi module version metadata, **không** tự động bảo đảm API/ABI tương thích, cũng không thay một Maven/Gradle dependency resolver.

Nếu `FormatService.format(String)` bị đổi thành `format(Object)`, consumer cũ có thể gặp lỗi biên dịch/link dù metadata vẫn ghi `1.0`. Cần test API diff/binary compatibility và chạy consumer cũ với artifact mới.

### 7.2. Manifest khác module descriptor

`META-INF/MANIFEST.MF` có thể chứa `Main-Class`, `Implementation-Version`, `Automatic-Module-Name`, `Multi-Release` và thông tin khác tùy build.

- `Main-Class` phù hợp với executable JAR chạy `java -jar`. Demo đang chạy bằng `java -m module/main`, nên không cần `Main-Class`.
- `Implementation-Version` hỗ trợ truy vết release, không phải enforcement của JPMS.
- `Automatic-Module-Name` đặt tên ổn định cho JAR **chưa có `module-info.class`** khi dùng như automatic module. Nó không override tên explicit module.
- `Multi-Release: true` chỉ phù hợp nếu thật sự đóng gói multi-release JAR, có `META-INF/versions/N` đúng cấu trúc. Không thêm chỉ để “có metadata”.
- Metadata không được chứa password, token, connection string hoặc đường dẫn nội bộ nhạy cảm.

## 8. Chạy ứng dụng từ JAR thật và xác minh provider

Sau khi tạo ba JAR:

```bash
java --module-path mlib \
  --add-modules com.example.impl \
  --module com.example.app/com.example.app.App
```

Trên PowerShell:

```powershell
java --module-path mlib --add-modules com.example.impl --module com.example.app/com.example.app.App
```

**Output xác định với artifact đầy đủ:**

```text
api.version=1.0
provider=com.example.impl.PrefixFormatter
message=Hello, Java 11
verified=true
```

Đã kiểm chứng thực tế bằng `javac --release 11` và chạy bộ ba modular JAR trên OpenJDK hiện đại. Các giá trị ổn định vì demo yêu cầu chính xác một provider, resource cố định và không in timestamp/temporary path.

**Tại sao `--add-modules com.example.impl`?** Nó bảo đảm module provider được **resolve vào graph**, thay vì chỉ nằm trong một thư mục trên disk. Với JPMS, file JAR nằm trên module path không nhất thiết đã thuộc một module layer được dùng. Dùng explicit provider root cho bài test làm kết quả dễ hiểu và tái hiện.

Nếu thiếu provider, app báo **`provider not resolved`**. Nếu provider được tìm thấy nhưng resource của nó bị bỏ sót, app báo **`prefix resource missing`**. Hai thông báo thuộc **hai tầng vấn đề khác nhau**; không nên chữa cả hai bằng cách thêm một classpath tùy ý.

### 8.1. Khi có nhiều providers

`ServiceLoader` có thể trả nhiều implementation; thứ tự phát hiện providers **không phải một priority contract toàn cục**. Ứng dụng thật nên có lựa chọn dựa trên ID, capability, priority do policy định nghĩa, hoặc phát hiện ambiguity. Code demo yêu cầu đúng một provider **chỉ vì scope bài test**; với plugin ecosystem không được mặc định lấy implementation đầu tiên là “đúng”.

### 8.2. ServiceConfigurationError không giống không có provider

Khi provider descriptor sai, class không load được, constructor thiếu hoặc ném exception, `ServiceLoader` có thể ném `ServiceConfigurationError` trong lúc duyệt. Không nên chỉ đếm 0 và ghi “không có implementation”. Hãy ghi đủ cause/phase trong log **không lộ thông tin nhạy cảm**, rồi fail-fast khi provider là dependency bắt buộc.

## 9. Phân biệt service registration trên module path và classpath

Một điểm nền tảng trong Java 11: **explicit named modules** và **classpath/unnamed module** dùng các cách đăng ký provider khác nhau.

### 9.1. Named module: `uses`/`provides`

Trong demo:

```java
// Trong module-info.java của consumer:
uses com.example.contract.FormatService;

// Trong module-info.java của provider:
provides com.example.contract.FormatService
        with com.example.impl.PrefixFormatter;
```

Đây là **trích đoạn directive**, chỉ hợp lệ bên trong `module-info.java`. Với named modules, không bắt buộc thêm file `META-INF/services` để `ServiceLoader` thấy implementation đã được khai báo bằng `provides`. Provider package không cần `exports` chỉ cho mục đích service registration.

### 9.2. Classpath: `META-INF/services/<FQCN>`

Khi triển khai provider như một JAR trên **classpath**, nó nằm trong unnamed module và phải được khai báo theo service configuration file:

```text
META-INF/services/com.example.contract.FormatService
```

Nội dung file — từng provider FQCN một dòng:

```text
com.example.impl.PrefixFormatter
```

Quy tắc của `ServiceLoader` trên Java 11:

- Filename là **fully qualified binary name của service interface**, đúng chữ hoa/thường.
- File được mã hóa **UTF-8**.
- Có thể có comment với `#` và dòng trống; mỗi tên provider phải hợp lệ.
- Implementation phải là class load được và có cách khởi tạo hợp lệ. Đối với classpath provider truyền thống, public no-arg constructor là yêu cầu phù hợp.
- Với nhiều dependencies chứa service descriptor, fat/shaded JAR phải **merge entries**, không ghi đè một descriptor lên descriptor khác.
- Không nhét các tên class không có thật; failure xảy ra **khi ServiceLoader duyệt provider**.
- Không dùng **class name đơn** hay module name làm filename; FQCN của interface mới đúng.

**Khi cần cả hai deployment modes**, có thể phân phối một JAR có explicit `module-info.class` và service descriptor classpath tương ứng, nhưng phải **test cả module path lẫn classpath**. Trong named module, provider đã công bố bằng `provides`; service descriptor của unnamed module không thay thế directive đó. Tránh duplicate registrations và xác nhận count theo deployment policy.

### 9.3. So sánh nhanh

| Môi trường | Đăng ký provider | Consumer cần | Test quan trọng |
| --- | --- | --- | --- |
| Explicit named modules | `module-info: provides ... with ...` | `requires` + `uses` | Provider module resolved |
| Classpath/unnamed modules | `META-INF/services/<service-FQCN>` | API interface visible trên classpath | Descriptor UTF-8, classload/no-arg ctor |
| Mixed deployment | Mỗi phần theo cơ chế của nó | Classloader/layer phù hợp | Không mất hoặc duplicate providers |
| Custom `jlink` image | Named module providers trong image | Đầy đủ graph | Chạy `image/bin/java` |
| Plugin-defined `ModuleLayer` | Named modules/services của layer | ServiceLoader dùng đúng layer | Khám phá và khởi tạo provider thật |

**Không đánh đồng** “implementation implements interface” với “provider được `ServiceLoader` phát hiện”. `ServiceLoader` không tự quét mọi `.class` để suy ra providers.

## 10. Resource lookup và JPMS encapsulation

### 10.1. Absolute vs relative resource path

Code đã chạy:

```java
try (InputStream in = PrefixFormatter.class.getResourceAsStream(
        "/META-INF/demo/prefix.txt")) {
    if (in == null) {
        throw new IllegalStateException("prefix resource missing");
    }
    // Đọc resource trong module của PrefixFormatter.
}
```

- Dấu `/` đầu string là **absolute resource name**.
- Không có `/` đầu, `Class.getResourceAsStream` diễn giải tên **tương đối theo package của class**.
- Có resource trên filesystem trong lúc build không đảm bảo resource ở đúng đường dẫn trong JAR.
- Không nên đọc file đóng gói bằng `Paths.get("src/...")`; source tree thường không có trên server hay trong `jlink` image.
- Đóng `InputStream` với try-with-resources. Với text UTF-8, dùng `StandardCharsets.UTF_8`.

### 10.2. Resource encapsulation trong named module

Với JPMS, non-`.class` resource có thể được **encapsulate** nếu nằm trong một package của module chưa `opens` cho module truy cập. Vì vậy:

- `Class.getResourceAsStream`, `Module.getResourceAsStream` và `ClassLoader.getResourceAsStream` có thể có rule truy cập khác nhau tùy caller/module.
- Không suy từ việc `jar --list` thấy `com/example/impl/config.properties` rằng một module bất kỳ đều đọc được file đó.
- Nếu resource là **private implementation detail**, hãy để module sở hữu nó đọc nội bộ bằng class/module API thích hợp.
- Nếu resource là **public API resource**, thiết kế path/access policy rõ ràng, xem xét `opens` khi thật sự cần, và test từ consumer module.
- Resource trong `META-INF/demo` không thuộc một Java package của module nên đơn giản hóa demo, nhưng **không làm dữ liệu bên trong được bảo mật**.

**Không thêm `opens ...` hàng loạt chỉ để chữa resource lookup**. Nó mở rộng surface reflective access. Hãy phân tích path, caller, ownership và nhu cầu trước.

### 10.3. Properties và encoding

Trong demo, `api.version=1.0` là ASCII, nên `Properties.load(InputStream)` đọc chính xác. Nếu resource là text UTF-8 có tiếng Việt và không dùng cách escape truyền thống, có thể sử dụng `Reader` phù hợp:

```java
try (java.io.Reader reader = new java.io.InputStreamReader(
        in, java.nio.charset.StandardCharsets.UTF_8)) {
    properties.load(reader);
}
```

Đây là **trích đoạn**, cần biến `InputStream in` và `Properties properties` còn hợp lệ. Không giả định hai overload `Properties.load(InputStream)` và `load(Reader)` có semantics encoding giống hệt nhau.

### 10.4. Resource path cũng có thể là một phần API contract

Nếu plugin hoặc consumer bên ngoài được **công bố** là có thể đọc `/META-INF/demo/schema.json`, thay path đó có thể là breaking change ở runtime dù mọi Java method signature giữ nguyên. Mặt khác, resource chỉ dùng bên trong provider là implementation detail, **không bắt buộc hứa giữ path mãi mãi** cho bên ngoài.

Một bản API spec nên nêu rõ những thứ nào được hỗ trợ công khai: Java types, SPI names, resource names, metadata keys, supported versions và error behavior.

## 11. Kiểm chứng với `jdeps`, `javap` và module validation

### 11.1. `jdeps` cho static dependencies

```bash
jdeps --module-path mlib --check com.example.app
```

Công cụ phân tích module/class dependencies. Trong ví dụ, app yêu cầu `com.example.contract` và `java.base`. Output có thể gồm “Module descriptor”, “Suggested module descriptor”, “Transitive reduced graph”; **không assert toàn bộ text** vì cách trình bày thay đổi theo JDK.

**`jdeps` không xác minh:**

- File `prefix.txt` hoặc `api.properties` tồn tại.
- Provider constructor chạy được.
- `ServiceLoader` tìm thấy implementation runtime.
- Reflection hoặc class names sinh động từ `String`.
- Mọi tương thích API/ABI giữa hai bản release.

Đó là lý do nó phải đi cùng **artifact inspection + runtime smoke test**.

### 11.2. `javap` để nhìn public method signature

```bash
javap --module-path mlib \
  --module com.example.contract \
  -public com.example.contract.FormatService
```

Bạn cần thấy interface với method `String format(String)`. Tuy nhiên, một lần in `javap` **chưa so với bản API cũ**, nên không thể tự tuyên bố binary compatibility. Với thư viện phát hành cho bên ngoài, dùng baseline API/ABI diff, compile consumer cũ khi phù hợp và chạy integration tests.

### 11.3. Validate module graph

```bash
java --module-path mlib --validate-modules
```

Giúp nhận diện một số module metadata/conflict problems, nhưng **không thử load resource** hay gọi API method. Một module graph “hợp lệ” có thể vẫn thiếu provider/module đã bị loại do root selection; cần phép thử hoạt động thật.

## 12. Đóng gói custom runtime bằng `jlink`

`jlink` cho phép tạo runtime image gồm những named modules được chọn và phụ thuộc transitively. Với ba JAR đã đóng gói:

```bash
jlink --module-path mlib \
  --add-modules com.example.app,com.example.impl \
  --output image
```

Chạy **Java trong image** chứ không dùng JDK hệ thống:

```bash
./image/bin/java -m com.example.app/com.example.app.App
```

Trên Windows:

```powershell
.\image\bin\java.exe -m com.example.app/com.example.app.App
```

**Output phải giống lần chạy module path:**

```text
api.version=1.0
provider=com.example.impl.PrefixFormatter
message=Hello, Java 11
verified=true
```

Đã kiểm chứng toàn bộ bước `jlink` và chạy ứng dụng từ image thực tế với mã target Java 11 trên OpenJDK mới. **Việc chạy trong image là một check riêng**, vì image có thể bỏ một module, resource hoặc runtime facility mà full JDK của developer vốn có.

### 12.1. `--bind-services` có cần không?

Java 11 `jlink --bind-services` liên kết các **service provider modules** và dependencies theo service binding:

```bash
jlink --module-path mlib \
  --add-modules com.example.app \
  --bind-services \
  --output image-with-services
```

Đây là **biến thể để kiểm tra**, không phải bắt buộc dùng cho demo. Nó có thể kéo vào nhiều JDK provider modules hơn dự kiến, làm image lớn. Với ứng dụng muốn đúng một provider, cách `--add-modules com.example.app,com.example.impl` như demo thể hiện lựa chọn rõ ràng.

Khi dùng `--bind-services`, hãy đo image size, liệt kê modules và thử đúng provider count. Đừng kết luận provider đã có trong image chỉ vì module JAR nằm trên build machine.

### 12.2. Các bước QA image

- Chạy `image/bin/java --list-modules` để thấy contract, app, impl và required JDK modules.
- Chạy `image/bin/java -m ...` xác minh output và resource.
- Kiểm tra image được dựng bằng **đúng JDK vendor/version/architecture** muốn triển khai.
- Không giả định image tối giản có `javac`, `jar`, `jdeps` — chúng có thể không được link vào.
- Rebuild và redeploy image khi có **JDK security updates**; cập nhật full JDK trên host không tự cập nhật image đã được đóng gói cũ.

## 13. Metadata khác cần cân nhắc ở thư viện thực tế

### 13.1. `Automatic-Module-Name`

Một JAR **không có `module-info.class`** có thể trở thành automatic module khi đưa lên module path. Khi cần tên module ổn định trước khi chuyển sang explicit JPMS, manifest `Automatic-Module-Name` có thể hữu ích. Nhưng:

- Nó **không** thay thế `requires`/`exports`/`uses`/`provides` được thiết kế trong explicit module.
- Khi đã có `module-info.class`, tên module được khai báo trong descriptor.
- Automatic modules có behavior rộng hơn về đọc/export packages; không tự đánh đồng với explicit module trong API review.
- Khi migrate, cần test consumer/provider với module name và graph mới.

### 13.2. Multi-release JAR và `META-INF/versions`

Multi-release JAR cho phép triển khai class/resource theo Java version khi cần. Nếu dùng:

- Có manifest `Multi-Release: true` và entries trong `META-INF/versions/N`.
- Root classes phải chạy với Java baseline đã công bố.
- Version-specific classes và module metadata phải được kiểm tra với từng runtime mục tiêu.
- Không thêm variant `/11` chỉ vì khóa học nhắm Java 11; demo chung đã đủ.
- Dùng `jar --describe-module`/`jdeps` với lựa chọn version cần thiết và test cả Java 11 lẫn các JDK về sau.

### 13.3. Traceability và supply chain

Metadata về version, artifact checksum, build commit, license/notice, SBOM hoặc provenance có thể bắt buộc tùy tổ chức. Đó là **quy trình release**, không phải yêu cầu tự động của `ServiceLoader`.

Luôn kiểm tra artifact được **tải về từ repository phát hành**, không chỉ thư mục build local. Giữ nguồn gốc và phiên bản dependencies rõ để có thể tái tạo bản đang chạy và phát hành bản vá khi cần. Không lưu private key, token hay credential trong JAR chỉ để tiện deployment.

## 14. Những lỗi phổ biến và cách tìm nguyên nhân

| Triệu chứng | Nguyên nhân có thể | Kiểm tra/khắc phục |
| --- | --- | --- |
| `package ... is not visible` | Thiếu `exports` hoặc `requires` | So `module-info.java`/`jar --describe-module` |
| `Module com.example.impl not found` | Provider JAR không có trên module path/image | Kiểm tra mlib, roots, tên module |
| `provider not resolved` | Thiếu `provides` hoặc provider chưa resolve | `module-info.class`, `--add-modules`, `ServiceLoader` |
| `ServiceConfigurationError` | Descriptor/class/constructor sai hoặc provider init fail | Xem cause và SPI declaration |
| `prefix resource missing` | Resource bị bỏ hoặc sai path trong provider JAR | `jar --list` + `getResourceAsStream` |
| `api metadata missing` | App JAR thiếu properties | Kiểm tra file bên trong app artifact |
| `NoSuchMethodError` | Runtime binary API khác bản compile | API diff, dependency graph, consumer test |
| `ClassNotFoundException` | Class/JAR thiếu hoặc classloader sai | Kiểm artifact và classpath/module path |
| `InaccessibleObjectException` | Deep reflection bị JPMS giới hạn | Xem `opens`/framework contract, tránh mở tràn |
| Multiple providers | Service descriptors bị duplicate hoặc nhiều modules | Áp chính sách chọn provider rõ |
| IDE chạy, JAR lỗi | IDE có `src`/test resources trên path | Chạy artifact trong build sạch |
| Fat JAR chỉ còn một SPI | `META-INF/services/*` bị overwrite | Cấu hình merge descriptors |
| `jlink` chạy lỗi provider | Image không chứa provider hoặc resource | `--add-modules`/`--bind-services` và smoke test |
| `jar -tf` thấy file nhưng code không thấy | Sai resource name/caller/module encapsulation | Xem `Class.getResourceAsStream` rules |
| Run `java -jar` khác `java -m` | Khác entry point/module graph | Định nghĩa đúng deployment mode |
| Resource bundle sai locale/encoding | File không được copy hoặc parser/charset khác | Test từng locale bằng artifact thật |

### Đừng chữa mọi lỗi bằng `--add-opens`

`--add-opens` có thể giải quyết một số deep-reflection restrictions nhưng **không** tạo ra resource bị thiếu, không tự sửa provider declaration và có thể mở rộng access surface. Với lỗi thiếu `prefix.txt`, phải sửa **packaging path**; với lỗi thiếu provider, phải sửa **service/module graph**.

### Một provider đã tìm thấy vẫn có thể lỗi khi chạy

`ServiceLoader` trả được `PrefixFormatter` mới chỉ xác minh một phần. Nếu provider thực hiện `format(...)` và file `prefix.txt` không có, lỗi vẫn phát sinh. Vì vậy smoke test phải **thực thi operation thật với fixture an toàn**, chứ không dừng ở việc đếm providers.

## 15. Đưa vào CI/CD: kiểm tĩnh rồi kiểm động

Một pipeline kiểm chứng API artifact nên có các cổng:

| Gate | Kiểm tra | Không thay thế cho |
| --- | --- | --- |
| Compile | `javac --release 11`, modules compile | Resource packaging |
| JAR inventory | `jar --list`, assert file paths | Load/parse resource |
| Module metadata | `jar --describe-module` | Provider runtime instantiation |
| Static dependencies | `jdeps --check`, `--validate-modules` | Reflection/service/resource checks |
| API compatibility | Public API snapshot/diff và consumer tests | Module graph nếu không test riêng |
| Service discovery | `ServiceLoader` tìm đúng providers | Provider operation/resource correctness |
| Resource smoke | Provider/app mở file từ JAR, validate nội dung | Data/security review |
| Custom runtime | `jlink` + chạy `image/bin/java` | Update policy cho image |
| Release security | Credential scanning, license/SBOM, checksums | Semantic compatibility |

Quy trình thực hành POSIX:

```bash
# Giả định files src/ và assets/ đã tạo theo mục 4.
mkdir -p mods mlib

# API contract + provider + consumer compile.
javac --release 11 --module-source-path src -d mods \
  -m com.example.contract,com.example.impl,com.example.app

# Đóng gói theo mục 6, bao gồm resource files.
jar --create --file mlib/com.example.contract.jar \
  -C mods/com.example.contract .
jar --create --file mlib/com.example.impl.jar \
  -C mods/com.example.impl . -C assets/impl META-INF/demo/prefix.txt
jar --create --file mlib/com.example.app.jar \
  -C mods/com.example.app . -C assets/app META-INF/demo/api.properties

# Static metadata/dependency checks.
jar --list --file mlib/com.example.impl.jar
jar --describe-module --file mlib/com.example.impl.jar
jdeps --module-path mlib --check com.example.app

# Chạy consumer từ release JARs.
java --module-path mlib --add-modules com.example.impl \
  -m com.example.app/com.example.app.App

# Kiểm chứng provider/resources cả sau jlink.
jlink --module-path mlib \
  --add-modules com.example.app,com.example.impl --output image
./image/bin/java -m com.example.app/com.example.app.App
```

Đây là **trình tự test minh họa**, chưa phải pipeline CI hoàn chỉnh: trong CI phải tạo thư mục build **sạch**, kiểm exit codes, assert presence/contents, kiểm stdout và không tái sử dụng output `image` đã tồn tại (jlink thường từ chối output path có sẵn).

### 15.1. Maven/Gradle có thay đổi nguyên tắc không?

Không. Dù Maven/Gradle tự copy `src/main/resources`, bài QA vẫn phải kiểm **artifact sau shading/minimization**:

- Các provider class có thể bị optimizer xem là “không dùng” vì được load động bằng `ServiceLoader`.
- Service descriptor ở fat JAR cần **merge**; nếu bị overwrite, một provider biến mất.
- Resource filters có thể sửa encoding, path hoặc giá trị metadata.
- Test compile/module graph không đồng nghĩa artifact cuối hoạt động trong custom image.
- Nếu deploy theo classpath và JPMS cả hai, phải có hai đường integration test tương ứng.

### 15.2. API compatibility cần nhìn cả consumer cũ

Giả sử bản thư viện cũ export `FormatService.format(String)`, bản mới đổi thành `format(Object)`. Metadata `Implementation-Version` hoặc `--module-version 1.0` không tự ngăn lỗi runtime. Một release process nên giữ API baseline, so signatures và **chạy consumer thực** với bản artifact dự kiến phát hành.

Ngoài method signatures, nếu public API được mô tả có resource path cố định hoặc service type name cố định, thay chúng cũng có thể là **behavioral/runtime breaking change** dù `javap` không phát hiện.

## 16. Bài luyện tập kèm đáp án

**Bài 1.** `FormatService` là `public interface`, nhưng app module báo package không visible. Lỗi ở đâu?

**Đáp án:** Contract module cần `exports com.example.contract` và app cần `requires com.example.contract`. `public` không phá ranh giới JPMS.

**Bài 2.** Provider JAR có `PrefixFormatter.class` nhưng `ServiceLoader` trả rỗng khi chạy trên module path. Đã đủ điều kiện chưa?

**Đáp án:** Chưa. Named provider module cần `provides FormatService with PrefixFormatter`; module phải được **resolve** trong graph/layer. Chỉ có implementation class không đủ.

**Bài 3.** Có cần `exports com.example.impl` để `ServiceLoader` tạo provider từ named module?

**Đáp án:** Không, với service declaration và constructor/provider method hợp lệ. Export package implementation có thể mở rộng API surface không cần thiết.

**Bài 4.** App chạy trên IDE nhưng bị `api metadata missing` khi chạy JAR. Cần sửa ở đâu?

**Đáp án:** Kiểm tra `META-INF/demo/api.properties` thực sự có trong app JAR, đúng path/encoding; không chỉ nhìn thư mục `src`.

**Bài 5.** Khi provider có mặt, tại sao vẫn có thể thấy `prefix resource missing`?

**Đáp án:** `ServiceLoader` chỉ chứng minh provider được khám phá/khởi tạo. Resource riêng của implementation vẫn có thể bị bỏ quên lúc đóng gói. Phải gọi `format(...)` trong smoke test.

**Bài 6.** Một classpath JAR cần đăng ký `FormatService` bằng cách nào?

**Đáp án:** File UTF-8 `META-INF/services/com.example.contract.FormatService`, nội dung gồm FQCN provider `com.example.impl.PrefixFormatter`. Trong named module sử dụng `provides`.

**Bài 7.** Vì sao không dùng `jdeps --check` là phép kiểm duy nhất?

**Đáp án:** `jdeps` phân tích static dependencies; nó không xác minh resource, việc chạy provider constructor hoặc thay đổi hành vi động. Cần runtime test.

**Bài 8.** `jar --list` có đủ để kết luận file resource đọc được?

**Đáp án:** Không. Có thể sai resource lookup path, module encapsulation hoặc nội dung/encoding. Phải đọc bằng API từ artifact thật.

**Bài 9.** `jlink` build thành công nhưng app chạy trong image không thấy provider. Điều tra gì?

**Đáp án:** Kiểm tra provider module có trong image qua `--add-modules` hoặc service binding, kiểm `provides`/`uses`, và thực hiện smoke test từ `image/bin/java`.

**Bài 10.** Khi nào nên dùng `Automatic-Module-Name`?

**Đáp án:** Với JAR **chưa có explicit `module-info.class`** muốn làm automatic module có tên ổn định. Nó không thay module descriptor của explicit module.

**Bài 11.** Có cần cấu hình `--bind-services` cho mọi custom image không?

**Đáp án:** Không. Nó có thể kéo nhiều providers/dependencies; nếu cần đúng một provider, roots explicit thường dễ kiểm soát. Dù chọn cách nào cũng phải test output image thực.

**Bài 12.** Một API vẫn ghi `api.version=1.0` nhưng thay tên method. Metadata có bảo đảm consumer cũ tương thích không?

**Đáp án:** Không. Version metadata dùng truy vết; phải so public API signatures và chạy consumer cũ với artifact mới.

**Bài 13.** `META-INF/demo/prefix.txt` có cần xem là public API contract không?

**Đáp án:** Chỉ khi nhà phát triển **công bố** consumer khác được phép phụ thuộc path/format đó. Nếu chỉ provider dùng nội bộ thì là implementation detail.

**Bài 14.** Có nên đưa API key vào file `api.properties` được đóng trong JAR?

**Đáp án:** Không. Người có JAR có thể giải nén xem nội dung. Secrets phải nằm ở hệ thống cấu hình/bí mật bảo vệ phù hợp deployment policy.

## 17. Checklist kiểm chứng trước khi phát hành

- [ ] Đã xác định **API contract**: module name, exported packages, public types và method signatures?
- [ ] Đã biên dịch theo `--release 11` và chạy trên các runtime cam kết hỗ trợ?
- [ ] `module-info.class` ở **gốc modular JAR** đúng module name?
- [ ] Consumer có `requires`/`uses`, provider có `requires`/`provides` tương ứng?
- [ ] Implementation provider có constructor/provider method hợp lệ và không cần export package nội bộ ngoài ý muốn?
- [ ] Provider module đã được **resolve**, không chỉ có file JAR trên disk?
- [ ] Non-class resources đã được **copy đúng path** vào artifact cuối?
- [ ] `Properties`/text resources có charset và schema xác định?
- [ ] `jar --list` và `jar --describe-module` đã kiểm đúng entries/directives?
- [ ] Với classpath, `META-INF/services/<service-FQCN>` có file UTF-8 và provider class names hợp lệ?
- [ ] Khi tạo fat JAR, service descriptors đã được merge và resource không bị strip?
- [ ] `jdeps`/module validation đã chạy, nhưng **không dùng thay runtime smoke**?
- [ ] Test chạy từ **JAR thực**, không lấy resource/implementation từ IDE test classpath?
- [ ] Test gọi `ServiceLoader` và **thực thi API method**, không chỉ đếm providers?
- [ ] Khi dùng `jlink`, đã chạy thử **image/bin/java** với đầy đủ providers/resources?
- [ ] Manifest/module version/Automatic-Module-Name được dùng đúng mục đích, không mâu thuẫn?
- [ ] Nếu có Multi-Release JAR, đã test đúng runtime version và resource variants?
- [ ] Không đóng gói secrets, private keys, test credentials hoặc dữ liệu không được phép?
- [ ] Release artifact có version/checksum và quy trình rebuild image khi cập nhật JDK?
- [ ] CI so tương thích API/binary và thực thi consumer trên bản phân phối cuối?

## 18. Tổng kết và tài liệu tham khảo

**Ghi nhớ:** một API Java 11 usable ngoài source tree cần **đủ class + module visibility + resources + service registration + metadata + runtime graph**. Biên dịch thành công chỉ là điều kiện đầu tiên; lỗi nghiêm trọng thường chỉ xuất hiện ở bước chạy bản JAR đã phát hành hoặc image đã link.

Bốn dòng output:

```text
api.version=1.0
provider=com.example.impl.PrefixFormatter
message=Hello, Java 11
verified=true
```

xác nhận cùng lúc rằng **app metadata được load**, **`ServiceLoader` phát hiện đúng provider**, **provider đọc được prefix resource** và **method API hoạt động**. Đây là kiểu smoke test có giá trị hơn việc chỉ nhìn một `.class` hiện diện trong archive.

**Nguồn Oracle/OpenJDK và hướng dẫn còn áp dụng:**

- [Oracle Java SE 11 — `ServiceLoader`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/ServiceLoader.html): provider trong named modules, `META-INF/services` trên classpath, cơ chế khởi tạo và lỗi.
- [Oracle Java SE 11 — `Module`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/Module.html): named module và resource encapsulation.
- [Oracle Java SE 11 — `Class.getResourceAsStream`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/Class.html): resource lookup path và module constraints.
- [Oracle Java SE 11 — `Properties`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/Properties.html): `load(InputStream)`/`load(Reader)` và encoding.
- [Oracle Java SE 11 — `javac`](https://docs.oracle.com/en/java/javase/11/tools/javac.html): `--release` và module compilation.
- [Oracle Java SE 11 — `jar`](https://docs.oracle.com/en/java/javase/11/tools/jar.html): modular JAR, `-C`, `--list`, `--describe-module` và module metadata.
- [Oracle Java SE 11 — `jdeps`](https://docs.oracle.com/en/java/javase/11/tools/jdeps.html): static dependencies/module graph.
- [Oracle Java SE 11 — `jlink`](https://docs.oracle.com/en/java/javase/11/tools/jlink.html): custom runtime và `--bind-services`.
- [OpenJDK JEP 261 — Module System](https://openjdk.org/jeps/261): nền tảng JPMS.
- [OpenJDK JEP 238 — Multi-Release JAR Files](https://openjdk.org/jeps/238): versioned classes/resources.
- [Dev.java — `jar`](https://dev.java/learn/jvm/core-tools/jar/): cách đóng gói JAR trên JDK mới.
- [Dev.java — `jlink`](https://dev.java/learn/jvm/core-tools/jlink/): service binding và custom image.
